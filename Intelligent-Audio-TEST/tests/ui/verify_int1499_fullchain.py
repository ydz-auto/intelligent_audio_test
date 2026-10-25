# -*- coding: utf-8 -*-
"""INT-1499 全链路实测：挑选（阶段 1/2）→ 加购 → 购物车四视图 → 复核 → 下单 merge → 页签/日常标识。

被测树：默认 15173 发布镜像（wiring/react afcd3f562 = INT-1509 + INT-1694 + INT-1687 接线后重建），
后端为 docker 真实库栈 15000（库 intelligent_audio_test）；也可用 INT1499_BASE 指向旁路容器。

用法（分阶段跑，购物车跨阶段共享）：
  INT1499_BASE=http://127.0.0.1:15173 python tests/ui/verify_int1499_fullchain.py --phase light --keep-cart
  INT1499_BASE=http://127.0.0.1:15173 python tests/ui/verify_int1499_fullchain.py --phase edge  --keep-cart
  INT1499_BASE=http://127.0.0.1:15173 python tests/ui/verify_int1499_fullchain.py --phase dark  --keep-cart
  INT1499_BASE=http://127.0.0.1:15173 python tests/ui/verify_int1499_fullchain.py --phase checkout
产物：tests/ui/artifacts/int1499_fullchain/*.png + result.json（INT1499_ART_DIR 可换目录）
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
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

BASE = os.environ.get('INT1499_BASE', 'http://127.0.0.1:15173')
API = os.environ.get('INT1499_API', 'http://127.0.0.1:15000')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.environ.get('INT1499_ART_DIR') or os.path.join(HERE, 'artifacts', 'int1499_fullchain')
os.makedirs(ART, exist_ok=True)

LOGIN_USER = os.environ.get('INT1499_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('INT1499_PASS', 'JieXianTest@2026')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
TASK_NAME = os.environ.get('INT1499_TASK_NAME', '接线测试_INT1499_全链路')

TOKEN = {'v': None}
CREATED = {'task_id': None}
CHECKS = []
FAILS = []
RESULT = {'base': BASE, 'api': API, 'health': [], 'shots': [], 'network': [], 'data': {}}


def check(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('CHECK', 'PASS' if ok else 'FAIL', name, '|', str(detail)[:300])
    if not ok:
        FAILS.append(name)


def health(tag):
    try:
        with urllib.request.urlopen(API + '/health', timeout=15) as r:
            body = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        body = {'error': str(exc)}
    RESULT['health'].append({'at': tag, 'body': body})
    print('HEALTH', tag, body)
    check('防串库 %s：database=intelligent_audio_test' % tag,
          body.get('database') == 'intelligent_audio_test', body)


LOGIN_JS = r"""
return (async () => {
  const keyResp = await fetch('/api/v1/auth/login/encryption-key').then(r=>r.json());
  const d = keyResp.data || keyResp;
  if(!d.enabled) return {step:'disabled'};
  const pem = d.public_key.replace(/-----[^-]+-----/g,'').replace(/\s+/g,'');
  const bin = Uint8Array.from(atob(pem), c=>c.charCodeAt(0));
  const key = await crypto.subtle.importKey('spki', bin, {name:'RSA-OAEP', hash:'SHA-256'}, false, ['encrypt']);
  const enc = await crypto.subtle.encrypt({name:'RSA-OAEP'}, key, new TextEncoder().encode(arguments[0]));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(enc)));
  const body = new URLSearchParams({username: arguments[1], password_encrypted: b64, encryption_key_id: d.kid});
  const r = await fetch('/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  const txt = await r.text();
  let j = {}; try { j = JSON.parse(txt); } catch(e) {}
  if (r.ok && j.access_token) localStorage.setItem('iatp:auth:token:v1', j.access_token);
  return {status: r.status, token: j.access_token || null, body: r.ok ? 'ok' : txt.slice(0,300)};
})()
"""


def driver(w=1560, h=1080):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=%d,%d' % (w, h))
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg

    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:  # noqa: BLE001
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(150)
    d.set_script_timeout(150)
    return d


def login(d):
    res = {}
    for _ in range(3):
        try:
            d.get(BASE + '/login')
            time.sleep(4)
            res = d.execute_script(LOGIN_JS, LOGIN_PASS, LOGIN_USER)
            if res.get('token'):
                break
        except Exception:  # noqa: BLE001
            time.sleep(2)
    TOKEN['v'] = res.get('token')
    print('LOGIN', res.get('status'), bool(TOKEN['v']))
    check('真实账号登录拿到 token', bool(TOKEN['v']), res.get('body'))
    if not TOKEN['v']:
        raise RuntimeError('login failed')


def set_theme(d, mode):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.refresh()
    time.sleep(3.5)


def shot(d, name):
    d.execute_script(
        'window.scrollTo(0,0);document.querySelectorAll("*").forEach(function(e){'
        'if(e.scrollTop>0&&e.scrollHeight>e.clientHeight+20)e.scrollTop=0;});'
    )
    time.sleep(0.6)
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    RESULT['shots'].append(p)
    print('SHOT', name)


def _root(root):
    """把 WebDriver 归一成 None（document），避免把 driver 当元素塞进 JS。"""
    if root is None:
        return None
    if not hasattr(root, 'tag_name'):
        return None
    return root


def count(d, css, root=None):
    return d.execute_script(
        'var root=arguments[0]||document;'
        'return Array.from(root.querySelectorAll(arguments[1]))'
        '.filter(function(e){return e.offsetParent!==null;}).length;',
        _root(root),
        css,
    )


def texts(d, root=None):
    return d.execute_script(
        'var root=arguments[0]||document;'
        'return Array.from(root.querySelectorAll("button"))'
        '.filter(function(b){return b.offsetParent!==null;})'
        '.map(function(b){return (b.textContent||"").trim();});',
        _root(root),
    )


def body_text(d, root=None):
    return d.execute_script(
        'return (arguments[0]||document.body).innerText||"";',
        _root(root),
    )


def click_text(d, needle, root=None, exact=False, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok = d.execute_script(
            'var root=arguments[0]||document,needle=arguments[1],exact=arguments[2];'
            'var el=Array.from(root.querySelectorAll("button")).find(function(b){'
            'if(b.offsetParent===null)return false;'
            'var t=(b.textContent||"").trim();'
            'return exact?(t===needle):(t.indexOf(needle)>=0);});'
            'if(!el)return false;'
            'el.scrollIntoView({block:"center"});el.click();return true;',
            _root(root),
            needle,
            exact,
        )
        if ok:
            return True
        time.sleep(0.5)
    return False


SEL_CASE_ORG_HDR = "[class*='flex-wrap items-center gap-2']"


def org_header_count(d, root=None):
    """用例视图 / 任务视图用例子模式的组织组头（PickCaseOrgList → CaseSubGroupHeader，无 -org: testid）。"""
    return count(d, SEL_CASE_ORG_HDR, root)


def visible_dialog(d):
    return d.execute_script(
        'var ds=Array.from(document.querySelectorAll(\'[role="dialog"],[role="alertdialog"]\'))'
        '.filter(function(x){var r=x.getBoundingClientRect();'
        'return r.width>0&&r.height>0;});return ds[ds.length-1]||null;'
    )


def expand_all(d, root=None, rounds=12, width=4):
    for _ in range(rounds):
        n = d.execute_script(
            'var root=arguments[0]||document,w=arguments[1];'
            'var btns=Array.from(root.querySelectorAll(\'button[aria-label="展开"]\'))'
            '.filter(function(b){return b.offsetParent!==null;}).slice(0,w);'
            'btns.forEach(function(b){b.scrollIntoView({block:"center"});b.click();});'
            'return btns.length;',
            _root(root),
            width,
        )
        time.sleep(0.35)
        if not n:
            break
    time.sleep(0.4)


def drain(d):
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:  # noqa: BLE001
        return out
    for e in logs:
        try:
            m = json.loads(e['message'])['message']
        except Exception:  # noqa: BLE001
            continue
        if m.get('method') != 'Network.responseReceived':
            continue
        r = m['params']['response']
        u = r.get('url') or ''
        if '/api/' in u:
            out.append({'status': r.get('status'), 'url': u.split('/api/v1')[-1][:120]})
    return out


def tab_counts(d):
    out = {}
    for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        txt = (t.text or '').strip()
        if txt:
            out[txt] = txt
    return out


def open_pick(d, wait_rows=420):
    d.get(BASE + '/tasks?tab=cherry-picks')
    time.sleep(4)
    if not click_text(d, '开始挑选', timeout=90):
        raise RuntimeError('找不到「开始挑选」')
    WebDriverWait(d, 120).until(
        lambda x: len([c for c in x.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
                       if (c.get_attribute('aria-label') or '').startswith('选择任务')]) > 0
    )
    time.sleep(1.5)


def pick_task_checkboxes(d):
    return [c for c in d.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            if (c.get_attribute('aria-label') or '').startswith('选择任务') and c.is_displayed()]


def select_tasks(d, ids=(418, 419)):
    rows = pick_task_checkboxes(d)
    by_id = {}
    for cb in rows:
        try:
            row = cb.find_element(By.XPATH, './ancestor-or-self::*[@data-testid][1]')
            tid = (row.get_attribute('data-testid') or '').replace('pick-task-', '')
            if tid.isdigit():
                by_id[int(tid)] = cb
        except Exception:  # noqa: BLE001
            pass
    chosen = []
    for i in ids:
        if i in by_id:
            d.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();', by_id[i])
            chosen.append(i)
            time.sleep(0.4)
    if len(chosen) < 2:
        for cb in rows:
            j = cb.get_attribute('aria-label')
            d.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();', cb)
            chosen.append(j)
            time.sleep(0.4)
            if len(chosen) >= 2:
                break
    print('STAGE1_SELECTED', chosen)
    return chosen


def stage1_detail(d):
    """阶段 1 行明细：id / 行文本（含执行状态徽章与「n 条」计数）。"""
    out = []
    for row in d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']"):
        tid = (row.get_attribute('data-testid') or '').replace('pick-task-', '')
        out.append({'id': tid, 'text': (row.text or '').replace('\n', ' ')[:120]})
    return out


def select_task_ids(d, ids):
    """按任务 id 精确勾选（不兜底补选），返回实际勾到的 id。"""
    chosen = []
    for tid in ids:
        els = d.find_elements(By.CSS_SELECTOR, "[data-testid='pick-task-%d']" % tid)
        if not els:
            continue
        cb = els[0].find_elements(By.CSS_SELECTOR, "[role='checkbox']")
        if cb:
            d.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();', cb[0])
            chosen.append(tid)
            time.sleep(0.4)
    print('STAGE1_SELECTED_EXACT', chosen)
    return chosen


def pickable_backend(d):
    """后端 pickable-tasks 口径（带 token，页面内 fetch）：总数与状态分布。"""
    try:
        return d.execute_script('''
          return (async () => {
            const t = localStorage.getItem('iatp:auth:token:v1');
            const r = await fetch('/api/v1/tasks/cherry-picks/pickable-tasks?page=1&per_page=200&sort_by=status&sort_order=asc', {headers:{Authorization:'Bearer '+t}});
            const j = await r.json(); const d = j.data||j;
            const dist = {};
            (d.items||[]).forEach(i => { const k = i.execution_status||'?'; dist[k]=(dist[k]||0)+1; });
            return {total: d.total, loaded: (d.items||[]).length, dist: dist};
          })()''')
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc)}


def cart_items(d):
    """购物车条目（带 token，页面内 fetch）。"""
    try:
        return d.execute_script('''
          return (async () => {
            const t = localStorage.getItem('iatp:auth:token:v1');
            const r = await fetch('/api/v1/tasks/cherry-picks/cart', {headers:{Authorization:'Bearer '+t}});
            const j = await r.json(); const d = j.data||j;
            const items = [];
            (d.groups||[]).forEach(g => (g.items||[]).forEach(i => items.push({
              resultId: i.result_id, status: i.execution_status, task: i.source_task_name,
              itemId: i.item_id})));
            return {total: d.total, invalid: d.invalid_item_ids, items: items};
          })()''')
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc)}


def failed_leaf(d):
    """找一个带「执行失败」徽章的叶行，返回 (元素, resultId)。"""
    return d.execute_script('''
      var rows = Array.from(document.querySelectorAll("[data-testid^='pick-leaf-']"))
        .filter(function(x){return x.offsetParent!==null;});
      for (var i=0;i<rows.length;i++){
        if ((rows[i].innerText||'').indexOf('执行失败')>=0){
          return {rid: (rows[i].getAttribute('data-testid')||'').replace('pick-leaf-',''),
                  idx: i, text: (rows[i].innerText||'').replace(/\\n/g,' ').slice(0,160)};
        }
      }
      return null;''')


def click_leaf_checkbox(d, rid):
    return d.execute_script('''
      var p = document.querySelector("[data-testid='pick-leaf-"+arguments[0]+"']");
      if(!p) return false;
      p.scrollIntoView({block:"center"});
      var cb = p.querySelector("[role='checkbox']");
      if(!cb) return false;
      cb.click(); return true;''', str(rid))


def add_selected_to_cart(d):
    """不加全选，只把已勾选叶加购（edge 用例：失败叶）。"""
    t0 = cart_total(d)
    if not click_text(d, '加入购物车', timeout=30):
        return {'error': 'no-add-button'}
    time.sleep(6)
    net = drain(d)
    items = [n for n in net if 'cherry-picks/cart/items' in n['url']]
    t1 = cart_total(d)
    return {'cart_before': t0, 'cart_after': t1, 'calls': items}


def wait_candidates(d, timeout=420):
    """候选就绪：出现用例卡 / 叶行 / 空态；「候选加载失败」算失败。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = d.page_source or ''
        if '候选加载失败' in body:
            return 'error'
        cards = count(d, "[aria-label^='选择 ']")
        leaves = count(d, "[data-testid^='pick-leaf-']")
        orgs = count(d, "[data-testid*='-org:']")
        if cards > 0 or leaves > 0 or orgs > 0 or '无符合条件的执行结果' in body:
            time.sleep(2.5)
            return 'ok'
        time.sleep(3)
    return 'timeout'


