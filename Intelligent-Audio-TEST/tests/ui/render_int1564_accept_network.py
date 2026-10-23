# -*- coding: utf-8 -*-
"""INT-1564 验收 Network 证据图（测试工程师独立验收采集数据 → PNG）。"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_int1564_network as R  # 复用模板/渲染器

sys.stdout.reconfigure(encoding='utf-8')

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1564_accept')


def main():
    data = json.load(open(os.path.join(ART, 'verify_int1564.json'), encoding='utf-8'))
    steps = data['steps']
    blocked = [s for s in steps if 'posted' in s]
    written = [s for s in steps if s.get('requests')]
    html = R.TEMPLATE.format(sections=(
        R.section('① 前端校验拦截：不发出请求（window.__net 无写请求）',
                  '空 Client Secret / 三端点分别留空 / Slug 四种非法值 —— 点「保存」后均无 POST，弹窗保持打开并给出字段级错误。',
                  blocked)
        + R.section('② 创建 / 编辑 / 后端拒绝：真实请求-响应',
                    '合法提交 POST 201（provider_id 落库）；编辑态空 secret 的 PUT 请求体不含 client_secret；'
                    '重复 slug 的 POST 409 且前端 toast 展示后端 message 原文。',
                    written)
    ))
    out_html = os.path.join(ART, 'network_evidence.html')
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    drv = R._driver()
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
