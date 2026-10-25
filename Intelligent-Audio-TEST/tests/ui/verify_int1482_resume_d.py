# -*- coding: utf-8 -*-
"""INT-1482 续测 D 轮（只读）：INT-1776 task_name 部署后 UI 复核 + 统计页指标层取证。

本轮不写任何记录：
- 报告中心列表 / 报告详情 564（真实报告，task 413 存活）核对任务名渲染；
- 统计页核对 case-averages 实测响应，并与 report_service 日志里 device_service 50053 refused 对照。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}


def save():
    with open(os.path.join(L.ART, 'resumeD_result.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)


def section(name, fn):
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1500:]
    save()


def reqs(d, contains=None, since=0, methods=None):
    out = []
    for e in L.fetch_log(d, since):
        u = e.get('url', '')
        if contains and contains not in u:
            continue
        if methods and e.get('method') not in methods:
            continue
        out.append({k: e.get(k) for k in ('method', 'url', 'status', 'reqBody', 'resBody', 'error')})
    return out


def cards(d):
    out = {}
    for card in d.find_elements(By.CSS_SELECTOR, 'div.rounded-2xl'):
        txt = (card.text or '').strip()
        for label in ('报告数量', '测试用例执行统计', '评估指标', '设备性能'):
            if txt.startswith(label) and label not in out:
                out[label] = [x.strip() for x in txt.split('\n') if x.strip()][:4]
    return out


def main():
    d = L.driver()
    try:
        L.login(d)
        OUT['env_base'] = L.BASE
        OUT['env_backend'] = L.BACKEND

        # ── A. 报告中心列表：task_name
        def center():
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
            time.sleep(2.5)
            OUT['center_list_req'] = [{k: e.get(k) for k in ('method', 'url', 'status')}
                                      for e in reqs(d, '/reports?', since=t0, methods=('GET',))][:2]
            rows = []
            for tr in d.find_elements(By.CSS_SELECTOR, 'table tbody tr'):
                rows.append((d.execute_script("return arguments[0].textContent", tr) or '').strip()[:120])
            OUT['center_rows'] = rows[:8]
            body = L.body(d)
            OUT['center_has_413_name'] = '环境理解小艺E2E测试任务_2026/9/28 11:44:42' in body
            OUT['center_has_any_task_name'] = 'E2E测试任务_' in body
            L.shot(d, 'd01_report_center_light')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-center')
            time.sleep(5)
            OUT['center_dark_has_name'] = '环境理解小艺E2E测试任务_2026/9/28 11:44:42' in L.body(d)
            L.shot(d, 'd02_report_center_dark')
            L.apply_theme(d, 'light')
        section('center', center)

        # ── B. 报告详情 564 header 任务名
        def detail():
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            d.get(L.BASE + '/report/564')
            time.sleep(7)
            txt = L.body(d)
            OUT['detail_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')}
                                  for e in reqs(d, '/reports/564', since=t0)][:4]
            r = L.api(d, '/reports/564')
            dj = ((r.get('json') or {}).get('data') or {})
            OUT['detail_api'] = {'http': r['status'], 'task_id': dj.get('task_id'),
                                 'task_name': dj.get('task_name'),
                                 'summary_task_name': (dj.get('summary') or {}).get('task_name')}
            seg = txt[:1200]
            OUT['detail_text_head'] = seg
            OUT['detail_has_name'] = '环境理解小艺E2E测试任务_2026/9/28 11:44:42' in txt
            L.shot(d, 'd03_report_detail_564_light')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report/564')
            time.sleep(7)
            OUT['detail_dark_has_name'] = '环境理解小艺E2E测试任务_2026/9/28 11:44:42' in L.body(d)
            L.shot(d, 'd04_report_detail_564_dark')
            L.apply_theme(d, 'light')
        section('detail', detail)

        # ── C. 统计页：指标层实测（环境降级取证）
        def stats():
            L.reset_fetch_log(d)
            t_all = L.now_ms()
            d.get(L.BASE + '/report-statistics')
            WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
            time.sleep(8)
            OUT['stats_text_head'] = L.body(d)[:900]
            OUT['stats_cards'] = cards(d)
            OUT['stats_report_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')}
                                        for e in reqs(d, '/reports?', since=t_all, methods=('GET',))][:2]
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            OUT['stats_combos'] = len(combos)
            if combos:
                L.js_click(d, combos[0])
                time.sleep(1.2)
                for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (o.text or '').strip() == '评估维度' and o.is_displayed():
                        L.js_click(d, o)
                        break
                time.sleep(1)
            t1 = L.now_ms()
            ca = []
            for _ in range(90):
                time.sleep(1)
                ca = reqs(d, '/reports/case-averages', since=t1, methods=('POST',))
                if ca:
                    break
            OUT['stats_case_avg_reqs'] = [
                {'status': c.get('status'), 'reqBody': c.get('reqBody'),
                 'resHead': (c.get('resBody') or '')[:700]} for c in ca[:2]
            ]
            time.sleep(6)
            OUT['stats_cards_after'] = cards(d)
            txt = L.body(d)
            OUT['stats_has_empty'] = '暂无数据' in txt or '暂无统计数据' in txt
            OUT['stats_text_tail'] = txt[-900:]
            L.shot(d, 'd05_stats_light_env_degraded')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-statistics')
            time.sleep(10)
            L.shot(d, 'd06_stats_dark_env_degraded')
            L.apply_theme(d, 'light')
        section('stats', stats)

    finally:
        save()
        d.quit()
    print('DONE')


if __name__ == '__main__':
    main()