def stage2_hierarchy(d, mode, tag=''):
    """阶段 2：用例视图（组织→用例卡→设备→任务）、设备视图（设备→组织→用例卡→任务）。"""
    out = {}
    expand_all(d)
    out['switcher'] = texts(d)
    out['case'] = {
        'org': org_header_count(d),
        'case_card': count(d, "[aria-label^='选择 ']"),
        'device': count(d, "[data-testid*='-device:']"),
        'task': count(d, "[data-testid*='-task:']"),
        'resultType': count(d, "[data-testid*='-resultType']"),
    }
    check('阶段2 切换器无「结果类型视图」（结果类型仅 1 种）',
          '结果类型视图' not in out['switcher'], out['switcher'][:8])
    check('阶段2 用例视图：组织层 + 用例卡 + 设备层 + 任务层', all(
        out['case'][k] > 0 for k in ('org', 'case_card', 'device', 'task')), out['case'])
    check('阶段2 用例视图无 result_type 层（单一种类省略）',
          out['case']['resultType'] == 0, out['case']['resultType'])
    shot(d, '%s_stage2_case%s' % (mode, tag))

    click_text(d, '标签视图')
    time.sleep(1.5)
    expand_all(d)
    out['case_tag'] = {
        'org': org_header_count(d),
        'task': count(d, "[data-testid*='-task:']"),
        'resultType': count(d, "[data-testid*='-resultType']"),
    }
    check('阶段2 用例视图切标签：组织层仍在、任务层仍在', out['case_tag']['org'] > 0 and out['case_tag']['task'] > 0,
          out['case_tag'])
    shot(d, '%s_stage2_case_tag%s' % (mode, tag))
    click_text(d, '分组视图')
    time.sleep(1.2)

    click_text(d, '设备视图')
    time.sleep(1.8)
    expand_all(d)
    out['device'] = {
        'device': count(d, "[data-testid*='-device:']"),
        'org': count(d, "[data-testid*='-org:']"),
        'case_card': count(d, "[aria-label^='选择 ']"),
        'task': count(d, "[data-testid*='-task:']"),
        'resultType': count(d, "[data-testid*='-resultType']"),
    }
    check('阶段2 设备视图：设备 → 组织组头 → 用例卡 → 任务',
          out['device']['device'] > 0 and out['device']['org'] > 0
          and out['device']['task'] > 0, out['device'])
    check('阶段2 设备视图无 result_type 层（单一种类省略）',
          out['device']['resultType'] == 0, out['device']['resultType'])
    shot(d, '%s_stage2_device%s' % (mode, tag))
    click_text(d, '标签视图')
    time.sleep(1.5)
    expand_all(d)
    out['device_tag'] = {'org': count(d, "[data-testid*='-org:']"),
                         'task': count(d, "[data-testid*='-task:']")}
    check('阶段2 设备视图切标签：组织层仍在', out['device_tag']['org'] > 0, out['device_tag'])
    shot(d, '%s_stage2_device_tag%s' % (mode, tag))
    click_text(d, '分组视图')
    time.sleep(1.2)
    return out


