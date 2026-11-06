# -*- coding: utf-8 -*-
"""INT-2375 日巡专项：INT-2368 两处 P3 修复在部署镜像（15173）的只读复测。

卡内要求（2026-11-04 日巡重点）：
  1. 报告中心无关键字命中的空态首屏可见、不被视口裁切（1680×899，表头/说明/
     操作按钮全部落在内容区可视下沿内，列表区无需内部滚动）。
  2. 设备页加载态统计先显示「在线 —/共 —」，取到数据后更新为真实计数，
     加载中不出现误导性的「共 0 条」；三个页签同口径。

实现要点（沿用 INT-2368 复测口径，见 memory docker-stack-ui-screenshot-recipe）：
  - 用 Playwright **async** API：同步 API 的 time.sleep 会阻塞 driver 线程，
    挂住路由期间发不出 evaluate / screenshot；
  - 先正常访问一次目标页预热懒加载 chunk，再挂路由 + reload，否则 chunk 也被
    延迟，骨架都出不来；
  - 空态可见性不只断言 innerText，还要量 getBoundingClientRect 与滚动容器
    clientHeight/scrollHeight（INT-2367 曾把「DOM 有文案但首屏被裁」误判通过）。

只读：只有登录、GET 与页面内筛选，不写业务库。
跑法：
  <python> tests/ui/probe_int2375_int2368_verify.py --base http://localhost:15173 \
      --api http://localhost:15000
"""
import argparse
import asyncio
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from playwright.async_api import async_playwright  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int2375')
KW = '接线测试_不存在_20261104'
VIEWPORT = {'width': 1680, 'height': 899}

MEASURE_EMPTY_JS = r"""
() => {
  const vis = (e) => e && e.offsetParent !== null && e.getBoundingClientRect().height > 0;
  const exact = (t) => [...document.querySelectorAll('h1,h2,h3,h4,p,span,div,button')]
      .find(e => vis(e) && (e.innerText || '').trim() === t);
  const rect = (e) => {
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
            h: Math.round(r.height), top: Math.round(r.top), bottom: Math.round(r.bottom)};
  };
  const title = exact('未找到匹配报告');
  const desc = exact('试试其他关键字');
  let emptyRoot = title;
  while (emptyRoot && emptyRoot.parentElement &&
         !String(emptyRoot.className || '').includes('border-dashed')) {
    emptyRoot = emptyRoot.parentElement;
  }
  // 空态内的「清除全部筛选」才是修复点（高级搜索区另有一个同名按钮）
  const allClear = [...document.querySelectorAll('button')]
      .filter(b => (b.innerText || '').trim() === '清除全部筛选' && vis(b));
  const btn = (emptyRoot && allClear.find(b => emptyRoot.contains(b))) || allClear[allClear.length - 1];
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
  const hit = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const at = document.elementFromPoint(
      Math.min(innerWidth - 1, Math.max(0, r.x + r.width / 2)),
      Math.min(innerHeight - 1, Math.max(0, r.y + r.height / 2)));
    return !!at && (at === el || el.contains(at));
  };
  const txt = document.body.innerText || '';
  return {
    viewport: {w: innerWidth, h: innerHeight},
    title: rect(title), desc: rect(desc), btn: rect(btn), emptyRoot: rect(emptyRoot),
    scrollContainer: sc ? {clientHeight: sc.clientHeight, scrollHeight: sc.scrollHeight,
                           top: Math.round(scRect.top), bottom: Math.round(scRect.bottom)} : null,
    titleHit: hit(title), btnHit: hit(btn),
    textHasTitle: txt.includes('未找到匹配报告'),
    textHasDesc: txt.includes('试试其他关键字'),
    countZero: txt.includes('共 0 个'),
    theme: document.documentElement.className,
  };
}
"""

MEASURE_DEVICES_JS = r"""
() => {
  const vis = (e) => e && e.offsetParent !== null;
  const badgeEl = [...document.querySelectorAll('span,div')]
      .find(e => vis(e) && /^在线\s*[—\d]+\s*\/\s*共\s*[—\d]+$/.test((e.innerText || '').trim()));
  const txt = document.body.innerText || '';
  return {
    badge: badgeEl ? (badgeEl.innerText || '').trim() : null,
    hasZeroFooter: txt.includes('共 0 条'),
    realFooter: (txt.match(/共\s*\d+\s*条/g) || []).slice(0, 3),
    rows: document.querySelectorAll('tbody tr').length,
    skeletons: document.querySelectorAll(
        '[class*=animate-pulse],[class*=skeleton],[data-slot=skeleton],[data-slot*=skeleton]').length,
    hasErrorText: /加载失败|获取失败/.test(txt),
    theme: document.documentElement.className,
  };
}
"""


