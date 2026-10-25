# -*- coding: utf-8 -*-
"""INT-1945 验收：文件日志行标记假成功。

同一脚本双跑（A/B）：
  MODE=fix      → 本卡交付 dist 的旁路容器（默认 15245）
  MODE=baseline → 共享 15173 旧镜像（不含本卡改动），应复现「文件日志行有标记入口 +
                  选中后 toast 日志已标记但不落库」的缺陷形态

环境：docker 真实库栈（api_gateway 15000 / 库 intelligent_audio_test），
旁路容器 nginx 反代 api_gateway:5000。文件日志本就不落库，历史库行使用本 run 自建夹具
（content 前缀「接线测试_INT1945_」，run 结束前删除，脚本不写库）。

用法：
  MODE=fix FIXTURE_ID=<历史库行 id> python verify_int1945_logs_mark.py   # 含历史行/混合
  MODE=fix python verify_int1945_logs_mark.py                            # 仅文件日志场景
  MODE=baseline python verify_int1945_logs_mark.py
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

MODE = os.environ.get('MODE', 'fix')
DEFAULT_BASE = 'http://127.0.0.1:15245' if MODE == 'fix' else 'http://127.0.0.1:15173'
BASE = os.environ.get('REACT_BASE', DEFAULT_BASE)
FIXTURE_ID = int(os.environ['FIXTURE_ID']) if os.environ.get('FIXTURE_ID') else None
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1945', MODE)
os.makedirs(ART, exist_ok=True)

FLOOR = 10 ** 12

FETCH_PATCH = r"""
window.__fetchLog = [];
window.__fetchStart = Date.now();
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  let body = '';
  try { body = (init2.body && typeof init2.body === 'string') ? init2.body : ''; } catch (e) {}
  let res, err;
  try {
    res = await __origFetch.apply(this, arguments);
  } catch (e) {
    window.__fetchLog.push({url: url, method: method, status: -1, error: String(e), body: body, t: Date.now()});
    throw e;
  }
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
    line = '%s %s %s' % ('PASS' if ok else 'FAIL', name, detail)
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode('ascii', 'replace').decode('ascii'), flush=True)


def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1400')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
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
    """优先真实点击（base-ui 菜单按钮要 pointer 事件），不可点时退回 JS click。"""
    try:
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click();', el)


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p, flush=True)


def page_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : "";') or ''


def footer_text(drv):
    m = re.search(r'共\s*[\d,]+\s*条日志[^\n]*', page_text(drv))
    return m.group(0) if m else ''


