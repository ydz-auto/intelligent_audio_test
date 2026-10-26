# -*- coding: utf-8 -*-
"""INT-1316 补充验收：toast 计数精确断言 + 删除后详情 400/404 + API 列表无残留。

由测试工程师独立复核，补齐实施者脚本未显式断言的验收点：
  1. toast 精确文案「成功删除 3 个算法」（successCount 与 selected 条数一致）
  2. 删除后 GET /algorithm/definitions/{type} → 400 Algorithm not found（详情 404/400）
  3. API 列表 /algorithm/definitions 不再含这 3 条（不只查 DOM）
  4. 浅/深色截图留证

数据纪律：本 run 自建「接线测试_INT1316复核_」记录，run 结束前删净。
"""
import json
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1316_recheck')

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5316')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

RUN_TAG = time.strftime('%H%M%S')
TYPES = [f'jxcs_recheck_{RUN_TAG}_{i}' for i in range(1, 4)]
NAMES = [f'接线测试_INT1316复核_{RUN_TAG}_{i}' for i in range(1, 4)]


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def _js_click(drv, xpath):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "arguments[0].scrollIntoView({ block: 'center' }); arguments[0].click();", el)
    time.sleep(0.6)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _edit_field(drv, xpath, new_value):
    el = drv.find_element(By.XPATH, xpath)
    tag = el.tag_name.lower()
    proto = 'HTMLTextAreaElement' if tag == 'textarea' else 'HTMLInputElement'
    drv.execute_script(
        "const s = Object.getOwnPropertyDescriptor(window.%s.prototype, 'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));" % proto,
        el, new_value)
    time.sleep(0.6)


def _login(drv):
    _goto(drv, '/login')
    try:
        drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
        _goto(drv, '/login')
    except Exception:
        pass
    WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def _wait_list_ready(drv):
    for _ in range(4):
        try:
            WebDriverWait(drv, 25).until(
                lambda d: d.find_elements(By.XPATH, "//tbody/tr") or d.find_elements(By.XPATH, "//th"))
            return
        except Exception:
            drv.refresh()
            time.sleep(2.0)
    raise AssertionError('算法列表未在 100s 内加载')


def _create_algorithm(drv, type_, name):
    _js_click(drv, "//button[normalize-space()='新建算法']")
    WebDriverWait(drv, 8).until(lambda d: '新建算法' in _body_text(d))
    time.sleep(0.8)
    _edit_field(drv, "//input[@id='algo-type']", type_)
    _edit_field(drv, "//input[@id='algo-name']", name)
    _js_click(drv, "//button[normalize-space()='发布']")
    WebDriverWait(drv, 25).until(lambda d: '算法已创建' in _body_text(d))
    WebDriverWait(drv, 12).until(
        lambda d: '管理算法定义、参数与映射关系' not in _body_text(d))
    time.sleep(1.5)


def _select_row(drv, name):
    _js_click(drv, f"//*[@aria-label='选择算法 {name}']")
    time.sleep(0.4)


def _fetch(drv, script_args):
    """页内 fetch（localStorage token）→ {status, body} 信封。"""
    script = """
        const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
        return fetch(arguments[0], {
          method: arguments[1] || 'GET',
          headers: { 'Authorization': 'Bearer ' + token, 'Accept': 'application/json' },
        }).then(async (r) => {
          let body = '';
          try { body = await r.text(); } catch (e) { body = ''; }
          return JSON.stringify({ status: r.status, body: body.slice(0, 300) });
        });
    """
    return drv.execute_script(script, *script_args)


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    created = []
    try:
        _login(drv)
        _goto(drv, '/AlgorithmConfig')
        _wait_list_ready(drv)

        # 1) 新建 3 个测试算法
        for type_, name in zip(TYPES, NAMES):
            _create_algorithm(drv, type_, name)
            created.append(type_)
            print('created', type_, name)
        _wait_list_ready(drv)
        time.sleep(1.5)

        # 2) 勾选 3 条 → 批量删除
        for name in NAMES:
            _select_row(drv, name)
        _js_click(drv, "//button[normalize-space()='批量删除']")
        WebDriverWait(drv, 8).until(lambda d: '批量删除' in _body_text(d))
        time.sleep(0.5)
        _js_click(drv, "//button[normalize-space()='删除']")
        # 等 toast 出现并稳定
        WebDriverWait(drv, 30).until(
            lambda d: '个算法' in _body_text(d) and ('成功删除' in _body_text(d) or '失败' in _body_text(d)))
        time.sleep(3.0)
        text = _body_text(drv)
        # 精确断言 toast：成功删除 3 个算法（与勾选条数一致）
        m = re.search(r'成功删除 (\d+) 个算法', text)
        assert m, f'toast 未出现「成功删除 N 个算法」，body 片段: {text[:300]}'
        got = int(m.group(1))
        assert got == 3, f'toast 成功数 {got} != 3'
        failed_m = re.search(r'失败 (\d+) 个', text)
        failed = int(failed_m.group(1)) if failed_m else 0
        assert failed == 0, f'toast 失败数 {failed} != 0'
        print('TOAST:', m.group(0), f'失败 {failed} 个')
        drv.save_screenshot(os.path.join(ARTIFACTS, '01_bulk_after_light.png'))

        # 3) API 复核：详情 400/404 not found + 列表无残留
        for t in TYPES:
            detail = json.loads(_fetch(drv, (BASE + f'/api/v1/algorithm/definitions/{t}', 'GET')))
            status = detail['status']
            body = detail['body']
            assert status in (400, 404), f'{t} 详情仍 {status}: {body}'
            assert 'not found' in body.lower() or '不存在' in body, f'{t} 详情 body 非 not found: {body}'
            print(f'detail {t} -> {status} {body[:80]}')
        listing = json.loads(_fetch(drv, (BASE + '/api/v1/algorithm/definitions', 'GET')))
        assert listing['status'] == 200, f'列表请求失败: {listing}'
        list_body = listing['body'].lower()
        for name in NAMES:
            assert name.lower() not in list_body, f'API 列表仍残留 {name}'
        print('API 列表已无 3 条测试记录')

        # 4) 深色截图
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", JSON.stringify("dark"))')
        drv.get(BASE + '/AlgorithmConfig')
        time.sleep(3)
        _wait_list_ready(drv)
        drv.save_screenshot(os.path.join(ARTIFACTS, '02_bulk_after_dark.png'))

        print('SUPPLEMENT INT-1316 PASS')
        return 0
    finally:
        # 兜底清理：仍残留的测试记录逐条单删
        for t in created:
            try:
                res = json.loads(_fetch(drv, (BASE + f'/api/v1/algorithm/definitions/{t}', 'DELETE')))
                print('cleanup', t, res['status'], res['body'][:80])
            except Exception as e:
                print('cleanup', t, 'failed', e)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
