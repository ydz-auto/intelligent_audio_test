# -*- coding: utf-8 -*-
"""INT-1643：补 ① 导出真实下载落盘（按钮文案「开始导出」）+ 导出网关层 502；
② 噪声子弹窗「选择噪声音频」的加载态 / 502 失败态 / 重试后空态。一次会话做完。"""
import glob
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

L.BASE = 'http://127.0.0.1:15933'
FLAGS = r'D:\00_user_data\tmp\int1643_nginx\flags'
DL = os.path.join(L.ART, 'downloads')
os.makedirs(DL, exist_ok=True)
GROUP = '打断与恢复'
RESULT = {'stages': {}, 'shots': []}


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.4):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception as e:
            last = e
        time.sleep(interval)
    if last:
        raise last
    return None


def shot(d, name):
    p = L.shot(d, name)
    RESULT['shots'].append(os.path.basename(p))
    return p


def flag(name, on):
    p = os.path.join(FLAGS, name)
    if on:
        open(p, 'w', encoding='utf-8').write('1')
    else:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def throttle(d, on):
    d.execute_cdp_cmd('Network.enable', {})
    d.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': 2000 if on else 0,
        'downloadThroughput': 400 * 1024 if on else -1,
        'uploadThroughput': 400 * 1024 if on else -1,
        'connectionType': 'cellular3g' if on else 'none'})


def net_log(d, clear=True):
    entries = L.fetch_log(d)
    if clear:
        L.clear_fetch_log(d)
    return [{'method': e.get('method'), 'url': (e.get('url') or '').split('127.0.0.1:15933')[-1][:160],
             'status': e.get('status'),
             'resp': (e.get('resBody') or '')[:200] if (e.get('status') or 200) >= 400 else None}
            for e in entries if '/api/' in (e.get('url') or '')]


def dialogs(d):
    return [e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if vis(e)]


def cur_dialog(d, title, timeout=25):
    def f():
        for e in dialogs(d):
            if title in (e.text or ''):
                return e
        return None
    return retry(f, timeout)


def sub_dialog(d, timeout=25):
    def f():
        for e in dialogs(d):
            if '选择一个噪声音频文件' in (e.text or ''):
                return e
        return None
    return retry(f, timeout)


def click_btn(d, scope, text, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        b = next((x for x in scope.find_elements(By.TAG_NAME, 'button')
                  if vis(x) and (x.text or '').strip() == text), None)
        if b is not None:
            try:
                d.execute_script('arguments[0].click();', b)
                return True
            except Exception:
                time.sleep(0.4)
                continue
        time.sleep(0.4)
    return False


def close_all(d):
    for _ in range(3):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.7)
        for x in dialogs(d):
            for b in x.find_elements(By.TAG_NAME, 'button'):
                if vis(b) and (b.text or '').strip() in ('取消', '关闭'):
                    try:
                        d.execute_script('arguments[0].click();', b)
                    except Exception:
                        pass
                    break
        time.sleep(0.5)


def toasts(d):
    try:
        return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    except Exception:
        return []


def ensure_selected(d, names):
    for n in names:
        cb = retry(lambda: next((c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
                                 if vis(c) and c.get_attribute('aria-label') == '选择 ' + n), None), 20)
        if (cb.get_attribute('aria-checked') or '') != 'true':
            d.execute_script('arguments[0].click();', cb)
            time.sleep(0.4)
    time.sleep(1.2)


