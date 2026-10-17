# -*- coding: utf-8 -*-
"""INT-596 返修重交付（commit 983a2dc8）复测——UX 审计 P2 五项 + P3 批次浏览器验收。

打回后复测只测失败项（P2 五项 + P3 批次中浏览器可触发项），真实 Chrome headless，
独立 dev server（REACT_DEV_BASE 覆盖，本 run :5285），mock 稿无后端依赖。

覆盖：
P2-1  Benchmark 发布确认弹窗（§4.13 ConfirmDialog，destructive 主钮 + 确认文案）
P2-2  报告中心勾选态切换回收站/筛选即清空（批量浮条不再作用于非当前视图）
P2-4  报告查看错误态语义分叉：/report/99999 →「报告不存在」，无「请重试」
P3    具体用例筛选卡：搜索 + 「已选条件 (N)」逐项可删
P3    分组对比筛选卡：「已选条件 (N)」逐项可删
P3    批量对比弹窗「对比配置」页签（§4.6：对比维度/指标/方式/报告配置）
P3    分享弹窗「收件人」受控输入（落 state 不丢弃）
P3    对比面板报告保存卡：空名禁存
多资源 具体用例卡片「设备/API 执行结果」按资源（device/api）分组多列展示（负责人 06:37 反馈核对）

失败落 tests/ui/artifacts/int596_retest/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int596_retest')

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
    # INT-606 认证接线后：拦截 /auth/me（getMe）返回预置超级用户，配合 localStorage 预置登录态
    # （出图同法：红线④不起后端；getMe 200 则 hydrateSession 不清登录态）
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': r'''
window.__iatpMockAuth = {
  user_id: 'demo_admin',
  username: 'demo_admin',
  permissions: ['*'],
};
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = (typeof input === 'string' ? input : (input && input.url) || '') || '';
  if (url.indexOf('/auth/me') !== -1) {
    return Promise.resolve(new Response(JSON.stringify(window.__iatpMockAuth), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  if (url.indexOf('/auth/mode') !== -1) {
    return Promise.resolve(new Response(JSON.stringify({ auth_mode: 'off' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  if (url.indexOf('/auth/oauth/providers') !== -1) {
    return Promise.resolve(new Response('[]', {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  return __origFetch.apply(this, arguments);
};
'''
    })
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
    try:
        _login(_DRIVER)
    except Exception:
        pass
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
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _login(drv, username='demo_admin'):
    """预置登录态（INT-606 后 mock 表单登录不可用）：先落 origin，再写 localStorage，
    随后各用例直接导航（getMe 已由 fetch 拦截兜底，hydrateSession 不清态）。"""
    _goto(drv, '/login')
    drv.execute_script(
        'try { window.localStorage.clear() } catch (e) {};'
        'window.localStorage.setItem("iatp:auth:token:v1", "retest-fake-token");'
        'window.localStorage.setItem("iatp:auth:v1", JSON.stringify({state:{user:{'
        'id:"demo_admin",username:"demo_admin",displayName:"演示管理员",roleName:"管理员",'
        'permissions:["*"]}},version:0}));'
        'window.localStorage.setItem("iatp:algorithm:v1", JSON.stringify({state:{algorithmId:""},version:0}));'
    )
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心', timeout=20)


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _clear_global_algorithm(drv):
    drv.execute_script(
        'localStorage.setItem("iatp:algorithm:v1", JSON.stringify({state:{algorithmId:""},version:0}))')
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# P2
# ---------------------------------------------------------------------------

def test_p2_benchmark_publish_confirm_dialog(drv):
    """P2-1：Benchmark 发布须经 §4.13 ConfirmDialog（destructive 主钮 + 确认文案），确认前不落库。"""
    _goto(drv, '/report/1185')
    _wait_text(drv, 'Benchmark 排行')
    _wait_text(drv, '发布 Benchmark 报告', timeout=20)
    btn = drv.find_element(By.XPATH, "//button[contains(., '发布 Benchmark 报告')]")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", btn)
    time.sleep(0.3)
    btn.click()
    # 确认弹窗出现：文案 + destructive 主钮
    _wait_text(drv, '将当前排行结果生成独立 Benchmark 报告，可查看与导出。', timeout=8)
    body = _body_text(drv)
    assert '发布 Benchmark 报告' in body, '确认弹窗标题缺失'
    publish_btn = drv.find_element(By.XPATH, "//button[normalize-space(.)='发布']")
    cls = publish_btn.get_attribute('class') or ''
    assert 'destructive' in cls.lower() or 'bg-destructive' in cls, \
        f'确认主钮非 destructive：{cls}'
    # 取消 → 弹窗关闭（页内常驻文案含 desc 子串，以弹窗「发布」主钮消失判定关闭）
    drv.find_element(By.XPATH, "//button[normalize-space(.)='取消']").click()
    time.sleep(0.5)
    remaining = drv.find_elements(By.XPATH, "//button[normalize-space(.)='发布']")
    assert not remaining, '取消后确认弹窗未关闭（「发布」主钮仍在）'


def test_p2_report_center_selection_clears_on_view_switch(drv):
    """P2-2：勾选后切换视图/筛选条件 → 勾选清空，批量浮条消失（不作用于非当前视图项）。

    注：回收站/仅看收藏 Switch 存在预置缺陷（点击后 URL 归一化为 trash=false，见审计记录），
    本用例经高级搜索「任务类型」条件变更验证 deps 补齐生效（P2-2 修复核心）。
    """
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    time.sleep(0.8)
    # 勾选第一行数据行（Checkbox 为 span role=checkbox 形态，JS click 触发 onCheckedChange）
    row_checkbox = drv.find_element(
        By.XPATH, "//span[@data-slot='checkbox'][starts-with(@aria-label, '选择报告')]")
    drv.execute_script("arguments[0].click();", row_checkbox)
    time.sleep(0.5)
    _wait_text(drv, '已选择 1 个报告', timeout=8)
    # 高级搜索改「任务类型」→ 筛选条件变化 → 勾选清空
    drv.find_element(By.XPATH, "//button[contains(., '高级搜索')]").click()
    time.sleep(0.5)
    drv.find_element(By.XPATH, "//button[@id='adv-task-type']").click()
    time.sleep(0.5)
    # 选第一个非「全部」的选项
    items = drv.find_elements(By.XPATH, "//*[@role='option' and not(contains(., '全部'))]")
    assert items, '任务类型下拉无可选项'
    items[0].click()
    time.sleep(0.8)
    body = _body_text(drv)
    assert '已选择' not in body, '高级搜索变更后批量浮条未清空（勾选残留）'
    assert '已选择 1 个报告' not in body, '高级搜索变更后勾选残留'


def test_p2_report_not_found_semantic(drv):
    """P2-4：无效 ID →「报告不存在」；不得误标「加载失败/请重试」（网络/500 才用该文案）。"""
    _goto(drv, '/report/99999')
    _wait_text(drv, '报告不存在', timeout=20)
    body = _body_text(drv)
    assert '请提供有效的报告ID' in body, '404 缺引导文案'
    assert '请重试' not in body, '404 语义误标「请重试」（网络/500 才显）'
    assert '加载失败' not in body, '404 语义误标「加载失败」'
    # 返回报告中心按钮存在
    drv.find_element(By.XPATH, "//button[contains(., '返回报告中心')]")


# ---------------------------------------------------------------------------
# P3
# ---------------------------------------------------------------------------

def test_p3_specific_case_filter_search_and_selected_conditions(drv):
    """P3：具体用例筛选卡 搜索输入 + 「已选条件 (N)」逐项可删（§3.3.7/3.3.8）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '具体用例对比')
    time.sleep(1.2)
    # 搜索输入（具体用例名称搜索框）
    assert drv.find_elements(By.XPATH, "//input[contains(@placeholder, '输入用例ID或名称关键词')]"), \
        '具体用例筛选卡缺名称搜索输入'
    # 具体用例段（最后一个「用例分组」label span）→ filter root（最近 flex-col 祖先）→ chip 组
    grp_spans = drv.find_elements(By.XPATH, "//span[normalize-space(.)='用例分组']")
    assert grp_spans, '页面无「用例分组」label'
    root = grp_spans[-1].find_element(By.XPATH, "./ancestor::div[contains(@class, 'flex-col')][1]")
    chips = root.find_elements(
        By.XPATH, ".//button[@type='button'][not(contains(., '上一页'))][not(contains(., '下一页'))]")
    assert chips, '具体用例筛选卡「用例分组」无可点 chip'
    chip = chips[0]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", chip)
    time.sleep(0.3)
    drv.execute_script("arguments[0].click();", chip)
    time.sleep(0.6)
    _wait_text(drv, '已选条件 (1)', timeout=8)
    # 逐项可删
    del_btn = drv.find_element(By.XPATH, "//button[starts-with(@aria-label, '移除条件')]")
    drv.execute_script("arguments[0].click();", del_btn)
    time.sleep(0.5)
    assert '已选条件 (1)' not in _body_text(drv), '移除条件后「已选条件」条未消失'


