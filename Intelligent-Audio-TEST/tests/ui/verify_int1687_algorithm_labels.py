# -*- coding: utf-8 -*-
"""INT-1687 验收脚本：用例卡算法徽章 / 抽屉「评估维度」提示条不再显示算法类型码。

同一脚本双跑对照（A/B）：
- 修复侧：本 run 由交付提交 02e6e3973 的 diff 构建的 dist 起的旁路 nginx 容器（--base http://127.0.0.1:15287）
- 基线侧：共享 15173 旧镜像（不含本卡改动，--base http://127.0.0.1:15173）

检查项：
1. 用例页 /testcases/by-group：展开分组后用例卡徽章文本；
   - 命中「小艺语音大模型」计数 > 0；
   - 页面中形如 voice_llm / wire_test_param / asr_* 的裸类型码计数 = 0；
   - 记下所有徽章候选元素的 (tag, text)。
2. 打开某用例「编辑用例」抽屉 → 切「评估维度」步骤 → 记录过滤提示条原文：
   - 修复侧应含「小艺语音大模型」；基线侧应含 voice_llm。
3. 页内 fetch GET /api/v1/algorithm/options 记录真实 value→name（证据）, 并从 performance log
   取 /api/v1/algorithm/options、/api/v1/testcases 的 HTTP 状态与耗时。
4. 浅 / 深色各自截图：用例卡、抽屉评估步骤。

用法：
    python tests/ui/verify_int1687_algorithm_labels.py --label fix --base http://127.0.0.1:15287
    python tests/ui/verify_int1687_algorithm_labels.py --label baseline --base http://127.0.0.1:15173 --themes light
环境变量：CHROMEDRIVER（默认本机证书缓存驱动）。
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
RAW_CODE_RE = re.compile(r'(voice_llm|wire_test_param)')

COLLECT_JS = r"""
const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
const rawRe = /^(voice_llm|wire_test_param|asr[_a-z0-9]*|eval_[_a-z0-9]*)$/;
const badges = [];
for (const el of document.querySelectorAll('span,div')) {
  if (el.children.length) continue;
  const t = norm(el.innerText);
  if (!t || t.length > 40) continue;
  if (rawRe.test(t) || t.indexOf('\u5c0f\u827a\u8bed\u97f3\u5927\u6a21\u578b') >= 0) {
    badges.push({ tag: el.tagName, text: t, cls: (el.className || '').toString().slice(0, 80) });
  }
}
return {
  text: norm(document.body ? document.body.innerText : ''),
  badges: badges,
  good: (document.body ? document.body.innerText : '').split('\u5c0f\u827a\u8bed\u97f3\u5927\u6a21\u578b').length - 1,
  raw: (document.body ? document.body.innerText : '').match(/voice_llm|wire_test_param/g) || [],
  caseRows: document.querySelectorAll('[aria-label^="\u9009\u62e9 "]').length,
};
"""

EXPAND_JS = r"""
const heads = Array.from(document.querySelectorAll('div.cursor-pointer'));
const target = heads.find(function (h) { return /(^|\D)[1-9]\d*\s*条/.test(h.innerText); }) || heads[0];
if (!target) return null;
const name = (target.innerText || '').replace(/\s+/g, ' ').slice(0, 40);
target.click();
return name;
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
if (!t) return { clicked: false, tabs: tabs.map(function (b) { return (b.innerText || '').trim(); }).slice(0, 12) };
t.click();
return { clicked: true };
"""

HINT_JS = r"""
const dlg = document.querySelectorAll('[role="dialog"]');
const root = dlg.length ? dlg[dlg.length - 1] : document.body;
const txt = (root.innerText || '').replace(/\s+/g, ' ');
const m = txt.match(/\u5df2\u6839\u636e[^\u3002]{0,60}\u8fc7\u6ee4\u53ef\u7528\u7ef4\u5ea6/);
return {
  hint: m ? m[0] : null,
  dialog_text_head: txt.slice(0, 200),
  ready: m != null,
};
"""

OPTIONS_FETCH_JS = r"""
const done = arguments[arguments.length - 1];
fetch('/api/v1/algorithm/options', { credentials: 'include' })
  .then(function (r) { return r.text().then(function (b) { done({ status: r.status, body: b.slice(0, 2000) }); }); })
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
        rows.append({'url': url, 'status': resp.get('status'), 'type': resp.get('mimeType')})


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


