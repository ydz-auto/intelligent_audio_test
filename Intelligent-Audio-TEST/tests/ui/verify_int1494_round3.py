# -*- coding: utf-8 -*-
"""INT-1494 第三轮：报告展示页页签筛选效能 + 行内「查看」跳转。"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1494_helpers import (ARTIFACTS, BASE, body_text, clear_perf, driver,  # noqa: E402
                             goto, js_click, requests_simple, result, set_theme,
                             shot)

R = []


def tabs():
    d = driver()
    try:
        set_theme(d, 'light')
        goto(d, '/reports')
        time.sleep(4)
        st, shots = {}, []
        tabs = d.find_elements(By.CSS_SELECTOR, "[role='tab'], button")
        tab_map = {}
        for t in tabs:
            tx = (t.text or '').strip()
            if tx in ('任务报告', '对比报告', '二次对比报告', 'Benchmark 报告', '全部'):
                tab_map[tx] = t
        st['tabs_found'] = list(tab_map)
        # 表格行：tbody tr
        def rows():
            return [r.text.replace('\n', ' | ') for r in d.find_elements(By.CSS_SELECTOR, 'tbody tr')]
        st['rows_all'] = rows()
        clear_perf(d)
        if '对比报告' in tab_map:
            js_click(d, tab_map['对比报告'])
            time.sleep(3)
            st['rows_comparison'] = rows()
            st['api_comparison'] = requests_simple(d, '/reports')[:4]
            st['empty_text_comparison'] = [ln for ln in body_text(d).split('\n') if '暂无' in ln or '没有' in ln][:3]
            shots.append(shot(d, 'reports_tab_comparison_light'))
        if 'Benchmark 报告' in tab_map:
            js_click(d, tab_map['Benchmark 报告'])
            time.sleep(3)
            st['rows_benchmark'] = rows()
            st['api_benchmark'] = requests_simple(d, '/reports')[:4]
        if '任务报告' in tab_map:
            js_click(d, tab_map['任务报告'])
            time.sleep(3)
            st['rows_task'] = rows()
        # 行内「查看」：限定 tbody 内按钮
        clear_perf(d)
        btns = d.find_elements(By.CSS_SELECTOR, 'tbody tr button, tbody tr a')
        target = None
        for b in btns:
            if '查看' in (b.text or ''):
                target = b
                break
        st['row_view_found'] = target is not None
        if target is not None:
            js_click(d, target)
            time.sleep(5)
            st['view_url'] = d.current_url
            st['view_title'] = body_text(d)[:300]
            shots.append(shot(d, 'reports_row_view_light'))
        R.append(result('reports_tabs', True, st, shots))
    except Exception as exc:
        R.append(result('reports_tabs', False, 'EXC %r' % (exc,)))
    finally:
        d.quit()


tabs()
with open(os.path.join(ARTIFACTS, 'int1494_round3.json'), 'w', encoding='utf-8') as f:
    json.dump(R, f, ensure_ascii=False, indent=2)
print(json.dumps(R, ensure_ascii=False, indent=2))
