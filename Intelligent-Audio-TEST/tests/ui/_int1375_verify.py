# -*- coding: utf-8 -*-
"""INT-1375 浏览器实测：设备 SPL 编辑回显测试频率。

流程：
1. 表单登录真实库栈（接线测试_admin / JieXianTest@2026，VITE_AUTH_MODE=dev 加密链路）；
2. 打开 #/SPLMapping 设备 SPL 页；
3. 通过 API（用 localStorage token）POST /spl 建 test_frequency=2000 映射；
4. 页面刷新后点该映射「编辑」；
5. 断言 #field-testFrequency 值为 2000（缺陷修复后不回退 1000）；
6. Network 取证 GET /spl/{id} 返回 test_frequency=2000；
7. 浅/深色截图。
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

BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5600')
API = os.environ.get('UI_API_BASE', 'http://127.0.0.1:5700')
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, '_int1375_evidence')
USERNAME = os.environ.get('UI_TEST_USERNAME', '接线测试_admin')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'JieXianTest@2026')

MAPPING_NAME = '接线测试_INT1375_2000'


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
    # 每个新文档注入：扩大 resource timing 缓冲区，避免 vite 模块加载占满 250 默认槽位丢失 API 请求
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
            # 登录页可能无 .login-card，打印页面片段帮助诊断
            body = driver.find_element(By.TAG_NAME, 'body').get_attribute('innerHTML')[:500]
            print('LOGIN_PAGE_NO_CARD', body, flush=True)
        time.sleep(1)
        try:
            uname = driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]')
        except Exception:
            # 兜底：任意 input
            inputs = driver.find_elements(By.CSS_SELECTOR, 'input')
            print('INPUTS', [i.get_attribute('placeholder') for i in inputs], flush=True)
            raise
        pwd = driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]')
        btn = driver.find_element(By.CSS_SELECTOR, '.login-card form button')
        uname.send_keys(USERNAME)
        pwd.send_keys(PASSWORD)
        btn.click()
        # 等待离开 /login
        try:
            wait.until(lambda d: '/login' not in d.current_url.split('#')[-1])
            print('LOGIN_OK', driver.current_url, flush=True)
        except Exception:
            err = driver.find_elements(By.CSS_SELECTOR, '.login-card .error-msg')
            print('LOGIN_ERR', [e.text for e in err], driver.current_url, flush=True)
            raise
        # 等 token 就绪
        time.sleep(2)
        token = driver.execute_script('return localStorage.getItem("auth_token")')
        print('TOKEN_LEN', len(token) if token else 0, flush=True)
        if not token:
            raise RuntimeError('no auth_token in localStorage')

        # ── 2. 打开 SPL 页（整页加载，避免 boot 吞 hash 导航） ──
        driver.get(f'{BASE}/#/SPLMapping')
        time.sleep(3)
        # 断言页面标题
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.spl-mapping-view')))

        # ── 3. 建 test_frequency=2000 映射（API，token 取自登录） ──
        # SPL 映射关联的是播放设备（/playback-devices）
        import httpx
        headers = {'Authorization': f'Bearer {token}'}
        dev_r = httpx.get(f'{API}/api/v1/playback-devices', headers=headers, timeout=10)
        dev_j = dev_r.json()
        # 兼容多种包装：数组 / { items } / { data: [...] } / { data: { items } }
        devs = dev_j if isinstance(dev_j, list) else dev_j.get('items') or (dev_j.get('data') or {}).get('items') or dev_j.get('data') or []
        print('DEVICES', len(devs), flush=True)
        device_id = None
        for d in (devs or []):
            if isinstance(d, dict) and d.get('id'):
                device_id = d['id']
                break
        if device_id is None:
            print('DEV_RESP', dev_r.text[:400], flush=True)
        # 删除旧测试映射（幂等）
        spl_list = httpx.get(f'{API}/api/v1/spl', headers=headers, timeout=10).json()
        for m in (spl_list.get('items') or []):
            if m.get('name') == MAPPING_NAME:
                httpx.delete(f"{API}/api/v1/spl/{m['id']}", headers=headers, timeout=10)
        payload = {
            'name': MAPPING_NAME,
            'device_id': device_id,
            'distance': 1,
            'test_frequency': 2000,
        }
        resp = httpx.post(f'{API}/api/v1/spl', json=payload, headers=headers, timeout=10)
        print('POST_SPL', resp.status_code, resp.text[:300], flush=True)
        if resp.status_code >= 400:
            raise RuntimeError(f'POST /spl failed: {resp.status_code} {resp.text}')
        created = resp.json()
        created_id = created.get('id') or created.get('data', {}).get('id')
        if not created_id:
            raise RuntimeError(f'created mapping id missing: {created.text}')
        print('CREATED_ID', created_id, flush=True)

        # 核对 GET 回读
        get_r = httpx.get(f'{API}/api/v1/spl/{created_id}', headers=headers, timeout=10)
        got = get_r.json().get('data', get_r.json())
        print('GET_SPL', get_r.status_code, 'test_frequency=', got.get('test_frequency'), flush=True)
        assert get_r.status_code == 200

        # ── 4. 刷新页面 → 点该映射「编辑」 ──
        driver.get(f'{BASE}/#/SPLMapping')
        time.sleep(3)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.spl-mapping-view')))
        # 找到名称匹配的卡片
        cards = driver.find_elements(By.CSS_SELECTOR, '.mapping-card')
        print('CARDS_COUNT', len(cards), flush=True)
        for c in cards:
            nm = c.find_element(By.CSS_SELECTOR, '.mapping-name').text
            print('  CARD', repr(nm), flush=True)
        target = None
        for c in cards:
            if MAPPING_NAME in c.find_element(By.CSS_SELECTOR, '.mapping-name').text:
                target = c
                break
        if target is None:
            body = driver.find_element(By.CSS_SELECTOR, '.spl-mapping-view').text[:800]
            print('CARD_NOT_FOUND', body, flush=True)
            raise RuntimeError('mapping card not found')
        edit_btn = target.find_element(By.XPATH, './/button[contains(., "编辑")]')
        edit_btn.click()
        # 等模态窗与字段
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#field-testFrequency')))
        except Exception:
            # 字段可能是 name 不同大小写或 input 组合
            print('NO_FIELD', flush=True)
            raise
        tf = driver.find_element(By.CSS_SELECTOR, '#field-testFrequency')
        val = tf.get_attribute('value')
        print('FIELD_TESTFREQ_VALUE', repr(val), flush=True)
        assert val == '2000', f'回显 {val!r} != 2000'

        # 浅色截图
        driver.save_screenshot(os.path.join(OUT_DIR, 'int1375_light_edit.png'))

        # ── 5. 深色 ──
        driver.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.5)
        driver.save_screenshot(os.path.join(OUT_DIR, 'int1375_dark_edit.png'))
        driver.execute_script('document.documentElement.classList.remove("dark")')

        # ── 6. Network 取证：resource timing 里 GET /spl/{id} 与 POST /spl ──
        perfs = driver.execute_script(
            'return performance.getEntriesByType("resource").map(e => ({name: e.name, dur: e.duration}))')
        with open(os.path.join(OUT_DIR, 'network.json'), 'w', encoding='utf-8') as fh:
            json.dump(perfs, fh, ensure_ascii=False, indent=1)
        spl_reqs = [p for p in perfs if '/spl' in p['name'] and ('api/v1/spl' in p['name'])]
        print('SPL_NETWORK_COUNT', len(spl_reqs), flush=True)
        for p in spl_reqs[-6:]:
            print('  ', p['name'][-60:], round(p['dur'], 1), 'ms', flush=True)

        # ── 7. 删除测试映射 ──
        del_r = httpx.delete(f'{API}/api/v1/spl/{created_id}', headers=headers, timeout=10)
        print('DELETE_SPL', del_r.status_code, flush=True)

        print('PASS', flush=True)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
