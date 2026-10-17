# -*- coding: utf-8 -*-
"""INT-600 挑选合并交互重设计 验收补充走查（真实 Chrome headless，按 test_ui_09/25 先例）。

现有 test_ui_25_int600_cherry_pick.py 覆盖 4 条冒烟；本文件按验收标准补足：
- §3.2 联动规则 R2/R3/R4/R5/R6/R8/R9/R10（R1 已有冒烟）逐条浏览器实测
- §4.3 购物车移除矩阵全量（单条X/批量/一键失效/清空/节点移除该组/整组移除整组）+ 另存挑选集/恢复
- §5.3 三出口各一次真实下单（merge/reexecute/reevaluate）+ configInconsistent 强制确认
- §8 RBAC：algo_engineer 页签列表只读可见 + 挑选链整链隐藏 + 购物车只读态
- §6.3 跨组件状态同步：购物车角标加购/移除后实时刷新
- 回归断言：批量浮条「加入挑选」吸收「合并任务」/仅终态可挑/三档粒度/引用持有文案

数据为 frontend-react mock（无后端依赖）；REACT_DEV_BASE 可覆写，默认 5273。
失败落 tests/ui/artifacts/int600_cherry_pick_ext/<用例>/。
"""
import json
import os
import re
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int600_cherry_pick_ext')

# 本 run 隔离 dev server（parallel 纪律：不复用其它 run 的栈）
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5287')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


_DRIVER = None


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
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


@pytest.fixture(scope='session')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    yield _DRIVER
    try:
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if call.when == 'call' and call.excinfo is not None:
        try:
            _save_evidence(item.name, _DRIVER)
        except Exception:
            pass


def _wait(drv, by, value, timeout=12):
    return WebDriverWait(drv, timeout).until(
        lambda d: d.find_elements(by, value))


def _wait_text(drv, fragment, timeout=12):
    """等待任一可见元素包含文本 fragment（可见状态断言）。"""
    def _found(d):
        for el in d.find_elements(By.XPATH, f"//*[contains(., '{fragment}')]"):
            if el.is_displayed():
                return el
        return None
    return WebDriverWait(drv, timeout).until(_found)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _click(drv, by, value, timeout=12):
    el = _wait(drv, by, value, timeout)
    for cand in el:
        if cand.is_displayed():
            cand.click()
            return cand
    return el[0]


def _click_by(drv, xpath, timeout=12):
    return _click(drv, By.XPATH, xpath, timeout)


def _texts(drv, by, value):
    return [e.text.strip() for e in drv.find_elements(by, value) if e.text.strip()]


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.4)


def _login(drv, username='demo_admin'):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _inject_user(drv, permissions, username='algo_engineer'):
    """注入指定权限用户快照（auth-store 持久键 iatp:auth:v1，test_ui_09 先例）。"""
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script("window.localStorage.clear()")
    snapshot = {
        'state': {
            'user': {
                'id': 'mock-algo-001',
                'username': username,
                'displayName': '演示算法工程师',
                'roleName': '算法工程师',
                'permissions': permissions,
            }
        },
        'version': 0,
    }
    drv.execute_script(
        "window.localStorage.setItem('iatp:auth:v1', arguments[0])",
        json.dumps(snapshot, ensure_ascii=False))


def _open_pick_wizard(drv):
    """进入挑选合并页签并打开四步向导（树形默认收起至任务级）。"""
    _goto(drv, '/tasks/cherry-picks')
    _click_by(drv, "//button[contains(., '开始挑选')]")
    time.sleep(1.5)
    _wait(drv, By.XPATH, "//*[contains(., '挑选') and contains(., '购物车') and contains(., '复核')]")
    # 全部展开，暴露四级分支与结果行叶
    _click_by(drv, "//button[contains(., '全部展开')]")
    time.sleep(1.0)


def _open_cart_drawer(drv):
    _goto(drv, '/tasks/cherry-picks')
    _click_by(drv, "//button[contains(., '打开购物车')]")
    time.sleep(1.2)
    _wait(drv, By.XPATH, "//*[contains(., '我的购物车')]")


