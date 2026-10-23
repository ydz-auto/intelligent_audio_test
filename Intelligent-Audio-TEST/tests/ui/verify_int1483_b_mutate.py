# -*- coding: utf-8 -*-
"""INT-1483 Phase B：算法新建/编辑 Sheet 全字段 + 参数表单 + 发布/回读/删除闭环。"""
import json
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'B' + H.RUN_TAG
TYPE = f'itest1483_{TAG.lower()}'
NAME = f'接线测试_INT1483_算法_{TAG}'
NAME2 = NAME + '_已编辑'
OUT = {'type': TYPE, 'name': NAME, 'name2': NAME2}


def wtext(text, timeout=20):
    WebDriverWait(d, timeout).until(lambda x: text in H.body_text(x))


def find(xp):
    return WebDriverWait(d, 15).until(EC.presence_of_element_located((By.XPATH, xp)))


def sheet_ready():
    wtext('管理算法定义、参数与映射关系')


def publish_btn():
    return find("//button[@type='submit' and contains(normalize-space(.), '发布')]")


def set_input(el, value):
    el.clear()
    el.send_keys(value)


d = H.driver()
try:
    print('LOGIN:', H.login(d))
    H.goto_page(d)

    # ---------- B1 打开新建 Sheet ----------
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '新建算法')]"))
    sheet_ready()
    time.sleep(1)
    OUT['open_fetches'] = [(e['method'], e['url'], e['status']) for e in H.fetch_log(d)]
    H.shot(d, 'B1_create_sheet_light')

    # 字段初值
    OUT['initial'] = {
        'type': d.find_element(By.ID, 'algo-type').get_attribute('value'),
        'name': d.find_element(By.ID, 'algo-name').get_attribute('value'),
        'order': d.find_element(By.ID, 'algo-order').get_attribute('value'),
        'status_label_online': '上线' in H.body_text(d),
        'publish_disabled': not publish_btn().is_enabled(),
    }

    # 所属分组下拉选项数（groups + 新建分组哨兵）
    st_g, pay_g, _ = H.api_json(d, '/algorithm/groups')
    groups = (pay_g or {}).get('data', {}).get('items') or []
    H.js_click(d, find("//label[contains(normalize-space(.), '所属分组')]/following-sibling::button[@role='combobox']"))
    time.sleep(0.6)
    opts = d.find_elements(By.CSS_SELECTOR, "[role='option']")
    OUT['group_dropdown'] = {'option_count': len(opts),
                             'labels': [o.text for o in opts],
                             'api_groups': len(groups)}
    H.shot(d, 'B1_group_dropdown_light')
    # 再点触发器收起下拉（Esc / 点遮罩会连带关闭整个 Sheet）
    H.js_click(d, find("//label[contains(normalize-space(.), '所属分组')]/following-sibling::button[@role='combobox']"))
    time.sleep(0.6)
    assert '管理算法定义、参数与映射关系' in H.body_text(d), '分组下拉关闭后 Sheet 被误关'

    # ---------- B2 校验 ----------
    set_input(d.find_element(By.ID, 'algo-type'), 'Bad-Type')
    time.sleep(0.8)
    OUT['invalid_type_error'] = '算法代码需小写字母开头' in H.body_text(d)
    OUT['publish_disabled_still'] = not publish_btn().is_enabled()
    H.shot(d, 'B2_invalid_type_light')
    set_input(d.find_element(By.ID, 'algo-type'), TYPE)
    time.sleep(0.5)

    # ---------- B3 全字段填写 + 添加设备参数 ----------
    set_input(d.find_element(By.ID, 'algo-name'), NAME)
    set_input(d.find_element(By.ID, 'algo-order'), '42')
    set_input(d.find_element(By.ID, 'algo-desc'), '接线测试算法定义（INT-1483 深走查自建，验收后删除）')

    H.js_click(d, find("//button[@aria-label='添加参数']"))
    time.sleep(0.5)
    H.click_menuitem(d, '添加设备参数')
    time.sleep(0.6)
    codes = d.find_elements(By.CSS_SELECTOR, "input[aria-label='参数代码']")
    names = d.find_elements(By.CSS_SELECTOR, "input[aria-label='参数名称']")
    set_input(codes[-1], 'test_param')
    set_input(names[-1], '测试参数')
    time.sleep(0.4)
    OUT['param_rows_after_add'] = len(codes)
    H.shot(d, 'B3_create_filled_light')

    # 深色
    H.apply_theme(d, 'dark')
    H.shot(d, 'B3_create_filled_dark')
    H.apply_theme(d, 'light')

    OUT['publish_enabled'] = publish_btn().is_enabled()

    # ---------- B4 发布 ----------
    H.clear_fetch_log(d)
    H.js_click(d, publish_btn())
    # 发布 POST 落库较慢（参数/映射聚合），等 Sheet 关闭或错误 Alert 出现
    WebDriverWait(d, 90).until(
        lambda x: '管理算法定义、参数与映射关系' not in H.body_text(x)
        or '发布失败' in H.body_text(x) or '请修' in H.body_text(x))
    time.sleep(1.5)
    toasts = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    OUT['publish_toasts'] = toasts
    H.shot(d, 'B4_after_publish')
    logs = H.fetch_log(d, '/algorithm/definitions')
    OUT['publish_fetches'] = [
        {'method': e['method'], 'url': e['url'], 'status': e['status'],
         'req': (json.loads(e['reqBody']) if e.get('reqBody') else None)}
        for e in logs if e['method'] in ('POST', 'PUT')
    ]
    # 回读
    det = H.api_detail_summary(d, TYPE)
    OUT['readback_after_create'] = det
    H.save_evidence('phaseB_mutate', OUT)
    d.refresh()
    H.goto_page(d)
    OUT['list_has_created'] = NAME in H.body_text(d)
    H.shot(d, 'B4_list_after_create_light')
    if not OUT['list_has_created']:
        OUT['ABORT'] = 'created algorithm not visible in list; see publish_fetches'
        H.save_evidence('phaseB_mutate', OUT)
        print(json.dumps(OUT, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    # ---------- B5 编辑：回显 + 修改 + 回读 ----------
    H.open_row_menu(d, NAME)
    H.click_menuitem(d, '编辑')
    sheet_ready()
    time.sleep(1.2)
    OUT['edit_initial'] = {
        'type_value': d.find_element(By.ID, 'algo-type').get_attribute('value'),
        'type_disabled': not d.find_element(By.ID, 'algo-type').is_enabled(),
        'name_value': d.find_element(By.ID, 'algo-name').get_attribute('value'),
        'order_value': d.find_element(By.ID, 'algo-order').get_attribute('value'),
        'desc_value': d.find_element(By.ID, 'algo-desc').get_attribute('value'),
        'param_code': (d.find_elements(By.CSS_SELECTOR, "input[aria-label='参数代码']") or [None])[0].get_attribute('value'),
    }
    H.shot(d, 'B5_edit_prefill_light')
    set_input(d.find_element(By.ID, 'algo-name'), NAME2)
    set_input(d.find_element(By.ID, 'algo-desc'), '接线测试算法定义（编辑后描述）')
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "[data-slot='switch']"))
    time.sleep(0.5)
    OUT['status_after_toggle'] = '下线' in H.body_text(d)
    H.apply_theme(d, 'dark')
    H.shot(d, 'B5_edit_dark')
    H.apply_theme(d, 'light')

    H.clear_fetch_log(d)
    H.js_click(d, publish_btn())
    WebDriverWait(d, 90).until(
        lambda x: '管理算法定义、参数与映射关系' not in H.body_text(x)
        or '发布失败' in H.body_text(x))
    time.sleep(1.5)
    toasts2 = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    OUT['edit_toasts'] = toasts2
    OUT['edit_fetches'] = [
        {'method': e['method'], 'url': e['url'], 'status': e['status'],
         'req': (json.loads(e['reqBody']) if e.get('reqBody') else None)}
        for e in H.fetch_log(d, '/algorithm/definitions') if e['method'] in ('POST', 'PUT')
    ]
    OUT['readback_after_edit'] = H.api_detail_summary(d, TYPE)

    # ---------- B6 脏态离开丢弃 + 重开无残留 ----------
    d.refresh()
    H.goto_page(d)
    H.open_row_menu(d, NAME2)
    H.click_menuitem(d, '编辑')
    sheet_ready()
    time.sleep(1)
    set_input(d.find_element(By.ID, 'algo-name'), NAME2 + '_临时')
    time.sleep(0.6)
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.8)
    OUT['dirty_guard'] = '有未保存的更改' in H.body_text(d)
    if OUT['dirty_guard']:
        H.shot(d, 'B6_dirty_guard_light')
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.8)
    # 重开确认无残留
    H.open_row_menu(d, NAME2)
    H.click_menuitem(d, '编辑')
    sheet_ready()
    time.sleep(1)
    OUT['reopen_name'] = d.find_element(By.ID, 'algo-name').get_attribute('value')
    OUT['reopen_has_temp'] = '_临时' in OUT['reopen_name']
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.8)
    if '有未保存的更改' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.6)

    # 新建重开为空
    H.js_click(d, find("//button[contains(normalize-space(.), '新建算法')]"))
    sheet_ready()
    time.sleep(0.8)
    OUT['create_reopen'] = {
        'type': d.find_element(By.ID, 'algo-type').get_attribute('value'),
        'name': d.find_element(By.ID, 'algo-name').get_attribute('value'),
    }
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.8)
    if '有未保存的更改' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.6)

    # ---------- B7 删除：取消 + 确认 + 回读 ----------
    H.open_row_menu(d, NAME2)
    H.click_menuitem(d, '删除')
    time.sleep(0.8)
    OUT['delete_confirm_text'] = '确认删除' in H.body_text(d) and NAME2 in H.body_text(d)
    H.shot(d, 'B7_delete_confirm_light')
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]"))
    time.sleep(0.6)
    OUT['delete_cancelled_still_present'] = NAME2 in H.body_text(d)
    H.open_row_menu(d, NAME2)
    H.click_menuitem(d, '删除')
    time.sleep(0.8)
    H.clear_fetch_log(d)
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '删除')]"))
    toasts3 = H.wait_toast(d, 30)
    time.sleep(2)
    OUT['delete_toasts'] = toasts3
    OUT['delete_fetches'] = [(e['method'], e['url'], e['status'])
                             for e in H.fetch_log(d, '/algorithm/definitions') if e['method'] == 'DELETE']
    det2 = H.api_detail_summary(d, TYPE)
    OUT['readback_after_delete'] = det2
    d.refresh()
    H.goto_page(d)
    OUT['list_has_deleted'] = NAME2 not in H.body_text(d)

    try:
        OUT['console_severe'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
    except Exception:
        OUT['console_severe'] = []

    H.save_evidence('phaseB_mutate', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:6000])
finally:
    d.quit()
