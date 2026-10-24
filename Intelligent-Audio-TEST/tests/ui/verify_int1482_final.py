# -*- coding: utf-8 -*-
"""INT-1482 续测终局：生成成功态(任务310) + 统计页评估维度/设备性能/散点热力图（eval 恢复后）。"""
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


def save():
    try:
        with open(os.path.join(L.ART, 'final_result.json'), 'w', encoding='utf-8') as f:
            json.dump({'out': OUT, 'created': CREATED}, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


def section(name, fn):
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1400:]
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


def main():
    d = L.driver()
    try:
        L.login(d)

        # ───── 生成成功态
        def generate():
            d.get(L.BASE + '/report-center')
            WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
            time.sleep(1.5)
            L.click_text(d, '生成报告')
            dl = L.wait_dialog(d, '生成报告')
            for _ in range(40):
                if [b for b in dl.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]')]:
                    break
                time.sleep(1)
            inp = dl.find_element(By.CSS_SELECTOR, "input[placeholder='搜索任务名称或ID']")
            inp.clear()
            inp.send_keys('310')
            time.sleep(1.2)
            target = None
            for b in dl.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]'):
                if '任务 #310' in (b.text or ''):
                    target = b
                    break
            if target is None:
                raise AssertionError('弹窗内无任务 #310')
            L.js_click(d, target)
            time.sleep(0.6)
            n = dl.find_element(By.ID, 'report-name')
            n.clear()
            n.send_keys(GEN_NAME)
            desc = dl.find_element(By.ID, 'report-desc')
            desc.clear()
            desc.send_keys('接线测试：INT-1482 复走临时报告，验收后删除')
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
                        L.shot(d, 'f01_generate_progress_final')
                        break
                elif samples:
                    break
            OUT['gen_progress_samples'] = samples
            OUT['gen_reqs'] = reqs(d, '/reports', since=t0)
            time.sleep(4)
            OUT['gen_url_after'] = d.current_url
            OUT['gen_body_after'] = L.body(d)[:300]
            r = L.api(d, '/reports?page=1&per_page=50')
            items = ((r.get('json') or {}).get('data') or {}).get('items') or []
            mine = [i for i in items if GEN_NAME in (i.get('name') or '')]
            OUT['gen_readback_list'] = [(i['id'], i['name'], i.get('status'), i.get('task_id'),
                                         (i.get('summary') or {}).get('total_cases')) for i in mine[:3]]
            if not mine:
                raise AssertionError('未查到自建报告')
            rid = mine[0]['id']
            CREATED.append(rid)
            OUT['gen_report_id'] = rid
            det = L.api(d, '/reports/%d' % rid)
            dj = ((det.get('json') or {}).get('data') or {})
            OUT['gen_readback_detail'] = {
                'http': det['status'], 'name': dj.get('name'), 'status': dj.get('status'),
                'task_id': dj.get('task_id'),
                'summary': {k: (dj.get('summary') or {}).get(k) for k in
                            ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate')},
                'cases_n': len(dj.get('cases') or []),
                'metric_stats_n': len(dj.get('metric_stats') or []),
            }
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(5)
            OUT['gen_detail_text'] = L.body(d)[:600]
            L.shot(d, 'f02_generate_detail_light')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report/%d' % rid)
            time.sleep(5)
            L.shot(d, 'f03_generate_detail_dark')
            L.apply_theme(d, 'light')
        section('generate', generate)

        # ───── 统计页评估维度（生成成功后最新任务报告=任务310）
        def stats():
            L.reset_fetch_log(d)
            d.get(L.BASE + '/report-statistics')
            WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
            time.sleep(5)
            t0 = L.now_ms()
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            if not combos:
                raise AssertionError('维度下拉不可见')
            L.js_click(d, combos[0])
            time.sleep(1)
            OUT['stats_dim_options'] = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
            for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (o.text or '').strip() == '评估维度' and o.is_displayed():
                    L.js_click(d, o)
                    break
            ca = []
            for i in range(90):
                time.sleep(1)
                ca = reqs(d, '/reports/case-averages', since=t0, methods=('POST',))
                if ca:
                    break
            time.sleep(6)
            OUT['stats_case_avg_reqs'] = ca
            OUT['stats_text'] = L.body(d)[:1200]
            cards = {}
            for card in d.find_elements(By.CSS_SELECTOR, 'div.rounded-2xl'):
                txt = (card.text or '').strip()
                for label in ('报告数量', '测试用例执行统计', '评估指标', '设备性能'):
                    if txt.startswith(label) and label not in cards:
                        cards[label] = [x.strip() for x in txt.split('\n') if x.strip()][:3]
            OUT['stats_cards'] = cards
            OUT['stats_table_rows'] = [(d.execute_script("return arguments[0].textContent", tr) or '')[:120]
                                       for tr in d.find_elements(By.CSS_SELECTOR, 'table tbody tr')[:12]]
            L.shot(d, 'f04_stats_metric_light')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t); time.sleep(2); break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t); time.sleep(4); break
            txt = L.body(d)
            OUT['stats_chart_text'] = txt[-600:]
            OUT['stats_canvas_n'] = len(d.find_elements(By.TAG_NAME, 'canvas'))
            OUT['stats_svg_n'] = len(d.find_elements(By.TAG_NAME, 'svg'))
            L.shot(d, 'f05_stats_charts_light')
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-statistics')
            time.sleep(6)
            combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
            if combos:
                L.js_click(d, combos[0]); time.sleep(1)
                for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                    if (o.text or '').strip() == '评估维度' and o.is_displayed():
                        L.js_click(d, o); break
                time.sleep(16)
            L.shot(d, 'f06_stats_metric_dark')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '统计结果' and t.is_displayed():
                    L.js_click(d, t); time.sleep(2); break
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '图表' and t.is_displayed():
                    L.js_click(d, t); time.sleep(3); break
            L.shot(d, 'f07_stats_charts_dark')
            L.apply_theme(d, 'light')
        section('stats', stats)

    finally:
        save()
        d.quit()
    print('DONE')


if __name__ == '__main__':
    main()
