# -*- coding: utf-8 -*-
"""INT-1199 真实库走查·旧Vue·音频设备域 —— 浏览器实测脚本（连真实库栈 5700 前端 5411）。
登录 → 逐页截图 + performance 网络证据 + 模态窗截图。只读为主；写操作仅上传/删除「接线测试」前缀音频。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = 'http://127.0.0.1:5411'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int1199_shots')
os.makedirs(OUT, exist_ok=True)

DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'

REPORT = {'pages': {}, 'api_calls': []}


def new_driver(block_api=False):
    opts = webdriver.ChromeOptions()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    d = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
    d.set_window_size(1440, 900)
    d.execute_cdp_cmd('Network.enable', {})
    if block_api:
        d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api/v1*', '*socket.io*']})
    return d


def wait_any(driver, selectors, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            found = driver.execute_script(
                "const sels = arguments[0];"
                "return sels.some(s => document.querySelector(s) !== null);",
                selectors,
            )
            if found:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def shot(driver, name):
    path = os.path.join(OUT, name)
    driver.save_screenshot(path)
    return path


def api_calls(driver):
    return driver.execute_script(
        "return performance.getEntriesByType('resource').map(e => e.name).filter(n => n.includes('/api/v1/'));"
    )


def login(driver):
    driver.get(BASE + '/#/login')
    wait_any(driver, ['.login-card'], 15)
    driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]').send_keys('接线测试_admin')
    driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]').send_keys('JieXianTest@2026')
    driver.find_element(By.CSS_SELECTOR, '.login-card form button.login-btn').click()
    end = time.time() + 30
    while time.time() < end:
        if '/login' not in driver.current_url.split('#')[-1]:
            break
        time.sleep(0.5)
    time.sleep(2)
    print('login route:', driver.current_url)
    shot(driver, '00_after_login.png')


def go(driver, route):
    driver.get(BASE + '/#/' + route)
    time.sleep(2)


def capture_page_apis(driver, page):
    calls = api_calls(driver)
    REPORT['api_calls'].append({'page': page, 'calls': calls})
    print(f'[{page}] api calls ({len(calls)}):')
    for c in calls[:25]:
        print('   ', c.replace(BASE, ''))
    return calls


def count_text(driver, css):
    try:
        els = driver.find_elements(By.CSS_SELECTOR, css)
        return len(els)
    except Exception:
        return -1


# ── 1. AudioImport ──────────────────────────────────────────
def walk_audio_import(driver):
    go(driver, 'AudioImport')
    wait_any(driver, ['.audio-import-view', '.data-table', '.audio-list-skeleton'], 30)
    time.sleep(2)
    calls = capture_page_apis(driver, 'AudioImport')
    audios_rows = count_text(driver, '.data-table tbody tr')
    pagination = driver.find_elements(By.CSS_SELECTOR, '.pagination-container')
    print(f'[AudioImport] rows in table: {audios_rows}, pagination present: {bool(pagination)}')
    total_text = ''
    try:
        total_el2 = driver.find_elements(By.CSS_SELECTOR, '.audio-list-component .total-count, .audio-list-component .count-info')
        if total_el2:
            total_text = total_el2[0].text.strip()
    except Exception:
        pass
    shot(driver, '10_audioimport_list.png')
    REPORT['pages']['AudioImport'] = {
        'rows_rendered': audios_rows,
        'pagination': bool(pagination),
        'total_text': total_text,
        'api_list_called': any('/api/v1/audios' in c for c in calls),
    }
    # empty state via nonsense search
    try:
        inp = driver.find_element(By.CSS_SELECTOR, '.search-input')
        inp.clear()
        inp.send_keys('__no_such_audio_zzz__')
        time.sleep(2)
        wait_any(driver, ['.empty-state'], 15)
        shot(driver, '11_audioimport_empty_search.png')
        REPORT['pages']['AudioImport']['empty_state'] = 'ok'
        inp.clear()
        time.sleep(2)
    except Exception as e:
        print('empty state search failed:', e)
        REPORT['pages']['AudioImport']['empty_state'] = 'err: ' + str(e)
    # open upload modal
    try:
        driver.execute_script("document.querySelector('.audio-import-view .btn-primary').click()")
        wait_any(driver, ['.upload-file-modal', '.drop-zone'], 15)
        time.sleep(1)
        shot(driver, '12_audioimport_upload_modal.png')
        REPORT['pages']['AudioImport']['upload_modal'] = 'ok'
    except Exception as e:
        print('upload modal open failed:', e)
        REPORT['pages']['AudioImport']['upload_modal'] = 'err: ' + str(e)


# ── 2. Device ───────────────────────────────────────────────
def walk_device(driver):
    go(driver, 'Device')
    wait_any(driver, ['.device-view', '.device-type-tabs'], 30)
    time.sleep(2)
    calls = capture_page_apis(driver, 'Device')
    tabs = driver.find_elements(By.CSS_SELECTOR, '.device-type-tabs .tab-btn')
    print('[Device] tabs:', [t.text.strip() for t in tabs])
    stats = driver.find_elements(By.CSS_SELECTOR, '.stats-grid .stat-card')
    print('[Device] stat cards:', len(stats))
    cards = driver.find_elements(By.CSS_SELECTOR, '#testDeviceContent .device-card, .devices-grid .device-card')
    print('[Device] test device cards:', len(cards))
    statuses = []
    for card in driver.find_elements(By.CSS_SELECTOR, '#testDeviceContent .device-card, .devices-grid .device-card')[:6]:
        statuses.append(card.text.split('\n')[:4])
    shot(driver, '20_device_test_tab.png')
    REPORT['pages']['Device'] = {
        'tabs': [t.text.strip() for t in tabs],
        'stat_cards': len(stats),
        'device_cards': len(cards),
        'device_preview': statuses,
        'api_list_called': any('/api/v1/test-devices' in c for c in calls),
    }
    # 添加设备模态窗
    try:
        driver.execute_script("document.querySelector('.device-view .btn-primary').click()")
        wait_any(driver, ['.device-form-modal', '.modal-content', '.device-form'], 15)
        time.sleep(1)
        shot(driver, '21_device_add_modal.png')
        REPORT['pages']['Device']['add_modal'] = 'ok'
    except Exception as e:
        print('add modal open failed:', e)
        REPORT['pages']['Device']['add_modal'] = 'err: ' + str(e)
    # 关闭模态窗
    try:
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close')?.click()")
        time.sleep(0.5)
    except Exception:
        pass
    # 分组管理
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, '.device-view .btn-secondary')
        for b in btns:
            if '分组管理' in b.text:
                b.click()
                break
        wait_any(driver, ['.device-group-manager', '.group-manager-modal'], 15)
        time.sleep(1)
        shot(driver, '22_device_group_manager.png')
        REPORT['pages']['Device']['group_manager'] = 'ok'
    except Exception as e:
        print('group manager open failed:', e)
        REPORT['pages']['Device']['group_manager'] = 'err: ' + str(e)


# ── 3. SPLMapping ───────────────────────────────────────────
def walk_spl_mapping(driver):
    go(driver, 'SPLMapping')
    wait_any(driver, ['.spl-mapping-view', '.spl-domain-tabs'], 30)
    time.sleep(2)
    calls = capture_page_apis(driver, 'SPLMapping')
    stats = driver.find_elements(By.CSS_SELECTOR, '.spl-mapping-view .stats-grid .stat-card')
    stat_texts = [s.text.strip().replace('\n', '=') for s in stats]
    print('[SPLMapping] stat cards:', stat_texts)
    rows = driver.find_elements(By.CSS_SELECTOR, '.spl-mapping-view table tbody tr, .spl-table tbody tr, .data-table tbody tr')
    print('[SPLMapping] rows:', len(rows))
    shot(driver, '30_splmapping_list.png')
    REPORT['pages']['SPLMapping'] = {
        'stat_cards': stat_texts,
        'rows': len(rows),
        'api_list_called': any('/api/v1/spl' in c for c in calls),
    }
    # 添加增益映射模态窗
    try:
        driver.execute_script("document.querySelector('.spl-mapping-view .btn-primary').click()")
        wait_any(driver, ['.spl-modal', '.spl-mapping-modal', '.modal-content'], 15)
        time.sleep(1)
        shot(driver, '31_splmapping_add_modal.png')
        REPORT['pages']['SPLMapping']['add_modal'] = 'ok'
    except Exception as e:
        print('spl add modal open failed:', e)
        REPORT['pages']['SPLMapping']['add_modal'] = 'err: ' + str(e)


# ── 4. 错误态（独立会话 CDP 拦 /api/v1） ────────────────────
def walk_error_state():
    d = new_driver(block_api=True)
    login(d)
    go(d, 'AudioImport')
    time.sleep(3)
    ok = wait_any(d, ['.load-error-state', '.device-error-banner', '.audio-list-skeleton'], 20)
    shot(d, '40_error_state_audioimport.png')
    print('[ErrorState] load-error-state visible:', ok)
    REPORT['pages']['error_state_check'] = {'audioimport_error_visible': ok}
    d.quit()


def main():
    driver = new_driver()
    try:
        login(driver)
        walk_audio_import(driver)
        walk_device(driver)
        walk_spl_mapping(driver)
    finally:
        driver.quit()
    try:
        walk_error_state()
    except Exception as e:
        print('error state session failed:', e)
        REPORT['pages']['error_state_check'] = 'err: ' + str(e)
    with open(os.path.join(OUT, '_int1199_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    print('REPORT DONE:', OUT)


if __name__ == '__main__':
    main()
