# -*- coding: utf-8 -*-
"""INT-1642 返工复测：收藏态导出范围（代码审计 P2）+ 导出范围复位（P3-2）。

交付：agent/react-c/int-1642 @ f1ab6585e（上一轮 492fe09b4）。
前端：本卡交付树 archive → pnpm build → nginx 旁路容器 15242（--network intelligent-audio-test_default，
nginx conf 取自 iat-react-frontend），后端 docker 网关 /api → api_gateway:5000，库 intelligent_audio_test。

断言口径：
- 收藏态「按当前筛选导出」：不发 POST /testcases/ids；发 GET /testcases?…favorite=true；
  POST /testcases/export 的 ids 恰为收藏集；落盘 JSON total_count 与 id 集合一致（不得是全库）。
- 「仅导出已选」：请求体只含所选 id。
- 导出弹窗重开复位：选「仅导出已选」→ 取消 → 清空勾选 → 重开 → 回落「按当前筛选」且无禁用选中残留。
- 其余筛选（搜索）仍走 /ids，不退化成列表全量扫描。
写库纪律：只在 2 条真实用例上加收藏（per-user 关系），run 结束前 DELETE 复原并复核收藏集回到基线。
"""
import json
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = 'http://127.0.0.1:15242'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1642_rework')
DL = os.path.join(ART, 'downloads')
os.makedirs(DL, exist_ok=True)
RES = {}
REF_CASE = 'db8e4328-28d0-48a8-b3ae-9a19d7b58d45'

FETCH_PATCH = r"""
window.__fetchLog = [];
window.__stubRules = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  const hit = (window.__stubRules || []).find(function(r) {
    return (!r.method || r.method === method) && url.indexOf(r.match) !== -1;
  });
  if (hit) {
    window.__fetchLog.push({url: url, method: method, status: hit.status, stub: true,
      reqBody: typeof init2.body === 'string' ? init2.body : null,
      resBody: hit.body, t: Date.now()});
    return new Response(hit.body, {status: hit.status, headers: {'Content-Type': 'application/json'}});
  }
  let res;
  try {
    res = await __origFetch.apply(this, arguments);
  } catch (e) {
    window.__fetchLog.push({url: url, method: method, status: -1, error: String(e), t: Date.now()});
    throw e;
  }
  const entry = {url: url, method: method, status: res.status, t: Date.now(),
    reqBody: typeof init2.body === 'string' ? init2.body : null};
  if (url.indexOf('/api/v1') !== -1) {
    try { entry.resBody = await res.clone().text(); } catch (e) {}
  }
  window.__fetchLog.push(entry);
  return res;
};
"""


def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    o.add_experimental_option('prefs', {
        'download.default_directory': DL.replace('\\', '/'),
        'download.prompt_for_download': False,
        'safebrowsing.enabled': True,
    })
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        d.execute_cdp_cmd('Page.setDownloadBehavior',
                          {'behavior': 'allow', 'downloadPath': DL})
    except Exception:
        pass
    return d


def js(d, script, *args):
    return d.execute_script(script, *args)


def body_text(d):
    return js(d, 'return document.body ? (document.body.innerText || "") : "";') or ''


def wait_fn(d, fn, timeout=40, step=0.4):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(step)
    return None


def wait_body(d, sub, timeout=40):
    return bool(wait_fn(d, lambda: sub in body_text(d), timeout))


def text_of(d, el):
    try:
        return (js(d, 'return (arguments[0].innerText || arguments[0].textContent || "").trim();', el) or '')
    except Exception:
        return ''


