# -*- coding: utf-8 -*-
"""INT-695 音频选择子弹窗 + 评估策略折叠节 浏览器走查（真实 Chrome headless）。

驱动 frontend-react/ dev server（默认 5273，env REACT_DEV_BASE 可覆写），连常驻后端
（AUTH_MODE=off 注入 dev_user '*' 全放行，登录页「进入工作台」直进）按 11_用例域.md §5.1/§5.1.3
逐项断言：

① 音频选择子弹窗（多选态 + 底部计数）：新增用例抽屉 → 轮次「音频列表」步骤 →「从音频库选择」→
   Dialog sm:max-w-4xl「选择音频文件」：真实 GET /audios 列表（每页 12 条 checkbox 行）+
   头部「上传音频/批量从文件夹导入」入口 + 底部「当前页 {n} 个音频 ({总时长})｜已选择 {n} 个 ({时长})」；
   勾选首行 → 底部「已选择 1 个」→「确认选择」→ toast「已添加 {n} 个音频到轮次」→ 行内显示所选音频名。
② 评估策略折叠节（默认收起）：节头「评估策略」+ 徽章「未配置」；展开后三模式 RadioGroup
   （不使用评估策略/引用已有策略/新建策略）。
③ 引用已有策略 + 摘要卡：选「引用已有策略」→ 策略 Select（选项带摘要「{名} · 整体维度 {n} 项 ·
   噪声 {已配置|未配置}」）→ 选择「全链路智能音箱回归」→ 摘要卡（策略名 + 描述 + 维度 chips + 全局噪声
   摘要）+ 用例级覆盖区两枚 Switch + 节头徽章「已引用「全链路智能音箱回归」」。
④ 新建策略内联表单：「新建策略」→ 策略名称*（全局唯一校验）/策略描述 + 整体评估维度编辑器 +
   全局背景噪声编辑器 + 主钮「保存策略并引用」→ POST 入库 → 用例引用新策略 + 徽章
   「已引用「{策略名}」」。
⑤ 保存回读：抽屉保存 → toast「添加测试用例成功」+ description 回读 evaluationStrategy 契约
   （引用态「评估策略：已引用「{名}」」/内联态「整体维度 {n} 项 · 噪声 {已配置|未配置}」）。

失败落 tests/ui/artifacts/int695_audio_select_strategy/<用例>/。
"""
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int695_audio_select_strategy')

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
                f.write(entry.get('message', '') + '\n')
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


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _enter_workbench(drv):
    """AUTH_MODE=off：登录页「进入工作台」直进工作台。"""
    drv.get(BASE + '/login')
    time.sleep(1.5)
    btns = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if btns:
        btns[0].click()
        time.sleep(2)
    drv.get(BASE + '/testcases/by-group')
    time.sleep(2.5)
    assert '用例管理' in _body(drv) or '话轮接管' in _body(drv), '用例管理页未打开'


def _open_drawer(drv):
    btns = drv.find_elements(By.XPATH, "//button[contains(., '新增用例')]")
    target = None
    for b in btns:
        if b.text.strip() == '新增用例':
            target = b
            break
    if target is None:
        target = btns[0]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
    time.sleep(0.4)
    target.click()
    WebDriverWait(drv, 8).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']")))
    time.sleep(1.0)
    assert '新增测试用例' in _body(drv), '新增用例抽屉未打开'


def _expand_strategy(drv):
    strat = drv.find_element(By.XPATH, "//button[contains(., '评估策略')]")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", strat)
    time.sleep(0.4)
    strat.click()
    time.sleep(0.8)


def _toast_text(drv):
    time.sleep(0.4)
    return '\n'.join(t.text for t in drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]"))


# ── ① 音频选择子弹窗（多选态 + 底部计数）──────────────────
def test_01_audio_select_modal_multi(drv):
    _enter_workbench(drv)
    _open_drawer(drv)

    # 轮次「音频列表」步骤 →「从音频库选择」
    tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
    assert tabs, '音频列表步骤 Tabs 缺失'
    tabs[0].click()
    time.sleep(1.0)
    lib_btns = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
    assert lib_btns, '「从音频库选择」入口缺失'
    lib_btns[0].click()
    time.sleep(2.5)

    dlg = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    txt = dlg.text
    assert '选择音频文件' in txt, f'子弹窗标题缺失：{txt[:120]}'
    assert '上传音频' in txt and '批量从文件夹导入' in txt, f'上传/批量导入入口缺失：{txt[:200]}'
    assert '当前页' in txt and '已选择' in txt, f'底部计数缺失：{txt[:200]}'
    _save_evidence('01a_audio_modal', drv)

    # 真实列表（每页 12 条 checkbox 行）
    rows = drv.find_elements(By.XPATH, "//div[@data-slot='dialog-content']//button[.//*[@role='checkbox']]")
    assert len(rows) >= 1, '音频列表无数据'
    assert len(rows) == 12, f'音频列表每页应 12 条：{len(rows)}'

    # 勾选首行 → 底部计数更新 → 确认选择
    picked_name = rows[0].text.split('\n')[0].strip()
    drv.execute_script("arguments[0].click()", rows[0])
    time.sleep(0.8)
    txt = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']").text
    assert '已选择 1 个' in txt, f'勾选后底部计数未更新：{txt[-160:]}'
    _save_evidence('01b_audio_modal_selected', drv)

    confirm = drv.find_elements(By.XPATH, "//button[contains(., '确认选择')]")
    assert confirm, '确认选择按钮缺失'
    drv.execute_script("arguments[0].click()", confirm[0])
    time.sleep(1.0)
    t = _toast_text(drv)
    assert '已添加' in t, f'确认选择 toast 缺失：{t}'
    # 回填：所选音频名出现在轮次行内
    assert picked_name in _body(drv), f'所选音频未回填到轮次：{picked_name}'
    _save_evidence('01c_audio_added', drv)


