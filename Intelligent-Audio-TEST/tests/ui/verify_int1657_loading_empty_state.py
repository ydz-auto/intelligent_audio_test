# -*- coding: utf-8 -*-
"""INT-1657 验收脚本：用例页首屏列表加载期间不得显示「没有找到符合条件的测试用例」空态。

同一脚本双跑对照（A/B）：
- 修复侧：本 run 从交付提交 3e6bb1f84 导出 dist 起的旁路 nginx 容器（--base http://127.0.0.1:15247）
- 基线侧：共享 15173 旧镜像（不含本卡改动，--base http://127.0.0.1:15173）

逐 0.3s 采样首屏 body 文本直到 /api/v1/testcases 响应完成 + 2s，记录：
1. 「用例列表加载中…」(role=status) 首次/末次出现时刻；
2. 「没有找到符合条件的测试用例 / 尝试清空「分组」「标签」筛选」是否在加载窗口内出现；
3. 分组卡（「已加载全部 N 个分组」）与组内用例行（[aria-label^="选择 "]）渲染时刻；
4. /api/v1/groups、/api/v1/testcases 的 HTTP 状态与耗时（performance log，非页内打点）。

截图：加载态（或基线侧误显空态）、加载完成、展开分组后的用例行；浅色 / 深色各一轮。

用法：
    python tests/ui/verify_int1657_loading_empty_state.py --label fix --base http://127.0.0.1:15247
    python tests/ui/verify_int1657_loading_empty_state.py --label baseline --base http://127.0.0.1:15173 --themes light
环境变量：CHROMEDRIVER（默认本机证书缓存驱动）。
"""
import argparse
import json
import os
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

EMPTY_TITLE = '没有找到符合条件的测试用例'
EMPTY_DESC = '尝试清空「分组」「标签」筛选'
LOADING_HINT = '用例列表加载中'
ALL_GROUPS_MARK = '已加载全部'

SAMPLE_JS = """
const body = document.body ? document.body.innerText : '';
return {
  text: body,
  status: Array.from(document.querySelectorAll('[role=status]')).map(function (e) { return e.innerText; }),
  caseRows: document.querySelectorAll('[aria-label^="选择 "]').length,
  groupCards: document.querySelectorAll('div.cursor-pointer').length,
};
"""

