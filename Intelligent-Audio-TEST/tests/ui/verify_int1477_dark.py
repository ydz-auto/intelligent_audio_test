# -*- coding: utf-8 -*-
"""INT-1477 复走·用例域：深色态补拍（docker 真实栈 15173）。

只跑深色：试听配置/播放器、新增抽屉、音频库选择、批量七窗；每个窗独立 try，
单窗失败不阻塞其余。产出到 tests/ui/artifacts/int1477/。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int1477')
os.makedirs(ART, exist_ok=True)
EVID = []


def log(*a):
    print(*a, flush=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(120)
    return d


def find(d, t, tag='*', exact=True):
    cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
    for e in d.find_elements(By.XPATH, f"//{tag}[{cond}]"):
        if e.is_displayed():
            return e
    return None


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


def click_text(d, t, tag='*', exact=True, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        e = find(d, t, tag, exact)
        if e:
            jsclick(d, e)
            return e
        time.sleep(0.6)
    raise AssertionError('未找到: ' + t)


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('  shot:', name)


def clear_log(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def calls(d):
    reqs, seen = {}, False
    try:
        logs = d.get_log('performance')
    except Exception:
        return []
    for e in logs:
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        p = m.get('params', {})
        if m.get('method') == 'Network.requestWillBeSent':
            r = p['request']
            if '/api/' not in r['url']:
                continue
            seen = True
            reqs[p['requestId']] = {'method': r['method'],
                                    'url': r['url'].split(BASE)[-1],
                                    'status': None,
                                    'post': (r.get('postData') or '')[:300]}
        elif m.get('method') == 'Network.responseReceived':
            if p['requestId'] in reqs:
                reqs[p['requestId']]['status'] = p['response']['status']
    return [v for v in reqs.values() if v['status'] is not None]


def rec(window, note, cs):
    EVID.append({'window': window, 'theme': 'dark', 'note': note, 'calls': cs})
    log(f'  [{window}/dark] {note} | ' + ' ; '.join(
        f"{c['method']} {c['url'].split('?')[0]} -> {c['status']}" for c in cs))


def esc(d, n=2):
    for _ in range(n):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.8)


def wait_dialog(d, frag, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//*[@role='dialog']"):
            if e.is_displayed() and frag in (e.text or ''):
                return e
        time.sleep(0.5)
    raise AssertionError('弹窗未出现: ' + frag)


def main():
    d = driver()
    results = {}
    try:
        d.get(BASE + '/')
        time.sleep(3)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.get(BASE + '/testcases/by-group?d=%d' % int(time.time()))
        # 等首屏
        end = time.time() + 120
        ok = False
        while time.time() < end:
            try:
                b = d.find_element(By.TAG_NAME, 'body').text
            except Exception:
                b = ''
            if '用例管理' in b and '导出' in b:
                ok = True
                break
            time.sleep(1.5)
        if not ok:
            raise AssertionError('页面未就绪')
        time.sleep(2)
        shot(d, '00_page_dark')

        # 展开第一个分组（话轮接管，211 条，首屏即有）
        hdr = d.find_elements(By.XPATH, "//span[normalize-space(.)='话轮接管']")
        if hdr:
            jsclick(d, hdr[0])
            time.sleep(3)

        # 1) 试听配置 + 播放器
        try:
            clear_log(d)
            btns = [e for e in d.find_elements(By.XPATH, "//button[@aria-label='预览音频']") if e.is_displayed()]
            jsclick(d, btns[0])
            wait_dialog(d, '音频试听配置')
            time.sleep(2)
            shot(d, '12_audio_preview_config_dark')
            cs = calls(d)
            click_text(d, '开始试听', 'button')
            time.sleep(2.5)
            shot(d, '13_audio_player_dark')
            cs2 = calls(d)
            rec('audio-preview-config-dialog', '配置态（深色）', cs)
            rec('audio-player-dialog', '播放器态（深色，开始试听后）', cs2)
            results['preview'] = 'ok'
            esc(d)
        except Exception as e:
            results['preview'] = f'FAIL {e}'
            log('  FAIL preview', e)
            esc(d)

        # 2) 新增抽屉 + 音频库选择
        try:
            clear_log(d)
            click_text(d, '新增用例', 'button')
            wait_dialog(d, '新增用例')
            time.sleep(2)
            shot(d, '01_case_mutate_drawer_dark')
            rec('case-mutate-drawer', '新增抽屉（深色）', calls(d))
            results['drawer'] = 'ok'
        except Exception as e:
            results['drawer'] = f'FAIL {e}'
            log('  FAIL drawer', e)

        try:
            clear_log(d)
            click_text(d, '音频列表', 'button')
            time.sleep(1.5)
            click_text(d, '+ 添加音频', 'button')
            wait_dialog(d, '选择音频')
            time.sleep(3)
            shot(d, '02_audio_select_dark')
            rec('audio/audio-select-dialog', '音频库选择（深色）', calls(d))
            results['audio_select'] = 'ok'
        except Exception as e:
            results['audio_select'] = f'FAIL {e}'
            log('  FAIL audio_select', e)
        esc(d, 3)

        # 3) 批量七窗
        bulk = [
            ('批量设置专属参数', '专属参数'),
            ('批量设置播放设备', '播放设备'),
            ('批量设置声压', '声压'),
            ('批量设置噪声', '噪声'),
            ('批量设置评估维度', '评估维度'),
            ('批量调整分组', '调整分组'),
            ('批量管理标签', '管理标签'),
        ]
        try:
            has = [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
                   if e.is_displayed() and (e.get_attribute('aria-label') or '').startswith('全选分组')]
            boxes = [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
                     if e.is_displayed() and (e.get_attribute('aria-label') or '').startswith('选择 ')]
            if boxes:
                jsclick(d, boxes[0])
            elif has:
                jsclick(d, has[0])
            time.sleep(2)
            shot(d, '03_bulk_bar_dark')
            results['bulk_bar'] = 'ok'
        except Exception as e:
            results['bulk_bar'] = f'FAIL {e}'
            log('  FAIL bulk_bar', e)

        for i, (label, frag) in enumerate(bulk):
            try:
                clear_log(d)
                click_text(d, label, 'button')
                time.sleep(2.5)
                shot(d, f'2{i}_bulk_{frag}_dark')
                rec(f'batch-dialog:{label}', '批量弹窗（深色）', calls(d))
                results[label] = 'ok'
                esc(d)
            except Exception as e:
                results[label] = f'FAIL {e}'
                log('  FAIL', label, e)
                esc(d)
    finally:
        try:
            d.quit()
        except Exception:
            pass

    ev = os.path.join(ART, 'evidence.json')
    merged = []
    if os.path.isfile(ev):
        try:
            merged = json.load(open(ev, encoding='utf-8'))
        except Exception:
            merged = []
    merged += EVID
    json.dump(merged, open(ev, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    log('RESULTS', json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
