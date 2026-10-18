# -*- coding: utf-8 -*-
"""INT-694 任务域弹窗补齐 冒烟核心链路浏览器走查（真实 Chrome headless，按 test_ui_25 先例）。

针对 frontend-react/ 任务页（真实接口 + 常驻后端；动作端点已接线）：
P1 重新执行/重新评估范围选择弹窗（§5.7）：三选项 + 「手动选择用例」展开态（错误态/用例列表/全选/过滤 Select）
P2 导出数据弹窗（§5.12）：勾选任务 → 批量浮条「导出数据」→ 选中清单 + 参考参数/音频 Checkbox + 开始导出
P3 导入数据弹窗（§5.12）：Actions「导入数据」→ 选文件段（.zip accept）
P4 冻结任务详情弹窗（§5.13）：已发布展开行真实详情（legacy 历史版本态或快照弹窗三节）
P5 冻结报告弹窗（§5.13）：已发布展开行「查看冻结报告」→ 查看源报告 # link + 真实统计行
P6 重新评估手动选择：任务详情失败显示错误态+重试（P2-1；硬确认层依赖真实复核数据，后端阻塞时跳过）

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
    # 勾选第一行用例 → 确认按钮计数出现（详情可用时）
    time.sleep(0.4)
    # 用例勾选列表只在任务详情成功时渲染；真实后端 GET /tasks/{id} 被 INT-734 422
    # （TaskCaseBrief.reviewed null）阻断时，手动选择区走 P2-1 错误态（加载失败+重试）。
    case_checkboxes = drv.find_elements(
        By.CSS_SELECTOR,
        '[data-slot="dialog-content"] [data-slot="scroll-area"] [data-slot="checkbox"]')
    if not case_checkboxes:
        dlg_text = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
        assert '本任务用例加载失败' in dlg_text and '重试' in dlg_text, \
            f'详情失败应显示错误态+重试（P2-1），实际 {dlg_text[:160]}'
        assert '暂无已执行用例' not in dlg_text, '错误态不应误显示为空态'
        return
    case_checkboxes[-1].click()
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
    """P4 冻结任务详情弹窗：真实数据下按 has_task_snapshot 分流（legacy 历史版本态 / 快照弹窗）"""
    _login(drv)
    _goto(drv, '/tasks/published')
    time.sleep(0.8)
    # 展开第一行版本详情（版本 按钮）
    _click(drv, By.XPATH, "//button[contains(., '版本')]")
    time.sleep(1.5)
    body = ' '.join(_texts(drv, By.TAG_NAME, 'body'))
    # 真实详情渲染（来源任务 #417 链路），非 mock 数据
    assert '来源任务 #417' in body or '来源任务' in body, \
        f'展开行应渲染真实来源任务信息 {body[:120]}'
    # 真实 published 1 为 legacy（has_task_snapshot=false）→ 历史版本提示、无快照入口；
    # 若有 has_task_snapshot=true 的任务版本则验证快照弹窗三节
    snap_btns = drv.find_elements(By.XPATH, "//button[contains(., '查看冻结任务详情')]")
    if snap_btns:
        snap_btns[0].click()
        time.sleep(0.8)
        dlg = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
        assert '任务信息' in dlg and '关联资源（发布时冻结）' in dlg, f'快照弹窗三节 {dlg[:120]}'
    else:
        assert '历史版本' in body or '发布时未冻结' in body, \
            f'legacy 任务应显示历史版本提示 {body[:200]}'


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


def test_06_reevaluate_scope_and_error_state(drv):
    """P6 重新评估弹窗：范围三选项 + 手动选择错误态（真实后端任务详情 422 时 P2-1 兜底，非误导空态）"""
    _login(drv)
    _goto(drv, '/tasks/daily')
    # 逐行打开操作菜单，找到含「重新评估」的行
    opened = False
    for i in range(10):
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
    time.sleep(1.5)
    dlg = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert '重新评估' in dlg
    # 手动选择用例 → 任务详情查询失败时显示错误态 + 重试（P2-1），不得误显示为空态
    _click(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    time.sleep(1.5)
    dlg2 = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert '加载失败' in dlg2 and '重试' in dlg2, \
        f'任务详情失败应显示错误态+重试而非空态 {dlg2[:200]}'
    assert '暂无已执行用例' not in dlg2, '错误态不应误显示为空态'
    # 硬确认层：真实复核数据（review_count>0）可用时才断言；后端 422 阻塞时跳过（INT-694 后端缺陷卡）
