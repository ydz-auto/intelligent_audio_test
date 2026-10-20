# -*- coding: utf-8 -*-
"""INT-1005 运行时验证：任务导出弹窗错误态（client.ts blob 分支 response.ok 修复后）。

场景（2026-10-20 实况）：共享 5000 栈已于 INT-1016 重启，task_service 带
filter_visible_task_ids，POST /data-transfer/export 对正常任务返回 200 + zip，
「陈旧 task_service 自然 400」不再可复现。为仍以真实网络 400 复测错误路径，
本脚本改为：API 建一条「接线测试_int1005_*」任务 → UI 勾选并打开导出弹窗 →
API 删除该任务 → 点击「开始导出」发送已删除 id → 后端真实返回 HTTP 400 +
JSON {"message":"任务不存在或已删除: [...]"}。

修复后应：
- 调用方拿到 rejected（Error.message = 后端 message）
- 页面显示 .dt-error（后端 message），弹窗保持打开
- 不下载损坏 zip（不触发 URL.createObjectURL / 不 emit exported / 不关弹窗）

证据：浅/深色截图 + fetch 录制（__reqs 含 export→400）+ console。
"""
import json
import os
import re
import sys
import time

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils'))
from api_client import ApiClient  # noqa: E402

FRONTEND = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5605')
API_ROOT = os.environ.get('UI_API_BASE', 'http://127.0.0.1:5000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1005_export_error')
os.makedirs(ARTIFACT_DIR, exist_ok=True)


def chrome_major():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def resolve_driver():
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    if os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
        major = chrome_major()
        if major:
            same = [exe for ver, exe in cands if ver and ver[0] == major]
            if same:
                return max(same)
        if cands:
            return sorted(cands)[-1][1]
    return ''


FETCH_RECORDER = r"""
window.__reqs = [];
window.__downloads = [];
const _origFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const url = typeof args[0] === 'string' ? args[0] : (args[0].url || String(args[0]));
  const opts = args[1] || {};
  const rec = { method: (opts.method || 'GET'), url, status: null, ok: false, bodyPreview: null, ts: Date.now() };
  try {
    const resp = await _origFetch(...args);
    rec.status = resp.status;
    rec.ok = resp.ok;
    try {
      const ct = resp.headers.get('content-type') || '';
      if (ct.includes('json')) {
        const cloned = resp.clone();
        const j = await cloned.json();
        rec.bodyPreview = (j && (j.message || j.detail)) || '';
      }
    } catch (e) {}
    return resp;
  } catch (e) {
    rec.error = String(e && e.message || e);
    throw e;
  } finally {
    window.__reqs.push(rec);
  }
};
const _origURL = window.URL.createObjectURL.bind(window.URL);
window.URL.createObjectURL = (obj) => {
  window.__downloads.push({ ts: Date.now(), type: obj && obj.type, size: obj && obj.size });
  return _origURL(obj);
};
window.__fetchInstalled = true;
"""


def create_test_task(api: ApiClient) -> dict:
    """建一条「接线测试_int1005_*」任务，返回 {'id':..., 'name':...}。"""
    stamp = time.strftime('%H%M%S')
    name = f'接线测试_int1005_{stamp}'
    headers = {'Authorization': 'Bearer ' + api.token}
    r = httpx.post(f'{API_ROOT}/api/v1/tasks', headers=headers,
                   json={'name': name, 'description': 'int1005 error-path probe'}, timeout=30)
    r.raise_for_status()
    task_id = r.json()['data']['id']
    print(f'已创建测试任务: {name} (id={task_id})')
    return {'id': task_id, 'name': name}


def delete_test_task(api: ApiClient, task_id) -> None:
    """API 删除任务（模拟导出请求发出前任务已被删除的真实竞态）。"""
    headers = {'Authorization': 'Bearer ' + api.token}
    r = httpx.delete(f'{API_ROOT}/api/v1/tasks/{task_id}', headers=headers, timeout=30)
    r.raise_for_status()
    print(f'已删除测试任务 id={task_id}')


