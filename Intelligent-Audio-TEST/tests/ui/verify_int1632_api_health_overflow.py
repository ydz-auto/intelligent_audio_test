# -*- coding: utf-8 -*-
"""INT-1632 验收：开始测试·API 连接测试结果弹窗错误态横向溢出。

覆盖：浅色 / 深色两轮量测（弹窗 clientWidth vs scrollWidth、健康分/「重新测试」/4 个 dd
右边界 vs 弹窗右边界）+ 真实请求 POST /apis/{id}/health + Network（页内 fetch 打点）。
对接本卡 dist 容器（REACT_BASE，默认 15288）→ api_gateway:5000（docker 真实库栈，库 intelligent_audio_test）。
A/B：同一脚本换 REACT_BASE=http://127.0.0.1:15173（旧镜像）应复现溢出。

用法：python tests/ui/verify_int1632_api_health_overflow.py [--tag post|old]
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15288')
API_NAME = os.environ.get('PROBE_API_NAME', '接线测试_INT1632_溢出测试_20261024')
TAG = sys.argv[1] if len(sys.argv) > 1 else 'post'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1632')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  let res, err;
  try {
    res = await __origFetch.apply(this, arguments);
  } catch (e) {
    window.__fetchLog.push({url: url, method: method, status: -1, error: String(e), t: Date.now()});
    throw e;
  }
  const entry = {url: url, method: method, status: res.status, t: Date.now()};
  if (url.indexOf('/api/v1') !== -1) {
    try { entry.resBody = await res.clone().text(); } catch (e) {}
  }
  window.__fetchLog.push(entry);
  return res;
};
"""

