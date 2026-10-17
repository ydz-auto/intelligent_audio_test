# -*- coding: utf-8 -*-
"""INT-594 标签分类筛选核实补齐 浏览器走查（真实 Chrome headless，按 test_ui_25 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273，env 可覆写），
按 INT-594 交付清单（React页面工程师B commit 5b4b9859）与 11_用例域.md §3.4/§4.2 逐项断言：

① 用例管理页工具栏「标签」facet（§3.4/§3.6）：
   - 选项按分类分组展示：组头=分类名（人数/场景/语种/噪声环境/设备类型）+ 色点 + 客户端聚合计数；
   - 单选：选中标签 → 用例流只显携带该标签的用例（「音箱」6 条）；再点=取消；
   - Command 搜索过滤标签名；无匹配「没有找到匹配的标签」；
   - 选中后工具栏右端出现「标签操作」下拉（收编①）；「重置」清空页内筛选（含标签）。

② 标签管理页分类筛选（§4.2，INT-507 落地核实）：
   - 左分类树点「人数」→ 右表只显 1人/2人/多人，所属分类列隐藏；
   - 点「未分类」→ 全量 13 个标签 + 所属分类列展示（未分类兜底）；
   - 标签搜索无匹配 → 「没有找到匹配的标签」空态。

失败落 tests/ui/artifacts/int594_tag_category_filter/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int594_tag_category_filter')

# 5273 = 本工作区 dev server（本卡验收起本 run 隔离 dev server）；env 可覆写
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


# ── 用例管理页定位工具 ────────────────────────────────
def _tag_facet_trigger(drv):
    """标签 facet 触发器（PopoverTrigger Button：标签 全部 / 标签 {tag}）。"""
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//button[contains(., '标签')][.//span[contains(., '全部') or contains(., '音箱') or contains(., '中文') or contains(., '手机') or contains(., '1人') or contains(., '会议')]]")) > 0)
    return drv.find_element(By.XPATH,
        "//button[contains(., '标签')][.//span[contains(., '全部') or contains(., '音箱') or contains(., '中文') or contains(., '手机') or contains(., '1人') or contains(., '会议')]]")


def _tag_popover(drv):
    """标签 facet Popover 内容（唯一 data-slot='popover-content' 容器）。"""
    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content']")) > 0)
    return drv.find_element(By.CSS_SELECTOR, "[data-slot='popover-content']")


def _tag_option(drv, name):
    """Popover 内标签选项按钮（plain button，文本=标签名）。"""
    p = _tag_popover(drv)
    btns = p.find_elements(By.XPATH, f".//button[contains(., '{name}')]")
    assert btns, f'标签选项「{name}」缺失'
    return btns[0]


def _tag_search_input(drv):
    return _tag_popover(drv).find_element(By.CSS_SELECTOR, "input[aria-label='搜索标签']")


def _case_checkboxes(drv):
    return drv.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']")


# ── ① 用例管理页标签 facet ────────────────────────────
def test_01_tag_facet_grouped_by_category_with_counts(drv):
    """§3.4：标签 facet 选项按分类分组（组头=分类名+色点+计数），单选入口。"""
    _login(drv)
    _goto(drv, '/testcases')

    _tag_facet_trigger(drv).click()
    time.sleep(0.6)
    pop = _tag_popover(drv)
    ptxt = pop.text

    # 组头=分类名（INT-487：GET /tags/by-category 口径）
    for cat in ['人数', '场景', '语种', '噪声环境', '设备类型']:
        assert cat in ptxt, f'facet 组头分类「{cat}」缺失：{ptxt[:400]}'

    # 各组标签选项齐全（13 个 mock 标签）
    for tag in ['1人', '2人', '多人', '客厅', '车内', '会议室',
                '中文', '英文', '安静', '嘈杂', '音乐', '音箱', '手机']:
        assert tag in ptxt, f'facet 选项「{tag}」缺失：{ptxt[:400]}'

    # 「音箱」选项带聚合计数（§3.4 客户端从已加载集聚合 = 6）
    speaker = _tag_option(drv, '音箱')
    stext = speaker.text
    assert '6' in stext, f'「音箱」选项计数缺失：{stext!r}'

    # 色点：选项按钮内圆点 span 存在且非空背景（数据驱动色）
    dots = speaker.find_elements(By.CSS_SELECTOR, "span.rounded-full")
    assert dots, f'「音箱」选项色点缺失：{stext!r}'
    _save_evidence('01_facet_grouped', drv)


def test_02_tag_single_select_filters_cases(drv):
    """§3.4/INT-592 单选：选中「音箱」→ 用例流只显携带该标签的用例。"""
    _login(drv)
    _goto(drv, '/testcases')

    _tag_facet_trigger(drv).click()
    time.sleep(0.6)
    _tag_option(drv, '音箱').click()
    time.sleep(1.0)

    # 触发器回显选中态「标签 音箱」
    trigger = _tag_facet_trigger(drv)
    assert '音箱' in trigger.text and '全部' not in trigger.text, \
        f'facet 触发器未回显「标签 音箱」：{trigger.text!r}'

    body = _body_text(drv)
    # 携带「音箱」标签的用例（tc-001/002/003/004/005/017）应保留
    for name in ['智能音箱-播放音乐-中文-客厅', '智能音箱-调节音量-2人',
                 '智能音箱-语音点歌-嘈杂环境', '智能音箱-闹钟设置-音乐干扰']:
        assert name in body, f'选中「音箱」后用例「{name}」应保留'
    # 不带「音箱」标签的用例（tc-006 车载-导航）应被过滤
    assert '车载-导航指令' not in body, '选中「音箱」后不应显示车载-导航用例'
    _save_evidence('02_single_select_filter', drv)


def test_03_tag_click_again_cancels(drv):
    """§3.4 单选：选中标签再点 = 取消（清空标签筛选，与重置同口径）。"""
    _login(drv)
    _goto(drv, '/testcases')

    _tag_facet_trigger(drv).click()
    time.sleep(0.6)
    _tag_option(drv, '音箱').click()
    time.sleep(0.8)

    _tag_facet_trigger(drv).click()
    time.sleep(0.6)
    _tag_option(drv, '音箱').click()
    time.sleep(0.8)

    trigger = _tag_facet_trigger(drv)
    assert '全部' in trigger.text, f'再点取消后应回「标签 全部」：{trigger.text!r}'
    body = _body_text(drv)
    assert '车载-导航指令' in body, '取消标签筛选后应恢复全量用例'
    _save_evidence('03_click_again_cancel', drv)


def test_04_tag_facet_command_search(drv):
    """§3.4：Command 搜索输入过滤标签名；无匹配空态。"""
    _login(drv)
    _goto(drv, '/testcases')

    _tag_facet_trigger(drv).click()
    time.sleep(0.6)
    box = _tag_search_input(drv)
    box.send_keys('音箱')
    time.sleep(0.6)
    ptxt = _tag_popover(drv).text
    assert '音箱' in ptxt, '搜索「音箱」后选项应保留'
    assert '1人' not in ptxt, f'搜索「音箱」后无关选项应过滤：{ptxt[:300]}'
    assert '人数' not in ptxt, f'搜索「音箱」后无关分组头应过滤：{ptxt[:300]}'

    box.clear()
    box.send_keys('zzz-不存在标签')
    time.sleep(0.6)
    ptxt = _tag_popover(drv).text
    assert '没有找到匹配的标签' in ptxt, f'搜索无匹配空态缺失：{ptxt[:200]}'
    _save_evidence('04_command_search', drv)


def test_05_tag_reset_clears_filter(drv):
    """§3.4：「重置」清空页内筛选（含标签）。"""
    _login(drv)
    _goto(drv, '/testcases')

    _tag_facet_trigger(drv).click()
    time.sleep(0.6)
    _tag_option(drv, '音箱').click()
    time.sleep(0.8)
    assert '标签' in _tag_facet_trigger(drv).text and '全部' not in _tag_facet_trigger(drv).text

    # 页内筛选开启 → 「重置」钮出现
    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '重置')]")) > 0)
    drv.find_element(By.XPATH, "//button[contains(., '重置')]").click()
    time.sleep(0.8)

    trigger = _tag_facet_trigger(drv)
    assert '全部' in trigger.text, f'重置后标签应回「全部」：{trigger.text!r}'
    body = _body_text(drv)
    assert '车载-导航指令' in body, '重置后应恢复全量用例'
    _save_evidence('05_reset_linkage', drv)


def test_06_tag_actions_dropdown_on_select(drv):
    """§3.6 收编①：标签 facet 单选选中态后工具栏右端出现「标签操作」下拉三项。"""
    _login(drv)
    _goto(drv, '/testcases')

    # 未选标签时不出现
    assert len(drv.find_elements(By.XPATH, "//button[contains(., '标签操作')]")) == 0

    _tag_facet_trigger(drv).click()
    time.sleep(0.6)
    _tag_option(drv, '中文').click()
    time.sleep(0.8)

    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '标签操作')]")) > 0)
    trigger = drv.find_element(By.XPATH, "//button[contains(., '标签操作')]")
    trigger.click()
    time.sleep(0.5)

    items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']")
    texts = '\n'.join(i.text for i in items)
    for label in ['编辑标签', '删除标签', '复制标签下用例']:
        assert label in texts, f'标签操作下拉缺「{label}」：{texts}'
    _save_evidence('06_tag_actions_dropdown', drv)


# ── ② 标签管理页分类筛选（§4.2 核实）───────────────────
def test_07_tags_page_category_tree_filters(drv):
    """§4.2：左分类树点「人数」→ 右表按分类过滤（1人/2人/多人），所属分类列隐藏。"""
    _login(drv)
    _goto(drv, '/TagManagement')

    drv.find_element(By.XPATH, "//button[contains(., '人数')]").click()
    time.sleep(0.9)

    body = _body_text(drv)
    assert '共 3 个标签' in body, f'「人数」分类右卡计数缺失：{body[-400:]}'
    for tag in ['1人', '2人', '多人']:
        assert tag in body, f'「人数」分类下标签「{tag}」缺失'
    # 所属分类列隐藏：表头仅 标签/描述/操作
    headers = [h.text for h in drv.find_elements(By.CSS_SELECTOR, 'table thead th')]
    assert '所属分类' not in headers, f'分类选中态所属分类列应隐藏：{headers}'
    _save_evidence('07_category_tree_filter', drv)


def test_08_tags_page_uncategorized_fallback(drv):
    """§4.2 未分类兜底：点「未分类」→ 全量 13 标签 + 所属分类列展示。"""
    _login(drv)
    _goto(drv, '/TagManagement')

    drv.find_element(By.XPATH, "//button[contains(., '未分类')]").click()
    time.sleep(0.9)

    body = _body_text(drv)
    assert '共 13 个标签' in body, f'「未分类」右卡计数缺失：{body[-400:]}'
    headers = [h.text for h in drv.find_elements(By.CSS_SELECTOR, 'table thead th')]
    assert headers == ['标签', '所属分类', '描述', '操作'], f'未分类态表头异常：{headers}'
    # 分类列内容（含所属分类名示例）
    assert '所属分类' in body and '设备类型' in body, '未分类态应展示所属分类列'
    _save_evidence('08_uncategorized_fallback', drv)


def test_09_tags_page_empty_state(drv):
    """§4.2 空态：标签搜索无匹配 → 「没有找到匹配的标签」。"""
    _login(drv)
    _goto(drv, '/TagManagement')

    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索标签']")
    box.send_keys('zzz-不存在标签')
    WebDriverWait(drv, 10).until(
        lambda d: '没有找到匹配的标签' in _body_text(drv))
    _save_evidence('09_tags_empty_state', drv)


# ── 无抛错级 console ──────────────────────────────────
def test_10_no_console_severe_errors(drv):
    """两个页面均无 console SEVERE 报错。"""
    _login(drv)
    for path in ['/testcases', '/TagManagement']:
        _goto(drv, path)
        time.sleep(1.0)
        errors = [e for e in drv.get_log('browser')
                  if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', ''))]
        assert not errors, f'{path} console SEVERE 报错：{errors[:5]}'
    _save_evidence('10_no_console_errors', drv)
