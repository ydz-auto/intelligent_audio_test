# -*- coding: utf-8 -*-
"""INT-509 评估维度 React 可视稿浏览器走查（真实 Chrome headless，按 test_ui_09/10 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. /Evaluation 页面渲染：页头「评估维度」+ 说明 + 面包屑；自动合并提示条；双视图
   页签（列表视图/分组视图）；筛选工具栏（搜索/状态/分类/关联算法）；维度表格九列
   （维度名称/描述/分类/关联算法/权重/API 状态/状态/操作）
2. 列表视图表格内容：主/子维度层级（主/子徽章 + 子维度「（父名）」括注）、权重滑杆、
   启用/禁用状态徽章、LLM Judge 徽章（语义理解）
3. 筛选：搜索「时延」→ 仅响应时延维度；重置筛选恢复全量
4. 分组视图：切「分组视图」→ 分类聚合卡（识别质量/语义理解/响应体验/稳定性 +
   组头「添加维度」/计数徽章）
5. 新增维度抽屉（§5.5）：打开「新增维度」→ Sheet 标题 + 五页签（基本信息/层级配置/
   结果配置/API配置/关联算法）→ 填名称 → 保存 → toast「评估维度添加成功」+ Sheet 关闭
6. 新增分类弹窗（§5.5）：打开「新增分类」→ 分类名称/描述/图标 → 创建 → toast
7. 规则试算（§4.1）：点「规则试算维度 识别准确率」→ 输入测试值 → 试算 → 「评分 X 分」
8. API 健康测试（§5.5）：点「测试维度 识别准确率 的 API」→ 结果弹窗「API健康测试结果」+ 在线
9. 删除确认（§4.1/§5.6）：点「删除维度 …」→ ConfirmDialog 文案 → 确认 → toast「维度已删除」
10. RBAC 只读态：注入仅 evaluation:read 快照 → 写钮禁用 + Tooltip「无 evaluation:dim_manage 权限」
11. 全局算法联动（P2-1 返修，§4.1）：全局算法 asr-v3 → chip + facet 继承 + 列表过滤 + × 清空
12. 权重滑杆提交（§4.1/§10-4）：ArrowUp → onValueCommitted → toast「权重更新成功」
13. 批量禁用（勾选 → 浮条 → 确认弹窗 → toast）
14. 批量删除（勾选 → 确认弹窗 → toast；mock 重拉还原静态数据，行态不断言）
15. 复制维度（确认弹窗 → 成功 toast）
16. 上移/下移边界（首行/子维度边界禁用 + 有效上移）
17. 分页（共 12 条 → 1 / 2 → 下一页 → 2 / 2）
18. 导入/导出（JSON/Excel 二选一下拉项 → toast）
19. 分类含维度删除拦截（分组视图禁用 + Tooltip 文案）

失败落 tests/ui/artifacts/int509_evaluation/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int509_evaluation')

# 5273 = 工作区常驻 dev server（strictPort 钉死）；env 可覆写
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
    time.sleep(1.5)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _login(drv, username='demo_admin'):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    # React SPA 首屏挂载时序：显式等用户名输入框出现再交互（防首测 flaky）
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.ID, 'username')) > 0)
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)
    # 全局算法置空：默认展示全部维度（全局算法联动口径单独由 test_11 覆盖）
    _set_global_algorithm(drv, '')


def _set_global_algorithm(drv, algorithm_id):
    """设置全局算法 store（iatp:algorithm:v1）；空串=无全局选择（全部维度可见）。"""
    drv.execute_script(
        "window.localStorage.setItem('iatp:algorithm:v1', arguments[0])",
        json.dumps({'state': {'algorithmId': algorithm_id}, 'version': 0}))


def _table_headers(drv):
    return [h.text for h in drv.find_elements(By.CSS_SELECTOR, 'table thead th')]


# ── 1. 页面渲染 ─────────────────────────────────────────
def test_01_page_renders(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    assert '评估维度' in txt, f'页标题缺失：{txt[:150]}'
    assert '管理语音测试的评估维度和权重' in txt, f'页说明缺失：{txt[:200]}'
    assert '同一分类下、评估服务与请求模板一致的维度，评估时会自动合并为一次请求，共用一次判定结果。' in txt, \
        f'自动合并提示条缺失：{txt[:300]}'
    for tab in ['列表视图', '分组视图']:
        assert tab in txt, f'视图页签「{tab}」缺失'
    # 工具栏 + 表头
    assert _search_input_exists(drv), '搜索框缺失'
    for header in ['维度名称', '描述', '分类', '关联算法', '权重', 'API 状态', '状态', '操作']:
        assert header in _table_headers(drv), f'表头「{header}」缺失：{_table_headers(drv)}'


def _search_input_exists(drv):
    return len(drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")) > 0


# ── 2. 列表视图表格内容 ─────────────────────────────────
def test_02_list_view_content(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    for dim in ['识别准确率', '字准率', '句准率', '语义理解', '响应时延', '噪声鲁棒性']:
        assert dim in txt, f'维度「{dim}」缺失：{txt[:400]}'
    # 子维度括注「（父名）」
    assert '（识别准确率）' in txt, '子维度父名括注缺失'
    # 徽章：主/子 + 状态 + LLM Judge
    assert '主' in txt and '子' in txt, '主/子徽章缺失'
    assert '启用' in txt and '禁用' in txt, '启用/禁用状态徽章缺失'
    assert 'LLM Judge' in txt, 'LLM Judge 徽章缺失（语义理解维度）'
    # 在线/离线 API 状态
    assert '在线' in txt and '离线' in txt, '在线/离线 API 状态缺失'


# ── 3. 搜索筛选 + 重置 ──────────────────────────────────
def test_03_search_filter_reset(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys('时延')
    WebDriverWait(drv, 10).until(
        lambda d: '响应时延' in _body_text(drv) and '识别准确率' not in _body_text(drv))
    txt = _body_text(drv)
    assert '响应时延' in txt and '识别准确率' not in txt, f'搜索「时延」结果异常：{txt[:400]}'
    # 重置筛选恢复全量
    drv.find_element(By.XPATH, "//button[contains(., '重置筛选')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '识别准确率' in _body_text(drv))


# ── 4. 分组视图 ─────────────────────────────────────────
def test_04_group_view(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '分组视图')]").click()
    time.sleep(1.0)
    txt = _body_text(drv)
    for cat in ['识别质量', '语义理解', '响应体验', '稳定性']:
        assert cat in txt, f'分类聚合卡「{cat}」缺失：{txt[:400]}'
    assert '添加维度' in txt, '组头「添加维度」缺失'
    # 分类行操作（编辑/删除分类）
    assert len(drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='编辑分类 ']")) >= 2, \
        '分类「编辑分类」按钮缺失'
    # 组内表格复用同款列
    headers = _table_headers(drv)
    assert '维度名称' in headers, '分组视图组内表格列缺失'


# ── 5. 新增维度抽屉（§5.5）──────────────────────────────
def test_05_dimension_mutate_drawer(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
    time.sleep(0.9)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    stxt = sheet.text
    assert '新增评估维度' in stxt, f'抽屉标题缺失：{stxt[:150]}'
    for tab in ['基本信息', '层级配置', '结果配置', 'API配置', '关联算法']:
        assert tab in stxt, f'抽屉页签「{tab}」缺失：{stxt[:300]}'
    # 填名称 → 保存
    sheet.find_element(By.ID, 'dim-name').send_keys('试听质量')
    time.sleep(0.3)
    save_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                if b.text.strip() == '保存' and b.is_displayed()]
    assert save_btn and not save_btn[0].get_attribute('disabled'), '填名后「保存」应启用'
    save_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '评估维度添加成功' in _body_text(drv))
    time.sleep(0.6)


# ── 6. 新增分类弹窗（§5.5）──────────────────────────────
def test_06_category_create_dialog(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '新增分类')]").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert '新建分类' in dtxt, f'分类弹窗标题缺失：{dtxt[:150]}'
    for field in ['分类名称', '描述', '图标']:
        assert field in dtxt, f'分类字段「{field}」缺失：{dtxt[:200]}'
    dialog.find_element(By.ID, 'category-name').send_keys('音频体验')
    time.sleep(0.3)
    create_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                  if b.text.strip() in ('创建', '保存') and b.is_displayed()]
    assert create_btn and not create_btn[0].get_attribute('disabled'), '填名后「创建」应启用'
    create_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '分类添加成功' in _body_text(drv))


# ── 7. 规则试算（§4.1）─────────────────────────────────
def test_07_rule_calc(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='规则试算维度 识别准确率']").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert '规则试算' in dtxt, f'试算弹窗标题缺失：{dtxt[:150]}'
    dialog.find_element(By.ID, 'calc-value').send_keys('96.5')
    time.sleep(0.3)
    calc_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                if b.text.strip() == '试算' and b.is_displayed()]
    assert calc_btn, '试算按钮缺失'
    calc_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '评分' in _body_text(drv))
    dtxt = dialog.text
    assert '评分 10 分' in dtxt, f'试算结果异常：{dtxt[:300]}'


# ── 8. API 健康测试（§5.5）─────────────────────────────
def test_08_health_test(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='测试维度 识别准确率 的 API']").click()
    time.sleep(1.0)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert 'API健康测试结果' in dtxt, f'健康结果弹窗缺失：{dtxt[:150]}'
    assert '在线' in dtxt, f'总状态在线缺失：{dtxt[:300]}'
    assert '健康探测完成' in dtxt, f'端点信息缺失：{dtxt[:300]}'


# ── 9. 删除确认（§5.6）─────────────────────────────────
def test_09_delete_confirm(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='删除维度 响应时延']").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '删除维度' in dtxt and '确定要删除维度「响应时延」吗？此操作不可恢复。' in dtxt, \
        f'删除确认文案缺失：{dtxt[:200]}'
    confirm_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == '删除' and b.is_displayed()]
    assert confirm_btn, '确认按钮「删除」缺失'
    confirm_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '维度已删除' in _body_text(drv))


# ── 10. RBAC 只读态（仅 evaluation:read）───────────────
def test_10_rbac_readonly_state(drv):
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
                'permissions': ['evaluation:read'],
            }
        },
        'version': 0,
    }
    drv.execute_script(
        "window.localStorage.setItem('iatp:auth:v1', arguments[0])",
        json.dumps(snapshot, ensure_ascii=False))
    _set_global_algorithm(drv, '')
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    assert '评估维度' in txt, f'只读态页面未渲染：{txt[:150]}'
    # 新增维度钮禁用
    new_btn = drv.find_elements(By.XPATH, "//button[contains(., '新增维度')]")
    for b in new_btn:
        if b.is_displayed():
            assert b.get_attribute('disabled'), '只读态「新增维度」应禁用'
    # 悬停可见写权限 Tooltip（§7 注 1「无 {权限码} 权限」口径，P3-1）
    ActionChains(drv).move_to_element(new_btn[0]).perform()
    WebDriverWait(drv, 10).until(
        lambda d: '无 evaluation:dim_manage 权限' in _body_text(drv))
    # 行操作禁用（首个编辑钮）
    edit_btn = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='编辑维度 ']")
    assert edit_btn and edit_btn[0].get_attribute('disabled'), '只读态编辑维度应禁用'
    del_btn = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='删除维度 ']")
    assert del_btn and del_btn[0].get_attribute('disabled'), '只读态删除维度应禁用'
    # 恢复 admin 会话（后续用例隔离）
    drv.execute_script("window.localStorage.clear()")


# ── 11. 全局算法联动（§4.1，P2-1 返修）────────────────────
def test_11_global_algorithm_linkage(drv):
    _login(drv)
    _set_global_algorithm(drv, 'asr-v3')
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    # 联动 chip（算法：通用识别引擎）
    assert '算法：通用识别引擎' in txt, f'全局算法联动 chip 缺失：{txt[:300]}'
    # 关联算法 facet 显式显示全局算法值（非「全部」）
    facet = [b for b in drv.find_elements(By.TAG_NAME, 'button') if '关联算法' in b.text]
    assert facet and '通用识别引擎' in facet[0].text, \
        f'关联算法 facet 未继承全局算法：{facet[0].text if facet else "无"}'
    assert '全部' not in facet[0].text.replace('关联算法', ''), \
        '关联算法 facet 不应显示「全部」'
    # 列表按全局算法过滤：asr-v3 维度在，eval-ensemble/asr-stream 维度隐藏
    for dim in ['识别准确率', '字准率', '句准率', '噪声鲁棒性']:
        assert dim in txt, f'asr-v3 维度「{dim}」应可见：{txt[:500]}'
    for dim in ['语义理解', '唤醒成功率', '响应时延']:
        assert dim not in txt, f'非 asr-v3 维度「{dim}」应被全局过滤隐藏：{txt[:500]}'
    # × 清空全局算法 → 回到页内自由筛选（全部维度可见）
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='清除全局算法']").click()
    WebDriverWait(drv, 10).until(
        lambda d: '语义理解' in _body_text(drv) and '唤醒成功率' in _body_text(drv))
    txt = _body_text(drv)
    assert '算法：通用识别引擎' not in txt, '清除全局算法后联动 chip 应隐藏'


# ── 12. 权重滑杆提交（onValueCommitted，§4.1/§10-4）────────
def test_12_weight_slider_commit(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    # base-ui slider：交互元素是 thumb 内嵌的 native range input（clip-path 隐藏）
    inputs = drv.find_elements(
        By.CSS_SELECTOR, "[data-slot='slider-thumb'] input[type='range']")
    assert inputs, '权重滑杆 range input 缺失'
    drv.execute_script('arguments[0].focus();', inputs[0])
    time.sleep(0.3)
    inputs[0].send_keys(Keys.ARROW_UP)
    WebDriverWait(drv, 10).until(
        lambda d: '权重更新成功' in _body_text(drv))


# ── 13. 批量禁用（勾选 → 浮条 → 确认弹窗）────────────────
def test_13_batch_disable(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "[aria-label='选择维度 识别准确率']").click()
    time.sleep(0.3)
    drv.find_element(By.CSS_SELECTOR, "[aria-label='选择维度 字准率']").click()
    time.sleep(0.3)
    assert '已选择 2 个维度' in _body_text(drv), '批量浮条计数缺失'
    drv.find_element(By.XPATH, "//button[contains(., '批量禁用')]").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '确定要禁用选中的 2 个维度吗' in dtxt, f'批量禁用确认文案缺失：{dtxt[:200]}'
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '批量禁用' and b.is_displayed()]
    assert confirm, '批量禁用确认按钮缺失'
    confirm[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '批量操作执行成功' in _body_text(drv))


# ── 14. 批量删除（勾选 → 浮条 → 确认弹窗 → toast）────────
# 注：mock 阶段 mutation invalidate 后重拉还原静态 mock 数据，行移除态会被回写，
# 故按 test_09 口径断言确认弹窗与成功 toast（交互链路完整覆盖）。
def test_14_batch_delete(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "[aria-label='选择维度 响应时延']").click()
    time.sleep(0.3)
    drv.find_element(By.CSS_SELECTOR, "[aria-label='选择维度 噪声鲁棒性']").click()
    time.sleep(0.3)
    drv.find_element(By.XPATH, "//button[contains(., '批量删除')]").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '确定要删除选中的 2 个维度吗' in dtxt, f'批量删除确认文案缺失：{dtxt[:200]}'
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '批量删除' and b.is_displayed()]
    assert confirm, '批量删除确认按钮缺失'
    confirm[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '批量操作执行成功' in _body_text(drv))


# ── 15. 复制维度（确认弹窗 → 成功 toast）──────────────────
def test_15_duplicate_dimension(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='复制维度 响应时延']").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '确定要复制维度「响应时延」吗' in dtxt, f'复制确认文案缺失：{dtxt[:200]}'
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '复制' and b.is_displayed()]
    assert confirm, '复制确认按钮缺失'
    confirm[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '维度复制成功' in _body_text(drv))


# ── 16. 上移/下移边界（主/子维度同屏）────────────────────
def test_16_move_boundaries(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    # 首行主维度上移禁用
    up1 = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='上移维度 识别准确率']")
    assert up1 and up1[0].get_attribute('disabled'), '首行主维度上移应禁用'
    # 子维度「字准率」上移禁用（父维度在其上方）
    up_sub = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='上移维度 字准率']")
    assert up_sub and up_sub[0].get_attribute('disabled'), '子维度上移到父维度之上应禁用'
    # 子维度「句准率」下移禁用（下一行为其它主维度）
    down_sub = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='下移维度 句准率']")
    assert down_sub and down_sub[0].get_attribute('disabled'), '子维度下移到其它主维度组应禁用'
    # 有效上移：第二主维度「语义理解」上移可用并触发成功 toast
    up2 = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='上移维度 语义理解']")
    assert up2 and not up2[0].get_attribute('disabled'), '非边界主维度上移应可用'
    up2[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '已上移' in _body_text(drv))


# ── 17. 分页（列表视图 Footer Portal）────────────────────
def test_17_pagination(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    assert '共 12 条' in txt, f'分页总条数缺失：{txt[:300]}'
    assert '1 / 2' in txt, f'首页分页指示缺失：{txt[:300]}'
    next_btn = [b for b in drv.find_elements(By.TAG_NAME, 'button')
                if b.text.strip() == '下一页' and b.is_displayed()]
    assert next_btn and not next_btn[0].get_attribute('disabled'), '下一页应可用'
    next_btn[0].click()
    time.sleep(0.8)
    txt = _body_text(drv)
    assert '2 / 2' in txt, f'第二页分页指示缺失：{txt[:300]}'
    assert '回声消除效果' in txt, f'第二页维度缺失：{txt[:400]}'
    assert '识别准确率' not in txt, '第二页不应出现第一页维度'


# ── 18. 导入/导出（JSON/Excel 二选一下拉，§4.1）───────────
def test_18_import_export(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '导入/导出')]").click()
    time.sleep(0.7)
    items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']")
    labels = [i.text for i in items]
    assert any('导入维度' in l for l in labels), f'导入项缺失：{labels}'
    assert any('导出维度（JSON）' in l for l in labels), f'JSON 导出项缺失：{labels}'
    assert any('导出维度（Excel）' in l for l in labels), f'Excel 导出项缺失：{labels}'
    # 导入 → toast
    for i in items:
        if '导入维度' in i.text:
            i.click()
            break
    WebDriverWait(drv, 10).until(
        lambda d: '导入完成：新增 2 · 更新 1' in _body_text(drv))
    # 导出 JSON → toast
    drv.find_element(By.XPATH, "//button[contains(., '导入/导出')]").click()
    time.sleep(0.7)
    for i in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']"):
        if '导出维度（JSON）' in i.text:
            i.click()
            break
    WebDriverWait(drv, 10).until(
        lambda d: '导出完成（JSON）' in _body_text(drv))


# ── 19. 分类含维度删除拦截（分组视图）────────────────────
def test_19_category_delete_interception(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '分组视图')]").click()
    time.sleep(1.0)
    # 含维度分类「识别质量」删除钮禁用
    del_btn = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='删除分类 识别质量']")
    assert del_btn and del_btn[0].get_attribute('disabled'), \
        '含维度分类的删除钮应禁用'
    # 悬停可见拦截 Tooltip
    ActionChains(drv).move_to_element(del_btn[0]).perform()
    WebDriverWait(drv, 10).until(
        lambda d: '请先迁移或删除维度' in _body_text(drv))
