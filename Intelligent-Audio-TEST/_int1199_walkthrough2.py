# -*- coding: utf-8 -*-
"""INT-1199 真实库走查·旧Vue·音频设备域 —— 浏览器实测脚本 v2（连真实库栈 5700，前端 5411）。

登录 → 逐页截图（浅色）+ performance Network 证据 + 模态窗截图 + 真实数据核对。
只读为主；写操作仅「接线测试」前缀。输出 _int1199_shots_v2/。
"""
import json
import os
import time
import sys

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = 'http://127.0.0.1:5411'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int1199_shots_v2')
os.makedirs(OUT, exist_ok=True)

DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'

REPORT = {'pages': {}, 'api_calls': []}


def new_driver(block_api=False):
    opts = webdriver.ChromeOptions()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1000')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
    d.set_window_size(1600, 1000)
    d.execute_cdp_cmd('Network.enable', {})
    if block_api:
        d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api/v1*', '*socket.io*']})
    return d


def wait_any(driver, selectors, timeout=30):
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


def drain_api_calls(driver, page):
    """读 performance log 里的 Network.requestWillBeSent，抽 /api/ 调用。读后清空缓冲。"""
    calls = []
    try:
        logs = driver.get_log('performance')
        for l in logs:
            try:
                msg = json.loads(l['message'])
            except Exception:
                continue
            m = msg.get('message', {})
            if m.get('method') != 'Network.requestWillBeSent':
                continue
            url = m.get('params', {}).get('request', {}).get('url', '')
            if '/api/' in url or '/socket.io' in url:
                calls.append(url)
    except Exception as e:
        print('  [perf-log err]', e)
    REPORT['api_calls'].append({'page': page, 'calls': calls})
    print(f'[{page}] api calls ({len(calls)}):')
    for c in calls[:30]:
        print('   ', c.replace(BASE, ''))
    return calls


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
    print('after login route:', driver.current_url)
    shot(driver, '00_after_login.png')
    return driver.current_url


def go(driver, route):
    driver.get(BASE + '/#/' + route)
    time.sleep(2)


def js_text(driver, sel):
    return driver.execute_script("const e=document.querySelector(arguments[0]); return e?e.innerText.trim():'';", sel)


# ── 1. AudioImport ──────────────────────────────────────────
def walk_audio_import(driver):
    go(driver, 'AudioImport')
    wait_any(driver, ['.audio-import-view', '.audio-content-card', '.data-table'], 40)
    time.sleep(3)
    calls = drain_api_calls(driver, 'AudioImport')
    # rows in the audio table
    rows = driver.execute_script(
        "return document.querySelectorAll('.data-table tbody tr').length "
        "+ document.querySelectorAll('.audio-list-component tbody tr').length "
        "+ document.querySelectorAll('.audio-table tbody tr').length;"
    )
    # total text
    total_text = ''
    for sel in ['.total-count', '.count-info', '.audio-count', '.audio-list-component .total-count']:
        t = js_text(driver, sel)
        if t:
            total_text = t
            break
    # pagination
    has_pagination = bool(driver.find_elements(By.CSS_SELECTOR, '.pagination-container, .pagination, .el-pagination'))
    # 分类/格式/时长/采样率列
    headers = driver.execute_script(
        "return Array.from(document.querySelectorAll('.data-table thead th, .audio-table thead th')).map(e=>e.innerText.trim());"
    )
    print('[AudioImport] rows:', rows, 'total:', total_text, 'pagination:', has_pagination)
    print('[AudioImport] headers:', headers)
    shot(driver, '10_audioimport_list.png')
    REPORT['pages']['AudioImport'] = {
        'rows_rendered': rows,
        'total_text': total_text,
        'pagination': has_pagination,
        'headers': headers,
        'api_list_called': any('/api/v1/audios' in c for c in calls),
        'api_audios_urls': [c for c in calls if '/audios' in c][:5],
    }
    # 分类列核对（干声/噪声/提示词）
    try:
        type_cols = driver.execute_script(
            "return Array.from(document.querySelectorAll('.data-table tbody tr .audio-type, .audio-type-badge, .type-badge')).map(e=>e.innerText.trim()).slice(0,10);"
        )
        print('[AudioImport] type badges:', type_cols)
        REPORT['pages']['AudioImport']['type_badges'] = type_cols
    except Exception as e:
        print('type badges err:', e)

    # 空态（搜索无结果）
    try:
        inp = driver.find_element(By.CSS_SELECTOR, '.search-input')
        inp.clear()
        inp.send_keys('__no_such_audio_zzz_9527__')
        time.sleep(2.5)
        empty_ok = wait_any(driver, ['.empty-state', '.no-data', '.no-data-text', '.table-empty'], 15)
        shot(driver, '11_audioimport_empty_search.png')
        REPORT['pages']['AudioImport']['empty_state'] = 'ok' if empty_ok else 'no-empty-state-seen'
        inp.clear()
        time.sleep(2)
    except Exception as e:
        print('empty state search failed:', e)
        REPORT['pages']['AudioImport']['empty_state'] = 'err: ' + str(e)

    # 上传模态窗
    try:
        driver.execute_script("document.querySelector('.audio-import-view .btn-primary, .audio-import-view button.btn-primary').click()")
        wait_any(driver, ['.upload-file-modal', '.drop-zone', '.upload-modal'], 15)
        time.sleep(1.5)
        shot(driver, '12_audioimport_upload_modal.png')
        REPORT['pages']['AudioImport']['upload_modal'] = 'ok'
    except Exception as e:
        print('upload modal open failed:', e)
        REPORT['pages']['AudioImport']['upload_modal'] = 'err: ' + str(e)
    # 关闭模态
    try:
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
        time.sleep(0.8)
    except Exception:
        pass

    # 播放试听（若有）
    try:
        play_btn = driver.find_elements(By.CSS_SELECTOR, '.play-btn, .btn-play, .audio-play-btn, .play-icon')
        if play_btn:
            play_btn[0].click()
            time.sleep(2)
            shot(driver, '13_audioimport_playback.png')
            REPORT['pages']['AudioImport']['playback'] = 'ok'
        else:
            REPORT['pages']['AudioImport']['playback'] = 'no-play-btn'
    except Exception as e:
        REPORT['pages']['AudioImport']['playback'] = 'err: ' + str(e)


