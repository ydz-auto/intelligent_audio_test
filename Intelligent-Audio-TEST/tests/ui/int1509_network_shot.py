# -*- coding: utf-8 -*-
"""把 INT-1509 阶段 1 走查捕获的 Network 记录渲染成截图（性能日志取证）。

数据来源：accept.json 的 network_stage1_raw（Chrome performance log：
Network.requestWillBeSent / responseReceived），不伪造请求。
用法：python tests/ui/int1509_network_shot.py
"""
import html
import json
import os
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

ART = os.path.join('tests', 'ui', 'artifacts', 'int1509')
DRIVER = os.environ.get(
    'INT1509_DRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)

raw = json.load(open(os.path.join(ART, 'accept.json'), encoding='utf-8'))
entries = raw.get('network_stage1_raw') or []

rows = []
seen = {}
for e in entries:
    url = e['url']
    if e['kind'] == 'req':
        rec = seen.setdefault(url, {'method': e.get('method') or 'GET', 'status': '进行中'})
        rec['method'] = e.get('method') or 'GET'
    elif e['kind'] == 'resp':
        rec = seen.setdefault(url, {'method': 'GET', 'status': '进行中'})
        rec['status'] = e.get('status')
for url, info in seen.items():
    short = url.split('/api/v1')[-1]
    is_pick = 'pickable-tasks' in url
    is_cand = '/candidates' in url
    cls = 'pick' if is_pick else ('cand' if is_cand else '')
    rows.append(
        f"<tr class='{cls}'><td>{html.escape(info['method'])}</td>"
        f"<td class='u'>{html.escape(short[:170])}</td>"
        f"<td class='s'>{html.escape(str(info['status']))}</td>"
        f"<td>{'pickable-tasks（阶段 1 唯一数据源）' if is_pick else ('candidates（应为 0 条）' if is_cand else '')}</td></tr>"
    )

pick_n = sum(1 for u in seen if 'pickable-tasks' in u)
cand_n = sum(1 for u in seen if '/candidates' in u)
body = f"""
<html><head><meta charset='utf-8'><style>
body {{ font-family: 'Public Sans', 'Segoe UI', sans-serif; background:#fff; color:#111; margin:24px; }}
h1 {{ font-size:18px; margin:0 0 4px; }}
.meta {{ color:#555; font-size:12px; margin-bottom:14px; }}
table {{ border-collapse:collapse; width:100%; font-size:12px; }}
th,td {{ border-bottom:1px solid #e5e7eb; padding:7px 8px; text-align:left; vertical-align:top; }}
th {{ background:#f8fafc; color:#374151; font-weight:600; }}
td.u {{ font-family: 'JetBrains Mono', Consolas, monospace; color:#0f172a; word-break:break-all; }}
td.s {{ color:#047857; font-weight:600; }}
tr.pick {{ background:#ecfdf5; }}
tr.cand {{ background:#fef2f2; }}
.sum {{ margin-top:14px; font-size:13px; }}
b {{ color:#065f46; }}
</style></head><body>
<h1>INT-1509 阶段 1 · Network 取证（Chrome performance log）</h1>
<div class='meta'>页面：/tasks?tab=cherry-picks → 挑选向导阶段 1（浅色）；记录窗口：进入阶段 1 首屏 + 三次排序切换；来源：accept.json network_stage1_raw</div>
<table><thead><tr><th>方法</th><th>请求 URL（/api/v1 之后）</th><th>状态</th><th>说明</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<div class='sum'>合计：pickable-tasks 请求 <b>{pick_n}</b> 条（阶段 1 唯一数据源，page=1&amp;per_page=200&amp;sort_by/sort_order 由服务端排序）；
candidates 请求 <b>{cand_n}</b> 条（阶段 2 查询已门控到「下一步：选择结果」之后）。</div>
</body></html>
"""

os.environ.setdefault('SE_OFFLINE', 'true')
opts = webdriver.ChromeOptions()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1680,900')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-gpu')
d = webdriver.Chrome(service=Service(DRIVER), options=opts)
try:
    d.get('data:text/html;charset=utf-8,' + urllib.parse.quote(body))
    time.sleep(1)
    p = os.path.join(ART, 'p15_network_stage1.png')
    h = d.execute_script('return document.body.scrollHeight')
    d.set_window_size(1680, min(int(h) + 80, 2400))
    time.sleep(0.5)
    d.save_screenshot(p)
    print('saved', p, 'pick', pick_n, 'cand', cand_n)
finally:
    d.quit()
