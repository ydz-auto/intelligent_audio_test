# -*- coding: utf-8 -*-
"""INT-1731 四窗复测三段：声压窗 (b) 指定轮次空勾选不提交 / (c) 逐轮仅第2轮提交回读。"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_int1477_int1731 as base  # noqa: E402
import verify_int1477_int1731_b as b  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

TAG = os.environ.get('FIXTAG', '10241546')
base.GROUP = '接线测试_INT1477R组' + TAG
base.NAMES = ['接线测试_INT1477R_' + TAG + '_A', '接线测试_INT1477R_' + TAG + '_B']
NAMES = base.NAMES
OUT = {'fixtures': {}, 'submit': {}}


def log(*a):
    print(*a, flush=True)


def main():
    d = base.driver()
    try:
        d.get(base.BASE + '/testcases/by-group')
        base.wait_page(d)
        ids = b.find_ids(d)
        OUT['fixtures'] = ids
        if any(v is None for v in ids.values()):
            raise AssertionError('夹具用例缺失')
        base.open_page(d)
        OUT['submit']['before'] = b.all_states(d, ids)
        try:
            OUT['submit']['b_specific_none'] = b.spl_submit(
                d, 'specific_none', ['第1轮'], '66', 'r_spl_submit_none')
        except Exception as e:
            OUT['submit']['b_specific_none'] = {'error': repr(e)}
            log('B ERR', repr(e))
            try:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except Exception:
                pass
            time.sleep(1)
        OUT['submit']['after_b'] = b.all_states(d, ids)
        try:
            OUT['submit']['c_per_round_round2'] = b.spl_submit(
                d, 'per_round', [], '67', 'r_spl_submit_per_round')
        except Exception as e:
            OUT['submit']['c_per_round_round2'] = {'error': repr(e)}
            log('C ERR', repr(e))
        OUT['submit']['after_c'] = b.all_states(d, ids)
    finally:
        json.dump(OUT, open(os.path.join(base.ART, 'rounds_evidence_c.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
    log('DONE')


if __name__ == '__main__':
    main()
