# -*- coding: utf-8 -*-
"""INT-631 UI 实测：任务数据导出请求体平铺 + 受影响页（任务列表）导入/导出对话框走查。

卡面验收标准（受影响页回归 + 无兼容层残留）的 UI 层证据：

1. 任务列表勾选任务 → 批量操作栏「导出数据」→ TaskDataExportDialog 打开，
   「包含参考参数文件」「包含音频文件」两个勾选项渲染且可切换；
2. 点击「开始导出」→ 拦截真实 fetch 请求，断言 POST /data-transfer/export
   请求体为**平铺** {task_ids, include_ref_params, include_audios}，无嵌套
   options（网关 APIModel extra=ignore 会静默丢弃嵌套 options——这是本卡
   修复的核心契约，浏览器侧实测锁定）；
3. 导入入口走查：任务列表「导入数据」→ TaskDataImportDialog 打开可关闭；
4. 浅色/深色截图取证（深色以 documentElement.dark 强制，页面框架走 tokens 双主题）。

数据卫生：API 自建任务，teardown 软删 + purge，零残留（隔离库）。
导出响应可能因任务无结果而报错（本卡不改后端），请求体断言不依赖导出成功。
"""
import json

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'

# TaskDataExportDialog / TaskDataImportDialog（frontend/src/components/task/）
EXPORT_DIALOG_TITLE = '导出任务数据'
IMPORT_DIALOG_TITLE = '导入任务数据'
DIALOG_OVERLAY = '.dt-dialog-overlay'
DIALOG = '.dt-dialog'
CHECK_LABELS = '.dt-check'
EXPORT_BTN_TEXT = '导出数据'
IMPORT_BTN_TEXT = '导入数据'
START_EXPORT_BTN = '开始导出'


def _create_task(api_client) -> dict:
    """API 造 1 个任务（无用例/结果，足够进入列表与导出对话框）。"""
    suffix = unique_suffix()
    name = f'ui631_任务_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': name,
        'type': 'e2e',
        'description': 'INT-631 数据迁移导出对话框实测',
    })
    task = data.get('data') or {}
    task_id = task.get('id')
    assert task_id, f'API 造任务失败: {str(data)[:200]}'
    return {'id': str(task_id), 'name': name}


def _cleanup_task(api_client, task_id: str) -> None:
    """任务软删（回收站）→ 彻底删除（purge），库内零残留。"""
    try:
        api_client.request('POST', '/tasks/batch-action',
                           {'action': 'delete', 'task_ids': [int(task_id)]})
    except Exception:
        pass
    try:
        api_client.request('DELETE', f'/tasks/{task_id}/purge')
    except Exception:
        pass


def _find_task_checkbox(bp: BasePage, task_name: str):
    """定位指定任务卡片的勾选框（input.task-checkbox，TaskCard.vue）。"""
    cards = bp.find_all('.task-card')
    for card in cards:
        if not card.is_displayed():
            continue
        name_el = card.find_elements(By.CSS_SELECTOR, '.task-title')
        if name_el and task_name in (name_el[0].text or ''):
            boxes = [c for c in card.find_elements(By.CSS_SELECTOR, 'input.task-checkbox')
                     if c.is_displayed()]
            if boxes:
                return boxes[0]
    return None


def _install_fetch_interceptor(driver) -> None:
    """在真实 fetch 前挂钩，捕获 /data-transfer/export 出网请求体（不改写请求）。"""
    driver.execute_script(
        "window.__int631_export_bodies = [];"
        "if (!window.__int631_fetch_patched) {"
        "  const orig = window.fetch.bind(window);"
        "  window.fetch = function(url, opts) {"
        "    try {"
        "      const u = String(url);"
        "      if (u.indexOf('/data-transfer/export') !== -1) {"
        "        window.__int631_export_bodies.push({url: u, body: opts && opts.body ? String(opts.body) : null});"
        "      }"
        "    } catch (e) {}"
        "    return orig(url, opts);"
        "  };"
        "  window.__int631_fetch_patched = true;"
        "}"
    )


def _captured_export_bodies(driver) -> list:
    return driver.execute_script('return window.__int631_export_bodies || []')


@pytest.fixture()
def int631_task(api_client):
    handles = _create_task(api_client)
    yield handles
    _cleanup_task(api_client, handles['id'])


