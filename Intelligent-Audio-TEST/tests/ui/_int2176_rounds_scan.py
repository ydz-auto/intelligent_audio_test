# -*- coding: utf-8 -*-
"""INT-2176 报告用例扫描：找出含 rounds 源 / 多轮次指标的报告用例（只读）。"""
import json
import sys
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
TOKEN = open('artifacts/int2176/token.txt', encoding='utf-8').read().strip()
H = {'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}


def req(method, path, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method, headers=H)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, {'_err': e.read().decode('utf-8', 'replace')[:200]}


def scan(rid):
    st, j = req('POST', f'/reports/{rid}/cases/search', {'page': 1, 'page_size': 200})
    if st != 200:
        return []
    items = ((j.get('data') or {}).get('items')) or []
    hits = []
    for it in items:
        ar = it.get('algorithmResults') or {}
        src = None
        for k, v in (ar.items() if isinstance(ar, dict) else []):
            if isinstance(v, dict):
                if isinstance(v.get('rounds'), list) and v.get('rounds'):
                    src = f'value.rounds[{len(v["rounds"])}] key={k}'
                    break
                if isinstance(v.get('value'), dict) and isinstance(v['value'].get('rounds'), list) and v['value']['rounds']:
                    src = f'nested.rounds[{len(v["value"]["rounds"])}] key={k}'
                    break
        metric_rounds = sorted({m['metric'].split('@')[-1] for mm in it.get('metrics') or []
                                for m in mm.get('metrics') or [] if '@' in m['metric']})
        hits.append({'id': it.get('id'), 'name': it.get('name'), 'src': src,
                     'arity': type(ar).__name__, 'keys': list(ar)[:6] if isinstance(ar, dict) else None,
                     'metric_rounds': metric_rounds, 'res': [r.get('resource') for r in it.get('results') or []]})
    return {'report': rid, 'total': (j.get('data') or {}).get('total'), 'cases': hits}


def main():
    st, j = req('GET', '/reports?page=1&page_size=20')
    ids = []
    page = 1
    while True:
        st, j = req('GET', f'/reports?page={page}&page_size=20')
        d = j.get('data') or {}
        items = d.get('items') or []
        ids += [(r['id'], r.get('type'), r.get('status')) for r in items]
        if len(ids) >= (d.get('total') or 0) or not items:
            break
        page += 1
    print('reports', len(ids))
    out = []
    for rid, typ, status in ids:
        try:
            res = scan(rid)
        except Exception as e:
            print('ERR', rid, e)
            continue
        interesting = [c for c in res['cases'] if c['src'] or len(c['metric_rounds']) > 2]
        if interesting:
            out.append({'report': rid, 'type': typ, 'status': status, 'total': res['total'],
                        'cases': interesting[:6]})
            print(json.dumps(out[-1], ensure_ascii=False)[:900])
    with open('artifacts/int2176/rounds_scan.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
