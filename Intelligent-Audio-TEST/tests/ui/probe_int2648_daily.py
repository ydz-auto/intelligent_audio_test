# -*- coding: utf-8 -*-
"""INT-2648 前端回归日巡补充实测（React docker 栈 15173，只读）。

本探针补三件上一轮（INT-2638）之后合入 V10.11.2 的界面增量，其余页/链路沿用
smoke_react_nav_walk_int2136 / smoke_frontend_int1919 / probe_int2441 / probe_int2445 /
probe_int2628 / probe_int2638 / probe_int2640：

  1. `int2641`：开始测试第二步实验室 facet 选项来自真实 GET /laboratories
     （只有「全部实验室 / LAB-A」，无旗舰/车载/入门虚构实验室），设备按真实
     lab_id 过滤、API 区不被实验室 facet 误伤、系统类型筛空时出空态并可还原。
  2. `int2639`：报告详情统计卡新增 P90 / P95 两行，值随原始数据算出（客户端
     calculateDistributionStats），浅色 / 深色各截一张。
  3. `aichat`：/ai-chat 的「目标模式」切换器（INT-2477 后续文案收敛，原「对话/Auto」
     三段切换改为单按钮 toggle）：点开出现五维预算设置，再点回普通对话；
     旧探针 probe_int2628 按旧文案断言 Auto，属测试代码过期，不是产品缺陷。

只读语义：只打开弹层 / 切换筛选、不提交任何写请求、不写库。
跑法：
  python tests/ui/probe_int2648_daily.py int2641 --base http://localhost:15173 --api http://localhost:15000
  python tests/ui/probe_int2648_daily.py int2639 --base http://localhost:15173
  python tests/ui/probe_int2648_daily.py aichat  --base http://localhost:15173
  python tests/ui/probe_int2648_daily.py all     # 依次跑三项
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2648')
FAKE_LABS = ('旗舰实验室', '车载实验室', '入门实验室')


class Probe:
    def __init__(self, base, api, username, password):
        self.base = base.rstrip('/')
        self.api = api.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-42s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def shot(self, page, name):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, name + '.png')
        page.screenshot(path=path)
        return path

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=45000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)

    @staticmethod
    def set_dark(page, on):
        page.evaluate("on => document.documentElement.classList.toggle('dark', on)", on)
        page.wait_for_timeout(600)

    # ── 通用：Select 当前文案 / 打开后选项 ─────────────────────
    @staticmethod
    def trigger_by_text(page, text):
        """文案为 text 的 Base UI Select 触发器（button）。选中后文案会变，需先取再复用。"""
        return page.locator('button').filter(has_text=text).first

    @staticmethod
    def open_options(page):
        return [t.strip() for t in page.locator('[role=option]').all_inner_texts() if t.strip()]

    @staticmethod
    def pick(page, trigger, option_text):
        trigger.click()
        page.wait_for_timeout(500)
        page.locator('[role=option]').filter(has_text=option_text).first.click()
        page.wait_for_timeout(800)


def mode_int2641(p, args):
    """INT-2641：开始测试 step2 实验室 facet 真实化。"""
    from tests.ui.utils.api_client import ApiClient
    api = ApiClient(p.api)
    api.login(p.username, p.password)
    labs = api.request('GET', '/laboratories?page=1&per_page=1000').get('data') or {}
    lab_items = labs.get('items') if isinstance(labs, dict) else labs
    lab_items = lab_items or []
    devs = api.request('GET', '/test-devices?page=1&per_page=1000').get('data') or {}
    dev_items = devs.get('items') if isinstance(devs, dict) else devs
    dev_items = dev_items or []
    print('API_LABS=' + json.dumps(lab_items, ensure_ascii=False), flush=True)
    print('API_DEVICES=%d' % len(dev_items), flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        p.login(page)
        page.goto(p.base + '/start-test?step=1&view=card', wait_until='domcontentloaded')
        page.wait_for_timeout(3500)
        # 当前版本 step=1 直达即同屏渲染资源选择；若停在第一步（有「下一步」且无实验室 facet）再前进
        if page.locator('button').filter(has_text='全部实验室').count() == 0:
            page.get_by_role('button', name='下一步').first.click()
            page.wait_for_timeout(3000)

        # 1) facet 选项 = 全部实验室 + 真实实验室，不含虚构实验室
        lab_trigger = p.trigger_by_text(page, '全部实验室')
        lab_trigger.click()
        page.wait_for_timeout(500)
        options = p.open_options(page)
        page.keyboard.press('Escape')
        page.wait_for_timeout(400)
        real_names = [l.get('name') for l in lab_items]
        expected = ['全部实验室'] + real_names
        fake_hit = [o for o in options if any(f in o for f in FAKE_LABS)]
        p.check('lab_facet_from_real_api', options == expected,
                'options=%s expected=%s' % (options, expected))
        p.check('lab_facet_no_fake_labs', not fake_hit,
                'fake=%s' % fake_hit)

        # 2) 选真实实验室：设备/API 计数不变（6 台均属 LAB-A；API 不挂实验室）
        if real_names:
            p.pick(page, lab_trigger, real_names[0])
            counts = page.evaluate("""() => {
              const m = (document.body.innerText || '').match(/共 (\\d+) 台设备 · (\\d+) 个 API/);
              return m ? [Number(m[1]), Number(m[2])] : null;
            }""")
            p.check('lab_filter_counts_unchanged', counts == [len(dev_items), 3],
                    'counts=%s devices_api=%d apis_expected=3' % (counts, len(dev_items)))
            p.shot(page, 'int2641_lab_selected_light')
            p.set_dark(page, True)
            p.shot(page, 'int2641_lab_selected_dark')
            p.set_dark(page, False)

        # 3) 系统类型筛 Android（0 命中）→ 设备区空态 + 计数归零；还原
        sys_trigger = p.trigger_by_text(page, '全部系统')
        p.pick(page, sys_trigger, 'Android')
        empty = page.locator('text=当前筛选条件下没有可用设备').count() > 0
        zero_counts = page.evaluate("""() => {
          const m = (document.body.innerText || '').match(/共 (\\d+) 台设备 · (\\d+) 个 API/);
          return m ? [Number(m[1]), Number(m[2])] : null;
        }""")
        p.check('system_filter_empty_state', empty and zero_counts == [0, 0],
                'empty=%s counts=%s' % (empty, zero_counts))
        p.shot(page, 'int2641_system_android_empty')
        # 还原（触发器文案已变成 Android，重新定位）
        p.pick(page, p.trigger_by_text(page, 'Android'), '全部系统')
        restored = page.evaluate("""() => {
          const m = (document.body.innerText || '').match(/共 (\\d+) 台设备 · (\\d+) 个 API/);
          return m ? [Number(m[1]), Number(m[2])] : null;
        }""")
        p.check('system_filter_restored', restored == [len(dev_items), 3], 'counts=%s' % (restored,))
        # 全树无虚构实验室残留走代码侧 grep，不在此重复
        browser.close()


def mode_int2639(p, args):
    """INT-2639：报告详情统计卡 P90/P95。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        p.login(page)
        page.goto(p.base + '/report-center', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        page.locator('tbody tr').first.click()
        page.wait_for_timeout(5000)
        # 统计卡在「正态分布图」视图下渲染（默认表格视图不挂 ChartStatsCard）
        dist_btn = page.locator('button').filter(has_text='正态分布图')
        if dist_btn.count():
            dist_btn.first.click()
            page.wait_for_timeout(2500)
        # 统计卡在报告详情图表区；必要时滚动让懒渲染出来
        for _ in range(3):
            page.mouse.wheel(0, 700)
            page.wait_for_timeout(500)
        stats = page.evaluate("""() => {
          const out = [];
          const nodes = Array.from(document.querySelectorAll('div.rounded-xl.border.p-3'));
          for (const n of nodes) {
            const title = (n.innerText || '').includes('统计信息');
            if (!title) continue;
            const txt = n.innerText || '';
            const p90 = txt.match(/P90\\s*([-\\d.]+)/);
            const p95 = txt.match(/P95\\s*([-\\d.]+)/);
            out.push({hasTitle: true, p90: p90 ? p90[1] : null, p95: p95 ? p95[1] : null,
                      sample: txt.slice(0, 160)});
          }
          return out;
        }""")
        p.check('report_stats_card_present', len(stats) > 0, 'cards=%d' % len(stats))
        ok_rows = [s for s in stats if s['p90'] and s['p95']]
        p.check('report_stats_p90_p95_rendered', len(ok_rows) == len(stats) and len(stats) > 0,
                'cards=%d with_p90_p95=%d sample=%s' % (len(stats), len(ok_rows),
                                                        ok_rows[0]['sample'] if ok_rows else ''))
        p.shot(page, 'int2639_report_stats_light')
        p.set_dark(page, True)
        p.shot(page, 'int2639_report_stats_dark')
        p.set_dark(page, False)
        browser.close()


def mode_aichat(p, args):
    """/ai-chat「目标模式」切换器：点开五维预算、再点回普通对话。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
        page = ctx.new_page()
        p.login(page)
        page.goto(p.base + '/ai-chat', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        sw = page.locator('[data-agent-mode-switcher]')
        present = sw.count() > 0
        mode0 = sw.first.get_attribute('data-agent-mode-switcher') if present else None
        label = sw.first.inner_text().strip() if present else ''
        p.check('aichat_switcher_present', present and mode0 == 'chat' and label == '目标模式',
                'present=%s mode=%s label=%r' % (present, mode0, label))
        p.shot(page, 'aichat_chat_mode')
        if present:
            sw.first.click()
            page.wait_for_timeout(1200)
            mode1 = page.locator('[data-agent-mode-switcher]').first.get_attribute(
                'data-agent-mode-switcher')
            budget = page.locator('[data-auto-budget-settings]')
            has_budget = budget.count() > 0
            # 面板默认展开（useState(true)），五个维度输入框与标签同屏可见
            labels = []
            inputs = 0
            if has_budget:
                txt = budget.first.inner_text()
                labels = [k for k in ('最大轮次', '最大工具调用', '最大 token（输入+输出）',
                                      '最大时长', '最大输出') if k in txt]
                inputs = budget.first.locator('input').count()
            p.check('aichat_auto_mode_budget_panel',
                    mode1 == 'auto' and has_budget and len(labels) == 5 and inputs == 5,
                    'mode=%s budget=%s fields=%s inputs=%d' % (mode1, has_budget, labels, inputs))
            p.shot(page, 'aichat_auto_budget_light')
            p.set_dark(page, True)
            p.shot(page, 'aichat_auto_budget_dark')
            p.set_dark(page, False)
            page.locator('[data-agent-mode-switcher]').first.click()
            page.wait_for_timeout(1000)
            mode2 = page.locator('[data-agent-mode-switcher]').first.get_attribute(
                'data-agent-mode-switcher')
            budget_gone = page.locator('[data-auto-budget-settings]').count() == 0
            p.check('aichat_toggle_back_to_chat', mode2 == 'chat' and budget_gone,
                    'mode=%s budget_removed=%s' % (mode2, budget_gone))
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['int2641', 'int2639', 'aichat', 'all'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()
    p = Probe(args.base, args.api, args.username, args.password)
    modes = ['int2641', 'int2639', 'aichat'] if args.mode == 'all' else [args.mode]
    for m in modes:
        print('=== MODE %s ===' % m, flush=True)
        globals()['mode_%s' % m](p, args)
    p.checks and os.makedirs(ART, exist_ok=True)
    summary = os.path.join(ART, 'summary.json')
    with open(summary, 'w', encoding='utf-8') as f:
        json.dump(p.checks, f, ensure_ascii=False, indent=2)
    total = len(p.checks)
    passed = len([c for c in p.checks if c['ok']])
    print('PASSED=%d FAILED=%d' % (passed, total - passed), flush=True)
    print('SUMMARY_JSON=%s' % summary, flush=True)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
