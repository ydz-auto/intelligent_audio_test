# -*- coding: utf-8 -*-
"""INT-1483 Phase C：分组管理弹窗（空态 / 新建 / 编辑 / 排序·图标落库 / 删除 + 回读）；
Phase D：导入算法弹窗（JSON 校验 / 真实导入 / 列表刷新 / 清理）。"""
import json
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'C' + H.RUN_TAG
G1 = f'接线测试_INT1483_分组A_{TAG}'
G1B = G1 + '_改'
G2 = f'接线测试_INT1483_分组B_{TAG}'
IMP_TYPE = f'itest1483_imp_{TAG.lower()}'
IMP_NAME = f'接线测试_INT1483_导入_{TAG}'
OUT = {'g1': G1, 'g1b': G1B, 'g2': G2, 'imp_type': IMP_TYPE, 'imp_name': IMP_NAME}


def wtext(text, timeout=20):
    WebDriverWait(d, timeout).until(lambda x: text in H.body_text(x))


def find(xp):
    return WebDriverWait(d, 15).until(EC.presence_of_element_located((By.XPATH, xp)))


def set_input(el, v):
    el.clear()
    el.send_keys(v)


def save_ev():
    H.save_evidence('phaseCD_group_import', OUT)


def open_group_dialog():
    if '算法分组管理' in H.body_text(d):
        return
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    H.click_menuitem(d, '分组管理')
    wtext('算法分组管理')
    time.sleep(0.8)


def groups_api():
    st, pay, _ = H.api_json(d, '/algorithm/groups')
    return (pay or {}).get('data', {}).get('items') or []


def open_group_form(name=None):
    if name:
        H.js_click(d, find(f"//button[@aria-label='编辑分组 {name}']"))
    else:
        H.js_click(d, find("//button[contains(normalize-space(.), '新建分组')]"))
    WebDriverWait(d, 15).until(EC.presence_of_element_located((By.ID, 'group-name')))
    time.sleep(0.8)


def fill_group(name, order, icon, desc):
    set_input(d.find_element(By.ID, 'group-name'), name)
    set_input(d.find_element(By.ID, 'group-order'), order)
    set_input(d.find_element(By.ID, 'group-icon'), icon)
    set_input(d.find_element(By.ID, 'group-desc'), desc)
    time.sleep(0.3)


def submit_group():
    H.clear_fetch_log(d)
    H.js_click(d, find("//form//button[@type='submit' and contains(normalize-space(.), '保存')]"))
    H.wait_toast(d, 20)
    time.sleep(1.5)
    return [(e['method'], e['url'], e['status'], e.get('reqBody')) for e in H.fetch_log(d, '/algorithm/groups')
            if e['method'] in ('POST', 'PUT')]


