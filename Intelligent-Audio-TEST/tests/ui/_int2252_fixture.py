# -*- coding: utf-8 -*-
"""INT-2252 验收夹具：建一个「无算法关联」的维度（差分用），用完按 id 清。

用法：
  python _int2252_fixture.py create     # 建并打印 id
  python _int2252_fixture.py list       # 列出本卡前缀的行
  python _int2252_fixture.py cleanup    # 按 id 硬删（关系 / 参数 / 维度行）
"""
import json
import sys

import _int2252_probe as P

NAME = '接线测试_2252_无关联维度'
NAME2 = '接线测试_2252_有关联维度'


def _target(tok):
    st, d = P.get_json(tok, '/evaluation/dimensions?per_page=1000')
    d = P.unwrap(d) or {}
    rows = [i for i in (d.get('items') or [])
            if (i.get('name') or '').startswith('接线测试_2252_')]
    return rows


def create(tok, name, assoc=None):
    body = {
        'name': name,
        'description': 'INT-2252 验收差分夹具（验收后删除）',
        'keywords': 'int2252audit',
        'dimension_type': 'main',
        'type': 'manual',
        'result_type': 0,
        'result_min': 0,
        'result_max': 100,
        'decimal_places': 2,
        'weight': 1,
        'estimated_exec_time': 30,
        'status': True,
        'category_id': 4,
        'statistic_method': 'average',
        'agg_denominator': 'case',
        'visibility': 'shared',
    }
    if assoc:
        body['associated_algorithms'] = assoc
    st, resp = P.http('POST', '/evaluation/dimensions', body=body, token=tok)
    print('CREATE', st, str(resp)[:200])


def main():
    action = sys.argv[1]
    tok = P.login()
    if action == 'create':
        if _target(tok):
            print('EXISTS', json.dumps(_target(tok), ensure_ascii=True))
            return
        create(tok, NAME)
        print('ROWS', json.dumps(_target(tok), ensure_ascii=True))
    elif action == 'create2':
        if any(r.get('name') == NAME2 for r in _target(tok)):
            print('EXISTS2')
        else:
            create(tok, NAME2, [{'algorithm_type': 'voice_llm', 'is_default': True, 'weight': 1}])
        print('ROWS', json.dumps([(r.get('id'), r.get('name'), r.get('associated_algorithms')) for r in _target(tok)], ensure_ascii=True))
    elif action == 'list':
        print('ROWS', json.dumps([(r.get('id'), r.get('name'), r.get('associated_algorithms')) for r in _target(tok)], ensure_ascii=True))
    elif action == 'cleanup':
        rows = [r for r in _target(tok)]
        print('CLEANUP_TARGETS', [(r.get('id'), r.get('name')) for r in rows])
        for r in rows:
            st, resp = P.http('DELETE', '/evaluation/dimensions/%s' % r.get('id'), token=tok)
            print('DELETE', r.get('id'), st, str(resp)[:120])
        print('AFTER', json.dumps(_target(tok), ensure_ascii=True))


if __name__ == '__main__':
    main()