EXPAND_JS = """
const heads = Array.from(document.querySelectorAll('div.cursor-pointer'));
const target = heads.find(function (h) { return /(^|\\D)[1-9]\\d*\\s*条/.test(h.innerText); }) || heads[0];
if (!target) return null;
const name = target.innerText;
target.click();
return name;
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
        # 退回缓存目录里最新版本
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
        versions = sorted(os.listdir(cache)) if os.path.isdir(cache) else []
        exe = os.path.join(cache, versions[-1], 'chromedriver.exe') if versions else None
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(service=srv, options=opts)
    drv.set_script_timeout(60)
    drv.set_page_load_timeout(180)
    return drv


def drain_perf(drv, seen, net, starts):
    """把 performance log 里 /api/v1/{groups,testcases} 的响应与耗时记进 net（按 requestId 去重）。"""
    try:
        entries = drv.get_log('performance')
    except Exception:
        return
    for entry in entries:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        method = msg.get('method')
        params = msg.get('params', {})
        if method == 'Network.requestWillBeSent':
            rid = params.get('requestId')
            if rid:
                starts[rid] = params.get('timestamp')
        elif method == 'Network.responseReceived':
            url = params.get('response', {}).get('url', '')
            key = None
            if '/api/v1/testcases' in url and '/testcases/' not in url.split('/api/v1/testcases')[1][:1]:
                key = 'testcases'
            elif '/api/v1/groups' in url:
                key = 'groups'
            if not key:
                continue
            rid = params.get('requestId')
            if rid in seen:
                continue
            seen.add(rid)
            net.setdefault(key, []).append(
                {
                    'url': url,
                    'status': params.get('response', {}).get('status'),
                    'requestId': rid,
                    'wall': params.get('response', {}).get('responseTime'),
                }
            )
        elif method == 'Network.loadingFinished':
            rid = params.get('requestId')
            start = starts.get(rid)
            for key, rows in net.items():
                for row in rows:
                    if row.get('requestId') == rid and start:
                        row['duration_ms'] = round((params.get('timestamp', 0) - start) * 1000, 1)


def run_theme(drv, base, theme, out_dir, label, timeout=150.0):
    os.makedirs(out_dir, exist_ok=True)
    # 同源设置主题后整页加载（避免 about:blank 中转丢 localStorage/主题）
    drv.get(base + '/')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    drv.delete_all_cookies()
    seen = set()
    net = {}
    starts = {}
    # 清空旧日志
    try:
        drv.get_log('performance')
    except Exception:
        pass

    t0 = time.time()
    drv.get(base + '/testcases/by-group?INT1657=' + str(int(t0)))
    samples = []
    loading_first = loading_last = empty_first = group_first = rows_first = None
    loading_shot = empty_shot = None
    response_done_at = None
    resp = None

    while time.time() - t0 < timeout:
        t = round(time.time() - t0, 2)
        try:
            st = drv.execute_script(SAMPLE_JS)
        except Exception as exc:  # 页面跳转中
            st = {'text': '', 'status': [], 'caseRows': 0, 'err': str(exc)}
        text = st.get('text') or ''
        has_loading = LOADING_HINT in text or any(LOADING_HINT in s for s in st.get('status') or [])
        has_empty = EMPTY_TITLE in text
        has_groups = ALL_GROUPS_MARK in text
        rows = st.get('caseRows', 0)
        group_cards = st.get('groupCards', 0)

        if has_loading and loading_first is None:
            loading_first = t
            if theme == 'light' or loading_shot is None:
                loading_shot = os.path.join(out_dir, 'loading_%s.png' % theme)
                drv.save_screenshot(loading_shot)
        if has_loading:
            loading_last = t
        if has_empty:
            if empty_first is None:
                empty_first = t
                empty_shot = os.path.join(out_dir, 'baseline_empty_%s.png' % theme)
                drv.save_screenshot(empty_shot)
        if group_cards and group_first is None:
            group_first = t
        if rows and rows_first is None:
            rows_first = t

        drain_perf(drv, seen, net, starts)
        tc = net.get('testcases') or []
        if response_done_at is None and tc:
            resp = tc[-1]
            response_done_at = t
        samples.append(
            {
                't': t,
                'loading': has_loading,
                'empty': has_empty,
                'groups_mark': has_groups,
                'case_rows': rows,
                'group_cards': group_cards,
                'text_len': len(text),
            }
        )
        if response_done_at is not None and t - response_done_at >= 2.0:
            break
        time.sleep(0.3)

    # 加载完成截图（渲染稳定后再拍）
    for _ in range(20):
        final = drv.execute_script(SAMPLE_JS)
        if final.get('groupCards', 0) > 0:
            break
        time.sleep(0.3)
    time.sleep(0.8)
    final = drv.execute_script(SAMPLE_JS)
    loaded_shot = os.path.join(out_dir, 'loaded_%s.png' % theme)
    drv.save_screenshot(loaded_shot)

    # 展开一个有用例的分组，验证组内用例行渲染（组内用例按 group_id 懒加载，慢）
    expanded_name = drv.execute_script(EXPAND_JS)
    after_expand = final
    for _ in range(120):
        after_expand = drv.execute_script(SAMPLE_JS)
        if after_expand.get('caseRows', 0) > 0:
            break
        time.sleep(0.5)
    expanded_shot = os.path.join(out_dir, 'expanded_%s.png' % theme)
    drv.save_screenshot(expanded_shot)

    groups = (net.get('groups') or [])
    testcases = (net.get('testcases') or [])
    summary = {
        'label': label,
        'theme': theme,
        'base': base,
        'final_url': drv.current_url,
        'loading_hint_first_s': loading_first,
        'loading_hint_last_s': loading_last,
        'empty_state_first_s': empty_first,
        'groups_rendered_at_s': group_first,
        'case_rows_first_s': rows_first,
        'testcases_response_seen_at_s': response_done_at,
        'groups_http': [(g.get('status'), g.get('duration_ms')) for g in groups],
        'testcases_http': [(g.get('status'), g.get('duration_ms'), g.get('url')) for g in testcases],
        'final_has_empty_state': EMPTY_TITLE in (final.get('text') or ''),
        'final_has_loading_hint': LOADING_HINT in (final.get('text') or ''),
        'final_case_rows': final.get('caseRows'),
        'final_group_cards': final.get('groupCards'),
        'final_text_head': (final.get('text') or '')[:300],
        'expanded_group': expanded_name,
        'rows_after_expand': after_expand.get('caseRows'),
        'samples': len(samples),
        'sample_timeline': samples[:12] + samples[-3:],
        'shots': {
            'loading': loading_shot,
            'baseline_empty': empty_shot,
            'loaded': loaded_shot,
            'expanded': expanded_shot,
        },
    }
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:15247')
    ap.add_argument('--label', default='fix')
    ap.add_argument('--themes', default='light,dark')
    ap.add_argument('--timeout', type=float, default=150.0)
    args = ap.parse_args()

    out_dir = os.path.join(REPO, 'tests', 'ui', 'artifacts', 'int1657_' + args.label)
    drv = build_driver()
    results = []
    try:
        for theme in [t.strip() for t in args.themes.split(',') if t.strip()]:
            results.append(run_theme(drv, args.base, theme, out_dir, args.label, args.timeout))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    out = {'runs': results}
    path = os.path.join(out_dir, 'summary.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print('SUMMARY:', path)


if __name__ == '__main__':
    main()
