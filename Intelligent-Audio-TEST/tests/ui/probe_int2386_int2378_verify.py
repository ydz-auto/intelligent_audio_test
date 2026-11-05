# -*- coding: utf-8 -*-
"""INT-2386 日巡顺带复测 INT-2378：/reports 报告展示页加载中计数占位。

背景：15173 已重新部署（dist 与 wiring/react @ f5acf7226 的构建产物逐字节一致），
卡内要求「若已重新部署则顺带复测该项」。INT-2378 两处：
  1. 首载中 / 首载失败且无数据时，页头徽标与工具栏计数显示「共 — 个已发布报告」，
     不显示误导性的「共 0 个已发布报告」；取到数据后按真实 total 展示；真·空列表仍显 0。
  2. 无命中空态容器 min-h-fit：1680×899 下内容区无需内部滚动，标题/说明完整可见。

实现：Playwright async（挂住路由期间仍能 evaluate / screenshot），先预热懒加载 chunk
再挂路由 + reload；计数按元素文本正则取，避免把骨架或其它文案混进来。只读。

跑法：<python> tests/ui/probe_int2386_int2378_verify.py --base http://localhost:15173
"""
import argparse
import asyncio
import json
import os
import re
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int2386')
VIEWPORT = {'width': 1680, 'height': 899}
KW = '接线测试_不存在_20261105'

MEASURE_COUNT_JS = r"""
() => {
  const vis = (e) => e && e.offsetParent !== null;
  const re = /共\s*(—|\d+)\s*个已发布报告/;
  const out = [];
  for (const e of document.querySelectorAll('span,p,div,strong,b,em')) {
    if (!vis(e)) continue;
    const t = (e.innerText || '').trim();
    if (t.length > 40) continue;              // 只看短文案元素，避免容器聚合
    if (re.test(t)) out.push(t);
  }
  const body = document.body.innerText || '';
  return {
    counts: Array.from(new Set(out)),
    bodyHasZeroText: /共\s*0\s*个已发布报告/.test(body),
    bodyHasDashText: /共\s*—\s*个已发布报告/.test(body),
    skeletons: document.querySelectorAll(
      '[class*=animate-pulse],[class*=skeleton],[data-slot=skeleton]').length,
    hasErrorText: /加载失败|获取失败|请重试/.test(body),
    emptyText: body.includes('暂无已发布报告'),
    theme: document.documentElement.className,
    bodyLen: body.length,
  };
}
"""

MEASURE_EMPTY_JS = r"""
() => {
  const vis = (e) => e && e.offsetParent !== null && e.getBoundingClientRect().height > 0;
  const exact = (t) => [...document.querySelectorAll('h1,h2,h3,h4,p,span,div')]
      .find(e => vis(e) && (e.innerText || '').trim() === t);
  const rect = (e) => {
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return {top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height)};
  };
  const title = exact('暂无已发布报告');
  let root = title;
  while (root && root.parentElement && !String(root.className || '').includes('border-dashed')) {
    root = root.parentElement;
  }
  let sc = null;
  if (title) {
    let n = title.parentElement;
    while (n && n !== document.body) {
      const cs = getComputedStyle(n);
      if (/(auto|scroll)/.test(cs.overflowY) && n.clientHeight > 0) { sc = n; break; }
      n = n.parentElement;
    }
  }
  const scRect = sc ? sc.getBoundingClientRect() : null;
  return {
    title: rect(title),
    emptyRoot: rect(root),
    scrollContainer: sc ? {clientHeight: sc.clientHeight, scrollHeight: sc.scrollHeight,
                           top: Math.round(scRect.top), bottom: Math.round(scRect.bottom)} : null,
    hasTitle: !!(title),
    theme: document.documentElement.className,
    bodyLen: (document.body.innerText || '').length,
  };
}
"""


async def login(page, base, user='dev_user', pwd='dev_password'):
    await page.goto(base + '/login', wait_until='domcontentloaded')
    await page.wait_for_selector('#username', timeout=30000)
    await page.fill('#username', user)
    await page.fill('#password', pwd)
    await page.keyboard.press('Enter')
    await page.wait_for_function("() => !location.pathname.startsWith('/login')", timeout=45000)
    await page.wait_for_timeout(2500)


