# -*- coding: utf-8 -*-
"""INT-1829 验收脚本：统计报表页「热力图」整页 500（ReportChart 漏注册 MatrixElement）。

同一脚本双跑对照（A/B）：
- 修复侧：本 run 用交付 diff（d67f0929f）打补丁后 pnpm build 的 dist 起的旁路 nginx 容器（--base http://127.0.0.1:15289）
- 基线侧：共享 15173 旧镜像（不含本卡改动，--base http://127.0.0.1:15173）

检查项（每主题浅/深各一遍）：
1. /report-statistics → 「统计结果」→「图表」→ 散点图正常（回归面）；
2. 同页点「热力图」：不出现错误边界「糟糕！出错了」，出现标题「设备 × 评估维度 值矩阵」
   + 副标题「密度分布：颜色越深值越高」，canvas 有绘制像素（修复侧）；基线侧应崩溃。
3. 「趋势分析」→「趋势图表」→「热力图」同一检查。
4. 附带：console SEVERE 日志、performance log 里 reports / tab-counts / case-averages 的 HTTP 状态。

用法：
    python tests/ui/verify_int1829_heatmap.py --label fix --base http://127.0.0.1:15289 --out <dir>
    python tests/ui/verify_int1829_heatmap.py --label baseline --base http://127.0.0.1:15173 --out <dir>
环境变量：CHROMEDRIVER（默认本机证书缓存驱动）。
"""
import argparse
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'

HEATMAP_TITLE = '设备 × 评估维度 值矩阵'
HEATMAP_SUBTITLE = '密度分布：颜色越深值越高'

CLICK_JS = r"""
const txt = String(arguments[0] || '').replace(/\s+/g, ' ').trim();
const sel = arguments[1] || 'button,[role=tab],[role=radio]';
const els = Array.from(document.querySelectorAll(sel));
let el = els.find(function (e) { return (e.innerText || '').replace(/\s+/g, ' ').trim() === txt; });
if (!el) el = els.find(function (e) { return (e.innerText || '').indexOf(txt) >= 0; });
if (!el) return null;
el.scrollIntoView({ block: 'center' });
el.click();
return el.tagName + '|' + (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 40);
"""

STATE_JS = r"""
const txt = (document.body ? document.body.innerText : '');
const canvases = Array.from(document.querySelectorAll('canvas')).map(function (c) {
  let painted = 0;
  try {
    const ctx = c.getContext('2d');
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    for (let i = 3; i < d.length; i += 4) { if (d[i] > 0) painted++; }
  } catch (e) {}
  return { w: c.width, h: c.height, painted: painted };
});
return {
  errorBoundary: txt.indexOf('\u7cdf\u7cd5\uff01\u51fa\u9519\u4e86') >= 0,
  hasHeatTitle: txt.indexOf('\u8bbe\u5907 \u00d7 \u8bc4\u4f30\u7ef4\u5ea6 \u503c\u77e9\u9635') >= 0,
  hasHeatSubtitle: txt.indexOf('\u5bc6\u5ea6\u5206\u5e03\uff1a\u989c\u8272\u8d8a\u6df1\u503c\u8d8a\u9ad8') >= 0,
  hasChartGroup: !!document.querySelector('[role="group"][aria-label="\u7edf\u8ba1\u56fe\u8868\u7c7b\u578b"]'),
  hasDarkClass: document.documentElement.classList.contains('dark'),
  canvases: canvases,
  textHead: txt.replace(/\s+/g, ' ').slice(0, 600)
};
"""


def build_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1200')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    opts.set_capability('pageLoadStrategy', 'eager')
    exe = os.environ.get('CHROMEDRIVER', DEFAULT_DRIVER)
    if not os.path.isfile(exe):
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
        versions = sorted(os.listdir(cache)) if os.path.isdir(cache) else []
        exe = os.path.join(cache, versions[-1], 'chromedriver.exe') if versions else None
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(service=srv, options=opts)
    drv.set_script_timeout(120)
    drv.set_page_load_timeout(180)
    return drv


def wait_for(drv, js, pred, timeout=90.0, step=0.4, arg=None):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = drv.execute_script(js, arg) if arg is not None else drv.execute_script(js)
        except Exception:
            last = None
        if pred(last):
            return last
        time.sleep(step)
    return last


def click_text(drv, text, sel=None):
    return drv.execute_script(CLICK_JS, text, sel)


