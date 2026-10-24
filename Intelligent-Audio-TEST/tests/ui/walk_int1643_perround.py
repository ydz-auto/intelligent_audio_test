# -*- coding: utf-8 -*-
"""INT-1643 打回第 3 轮：批量评估维度「逐轮设置」→ round_dimensions 提交键运行时取证。

卡面第 2 项后半：核对 round_dimensions 提交键（'-1' 最后一轮）与「-1 叠加合并到实际最后一轮、
按维度 id 去重、基础轮权重优先」的合并口径。

步骤：分组视图 → 组头批量修改 → 评价维度 → 逐轮设置
      → 第 2 轮：A(打断成功数量)+B(打断失败数量, 权重 70)
      → 最后一轮：B(打断失败数量, 权重 30)+C(打断询问数量)
      → 确定 → 抓 POST /testcases/batch 请求体/响应 → GET /testcases/{id} 回读各轮维度与权重。
产物：artifacts/int1643/perround_evidence.json + pr_*.png（浅色）+ pr_dark.png（深色同链路截）
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By

FIX = os.path.join(L.ART, 'perround_fixture.json')
with open(FIX, encoding='utf-8') as f:
    fx = json.load(f)
GROUP = fx['group_name']
CID = fx['case_id']

DIM_A = '打断成功数量'   # id 971
DIM_B = '打断失败数量'   # id 972（两轮都选，验证去重与权重优先）
DIM_C = '打断询问数量'   # id 973
OUT = {'case_id': CID, 'group': GROUP,
       'expect': {'round2': [DIM_A, DIM_B, DIM_C], 'B_weight_from_round2': 70,
                  'B_weight_from_last_round': 30}}
d = None


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


def texts(els):
    return [(e.text or '').strip() for e in els if vis(e)]


def find_dialog(kw):
    ds = [x for x in L.dialogs(d) if kw in (x.text or '')]
    return ds[-1] if ds else None


def menu_items():
    return [x for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if vis(x)]


def open_batch_menu():
    if menu_items():
        return
    btn = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, 'button[aria-label]')
                              if vis(b) and '批量修改' in (b.get_attribute('aria-label') or '')), None), 20)
    L.js_click(d, btn)
    retry(lambda: menu_items() or None, 10)


def open_dims_dialog():
    open_batch_menu()
    mi = retry(lambda: next((x for x in menu_items() if (x.text or '').strip() == '评价维度'), None), 12)
    if mi is None:
        raise RuntimeError('menu item 评价维度 missing: %s' % texts(menu_items()))
    L.clear_fetch_log(d)
    L.js_click(d, mi)
    dlg = retry(lambda: find_dialog('批量设置评估维度'), 25)
    time.sleep(1.0)
    return dlg


def radio(label_kw):
    lb = retry(lambda: next((x for x in find_dialog('批量设置评估维度').find_elements(By.TAG_NAME, 'label')
                             if vis(x) and label_kw in (x.text or '')), None), 12)
    inp = lb.find_elements(By.TAG_NAME, 'input')
    L.js_click(d, inp[0] if inp else lb)
    time.sleep(1.0)


def tab_labels():
    dlg = find_dialog('批量设置评估维度')
    return [t for t in texts(dlg.find_elements(By.TAG_NAME, 'button')) if '轮' in t]


def click_tab(label):
    dlg = find_dialog('批量设置评估维度')
    btn = retry(lambda: next((b for b in dlg.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == label
                              and '关闭' not in (b.get_attribute('aria-label') or '')), None), 12)
    L.js_click(d, btn)
    time.sleep(1.0)
    return label


def chip_click(name):
    """在评估维度云里点选 chip（主维度 chip 带「主」徽章，按名称前缀匹配）。"""
    dlg = find_dialog('批量设置评估维度')
    cloud = dlg.find_element(By.CSS_SELECTOR, "[data-testid='batch-dim-round-cloud']")
    btn = retry(lambda: next((b for b in cloud.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]')
                              if vis(b) and (b.text or '').strip().startswith(name)), None), 10)
    L.js_click(d, btn)
    time.sleep(0.8)
    return {'clicked': (btn.text or '').strip()[:40], 'aria_pressed': btn.get_attribute('aria-pressed')}


def set_param(dim_name, which, value):
    """设置某维度参数卡里的权重/阈值（原生 setter + input 事件，触发 React onChange）。"""
    dlg = find_dialog('批量设置评估维度')
    card = retry(lambda: dlg.find_element(
        By.XPATH, ".//button[@aria-label='移除维度 %s']/ancestor::div[contains(@class,'ring-1')][1]" % dim_name), 10)
    inputs = [i for i in card.find_elements(By.TAG_NAME, 'input') if vis(i)]
    idx = 0 if which == 'weight' else 1
    el = inputs[idx]
    old = el.get_attribute('value')
    d.execute_script(
        """
        const el = arguments[0], v = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, v);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        """, el, str(value))
    time.sleep(0.6)
    return {'dim': dim_name, 'field': which, 'old': old, 'new': el.get_attribute('value')}


def selected_names():
    """当前激活轮次卡片上的已选维度（参数卡标题）。"""
    dlg = find_dialog('批量设置评估维度')
    return texts([b for b in dlg.find_elements(By.CSS_SELECTOR, "button[aria-label^='移除维度']")])


def detail(cid):
    st, p, raw = L.api_json(d, '/testcases/' + cid)
    return st, (p or {}).get('data') or {}, raw


def summarize(x):
    cfg = x.get('config') or {}
    out = []
    for r in (cfg.get('rounds') or []):
        dims = ((r.get('evaluation') or {}).get('dimensions')) or []
        out.append({'n': r.get('round_number'),
                    'dims': [{'id': z.get('id'), 'name': z.get('name'),
                              'weight': z.get('weight'), 'threshold': z.get('threshold')} for z in dims]})
    return {'case_level_dims': cfg.get('dimensions'), 'rounds': out}


def main():
    global d
    d = L.driver()
    L.login(d)

    # 造数基线回读
    st, before, _ = detail(CID)
    OUT['before'] = {'status': st, 'summary': summarize(before)}
    assert st == 200, 'fixture case unreachable: %s' % st

    d.get(L.BASE + '/testcases')
    time.sleep(6)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 20)
    L.js_click(d, opt)
    time.sleep(5)
    hdr = retry(lambda: next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None), 20)
    L.js_click(d, hdr)
    time.sleep(5)
    L.shot(d, 'pr01_group_view')

    dlg = open_dims_dialog()
    OUT['dialog_open_text'] = (dlg.text or '')[:800]
    L.shot(d, 'pr02_dims_all_rounds')

    # 逐轮设置
    radio('逐轮设置')
    dlg = find_dialog('批量设置评估维度')
    OUT['per_round_tabs'] = tab_labels()
    L.shot(d, 'pr03_per_round_tabs')

    # 第 2 轮：A + B（B 权重 70）
    OUT['tab_round2'] = click_tab('第 2 轮')
    OUT['r2_click_A'] = chip_click(DIM_A)
    OUT['r2_click_B'] = chip_click(DIM_B)
    OUT['r2_param_B'] = set_param(DIM_B, 'weight', 70)
    OUT['r2_cards'] = selected_names()
    L.shot(d, 'pr04_round2_AB_weight70')

    # 最后一轮：B（权重 30）+ C
    OUT['tab_last'] = click_tab('最后一轮')
    OUT['last_click_B'] = chip_click(DIM_B)
    OUT['last_param_B'] = set_param(DIM_B, 'weight', 30)
    OUT['last_click_C'] = chip_click(DIM_C)
    OUT['last_cards'] = selected_names()
    L.shot(d, 'pr05_last_BC_weight30')

    # 回到第 2 轮确认两轮参数互不串（权重仍 70）
    OUT['tab_round2_back'] = click_tab('第 2 轮')
    dlg = find_dialog('批量设置评估维度')
    cards_b = dlg.find_elements(
        By.XPATH, ".//button[@aria-label='移除维度 %s']/ancestor::div[contains(@class,'ring-1')][1]" % DIM_B)
    card_b = cards_b[0] if cards_b else None
    OUT['r2_B_weight_after_switch'] = [i.get_attribute('value') for i in
                                       (card_b.find_elements(By.TAG_NAME, 'input') if card_b else []) if vis(i)]

    # 提交并抓包
    L.clear_fetch_log(d)
    btn = retry(lambda: next((b for b in find_dialog('批量设置评估维度').find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == '确定'), None), 10)
    L.js_click(d, btn)
    OUT['submit_clicked_at'] = time.strftime('%H:%M:%S')
    L.shot(d, 'pr06_submitting')
    toasts = L.wait_toast(d, 25)
    OUT['toasts'] = toasts
    time.sleep(3)

    fetch = [e for e in L.fetch_log(d) if '/testcases/batch' in (e.get('url') or '')]
    OUT['batch_calls'] = [{'method': e.get('method'), 'url': e.get('url'), 'status': e.get('status'),
                           'reqBody': e.get('reqBody'), 'resBody': e.get('resBody')} for e in fetch]
    if fetch:
        req = fetch[0].get('reqBody') or ''
        try:
            payload = json.loads(req)
            OUT['round_dimensions_keys'] = list((payload.get('round_dimensions') or {}).keys())
            OUT['round_dimensions'] = payload.get('round_dimensions')
            OUT['payload_round_mode'] = payload.get('round_mode')
            OUT['payload_dimensions'] = payload.get('dimensions')
        except Exception:
            OUT['req_parse_err'] = traceback.format_exc()[-300:]

    # 回读
    st, after, raw = detail(CID)
    OUT['after'] = {'status': st, 'summary': summarize(after), 'raw_head': (raw or '')[:600]}

    # 深色同链路截（重开弹窗逐轮 tab，不提交）
    try:
        L.apply_theme(d, 'dark')
        d.get(L.BASE + '/testcases')
        time.sleep(5)
        t2 = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                 if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
        L.js_click(d, t2)
        time.sleep(1.2)
        o2 = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                 if vis(b) and (b.text or '').strip() == GROUP), None), 20)
        L.js_click(d, o2)
        time.sleep(5)
        h2 = retry(lambda: next((e for e in d.find_elements(
            By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
            if vis(e)), None), 20)
        L.js_click(d, h2)
        time.sleep(4)
        dlg2 = open_dims_dialog()
        radio('逐轮设置')
        click_tab('最后一轮')
        chip_click(DIM_B)
        chip_click(DIM_C)
        L.shot(d, 'pr07_per_round_dark')
        # 取消，不提交
        cancel = next((b for b in find_dialog('批量设置评估维度').find_elements(By.TAG_NAME, 'button')
                       if vis(b) and (b.text or '').strip() == '取消'), None)
        if cancel:
            L.js_click(d, cancel)
        time.sleep(1)
        L.apply_theme(d, 'light')
    except Exception:
        OUT['dark_err'] = traceback.format_exc()[-600:]


try:
    main()
except Exception:
    OUT['fatal'] = traceback.format_exc()[-2000:]
finally:
    try:
        OUT['fetch_tail'] = [{'m': e.get('method'), 'u': (e.get('url') or '')[:80], 's': e.get('status')}
                             for e in L.fetch_log(d)][-10:]
    except Exception:
        pass
    L.save_evidence('perround_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
