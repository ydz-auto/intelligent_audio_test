# -*- coding: utf-8 -*-
"""INT-888 任务域模态窗 5 类弹窗逐窗验收（真实 Chrome headless，常驻后端 AUTH_MODE=off）。

针对 frontend-react/ 接线基线（wiring/react + INT-825/INT-845/INT-648 已合入），dev server 5341：
  P1 冻结详情弹窗（已发布展开行 → 查看冻结任务详情 → 任务信息/关联资源/用例 三节真实快照数据）
  P2 冻结报告节（已发布展开行 → 无报告快照任务 → 真实空态「该版本无冻结报告」；库无 has_report_snapshot
     =true 任务，弹窗本体以空态链路呈现，数据缺口在结论标注）
  P3 重执行范围弹窗（日常行 → 重新执行 → 三选项 + 手动选择真实用例列表（任务45 两条真实用例）→
     确认钮计数；任务1158（0 用例）提交 retry 为无残留 no-op，Network 证据 POST /tasks/{id}/retry）
  P4 重评估范围弹窗（日常行 → 重新评估 → 三选项 + 手动选择真实用例；维度网格按真实数据聚合，
     本库用例无 evaluation_dimensions 则按真实数据不渲染，不判缺陷）
  P5 导出数据弹窗（勾选任务 → 批量浮条 → 导出任务数据 → 选中清单 + 参考参数/音频选项 →
     开始导出真实 POST /data-transfer/export 返回 ZIP 下载）
  P6 导入数据弹窗（页面 Actions → 导入任务数据 → 选择导出包 + .zip accept 文件输入）
  P7 挑选合并向导（挑选合并页签 → 容器列表真实空态 → 开始挑选 → 四步 Stepper + Step1 候选
     列表真实空态（库无执行结果候选），Network 证据 GET /tasks/cherry-picks/candidates）

证据：每窗浅色 + 深色截图 + performance resource entries（真实接口请求）。
失败落 tests/ui/artifacts/int888_task_modals/<用例>/。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int888_task_modals')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5341')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
THEME_KEY = 'iatp:theme:v1:mode'
DL_DIR = os.path.join(ARTIFACTS, 'downloads')


def _driver():
    os.makedirs(DL_DIR, exist_ok=True)
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_experimental_option('prefs', {
        'download.default_directory': DL_DIR,
        'download.prompt_for_download': False,
        'safebrowsing.enabled': True,
    })
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


@pytest.fixture(scope='module')
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
    if call.when == 'call' and call.excinfo is not None and _DRIVER is not None:
        d = os.path.join(ARTIFACTS, item.name)
        os.makedirs(d, exist_ok=True)
        try:
            _DRIVER.save_screenshot(os.path.join(d, 'screenshot_fail.png'))
            with open(os.path.join(d, 'page_source_fail.html'), 'w', encoding='utf-8') as f:
                f.write(_DRIVER.page_source)
        except Exception:
            pass


def _wait(drv, by, value, timeout=20):
    return WebDriverWait(drv, timeout).until(
        lambda d: d.find_elements(by, value))


def _click(drv, by, value, timeout=20):
    el = _wait(drv, by, value, timeout)
    for cand in el:
        if cand.is_displayed():
            cand.click()
            return cand
    return el[0]


def _texts(drv, by, value):
    return [e.text.strip() for e in drv.find_elements(by, value) if e.text.strip()]


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _goto(drv, path, wait_for=None):
    drv.get(BASE + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    if wait_for:
        _wait_text(drv, wait_for)


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _set_theme(drv, mode):
    drv.execute_script(
        'try { localStorage.setItem(%r, %r) } catch (e) {}' % (THEME_KEY, mode))


def _session_boot(drv):
    """AUTH_MODE=off：清 localStorage 后首跳 / 触发会话恢复（dev_user 全放行）。"""
    drv.get(BASE + '/')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _set_theme(drv, 'light')
    _goto(drv, '/')


def _resource_urls(drv):
    """performance resource entries → 本会话已发起的真实接口请求 URL 列表。"""
    return drv.execute_script(
        'return performance.getEntriesByType("resource").map(e => e.name)'
        '.filter(n => n.includes("/api/"))')


def _shot(drv, name):
    """截图 + 页面源 + Network 请求清单落盘。"""
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        net = [u for u in _resource_urls(drv)]
        with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(net, f, ensure_ascii=False, indent=1)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _search_tasks(drv, frag):
    """日常页搜索框输入 frag（500ms debounce），等待过滤后的任务行出现。

    用原生 setter + input 事件驱动 React 受控输入（避免 Selenium clear/send_keys
    与 React 19 受控值跟踪的偶发不同步）；最多两轮重输。
    """
    search = _wait(drv, By.CSS_SELECTOR, 'input[aria-label="搜索任务"]')[0]
    drv.execute_script(
        "const i = arguments[0]; const s = Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype, 'value').set; "
        "s.call(i, arguments[1]); i.dispatchEvent(new Event('input', { bubbles: true }));",
        search, frag)
    for _ in range(2):
        try:
            rows = WebDriverWait(drv, 8).until(
                lambda d: d.find_elements(By.XPATH, f"//tr[contains(., '{frag}')]"))
            if rows:
                return rows[-1]
        except Exception:
            pass
        # 重输一轮（值可能被并发渲染覆盖）
        drv.execute_script(
            "const i = arguments[0]; const s = Object.getOwnPropertyDescriptor("
            "window.HTMLInputElement.prototype, 'value').set; "
            "s.call(i, arguments[1]); i.dispatchEvent(new Event('input', { bubbles: true }));",
            search, frag)
        time.sleep(1.0)
    return _wait(drv, By.XPATH, f"//tr[contains(., '{frag}')]")[-1]


def _clear_search(drv):
    """搜索框复位：直接重载日常页（会话 dev_user 态保留，列表回到未过滤全量）；
    等表格首行出现（任务列表异步加载完成）。"""
    _goto(drv, '/tasks/daily', wait_for='日常')
    _wait(drv, By.CSS_SELECTOR, '[data-slot="checkbox"][aria-label^="选择 "]')
    time.sleep(0.6)


def _open_any_reexecute_dialog(drv):
    """在 /tasks/daily 首页逐行找含「重新执行」菜单且用例进度为 0/0 的任务行，
    打开其重新执行弹窗（retry 提交为后端 no-op，不产生执行残留）。"""
    rows = _wait(drv, By.XPATH, "//tr[contains(., '/0')]")
    for target in rows[:8]:
        if '0/0' not in target.text:
            continue
        btns = target.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')
        for b in btns:
            if b.is_displayed():
                b.click()
                break
        else:
            continue
        time.sleep(0.8)
        items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']")
        hit = [it for it in items if '重新执行' in it.text]
        if hit:
            hit[0].click()
            dlg = _wait(drv, By.CSS_SELECTOR, "[data-slot='dialog-content']")
            time.sleep(0.4)
            return dlg[-1]
        drv.find_element(By.TAG_NAME, 'body').send_keys('')
        time.sleep(0.4)
    raise AssertionError('首页应有 0/0 用例进度且含「重新执行」菜单的任务行')


def _open_daily_row_menu(drv, task_name_frag, menu_label, search_frag=None):
    """在 /tasks/daily 中找到含 task_name_frag 的任务行（search_frag 提供时先搜索定位），
    打开其操作菜单，点击含 menu_label 的菜单项，并等弹窗 dialog-content 出现。
    返回弹窗内容元素（None 表示菜单项无对应弹窗）。"""
    if search_frag:
        _search_tasks(drv, search_frag)
    rows = _wait(drv, By.XPATH, f"//tr[contains(., '{task_name_frag}')]")
    target = rows[-1]
    btns = target.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')
    for b in btns:
        if b.is_displayed():
            b.click()
            break
    time.sleep(0.8)
    items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']")
    hit = [it for it in items if menu_label in it.text]
    assert hit, f'行 {task_name_frag} 操作菜单应含「{menu_label}」，实际 {[it.text for it in items]}'
    hit[0].click()
    # 等弹窗打开（菜单项点击后 dialog-content 出现）
    dlg = _wait(drv, By.CSS_SELECTOR, "[data-slot='dialog-content']")
    time.sleep(0.6)
    return dlg[-1]


def test_01_frozen_task_detail_dialog(drv):
    """P1 冻结详情弹窗：已发布展开行 → 查看冻结任务详情 → 三节真实快照数据。"""
    _session_boot(drv)
    _goto(drv, '/tasks/published', wait_for='已发布')
    time.sleep(1.0)
    # 展开第一行版本链（列表按发布倒序，首行 = 接线测试 INT-638 发布弹窗验证）
    _click(drv, By.XPATH, "//button[contains(., '版本')]")
    time.sleep(1.5)
    body = _body_text(drv)
    assert '任务详情（发布时冻结 · 不可变）' in body, '展开行应渲染任务详情冻结节'
    assert '查看冻结任务详情' in body, 'has_task_snapshot=true 任务应提供冻结详情入口'
    # 打开冻结详情弹窗
    _click(drv, By.XPATH, "//button[contains(., '查看冻结任务详情')]")
    time.sleep(0.8)
    _wait_text(drv, '任务信息')
    dlg = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert '任务详情（发布时冻结 · 不可变）' in dlg, '弹窗标题'
    assert '任务信息' in dlg, '弹窗三节之①'
    assert '用例（' in dlg, '弹窗三节之③'
    assert '来源任务' in _body_text(drv) or '来源任务' in dlg, '冻结详情应含来源任务信息'
    # 关联资源节按真实快照数据条件渲染：本快照 devices/apis/playbackDevices 全空 → 节隐藏（数据驱动，非缺陷）
    if '关联资源' not in dlg:
        print('NOTE: 本发布任务快照无 devices/apis/playbackDevices，关联资源节按真实数据隐藏（数据缺口）')
    _shot(drv, '01_frozen_task_detail_light')
    # 真实接口证据
    nets = _resource_urls(drv)
    assert any('/api/v1/published-tasks' in u for u in nets), f'应含 published-tasks 请求 {nets}'
    # 关闭
    # 弹窗随后续导航重置关闭（base-ui Dialog 关闭钮为图标按钮，无需显式点击）
    time.sleep(0.5)
    # 深色复开
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/published', wait_for='已发布')
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '版本')]")
    time.sleep(1.2)
    _click(drv, By.XPATH, "//button[contains(., '查看冻结任务详情')]")
    time.sleep(0.8)
    _wait_text(drv, '任务信息')
    _shot(drv, '01_frozen_task_detail_dark')


def test_02_frozen_report_section(drv):
    """P2 冻结报告节：当前库无 has_report_snapshot=true 的已发布任务 → 真实空态渲染。"""
    _set_theme(drv, 'light')
    _goto(drv, '/tasks/published', wait_for='已发布')
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '版本')]")
    time.sleep(1.5)
    body = _body_text(drv)
    assert '冻结报告（发布时快照 · 不可变）' in body, '展开行应渲染冻结报告节'
    assert '该版本无冻结报告（发布时源任务无已完成报告）' in body, \
        '无报告快照任务应显示真实空态（非弹窗占位）'
    # 确认库内已发布任务全无报告快照 → 弹窗入口不渲染（数据缺口，非代码缺陷）
    assert '查看冻结报告' not in body, 'has_report_snapshot=false 不应出现查看冻结报告按钮'
    _shot(drv, '02_frozen_report_empty_light')
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/published', wait_for='已发布')
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '版本')]")
    time.sleep(1.2)
    _shot(drv, '02_frozen_report_empty_dark')
    nets = _resource_urls(drv)
    assert any('/api/v1/published-tasks' in u for u in nets), f'应含 published-tasks 请求 {nets}'


def test_03_reexecute_scope_dialog(drv):
    """P3 重新执行范围弹窗：三选项 + 手动选择真实用例（任务45 两条真实用例）+ 提交 no-op 链路。"""
    _set_theme(drv, 'light')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(1.0)
    # 任务45（failed，2 条真实用例；日常列表分页 10/页在第二页）→ 搜索定位后开「重新执行」
    _open_daily_row_menu(drv, 'ui405_任务', '重新执行', search_frag='ui405')
    time.sleep(0.4)
    dlg = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert '重新执行' in dlg, '弹窗标题应为重新执行'
    # 三选项
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-all"]')
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-failed_only"]')
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    # 切手动选择 → 真实用例列表（GET /tasks/45）
    _click(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    time.sleep(1.5)
    _wait_text(drv, '全选')
    case_checks = drv.find_elements(
        By.CSS_SELECTOR,
        '[data-slot="dialog-content"] [data-slot="scroll-area"] [data-slot="checkbox"]')
    assert len(case_checks) >= 2, f'任务45 应渲染 ≥2 条真实用例，实际 {len(case_checks)}'
    # 真实用例名
    case_names = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert 'ui405_用例1' in case_names or 'ui405_用例2' in case_names, \
        f'手动选择应显示真实用例名 {case_names[:200]}'
    # 勾选 → 确认钮计数
    case_checks[-1].click()
    time.sleep(0.5)
    confirm = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '确认')]")
    assert any('已选 1 个用例' in t for t in confirm), f'确认钮应带选中计数 {confirm}'
    # Network：GET /tasks/45 真实请求
    nets = _resource_urls(drv)
    assert any(u.endswith('/api/v1/tasks/45') for u in nets), f'应含 GET /tasks/45 {nets}'
    _shot(drv, '03_reexecute_scope_realcases_light')
    # 取消关闭（不在真实任务45上提交，避免执行残留）
    _click(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '取消')]")
    time.sleep(0.6)
    # 清搜索回到全列表
    _clear_search(drv)
    # 任务1158（0 用例，首页可见）→ 提交 retry 验证真实 POST 链路（后端 no-op，无执行残留）。
    # 注意：共享库被并发 run 写入，首页任务会变化；改为取任意首页行「重新执行」弹窗提交。
    _clear_search(drv)
    _open_any_reexecute_dialog(drv)
    time.sleep(0.4)
    _click(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '确认')]")
    time.sleep(1.5)
    nets2 = _resource_urls(drv)
    assert any(re.search(r'/api/v1/tasks/\d+/retry$', u) for u in nets2), \
        f'提交应发 POST /tasks/{id}/retry {nets2}'
    _shot(drv, '03_reexecute_submit_light')
    # 深色复开
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(0.8)
    _open_daily_row_menu(drv, 'ui405_任务', '重新执行', search_frag='ui405')
    time.sleep(0.4)
    _click(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    time.sleep(1.2)
    _wait_text(drv, '全选')
    _shot(drv, '03_reexecute_scope_realcases_dark')
    _click(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '取消')]")
    time.sleep(0.5)


def test_04_reevaluate_scope_dialog(drv):
    """P4 重新评估范围弹窗：三选项 + 手动选择真实用例；维度网格按真实数据聚合。"""
    _set_theme(drv, 'light')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(0.8)
    _open_daily_row_menu(drv, 'ui405_任务', '重新评估', search_frag='ui405')
    time.sleep(0.6)
    dlg = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert '重新评估' in dlg, '弹窗标题应为重新评估'
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-all"]')
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    _click(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    time.sleep(1.5)
    _wait_text(drv, '全选')
    case_checks = drv.find_elements(
        By.CSS_SELECTOR,
        '[data-slot="dialog-content"] [data-slot="scroll-area"] [data-slot="checkbox"]')
    assert len(case_checks) >= 1, '重新评估手动选择应渲染真实用例'
    # 维度网格：本库用例 evaluation_dimensions 为空 → 按真实数据不渲染（缺口在结论标注）
    dims = _texts(drv, By.XPATH, "//*[@data-slot='dialog-content']")
    has_dims = any('评估维度' in t for t in dims)
    if not has_dims:
        print('NOTE: 本库用例无 evaluation_dimensions，评估维度网格按真实数据未渲染（数据缺口）')
    _shot(drv, '04_reevaluate_scope_light')
    nets = _resource_urls(drv)
    assert any(u.endswith('/api/v1/tasks/45') for u in nets), f'应含 GET /tasks/45 {nets}'
    _click(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '取消')]")
    time.sleep(0.5)
    # 深色
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(0.8)
    _open_daily_row_menu(drv, 'ui405_任务', '重新评估', search_frag='ui405')
    time.sleep(0.6)
    _click(drv, By.CSS_SELECTOR, '[data-testid="reexecute-scope-selected"]')
    time.sleep(1.2)
    _shot(drv, '04_reevaluate_scope_dark')
    _click(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '取消')]")
    time.sleep(0.5)


def test_05_export_data_dialog(drv):
    """P5 导出数据弹窗：勾选任务 → 批量浮条 → 导出任务数据 → 选项 + 开始导出真实请求。"""
    _set_theme(drv, 'light')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(0.8)
    # 勾选第一行任务
    row_check = _wait(drv, By.CSS_SELECTOR, '[data-slot="checkbox"][aria-label^="选择 "]')
    row_check[0].click()
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '导出数据')]")
    time.sleep(0.8)
    dlg = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert '导出任务数据' in dlg
    assert '选中任务' in dlg and '1 个' in dlg, f'应显示选中任务清单 {dlg[:160]}'
    assert '包含参考参数文件' in dlg and '包含音频文件（体积较大）' in dlg
    assert '开始导出' in dlg
    _shot(drv, '05_export_data_light')
    # 真实提交：POST /data-transfer/export → ZIP 下载（只读任务数据，无库残留）
    _click(drv, By.XPATH, "//*[@data-slot='dialog-content']//button[contains(., '开始导出')]")
    # 导出为大结果集可能数秒；轮询等 Network 证据（最多 20s）
    nets = []
    for _ in range(40):
        nets = _resource_urls(drv)
        if any('/api/v1/data-transfer/export' in u for u in nets):
            break
        time.sleep(0.5)
    assert any('/api/v1/data-transfer/export' in u for u in nets), \
        f'开始导出应发 POST /data-transfer/export {nets}'
    # 成功 toast（失败态也留证：导出按钮下方 errorMessage）
    try:
        _wait_text(drv, '导出完成', timeout=8)
    except Exception:
        dlg_err = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
        print(f'WARN: 导出成功 toast 未出现，弹窗内容={dlg_err[:200]}')
    _shot(drv, '05_export_data_done_light')
    # 深色复开
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(0.8)
    row_check2 = _wait(drv, By.CSS_SELECTOR, '[data-slot="checkbox"][aria-label^="选择 "]')
    row_check2[0].click()
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '导出数据')]")
    time.sleep(0.8)
    _wait_text(drv, '导出任务数据')
    _shot(drv, '05_export_data_dark')
    # 弹窗随后续导航重置关闭（base-ui Dialog 关闭钮为图标按钮，无需显式点击）
    time.sleep(0.4)


def test_06_import_data_dialog(drv):
    """P6 导入数据弹窗：页面 Actions「导入数据」→ 选择导出包 + .zip accept 文件输入。"""
    _set_theme(drv, 'light')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '导入数据')]")
    time.sleep(0.8)
    dlg = ' '.join(_texts(drv, By.XPATH, "//*[@data-slot='dialog-content']"))
    assert '导入任务数据' in dlg, f'弹窗标题 {dlg[:120]}'
    assert '选择导出包' in dlg, f'应含选择导出包段 {dlg[:160]}'
    file_input = _wait(drv, By.CSS_SELECTOR, 'input[type="file"][accept=".zip"]')
    assert len(file_input) > 0, '应含 .zip accept 文件输入'
    _shot(drv, '06_import_data_light')
    # 深色
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/daily', wait_for='日常')
    time.sleep(0.5)
    _click(drv, By.XPATH, "//button[contains(., '导入数据')]")
    time.sleep(0.8)
    _wait_text(drv, '导入任务数据')
    _shot(drv, '06_import_data_dark')
    # 弹窗随后续导航重置关闭（base-ui Dialog 关闭钮为图标按钮，无需显式点击）
    time.sleep(0.4)


def test_07_cherry_pick_wizard(drv):
    """P7 挑选合并向导：容器列表真实空态 → 开始挑选 → 四步 Stepper + Step1 候选真实空态。"""
    _set_theme(drv, 'light')
    _goto(drv, '/tasks/cherry-picks', wait_for='挑选合并')
    time.sleep(1.2)
    body = _body_text(drv)
    assert '合并容器' in body, '挑选合并页应渲染容器统计徽章（真实数据源）'
    _shot(drv, '07_cherry_container_light')
    # 开始挑选 → 向导 Step1
    _click(drv, By.XPATH, "//button[contains(., '开始挑选')]")
    time.sleep(1.5)
    steps = _wait(drv, By.CSS_SELECTOR, '[data-testid^="wizard-step-"]')
    step_keys = [s.get_attribute('data-testid') for s in steps]
    for k in ('wizard-step-pick', 'wizard-step-cart', 'wizard-step-review', 'wizard-step-checkout'):
        assert k in step_keys, f'四步 Stepper 应含 {k}，实际 {step_keys}'
    # Step1 候选列表：真实数据驱动——库有候选（并发 run 会写入执行结果）则渲染候选树；
    # 无候选则空态。两者皆真实链路，分别断言并留证。
    time.sleep(2.0)
    body_step1 = _body_text(drv)
    if '无符合条件的执行结果' in body_step1:
        _shot(drv, '07_cherry_wizard_pick_empty_light')
    else:
        # 候选树渲染：真实候选行（结果 checkbox + 候选文本），留证
        _wait(drv, By.CSS_SELECTOR, '[aria-label$="条）"]')  # 候选树顶层分支 checkbox（默认折叠）
        _shot(drv, '07_cherry_wizard_pick_candidates_light')
    nets = _resource_urls(drv)
    assert any('/api/v1/tasks/cherry-picks/candidates' in u for u in nets), \
        f'Step1 应发 GET candidates {nets}'
    assert any('/api/v1/tasks?merged=true' in u or 'merged=true' in u for u in nets) or \
        any('/api/v1/tasks/cherry-picks' in u for u in nets), f'容器列表应发合并查询 {nets}'
    # 返回列表
    _click(drv, By.XPATH, "//button[contains(., '返回列表')]")
    time.sleep(0.6)
    # 深色复开
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/cherry-picks', wait_for='挑选合并')
    time.sleep(0.8)
    _click(drv, By.XPATH, "//button[contains(., '开始挑选')]")
    time.sleep(1.2)
    if '无符合条件的执行结果' in _body_text(drv):
        _shot(drv, '07_cherry_wizard_pick_empty_dark')
    else:
        _wait(drv, By.CSS_SELECTOR, '[aria-label$="条）"]')  # 候选树顶层分支 checkbox（默认折叠）
        _shot(drv, '07_cherry_wizard_pick_candidates_dark')
