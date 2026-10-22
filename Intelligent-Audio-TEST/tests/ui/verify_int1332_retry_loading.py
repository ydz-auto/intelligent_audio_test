# -*- coding: utf-8 -*-
"""INT-1332 返工：重试窗口加载态保持（P1 回归）浏览器验证。

场景：
- A 单删：首次 DELETE 挂起 → 20s 超时弹窗 → 点「重试」→ 重试请求 in-flight 期间
  行内按钮保持「删除中」+ disabled（P1 修复点），随后重试以成功响应完成。
- B 批量：批量 DELETE 挂起 → 20s 超时弹窗 → 点「重试」→ 页头「批量删除」按钮
  保持「删除中...」+ disabled（P1 修复点），随后重试以成功响应完成。

请求挂起/放行用注入的 window.fetch 包装（Page.addScriptToEvaluateOnNewDocument）：
命中 DELETE /api/v1/audios/{id} 时按 window.__dd 配置 holdMs 后放行，或直接
fulfill 伪造成功响应——后端收不到任何真实 DELETE，测试记录跑完由 SQL 硬删清理。
"""
import json
import os
import sys
import time

# Intelligent-Audio-TEST 仓库根（本文件在 tests/ui/ 下，三级 dirname 到根）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

FRONTEND = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5608')
API = os.environ.get('UI_API_BASE', 'http://127.0.0.1:5700')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1332_rework')
os.makedirs(ARTIFACTS, exist_ok=True)

TIMEOUT_SEC = 20  # DELETE_REQUEST_TIMEOUT_MS / 1000

WRAPPER_JS = r"""
(function () {
  if (window.__ddInstalled) return;
  window.__ddInstalled = true;
  window.__dd = { enabled: false, holdMs: 30000, fulfillBody: null, calls: 0 };
  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const args = arguments;
    const reqUrl = (typeof input === 'string') ? input : ((input && input.url) || '');
    const method = (init && init.method) || (typeof input === 'string' ? 'GET' : ((input && input.method) || 'GET'));
    const m = String(method).toUpperCase();
    const u = String(reqUrl);
    const isSingleDelete = m === 'DELETE' && /\/api\/v1\/audios\/[0-9]+(\?.*)?$/.test(u);
    const isBatchDelete = m === 'POST' && /\/api\/v1\/audios\/batch-action/.test(u);
    if (isSingleDelete || isBatchDelete) {
      const cfg = window.__dd;
      cfg.calls += 1;
      if (cfg.enabled) {
        return new Promise(function (resolve, reject) {
          setTimeout(function () {
            if (cfg.fulfillBody) {
              const body = cfg.fulfillBody;
              cfg.fulfillBody = null;
              resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }));
            } else {
              origFetch.apply(window, args).then(resolve, reject);
            }
          }, cfg.holdMs);
        });
      }
    }
    return origFetch.apply(window, args);
  };
})();
"""


def setup_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1500,950')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})

    # 驱动解析：Selenium 缓存同主版本最新（复用 conftest 口径）
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if os.path.isdir(cache_root):
        vers = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                vers.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
        if vers:
            drv_path = max(vers)[1]
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def body_text(drv):
    return drv.execute_script('return document.documentElement.textContent || ""')


def wait_until(drv, fn, timeout=30, desc=''):
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(drv, timeout).until(lambda d: fn(d))
    if desc:
        print(f'OK 等待: {desc}')


def click_modal_button(drv, text):
    from selenium.webdriver.common.by import By
    btns = drv.find_elements(By.CSS_SELECTOR, '.modal-confirmActions button')
    for b in btns:
        if text in (b.text or ''):
            drv.execute_script('arguments[0].click();', b)
            return b
    raise AssertionError(f'模态按钮「{text}」未找到')


def modal_title(drv):
    from selenium.webdriver.common.by import By
    els = drv.find_elements(By.CSS_SELECTOR, '.modal-title')
    return els[-1].text.strip() if els else ''


def find_row(drv, name_part):
    from selenium.webdriver.common.by import By
    rows = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
    for row in rows:
        try:
            name_el = row.find_element(By.CSS_SELECTOR, '.audio-name')
        except Exception:
            continue
        if name_part in (name_el.text or ''):
            return row
    return None


def row_delete_btn(row):
    return row.find_element(By.CSS_SELECTOR, 'button.btn.btn-danger')


def row_checkbox(row):
    return row.find_element(By.CSS_SELECTOR, 'input.audio-checkbox')


