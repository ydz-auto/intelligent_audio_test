# -*- coding: utf-8 -*-
"""INT-2211 返工复测 · 用例域补测（/testcases/by-group，浅/深）。

用例卡「最后编辑时间」= 后端裸 UTC +8h（逐条与 /api/v1/testcases 原始 updated_at 比对）。
运行：D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/verify_int2211_testcases_retest.py
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15231')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import verify_int2211_retest as R  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

WANT = '环境理解'


def gather(drv):
    return drv.execute_script(
        """var out=[];
           var walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
           while(walker.nextNode()){
             var t=walker.currentNode.nodeValue||'';
             if(t.indexOf('最后编辑时间')>=0){
               var p=walker.currentNode.parentElement;
               out.push((p && p.textContent || '').trim());
             }
           }
           return out;"""
    )


def main():
    token, user = R.B.rsa_login_token(*R.ACCOUNT)
    status, items = R.api_records(token, '/api/v1/testcases?per_page=500')
    expected = set()
    for it in items:
        v = it.get('updated_at') or it.get('created_at')
        if v:
            exp = R.local_dt(v)
            if exp:
                expected.add(exp)
    print('api=%s cases=%d expected=%d' % (status, len(items), len(expected)))
    drv = R.B.driver_init()
    try:
        R.B.bootstrap(drv, token, user)
        for theme in ('light', 'dark'):
            if theme == 'dark':
                R.B.set_theme(drv, 'dark')
            R.reset(drv)
            R.B.goto(drv, '/testcases/by-group', '用例')
            R.assert_theme(drv, theme)
            WebDriverWait(drv, 45).until(lambda d: WANT in R.B.body_text(d))
            time.sleep(1.0)
            drv.find_element(By.XPATH, "//span[contains(normalize-space(.), '%s')]" % WANT).click()
            WebDriverWait(drv, 45).until(lambda d: '最后编辑时间' in R.B.body_text(d))
            time.sleep(1.5)
            lines = gather(drv)
            times = []
            for ln in lines:
                m = re.search(r'最后编辑时间\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', ln)
                if m:
                    times.append(m.group(1))
            hit = [t for t in times if t in expected]
            bad = [t for t in times if t not in expected]
            R.record('testcases[%s] 用例卡最后编辑时间 +8' % theme,
                     bool(times) and not bad,
                     'DOM %d 条，命中 %d，未命中 %s；样例 %s'
                     % (len(times), len(hit), bad[:3], times[:3]))
            R.shot(drv, 'testcases_%s' % theme)
            R.capture_net(drv)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    bad = [r for r in R.RESULTS if not r['ok']]
    print('\n==== TOTAL %d, FAIL %d ====' % (len(R.RESULTS), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
