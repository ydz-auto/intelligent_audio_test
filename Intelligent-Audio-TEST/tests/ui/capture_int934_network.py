# -*- coding: utf-8 -*-
"""INT-934 Network 证据截图：CDP performance log 提取 /reports/999999 请求+响应 → PNG。

用法：python capture_int934_network.py --base http://localhost:5310
输出：tests/ui/artifacts/int934_report_not_found/network_evidence.png
"""
import argparse
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int934_report_not_found')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5310')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    try:
        drv.set_page_load_timeout(45)
        # AUTH_MODE=off 会话引导 → 目标页
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.removeItem("iatp:theme:v1:mode")')
        drv.get(base + '/report/999999')
        time.sleep(8)
        # 等页面错误态文本（避免 GBK 打印，直接判断）
        assert '报告不存在' in (drv.page_source or ''), '报告不存在 not rendered'
        # 读取 performance log（双层嵌套解析，见 wiring-selenium-performance-log 记忆）
        reqs = {}
        for entry in drv.get_log('performance'):
            try:
                import json as _json
                msg = _json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                url = req.get('url') or ''
                if '/reports/999999' in url:
                    reqs[params.get('requestId')] = {
                        'method': req.get('method', 'GET'),
                        'url': url,
                        'status': None,
                    }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
        # 取一条请求的响应体
        body = ''
        for rid, info in reqs.items():
            try:
                r = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
                if r.get('base64Encoded'):
                    import base64
                    body = base64.b64decode(r.get('body', '')).decode('utf-8', 'replace')
                else:
                    body = r.get('body', '')
            except Exception:
                body = '(body unavailable)'
            if body:
                break
        evidence = []
        for rid, info in reqs.items():
            evidence.append('[Network] %s %s' % (info.get('method', 'GET'), info.get('url')))
            evidence.append('status: %s' % info.get('status'))
        evidence.append('response body: %s' % (body if body else '(unavailable)'))
        evidence.append('page rendered: 报告不存在 (not 加载失败)')
        evidence.append('verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
        text = '\n'.join(evidence)

        # 渲染 PNG（纯 ASCII，PIL 默认字体）
        from PIL import Image, ImageDraw, ImageFont
        try:
            font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
        except Exception:
            font = ImageFont.load_default()
        lines = text.split('\n')
        W, H = 1100, max(120, 40 * len(lines) + 40)
        img = Image.new('RGB', (W, H), (245, 245, 245))
        draw = ImageDraw.Draw(img)
        y = 12
        for ln in lines:
            draw.text((16, y), ln, fill=(20, 20, 20), font=font)
            y += 36
        out = os.path.join(ARTIFACTS, 'network_evidence.png')
        img.save(out)
        print('network evidence written:', out)
        print(text)
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
