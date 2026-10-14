# -*- coding: utf-8 -*-
"""INT-278 验收：ReportView 页面 CSS 非 scoped 全局泄漏（INT-250 同型）。

缺陷口径（issue INT-278）：修复前 ReportView.vue 以非 scoped
``<style src="./reportView.css">`` 全局注入，css 内含
``.btn/.btn-primary/.btn-success/.btn-secondary/.loading-state/
.error-state/.empty-state`` 等全站高频通用类名——访问报告页后全局生效，
污染其他页面同名元素。

修复方案（同 INT-250 pt- / INT-277 tg- 统一修法）：reportView.css 全部
选择器 ``rv-`` 前缀命名空间化（含 keyframes 改名 rv-spin/rv-slideInRight、
id #rv-unified-selector），``<style src>`` 全局注入保留但不再含任何全站
通用裸类名。

验收断言（对应 issue 验收标准「vitest+build 零错误 + 跨页污染实测消失」
中的运行时部分，vitest/build 由验收记录另行收集）：

1. **静态**：reportView.css 源文件不含任何裸通用类选择器（白名单外
   一律 ``rv-`` / ``#rv-`` 前缀；@keyframes 一律 rv- 前缀）。
2. **运行时（核心）**：headless Chrome 真实访问 ``/report/:id``，比对
   访问前后 document.styleSheets 全量 CSS 规则选择器集合——新增规则
   必须全部 ``rv-`` 命名空间（零裸 .btn/.loading-state/... 泄漏）。
3. **跨页污染消失（主验收项）**：访问报告页后转 Tasks / TagManagement /
   HistoryReports，页面探针元素计算样式访问前后一致。
4. **报告页自身样式生效**：.rv-report-view-page 容器渲染、页面标题显示
   （防「前缀化把页面样式改丢」的反向回归）。

环境口径：tests/ui 门禁三件套沿用（RUN_LIVE_STACK=1 显式纳入、隔离库
守卫、引导自举），并行隔离栈跑（run_gate.py，:6000/:6273）。

测试数据卫生：报告数据用隔离库既有 smoke 报告（回收站恢复一条置 live，
teardown 原样放回回收站），零写入残留。
"""
import os

import pytest

from tests.ui.pages.base_page import BasePage

# ── 被测页路由 ────────────────────────────────────────────────
REPORT_ROUTE = '/report/10'      # 隔离库既有 INT-314 smoke 任务报告（published）
# 跨页探针：直接命中 Tasks 页真实 .btn-primary 批量操作按钮——修复前
# reportView.css 泄漏的 .btn/.btn-primary 规则（padding/background/
# border-radius/box-shadow）恰好覆盖其计算样式，探针属性取缺陷规则
# 声明体里与全站基线值不同的字段（padding 10px 24px vs 基线 5px 10px）。
PROBE_PAGES = [
    # (hash 路由, 探针 CSS 选择器)
    ('/tasks', '.btn-primary'),
    ('/TagManagement', '.tg-page-title'),
    ('/history-reports', '.main-content'),
]

# 全站高频通用类名（缺陷清单原始证据集合）：泄漏检测黑名单。
# 这些名字修复前由 reportView.css 全局注入（约 20 条裸规则），修复后
# 只允许经 main.css（全站设计系统本体）与 scoped 组件样式出现。
BARE_GENERIC = {
    'btn', 'btn-primary', 'btn-success', 'btn-secondary',
    'loading-state', 'error-state', 'empty-state', 'loading-spinner',
    'analysis-text', 'analysis-textarea', 'device-info', 'device-name',
    'device-icon-wrapper', 'device-type-tag', 'device-select-item',
    'selection-indicator', 'toast-container', 'toast-success', 'toast-error',
    'toast-warning', 'toast-info', 'floating-actions', 'action-btn',
    'export-dropdown', 'export-menu-item', 'comparison-header',
    'comparison-title', 'comparison-subtitle', 'comparison-selectors',
    'comparison-section', 'selector-title', 'unified-selector',
    'analysis-conclusion-card', 'analysis-icon', 'analysis-content',
    'analysis-header', 'analysis-title', 'analysis-status', 'analysis-edit',
    'analysis-actions', 'edit-field', 'selected', 'api-item', 'published',
    'draft', 'status-dot', 'copy-toast', 'export-dropdown-wrapper',
}


