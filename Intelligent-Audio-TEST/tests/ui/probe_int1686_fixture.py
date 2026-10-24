# -*- coding: utf-8 -*-
"""INT-1686 复测夹具探针：建带 case_params 的临时算法定义 → 校验 options / form-schema 双份字段。"""
import json
import sys

sys.path.insert(0, __file__.rsplit('\\', 1)[0])
import int1483_helpers as H  # noqa: E402

TYPE = 'wire_test_int1686d'
NAME = '接线测试_验收去重算法1686d'


def def_body(status='online'):
    return {
        'type': TYPE, 'name': NAME, 'group_id': None, 'display_order': 1,
        'status': status, 'description': 'INT-1686 复测夹具',
        'device_params': [], 'api_params': [],
        'case_params': [
            {'param_code': 'wire1686d_threshold', 'param_name': '接线测试阈值',
             'label': '接线测试阈值', 'param_type': 'number', 'default_value': 10,
             'ui_order': 1, 'scope': 'case', 'ui_group': 'basic', 'required': False},
            {'param_code': 'wire1686d_flag', 'param_name': '接线测试开关',
             'label': '接线测试开关', 'param_type': 'boolean', 'default_value': False,
             'ui_order': 2, 'scope': 'case', 'ui_group': 'basic', 'required': False},
        ],
        'reference_params': [],
        'mappings': {'device': [], 'api': [], 'evaluation': []},
        'associated_dimensions': [],
    }


out = {}
d = H.driver()
try:
    H.login(d)
    st, pay, raw = H.api_json(d, '/algorithm/definitions', 'POST', def_body())
    out['create'] = {'status': st, 'type': ((pay or {}).get('data') or {}).get('type'),
                     'raw': raw[:200]}
    st, pay, raw = H.api_json(d, '/algorithm/options')
    items = ((pay or {}).get('data') or {}).get('items') if isinstance((pay or {}).get('data'), dict) else (pay or {}).get('data')
    out['options'] = {'status': st, 'hit': [o for o in (items or []) if isinstance(o, dict) and o.get('value') == TYPE]}
    st, pay, raw = H.api_json(d, '/algorithm/form-schema/' + TYPE)
    data = (pay or {}).get('data') if isinstance(pay, dict) else None
    out['form_schema'] = {
        'status': st,
        'fields': len((data or {}).get('fields') or []),
        'groups': [{'name': g.get('name'), 'fields': len(g.get('fields') or [])}
                   for g in ((data or {}).get('groups') or [])],
        'raw': raw[:300] if st != 200 else None,
    }
finally:
    d.quit()

print(json.dumps(out, ensure_ascii=False, indent=2))
