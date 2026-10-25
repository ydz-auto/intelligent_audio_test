# -*- coding: utf-8 -*-
"""INT-1945 返工复测：跨页勾选时批量标记入口按「已选集合」判定。

上一轮打回项：第 1 页勾选历史库行 → 翻到全文件日志页后，浮条误报
「所选为文件日志，不支持标记」并藏掉「标记颜色」入口（markableSelectedCount
由当前页 rows 推导）。本轮交付 675419281 改为按 selectedIds 全量判定。

实测环境：docker 真实库栈（api_gateway :15000 / 库 intelligent_audio_test），
本卡交付 dist 的旁路容器 :15246（nginx 反代 api_gateway:5000）。
历史库行夹具由调用方先插入（默认 id=6950063，content 前缀「接线测试_INT1945_」），
脚本只读列表与标记写入，不负责建/删夹具。

用法：
  python verify_int1945_crosspage.py
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15246')
FIXTURE_ID = int(os.environ.get('FIXTURE_ID', '6950063'))
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1945', 'crosspage')
os.makedirs(ART, exist_ok=True)

FLOOR = 10 ** 12

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  let body = '';
  try { body = (init2.body && typeof init2.body === 'string') ? init2.body : ''; } catch (e) {}
  const res = await __origFetch.apply(this, arguments);
  const entry = {url: url, method: method, status: res.status, body: body, t: Date.now()};
  if (url.indexOf('/api/v1/logs') !== -1) {
    try { entry.resBody = await res.clone().text(); } catch (e) {}
  }
  window.__fetchLog.push(entry);
  return res;
};
"""

CHECKS = []


