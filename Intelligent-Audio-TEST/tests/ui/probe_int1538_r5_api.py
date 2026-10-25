# -*- coding: utf-8 -*-
"""INT-1538 返工探针：分组软删/同名复用契约 + /health 原文 + 用例与分组计数基线。

只读为主；临时分组带 接线测试_ 前缀，脚本末尾自清理。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By

TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1538_R5组_' + TAG
OUT = {'tag': TAG, 'group_name': NAME}


def health_raw(d):
    return d.execute_async_script("""
        const done = arguments[arguments.length-1];
        fetch('/health').then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """)


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(5)

    OUT['health'] = health_raw(d)
    st, payload, raw = L.api_json(d, '/groups?page=1&per_page=200')
    OUT['groups_list'] = {'status': st, 'total': ((payload or {}).get('data') or {}).get('total'),
                          'items': len((((payload or {}).get('data') or {}).get('items') or []))}
    st, payload, raw = L.api_json(d, '/testcases?page=1&per_page=1')
    OUT['cases_total'] = ((payload or {}).get('data') or {}).get('total')
    st, payload, raw = L.api_json(d, '/audios?audio_type=noise&page=1&per_page=1')
    OUT['noise_total'] = ((payload or {}).get('data') or {}).get('total')

    # 1) 建组
    st, payload, raw = L.api_json(d, '/groups', 'POST',
                                  {'name': NAME, 'description': 'INT-1538 返工临时组', 'algorithm_type': ''})
    OUT['create'] = {'status': st, 'body': raw[:300]}
    gid = str(((payload or {}).get('data') or {}).get('id') or '')
    OUT['group_id'] = gid

    # 2) 软删
    if gid:
        st, payload, raw = L.api_json(d, '/groups/' + gid, 'DELETE')
        OUT['delete'] = {'status': st, 'body': raw[:300]}
        time.sleep(1)
        st, payload, raw = L.api_json(d, '/groups?page=1&per_page=200&keyword=' + NAME)
        items = ((payload or {}).get('data') or {}).get('items') or []
        OUT['after_delete_listed'] = [x.get('name') for x in items]
        # 软删标记：查 only_deleted / include_deleted 两种口径
        for q in ('&only_deleted=1', '&include_deleted=1', '&is_deleted=1'):
            st2, p2, r2 = L.api_json(d, '/groups?page=1&per_page=200&keyword=' + NAME + q)
            it2 = ((p2 or {}).get('data') or {}).get('items') or []
            OUT['after_delete_listed' + q] = {'status': st2, 'names': [x.get('name') for x in it2],
                                              'raw': None if it2 else r2[:160]}
        # 3) 同名再建
        st, payload, raw = L.api_json(d, '/groups', 'POST',
                                      {'name': NAME, 'description': '', 'algorithm_type': ''})
        OUT['recreate_same_name'] = {'status': st, 'body': raw[:400]}
        gid2 = str(((payload or {}).get('data') or {}).get('id') or '')
        OUT['group_id2'] = gid2
        if gid2:
            st, payload, raw = L.api_json(d, '/groups/' + gid2, 'DELETE')
            OUT['cleanup_delete2'] = {'status': st, 'body': raw[:200]}
finally:
    L.save_evidence('probe_r5_api', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
