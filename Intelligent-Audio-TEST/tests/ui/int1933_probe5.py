# -*- coding: utf-8 -*-
"""INT-1933 补证：设备管理 API 页签「编辑」抽屉保存后，meta / audio_config 是否被静默清空。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By  # noqa: E402

import int1643_lib as L  # noqa: E402

L.BASE = 'http://127.0.0.1:15173'
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1933')
os.makedirs(L.ART, exist_ok=True)
OUT = {}
NAME = '接线测试_INT1933_DEV_' + time.strftime('%H%M%S')


def vis_dialog(drv):
    return drv.execute_script("""
        const vis = e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e);
          return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden'; };
        const ds = Array.from(document.querySelectorAll("[role='dialog'],[role='alertdialog']")).filter(vis);
        return ds.length ? true : false;
    """)


def main():
    d = L.driver()
    tmp_id = None
    try:
        L.login(d)
        st, payload, raw = L.api_json(d, '/apis', 'POST', {
            'name': NAME, 'algorithm_type': 'voice_llm', 'default_max_process': 5,
            'description': 'dev entry probe', 'device_type': 'http_api',
            'endpoints': [{'endpoint': 'https://api.example.com/v1/asr', 'name': 'dev-ep',
                           'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60,
                           'status': 'online', 'priority': 1, 'description': None}],
            'meta': {
                'apiKey': 'dev-keep', 'version': 'v1', 'protocol': 'http',
                'environment': 'development', 'appendix_unknown': {'keep': True},
                'method': 'PUT', 'headers': {'X-Dev': 'yes'},
                'body_template': {'text': '{{text}}'}, 'result_parser': {'asr_text_path': 'data.text'},
                'asr_mapping': '$.data.text', 'append_mode': False,
            },
            'audio_config': {'sample_rate': 16000, 'bit_depth': 's16',
                             'channels': 1, 'container': 'pcm'},
        })
        tmp_id = ((payload or {}).get('data') or {}).get('id')
        before = (L.api_json(d, '/apis/%s' % tmp_id)[1] or {}).get('data') or {}
        OUT['created_id'] = tmp_id
        OUT['before_meta'] = before.get('meta')
        OUT['before_audio'] = before.get('audio_config')

        d.get(L.BASE + '/devices')
        time.sleep(5)
        for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if t.is_displayed() and (t.text or '').strip() == '测试 API':
                L.js_click(d, t)
                break
        time.sleep(3.0)
        trig = None
        for b in d.find_elements(By.CSS_SELECTOR, "[aria-label='操作 %s']" % NAME):
            if b.is_displayed():
                trig = b
                break
        OUT['row_found'] = trig is not None
        if trig is not None:
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", trig)
            L.js_click(d, trig)
            time.sleep(0.9)
            for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                if i.is_displayed() and (i.text or '').strip() == '编辑':
                    L.js_click(d, i)
                    break
            time.sleep(2.2)
        OUT['drawer_open'] = vis_dialog(d)
        OUT['drawer_head'] = d.execute_script("""
            const vis = e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e);
              return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden'; };
            const ds = Array.from(document.querySelectorAll("[role='dialog'],[role='alertdialog']")).filter(vis);
            const x = ds[ds.length-1]; return x ? (x.innerText||'').slice(0,900) : '';
        """)
        L.shot(d, 'P5_device_drawer_meta')
        # 原样保存（不改进任何字段）
        saved = False
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and (b.text or '').strip() == '保存':
                L.js_click(d, b)
                saved = True
                break
        OUT['save_clicked'] = saved
        time.sleep(3.0)
        OUT['drawer_closed_after_save'] = not vis_dialog(d)
        after = (L.api_json(d, '/apis/%s' % tmp_id)[1] or {}).get('data') or {}
        OUT['after_meta'] = after.get('meta')
        OUT['after_audio'] = after.get('audio_config')

        bm, am = before.get('meta') or {}, after.get('meta') or {}
        OUT['meta_keys_lost'] = sorted(set(bm.keys()) - set(am.keys()))
        OUT['meta_keys_changed'] = {k: (bm.get(k), am.get(k)) for k in bm if bm.get(k) != am.get(k)}
        OUT['audio_changed'] = before.get('audio_config') != after.get('audio_config')
        L.save_evidence('probe5', OUT)
        print(json.dumps(OUT, ensure_ascii=False, indent=1))
    finally:
        try:
            if tmp_id:
                st, _, raw = L.api_json(d, '/apis/%s' % tmp_id, 'DELETE')
                print('CLEANUP', st, raw[:80])
        except Exception as e:
            print('cleanup err', e)
        d.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
