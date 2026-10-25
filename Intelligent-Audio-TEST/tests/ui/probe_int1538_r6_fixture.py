# -*- coding: utf-8 -*-
"""INT-1538 P1-5 复测前置探测：找一个 2 轮带音频的真实用例 config，并核对 preview 接口 host。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L

OUT = {}
d = L.driver()
try:
    L.login(d)
    st, payload, raw = L.api_json(d, '/testcases?page=1&per_page=20')
    OUT['list_status'] = st
    items = ((payload or {}).get('data') or {}).get('items') or []
    OUT['list_count'] = len(items)
    OUT['first_item_keys'] = sorted(items[0].keys()) if items else []

    found = []
    for it in items[:20]:
        cid = it.get('id')
        st2, p2, raw2 = L.api_json(d, '/testcases/' + str(cid))
        cfg = ((p2 or {}).get('data') or {}).get('config')
        if not isinstance(cfg, dict):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = None
        rounds = (cfg or {}).get('rounds') or []
        naud = sum(len(r.get('audios') or []) for r in rounds)
        found.append({'id': cid, 'name': it.get('name'), 'status': st2,
                      'rounds': len(rounds), 'audios': naud,
                      'round_keys': sorted(rounds[0].keys()) if rounds else [],
                      'audio_keys': sorted((rounds[0].get('audios') or [{}])[0].keys()) if rounds and rounds[0].get('audios') else []})
        if len(rounds) == 2 and naud >= 1:
            OUT['picked'] = {'id': cid, 'name': it.get('name')}
            OUT['picked_cfg'] = cfg
            break
    OUT['scanned'] = found

    # 直接探 preview：浏览器播放模式
    for body in ({'audio_id': 2358, 'playback_mode': 'frontend'},
                 {'audio_id': 2358, 'playback_mode': 'frontend', 'audio_ids': [2358]}):
        st3, p3, raw3 = L.api_json(d, '/audios/2358/preview', 'POST', body)
        OUT['preview_' + str(sorted(body.keys()))] = {'status': st3, 'body': raw3[:1200]}
    # 试听配置用的可能不是 /audios/{id}/preview，先看 audios 列表里 2358 是否在
    st4, p4, raw4 = L.api_json(d, '/audios?page=1&per_page=5&keyword=url_src_A_6')
    OUT['audio_search'] = {'status': st4, 'body': raw4[:600]}
finally:
    json.dump(OUT, open('_probe_r6.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(OUT, ensure_ascii=False)[:3000])
    try:
        d.quit()
    except Exception:
        pass
