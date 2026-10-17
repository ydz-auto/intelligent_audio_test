# -*- coding: utf-8 -*-
"""INT-584 用例编辑抽屉两常驻节 + 分组/标签子视图双向切换 浏览器走查（真实 Chrome headless）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273），
按 11_用例域.md（INT-579 审计通过版）验收清单逐项断言：
① 用例编辑抽屉两常驻节（§5.1.1 全局背景噪声 / §5.1.2 整体评估维度）字段/文案/mock 形态；
   轮次「评估维度」步骤权重/阈值 0-100、LLM 模型+Prompt Select、无「最大 Token/Temperature」、
   「启用本轮评估」Checkbox。
② 分组视图组头右区「平铺|按标签」Tabs 胶囊、默认平铺；切「按标签」客户端聚合 + 「未设置标签」桶末尾弱化。
③ 标签视图标签卡头「平铺|按用例分组」、默认平铺；切「按用例分组」按分组聚合 + 「未分组」桶末尾弱化。
④ 切换状态 per-card 会话内存保留（同会话内切页签不丢、刷新回平铺）、空态文案与选中态保持。
⑤ 子分组头只读（§3.9 零操作入口），与既有入口（CaseGroupActions / 行内五钮 / 批量浮条）不冲突。

失败落 tests/ui/artifacts/int584_subview_editors/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int584_subview_editors')

# 5273 = 本工作区常驻 dev server；env 可覆写
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver(width=1680):
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument(f'--window-size={width},1050')
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


@pytest.fixture(scope='session')
def mdrv():
    """移动端（≤640px）专用浏览器会话：§3.5/§3.6 移动端「显示方式」收编验证。"""
    global _DRIVER
    _DRIVER = _driver(width=480)
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
    """INT-606 接线后 mock 表单登录不可用（登录页走真实后端 /api/v1/auth，未起时无登录态）。
    改为 localStorage 注入会话（iatp:auth:v1 + token，权限 '*'），test_ui_23/29 同口径。"""
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    snapshot = {
        'state': {
            'user': {
                'id': 'mock-admin-001',
                'username': username,
                'displayName': '演示管理员',
                'roleName': '超级管理员',
                'permissions': ['*'],
            }
        },
        'version': 0,
    }
    drv.execute_script(
        "window.localStorage.setItem('iatp:auth:v1', arguments[0])",
        json.dumps(snapshot, ensure_ascii=False))
    _goto(drv, '/testcases/by-group')
    time.sleep(0.6)


# ── 定位工具 ────────────────────────────────────────────
def _card(drv, checkbox_aria_label):
    """通过卡头 checkbox aria-label 定位整卡（分组卡/标签卡/未分组卡）外层 bg-card。"""
    xpath = (
        f"//*[@aria-label='{checkbox_aria_label}']"
        f"/ancestor::div[contains(@class,'bg-card')][1]"
    )
    WebDriverWait(drv, 12).until(
        lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _group_card(drv, group_name):
    return _card(drv, f'全选分组 {group_name}')


def _tag_card(drv, tag_name):
    return _card(drv, f'全选标签 {tag_name}')


def _sub_tab(card, label):
    """卡内子视图切换 Tabs 的指定 trigger（平铺/按标签/按用例分组）。"""
    return card.find_element(
        By.XPATH, f".//button[@role='tab'][contains(., '{label}')]")


def _is_active(tab):
    return tab.get_attribute('data-active') is not None


def _click_tab(tab):
    tab.click()
    time.sleep(0.9)


def _open_edit_drawer(drv, case_name):
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


# ── ① 用例编辑抽屉两常驻节字段/文案/mock 形态 ─────────────
def test_01_edit_drawer_two_persistent_sections(drv):
    _login(drv)
    # 编辑 rounds=1 的用例（tc-002），两常驻节不随轮次数隐藏（INT-579 §10 #7）
    sheet = _open_edit_drawer(drv, '智能音箱-调节音量-2人')
    w = sheet.size['width']
    assert w >= 1200, f'抽屉宽度不足 1280：{w}'
    txt = sheet.text
    # 两常驻节标题
    assert '全局背景噪声' in txt, f'全局背景噪声节缺失：{txt[:200]}'
    assert '整体评估维度' in txt, f'整体评估维度节缺失：{txt[:200]}'

    # §5.1.1 全局背景噪声：节头 + 说明 + 噪声音频卡 + 声压级 + 循环 + 设备 + 警示 chip
    assert '配置后跨所有轮次持续播放，优先于轮次级噪声' in txt, '全局噪声节说明缺失'
    assert '粉红噪声_94dB.wav' in txt, 'mock 噪声音频缺失'
    assert '3m' in txt, '噪声音频时长徽章（180s→3m）缺失'
    assert '粉红噪声' in txt, '噪声音频标签 chips 缺失'
    assert '更换' in txt and '试听' in txt, '更换/试听按钮缺失'
    # 声压级 number 0-120 step 1 默认 60
    spl = sheet.find_element(
        By.XPATH, ".//*[contains(@class,'text-sm')][contains(., '声压级 (dB)')]/following-sibling::input")
    assert spl.get_attribute('value') == '60', f'声压级默认应为 60：{spl.get_attribute("value")}'
    assert spl.get_attribute('min') == '0' and spl.get_attribute('max') == '120' \
        and spl.get_attribute('step') == '1', '声压级 min0/max120/step1 缺失'
    # 循环播放 Switch 默认开
    loop_sw = sheet.find_element(By.XPATH, ".//*[@role='switch'][@aria-label='循环播放']")
    assert loop_sw.get_attribute('aria-checked') == 'true', '循环播放默认应开启'
    # 播放设备 chips 多选（dev-1/dev-3 已选）
    for dev in ['音频接口 A (通道 1)', '功放 左声道 (通道 1)']:
        chip = sheet.find_element(By.XPATH, f".//button[@aria-pressed='true'][contains(., '{dev}')]")
        assert chip is not None, f'播放设备 chip「{dev}」应处于选中态'
    # 未匹配播放设备警示 chip（⚠️ 实施注意① 统一文案）
    warn = sheet.find_element(By.XPATH, ".//*[contains(., '未匹配到播放设备ID：旧喇叭组')]")
    assert warn is not None, '未匹配播放设备警示 chip 缺失'
    # 数据契约注释文案落位
    assert '播放设备（可多选）' in txt, '播放设备标签缺失'

    # §5.1.2 整体评估维度：节头 + 徽章 + 副标题 + 启用开关 + 维度多选 + 已选参数卡
    overall = sheet.find_element(By.XPATH, ".//section[.//*[contains(., '整体评估维度')]]")
    otxt = overall.text
    assert '所有轮次' in otxt, '「所有轮次」徽章缺失'
    assert 'config.dimensions' in otxt, '副标题 config.dimensions 缺失'
    assert '启用整体评估' in otxt, '启用整体评估开关缺失'
    assert '搜索评估维度' in otxt or overall.find_elements(
        By.XPATH, ".//input[@aria-label='搜索评估维度']"), '搜索框缺失'
    assert '已选 2 项' in otxt, '已选计数缺失'
    enabled_sw = overall.find_element(By.XPATH, ".//*[@role='switch'][@aria-label='启用整体评估']")
    assert enabled_sw.get_attribute('aria-checked') == 'true', '启用整体评估默认应开启'
    # 已选参数卡：识别准确率/字准率 权重 50 + 阈值 80（0-100 默认）
    o_vals = [i.get_attribute('value') for i in overall.find_elements(By.TAG_NAME, 'input')]
    assert o_vals.count('50') >= 2, f'整体评估参数卡权重 50 缺失：{o_vals}'
    assert o_vals.count('80') >= 2, f'整体评估参数卡阈值 80 缺失：{o_vals}'
    _save_evidence('01_edit_drawer_two_sections', drv)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)


# ── ① 轮次「评估维度」步骤新字段 ─────────────────────────
def test_02_eval_step_weight_threshold_llm_select(drv):
    _login(drv)
    sheet = _open_edit_drawer(drv, '智能音箱-调节音量-2人')
    # 切到「评估维度」步骤
    step_tab = sheet.find_element(By.XPATH, ".//button[@role='tab'][contains(., '评估维度')]")
    step_tab.click()
    time.sleep(0.7)
    txt = sheet.text
    # 权重/阈值 0-100 number（标签「权重」/「阈值」，§5.1 修正）
    assert '权重' in txt and '阈值' in txt, f'评估维度步骤权重/阈值缺失：{txt[:200]}'
    wt = sheet.find_element(
        By.XPATH, ".//*[contains(@class,'text-sm')][contains(., '权重')]/following-sibling::input")
    assert wt.get_attribute('min') == '0' and wt.get_attribute('max') == '100', '权重 0-100 约束缺失'
    # 「启用本轮评估」Checkbox（首轮默认开）
    enabled = sheet.find_element(By.XPATH, ".//*[@aria-label='启用本轮评估']")
    assert enabled.get_attribute('aria-checked') == 'true', '首轮「启用本轮评估」默认应勾选'
    # 点「语义理解」主维度 → LLM Judge 参数卡（模型 Select + Prompt 模板 Select；无 最大 Token/Temperature）
    chip = sheet.find_element(By.XPATH, ".//button[contains(., '语义理解')]")
    chip.click()
    time.sleep(0.7)
    txt = sheet.text
    assert 'LLM Judge' in txt, 'LLM Judge 徽章缺失'
    assert '模型' in txt and 'Prompt 模板' in txt, f'LLM 模型/Prompt Select 缺失：{txt[-300:]}'
    for banned in ['最大 Token', 'Temperature']:
        assert banned not in txt, f'「{banned}」应按 §5.1 移除（属维度定义 §5.5）'
    _save_evidence('02_eval_step_llm_select', drv)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)


# ── ② 分组视图：切换控件位置/默认平铺/按标签聚合/未设置标签桶 ──
def test_03_group_view_subview_switch(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    # g1 组头右区：切换控件存在且默认平铺
    g1 = _group_card(drv, '智能音箱功能测试')
    flat = _sub_tab(g1, '平铺')
    by_tag = _sub_tab(g1, '按标签')
    assert _is_active(flat), '分组卡子视图默认应为「平铺」'
    assert not _is_active(by_tag), '分组卡子视图「按标签」默认不应选中'
    # 默认平铺：组内用例卡直接渲染
    txt = _body_text(drv)
    assert '智能音箱-播放音乐-中文-客厅' in txt, '默认平铺组内用例卡缺失'
    # 切「按标签」→ 客户端聚合，标签子分组头（色点/名称/分类角标/计数/总时长）
    _click_tab(by_tag)
    g1 = _group_card(drv, '智能音箱功能测试')
    assert _is_active(_sub_tab(g1, '按标签')), '切「按标签」后选中态未保持'
    # 子分组头：音箱 5 条 设备类型 / 中文 3 条 语种
    sub_headers = g1.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    assert sub_headers, '按标签子分组头缺失'
    for name, cat, cnt in [('音箱', '设备类型', '5 条'), ('中文', '语种', '3 条')]:
        hits = [h for h in sub_headers if h.text.find(name) >= 0]
        assert hits, f'标签子分组「{name}」缺失'
        htxt = hits[0].text
        assert cat in htxt, f'子分组「{name}」分类角标「{cat}」缺失：{htxt}'
        assert cnt in htxt, f'子分组「{name}」计数「{cnt}」缺失：{htxt}'
    assert '总时长' in sub_headers[0].text, '子分组总时长徽章缺失'
    # 未分组虚拟组（tc-014 无标签/tc-015 1人/tc-016 中文+会议室）→ 按标签：「未设置标签」桶末尾弱化
    un = _card(drv, '全选未分组用例')
    _click_tab(_sub_tab(un, '按标签'))
    un = _card(drv, '全选未分组用例')
    un_headers = un.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    labels = [h.text.split('\n')[0] for h in un_headers]
    assert '未设置标签' in labels, f'「未设置标签」桶缺失：{labels}'
    assert labels[-1] == '未设置标签', f'「未设置标签」应置于末尾：{labels}'
    assert 'bg-muted' in un_headers[-1].get_attribute('class'), '「未设置标签」桶应弱化（muted）'
    _save_evidence('03_group_subview_by_tag', drv)


# ── ④ 分组视图：per-card 会话内存（切页签不丢、刷新回平铺）──
def test_04_group_subview_session_memory(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    g1 = _group_card(drv, '智能音箱功能测试')
    _click_tab(_sub_tab(g1, '按标签'))
    assert _is_active(_sub_tab(_group_card(drv, '智能音箱功能测试'), '按标签'))
    # 顶视图页签「按标签」（DOM 序首个）→ 客户端导航到 by-tag（会话 store 不重置）
    top_tag = drv.find_element(By.XPATH, "//button[@role='tab'][contains(., '按标签')][1]")
    _click_tab(top_tag)
    assert '/testcases/by-tag' in drv.current_url, f'顶视图页签未切到 by-tag：{drv.current_url}'
    # 切回「按分组」→ g1 仍按标签（per-card 会话内存保留）
    top_group = drv.find_element(By.XPATH, "//button[@role='tab'][contains(., '按分组')][1]")
    _click_tab(top_group)
    assert '/testcases/by-group' in drv.current_url
    assert _is_active(_sub_tab(_group_card(drv, '智能音箱功能测试'), '按标签')), \
        '切页签后 per-card 切换状态应保留'
    # 刷新 → 会话 store 清空 → 回默认平铺
    drv.refresh()
    time.sleep(1.6)
    g1 = _group_card(drv, '智能音箱功能测试')
    assert _is_active(_sub_tab(g1, '平铺')), '刷新后应回默认平铺'
    _save_evidence('04_group_subview_session_memory', drv)


# ── ③ 标签视图：切换控件位置/默认平铺/按用例分组聚合/未分组桶 ──
def test_05_tag_view_subview_switch(drv):
    _login(drv)
    _goto(drv, '/testcases/by-tag')
    # 音箱标签卡：默认平铺
    spk = _tag_card(drv, '音箱')
    assert _is_active(_sub_tab(spk, '平铺')), '标签卡子视图默认应为「平铺」'
    # 音乐卡（tc-001/tc-005 g1 + tc-007 g2）→ 按用例分组：智能音箱功能测试 2 条 + 车载语音交互 1 条
    music = _tag_card(drv, '音乐')
    _click_tab(_sub_tab(music, '按用例分组'))
    music = _tag_card(drv, '音乐')
    m_headers = music.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    m_labels = [h.text.split('\n')[0] for h in m_headers]
    assert '智能音箱功能测试' in m_labels, f'音乐卡按分组子组缺失：{m_labels}'
    assert '车载语音交互' in m_labels, f'音乐卡按分组子组缺失：{m_labels}'
    g1_hdr = next(h for h in m_headers if h.text.split('\n')[0] == '智能音箱功能测试')
    assert '2 条' in g1_hdr.text, f'智能音箱功能测试子组计数应为 2 条：{[h.text for h in m_headers]}'
    # 1人卡（tc-004/tc-006/tc-009 分组 + tc-015 未分组）→ 「未分组」桶末尾弱化
    one = _tag_card(drv, '1人')
    _click_tab(_sub_tab(one, '按用例分组'))
    one = _tag_card(drv, '1人')
    o_headers = one.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    o_labels = [h.text.split('\n')[0] for h in o_headers]
    assert '未分组' in o_labels, f'「未分组」桶缺失：{o_labels}'
    assert o_labels[-1] == '未分组', f'「未分组」应置于末尾：{o_labels}'
    assert 'bg-muted' in o_headers[-1].get_attribute('class'), '「未分组」桶应弱化（muted）'
    _save_evidence('05_tag_subview_by_group', drv)


# ── ⑤ 子分组头只读 + 与既有入口不冲突 ────────────────────
def test_06_sub_group_header_readonly_no_conflict(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    g1 = _group_card(drv, '智能音箱功能测试')
    _click_tab(_sub_tab(g1, '按标签'))
    g1 = _group_card(drv, '智能音箱功能测试')
    # 子分组头只读：无任何操作按钮（组织行非实体行，§3.9 零操作入口）
    sub_headers = g1.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    assert sub_headers
    for h in sub_headers:
        btns = h.find_elements(By.TAG_NAME, 'button')
        assert not btns, f'子分组头不应有任何操作按钮：{h.text} / {len(btns)}'
    # 既有入口不冲突：组头 CaseGroupActions 仍存在
    gh_txt = g1.text
    for btn in ['编辑', '删除', '新增用例', '复制', '批量修改']:
        assert btn in gh_txt, f'组头既有操作「{btn}」缺失'
    # 行内五钮仍在用例卡
    cards = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']")
    assert cards, '行内「编辑用例」按钮缺失'
    assert drv.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']"), '行内「预览音频」缺失'
    assert drv.find_elements(By.CSS_SELECTOR, "button[aria-label='复制用例']"), '行内「复制用例」缺失'
    assert drv.find_elements(By.CSS_SELECTOR, "button[aria-label='删除用例']"), '行内「删除用例」缺失'
    # 批量浮条：勾选一用例后出现「批量修改」
    drv.find_element(By.XPATH, "//*[@aria-label='选择 智能音箱-播放音乐-中文-客厅']").click()
    time.sleep(0.7)
    txt = _body_text(drv)
    assert '批量修改' in txt, '勾选用例后批量浮条「批量修改」缺失'
    _save_evidence('06_subgroup_header_readonly', drv)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)


# ── ⑥ 移动端（≤640px）「显示方式」收编（INT-584 审计返修 P3-1）──────
def _open_group_display_submenu(mdrv, group_name):
    """移动端分组卡：CaseGroupActions「批量修改」下拉 → 首项「显示方式」子菜单。"""
    card = _group_card(mdrv, group_name)
    bm = card.find_element(By.XPATH, ".//button[contains(@aria-label,'批量修改')]")
    bm.click()
    time.sleep(0.8)
    # 子菜单触发器「显示方式」
    sub = None
    for el in mdrv.find_elements(By.XPATH, "//*[contains(., '显示方式')]"):
        if el.is_displayed() and (el.text or '').strip() == '显示方式':
            sub = el
            break
    assert sub is not None, '移动端批量修改下拉首项「显示方式」子菜单缺失'
    sub.click()
    time.sleep(0.7)
    return card


def _menu_item(mdrv, label):
    """下拉菜单中指定 label 的 menuitem（当前值带 ✓）。"""
    for el in mdrv.find_elements(By.XPATH, "//*[@role='menuitem']"):
        if (el.text or '').strip().split('\n')[0] == label:
            return el
    return None


def test_07_mobile_group_card_subview_in_casegroup_actions(mdrv):
    """移动端（480px）分组卡：Tabs 不渲染；子视图切换收进 CaseGroupActions 下拉首项「显示方式」；
    选「按标签」后客户端聚合生效、选中态 ✓ 保留。"""
    _login(mdrv)
    _goto(mdrv, '/testcases/by-group')
    g1 = _group_card(mdrv, '智能音箱功能测试')
    # 移动端不渲染 Tabs（role=tab 的 平铺/按标签 胶囊不应存在）
    tabs = g1.find_elements(By.XPATH, ".//button[@role='tab']")
    assert not tabs, f'移动端分组卡不应渲染 Tabs 胶囊：{len(tabs)}'
    # 打开 批量修改 → 显示方式 子菜单（首项），默认平铺 ✓
    _open_group_display_submenu(mdrv, '智能音箱功能测试')
    flat_item = _menu_item(mdrv, '平铺')
    assert flat_item is not None, '显示方式子菜单「平铺」缺失'
    assert '✓' in (flat_item.text or ''), '移动端子菜单默认应选中「平铺」'
    # 选「按标签」→ 客户端聚合生效（音箱 5 条 设备类型 / 中文 3 条 语种 子分组头出现）
    tag_item = _menu_item(mdrv, '按标签')
    assert tag_item is not None, '显示方式子菜单「按标签」缺失'
    tag_item.click()
    time.sleep(1.0)
    g1 = _group_card(mdrv, '智能音箱功能测试')
    subs = g1.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    assert subs, '移动端选「按标签」后子分组头缺失'
    labels = [s.text.split('\n')[0] for s in subs]
    assert '音箱' in labels and '中文' in labels, f'移动端按标签聚合子分组缺失：{labels}'
    # 选中态 ✓ 保留：再开下拉，按标签带 ✓
    _open_group_display_submenu(mdrv, '智能音箱功能测试')
    by_tag = _menu_item(mdrv, '按标签')
    assert by_tag is not None and '✓' in (by_tag.text or ''), '移动端选「按标签」后选中态 ✓ 未保留'
    _save_evidence('07_mobile_group_subview_in_casegroup_actions', mdrv)
    mdrv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)


def test_08_mobile_tag_card_subview_dropdown(mdrv):
    """移动端（480px）标签卡：子视图切换收进 SubViewDisplayMenu「显示方式」下拉；
    选「按用例分组」后客户端聚合生效、选中态 ✓ 保留。"""
    _login(mdrv)
    _goto(mdrv, '/testcases/by-tag')
    spk = _tag_card(mdrv, '音箱')
    # 标签卡移动端：独立「显示方式」下拉（SubViewDisplayMenu）
    dm = spk.find_element(By.XPATH, ".//button[@aria-label='显示方式']")
    assert dm.is_displayed(), '移动端标签卡「显示方式」下拉缺失'
    dm.click()
    time.sleep(0.7)
    flat_item = _menu_item(mdrv, '平铺')
    assert flat_item is not None and '✓' in (flat_item.text or ''), '标签卡下拉默认应选中「平铺」'
    by_group = _menu_item(mdrv, '按用例分组')
    assert by_group is not None, '标签卡下拉「按用例分组」缺失'
    by_group.click()
    time.sleep(1.0)
    spk = _tag_card(mdrv, '音箱')
    subs = spk.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    assert subs, '移动端标签卡选「按用例分组」后子分组头缺失'
    labels = [s.text.split('\n')[0] for s in subs]
    assert '智能音箱功能测试' in labels, f'移动端按用例分组聚合缺失：{labels}'
    # 选中态 ✓ 保留
    dm = spk.find_element(By.XPATH, ".//button[@aria-label='显示方式']")
    dm.click()
    time.sleep(0.7)
    by_group = _menu_item(mdrv, '按用例分组')
    assert by_group is not None and '✓' in (by_group.text or ''), '标签卡选「按用例分组」后 ✓ 未保留'
    _save_evidence('08_mobile_tag_subview_dropdown', mdrv)
    mdrv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)


def test_09_mobile_trash_fallback_display_menu(mdrv):
    """移动端回收站态：CaseGroupActions 隐藏（无批量修改/编辑/删除），
    子视图切换回退独立 SubViewDisplayMenu「显示方式」下拉（不回归桌面态）。"""
    _login(mdrv)
    _goto(mdrv, '/testcases/by-group')
    # 进回收站（title=回收站 toggle）
    trash_toggle = mdrv.find_element(By.XPATH, "//button[@title='回收站']")
    trash_toggle.click()
    time.sleep(1.2)
    # 回收站态分组卡：CaseGroupActions 隐藏 → 无 批量修改/编辑/删除（精确按钮文案判断）
    g1 = _group_card(mdrv, '智能音箱功能测试')
    btns = g1.find_elements(By.XPATH, ".//button")
    btn_labels = [(b.text or '').strip() or (b.get_attribute('aria-label') or '').strip()
                  for b in btns]
    banned = {'批量修改', '编辑', '删除', '新增用例', '复制'}
    hit = [lb for lb in btn_labels if lb in banned]
    assert not hit, f'移动端回收站态 CaseGroupActions 应隐藏：{btn_labels}'
    # 独立 SubViewDisplayMenu 回退存在且可用
    dm = g1.find_element(By.XPATH, ".//button[@aria-label='显示方式']")
    assert dm.is_displayed(), '移动端回收站态「显示方式」回退下拉缺失'
    dm.click()
    time.sleep(0.7)
    by_tag = _menu_item(mdrv, '按标签')
    assert by_tag is not None, '回收站态「显示方式」下拉「按标签」缺失'
    by_tag.click()
    time.sleep(1.0)
    g1 = _group_card(mdrv, '智能音箱功能测试')
    subs = g1.find_elements(By.XPATH, ".//div[contains(@class,'px-1 py-1.5') or contains(@class,'bg-muted/40')]")
    assert subs, '移动端回收站态选「按标签」后子分组头缺失'
    _save_evidence('09_mobile_trash_fallback_display_menu', mdrv)
    mdrv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)
