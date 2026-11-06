# -*- coding: utf-8 -*-
"""INT-2136 React(15173) 侧栏逐页走查（docker 真实库栈，只读）。

INT-1919 五条链路覆盖登录/任务/用例/报告/开始测试；本脚本补全「前端各管理页
可达且主容器渲染」的面：登录态注入后读侧栏链接，逐条访问，记录
  - HTTP 状态（/api/v1 请求里 ≥400 的）
  - 页面可见正文长度 / page-title 文本
  - console SEVERE
并落截图与 JSON 汇总。

跑法（环境铁律：连 docker 栈，不启动本地栈）：
  <conda python> tests/ui/smoke_react_nav_walk_int2136.py --base http://localhost:15173 \
      --api http://localhost:15000
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui.utils.api_client import ApiClient  # noqa: E402
from tests.ui.smoke_frontend_int1854 import (  # noqa: E402
    CHROME_BINARY, body_text, console_errors, make_driver, parse_perf, shot, wait_quiet,
    RESULT, ART_ROOT,
)
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402


def nav_links(drv, base):
    links = drv.execute_script("""
      const out = [];
      for (const a of document.querySelectorAll('a[href]')) {
        const r = a.getBoundingClientRect();
        if (r.width < 10 || r.height < 5) continue;
        const t = (a.innerText || '').trim();
        out.push({href: a.getAttribute('href'), text: t.slice(0, 24)});
      }
      return out;
    """) or []
    seen, paths = set(), []
    for item in links:
        href = item.get('href') or ''
        if not href.startswith('/') or href.startswith('//'):
            continue
        if href in seen or href.startswith('/login') or href.startswith('/logout'):
            continue
        seen.add(href)
        paths.append((href, item.get('text') or ''))
    return paths


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default=os.environ.get('API_BASE', 'http://localhost:15000'))
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()

    base = args.base.rstrip('/')
    art = os.path.join(ART_ROOT, 'int2136_nav')
    os.makedirs(art, exist_ok=True)
    os.makedirs(os.path.join(art, 'downloads'), exist_ok=True)
    RESULT['art'] = art  # shot() 依赖 RESULT['art']（基类在 Smoke.__init__ 里设）

    client = ApiClient(args.api)
    client.login(args.username, args.password)  # 仅用于校验账号；页面走真实表单登录
    print('API login ok user=%s' % (client.user or {}).get('username'), flush=True)

    drv = make_driver(os.path.join(art, 'downloads'))
    pages = {}
    try:
        # 真实表单登录（localStorage 键为 iatp:auth:token:v1 / iatp:auth:v1，
        # 直接注入 shape 易漂移；走 UI 登录与 INT-1919 chain1 同口径）
        drv.get(base + '/login')
        WebDriverWait(drv, 45).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
        time.sleep(1)
        user_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
                       if e.is_displayed() and e.get_attribute('type') in (None, 'text', 'email')]
        pwd_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
                      if e.is_displayed()]
        user_inputs[0].send_keys(args.username)
        pwd_inputs[0].send_keys(args.password)
        btns = [b for b in drv.find_elements(By.TAG_NAME, 'button')
                if b.is_displayed() and (b.text or '').strip() in ('登 录', '登录')]
        (btns or drv.find_elements(By.CSS_SELECTOR, 'button[type=submit]'))[-1].click()
        WebDriverWait(drv, 45).until(lambda d: 'login' not in d.current_url.lower())
        time.sleep(4)
        drv.get(base + '/dashboard')
        time.sleep(4)
        wait_quiet(drv, 30)
        print('after login url=%s' % drv.current_url, flush=True)
        paths = nav_links(drv, base)
        print('NAV_LINKS=%d %s' % (len(paths), [p[0] for p in paths]), flush=True)
        for href, text in paths:
            rec = {'label': text, 'ok': False}
            try:
                drv.get(base + href)
                time.sleep(3.5)
                wait_quiet(drv, 25)
                txt = body_text(drv)
                apis = parse_perf(drv.get_log('performance'))
                bad = [a for a in apis if isinstance(a.get('status'), int) and a['status'] >= 400]
                titles = [el.text.strip() for el in drv.find_elements(By.CSS_SELECTOR, '.page-title')]
                h1 = [el.text.strip() for el in drv.find_elements(By.CSS_SELECTOR, 'h1')]
                rec.update({
                    'url': drv.current_url,
                    'body_len': len(txt),
                    'page_titles': titles[:3],
                    'h1': h1[:3],
                    'head': txt[:120],
                    'api_4xx5xx': [{'m': a.get('method'), 's': a.get('status'),
                                    'u': (a.get('url') or '')[:140]} for a in bad][:8],
                    'console': console_errors(drv)[:3],
                })
                rec['shot'] = shot(drv, 'nav_%s' % href.strip('/').replace('/', '_') or 'home')['path']
                rec['ok'] = rec['body_len'] > 30 and not any(
                    a.get('status') and a['status'] >= 500 for a in bad)
            except Exception as exc:
                rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
            pages[href] = rec
            print('PAGE %-22s ok=%s len=%s 4xx5xx=%s' % (
                href, rec.get('ok'), rec.get('body_len'), len(rec.get('api_4xx5xx') or [])), flush=True)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    RESULT['nav_walk'] = pages
    out_path = os.path.join(art, 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(pages, fh, ensure_ascii=False, indent=2)
    print('\nSUMMARY_JSON=%s' % out_path)
    fails = {k: v for k, v in pages.items() if not v.get('ok')}
    print('PAGES=%d FAIL=%d' % (len(pages), len(fails)))
    for k, v in fails.items():
        print('  FAIL', k, v.get('error') or v.get('api_4xx5xx') or v.get('head'))


if __name__ == '__main__':
    main()
