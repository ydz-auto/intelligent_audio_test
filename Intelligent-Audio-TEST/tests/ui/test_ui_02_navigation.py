# -*- coding: utf-8 -*-
"""INT-260 首批 UI 用例 · 导航域：侧栏点击导航 / 直达路由 / 未登录重定向。

导航=人手操作的核心路径：侧栏 hover 展开 → 点击菜单项 → 目标页渲染断言
（document.title 由路由守卫统一写入，含页名与站点名，防"点了没反应"回归）。
"""
import pytest

from tests.ui.pages.test_case_page import TestCasePage

# （菜单标签, hash 路由, 期望 document.title 前缀）
NAV_TARGETS = [
    ('用例管理', '/TestCaseManager', '用例管理'),
    ('设备管理', '/Device', '设备管理'),
    ('标签管理', '/TagManagement', '标签管理'),
    ('算法配置', '/AlgorithmConfig', '算法配置'),
]


def test_sidebar_navigation_click_through(page):
    """侧栏逐项点击：路由变化 + 目标页标题渲染（防菜单点击失灵回归）。"""
    page.goto('/')
    page.wait_visible('.main-content', timeout=15)
    page.hover('.sidebar', timeout=10)  # 默认折叠，hover 展开

    for label, route, title_prefix in NAV_TARGETS:
        page.hover('.sidebar', timeout=10)  # 折叠态先 hover 展开（人手操作等价）
        page.click_xpath(
            "//aside[contains(@class,'sidebar')]//a[contains(@class,'navLink') "
            f"and contains(normalize-space(.),\"{label}\")]")
        page.wait.until(lambda d, r=route: d.current_url.split('#')[-1].startswith(r))
        assert title_prefix in page.document_title(), \
            f'点击「{label}」后 document.title={page.document_title()!r}，未含 {title_prefix!r}'
        page.wait_visible('.main-content > *', timeout=15)
    page.hover('.sidebar', timeout=10)


def test_direct_url_routes_render(page):
    """直达 hash 路由：各页面按路由渲染对应标题（防路由表回归）。"""
    targets = [
        ('/TestCaseManager', '用例管理', '.test-case-list-container'),
        ('/Evaluation', '评估维度管理', '.search-input'),
        ('/tasks', '测试任务记录', '.main-content'),
        ('/Device', '设备管理', '.main-content'),
        ('/TagManagement', '标签管理', '.main-content'),
    ]
    for route, title_prefix, marker in targets:
        page.goto(route)
        page.wait_visible(marker, timeout=20)
        assert title_prefix in page.document_title(), \
            f'直达 {route} 后 document.title={page.document_title()!r}，未含 {title_prefix!r}'


def test_unauthenticated_redirects_to_login(driver, page):
    """清除登录态后访问受保护路由 → 路由守卫弹回 /login 并带 redirect 参数。"""
    driver.execute_script('window.localStorage.clear();')
    page.goto('/TestCaseManager')
    page.wait_visible('.login-card', timeout=15)
    assert '/login' in page.current_route(), '未登录访问受保护路由未被弹回 /login'
    assert 'redirect' in page.current_route(), '重定向缺少 redirect 参数（登录后无法回跳原页）'


def test_case_manager_page_loads(page):
    """用例列表加载：页头/工具栏/视图切换器渲染 + 列表容器就绪（防页面白屏回归）。"""
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)
    assert '测试用例管理' in tc.page_title_text(), \
        f'页头标题异常: {tc.page_title_text()!r}'
    assert tc.exists(tc.VIEW_SWITCHER), '视图切换器未渲染'
    assert tc.exists(tc.GROUP_VIEW_BTN) and tc.exists(tc.TAG_VIEW_BTN), '分组/标签切换按钮缺失'
    assert tc.view_mode() == 'group', '默认视图应为分组视图'
    # 列表区要么有类别卡片要么有空态提示，不允许两者皆无（白屏）
    assert tc.find_all(tc.CATEGORY_CARDS) or tc.has_empty_state(), \
        '用例列表既无数据也无空态提示（疑似白屏）'
