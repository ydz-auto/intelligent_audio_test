# -*- coding: utf-8 -*-
"""INT-1483 Phase A：列表基线 + 详情 Dialog 逐字段核对 + 确认弹窗（复制/重载）取消与确认。"""
import json
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

OUT = {}


def section(text, title):
    body = H.body_text(d)
    assert text in body, f'缺少 {title}: {text!r}'


d = H.driver()
try:
    print('LOGIN:', H.login(d))
    H.goto_page(d)

    # ---------- A1 列表基线 ----------
    status, payload, raw = H.api_json(d, '/algorithm/definitions')
    items = (payload or {}).get('data', {}).get('items') or (payload or {}).get('items') or []
    OUT['defs_api'] = {'status': status, 'total': len(items),
                       'types': [i.get('type') for i in items]}
    text = H.body_text(d)
    OUT['list_text_head'] = text[:600]
    OUT['list_badge_matches'] = f"共 {len(items)} 个算法" in text
    H.shot(d, 'A1_list_light')

    status_g, payload_g, _ = H.api_json(d, '/algorithm/groups')
    groups = (payload_g or {}).get('data', {}).get('items') or []
    OUT['groups_api'] = {'status': status_g, 'count': len(groups),
                         'items': [{k: g.get(k) for k in ('id', 'name', 'icon', 'display_order')} for g in groups]}

    # 列表请求记录
    OUT['list_fetches'] = [
        {'method': e['method'], 'url': e['url'], 'status': e['status']}
        for e in H.fetch_log(d, '/algorithm/definitions')
    ]

    # ---------- A2 详情 Dialog ----------
    target = items[0] if items else None
    assert target, '列表无真实算法，无法走详情'
    alg_name = target['name']
    alg_type = target['type']
    det = H.api_detail_summary(d, alg_type)
    st = det.get('status')
    detail = det.get('data') or {}
    OUT['detail_api'] = {'status': st, **detail}

    H.open_row_menu(d, alg_name)
    H.click_menuitem(d, '详情')
    WebDriverWait(d, 20).until(lambda dd: '算法定义与参数映射只读详情' in H.body_text(dd))
    time.sleep(0.8)
    H.shot(d, 'A2_detail_light')
    dlg_text = H.body_text(d)
    OUT['detail_dialog_text'] = dlg_text[-2500:]

    dev_n = detail.get('device_params') or 0
    api_n = detail.get('api_params') or 0
    case_n = detail.get('case_params') or 0
    checks = {
        'name': alg_name in dlg_text,
        'type': alg_type in dlg_text,
        'group': (detail.get('group_name') or '未分组') in dlg_text,
        'status_cn': ('上线' if detail.get('status') == 'online' else '下线') in dlg_text,
        'display_order': str(detail.get('display_order')) in dlg_text,
        'param_total': str(dev_n + api_n + case_n) in dlg_text,
        'device_tab': f"设备参数（{dev_n}）" in dlg_text,
        'api_tab': f"API参数（{api_n}）" in dlg_text,
        'case_tab': f"用例参数（{case_n}）" in dlg_text,
        'map_eval_tab': f"评估参数（{detail.get('mappings_evaluation', 0)}）" in dlg_text,
    }
    if detail.get('first_device_param_code'):
        checks['first_device_param_rendered'] = detail['first_device_param_code'] in dlg_text
    if detail.get('first_api_param_code'):
        checks['first_api_param_rendered'] = detail['first_api_param_code'] in dlg_text
    OUT['detail_checks'] = checks

    # 切到 API / 用例页签核对行数
    tabs = {t.text.split('（')[0]: t for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']")}
    OUT['detail_tab_labels'] = [t.text for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']")]
    for label in ('API参数', '用例参数'):
        el = tabs.get(label)
        if el:
            H.js_click(d, el)
            time.sleep(0.5)
    H.shot(d, 'A2_detail_tabs_light')

    # 深色详情
    H.apply_theme(d, 'dark')
    H.shot(d, 'A2_detail_dark')
    H.apply_theme(d, 'light')

    # Esc 关闭
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.8)
    OUT['detail_closed_esc'] = '算法定义与参数映射只读详情' not in H.body_text(d)

    # ---------- A3 复制确认弹窗（取消路径，不产生数据） ----------
    H.open_row_menu(d, alg_name)
    H.click_menuitem(d, '复制')
    time.sleep(0.8)
    confirm_text = H.body_text(d)
    OUT['clone_confirm'] = {
        'title': '确认复制' in confirm_text,
        'desc': f'确定要复制算法「{alg_name}」吗？' in confirm_text,
    }
    H.shot(d, 'A3_clone_confirm_light')
    # 取消
    cancel = WebDriverWait(d, 10).until(
        EC.presence_of_element_located((By.XPATH, "//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]")))
    H.js_click(d, cancel)
    time.sleep(0.6)
    OUT['clone_cancelled'] = not d.find_elements(By.XPATH, "//*[contains(normalize-space(.), '确定要复制算法')]")

    # ---------- A4 重载配置：取消 + 确认 ----------
    more = d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']")
    H.js_click(d, more)
    time.sleep(0.5)
    H.click_menuitem(d, '重载配置')
    time.sleep(0.8)
    OUT['reload_confirm_text'] = '将重载后端算法配置缓存' in H.body_text(d)
    H.shot(d, 'A4_reload_confirm_light')
    H.clear_fetch_log(d)
    ok = d.find_element(By.XPATH, "//div[@role='alertdialog']//button[contains(normalize-space(.), '重载')]")
    H.js_click(d, ok)
    toasts = H.wait_toast(d, 25)
    OUT['reload_toasts'] = toasts
    OUT['reload_fetch'] = [{'method': e['method'], 'url': e['url'], 'status': e['status']}
                           for e in H.fetch_log(d, '/algorithm/reload')]

    # 深色列表截图
    H.apply_theme(d, 'dark')
    H.shot(d, 'A4_list_dark')
    H.apply_theme(d, 'light')

    # 浏览器控制台错误
    try:
        errs = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
        OUT['console_severe'] = errs
    except Exception:
        OUT['console_severe'] = []

    H.save_evidence('phaseA_list_detail', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:4000])
finally:
    d.quit()
