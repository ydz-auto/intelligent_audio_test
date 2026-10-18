# -*- coding: utf-8 -*-
"""INT-694 任务域弹窗补齐 冒烟核心链路浏览器走查（真实 Chrome headless，按 test_ui_25 先例）。

针对 frontend-react/ 任务页（mock 数据 + 接线动作端点）：
P1 重新执行/重新评估范围选择弹窗（§5.7）：三选项 + 「手动选择用例」展开态（用例列表/全选/过滤 Select）
P2 导出数据弹窗（§5.12）：勾选任务 → 批量浮条「导出数据」→ 选中清单 + 参考参数/音频 Checkbox + 开始导出
P3 导入数据弹窗（§5.12）：Actions「导入数据」→ 选文件段（.zip accept）
P4 冻结任务详情弹窗（§5.13）：已发布展开行「查看冻结任务详情」→ 任务信息/关联资源/用例三节
P5 冻结报告弹窗（§5.13）：已发布展开行「查看冻结报告」→ 「查看源报告 #」link + 统计行

失败落 tests/ui/artifacts/int694_task_dialogs/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int694_task_dialogs')

# 5273 = 本工作区常驻 dev server；env 可覆写
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
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


def _wait(drv, by, value, timeout=15):
    return WebDriverWait(drv, timeout).until(
        lambda d: d.find_elements(by, value))


def _click(drv, by, value, timeout=15):
    el = _wait(drv, by, value, timeout)
    for cand in el:
        if cand.is_displayed():
            cand.click()
            return cand
    return el[0]


def _texts(drv, by, value):
    return [e.text.strip() for e in drv.find_elements(by, value) if e.text.strip()]


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _login(drv, username='admin'):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('admin123')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def test_01_reexecute_scope_dialog(drv):
    """P1 重新执行范围选择弹窗：三选项 + 手动选择用例展开态"""
    _login(drv)
    _goto(drv, '/tasks/daily')
    # 逐行打开操作菜单，找到含「重新执行」的行（mock 列表按状态显隐，首行 running 无此菜单项）
    opened = False
    for i in range(8):
        _wait(drv, By.CSS_SELECTOR, 'button[aria-label="任务操作"]')
        btns = drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')
        if i >= len(btns):
            break
        btns[i].click()
        time.sleep(0.8)
        items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']")
        rerun = [it for it in items if '重新执行' in it.text]
        if rerun:
            rerun[0].click()
            opened = True
            break
        # 未命中：按 Esc 收起菜单继续下一行
        drv.find_element(By.TAG_NAME, 'body').send_keys('')
        time.sleep(0.4)
    assert opened, '应至少有一行提供「重新执行」菜单项'
    time.sleep(0.8)
    # 三选项
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-all"]')
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-failed_only"]')
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    # 切到「手动选择用例」→ 用例列表展开（含全选 + 过滤 Select）
    _click(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    time.sleep(0.6)
    case_labels = _wait(drv, By.XPATH, "//*[contains(., '全选')]")
    assert len(case_labels) > 0
    # 勾选第一行用例 → 确认按钮计数出现
    time.sleep(0.4)
    checkboxes = drv.find_elements(By.CSS_SELECTOR,
                                   '[data-slot="dialog-content"] [data-slot="checkbox"]')
    assert len(checkboxes) > 0, '手动选择用例区应渲染用例勾选列表'
    checkboxes[-1].click()
    time.sleep(0.4)
    confirm_texts = _texts(drv, By.XPATH, "//button[contains(., '确认')]")
    assert any('已选 1 个用例' in t for t in confirm_texts), \
        f'手动勾选后确认钮应带选中计数，实际 {confirm_texts}'


def test_02_export_data_dialog(drv):
    """P2 导出数据弹窗：勾选任务 → 批量浮条「导出数据」→ 清单 + 选项"""
    _login(drv)
    _goto(drv, '/tasks/daily')
    # 勾选第一行任务（base-ui Checkbox 为 span[role=checkbox]，data-slot=checkbox）
    row_check = _wait(drv, By.CSS_SELECTOR, '[data-slot="checkbox"][aria-label^="选择 "]')
    row_check[0].click()
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '导出数据')]")
    time.sleep(0.6)
    dialog_texts = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']")
    joined = ' '.join(dialog_texts)
    assert '导出任务数据' in joined
    assert '选中任务' in joined and '1 个' in joined
    assert '包含参考参数文件' in joined and '包含音频文件（体积较大）' in joined
    assert '开始导出' in joined


def test_03_import_data_dialog(drv):
    """P3 导入数据弹窗：Actions「导入数据」→ 选文件段"""
    _login(drv)
    _goto(drv, '/tasks/daily')
    _click(drv, By.XPATH, "//button[contains(., '导入数据')]")
    time.sleep(0.6)
    dialog_texts = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']")
    joined = ' '.join(dialog_texts)
    assert '导入任务数据' in joined
    assert '选择导出包' in joined
    # .zip accept 的文件输入
    file_input = _wait(drv, By.CSS_SELECTOR, 'input[type="file"][accept=".zip"]')
    assert len(file_input) > 0


def test_04_frozen_task_snapshot_dialog(drv):
    """P4 冻结任务详情弹窗：已发布展开行「查看冻结任务详情」→ 三节 + 用例 Collapsible"""
    _login(drv)
    _goto(drv, '/tasks/published')
    time.sleep(0.8)
    # 展开第一行版本详情（版本 按钮）
    _click(drv, By.XPATH, "//button[contains(., '版本')]")
    time.sleep(0.8)
    _click(drv, By.XPATH, "//button[contains(., '查看冻结任务详情')]")
    time.sleep(0.8)
    dialog_texts = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']")
    joined = ' '.join(dialog_texts)
    assert '任务详情（发布时冻结' in joined
    assert '任务信息' in joined
    assert '关联资源（发布时冻结）' in joined
    assert '用例（3）' in joined
    # 展开首个用例 Collapsible → 参考参数块出现
    _click(drv, By.XPATH, "//*[@data-slot='collapsible-trigger']")
    time.sleep(0.6)
    body_texts = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']")
    assert any('参考参数' in t for t in body_texts), f'用例展开后应显示参考参数块 {body_texts}'


def test_05_frozen_report_dialog(drv):
    """P5 冻结报告弹窗：已发布展开行「查看冻结报告」→ 查看源报告 link + 统计行"""
    _login(drv)
    _goto(drv, '/tasks/published')
    time.sleep(0.8)
    _click(drv, By.XPATH, "//button[contains(., '版本')]")
    time.sleep(0.8)
    _click(drv, By.XPATH, "//button[contains(., '查看冻结报告')]")
    time.sleep(0.8)
    dialog_texts = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']")
    joined = ' '.join(dialog_texts)
    assert '冻结报告（发布时快照' in joined
    assert '查看源报告 #' in joined
    assert '用例总数' in joined and '通过率' in joined


def test_06_reevaluate_dimension_and_hard_confirm(drv):
    """P6 重新评估弹窗：维度勾选网格（默认全选）+ 重新提取设备输出 + 复核硬确认层"""
    _login(drv)
    _goto(drv, '/tasks/daily')
    # 逐行打开操作菜单，找到含「重新评估」的行（终态任务；mock 详情 review_count=2）
    opened = False
    for i in range(8):
        _wait(drv, By.CSS_SELECTOR, 'button[aria-label="任务操作"]')
        btns = drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')
        if i >= len(btns):
            break
        btns[i].click()
        time.sleep(0.8)
        items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']")
        reeval = [it for it in items if '重新评估' in it.text]
        if reeval:
            reeval[0].click()
            opened = True
            break
        drv.find_element(By.TAG_NAME, 'body').send_keys('')
        time.sleep(0.4)
    assert opened, '应至少有一行提供「重新评估」菜单项'
    time.sleep(0.8)
    dialog_texts = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']")
    joined = ' '.join(dialog_texts)
    assert '重新评估' in joined
    assert '评估维度（默认全选）' in joined
    assert '重新提取设备输出（从存档日志）' in joined
    # 确认 → 存在复核结果时先弹硬确认层（§5.7 覆盖并继续）
    _click(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '确认')]")
    time.sleep(0.6)
    confirm_texts = _texts(drv, By.XPATH, "//*[@data-slot='alert-dialog-content']")
    joined_confirm = ' '.join(confirm_texts)
    assert '人工复核结果' in joined_confirm and '覆盖并继续' in joined_confirm, \
        f'应弹出人工复核硬确认层，实际 {joined_confirm}'
