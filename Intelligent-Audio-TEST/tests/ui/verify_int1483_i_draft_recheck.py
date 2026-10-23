# -*- coding: utf-8 -*-
"""INT-1483 Phase I：草稿快照复验（INT-1514）——保存草稿 → 改名发布 → 读草稿接口 → 重开编辑回显。"""
import json
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'J' + H.RUN_TAG
TYPE = f'itest1483_j_{TAG.lower()}'
NAME = f'接线测试_INT1483_草稿_{TAG}'
OUT = {'type': TYPE, 'name': NAME}


def find(xp, t=15):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def body():
    return H.body_text(d)


def wtext(text, t=25):
    WebDriverWait(d, t).until(lambda x: text in body())


d = H.driver()
try:
    H.login(d)
    H.goto_page(d)
    st, pay, _ = H.api_json(d, '/algorithm/definitions', 'POST', {
        'type': TYPE, 'name': NAME, 'group_id': None, 'display_order': 1, 'status': 'offline',
        'description': '接线测试草稿复验', 'device_params': [], 'api_params': [], 'case_params': [],
        'reference_params': [], 'mappings': {'device': [], 'api': [], 'evaluation': []},
        'associated_dimensions': []})
    OUT['create_status'] = st
    H.goto_page(d)

    H.open_row_menu(d, NAME)
    H.click_menuitem(d, '编辑')
    wtext('管理算法定义、参数与映射关系')
    time.sleep(1.2)
    name_el = d.find_element(By.ID, 'algo-name')
    name_el.clear(); name_el.send_keys(NAME + '_草稿态')
    time.sleep(0.6)
    H.js_click(d, find("//button[contains(normalize-space(.), '保存草稿')]"))
    time.sleep(3.5)
    st_d, pay_d, _ = H.api_json(d, f'/algorithm/definitions/draft/{TYPE}')
    OUT['draft_after_save'] = {'status': st_d,
                               'name': ((pay_d or {}).get('data') or {}).get('name')}
    OUT['draft_banner_after_save'] = '存在未发布的草稿' in body()

    name_el = d.find_element(By.ID, 'algo-name')
    name_el.clear(); name_el.send_keys(NAME + '_发布态')
    time.sleep(0.6)
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[@type='submit' and contains(normalize-space(.), '发布')]"))
    WebDriverWait(d, 90).until(lambda x: '管理算法定义、参数与映射关系' not in body())
    time.sleep(2)
    OUT['publish_fetches'] = [(e['method'], e['url'], e['status'])
                              for e in H.fetch_log(d, '/algorithm/definitions')]
    st_d2, pay_d2, _ = H.api_json(d, f'/algorithm/definitions/draft/{TYPE}')
    OUT['draft_after_publish'] = {'status': st_d2,
                                  'data': ((pay_d2 or {}).get('data') if isinstance(pay_d2, dict) else None)}
    det = H.api_detail_summary(d, TYPE)
    OUT['published_readback'] = {'status': det['status'],
                                 'name': (det.get('data') or {}).get('name')}

    d.refresh(); H.goto_page(d)
    H.open_row_menu(d, NAME + '_发布态')
    H.click_menuitem(d, '编辑')
    wtext('管理算法定义、参数与映射关系')
    time.sleep(1.5)
    OUT['reopen_edit_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['reopen_draft_banner'] = '存在未发布的草稿' in body()
    H.shot(d, 'I1_edit_after_publish_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'I1_edit_after_publish_dark')
    H.apply_theme(d, 'light')

    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.9)
    if '有未保存的更改' in body():
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.8)

    # 清理本卡数据
    st_del, _, _ = H.api_json(d, f'/algorithm/definitions/{TYPE}', 'DELETE')
    OUT['delete_status'] = st_del
    H.save_evidence('phaseI_draft_recheck', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
finally:
    try:
        d.quit()
    except Exception:
        pass