def _expand_cart_all(drv, max_rounds=16):
    """购物车树默认收起：反复展开可见的节点（CollapsibleTrigger aria-label=展开）直至叶行出现。"""
    for _ in range(max_rounds):
        btns = [b for b in drv.find_elements(
            By.CSS_SELECTOR, "[data-slot='sheet-content'] button[aria-label='展开']")
            if b.is_displayed()]
        if not btns:
            return True
        btns[0].click()
        time.sleep(0.35)
    return False


def _confirm_dialog_click(drv, confirm_text=None):
    """点 ConfirmDialog（AlertDialog）Footer 内的确认钮（取消钮带 data-slot，据此排除）。"""
    content = _visible_alert_content(drv)
    if confirm_text is None:
        # Footer 中非取消钮即确认钮（text 经 base-ui 渲染可能取不到，按结构定位）
        btn = content.find_element(
            By.CSS_SELECTOR, "[data-slot='alert-dialog-footer'] button:not([data-slot='alert-dialog-cancel'])")
    else:
        btns = content.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-footer'] button")
        btn = next((b for b in btns if (b.text or '').strip() == confirm_text), None)
        assert btn is not None, f'确认钮「{confirm_text}」未找到'
    btn.click()
    return btn


def _visible_alert_content(drv, timeout=8):
    """等待并返回可见的 AlertDialog content（open 动画期间 text 可能暂为空）。"""
    deadline = time.time() + timeout
    content = None
    while time.time() < deadline:
        for el in drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']"):
            if el.is_displayed():
                content = el
                break
        if content is not None:
            return content
        time.sleep(0.2)
    raise AssertionError('AlertDialog content 未在超时内出现')


def _dialog_text(drv):
    """当前 AlertDialog 内容文本（ConfirmDialog 标题+描述）。"""
    el = _visible_alert_content(drv, timeout=6)
    deadline = time.time() + 6
    while time.time() < deadline:
        txt = (el.text or '').strip()
        if txt:
            return txt
        time.sleep(0.2)
    return ''


def _task_cb(drv, task_id):
    return f"[data-testid='pick-branch-task:{task_id}'] [data-slot='checkbox']"


def _leaf_cb(drv, result_id):
    return f"[data-testid='pick-leaf-{result_id}'] [data-slot='checkbox']"


def _cart_leaf_ids(drv):
    return [e.get_attribute('data-testid').replace('cart-leaf-', '')
            for e in drv.find_elements(By.CSS_SELECTOR, "[data-testid^='cart-leaf-']")]


