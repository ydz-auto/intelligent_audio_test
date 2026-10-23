# -*- coding: utf-8 -*-
"""INT-1530 快速探测：docker 15173 上 开始测试页 / 设备 API 页加载与弹窗结构。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    service = Service(executable_path=os.path.join(
        os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64', '155.0.8059.39', 'chromedriver.exe'))
    return webdriver.Chrome(options=options, service=service)


def main():
    drv = _driver()
    try:
        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(6)
        print('URL:', drv.current_url)
        print('title:', drv.title)
        print('has 新增 API:', any('新增 API' in (b.text or '') for b in drv.find_elements(By.TAG_NAME, 'button')))
        print('has API 密钥:', 'API 密钥' in (drv.execute_script('return document.body.textContent') or ''))
        btns = [b.text.strip() for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip()]
        print('buttons:', json.dumps(btns[:30], ensure_ascii=False))
        drv.save_screenshot(os.path.join('tests/ui/artifacts/int1530', 'probe_starttest.png'))
        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(5)
        print('devices URL:', drv.current_url)
        print('devices has 添加测试API:', any('添加测试API' in (b.text or '') for b in drv.find_elements(By.TAG_NAME, 'button')))
        btns2 = [b.text.strip() for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip()]
        print('devices buttons:', json.dumps(btns2[:30], ensure_ascii=False))
        drv.save_screenshot(os.path.join('tests/ui/artifacts/int1530', 'probe_devices.png'))
    finally:
        drv.quit()


if __name__ == '__main__':
    os.makedirs('tests/ui/artifacts/int1530', exist_ok=True)
    main()
