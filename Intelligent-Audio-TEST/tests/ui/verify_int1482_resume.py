# -*- coding: utf-8 -*-
"""INT-1482 续测复走：报告生成成功态 / 报告对比(412+390) / 统计页评估维度·设备性能·散点热力图。

前置：环境三项核对已过；INT-1572（7d2ad034f）、INT-1571（391a6ec9d）已在 V9.7.31 并部署。
只写「接线测试_」前缀自建报告，脚本末尾由 cleanup_int1482_resume.py 清理。
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}
STAMP = time.strftime('%H%M%S')
GEN_NAME = '接线测试_INT1482_生成_' + STAMP
CMP_NAME = '接线测试_INT1482_对比_' + STAMP
CREATED = []


def save():
    try:
        with open(os.path.join(L.ART, 'resume_result.json'), 'w', encoding='utf-8') as f:
            json.dump({'out': OUT, 'created': CREATED}, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


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


def dialogs_text(d):
    return [x['text'] for x in L.dialogs(d)]


def wait_dialog_gone(d, timeout=180):
    def _f(x):
        return len([1 for dl in L.dialogs(x) if '生成' in dl['text'] or '对比' in dl['text']]) == 0
    WebDriverWait(d, timeout).until(_f)


def main():
    d = L.driver()
    try:
        L.login(d)

        # ───────────────── A. 报告生成：选任务 → 校验 → 提交 → 进度 → 成功 → 详情
        def generate():
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
            time.sleep(1)
            L.reset_fetch_log(d)
            t_open = L.now_ms()
            L.click_text(d, '生成报告')
            dl = L.wait_dialog(d, '生成报告')
            time.sleep(2.5)
            OUT['gen_dialog_text'] = dl.text[:500]
            OUT['gen_open_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')}
                                    for e in reqs(d, since=t_open)][:8]
            # 校验1：未选任务 → 提交按钮禁用
            sub = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报告']
            OUT['gen_submit_disabled_no_task'] = bool(sub and (sub[-1].get_attribute('disabled') is not None
                                                               or not sub[-1].is_enabled()))
            # 校验2：选中任务后名称留空提交
            inp = dl.find_element(By.CSS_SELECTOR, "input[placeholder='搜索任务名称或ID']")
            inp.clear()
            inp.send_keys('585')
            time.sleep(1.5)
            picked = False
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if b.get_attribute('aria-pressed') is not None and '任务 #585' in (b.text or ''):
                    L.js_click(d, b)
                    picked = True
                    break
            OUT['gen_task_picked'] = picked
            OUT['gen_task_list_text'] = dl.text[:400]
            time.sleep(0.8)
            name_in = dl.find_element(By.ID, 'report-name')
            name_in.clear()
            L.reset_fetch_log(d)
            t_sub = L.now_ms()
            sub = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报告']
            if sub:
                L.js_click(d, sub[-1])
            time.sleep(3)
            OUT['gen_empty_name_dialogs'] = dialogs_text(d)[:3]
            OUT['gen_empty_name_reqs'] = reqs(d, '/reports', since=t_sub, methods=('POST',))
            # 若空名被拒/未提交，则填名重交
            still_open = [dl2 for dl2 in L.dialogs(d) if '生成报告' in dl2['text']]
            if still_open:
                dlg = still_open[-1]['el']
                n = dlg.find_element(By.ID, 'report-name')
                n.clear()
                n.send_keys(GEN_NAME)
                L.reset_fetch_log(d)
                t_sub2 = L.now_ms()
                for b in dlg.find_elements(By.TAG_NAME, 'button'):
                    if (b.text or '').strip() == '生成报告':
                        L.js_click(d, b)
                        break
                OUT['gen_submit_ts'] = t_sub2
            else:
                OUT['gen_submit_ts'] = t_sub
            # 进度弹窗采样
            prog_samples = []
            prog_el = None
            for i in range(20):
                for cand in L.dialogs(d):
                    if '生成报告' in cand['text'] or '排队' in cand['text'] or '正在生成' in cand['text'] or '生成完成' in cand['text'] or '生成失败' in cand['text']:
                        prog_el = cand
                        break
                if prog_el:
                    break
                time.sleep(0.5)
            OUT['gen_progress_seen'] = bool(prog_el)
            if prog_el:
                prog_samples.append(prog_el['text'][:300])
                L.shot(d, 'r01_generate_progress_light')
            for i in range(60):
                time.sleep(2)
                cur = [dl2 for dl2 in L.dialogs(d) if any(k in dl2['text'] for k in ('正在生成', '排队', '生成完成', '生成失败'))]
                if cur:
                    txt = cur[-1]['text'][:300]
                    if not prog_samples or prog_samples[-1] != txt:
                        prog_samples.append(txt)
                    if '生成完成' in txt or '生成失败' in txt:
                        break
                else:
                    if prog_samples:
                        break
            OUT['gen_progress_samples'] = prog_samples
            time.sleep(3)
            OUT['gen_url_after'] = d.current_url
            OUT['gen_body_after'] = L.body(d)[:400]
            OUT['gen_reqs'] = reqs(d, '/reports', since=OUT.get('gen_submit_ts', 0))
            # 回读：列表接口找自建报告
            r = L.api(d, '/reports?page=1&per_page=50')
            items = ((r.get('json') or {}).get('data') or {}).get('items') or []
            mine = [i for i in items if GEN_NAME in (i.get('name') or '')]
            if not mine and items:
                # 空名提交被接受时，名称可能是任务名派生
                mine = [i for i in items[:3] if int(i.get('task_id') or 0) == 585]
            OUT['gen_readback_list'] = [(i['id'], i['name'], i.get('status'), i.get('task_id'),
                                         (i.get('summary') or {}).get('total_cases')) for i in mine[:3]]
            if mine:
                rid = mine[0]['id']
                CREATED.append(rid)
                OUT['gen_report_id'] = rid
                det = L.api(d, '/reports/%d' % rid)
                dj = ((det.get('json') or {}).get('data') or {})
                OUT['gen_readback_detail'] = {
                    'status': det['status'], 'id': dj.get('id'), 'name': dj.get('name'),
                    'task_id': dj.get('task_id'), 'report_type': dj.get('report_type'),
                    'summary': {k: (dj.get('summary') or {}).get(k) for k in
                                ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate')},
                    'cases_n': len(dj.get('cases') or []),
                    'metric_stats_n': len(dj.get('metric_stats') or []),
                }
                # 详情页回读 + 截图
                d.get(L.BASE + '/report/%d' % rid)
                try:
                    WebDriverWait(d, 60).until(lambda x: 'report' in (x.page_source or '').lower())
                except Exception:
                    pass
                time.sleep(4)
                OUT['gen_detail_page_text'] = L.body(d)[:600]
                L.shot(d, 'r02_generate_detail_light')
                L.apply_theme(d, 'dark')
                d.get(L.BASE + '/report/%d' % rid)
                time.sleep(5)
                L.shot(d, 'r03_generate_detail_dark')
                L.apply_theme(d, 'light')
        section('generate', generate)

        # ───────────────── B. 报告对比：选两份报告 → 基于任务 412+390 → 提交 → 成功 → 结果
        def compare():
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
            time.sleep(2)
            rows = d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
            picked = 0
            for tr in rows[:2]:
                try:
                    cb = tr.find_element(By.XPATH, ".//*[@role='checkbox']")
                    L.js_click(d, cb)
                    picked += 1
                    time.sleep(0.4)
                except Exception:
                    pass
            OUT['cmp_rows_selected'] = picked
            time.sleep(0.8)
            L.shot(d, 'r04_compare_selected_light')
            L.click_text(d, '批量对比')
            dl = L.wait_dialog(d, '报告对比')
            time.sleep(2)
            OUT['cmp_dialog_text'] = dl.text[:700]
            # 比对配置下拉选项条数（对比维度）
            combos = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            OUT['cmp_combos'] = len(combos)
            # 基于任务 tab 勾选 412 / 390
            picked_tasks = []
            for tid in (412, 390):
                for lab in dl.find_elements(By.TAG_NAME, 'label'):
                    if '#%d' % tid in (lab.text or ''):
                        cb = lab.find_element(By.CSS_SELECTOR, "[role='checkbox']")
                        L.js_click(d, cb)
                        picked_tasks.append(tid)
                        time.sleep(0.5)
                        break
            OUT['cmp_tasks_picked'] = picked_tasks
            OUT['cmp_after_pick'] = dl.text[:400]
            name_el = dl.find_element(By.ID, 'compare-name')
            name_el.clear()
            name_el.send_keys(CMP_NAME)
            L.shot(d, 'r05_compare_config_light')
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '生成对比报告':
                    L.js_click(d, b)
                    break
            # 等 compare 请求返回
            cmp_reqs = []
            for i in range(90):
                time.sleep(1)
                cmp_reqs = reqs(d, '/reports/compare', since=t0, methods=('POST',))
                if cmp_reqs:
                    break
            OUT['cmp_reqs'] = cmp_reqs
            OUT['cmp_secs_to_req'] = round((L.now_ms() - t0) / 1000.0, 1)
            # 进度弹窗（同步 compare → 轮询 /progress）
            samples = []
            for i in range(60):
                time.sleep(2)
                cur = [x for x in L.dialogs(d) if any(k in x['text'] for k in ('生成', '对比', '排队'))]
                if cur:
                    txt = cur[-1]['text'][:300]
                    if not samples or samples[-1] != txt:
                        samples.append(txt)
                    if '生成完成' in txt or '生成失败' in txt:
                        break
                elif samples:
                    break
            OUT['cmp_progress_samples'] = samples
            time.sleep(4)
            OUT['cmp_url_after'] = d.current_url
            OUT['cmp_body_after'] = L.body(d)[:400]
            OUT['cmp_progress_reqs'] = reqs(d, '/progress', since=t0)
            L.shot(d, 'r06_compare_result_light')
            # 回读列表与详情
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
                    'status': det['status'], 'id': dj.get('id'), 'name': dj.get('name'),
                    'report_type': dj.get('report_type'),
                    'summary': {k: (dj.get('summary') or {}).get(k) for k in
                                ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate')},
                    'resources': (dj.get('summary') or {}).get('resources'),
                    'metric_data_n': len((dj.get('summary') or {}).get('metric_data') or []),
                }
                d.get(L.BASE + '/report/%d' % rid)
                time.sleep(5)
                OUT['cmp_detail_text'] = L.body(d)[:600]
                L.shot(d, 'r07_compare_detail_light')
                L.apply_theme(d, 'dark')
                d.get(L.BASE + '/report/%d' % rid)
                time.sleep(5)
                L.shot(d, 'r08_compare_detail_dark')
                L.apply_theme(d, 'light')
        section('compare', compare)

        # ───────────────── C. 统计页：评估维度 / 设备性能 / 散点·热力图
        def stats():
            d.get(L.BASE + '/report-statistics')
            WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
            time.sleep(4)
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            OUT['stats_url'] = d.current_url
            OUT['stats_initial_text'] = L.body(d)[:500]
            L.shot(d, 'r09_stats_time_light')
            # 切评估维度
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            OUT['stats_combos'] = len(combos)
            if combos:
                L.js_click(d, combos[0])
                time.sleep(1)
                opts = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
                OUT['stats_dim_options'] = opts
                for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (o.text or '').strip() == '评估维度' and o.is_displayed():
                        L.js_click(d, o)
                        break
                time.sleep(1)
            # 等 case-averages 返回
            ca = []
            for i in range(90):
                time.sleep(1)
                ca = reqs(d, '/reports/case-averages', since=t0, methods=('POST',))
                if ca:
                    time.sleep(3)
                    break
            OUT['stats_case_avg_reqs'] = ca
            OUT['stats_after_dim_text'] = L.body(d)[:900]
            L.shot(d, 'r10_stats_metric_light')
            # 统计卡取值
            cards = {}
            try:
                for card in d.find_elements(By.CSS_SELECTOR, 'div.rounded-2xl.border'):
                    txt = (card.text or '')
                    for label in ('报告数量', '测试用例执行统计', '评估指标', '设备性能'):
                        if txt.startswith(label):
                            lines = [x.strip() for x in txt.split('\n') if x.strip()]
                            cards[label] = lines[:3]
            except Exception:
                pass
            OUT['stats_cards'] = cards
            # 统计维度表行
            rows = d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
            OUT['stats_table_rows'] = [d.execute_script("return arguments[0].textContent", tr)[:120] for tr in rows[:10]]
            # 统计结果 → 图表
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t)
                    time.sleep(2)
                    break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t)
                    time.sleep(3)
                    break
            OUT['stats_chart_text'] = L.body(d)[:700]
            OUT['stats_canvas_n'] = len(d.find_elements(By.TAG_NAME, 'canvas'))
            OUT['stats_svg_n'] = len(d.find_elements(By.TAG_NAME, 'svg'))
            for kw in ('散点图', '热力图', '设备 × 评估维度'):
                OUT['stats_has_%s' % kw] = kw in L.body(d)
            L.shot(d, 'r11_stats_charts_light')
            # 深色
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-statistics')
            time.sleep(6)
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            if combos:
                L.js_click(d, combos[0])
                time.sleep(1)
                for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (o.text or '').strip() == '评估维度' and o.is_displayed():
                        L.js_click(d, o)
                        break
                time.sleep(12)
            L.shot(d, 'r12_stats_metric_dark')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t); time.sleep(2); break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t); time.sleep(3); break
            L.shot(d, 'r13_stats_charts_dark')
            L.apply_theme(d, 'light')
        section('stats', stats)

    finally:
        save()
        d.quit()
    print('DONE')


if __name__ == '__main__':
    main()
