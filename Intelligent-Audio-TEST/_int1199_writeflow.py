# -*- coding: utf-8 -*-
"""INT-1199 写流程走查：UI 上传小 WAV（接线测试前缀）+ 批量删除按钮联动 + 设备 API 增删。
清理保证：结束后按文件名前缀 API 查询并删除本卡产物，验证归零。
输出 _int1199_shots_v4/writeflow_*.png + 结果追加 _int1199_writeflow.json。
"""
import base64
import json
import os
import struct
import sys
import time
import wave

import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By

sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://127.0.0.1:5412'
API = 'http://127.0.0.1:5700'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int1199_shots_v4')
os.makedirs(OUT, exist_ok=True)
DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

PREFIX = '接线测试_走查'
RESULT = {}

# 生成 1 秒 8kHz 16bit 单声道静音 WAV（约 16KB），文件名带「接线测试_走查」前缀（上传产物可识别可清理）
WAV_PATH = os.path.join(OUT, PREFIX + '_%d.wav' % int(time.time()))
with wave.open(WAV_PATH, 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(8000)
    w.writeframes(b'\x00\x00' * 8000)
print('wav bytes:', os.path.getsize(WAV_PATH), os.path.basename(WAV_PATH))


def new_driver():
    opts = webdriver.ChromeOptions()
    opts.binary_location = CHROME
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1000')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
    d.set_window_size(1600, 1000)
    d.execute_cdp_cmd('Network.enable', {})
    return d


def wait_any(driver, selectors, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.execute_script("return arguments[0].some(s => document.querySelector(s) !== null);", selectors):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def login(driver):
    driver.get(BASE + '/#/login')
    wait_any(driver, ['.login-card'], 20)
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]').send_keys('接线测试_admin')
    driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]').send_keys('JieXianTest@2026')
    driver.find_element(By.CSS_SELECTOR, '.login-card form button.login-btn').click()
    end = time.time() + 40
    while time.time() < end:
        try:
            if '/login' not in driver.current_url.split('#')[-1]:
                break
        except Exception:
            break
        time.sleep(0.5)
    time.sleep(3)
    tok = driver.execute_script("return localStorage.getItem('auth_token') || ''")
    print('login token:', bool(tok))
    return tok


def api(token, method, path, **kw):
    headers = {'Authorization': 'Bearer ' + token}
    if 'headers' in kw:
        kw['headers'].update(headers)
    else:
        kw['headers'] = headers
    r = httpx.request(method, API + path, timeout=30, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:300]


