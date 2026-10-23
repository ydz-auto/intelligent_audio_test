# -*- coding: utf-8 -*-
"""INT-1483 Phase E：批量删除（取消/确认）+ 导出 + 编辑发布后草稿回显核对（INT-1319 草稿清除）。"""
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'E' + H.RUN_TAG
TYPES = [f'itest1483_e1_{TAG.lower()}', f'itest1483_e2_{TAG.lower()}']
NAMES = [f'接线测试_INT1483_批量1_{TAG}', f'接线测试_INT1483_批量2_{TAG}']
OUT = {'types': TYPES, 'names': NAMES}


def find(xp, t=15):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def save_ev():
    H.save_evidence('phaseE_bulk_export_draft', OUT)


def create_algo(t, n):
    body = {'type': t, 'name': n, 'group_id': None, 'display_order': 1, 'status': 'offline',
            'description': '接线测试批量删除用', 'device_params': [], 'api_params': [],
            'case_params': [], 'reference_params': [],
            'mappings': {'device': [], 'api': [], 'evaluation': []}, 'associated_dimensions': []}
    st, pay, raw = H.api_json(d, '/algorithm/definitions', 'POST', body)
    return st, raw[:200]


d = H.driver()
try:
    print('LOGIN:', H.login(d))
    H.goto_page(d)
    for t, n in zip(TYPES, NAMES):
        OUT.setdefault('created', []).append([t, create_algo(t, n)])
    d.refresh()
    H.goto_page(d)

    # ---------- E2 批量删除：未勾选提示 ----------
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    H.click_menuitem(d, '批量删除')
    time.sleep(1)
    OUT['bulk_no_selection_toast'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    H.shot(d, 'E2_bulk_no_selection_light')

    # 勾选两条自建算法
    boxes = []
    for n in NAMES:
        row = d.find_element(By.XPATH, f"//tr[.//*[contains(normalize-space(.), '{n}')]]")
        cb = row.find_element(By.CSS_SELECTOR, "[role='checkbox'], input[type='checkbox']")
        H.js_click(d, cb)
        boxes.append(n)
    time.sleep(0.8)
    OUT['bulk_bar_text'] = [t for t in H.body_text(d).split('\n') if '已选择' in t][:2]
    OUT['selected_visible'] = f'已选择 {len(NAMES)} 个算法' in H.body_text(d)
    H.shot(d, 'E2_bulk_selected_light')

    H.js_click(d, find("//button[contains(normalize-space(.), '批量删除')]"))
    time.sleep(1)
    OUT['bulk_confirm_text'] = f'将删除已选择的 {len(NAMES)} 个算法' in H.body_text(d)
    H.shot(d, 'E2_bulk_confirm_light')
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]"))
    time.sleep(0.8)
    OUT['bulk_cancel_keeps'] = all(n in H.body_text(d) for n in NAMES)

    H.js_click(d, find("//button[contains(normalize-space(.), '批量删除')]"))
    time.sleep(1)
    H.clear_fetch_log(d)
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '删除')]"))
    toasts = H.wait_toast(d, 40)
    time.sleep(3)
    OUT['bulk_toasts'] = toasts
    OUT['bulk_fetches'] = [
        {'method': e['method'], 'url': e['url'], 'status': e['status'],
         'req': (json.loads(e['reqBody']) if e.get('reqBody') else None)}
        for e in H.fetch_log(d, '/algorithm/') if '/algorithm/definitions' in e['url'] or '/bulk-delete' in e['url']]
    d.refresh()
    H.goto_page(d)
    OUT['bulk_list_gone'] = all(n not in H.body_text(d) for n in NAMES)
    OUT['bulk_readback'] = {t: H.api_detail_summary(d, t)['status'] for t in TYPES}
    H.shot(d, 'E2_after_bulk_delete_light')
    save_ev()

    # ---------- E3 导出算法（下载 .json） ----------
    dl = os.path.join(H.ART, 'downloads')
    os.makedirs(dl, exist_ok=True)
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    H.click_menuitem(d, '导出算法')
    time.sleep(3)
    files = os.listdir(dl)
    OUT['export_files'] = files
    if files:
        p = os.path.join(dl, files[0])
        OUT['export_size'] = os.path.getsize(p)
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        OUT['export_count'] = len(data)
        OUT['export_sample_type'] = data[0].get('type') if data else None

    # ---------- E4 草稿：编辑发布后是否仍有旧草稿 ----------
    t2 = TYPES[0] + '_draft'
    n2 = NAMES[0] + '_草稿'
    OUT['draft_create'] = create_algo(t2, n2)
    # 打开编辑、改名为 X、保存草稿（不等自动），再改名为 Y 发布，发布后读草稿
    H.open_row_menu(d, n2)
    H.click_menuitem(d, '编辑')
    WebDriverWait(d, 20).until(lambda x: '管理算法定义、参数与映射关系' in H.body_text(x))
    time.sleep(1)
    name_el = d.find_element(By.ID, 'algo-name')
    name_el.clear(); name_el.send_keys(n2 + '_草稿态')
    time.sleep(0.5)
    # 保存草稿
    H.js_click(d, find("//button[contains(normalize-space(.), '保存草稿')]"))
    time.sleep(3)
    st_d, pay_d, raw_d = H.api_json(d, f'/algorithm/definitions/draft/{t2}')
    OUT['draft_after_save'] = {'status': st_d, 'name': (pay_d or {}).get('data', {}).get('name') if isinstance(pay_d, dict) else None}
    # 再改名并发布
    name_el.clear(); name_el.send_keys(n2 + '_发布态')
    H.js_click(d, find("//button[@type='submit' and contains(normalize-space(.), '发布')]"))
    WebDriverWait(d, 90).until(lambda x: '管理算法定义、参数与映射关系' not in H.body_text(x))
    time.sleep(2)
    st_d2, pay_d2, _ = H.api_json(d, f'/algorithm/definitions/draft/{t2}')
    OUT['draft_after_publish'] = {'status': st_d2,
                                  'data': ((pay_d2 or {}).get('data') if isinstance(pay_d2, dict) else None)}
    OUT['published_readback'] = H.api_detail_summary(d, t2)
    # 重开编辑看回显
    d.refresh(); H.goto_page(d)
    H.open_row_menu(d, n2 + '_发布态')
    H.click_menuitem(d, '编辑')
    WebDriverWait(d, 20).until(lambda x: '管理算法定义、参数与映射关系' in H.body_text(x))
    time.sleep(1.5)
    OUT['reopen_edit_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['draft_banner_shown'] = '存在未发布的草稿' in H.body_text(d)
    H.shot(d, 'E4_edit_after_publish_light')
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.8)
    if '有未保存的更改' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.6)

    save_ev()
    try:
        OUT['console_severe'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
    except Exception:
        pass
    save_ev()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:5000])
finally:
    d.quit()
