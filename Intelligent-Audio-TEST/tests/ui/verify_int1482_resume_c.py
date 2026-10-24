# -*- coding: utf-8 -*-
"""INT-1482 续测 C 轮：生成成功态(新夹具) + 统计页评估维度/设备性能/散点·热力图。

新夹具（2026-10-24 DB 复核）：任务 398「拒识场景测试E2E测试任务_2026/9/22 19:21:21」
completed / 2 结果 / 15 维度得分 / task_device_relations→device 9（pura90小艺，online 未删）
/ test_reports 无任何记录（含软删）。用于打通「生成成功态」，生成后最新任务报告=本报告，
统计页 task 上下文指向存活任务 398。
"""
import atexit
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
STAMP = time.strftime('%H%M%S')
GEN_NAME = '接线测试_INT1482_生成_' + STAMP
CREATED = []
GEN_TASK = int(os.environ.get('GEN_TASK', '398'))


def save():
    try:
        with open(os.path.join(L.ART, 'resumeC_result.json'), 'w', encoding='utf-8') as f:
            json.dump({'out': OUT, 'created': CREATED, 'gen_task': GEN_TASK}, f,
                      ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


def section(name, fn):
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1800:]
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


def progress_dialogs(d):
    out = []
    for cand in L.dialogs(d):
        t = cand['text']
        if '选择任务' in t or '基于任务' in t or '对比维度' in t:
            continue
        if any(k in t for k in ('正在生成', '排队中', '生成完成', '生成失败')):
            out.append(cand)
    return out


def cards(d):
    out = {}
    for card in d.find_elements(By.CSS_SELECTOR, 'div.rounded-2xl'):
        txt = (card.text or '').strip()
        for label in ('报告数量', '测试用例执行统计', '评估指标', '设备性能'):
            if txt.startswith(label) and label not in out:
                out[label] = [x.strip() for x in txt.split('\n') if x.strip()][:3]
    return out


