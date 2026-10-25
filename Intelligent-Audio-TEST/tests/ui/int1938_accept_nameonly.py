# -*- coding: utf-8 -*-
"""INT-1938 补充核对：只改名称保存（不触碰 meta / audio_config）时，PUT 不提交这两列，回读原样保留。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

TAG = L.PREFIX + 'INT1938C_' + L.RUN_TAG
ART = os.path.join(L.HERE, 'artifacts', 'int1938_accept')
os.makedirs(ART, exist_ok=True)


def visible_dialogs(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]


def dialog_by_title(drv, title, timeout=25):
    def f(d):
        for e in visible_dialogs(d):
            if title in (e.text or ''):
                return e
        return None
    return WebDriverWait(drv, timeout).until(f)


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


def main():
    ev = {'tag': TAG, 'base': L.BASE, 'checks': {}}
    drv = L.driver()
    api_id = None
    try:
        L.login(drv)
        _, apis_page, _ = L.api_json(drv, '/apis?per_page=20')
        items = (apis_page or {}).get('items') or ((apis_page or {}).get('data') or {}).get('items') or []
        algo = next((it.get('algorithm_type') for it in items if it.get('algorithm_type')), None)
        fixture = {
            'name': TAG, 'vendor': 'int1938c', 'description': 'INT-1938 数据安全核对',
            'algorithm_type': algo, 'default_max_process': 4,
            'device_type': 'websocket_api',
            'audio_config': {'sample_rate': 24000, 'bit_depth': 's24', 'channels': 2, 'container': 'wav'},
            'meta': {'protocol': 'wss', 'ws_headers': {'X-K': 'v'},
                     'session_config': {'x': 1}, 'int1938c_unknown': 'keep',
                     'append_mode': True},
            'endpoints': [{'endpoint': 'wss://ep.example.com/v1/asr', 'name': '主端点',
                           'priority': 1, 'max_process': 4, 'max_timeout': 30,
                           'max_audio_duration': 60}],
        }
        st, payload, raw = L.api_json(drv, '/apis', 'POST', fixture)
        assert st in (200, 201), 'create failed %s %s' % (st, raw)
        api_id = (payload or {}).get('id') or (payload or {}).get('data', {}).get('id')
        _, before, _ = L.api_json(drv, '/apis/%s' % api_id)
        before = (before or {}).get('data') or before or {}
        ev['checks']['before'] = {'meta': before.get('meta'), 'audio': before.get('audio_config'),
                                  'device_type': before.get('device_type')}

        drv.get(L.BASE + '/devices/api')
        inp = WebDriverWait(drv, 25).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "input[aria-label='搜索 API 名称或端点']"))
        drv.execute_script("""
          const el = arguments[0], v = arguments[1];
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, v);
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """, inp, TAG)
        time.sleep(1.2)
        WebDriverWait(drv, 30).until(lambda d: TAG in L.body_text(d))
        btn = WebDriverWait(drv, 25).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "[aria-label='操作 %s']" % TAG))
        L.js_click(drv, btn)
        time.sleep(0.6)
        L.js_click(drv, WebDriverWait(drv, 15).until(
            lambda d: d.find_element(By.XPATH, "//*[@data-slot='dropdown-menu-item' and normalize-space(.)='编辑']")))
        time.sleep(2.0)
        dlg = dialog_by_title(drv, '编辑 API')
        set_input(drv, dlg.find_element(By.ID, 'api-name'), TAG + '_仅改名')
        L.clear_fetch_log(drv)
        L.js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='保存']"))
        ev['checks']['toasts'] = L.wait_toast(drv, 25)
        time.sleep(2.0)
        puts = [e for e in L.fetch_log(drv, '/apis') if e.get('method') == 'PUT']
        if puts:
            body = json.loads(puts[-1].get('reqBody') or '{}')
            ev['checks']['put_status'] = puts[-1].get('status')
            ev['checks']['put_keys'] = sorted(body.keys())
            ev['checks']['put_has_meta'] = 'meta' in body
            ev['checks']['put_has_audio_config'] = 'audio_config' in body
            ev['checks']['put_device_type'] = body.get('device_type')
        _, after, _ = L.api_json(drv, '/apis/%s' % api_id)
        after = (after or {}).get('data') or after or {}
        ev['checks']['after'] = {'name': after.get('name'), 'meta': after.get('meta'),
                                 'audio': after.get('audio_config'),
                                 'device_type': after.get('device_type')}
        ev['checks']['meta_preserved'] = after.get('meta') == before.get('meta')
        ev['checks']['audio_preserved'] = after.get('audio_config') == before.get('audio_config')
        ev['checks']['device_type_preserved'] = after.get('device_type') == before.get('device_type')
    finally:
        try:
            if api_id:
                st, _, raw = L.api_json(drv, '/apis/%s' % api_id, 'DELETE')
                ev['checks']['delete_status'] = st
        except Exception:
            pass
        try:
            drv.quit()
        except Exception:
            pass
        out = os.path.join(ART, 'evidence_nameonly.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        print('EVIDENCE', out)


if __name__ == '__main__':
    main()