async def login(page, base, username='dev_user', password='dev_password'):
    await page.goto(base + '/login', wait_until='domcontentloaded')
    await page.wait_for_selector('input[type=password]', timeout=30000)
    await page.fill("input[placeholder*='用户名']", username)
    await page.fill('input[type=password]', password)
    await page.keyboard.press('Enter')
    await page.wait_for_function("() => !location.pathname.startsWith('/login')", timeout=30000)
    await page.wait_for_timeout(2500)


async def search_report(page, keyword):
    await page.evaluate("""(v) => {
      const el = [...document.querySelectorAll('input')]
          .find(e => (e.placeholder || '').includes('搜索报告名称'));
      if (!el) return 'no-input';
      el.focus();
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return 'ok';
    }""", keyword)


async def report_empty(page, base, shot_prefix):
    await page.goto(base + '/report-center', wait_until='domcontentloaded')
    await page.wait_for_selector('tbody tr', timeout=30000)
    await page.wait_for_timeout(1500)
    await search_report(page, KW)
    await page.wait_for_function(
        "() => (document.body.innerText || '').includes('未找到匹配报告')", timeout=30000)
    await page.wait_for_timeout(1200)
    m = await page.evaluate(MEASURE_EMPTY_JS)
    await page.screenshot(path=os.path.join(ART, '%s_report_empty.png' % shot_prefix))
    # 可见性判据：标题/说明/按钮都在视口内，且都在内容区滚动容器可视下沿内；
    # 容器 scrollHeight 不超出 clientHeight（无需内部滚动）
    sc = m.get('scrollContainer') or {}
    limit = m['viewport']['h']
    if sc.get('bottom'):
        limit = min(limit, sc['bottom'])
    parts = ('title', 'desc', 'btn')
    in_view = all(m.get(p) and m[p]['top'] >= 0 and m[p]['bottom'] <= limit + 1 for p in parts)
    no_inner_scroll = (not sc) or (sc.get('scrollHeight', 0) <= sc.get('clientHeight', 0) + 2)
    m['ok'] = bool(m.get('textHasTitle') and m.get('textHasDesc') and m.get('countZero')
                   and in_view and no_inner_scroll and m.get('btnHit'))
    m['in_view'] = in_view
    m['no_inner_scroll'] = no_inner_scroll
    m['limit_bottom'] = limit
    # 恢复：点「清除全部筛选」→ 真实列表回来（无布局回归）
    try:
        await page.click("button:has-text('清除全部筛选') >> nth=0", timeout=5000)
        await page.wait_for_selector('tbody tr', timeout=15000)
        await page.wait_for_timeout(1200)
        rows = await page.evaluate("() => document.querySelectorAll('tbody tr').length")
        m['clear_recovered_rows'] = rows
        await page.screenshot(path=os.path.join(ART, '%s_report_clear_recovered.png' % shot_prefix))
    except Exception as exc:
        m['clear_recovered_error'] = '%s: %s' % (type(exc).__name__, str(exc)[:160])
    return m


