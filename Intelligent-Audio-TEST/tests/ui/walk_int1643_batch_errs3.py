# -*- coding: utf-8 -*-
"""INT-1643 返工轮 Part A4（合并重跑）：分组 / 声压 / 评估维度 / 管理标签 / 噪声 五窗的
真实加载态 + 网关层 502 失败态（含 toast 错误文案），以及导出真实下载落盘 + 导出 502。

要点：
- 每次批量动作失败后页面会清空勾选、底部批量条消失 → 每个阶段开始前重新勾选 3 条；
- toast 只在 ~4s 内可见 → 失败态截图在响应返回后 0.4s 内取。
"""
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

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15933')
L.API = 'http://127.0.0.1:15000'

FLAGS = r'D:\00_user_data\tmp\int1643_nginx\flags'
DL = os.path.join(L.ART, 'downloads')
os.makedirs(DL, exist_ok=True)
GROUP = '打断与恢复'
RESULT = {'stages': {}, 'shots': [], 'selected': {}}


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
        with open(p, 'w', encoding='utf-8') as f:
            f.write('1')
    else:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def clear_flags():
    for n in os.listdir(FLAGS):
        try:
            os.remove(os.path.join(FLAGS, n))
        except Exception:
            pass


def throttle(d, on):
    try:
        d.execute_cdp_cmd('Network.enable', {})
        d.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 2000 if on else 0,
            'downloadThroughput': 400 * 1024 if on else -1,
            'uploadThroughput': 400 * 1024 if on else -1,
            'connectionType': 'cellular3g' if on else 'none'})
    except Exception as e:
        print('throttle err', e)


def net_log(d, clear=True):
    entries = L.fetch_log(d)
    if clear:
        L.clear_fetch_log(d)
    keep = []
    for e in entries:
        u = e.get('url') or ''
        if '/api/' in u:
            keep.append({'method': e.get('method'), 'url': u.split('127.0.0.1:15933')[-1][:160],
                         'status': e.get('status'),
                         'resp': (e.get('resBody') or '')[:200] if (e.get('status') or 200) >= 400 else None})
    return keep


def record(stage, data):
    RESULT['stages'][stage] = data
    L.save_evidence('resultA4', RESULT)
    print('STAGE', stage, json.dumps(data, ensure_ascii=False)[:500])


def dialogs(d):
    return [e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if vis(e)]


def cur_dialog(d, title, timeout=25):
    def f():
        for e in dialogs(d):
            if title in (e.text or ''):
                return e
        return None
    return retry(f, timeout)


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


def click_btn(d, scope, text, timeout=20):
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


def toasts(d):
    try:
        return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    except Exception:
        return []


def enter_group(d):
    t0 = time.time()
    sp = None
    while time.time() - t0 < 150:
        cand = [s for s in d.find_elements(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP) if vis(s)]
        if cand:
            sp = cand[0]
            break
        time.sleep(2)
    if sp is None:
        raise RuntimeError('group span not found')
    d.execute_script('arguments[0].click();', sp)
    t1 = time.time()
    rows = []
    while time.time() - t1 < 150:
        rows = [c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if vis(c)]
        if rows:
            break
        time.sleep(3)
    return [c.get_attribute('aria-label') for c in rows]


def ensure_selected(d):
    """批量动作失败后勾选会被清空：重新勾选本卡 3 条。"""
    n = 0
    for name in RESULT['selected'].keys():
        cb = retry(lambda: next((c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
                                 if vis(c) and c.get_attribute('aria-label') == '选择 ' + name), None), 20)
        if (cb.get_attribute('aria-checked') or '') != 'true':
            d.execute_script('arguments[0].click();', cb)
            time.sleep(0.4)
            n += 1
    time.sleep(1.2)
    return n


def open_bulk(d, label):
    bar = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == label), None), 25)
    d.execute_script('arguments[0].click();', bar)
    time.sleep(2.5)


def failure_cycle(d, data, tag, key='fail_batch', pre_delay=0.0):
    """点击确定 → 加载态截图 → 失败态（toast 在 ~4s 内）→ Network。"""
    flag(key, True)
    throttle(d, True)
    L.clear_fetch_log(d)
    return data


