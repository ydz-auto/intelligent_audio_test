# -*- coding: utf-8 -*-
"""INT-951 修复验收 + 控制台 SEVERE 定位（真实 Chrome headless，连常驻后端；v2 driver 逻辑）。

验收核心（INT-951）：
1. /report/2 用例详情弹窗真实数据渲染，rounds(json) 不触发「时间轴对比」
2. 展开详情（inline）同样无「时间轴对比」
3. TimelineComparison 相关 console SEVERE 不存在（rounds 不进时间轴 → 无重复 key / NaN）
4. Network：/reports/2 与 /reports/2/cases/search 真实请求 + rounds(json) 载荷

对剩余非时间轴 console.error 做 DOM 关联 dump（定位是否为本卡范围外既有问题）。
截图落 tests/ui/artifacts/int951_report_timeline/light|dark/。
"""
import json
import os
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int951_report_timeline')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5300')
REPORT_ID = os.environ.get('REACT_REPORT_ID', '2')
CASE_NAME = '测试用例_2026144019.wav_153241'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def _shot(drv, name, theme):
    d = os.path.join(ARTIFACTS, theme)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, name + '.png'))
    print('saved', theme, name)


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _inject(drv):
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': r'''
window.__iatpMockAuth = { user_id: 'demo_admin', username: 'demo_admin', permissions: ['*'] };
window.__iatpNet = { casesSearch: null };
window.__iatpErrors = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = (typeof input === 'string' ? input : (input && input.url) || '') || '';
  if (url.indexOf('/auth/me') !== -1) {
    return Promise.resolve(new Response(JSON.stringify(window.__iatpMockAuth), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  if (url.indexOf('/auth/mode') !== -1) {
    return Promise.resolve(new Response(JSON.stringify({ auth_mode: 'off' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  if (url.indexOf('/cases/search') !== -1) {
    return __origFetch.apply(this, arguments).then(function(res) {
      try {
        res.clone().json().then(function(j) { window.__iatpNet.casesSearch = j; }).catch(function() {});
      } catch (e) {}
      return res;
    });
  }
  return __origFetch.apply(this, arguments);
};
const __origConsoleError = console.error;
console.error = function() {
  const parts = [];
  for (let i = 0; i < arguments.length; i++) {
    const a = arguments[i];
    let s;
    try { s = typeof a === 'string' ? a : JSON.stringify(a); } catch (e) { s = String(a); }
    parts.push(s.slice(0, 300));
  }
  window.__iatpErrors.push(parts.join(' ||| '));
  return __origConsoleError.apply(console, arguments);
};
'''})


def _login(drv):
    drv.get(BASE + '/login')
    time.sleep(1.5)
    btns = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if btns:
        btns[0].click()
        time.sleep(2.5)
    if '/login' in drv.current_url:
        drv.get(BASE + '/report/' + REPORT_ID)
        time.sleep(2)


def _open_report(drv):
    drv.get(BASE + '/report/' + REPORT_ID)
    WebDriverWait(drv, 30).until(lambda d: CASE_NAME in _body(d) or '具体用例对比' in _body(d))
    time.sleep(2)


def _open_detail_dialog(drv):
    WebDriverWait(drv, 20).until(lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '详情')]")) > 0)
    btns = drv.find_elements(By.XPATH, "//button[contains(., '详情')]")
    target = None
    for b in btns:
        if b.text.strip() == '详情':
            target = b
            break
    if target is None:
        target = btns[0]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
    time.sleep(0.5)
    target.click()
    WebDriverWait(drv, 15).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']") and ('执行结果' in _body(d)))
    time.sleep(1.5)


def _dialog_dom_info(drv):
    return drv.execute_script(
        "const d = document.querySelector('[data-slot=dialog-content]');"
        "if (!d) return 'NO DIALOG';"
        "const lists = [];"
        "for (const tag of ['tr','li','button']) {"
        "  const els = d.querySelectorAll(tag);"
        "  if (els.length > 1) {"
        "    const sample = Array.from(els).slice(0, 6).map(e => (e.textContent||'').trim().slice(0,30));"
        "    lists.push(tag + ':' + els.length + '=' + JSON.stringify(sample));"
        "  }"
        "}"
        "return {hasTimeline: d.textContent.includes('时间轴对比'), lists: lists};")


def _rounds_payload(drv):
    return drv.execute_script(
        "const d = window.__iatpNet && window.__iatpNet.casesSearch;"
        "if (!d) return null;"
        "const item = d && d.data && d.data.items && d.data.items[0];"
        "const algos = (item && (item.algorithmResults || item.algorithm_results)) || [];"
        "const r = algos.find(function(x){ return (x.param_code || x.paramCode) === 'rounds'; });"
        "return r ? { param_type: r.param_type || r.paramType, value_is_array: Array.isArray(r.value) } : null;")


def _collect_timeline_severe(drv):
    """收集重复 key / TimelineComparison 相关 SEVERE（INT-951 验收口径：rounds 不进时间轴 + 弹窗无重复 key）。"""
    out = []
    for entry in drv.get_log('browser'):
        if entry.get('level') != 'SEVERE':
            continue
        msg = entry.get('message', '')
        if 'same key' in msg or 'unique "key" prop' in msg or 'TimelineComparison' in msg:
            out.append(msg[:300])
    return out


def main():
    drv = _driver()
    try:
        _inject(drv)
        # ---- 浅色 ----
        _login(drv)
        _open_report(drv)
        _open_detail_dialog(drv)
        body = _body(drv)
        print('DIALOG hasTimeline block:', '时间轴对比' in body)
        assert CASE_NAME in body and '执行结果' in body, '弹窗未渲染真实数据'
        assert '时间轴对比' not in body, 'rounds(json) 仍误渲染「时间轴对比」'
        tl_severe = _collect_timeline_severe(drv)
        print('TimelineComparison SEVERE count:', len(tl_severe))
        assert not tl_severe, 'TimelineComparison SEVERE 残留: ' + '; '.join(tl_severe)[:500]
        # 控制台误差 dump（定位来源）
        errs = drv.execute_script("return (window.__iatpErrors || []).slice()")
        print('dialog console.error count:', len(errs))
        for e in errs:
            print('   ERR:', e[:280])
        print('DIALOG DOM:', _dialog_dom_info(drv))
        _shot(drv, '01_case_detail_dialog_light', 'light')
        # Network + rounds 载荷
        rounds_payload = _rounds_payload(drv)
        print('rounds payload:', rounds_payload)
        assert rounds_payload and rounds_payload.get('param_type') == 'json', 'cases/search 未见 rounds(json) 载荷'
        # 关弹窗后再展开详情 inline
        for b in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-close']"):
            try:
                b.click()
                break
            except Exception:
                continue
        time.sleep(1)
        btns = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='展开详情']")
        if not btns:
            btns = drv.find_elements(By.XPATH, "//button[contains(., '展开详情')]")
        if btns:
            drv.execute_script("arguments[0].scrollIntoView({block:'center'})", btns[0])
            time.sleep(0.4)
            btns[0].click()
            time.sleep(1.5)
            body = _body(drv)
            assert '时间轴对比' not in body, '展开详情仍误渲染「时间轴对比」'
            _shot(drv, '02_case_expanded_light', 'light')
        # ---- 深色 ----
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'dark');"
                           "document.documentElement.classList.add('dark');")
        drv.get('about:blank')
        time.sleep(1)
        _open_report(drv)
        _open_detail_dialog(drv)
        body = _body(drv)
        assert '时间轴对比' not in body, '深色下「时间轴对比」仍误渲染'
        assert not _collect_timeline_severe(drv), '深色 TimelineComparison SEVERE 残留'
        _shot(drv, '03_case_detail_dialog_dark', 'dark')
        print('INT-951 验收断言全部通过')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
