# -*- coding: utf-8 -*-
"""INT-2418 审计补图：页面上两张控制卡（报告保存 / 选择要对比的设备和API）仍可操作。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui import probe_int2418_export_rework as base  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2418_audit_p3')


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--report', type=int, default=395)
    args = ap.parse_args()
    os.makedirs(ART, exist_ok=True)
    sm.env_check('audit_p3_shots_start')
    smoke = sm.Smoke('react', args.base.rstrip('/'))
    sm.RESULT['art'] = ART
    d = sm.make_driver(os.path.join(ART, 'downloads_shots'))
    try:
        smoke.drv = d
        base.login_harness(smoke)
        d.get('%s/report/%d' % (args.base.rstrip('/'), args.report))
        time.sleep(9)
        sm.wait_quiet(d, 40)
        d.execute_script("""
          var ps = Array.from(document.querySelectorAll('.report-view-container p'));
          var t = ps.filter(function(p){return (p.textContent||'').trim()==='选择要对比的设备和API';})[0];
          if (t) t.scrollIntoView({block:'center'});
        """)
        time.sleep(1.5)
        print(sm.shot(d, 'audit_p3_page_selector_card'))
        sm.env_check('audit_p3_shots_end')
    finally:
        try:
            d.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
