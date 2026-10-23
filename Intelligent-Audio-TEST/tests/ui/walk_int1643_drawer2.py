# -*- coding: utf-8 -*-
"""INT-1643 返工轮 Part B：抽屉五步逐字段（算法参数真实字段保存→回读、评估维度勾选保存→回读）、
参考参数真实 400 读取失败 + 重试、缺图 A1/A2/A4/A5/A6/A7。

前置：Part A 已用临时用例「接线测试_INT1643_参数」(algorithm_type=wire_test_param,
case_params: threshold) 与参考用例 DD100。
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

GROUP = '打断与恢复'
TEMP_CASE = '接线测试_INT1643_参数'
REF_CASE_KW = 'DD100'
FIELD_LABEL = '接线测试阈值'
DIM_NAME = '识别成功率'
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
    L.save_evidence('resultB', RESULT)
    print('STAGE', stage, json.dumps(data, ensure_ascii=False)[:700])


def dialogs(d):
    return [e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if vis(e)]


def enter_group(d):
    for attempt in range(2):
        t0 = time.time()
        sp = None
        while time.time() - t0 < 240:
            cand = [s for s in d.find_elements(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP) if vis(s)]
            if cand:
                sp = cand[0]
                break
            time.sleep(3)
        if sp is None:
            print('group span not found in %ds, reload (attempt %d)' % (time.time() - t0, attempt), flush=True)
            d.get(L.BASE + '/testcases/by-group')
            time.sleep(10)
            continue
        d.execute_script('arguments[0].click();', sp)
        t1 = time.time()
        rows = []
        while time.time() - t1 < 240:
            rows = [c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if vis(c)]
            if rows:
                break
            time.sleep(3)
        return [c.get_attribute('aria-label') for c in rows]
    raise RuntimeError('group span not found')


def open_case(d, name_contains):
    cb = retry(lambda: next((c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
                             if vis(c) and name_contains in (c.get_attribute('aria-label') or '')), None), 30)
    edit = None
    node = cb
    for _ in range(8):
        node = node.find_element(By.XPATH, '..')
        btns = [b for b in node.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']") if vis(b)]
        if btns:
            edit = btns[-1]
            break
    if edit is None:
        raise RuntimeError('edit button not found for %s' % name_contains)
    d.execute_script('arguments[0].click();', edit)
    dr = retry(lambda: next((x for x in dialogs(d) if '参考参数' in (x.text or '')), None), 40)
    time.sleep(2)
    return dr


def tabs_of(dr):
    return [x for x in dr.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]


def click_tab(d, dr, label):
    t = retry(lambda: next((x for x in tabs_of(dr) if (x.text or '').strip() == label), None), 20)
    L.js_click(d, t)
    time.sleep(2.5)
    return t


def save(d, dr):
    b = retry(lambda: next((x for x in dr.find_elements(By.TAG_NAME, 'button')
                            if vis(x) and (x.text or '').strip() == '保存'), None), 20)
    L.js_click(d, b)
    time.sleep(1.5)
    return b


def toasts(d):
    try:
        return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    except Exception:
        return []


def api_case(d, cid):
    s, payload, raw = L.api_json(d, '/testcases/' + cid)
    item = payload.get('data') if isinstance(payload, dict) and 'data' in payload else payload
    return s, item


def algo_input(dr):
    def f():
        inp = dr.find_elements(By.XPATH,
                               "//label[contains(normalize-space(.),'%s')]/following::input[1]" % FIELD_LABEL)
        for x in inp:
            if vis(x):
                return x
        return None
    return retry(f, 20)


def stage_tabs(d, dr):
    data = {'title': '抽屉五步逐页签', 'tabs': []}
    labels = [(x.text or '').strip() for x in tabs_of(dr)]
    data['tabs_seen'] = labels
    print('tabs', labels)
    order = [('A1', '算法参数'), ('A2', '音频列表'), ('A3', '噪声与干扰'), ('A4', '评估维度'), ('A5', '参考参数')]
    for prefix, label in order:
        if label not in labels:
            data['tabs'].append({'label': label, 'missing': True})
            continue
        click_tab(d, dr, label)
        time.sleep(1.5)
        shot(d, '%s_%s' % (prefix, {'算法参数': 'algo_params', '音频列表': 'audio_list', '噪声与干扰': 'noise',
                                    '评估维度': 'evaluation', '参考参数': 'reference'}[label]))
        entry = {'label': label, 'text': (dr.text or '')[:500], 'net': net_log(d)}
        if label == '参考参数':
            # INT-1645 缺口：路径存在但内容接口 400 → 真实失败态 + 重试
            time.sleep(3)
            shot(d, 'A5_ref_error')
            entry['error_text'] = (dr.text or '')[-500:]
            entry['net_error'] = net_log(d)
            rb = next((b for b in dr.find_elements(By.TAG_NAME, 'button')
                       if vis(b) and '重试' in (b.text or '')), None)
            entry['retry_btn'] = rb is not None
            if rb is not None:
                L.js_click(d, rb)
                time.sleep(0.8)
                shot(d, 'A6_ref_retry_loading')
                time.sleep(6)
                shot(d, 'A6_ref_after_retry')
                entry['after_retry'] = (dr.text or '')[-400:]
                entry['net_retry'] = net_log(d)
        data['tabs'].append(entry)
    L.apply_theme(d, 'dark')
    shot(d, 'A7_drawer_dark')
    L.apply_theme(d, 'light')
    record('drawer_tabs', data)
    return data


def stage_algo_edit(d, dr, cid):
    """只填值不保存（保存与评估维度合并一次，减少抽屉开关次数）。"""
    data = {'title': '算法参数逐字段编辑'}
    click_tab(d, dr, '算法参数')
    time.sleep(2)
    inp = algo_input(dr)
    data['before_value'] = inp.get_attribute('value')
    data['field_visible'] = True
    inp.click()
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys('0.8')
    time.sleep(0.6)
    data['typed_value'] = inp.get_attribute('value')
    shot(d, 'A1_algo_edited')
    record('drawer_algo_edit', data)
    return data


def stage_algo_reopen(d, cid):
    data = {'title': '算法参数重开回显'}
    dr = open_case(d, TEMP_CASE)
    click_tab(d, dr, '算法参数')
    time.sleep(2)
    inp = algo_input(dr)
    data['reopen_value'] = inp.get_attribute('value')
    shot(d, 'A6_algo_reopen')
    record('drawer_algo_reopen', data)
    return dr, data


def stage_eval_add(d, dr, cid):
    data = {'title': '评估维度勾选 + 保存后双回读（算法参数 / 维度）'}
    click_tab(d, dr, '评估维度')
    time.sleep(3)
    chip = retry(lambda: next((b for b in dr.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and DIM_NAME in (b.text or '')), None), 15)
    data['chip_found'] = chip is not None
    if chip is not None:
        d.execute_script('arguments[0].click();', chip)
        time.sleep(1.5)
        data['chip_text'] = (chip.text or '')[:60]
        shot(d, 'A4_eval_selected')
    L.clear_fetch_log(d)
    save(d, dr)
    time.sleep(3)
    data['toast'] = toasts(d)
    data['net_save'] = net_log(d)
    data['drawer_open'] = any('参考参数' in (x.text or '') for x in dialogs(d))
    time.sleep(2)
    s, item = api_case(d, cid)
    data['readback_status'] = s
    data['readback_algorithm_params'] = item.get('algorithm_params') if isinstance(item, dict) else None
    vals = []
    for r in (data['readback_algorithm_params'] or []):
        for p in (r.get('params') or []):
            try:
                vals.append((p.get('field_code'), float(p.get('field_value'))))
            except Exception:
                vals.append((p.get('field_code'), p.get('field_value')))
    data['readback_algo_ok'] = ('threshold', 0.8) in vals
    rounds = (item or {}).get('config', {}).get('rounds', []) if isinstance(item, dict) else []
    dims = []
    for r in rounds:
        for dd in ((r.get('evaluation') or {}).get('dimensions') or []):
            dims.append((r.get('round_number'), dd.get('id'), dd.get('name')))
    data['readback_dims'] = dims
    data['readback_dim_ok'] = any(str(x[1]) == '121' for x in dims)
    record('drawer_eval', data)
    return data


def stage_ref_error(d):
    data = {'title': '参考参数真实 400 读取失败 + 重试'}
    dr = open_case(d, REF_CASE_KW)
    click_tab(d, dr, '参考参数')
    time.sleep(4)
    L.clear_fetch_log(d)
    shot(d, 'A5_ref_error')
    data['error_text'] = (dr.text or '')[-600:]
    data['net'] = net_log(d)
    rb = retry(lambda: next((b for b in dr.find_elements(By.TAG_NAME, 'button')
                             if vis(b) and '重试' in (b.text or '')), None), 10)
    data['retry_btn'] = rb is not None
    if rb is not None:
        L.js_click(d, rb)
        time.sleep(1.0)
        shot(d, 'A6_ref_retry_loading')
        time.sleep(6)
        shot(d, 'A6_ref_after_retry')
        data['after_retry'] = (dr.text or '')[-600:]
        data['net_retry'] = net_log(d)
    record('drawer_ref_error', data)
    return dr


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases/by-group')
        labels = enter_group(d)
        print('rows', labels[:3], flush=True)
        s, payload, raw = L.api_json(d, '/testcases?page=1&per_page=3&group_id=31d8cb2d-b349-4187-b7e0-d3f7cadc0d26')
        items = (payload or {}).get('data', {}).get('items', []) if isinstance(payload, dict) else []
        temp_id = next((it['id'] for it in items if TEMP_CASE in it['name']), None)
        RESULT['temp_id'] = temp_id
        print('temp', temp_id)
        dr = open_case(d, TEMP_CASE)
        try:
            stage_tabs(d, dr)
        except Exception:
            record('drawer_tabs', {'exception': traceback.format_exc()[-1200:]})
        try:
            stage_algo_edit(d, dr, temp_id)
        except Exception:
            record('drawer_algo_edit', {'exception': traceback.format_exc()[-1500:]})
        try:
            stage_eval_add(d, dr, temp_id)
        except Exception:
            record('drawer_eval', {'exception': traceback.format_exc()[-1500:]})
        try:
            dr2, reopened = stage_algo_reopen(d, temp_id)
            record('drawer_algo_reopen', reopened)
        except Exception:
            record('drawer_algo_reopen', {'exception': traceback.format_exc()[-1200:]})
    finally:
        L.save_evidence('resultB', RESULT)
        d.quit()
        print('DONE shots', len(RESULT['shots']))


if __name__ == '__main__':
    main()
