# -*- coding: utf-8 -*-
"""INT-1481 复测补充：单独复验 INT-1502「停止测试音」成功路径（真实栈 15173/15000）。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_int1481_spl_device as h
import verify_int1481_retest_fixes as r


def main():
    d = h.new_driver()
    try:
        d.get(h.BASE + '/SPLMapping')
        time.sleep(6)
        h.wait_rows(d)
        h.js_click(d, h.find(d, "//button[normalize-space(.)='添加增益映射']"))
        time.sleep(1.2)
        h.set_input(d, '映射名称', '接线测试_INT1481R2_停止')
        h.open_select(d, '关联播放设备', '设备正面（0.5m+0°）')
        h.set_input(d, '第 1 行增益偏移', '-12')
        time.sleep(0.5)
        r.stub_test_tone_success(d)
        h.js_click(d, h.find(d, "//button[@aria-label='第 1 行播放测试音']"))
        time.sleep(2)
        before = h.log_len(d)
        h.js_click(d, h.find(d, "//button[@aria-label='第 1 行播放测试音']"))
        time.sleep(2.5)
        stops = [e for e in h.reqlog(d, before) if '/spl/test-tone/stop' in e['url']]
        h.check('1502b 停止请求 200', bool(stops) and str(stops[0]['status']) == '200',
                [(e['method'], e['status'], e['reqBody'], e['respBody'][:120]) for e in stops])
        pressed = h.find(d, "//button[@aria-label='第 1 行播放测试音']").get_attribute('aria-pressed')
        h.check('1502b 停止后退出播放态', pressed == 'false', pressed)
        h.shot(d, '69_int1502_stop_retry_light')
        h.click_text(d, '取消')
        time.sleep(0.6)
    finally:
        try:
            d.quit()
        except Exception:
            pass
        h.log('CHECKS: %d/%d' % (sum(1 for c in h.EVID['checks'] if c['ok']), len(h.EVID['checks'])))
        for c in h.EVID['checks']:
            if not c['ok']:
                h.log('FAILED:', c['name'], str(c['detail'])[:400])


if __name__ == '__main__':
    main()