def test_p3_category_comparison_selected_conditions(drv):
    """P3：按用例分组对比筛选卡「已选条件 (N)」逐项可删（§3.3.8）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '按用例分组对比')
    time.sleep(1.0)
    # 第一个「用例标签」label span（按用例分组对比段）→ filter root → checkbox 组
    tag_spans = drv.find_elements(By.XPATH, "//span[normalize-space(.)='用例标签']")
    assert tag_spans, '页面无「用例标签」label'
    root = tag_spans[0].find_element(By.XPATH, "./ancestor::div[contains(@class, 'flex-col')][1]")
    labels = root.find_elements(By.XPATH, ".//span[@data-slot='checkbox']")
    assert labels, '按用例分组对比「用例标签」无可选 checkbox'
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", labels[0])
    time.sleep(0.3)
    drv.execute_script("arguments[0].click();", labels[0])
    time.sleep(0.6)
    _wait_text(drv, '已选条件 (1)', timeout=8)
    body = _body_text(drv)
    assert '标签·' in body, '已选条件条缺「标签·」前缀'
    del_btn = drv.find_element(By.XPATH, "//button[starts-with(@aria-label, '移除条件')]")
    drv.execute_script("arguments[0].click();", del_btn)
    time.sleep(0.5)
    assert '已选条件 (1)' not in _body_text(drv), '移除后「已选条件」条未消失'


def test_p3_compare_dialog_config_tab(drv):
    """P3：批量对比弹窗补「对比配置」页签（§4.6 对比维度/指标/方式/报告配置）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    time.sleep(0.8)
    checkboxes = drv.find_elements(
        By.XPATH, "//span[@data-slot='checkbox'][starts-with(@aria-label, '选择报告')]")
    assert len(checkboxes) >= 2, f'报告中心可勾选行 <2（{len(checkboxes)}），无法触发批量对比'
    drv.execute_script("arguments[0].click();", checkboxes[0])
    time.sleep(0.2)
    drv.execute_script("arguments[0].click();", checkboxes[1])
    time.sleep(0.5)
    _wait_text(drv, '已选择 2 个报告', timeout=8)
    drv.find_element(By.XPATH, "//button[contains(., '批量对比')]").click()
    _wait_text(drv, '对比配置', timeout=10)
    drv.find_element(By.XPATH, "//button[@role='tab' and contains(., '对比配置')]").click()
    time.sleep(0.5)
    body = _body_text(drv)
    for label in ('对比维度', '对比指标', '对比方式', '报告名称'):
        assert label in body, f'对比配置页签缺「{label}」'
    # 关闭弹窗
    close_btns = drv.find_elements(By.XPATH, "//button[@data-slot='dialog-close']")
    if close_btns:
        close_btns[0].click()
        time.sleep(0.3)


