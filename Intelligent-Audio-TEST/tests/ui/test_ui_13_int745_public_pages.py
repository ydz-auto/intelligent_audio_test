# -*- coding: utf-8 -*-
"""INT-745 UI 实测：公共页（首页门户 + 文档 + 关于 + 排行榜）。

覆盖卡面验收标准（devloop-protocol §2.5.3 浏览器实测 + 截图）：
1. 首页门户 `/`：PublicLayout 公共壳（站头六项 + 页脚，无侧栏），未登录可见；
   去业务统计（.quick-stats 不渲染）；业务受限入口（工作台等）未登录 + 认证开启
   → 「需要登录」Dialog（5 秒倒计时）→ /login?redirect=
2. 文档 `/user-guide` `/user-guide-api`：左目录 + 右内容，手册切换跨路由，
   代码块/表格/复制钮（结构化渲染，未引 marked/shiki）
3. 关于 `/about`：版本/健康状态卡（GET /health 真实数据 V9.7.31/正常）+ 文档链接卡组
4. 排行榜 `/rankings`：Hero 文案「排行榜」，页内算法卡片网格（「全部算法」首卡 +
   每算法一张大卡），不渲染右上角算法切换器；未登录只读降级/错误态，登录后全量
5. 主题切换：.dark 全局生效 + localStorage iatp:theme:v1 持久化
6. 浅/深色两套 + Network（performance resource entries）证据截图

数据卫生：公共页只读，无共享库 fixture 写入，零残留。
"""
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from tests.ui.pages.base_page import BasePage, TOKEN_KEY, USER_KEY

# 与 conftest 同口径（run_gate.py 起栈后注入 UI_API_BASE/UI_FRONTEND_BASE）
FRONTEND = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:6273')

# 证据截图目录（devloop §2.5.3：PNG 随测试结论贴卡）
EVIDENCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'artifacts', 'int745')

NAV_LABELS = ['主页', '工作台', '报告', '排行榜', '文档', '关于']


def _snap(page: BasePage, name: str) -> str:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    path = os.path.join(EVIDENCE_DIR, name)
    page.driver.save_screenshot(path)
    print(f'[INT-745] 截图: {path}')
    return path


def _as_anonymous(page: BasePage):
    """清空登录态并整页重启（公共页未登录口径）。"""
    page.goto('/login')
    page.wait_visible('.login-card', timeout=15)
    page.clear_login_state()
    page.goto('/')
    page.wait_visible('.public-header', timeout=15)
    page.settle(0.5)


def _nav_texts(page: BasePage):
    els = page.find_all('.public-nav .public-nav-link')
    return [e.text.strip() for e in els]


def _dark_theme(page: BasePage, on: bool):
    page.driver.execute_script(
        'document.documentElement.classList.toggle("dark", arguments[0]);', on)
    page.settle(0.3)


def _resource_urls(page: BasePage) -> list:
    """浏览器侧真实发出的请求（Resource Timing API）。"""
    return page.driver.execute_script(
        'return performance.getEntriesByType("resource").map(function(e){return e.name;});')


def test_public_home_portal_shell_and_no_stats(page):
    """首页门户：PublicLayout 公共壳（站头六项 + 页脚）、无侧栏、去业务统计、未登录可见。"""
    _as_anonymous(page)

    # 公共壳：站头 + 顶导航六项，无工作台侧栏
    assert page.find_visible('.public-header', timeout=15), '站头未渲染'
    labels = _nav_texts(page)
    assert labels == NAV_LABELS, f'顶导航六项异常: {labels}'
    assert not page.exists('aside.sidebar'), '公共门户不应渲染工作台侧栏'
    assert page.find_visible('.public-footer', timeout=10), '页脚未渲染'

    # Hero / 流程 / 功能网格 / 信息区
    hero = page.find_visible('.hero-section', timeout=15).text
    assert '智能语音测试系统' in hero, f'Hero 标题异常: {hero[:40]!r}'
    assert page.find_visible('.workflow-section', timeout=10), '流程区未渲染'
    assert page.find_visible('.features-section', timeout=10), '功能网格未渲染'
    assert page.find_visible('.info-section', timeout=10), '信息区未渲染'

    # 去业务统计（QuickStats 移交工作台 /dashboard）
    assert not page.exists('.quick-stats'), '首页门户不应渲染业务统计 QuickStats'

    # 未登录可见：路由 /，无登录弹回
    assert page.current_route() in ('/', ''), f'公共门户未停留 /: {page.current_route()}'

    _snap(page, 'home_light.png')
    _dark_theme(page, True)
    _snap(page, 'home_dark.png')
    _dark_theme(page, False)


