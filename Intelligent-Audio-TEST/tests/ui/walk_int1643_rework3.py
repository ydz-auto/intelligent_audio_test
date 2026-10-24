# -*- coding: utf-8 -*-
"""INT-1643 复核轮（第 2 次打回）证据补齐脚本。

只补审计未通过的三处加载态 + A6 重试证据 + N3 设备闭合态图，不重跑全量：
1. 播放设备窗真实加载态：CDP 限速 8s，开窗后 <1.2s 截图 → 「正在加载播放设备...」
2. 用例专属参数窗：算法列表被页面级预取（['shell','algorithm','options'], staleTime 5min）掩盖，
   故改用本窗真实在途的 **schema 表单加载态**（选算法后 GET /algorithm/form-schema/voice_llm 在途）
3. 评估维度窗提交中态：拉高视口到 1600x1400 + 滚到弹窗底部，提交时截 确定 按钮内 Spinner
4. A5/A6：临时用例「接线测试_INT1643_重试」参考参数 tab 真实 404 失败态 → 点「重试」→
   抓第二次 GET .../rounds/1/ref-params 的 fetch 日志 + nginx 访问日志（两次 404）
5. N3：播放设备窗加载完成后的设备列表 + 选中后闭合态触发器显示设备名称

基座：旁路站 15933（nginx:alpine，dist=INT-1642 交付构建）+ api_gateway:5000；/audit/fail_batch 在网关层返回真实 502。
"""
import json
import os
import subprocess
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
TEMP_CASE = '接线测试_INT1643_重试'
LATENCY_MS = 8000
RESULT = {'stages': {}, 'shots': [], 'net': [], 'latency_ms': LATENCY_MS}


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=30, interval=0.4):
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


def throttle(d, on, latency=LATENCY_MS):
    try:
        d.execute_cdp_cmd('Network.enable', {})
        d.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': latency if on else 0,
            'downloadThroughput': 300 * 1024 if on else -1,
            'uploadThroughput': 300 * 1024 if on else -1,
            'connectionType': 'cellular3g' if on else 'none'})
    except Exception as e:
        print('throttle err', e, flush=True)


def net_log(d, clear=True, needle='/api/'):
    entries = L.fetch_log(d)
    if clear:
        L.clear_fetch_log(d)
    keep = []
    for e in entries:
        u = e.get('url') or ''
        if needle in u:
            keep.append({'method': e.get('method'), 't': e.get('t'),
                         'url': u.replace('http://127.0.0.1:15933', '')[:170],
                         'status': e.get('status'),
                         'resp': (e.get('resBody') or '')[:260] if (e.get('status') or 200) >= 400 else None})
    return keep


def nginx_log(tail=400):
    try:
        r = subprocess.run(['docker', 'logs', '--tail', str(tail), 'int1643-bypass'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        return (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        return 'ERR %s' % e


def record(stage, data):
    RESULT['stages'][stage] = data
    L.save_evidence('result_rework3', RESULT)
    print('STAGE', stage, json.dumps(data, ensure_ascii=False)[:800], flush=True)


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


def cur_dialog(d, title, timeout=30):
    def f():
        for e in dialogs(d):
            if title in (e.text or ''):
                return e
        return None
    return retry(f, timeout)


def close_dialog(d):
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.2)
    for x in dialogs(d):
        try:
            b = btn(x, '取消', timeout=1)
            if b:
                L.js_click(d, b)
        except Exception:
            pass
    time.sleep(0.8)


def open_bulk(d, label, settle=0.0):
    bar = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == label), None), 25)
    L.js_click(d, bar)
    if settle:
        time.sleep(settle)


