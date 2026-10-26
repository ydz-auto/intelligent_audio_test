# -*- coding: utf-8 -*-
"""INT-1938 验收：「测试 API」页签行「编辑」复用 §5.3 五页签 API 编辑弹窗（与开始测试同件）。

连 docker 真实栈：前端 dev server（本 worktree，代理 15000）。只写本 run 自建的「接线测试_」记录。

核对项：
1. 行菜单「编辑」/ 详情「编辑」→ 弹窗标题「编辑 API」，5 个页签齐全（bug 现象：0 页签旧抽屉）
2. 请求模板页签回显 meta（method/body_template），响应解析页签可见；输出字段/映射页签可切
3. 基础页签回显 audio_config 与显式 device_type（websocket_api）
4. 保存只改 meta 的一个键 → GET 回读：新键生效、未知键与 audio_config 均未被清
5. 保存后本页「测试 API」列表自动刷新（改名可见）
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

TAG = L.PREFIX + 'INT1938_' + L.RUN_TAG
ART = os.path.join(L.HERE, 'artifacts', 'int1938')
os.makedirs(ART, exist_ok=True)


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def dialog_by_title(drv, title, timeout=25):
    def f(d):
        for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
            if e.is_displayed() and title in (e.text or ''):
                return e
        return None
    return WebDriverWait(drv, timeout).until(f)


def tab_labels(drv, dlg):
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
            time.sleep(0.8)
            return True
    return False


def filter_by_name(drv, name, timeout=30):
    """用页内搜索框收窄到本夹具行（列表 1000 条全量拉取，前端分页）。"""
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


def open_row_menu(drv, name):
    btn = WebDriverWait(drv, 25).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "[aria-label='操作 %s']" % name))
    L.js_click(drv, btn)
    time.sleep(0.6)
    item = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(
            By.XPATH, "//*[@data-slot='dropdown-menu-item' and normalize-space(.)='编辑']"))
    L.js_click(drv, item)
    time.sleep(1.0)


def main():
    evidence = {'tag': TAG, 'checks': {}, 'fetch': []}
    drv = L.driver()
    try:
        url = L.login(drv)
        print('LOGIN ->', url)
        L.clear_fetch_log(drv)

        # ── 夹具：一条带 meta（含未知键）+ audio_config + 显式 device_type 的自建 API ──
        # 算法类型取库里既有 API 的值，保证「关联算法」下拉能正常回显
        _, apis_page, _ = L.api_json(drv, '/apis?per_page=20')
        page = apis_page or {}
        items = page.get('items') or (page.get('data') or {}).get('items') or []
        algo = next((it.get('algorithm_type') for it in items if it.get('algorithm_type')), None)
        print('ALGO FROM EXISTING', algo)
        fixture = {
            'name': TAG,
            'vendor': 'int1938',
            'description': 'INT-1938 验收夹具',
            'algorithm_type': algo,
            'default_max_process': 3,
            'device_type': 'websocket_api',
            'audio_config': {'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1, 'container': 'pcm'},
            'meta': {
                'protocol': 'wss',
                'environment': 'testing',
                # HTTP 组键（切到 HTTP API 设备类型才显示）
                'method': 'POST',
                'headers': {'Authorization': 'Bearer {{token}}'},
                'body_template': {'text': '{{audio_b64}}'},
                # WS 组键（websocket_api 设备类型下显示）
                'ws_headers': {'X-Trace': 'int1938'},
                'session_config': {'turn_detection': True},
                'pacing': {'interval_ms': 200},
                'result_parser': {'text_path': 'data.text'},
                'asr_mapping': {'text': 'text'},
                'append_mode': True,
                'int1938_unknown_key': 'keep-me',
            },
            'endpoints': [
                {'endpoint': 'wss://ep.example.com/v1/asr', 'name': '主端点',
                 'priority': 1, 'max_process': 3, 'max_timeout': 30, 'max_audio_duration': 60},
            ],
        }
        st, payload, raw = L.api_json(drv, '/apis', 'POST', fixture)
        print('CREATE', st, raw[:300])
        assert st in (200, 201), 'create fixture failed: %s %s' % (st, raw)
        api_id = (payload or {}).get('id') or (payload or {}).get('data', {}).get('id')
        assert api_id, 'no id in create response: %s' % raw
        evidence['api_id'] = api_id
        # 夹具落库核对（POST 是否真存了 meta / audio_config / device_type）
        _, fx, _ = L.api_json(drv, '/apis/%s' % api_id)
        fx = (fx or {}).get('data') or fx or {}
        evidence['fixture'] = {
            'device_type': fx.get('device_type'),
            'audio_config': fx.get('audio_config'),
            'meta_keys': sorted((fx.get('meta') or {}).keys()),
        }
        print('FIXTURE', evidence['fixture'])
        time.sleep(1.5)

        # ── 1. 行菜单「编辑」→ 五页签弹窗 ──
        drv.get(L.BASE + '/devices/api')
        filter_by_name(drv, TAG)
        open_row_menu(drv, TAG)
        dlg = dialog_by_title(drv, '编辑 API')
        labels = tab_labels(drv, dlg)
        title = dlg.find_element(By.CSS_SELECTOR, 'h2, [data-slot="dialog-title"]').text or ''
        evidence['checks']['dialog_title'] = title
        evidence['checks']['tabs'] = labels
        print('DIALOG', title, labels)
        shot(drv, 'P1_dialog_basic_light')

        # ── 2. 基础页签回显 audio_config / device_type ──
        body = L.body_text(drv)
        evidence['checks']['basic_has_audio_config'] = '音频格式（audio_config）' in body
        evidence['checks']['basic_audio_sample_rate_16000'] = '16000 Hz' in body
        evidence['checks']['basic_audio_bit_depth_s16'] = 's16' in body
        evidence['checks']['basic_device_type_ws'] = 'Realtime WS' in body
        evidence['checks']['basic_text_head'] = body[:600]
        shot(drv, 'P2_basic_audio_light')

        # ── 3. 请求模板页签：meta 回显（夹具是 websocket_api → WS 组）──
        evidence['checks']['tab_request_clicked'] = click_tab(drv, dlg, '请求模板')
        t2 = L.body_text(drv)
        evidence['checks']['request_ws_badge'] = 'Realtime WS（websocket_api）' in t2
        evidence['checks']['request_has_session_config'] = '会话配置（session_config）' in t2
        evidence['checks']['request_has_pacing'] = '节奏控制（pacing）' in t2
        evidence['checks']['request_ws_head'] = t2[t2.find('按目标设备类型显隐'):][:700]
        # meta WS 组键是否真的回填到控件（不是空壳页签）
        evidence['checks']['session_config_value'] = drv.execute_script(
            "const el=document.getElementById('meta-session-config'); return el ? el.value : null")
        evidence['checks']['pacing_value'] = drv.execute_script(
            "const el=document.getElementById('meta-pacing'); return el ? el.value : null")
        shot(drv, 'P3_request_tab_light')

        # ── 4. 响应解析 / 输出字段 / 映射 页签可切 ──
        evidence['checks']['tab_response_clicked'] = click_tab(drv, dlg, '响应解析')
        t3 = L.body_text(drv)
        evidence['checks']['response_has_parser'] = 'result_parser' in t3
        shot(drv, 'P4_response_tab_light')
        evidence['checks']['tab_output_clicked'] = click_tab(drv, dlg, '输出字段')
        time.sleep(1.2)
        evidence['checks']['output_text'] = L.body_text(drv)[:400]
        shot(drv, 'P5_output_tab_light')
        evidence['checks']['tab_mapping_clicked'] = click_tab(drv, dlg, '映射')
        time.sleep(1.2)
        shot(drv, 'P6_mapping_tab_light')

        # 深色同屏核对（同源：同一弹窗切主题）
        L.apply_theme(drv, 'dark')
        shot(drv, 'P7_mapping_tab_dark')
        click_tab(drv, dlg, '基础')
        shot(drv, 'P8_basic_dark')
        click_tab(drv, dlg, '请求模板')
        shot(drv, 'P9_request_dark')
        L.apply_theme(drv, 'light')
        click_tab(drv, dlg, '基础')

        # ── 5. 改名保存 → 列表自动刷新 + 接口回读 ──
        new_name = TAG + '_改'
        name_input = dlg.find_element(By.ID, 'api-name')
        drv.execute_script("""
          const el = arguments[0], v = arguments[1];
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, v);
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """, name_input, new_name)
        time.sleep(0.6)
        save_btn = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='保存']")
        L.clear_fetch_log(drv)
        L.js_click(drv, save_btn)
        toasts = L.wait_toast(drv, 25)
        evidence['checks']['save_toasts'] = toasts
        time.sleep(2.0)
        evidence['fetch'] = [
            {k: e.get(k) for k in ('method', 'url', 'status', 'reqBody')}
            for e in L.fetch_log(drv, '/apis')
        ]
        shot(drv, 'P10_after_save_light')

        # 列表刷新（不手动 reload）
        refreshed = False
        try:
            WebDriverWait(drv, 20).until(lambda d: new_name in L.body_text(d))
            refreshed = True
        except Exception:
            pass
        evidence['checks']['list_refreshed'] = refreshed
        shot(drv, 'P11_list_after_save_light')

        # 接口回读核对（meta 未丢、audio_config 未动、device_type 未被清）
        st, detail, raw2 = L.api_json(drv, '/apis/%s' % api_id)
        detail = (detail or {}).get('data') or detail or {}
        meta = detail.get('meta') or {}
        evidence['checks']['readback_status'] = st
        evidence['checks']['meta_unknown_key_kept'] = meta.get('int1938_unknown_key') == 'keep-me'
        evidence['checks']['meta_keys'] = sorted(meta.keys())
        evidence['checks']['audio_config'] = detail.get('audio_config')
        evidence['checks']['device_type'] = detail.get('device_type')
        evidence['checks']['name'] = detail.get('name')

        # 回读后再开一次：device_type 仍回显 websocket_api（不被写成 auto/null）
        drv.get(L.BASE + '/devices/api')
        filter_by_name(drv, new_name)
        open_row_menu(drv, new_name)
        dlg2 = dialog_by_title(drv, '编辑 API')
        body2 = L.body_text(drv)
        evidence['checks']['reopen_basic_text'] = body2[:500]
        shot(drv, 'P12_reopen_basic_light')
        # 关掉弹窗
        try:
            drv.find_element(By.XPATH, "//*[normalize-space(text())='取消']").click()
        except Exception:
            drv.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1)

    finally:
        # 清理夹具
        try:
            sid = evidence.get('api_id')
            if sid:
                st, _, raw = L.api_json(drv, '/apis/%s' % sid, 'DELETE')
                evidence['cleanup'] = {'status': st, 'body': raw[:200]}
                st2, _, _ = L.api_json(drv, '/apis/%s' % sid)
                evidence['cleanup']['readback_status'] = st2
        except Exception as e:
            evidence['cleanup'] = {'error': str(e)}
        try:
            drv.quit()
        except Exception:
            pass
        out = os.path.join(ART, 'evidence.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)
        print('EVIDENCE', out)


if __name__ == '__main__':
    main()
