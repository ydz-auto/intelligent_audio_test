# -*- coding: utf-8 -*-
"""INT-2102 批量「管理标签」弹窗按分类分组浏览器验收（docker :15000 真实后端 + 本卡 dev server）。

覆盖验收标准：
1. 批量「管理标签」弹窗点选区按分类分组（组头=分类名＋组内标签＋「未分类」尾组）。
2. 选中/移除 chips 后分组内联动正确（chips 从候选剔除、空组头隐藏、未分类尾组仍在）。
3. 提交 add_tags 后回读一致（GET /testcases/{id} tags 含新增标签）。
4. Network 证据：真实 GET /tags/by-category 请求（无 mock 残留）。
5. 浅/深色截图。

前置：本 worktree frontend-react dev server（rsbuild dev --port <5300~5399>，
API_PROXY_TARGET=http://localhost:15000）+ docker 15000 网关（真实库 intelligent_audio_test）。
数据卫生：fixture 全部「接线测试_INT2102_」前缀，用例走本卡自建，run 结束前删除。
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

import _int2102_api as api

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5322')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int2102_batch_tags')

USER_TAG = 'INT2102'
_DRIVER = None
_TOKEN = None
_FIXTURE = None  # {group_id, case_ids}
_TAGS_CLEANED = False


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
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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


@pytest.fixture(scope='module')
def drv():
    global _DRIVER, _TOKEN
    _DRIVER = _driver()
    _install_netlog(_DRIVER)
    tok, err = api._login()
    assert tok, f'登录失败: {err}'
    _TOKEN = tok
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
        d = os.path.join(ARTIFACTS, item.name)
        os.makedirs(d, exist_ok=True)
        try:
            _DRIVER.save_screenshot(os.path.join(d, 'screenshot.png'))
            with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
                f.write(_DRIVER.page_source)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)


def _body_text(drv):
    return drv.execute_script('return document.body ? document.body.textContent : ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _install_netlog(drv):
    # 跨页面导航保留整场会话的请求证据：每页安装时从 sessionStorage 恢复历史，
    # 每次请求后回写；test_07 汇总的是整场会话（含上一页发出的 POST /testcases/batch），
    # 不是仅当前页。
    script = r'''
    (() => {
      const KEY = '__int2102_netlog';
      if (window.__netLogInstalled) return;
      window.__netLog = [];
      try {
        const saved = sessionStorage.getItem(KEY);
        if (saved) window.__netLog = JSON.parse(saved);
      } catch (e) {}
      const flush = () => {
        try { sessionStorage.setItem(KEY, JSON.stringify(window.__netLog)); } catch (e) {}
      };
      const origFetch = window.fetch.bind(window);
      window.fetch = async (...args) => {
        const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url);
        const method = (args[1] && args[1].method) || 'GET';
        const started = performance.now();
        try {
          const resp = await origFetch(...args);
          window.__netLog.push({ method, url: String(url), status: resp.status,
            ms: Math.round(performance.now() - started) });
          flush();
          return resp;
        } catch (e) {
          window.__netLog.push({ method, url: String(url), status: -1, ms: 0,
            error: String(e) });
          flush();
          throw e;
        }
      };
      window.__netLogInstalled = true;
      flush();
    })();
    '''
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': script})


def _netlog(drv):
    # 优先读当前页内存日志（含从 sessionStorage 恢复的历史）；读不到时直接从存储取
    try:
        return drv.execute_script('return window.__netLog || []')
    except Exception:
        try:
            return drv.execute_script(
                "try { return JSON.parse(sessionStorage.getItem('__int2102_netlog') || '[]') } catch (e) { return [] }")
        except Exception:
            return []


def _ensure_logged_in(drv, tries=2):
    for _ in range(tries):
        _goto(drv, '/dashboard')
        if '/login' not in drv.current_url:
            break
        _goto(drv, '/login')
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.ID, 'username'))
        drv.find_element(By.ID, 'username').send_keys('dev_user')
        drv.find_element(By.ID, 'password').send_keys('dev_password')
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        ok = False
        for _ in range(6):
            time.sleep(2)
            if '/login' not in drv.current_url and '工作台' in _body_text(drv):
                ok = True
                break
        if ok:
            break
    WebDriverWait(drv, 25).until(lambda d: '/login' not in drv.current_url)
    _wait_text(drv, '工作台', timeout=25)


def _js_click(drv, xpath):
    el = WebDriverWait(drv, 12).until(lambda d: d.find_element(By.XPATH, xpath))
    drv.execute_script('arguments[0].click()', el)


def _shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(os.path.dirname(d), exist_ok=True)
    drv.save_screenshot(d)
    return d


def _set_theme(drv, name):
    _js_click(drv, "//button[@aria-label='打开主题设置']")
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, f"//*[@role='radio'][contains(., '{name}')]")
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC
    time.sleep(0.5)


def _goto_my_cases(drv, user):
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, '\u7528\u4f8b\u7ba1\u7406')
    # \u5206\u7ec4 facet \u7b5b\u9009\u5230\u672c\u5361\u5206\u7ec4\uff08by-group \u5361\u6309\u6570\u91cf\u6392\u5e8f\u53ea\u6e32\u67d3\u524d 5 \u7ec4\uff0c\u65b0\u5206\u7ec4\u5728\u5c3e\u90e8\uff09
    facet = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.XPATH,
            "//button[contains(normalize-space(.), '\u5206\u7ec4') and contains(normalize-space(.), '\u5168\u90e8')]"))
    drv.execute_script('arguments[0].click()', facet)
    opt = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH,
            f"//button[contains(normalize-space(.), '\u63a5\u7ebf\u6d4b\u8bd5_{user}_\u5206\u7ec4')]"))
    drv.execute_script('arguments[0].click()', opt)
    _wait_text(drv, f'\u63a5\u7ebf\u6d4b\u8bd5_{user}_\u5206\u7ec4', timeout=20)
    # \u5c55\u5f00\u5206\u7ec4\u5361\uff08\u7ec4\u5934\u53ef\u70b9\u51fb\u5c55\u5f00\uff0cINT-1027 \u9ed8\u8ba4\u6536\u8d77\uff09
    header = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH,
            f"//span[normalize-space(.)='\u63a5\u7ebf\u6d4b\u8bd5_{user}_\u5206\u7ec4']/ancestor::div[contains(@class, 'cursor-pointer')]"))
    drv.execute_script('arguments[0].click()', header)
    _wait_text(drv, f'\u63a5\u7ebf\u6d4b\u8bd5_{user}_\u7528\u4f8bA', timeout=20)


def _select_my_cases(drv, user):
    """\u52fe\u9009\u672c\u5361 2 \u4e2a\u7528\u4f8b\uff08\u7528\u4f8b\u5361 base-ui Checkbox role=checkbox aria-label='\u9009\u62e9 {\u540d\u79f0}'\uff09\u3002"""
    clicked = 0
    for suffix in ('\u7528\u4f8bA', '\u7528\u4f8bB'):
        try:
            cb = WebDriverWait(drv, 12).until(
                lambda d: d.find_element(By.CSS_SELECTOR,
                    f"[role='checkbox'][aria-label='\u9009\u62e9 \u63a5\u7ebf\u6d4b\u8bd5_{user}_{suffix}']"))
            if not cb.is_enabled():
                continue
            drv.execute_script('arguments[0].click()', cb)
            clicked += 1
        except Exception:
            continue
    assert clicked >= 2, f'\u672a\u80fd\u52fe\u9009\u672c\u5361 2 \u4e2a\u7528\u4f8b\uff08{clicked}\uff09'
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(., '\u6279\u91cf\u7ba1\u7406\u6807\u7b7e')]"))


def _open_tags_dialog(drv, user):
    _js_click(drv, "//button[contains(., '\u6279\u91cf\u7ba1\u7406\u6807\u7b7e')]")
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '\u6279\u91cf\u7ba1\u7406\u6807\u7b7e')]"))
    _wait_text(drv, '\u5df2\u6709\u6807\u7b7e\uff08\u70b9\u51fb\u6dfb\u52a0\uff09\uff1a')


@pytest.fixture(scope='module', autouse=True)
def fixture(drv):
    """模块级 fixture：建分类/标签/用例；测试内不清理，模块尾清理。"""
    global _FIXTURE
    assert _TOKEN
    api._fixture(_TOKEN, USER_TAG)
    _FIXTURE = api._case_fixture(_TOKEN, USER_TAG)
    yield _FIXTURE
    # 模块尾清理：删用例/分组/标签/分类
    try:
        api._case_cleanup(_TOKEN, USER_TAG, _FIXTURE.get('group_id'))
    except Exception as e:
        print(f'[INT2102-CLEANUP] 用例清理异常: {e}')
    try:
        api._cleanup(_TOKEN)
    except Exception as e:
        print(f'[INT2102-CLEANUP] 标签清理异常: {e}')


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_01_login_and_open_batch_tags_dialog(drv, fixture):
    _ensure_logged_in(drv)
    _goto_my_cases(drv, USER_TAG)
    _select_my_cases(drv, USER_TAG)
    _open_tags_dialog(drv, USER_TAG)
    _shot(drv, '01-tags-dialog-light.png')
    body = _body_text(drv)
    assert f'接线测试_{USER_TAG}_分类A' in body or '分类A' in body


def test_02_grouped_by_category(drv, fixture):
    """点选区按分类分组：组头=分类名＋组内标签＋「未分类」尾组。"""
    body = _body_text(drv)
    # 组头 = 分类A / 分类B
    assert f'接线测试_{USER_TAG}_分类A' in body, '缺分类A组头'
    assert f'接线测试_{USER_TAG}_分类B' in body, '缺分类B组头'
    # 组内标签
    assert f'接线测试_{USER_TAG}_标签1' in body, '缺分类A组内标签1'
    assert f'接线测试_{USER_TAG}_标签2' in body, '缺分类A组内标签2'
    assert f'接线测试_{USER_TAG}_标签3' in body, '缺分类B组内标签3'
    # 未分类尾组（真实库未分类标签存在；至少组织名 TAB 前缀的未分类标签可见）+ 真实库未分类标签之一
    assert '未分类' in body, '缺「未分类」尾组'
    assert 'INT1332' in body, '未分类组应含真实库未分类标签 INT1332'
    _shot(drv, '02-grouped-light.png')


def test_03_chip_linkage_in_groups(drv, fixture):
    """选中/移除 chips 后分组内联动正确。"""
    tag1 = f'接线测试_{USER_TAG}_标签1'
    tag2 = f'接线测试_{USER_TAG}_标签2'
    tag3 = f'接线测试_{USER_TAG}_标签3'
    cat_a = f'接线测试_{USER_TAG}_分类A'
    # 点选分类A组内标签1 → 成为 chip 且从候选消失
    WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, f"//button[normalize-space(.)='{tag1}']"))
    _js_click(drv, f"//button[normalize-space(.)='{tag1}']")
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='移除 {tag1}']"))
    assert not drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{tag1}']"), \
        '已选标签不应留在候选区'
    assert drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{tag2}']"), \
        '组内其余标签应保留'
    assert drv.find_elements(By.XPATH, f"//p[normalize-space(.)='{cat_a}']"), \
        '分类A组头应保留（组内还有标签2）'
    # 再点标签2 → 分类A组头隐藏（组内全选），未分类与分类B仍在
    _js_click(drv, f"//button[normalize-space(.)='{tag2}']")
    WebDriverWait(drv, 8).until(
        lambda d: not d.find_elements(By.XPATH, f"//p[normalize-space(.)='{cat_a}']"))
    assert drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{tag3}']"), \
        '分类B组内标签应保留'
    assert drv.find_elements(By.XPATH, "//p[normalize-space(.)='未分类']"), '未分类尾组应保留'
    # 移除 chip → 标签回候选、组头还原
    _js_click(drv, f"//button[@aria-label='移除 {tag1}']")
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, f"//button[normalize-space(.)='{tag1}']"))
    assert drv.find_elements(By.XPATH, f"//p[normalize-space(.)='{cat_a}']"), \
        '移除 chip 后分类A组头应还原'


def test_04_submit_add_tags_and_readback(drv, fixture):
    """勾选 2 个标签提交 → toast 成功；GET /testcases/{id} 回读一致。"""
    tag1 = f'接线测试_{USER_TAG}_标签1'
    tag3 = f'接线测试_{USER_TAG}_标签3'
    # 清掉上一步残留 chip（test_03 结束时 chips=[标签2]），再选 标签1 + 标签3
    for chip in drv.find_elements(By.XPATH, "//button[starts-with(@aria-label, '移除 接线测试_INT2102_')]"):
        drv.execute_script('arguments[0].click()', chip)
    time.sleep(0.5)
    for tag in (tag1, tag3):
        if not drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{tag}']"):
            continue
        _js_click(drv, f"//button[normalize-space(.)='{tag}']")
    _js_click(drv, "//button[normalize-space(.)='确定']")
    _wait_text(drv, '批量操作执行成功', timeout=15)
    _shot(drv, '04-submitted-light.png')
    # Network 证据：POST /testcases/batch + GET /tags/by-category
    logs = _netlog(drv)
    assert any(l['method'] == 'GET' and 'tags/by-category' in l['url'] for l in logs), \
        f'未捕获 GET /tags/by-category: {[l for l in logs if "tags" in l["url"]]}'
    assert any(l['method'] == 'POST' and 'testcases/batch' in l['url'] for l in logs), \
        f'未捕获 POST /testcases/batch: {[l for l in logs if "batch" in l["url"]]}'
    # 回读：GET /testcases/{id} → tags 含新增标签
    for cid in fixture['case_ids']:
        _, detail = api._req('GET', f"/testcases/{cid}", token=_TOKEN)
        tags = ((detail or {}).get('data') or {}).get('tags') or []
        names = [t if isinstance(t, str) else t.get('name') for t in tags]
        assert tag1 in names and tag3 in names, \
            f'用例 {cid} 回读 tags 不含新增标签: {names}'


def test_05_remove_mode_and_rename_mode(drv):
    """移除模式 + 改名模式不回归（沿用 §5.3.7 三模式）。"""
    # 重新打开弹窗
    _js_click(drv, "//button[contains(., '批量管理标签')]")
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '批量管理标签')]"))
    # 移除模式
    _js_click(drv, "//label[contains(., '移除标签')]")
    _wait_text(drv, '已有标签（点击移除）：')
    assert '未分类' in _body_text(drv)
    # 改名模式
    _js_click(drv, "//label[contains(., '修改标签名字')]")
    _wait_text(drv, '原标签')
    _wait_text(drv, '新标签名')
    combos = drv.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
    assert combos, '改名模式应有原标签 Select'
    _shot(drv, '05-rename-mode-light.png')


def test_06_dark_theme(drv):
    """深色主题下弹窗分组渲染 + 截图。"""
    _set_theme(drv, '深色')
    _goto_my_cases(drv, USER_TAG)
    _select_my_cases(drv, USER_TAG)
    _open_tags_dialog(drv, USER_TAG)
    root_class = drv.execute_script('return document.documentElement.className')
    assert 'dark' in root_class, f'深色未生效: root={root_class}'
    _shot(drv, '06-tags-dialog-dark.png')


def test_07_network_evidence(drv):
    """Network 证据汇总：真实 /tags/by-category + /testcases/batch，无 mock 残留。"""
    logs = _netlog(drv)
    api_urls = [l['url'] for l in logs if '/api/' in l['url']]
    assert api_urls, '无任何 /api/ 请求'
    assert any('tags/by-category' in u for u in api_urls), \
        f'缺 GET /tags/by-category: {api_urls}'
    assert any('testcases/batch' in u for u in api_urls), \
        f'缺 POST /testcases/batch: {api_urls}'
    assert not any('mock' in u.lower() for u in api_urls), f'出现 mock 请求: {api_urls}'
    d = os.path.join(ARTIFACTS, '07-network')
    os.makedirs(d, exist_ok=True)
    summary = '\n'.join(
        f"  {l['method']:6} {l.get('status', '?')} {l['url'].split('/api/v1')[-1]}"
        for l in logs if '/api/' in l['url'])
    with open(os.path.join(d, 'netlog.json'), 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    with open(os.path.join(d, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write(summary + '\n')


def test_08_light_theme_restore(drv):
    """还原浅色主题。"""
    _set_theme(drv, '浅色')
    _goto(drv, '/dashboard')
    _wait_text(drv, '工作台', timeout=20)