# ── §3.2 联动规则 R2/R3/R4/R5/R6/R8 ──
def test_10_linkage_r2_r3_r4_r5_r6_r8(drv):
    """R3 部分选中 indeterminate / R1→R2 父级全选→全取消 / R6 用例级全含 /
    R4 取消 device 清其下 result_type / R5 取消 result_type 保留 device 部分选中 / R8 跨任务独立。"""
    _login(drv)
    _open_pick_wizard(drv)

    # R3：勾选单叶（5001）→ 任务级「部分选中」
    _click(drv, By.CSS_SELECTOR, _leaf_cb(drv, 5001))
    time.sleep(0.5)
    task_row = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-branch-task:1042']")
    assert '部分选中' in task_row.text, f'R3 任务级应为部分选中：{task_row.text}'
    _wait_text(drv, '已选 1 条结果')

    # R1 兜底：任务级勾选 → 全部 6 子孙选中（task 1042 = 6 条）
    _click(drv, By.CSS_SELECTOR, _task_cb(drv, 1042))
    time.sleep(0.5)
    checked = drv.find_elements(By.CSS_SELECTOR,
                                "[data-testid='pick-branch-task:1042'] [data-slot='checkbox'][data-checked]")
    assert len(checked) > 0, 'R1 任务级应为全选态'

    # R2：再次点击任务级 → 全部取消，无残留
    _click(drv, By.CSS_SELECTOR, _task_cb(drv, 1042))
    time.sleep(0.5)
    _wait_text(drv, '已选 0 条结果')
    assert not drv.find_elements(By.CSS_SELECTOR,
                                 "[data-testid^='pick-leaf-'] [data-slot='checkbox'][data-checked]"), \
        'R2 取消任务级后不应有任何叶残留'

    # R6：勾选用例 c-001（含 device×result_type 全部 3 条）→ 全含
    _click(drv, By.CSS_SELECTOR, "[data-testid='pick-branch-case:1042:c-001'] [data-slot='checkbox']")
    time.sleep(0.5)
    _wait_text(drv, '已选 3 条结果')  # 5001/5002/5003
    c1_row = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-branch-case:1042:c-001']")
    assert 'data-checked' in c1_row.get_attribute('outerHTML'), f'R6 用例级应全选：{c1_row.text}'

    # R4：任务级全选后取消 c-001 下「音箱-客厅位」device → 其下 real-time/final 全清（剩 5004/5005/5006）
    _click(drv, By.CSS_SELECTOR, _task_cb(drv, 1042))  # 部分选中(3) → 全选 6
    time.sleep(0.4)
    device_cb = "[data-testid='pick-branch-device:1042:c-001:device:1'] [data-slot='checkbox']"
    _click(drv, By.CSS_SELECTOR, device_cb)  # device 已全选 → 取消
    time.sleep(0.5)
    _wait_text(drv, '已选 3 条结果')  # 剩 5004/5005/5006
    for leaf in (5001, 5002, 5003):
        assert not drv.find_elements(By.CSS_SELECTOR, _leaf_cb(drv, leaf) + '[data-checked]'), \
            f'R4 取消 device 后叶 {leaf} 不应勾选'
    c1_after = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-branch-case:1042:c-001']")
    assert '部分选中' not in c1_after.text, 'R4 后 c-001 不应部分选中（唯一 device 已清）'

    # R5：重选该 device（3 条）→ 取消 result_type real-time → 仅清其下 2 条，device 保持部分选中
    _click(drv, By.CSS_SELECTOR, device_cb)  # device 未选 → 全选 3
    time.sleep(0.4)
    _wait_text(drv, '已选 6 条结果')
    rt_cb = "[data-testid='pick-branch-resultType:1042:c-001:device:1:real-time'] [data-slot='checkbox']"
    _click(drv, By.CSS_SELECTOR, rt_cb)  # real-time 已选 → 取消
    time.sleep(0.5)
    _wait_text(drv, '已选 4 条结果')  # 剩 5003/5004/5005/5006
    device_row = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-branch-device:1042:c-001:device:1']")
    assert '部分选中' in device_row.text, f'R5 device 应保持部分选中：{device_row.text}'

    # R8：勾选任务 1041 → 任务 1042 勾选不受影响（跨任务独立根）
    _click(drv, By.CSS_SELECTOR, _task_cb(drv, 1041))
    time.sleep(0.5)
    _wait_text(drv, '已选 7 条结果')  # 1042:4 + 1041:3
    t1041 = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-branch-task:1041']")
    t1042 = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-branch-task:1042']")
    assert 'data-checked' in t1041.get_attribute('outerHTML'), 'R8 任务1041 应全选'
    assert '部分选中' in t1042.text, f'R8 任务1042 保持部分选中不受影响：{t1042.text}'


# ── §3.2 R9 全选/反选/清空 + R10 已加购 + 三档粒度 ──
def test_11_linkage_r9_r10_and_granularity(drv):
    """R10 已加购标记；三档粒度（逐条/整组/维度批量）；R9 全选（11 条）/反选/清空。"""
    _login(drv)
    _open_pick_wizard(drv)

    # R10：mock 初始购物车含 5001/5002/5004/5010 → 对应叶显示「已加购」
    leaf5001 = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-leaf-5001']")
    assert '已加购' in leaf5001.text, f'R10 5001 应显示已加购：{leaf5001.text}'
    leaf5011 = drv.find_element(By.CSS_SELECTOR, "[data-testid='pick-leaf-5011']")
    assert '已加购' not in leaf5011.text, 'R10 5011（未加购）不应显示已加购'

    # 三档粒度-1 逐条：勾选 5003 → 1
    _click(drv, By.CSS_SELECTOR, _leaf_cb(drv, 5003))
    time.sleep(0.4)
    _wait_text(drv, '已选 1 条结果')

    # 三档粒度-2 整组：勾选任务 1042 → 6 条
    _click(drv, By.CSS_SELECTOR, _task_cb(drv, 1042))
    time.sleep(0.4)
    _wait_text(drv, '已选 6 条结果')

    # 三档粒度-3 维度批量：全选当前筛选 → 11 条 / 3 任务 / 4 设备
    _click_by(drv, "//button[contains(., '全选当前筛选')]")
    time.sleep(0.5)
    _wait_text(drv, '已选 11 条结果')
    _wait_text(drv, '来自 3 个任务')
    _wait_text(drv, '覆盖 4 台设备')

    # R9 反选：当前可见全选 → 取反后 0
    _click_by(drv, "//button[contains(., '反选')]")
    time.sleep(0.5)
    _wait_text(drv, '已选 0 条结果')

    # R9 反选恢复全选 → 清空 → 0
    _click_by(drv, "//button[contains(., '反选')]")
    time.sleep(0.5)
    _wait_text(drv, '已选 11 条结果')
    _click_by(drv, "//button[contains(., '清空')]")
    time.sleep(0.5)
    _wait_text(drv, '已选 0 条结果')