def stage_export(d, names):
    data = {'title': '导出真实下载'}
    for f in glob.glob(os.path.join(DL, '*')):
        try:
            os.remove(f)
        except Exception:
            pass
    ensure_selected(d, names)
    try:
        d.execute_cdp_cmd('Browser.setDownloadBehavior',
                          {'behavior': 'allow', 'downloadPath': DL, 'eventsEnabled': True})
        data['dl'] = 'Browser.setDownloadBehavior'
    except Exception as e:
        d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': DL})
        data['dl'] = 'Page.setDownloadBehavior'
    b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                            if vis(x) and (x.text or '').strip() == '导出'), None), 20)
    d.execute_script('arguments[0].click();', b)
    dlg = cur_dialog(d, '导出用例')
    time.sleep(1.5)
    shot(d, 'D1_export_dialog')
    data['dialog_text'] = (dlg.text or '')[:200]
    rb = [e for e in dlg.find_elements(By.CSS_SELECTOR, "input[type='radio']") if vis(e)]
    if len(rb) > 1 and not rb[1].get_attribute('disabled'):
        d.execute_script('arguments[0].click();', rb[1])
        time.sleep(0.6)
        data['scope'] = 'selected'
    else:
        data['scope'] = 'filter'
    data['scope_text'] = (dlg.text or '')[:160]
    L.clear_fetch_log(d)
    ok = click_btn(d, dlg, '开始导出')
    data['click_start_export'] = ok
    time.sleep(1.0)
    shot(d, 'D2_export_loading')
    data['loading_text'] = (dlg.text or '')[-160:]
    files = []
    t0 = time.time()
    while time.time() - t0 < 90:
        files = [f for f in glob.glob(os.path.join(DL, '*')) if os.path.getsize(f) > 0]
        if files:
            break
        time.sleep(2)
    data['net'] = net_log(d)
    time.sleep(2)
    files = [f for f in glob.glob(os.path.join(DL, '*')) if os.path.getsize(f) > 0]
    data['files'] = [{'name': os.path.basename(f), 'size': os.path.getsize(f)} for f in files]
    if files:
        raw = open(files[0], 'rb').read()
        data['head'] = raw[:200].decode('utf-8', 'replace')
        try:
            payload = json.loads(raw.decode('utf-8'))
            cases = (payload.get('data') or {}).get('test_cases') or payload.get('test_cases')
            data['json_ok'] = True
            data['case_count'] = len(cases) if isinstance(cases, list) else None
        except Exception as e:
            data['json_ok'] = 'parse error: %s' % e
        data['toast'] = toasts(d)
        shot(d, 'D3_export_downloaded')
    close_all(d)
    # 502
    try:
        ensure_selected(d, names)
        flag('fail_export', True)
        b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                                if vis(x) and (x.text or '').strip() == '导出'), None), 20)
        d.execute_script('arguments[0].click();', b)
        dlg2 = cur_dialog(d, '导出用例')
        time.sleep(1.2)
        rb2 = [e for e in dlg2.find_elements(By.CSS_SELECTOR, "input[type='radio']") if vis(e)]
        if len(rb2) > 1 and not rb2[1].get_attribute('disabled'):
            d.execute_script('arguments[0].click();', rb2[1])
            time.sleep(0.5)
        L.clear_fetch_log(d)
        click_btn(d, dlg2, '开始导出')
        t0 = time.time()
        got = []
        while time.time() - t0 < 10:
            got = toasts(d)
            if got:
                break
            time.sleep(0.2)
        shot(d, 'E_export_error')
        L.apply_theme(d, 'dark')
        shot(d, 'E_export_error_dark')
        L.apply_theme(d, 'light')
        data['toast_err'] = got
        data['net_fail'] = net_log(d)
        flag('fail_export', False)
        close_all(d)
    except Exception:
        data['error_state_exception'] = traceback.format_exc()[-600:]
        flag('fail_export', False)
    RESULT['stages']['export'] = data
    L.save_evidence('result_fix', RESULT)


def stage_noise(d, names):
    data = {'title': '噪声窗加载/失败/空态'}
    ensure_selected(d, names)
    bar = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == '批量设置噪声'), None), 20)
    d.execute_script('arguments[0].click();', bar)
    time.sleep(2.5)
    dlg = retry(lambda: next((e for e in dialogs(d) if '批量设置噪声' in (e.text or '')), None), 20)
    pick = retry(lambda: next((b for b in dlg.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and '点击选择噪声音频' in (b.text or '')), None), 15)
    # 加载态：限速下打开子弹窗
    flag('fail_audios', True)
    d.execute_script('arguments[0].click();', pick)
    sub = sub_dialog(d, 20)
    time.sleep(3)
    shot(d, 'E_noise_error')
    data['error_text'] = (sub.text or '')[:400]
    data['net_error'] = net_log(d)
    flag('fail_audios', False)
    throttle(d, True)
    rb = retry(lambda: next((b for b in sub.find_elements(By.TAG_NAME, 'button')
                             if vis(b) and '重试' in (b.text or '')), None), 10)
    data['retry_btn'] = rb is not None
    if rb is not None:
        d.execute_script('arguments[0].click();', rb)
        time.sleep(1.2)
        shot(d, 'L_noise_loading')
        data['loading_text'] = (sub.text or '')[:300]
    throttle(d, False)
    time.sleep(6)
    shot(d, 'N_noise_empty')
    data['normal_text'] = (sub.text or '')[:300]
    data['net_retry'] = net_log(d)
    close_all(d)
    RESULT['stages']['noise'] = data
    L.save_evidence('result_fix', RESULT)


def main():
    for n in os.listdir(FLAGS):
        try:
            os.remove(os.path.join(FLAGS, n))
        except Exception:
            pass
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases/by-group')
        t0 = time.time()
        sp = None
        while time.time() - t0 < 240:
            cand = [s for s in d.find_elements(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP) if vis(s)]
            if cand:
                sp = cand[0]
                break
            time.sleep(2)
        d.execute_script('arguments[0].click();', sp)
        t1 = time.time()
        rows = []
        while time.time() - t1 < 240:
            rows = [c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if vis(c)]
            if rows:
                break
            time.sleep(3)
        payload = L.api_json(d, '/testcases?page=1&per_page=3&group_id=31d8cb2d-b349-4187-b7e0-d3f7cadc0d26')[1]
        items = (payload or {}).get('data', {}).get('items', [])
        names = [it['name'] for it in items[:3]]
        try:
            stage_export(d, names)
        except Exception:
            RESULT['stages']['export'] = {'exception': traceback.format_exc()[-900:]}
            L.save_evidence('result_fix', RESULT)
            close_all(d)
        try:
            stage_noise(d, names)
        except Exception:
            RESULT['stages']['noise'] = {'exception': traceback.format_exc()[-900:]}
            L.save_evidence('result_fix', RESULT)
            close_all(d)
    finally:
        for n in os.listdir(FLAGS):
            try:
                os.remove(os.path.join(FLAGS, n))
            except Exception:
                pass
        try:
            throttle(d, False)
        except Exception:
            pass
        d.quit()
        print('DONE')


if __name__ == '__main__':
    main()
