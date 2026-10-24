# -*- coding: utf-8 -*-
"""INT-1643 返工轮 Part A：批量七窗真实加载态 + 网关层 502 失败态；导出成功/失败态；
批量「用例专属参数」逐字段提交 + 逐条 GET 回读。

基座：15933 旁路站（HEAD + INT-1642 492fe09b4 构建 dist），nginx 反代 api_gateway:5000；
/audit/fail_* flag 文件在网关层返回真实 502（非页内 mock）；加载态用 CDP Network.emulateNetworkConditions 限速。
"""
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
NEW_ALGO = 'wire_test_param'
TEMP_CASE = '接线测试_INT1643_参数'
RESULT = {'stages': {}, 'net': [], 'shots': [], 'readback': {}}


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
        if on:
            d.execute_cdp_cmd('Network.emulateNetworkConditions', {
                'offline': False, 'latency': 2500,
                'downloadThroughput': 400 * 1024, 'uploadThroughput': 400 * 1024,
                'connectionType': 'cellular3g'})
        else:
            d.execute_cdp_cmd('Network.emulateNetworkConditions', {
                'offline': False, 'latency': 0,
                'downloadThroughput': -1, 'uploadThroughput': -1,
                'connectionType': 'none'})
    except Exception as e:
        print('throttle err', e)


def net_log(d, clear=True):
    entries = L.fetch_log(d)
    if clear:
        L.clear_fetch_log(d)
    keep = []
    for e in entries:
        u = e.get('url') or ''
        if '/api/' in u or '/health' in u:
            keep.append({'method': e.get('method'), 'url': u.split('127.0.0.1:15933')[-1][:160],
                         'status': e.get('status'),
                         'resp': (e.get('resBody') or '')[:200] if e.get('status', 200) >= 400 or e.get('status') == -1 else None})
    return keep


def buttons(scope):
    return [b for b in scope.find_elements(By.TAG_NAME, 'button') if vis(b)]


def btn(scope, text, exact=True, timeout=20):
    def f():
        for b in buttons(scope):
            t = (b.text or '').strip()
            if (t == text) if exact else (text in t):
                return b
        return None
    return retry(f, timeout)


def dialogs(d):
    return [e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if vis(e)]


def cur_dialog(d, title, timeout=20):
    def f():
        for e in dialogs(d):
            if title in (e.text or ''):
                return e
        return None
    return retry(f, timeout)


def close_dialog(d):
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    for x in dialogs(d):
        try:
            b = btn(x, '取消', timeout=1)
            if b:
                L.js_click(d, b)
        except Exception:
            pass
    time.sleep(0.6)


def enter_group(d):
    """分组卡默认收起：点组名 span 展开，等待组内用例懒加载完成（真实站约 50s）。"""
    t0 = time.time()
    sp = None
    while time.time() - t0 < 150:
        cand = [s for s in d.find_elements(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP)
                if vis(s)]
        if cand:
            sp = cand[0]
            break
        time.sleep(2)
    if sp is None:
        raise RuntimeError('group span not found in 150s')
    L.js_click(d, sp)
    t1 = time.time()
    rows = []
    while time.time() - t1 < 150:
        rows = [c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if vis(c)]
        if rows:
            break
        time.sleep(3)
    RESULT.setdefault('timing', {})['group_expand_s'] = round(time.time() - t0)
    return [c.get_attribute('aria-label') for c in rows]


def select_by_name(d, name):
    cb = retry(lambda: next((c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
                             if vis(c) and c.get_attribute('aria-label') == '选择 ' + name), None), 25)
    L.js_click(d, cb)
    time.sleep(0.6)
    return cb.get_attribute('aria-label')


def open_bulk(d, label):
    bar = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == label), None), 20)
    L.js_click(d, bar)
    time.sleep(2.5)


def combo(dlg, placeholder):
    el = next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)), None)
    if el is not None:
        return el
    for b in buttons(dlg):
        if placeholder in (b.text or ''):
            return b
    return buttons(dlg)[0]


def click_submit(d, dlg, label='确定'):
    b = btn(dlg, label, timeout=10)
    L.js_click(d, b)
    return b


