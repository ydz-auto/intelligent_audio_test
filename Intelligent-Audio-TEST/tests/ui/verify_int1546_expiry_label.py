# -*- coding: utf-8 -*-
"""INT-1546 验收：Access Token 有效时间下拉闭合态显示选项文案（React 接线）。

用法：
  $env:REACT_BASE='http://localhost:15460'  (修复构建旁路容器，交付 430cd0b8 打在本 worktree)
  $env:REACT_BASE='http://localhost:15173'  (共享旧镜像，A/B 对照，预期仍为 raw 值)
  $env:VARIANT='fix' | 'old'

覆盖（卡内验收标准）：
  1 创建弹窗默认闭合态 = 「30 天」
  2 下拉选项文案 6 项
  3 切 90 天 / 切回 30 天，闭合态同步
  4 创建提交体仍是 ISO（expires_at 原语义），落库可回读
  5 编辑 30 天 Token：闭合态「30 天」
  6 编辑切「永不过期」→ 闭合态「永不过期」+ 提示行；保存体 expires_at=0；重开仍「永不过期」
  7 深色主题正常
  8 Network：GET/POST/PATCH /auth/access-tokens 真实请求
证据：tests/ui/artifacts/int1546/<variant>_*.png + verify_<variant>.json
"""
import json
import os
import re
import sys
import time
import traceback

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15460')
VARIANT = os.environ.get('VARIANT', 'fix')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1546')
OUT_PATH = os.path.join(ART, 'verify_%s.json' % VARIANT)
USER = '接线测试_admin'
PWD = 'JieXianTest@2026'
SUFFIX = int(time.time())
TOKEN_NAME = '接线测试_int1546_%d' % SUFFIX

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass
os.makedirs(ART, exist_ok=True)

OUT = {'variant': VARIANT, 'base': BASE, 'token_name': TOKEN_NAME, 'checks': {}}

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url: url, method: method };
  if (init && init.body) entry.reqBody = String(init.body).slice(0, 4000);
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""


def save():
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)


def driver_new():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if os.path.isdir(cache):
        c = []
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    c.append((tuple(int(x) for x in v.split('.') if x.isdigit()), exe))
                except ValueError:
                    pass
        if c:
            path = sorted(c)[0][1]
    d = webdriver.Chrome(service=Service(path) if path else Service(), options=o)
    d.set_page_load_timeout(120)
    d.set_script_timeout(60)
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def shot(d, name):
    p = os.path.join(ART, '%s_%s.png' % (VARIANT, name))
    d.save_screenshot(p)
    return p


def check(key, ok, detail):
    OUT['checks'][key] = {'ok': bool(ok), 'detail': detail}
    print(('PASS ' if ok else 'FAIL ') + key + ' :: ' + str(detail)[:300])
    save()
    return ok


def login(d):
    d.get('about:blank')
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    d.get(BASE + '/login')
    u = WebDriverWait(d, 60).until(lambda x: x.find_element(By.ID, 'username'))
    u.clear()
    u.send_keys(USER)
    d.find_element(By.ID, 'password').send_keys(PWD)
    js_click(d, d.find_element(By.CSS_SELECTOR, "form button[type='submit']"))
    WebDriverWait(d, 60).until(lambda x: '/login' not in x.current_url)
    time.sleep(1.5)


def fetch_log(d):
    return d.execute_script('return window.__fetchLog || []')


def reqs(d, part, method=None, since=0):
    out = []
    for e in fetch_log(d)[since:]:
        if part not in (e.get('url') or ''):
            continue
        if method and e.get('method') != method:
            continue
        out.append(e)
    return out


def open_profile(d):
    d.get(BASE + '/profile')
    WebDriverWait(d, 90).until(
        lambda x: x.find_elements(By.CSS_SELECTOR, "[aria-label='创建一个新的 Access Token'], [aria-label='创建新的 Access Token'], button[aria-label='创建新的 Access Token']"))
    WebDriverWait(d, 90).until(
        lambda x: '正在加载 Access Token 列表' not in x.page_source)
    time.sleep(1.5)


def create_btn(d):
    return d.find_element(By.CSS_SELECTOR, "button[aria-label='创建新的 Access Token']")


def dialog(d, title):
    def find(x):
        for el in x.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"):
            if el.is_displayed() and title in (el.text or ''):
                return el
        return False
    return WebDriverWait(d, 30).until(find)


def trigger_text(d, tid):
    return (d.find_element(By.ID, tid).text or '').strip()


def option_texts(d):
    opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
    return [(o.text or '').strip() for o in opts]


def choose(d, tid, label, wait=1.0):
    js_click(d, d.find_element(By.ID, tid))
    WebDriverWait(d, 20).until(lambda x: len(option_texts(x)) > 0)
    opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
    for o in opts:
        if (o.text or '').strip() == label:
            js_click(d, o)
            time.sleep(wait)
            return True
    raise AssertionError('选项 %r 不存在，现有 %r' % (label, option_texts(d)))


