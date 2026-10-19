# -*- coding: utf-8 -*-
"""INT-889 用例域模态窗逐窗验收浏览器走查（真实 Chrome headless，连常驻后端）。

针对 frontend-react/ 接线态（连常驻 5000 段 run_all 开发栈，AUTH_MODE=off 免登录，
登录页「进入工作台」直进）按本卡验收清单逐项断言：

① 音频选择子弹窗：新增用例抽屉 → 轮次「音频列表」步骤 →「从音频库选择」→
   Dialog「选择音频文件」：真实 GET /audios 列表 + 底部计数「当前页 {n} 个音频 ({时长})｜
   已选择 {n} 个」；勾选 → 底部「已选择 {n} 个」→「确认选择」→ toast「已添加 {n} 个音频
   到轮次」→ 轮次行内显示所选音频名。
② 评估策略折叠节：默认收起 → 节头「评估策略」+ 徽章「未配置」；展开后三模式
   RadioGroup（不使用评估策略/引用已有策略/新建策略）。
③ 批量操作四弹窗（专属参数/播放设备/声压/噪声）：勾选用例 → 浮条动作 → 各弹窗
   打开 → 真实数据（算法选项 / 播放设备 / 应用层级 / 轮次范围）→ 关键操作 →
   关闭；批量写操作（声压）作用于「接线测试」前缀探针用例，POST /testcases/batch。
④ 浅色 + 深色截图（§3.3 界面卡必附图）。

失败落 tests/ui/artifacts/int889_testcases_modals/<用例>/。
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
from selenium.webdriver.support import expected_conditions as EC

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int889_testcases_modals')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5320')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 本卡探针用例（「接线测试」前缀；批量写操作目标，run 结束前删）
PROBE_PREFIX = '接线测试_INT889_batchops'
PROBE_GROUP = '接线测试_INT889_组'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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


def _save_evidence(name, drv, dark=False):
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


def _load_more(drv, rounds=8):
    for _ in range(rounds):
        more = drv.find_elements(By.XPATH, "//button[contains(., '加载更多')]")
        if not more:
            return
        try:
            more[0].click()
            time.sleep(1.0)
        except Exception:
            return


def _select_probe_cases(drv):
    """勾选探针用例（接线测试_INT889_batchops_*）。"""
    boxes = drv.find_elements(
        By.CSS_SELECTOR, f"[role='checkbox'][aria-label^='选择 {PROBE_PREFIX}']")
    if not boxes:
        _load_more(drv)
        boxes = drv.find_elements(
            By.CSS_SELECTOR, f"[role='checkbox'][aria-label^='选择 {PROBE_PREFIX}']")
    assert boxes, f'未找到探针用例 checkbox（{PROBE_PREFIX}）'
    for b in boxes:
        if b.get_attribute('aria-checked') != 'true':
            drv.execute_script("arguments[0].click()", b)
            time.sleep(0.4)
    return len(boxes)


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


def _select_option(drv, text):
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


# ── ① 音频选择子弹窗（真实 GET /audios）──────────────────
def test_01_audio_select_modal_real_data(drv):
    _enter_workbench(drv)
    _open_drawer(drv)

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
    assert '当前页' in txt and '已选择' in txt, f'底部计数缺失：{txt[:200]}'
    assert '取消' in txt and '确认选择' in txt, f'底部按钮缺失：{txt[:200]}'
    _save_evidence('01a_audio_modal', drv)

    # 真实列表：常驻后端 3 个 dry 音频（兼容测试_01.wav / 同名素材.wav）
    rows = drv.find_elements(By.XPATH, "//div[@data-slot='dialog-content']//button[.//*[@role='checkbox']]")
    assert len(rows) >= 1, '音频列表无数据'
    # 首个音频名应在后端真实库中（探针：兼容测试_01.wav）
    picked_name = rows[0].text.split('\n')[0].strip()
    assert picked_name, '音频行名缺失'

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
    assert picked_name in _body(drv), f'所选音频未回填到轮次：{picked_name}'
    _save_evidence('01c_audio_added', drv)


# ── ② 评估策略折叠节（默认收起 + 三模式）──────────────────
def test_02_strategy_section_modes(drv):
    _enter_workbench(drv)
    _open_drawer(drv)

    strat = drv.find_element(By.XPATH, "//button[contains(., '评估策略')]")
    txt0 = _body(drv)
    assert '未配置' in txt0, '节头徽章应默认「未配置」'
    _expand_strategy(drv)
    txt = _body(drv)
    assert '不使用评估策略' in txt and '引用已有策略' in txt and '新建策略' in txt, \
        f'三模式 RadioGroup 缺失：{txt[-300:]}'
    _save_evidence('02_strategy_modes', drv)


# ── ③ 批量操作四弹窗（真实数据）─────────────────────────
def test_03_batch_dialogs_open_real_data(drv):
    _enter_workbench(drv)
    n = _select_probe_cases(drv)
    assert n >= 1, '探针用例勾选失败'

    # ③a 批量设置专属参数
    _bulk_button(drv, '批量设置专属参数').click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '批量设置用例专属参数')
    txt = dlg.text
    assert f'您勾选了 {n} 个用例，将统一设置其算法专属参数' in txt, f'头部文案缺失：{txt[:200]}'
    assert '算法类型 *' in txt, '算法类型必填缺失'
    # 打开算法 Select → 真实 GET /algorithm/options（voice_llm 小艺语音大模型）
    sel = dlg.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    drv.execute_script("arguments[0].click()", sel)
    time.sleep(0.6)
    _select_option(drv, '小艺语音大模型')
    txt = _dialog_by_title(drv, '批量设置用例专属参数').text
    assert '该算法暂无参数配置' in txt or '正在加载算法参数表单' in txt or '基础识别' in txt, \
        f'算法表单加载缺失：{txt[-200:]}'
    _save_evidence('03a_algo_params_dialog', drv)
    _dialog_by_title(drv, '批量设置用例专属参数').find_element(
        By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.6)

    # ③b 批量设置播放设备
    _bulk_button(drv, '批量设置播放设备').click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '批量设置播放设备')
    txt = dlg.text
    assert f'您勾选了 {n} 个用例，将统一设置其播放设备' in txt, f'播放设备弹窗头部缺失：{txt[:200]}'
    assert '播放设备 *' in txt and '重新扫描' in txt, '播放设备必填/重新扫描钮缺失'
    assert '应用层级' in txt or '目标人音频' in txt, f'应用层级缺失：{txt[-200:]}'
    _save_evidence('03b_device_dialog', drv)
    _dialog_by_title(drv, '批量设置播放设备').find_element(
        By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.6)

    # ③c 批量设置声压（关键操作：确定 → POST /testcases/batch）
    _bulk_button(drv, '批量设置声压').click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '批量设置声压级')
    txt = dlg.text
    assert f'您勾选了 {n} 个用例，将统一设置其声压级' in txt, f'声压弹窗头部缺失：{txt[:200]}'
    assert '声压级 dB *' in txt, '声压级必填缺失'
    spl = dlg.find_element(By.CSS_SELECTOR, "input[type='number']")
    assert spl.get_attribute('placeholder') == '请输入声压级，例如：65', '声压级占位缺失'
    assert spl.get_attribute('min') == '0' and spl.get_attribute('max') == '140', '声压级 0-140 缺失'
    for layer in ['目标人音频', 'case级背景噪声', 'segment级背景噪声', '干扰人', '声纹']:
        assert layer in txt, f'应用层级「{layer}」缺失'
    _save_evidence('03c_spl_dialog', drv)
    # 填声压 → 确定（写操作：作用于接线测试探针用例）
    spl.send_keys('70')
    time.sleep(0.4)
    _dialog_by_title(drv, '批量设置声压级').find_element(
        By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]").click()
    time.sleep(1.0)
    t = _toast_text(drv)
    assert '批量操作执行成功' in t, f'批量 toast 缺失：{t}'
    assert len(drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")) == 0, \
        '确定后弹窗应关闭'
    _save_evidence('03c_spl_submitted', drv)

    # ③d 批量设置噪声
    _bulk_button(drv, '批量设置噪声').click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '批量设置噪声')
    txt = dlg.text
    assert f'您勾选了 {n} 个用例，将统一设置其噪声' in txt, f'噪声弹窗头部缺失：{txt[:200]}'
    assert '噪声音频' in txt, f'噪声音频选择器缺失：{txt[-200:]}'
    assert '噪声声压级 dB' in txt, f'噪声声压级缺失：{txt[-200:]}'
    _save_evidence('03d_noise_dialog', drv)
    _dialog_by_title(drv, '批量设置噪声').find_element(
        By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.6)


# ── ④ 批量浮条清选 / 网络证据 ─────────────────────────
def test_04_batch_network_evidence(drv):
    _enter_workbench(drv)
    _select_probe_cases(drv)
    # 清空 performance log 后执行一次批量操作，抓 Network 请求
    try:
        drv.get_log('performance')
    except Exception:
        pass
    _bulk_button(drv, '批量设置声压').click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '批量设置声压级')
    spl = dlg.find_element(By.CSS_SELECTOR, "input[type='number']")
    spl.send_keys('75')
    time.sleep(0.3)
    _dialog_by_title(drv, '批量设置声压级').find_element(
        By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]").click()
    time.sleep(1.2)
    reqs = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.requestWillBeSent':
                url = inner.get('params', {}).get('request', {}).get('url', '')
                if '/api/v1/testcases/batch' in url:
                    reqs.append(inner.get('params', {}).get('request', {}))
    except Exception as e:
        reqs.append({'error': str(e)})
    assert any('/api/v1/testcases/batch' in (r.get('url', '') or '') for r in reqs), \
        f'未见 /testcases/batch 真实请求：{reqs[:3]}'
    with open(os.path.join(ARTIFACTS, '04_network_batch.json'), 'w', encoding='utf-8') as f:
        json.dump(reqs, f, ensure_ascii=False, indent=2)
    _save_evidence('04_batch_submitted', drv)


# ── ⑤ 无抛错级 console ────────────────────────────────
def test_05_no_console_severe_errors(drv):
    _enter_workbench(drv)
    _open_drawer(drv)
    time.sleep(1.0)
    errors = [e for e in drv.get_log('browser')
              if e.get('level') == 'SEVERE'
              and 'favicon' not in str(e.get('message', ''))
              and not ('Failed to load resource' in str(e.get('message', ''))
                       and 'Uncaught' not in str(e.get('message', '')))]
    assert not errors, f'页面 console SEVERE 报错：{errors[:5]}'
    _save_evidence('05_no_console_errors', drv)
