# -*- coding: utf-8 -*-
"""INT-1482 续测 E 轮：INT-1825 解阻后统计页指标层实测（浅/深）。

流程：
1) 用任务 411（completed / 2 用例 / 1 设备 / 有维度结果 / 无报告）自建「接线测试_INT1482_统计指标层」报告，
   使其成为报告列表最新任务报告 → 统计页 case-averages 的上下文。
2) /report-statistics 实测：报告数量/用例执行/评估指标/设备性能四卡、评估维度行、散点图/热力图；
   抓 GET /reports 与 POST /reports/case-averages 的请求体与响应体；浅色 + 深色截图（深色前断言 html.dark + body 背景）。
3) 清理：软删 + 彻底删除自建报告，回读 404。
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

OUT = {'created': []}
FIXTURE_NAME = '接线测试_INT1482_统计指标层'


def save():
    path = os.path.join(L.ART, 'resumeE_result.json')
    merged = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                merged = json.load(f)
        except Exception:
            merged = {}
    merged.update(OUT)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=1, default=str)


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


def table_rows(d):
    rows = []
    for tr in d.find_elements(By.CSS_SELECTOR, 'table tbody tr'):
        rows.append((d.execute_script("return arguments[0].textContent", tr) or '').strip()[:160])
    return rows


def canvases(d):
    return len([c for c in d.find_elements(By.CSS_SELECTOR, 'canvas') if c.is_displayed()])


def theme_state(d):
    return d.execute_script("""
      return {dark: document.documentElement.classList.contains('dark'),
              cls: document.documentElement.className,
              bg: getComputedStyle(document.body).backgroundColor};
    """)


def pick_dimension(d, label):
    combos = [c for c in d.find_elements(By.CSS_SELECTOR, "[role='combobox']") if c.is_displayed()]
    if not combos:
        raise RuntimeError('no visible combobox')
    L.js_click(d, combos[0])
    time.sleep(1.5)
    for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
        if (o.text or '').strip() == label and o.is_displayed():
            L.js_click(d, o)
            time.sleep(2)
            return True
    raise RuntimeError('option not found: ' + label)


def click_tab(d, label):
    for b in d.find_elements(By.CSS_SELECTOR, "button[role='tab'], button"):
        if (b.text or '').strip() == label and b.is_displayed():
            L.js_click(d, b)
            time.sleep(1.5)
            return True
    raise RuntimeError('tab not found: ' + label)


def walk_stats(d, tag):
    """统计页实测一轮（当前主题），返回采集结果。"""
    L.reset_fetch_log(d)
    t0 = L.now_ms()
    d.get(L.BASE + '/report-statistics')
    WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
    # 等 case-averages 回包
    ca = []
    for _ in range(120):
        time.sleep(1)
        ca = reqs(d, '/reports/case-averages', since=t0, methods=('POST',))
        if ca:
            break
    time.sleep(6)
    res = {}
    res['theme'] = theme_state(d)
    res['cards'] = cards(d)
    res['rows_time'] = table_rows(d)
    res['case_avg_reqs'] = [
        {'status': c.get('status'), 'reqBody': c.get('reqBody'),
         'resHead': (c.get('resBody') or '')[:1200]} for c in ca[:2]
    ]
    res['list_reqs'] = [{k: e.get(k) for k in ('method', 'url', 'status')}
                        for e in reqs(d, '/reports?', since=t0, methods=('GET',))][:2]
    res['text_head'] = L.body(d)[:700]
    res['has_empty_text'] = ('暂无统计数据' in L.body(d))

    # 评估维度
    pick_dimension(d, '评估维度')
    time.sleep(4)
    res['cards_metric'] = cards(d)
    res['rows_metric'] = table_rows(d)
    res['text_metric_tail'] = L.body(d)[-800:]
    L.shot(d, 'e10_%s_stats_metric' % tag)
    res['shot_metric'] = os.path.join(L.ART, 'e10_%s_stats_metric.png' % tag)

    # 统计结果 → 图表（散点图）
    click_tab(d, '统计结果')
    click_tab(d, '图表')
    time.sleep(3)
    res['chart_text'] = L.body(d)[-800:]
    res['chart_canvas'] = canvases(d)
    res['chart_has_empty'] = '暂无数据' in L.body(d)
    L.shot(d, 'e11_%s_stats_chart' % tag)
    res['shot_chart'] = os.path.join(L.ART, 'e11_%s_stats_chart.png' % tag)

    # 热力图
    for b in d.find_elements(By.CSS_SELECTOR, "button"):
        if (b.text or '').strip() == '热力图' and b.is_displayed():
            L.js_click(d, b)
            break
    time.sleep(3)
    res['heatmap_text'] = L.body(d)[-600:]
    res['heatmap_canvas'] = canvases(d)
    res['heatmap_has_matrix'] = '设备 × 评估维度 值矩阵' in L.body(d)
    res['heatmap_has_empty'] = '暂无数据' in L.body(d)
    L.shot(d, 'e12_%s_stats_heatmap' % tag)
    res['shot_heatmap'] = os.path.join(L.ART, 'e12_%s_stats_heatmap.png' % tag)
    return res


def stats_light(d):
    r = walk_stats(d, 'light')
    OUT['light'] = r
    if r['theme']['dark']:
        raise RuntimeError('light expected, got dark: %s' % r['theme'])


def stats_dark(d):
    L.apply_theme(d, 'dark')
    r = walk_stats(d, 'dark')
    OUT['dark'] = r
    if not r['theme']['dark']:
        raise RuntimeError('dark missing: %s' % r['theme'])
    if r['theme']['bg'] != 'rgb(19, 29, 46)':
        raise RuntimeError('dark body bg unexpected: %s' % r['theme']['bg'])


def fixture(d):
    L.reset_fetch_log(d)
    r = L.api(d, '/reports/generate-task', 'POST',
              {'task_id': 411, 'name': FIXTURE_NAME}, timeout=180)
    j = r.get('json') or {}
    OUT['gen_http'] = r['status']
    OUT['gen_body'] = j
    rid = None
    if isinstance(j.get('report_id'), int):
        rid = j['report_id']
    if isinstance(j.get('id'), int):
        rid = j['id']
    deadline = time.time() + 180
    while time.time() < deadline:
        lr = L.api(d, '/reports?page=1&per_page=10&sort_by=created_at&order=desc'
                      '&deleted=false&favorite=false')
        items = (((lr.get('json') or {}).get('data') or {}).get('items') or [])
        hit = [i for i in items if i.get('task_id') == 411
               and FIXTURE_NAME in (i.get('name') or '')]
        if hit:
            rid = hit[0]['id']
            OUT['fixture_row'] = {k: hit[0].get(k) for k in
                                  ('id', 'name', 'task_id', 'task_name', 'status', 'created_at')}
            break
        time.sleep(3)
    if not rid:
        raise RuntimeError('fixture report not found; gen=%s' % OUT.get('gen_body'))
    OUT['fixture_id'] = rid
    OUT['created'] = [rid]
    rr = L.api(d, '/reports/%d' % rid)
    dj = ((rr.get('json') or {}).get('data') or {})
    OUT['fixture_detail'] = {'http': rr['status'], 'task_id': dj.get('task_id'),
                             'task_name': dj.get('task_name'), 'status': dj.get('status'),
                             'name': dj.get('name')}
    # 列表首行必须是夹具（统计页取列表首个 task_report）
    lr = L.api(d, '/reports?page=1&per_page=5&sort_by=created_at&order=desc'
                  '&deleted=false&favorite=false')
    items = (((lr.get('json') or {}).get('data') or {}).get('items') or [])
    OUT['list_head'] = [{'id': i.get('id'), 'task_id': i.get('task_id'),
                         'task_name': i.get('task_name'), 'created_at': i.get('created_at')}
                        for i in items[:3]]


def main():
    d = L.driver()
    try:
        L.login(d)
        OUT['env_base'] = L.BASE
        OUT['env_backend'] = L.BACKEND

        # ── A. 自建统计页夹具报告（任务 411）；mode=dark/light 时复用已有夹具
        mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
        if mode in ('all', 'light'):
            section('fixture', lambda: fixture(d))

        # ── B/C. 统计页浅色 + 深色
        if mode in ('all', 'light'):
            section('stats_light', lambda: stats_light(d))
        if mode in ('all', 'dark'):
            section('stats_dark', lambda: stats_dark(d))
        L.apply_theme(d, 'light')
    finally:
        save()
        d.quit()
    print('DONE fixture_id=%s' % OUT.get('fixture_id'))


if __name__ == '__main__':
    main()