d = H.driver()
try:
    print('LOGIN:', H.login(d))
    H.goto_page(d)

    # ---------- C1 分组管理：空态 ----------
    H.clear_fetch_log(d)
    open_group_dialog()
    OUT['dialog_open_fetches'] = [(e['method'], e['url'], e['status']) for e in H.fetch_log(d, '/algorithm/groups')]
    OUT['empty_state'] = '暂无分组' in H.body_text(d) and '共 0 个分组' in H.body_text(d)
    H.shot(d, 'C1_group_empty_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'C1_group_empty_dark')
    H.apply_theme(d, 'light')

    # ---------- C2 新建分组 A（排序 7 / 图标 mic） ----------
    open_group_form()
    OUT['form_defaults'] = {
        'order': d.find_element(By.ID, 'group-order').get_attribute('value'),
        'name': d.find_element(By.ID, 'group-name').get_attribute('value'),
    }
    # 必填留空：保存禁用
    OUT['save_disabled_when_empty'] = not d.find_element(By.XPATH, "//form//button[@type='submit']").is_enabled()
    fill_group(G1, '7', 'mic', '接线测试分组A描述')
    OUT['save_enabled_after_fill'] = d.find_element(By.XPATH, "//form//button[@type='submit']").is_enabled()
    H.shot(d, 'C2_group_form_light')
    OUT['create_fetches'] = submit_group()
    groups = groups_api()
    g1 = next((g for g in groups if g.get('name') == G1), None)
    OUT['g1_after_create'] = g1
    OUT['g1_persisted'] = g1 is not None
    OUT['dialog_rows_after_create'] = len(d.find_elements(By.CSS_SELECTOR, "table tbody tr"))
    OUT['dialog_text_after_create'] = H.body_text(d)[-800:]
    H.shot(d, 'C2_group_created_light')
    save_ev()

    # ---------- C3 新建分组 B ----------
    open_group_form()
    fill_group(G2, '3', 'sparkles', '接线测试分组B描述')
    OUT['create_fetches_b'] = submit_group()
    groups = groups_api()
    OUT['groups_after_b'] = [{k: g.get(k) for k in ('id', 'name', 'icon', 'display_order')} for g in groups]
    H.shot(d, 'C3_group_two_light')

    # 列表分组筛选下拉选项数（groups + 全部）
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(1)
    if '算法分组管理' in H.body_text(d):
        H.js_click(d, d.find_element(By.XPATH, "//button[contains(@aria-label,'Close')]"))
        time.sleep(0.8)
    H.clear_fetch_log(d)
    trg = d.find_element(By.CSS_SELECTOR, "button[aria-label='分组']")
    H.js_click(d, trg)
    time.sleep(0.7)
    opts = [o.text for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")]
    OUT['list_group_facet'] = {'options': opts, 'api_groups': len(groups_api())}
    H.shot(d, 'C3_list_group_facet_light')
    H.js_click(d, trg)
    time.sleep(0.5)

    # ---------- C4 编辑分组 A（名称/描述/图标/排序） ----------
    open_group_dialog()
    open_group_form(G1)
    OUT['edit_form_prefill'] = {
        'name': d.find_element(By.ID, 'group-name').get_attribute('value'),
        'order': d.find_element(By.ID, 'group-order').get_attribute('value'),
        'icon': d.find_element(By.ID, 'group-icon').get_attribute('value'),
        'desc': d.find_element(By.ID, 'group-desc').get_attribute('value'),
    }
    fill_group(G1B, '9', 'mic2', '接线测试分组A描述_改')
    OUT['edit_fetches'] = submit_group()
    groups = groups_api()
    OUT['g1_after_edit'] = next((g for g in groups if g.get('name') == G1B), None)
    OUT['g1_old_name_gone'] = not any(g.get('name') == G1 for g in groups)
    OUT['dialog_text_after_edit'] = H.body_text(d)[-700:]
    H.shot(d, 'C4_group_edited_light')
    save_ev()

    # ---------- C5 删除分组 B（取消 + 确认） ----------
    H.js_click(d, find(f"//button[@aria-label='删除分组 {G2}']"))
    time.sleep(0.8)
    OUT['delete_dialog_text'] = '删除分组' in H.body_text(d)
    H.shot(d, 'C5_group_delete_confirm_light')
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]"))
    time.sleep(0.6)
    OUT['delete_cancelled_present'] = any(g.get('name') == G2 for g in groups_api())
    H.js_click(d, find(f"//button[@aria-label='删除分组 {G2}']"))
    time.sleep(0.8)
    H.clear_fetch_log(d)
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '删除')]"))
    H.wait_toast(d, 20)
    time.sleep(1.5)
    OUT['delete_fetches'] = [(e['method'], e['url'], e['status']) for e in H.fetch_log(d, '/algorithm/groups')]
    OUT['groups_after_delete'] = [{k: g.get(k) for k in ('id', 'name')} for g in groups_api()]
    H.shot(d, 'C5_group_after_delete_light')
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.8)

    # ---------- D1 导入弹窗：JSON 校验 ----------
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    H.click_menuitem(d, '导入算法')
    wtext('粘贴或上传算法定义 JSON')
    time.sleep(0.7)
    H.shot(d, 'D1_import_dialog_light')
    ta = d.find_element(By.CSS_SELECTOR, "textarea[aria-label='算法定义 JSON']")
    OUT['import_btn_disabled_empty'] = not d.find_element(By.XPATH, "//button[contains(normalize-space(.), '导入') and not(contains(normalize-space(.), '导入算法'))]").is_enabled()
    ta.send_keys('{not json')
    H.js_click(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '导入') and not(contains(normalize-space(.), '导入算法'))]"))
    time.sleep(1)
    OUT['json_error'] = 'JSON 格式错误' in H.body_text(d)
    OUT['json_error_text'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, "[role='alert']")]
    H.shot(d, 'D1_import_invalid_light')
    # 非数组
    ta.clear()
    ta.send_keys('{"type":"x"}')
    H.js_click(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '导入') and not(contains(normalize-space(.), '导入算法'))]"))
    time.sleep(1)
    OUT['array_error'] = '期望算法定义数组' in H.body_text(d)

    # ---------- D2 真实导入 ----------
    payload = [{
        'type': IMP_TYPE,
        'name': IMP_NAME,
        'group_id': None,
        'display_order': 5,
        'status': 'offline',
        'description': '接线测试导入（INT-1483）',
        'device_params': [],
        'api_params': [],
        'case_params': [],
        'reference_params': [],
        'mappings': {'device': [], 'api': [], 'evaluation': []},
        'associated_dimensions': [],
    }]
    ta.clear()
    ta.send_keys(json.dumps(payload, ensure_ascii=False, indent=2))
    H.clear_fetch_log(d)
    H.js_click(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '导入') and not(contains(normalize-space(.), '导入算法'))]"))
    toasts = H.wait_toast(d, 30)
    time.sleep(2)
    OUT['import_toasts'] = toasts
    OUT['import_fetches'] = [
        {'method': e['method'], 'url': e['url'], 'status': e['status'],
         'req': (json.loads(e['reqBody']) if e.get('reqBody') else None),
         'res': (e.get('resBody') or '')[:300]}
        for e in H.fetch_log(d, '/algorithm/import')]
    OUT['dialog_closed_after_import'] = '粘贴或上传算法定义 JSON' not in H.body_text(d)
    det = H.api_detail_summary(d, IMP_TYPE)
    OUT['import_readback'] = det
    d.refresh()
    H.goto_page(d)
    OUT['list_has_imported'] = IMP_NAME in H.body_text(d)
    H.shot(d, 'D2_list_after_import_light')

    save_ev()
    try:
        OUT['console_severe'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
    except Exception:
        pass
    save_ev()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:5000])
finally:
    d.quit()