def shot(drv, name):
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    print(f'截图: {name}')
    return path


def main():
    # 前置：登录态（RSA-OAEP 口径）
    api = ApiClient(API)
    api.login('接线测试_admin', 'JieXianTest@2026')
    token, user = api.token, api.user
    print(f'登录 OK user.id={user.get("id")} db={api.health().get("database")}')

    drv = setup_driver()
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        # 注入 fetch 包装（每个新文档生效）
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': WRAPPER_JS})

        # 注入登录态并整页 boot
        drv.get(f'{FRONTEND}/#/login')
        WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, '.login-card'))
        payload = {
            'id': user.get('id', 0),
            'username': user.get('username', ''),
            'roleId': user.get('role_id'),
            'roleName': user.get('role_name', ''),
            'permissions': user.get('permissions', []),
        }
        drv.execute_script(
            'window.localStorage.setItem("auth_token", arguments[0]);'
            'window.localStorage.setItem("auth_user", arguments[1]);',
            token, json.dumps(payload),
        )
        drv.get(f'{FRONTEND}/')  # 整页重载，boot 读回登录态
        time.sleep(1.5)
        drv.get(f'{FRONTEND}/#/audio-import')
        wait_until(drv, lambda d: d.find_elements(By.CSS_SELECTOR, '.audio-name'), 30,
                   '音频列表渲染')
        print(f'页面标题: {drv.find_element(By.CSS_SELECTOR, ".page-title").text}')

        # ── A. 单删重试 in-flight 加载态 ──
        print('\n==== A. 单删重试 in-flight ====')
        row = find_row(drv, 'JieXian_INT1332_retry_1792694224_0.wav')
        assert row, '测试记录行未找到（_0）'
        dbtn = row_delete_btn(row)
        drv.execute_script('window.__dd = {enabled:true, holdMs:%d, fulfillBody:null, calls:0};' % (TIMEOUT_SEC * 1000 + 10000))
        dbtn.click()
        # 确认弹窗（删除音频 → 确定）
        wait_until(drv, lambda d: d.find_elements(By.CSS_SELECTOR, '.modal-confirm'), 10, '确认弹窗')
        assert '删除音频' in modal_title(drv), f'确认弹窗标题异常: {modal_title(drv)}'
        click_modal_button(drv, '确定')
        # 首删 in-flight：行内按钮「删除中」+ disabled
        wait_until(drv, lambda d: (lambda r: r and '删除中' in row_delete_btn(r).text)(find_row(drv, 'JieXian_INT1332_retry_1792694224_0.wav')), 6,
                   '首删加载态')
        r = find_row(drv, 'JieXian_INT1332_retry_1792694224_0.wav')
        assert r and row_delete_btn(r).get_attribute('disabled') is not None, '首删按钮未禁用'
        shot(drv, 'A1_first_delete_loading.png')
        # 超时弹窗
        wait_until(drv, lambda d: '删除超时' in modal_title(drv), TIMEOUT_SEC + 12, '删除超时弹窗')
        assert modal_title(drv) == '删除超时', f'超时弹窗标题: {modal_title(drv)}'
        # 配置重试腿：hold 8s 后伪造成功
        drv.execute_script('window.__dd.holdMs = 8000; window.__dd.fulfillBody = {success:true, code:0, message:"音频文件已删除", data:null};')
        click_modal_button(drv, '重试')
        # P1：重试请求 in-flight 期间，行内按钮保持「删除中」+ disabled
        time.sleep(2.0)
        r = find_row(drv, 'JieXian_INT1332_retry_1792694224_0.wav')
        assert r, '重试期间行未找到'
        rb = row_delete_btn(r)
        state_ok = (rb.text or '').strip() == '删除中' and rb.get_attribute('disabled') is not None
        print(f'重试 in-flight 行内按钮: text={rb.text.strip()!r} disabled={rb.get_attribute("disabled")!r}')
        shot(drv, 'A2_retry_inflight_single.png')
        assert state_ok, f'P1 失败：重试 in-flight 按钮未保持「删除中」+disabled（text={rb.text.strip()!r} disabled={rb.get_attribute("disabled")!r}）'
        # 重试成功弹窗
        wait_until(drv, lambda d: '删除成功' in modal_title(drv), 12, '删除成功弹窗')
        shot(drv, 'A3_retry_success.png')
        click_modal_button(drv, '确定')
        wait_until(drv, lambda d: not d.find_elements(By.CSS_SELECTOR, '.modal-confirm'), 8, '关闭成功弹窗')
        calls = drv.execute_script('return window.__dd.calls;')
        print(f'PASS A：单删重试完成，拦截 DELETE 调用次数={calls}')

        # ── B. 批量删除重试 in-flight ──
        print('\n==== B. 批量重试 in-flight ====')
        # 选中剩余两条测试记录
        for part in ('JieXian_INT1332_retry_1792694224_1.wav', 'JieXian_INT1332_retry_1792694224_2.wav'):
            row = find_row(drv, part)
            assert row, f'测试记录行未找到（{part}）'
            cb = row_checkbox(row)
            drv.execute_script('arguments[0].click();', cb)
        # 页头批量删除按钮
        btns = drv.find_elements(By.CSS_SELECTOR, '.header-right .action-buttons button')
        batch_btn = None
        for b in btns:
            if '批量删除' in (b.text or ''):
                batch_btn = b
                break
        assert batch_btn, '页头「批量删除」按钮未找到'
        drv.execute_script('window.__dd = {enabled:true, holdMs:%d, fulfillBody:null, calls:0};' % (TIMEOUT_SEC * 1000 + 10000))
        drv.execute_script('arguments[0].click();', batch_btn)
        wait_until(drv, lambda d: d.find_elements(By.CSS_SELECTOR, '.modal-confirm'), 10, '批量确认弹窗')
        assert '批量删除' in modal_title(drv), f'批量确认弹窗标题: {modal_title(drv)}'
        click_modal_button(drv, '确定')
        # 批量 in-flight：页头按钮「删除中...」+ disabled
        wait_until(drv, lambda d: any('删除中' in (b.text or '') for b in d.find_elements(By.CSS_SELECTOR, '.header-right .action-buttons button')), 6,
                   '批量加载态')
        bb = None
        for b in drv.find_elements(By.CSS_SELECTOR, '.header-right .action-buttons button'):
            if '删除中' in (b.text or ''):
                bb = b
                break
        assert bb and bb.get_attribute('disabled') is not None, '批量首删按钮未禁用'
        shot(drv, 'B1_batch_delete_loading.png')
        # 超时弹窗
        wait_until(drv, lambda d: '批量删除超时' in modal_title(drv), TIMEOUT_SEC + 12, '批量删除超时弹窗')
        assert modal_title(drv) == '批量删除超时', f'批量超时弹窗标题: {modal_title(drv)}'
        # 配置重试腿
        drv.execute_script('window.__dd.holdMs = 8000; window.__dd.fulfillBody = {success:true, code:0, message:"成功删除 2 个音频", data:null};')
        click_modal_button(drv, '重试')
        time.sleep(2.0)
        # P1：批量重试 in-flight，页头按钮保持「删除中...」+ disabled
        bb = None
        for b in drv.find_elements(By.CSS_SELECTOR, '.header-right .action-buttons button'):
            if '删除中' in (b.text or ''):
                bb = b
                break
        state_ok = bb is not None and (bb.text or '').strip() == '删除中...' and bb.get_attribute('disabled') is not None
        print(f'批量重试 in-flight 页头按钮: {bb.text.strip() if bb else None!r} disabled={bb.get_attribute("disabled") if bb else None!r}')
        shot(drv, 'B2_retry_inflight_batch.png')
        assert state_ok, f'P1 失败：批量重试 in-flight 按钮未保持「删除中...」+disabled'
        # 批量重试成功弹窗
        wait_until(drv, lambda d: '删除成功' in modal_title(drv), 12, '批量删除成功弹窗')
        shot(drv, 'B3_retry_success_batch.png')
        click_modal_button(drv, '确定')
        wait_until(drv, lambda d: not d.find_elements(By.CSS_SELECTOR, '.modal-confirm'), 8, '关闭批量成功弹窗')
        calls = drv.execute_script('return window.__dd.calls;')
        print(f'PASS B：批量重试完成，拦截 DELETE 调用次数={calls}')

        # console 错误检查
        logs = drv.get_log('browser')
        severe = [l for l in logs if l.get('level') in ('SEVERE', 'ERROR')]
        aborts = [l for l in logs if l.get('level') == 'WARNING' and ('aborted' in (l.get('message') or '').lower() or 'timed out' in (l.get('message') or '').lower())]
        if severe:
            print('SEVERE/ERROR console:', [l['message'][:200] for l in severe])
        else:
            print('console 无 SEVERE/ERROR')
        print('主动中止/超时 warn（预期）:', len(aborts))

        print('\n=== 全部 PASS ===')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