def cart_scope(d):
    el = d.execute_script('''
      var ds=Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"]'))
        .filter(function(x){var r=x.getBoundingClientRect();return r.width>0&&r.height>0;});
      for(var i=ds.length-1;i>=0;i--){var t=ds[i].innerText||'';
        if(t.indexOf('购物车')>=0 && t.indexOf('是否继续')<0 && t.indexOf('移除用例「')<0) return ds[i];}
      return null;''')
    return el if el is not None else d


def alert_dialog(d):
    return d.execute_script('''
      var ds=Array.from(document.querySelectorAll('[role="alertdialog"],[role="dialog"]'))
        .filter(function(x){var r=x.getBoundingClientRect();return r.width>0&&r.height>0;});
      for(var i=ds.length-1;i>=0;i--){var t=ds[i].innerText||'';
        if(t.indexOf('是否继续')>=0 || t.indexOf('确认合并')>=0) return ds[i];}
      return null;''')


def confirm_alert(d, timeout=10):
    """确认 alertdialog 的「继续 / 继续合并」；等动画结束再点，点完等它消失。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        el = alert_dialog(d)
        if el is not None:
            time.sleep(0.8)
            for label in ('继续合并', '继续', '确定', '确认'):
                if click_text(d, label, el, timeout=2):
                    time.sleep(1.5)
                    return label
        else:
            time.sleep(0.5)
        time.sleep(0.5)
    return None


def cart_total(d):
    """后端购物车条目总数（带 token；页面内 fetch）。"""
    try:
        return d.execute_script('''
          return (async () => {
            const t = localStorage.getItem('iatp:auth:token:v1');
            const r = await fetch('/api/v1/tasks/cherry-picks/cart', {headers:{Authorization:'Bearer '+t}});
            const j = await r.json(); const d = j.data||j;
            return {total: d.total, groups: (d.groups||[]).length};
          })()''')
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc)}


def cart_hierarchy(d, mode, tag=''):
    dlg = cart_scope(d)
    expand_all(d, dlg)
    dlg = cart_scope(d)
    out = {'switcher': texts(d, dlg)}
    out['task_view'] = {
        'task_nodes': count(d, "[data-testid^='cart-branch-cart-task:']", dlg),
        'org': org_header_count(d, dlg),
        'case_card': count(d, "[aria-label^='选择 ']", dlg),
        'device': count(d, "[data-testid*='-device:']", dlg),
        'resultType': count(d, "[data-testid*='-resultType']", dlg),
        'sub_modes': [s for s in out['switcher'] if s in ('用例', '设备', '结果类型')],
    }
    check('购物车切换器：任务视图 / 用例视图 / 设备视图（无结果类型视图）',
          '任务视图' in out['switcher'] and '用例视图' in out['switcher']
          and '设备视图' in out['switcher'] and '结果类型视图' not in out['switcher'],
          out['switcher'][:8])
    check('任务视图：任务在第一级（≥2 个任务节点）', out['task_view']['task_nodes'] >= 2,
          out['task_view']['task_nodes'])
    check('任务视图用例子模式：任务 → 组织层 → 用例卡', out['task_view']['org'] > 0
          and out['task_view']['case_card'] > 0, out['task_view'])
    shot(d, '%s_cart_task_case%s' % (mode, tag))

    click_text(d, '标签视图', cart_scope(d))
    time.sleep(1.5)
    expand_all(d, cart_scope(d))
    out['task_case_tag'] = {'org': org_header_count(d, cart_scope(d))}
    check('任务视图用例子模式切标签：组织层仍在', out['task_case_tag']['org'] > 0, out['task_case_tag'])
    shot(d, '%s_cart_task_case_tag%s' % (mode, tag))
    click_text(d, '分组视图', cart_scope(d))
    time.sleep(1.2)

    click_text(d, '设备', cart_scope(d), exact=True)
    time.sleep(1.8)
    expand_all(d, cart_scope(d))
    out['task_device'] = {
        'task_nodes': count(d, "[data-testid^='cart-branch-cart-task:']", cart_scope(d)),
        'device': count(d, "[data-testid*='-device:']", cart_scope(d)),
        'org': count(d, "[data-testid*='-org:']", cart_scope(d)),
        'case_card': count(d, "[aria-label^='选择 ']", cart_scope(d)),
        'resultType': count(d, "[data-testid*='-resultType']", cart_scope(d)),
    }
    check('任务视图设备子模式：任务 → 设备 → 组织组头 → 用例卡',
          out['task_device']['device'] > 0 and out['task_device']['org'] > 0
          and out['task_device']['task_nodes'] >= 2, out['task_device'])
    shot(d, '%s_cart_task_device%s' % (mode, tag))

    click_text(d, '用例视图', cart_scope(d), exact=True)
    time.sleep(1.8)
    expand_all(d, cart_scope(d))
    out['case_view'] = {
        'org': org_header_count(d, cart_scope(d)),
        'task': count(d, "[data-testid*='-task:']", cart_scope(d)),
        'resultType': count(d, "[data-testid*='-resultType']", cart_scope(d)),
    }
    check('购物车用例视图：组织层 → 用例卡 → … → 任务层',
          out['case_view']['org'] > 0 and out['case_view']['task'] > 0, out['case_view'])
    shot(d, '%s_cart_case%s' % (mode, tag))
    click_text(d, '标签视图', cart_scope(d))
    time.sleep(1.5)
    expand_all(d, cart_scope(d))
    shot(d, '%s_cart_case_tag%s' % (mode, tag))
    click_text(d, '分组视图', cart_scope(d))
    time.sleep(1.2)

    click_text(d, '设备视图', cart_scope(d), exact=True)
    time.sleep(1.8)
    expand_all(d, cart_scope(d))
    out['device_view'] = {
        'device': count(d, "[data-testid*='-device:']", cart_scope(d)),
        'org': count(d, "[data-testid*='-org:']", cart_scope(d)),
        'task': count(d, "[data-testid*='-task:']", cart_scope(d)),
    }
    check('购物车设备视图：设备 → 组织组头 → … → 任务层',
          out['device_view']['device'] > 0 and out['device_view']['org'] > 0
          and out['device_view']['task'] > 0, out['device_view'])
    shot(d, '%s_cart_device%s' % (mode, tag))
    return out


def add_to_cart(d):
    t0 = cart_total(d)
    click_text(d, '全选当前筛选', timeout=30)
    time.sleep(1.5)
    badge = body_text(d)
    selected = None
    for line in badge.splitlines():
        if '已选' in line and '条' in line:
            selected = line.strip()
            break
    click_text(d, '加入购物车', timeout=30)
    time.sleep(6)
    net = drain(d)
    items = [n for n in net if 'cherry-picks/cart/items' in n['url']]
    t1 = cart_total(d)
    check('加入购物车：POST /cart/items 2xx', bool(items) and all(
        200 <= (n['status'] or 0) < 300 for n in items), items[:3])
    check('加入购物车后购物车 non-empty 且增加', bool(t1.get('total', 0)) and
          t1.get('total', 0) > t0.get('total', 0), {'before': t0, 'after': t1})
    return {'selected_line': selected, 'cart_items_calls': items,
            'cart_before': t0, 'cart_after': t1}


def open_cart_from_wizard(d):
    if not click_text(d, '打开购物车', timeout=30):
        for b in d.find_elements(By.CSS_SELECTOR, "[data-testid='wizard-step-cart']"):
            d.execute_script('arguments[0].click();', b)
            break
    WebDriverWait(d, 90).until(
        lambda x: len(x.find_elements(By.CSS_SELECTOR, '[data-testid^="cart-branch-"]')) > 0
        or '购物车为空' in body_text(x)
    )
    time.sleep(2.5)


def removal_checks(d, mode):
    """勾选联动 / 移除该组 / 单条 X：数量按购物车树变化核对。"""
    scope = cart_scope(d)
    out = {}
    if not click_text(d, '任务视图', scope, exact=True, timeout=15):
        check('切回任务视图', False)
    else:
        time.sleep(1.5)
    expand_all(d, cart_scope(d))
    scope = cart_scope(d)
    before_text = body_text(d, scope)
    out['before'] = [ln.strip() for ln in before_text.splitlines() if '条' in ln][:6]

    # 组头三态：点第一个任务节点的全选 checkbox
    task_nodes = scope.find_elements(By.CSS_SELECTOR, "[data-testid^='cart-branch-cart-task:']")
    out['task_nodes'] = len(task_nodes)
    if task_nodes:
        cb = task_nodes[0].find_elements(By.CSS_SELECTOR, "[role='checkbox']")
        if cb:
            d.execute_script('arguments[0].click();', cb[0])
            time.sleep(1.5)
            summary = body_text(d, cart_scope(d))
            out['after_task_toggle'] = [ln.strip() for ln in summary.splitlines() if '已选' in ln or '移除已选' in ln][:4]
            check('任务节点全选可用（出现「已选 / 移除已选」）',
                  any('已选' in x for x in out['after_task_toggle']), out['after_task_toggle'])
            d.execute_script('arguments[0].click();', cb[0])
            time.sleep(1.2)

    # 移除该组：只清该节点（确认框等动画结束再点，点完等它消失）
    scope = cart_scope(d)
    out['cart_total_before_remove'] = cart_total(d)
    groups = scope.find_elements(By.CSS_SELECTOR, "button[aria-label='移除该组']")
    out['group_remove_buttons'] = len(groups)
    if groups:
        d.execute_script('arguments[0].click();', groups[-1])
        label = confirm_alert(d)
        out['confirm_label'] = label
        time.sleep(2)
        out['cart_total_after_remove'] = cart_total(d)
        check('移除该组：出现确认框并已确认', label is not None, label)
        check('移除该组：购物车条数下降（不跨节点）',
              (out['cart_total_after_remove'].get('total') or 0)
              < (out['cart_total_before_remove'].get('total') or 0),
              {'before': out['cart_total_before_remove'], 'after': out['cart_total_after_remove']})
        check('移除该组后无残留确认框', alert_dialog(d) is None)
        shot(d, '%s_cart_after_group_remove' % mode)

    # 单条 X：只删这一条
    scope = cart_scope(d)
    xs = scope.find_elements(By.CSS_SELECTOR, "button[aria-label='移除']")
    out['single_remove_buttons'] = len(xs)
    out['cart_total_before_single'] = cart_total(d)
    if xs:
        d.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();', xs[-1])
        label = confirm_alert(d)
        time.sleep(1.5)
        out['cart_total_after_single'] = cart_total(d)
        check('单条 X：出现确认框并已确认', label is not None, label)
        check('单条 X：购物车条数 -1',
              (out['cart_total_after_single'].get('total') or 0)
              == (out['cart_total_before_single'].get('total') or 0) - 1,
              {'before': out['cart_total_before_single'], 'after': out['cart_total_after_single']})
    return out


def review_checks(d, mode):
    confirm_alert(d, timeout=3)
    scope = cart_scope(d)
    if not click_text(d, '去复核', scope, timeout=30):
        check('进入复核步骤', False)
        return {}
    time.sleep(4)
    scope = cart_scope(d)
    expand_all(d, scope)
    txt = body_text(d, cart_scope(d))
    all_buttons = texts(d)
    out = {
        'org_controls': count(d, '[aria-label="用例组织方式"]'),
        'task': count(d, "[data-testid*='-task:']"),
        'switcher': [x for x in all_buttons if '视图' in x][:10],
        'summary_lines': [ln.strip() for ln in txt.splitlines() if '结果' in ln or '来源任务' in ln][:6],
    }
    check('复核步骤：组织控件 1 份', out['org_controls'] == 1, out['org_controls'])
    check('复核步骤：任务层仍在', out['task'] > 0, out['task'])
    check('复核步骤：四视图切换器含任务视图、无结果类型视图',
          '任务视图' in all_buttons and '结果类型视图' not in all_buttons,
          out['switcher'])
    shot(d, '%s_review' % mode)
    return out


def checkout(d, mode):
    scope = cart_scope(d)
    if not click_text(d, '确认下单', scope, timeout=30):
        check('复核 → 下单步骤', False)
        return {}
    time.sleep(3)
    txt = body_text(d)
    check('进入下单步骤', '确认下单' in txt or '下单' in txt, txt[:120])
    name_input = None
    for css in ('#checkout-name', "input[aria-label='新任务名称']"):
        els = d.find_elements(By.CSS_SELECTOR, css)
        if els:
            name_input = els[0]
            break
    if name_input is not None:
        name_input.clear()
        name_input.send_keys(TASK_NAME)
    else:
        check('下单步骤：任务名称输入', False)
    shot(d, '%s_checkout_form' % mode)
    # toast 取证：下单后立即跳详情页，toast 存续很短——点击前挂 MutationObserver 收新增节点文本
    d.execute_script('''
      window.__int1499Toasts = [];
      window.__int1499Mo = new MutationObserver(function(muts){
        muts.forEach(function(m){ (m.addedNodes||[]).forEach(function(n){
          if(n.nodeType===1){
            var t=(n.textContent||'').trim();
            if(t) window.__int1499Toasts.push(t.slice(0,200));
            (n.querySelectorAll?Array.from(n.querySelectorAll('[data-sonner-toast]')):[]).forEach(function(x){
              window.__int1499Toasts.push(((x.textContent||'').trim()||'').slice(0,200));});
          }
        });});
      });
      window.__int1499Mo.observe(document.body,{childList:true,subtree:true});
      return true;''')
    click_text(d, '确认下单', timeout=20)
    time.sleep(2.5)
    # 配置不一致确认
    if click_text(d, '继续合并', timeout=4):
        print('CONFIRM_MERGE')
        time.sleep(1)
    deadline = time.time() + 90
    task_id = None
    while time.time() < deadline:
        url = d.current_url or ''
        if '/tasks/' in url:
            tail = url.split('/tasks/')[-1].split('?')[0]
            if tail.isdigit():
                task_id = int(tail)
                break
        time.sleep(2)
    time.sleep(2)
    toast = body_text(d)
    captured = d.execute_script('return (window.__int1499Toasts||[]).slice(-40);') or []
    net = drain(d)
    calls = [n for n in net if 'cherry-picks' in n['url']]
    hit = [t for t in captured if '挑选合并任务已创建' in t]
    out = {'task_id': task_id, 'url': d.current_url, 'calls': calls,
           'toast_created': bool(hit), 'toasts': captured[:12],
           'toast_visible_text': '挑选合并任务已创建' in toast}
    check('下单 merge：跳转 /tasks/{id}', task_id is not None, out['url'])
    check('下单 merge：POST /cart/checkout 2xx',
          any('checkout' in c['url'] and 200 <= (c['status'] or 0) < 300 for c in calls), calls[-5:])
    check('下单 merge：toast「挑选合并任务已创建」', out['toast_created'],
          {'hit': hit[:2], 'visible': out['toast_visible_text'], 'captured': captured[:6]})
    shot(d, '%s_checkout_result' % mode)
    return out


def settled_tabs(d, timeout=60):
    """页签计数是异步加载的（换键先显示 0）：等「挑选合并」计数落到正数再取快照。"""
    deadline = time.time() + timeout
    tabs = {}
    while time.time() < deadline:
        tabs = tab_counts(d)
        if _tab_num(tabs) > 0:
            return tabs
        time.sleep(2)
    return tabs


def task_list_checks(d, mode, task_id, before_tabs):
    d.get(BASE + '/tasks?tab=cherry-picks')
    time.sleep(6)
    after_tabs = settled_tabs(d)
    txt = body_text(d)
    rows = [ln.strip() for ln in txt.splitlines() if '结果挑选' in ln or TASK_NAME in ln][:8]
    out = {'tabs_before': before_tabs, 'tabs_after': after_tabs, 'rows': rows}
    check('挑选合并页签计数 +1', _tab_num(after_tabs) == _tab_num(before_tabs) + 1,
          {'before': before_tabs, 'after': after_tabs})
    check('挑选合并页签出现本 run 新容器行', TASK_NAME in txt, rows[:4])
    shot(d, '%s_task_list_cherry_picks' % mode)

    d.get(BASE + '/tasks?tab=daily')
    time.sleep(6)
    dtxt = body_text(d)
    row = d.execute_script('''
      var needle=arguments[0];
      var cands=Array.from(document.querySelectorAll('tr,[role="row"]'));
      var hit=cands.filter(function(r){return (r.innerText||'').indexOf(needle)>=0;});
      if(!hit.length){
        hit=Array.from(document.querySelectorAll('div')).filter(function(r){
          var t=r.innerText||'';
          return t.indexOf(needle)>=0 && t.indexOf('结果挑选')>=0 && t.length<600;});
      }
      return hit.length ? (hit[0].innerText||'').split('\\n').join(' | ').slice(0,300) : null;''', TASK_NAME)
    out['daily_row'] = row
    out['daily_has_marker'] = bool(row) and ('挑选合并' in row) and ('结果挑选' in row)
    out['daily_lines'] = [ln.strip() for ln in dtxt.splitlines()
                          if '挑选合并' in ln or TASK_NAME in ln][:8]
    check('日常任务页签：新容器行带「挑选合并」标识', out['daily_has_marker'], row or out['daily_lines'][:4])
    shot(d, '%s_task_list_daily' % mode)
    return out


def _tab_num(tabs):
    for k in tabs:
        if '挑选合并' in k:
            digits = ''.join(ch for ch in k if ch.isdigit())
            if digits:
                return int(digits)
    return 0


def cart_clear():
    req = urllib.request.Request(API + '/api/v1/tasks/cherry-picks/cart/items', method='DELETE')
    if TOKEN['v']:
        req.add_header('Authorization', 'Bearer ' + TOKEN['v'])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b'{}')
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc)}


def api(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(API + path, method=method, data=data)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    if TOKEN['v']:
        req.add_header('Authorization', 'Bearer ' + TOKEN['v'])
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read() or b'{}')
    except Exception as exc:  # noqa: BLE001
        return None, {'error': str(exc)}


def cleanup_task(task_id):
    """收尾：软删 + purge 本 run 下单创建的容器任务。"""
    if not task_id:
        return {}
    out = {}
    out['delete'] = api('DELETE', '/api/v1/tasks/%d' % task_id)
    out['purge'] = api('DELETE', '/api/v1/tasks/%d/purge' % task_id)
    return out


def arg_value(name, default=''):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def load_candidates(d, tries=3):
    """阶段 2 候选加载；已知 candidates 并发 60s DEADLINE_EXCEEDED 用「重试」兜。"""
    w = 'timeout'
    for _ in range(tries):
        w = wait_candidates(d)
        if w == 'ok':
            return w
        if not click_text(d, '重试', timeout=12):
            break
        time.sleep(3)
    return w


def phase_edge(d, res):
    """边界 A：单任务时任务层省略；边界 B：失败任务 312 的失败叶行可加购（不得被前端过滤）。"""
    # ---- A：单任务 → 任务层省略（311，failed 任务）
    open_pick(d)
    chosen = select_task_ids(d, [311])
    check('边界：能勾选失败任务 311', chosen == [311], chosen)
    click_text(d, '下一步', timeout=30)
    wait = load_candidates(d)
    check('边界：311 单任务候选加载成功', wait == 'ok', wait)
    expand_all(d)
    out = {
        'task_layer': count(d, "[data-testid*='-task:']"),
        'leaves': count(d, "[data-testid^='pick-leaf-']"),
    }
    res['edge_single'] = out
    check('边界：选 1 个任务时阶段 2 任务层省略', out['task_layer'] == 0, out['task_layer'])
    check('边界：311 候选叶渲染（未被前端过滤）', out['leaves'] > 0, out['leaves'])
    shot(d, 'p20_edge_single_task_light')

    # ---- B：312（failed，含 7 条失败结果）→ 展开全树 → 失败叶加购
    open_pick(d)
    chosen = select_task_ids(d, [312])
    check('边界：能勾选失败任务 312', chosen == [312], chosen)
    click_text(d, '下一步', timeout=30)
    wait = load_candidates(d)
    check('边界：312 单任务候选加载成功', wait == 'ok', wait)
    expand_all(d, rounds=80, width=20)
    leaves = d.execute_script(
        'return Array.from(document.querySelectorAll("[data-testid^=\'pick-leaf-\']"))'
        '.filter(function(x){return x.offsetParent!==null;}).length;')
    failed_n = d.execute_script(
        'return Array.from(document.querySelectorAll("[data-testid^=\'pick-leaf-\']"))'
        '.filter(function(x){return x.offsetParent!==null && (x.innerText||"").indexOf("执行失败")>=0;}).length;')
    res['edge_failed_task'] = {'leaves': leaves, 'failed_leaves': failed_n}
    check('边界：312 全展开候选叶渲染', leaves >= 50, leaves)
    check('边界：312 失败叶行渲染且标「执行失败」', failed_n > 0, failed_n)
    shot(d, 'p20b_edge_failed_leaves_light')

    leaf = failed_leaf(d)
    res['edge_failed_leaf'] = leaf
    check('边界：定位到一条失败叶行', bool(leaf), leaf)
    if leaf:
        before = cart_items(d)
        click_leaf_checkbox(d, leaf['rid'])
        time.sleep(1.2)
        shot(d, 'p21_edge_failed_leaf_selected_light')
        add = add_selected_to_cart(d)
        res['edge_add'] = add
        check('边界：失败叶加购 POST /cart/items 2xx',
              bool(add.get('calls')) and all(200 <= (n['status'] or 0) < 300 for n in add['calls']),
              add.get('calls'))
        check('边界：加购后购物车条数 +1',
              (add.get('cart_after', {}).get('total') or 0) == (add.get('cart_before', {}).get('total') or 0) + 1,
              {'before': add.get('cart_before'), 'after': add.get('cart_after')})
        after = cart_items(d)
        hit = [i for i in (after.get('items') or []) if str(i.get('resultId')) == str(leaf['rid'])]
        res['edge_cart_item'] = {'before_total': before.get('total'), 'after_total': after.get('total'),
                                 'hit': hit[:2]}
        check('边界：失败叶进入购物车且状态=failed',
              bool(hit) and all((i.get('status') or '') == 'failed' for i in hit), hit[:2])


def phase_light(d, res):
    health('start')
    d.get(BASE + '/tasks?tab=cherry-picks')
    time.sleep(6)
    res['tabs_before'] = tab_counts(d)
    shot(d, 'p1_task_list_before')

    open_pick(d)
    rows = pick_task_checkboxes(d)
    res['stage1_rows'] = len(rows)
    check('阶段 1 任务清单全量（≥100，不是旧的 2 条）', len(rows) >= 100, len(rows))
    net = drain(d)
    pick_calls = [n for n in net if 'pickable-tasks' in n['url']]
    cand_calls = [n for n in net if 'cherry-picks/candidates' in n['url']]
    res['stage1_network'] = {'pickable': pick_calls[-3:], 'candidates': cand_calls}
    check('阶段 1 只发 pickable-tasks，不发 candidates',
          bool(pick_calls) and not cand_calls, {'pick': pick_calls[-1:], 'cand': len(cand_calls)})
    detail = stage1_detail(d)
    by_id = {r['id']: r['text'] for r in detail}
    be = pickable_backend(d)
    res['stage1_backend'] = be
    res['stage1_failed_rows'] = {k: by_id.get(k) for k in ('311', '312')}
    check('阶段 1 条数与后端终态任务集合一致（服务端 total）',
          be.get('total') == len(detail), {'backend': be.get('total'), 'rendered': len(detail)})
    check('阶段 1 任务集合含执行失败/已停止（后端 failed/stopped 均 >0）',
          (be.get('dist') or {}).get('failed', 0) > 0 and (be.get('dist') or {}).get('stopped', 0) > 0,
          be.get('dist'))
    check('阶段 1 失败任务 311/312 在清单内且行内标「执行失败」',
          '311' in by_id and '312' in by_id and '执行失败' in by_id.get('311', '')
          and '执行失败' in by_id.get('312', ''), res['stage1_failed_rows'])
    shot(d, 'p2_stage1_light')

    select_tasks(d)
    click_text(d, '下一步', timeout=30)
    wait = load_candidates(d)
    check('阶段 2 候选加载成功（无「候选加载失败」）', wait == 'ok', wait)
    res['stage2_wait'] = wait
    res['stage2_leaves'] = count(d, "[data-testid^='pick-leaf-']")
    shot(d, 'p3_stage2_loaded_light')
    res['stage2_light'] = stage2_hierarchy(d, 'p4', '_light')

    res['add_to_cart'] = add_to_cart(d)
    open_cart_from_wizard(d)
    res['cart_light'] = cart_hierarchy(d, 'p5', '_light')
    res['removal'] = removal_checks(d, 'p6')
    res['review_light'] = review_checks(d, 'p7')


def phase_dark(d, res):
    set_theme(d, 'dark')
    open_pick(d)
    select_tasks(d)
    click_text(d, '下一步', timeout=30)
    wait = load_candidates(d)
    check('深色：阶段 2 候选加载成功', wait == 'ok', wait)
    res['stage2_dark'] = stage2_hierarchy(d, 'p8', '_dark')
    res['add_to_cart_dark'] = add_to_cart(d)
    open_cart_from_wizard(d)
    res['cart_dark'] = cart_hierarchy(d, 'p9', '_dark')
    res['review_dark'] = review_checks(d, 'p10')


def phase_checkout(d, res):
    set_theme(d, 'light')
    d.get(BASE + '/tasks?tab=cherry-picks')
    time.sleep(6)
    res['tabs_before'] = settled_tabs(d)
    open_pick(d)
    select_tasks(d)
    click_text(d, '下一步', timeout=30)
    wait = load_candidates(d)
    check('下单前：阶段 2 候选加载成功', wait == 'ok', wait)
    open_cart_from_wizard(d)
    res['cart_total_before_checkout'] = cart_total(d)
    check('下单前购物车非空', bool(res['cart_total_before_checkout'].get('total')),
          res['cart_total_before_checkout'])
    res['review_before_checkout'] = review_checks(d, 'p11')
    res['checkout'] = checkout(d, 'p12')
    tid = res['checkout'].get('task_id')
    if tid:
        res['task_list'] = task_list_checks(d, 'p13', tid, res.get('tabs_before') or {})
    CREATED['task_id'] = tid
    health('delivery')


def main():
    phase = arg_value('--phase', 'light')
    keep_cart = '--keep-cart' in sys.argv
    d = driver()
    res = RESULT['data']
    try:
        d.get(BASE + '/')
        login(d)
        res['phase'] = phase
        if phase == 'light':
            set_theme(d, 'light')
            phase_light(d, res)
        elif phase == 'dark':
            set_theme(d, 'dark')
            phase_dark(d, res)
        elif phase == 'edge':
            set_theme(d, 'light')
            phase_edge(d, res)
        elif phase == 'checkout':
            phase_checkout(d, res)
        else:
            raise RuntimeError('unknown phase %s' % phase)
    finally:
        try:
            d.quit()
        except Exception:  # noqa: BLE001
            pass
        # 收尾无论成败都执行：清购物车 + 软删/purge 本 run 下单容器
        keep_task = '--keep-task' in sys.argv
        try:
            res['cleanup'] = {'cart': None if keep_cart else cart_clear(),
                              'task': None if keep_task else
                              (cleanup_task(CREATED['task_id']) if CREATED['task_id'] else None)}
        except Exception as exc:  # noqa: BLE001
            res['cleanup'] = {'error': str(exc)}
    out = os.path.join(ART, 'result.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'checks': CHECKS, 'data': res, 'health': RESULT['health']}, f, ensure_ascii=False, indent=2)
    print('SUMMARY %d/%d' % (len([c for c in CHECKS if c['ok']]), len(CHECKS)))
    if FAILS:
        print('FAILED:', json.dumps(FAILS, ensure_ascii=False))
        sys.exit(1)
    print('ALL_OK')


if __name__ == '__main__':
    main()
