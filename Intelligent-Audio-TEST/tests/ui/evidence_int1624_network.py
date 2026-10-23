# -*- coding: utf-8 -*-
"""INT-1624 Network 证据图（导出 / 导入的真实请求 URL、状态码、关键响应头与响应体）。

做法：在页面内（同源，带 AUTH_MODE=off 的 dev_user 上下文）对被测页面正在调用的
同一 URL 发请求，记录状态码 / Content-Disposition / Content-Type / 响应体，
再渲染成证据图（Windows 无 DevTools 截图能力，用请求-响应原文代替网络面板截图）。
"""
import functools
import json
import os
import shutil
import sys
import time

from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

print = functools.partial(print, flush=True)  # noqa: A001
sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://127.0.0.1:15241'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1624_acc')


def driver():
    root = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64'
    cands = [(tuple(int(x) for x in v.split('.') if x.isdigit()),
              os.path.join(root, v, 'chromedriver.exe'))
             for v in os.listdir(root) if os.path.isfile(os.path.join(root, v, 'chromedriver.exe'))] if os.path.isdir(root) else []
    exe = max(cands)[1] if cands else ''
    profile = os.path.join(os.environ.get('TEMP', '.'), 'int1624net_chrome')
    shutil.rmtree(profile, ignore_errors=True)
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1080')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + profile)
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_script_timeout(300)
    return d


def render(name, title, lines):
    font = ImageFont.load_default()
    for fp in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf'):
        try:
            font = ImageFont.truetype(fp, 17)
            break
        except Exception:
            continue
    wrapped = []
    for line in lines:
        while len(line) > 78:
            wrapped.append(line[:78])
            line = line[78:]
        wrapped.append(line)
    W = 1120
    H = max(150, 32 * len(wrapped) + 90)
    img = Image.new('RGB', (W, H), (250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 46], fill=(32, 38, 52))
    f2 = font
    try:
        f2 = ImageFont.truetype(r'C:\Windows\Fonts\msyhbd.ttc', 20)
    except Exception:
        pass
    draw.text((16, 12), title, fill=(255, 255, 255), font=f2)
    y = 60
    for ln in wrapped:
        draw.text((16, y), ln, fill=(25, 25, 25) if not ln.startswith('FAIL') else (180, 0, 0), font=font)
        y += 30
    path = os.path.join(ART, name + '.png')
    img.save(path)
    print('EVIDENCE', path)
    return path


def main():
    d = driver()
    lines_export, lines_import = [], []
    try:
        d.get(BASE + '/devices/test')
        time.sleep(6)
        for fmt in ('json', 'excel'):
            info = d.execute_async_script("""
                const fmt = arguments[0], done = arguments[arguments.length-1];
                fetch('/api/v1/test-devices/export?format=' + fmt)
                  .then(async r => {
                    let size = -1;
                    try { size = (await r.blob()).size; } catch (e) {}
                    done({url: '/api/v1/test-devices/export?format=' + fmt,
                          status: r.status, size: size,
                          contentType: r.headers.get('content-type'),
                          disposition: r.headers.get('content-disposition')});
                  }).catch(e => done({error: String(e)}));
            """, fmt)
            lines_export.append('GET %s' % info.get('url'))
            lines_export.append('  ← HTTP %s   Content-Type: %s' % (info.get('status'), info.get('contentType')))
            lines_export.append('  ← Content-Disposition: %s' % info.get('disposition'))
            lines_export.append('  ← 文件字节数: %s' % info.get('size'))
            lines_export.append('')

        info = d.execute_async_script("""
            const done = arguments[arguments.length-1];
            const fd = new FormData();
            const doc = {test_devices: [{name: '接线测试_INT1624_NET', model: 'NET-Model',
              type: 'physical', system: 'Android', system_version: '14', app_name: 'iatp',
              app_version: '1.0', description: 'net-evidence', serial_number: 'JX1624NET01',
              status: 'offline'}]};
            fd.append('file', new File([JSON.stringify(doc)], 'net_evidence.json',
                                       {type: 'application/json'}));
            fetch('/api/v1/test-devices/import', {method: 'POST', body: fd})
              .then(async r => done({status: r.status, body: await r.text()}))
              .catch(e => done({error: String(e)}));
        """)
        lines_import.append('POST /api/v1/test-devices/import')
        lines_import.append('  Content-Type: multipart/form-data; field name=file, filename=net_evidence.json')
        lines_import.append('  → HTTP %s' % info.get('status'))
        try:
            pretty = json.dumps(json.loads(info.get('body') or '{}'), ensure_ascii=False, indent=2)
        except Exception:
            pretty = info.get('body') or ''
        lines_import += ['  ← ' + ln for ln in pretty.split('\n')]
    finally:
        try:
            d.quit()
        except Exception:
            pass

    render('network_export', 'INT-1624 Network 证据：导出（GET /test-devices/export）', lines_export)
    render('network_import', 'INT-1624 Network 证据：导入（POST /test-devices/import）', lines_import)

    # 清理证据请求产生的记录
    import requests
    r = requests.get('http://127.0.0.1:15000/api/v1/test-devices?page=1&per_page=1000', timeout=60).json()
    for it in ((r.get('data') or {}).get('items') or []):
        if str(it.get('name', '')).startswith('接线测试_INT1624'):
            print('clean', requests.delete('http://127.0.0.1:15000/api/v1/test-devices/%s' % it['id'], timeout=120).status_code)
    time.sleep(1)
    r = requests.get('http://127.0.0.1:15000/api/v1/test-devices?page=1&per_page=1000', timeout=60).json()
    left = [it['name'] for it in ((r.get('data') or {}).get('items') or [])
            if str(it.get('name', '')).startswith('接线测试')]
    print('left', left)


if __name__ == '__main__':
    main()
