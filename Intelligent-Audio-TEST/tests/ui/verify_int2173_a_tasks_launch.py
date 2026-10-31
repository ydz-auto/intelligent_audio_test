# -*- coding: utf-8 -*-
"""INT-2173 走查·React 任务执行域 A 部分：
任务列表页签/分页/搜索/筛选、任务创建（algorithm_type 落库）、
实时日志 WS 增量、通知去重/角标、启动跳执行步、跨页刷新。
只写「接线测试_」前缀自建数据，收尾按 id 软删+purge。
"""
import json
import os
import re
import sys
import urllib.parse
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2173')
os.makedirs(ART, exist_ok=True)
TS = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT2173_%s' % TS
RESULTS = []
CTX = {'created_task': None, 'http': []}


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1200]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)[:400]) if detail else ''))
    return ok


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text or ''


def wait_text(drv, text, timeout=60):
    return WebDriverWait(drv, timeout).until(lambda d: text in body(d))


def js_click_text(drv, text, scope_sel='body', exact=True):
    return drv.execute_script('''
      const scope = document.querySelector(arguments[1]) || document.body;
      const want = arguments[0];
      for (const el of scope.querySelectorAll('button, a, [role=button], [role=tab], [role=checkbox], li, span')) {
        const t = (el.textContent||'').trim();
        if (arguments[2] ? t === want : t.includes(want)) {
          if (!(el.offsetWidth || el.offsetHeight)) continue;
          el.click();
          return true;
        }
      }
      return false;
    ''', text, scope_sel, exact)


def list_total(drv):
    """当前列表分页「共 N 条」/「1–x / N」。"""
    t = body(drv)
    m = re.search(r'共\s*([\d,]+)\s*条', t) or re.search(r'\d+\s*[–-]\s*\d+\s*/\s*([\d,]+)', t)
    return int(m.group(1).replace(',', '')) if m else None


def api_total(path, token):
    st, d = B.api(path, token)
    data = d.get('data') or {}
    return st, data.get('total', data.get('stats', {}).get('total') if isinstance(data.get('stats'), dict) else None)


def open_daily(drv):
    B.goto(drv, '/tasks/daily', timeout=90)
    wait_text(drv, '任务名称', 60)
    time.sleep(1.2)


def header_snapshot(drv):
    scripts = drv.execute_script("return [...document.querySelectorAll('script[src]')].map(s=>s.src).filter(s=>/index\\.|lib-react/.test(s))")
    return scripts


