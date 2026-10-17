# -*- coding: utf-8 -*-
"""INT-648 标签管理页 infra mock→api 接线浏览器验收（真实 Chrome headless + 真实后端）。

前置：本 worktree frontend-react dev server（rsbuild dev --port <空闲>，/api 代理 → :5000
常驻后端，AUTH_MODE=off）；本文件直接访问 /TagManagement，dev_user 全放行。

覆盖验收标准「浏览器实测核心链路并附图」：
1. 加载真实数据：GET /api/v1/tags + /api/v1/tags/categories → 右表/左树渲染（非 mock 计数）
2. 分类创建（POST /tags/categories）→ 左树出现新分类、计数联动
3. 标签创建（POST /tags）→ 右表出现新标签、所属分类列正确
4. 标签编辑（PUT /tags/{id}）→ 表内名称更新
5. 非空分类删除拦截（tagCount>0 删除钮禁用 + Tooltip）
6. 标签删除（DELETE /tags/{id}?cascade=false）→ 表内消失
7. 分类删除（DELETE /tags/categories/{id}）→ 左树还原
8. 跨页联动：标签页增改后 → /testcases/by-tag 标签 facet 含新标签（同 ['tags'] query 前缀）
9. Network 证据：以上动作全部真实请求（__netLog fetch 包装捕获）
10. 浅/深色截图（load / CRUD 后）

数据卫生：验收用唯一前缀 INT648验收* 的 fixture，UI 删除 + 最后 API 兜底清理（finally），
验收后不留残留。
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5275')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'tests', 'ui', 'artifacts', 'int648_tag_api_wiring')

CAT_NAME = 'INT648验收分类'
TAG_NAME = 'INT648验收标签'
TAG_NAME2 = 'INT648验收标签改'

# 常驻后端 api_gateway（rsbuild proxy 目标）
API = os.environ.get('API_BASE', 'http://localhost:5000/api/v1')


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


def _save(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
    except Exception:
        pass


def _body(drv):
    return drv.execute_script('return document.body ? document.body.textContent : ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(d))


def _click_btn(drv, text, timeout=12):
    el = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.XPATH, f"//button[contains(normalize-space(.), '{text}')]"))
    el.click()


def _install_netlog(drv):
    """注入 fetch 包装：所有 /api/ 请求记录 url/method/status 到 window.__netLog。"""
    script = r'''
    (() => {
      if (window.__netLogInstalled) return;
      window.__netLog = [];
      const origFetch = window.fetch.bind(window);
      window.fetch = async (...args) => {
        const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url);
        const method = (args[1] && args[1].method) || 'GET';
        const started = performance.now();
        try {
          const resp = await origFetch(...args);
          window.__netLog.push({
            method, url: String(url), status: resp.status,
            ms: Math.round(performance.now() - started),
          });
          return resp;
        } catch (e) {
          window.__netLog.push({ method, url: String(url), status: -1, ms: 0, error: String(e) });
          throw e;
        }
      };
      window.__netLogInstalled = true;
    })();
    '''
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': script})


def _netlog(drv):
    try:
        return drv.execute_script('return window.__netLog || []')
    except Exception:
        return []


def _api_req(method, path, body=None):
    """直接打后端（兜底清理 / 断言后端状态用）。"""
    import urllib.request
    url = API + path
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(body).encode('utf-8')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return None, {'_error': str(e)}


def _backend_tags():
    _, data = _api_req('GET', '/tags?page=1&per_page=100')
    return (data.get('data') or {}).get('items') or []


def _backend_cats():
    _, data = _api_req('GET', '/tags/categories?page=1&per_page=100')
    return (data.get('data') or {}).get('items') or []


def _cleanup_backend():
    """兜底：按前缀删光本卡验收 fixture（分类须为空，先删标签再删分类）。"""
    for t in _backend_tags():
        if t.get('name', '').startswith('INT648验收'):
            _api_req('DELETE', f"/tags/{t['id']}?cascade=false")
    for c in _backend_cats():
        if c.get('name', '').startswith('INT648验收'):
            _api_req('DELETE', f"/tags/categories/{c['id']}")


@pytest.fixture(scope='module')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    _install_netlog(_DRIVER)
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
        _save(item.name, _DRIVER)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _select_category_in_dialog(drv, cat_name):
    """Base UI Select：点触发器 → 点选项。"""
    trig = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']"))
    trig.click()
    opt = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH,
                                 f"//*[@role='option' and contains(normalize-space(.), '{cat_name}')]"))
    opt.click()
    time.sleep(0.3)


def _open_row_action(drv, aria_label):
    el = WebDriverWait(drv, 12).until(
        lambda d: d.find_element(By.CSS_SELECTOR, f"[aria-label='{aria_label}']"))
    el.click()


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_01_load_real_data(drv):
    _cleanup_backend()
    _goto(drv, '/TagManagement')
    _wait_text(drv, '标签管理')
    _wait_text(drv, '未分类')
    _wait_text(drv, '已加载全部')
    # 右表渲染真实后端标签（与后端计数一致，非 mock 固定计数）
    expect_total = len(_backend_tags())
    _wait_text(drv, f'共 {expect_total} 个标签')
    _wait_text(drv, 'INT308')  # 后端真实标签之一
    # 0 个分类时左树只有「未分类」固定项 + 本卡 fixture 不残留
    assert 'INT648验收分类' not in _body(drv)
    _save('01-light-load', drv)


def test_02_create_category(drv):
    _click_btn(drv, '新建')  # 分类树「新建」
    _wait_text(drv, '新建分类')
    drv.find_element(By.ID, 'category-name').send_keys(CAT_NAME)
    drv.find_element(By.ID, 'category-desc').send_keys('INT648 验收接线分类描述')
    _click_btn(drv, '创建')
    _wait_text(drv, '分类创建成功')
    # 左树出现新分类；计数=共 1 个
    _wait_text(drv, CAT_NAME)
    _wait_text(drv, '共 1 个')
    # 后端真实落库
    cats = [c for c in _backend_cats() if c['name'] == CAT_NAME]
    assert len(cats) == 1, f'后端未查到新分类: {_backend_cats()}'
    # Network 证据
    logs = _netlog(drv)
    assert any(l['method'] == 'POST' and l['url'].endswith('/tags/categories')
               and l['status'] == 201 for l in logs), f'未捕获 POST /tags/categories: {logs}'


def test_03_create_tag(drv):
    _click_btn(drv, '新建标签')
    _wait_text(drv, '新建标签')
    drv.find_element(By.ID, 'tag-name').send_keys(TAG_NAME)
    _select_category_in_dialog(drv, CAT_NAME)
    drv.find_element(By.ID, 'tag-desc').send_keys('INT648 验收接线标签描述')
    _click_btn(drv, '创建')
    _wait_text(drv, '标签创建成功')
    # 右表出现新标签（所属分类列含分类名）
    _wait_text(drv, TAG_NAME)
    _wait_text(drv, CAT_NAME)
    # 后端真实落库
    tags = [t for t in _backend_tags() if t['name'] == TAG_NAME]
    assert len(tags) == 1, f'后端未查到新标签: {_backend_tags()}'
    assert tags[0].get('category_name') == CAT_NAME
    logs = _netlog(drv)
    assert any(l['method'] == 'POST' and l['url'].endswith('/tags') and l['status'] == 201
               for l in logs), f'未捕获 POST /tags: {logs}'
    _save('02-light-crud', drv)


def test_04_edit_tag(drv):
    _open_row_action(drv, f'编辑标签 {TAG_NAME}')
    _wait_text(drv, '编辑标签')
    name = drv.find_element(By.ID, 'tag-name')
    name.clear()
    name.send_keys(TAG_NAME2)
    _click_btn(drv, '保存')
    _wait_text(drv, '标签更新成功')
    _wait_text(drv, TAG_NAME2)
    tags = [t for t in _backend_tags() if t['name'] == TAG_NAME2]
    assert len(tags) == 1, f'后端未查到改名标签: {_backend_tags()}'
    logs = _netlog(drv)
    assert any(l['method'] == 'PUT' and '/tags/' in l['url'] and l['status'] == 200
               for l in logs), f'未捕获 PUT /tags: {logs}'


def test_05_nonempty_category_delete_blocked(drv):
    # 选中分类（点树中分类行 → 右表只显该分类标签）
    el = WebDriverWait(drv, 12).until(
        lambda d: d.find_element(By.XPATH, f"//button[contains(., '{CAT_NAME}')]"))
    el.click()
    _wait_text(drv, '共 1 个标签')
    # 删除钮 disabled（tagCount>0 拦截）
    del_btn = drv.find_element(By.CSS_SELECTOR, f"[aria-label='删除分类 {CAT_NAME}']")
    assert del_btn.is_enabled() is False, '非空分类删除钮应禁用'


def test_06_delete_tag(drv):
    _open_row_action(drv, f'删除标签 {TAG_NAME2}')
    _wait_text(drv, f'确定删除标签「{TAG_NAME2}」吗？')
    _click_btn(drv, '删除')
    _wait_text(drv, '标签删除成功')
    tags = [t for t in _backend_tags() if t['name'] == TAG_NAME2]
    assert tags == [], f'标签未删除: {_backend_tags()}'
    logs = _netlog(drv)
    assert any(l['method'] == 'DELETE' and '/tags/' in l['url']
               and 'cascade=false' in l['url'] and l['status'] == 200
               for l in logs), f'未捕获 DELETE /tags/{{id}}?cascade=false: {logs}'


def test_07_delete_category(drv):
    # 仍选中该分类（test_05 选中），标签已删 → 分类为空 → 删除钮启用
    _wait_text(drv, '共 0 个标签')
    _open_row_action(drv, f'删除分类 {CAT_NAME}')
    _wait_text(drv, f'确定删除分类「{CAT_NAME}」吗？')
    _click_btn(drv, '删除')
    _wait_text(drv, '分类删除成功')
    cats = [c for c in _backend_cats() if c['name'] == CAT_NAME]
    assert cats == [], f'分类未删除: {_backend_cats()}'
    logs = _netlog(drv)
    assert any(l['method'] == 'DELETE' and '/tags/categories/' in l['url']
               and l['status'] == 200 and '?cascade' not in l['url']
               for l in logs), f'未捕获 DELETE /tags/categories: {logs}'


def test_08_cross_page_linkage(drv):
    # 重建分类+标签（用于跨页联动；分类已删空需先建）
    _click_btn(drv, '新建')  # 分类
    _wait_text(drv, '新建分类')
    drv.find_element(By.ID, 'category-name').send_keys(CAT_NAME)
    _click_btn(drv, '创建')
    _wait_text(drv, '分类创建成功')
    _click_btn(drv, '新建标签')
    _wait_text(drv, '新建标签')
    drv.find_element(By.ID, 'tag-name').send_keys(TAG_NAME + '联动')
    _select_category_in_dialog(drv, CAT_NAME)
    _click_btn(drv, '创建')
    _wait_text(drv, '标签创建成功')
    _wait_text(drv, TAG_NAME + '联动')
    _save('03-light-linkage', drv)
    # 跨页：用例页 by-tag 视图 → 标签 facet 含新标签（真实 GET /tags 渲染；
    # facet 弹层默认收起，需点开「标签 全部」触发器再断言选项）
    try:
        _goto(drv, '/testcases/by-tag')
        # 打开标签 facet（触发器按钮文本 =「标签 全部」）
        facet_btn = WebDriverWait(drv, 20).until(
            lambda d: d.find_element(
                By.XPATH, "//button[contains(normalize-space(.), '标签') and contains(normalize-space(.), '全部')]"))
        facet_btn.click()
        _wait_text(drv, TAG_NAME + '联动', timeout=15)
        _save('04-by-tag-facet', drv)
    finally:
        # 清理联动 fixture（UI 已切页，直接 API 删）
        for t in _backend_tags():
            if t['name'] == TAG_NAME + '联动':
                _api_req('DELETE', f"/tags/{t['id']}?cascade=false")
        for c in _backend_cats():
            if c['name'] == CAT_NAME:
                _api_req('DELETE', f"/tags/categories/{c['id']}")


def test_09_dark_theme(drv):
    drv.execute_script(
        "try { localStorage.setItem('iatp:theme:v1:mode', 'dark') } catch (e) {}")
    _goto(drv, '/TagManagement')
    _wait_text(drv, '标签管理')
    _wait_text(drv, '未分类')
    root_class = drv.execute_script('return document.documentElement.className')
    assert 'dark' in root_class, f'深色未生效: root={root_class}'
    _save('05-dark-load', drv)


def _perf_network(drv):
    """从 CDP performance log 提取网络条目（跨整 session，不受页面刷新影响）。"""
    entries = []
    try:
        for line in drv.get_log('performance'):
            try:
                outer = json.loads(line.get('message', '{}'))
                msg = outer.get('message', {})
                if not isinstance(msg, dict):
                    msg = outer
                method = msg.get('method') or ''
                params = msg.get('params') or {}
                if method == 'Network.requestWillBeSent':
                    req = params.get('request', {})
                    url = req.get('url', '')
                    if '/api/' in url:
                        entries.append({
                            'method': (req.get('method') or 'GET'),
                            'url': url,
                            'requestId': params.get('requestId'),
                            'timestamp': params.get('timestamp'),
                        })
                elif method == 'Network.responseReceived':
                    resp = params.get('response', {})
                    url = resp.get('url', '')
                    if '/api/' in url:
                        status = resp.get('status')
                        for e in entries:
                            if e.get('requestId') == params.get('requestId'):
                                e['status'] = status
                                break
            except Exception:
                continue
    except Exception:
        pass
    return entries


def test_10_network_evidence(drv):
    # fetch 包装 netlog（当前文档内）
    logs = _netlog(drv)
    real = [l for l in logs if '/api/' in l['url']]
    assert real, '无任何 /api/ 请求（页面未走真实接口？）'
    # CDP performance 日志（跨整 session，含全部 CRUD 请求）
    perf = _perf_network(drv)
    with_status = [e for e in perf if 'status' in e]
    assert with_status, 'performance 日志无带状态码的 /api/ 请求'
    summary = '\n'.join(
        f"  {e['method']:6} {e.get('status', '?')} {e['url'].split('/api/v1')[-1]}"
        for e in sorted(with_status, key=lambda x: x.get('timestamp', 0)))
    print('\n[NETLOG] 跨整 session 真实请求摘要:\n' + summary)
    # 断言真实 CRUD 端点都在（验收标准核心链路）
    def has(method, fragment):
        return any(e['method'] == method and fragment in e['url'] for e in with_status)

    assert has('GET', '/api/v1/tags/categories'), '缺 GET /tags/categories'
    assert has('GET', '/api/v1/tags?'), '缺 GET /tags'
    assert has('POST', '/api/v1/tags/categories'), '缺 POST /tags/categories'
    assert has('POST', '/api/v1/tags'), '缺 POST /tags'
    assert has('PUT', '/api/v1/tags/'), '缺 PUT /tags/{id}'
    assert has('DELETE', '/api/v1/tags/'), '缺 DELETE /tags/{id}'
    assert any(e['method'] == 'DELETE' and 'cascade=false' in e['url']
               for e in with_status), '缺 DELETE /tags/{id}?cascade=false'
    assert has('DELETE', '/api/v1/tags/categories/'), '缺 DELETE /tags/categories/{id}'
    # 写入证据文件（供评论附件/复现）
    d = os.path.join(ARTIFACTS, '10-network')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'perf_netlog.json'), 'w', encoding='utf-8') as f:
        json.dump(with_status, f, ensure_ascii=False, indent=2)
    with open(os.path.join(d, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write(summary + '\n')


def test_11_no_fixture_residue(drv):
    _cleanup_backend()
    tags = [t for t in _backend_tags() if t['name'].startswith('INT648验收')]
    cats = [c for c in _backend_cats() if c['name'].startswith('INT648验收')]
    assert tags == [], f'验收 fixture 残留标签: {tags}'
    assert cats == [], f'验收 fixture 残留分类: {cats}'
