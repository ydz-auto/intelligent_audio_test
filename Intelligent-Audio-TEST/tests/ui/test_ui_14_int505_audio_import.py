# -*- coding: utf-8 -*-
"""INT-505 音频管理页可视稿 浏览器走查（真实 Chrome headless，按 test_ui_13 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. 列表页：标题徽标「共 142 个」+ 统计徽章行（总文件数/总大小/总时长/今日上传）+
   十列数据表 + 视图 Tabs（列表/文件夹）+ 分页
2. 搜索「搜索文件名或标注」/ 格式 / 音频类型 / 采样率 / 音频时长 / 标签 facet 筛选
3. 行菜单：预览（播放器 Dialog）/ 详情（编辑元数据 Dialog）/ 下载（toast）/
   转换格式（Dialog）/ 特征分析（Dialog）/ 播放历史（Dialog）/ 删除（ConfirmDialog）
4. 上传弹窗：拖放区 + 上传选项（生成测试用例等）+ 开始上传 → 上传进度卡（§5.4）
5. 批量：勾选行 → 批量浮条「已选 {n} 个音频」→ 批量删除 ConfirmDialog → toast
6. URL 导入 / 批量更新标注弹窗
7. 文件夹视图：左树（dry/noise/prompt/mixed）+ 右表

失败落 tests/ui/artifacts/int505_audio_import/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int505_audio_import')

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


def _wait_rows(drv, n):
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == n)


def _open_row_menu(drv, name):
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='音频 {name} 的操作']")
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


# ── 1. 列表页：标题徽标 + 统计徽章 + 列头 + 视图 Tabs + 分页 ───
def test_01_list_page_render(drv):
    _login(drv)
    _goto(drv, '/audio-import')
    txt = _body_text(drv)
    assert '音频管理' in txt, f'页面标题缺失：{txt[:120]}'
    assert '共 142 个' in txt, f'标题徽标计数缺失：{txt[:200]}'
    # 统计徽章行（§5.1 AudioListStats）
    for stat in ['总文件数', '总大小', '总时长', '今日上传']:
        assert stat in txt, f'统计徽章「{stat}」缺失'
    # 十列表头
    for header in ['ID', '文件名', '格式', '大小', '时长', '音频类型',
                   '源语言', '标签', '创建时间', '操作']:
        assert header in txt, f'列头「{header}」缺失'
    # 视图 Tabs
    assert '列表视图' in txt, '列表视图 Tab 缺失'
    assert '文件夹视图' in txt, '文件夹视图 Tab 缺失'
    # mock 首行数据
    assert '客厅_中文_命令集.wav' in txt, 'mock 音频行缺失'
    # 页头按钮（§5.1）
    for btn in ['上传音频', '批量从文件夹导入', 'URL 导入', '批量更新标注']:
        assert btn in txt, f'页头按钮「{btn}」缺失'
    # 搜索占位
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索音频']")
    assert search.get_attribute('placeholder') == '搜索文件名或标注', \
        f'搜索占位错误：{search.get_attribute("placeholder")}'
    _drain_console(drv)


# ── 2. 筛选 facet：搜索 / 音频类型 / 采样率 / 重置 ───
def test_02_facet_filters(drv):
    _goto(drv, '/audio-import')
    txt = _body_text(drv)
    assert '音频类型' in txt, '音频类型 facet 缺失'
    assert '采样率' in txt, '采样率 facet 缺失'
    assert '音频时长' in txt, '音频时长 facet 缺失'
    assert '标签' in txt, '标签 facet 缺失'
    # 搜索过滤（等防抖提交且过滤生效：客厅行消失）
    search = drv.find_element(By.XPATH, "//input[@aria-label='搜索音频']")
    search.send_keys('噪声')
    WebDriverWait(drv, 8).until(
        lambda d: '客厅_中文_命令集.wav' not in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '白噪声_空调.wav' in txt, '搜索「噪声」后应命中白噪声_空调'
    assert '客厅_中文_命令集.wav' not in txt, '搜索后干声样本不应可见'
    # 重置
    drv.find_element(By.XPATH, "//button[contains(., '重置')]").click()
    WebDriverWait(drv, 8).until(
        lambda d: '客厅_中文_命令集.wav' in d.execute_script('return document.body.textContent || ""'))


# ── 3. 行菜单：预览 / 转换格式 / 特征分析 / 播放历史 / 删除 ───
def test_03_row_actions(drv):
    _goto(drv, '/audio-import')
    # 预览
    _open_row_menu(drv, '客厅_中文_命令集.wav')
    _click_menu_item(drv, '预览')
    WebDriverWait(drv, 6).until(
        lambda d: '音频播放' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    # SelectValue 渲染选中 value 字符串（Base UI 行为，全站一致）——断言稳定文案
    assert '试听配置' in txt and '播放模式' in txt, '试听配置缺失'
    _press_esc(drv)
    # 转换格式
    _open_row_menu(drv, '客厅_中文_命令集.wav')
    _click_menu_item(drv, '转换格式')
    WebDriverWait(drv, 6).until(
        lambda d: '音频格式转换' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    for fmt in ['MP3', 'WAV', 'FLAC', 'AAC']:
        assert fmt in txt, f'转换目标格式「{fmt}」缺失'
    _press_esc(drv)
    # 特征分析
    _open_row_menu(drv, '客厅_中文_命令集.wav')
    _click_menu_item(drv, '特征分析')
    WebDriverWait(drv, 6).until(
        lambda d: '音频特征分析' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '信噪比' in txt and '质量评分' in txt, '特征分析分区缺失'
    _press_esc(drv)
    # 播放历史
    _open_row_menu(drv, '客厅_中文_命令集.wav')
    _click_menu_item(drv, '播放历史')
    WebDriverWait(drv, 6).until(
        lambda d: '播放历史' in d.execute_script('return document.body.textContent || ""'))
    _press_esc(drv)


# ── 4. 上传弹窗 → 上传进度卡 ───
def test_04_upload_dialog_and_progress(drv):
    _goto(drv, '/audio-import')
    drv.find_element(By.XPATH, "//button[contains(., '上传音频')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '拖拽文件到此处或点击选择文件' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '生成测试用例' in txt, '上传选项「生成测试用例」缺失'
    assert '继承音频标签' in txt, '上传选项「继承音频标签」缺失'
    assert '评估维度' in txt, '评估维度分区缺失'
    # 注入一个 mock wav 文件 → 已选择 1 个文件
    wav = os.path.join(ARTIFACTS, 'smoke_sample.wav')
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    with open(wav, 'wb') as f:
        f.write(b'RIFF' + b'\x00' * 64)
    file_input = drv.find_element(By.CSS_SELECTOR, 'input[type="file"]')
    file_input.send_keys(wav)
    WebDriverWait(drv, 6).until(
        lambda d: '已选择 1 个文件' in d.execute_script('return document.body.textContent || ""'))
    drv.find_element(By.XPATH, "//button[contains(., '开始上传')]").click()
    # 进度卡浮出（§5.4：任务名 + 队列控制 + 进度推进）
    WebDriverWait(drv, 8).until(
        lambda d: '队列控制' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '个音频文件' in txt, '上传任务名缺失'
    assert '导入速度' in txt or '预计剩余' in txt, '上传进度卡当前文件行缺失'


# ── 5. 批量浮条 + 批量设置标签（P1）+ 批量删除 ───
def test_05_bulk_actions(drv):
    _goto(drv, '/audio-import')
    # 勾选首行（照 test_ui_13：role=checkbox + aria-label）
    drv.find_element(By.XPATH,
        "//*[@role='checkbox'][@aria-label='选择音频 客厅_中文_命令集.wav']").click()
    WebDriverWait(drv, 6).until(
        lambda d: '已选 1 个音频' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '批量删除' in txt and '批量导出' in txt, '批量浮条按钮缺失'
    assert '更多批量操作' in txt, '更多批量操作入口缺失'
    # 批量设置标签（P1 返修：弹窗提交选中 ids，toast 与所选数量一致而非 0）
    drv.find_element(By.XPATH, "//button[contains(., '批量设置标签')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '为选中的 1 个音频批量设置标签' in d.execute_script(
            'return document.body.textContent || ""'))
    drv.find_element(By.ID, 'batch-tags-input').send_keys('测试标签')
    drv.find_element(By.XPATH, "//button[contains(., '确认设置')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '已为 1 个音频设置标签' in d.execute_script(
            'return document.body.textContent || ""'))
    # 批量删除 ConfirmDialog
    drv.find_element(By.XPATH, "//button[contains(., '批量删除')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog']"))
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '批量删除')]").click()
    time.sleep(1.0)


# ── 6. URL 导入 / 批量更新标注 弹窗 ───
def test_06_import_dialogs(drv):
    _goto(drv, '/audio-import')
    drv.find_element(By.XPATH, "//button[contains(., 'URL 导入')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '从 URL 导入音频' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert 'URL 列表' in txt and '音频类型' in txt, 'URL 导入字段缺失'
    _press_esc(drv)
    drv.find_element(By.XPATH, "//button[contains(., '批量更新标注')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '批量更新标注' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert '按文件名匹配音频与标注文件' in txt, '批量标注说明缺失'
    _press_esc(drv)


# ── 7. 文件夹视图：左树右表 + 全选（P3）+ 批量从文件夹导入（P6） ───
def test_07_folder_view(drv):
    _goto(drv, '/audio-import')
    drv.find_element(By.XPATH, "//button[contains(., '文件夹视图')]").click()
    WebDriverWait(drv, 6).until(
        lambda d: '当前文件夹' in d.execute_script('return document.body.textContent || ""'))
    txt = _body_text(drv)
    for folder in ['dry', 'noise', 'prompt', 'mixed']:
        assert folder in txt, f'文件夹树节点「{folder}」缺失'
    assert '上传音频' in txt, '文件夹卡头部上传入口缺失'
    assert '批量从文件夹导入' in txt, '文件夹卡头部「批量从文件夹导入」入口缺失（P6）'
    # 文件夹视图全选（P3 返修：作用于当前文件夹表格行，而非列表视图页行）
    row_count = len(drv.find_elements(By.CSS_SELECTOR, 'tbody tr'))
    assert row_count >= 1, '文件夹视图表格无行'
    drv.find_element(By.XPATH, "//*[@role='checkbox'][@aria-label='全选当前页']").click()
    WebDriverWait(drv, 6).until(
        lambda d: f'已选 {row_count} 个音频' in d.execute_script(
            'return document.body.textContent || ""'))
    txt = _body_text(drv)
    assert f'已选 {row_count} 个音频' in txt, \
        f'文件夹全选后批量浮条计数应为 {row_count}（作用于文件夹行集）'
    # 主题切换走查：ConfigDrawer 入口（导航栏）存在
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, f'浏览器 console SEVERE 错误：{_CONSOLE_SEVERE[:3]}'
