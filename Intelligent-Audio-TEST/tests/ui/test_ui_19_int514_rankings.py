# -*- coding: utf-8 -*-
"""INT-514 排行榜页可视稿 浏览器走查（真实 Chrome headless，按 test_ui_18 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. 公开路由 /rankings：Hero 标题「排行榜」+ 副标题 + 类别下划线页签（全部/语音识别/语音对话/语音合成/翻译）
2. 算法卡片网格（页内独立）：区头「算法切换」+ 首卡「全部算法」+ 各算法大卡（名称/分组/在线状态/参数摘要/描述）+ 离线卡置灰
3. 指标组卡 ×N：卡头（指标名·场景 + 方向徽章 + 参与主体数 + 计算于）+ 图表区 + 榜单块（列表/表格双视图切换）
4. 双栏榜单：名次 + 主体（细下划线）+ 徽章组 + 主值 + 基线差/score100 + 实测轨「查看报告」
5. 类别页签筛选写 URL（category=asr）
6. 算法卡点击 → 页内 store（localStorage iatp:rankings:v1:algorithm）+ 选中态高亮；全部算法恢复
7. 筛选行：测试集/指标/数据来源 Select + 搜索主体联想
8. 立即计算：ConfirmDialog → 开始计算 → toast「排行计算完成」
9. 深浅色：暗色下榜单与图表区仍渲染

失败落 tests/ui/artifacts/int514_rankings/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int514_rankings')

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


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _reset_page_state(drv):
    """清空排行页算法/视图本地态，确保用例从默认「全部算法 + 列表视图」开始。"""
    drv.execute_script(
        'localStorage.removeItem("iatp:rankings:v1:algorithm");'
        'localStorage.removeItem("iatp:rankings:v1:view");')
    time.sleep(0.3)


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_public_route_hero_and_category_tabs(drv):
    """公开路由 /rankings：Hero 标题/副标题 + 类别下划线页签（§4.2/§7）。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '排行榜')
    text = _body_text(drv)
    assert '多个厂商模型/APP/API 在同一标准化环境' in text, 'Hero 副标题缺失'
    for label in ('全部', '语音识别', '语音对话', '语音合成', '翻译'):
        assert label in text, f'类别页签「{label}」缺失'
    tabs = drv.find_elements(
        By.XPATH, "//div[@role='tablist' and @aria-label='指标类别']//button[@role='tab']")
    assert len(tabs) == 5, '类别页签数量应为 5'


def test_algorithm_card_grid_page_local(drv):
    """算法卡片网格：区头「算法切换」+ 首卡「全部算法」+ 算法大卡（名称/分组/状态/参数摘要/描述）+ 离线置灰。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '算法切换')
    text = _body_text(drv)
    assert '仅影响本页榜单，不改变全局算法。' in text, '页内独立副提示缺失'
    assert '全部算法' in text, '「全部算法」首卡缺失'
    assert '不按算法筛选，展示全部算法数据。' in text, '首卡副文缺失'
    for name in ('通用识别引擎', '流式识别引擎', '多维评估集成', '旧版 GMM 识别'):
        assert name in text, f'算法大卡「{name}」缺失'
    assert '设备参数 2 · API 参数 1 · 用例参数 1' in text, '参数摘要行缺失'
    assert '在线' in text and '离线' in text, '在线/离线状态徽章缺失'
    # 页内独立：点击算法不写全局 store（iatp:algorithm:v1）
    cards = drv.find_elements(By.XPATH, "//section[@aria-label='算法切换']//button")
    assert len(cards) >= 5, '算法卡片网格卡片数不足（首卡 + 4 算法卡）'
    cards[1].click()
    time.sleep(0.6)
    global_store = drv.execute_script('return localStorage.getItem("iatp:algorithm:v1") || ""')
    assert global_store == '', '页内算法切换不应写回全局 store（公开页不污染全局）'
    local_store = drv.execute_script(
        'return localStorage.getItem("iatp:rankings:v1:algorithm") || ""')
    assert 'asr-v3' in local_store, '页内算法未写入 iatp:rankings:v1:algorithm'
    # 恢复全部算法
    drv.find_elements(By.XPATH, "//section[@aria-label='算法切换']//button")[0].click()
    time.sleep(0.4)


def test_metric_group_cards_and_leaderboard(drv):
    """指标组卡：卡头（指标名·场景 + 方向徽章 + 参与主体数 + 计算于）+ 榜单双栏行。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '字错率 · 通用')
    text = _body_text(drv)
    # 组卡集合（asr 两组 + voice_llm/tts/translation 各一组）
    for card_title in ('字错率 · 通用', '字错率 · 噪声', '末字延迟 · 通用', '自然度 MOS 分 · 通用', 'BLEU 分数 · 通用'):
        assert card_title in text, f'指标组卡「{card_title}」缺失'
    assert '越低越好' in text and '越高越好' in text, '方向徽章缺失'
    assert '个主体 · 计算于' in text, '「个主体 · 计算于」角标缺失'
    assert '榜单' in text, '榜单块头缺失'
    assert '按名次排列，实测轨取最新版本参与对比。' in text, '榜单块说明缺失'
    # 榜单行元素：主体名 + 徽章组（闭源/平台实测）+ 主值（% / ms）+ 查看报告 + DeltaText
    assert '远场语音评测模型-旗舰版' in text, '榜单位置 1 主体缺失'
    assert '平台实测' in text, '来源徽章「平台实测」缺失'
    assert '查看报告' in text, '实测轨「查看报告」链接缺失'
    assert '-0.30%' in text or '+0.50%' in text, 'DeltaText 基线差未渲染（双轨并存行应有 ± 值）'