async def loading_count(page, mode, dark, shot_prefix):
    """mode: 'hold'（加载中）| 'block'（首载失败）"""
    release = asyncio.Event()

    async def slow(route):
        if mode == 'block':
            await route.abort()
            return
        try:
            await asyncio.wait_for(release.wait(), timeout=12)
        except asyncio.TimeoutError:
            pass
        await route.continue_()

    rec = {'mode': mode}
    pat = '**/api/v1/reports?*'
    await page.route(pat, slow)
    try:
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_timeout(2200)
        rec['state'] = await page.evaluate(MEASURE_COUNT_JS)
        await page.screenshot(path=os.path.join(ART, '%s_reports_%s_%s.png'
                                                % (shot_prefix, mode, 'dark' if dark else 'light')))
        release.set()
        if mode == 'hold':
            await page.wait_for_function(
                "() => /共\\s*\\d+\\s*个已发布报告/.test(document.body.innerText || '')",
                timeout=30000)
            await page.wait_for_timeout(800)
            rec['after'] = await page.evaluate(MEASURE_COUNT_JS)
            await page.screenshot(path=os.path.join(ART, '%s_reports_loaded_%s.png'
                                                    % (shot_prefix, 'dark' if dark else 'light')))
    except Exception as exc:
        rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
    finally:
        release.set()
        await page.unroute(pat, slow)
    st = rec.get('state') or {}
    if mode == 'hold':
        rec['ok'] = bool(
            not st.get('bodyHasZeroText')
            and '共 — 个已发布报告' in (st.get('counts') or [])
            and re.search(r'共\s*\d+\s*个已发布报告', ' '.join((rec.get('after') or {}).get('counts') or []))
        )
    else:
        rec['ok'] = bool(not st.get('bodyHasZeroText') and st.get('bodyHasDashText'))
    return rec


async def empty_state(page, dark, shot_prefix):
    await page.goto(page.url.split('/reports')[0] + '/reports', wait_until='domcontentloaded')
    await page.wait_for_timeout(3500)
    # 搜索一个必然不存在的关键字
    await page.evaluate("""(v) => {
      const el = [...document.querySelectorAll('input')]
          .find(e => (e.placeholder || '').includes('搜索'));
      if (!el) return 'no-input';
      el.focus();
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return 'ok';
    }""", KW)
    await page.wait_for_timeout(3000)
    rec = {'state': await page.evaluate(MEASURE_EMPTY_JS)}
    await page.screenshot(path=os.path.join(ART, '%s_reports_empty_%s.png'
                                            % (shot_prefix, 'dark' if dark else 'light')))
    st = rec['state']
    sc = st.get('scrollContainer') or {}
    sc_rect_bottom = sc.get('bottom')
    title = st.get('title') or {}
    limit = sc_rect_bottom if sc_rect_bottom else VIEWPORT['height']
    rec['in_view'] = bool(title and title.get('top', -1) >= 0
                          and title.get('bottom', 10 ** 6) <= limit + 1)
    rec['no_inner_scroll'] = (not sc) or (sc.get('scrollHeight', 0) <= sc.get('clientHeight', 0) + 2)
    rec['ok'] = bool(st.get('hasTitle') and rec['in_view'] and rec['no_inner_scroll'])
    return rec


async def run_scheme(p, base, dark, shot_prefix, summary):
    browser = await p.chromium.launch(headless=True, args=['--lang=zh-CN'])
    ctx = await browser.new_context(viewport=VIEWPORT, locale='zh-CN')
    page = await ctx.new_page()
    await login(page, base)
    if dark:
        await page.evaluate("() => localStorage.setItem('iatp:theme:v1:mode','dark')")
    # 预热 /reports 懒加载 chunk
    await page.goto(base + '/reports', wait_until='domcontentloaded')
    await page.wait_for_timeout(4000)
    if dark:
        await page.evaluate("() => localStorage.setItem('iatp:theme:v1:mode','dark')")
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_timeout(2500)
    summary[shot_prefix + '_hold'] = await loading_count(page, 'hold', dark, shot_prefix)
    summary[shot_prefix + '_block'] = await loading_count(page, 'block', dark, shot_prefix)
    # 恢复：解除拦截后重新访问
    await page.goto(base + '/reports', wait_until='domcontentloaded')
    await page.wait_for_timeout(3000)
    summary[shot_prefix + '_empty'] = await empty_state(page, dark, shot_prefix)
    await ctx.close()
    await browser.close()


async def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)
    summary = {'base': base, 'viewport': VIEWPORT}

    async with async_playwright() as p:
        await run_scheme(p, base, False, 'light', summary)
        await run_scheme(p, base, True, 'dark', summary)

    with open(os.path.join(ART, 'int2378_verify.json'), 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for k, v in summary.items():
        if isinstance(v, dict):
            print('%-18s ok=%s mode=%s counts=%s' % (k, v.get('ok'), v.get('mode'),
                                                     (v.get('state') or {}).get('counts')))


if __name__ == '__main__':
    asyncio.run(main())
