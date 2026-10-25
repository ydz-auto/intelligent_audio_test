# -*- coding: utf-8 -*-
"""INT-1482 报告域深走查公共库：driver/登录/接口/截图/主题/网络打点。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
BACKEND = os.environ.get('REAL_BACKEND', 'http://localhost:15000')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1482')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__fetchLog = [];
window.__origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || 'GET';
  let entry = {url: url, method: method, ts: Date.now()};
  try {
    if (init && init.body) entry.reqBody = String(init.body).slice(0, 4000);
    const res = await window.__origFetch.apply(this, arguments);
    entry.status = res.status;
    const ct = res.headers.get('content-type') || '';
    if (url.indexOf('/api/v1') !== -1 && (ct.indexOf('json') !== -1)) {
      try { entry.resBody = (await res.clone().text()).slice(0, 6000); } catch (e) {}
    }
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e); entry.status = -1;
    window.__fetchLog.push(entry);
    throw e;
  }
};
window.__resetFetchLog = function(){ window.__fetchLog = []; };
"""


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.add_argument('--accept-lang=zh-CN')
    o.add_argument('--user-data-dir=' + os.path.join(os.environ.get('TEMP', '.'), 'int1482_chrome_%d' % os.getpid()))
    o.add_argument('--disable-features=Translate')
    o.add_experimental_option('prefs', {
        'download.default_directory': os.path.abspath(os.path.join(ART, 'downloads')),
        'download.prompt_for_download': False,
    })
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    if os.path.isdir(root):
        for v in os.listdir(root):
            p = os.path.join(root, v, 'chromedriver.exe')
            try:
                if os.path.isfile(p) and int(v.split('.')[0]) == major:
                    exe = p
            except ValueError:
                pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(120)
    try:
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return d


def login(d, user='接线测试_admin', pwd='JieXianTest@2026'):
    for attempt in range(3):
        d.get(BASE + '/login')
        try:
            WebDriverWait(d, 30).until(lambda x: x.find_elements(By.ID, 'username'))
        except Exception:
            continue
        u = d.find_element(By.ID, 'username')
        u.clear()
        u.send_keys(user)
        p = d.find_element(By.ID, 'password')
        p.clear()
        p.send_keys(pwd)
        try:
            d.find_element(By.XPATH, "//form//button[@type='submit']").click()
        except Exception:
            p.submit()
        try:
            WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
            time.sleep(2)
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError('登录失败 user=%s' % user)


def api(d, path, method='GET', body=None, timeout=120):
    js = """
    const path = arguments[0], method = arguments[1], body = arguments[2];
    const cb = arguments[arguments.length-1];
    const token = (window.localStorage.getItem('iatp:auth:token:v1') || '').replace(/^"|"$/g,'');
    const h = {'Content-Type':'application/json'};
    if (token) h['Authorization'] = 'Bearer ' + token;
    const init = {method: method, headers: h};
    if (body !== null) init.body = JSON.stringify(body);
    fetch('/api/v1' + path, init)
      .then(async r => cb({status: r.status, text: (await r.text()).slice(0, 200000)}))
      .catch(e => cb({status:-1, text:String(e)}));
    """
    d.set_script_timeout(timeout)
    r = d.execute_async_script(js, path, method, body)
    try:
        r['json'] = json.loads(r['text'])
    except Exception:
        r['json'] = None
    return r


def shot(d, name, theme='light'):
    path = os.path.join(ART, name + '.png')
    d.save_screenshot(path)
    return path


def set_theme(d, mode):
    # 纯字符串，不能 JSON.stringify：写成 "dark"（带引号）不在允许集合里会静默回退浅色
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', '%s')" % mode)
    d.get('about:blank')
    d.refresh() if False else None


def apply_theme(d, mode):
    """写主题 key 后整页重载（about:blank 打断 bfcache）。"""
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', '%s')" % mode)
    url = d.current_url
    d.get('about:blank')
    d.get(url)
    time.sleep(3)


def body(d):
    return d.execute_script("return document.body.textContent || ''")


def js_click(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)


def find_by_text(d, text, tag='*', root=None):
    root = root or d
    xp = ".//%s[contains(normalize-space(.), '%s')]" % (tag, text) if root is not d else \
         "//%s[contains(normalize-space(.), '%s')]" % (tag, text)
    return root.find_elements(By.XPATH, xp)


def click_text(d, text, tag='button'):
    for el in find_by_text(d, text, tag):
        try:
            if el.is_displayed():
                js_click(d, el)
                return el
        except Exception:
            pass
    raise AssertionError('找不到可点击元素: %s' % text)


def dialogs(d):
    out = []
    for dl in d.find_elements(By.CSS_SELECTOR, "[role='dialog'],[role='alertdialog']"):
        try:
            out.append({'text': dl.text, 'el': dl})
        except Exception:
            pass
    return out


def wait_dialog(d, contains='', timeout=15):
    def _f(x):
        for dl in x.find_elements(By.CSS_SELECTOR, "[role='dialog'],[role='alertdialog']"):
            try:
                if dl.is_displayed() and contains in dl.text:
                    return dl
            except Exception:
                pass
        return False
    return WebDriverWait(d, timeout).until(_f)


def close_dialog(d, how='esc'):
    if how == 'esc':
        from selenium.webdriver.common.keys import Keys
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    elif how == 'button':
        for b in d.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(@aria-label,'Close') or normalize-space(.)='关闭' or normalize-space(.)='取消']"):
            try:
                if b.is_displayed():
                    js_click(d, b)
                    break
            except Exception:
                pass
    time.sleep(0.8)


def fetch_log(d, since=0):
    try:
        return d.execute_script("return (window.__fetchLog||[]).filter(e=>e.ts>=%d);" % since)
    except Exception:
        return []


def reset_fetch_log(d):
    d.execute_script("if(window.__resetFetchLog) window.__resetFetchLog();")


def now_ms():
    return int(time.time() * 1000)