# ── 2. Device ───────────────────────────────────────────────
def walk_device(driver):
    go(driver, 'Device')
    wait_any(driver, ['.device-view', '.device-type-tabs'], 40)
    time.sleep(3)
    calls = drain_api_calls(driver, 'Device')
    tabs = [t.text.strip() for t in driver.find_elements(By.CSS_SELECTOR, '.device-type-tabs .tab-btn')]
    stats = driver.find_elements(By.CSS_SELECTOR, '.stats-grid .stat-card')
    stat_texts = [s.text.strip().replace('\n', '=') for s in stats]
    print('[Device] tabs:', tabs)
    print('[Device] stat cards:', stat_texts)
    # 当前 tab 卡片
    cards = driver.execute_script(
        "return document.querySelectorAll('#testDeviceContent .device-card, #testDeviceContent .device-card-item, "
        "#testDeviceContent [class*=\"device-card\"]').length;"
    )
    print('[Device] test tab device cards:', cards)
    shot(driver, '20_device_test_tab.png')
    # 卡片预览内容
    preview = driver.execute_script(
        "return Array.from(document.querySelectorAll('#testDeviceContent .device-card, #testDeviceContent .device-card-item')).map(e=>e.innerText.trim().split('\\n').slice(0,5)).slice(0,5);"
    )
    print('[Device] test cards preview:', json.dumps(preview, ensure_ascii=False)[:600])
    REPORT['pages']['Device'] = {
        'tabs': tabs,
        'stat_cards': stat_texts,
        'test_cards': len(cards),
        'test_cards_preview': preview,
        'api_list_called': any('/api/v1/test-devices' in c for c in calls),
        'api_urls': [c for c in calls if '/device' in c or '/test-devices' in c or '/playback' in c][:8],
    }

    # API tab
    try:
        tab_btns = driver.find_elements(By.CSS_SELECTOR, '.device-type-tabs .tab-btn')
        for b in tab_btns:
            if 'API' in b.text or 'api' in b.text.lower():
                b.click()
                break
        time.sleep(2.5)
        shot(driver, '21_device_api_tab.png')
        REPORT['pages']['Device']['api_tab'] = 'ok'
    except Exception as e:
        REPORT['pages']['Device']['api_tab'] = 'err: ' + str(e)
    # 切回 TEST tab
    try:
        tab_btns = driver.find_elements(By.CSS_SELECTOR, '.device-type-tabs .tab-btn')
        for b in tab_btns:
            if '测试设备' in b.text:
                b.click()
                break
        time.sleep(2)
    except Exception:
        pass

    # 添加设备模态窗
    try:
        driver.execute_script("document.querySelector('.device-view .btn-primary').click()")
        wait_any(driver, ['.device-form-modal', '.device-form', '.modal-content', '.device-modal'], 15)
        time.sleep(1.5)
        shot(driver, '22_device_add_modal.png')
        REPORT['pages']['Device']['add_modal'] = 'ok'
    except Exception as e:
        print('add modal open failed:', e)
        REPORT['pages']['Device']['add_modal'] = 'err: ' + str(e)
    # 关闭模态
    try:
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
        time.sleep(1)
    except Exception:
        pass

    # 分组管理
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, '.device-view .btn-secondary')
        for b in btns:
            if '分组管理' in b.text:
                driver.execute_script("arguments[0].click()", b)
                break
        wait_any(driver, ['.device-group-manager', '.group-manager-modal', '.group-tree'], 15)
        time.sleep(1.5)
        shot(driver, '23_device_group_manager.png')
        REPORT['pages']['Device']['group_manager'] = 'ok'
    except Exception as e:
        print('group manager open failed:', e)
        REPORT['pages']['Device']['group_manager'] = 'err: ' + str(e)
    # 关闭
    try:
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
        time.sleep(0.8)
    except Exception:
        pass