def test_export_dialog_flat_request_body(page, int631_task):
    """勾选任务 → 导出对话框 → 开始导出：出网请求体平铺（无嵌套 options）。"""
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=30)
    page.settle(0.5)

    # 勾选本卡任务 → 批量操作栏出现「导出数据」
    box = WebDriverWait(page.driver, 15).until(
        lambda d: _find_task_checkbox(page, int631_task['name']))
    page.driver.execute_script('arguments[0].click();', box)
    page.wait_visible('.batch-actions', timeout=15)
    page.settle(0.4)

    export_btn = [b for b in page.find_all('.batch-actions button')
                  if EXPORT_BTN_TEXT in (b.text or '') and b.is_displayed()]
    assert export_btn, '批量操作栏未出现「导出数据」按钮'
    page.driver.execute_script('arguments[0].click();', export_btn[0])

    # 导出对话框打开：标题 + 两个勾选项（包含参考参数 / 包含音频）
    dialog = WebDriverWait(page.driver, 15).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, DIALOG)))
    assert EXPORT_DIALOG_TITLE in dialog.text, \
        f'导出对话框标题异常: {dialog.text[:80]!r}'
    checks = [c for c in dialog.find_elements(By.CSS_SELECTOR, CHECK_LABELS)
              if c.is_displayed()]
    assert len(checks) == 2, f'导出勾选项应为 2 个（参考参数/音频）：实际 {len(checks)}'
    checkbox_els = [c.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                    for c in checks]
    # 默认态：包含参考参数=true、包含音频=false
    assert checkbox_els[0].is_selected() is True, '「包含参考参数文件」应默认勾选'
    assert checkbox_els[1].is_selected() is False, '「包含音频文件」应默认未勾选'
    # 切换两个勾选项 → 状态翻转
    page.driver.execute_script('arguments[0].click();', checkbox_els[0])
    page.driver.execute_script('arguments[0].click();', checkbox_els[1])
    page.settle(0.2)
    assert checkbox_els[0].is_selected() is False, '「包含参考参数」切换后应取消勾选'
    assert checkbox_els[1].is_selected() is True, '「包含音频」切换后应勾选'

    # 截图：导出对话框浅色（关键交互态）
    page.driver.save_screenshot(
        page.node_artifact_dir('int631_export_dialog_light.png'))
    # 深色：documentElement.dark 强制（tokens.css 双主题预留）
    page.driver.execute_script("document.documentElement.classList.add('dark');")
    page.settle(0.3)
    page.driver.save_screenshot(
        page.node_artifact_dir('int631_export_dialog_dark.png'))
    page.driver.execute_script("document.documentElement.classList.remove('dark');")

    # 拦截出网请求后点击「开始导出」→ 断言平铺请求体
    _install_fetch_interceptor(page.driver)
    start_btn = [b for b in dialog.find_elements(By.CSS_SELECTOR, 'button')
                 if START_EXPORT_BTN in (b.text or '') and b.is_displayed()]
    assert start_btn, '导出对话框未渲染「开始导出」按钮'
    page.driver.execute_script('arguments[0].click();', start_btn[0])
    WebDriverWait(page.driver, 12).until(
        lambda d: len(_captured_export_bodies(d)) >= 1)

    captured = _captured_export_bodies(page.driver)
    assert captured, '未捕获到 /data-transfer/export 出网请求'
    body_text = captured[0]['body']
    assert body_text, f'导出请求体为空: {captured[0]!r}'
    parsed = json.loads(body_text)
    assert parsed.get('task_ids') == [int(int631_task['id'])], \
        f'task_ids 异常: {parsed.get("task_ids")!r}'
    assert set(parsed.keys()) == {'task_ids', 'include_ref_params', 'include_audios'}, \
        f'请求体键集合异常（应平铺无嵌套）: {sorted(parsed.keys())}'
    assert parsed['include_ref_params'] is False, '参考参数应为切换后的 False'
    assert parsed['include_audios'] is True, '音频应为切换后的 True'
    assert 'options' not in parsed, '请求体不得包含嵌套 options（网关 extra=ignore 静默丢弃）'


def test_import_dialog_opens(page, int631_task):
    """受影响页回归：任务列表「导入数据」→ 导入对话框打开并渲染文件选择。"""
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=30)
    page.settle(0.5)

    import_btn = [b for b in page.find_all('.task-actions button')
                  if IMPORT_BTN_TEXT in (b.text or '') and b.is_displayed()]
    assert import_btn, '任务列表头部未出现「导入数据」按钮'
    page.driver.execute_script('arguments[0].click();', import_btn[0])

    dialog = WebDriverWait(page.driver, 15).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, DIALOG)))
    assert IMPORT_DIALOG_TITLE in dialog.text, \
        f'导入对话框标题异常: {dialog.text[:80]!r}'
    file_input = dialog.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
    assert file_input, '导入对话框未渲染文件选择（.zip）'
    # 关闭对话框
    close_btn = [b for b in dialog.find_elements(By.CSS_SELECTOR, 'button')
                 if b.is_displayed() and ('取消' in (b.text or '') or '关闭' in (b.text or ''))]
    assert close_btn, '导入对话框未渲染取消/关闭按钮'
    page.driver.execute_script('arguments[0].click();', close_btn[0])
    assert page.wait_gone(DIALOG, timeout=10), '导入对话框关闭失败'
