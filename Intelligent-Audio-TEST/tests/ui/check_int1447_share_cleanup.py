# -*- coding: utf-8 -*-
"""INT-1447 收尾：核验报告 497 分享列表为空（本 run 产物已撤销，无残留）。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1447_report_share_custom import (
    BASE, REPORT_ID, _driver, _login, _goto,
)

drv = _driver()
try:
    _login(drv)
    _goto(drv, f'/report/{REPORT_ID}')
    time_ = __import__('time')
    time_.sleep(2)
    res = drv.execute_async_script("""
      const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
      const r = await fetch('/api/v1/reports/' + arguments[0] + '/share', {
        headers: {'Authorization': 'Bearer ' + token}
      });
      const body = await r.text();
      arguments[arguments.length - 1](JSON.stringify({status: r.status, body: body}));
    """, REPORT_ID)
    print('shares_for_497 =', res)
    data = json.loads(res)
    shares = json.loads(data['body']).get('data', {}).get('shares', [])
    active = [s for s in shares if not s.get('revoked')]
    print('total_shares:', len(shares), 'active_shares:', len(active))
    print('RESULT:', 'CLEAN' if len(shares) == 0 else 'HAS_SHARES')
except Exception as e:
    print('CHECK_ERROR:', repr(e))
finally:
    try:
        drv.quit()
    except Exception:
        pass
