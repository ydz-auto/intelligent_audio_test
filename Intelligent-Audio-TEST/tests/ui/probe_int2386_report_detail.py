# -*- coding: utf-8 -*-
"""INT-2386 复现：报告中心行点击后 /report/<id> 是否挂载详情。

int1919 chain4 连续两次出现：URL 已到 /report/426?from=management，
但列表页仍渲染、无 GET /api/v1/reports/426 请求。本探针分开测三条路径：
  A 直接 goto /report/426?from=management
  B 报告中心点首行（int1919 的做法）
  C 报告中心点已发布行（按名称定位）
并对每步记录渲染文本与 /api/v1/reports/ 请求。只读。
"""
import argparse
import json
import re
import sys

from playwright.sync_api import sync_playwright

BASE = 'http://localhost:15173'
USER = 'dev_user'
PWD = 'dev_password'
OUT = {}


def text(page):
    try:
        return re.sub(r'\s+', ' ', page.inner_text('body'))[:400]
    except Exception as exc:
        return 'ERR %s' % exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=BASE)
    ap.add_argument('--report-id', type=int, default=426)
    args = ap.parse_args()
    base = args.base.rstrip('/')

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={'width': 1680, 'height': 899})
        page = ctx.new_page()
        seen = []
        page.on('request', lambda r: seen.append(r.url) if '/api/v1/reports' in r.url else None)

        page.goto(base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=30000)
        page.wait_for_timeout(800)
        page.fill('#username', USER)
        page.fill('#password', PWD)
        page.keyboard.press('Enter')
        page.wait_for_function("!location.pathname.startsWith('/login')", timeout=45000)
        page.wait_for_timeout(2500)

        # A 直接访问详情
        seen.clear()
        page.goto('%s/report/%d?from=management' % (base, args.report_id),
                  wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        OUT['direct'] = {
            'url': page.url,
            'text': text(page),
            'detail_apis': [u.split('/api/v1/')[-1][:80] for u in seen],
            'has_export_btn': page.locator('button', has_text='导出').count(),
        }
        page.screenshot(path='tests/ui/artifacts/int1919/react/probe_direct_detail.png')

        # B 报告中心 → 首行
        seen.clear()
        page.goto(base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        rows = page.locator('tbody tr')
        OUT['rows'] = rows.count()
        first = rows.first
        OUT['row0_text'] = first.inner_text()[:220] if rows.count() else None
        first.click()
        page.wait_for_timeout(6000)
        OUT['row_click'] = {
            'url': page.url,
            'text': text(page),
            'detail_apis': [u.split('/api/v1/')[-1][:80] for u in seen],
            'has_export_btn': page.locator('button', has_text='导出').count(),
        }
        page.screenshot(path='tests/ui/artifacts/int1919/react/probe_row_click.png')

        # C 已发布行
        seen.clear()
        page.goto(base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        pub = page.locator('tbody tr', has_text='已发布').first
        OUT['published_row_count'] = page.locator('tbody tr', has_text='已发布').count()
        if OUT['published_row_count']:
            OUT['pub_row_text'] = pub.inner_text()[:220]
            pub.click()
            page.wait_for_timeout(6000)
            OUT['pub_click'] = {
                'url': page.url,
                'text': text(page),
                'detail_apis': [u.split('/api/v1/')[-1][:80] for u in seen],
                'has_export_btn': page.locator('button', has_text='导出').count(),
            }
            page.screenshot(path='tests/ui/artifacts/int1919/react/probe_pub_click.png')

        ctx.close()
        b.close()

    print(json.dumps(OUT, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
