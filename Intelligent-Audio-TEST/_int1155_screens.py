# -*- coding: utf-8 -*-
"""INT-1155 个人中心 Access Token 管理区截图脚本（临时取证用，不入提交）。

用法（先起 vite dev 指向常驻后端）：
    cd Intelligent-Audio-TEST/frontend
    VITE_API_TARGET=http://127.0.0.1:15000 npm run dev -- --port 5605
    python _int1155_screens.py --base http://127.0.0.1:5605 --out _int1155_shots
"""
import argparse
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

CHROME_BINARY = os.environ.get('UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
CHROMEDRIVER = os.environ.get(
    'UI_CHROMEDRIVER',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 'e2e_tests', 'selenium', 'drivers', 'chromedriver-win32', 'chromedriver.exe'))


def _chrome_major():
    if os.name != 'nt':
        return 0
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int((winreg.QueryValueEx(k, 'version')[0]).split('.')[0])
    except Exception:
        return 0


def resolve_chromedriver():
    env = os.environ.get('UI_CHROMEDRIVER')
    if env:
        return env
    major = _chrome_major()
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    if os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
        if major:
            same = [exe for ver, exe in cands if ver and ver[0] == major]
            if same:
                return max(same)
        for _, exe in sorted(cands, reverse=True):
            return exe
    return CHROMEDRIVER if os.path.isfile(CHROMEDRIVER) else ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:5605')
    ap.add_argument('--out', default='_int1155_shots')
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1440,1000')
    opts.add_argument('--force-device-scale-factor=1')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    drv_path = resolve_chromedriver()
    service = Service(drv_path) if drv_path else None
    drv = webdriver.Chrome(options=opts, service=service)
    wait = WebDriverWait(drv, 20)
    base = args.base.rstrip('/')

    # 网络证据：在新文档加载前注入 PerformanceObserver（不受 resource timing
    # 默认 250 条缓冲 evict 影响），收集 /api/v1 真实请求到 window.__apiReqs。
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': '''
        window.__apiReqs = window.__apiReqs || [];
        try { window.setResourceTimingBufferSize(5000); } catch (e) {}
        try {
          var obs = new PerformanceObserver(function(list) {
            for (var i = 0; i < list.getEntries().length; i++) {
              var e = list.getEntries()[i];
              if (e.name.indexOf('/api/v1/') >= 0 || e.name.indexOf('/api/option') >= 0) {
                window.__apiReqs.push({
                  name: e.name.replace(/^https?:\\/\\/[^/]+\\/api\\//, '/api/'),
                  dur: Math.round(e.duration),
                  initiator: e.initiatorType
                });
              }
            }
          });
          obs.observe({entryTypes: ['resource']});
        } catch (e) {}
    '''})

    # 登录态注入：仅 auth_user（AUTH_MODE=off 后端按 dev_user 放行，
    # 避免注入假 token 导致 /auth/* 401）
    drv.get(f'{base}/#/login')
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
    except Exception:
        pass
    drv.execute_script(
        'window.localStorage.setItem(arguments[0], arguments[1]);',
        'auth_user', json.dumps({
            'id': 1, 'username': 'admin', 'roleId': 1, 'roleName': '管理员',
            'permissions': ['*'],
        }),
    )
    drv.refresh()
    # AUTH_MODE=off：无 token 直接放行（路由守卫 next()），登录页 refresh 后
    # 仍在 AuthLayout；直接 hash 导航到 /profile 等布局壳渲染。
    time.sleep(1.5)
    drv.get(f'{base}/#/profile')
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.profile-page')))
    time.sleep(1.5)

    # 网络证据：读取注入的 PerformanceObserver 收集到的 /api/v1 真实请求
    drv.execute_cdp_cmd('Network.enable', {})
    drv.refresh()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.token-table, .token-state')))
    time.sleep(3.0)
    net_entries = drv.execute_script('return window.__apiReqs || [];')
    with open(os.path.join(out, 'network.json'), 'w', encoding='utf-8') as fh:
        json.dump(net_entries, fh, ensure_ascii=False, indent=2)
    # 页面诊断（确认 Token 管理区渲染）
    diag = drv.execute_script(
        'return {'
        '  hash: location.hash,'
        '  hasProfile: !!document.querySelector(".profile-page"),'
        '  hasTokenTable: !!document.querySelector(".token-table"),'
        '  hasTokenState: !!document.querySelector(".token-state"),'
        '  tokenRows: document.querySelectorAll(".token-table tbody tr").length,'
        '  hasCreateBtn: !!Array.from(document.querySelectorAll("button")).find(function(b){return b.textContent.indexOf("创建令牌")>=0;}),'
        '  modalCount: document.querySelectorAll(".modal-overlay").length,'
        '  apiEntries: performance.getEntriesByType("resource").filter(function(e){return e.name.indexOf("/api/")>=0;}).length'
        '};'
    )
    with open(os.path.join(out, 'diag.json'), 'w', encoding='utf-8') as fh:
        json.dump(diag, fh, ensure_ascii=False, indent=2)
    logs = drv.get_log('browser')
    with open(os.path.join(out, 'console.log'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(f"[{e['level']}] {e['message']}" for e in logs))

    # 浅色截图
    drv.execute_script("document.documentElement.classList.remove('dark');")
    time.sleep(0.5)
    drv.save_screenshot(os.path.join(out, '1_light_profile_token.png'))

    # 深色截图
    drv.execute_script("document.documentElement.classList.add('dark');")
    time.sleep(0.8)
    drv.save_screenshot(os.path.join(out, '2_dark_profile_token.png'))
    drv.execute_script("document.documentElement.classList.remove('dark');")
    time.sleep(0.5)

    # 创建弹窗：一段态表单 → 二段态明文一次
    try:
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., '创建令牌')]")))
        btn.click()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#at-name')))
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(out, '3_create_modal_form.png'))
        drv.find_element(By.CSS_SELECTOR, '#at-name').send_keys('验收演示令牌')
        scope_boxes = drv.find_elements(By.CSS_SELECTOR, '.scope-option input[type=checkbox]')
        if scope_boxes:
            drv.execute_script('arguments[0].click();', scope_boxes[0])
        submit = drv.find_element(By.CSS_SELECTOR, '.access-token-form .form-actions button[type="submit"]')
        drv.execute_script('arguments[0].click();', submit)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="token-plaintext"]')))
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(out, '4_create_plaintext_once.png'))
        copy_btn = drv.find_elements(By.XPATH, "//div[contains(@class,'token-reveal')]//button[contains(., '复制')]")
        assert copy_btn, '明文复制按钮缺失'
        done = drv.find_element(By.XPATH, "//button[contains(., '我已保存，关闭')]")
        drv.execute_script('arguments[0].click();', done)
        time.sleep(0.8)
    except Exception as e:
        with open(os.path.join(out, 'create_flow.err'), 'w', encoding='utf-8') as fh:
            fh.write(f'{type(e).__name__}: {e}\n')
        drv.save_screenshot(os.path.join(out, '3_create_modal_fail.png'))

    # 编辑弹窗（限定令牌表内）
    try:
        drv.refresh()
        time.sleep(2.5)
        edit_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '.token-table .btn-ghost')))
        edit_btn.click()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#at-edit-name')))
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(out, '5_edit_modal.png'))
        cancel = drv.find_element(By.CSS_SELECTOR, '.access-token-form .form-actions button[type="button"]')
        drv.execute_script('arguments[0].click();', cancel)
        time.sleep(0.5)
    except Exception as e:
        with open(os.path.join(out, 'edit_flow.err'), 'w', encoding='utf-8') as fh:
            fh.write(f'{type(e).__name__}: {e}\n')

    # 删除确认弹窗（限定令牌表内）
    try:
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, '.modal-overlay')))
        del_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '.token-table .btn-ghost-danger')))
        del_btn.click()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.modal-overlay')))
        time.sleep(0.6)
        drv.save_screenshot(os.path.join(out, '6_delete_confirm.png'))
    except Exception as e:
        with open(os.path.join(out, 'delete_flow.err'), 'w', encoding='utf-8') as fh:
            fh.write(f'{type(e).__name__}: {e}\n')

    drv.quit()
    print('DONE ->', out)
    for f in sorted(os.listdir(out)):
        print(' ', f)


if __name__ == '__main__':
    main()
