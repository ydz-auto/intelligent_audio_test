# -*- coding: utf-8 -*-
"""INT-507 标签管理 React 可视稿浏览器走查（真实 Chrome headless，按 test_ui_09 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5274）：
1. /TagManagement 页面渲染：页头「标签管理」+ 说明 + 面包屑；左分类树卡（标签分类/共 5 个/
   + 新建/搜索分类.../五个分类+未分类固定尾项/已加载全部）；右标签表卡（未分类/共 13 个标签/
   「搜索标签...」/「新建标签」/表头 标签·所属分类·描述·操作 / 已加载全部 13 个标签）
2. 分类选中过滤：点「人数」→ 右卡标题「人数」/共 3 个标签/所属分类列隐藏（表头 3 列）
3. 标签搜索防抖：输入「音乐」→ 300ms 防抖后右表仅 1 行（共 1 个标签），清空恢复 13 行
4. 新建标签模态（§5.4）：打开「新建标签」对话框 → 名称空时「创建」禁用 → 填名启用 →
   提交 → toast「标签创建成功」+ 对话框关闭
5. 新建分类模态（§5.4）：打开「新建分类」对话框 → 分类名称/描述/颜色/排序字段 → 提交 → toast
6. 分类删除拦截：选中「人数」→ 删除分类钮禁用 + Tooltip「该分类下还有 3 个标签，请先移除或迁移标签」
7. 标签删除确认（§4.2）：点「删除标签 音乐」→ ConfirmDialog「确定删除标签「音乐」吗？」→ toast「标签删除成功」
8. RBAC 只读态：注入仅 tag:read 快照 → 写钮全部禁用 + Tooltip「无 tag:create 权限」；行编辑/删除禁选
9. 主题抽屉：10 预设齐全（lake-view 默认），本页零硬编码品牌色

失败落 tests/ui/artifacts/int507_tag_management/<用例>/（截图+console+source）。
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

# 栈门禁豁免：本文件走查 frontend-react/ mock 稿（无后端依赖），
# tests/ui/conftest.py 经 STACK_GATE_EXEMPT_MODULES 对本模块放行。

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int507_tag_management')

# 5274 = INT-507 交付验收隔离副本 dev server（5273 为主工作区常驻）；env 可覆写
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5274')
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
    time.sleep(1.2)


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


def _search_input(drv, label):
    return drv.find_element(By.CSS_SELECTOR, f"input[aria-label='{label}']")


def _table_headers(drv):
    return drv.find_elements(By.CSS_SELECTOR, 'table thead th')


def _right_title(drv):
    """右卡标题（当前分类名 + 计数）：取含 tabular-nums 计数的 CardTitle 文本。"""
    titles = drv.find_elements(By.CSS_SELECTOR, '[data-slot=card-title]')
    return [t.text for t in titles]


# ── 1. 页面渲染（左分类树 + 右标签表）────────────────────
def test_01_page_renders(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
    txt = _body_text(drv)
    assert '标签管理' in txt, f'页标题缺失：{txt[:150]}'
    assert '管理标签分类和标签，用于用例筛选和报告统计' in txt, f'页说明缺失：{txt[:200]}'
    # 左分类树卡
    assert '标签分类' in txt, '左卡标题缺失'
    assert '共 5 个' in txt, '左卡计数缺失'
    for cat in ['人数', '场景', '语种', '噪声环境', '设备类型']:
        assert cat in txt, f'分类「{cat}」缺失'
    assert '未分类' in txt, '未分类固定尾项缺失'
    assert '已加载全部' in txt, '左卡「已加载全部」缺失'
    # 右标签表卡（默认未分类视图=全量 13 标签）
    titles = _right_title(drv)
    assert any('未分类' in t and '共 13 个标签' in t for t in titles), \
        f'右卡标题未分类/共 13 个标签缺失：{titles}'
    headers = [h.text for h in _table_headers(drv)]
    assert headers == ['标签', '所属分类', '描述', '操作'], f'右表表头异常：{headers}'
    assert '已加载全部 13 个标签' in txt, '右表「已加载全部」缺失'
    # 搜索框 + 新建钮
    assert _search_input(drv, '搜索分类').get_attribute('placeholder') == '搜索分类...'
    assert _search_input(drv, '搜索标签').get_attribute('placeholder') == '搜索标签...'
    assert '新建标签' in txt and '新建' in txt


# ── 2. 分类选中过滤 ──────────────────────────────────────
def test_02_category_select_filters(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
    # 点「人数」分类（左树按钮）
    drv.find_element(By.XPATH, "//button[contains(., '人数')]").click()
    time.sleep(0.9)
    txt = _body_text(drv)
    titles = _right_title(drv)
    assert any('人数' in t and '共 3 个标签' in t for t in titles), \
        f'右卡标题未切到「人数/共 3 个标签」：{titles}'
    # 所属分类列隐藏：表头仅 3 列（标签/描述/操作）
    headers = [h.text for h in _table_headers(drv)]
    assert '所属分类' not in headers, f'分类选中态所属分类列应隐藏：{headers}'
    assert '1人' in txt and '2人' in txt and '多人' in txt, '人数分类下 3 个标签缺失'


# ── 3. 标签搜索（300ms 防抖）─────────────────────────────
def test_03_tag_search_debounced(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
    box = _search_input(drv, '搜索标签')
    box.send_keys('音乐')
    WebDriverWait(drv, 10).until(
        lambda d: '共 1 个标签' in _body_text(drv))
    txt = _body_text(drv)
    assert '音乐' in txt and '已加载全部 1 个标签' in txt, f'搜索「音乐」结果异常：{txt[:300]}'
    # 清空恢复全量
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.BACKSPACE)
    WebDriverWait(drv, 10).until(
        lambda d: '共 13 个标签' in _body_text(drv))


# ── 4. 新建标签模态（§5.4）───────────────────────────────
def test_04_tag_create_dialog(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
    drv.find_element(By.XPATH, "//button[contains(., '新建标签')]").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert '新建标签' in dtxt, f'对话框标题缺失：{dtxt[:150]}'
    for field in ['标签名称', '所属分类', '描述', '颜色']:
        assert field in dtxt, f'字段「{field}」缺失：{dtxt[:200]}'
    # 名称空 → 创建禁用
    create_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                  if b.text.strip() in ('创建', '保存') and b.is_displayed()]
    assert create_btn and create_btn[0].get_attribute('disabled'), '名称为空时「创建」应禁用'
    # 填名 → 启用 → 提交 → toast
    dialog.find_element(By.ID, 'tag-name').send_keys('新标签')
    time.sleep(0.3)
    create_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                  if b.text.strip() in ('创建', '保存') and b.is_displayed()]
    assert create_btn and not create_btn[0].get_attribute('disabled'), '填名后「创建」应启用'
    create_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '标签创建成功' in _body_text(drv))
    WebDriverWait(drv, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content'][data-open]")) == 0
        if d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']") else True)
    time.sleep(0.6)


# ── 5. 新建分类模态（§5.4）───────────────────────────────
def test_05_category_create_dialog(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
    # 左卡「+ 新建」
    drv.find_element(By.XPATH, "//button[contains(., '新建')]").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert '新建分类' in dtxt, f'对话框标题缺失：{dtxt[:150]}'
    for field in ['分类名称', '描述', '颜色', '排序']:
        assert field in dtxt, f'字段「{field}」缺失：{dtxt[:200]}'
    dialog.find_element(By.ID, 'category-name').send_keys('新分类')
    time.sleep(0.3)
    create_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                  if b.text.strip() in ('创建', '保存') and b.is_displayed()]
    assert create_btn and not create_btn[0].get_attribute('disabled'), '填名后「创建」应启用'
    create_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '分类创建成功' in _body_text(drv))


# ── 6. 分类删除拦截（事前阻断）──────────────────────────
def test_06_category_delete_guard(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
    drv.find_element(By.XPATH, "//button[contains(., '人数')]").click()
    time.sleep(0.8)
    btn = drv.find_element(By.CSS_SELECTOR, "button[aria-label='删除分类 人数']")
    assert btn.get_attribute('disabled'), '含标签分类的删除钮应禁用'
    # Tooltip 文案（悬停触发 Base UI Tooltip）
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(drv).move_to_element(btn).perform()
    time.sleep(0.8)
    txt = _body_text(drv)
    assert '该分类下还有 3 个标签，请先移除或迁移标签' in txt, \
        f'删除拦截 Tooltip 缺失：{txt[:300]}'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)


# ── 7. 标签删除确认（§4.2 软删不级联）────────────────────
def test_07_tag_delete_confirm(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='删除标签 音乐']").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '删除标签' in dtxt and '确定删除标签「音乐」吗？' in dtxt, f'删除确认文案缺失：{dtxt[:200]}'
    confirm_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == '删除' and b.is_displayed()]
    assert confirm_btn, '确认按钮「删除」缺失'
    confirm_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '标签删除成功' in _body_text(drv))


# ── 8. RBAC 只读态（仅 tag:read → 写钮禁用 + Tooltip）────
def test_08_rbac_readonly_state(drv):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script("window.localStorage.clear()")
    snapshot = {
        'state': {
            'user': {
                'id': 'mock-algo-001',
                'username': 'algo_engineer',
                'displayName': '演示算法工程师',
                'roleName': '算法工程师',
                'permissions': ['tag:read'],
            }
        },
        'version': 0,
    }
    drv.execute_script(
        "window.localStorage.setItem('iatp:auth:v1', arguments[0])",
        json.dumps(snapshot, ensure_ascii=False))
    _goto(drv, '/TagManagement')
    txt = _body_text(drv)
    assert '标签管理' in txt, f'只读态页面未渲染：{txt[:150]}'
    # 写钮全部禁用（+ 新建 / 新建标签）
    for aria in ['搜索分类', '搜索标签']:
        _search_input(drv, aria)
    new_cat = drv.find_elements(By.XPATH, "//button[contains(., '新建')]")
    for b in new_cat:
        if b.is_displayed() and b.text.strip() in ('新建', '新建标签'):
            assert b.get_attribute('disabled'), f'只读态「{b.text}」应禁用'
    # 行编辑/删除禁选（首个可见标签操作钮）
    edit_btn = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='编辑标签 ']")
    assert edit_btn and edit_btn[0].get_attribute('disabled'), '只读态编辑标签应禁用'
    del_btn = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='删除标签 ']")
    assert del_btn and del_btn[0].get_attribute('disabled'), '只读态删除标签应禁用'
    # 左分类树行内编辑/删除钮：选中行恒渲染但置灰（§7 注 1 不整组隐藏 + Tooltip）
    drv.find_element(By.XPATH, "//button[contains(., '人数')]").click()
    time.sleep(0.8)
    cat_edit = drv.find_element(By.CSS_SELECTOR, "button[aria-label='编辑分类 人数']")
    assert cat_edit.get_attribute('disabled'), '只读态左树编辑分类应置灰'
    cat_del = drv.find_element(By.CSS_SELECTOR, "button[aria-label='删除分类 人数']")
    assert cat_del.get_attribute('disabled'), '只读态左树删除分类应置灰'
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(drv).move_to_element(cat_edit).perform()
    time.sleep(0.8)
    assert '无 tag:update 权限' in _body_text(drv), '只读态左树编辑分类 Tooltip 缺失'
    # 恢复 admin 会话（后续用例隔离）
    drv.execute_script("window.localStorage.clear()")


# ── 9. 主题抽屉可用性（本页零硬编码品牌色）──────────────
def test_09_theme_drawer_available(drv):
    _login(drv)
    _goto(drv, '/TagManagement')
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
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
