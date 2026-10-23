# -*- coding: utf-8 -*-
"""INT-1254 续跑：删除 / 批量 / 校验 / 计数 / 深色截图（剩余闭环项）。"""
import os
import sys
import time
import json
import re
import urllib.request
import urllib.parse

sys.path.insert(0, r'D:\00_user_data\multica_workspaces_desktop-api.multica.ai\intelligent-95ba6a12369f\int-1254-f48cf3a2b18f\worktree\Intelligent-Audio-TEST\tests\ui')
from selenium.webdriver.common.by import By
from walkthrough_int1254_combined import (
    _driver, _body_text, _goto_eval, _PREFIX, API, _api_get,
    _open_create, _click_select_item, _shot, _find_row, _set_theme, _switch_tab,
)

TS = str(int(time.time()))


def delete_dim(did):
    req = urllib.request.Request(API + f'/evaluation/dimensions/{did}', method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except Exception as e:
        return str(e)


def cleanup(name_prefix=_PREFIX):
    dd = _api_get('/evaluation/dimensions?per_page=1000&search=' + name_prefix)
    for it in dd.get('data', {}).get('items', []):
        if (it.get('name') or '').startswith(name_prefix):
            print('cleanup', it['id'], it['name'], delete_dim(it['id']))


def wait_toast(d, ok_text, fail_text, timeout=35):
    for i in range(timeout):
        time.sleep(1)
        body = _body_text(d)
        if ok_text in body or fail_text in body:
            return ok_text in body
    return False


d = _driver()
try:
    _goto_eval(d)
    _set_theme(d, 'light')
    _goto_eval(d)

    # ===== PHASE 3: 删除 =====
    print('===== PHASE 3: 删除 =====')
    sheet = _open_create(d)
    delname = _PREFIX + 'del_' + TS
    sheet.find_element(By.ID, 'dim-name').send_keys(delname)
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    d.execute_script('arguments[0].click()', save_btns[0])
    ok = wait_toast(d, '评估维度添加成功', '保存失败')
    print('create temp for delete:', delname, ok)
    dd = _api_get('/evaluation/dimensions?per_page=1000&search=' + delname)
    items = dd.get('data', {}).get('items', [])
    tid = items[0]['id'] if items else None
    print('temp id:', tid)
    _goto_eval(d)
    box = d.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.clear()
    box.send_keys(delname)
    for i in range(25):
        time.sleep(1)
        if delname in _body_text(d):
            break
    del_btn = None
    for b in d.find_elements(By.CSS_SELECTOR, f"button[aria-label='删除维度 {delname}']"):
        if b.is_displayed():
            del_btn = b
            break
    assert del_btn, '删除按钮缺失'
    d.execute_script('arguments[0].click()', del_btn)
    time.sleep(0.9)
    dialog = d.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    print('confirm contains 确定要删除:', f'确定要删除维度「{delname}」吗？此操作不可恢复。' in dtxt)
    _shot(d, 'p3_delete_confirm')
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '删除' and b.is_displayed()]
    d.execute_script('arguments[0].click()', confirm[0])
    ok = wait_toast(d, '维度已删除', '删除维度失败')
    print('delete toast ok:', ok)
    _shot(d, 'p3_deleted_toast')
    dd = _api_get(f'/evaluation/dimensions/{tid}')
    print('GET after delete success False:', dd.get('success') is False)
    print('PHASE 3 delete OK')

    # ===== PHASE 4: 批量 =====
    print('===== PHASE 4: 批量 =====')
    batch_ids = []
    for i in range(3):
        _goto_eval(d)
        sheet = _open_create(d)
        bn = _PREFIX + f'batch{i+1}_' + TS
        sheet.find_element(By.ID, 'dim-name').send_keys(bn)
        save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                     if b.text.strip() == '保存' and b.is_displayed()]
        d.execute_script('arguments[0].click()', save_btns[0])
        ok = wait_toast(d, '评估维度添加成功', '保存失败')
        print('create batch', i + 1, bn, ok)
        dd = _api_get('/evaluation/dimensions?per_page=1000&search=' + bn)
        items = dd.get('data', {}).get('items', [])
        batch_ids.append(items[0]['id'] if items else None)
    print('batch ids:', batch_ids)
    _shot(d, 'p4_three_created')

    # batch disable first
    _goto_eval(d)
    box = d.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.clear()
    box.send_keys(_PREFIX + 'batch1_' + TS)
    for i in range(25):
        time.sleep(1)
        if _PREFIX + 'batch1_' + TS in _body_text(d):
            break
    cb = d.find_element(By.CSS_SELECTOR, "[aria-label='选择维度 " + _PREFIX + "batch1_" + TS + "']")
    d.execute_script('arguments[0].click()', cb)
    time.sleep(0.6)
    for b in d.find_elements(By.XPATH, "//button[contains(., '批量操作')]"):
        if b.is_displayed():
            d.execute_script('arguments[0].click()', b)
            break
    time.sleep(0.8)
    for item in d.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']"):
        if item.text.strip() == '批量禁用':
            d.execute_script('arguments[0].click()', item)
            break
    time.sleep(0.8)
    dialog = d.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    print('batch disable confirm:', '确定要禁用选中的 1 个维度吗？' in dialog.text)
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '批量禁用' and b.is_displayed()]
    d.execute_script('arguments[0].click()', confirm[0])
    ok = wait_toast(d, '批量操作执行成功', '批量操作失败')
    time.sleep(1.0)
    dd = _api_get(f'/evaluation/dimensions/{batch_ids[0]}')
    print('batch1 status after disable (False):', dd.get('data', {}).get('status'))
    _shot(d, 'p4_batch_disable_done')

    # batch delete 2,3 via floating bar
    _goto_eval(d)
    box = d.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.clear()
    box.send_keys(_PREFIX + 'batch')
    for i in range(25):
        time.sleep(1)
        if (_PREFIX + 'batch2_' + TS in _body_text(d)) and (_PREFIX + 'batch3_' + TS in _body_text(d)):
            break
    cb2 = d.find_element(By.CSS_SELECTOR, "[aria-label='选择维度 " + _PREFIX + "batch2_" + TS + "']")
    d.execute_script('arguments[0].click()', cb2)
    cb3 = d.find_element(By.CSS_SELECTOR, "[aria-label='选择维度 " + _PREFIX + "batch3_" + TS + "']")
    d.execute_script('arguments[0].click()', cb3)
    time.sleep(0.6)
    for b in d.find_elements(By.XPATH, "//button[contains(., '批量删除')]"):
        if b.is_displayed():
            d.execute_script('arguments[0].click()', b)
            break
    time.sleep(0.8)
    dialog = d.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    print('batch delete confirm:', '确定要删除选中的 2 个维度吗？' in dialog.text)
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '批量删除' and b.is_displayed()]
    d.execute_script('arguments[0].click()', confirm[0])
    ok = wait_toast(d, '批量操作执行成功', '批量操作失败')
    time.sleep(1.0)
    _shot(d, 'p4_batch_delete_done')
    for i in (1, 2):
        dd = _api_get(f'/evaluation/dimensions/{batch_ids[i]}')
        print(f'batch{i+1} deleted (success False):', dd.get('success') is False)
    print('PHASE 4 batch OK')

    # ===== PHASE 5: 校验 =====
    print('===== PHASE 5: 校验 =====')
    _goto_eval(d)
    sheet = _open_create(d)
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    print('empty name save disabled:', save_btns[0].get_attribute('disabled'))
    _shot(d, 'p5_empty_name')
    name_input = sheet.find_element(By.ID, 'dim-name')
    name_input.send_keys(_PREFIX + 'val_' + TS)
    _switch_tab(d, sheet, '结果配置')
    mi = sheet.find_element(By.ID, 'dim-result-min')
    mi.clear(); mi.send_keys('90')
    ma = sheet.find_element(By.ID, 'dim-result-max')
    ma.clear(); ma.send_keys('80')
    time.sleep(0.5)
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    print('invalid range save disabled:', save_btns[0].get_attribute('disabled'))
    _shot(d, 'p5_invalid_range')
    for b in sheet.find_elements(By.TAG_NAME, 'button'):
        if b.text.strip() == '取消' and b.is_displayed():
            d.execute_script('arguments[0].click()', b)
            break
    time.sleep(1.0)
    sheet2 = _open_create(d)
    nv = sheet2.find_element(By.ID, 'dim-name').get_attribute('value') or ''
    print('reopen name value empty:', nv == '')
    _shot(d, 'p5_reopen_reset')
    for b in sheet2.find_elements(By.TAG_NAME, 'button'):
        if b.text.strip() == '取消' and b.is_displayed():
            d.execute_script('arguments[0].click()', b)
            break
    time.sleep(1.0)
    print('PHASE 5 validation OK')

    # ===== PHASE 6: 选项与计数 =====
    print('===== PHASE 6: 选项与计数 =====')
    _goto_eval(d)
    txt = _body_text(d)
    m = re.search(r'共 (\d+) 条', txt)
    ui_total = int(m.group(1)) if m else None
    dd = _api_get('/evaluation/dimensions?per_page=1')
    api_total = dd.get('data', {}).get('total')
    print('UI footer total:', ui_total, 'API total:', api_total, 'match:', ui_total == api_total)
    dd = _api_get('/evaluation/categories?per_page=100')
    api_cats = dd.get('data', {}).get('items', [])
    print('API categories:', len(api_cats), [c['name'] for c in api_cats])
    dd = _api_get('/algorithm/options')
    api_algos = dd.get('data', {}).get('algorithms', [])
    print('API algorithms:', len(api_algos), [a['name'] for a in api_algos])
    cat_facet = None
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and '全部分类' in (b.text or ''):
            cat_facet = b
            break
    if cat_facet:
        d.execute_script('arguments[0].click()', cat_facet)
        time.sleep(0.8)
        # FacetFilter uses Popover+button, not base-ui Select
        pop = d.find_element(By.CSS_SELECTOR, "[data-slot='popover-content']")
        buttons = [b.text.strip() for b in pop.find_elements(By.TAG_NAME, 'button')]
        print('分类 facet items:', buttons)
        real = [i for i in buttons if i not in ('全部分类', '全部')]
        print('分类 facet vs api categories match:', len(real) == len(api_cats))
        d.execute_script("document.body.click()")
        time.sleep(0.4)
    algo_facet = None
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and '关联算法' in (b.text or '') and '全部' in (b.text or ''):
            algo_facet = b
            break
    if algo_facet:
        d.execute_script('arguments[0].click()', algo_facet)
        time.sleep(0.8)
        pop = d.find_element(By.CSS_SELECTOR, "[data-slot='popover-content']")
        buttons = [b.text.strip() for b in pop.find_elements(By.TAG_NAME, 'button')]
        print('算法 facet items:', buttons, 'expect +1(全部):', len(buttons) == len(api_algos) + 1)
        d.execute_script("document.body.click()")
        time.sleep(0.4)
    for t in d.find_elements(By.CSS_SELECTOR, "[data-slot='tabs-trigger']"):
        if t.text.strip() == '分组视图' and t.is_displayed():
            d.execute_script('arguments[0].click()', t)
            break
    time.sleep(1.2)
    txt = _body_text(d)
    for c in api_cats:
        print('group has', c['name'], c['name'] in txt)
    _shot(d, 'p6_group_view')
    print('PHASE 6 counts OK')

    # dark theme
    _set_theme(d, 'dark')
    _goto_eval(d)
    _shot(d, 'dark_page')
    _open_create(d)
    _shot(d, 'dark_drawer')
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if b.text.strip() == '取消' and b.is_displayed():
            d.execute_script('arguments[0].click()', b)
            break
    print('dark captures done')
finally:
    cleanup()
    d.quit()
    print('DONE')