def enter_group(d):
    t0 = time.time()
    sp = None
    while time.time() - t0 < 180:
        cand = [s for s in d.find_elements(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP)
                if vis(s)]
        if cand:
            sp = cand[0]
            break
        time.sleep(2)
    if sp is None:
        raise RuntimeError('group span not found')
    L.js_click(d, sp)
    t1 = time.time()
    rows = []
    while time.time() - t1 < 180:
        rows = [c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']") if vis(c)]
        if rows:
            break
        time.sleep(3)
    RESULT['timing'] = {'group_expand_s': round(time.time() - t0)}
    return [c.get_attribute('aria-label') for c in rows]


def select_by_name(d, name):
    cb = retry(lambda: next((c for c in d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")
                             if vis(c) and c.get_attribute('aria-label') == '选择 ' + name), None), 30)
    L.js_click(d, cb)
    time.sleep(0.5)


def open_case_drawer(d, name_contains):
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
    dr = retry(lambda: next((x for x in dialogs(d) if '参考参数' in (x.text or '')), None), 45)
    time.sleep(2)
    return dr


def click_tab(d, dr, label):
    t = retry(lambda: next((x for x in dr.find_elements(By.CSS_SELECTOR, "[role='tab']")
                            if vis(x) and (x.text or '').strip() == label), None), 25)
    L.js_click(d, t)
    time.sleep(2.5)
    return t


# ---------------- 1. 播放设备窗加载态 + N3 ----------------

def stage_device(d):
    data = {'title': '批量设置播放设备'}
    throttle(d, True)
    open_bulk(d, '批量设置播放设备')
    dlg = cur_dialog(d, '批量设置播放设备')
    t0 = time.time()
    shot(d, 'L3_device_loading_r2')
    data['loading_text'] = (dlg.text or '')[:400]
    data['loading_has_text'] = '正在加载播放设备' in (dlg.text or '')
    data['since_open_s'] = round(time.time() - t0, 2)
    data['net_inflight'] = net_log(d)
    throttle(d, False)
    # 等加载完成，取真实设备列表
    retry(lambda: None if '正在加载播放设备' in (dlg.text or '') else True, 40)
    time.sleep(1.5)
    shot(d, 'N3_device_list_r2')
    data['normal_text'] = (dlg.text or '')[:500]
    data['net_loaded'] = net_log(d)
    # 选中一台设备 → 闭合态触发器是否显示名称
    try:
        combo = next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)), None)
        if combo is not None:
            L.js_click(d, combo)
            time.sleep(1.0)
            opts = [(e.text or '').strip() for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e)]
            data['device_options'] = opts[:6]
            if opts:
                first = next(e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e))
                L.js_click(d, first)
                time.sleep(1.0)
                shot(d, 'N3_device_selected_r2')
                data['selected_trigger_text'] = (dlg.text or '')[:400]
    except Exception:
        data['select_exception'] = traceback.format_exc()[-600:]
    close_dialog(d)
    record('device_loading', data)


# ---------------- 2. 用例专属参数窗（列表预取 → 表单加载态） ----------------

def stage_params(d):
    data = {'title': '批量设置用例专属参数'}
    open_bulk(d, '批量设置用例专属参数', settle=1.2)
    dlg = cur_dialog(d, '批量设置用例专属参数')
    t_open = time.time()
    data['open_text'] = (dlg.text or '')[:400]
    data['list_loading_visible'] = '加载算法列表' in (dlg.text or '')
    shot(d, 'L2_params_list_prefetched_r2')
    data['open_after_s'] = round(time.time() - t_open, 2)
    # 选算法（voice_llm）触发 schema 请求，限速让其在途
    combo = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)), None), 20)
    throttle(d, True)
    L.clear_fetch_log(d)
    L.js_click(d, combo)
    time.sleep(1.0)
    opt = retry(lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                              if vis(e) and 'voice_llm' in (e.get_attribute('data-value') or '')), None), 10)
    if opt is None:
        opt = next(e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e))
    L.js_click(d, opt)
    t1 = time.time()
    time.sleep(0.8)
    shot(d, 'L2_params_form_loading_r2')
    data['form_loading_text'] = (dlg.text or '')[:500]
    data['form_loading_visible'] = '正在加载算法参数表单' in (dlg.text or '')
    data['form_loading_after_s'] = round(time.time() - t1, 2)
    data['net_schema_inflight'] = net_log(d)
    throttle(d, False)
    retry(lambda: None if '正在加载算法参数表单' in (dlg.text or '') else True, 40)
    time.sleep(1.5)
    shot(d, 'N2_params_form_r2')
    data['normal_text'] = (dlg.text or '')[:500]
    data['net_schema_loaded'] = net_log(d)
    close_dialog(d)
    record('params_loading', data)


# ---------------- 3. 评估维度窗：提交中态 ----------------

