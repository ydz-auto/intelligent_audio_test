# -*- coding: utf-8 -*-
"""INT-1483 补走前置探测：:15000 现役后端是否已含 INT-1514「发布清草稿」修复。

不做界面操作，只按前端真实接口序列走一遍：
  POST /algorithm/definitions（建）
  PUT  /algorithm/definitions/draft（存草稿，名称 A）
  PUT  /algorithm/definitions/{type}（发布，名称 B）
  GET  /algorithm/definitions/draft/{type}（回读草稿：空 = 已修复；仍是 A = 镜像滞后）
清理：DELETE 定义 + DELETE 草稿，库里不留本探针记录。
"""
import json
import time

import int1483_helpers as H

TAG = 'P' + H.RUN_TAG
TYPE = f'itest1483_p_{TAG.lower()}'
NAME = f'接线测试_INT1483_探针_{TAG}'
OUT = {'type': TYPE}


def def_body(name, status='offline'):
    return {
        'type': TYPE, 'name': name, 'group_id': None, 'display_order': 1,
        'status': status, 'description': 'INT-1483 后端修复部署探测',
        'device_params': [], 'api_params': [], 'case_params': [], 'reference_params': [],
        'mappings': {'device': [], 'api': [], 'evaluation': []},
        'associated_dimensions': [],
    }


d = H.driver()
try:
    H.login(d)
    st, pay, raw = H.api_json(d, '/algorithm/definitions', 'POST', def_body(NAME))
    OUT['create'] = {'status': st, 'type': (pay or {}).get('data', {}).get('type')}

    st, pay, raw = H.api_json(d, '/algorithm/definitions/draft', 'PUT', {
        'algorithm_type': TYPE, 'definition': def_body(NAME + '_草稿态')})
    OUT['save_draft'] = {'status': st, 'name': ((pay or {}).get('data') or {}).get('name')}

    st, pay, raw = H.api_json(d, f'/algorithm/definitions/{TYPE}', 'PUT', def_body(NAME + '_发布态', 'online'))
    OUT['publish'] = {'status': st, 'name': ((pay or {}).get('data') or {}).get('name')}

    st_d, pay_d, raw_d = H.api_json(d, f'/algorithm/definitions/draft/{TYPE}')
    draft = (pay_d or {}).get('data')
    if isinstance(draft, dict) and 'definition' in draft:
        draft = draft.get('definition')
    OUT['draft_after_publish'] = {
        'status': st_d,
        'empty': not bool(draft),
        'name': (draft or {}).get('name') if isinstance(draft, dict) else None,
        'raw_head': (raw_d or '')[:300],
    }

    st_g, pay_g, _ = H.api_json(d, f'/algorithm/definitions/{TYPE}')
    OUT['definition_after_publish'] = {'status': st_g,
                                       'name': ((pay_g or {}).get('data') or {}).get('name')}
finally:
    try:
        H.api_json(d, f'/algorithm/definitions/draft/{TYPE}', 'DELETE')
        H.api_json(d, f'/algorithm/definitions/{TYPE}', 'DELETE')
        st, _, _ = H.api_json(d, f'/algorithm/definitions/{TYPE}')
        OUT['cleanup'] = {'definition_get_after_delete': st}
    except Exception as e:
        OUT['cleanup_error'] = str(e)
    try:
        d.quit()
    except Exception:
        pass

print(json.dumps(OUT, ensure_ascii=False, indent=2))