def main():
    api = ApiClient(API_ROOT)
    api.login('admin', 'admin123')
    token = api.token
    user = api.user

    task = create_test_task(api)

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    drv_path = resolve_driver()
    service = Service(executable_path=drv_path) if drv_path else Service()
    driver = webdriver.Chrome(options=options, service=service)
    driver.set_page_load_timeout(45)
    wait = WebDriverWait(driver, 20)
    long_wait = WebDriverWait(driver, 60)

    try:
        # ── 登录态注入 ──
        driver.get(f'{FRONTEND}/#/login')
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
        payload = {
            'id': user.get('id', 0),
            'username': user.get('username', ''),
            'roleId': user.get('role_id'),
            'roleName': user.get('role_name', ''),
            'permissions': user.get('permissions', []),
        }
        driver.execute_script(
            'window.localStorage.setItem(arguments[0], arguments[1]);'
            'window.localStorage.setItem(arguments[2], arguments[3]);',
            'auth_token', token, 'auth_user', json.dumps(payload),
        )
        driver.refresh()
        time.sleep(1)

        # ── 任务页：找到本脚本刚建的任务并勾选 ──
        driver.get(f'{FRONTEND}/#/Tasks')
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.page-title')))
        except Exception:
            pass
        task_card = None
        for attempt in range(3):
            try:
                long_wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.task-checkbox')))
                cards = driver.find_elements(By.CSS_SELECTOR, '.task-card')
                for c in cards:
                    title = c.find_elements(By.CSS_SELECTOR, '.task-title')
                    if title and title[0].get_attribute('textContent').strip() == task['name']:
                        task_card = c
                        break
                if task_card is not None:
                    break
            except Exception:
                driver.refresh()
                time.sleep(2)
        if task_card is None:
            raise RuntimeError(f'未在任务列表找到本卡任务 {task["name"]!r}')
        task_card.find_element(By.CSS_SELECTOR, '.task-checkbox').click()
        time.sleep(0.5)

        # ── 安装 fetch/download 录制器（页面加载后注入）──
        driver.execute_script(FETCH_RECORDER)

        # ── 打开导出弹窗 ──
        driver.find_element(By.XPATH, "//button[contains(normalize-space(.), '导出数据')]").click()
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.dt-dialog-overlay .dt-dialog')))
        print('导出弹窗已打开')

        # ── 弹窗打开后、点击导出前，用 API 删除该任务（真实 400 前置条件）──
        delete_test_task(api, task['id'])

        # ── 点击「开始导出」→ 后端真实返回 HTTP 400 + JSON 错误体 ──
        driver.find_element(By.CSS_SELECTOR, '.dt-btn-primary').click()

        # ── 等待 .dt-error 出现 ──
        err_el = long_wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '.dt-error')))
        err_text = err_el.text.strip()
        print(f'.dt-error 文案: {err_text[:120]!r}')

        # ── 断言 ──
        assert '任务不存在或已删除' in err_text, f'错误文案未含后端 message: {err_text!r}'
        dialog_open = driver.find_elements(By.CSS_SELECTOR, '.dt-dialog-overlay .dt-dialog')
        assert dialog_open, '导出弹窗被关闭（不应 emit exported / close）'
        print('弹窗保持打开 ✓')
        dl = driver.execute_script('return window.__downloads;')
        print(f'createObjectURL 调用数: {len(dl)}')
        assert len(dl) == 0, f'错误路径仍触发了下载: {dl}'

        reqs = driver.execute_script('return window.__reqs;')
        export_reqs = [r for r in reqs if 'data-transfer/export' in r['url']]
        assert export_reqs, '未捕获到 export 请求'
        last = export_reqs[-1]
        print(f"export 请求: {last['method']} {last['url']} → HTTP {last['status']} body={last['bodyPreview'][:120]!r}")
        assert last['status'] == 400, f'expect 400, got {last["status"]}'

        # ── 浅色截图 ──
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'light_error.png'))
        print('浅色截图已存')

        # ── 切深色：重新导出 → 深色截图 ──
        driver.find_element(By.CSS_SELECTOR, '.theme-switcher [title="切换为深色"]').click()
        wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@class,'theme-option') and contains(., '深色')]")))
        driver.find_element(
            By.XPATH, "//button[contains(@class,'theme-option') and contains(., '深色')]").click()
        wait.until(lambda d: d.find_element(By.TAG_NAME, 'html').get_attribute('class').__contains__('dark'))
        time.sleep(0.5)
        # 深色下再触发一次导出（任务仍为已删除，弹窗仍打开）
        driver.find_element(By.CSS_SELECTOR, '.dt-btn-primary').click()
        long_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.dt-error')))
        time.sleep(0.5)
        driver.save_screenshot(os.path.join(ARTIFACT_DIR, 'dark_error.png'))
        print('深色截图已存')

        dl2 = driver.execute_script('return window.__downloads;')
        reqs2 = driver.execute_script('return window.__reqs;')
        export2 = [r for r in reqs2 if 'data-transfer/export' in r['url']][-1]
        print(f'深色 export: HTTP {export2["status"]}, downloads={len(dl2)}')
        assert export2['status'] == 400
        assert len(dl2) == 0

        # ── console 日志 ──
        logs = driver.get_log('browser')
        errors = [l for l in logs if l['level'] == 'SEVERE' and 'favicon' not in l['message'].lower()]
        with open(os.path.join(ARTIFACT_DIR, 'console.log'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(f"[{l['level']}] {l['source']}: {l['message']}" for l in logs) or '(no console entries)')
        print(f'console SEVERE 数: {len(errors)}（排除 favicon）')

        # ── 汇总证据文件 ──
        with open(os.path.join(ARTIFACT_DIR, 'network_summary.txt'), 'w', encoding='utf-8') as fh:
            for r in reqs2:
                fh.write(f"{r['method']} {r['url']} → {r['status']} {r.get('bodyPreview', '')[:100]}\n")

        print('\n=== VERIFY PASS ===')
        print(f'证据目录: {ARTIFACT_DIR}')
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
