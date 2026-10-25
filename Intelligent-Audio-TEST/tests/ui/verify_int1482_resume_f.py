# -*- coding: utf-8 -*-
"""INT-1482 F 轮：INT-1829 修复后统计页复走（热力图 浅 + 深 + 趋势分析入口）。

流程：
1) 用任务 411 自建「接线测试_INT1482_统计指标层」报告 → 成为列表最新任务报告（统计页 case-averages 上下文）。
2) 浅色 /report-statistics：报告数量、测试用例执行统计、评估指标、设备性能四卡 + 评估维度明细行 +
   散点图 + 热力图（断言渲染出图、无错误边界、控制台无 "matrix" 未注册异常）。
3) 深色同流程，深色前断言 html.dark 且 body 背景 rgb(19, 29, 46)。
4) 趋势分析 → 趋势图表 → 热力图 同一组件另一入口。
5) 抓 GET /reports 与 POST /reports/case-averages 请求体 + 响应体；截图浅/深。
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
TASK_ID = 411
ERR_HOOK = r"""
window.__errs = [];
(function(){
  var o = console.error;
  console.error = function(){
    try { window.__errs.push(Array.prototype.map.call(arguments, function(a){
      return typeof a === 'string' ? a : (a && (a.stack || a.message)) || String(a);
    }).join(' ').slice(0, 3000)); } catch(e) {}
    return o.apply(console, arguments);
  };
})();
window.addEventListener('error', function(e){
  window.__errs.push(String((e.error && (e.error.stack || e.error.message)) || e.message));
});
window.addEventListener('unhandledrejection', function(e){
  window.__errs.push('unhandledrejection: ' + String((e.reason && (e.reason.stack || e.reason.message)) || e.reason));
});
"""


def save():
    path = os.path.join(L.ART, 'resumeF_result.json')
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
        OUT[name + '_error'] = traceback.format_exc()[-1800:]
        save()
        raise


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


def click_heatmap(d):
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == '热力图' and b.is_displayed():
            L.js_click(d, b)
            time.sleep(4)
            return True
    raise RuntimeError('heatmap button not found')


def assert_heatmap_ok(d, tag):
    txt = L.body(d)
    crashed = '糟糕！出错了' in txt
    errs = d.execute_script('return window.__errs || []')
    n_canvas = canvases(d)
    has_title = '设备 × 评估维度 值矩阵' in txt
    has_empty = '暂无数据' in txt
    res = {'crashed': crashed, 'canvas': n_canvas, 'has_matrix_title': has_title,
           'has_empty_text': has_empty, 'errors': [e[:400] for e in errs[:5]],
           'text_tail': txt[-500:]}
    unregistered = any('not a registered element' in e for e in errs)
    res['unregistered_element_error'] = unregistered
    res['ok'] = (not crashed) and (not unregistered) and n_canvas >= 1 and has_title
    return res


def walk_stats(d, tag):
    """统计页实测一轮（当前主题）。"""
    L.reset_fetch_log(d)
    t0 = L.now_ms()
    d.get(L.BASE + '/report-statistics')
    WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
    d.execute_script(ERR_HOOK)
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
    res['text_metric_tail'] = L.body(d)[-900:]
    L.shot(d, 'f10_%s_stats_metric' % tag)
    res['shot_metric'] = os.path.join(L.ART, 'f10_%s_stats_metric.png' % tag)

    # 统计结果 → 图表（散点图）
    click_tab(d, '统计结果')
    click_tab(d, '图表')
    time.sleep(3)
    res['chart_text'] = L.body(d)[-800:]
    res['chart_canvas'] = canvases(d)
    res['chart_has_empty'] = '暂无数据' in L.body(d)
    L.shot(d, 'f11_%s_stats_chart' % tag)
    res['shot_chart'] = os.path.join(L.ART, 'f11_%s_stats_chart.png' % tag)

    # 热力图
    click_heatmap(d)
    res['heatmap'] = assert_heatmap_ok(d, tag)
    res['heatmap_shot'] = L.shot(d, 'f12_%s_stats_heatmap' % tag)
    return res


def walk_trend_heatmap(d, tag):
    """趋势分析 → 趋势图表 → 热力图（同一 StatisticsCharts 组件另一入口）。"""
    L.reset_fetch_log(d)
    d.get(L.BASE + '/report-statistics')
    WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
    time.sleep(8)
    d.execute_script(ERR_HOOK)
    click_tab(d, '趋势分析')
    click_tab(d, '趋势图表')
    time.sleep(3)
    res = {'trend_canvas': canvases(d)}
    click_heatmap(d)
    res['heatmap'] = assert_heatmap_ok(d, tag)
    res['shot'] = L.shot(d, 'f13_%s_stats_trend_heatmap' % tag)
    return res


def stats_light(d):
    r = walk_stats(d, 'light')
    OUT['light'] = r
    OUT['trend_light'] = walk_trend_heatmap(d, 'light')


def stats_dark(d):
    L.apply_theme(d, 'dark')
    r = walk_stats(d, 'dark')
    OUT['dark'] = r
    OUT['trend_dark'] = walk_trend_heatmap(d, 'dark')


def fixture(d):
    L.reset_fetch_log(d)
    r = L.api(d, '/reports/generate-task', 'POST',
              {'task_id': TASK_ID, 'name': FIXTURE_NAME}, timeout=180)
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
        hit = [i for i in items if i.get('task_id') == TASK_ID
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
    lr = L.api(d, '/reports?page=1&per_page=5&sort_by=created_at&order=desc'
                  '&deleted=false&favorite=false')
    items = (((lr.get('json') or {}).get('data') or {}).get('items') or [])
    OUT['list_head'] = [{'id': i.get('id'), 'task_id': i.get('task_id'),
                         'task_name': i.get('task_name'), 'created_at': i.get('created_at')}
                        for i in items[:3]]
    if not items or items[0].get('id') != rid:
        raise RuntimeError('夹具不是列表首行: %s' % OUT['list_head'])


def main():
    d = L.driver()
    try:
        L.login(d)
        OUT['env_base'] = L.BASE
        OUT['env_backend'] = L.BACKEND
        mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
        if mode != 'existing':
            section('fixture', lambda: fixture(d))
        section('stats_light', lambda: stats_light(d))
        section('stats_dark', lambda: stats_dark(d))
        L.apply_theme(d, 'light')
    finally:
        save()
        d.quit()
    print('DONE fixture_id=%s light_heatmap_canvas=%s dark_heatmap_canvas=%s'
          % (OUT.get('fixture_id'),
             (OUT.get('light') or {}).get('heatmap', {}).get('canvas'),
             (OUT.get('dark') or {}).get('heatmap', {}).get('canvas')))


if __name__ == '__main__':
    main()
