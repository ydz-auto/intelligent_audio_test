# -*- coding: utf-8 -*-
"""INT-2397 日巡补充：报告中心搜索 + 计数实测（React 15173，docker 真实库栈）。

卡 INT-2397 的关键链路要求覆盖「报告：中心 / 详情 / 搜索 / 计数」。int1919 只覆盖
中心列表与详情、计数只用于「共 N 个报告」截图取证；搜索没有脚本固化，本探针补上：

  1. 进入 /report-center，记录「共 N 个报告」与实际行数；
  2. 搜索命中词（默认「全类型」，可从 --hit 覆盖）→ 记录计数、行数、请求参数
     （前端发 `keyword=`，网关映射到 report_service 的 `search`，INT-2329）；
  3. 搜索必不存在的词 → 计数 0 + 空态文案；
  4. 清空搜索 → 计数恢复。

只读，不写任何业务数据。截图落 tests/ui/artifacts/int2397/。

跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2397_report_search.py --base http://localhost:15173
"""
import argparse
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2397')


def _count(page):
    body = re.sub(r'\s+', ' ', page.inner_text('body'))
    m = re.search(r'共\s*([\d,]+)\s*个报告', body)
    return {
        'count': m.group(1) if m else None,
        'rows': page.locator('tbody tr').count(),
        'empty_hint': ('未找到' in body) or ('暂无' in body),
    }


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    ap.add_argument('--hit', default='全类型', help='必然命中若干条报告的搜索词')
    ap.add_argument('--miss', default='zzz_not_exist_zzz')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)

    out = {'base': base, 'hit_word': args.hit, 'miss_word': args.miss}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 899})
        page = ctx.new_page()
        reqs = []
        page.on('request', lambda r: reqs.append(r.url)
                if '/api/v1/reports?' in r.url else None)
        page.on('console', lambda m: out.setdefault('console_errors', []).append(m.text)
                if m.type == 'error' else None)

        page.goto(base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=30000)
        page.fill('#username', args.username)
        page.fill('#password', args.password)
        page.keyboard.press('Enter')
        page.wait_for_function("!location.pathname.startsWith('/login')", timeout=45000)
        page.wait_for_timeout(2500)

        page.goto(base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(5000)
        out['before'] = _count(page)

        box = page.locator('input[placeholder*="搜索报告"]').first
        if box.count() == 0:
            out['error'] = '未找到报告中心搜索框'
        else:
            for tag, word in (('hit', args.hit), ('miss', args.miss)):
                reqs.clear()
                box.fill(word)
                page.keyboard.press('Enter')
                page.wait_for_timeout(3000)
                rec = _count(page)
                rec['requests'] = [u.split('/api/v1/')[-1][:140] for u in reqs]
                out[tag] = rec
                page.screenshot(path=os.path.join(ART, 'report_search_%s.png' % tag))
            reqs.clear()
            box.fill('')
            page.keyboard.press('Enter')
            page.wait_for_timeout(3000)
            out['restored'] = _count(page)

        # 判定：命中条目数下降且与请求词一致；不存在词落到 0 且有空态；清空恢复原计数
        hit_ok = (out.get('hit', {}).get('count') not in (None, '0')
                  and int(out['hit']['count'].replace(',', '')) <
                  int((out.get('before', {}).get('count') or '0').replace(',', '')))
        miss_ok = (out.get('miss', {}).get('count') == '0'
                   and out['miss'].get('rows') == 0 and out['miss'].get('empty_hint'))
        restore_ok = (out.get('restored', {}).get('count') == out.get('before', {}).get('count'))
        out['ok'] = bool(hit_ok and miss_ok and restore_ok)
        out['verdict'] = {'hit_ok': hit_ok, 'miss_ok': miss_ok, 'restore_ok': restore_ok}
        ctx.close()
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
