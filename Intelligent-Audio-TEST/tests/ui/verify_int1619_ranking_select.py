# -*- coding: utf-8 -*-
"""INT-1619 验收：/rankings 筛选行「指标」「数据来源」Select 闭合态文案。

覆盖：UI 选择 / 直链还原 / 重置 / 浅色深色 / Network / 立即计算确认窗回归。
对接 bypass 容器（本卡 dist）→ api_gateway:5000（docker 真实库栈 15000，库 intelligent_audio_test）。
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15251')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1619')
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
    try {
      entry.resBody = await res.clone().text();
    } catch (e) {}
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


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def trigger(drv, label):
    return drv.find_element(By.CSS_SELECTOR, f"[aria-label='{label}']")


def wait_filters(drv, timeout=45):
    WebDriverWait(drv, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[aria-label='指标']")) > 0
    )
    time.sleep(1)


def popup_option(drv, text, timeout=15):
    """在当前打开的 Select popup 里按可见文本找 option 并 JS click。"""
    end = time.time() + timeout
    while time.time() < end:
        opts = drv.find_elements(By.CSS_SELECTOR, "[role='option']")
        for o in opts:
            if text_of(drv, o) == text and o.is_displayed():
                js_click(drv, o)
                return True
        time.sleep(0.3)
    return False


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def set_theme(drv, mode):
    """同源设置主题后 reload（memory: about:blank 中转会丢主题）。"""
    drv.get(BASE + '/rankings')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.refresh()
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )
    time.sleep(2)


def url_search(drv):
    return drv.current_url.split('?', 1)[1] if '?' in drv.current_url else ''


def main():
    d = make_driver()
    result = {}
    try:
        # 1) UI 选择
        set_theme(d, 'light')
        d.get(BASE + '/rankings')
        wait_filters(d)
        jt0 = text_of(d, trigger(d, '指标'))
        st0 = text_of(d, trigger(d, '数据来源'))
        result['initial'] = {'metric': jt0, 'source': st0}

        js_click(d, trigger(d, '指标'))
        time.sleep(0.6)
        result['metric_option_click'] = popup_option(d, '环境理解评分')
        time.sleep(1)
        js_click(d, trigger(d, '数据来源'))
        time.sleep(0.6)
        result['source_option_click'] = popup_option(d, '平台实测')
        time.sleep(1.2)

        result['ui_selected'] = {
            'metric': text_of(d, trigger(d, '指标')),
            'source': text_of(d, trigger(d, '数据来源')),
            'url': url_search(d),
        }
        shot(d, '01_ui_selected_light')

        # 2) 重置
        reset_btn = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if text_of(d, b) in ('重置', '恢复默认', '重置筛选'):
                reset_btn = b
                break
        if reset_btn is not None:
            js_click(d, reset_btn)
            time.sleep(1.5)
            result['reset'] = {
                'metric': text_of(d, trigger(d, '指标')),
                'source': text_of(d, trigger(d, '数据来源')),
                'url': url_search(d),
            }
            shot(d, '02_reset_light')
        else:
            result['reset'] = {'error': 'reset button not found'}

        # 3) 直链还原（全新加载，light）
        d.get(BASE + '/rankings?metricCode=ENV_UNDERSTAND_SCORE&source=platform_test')
        wait_filters(d)
        time.sleep(1.5)
        result['directlink_light'] = {
            'metric': text_of(d, trigger(d, '指标')),
            'source': text_of(d, trigger(d, '数据来源')),
            'url': url_search(d),
        }
        shot(d, '03_directlink_light')

        # 4) Network：本页 ranking 请求
        logs = d.execute_script('return window.__fetchLog || []') or []
        result['ranking_requests'] = [
            {'url': e.get('url'), 'status': e.get('status'), 'len': len(e.get('resBody') or '')}
            for e in logs
            if '/benchmarks/ranking' in (e.get('url') or '')
        ]

        # 5) 交互回归：立即计算打开确认窗（不真正计算，避免重算共享库）
        compute_btn = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            tx = text_of(d, b)
            if '立即计算' in tx:
                compute_btn = b
                break
        if compute_btn is not None:
            js_click(d, compute_btn)
            time.sleep(1.2)
            body = d.execute_script('return document.body.textContent || ""')
            result['compute_dialog'] = {
                'opened': '重新计算排行' in body,
                'has_cancel': any('取消' in text_of(d, b) for b in d.find_elements(By.TAG_NAME, 'button')),
            }
            shot(d, '05_compute_confirm_light')
            for b in d.find_elements(By.TAG_NAME, 'button'):
                if '取消' in text_of(d, b):
                    js_click(d, b)
                    break
            time.sleep(0.8)
        else:
            result['compute_dialog'] = {'error': 'compute button not found'}

        # 6) UI 选中态深色
        set_theme(d, 'dark')
        d.get(BASE + '/rankings')
        wait_filters(d)
        js_click(d, trigger(d, '指标'))
        time.sleep(0.6)
        popup_option(d, '环境理解评分')
        time.sleep(1)
        js_click(d, trigger(d, '数据来源'))
        time.sleep(0.6)
        popup_option(d, '平台实测')
        time.sleep(1.2)
        result['ui_selected_dark'] = {
            'html_class': d.find_element(By.TAG_NAME, 'html').get_attribute('class'),
            'metric': text_of(d, trigger(d, '指标')),
            'source': text_of(d, trigger(d, '数据来源')),
        }
        shot(d, '06_ui_selected_dark')

        # 7) 直链深色（同源 reload）
        set_theme(d, 'dark')
        d.get(BASE + '/rankings?metricCode=ENV_UNDERSTAND_SCORE&source=platform_test')
        wait_filters(d)
        time.sleep(1.5)
        result['directlink_dark'] = {
            'html_class': d.find_element(By.TAG_NAME, 'html').get_attribute('class'),
            'metric': text_of(d, trigger(d, '指标')),
            'source': text_of(d, trigger(d, '数据来源')),
        }
        shot(d, '04_directlink_dark')

        # 8) 控制台错误
        try:
            result['browser_errors'] = [
                e for e in d.get_log('browser') if e.get('level') == 'SEVERE'
            ][:10]
        except Exception as exc:
            result['browser_errors'] = [str(exc)]
    finally:
        summary = {k: v for k, v in result.items() if k != 'browser_errors'}
        summary['browser_errors'] = result.get('browser_errors')
        print('RESULT ' + json.dumps(summary, ensure_ascii=False))
        d.quit()


if __name__ == '__main__':
    sys.exit(main())
