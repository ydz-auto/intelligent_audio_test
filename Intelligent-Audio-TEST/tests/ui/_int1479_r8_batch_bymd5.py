# -*- coding: utf-8 -*-
"""INT-1479 R8 · B2：批量更新标注的 by-md5 请求取证 + 列表筛选独立性。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402
import _int1479_r8_batch_annotation as B  # noqa: E402

OUT = L.OUT


def net_since(c, i):
    out = []
    for e in c.events[i:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                out.append({'kind': 'req', 'm': r['method'], 'u': r['url'].split('?')[0],
                            'body': (r.get('postData') or '')[:600]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                out.append({'kind': 'resp', 'status': r['status'], 'u': r['url'].split('?')[0]})
    return out


def main():
    c = L.connect()
    print('READY', B.open_page(c, 'light'), flush=True)
    print('SEARCH INPUTS', c.eval(
        "Array.from(document.querySelectorAll('input')).map(i=>i.getAttribute('aria-label')||i.placeholder||i.type)"),
        flush=True)
    print('SEARCH', B.search(c, '接线测试_INT1613'), flush=True)
    time.sleep(5)
    names = c.eval("Array.from(document.querySelectorAll('tbody tr')).map(r=>r.innerText.split('\\n')[0]).slice(0,5)")
    print('ROWS AFTER FILTER', B.rows(c), json.dumps(names, ensure_ascii=False), flush=True)
    print('OTHER SEARCH?', json.dumps(c.eval(
        "Array.from(document.querySelectorAll('input')).map(i=>({a:i.getAttribute('aria-label'),p:i.placeholder,t:i.type,v:i.value}))"),
        ensure_ascii=False), flush=True)

    t0 = len(c.events)
    print('OPEN', B.open_batch(c)); time.sleep(2.5)
    print('FILES', B.set_files(c, [B.COPY, B.TXT]), flush=True)
    time.sleep(10)
    c.pump()
    evs = net_since(c, t0)
    md5req = [e for e in evs if 'by-md5' in e['u']]
    print('BY-MD5 REQ', json.dumps([e for e in md5req if e['kind'] == 'req'], ensure_ascii=False), flush=True)
    print('BY-MD5 RESP', json.dumps([e for e in md5req if e['kind'] == 'resp'], ensure_ascii=False), flush=True)
    print('DIALOG', (c.eval(B.dlg(c)) or '').replace('\n', ' | ')[:600], flush=True)
    out = {'by_md5_events': md5req, 'rows_after_filter': B.rows(c),
           'row_names': names,
           'inputs': c.eval("Array.from(document.querySelectorAll('input')).map(i=>({a:i.getAttribute('aria-label'),p:i.placeholder,t:i.type}))"),
           'dialog': (c.eval(B.dlg(c)) or '')[:800]}
    with open(os.path.join(OUT, 'r8_batch_by_md5.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('CLOSE', B.close_dialog(c), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