# ── §4.3 移除矩阵A：单条X / 批量 / 一键失效 / 清空 ──
def test_12_cart_remove_single_batch_invalid_clear(drv):
    """购物车移除矩阵：展开树 → 单条 X → 批量勾选移除 → 一键移除失效 → 清空。"""
    _login(drv)
    _open_cart_drawer(drv)
    _expand_cart_all(drv)

    # 初始 5 条：ci-1..ci-5（ci-5 失效）
    leaves = _cart_leaf_ids(drv)
    assert leaves == ['ci-1', 'ci-2', 'ci-3', 'ci-4', 'ci-5'], f'初始购物车应 5 条：{leaves}'

    # 单条 X：移除 ci-1
    _click(drv, By.CSS_SELECTOR, "[data-testid='cart-leaf-ci-1'] button[aria-label='移除']")
    _confirm_dialog_click(drv)
    _wait_text(drv, '已移除 1 条')
    time.sleep(0.8)
    assert 'ci-1' not in _cart_leaf_ids(drv), 'ci-1 应已移除'

    # 批量：勾选 ci-2 + ci-3 → 移除已选（2）
    _click(drv, By.CSS_SELECTOR, "[data-testid='cart-leaf-ci-2'] [data-slot='checkbox']")
    _click(drv, By.CSS_SELECTOR, "[data-testid='cart-leaf-ci-3'] [data-slot='checkbox']")
    time.sleep(0.4)
    _click_by(drv, "//button[contains(., '移除已选（2）')]")
    _confirm_dialog_click(drv)
    _wait_text(drv, '已移除 2 条')
    time.sleep(0.8)
    assert _cart_leaf_ids(drv) == ['ci-4', 'ci-5'], f'批量移除后应剩 ci-4/ci-5：{_cart_leaf_ids(drv)}'

    # 一键移除失效：仅 ci-5 失效
    _click_by(drv, "//button[contains(., '移除失效条目（1）')]")
    _wait_text(drv, '失效条目已移除')
    time.sleep(0.8)
    assert _cart_leaf_ids(drv) == ['ci-4'], f'失效移除后应剩 ci-4：{_cart_leaf_ids(drv)}'

    # 清空购物车
    _click_by(drv, "//button[contains(., '清空购物车')]")
    _confirm_dialog_click(drv)
    _wait_text(drv, '购物车已清空')
    time.sleep(0.8)
    _wait_text(drv, '购物车为空')


