# -*- coding: utf-8 -*-
"""INT-2386 复现：Selenium 下 int1919 chain4（报告中心行点击 → 详情）是否稳定。

Playwright 直连/点击 3/3 都正常；Selenium 连续两次停在列表页。本探针用与
int1919 完全相同的驱动与点击方式重复 N 次，量化是否驱动侧抖动。只读。

跑法：<conda python> tests/ui/probe_int2386_selenium_repro.py --base http://localhost:15173 --rounds 3
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import smoke_frontend_int1854 as B  # noqa: E402
import smoke_frontend_int1919 as S  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--rounds', type=int, default=3)
    args = ap.parse_args()

    sm = S.Smoke1919('react', args.base)
    dl = os.path.join(B.RESULT['art'], 'downloads')
    os.makedirs(dl, exist_ok=True)
    sm.download_dir = dl
    sm.drv = B.make_driver(dl)
    out = []
    d = sm.drv
    try:
        login = sm.login()
        print('login ok=%s' % login.get('ok'))
        for i in range(args.rounds):
            rec = {}
            try:
                r = sm.chain_reports()
                rec = {'round': i + 1, 'ok': r.get('ok'),
                       'url': (r.get('detail') or {}).get('url'),
                       'has_detail_api': any('/reports/%d' % (r.get('report') or {}).get('id', -1)
                                             in (a.get('url') or '')
                                             for a in (r.get('detail_apis') or [])),
                       'export': r.get('export')}
            except Exception as exc:
                rec = {'round': i + 1, 'error': '%s: %s' % (type(exc).__name__, str(exc)[:200])}
            print(json.dumps(rec, ensure_ascii=False))
            out.append(rec)
    finally:
        try:
            d.quit()
        except Exception:
            pass
    print('SUMMARY', json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