def _collect_selectors(driver) -> set:
    """收集 document.styleSheets 全量规则选择器（含 keyframes 名）。

    只挑「选择器以裸通用类名为最左类」的规则——与缺陷形态一致：
    reportView.css 注入的是 ``.btn { ... }`` 这类顶层裸规则。带祖先
    限定（如 .api-actions .btn）或作用域前缀（.test-view-common .btn）
    的规则不属于本卡泄漏向量。
    """
    script = """
    const out = [];
    for (const sheet of document.styleSheets) {
      let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
      if (!rules) continue;
      const walk = (list) => {
        for (const rule of list) {
          if (rule.type === CSSRule.MEDIA_RULE) { walk(rule.cssRules); continue; }
          if (rule.selectorText) out.push(rule.selectorText);
          if (rule.type === CSSRule.KEYFRAMES_RULE) out.push('@keyframes ' + rule.name);
        }
      };
      walk(rules);
    }
    return out;
    """
    return set(driver.execute_script(script))


def _leaked_bare_rules(selectors) -> list:
    """从选择器集合中挑出「最左 token 是裸通用类」的泄漏规则。"""
    import re
    leaked = []
    for sel in selectors:
        if sel.startswith('@keyframes '):
            name = sel.split('@keyframes ', 1)[1].strip()
            if name in BARE_GENERIC:
                leaked.append(sel)
            continue
        # 取最左 compound selector 的第一个类名
        left = re.split(r'[ >~+,:()\[]', sel.split('::')[0], 1)[0].strip()
        m = re.match(r'^\.([A-Za-z0-9_-]+)', left)
        if m and m.group(1) in BARE_GENERIC:
            leaked.append(sel)
    return sorted(leaked)


@pytest.fixture(scope='module')
def report_live(api_client):
    """把隔离库回收站的 INT-314 smoke 报告(id=10)恢复到 live 供 UI 打开。

    teardown 原样放回回收站（该报告本就是此前 smoke 测试的回收站残留，
    验收零新增数据）。若隔离库无此报告，显式 fail 提示数据前置。
    """
    r = api_client.request('GET', '/reports')
    live_ids = [i['id'] for i in r['data']['items']]
    if 10 in live_ids:
        yield 10
        return
    trash = api_client.request('GET', '/reports?deleted=true')
    trash_ids = [i['id'] for i in trash['data']['items']]
    if 10 not in trash_ids:
        pytest.fail('隔离库缺少预期 smoke 报告 id=10（live 与回收站均无）。'
                    '请以 python tests/ui/run_gate.py 依赖的隔离栈数据为准，'
                    '或先在隔离库重放 smoke 种子。')
    api_client.request('POST', '/reports/10/restore')
    yield 10
    # teardown：放回回收站（恢复原状，不引入残留）
    api_client.request('DELETE', '/reports/10')