def run_theme(drv, base, theme, out_dir, label, view='by-group'):
    os.makedirs(out_dir, exist_ok=True)
    drv.get(base + '/')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    drv.execute_script("localStorage.setItem('iatp:theme:mode', arguments[0]);", theme)
    try:
        drv.get_log('performance')
    except Exception:
        pass
    url = base + '/testcases/' + view + '?INT1687=' + str(int(time.time()))
    drv.get(url)
    # 等分组卡渲染
    wait_for(drv, "return document.querySelectorAll('div.cursor-pointer').length;", lambda v: (v or 0) > 0, 120)
    expanded = drv.execute_script(EXPAND_JS)
    time.sleep(0.5)
    # 等组内用例卡（懒加载，慢）
    wait_for(drv, COLLECT_JS, lambda v: bool(v) and (v.get('caseRows', 0) > 0 or v.get('good', 0) > 0), 180, 0.8)
    time.sleep(2.0)
    cards = drv.execute_script(COLLECT_JS)
    cards_shot = os.path.join(out_dir, 'cards_%s.png' % theme)
    drv.save_screenshot(cards_shot)

    # 页内 fetch 真实选项（证据：value→name）
    try:
        opt = drv.execute_async_script(OPTIONS_FETCH_JS)
    except Exception as exc:
        opt = {'status': None, 'body': 'ERR ' + str(exc)}

    # 打开编辑抽屉 → 评估维度
    dialog = {'opened': False}
    opened = drv.execute_script(OPEN_DRAWER_JS)
    if opened:
        got = wait_for(
            drv,
            "return document.querySelectorAll('[role=\"dialog\"]').length;",
            lambda v: (v or 0) > 0,
            40,
        )
        time.sleep(1.5)
        tab_res = drv.execute_script(TAB_JS)
        hint = wait_for(drv, HINT_JS, lambda v: bool(v) and v.get('ready'), 90, 0.6)
        time.sleep(0.8)
        drawer_shot = os.path.join(out_dir, 'drawer_%s.png' % theme)
        drv.save_screenshot(drawer_shot)
        dialog = {
            'opened': bool(opened) and bool(got),
            'tab': tab_res,
            'hint': (hint or {}).get('hint'),
            'dialog_head': (hint or {}).get('dialog_text_head'),
            'shot': drawer_shot,
        }
    else:
        drawer_shot = None

    seen = set()
    net = []
    drain_perf(drv, seen, net)

    return {
        'label': label,
        'theme': theme,
        'base': base,
        'url': url,
        'expanded_group': expanded,
        'cards': {
            'good_count': cards.get('good'),
            'raw_codes_in_page': cards.get('raw'),
            'badge_candidates': cards.get('badges'),
            'case_rows': cards.get('caseRows'),
            'shot': cards_shot,
            'text_head': (cards.get('text') or '')[:400],
        },
        'dialog': dialog,
        'algorithm_options_http': opt,
        'network': net,
        'console_severe': [
            c.get('message') for c in (drv.get_log('browser') or []) if c.get('level') == 'SEVERE'
        ][:8],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:15287')
    ap.add_argument('--label', default='fix')
    ap.add_argument('--themes', default='light,dark')
    ap.add_argument('--view', default='by-group')
    args = ap.parse_args()

    out_dir = os.path.join(REPO, 'tests', 'ui', 'artifacts', 'int1687_' + args.label)
    drv = build_driver()
    results = []
    try:
        for theme in [t.strip() for t in args.themes.split(',') if t.strip()]:
            results.append(run_theme(drv, args.base, theme, out_dir, args.label, args.view))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    out = {'runs': results}
    path = os.path.join(out_dir, 'summary.json')
    os.makedirs(out_dir, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print('SUMMARY:', path)


if __name__ == '__main__':
    main()


