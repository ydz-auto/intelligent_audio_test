# -*- coding: utf-8 -*-
"""INT-1550 评估分类删除入口可达性验收（React 接线版，docker 后端 15000）。

针对交付 commit d51d2fcf（分支 agent/react-c/int-1550）合入 wiring/react 头后的 dist：
① 分类下有维度：分组视图「删除分类」禁用 + Tooltip「该分类下还有 N 个维度…」；
② 筛选把维度筛空：组内显示「当前筛选下无匹配维度」、计数 可见/总数、删除仍禁用
   （可删除判定用分类维度总数，不受筛选影响）；
③ 行内删除该分类下唯一维度：空分类分组仍在、占位「该分类下暂无维度」、删除钮可用；
④ 刷新后仍在（证明分组由 GET /evaluation/categories 派生，而非维度派生）；
⑤ 点删除 → ConfirmDialog 文案 → 确认 → DELETE /evaluation/categories/{id} 200 →
   toast「分类删除成功」→ GET 回读分类消失；
⑥ 浅/深截图 + Network 证据；结束前清理本卡自建分类/维度。
"""
import json
import os
import time
import urllib.error
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15250')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, 'artifacts', 'int1550_category_delete')

STAMP = str(int(time.time()))
CAT_NAME = f'INT1550验收分类_{STAMP}'
DIM_NAME = f'INT1550验收维度_{STAMP}'
PREFIX = 'INT1550验收'


# ───────────────────────── API ─────────────────────────

def _api(path, method='GET', body=None):
    url = BASE + '/api/v1' + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')[:300]


def _categories():
    _, data = _api('/evaluation/categories?per_page=200')
    return (data or {}).get('data', {}).get('items', []) or []


def _dimensions():
    _, data = _api('/evaluation/dimensions?per_page=1000')
    return (data or {}).get('data', {}).get('items', []) or []


def _cleanup_stale():
    """清掉历史遗留的本卡前缀数据（维度先删，再删分类）。"""
    removed = []
    for dim in _dimensions():
        if str(dim.get('name', '')).startswith(PREFIX):
            removed.append(('dim', dim['id'], _api(f"/evaluation/dimensions/{dim['id']}", 'DELETE')[0]))
    for cat in _categories():
        if str(cat.get('name', '')).startswith(PREFIX):
            removed.append(('cat', cat['id'], _api(f"/evaluation/categories/{cat['id']}", 'DELETE')[0]))
    return removed


# ───────────────────────── browser ─────────────────────────

def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
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
    drv.set_page_load_timeout(60)
    return drv


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _shot(drv, name, sub='light'):
    d = os.path.join(ARTIFACTS, sub)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, f'{name}.png'))


def _set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);", mode)
    time.sleep(0.6)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _enter_workbench(drv):
    _goto(drv, '/login')
    WebDriverWait(drv, 20).until(lambda d: '进入工作台' in _body_text(d))
    drv.find_element(By.XPATH, "//button[contains(., '进入工作台')]").click()
    WebDriverWait(drv, 30).until(lambda d: 'dashboard' in d.current_url)
    time.sleep(1.0)


def _open_evaluation_group_view(drv):
    _goto(drv, '/Evaluation')
    WebDriverWait(drv, 30).until(lambda d: '评估维度' in _body_text(d))
    tab = drv.find_element(By.XPATH, "//button[normalize-space(.)='分组视图']")
    drv.execute_script('arguments[0].click()', tab)
    WebDriverWait(drv, 20).until(lambda d: d.find_element(
        By.XPATH, "//button[normalize-space(.)='分组视图']").get_attribute('aria-selected') == 'true')
    # 等分类分组渲染出来（分类接口 100 条，需等 GET categories 返回）
    WebDriverWait(drv, 40).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='删除分类 {CAT_NAME}']"))
    time.sleep(0.5)


def _group_card_text(drv):
    return drv.execute_script(
        """
        const btn = document.querySelector('button[aria-label="删除分类 ' + arguments[0] + '"]');
        if (!btn) return null;
        const card = btn.closest('div[class*="bg-card"]');
        return card ? (card.innerText || '') : null;
        """, CAT_NAME)


def _scroll_to_group(drv, name=None):
    """把本卡分类的分组卡滚到视口中间，截图证据更直观。"""
    drv.execute_script(
        """const b=document.querySelector('button[aria-label="删除分类 ' + arguments[0] + '"]');
           const c=b&&b.closest('div[class*="bg-card"]');
           if (c) c.scrollIntoView({block:'center'});""", name or CAT_NAME)
    time.sleep(0.4)


