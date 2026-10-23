# -*- coding: utf-8 -*-
"""INT-1502 Network 证据图：把两轮实测（真实栈 / 契约桩）的请求-响应渲染成 PNG。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1502_spl_test_tone import _driver  # noqa: E402

ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1502_spl_test_tone')

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
 .tag {{ display:inline-block; padding:1px 6px; border-radius:4px; background:#1e293b; color:#93c5fd; font-size:11px; }}
</style></head><body>
<h1>INT-1502 增益映射「播放测试音」Network 证据</h1>
<div class="meta">真实库 intelligent_audio_test · 前端 dev server 5352/5353 → 网关 5700 · 采集：CDP performance log</div>
{sections}
</body></html>"""

ROW = """<tr><td><span class="tag">{method}</span></td><td><code>{url}</code></td>
<td class="{cls}">{status}</td><td><code>{req}</code></td><td><code>{resp}</code></td></tr>"""


def esc(text):
    if text is None:
        return ''
    text = str(text)
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))[:900]


def section(title, note, evidence):
    rows = []
    for step in evidence['steps']:
        for key in ('device_get', 'test_tone', 'stop_requests'):
            for item in step.get(key) or []:
                status = item.get('status')
                cls = 'ok' if status == 200 else 'bad'
                rows.append(ROW.format(
                    method=esc(item.get('method')), url=esc(item.get('url')),
                    status=esc(status), cls=cls,
                    req=esc(item.get('postData') or ''),
                    resp=esc(item.get('body') or ''),
                ))
    return (f'<h2>{title}</h2><div class="meta">{note}</div>'
            '<table><tr><th>方法</th><th>URL</th><th>状态</th><th>请求体</th><th>响应体</th></tr>'
            + ''.join(rows) + '</table>')


def main():
    real = json.load(open(os.path.join(ARTIFACTS, 'evidence-real.json'), encoding='utf-8'))
    stub = json.load(open(os.path.join(ARTIFACTS, 'evidence-stub-run.json'), encoding='utf-8'))
    html = TEMPLATE.format(sections=(
        section('① 真实库栈 5700：选设备 → POST /spl/test-tone（真实后端）',
                'GET /playback-devices/{id} 200 取 device_unique_id；POST /spl/test-tone 请求体正确、'
                '后端因本机音频栈卡死（pyaudio shadow fixture）返回 400「没有找到可用的播放设备」→ 前端提示该 message 且不进入播放态。',
                real)
        + section('② 契约桩旁路 /spl/test-tone（仅此两端点，其余透传 5700 真实库）',
                  '验证播放成功态：200 → 播放中（aria-pressed=true）→ 点停止 / 关闭弹窗均发 POST /spl/test-tone/stop。',
                  stub)
    ))
    out_html = os.path.join(ARTIFACTS, 'network_evidence.html')
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    drv = _driver()
    try:
        drv.get('file:///' + out_html.replace('\\', '/'))
        import base64
        import time
        time.sleep(1.5)
        drv.set_window_size(1700, 1500)
        time.sleep(0.5)
        shot = drv.execute_cdp_cmd('Page.captureScreenshot', {
            'format': 'png', 'captureBeyondViewport': True})
        png = os.path.join(ARTIFACTS, 'network_evidence.png')
        with open(png, 'wb') as f:
            f.write(base64.b64decode(shot['data']))
        print('saved', png)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
