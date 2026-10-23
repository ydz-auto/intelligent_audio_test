# -*- coding: utf-8 -*-
"""INT-1619 对照取证：15173（wiring/react 旧镜像，未含本卡修复）直链态触发器文案。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1619_ranking_select as base  # noqa: E402

base.BASE = 'http://127.0.0.1:15173'
d = base.make_driver()
try:
    d.get(base.BASE + '/rankings?metricCode=ENV_UNDERSTAND_SCORE&source=platform_test')
    base.wait_filters(d)
    time.sleep(1.5)
    m = base.text_of(d, base.trigger(d, '指标'))
    s = base.text_of(d, base.trigger(d, '数据来源'))
    base.shot(d, '00_before_15173_directlink_light')
    print('BEFORE metric_ascii=%s' % m.encode('ascii', 'replace').decode())
    print('BEFORE source_ascii=%s' % s.encode('ascii', 'replace').decode())
finally:
    d.quit()