def test_public_restricted_entry_login_dialog(page):
    """未登录 + 认证开启：受限业务入口（工作台）弹「需要登录」Dialog → /login?redirect=。"""
    _as_anonymous(page)

    # 点顶导航「工作台」（restricted 项）
    page.click_xpath(
        "//nav[contains(@class,'public-nav')]//*[contains(@class,'public-nav-link') "
        "and normalize-space(.)='工作台']", timeout=10)
    page.wait_visible('.login-required-modal', timeout=10)
    modal = page.find_visible('.login-required-modal', timeout=10)
    assert '需要登录' in page.driver.find_element(By.CSS_SELECTOR, '.modal-title, .lr-description').text \
        or '请登录' in modal.text, f'受限项 Dialog 文案异常: {modal.text[:60]!r}'
    countdown = page.find_visible('.lr-countdown', timeout=5).text
    assert '将在' in countdown and '秒后' in countdown and any(
        c.isdigit() for c in countdown), f'倒计时未渲染: {countdown!r}'
    _snap(page, 'login_required_dialog.png')

    # 5 秒倒计时后自动 confirm → 跳登录页带 redirect
    page.wait.until(
        lambda d: '/login' in d.current_url.split('#')[-1],
        message='受限项 Dialog 后未跳登录页', )
    route = page.current_route()
    assert 'redirect=' in route and 'dashboard' in route, \
        f'登录跳转未带 redirect=/dashboard: {route!r}'


def test_public_user_guide_and_manual_switch(page):
    """文档页：左目录 + 右内容（结构化渲染）、手册切换跨路由、代码块/表格/复制钮。"""
    _as_anonymous(page)

    page.goto('/user-guide')
    page.wait_visible('.guide-container', timeout=15)
    page.settle(0.4)

    # 目录 + 正文（使用手册）
    toc = page.find_visible('.guide-toc', timeout=10).text
    assert '目录' in toc, '目录区未渲染'
    toc_items = page.find_all('.toc-list .toc-link')
    assert len(toc_items) >= 8, f'目录应 ≥8 节，实际 {len(toc_items)}'
    assert page.find_visible('.guide-article', timeout=10), '正文区未渲染'
    assert page.find_visible('.guide-h1', timeout=10), '手册标题未渲染'
    # 首个目录项默认高亮（滚动追踪）
    assert 'active' in (toc_items[0].get_attribute('class') or ''), '首个目录项未高亮'

    # 手册切换 → API 手册（跨路由）
    page.click_xpath(
        "//nav[contains(@class,'guide-manual-switch')]//*[contains(@class,'manual-item') "
        "and normalize-space(.)='API 手册']", timeout=10)
    page.wait.until(lambda d: '/user-guide-api' in d.current_url.split('#')[-1],
                    message='未切到 /user-guide-api')
    page.settle(0.5)
    article = page.find_visible('.guide-article', timeout=10).text
    assert 'API' in article or '接口' in article, f'API 手册正文异常: {article[:60]!r}'

    # 回使用手册：代码块/表格/复制钮就位
    page.goto('/user-guide')
    page.wait_visible('.guide-code-block', timeout=15)
    page.settle(0.3)
    assert page.exists('.guide-table'), '表格未渲染'
    assert page.exists('.copy-btn'), '代码复制钮未渲染'
    _snap(page, 'user_guide_light.png')
    _dark_theme(page, True)
    _snap(page, 'user_guide_dark.png')
    _dark_theme(page, False)


def test_public_about_health_card(page):
    """关于页：版本/健康状态卡（GET /health 真实数据）+ 认证模式 + 文档链接。"""
    _as_anonymous(page)

    page.goto('/about')
    page.wait_visible('.about-page', timeout=15)
    page.settle(1.0)  # 等 /health + /auth/mode 异步返回

    # 版本与服务状态卡：真实 /health 数据
    card = page.find_visible('.about-card', timeout=10).text
    assert '版本与服务状态' in card, '版本状态卡未渲染'
    assert 'V9.7.31' in card, f'健康卡未展示版本 V9.7.31: {card[:80]!r}'
    assert '正常' in card, f'健康卡未展示「正常」徽章: {card[:80]!r}'
    assert 'api_gateway' in card.lower() or '网关' in card, '健康卡未展示网关服务名'
    assert '认证模式' in card, '认证模式行缺失'
    assert 'dev' in card.lower(), f'认证模式应显示 dev: {card[:80]!r}'

    # 文档链接卡组
    links = page.find_all('.doc-link')
    assert len(links) >= 4, f'文档链接卡组应 ≥4 条，实际 {len(links)}'

    # 真实请求证据：/health 经 Vite 代理到网关
    urls = _resource_urls(page)
    assert any('/health' in u for u in urls), f'未见 /health 真实请求: {[u for u in urls if "api" in u][:6]}'
    assert any('auth/mode' in u for u in urls), '未见 /auth/mode 真实请求'

    _snap(page, 'about_light.png')
    _dark_theme(page, True)
    _snap(page, 'about_dark.png')
    _dark_theme(page, False)


