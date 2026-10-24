# -*- coding: utf-8 -*-
"""INT-1673 P3-2 补测：模板下载深色截图 + 成功 toast 文案 + 失败态透出后端 message。

成功：真实 GET /testcases/template/download 200 → 落 xlsx → toast「模板已下载」+ 真实文件名。
失败：页内 fetch 包装让该 URL 回 500 JSON（错误态注入），核对 toast 带后端 message。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15268')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
TAG = os.environ.get('RUN_TAG', 'fix')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1673_template', TAG)
DL = os.path.join(ART, 'downloads')
THEME_KEY = 'iatp:theme:v1:mode'

REPORT = {'tag': TAG, 'base': BASE, 'cases': [], 'screenshots': [], 'fail': []}

PATCH = r"""
window.__fetchLog = [];
window.__failTemplate = false;
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  if (window.__failTemplate && /\/testcases\/template\/download/.test(url)) {
    window.__fetchLog.push({url: url, method: method, status: 500, injected: true});
    return new Response(JSON.stringify({success: false, code: 50000, message: '模板生成失败：磁盘空间不足'}), {
      status: 500, headers: {'Content-Type': 'application/json'},
    });
  }
  const res = await __origFetch.apply(this, arguments);
  window.__fetchLog.push({url: url, method: method, status: res.status});
  return res;
};
"""


def log(m):
    print(m, flush=True)


def check(name, ok, detail=''):
    REPORT['cases'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    if not ok:
        REPORT['fail'].append({'name': name, 'detail': detail})
        log('FAIL %s | %s' % (name, detail))
    else:
        log('OK   %s | %s' % (name, detail))
    return ok


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox', '--lang=zh-CN'):
        o.add_argument(a)
    o.add_experimental_option('prefs', {
        'download.default_directory': os.path.abspath(DL),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
    })
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(root):
        for v in os.listdir(root):
            exe = os.path.join(root, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(v.split('.')[0]) == major:
                        path = exe
                except Exception:
                    pass
    drv = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    drv.set_page_load_timeout(120)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return drv


def body(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def click_text(drv, text):
    for el in drv.find_elements(By.XPATH, "//button[normalize-space(.)='%s']" % text):
        if el.is_displayed():
            drv.execute_script('arguments[0].click()', el)
            return el
    raise AssertionError('找不到按钮：%s' % text)


def toasts(drv):
    return drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-sonner-toast]')).map(function(t){return (t.textContent||'').trim();});"
    ) or []


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name)
    drv.save_screenshot(p)
    s = os.path.getsize(p)
    REPORT['screenshots'].append({'name': name, 'size': s})
    log('SHOT %s size=%d' % (name, s))
    assert s > 10_000


def open_page(drv, theme):
    drv.get(BASE + '/')
    time.sleep(1.0)
    drv.execute_script("localStorage.setItem(%r, %r)" % (THEME_KEY, theme))
    drv.get(BASE + '/testcases')
    WebDriverWait(drv, 240, 0.4).until(
        lambda d: len([b for b in d.find_elements(By.XPATH, "//*[contains(@aria-label,'批量修改')]") if b.is_displayed()]) > 0)
    time.sleep(1.5)
    if theme == 'dark':
        WebDriverWait(drv, 20).until(lambda d: 'dark' in d.execute_script('return document.documentElement.className'))


def main():
    os.makedirs(DL, exist_ok=True)
    health = json.loads(urllib.request.urlopen(API + '/health', timeout=15).read().decode())
    log('ENV: database=%s' % health.get('database'))
    assert health.get('database') == 'intelligent_audio_test'
    drv = driver()
    try:
        # --- 深色成功路径 ---
        open_page(drv, 'dark')
        for f in os.listdir(DL):
            try:
                os.remove(os.path.join(DL, f))
            except Exception:
                pass
        click_text(drv, '模板下载')
        WebDriverWait(drv, 60, 0.4).until(lambda d: any('模板已下载' in t for t in toasts(d)))
        time.sleep(1.2)
        logs = drv.execute_script('return window.__fetchLog || []')
        reqs = [r for r in logs if '/testcases/template/download' in r['url']]
        report = {'requests': reqs, 'toasts': toasts(drv)}
        check('[dark] 模板下载发真实 GET 200', bool(reqs) and reqs[-1].get('status') == 200, reqs)
        check('[dark] toast 带真实文件名（含 testcase_template_ 与 .xlsx）',
              any('testcase_template_' in t and '.xlsx' in t for t in toasts(drv)), toasts(drv))
        check('[dark] toast 不含「演示」字样', not any('演示' in t for t in toasts(drv)), toasts(drv))
        files = [f for f in os.listdir(DL) if f.lower().endswith('.xlsx')]
        size = os.path.getsize(os.path.join(DL, files[0])) if files else 0
        check('[dark] 浏览器落 xlsx 文件（非空）', bool(files) and size > 3000, {'files': files, 'size': size})
        shot(drv, 'template_dark_toast.png')
        REPORT['dark_success'] = report

        # --- 错误态：500 + 后端 message 透出 ---
        open_page(drv, 'light')
        drv.execute_script('window.__failTemplate = true; window.__fetchLog = [];')
        click_text(drv, '模板下载')
        WebDriverWait(drv, 40, 0.4).until(lambda d: any('模板下载失败' in t for t in toasts(d)))
        time.sleep(0.5)
        err_toasts = toasts(drv)
        check('[light] 失败态 toast 透出后端 message',
              any('模板下载失败' in t and '磁盘空间不足' in t for t in err_toasts), err_toasts)
        shot(drv, 'template_error_light.png')
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'report_%s.json' % TAG), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    log('FAILS: %d' % len(REPORT['fail']))
    return 1 if REPORT['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
