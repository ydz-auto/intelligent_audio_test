# -*- coding: utf-8 -*-
"""INT-1254 证据补拍：两个缺陷的浏览器侧证据（未分类不落库 + 输出字段不落库）。"""
import os
import sys
import time
import json
import urllib.request
import urllib.parse

sys.path.insert(0, r'D:\00_user_data\multica_workspaces_desktop-api.multica.ai\intelligent-95ba6a12369f\int-1254-f48cf3a2b18f\worktree\Intelligent-Audio-TEST\tests\ui')
from selenium.webdriver.common.by import By
from walkthrough_int1254_combined import (
    _driver, _body_text, _goto_eval, _PREFIX, API, _api_get,
    _open_create, _click_select_item, _shot, _set_theme, _switch_tab,
)

TS = str(int(time.time()))


def wait_toast(d, ok_text, fail_text, timeout=40):
    for i in range(timeout):
        time.sleep(1)
        body = _body_text(d)
        if ok_text in body or fail_text in body:
            return ok_text in body
    return False


def delete_dim(did):
    req = urllib.request.Request(API + f'/evaluation/dimensions/{did}', method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except Exception as e:
        return str(e)


d = _driver()
created_id = None
try:
    _goto_eval(d)
    _set_theme(d, 'light')
    _goto_eval(d)

    # ── 缺陷1证据：新建全字段 → GET 详情 output_fields 应为1（表单默认1行），实测0 ──
    print('===== BUG-1 证据：output_fields 不落库 =====')
    sheet = _open_create(d)
    name = _PREFIX + 'bug1_' + TS
    sheet.find_element(By.ID, 'dim-name').send_keys(name)
    sheet.find_element(By.ID, 'dim-description').send_keys('输出字段落库证据')
    triggers = sheet.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    _click_select_item(d, triggers[1], '拒识')
    _switch_tab(d, sheet, 'API配置')
    # 输出字段配置默认 1 行（score），新增一行 wer
    for btn in sheet.find_elements(By.TAG_NAME, 'button'):
        if btn.text.strip() == '添加字段' and btn.is_displayed():
            d.execute_script('arguments[0].click()', btn)
            break
    time.sleep(0.5)
    # 填第二行输出字段
    try:
        pc2 = sheet.find_element(By.CSS_SELECTOR, "input[aria-label='输出字段代码 2']")
        pc2.send_keys('wer')
        pn2 = sheet.find_element(By.CSS_SELECTOR, "input[aria-label='输出显示名 2']")
        pn2.send_keys('WER值')
    except Exception as e:
        print('second output field fill skipped:', e)
    _shot(d, 'bug1_output_fields_filled')
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    d.execute_script('arguments[0].click()', save_btns[0])
    ok = wait_toast(d, '评估维度添加成功', '保存失败')
    print('created ok:', ok)
    dd = _api_get('/evaluation/dimensions?per_page=1000&search=' + name)
    items = dd.get('data', {}).get('items', [])
    if items:
        created_id = items[0]['id']
        print('created id:', created_id)
        detail = _api_get(f'/evaluation/dimensions/{created_id}')
        ddata = detail.get('data', {})
        print('detail output_fields count:', len(ddata.get('output_fields') or []))
        print('detail required_inputs count:', len(ddata.get('required_inputs') or []))
        print('BUG-1 判定: 表单配置2行输出字段, GET 详情 output_fields=',
              len(ddata.get('output_fields') or []), '(期望≥2)')

    # ── 缺陷2证据：编辑设「未分类」→ UI 显示未分类 → GET 仍返回原分类 ──
    print('===== BUG-2 证据：编辑清空分类不落库 =====')
    _goto_eval(d)
    box = d.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.clear()
    box.send_keys(name)
    for i in range(25):
        time.sleep(1)
        if name in _body_text(d):
            break
    for b in d.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {name}']"):
        if b.is_displayed():
            d.execute_script('arguments[0].click()', b)
            break
    time.sleep(2.5)
    sheet = d.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    triggers = sheet.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    print('edit drawer triggers before:', [t.text for t in triggers])
    _click_select_item(d, triggers[1], '未分类')
    triggers = sheet.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    print('edit drawer triggers after 未分类:', [t.text for t in triggers])
    _shot(d, 'bug2_edit_set_uncategorized')
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    d.execute_script('arguments[0].click()', save_btns[0])
    ok = wait_toast(d, '评估维度更新成功', '保存失败')
    print('edit save ok:', ok)
    time.sleep(0.5)
    if created_id:
        detail = _api_get(f'/evaluation/dimensions/{created_id}')
        ddata = detail.get('data', {})
        print('GET category_id after set 未分类:', ddata.get('category_id'),
              '(期望 null/None, 实测=原分类 3 即缺陷)')
    _shot(d, 'bug2_after_edit_category_check')
    print('证据补拍完成')
finally:
    if created_id:
        print('cleanup', created_id, delete_dim(created_id))
    d.quit()
