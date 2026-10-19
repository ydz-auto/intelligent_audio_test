# -*- coding: utf-8 -*-
"""INT-951 独立补充验证：fresh driver 重走 /report/2 用例详情弹窗。
与交付脚本不同：完整 dump 弹窗文本(UTF-8)、全量 console 日志分级、Network 真实请求清单、
断言 rounds(json) 不触发时间轴 + 无重复 key / TimelineComparison 错误。
"""
import json, os, sys, time, winreg
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:5300'
REPORT_ID = '2'
CASE_NAME = '测试用例_2026144019.wav_153241'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int951_independent_verify.txt')

def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        major = 0
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for v, exe in cands if v and v[0] == major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)

def _inject(drv):
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': r'''
window.__iatpMockAuth = { user_id: 'demo_admin', username: 'demo_admin', permissions: ['*'] };
window.__iatpNet = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = (typeof input === 'string' ? input : (input && input.url) || '') || '';
  if (url.indexOf('/auth/me') !== -1) {
    return Promise.resolve(new Response(JSON.stringify(window.__iatpMockAuth), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  }
  if (url.indexOf('/auth/mode') !== -1) {
    return Promise.resolve(new Response(JSON.stringify({ auth_mode: 'off' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  }
  return __origFetch.apply(this, arguments).then(function(res) {
    try { window.__iatpNet.push(url + ' -> ' + res.status); } catch (e) {}
    return res;
  });
};
''', })

def main():
    drv = _driver()
    lines = []
    try:
        _inject(drv)
        drv.get(BASE + '/report/' + REPORT_ID)
        WebDriverWait(drv, 30).until(lambda d: CASE_NAME in d.find_element(By.TAG_NAME, 'body').text or '具体用例对比' in d.find_element(By.TAG_NAME, 'body').text)
        time.sleep(2)
        btns = drv.find_elements(By.XPATH, "//button[contains(., '详情')]")
        target = None
        for b in btns:
            if b.text.strip() == '详情':
                target = b; break
        if target is None and btns:
            target = btns[0]
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
        time.sleep(0.5)
        target.click()
        WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        time.sleep(2)
        dialog_text = drv.execute_script(
            "const d=document.querySelector('[data-slot=dialog-content]'); return d ? d.innerText : 'NO DIALOG'")
        lines.append('=== DIALOG TEXT (light) ===')
        lines.append(dialog_text)
        lines.append('')
        lines.append('=== console logs (light) ===')
        for entry in drv.get_log('browser'):
            lines.append(entry.get('level') + ': ' + (entry.get('message') or '')[:500])
        lines.append('')
        lines.append('=== network observed via fetch patch ===')
        for u in drv.execute_script("return (window.__iatpNet || []).slice()"):
            lines.append(u)
        lines.append('')
        # 断言
        assert '时间轴对比' not in dialog_text, 'FAIL: 时间轴对比 still rendered'
        assert CASE_NAME in dialog_text, 'FAIL: case name missing from dialog'
        assert '执行结果' in dialog_text, 'FAIL: 执行结果 missing from dialog'
        severe = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
        dup = [e for e in severe if 'same key' in e.get('message','') or 'unique "key" prop' in e.get('message','') or 'TimelineComparison' in e.get('message','')]
        lines.append('SEVERE total: %d, dup/timeline severe: %d' % (len(severe), len(dup)))
        lines.append('断言: 时间轴对比 absent / real data present / no dup-key SEVERE => %s' % ('PASS' if (not dup and '时间轴对比' not in dialog_text) else 'FAIL'))
        # 深色
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'dark'); document.documentElement.classList.add('dark');")
        drv.get('about:blank'); time.sleep(1)
        drv.get(BASE + '/report/' + REPORT_ID)
        WebDriverWait(drv, 30).until(lambda d: CASE_NAME in d.find_element(By.TAG_NAME, 'body').text)
        time.sleep(2)
        btns = drv.find_elements(By.XPATH, "//button[contains(., '详情')]")
        target = None
        for b in btns:
            if b.text.strip() == '详情':
                target = b; break
        if target is None and btns:
            target = btns[0]
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
        time.sleep(0.5)
        target.click()
        WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        time.sleep(1.5)
        dtext2 = drv.execute_script("const d=document.querySelector('[data-slot=dialog-content]'); return d ? d.innerText : 'NO DIALOG'")
        severe2 = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
        dup2 = [e for e in severe2 if 'same key' in e.get('message','') or 'unique "key" prop' in e.get('message','') or 'TimelineComparison' in e.get('message','')]
        lines.append('=== DIALOG TEXT (dark) hasTimeline=%s dupSevere=%d ===' % ('时间轴对比' in dtext2, len(dup2)))
        lines.append('断言(深色): %s' % ('PASS' if ('时间轴对比' not in dtext2 and not dup2) else 'FAIL'))
    finally:
        drv.quit()
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('wrote', OUT)
    print('\n'.join(lines[:20]))

if __name__ == '__main__':
    main()