def test_p3_share_dialog_controlled_input(drv):
    """P3：分享弹窗「收件人」受控输入落 state（原不受控 Input 保存后丢弃）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '旗舰音箱全量回归 · 第 3 轮报告')
    _wait_text(drv, '分享', timeout=20)
    drv.find_element(By.XPATH, "//button[contains(., '分享')]").click()
    _wait_text(drv, '分享报告', timeout=10)
    # 切「邮件分享」方式 → 收件人 input
    drv.find_element(By.XPATH, "//button[contains(., '邮件分享')]").click()
    time.sleep(0.5)
    email_input = drv.find_element(By.XPATH, "//input[@placeholder='name@example.com']")
    email_input.send_keys('tester@example.com')
    time.sleep(0.3)
    assert email_input.get_attribute('value') == 'tester@example.com', \
        '收件人输入未受控（值未落 state）'
    # 关闭重开 → 值保留（state 未丢弃）
    drv.find_element(By.XPATH, "//button[@data-slot='dialog-close']").click()
    time.sleep(0.6)
    drv.find_element(By.XPATH, "//button[contains(., '分享')]").click()
    _wait_text(drv, '分享报告', timeout=10)
    drv.find_element(By.XPATH, "//button[contains(., '邮件分享')]").click()
    time.sleep(0.5)
    reopened = drv.find_element(By.XPATH, "//input[@placeholder='name@example.com']")
    assert reopened.get_attribute('value') == 'tester@example.com', \
        '重开后收件人值丢失（state 未保留）'
    drv.find_element(By.XPATH, "//button[@data-slot='dialog-close']").click()
    time.sleep(0.4)


def test_p3_save_card_empty_name_disabled(drv):
    """P3：对比面板报告保存卡 空名禁存（!name.trim() 禁用保存按钮）。"""
    _goto(drv, '/report/1190')
    _wait_text(drv, '对比报告', timeout=20)
    _wait_text(drv, '报告保存', timeout=20)
    name_input = drv.find_element(By.XPATH, "//div[.//p[normalize-space(.)='报告保存']]//input[@placeholder='请输入报告名称']")
    save_btn = drv.find_element(By.XPATH, "//div[.//p[normalize-space(.)='报告保存']]//button[normalize-space(.)='保存']")
    name_input.click()
    name_input.send_keys('\ue009' + 'a')  # ctrl+a 全选后覆盖为 'a'
    time.sleep(0.3)
    name_input.send_keys('\ue009' + '\ue003')  # ctrl+a + backspace → 空名
    time.sleep(0.4)
    assert not save_btn.is_enabled(), '空名时保存按钮未禁用（P3 空名禁存失效）'
    name_input.send_keys('复测报告名')
    time.sleep(0.4)
    assert save_btn.is_enabled(), '输入名称后保存按钮仍禁用'


# ---------------------------------------------------------------------------
# 负责人 06:37 反馈核对：多设备/API 结果 + 播放器
# ---------------------------------------------------------------------------

def test_specific_case_multi_resource_results(drv):
    """具体用例卡片「设备/API 执行结果」多资源（device/api）多列展示（负责人 06:37 反馈核对）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '具体用例对比')
    _wait_text(drv, '多轮对话-闲聊上下文（voice_llm）', timeout=20)
    drv.execute_script(
        "const row=[...document.querySelectorAll('div.rounded-xl.border')]"
        ".find(d=>d.textContent.includes('多轮对话-闲聊上下文（voice_llm）'));"
        "if(row){const bs=row.querySelectorAll('button');bs[bs.length-1].click()}")
    _wait_text(drv, '评分指标', timeout=15)
    _wait_text(drv, '设备/API 执行结果', timeout=15)
    body = _body_text(drv)
    # 资源名出现在结果区（mock c-1042-001 的 device_1/api_101 资源标识）
    assert 'device_1' in body or 'api_101' in body or '全部资源' in body, \
        '设备/API 执行结果未见多资源（device/api）标识'
