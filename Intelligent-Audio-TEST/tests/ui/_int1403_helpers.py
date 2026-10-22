# -*- coding: utf-8 -*-
"""INT-1403 helper: 用浏览器登录拿 token，列出 接线测试_INT1403 前缀用户（诊断残留）。"""
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
CHROME_BINARY = os.environ.get('UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5670')
API = os.environ.get('UI_API_BASE', 'http://127.0.0.1:15000')
USERNAME = os.environ.get('UI_TEST_USERNAME', '接线测试_admin')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'JieXianTest@2026')


def main():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=opts, service=Service())
    wait = WebDriverWait(driver, 60)
    try:
        driver.get(f'{BASE}/#/login')
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
        time.sleep(1)
        uname = driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]')
        pwd = driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]')
        btn = driver.find_element(By.CSS_SELECTOR, '.login-card form button')
        uname.send_keys(USERNAME)
        pwd.send_keys(PASSWORD)
        btn.click()
        wait.until(lambda d: '/login' not in d.current_url.split('#')[-1])
        time.sleep(2)
        token = driver.execute_script('return localStorage.getItem("auth_token")')
        print('TOKEN_LEN', len(token) if token else 0, flush=True)
        import httpx
        headers = {'Authorization': f'Bearer {token}'}
        # 清理所有 INT1403 前缀测试用户
        r = httpx.get(f'{API}/api/v1/auth/users', headers=headers, timeout=15)
        j = r.json()
        users = j.get('items') or j.get('data', {}).get('items') or []
        for u in users:
            nm = u.get('username') or ''
            if 'INT1403' in nm or '邮箱' in nm:
                print('CLEANING', u.get('id'), repr(nm), flush=True)
                httpx.delete(f"{API}/api/v1/auth/users/{u['id']}", headers=headers, timeout=15)
        r2 = httpx.get(f'{API}/api/v1/auth/users', headers=headers, timeout=15)
        users2 = r2.json().get('items') or r2.json().get('data', {}).get('items') or []
        print('TOTAL_USERS_AFTER_CLEAN', len(users2), flush=True)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
