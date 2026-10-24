# -*- coding: utf-8 -*-
"""INT-1654 验收：日志页「清除弹窗估算不随列表筛选」+「导出摘要中文标签」。

同一脚本双跑：
  MODE=fix      → 本卡交付 dist 的旁路容器（默认 15244）
  MODE=baseline → 共享 15173 旧镜像（不含本卡改动）
修复侧脚本对旧镜像应复现缺陷形态，才能把绿灯归因到本次修复。

环境：docker 真实库栈（api_gateway 15000 / 库 intelligent_audio_test），
经旁路容器 nginx 反代 api_gateway:5000。不执行真实清除。
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
from selenium.webdriver.support.ui import WebDriverWait

MODE = os.environ.get('MODE', 'fix')
BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15244')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1654', MODE)
os.makedirs(ART, exist_ok=True)

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
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p, flush=True)


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


def page_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : "";') or ''


def footer_text(drv):
    m = re.search(r'共\s*[\d,]+\s*条日志[^\n]*', page_text(drv))
    return m.group(0) if m else ''


def wait_footer(drv, n_contains, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        t = footer_text(drv)
        if t and n_contains in t:
            return t
        time.sleep(0.5)
    return footer_text(drv)


def wait_list_ready(drv, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if re.search(r'共\s*[\d,]+\s*条日志', footer_text(drv)):
            return True
        time.sleep(0.5)
    return False


def click_level_chip(drv, level):
    """级别 chip 多选：默认全选，只剩目标级别 = 点掉其余四个。"""
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    for _ in range(2):
        for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]'):
            tx = text_of(drv, b).strip()
            name = next((lv for lv in levels if tx.startswith(lv)), None)
            if not name or not b.is_displayed():
                continue
            pressed = b.get_attribute('aria-pressed') == 'true'
            if name == level and not pressed:
                js_click(drv, b)
                time.sleep(0.4)
            elif name != level and pressed:
                js_click(drv, b)
                time.sleep(0.4)
        time.sleep(1.0)
        pressed_now = [text_of(drv, b).strip()[:10] for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]')
                       if b.get_attribute('aria-pressed') == 'true' and b.is_displayed()]
        if len(pressed_now) == 1 and pressed_now[0].startswith(level):
            return True
    return False


def dialog(drv, timeout=20):
    WebDriverWait(drv, timeout).until(
        lambda d: any(x.is_displayed() for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"))
    )
    for x in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
        if x.is_displayed():
            return x
    return None


def read_dialog_text(drv):
    dlg = dialog(drv)
    return (drv.execute_script('return arguments[0].textContent || "";', dlg) or '').strip()


def wait_dialog_text_change(drv, old):
    end = time.time() + 40
    while time.time() < end:
        t = read_dialog_text(drv)
        if t != old:
            return t
        time.sleep(0.5)
    return read_dialog_text(drv)


def wait_dialog_estimate(drv, timeout=90, must_contain=None):
    """等弹窗文案里的估算数字出现（/logs/stats 全量扫描可能要数秒）。"""
    end = time.time() + timeout
    t = ''
    while time.time() < end:
        t = read_dialog_text(drv)
        if re.search(r'约\s*[\d,]+\s*条', t) and (must_contain is None or must_contain in t):
            return t
        time.sleep(1.0)
    return t


def est_number(text):
    m = re.search(r'约\s*([\d,]+)\s*条', text)
    return int(m.group(1).replace(',', '')) if m else None


def open_clear_dialog(drv):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if text_of(drv, b).strip() == '清除日志' and b.is_displayed():
            js_click(drv, b)
            break
    return wait_dialog_text_change(drv, '')


def close_dialog(drv):
    try:
        dlg = dialog(drv)
        for b in dlg.find_elements(By.TAG_NAME, 'button'):
            if text_of(drv, b).strip() == '取消':
                js_click(drv, b)
                break
    except Exception:
        pass
    time.sleep(1.2)


def set_datetime(drv, value):
    drv.execute_script(
        """
        var el = document.getElementById('log-clear-before');
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, arguments[0]);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        value,
    )


def pick_select(drv, aria_label, option_text):
    trig = drv.find_element(By.CSS_SELECTOR, "[aria-label='%s']" % aria_label)
    js_click(drv, trig)
    time.sleep(0.8)
    end = time.time() + 15
    while time.time() < end:
        for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']"):
            if o.is_displayed() and text_of(drv, o).strip() == option_text:
                js_click(drv, o)
                time.sleep(1.0)
                return True
        time.sleep(0.3)
    return False


def select_trigger_text(drv, aria_label):
    return text_of(drv, drv.find_element(By.CSS_SELECTOR, "[aria-label='%s']" % aria_label)).strip()


