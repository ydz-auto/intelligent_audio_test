# -*- coding: utf-8 -*-
"""INT-491 复验补充：分组管理弹窗回归项 ①-③（派发 01a1463d-43bb，commit 478e1b8b）。

仅覆盖本卡失败清单项（分组管理弹窗首载）及其主交互，避免重跑已通过用例：
① mock 4 组首载显示（客厅组/回归验证组/车载场景组[含车载近场子组]/播放设备组），不再恒「暂无分组」
② 新建分组即时可见 + 关闭重开不丢（P3-17 目标不回退；弹窗常驻挂载，本地 state 跨开关保留，页面不重载）
③ 复制/重命名/移动/批量添加成员在列表非空下可操作（§6.3 主交互）

复用 test_ui_17 的驱动/走查基建（真实 Chrome headless）。
"""
import json
import os
import time

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test_ui_17_int491_devices import (
    _body_text,
    _click_menu_item,
    _driver,
    _goto,
    _login,
    _press_esc,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MY_ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int491_group_retest')


@pytest.fixture(scope='session')
def drv():
    d = _driver()
    yield d
    try:
        d.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed:
        d = item.funcargs.get('drv')
        if d is not None:
            _save_evidence(item.name, d)


def _save_evidence(name, drv):
    d = os.path.join(MY_ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _open_group_dialog(drv, reload=True):
    """打开分组管理弹窗；reload=True 先导航到 /devices/test（新会话），False 仅从当前页打开（验证关闭重开不丢）。"""
    if reload:
        _goto(drv, '/devices/test')
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menu_item(drv, '分组管理')
    # 弹窗标题出现后，须等异步 mockLatency 首载把分组列表填充（回归根因：挂载时为空数组）
    WebDriverWait(drv, 6).until(
        lambda d: '设备分组管理' in d.execute_script('return document.body.textContent || ""'))
    WebDriverWait(drv, 8).until(
        lambda d: '客厅组' in d.execute_script('return document.body.textContent || ""'))


def _open_group_menu(drv, group_name):
    drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {group_name}']").click()
    # 等目标菜单项渲染且可见（Radix 菜单有动画窗口，任意 menuitem 出现不等于目标项已可点）
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))


def _click_group_menu_item(drv, label):
    """等待含目标文本的菜单项出现且可见后点击（规避全量跑时菜单渲染竞态）。"""
    el = WebDriverWait(drv, 5).until(
        lambda d: next(
            (it for it in d.find_elements(By.XPATH, "//*[@role='menuitem']")
             if label in it.text and it.is_displayed()),
            None))
    el.click()


def _create_group(drv, name):
    inp = drv.find_element(By.ID, 'group-name')
    inp.send_keys(name)
    drv.find_element(By.XPATH, "//button[contains(., '创建')]").click()
    # 以分组行操作钮出现为创建成功证据（输入框内文本不构成证据）
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {name}']"))


def _assert_no_severe(drv):
    sev = [e.get('message', '') for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    assert not sev, f'浏览器 console SEVERE 错误：{sev[:3]}'


# ── ① 首载：mock 4 组 + 嵌套子组，不再恒「暂无分组」 ───
def test_group_list_initial_mock_groups(drv):
    _login(drv)
    _open_group_dialog(drv)
    txt = _body_text(drv)
    assert '暂无分组' not in txt, f'分组列表恒空回归：仍显示「暂无分组」'
    for g in ['客厅组', '回归验证组', '车载场景组', '播放设备组']:
        assert g in txt, f'mock 分组「{g}」缺失：{txt[:200]}'
    assert '车载近场子组' in txt, f'嵌套子组「车载近场子组」缺失：{txt[:200]}'
    _assert_no_severe(drv)


# ── ② 新建即时可见 + 关闭重开不丢（P3-17 不回退；页面不重载） ───
def test_group_create_reopen_persist(drv):
    _login(drv)
    _open_group_dialog(drv)
    _create_group(drv, '复测新建组')
    _press_esc(drv)
    WebDriverWait(drv, 5).until(
        lambda d: '设备分组管理' not in d.execute_script('return document.body.textContent || ""'))
    # 不重载页面，仅从当前页重新打开弹窗：常驻挂载组件的本地 state 应保留新建分组
    _open_group_dialog(drv, reload=False)
    assert '复测新建组' in _body_text(drv), f'关闭重开后新建分组丢失（P3-17 回退）'
    _assert_no_severe(drv)


# ── ③ 复制/重命名/移动/批量添加成员在列表非空下可操作 ───
def test_group_operations(drv):
    _login(drv)
    _open_group_dialog(drv)
    # 复制：客厅组 → 客厅组（副本）
    _open_group_menu(drv, '客厅组')
    _click_group_menu_item(drv, '复制')
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//button[@aria-label='分组操作 客厅组（副本）']"))
    # 新建 + 重命名
    _create_group(drv, '复测操作组')
    _open_group_menu(drv, '复测操作组')
    _click_group_menu_item(drv, '重命名')
    WebDriverWait(drv, 5).until(
        lambda d: '重命名分组' in d.execute_script('return document.body.textContent || ""'))
    rn = drv.find_element(By.XPATH, "//input[@placeholder='分组名称']")
    rn.clear()
    rn.send_keys('复测重命名组')
    drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//button[@aria-label='分组操作 复测重命名组']"))
    # 移动：弹窗可开、目标列表非空（根级 + 其它分组），取消关闭
    _open_group_menu(drv, '复测重命名组')
    _click_group_menu_item(drv, '移动')
    WebDriverWait(drv, 5).until(
        lambda d: '移动分组' in d.execute_script('return document.body.textContent || ""'))
    mtxt = _body_text(drv)
    assert '根级' in mtxt and '客厅组' in mtxt, f'移动目标列表缺失：{mtxt[:200]}'
    move_dlg = drv.find_element(By.XPATH, "(//*[@role='dialog'])[last()]")
    move_dlg.find_element(By.XPATH, ".//button[contains(., '取消')]").click()
    time.sleep(0.5)
    # 批量添加成员：展开复测重命名组（0 成员）→ 批量添加成员 → 勾选设备 → 加入
    drv.find_element(By.XPATH, "//button[contains(., '复测重命名组')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: '批量添加成员' in d.execute_script('return document.body.textContent || ""'))
    drv.find_element(By.XPATH, "//button[contains(., '批量添加成员')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][.//button[contains(., '台设备')]]"))
    bulk = drv.find_element(By.XPATH, "(//*[@role='dialog'])[last()]")
    bulk.find_element(By.XPATH, ".//label[contains(., '音箱-客厅位')]//*[@role='checkbox']").click()
    drv.find_element(By.XPATH, "//button[contains(., '台设备')]").click()
    # 成员标签（含移除钮）出现在已展开的成员区
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//button[@aria-label='移出 音箱-客厅位']"))
    _assert_no_severe(drv)
