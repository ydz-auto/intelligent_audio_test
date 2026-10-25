# -*- coding: utf-8 -*-
"""INT-1778 R1 复测夹具清理（param / mapping 按 param_code 删除并复核）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15267')
PARAM_CODE = 'int1778rt_out'


def main():
    d = L.driver()
    try:
        L.login(d)
        st, payload, _ = L.api_json(d, '/algorithm/mappings?algorithm_type=voice_llm&source_type=api')
        for it in ((payload or {}).get('data') or {}).get('items') or []:
            if it.get('source_param') == PARAM_CODE:
                print('DEL mapping', it['id'], L.api_json(d, '/algorithm/mappings/%s' % it['id'], 'DELETE')[0])
        st, payload, _ = L.api_json(d, '/algorithm/params?algorithm_type=voice_llm&param_type=api')
        for it in ((payload or {}).get('data') or {}).get('items') or []:
            if it.get('param_code') == PARAM_CODE:
                print('DEL param', it['id'], L.api_json(d, '/algorithm/params/%s' % it['id'], 'DELETE')[0])

        st, payload, _ = L.api_json(d, '/algorithm/mappings?algorithm_type=voice_llm&source_type=api')
        left_m = [it for it in ((payload or {}).get('data') or {}).get('items') or []
                  if it.get('source_param') == PARAM_CODE]
        st, payload, _ = L.api_json(d, '/algorithm/params?algorithm_type=voice_llm&param_type=api')
        left_p = [it for it in ((payload or {}).get('data') or {}).get('items') or []
                  if it.get('param_code') == PARAM_CODE]
        print('LEFTOVER mappings', left_m)
        print('LEFTOVER params', left_p)
        return 0 if not left_m and not left_p else 1
    finally:
        d.quit()


if __name__ == '__main__':
    sys.exit(main())
