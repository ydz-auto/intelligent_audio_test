# -*- coding: utf-8 -*-
"""INT-1482 续测复走 B：生成(任务290) / 对比(弹窗, 真实任务×2) / 统计页评估维度。

修正 A 轮问题：
- 生成任务从弹窗「已完成任务」列表里选（#290 有 20 用例与评估结果，且尚无报告）；
- 对比报告名在「对比配置」子页签，#compare-name 只在那个 tab 渲染；
- 进度弹窗判定排除生成表单本身（含「选择任务」）。
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
CMP_NAME = '接线测试_INT1482_对比_' + STAMP
GEN_TASK = int(os.environ.get('GEN_TASK', '290'))
CMP_TASKS = [int(x) for x in os.environ.get('CMP_TASKS', '390,413').split(',')]
CREATED = []


def save():
    try:
        with open(os.path.join(L.ART, 'resumeB_result.json'), 'w', encoding='utf-8') as f:
            json.dump({'out': OUT, 'created': CREATED}, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


def section(name, fn):
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1600:]
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
    """进度弹窗（排除生成表单/对比表单本身）。"""
    out = []
    for cand in L.dialogs(d):
        t = cand['text']
        if '选择任务' in t or '基于任务' in t or '对比维度' in t:
            continue
        if any(k in t for k in ('正在生成', '排队中', '生成完成', '生成失败', '正在对比')):
            out.append(cand)
    return out


def wait_progress(d, reqs_watch=None, max_secs=240, on_tick=None):
    samples = []
    end = time.time() + max_secs
    while time.time() < end:
        cur = progress_dialogs(d)
        if cur:
            txt = cur[-1]['text'][:300]
            if not samples or samples[-1] != txt:
                samples.append(txt)
            if '生成完成' in txt or '生成失败' in txt:
                return samples, txt
        time.sleep(2)
    return samples, samples[-1] if samples else ''


def wait_task_list(d, timeout=40):
    """等已完成任务列表真正渲染（数据源 /tasks?status=completed 偶发首屏为空）。"""
    end = time.time() + timeout
    while time.time() < end:
        btns = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-pressed]")]
        for b in btns:
            try:
                if '任务 #' in (b.text or ''):
                    return True
            except Exception:
                pass
        time.sleep(1)
    return False


def main():
    d = L.driver()
    try:
        L.login(d)

        # ───────── A. 生成报告 → 进度 → 成功 → 详情
        def generate():
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
            time.sleep(1.5)
            L.reset_fetch_log(d)
            t_open = L.now_ms()
            L.click_text(d, '生成报告')
            dl = L.wait_dialog(d, '生成报告')
            ok = wait_task_list(d)
            if not ok:
                # 首屏为空：关弹窗、刷新页面、重开一次
                OUT['gen_first_open_empty'] = True
                L.close_dialog(d, 'esc')
                time.sleep(1)
                d.refresh()
                time.sleep(6)
                L.click_text(d, '生成报告')
                dl = L.wait_dialog(d, '生成报告')
                ok = wait_task_list(d)
            OUT['gen_task_list_ready'] = ok
            OUT['gen_dialog_first'] = dl.text[:200]
            OUT['gen_open_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in reqs(d, '/tasks', since=t_open)][:4]
            sub = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报告']
            OUT['gen_submit_disabled_no_task'] = bool(sub and not sub[-1].is_enabled())
            # 选任务（滚动到目标）
            inp = dl.find_element(By.CSS_SELECTOR, "input[placeholder='搜索任务名称或ID']")
            inp.clear()
            inp.send_keys(str(GEN_TASK))
            time.sleep(1.5)
            OUT['gen_filtered_text'] = dl.text[:250]
            target = None
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                try:
                    if b.get_attribute('aria-pressed') is not None and ('任务 #%d' % GEN_TASK) in (b.text or ''):
                        target = b
                        break
                except Exception:
                    pass
            if target is None:
                raise AssertionError('生成弹窗里找不到任务 #%d' % GEN_TASK)
            L.js_click(d, target)
            time.sleep(0.8)
            OUT['gen_picked'] = dl.find_element(By.CSS_SELECTOR, "button[aria-pressed='true']").text[:120]
            # 名称留空提交一次（校验观察）
            name_in = dl.find_element(By.ID, 'report-name')
            name_in.clear()
            L.reset_fetch_log(d)
            t_sub = L.now_ms()
            sub = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报告']
            L.js_click(d, sub[-1])
            time.sleep(3)
            OUT['gen_empty_submit_progress'] = [x['text'][:150] for x in progress_dialogs(d)]
            st = L.find_by_text(d, '报告名称不能为空') + L.find_by_text(d, '请输入报告名称')
            OUT['gen_empty_validation'] = [e.text for e in st if e.is_displayed()][:3]
            form_open = [x for x in L.dialogs(d) if '选择任务' in x['text']]
            if form_open:
                # 空名被拦（客户端校验或按钮未提交）→ 填名重交
                dlg = form_open[-1]['el']
                n = dlg.find_element(By.ID, 'report-name')
                n.clear()
                n.send_keys(GEN_NAME)
                desc = dlg.find_element(By.ID, 'report-desc')
                desc.clear()
                desc.send_keys('接线测试：INT-1482 复走临时报告，验收后删除')
                L.shot(d, 's01_generate_form_light')
                L.reset_fetch_log(d)
                t_sub = L.now_ms()
                for b in dlg.find_elements(By.TAG_NAME, 'button'):
                    if (b.text or '').strip() == '生成报告':
                        L.js_click(d, b)
                        break
            OUT['gen_submit_ts'] = t_sub
            OUT['gen_submit_reqs'] = reqs(d, '/reports', since=t_sub, methods=('POST',))
            samples, last = wait_progress(d, max_secs=240)
            OUT['gen_progress_samples'] = samples
            time.sleep(4)
            OUT['gen_url_after'] = d.current_url
            OUT['gen_body_after'] = L.body(d)[:350]
            OUT['gen_reqs_after'] = reqs(d, '/reports', since=t_sub)
            # 回读
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
            OUT['gen_readback_detail'] = {
                'http': det['status'], 'id': dj.get('id'), 'name': dj.get('name'),
                'task_id': dj.get('task_id'), 'report_type': dj.get('report_type'),
                'status': dj.get('status'),
                'summary': {k: (dj.get('summary') or {}).get(k) for k in
                            ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate')},
                'cases_n': len(dj.get('cases') or []),
                'metric_stats_n': len(dj.get('metric_stats') or []),
            }
            # 详情页
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(5)
            OUT['gen_detail_text'] = L.body(d)[:700]
            L.shot(d, 's02_generate_detail_light')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(5)
            L.shot(d, 's03_generate_detail_dark')
            L.apply_theme(d, 'light')
        section('generate', generate)

        # ───────── B. 对比弹窗（基于任务）
        def compare():
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
            time.sleep(2)
            rows = d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
            picked = 0
            for tr in rows[:2]:
                try:
                    L.js_click(d, tr.find_element(By.XPATH, ".//*[@role='checkbox']"))
                    picked += 1
                    time.sleep(0.4)
                except Exception:
                    pass
            OUT['cmp_rows_selected'] = picked
            time.sleep(0.5)
            L.click_text(d, '批量对比')
            dl = L.wait_dialog(d, '报告对比')
            ready = False
            for _ in range(40):
                if dl.find_elements(By.CSS_SELECTOR, 'label'):
                    ready = True
                    break
                time.sleep(1)
            OUT['cmp_task_list_ready'] = ready
            picked_tasks = []
            for tid in CMP_TASKS:
                for lab in dl.find_elements(By.TAG_NAME, 'label'):
                    if ('#%d' % tid) in (lab.text or '') and tid not in picked_tasks:
                        L.js_click(d, lab.find_element(By.CSS_SELECTOR, "[role='checkbox']"))
                        picked_tasks.append(tid)
                        time.sleep(0.5)
                        break
            OUT['cmp_tasks_picked'] = picked_tasks
            OUT['cmp_tasks_missing'] = [t for t in CMP_TASKS if t not in picked_tasks]
            OUT['cmp_after_pick'] = dl.text[-250:]
            if len(picked_tasks) < 2:
                raise AssertionError('弹窗只勾到 %s，不足两个任务' % picked_tasks)
            # 切对比配置填名 + 读下拉选项
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '对比配置':
                    L.js_click(d, t)
                    time.sleep(1.2)
                    break
            OUT['cmp_config_text'] = dl.text[:400]
            combos = [c for c in dl.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            OUT['cmp_combos'] = len(combos)
            if combos:
                L.js_click(d, combos[0])
                time.sleep(0.8)
                OUT['cmp_dim_options'] = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
                d.find_element(By.TAG_NAME, 'body').send_keys('')
                time.sleep(0.4)
            name_el = dl.find_element(By.ID, 'compare-name')
            name_el.clear()
            name_el.send_keys(CMP_NAME)
            L.shot(d, 's04_compare_config_light')
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '生成对比报告':
                    L.js_click(d, b)
                    break
            cmp_reqs = []
            for i in range(120):
                time.sleep(1)
                cmp_reqs = reqs(d, '/reports/compare', since=t0, methods=('POST',))
                if cmp_reqs:
                    break
            OUT['cmp_reqs'] = cmp_reqs
            OUT['cmp_secs_to_req'] = round((L.now_ms() - t0) / 1000.0, 1)
            samples, last = wait_progress(d, max_secs=240)
            OUT['cmp_progress_samples'] = samples
            OUT['cmp_progress_reqs'] = reqs(d, '/progress', since=t0)
            time.sleep(4)
            OUT['cmp_url_after'] = d.current_url
            OUT['cmp_body_after'] = L.body(d)[:350]
            L.shot(d, 's05_compare_result_light')
            r = L.api(d, '/reports?page=1&per_page=50')
            items = ((r.get('json') or {}).get('data') or {}).get('items') or []
            mine = [i for i in items if CMP_NAME in (i.get('name') or '')]
            OUT['cmp_readback_list'] = [(i['id'], i['name'], i.get('status'), i.get('report_type'),
                                         (i.get('summary') or {}).get('total_cases')) for i in mine[:3]]
            if mine:
                rid = mine[0]['id']
                CREATED.append(rid)
                OUT['cmp_report_id'] = rid
                det = L.api(d, '/reports/%d' % rid)
                dj = ((det.get('json') or {}).get('data') or {})
                OUT['cmp_readback_detail'] = {
                    'http': det['status'], 'id': dj.get('id'), 'name': dj.get('name'),
                    'report_type': dj.get('report_type'),
                    'summary': {k: (dj.get('summary') or {}).get(k) for k in
                                ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate')},
                    'resources': (dj.get('summary') or {}).get('resources'),
                    'metric_data_n': len((dj.get('summary') or {}).get('metric_data') or []),
                }
                d.get(L.BASE + '/report/%d' % rid)
                time.sleep(5)
                OUT['cmp_detail_text'] = L.body(d)[:700]
                L.shot(d, 's06_compare_detail_light')
                L.apply_theme(d, 'dark')
                d.get(L.BASE + '/report/%d' % rid)
                time.sleep(5)
                L.shot(d, 's07_compare_detail_dark')
                L.apply_theme(d, 'light')
        section('compare', compare)

        # ───────── C. 统计页评估维度 / 设备性能 / 散点·热力图
        def stats():
            d.get(L.BASE + '/report-statistics')
            WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
            time.sleep(4)
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            OUT['stats_initial_text'] = L.body(d)[:400]
            L.shot(d, 's08_stats_time_light')
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            OUT['stats_combos'] = len(combos)
            if not combos:
                raise AssertionError('统计页维度下拉不可见')
            L.js_click(d, combos[0])
            time.sleep(1)
            OUT['stats_dim_options'] = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
            picked = False
            for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (o.text or '').strip() == '评估维度' and o.is_displayed():
                    L.js_click(d, o)
                    picked = True
                    break
            OUT['stats_dim_picked'] = picked
            ca = []
            for i in range(120):
                time.sleep(1)
                ca = reqs(d, '/reports/case-averages', since=t0, methods=('POST',))
                if ca:
                    time.sleep(4)
                    break
            OUT['stats_case_avg_reqs'] = ca
            OUT['stats_after_dim_text'] = L.body(d)[:1200]
            cards = {}
            for card in d.find_elements(By.CSS_SELECTOR, 'div.rounded-2xl'):
                txt = (card.text or '').strip()
                for label in ('报告数量', '测试用例执行统计', '评估指标', '设备性能'):
                    if txt.startswith(label) and label not in cards:
                        cards[label] = [x.strip() for x in txt.split('\n') if x.strip()][:3]
            OUT['stats_cards'] = cards
            rows = d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
            OUT['stats_table_rows'] = [(d.execute_script("return arguments[0].textContent", tr) or '')[:120] for tr in rows[:12]]
            L.shot(d, 's09_stats_metric_light')
            # 统计结果 → 图表
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t); time.sleep(2); break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t); time.sleep(3); break
            txt = L.body(d)
            OUT['stats_chart_text'] = txt[:900]
            OUT['stats_canvas_n'] = len(d.find_elements(By.TAG_NAME, 'canvas'))
            OUT['stats_chart_flags'] = {k: (k in txt) for k in ('散点图', '热力图', '设备 × 评估维度')}
            L.shot(d, 's10_stats_charts_light')
            # 深色
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-statistics')
            time.sleep(6)
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            if combos:
                L.js_click(d, combos[0]); time.sleep(1)
                for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (o.text or '').strip() == '评估维度' and o.is_displayed():
                        L.js_click(d, o); break
                time.sleep(14)
            L.shot(d, 's11_stats_metric_dark')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t); time.sleep(2); break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t); time.sleep(3); break
            L.shot(d, 's12_stats_charts_dark')
            L.apply_theme(d, 'light')
        section('stats', stats)

    finally:
        save()
        d.quit()
    print('DONE')


if __name__ == '__main__':
    main()
