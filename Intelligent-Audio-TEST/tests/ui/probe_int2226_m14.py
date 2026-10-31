# -*- coding: utf-8 -*-
"""INT-2226 M14 探针：三端用例页（8080 旧 Vue / 15173 React / 16173 新 Vue）结构取样。

只读探针：登录后打开用例页，导出可见按钮 / 输入框 / 表头文本与真实 API 请求，
用于写交互脚本前对准选择器。不写业务数据。
"""
import argparse
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2226')
os.makedirs(ART, exist_ok=True)

FRONTS = {
    'react': 'http://localhost:15173',
    'uxvue': 'http://localhost:16173',
    'vue': 'http://localhost:8080',
}


def dump(page, tag):
    data = page.evaluate("""() => {
      const vis = el => { const r = el.getBoundingClientRect();
        return r.width > 4 && r.height > 4 && getComputedStyle(el).visibility !== 'hidden' &&
               getComputedStyle(el).display !== 'none'; };
      const out = {url: location.href, title: document.title};
      out.buttons = [...document.querySelectorAll('button')].filter(vis)
        .map(b => ({t: (b.innerText || b.textContent || '').trim().slice(0, 30),
                    cls: (b.className || '').toString().slice(0, 80)})).filter(x => x.t);
      out.inputs = [...document.querySelectorAll('input')].filter(vis)
        .map(i => ({type: i.type, ph: i.placeholder, cls: (i.className||'').toString().slice(0,60)}));
      out.selects = [...document.querySelectorAll('select')].filter(vis)
        .map(s => ({cls: (s.className||'').toString().slice(0,60),
                    opts: [...s.options].map(o => o.text).slice(0, 12)}));
      out.headers = [...document.querySelectorAll('th')].filter(vis).map(t => (t.innerText||'').trim());
      out.labels = [...document.querySelectorAll('a')].filter(vis)
        .map(a => ({t: (a.innerText||'').trim().slice(0,20), h: a.getAttribute('href')}))
        .filter(x => x.t && x.h).slice(0, 40);
      out.head = (document.body.innerText || '').slice(0, 600);
      return out;
    }""")
    print('==== %s ====' % tag, flush=True)
    print(json.dumps(data, ensure_ascii=False, indent=1), flush=True)
    return data


def login(page, base, user, pwd, hash_route=False):
    login_path = '/#/login' if hash_route else '/login'
    page.goto(base + login_path, wait_until='domcontentloaded')
    time.sleep(3)
    page.locator('input[type=password]').first.fill(pwd)
    texts = page.locator('input[type=text], input:not([type])')
    texts.first.fill(user)
    btns = page.get_by_role('button', name=re.compile('登\\s*录|登录'))
    if btns.count():
        btns.first.click()
    else:
        page.locator('button[type=submit]').first.click()
    page.wait_for_function("() => !/login/i.test(location.href)", timeout=45000)
    time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--front', required=True, choices=list(FRONTS))
    ap.add_argument('--path', default='')
    ap.add_argument('--hash', action='store_true', help='前端为 hash 路由（新Vue/旧Vue）')
    args = ap.parse_args()
    base = FRONTS[args.front]
    hash_route = args.hash or args.front in ('uxvue', 'vue')
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 900})
        page = ctx.new_page()
        reqs = []
        page.on('request', lambda r: reqs.append(r.url) if '/api/' in r.url else None)
        login(page, base, 'dev_user', 'dev_password', hash_route)
        print('after login:', page.url, flush=True)
        dump(page, args.front + ' after-login')
        if args.path:
            page.goto(base + args.path, wait_until='domcontentloaded')
            time.sleep(5)
            dump(page, args.front + ' ' + args.path)
        print('API REQS:', json.dumps(sorted(set(reqs)), ensure_ascii=False, indent=1), flush=True)
        page.screenshot(path=os.path.join(ART, 'probe_%s.png' % args.front))
        b.close()


if __name__ == '__main__':
    main()
