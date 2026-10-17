# -*- coding: utf-8 -*-
"""INT-595 用例管理页走查补齐 浏览器走查（真实 Chrome headless，按 test_ui_23 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273，env 可覆写），
按 INT-595 交付清单（React页面工程师C commit a7a29f83）逐项断言：

① 标签操作下拉（11_用例域.md §3.6 收编①）：标签 facet 单选「音箱」→ 工具栏右端「标签操作」出现；
   编辑标签（toast「编辑标签「音箱」（演示）」）/ 删除标签（级联确认「该操作将级联删除标签下的
   {n} 个用例，不可恢复！」→ 确定 → toast「标签已删除」）/ 复制标签下用例（确认含「同时复制到新分组」
   Checkbox，复制后将生成新标签：音箱_copy → 确定 → toast「已复制标签下用例」）。
② 音频播放器（§5.2）：有音频用例 → 预览 → 配置弹窗（播放模式 RadioGroup + 偏移量）→「开始试听」→
   播放器 stage（标题「测试用例预览｜{name} 音频」/ 播放进度 Slider / {current}/{duration} /
   播放·暂停切换 / 停止 / 播放设备区「播放设备（浏览器播放）」/「返回试听配置」双向切换）。
③ 预览置灰（§3.3.2）：tc-014 临时-接口稳定性回归（audioCount=0）预览钮 aria-disabled + Tooltip
   「该测试用例没有关联音频文件」，其余四钮可用。
④ 空态三态（§3.3 INT-592 文案）：搜索无结果 →「没有找到符合条件的测试用例」+「尝试清空「分组」「标签」筛选」；
   回收站态无匹配 →「回收站为空」；空态下提供「+ 新增用例」入口（回收站空态不出现）。
⑤ isFetching 降透明不消失（§3.3.3）：搜索触发 refetch 期间列表容器出现 opacity-60（降透明），
   列表不消失（上一帧保留），refetch 完成后恢复。
⑥ 批量浮条联动：勾选用例 → 底部浮条「{n} 个用例已选择」+ 九件套出现；标签筛选选中态下
   「标签操作」下拉与批量浮条共存不冲突。

失败落 tests/ui/artifacts/int595_testcases_walkthrough/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int595_testcases_walkthrough')

# 5273 = 本工作区常驻 dev server；env 可覆写（本卡验收起本 run 隔离 dev server 时覆写为独立端口）
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
def _search_input(drv):
    return drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索用例']")


def _tag_facet_trigger(drv):
    """标签 facet 触发器（PopoverTrigger Button：「标签 全部 / 标签 {tag}」）。"""
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//button[contains(., '标签')][.//span[contains(., '全部') or contains(., '音箱') or contains(., '中文') or contains(., '手机') or contains(., '会议')]]")) > 0)
    return drv.find_element(By.XPATH,
        "//button[contains(., '标签')][.//span[contains(., '全部') or contains(., '音箱') or contains(., '中文') or contains(., '手机') or contains(., '会议')]]")


def _tag_option(drv, name):
    """标签 facet Popover 内选项按钮（plain button，文本=标签名）。"""
    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content']")) > 0)
    contents = drv.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content']")
    for c in contents:
        btns = c.find_elements(By.XPATH, f".//button[contains(., '{name}')]")
        if btns:
            return btns[0]
    raise AssertionError(f'标签选项「{name}」缺失')


def _tag_actions_trigger(drv):
    """工具栏右端「标签操作」下拉触发器。"""
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//button[contains(., '标签操作')]")) > 0)
    return drv.find_element(By.XPATH, "//button[contains(., '标签操作')]")


def _dropdown_item(drv, text):
    """DropdownMenu 内容项（data-slot='dropdown-menu-item'）。"""
    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-content']")) > 0)
    for c in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-content']"):
        items = c.find_elements(By.XPATH, f".//*[@data-slot='dropdown-menu-item'][contains(., '{text}')]")
        if items:
            return items[0]
    raise AssertionError(f'下拉项「{text}」缺失')


def _confirm_dialog(drv):
    """AlertDialog（ConfirmDialog）容器（等待有文本的内容元素——弹层动效落位后读正文）。"""
    deadline = time.time() + 8
    while time.time() < deadline:
        els = drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
        for el in els:
            if el.text.strip():
                return el
        time.sleep(0.2)
    assert els, '确认弹窗未出现'
    return els[0]


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _toast_text(drv):
    time.sleep(0.4)
    toasts = drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]")
    if not toasts:
        return ''
    return '\n'.join(t.text for t in toasts)


def _bulk_bar(drv):
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")) > 0)
    return drv.find_element(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")


def _select_case(drv, index=0):
    boxes = drv.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']")
    assert boxes, '未找到用例勾选 checkbox'
    boxes[index].click()
    time.sleep(0.6)
    return boxes[index]


# ── ① 标签操作下拉（§3.6 收编①）────────────────────────
def test_01_tag_actions_dropdown_edit_delete_copy(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')

    # 无标签筛选时不出现「标签操作」
    assert len(drv.find_elements(By.XPATH, "//button[contains(., '标签操作')]")) == 0, \
        '未选标签时不应出现标签操作入口'

    # 标签 facet 选「音箱」
    _tag_facet_trigger(drv).click()
    time.sleep(0.5)
    _tag_option(drv, '音箱').click()
    time.sleep(0.8)

    # 选中态后工具栏右端出现「标签操作」
    trigger = _tag_actions_trigger(drv)
    trigger.click()
    time.sleep(0.5)

    # 编辑标签 → 演示 toast
    _dropdown_item(drv, '编辑标签').click()
    t = _toast_text(drv)
    assert '编辑标签「音箱」（演示）' in t, f'编辑标签 toast 缺失：{t}'

    # 删除标签 → 级联确认
    _tag_actions_trigger(drv).click()
    time.sleep(0.5)
    _dropdown_item(drv, '删除标签').click()
    conf = _confirm_dialog(drv)
    ctext = conf.text
    assert '删除标签' in ctext, f'删除确认标题缺失：{ctext[:120]}'
    assert '确定要删除标签「音箱」吗？' in ctext, f'删除确认文案缺失：{ctext[:200]}'
    assert '该操作将级联删除标签下的 6 个用例，不可恢复！' in ctext, \
        f'级联删除计数文案缺失：{ctext[:200]}'
    _save_evidence('01a_delete_confirm', drv)
    conf.find_element(By.XPATH, ".//button[contains(., '删除')]").click()
    time.sleep(0.8)
    t = _toast_text(drv)
    assert '标签已删除' in t and '已级联删除 6 个用例' in t, f'删除 toast 缺失：{t}'

    # 复制标签下用例 → 确认含「同时复制到新分组」→ 确定
    _tag_actions_trigger(drv).click()
    time.sleep(0.5)
    _dropdown_item(drv, '复制标签下用例').click()
    conf = _confirm_dialog(drv)
    ctext = conf.text
    assert '复制后将生成新标签：音箱_copy' in ctext, f'复制确认文案缺失：{ctext[:200]}'
    assert '同时复制到新分组' in ctext, f'「同时复制到新分组」Checkbox 缺失：{ctext[:200]}'
    _save_evidence('01b_copy_confirm', drv)
    conf.find_element(By.XPATH, ".//button[contains(., '复制')]").click()
    time.sleep(0.8)
    t = _toast_text(drv)
    assert '已复制标签下用例' in t and '新标签：音箱_copy' in t, f'复制 toast 缺失：{t}'


# ── ② 音频播放器（§5.2）────────────────────────────────
def test_02_audio_player_config_and_playing(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')

    # 找第一个有音频用例（默认分组卡 g1 展开，tc-001 有音频）
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']:not([aria-disabled])")) > 0)
    preview = drv.find_element(By.CSS_SELECTOR, "button[aria-label='预览音频']:not([aria-disabled])")
    preview.click()
    time.sleep(0.8)

    # 配置弹窗：播放模式 + 偏移量 + 开始试听
    dlg = _dialog_by_title(drv, '音频试听配置')
    txt = dlg.text
    assert '播放模式' in txt and '浏览器播放' in txt and '实验室播放' in txt, \
        f'播放模式缺失：{txt[:200]}'
    assert '偏移量（秒）' in txt, '偏移量输入缺失'
    assert '开始试听' in txt, '开始试听按钮缺失'
    _save_evidence('02a_config_dialog', drv)

    # 开始试听 → 播放器 stage
    dlg.find_element(By.XPATH, ".//button[contains(., '开始试听')]").click()
    time.sleep(0.8)
    dlg = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    txt = dlg.text
    assert '测试用例预览｜' in txt and '音频' in txt, f'播放器标题缺失：{txt[:200]}'
    # 进度 Slider：aria-label='播放进度' 暴露在元素属性（非可见文本）
    sliders = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='slider'][aria-label='播放进度']")
    assert sliders, '进度 Slider（aria-label 播放进度）缺失'
    assert '播放' in txt and '停止' in txt, '播放/停止按钮缺失'
    assert '播放设备（浏览器播放）' in txt, f'播放设备区缺失：{txt[:200]}'
    assert '音频接口 A (通道 1) [干声]' in txt, '勾选设备未显示'
    assert '返回试听配置' in txt, '返回按钮缺失'
    _save_evidence('02b_player', drv)

    # 播放 → 暂停 切换
    play_btn = drv.find_element(By.CSS_SELECTOR, "button[aria-label='播放']")
    play_btn.click()
    time.sleep(0.5)
    assert drv.find_elements(By.CSS_SELECTOR, "button[aria-label='暂停']"), '播放后应为暂停态'
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='暂停']").click()
    time.sleep(0.5)
    assert drv.find_elements(By.CSS_SELECTOR, "button[aria-label='播放']"), '暂停后应回播放态'
    _save_evidence('02c_play_pause', drv)

    # 停止 → 进度归零
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='停止']").click()
    time.sleep(0.5)
    dlg = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    assert '00:00 / 00:42' in dlg.text, f'停止后进度未归零：{dlg.text[-200:]}'

    # 返回试听配置 → 双向切换回配置态
    drv.find_element(By.XPATH, "//button[contains(., '返回试听配置')]").click()
    time.sleep(0.5)
    dlg = _dialog_by_title(drv, '音频试听配置')
    assert '开始试听' in dlg.text, '返回配置态后「开始试听」应可见'
    _save_evidence('02d_back_to_config', drv)


# ── ③ 预览置灰 + Tooltip（§3.3.2）───────────────────────
def test_03_preview_disabled_tooltip(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')

    # 搜索定位 tc-014（临时-接口稳定性回归，audioCount=0）
    _search_input(drv).send_keys('临时-接口稳定性回归')
    time.sleep(1.2)

    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']")) > 0)
    preview = drv.find_element(By.CSS_SELECTOR, "button[aria-label='预览音频']")
    assert preview.get_attribute('aria-disabled') == 'true', 'tc-014 预览钮应 aria-disabled'
    assert preview.get_attribute('disabled') == 'true' or preview.get_attribute('disabled') == 'true', \
        'tc-014 预览钮应 disabled'
    _save_evidence('03_preview_disabled', drv)

    # 其余四钮可用
    for label in ['复制用例', '收藏', '编辑用例', '删除用例']:
        btns = drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='{label}']")
        assert btns and not btns[0].get_attribute('disabled'), f'「{label}」应可用'
    # 确认 tc-014 名称与无音频 Tooltip（hover 后 TooltipContent）
    body = _body_text(drv)
    assert '临时-接口稳定性回归' in body, '搜索后未定位到 tc-014'
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(drv).move_to_element(preview).perform()
    time.sleep(0.8)
    tooltips = drv.find_elements(By.CSS_SELECTOR, "[data-slot='tooltip-content']")
    tooltip_texts = '\n'.join(t.text for t in tooltips)
    assert '该测试用例没有关联音频文件' in tooltip_texts, \
        f'无音频 Tooltip 缺失：{tooltip_texts or "(无 tooltip)"}'
    _save_evidence('03b_tooltip', drv)


# ── ④ 空态三态（§3.3 INT-592 文案）──────────────────────
def test_04_empty_states_no_match_and_trash(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')

    # 筛选无匹配：搜索无结果
    _search_input(drv).send_keys('zzz-不存在-用例')
    time.sleep(1.2)
    body = _body_text(drv)
    assert '没有找到符合条件的测试用例' in body, f'筛选无匹配空态缺失：{body[-300:]}'
    assert '尝试清空「分组」「标签」筛选' in body, f'空态描述缺失：{body[-300:]}'
    assert '+ 新增用例' in body, '空态下应提供新增入口'
    _save_evidence('04a_no_match_empty', drv)

    # 回收站态无匹配 → 「回收站为空」
    _search_input(drv).clear()
    time.sleep(1.0)
    drv.find_element(By.CSS_SELECTOR, "button[title='回收站']").click()
    time.sleep(1.2)
    _search_input(drv).send_keys('zzz-不存在-用例')
    time.sleep(1.2)
    body = _body_text(drv)
    assert '回收站为空' in body, f'回收站空态缺失：{body[-300:]}'
    assert '+ 新增用例' not in body, '回收站空态不应出现新增入口'
    _save_evidence('04b_trash_empty', drv)


# ── ⑤ isFetching 降透明不消失（§3.3.3）─────────────────
def test_05_is_fetching_dim_not_disappear(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']")) > 0)

    # 搜索触发 refetch：进入页面后查询已就绪（staleTime 15s 内首次已缓存），
    # 输入触发新 queryKey → 在页内轮询捕获 opacity-60（降透明）且列表容器仍在
    _search_input(drv).send_keys('智能音箱')
    # 500ms debounce + 120ms mock 延迟：轮询 2s 捕获降透明态
    caught = drv.execute_script('''
      const start = Date.now();
      let seen = false;
      while (Date.now() - start < 2000) {
        const el = document.querySelector('.space-y-3.transition-opacity');
        if (el) {
          if (el.classList.contains('opacity-60')) { seen = true; break; }
        }
        // 等待渲染帧
        await new Promise(r => setTimeout(r, 30));
      }
      return seen;
    ''')
    assert caught, '搜索 refetch 期间未捕获 opacity-60 降透明态'
    # refetch 完成后恢复，且列表未消失（用例卡仍在）
    time.sleep(1.2)
    boxes = drv.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']")
    assert boxes, 'refetch 后列表不应消失'
    root = drv.find_element(By.CSS_SELECTOR, ".space-y-3.transition-opacity")
    assert 'opacity-60' not in root.get_attribute('class'), 'refetch 完成后应恢复全透明'
    _save_evidence('05_dim_recover', drv)


# ── ⑥ 批量浮条联动 ─────────────────────────────────────
def test_06_bulk_bar_linkage_with_tag_actions(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')

    # 标签筛选选中「音箱」→ 标签操作下拉存在；勾选用例 → 批量浮条出现（共存）
    _tag_facet_trigger(drv).click()
    time.sleep(0.5)
    _tag_option(drv, '音箱').click()
    time.sleep(1.0)
    assert _tag_actions_trigger(drv), '标签筛选态下「标签操作」下拉应存在'

    _select_case(drv, 0)
    bar = _bulk_bar(drv)
    bt = bar.text
    assert '个用例已选择' in bt, f'批量浮条计数缺失：{bt}'
    for label in ['批量设置专属参数', '批量设置播放设备', '批量设置声压', '批量设置噪声', '刷新参考参数']:
        assert label in bt, f'批量浮条缺「{label}」'
    _save_evidence('06_bulk_bar_with_tag', drv)

    # 标签操作下拉在勾选态下仍可打开（互不冲突）
    _tag_actions_trigger(drv).click()
    time.sleep(0.5)
    assert _dropdown_item(drv, '复制标签下用例'), '勾选态下标签操作下拉应可打开'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)

    # 清除筛选 → 重置；回收站态批量浮条不含批量设置（INT-587 口径复核）
    drv.find_element(By.CSS_SELECTOR, "button[title='回收站']").click()
    time.sleep(1.0)
    _select_case(drv, 0)
    bar = _bulk_bar(drv)
    bt = bar.text
    assert '批量恢复' in bt and '批量彻底删除' in bt, f'回收站浮条应含恢复/彻底删除：{bt}'
    for banned in ['批量设置专属参数', '批量设置播放设备', '批量设置声压', '批量设置噪声']:
        assert banned not in bt, f'回收站态不应出现「{banned}」'
    _save_evidence('06b_trash_bulk_bar', drv)


# ── 无抛错级 console ────────────────────────────────────
def test_07_no_console_severe_errors(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    time.sleep(1.0)
    errors = [e for e in drv.get_log('browser')
              if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', ''))]
    assert not errors, f'页面 console SEVERE 报错：{errors[:5]}'
    _save_evidence('07_no_console_errors', drv)
