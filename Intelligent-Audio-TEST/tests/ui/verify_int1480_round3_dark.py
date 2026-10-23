# -*- coding: utf-8 -*-
"""INT-1480 第三轮补拍：安装/卸载、设备表单、扫描弹窗的深色截图（只读，不提交）。"""
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.stdout.reconfigure(encoding='utf-8')
BASE = 'http://127.0.0.1:15173'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1480_round3')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ONLINE_DEVICE = 'pura90gpt'


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = [(tuple(int(x) for x in v.split('.') if x.isdigit()),
              os.path.join(cache, v, 'chromedriver.exe'))
             for v in os.listdir(cache) if os.path.isfile(os.path.join(cache, v, 'chromedriver.exe'))]
    d = webdriver.Chrome(options=o, service=Service(executable_path=max(cands)[1]))
    d.set_page_load_timeout(60)
    return d


def body(d):
    return d.execute_script('return document.body.textContent || ""')


def shot(d, name):
    p = os.path.join(ART, name)
    os.makedirs(p, exist_ok=True)
    d.save_screenshot(os.path.join(p, 'screenshot.png'))
    print('saved', name)


def jsclick(d, el):
    d.execute_script('arguments[0].click()', el)
    time.sleep(0.5)


def menu_item(d, label, timeout=8):
    def f(x):
        for it in x.find_elements(By.XPATH, "//*[@role='menuitem']"):
            try:
                if label in it.text and it.is_displayed():
                    return it
            except Exception:
                continue
        return False
    return WebDriverWait(d, timeout).until(f)


def main():
    d = driver()
    try:
        d.get(BASE + '/devices/test')
        WebDriverWait(d, 40).until(lambda x: '设备管理' in body(x))
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.refresh()
        WebDriverWait(d, 40).until(lambda x: '设备管理' in body(x))
        time.sleep(2.0)

        # 1) 设备表单深色
        for b in d.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
            if b.is_displayed():
                jsclick(d, b)
                break
        WebDriverWait(d, 20).until(lambda x: '测试设备信息' in body(x))
        time.sleep(1.0)
        shot(d, 'r4_drawer_dark')
        for b in d.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]"):
            if b.is_displayed():
                jsclick(d, b)
                break
        time.sleep(1.0)

        # 2) 安装应用弹窗深色（只打开后取消，不提交）
        jsclick(d, d.find_element(By.XPATH, "//button[@aria-label='操作 %s']" % ONLINE_DEVICE))
        jsclick(d, menu_item(d, '安装应用'))
        WebDriverWait(d, 15).until(lambda x: '应用安装包路径' in body(x))
        time.sleep(1.0)
        shot(d, 'r2_install_dialog_dark')
        for b in d.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]"):
            if b.is_displayed():
                jsclick(d, b)
                break
        time.sleep(1.0)

        # 3) 卸载应用弹窗深色
        jsclick(d, d.find_element(By.XPATH, "//button[@aria-label='操作 %s']" % ONLINE_DEVICE))
        jsclick(d, menu_item(d, '卸载应用'))
        WebDriverWait(d, 15).until(lambda x: '应用包名' in body(x))
        time.sleep(1.0)
        shot(d, 'r2_uninstall_dialog_dark')
        for b in d.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]"):
            if b.is_displayed():
                jsclick(d, b)
                break
        time.sleep(1.0)

        # 4) 扫描弹窗深色
        jsclick(d, d.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
        time.sleep(0.6)
        jsclick(d, menu_item(d, '扫描设备'))
        WebDriverWait(d, 20).until(lambda x: '扫描测试设备' in body(x))
        time.sleep(5)
        shot(d, 'r5_scan_dark')
        for b in d.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]"):
            if b.is_displayed():
                jsclick(d, b)
                break

        # 恢复浅色，避免影响后续并发走查
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light')")
        d.get(BASE + '/devices/test')
        WebDriverWait(d, 40).until(lambda x: '设备管理' in body(x))
    finally:
        d.quit()


main()