MEASURE_JS = r"""
const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
const dlg = dialogs.find(d => (d.textContent || '').indexOf('连接测试结果') !== -1);
if (!dlg) return {error: 'dialog not found'};
const rect = dlg.getBoundingClientRect();
const right = rect.right;
const score = dlg.querySelector('span.tabular-nums');
const scoreRight = score ? score.getBoundingClientRect().right : null;
const retest = Array.from(dlg.querySelectorAll('button')).find(b => (b.textContent || '').indexOf('重新测试') !== -1);
const retestRight = retest ? retest.getBoundingClientRect().right : null;
const dds = Array.from(dlg.querySelectorAll('dd')).map(d => {
  const r = d.getBoundingClientRect();
  const cs = getComputedStyle(d);
  return {text: (d.textContent || '').slice(0, 40), right: r.right,
          scrollW: d.scrollWidth, clientW: d.clientWidth, wordBreak: cs.wordBreak};
});
const ddsOver = dds.filter(d => d.right > right + 0.5).length;
const dts = Array.from(dlg.querySelectorAll('dt')).map(d => d.getBoundingClientRect().right);
const err = dlg.querySelector('.text-destructive');
return {
  clientWidth: dlg.clientWidth, scrollWidth: dlg.scrollWidth,
  right: right, left: rect.left, width: rect.width,
  scoreRight: scoreRight, retestRight: retestRight,
  dds: dds, ddsOver: ddsOver, dtMaxRight: dts.length ? Math.max.apply(null, dts) : null,
  errClass: err ? err.className : null,
  errScrollW: err ? err.scrollWidth : null,
  errClientW: err ? err.clientWidth : null,
  errText: err ? (err.textContent || '').slice(0, 80) : null,
  bodyText: (dlg.textContent || '').slice(0, 300)
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
    d.set_page_load_timeout(45)
    d.set_script_timeout(45)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def wait_ready(drv, timeout=60):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')


def open_probe_card_and_test(drv):
    """进入 /start-test?step=1，点探针 API 卡「连接测试」，等结果弹窗出现。"""
    drv.get(BASE + '/start-test?step=1')
    wait_ready(drv)
    btn_xpath = "//button[@aria-label='连接测试 %s']" % API_NAME
    btn = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.XPATH, btn_xpath) if d.find_elements(By.XPATH, btn_xpath) else False)
    js_click(drv, btn)
    WebDriverWait(drv, 90).until(
        lambda d: d.execute_script(
            "return Array.from(document.querySelectorAll('[role=\"dialog\"]')).some(x => (x.textContent||'').indexOf('连接测试结果')!==-1 && x.querySelectorAll('dd').length >= 4)"))


def measure(drv):
    return drv.execute_script(MEASURE_JS)


def close_dialog(drv):
    drv.execute_script(
        "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));")
    time.sleep(0.6)


def run_round(drv, mode):
    """mode: light / dark。返回量测 dict。"""
    # 先落到同源页面，localStorage 才可写（data: URL 下禁用）
    drv.get(BASE + '/start-test?step=1')
    wait_ready(drv)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
                       'dark' if mode == 'dark' else 'light')
    if mode == 'dark':
        drv.get(BASE + '/start-test?step=1')
        wait_ready(drv)
        time.sleep(0.8)
        cls = drv.execute_script('return document.documentElement.className')
        bg = drv.execute_script('return getComputedStyle(document.body).backgroundColor')
        print('[dark] html.class=%s body.bg=%s' % (cls, bg))
        assert 'dark' in (cls or ''), 'dark 主题未生效（html.class=%r）' % cls
    else:
        drv.get(BASE + '/start-test?step=1')
        wait_ready(drv)
        time.sleep(0.8)
        cls = drv.execute_script('return document.documentElement.className')
        print('[light] html.class=%s' % cls)

    open_probe_card_and_test(drv)
    time.sleep(1.0)
    m = measure(drv)
    shot = os.path.join(ART, '%s_%s.png' % (TAG, mode))
    drv.save_screenshot(shot)
    m['screenshot'] = shot
    m['mode'] = mode
    m['fetch'] = [e for e in drv.execute_script('return window.__fetchLog || []')
                  if '/health' in (e.get('url') or '')]
    close_dialog(drv)
    return m


def verdict(m):
    """逐条判定，返回 (ok, failures)。"""
    fails = []
    if m.get('error'):
        return False, ['量测失败：%s' % m['error']]
    if m['scrollWidth'] > m['clientWidth'] + 1:
        fails.append('弹窗横向溢出 scrollWidth=%s > clientWidth=%s' % (m['scrollWidth'], m['clientWidth']))
    if m['scoreRight'] is None or m['scoreRight'] > m['right'] + 0.5:
        fails.append('健康分右边界 %s 越出弹窗右边界 %s' % (m['scoreRight'], m['right']))
    if m['retestRight'] is None or m['retestRight'] > m['right'] + 0.5:
        fails.append('「重新测试」右边界 %s 越出弹窗右边界 %s' % (m['retestRight'], m['right']))
    if m['ddsOver']:
        fails.append('%s 个 dd 右边界越出弹窗右边界 %s' % (m['ddsOver'], m['right']))
    if len(m['dds']) != 4:
        fails.append('dd 行数 %s != 4' % len(m['dds']))
    if not m['fetch']:
        fails.append('未捕获 POST /apis/*/health 请求')
    else:
        bad = [e for e in m['fetch'] if e.get('status') != 200]
        if bad:
            fails.append('health 请求状态异常：%s' % [(e['url'], e['status']) for e in bad])
    return (len(fails) == 0), fails


def main():
    drv = make_driver()
    out = {'base': BASE, 'apiName': API_NAME, 'tag': TAG, 'rounds': {}}
    try:
        for mode in ('light', 'dark'):
            m = run_round(drv, mode)
            ok, fails = verdict(m)
            out['rounds'][mode] = {'measure': m, 'pass': ok, 'fails': fails}
            print('=== %s %s ===' % (TAG, mode))
            print(json.dumps(m, ensure_ascii=False, indent=1)[:2600])
            print('PASS' if ok else 'FAIL', fails)
    finally:
        drv.quit()
    p = os.path.join(ART, '%s_result.json' % TAG)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('saved', p)


if __name__ == '__main__':
    main()
