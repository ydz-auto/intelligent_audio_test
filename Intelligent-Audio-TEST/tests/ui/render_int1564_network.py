# -*- coding: utf-8 -*-
"""INT-1564 Network 证据图：把实测采集的请求-响应渲染成 PNG。"""
import base64
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

sys.stdout.reconfigure(encoding='utf-8')

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1564')

TEMPLATE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<style>
 body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background:#0f172a; color:#e2e8f0; padding:24px; }}
 h1 {{ font-size:20px; margin:0 0 6px; }}
 h2 {{ font-size:15px; margin:22px 0 8px; color:#7dd3fc; }}
 .meta {{ color:#94a3b8; font-size:12px; margin-bottom:12px; }}
 table {{ width:100%; border-collapse:collapse; font-size:12px; }}
 th,td {{ border:1px solid #1e293b; padding:6px 8px; vertical-align:top; text-align:left; }}
 th {{ background:#111827; color:#cbd5e1; }}
 code {{ font-family: Consolas, monospace; font-size:11px; word-break:break-all; }}
 .ok {{ color:#34d399; font-weight:600; }}
 .bad {{ color:#f87171; font-weight:600; }}
 .none {{ color:#fbbf24; font-weight:600; }}
 .tag {{ display:inline-block; padding:1px 6px; border-radius:4px; background:#1e293b; color:#93c5fd; font-size:11px; }}
</style></head><body>
<h1>INT-1564 OAuth 新建弹窗校验 Network 证据</h1>
<div class="meta">docker 网关 localhost:15000 · React dev server :5364 · 采集：页面 fetch 打点（window.fetch 包装）</div>
{sections}
</body></html>"""

ROW = """<tr><td><span class="tag">{method}</span></td><td><code>{url}</code></td>
<td class="{cls}">{status}</td><td><code>{req}</code></td><td><code>{resp}</code></td></tr>"""


def esc(text):
    if text is None:
        return ''
    text = str(text)
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))[:700]


def section(title, note, steps):
    rows = []
    for step in steps:
        for item in step.get('requests') or []:
            status = item.get('status')
            cls = 'ok' if status and status < 300 else 'bad'
            rows.append(ROW.format(
                method=esc(item.get('method')), url=esc(item.get('url')),
                status=esc(status), cls=cls,
                req=esc(item.get('req') or ''), resp=esc(item.get('resp') or '')))
        if 'posted' in step and not step.get('requests'):
            rows.append(ROW.format(
                method='—', url=esc(step.get('name')), status='未发出请求',
                cls='none', req=esc('前端校验拦截（posted=%s）' % step.get('posted')), resp=''))
    return ('<h2>%s</h2><div class="meta">%s</div>'
            '<table><tr><th>方法</th><th>URL</th><th>状态</th><th>请求体</th><th>响应体</th></tr>'
            % (esc(title), esc(note)) + ''.join(rows) + '</table>')


def _driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--window-size=1700,1200')
    return webdriver.Chrome(options=o)


def main():
    data = json.load(open(os.path.join(ART, 'verify_int1564.json'), encoding='utf-8'))
    steps = data['steps']
    blocked = [s for s in steps if 'posted' in s]
    written = [s for s in steps if s.get('requests')]
    html = TEMPLATE.format(sections=(
        section('① 前端校验拦截：不发出请求',
                '空 Client Secret / 空授权端点 / Slug 非法值三种提交均被前端拦下，window.__net 中无 POST /auth/oauth-providers。',
                blocked)
        + section('② 创建 / 编辑 / 后端拒绝：真实请求-响应',
                  '合法提交 POST 201（provider_id 落库）；编辑态空 secret 的 PUT 请求体不含 client_secret；'
                  '重复 slug 的 POST 400 且前端 toast 展示后端 message 原文。',
                  written)
    ))
    out_html = os.path.join(ART, 'network_evidence.html')
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    drv = _driver()
    try:
        drv.get('file:///' + out_html.replace('\\', '/'))
        time.sleep(1.5)
        drv.set_window_size(1700, 1400)
        time.sleep(0.5)
        shot = drv.execute_cdp_cmd('Page.captureScreenshot', {
            'format': 'png', 'captureBeyondViewport': True})
        png = os.path.join(ART, 'network_evidence.png')
        with open(png, 'wb') as f:
            f.write(base64.b64decode(shot['data']))
        print('saved', png)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
