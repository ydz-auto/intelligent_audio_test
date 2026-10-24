# -*- coding: utf-8 -*-
"""清理 INT-1477R 夹具（用例软删+purge、分组 cascade 删除）并回读为 0。"""
import json
import os
import sys
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_int1477_int1731 as base  # noqa: E402

TAG = os.environ.get('FIXTAG', '10241546')
base.GROUP = '接线测试_INT1477R组' + TAG
base.NAMES = ['接线测试_INT1477R_' + TAG + '_A', '接线测试_INT1477R_' + TAG + '_B']
PREFIX = '接线测试_INT1477R'


def main():
    d = base.driver()
    out = {}
    try:
        d.get(base.BASE + '/testcases/by-group')
        base.wait_page(d)
        out['cleanup'] = base.cleanup(d)
        for kw in (PREFIX, PREFIX + '_10241546'):
            for q, key in (('', 'active'), ('&only_deleted=true', 'deleted')):
                r = base.api(d, 'GET', '/api/v1/testcases?page=1&per_page=100&keyword=' +
                             urllib.parse.quote(kw) + q)
                data = (r.get('json') or {}).get('data') or {}
                items = data.get('items') if isinstance(data, dict) else data
                hit = [{'id': x.get('id'), 'name': x.get('name'),
                        'is_deleted': x.get('is_deleted')} for x in (items or [])
                       if (x.get('name') or '').startswith(PREFIX)]
                out['readback:' + kw + ':' + key] = hit
        g = base.api(d, 'GET', '/api/v1/groups?page=1&per_page=200')
        gd = (g.get('json') or {}).get('data') or {}
        gi = gd.get('items') if isinstance(gd, dict) else gd
        out['readback:groups'] = [{'id': x.get('id'), 'name': x.get('name')}
                                  for x in (gi or []) if PREFIX in (x.get('name') or '')]
        out['readback:groups_deleted'] = None
        gd2 = base.api(d, 'GET', '/api/v1/groups?page=1&per_page=200&only_deleted=true')
        g2 = (gd2.get('json') or {}).get('data') or {}
        g2i = g2.get('items') if isinstance(g2, dict) else g2
        out['readback:groups_deleted'] = [{'id': x.get('id'), 'name': x.get('name')}
                                          for x in (g2i or []) if PREFIX in (x.get('name') or '')]
    finally:
        json.dump(out, open(os.path.join(base.ART, 'cleanup_evidence.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