def js_click(d, el):
    js(d, 'arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def btn_by_text(d, text, root=None):
    root = root or d
    for el in root.find_elements(By.TAG_NAME, 'button'):
        if text in text_of(d, el):
            return el
    return None


def click_btn(d, text, timeout=20):
    el = wait_fn(d, lambda: btn_by_text(d, text), timeout)
    if el is None:
        raise RuntimeError('button not found: ' + text)
    js_click(d, el)
    return True


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    print('SHOT', name)
    return p


def api(d, method, path, payload=None):
    """页内同源请求（与 UI 同一会话 / 同一 per-user 收藏身份）。"""
    res = js(d, """
      const method = arguments[0], url = arguments[1], payload = arguments[2];
      const tok = localStorage.getItem('iatp:auth:token:v1');
      const headers = {'Content-Type': 'application/json'};
      if (tok) headers['Authorization'] = 'Bearer ' + tok;
      const opt = {method: method, headers: headers};
      if (payload !== null) opt.body = JSON.stringify(payload);
      const r = await fetch(url, opt);
      const t = await r.text();
      let j = null; try { j = JSON.parse(t); } catch (e) {}
      return {status: r.status, body: j, raw: t.slice(0, 400)};
    """, method, path, payload)
    return res


def favorite_ids(d):
    r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=200&favorite=true')
    items = ((r.get('body') or {}).get('data') or {}).get('items') or []
    return [i.get('id') for i in items], items


def clear_log(d):
    js(d, 'window.__fetchLog = [];')


def clear_downloads():
    for f in os.listdir(DL):
        try:
            os.remove(os.path.join(DL, f))
        except OSError:
            pass


def fetch_log(d, match=None, method=None):
    out = []
    for e in (js(d, 'return window.__fetchLog || [];') or []):
        if match and match not in (e.get('url') or ''):
            continue
        if method and (e.get('method') or '') != method:
            continue
        out.append(e)
    return out


def newest_download(prefix, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        files = [f for f in os.listdir(DL) if not f.endswith('.crdownload') and f.startswith(prefix)]
        if files:
            files.sort(key=lambda f: os.path.getmtime(os.path.join(DL, f)))
            return os.path.join(DL, files[-1])
        time.sleep(0.5)
    return None


def card_checkboxes(d):
    return d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')


def expand_group(d, keyword, timeout=120):
    head = wait_fn(d, lambda: next(
        (e for e in d.find_elements(By.XPATH, "//div[contains(@class,'cursor-pointer')]")
         if keyword in (text_of(d, e) or '') and '条' in (text_of(d, e) or '')), None), 30)
    if head is None:
        return False
    collapsed = js(d, """const svg = arguments[0].querySelector('svg');
        return svg ? /-rotate-90/.test(svg.getAttribute('class') || '') : true;""", head)
    if collapsed:
        js_click(d, head)
    got = wait_fn(d, lambda: len(card_checkboxes(d)) > 0, timeout, 2.0)
    return bool(got)


def selected_cards(d):
    return js(d, """
      return Array.from(document.querySelectorAll('[aria-label^="选择 "]'))
        .filter(function(e){return e.getAttribute('aria-checked') === 'true';})
        .map(function(e){return e.getAttribute('aria-label');});
    """) or []


def expand_all_groups(d, timeout=90):
    """展开当前列表里所有收起的组卡（收藏筛选下组内才出卡）。"""
    n = 0
    for _ in range(12):
        heads = d.find_elements(By.XPATH, "//div[contains(@class,'cursor-pointer')]")
        pending = []
        for h in heads:
            t = text_of(d, h) or ''
            if '条' not in t:
                continue
            collapsed = js(d, """const svg = arguments[0].querySelector('svg');
                return svg ? /-rotate-90/.test(svg.getAttribute('class') || '') : false;""", h)
            if collapsed:
                pending.append(h)
        if not pending:
            break
        for h in pending:
            js_click(d, h)
            n += 1
            time.sleep(1.2)
        time.sleep(1.0)
    wait_fn(d, lambda: len(card_checkboxes(d)) > 0, timeout, 1.0)
    return n


def open_case_drawer(d, keyword):
    """按用例名关键字找卡片 → 点行内「编辑用例」打开抽屉。"""
    cb = wait_fn(d, lambda: next((c for c in card_checkboxes(d)
                                  if keyword in (c.get_attribute('aria-label') or '')), None), 40)
    if cb is None:
        return False
    card = cb.find_element(By.XPATH, "./ancestor::div[contains(@class,'bg-card')][1]")
    btn = wait_fn(d, lambda: next((b for b in card.find_elements(
        By.CSS_SELECTOR, "button[aria-label='编辑用例']")), None), 15)
    if btn is None:
        return False
    js_click(d, btn)
    return True


def open_export(d):
    click_btn(d, '导出', 20)
    ok = wait_body(d, '导出用例', 20)
    time.sleep(0.6)
    return ok


def radio_state(d):
    return js(d, """
      const ins = Array.from(document.querySelectorAll("input[name='export-range']"));
      return ins.map(function(i){
        const lab = i.closest('label') || i.parentElement;
        return {checked: i.checked, disabled: i.disabled,
                text: ((lab && lab.innerText) || '').trim()};
      });
    """)


def run_export(d, tag):
    """点「开始导出」并收集请求/文件。"""
    clear_downloads()
    clear_log(d)
    assert open_export(d), 'export dialog not open (%s)' % tag
    click_btn(d, '开始导出', 20)
    wait_fn(d, lambda: any(s in body_text(d) for s in ('已导出', '导出失败', '没有可导出的用例')), 90)
    time.sleep(1.5)
    out = {
        'export_calls': [{'url': e.get('url'), 'status': e.get('status'), 'req': e.get('reqBody')}
                         for e in fetch_log(d, '/testcases/export')],
        'ids_calls': [{'url': e.get('url'), 'status': e.get('status'), 'req': e.get('reqBody')}
                      for e in fetch_log(d, '/testcases/ids')],
        'list_calls': [{'url': e.get('url'), 'status': e.get('status')}
                       for e in fetch_log(d, 'favorite=true') if '/testcases?' in (e.get('url') or '')],
        'toast_ok': '已导出' in body_text(d),
        'toast_fail': '导出失败' in body_text(d),
    }
    f = newest_download('testcases_export_')
    out['file'] = os.path.basename(f) if f else None
    out['size'] = os.path.getsize(f) if f else 0
    out['ids_in_file'] = None
    out['total_count'] = None
    if f and f.endswith('.json'):
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
            out['total_count'] = data.get('total_count')
            out['ids_in_file'] = [c.get('id') for c in (data.get('test_cases') or [])]
        except Exception as e:
            out['parse_error'] = str(e)[:200]
    return out


def set_search(d, value):
    inp = wait_fn(d, lambda: (d.find_elements(By.CSS_SELECTOR, "[aria-label='搜索用例']") or [None])[0], 30)
    if inp is None:
        raise RuntimeError('search input not found')
    js_click(d, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    if value:
        inp.send_keys(value)
    time.sleep(2.6)


def toggle_favorite_filter(d):
    btn = wait_fn(d, lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                   if b.get_attribute('title') == '只看收藏'), None), 20)
    if btn is None:
        raise RuntimeError('favorite filter toggle not found')
    js_click(d, btn)
    time.sleep(3.0)


def login(d):
    """收藏是 per-user 关系：AUTH_MODE=off 下仍是未认证（user_id 缺失）→ 需以真实账号登录。"""
    d.get(BASE + '/login')
    u = wait_fn(d, lambda: (d.find_elements(By.ID, 'username') or [None])[0], 30)
    if u is None:
        raise RuntimeError('login input not found')
    u.clear()
    u.send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    btn = wait_fn(d, lambda: next((b for b in d.find_elements(
        By.XPATH, "//button[contains(., '登') and contains(., '录')]")), None), 20)
    if btn is None:
        btn = btn_by_text(d, '登录')
    if btn is None:
        raise RuntimeError('login button not found; body=%s' % body_text(d)[:200])
    js_click(d, btn)
    ok = wait_fn(d, lambda: '/login' not in d.current_url, 60, 1.0)
    time.sleep(2)
    return bool(ok)


def main():
    d = make_driver()
    added = []
    try:
        # ---------- 0. 登录 + 基线：收藏集（per-user） ----------
        RES['login_ok'] = login(d)
        try:
            tok = js(d, "return localStorage.getItem('iatp:auth:token:v1');")
            with open(os.path.join(ART, 'token.txt'), 'w', encoding='utf-8') as fh:
                fh.write(tok or '')
        except Exception:
            pass
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 90), 'page not loaded'
        time.sleep(3)
        base_ids, base_items = favorite_ids(d)
        RES['favorite_baseline'] = {'count': len(base_ids), 'names': [i.get('name') for i in base_items]}

        # 取 2 条非收藏的真实用例做收藏夹具
        r = {'body': None}
        for _ in range(5):
            r = api(d, 'GET', '/api/v1/testcases?page=1&per_page=20')
            items = ((r.get('body') or {}).get('data') or {}).get('items') or []
            if items:
                break
            time.sleep(6)
        items = ((r.get('body') or {}).get('data') or {}).get('items') or []
        RES['list_probe'] = {'status': r.get('status'), 'count': len(items),
                             'raw': (r.get('raw') or '')[:200]}
        targets = [i for i in items if i.get('id') not in base_ids][:2]
        assert len(targets) == 2, 'not enough real cases: %s' % len(items)
        RES['fixture_cases'] = [{'id': t['id'], 'name': t.get('name'), 'group': t.get('group_name')} for t in targets]
        for t in targets:
            rr = api(d, 'POST', '/api/v1/testcases/%s/favorite' % t['id'])
            RES.setdefault('favorite_add_status', []).append(rr.get('status'))
            if rr.get('status') in (200, 201):
                added.append(t)
        assert len(added) == 2, 'favorite add failed: %s' % RES.get('favorite_add_status')

        now_ids, now_items = favorite_ids(d)
        RES['favorite_after_add'] = {'count': len(now_ids), 'names': [i.get('name') for i in now_items]}
        expected_ids = set(now_ids)

        # ---------- A. 收藏态「按当前筛选导出」 ----------
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 90), 'reload failed'
        time.sleep(3)
        toggle_favorite_filter(d)
        # 展开含收藏用例的分组，核对界面所见
        groups = sorted({t.get('group_name') for t in targets if t.get('group_name')})
        expanded = expand_all_groups(d)
        time.sleep(1.5)
        bt = body_text(d)
        RES['favorite_view'] = {
            'groups': groups,
            'expanded': expanded,
            'visible_cards': len(card_checkboxes(d)),
            'names_visible': {t['name']: (t['name'] in bt) for t in targets},
        }
        shot(d, '01_favorite_filter_light')

        r = run_export(d, 'favorite-scope')
        RES['favorite_export'] = r
        body_ids = None
        if r['export_calls']:
            try:
                body_ids = json.loads(r['export_calls'][0]['req'] or '{}').get('ids')
            except Exception:
                body_ids = None
        RES['favorite_export']['request_ids'] = body_ids
        RES['favorite_export']['ids_match_favorite_set'] = (set(body_ids or []) == expected_ids)
        RES['favorite_export']['file_ids_match'] = (set(r.get('ids_in_file') or []) == expected_ids)
        RES['favorite_export']['no_ids_endpoint'] = (len(r['ids_calls']) == 0)
        RES['favorite_export']['list_used'] = (len(r['list_calls']) > 0)
        RES['favorite_export']['total_count_matches'] = (r.get('total_count') == len(expected_ids))
        shot(d, '02_favorite_export_done_light')

        # ---------- B. 「仅导出已选」：请求体只含所选 ----------
        cards = card_checkboxes(d)
        for c in cards:
            js_click(d, c)
        time.sleep(1.2)
        n_sel = len(selected_cards(d))
        RES['selected_count'] = n_sel
        assert open_export(d), 'export dialog not open (selected scope)'
        radio_sel = wait_fn(d, lambda: next((i for i in d.find_elements(
            By.CSS_SELECTOR, "input[name='export-range']") if not i.is_selected()), None), 15)
        assert radio_sel is not None, 'selected radio not found'
        js_click(d, radio_sel)
        time.sleep(0.8)
        RES['radio_after_choose_selected'] = radio_state(d)
        clear_downloads()
        clear_log(d)
        click_btn(d, '开始导出', 20)
        wait_fn(d, lambda: ('已导出' in body_text(d)) or ('导出失败' in body_text(d)), 120)
        time.sleep(1.5)
        sel_calls = fetch_log(d, '/testcases/export')
        sel_req = None
        if sel_calls:
            try:
                sel_req = json.loads(sel_calls[0].get('req') or '{}').get('ids')
            except Exception:
                sel_req = None
        RES['selected_export'] = {
            'calls': [{'url': c.get('url'), 'status': c.get('status')} for c in sel_calls],
            'request_ids': sel_req,
            'count_matches_selection': (len(sel_req or []) == n_sel),
            'subset_of_favorites': (set(sel_req or []).issubset(expected_ids)),
            'toast_ok': '已导出' in body_text(d),
        }
        shot(d, '03_selected_export_done_light')

        # ---------- C. 导出范围复位（P3-2 原缺陷路径） ----------
        # 保持勾选 → 开弹窗 → 选「仅导出已选」→ 取消 → 清空勾选 → 重开
        assert open_export(d), 'export dialog not open (reset prep)'
        radio_sel = wait_fn(d, lambda: next((i for i in d.find_elements(
            By.CSS_SELECTOR, "input[name='export-range']") if not i.is_selected()), None), 15)
        if radio_sel is not None:
            js_click(d, radio_sel)
        time.sleep(0.8)
        RES['reset_radio_after_select_scope'] = radio_state(d)
        click_btn(d, '取消', 15)
        time.sleep(0.8)
        for c in card_checkboxes(d):
            if c.get_attribute('aria-checked') == 'true':
                js_click(d, c)
        time.sleep(1.0)
        RES['selected_after_uncheck'] = len(selected_cards(d))
        assert open_export(d), 'export dialog not open (reset check)'
        st = radio_state(d)
        RES['reset_radio_after_reopen'] = st
        RES['reset_ok'] = (bool(st) and st[0].get('checked') is True
                           and not st[0].get('disabled'))
        shot(d, '04_export_scope_reset_light')
        click_btn(d, '取消', 15)
        time.sleep(0.6)
        # 若还有残留勾选，清掉，避免影响后续搜索导出
        for c in card_checkboxes(d):
            if c.get_attribute('aria-checked') == 'true':
                js_click(d, c)
        time.sleep(0.8)

        # ---------- D. 回归：搜索筛选仍走 `/ids`（不退化列表全量扫描） ----------
        toggle_favorite_filter(d)  # 关掉「只看收藏」
        time.sleep(2.0)
        set_search(d, 'JS172')
        time.sleep(2.0)
        r = run_export(d, 'search-scope')
        RES['search_export'] = r
        RES['search_export']['uses_ids_endpoint'] = (len(r['ids_calls']) > 0)
        RES['search_export']['no_list_scan'] = (len([
            e for e in fetch_log(d, '/testcases?') if 'per_page=200' in (e.get('url') or '')]) == 0)
        shot(d, '05_search_export_done_light')
        set_search(d, '')
        time.sleep(2.0)

        # ---------- E. 深色：收藏筛选 + 导出弹窗 ----------
        js(d, "localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.get('about:blank')
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 90), 'dark reload failed'
        time.sleep(3)
        toggle_favorite_filter(d)
        RES['dark_expanded'] = expand_all_groups(d)
        shot(d, '06_favorite_filter_dark')
        assert open_export(d), 'export dialog not open (dark)'
        RES['dark_radio_state'] = radio_state(d)
        shot(d, '07_export_dialog_dark')
        click_btn(d, '取消', 15)
        # 主题复原
        js(d, "localStorage.setItem('iatp:theme:v1:mode','light');")

        # ---------- F. 参考参数真机回读（INT-1645 已通，2026-10-24 复核 200） ----------
        RES['ref_params_probe'] = api(
            d, 'GET', '/api/v1/testcases/%s/rounds/1/ref-params' % REF_CASE)
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 90), 'reload for ref-params failed'
        time.sleep(3)
        set_search(d, 'HJ050')
        expand_all_groups(d)
        opened = open_case_drawer(d, 'HJ050')
        RES['ref_drawer_opened'] = bool(opened)
        if opened:
            assert wait_body(d, '轮次配置', 40), 'drawer not open'
            time.sleep(1.2)
            clear_log(d)
            click_btn(d, '参考参数', 20)
            time.sleep(2.5)
            bt = body_text(d)
            RES['ref_ui'] = {
                'get_calls': [{'url': e.get('url'), 'status': e.get('status'),
                               'res': (e.get('resBody') or '')[:200]}
                              for e in fetch_log(d, '/ref-params')],
                'shows_failure': '参考参数内容读取失败' in bt,
                'has_view_edit': '查看/编辑' in bt,
                'shows_real_path': 'ref_params' in bt,
                'fake_tc001': 'tc-001' in bt,
            }
            shot(d, '08_reference_step_light')

        # 读写闭环（真实 PUT → GET 回读 → 原值还原；全程记录并复核复原）
        orig = api(d, 'GET', '/api/v1/testcases/%s/rounds/1/ref-params' % REF_CASE)
        RES['ref_roundtrip'] = {'get_status': orig.get('status')}
        orig_params = ((orig.get('body') or {}).get('data') or {}).get('referenceParams')
        with open(os.path.join(ART, 'ref_original.json'), 'w', encoding='utf-8') as fh:
            json.dump(orig_params, fh, ensure_ascii=False, indent=2)
        restored = False
        try:
            assert orig_params is not None, 'original ref params empty'
            modified = json.loads(json.dumps(orig_params))
            modified[0]['value'] = str(modified[0].get('value', '')) + '__int1642_probe'
            put = api(d, 'PUT', '/api/v1/testcases/%s/rounds/1/ref-params' % REF_CASE,
                      {'referenceParams': modified})
            back = api(d, 'GET', '/api/v1/testcases/%s/rounds/1/ref-params' % REF_CASE)
            back_params = ((back.get('body') or {}).get('data') or {}).get('referenceParams')
            RES['ref_roundtrip'].update({
                'put_status': put.get('status'),
                'get_back_status': back.get('status'),
                'readback_matches_modified': (back_params == modified),
            })
        finally:
            rest = api(d, 'PUT', '/api/v1/testcases/%s/rounds/1/ref-params' % REF_CASE,
                       {'referenceParams': orig_params})
            chk = api(d, 'GET', '/api/v1/testcases/%s/rounds/1/ref-params' % REF_CASE)
            chk_params = ((chk.get('body') or {}).get('data') or {}).get('referenceParams')
            restored = (chk_params == orig_params)
            RES['ref_roundtrip'].update({'restore_status': rest.get('status'),
                                         'restored_exact': restored})
            if not restored:
                RES['ref_roundtrip']['RESTORE_FAILED_original'] = orig_params
    finally:
        # ---------- 收尾：撤收藏夹具，复核回到基线 ----------
        try:
            for t in added:
                rr = api(d, 'DELETE', '/api/v1/testcases/%s/favorite' % t['id'])
                RES.setdefault('favorite_del_status', []).append(rr.get('status'))
            ids_after, items_after = favorite_ids(d)
            RES['favorite_after_cleanup'] = {'count': len(ids_after),
                                             'names': [i.get('name') for i in items_after]}
        except Exception as e:
            RES['cleanup_error'] = str(e)[:300]
        try:
            RES['console_severe'] = [l for l in (d.get_log('browser') or [])
                                     if l.get('level') == 'SEVERE'][:8]
        except Exception:
            pass
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as fh:
            json.dump(RES, fh, ensure_ascii=False, indent=2)
    print(json.dumps(RES, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
