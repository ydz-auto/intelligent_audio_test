# -*- coding: utf-8 -*-
"""INT-1488 复走（INT-1654 修复后）：重走「清除日志弹窗」+「导出日志弹窗」。

背景：INT-1488 前端UX审计打回两项（清除弹窗估算跟随筛选 / 导出摘要原始枚举），
修复交付 `agent/react-a/int-1654` / `1901e28c9`，已合入 wiring/react（cherry-pick
`9d3e3e8ec`）。共享 15173 镜像（2026-10-23T23:07Z 构建）早于合入，故本 run 按
15173 归属口径用「wiring/react 头构建」的旁路容器（15248）验收，不动共享 15173。

后端：docker 真实库栈 15000（intelligent_audio_test）。
保留路径：不执行真实清除；导出为只读下载，验响应非空。

用法：
  python verify_int1488_int1654_rewalk.py
  REACT_BASE=http://127.0.0.1:15248 python verify_int1488_int1654_rewalk.py
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
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1488_int1654')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  let body = '';
  try { body = (init2.body && typeof init2.body === 'string') ? init2.body : ''; } catch (e) {}
  let res, err;
  try { res = await __origFetch.apply(this, arguments); }
  catch (e) {
    window.__fetchLog.push({url: url, method: method, status: -1, error: String(e), body: body, t: Date.now()});
    throw e;
  }
  const entry = {url: url, method: method, status: res.status, body: body, t: Date.now()};
  if (url.indexOf('/api/v1/logs') !== -1) {
    try {
      var txt = await res.clone().text();
      entry.resLen = txt.length;
      entry.resBody = url.indexOf('/logs/export') !== -1 ? txt.slice(0, 300) : txt;
    } catch (e) { entry.resErr = String(e); }
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
    d.set_page_load_timeout(120)
    d.set_script_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def login_if_needed(drv):
    """登录真实库账号（接线测试_admin）；已在会话内则跳过。"""
    drv.get(BASE + '/login')
    time.sleep(2)
    for _ in range(3):
        if drv.find_elements(By.ID, 'username'):
            break
        drv.get(BASE + '/login')
        time.sleep(2)
    try:
        WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.ID, 'username'))
    except Exception:
        return False
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(6)
    return True


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


def footer_count(drv):
    m = re.search(r'共\s*([\d,]+)\s*条日志', footer_text(drv))
    return int(m.group(1).replace(',', '')) if m else None


def api_total(drv, path):
    r = api_json(drv, path)
    try:
        return json.loads(r['body'])['data']['total']
    except Exception:
        return None


def wait_footer(drv, must, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        t = footer_text(drv)
        if t and must in t:
            return t
        time.sleep(0.5)
    return footer_text(drv)


def wait_list_ready(drv, timeout=150):
    end = time.time() + timeout
    while time.time() < end:
        if re.search(r'共\s*[\d,]+\s*条日志', footer_text(drv)):
            return True
        time.sleep(0.5)
    return False


def click_level_chip(drv, level):
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    for _ in range(3):
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
        on = [text_of(drv, b).strip()[:10] for b in drv.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]')
              if b.get_attribute('aria-pressed') == 'true' and b.is_displayed()]
        if len(on) == 1 and on[0].startswith(level):
            return True
    return False


def dialog(drv, timeout=25):
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


def dialog_count(drv):
    return len([x for x in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if x.is_displayed()])


def wait_dialog_gone(drv, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if dialog_count(drv) == 0:
            return True
        time.sleep(0.3)
    return dialog_count(drv) == 0


def wait_dialog_estimate(drv, timeout=150, must_contain=None):
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
    WebDriverWait(drv, 25).until(
        lambda d: any(x.is_displayed() for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"))
    )
    time.sleep(1.0)


def click_dialog_button(drv, label):
    dlg = dialog(drv)
    for b in dlg.find_elements(By.TAG_NAME, 'button'):
        if text_of(drv, b).strip() == label:
            js_click(drv, b)
            return True
    return False


def close_esc(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
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


def datetime_value(drv):
    return drv.execute_script("return document.getElementById('log-clear-before').value;")


def keep_marked_checked(drv):
    """base-ui Switch：可能是 button[role=switch] 或 input，按实际结构读 checked 态。"""
    return drv.execute_script(
        """
        var e = document.getElementById('log-clear-keep-marked');
        if (!e) return null;
        var a = e.getAttribute('aria-checked');
        if (a !== null) return a;
        if (e.tagName === 'INPUT') return String(!!e.checked);
        var sw = e.closest('[role="switch"]') || document.querySelector('[role="switch"]');
        if (sw) return sw.getAttribute('aria-checked');
        var box = e.closest('label') && e.closest('label').querySelector('input');
        return box ? String(!!box.checked) : null;
        """
    )


def pick_select(drv, aria_label, option_text):
    trig = drv.find_element(By.CSS_SELECTOR, "[aria-label='%s']" % aria_label)
    js_click(drv, trig)
    time.sleep(0.9)
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
    for row in dlg.find_elements(By.XPATH, ".//div[contains(@class,'items-baseline')]"):
        spans = row.find_elements(By.TAG_NAME, 'span')
        if len(spans) >= 2:
            k = text_of(drv, spans[0]).strip()
            v = text_of(drv, spans[1]).strip()
            if k:
                out[k] = v
    return out


def open_export_dialog(drv):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if text_of(drv, b).strip() == '导出日志' and b.is_displayed():
            js_click(drv, b)
            break
    WebDriverWait(drv, 25).until(
        lambda d: any(x.is_displayed() for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"))
    )
    time.sleep(1.0)


def fetch_log(drv):
    return drv.execute_script('return window.__fetchLog || []')


def set_dark(drv, dark):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", 'dark' if dark else 'light')
    drv.refresh()
    WebDriverWait(drv, 90).until(
        lambda d: ('dark' if dark else 'light') in (d.execute_script('return document.documentElement.className') or '')
    )
    time.sleep(2)


def approx(a, b):
    return a is not None and b is not None and abs(a - b) <= max(50, b * 0.005)


def run_light(drv):
    print('== LIGHT ==', flush=True)
    drv.get(BASE + '/logs')
    ok = wait_list_ready(drv)
    if not ok or footer_text(drv).startswith('共 0 条'):
        drv.refresh()
        time.sleep(3)
        ok = wait_list_ready(drv)
    record('light_list_loaded', ok, footer_text(drv))
    if not ok:
        return

    shot(drv, 'light_00_logs_page')
    click_level_chip(drv, 'ERROR')
    api_err = api_total(drv, '/api/v1/logs/stats?page=1&per_page=1&level=ERROR')
    wait_footer(drv, '共 ')
    err_footer = footer_count(drv)
    record('light_filter_error_footer_matches_api',
           err_footer is not None and api_err is not None and err_footer == api_err,
           'footer=%s api=%s' % (err_footer, api_err))

    unfiltered = api_json(drv, '/api/v1/logs/stats?page=1&per_page=1')
    try:
        unfiltered_total = json.loads(unfiltered['body'])['data']['total']
    except Exception:
        unfiltered_total = None
    print('UNFILTERED', unfiltered_total, flush=True)

    # ── 清除弹窗 ──
    before_open = len(fetch_log(drv))
    open_clear_dialog(drv)
    t = wait_dialog_estimate(drv)
    est, est0 = est_number(t), est_number(t)
    record('light_clear_estimate_present', est is not None, 'est=%s' % est)
    record('light_clear_estimate_matches_unfiltered', approx(est, unfiltered_total),
           'est=%s unfiltered=%s' % (est, unfiltered_total))
    record('light_clear_not_filtered_count', est != err_footer, 'est=%s filtered=%s' % (est, err_footer))
    record('light_clear_scope_all', '全部' in t, t[:120])
    record('light_clear_note_independent', '清除范围与列表筛选条件无关' in t, '')
    shot(drv, 'light_01_clear_dialog_filtered')

    reqs = [r for r in fetch_log(drv)[before_open:] if '/logs/stats' in r.get('url', '')]
    est_req = [r for r in reqs if not any(k in r['url'] for k in ('level=', 'category=', 'mark=', 'keyword=', 'algorithm_type='))]
    record('light_clear_estimate_request_unfiltered', bool(est_req),
           '; '.join(r['url'] for r in reqs)[:300])
    if est_req:
        try:
            st = json.loads(est_req[-1].get('resBody', '{}'))['data']['total']
        except Exception:
            st = None
        record('light_clear_request_total_matches_dialog', approx(st, est), 'server=%s dialog=%s' % (st, est))

    set_datetime(drv, '2026-10-20T00:00')
    t2 = wait_dialog_estimate(drv, must_contain='2026-10-20 00:00 之前的')
    est2 = est_number(t2)
    api_end = api_json(drv, '/api/v1/logs/stats?page=1&per_page=1&end_time=2026-10-20T00:00')
    try:
        end_total = json.loads(api_end['body'])['data']['total']
    except Exception:
        end_total = None
    record('light_clear_before_time_text', '2026-10-20 00:00 之前的' in t2, t2[:140])
    record('light_clear_before_time_estimate', approx(est2, end_total), 'est=%s api=%s' % (est2, end_total))
    shot(drv, 'light_02_clear_dialog_before_time')

    # 取消 → 关闭；重开复位（时间空、保留已标记开）
    clicked = click_dialog_button(drv, '取消')
    record('light_clear_cancel_closes', clicked and wait_dialog_gone(drv), '')
    open_clear_dialog(drv)
    time.sleep(2)
    record('light_clear_reopen_reset_time', datetime_value(drv) == '', 'value=%r' % datetime_value(drv))
    km_state = str(keep_marked_checked(drv)).lower()
    t3 = read_dialog_text(drv)
    record('light_clear_reopen_keep_marked_on',
           km_state in ('true', 'checked') or '保留已标记日志不受影响' in t3,
           'state=%r text=%s' % (km_state, t3[:100]))
    t3 = wait_dialog_estimate(drv)
    record('light_clear_reopen_scope_all', '全部' in t3, t3[:120])

    # 保留已标记关 → 文案切换
    try:
        drv.execute_script("document.getElementById('log-clear-keep-marked').click();")
        time.sleep(1.0)
    except Exception:
        pass
    record('light_clear_keep_marked_off_text', '含已标记日志' in read_dialog_text(drv), read_dialog_text(drv)[:100])
    shot(drv, 'light_03_clear_dialog_keep_marked_off')

    # Esc 关闭
    close_esc(drv)
    record('light_clear_esc_closes', wait_dialog_gone(drv), '')

    # ── 导出弹窗：筛选后摘要中文 ──
    pick_select(drv, '分类', '系统日志')
    pick_select(drv, '模块', 'API模块')
    pick_select(drv, '标记筛选', '黄色标记')
    trig = drv.find_element(By.CSS_SELECTOR, "[aria-label='算法类型']")
    js_click(drv, trig)
    time.sleep(1.0)
    algo_name = None
    for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']"):
        tx = text_of(drv, o).strip()
        if o.is_displayed() and tx and tx != '全部算法':
            algo_name = tx
            js_click(drv, o)
            break
    time.sleep(3)
    record('light_filters_selected', algo_name is not None,
           'cat=%s mod=%s mark=%s algo=%s' % (select_trigger_text(drv, '分类'),
                                              select_trigger_text(drv, '模块'),
                                              select_trigger_text(drv, '标记筛选'),
                                              select_trigger_text(drv, '算法类型')))

    open_export_dialog(drv)
    vals = summary_values(drv)
    dtext = read_dialog_text(drv)
    shot(drv, 'light_04_export_summary')
    print('LIGHT_SUMMARY', json.dumps(vals, ensure_ascii=False), flush=True)
    record('light_summary_category_cn', vals.get('分类') == '系统日志', vals.get('分类'))
    record('light_summary_module_cn', vals.get('模块') == 'API模块', vals.get('模块'))
    record('light_summary_mark_cn', vals.get('标记') == '黄色标记', vals.get('标记'))
    record('light_summary_algorithm_cn', bool(algo_name) and vals.get('算法') == algo_name,
           '%s vs %s' % (vals.get('算法'), algo_name))
    record('light_summary_no_raw_enum',
           not [w for w in ('system', 'yellow', 'voice_llm', 'wire_test_param') if w in dtext],
           json.dumps(vals, ensure_ascii=False))

    # 取消 / 重开：不残留
    click_dialog_button(drv, '取消')
    record('light_export_cancel_closes', wait_dialog_gone(drv), '')
    open_export_dialog(drv)
    vals2 = summary_values(drv)
    record('light_export_reopen_keeps_summary', vals2.get('分类') == '系统日志' and vals2.get('标记') == '黄色标记',
           json.dumps(vals2, ensure_ascii=False))

    # 只留级别=ERROR 再真实导出（分类/模块/标记改回全部），验证 200 + 响应非空 + 成功关闭
    pick_select(drv, '分类', '所有分类')
    pick_select(drv, '模块', '所有模块')
    pick_select(drv, '标记筛选', '所有标记')
    trig = drv.find_element(By.CSS_SELECTOR, "[aria-label='算法类型']")
    js_click(drv, trig)
    time.sleep(0.8)
    for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']"):
        if o.is_displayed() and text_of(drv, o).strip() == '全部算法':
            js_click(drv, o)
            break
    time.sleep(2)

    open_export_dialog(drv)
    before_export = len(fetch_log(drv))
    # 选 JSON 格式（响应体更大，能证明非空）
    fmt = drv.find_element(By.ID, 'log-export-format')
    js_click(drv, fmt)
    time.sleep(0.8)
    for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']"):
        if o.is_displayed() and text_of(drv, o).strip() == 'JSON':
            js_click(drv, o)
            break
    time.sleep(0.8)
    click_dialog_button(drv, '导出')
    closed = wait_dialog_gone(drv, timeout=180)
    time.sleep(1.0)
    exports = [r for r in fetch_log(drv)[before_export:] if '/logs/export' in r.get('url', '')]
    exp = exports[-1] if exports else None
    record('light_export_request_sent', exp is not None,
           (exp or {}).get('method', '') + ' ' + (exp or {}).get('url', ''))
    record('light_export_status_200', bool(exp) and exp.get('status') == 200, str((exp or {}).get('status')))
    record('light_export_body_nonempty', bool(exp) and (exp.get('resLen') or 0) > 0,
           'resLen=%s head=%r' % ((exp or {}).get('resLen'), ((exp or {}).get('resBody') or '')[:80]))
    record('light_export_dialog_closes_on_success', closed, '')
    shot(drv, 'light_05_after_export_success')

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
    shot(drv, 'dark_00_logs_page')

    click_level_chip(drv, 'ERROR')
    api_err = api_total(drv, '/api/v1/logs/stats?page=1&per_page=1&level=ERROR')
    wait_footer(drv, '共 ')
    err_footer = footer_count(drv)
    record('dark_filter_error_footer_matches_api',
           err_footer is not None and api_err is not None and err_footer == api_err,
           'footer=%s api=%s' % (err_footer, api_err))

    open_clear_dialog(drv)
    t = wait_dialog_estimate(drv)
    est = est_number(t)
    shot(drv, 'dark_01_clear_dialog_filtered')
    record('dark_clear_estimate_not_filtered', est is not None and est != err_footer,
           'est=%s filtered=%s' % (est, err_footer))
    record('dark_clear_scope_all', '全部' in t and '清除范围与列表筛选条件无关' in t, t[:120])

    set_datetime(drv, '2026-10-20T00:00')
    t2 = wait_dialog_estimate(drv, must_contain='2026-10-20 00:00 之前的')
    shot(drv, 'dark_02_clear_dialog_before_time')
    record('dark_clear_before_time_text', '2026-10-20 00:00 之前的' in t2, t2[:140])
    click_dialog_button(drv, '取消')
    wait_dialog_gone(drv)

    pick_select(drv, '分类', '系统日志')
    pick_select(drv, '模块', 'API模块')
    pick_select(drv, '标记筛选', '黄色标记')
    open_export_dialog(drv)
    vals = summary_values(drv)
    dtext = read_dialog_text(drv)
    shot(drv, 'dark_03_export_summary')
    print('DARK_SUMMARY', json.dumps(vals, ensure_ascii=False), flush=True)
    record('dark_summary_cn',
           vals.get('分类') == '系统日志' and vals.get('模块') == 'API模块' and vals.get('标记') == '黄色标记',
           json.dumps(vals, ensure_ascii=False))
    record('dark_summary_no_raw_enum',
           not [w for w in ('system', 'yellow') if w in dtext], json.dumps(vals, ensure_ascii=False))
    click_dialog_button(drv, '取消')
    wait_dialog_gone(drv)

    with open(os.path.join(ART, 'fetch_log_dark.json'), 'w', encoding='utf-8') as f:
        json.dump(fetch_log(drv), f, ensure_ascii=False, indent=1)


def main():
    print('BASE=%s' % BASE, flush=True)
    d = make_driver()
    try:
        login_ok = login_if_needed(d)
        record('login_ok', login_ok, d.current_url)
        d.get(BASE + '/logs')
        health = api_json(d, BASE + '/health')
        print('HEALTH', health['body'][:200], flush=True)
        try:
            record('health_db_real', 'intelligent_audio_test' in health['body'], health['body'][:120])
        except Exception:
            record('health_db_real', False, health['body'][:120])
        run_light(d)
        run_dark(d)
        errs = [e for e in d.get_log('browser') if e['level'] in ('SEVERE', 'ERROR')]
        record('no_console_severe', len(errs) == 0, json.dumps(errs[:3], ensure_ascii=False))
    finally:
        try:
            d.quit()
        except Exception:
            pass
    passed = sum(1 for c in CHECKS if c['ok'])
    print('RESULT %d/%d' % (passed, len(CHECKS)), flush=True)
    with open(os.path.join(ART, 'checks.json'), 'w', encoding='utf-8') as f:
        json.dump(CHECKS, f, ensure_ascii=False, indent=1)
    return 0 if passed == len(CHECKS) else 1


if __name__ == '__main__':
    sys.exit(main())
