# -*- coding: utf-8 -*-
"""INT-1686 复测夹具收尾：软删临时算法定义并确认 options / form-schema 已不可见。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1483_helpers as H  # noqa: E402

TYPE = 'wire_test_int1686d'
out = {}
d = H.driver()
try:
    H.login(d)
    st, pay, raw = H.api_json(d, '/algorithm/definitions/' + TYPE, 'DELETE')
    out['delete'] = {'status': st, 'raw': raw[:200]}
    st, pay, raw = H.api_json(d, '/algorithm/reload', 'POST', {})
    out['reload'] = {'status': st, 'raw': raw[:120]}
    st, pay, raw = H.api_json(d, '/algorithm/options')
    data = ((pay or {}).get('data') or {}) if isinstance(pay, dict) else {}
    out['options_has_type'] = any(
        a.get('value') == TYPE for a in (data.get('algorithms') or []))
    st, pay, raw = H.api_json(d, '/algorithm/form-schema/' + TYPE)
    out['form_schema'] = {'status': st, 'raw': (raw or '')[:160]}
finally:
    d.quit()
print(json.dumps(out, ensure_ascii=False, indent=2))
