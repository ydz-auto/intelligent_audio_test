# -*- coding: utf-8 -*-
"""INT-1938 验收：「设备管理 → 测试 API」页签「编辑」复用 §5.3 五页签 api-edit 弹窗。

连 docker 真实栈（后端网关 15000 / 前端用 docker 容器，REACT_BASE 指定）。
本脚本两种模式（环境变量 INT1938_MODE）：
  prefix —— 共享 15173（wiring/react 头构建，不含本卡修复）：记录入口打开的是什么，用于对照；
  fix    —— 旁路容器（交付提交 dcda7bc29 的 dist）：完整验收（回显 / 编辑保存 / 回读 / 刷新）。

只写本 run 自建的「接线测试_」记录，finally 里删除并回读确认。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

MODE = os.environ.get('INT1938_MODE', 'fix')
TAG = L.PREFIX + 'INT1938A_' + L.RUN_TAG
ART = os.path.join(L.HERE, 'artifacts', 'int1938_accept')
os.makedirs(ART, exist_ok=True)

AUDIO = {'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1, 'container': 'pcm'}
META = {
    'protocol': 'wss',
    'environment': 'testing',
    'method': 'POST',
    'headers': {'Authorization': 'Bearer {{token}}'},
    'body_template': {'text': '{{audio_b64}}'},
    'ws_headers': {'X-Trace': 'int1938a'},
    'session_config': {'turn_detection': True},
    'pacing': {'interval_ms': 200},
    'result_parser': {'text_path': 'data.text'},
    'asr_mapping': {'text': 'text'},
    'append_mode': True,
    'int1938a_unknown_key': 'keep-me',
}


def shot(drv, name):
    p = os.path.join(ART, '%s_%s.png' % (MODE, name))
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def visible_dialogs(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]


def dialog_by_title(drv, title, timeout=25):
    def f(d):
        for e in visible_dialogs(d):
            t = e.text or ''
            if title in t:
                return e
        return None
    return WebDriverWait(drv, timeout).until(f)


def dialog_heading(dlg):
    for sel in ('[data-slot="dialog-title"]', 'h2', 'h3'):
        for el in dlg.find_elements(By.CSS_SELECTOR, sel):
            t = (el.text or '').strip()
            if t:
                return t
    return ''


def tab_labels(dlg):
    out = []
    for el in dlg.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        t = (el.text or '').strip()
        if t:
            out.append(t)
    return out


def click_tab(drv, dlg, label):
    for el in dlg.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if (el.text or '').strip() == label:
            L.js_click(drv, el)
            time.sleep(0.9)
            return True
    return False


def filter_by_name(drv, name, timeout=30):
    inp = WebDriverWait(drv, 25).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "input[aria-label='搜索 API 名称或端点']"))
    drv.execute_script("""
      const el = arguments[0], v = arguments[1];
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    """, inp, name)
    time.sleep(1.2)
    WebDriverWait(drv, timeout).until(lambda d: name in L.body_text(d))


def menu_item(drv, label):
    return WebDriverWait(drv, 15).until(
        lambda d: d.find_element(
            By.XPATH, "//*[@data-slot='dropdown-menu-item' and normalize-space(.)='%s']" % label))


def open_row_menu(drv, name):
    btn = WebDriverWait(drv, 25).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "[aria-label='操作 %s']" % name))
    L.js_click(drv, btn)
    time.sleep(0.6)


def set_input(drv, el, value):
    drv.execute_script("""
      const el = arguments[0], v = arguments[1];
      const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                                              : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    """, el, value)
    time.sleep(0.4)


def bundle_fingerprint(drv):
    try:
        return drv.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src'));")
    except Exception:
        return []


def create_fixture(drv):
    _, apis_page, _ = L.api_json(drv, '/apis?per_page=20')
    page = apis_page or {}
    items = page.get('items') or (page.get('data') or {}).get('items') or []
    algo = next((it.get('algorithm_type') for it in items if it.get('algorithm_type')), None)
    fixture = {
        'name': TAG,
        'vendor': 'int1938a',
        'description': 'INT-1938 验收夹具（测试工程师）',
        'algorithm_type': algo,
        'default_max_process': 3,
        'device_type': 'websocket_api',
        'audio_config': AUDIO,
        'meta': dict(META),
        'endpoints': [
            {'endpoint': 'wss://ep.example.com/v1/asr', 'name': '主端点', 'priority': 1,
             'max_process': 3, 'max_timeout': 30, 'max_audio_duration': 60},
        ],
    }
    st, payload, raw = L.api_json(drv, '/apis', 'POST', fixture)
    print('CREATE', st, raw[:200])
    assert st in (200, 201), 'create fixture failed: %s %s' % (st, raw)
    api_id = (payload or {}).get('id') or (payload or {}).get('data', {}).get('id')
    assert api_id, 'no id: %s' % raw
    return api_id, algo


def main():
    ev = {'mode': MODE, 'base': L.BASE, 'tag': TAG, 'checks': {}, 'shots': {}}
    drv = L.driver()
    api_id = None
    try:
        url = L.login(drv)
        ev['checks']['landing'] = url
        ev['checks']['bundle'] = bundle_fingerprint(drv)
        L.clear_fetch_log(drv)

        api_id, algo = create_fixture(drv)
        ev['api_id'] = api_id
        ev['algorithm_type'] = algo
        _, fx, _ = L.api_json(drv, '/apis/%s' % api_id)
        fx = (fx or {}).get('data') or fx or {}
        ev['checks']['fixture'] = {
            'device_type': fx.get('device_type'),
            'audio_config': fx.get('audio_config'),
            'meta_keys': sorted((fx.get('meta') or {}).keys()),
            'meta_count': len(fx.get('meta') or {}),
        }
        print('FIXTURE', ev['checks']['fixture'])
        time.sleep(1.0)

        # ── 入口：设备管理 → 测试 API → 行菜单「编辑」 ──
        drv.get(L.BASE + '/devices/api')
        filter_by_name(drv, TAG)
        L.clear_fetch_log(drv)
        open_row_menu(drv, TAG)
        L.js_click(drv, menu_item(drv, '编辑'))
        time.sleep(2.0)
        dlg = dialog_by_title(drv, 'API') if MODE == 'fix' else None
        if MODE == 'fix':
            title = dialog_heading(dlg)
            tabs = tab_labels(dlg)
        else:
            # 修复前：等任一可见弹层，记标题 / 页签
            WebDriverWait(drv, 20).until(lambda d: len(visible_dialogs(d)) > 0)
            time.sleep(1.0)
            dlg = visible_dialogs(drv)[-1]
            title = dialog_heading(dlg)
            tabs = tab_labels(dlg)
        ev['checks']['entry_dialog_title'] = title
        ev['checks']['entry_tabs'] = tabs
        ev['checks']['entry_is_api_edit'] = ('编辑 API' == title)
        print('ENTRY', title, tabs)
        ev['shots']['entry'] = shot(drv, 'E1_entry_' + MODE)
        ev['checks']['entry_body'] = L.body_text(drv)[:800]
        ev['checks']['entry_requests'] = [
            {k: e.get(k) for k in ('method', 'url', 'status')} for e in L.fetch_log(drv)
        ]

        if MODE == 'prefix':
            # 对照侧到此为止：只要证明「修复前这个入口不是五页签弹窗」
            ev['checks']['prefix_has_five_tabs'] = (tabs == ['基础', '请求模板', '响应解析', '输出字段', '映射'])
            return

        assert title == '编辑 API', 'entry dialog title=%r' % title

        # ── 基础页签：audio_config + 显式 device_type 回显 ──
        body = L.body_text(drv)
        ev['checks']['basic'] = {
            'has_audio_section': '音频格式（audio_config）' in body,
            'sample_rate_16000': '16000 Hz' in body,
            'bit_depth_s16': 's16' in body,
            'channels_1': '1' in body,
            'container_pcm': 'pcm' in body.lower(),
            'device_type_realtime_ws': 'Realtime WS' in body,
        }
        ev['shots']['basic_light'] = shot(drv, 'P1_basic_light')

        # ── 请求模板页签：meta 回显（WS 组键）──
        ev['checks']['tab_request_clicked'] = click_tab(drv, dlg, '请求模板')
        tb = L.body_text(drv)
        ev['checks']['request'] = {
            'ws_badge': 'Realtime WS（websocket_api）' in tb,
            'session_config_label': '会话配置（session_config）' in tb,
            'pacing_label': '节奏控制（pacing）' in tb,
            'ws_headers_label': 'WS 请求头' in tb,
            'ws_header_row_value': 'X-Trace' in tb and 'int1938a' in tb,
            'session_config_value': drv.execute_script(
                "const el=document.getElementById('meta-session-config'); return el?el.value:null"),
            'pacing_value': drv.execute_script(
                "const el=document.getElementById('meta-pacing'); return el?el.value:null"),
        }
        ev['shots']['request_light'] = shot(drv, 'P2_request_light')

        # ── 响应解析页签：result_parser 回显 ──
        ev['checks']['tab_response_clicked'] = click_tab(drv, dlg, '响应解析')
        time.sleep(1.0)
        ev['checks']['response'] = {
            'has_result_parser': 'result_parser' in L.body_text(drv),
            'result_parser_value': drv.execute_script(
                "const el=document.getElementById('meta-result-parser'); return el?el.value:null"),
        }
        ev['shots']['response_light'] = shot(drv, 'P3_response_light')

        # ── 输出字段 / 映射 页签渲染 + 只读数据源真实请求 ──
        ev['checks']['tab_output_clicked'] = click_tab(drv, dlg, '输出字段')
        time.sleep(1.2)
        ev['checks']['output_text'] = L.body_text(drv)[:600]
        ev['shots']['output_light'] = shot(drv, 'P4_output_light')
        ev['checks']['tab_mapping_clicked'] = click_tab(drv, dlg, '映射')
        time.sleep(1.2)
        ev['checks']['mapping_text'] = L.body_text(drv)[:600]
        ev['shots']['mapping_light'] = shot(drv, 'P5_mapping_light')
        ev['checks']['readonly_requests'] = [
            {k: e.get(k) for k in ('method', 'url', 'status')}
            for e in L.fetch_log(drv) if '/algorithm' in (e.get('url') or '')
        ]

        # ── 深色（同一次弹窗切主题，同源）──
        L.apply_theme(drv, 'dark')
        click_tab(drv, dlg, '基础')
        ev['shots']['basic_dark'] = shot(drv, 'P6_basic_dark')
        click_tab(drv, dlg, '请求模板')
        ev['shots']['request_dark'] = shot(drv, 'P7_request_dark')
        L.apply_theme(drv, 'light')

        # ── 编辑 meta 一个键 + 改名 → 保存；核 PUT 请求体 ──
        click_tab(drv, dlg, '基础')
        new_name = TAG + '_改'
        name_input = dlg.find_element(By.ID, 'api-name')
        set_input(drv, name_input, new_name)
        click_tab(drv, dlg, '请求模板')
        pacing_el = dlg.find_element(By.ID, 'meta-pacing')
        set_input(drv, pacing_el, '{"interval_ms": 250}')
        ev['checks']['pacing_after_edit'] = pacing_el.get_attribute('value')
        L.clear_fetch_log(drv)
        save_btn = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='保存']")
        L.js_click(drv, save_btn)
        ev['checks']['save_toasts'] = L.wait_toast(drv, 25)
        time.sleep(2.0)
        puts = [e for e in L.fetch_log(drv, '/apis') if e.get('method') == 'PUT']
        ev['checks']['save_puts'] = [
            {'method': e.get('method'), 'url': e.get('url'), 'status': e.get('status'),
             'reqBody': (e.get('reqBody') or '')[:1500]} for e in puts
        ]
        if puts:
            try:
                body_json = json.loads(puts[-1].get('reqBody') or '{}')
            except Exception:
                body_json = {}
            meta_sent = body_json.get('meta') or {}
            ev['checks']['save_body_meta'] = meta_sent
            ev['checks']['save_sends_meta'] = bool(meta_sent)
            ev['checks']['save_body_has_audio_config'] = 'audio_config' in body_json
            ev['checks']['save_body_device_type'] = body_json.get('device_type')

        # ── 列表自动刷新（不手动 reload）──
        try:
            WebDriverWait(drv, 20).until(lambda d: new_name in L.body_text(d))
            ev['checks']['list_refreshed'] = True
        except Exception:
            ev['checks']['list_refreshed'] = False
        ev['shots']['list_after_save'] = shot(drv, 'P8_list_after_save')

        # ── GET 回读：meta / audio_config / device_type 未被清 ──
        st, detail, raw = L.api_json(drv, '/apis/%s' % api_id)
        detail = (detail or {}).get('data') or detail or {}
        meta = detail.get('meta') or {}
        ev['checks']['readback'] = {
            'status': st,
            'name': detail.get('name'),
            'meta_count': len(meta),
            'meta_keys': sorted(meta.keys()),
            'unknown_key_kept': meta.get('int1938a_unknown_key') == 'keep-me',
            'pacing': meta.get('pacing'),
            'session_config': meta.get('session_config'),
            'audio_config': detail.get('audio_config'),
            'device_type': detail.get('device_type'),
            'default_max_process': detail.get('default_max_process'),
        }

        # ── 重开：改名后的行 → 编辑，确认持久化 + 回显 ──
        drv.get(L.BASE + '/devices/api')
        filter_by_name(drv, new_name)
        open_row_menu(drv, new_name)
        L.js_click(drv, menu_item(drv, '编辑'))
        time.sleep(2.0)
        dlg2 = dialog_by_title(drv, '编辑 API')
        ev['checks']['reopen'] = {
            'title': dialog_heading(dlg2),
            'tabs': tab_labels(dlg2),
            'basic_has_ws': 'Realtime WS' in L.body_text(drv),
            'name_value': dlg2.find_element(By.ID, 'api-name').get_attribute('value'),
        }
        click_tab(drv, dlg2, '请求模板')
        ev['checks']['reopen']['pacing_value'] = drv.execute_script(
            "const el=document.getElementById('meta-pacing'); return el?el.value:null")
        ev['shots']['reopen_basic'] = shot(drv, 'P9_reopen_request')

        # 关闭弹窗（取消）
        try:
            dlg2.find_element(By.XPATH, ".//button[normalize-space(.)='取消']").click()
            time.sleep(1.0)
        except Exception:
            try:
                drv.find_element(By.CSS_SELECTOR, "[role='dialog'] [data-slot='dialog-close']").click()
                time.sleep(1.0)
            except Exception:
                pass

        # ── 详情弹窗内的「编辑」也开同件 ──
        drv.get(L.BASE + '/devices/api')
        filter_by_name(drv, new_name)
        open_row_menu(drv, new_name)
        L.js_click(drv, menu_item(drv, '详情'))
        time.sleep(1.5)
        detail_dlg = dialog_by_title(drv, '')
        try:
            edit_btn = detail_dlg.find_element(By.XPATH, ".//button[normalize-space(.)='编辑']")
            L.js_click(drv, edit_btn)
            time.sleep(2.0)
            dlg3 = dialog_by_title(drv, '编辑 API')
            ev['checks']['detail_entry'] = {
                'title': dialog_heading(dlg3),
                'tabs': tab_labels(dlg3),
                'device_type_realtime_ws': 'Realtime WS' in L.body_text(drv),
            }
            ev['shots']['detail_entry'] = shot(drv, 'P10_detail_entry')
            try:
                dlg3.find_element(By.XPATH, ".//button[normalize-space(.)='取消']").click()
            except Exception:
                pass
            time.sleep(0.8)
        except Exception as e:
            ev['checks']['detail_entry'] = {'error': str(e)}

        # ── 全量列表里不残留本卡夹具（含交付方那批已软删的记录不可见）──
        _, page_all, _ = L.api_json(drv, '/apis?per_page=1000')
        all_items = (page_all or {}).get('items') or ((page_all or {}).get('data') or {}).get('items') or []
        ev['checks']['list_total'] = len(all_items)
        ev['checks']['fixture_rows_in_list'] = [
            it.get('name') for it in all_items if 'INT1938' in (it.get('name') or '')
        ]

    finally:
        cleanup = {}
        try:
            if api_id:
                st, _, raw = L.api_json(drv, '/apis/%s' % api_id, 'DELETE')
                cleanup['delete_status'] = st
                cleanup['delete_body'] = raw[:200]
                st2, _, raw2 = L.api_json(drv, '/apis/%s' % api_id)
                cleanup['readback_status_after_delete'] = st2
                cleanup['readback_body'] = raw2[:200]
        except Exception as e:
            cleanup['error'] = str(e)
        ev['cleanup'] = cleanup
        try:
            drv.quit()
        except Exception:
            pass
        out = os.path.join(ART, 'evidence_%s.json' % MODE)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        print('EVIDENCE', out)


if __name__ == '__main__':
    main()
