# -*- coding: utf-8 -*-
"""INT-508 算法配置页可视稿 浏览器走查（真实 Chrome headless，按 test_ui_11 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. 列表页：标题徽标「共 7 个算法」+ 十列数据表 + 状态徽章 + 当前全局算法徽章 + 分页
2. 搜索「搜索算法类型或名称」/ 分组 facet / 状态 facet 筛选
3. 行菜单：详情（只读 Dialog）/ 编辑（五 Tab Sheet + 代码禁用）/ 复制（副本预填）/
   删除（ConfirmDialog）
4. 新建算法：五 Tab Sheet 全量编辑、保存聚合入库、列表计数刷新（成功后删除还原基线）
5. 分组管理：分组表 + 新建分组表单 + 删除 cascade 提示
6. 导入/导出/重载：JSON 导入校验、导出 toast、重载 ConfirmDialog + toast
7. 批量删除（勾选 → 浮条 → ConfirmDialog）+ 全局算法切换器联动高亮

失败落 tests/ui/artifacts/int508_algorithm_config/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int508_algorithm_config')

# 5273 = 本工作区常驻 dev server；env 可覆写（INT-473 隔离副本为 5274）
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
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
_CONSOLE_SEVERE = []


def _drain_console(drv):
    """把浏览器 console 累积的 SEVERE 条目归入会话级列表（get_log 只返回上次调用后的增量）。"""
    global _CONSOLE_SEVERE
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                _CONSOLE_SEVERE.append(entry.get('message', ''))
    except Exception:
        pass


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
    # 会话级登录（demo_admin 权限 '*'），单跑任意用例也能通过路由守卫
    try:
        _login(_DRIVER)
    except Exception:
        pass
    yield _DRIVER
    try:
        _drain_console(_DRIVER)
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _login(drv, username='demo_admin'):
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _wait_rows(drv, n):
    WebDriverWait(drv, 12).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == n)


def _wait_rows_retry(drv, n):
    """等待列表行数；8s 未达到则刷新页面重试一次（dev server HMR 重编译期间防抖）。"""
    try:
        _wait_rows(drv, n)
        return
    except Exception:
        drv.refresh()
        time.sleep(1.5)
        _wait_rows(drv, n)


def _open_row_menu(drv, name):
    """点击指定算法行的「⋯」操作菜单（aria-label='算法 {name} 的操作'）。"""
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='算法 {name} 的操作']")
    btn.click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))


def _click_menu_item(drv, label):
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
    for it in items:
        if label in it.text:
            it.click()
            return
    raise AssertionError(f'行菜单项「{label}」未找到')


def _click_more_action(drv, label):
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menu_item(drv, label)


def _clear_input(drv, el):
    """用原生 value setter + input 事件清空受控输入（Selenium clear() 不触发 React onChange）。"""
    drv.execute_script(
        "const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
        "s.call(arguments[0], '');"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
        el)
    time.sleep(0.6)


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def _alert_button(drv, text):
    return drv.find_element(
        By.XPATH, f"//*[@role='alertdialog']//button[contains(., '{text}')]")


# ── 1. 列表页：标题徽标 + 十列数据表 + 状态徽章 + 当前全局算法徽章 + 分页 ───
def test_01_list_page_render(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    txt = _body_text(drv)
    assert '算法配置' in txt, f'页面标题缺失：{txt[:120]}'
    assert '共 7 个算法' in txt, f'标题徽标计数缺失：{txt[:200]}'
    # 搜索框占位（§3.4）
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索算法']")
    assert search.get_attribute('placeholder') == '搜索算法类型或名称', \
        f'搜索占位错误：{search.get_attribute("placeholder")}'
    # 十列表头（勾选列无文字，断言其余九列）
    for header in ['ID', '算法类型', '名称', '分组', '参数数', '关联用例',
                   '状态', '更新时间', '操作']:
        assert header in txt, f'列头「{header}」缺失'
    # 7 行 mock 数据
    _wait_rows(drv, 7)
    for row in ['通用识别引擎', '流式识别引擎', '多维评估集成', '实验识别引擎',
                '语音合成引擎', '端点检测引擎', '唤醒词识别']:
        assert row in txt, f'算法行「{row}」缺失'
    # 状态徽章（§3.4 online=上线 / offline=下线）
    assert txt.count('上线') == 5, f'上线徽章应 5 枚，实际 {txt.count("上线")}'
    assert txt.count('下线') == 2, f'下线徽章应 2 枚，实际 {txt.count("下线")}'
    # 当前全局算法徽章（默认 asr-v3=通用识别引擎，§2.2）
    global_rows = drv.find_elements(By.XPATH, "//tr[.//*[contains(., '当前全局算法')]]")
    assert len(global_rows) == 1, f'当前全局算法徽章应恰好 1 行，实际 {len(global_rows)}'
    assert '通用识别引擎' in global_rows[0].text, '默认全局算法应为 通用识别引擎 行'
    # 分页（§3.7）
    assert '共 7 条' in txt, f'分页计数缺失：{txt[-120:]}'
    assert '1 / 1' in txt, f'分页页码缺失：{txt[-120:]}'


# ── 2. 搜索 / 分组 / 状态 facet 筛选 ──
def test_02_search_and_facets(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    # 搜索 asr → 3 行（asr-v3 / asr-stream / asr-experimental）
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索算法']")
    search.send_keys('asr')
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == 3)
    txt = _body_text(drv)
    assert '通用识别引擎' in txt and '流式识别引擎' in txt and '实验识别引擎' in txt
    assert '多维评估集成' not in txt, '搜索 asr 不应出现 eval-ensemble'
    # 清除搜索 → 7 行（Selenium clear() 不触发 React onChange，用原生 setter）
    _clear_input(drv, search)
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == 7)
    # 分组 facet：语音识别 → 3 行
    grp = drv.find_element(By.XPATH, "//button[@aria-label='分组']")
    grp.click()
    time.sleep(0.4)
    drv.find_element(By.XPATH, "//*[@role='option'][contains(., '语音识别')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == 3)
    txt = _body_text(drv)
    assert '语音合成引擎' in txt and '唤醒词识别' in txt, f'语音识别分组行缺失：{txt[:200]}'
    assert '流式识别引擎' not in txt, '语音识别分组不应含流式识别引擎'
    # 刷新还原 → 状态 facet：下线 → 2 行（实验识别引擎 + 唤醒词识别）
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    status = drv.find_element(By.XPATH, "//button[@aria-label='状态']")
    status.click()
    time.sleep(0.4)
    drv.find_element(By.XPATH, "//*[@role='option'][contains(., '下线')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == 2)
    txt = _body_text(drv)
    assert '实验识别引擎' in txt and '唤醒词识别' in txt
    assert '语音合成引擎' not in txt, '下线筛选不应含上线算法'


# ── 3. 行菜单：详情只读 Dialog ──
def test_03_row_menu_detail_dialog(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    _open_row_menu(drv, '通用识别引擎')
    # 行菜单四项（§3.5：详情/编辑/复制/删除）
    txt = _body_text(drv)
    for item in ['详情', '编辑', '复制', '删除']:
        assert item in txt, f'行菜单项「{item}」缺失'
    _click_menu_item(drv, '详情')
    WebDriverWait(drv, 8).until(
        lambda d: '算法定义与参数映射只读详情' in _body_text(drv))
    txt = _body_text(drv)
    # 基本信息（§7.2）
    for field in ['基本信息', '算法类型', '显示名称', '所属分组', '参数数量',
                  '创建时间', '更新时间', 'asr-v3']:
        assert field in txt, f'详情字段「{field}」缺失'
    # 参数定义 / 参数映射两区（§7.2 三页签）
    for section in ['参数定义', '参数映射']:
        assert section in txt, f'详情分区「{section}」缺失'
    for tab in ['设备参数', 'API参数', '评估参数']:
        assert tab in txt, f'详情页签「{tab}」缺失'
    _press_esc(drv)
    WebDriverWait(drv, 5).until(
        lambda d: '算法定义与参数映射只读详情' not in _body_text(drv))


# ── 4. 编辑 Sheet：五 Tab 分节 + 编辑态代码禁用 ──
def test_04_edit_sheet_five_tabs(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    _open_row_menu(drv, '通用识别引擎')
    _click_menu_item(drv, '编辑')
    WebDriverWait(drv, 8).until(lambda d: '编辑算法' in _body_text(drv))
    txt = _body_text(drv)
    # 五 Tab（§6.1）
    for tab in ['基本信息', '参数配置', '参考参数', '参数映射', '评估维度']:
        assert tab in txt, f'编辑 Sheet 分节「{tab}」缺失'
    # 编辑态算法代码禁用（§6.2 代码为主键）
    code = drv.find_element(By.XPATH, "//input[@id='algo-type']")
    assert code.get_attribute('disabled') is not None, '编辑态算法代码应禁用'
    assert code.get_attribute('value') == 'asr-v3', f'算法代码预填错误：{code.get_attribute("value")}'
    # 保存可用性（INT-508 P1：保存按钮不得恒禁用；编辑态预填合法时应可用）
    save_btn = drv.find_element(By.XPATH, "//button[normalize-space()='保存']")
    assert save_btn.is_enabled(), '编辑态保存按钮应可用（P1 修复后，预填合法即解锁）'
    # 保存链路：点击保存 → toast「算法已保存」（§6.3/§7.6 编辑态口径）+ 列表计数 7 不变
    save_btn.click()
    WebDriverWait(drv, 10).until(lambda d: '算法已保存' in _body_text(drv))
    _wait_rows_retry(drv, 7)
    txt = _body_text(drv)
    assert '通用识别引擎' in txt, f'编辑保存后列表丢失原算法：{txt[-200:]}'
    # 取消关闭
    _press_esc(drv)
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(drv))


# ── 5. 新建算法：五 Tab Sheet 保存入库 + 计数刷新（随后删除还原基线） ──
def test_05_create_algorithm_flow(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    # 页头「新建算法」（§3.3 主按钮）
    drv.find_element(By.XPATH, "//button[contains(., '新建算法')]").click()
    WebDriverWait(drv, 8).until(lambda d: '管理算法定义、参数与映射关系' in _body_text(drv))
    txt = _body_text(drv)
    for tab in ['基本信息', '参数配置', '参考参数', '参数映射', '评估维度']:
        assert tab in txt, f'新建 Sheet 分节「{tab}」缺失'
    # 基本信息（§6.2：算法代码 / 显示名称 / 所属分组必填）
    drv.find_element(By.XPATH, "//input[@id='algo-type']").send_keys('int508_algo')
    drv.find_element(By.XPATH, "//input[@id='algo-name']").send_keys('验收测试算法')
    drv.find_element(By.XPATH, "//button[contains(., '请选择分组')]").click()
    time.sleep(0.4)
    drv.find_element(By.XPATH, "//*[@role='option'][contains(., '语音识别')]").click()
    # 保存
    drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
    WebDriverWait(drv, 10).until(lambda d: '算法已创建' in _body_text(drv))
    WebDriverWait(drv, 10).until(lambda d: '共 8 个算法' in _body_text(drv))
    txt = _body_text(drv)
    assert '验收测试算法' in txt, f'新算法未出现在列表：{txt[-300:]}'
    # 还原基线：删除新建算法（§3.5 行菜单删除 → §7.5 ConfirmDialog）
    _open_row_menu(drv, '验收测试算法')
    _click_menu_item(drv, '删除')
    WebDriverWait(drv, 6).until(lambda d: '确认删除' in _body_text(drv))
    confirm = drv.find_element(
        By.XPATH, "//*[@role='alertdialog'][contains(., '确定要删除算法「验收测试算法」吗？')]")
    assert confirm, '删除确认文案缺失'
    _alert_button(drv, '删除').click()
    WebDriverWait(drv, 10).until(lambda d: '算法已删除' in _body_text(drv))
    WebDriverWait(drv, 10).until(lambda d: '共 7 个算法' in _body_text(drv))


# ── 6. 复制：确认 Dialog → 副本 Sheet 预填（type 加 _copy / name 加 (副本)） ──
def test_06_clone_flow(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    _open_row_menu(drv, '通用识别引擎')
    _click_menu_item(drv, '复制')
    WebDriverWait(drv, 6).until(lambda d: '确认复制' in _body_text(drv))
    txt = _body_text(drv)
    assert '副本将命名为「通用识别引擎 (副本)」并复制全部参数与映射。' in txt, \
        f'复制确认文案缺失：{txt[:300]}'
    drv.find_element(By.XPATH, "//button[contains(., '复制')]").click()
    WebDriverWait(drv, 8).until(lambda d: '复制算法' in _body_text(drv))
    code = drv.find_element(By.XPATH, "//input[@id='algo-type']")
    assert code.get_attribute('value') == 'asr-v3_copy', \
        f'副本算法代码应为 asr-v3_copy：{code.get_attribute("value")}'
    name = drv.find_element(By.XPATH, "//input[@id='algo-name']")
    assert name.get_attribute('value') == '通用识别引擎 (副本)', \
        f'副本显示名称应为「通用识别引擎 (副本)」：{name.get_attribute("value")}'
    # 保存可用性 + 复制保存链路（INT-508 P1：复制态保存不得恒禁用）
    save_btn = drv.find_element(By.XPATH, "//button[normalize-space()='保存']")
    assert save_btn.is_enabled(), '复制态保存按钮应可用（P1 修复后，副本预填合法即解锁）'
    save_btn.click()
    WebDriverWait(drv, 10).until(lambda d: '算法已创建' in _body_text(drv))
    WebDriverWait(drv, 10).until(lambda d: '共 8 个算法' in _body_text(drv))
    txt = _body_text(drv)
    assert '通用识别引擎 (副本)' in txt, f'副本未出现在列表：{txt[-200:]}'
    # 还原基线：删除副本
    _open_row_menu(drv, '通用识别引擎 (副本)')
    _click_menu_item(drv, '删除')
    WebDriverWait(drv, 6).until(lambda d: '确认删除' in _body_text(drv))
    _alert_button(drv, '删除').click()
    WebDriverWait(drv, 10).until(lambda d: '算法已删除' in _body_text(drv))
    WebDriverWait(drv, 10).until(lambda d: '共 7 个算法' in _body_text(drv))
    _press_esc(drv)


# ── 7. 分组管理：分组表 + 新建表单 + 删除 cascade 提示 ──
def test_07_group_manager(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    # 页头更多操作 → 分组管理（§3.3）
    _click_more_action(drv, '分组管理')
    WebDriverWait(drv, 8).until(lambda d: '算法分组管理' in _body_text(drv))
    txt = _body_text(drv)
    assert '管理算法分组，算法分组用于算法列表筛选与编辑时归属选择' in txt
    for header in ['分组名称', '描述', '排序', '算法数']:
        assert header in txt, f'分组表列头「{header}」缺失'
    for grp in ['语音识别', '流式处理', '评估分析', '实验预研']:
        assert grp in txt, f'分组「{grp}」缺失'
    # 新建分组小表单（§7.1）
    drv.find_element(By.XPATH, "//button[contains(., '新建分组')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//input[@id='group-name']"))
    _press_esc(drv)
    # 删除 cascade 提示（分组含算法时，§7.1）
    del_btn = drv.find_element(By.XPATH, "//button[@aria-label='删除分组 语音识别']")
    del_btn.click()
    WebDriverWait(drv, 6).until(lambda d: '删除分组' in _body_text(drv))
    cascade = drv.find_element(
        By.XPATH, "//*[@role='alertdialog'][contains(., '分组「语音识别」包含 3 个算法。删除分组不会删除算法（算法将变为未分组），确定删除吗？')]")
    assert cascade, '分组含算法删除 cascade 提示缺失'
    # cascade 确认删除：分组删除成功、算法保留变未分组（§3.6 对齐后端 soft_delete 契约，无拦截）
    _alert_button(drv, '删除').click()
    WebDriverWait(drv, 6).until(lambda d: '分组已删除' in _body_text(drv))
    WebDriverWait(drv, 6).until(lambda d: '语音识别' not in _body_text(drv))
    _press_esc(drv)


# ── 8. 导入 / 导出 / 重载 ──
def test_08_import_export_reload(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    # 导入算法 Dialog（§7.6，补现状缺口）
    _click_more_action(drv, '导入算法')
    WebDriverWait(drv, 8).until(lambda d: '支持 .json 文件，格式与导出算法一致' in _body_text(drv))
    # 非法 JSON → 内联错误
    ta = drv.find_element(By.XPATH, "//textarea[@aria-label='算法定义 JSON']")
    ta.send_keys('{not-json')
    drv.find_element(By.XPATH, "//button[contains(., '导入')]").click()
    WebDriverWait(drv, 6).until(lambda d: 'JSON 格式错误' in _body_text(drv))
    _press_esc(drv)
    # 导出算法（§7.14 直接下载 + toast）
    _click_more_action(drv, '导出算法')
    WebDriverWait(drv, 6).until(lambda d: '配置已导出' in _body_text(drv))
    # 重载配置（§7.7）
    _click_more_action(drv, '重载配置')
    WebDriverWait(drv, 6).until(
        lambda d: '将重载后端算法配置缓存，使最近变更立即生效。确定重载吗？' in _body_text(drv))
    _alert_button(drv, '重载').click()
    WebDriverWait(drv, 6).until(lambda d: '配置已重载' in _body_text(drv))


# ── 9. 批量删除 + 全局算法切换器联动 ──
def test_09_bulk_delete_and_global_switcher(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    # 勾选 2 行 → 批量浮条（§3.7）
    drv.find_element(By.XPATH, "//*[@role='checkbox'][@aria-label='选择算法 通用识别引擎']").click()
    drv.find_element(By.XPATH, "//*[@role='checkbox'][@aria-label='选择算法 流式识别引擎']").click()
    WebDriverWait(drv, 5).until(lambda d: '已选择 2 个算法' in _body_text(drv))
    drv.find_element(By.XPATH, "//button[contains(., '批量删除')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '将删除已选择的 2 个算法。此操作不可恢复。' in _body_text(drv))
    _alert_button(drv, '删除').click()
    # mock 7 个算法全部带关联用例（caseCount>0），批量删除应全数被拦截（§6.7/§7.8）
    WebDriverWait(drv, 8).until(lambda d: '成功删除 0 个算法，失败 2 个' in _body_text(drv))
    # 被拦截后行数不变，刷新恢复基线
    _wait_rows_retry(drv, 7)
    # 全局算法切换器联动（§2.2：切到 asr-stream 后对应行高亮）
    drv.find_element(By.XPATH, "//button[@aria-label='切换全局算法']").click()
    time.sleep(0.5)
    drv.find_element(By.XPATH, "//button[contains(., '流式识别引擎')]").click()
    time.sleep(0.8)
    global_rows = drv.find_elements(By.XPATH, "//tr[.//*[contains(., '当前全局算法')]]")
    assert len(global_rows) == 1, f'切换后应仍恰好 1 行高亮，实际 {len(global_rows)}'
    assert '流式识别引擎' in global_rows[0].text, \
        f'全局算法切换后应高亮 流式识别引擎 行：{global_rows[0].text}'
    # 还原默认全局算法
    drv.find_element(By.XPATH, "//button[@aria-label='切换全局算法']").click()
    time.sleep(0.5)
    drv.find_element(By.XPATH, "//button[contains(., '通用识别引擎')]").click()
    time.sleep(0.5)


# ── 10. 全会话无 JS 严重错误 ──
def test_10_no_severe_console_errors(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    time.sleep(1.0)
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, \
        '浏览器控制台存在 SEVERE 错误：\n' + '\n'.join(_CONSOLE_SEVERE)
