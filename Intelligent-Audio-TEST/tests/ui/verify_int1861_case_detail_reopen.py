# -*- coding: utf-8 -*-
"""INT-1861 验收：case-detail 弹窗**同一用例**关闭重开后，轮次 Tab 复位到第一个有数据的 Tab。

缺陷（INT-1486 复走 P3-2）：弹窗由父层常驻挂载（`open` 开关），`tabChoice` 只按 caseId 键控，
同用例重开沿用上次选中态（停在「整体」）；V9.7.10 的详情组件随数据挂载，每次打开重新初始化。

本脚本用真实多轮用例（任务 407 / d8bdd5a6… DD139，8 枚 Tab = 第1轮…第7轮 + 整体）实测：
1. 全新打开 → 默认落在第一个有数据的 Tab（该用例第 1 轮无指标值 → 第2轮）；
2. 点「整体」→ Esc 关闭 → **同页重开同一用例** → 必须回到第2轮（= 全新打开的口径）；
3. 深色同口径；浅 / 深色各截「打开 / 重开」两张图；
4. Network：重开时 detail / results / logs 均 200；
5. 回归：同页换用例仍按 caseId 复位到第一个有数据的 Tab。

用法：
  REACT_BASE=http://127.0.0.1:15263 python verify_int1861_case_detail_reopen.py   # 修复侧旁路容器
  REACT_BASE=http://127.0.0.1:15173 python verify_int1861_case_detail_reopen.py   # 旧镜像对照（应失败）
"""
import importlib.util
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ART = os.path.join(HERE, 'artifacts', 'int1861-reopen')

os.environ.setdefault('REACT_BASE', 'http://127.0.0.1:15263')
os.environ.setdefault('BACKEND_BASE', 'http://127.0.0.1:15000')
os.environ.setdefault('ART_DIR', DEFAULT_ART)

_spec = importlib.util.spec_from_file_location(
    'int1688h', os.path.join(HERE, 'verify_int1688_case_detail_dialog.py')
)
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)

# 本卡用任务 407（实施者复现用的同一任务；用例与 402 同一条）
h.TASK_ID = int(os.environ.get('TASK_ID', '407'))
BASE = h.BASE
ART = h.ART
MULTI = h.MULTI_CASE_ID
MULTI_FRAG = h.MULTI_FRAG
SINGLE_FRAG = h.SINGLE_FRAG
DARK_KEY = h.DARK_KEY

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# 关掉的 base-ui 弹窗可能以 aria-hidden 留在 DOM：一律只认「可见」的那一个，且取最后一个
DLG_JS = r"""
const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
    && !e.closest('[aria-hidden="true"]'); };
return [...document.querySelectorAll('[data-slot="case-detail-dialog"]')].filter(vis).length;
"""

COLLECT_JS = r"""
const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
    && !e.closest('[aria-hidden="true"]'); };
const dlg = [...document.querySelectorAll('[data-slot="case-detail-dialog"]')].filter(vis).pop();
if (!dlg) return null;
const tabs = [...dlg.querySelectorAll('[role="tab"]')].map(b => ({
  label: (b.textContent || '').trim(),
  selected: b.getAttribute('aria-selected') === 'true',
}));
const head = dlg.querySelector('[data-slot="dialog-header"]') || dlg;
return {
  tabs,
  selected: tabs.filter(t => t.selected).map(t => t.label),
  dialogText: dlg.textContent || '',
  headerText: head.textContent || '',
};
"""


def dialog_open(drv):
    return drv.execute_script(DLG_JS) > 0


def collect(drv):
    return drv.execute_script(COLLECT_JS) or {}


def wait_dialog(drv, want, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: dialog_open(d) == want)
    time.sleep(0.6)


def close_dialog(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    wait_dialog(drv, False, timeout=20)
    time.sleep(0.8)


SEARCH_XPATH = "//input[@placeholder='搜索用例名称或 ID…']"


def ensure_case_list(drv):
    """任务详情页的「用例清单」默认折叠：先展开，拿到用例搜索框。"""
    try:
        return drv.find_element(By.XPATH, SEARCH_XPATH)
    except Exception:
        btn = WebDriverWait(drv, 180).until(
            lambda d: d.find_element(By.XPATH, "//button[contains(normalize-space(.),'用例清单')]")
        )
        h.js_click(drv, btn, 2.5)
        return WebDriverWait(drv, 60).until(lambda d: d.find_element(By.XPATH, SEARCH_XPATH))


def search_case(drv, frag):
    box = ensure_case_list(drv)
    h.js_click(drv, box, 0.3)
    # React 受控输入：用键盘全选替换（element.clear() 不触发 onChange）
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.BACKSPACE)
    time.sleep(0.4)
    box.send_keys(frag)
    time.sleep(2.5)


def open_case_button(drv, frag):
    return WebDriverWait(drv, 60).until(
        lambda d: d.find_elements(
            By.XPATH,
            "//button[starts-with(@title,'查看用例详情：')][contains(@title,'%s')]" % frag,
        )
    )[0]


def open_case(drv, frag):
    h.goto(drv, '/tasks/%d' % h.TASK_ID, wait=5)
    WebDriverWait(drv, 180).until(
        lambda d: '用例清单' in (d.execute_script('return document.body.innerText') or '')
    )
    search_case(drv, frag)
    h.js_click(drv, open_case_button(drv, frag), 1.0)
    wait_dialog(drv, True)
    h.wait_text(drv, '执行结果与指标', 90)
    time.sleep(1.2)


def reopen_same_case(drv, frag):
    """同页重开同一用例（不 reload）：点列表里的「查看用例详情」按钮。"""
    h.js_click(drv, open_case_button(drv, frag), 1.0)
    wait_dialog(drv, True)
    h.wait_text(drv, '执行结果与指标', 90)
    time.sleep(1.2)


