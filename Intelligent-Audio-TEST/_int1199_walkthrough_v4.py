# -*- coding: utf-8 -*-
"""INT-1199 真实库走查·旧Vue·音频设备域 —— v4 完整交付走查脚本（前端 5412 → 真实库 5700）。

登录 → 三页截图（浅色）+ performance Network 证据 + 模态窗结构 + SPL 两域比对 + 错误态。
只读为主；写操作仅探测模态结构，不做真实写库（真实库数据卫生）。
输出 _int1199_shots_v4/ + _int1199_report_v4.json。
"""
import json
import os
import time

import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By

BASE = 'http://127.0.0.1:5412'
HEALTH = 'http://127.0.0.1:5700/health'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_int1199_shots_v4')
os.makedirs(OUT, exist_ok=True)

DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

REPORT = {'pages': {}, 'api_calls': [], 'health': [], 'spl_crosscheck': {}}


def health_record(label):
    try:
        r = httpx.get(HEALTH, timeout=10).json()
        rec = {'label': label, 'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        rec.update(r)
        REPORT['health'].append(rec)
        print(f'[health:{label}]', r)
        return r
    except Exception as e:
        rec = {'label': label, 'error': str(e)}
        REPORT['health'].append(rec)
        print('[health err]', e)
        return rec


def new_driver(block_api=False):
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
    print('  [shot]', name, os.path.exists(path))
    return path


def drain_api_calls(driver, page):
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
            if '/api/v1/' in url or 'socket.io' in url:
                calls.append(url)
    except Exception as e:
        print('  [perf-log err]', e)
    REPORT['api_calls'].append({'page': page, 'calls': calls})
    print(f'[{page}] api calls ({len(calls)}):')
    for c in calls[:25]:
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
    token = driver.execute_script("return localStorage.getItem('auth_token') || ''")
    print('token present:', bool(token))
    shot(driver, '00_after_login.png')
    return token


def go(driver, route):
    try:
        driver.get_log('performance')
    except Exception:
        pass
    driver.get(BASE + '/#/' + route)
    time.sleep(2)


def js_text(driver, sel):
    return driver.execute_script("const e=document.querySelector(arguments[0]); return e?e.innerText.trim():'';", sel)


def js_count(driver, sel):
    return driver.execute_script("return document.querySelectorAll(arguments[0]).length;", sel)


def js_texts(driver, sel, limit=12):
    return driver.execute_script(
        "return Array.from(document.querySelectorAll(arguments[0])).map(e=>e.innerText.trim()).slice(0,arguments[1]);",
        sel, limit,
    )


def auth_fetch(driver, token, url):
    """浏览器上下文内带 token 的 fetch（跨真实库 5700 由 vite proxy 转发）。异步回调。"""
    script = (
        "const url=arguments[0], token=arguments[1], done=arguments[2];"
        "fetch(url,{headers:{'Authorization':'Bearer '+token}})"
        ".then(r=>r.status===200?r.json():Promise.reject({status:r.status}))"
        ".then(d=>done({ok:true,data:d}))"
        ".catch(e=>done({ok:false,error:e&&e.status?('status='+e.status):'ERR'}));"
    )
    try:
        res = driver.execute_async_script(script, url, token)
        if res and res.get('ok'):
            return res['data']
        return {'fetch_error': (res or {}).get('error') or 'ERR'}
    except Exception as e:
        return {'fetch_error': str(e)}


# ── 1. AudioImport ──────────────────────────────────────────
def walk_audio_import(driver, token):
    go(driver, 'AudioImport')
    wait_any(driver, ['.audio-import-view', '.data-table'], 40)
    time.sleep(3)
    calls = drain_api_calls(driver, 'AudioImport')
    rows = js_count(driver, '.data-table tbody tr')
    total_text = js_text(driver, '.pagination-container')
    has_pagination = bool(driver.find_elements(By.CSS_SELECTOR, '.pagination-container'))
    headers = driver.execute_script(
        "return Array.from(document.querySelectorAll('.data-table thead th')).map(e=>e.innerText.trim());"
    )
    type_badges = js_texts(driver, '.data-table tbody tr .audio-type-badge', 8)
    format_badges = js_texts(driver, '.data-table tbody tr .format-badge', 8)
    durations = js_texts(driver, '.data-table tbody tr td:nth-child(5)', 5)
    # 操作列按钮（预览/编辑/下载/删除）
    row_actions = driver.execute_script(
        "return Array.from(document.querySelectorAll('.data-table tbody tr:first-child td:last-child button, "
        ".data-table tbody tr:first-child .action-col button, .data-table tbody tr:first-child .btn'))"
        ".map(e=>e.innerText.trim()).filter(Boolean);"
    )
    print('[AudioImport] rows:', rows, 'pagination:', has_pagination)
    print('[AudioImport] total:', total_text.replace('\n', ' | ')[:160])
    print('[AudioImport] headers:', json.dumps(headers, ensure_ascii=False))
    print('[AudioImport] type badges:', json.dumps(type_badges, ensure_ascii=False))
    print('[AudioImport] first-row actions:', json.dumps(row_actions, ensure_ascii=False))
    shot(driver, '10_audioimport_list.png')
    REPORT['pages']['AudioImport'] = {
        'rows_rendered': rows,
        'pagination_text': total_text,
        'pagination': has_pagination,
        'headers': headers,
        'type_badges': type_badges,
        'format_badges': format_badges,
        'durations': durations,
        'row_actions': row_actions,
        'api_list_called': any('/api/v1/audios' in c for c in calls),
        'api_urls': [c for c in calls if '/audios' in c][:6],
    }

    # 顶部批量操作按钮
    top_btns = driver.execute_script(
        "return Array.from(document.querySelectorAll('.audio-import-view .action-buttons button'))"
        ".map(e=>e.innerText.trim().replace(/\\n/g,' ')).filter(Boolean);"
    )
    print('[AudioImport] top buttons:', json.dumps(top_btns, ensure_ascii=False))
    REPORT['pages']['AudioImport']['top_buttons'] = top_btns

    # 空态（搜索无结果）
    try:
        inp = driver.find_element(By.CSS_SELECTOR, '.search-input')
        inp.clear()
        inp.send_keys('__no_such_audio_zzz_9527__')
        time.sleep(2.5)
        empty_ok = wait_any(driver, ['.empty-state', '.no-data', '.empty'], 15)
        empty_text = js_text(driver, '.empty-state, .no-data, .empty')
        shot(driver, '11_audioimport_empty_search.png')
        REPORT['pages']['AudioImport']['empty_state'] = 'ok' if empty_ok else 'no-empty-state-seen'
        REPORT['pages']['AudioImport']['empty_state_text'] = empty_text[:200]
        inp.clear()
        time.sleep(2)
    except Exception as e:
        print('empty state search failed:', e)
        REPORT['pages']['AudioImport']['empty_state'] = 'err: ' + str(e)

    # 上传模态窗结构
    try:
        driver.execute_script("document.querySelector('.audio-import-view button.btn-primary').click()")
        wait_any(driver, ['.upload-file-modal', '.drop-zone', '.upload-modal', '.modal-content'], 15)
        time.sleep(1.5)
        shot(driver, '12_audioimport_upload_modal.png')
        modal_text = js_text(driver, '.upload-file-modal, .upload-modal, .modal-content')
        REPORT['pages']['AudioImport']['upload_modal'] = 'ok'
        REPORT['pages']['AudioImport']['upload_modal_text'] = modal_text[:300]
        # 关闭
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn, .modal-close-btn')?.click()")
        time.sleep(0.8)
    except Exception as e:
        print('upload modal open failed:', e)
        REPORT['pages']['AudioImport']['upload_modal'] = 'err: ' + str(e)

    # 播放试听
    try:
        preview_btn = None
        for b in driver.find_elements(By.CSS_SELECTOR, '.data-table tbody tr button'):
            if '预览' in b.text:
                preview_btn = b
                break
        if preview_btn:
            driver.execute_script("arguments[0].click()", preview_btn)
            time.sleep(2.5)
            wait_any(driver, ['.audio-player-modal', '.player-modal', '.audio-player'], 15)
            shot(driver, '13_audioimport_playback.png')
            REPORT['pages']['AudioImport']['playback'] = 'ok'
            try:
                driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
                time.sleep(1)
            except Exception:
                pass
        else:
            REPORT['pages']['AudioImport']['playback'] = 'no-preview-btn'
    except Exception as e:
        REPORT['pages']['AudioImport']['playback'] = 'err: ' + str(e)

    # 直接 fetch 抽样 audios 列表（真实库核对）
    try:
        aud = auth_fetch(driver, token, BASE + '/api/v1/audios?page=1&per_page=5')
        if isinstance(aud, dict) and 'fetch_error' not in aud:
            total = aud.get('total') or aud.get('pagination', {}).get('total')
            items = aud.get('items') or aud.get('audios') or aud.get('data') or []
            REPORT['pages']['AudioImport']['api_total'] = total
            REPORT['pages']['AudioImport']['api_sample_names'] = [a.get('filename') or a.get('name') for a in items][:5]
            print('[AudioImport] api total:', total, 'sample:', REPORT['pages']['AudioImport']['api_sample_names'])
        else:
            REPORT['pages']['AudioImport']['api_total_err'] = str(aud)[:200]
            print('[AudioImport] fetch err:', str(aud)[:200])
    except Exception as e:
        print('[AudioImport] fetch err:', e)


# ── 2. Device ───────────────────────────────────────────────
def walk_device(driver, token):
    go(driver, 'Device')
    wait_any(driver, ['.device-view', '.device-type-tabs'], 40)
    time.sleep(3)
    calls = drain_api_calls(driver, 'Device')
    tabs = [t.text.strip() for t in driver.find_elements(By.CSS_SELECTOR, '.device-type-tabs .tab-btn')]
    stats = driver.find_elements(By.CSS_SELECTOR, '.stats-grid .stat-card')
    stat_texts = [s.text.strip().replace('\n', '=') for s in stats]
    print('[Device] tabs:', json.dumps(tabs, ensure_ascii=False))
    print('[Device] stat cards:', json.dumps(stat_texts, ensure_ascii=False))
    cards = js_count(driver, '#testDeviceContent .device-card, #testDeviceContent .device-card-item')
    preview = driver.execute_script(
        "return Array.from(document.querySelectorAll('#testDeviceContent .device-card, #testDeviceContent .device-card-item'))"
        ".map(e=>e.innerText.trim().split('\\n').slice(0,6)).slice(0,5);"
    )
    print('[Device] test cards:', cards)
    print('[Device] preview:', json.dumps(preview, ensure_ascii=False)[:800])
    shot(driver, '20_device_test_tab.png')
    REPORT['pages']['Device'] = {
        'tabs': tabs,
        'stat_cards': stat_texts,
        'test_cards': cards,
        'test_cards_preview': preview,
        'api_list_called': any('/api/v1/test-devices' in c for c in calls),
        'api_urls': [c for c in calls if '/device' in c or '/test-devices' in c or '/playback' in c][:8],
    }
    # 顶部按钮（添加/扫描/分组管理/批量）
    top_btns = driver.execute_script(
        "return Array.from(document.querySelectorAll('.device-view .header .btn, .device-view .btn-secondary, .device-view .btn-primary, .device-view .dropdown-toggle'))"
        ".map(e=>e.innerText.trim().replace(/\\n/g,' ')).filter(Boolean);"
    )
    REPORT['pages']['Device']['top_buttons'] = top_btns
    print('[Device] top buttons:', json.dumps(top_btns, ensure_ascii=False))

    # API tab
    try:
        tab_btns = driver.find_elements(By.CSS_SELECTOR, '.device-type-tabs .tab-btn')
        for b in tab_btns:
            if 'API' in b.text or 'api' in b.text.lower():
                driver.execute_script("arguments[0].click()", b)
                break
        time.sleep(2.5)
        shot(driver, '21_device_api_tab.png')
        api_rows = js_count(driver, '#apiDeviceContent .device-card, #apiDeviceContent .device-card-item')
        REPORT['pages']['Device']['api_tab'] = 'ok'
        REPORT['pages']['Device']['api_tab_cards'] = api_rows
        print('[Device] api tab cards:', api_rows)
    except Exception as e:
        REPORT['pages']['Device']['api_tab'] = 'err: ' + str(e)
    # 切回 TEST tab
    try:
        for b in driver.find_elements(By.CSS_SELECTOR, '.device-type-tabs .tab-btn'):
            if '测试设备' in b.text:
                driver.execute_script("arguments[0].click()", b)
                break
        time.sleep(2)
    except Exception:
        pass

    # 添加设备模态窗
    try:
        driver.execute_script("document.querySelector('.device-view button.btn-primary').click()")
        wait_any(driver, ['.device-form-modal', '.device-form', '.modal-content', '.device-modal'], 15)
        time.sleep(1.5)
        shot(driver, '22_device_add_modal.png')
        modal_text = js_text(driver, '.device-form-modal, .device-form, .modal-content')
        REPORT['pages']['Device']['add_modal'] = 'ok'
        REPORT['pages']['Device']['add_modal_text'] = modal_text[:300]
        print('[Device] add modal text:', modal_text[:200].replace('\n', ' | '))
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
        time.sleep(1)
    except Exception as e:
        print('add modal open failed:', e)
        REPORT['pages']['Device']['add_modal'] = 'err: ' + str(e)

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
        gp_rows = js_count(driver, '.group-tree .group-node, .group-tree li, .group-tree-item')
        REPORT['pages']['Device']['group_manager'] = 'ok'
        REPORT['pages']['Device']['group_manager_groups'] = gp_rows
        print('[Device] group manager groups:', gp_rows)
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
        time.sleep(0.8)
    except Exception as e:
        print('group manager open failed:', e)
        REPORT['pages']['Device']['group_manager'] = 'err: ' + str(e)

    # 扫描设备按钮存在性（不实际触发广播扫描）
    try:
        scan_btn = None
        for b in driver.find_elements(By.CSS_SELECTOR, '.device-view button'):
            if '扫描' in b.text:
                scan_btn = b
                break
        REPORT['pages']['Device']['scan_button'] = 'present' if scan_btn else 'not-found'
    except Exception:
        REPORT['pages']['Device']['scan_button'] = 'err'

    # 直接 fetch 抽样 devices
    try:
        dv = auth_fetch(driver, token, BASE + '/api/v1/test-devices?page=1&per_page=10')
        if isinstance(dv, dict) and 'fetch_error' not in dv:
            items = dv.get('items') or dv.get('devices') or dv.get('data') or []
            REPORT['pages']['Device']['api_total'] = dv.get('total') or dv.get('pagination', {}).get('total')
            REPORT['pages']['Device']['api_sample'] = [
                {k: (i.get(k) if k in i else None) for k in ('name', 'model', 'status', 'online')}
                for i in items
            ][:5]
            print('[Device] api total:', REPORT['pages']['Device']['api_total'], 'sample:', REPORT['pages']['Device']['api_sample'])
        else:
            REPORT['pages']['Device']['api_total_err'] = str(dv)[:200]
            print('[Device] fetch err:', str(dv)[:200])
    except Exception as e:
        print('[Device] fetch err:', e)


# ── 3. SPLMapping ───────────────────────────────────────────
def walk_spl_mapping(driver, token):
    go(driver, 'SPLMapping')
    wait_any(driver, ['.spl-mapping-view', '.spl-domain-tabs'], 40)
    time.sleep(3)
    calls = drain_api_calls(driver, 'SPLMapping')

    # DEVICE（增益映射）域
    domain_tabs = [t.text.strip() for t in driver.find_elements(By.CSS_SELECTOR, '.spl-domain-tabs .domain-tab-btn')]
    print('[SPLMapping] domain tabs:', json.dumps(domain_tabs, ensure_ascii=False))
    stats = driver.find_elements(By.CSS_SELECTOR, '.spl-mapping-view .stats-grid .stat-card')
    stat_texts = [s.text.strip().replace('\n', '=') for s in stats]
    print('[SPLMapping] stat cards:', json.dumps(stat_texts, ensure_ascii=False))
    cards = js_count(driver, '.spl-mapping-section .mapping-card')
    card_preview = driver.execute_script(
        "return Array.from(document.querySelectorAll('.spl-mapping-section .mapping-card'))"
        ".map(e=>e.innerText.trim().split('\\n').slice(0,10)).slice(0,4);"
    )
    empty_text = js_text(driver, '.spl-mapping-empty')
    loading = js_text(driver, '.spl-mapping-loading')
    print('[SPLMapping] device-tab mapping cards:', cards)
    print('[SPLMapping] empty text:', empty_text[:150])
    print('[SPLMapping] loading text:', loading[:150])
    print('[SPLMapping] card preview:', json.dumps(card_preview, ensure_ascii=False)[:900])
    shot(driver, '30_splmapping_device_tab.png')
    REPORT['pages']['SPLMapping'] = {
        'domain_tabs': domain_tabs,
        'stat_cards': stat_texts,
        'mapping_cards': cards,
        'mapping_cards_preview': card_preview,
        'empty_text': empty_text[:200],
        'loading_text': loading[:200],
        'api_list_called': any('/api/v1/spl' in c for c in calls),
        'api_urls': [c for c in calls if '/spl' in c][:8],
    }

    # 添加增益映射模态窗
    try:
        driver.execute_script("document.querySelector('.spl-mapping-view button.btn-primary').click()")
        wait_any(driver, ['.spl-modal', '.spl-mapping-modal', '.modal-content', '.gain-modal'], 15)
        time.sleep(1.5)
        shot(driver, '31_splmapping_add_modal.png')
        modal_text = js_text(driver, '.spl-modal, .spl-mapping-modal, .modal-content')
        REPORT['pages']['SPLMapping']['add_modal'] = 'ok'
        REPORT['pages']['SPLMapping']['add_modal_text'] = modal_text[:400]
        print('[SPLMapping] add modal text:', modal_text[:250].replace('\n', ' | '))
        driver.execute_script("document.querySelector('.modal-mask, .modal-overlay, .modal-close, .btn-close, .close-btn')?.click()")
        time.sleep(0.8)
    except Exception as e:
        print('spl add modal open failed:', e)
        REPORT['pages']['SPLMapping']['add_modal'] = 'err: ' + str(e)

    # API_RMS 域
    try:
        for b in driver.find_elements(By.CSS_SELECTOR, '.spl-domain-tabs .domain-tab-btn'):
            if 'RMS' in b.text:
                driver.execute_script("arguments[0].click()", b)
                break
        time.sleep(2.5)
        rms_stats = [s.text.strip().replace('\n', '=') for s in driver.find_elements(By.CSS_SELECTOR, '.spl-mapping-view .stats-grid .stat-card')]
        rms_rows = js_count(driver, '.rms-spl-table tbody tr')
        rms_preview = driver.execute_script(
            "return Array.from(document.querySelectorAll('.rms-spl-table tbody tr'))"
            ".map(e=>e.innerText.trim().split('\\n').slice(0,6)).slice(0,3);"
        )
        shot(driver, '32_splmapping_api_rms_tab.png')
        REPORT['pages']['SPLMapping']['rms_stats'] = rms_stats
        REPORT['pages']['SPLMapping']['rms_rows'] = rms_rows
        REPORT['pages']['SPLMapping']['rms_preview'] = rms_preview
        print('[SPLMapping] RMS stats:', json.dumps(rms_stats, ensure_ascii=False))
        print('[SPLMapping] RMS rows:', rms_rows, 'preview:', json.dumps(rms_preview, ensure_ascii=False)[:500])
    except Exception as e:
        print('rms tab switch failed:', e)
        REPORT['pages']['SPLMapping']['rms_tab_err'] = str(e)

    # 跨核对：/spl（增益）与 /spl/stats（设备域）的 stats vs list
    try:
        spl_list = auth_fetch(driver, token, BASE + '/api/v1/spl?page=1&per_page=100')
        spl_stats = auth_fetch(driver, token, BASE + '/api/v1/spl/stats')
        cross = {'spl_list_raw': spl_list, 'spl_stats_raw': spl_stats}
        # 抽摘要
        def brief(x):
            if isinstance(x, dict) and 'fetch_error' not in x:
                items = x.get('items') or x.get('data') or x.get('mappings') or []
                return {'keys': sorted(x.keys())[:10], 'total_field': x.get('total'), 'items_len': len(items) if isinstance(items, list) else 'n/a'}
            return str(x)[:200]
        cross['spl_list_summary'] = brief(spl_list)
        cross['spl_stats_summary'] = brief(spl_stats)
        REPORT['spl_crosscheck'] = cross
        print('[SPL crosscheck] list:', json.dumps(cross['spl_list_summary'], ensure_ascii=False))
        print('[SPL crosscheck] stats:', json.dumps(cross['spl_stats_summary'], ensure_ascii=False))
    except Exception as e:
        REPORT['spl_crosscheck']['err'] = str(e)
        print('[SPL crosscheck] err:', e)


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
    health_record('run-start')
    driver = new_driver()
    try:
        token = login(driver)
        if not token:
            print('!!! login produced no token — aborting walkthrough')
            REPORT['fatal'] = 'no token after login'
        else:
            health_record('pre-screenshots')
            walk_audio_import(driver, token)
            walk_device(driver, token)
            walk_spl_mapping(driver, token)
    finally:
        driver.quit()
    try:
        walk_error_state()
    except Exception as e:
        print('error state session failed:', e)
        REPORT['pages']['error_state_check'] = 'err: ' + str(e)
    health_record('pre-delivery')
    with open(os.path.join(OUT, '_int1199_report_v4.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    print('REPORT DONE:', OUT)


if __name__ == '__main__':
    main()
