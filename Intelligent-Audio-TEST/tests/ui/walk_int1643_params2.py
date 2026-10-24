# -*- coding: utf-8 -*-
"""INT-1643 返工轮 Part A2：「批量设置用例专属参数」窗加载态 / 网关层 502 失败态 +
逐字段提交 → 逐条 GET /testcases/{id} 回读。

（Part A 的 stage_params 因标题串写成「批量设置专属参数」（实际「批量设置用例专属参数」）未取到弹窗，
本脚本单独补该窗。）
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
GROUP = '打断与恢复'
TITLE = '用例专属参数'
RESULT = {'stages': {}, 'shots': [], 'net': []}


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
            'offline': False, 'latency': 2500 if on else 0,
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
    L.save_evidence('resultA2', RESULT)
    print('STAGE', stage, json.dumps(data, ensure_ascii=False)[:600])


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


def cur_dialog(d, timeout=25):
    def f():
        for e in dialogs(d):
            if TITLE in (e.text or ''):
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
    L.js_click(d, sp)
    t1 = time.time()
    rows = []
    while time.time() - t1 < 150:
        rows = [c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if vis(c)]
        if rows:
            break
        time.sleep(3)
    return [c.get_attribute('aria-label') for c in rows]


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
        ids_by_name = {it['name']: it['id'] for it in items[:3]}
        RESULT['selected'] = ids_by_name
        for n in ids_by_name:
            cb = retry(lambda: next((c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
                                     if vis(c) and c.get_attribute('aria-label') == '选择 ' + n), None), 25)
            L.js_click(d, cb)
            time.sleep(0.5)
        time.sleep(1.5)

        data = {'title': '批量设置用例专属参数'}
        # ---- 加载态：算法列表加载中 ----
        throttle(d, True)
        bar = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                  if vis(b) and (b.text or '').strip() == '批量设置专属参数'), None), 20)
        L.js_click(d, bar)
        dlg = cur_dialog(d, 25)
        shot(d, 'L2_params_list_loading')
        data['loading_text'] = (dlg.text or '')[:300]
        throttle(d, False)
        time.sleep(5)
        # ---- 选择算法（wire_test_param）----
        combo = next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)), None)
        L.js_click(d, combo)
        time.sleep(1.0)
        opts = [(e.text or '').strip() for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e)]
        data['algorithm_options'] = opts
        target = next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                       if vis(e) and '参数算法' in (e.text or '')), None)
        if target is None:
            raise RuntimeError('wire_test_param option missing: %s' % opts)
        # ---- 失败态：schema 网关层 502 ----
        flag('fail_schema', True)
        L.clear_fetch_log(d)
        L.js_click(d, target)
        time.sleep(4)
        shot(d, 'E2_params_schema_error')
        data['error_text'] = (dlg.text or '')[:500]
        data['net_error'] = net_log(d)
        flag('fail_schema', False)
        # ---- 重试：真实请求在途（限速）----
        throttle(d, True)
        L.js_click(d, btn(dlg, '重试', timeout=10))
        time.sleep(1.2)
        shot(d, 'L2_params_form_loading')
        data['loading_text2'] = (dlg.text or '')[:400]
        throttle(d, False)
        time.sleep(5)
        shot(d, 'N2_params_form')
        data['normal_text'] = (dlg.text or '')[:400]
        data['net_retry'] = net_log(d)
        # ---- 逐字段填写并提交 ----
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
        L.js_click(d, btn(dlg, '确定', timeout=10))
        time.sleep(4)
        data['toast'] = toasts(d)
        data['net_submit'] = net_log(d)
        data['dialog_open'] = bool(cur_dialog(d, 3))
        close_dialog(d)
        time.sleep(2)
        rb = {}
        for name, cid in ids_by_name.items():
            res = L.api_json(d, '/testcases/' + cid)
            s2, item = res[0], res[1]
            item = item.get('data') if isinstance(item, dict) and 'data' in item else item
            rb[name] = {'status': s2,
                        'algorithm_params': item.get('algorithm_params') if isinstance(item, dict) else None}
        data['readback'] = rb
        ok = []
        for name, v in rb.items():
            vals = []
            for r in (v.get('algorithm_params') or []):
                for p in (r.get('params') or []):
                    b = p.get('field_value')
                    vals.append((p.get('field_code'), float(b) if isinstance(b, (int, float)) else b))
            if ('threshold', 0.3) in vals:
                ok.append(name)
        data['readback_ok'] = ok
        record('params_window', data)
    finally:
        clear_flags()
        try:
            throttle(d, False)
        except Exception:
            pass
        L.save_evidence('resultA2', RESULT)
        d.quit()
        print('DONE shots', len(RESULT['shots']))


if __name__ == '__main__':
    main()
