# -*- coding: utf-8 -*-
"""INT-1479 通用 CDP 驱动（按 argv 提供的小 DSL 执行，便于逐窗试探）。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cdp1479 import CDP  # noqa: E402

BASE = 'http://127.0.0.1:15173/audio-import'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
CLICK_JS = """
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


def cdp():
    pages = [t for t in requests.get('http://127.0.0.1:9222/json/list', timeout=10).json()
             if t.get('type') == 'page']
    c = CDP(pages[0]['webSocketDebuggerUrl'], timeout=60)
    c.send('Page.enable'); c.send('Runtime.enable'); c.send('Network.enable'); c.send('DOM.enable')
    return c


def wait_page(c, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        t = c.eval("(document.body && document.body.innerText) || ''") or ''
        rows = c.eval("document.querySelectorAll('tbody tr').length") or 0
        if '音频管理' in t and rows > 0:
            return True
        time.sleep(2)
    return False


def click(c, label, exact=True, scope=None):
    return c.eval(CLICK_JS % (json.dumps(label), 'true' if exact else 'false',
                              json.dumps(scope) if scope else 'null'))


def dialog(c):
    return c.eval("""
      (function(){
        const d = document.querySelector('[role=dialog],[role=alertdialog]');
        if (!d) return null;
        const items = Array.from(d.querySelectorAll('input,textarea,select,button,[role=combobox],[role=checkbox],[role=switch],[role=radio]'))
          .map((e,i) => ({i, tag:e.tagName.toLowerCase(), type:e.type||'', role:e.getAttribute('role')||'',
                          name:e.getAttribute('name')||'', ph:e.getAttribute('placeholder')||'',
                          aria:e.getAttribute('aria-label')||'', text:(e.innerText||'').trim().slice(0,40),
                          value:(e.value===undefined?'':String(e.value)).slice(0,60),
                          checked:e.checked===undefined?'':e.checked}));
        return {title:(d.innerText||'').split('\\n').slice(0,6), items};
      })()
    """)


def shot(c, name):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name + '.png')
    c.screenshot(p)
    return p


def requests_since(c, idx):
    out = []
    for e in c.events[idx:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                out.append({'m': r['method'], 'u': r['url'].split('?')[0],
                            'body': (r.get('postData') or '')[:600]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                out.append({'status': r['status'], 'u': r['url'].split('?')[0]})
    return out


def fmt(x):
    return json.dumps(x, ensure_ascii=False, indent=1)
