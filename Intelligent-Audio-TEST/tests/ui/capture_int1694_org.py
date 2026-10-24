# -*- coding: utf-8 -*-
"""INT-1694 追加取证：设备 / 结果类型视图的「组织组头 → 用例卡」两段（浅 + 深）。

复用 capture_int1694 的登录 / 造数 / 截图 helper（同端口 5331、同真实栈 15000）。
每张图只展开到第三层（设备 → result_type → 组织组头），用例卡保持折叠，
使「组织组头 → 用例卡」两段同屏可见；另加分组 ↔ 标签切换各一张。

用法：python capture_int1694_org.py light | dark
输出：tests/ui/artifacts/int1694/<mode>_org_*.png
"""
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1694 as base  # noqa: E402


def select_tasks(drv, rows):
    chosen = []
    for cb in rows[:2]:
        label = cb.get_attribute('aria-label') or ''
        base.js_click(drv, cb)
        time.sleep(0.4)
        chosen.append(label)
    print('STAGE1_SELECTED', chosen)
    if len(chosen) < 2:
        raise RuntimeError('阶段 1 未勾到两个任务')
    return chosen


def expand_levels(drv, rounds):
    """逐层展开 N 轮：每轮点掉当前所有「展开」钮（分支行 + 用例卡共用该 aria-label）。"""
    for i in range(rounds):
        btns = [b for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label='展开']")]
        if not btns:
            break
        for b in btns:
            try:
                base.js_click(drv, b)
            except Exception:
                pass
        time.sleep(0.8)
        print('EXPAND_ROUND', i + 1, len(btns))
    time.sleep(1)


def shot(drv, name):
    """截图前把所有内层滚动容器归零（展开时 scrollIntoView 会把树容器滚走）。"""
    drv.execute_script(
        "window.scrollTo(0,0);"
        "document.querySelectorAll('*').forEach(function(e){"
        "  if (e.scrollTop > 0 && e.scrollHeight > e.clientHeight + 20) e.scrollTop = 0;"
        "});"
    )
    time.sleep(0.5)
    base.shot(drv, name)


def org_rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, '[data-testid*="-org:"]')


PATH_JS = (
    'var r=[],e=arguments[0];'
    'while(e){if(e.getAttribute&&e.getAttribute("data-testid"))'
    'r.push(e.getAttribute("data-testid"));e=e.parentElement;}'
    'return r.reverse().join(" > ");'
)


def report(drv, tag):
    orgs = org_rows(drv)
    names = [(o.get_attribute('data-testid') or '').split('-org:')[-1] for o in orgs]
    print('ORG_LAYER', tag, 'count=%d' % len(orgs), names[:6])
    if orgs:
        print('ORG_PATH', drv.execute_script(PATH_JS, orgs[0]))
    if not orgs:
        raise RuntimeError('组织层未渲染：%s' % tag)


def wait_task_rows(drv, timeout=300):
    """阶段 1 任务行（pickable-tasks 在真实库较慢，最长等 5 分钟）。

    优先挑名字含「拒识」的小体量任务（约 200 条候选，树可读）；
    取不到时退回前两个任务。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = [
            c
            for c in drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            if (c.get_attribute('aria-label') or '').startswith('选择任务')
        ]
        if len(rows) >= 2:
            preferred = [c for c in rows if '拒识' in (c.get_attribute('aria-label') or '')]
            print('TASK_ROWS', len(rows), 'preferred', len(preferred))
            return preferred if len(preferred) >= 2 else rows
        time.sleep(3)
    raise RuntimeError('阶段 1 任务行未加载（pickable-tasks 超时）')


def wait_tree(drv, timeout=300, selector='[data-testid^="pick-branch-"]'):
    """等树渲染出分支行（真实库候选加载可达 1 分钟以上）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if drv.find_elements(By.CSS_SELECTOR, selector):
            time.sleep(1.5)
            return
        time.sleep(3)
    raise RuntimeError('树未渲染：%s' % selector)


def switch_view(drv, label):
    base.click_text(drv, label, limit=True)
    time.sleep(1.5)
    wait_tree(drv)


def capture_stage2(drv, mode):
    """阶段 2：设备视图 / 结果类型视图 × 分组 / 标签。"""
    switch_view(drv, '设备视图')
    expand_levels(drv, 3)
    report(drv, 'stage2_device_group')
    shot(drv, '%s_org_stage2_device_group' % mode)
    base.click_text(drv, '标签视图', limit=True)
    time.sleep(1.5)
    expand_levels(drv, 3)
    report(drv, 'stage2_device_tag')
    shot(drv, '%s_org_stage2_device_tag' % mode)
    base.click_text(drv, '分组视图', limit=True)
    time.sleep(1.2)

    base.click_text(drv, '结果类型视图')
    time.sleep(1.5)
    wait_tree(drv)
    expand_levels(drv, 3)
    report(drv, 'stage2_resulttype_group')
    shot(drv, '%s_org_stage2_resulttype_group' % mode)
    base.click_text(drv, '标签视图', limit=True)
    time.sleep(1.5)
    expand_levels(drv, 3)
    report(drv, 'stage2_resulttype_tag')
    shot(drv, '%s_org_stage2_resulttype_tag' % mode)
    base.click_text(drv, '分组视图', limit=True)
    time.sleep(1.2)


def click_exact(drv, label):
    """按按钮文案精确匹配，且只点抽屉内（[role=dialog]）的按钮——
    页面背后筛选栏也有「设备 / 结果类型」同名按钮，全局匹配会误点。"""
    dialogs = drv.find_elements(By.CSS_SELECTOR, "[role='dialog']")
    scope = dialogs[-1] if dialogs else drv
    for el in scope.find_elements(By.CSS_SELECTOR, 'button'):
        try:
            if base.text_of(drv, el).strip() == label:
                base.js_click(drv, el)
                return el
        except Exception:
            pass
    raise RuntimeError('找不到精确文案按钮: %s' % label)


def capture_cart(drv, mode):
    """购物车 / 复核抽屉：任务视图设备 / 结果类型子模式（B 组）组织层同屏。"""
    base.open_cart(drv)
    # 任务视图 · 设备子模式：任务 → 设备 → result_type → 组织组头 → 用例卡
    click_exact(drv, '设备')
    time.sleep(1.5)
    expand_levels(drv, 4)
    report(drv, 'cart_task_device')
    shot(drv, '%s_org_cart_task_device' % mode)
    click_exact(drv, '结果类型')
    time.sleep(1.5)
    expand_levels(drv, 4)
    report(drv, 'cart_task_resulttype')
    shot(drv, '%s_org_cart_task_resulttype' % mode)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'light'
    d = base.make_driver()
    try:
        base.login(d)
        d.get(base.BASE + '/tasks/cherry-pick')
        time.sleep(2)
        base.set_theme(d, 'dark' if mode == 'dark' else 'light')
        base.open_pick(d)
        rows = wait_task_rows(d)
        select_tasks(d, rows)
        base.click_text(d, '下一步', limit=True)
        WebDriverWait(d, 240).until(
            lambda x: len(x.find_elements(By.CSS_SELECTOR, '.animate-pulse')) == 0
        )
        time.sleep(3)
        capture_stage2(d, mode)
        base.add_to_cart(d)
        capture_cart(d, mode)
        print('OK', mode)
    finally:
        d.quit()
        base.clear_cart()


if __name__ == '__main__':
    main()

