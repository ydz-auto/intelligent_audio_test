# -*- coding: utf-8 -*-
"""INT-2213 验收补充：窗口化 DOM 规模 + 维度参数请求数 + 浅/深色与 Network 取证。

用法：python _int2213_verify.py --base http://localhost:5345 --algo 接线测试_2213_性能1192
复用 _int2121_scroll_audit.py 的登录/打开编辑 Sheet/采帧工具。
"""
import argparse
import importlib.util
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2213', 'verify')
os.makedirs(ART, exist_ok=True)

spec = importlib.util.spec_from_file_location('sa', os.path.join(HERE, '_int2121_scroll_audit.py'))
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)

STATS = r"""
const t = window.__evalTable;
const trs = [...t.querySelectorAll('tbody tr')];
const byKind = k => trs.filter(tr => tr.getAttribute('data-vkind') === k);
const form = document.querySelector('#algorithm-mutate-form');
return {
  tbody_trs: trs.length,
  headers: byKind('header').length,
  rows: byKind('row').length,
  add_rows: byKind('add').length,
  spacers: byKind('spacer').length,
  all_trs: document.querySelectorAll('tr').length,
  nodes: document.querySelectorAll('*').length,
  select_triggers: document.querySelectorAll('[data-slot="select-trigger"]').length,
  scrollTop: form ? Math.round(form.scrollTop) : null,
  scrollHeight: form ? form.scrollHeight : null,
};
"""

SCROLL_FORM = r"""
const form = document.querySelector('#algorithm-mutate-form');
form.scrollTop = arguments[0];
return Math.round(form.scrollTop);
"""

NET_JS = r"""
return [...document.querySelectorAll('tbody tr[data-vkind="row"]')].length;
"""


def collect_net(d):
    urls = []
    try:
        for e in d.get_log('performance'):
            m = json.loads(e['message'])['message']
            if m.get('method') == 'Network.responseReceived':
                u = m['params']['response']['url']
                if '/api/' in u:
                    urls.append({'url': u.split('?')[0], 'status': m['params']['response']['status']})
    except Exception as ex:
        return {'err': str(ex)}
    uniq, seen = [], set()
    for u in urls:
        k = (u['url'], u['status'])
        if k not in seen:
            seen.add(k)
            uniq.append(u)
    return uniq


def net_screenshot(d, entries, path):
    rows = ''.join(
        f"<tr><td>{i+1}</td><td>{e['status']}</td><td>{e['url']}</td></tr>"
        for i, e in enumerate(entries)
    )
    html = (
        "<html><head><meta charset='utf-8'><style>"
        "body{font:13px/1.5 'Segoe UI',sans-serif;padding:16px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:3px 6px}"
        "td:nth-child(1){width:42px}td:nth-child(2){width:52px}"
        "</style></head><body>"
        f"<h3>INT-2213 Network 取证：{d.execute_script('return location.origin')} · 共 {len(entries)} 个 /api 请求</h3>"
        "<table><tr><th>#</th><th>状态</th><th>URL</th></tr>" + rows + "</table></body></html>"
    )
    d.execute_script("document.open();document.write(arguments[0]);document.close();", html)
    time.sleep(0.5)
    d.save_screenshot(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5345')
    ap.add_argument('--algo', default='接线测试_2213_性能1192')
    a = ap.parse_args()
    sa.ALGO = a.algo
    out = {'base': a.base, 'algo': a.algo}

    d = sa.make_driver(log_perf=True)
    try:
        sa.login(d, a.base)
        # 打开编辑 Sheet（含展开高级配置与评估参数映射）
        t0 = time.time()
        sa.open_edit_sheet(d, a.base)
        time.sleep(3)
        net_open = collect_net(d)
        out['open_seconds'] = round(time.time() - t0, 1)
        out['net_on_open'] = net_open
        out['dim_param_reqs_on_open'] = sum(1 for u in net_open if 'dimension-params' in u['url'])

        d.execute_script(sa.SCROLL_TO_TABLE_JS)
        time.sleep(1.0)
        out['stats_top'] = d.execute_script(STATS)
        d.save_screenshot(os.path.join(ART, 'mapping-group-top-light.png'))

        d.execute_script(SCROLL_FORM, 8000)
        time.sleep(1.2)
        out['stats_mid'] = d.execute_script(STATS)
        d.save_screenshot(os.path.join(ART, 'mapping-group-mid-light.png'))

        d.execute_script(SCROLL_FORM, 60000)
        time.sleep(1.2)
        out['stats_deep'] = d.execute_script(STATS)
        d.save_screenshot(os.path.join(ART, 'mapping-group-deep-light.png'))

        out['rows_rendered_deep'] = d.execute_script(NET_JS)

        # 深色
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.get('about:blank')
        time.sleep(0.4)
        sa.open_edit_sheet(d, a.base)
        time.sleep(2)
        out['dark_active'] = d.execute_script(
            "return document.documentElement.className.includes('dark')")
        d.execute_script(sa.SCROLL_TO_TABLE_JS)
        time.sleep(1.0)
        d.save_screenshot(os.path.join(ART, 'mapping-group-top-dark.png'))
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

        net_all = collect_net(d)
        out['dim_param_reqs_total_session'] = sum(1 for u in net_all if 'dimension-params' in u['url'])
        net_screenshot(d, net_all, os.path.join(ART, 'network-log.png'))
        out['network'] = net_all
    finally:
        d.quit()

    with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    brief = {k: v for k, v in out.items() if k != 'network'}
    print(json.dumps(brief, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
