# -*- coding: utf-8 -*-
"""INT-1643 用例域补测 3 共用工具（React 接线，docker 15000 后端 / 15173 前端）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1643')
os.makedirs(ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M%S')
PREFIX = '接线测试_'

FETCH_PATCH = r"""
window.__fetchLog = [];
if (!window.__origFetch) { window.__origFetch = window.fetch; }
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  let res, err;
  try {
    res = await window.__origFetch.apply(this, arguments);
  } catch (e) {
    window.__fetchLog.push({url: url, method: method, status: -1, error: String(e), t: Date.now()});
    throw e;
  }
  const entry = {url: url, method: method, status: res.status, t: Date.now()};
  if (init2.body) entry.reqBody = typeof init2.body === 'string' ? init2.body : String(init2.body);
  try {
    const ct = res.headers.get('content-type') || '';
    if (url.indexOf('/api/v1') !== -1 && ct.indexOf('json') !== -1) {
      entry.resBody = await res.clone().text();
    }
  } catch (e) {}
  window.__fetchLog.push(entry);
  return res;
};
"""


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.add_argument('--autoplay-policy=no-user-gesture-required')
    o.add_experimental_option('excludeSwitches', ['enable-logging'])
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
    d.set_page_load_timeout(60)
    d.set_script_timeout(60)
    try:
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return d


def login(drv, attempts=3):
    last = None
    for i in range(attempts):
        drv.get(BASE + '/login')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        if '/login' not in drv.current_url:
            return drv.current_url
        # AUTH_MODE=off：开放模式直接进工作台
        for b in drv.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '进入工作台':
                js_click(drv, b)
                try:
                    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
                    time.sleep(2)
                    return drv.current_url
                except Exception:
                    pass
        try:
            u = WebDriverWait(drv, 12).until(EC.presence_of_element_located((By.ID, 'username')))
        except Exception:
            last = 'no form'
            continue
        u.clear()
        u.send_keys('接线测试_admin')
        p = drv.find_element(By.ID, 'password')
        p.clear()
        p.send_keys('JieXianTest@2026')
        btn = drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '登录')]")
        js_click(drv, btn)
        try:
            WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
            time.sleep(2)
            return drv.current_url
        except Exception:
            last = 'still on login'
            time.sleep(2)
    raise RuntimeError('login failed: %s' % last)


def api(drv, path, method='GET', body=None):
    return drv.execute_async_script(
        """
        const path = arguments[0], method = arguments[1], body = arguments[2];
        const done = arguments[arguments.length-1];
        const token = localStorage.getItem('iatp:auth:token:v1');
        const opt = {method: method, headers: token ? {Authorization: 'Bearer ' + token} : {}};
        if (body !== null && body !== undefined) {
          opt.headers['Content-Type'] = 'application/json';
          opt.body = JSON.stringify(body);
        }
        fetch('/api/v1' + path, opt)
          .then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """, path, method, body)


def api_json(drv, path, method='GET', body=None):
    r = api(drv, path, method, body)
    try:
        payload = json.loads(r['body'])
    except Exception:
        payload = None
    return r['status'], payload, r['body']


def fetch_log(drv, needle=None):
    try:
        log = drv.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []
    if needle:
        log = [e for e in log if needle in (e.get('url') or '')]
    return log


def clear_fetch_log(drv):
    drv.execute_script('window.__fetchLog = []')


def body_text(drv):
    return drv.execute_script('return document.body.innerText || ""') or ''


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def apply_theme(drv, mode):
    drv.execute_script(
        """
        const v = arguments[0];
        localStorage.setItem('iatp:theme:v1:mode', JSON.stringify(v));
        document.documentElement.classList.remove('light','dark');
        document.documentElement.classList.add(v);
        document.documentElement.setAttribute('data-theme', v);
        """, mode)
    time.sleep(0.8)


def js_click(drv, el):
    drv.execute_script('arguments[0].click();', el)


def wait_toast(drv, timeout=20):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')) > 0)
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        time.sleep(0.3)
        for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]'):
            try:
                drv.execute_script('arguments[0].remove()', t)
            except Exception:
                pass
        return toasts
    except Exception:
        return []


def dialogs(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]


def wait_dialog(drv, title, timeout=20):
    def f(d):
        for e in dialogs(d):
            if title in (e.text or ''):
                return e
        return None
    return WebDriverWait(drv, timeout).until(f)


def odd(v):
    """结构化证据累加器。"""
    return v


def save_evidence(name, data):
    p = os.path.join(ART, name + '.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    print('EVIDENCE', p)
    return p
