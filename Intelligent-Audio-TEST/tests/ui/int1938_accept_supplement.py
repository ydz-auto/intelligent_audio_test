# -*- coding: utf-8 -*-
"""INT-1938 验收补测：请求模板页签 WS 请求头键值回填 + 关窗重开无残留 + 删除后列表无残留。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

TAG = L.PREFIX + 'INT1938B_' + L.RUN_TAG
ART = os.path.join(L.HERE, 'artifacts', 'int1938_accept')
os.makedirs(ART, exist_ok=True)
AUDIO = {'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1, 'container': 'pcm'}
META = {
    'protocol': 'wss', 'environment': 'testing',
    'ws_headers': {'X-Trace': 'int1938b'},
    'session_config': {'turn_detection': True},
    'pacing': {'interval_ms': 200},
    'result_parser': {'text_path': 'data.text'},
    'asr_mapping': {'text': 'text'},
    'int1938b_unknown_key': 'keep-me',
    'append_mode': True,
}


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)


def visible_dialogs(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]


def dialog_by_title(drv, title, timeout=25):
    def f(d):
        for e in visible_dialogs(d):
            if title in (e.text or ''):
                return e
        return None
    return WebDriverWait(drv, timeout).until(f)


def filter_by_name(drv, name):
    inp = WebDriverWait(drv, 25).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "input[aria-label='搜索 API 名称或端点']"))
    drv.execute_script("""
      const el = arguments[0], v = arguments[1];
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    """, inp, name)
    time.sleep(1.2)
    WebDriverWait(drv, 30).until(lambda d: name in L.body_text(d))


def open_edit(drv, name):
    btn = WebDriverWait(drv, 25).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "[aria-label='操作 %s']" % name))
    L.js_click(drv, btn)
    time.sleep(0.6)
    item = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.XPATH, "//*[@data-slot='dropdown-menu-item' and normalize-space(.)='编辑']"))
    L.js_click(drv, item)
    time.sleep(2.0)
    return dialog_by_title(drv, '编辑 API')


def click_tab(drv, dlg, label):
    for el in dlg.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if (el.text or '').strip() == label:
            L.js_click(drv, el)
            time.sleep(0.9)
            return True
    return False


def label_values(dlg, needle):
    out = []
    for el in dlg.find_elements(By.CSS_SELECTOR, 'input, textarea'):
        lab = el.get_attribute('aria-label') or ''
        if needle in lab:
            out.append({'label': lab, 'value': el.get_attribute('value')})
    return out


def main():
    ev = {'tag': TAG, 'base': L.BASE, 'checks': {}}
    drv = L.driver()
    api_id = None
    try:
        L.login(drv)
        ev['checks']['bundle_start'] = drv.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.getAttribute('src'))")
        _, apis_page, _ = L.api_json(drv, '/apis?per_page=20')
        items = (apis_page or {}).get('items') or ((apis_page or {}).get('data') or {}).get('items') or []
        algo = next((it.get('algorithm_type') for it in items if it.get('algorithm_type')), None)
        fixture = {
            'name': TAG, 'vendor': 'int1938b', 'description': 'INT-1938 补测夹具',
            'algorithm_type': algo, 'default_max_process': 2,
            'device_type': 'websocket_api', 'audio_config': AUDIO, 'meta': META,
            'endpoints': [{'endpoint': 'wss://ep.example.com/v1/asr', 'name': '主端点',
                           'priority': 1, 'max_process': 2, 'max_timeout': 30,
                           'max_audio_duration': 60}],
        }
        st, payload, raw = L.api_json(drv, '/apis', 'POST', fixture)
        assert st in (200, 201), 'create failed %s %s' % (st, raw)
        api_id = (payload or {}).get('id') or (payload or {}).get('data', {}).get('id')

        # 1) 请求模板 WS 请求头键值回填（input 的 value 不在 innerText 里，按 aria-label 读）
        drv.get(L.BASE + '/devices/api')
        filter_by_name(drv, TAG)
        dlg = open_edit(drv, TAG)
        click_tab(drv, dlg, '请求模板')
        ev['checks']['request_tab_inputs'] = label_values(dlg, 'WS 请求头')
        ev['checks']['header_rows'] = label_values(dlg, '请求头')
        shot(drv, 'B1_request_headers_light')

        # 2) 关窗重开：不残留上次输入（本轮不改值，核对回填仍等于库值）
        try:
            dlg.find_element(By.XPATH, ".//button[normalize-space(.)='取消']").click()
        except Exception:
            drv.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1.2)
        dlg2 = open_edit(drv, TAG)
        click_tab(drv, dlg2, '请求模板')
        ev['checks']['reopen_header_inputs'] = label_values(dlg2, 'WS 请求头')
        ev['checks']['reopen_session_config'] = drv.execute_script(
            "const el=document.getElementById('meta-session-config'); return el?el.value:null")
        shot(drv, 'B2_reopen_request_light')
        try:
            dlg2.find_element(By.XPATH, ".//button[normalize-space(.)='取消']").click()
        except Exception:
            pass
        time.sleep(0.8)

        # 3) 删除夹具 → 列表不再出现（接口 + 页面）
        st_del, _, raw_del = L.api_json(drv, '/apis/%s' % api_id, 'DELETE')
        ev['checks']['delete_status'] = st_del
        ev['checks']['delete_body'] = raw_del[:200]
        api_id = None  # 已删
        st2, _, _ = L.api_json(drv, '/apis')
        _, page_all, _ = L.api_json(drv, '/apis?per_page=1000')
        all_items = (page_all or {}).get('items') or ((page_all or {}).get('data') or {}).get('items') or []
        ev['checks']['api_list_total'] = len(all_items)
        ev['checks']['int1938_rows_after_delete'] = [
            it.get('name') for it in all_items if 'INT1938' in (it.get('name') or '')
        ]
        drv.get(L.BASE + '/devices/api')
        time.sleep(2.0)
        ev['checks']['page_has_tag_after_delete'] = TAG in L.body_text(drv)
        shot(drv, 'B3_list_after_delete')
        ev['checks']['bundle_end'] = drv.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.getAttribute('src'))")
    finally:
        try:
            if api_id:
                L.api_json(drv, '/apis/%s' % api_id, 'DELETE')
        except Exception:
            pass
        try:
            drv.quit()
        except Exception:
            pass
        out = os.path.join(ART, 'evidence_supplement.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        print('EVIDENCE', out)


if __name__ == '__main__':
    main()