def record(stage, data):
    RESULT['stages'][stage] = data
    L.save_evidence('resultA', RESULT)
    print('STAGE', stage, json.dumps(data, ensure_ascii=False)[:700])


def toasts(d):
    try:
        return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    except Exception:
        return []


# ---------------- 批量七窗 ----------------

def stage_group(d):
    data = {'title': '批量调整分组'}
    open_bulk(d, '批量调整分组')
    dlg = cur_dialog(d, '批量调整分组')
    L.js_click(d, combo(dlg, '请选择分组'))
    time.sleep(1.0)
    opt = retry(lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                              if vis(e) and GROUP in (e.text or '')), None), 10)
    L.js_click(d, opt)
    time.sleep(0.8)
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    click_submit(d, dlg)
    time.sleep(1.2)
    shot(d, 'L1_group_loading')
    data['loading_text'] = (dlg.text or '')[-300:]
    time.sleep(8)
    shot(d, 'E1_group_error')
    data['error_text'] = (dlg.text or '')[-400:]
    data['toast'] = toasts(d)
    data['net'] = net_log(d)
    data['dialog_open'] = bool(cur_dialog(d, '批量调整分组', timeout=3))
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.0)
    close_dialog(d)
    record('group', data)


def stage_params(d):
    data = {'title': '批量设置专属参数'}
    throttle(d, True)
    open_bulk(d, '批量设置专属参数')
    dlg = cur_dialog(d, '批量设置专属参数')
    time.sleep(1.0)
    shot(d, 'L2_params_list_loading')
    data['loading_text'] = (dlg.text or '')[:300]
    throttle(d, False)
    time.sleep(4)
    L.js_click(d, combo(dlg, '请选择算法'))
    time.sleep(0.8)
    opts = [(e.text or '').strip() for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e)]
    data['algorithm_options'] = opts
    target = next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                   if vis(e) and ('参数算法' in (e.text or ''))), None)
    if target is None:
        target = next(e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e))
    flag('fail_schema', True)
    L.clear_fetch_log(d)
    L.js_click(d, target)
    time.sleep(4)
    shot(d, 'E2_params_schema_error')
    data['error_text'] = (dlg.text or '')[:500]
    data['net'] = net_log(d)
    flag('fail_schema', False)
    throttle(d, True)
    L.js_click(d, btn(dlg, '重试', timeout=10))
    time.sleep(1.2)
    shot(d, 'L2_params_form_loading')
    data['loading_text2'] = (dlg.text or '')[:400]
    throttle(d, False)
    time.sleep(5)
    shot(d, 'N2_params_form')
    data['normal_text'] = (dlg.text or '')[:500]
    data['net_retry'] = net_log(d)
    close_dialog(d)
    record('params', data)


def stage_device(d):
    data = {'title': '批量设置播放设备'}
    throttle(d, True)
    open_bulk(d, '批量设置播放设备')
    dlg = cur_dialog(d, '批量设置播放设备')
    time.sleep(1.0)
    shot(d, 'L3_device_loading')
    data['loading_text'] = (dlg.text or '')[:300]
    throttle(d, False)
    time.sleep(5)
    shot(d, 'N3_device_list')
    data['normal_text'] = (dlg.text or '')[:300]
    flag('fail_devices', True)
    L.clear_fetch_log(d)
    scan = retry(lambda: next((b for b in buttons(dlg) if '扫描' in (b.text or '')), None), 10)
    L.js_click(d, scan)
    time.sleep(6)
    shot(d, 'E3_device_scan_error')
    data['error_text'] = (dlg.text or '')[:500]
    data['net'] = net_log(d)
    flag('fail_devices', False)
    time.sleep(3)
    close_dialog(d)
    record('device', data)


def stage_spl(d):
    data = {'title': '批量设置声压级'}
    open_bulk(d, '批量设置声压级')
    dlg = cur_dialog(d, '批量设置声压级')
    inp = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, "input[aria-label='声压级 dB']")
                              if vis(e)), None), 10)
    inp.click()
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys('65')
    time.sleep(0.5)
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    click_submit(d, dlg)
    time.sleep(1.2)
    shot(d, 'L4_spl_loading')
    data['loading_text'] = (dlg.text or '')[-300:]
    time.sleep(8)
    shot(d, 'E4_spl_error')
    data['error_text'] = (dlg.text or '')[-400:]
    data['toast'] = toasts(d)
    data['net'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.0)
    close_dialog(d)
    record('spl', data)


