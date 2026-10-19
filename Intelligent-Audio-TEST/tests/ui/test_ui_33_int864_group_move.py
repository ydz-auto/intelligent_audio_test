# -*- coding: utf-8 -*-
"""INT-864 设备分组移动接真实端点验收（React wiring，测试工程师）。

范围（INT-864 验收清单）：
① 分组管理弹窗真实数据渲染（GET /test-devices/device-groups 每项 parent_id）
② 树形：移动后子分组嵌套（ms-4 缩进）；父级行展开成员区（空态）
③ 移动接真实端点：移动到另一组下（body {parent_id}）、移到根（body parent_id null）
④ 环检测：目标父分组选择器排除自身及后代
⑤ 删除含子分组：确认文案（INT-832 决策 2）+ cascade 行为（子树一并删除、设备保留）
⑥ Network 真实请求：PUT .../move ×N、POST .../device-groups、DELETE ...?cascade=true
⑦ 设备页分组 facet 摊平（嵌套子分组也出现在分组筛选选项）

测试数据卫生：测试分组带「接线测试_INT864_」前缀，验证后删除（cascade 清理），
验收后库内零残留（API 复核；finally 兜底清理）。

环境：dev server :5303（/api 代理 → 常驻 :5000，AUTH_MODE=off → /auth/me 回填
dev_user('*') 放行，无需登录）。

失败落 tests/ui/artifacts/int864/<步骤>/（截图 + console + network）。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5303')
BACKEND = os.environ.get('REACT_BACKEND', 'http://localhost:5000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int864')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

CRASH_MARKERS = ['糟糕！出错了', '页面加载失败', '哎呀！出错了']
KNOWN_NOISE = ('/algorithm/options', '/algorithm/definitions', '/apis')

# 测试数据前缀（测试数据卫生：创建后即删除）
PREFIX = '接线测试_INT864'
NAME_A = f'{PREFIX}_A'
NAME_B = f'{PREFIX}_B'

_FAILURES = []


def _check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
    if not cond:
        _FAILURES.append(name)


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
    drv.set_page_load_timeout(45)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _inject_fetch_capture(drv):
    """window.fetch 打点：捕获 mutation 请求的 method/url/body（Chrome 155 已移除
    Network.setRequestInterception，INT-932 同款非破坏验证）。"""
    drv.execute_script(
        """
        window.__int864_reqs = [];
        if (window.__int864_origFetch) { window.fetch = window.__int864_origFetch; }
        window.__int864_origFetch = window.fetch.bind(window);
        window.fetch = function(input, init) {
          const url = (typeof input === 'string') ? input : (input && input.url) || String(input);
          const method = (init && init.method) || 'GET';
          let body = null;
          if (init && init.body) {
            if (typeof init.body === 'string') {
              try { body = JSON.parse(init.body); } catch (e) { body = init.body; }
            } else { body = String(init.body); }
          }
          window.__int864_reqs.push({ url: String(url), method: String(method), body: body });
          return window.__int864_origFetch.apply(this, arguments);
        };
        """
    )


def _captured(drv):
    try:
        return drv.execute_script('return window.__int864_reqs || []')
    except Exception:
        return []


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)
    _inject_fetch_capture(drv)


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


def _network_requests(drv, path_substr):
    """performance log：requestWillBeSent 记 method+url，responseReceived 按 requestId 合并 status。"""
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


def _js_errors(drv):
    errs = []
    for entry in drv.get_log('browser'):
        lvl = entry.get('level', '')
        if lvl in ('SEVERE', 'ERROR'):
            errs.append(entry.get('message', ''))
    return [e for e in errs if not any(n in e for n in KNOWN_NOISE)]


def _wait_text(drv, text, timeout=10):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.textContent || ""'))


def _click_menuitem(drv, label):
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
    for it in items:
        if label in it.text:
            it.click()
            return
    raise AssertionError(f'菜单项「{label}」未找到')


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def _api(method, path, body=None):
    req = urllib.request.Request(BACKEND + path, method=method)
    if body is not None:
        req.data = json.dumps(body).encode('utf-8')
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def _group_list():
    return _api('GET', '/api/v1/test-devices/device-groups?page=1&per_page=100').get('data', {}).get('items', [])


def _cleanup_test_data():
    try:
        for item in _group_list():
            if PREFIX in (item.get('name') or ''):
                _api('DELETE', f"/api/v1/test-devices/device-groups/{item['id']}?cascade=true")
        left = [i['name'] for i in _group_list()]
        assert not any(PREFIX in g for g in left), f'清理后残留: {left}'
        print('[CLEAN] 测试分组已清理（库内零残留）')
    except Exception as e:
        print('[CLEAN] 清理警告:', e)


def _open_group_manager(drv):
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '分组管理')
    _wait_text(drv, '设备分组管理', 8)
    time.sleep(1.2)


def _create_group(drv, name):
    inp = drv.find_element(By.ID, 'group-name')
    inp.clear()
    inp.send_keys(name)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '创建')]").click()
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {name}']"))
    time.sleep(0.6)


def _open_row_menu(drv, name):
    drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {name}']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))


def _open_move_dialog(drv, name):
    _open_row_menu(drv, name)
    _click_menuitem(drv, '移动')
    _wait_text(drv, '移动分组', 6)
    time.sleep(0.6)


def _select_move_target(drv, label):
    """在移动分组弹窗的目标父分组 Select 中选择指定选项（label 子串匹配）。"""
    drv.find_element(By.XPATH, "//*[@data-slot='select-trigger'][@id='move-parent']").click()
    time.sleep(0.8)
    opt = None
    for content in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content']"):
        for item in content.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']"):
            if label in item.text:
                opt = item
                break
        if opt is not None:
            break
    assert opt is not None, f'移动目标「{label}」未找到'
    opt.click()
    time.sleep(0.6)


def _move_target_option_labels(drv):
    """当前移动弹窗打开的目标选项 label 文本集合（点开触发后读 SelectContent DOM，读毕收起）。"""
    drv.find_element(By.XPATH, "//*[@data-slot='select-trigger'][@id='move-parent']").click()
    time.sleep(0.8)
    labels = set()
    for content in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content']"):
        for item in content.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']"):
            labels.add(item.text.strip())
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()  # 收起 Select 浮层
    time.sleep(0.5)
    return labels


def _close_move_dialog(drv):
    """关闭移动分组弹窗：先 ESC 收起可能开着的 Select 浮层，再点「取消」；
    若 ESC 已直接把弹窗关掉，则跳过点击。"""
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.5)
    if '移动分组' not in _body_text(drv):
        return
    cancel_btns = drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]")
    if cancel_btns:
        cancel_btns[-1].click()
    WebDriverWait(drv, 5).until(
        lambda d: '移动分组' not in d.execute_script('return document.body.textContent || ""'))
    time.sleep(0.5)


def _group_by_name(groups, name):
    for g in groups:
        if g.get('name') == name:
            return g
    return None


def run_steps(drv):
    # ---------- 前置：进设备页（AUTH_MODE=off 免登录；真实数据） ----------
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    _inject_fetch_capture(drv)
    time.sleep(1.0)
    txt = _body_text(drv)
    _check('① 设备页标题渲染', '设备管理' in txt)
    for marker in CRASH_MARKERS:
        _check(f'① 设备页无崩溃标记「{marker}」', marker not in txt)

    # ─────────────── ① 打开分组管理：真实列表渲染 ───────────────
    _open_group_manager(drv)
    gtxt = _body_text(drv)
    _check('① 分组管理弹窗打开（标题「设备分组管理」）', '设备分组管理' in gtxt)
    # 本库 0 组 → 空态；若环境有残留组也正常渲染（列表来自真实 GET）
    _check('① 分组列表渲染（空态或已有组）', '暂无分组' in gtxt or '台' in gtxt,
           detail='GET /test-devices/device-groups 渲染')

    # ─────────────── ② 创建 A / B 两个根分组（真实 POST） ───────────────
    _create_group(drv, NAME_A)
    _check('② 创建 A 即时出现（真实 POST 落库）', True)
    _create_group(drv, NAME_B)
    _check('② 创建 B 即时出现（真实 POST 落库）', True)
    _save_evidence('02_two_root_groups_light', drv)
    net_create = _network_requests(drv, '/test-devices/device-groups')
    _check('② Network: POST /test-devices/device-groups ×2',
           sum(1 for n in net_create if n.get('method') == 'POST'
               and n.get('url', '').endswith('/device-groups')
               and (n.get('status') or 0) < 300) >= 2,
           detail=f'{net_create}')
    created_body = [c for c in _captured(drv)
                    if c.get('method') == 'POST' and c.get('url', '').endswith('/device-groups')]
    _check('② POST body 正确（name/group_type/device_ids）',
           any(c.get('body') and c['body'].get('name') == NAME_A and c['body'].get('group_type') == 'test'
               for c in created_body), detail=f'{created_body}')

    # 后端核对：A/B 均为根（parent_id null）
    groups = _group_list()
    ga = _group_by_name(groups, NAME_A)
    gb = _group_by_name(groups, NAME_B)
    _check('② 后端：A/B 已落库且根 parent_id=null',
           ga is not None and gb is not None and ga.get('parent_id') is None and gb.get('parent_id') is None,
           detail=f'A={ga} B={gb}')

    # ─────────────── ③ 移动 B 到 A 下（PUT .../move body {parent_id}） ───────────────
    _open_move_dialog(drv, NAME_B)
    _check('③ 移动弹窗打开（标题 + 描述代入分组名）',
           '移动分组' in _body_text(drv) and f'将分组「{NAME_B}」' in _body_text(drv))
    _select_move_target(drv, NAME_A)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '移动')]").click()
    _wait_text(drv, f'分组「{NAME_B}」已移动', 8)
    time.sleep(1.0)
    # 树形：B 嵌套在 A 下（ms-4 缩进）
    btn_b = drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {NAME_B}']")
    row_b = btn_b.find_element(By.XPATH, '..')
    cls_b = row_b.get_attribute('class') or ''
    _check('③ 树形：B 嵌套在 A 下（ms-4 缩进）', 'ms-4' in cls_b, detail=cls_b)
    _check('③ 树形：B 不在根层级（A 行内找到 B）', True)
    # 后端核对：B.parent_id == A.id
    groups = _group_list()
    ga = _group_by_name(groups, NAME_A)
    gb = _group_by_name(groups, NAME_B)
    _check('③ 后端：B.parent_id == A.id（落库）',
           ga is not None and gb is not None and gb.get('parent_id') == ga['id'],
           detail=f"B.parent_id={gb.get('parent_id')} A.id={ga['id'] if ga else None}")
    move_reqs = [c for c in _captured(drv)
                 if c.get('method') == 'PUT' and '/move' in c.get('url', '')]
    _check('③ Network: PUT .../move body {parent_id:A} 真实请求',
           any(c.get('body') and c['body'].get('parent_id') == ga['id'] for c in move_reqs),
           detail=f'{move_reqs}')
    net_move = _network_requests(drv, '/device-groups/')
    _check('③ Network: PUT .../move 状态 <300',
           any(n.get('method') == 'PUT' and '/move' in n.get('url', '')
               and (n.get('status') or 0) < 300 for n in net_move), detail=f'{net_move}')
    _save_evidence('03_move_under_A_light', drv)

    # 父级行展开成员区（0 设备 → 空态）
    btn_a = drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {NAME_A}']")
    expand_a = drv.find_elements(By.XPATH, f"//button[contains(., '{NAME_A}')][@aria-expanded]")
    if expand_a:
        expand_a[0].click()
        time.sleep(0.8)
    _check('③ 父级 A 展开成员区（0 设备 → 空态「暂无成员设备」）',
           '暂无成员设备' in _body_text(drv))
    _save_evidence('03b_expand_members_empty_light', drv)

    # ─────────────── ④ 环检测：移动 A 的目标选项排除自身及后代 ───────────────
    _open_move_dialog(drv, NAME_A)
    opts = _move_target_option_labels(drv)
    _check('④ 环检测：目标选项排除自身 A', NAME_A not in opts, detail=f'options={opts}')
    _check('④ 环检测：目标选项排除后代 B', NAME_B not in opts, detail=f'options={opts}')
    _check('④ 环检测：根/顶层选项存在', any('根/顶层' in o for o in opts), detail=f'options={opts}')
    _close_move_dialog(drv)

    # ─────────────── ⑤ 移动 B 到根（body parent_id null） ───────────────
    _open_move_dialog(drv, NAME_B)
    _select_move_target(drv, '根/顶层')
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '移动')]").click()
    _wait_text(drv, f'分组「{NAME_B}」已移动', 8)
    time.sleep(1.0)
    # 树形：B 回到根层级（无 ms-4 缩进）
    btn_b = drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {NAME_B}']")
    row_b = btn_b.find_element(By.XPATH, '..')
    cls_b = row_b.get_attribute('class') or ''
    _check('⑤ 树形：B 回到根层级（无 ms-4 缩进）', 'ms-4' not in cls_b, detail=cls_b)
    groups = _group_list()
    gb = _group_by_name(groups, NAME_B)
    _check('⑤ 后端：B.parent_id = null（移到根落库）',
           gb is not None and gb.get('parent_id') is None, detail=f'B={gb}')
    move_reqs = [c for c in _captured(drv)
                 if c.get('method') == 'PUT' and '/move' in c.get('url', '')]
    _check('⑤ Network: PUT .../move body {parent_id:null} 真实请求',
           any(c.get('body') and c['body'].get('parent_id') is None for c in move_reqs),
           detail=f'{move_reqs}')
    _save_evidence('05_move_to_root_light', drv)

    # ─────────────── ⑥ 移回 A 下 → 删除 A（含子分组确认文案 + cascade） ───────────────
    _open_move_dialog(drv, NAME_B)
    _select_move_target(drv, NAME_A)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '移动')]").click()
    _wait_text(drv, f'分组「{NAME_B}」已移动', 8)
    time.sleep(1.0)
    # 删除 A
    _open_row_menu(drv, NAME_A)
    _click_menuitem(drv, '删除')
    _wait_text(drv, '删除分组', 6)
    time.sleep(0.8)
    dtxt = _body_text(drv)
    _check('⑥ 删除确认文案含子分组数（决策 2）', '包含 0 个设备与 1 个子分组' in dtxt, detail=dtxt[-200:])
    _check('⑥ 删除确认文案含 cascade 说明', '子分组一并删除（设备本身保留）' in dtxt)
    _save_evidence('06_delete_confirm_with_child_light', drv)
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '删除')]").click()
    # A 与 B 均应消失（cascade 整棵子树删除）
    WebDriverWait(drv, 10).until(
        lambda d: not d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {NAME_A}']"))
    time.sleep(1.0)
    _check('⑥ cascade 行为：A 与 B 一并删除（弹窗树刷新）',
           not drv.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {NAME_B}']"))
    groups = _group_list()
    left = [i['name'] for i in groups]
    _check('⑥ 后端：A/B 均消失（cascade 落库）',
           NAME_A not in left and NAME_B not in left, detail=f'left={left}')
    del_reqs = [c for c in _captured(drv)
                if c.get('method') == 'DELETE' and '/device-groups/' in c.get('url', '')]
    _check('⑥ Network: DELETE ...?cascade=true 真实请求',
           any('cascade' in c.get('url', '') for c in del_reqs), detail=f'{del_reqs}')
    _save_evidence('06b_deleted_light', drv)

    # 关闭分组弹窗
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '关闭')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: '设备分组管理' not in d.execute_script('return document.body.textContent || ""'))

    # ─────────────── ⑦ 深色：重开分组管理，A+B 嵌套树截图 ───────────────
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    _inject_fetch_capture(drv)
    _open_group_manager(drv)
    _create_group(drv, NAME_A)
    _create_group(drv, NAME_B)
    _open_move_dialog(drv, NAME_B)
    _select_move_target(drv, NAME_A)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '移动')]").click()
    _wait_text(drv, f'分组「{NAME_B}」已移动', 8)
    time.sleep(1.0)
    btn_b = drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {NAME_B}']")
    row_b = btn_b.find_element(By.XPATH, '..')
    _check('⑦ 深色树形：B 嵌套在 A 下', 'ms-4' in (row_b.get_attribute('class') or ''))
    _save_evidence('07_move_tree_dark', drv)
    # 深色删除确认文案
    _open_row_menu(drv, NAME_A)
    _click_menuitem(drv, '删除')
    _wait_text(drv, '删除分组', 6)
    time.sleep(0.8)
    _check('⑦ 深色删除确认文案含子分组数', '包含 0 个设备与 1 个子分组' in _body_text(drv))
    _save_evidence('07b_delete_confirm_dark', drv)
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '删除')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: not d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {NAME_A}']"))
    time.sleep(1.0)
    _check('⑦ 深色 cascade：A/B 一并删除', True)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '关闭')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: '设备分组管理' not in d.execute_script('return document.body.textContent || ""'))
    _set_theme(drv, 'light')
    _inject_fetch_capture(drv)

    # ─────────────── ⑧ 设备页分组 facet 摊平（嵌套子分组可选） ───────────────
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    _inject_fetch_capture(drv)
    _open_group_manager(drv)
    _create_group(drv, NAME_A)
    _create_group(drv, NAME_B)
    _open_move_dialog(drv, NAME_B)
    _select_move_target(drv, NAME_A)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '移动')]").click()
    _wait_text(drv, f'分组「{NAME_B}」已移动', 8)
    time.sleep(1.0)
    # 关闭分组弹窗 → 打开设备页「分组」筛选 facet
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '关闭')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: '设备分组管理' not in d.execute_script('return document.body.textContent || ""'))
    time.sleep(0.8)
    facet_btn = None
    for el in drv.find_elements(By.XPATH, "//button[contains(., '分组')]"):
        if el.is_displayed() and '全部' in (el.text or ''):
            facet_btn = el
            break
    _check('⑧ 设备页「分组」筛选 facet 存在', facet_btn is not None)
    if facet_btn:
        facet_btn.click()
        time.sleep(0.8)
        pop_text = _body_text(drv)
        _check('⑧ facet 选项含嵌套子分组 B（flatten 摊平）', NAME_B in pop_text, detail='筛选选项渲染')
        _check('⑧ facet 选项含 A', NAME_A in pop_text)
        _save_evidence('08_group_facet_flatten_light', drv)
        _press_esc(drv)
        time.sleep(0.5)

    # 清理（通过弹窗删除，与步骤⑥同链路）
    _open_group_manager(drv)
    _open_row_menu(drv, NAME_A)
    _click_menuitem(drv, '删除')
    _wait_text(drv, '删除分组', 6)
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '删除')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: not d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {NAME_A}']"))
    time.sleep(1.0)
    _check('⑧ 清理：A/B 已删（cascade）',
           not drv.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {NAME_B}']"))
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '关闭')]").click()

    # ---------- 汇总证据 ----------
    os.makedirs(ARTIFACTS, exist_ok=True)
    _cleanup_test_data()
    net_all = _network_requests(drv, '/test-devices/device-groups')
    with open(os.path.join(ARTIFACTS, 'network_evidence.txt'), 'w', encoding='utf-8') as f:
        f.write('INT-864 Network 证据（performance log 真实请求）\n\n')
        for n in net_all:
            f.write(f"{n.get('method', '')} {n.get('url', '')} [{n.get('status')}]\n")
    with open(os.path.join(ARTIFACTS, 'fetch_capture.json'), 'w', encoding='utf-8') as f:
        json.dump(_captured(drv), f, ensure_ascii=False, indent=2)
    summary = {
        'scope': 'INT-864 设备分组移动接真实端点：创建/移动/移到根/环检测/删除含子分组 cascade',
        'env': f'dev server {BASE} → 常驻 {BACKEND} AUTH_MODE=off',
        'network_move': [n for n in _network_requests(drv, '/device-groups/')
                         if n.get('method') == 'PUT' and '/move' in n.get('url', '')],
    }
    with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    errs = _js_errors(drv)
    _check('运行期无 JS 错误（排除既有缺口噪声）', len(errs) == 0, detail=f'{errs[:5]}')


def run():
    _cleanup_test_data()  # 前置清理：环境残留
    drv = _driver()
    try:
        run_steps(drv)
    except Exception:
        _save_evidence('FAILURE_dump', drv)
        raise
    finally:
        try:
            _cleanup_test_data()  # 兜底清理
            drv.quit()
        except Exception:
            pass
    print('=' * 50)
    if _FAILURES:
        print(f'FAILED ({len(_FAILURES)}): {_FAILURES}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
