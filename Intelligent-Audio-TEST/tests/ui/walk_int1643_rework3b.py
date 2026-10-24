# -*- coding: utf-8 -*-
"""INT-1643 复核轮 Part B：只补「用例专属参数窗」表单加载态 + 「评估维度窗」提交中态。

（Part A 的 walk_int1643_rework3.py 里这两窗因批量条按钮标签写成弹窗标题而未打开；
本脚本用真实按钮标签「批量设置专属参数」「批量设置评估维度」重取，设备窗与参考参数重试的证据沿用 Part A。）
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

FLAGS = os.environ.get('AUDIT_FLAGS', r'D:\00_user_data\tmp\int1643_nginx\flags')
GROUP = '打断与恢复'
LATENCY_MS = 8000
RESULT = {'stages': {}, 'shots': [], 'latency_ms': LATENCY_MS}


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=30, interval=0.4, what='element'):
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception:
            pass
        time.sleep(interval)
    raise TimeoutError('not found in %ss: %s' % (timeout, what))


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


def throttle(d, on, latency=LATENCY_MS):
    d.execute_cdp_cmd('Network.enable', {})
    d.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': latency if on else 0,
        'downloadThroughput': 300 * 1024 if on else -1,
        'uploadThroughput': 300 * 1024 if on else -1,
        'connectionType': 'cellular3g' if on else 'none'})


def net_log(d, clear=True):
    entries = L.fetch_log(d)
    if clear:
        L.clear_fetch_log(d)
    out = []
    for e in entries:
        u = e.get('url') or ''
        if '/api/' in u:
            out.append({'method': e.get('method'), 't': e.get('t'),
                        'url': u.replace('http://127.0.0.1:15933', '')[:170],
                        'status': e.get('status'),
                        'resp': (e.get('resBody') or '')[:240] if (e.get('status') or 200) >= 400 else None})
    return out


def record(stage, data):
    RESULT['stages'][stage] = data
    L.save_evidence('result_rework3b', RESULT)
    print('STAGE', stage, json.dumps(data, ensure_ascii=False)[:900], flush=True)


def buttons(scope):
    return [b for b in scope.find_elements(By.TAG_NAME, 'button') if vis(b)]


def dialogs(d):
    return [e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if vis(e)]


def cur_dialog(d, title, timeout=30):
    return retry(lambda: next((e for e in dialogs(d) if title in (e.text or '')), None),
                 timeout, what='dialog ' + title)


def close_dialog(d):
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.2)
    for x in dialogs(d):
        try:
            b = next((b for b in buttons(x) if (b.text or '').strip() == '取消'), None)
            if b is not None:
                L.js_click(d, b)
        except Exception:
            pass
    time.sleep(0.8)


def enter_group(d):
    t0 = time.time()
    sp = retry(lambda: next((s for s in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']" % GROUP) if vis(s)), None), 180, 2, 'group span')
    L.js_click(d, sp)
    rows = retry(lambda: ([c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if vis(c)] or None),
                 180, 3, 'case rows')
    RESULT['timing'] = {'group_expand_s': round(time.time() - t0)}
    return rows


def ensure_selected(d, names):
    """只点未勾选的用例，避免把已勾选的再点掉。"""
    state = {}
    for name in names:
        def find():
            return next((c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
                         if vis(c) and c.get_attribute('aria-label') == '选择 ' + name), None)
        cb = retry(find, 30, 0.5, 'checkbox ' + name[:12])
        checked = (cb.get_attribute('aria-checked') or '').lower() == 'true'
        if not checked:
            L.js_click(d, cb)
            time.sleep(0.5)
        state[name] = checked
    return state


def open_bulk(d, label):
    bar = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == label), None), 25, what='bulk ' + label)
    L.js_click(d, bar)
    return bar


def click_tab(d, dr, label):
    t = retry(lambda: next((x for x in dr.find_elements(By.CSS_SELECTOR, "[role='tab']")
                            if vis(x) and (x.text or '').strip() == label), None), 25, what='tab ' + label)
    L.js_click(d, t)
    time.sleep(2)


# ---------------- 用例专属参数窗：schema 表单加载态 ----------------

def stage_params(d, names):
    data = {'title': '批量设置用例专属参数'}
    data['selected_state'] = ensure_selected(d, names)
    time.sleep(1.5)
    open_bulk(d, '批量设置专属参数')
    dlg = cur_dialog(d, '批量设置用例专属参数')
    time.sleep(1.0)
    data['open_text'] = (dlg.text or '')[:400]
    data['list_loading_visible'] = '加载算法列表' in (dlg.text or '')
    shot(d, 'L2_params_list_prefetched_r2')
    data['net_open'] = net_log(d)
    combo = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)), None),
                  20, what='algorithm combobox')
    throttle(d, True)
    L.clear_fetch_log(d)
    L.js_click(d, combo)
    time.sleep(1.0)
    opt = next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                if vis(e) and 'voice_llm' in ((e.get_attribute('data-value') or '') + (e.text or ''))), None)
    if opt is None:
        opt = retry(lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e)), None),
                    10, what='algorithm option')
    data['option_text'] = (opt.text or '').strip()[:60]
    L.js_click(d, opt)
    t1 = time.time()
    time.sleep(0.8)
    shot(d, 'L2_params_form_loading_r2')
    data['form_loading_after_s'] = round(time.time() - t1, 2)
    data['form_loading_text'] = (dlg.text or '')[:500]
    data['form_loading_visible'] = '正在加载算法参数表单' in (dlg.text or '')
    data['net_schema_inflight'] = net_log(d)
    throttle(d, False)
    retry(lambda: None if '正在加载算法参数表单' in (dlg.text or '') else True, 40, what='schema loaded')
    time.sleep(1.5)
    shot(d, 'N2_params_form_r2')
    data['normal_text'] = (dlg.text or '')[:500]
    data['net_schema_loaded'] = net_log(d)
    close_dialog(d)
    record('params_loading', data)


# ---------------- 评估维度窗：提交中态 ----------------

def stage_dims(d, names):
    data = {'title': '批量设置评估维度（提交中态）'}
    data['selected_state'] = ensure_selected(d, names)
    time.sleep(1.5)
    open_bulk(d, '批量设置评估维度')
    dlg = cur_dialog(d, '批量设置评估维度')
    time.sleep(2)
    data['dialog_text'] = (dlg.text or '')[:300]
    d.execute_script("""
      const dlg = arguments[0];
      const sc = [dlg, ...dlg.querySelectorAll('*')].filter(e => {
        const s = getComputedStyle(e);
        return (s.overflowY === 'auto' || s.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 4;
      });
      sc.forEach(e => { e.scrollTop = e.scrollHeight; });
    """, dlg)
    time.sleep(0.8)
    ok = retry(lambda: ([b for b in buttons(dlg) if (b.text or '').strip() == '确定'] or [None])[-1],
               15, what='dims submit button')
    data['submit_rect'] = d.execute_script("""const r=arguments[0].getBoundingClientRect();
        return {top:Math.round(r.top),bottom:Math.round(r.bottom),vh:window.innerHeight,
                visible: r.top>=0 && r.bottom<=window.innerHeight};""", ok)
    data['viewport'] = d.execute_script('return [window.innerWidth, window.innerHeight]')
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    L.js_click(d, ok)
    t0 = time.time()
    time.sleep(1.0)
    data['submit_button_state'] = d.execute_script("""
      const b = arguments[0];
      return {disabled: !!b.disabled, text: (b.innerText||'').trim(),
              hasSpinner: !!b.querySelector('svg, [data-slot="spinner"], [class*="spinner"]'),
              html: b.innerHTML.slice(0,200)};
    """, ok)
    data['shot_after_s'] = round(time.time() - t0, 2)
    shot(d, 'L5_dims_submit_loading_r2')
    data['net_submit'] = net_log(d)
    time.sleep(12)
    shot(d, 'E5_dims_error_r2')
    data['error_toast'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    data['net_error'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1)
    close_dialog(d)
    record('dims_loading', data)


def main():
    clear_flags()
    d = L.driver()
    try:
        L.login(d)
        d.set_window_size(1600, 1400)
        d.get(L.BASE + '/testcases/by-group')
        enter_group(d)
        s, payload, raw = L.api_json(d, '/testcases?page=1&per_page=3&group_id=31d8cb2d-b349-4187-b7e0-d3f7cadc0d26')
        items = ((payload or {}).get('data') or {}).get('items', []) if isinstance(payload, dict) else []
        names = [it['name'] for it in items[:3]]
        RESULT['selected'] = names
        for fn in (stage_params, stage_dims):
            try:
                fn(d, names)
            except Exception:
                record(fn.__name__, {'exception': traceback.format_exc()[-2500:]})
                try:
                    close_dialog(d)
                    flag('fail_batch', False)
                    throttle(d, False)
                except Exception:
                    pass
    finally:
        clear_flags()
        try:
            throttle(d, False)
        except Exception:
            pass
        L.save_evidence('result_rework3b', RESULT)
        d.quit()
        print('DONE shots', len(RESULT['shots']), flush=True)


if __name__ == '__main__':
    main()