# ── ② 评估策略折叠节（默认收起 + 三模式）──────────────────
def test_02_strategy_section_modes(drv):
    _enter_workbench(drv)
    _open_drawer(drv)

    _expand_strategy(drv)
    txt = _body(drv)
    assert '不使用评估策略' in txt and '引用已有策略' in txt and '新建策略' in txt, \
        f'三模式 RadioGroup 缺失：{txt[-300:]}'
    assert '未配置' in txt, '节头徽章应默认「未配置」'
    _save_evidence('02_strategy_modes', drv)


# ── ③ 引用已有策略 + 摘要卡 ───────────────────────────────
def test_03_reference_strategy_summary(drv):
    _enter_workbench(drv)
    _open_drawer(drv)
    _expand_strategy(drv)

    labels = drv.find_elements(By.XPATH, "//label[contains(., '引用已有策略')]")
    assert labels, '「引用已有策略」模式缺失'
    labels[0].click()
    time.sleep(1.0)

    sel = drv.find_elements(By.XPATH, "//button[contains(., '请选择要引用的评估策略')]")
    assert sel, '策略 Select 缺失'
    drv.execute_script("arguments[0].click()", sel[0])
    time.sleep(1.0)
    txt = _body(drv)
    assert '整体维度' in txt and ('已配置' in txt or '未配置' in txt), \
        f'策略选项摘要缺失：{txt[-300:]}'
    _save_evidence('03a_reference_list', drv)

    opts = drv.find_elements(By.XPATH, "//*[@data-slot='select-item' or contains(@class,'select-item')]")
    assert opts, '策略列表为空'
    drv.execute_script("arguments[0].click()", opts[0])
    time.sleep(1.0)
    txt = _body(drv)
    assert '全局策略' in txt, '策略摘要卡缺失'
    assert '覆盖整体评估维度' in txt and '覆盖全局背景噪声' in txt, '用例级覆盖区缺失'
    assert '已引用「' in txt, f'节头徽章未切换为已引用：{txt[-200:]}'
    _save_evidence('03b_reference_summary', drv)


# ── ④ 新建策略内联表单 ────────────────────────────────────
def test_04_create_strategy_inline_form(drv):
    _enter_workbench(drv)
    _open_drawer(drv)
    _expand_strategy(drv)

    labels = drv.find_elements(By.XPATH, "//label[contains(., '新建策略')]")
    assert labels, '「新建策略」模式缺失'
    labels[0].click()
    time.sleep(1.0)
    txt = _body(drv)
    assert '策略名称' in txt, '策略名称字段缺失'
    assert '整体评估维度' in txt and '全局背景噪声' in txt, '策略字段编辑器缺失'
    assert '保存策略并引用' in txt, '保存策略并引用按钮缺失'
    _save_evidence('04_create_form', drv)

    name = drv.find_element(By.CSS_SELECTOR, "input[aria-label='策略名称']")
    name.send_keys('INT695_新建策略')
    time.sleep(0.3)
    save_btn = drv.find_elements(By.XPATH, "//button[contains(., '保存策略并引用')]")
    drv.execute_script("arguments[0].click()", save_btn[0])
    time.sleep(1.2)
    t = _toast_text(drv)
    assert '已保存并引用' in t, f'新建策略 toast 缺失：{t}'
    assert '已引用「INT695_新建策略」' in _body(drv), '节头徽章未更新为已引用新策略'
    _save_evidence('04b_create_saved', drv)


# ── ⑤ 保存回读 evaluationStrategy 契约 ───────────────────
def test_05_save_readback_contract(drv):
    _enter_workbench(drv)
    _open_drawer(drv)
    _expand_strategy(drv)

    # 引用态保存回读
    labels = drv.find_elements(By.XPATH, "//label[contains(., '引用已有策略')]")
    labels[0].click()
    time.sleep(1.0)
    sel = drv.find_elements(By.XPATH, "//button[contains(., '请选择要引用的评估策略')]")
    drv.execute_script("arguments[0].click()", sel[0])
    time.sleep(1.0)
    opts = drv.find_elements(By.XPATH, "//*[@data-slot='select-item' or contains(@class,'select-item')]")
    drv.execute_script("arguments[0].click()", opts[0])
    time.sleep(1.0)

    save_btns = drv.find_elements(By.XPATH, "//button[contains(., '保存')]")
    save_btn = None
    for b in save_btns:
        if b.text.strip() == '保存':
            save_btn = b
            break
    if save_btn is None:
        save_btn = save_btns[0]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", save_btn)
    time.sleep(0.3)
    drv.execute_script("arguments[0].click()", save_btn)
    time.sleep(1.0)
    t = _toast_text(drv)
    assert '添加测试用例成功' in t, f'保存 toast 缺失：{t}'
    assert '评估策略：已引用「' in t, f'保存回读未含引用契约：{t}'
    _save_evidence('05_save_readback_reference', drv)


# ── 无抛错级 console ────────────────────────────────────
def test_06_no_console_severe_errors(drv):
    _enter_workbench(drv)
    _open_drawer(drv)
    time.sleep(1.0)
    errors = [e for e in drv.get_log('browser')
              if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', ''))]
    assert not errors, f'页面 console SEVERE 报错：{errors[:5]}'
    _save_evidence('06_no_console_errors', drv)