def shot(drv, name):
    path = h.shot(drv, name)
    return path


def first_with_data(expected):
    return next(
        (t['label'] for t in expected['tabs'] if h.tab_has_data(t)),
        expected['tabs'][0]['label'],
    )


def reopen_round(drv, expected, tag, shot_prefix):
    """切「整体」→ 关闭 → 同用例重开 → 复位到第一个有数据的 Tab。"""
    want = first_with_data(expected)
    fresh = collect(drv)
    h.check('%s：全新打开默认选中「%s」' % (tag, want), fresh.get('selected') == [want],
            fresh.get('selected'))
    h.check('%s：轮次 Tab 列表 = %s' % (tag, [t['label'] for t in expected['tabs']]),
            [t['label'] for t in fresh.get('tabs', [])] == [t['label'] for t in expected['tabs']],
            fresh.get('tabs'))
    shot(drv, shot_prefix + '_open')

    overall = expected['tabs'][-1]['label']
    h.click_tab(drv, overall)
    stuck = collect(drv)
    h.check('%s：点「%s」后选中它' % (tag, overall), stuck.get('selected') == [overall],
            stuck.get('selected'))

    close_dialog(drv)
    h.check('%s：Esc 关闭后弹窗不再可见' % tag, not dialog_open(drv), '')

    reopen_same_case(drv, MULTI_FRAG)
    back = collect(drv)
    h.check('%s：同用例重开复位到第一个有数据的 Tab「%s」（缺陷点是停在「%s」）'
            % (tag, want, overall), back.get('selected') == [want],
            {'want': [want], 'got': back.get('selected'), 'tabs': back.get('tabs')})
    h.check('%s：重开后「%s」不再是选中态' % (tag, overall),
            overall not in (back.get('selected') or []), back.get('selected'))
    h.check('%s：重开后选中态与全新打开逐字一致' % tag,
            back.get('selected') == fresh.get('selected'),
            {'fresh': fresh.get('selected'), 'reopen': back.get('selected')})
    shot(drv, shot_prefix + '_reopen')
    return back


def net_capture(drv):
    log = h.network_responses(drv)
    return {
        'detail': h.network_status(log, '/cases/%s/detail' % MULTI),
        'results': h.network_status(log, '/cases/%s/results' % MULTI),
        'logs': [e for e in h.network_status(log, '/api/v1/logs') if MULTI in e[0] or 'logs' in e[0]],
    }


def main():
    expected = h.expected_view(MULTI)
    want = first_with_data(expected)
    print('期望：Tab=%s / 第一个有数据=%s' % ([t['label'] for t in expected['tabs']], want))
    evidence = {'base': BASE, 'task': h.TASK_ID, 'case': MULTI, 'want_first': want,
                'tabs': [t['label'] for t in expected['tabs']], 'shots': {}, 'network': {}}
    drv = h.build_driver()
    try:
        h.goto(drv, '/tasks/%d' % h.TASK_ID, wait=2)
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)
        # ---------- 浅色 ----------
        open_case(drv, MULTI_FRAG)
        reopen_round(drv, expected, '浅色', 'int1861_light')
        evidence['shots']['light_open'] = os.path.join(ART, 'int1861_light_open.png')
        evidence['shots']['light_reopen'] = os.path.join(ART, 'int1861_light_reopen.png')

        net = net_capture(drv)
        evidence['network'] = net
        h.check('Network：重开时 GET .../detail → 200',
                any(c == 200 for _, c in net['detail']), net['detail'])
        h.check('Network：重开时 GET .../results → 200',
                any(c == 200 for _, c in net['results']), net['results'])
        h.check('Network：重开时 GET /api/v1/logs → 200',
                any(c == 200 for _, c in net['logs']), net['logs'])

        # ---------- 回归：同页换用例仍复位 ----------
        close_dialog(drv)
        single = h.expected_view(h.SINGLE_CASE_ID)
        search_case(drv, SINGLE_FRAG)
        h.js_click(drv, open_case_button(drv, SINGLE_FRAG), 1.0)
        wait_dialog(drv, True)
        h.wait_text(drv, '执行结果与指标', 90)
        time.sleep(1.2)
        got = collect(drv)
        single_want = first_with_data(single)
        # 单轮用例只有 1 枚 Tab，按设计不渲染轮次 Tab 条（roundTabs.length > 1 才出），直接展示指标表
        h.check('回归：换到单轮用例后无轮次 Tab 条（单 Tab 不渲染）、指标表正常',
                got.get('tabs') == []
                and '执行结果与指标' in (got.get('dialogText') or '')
                and '接管率占比' in (got.get('dialogText') or ''),
                {'tabs': got.get('tabs'), 'text': (got.get('dialogText') or '')[:200]})
        h.check('回归：单轮用例期望 Tab 口径 = %s（仅 1 枚，无轮次条）' % single_want,
                [t['label'] for t in single['tabs']] == ['指标'], single['tabs'])

        # ---------- 深色 ----------
        drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
        open_case(drv, MULTI_FRAG)
        dark_html = drv.execute_script('return document.documentElement.className')
        h.check('深色主题已生效', 'dark' in (dark_html or ''), dark_html)
        reopen_round(drv, expected, '深色', 'int1861_dark')
        evidence['shots']['dark_open'] = os.path.join(ART, 'int1861_dark_open.png')
        evidence['shots']['dark_reopen'] = os.path.join(ART, 'int1861_dark_reopen.png')
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    failed = [r for r in h.RESULT if not r['ok']]
    evidence['checks'] = h.RESULT
    evidence['failed'] = len(failed)
    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print('\n==== %d checks, %d failed (base=%s) ====' % (len(h.RESULT), len(failed), BASE))
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
