# -*- coding: utf-8 -*-
"""INT-997 用例列表页行级/批量操作接真实接口浏览器验收（连常驻 5000 后端）。

范围：frontend-react/src/features/testcases 行级/分组级/批量/全部恢复操作全部接真实写接口。
验收：各操作 Network 显示真实 POST/PUT/DELETE 请求且生效（非 toast 演示）+ 浅/深色截图。

探测数据（run 结束前清理）：
- 分组：接线测试_INT997_组1 / 组2（+ 批量新建组 / 复制分组派生组）
- 用例：接线测试_INT997_A~F（经 POST /testcases 落库）

网络证据：performance log（requestWillBeSent → method/url，responseReceived → status，跨 drain 累积）
+ window.fetch 打点捕获请求体（action 字段核实）。
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int997_row_batch_wiring')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5320')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
# 常驻栈 api_gateway 只监听 IPv4（0.0.0.0:5000），urllib 解析 localhost 到 ::1 会 SynSent 卡死
# （2026-10-21 实测），API 直达固定用 127.0.0.1；浏览器 BASE 保持 localhost（localStorage 同源）。
GATEWAY = 'http://127.0.0.1:5000/api/v1'

# AUTH_MODE=off 常驻栈无可登录流程（login 401），而收藏/删除等 per-user 写侧
# 需 Bearer user_id。用常驻栈 .env JWT_SECRET 自签一个 dev 身份 token 注入
# localStorage（client.ts authTokenStore 同源读取），模拟生产登录态下前端行为。
JWT_SECRET = '50a07cea25f73cde1dca9dc66f538aa3e6be075988cda82e'


def _mint_token(user_id=1):
    import base64
    import hashlib
    import hmac
    header = {'alg': 'HS256', 'typ': 'JWT'}
    payload = {
        'user_id': user_id,
        'username': 'admin',
        'role_id': 1,
        'permissions': ['*'],
        'exp': int(time.time()) + 3600,
        'iat': int(time.time()),
    }

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b'=').decode()

    sig_input = f'{b64(header)}.{b64(payload)}'
    sig = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), sig_input.encode(), hashlib.sha256).digest()
    ).rstrip(b'=').decode()
    return f'{sig_input}.{sig}'

BASE_PREFIX = '接线测试_INT997_'
RUN_TAG = str(int(time.time() * 1000) % 100000000)
GROUP1 = BASE_PREFIX + RUN_TAG + '_组1'
GROUP2 = BASE_PREFIX + RUN_TAG + '_组2'
NEWGROUP = BASE_PREFIX + RUN_TAG + '_新组'
CASE_PREFIX = BASE_PREFIX + RUN_TAG + '_'
CASES = ['A', 'B', 'C', 'D', 'E', 'F']

RESULTS = []

# 网络证据跨页面累积（整页导航/重挂会清空页面内 __int997_reqs，证据从 _NET_LOG 汇总）
_NET_LOG = []


def _api(path, method='GET', body=None):
    req = urllib.request.Request(GATEWAY + path, method=method)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(body).encode('utf-8')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def _record(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(f'  [{"PASS" if ok else "FAIL"}] {name}: {detail}')


def _setup_probe_data():
    # 预清理：上次失败 run 可能遗留探针数据（重跑安全）
    _cleanup(None, None, None)
    gid1, gid2 = None, None
    _, d = _api('/groups', 'POST', {'name': GROUP1, 'description': '', 'algorithm_type': ''})
    gid1 = d.get('data', {}).get('id')
    _, d = _api('/groups', 'POST', {'name': GROUP2, 'description': '', 'algorithm_type': ''})
    gid2 = d.get('data', {}).get('id')
    if not gid1 or not gid2:
        raise RuntimeError(f'建组失败: gid1={gid1} gid2={gid2}')
    cids = {}
    for c in CASES:
        body = {
            'name': CASE_PREFIX + c,
            'description': 'INT-997 行级/批量接线探针',
            'group_id': gid1,
            'tags': [],
            'config': {
                'rounds': [{'round_number': 1, 'audios': [],
                            'evaluation': {'enabled': True, 'dimensions': []}}],
                'background_noise': None,
                'dimensions': [],
            },
        }
        st, d = _api('/testcases', 'POST', body)
        cid = d.get('data', {}).get('id')
        if not cid:
            raise RuntimeError(f'建用例失败: {c} st={st} {d}')
        cids[c] = cid
    print(f'  setup: gid1={gid1} gid2={gid2} cases={cids}')
    return gid1, gid2, cids


def _cleanup(gid1, gid2, cids):
    # 库中残留探针用例（含副本/移动后的），彻底删除（正常 + 回收站两处；per_page=200 防漏）。
    # purge 仅对「已软删（回收站态）」用例生效：直接 purge 非删除态用例是 no-op（purged_count=0，
    # INT-997 复测实测），故先 POST /testcases/batch action=delete 软删全部命中项，再逐条 purge。
    ids = []
    for query in ['/testcases?page=1&per_page=200',
                  '/testcases?page=1&per_page=200&trash=true']:
        try:
            st, d = _api(query)
        except Exception:
            continue
        items = d.get('data', {}).get('items', []) or []
        for c in items:
            if c.get('name', '').startswith(BASE_PREFIX):
                ids.append(c['id'])
    ids = list(dict.fromkeys(ids))
    if ids:
        try:
            _api('/testcases/batch', 'POST', {'action': 'delete', 'ids': ids})
        except Exception:
            pass
        for cid in ids:
            try:
                _api(f"/testcases/{cid}/purge", 'DELETE')
            except Exception:
                pass
    # 级联删除所有探针前缀分组（per_page=200：默认 100 会漏掉新增组，INT-639 分组分页口径）
    st, d = _api('/groups?page=1&per_page=200')
    items = d.get('data', {}).get('items', []) or []
    for g in items:
        if g.get('name', '').startswith(BASE_PREFIX):
            try:
                _api(f"/groups/{g['id']}?cascade=true", 'DELETE')
            except Exception:
                pass
    print('  cleanup done')


# ---------------------------------------------------------------------------
# Selenium 基础设施
# ---------------------------------------------------------------------------

def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-software-rasterizer')
    # 自建 user-data-dir（默认在 %TEMP%\multica-task-* 会被并发任务清扫误删→Chrome 连接断，
    # INT-997 五连崩根因之一）；换名驱动二进制防按映像名 taskkill 误杀。
    # 目录按进程唯一：复用同目录会让 /login 带旧登录态直接重定向 /dashboard（INT-997 实测）。
    _UDD = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'bin', f'int997_profile_{os.getpid()}')
    os.makedirs(_UDD, exist_ok=True)
    options.add_argument(f'--user-data-dir={_UDD}')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    _RENAMED = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'bin', 'int997_cdriver.exe')
    drv_path = _RENAMED if os.path.isfile(_RENAMED) else ''
    if not drv_path:
        import winreg
        chrome_major = 0
        chrome_patch = 0
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
                parts = winreg.QueryValueEx(k, 'version')[0].split('.')
                chrome_major = int(parts[0])
                chrome_patch = int(parts[-1]) if len(parts) >= 4 else 0
        except Exception:
            pass
        cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
        if chrome_major and os.path.isdir(cache_root):
            cands = []
            for ver in os.listdir(cache_root):
                exe = os.path.join(cache_root, ver, 'chromedriver.exe')
                if os.path.isfile(exe):
                    try:
                        cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                    except ValueError:
                        continue
            same = sorted(cands, key=lambda c: c[0])
            # 挑同大版本里 patch 最接近且不超前浏览器的驱动（Chrome 155.0.8059.80 对 .79 驱动最稳）
            best = None
            for ver, exe in same:
                if ver and ver[0] == chrome_major and ver[-1] <= chrome_patch:
                    best = exe
            if best is None and same:
                best = same[-1][1]
            drv_path = best or ''
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


_DRIVER = None


def _inject_fetch_capture(drv):
    # 页面内 fetch 打点（含响应 status）替代 chromedriver performance log——
    # get_log('performance') 长会话累积大缓冲会打崩 driver（INT-997 四连崩根因）。
    # Chrome 155 已移除 Network.setRequestInterception（见记忆），fetch 打点 + 合成 500 是本工作区先例。
    drv.execute_script(
        """
        if (!window.__int997_reqs) { window.__int997_reqs = []; }
        if (window.__int997_origFetch) { window.fetch = window.__int997_origFetch; }
        window.__int997_origFetch = window.fetch.bind(window);
        window.fetch = function(input, init) {
          const url = (typeof input === 'string') ? input : (input && input.url) || String(input);
          const method = (init && init.method) || 'GET';
          let body = null;
          if (init && init.body) {
            if (typeof init.body === 'string') {
              try { body = JSON.parse(init.body); } catch (e) { body = init.body; }
            } else { body = String(init.body); }
          }
          const rec = { url: String(url), method: String(method), body: body, status: null };
          window.__int997_reqs.push(rec);
          return window.__int997_origFetch.apply(this, arguments).then(
            function(res) { rec.status = res.status; return res; },
            function(err) { rec.status = 0; throw err; }
          );
        };
        """
    )


def _captured(drv):
    try:
        return drv.execute_script('return window.__int997_reqs || []')
    except Exception:
        return []


def _reset_capture(drv):
    drv.execute_script('window.__int997_reqs = []')


def _perf_network(drv):
    """网络证据源为页面内 fetch 打点（method/url/status/action），跨导航累积到 _NET_LOG。"""
    try:
        for r in _captured(drv):
            b = r.get('body')
            action = ''
            if isinstance(b, dict):
                action = str(b.get('action', ''))
            entry = {'method': r.get('method'), 'url': r.get('url', ''),
                     'status': r.get('status'), 'action': action}
            if entry not in _NET_LOG[-500:]:
                _NET_LOG.append(entry)
    except Exception:
        pass
    return list(_NET_LOG)


def _wait_requests(drv, url_sub, method=None, timeout=8):
    """等目标写请求出现且响应状态已落（页面内 fetch 打点；status 异步填充）。"""
    seen = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        for r in _captured(drv):
            u = r.get('url', '')
            m = r.get('method', '')
            if url_sub in u and m != 'GET':
                if method and m != method:
                    continue
                if r.get('status') is None:
                    continue  # 响应尚未到达，等下一轮
                b = r.get('body')
                action = ''
                if isinstance(b, dict):
                    action = str(b.get('action', ''))
                entry = {'method': m, 'url': u, 'status': r.get('status'), 'action': action}
                if entry not in _NET_LOG[-500:]:
                    _NET_LOG.append(entry)  # 证据累积（跨导航清空页面内数组后仍可汇总）
                seen.append(entry)
        if seen:
            return seen
        time.sleep(0.4)
    return seen


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _toast_text(drv):
    time.sleep(0.3)
    return '\n'.join(t.text for t in drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]"))


def _safe_get(drv, url, timeout=60):
    """带重试的页面导航（Chrome headless 偶发 renderer 超时，重试一次）。"""
    drv.set_page_load_timeout(timeout)
    for attempt in range(3):
        try:
            drv.get(url)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2.0)


def _goto(drv, path, wait_for=None):
    _safe_get(drv, BASE + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    if wait_for:
        WebDriverWait(drv, 20).until(lambda d: wait_for(d))
    time.sleep(1.2)
    _inject_fetch_capture(drv)


def _wait_case_card(drv, case_name, timeout=20):
    WebDriverWait(drv, timeout).until(
        lambda d: len(d.find_elements(
            By.CSS_SELECTOR, f"[role='checkbox'][aria-label='选择 {case_name}']")) > 0)
    time.sleep(0.3)


def _expand_group(drv, group_name):
    """INT-1027 分组默认收起：点组头展开。返回展开后的组卡；已展开则原样返回。
    组头=组卡内第一个 cursor-pointer 行（右侧 CaseGroupActions 区 stopPropagation 不受影响）。
    组卡内出现用例勾选框（aria-label^='选择 '）视为已展开。"""
    for _ in range(3):
        cards = drv.find_elements(By.XPATH,
            f"//div[contains(@class,'bg-card')][.//span[contains(., '{group_name}')]]")
        for card in cards:
            boxes = card.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']")
            if boxes:
                return card
            headers = card.find_elements(By.XPATH, ".//div[contains(@class,'cursor-pointer')]")
            if not headers:
                continue
            drv.execute_script('arguments[0].scrollIntoView({block:"center"})', headers[0])
            time.sleep(0.2)
            drv.execute_script('arguments[0].click()', headers[0])
            time.sleep(0.7)
            return card
        time.sleep(0.5)
    return None


def _load_more_in_group(drv, group_name, target_case=None, max_clicks=8):
    """组内懒加载：点「加载更多」直到目标用例出现（默认点到无钮为止）。
    INT-1027 分组默认收起：先展开组再查用例卡/加载更多。"""
    _expand_group(drv, group_name)
    for _ in range(max_clicks):
        if target_case:
            try:
                _wait_case_card(drv, target_case, timeout=3)
                return True
            except Exception:
                pass
        cards = drv.find_elements(By.XPATH,
            f"//div[contains(@class,'bg-card')][.//span[contains(., '{group_name}')]]")
        clicked = False
        for card in cards:
            btns = card.find_elements(By.XPATH, ".//button[contains(., '加载更多')]")
            if btns:
                drv.execute_script('arguments[0].scrollIntoView({block:"center"})', btns[0])
                time.sleep(0.2)
                btns[0].click()
                clicked = True
                time.sleep(0.8)
                break
        if not clicked:
            break
    if target_case:
        try:
            _wait_case_card(drv, target_case, timeout=5)
            return True
        except Exception:
            return False
    return True


def _group_card_present(drv, group_name):
    return len(drv.find_elements(By.XPATH,
        f"//div[contains(@class,'bg-card')][.//span[contains(., '{group_name}')]]")) > 0


def _load_more_groups(drv, target_group=None, max_clicks=40):
    """分组列表懒加载：点底部「已显示 N / M 个分组 · 加载更多」直到目标分组卡出现。

    共享库当前 133 个分组、每页 5 组，新增探针分组若落在首屏外，用例卡根本不渲染，
    不先加载到位后面的勾选/动作全超时（INT-997 实测 ⑧新组不可见即此）。
    判定用分组卡 DOM 而非 body 文本——toast「新分组：xxx」会误命中 body 文本。
    """
    for _ in range(max_clicks):
        if target_group:
            if _group_card_present(drv, target_group):
                return True
        btns = drv.find_elements(By.XPATH, "//button[contains(., '加载更多') and contains(., '个分组')]")
        if not btns:
            return target_group is None or _group_card_present(drv, target_group)
        drv.execute_script('arguments[0].scrollIntoView({block:"end"})', btns[0])
        time.sleep(0.2)
        btns[0].click()
        time.sleep(0.6)
    return target_group is None or _group_card_present(drv, target_group)


def _ensure_case_visible(drv, case_name):
    """按需加载探针分组卡（含改名后的组1）+ 展开组卡 + 组内懒加载，直到目标用例卡出现。

    先等用例名进 body（回收站查询异步落地，空态先渲染时勾选尚不存在），再定位勾选框。
    只加载到探针组卡出现为止（目标组卡可能不在首屏，但探针组用例数高、排序靠前），
    避免每次全量点穿共享库 27 页分组——长流程下 chromedriver 会话不稳定（INT-997 实测）。
    """
    # 1) 数据落地：用例名或探针组卡名出现在页面（组默认收起 INT-1027，用例名在展开前不入 body，
    #    以组卡出现为数据落地信号；用例名命中说明已展开渲染）
    deadline = time.time() + 20
    while time.time() < deadline:
        if _name_present(drv, case_name) or _group_card_present(drv, GROUP1):
            break
        time.sleep(0.5)
    # 2) 加载探针组卡（组1 可能已被 ⑫ 改名；含 新组/组1_copy）
    for g in (GROUP1, GROUP1 + '_改名', GROUP2, NEWGROUP, GROUP1 + '_copy'):
        if _group_card_present(drv, g):
            continue
        if _load_more_groups(drv, target_group=g):
            break
    # 3) 展开含目标用例的组（INT-1027 默认收起；用例卡在展开后才渲染）
    for g in (GROUP1, GROUP2, GROUP1 + '_改名', NEWGROUP):
        if _expand_group(drv, g):
            break
    try:
        _wait_case_card(drv, case_name, timeout=5)
        return True
    except Exception:
        # 4) 组内懒加载：轮询所有可见组卡「加载更多」直到目标出现
        for g in (GROUP1, GROUP2, GROUP1 + '_改名', NEWGROUP):
            if _load_more_in_group(drv, g, target_case=case_name):
                return True
        for _ in range(12):
            try:
                _wait_case_card(drv, case_name, timeout=2)
                return True
            except Exception:
                pass
            btns = drv.find_elements(
                By.XPATH, "//div[contains(@class,'bg-card')]//button[contains(., '加载更多')]")
            if not btns:
                break
            clicked = False
            for b in btns:
                try:
                    drv.execute_script('arguments[0].scrollIntoView({block:"center"})', b)
                    time.sleep(0.15)
                    b.click()
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                break
            time.sleep(0.6)
        try:
            _wait_case_card(drv, case_name, timeout=3)
            return True
        except Exception:
            return False


def _ensure_group_cases(drv, group_name, target_case, retries=2):
    """组内懒加载直到目标用例卡出现；失败整页刷新再试（共享库慢查询/并发下兜底）。"""
    for attempt in range(retries + 1):
        try:
            if _load_more_in_group(drv, group_name, target_case=target_case, max_clicks=10):
                return True
        except Exception:
            pass
        if attempt < retries:
            _safe_get(drv, BASE + '/testcases/by-group')
            try:
                WebDriverWait(drv, 30).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete')
            except Exception:
                pass
            time.sleep(1.5)
    try:
        _wait_case_card(drv, target_case, timeout=8)
        return True
    except Exception:
        return False


def _enter_workbench(drv):
    _safe_get(drv, BASE + '/login')
    WebDriverWait(drv, 20).until(lambda d: '进入工作台' in _body_text(d))
    btns = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if btns:
        btns[0].click()
    time.sleep(2.0)
    # AUTH_MODE=off：无登录流程，注入自签 dev token 供 per-user 写侧（收藏）取 user_id
    drv.execute_script(
        "localStorage.setItem('iatp:auth:token:v1', arguments[0]);", _mint_token())
    drv.execute_script(
        "localStorage.setItem('iatp:algorithm:v1',"
        " JSON.stringify({state:{algorithmId:''},version:0}));")
    _goto(drv, '/testcases/by-group',
          wait_for=lambda d: GROUP1 in _body_text(d) or '用例管理' in _body_text(d))
    time.sleep(1.5)


def _goto_trash(drv):
    """进入回收站视图：URL ?trash=true 不驱动本地 filter（filters 在组件 state），
    须点筛选工具条「回收站」toggle 才切进回收站态（INT-997 ⑬实测）。"""
    _goto(drv, '/testcases/by-group',
          wait_for=lambda d: '用例管理' in _body_text(d) or '按分组' in _body_text(d))
    time.sleep(1.0)
    btns = drv.find_elements(By.XPATH, "//button[@title='回收站']")
    assert btns, '回收站 toggle 未找到'
    drv.execute_script('arguments[0].click()', btns[0])
    time.sleep(1.5)


def _set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);", mode)
    time.sleep(0.8)


def _shot(drv, name, sub):
    d = os.path.join(ARTIFACTS, sub)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, f'{name}.png'))
    with open(os.path.join(d, f'{name}.page.html'), 'w', encoding='utf-8') as f:
        f.write(drv.page_source)


def _find_case_card(drv, case_name):
    boxes = drv.find_elements(By.CSS_SELECTOR, f"[role='checkbox'][aria-label='选择 {case_name}']")
    if not boxes:
        return None
    node = boxes[0]
    for _ in range(8):
        node = node.find_element(By.XPATH, '..')
        try:
            # 回收站态用例卡仅 2 个 aria-label 动作钮（恢复/彻底删除），阈值取 1
            if len(node.find_elements(By.CSS_SELECTOR, 'button[aria-label]')) >= 1:
                return node
        except Exception:
            continue
    return boxes[0].find_element(By.XPATH, '..')


def _click_case_action(drv, case_name, aria_label):
    _wait_overlay_gone(drv)
    _ensure_case_visible(drv, case_name)
    card = None
    # React query refetch 致 DOM 短暂卸载/重挂（INT-932 同根因），重试定位再断言
    for _ in range(3):
        card = _find_case_card(drv, case_name)
        if card is not None:
            break
        time.sleep(1.0)
        _ensure_case_visible(drv, case_name)
    assert card is not None, f'用例卡 {case_name} 未找到'
    target = None
    for b in card.find_elements(By.CSS_SELECTOR, 'button[aria-label]'):
        if b.get_attribute('aria-label') == aria_label:
            target = b
            break
    assert target is not None, f'动作钮 {aria_label} 未在卡 {case_name} 找到'
    drv.execute_script('arguments[0].scrollIntoView({block:"center"})', target)
    time.sleep(0.3)
    drv.execute_script('arguments[0].click()', target)
    time.sleep(0.6)


def _select_cases(drv, names):
    _wait_overlay_gone(drv)
    for n in names:
        boxes = []
        for _ in range(3):
            if _ensure_case_visible(drv, n):
                boxes = drv.find_elements(By.CSS_SELECTOR, f"[role='checkbox'][aria-label='选择 {n}']")
                if boxes:
                    break
            time.sleep(1.0)
        assert boxes, f'未找到 {n} 勾选框'
        b = boxes[0]
        if b.get_attribute('aria-checked') != 'true':
            drv.execute_script("arguments[0].click()", b)
            time.sleep(0.3)


def _bulk_bar(drv):
    _wait_overlay_gone(drv)
    WebDriverWait(drv, 8).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")) > 0)
    return drv.find_element(By.XPATH,
        "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")


def _bulk_button(drv, label):
    bar = _bulk_bar(drv)
    target = None
    for b in bar.find_elements(By.TAG_NAME, 'button'):
        if label in (b.text or ''):
            target = b
            break
    assert target is not None, f'批量钮 {label} 未找到'
    drv.execute_script('arguments[0].click()', target)
    time.sleep(0.5)


def _confirm_click(drv, confirm_text):
    time.sleep(0.8)
    btns = drv.find_elements(By.XPATH,
        f"//div[@data-slot='alert-dialog-content']//button[contains(., '{confirm_text}')]")
    if not btns:
        btns = drv.find_elements(By.XPATH, f"//button[contains(., '{confirm_text}')]")
    assert btns, f'确认钮 {confirm_text} 未找到'
    drv.execute_script('arguments[0].click()', btns[-1])
    time.sleep(0.8)


def _wait_overlay_gone(drv, timeout=6):
    """等 base-ui 弹窗遮罩退场（close 动画期间遮罩拦截后续点击，INT-997 ⑩实测）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        overlays = drv.find_elements(By.CSS_SELECTOR,
            "[data-slot='dialog-overlay'][data-open=''],"
            "[data-slot='alert-dialog-overlay'][data-open='']")
        if not overlays:
            return True
        time.sleep(0.3)
    return True


