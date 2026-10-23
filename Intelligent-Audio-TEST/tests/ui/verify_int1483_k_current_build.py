# -*- coding: utf-8 -*-
"""INT-1483 Phase K（当前前端构建复核）：加载骨架屏 + 批量删除确认深色 + 分组管理有数据深色。"""
import json
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'K' + H.RUN_TAG
GRP = f'接线测试_INT1483_分组K_{TAG}'
TYPES = [f'itest1483_k1_{TAG.lower()}', f'itest1483_k2_{TAG.lower()}']
NAMES = [f'接线测试_INT1483_批量K1_{TAG}', f'接线测试_INT1483_批量K2_{TAG}']
OUT = {'tag': TAG, 'grp': GRP, 'types': TYPES}

SLOW_JS = r"""
(function(){
  var orig = window.fetch;
  window.fetch = function(u, o){
    var url = (typeof u === 'string') ? u : (u && u.url) || '';
    var self = this, args = arguments;
    if (url.indexOf('/algorithm/definitions') !== -1) {
      return new Promise(function(r){ setTimeout(function(){ r(orig.apply(self, args)); }, 6000); });
    }
    return orig.apply(self, args);
  };
})();
"""


def find(xp, t=15):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def wtext(text, t=25):
    WebDriverWait(d, t).until(lambda x: text in H.body_text(x))


def save():
    H.save_evidence('phaseK_current_build', OUT)


d = H.driver()
try:
    H.login(d)

    # ---- K1 加载骨架屏 ----
    sid = d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': SLOW_JS})['identifier']
    d.get(H.BASE + '/AlgorithmConfig')
    time.sleep(2.0)
    OUT['loading'] = {
        'skeleton_count': len(d.find_elements(By.CSS_SELECTOR, "[data-slot='skeleton']")),
        'table_absent': '算法类型' not in H.body_text(d),
    }
    H.shot(d, 'K1_list_loading_light')
    d.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': sid})
    wtext('算法类型', 60)
    time.sleep(1)
    OUT['loading_resolved'] = '算法类型' in H.body_text(d)
    save()

    # ---- K2 分组管理有数据（浅/深）----
    st, pay, _ = H.api_json(d, '/algorithm/groups', 'POST',
                            {'name': GRP, 'description': '接线测试分组K', 'icon': 'mic', 'display_order': 5})
    OUT['group_create_status'] = st
    H.goto_page(d)
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    H.js_click(d, WebDriverWait(d, 10).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '分组管理')]"))))
    wtext('算法分组管理')
    time.sleep(1.2)
    OUT['group_row_visible'] = GRP in H.body_text(d)
    H.shot(d, 'K2_group_with_data_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'K2_group_with_data_dark')
    H.apply_theme(d, 'light')
    st_g, pay_g, _ = H.api_json(d, '/algorithm/groups')
    OUT['group_readback'] = [{k: g.get(k) for k in ('id', 'name', 'icon', 'display_order')}
                             for g in ((pay_g or {}).get('data', {}).get('items') or [])]
    H.close_overlays(d)
    time.sleep(0.6)
    save()

    # ---- K3 批量删除确认弹窗（深色）----
    for t, n in zip(TYPES, NAMES):
        H.api_json(d, '/algorithm/definitions', 'POST', {
            'type': t, 'name': n, 'group_id': None, 'display_order': 1, 'status': 'offline',
            'description': '接线测试 Phase K', 'device_params': [], 'api_params': [], 'case_params': [],
            'reference_params': [], 'mappings': {'device': [], 'api': [], 'evaluation': []},
            'associated_dimensions': []})
    H.goto_page(d)
    for n in NAMES:
        row = find(f"//tr[.//*[contains(normalize-space(.), '{n}')]]")
        H.js_click(d, row.find_element(By.CSS_SELECTOR, "[role='checkbox'], input[type='checkbox']"))
        time.sleep(0.3)
    OUT['bulk_selected'] = f'已选择 {len(NAMES)} 个算法' in H.body_text(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '批量删除')]"))
    time.sleep(1)
    OUT['bulk_confirm_text'] = f'将删除已选择的 {len(NAMES)} 个算法' in H.body_text(d)
    H.apply_theme(d, 'dark')
    H.shot(d, 'K3_bulk_confirm_dark')
    H.apply_theme(d, 'light')
    H.shot(d, 'K3_bulk_confirm_light')
    H.js_click(d, find("//div[@role='alertdialog']//button[contains(normalize-space(.), '取消')]"))
    time.sleep(0.8)
    OUT['bulk_cancel_keeps'] = all(n in H.body_text(d) for n in NAMES)

    # 清理本阶段自建数据
    for t in TYPES:
        H.api_json(d, f'/algorithm/definitions/{t}', 'DELETE')
    groups = ((H.api_json(d, '/algorithm/groups')[1] or {}).get('data', {}) or {}).get('items') or []
    for g in groups:
        if '接线测试_INT1483' in (g.get('name') or ''):
            H.api(d, f"/algorithm/groups/{g['id']}", 'DELETE')
    save()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
finally:
    try:
        d.quit()
    except Exception:
        pass