def main():
    token, user = B.rsa_login_token('接线测试_admin', 'JieXianTest@2026')
    st, health = B.api('/health', None)
    print('health', st, health)
    check('开工核对 /health database=intelligent_audio_test', health.get('database') == 'intelligent_audio_test', health)

    drv = B.driver_init()
    try:
        B.bootstrap(drv, token, user)
        CTX['headers_start'] = header_snapshot(drv)
        open_daily(drv)

        # ---------------- 1. 列表页签 / 分页 / 搜索 / 筛选 ----------------
        st, t_daily = api_total('/api/v1/tasks?page=1&per_page=10', token)
        ui_total = list_total(drv)
        check('日常页签：UI 列表总数 = GET /tasks total', ui_total == t_daily,
              {'ui': ui_total, 'api': t_daily})
        tab_labels = [x.text.split('\n')[0].strip() for x in drv.find_elements(By.CSS_SELECTOR, '[role=tab]')]
        check('任务页签实为 3 个（日常/已发布/挑选合并），「收藏」是筛选开关而非第 4 页签',
              tab_labels == ['日常', '已发布', '挑选合并'] and '只看收藏' in body(drv),
              {'tabs': tab_labels})
        shot(drv, 'A01_daily_light')

        # 搜索
        box = drv.find_element(By.XPATH, "//input[@placeholder='搜索任务名称、描述或标签']")
        B.set_input(drv, box, 'matrix_physical')
        js_click_text(drv, '查询')
        time.sleep(2.5)
        st, t_search = api_total('/api/v1/tasks?page=1&per_page=10&search=matrix_physical', token)
        ui_search = list_total(drv)
        rows_ok = 'matrix_physical_1793353430' in body(drv) and 'INT2173' not in body(drv)
        check('日常页签：搜索 matrix_physical → UI total=API search total 且命中行',
              ui_search == t_search and rows_ok, {'ui': ui_search, 'api': t_search, 'rows_ok': rows_ok})
        shot(drv, 'A02_daily_search')
        # 清空搜索
        B.set_input(drv, box, '')
        js_click_text(drv, '查询')
        time.sleep(2)

        # 执行状态筛选：已完成
        opened = drv.execute_script('''
          for (const el of document.querySelectorAll('button,[role=combobox]')) {
            const t=(el.textContent||'').replace(/\\s+/g,' ').trim();
            if (t.startsWith('执行状态')) { el.click(); return true; }
          }
          return false;
        ''')
        time.sleep(1)
        picked = js_click_text(drv, '已完成', scope_sel='[role=dialog], [data-slot=popover-content]')
        if not picked:
            picked = drv.execute_script('''
              for (const el of document.querySelectorAll('[role=option], [data-slot=select-item], div[role=menuitem]')) {
                if ((el.textContent||'').trim() === '已完成') { el.click(); return true; }
              }
              return false;
            ''')
        time.sleep(1.5)
        js_click_text(drv, '查询')
        time.sleep(2.5)
        st, t_done = api_total('/api/v1/tasks?page=1&per_page=10&execution_status=completed', token)
        ui_done = list_total(drv)
        check('日常页签：执行状态=已完成 筛选 UI total=API total',
              ui_done == t_done, {'ui': ui_done, 'api': t_done, 'opened': opened, 'picked': picked})
        shot(drv, 'A03_daily_filter_done')
        # 重置（点页面「重置」或筛选器）
        js_click_text(drv, '重置')
        time.sleep(2)

        # 分页：点第 2 页
        p2 = drv.execute_script('''
          for (const el of document.querySelectorAll('button, a')) {
            const t=(el.textContent||'').trim();
            if (t === '2' && (el.offsetWidth||el.offsetHeight)) { el.click(); return true; }
          }
          return false;
        ''')
        time.sleep(2.5)
        t = body(drv)
        check('日常页签：分页切到第 2 页（页码区域显示 11–20 / total）',
              p2 and re.search(r'11\s*[–-]\s*20\s*/\s*\d+', t) is not None,
              {'p2': p2, 'pag': re.findall(r'\d+\s*[–-]\s*\d+\s*/\s*\d+', t)[:3]})
        shot(drv, 'A04_daily_page2')

        # 已发布页签
        B.goto(drv, '/tasks/published', timeout=90)
        wait_text(drv, '任务名称' if False else '名称/说明', 60)
        time.sleep(1.2)
        st, t_pub = api_total('/api/v1/published-tasks?page=1&per_page=10', token)
        ui_pub = list_total(drv)
        check('已发布页签：UI total=GET /published-tasks total', ui_pub == t_pub, {'ui': ui_pub, 'api': t_pub})
        shot(drv, 'A05_published')
        # 已发布搜索
        sbox = drv.find_element(By.XPATH, "//input[@placeholder='搜索任务名称、描述或标签']")
        B.set_input(drv, sbox, 'INT2070')
        js_click_text(drv, '查询')
        time.sleep(2.5)
        st, t_pub_s = api_total('/api/v1/published-tasks?page=1&per_page=10&keyword=INT2070', token)
        ui_pub_s = list_total(drv)
        check('已发布页签：搜索 keyword 生效且 total 一致', ui_pub_s == t_pub_s,
              {'ui': ui_pub_s, 'api': t_pub_s})
        shot(drv, 'A06_published_search')

        # 挑选合并页签
        B.goto(drv, '/tasks/cherry-picks', timeout=90)
        wait_text(drv, '结果挑选', 60)
        time.sleep(1.5)
        t = body(drv)
        st, merged = B.api('/api/v1/tasks?page=1&per_page=100&merged=true', token)
        mdata = merged.get('data') or {}
        stats = mdata.get('stats') or {}
        check('挑选合并页签：统计与 merged 接口一致（总数/整任务/结果挑选）',
              ('合并容器 %s' % stats.get('total')) in t and ('结果挑选 %s' % stats.get('picked')) in t,
              {'ui_text': re.findall(r'合并容器 \d+|整任务合并 \d+|结果挑选 \d+', t), 'api': stats})
        shot(drv, 'A07_cherry_picks')

        # 只看收藏
        B.goto(drv, '/tasks/daily', timeout=90)
        wait_text(drv, '任务名称', 60)
        js_click_text(drv, '只看收藏')
        time.sleep(2.5)
        t = body(drv)
        st, fav = B.api('/api/v1/tasks?page=1&per_page=10&favorite=true', token)
        fdata = fav.get('data') or {}
        ui_fav = list_total(drv)
        check('日常页签：只看收藏 开关生效（UI total 与 favorite=true 列表一致，0 条时显示空态）',
              ui_fav == fdata.get('total'), {'ui': ui_fav, 'api': fdata.get('total'), 'api_stats': fdata.get('stats'), 'text': t[-200:]})
        shot(drv, 'A08_favorite')
        js_click_text(drv, '只看收藏')
        time.sleep(1)

        # ---------------- 2. 任务创建（UI 向导）+ algorithm_type 落库 ----------------
        # 选全局算法 → 小艺语音大模型
        try:
            trig = drv.find_element(By.CSS_SELECTOR, '[aria-label="切换全局算法"]')
            drv.execute_script('arguments[0].click()', trig)
            time.sleep(1.2)
            ok_algo = drv.execute_script('''
              const pop = document.querySelector('[data-slot=popover-content]');
              if (!pop) return false;
              for (const el of pop.querySelectorAll('*')) {
                if (el.children.length === 0 && (el.textContent||'').trim() === '小艺语音大模型') { el.click(); return true; }
              }
              return false;
            ''')
            time.sleep(1.5)
        except Exception as exc:
            ok_algo = 'ERR ' + str(exc)
        algo_text = body(drv)
        check('全局算法切换为「小艺语音大模型」（供 algorithm_type 落库验证）', ok_algo is True, {'ok_algo': ok_algo})

        B.goto(drv, '/start-test', timeout=90)
        time.sleep(3)
        cbox = None
        for _ in range(20):
            els = drv.find_elements(By.XPATH, "//input[@placeholder='搜索用例名称或描述']")
            if els:
                cbox = els[0]
                break
            drv.execute_script("""
              for (const b of document.querySelectorAll('button')) {
                const t=(b.textContent||'').replace(/\s+/g,' ').trim();
                if (t.startsWith('1') && t.includes('选择测试用例')) { b.click(); return true; }
              }
              return false;
            """)
            time.sleep(1)
        if cbox is None:
            raise RuntimeError('step0 not ready: ' + body(drv)[-400:])
        B.set_input(drv, cbox, 'matrix_case_1793352275')
        time.sleep(3)
        picked_case = False
        for attempt in range(15):
            state = drv.execute_script("""
              const name='matrix_case_1793352275';
              for (const el of document.querySelectorAll('*')) {
                if (el.children.length === 0 && (el.textContent||'').trim() === name) {
                  let row = el;
                  for (let i=0;i<8 && row;i++) {
                    if (row.querySelector('[role=checkbox], input[type=checkbox]')) break;
                    row = row.parentElement;
                  }
                  if (!row) continue;
                  const span = row.querySelector('[role=checkbox]');
                  const inp = row.querySelector('input[type=checkbox]');
                  if (span && span.getAttribute('aria-checked') === 'true') return 'checked';
                  if (inp) inp.click(); else if (span) span.click();
                  return 'clicked';
                }
              }
              return 'norow';
            """)
            time.sleep(0.8)
            if state == 'checked' or '已选 1 条用例' in body(drv):
                picked_case = True
                break
            # 若点 input 未生效，改点可视 checkbox
            drv.execute_script("""
              const name='matrix_case_1793352275';
              for (const el of document.querySelectorAll('*')) {
                if (el.children.length === 0 && (el.textContent||'').trim() === name) {
                  let row = el;
                  for (let i=0;i<8 && row;i++) {
                    if (row.querySelector('[role=checkbox], input[type=checkbox]')) break;
                    row = row.parentElement;
                  }
                  if (!row) continue;
                  const span = row.querySelector('[role=checkbox]');
                  if (span) { span.click(); return true; }
                }
              }
              return false;
            """)
            time.sleep(0.8)
            if '已选 1 条用例' in body(drv):
                picked_case = True
                break
        check('步骤1 勾选 1 条用例（matrix_case_1793352275）', picked_case, {'tail': body(drv)[-240:]})
        time.sleep(1)
        js_click_text(drv, '下一步', exact=True)
        time.sleep(3)
        picked_api = drv.execute_script('''
          const cb = document.querySelector('[aria-label="选择 API matrix_http_nonstream_1793352373"]');
          if (cb) { cb.click(); return true; }
          return false;
        ''')
        time.sleep(1.5)
        sel_text = body(drv)
        check('步骤2 选中 1 个 API（已选 0 台设备 · 1 个 API）', picked_api and re.search(r'已选 0 台设备 · 1 个 API', sel_text) is not None,
              re.findall(r'已选 \d+ 台设备 · \d+ 个 API[^·]*', sel_text)[:2])
        drv.execute_script('window.__reqs = window.__reqs || []; window.__reqs.length = 0;')
        clicked_start = drv.execute_script('''
          const hits=[...document.querySelectorAll('button')].filter(b => (b.textContent||'').trim()==='开始测试' && (b.offsetWidth||b.offsetHeight) && !b.closest('aside'));
          const b = hits[hits.length-1];
          if (b) { b.click(); return true; }
          return false;
        ''')
        time.sleep(1.5)
        print('clicked_start', clicked_start, 'body_tail', body(drv)[-200:])
        name_inp = None
        for _ in range(10):
            els = drv.find_elements(By.ID, 'task-name')
            if els:
                name_inp = els[0]
                break
            drv.execute_script("""
              const hits=[...document.querySelectorAll('button')].filter(b => (b.textContent||'').trim()==='开始测试' && (b.offsetWidth||b.offsetHeight) && !b.closest('aside'));
              const b = hits[hits.length-1];
              b && b.click();
            """)
            time.sleep(1)
        if name_inp is None:
            print('LAUNCH DIALOG MISSING body_tail:', body(drv)[-800:])
            raise RuntimeError('task-name dialog not opened')
        check('步骤2「开始测试」打开任务名称弹窗', True, {})
        B.set_input(drv, name_inp, NAME)
        time.sleep(0.8)
        drv.execute_script('''
          const dlg = document.querySelector("[data-slot='dialog-content']");
          const b = [...dlg.querySelectorAll('button')].find(x => (x.textContent||'').trim() === '开始测试');
          b && b.click();
        ''')
        # 等 nav step=2
        for _ in range(40):
            time.sleep(0.5)
            if 'step=2' in drv.current_url:
                break
        check('启动成功自动跳到执行步（/start-test?step=2），不再直接跳结果步',
              'step=2' in drv.current_url, drv.current_url)

        reqs = drv.execute_script('return (window.__reqs||[]).filter(r=>r.method==="POST" && /\\/tasks$/.test(r.url)).slice(-1)')
        body_req = {}
        if reqs:
            try:
                body_req = json.loads(reqs[0].get('body') or '{}')
            except Exception:
                body_req = {}
        CTX['create_body'] = body_req
        check('POST /tasks 请求体：algorithm_type=voice_llm（真实算法类型码）',
              body_req.get('algorithm_type') == 'voice_llm', {'algorithm_type': body_req.get('algorithm_type')})
        check('POST /tasks 请求体：已无 test_type / execution_mode / serial_first 废弃字段',
              not any(k in body_req for k in ('test_type', 'execution_mode', 'serial_first')),
              {'keys': list(body_req.keys())})

        st, found = B.api('/api/v1/tasks?page=1&per_page=10&search=' + urllib.parse.quote(NAME), token)
        items = (found.get('data') or {}).get('items') or []
        tid = items[0]['id'] if items else None
        CTX['created_task'] = tid
        check('新任务以「接线测试_」前缀落库并可检索', tid is not None, {'tid': tid, 'name': NAME})

        if tid:
            st, td = B.api('/api/v1/tasks/%d' % tid, token)
            d = td.get('data') or {}
            check('GET /tasks/:id 回读：无 test_type 字段', 'test_type' not in d, {'keys': [k for k in d.keys() if 'type' in k]})
            check('GET /tasks/:id 回读：algorithm_type 非空且与算法选项一致（voice_llm）',
                  d.get('algorithm_type') == 'voice_llm', {'algorithm_type': d.get('algorithm_type')})
            check('GET /tasks/:id 回读：用例数=1 且已落 case_devices（device_types=http_api）',
                  d.get('total_cases') == 1 and d.get('device_types') == ['http_api'],
                  {'total_cases': d.get('total_cases'), 'device_types': d.get('device_types')})

        # ---------------- 5. 实时日志 WS 增量 + 通知 ----------------
        # 装 toast 观察器（sonner 弹窗短暂出现，MutationObserver 记录文案去重）
        drv.execute_script("""
          window.__toasts = window.__toasts || [];
          window.__toastSeen = window.__toastSeen || [];
          if (!window.__toastObs) {
            window.__toastObs = new MutationObserver(() => {
              for (const t of document.querySelectorAll('[data-sonner-toast]')) {
                const s = (t.textContent || '').trim();
                if (s && window.__toastSeen.indexOf(s) < 0) { window.__toastSeen.push(s); window.__toasts.push(s); }
              }
            });
            window.__toastObs.observe(document.body, {childList: true, subtree: true});
          }
        """)
        samples = []
        start = time.time()
        status = None
        LOG_JS = r"""
          const nodes = [...document.querySelectorAll('div,span,h3,h4')];
          const title = nodes.map(e => (e.textContent||'').trim()).find(t => /^实时日志\s*\d+/.test(t));
          let n = -1;
          if (title) { const m = title.match(/^实时日志\s*(\d+)/); n = m ? parseInt(m[1], 10) : -1; }
          const toasts = [...document.querySelectorAll('[data-sonner-toast]')].map(e => (e.textContent||'').trim());
          const rt = (document.body.textContent||'').includes('实时内容流');
          return {logs: n, toasts: (window.__toastSeen||[]).concat(toasts), hasCard: !!title, realtime: rt};
        """
        while time.time() - start < 150:
            info = drv.execute_script(LOG_JS) or {}
            samples.append({'t': round(time.time() - start, 1), 'logs': info.get('logs'), 'hasCard': info.get('hasCard'), 'realtime': info.get('realtime')})
            if tid:
                try:
                    st, td = B.api('/api/v1/tasks/%d' % tid, token)
                    status = (td.get('data') or {}).get('status')
                except Exception as exc:
                    print('poll skip', exc)
            if status in ('completed', 'failed', 'stopped') and len(samples) > 2:
                break
            time.sleep(1.0)
        log_counts = [x['logs'] for x in samples if x['logs'] is not None and x['logs'] >= 0]
        uniq = sorted(set(log_counts))
        CTX['log_samples'] = samples[:50]
        check('实时日志卡：任务运行中日志条数随 /ws/logs 增量增长（≥2 个不同条数）',
              len(uniq) >= 2 and uniq[-1] > uniq[0], {'counts': uniq[:12], 'samples': samples[:10], 'status': status})
        # 完成后日志条数最终稳定（记录停止时间；REST 首页/尾批 WS 可能在结束后仍有 flush）
        hist = []
        stable_since = None
        stopped_after = None
        for _ in range(24):
            info = drv.execute_script(LOG_JS) or {}
            n = info.get('logs')
            if hist and n == hist[-1]:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= 4.0:
                    stopped_after = round(stable_since - start, 1)
                    break
            else:
                stable_since = None
            hist.append(n)
            time.sleep(1.0)
        check('实时日志卡：任务结束后日志不再增长（最终稳定）',
              stopped_after is not None, {'history': hist, 'stopped_after_s': stopped_after, 'status': status})
        dup = drv.execute_script("""
          const nodes = [...document.querySelectorAll('div')].filter(e => (e.className||'').toString().includes('font-mono') && e.children.length===0);
          const seen = new Set(); let dups = 0;
          for (const n of nodes) { const t=(n.textContent||'').trim(); if (!t) continue; if (seen.has(t)) dups++; else seen.add(t); }
          return {total: nodes.length, dups};
        """)
        check('实时日志卡：WS 增量与 REST 合并后无重复行（可见行文本去重）',
              (dup or {}).get('dups', 0) == 0, dup)
        rt_seen = any(x.get('realtime') for x in samples)
        check('实时内容流面板：被测 API 为 http（非 websocket）时任务运行中不渲染',
              not rt_seen, {'realtime_seen': rt_seen, 'device_types': ['http_api']})
        CTX['toasts'] = drv.execute_script('return window.__toastSeen || []') or []
        shot(drv, 'A09_executing_step')

        # ---------------- 7. 通知：角标 / 面板按 key 合并 / toast 静默 ----------------
        badge = drv.execute_script("""
          const b = document.querySelector('[aria-label="通知"]');
          if (!b) return null;
          const badge = b.querySelector('[data-slot=badge]');
          return badge ? (badge.textContent||'').trim() : null;
        """)
        bell = drv.find_element(By.CSS_SELECTOR, '[aria-label="通知"]')
        drv.execute_script('arguments[0].click()', bell)
        time.sleep(2)
        panel = drv.execute_script("""
          const pop = document.querySelector('[data-slot=popover-content]');
          if (!pop) return null;
          const rows = [...pop.querySelectorAll('div.flex.items-start.gap-3')].map(r => {
            const spans = [...r.querySelectorAll('span')].map(x => (x.textContent||'').trim()).filter(Boolean);
            const p = r.querySelector('p');
            return {title: spans[0] || '', content: p ? (p.textContent||'').trim() : ''};
          });
          return {text: (pop.textContent||'').trim().slice(0, 1500), rows};
        """)
        rows = (panel or {}).get('rows') or []
        check('通知中心：运行任务后出现通知行（SSE task_progress/task_log 进入面板）',
              len(rows) > 0, {'badge': badge, 'rows': rows[:6], 'text': (panel or {}).get('text', '')[:300]})
        prog = [r for r in rows if r['content'].startswith('进度')]
        check('通知角标数与未读通知条数一致（badge=%s, rows=%d）' % (badge, len(rows)),
              badge is not None and badge.isdigit() and int(badge) == len(rows),
              {'badge': badge, 'rows': len(rows), 'rows_detail': rows[:6]})
        mine = [r for r in rows if r['title'] == NAME]
        check('通知中心：本任务 task_progress 高频事件按业务 key 合并为 1 行（无刷屏）',
              len(mine) == 1 and mine[0]['content'].startswith('进度'), {'mine': mine, 'all_titles': [r['title'] for r in rows]})
        keys = [(r['title'], r['content']) for r in rows]
        from collections import Counter
        rep = {k: v for k, v in Counter(keys).items() if v > 1}
        check('通知中心：同一业务 key 不出现重复行', len(rep) == 0, {'repeated': list(rep.items())[:4]})
        toasts = CTX['toasts']
        prog_toasts = [t for t in toasts if '进度' in t]
        check('toast：进度类（kind=task）静默不弹（无「进度」toast）', len(prog_toasts) == 0, {'toasts': toasts[:8]})
        err_toasts = [t for t in toasts if '[WARNING]' in t or '[ERROR]' in t]
        check('toast：错误类同 key 只弹一次（无重复错误 toast）',
              len(err_toasts) == len(set(err_toasts)), {'error_toasts': err_toasts[:5], 'all': toasts[:8]})
        shot(drv, 'A10_notification_panel')
        try:
            drv.find_element(By.TAG_NAME, 'body').send_keys('\x1b')
        except Exception:
            pass
        time.sleep(1)
        # 深色截图（通知取证之后 reload 不影响已取证据）
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
        time.sleep(6)
        shot(drv, 'A11_dark_tasks_after')
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light'); location.reload();")
        time.sleep(6)

        # ---------------- 10. 跨页刷新：新任务出现在日常列表且总数+1 ----------------
        open_daily(drv)
        st, t_daily2 = api_total('/api/v1/tasks?page=1&per_page=10&algorithm_type=voice_llm', token)
        js_click_text(drv, '查询')
        time.sleep(2)
        ui2 = list_total(drv)
        hit = NAME in body(drv)
        check('联动：新任务出现在日常列表，UI total 与 /tasks total 同步',
              hit and ui2 == t_daily2, {'hit': hit, 'ui': ui2, 'api': t_daily2, 'delta': (t_daily2 or 0) - (t_daily or 0)})
        shot(drv, 'A12_daily_after_create')

        CTX['headers_end'] = header_snapshot(drv)
        check('基线未漂移：index/lib-react 构建哈希开工=收工', CTX['headers_start'] == CTX['headers_end'],
              {'start': CTX['headers_start'], 'end': CTX['headers_end']})
    finally:
        drv.quit()
        # 清理：软删 + purge 自建任务
        tid = CTX.get('created_task')
        if tid:
            st1, r1 = B.api('/api/v1/tasks/%d' % tid, token, method='DELETE')
            st2, r2 = B.api('/api/v1/tasks/%d/purge' % tid, token, method='DELETE')
            print('CLEANUP', tid, st1, st2)
            CTX['cleanup'] = {'delete': st1, 'purge': st2}
        for _ in range(20):
            st, d = B.api('/api/v1/tasks?page=1&per_page=10&search=' + urllib.parse.quote(NAME), token)
            if ((d.get('data') or {}).get('total') or 0) == 0:
                break
            time.sleep(1)
        print('CLEANUP REMAIN', B.api('/api/v1/tasks?page=1&per_page=10&search=' + urllib.parse.quote(NAME), token)[1].get('data', {}).get('total'))

    failed = [r for r in RESULTS if not r['ok']]
    print('\n==== A: %d checks, %d failed ====' % (len(RESULTS), len(failed)))
    with open(os.path.join(ART, 'evidence_A.json'), 'w', encoding='utf-8') as f:
        json.dump({'checks': RESULTS, 'ctx': {k: v for k, v in CTX.items() if k != 'log_samples'},
                   'samples': CTX.get('log_samples', [])}, f, ensure_ascii=False, indent=1)
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'][:200])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