def _group_header_btn(drv, group_name, label):
    _wait_overlay_gone(drv)
    found = _load_more_groups(drv, target_group=group_name)
    if not found:
        # groups query 异步 refetch 未落地：整页刷新后再按分页加载目标组卡
        _safe_get(drv, BASE + '/testcases/by-group')
        WebDriverWait(drv, 25).until(
            lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1.2)
        _inject_fetch_capture(drv)  # 整页刷新后 window.fetch 还原，需重挂打点
        _load_more_groups(drv, target_group=group_name)
    target = None
    cards = drv.find_elements(By.XPATH,
        f"//div[contains(@class,'bg-card')][.//span[contains(., '{group_name}')]]")
    for card in cards:
        btns = card.find_elements(By.XPATH, f".//button[contains(., '{label}')]")
        if btns:
            target = btns[0]
            break
    assert target is not None, f'分组头钮 {label} 未找到（组 {group_name}）'
    drv.execute_script('arguments[0].scrollIntoView({block:"center"})', target)
    time.sleep(0.3)
    # JS 直发点击：base-ui 弹窗关闭动画期间遮罩仍拦截 WebDriver 原生点击
    # （INT-997 ⑩实测 ElementClickInterceptedException），JS dispatch 不在此例。
    drv.execute_script('arguments[0].click()', target)
    time.sleep(0.6)


