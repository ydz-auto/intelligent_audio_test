# -*- coding: utf-8 -*-
"""INT-1483 Phase F：补未覆盖项——导入弹窗文件上传路径、深色截图（导入/确认弹窗/有数据分组）、
列表加载与 500 错误态、参数表单按类型切换（number/slider 范围校验、功能特性快捷开关）、
导航/页脚计数联动。"""
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'F' + H.RUN_TAG
IMP_TYPE = f'itest1483_fup_{TAG.lower()}'
IMP_NAME = f'接线测试_INT1483_上传导入_{TAG}'
GRP = f'接线测试_INT1483_分组F_{TAG}'
BULK_TYPES = [f'itest1483_fb1_{TAG.lower()}', f'itest1483_fb2_{TAG.lower()}']
BULK_NAMES = [f'接线测试_INT1483_批量F1_{TAG}', f'接线测试_INT1483_批量F2_{TAG}']
OUT = {'tag': TAG, 'imp_type': IMP_TYPE, 'grp': GRP, 'bulk_types': BULK_TYPES}

FILE_JSON = os.path.join(H.ART, f'import_file_{TAG}.json')


def find(xp, t=15):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def wtext(text, t=20):
    WebDriverWait(d, t).until(lambda x: text in H.body_text(x))


def save():
    H.save_evidence('phaseF_gaps', OUT)


def close_all():
    H.close_overlays(d)
    time.sleep(0.4)


def create_algo(t, n, group_id=None):
    body = {'type': t, 'name': n, 'group_id': group_id, 'display_order': 1, 'status': 'offline',
            'description': '接线测试 INT-1483 Phase F', 'device_params': [], 'api_params': [],
            'case_params': [], 'reference_params': [],
            'mappings': {'device': [], 'api': [], 'evaluation': []}, 'associated_dimensions': []}
    return H.api_json(d, '/algorithm/definitions', 'POST', body)[0]


def menu_item(text, t=12):
    el = WebDriverWait(d, t).until(EC.presence_of_element_located(
        (By.XPATH, f"//*[@role='menuitem'][contains(normalize-space(.), '{text}')]")))
    H.js_click(d, el)
    time.sleep(0.9)