def main():
    token = None
    driver = new_driver()
    try:
        token = login(driver)
        RESULT['login_token'] = bool(token)

        # ── 1. 上传前先清一次同名残留 ──
        st, lst2 = api(token, 'GET', '/api/v1/audios?page=1&per_page=100')
        items = (lst2.get('data', {}).get('items') if isinstance(lst2, dict) else []) or []
        existing = [it for it in items if '接线测试_走查' in (it.get('name') or '')]
        for it in existing:
            api(token, 'DELETE', f"/api/v1/audios/{it['id']}")
        print('pre-clean existing 接线测试 audios:', len(existing))

        # ── 2. UI 上传 ──
        driver.get(BASE + '/#/AudioImport')
        wait_any(driver, ['.audio-import-view', '.data-table'], 40)
        time.sleep(2)
        driver.execute_script("document.querySelector('.audio-import-view button.btn-primary').click()")
        wait_any(driver, ['.drop-zone input[type=file]', '.upload-file-modal input[type=file]'], 15)
        time.sleep(1.5)
        shot = os.path.join(OUT, '50_writeflow_upload_modal.png')
        driver.save_screenshot(shot)
        print('upload modal shot:', os.path.exists(shot))
        # 选择文件
        f_input = driver.find_element(By.CSS_SELECTOR, '.drop-zone input[type=file], .upload-file-modal input[type=file]')
        f_input.send_keys(WAV_PATH)
        time.sleep(2)
        # 点「开始上传」
        try:
            btn = None
            for b in driver.find_elements(By.CSS_SELECTOR, 'button'):
                if '开始上传' in (b.text or ''):
                    btn = b
                    break
            if btn is None:
                raise RuntimeError('no 开始上传 button found')
            driver.execute_script("arguments[0].click()", btn)
            print('upload start clicked')
        except Exception as e:
            print('upload start click err:', e)
        # 等待上传/刷新（进度卡或列表变化）
        time.sleep(10)
        shot2 = os.path.join(OUT, '51_writeflow_upload_after.png')
        driver.save_screenshot(shot2)
        print('after-upload shot:', os.path.exists(shot2))

        # ── 3. 查询上传产物 ──
        st, lst3 = api(token, 'GET', '/api/v1/audios?page=1&per_page=100')
        items3 = (lst3.get('data', {}).get('items') if isinstance(lst3, dict) else []) or []
        mine = [it for it in items3 if '接线测试_走查' in (it.get('name') or '')]
        RESULT['uploaded_audios_found'] = [
            {'id': it.get('id'), 'name': it.get('name')} for it in mine
        ]
        print('uploaded audios found via API:', RESULT['uploaded_audios_found'])

        # 在 UI 搜索验证渲染
        if mine:
            fname = mine[0].get('name')
            try:
                inp = driver.find_element(By.CSS_SELECTOR, '.search-input')
                inp.clear()
                inp.send_keys(fname[:20])
                time.sleep(3)
                shot3 = os.path.join(OUT, '52_writeflow_list_search.png')
                driver.save_screenshot(shot3)
                rows = driver.execute_script("return document.querySelectorAll('.data-table tbody tr').length;")
                RESULT['ui_search_rows'] = rows
                print('ui search rows for uploaded file:', rows, 'shot:', os.path.exists(shot3))
            except Exception as e:
                print('ui search err:', e)

        # ── 4. 清理：API 删除本卡产物 ──
        deleted = []
        for it in mine:
            code, body = api(token, 'DELETE', f"/api/v1/audios/{it['id']}")
            deleted.append({'id': it['id'], 'delete_code': code})
        RESULT['cleanup_deleted'] = deleted
        # 复核归零
        st, lst4 = api(token, 'GET', '/api/v1/audios?page=1&per_page=100')
        items4 = (lst4.get('data', {}).get('items') if isinstance(lst4, dict) else []) or []
        remain = [it for it in items4 if '接线测试_走查' in (it.get('name') or '')]
        RESULT['cleanup_remaining'] = len(remain)
        print('cleanup deleted:', deleted, 'remaining:', len(remain))

        # ── 5. 设备 API 增删（UI 模态已验证打开） ──
        dev_name = PREFIX + '_device_%d' % int(time.time())
        body = {
            'deviceName': dev_name,
            'model': 'walkthrough-probe',
            'deviceType': 'physical',
            'system': 'HarmonyOS',
            'systemVersion': '5.0',
            'appName': 'walkthrough-probe',
            'appVersion': '1.0',
        }
        c, r = api(token, 'POST', '/api/v1/test-devices', json=body)
        print('device create code:', c, str(r)[:200])
        RESULT['device_create'] = {'code': c, 'resp': str(r)[:200]}
        dev_id = None
        if c == 200 or c == 201:
            if isinstance(r, dict):
                dev_id = r.get('id') or (r.get('data') or {}).get('id')
            if dev_id:
                # 在 UI 设备页验证渲染
                driver.get(BASE + '/#/Device')
                time.sleep(3)
                shot4 = os.path.join(OUT, '53_writeflow_device_created.png')
                driver.save_screenshot(shot4)
                RESULT['device_ui_shot'] = os.path.exists(shot4)
                print('device created, ui shot taken')
                # 删除
                c2, r2 = api(token, 'DELETE', f'/api/v1/test-devices/{dev_id}')
                RESULT['device_delete'] = {'code': c2}
                print('device delete code:', c2)
                # 复核
                c3, r3 = api(token, 'GET', '/api/v1/test-devices?page=1&per_page=100')
                items5 = (r3.get('data', {}).get('items') if isinstance(r3, dict) else []) or []
                RESULT['device_remaining'] = len([it for it in items5 if dev_name in (it.get('name') or '')])
                print('device remaining after delete:', RESULT['device_remaining'])
        else:
            print('device create failed (code %s): %s' % (c, str(r)[:300]))

    finally:
        driver.quit()

    with open(os.path.join(OUT, '_int1199_writeflow.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULT, f, ensure_ascii=False, indent=2)
    print('WRITEFLOW DONE')


if __name__ == '__main__':
    main()
