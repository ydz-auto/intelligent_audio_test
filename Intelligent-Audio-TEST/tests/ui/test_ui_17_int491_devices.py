# -*- coding: utf-8 -*-
"""INT-491 设备管理页可视稿 浏览器走查（真实 Chrome headless，按 test_ui_14 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. /devices → /devices/test：标题「设备管理」徽标「在线 5/共 9」+ 统计徽章行（总设备数/在线/
   离线/异常）+ 测试设备十数列 + 三开关页头 + 主按钮 + 更多操作
2. 页签切换：播放设备（声压映射列）/ 测试 API（端点展开 + RMS-SPL 默认映射）
3. 测试中占用态（INT-487）：音箱-客厅位状态位叠加「测试中」徽章 + 行菜单「停止测试」
4. 所属实验室列（INT-487）：声学实验室 A Badge / 未绑定
5. 监控告警面板（开关②）：统计徽章 + 告警列表 + 告警规则弹窗
6. 筛选：搜索 + 实验室 facet + 重置
7. 批量操作模式开关 → 行 Checkbox → 批量浮条
8. 弹窗群：扫描设备 / 新增抽屉 / 详情 / 分组管理 / 关联声压映射
9. 浏览器 console 无 SEVERE（主题/深浅色零特判）

失败落 tests/ui/artifacts/int491_devices/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int491_devices')

# 5273 = 本工作区常驻 dev server；env 可覆写
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
    drv.set_page_load_timeout(60)
    return drv


_DRIVER = None
_CONSOLE_SEVERE = []


def _drain_console(drv):
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
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)
    _drain_console(drv)


def _click_switch(drv, aria_label):
    """点页面级开关（§3.3 三开关：Base UI Switch 渲染 role='switch' 的按钮）"""
    drv.find_element(By.XPATH, f"//*[@role='switch'][@aria-label='{aria_label}']").click()
    time.sleep(0.5)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _login(drv, username='demo_admin'):
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _open_row_menu(drv, name):
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='操作 {name}']")
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


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.5)


# ── 1. 测试设备页签：标题徽标 + 统计徽章 + 列头 + 三开关 + 主按钮 ───
def test_01_test_tab_render(drv):
    _login(drv)
    _goto(drv, '/devices')
    assert '/devices/test' in drv.current_url, f'index 应重定向 /devices/test：{drv.current_url}'
    txt = _body_text(drv)
    assert '设备管理' in txt, f'页面标题缺失：{txt[:120]}'
    assert '在线 5/共 9' in txt, f'标题徽标「在线 5/共 9」缺失：{txt[:200]}'
    # 统计徽章行（§9）
    for stat in ['总设备数', '在线设备', '离线设备', '异常设备']:
        assert stat in txt, f'统计徽章「{stat}」缺失'
    # 三开关 + 主按钮（更多操作为图标钮，aria-label 承载，不入 textContent）
    for btn in ['批量操作模式', '监控告警面板', 'ID 排序', '添加测试设备']:
        assert btn in txt, f'页头控件「{btn}」缺失'
    assert len(drv.find_elements(By.XPATH, "//button[@aria-label='更多操作']")) == 1, \
        '更多操作图标钮缺失'
    # 列头（§3.4 含所属实验室 INT-487）
    for header in ['ID', '设备名称', '状态', '所属实验室', '系统', '型号', '序列号',
                   '连接方式', '支持算法', '最后在线', '操作']:
        assert header in txt, f'测试设备列头「{header}」缺失'
    # mock 首行 + 占用态（INT-487）
    assert '音箱-客厅位' in txt, 'mock 测试设备行缺失'
    assert '测试中' in txt, '「测试中」占用叠加态徽章缺失'
    assert '声学实验室 A' in txt, '所属实验室 Badge 缺失'
    assert '未绑定' in txt, '未绑定实验室口径缺失'
    # 搜索占位
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索设备名称或型号']")
    assert search.get_attribute('placeholder') == '搜索设备名称或型号', \
        f'搜索占位错误：{search.get_attribute("placeholder")}'
    _drain_console(drv)


# ── 2. 页签切换：播放设备 / 测试 API ───
def test_02_tab_switch(drv):
    _goto(drv, '/devices/test')
    drv.find_element(By.XPATH, "//button[contains(., '播放设备')]").click()
    WebDriverWait(drv, 10).until(lambda d: '/devices/playback' in d.current_url)
    time.sleep(1.0)
    txt = _body_text(drv)
    for header in ['名称', '设备类型', '所属实验室', '支持的格式', '系统唯一标识',
                   '支持的通道数', '采样率', '声压映射', '更新时间', '操作']:
        assert header in txt, f'播放设备列头「{header}」缺失'
    assert '参考音源-01' in txt, 'mock 播放设备行缺失'
    assert '干声设备' in txt and '噪声设备' in txt, '设备类型 Badge 缺失'
    # 测试 API 页签
    drv.find_element(By.XPATH, "//button[contains(., '测试 API')]").click()
    WebDriverWait(drv, 10).until(lambda d: '/devices/api' in d.current_url)
    time.sleep(1.0)
    txt = _body_text(drv)
    for header in ['API 名称', '协议', '环境', '状态', '端点数', '默认并发', '健康分',
                   'RMS-SPL 默认映射', '操作']:
        assert header in txt, f'API 列头「{header}」缺失'
    assert 'ASR HTTP API' in txt, 'mock API 行缺失'
    assert 'HTTPS' in txt and '测试' in txt, 'API 协议/环境 Badge 缺失'
    # API 端点展开（§3.6）
    drv.find_element(By.XPATH, "//button[contains(., 'ASR HTTP API')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '端点明细' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    for col in ['URL', '优先级', '最大进程', '超时', '音频时长']:
        assert col in txt, f'端点明细列头「{col}」缺失'
    assert '/v1/asr/stream' in txt, '端点明细 URL 缺失'
    _drain_console(drv)


# ── 3. 测试中占用态行菜单（INT-487） + 详情/编辑 ───
def test_03_row_actions(drv):
    _goto(drv, '/devices/test')
    # 被占用设备行菜单应显「停止测试」（§3.4.1）
    _open_row_menu(drv, '音箱-客厅位')
    _click_menu_item(drv, '停止测试')
    time.sleep(0.5)
    # 详情弹窗（§6.2 只读）
    _open_row_menu(drv, '音箱-客厅位')
    _click_menu_item(drv, '详情')
    WebDriverWait(drv, 6).until(
        lambda d: '测试设备详情' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '声学实验室 A' in txt, '详情弹窗所属实验室缺失'
    assert 'HDC 驱动 3.1' in txt, '详情弹窗驱动字段缺失'
    _press_esc(drv)
    # 编辑抽屉（§6.2）
    _open_row_menu(drv, '音箱-客厅位')
    _click_menu_item(drv, '编辑')
    WebDriverWait(drv, 6).until(
        lambda d: '编辑设备' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '是否需要提示词' in txt, '编辑抽屉「是否需要提示词」缺失'
    assert '高级设置' in txt, '编辑抽屉「高级设置」分区缺失'
    _press_esc(drv)
    _drain_console(drv)


# ── 4. 监控告警面板（开关②） + 告警规则弹窗 ───
def test_04_alarm_panel(drv):
    _goto(drv, '/devices/test')
    _click_switch(drv, '监控告警面板')
    # 面板展开：告警统计徽章行出现（监控告警标题常驻，不能以其出现为条件）
    WebDriverWait(drv, 8).until(
        lambda d: '待处理' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    for stat in ['待处理', '已确认', '已恢复', '总计']:
        assert stat in txt, f'告警统计徽章「{stat}」缺失'
    for col in ['级别', '设备', '规则', '指标', '内容', '邮件', '触发时间', '操作']:
        assert col in txt, f'告警列头「{col}」缺失'
    assert '离线时长' in txt, '告警指标中文映射缺失'
    assert '设备-异常节点' in txt, 'mock 告警行缺失'
    # 告警规则弹窗（§6.6）
    drv.find_element(By.XPATH, "//button[contains(., '告警规则')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '监控告警规则' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    for field in ['规则名称', '告警指标', '阈值', '告警级别', '邮件通知', '启用']:
        assert field in txt, f'告警规则字段「{field}」缺失'
    assert '离线超时告警' in txt, 'mock 告警规则行缺失'
    _press_esc(drv)
    _press_esc(drv)
    _drain_console(drv)


# ── 5. 筛选：搜索 + 实验室 facet + 重置 ───
def test_05_filters(drv):
    _goto(drv, '/devices/test')
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索设备名称或型号']")
    search.send_keys('卧室')
    # 等防抖提交且过滤生效：客厅位行消失（卧室位在过滤前已可见，不能以其出现为条件）
    WebDriverWait(drv, 8).until(
        lambda d: '音箱-客厅位' not in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '音箱-卧室位' in txt, '搜索「卧室」后应命中音箱-卧室位'
    # 重置
    drv.find_element(By.XPATH, "//button[contains(., '重置')]").click()
    WebDriverWait(drv, 8).until(
        lambda d: '音箱-客厅位' in d.execute_script('return document.body.textContent || ""'))
    # 实验室 facet（INT-487：选项动态 GET /laboratories）
    drv.find_element(By.XPATH, "//button[contains(., '实验室')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: '声学实验室 A' in d.execute_script('return document.body.textContent || ""'))
    _press_esc(drv)
    _drain_console(drv)


# ── 6. 批量操作模式 → 行 Checkbox → 批量浮条 ───
def test_06_bulk_actions(drv):
    _goto(drv, '/devices/test')
    _click_switch(drv, '批量操作模式')
    time.sleep(0.5)
    drv.find_element(By.XPATH,
        "//*[@role='checkbox'][@aria-label='选择设备 音箱-客厅位']").click()
    WebDriverWait(drv, 6).until(
        lambda d: '设备 1 个已选择' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    for btn in ['连接', '断开', '重启', '关机', '健康检查', '删除']:
        assert btn in txt, f'批量浮条按钮「{btn}」缺失'
    # 批量删除确认（§3.8）
    drv.find_element(By.XPATH, "//button[contains(., '删除')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog']"))
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '批量删除')]").click()
    time.sleep(0.8)
    _drain_console(drv)


# ── 7. 弹窗群：扫描 / 新增抽屉 / 分组管理 / 关联声压映射 ───
def test_07_modals(drv):
    _goto(drv, '/devices/test')
    # 更多操作 → 扫描设备（§6.1）
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menu_item(drv, '扫描设备')
    WebDriverWait(drv, 6).until(
        lambda d: '扫描测试设备' in d.execute_script('return document.body.textContent || ""'))
    drv.find_element(By.XPATH, "//button[contains(., '开始扫描')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '扫描完成' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '已添加' in txt, '扫描结果「已添加」徽标缺失'
    _press_esc(drv)
    # 新增抽屉（§6.2）
    drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '添加测试设备' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    for field in ['设备类型', '设备系统', '系统版本', '连接方式', '设备序列号', '是否需要提示词']:
        assert field in txt, f'新增抽屉字段「{field}」缺失'
    _press_esc(drv)
    # 分组管理（§6.3）
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menu_item(drv, '分组管理')
    WebDriverWait(drv, 6).until(
        lambda d: '设备分组管理' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '客厅组' in txt and '回归验证组' in txt, '分组列表缺失'
    assert '播放设备分组暂未实装' in txt or '播放设备组' in txt, '播放设备组禁用态缺失'
    _press_esc(drv)
    # 播放设备页签 → 关联声压映射（§6.4）
    drv.find_element(By.XPATH, "//button[contains(., '播放设备')]").click()
    WebDriverWait(drv, 10).until(lambda d: '/devices/playback' in d.current_url)
    time.sleep(0.8)
    _open_row_menu(drv, '参考音源-02')
    _click_menu_item(drv, '关联声压映射')
    WebDriverWait(drv, 6).until(
        lambda d: '关联声压映射' in d.execute_script('return document.body.textContent || ""'))
    _press_esc(drv)
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, f'浏览器 console SEVERE 错误：{_CONSOLE_SEVERE[:3]}'