def capture_loading_then_error(d, dlg, tag, data, click_first=True, wait_resp=2.8):
    shot(d, 'L_%s_loading' % tag)
    data['loading_text'] = (dlg.text or '')[-260:]
    t0 = time.time()
    got = []
    while time.time() - t0 < 12:
        got = toasts(d)
        if got:
            break
        time.sleep(0.3)
    shot(d, 'E_%s_error' % tag)
    data['toasts'] = got
    data['error_text'] = (dlg.text or '')[-400:]
    data['net'] = net_log(d)
    throttle(d, False)
    return data


def finish_stage(d, key):
    flag(key, False)
    time.sleep(1.2)
    close_all(d)


def stage_group(d):
    data = {'title': '批量调整分组'}
    data['reselect'] = ensure_selected(d)
    open_bulk(d, '批量调整分组')
    dlg = cur_dialog(d, '批量调整分组')
    combo = next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)), None)
    d.execute_script('arguments[0].click();', combo)
    time.sleep(1.0)
    opt = retry(lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                              if vis(e) and GROUP in (e.text or '')), None), 10)
    d.execute_script('arguments[0].click();', opt)
    time.sleep(0.8)
    data['trigger_text'] = (dlg.text or '')[:120]
    failure_cycle(d, data, 'group')
    click_btn(d, dlg, '确定')
    capture_loading_then_error(d, dlg, 'group', data)
    finish_stage(d, 'fail_batch')
    record('group', data)


def stage_spl(d):
    data = {'title': '批量设置声压级'}
    data['reselect'] = ensure_selected(d)
    open_bulk(d, '批量设置声压')
    dlg = cur_dialog(d, '批量设置声压级')
    inp = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, "input[aria-label='声压级 dB']")
                              if vis(e)), None), 15)
    inp.click()
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys('65')
    time.sleep(0.5)
    failure_cycle(d, data, 'spl')
    click_btn(d, dlg, '确定')
    capture_loading_then_error(d, dlg, 'spl', data)
    finish_stage(d, 'fail_batch')
    record('spl', data)


def stage_dims(d):
    data = {'title': '批量设置评估维度'}
    data['reselect'] = ensure_selected(d)
    open_bulk(d, '批量设置评估维度')
    dlg = cur_dialog(d, '批量设置评估维度')
    time.sleep(2)
    failure_cycle(d, data, 'dims')
    click_btn(d, dlg, '确定')
    capture_loading_then_error(d, dlg, 'dims', data)
    finish_stage(d, 'fail_batch')
    record('dims', data)


def stage_tags(d):
    data = {'title': '批量管理标签'}
    data['reselect'] = ensure_selected(d)
    open_bulk(d, '批量管理标签')
    dlg = cur_dialog(d, '批量管理标签')
    inp = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, 'input')
                              if vis(e) and '标签' in (e.get_attribute('placeholder') or '')), None), 15)
    inp.click()
    inp.send_keys('接线测试_INT1643_state')
    inp.send_keys(Keys.ENTER)
    time.sleep(1.0)
    data['chip_text'] = (dlg.text or '')[:200]
    failure_cycle(d, data, 'tags')
    click_btn(d, dlg, '确定')
    capture_loading_then_error(d, dlg, 'tags', data)
    finish_stage(d, 'fail_batch')
    record('tags', data)


def stage_noise(d):
    data = {'title': '批量设置噪声（加载/失败态在子弹窗）'}
    data['reselect'] = ensure_selected(d)
    open_bulk(d, '批量设置噪声')
    dlg = cur_dialog(d, '批量设置噪声')
    time.sleep(1)
    pick = retry(lambda: next((b for b in dlg.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and '点击选择噪声音频' in (b.text or '')), None), 15)
    flag('fail_audios', True)
    d.execute_script('arguments[0].click();', pick)
    sub = cur_dialog(d, '选择噪声音频', 20)
    time.sleep(3)
    shot(d, 'E_noise_error')
    data['error_text'] = (sub.text or '')[:400]
    data['net_error'] = net_log(d)
    flag('fail_audios', False)
    throttle(d, True)
    retry_btn = retry(lambda: next((b for b in sub.find_elements(By.TAG_NAME, 'button')
                                    if vis(b) and '重试' in (b.text or '')), None), 10)
    data['retry_btn'] = retry_btn is not None
    if retry_btn is not None:
        d.execute_script('arguments[0].click();', retry_btn)
        time.sleep(1.2)
        shot(d, 'L_noise_loading')
        data['loading_text'] = (sub.text or '')[:300]
    throttle(d, False)
    time.sleep(6)
    shot(d, 'N_noise_empty')
    data['normal_text'] = (sub.text or '')[:300]
    data['net_retry'] = net_log(d)
    close_all(d)
    record('noise', data)