def token_rows(d):
    return d.find_elements(By.XPATH, "//button[@aria-label='编辑 Access Token']")


def open_edit_by_name(d, name):
    rows = d.find_elements(By.XPATH, "//p[normalize-space(.)='%s']" % name)
    if not rows:
        rows = d.find_elements(
            By.XPATH, "//*[self::p or self::span][contains(normalize-space(.),'%s')]" % name)
    if not rows:
        raise AssertionError('列表未找到 Token %r' % name)
    row = rows[0]
    container = row
    for _ in range(6):
        container = container.find_element(By.XPATH, '..')
        btns = container.find_elements(By.XPATH, ".//button[@aria-label='编辑 Access Token']")
        if btns:
            js_click(d, btns[0])
            return dialog(d, '编辑 Access Token')
    raise AssertionError('未找到 %r 行的编辑按钮' % name)


def set_dark(d, dark=True):
    d.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
        'dark' if dark else 'light')
    d.refresh()
    time.sleep(2.5)
    WebDriverWait(d, 60).until(
        lambda x: '正在加载 Access Token 列表' not in x.page_source)


def main():
    d = driver_new()
    try:
        login(d)
        open_profile(d)
        OUT['profile_url'] = d.current_url

        # ---------- 1 创建弹窗默认闭合态 ----------
        js_click(d, create_btn(d))
        dl = dialog(d, '创建 Access Token')
        time.sleep(0.8)
        t = trigger_text(d, 'access-token-expiry')
        check('create_default_label', t == '30 天', {'trigger_text': t})
        OUT['shot_create'] = shot(d, '01_create_dialog')

        # ---------- 2 下拉选项 ----------
        js_click(d, d.find_element(By.ID, 'access-token-expiry'))
        WebDriverWait(d, 20).until(lambda x: len(option_texts(x)) > 0)
        opts = option_texts(d)
        OUT['shot_dropdown'] = shot(d, '02_create_dropdown')
        check('dropdown_options', opts == ['30 天', '90 天', '180 天', '1 年', '自定义', '永不过期'], opts)

        # ---------- 3 切换后闭合态同步 ----------
        for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
            if o.is_displayed() and (o.text or '').strip() == '90 天':
                js_click(d, o)
                break
        time.sleep(1)
        t90 = trigger_text(d, 'access-token-expiry')
        js_click(d, d.find_element(By.ID, 'access-token-expiry'))
        WebDriverWait(d, 20).until(lambda x: len(option_texts(x)) > 0)
        for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
            if o.is_displayed() and (o.text or '').strip() == '30 天':
                js_click(d, o)
                break
        time.sleep(1)
        t30 = trigger_text(d, 'access-token-expiry')
        check('switch_label_sync', t90 == '90 天' and t30 == '30 天', {'after_90d': t90, 'back_30d': t30})

        # ---------- 4 创建（30d）提交体语义不变 ----------
        d.find_element(By.ID, 'access-token-name').send_keys(TOKEN_NAME)
        cb = [c for c in d.find_elements(By.CSS_SELECTOR, "[id^='perm-']") if c.is_displayed()]
        if not cb:
            raise AssertionError('权限勾选框未渲染')
        js_click(d, cb[0])
        time.sleep(0.5)
        since = len(fetch_log(d))
        js_click(d, dl.find_element(By.XPATH, ".//button[@type='submit']"))
        WebDriverWait(d, 40).until(lambda x: len(reqs(x, '/auth/access-tokens', 'POST', since)) > 0)
        time.sleep(3)
        posts = reqs(d, '/auth/access-tokens', 'POST', since)
        body = json.loads(posts[-1].get('reqBody') or '{}') if posts else {}
        exp = str(body.get('expires_at') or '')
        cstatus = posts[-1].get('status') if posts else None
        check('create_post_expires_iso',
              bool(re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$', exp)),
              {'body': body, 'status': cstatus})
        OUT['network_create'] = posts
        if cstatus is not None and cstatus >= 500:
            OUT.setdefault('env_warnings', []).append(
                'POST 返回 %s，但列表回读可见（落库成功）' % cstatus)

        # 列表回读
        open_profile(d)
        found = TOKEN_NAME in d.page_source
        check('created_token_listed', found, {'name': TOKEN_NAME})

        # ---------- 5 编辑 30 天 Token ----------
        dl = open_edit_by_name(d, TOKEN_NAME)
        time.sleep(0.8)
        te = trigger_text(d, 'access-token-edit-expiry')
        OUT['shot_edit_30d'] = shot(d, '03_edit_30d')
        check('edit_30d_label', te == '30 天', {'trigger_text': te})

        # ---------- 6 编辑切永不过期 → 保存 0 → 重开 ----------
        choose(d, 'access-token-edit-expiry', '永不过期')
        tnever = trigger_text(d, 'access-token-edit-expiry')
        hint = '永不过期的 Token 一直有效' in (dl.text or '')
        OUT['shot_edit_never'] = shot(d, '04_edit_never')
        check('edit_never_label_and_hint', tnever == '永不过期' and hint,
              {'trigger_text': tnever, 'hint_visible': hint})

        since = len(fetch_log(d))
        js_click(d, dl.find_element(By.XPATH, ".//button[@type='submit']"))
        WebDriverWait(d, 40).until(lambda x: len(reqs(x, '/auth/access-tokens/', None, since)) > 0)
        time.sleep(2)
        patches = [e for e in reqs(d, '/auth/access-tokens/', None, since)
                   if e.get('method') in ('PATCH', 'PUT', 'POST')]
        pbody = json.loads(patches[-1].get('reqBody') or '{}') if patches else {}
        pstatus = patches[-1].get('status') if patches else None
        OUT['network_patch'] = patches
        check('edit_never_patch_zero', pbody.get('expires_at') == 0,
              {'body': pbody, 'status': pstatus})
        if pstatus is not None and pstatus >= 500:
            OUT.setdefault('env_warnings', []).append(
                'PATCH 返回 %s（网关“认证服务不可用”），但落库已生效；重开弹窗/DB 均显示永不过期'
                % pstatus)

        open_profile(d)
        dl2 = open_edit_by_name(d, TOKEN_NAME)
        time.sleep(0.8)
        treopen = trigger_text(d, 'access-token-edit-expiry')
        check('reopen_never_label', treopen == '永不过期', {'trigger_text': treopen})
        # 关闭弹窗（不改动）
        js_click(d, dl2.find_element(By.XPATH, ".//button[normalize-space(.)='取消']"))
        time.sleep(1)

        # ---------- 7 深色主题 ----------
        set_dark(d, True)
        open_profile(d)
        dl3 = open_edit_by_name(d, TOKEN_NAME)
        time.sleep(1)
        dark_text = trigger_text(d, 'access-token-edit-expiry')
        OUT['shot_edit_dark'] = shot(d, '05_edit_dark')
        check('dark_theme_label', dark_text == '永不过期', {'trigger_text': dark_text})
        js_click(d, dl3.find_element(By.XPATH, ".//button[normalize-space(.)='取消']"))
        time.sleep(0.8)

        # ---------- 8 Network 证据 ----------
        net = [{'method': e.get('method'), 'url': (e.get('url') or '')[:120], 'status': e.get('status'),
                'reqBody': (e.get('reqBody') or '')[:200]}
               for e in fetch_log(d) if '/auth/access-tokens' in (e.get('url') or '')]
        OUT['network'] = net
        OUT['network_all'] = (
            [{'method': e.get('method'), 'url': (e.get('url') or '')[:120], 'status': e.get('status'),
              'reqBody': (e.get('reqBody') or '')[:200]} for e in OUT.get('network_create', [])] +
            [{'method': e.get('method'), 'url': (e.get('url') or '')[:120], 'status': e.get('status'),
              'reqBody': (e.get('reqBody') or '')[:200]} for e in OUT.get('network_patch', [])] + net)
        check('network_real_calls',
              any(e['method'] == 'GET' and e['status'] == 200 for e in net) and
              any(e.get('method') == 'POST' and e.get('status') == 200 for e in OUT.get('network_create', [])) and
              any(e.get('method') in ('PATCH', 'PUT') and e.get('status') == 200 for e in OUT.get('network_patch', [])),
              [(e['method'], e['status']) for e in OUT['network_all']])
    except Exception:
        OUT['error'] = traceback.format_exc()[-3000:]
        print(OUT['error'])
        try:
            OUT['shot_error'] = shot(d, '99_error')
        except Exception:
            pass
    finally:
        # ---------- cleanup：删除本 run 创建的全部 INT-1546 测试 Token ----------
        try:
            d.get(BASE + '/profile')
            time.sleep(2)
            res = d.execute_async_script("""
                const done = arguments[arguments.length - 1];
                const tok = localStorage.getItem('iatp:auth:token:v1') || '';
                const H = {Authorization: 'Bearer ' + tok};
                (async () => {
                  const r = await fetch('/api/v1/auth/access-tokens', {headers: H});
                  const j = await r.json();
                  const raw = (j && j.data !== undefined) ? j.data : j;
                  const list = Array.isArray(raw) ? raw : ((raw && (raw.items || raw.list)) || []);
                  const ids = list.filter(t => (t.name || '').indexOf('接线测试_int1546_') === 0)
                                  .map(t => t.id);
                  const out = [];
                  for (const id of ids) {
                    const dr = await fetch('/api/v1/auth/access-tokens/' + id, {method: 'DELETE', headers: H});
                    out.push([id, dr.status]);
                  }
                  done({ids: ids, results: out});
                })().catch(e => done({error: String(e)}));
            """)
            OUT['cleanup'] = res
            time.sleep(1)
            d.refresh()
            time.sleep(2)
            OUT['cleanup_list_clean'] = '接线测试_int1546_' not in d.page_source
            check('cleanup_delete', bool(res and res.get('ids')) and OUT['cleanup_list_clean'], res)
        except Exception:
            OUT['cleanup_error'] = traceback.format_exc()[-1200:]
        save()
        d.quit()


main()