def summary_values(drv):
    dlg = dialog(drv)
    out = {}
    for row in dlg.find_elements(By.XPATH, ".//div[contains(@class,'flex') and contains(@class,'items-baseline')]"):
        spans = row.find_elements(By.TAG_NAME, 'span')
        if len(spans) >= 2:
            k = text_of(drv, spans[0]).strip()
            v = text_of(drv, spans[1]).strip()
            if k:
                out[k] = v
    return out


def fetch_log(drv):
    return drv.execute_script('return window.__fetchLog || []')


def set_dark(drv, dark):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", 'dark' if dark else 'light')
    drv.refresh()
    WebDriverWait(drv, 60).until(
        lambda d: ('dark' if dark else 'light') in (d.execute_script('return document.documentElement.className') or '')
    )
    time.sleep(2)


def run_light(drv):
    print('== LIGHT ==', flush=True)
    drv.get(BASE + '/logs')
    ok = wait_list_ready(drv)
    if not ok or footer_text(drv).startswith('共 0 条'):
        drv.refresh()
        time.sleep(3)
        ok = wait_list_ready(drv)
    record('list_loaded', ok, footer_text(drv))
    if not ok:
        return

    click_level_chip(drv, 'ERROR')
    now_footer = wait_footer(drv, '共 799 条日志')
    record('filter_error_footer_799', '799' in (now_footer or ''), now_footer)

    unfiltered = api_json(drv, '/api/v1/logs/stats?page=1&per_page=1')
    try:
        unfiltered_total = json.loads(unfiltered['body'])['data']['total']
    except Exception:
        unfiltered_total = None

    before_open = len(fetch_log(drv))
    open_clear_dialog(drv)
    t = wait_dialog_estimate(drv)
    est = est_number(t)
    record('clear_dialog_estimate_present', est is not None, 'est=%s text=%s' % (est, t[:160]))
    shot(drv, 'light_01_clear_dialog_filtered_error')

    if MODE == 'fix':
        record('clear_dialog_uses_unfiltered_total',
               est is not None and unfiltered_total is not None and abs(est - unfiltered_total) <= max(50, unfiltered_total * 0.005),
               'est=%s unfiltered=%s' % (est, unfiltered_total))
        record('clear_dialog_not_filtered_799', est not in (799,), 'est=%s' % est)
        record('clear_dialog_scope_all', ('全部' in t) and ('约' in t), t[:160])
        record('clear_dialog_note_independent', '与列表筛选条件无关' in t, '')
    else:
        record('clear_dialog_follows_filter(baseline)', est == 799, 'est=%s' % est)

    # 弹窗打开后新增的 stats 请求是否带列表筛选
    new_reqs = [r for r in fetch_log(drv)[before_open:] if '/logs/stats' in r.get('url', '')]
    est_req = [r for r in new_reqs if 'level=' not in r['url']]
    record('estimate_request_has_no_level_filter', bool(est_req), '; '.join(r['url'] for r in new_reqs)[:400])
    if est_req:
        try:
            body = json.loads(est_req[-1].get('resBody', '{}'))
            server_total = body.get('data', {}).get('total')
        except Exception:
            server_total = None
        record('estimate_request_total_matches_dialog',
               server_total is not None and est is not None and abs(server_total - est) <= max(50, server_total * 0.005),
               'server=%s dialog=%s' % (server_total, est))

    # 设时间点 → 估算切到该时间点之前
    set_datetime(drv, '2026-10-20T00:00')
    t2 = wait_dialog_estimate(drv, must_contain='2026-10-20 00:00 之前的')
    est2 = est_number(t2)
    shot(drv, 'light_02_clear_dialog_before_time')
    api_end = api_json(drv, '/api/v1/logs/stats?page=1&per_page=1&end_time=2026-10-20T00:00')
    try:
        end_total = json.loads(api_end['body'])['data']['total']
    except Exception:
        end_total = None
    if MODE == 'fix':
        record('clear_dialog_before_time_text', '2026-10-20 00:00' in t2 and '之前的' in t2, t2[:160])
        record('clear_dialog_before_time_estimate',
               est2 is not None and end_total is not None and abs(est2 - end_total) <= max(50, end_total * 0.005),
               'est=%s api=%s' % (est2, end_total))
    else:
        record('clear_dialog_before_time_ignored(baseline)', est2 == est, 'est2=%s est=%s' % (est2, est))

    close_dialog(drv)

    # 导出摘要
    pick_select(drv, '分类', '系统日志')
    pick_select(drv, '模块', 'API模块')
    pick_select(drv, '标记筛选', '黄色标记')
    trig = drv.find_element(By.CSS_SELECTOR, "[aria-label='算法类型']")
    js_click(drv, trig)
    time.sleep(1.0)
    algo_name = None
    algo_value = None
    for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']"):
        tx = text_of(drv, o).strip()
        if o.is_displayed() and tx and tx != '全部算法':
            algo_name = tx
            algo_value = o.get_attribute('data-value') or ''
            js_click(drv, o)
            break
    time.sleep(2.0)
    record('filters_selected', algo_name is not None,
           'cat=%s mod=%s mark=%s algo=%s(%s)' % (select_trigger_text(drv, '分类'),
                                                  select_trigger_text(drv, '模块'),
                                                  select_trigger_text(drv, '标记筛选'),
                                                  select_trigger_text(drv, '算法类型'), algo_name))

    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if text_of(drv, b).strip() == '导出日志' and b.is_displayed():
            js_click(drv, b)
            break
    wait_dialog_text_change(drv, '')
    time.sleep(1.0)
    vals = summary_values(drv)
    dtext = read_dialog_text(drv)
    shot(drv, 'light_03_export_summary')
    print('SUMMARY', json.dumps(vals, ensure_ascii=False), flush=True)
    if MODE == 'fix':
        record('summary_category_cn', vals.get('分类') == '系统日志', vals.get('分类'))
        record('summary_module_cn', vals.get('模块') == 'API模块', vals.get('模块'))
        record('summary_mark_cn', vals.get('标记') == '黄色标记', vals.get('标记'))
        record('summary_algorithm_cn', bool(algo_name) and vals.get('算法') == algo_name,
               '%s vs %s' % (vals.get('算法'), algo_name))
        raw_hits = [w for w in ('system', 'yellow', 'voice_llm') if w in dtext]
        record('summary_no_raw_enum', not raw_hits, str(raw_hits))
    else:
        record('summary_raw_enum(baseline)',
               vals.get('分类') == 'system' and vals.get('标记') == 'yellow',
               json.dumps(vals, ensure_ascii=False))
    close_dialog(drv)

    with open(os.path.join(ART, 'fetch_log_light.json'), 'w', encoding='utf-8') as f:
        json.dump(fetch_log(drv), f, ensure_ascii=False, indent=1)