# ── §4.3 移除矩阵B：节点移除该组 / 整组移除整组 ──
def test_13_cart_remove_node_and_group(drv):
    """节点「移除该组」（c-001 用例下 2 条）与来源任务「移除整组」。"""
    _login(drv)
    _open_cart_drawer(drv)
    _expand_cart_all(drv)

    # 节点移除该组：c-001 用例（ci-1/ci-2）
    _click(drv, By.CSS_SELECTOR,
          "[data-testid='cart-branch-cart-case:1042:c-001'] button[aria-label='移除该组']")
    _wait(drv, By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dialog_txt = _dialog_text(drv)
    assert '移除用例' in dialog_txt and '下的 2 条结果' in dialog_txt, f'节点移除确认文案缺失：{dialog_txt[:120]}'
    _confirm_dialog_click(drv)
    _wait_text(drv, '已移除 2 条')
    time.sleep(0.8)
    assert _cart_leaf_ids(drv) == ['ci-3', 'ci-4', 'ci-5'], f'节点移除后应剩 ci-3/ci-4/ci-5：{_cart_leaf_ids(drv)}'

    # 整组移除：任务 1041 组头「移除整组」（ci-4/ci-5）
    grp = _wait(drv, By.XPATH,
                "//section[.//*[contains(., '车载语音助手唤醒词响应测试')]]//button[@aria-label='移除整组']")[0]
    grp.click()
    _wait(drv, By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dialog_txt = _dialog_text(drv)
    assert '移除来源任务' in dialog_txt and '下的 2 条结果' in dialog_txt, f'整组移除确认文案缺失：{dialog_txt[:120]}'
    _confirm_dialog_click(drv)
    _wait_text(drv, '已移除 2 条')
    time.sleep(0.8)
    assert _cart_leaf_ids(drv) == ['ci-3'], f'整组移除后应剩 ci-3：{_cart_leaf_ids(drv)}'


# ── §4.3 另存挑选集 + 恢复 ──
def test_14_pick_set_save_and_restore(drv):
    """另存为挑选集 → 清空 → 关抽屉 → 管理挑选集恢复进购物车。"""
    _login(drv)
    _open_cart_drawer(drv)

    _click_by(drv, "//button[contains(., '另存为挑选集')]")
    _wait(drv, By.XPATH, "//*[contains(., '为当前购物车内容命名')]")
    inp = drv.find_element(By.XPATH, "//input[@placeholder='挑选集名称（例如：远场高置信度候选集）']")
    inp.send_keys('验收测试挑选集ABC')
    _click_by(drv, "//button[contains(., '保存')]")
    _wait_text(drv, '挑选集「验收测试挑选集ABC」已保存（5 条）')
    time.sleep(0.6)

    # 清空购物车
    _click_by(drv, "//button[contains(., '清空购物车')]")
    _confirm_dialog_click(drv)
    _wait_text(drv, '购物车为空')

    # 关抽屉 → 管理挑选集 → 恢复
    _click(drv, By.CSS_SELECTOR, "[data-slot='sheet-close']")
    time.sleep(0.6)
    _click_by(drv, "//button[contains(., '管理挑选集')]")
    _wait(drv, By.XPATH, "//*[contains(., '验收测试挑选集ABC')]")
    # 恢复本测试另存的挑选集（popover 内含预置 set-1，勿误点其「恢复」）
    _click_by(drv,
              "//p[text()='验收测试挑选集ABC']/ancestor::div[contains(@class,'hover:bg-accent')]//button[contains(., '恢复')]")
    _wait_text(drv, '已恢复 5 条进购物车')
    # 关挑选集 popover → 重新打开抽屉核验恢复结果
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.5)
    _click_by(drv, "//button[contains(., '打开购物车')]")
    time.sleep(1.0)
    _wait(drv, By.XPATH, "//*[contains(., '我的购物车')]")
    _expand_cart_all(drv)
    assert len(_cart_leaf_ids(drv)) == 5, f'恢复后购物车应 5 条：{_cart_leaf_ids(drv)}'


# ── §5.3 三出口·merge（默认）+ configInconsistent 强制确认 + 引用持有文案 ──
def test_15_checkout_merge_forced_confirm(drv):
    """复核 → 下单：merge 出口 + 新任务名称必填 + configInconsistent 强制确认 + 创建成功。"""
    _login(drv)
    _goto(drv, '/tasks/cherry-picks')
    _click_by(drv, "//button[contains(., '打开购物车')]")
    time.sleep(1.2)
    _click_by(drv, "//button[contains(., '去复核（5）')]")
    time.sleep(1.8)

    # 复核摘要 + 失效 Alert + 配置不一致 Alert（mock 初始 5 条 / 2 来源任务）
    _wait_text(drv, '结果 5 条')
    _wait_text(drv, '来源任务 2 个')
    _wait_text(drv, '设备 3 台 / 用例 4 个')
    _wait_text(drv, '1 条购物车条目已失效')
    _wait_text(drv, '任务级配置（algorithm_type）不一致')

    # 确认下单 → 下单步骤（四步向导 Step4）
    _click_by(drv, "//button[contains(., '确认下单（5）')]")
    time.sleep(1.2)
    for action in ('merge', 'reexecute', 'reevaluate'):
        assert _wait(drv, By.CSS_SELECTOR, f"[data-testid='checkout-action-{action}']"), f'缺三出口 {action}'
    # 引用持有红线文案（INT-339：源任务保持原样）
    merge_card = drv.find_element(By.CSS_SELECTOR, "[data-testid='checkout-action-merge']")
    assert '源任务保持原样' in merge_card.text, f'merge 出口缺引用持有文案：{merge_card.text}'

    # configInconsistent：确认下单先弹强制确认（handleConfirm 先于名称校验）
    _click_by(drv, "//button[contains(., '确认下单')]")
    _wait(drv, By.XPATH, "//*[contains(., '确认合并？')]")
    dialog_txt = _body_text(drv)
    assert '任务级配置（algorithm_type）不一致' in dialog_txt and '是否继续合并' in dialog_txt, \
        f'强制确认文案缺失：{dialog_txt[:200]}'
    _click_by(drv, "//button[contains(., '继续合并')]")
    # 空名称经强制确认后仍被拦下
    _wait_text(drv, '新任务名称必填')

    inp = drv.find_element(By.ID, 'checkout-name')
    inp.send_keys('验收-合并-20261017')
    _click_by(drv, "//button[contains(., '确认下单')]")
    # configInconsistent → 再次强制确认 → 下单成功
    _wait(drv, By.XPATH, "//*[contains(., '确认合并？')]")
    _click_by(drv, "//button[contains(., '继续合并')]")

    # 下单成功：跳转 /tasks/:id 且 toast 提示可手动生成报告
    WebDriverWait(drv, 15).until(lambda d: re.search(r'/tasks/\d+$', d.current_url))
    _wait_text(drv, '挑选合并任务已创建')
    _wait_text(drv, '可手动生成报告')


# ── §5.3 三出口·reexecute ──
def test_16_checkout_reexecute_exit(drv):
    """重新执行出口：选择 reexecute → 确认下单 → 重执行任务已创建并启动。"""
    _login(drv)
    _goto(drv, '/tasks/cherry-picks')
    _click_by(drv, "//button[contains(., '打开购物车')]")
    time.sleep(1.2)
    _click_by(drv, "//button[contains(., '去复核（5）')]")
    time.sleep(1.8)
    _click_by(drv, "//button[contains(., '确认下单（5）')]")
    time.sleep(1.2)

    _click(drv, By.CSS_SELECTOR, "[data-testid='checkout-action-reexecute']")
    time.sleep(0.4)
    reexec_card = drv.find_element(By.CSS_SELECTOR, "[data-testid='checkout-action-reexecute']")
    assert '按所选结果的用例×设备集合创建重执行任务并启动' in reexec_card.text, \
        f'reexecute 说明缺失：{reexec_card.text}'
    _click_by(drv, "//button[contains(., '确认下单')]")
    _wait(drv, By.XPATH, "//*[contains(., '确认合并？')]")
    _click_by(drv, "//button[contains(., '继续合并')]")
    WebDriverWait(drv, 15).until(lambda d: re.search(r'/tasks/\d+$', d.current_url))
    _wait_text(drv, '重执行任务已创建并启动')


# ── §5.3 三出口·reevaluate ──
def test_17_checkout_reevaluate_exit(drv):
    """重新评估出口：选择 reevaluate → 确认下单 → 对 2 个来源任务发起重新评估。"""
    _login(drv)
    _goto(drv, '/tasks/cherry-picks')
    _click_by(drv, "//button[contains(., '打开购物车')]")
    time.sleep(1.2)
    _click_by(drv, "//button[contains(., '去复核（5）')]")
    time.sleep(1.8)
    _click_by(drv, "//button[contains(., '确认下单（5）')]")
    time.sleep(1.2)

    _click(drv, By.CSS_SELECTOR, "[data-testid='checkout-action-reevaluate']")
    time.sleep(0.4)
    reeval_card = drv.find_element(By.CSS_SELECTOR, "[data-testid='checkout-action-reevaluate']")
    assert '不重跑执行' in reeval_card.text, f'reevaluate 说明缺失：{reeval_card.text}'
    _click_by(drv, "//button[contains(., '确认下单')]")
    _wait(drv, By.XPATH, "//*[contains(., '确认合并？')]")
    _click_by(drv, "//button[contains(., '继续合并')]")
    _wait_text(drv, '已对 2 个来源任务发起重新评估')


# ── §8 RBAC：algo_engineer 列表只读可见 + 挑选链整链隐藏 + 购物车只读 ──
def test_18_algo_engineer_readonly(drv):
    """注入 algo_engineer（task:read，无 task:cherry_pick）：页签列表只读可见、
    「开始挑选」隐藏、购物车抽屉只读（增删钮隐藏）。"""
    _inject_user(drv, ['algorithm:read', 'task:read', 'report:read'])
    _goto(drv, '/tasks/cherry-picks')
    body = _body_text(drv)

    # 页签列表只读可见：挑选合并页签 + 统一容器列表（3 个容器）
    assert '挑选合并' in body, 'algo_engineer 应可见「挑选合并」页签'
    assert '远场识别高置信度结果挑选集' in body and '车载噪声环境挑选合并' in body, \
        f'容器列表只读可见缺失：{body[:200]}'
    assert '合并容器 3' in body, f'stats 徽章行缺失：{body[:200]}'

    # 挑选链整链隐藏：无「开始挑选」（task:cherry_pick 门控）
    assert '开始挑选' not in body, 'algo_engineer 不应出现「开始挑选」'

    # 购物车抽屉只读态：可见、无增删钮
    _click_by(drv, "//button[contains(., '打开购物车')]")
    time.sleep(1.2)
    sheet = _wait(drv, By.CSS_SELECTOR, "[data-slot='sheet-content']")[0]
    _expand_cart_all(drv)
    sheet_txt = sheet.text
    assert '我的购物车' in sheet_txt
    assert len(_cart_leaf_ids(drv)) == 5, f'只读购物车仍应展示 5 条：{_cart_leaf_ids(drv)}'
    # 只读态：无勾选框 / 无 X 移除 / 无失效移除 / 无清空 / 无另存 / 无去复核
    assert not drv.find_elements(By.CSS_SELECTOR, "[data-testid^='cart-leaf-'] [data-slot='checkbox']"), \
        '只读态不应有购物车勾选框'
    assert not drv.find_elements(By.CSS_SELECTOR, "[data-slot='sheet-content'] button[aria-label='移除']"), \
        '只读态不应有移除钮'
    for forbidden in ['清空购物车', '另存为挑选集', '移除失效条目', '去复核', '移除整组', '移除该组']:
        assert forbidden not in sheet_txt, f'只读态不应出现「{forbidden}」'
    # 失效标记与降级分组展示可见
    assert '已失效' in sheet_txt, '只读购物车应显示失效标记'
    assert '结果类型待补充' in sheet_txt, '§11-5 降级 result_type 分组 Tooltip 文案应可见'


# ── §6.3 跨组件状态同步：购物车角标加购/移除后实时刷新 ──
def test_19_cart_badge_sync(drv):
    """打开购物车钮角标：初始 5 → 全选加购（新增 7、重复 4 跳过）→ 12 → 单条移除 → 11。"""
    _login(drv)
    _goto(drv, '/tasks/cherry-picks')
    time.sleep(1.2)
    open_btn = drv.find_element(By.XPATH, "//button[contains(., '打开购物车')]")
    assert '5' in open_btn.text, f'角标初始应为 5：{open_btn.text}'

    # 全选 → 加入购物车：候选 11 中 4 条已在购物车（R10 幂等跳过）
    _click_by(drv, "//button[contains(., '开始挑选')]")
    time.sleep(1.5)
    _click_by(drv, "//button[contains(., '全选当前筛选')]")
    time.sleep(0.5)
    _click_by(drv, "//button[contains(., '加入购物车（11）')]")
    _wait_text(drv, '已加入购物车 7 条（重复 4 条已跳过）')
    time.sleep(1.0)

    # 返回列表 → 角标 12（7 新增 + 初始 5）
    _click_by(drv, "//button[contains(., '返回列表')]")
    time.sleep(1.2)
    open_btn = drv.find_element(By.XPATH, "//button[contains(., '打开购物车')]")
    assert '12' in open_btn.text, f'加购后角标应为 12：{open_btn.text}'

    # 单条移除 → 角标 11
    _click_by(drv, "//button[contains(., '打开购物车')]")
    time.sleep(1.0)
    _expand_cart_all(drv)
    _click(drv, By.CSS_SELECTOR, "[data-testid='cart-leaf-ci-1'] button[aria-label='移除']")
    _confirm_dialog_click(drv)
    _wait_text(drv, '已移除 1 条')
    time.sleep(1.0)
    _click(drv, By.CSS_SELECTOR, "[data-slot='sheet-close']")
    time.sleep(0.6)
    open_btn = drv.find_element(By.XPATH, "//button[contains(., '打开购物车')]")
    assert '11' in open_btn.text, f'移除后角标应为 11：{open_btn.text}'


# ── 回归断言：批量浮条「加入挑选」吸收「合并任务」+ 仅终态可挑 + 预选筛选 ──
def test_20_regression_bulk_join_pick_and_terminal_only(drv):
    """批量浮条：选 2 个终态任务 → 出现「加入挑选」而非「合并任务」钮；点击进向导预选任务级筛选。
    挑选页「仅终态可挑」提示与引用持有文案存在。"""
    _login(drv)
    _goto(drv, '/tasks/daily')
    body = _body_text(drv)
    assert '加入挑选' not in body  # 未选时不显示
    # 旧「合并任务」批量钮已吸收：不存在文本恰为「合并任务」的按钮（任务行描述含该词属正常文案）
    assert not drv.find_elements(By.XPATH, "//button[normalize-space(.)='合并任务']"), \
        '旧「合并任务」批量钮已吸收，不应存在'

    # 选 2 个终态任务（1041 completed / 1040 failed）——「加入挑选」按终态判定
    _click(drv, By.CSS_SELECTOR, "[data-slot='checkbox'][aria-label='选择 车载语音助手唤醒词响应测试']")
    _click(drv, By.CSS_SELECTOR, "[data-slot='checkbox'][aria-label='选择 API 通道并发稳定性验证（压测时段）']")
    time.sleep(0.6)
    _wait(drv, By.XPATH, "//*[contains(., '个任务已选择')]")
    _click_by(drv, "//button[contains(., '加入挑选')]")
    time.sleep(1.5)
    # 导航到挑选合并页签且向导已打开；presetTaskIds 生效为筛选（1041 可见、1042 被筛出）
    assert '/cherry-picks' in drv.current_url, f'应跳转挑选合并页签：{drv.current_url}'
    _wait(drv, By.XPATH, "//button[contains(., '返回列表')]")
    assert drv.find_elements(By.CSS_SELECTOR, "[data-testid='pick-branch-task:1041']"), '预选任务 1041 应可见'
    assert not drv.find_elements(By.CSS_SELECTOR, "[data-testid='pick-branch-task:1042']"), \
        '未选任务 1042 应被预选筛选排除'
    _wait_text(drv, '仅已完成、执行失败、已停止的终态任务可挑选')
    # 筛选工具栏 facet 全套在 Step1 可见（Select 触发器以 aria-label 呈现，MultiFacet 显示按钮文本）
    for facet in ('来源任务', '设备', '结果类型', '执行状态', '评估状态'):
        assert facet in _body_text(drv), f'筛选 facet「{facet}」缺失'
    assert drv.find_elements(By.CSS_SELECTOR, "[aria-label='时间范围']"), '时间范围 facet 缺失'
    # 执行状态仅终态三值（仅终态可挑口径）
    _click(drv, By.CSS_SELECTOR, "button[aria-label='执行状态']")
    _wait(drv, By.XPATH, "//*[contains(., '已完成') and contains(., '执行失败') and contains(., '已停止')]")
    for opt in ('已完成', '执行失败', '已停止'):
        assert drv.find_elements(By.XPATH, f"//*[@role='option' and contains(., '{opt}')]"), f'执行状态缺终态项「{opt}」'
    drv.find_element(By.TAG_NAME, 'body').send_keys('')  # ESC 关下拉