async def devices_loading(page, base, tab, pat, shot_prefix, dark=False):
    url = base + '/devices/' + tab
    await page.goto(url, wait_until='domcontentloaded')
    await page.wait_for_selector('tbody tr', timeout=30000)
    await page.wait_for_timeout(1200)

    release = asyncio.Event()

    async def slow(route):
        try:
            await asyncio.wait_for(release.wait(), timeout=10)
        except asyncio.TimeoutError:
            pass
        await route.continue_()

    await page.route(pat, slow)
    rec = {'tab': tab, 'pattern': pat}
    try:
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_timeout(1200)
        loading = await page.evaluate(MEASURE_DEVICES_JS)
        rec['loading'] = loading
        await page.screenshot(path=os.path.join(ART, '%s_devices_loading_%s.png' % (shot_prefix, tab)))
        # 放行：让挂住的路由继续，等真实计数渲染
        release.set()
        await page.wait_for_selector('tbody tr', timeout=30000)
        await page.wait_for_function(
            "() => /在线\\s*\\d+\\s*\\/\\s*共\\s*\\d+/.test(document.body.innerText || '')", timeout=30000)
        await page.wait_for_timeout(1000)
        rec['loaded'] = await page.evaluate(MEASURE_DEVICES_JS)
        await page.screenshot(path=os.path.join(ART, '%s_devices_loaded_%s.png' % (shot_prefix, tab)))
    except Exception as exc:
        rec['loaded_error'] = '%s: %s' % (type(exc).__name__, str(exc)[:160])
    finally:
        release.set()
        await page.unroute(pat, slow)
    ld, ok = rec.get('loading') or {}, rec.get('loaded') or {}
    rec['ok'] = bool(
        ld.get('badge') == '在线 —/共 —'
        and not ld.get('hasZeroFooter')
        and nd(ld.get('skeletons')) > 0
        and re.match(r'^在线 \d+/共 \d+$', (ok.get('badge') or ''))
        and not ok.get('hasZeroFooter')
    )
    return rec


def nd(v):
    return v or 0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default=os.environ.get('API_BASE', 'http://localhost:15000'))
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)
    summary = {'base': base, 'viewport': VIEWPORT, 'keyword': KW}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--lang=zh-CN'])

        # 浅色：报告空态 + 设备三页签加载态
        ctx = await browser.new_context(viewport=VIEWPORT, locale='zh-CN')
        page = await ctx.new_page()
        console = []
        page.on('console', lambda m: console.append(
            (m.type, m.text[:200])) if m.type == 'error' else None)
        await login(page, base, args.username, args.password)
        summary['report_empty_light'] = await report_empty(page, base, 'light')
        devices = {}
        for tab, pat in (('test', '**/api/v1/test-devices*'),
                         ('playback', '**/api/v1/playback-devices*'),
                         ('api', '**/api/v1/apis*')):
            devices[tab] = await devices_loading(page, base, tab, pat, 'light')
        summary['devices'] = devices
        summary['console_errors_light'] = console[:5]
        await ctx.close()

        # 深色：同样的两处（各 reload 后设置主题）
        ctx2 = await browser.new_context(viewport=VIEWPORT, locale='zh-CN')
        await ctx2.add_init_script(
            "localStorage.setItem('iatp:theme:v1:mode','dark');")
        page2 = await ctx2.new_page()
        console2 = []
        page2.on('console', lambda m: console2.append(
            (m.type, m.text[:200])) if m.type == 'error' else None)
        await login(page2, base, args.username, args.password)
        summary['report_empty_dark'] = await report_empty(page2, base, 'dark')
        summary['devices_dark'] = await devices_loading(
            page2, base, 'test', '**/api/v1/test-devices*', 'dark', dark=True)
        summary['console_errors_dark'] = console2[:5]
        await ctx2.close()
        await browser.close()

    out = os.path.join(ART, 'int2368_verify.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print('\nSUMMARY_JSON=%s' % out)
    for key in ('report_empty_light', 'report_empty_dark'):
        v = summary[key]
        print('%-18s ok=%s in_view=%s no_inner_scroll=%s title=%s btn=%s limit=%s' % (
            key, v.get('ok'), v.get('in_view'), v.get('no_inner_scroll'),
            v.get('title'), v.get('btn'), v.get('limit_bottom')))
    for tab, v in summary['devices'].items():
        print('DEVICES light %-8s ok=%s loading=%s pager0=%s loaded=%s' % (
            tab, v.get('ok'), (v.get('loading') or {}).get('badge'),
            (v.get('loading') or {}).get('hasZeroFooter'),
            (v.get('loaded') or {}).get('badge')))
    v = summary['devices_dark']
    print('DEVICES dark  %-8s ok=%s loading=%s pager0=%s loaded=%s' % (
        'test', v.get('ok'), (v.get('loading') or {}).get('badge'),
        (v.get('loading') or {}).get('hasZeroFooter'),
        (v.get('loaded') or {}).get('badge')))
    ok_all = (summary['report_empty_light'].get('ok') and summary['report_empty_dark'].get('ok')
              and all(v.get('ok') for v in summary['devices'].values())
              and summary['devices_dark'].get('ok'))
    print('ALL_OK=%s' % ok_all)


if __name__ == '__main__':
    asyncio.run(main())
