# -*- coding: utf-8 -*-
"""INT-983（重交付 INT-288）A 域三页加载/错误/空态真实浏览器截图。

用 CDP 网络拦截制造后端不可用场景，验证错误态（LoadErrorState 错误条 + 重试）
而非误导性空态；同时截成功态与 LogView 空态。纯读页，只读语义，不改库。
注：旧 Vue 未启用 .dark 主题（tokens.css「结构预留，项目当前未启用」），只截浅色。

CDP 陷阱（实测）：setBlockedURLs 只对本会话「设置之后」发出的请求生效；同会话先
加载成功态再拦，浏览器从缓存/bfcache 供数，拦截不生效 → 成功/错误各用独立会话。
"""
import os
import time

from selenium import webdriver

BASE = 'http://127.0.0.1:5401'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int983_shots')
os.makedirs(OUT, exist_ok=True)

DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'

PAGES = [
    ('home', '/#/', ['.quick-stats', '.home-stats-loading', '.load-error-state']),
    ('tasks', '/#/tasks', ['.task-list-with-pagination', '.empty-state', '.load-error-state']),
    ('logview', '/#/LogView', ['.data-table', '.lv-loading-state', '.lv-empty-state', '.load-error-state']),
]


def wait_any(driver, selectors, timeout=25):
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


def new_driver(block_api):
    opts = webdriver.ChromeOptions()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    d = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
    d.set_window_size(1440, 900)
    d.execute_cdp_cmd('Network.enable', {})
    if block_api:
        d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api/v1*', '*socket.io*']})
    return d


def shot(driver, name):
    driver.save_screenshot(os.path.join(OUT, name))
    print('saved', name)


def capture_ok():
    d = new_driver(False)
    try:
        for tag, path, sels in PAGES:
            d.get(BASE + path)
            wait_any(d, sels, timeout=25)
            time.sleep(2)
            shot(d, f'{tag}_success.png')
    finally:
        d.quit()


def capture_error():
    d = new_driver(True)
    try:
        for tag, path, sels in PAGES:
            d.get(BASE + path)
            wait_any(d, sels, timeout=25)
            time.sleep(2)
            shot(d, f'{tag}_error.png')
    finally:
        d.quit()


def capture_empty():
    d = new_driver(False)
    try:
        d.get(BASE + '/#/LogView')
        wait_any(d, ['.data-table', '.lv-empty-state'], timeout=25)
        d.execute_script(
            "const inp = document.querySelector('.search-input');"
            "if (inp) { inp.value = '无此日志关键词xyz'; "
            "  inp.dispatchEvent(new Event('input', { bubbles: true })); }"
        )
        wait_any(d, ['.lv-empty-state'], timeout=25)
        time.sleep(2)
        shot(d, 'logview_empty.png')
    finally:
        d.quit()


if __name__ == '__main__':
    capture_ok()
    capture_error()
    capture_empty()
