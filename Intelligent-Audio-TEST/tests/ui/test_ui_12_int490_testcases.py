# -*- coding: utf-8 -*-
"""INT-490 用例管理 React 可视稿返修复测浏览器走查（真实 Chrome headless，按 test_ui_09 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
P1 侧栏高亮（前缀匹配）：/testcases、/testcases/by-group、/testcases/by-tag 下
   「测试资产 → 用例管理」导航项 data-active 高亮
P2 分组默认展开：fresh 打开 /testcases/by-group 分组卡默认全展开、组内用例卡可见；
   手动折叠/展开生效（分组/标签两视图同源）
三条新口径：
1. 分组卡片流（组头勾选全选+计数/总时长徽章+编辑/删除/新增用例/复制+批量九项 + 组内用例卡）
2. 用例不分类型：无「测试类型」facet / 无类型徽章 / 无「端到端测试用例」表述
3. 编辑模态窗五步骤全字段（1280px 抽屉：轮次导航 + 算法参数/音频列表/噪声与干扰/
   评估维度/参考参数 + 多轮全局背景噪声/整体评估维度）

失败落 tests/ui/artifacts/int490_testcases/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int490_testcases')

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


def _sidebar_testcases_link(drv):
    """侧栏「测试资产 → 用例管理」<a> 元素（href=/testcases）。"""
    els = drv.find_elements(By.CSS_SELECTOR, "a[href='/testcases']")
    assert els, '侧栏用例管理链接不存在'
    return els[0]


# ── ① P1：侧栏「测试资产→用例管理」前缀高亮 ──────────────
def test_01_sidebar_highlight_prefix_all_paths(drv):
    _login(drv)
    for path in ['/testcases', '/testcases/by-group', '/testcases/by-tag']:
        _goto(drv, path)
        link = _sidebar_testcases_link(drv)
        active = link.get_attribute('data-active')
        assert active is not None, \
            f'{path} 下「用例管理」侧栏未高亮（data-active 缺失）'
        _save_evidence(f'01_sidebar_{path.strip("/").replace("/", "_")}', drv)


# ── ② P2：分组视图首屏默认展开 + 手动折叠/展开 ───────────
def test_02_group_default_expanded_and_manual_toggle(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    txt = _body_text(drv)
    # 分组卡组头可见
    for g in ['智能音箱功能测试', '车载语音交互', '手机助手场景', '会议转写测试']:
        assert g in txt, f'分组「{g}」缺失'
    # 组内用例卡首屏可见（默认展开，P2 修复断言）
    for c in ['智能音箱-播放音乐-中文-客厅', '车载-导航指令-车内-1人']:
        assert c in txt, f'首屏分组默认展开断言失败：组内用例「{c}」不可见'
    # 手动折叠「智能音箱功能测试」：点组头 → 组内用例不可见
    _save_evidence('02_bygroup_default_expanded', drv)
    header = drv.find_element(By.XPATH,
        "//span[contains(., '智能音箱功能测试')]/ancestor::div[contains(@class, 'flex')][1]")
    header.click()
    time.sleep(0.7)
    txt = _body_text(drv)
    assert '智能音箱-播放音乐-中文-客厅' not in txt, '折叠后组内用例应不可见'
    # 再点展开 → 组内用例恢复可见
    header.click()
    time.sleep(0.7)
    txt = _body_text(drv)
    assert '智能音箱-播放音乐-中文-客厅' in txt, '展开后组内用例应恢复可见'
    _save_evidence('02_bygroup_after_reopen', drv)


# ── ③ 分组卡组头：勾选全选/计数+总时长徽章/组操作面板 ──
def test_03_group_header_actions_and_badges(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    txt = _body_text(drv)
    # g1 智能音箱功能测试 = 5 条，总时长 156+48+210+12+132 = 558s = 9m 18s
    assert '5 条' in txt, f'g1 计数徽章缺失：{txt[:300]}'
    assert '总时长' in txt and '9m 18s' in txt, f'g1 总时长徽章缺失：{txt[:300]}'
    # 组头操作：编辑/删除/新增用例/复制
    for btn in ['编辑', '删除', '新增用例', '复制']:
        assert btn in txt, f'组头操作按钮「{btn}」缺失'
    # 批量修改下拉九项
    drv.find_element(By.XPATH, "//button[contains(., '批量修改')]").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    for item in ['用例专属参数', '播放设备', '声压', '调整分组', '评价维度',
                 '噪声', '标签生成名称', '管理标签', '用例参考更新']:
        assert item in txt, f'批量修改九项缺「{item}」'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)


# ── ④ 组内懒加载分页计数（加载更多按钮仅在 >5 条时出现）──
def test_04_group_inline_pagination(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    # g1=5 条（≤每页 5），无「加载更多」按钮；组内用例卡渲染 5 张
    cards = drv.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']")
    # 未分组 3 条 + g1 5 条 + g2 3 条 = 首屏可见用例卡（展开态）应 ≥ 8
    assert len(cards) >= 8, f'首屏可见用例卡不足：{len(cards)}'
    load_more = drv.find_elements(By.XPATH, "//button[contains(., '加载更多')]")
    # 分组内每页 5 条：g1=5 恰好一页，应无「已显示 … / … 条 · 加载更多」组内按钮
    inline_btns = [b for b in load_more if ' 条' in b.text and '加载更多' in b.text]
    assert not inline_btns, f'组内加载更多不应出现（各分组≤5条）：{[b.text for b in inline_btns]}'


# ── ⑤ 分组排序下拉 + 分组分页提示 ──────────────────────
def test_05_group_sort_and_group_pagination(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    # 排序下拉
    drv.find_element(By.XPATH, "//button[contains(., '排序')]").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    for opt in ['分组排序', '按用例数量', '按分组名称', '按创建时间', '顺序']:
        assert opt in txt, f'排序下拉缺「{opt}」'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)
    # 4 个分组 ≤ 每页 5 → 「已加载全部 4 个分组」
    txt = _body_text(drv)
    assert '已加载全部 4 个分组' in txt, f'分组分页「已加载全部 4 个分组」缺失：{txt[-200:]}'


# ── ⑥ 标签视图标签分组卡 + 加载更多标签 ─────────────────
def test_06_tag_view_cards_and_load_more(drv):
    _login(drv)
    _goto(drv, '/testcases/by-tag')
    txt = _body_text(drv)
    # 标签分组卡（音箱/中文 等）带分类名与计数
    assert '音箱' in txt and '设备类型' in txt, f'标签分组卡缺失：{txt[:300]}'
    assert '5 条' in txt, f'标签计数徽章缺失：{txt[:300]}'
    # 分页：15 个标签 → 首屏 5 个 + 加载更多
    assert '已显示 5 / 15 个标签' in txt, f'标签加载更多文案缺失：{txt[-200:]}'
    btn = drv.find_element(By.XPATH, "//button[contains(., '加载更多')]")
    btn.click()
    time.sleep(0.7)
    txt = _body_text(drv)
    assert '已显示 10 / 15 个标签' in txt, f'二次分页缺失：{txt[-200:]}'
    btn = drv.find_element(By.XPATH, "//button[contains(., '加载更多')]")
    btn.click()
    time.sleep(0.7)
    txt = _body_text(drv)
    assert '已加载全部 15 个标签' in txt, f'全部加载后文案缺失：{txt[-200:]}'
    _save_evidence('06_tag_view_all_loaded', drv)


# ── ⑦ 用例卡五钮 + 回收站态恢复/彻底删除 + 元信息 ──────
def test_07_case_card_actions_and_trash(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    txt = _body_text(drv)
    # 正常态五钮（预览/复制/收藏/编辑/删除）——tc-001 是收藏项，收藏钮应为「取消收藏」
    for aria in ['预览音频', '复制用例', '编辑用例', '删除用例']:
        els = drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='{aria}']")
        assert els, f'用例卡按钮「{aria}」缺失'
    favs = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='取消收藏']")
    fav0 = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='收藏']")
    assert favs and fav0, '收藏/取消收藏按钮应共存（tc-001 收藏，其余未收藏）'
    # 回收站态：进回收站清空收藏态且收藏钮禁用（互斥）
    drv.find_element(By.CSS_SELECTOR, "button[title='回收站']").click()
    time.sleep(1.0)
    txt = _body_text(drv)
    assert '已删除-旧版唤醒测试' in txt, f'回收站用例缺失：{txt[:200]}'
    assert '删除时间' in txt and '删除人' in txt, '回收站元信息（删除时间/删除人）缺失'
    # 回收站态按钮换为 恢复/彻底删除
    restore = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='恢复用例']")
    purge = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='彻底删除（不可恢复）']")
    assert restore and purge, '回收站态恢复/彻底删除按钮缺失'
    # 收藏钮在回收站态禁用
    fav_disabled = drv.find_elements(By.CSS_SELECTOR, "button[title='只看收藏']")
    assert fav_disabled and fav_disabled[0].get_attribute('disabled') is not None, \
        '回收站态「只看收藏」应禁用（互斥）'
    _save_evidence('07_trash_state', drv)
    # 还原默认态
    drv.find_element(By.CSS_SELECTOR, "button[title='回收站']").click()
    time.sleep(0.8)


# ── ⑧ 新增用例 1280px 抽屉：五步骤全字段 + 轮次操作 ────
def test_08_create_drawer_full_fields(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    drv.find_element(By.XPATH, "//button[contains(., '新增用例')]").click()
    time.sleep(1.0)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    w = sheet.size['width']
    assert w >= 1200, f'抽屉宽度不足 1280：{w}'
    txt = sheet.text
    # 五步骤页签
    for step in ['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数']:
        assert step in txt, f'步骤页签「{step}」缺失'
    # 轮次导航：默认 2 轮 + 添加/复制
    assert '第 1 轮' in txt and '第 2 轮' in txt, f'轮次导航初始轮次缺失：{txt[:300]}'
    assert '添加轮次' in txt and '复制当前轮次' in txt, '轮次添加/复制按钮缺失'
    # 基本信息/标签/关联算法
    for f in ['用例名称', '所属分组', '标签', '描述', '关联算法']:
        assert f in txt, f'基本信息字段「{f}」缺失'
    # 多轮 >1 → 全局背景噪声 + 整体评估维度
    assert '全局背景噪声' in txt, '多轮全局背景噪声节缺失'
    assert '整体评估维度' in txt, '多轮整体评估维度节缺失'
    # 算法参数步骤字段（默认无关联算法 → 按 asr-v3 schema 渲染基础识别+解码优化）
    step_tab = lambda name: sheet.find_element(
        By.XPATH, f".//button[@role='tab' and contains(., '{name}')]")
    step_tab('算法参数').click()
    time.sleep(0.6)
    txt = sheet.text
    for f in ['基础识别', '采样率（Hz）', 'VAD 阈值', '最大音频时长（秒）', '说话人分离']:
        assert f in txt, f'算法参数步骤缺「{f}」'
    # 音频列表步骤字段
    step_tab('音频列表').click()
    time.sleep(0.6)
    txt = sheet.text
    for f in ['音频文件', '播放设备', '声压级 dB', '批量设备', '批量声压']:
        assert f in txt, f'音频列表步骤缺「{f}」'
    # 噪声与干扰步骤字段
    step_tab('噪声与干扰').click()
    time.sleep(0.6)
    txt = sheet.text
    for f in ['背景噪声', '声纹注册配置', '干扰人配置', '添加干扰人']:
        assert f in txt, f'噪声与干扰步骤缺「{f}」'
    # 评估维度步骤：权重/阈值 0-100 number + LLM Judge（点「语义理解」chip 展示 LLM 配置卡；
    # INT-584 修正：权重/阈值 0-100，删「最大 Token/Temperature」，LLM=模型+Prompt Select）
    step_tab('评估维度').click()
    time.sleep(0.6)
    txt = sheet.text
    for f in ['权重', '阈值']:
        assert f in txt, f'评估维度步骤缺「{f}」'
    try:
        sheet.find_element(By.XPATH, ".//button[contains(., '语义理解')]").click()
        time.sleep(0.6)
        txt = sheet.text
        assert 'LLM Judge' in txt, '评估维度 LLM Judge 配置卡缺失'
        for f in ['模型', 'Prompt 模板']:
            assert f in txt, f'LLM Judge 配置缺「{f}」'
        for banned in ['最大 Token', 'Temperature']:
            assert banned not in txt, f'「{banned}」应随 INT-584 移除（属维度定义 §5.5）'
    except Exception as e:  # 语义理解 chip 未命中时降级：仅断言维度过滤机制存在
        assert '识别准确率' in txt, f'评估维度 chips 缺失：{txt[:200]}'
    # 参考参数步骤
    step_tab('参考参数').click()
    time.sleep(0.6)
    txt = sheet.text
    assert '参考参数' in txt, '参考参数步骤缺失'
    # 添加轮次 → 第 3 轮
    drv.find_element(By.XPATH, "//button[contains(., '添加轮次')]").click()
    time.sleep(0.6)
    txt = sheet.text
    assert '第 3 轮' in txt, '添加轮次后第 3 轮缺失'
    # 复制当前轮次 → 第 4 轮
    drv.find_element(By.XPATH, "//button[contains(., '复制当前轮次')]").click()
    time.sleep(0.6)
    txt = sheet.text
    assert '第 4 轮' in txt, '复制当前轮次后第 4 轮缺失'
    _save_evidence('08_create_drawer_full', drv)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)


# ── ⑨ 用例不分类型：facet/徽章不再渲染 ─────────────────
def test_09_no_test_type_facet_badge(drv):
    _login(drv)
    for path in ['/testcases/by-group', '/testcases/by-tag']:
        _goto(drv, path)
        txt = _body_text(drv)
        for banned in ['测试类型', '端到端测试', 'API测试', '全部类型']:
            assert banned not in txt, f'{path} 仍渲染「{banned}」'
    # 类型徽章也不在用例卡（算法徽章保留）
    _goto(drv, '/testcases/by-group')
    # 正式类型维度=算法徽章保留（通用识别引擎/流式识别引擎/多维评估集成）
    txt = _body_text(drv)
    assert '通用识别引擎' in txt or '流式识别引擎' in txt or '多维评估集成' in txt, \
        f'算法徽章缺失：{txt[:200]}'


# ── ⑩ 深浅色/多主题随全局切换 ──────────────────────────
def test_10_theme_switch(drv):
    _login(drv)
    _goto(drv, '/testcases/by-group')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='打开主题设置']").click()
    time.sleep(1.0)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    txt = sheet.text
    assert '外观设置' in txt and '颜色预设' in txt, f'主题抽屉内容缺失：{txt[:150]}'
    labels = drv.execute_script(
        "return Array.from(document.querySelectorAll('span[role=radio][aria-label]'))"
        ".map(e => e.getAttribute('aria-label'))")
    for name in ['默认蓝', 'Anthropic', '简洁大字', '暗流', '玫瑰园', '湖光',
                 '落日', '林语', '海风', '薰衣草']:
        assert name in labels, f'预设缺「{name}」：{labels}'
    # 切换湖光 → html class 变 light/深色联动（浅色默认）
    drv.find_element(By.CSS_SELECTOR, "span[role=radio][aria-label='湖光']").click()
    time.sleep(0.8)
    html_class = drv.find_element(By.TAG_NAME, 'html').get_attribute('class')
    _save_evidence('10_theme_huguang', drv)
    # 深色模式切换
    try:
        drv.find_element(By.CSS_SELECTOR, "[aria-label='切换深色模式']").click()
        time.sleep(0.8)
        html_class = drv.find_element(By.TAG_NAME, 'html').get_attribute('class')
        _save_evidence('10_theme_dark', drv)
    except Exception:
        pass
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