def main():
    d = L.driver()
    try:
        L.login(d)
        OUT['env_base'] = L.BASE
        OUT['env_backend'] = L.BACKEND

        # ───── A. 生成成功态
        def generate():
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
            time.sleep(1.5)
            L.reset_fetch_log(d)
            t_open = L.now_ms()
            L.click_text(d, '生成报告')
            dl = L.wait_dialog(d, '生成报告')
            for _ in range(40):
                if [b for b in dl.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]')]:
                    break
                time.sleep(1)
            OUT['gen_open_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')}
                                    for e in reqs(d, '/tasks', since=t_open)][:4]
            inp = dl.find_element(By.CSS_SELECTOR, "input[placeholder='搜索任务名称或ID']")
            inp.clear()
            inp.send_keys(str(GEN_TASK))
            time.sleep(1.2)
            target = None
            for b in dl.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]'):
                if ('任务 #%d' % GEN_TASK) in (b.text or ''):
                    target = b
                    break
            if target is None:
                raise AssertionError('弹窗内无任务 #%d（已完成列表未加载）' % GEN_TASK)
            OUT['gen_task_text'] = target.text[:160]
            L.js_click(d, target)
            time.sleep(0.6)
            n = dl.find_element(By.ID, 'report-name')
            n.clear()
            n.send_keys(GEN_NAME)
            desc = dl.find_element(By.ID, 'report-desc')
            desc.clear()
            desc.send_keys('接线测试：INT-1482 复走临时报告，验收后删除')
            L.shot(d, 'c01_generate_form_light')
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '生成报告':
                    L.js_click(d, b)
                    break
            samples = []
            end = time.time() + 300
            while time.time() < end:
                time.sleep(2)
                cur = progress_dialogs(d)
                if cur:
                    txt = cur[-1]['text'][:300]
                    if not samples or samples[-1] != txt:
                        samples.append(txt)
                    if '生成完成' in txt or '生成失败' in txt:
                        L.shot(d, 'c02_generate_progress_final')
                        break
                elif samples:
                    break
            OUT['gen_progress_samples'] = samples
            OUT['gen_reqs'] = reqs(d, '/reports', since=t0)
            time.sleep(4)
            OUT['gen_url_after'] = d.current_url
            OUT['gen_body_after'] = L.body(d)[:400]
            r = L.api(d, '/reports?page=1&per_page=50')
            items = ((r.get('json') or {}).get('data') or {}).get('items') or []
            mine = [i for i in items if GEN_NAME in (i.get('name') or '')]
            OUT['gen_readback_list'] = [(i['id'], i['name'], i.get('status'), i.get('task_id'),
                                         (i.get('summary') or {}).get('total_cases')) for i in mine[:3]]
            if not mine:
                raise AssertionError('列表回读未找到自建报告 %s' % GEN_NAME)
            rid = mine[0]['id']
            CREATED.append(rid)
            OUT['gen_report_id'] = rid
            det = L.api(d, '/reports/%d' % rid)
            dj = ((det.get('json') or {}).get('data') or {})
            sm = dj.get('summary') or {}
            OUT['gen_readback_detail'] = {
                'http': det['status'], 'name': dj.get('name'), 'status': dj.get('status'),
                'task_id': dj.get('task_id'), 'report_type': dj.get('report_type'),
                'summary': {k: sm.get(k) for k in ('total_cases', 'completed_cases', 'failed_cases',
                                                   'pass_rate', 'overall_success_rate')},
                'devices': [x.get('name') if isinstance(x, dict) else x for x in (sm.get('devices') or [])][:5],
                'resources_n': len(sm.get('resources') or []),
                'all_metrics_n': len(sm.get('all_metrics') or []),
                'cases_n': len(dj.get('cases') or sm.get('cases') or []),
                'metric_stats_n': len(dj.get('metric_stats') or []),
            }
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(6)
            OUT['gen_detail_text'] = L.body(d)[:900]
            L.shot(d, 'c03_generate_detail_light')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(6)
            L.shot(d, 'c04_generate_detail_dark')
            L.apply_theme(d, 'light')
        section('generate', generate)

        # ───── B. 统计页评估维度 / 设备性能 / 散点·热力图
        def stats():
            L.reset_fetch_log(d)
            t_all = L.now_ms()
            d.get(L.BASE + '/report-statistics')
            WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
            time.sleep(6)
            OUT['stats_initial_text'] = L.body(d)[:500]
            OUT['stats_initial_cards'] = cards(d)
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            OUT['stats_combos'] = len(combos)
            if not combos:
                raise AssertionError('维度下拉不可见')
            L.js_click(d, combos[0])
            time.sleep(1)
            OUT['stats_dim_options'] = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                                        if o.is_displayed()]
            picked = False
            for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (o.text or '').strip() == '评估维度' and o.is_displayed():
                    L.js_click(d, o)
                    picked = True
                    break
            OUT['stats_dim_picked'] = picked
            t0 = L.now_ms()
            ca = []
            for _ in range(120):
                time.sleep(1)
                ca = reqs(d, '/reports/case-averages', since=t0, methods=('POST',))
                if ca:
                    break
            OUT['stats_case_avg_reqs'] = ca
            time.sleep(6)
            OUT['stats_text'] = L.body(d)[:1400]
            OUT['stats_cards'] = cards(d)
            OUT['stats_table_rows'] = [(d.execute_script("return arguments[0].textContent", tr) or '')[:140]
                                       for tr in d.find_elements(By.CSS_SELECTOR, 'table tbody tr')[:12]]
            OUT['stats_report_list_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')}
                                             for e in reqs(d, '/reports?', since=t_all)][:3]
            L.shot(d, 'c05_stats_metric_light')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t); time.sleep(2); break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t); time.sleep(4); break
            txt = L.body(d)
            OUT['stats_chart_text'] = txt[-800:]
            OUT['stats_canvas_n'] = len(d.find_elements(By.TAG_NAME, 'canvas'))
            OUT['stats_svg_n'] = len(d.find_elements(By.TAG_NAME, 'svg'))
            OUT['stats_chart_flags'] = {k: (k in txt) for k in ('散点图', '热力图', '设备 × 评估维度', '暂无数据')}
            L.shot(d, 'c06_stats_charts_light')
            # 深色
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-statistics')
            time.sleep(8)
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            if combos:
                L.js_click(d, combos[0]); time.sleep(1)
                for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (o.text or '').strip() == '评估维度' and o.is_displayed():
                        L.js_click(d, o); break
                time.sleep(16)
            OUT['stats_dark_cards'] = cards(d)
            L.shot(d, 'c07_stats_metric_dark')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t); time.sleep(2); break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t); time.sleep(3); break
            L.shot(d, 'c08_stats_charts_dark')
            L.apply_theme(d, 'light')
        section('stats', stats)

        # ───── C. 回读：最新任务报告是否指向存活任务
        def readback():
            r = L.api(d, '/reports?page=1&per_page=1000&sort_by=created_at&order=desc&deleted=false&favorite=false')
            items = ((r.get('json') or {}).get('data') or {}).get('items') or []
            first = next((i for i in items if isinstance(i.get('task_id'), int) and i.get('task_id') > 0), None)
            OUT['readback_latest_task_report'] = {
                'report_id': first.get('id') if first else None,
                'task_id': first.get('task_id') if first else None,
                'name': first.get('name') if first else None,
                'created_at': first.get('created_at') if first else None,
            }
            if first:
                ra = L.api(d, '/reports/case-averages', 'POST', {'task_id': first['task_id']}, timeout=180)
                j = ra.get('json') or {}
                data = j.get('data') or {}
                OUT['readback_case_avg'] = {
                    'http': ra['status'], 'task_id': first['task_id'],
                    'total_cases': data.get('total_cases'), 'total_results': data.get('total_results'),
                    'overall_n': len(data.get('overall_averages') or []),
                    'resources_n': len(data.get('resources') or []),
                    'metric_data_n': len(data.get('metric_data') or []),
                    'partial': data.get('partial'),
                    'msg': j.get('message'),
                }
        section('readback', readback)

    finally:
        save()
        d.quit()
    print('DONE')


if __name__ == '__main__':
    main()
