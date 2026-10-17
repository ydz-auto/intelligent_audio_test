# -*- coding: utf-8 -*-
"""INT-588 用例编辑模态窗批量操作补全 浏览器走查（真实 Chrome headless，按 test_ui_22/23 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273），
按 11_用例域.md §4 工具栏九件 + 抽屉「自动生成」验收清单逐项断言：

① 工具栏九件齐备（升序/降序/随机排序/标签交错/标签设备/批量设备/设备交叉/批量声压/清空，
   标签设备补齐不再缺失），各工具钮 ghost sm + Tooltip；
② 标签交错：≥2 标签 chip 面板 → 确认后按所选标签分段交错、多标签音频各段各现一次、
   未命中音频追加末尾（排序不改丢数据）；
③ 标签设备：标签→设备映射面板 → 命中标签的音频播放设备被批量设置，未命中不变；
④ 批量设备：设备 Select「{设备名} (通道 {n}) [干声/噪声]」+ 全部/勾选范围 → 应用；
⑤ 设备交叉：多选设备 chips → 按音频列表顺序轮转分配；
⑥ 批量声压：number 40-100 默认 65 + 全部/勾选范围 → 应用；
⑦ 清空：清空当前轮次音频列表 → 空态（既有行为不回归）；
⑧ 抽屉「自动生成」：按标签升序（`-` 连接）真实填入名称框；未填标签提示
   「请先添加标签后再自动生成名称」；编辑态原名不丢；
⑨ 无演示 toast / 无 SEVERE console 报错。

失败落 tests/ui/artifacts/int588_audio_list_batch_ops/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int588_audio_list_batch_ops')

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
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.4)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


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


# ── 定位工具 ────────────────────────────────────────────
def _open_edit_drawer(drv, case_name='智能音箱-调节音量-2人'):
    _goto(drv, '/testcases/by-group')
    edit_btn = drv.find_element(
        By.XPATH,
        f"//*[@aria-label='选择 {case_name}']/ancestor::div[contains(@class,'bg-card')][1]"
        f"//button[@aria-label='编辑用例']",
    )
    edit_btn.click()
    time.sleep(1.0)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    return sheet


def _open_audio_list_step(drv, case_name='智能音箱-调节音量-2人'):
    _open_edit_drawer(drv, case_name)
    tab = drv.find_element(By.XPATH, "//button[@role='tab'][contains(., '音频列表')]")
    tab.click()
    time.sleep(1.0)
    return drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")


def _toolbar(drv):
    """音频列表步骤工具栏（含全部工具钮）。"""
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    # 工具栏是音频列表步骤首个 flex-wrap 容器；以「清空」钮所在工具栏定位
    return sheet.find_element(By.XPATH,
        "//div[contains(@class,'flex')][contains(@class,'flex-wrap')]"
        "[.//button[contains(., '清空')]]")


def _toolbar_buttons(drv):
    return _toolbar(drv).find_elements(By.XPATH, ".//button")


def _audio_card(drv, n):
    """第 n 张音频卡（卡头勾选 checkbox aria-label）。"""
    xpath = f"//*[@aria-label='勾选音频 {n}']/ancestor::div[contains(@class,'ring-1')][1]"
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _file_names(drv, count):
    return [_audio_card(drv, n)
            .find_element(By.XPATH, ".//span[contains(@class,'truncate')]").text
            for n in range(1, count + 1)]


def _card_device(drv, n):
    return _audio_card(drv, n).find_element(By.XPATH, ".//p[starts-with(., '设备：')]").text


def _card_spl(drv, n):
    return _audio_card(drv, n).find_element(By.CSS_SELECTOR, "input[type='number']") \
        .get_attribute('value')


def _card_checked(drv, n):
    """第 n 张音频卡勾选态（base-ui Checkbox 根钮 aria-checked）。"""
    return _audio_card(drv, n).find_element(
        By.XPATH, ".//*[starts-with(@aria-label, '勾选音频')]").get_attribute('aria-checked')


def _console_severe(drv):
    return [e for e in drv.get_log('browser')
            if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', ''))]


def _add_audios(drv, times):
    btn = drv.find_element(By.XPATH, "//button[contains(., '添加音频')]")
    for _ in range(times):
        btn.click()
        time.sleep(0.5)


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _select_option(drv, text):
    """在已打开的 base-ui Select 弹层中点指定项。"""
    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='select-content']")) > 0)
    contents = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content']")
    target = None
    for c in contents:
        items = c.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
        for it in items:
            if text in it.text:
                target = it
                break
        if target is not None:
            break
    assert target is not None, f'Select 项「{text}」缺失'
    target.click()
    time.sleep(0.5)


def _click_scope_radio(drv, dlg, name, label):
    el = dlg.find_element(
        By.XPATH, f"//input[@type='radio'][@name='{name}'][ancestor::label[contains(., '{label}')]]")
    el.click()
    time.sleep(0.4)


def _toast_text(drv):
    time.sleep(0.4)
    toasts = drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]")
    if not toasts:
        return ''
    return '\n'.join(t.text for t in toasts)


# ── ① 工具栏九件齐备 + ghost sm + Tooltip ────────────────
def test_01_toolbar_9_items_ghost_sm_tooltip(drv):
    _login(drv)
    _open_audio_list_step(drv)
    btns = _toolbar_buttons(drv)
    labels = [b.text.strip() for b in btns]
    for expect in ['升序', '降序', '随机排序', '标签交错', '标签设备', '批量设备', '设备交叉', '批量声压', '清空']:
        assert expect in labels, f'工具栏缺「{expect}」：{labels}'
    assert len(btns) == 9, f'工具栏应恰 9 件：{labels}'
    # 各工具钮 ghost sm（cva ghost 变体特征 hover:bg-muted + sm 高 h-7，无 bg-primary 实底）
    for b in btns:
        cls = b.get_attribute('class') or ''
        assert 'hover:bg-muted' in cls and 'bg-primary' not in cls, \
            f'工具钮非 ghost 变体：{b.text} {cls[:120]}'
        assert 'h-7' in cls, f'工具钮非 sm 高：{b.text} {cls[:80]}'
    # 悬停「批量设备」→ Tooltip 出现（base-ui tooltip-content）
    target = [b for b in btns if '批量设备' in b.text][0]
    ActionChains(drv).move_to_element(target).perform()
    WebDriverWait(drv, 5).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='tooltip-content']")) > 0)
    tips = drv.find_elements(By.CSS_SELECTOR, "[data-slot='tooltip-content']")
    assert any('批量设备' in t.text for t in tips), 'Tooltip 内容缺失'
    _save_evidence('01_toolbar_9items', drv)


# ── ② 标签交错：分段交错、多标签各段各现一次 ─────────────
def test_02_tag_interleave(drv):
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)  # 2 初始 + 3 = 5 条：客厅/车内/会议室/音乐背景/英文
    _save_evidence('02a_interleave_before', drv)

    btns = _toolbar_buttons(drv)
    [b for b in btns if '标签交错' in b.text][0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '标签交错')
    assert '至少选择 2 个' in dlg.text, '≥2 标签提示缺失'
    # 未选满 2 个时确定禁用
    ok = dlg.find_element(By.XPATH, ".//button[contains(., '确定')]")
    assert ok.get_attribute('disabled') is not None, '不足 2 标签时确定应禁用'
    # 选「中文」「客厅」
    dlg.find_element(By.XPATH, ".//button[@aria-pressed='false'][contains(., '中文')]").click()
    time.sleep(0.3)
    dlg.find_element(By.XPATH, ".//button[@aria-pressed='false'][contains(., '客厅')]").click()
    time.sleep(0.3)
    assert '已选 2 个标签' in dlg.text, '已选计数缺失'
    _save_evidence('02b_tag_interleave_panel', drv)
    dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)

    names = _file_names(drv, 6)
    assert names == [
        '客厅_中文_命令集.wav',   # 中文段
        '会议室_多人_中文.wav',   # 中文段
        '客厅_中文_命令集.wav',   # 客厅段（多标签音频各段各现一次）
        '车内_导航_1人.wav',      # 未命中追加末尾
        '音乐背景_闹钟.wav',
        '英文_短信指令.flac',
    ], f'标签交错排序不符：{names}'
    t = _toast_text(drv)
    assert '已按标签「中文 / 客厅」交错排序' in t, f'交错 toast 缺失：{t}'
    # P2 修复验收：多标签音频各段各现一次须为独立行——勾选第 1 行，第 3 行（客厅段同一音频）不应联动勾选
    assert _card_checked(drv, 1) == 'false', f'交错后第 1 行初始应未勾选：{_card_checked(drv, 1)}'
    _audio_card(drv, 1).find_element(By.XPATH, ".//*[starts-with(@aria-label, '勾选音频')]").click()
    time.sleep(0.4)
    assert _card_checked(drv, 1) == 'true', '第 1 行勾选后应为已勾选'
    assert _card_checked(drv, 3) == 'false', \
        f'P2 状态耦合：勾选第 1 行不应联动第 3 行（同一音频不同段应独立）：{_card_checked(drv, 3)}'
    # 独立编辑：改第 1 行声压，第 3 行不变
    _audio_card(drv, 1).find_element(By.CSS_SELECTOR, "input[type='number']").clear()
    _audio_card(drv, 1).find_element(By.CSS_SELECTOR, "input[type='number']").send_keys('90')
    time.sleep(0.4)
    assert _card_spl(drv, 1) == '90', '第 1 行声压应更新为 90'
    assert _card_spl(drv, 3) == '65', f'P2 状态耦合：第 1 行声压更新不应联动第 3 行：{_card_spl(drv, 3)}'
    # 标签交错确认渲染后控制台零 SEVERE（审计清单第 3 条；test_10 面板开/关路径不覆盖此路径）
    assert not _console_severe(drv), f'标签交错确认后 console SEVERE：{_console_severe(drv)[:5]}'
    _save_evidence('02c_tag_interleave_result', drv)


# ── ③ 标签设备：标签→设备映射，命中音频批量设置 ──────────
def test_03_tag_device_mapping(drv):
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)
    btns = _toolbar_buttons(drv)
    [b for b in btns if '标签设备' in b.text][0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '标签设备')
    assert '选择标签与目标播放设备' in dlg.text, '标签设备面板说明缺失'
    assert dlg.find_element(By.XPATH, ".//button[contains(., '确定')]") \
        .get_attribute('disabled') is not None, '未选标签/设备时确定应禁用'
    # 标签 → 中文；目标设备 → 音频接口 B (通道 2) [噪声]
    dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']").click()
    time.sleep(0.4)
    _select_option(drv, '中文')
    dlg = _dialog_by_title(drv, '标签设备')
    triggers = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    triggers[1].click()
    time.sleep(0.4)
    _select_option(drv, '音频接口 B (通道 2) [噪声]')
    _save_evidence('03a_tag_device_panel', drv)
    dlg = _dialog_by_title(drv, '标签设备')
    dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)
    # 命中「中文」：第1（客厅_中文_命令集）、第3（会议室_多人_中文）→ 音频接口 B；其余不变
    assert '音频接口 B (通道 2) [噪声]' in _card_device(drv, 1), _card_device(drv, 1)
    assert '音频接口 B (通道 2) [噪声]' in _card_device(drv, 3), _card_device(drv, 3)
    for n in (2, 4, 5):
        assert '音频接口 A (通道 1) [干声]' in _card_device(drv, n), f'第{n}条不应被改：{_card_device(drv, n)}'
    _save_evidence('03b_tag_device_result', drv)


# ── ④ 批量设备：全部范围 ────────────────────────────────
def test_04_batch_device_all_scope(drv):
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)
    btns = _toolbar_buttons(drv)
    [b for b in btns if '批量设备' in b.text][0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    assert '播放设备' in dlg.text and '全部音频' in dlg.text, '批量设备面板字段缺失'
    dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']").click()
    time.sleep(0.4)
    _select_option(drv, '蓝牙音箱 (通道 3) [干声]')
    _save_evidence('04a_batch_device_panel', drv)
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)
    for n in range(1, 6):
        assert '蓝牙音箱 (通道 3) [干声]' in _card_device(drv, n), f'第{n}条设备未更新：{_card_device(drv, n)}'
    t = _toast_text(drv)
    assert '已为全部音频批量设置播放设备' in t, f'批量设备 toast 缺失：{t}'
    _save_evidence('04b_batch_device_result', drv)


# ── ⑤ 批量设备：勾选范围 ────────────────────────────────
def test_05_batch_device_selected_scope(drv):
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)
    # 勾选第 1 张音频
    drv.find_element(By.XPATH, "//*[@aria-label='勾选音频 1']").click()
    time.sleep(0.5)
    btns = _toolbar_buttons(drv)
    [b for b in btns if '批量设备' in b.text][0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    assert '勾选音频（1 个）' in dlg.text, '勾选计数缺失'
    dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']").click()
    time.sleep(0.4)
    _select_option(drv, '音频接口 B (通道 2) [噪声]')
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    _click_scope_radio(drv, dlg, 'batch-device-scope', '勾选音频')
    _save_evidence('05a_batch_device_selected_panel', drv)
    dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)
    assert '音频接口 B (通道 2) [噪声]' in _card_device(drv, 1), _card_device(drv, 1)
    for n in (2, 3, 4, 5):
        assert '音频接口 A (通道 1) [干声]' in _card_device(drv, n), f'第{n}条不应被改：{_card_device(drv, n)}'
    _save_evidence('05b_batch_device_selected_result', drv)


# ── ⑥ 设备交叉：多选设备按序轮转 ────────────────────────
def test_06_cross_device_round_robin(drv):
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)
    btns = _toolbar_buttons(drv)
    [b for b in btns if '设备交叉' in b.text][0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '设备交叉')
    assert '按当前音频列表顺序轮转分配' in dlg.text, '设备交叉说明缺失'
    assert dlg.find_element(By.XPATH, ".//button[contains(., '确定')]") \
        .get_attribute('disabled') is not None, '未选设备时确定应禁用'
    dlg.find_element(By.XPATH, ".//button[@aria-pressed='false'][contains(., '音频接口 A (通道 1) [干声]')]").click()
    time.sleep(0.3)
    dlg.find_element(By.XPATH, ".//button[@aria-pressed='false'][contains(., '音频接口 B (通道 2) [噪声]')]").click()
    time.sleep(0.3)
    assert '已选 2 个设备' in dlg.text, '设备已选计数缺失'
    _save_evidence('06a_cross_device_panel', drv)
    dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)
    expect = ['音频接口 A (通道 1) [干声]', '音频接口 B (通道 2) [噪声]']
    for n in range(1, 6):
        want = expect[(n - 1) % 2]
        assert want in _card_device(drv, n), f'第{n}条轮转应为 {want}：{_card_device(drv, n)}'
    t = _toast_text(drv)
    assert '已按列表顺序轮转分配 2 个设备' in t, f'设备交叉 toast 缺失：{t}'
    _save_evidence('06b_cross_device_result', drv)


# ── ⑦ 批量声压：40-100 默认 65 + 全部/勾选 ───────────────
def test_07_batch_spl_all_and_selected(drv):
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)
    # 默认 65 断言（先看卡片初始值）
    assert _card_spl(drv, 1) == '65', f'初始声压应为 65：{_card_spl(drv, 1)}'
    btns = _toolbar_buttons(drv)
    [b for b in btns if '批量声压' in b.text][0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量设置声压级')
    spl = dlg.find_element(By.CSS_SELECTOR, "input[type='number']")
    assert spl.get_attribute('value') == '65', f'默认应为 65：{spl.get_attribute("value")}'
    assert spl.get_attribute('min') == '40' and spl.get_attribute('max') == '100', \
        '批量声压 40-100 约束缺失'
    assert '范围 40-100，默认 65' in dlg.text, '范围说明缺失'
    # P3 修复验收：越界/空输入时「确定」禁用，合法时可用（与其它面板一致）
    ok_btn = dlg.find_element(By.XPATH, ".//button[contains(., '确定')]")
    assert ok_btn.get_attribute('disabled') is None, '默认 65 时确定应可用'
    # 空输入：真实用户式全选+退格（Selenium clear() 不触发 React onChange，不能代表真实清空）
    spl.send_keys(Keys.CONTROL, 'a')
    spl.send_keys(Keys.BACK_SPACE)
    time.sleep(0.3)
    assert dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").get_attribute('disabled') is not None, \
        '空输入时确定应禁用（P3）'
    # 越界 120
    spl.send_keys(Keys.CONTROL, 'a')
    spl.send_keys('120')
    time.sleep(0.3)
    assert dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").get_attribute('disabled') is not None, \
        '越界 120 时确定应禁用（P3）'
    # 合法 80
    spl.send_keys(Keys.CONTROL, 'a')
    spl.send_keys('80')
    time.sleep(0.3)
    assert dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").get_attribute('disabled') is None, \
        '输入 80 时确定应可用'
    _save_evidence('07a_batch_spl_panel', drv)
    dlg = _dialog_by_title(drv, '批量设置声压级')
    dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)
    for n in range(1, 6):
        assert _card_spl(drv, n) == '80', f'第{n}条声压应为 80：{_card_spl(drv, n)}'
    t = _toast_text(drv)
    assert '已为全部音频批量设置声压 80 dB' in t, f'批量声压 toast 缺失：{t}'
    _save_evidence('07b_batch_spl_result', drv)

    # 勾选范围：勾选第 2 张，批量声压 85 → 仅第 2 张变
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)
    drv.find_element(By.XPATH, "//*[@aria-label='勾选音频 2']").click()
    time.sleep(0.5)
    btns = _toolbar_buttons(drv)
    [b for b in btns if '批量声压' in b.text][0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量设置声压级')
    spl = dlg.find_element(By.CSS_SELECTOR, "input[type='number']")
    spl.clear()
    spl.send_keys('85')
    _click_scope_radio(drv, dlg, 'batch-spl-scope', '勾选音频')
    _save_evidence('07c_batch_spl_selected_panel', drv)
    dlg = _dialog_by_title(drv, '批量设置声压级')
    dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)
    assert _card_spl(drv, 2) == '85', f'第2条应 85：{_card_spl(drv, 2)}'
    for n in (1, 3, 4, 5):
        assert _card_spl(drv, n) == '65', f'第{n}条不应被改：{_card_spl(drv, n)}'
    _save_evidence('07d_batch_spl_selected_result', drv)


# ── ⑧ 清空 → 空态（既有行为不回归） ─────────────────────
def test_08_clear_audio_list(drv):
    _login(drv)
    _open_audio_list_step(drv)
    _add_audios(drv, 3)
    btns = _toolbar_buttons(drv)
    [b for b in btns if '清空' in b.text][0].click()
    time.sleep(0.8)
    body = _body_text(drv)
    assert '尚未添加音频' in body, f'清空后应空态：{body[-200:]}'
    assert drv.find_elements(By.XPATH, "//*[contains(@aria-label, '勾选音频 ')]") == [], \
        '清空后不应残留音频卡'
    _save_evidence('08_clear_empty', drv)


# ── ⑨ 抽屉「自动生成」真实填入名称框 ─────────────────────
def test_09_auto_generate_name(drv):
    _login(drv)
    sheet = _open_edit_drawer(drv, '智能音箱-调节音量-2人')
    name_input = sheet.find_element(By.ID, 'case-name')
    # 编辑态原名不丢
    assert name_input.get_attribute('value') == '智能音箱-调节音量-2人', \
        f'编辑态原名应保留：{name_input.get_attribute("value")}'
    _save_evidence('09a_auto_generate_before', drv)
    # 读当前标签，用与实现相同的 zh-CN localeCompare 计算期望名
    tags = _tags_in_drawer(drv)
    assert len(tags) >= 2, f'mock 用例应有标签：{tags}'
    expected = drv.execute_script(
        'return arguments[0].slice().sort((a, b) => a.localeCompare(b, "zh-CN")).join("-")',
        tags,
    )
    sheet.find_element(By.XPATH, "//button[contains(., '自动生成')]").click()
    time.sleep(0.8)
    val = name_input.get_attribute('value')
    assert val == expected, f'自动生成名称应为「{expected}」：{val}'
    t = _toast_text(drv)
    assert '已按标签升序自动生成名称' in t, f'自动生成 toast 缺失：{t}'
    _save_evidence('09b_auto_generate_filled', drv)

    # 未填标签 → 提示「请先添加标签后再自动生成名称」
    for tag in tags:
        rm = sheet.find_elements(By.XPATH, f"//button[@aria-label='移除标签 {tag}']")
        if rm:
            rm[0].click()
            time.sleep(0.2)
    assert _tags_in_drawer(drv) == [], '标签应已全部移除'
    sheet.find_element(By.XPATH, "//button[contains(., '自动生成')]").click()
    time.sleep(0.6)
    t = _toast_text(drv)
    assert '请先添加标签后再自动生成名称' in t, f'空标签提示缺失：{t}'
    assert name_input.get_attribute('value') == expected, '空标签时名称不应改变'
    _save_evidence('09c_auto_generate_empty_tags', drv)


def _tags_in_drawer(drv):
    """当前用例标签名：从 TagInput 移除钮 aria-label（移除标签 {name}）精确提取。"""
    rms = drv.find_elements(By.XPATH, "//button[starts-with(@aria-label, '移除标签 ')]")
    return [rm.get_attribute('aria-label')[len('移除标签 '):] for rm in rms]


# ── ⑩ 无演示 toast + 无 SEVERE console 报错 ──────────────
def test_10_no_demo_toast_and_no_console_errors(drv):
    _login(drv)
    _open_audio_list_step(drv)
    btns = _toolbar_buttons(drv)
    # 五个批量工具逐一打开：面板应真实弹出，不落演示 toast
    for label, title in [
        ('标签交错', '标签交错'),
        ('标签设备', '标签设备'),
        ('批量设备', '批量设置播放设备'),
        ('设备交叉', '设备交叉'),
        ('批量声压', '批量设置声压级'),
    ]:
        [b for b in btns if label in b.text][0].click()
        time.sleep(0.8)
        assert _dialog_by_title(drv, title) is not None, f'「{label}」未弹出面板'
        assert '演示' not in _body_text(drv), '不应出现演示 toast 文案'
        # 关闭面板
        _dialog_by_title(drv, title).find_element(
            By.XPATH, ".//button[contains(., '取消')]").click()
        time.sleep(0.5)
    # 页面无抛错级 console
    errors = [e for e in drv.get_log('browser')
              if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', ''))]
    assert not errors, f'页面 console SEVERE 报错：{errors[:5]}'
    _save_evidence('10_no_demo_toast_final', drv)
