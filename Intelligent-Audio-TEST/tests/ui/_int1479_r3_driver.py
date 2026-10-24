# -*- coding: utf-8 -*-
"""INT-1479 第三轮 CDP 驱动：登录 + 页面结构探针。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cdp1479 import CDP  # noqa: E402

BASE = 'http://127.0.0.1:15173'
USER = '接线测试_admin'
PWD = 'JieXianTest@2026'


def connect():
    pages = [t for t in requests.get('http://127.0.0.1:9222/json/list', timeout=10).json()
             if t.get('type') == 'page']
    c = CDP(pages[0]['webSocketDebuggerUrl'], timeout=90)
    for m in ('Page.enable', 'Runtime.enable', 'Network.enable', 'DOM.enable'):
        c.send(m)
    return c


def goto(c, path, wait=3):
    c.send('Page.navigate', {'url': BASE + path})
    time.sleep(wait)


def text(c):
    return c.eval("(document.body && document.body.innerText) || ''")


def buttons(c, scope=None):
    js = ("(function(){const r=%s;return Array.from(r.querySelectorAll('button,[role=button],a'))"
          ".map(e=>({t:(e.innerText||'').trim().slice(0,30),aria:e.getAttribute('aria-label')||'',"
          "slot:e.getAttribute('data-slot')||'',dis:e.disabled}))})()"
          % (("document.querySelector(%s)" % json.dumps(scope)) if scope else 'document'))
    return c.eval(js)


def login(c):
    goto(c, '/login', 4)
    t = text(c)
    print('LOGIN PAGE:', t[:300])
    # 填表：首个 text input 用户名，password 输入密码
    c.eval("""
      (function(){
        const inputs = Array.from(document.querySelectorAll('input'));
        const u = inputs.find(i => i.type === 'text' || i.type === 'email');
        const p = inputs.find(i => i.type === 'password');
        if (!u || !p) return 'NO_INPUTS:' + inputs.map(i=>i.type).join(',');
        const set = (el, v) => {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, v);
          el.dispatchEvent(new Event('input', {bubbles:true}));
          el.dispatchEvent(new Event('change', {bubbles:true}));
        };
        set(u, %s); set(p, %s);
        return 'FILLED';
      })()
    """ % (json.dumps(USER), json.dumps(PWD)))
    time.sleep(0.5)
    print('SUBMIT:', c.eval("""
      (function(){
        const b = Array.from(document.querySelectorAll('button')).find(x => /登录|登 录|Sign in/i.test(x.innerText||''));
        if (!b) return 'NO_BTN';
        b.click(); return 'CLICKED';
      })()
    """))
    for _ in range(40):
        time.sleep(1)
        u = c.eval('location.pathname')
        if u and u not in ('/login', '/sign-in'):
            return u
    return 'STUCK:' + str(c.eval('location.pathname')) + ' ' + text(c)[:200]


if __name__ == '__main__':
    c = connect()
    print('PATH START:', c.eval('location.pathname'))
    print('LOGIN RESULT:', login(c))
    goto(c, '/audio-import', 6)
    for _ in range(30):
        t = text(c)
        if '音频管理' in t:
            break
        time.sleep(2)
    t = text(c)
    print('PAGE TEXT:', t[:1200])
    print('BUTTONS:', json.dumps(buttons(c), ensure_ascii=False, indent=1))