def wait_list_ready(drv, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if re.search(r'共\s*[\d,]+\s*条日志', footer_text(drv)):
            return True
        time.sleep(0.5)
    return False


def row_ids(drv):
    return [int(a.split(' ')[-1]) for a in drv.execute_script(
        "return Array.from(document.querySelectorAll('[aria-label^=\"选择日志 \"]')).map(e => e.getAttribute('aria-label'));"
    ) or []]


def mark_entry_ids(drv):
    return [int(a.split(' ')[-1]) for a in drv.execute_script(
        "return Array.from(document.querySelectorAll('[aria-label^=\"标记日志 \"]')).map(e => e.getAttribute('aria-label'));"
    ) or []]


def row_text_by_id(drv, log_id):
    xp = "//tr[.//*[@aria-label='选择日志 %d']]" % log_id
    for tr in drv.find_elements(By.XPATH, xp):
        if tr.is_displayed():
            return text_of(drv, tr)
    return ''


def select_all(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[aria-label='全选当前页']")
    vis = [e for e in els if e.is_displayed()]
    if not vis:
        return False
    js_click(drv, vis[0])
    return True


def click_row_checkbox(drv, log_id):
    els = drv.find_elements(By.CSS_SELECTOR, "[aria-label='选择日志 %d']" % log_id)
    vis = [e for e in els if e.is_displayed()]
    if not vis:
        return False
    js_click(drv, vis[0])
    return True


def find_menu_item(drv, text):
    xp = "//*[@role='menuitem'][contains(normalize-space(.),'%s')]" % text
    for el in drv.find_elements(By.XPATH, xp):
        if el.is_displayed():
            return el
    return None


def find_clickable_by_text(drv, text, tag='*'):
    """取最内层可见命中元素，避免点到包裹容器。"""
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


def toast_texts(drv):
    return drv.execute_script("""
      return Array.from(document.querySelectorAll('[data-sonner-toast]')).map(function(t){
        return {text: t.innerText || '', type: t.getAttribute('data-type') || ''};
      });
    """) or []


def clear_toasts(drv):
    drv.execute_script("""
      document.querySelectorAll('[data-sonner-toast]').forEach(function(t){
        var b = t.querySelector('[data-close-button]');
        if (b) b.click();
      });
    """)


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


def fetch_log(drv):
    return drv.execute_script('return window.__fetchLog || [];') or []


def mark_requests(drv):
    return [r for r in fetch_log(drv) if r.get('method') == 'PUT' and '/api/v1/logs/mark' in r.get('url', '')]


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


def set_theme(drv, theme):
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)


def wait_rows(drv, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if row_ids(drv):
            return True
        time.sleep(0.5)
    return False


def open_logs(drv, theme='light'):
    drv.get(BASE + '/')
    set_theme(drv, theme)
    drv.get(BASE + '/logs')
    ok = wait_list_ready(drv, 150)
    time.sleep(1.0)
    if not wait_rows(drv, 60):
        print('ROWS empty after load, reload once; footer=%s' % footer_text(drv), flush=True)
        drv.get(BASE + '/logs')
        wait_list_ready(drv, 120)
        wait_rows(drv, 60)
    return ok


def body_is_blank_or_error(drv):
    t = page_text(drv)
    return (not t.strip()) or ('页面' in t and '出错' in t) or ('Something went wrong' in t)


def close_popover(drv):
    drv.execute_script("document.body.click();")
    time.sleep(0.5)


# ───────────────────────────── 场景 ─────────────────────────────

def scenario_file_rows(drv):
    """P1：默认页是文件日志行，行内不得有标记入口。"""
    ids = row_ids(drv)
    file_ids = [i for i in ids if i >= FLOOR]
    marks = mark_entry_ids(drv)
    record('P1 当前页有文件日志行', len(file_ids) > 0, 'rows=%d file=%d' % (len(ids), len(file_ids)))
    record('P1 文件日志行无标记入口', not (set(file_ids) & set(marks)),
           'mark_entries=%d 文件行命中=%d' % (len(marks), len(set(file_ids) & set(marks))))
    return ids, file_ids


def scenario_bulk_all_file(drv):
    """P2：全选当前页（全是文件日志）→ 无标记入口，只给说明，不发 PUT。"""
    all_file = all(i >= FLOOR for i in row_ids(drv))
    if not all_file:
        record('P2 跳过：当前页含历史库行（夹具），纯文件页场景见无夹具轮次', True, '')
        return ''
    before = len(mark_requests(drv))
    ok = select_all(drv)
    time.sleep(1.2)
    txt = page_text(drv)
    m = re.search(r'已选择\s*(\d+)\s*条日志', txt)
    record('P2 全选后浮条计数出现', bool(m), m.group(0) if m else '')
    has_mark_btn = find_clickable_by_text(drv, '标记颜色', 'button') is not None
    record('P2 全是文件日志时无「标记颜色」入口', not has_mark_btn, 'has_mark_btn=%s' % has_mark_btn)
    record('P2 说明文案「所选为文件日志，不支持标记」', '所选为文件日志，不支持标记' in txt, '')
    time.sleep(1.5)
    after = len(mark_requests(drv))
    record('P2 不发送 PUT /logs/mark', after == before, 'PUT 数 %d → %d' % (before, after))
    shot(drv, 'p2_bulk_all_file_%s' % MODE)
    return m.group(1) if m else ''


def scenario_file_row_mark_fake_success(drv, file_ids):
    """旧实现缺陷形态：文件行标记 → toast 成功但 updated=0、行内无徽标。"""
    if not file_ids:
        record('P0 有文件行列可点标记', False, 'no file ids')
        return
    tid = file_ids[0]
    btn = drv.find_elements(By.CSS_SELECTOR, "[aria-label='标记日志 %d']" % tid)
    if not btn:
        record('P0 旧实现：文件日志行有标记入口', False, '未见 标记日志 %d' % tid)
        return
    record('P0 旧实现：文件日志行有标记入口（缺陷复现）', True, 'id=%d' % tid)
    js_click(drv, btn[0])
    time.sleep(0.8)
    color = find_clickable_by_text(drv, '黄色', 'button')
    if not color:
        record('P0 标记弹层出现', False, '')
        return
    js_click(drv, color)
    t = wait_toast(drv, '日志已标记', 20)
    record('P0 旧实现：toast「日志已标记」（假成功）', bool(t and '日志已标记' in t['text']), json.dumps(t, ensure_ascii=False))
    reqs = mark_requests(drv)
    last = reqs[-1] if reqs else None
    record('P0 旧实现：PUT /logs/mark 返回 200 但无落库', bool(last and last.get('status') == 200 and ('不支持标记' in (last.get('resBody') or '') or '"updated":0' in (last.get('resBody') or ''))),
           (last or {}).get('resBody', '')[:200])
    row_txt = ''
    for tr in drv.find_elements(By.CSS_SELECTOR, 'table tbody tr'):
        if text_of(drv, tr).find(str(tid)) != -1:
            row_txt = text_of(drv, tr)
            break
    record('P0 旧实现：行内无标记徽标', 'yellow' not in row_txt, row_txt[:120])
    shot(drv, 'p0_file_row_fake_success_%s' % MODE)


def scenario_legacy_row_mark(drv):
    """P3：历史库行（本 run 夹具）标记照常成功 + 行内徽标。"""
    btn = drv.find_elements(By.CSS_SELECTOR, "[aria-label='标记日志 %d']" % FIXTURE_ID)
    vis = [b for b in btn if b.is_displayed()]
    record('P3 历史库行有标记入口', bool(vis), 'fixture=%d' % FIXTURE_ID)
    if not vis:
        return
    clear_toasts(drv)
    js_click(drv, vis[0])
    time.sleep(0.8)
    color = find_clickable_by_text(drv, '红色', 'button')
    if not color:
        record('P3 标记弹层出现', False, '')
        return
    js_click(drv, color)
    t = wait_toast(drv, '日志已标记', 25)
    record('P3 历史库行 toast「日志已标记」', bool(t and '日志已标记' in t['text']), json.dumps(t, ensure_ascii=False))
    time.sleep(1.5)
    row_txt = row_text_by_id(drv, FIXTURE_ID)
    record('P3 历史库行行内出现 red 徽标', 'red' in row_txt, row_txt[:120])
    resp = api_json(drv, '/api/v1/logs?page=1&per_page=50&mark=red&start_time=2026-01-01T00:00')
    hit = False
    try:
        data = json.loads(resp['body'])['data']
        hit = any(int(i['id']) == FIXTURE_ID for i in data['items'])
    except Exception:
        pass
    record('P3 GET /logs?mark=red 回读到夹具', hit, resp.get('body', '')[:160])
    shot(drv, 'p3_legacy_row_mark_%s' % MODE)


def scenario_mixed_batch(drv, file_ids):
    """P4：历史行 + 文件行混合批量 → warning 分档 + 文件行不落库。"""
    if not FIXTURE_ID or not file_ids:
        return
    clear_toasts(drv)
    ok1 = click_row_checkbox(drv, FIXTURE_ID)
    ok2 = click_row_checkbox(drv, file_ids[0])
    time.sleep(1.2)
    record('P4 混合勾选成功', ok1 and ok2, 'fixture=%s file=%s' % (ok1, ok2))
    btn = find_clickable_by_text(drv, '标记颜色', 'button')
    record('P4 混合勾选仍有「标记颜色」入口', btn is not None, '')
    if not btn:
        return
    before = len(mark_requests(drv))
    js_click(drv, btn)
    time.sleep(1.0)
    record('P4 标记颜色菜单可打开（无整页崩溃）', not body_is_blank_or_error(drv), page_text(drv)[:60].replace('\n', ' '))
    color = find_menu_item(drv, '黄色')
    if not color:
        record('P4 菜单出现颜色项', False, '')
        return
    js_click(drv, color)
    t = wait_toast(drv, '文件日志', 25)
    record('P4 混合批次 warning「已标记 1 条；1 条为文件日志，不支持标记」',
           bool(t and '已标记' in t['text'] and '文件日志' in t['text']), json.dumps(t, ensure_ascii=False))
    time.sleep(1.0)
    reqs = mark_requests(drv)
    sent = reqs[before:] if len(reqs) > before else []
    last = sent[-1] if sent else None
    body_ids = []
    if last:
        try:
            body_ids = json.loads(last['body']).get('log_ids', [])
        except Exception:
            pass
    record('P4 PUT body 含夹具与文件行两条', FIXTURE_ID in body_ids and any(int(x) >= FLOOR for x in body_ids),
           json.dumps(body_ids)[:160])
    resp = api_json(drv, '/api/v1/logs?page=1&per_page=50&mark=yellow&start_time=2026-01-01T00:00')
    hit = False
    try:
        data = json.loads(resp['body'])['data']
        hit = any(int(i['id']) == FIXTURE_ID for i in data['items'])
    except Exception:
        pass
    record('P4 夹具落库为 yellow', hit, resp.get('body', '')[:120])
    shot(drv, 'p4_mixed_batch_%s' % MODE)


def main():
    print('MODE=%s BASE=%s FIXTURE=%s' % (MODE, BASE, FIXTURE_ID), flush=True)
    d = make_driver()
    result = {'mode': MODE, 'base': BASE, 'fixture': FIXTURE_ID, 'checks': CHECKS}
    try:
        health = api_json(d, BASE + '/health')
        print('HEALTH', health.get('body', '')[:160], flush=True)

        ok = open_logs(d, 'light')
        record('列表加载（页脚「共 N 条日志」）', ok, footer_text(d))
        ids, file_ids = scenario_file_rows(d)
        shot(d, 'p1_light_list_%s' % MODE)

        if MODE == 'baseline':
            scenario_file_row_mark_fake_success(d, file_ids)
            d.get(BASE + '/logs')
            wait_list_ready(d, 120)
            time.sleep(1.0)
            before = len(mark_requests(d))
            select_all(d)
            time.sleep(1.0)
            btn = find_clickable_by_text(d, '标记颜色', 'button')
            record('P0 旧实现：全选文件日志出现「标记颜色」入口', btn is not None, '')
            if btn:
                js_click(d, btn)
                time.sleep(1.5)
                crashed = body_is_blank_or_error(d)
                record('P0 旧实现：菜单打开整页崩溃', crashed, page_text(d)[:80].replace('\n', ' '))
                shot(d, 'p0_bulk_menu_crash_%s' % MODE)
            open_logs(d, 'dark')
            time.sleep(1.0)
            shot(d, 'p5_dark_list_%s' % MODE)
            return result

        scenario_bulk_all_file(d)
        open_logs(d, 'dark')
        if not row_ids(d):
            print('DARK retry: rows empty', flush=True)
            time.sleep(3)
            d.get(BASE + '/logs')
            wait_list_ready(d, 120)
            time.sleep(1.5)
        ids_d, file_ids_d = scenario_file_rows(d)
        shot(d, 'p5_dark_list_%s' % MODE)
        if all(i >= FLOOR for i in row_ids(d)):
            select_all(d)
            time.sleep(1.0)
            record('P6 深色全选文件日志：无「标记颜色」入口', find_clickable_by_text(d, '标记颜色', 'button') is None,
                   '')
        else:
            record('P6 跳过：当前页含历史库行（夹具），纯文件深色场景见无夹具轮次', True, '')
        shot(d, 'p6_dark_bulk_all_file_%s' % MODE)

        if FIXTURE_ID:
            open_logs(d, 'light')
            # 夹具时间=now，默认排序应在首页；找不到就用时间窗过滤
            if FIXTURE_ID not in row_ids(d):
                d.get(BASE + '/logs?start_time=2026-10-01T00:00')
                time.sleep(3)
                record('夹具行出现在列表（默认页）', FIXTURE_ID in row_ids(d), 'rows=%d' % len(row_ids(d)))
            scenario_legacy_row_mark(d)
            file_ids_now = [i for i in row_ids(d) if i >= FLOOR]
            scenario_mixed_batch(d, file_ids_now)
            open_logs(d, 'dark')
            time.sleep(1.0)
            shot(d, 'p7_dark_after_mark_%s' % MODE)
    finally:
        with open(os.path.join(ART, 'checks_%s.json' % MODE), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        d.quit()
    failed = [c for c in CHECKS if not c['ok']]
    print('\nRESULT %s: %d checks, %d failed' % (MODE, len(CHECKS), len(failed)), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