def stage_dims(d):
    data = {'title': '批量设置评估维度'}
    open_bulk(d, '批量设置评估维度')
    dlg = cur_dialog(d, '批量设置评估维度')
    time.sleep(2)
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    click_submit(d, dlg)
    time.sleep(1.2)
    shot(d, 'L5_dims_loading')
    data['loading_text'] = (dlg.text or '')[-300:]
    time.sleep(8)
    shot(d, 'E5_dims_error')
    data['error_text'] = (dlg.text or '')[-400:]
    data['net'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.0)
    close_dialog(d)
    record('dims', data)


def stage_tags(d):
    data = {'title': '批量管理标签'}
    open_bulk(d, '批量管理标签')
    dlg = cur_dialog(d, '批量管理标签')
    inp = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, 'input')
                              if vis(e) and '标签' in (e.get_attribute('placeholder') or '')), None), 10)
    inp.click()
    inp.send_keys('接线测试_INT1643_state')
    inp.send_keys(Keys.ENTER)
    time.sleep(1.0)
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    click_submit(d, dlg)
    time.sleep(1.2)
    shot(d, 'L6_tags_loading')
    data['loading_text'] = (dlg.text or '')[-300:]
    time.sleep(8)
    shot(d, 'E6_tags_error')
    data['error_text'] = (dlg.text or '')[-400:]
    data['toast'] = toasts(d)
    data['net'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.0)
    close_dialog(d)
    record('tags', data)


def stage_noise(d):
    data = {'title': '批量设置噪声'}
    flag('fail_audios', True)
    open_bulk(d, '批量设置噪声')
    dlg = cur_dialog(d, '批量设置噪声')
    L.clear_fetch_log(d)
    time.sleep(5)
    shot(d, 'E7_noise_error')
    data['error_text'] = (dlg.text or '')[:500]
    data['net'] = net_log(d)
    flag('fail_audios', False)
    throttle(d, True)
    L.js_click(d, btn(dlg, '重试', timeout=10))
    time.sleep(1.2)
    shot(d, 'L7_noise_loading')
    data['loading_text'] = (dlg.text or '')[:300]
    throttle(d, False)
    time.sleep(6)
    shot(d, 'N7_noise_result')
    data['normal_text'] = (dlg.text or '')[:400]
    data['net_retry'] = net_log(d)
    close_dialog(d)
    record('noise', data)


def stage_export(d):
    data = {'title': '导出'}
    b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                            if vis(x) and (x.text or '').strip() == '导出'), None), 20)
    L.js_click(d, b)
    dlg = cur_dialog(d, '导出')
    time.sleep(2)
    shot(d, 'D1_export_dialog')
    rb = [e for e in dlg.find_elements(By.CSS_SELECTOR, "input[type='radio']") if vis(e)]
    data['radios'] = len(rb)
    if len(rb) > 1:
        L.js_click(d, rb[1])
        time.sleep(0.8)
    L.clear_fetch_log(d)
    throttle(d, True)
    b2 = retry(lambda: next((x for x in buttons(dlg) if '导出' in (x.text or '') and (x.text or '').strip() != '导出'), None), 8)
    L.js_click(d, b2)
    time.sleep(1.2)
    shot(d, 'D2_export_loading')
    data['loading_text'] = (dlg.text or '')[-300:]
    throttle(d, False)
    time.sleep(10)
    data['after_text'] = (dlg.text or '')[:400]
    data['toast'] = toasts(d)
    data['net_ok'] = net_log(d)
    shot(d, 'D3_export_result')
    L.apply_theme(d, 'dark')
    shot(d, 'D3_export_result_dark')
    L.apply_theme(d, 'light')
    time.sleep(1)
    flag('fail_export', True)
    L.clear_fetch_log(d)
    b3 = retry(lambda: next((x for x in buttons(dlg) if '导出' in (x.text or '')), None), 8)
    L.js_click(d, b3)
    time.sleep(6)
    shot(d, 'E8_export_error')
    L.apply_theme(d, 'dark')
    shot(d, 'E9_export_error_dark')
    L.apply_theme(d, 'light')
    data['error_text'] = L.body_text(d)[-400:]
    data['toast_err'] = toasts(d)
    data['net_fail'] = net_log(d)
    flag('fail_export', False)
    close_dialog(d)
    record('export', data)


