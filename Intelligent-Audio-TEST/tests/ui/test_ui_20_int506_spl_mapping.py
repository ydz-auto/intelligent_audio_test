# -*- coding: utf-8 -*-
"""INT-506 声压级映射管理页可视稿 浏览器走查（真实 Chrome headless，按 test_ui_17 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. /SPLMapping 物理域页签：标题「声压级映射管理」徽标「已校准 5/共 8」+ 双口径 Tabs +
   筛选工具栏（搜索+校准状态+关联播放设备）+ 统计徽章行（8/5/3/7）+ 十列 DataTable +
   页头动作区（批量配置 SPL/导入映射数据/添加增益映射）+ 三口径对称 Alert + 分页「共 8 条」
2. 数字域页签：徽标「已校准 3/共 6」+ 统计（6/3/3/5）+ 十列表 + 参考基准「65 dB / 1.0」+
   增益限幅「0.001 ~ 10.0」+ 默认 Badge + 主按钮「添加 RMS-SPL 映射」
3. 行操作菜单：物理域（详情/编辑/执行校准/校准历史/删除）+ 数字域（校准/设默认/详情/编辑/删除）
4. 弹窗群：增益映射详情 / RMS-SPL 数字校准（参考基准四格 + 校准点集表）
5. 筛选：搜索「客厅」→ 1 条 + 校准状态 facet「未校准」+ 重置
6. 主题抽屉：打开主题设置 → 切深浅色 → 页面正常
7. 浏览器 console 无 SEVERE（主题/深浅色零特判）

失败落 tests/ui/artifacts/int506_spl_mapping/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int506_spl_mapping')

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


def _goto_spl(drv):
    _login(drv)
    _goto(drv, '/SPLMapping')


def _open_row_menu(drv, name):
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='映射 {name} 的操作']")
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


def _switch_tab(drv, label):
    drv.find_element(By.XPATH, f"//*[@role='tab'][contains(., '{label}')]").click()
    time.sleep(1.0)
    _drain_console(drv)


# ── 1. 物理域页签：标题徽标 + 统计徽章 + 十列 + 页头动作区 + 三口径 Alert ───
def test_01_device_tab_render(drv):
    _goto_spl(drv)
    txt = _body_text(drv)

    assert '声压级映射管理' in txt, '标题缺失'
    assert '已校准 5/共 8' in txt, '物理域徽标「已校准 5/共 8」缺失'
    assert '设备 SPL（E2E）' in txt and 'API/Realtime RMS-SPL' in txt, '双口径 Tabs 缺失'

    # 统计徽章行（§4.1.2，SplStatsData 四字段）
    for label in ('映射总数', '已校准', '未校准', '关联设备数'):
        assert label in txt, f'统计徽章「{label}」缺失'

    # 物理域十列
    for col in ('ID', '映射名称', '关联播放设备', '设备类型', '测量距离',
                '目标声压级', '测试频率', '校准点数', '校准状态', '更新时间'):
        assert col in txt, f'物理域列头「{col}」缺失'

    # mock 行（§4.2，8 条全一页）
    for row in ('客厅_干声_65dB_1m', '车内_导航_65dB_0.5m', '会议室_多人_60dB_2m',
                '卧室_唤醒_70dB_1m', '厨房_噪声_55dB_1.5m', '书房_安静_60dB_0.8m',
                '大厅_远场_75dB_3m', '阳台_户外_65dB_1m'):
        assert row in txt, f'mock 物理域行「{row}」缺失'

    # 设备类型徽章 / 距离 / 目标声压级 / 频率（§4.2 渲染）
    assert '干声' in txt and '噪声' in txt, '设备类型徽章缺失'
    assert '1 米' in txt and '65 dB' in txt and '1000 Hz' in txt, '距离/目标声压级/频率渲染缺失'

    # 页头动作区（§4.1 Actions）
    for btn in ('批量配置 SPL', '导入映射数据', '添加增益映射'):
        assert btn in txt, f'物理域页头按钮「{btn}」缺失'

    # 三口径对称提示（§4.4）
    assert '三口径对称' in txt, '三口径 Alert 缺失'

    # 分页（§3.9/§4.1 Footer）
    assert '共 8 条' in txt, '分页「共 8 条」缺失'


# ── 2. 数字域页签：徽标 + 统计 + 十列 + 参考基准/增益限幅/默认 ───
def test_02_digital_tab_render(drv):
    _goto_spl(drv)
    _switch_tab(drv, 'API/Realtime RMS-SPL')
    txt = _body_text(drv)

    assert '已校准 4/共 6' in txt, '数字域徽标「已校准 4/共 6」缺失'
    for label in ('RMS-SPL 映射数', '已校准', '未校准', '关联 API 数'):
        assert label in txt, f'统计徽章「{label}」缺失'

    for col in ('映射名称', '关联 API', '协议', '供应商', '参考基准',
                '校准点数', '增益限幅', '校准状态', '默认'):
        assert col in txt, f'数字域列头「{col}」缺失'

    # mock 行（§4.3，6 条全一页）
    for row in ('客服ASR_WebSocket_默认', '导航ASR_HTTP_流式', '客服ASR_近场_备用',
                '车载语音_Realtime', '远场麦克风阵列_HTTP', '录音笔ASR_WebSocket'):
        assert row in txt, f'mock 数字域行「{row}」缺失'

    # 协议徽章 / 参考基准 / 增益限幅（§4.3 渲染，INT-506 修正格式保留 .0）
    assert 'WebSocket' in txt and 'HTTP' in txt, '协议徽章缺失'
    assert '65 dB / 1.0' in txt, '参考基准「65 dB / 1.0」缺失'
    assert '0.001 ~ 10.0' in txt, '增益限幅「0.001 ~ 10.0」缺失'
    assert '默认' in txt, '默认 Badge 缺失'

    assert '添加 RMS-SPL 映射' in txt, '数字域主按钮缺失'


# ── 3. 行操作菜单 + 弹窗群（详情 / 数字校准） ───
def test_03_row_actions_and_modals(drv):
    _goto_spl(drv)

    # 物理域行菜单（§4.2.1 五项）
    _open_row_menu(drv, '客厅_干声_65dB_1m')
    for item in ('详情', '编辑', '执行校准', '校准历史', '删除'):
        assert any(item in it.text for it in
                   drv.find_elements(By.XPATH, "//*[@role='menuitem']")), \
            f'物理域菜单项「{item}」缺失'
    _click_menu_item(drv, '详情')
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
    txt = _body_text(drv)
    assert '增益映射详情' in txt, '物理域详情弹窗标题缺失'
    assert '校准点数' in txt, '物理域详情弹窗基本信息缺失'
    _press_esc(drv)

    # 数字域行菜单（§4.3.1 五项；默认行菜单项为「清除默认」）
    _switch_tab(drv, 'API/Realtime RMS-SPL')
    _open_row_menu(drv, '客服ASR_WebSocket_默认')
    for item in ('校准', '清除默认', '详情', '编辑', '删除'):
        assert any(item in it.text for it in
                   drv.find_elements(By.XPATH, "//*[@role='menuitem']")), \
            f'数字域菜单项「{item}」缺失'
    _press_esc(drv)

    # 非默认行 → 菜单项「设默认」（§4.3.1）
    _open_row_menu(drv, '客服ASR_近场_备用')
    assert any('设默认' in it.text for it in
               drv.find_elements(By.XPATH, "//*[@role='menuitem']")), \
        '非默认行「设默认」菜单项缺失'
    _press_esc(drv)

    _open_row_menu(drv, '客服ASR_WebSocket_默认')
    _click_menu_item(drv, '校准')
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
    txt = _body_text(drv)
    assert 'RMS-SPL 数字校准' in txt, '数字校准弹窗标题缺失'
    assert '参考声压级' in txt, '参考基准四格缺失'
    assert '目标 SPL' in txt, '校准点集表列头缺失'
    assert '按参考生成' in txt, '按参考生成按钮缺失'
    _press_esc(drv)


# ── 4. 筛选：搜索 + 校准状态 facet + 重置 ───
def test_04_filters(drv):
    _goto_spl(drv)

    # 搜索（§4.1.1 debounce 500ms → 仅剩「客厅」1 条）
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索映射']")
    search.send_keys('客厅')
    time.sleep(1.0)
    txt = _body_text(drv)
    assert '客厅_干声_65dB_1m' in txt and '车内_导航_65dB_0.5m' not in txt, '搜索过滤未生效'
    assert '共 1 条' in txt, '搜索后分页计数未更新'

    # 重置清搜索后，校准状态 facet → 未校准（物理域 3 条）
    drv.find_element(By.XPATH, "//button[contains(., '重置')]").click()
    time.sleep(0.8)
    drv.find_element(By.XPATH, "//button[contains(., '校准状态')]").click()
    time.sleep(0.5)
    drv.find_element(By.XPATH, "//button[contains(., '未校准')]").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    assert '卧室_唤醒_70dB_1m' in txt and '客厅_干声_65dB_1m' not in txt, '校准状态 facet 未生效'
    assert '共 3 条' in txt, '未校准 facet 后分页计数未更新'

    # 重置恢复全量
    drv.find_element(By.XPATH, "//button[contains(., '重置')]").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    assert '客厅_干声_65dB_1m' in txt and '共 8 条' in txt, '重置未恢复全量'


# ── 5. 主题抽屉：打开 → 切深浅色 → 页面正常 ───
def test_05_theme_drawer(drv):
    _goto_spl(drv)
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
    txt = _body_text(drv)
    assert '外观设置' in txt, '主题抽屉未打开'

    # 切深色 → 页面仍渲染 /SPLMapping（Base UI Radio 组，项 aria-label「选择深色」）
    drv.find_element(By.XPATH, "//*[@aria-label='选择深色']").click()
    time.sleep(0.8)
    _press_esc(drv)
    time.sleep(0.5)
    txt = _body_text(drv)
    assert '声压级映射管理' in txt, '深浅色切换后页面渲染异常'


# ── 6. 浏览器 console 无 SEVERE（含主题/深浅色零特判） ───
def test_06_console_no_severe(drv):
    _goto_spl(drv)
    _switch_tab(drv, 'API/Realtime RMS-SPL')
    _drain_console(drv)
    global _CONSOLE_SEVERE
    assert not _CONSOLE_SEVERE, f'浏览器 console SEVERE：\n' + '\n'.join(_CONSOLE_SEVERE[:5])
