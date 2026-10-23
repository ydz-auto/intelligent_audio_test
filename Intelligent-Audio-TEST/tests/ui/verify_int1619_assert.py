# -*- coding: utf-8 -*-
"""INT-1619 断言复核：以精确字符串比较输出 ASCII PASS/FAIL（规避控制台 GBK 乱码）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1619_ranking_select import (  # noqa: E402
    BASE, make_driver, wait_filters, trigger, text_of, js_click, popup_option,
)

EXPECT = {
    'metric_sel': '环境理解评分',
    'source_sel': '平台实测',
    'metric_all': '全部指标',
    'source_all': '全部来源',
}


def main():
    d = make_driver()
    ok = True
    try:
        d.get(BASE + '/rankings?metricCode=ENV_UNDERSTAND_SCORE&source=platform_test')
        wait_filters(d)
        import time
        time.sleep(1.5)
        m = text_of(d, trigger(d, '指标'))
        s = text_of(d, trigger(d, '数据来源'))
        checks = [
            ('directlink_metric', m, EXPECT['metric_sel']),
            ('directlink_source', s, EXPECT['source_sel']),
        ]
        # 重置
        from selenium.webdriver.common.by import By
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if text_of(d, b) in ('重置', '恢复默认', '重置筛选'):
                js_click(d, b)
                break
        time.sleep(1.5)
        checks.append(('reset_metric', text_of(d, trigger(d, '指标')), EXPECT['metric_all']))
        checks.append(('reset_source', text_of(d, trigger(d, '数据来源')), EXPECT['source_all']))
        # UI 选择
        js_click(d, trigger(d, '指标'))
        time.sleep(0.6)
        popup_option(d, EXPECT['metric_sel'])
        time.sleep(1)
        js_click(d, trigger(d, '数据来源'))
        time.sleep(0.6)
        popup_option(d, EXPECT['source_sel'])
        time.sleep(1.2)
        checks.append(('ui_metric', text_of(d, trigger(d, '指标')), EXPECT['metric_sel']))
        checks.append(('ui_source', text_of(d, trigger(d, '数据来源')), EXPECT['source_sel']))

        for name, got, exp in checks:
            good = got == exp
            ok = ok and good
            print('%s %s got_len=%d got_cp=%s exp_cp=%s'
                  % ('PASS' if good else 'FAIL', name, len(got),
                     [ord(c) for c in got], [ord(c) for c in exp]))
        raw = 'ENV_UNDERSTAND_SCORE' not in m and 'platform_test' not in s
        print('%s no_raw_enum' % ('PASS' if raw else 'FAIL'))
        ok = ok and raw
    finally:
        d.quit()
    print('OVERALL ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