def stage_dims(d):
    data = {'title': '批量设置评估维度（提交中态）'}
    open_bulk(d, '批量设置评估维度', settle=1.5)
    dlg = cur_dialog(d, '批量设置评估维度')
    time.sleep(2)
    # 滚到弹窗底部，确保 确定 在视口内
    d.execute_script("""
      const dlg = arguments[0];
      const sc = [dlg, ...dlg.querySelectorAll('*')].filter(e => {
        const s = getComputedStyle(e);
        return (s.overflowY === 'auto' || s.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 4;
      });
      sc.forEach(e => { e.scrollTop = e.scrollHeight; });
    """, dlg)
    time.sleep(0.8)
    # 取最后一个可见「确定」（弹窗底栏提交钮；复制到轮次 Popover 内的同名钮不可见）
    ok = retry(lambda: ([b for b in buttons(dlg) if (b.text or '').strip() == '确定'][-1]
                        if [b for b in buttons(dlg) if (b.text or '').strip() == '确定'] else None), 15)
    rect = d.execute_script("""const r=arguments[0].getBoundingClientRect();
        return {top:Math.round(r.top),bottom:Math.round(r.bottom),vh:window.innerHeight,
                vw:window.innerWidth, visible: r.top>=0 && r.bottom<=window.innerHeight};""", ok)
    data['submit_rect'] = rect
    data['viewport'] = d.execute_script('return [window.innerWidth, window.innerHeight]')
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    L.js_click(d, ok)
    t0 = time.time()
    time.sleep(1.0)
    spinner = d.execute_script("""
      const b = arguments[0];
      return {found:true, disabled: !!b.disabled,
              hasSpinner: !!b.querySelector('svg, [data-slot="spinner"], [class*="spinner"]'),
              text: (b.innerText||'').trim(), html: b.innerHTML.slice(0,220)};
    """, ok)
    data['submit_button_state'] = spinner
    shot(d, 'L5_dims_submit_loading_r2')
    data['loading_text'] = (dlg.text or '')[-300:]
    data['net_submit'] = net_log(d)
    # 等 502 回来 → 错误态
    time.sleep(12)
    shot(d, 'E5_dims_error_r2')
    data['error_toast'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    data['net_error'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1)
    close_dialog(d)
    record('dims_loading', data)


# ---------------- 4. A5/A6 参考参数失败 + 重试 ----------------

def stage_ref_retry(d):
    data = {'title': '抽屉参考参数失败态 + 重试'}
    dr = open_case_drawer(d, TEMP_CASE)
    click_tab(d, dr, '参考参数')
    time.sleep(4)
    L.clear_fetch_log(d)
    shot(d, 'A5_ref_error_r2')
    data['error_text'] = (dr.text or '')[-600:]
    data['net_first'] = net_log(d)
    rb = retry(lambda: next((b for b in dr.find_elements(By.TAG_NAME, 'button')
                             if vis(b) and '重试' in (b.text or '')), None), 15)
    data['retry_btn'] = rb is not None
    if rb is None:
        raise RuntimeError('retry button missing')
    # 点击计数钩子：证明重试按钮真的被点过
    d.execute_script("""window.__retryClicks = 0;
        arguments[0].addEventListener('click', () => { window.__retryClicks += 1; });""", rb)
    throttle(d, True)
    L.clear_fetch_log(d)
    L.js_click(d, rb)
    t0 = time.time()
    time.sleep(1.0)
    shot(d, 'A6_ref_retry_inflight_r2')
    data['retry_clicks_after_1s'] = d.execute_script('return window.__retryClicks || 0')
    data['inflight_text'] = (dr.text or '')[-400:]
    throttle(d, False)
    time.sleep(9)
    shot(d, 'A6_ref_after_retry_r2')
    data['retry_clicks'] = d.execute_script('return window.__retryClicks || 0')
    data['after_retry_text'] = (dr.text or '')[-600:]
    data['net_retry'] = net_log(d)
    data['nginx_log'] = [ln for ln in nginx_log(300).splitlines() if 'ref-params' in ln][-8:]
    record('ref_retry', data)


def main():
    clear_flags()
    d = L.driver()
    try:
        L.login(d)
        d.set_window_size(1600, 1400)
        d.get(L.BASE + '/testcases/by-group')
        labels = enter_group(d)
        print('rows', labels[:3], flush=True)
        RESULT['rows_visible'] = labels[:6]
        s, payload, raw = L.api_json(d, '/testcases?page=1&per_page=3&group_id=31d8cb2d-b349-4187-b7e0-d3f7cadc0d26')
        items = ((payload or {}).get('data') or {}).get('items', []) if isinstance(payload, dict) else []
        # 选 3 条真实用例（本卡不改其数据；唯一提交走 fail_batch 502）
        sel = [it['name'] for it in items[:3]]
        RESULT['selected'] = sel
        for n in sel:
            select_by_name(d, n)
        time.sleep(2)
        for fn in (stage_device, stage_params, stage_dims, stage_ref_retry):
            try:
                fn(d)
            except Exception:
                record(fn.__name__, {'exception': traceback.format_exc()[-1500:]})
                try:
                    close_dialog(d)
                except Exception:
                    pass
        RESULT['nginx_all'] = [ln for ln in nginx_log(600).splitlines()
                               if '" 4' in ln or '" 5' in ln][-40:]
    finally:
        clear_flags()
        try:
            throttle(d, False)
        except Exception:
            pass
        L.save_evidence('result_rework3', RESULT)
        d.quit()
        print('DONE shots', len(RESULT['shots']), flush=True)


if __name__ == '__main__':
    main()
