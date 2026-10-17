# -*- coding: utf-8 -*-
"""INT-587 返修复测（验收标准 7 ESC 已修复 + 负责人反馈补全项）浏览器走查。

针对 frontend-react/ mock 稿，dev server 默认 5299（本 run 隔离栈，REACT_DEV_BASE 可覆写）。
认证：INT-605 接线后登录页走真实后端（/api/v1/auth/* 代理 localhost:5000）；后端未起时
表单登录不可用——本地注入 admin 会话（iatp:auth:v1，permissions ['*']），test_ui_29 同口径。

覆盖（负责人反馈 + 返修交付 75aa9b32/094783f5/8fda1447 相关用例，不复测原已通过项）：
① 批量设置评估维度弹窗（§5.3.5）：三档轮次范围「所有轮次（统一设置）/指定轮次（统一设置）/
   逐轮设置（每轮可不同）」逐项可用；指定轮次展开「第1~4轮」Checkbox 组；逐轮设置展开轮次
   Tab「第 n 轮/最后一轮」+「添加轮次」；维度选择为 V9.7.10 平铺 chips 云（搜索「搜索评估
   维度」+「已选 {n} 项」计数 + Plus/Check chip）。
② 四弹窗三档轮次范围逐项可用（专属参数/播放设备/声压/噪声：RoundScopeThreeField 三档 +
   逐轮 Tab 分轮可配）。
③ 评估维度选择改 V9.7.10 平铺云在四处消费方生效：批量设置评估维度、用例编辑抽屉轮次评估步骤、
   整体评估维度、音频导入上传选项（默认勾识别准确率/唤醒成功率）。
④ 导入收敛单入口：页头「导入用例」直跳 /audio-import；不再有「导入用例文件」下拉。
⑤ 导出弹窗仅导出（ExportDialog，范围 RadioGroup + 格式 Select，无导入分支）。
⑥ 验收标准 7 复测：ESC 清选（此前 P2 失败项，47474e69 修复）在三态下可用。

失败落 tests/ui/artifacts/int587_retest/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int587_retest')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5299')
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


def _login(drv):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    snapshot = {
        'state': {
            'user': {
                'id': 'mock-admin-001',
                'username': 'admin',
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


def _select_case(drv, index=0):
    boxes = WebDriverWait(drv, 12).until(
        lambda d: d.find_elements(
            By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']"))
    assert boxes, '未找到用例勾选 checkbox'
    boxes[index].click()
    time.sleep(0.6)
    return boxes[index]


def _bulk_bar(drv):
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")) > 0)
    return drv.find_element(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")


def _bulk_button(drv, label):
    bar = _bulk_bar(drv)
    return bar.find_element(By.XPATH, f".//button[contains(., '{label}')]")


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _radio(dlg, name, label):
    """弹窗内 radio：name 分组 + label 文案（三档轮次范围共用 name）。"""
    el = dlg.find_element(
        By.XPATH, f".//input[@type='radio'][@name='{name}'][ancestor::label[contains(., '{label}')]]")
    el.click()
    time.sleep(0.5)


def _round_checkbox(dlg, round_no):
    xpath = f".//label[contains(., '第{round_no}轮')]//*[@role='checkbox']"
    els = dlg.find_elements(By.XPATH, xpath)
    assert els, f'「第{round_no}轮」Checkbox 缺失'
    return els[0]


def _toast_text(drv):
    time.sleep(0.4)
    toasts = drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]")
    if not toasts:
        return ''
    return '\n'.join(t.text for t in toasts)


# ── ① 批量设置评估维度弹窗（§5.3.5）三档轮次 + V9.7.10 平铺云 ──
def test_01_batch_dimensions_three_mode_and_flat_cloud(drv):
    _login(drv)
    _select_case(drv, 0)
    _bulk_button(drv, '批量设置评估维度').click()
    time.sleep(0.8)

    dlg = _dialog_by_title(drv, '批量设置评估维度')
    txt = dlg.text
    assert '您勾选了 1 个用例，将为其设置评估维度' in txt, f'弹窗头部缺失：{txt[:200]}'
    # 三档轮次范围
    for mode in ['所有轮次（统一设置）', '指定轮次（统一设置）', '逐轮设置（每轮可不同）']:
        assert mode in txt, f'三档轮次缺「{mode}」'
    # V9.7.10 平铺云：搜索 + 已选计数（input 占位不入 text，改用 aria-label 断言）
    assert dlg.find_elements(By.XPATH, ".//input[@aria-label='搜索评估维度']"), '平铺云搜索框缺失'
    assert '已选' in txt, f'已选计数缺失：{txt[:400]}'
    chips = dlg.find_elements(By.XPATH, ".//button[contains(@class,'rounded-full')]")
    assert len(chips) >= 3, f'平铺维度 chip 云缺失（{len(chips)}）'
    # 未选 chip 为 Plus、已选为 Check（图标不可文本断言；断言 aria-pressed 双向切换）
    c0 = chips[0]
    pressed0 = c0.get_attribute('aria-pressed')
    c0.click()
    time.sleep(0.4)
    assert c0.get_attribute('aria-pressed') != pressed0, '点击维度 chip 未切换选中态'
    c0.click()
    time.sleep(0.4)
    _save_evidence('01_batch_dims_all_mode_cloud', drv)

    # 指定轮次 → 轮次号 Checkbox 组「第1~4轮」
    _radio(dlg, 'batch-dim-round-mode', '指定轮次')
    dlg = _dialog_by_title(drv, '批量设置评估维度')
    for r in range(1, 5):
        assert f'第{r}轮' in dlg.text, f'指定轮次缺「第{r}轮」'
    _round_checkbox(dlg, 2).click()
    time.sleep(0.3)
    _save_evidence('01b_batch_dims_specific_rounds', drv)

    # 逐轮设置 → 轮次 Tab（第 n 轮/最后一轮 + 添加轮次）
    _radio(dlg, 'batch-dim-round-mode', '逐轮设置')
    dlg = _dialog_by_title(drv, '批量设置评估维度')
    txt = dlg.text
    assert '第 1 轮' in txt and '最后一轮' in txt, f'逐轮 Tab 缺：{txt[:300]}'
    assert '添加轮次' in txt, '「添加轮次」缺'
    add = dlg.find_element(By.XPATH, ".//button[contains(., '添加轮次')]")
    add.click()
    time.sleep(0.4)
    dlg = _dialog_by_title(drv, '批量设置评估维度')
    # rounds 初始 [1,2,-1]，添加后为 [1,2,-1,3] → 出现「第 3 轮」
    assert '第 3 轮' in dlg.text, '添加轮次后应出现「第 3 轮」'
    _save_evidence('01c_batch_dims_per_round_tabs', drv)

    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.5)


# ── ② 四弹窗三档轮次范围逐项可用 ────────────────────────
def test_02_four_dialogs_three_mode_round_scope(drv):
    _login(drv)
    _select_case(drv, 0)
    cases = [
        ('批量设置专属参数', '批量设置用例专属参数', 'batch-algo-params-round'),
        ('批量设置播放设备', '批量设置播放设备', 'batch-device-round'),
        ('批量设置声压', '批量设置声压级', 'batch-spl-round'),
        ('批量设置噪声', '批量设置噪声', 'batch-noise-round'),
    ]
    for btn_label, dlg_title, radio_name in cases:
        _bulk_button(drv, btn_label).click()
        time.sleep(0.8)
        dlg = _dialog_by_title(drv, dlg_title)
        txt = dlg.text
        for mode in ['所有轮次（统一设置）', '指定轮次（统一设置）', '逐轮设置（每轮可不同）']:
            assert mode in txt, f'「{dlg_title}」三档轮次缺「{mode}」'
        # 指定轮次展开 Checkbox 组
        _radio(dlg, radio_name, '指定轮次')
        dlg = _dialog_by_title(drv, dlg_title)
        for r in range(1, 5):
            assert f'第{r}轮' in dlg.text, f'「{dlg_title}」指定轮次缺「第{r}轮」'
        # 逐轮设置展开轮次 Tab（分轮可配）
        _radio(dlg, radio_name, '逐轮设置')
        dlg = _dialog_by_title(drv, dlg_title)
        tabs = dlg.find_elements(By.XPATH, ".//button[contains(., '第') and contains(., '轮')]")
        assert len(tabs) >= 4, f'「{dlg_title}」逐轮 Tab 缺（{len(tabs)}）'
        _save_evidence(f'02_{btn_label}_three_mode', drv)
        dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
        time.sleep(0.5)
        # 恢复勾选（取消后勾选保持）
        assert _bulk_bar(drv), '取消弹窗后浮条应仍在'


# ── ③ 音频导入上传选项评估维度平铺云（默认勾必填项）─────
def test_03_audio_import_upload_options_dimension_cloud(drv):
    _login(drv)
    _goto(drv, '/audio-import')
    assert '音频管理' in _body_text(drv), '音频导入页未渲染'
    drv.find_element(By.XPATH, "//button[contains(., '上传音频')]").click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '上传音频')
    assert '生成测试用例' in dlg.text, '生成测试用例开关缺'
    # 点 label 切换开关（base-ui Switch 根按钮被 overlay 遮挡风险，label 关联 htmlFor 最稳）
    dlg.find_element(By.XPATH, ".//label[contains(., '生成测试用例')]").click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '上传音频')
    txt = dlg.text
    assert '评估维度' in txt, '开启生成测试用例后应出现评估维度区'
    assert dlg.find_elements(By.XPATH, ".//input[@aria-label='搜索评估维度']"), '上传选项维度搜索框缺失'
    assert '已选 2 项' in txt, f'上传选项默认应已选 2 项（识别准确率/唤醒成功率）：{txt[:400]}'
    chips = dlg.find_elements(By.XPATH, ".//button[contains(@class,'rounded-full')]")
    assert len(chips) >= 3, f'上传选项维度 chip 云缺失（{len(chips)}）'
    # 识别准确率在 asr-v3 过滤下可见且默认勾选
    names = {c.text: c.get_attribute('aria-pressed') for c in chips}
    assert names.get('识别准确率') == 'true', f'识别准确率应默认勾选：{names}'
    # 唤醒成功率关联 asr-stream，asr-v3 过滤下不可见；切到流式识别引擎后应可见且默认勾选
    alg_sel = dlg.find_element(By.CSS_SELECTOR, "button[data-slot='select-trigger'][aria-label='算法类型']")
    alg_sel.click()
    time.sleep(0.8)
    opt = None
    for content in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content']"):
        for item in content.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']"):
            if '流式识别引擎' in item.text:
                opt = item
                break
        if opt is not None:
            break
    assert opt is not None, '算法类型 Select 缺「流式识别引擎」'
    opt.click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '上传音频')
    chips = dlg.find_elements(By.XPATH, ".//button[contains(@class,'rounded-full')]")
    names = {c.text: c.get_attribute('aria-pressed') for c in chips}
    assert names.get('唤醒成功率') == 'true', f'asr-stream 下唤醒成功率应默认勾选：{names}'
    _save_evidence('03_upload_options_dimension_cloud', drv)
    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.5)


# ── ④ 用例编辑抽屉轮次评估步骤 + 整体评估维度平铺云 ──────
def test_04_case_edit_drawer_dimension_flat_cloud(drv):
    _login(drv)
    # 打开首张用例编辑抽屉
    edit_btn = WebDriverWait(drv, 12).until(
        lambda d: d.find_element(By.XPATH,
            "//button[@aria-label='编辑用例']"))
    edit_btn.click()
    time.sleep(1.0)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    txt = sheet.text
    assert '整体评估维度' in txt, f'整体评估维度节缺失：{txt[:200]}'
    # 整体评估维度：平铺云（搜索框 + 已选计数）
    overall = sheet.find_element(By.XPATH, ".//section[.//*[contains(., '整体评估维度')]]")
    assert overall.find_elements(By.XPATH, ".//input[@aria-label='搜索评估维度']"), '整体评估维度平铺云搜索框缺失'
    assert '已选' in overall.text, f'整体评估维度已选计数缺失：{overall.text[:300]}'
    o_chips = overall.find_elements(By.XPATH, ".//button[contains(@class,'rounded-full')]")
    assert len(o_chips) >= 3, f'整体评估维度 chip 云缺失（{len(o_chips)}）'
    _save_evidence('04a_drawer_overall_dimension_cloud', drv)
    # 轮次「评估维度」步骤平铺云
    step_tab = sheet.find_element(By.XPATH, ".//button[@role='tab'][contains(., '评估维度')]")
    step_tab.click()
    time.sleep(0.9)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    # 步骤区（含 DimensionPicker）在 sheet 内
    step_area = sheet.find_element(By.XPATH, ".//div[.//input[@aria-label='搜索评估维度']]")
    assert '已选' in step_area.text or step_area.find_elements(By.XPATH, ".//*[contains(., '已选')]"), \
        '轮次评估维度步骤已选计数缺失'
    s_chips = step_area.find_elements(By.XPATH, ".//button[contains(@class,'rounded-full')]")
    assert len(s_chips) >= 3, f'轮次评估维度步骤 chip 云缺失（{len(s_chips)}）'
    _save_evidence('04b_drawer_round_eval_dimension_cloud', drv)
    # 关闭抽屉（ESC 归抽屉消费）
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)


# ── ④ 导入收敛单入口 → /audio-import；导出仅导出 ────────
def test_05_import_single_entry_and_export_only(drv):
    _login(drv)
    btns = [b.text.strip() for b in
            drv.find_elements(By.TAG_NAME, 'button') if b.is_displayed() and b.text.strip()]
    assert '导入用例' in btns, f'页头缺「导入用例」单入口：{btns}'
    assert '导入用例文件' not in btns, '不应再有「导入用例文件」入口'
    assert '导入' not in btns, '不应再有旧的「导入」下拉入口'
    # 导入用例 → 直跳 /audio-import
    drv.find_element(By.XPATH, "//button[contains(., '导入用例')]").click()
    time.sleep(1.5)
    assert '/audio-import' in drv.current_url, f'导入用例应跳 /audio-import：{drv.current_url}'
    assert '音频管理' in _body_text(drv), '音频导入页未渲染'
    _save_evidence('05_import_single_entry', drv)

    # 回用例页验导出弹窗仅导出
    _goto(drv, '/testcases/by-group')
    drv.find_element(By.XPATH, "//button[contains(., '导出')]").click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '导出用例')
    txt = dlg.text
    assert '导出范围' in txt and '仅导出已选' in txt, f'导出范围缺：{txt[:200]}'
    assert '格式' in txt, '格式 Select 缺'
    assert '导入用例文件' not in txt and '导入后' not in txt, '导出弹窗不应含导入分支'
    _save_evidence('05b_export_only', drv)
    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.5)


# ── ⑤ 验收标准 7 复测：ESC 清选（此前 P2 失败项）───────
def test_06_esc_clear_retest(drv):
    _login(drv)
    _select_case(drv, 0)
    assert _bulk_bar(drv), '勾选后浮条应浮出'
    # ESC 清选
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)
    assert not drv.find_elements(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]"), \
        'ESC 清选后浮条应消失'
    _save_evidence('06_esc_clear', drv)
    # 标签视图 ESC 同样可用
    _goto(drv, '/testcases/by-tag')
    _select_case(drv, 0)
    assert _bulk_bar(drv), '标签视图勾选后浮条应浮出'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)
    assert not drv.find_elements(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]"), \
        '标签视图 ESC 清选后浮条应消失'
    # 回收站态 ESC 可用
    _goto(drv, '/testcases/by-group')
    drv.find_element(By.CSS_SELECTOR, "button[title='回收站']").click()
    time.sleep(1.0)
    _select_case(drv, 0)
    assert _bulk_bar(drv), '回收站勾选后浮条应浮出'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)
    assert not drv.find_elements(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]"), \
        '回收站 ESC 清选后浮条应消失'
