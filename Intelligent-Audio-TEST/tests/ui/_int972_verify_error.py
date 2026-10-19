# -*- coding: utf-8 -*-
"""INT-972 实测：用例列表在后端不可用时的错误态降级（dead backend repro）。

驱动 dev server（VITE_API_TARGET=localhost:5099 端口不存在）加载 #/testcases，
断言：
1. 渲染 .test-case-error-banner（固定友好文案「用例服务暂不可用，请稍后重试」），
   不再渲染「没有找到测试用例分组 / 没有找到标签分组的测试用例」空态；
2. 浅/深色各截图；
3. Network 取证（resource timing：指向 5099 的 API 请求全部失败）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHROME_BINARY = os.environ.get(
    'UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')

BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5611')
ROUTE = 'testcases'
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, '_int972_evidence')

os.makedirs(OUT_DIR, exist_ok=True)

BANNER = '.test-case-error-banner'
GROUP_EMPTY = '没有找到测试用例分组'
TAG_EMPTY = '没有找到标签分组的测试用例'
FRIENDLY_COPY = '用例服务暂不可用，请稍后重试'


def main():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--force-device-scale-factor=1')
    # 浏览器 console 取证（http client 每笔 API 请求/失败都 console.log，见 client.ts）
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

    driver = webdriver.Chrome(options=opts, service=Service())
    driver.set_window_size(1440, 900)

    try:
        # 单次导航 + 长等待：Vite dev 首次加载需编译全模块图（可达 1 分钟）
        driver.get(f'{BASE}/#/{ROUTE}')
        wait = WebDriverWait(driver, 90)
        try:
            banner = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, BANNER)))
        except Exception:
            print('TIMEOUT_DIAG URL=', driver.current_url)
            print('TIMEOUT_DIAG TITLE=', repr(driver.title))
            print('TIMEOUT_DIAG BODY=', repr(driver.find_element(By.TAG_NAME, 'body').text[:1500]))
            driver.save_screenshot(os.path.join(OUT_DIR, 'int972_timeout_diag.png'))
            raise
        # 等待 fetch 失败与 DOM 稳定
        time.sleep(3)

        assert FRIENDLY_COPY in banner.text, f'错误横幅缺固定文案: {banner.text!r}'
        body = driver.find_element(By.TAG_NAME, 'body').text
        assert GROUP_EMPTY not in body, '分组空态仍渲染（误导用户）'
        assert TAG_EMPTY not in body, '标签空态仍渲染（误导用户）'
        print('BANNER_TEXT=', repr(banner.text))
        print('EMPTY_STATE_SUPPRESSED=OK')

        # 浅色截图
        driver.save_screenshot(os.path.join(OUT_DIR, 'int972_error_light.png'))
        # 深色：documentElement 加 .dark
        driver.execute_script("document.documentElement.classList.add('dark');")
        time.sleep(1)
        driver.save_screenshot(os.path.join(OUT_DIR, 'int972_error_dark.png'))
        driver.execute_script("document.documentElement.classList.remove('dark');")

        # Network 取证：5099 的 API 请求（Failed to fetch 一般不留 resource entry，
        # 转用浏览器 console——http client 每笔请求/失败都 console.log）
        entries = driver.execute_script(
            'return performance.getEntriesByType("resource")'
            '.filter(e => e.name.includes("localhost:5099"))'
            '.map(e => ({name: e.name, initiatorType: e.initiatorType, '
            'duration: Math.round(e.duration * 100) / 100, transferSize: e.transferSize}));')
        print('NETWORK_ENTRIES=', json.dumps(entries, ensure_ascii=False, indent=2))
        console_logs = [
            {'level': e['level'], 'message': e['message']}
            for e in driver.get_log('browser')
            if 'localhost:5099' in e.get('message', '') or '[API Request]' in e.get('message', '')
            or '获取测试用例失败' in e.get('message', '') or '获取标签视图数据失败' in e.get('message', '')
        ]
        with open(os.path.join(OUT_DIR, 'int972_network.json'), 'w', encoding='utf-8') as fh:
            json.dump({'resourceTiming': entries, 'console': console_logs}, fh,
                      ensure_ascii=False, indent=2)
        print('CONSOLE_API_LOG_COUNT=', len(console_logs))
        for c in console_logs[:12]:
            print('CONSOLE:', c['level'], c['message'][:160])

        # 分组/标签两个视图切换后错误横幅仍显示（store error 贯通两个视图）
        driver.execute_script("document.querySelectorAll('.view-switcher button')[1]?.click();")
        time.sleep(2)
        tag_body = driver.find_element(By.TAG_NAME, 'body').text
        assert TAG_EMPTY not in tag_body, '标签视图空态仍渲染'
        assert FRIENDLY_COPY in tag_body, '标签视图错误横幅缺失'
        print('TAG_VIEW_ERROR_STATE=OK')

        print('ALL_ASSERTIONS_PASSED')
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
