# -*- coding: utf-8 -*-
"""INT-1362 复测（测试工程师）：P1 修复后开始测试「新增/编辑 API」弹窗带端点 API 保存成功 + 无回归。

复测重点（打回原文，§2.3 只复测失败项与修复相关部分）：
- P1 核心：开始测试「新增/编辑 API」弹窗新建/编辑带端点 API 保存成功（POST /apis 201 / PUT 200，不再 400）；
  用页内 fetch 打点捕获请求体，确认端点四整数 max_process/max_timeout/max_audio_duration/priority 齐全、无 api_url。
- 无回归：设备页抽屉/列表/详情/健康检查无 Master URL / apiUrl / apiUrlStatus；
  健康检查「端点状态」行绑 endpointsStatus；跨组件同步。
- 深浅色截图 + Network 证据；防串库核验；测试数据卫生（删「接线测试_INT1362_」前缀记录）。

环境：dev server :5310（/api → 真实库栈 :5700，AUTH_MODE=dev 表单登录）。
账号：接线测试_admin / JieXianTest@2026。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5310')
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, 'artifacts', 'int1362_retest')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
THEME_KEY = 'iatp:theme:v1:mode'
TOKEN_KEY = 'iatp:auth:token:v1'
NAME_PREFIX = '接线测试_INT1362_复测_'
KNOWN_NOISE = ('/algorithm/options', '/algorithm/definitions')

_FAILURES = []


def _check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
    if not cond:
        _FAILURES.append(name)


FETCH_PATCH_JS = r"""
(function () {
  try {
    if (window.__int1362Patched) return
    window.__int1362Patched = true
    window.__int1362Captured = []
    const orig = window.fetch.bind(window)
    window.fetch = function (input, init) {
      const method = ((init && init.method) || (input && input.method) || 'GET')
      const url = typeof input === 'string' ? input : (input && input.url) || ''
      let bodyText = null
      try {
        if (init && init.body) bodyText = typeof init.body === 'string' ? init.body : JSON.stringify(init.body)
      } catch (e) {}
      if (url.indexOf('/api/v1/apis') !== -1) {
        window.__int1362Captured.push({ method, url, body: bodyText, at: Date.now() })
      }
      return orig(input, init).then(function (res) {
        if (url.indexOf('/api/v1/apis') !== -1) {
          try {
            res.clone().json().then(function (j) {
              for (const c of window.__int1362Captured) {
                if (c.url === url && c.method === method && c.status === undefined) {
                  c.status = res.status
                  c.respBody = j
                  break
                }
              }
            }).catch(function () {})
          } catch (e) {}
        }
        return res
      })
    }
  } catch (e) {}
})()
"""


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    drv = webdriver.Chrome(options=options, service=Service())
    drv.set_page_load_timeout(45)
    # CDP 预注入：fetch 打点跨整页导航存活（Chrome 155 无 Network.setRequestInterception）
    try:
        drv.execute_cdp_cmd('Page.enable', {})
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH_JS})
    except Exception as e:
        print(f'[i] CDP 预注入失败（将降级为当前页注入）：{e}')
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.textContent || ""'))


def _visible_options(drv):
    return [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]


def _select_first_option(drv, scope_el):
    """在 scope_el 内点开 Select 触发器并选第一个可见选项（base-ui：JS click）。"""
    trig = scope_el.find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    _js_click(drv, trig)
    WebDriverWait(drv, 5).until(lambda d: len(_visible_options(drv)) > 0)
    opts = _visible_options(drv)
    if not opts:
        raise AssertionError('Select 无可见选项')
    _js_click(drv, opts[0])
    time.sleep(0.6)


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem(arguments[0], arguments[1])", THEME_KEY, theme)
    drv.refresh()
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _shot(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    except Exception:
        pass


def _network_requests(drv, path_substr):
    reqs = {}
    resp = {}
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            ev = inner.get('method')
            p = inner.get('params', {})
            if ev == 'Network.requestWillBeSent':
                r = p.get('request', {})
                reqs[p.get('requestId')] = (r.get('url', ''), r.get('method', ''))
            elif ev == 'Network.responseReceived':
                resp[p.get('requestId')] = p.get('response', {}).get('status')
    except Exception as e:
        return [{'error': str(e)}]
    out = []
    for rid, (url, method) in reqs.items():
        if path_substr in url:
            out.append({'url': url, 'method': method, 'status': resp.get(rid)})
    return out


def _inject_fetch_capture(drv):
    """页内 window.fetch 打点：捕获 /api/v1/apis 的 method/url/请求体/响应状态（Chrome 155 无 Network.setRequestInterception）。"""
    js = """
    (function () {
      if (window.__int1362Captured) return 'already'
      window.__int1362Captured = []
      const orig = window.fetch.bind(window)
      window.fetch = function (input, init) {
        const method = (init && init.method) || (input && input.method) || 'GET'
        const url = typeof input === 'string' ? input : (input && input.url) || ''
        let bodyText = null
        try {
          if (init && init.body) bodyText = typeof init.body === 'string' ? init.body : JSON.stringify(init.body)
        } catch (e) {}
        if (url.indexOf('/api/v1/apis') !== -1 || url.indexOf('/apis') !== -1) {
          window.__int1362Captured.push({ method, url, body: bodyText, at: Date.now() })
        }
        return orig(input, init).then(function (res) {
          if (url.indexOf('/api/v1/apis') !== -1 || url.indexOf('/apis') !== -1) {
            try {
              res.clone().json().then(function (j) {
                for (const c of window.__int1362Captured) {
                  if (c.url === url && c.method === method && c.status === undefined) {
                    c.status = res.status
                    c.respBody = j
                    break
                  }
                }
              }).catch(function () {})
            } catch (e) {}
          }
          return res
        })
      }
      return 'ok'
    })()
    """
    return drv.execute_script(js)


def _get_captured(drv):
    return drv.execute_script('return window.__int1362Captured || []')


def _cleanup_test_apis(drv):
    token = drv.execute_script('return window.localStorage.getItem(arguments[0])', TOKEN_KEY)
    if not token:
        print('[i] 无 token，跳过 fetch 清理')
        return
    js = """
    const done = arguments[arguments.length - 1]
    const prefix = arguments[0]
    const token = arguments[1]
    const headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }
    fetch('/api/v1/apis', { headers })
      .then(r => r.json())
      .then(list => {
        const arr = Array.isArray(list) ? list
          : (list && list.data && Array.isArray(list.data.items)) ? list.data.items
          : Array.isArray(list.items) ? list.items : []
        const targets = arr.filter(a => (a.name || '').startsWith(prefix))
        return Promise.all(targets.map(a =>
          fetch('/api/v1/apis/' + a.id, { method: 'DELETE', headers })
            .then(r => ({ id: a.id, name: a.name, status: r.status }))))
      })
      .then(res => done(res))
      .catch(e => done({ error: String(e) }))
    """
    try:
        res = drv.execute_async_script(js, NAME_PREFIX, token)
        print(f'[i] 清理复测 API：{json.dumps(res, ensure_ascii=False)}')
    except Exception as e:
        print(f'[i] 清理失败：{e}')


def _dialog_scope(drv, title_text):
    return drv.find_element(By.XPATH, f"//*[contains(@role,'dialog')][.//*[contains(., '{title_text}')]]")


def _login(drv):
    drv.get(BASE + '/login')
    time.sleep(1.0)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)
    if '/login' in drv.current_url:
        raise AssertionError('登录失败：仍在 /login')
    print('[i] 登录成功')


def _db_check(tag):
    with urllib.request.urlopen('http://127.0.0.1:5700/health', timeout=10) as r:
        h = json.loads(r.read().decode('utf-8'))
    ok = h.get('database') == 'intelligent_audio_test'
    _check(f'防串库{tag}：真实库栈 database=intelligent_audio_test', ok, detail=f"db={h.get('database')}")
    return h


def _four_int_inputs(drv, scope_el):
    found = {}
    for ph in ['名称', '优先级', '最大进程', '超时(s)', '音频时长(s)']:
        els = scope_el.find_elements(By.XPATH, f".//input[@placeholder='{ph}']")
        if els:
            found[ph] = els[-1]
    return found


def _new_api_dialog_flow(drv, api_name, endpoint_url):
    """开始测试 → 新增 API 弹窗：填名称+端点+算法，保存；返回捕获的 POST 记录。"""
    _goto(drv, '/start-test?step=1')
    _wait_text(drv, '开始测试', 20)
    time.sleep(1.5)
    btns = drv.find_elements(By.TAG_NAME, 'button')
    add_api = [b for b in btns if b.text.strip() == '新增 API' and b.is_displayed()]
    if not add_api:
        raise AssertionError('开始测试页「新增 API」按钮未找到')
    _js_click(drv, add_api[0])
    _wait_text(drv, '新增 API', 8)
    time.sleep(1.0)
    dlg = _dialog_scope(drv, '新增 API')
    dtxt = dlg.text
    _check('弹窗无 apiUrl 字段（无「API 端点」Master URL 标签）', 'API 端点' not in dtxt)
    _check('弹窗含「端点列表」+「添加端点」', '端点列表' in dtxt and '添加端点' in dtxt)
    dlg.find_element(By.XPATH, ".//button[contains(., '添加端点')]").click()
    time.sleep(0.8)
    dlg_url = dlg.find_element(By.XPATH, ".//input[@aria-label='端点 URL']")
    _check('弹窗端点行出现', dlg_url.is_displayed())
    four = _four_int_inputs(drv, dlg)
    _check('弹窗端点行四整数输入齐全（优先级/最大进程/超时/音频时长）',
           all(k in four for k in ['优先级', '最大进程', '超时(s)', '音频时长(s)']),
           detail=str(list(four.keys())))
    name_inp = dlg.find_element(By.ID, 'api-name')
    name_inp.clear()
    name_inp.send_keys(api_name)
    dlg_url.send_keys(endpoint_url)
    _select_first_option(drv, dlg)
    time.sleep(0.5)
    _shot('01_start_dialog_filled_light', drv)
    # 保存
    drv.get_log('performance')
    save_btn = dlg.find_element(By.XPATH, ".//button[contains(., '保存')]")
    _js_click(drv, save_btn)
    try:
        _wait_text(drv, 'API 已保存', 12)
        save_ok = True
    except Exception:
        save_ok = False
    _check('保存 toast「API 已保存」', save_ok)
    time.sleep(1.5)
    caps = _get_captured(drv)
    posts = [c for c in caps if c['method'] == 'POST' and c.get('status') is not None]
    posts_all = [c for c in caps if c['method'] == 'POST']
    _check('Network: POST /api/v1/apis 返回 <300（P1 修复核心，不再 400）',
           any(c.get('status', 0) < 300 for c in posts),
           detail=json.dumps(posts[-1:] if posts else posts_all[-1:], ensure_ascii=False))
    return posts_all or posts


def run_steps(drv):
    _db_check('①')
    _login(drv)
    _inject_fetch_capture(drv)

    # ── P1 核心：开始测试弹窗新建带端点 API ──
    api_name = NAME_PREFIX + '弹窗API'
    ep_url = 'http://127.0.0.1:5700/v1/test/retest-dialog'
    posts = _new_api_dialog_flow(drv, api_name, ep_url)
    # 请求体断言（P1 根因：端点 DTO 缺 max_audio_duration/priority）
    if posts:
        p = posts[-1]
        body = p.get('body')
        try:
            b = json.loads(body) if body else {}
        except Exception:
            b = {}
        eps = b.get('endpoints') or []
        ep0 = eps[0] if eps else {}
        _check('POST 请求体含端点且端点四整数齐全（max_audio_duration/priority 为整数）',
               len(eps) >= 1 and isinstance(ep0.get('max_audio_duration'), int)
               and isinstance(ep0.get('priority'), int) and isinstance(ep0.get('max_process'), int)
               and isinstance(ep0.get('max_timeout'), int),
               detail=f"body={json.dumps(b, ensure_ascii=False)[:400]}")
        _check('POST 请求体无 api_url 字段', 'api_url' not in json.dumps(b, ensure_ascii=False))
        _check('POST 端点 endpoint 值正确', ep0.get('endpoint') == ep_url, detail=str(ep0.get('endpoint')))
    # 列表出现
    _wait_text(drv, api_name, 12)
    _check('开始测试 API 列表出现新弹窗 API', api_name in _body(drv))
    _shot('02_start_api_list_light', drv)

    # ── P1 核心：编辑带端点 API → PUT 成功 ──
    name_spans = drv.find_elements(By.XPATH, f"//*[normalize-space(.)='{api_name}']")
    edit_btn = None
    if name_spans:
        node = name_spans[0]
        for _ in range(6):
            parent = node.find_element(By.XPATH, '..')
            btns = parent.find_elements(By.XPATH, ".//button[@aria-label='更多操作']")
            if btns:
                edit_btn = btns[0]
                break
            node = parent
    _check('找到弹窗 API 卡片「更多操作」入口', edit_btn is not None)
    if edit_btn:
        _js_click(drv, edit_btn)
        time.sleep(0.8)
        mi = [m for m in drv.find_elements(By.XPATH, "//*[@role='menuitem']") if m.is_displayed()]
        edit = [m for m in mi if '编辑' in m.text]
        _check('更多操作菜单含「编辑」', bool(edit))
        if edit:
            _js_click(drv, edit[0])
            _wait_text(drv, '编辑 API', 8)
            time.sleep(1.2)
            dlg2 = _dialog_scope(drv, '编辑 API')
            t2 = dlg2.text
            _check('编辑弹窗无 apiUrl 字段', 'API 端点' not in t2)
            _check('编辑弹窗含「端点列表」+「添加端点」', '端点列表' in t2 and '添加端点' in t2)
            dlg2.find_element(By.XPATH, ".//button[contains(., '添加端点')]").click()
            time.sleep(0.8)
            dlg2_url = dlg2.find_element(By.XPATH, ".//input[@aria-label='端点 URL']")
            _check('编辑态端点行出现', dlg2_url.is_displayed())
            four2 = _four_int_inputs(drv, dlg2)
            _check('编辑态端点行四整数输入齐全（优先级/最大进程/超时/音频时长）',
                   all(k in four2 for k in ['优先级', '最大进程', '超时(s)', '音频时长(s)']),
                   detail=str(list(four2.keys())))
            dlg2_url.send_keys('http://127.0.0.1:5700/v1/test/retest-edit')
            # 真实库读侧 algorithm_type=null → 编辑需重选关联算法（后端缺口，非前端缺陷）
            _select_first_option(drv, dlg2)
            time.sleep(0.5)
            _shot('03_edit_dialog_filled_light', drv)
            drv.get_log('performance')
            dlg2_save = dlg2.find_element(By.XPATH, ".//button[contains(., '保存')]")
            _js_click(drv, dlg2_save)
            time.sleep(2.5)
            caps2 = _get_captured(drv)
            puts = [c for c in caps2 if c['method'] == 'PUT' and c.get('status') is not None]
            puts_all = [c for c in caps2 if c['method'] == 'PUT']
            _check('Network: PUT /api/v1/apis/{id} 返回 <300（编辑带端点不再 400）',
                   any(c.get('status', 0) < 300 for c in puts),
                   detail=json.dumps(puts[-1:] if puts else puts_all[-1:], ensure_ascii=False))
            if puts_all:
                pb = puts_all[-1].get('body')
                try:
                    pbj = json.loads(pb) if pb else {}
                except Exception:
                    pbj = {}
                pe = (pbj.get('endpoints') or [])
                _check('PUT 请求体端点含 max_audio_duration/priority 整数',
                       len(pe) >= 1 and isinstance(pe[0].get('max_audio_duration'), int)
                       and isinstance(pe[0].get('priority'), int),
                       detail=f"body={json.dumps(pbj, ensure_ascii=False)[:400]}")
            time.sleep(1.0)
            _wait_text(drv, api_name, 12)

    # ── 健康检查：端点状态行绑 endpointsStatus ──
    _wait_text(drv, api_name, 12)
    cards = drv.find_elements(By.XPATH, "//button[contains(@aria-label, '连接测试')]")
    target = None
    for c in cards:
        if api_name in (c.get_attribute('aria-label') or ''):
            target = c
            break
    if not target and cards:
        target = cards[-1]
    if target:
        _js_click(drv, target)
        _wait_text(drv, '连接测试结果', 15)
        time.sleep(1.5)
        hd = _dialog_scope(drv, '连接测试结果')
        ht = hd.text
        _check('健康检查弹窗含「端点状态」行（绑 endpointsStatus）', '端点状态' in ht)
        _check('健康检查无 apiUrlStatus 展示', 'apiUrlStatus' not in ht.lower() and 'api_url_status' not in ht.lower())
        _shot('04_health_dialog_light', drv)
        close_btns = [b for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '关闭')]")]
        if close_btns:
            _js_click(drv, close_btns[0])
        else:
            drv.execute_script('document.body.dispatchEvent(new KeyboardEvent("keydown", {key:"Escape"}))')
        time.sleep(0.8)
    else:
        _check('健康检查入口找到', False)

    # ── 设备页抽屉：无 Master URL / apiUrl；端点列表唯一入口 ──
    _goto(drv, '/devices/api')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.0)
    btns = drv.find_elements(By.TAG_NAME, 'button')
    add = [b for b in btns if '添加测试API' in b.text and b.is_displayed()]
    if not add:
        add = [b for b in drv.find_elements(By.TAG_NAME, 'button') if '添加测试API' in b.text and b.is_displayed()]
    _check('设备页「添加测试API」按钮', bool(add))
    if add:
        _js_click(drv, add[0])
        _wait_text(drv, '端点列表', 8)
        time.sleep(1.0)
        drawer = _dialog_scope(drv, '添加测试API')
        dt = drawer.text
        _check('抽屉无 Master URL / apiUrl 残留（无「API 端点」标签）', 'API 端点' not in dt)
        _check('抽屉含「端点列表」+「添加端点」', '端点列表' in dt and '添加端点' in dt)
        drawer.find_element(By.XPATH, ".//button[contains(., '添加端点')]").click()
        time.sleep(0.8)
        durl = drawer.find_element(By.XPATH, ".//input[@aria-label='端点 URL']")
        _check('抽屉端点行出现', durl.is_displayed())
        fourd = _four_int_inputs(drv, drawer)
        _check('抽屉端点行四整数输入齐全（优先级/最大进程/超时/音频时长）',
               all(k in fourd for k in ['优先级', '最大进程', '超时(s)', '音频时长(s)']),
               detail=str(list(fourd.keys())))
        _shot('05_device_drawer_light', drv)
        # 取消关闭
        cbtns = drawer.find_elements(By.XPATH, ".//button[contains(., '取消')]")
        if cbtns:
            _js_click(drv, cbtns[0])
        else:
            drv.execute_script('document.body.dispatchEvent(new KeyboardEvent("keydown", {key:"Escape"}))')
        time.sleep(0.8)
    # 跨组件同步：设备页列表出现弹窗 API
    _wait_text(drv, api_name, 12)
    _check('跨组件同步：设备页 API 列表出现开始测试新建的弹窗 API', api_name in _body(drv))
    _shot('06_devices_list_sync_light', drv)

    # ── 深色截图 ──
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/api')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.0)
    btns = drv.find_elements(By.TAG_NAME, 'button')
    add = [b for b in btns if '添加测试API' in b.text and b.is_displayed()]
    if add:
        _js_click(drv, add[0])
        _wait_text(drv, '端点列表', 8)
        time.sleep(1.0)
        _shot('07_device_drawer_dark', drv)
        cbtns = drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]")
        if cbtns:
            _js_click(drv, cbtns[0])
        time.sleep(0.8)
    _goto(drv, '/start-test?step=1')
    _wait_text(drv, '开始测试', 20)
    time.sleep(1.0)
    btns = drv.find_elements(By.TAG_NAME, 'button')
    add_api = [b for b in btns if b.text.strip() == '新增 API' and b.is_displayed()]
    if add_api:
        _js_click(drv, add_api[0])
        _wait_text(drv, '新增 API', 8)
        time.sleep(1.0)
        dlg = _dialog_scope(drv, '新增 API')
        dlg.find_element(By.XPATH, ".//button[contains(., '添加端点')]").click()
        time.sleep(0.8)
        _shot('08_start_dialog_dark', drv)
        cbtns = drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]")
        if cbtns:
            _js_click(drv, cbtns[0])
        time.sleep(0.8)

    # ── Network 证据 PNG ──
    try:
        from PIL import Image, ImageDraw
        reqs = _network_requests(drv, '/api/v1/apis')
        lines = [f'INT-1362 复测 Network 证据 (performance log, {time.strftime("%H:%M:%S")})', '']
        for r in reqs:
            lines.append(f"{r.get('method')} {r.get('status')} {r.get('url')}")
        img = Image.new('RGB', (900, max(40, len(lines) * 18 + 20)), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)
        y = 12
        for ln in lines:
            draw.text((14, y), ln[:120], fill=(226, 232, 240))
            y += 18
        os.makedirs(ARTIFACTS, exist_ok=True)
        img.save(os.path.join(ARTIFACTS, 'network_evidence.png'))
        print(f'[i] Network 证据写入 network_evidence.png（{len(reqs)} 条 /apis 请求）')
    except Exception as e:
        print(f'[i] Network PNG 生成失败：{e}')

    _db_check('②')
    _cleanup_test_apis(drv)
    time.sleep(0.5)
    _db_check('③')


def main():
    drv = _driver()
    try:
        run_steps(drv)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    if _FAILURES:
        print(f'\n=== 失败 {len(_FAILURES)} 项 ===')
        for f in _FAILURES:
            print(f'  - {f}')
        raise SystemExit(1)
    print('\n=== INT-1362 复测全部通过 ===')


if __name__ == '__main__':
    main()
