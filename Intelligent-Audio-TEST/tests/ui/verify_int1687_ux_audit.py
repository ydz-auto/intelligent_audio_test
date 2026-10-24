# -*- coding: utf-8 -*-
"""INT-1687 前端UX审计：用例卡算法徽章 / 抽屉「评估维度」提示条算法名取自真实 /algorithm/options。

审计侧（前端UX审计员）自验，不复用实施者/验收方脚本结论：
- 浅/深色用例页（按分组 + 按标签）截图与徽章口径；
- 徽章与接口 algorithm_type 的逐卡对照（卡片数 vs 命中名称数）；
- 首屏到徽章出现的时间线（未命中/未加载时是否整枚消失 → 布局抖动）；
- 编辑抽屉「评估维度」提示条原文；
- 控制台 SEVERE 与 /algorithm/options、/testcases 的网络状态。

用法：
    python tests/ui/verify_int1687_ux_audit.py --base http://127.0.0.1:15289 --theme light
"""
import argparse
import json
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'

GOOD_LABEL = '小艺语音大模型'
RAW_RE = re.compile(r'voice_llm|wire_test_param|wire_test_int1686b')

# 时间线采样：记录每个时刻的卡片数 / 算法名数 / 裸类型码数
TIMELINE_JS = r"""
const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
const body = document.body ? document.body.innerText : '';
const nameHits = body.split('\u5c0f\u827a\u8bed\u97f3\u5927\u6a21\u578b').length - 1;
const raws = body.match(/voice_llm|wire_test_param|wire_test_int1686b/g) || [];
return {
  t: Date.now(),
  cases: document.querySelectorAll('[aria-label^="\u9009\u62e9 "]').length,
  groups: document.querySelectorAll('div.cursor-pointer').length,
  names: nameHits,
  raw: raws.length,
  skeleton: document.querySelectorAll('[data-slot="skeleton"], .animate-pulse').length,
};
"""

EXPAND_FIRST_GROUP_JS = r"""
const heads = Array.from(document.querySelectorAll('div.cursor-pointer'))
  .filter(function (h) { return /(\d+)\s*\u6761/.test(h.innerText || ''); });
const target = heads[0];
if (!target) return null;
const name = (target.innerText || '').replace(/\s+/g, ' ').slice(0, 30);
target.click();
return name;
"""

# 逐卡对照：每张卡的算法徽章文本（徽章 = 卡片内 secondary badge 之一）
CARD_DETAIL_JS = r"""
const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
const cards = Array.from(document.querySelectorAll('[aria-label^="\u9009\u62e9 "]'))
  .map(function (el) { return el.closest('div[class*="rounded"]') || el.parentElement; })
  .filter(Boolean);
const out = [];
const seen = new Set();
for (const c of cards) {
  const title = norm((c.innerText || '').split('\n')[0]);
  if (seen.has(c)) continue;
  seen.add(c);
  const badges = Array.from(c.querySelectorAll('[data-slot="badge"], span'))
    .filter(function (b) { return b.children.length === 0 && norm(b.innerText); })
    .map(function (b) { return norm(b.innerText); })
    .filter(function (t) { return t.length <= 24; });
  out.push({ title: title.slice(0, 30), badges: badges.slice(0, 6) });
  if (out.length >= 40) break;
}
return out;
"""

OPEN_DRAWER_JS = r"""
const btns = Array.from(document.querySelectorAll('button[aria-label="\u7f16\u8f91\u7528\u4f8b"]'));
if (!btns.length) return null;
btns[0].scrollIntoView({ block: 'center' });
btns[0].click();
return btns.length;
"""

TAB_JS = r"""
const dlg = document.querySelectorAll('[role="dialog"]');
const root = dlg.length ? dlg[dlg.length - 1] : document.body;
const tabs = Array.from(root.querySelectorAll('button, [role="tab"]'));
const t = tabs.find(function (b) { return (b.innerText || '').trim() === '\u8bc4\u4f30\u7ef4\u5ea6'; });
if (!t) return { clicked: false, tabs: tabs.map(function (b) { return (b.innerText || '').trim(); }).slice(0, 14) };
t.click();
return { clicked: true };
"""

HINT_JS = r"""
const dlg = document.querySelectorAll('[role="dialog"]');
const root = dlg.length ? dlg[dlg.length - 1] : document.body;
const txt = (root.innerText || '').replace(/\s+/g, ' ');
const m = txt.match(/\u5df2\u6839\u636e[^\u3002]{0,60}\u8fc7\u6ee4\u53ef\u7528\u7ef4\u5ea6/);
return { hint: m ? m[0] : null, ready: m != null, head: txt.slice(0, 260) };
"""

OPTIONS_FETCH_JS = r"""
const done = arguments[arguments.length - 1];
fetch('/api/v1/algorithm/options', { credentials: 'include' })
  .then(function (r) { return r.text().then(function (b) { done({ status: r.status, body: b.slice(0, 1500) }); }); })
  .catch(function (e) { done({ status: null, body: String(e) }); });
"""


def build_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1200')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    opts.set_capability('pageLoadStrategy', 'eager')
    exe = os.environ.get('CHROMEDRIVER', DEFAULT_DRIVER)
    if not os.path.isfile(exe):
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
        versions = sorted(os.listdir(cache)) if os.path.isdir(cache) else []
        exe = os.path.join(cache, versions[-1], 'chromedriver.exe') if versions else None
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(service=srv, options=opts)
    drv.set_script_timeout(120)
    drv.set_page_load_timeout(180)
    return drv


