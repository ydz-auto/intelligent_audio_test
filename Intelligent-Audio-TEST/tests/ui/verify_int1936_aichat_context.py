# -*- coding: utf-8 -*-
"""INT-1936 验收：/ai-chat?report={id} / ?task={id} 上下文名称走真实接口。

断言（卡面「可测验收标准」）：
1. /ai-chat?report=567（真实报告）→ 上下文条显示真实报告名，Network 有 GET /reports/567 200；
2. /ai-chat?report=999999（不存在）→ 显示「报告 #999999」+ failed 失败态，Network 404；
3. /ai-chat?task=658（真实任务）→ 显示真实任务名，Network 有 GET /tasks/658 200；
4. 三个场景页面内不出现任何 MOCK_REPORTS 演示名（旧实现残留）。

差分探针：/ai-chat?report=320 —— 真实库里的报告 320 名为「拒识E2E测试任务_…测试报告」，
旧实现（MOCK_REPORTS）会写成「T320 唤醒词识别回归测试报告」。同一脚本对 `REACT_BASE`
指向的任一构建跑一次，比对 localStorage 的 iatp:ai-chat:v1:config.reportContextLabel，
即可证明断言对「mock 命中」有区分力。

环境（docker 铁律）：REACT_BASE 默认本卡旁路容器 15276；PHYS_API 默认 15000 网关。
"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from int1494_helpers import clear_perf, driver  # noqa: E402

BASE = os.environ.get('REACT_BASE', 'http://localhost:15276')
OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'artifacts', 'int1936')
os.makedirs(OUT, exist_ok=True)

CHAT_KEYS = ['iatp:ai-chat:v1:config', 'iatp:ai-chat:v1:messages']

# MOCK_REPORTS（infrastructure/mock/ai-chat-mock.ts）里的演示名，任何场景都不得出现
MOCK_NAMES = [
    'T320 唤醒词识别回归测试报告',
    'T319 远场唤醒性能对比报告',
    'T317 噪声场景鲁棒性二次对比报告',
    'T315 端到端唤醒延迟测试报告',
    '任务 #320 唤醒词识别回归',
    '任务 #315 唤醒延迟基线',
    '任务 #308 噪声场景信噪比分层',
]

R = []


def rec(item, passed, detail, shots=()):
    R.append({'item': item, 'pass': bool(passed), 'detail': detail,
              'shots': list(shots)})
    print(('PASS ' if passed else 'FAIL ') + item + ' :: ' + str(detail)[:400])


def set_theme(d, mode):
    d.get(BASE + '/user-guide')
    d.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def clear_chat_prefs(d):
    d.execute_script(
        "arguments[0].forEach(function (k) { window.localStorage.removeItem(k); });",
        CHAT_KEYS)


def read_chat_config(d):
    raw = d.execute_script(
        "return window.localStorage.getItem('iatp:ai-chat:v1:config');")
    if not raw:
        return None
    try:
        return json.loads(raw).get('data')
    except Exception:
        return {'__raw__': raw}


def api_entries(d, needle):
    """performance log 里的 Network.responseReceived，按 URL 片段过滤。"""
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:
        return out
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg.get('params', {}).get('response', {})
        url = resp.get('url', '')
        if needle not in url:
            continue
        out.append({'url': url, 'status': resp.get('status')})
    return out


def wait_status(d, want, timeout=40):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        els = d.find_elements(By.CSS_SELECTOR, '[data-chat-context-status]')
        if els:
            last = els[0].get_attribute('data-chat-context-status')
            if last == want:
                return last, els[0]
        time.sleep(0.25)
    return last, (els[0] if els else None)


def badges(d):
    out = []
    for el in d.find_elements(By.CSS_SELECTOR, '[data-chat-context-status]'):
        out.append({'status': el.get_attribute('data-chat-context-status'),
                    'text': el.text})
    return out


def page_has_mock(d):
    html = d.execute_script('return document.documentElement.innerHTML;') or ''
    return [n for n in MOCK_NAMES if n in html]


def scenario(d, path, theme, needle, want_status, shot_name):
    set_theme(d, theme)
    clear_chat_prefs(d)
    clear_perf(d)
    d.get(BASE + path)
    try:
        WebDriverWait(d, 45).until(
            lambda x: x.execute_script('return document.readyState') == 'complete')
    except Exception:
        pass
    status, el = wait_status(d, want_status)
    # 等 Network 记录落地（get_log 是「取后清空」，只取一次，避免把证据抽干）
    api = []
    for _ in range(40):
        api = api_entries(d, needle)
        if api:
            break
        time.sleep(0.25)
    path_shot = os.path.join(OUT, shot_name + '.png')
    d.save_screenshot(path_shot)
    info = {
        'path': path,
        'theme': theme,
        'badge_status': status,
        'badge_text': (el.text if el is not None else None),
        'badges': badges(d),
        'api': api,
        'local_config': read_chat_config(d),
        'mock_in_page': page_has_mock(d),
        'shot': os.path.basename(path_shot),
    }
    return info


def main():
    d = driver()
    try:
        d.get(BASE + '/')
        time.sleep(1)
        print('BASE =', BASE)
        print('bundle =', d.execute_script(
            "return Array.from(document.querySelectorAll('script[src]'))"
            ".map(function(s){return s.src.split('/').pop();}).join(',')"))

        # ---- 场景 1：真实报告 567 ----
        light = scenario(d, '/ai-chat?report=567', 'light', '/reports/567',
                         'resolved', 'report567-light')
        dark = scenario(d, '/ai-chat?report=567', 'dark', '/reports/567',
                        'resolved', 'report567-dark')
        cfg = light['local_config'] or {}
        ok = (light['badge_status'] == 'resolved'
              and light['badge_text'] == '对比报告_20261023211734'
              and any(e['status'] == 200 for e in light['api'])
              and cfg.get('reportContextId') == '567'
              and cfg.get('reportContextLabel') == '对比报告_20261023211734'
              and not light['mock_in_page'])
        rec('report=567 显示真实报告名 + GET /reports/567 200 + 无 mock',
            ok, light)
        rec('report=567 深色同口径', dark['badge_status'] == 'resolved'
            and dark['badge_text'] == '对比报告_20261023211734',
            {'status': dark['badge_status'], 'text': dark['badge_text'],
             'shot': dark['shot'], 'mock_in_page': dark['mock_in_page']})

        # ---- 场景 2：不存在的报告 999999 ----
        miss_l = scenario(d, '/ai-chat?report=999999', 'light', '/reports/999999',
                          'failed', 'report999999-light')
        miss_d = scenario(d, '/ai-chat?report=999999', 'dark', '/reports/999999',
                          'failed', 'report999999-dark')
        cfg2 = miss_l['local_config'] or {}
        ok2 = (miss_l['badge_status'] == 'failed'
               and miss_l['badge_text'] == '报告 #999999'
               and any(e['status'] == 404 for e in miss_l['api'])
               and cfg2.get('reportContextLabel') == '报告 #999999'
               and not miss_l['mock_in_page'])
        rec('report=999999 降级「报告 #999999」+ failed + GET 404 + 无 mock',
            ok2, miss_l)
        rec('report=999999 深色同口径', miss_d['badge_status'] == 'failed'
            and miss_d['badge_text'] == '报告 #999999',
            {'status': miss_d['badge_status'], 'text': miss_d['badge_text'],
             'shot': miss_d['shot'], 'mock_in_page': miss_d['mock_in_page']})

        # ---- 场景 3：真实任务 658 ----
        task = scenario(d, '/ai-chat?task=658', 'light', '/tasks/658',
                        'resolved', 'task658-light')
        cfg3 = task['local_config'] or {}
        ok3 = (task['badge_status'] == 'resolved'
               and task['badge_text'] == '接线测试_INT1716_AUDIT_B'
               and any(e['status'] == 200 for e in task['api'])
               and cfg3.get('reportContextType') == 'task_context'
               and not task['mock_in_page'])
        rec('task=658 显示真实任务名 + GET /tasks/658 200 + task_context',
            ok3, task)

        # ---- 差分探针：report=320（mock 表里也有 320，演示名 T320…） ----
        probe = scenario(d, '/ai-chat?report=320', 'light', '/reports/320',
                         'resolved', 'report320-differential')
        cfg4 = probe['local_config'] or {}
        rec('差分：真实报告 320 不是 mock 演示名 T320',
            cfg4.get('reportContextLabel') == '拒识E2E测试任务_2026/9/21 11:24:45 - 测试报告'
            and not probe['mock_in_page'],
            {'badge': probe['badge_text'],
             'local_label': cfg4.get('reportContextLabel'),
             'mock_in_page': probe['mock_in_page'],
             'api': probe['api'], 'shot': probe['shot']})

        # ---- 场景 4：裸入口无 URL 上下文 ----
        set_theme(d, 'light')
        clear_chat_prefs(d)
        clear_perf(d)
        d.get(BASE + '/ai-chat')
        time.sleep(3)
        bare_shot = os.path.join(OUT, 'bare-light.png')
        d.save_screenshot(bare_shot)
        rec('裸 /ai-chat（无 URL 上下文）不出现 failed 上下文条',
            not [b for b in badges(d) if b['status'] != 'idle'],
            {'badges': badges(d), 'shot': os.path.basename(bare_shot)})

    except Exception:
        import traceback
        traceback.print_exc()
        rec('脚本异常', False, traceback.format_exc()[-1500:])
    finally:
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(OUT, 'result_%s.json' % (
                'new' if '15276' in BASE else BASE.split(':')[-1])), 'w',
                encoding='utf-8') as f:
            json.dump({'base': BASE, 'items': R}, f, ensure_ascii=False,
                      indent=2)
        print('\n==== SUMMARY ====')
        bad = [r for r in R if not r['pass']]
        print('PASS %d / %d' % (len(R) - len(bad), len(R)))
        for r in bad:
            print('FAILED:', r['item'])
        sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
