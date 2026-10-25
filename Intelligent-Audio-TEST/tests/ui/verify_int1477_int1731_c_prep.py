# -*- coding: utf-8 -*-
"""为 verify_int1477_int1731_c 准备 2 轮夹具（复用 base.create_fixtures，不跑四窗复测）。

用法：FIXTAG=10241546 python tests/ui/verify_int1477_int1731_c_prep.py
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_int1477_int1731 as base  # noqa: E402

TAG = os.environ.get('FIXTAG', '10241546')
base.GROUP = '接线测试_INT1477R组' + TAG
base.NAMES = ['接线测试_INT1477R_' + TAG + '_A', '接线测试_INT1477R_' + TAG + '_B']


def main():
    d = base.driver()
    try:
        d.get(base.BASE + '/testcases/by-group')
        base.wait_page(d)
        created = base.create_fixtures(d)
        print('FIXTURES ' + json.dumps(created, ensure_ascii=False), flush=True)
        if any(not x.get('id') for x in created):
            raise AssertionError('夹具创建失败')
    finally:
        try:
            d.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
