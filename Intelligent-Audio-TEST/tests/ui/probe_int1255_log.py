# -*- coding: utf-8 -*-
"""INT-1255 日志下载流程探针 v2。"""
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
        drv.get(BASE + '/report/493')
        WebDriverWait(drv, 40).until(lambda d: '豆包拒识' in _body(d))
        # 等具体用例数据加载
        for i in range(8):
            time.sleep(3)
            n = len(drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '下载日志')]"))
            print(f't+{(i+1)*3}s 下载日志按钮数={n}')
            if n > 0:
                break
        # 滚动到具体用例区
        drv.execute_script("document.querySelector('#report-specific-cases')?.scrollIntoView({block:'center'})")
        time.sleep(1)
        dl_btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '下载日志')]")
        print('可点按钮数:', len(dl_btns))
        for i, b in enumerate(dl_btns[:5]):
            try:
                print(f'  [{i}] displayed={b.is_displayed()} size={b.size}')
            except Exception as e:
                print(f'  [{i}] err {e}')
        # 点第一个
        if dl_btns:
            b = dl_btns[0]
            try:
                drv.execute_script('arguments[0].scrollIntoView({block:"center"})', b)
                time.sleep(0.5)
                b.click()
            except Exception:
                drv.execute_script('arguments[0].click()', b)
            time.sleep(2.5)
            body = _body(drv)
            print('弹窗含日志文件:', '日志文件' in body)
            print('body 片段:', body[max(0, body.find('下载')-30):body.find('下载')+80].replace('\n', ' '))
            drv.save_screenshot('tests/ui/artifacts/int1255_report/probe_log_dialog2.png')
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