class TestInt278CssNamespace:
    """INT-278 验收：rv- 命名空间隔离 + 跨页污染消失。"""

    def test_css_source_has_no_bare_generic_selectors(self):
        """静态：reportView.css 源文件不含裸通用类选择器 / 裸 keyframes。"""
        import re
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'frontend', 'src', 'views', 'ReportView', 'reportView.css')
        with open(css_path, encoding='utf-8') as f:
            css = f.read()
        # 抽全部类选择器（含选择器列表里的每一项）与 keyframes 名
        bare = []
        for sel in re.findall(r'([^{}\n]+)\{', css):
            sel = sel.strip()
            if sel.startswith('@'):
                m = re.match(r'^@keyframes\s+([A-Za-z0-9_-]+)', sel)
                if m and m.group(1) not in BARE_GENERIC and not m.group(1).startswith('rv-'):
                    bare.append(sel)
                continue
            for part in sel.split(','):
                part = part.strip()
                if not part or part.startswith('@'):
                    continue
                left = re.split(r'[ >~+:\(\[]', part.split('::')[0], 1)[0].strip()
                m = re.match(r'^\.([A-Za-z0-9_-]+)', left) or \
                    re.match(r'^#([A-Za-z0-9_-]+)', left)
                if m:
                    name = m.group(1)
                    if name in BARE_GENERIC:
                        bare.append(part)
                    elif not (name.startswith('rv-') or name == 'rv'):
                        bare.append(f'{part}  [非 rv- 命名空间类/id]')
        assert not bare, (
            'reportView.css 存在裸通用类选择器或非 rv- 命名空间选择器'
            f'（INT-278 缺陷回归）：{bare[:10]}')

    def test_report_page_style_flow_adds_only_rv_rules(self, page, report_live):
        """运行时核心：访问 /report/:id 前后样式流新增规则全部 rv- 命名空间。"""
        page.goto('/tasks')
        page.wait_visible('.main-content', timeout=15)
        before = _collect_selectors(page.driver)

        page.goto(REPORT_ROUTE)
        # 报告页自身渲染完成标志：rv- 容器或 loading/error 态出现
        page.wait_visible('.rv-report-view-page, .rv-loading-state, .rv-error-state',
                          timeout=20)
        page.settle(1.0)  # 异步 <style src> 注入余量
        after = _collect_selectors(page.driver)

        added = after - before
        # 报告组件自身的 scoped 规则（data-v hash）不属本卡口径，剔除
        added_scoped = {s for s in added if 'data-v-' in s}
        added_global = added - added_scoped
        leaked = _leaked_bare_rules(added_global)
        assert not leaked, (
            f'访问报告页后全局样式流新增 {len(leaked)} 条裸通用规则'
            f'（INT-278 缺陷回归）：{leaked[:15]}')
        # 正向：新增规则里应有 rv- 命名空间规则（证明报告样式确实注入）
        rv_added = [s for s in added_global if '.rv-' in s or '@keyframes rv-' in s]
        assert rv_added, '访问报告页后未见任何 rv- 命名空间规则注入，报告样式缺失？'

    def test_cross_page_style_pollution_gone(self, page, report_live):
        """主验收项：访问报告页后 Tasks/TagManagement/HistoryReports 探针
        计算样式与基线一致（无样式串扰）。探针命中泄漏规则实际覆盖的
        元素与属性（Tasks .btn-primary 的 padding/background 等）。"""
        def probe(route, selector):
            page.goto(route)
            el = page.find_visible(selector, timeout=20)
            page.settle(0.5)
            return page.driver.execute_script(
                'const s = getComputedStyle(arguments[0]);'
                'return {padding: s.padding, background: s.backgroundColor,'
                'radius: s.borderRadius, shadow: s.boxShadow};', el)

        # 基线（未访问报告页）
        baseline = {route: probe(route, sel) for route, sel in PROBE_PAGES}

        # 访问报告页（全局注入 reportView.css）
        page.goto(REPORT_ROUTE)
        page.wait_visible('.rv-report-view-page, .rv-loading-state, .rv-error-state',
                          timeout=20)
        page.settle(1.0)

        # 复测各页探针
        drift = {}
        for route, sel in PROBE_PAGES:
            now = probe(route, sel)
            if now != baseline[route]:
                drift[route] = {'baseline': baseline[route], 'after': now}
        assert not drift, f'跨页样式串扰（INT-278 缺陷回归）: {drift}'

    def test_report_page_own_style_applied(self, page, report_live):
        """反向回归：报告页自身 rv- 样式正常生效（容器渲染 + 标题/按钮）。"""
        page.goto(REPORT_ROUTE)
        el = page.wait_visible('.rv-report-view-page', timeout=20)
        page.settle(0.8)
        bg = page.driver.execute_script(
            'return getComputedStyle(arguments[0]).backgroundColor;', el)
        assert bg not in ('', 'rgba(0, 0, 0, 0)'), \
            f'.rv-report-view-page 容器样式未生效（background={bg!r}）'
        # 报告标题（task-report-panel 内 h 系或名称文本容器）存在
        assert page.driver.find_elements(
            'css selector', '.task-report-panel') or page.driver.find_elements(
            'css selector', '.rv-comparison-report-container'), \
            '报告内容容器未渲染'