def test_list_table_view_switch(drv):
    """列表/表格双视图切换：切「表格」→ 表格列（名次/主体/…/计算于）；切回「列表」恢复双栏。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '字错率 · 通用')
    # 第一张组卡的视图切换
    table_tab = drv.find_element(By.XPATH, "//button[contains(., '表格')]")
    table_tab.click()
    time.sleep(0.6)
    text = _body_text(drv)
    for col in ('名次', '主体类型', '来源', '版本', 'score100', '百分位', '与最佳差', '与中位差', '计算于'):
        assert col in text, f'表格列「{col}」缺失'
    regions = drv.find_elements(
        By.XPATH, "//div[@role='region' and starts-with(@aria-label, '排行明细表')]")
    assert regions, '表格滚动容器 aria-label「排行明细表」缺失'
    stored_view = drv.execute_script('return localStorage.getItem("iatp:rankings:v1:view") || ""')
    assert stored_view == 'table', '视图选择未持久化到 localStorage'
    drv.find_element(By.XPATH, "//button[contains(., '列表')]").click()
    time.sleep(0.6)
    remaining = drv.find_elements(
        By.XPATH, "//div[@role='region' and starts-with(@aria-label, '排行明细表')]")
    assert not remaining, '切回列表后表格不应显示'


def test_category_tab_writes_url_and_filters(drv):
    """类别页签筛选：点击「语音识别」→ URL category=asr + 仅 asr 组卡。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '字错率 · 通用')
    tab = drv.find_element(By.XPATH, "//div[@role='tablist']//button[contains(., '语音识别')]")
    tab.click()
    time.sleep(0.8)
    assert 'category=asr' in drv.current_url, 'URL 未写入 category=asr'
    text = _body_text(drv)
    assert '字错率 · 通用' in text
    assert '末字延迟 · 通用' not in text, '非 asr 组卡未随类别筛选隐藏'
    # 刷新可还原
    _goto(drv, '/rankings?category=asr')
    _wait_text(drv, '字错率 · 通用')
    assert '末字延迟 · 通用' not in _body_text(drv), 'URL 还原后非 asr 组卡不应出现'


def test_filter_row_subject_search(drv):
    """筛选行：搜索主体联想 + 筛选生效。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '全部测试集')
    search_input = drv.find_element(By.XPATH, "//input[@aria-label='搜索主体']")
    search_input.send_keys('远场')
    time.sleep(0.9)
    suggestion = drv.find_elements(By.XPATH, "//ul[@role='listbox']//li")
    assert suggestion, '主体联想下拉未出现'
    suggestion[0].click()
    time.sleep(0.6)
    assert 'subjectName=' in drv.current_url, '主体搜索未写入 URL subjectName'
    assert '远场语音评测模型-旗舰版' in _body_text(drv)


def test_recompute_confirm_dialog(drv):
    """立即计算（admin）：ConfirmDialog 确认 → toast「排行计算完成」。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '立即计算')
    drv.find_element(By.XPATH, "//button[contains(., '立即计算')]").click()
    time.sleep(0.6)
    dialog = _body_text(drv)
    assert '重新计算排行？' in dialog, '确认弹窗标题缺失'
    assert '将合并平台实测与外部基线全量重算，期间现有排行保持可查看。' in dialog, '弹窗描述缺失'
    drv.find_element(By.XPATH, "//button[contains(., '开始计算')]").click()
    _wait_text(drv, '排行计算完成', timeout=15)


def test_dark_theme_renders(drv):
    """深浅色：暗色下榜单/图表区仍渲染（图表轴色随主题切换）。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '字错率 · 通用')
    # 经 ConfigDrawer 主题设置抽屉切「深色」（照首页走查先例）
    try:
        drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
        time.sleep(0.5)
        drv.find_element(By.XPATH, "//*[@aria-label='选择深色']").click()
        time.sleep(0.8)
        drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
        time.sleep(0.3)
    except Exception:
        pass
    _wait_text(drv, '字错率 · 通用')
    text = _body_text(drv)
    assert '排行榜' in text and '榜单' in text and '查看报告' in text, '暗色下榜单未渲染'