def _delete_btn(drv):
    return drv.find_element(By.XPATH, f"//button[@aria-label='删除分类 {CAT_NAME}']")


def _hover_disabled_delete(drv):
    """禁用钮的 Tooltip 挂在包裹 span 上，hover span 取 tooltip 文案。"""
    span = drv.execute_script(
        """const btn = document.querySelector('button[aria-label="删除分类 ' + arguments[0] + '"]');
           return btn ? btn.parentElement : null;""", CAT_NAME)
    if span is None:
        return ''
    ActionChains(drv).move_to_element(span).perform()
    time.sleep(0.9)
    return _body_text(drv)


def _net_events(drv):
    out = []
    for e in drv.get_log('performance'):
        msg = e.get('message')
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except Exception:
                continue
        if not isinstance(msg, dict):
            continue
        evt = msg.get('message') if isinstance(msg.get('message'), dict) else msg
        if isinstance(evt, dict):
            out.append(evt)
    return out


def _category_network(drv, since=0):
    """返回 (请求列表, requestId→status)。"""
    reqs, status = [], {}
    for evt in _net_events(drv)[since:]:
        m = evt.get('method')
        p = evt.get('params', {}) or {}
        if m == 'Network.responseReceived':
            r = p.get('response', {}) or {}
            if '/evaluation/categories' in (r.get('url') or ''):
                status[p.get('requestId')] = r.get('status')
    for evt in _net_events(drv):
        m = evt.get('method')
        p = evt.get('params', {}) or {}
        if m == 'Network.requestWillBeSent':
            r = p.get('request', {}) or {}
            if '/evaluation/categories' in (r.get('url') or ''):
                reqs.append({
                    'requestId': p.get('requestId'),
                    'method': r.get('method'),
                    'url': r.get('url'),
                    'status': status.get(p.get('requestId')),
                })
    return reqs, status


