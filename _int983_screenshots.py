# -*- coding: utf-8 -*-
"""INT-983（重交付 INT-288）A 域四页加载/错误/空态真实浏览器截图。

用 CDP 网络拦截制造后端不可用场景，验证错误态（LoadErrorState 错误条 + 重试）
而非误导性空态；同时截成功态。纯读页，只读语义，不改库。
"""
import os
import time

from selenium import webdriver

BASE = 'http://127.0.0.1:5401'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int983_shots')
os.makedirs(OUT, exist_ok=True)

DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'

PAGES = [
    ('home', '/', ['.home-stats-loading', '.quick-stats', '.load-error-state']),
    ('tasks', '/tasks', ['.load-error-state', '.empty-state', '.task-list-with-pagination']),
    ('logview', '/LogView', ['.lv-loading-state', '.lv-empty-state', '.load-error-state', '.data-table']),
]

def wait_any(driver, selectors, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            found = driver.execute_script(
                "const sels = arguments[0];"
                "return sels.some(s => document.querySelector(s) !== null);",
                selectors,
            )
            if found:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False

def block_api(driver, block=True):
    driver.execute_cdp_cmd('Network.enable', {})
    if block:
        driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api*', '*socket.io*', '*ws*']})
    else:
        driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})

def shot(driver, name):
    driver.save_screenshot(os.path.join(OUT, name))
    print('saved', name)

def main():
    opts = webdriver.ChromeOptions()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
    driver.set_window_size(1440, 900)
    try:
        for tag, path, sels in PAGES:
            # 成功态
            block_api(driver, False)
            driver.get(BASE + path)
            wait_any(driver, sels, timeout=20)
            time.sleep(2)
            shot(driver, f'{tag}_success.png')

            # 错误态：CDP 拦截 API
            block_api(driver, True)
            driver.get(BASE + path)
            wait_any(driver, sels, timeout=20)
            time.sleep(2)
            shot(driver, f'{tag}_error.png')
    finally:
        driver.quit()

if __name__ == '__main__':
    main()
