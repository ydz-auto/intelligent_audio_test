# -*- coding: utf-8 -*-
"""INT-607 审计打回#1 复测——全局算法切换器真实数据断链（P1）+ 错误态区分（P3）。

对应 UX 审计 01a14b86 问题清单 P1：导航栏「算法」切换器下拉只显示
「全部算法」+「暂无匹配算法」，真实在线算法「小艺语音大模型」不出现。
返修 commit e8dab1f8：DTO 对齐真实 data.algorithms（{value,name,...}）。

复测点（打回后只测失败项 + 本次修复相关）：
1. P1 · 真实数据链路：dev_user（AUTH_MODE=off，*）打开「算法」切换器下拉，
   断言真实在线算法「小艺语音大模型」渲染出现 + Network/performance 有
   真实 /api/v1/algorithm/options 请求（非 mock）。
2. P1 · 选中写回：点击「小艺语音大模型」→ localStorage iatp:algorithm:v1
   写入 voice_llm，按钮文本收敛为「小艺语音大模型」（审计期望"一次切换全局生效"）。
3. P3 · 错误态区分：CDP 拦 /algorithm/options → 下拉显示「加载失败」+「重试」，
   不再误显示「暂无匹配算法」。
4. 回归 · 权限显隐：device_admin/guest 无 algorithm:read → 整钮隐藏（不改）。

运行：python tests/ui/test_ui_32b_int607_p1_retest.py
REACT_DEV_BASE 环境变量可覆盖（默认 http://localhost:5331）。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5331')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int607_p1_retest')
os.makedirs(ARTIFACTS, exist_ok=True)

AUTH_STORE_KEY = 'iatp:auth:v1'
TOKEN_KEY = 'iatp:auth:token:v1'
ALG_STORE_KEY = 'iatp:algorithm:v1'

# 与 test_ui_32 同源的角色会话（仅取显隐回归需要的角色）
ROLES = {
    'device_admin': {'user_id': 4, 'username': 'device_admin', 'role_name': '设备管理员', 'permissions': [
        'device:read', 'device:create', 'device:update', 'device:delete', 'device:control',
        'playback:read', 'playback:create', 'playback:update', 'playback:delete', 'playback:control',
        'spl:read', 'spl:create', 'spl:update', 'spl:delete', 'spl:test_tone',
        'digital_spl:read', 'digital_spl:create', 'digital_spl:update', 'digital_spl:delete',
        'lab:create', 'lab:update', 'lab:delete',
        'home:read', 'status:read', 'option:read', 'sse:read',
        'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ]},
    'guest': {'user_id': 5, 'username': 'guest', 'role_name': '游客', 'permissions': [
        'report:read', 'report:compare', 'home:read', 'status:read', 'sse:read',
        'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ]},
}


def _user_json(role_key):
    r = ROLES[role_key]
    return {
        'id': str(r['user_id']),
        'username': r['username'],
        'displayName': r['username'],
        'roleName': r['role_name'],
        'permissions': r['permissions'],
    }


def inject_session(driver, role_key):
    payload = json.dumps({'state': {'user': _user_json(role_key)}, 'version': 0})
    driver.execute_script(
        f"localStorage.setItem('{AUTH_STORE_KEY}', {json.dumps(payload)});"
        f"localStorage.removeItem('{TOKEN_KEY}');"
        f"localStorage.removeItem('{ALG_STORE_KEY}');"
    )


def block_urls(driver, urls):
    driver.execute_cdp_cmd('Network.enable', {})
    driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': urls})


def unblock_urls(driver):
    driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})


def set_theme(driver, theme):
    driver.execute_script(f"localStorage.setItem('iatp:theme:v1:mode', '{theme}');")


def wait_ready(driver, timeout=25):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            "return document.querySelector('header nav') != null || document.querySelector('[data-slot=\"sidebar-menu-button\"]') != null"
        )
    )


def open_dashboard(driver, sleep=2.0):
    driver.get(BASE + '/dashboard')
    wait_ready(driver)
    time.sleep(sleep)


def has_switcher(driver):
    try:
        return len(driver.find_elements(By.CSS_SELECTOR,
                                        '[aria-label="切换全局算法"]')) > 0
    except Exception:
        return False


def open_switcher(driver):
    trigger = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '[aria-label="切换全局算法"]'))
    )
    driver.execute_script("arguments[0].click();", trigger)
    time.sleep(1.0)


def dropdown_texts(driver):
    """收集算法切换器 popover-content 里所有可见 option 文本。"""
    try:
        panels = driver.find_elements(By.CSS_SELECTOR, '[data-slot="popover-content"]')
        for panel in panels:
            if '全部算法' in panel.text or '加载失败' in panel.text:
                return [line.strip() for line in panel.text.split('\n') if line.strip()]
    except Exception:
        pass
    return []


def main():
    results = []
    ok_all = True

    def check(name, condition, detail=''):
        nonlocal ok_all
        status = 'PASS' if condition else 'FAIL'
        if not condition:
            ok_all = False
        print(f'[{status}] {name} {detail}')
        results.append((status, name, detail))

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1440,900')
    options.add_argument('--hide-scrollbars')
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 900)

    try:
        # ========== 0. 前置：真实 /algorithm/options 响应 ==========
        import urllib.request
        try:
            with urllib.request.urlopen(
                    BASE + '/api/v1/algorithm/options', timeout=10) as resp:
                api_body = resp.read().decode('utf-8')
            api_ok = '"voice_llm"' in api_body and '小艺语音大模型' in api_body
            check('前置：真实 GET /algorithm/options 含 voice_llm', api_ok,
                  f'body={api_body[:200]}')
        except Exception as e:
            check('前置：真实 GET /algorithm/options 可达', False, str(e))
            api_body = ''

        # ========== 1. P1 · dev_user 打开算法切换器下拉 → 真实算法渲染 ==========
        unblock_urls(driver)
        driver.get(BASE + '/dashboard')
        wait_ready(driver)
        time.sleep(2.5)
        check('P1-前置：dev_user 算法切换器可见', has_switcher(driver))
        open_switcher(driver)
        texts = dropdown_texts(driver)
        check('P1-核心：下拉渲染真实在线算法「小艺语音大模型」',
              '小艺语音大模型' in texts, f'下拉项={texts}')
        check('P1-下拉含「全部算法」', '全部算法' in texts, f'下拉项={texts}')
        # 真实请求证据（performance resource entries）
        perf = driver.execute_script(
            "return performance.getEntriesByType('resource').filter(e => e.name.includes('/algorithm/options')).map(e => e.name)"
        )
        check('P1-真实请求：页面发出 /algorithm/options 请求（非 mock）',
              len(perf) > 0, f'entries={perf[:3]}')
        driver.save_screenshot(os.path.join(ARTIFACTS, 'alg_dropdown_light.png'))

        # 深色
        set_theme(driver, 'dark')
        open_dashboard(driver)
        open_switcher(driver)
        texts_dark = dropdown_texts(driver)
        check('P1-深色下拉同样渲染真实算法', '小艺语音大模型' in texts_dark,
              f'下拉项={texts_dark}')
        driver.save_screenshot(os.path.join(ARTIFACTS, 'alg_dropdown_dark.png'))
        set_theme(driver, 'light')

        # ========== 2. P1 · 选中写回 useAlgorithmStore（localStorage） ==========
        open_dashboard(driver)
        open_switcher(driver)
        # 点击「小艺语音大模型」选项
        opt = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(.,'小艺语音大模型')]")))
        driver.execute_script("arguments[0].click();", opt)
        time.sleep(1.0)
        stored = driver.execute_script(f"return localStorage.getItem('{ALG_STORE_KEY}');")
        check('P1-选中写回：iatp:algorithm:v1 含 voice_llm',
              stored is not None and 'voice_llm' in stored, f'localStorage={stored}')
        # 按钮收敛显示
        btn = driver.find_element(By.CSS_SELECTOR, '[aria-label="切换全局算法"]')
        check('P1-按钮文本收敛为「小艺语音大模型」',
              '小艺语音大模型' in btn.text, f'按钮={btn.text!r}')

        # ========== 3. P3 · 错误态区分（拦 /algorithm/options → 加载失败+重试） ==========
        block_urls(driver, ['*algorithm/options*'])
        open_dashboard(driver)
        open_switcher(driver)
        texts_err = dropdown_texts(driver)
        check('P3-错误态：显示「加载失败」而非「暂无匹配算法」',
              '加载失败' in texts_err, f'下拉项={texts_err}')
        has_retry = False
        try:
            has_retry = len(driver.find_elements(By.XPATH,
                                                 "//button[contains(.,'重试')]")) > 0
        except Exception:
            pass
        check('P3-错误态：提供「重试」入口', has_retry)
        unblock_urls(driver)
        open_dashboard(driver)

        # ========== 4. 回归 · 权限显隐（device_admin/guest 无 algorithm:read） ==========
        for role_key in ('device_admin', 'guest'):
            inject_session(driver, role_key)
            block_urls(driver, ['*auth/me*'])
            open_dashboard(driver)
            check(f'回归-{role_key}：算法切换器整钮隐藏',
                  not has_switcher(driver))
        unblock_urls(driver)

        # ========== 汇总 ==========
        passed = sum(1 for s, _, _ in results if s == 'PASS')
        failed = sum(1 for s, _, _ in results if s == 'FAIL')
        print(f'\n==== INT-607 P1 复测：{passed} 通过 / {failed} 失败 ====')
        for s, name, detail in results:
            print(f'  [{s}] {name}')
    finally:
        driver.quit()
    return ok_all


if __name__ == '__main__':
    import sys
    ok = main()
    sys.exit(0 if ok else 1)
