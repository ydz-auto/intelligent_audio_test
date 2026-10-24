# -*- coding: utf-8 -*-
"""INT-1777 复测 P2-1：取消 / 关闭后重开，基础页签表单不残留上次输入。

验收器给的复现：/start-test → 步骤 2「选择设备/API」→「新增 API」/ 卡片「更多操作 → 编辑」
改名称（+最大并发）→ 取消 → 同入口再打开 → 重开应显示已保存值。
本脚本对新增态与编辑态各验一遍，并核对取消/重开期间没有发出写请求。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5381')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1777_p21'
SUFFIX = int(time.time())
NAME_NEW = '不该保存的名字_%d' % SUFFIX

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || 'GET';
  const entry = { url: url, method: method };
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.status = 'ERR';
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL'), name, detail, flush=True)


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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major:
                        drv_path = exe
                except ValueError:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_script_timeout(120)
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return drv


def wait_page(drv, timeout=40):
    WebDriverWait(drv, timeout).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.5)


def login(drv):
    drv.get(BASE + '/login')
    wait_page(drv)
    try:
        uname = WebDriverWait(drv, 12).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        if '/login' not in drv.current_url:
            print('login: already signed in ->', drv.current_url, flush=True)
            return
        raise
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)
    print('login URL:', drv.current_url, flush=True)


def goto_starttest(drv):
    drv.get(BASE + '/start-test?step=1')
    wait_page(drv)
    WebDriverWait(drv, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]")))


def open_new_dialog(drv):
    WebDriverWait(drv, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]"))).click()
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'api-name')))
    time.sleep(0.8)


def set_input(drv, by, value):
    el = WebDriverWait(drv, 10).until(EC.presence_of_element_located(by))
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(value)
    time.sleep(0.3)
    return el.get_attribute('value')


def click_cancel(drv):
    drv.find_element(By.XPATH, "//button[normalize-space(.)='取消']").click()
    time.sleep(1.2)


def dialog_closed(drv):
    return not any(
        e.is_displayed() for e in drv.find_elements(By.XPATH, "//*[@role='dialog']//input[@id='api-name']"))


def api_list(drv):
    return drv.execute_async_script(
        """
        const done = arguments[arguments.length - 1];
        fetch('/api/v1/apis?page=1&page_size=100', {headers: {'Accept': 'application/json'}})
          .then(r => r.json()).then(j => done(j)).catch(e => done({error: String(e)}));
        """
    )


def open_edit(drv, api_name):
    btn = WebDriverWait(drv, 20).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//*[contains(normalize-space(.), '%s')]//button[@aria-label='更多操作'][1]" % api_name)))
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
    time.sleep(0.4)
    btn.click()
    time.sleep(0.8)
    edit = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]")))
    edit.click()
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'api-name')))
    time.sleep(1.2)


def write_requests(drv):
    log = drv.execute_script('return window.__fetchLog || []')
    return [e for e in log if e.get('method') in ('POST', 'PUT', 'PATCH', 'DELETE') and '/apis' in (e.get('url') or '')]


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    try:
        login(drv)
        drv.execute_script(
            "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")
        set_theme(drv, 'light')
        goto_starttest(drv)
        drv.execute_script('window.__fetchLog = [];')

        # ===== 新增态：改名 + 改最大并发 → 取消 → 重开 =====
        open_new_dialog(drv)
        set_input(drv, (By.ID, 'api-name'), NAME_NEW)
        set_input(drv, (By.ID, 'max-process'), '42')
        drv.save_screenshot('%s/00_new_before_cancel.png' % ART)
        click_cancel(drv)
        check('新增态取消后弹窗关闭', dialog_closed(drv))

        open_new_dialog(drv)
        name_val = drv.find_element(By.ID, 'api-name').get_attribute('value')
        max_val = drv.find_element(By.ID, 'max-process').get_attribute('value')
        check('新增态重开名称复位为空', name_val == '', 'value=%r' % name_val)
        check('新增态重开最大并发复位 5', max_val == '5', 'value=%r' % max_val)
        drv.save_screenshot('%s/01_reopen_new_light.png' % ART)
        click_cancel(drv)

        # ===== 编辑态：用真实已有 API，只改不保存 =====
        listing = api_list(drv)
        items = ((listing or {}).get('data') or {}).get('items') or []
        target = next(
            (i for i in items
             if i.get('name') and '接线测试' not in (i.get('name') or '')
             and i.get('algorithm_type') == 'voice_llm'),
            None)
        if target is None:
            check('找到可编辑的既有 API', False, 'items=%d' % len(items))
        else:
            api_name = target['name']
            print('edit target:', api_name, flush=True)
            open_edit(drv, api_name)
            original = drv.find_element(By.ID, 'api-name').get_attribute('value')
            check('编辑态打开回填已保存名称', original == api_name, 'form=%r api=%r' % (original, api_name))
            set_input(drv, (By.ID, 'api-name'), '不该保存的名字_EDIT')
            set_input(drv, (By.ID, 'max-process'), '77')
            click_cancel(drv)
            check('编辑态取消后弹窗关闭', dialog_closed(drv))

            open_edit(drv, api_name)
            name_val = drv.find_element(By.ID, 'api-name').get_attribute('value')
            max_val = drv.find_element(By.ID, 'max-process').get_attribute('value')
            check('编辑态重开名称回到已保存值', name_val == api_name, 'value=%r' % name_val)
            check('编辑态重开最大并发回到已保存值', max_val != '77', 'value=%r' % max_val)
            drv.save_screenshot('%s/02_reopen_edit_light.png' % ART)
            click_cancel(drv)

        writes = write_requests(drv)
        check('取消 / 重开期间无写请求', len(writes) == 0, json.dumps(writes, ensure_ascii=False)[:300])

        # ===== 深色：同一场景截图 =====
        set_theme(drv, 'dark')
        goto_starttest(drv)
        open_new_dialog(drv)
        set_input(drv, (By.ID, 'api-name'), NAME_NEW)
        click_cancel(drv)
        open_new_dialog(drv)
        name_val = drv.find_element(By.ID, 'api-name').get_attribute('value')
        check('深色新增态重开名称复位为空', name_val == '', 'value=%r' % name_val)
        drv.save_screenshot('%s/03_reopen_new_dark.png' % ART)
        click_cancel(drv)
        set_theme(drv, 'light')
    finally:
        drv.quit()

    failed = [r for r in results if not r[1]]
    print('SUMMARY: %d/%d PASS' % (len(results) - len(failed), len(results)), flush=True)
    for name, ok, detail in results:
        if not ok:
            print('FAILED:', name, detail, flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
