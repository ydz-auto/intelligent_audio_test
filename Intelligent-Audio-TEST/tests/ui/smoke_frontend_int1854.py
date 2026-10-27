# -*- coding: utf-8 -*-
"""INT-1854 前端回归冒烟（React 15173 / 新Vue 16173），docker 真实库栈。

环境铁律（负责人 2026-10-23）：后端网关 http://localhost:15000（database=intelligent_audio_test），
前端 React http://localhost:15173 / 新Vue http://localhost:16173。不启动任何本地栈。

冒烟链路（每前端逐条走，真实数据）：
  1 登录 / 会话保持 / 登出
  2 任务列表 → 任务详情（报告页签计数 vs /reports/by_task/{id}）
  3 用例列表 → 用例详情（维度 / 轮次 / 音频渲染）
  4 报告中心 → 报告详情 / HTML 导出
  5 开始测试入口 + 分组数与 /api/v1/groups 一致（不提交真实执行）

跑法：
  <conda python> tests/ui/smoke_frontend_int1854.py --kind react --base http://localhost:15173
  <conda python> tests/ui/smoke_frontend_int1854.py --kind vue   --base http://localhost:16173

产出：tests/ui/artifacts/int1854/<kind>/summary.json + 浅/深色截图。
只读冒烟；不写业务数据。
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART_ROOT = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1854')
CHROME_BINARY = os.environ.get(
    'UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
API = os.environ.get('API_BASE', 'http://localhost:15000').rstrip('/')
USERNAME = os.environ.get('UI_TEST_USERNAME', '接线测试_admin')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'JieXianTest@2026')

NET_PATCH = r"""
window.__net = {started:0, inflight:0, last:Date.now(), urls:[]};
function __track(url, done){ if(url && url.indexOf('/sse/')>=0) return;
  window.__net.started++; window.__net.inflight++; window.__net.last=Date.now(); window.__net.urls.push(url);
  const settle=function(){window.__net.inflight=Math.max(0,window.__net.inflight-1); window.__net.last=Date.now();};
  done&&done(settle);}