# ---------------- 批量专属参数提交 + 回读 ----------------

def api_case(d, cid):
    s, payload, raw = L.api_json(d, '/testcases/' + cid)
    item = payload.get('data') if isinstance(payload, dict) and 'data' in payload else payload
    return s, item


def stage_params_submit(d, ids_by_name):
    data = {'title': '批量专属参数 提交回读', 'ids': ids_by_name}
    names = list(ids_by_name.keys())
    open_bulk(d, '批量设置专属参数')
    dlg = cur_dialog(d, '批量设置专属参数')
    time.sleep(3)
    L.js_click(d, combo(dlg, '请选择算法'))
    time.sleep(0.8)
    target = next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                   if vis(e) and ('参数算法' in (e.text or ''))), None)
    if target is None:
        data['algorithm_missing'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e)]
        raise RuntimeError('wire_test_param not in options')
    L.js_click(d, target)
    time.sleep(4)
    data['form_text'] = (dlg.text or '')[:400]
    inp = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, "input[type='number']")
                              if vis(e)), None), 15)
    data['input_before'] = inp.get_attribute('value')
    inp.click()
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys('0.3')
    time.sleep(0.6)
    data['input_after'] = inp.get_attribute('value')
    L.clear_fetch_log(d)
    click_submit(d, dlg)
    time.sleep(4)
    data['toast'] = toasts(d)
    data['net'] = net_log(d)
    data['dialog_open'] = bool(cur_dialog(d, '批量设置专属参数', timeout=3))
    close_dialog(d)
    time.sleep(2)
    rb = {}
    for name, cid in ids_by_name.items():
        s, item = api_case(d, cid)
        rb[name] = {'status': s, 'algorithm_type': item.get('algorithm_type') if isinstance(item, dict) else None,
                    'algorithm_params': item.get('algorithm_params') if isinstance(item, dict) else None}
    data['readback'] = rb
    ok = []
    for name, v in rb.items():
        ap = v.get('algorithm_params') or []
        vals = []
        for r in ap:
            for p in (r.get('params') or []):
                vals.append((p.get('field_code'), p.get('field_value')))
        if ('threshold', 0.3) in [(a, float(b) if isinstance(b, (int, float)) else b) for a, b in vals]:
            ok.append(name)
    data['readback_ok'] = ok
    record('params_submit', data)
    return data


def main():
    clear_flags()
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases/by-group')
        labels = enter_group(d)
        print('row labels', labels[:4])
        RESULT['rows_visible'] = labels[:6]
        # 与页面同序取前 3 条（组内懒加载 page=1&per_page=20&group_id=...）
        s, payload, raw = L.api_json(d, '/testcases?page=1&per_page=3&group_id=31d8cb2d-b349-4187-b7e0-d3f7cadc0d26')
        items = (payload or {}).get('data', {}).get('items', []) if isinstance(payload, dict) else []
        ids_by_name = {it['name']: it['id'] for it in items[:3]}
        RESULT['selected'] = ids_by_name
        print('selected', ids_by_name)
        for n in ids_by_name:
            select_by_name(d, n)
        time.sleep(2)
        for fn in (stage_group, stage_params, stage_device, stage_spl, stage_dims, stage_tags, stage_noise):
            try:
                fn(d)
            except Exception:
                record(fn.__name__, {'exception': traceback.format_exc()[-1200:]})
                close_dialog(d)
        try:
            stage_export(d)
        except Exception:
            record('export', {'exception': traceback.format_exc()[-1200:]})
            close_dialog(d)
        try:
            stage_params_submit(d, ids_by_name)
        except Exception:
            record('params_submit', {'exception': traceback.format_exc()[-1500:]})
            close_dialog(d)
    finally:
        clear_flags()
        try:
            throttle(d, False)
        except Exception:
            pass
        L.save_evidence('resultA', RESULT)
        d.quit()
        print('DONE shots', len(RESULT['shots']))


if __name__ == '__main__':
    main()