def drain_perf(drv, rows):
    try:
        entries = drv.get_log('performance')
    except Exception:
        return
    for entry in entries:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg.get('params', {}).get('response', {})
        url = resp.get('url', '')
        if not any(k in url for k in ('/api/v1/reports', '/api/v1/health')):
            continue
        rows.append({'url': url.split('?')[0], 'status': resp.get('status'), 'type': resp.get('mimeType')})


def console_entries(drv):
    try:
        logs = drv.get_log('browser')
    except Exception:
        return []
    return [{'level': e.get('level'), 'message': (e.get('message') or '')[:300]} for e in logs
            if e.get('level') in ('SEVERE', 'WARNING')]


def run_theme(drv, base, theme, out_dir, label):
    os.makedirs(out_dir, exist_ok=True)
    res = {'label': label, 'base': base, 'theme': theme}
    drv.get(base + '/')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    drv.execute_script("localStorage.setItem('iatp:theme:mode', arguments[0]);", theme)
    try:
        drv.get_log('performance')
        drv.get_log('browser')
    except Exception:
        pass

    drv.get('%s/report-statistics?INT1829=%d' % (base, int(time.time())))
    tabs = wait_for(drv, "return document.querySelectorAll('[role=tab]').length;", lambda v: (v or 0) >= 3, 120)
    res['tabs_found'] = tabs

    res['click_result_tab'] = click_text(drv, '统计结果')
    time.sleep(1.0)
    res['click_chart_subtab'] = click_text(drv, '图表')
    got_group = wait_for(drv, "return !!document.querySelector('[role=\"group\"][aria-label=\"统计图表类型\"]');",
                         lambda v: bool(v), 60)
    res['chart_group_visible'] = bool(got_group)

    # 1) 散点图（回归面）
    res['click_scatter'] = click_text(drv, '散点图')
    time.sleep(2.0)
    res['scatter_state'] = drv.execute_script(STATE_JS)
    drv.save_screenshot(os.path.join(out_dir, 'scatter_%s_%s.png' % (label, theme)))

    # 2) 热力图 —— 崩溃点
    res['click_heatmap'] = click_text(drv, '热力图')
    time.sleep(3.0)
    res['heatmap_state'] = drv.execute_script(STATE_JS)
    drv.save_screenshot(os.path.join(out_dir, 'heatmap_%s_%s.png' % (label, theme)))

    if res['heatmap_state'].get('errorBoundary'):
        res['console'] = console_entries(drv)
        drain_perf(drv, res.setdefault('network', []))
        return res  # 崩溃后页面已不可恢复，趋势分析同组件无用例可跑

    # 3) 趋势分析 → 趋势图表 → 热力图
    res['click_trend_tab'] = click_text(drv, '趋势分析')
    time.sleep(1.0)
    res['click_trend_chart'] = click_text(drv, '趋势图表')
    got_group2 = wait_for(drv, "return !!document.querySelector('[role=\"group\"][aria-label=\"统计图表类型\"]');",
                          lambda v: bool(v), 60)
    res['trend_chart_group_visible'] = bool(got_group2)
    res['click_trend_heatmap'] = click_text(drv, '热力图')
    time.sleep(3.0)
    res['trend_heatmap_state'] = drv.execute_script(STATE_JS)
    drv.save_screenshot(os.path.join(out_dir, 'trend_heatmap_%s_%s.png' % (label, theme)))

    # 证据：热力图接口（页内 fetch，带 cookie）
    res['case_avg_fetch'] = drv.execute_async_script(r"""
        const done = arguments[arguments.length - 1];
        fetch('/api/v1/reports?page=1&per_page=3&sort_by=created_at&order=desc&deleted=false', { credentials: 'include' })
          .then(function (r) { return r.text().then(function (b) { done({ status: r.status, body: b.slice(0, 400) }); }); })
          .catch(function (e) { done({ status: null, body: String(e) }); });
    """)

    res['console'] = console_entries(drv)
    drain_perf(drv, res.setdefault('network', []))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--label', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--themes', default='light,dark')
    args = ap.parse_args()

    drv = build_driver()
    results = []
    try:
        for theme in [t.strip() for t in args.themes.split(',') if t.strip()]:
            results.append(run_theme(drv, args.base.rstrip('/'), theme, args.out, args.label))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    out_json = os.path.join(args.out, 'result_%s.json' % args.label)
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print('WROTE', out_json)


if __name__ == '__main__':
    main()
