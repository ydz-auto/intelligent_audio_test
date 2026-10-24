# -*- coding: utf-8 -*-
"""INT-1479 第二轮：页面结构探针（CDP）。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cdp1479 import CDP  # noqa: E402

BASE = 'http://127.0.0.1:15173/audio-import'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')


def cdp():
    pages = [t for t in requests.get('http://127.0.0.1:9222/json/list', timeout=10).json()
             if t.get('type') == 'page']
    c = CDP(pages[0]['webSocketDebuggerUrl'], timeout=60)
    c.send('Page.enable'); c.send('Runtime.enable'); c.send('Network.enable')
    return c


def wait_page(c, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        t = c.eval("(document.body && document.body.innerText) || ''") or ''
        rows = c.eval("document.querySelectorAll('tbody tr').length") or 0
        if '音频管理' in t and rows > 0:
            return True, rows
        time.sleep(3)
    return False, 0


if __name__ == '__main__':
    c = cdp()
    c.send('Page.navigate', {'url': BASE})
    ok, rows = wait_page(c)
    print('page ok', ok, 'rows', rows)
    print('url', c.eval('location.href'))
    print('title', c.eval('document.title'))
    txt = c.eval("(document.body.innerText||'').slice(0,1500)")
    print('--- body text ---')
    print(txt)
    btns = c.eval("""
      Array.from(document.querySelectorAll('button,[role=button],[role=combobox]'))
        .map(b => (b.getAttribute('aria-label')||b.innerText||'').trim().replace(/\\s+/g,' '))
        .filter(Boolean).slice(0,80)
    """)
    print('--- buttons ---')
    print(json.dumps(btns, ensure_ascii=False, indent=1))
    os.makedirs(OUT, exist_ok=True)
    c.screenshot(os.path.join(OUT, 'r2-00-page.png'))
    print('shot ok')
