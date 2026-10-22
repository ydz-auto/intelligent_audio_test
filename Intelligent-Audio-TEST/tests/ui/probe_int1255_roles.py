# -*- coding: utf-8 -*-
"""INT-1255 角色列表刷新探针：检查自定义角色是否在列表渲染。"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

FAKE_OPTION = r"""
const origFetch = window.fetch;
window.fetch = async (url, init) => {
  if (typeof url === 'string' && url.includes('/api/option/')) {
    return new Response(JSON.stringify({success:true, code:0, data:{}}), {status:200, headers:{'Content-Type':'application/json'}});
  }
  return origFetch(url, init);
};
"""


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
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


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def run():
    drv = _driver()
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FAKE_OPTION})
        drv.get(BASE + '/dashboard')
        WebDriverWait(drv, 30).until(lambda d: '工作台' in _body(drv))
        drv.get(BASE + '/system-settings/iam/roles')
        WebDriverWait(drv, 30).until(lambda d: '角色权限管理' in _body(drv))
        for i in range(5):
            time.sleep(2)
            body = _body(drv)
            print(f't+{(i+1)*2}s has 接线测试_角色673337: {'接线测试_角色673337' in body}')
            if '接线测试_角色673337' in body:
                print('  RENDERED')
                break
        print('最终:', '接线测试_角色673337' in _body(drv))
        # 角色操作按钮是否存在
        btns = drv.find_elements(By.XPATH, "//button[contains(@aria-label, '角色操作：接线测试_角色673337')]")
        print('角色操作按钮数:', len(btns))
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(run())