def _confirm_dialog_click(drv, text='删除'):
    WebDriverWait(drv, 15).until(
        lambda d: d.find_elements(By.XPATH, "//div[@role='alertdialog']"))
    time.sleep(0.7)  # 等开合动画就绪，避免点击被吞
    btn = drv.find_element(
        By.XPATH, f"//div[@role='alertdialog']//button[normalize-space(.)='{text}']")
    drv.execute_script('arguments[0].click()', btn)


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    r = {'base': BASE, 'category': CAT_NAME, 'dimension': DIM_NAME}
    r['pre_clean'] = _cleanup_stale()

    # ── 0. 造数：自建分类 + 该分类下唯一维度 ──
    code, data = _api('/evaluation/categories', 'POST', {
        'name': CAT_NAME,
        'description': 'INT-1550 验收临时分类（验收后删除）',
        'icon': 'fas fa-folder',
    })
    r['create_category'] = {'status': code, 'body': data}
    if code not in (200, 201):
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 1
    cat_id = data['data']['id']
    r['cat_id'] = cat_id

    code, data = _api('/evaluation/dimensions', 'POST', {
        'name': DIM_NAME,
        'description': 'INT-1550 验收临时维度（验收后删除）',
        'dimension_type': 'main',
        'category_id': cat_id,
        'weight': 5,
    })
    r['create_dimension'] = {'status': code, 'body': data}
    if code not in (200, 201):
        _api(f'/evaluation/categories/{cat_id}', 'DELETE')
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 1
    dim_id = data['data']['id']
    r['dim_id'] = dim_id

    drv = _driver()
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        _enter_workbench(drv)
        _open_evaluation_group_view(drv)

        # ── ① 有维度：删除分类禁用 + Tooltip ──
        btn = _delete_btn(drv)
        r['with_dim_delete_disabled'] = btn.get_attribute('disabled') is not None
        r['with_dim_card_text'] = _group_card_text(drv)
        r['with_dim_has_dim_row'] = DIM_NAME in (_body_text(drv) or '')
        _scroll_to_group(drv)
        _shot(drv, '01_with_dim_delete_disabled')
        body = _hover_disabled_delete(drv)
        r['with_dim_tooltip'] = f'该分类下还有 1 个维度' in body
        r['with_dim_tooltip_text'] = [
            line for line in body.split('\n') if '请先迁移或删除维度' in line][:1]
        _shot(drv, '02_tooltip_disabled')

        # ── ② 筛选把维度筛空：仍禁用、计数 可见/总数 ──
        search = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
        drv.execute_script('arguments[0].click()', search)
        search.send_keys('zzz_no_such_dim_int1550')
        time.sleep(1.5)
        card = _group_card_text(drv) or ''
        r['filtered_card_text'] = card
        r['filtered_badge_0_of_1'] = '0/1' in card
        r['filtered_placeholder'] = '当前筛选下无匹配维度' in card
        r['filtered_delete_still_disabled'] = _delete_btn(drv).get_attribute('disabled') is not None
        _shot(drv, '03_filter_hides_dim')

        # 清空筛选（受控输入：Ctrl+A + Delete 才触发 onChange）
        search.send_keys(Keys.CONTROL, 'a')
        search.send_keys(Keys.DELETE)
        WebDriverWait(drv, 25).until(
            lambda d: DIM_NAME in (d.execute_script(
                """const b=document.querySelector('button[aria-label="删除分类 ' + arguments[0] + '"]');
                   const c=b&&b.closest('div[class*="bg-card"]'); return c?c.innerText:'';""",
                CAT_NAME) or ''))
        time.sleep(0.5)

        # ── ③ 行内删除该分类下唯一维度 ──
        row_del = drv.find_element(By.XPATH, f"//button[@aria-label='删除维度 {DIM_NAME}']")
        drv.execute_script('arguments[0].click()', row_del)
        _confirm_dialog_click(drv, '删除')
        WebDriverWait(drv, 25).until(lambda d: '维度已删除' in _body_text(d))
        time.sleep(1.5)
        r['dim_delete_toast'] = '维度已删除' in _body_text(drv)
        r['dim_gone_backend'] = not any(
            d_.get('id') == dim_id for d_ in _dimensions())

        # 空分类分组仍在 + 删除钮可用（不刷新）
        WebDriverWait(drv, 20).until(
            lambda d: '该分类下暂无维度' in (d.execute_script(
                """const b=document.querySelector('button[aria-label="删除分类 ' + arguments[0] + '"]');
                   const c=b&&b.closest('div[class*="bg-card"]'); return c?c.innerText:'';""",
                CAT_NAME) or ''))
        card = _group_card_text(drv) or ''
        r['empty_card_text'] = card
        r['empty_placeholder'] = '该分类下暂无维度' in card
        r['empty_delete_enabled'] = _delete_btn(drv).get_attribute('disabled') is None
        _scroll_to_group(drv)
        _shot(drv, '04_empty_category_after_dim_delete')

        # ── ④ 刷新后仍在（分组由 categories 派生）──
        # 刷新后 viewMode 回默认列表视图，需重新切分组视图
        drv.refresh()
        WebDriverWait(drv, 60).until(lambda d: '评估维度' in _body_text(d))
        tab = drv.find_element(By.XPATH, "//button[normalize-space(.)='分组视图']")
        drv.execute_script('arguments[0].click()', tab)
        WebDriverWait(drv, 40).until(
            lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='删除分类 {CAT_NAME}']"))
        time.sleep(1.0)
        card = _group_card_text(drv) or ''
        r['after_reload_card_text'] = card
        r['after_reload_group_present'] = CAT_NAME in card
        r['after_reload_delete_enabled'] = _delete_btn(drv).get_attribute('disabled') is None
        _scroll_to_group(drv)
        _shot(drv, '05_after_reload')

        # ── ⑤ 删除分类：确认弹窗 → DELETE 200 → 回读消失 ──
        # Chrome 155 起 Network.setRequestInterception 不可用，性能日志在本轮抓不到
        # 本次 XHR；用页内 fetch 打点记录真实请求/状态码（INT-932 同款做法）。
        drv.execute_script(
            """
            if (!window.__netInstalled) {
              window.__netInstalled = true;
              window.__net = [];
              const of = window.fetch;
              window.fetch = function (input, init) {
                const url = typeof input === 'string' ? input : (input && input.url) || '';
                const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
                const rec = { url: url, method: method, status: null };
                window.__net.push(rec);
                return of.apply(this, arguments).then(function (r) {
                  rec.status = r.status; return r;
                });
              };
            }
            """)
        net_before = len(_net_events(drv))
        drv.execute_script('arguments[0].click()', _delete_btn(drv))
        WebDriverWait(drv, 15).until(lambda d: '删除分类' in _body_text(d)
                                     and d.find_elements(By.XPATH, "//div[@role='alertdialog']"))
        time.sleep(0.5)
        dlg_text = drv.find_element(By.XPATH, "//div[@role='alertdialog']").text
        r['confirm_dialog_text'] = dlg_text
        r['confirm_dialog_ok'] = (f'确定删除分类「{CAT_NAME}」吗？此操作不可恢复。' in dlg_text)
        _scroll_to_group(drv)
        _shot(drv, '06_delete_category_confirm')

        before_req = len(_category_network(drv)[0])
        _confirm_dialog_click(drv, '删除')
        WebDriverWait(drv, 25).until(lambda d: '分类删除成功' in _body_text(d))
        time.sleep(1.5)
        r['cat_delete_toast'] = '分类删除成功' in _body_text(drv)

        # get_log('performance') 读取即清空缓冲：本次只含确认点击后的新事件
        # 页内打点 + 性能日志双证据
        inpage = drv.execute_script('return window.__net || []')
        reqs, _ = _category_network(drv)
        r['inpage_requests'] = inpage
        r['perflog_requests'] = reqs
        writes = [q for q in inpage
                  if q.get('method') == 'DELETE' and '/evaluation/categories' in (q.get('url') or '')]
        r['delete_requests'] = writes
        r['delete_ok'] = any(
            f'/evaluation/categories/{cat_id}' in (q['url'] or '')
            and q['status'] in (200, 204) for q in writes)
        r['cat_gone_backend'] = not any(c.get('id') == cat_id for c in _categories())

        # 页面回读：分组消失
        WebDriverWait(drv, 20).until(
            lambda d: not d.find_elements(By.XPATH, f"//button[@aria-label='删除分类 {CAT_NAME}']"))
        r['group_gone_after_delete'] = CAT_NAME not in (drv.execute_script(
            """const els=[...document.querySelectorAll('div[class*="bg-card"]')];
               return els.map(e=>e.innerText).join('\\n');""") or '')
        _shot(drv, '07_after_category_deleted')

        # ── ⑥ 深色截图 ──
        # 再造一个空分类验证深色下空分类分组渲染（随后删除）
        code, data = _api('/evaluation/categories', 'POST', {
            'name': f'{CAT_NAME}_dark', 'description': 'INT-1550 深色空分类',
            'icon': 'fas fa-folder'})
        dark_cat = data['data']['id'] if code in (200, 201) else None
        r['dark_cat_id'] = dark_cat
        if dark_cat:
            drv.refresh()
            WebDriverWait(drv, 60).until(lambda d: '评估维度' in _body_text(d))
            tab = drv.find_element(By.XPATH, "//button[normalize-space(.)='分组视图']")
            drv.execute_script('arguments[0].click()', tab)
            WebDriverWait(drv, 40).until(
                lambda d: d.find_elements(
                    By.XPATH, f"//button[@aria-label='删除分类 {CAT_NAME}_dark']"))
            _set_theme(drv, 'dark')
            time.sleep(1.0)
            _scroll_to_group(drv, CAT_NAME + '_dark')
            _shot(drv, '08_empty_category_dark', 'dark')
            r['dark_empty_category_rendered'] = CAT_NAME + '_dark' in _body_text(drv)
            r['dark_cleanup'] = _api(f'/evaluation/categories/{dark_cat}', 'DELETE')[0]
        _set_theme(drv, 'light')
    except Exception as exc:  # 失败也要落盘现场并清理自建数据
        r['error'] = f'{type(exc).__name__}: {exc}'
        r['page_text_tail'] = (drv.execute_script('return document.body.textContent||""')
                               or '')[-800:]
        try:
            _shot(drv, '99_failure_state')
        except Exception:
            pass
        r['error_clean'] = _cleanup_stale()
        print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
        raise
    finally:
        drv.quit()

    # ── 清理 ──
    r['final_clean'] = _cleanup_stale()
    r['leftover_categories'] = [c['name'] for c in _categories()
                                if str(c.get('name', '')).startswith(PREFIX)]
    r['leftover_dimensions'] = [d['name'] for d in _dimensions()
                                if str(d.get('name', '')).startswith(PREFIX)]

    print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)

    checks = [
        ('with_dim_delete_disabled', True),
        ('with_dim_has_dim_row', True),
        ('with_dim_tooltip', True),
        ('filtered_badge_0_of_1', True),
        ('filtered_placeholder', True),
        ('filtered_delete_still_disabled', True),
        ('dim_delete_toast', True),
        ('dim_gone_backend', True),
        ('empty_placeholder', True),
        ('empty_delete_enabled', True),
        ('after_reload_group_present', True),
        ('after_reload_delete_enabled', True),
        ('confirm_dialog_ok', True),
        ('cat_delete_toast', True),
        ('delete_ok', True),
        ('cat_gone_backend', True),
        ('group_gone_after_delete', True),
        ('dark_empty_category_rendered', True),
    ]
    failed = [name for name, want in checks if r.get(name) != want]
    r['failed_checks'] = failed
    print('RESULT:', 'PASS' if not failed else 'FAIL ' + ','.join(failed), flush=True)
    return 0 if not failed else 1


if __name__ == '__main__':
    raise SystemExit(main())
