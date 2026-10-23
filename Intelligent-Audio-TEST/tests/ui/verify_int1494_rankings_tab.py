# -*- coding: utf-8 -*-
"""INT-1494 排行榜分类页签交互（空态下的真实请求与 URL 态）。"""
import json, os, sys, time
from selenium.webdriver.common.by import By
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1494_helpers import (ARTIFACTS, body_text, clear_perf, driver, goto,
                             js_click, requests_simple, result, set_theme, shot)
R = []
d = driver()
try:
    set_theme(d, 'light')
    clear_perf(d)
    goto(d, '/rankings', wait_text='排行榜')
    time.sleep(3)
    st = {'url0': d.current_url}
    for label in ('语音识别', '语音合成', '全部'):
        b = None
        for x in d.find_elements(By.CSS_SELECTOR, 'button, a'):
            if (x.text or '').strip().startswith(label) and x.is_displayed():
                b = x
                break
        if b is not None:
            clear_perf(d)
            js_click(d, b)
            time.sleep(2.5)
            st[label] = {'url': d.current_url,
                         'api': requests_simple(d, '/benchmarks')[:3],
                         'text': [t for t in body_text(d).split('\n') if '暂无' in t][:2]}
    st['compute_button'] = any('立即计算' in (x.text or '') for x in d.find_elements(By.CSS_SELECTOR, 'button'))
    R.append(result('rankings_tabs', True, st, [shot(d, 'rankings_tab_asr_light')]))
finally:
    d.quit()
json.dump(R, open(os.path.join(ARTIFACTS, 'int1494_rankings_tab.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(json.dumps(R, ensure_ascii=False, indent=2))