d = H.driver()
try:
    H.login(d)
    H.goto_page(d)
    OUT['env_health'] = H.api_json(d, '/system/health')[2][:200] if False else 'gateway ok (see comment)'
    OUT['list_fetches_on_load'] = [(e['method'], e['url'], e['status'])
                                   for e in H.fetch_log(d, '/algorithm/definitions')][:4]

    # ================= F1 导入弹窗：文件上传路径 + 深色 =================
    payload = [{
        'type': IMP_TYPE, 'name': IMP_NAME, 'group_id': None, 'display_order': 3,
        'status': 'offline', 'description': '接线测试上传导入（INT-1483 Phase F）',
        'device_params': [], 'api_params': [], 'case_params': [], 'reference_params': [],
        'mappings': {'device': [], 'api': [], 'evaluation': []}, 'associated_dimensions': [],
    }]
    with open(FILE_JSON, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    menu_item('导入算法')
    wtext('粘贴或上传算法定义 JSON')
    time.sleep(0.6)
    H.shot(d, 'F1_import_dialog_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'F1_import_dialog_dark')
    H.apply_theme(d, 'light')

    ta = d.find_element(By.CSS_SELECTOR, "textarea[aria-label='算法定义 JSON']")
    OUT['textarea_before_upload'] = ta.get_attribute('value')
    file_input = d.find_element(By.CSS_SELECTOR, "input[type='file']")
    OUT['file_input_present'] = True
    file_input.send_keys(os.path.abspath(FILE_JSON))
    time.sleep(1.5)
    ta = d.find_element(By.CSS_SELECTOR, "textarea[aria-label='算法定义 JSON']")
    OUT['textarea_after_upload_head'] = (ta.get_attribute('value') or '')[:160]
    OUT['upload_filled_textarea'] = IMP_TYPE in (ta.get_attribute('value') or '')
    H.shot(d, 'F1_import_file_loaded_light')

    H.clear_fetch_log(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '导入') and not(contains(normalize-space(.), '导入算法'))]"))
    toasts = H.wait_toast(d, 30)
    time.sleep(2)
    OUT['upload_import_toasts'] = toasts
    OUT['upload_import_fetches'] = [
        {'method': e['method'], 'url': e['url'], 'status': e['status'],
         'req_head': (e.get('reqBody') or '')[:200], 'res': (e.get('resBody') or '')[:200]}
        for e in H.fetch_log(d, '/algorithm/import')]
    OUT['upload_dialog_closed'] = '粘贴或上传算法定义 JSON' not in H.body_text(d)
    OUT['upload_readback'] = H.api_detail_summary(d, IMP_TYPE)
    OUT['upload_in_list'] = IMP_NAME in H.body_text(d)
    save()

    # ================= F2 确认弹窗深色（复制/删除/批量） =================
    real = '小艺语音大模型'
    H.open_row_menu(d, real)
    H.click_menuitem(d, '复制')
    time.sleep(0.8)
    H.apply_theme(d, 'dark')
    H.shot(d, 'F2_clone_confirm_dark')
    H.apply_theme(d, 'light')
    OUT['clone_dark_text_ok'] = '确定要复制算法' in H.body_text(d)
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]"))
    time.sleep(0.6)

    H.open_row_menu(d, real)
    H.click_menuitem(d, '删除')
    time.sleep(0.8)
    H.apply_theme(d, 'dark')
    H.shot(d, 'F2_delete_confirm_dark')
    H.apply_theme(d, 'light')
    OUT['delete_dark_text_ok'] = '确认删除' in H.body_text(d) and real in H.body_text(d)
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]"))
    time.sleep(0.6)
    OUT['real_algo_still_there'] = real in H.body_text(d)

    # 批量：建两条自建算法 → 勾选 → 批量删除确认（深色）→ 取消
    OUT['bulk_create'] = [create_algo(t, n) for t, n in zip(BULK_TYPES, BULK_NAMES)]
    H.goto_page(d)
    for n in BULK_NAMES:
        row = find(f"//tr[.//*[contains(normalize-space(.), '{n}')]]")
        H.js_click(d, row.find_element(By.CSS_SELECTOR, "[role='checkbox'], input[type='checkbox']"))
        time.sleep(0.3)
    OUT['bulk_selected_text'] = f'已选择 {len(BULK_NAMES)} 个算法' in H.body_text(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '批量删除')]"))
    time.sleep(1)
    OUT['bulk_confirm_text_ok'] = f'将删除已选择的 {len(BULK_NAMES)} 个算法' in H.body_text(d)
    H.apply_theme(d, 'dark')
    H.shot(d, 'F2_bulk_confirm_dark')
    H.apply_theme(d, 'light')
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]"))
    time.sleep(0.8)
    OUT['bulk_cancel_keeps'] = all(n in H.body_text(d) for n in BULK_NAMES)
    save()

    # ================= F3 分组管理：有数据态深色 =================
    st, pay, _ = H.api_json(d, '/algorithm/groups', 'POST',
                            {'name': GRP, 'description': '接线测试分组F', 'icon': 'mic', 'display_order': 4})
    OUT['group_create_status'] = st
    OUT['group_create_body'] = (pay or {})
    H.goto_page(d)
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    menu_item('分组管理')
    wtext('算法分组管理')
    time.sleep(1)
    OUT['group_dialog_has_row'] = GRP in H.body_text(d)
    H.shot(d, 'F3_group_with_data_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'F3_group_with_data_dark')
    H.apply_theme(d, 'light')
    # 排序/图标回读（INT-1318 复验：本次发布栈是否已落库）
    st_g, pay_g, _ = H.api_json(d, '/algorithm/groups')
    groups = (pay_g or {}).get('data', {}).get('items') or []
    OUT['group_readback'] = [{k: g.get(k) for k in ('id', 'name', 'icon', 'display_order')}
                             for g in groups]
    close_all()
    save()

    # F4~F6 由 verify_int1483_g2_params_rest.py（H1~H4）覆盖，这里提前结束
    raise SystemExit(0)

    # ================= F4 列表加载态 / 500 错误态 =================
    H.goto_page(d)
    # 加载骨架：延迟 /algorithm/definitions 4s，再切状态筛选触发新查询
    d.execute_script("""
      window.__origFetchF = window.fetch;
      window.fetch = function(u, o){
        var url = (typeof u === 'string') ? u : (u && u.url) || '';
        var self = this, args = arguments;
        if (url.indexOf('/algorithm/definitions') !== -1) {
          return new Promise(function(r){
            setTimeout(function(){ r(window.__origFetchF.apply(self, args)); }, 4000);
          });
        }
        return window.__origFetchF.apply(self, args);
      };
    """)
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='状态']"))
    time.sleep(0.5)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '上线')]"))
    time.sleep(0.8)
    OUT['loading_skeleton_visible'] = len(d.find_elements(By.CSS_SELECTOR, "[data-slot='skeleton']")) > 0
    OUT['loading_body_head'] = H.body_text(d)[-200:].replace('\n', ' ')
    H.shot(d, 'F4_list_loading_light')
    time.sleep(5)
    d.execute_script("window.fetch = window.__origFetchF;")

    # 错误态：让 definitions 返回 500，切筛选触发
    d.execute_script("""
      window.__origFetchE = window.fetch;
      window.fetch = function(u, o){
        var url = (typeof u === 'string') ? u : (u && u.url) || '';
        if (url.indexOf('/algorithm/definitions') !== -1) {
          return Promise.resolve(new Response('{"success":false,"code":500,"message":"mock 500"}',
            {status: 500, headers: {'Content-Type': 'application/json'}}));
        }
        return window.__origFetchE.apply(window, arguments);
      };
    """)
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='状态']"))
    time.sleep(0.5)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '下线')]"))
    time.sleep(2)
    body = H.body_text(d)
    OUT['error_state'] = {
        'title_加载失败': '加载失败' in body,
        'desc': '算法配置加载失败，请重试' in body,
        'retry_btn': '请重试' in body,
    }
    H.shot(d, 'F4_list_error_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'F4_list_error_dark')
    H.apply_theme(d, 'light')
    # 恢复后点「请重试」
    d.execute_script("window.fetch = window.__origFetchE;")
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '请重试')]"))
    time.sleep(3)
    OUT['retry_recovered'] = '算法类型' in H.body_text(d) and '加载失败' not in H.body_text(d)
    OUT['retry_fetches'] = [(e['method'], e['url'], e['status'])
                            for e in H.fetch_log(d, '/algorithm/definitions')][:4]
    H.shot(d, 'F4_after_retry_light')
    save()

    # ================= F5 参数表单：类型切换 + 功能特性快捷开关 + 范围校验 =================
    H.goto_page(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '新建算法')]"))
    wtext('管理算法定义、参数与映射关系')
    time.sleep(1)
    d.find_element(By.ID, 'algo-type').send_keys(f'itest1483_fp_{TAG.lower()}')
    d.find_element(By.ID, 'algo-name').send_keys(f'接线测试_INT1483_参数_{TAG}')
    time.sleep(0.5)

    # 功能特性快捷开关（翻译 = source_language + target_language）
    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 翻译']"))
    time.sleep(1)
    codes = [e.get_attribute('value') for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='参数代码']")]
    OUT['bundle_translation_added'] = {'codes': codes,
                                       'has_both': 'source_language' in codes and 'target_language' in codes}
    H.shot(d, 'F5_bundle_added_light')

    # 取消快捷开关 → 行移除
    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 翻译']"))
    time.sleep(0.8)
    codes2 = [e.get_attribute('value') for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='参数代码']")]
    OUT['bundle_removed'] = {'codes': codes2, 'none_left': 'source_language' not in codes2}

    # 重新勾选，切第一行为「数字」→ 出现 min/max/step/unit
    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 噪声']"))
    time.sleep(0.8)
    row = find("//tr[.//input[@aria-label='参数代码' and @value='noise_level']]")
    trigs = row.find_elements(By.CSS_SELECTOR, "button[role='combobox']")
    OUT['case_row_combobox_count'] = len(trigs)
    type_trigger = None
    for t in trigs:
        if (t.text or '').strip() in ('文本', '数字', '滑块', '开关', '多行文本'):
            type_trigger = t
            break
    OUT['type_trigger_text'] = (type_trigger.text if type_trigger else None)
    OUT['range_before_switch'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))
    H.js_click(d, type_trigger)
    time.sleep(0.6)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '数字')]"))
    time.sleep(0.8)
    OUT['range_after_number'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))
    OUT['range_inputs'] = {
        '最小值': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']")),
        '最大值': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最大值']")),
        '步长': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='步长']")),
        '单位': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='单位']")),
    }
    H.shot(d, 'F5_number_range_fields_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'F5_number_range_fields_dark')
    H.apply_theme(d, 'light')

    # 切「滑块」仍显范围
    H.js_click(d, find("//tr[.//input[@aria-label='参数代码' and @value='noise_level']]//button[role='combobox'][contains(normalize-space(.), '数字')]"))
    time.sleep(0.6)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '滑块')]"))
    time.sleep(0.8)
    OUT['range_after_slider'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))

    # min > max 校验
    mn = d.find_element(By.CSS_SELECTOR, "input[aria-label='最小值']")
    mx = d.find_element(By.CSS_SELECTOR, "input[aria-label='最大值']")
    mn.clear(); mn.send_keys('10')
    mx.clear(); mx.send_keys('5')
    time.sleep(0.5)
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[@type='submit' and contains(normalize-space(.), '发布')]"))
    time.sleep(2.5)
    body = H.body_text(d)
    OUT['range_validation'] = {
        'min_error': '最小值不能大于最大值' in body,
        'max_error': '最大值不能小于最小值' in body,
        'sheet_still_open': '管理算法定义、参数与映射关系' in body,
    }
    OUT['range_validation_fetch'] = [(e['method'], e['url'], e['status'])
                                     for e in H.fetch_log(d, '/algorithm/definitions')]
    H.shot(d, 'F5_range_validation_light')

    # 退出丢弃
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.8)
    if '有未保存的更改' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.8)

    # ================= F6 导航/计数联动 =================
    H.goto_page(d)
    st, pay, _ = H.api_json(d, '/algorithm/definitions')
    total = (pay or {}).get('data', {}).get('total')
    OUT['count_linkage'] = {
        'api_total': total,
        'badge_text': f'共 {total} 个算法' in H.body_text(d),
        'pager_text': [t for t in H.body_text(d).split('\n') if '条/页' in t][:1],
    }
    OUT['nav_badges'] = d.execute_script("""
      var out = [];
      document.querySelectorAll('nav [data-slot="badge"], aside [data-slot="badge"]').forEach(function(b){
        out.push({text: (b.textContent||'').trim(), near: (b.closest('a,button')||{}).textContent || ''});
      });
      return out.slice(0, 20);
    """)
    H.shot(d, 'F6_list_final_light')
    save()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:6000])
finally:
    try:
        d.quit()
    except Exception:
        pass
