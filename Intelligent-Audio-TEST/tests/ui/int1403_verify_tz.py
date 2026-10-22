# -*- coding: utf-8 -*-
"""INT-1403 测试工程师浏览器实测（off 模式直连真实库栈 :15000）。

流程：
1. 直连 #/system-settings/iam/users（后端 auth_mode=off，无需登录）；
2. 新建用户：用户名 + 非法邮箱 bad-email + 密码 → 保存 → 断言表单内提示
   「邮箱格式不正确」、模态窗未关、resource timing 无 POST /api/v1/auth/users；
3. 浅/深色截图（非法邮箱拦截态）；
4. 原生 setter 改合法邮箱 → 保存 → 断言「用户已创建」+ 出现 POST /auth/users；
5. 编辑态拦截：列表点「编辑」改非法邮箱 → 保存 → 断言拦截、无 PUT /auth/users/{id}；
6. API 回读自建用户 email + status，DELETE 清理；Network JSON + page_text 落盘。
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
BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5613')
API = os.environ.get('UI_API_BASE', 'http://127.0.0.1:15000')
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, '_int1403_evidence_tz')

# 用户名/邮箱带时间戳后缀：auth_service 删除为软删，唯一索引仍被占用（INT-1403 坑）
TEST_USER = f'接线测试_INT1403_{int(time.time() * 1000) % 100000}'
TEST_EMAIL = f'int1403_{int(time.time() * 1000) % 100000}@example.com'


def auth_users_entries(driver):
    return driver.execute_script(
        'return performance.getEntriesByType("resource")'
        '.filter(e => e.name.includes("/api/v1/auth/users"))'
        '.map(e => ({name: e.name, dur: e.duration}))')


def is_create_or_update_post(driver, base, method_verb):
    """返回出现过的写请求（POST /auth/users 或 PUT /auth/users/{id}），无则空列表。
    列表 GET 恒带 ?page= 查询参数，写请求 URL 无 query：按「精确路径且无 query」判定。
    """
    entries = auth_users_entries(driver)
    base = base.rstrip('/')
    out = []
    for e in entries:
        name = e['name']
        if method_verb == 'POST' and name == f'{base}/api/v1/auth/users':
            out.append(e)
        elif (method_verb == 'PUT' and name.startswith(f'{base}/api/v1/auth/users/')
              and '?' not in name):
            out.append(e)
    return out


def set_input_value(driver, selector, value):
    """原生 setter + input 事件，保证 Vue v-model 更新。"""
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

    import httpx
    try:
        # ── 0. 防串库：开始前核验 ──
        h = httpx.get(f'{API}/health', timeout=8).json()
        print('HEALTH_START', h.get('database'), flush=True)
        assert h.get('database') == 'intelligent_audio_test', h

        # ── 1. 打开用户管理页（off 模式直连）──
        driver.get(f'{BASE}/#/system-settings/iam/users')
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.settings-form-page')))
        except Exception:
            print('FIRST_LOAD_TIMEOUT_RELOAD', flush=True)
            driver.get(f'{BASE}/#/system-settings/iam/users')
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.settings-form-page')))
        time.sleep(2)
        body_text0 = driver.find_element(By.TAG_NAME, 'body').text[:200]
        print('PAGE_LOADED', repr(body_text0[:100]), flush=True)

        # ── 2. 新建用户 + 非法邮箱 → 拦截 ──
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
        err_texts = [e.text for e in err_el]
        print('ERROR_TEXT', err_texts, flush=True)
        assert any('邮箱格式不正确' in t for t in err_texts), f'error text missing: {err_texts}'
        assert driver.find_elements(By.CSS_SELECTOR, '.user-form'), 'modal closed unexpectedly'

        posts_invalid = is_create_or_update_post(driver, BASE, 'POST')
        print('INVALID_PHASE_POSTS', json.dumps(posts_invalid, ensure_ascii=False), flush=True)
        assert not posts_invalid, f'invalid email must not POST /auth/users: {posts_invalid}'

        # ── 3. 防串库：截图前核验 + 浅/深色截图 ──
        h2 = httpx.get(f'{API}/health', timeout=8).json()
        print('HEALTH_BEFORE_SHOT', h2.get('database'), flush=True)
        assert h2.get('database') == 'intelligent_audio_test', h2

        driver.save_screenshot(os.path.join(OUT_DIR, 'int1403_tz_light_invalid.png'))
        driver.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.5)
        driver.save_screenshot(os.path.join(OUT_DIR, 'int1403_tz_dark_invalid.png'))
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
        with open(os.path.join(OUT_DIR, 'page_text_after_valid.txt'), 'w', encoding='utf-8') as fh:
            fh.write(page_text)
        print('AFTER_VALID_SAVE_HAS_SUCCESS', '用户已创建' in page_text, flush=True)
        assert '用户已创建' in page_text, f'valid email should create user. page_text={page_text[:300]}'

        posts_valid = is_create_or_update_post(driver, BASE, 'POST')
        print('VALID_PHASE_POSTS', json.dumps(posts_valid, ensure_ascii=False), flush=True)
        assert posts_valid, 'valid email must POST /auth/users'

        # ── 5. 编辑态拦截：列表点「编辑」→ 改非法邮箱 → 保存 → 拦截 ──
        time.sleep(1)
        rows = driver.find_elements(By.CSS_SELECTOR, '.data-table tbody tr')
        target_row = None
        for r in rows:
            if TEST_USER in r.text:
                target_row = r
                break
        assert target_row is not None, 'created user row not found in list'
        edit_btn = target_row.find_element(By.XPATH, './/button[contains(., "编辑")]')
        edit_btn.click()
        time.sleep(1)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.user-form')))
        # 编辑态下 email 输入框
        set_input_value(driver, 'input[placeholder="user@example.com"]', 'edit-bad-email')
        save_btn = driver.find_element(By.CSS_SELECTOR, '.user-form .btn-primary')
        save_btn.click()
        time.sleep(1.5)
        err_el2 = driver.find_elements(By.CSS_SELECTOR, '.user-form .error-text')
        err_texts2 = [e.text for e in err_el2]
        print('EDIT_ERROR_TEXT', err_texts2, flush=True)
        assert any('邮箱格式不正确' in t for t in err_texts2), f'edit error missing: {err_texts2}'
        puts_edit = is_create_or_update_post(driver, BASE, 'PUT')
        print('EDIT_PHASE_PUTS', json.dumps(puts_edit, ensure_ascii=False), flush=True)
        assert not puts_edit, f'invalid edit must not PUT /auth/users/{{id}}: {puts_edit}'
        # 关闭编辑弹窗
        close_btn = driver.find_elements(By.CSS_SELECTOR, '.user-form .btn-default, .modal-close, .basic-modal .btn-text')
        # 尝试点击 modal 关闭按钮
        try:
            driver.execute_script(
                "const es=[...document.querySelectorAll('.basic-modal, .modal-mask, .basic-modal-mask, [class*=mask], [class*=overlay]')];"
                "const m=es.find(e=>e.getBoundingClientRect().width>0 && e.getBoundingClientRect().height>0);"
                "if(m) m.click();")
        except Exception as ex:
            print('CLOSE_MODAL_EXC', str(ex)[:120], flush=True)

        # ── 6. API 回读 + 清理 ──
        lst = httpx.get(f'{API}/api/v1/auth/users', timeout=15).json()
        users = lst.get('data', {}).get('items') or lst.get('items') or []
        created_id = None
        for u in users:
            if u.get('username') == TEST_USER:
                created_id = u['id']
                got = httpx.get(f'{API}/api/v1/auth/users/{u["id"]}', timeout=15)
                got_j = got.json().get('data', got.json())
                print('GET_CREATED', got.status_code, 'email=', got_j.get('email'),
                      'status=', got_j.get('status'), flush=True)
                assert got_j.get('email') == TEST_EMAIL, got_j
                assert got_j.get('status') == 'active', got_j
                break
        assert created_id, 'created test user not found in list'
        del_r = httpx.delete(f'{API}/api/v1/auth/users/{created_id}', timeout=15)
        print('DELETE_TEST_USER', del_r.status_code, flush=True)

        lst2 = httpx.get(f'{API}/api/v1/auth/users', timeout=15).json()
        users2 = lst2.get('data', {}).get('items') or lst2.get('items') or []
        assert not any(u.get('username') == TEST_USER for u in users2), 'test user not cleaned'
        print('TOTAL_USERS_AFTER_CLEAN', len(users2), flush=True)

        # ── 7. 防串库：交付前核验 + Network 落盘 ──
        h3 = httpx.get(f'{API}/health', timeout=8).json()
        print('HEALTH_END', h3.get('database'), flush=True)
        assert h3.get('database') == 'intelligent_audio_test', h3

        perfs_all = driver.execute_script(
            'return performance.getEntriesByType("resource").map(e => ({name: e.name, dur: e.duration}))')
        with open(os.path.join(OUT_DIR, 'network.json'), 'w', encoding='utf-8') as fh:
            json.dump(perfs_all, fh, ensure_ascii=False, indent=1)

        print('PASS', flush=True)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