def test_public_rankings_page_and_algorithm_grid(page, api_client):
    """排行榜：Hero 文案「排行榜」+ 页内算法卡片网格（不渲染右上角切换器）。

    未登录：只读降级条 + 排行错误态；登录（admin）：算法网格全量卡 + 排行空态。
    """
    # ── 未登录口径（公开可达，数据降级） ──
    _as_anonymous(page)
    page.goto('/rankings')
    page.wait_visible('.benchmark-ranking-view', timeout=15)
    page.settle(0.8)

    hero = page.find_visible('.rankings-hero', timeout=10).text
    assert '排行榜' in hero, f'Hero 标题应「排行榜」: {hero[:40]!r}'
    # 页内算法卡片网格只读降级条（无 algorithm:read）
    assert page.exists('.ag-readonly'), '未登录应渲染算法卡片只读降级条'
    ro = page.find_visible('.ag-readonly', timeout=10).text
    assert '全部算法' in ro, f'只读降级条应显示「全部算法」: {ro[:40]!r}'
    # 不渲染右上角全局算法切换器（PublicHeader 无切换器）
    assert not page.exists('.public-header .algorithm-switcher'), '公共站头不应渲染算法切换器'
    # 排行数据未授权：401 → 错误态（失败 + 重试）
    assert page.exists('.error-state') or page.exists('.empty-state'), \
        '排行榜应呈现错误/空态（数据需登录）'
    _snap(page, 'rankings_anon_light.png')

    # ── 登录（admin）口径：算法卡片网格全量卡 ──
    page.inject_login_state(api_client.token, api_client.user)
    page.goto('/rankings')
    page.wait_visible('.algorithm-card-grid', timeout=15)
    page.settle(1.0)

    cards = page.find_all('.ag-card')
    assert cards, '算法卡片网格未渲染任何卡'
    assert '全部算法' in cards[0].text, f'首卡应为「全部算法」: {cards[0].text[:30]!r}'
    assert len(cards) >= 2, f'网格应 ≥2 张卡（全部算法 + 至少 1 算法），实际 {len(cards)}'
    # 选中「全部算法」首卡高亮（默认态）
    assert 'selected' in (cards[0].get_attribute('class') or ''), '首卡默认应选中'
    # 页内独立：点击某个在线算法卡 → 选中态切换（不写全局 store）
    algo_cards = [c for c in page.find_all('.ag-card')[1:]
                  if 'offline' not in (c.get_attribute('class') or '')]
    assert algo_cards, '网格应有可点选的在线算法卡'
    page.driver.execute_script('arguments[0].click();', algo_cards[0])
    page.settle(0.4)
    selected = [c for c in page.find_all('.ag-card')
                if 'selected' in (c.get_attribute('class') or '')]
    assert selected and selected[0].text != '全部算法', \
        f'点击算法卡后应选中该算法卡（非全部算法）: {[c.text[:16] for c in selected]}'

    # 真实请求证据：algorithm/definitions + benchmarks/ranking
    urls = _resource_urls(page)
    assert any('algorithm/definitions' in u for u in urls), '未见 /algorithm/definitions 真实请求'
    assert any('benchmarks/ranking' in u for u in urls), '未见 /benchmarks/ranking 真实请求'

    _snap(page, 'rankings_light.png')
    _dark_theme(page, True)
    _snap(page, 'rankings_dark.png')
    _dark_theme(page, False)


def test_theme_toggle_persists(page):
    """主题切换：点站头按钮 → .dark 全局生效 + localStorage iatp:theme:v1 持久化。"""
    _as_anonymous(page)

    page.click('.theme-toggle', timeout=10)
    page.settle(0.4)
    assert page.driver.execute_script(
        'return document.documentElement.classList.contains("dark");'), '点击后未进入深色'
    saved = page.driver.execute_script(
        'return localStorage.getItem("iatp:theme:v1");')
    assert saved == 'dark', f'深色未持久化: {saved!r}'

    # 整页刷新后主题恢复（initTheme 读 localStorage）
    page.driver.refresh()
    page.wait_visible('.public-header', timeout=15)
    assert page.driver.execute_script(
        'return document.documentElement.classList.contains("dark");'), '刷新后深色未恢复'

    # 切回浅色，避免影响其它用例
    page.click('.theme-toggle', timeout=10)
    page.settle(0.3)
