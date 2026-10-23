# -*- coding: utf-8 -*-
"""INT-1436 补充探针：跨路由切换 + 移动端目录折叠（390px 视口）。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver(width=1680, height=1050):
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument(f'--window-size={width},{height}')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    ver_t = tuple(int(x) for x in ver.split('.') if x.isdigit())
                except ValueError:
                    continue
                if ver_t and ver_t[0] == chrome_major:
                    drv_path = exe
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def main():
    drv = _driver()
    try:
        # ① 从 /user-guide 点侧栏「接入指南」→ 跨路由切换到 /user-guide-integration
        drv.get(BASE + '/user-guide')
        time.sleep(2.5)
        assert '使用手册' in drv.find_element(By.TAG_NAME, 'body').text
        link = drv.find_element(By.CSS_SELECTOR, "aside a[href='/user-guide-integration']")
        link.click()
        time.sleep(2.0)
        assert '/user-guide-integration' in drv.current_url, drv.current_url
        assert '接入指南' in drv.find_element(By.TAG_NAME, 'body').text
        print('① 从使用手册跨路由切到接入指南 ✓', drv.current_url)

        # ② 移动端 390px：目录折叠触发器「目录」可见，展开后三章条目存在
        drv.set_window_size(390, 844)
        time.sleep(1.5)
        body = drv.find_element(By.TAG_NAME, 'body')
        toc_btn = drv.find_elements(By.XPATH, "//button[contains(., '目录')]")
        assert toc_btn, '移动端目录折叠触发器缺失'
        toc_btn[0].click()
        time.sleep(1.0)
        aside = drv.find_element(By.CSS_SELECTOR, 'aside')
        toc_items = aside.find_elements(By.CSS_SELECTOR, "ul a[href^='#']")
        assert len(toc_items) == 3, f'移动端目录条目数 = {len(toc_items)}'
        print(f'② 移动端目录折叠触发器 + 三章条目展开 ✓ ({len(toc_items)})')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