def record(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print('%s %s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)


def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1400')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
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
    d.set_page_load_timeout(90)
    d.set_script_timeout(90)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def js_click(drv, el):
    try:
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click();', el)


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p, flush=True)


def page_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : "";') or ''


def row_ids(drv):
    return [int(a.split(' ')[-1]) for a in drv.execute_script(
        "return Array.from(document.querySelectorAll('[aria-label^=\"选择日志 \"]')).map(e => e.getAttribute('aria-label'));"
    ) or []]


def wait_rows(drv, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if row_ids(drv):
            return True
        time.sleep(0.5)
    return False


def wait_list_ready(drv, timeout=150):
    end = time.time() + timeout
    while time.time() < end:
        if re.search(r'共\s*[\d,]+\s*条日志', page_text(drv)):
            return True
        time.sleep(0.5)
    return False


def open_logs(drv, theme='light'):
    drv.get(BASE + '/')
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    drv.get(BASE + '/logs')
    wait_list_ready(drv, 150)
    time.sleep(1.0)
    return wait_rows(drv, 60)


def click_row_checkbox(drv, log_id):
    els = drv.find_elements(By.CSS_SELECTOR, "[aria-label='选择日志 %d']" % log_id)
    vis = [e for e in els if e.is_displayed()]
    if not vis:
        return False
    js_click(drv, vis[0])
    return True


def click_button_text(drv, text):
    for el in drv.find_elements(By.XPATH, "//button[normalize-space(.)='%s']" % text):
        if el.is_displayed() and el.is_enabled():
            js_click(drv, el)
            return True
    return False


def find_clickable_by_text(drv, text, tag='*'):
    xp = "//%s[contains(normalize-space(.),'%s')]" % (tag, text)
    hits = [el for el in drv.find_elements(By.XPATH, xp) if el.is_displayed()]
    if not hits:
        return None
    for el in hits:
        nested = drv.execute_script(
            "return Array.from(arguments[0].querySelectorAll('*')).some(function(c){return (c.textContent||'').indexOf(arguments[1]) !== -1;});",
            el, text)
        if not nested:
            return el
    return hits[-1]


def find_menu_item(drv, text):
    xp = "//*[@role='menuitem'][contains(normalize-space(.),'%s')]" % text
    for el in drv.find_elements(By.XPATH, xp):
        if el.is_displayed():
            return el
    return None


def toast_texts(drv):
    return drv.execute_script("""
      return Array.from(document.querySelectorAll('[data-sonner-toast]')).map(function(t){
        return {text: t.innerText || '', type: t.getAttribute('data-type') || ''};
      });
    """) or []


def wait_toast(drv, must_contain, timeout=25):
    end = time.time() + timeout
    last = []
    while time.time() < end:
        last = toast_texts(drv)
        for t in last:
            if must_contain in t['text']:
                return t
        time.sleep(0.3)
    return None if not last else last[-1]


def mark_requests(drv):
    return [r for r in (drv.execute_script('return window.__fetchLog || [];') or [])
            if r.get('method') == 'PUT' and '/api/v1/logs/mark' in r.get('url', '')]


def api_json(drv, path):
    return drv.execute_async_script(
        """
        var cb = arguments[arguments.length - 1];
        fetch(arguments[0], {credentials: 'include'})
          .then(function (r) { return r.text().then(function (t) { cb({status: r.status, body: t}); }); })
          .catch(function (e) { cb({status: -1, body: String(e)}); });
        """,
        path,
    )


def bar_state(drv):
    txt = page_text(drv)
    m = re.search(r'已选择\s*(\d+)\s*条日志', txt)
    return {
        'count': int(m.group(1)) if m else None,
        'has_mark_btn': find_clickable_by_text(drv, '标记颜色', 'button') is not None,
        'says_file_only': '所选为文件日志，不支持标记' in txt,
    }


def scenario_cross_page(drv, theme):
    """第 1 页选历史库行 → 下一页（全文件日志）：入口仍在、不误报。"""
    open_logs(drv, theme)
    ids = row_ids(drv)
    record('[%s] 第 1 页含历史库行夹具' % theme, FIXTURE_ID in ids, 'rows=%d head=%s' % (len(ids), ids[:3]))
    if FIXTURE_ID not in ids:
        shot(drv, 'x_page1_missing_fixture_%s' % theme)
        return
    record('[%s] 第 1 页历史库行有行内标记入口' % theme,
           bool(drv.find_elements(By.CSS_SELECTOR, "[aria-label='标记日志 %d']" % FIXTURE_ID)), '')
    ok = click_row_checkbox(drv, FIXTURE_ID)
    time.sleep(1.2)
    st1 = bar_state(drv)
    record('[%s] 勾选历史库行浮条计数=1' % theme, ok and st1['count'] == 1, json.dumps(st1, ensure_ascii=False))
    record('[%s] 第 1 页浮条有「标记颜色」且无文件日志说明' % theme,
           st1['has_mark_btn'] and not st1['says_file_only'], json.dumps(st1, ensure_ascii=False))
    shot(drv, 'x1_page1_legacy_selected_%s' % theme)

    record('[%s] 点「下一页」' % theme, click_button_text(drv, '下一页'), '')
    end = time.time() + 60
    while time.time() < end:
        cur = row_ids(drv)
        if cur and FIXTURE_ID not in cur:
            break
        time.sleep(0.5)
    ids2 = row_ids(drv)
    record('[%s] 已翻到全文件日志页' % theme,
           bool(ids2) and FIXTURE_ID not in ids2 and all(i >= FLOOR for i in ids2),
           'rows=%d head=%s' % (len(ids2), ids2[:3]))
    time.sleep(1.0)
    st2 = bar_state(drv)
    record('[%s] 翻页后浮条仍显示已选 1 条' % theme, st2['count'] == 1, json.dumps(st2, ensure_ascii=False))
    record('[%s] 翻页后仍有「标记颜色」入口（修复点）' % theme, st2['has_mark_btn'], json.dumps(st2, ensure_ascii=False))
    record('[%s] 翻页后不再误报「所选为文件日志，不支持标记」（打回项）' % theme,
           not st2['says_file_only'], json.dumps(st2, ensure_ascii=False))
    shot(drv, 'x2_page2_crosspage_bar_%s' % theme)
    return st2


def scenario_cross_page_mark(drv):
    """跨页状态下直接标记：PUT 只带历史库行，落库 + toast，随后选择清空。"""
    before = len(mark_requests(drv))
    btn = find_clickable_by_text(drv, '标记颜色', 'button')
    if not btn:
        record('跨页标记：入口存在', False, '')
        return
    js_click(drv, btn)
    time.sleep(1.0)
    color = find_menu_item(drv, '红色')
    record('跨页标记：颜色菜单可打开', color is not None, '')
    if not color:
        shot(drv, 'x3_menu_missing')
        return
    js_click(drv, color)
    t = wait_toast(drv, '日志已标记', 25)
    record('跨页标记：toast「日志已标记」', bool(t and '日志已标记' in t['text']), json.dumps(t, ensure_ascii=False))
    time.sleep(1.0)
    reqs = mark_requests(drv)
    sent = reqs[before:]
    last = sent[-1] if sent else None
    body_ids = []
    if last:
        try:
            body_ids = [int(x) for x in json.loads(last['body']).get('log_ids', [])]
        except Exception:
            pass
    record('跨页标记：PUT body 只含所选历史库行', body_ids == [FIXTURE_ID],
           'body_ids=%s resp=%s' % (json.dumps(body_ids), (last or {}).get('resBody', '')[:160]))
    resp = api_json(drv, '/api/v1/logs?page=1&per_page=50&mark=red&start_time=2026-01-01T00:00')
    hit = False
    try:
        items = json.loads(resp['body'])['data']['items']
        hit = any(int(i['id']) == FIXTURE_ID for i in items)
    except Exception:
        pass
    record('跨页标记：GET /logs?mark=red 回读到夹具（已落库）', hit, resp.get('body', '')[:160])
    shot(drv, 'x3_crosspage_mark_result')


def scenario_file_only_negative(drv):
    """回归：只选文件日志行时仍不给入口、给说明（原修复不回归）。"""
    # 跨页标记成功后选择已被清空；本页全为文件日志，直接全选
    els = [e for e in drv.find_elements(By.CSS_SELECTOR, "[aria-label='全选当前页']") if e.is_displayed()]
    if not els:
        record('回归：文件日志页全选控件存在', False, '')
        return
    js_click(drv, els[0])
    time.sleep(1.2)
    st = bar_state(drv)
    ids = row_ids(drv)
    record('回归：本页全为文件日志', bool(ids) and all(i >= FLOOR for i in ids), 'rows=%d' % len(ids))
    record('回归：只选文件日志无「标记颜色」入口', not st['has_mark_btn'], json.dumps(st, ensure_ascii=False))
    record('回归：只选文件日志给出说明文案', st['says_file_only'], json.dumps(st, ensure_ascii=False))
    shot(drv, 'x4_file_only_negative')


def main():
    print('BASE=%s FIXTURE=%d' % (BASE, FIXTURE_ID), flush=True)
    d = make_driver()
    result = {'base': BASE, 'fixture': FIXTURE_ID, 'checks': CHECKS}
    try:
        health = api_json(d, BASE + '/health')
        print('HEALTH', health.get('body', '')[:160], flush=True)

        st = scenario_cross_page(d, 'light')
        if st and st['has_mark_btn']:
            scenario_cross_page_mark(d)
            scenario_file_only_negative(d)

        # 深色：同一跨页判定
        scenario_cross_page(d, 'dark')
    finally:
        with open(os.path.join(ART, 'checks_crosspage.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        d.quit()
    failed = [c for c in CHECKS if not c['ok']]
    print('\nRESULT: %d checks, %d failed' % (len(CHECKS), len(failed)), flush=True)
    for c in failed:
        print('  FAILED:', c['name'], c['detail'][:160], flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
