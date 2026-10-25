# -*- coding: utf-8 -*-
"""INT-1538 R6 复测夹具收尾：软删用例 purge + 同名分组核查（只清本 run 的 _R6 前缀）。"""
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
    d.get(L.BASE + '/testcases')
    time.sleep(4)
    for kw in ('接线测试_INT1538_R6',):
        st, p, _ = L.api_json(d, '/testcases?page=1&per_page=200&only_deleted=1&keyword=' + kw)
        items = ((p or {}).get('data') or {}).get('items') or []
        OUT.setdefault('soft_deleted_before', []).extend([(x['id'], x['name']) for x in items])
        for x in items:
            r = L.api_json(d, '/testcases/' + x['id'] + '/purge', 'DELETE')
            OUT.setdefault('purge', []).append((x['id'], r[0], r[2][:120]))
        st, p, _ = L.api_json(d, '/testcases?page=1&per_page=200&only_deleted=1&keyword=' + kw)
        OUT.setdefault('soft_deleted_after', []).extend(
            [(x['id'], x['name']) for x in (((p or {}).get('data') or {}).get('items') or [])])
        st, p, _ = L.api_json(d, '/testcases?page=1&per_page=200&keyword=' + kw)
        OUT.setdefault('alive_after', []).extend(
            [(x['id'], x['name']) for x in (((p or {}).get('data') or {}).get('items') or [])])
    # 分组：DELETE 是否硬删（only_deleted 应查不到）
    st, p, _ = L.api_json(d, '/groups?page=1&per_page=200')
    OUT['groups_alive_r6'] = [x.get('name') for x in (((p or {}).get('data') or {}).get('items') or [])
                              if 'R6' in (x.get('name') or '')]
    st, p, _ = L.api_json(d, '/groups?page=1&per_page=200&only_deleted=1')
    OUT['groups_deleted_r6'] = [x.get('name') for x in (((p or {}).get('data') or {}).get('items') or [])
                                if 'R6' in (x.get('name') or '')]
    # 全库遗留（历史轮次）计数，仅统计不处理
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=1&only_deleted=1&keyword=接线测试_')
    OUT['all_soft_deleted_total'] = ((p or {}).get('data') or {}).get('total')
finally:
    L.save_evidence('cleanup_r6_evidence', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
