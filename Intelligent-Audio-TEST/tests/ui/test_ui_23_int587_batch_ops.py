# -*- coding: utf-8 -*-
"""INT-587 用例管理页批量操作弹窗补全 浏览器走查（真实 Chrome headless，按 test_ui_22 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273），
按 11_用例域.md §5.3.1~5.3.4 + 刷新参考参数 验收清单逐项断言：

① §5.3.1 批量设置专属参数：算法类型* Select → DynamicForm 按算法 schema 渲染（基础识别等），
   空态「该算法暂无参数配置」（无 schema 算法，mock 数据全启用算法均有 schema，代码路径核验）+
   轮次范围 RadioGroup「所有轮次/指定轮次」→ 指定轮次展开「第{n}轮」Checkbox 组；
② §5.3.2 批量设置播放设备：设备 Select「{设备名} (通道 {n}) [干声/噪声]」+ 空态「暂无可用的播放设备」、
   「重新扫描」ghost 钮 → Spinner「正在扫描可用设备...」→ 失败红字（mock 奇偶轮换）→ 再扫恢复设备列表；
③ §5.3.3 批量设置声压级：声压级 dB* number 占位「请输入声压级，例如：65」min0/max140 + 应用层级五项；
④ §5.3.4 批量设置噪声：噪声音频选择器卡「点击选择噪声音频」→ 音频选择弹窗选中显名 + 重新选择/清除、
   噪声声压级 dB 默认 94 + 建议文案、播放设备多选 chips、应用层级默认勾 case级/segment级背景噪声；
⑤ 统一头部「您勾选了 {n} 个用例，将统一设置 X」+ 底部「取消｜确定」；确定后 toast 批量口径
   「批量操作执行成功（更新 {n} 个）」；
⑥ 刷新参考参数 ConfirmDialog「将对 {n} 个用例刷新参考参数，是否继续？」→ 确定 → toast「已提交刷新任务」；
⑦ 批量浮条在分组/标签/回收站三态正常；X 清选 / ESC 可用；
⑧ 新交互不落演示 toast（各弹窗真实弹出）；无新路由/URL 参数（仅 /testcases/{view} 页内交互）。

失败落 tests/ui/artifacts/int587_batch_ops/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int587_batch_ops')

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


def _login(drv, username='admin'):
    """INT-605 接线后登录页走真实后端（/api/v1/auth/* 代理 localhost:5000）；后端未起时
    表单登录不可用。改为 localStorage 注入 admin 会话（iatp:auth:v1 + token，权限 '*'），
    test_ui_29 同口径。"""
    drv.get(BASE + '/login')
    time.sleep(1.2)
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
def _select_case(drv, index=0):
    """点第 index 张用例卡头 checkbox（aria-label^='选择 '）勾选该用例。"""
    boxes = WebDriverWait(drv, 12).until(
        lambda d: d.find_elements(
            By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']"))
    assert boxes, '未找到用例勾选 checkbox'
    boxes[index].click()
    time.sleep(0.6)
    return boxes[index]


def _bulk_bar(drv):
    """底部批量浮条（CaseBulkActions）。"""
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")) > 0)
    return drv.find_element(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")


def _bulk_button(drv, label):
    """浮条内指定动作钮。"""
    bar = _bulk_bar(drv)
    return bar.find_element(By.XPATH, f".//button[contains(., '{label}')]")


def _dialogs(drv):
    """当前页面所有 dialog-content 元素。"""
    return drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")


def _dialog_by_title(drv, title):
    """按 DialogTitle 文本定位弹窗容器。"""
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _confirm_dialog(drv):
    """AlertDialog（ConfirmDialog）容器。"""
    els = drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    assert els, '确认弹窗未出现'
    return els[0]


def _toast_text(drv):
    """sonner toast 当前文本（自动等 0.2s 让动画落位）。"""
    time.sleep(0.4)
    toasts = drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]")
    if not toasts:
        return ''
    return '\n'.join(t.text for t in toasts)


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


def _click_radio(drv, name, label):
    """RoundScopeField 原生 radio：name 分组 + label 文案。"""
    el = drv.find_element(
        By.XPATH, f"//input[@type='radio'][@name='{name}'][ancestor::label[contains(., '{label}')]]")
    el.click()
    time.sleep(0.5)


def _round_checkbox(drv, round_no):
    """指定轮次展开后的「第{n}轮」checkbox（返回 role=checkbox 按钮）。"""
    xpath = (
        f"//label[contains(., '第{round_no}轮')]//*[@role='checkbox']"
    )
    els = drv.find_elements(By.XPATH, xpath)
    assert els, f'「第{round_no}轮」Checkbox 缺失'
    return els[0]


# ── ① §5.3.1 批量设置专属参数 ──────────────────────────
def test_01_algo_params_dialog_fields_and_confirm(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)
    _bulk_button(drv, '批量设置专属参数').click()
    time.sleep(0.8)

    dlg = _dialog_by_title(drv, '批量设置用例专属参数')
    txt = dlg.text
    # 统一头部「您勾选了 {n} 个用例，将统一设置 X」+ 底部「取消｜确定」
    assert '您勾选了 1 个用例，将统一设置其算法专属参数' in txt, f'弹窗头部文案缺失：{txt[:200]}'
    assert '算法类型 *' in txt, '算法类型必填标识缺失'
    assert '请先选择算法类型，参数表单将按算法 schema 加载' in txt, '未选算法空态缺失'
    assert '轮次范围' in txt and '所有轮次' in txt and '指定轮次' in txt, '轮次范围缺失'
    assert '取消' in txt and '确定' in txt, '底部取消/确定缺失'
    _save_evidence('01a_algo_params_initial', drv)

    # 选算法 → DynamicForm 按 schema 渲染（asr-v3 基础识别/采样率等）
    dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']").click()
    time.sleep(0.5)
    _select_option(drv, '通用识别引擎')
    txt = _dialog_by_title(drv, '批量设置用例专属参数').text
    for f in ['基础识别', '采样率（Hz）', 'VAD 阈值', '最大音频时长（秒）', '说话人分离']:
        assert f in txt, f'算法参数表单缺「{f}」'
    _save_evidence('01b_algo_params_with_form', drv)

    # 确定 → 批量口径 toast（不再落演示 toast）
    _dialog_by_title(drv, '批量设置用例专属参数').find_element(
        By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]").click()
    time.sleep(0.8)
    t = _toast_text(drv)
    assert '批量操作执行成功（更新 1 个）' in t, f'批量 toast 缺失：{t}'
    # 弹窗已关闭
    assert len(_dialogs(drv)) == 0, '确定后弹窗应关闭'


# ── ② §5.3.2 批量设置播放设备：重扫 Spinner/失败红字/恢复 ──
def test_02_device_dialog_rescan_spinner_error_recovery(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)
    _bulk_button(drv, '批量设置播放设备').click()
    time.sleep(0.8)

    dlg = _dialog_by_title(drv, '批量设置播放设备')
    txt = dlg.text
    assert '您勾选了 1 个用例，将统一设置其播放设备' in txt, f'播放设备弹窗头部缺失：{txt[:200]}'
    assert '播放设备 *' in txt and '重新扫描' in txt, '播放设备必填/重新扫描钮缺失'
    # 初始 ready 态：设备列表可选（占位为空态文案「暂无可用的播放设备」）
    dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']").click()
    time.sleep(0.5)
    _select_option(drv, '音频接口 A (通道 1) [干声]')
    # 应用层级五项
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    txt = dlg.text
    for layer in ['目标人音频', 'case级背景噪声', 'segment级背景噪声', '干扰人', '声纹']:
        assert layer in txt, f'应用层级「{layer}」缺失'
    assert '轮次范围' in txt and '所有轮次' in txt, '轮次范围缺失'

    # 重新扫描第 1 次 → Spinner「正在扫描可用设备...」→ 失败红字 + 设备清空（mock 奇偶轮换）
    rescan = dlg.find_element(By.XPATH, ".//button[contains(., '重新扫描')]")
    rescan.click()
    time.sleep(0.2)
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    assert '正在扫描可用设备...' in dlg.text, '扫描中 Spinner 文案缺失'
    _save_evidence('02a_device_rescan_spinner', drv)
    time.sleep(1.2)
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    assert '扫描失败：无法连接设备管理器' in dlg.text, f'失败红字缺失：{dlg.text[-200:]}'
    sel = dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    assert sel.get_attribute('aria-disabled') or sel.get_attribute('disabled'), '失败态设备 Select 应禁用'
    _save_evidence('02b_device_rescan_error', drv)

    # 重新扫描第 2 次 → 恢复成功态（设备列表可选）
    dlg.find_element(By.XPATH, ".//button[contains(., '重新扫描')]").click()
    time.sleep(1.2)
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    assert '扫描失败' not in dlg.text, f'二次扫描应恢复成功态：{dlg.text[-200:]}'
    dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']").click()
    time.sleep(0.5)
    _select_option(drv, '功放 左声道 (通道 1) [干声]')
    _save_evidence('02c_device_rescan_recovered', drv)

    # 取消关闭
    _dialog_by_title(drv, '批量设置播放设备').find_element(
        By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.5)


# ── ③ §5.3.3 批量设置声压级 ────────────────────────────
def test_03_spl_dialog_fields_and_confirm(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)
    _bulk_button(drv, '批量设置声压').click()
    time.sleep(0.8)

    dlg = _dialog_by_title(drv, '批量设置声压级')
    txt = dlg.text
    assert '您勾选了 1 个用例，将统一设置其声压级' in txt, f'声压级弹窗头部缺失：{txt[:200]}'
    assert '声压级 dB *' in txt, '声压级必填标识缺失'
    spl = dlg.find_element(By.CSS_SELECTOR, "input[type='number']")
    assert spl.get_attribute('placeholder') == '请输入声压级，例如：65', \
        f'占位缺失：{spl.get_attribute("placeholder")}'
    assert spl.get_attribute('min') == '0' and spl.get_attribute('max') == '140', \
        '声压级 0-140 约束缺失'
    for layer in ['目标人音频', 'case级背景噪声', 'segment级背景噪声', '干扰人', '声纹']:
        assert layer in txt, f'应用层级「{layer}」缺失'
    assert '轮次范围' in txt, '轮次范围缺失'
    # 五项均可勾（点目标人音频 + 干扰人）
    for label in ['目标人音频', '干扰人']:
        cb = dlg.find_element(
            By.XPATH, f".//label[contains(., '{label}')]//*[@role='checkbox']")
        cb.click()
        time.sleep(0.3)
        assert cb.get_attribute('aria-checked') == 'true', f'「{label}」勾选未生效'
    _save_evidence('03_spl_dialog', drv)

    # 确定 → 批量口径 toast
    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]").click()
    time.sleep(0.8)
    t = _toast_text(drv)
    assert '批量操作执行成功（更新 1 个）' in t, f'批量 toast 缺失：{t}'


# ── ④ §5.3.4 批量设置噪声：音频选择器卡 + 默认层级 ────────
def test_04_noise_dialog_audio_picker_and_default_layers(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)
    _bulk_button(drv, '批量设置噪声').click()
    time.sleep(0.8)

    dlg = _dialog_by_title(drv, '批量设置噪声')
    txt = dlg.text
    assert '您勾选了 1 个用例，将统一设置其噪声' in txt, f'噪声弹窗头部缺失：{txt[:200]}'
    assert '噪声音频' in txt and '点击选择噪声音频' in txt, '噪声音频选择器卡缺失'
    # 噪声声压级默认 94 + 建议文案
    spl = dlg.find_element(By.CSS_SELECTOR, "input[aria-label='噪声声压级 dB']")
    assert spl.get_attribute('value') == '94', f'噪声声压级默认应为 94：{spl.get_attribute("value")}'
    assert '建议值：94 dB（1kHz 校准点）' in txt, '噪声声压级建议文案缺失'
    # 播放设备多选 chips（默认选中 dev-1/dev-3）
    for dev in ['音频接口 A (通道 1) [干声]', '功放 左声道 (通道 1) [干声]']:
        chip = dlg.find_element(By.XPATH, f".//button[@aria-pressed='true'][contains(., '{dev}')]")
        assert chip is not None, f'播放设备 chip「{dev}」应默认选中'
    assert '播放设备（可多选）' in txt, '播放设备多选标签缺失'

    # 应用层级默认勾 case级/segment级背景噪声，目标人音频未勾
    cb_case = dlg.find_element(By.XPATH, ".//label[contains(., 'case级背景噪声')]//*[@role='checkbox']")
    cb_seg = dlg.find_element(By.XPATH, ".//label[contains(., 'segment级背景噪声')]//*[@role='checkbox']")
    cb_target = dlg.find_element(By.XPATH, ".//label[contains(., '目标人音频')]//*[@role='checkbox']")
    assert cb_case.get_attribute('aria-checked') == 'true', 'case级背景噪声应默认勾选'
    assert cb_seg.get_attribute('aria-checked') == 'true', 'segment级背景噪声应默认勾选'
    assert cb_target.get_attribute('aria-checked') == 'false', '目标人音频默认不应勾选'
    _save_evidence('04a_noise_dialog_default', drv)

    # 点击选择噪声音频 → 音频选择弹窗 → 选中显名 + 重新选择/清除
    dlg.find_element(By.XPATH, ".//button[contains(., '点击选择噪声音频')]").click()
    time.sleep(0.7)
    picker = _dialog_by_title(drv, '选择噪声音频')
    ptxt = picker.text
    assert '粉红噪声_94dB.wav' in ptxt and '白噪声_85dB.wav' in ptxt, f'音频选择弹窗列表缺失：{ptxt[:200]}'
    _save_evidence('04b_noise_audio_picker', drv)
    picker.find_element(By.XPATH, ".//button[contains(., '粉红噪声_94dB.wav')]").click()
    time.sleep(0.6)
    dlg = _dialog_by_title(drv, '批量设置噪声')
    txt = dlg.text
    assert '粉红噪声_94dB.wav' in txt, '已选噪声音频未显名'
    assert '重新选择' in txt and '清除' in txt, '重新选择/清除钮缺失'
    _save_evidence('04c_noise_audio_selected', drv)

    # 清除 → 回到「点击选择噪声音频」
    dlg.find_element(By.XPATH, ".//button[contains(., '清除')]").click()
    time.sleep(0.5)
    dlg = _dialog_by_title(drv, '批量设置噪声')
    assert '点击选择噪声音频' in dlg.text, '清除后应回到选择卡'

    # 确定 → 批量口径 toast
    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]").click()
    time.sleep(0.8)
    t = _toast_text(drv)
    assert '批量操作执行成功（更新 1 个）' in t, f'批量 toast 缺失：{t}'


# ── ⑤ 轮次范围三态交互（各弹窗可用）────────────────────
def test_05_round_scope_specific_rounds_checkboxes(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)

    # 声压弹窗内验证轮次范围
    _bulk_button(drv, '批量设置声压').click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量设置声压级')
    _click_radio(drv, 'batch-spl-round', '指定轮次')
    txt = dlg.text
    for r in ['第1轮', '第2轮', '第3轮', '第4轮']:
        assert r in txt, f'指定轮次展开缺「{r}」'
    # 勾选第 2 轮
    cb2 = _round_checkbox(drv, 2)
    cb2.click()
    time.sleep(0.3)
    assert cb2.get_attribute('aria-checked') == 'true', '第2轮勾选未生效'
    _save_evidence('05a_round_scope_specific', drv)
    # 切回所有轮次 → Checkbox 组收起
    _click_radio(drv, 'batch-spl-round', '所有轮次')
    dlg = _dialog_by_title(drv, '批量设置声压级')
    assert '第1轮' not in dlg.text, '切回所有轮次后 Checkbox 组应收起'
    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.5)

    # 噪声弹窗内同样可用
    _bulk_button(drv, '批量设置噪声').click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量设置噪声')
    _click_radio(drv, 'batch-noise-round', '指定轮次')
    cb4 = _round_checkbox(drv, 4)
    cb4.click()
    time.sleep(0.3)
    assert cb4.get_attribute('aria-checked') == 'true', '噪声弹窗第4轮勾选未生效'
    _save_evidence('05b_noise_round_scope_specific', drv)
    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.5)


# ── ⑥ 刷新参考参数 ConfirmDialog 直执行 ────────────────
def test_06_refresh_confirm_dialog_and_toast(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)
    _bulk_button(drv, '刷新参考参数').click()
    time.sleep(0.7)
    conf = _confirm_dialog(drv)
    txt = conf.text
    assert '刷新参考参数' in txt, f'确认弹窗标题缺失：{txt[:120]}'
    assert '将对 1 个用例刷新参考参数，是否继续？' in txt, f'确认文案缺失：{txt[:200]}'
    _save_evidence('06_refresh_confirm', drv)
    conf.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
    time.sleep(0.8)
    t = _toast_text(drv)
    assert '已提交刷新任务' in t, f'刷新 toast 缺失：{t}'


# ── ⑦ 回收站态批量浮条（批量恢复/批量彻底删除）───────────
def test_07_trash_view_bulk_bar_restore_purge(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    drv.find_element(By.CSS_SELECTOR, "button[title='回收站']").click()
    time.sleep(1.0)
    txt = _body_text(drv)
    assert '删除时间' in txt or '回收站' in txt, f'回收站态未进入：{txt[:200]}'
    _select_case(drv, 0)
    bar = _bulk_bar(drv)
    bt = bar.text
    assert '批量恢复' in bt and '批量彻底删除' in bt, f'回收站浮条应含恢复/彻底删除：{bt}'
    # 新批量设置动作不应出现在回收站态
    for banned in ['批量设置专属参数', '批量设置播放设备', '批量设置声压', '批量设置噪声']:
        assert banned not in bt, f'回收站态不应出现「{banned}」'
    _save_evidence('07_trash_bulk_bar', drv)
    # 恢复默认态
    drv.find_element(By.CSS_SELECTOR, "button[title='回收站']").click()
    time.sleep(0.8)


# ── ⑦ X 清选 / ESC 可用 ────────────────────────────────
def test_08_x_clear_and_esc(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)
    assert _bulk_bar(drv), '勾选后浮条应浮出'
    # X 清选
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='清除选择 (Esc)']").click()
    time.sleep(0.5)
    assert drv.find_elements(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]") == [], \
        'X 清选后浮条应消失'
    # ESC 清选
    _select_case(drv, 1)
    assert _bulk_bar(drv), '再次勾选后浮条应浮出'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)
    assert drv.find_elements(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]") == [], \
        'ESC 清选后浮条应消失'


# ── ⑦ 标签视图批量操作可用 ─────────────────────────────
def test_09_tag_view_batch_ops(drv):
    _login(drv)
    _goto(drv, '/testcases/by-tag')
    _select_case(drv, 0)
    bar = _bulk_bar(drv)
    bt = bar.text
    for btn in ['批量设置专属参数', '批量设置播放设备', '批量设置声压', '批量设置噪声', '刷新参考参数']:
        assert btn in bt, f'标签视图浮条缺「{btn}」'
    _bulk_button(drv, '批量设置噪声').click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量设置噪声')
    assert '您勾选了 1 个用例，将统一设置其噪声' in dlg.text, '标签视图噪声弹窗未弹出'
    _save_evidence('09_tag_view_noise_dialog', drv)
    dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.5)
    # 当前 URL 仍为 /testcases/by-tag（无新路由/URL 参数）
    assert '/testcases/by-tag' in drv.current_url, f'不应产生新路由：{drv.current_url}'


# ── ⑧ 演示 toast 不再落地 + 无新增前端报错 ──────────────
def test_10_no_demo_toast_and_no_console_errors(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    _select_case(drv, 0)
    # 依次点 4 个新动作：弹窗应真实弹出（而非演示 toast「批量操作执行成功（演示…）」）
    for label, title in [
        ('批量设置专属参数', '批量设置用例专属参数'),
        ('批量设置播放设备', '批量设置播放设备'),
        ('批量设置声压', '批量设置声压级'),
        ('批量设置噪声', '批量设置噪声'),
    ]:
        _bulk_button(drv, label).click()
        time.sleep(0.8)
        assert _dialog_by_title(drv, title) is not None, f'「{label}」未弹出弹窗'
        assert '演示：完整弹窗随接线批次落地' not in _body_text(drv), '不应再落演示 toast'
        dlg = _dialog_by_title(drv, title)
        dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
        time.sleep(0.5)
    # 页面无抛错级 console（后端未起时 /api/v1/auth/me 504 属网络环境噪音，不算 JS 运行时错误——
    # test_ui_29 同口径：'Failed to load resource' 且无 'Uncaught' 跳过）
    errors = [e for e in drv.get_log('browser')
              if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', ''))
              and not ('Failed to load resource' in str(e.get('message', ''))
                       and 'Uncaught' not in str(e.get('message', '')))]
    assert not errors, f'页面 console SEVERE 报错：{errors[:5]}'
    _save_evidence('10_no_demo_toast_final', drv)
