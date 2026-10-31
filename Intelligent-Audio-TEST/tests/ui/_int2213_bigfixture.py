# -*- coding: utf-8 -*-
"""INT-2213 大表夹具：在真实库上自建 1192 条评估映射 / 327 个维度分组的算法，
供窗口化渲染验收（DOM 规模与 INT-2203 实测口径一致）。

自建前缀「接线测试_」，run 结束 DELETE。
用法：
  python _int2213_bigfixture.py create
  python _int2213_bigfixture.py delete
token 复用 _int2213_fixture.py 落盘的 artifacts/int2213/token.txt。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2213')
API = 'http://127.0.0.1:15000/api/v1'
BIG_TYPE = 'int2213_perf_1192v2'
BIG_NAME = '接线测试_2213_性能1192'
TARGET_ROWS = 1192
TARGET_GROUPS = 327


def token():
    with open(os.path.join(ART, 'token.txt'), encoding='utf-8') as f:
        return f.read().strip()


def api(method, path, body=None, tok='', tries=3):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    last = None
    for _ in range(tries):
        r = urllib.request.Request(
            API + path,
            data=data,
            method=method,
            headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(r, timeout=600) as resp:
                raw = resp.read().decode('utf-8')
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', 'replace')
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw[:400]
        except Exception as e:  # 连接重置等瞬断
            last = e
            time.sleep(2)
    raise last


def dev_dto(p):
    return {
        'param_code': p['param_code'], 'param_name': p.get('param_name'),
        'label': p.get('param_name'), 'param_type': p.get('param_type') or 'text',
        'direction': p.get('direction') or 'input', 'required': bool(p.get('required')),
        'default_value': p.get('default_value'), 'help_text': p.get('help_text'),
        'ui_order': p.get('ui_order') or 0, 'hidden': bool(p.get('hidden')),
    }


def jval(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return json.dumps(v, ensure_ascii=False)


def case_dto(p):
    return {
        'param_code': p['param_code'], 'param_name': p.get('param_name'),
        'label': p.get('param_name'), 'param_type': p.get('param_type') or 'text',
        'required': bool(p.get('required')), 'default_value': jval(p.get('default_value')),
        'help_text': p.get('help_text'), 'ui_order': p.get('ui_order') or 0,
        'hidden': bool(p.get('hidden')), 'scope': p.get('scope'),
        'min_value': p.get('min_value'), 'max_value': p.get('max_value'),
        'step': p.get('step'), 'unit': p.get('unit'),
        'annotation_code': p.get('annotation_code'), 'field_path': p.get('field_path'),
    }


def ref_dto(p):
    return {
        'code': p['code'], 'name': p.get('name') or '', 'type': p.get('type') or 'text',
        'annotation_code': p.get('annotation_code'), 'annotation_format': p.get('annotation_format'),
        'field_path': p.get('field_path'), 'merge_mode': p.get('merge_mode'),
        'help_text': p.get('help_text'),
    }


def build_mappings(real_dim_ids):
    """1192 行 / 327 组：维度池 = 真实维度 + 合成 id（UI 显示「维度(id)」），
    唯一键 source+source_param+dimension_id 逐行不重复。"""
    dims = list(real_dim_ids[:TARGET_GROUPS])
    extra = 0
    while len(dims) < TARGET_GROUPS:
        extra += 1
        dims.append(9000 + extra)
    rows = []
    for i in range(TARGET_ROWS):
        dim = dims[i % TARGET_GROUPS]
        rows.append({
            'source': 'case' if i % 3 else 'case_config',
            'source_param': 'perf_src_%04d' % (i % 127),
            'source_direction': 'output',
            'target_param': 'perf_tgt_%04d' % (i % 97),
            'transform_type': 'none',
            'dimension_id': dim,
        })
    return rows


def delete(tok):
    st, res = api('DELETE', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    st2, _ = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    return {'delete': st, 'after_get': st2}


def create(tok):
    delete(tok)
    _, src = api('GET', '/algorithm/definitions/voice_llm', tok=tok)
    src = src['data']
    _, dims = api('GET', '/evaluation/dimensions?per_page=1000', tok=tok)
    dim_data = dims.get('data') or dims
    dim_items = dim_data.get('items') if isinstance(dim_data, dict) else dim_data
    real_ids = [int(d['id']) for d in dim_items]
    mappings = build_mappings(real_ids)
    st, res = api('POST', '/algorithm/definitions', {
        'type': BIG_TYPE, 'name': BIG_NAME, 'group_id': src.get('group_id'), 'display_order': 0,
        'status': 'online', 'description': 'INT-2213 自建性能夹具（run 内删除）',
        'device_params': [dev_dto(p) for p in src['device_params']],
        'case_params': [case_dto(p) for p in src['case_params']],
        'reference_params': [ref_dto(p) for p in src['reference_params']],
        'mappings': {'device': [], 'evaluation': mappings},
        'associated_dimensions': [],
    }, tok=tok)
    out = {'post': st, 'msg': str((res or {}).get('message'))[:200] if isinstance(res, dict) else str(res)[:200]}
    st, d = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    if st == 200:
        em = d['data']['mappings']['evaluation']
        out['readback'] = {
            'rows': len(em),
            'groups': len({str(m.get('dimension_id')) for m in em}),
            'real_dims': len(real_ids),
        }
    else:
        out['readback'] = {'status': st, 'body': str(d)[:300]}
    return out


def _key(m):
    # 与后端唯一约束 uq_param_mapping_algo_level 对齐：source+source_param+dimension_id
    return (m.get('source'), m.get('source_param'), m.get('dimension_id'))


def topup(tok):
    """create 走 gRPC 会 DEADLINE_EXCEEDED 只写一部分；PUT 只提交缺失评估映射补齐。"""
    _, src = api('GET', '/algorithm/definitions/voice_llm', tok=tok)
    src = src['data']
    _, dims = api('GET', '/evaluation/dimensions?per_page=1000', tok=tok)
    dim_data = dims.get('data') or dims
    dim_items = dim_data.get('items') if isinstance(dim_data, dict) else dim_data
    real_ids = [int(d['id']) for d in dim_items]
    want = build_mappings(real_ids)

    _, cur = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    cur = cur['data']
    have = {_key(m) for m in cur['mappings']['evaluation']}
    missing = [m for m in want if _key(m) not in have]
    out = {'have': len(have), 'missing': len(missing)}
    if missing:
        st, r = api('PUT', '/algorithm/definitions/' + BIG_TYPE, {
            'type': BIG_TYPE, 'name': cur['name'], 'group_id': cur.get('group_id'),
            'display_order': cur.get('display_order') or 0, 'status': cur.get('status') or 'online',
            'description': cur.get('description') or '',
            'device_params': [dev_dto(p) for p in cur['device_params']],
            'case_params': [case_dto(p) for p in cur['case_params']],
            'reference_params': [ref_dto(p) for p in cur['reference_params']],
            'mappings': {'device': [], 'evaluation': missing},
            'associated_dimensions': [],
        }, tok=tok)
        out['put'] = {'status': st, 'msg': str((r or {}).get('message'))[:160] if isinstance(r, dict) else str(r)[:160]}
    _, after = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    em = after['data']['mappings']['evaluation']
    out['now'] = {'rows': len(em), 'groups': len({str(m.get('dimension_id')) for m in em})}
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'create'
    tok = token()
    if cmd == 'delete':
        out = delete(tok)
    elif cmd == 'create':
        out = create(tok)
    elif cmd == 'topup':
        out = topup(tok)
    else:
        raise SystemExit('unknown cmd')
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
