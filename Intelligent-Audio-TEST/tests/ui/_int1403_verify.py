# -*- coding: utf-8 -*-
"""INT-1403 浏览器实测：IAM 用户表单邮箱格式校验（v3，原生 setter 输入 + 诊断落盘）。

流程：
1. 表单登录真实库栈（接线测试_admin / JieXianTest@2026，:15000 主库 intelligent_audio_test）；
2. 打开 #/system-settings/iam/users → 新建用户；
3. 填用户名 + 非法邮箱 bad-email + 密码 → 保存 → 断言表单内提示「邮箱格式不正确」、
   模态窗未关、无 POST /auth/users（resource timing 快照）；
4. 浅/深色截图（非法邮箱拦截态）；
5. 用原生 setter 改合法邮箱 → 保存 → 断言出现 POST /auth/users + 提示「用户已创建」；
6. API 回读自建用户 email、删除清理；Network JSON + page_text 落盘。
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

BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5670')
API = os.environ.get('UI_API_BASE', 'http://127.0.0.1:15000')
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, '_int1403_evidence')
USERNAME = os.environ.get('UI_TEST_USERNAME', '接线测试_admin')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'JieXianTest@2026')

# 用户名带时间戳后缀：auth_service 删除为软删，用户名/邮箱唯一索引仍被占用，
# 复用同一用户名或邮箱会 400/500「已存在」，故每轮用唯一用户名+唯一邮箱。
TEST_USER = f'接线测试_INT1403_{int(time.time() * 1000) % 100000}'
TEST_EMAIL = f'int1403_{int(time.time() * 1000) % 100000}@example.com'


def auth_users_entries(driver):
    return driver.execute_script(
        'return performance.getEntriesByType("resource")'
        '.filter(e => e.name.includes("/api/v1/auth/users"))'
        '.map(e => ({name: e.name, dur: e.duration}))')


def set_input_value(driver, selector, value):
    """原生 setter + input 事件，保证 Vue v-model 更新（Selenium 中文/清空兼容）。"""
    script = f"""
    const el = document.querySelector({json.dumps(selector)});
    const proto = el.tagName === 'TEXTAREA'
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, {json.dumps(value)});
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    return el.value;
    """
    return driver.execute_script(script)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--force-device-scale-factor=1')
    opts.add_argument('--disable-dev-shm-usage')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

    driver = webdriver.Chrome(options=opts, service=Service())
    driver.set_window_size(1440, 900)
    wait = WebDriverWait(driver, 90)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'performance.setResourceTimingBufferSize(3000);'
    })
    driver.execute_script('performance.setResourceTimingBufferSize(3000)')
    try:
        # ── 1. 登录 ──
        driver.get(f'{BASE}/#/login')
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
        except Exception:
            body = driver.find_element(By.TAG_NAME, 'body').get_attribute('innerHTML')[:500]
            print('LOGIN_PAGE_NO_CARD', body, flush=True)
        time.sleep(1)
        uname = driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]')
        pwd = driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]')
        btn = driver.find_element(By.CSS_SELECTOR, '.login-card form button')
        uname.send_keys(USERNAME)
        pwd.send_keys(PASSWORD)
        btn.click()
        try:
            wait.until(lambda d: '/login' not in d.current_url.split('#')[-1])
            print('LOGIN_OK', driver.current_url, flush=True)
        except Exception:
            err = driver.find_elements(By.CSS_SELECTOR, '.login-card .error-msg')
            print('LOGIN_ERR', [e.text for e in err], driver.current_url, flush=True)
            raise
        time.sleep(2)
        token = driver.execute_script('return localStorage.getItem("auth_token")')
        print('TOKEN_LEN', len(token) if token else 0, flush=True)
        if not token:
            raise RuntimeError('no auth_token in localStorage')

        # 预清理同名测试用户（幂等）
        import httpx
        headers = {'Authorization': f'Bearer {token}'}
        lst = httpx.get(f'{API}/api/v1/auth/users', headers=headers, timeout=15).json()
        users = lst.get('items') or lst.get('data', {}).get('items') or []
        for u in users:
            if u.get('username') == TEST_USER:
                httpx.delete(f"{API}/api/v1/auth/users/{u['id']}", headers=headers, timeout=15)
                print('PRE_CLEAN_DELETED', u['id'], flush=True)

        # ── 2. 打开用户管理页（整页加载） ──
        driver.get(f'{BASE}/#/system-settings/iam/users')
        time.sleep(3)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.settings-form-page')))
        time.sleep(1)

        # ── 3. 新建用户 + 非法邮箱 → 拦截 ──
        new_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//button[contains(., "新建用户")]')))
        new_btn.click()
        time.sleep(1)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.user-form')))
        set_input_value(driver, 'input[placeholder="登录名"]', TEST_USER)
        set_input_value(driver, 'input[placeholder="user@example.com"]', 'bad-email')
        set_input_value(driver, 'input[placeholder="至少 6 位"]', 'Test@123456')

        save_btn = driver.find_element(By.CSS_SELECTOR, '.user-form .btn-primary')
        save_btn.click()
        time.sleep(1.5)

        err_el = driver.find_elements(By.CSS_SELECTOR, '.user-form .error-text')
        texts = [e.text for e in err_el]
        print('ERROR_TEXT', texts, flush=True)
        assert any('邮箱格式不正确' in t for t in texts), f'error text missing: {texts}'
        assert driver.find_elements(By.CSS_SELECTOR, '.user-form'), 'modal closed unexpectedly'

        invalid_entries = auth_users_entries(driver)
        post_invalid = [p for p in invalid_entries if not '?' in p['name'].split('/api/v1/auth/users')[1]]
        print('INVALID_PHASE_AUTH_USERS', json.dumps(invalid_entries, ensure_ascii=False), flush=True)
        assert not post_invalid, f'invalid email must not POST /auth/users: {post_invalid}'

        driver.save_screenshot(os.path.join(OUT_DIR, 'int1403_light_invalid.png'))
        driver.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.5)
        driver.save_screenshot(os.path.join(OUT_DIR, 'int1403_dark_invalid.png'))
        driver.execute_script('document.documentElement.classList.remove("dark")')

        # ── 4. 改合法邮箱 → 提交成功 ──
        set_input_value(driver, 'input[placeholder="user@example.com"]', TEST_EMAIL)
        email_val = driver.execute_script(
            'return document.querySelector("input[placeholder=\'user@example.com\']").value')
        print('EMAIL_VALUE_BEFORE_SAVE', repr(email_val), flush=True)
        save_btn = driver.find_element(By.CSS_SELECTOR, '.user-form .btn-primary')
        save_btn.click()
        time.sleep(2.5)

        page_text = driver.find_element(By.CSS_SELECTOR, '.settings-form-page').text
        with open(os.path.join(OUT_DIR, 'page_text.txt'), 'w', encoding='utf-8') as fh:
            fh.write(page_text)
        print('AFTER_VALID_SAVE_HAS_SUCCESS', '用户已创建' in page_text, flush=True)
        if '用户已创建' not in page_text:
            print('PAGE_TEXT_DUMPED', flush=True)

        valid_entries = auth_users_entries(driver)
        post_valid = [p for p in valid_entries if not '?' in p['name'].split('/api/v1/auth/users')[1]]
        print('VALID_PHASE_AUTH_USERS', json.dumps(valid_entries, ensure_ascii=False), flush=True)

        # ── 5. API 回读 + 清理 ──
        lst2 = httpx.get(f'{API}/api/v1/auth/users', headers=headers, timeout=15).json()
        users2 = lst2.get('items') or lst2.get('data', {}).get('items') or []
        created_id = None
        for u in users2:
            if u.get('username') == TEST_USER:
                created_id = u['id']
                got = httpx.get(f'{API}/api/v1/auth/users/{u["id"]}', headers=headers, timeout=15)
                got_j = got.json().get('data', got.json())
                print('GET_CREATED', got.status_code, 'email=', got_j.get('email'),
                      'status=', got_j.get('status'), flush=True)
                assert got_j.get('email') == TEST_EMAIL, got_j
                break
        assert created_id, 'created test user not found in list'
        del_r = httpx.delete(f'{API}/api/v1/auth/users/{created_id}', headers=headers, timeout=15)
        print('DELETE_TEST_USER', del_r.status_code, flush=True)

        lst3 = httpx.get(f'{API}/api/v1/auth/users', headers=headers, timeout=15).json()
        users3 = lst3.get('items') or lst3.get('data', {}).get('items') or []
        assert not any(u.get('username') == TEST_USER for u in users3), 'test user not cleaned'

        perfs_all = driver.execute_script(
            'return performance.getEntriesByType("resource").map(e => ({name: e.name, dur: e.duration}))')
        with open(os.path.join(OUT_DIR, 'network.json'), 'w', encoding='utf-8') as fh:
            json.dump(perfs_all, fh, ensure_ascii=False, indent=1)

        print('PASS', flush=True)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