def drain_perf(drv, seen, rows):
    try:
        entries = drv.get_log('performance')
    except Exception:
        return
    for entry in entries:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg.get('params', {}).get('response', {})
        url = resp.get('url', '')
        if '/api/v1/algorithm/options' not in url and '/api/v1/testcases' not in url:
            continue
        rid = msg.get('params', {}).get('requestId')
        if rid in seen:
            continue
        seen.add(rid)
        rows.append({'url': url[:140], 'status': resp.get('status')})


def wait_for(drv, js, pred, timeout=90.0, step=0.4):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = drv.execute_script(js)
        except Exception:
            last = None
        if pred(last):
            return last
        time.sleep(step)
    return last


def sample_timeline(drv, seconds=25.0, step=0.2):
    rows = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            rows.append(drv.execute_script(TIMELINE_JS))
        except Exception:
            pass
        time.sleep(step)
    return rows


def run(drv, base, theme, view, out_dir, tag):
    os.makedirs(out_dir, exist_ok=True)
    drv.get(base + '/')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    try:
        drv.get_log('performance')
    except Exception:
        pass
    url = '%s/testcases/%s?INT1687UX=%d' % (base, view, int(time.time()))
    drv.get(url)
    # 时间线：分组卡 → 展开 → 用例卡 → 徽章
    wait_for(drv, "return document.querySelectorAll('div.cursor-pointer').length;", lambda v: (v or 0) > 0, 120)
    expanded = drv.execute_script(EXPAND_FIRST_GROUP_JS)
    timeline = sample_timeline(drv, 28.0, 0.25)
    cards = wait_for(drv, CARD_DETAIL_JS, lambda v: bool(v) and len(v) > 3, 120, 1.0) or []
    time.sleep(1.5)
    detail = drv.execute_script(CARD_DETAIL_JS) or []
    shot = os.path.join(out_dir, 'cards_%s_%s.png' % (tag, theme))
    drv.save_screenshot(shot)

    try:
        opt = drv.execute_async_script(OPTIONS_FETCH_JS)
    except Exception as exc:
        opt = {'status': None, 'body': 'ERR ' + str(exc)}

    # 抽屉：编辑用例 → 评估维度
    dialog = {'opened': False}
    opened = drv.execute_script(OPEN_DRAWER_JS)
    if opened:
        wait_for(drv, "return document.querySelectorAll('[role=\"dialog\"]').length;", lambda v: (v or 0) > 0, 40)
        time.sleep(1.5)
        tab_res = drv.execute_script(TAB_JS)
        hint = wait_for(drv, HINT_JS, lambda v: bool(v) and v.get('ready'), 90, 0.6)
        time.sleep(1.0)
        drawer_shot = os.path.join(out_dir, 'drawer_%s_%s.png' % (tag, theme))
        drv.save_screenshot(drawer_shot)
        dialog = {'opened': True, 'tab': tab_res, 'hint': (hint or {}).get('hint'),
                  'head': (hint or {}).get('head'), 'shot': drawer_shot}

    seen, net = set(), []
    drain_perf(drv, seen, net)

    body_text = drv.execute_script("return (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');")
    # 名称/类型码计数按页内正文
    names = body_text.count(GOOD_LABEL)
    raws = RAW_RE.findall(body_text)

    # 时间线摘要：首个卡片出现时刻、首个算法名出现时刻
    t0 = timeline[0]['t'] if timeline else 0
    first_card = next((r for r in timeline if r['cases'] > 0), None)
    first_name = next((r for r in timeline if r['names'] > 0), None)

    return {
        'tag': tag, 'theme': theme, 'view': view, 'url': url, 'expanded': expanded,
        'timeline': {
            'samples': len(timeline),
            'first_case_ms': (first_card['t'] - t0) if first_card else None,
            'first_name_ms': (first_name['t'] - t0) if first_name else None,
            'max_cards': max([r['cases'] for r in timeline] or [0]),
            'name_series_first10': [(r['cases'], r['names'], r['raw']) for r in timeline[:10]],
        },
        'page': {'names': names, 'raw_codes': raws[:10], 'raw_count': len(raws)},
        'cards': detail[:25],
        'card_count': len(detail),
        'cards_with_badge': sum(1 for c in detail if any(GOOD_LABEL in b for b in c['badges'])),
        'cards_with_raw_code': sum(1 for c in detail if any(RAW_RE.fullmatch(b or '') for b in c['badges'])),
        'dialog': dialog,
        'options_http': opt,
        'network': net,
        'console_severe': [c.get('message') for c in (drv.get_log('browser') or []) if c.get('level') == 'SEVERE'][:8],
        'shot': shot,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:15289')
    ap.add_argument('--theme', default='light')
    ap.add_argument('--view', default='by-group')
    ap.add_argument('--tag', default='fix')
    args = ap.parse_args()
    out_dir = os.path.join(REPO, 'tests', 'ui', 'artifacts', 'int1687_ux')
    drv = build_driver()
    try:
        res = run(drv, args.base, args.theme, args.view, out_dir, args.tag)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'summary_%s_%s.json' % (args.tag, args.theme))
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    brief = dict(res)
    brief.pop('cards', None)
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    print('SUMMARY:', path)


if __name__ == '__main__':
    main()
