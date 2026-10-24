# -*- coding: utf-8 -*-
"""INT-1479 R4：CDP 会话封装（开放模式免登录；Docker SPA 冷启动较慢）。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cdp1479 import CDP  # noqa: E402

BASE = os.environ.get('INT1479_BASE', 'http://127.0.0.1:15173')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')


def connect(timeout=120):
    pages = [t for t in requests.get('http://127.0.0.1:9222/json/list', timeout=15).json()
             if t.get('type') == 'page']
    c = CDP(pages[0]['webSocketDebuggerUrl'], timeout=timeout)
    for m in ('Page.enable', 'Runtime.enable', 'Network.enable', 'DOM.enable'):
        c.send(m)
    return c


def nav(c, path, wait=5):
    try:
        c.send('Page.navigate', {'url': BASE + path}, )
    except TimeoutError:
        pass
    time.sleep(wait)
    # 有导航会丢连接上下文，忽略；后续 eval 会重试
    return True


def text(c):
    return c.eval("(document.body && document.body.innerText) || ''") or ''


def wait_ready(c, timeout=240):
    end = time.time() + timeout
    while time.time() < end:
        try:
            t = text(c)
            rows = c.eval("document.querySelectorAll('tbody tr').length") or 0
            if '音频管理' in t and rows > 0:
                return True
            if '进入工作台' in t:
                click(c, '进入工作台')
                time.sleep(3)
        except Exception:
            pass
        time.sleep(3)
    return False


def click(c, label, exact=True, scope=None):
    js = """
    (function(label, exact, scope){
      const root = scope ? document.querySelector(scope) : document;
      if (!root) return 'NO_SCOPE';
      const nodes = Array.from(root.querySelectorAll('button,[role=menuitem],[role=option],[role=tab],a,label'));
      const el = nodes.find(n => (n.textContent||'').trim() === label) ||
                 (!exact && nodes.find(n => (n.textContent||'').includes(label)));
      if (!el) return 'NOT_FOUND:' + label;
      el.click();
      return 'CLICKED:' + label;
    })(%s, %s, %s)
    """
    return c.eval(js % (json.dumps(label), 'true' if exact else 'false',
                        json.dumps(scope) if scope else 'null'))


def shot(c, name):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name + '.png')
    c.screenshot(p)
    return p


def net_since(c, idx):
    reqs, resps = [], []
    for e in c.events[idx:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                reqs.append({'m': r['method'], 'u': r['url'].split('?')[0],
                             'body': (r.get('postData') or '')[:800]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                resps.append({'status': r['status'], 'u': r['url'].split('?')[0]})
    return reqs, resps


def set_theme(c, theme):
    c.eval("localStorage.setItem('iatp:theme:v1:mode', %s)" % json.dumps(theme))
