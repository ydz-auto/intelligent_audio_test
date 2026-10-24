# -*- coding: utf-8 -*-
"""INT-1643 续测（打回返工轮）：七类批量弹窗 + 抽屉五步的真实加载态 / 真实失败态；
INT-1642 五项复测缺图补齐（A1/A2/A4/A5/A6/D1/D3/E2）。

基座：frontend-react @ HEAD + INT-1642 交付 492fe09b4（临时副本构建），
nginx:alpine 容器 15933 反代 api_gateway:5000，`/audit/fail_*` flag 文件在网关层注入 502
（真实 HTTP 失败，不在页面里 mock）；加载态用 CDP Network.emulateNetworkConditions 限速
让真实请求在途，断言在途期间的 UI。
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
REAL_KW = 'DD100'
RESULT = {'stages': {}, 'net': [], 'shots': []}


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
                         'error': (e.get('resBody') or '')[:160] if e.get('status', 200) >= 400 else None})
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
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 40)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 20)
    L.js_click(d, opt)
    time.sleep(7)
    hdr = next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None)
    if hdr is not None:
        L.js_click(d, hdr)
        time.sleep(6)


def select_rows(d, n=3):
    cbs = [e for e in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']") if vis(e)]
    labels = [(c.get_attribute('aria-label') or '') for c in cbs]
    rows = [c for c in cbs if '全选' not in (c.get_attribute('aria-label') or '')]
    if len(rows) < n:
        rows = cbs[-n:]
    for c in rows[:n]:
        L.js_click(d, c)
        time.sleep(0.4)
    time.sleep(1.5)
    return labels[:6]


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
    L.save_evidence('result', RESULT)
    print('STAGE', stage, json.dumps(data, ensure_ascii=False)[:900])


# ---------------- 批量七窗 ----------------

def stage_group(d):
    data = {'title': '批量调整分组'}
    open_bulk(d, '批量调整分组')
    dlg = cur_dialog(d, '批量调整分组')
    # 目标分组 Select
    L.js_click(d, combo(dlg, '请选择分组'))
    time.sleep(1.0)
    opt = retry(lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                              if vis(e) and GROUP in (e.text or '')), None), 10)
    L.js_click(d, opt)
    time.sleep(0.8)
    data['selected_group'] = GROUP
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    click_submit(d, dlg)
    time.sleep(1.0)
    shot(d, 'L_group_loading')
    data['loading_ui'] = '确定 按钮进入提交中（Spinner + 禁用）'
    time.sleep(7)
    shot(d, 'E_group_error')
    data['error_text'] = (dlg.text or '')[:500]
    data['toast'] = L.body_text(d)[-300:]
    data['net'] = net_log(d)
    data['dialog_still_open'] = bool(cur_dialog(d, '批量调整分组', timeout=3))
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.5)
    close_dialog(d)
    record('group', data)


def stage_params(d):
    data = {'title': '批量设置专属参数'}
    throttle(d, True)
    open_bulk(d, '批量设置专属参数')
    dlg = cur_dialog(d, '批量设置专属参数')
    time.sleep(1.0)
    shot(d, 'L_params_loading')
    data['loading_ui'] = '加载算法列表...'
    throttle(d, False)
    time.sleep(4)
    # 选算法（此时 fail_schema 未开）
    L.js_click(d, combo(dlg, '请选择算法'))
    time.sleep(0.8)
    opts = [(e.text or '').strip() for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e)]
    data['algorithm_options'] = opts
    flag('fail_schema', True)
    L.js_click(d, next(e for e in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(e)))
    L.clear_fetch_log(d)
    time.sleep(4)
    shot(d, 'E_params_error')
    data['error_text'] = (dlg.text or '')[:500]
    data['net'] = net_log(d)
    flag('fail_schema', False)
    throttle(d, True)
    L.js_click(d, btn(dlg, '重试', timeout=10))
    time.sleep(1.2)
    shot(d, 'L_params_form_loading')
    data['loading_ui2'] = '正在加载算法参数表单...'
    throttle(d, False)
    time.sleep(5)
    shot(d, 'N_params_form')
    data['normal_text'] = (dlg.text or '')[:400]
    data['net_retry'] = net_log(d)
    close_dialog(d)
    record('params', data)


def stage_device(d):
    data = {'title': '批量设置播放设备'}
    throttle(d, True)
    open_bulk(d, '批量设置播放设备')
    dlg = cur_dialog(d, '批量设置播放设备')
    time.sleep(1.0)
    shot(d, 'L_device_loading')
    data['loading_ui'] = '播放设备列表加载中'
    throttle(d, False)
    time.sleep(5)
    shot(d, 'N_device_list')
    data['device_list_text'] = (dlg.text or '')[:300]
    flag('fail_devices', True)
    L.clear_fetch_log(d)
    scan = retry(lambda: next((b for b in buttons(dlg) if '扫描' in (b.text or '')), None), 10)
    L.js_click(d, scan)
    time.sleep(5)
    shot(d, 'E_device_scan_error')
    data['error_text'] = (dlg.text or '')[:500]
    data['net'] = net_log(d)
    flag('fail_devices', False)
    time.sleep(4)
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
    time.sleep(1.0)
    shot(d, 'L_spl_loading')
    time.sleep(7)
    shot(d, 'E_spl_error')
    data['error_text'] = (dlg.text or '')[:400]
    data['net'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.5)
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
    time.sleep(1.0)
    shot(d, 'L_dims_loading')
    time.sleep(7)
    shot(d, 'E_dims_error')
    data['error_text'] = (dlg.text or '')[-400:]
    data['net'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.5)
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
    data['chips'] = (dlg.text or '')[:300]
    flag('fail_batch', True)
    throttle(d, True)
    L.clear_fetch_log(d)
    click_submit(d, dlg)
    time.sleep(1.0)
    shot(d, 'L_tags_loading')
    time.sleep(7)
    shot(d, 'E_tags_error')
    data['error_text'] = (dlg.text or '')[:400]
    data['net'] = net_log(d)
    throttle(d, False)
    flag('fail_batch', False)
    time.sleep(1.5)
    close_dialog(d)
    record('tags', data)


def stage_noise(d):
    data = {'title': '批量设置噪声'}
    flag('fail_audios', True)
    open_bulk(d, '批量设置噪声')
    dlg = cur_dialog(d, '批量设置噪声')
    L.clear_fetch_log(d)
    time.sleep(5)
    shot(d, 'E_noise_error')
    data['error_text'] = (dlg.text or '')[:500]
    data['net'] = net_log(d)
    flag('fail_audios', False)
    throttle(d, True)
    L.js_click(d, btn(dlg, '重试', timeout=10))
    time.sleep(1.2)
    shot(d, 'L_noise_loading')
    data['loading_ui'] = '噪声数据加载中'
    throttle(d, False)
    time.sleep(6)
    shot(d, 'N_noise_empty')
    data['normal_text'] = (dlg.text or '')[:400]
    data['net_retry'] = net_log(d)
    close_dialog(d)
    record('noise', data)


# ---------------- 导出 ----------------

def stage_export(d):
    data = {'title': '导出'}
    b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                            if vis(x) and (x.text or '').strip() == '导出'), None), 20)
    L.js_click(d, b)
    dlg = cur_dialog(d, '导出')
    time.sleep(2)
    shot(d, 'D1_export_dialog')
    # 按当前筛选条件导出
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
    data['loading_ui'] = '导出中…'
    throttle(d, False)
    time.sleep(8)
    data['after_text'] = (dlg.text or '')[:300]
    data['net_ok'] = net_log(d)
    shot(d, 'D3_export_dark')
    L.apply_theme(d, 'dark')
    shot(d, 'D3_dark_export_result')
    L.apply_theme(d, 'light')
    time.sleep(1)
    # 失败态（网关层 502）
    flag('fail_export', True)
    L.clear_fetch_log(d)
    b3 = retry(lambda: next((x for x in buttons(dlg) if '导出' in (x.text or '')), None), 8)
    L.js_click(d, b3)
    time.sleep(5)
    shot(d, 'E1_export_error')
    L.apply_theme(d, 'dark')
    shot(d, 'E2_export_error_dark')
    L.apply_theme(d, 'light')
    data['error_text'] = L.body_text(d)[-400:]
    data['net_fail'] = net_log(d)
    flag('fail_export', False)
    close_dialog(d)
    record('export', data)


# ---------------- 抽屉五步 ----------------

def open_drawer(d, kw=REAL_KW):
    row = retry(lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "button[aria-label*='编辑用例']")
                              if vis(e) and kw in (e.get_attribute('aria-label') or '')), None), 24)
    if row is None:
        # aria-label 只有「编辑用例」→ 用行文本定位
        row = retry(lambda: next((e for e in d.find_elements(By.XPATH,
                     "//*[contains(text(),'%s')]/ancestor::*[self::tr or contains(@class,'row')][1]//button[contains(@aria-label,'编辑用例')]" % kw)
                     if vis(e)), None), 24)
    L.js_click(d, row)
    return retry(lambda: next((x for x in dialogs(d) if '参考参数' in (x.text or '')), None), 40)


def tab(d, dr, label):
    t = next((x for x in dr.find_elements(By.CSS_SELECTOR, "[role='tab']")
              if vis(x) and (x.text or '').strip() == label), None)
    if t is None:
        return None
    L.js_click(d, t)
    time.sleep(2.5)
    return t


def stage_drawer(d, tab_labels):
    data = {'title': '抽屉五步', 'tabs': []}
    dr = open_drawer(d)
    data['tabs_seen'] = [ (x.text or '').strip() for x in dr.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]
    for i, label in enumerate(tab_labels, start=1):
        if tab(d, dr, label) is None:
            data['tabs'].append({'label': label, 'missing': True})
            continue
        time.sleep(1.5)
        shot(d, 'A%d_%s' % (i, label.replace('与', '_').replace(' ', '')))
        txt = (dr.text or '')[:600]
        data['tabs'].append({'label': label, 'text': txt})
    # 深色
    L.apply_theme(d, 'dark')
    shot(d, 'A7_drawer_dark')
    L.apply_theme(d, 'light')
    record('drawer_tabs', data)
    # 参考参数：真实后端 400 → 读取失败 + 重试
    ref = {'title': '参考参数错误态'}
    tab(d, dr, '参考参数')
    time.sleep(4)
    shot(d, 'A5_ref_error')
    ref['error_text'] = (dr.text or '')[-500:]
    L.clear_fetch_log(d)
    rb = retry(lambda: next((b for b in buttons(dr) if '重试' in (b.text or '')), None), 8)
    if rb:
        L.js_click(d, rb)
        time.sleep(0.6)
        shot(d, 'A6_ref_retry_loading')
        time.sleep(5)
        shot(d, 'A6_ref_after_retry')
        ref['after_retry'] = (dr.text or '')[-500:]
        ref['net'] = net_log(d)
    record('ref_params', ref)
    # 算法参数：网关层 502 失败态 + 节流加载态
    algo = {'title': '抽屉算法参数'}
    flag('fail_schema', True)
    L.clear_fetch_log(d)
    tab(d, dr, '算法参数')
    time.sleep(4)
    shot(d, 'E_drawer_algo_error')
    algo['error_text'] = (dr.text or '')[:500]
    algo['net'] = net_log(d)
    flag('fail_schema', False)
    throttle(d, True)
    rb = retry(lambda: next((b for b in buttons(dr) if '重试' in (b.text or '')), None), 8)
    if rb:
        L.js_click(d, rb)
        time.sleep(1.2)
        shot(d, 'L_drawer_algo_loading')
    throttle(d, False)
    time.sleep(5)
    shot(d, 'N_drawer_algo')
    record('drawer_algo', algo)
    # 噪声与干扰：播放设备失败态
    noise = {'title': '抽屉噪声与干扰'}
    flag('fail_devices', True)
    L.clear_fetch_log(d)
    tab(d, dr, '噪声与干扰')
    time.sleep(4)
    shot(d, 'E_drawer_noise_error')
    noise['error_text'] = (dr.text or '')[:600]
    noise['net'] = net_log(d)
    flag('fail_devices', False)
    record('drawer_noise', noise)
    close_dialog(d)


def main():
    clear_flags()
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases')
        time.sleep(8)
        enter_group(d)
        labels = select_rows(d, 3)
        print('checkbox labels', labels)
        RESULT['selection'] = labels
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
        # 抽屉在干净页面重开
        d.get(L.BASE + '/testcases')
        time.sleep(8)
        enter_group(d)
        try:
            stage_drawer(d, ['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数'])
        except Exception:
            record('drawer', {'exception': traceback.format_exc()[-1500:]})
    finally:
        clear_flags()
        throttle(d, False)
        L.save_evidence('result', RESULT)
        d.quit()
        print('DONE shots', len(RESULT['shots']))


if __name__ == '__main__':
    main()