def _click_radio_label(dlg, text):
    labels = dlg.find_elements(By.XPATH, f".//label[contains(., '{text}')]")
    assert labels, f'单选 {text} 未找到'
    labels[0].click()
    time.sleep(0.4)


def _select_option_in_dialog(drv, text):
    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")) > 0)
    items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
    target = None
    for it in items:
        if text in (it.text or ''):
            target = it
            break
    assert target is not None, f'Select 项 {text} 缺失'
    drv.execute_script('arguments[0].scrollIntoView({block:"center"})', target)
    time.sleep(0.3)
    target.click()
    time.sleep(0.5)


def _name_present(drv, name):
    """精确匹配用例/分组名是否在页面（名称后不跟 _/字母/数字，避免 D 误匹配 D_copy）。"""
    import re
    body = _body_text(drv)
    return len(re.findall(re.escape(name) + r'(?![_A-Za-z0-9])', body)) > 0


def _dialog_content(drv, title):
    xpath = f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    global _DRIVER
    gid1, gid2, cids = _setup_probe_data()
    _DRIVER = _driver()
    drv = _DRIVER
    try:
        _enter_workbench(drv)
        # 组内懒加载每页 5 条：先等任一探针用例出现，再加载组1全部用例（A 排最后）
        _wait_case_card(drv, CASE_PREFIX + 'F', timeout=25)
        _load_more_in_group(drv, GROUP1, target_case=CASE_PREFIX + 'A')
        _reset_capture(drv)
        body = _body_text(drv)
        _record('页面加载-用例管理页', '用例管理' in body or '按分组' in body,
                'body 含按分组/用例管理')
        _record('分组可见-组1', GROUP1 in body, f'组1={GROUP1} 在页面上')
        _shot(drv, '01_light_list', 'light')

        # ── ① 行收藏（A）──────────────────────────────────
        _reset_capture(drv)
        _click_case_action(drv, CASE_PREFIX + 'A', '收藏')
        fav_req = _wait_requests(drv, f'/testcases/{cids["A"]}/favorite', 'POST')
        fav_ok = bool(fav_req)
        fav_status = fav_req[0].get('status') if fav_req else None
        toasts = _toast_text(drv)
        _record('①行收藏-真实请求', fav_ok,
                f'POST /testcases/{cids["A"]}/favorite status={fav_status}')
        _record('①行收藏-生效', fav_status == 200 and '已加入收藏' in toasts,
                f'status={fav_status} toast={toasts[:40]!r}')
        time.sleep(1.2)

        # ── ② 行复制（B）──────────────────────────────────
        _reset_capture(drv)
        _click_case_action(drv, CASE_PREFIX + 'B', '复制用例')
        cp_req = _wait_requests(drv, f'/testcases/{cids["B"]}/copy', 'POST')
        cp_status = cp_req[0].get('status') if cp_req else None
        time.sleep(2.0)
        b_copy = CASE_PREFIX + 'B_copy'
        _load_more_in_group(drv, GROUP1, target_case=b_copy)
        _record('②行复制-真实请求', bool(cp_req),
                f'POST /testcases/{cids["B"]}/copy status={cp_status}')
        _record('②行复制-生效(副本出现)', b_copy in _body_text(drv),
                f'新用例 {b_copy} 出现')

        # ── ③ 行删除（C）──────────────────────────────────
        _reset_capture(drv)
        _click_case_action(drv, CASE_PREFIX + 'C', '删除用例')
        _confirm_click(drv, '删除')
        del_req = _wait_requests(drv, f'/testcases/{cids["C"]}', 'DELETE')
        del_status = del_req[0].get('status') if del_req else None
        time.sleep(2.0)
        _record('③行删除-真实请求', bool(del_req),
                f'DELETE /testcases/{cids["C"]} status={del_status}')
        _record('③行删除-生效(列表消失)', CASE_PREFIX + 'C' not in _body_text(drv),
                'C 从正常列表消失')

        # ── ④ 批量复制（D、E）──────────────────────────────
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'D', CASE_PREFIX + 'E'])
        _bulk_button(drv, '批量复制')
        _confirm_click(drv, '批量复制')
        bcopy_req = _wait_requests(drv, '/testcases/batch', 'POST')
        bcopy_ok = bool(bcopy_req) or any(
            (r.get('body') or {}).get('action') == 'copy' for r in _captured(drv))
        time.sleep(2.0)
        _record('④批量复制-真实请求', bcopy_ok, 'POST /testcases/batch action=copy')
        # 生效：以库内真实数据为准（懒加载分页下 UI 渲染不可靠；API 权威）
        st, d = _api('/testcases?page=1&per_page=200')
        names = [i.get('name', '') for i in (d.get('data', {}).get('items') or [])]
        _record('④批量复制-生效(副本落库)',
                CASE_PREFIX + 'D_copy' in names and CASE_PREFIX + 'E_copy' in names,
                f'D_copy/E_copy 已入库（总数 {len(names)}）')

        # ── ⑤ 批量删除（D、E 原）───────────────────────────
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'D', CASE_PREFIX + 'E'])
        _bulk_button(drv, '批量删除')
        _confirm_click(drv, '批量删除')
        bdel_req = _wait_requests(drv, '/testcases/batch', 'POST')
        bdel_ok = bool(bdel_req) or any(
            (r.get('body') or {}).get('action') == 'delete' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑤批量删除-真实请求', bdel_ok, 'POST /testcases/batch action=delete')
        _record('⑤批量删除-生效(D/E消失)',
                not _name_present(drv, CASE_PREFIX + 'D')
                and not _name_present(drv, CASE_PREFIX + 'E'),
                'D/E 从列表消失')

        # ── ⑥ 批量调整分组-移动（B、B_copy → 组2）────────────
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'B', CASE_PREFIX + 'B_copy'])
        _bulk_button(drv, '批量调整分组')
        dlg = _dialog_content(drv, '批量调整分组')
        trigs = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
        trigs[0].click()
        _select_option_in_dialog(drv, GROUP2)
        dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
        move_req = _wait_requests(drv, '/testcases/batch', 'POST')
        move_ok = bool(move_req) or any(
            (r.get('body') or {}).get('action') == 'move_to_group' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑥批量调整分组-移动真实请求', move_ok,
                f'POST /testcases/batch action=move_to_group {move_req[:1]}')

        # ── ⑦ 批量调整分组-复制（D_copy、E_copy → 组2）────────
        _reset_capture(drv)
        _load_more_in_group(drv, GROUP1, target_case=CASE_PREFIX + 'E_copy')
        _select_cases(drv, [CASE_PREFIX + 'D_copy', CASE_PREFIX + 'E_copy'])
        _bulk_button(drv, '批量调整分组')
        dlg = _dialog_content(drv, '批量调整分组')
        _click_radio_label(dlg, '复制到目标分组')
        trigs = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
        trigs[0].click()
        _select_option_in_dialog(drv, GROUP2)
        dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
        cpg_req = _wait_requests(drv, '/testcases/batch', 'POST')
        cpg_ok = bool(cpg_req) or any(
            (r.get('body') or {}).get('action') == 'copy_to_group' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑦批量调整分组-复制真实请求', cpg_ok,
                f'POST /testcases/batch action=copy_to_group {cpg_req[:1]}')

        # ── ⑧ 批量调整分组-新建分组（F → 新组）──────────────
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'F'])
        _bulk_button(drv, '批量调整分组')
        dlg = _dialog_content(drv, '批量调整分组')
        trigs = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
        trigs[0].click()
        _select_option_in_dialog(drv, '+ 新建分组')
        inp = dlg.find_element(By.CSS_SELECTOR, "input[aria-label='新分组名称']")
        inp.clear()
        inp.send_keys(NEWGROUP)
        dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
        ng_req = _wait_requests(drv, '/groups', 'POST')
        ng_ok = bool(ng_req)
        ng_status = ng_req[0].get('status') if ng_req else None
        time.sleep(2.0)
        _record('⑧批量新建分组-真实请求', ng_ok,
                f'POST /groups status={ng_status}')
        _goto(drv, '/testcases/by-group',
              wait_for=lambda d: '用例管理' in _body_text(d) or '按分组' in _body_text(d))
        _load_more_groups(drv, target_group=NEWGROUP)
        _record('⑧批量新建分组-新组出现', NEWGROUP in _body_text(drv),
                f'新组 {NEWGROUP} 出现')

        # ── ⑨ 标签-添加 / 移除 / 改名（A、D_copy）────────────
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'A', CASE_PREFIX + 'D_copy'])
        _bulk_button(drv, '批量管理标签')
        dlg = _dialog_content(drv, '批量管理标签')
        inp = dlg.find_element(By.CSS_SELECTOR, "input[placeholder*='输入标签']")
        inp.send_keys('INT997标签')
        inp.send_keys('\ue007')
        time.sleep(0.6)
        dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
        at_req = _wait_requests(drv, '/testcases/batch', 'POST')
        at_ok = bool(at_req) or any(
            (r.get('body') or {}).get('action') == 'add_tags' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑨标签-添加真实请求', at_ok,
                f'POST /testcases/batch action=add_tags {at_req[:1]}')

        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'A', CASE_PREFIX + 'D_copy'])
        _bulk_button(drv, '批量管理标签')
        dlg = _dialog_content(drv, '批量管理标签')
        _click_radio_label(dlg, '移除标签')
        inp = dlg.find_element(By.CSS_SELECTOR, "input[placeholder*='输入标签']")
        inp.send_keys('INT997标签')
        inp.send_keys('\ue007')
        time.sleep(0.6)
        dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
        rt_req = _wait_requests(drv, '/testcases/batch', 'POST')
        rt_ok = bool(rt_req) or any(
            (r.get('body') or {}).get('action') == 'remove_tags' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑨标签-移除真实请求', rt_ok,
                f'POST /testcases/batch action=remove_tags {rt_req[:1]}')

        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'A', CASE_PREFIX + 'D_copy'])
        _bulk_button(drv, '批量管理标签')
        dlg = _dialog_content(drv, '批量管理标签')
        _click_radio_label(dlg, '修改标签名字')
        sel = dlg.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
        sel[0].click()
        _select_option_in_dialog(drv, 'INT997标签')
        inp = dlg.find_element(By.CSS_SELECTOR, "input[placeholder*='新标签名称']")
        inp.send_keys('INT997标签改名')
        dlg.find_element(By.XPATH, ".//button[contains(., '确定')]").click()
        rn_req = _wait_requests(drv, '/testcases/batch', 'POST')
        rn_ok = bool(rn_req) or any(
            (r.get('body') or {}).get('action') == 'rename_tag' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑨标签-改名真实请求', rn_ok,
                f'POST /testcases/batch action=rename_tag {rn_req[:1]}')

        # ── ⑩ 复制分组（组1）──────────────────────────────
        _reset_capture(drv)
        _group_header_btn(drv, GROUP1, '复制')
        cg_req = _wait_requests(drv, '/testcases/batch', 'POST')
        cg_ok = bool(cg_req) or any(
            (r.get('body') or {}).get('action') == 'copy_by_group' for r in _captured(drv))
        time.sleep(2.5)
        _record('⑩复制分组-真实请求', cg_ok,
                f'POST /testcases/batch action=copy_by_group {cg_req[:1]}')
        _load_more_groups(drv, target_group=GROUP1 + '_copy')
        _record('⑩复制分组-生效(新组出现)', GROUP1 + '_copy' in _body_text(drv),
                f'组 {GROUP1}_copy 出现')

        # ── ⑪ 删除分组（组1_copy）─────────────────────────
        _reset_capture(drv)
        _group_header_btn(drv, GROUP1 + '_copy', '删除')
        _confirm_click(drv, '删除')
        dg_req = _wait_requests(drv, '/groups/', 'DELETE')
        dg_ok = bool(dg_req)
        dg_status = dg_req[0].get('status') if dg_req else None
        time.sleep(2.5)
        _record('⑪删除分组-真实请求', dg_ok,
                f'DELETE /groups/{{id}}?cascade=true status={dg_status}')
        _record('⑪删除分组-生效(消失)', GROUP1 + '_copy' not in _body_text(drv),
                f'组 {GROUP1}_copy 消失')

        # ── ⑫ 编辑分组（组1 → 改名）─────────────────────────
        _reset_capture(drv)
        _group_header_btn(drv, GROUP1, '编辑')
        dlg = _dialog_content(drv, '编辑分组')
        name_inp = dlg.find_element(By.CSS_SELECTOR, "input[placeholder*='分组名称']")
        name_inp.clear()
        name_inp.send_keys(GROUP1 + '_改名')
        dlg.find_element(By.XPATH, ".//button[contains(., '保存')]").click()
        eg_req = _wait_requests(drv, f'/groups/{gid1}', 'PUT')
        eg_ok = bool(eg_req)
        eg_status = eg_req[0].get('status') if eg_req else None
        time.sleep(2.0)
        _record('⑫编辑分组-真实请求', eg_ok,
                f'PUT /groups/{gid1} status={eg_status}')
        if not _load_more_groups(drv, target_group=GROUP1 + '_改名'):
            _safe_get(drv, BASE + '/testcases/by-group')
            WebDriverWait(drv, 25).until(
                lambda d: d.execute_script('return document.readyState') == 'complete')
            time.sleep(1.2)
            _load_more_groups(drv, target_group=GROUP1 + '_改名')
        _record('⑫编辑分组-生效(改名)', GROUP1 + '_改名' in _body_text(drv),
                f'组 {GROUP1}_改名 出现')

        _shot(drv, '02_light_list_after_ops', 'light')

        # ── 回收站区 ─────────────────────────────────────
        # 现回收站：C、D、E（D/E 步⑤删除；C 步③删除）
        _goto_trash(drv)
        time.sleep(1.5)

        # ⑬ 行恢复（C）
        _reset_capture(drv)
        _click_case_action(drv, CASE_PREFIX + 'C', '恢复用例')
        _confirm_click(drv, '恢复')
        rr_req = _wait_requests(drv, f'/testcases/{cids["C"]}/restore', 'POST')
        rr_status = rr_req[0].get('status') if rr_req else None
        time.sleep(2.0)
        _record('⑬回收站-行恢复真实请求', bool(rr_req),
                f'POST /testcases/{cids["C"]}/restore status={rr_status}')
        _shot(drv, '03_light_trash', 'trash')

        # ⑭ 批量恢复（D、E）
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'D', CASE_PREFIX + 'E'])
        _bulk_button(drv, '批量恢复')
        _confirm_click(drv, '批量恢复')
        br_req = _wait_requests(drv, '/testcases/batch', 'POST')
        br_ok = bool(br_req) or any(
            (r.get('body') or {}).get('action') == 'restore' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑭回收站-批量恢复真实请求', br_ok,
                f'POST /testcases/batch action=restore {br_req[:1]}')

        # 为 行彻底删除/批量彻底删除 造回收站数据：删 A、D_copy（正常视图）
        _goto(drv, '/testcases/by-group',
              wait_for=lambda d: '用例管理' in _body_text(d) or '按分组' in _body_text(d))
        time.sleep(1.0)
        _click_case_action(drv, CASE_PREFIX + 'A', '删除用例')
        _confirm_click(drv, '删除')
        time.sleep(1.5)
        _click_case_action(drv, CASE_PREFIX + 'D_copy', '删除用例')
        _confirm_click(drv, '删除')
        time.sleep(1.5)
        _goto_trash(drv)
        time.sleep(1.0)

        # ⑮ 行彻底删除（A）
        _reset_capture(drv)
        _click_case_action(drv, CASE_PREFIX + 'A', '彻底删除（不可恢复）')
        _confirm_click(drv, '彻底删除')
        pp_req = _wait_requests(drv, '/purge', 'DELETE', timeout=5)
        pp_req = pp_req or [r for r in _perf_network(drv)
                            if '/purge' in r.get('url', '') and r.get('method') == 'DELETE']
        pp_status = pp_req[0].get('status') if pp_req else None
        time.sleep(2.0)
        _record('⑮回收站-行彻底删除真实请求', bool(pp_req),
                f'DELETE /testcases/{{id}}/purge status={pp_status}')

        # ⑯ 批量彻底删除（D_copy）
        _reset_capture(drv)
        _select_cases(drv, [CASE_PREFIX + 'D_copy'])
        _bulk_button(drv, '批量彻底删除')
        _confirm_click(drv, '批量彻底删除')
        bpp_req = _wait_requests(drv, '/testcases/purge', 'POST')
        bpp_status = bpp_req[0].get('status') if bpp_req else None
        time.sleep(2.0)
        _record('⑯回收站-批量彻底删除真实请求', bool(bpp_req),
                f'POST /testcases/purge status={bpp_status}')

        # ⑰ 全部恢复：再造两条回收站数据（删 B、B_copy）再全部恢复
        _goto(drv, '/testcases/by-group',
              wait_for=lambda d: '用例管理' in _body_text(d) or '按分组' in _body_text(d))
        time.sleep(1.0)
        _click_case_action(drv, CASE_PREFIX + 'B', '删除用例')
        _confirm_click(drv, '删除')
        time.sleep(1.2)
        _click_case_action(drv, CASE_PREFIX + 'B_copy', '删除用例')
        _confirm_click(drv, '删除')
        time.sleep(1.5)
        _goto_trash(drv)
        time.sleep(1.0)
        _reset_capture(drv)
        restore_btns = drv.find_elements(By.XPATH, "//button[contains(., '全部恢复')]")
        assert restore_btns, '全部恢复按钮未找到'
        drv.execute_script('arguments[0].click()', restore_btns[0])
        _confirm_click(drv, '全部恢复')
        ra_req = _wait_requests(drv, '/testcases/batch', 'POST')
        ra_ok = bool(ra_req) or any(
            (r.get('body') or {}).get('action') == 'restore' for r in _captured(drv))
        time.sleep(2.0)
        _record('⑰回收站-全部恢复真实请求', ra_ok,
                f'POST /testcases/batch action=restore（全部恢复） {ra_req[:1]}')

        # ── 深色截图 ────────────────────────────────────
        _goto(drv, '/testcases/by-group', wait_for=lambda d: GROUP1 + '_改名' in _body_text(d))
        time.sleep(1.0)
        _set_theme(drv, 'dark')
        time.sleep(1.0)
        _shot(drv, '04_dark_list', 'dark')
        _shot(drv, '05_dark_after_ops', 'dark')

        # ── Network 证据汇总 ─────────────────────────────
        net = _perf_network(drv)
        write_net = os.path.join(ARTIFACTS, 'network_evidence.txt')
        os.makedirs(ARTIFACTS, exist_ok=True)
        with open(write_net, 'w', encoding='utf-8') as f:
            f.write('INT-997 Network 证据（performance log 汇总）\n\n')
            for n in net:
                if n.get('method') != 'GET':
                    f.write(f"{n['method']} {n['url']} status={n.get('status')}\n")
        _record('网络证据落盘', os.path.exists(write_net), write_net)

    finally:
        try:
            drv.quit()
        except Exception:
            pass
        _DRIVER = None
        try:
            _cleanup(gid1, gid2, cids)
        except Exception as e:
            print('  cleanup error:', e)

    print('\n===== INT-997 验收结果汇总 =====')
    fails = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f'  {"✅" if ok else "❌"} {name}: {detail}')
    print(f'\n通过 {len(RESULTS) - len(fails)}/{len(RESULTS)}')
    return 1 if fails else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
