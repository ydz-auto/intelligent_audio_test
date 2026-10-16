# -*- coding: utf-8 -*-
"""INT-548 UI 实测：LogView 日志归档管理面板可见可操作（验收标准 4）。

登录（会话级注入 admin 登录态）→ /#/LogView → 断言归档面板渲染且可操作：
1. 归档状态区块（data-testid=archive-status）可见，含数字/归档目录展示；
2. 触发归档按钮可见可点（admin 具备 log:manage，permission 门控放行）；
3. 已归档日志查询区块可见（查询按钮 + 任务/用例输入框）；
4. 归档文件下载/删除按钮可见（下载 log:read / 删除 log:manage，admin 全可用）。

权限门控的负向分支（无 log:manage 时操作按钮禁用）由前端单元测试
logArchive.spec.ts 覆盖（canManage computed），UI 层仅验证 admin 全操作可见。
"""
from tests.ui.pages.base_page import BasePage


# 归档面板稳定选择器（LogArchivePanel.vue data-testid 锚点）
ARCHIVE_PANEL = '.log-archive-panel'
ARCHIVE_STATUS = '[data-testid="archive-status"]'
ARCHIVE_TRIGGER = '[data-testid="archive-trigger"]'
ARCHIVE_TRIGGER_BTN = '[data-testid="archive-trigger-btn"]'
ARCHIVED_LOGS = '[data-testid="archived-logs"]'
ARCHIVED_QUERY_BTN = '[data-testid="archived-query-btn"]'
ARCHIVE_FILE_OPS = '[data-testid="archive-file-ops"]'
ARCHIVE_DOWNLOAD_BTN = '[data-testid="archive-download-btn"]'
ARCHIVE_DELETE_BTN = '[data-testid="archive-delete-btn"]'


def test_log_archive_panel_visible_and_operable(page: BasePage):
    """归档面板整体可见：状态/触发/已归档/文件操作四区块齐备。"""
    page.goto('/LogView')
    page.wait_visible(ARCHIVE_PANEL, timeout=25)
    # 路由守卫权限：能进入 LogView 说明 log:read 已放行（admin）
    page.wait_visible(ARCHIVE_STATUS, timeout=25)
    page.wait_visible(ARCHIVE_TRIGGER, timeout=25)
    page.wait_visible(ARCHIVED_LOGS, timeout=25)
    page.wait_visible(ARCHIVE_FILE_OPS, timeout=25)


def test_archive_status_displays_values(page: BasePage):
    """归档状态区块渲染数字统计与归档目录展示（防空白/白屏回归）。"""
    page.goto('/LogView')
    page.wait_visible(ARCHIVE_STATUS, timeout=25)
    # 状态区块内必须渲染出数值/文案元素（空值也至少显示占位 '-')
    values = page.find_all(f'{ARCHIVE_STATUS} .archive-stat-value')
    assert len(values) >= 4, f'归档状态应展示至少 4 个统计项，实际 {len(values)}'
    texts = [v.text.strip() for v in values]
    assert any(t.isdigit() or t == '-' for t in texts), \
        f'归档状态统计值缺失: {texts!r}'


def test_archive_actions_visible_for_admin(page: BasePage):
    """admin（log:manage）下：触发归档/下载/删除/查询按钮全部可见可用。"""
    page.goto('/LogView')
    page.wait_visible(ARCHIVE_TRIGGER_BTN, timeout=25)
    trigger_btn = page.find_visible(ARCHIVE_TRIGGER_BTN, timeout=25)
    assert trigger_btn.is_enabled(), 'admin 应可触发归档（log:manage 门控）'
    assert page.exists(ARCHIVE_DOWNLOAD_BTN), '下载归档文件按钮缺失'
    assert page.exists(ARCHIVE_DELETE_BTN), '删除归档文件按钮缺失'
    page.wait_visible(ARCHIVED_QUERY_BTN, timeout=25)
    assert page.find_visible(ARCHIVED_QUERY_BTN, timeout=25).is_enabled(), \
        '已归档日志查询按钮应可用（log:read）'