const __of=window.fetch;
window.fetch=function(input,init){const url=typeof input==='string'?input:(input&&input.url)||'';let settle;__track(url,function(s){settle=s;});const p=__of.apply(this,arguments);if(settle){p.then(settle,settle);}return p;};
const __xo=XMLHttpRequest.prototype.open;const __xs=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open=function(m,u){this.__u=u;return __xo.apply(this,arguments);};
XMLHttpRequest.prototype.send=function(){const x=this;let settle;__track(String(x.__u||''),function(s){settle=s;});if(settle){x.addEventListener('loadend',settle);}return __xs.apply(this,arguments);};
"""

RESULT = {'env': {}, 'chains': {}, 'screenshots': [], 'notes': []}


def log(msg):
    print('[int1854] %s' % msg, flush=True)


# ── HTTP（只读）────────────────────────────────────────────
def http_json(path, timeout=60):
    url = API + '/api/v1' + path
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {'raw': raw[:300]}


def env_check(tag):
    with urllib.request.urlopen(API + '/health', timeout=20) as r:
        health = json.loads(r.read().decode('utf-8'))
    rec = {'tag': tag, 'health': health}
    RESULT['env'][tag] = rec
    log('ENV[%s] database=%s version=%s' % (tag, health.get('database'), health.get('version')))
    assert health.get('database') == 'intelligent_audio_test', '环境串库: %s' % health
    return rec


# ── 浏览器 ─────────────────────────────────────────────────
def make_driver(download_dir):
    opts = Options()
    opts.binary_location = CHROME_BINARY
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu',
              '--no-sandbox', '--lang=zh-CN', '--disable-dev-shm-usage'):
        opts.add_argument(a)
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    drv = webdriver.Chrome(options=opts)
    drv.set_page_load_timeout(90)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': NET_PATCH})
    try:
        drv.execute_cdp_cmd('Page.setDownloadBehavior',
                            {'behavior': 'allow', 'downloadPath': download_dir})
    except Exception:
        pass
    return drv


def body_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : ""') or ''


def wait_quiet(drv, timeout=35, quiet_ms=1200):
    deadline = time.time() + timeout
    time.sleep(1.0)
    while time.time() < deadline:
        try:
            st = drv.execute_script('return window.__net || null')
        except Exception:
            st = None
        if st and st.get('started', 0) > 0 and st.get('inflight', 0) == 0:
            if time.time() * 1000 - st.get('last', 0) >= quiet_ms:
                return True
        time.sleep(0.25)
    return False


def parse_perf(raw_logs):
    pending, out = {}, []
    for entry in raw_logs:
        try:
            inner = json.loads(entry.get('message', '{}')).get('message', {})
            method, params = inner.get('method', ''), inner.get('params', {})
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            req = params.get('request', {})
            pending[params.get('requestId')] = {'method': req.get('method'), 'url': req.get('url')}
        elif method == 'Network.responseReceived':
            resp = params.get('response', {})
            rec = dict(pending.get(params.get('requestId')) or {})
            rec['url'] = rec.get('url') or resp.get('url')
            rec['status'] = resp.get('status')
            rec['mime'] = resp.get('mimeType')
            if '/api/v1/' in (rec.get('url') or ''):
                out.append(rec)
    seen, uniq = set(), []
    for r in out:
        key = (r.get('method'), r.get('url'), r.get('status'))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def api_errors(apis):
    return [a for a in apis if isinstance(a.get('status'), int) and a['status'] >= 400]


def console_errors(drv):
    errs = []
    try:
        for e in drv.get_log('browser'):
            if e.get('level') != 'SEVERE':
                continue
            msg = str(e.get('message', ''))
            if 'favicon' in msg:
                continue
            errs.append(msg[:300])
    except Exception:
        pass
    return errs


def shot(drv, key):
    os.makedirs(RESULT['art'], exist_ok=True)
    path = os.path.join(RESULT['art'], key + '.png')
    drv.save_screenshot(path)
    RESULT['screenshots'].append({'name': key, 'size': os.path.getsize(path)})
    log('SHOT %s (%d bytes)' % (key, os.path.getsize(path)))
    return {'path': path, 'size': os.path.getsize(path)}


def click_js(drv, el):
    drv.execute_script('arguments[0].click()', el)


def find_buttons(drv, texts=None, contains=None):
    out = []
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if not b.is_displayed():
                continue
        except Exception:
            continue
        t = (b.text or '').strip()
        if texts and t in texts:
            out.append(b)
        elif contains and any(c in t for c in contains):
            out.append(b)
    return out


class Smoke(object):
    def __init__(self, kind, base):
        self.kind = kind
        self.vue = kind == 'vue'
        self.base = base.rstrip('/')
        self.drv = None
        RESULT['art'] = os.path.join(ART_ROOT, kind)
        RESULT['kind'] = kind
        RESULT['base'] = self.base

    # 前端路由：Vue 用 hash 路由
    def url(self, path):
        if self.vue:
            return self.base + '/#/' + path.lstrip('/')
        return self.base + path

    # ── 1 登录 / 会话 / 登出 ────────────────────────────────
    def login(self):
        d = self.drv
        rec = {'ok': False}
        if self.vue:
            d.get(self.base + '/')
            WebDriverWait(d, 45).until(
                EC.presence_of_element_located((By.TAG_NAME, 'button')))
            time.sleep(2.5)
            cands = [b for b in d.find_elements(By.TAG_NAME, 'button')
                     if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
            if not cands:
                # 登出后可能仍停在带模态的页面：关掉模态重载
                d.execute_script('window.localStorage.clear()')
                d.get(self.base + '/')
                time.sleep(4)
                cands = [b for b in d.find_elements(By.TAG_NAME, 'button')
                         if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
            if not cands:
                raise AssertionError('登录入口按钮未找到')
            click_js(d, cands[0])
            WebDriverWait(d, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
        else:
            d.get(self.base + '/login')
            try:
                WebDriverWait(d, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
            except Exception:
                # 登出后守卫可能停在首页：清一次本地态再进登录页
                d.execute_script('window.localStorage.clear()')
                d.get(self.base + '/login')
                time.sleep(2)
                WebDriverWait(d, 45).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
        time.sleep(1.0)
        u = [e for e in d.find_elements(By.CSS_SELECTOR, 'input')
             if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
        p = [e for e in d.find_elements(By.CSS_SELECTOR, 'input[type=password]')
             if e.is_displayed()][0]
        u.clear(); u.send_keys(USERNAME)
        p.clear(); p.send_keys(PASSWORD)
        btns = [b for b in d.find_elements(By.TAG_NAME, 'button')
                if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
        if not btns:
            btns = [b for b in d.find_elements(By.CSS_SELECTOR, 'button[type=submit]')
                    if b.is_displayed()]
        click_js(d, btns[-1])
        WebDriverWait(d, 45).until(lambda dd: 'login' not in dd.current_url.lower())
        time.sleep(3)
        rec['url_after'] = d.current_url
        rec['ls_keys'] = d.execute_script('return Object.keys(window.localStorage)')
        rec['apis'] = parse_perf(d.get_log('performance'))
        rec['token_stored'] = any('token' in k for k in (rec['ls_keys'] or []))
        rec['login_post_ok'] = any('/auth/login' in (a.get('url') or '') and a.get('status') == 200
                                   for a in rec['apis'])
        rec['ok'] = rec['login_post_ok'] and rec['token_stored']
        # 会话保持：刷新后仍在工作台
        d.refresh(); time.sleep(4)
        rec['after_reload_url'] = d.current_url
        rec['session_kept'] = 'login' not in d.current_url.lower().split('#')[-1]
        rec['ok'] = rec['ok'] and rec['session_kept']
        rec['shot'] = shot(d, '01_%s_login_after' % self.kind)
        return rec

    def logout(self):
        d = self.drv
        rec = {'ok': False}
        before = d.current_url
        try:
            # 打开用户菜单：React 是 aria-label=用户菜单；Vue 是含用户名的按钮
            menu = None
            for b in d.find_elements(By.TAG_NAME, 'button'):
                if not b.is_displayed():
                    continue
                aria = b.get_attribute('aria-label') or ''
                if aria in ('用户菜单', '账户菜单'):
                    menu = b
                    break
            if menu is None:
                for b in d.find_elements(By.TAG_NAME, 'button'):
                    if b.is_displayed() and USERNAME in (b.text or ''):
                        menu = b
                        break
            if menu is None:
                for b in d.find_elements(By.CSS_SELECTOR, '[aria-label*=用户], [aria-label*=账户]'):
                    if b.is_displayed():
                        menu = b
                        break
            if menu is None:
                rec['error'] = '用户菜单按钮未找到'
                return rec
            click_js(d, menu)
            time.sleep(1.5)
            items = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=menuitem], button, a, [role=menuitem]')
                     if e.is_displayed() and ('退出' in (e.text or '') or '登出' in (e.text or ''))]
            rec['menu_items'] = [e.text.strip()[:20] for e in items]
            if not items:
                rec['error'] = '菜单无退出项'
                return rec
            click_js(d, items[0])
            time.sleep(2)
            # 有确认弹窗时点确认（React 确认登出弹窗主钮文案「登出」）
            dlgs = [x for x in d.find_elements(By.CSS_SELECTOR, '[role=dialog], [role=alertdialog]')
                    if x.is_displayed()]
            if dlgs:
                for b in dlgs[0].find_elements(By.TAG_NAME, 'button'):
                    if b.is_displayed() and (b.text or '').strip() in ('确定', '确认', '退出', '登出', '退出登录'):
                        click_js(d, b)
                        break
                time.sleep(3)
            else:
                # Vue 自定义模态（非 role=dialog）：点可见的确认钮
                conf = [b for b in d.find_elements(By.TAG_NAME, 'button')
                        if b.is_displayed() and (b.text or '').strip() in ('确定', '确认', '登出', '退出登录')]
                if conf:
                    click_js(d, conf[-1])
                    time.sleep(3)
            time.sleep(2)
            rec['url_after'] = d.current_url
            rec['ls_keys'] = d.execute_script('return Object.keys(window.localStorage)')
            rec['token_cleared'] = not any('token' in (k or '') for k in (rec['ls_keys'] or []))
            rec['redirected_login'] = 'login' in d.current_url.lower()
            rec['ok'] = rec['token_cleared'] or rec['redirected_login']
            rec['shot'] = shot(d, '02_%s_after_logout' % self.kind)
        except Exception as exc:
            rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
        rec['url_before'] = before
        return rec

    # ── 2 任务列表 → 任务详情（报告页签计数）────────────────
    def chain_tasks(self):
        d = self.drv
        out = {'ok': False, 'steps': {}, 'api_errors': []}
        path = '/tasks' if self.vue else '/tasks/daily'
        d.get(self.url(path))
        time.sleep(3)
        if self.vue:
            WebDriverWait(d, 60).until(
                lambda dd: len([b for b in dd.find_elements(By.TAG_NAME, 'button')
                                if b.is_displayed() and b.text.strip() == '查看详情']) > 0)
        else:
            WebDriverWait(d, 60).until(
                lambda dd: len(dd.find_elements(By.CSS_SELECTOR, "button[title='查看详情']")) > 0)
        wait_quiet(d, 30)
        st, tasks = http_json('/tasks?page=1&per_page=10')
        api_total = (tasks.get('data') or {}).get('total')
        if self.vue:
            rows = [b for b in d.find_elements(By.TAG_NAME, 'button')
                    if b.is_displayed() and b.text.strip() == '查看详情']
            page_text = body_text(d)
        else:
            rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'tbody tr') if r.is_displayed()]
        out['steps']['list'] = {
            'api_total': api_total,
            'row_count': len(rows),
            'total_in_page': (re.search(r'共\s*(\d+)\s*条', body_text(d)).group(1)
                              if re.search(r'共\s*(\d+)\s*条', body_text(d)) else None),
        }
        list_apis = parse_perf(d.get_log('performance'))
        out['list_apis'] = [a for a in list_apis if '/tasks' in (a.get('url') or '')][:6]
        out['shot_list'] = shot(d, '03_%s_task_list' % self.kind)
        # 打开第一行详情
        if self.vue:
            click_js(d, rows[0])
        else:
            click_js(d, rows[0].find_element(By.CSS_SELECTOR, "button[title='查看详情']"))
        time.sleep(6)
        wait_quiet(d, 30)
        # 详情页报告区在下方，滚到底触发渲染
        d.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(3)
        det_text = body_text(d)
        out['steps']['detail'] = {
            'url': d.current_url,
            'has_report_section': '报告' in det_text,
            'text_tail': det_text[-500:],
        }
        out['shot_detail'] = shot(d, '04_%s_task_detail' % self.kind)
        out['detail_apis'] = parse_perf(d.get_log('performance'))
        # 报告计数交叉核对：对列表首条任务
        m = re.search(r'/tasks/(\d+)', d.current_url)
        task_id = int(m.group(1)) if m else None
        if task_id is None:
            st, tj = http_json('/tasks?page=1&per_page=1')
            task_id = ((tj.get('data') or {}).get('items') or [{}])[0].get('id')
        out['task_id'] = task_id
        out['report_check'] = self.report_count_check(d, task_id)
        # 深色
        self.set_theme(True)
        d.refresh(); time.sleep(5)
        out['shot_detail_dark'] = shot(d, '04_%s_task_detail_dark' % self.kind)
        self.set_theme(False)
        out['api_errors'] = api_errors(list_apis)
        out['ok'] = (out['steps']['list']['row_count'] > 0
                     and bool(out['steps']['detail']['url'])
                     and out['report_check'].get('match') is True)
        return out

    def report_count_check(self, drv, task_id):
        """任务详情报告区与 /reports/by_task/{id} 对照。

        INT-2116 校正：当前 React 任务详情不再内联报告名/空态提示——任务无报告时
        TaskReportDocuments 取到 null 不渲染报告区；有报告时渲染「报告文档」区
        （无 Studio 文档则显示空态文案「该任务的报告暂无关联文档」）。按新口径：
          - 404（无报告）：详情页正常渲染（未进入「任务详情加载失败」错误态）即接受；
            页面空态文案仅作信息记录。
          - 200（有报告）：报告名或「报告文档」区任一可见即接受。
        """
        rec = {'task_id': task_id}
        st, resp = http_json('/reports/by_task/%s' % task_id, timeout=90)
        rec['api_status'] = st
        txt = body_text(drv)
        if st == 200:
            data = resp.get('data') or {}
            name = data.get('name') or ''
            rec['api_has_report'] = True
            rec['api_report_name'] = name[:40]
            rec['ui_has_report'] = bool(name and name[:20] in txt)
            rec['ui_has_doc_section'] = '报告文档' in txt
            rec['ui_empty_doc_hints'] = [h for h in ('暂无关联文档', '该任务的报告暂无关联文档')
                                         if h in txt]
            rec['match'] = bool((name and name[:20] in txt) or '报告文档' in txt)
        elif st == 404:
            rec['api_has_report'] = False
            hints = [h for h in ('暂无报告', '无报告', '没有报告', '暂未生成', '不适用', '未生成')
                     if h in txt]
            rec['ui_empty_hints'] = hints
            rec['detail_ok'] = '任务详情加载失败' not in txt
            rec['match'] = rec['detail_ok']
        else:
            rec['match'] = None
        return rec

    # ── 3 用例列表 → 用例详情（维度 / 轮次 / 音频）──────────
    def chain_cases(self):
        d = self.drv
        out = {'ok': False}
        d.get(self.url('/testcases'))
        time.sleep(5)
        wait_quiet(d, 40)
        # 展开首个分组：点分组行（标题形如「话轮接管 211 条」）→ 摊平用例卡
        expanded = False
        st, gr = http_json('/groups?page=1&per_page=100')
        gnames = [g.get('name') for g in ((gr.get('data') or {}).get('items') or [])][:6]
        for gname in gnames:
            if not gname:
                continue
            cands = d.execute_script("""
              const name = arguments[0];
              const out = [];
              for (const el of document.querySelectorAll('div,section,article,li')) {
                const t = (el.innerText || '').trim();
                if (!t.startsWith(name)) continue;
                if (t.length > 160) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 400 || r.height > 220) continue;
                out.push(el);
              }
              return out.slice(-1);
            """, gname)
            if not cands:
                continue
            click_js(d, cands[0])
            time.sleep(4)
            wait_quiet(d, 25)
            if re.search(r'\d+\s*轮', body_text(d)) or '测试用例_' in body_text(d):
                expanded = True
                break
        txt = body_text(d)
        out['expanded'] = expanded
        out['shot_list'] = shot(d, '05_%s_case_list' % self.kind)
        out['list_apis'] = parse_perf(d.get_log('performance'))
        out['rounds_visible'] = bool(re.search(r'\d+\s*轮', txt))
        out['cases_visible'] = ('测试用例_' in txt) or ('用例ID' in txt)
        # 详情入口：按钮 title/aria 含「用例详情」，或报告详情里的用例详情弹窗
        entry = None
        for sel in ("button[title='查看用例详情']", "button[aria-label='查看用例详情']"):
            els = [e for e in d.find_elements(By.CSS_SELECTOR, sel) if e.is_displayed()]
            if els:
                entry = els[0]
                break
        if entry is None:
            for b in d.find_elements(By.TAG_NAME, 'button'):
                try:
                    if not b.is_displayed():
                        continue
                except Exception:
                    continue
                label = (b.get_attribute('title') or '') + (b.get_attribute('aria-label') or '')
                if '用例详情' in label:
                    entry = b
                    break
        out['detail_entry_found'] = entry is not None
        if entry is not None:
            click_js(d, entry)
            time.sleep(3)
            wait_quiet(d, 20)
            dtxt = body_text(d)
            out['detail_text_head'] = dtxt[:600]
            out['detail_has_dimension'] = '维度' in dtxt
            out['detail_has_rounds'] = bool(re.search(r'第\s*\d+\s*/\s*\d+\s*轮|\d+\s*轮', dtxt))
            out['detail_has_audio'] = ('音频' in dtxt) or ('试听' in dtxt) or ('播放' in dtxt)
            out['detail_apis'] = parse_perf(d.get_log('performance'))
            out['shot_detail'] = shot(d, '06_%s_case_detail' % self.kind)
            ok_detail = all([out['detail_has_dimension'], out['detail_has_rounds'], out['detail_has_audio']])
        else:
            # 无抽屉入口：记录用例卡上可见的维度/轮次/音频证据
            out['detail_note'] = '用例列表未找到「查看用例详情」入口'
            out['card_has_audio_action'] = bool(
                [b for b in d.find_elements(By.TAG_NAME, 'button')
                 if b.is_displayed() and any(k in ((b.get_attribute('aria-label') or '') + (b.get_attribute('title') or '') + (b.text or ''))
                                             for k in ('试听', '音频', '播放'))])
            ok_detail = False
        # 深色
        self.set_theme(True)
        d.refresh(); time.sleep(4)
        out['shot_list_dark'] = shot(d, '05_%s_case_list_dark' % self.kind)
        self.set_theme(False)
        out['ok'] = bool(out['cases_visible'] and out['rounds_visible'] and ok_detail)
        return out

    # ── 4 报告中心 → 报告详情 / HTML 导出 ───────────────────
    def chain_reports(self):
        d = self.drv
        out = {'ok': False}
        d.get(self.url('/report-center'))
        time.sleep(5)
        wait_quiet(d, 40)
        st, rc = http_json('/reports?page=1&per_page=20&sort_by=created_at&order=desc&deleted=false')
        items = (rc.get('data') or {}).get('items') or []
        out['api_reports'] = len(items)
        out['center_text_head'] = body_text(d)[:200]
        out['shot_center'] = shot(d, '07_%s_report_center' % self.kind)
        # 打开首个已发布报告（有预览价值的），否则首个
        target = next((i for i in items if i.get('status') == 'published'), items[0] if items else None)
        if target is None:
            out['error'] = '报告列表为空'
            return out
        out['report'] = {'id': target.get('id'), 'name': (target.get('name') or '')[:40],
                         'status': target.get('status')}
        if self.vue:
            # 行内「查看」按钮
            names = [i for i in items]
            click = None
            for b in d.find_elements(By.TAG_NAME, 'button'):
                if b.is_displayed() and b.text.strip() == '查看':
                    click = b
                    break
            if click is None:
                raise AssertionError('报告中心行内「查看」未找到')
            click_js(d, click)
        else:
            rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'tbody tr') if r.is_displayed()]
            if not rows:
                raise AssertionError('报告中心无行')
            click_js(d, rows[0])
        time.sleep(7)
        wait_quiet(d, 40)
        out['detail'] = {'url': d.current_url, 'text_head': body_text(d)[:400]}
        out['detail_apis'] = parse_perf(d.get_log('performance'))
        out['shot_detail'] = shot(d, '08_%s_report_detail' % self.kind)
        # HTML 导出
        out['export'] = self.export_html(d)
        # 深色
        self.set_theme(True)
        time.sleep(2)
        out['shot_detail_dark'] = shot(d, '08_%s_report_detail_dark' % self.kind)
        self.set_theme(False)
        out['ok'] = bool(out['detail']['url']) and bool(out['export'].get('ok'))
        return out

    def export_html(self, d):
        """报告详情「导出」→ 弹窗选格式 html → 导出，校验导出请求 2xx。"""
        rec = {'ok': False}
        try:
            parse_perf(d.get_log('performance'))  # 清空
            exp = find_buttons(d, texts=('导出', '导出报告', 'HTML 导出'))
            if not exp:
                exp = find_buttons(d, contains=('导出',))
            if not exp:
                rec['error'] = '报告详情无导出按钮'
                return rec
            click_js(d, exp[0])
            time.sleep(2.5)
            # 导出弹窗：tab 导出 / 导出进度 / 导出历史 + 格式 combobox + 主钮
            dlgs = [x for x in d.find_elements(By.CSS_SELECTOR, '[role=dialog]') if x.is_displayed()]
            scope = dlgs[-1] if dlgs else d
            rec['dialog_open'] = bool(dlgs)
            if dlgs:
                rec['dialog_text'] = dlgs[-1].text[:300]
                # 格式下拉：默认 csv → 选 html
                combo = [b for b in scope.find_elements(By.CSS_SELECTOR, '[role=combobox], button')
                         if b.is_displayed() and (b.text or '').strip().lower() in ('csv', 'excel', 'pdf', 'html', 'json')]
                if combo:
                    click_js(d, combo[0])
                    time.sleep(1.5)
                    opts = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=option], [role=menuitem]')
                            if e.is_displayed() and (e.text or '').strip().lower().startswith('html')]
                    if opts:
                        click_js(d, opts[0])
                    else:
                        # 原生 select
                        try:
                            d.execute_script(
                                "const s=arguments[0]; s.value='html';"
                                "s.dispatchEvent(new Event('change',{bubbles:true}));", combo[0])
                        except Exception:
                            pass
                    time.sleep(1.0)
                    rec['format_selected'] = 'html'
                # 主钮「导出」
                mains = [b for b in scope.find_elements(By.TAG_NAME, 'button')
                         if b.is_displayed() and (b.text or '').strip() == '导出']
                if mains:
                    click_js(d, mains[-1])
                    time.sleep(6)
            apis = parse_perf(d.get_log('performance'))
            hits = [a for a in apis if '/export' in (a.get('url') or '')]
            rec['export_apis'] = hits
            rec['ok'] = any(200 <= (h.get('status') or 0) < 300 for h in hits)
            if not rec['ok']:
                rec['error'] = '未观察到 2xx 导出请求: %s' % (hits or 'none')
        except Exception as exc:
            rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:250])
            try:
                rec['shot'] = shot(d, '08_%s_export_fail' % self.kind)
            except Exception:
                pass
        return rec

    # ── 5 开始测试入口 + 分组数一致 ─────────────────────────
    def chain_start_test(self):
        d = self.drv
        out = {'ok': False}
        d.get(self.url('/start-test'))
        time.sleep(6)
        wait_quiet(d, 40)
        txt = body_text(d)
        out['url'] = d.current_url
        out['text_head'] = txt[:300]
        out['steps_visible'] = ('选择测试用例' in txt) or ('选择用例' in txt)
        apis = parse_perf(d.get_log('performance'))
        out['apis'] = apis
        out['shot'] = shot(d, '09_%s_start_test' % self.kind)
        # 分组数：页面 «已显示 5 / N 个分组»
        m = re.search(r'已显示\s*\d+\s*/\s*(\d+)\s*个分组', txt)
        ui_groups = int(m.group(1)) if m else None
        st, g = http_json('/groups?page=1&per_page=1000')
        api_groups = (g.get('data') or {}).get('total') or len((g.get('data') or {}).get('items') or [])
        out['group_compare'] = {'ui': ui_groups, 'api': api_groups}
        # 前端实际拉取的分组请求
        out['group_requests'] = [a for a in apis if '/groups' in (a.get('url') or '')]
        out['group_match'] = (ui_groups is not None and ui_groups == api_groups)
        # 深色
        self.set_theme(True)
        d.refresh(); time.sleep(5)
        wait_quiet(d, 30)
        out['shot_dark'] = shot(d, '09_%s_start_test_dark' % self.kind)
        self.set_theme(False)
        out['ok'] = bool(out['steps_visible'] and out['group_match'])
        return out

    # ── 主题 ───────────────────────────────────────────────
    def set_theme(self, dark):
        d = self.drv
        if self.vue:
            # 深色按钮：切换为深色 / 切换为浅色
            try:
                label = '切换为浅色' if dark else '切换为深色'
                btns = [b for b in d.find_elements(By.TAG_NAME, 'button')
                        if b.is_displayed() and (b.get_attribute('title') or '') == label]
                if btns:
                    click_js(d, btns[0]); time.sleep(2)
            except Exception:
                pass
            # 兜底：写 localStorage 主题键
            try:
                d.execute_script(
                    "localStorage.setItem('theme', arguments[0]);"
                    "document.documentElement.classList.toggle('dark', !!(arguments[0]||'').includes('dark'));",
                    'dark' if dark else 'light')
            except Exception:
                pass
        else:
            try:
                d.execute_script(
                    'localStorage.setItem("iatp:theme:v1:mode", arguments[0]);', 'dark' if dark else 'light')
            except Exception:
                pass

    # ── 编排 ───────────────────────────────────────────────
    def run(self):
        env_check('start')
        download_dir = os.path.join(RESULT['art'], 'downloads')
        os.makedirs(download_dir, exist_ok=True)
        self.drv = make_driver(download_dir)
        d = self.drv
        try:
            RESULT['chains']['1_login'] = self.login()
            if not RESULT['chains']['1_login'].get('ok'):
                raise AssertionError('登录失败')
            RESULT['chains']['1_logout'] = self.logout()
            # 登出后重新登录，继续其余链路
            try:
                RESULT['chains']['1_relogin'] = self.login()
            except Exception as exc:
                RESULT['chains']['1_relogin'] = {
                    'ok': False, 'error': '%s: %s' % (type(exc).__name__, str(exc)[:300])}
                log('RELOGIN failed: %s' % exc)
            for name, fn in (('2_tasks', self.chain_tasks),
                             ('3_cases', self.chain_cases),
                             ('4_reports', self.chain_reports),
                             ('5_start_test', self.chain_start_test)):
                try:
                    RESULT['chains'][name] = fn()
                except Exception as exc:
                    RESULT['chains'][name] = {
                        'ok': False,
                        'error': '%s: %s' % (type(exc).__name__, str(exc)[:300]),
                        'trace': traceback.format_exc()[-700:]}
                    log('CHAIN %s ERROR %s' % (name, exc))
                log('CHAIN %s ok=%s' % (name, RESULT['chains'][name].get('ok')))
            RESULT['console_errors'] = console_errors(d)
            env_check('end')
        finally:
            try:
                d.quit()
            except Exception:
                pass


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--kind', required=True, choices=['react', 'vue'])
    ap.add_argument('--base', required=True)
    args = ap.parse_args()
    os.makedirs(ART_ROOT, exist_ok=True)

    sm = Smoke(args.kind, args.base)
    sm.run()

    out_path = os.path.join(RESULT['art'], 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('\nSUMMARY_JSON=%s' % out_path)
    for k, v in RESULT['chains'].items():
        if isinstance(v, dict):
            print('CHAIN %-14s ok=%s note=%s' % (k, v.get('ok'), (v.get('error') or '')[:120]))


if __name__ == '__main__':
    main()