def run_dark(drv):
    print('== DARK ==', flush=True)
    set_dark(drv, True)
    drv.get(BASE + '/logs')
    if not wait_list_ready(drv):
        record('dark_list_loaded', False, footer_text(drv))
        return
    record('dark_theme_applied',
           'dark' in (drv.execute_script('return document.documentElement.className') or ''), '')
    click_level_chip(drv, 'ERROR')
    wait_footer(drv, '共 799 条日志')
    open_clear_dialog(drv)
    t = wait_dialog_estimate(drv)
    est = est_number(t)
    shot(drv, 'dark_01_clear_dialog_filtered_error')
    if MODE == 'fix':
        record('dark_clear_dialog_estimate_scope', est is not None and est != 799 and '全部' in t, 'est=%s' % est)
    set_datetime(drv, '2026-10-20T00:00')
    t2 = wait_dialog_estimate(drv, must_contain='2026-10-20 00:00 之前的')
    print('DARK_BEFORE_TIME', t2[:160], flush=True)
    shot(drv, 'dark_02_clear_dialog_before_time')
    close_dialog(drv)

    pick_select(drv, '分类', '系统日志')
    pick_select(drv, '模块', 'API模块')
    pick_select(drv, '标记筛选', '黄色标记')
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if text_of(drv, b).strip() == '导出日志' and b.is_displayed():
            js_click(drv, b)
            break
    wait_dialog_text_change(drv, '')
    time.sleep(1.0)
    vals = summary_values(drv)
    dtext = read_dialog_text(drv)
    shot(drv, 'dark_03_export_summary')
    print('DARK_SUMMARY', json.dumps(vals, ensure_ascii=False), flush=True)
    if MODE == 'fix':
        record('dark_summary_cn',
               vals.get('分类') == '系统日志' and vals.get('模块') == 'API模块' and vals.get('标记') == '黄色标记',
               json.dumps(vals, ensure_ascii=False))
        raw_hits = [w for w in ('system', 'yellow') if w in dtext]
        record('dark_summary_no_raw_enum', not raw_hits, str(raw_hits))
    close_dialog(drv)


def main():
    print('MODE=%s BASE=%s' % (MODE, BASE), flush=True)
    d = make_driver()
    try:
        d.get(BASE + '/logs')
        health = api_json(d, BASE + '/health')
        print('HEALTH', health['body'][:200], flush=True)
        run_light(d)
        run_dark(d)
        errs = [e for e in d.get_log('browser') if e['level'] in ('SEVERE', 'ERROR')]
        record('no_console_severe', len(errs) == 0, json.dumps(errs[:3], ensure_ascii=False))
    finally:
        d.quit()
    passed = sum(1 for c in CHECKS if c['ok'])
    print('RESULT %s %d/%d' % (MODE, passed, len(CHECKS)), flush=True)
    with open(os.path.join(ART, 'checks.json'), 'w', encoding='utf-8') as f:
        json.dump(CHECKS, f, ensure_ascii=False, indent=1)
    return 0 if passed == len(CHECKS) else 1


if __name__ == '__main__':
    sys.exit(main())
