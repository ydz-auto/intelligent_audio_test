# -*- coding: utf-8 -*-
"""INT-1643 批量七窗逐条提交 + GET 回读（INT-1538 遗留项 1/2）。

七窗：调整分组 / 用例专属参数 / 播放设备 / 声压 / 评价维度 / 管理标签 / 噪声。
每窗：打开 → 交互 → 提交 → 抓 POST /testcases/batch 请求体与响应 → GET /testcases/{id} 回读。
产物：artifacts/int1643/batch_evidence.json + b*.png
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

GROUP = '接线测试_INT1643_批量组'
TARGET_GROUP = '接线测试_INT1643_目标组'
CASES = {
    'A': '8bb822a4-243c-4f20-87e5-ae015028d724',
    'B': '38a3fa72-1561-425d-b467-9b46ca209e23',
    'C': '701fd9e8-dc88-456f-b5e6-04036fe37483',
}
TAG = '接线测试_INT1643_标签'
OUT = {'sections': {}}


def vis(el):
    try:
        return el.is_displayed()
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


def section(name):
    def deco(fn):
        t0 = time.time()
        try:
            r = fn()
            OUT['sections'][name] = {'ok': True, 'dur': round(time.time() - t0, 1), 'result': r}
        except Exception:
            OUT['sections'][name] = {'ok': False, 'err': traceback.format_exc()[-900:],
                                     'dur': round(time.time() - t0, 1)}
        L.save_evidence('batch_evidence', OUT)
        return fn
    return deco


def body():
    return L.body_text(d)


def find_dialog(kw):
    ds = [x for x in L.dialogs(d) if kw in (x.text or '')]
    return ds[-1] if ds else None


def menu_items():
    return [x for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if vis(x)]


def open_batch_menu():
    if menu_items():
        return
    btn = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, 'button[aria-label]')
                              if vis(b) and '批量修改' in (b.get_attribute('aria-label') or '')), None), 15)
    L.js_click(d, btn)
    retry(lambda: menu_items() or None, 10)


def open_dialog(label, title_kw):
    open_batch_menu()
    mi = retry(lambda: next((x for x in menu_items() if (x.text or '').strip() == label), None), 10)
    if mi is None:
        L.shot(d, 'err_no_menu_item_' + label)
        raise RuntimeError('batch menu item missing: %s (menu=%s)' %
                           (label, [(x.text or '')[:20] for x in menu_items()]))
    L.clear_fetch_log(d)
    L.js_click(d, mi)
    dlg = retry(lambda: find_dialog(title_kw), 20)
    time.sleep(0.8)
    return dlg


def close_dialog():
    for x in L.dialogs(d):
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if (c.text or '').strip() in ('取消', 'Close') and vis(c):
                try:
                    L.js_click(d, c)
                except Exception:
                    pass
                time.sleep(0.8)
                return


def click_text(scope, text, exact=True):
    for tag in ('button', 'label', 'span', 'div'):
        for e in scope.find_elements(By.TAG_NAME, tag):
            t = (e.text or '').strip()
            if (t == text if exact else text in t) and vis(e):
                L.js_click(d, e)
                return e
    return None


def pick_select(dlg, trigger_text, option_text):
    trig = retry(lambda: next((e for e in dlg.find_elements(
        By.CSS_SELECTOR, "[role='combobox'], button") if vis(e) and trigger_text in (e.text or '')), None), 12)
    L.js_click(d, trig)
    time.sleep(1.0)
    opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(o)]
    OUT.setdefault('_last_options', {})[trigger_text] = [(o.text or '').strip()[:40] for o in opts]
    opt = next((o for o in opts if option_text in (o.text or '')), None)
    if opt is None:
        raise RuntimeError('option not found: %s in %s' % (option_text, [(o.text or '')[:30] for o in opts]))
    L.js_click(d, opt)
    time.sleep(0.8)
    return (opt.text or '').strip()


def click_radio(dlg, label_text):
    for lb in dlg.find_elements(By.TAG_NAME, 'label'):
        if vis(lb) and label_text in (lb.text or ''):
            inp = lb.find_elements(By.TAG_NAME, 'input')
            if inp:
                L.js_click(d, inp[0])
            else:
                L.js_click(d, lb)
            time.sleep(0.6)
            return True
    raise RuntimeError('radio not found: %s' % label_text)


def set_input(el, value):
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(str(value))


def submit(dlg):
    btn = next((b for b in dlg.find_elements(By.TAG_NAME, 'button')
                if vis(b) and (b.text or '').strip() == '确定'), None)
    if btn is None:
        raise RuntimeError('no 确定 button')
    L.js_click(d, btn)
    time.sleep(2.5)
    return L.wait_toast(d, 20)


def batch_fetch():
    return [e for e in L.fetch_log(d) if '/testcases/batch' in (e.get('url') or '')]


def detail(cid):
    st, p, raw = L.api_json(d, '/testcases/' + cid)
    return st, (p or {}).get('data') or p or {}, raw


def summarize_case(cid):
    st, x, _ = detail(cid)
    cfg = x.get('config') or {}
    rounds = []
    for r in (cfg.get('rounds') or []):
        audios = [(a.get('audio_id'), a.get('playback_device_id'), a.get('playback_device_name'), a.get('spl'))
                  for a in (r.get('audios') or [])]
        rounds.append({'n': r.get('round_number'), 'audios': audios,
                       'dims': (r.get('evaluation') or {}).get('dimensions')})
    return {'status': st, 'group_id': x.get('group_id'), 'group_name': x.get('group_name'),
            'tags': x.get('tags'), 'algorithm_type': x.get('algorithm_type'),
            'rounds': rounds, 'dimensions': cfg.get('dimensions'),
            'background_noise': cfg.get('background_noise')}


def batch_body():
    out = []
    for e in batch_fetch():
        out.append({'status': e.get('status'), 'req': (e.get('reqBody') or '')[:1200],
                    'res': (e.get('resBody') or '')[:600]})
    return out


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    # 分组解析（存在即复用）+ 把夹具移回本组（上一轮调整分组已把它们移到目标组）
    st, p, _ = L.api_json(d, '/groups?per_page=200&page=1')
    groups = ((p or {}).get('data') or {}).get('items') or []
    gid = next((g['id'] for g in groups if g.get('name') == GROUP), None)
    tgid = next((g['id'] for g in groups if g.get('name') == TARGET_GROUP), None)
    if tgid is None:
        st, p, _ = L.api_json(d, '/groups', 'POST', {'name': TARGET_GROUP, 'description': 'INT-1643 批量调整目标组'})
        OUT['target_group_create'] = (st, (json.dumps(p, ensure_ascii=False)[:300] if p else ''))
        tgid = ((p or {}).get('data') or {}).get('id')
    else:
        OUT['target_group_create'] = ('reuse', tgid)
    OUT['group_ids'] = {'batch': gid, 'target': tgid}
    if gid:
        ids = list(CASES.values())
        st, p, raw = L.api_json(d, '/testcases/batch', 'POST',
                                {'action': 'move_to_group', 'ids': ids, 'target_group_id': gid})
        OUT['fixture_move_back'] = (st, (raw or '')[:200])
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 15)
    L.js_click(d, opt)
    time.sleep(5)
    hdr = retry(lambda: next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None), 15)
    L.js_click(d, hdr)
    time.sleep(5)
    OUT['before'] = {k: summarize_case(v) for k, v in CASES.items()}
    L.save_evidence('batch_evidence', OUT)

    # 调整分组放最后（执行后用例离开本组，组头批量入口消失）

    @section('params')
    def _():
        dlg = open_dialog('用例专属参数', '批量设置用例专属参数')
        opts = {}
        trig = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox'], button")
                                   if vis(e) and '请选择算法' in (e.text or '')), None), 12)
        L.js_click(d, trig)
        time.sleep(1.2)
        opts['algorithm'] = [(o.text or '').strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(o)]
        opt = next((o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                    if vis(o) and '小艺' in (o.text or '')), None)
        if opt is None:
            opt = next((o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(o)), None)
        if opt is not None:
            L.js_click(d, opt)
            time.sleep(2.5)
        dlg = find_dialog('批量设置用例专属参数')
        L.shot(d, 'b02_params_dialog')
        opts['dialog_after'] = (dlg.text or '')[:700]
        opts['inputs'] = [{'aria': i.get_attribute('aria-label'), 'ph': i.get_attribute('placeholder'),
                           'type': i.get_attribute('type'), 'val': i.get_attribute('value')}
                          for i in dlg.find_elements(By.TAG_NAME, 'input') if vis(i)]
        fill_count = len([i for i in dlg.find_elements(By.TAG_NAME, 'input')
                          if vis(i) and (i.get_attribute('type') or 'text') in ('text', 'number')
                          and i.get_attribute('aria-label')])
        opts['fillable_fields'] = fill_count
        if fill_count == 0:
            opts['verdict'] = '环境缺口：算法无专属参数字段，无法逐字段提交'
            close_dialog()
            return opts
        toasts = submit(dlg)
        time.sleep(2)
        opts['toasts'] = toasts
        opts['fetch'] = batch_body()
        opts['after_A'] = summarize_case(CASES['A'])
        return opts

    @section('device')
    def _():
        dlg = open_dialog('播放设备', '批量设置播放设备')
        closed_before = None
        pick_select(dlg, '请选择设备', '设备正面（0.5m+0°）')
        trig = next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox'], button")
                     if vis(e) and '设备正面' in (e.text or '')), None)
        closed_before = (trig.text or '').strip() if trig else None
        OUT['device_select_closed_text'] = closed_before
        L.shot(d, 'b03_device_dialog')
        toasts = submit(dlg)
        time.sleep(2.5)
        return {'closed_state_text': closed_before, 'toasts': toasts, 'fetch': batch_body(),
                'after_A': summarize_case(CASES['A'])}

    @section('spl')
    def _():
        dlg = open_dialog('声压', '批量设置声压级')
        inp = retry(lambda: next((i for i in dlg.find_elements(By.TAG_NAME, 'input')
                                  if vis(i) and i.get_attribute('aria-label') == '声压级 dB'), None), 10)
        set_input(inp, '72')
        L.shot(d, 'b04_spl_dialog')
        toasts = submit(dlg)
        time.sleep(2.5)
        return {'toasts': toasts, 'fetch': batch_body(), 'after_A': summarize_case(CASES['A'])}

    @section('dimensions')
    def _():
        dlg = open_dialog('评价维度', '批量设置评估维度')
        L.shot(d, 'b05_dims_dialog_all')
        click_radio(dlg, '指定轮次（统一设置）')
        time.sleep(1.0)
        dlg = find_dialog('批量设置评估维度')
        labels = [lb.text.strip() for lb in dlg.find_elements(By.TAG_NAME, 'label') if vis(lb)]
        round_labels = [t for t in labels if t.startswith('第') and '轮' in t]
        OUT['dims_specific_round_labels'] = round_labels
        L.shot(d, 'b06_dims_specific_rounds')
        # 逐轮模式 tab
        click_radio(dlg, '逐轮设置（每轮可不同）')
        time.sleep(1.0)
        dlg = find_dialog('批量设置评估维度')
        per_round_text = (dlg.text or '')[:600]
        OUT['dims_per_round_text'] = per_round_text
        L.shot(d, 'b07_dims_per_round')
        # 回到指定轮次，选第 1 轮 + 一个主维度
        click_radio(dlg, '指定轮次（统一设置）')
        time.sleep(0.8)
        dlg = find_dialog('批量设置评估维度')
        dim_btn = next((b for b in dlg.find_elements(By.TAG_NAME, 'button')
                        if vis(b) and (b.text or '').strip().startswith('打断成功数量')), None)
        if dim_btn is not None:
            L.js_click(d, dim_btn)
            time.sleep(0.8)
        L.shot(d, 'b08_dims_selected')
        toasts = submit(dlg)
        time.sleep(2.5)
        return {'specific_round_labels': round_labels, 'per_round_text': per_round_text,
                'toasts': toasts, 'fetch': batch_body(), 'after_A': summarize_case(CASES['A'])}

    @section('tags')
    def _():
        dlg = open_dialog('管理标签', '批量管理标签')
        inp = retry(lambda: next((i for i in dlg.find_elements(By.TAG_NAME, 'input')
                                  if vis(i) and (i.get_attribute('placeholder') or '').startswith('输入标签')), None), 10)
        set_input(inp, TAG)
        inp.send_keys(Keys.ENTER)
        time.sleep(0.8)
        L.shot(d, 'b09_tags_dialog')
        toasts = submit(dlg)
        time.sleep(2.5)
        return {'toasts': toasts, 'fetch': batch_body(), 'after_A': summarize_case(CASES['A'])}

    @section('noise')
    def _():
        dlg = open_dialog('噪声', '批量设置噪声')
        L.shot(d, 'b10_noise_dialog')
        text0 = (dlg.text or '')
        btn = retry(lambda: next((b for b in dlg.find_elements(By.TAG_NAME, 'button')
                                  if vis(b) and '点击选择噪声音频' in (b.text or '')), None), 12)
        L.clear_fetch_log(d)
        L.js_click(d, btn)
        time.sleep(4)
        picker = None
        for kw in ('选择音频文件', '选择噪声音频', '噪声音频'):
            cand = find_dialog(kw)
            if cand is not None:
                picker = cand
                break
        OUT['noise_picker_text'] = (picker.text or '')[:600] if picker else 'NO PICKER'
        OUT['noise_picker_fetch'] = [(e.get('method'), (e.get('url') or '')[:90], e.get('status'))
                                     for e in L.fetch_log(d)]
        L.shot(d, 'b11_noise_picker')
        close_dialog()
        time.sleep(0.8)
        OUT['noise_dialog_text'] = text0[:600]
        OUT['noise_dev_hint_present'] = '演示提示条' in text0 or '导入时未匹配到音频' in text0
        close_dialog()
        return {'picker_text': OUT['noise_picker_text'][:300],
                'fetch': OUT['noise_picker_fetch'],
                'dev_hint_in_batch_dialog': OUT['noise_dev_hint_present']}

    @section('group')
    def _():
        dlg = open_dialog('调整分组', '批量调整分组')
        L.shot(d, 'b01_group_dialog')
        pick_select(dlg, '请选择分组', TARGET_GROUP)
        OUT['group_mode_checked'] = [i.get_attribute('checked') for i in dlg.find_elements(By.CSS_SELECTOR, "input[type='radio']")]
        toasts = submit(dlg)
        time.sleep(2.5)
        return {'toasts': toasts, 'fetch': batch_body(),
                'after_A': summarize_case(CASES['A']), 'after_B': summarize_case(CASES['B'])}
finally:
    OUT['after'] = {}
    try:
        for k, v in CASES.items():
            OUT['after'][k] = summarize_case(v)
    except Exception:
        pass
    L.save_evidence('batch_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