def stage_export(d):
    data = {'title': '导出真实下载 + 502'}
    data['reselect'] = ensure_selected(d)
    for f in glob.glob(os.path.join(DL, '*')):
        try:
            os.remove(f)
        except Exception:
            pass
    try:
        d.execute_cdp_cmd('Browser.setDownloadBehavior',
                          {'behavior': 'allow', 'downloadPath': DL, 'eventsEnabled': True})
        data['dl'] = 'Browser.setDownloadBehavior'
    except Exception as e:
        d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': DL})
        data['dl'] = 'Page.setDownloadBehavior (%s)' % e
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
    L.clear_fetch_log(d)
    click_btn(d, dlg, '导出')
    files = []
    t0 = time.time()
    while time.time() - t0 < 90:
        files = [f for f in glob.glob(os.path.join(DL, '*')) if os.path.getsize(f) > 0]
        if files:
            break
        time.sleep(2)
    data['net'] = net_log(d)
    data['files'] = [{'name': os.path.basename(f), 'size': os.path.getsize(f)} for f in
                     [f for f in glob.glob(os.path.join(DL, '*')) if os.path.getsize(f) > 0]]
    if data['files']:
        raw = open([f for f in glob.glob(os.path.join(DL, '*')) if os.path.getsize(f) > 0][0], 'rb').read()
        data['head'] = raw[:200].decode('utf-8', 'replace')
        try:
            payload = json.loads(raw.decode('utf-8'))
            cases = (payload.get('data') or {}).get('test_cases') or payload.get('test_cases')
            data['json_ok'] = True
            data['case_count'] = len(cases) if isinstance(cases, list) else None
        except Exception as e:
            data['json_ok'] = 'parse error: %s' % e
    shot(d, 'D3_export_downloaded')
    close_all(d)
    # 502 失败态
    try:
        flag('fail_export', True)
        b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                                if vis(x) and (x.text or '').strip() == '导出'), None), 20)
        d.execute_script('arguments[0].click();', b)
        dlg2 = cur_dialog(d, '导出用例')
        time.sleep(1.5)
        rb2 = [e for e in dlg2.find_elements(By.CSS_SELECTOR, "input[type='radio']") if vis(e)]
        if len(rb2) > 1 and not rb2[1].get_attribute('disabled'):
            d.execute_script('arguments[0].click();', rb2[1])
            time.sleep(0.6)
        L.clear_fetch_log(d)
        click_btn(d, dlg2, '导出')
        t0 = time.time()
        got = []
        while time.time() - t0 < 10:
            got = toasts(d)
            if got:
                break
            time.sleep(0.3)
        shot(d, 'E_export_error')
        L.apply_theme(d, 'dark')
        shot(d, 'E_export_error_dark')
        L.apply_theme(d, 'light')
        data['toast_err'] = got
        data['net_fail'] = net_log(d)
        flag('fail_export', False)
        close_all(d)
    except Exception:
        data['error_state_exception'] = traceback.format_exc()[-800:]
        flag('fail_export', False)
    record('export', data)


def main():
    clear_flags()
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases/by-group')
        labels = enter_group(d)
        print('rows', labels[:3])
        s, payload, raw = L.api_json(d, '/testcases?page=1&per_page=3&group_id=31d8cb2d-b349-4187-b7e0-d3f7cadc0d26')
        items = (payload or {}).get('data', {}).get('items', []) if isinstance(payload, dict) else []
        RESULT['selected'] = {it['name']: it['id'] for it in items[:3]}
        ensure_selected(d)
        for fn in (stage_group, stage_spl, stage_dims, stage_tags, stage_noise, stage_export):
            try:
                fn(d)
            except Exception:
                record(fn.__name__, {'exception': traceback.format_exc()[-1000:]})
                close_all(d)
    finally:
        clear_flags()
        try:
            throttle(d, False)
        except Exception:
            pass
        L.save_evidence('resultA4', RESULT)
        d.quit()
        print('DONE shots', len(RESULT['shots']))


if __name__ == '__main__':
    main()