# ── 3. SPLMapping ───────────────────────────────────────────
def walk_spl_mapping(driver):
    go(driver, 'SPLMapping')
    wait_any(driver, ['.spl-mapping-view', '.spl-domain-tabs'], 40)
    time.sleep(3)
    calls = drain_api_calls(driver, 'SPLMapping')
    stats = driver.find_elements(By.CSS_SELECTOR, '.spl-mapping-view .stats-grid .stat-card')
    stat_texts = [s.text.strip().replace('\n', '=') for s in stats]
    print('[SPLMapping] stat cards:', stat_texts)
    rows = driver.execute_script(
        "return document.querySelectorAll('.spl-mapping-view table tbody tr, .spl-table tbody tr, .data-table tbody tr').length;"
    )
    print('[SPLMapping] rows:', rows)
    # 行内容
    row_texts = driver.execute_script(
        "return Array.from(document.querySelectorAll('.spl-mapping-view table tbody tr, .spl-table tbody tr, .data-table tbody tr')).map(e=>e.innerText.trim().split('\\n')).slice(0,4);"
    )
    print('[SPLMapping] rows preview:', json.dumps(row_texts, ensure_ascii=False)[:700])
    shot(driver, '30_splmapping_list.png')
    REPORT['pages']['SPLMapping'] = {
        'stat_cards': stat_texts,
        'rows': rows,
        'rows_preview': row_texts,
        'api_list_called': any('/api/v1/spl' in c for c in calls),
        'api_urls': [c for c in calls if '/spl' in c][:8],
    }

    # 添加增益映射模态窗
    try:
        driver.execute_script("document.querySelector('.spl-mapping-view .btn-primary').click()")
        wait_any(driver, ['.spl-modal', '.spl-mapping-modal', '.modal-content', '.gain-modal'], 15)
        time.sleep(1.5)
        shot(driver, '31_splmapping_add_modal.png')
        REPORT['pages']['SPLMapping']['add_modal'] = 'ok'
    except Exception as e:
        print('spl add modal open failed:', e)
        REPORT['pages']['SPLMapping']['add_modal'] = 'err: ' + str(e)
    # 关闭
    try:
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
        time.sleep(0.8)
    except Exception:
        pass


# ── 4. 错误态（独立会话 CDP 拦 /api/v1） ────────────────────
def walk_error_state():
    d = new_driver(block_api=True)
    try:
        login(d)
        for route, sel, name in [
            ('AudioImport', '.audio-import-view', '40_error_audioimport'),
            ('Device', '.device-view', '41_error_device'),
            ('SPLMapping', '.spl-mapping-view', '42_error_splmapping'),
        ]:
            go(d, route)
            time.sleep(3)
            wait_any(d, ['.load-error-state', '.device-error-banner', '.error-banner', '.error-state', '.error-msg'], 20)
            shot(d, name + '.png')
    finally:
        d.quit()
    REPORT['pages']['error_state_check'] = 'done'
    print('[ErrorState] captured 3 pages with blocked API')


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
    with open(os.path.join(OUT, '_int1199_report_v2.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    print('REPORT DONE:', OUT)


if __name__ == '__main__':
    main()
