# -*- coding: utf-8 -*-
import json, time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import int1483_helpers as H

TAG = 'D' + H.RUN_TAG
T = f'itest1483_draft_{TAG.lower()}'
N = f'接线测试_INT1483_草稿_{TAG}'
OUT = {'type': T, 'name': N}

def find(xp, t=15):
    return WebDriverWait(d, t).until(lambda x: x.find_element(By.XPATH, xp))

d = H.driver()
try:
    H.login(d); H.goto_page(d)
    body = {'type': T, 'name': N, 'group_id': None, 'display_order': 1, 'status': 'offline',
            'description': '接线测试草稿核验', 'device_params': [], 'api_params': [], 'case_params': [],
            'reference_params': [], 'mappings': {'device': [], 'api': [], 'evaluation': []},
            'associated_dimensions': []}
    print('create', H.api_json(d, '/algorithm/definitions', 'POST', body)[0])
    d.refresh(); H.goto_page(d)
    H.open_row_menu(d, N)
    H.click_menuitem(d, '编辑')
    WebDriverWait(d, 20).until(lambda x: '管理算法定义、参数与映射关系' in H.body_text(x))
    time.sleep(1.2)
    OUT['edit_initial_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    el = d.find_element(By.ID, 'algo-name')
    el.clear(); el.send_keys(N + '_草稿态')
    time.sleep(0.5)
    H.js_click(d, find("//button[contains(normalize-space(.), '保存草稿')]"))
    time.sleep(3)
    st, pay, raw = H.api_json(d, f'/algorithm/definitions/draft/{T}')
    OUT['draft_after_save'] = {'status': st, 'body': raw[:400]}
    el = d.find_element(By.ID, 'algo-name')
    el.clear(); el.send_keys(N + '_发布态')
    H.js_click(d, find("//button[@type='submit' and contains(normalize-space(.), '发布')]"))
    WebDriverWait(d, 90).until(lambda x: '管理算法定义、参数与映射关系' not in H.body_text(x))
    time.sleep(2)
    st2, pay2, raw2 = H.api_json(d, f'/algorithm/definitions/draft/{T}')
    OUT['draft_after_publish'] = {'status': st2, 'body': raw2[:400]}
    OUT['published'] = H.api_detail_summary(d, T)
    d.refresh(); H.goto_page(d)
    H.open_row_menu(d, N + '_发布态')
    H.click_menuitem(d, '编辑')
    WebDriverWait(d, 20).until(lambda x: '管理算法定义、参数与映射关系' in H.body_text(x))
    time.sleep(1.5)
    OUT['reopen_edit_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['draft_banner'] = '未发布的草稿' in H.body_text(d)
    H.shot(d, 'E4_edit_after_publish_light')
    H.save_evidence('phaseE_draft', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
finally:
    d.quit()
