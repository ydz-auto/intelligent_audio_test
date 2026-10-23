# -*- coding: utf-8 -*-
"""INT-1585 验收实测（测试工程师）：useSystemOptions 按 option:read 关 query。

被测对象与容器：
  NEW_GATE  http://127.0.0.1:15242  本卡交付 dist（含 option:read 门禁）+ nginx 对
                                    /api/option/ 直接 403（模拟 AUTH_MODE=on 的真实后端行为）
  NEW_LIVE  http://127.0.0.1:15243  本卡交付 dist + 标准反代（admin 真实读写链路）
  OLD_GATE  http://127.0.0.1:15244  修复前镜像 iat-react-frontend:latest + 同样的 403 规则（A/B 对照）

环境说明：docker 栈 gateway 当前 AUTH_MODE=off（printenv 确认），AuthMiddleware 对每个请求
注入 dev_user permissions=['*']，真实账号登录/注入 token 都会被 /auth/me 覆盖，/api/option/
也不会 403。故 guest / 半权限的会话用页面级 fetch 桩按「DB 里真实角色的权限码」注入
/auth/me（token 落 localStorage），/api/option/ 的 403 由旁路 nginx 真实返回——是真实网络
响应与真实 console SEVERE，非页内合成。admin 段直接走真实离栈 dev_user('*')。

用法：
  python tests/ui/verify_int1585_tester.py            # 全量
  set ONLY=guest,ab & python tests/ui/verify_int1585_tester.py
输出：tests/ui/artifacts/int1585_verify/verify_int1585_tester.json + png
"""
import atexit
import json
import os
import time
import traceback

os.environ.setdefault('SE_OFFLINE', 'true')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

NEW_GATE = os.environ.get('NEW_GATE', 'http://127.0.0.1:15242')
NEW_LIVE = os.environ.get('NEW_LIVE', 'http://127.0.0.1:15243')
OLD_GATE = os.environ.get('OLD_GATE', 'http://127.0.0.1:15244')

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1585_verify')
os.makedirs(ART, exist_ok=True)
OUT_PATH = os.path.join(ART, os.environ.get('OUT_NAME', 'verify_int1585_tester.json'))

# 真实 guest 角色（role_id=5）权限码——来自主库 role_permissions join permissions
GUEST_PERMS = [
    'auth:callback', 'auth:login', 'auth:logout', 'auth:me', 'auth:refresh',
    'home:read', 'report:compare', 'report:read', 'sse:read', 'status:read',
]
# 半权限：只有 user:read 无 option:read（可过系统设置路由守卫）
HALF_PERMS = ['user:read']

GUEST_ME = {
    'user_id': 373, 'username': '接线测试_guest', 'role_id': 5,
    'permissions': GUEST_PERMS,
}
HALF_ME = {
    'user_id': -1, 'username': '接线测试_INT1585_半权限(模拟会话)', 'role_id': -1,
    'permissions': HALF_PERMS,
}

PAGES = ['/dashboard', '/tasks', '/reports', '/testcases']

BOOTSTRAP = r"""
(function () {
  const TOKEN_KEY = 'iatp:auth:token:v1';
  const role = localStorage.getItem('int1585:role') || '';
  let me = null;
  try { me = JSON.parse(localStorage.getItem('int1585:me') || 'null'); } catch (e) { me = null; }
  if (role === 'guest' || role === 'half') {
    localStorage.setItem(TOKEN_KEY, 'int1585-e2e-token');
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
  window.__apiLog = [];
  const orig = window.fetch;
  window.fetch = async function (input, init) {
    let url = typeof input === 'string' ? input : ((input && input.url) || '');
    let path = url;
    try { path = new URL(url, location.origin).pathname; } catch (e) {}
    const isMe = path.indexOf('/api/v1/auth/me') === 0;
    const isMode = path.indexOf('/api/v1/auth/mode') === 0;
    if ((role === 'guest' || role === 'half') && isMe) {
      window.__apiLog.push({ url: url, status: 200, synthetic: 'auth/me' });
      return new Response(JSON.stringify(me || {}), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      });
    }
    if (role === 'anon' && isMode) {
      window.__apiLog.push({ url: url, status: 200, synthetic: 'auth/mode=on' });
      return new Response(JSON.stringify({ auth_mode: 'on' }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      });
    }
    let res;
    try {
      res = await orig.apply(this, arguments);
    } catch (e) {
      window.__apiLog.push({ url: url, status: -1 });
      throw e;
    }
    window.__apiLog.push({ url: url, status: res.status });
    return res;
  };
})();
"""

OUT = {'new_gate': NEW_GATE, 'new_live': NEW_LIVE, 'old_gate': OLD_GATE,
       'guest_perms': GUEST_PERMS, 'half_perms': HALF_PERMS,
       'env_note': 'gateway AUTH_MODE=off；guest/半权限会话用页内 fetch 桩按真实角色权限注入 /auth/me，'
                   '/api/option/ 403 由旁路 nginx 真实返回'}


def save():
    try:
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


def section(name, fn):
    t0 = time.time()
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_ok'] = False
        OUT[name + '_error'] = traceback.format_exc()[-3000:]
        print('SECTION FAILED', name, OUT[name + '_error'])
    OUT[name + '_dur_s'] = round(time.time() - t0, 1)
    save()


def make_driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    path = ''
    try:
        import winreg
        major = 0
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
        if major and os.path.isdir(cache):
            for ver in os.listdir(cache):
                exe = os.path.join(cache, ver, 'chromedriver.exe')
                if os.path.isfile(exe) and ver.split('.')[0] == str(major):
                    path = exe
    except Exception:
        pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(180)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': BOOTSTRAP})
    return d


def wait_ready(drv, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: d.execute_script('return document.readyState') == 'complete')


def js_click(drv, el):
    drv.execute_script('arguments[0].click();', el)


def set_role(drv, base, role, me=None):
    """先在源上写会话配置，下一次导航由 BOOTSTRAP 注入 token / 权限。"""
    drv.get(base + '/login')
    wait_ready(drv)
    time.sleep(1.5)
    drv.execute_script(
        "localStorage.setItem('int1585:role', arguments[0]);"
        "localStorage.setItem('int1585:me', arguments[1]);",
        role, json.dumps(me or {}, ensure_ascii=False))


def console_severe(drv):
    out = []
    try:
        for e in drv.get_log('browser'):
            if (e.get('level') or '').upper() == 'SEVERE':
                out.append(e.get('message', ''))
    except Exception:
        pass
    return out


def net_events(drv):
    rows = []
    try:
        raw = drv.get_log('performance')
    except Exception:
        return rows
    reqs = {}
    for entry in raw:
        try:
            msg = json.loads(entry['message'])
        except Exception:
            continue
        m = msg.get('message') or {}
        method = m.get('method')
        params = m.get('params') or {}
        if method == 'Network.requestWillBeSent':
            reqs[params.get('requestId')] = {
                'url': params.get('request', {}).get('url', ''),
                'method': params.get('request', {}).get('method', ''),
            }
        elif method == 'Network.responseReceived':
            r = reqs.get(params.get('requestId'))
            if r:
                rows.append((r['method'], r['url'], params.get('response', {}).get('status')))
    return rows


def clear_logs(drv):
    for kind in ('browser', 'performance'):
        try:
            drv.get_log(kind)
        except Exception:
            pass


def collect(drv, label, wait=7):
    time.sleep(wait)
    sev = console_severe(drv)
    net = net_events(drv)
    opt = [n for n in net if '/api/option' in n[1]]
    bad = [n for n in net if n[2] in (401, 403)]
    try:
        page_log = drv.execute_script('return window.__apiLog || []')
    except Exception:
        page_log = []
    rec = {
        'severe': sev,
        'severe_count': len(sev),
        'option_requests': len(opt),
        'option_status': [n[2] for n in opt],
        'bad_auth_responses': [{'url': n[1], 'status': n[2]} for n in bad],
        'bad_auth_count': len(bad),
        'page_fetch_me': [x for x in page_log if 'auth/me' in (x.get('url') or '')],
        'pathname': drv.execute_script('return location.pathname'),
        'net_total': len(net),
    }
    OUT.setdefault('samples', {})[label] = rec
    print(label, '| SEVERE', rec['severe_count'], '| option', rec['option_requests'],
          rec['option_status'], '| 401/403', rec['bad_auth_count'], '| path', rec['pathname'])
    if sev:
        print('    severe:', [s[:160] for s in sev[:4]])
    save()
    return rec


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    OUT.setdefault('shots', []).append(name + '.png')
    print('SHOT', p)


def reload(drv, base, path, label, wait=7):
    clear_logs(drv)
    drv.get(base + path)
    wait_ready(drv)
    return collect(drv, label, wait=wait)


def page_fetch(drv, url, opts=None):
    return drv.execute_async_script(
        """
        const url = arguments[0], opts = arguments[1] || {};
        const done = arguments[arguments.length - 1];
        fetch(url, opts).then(r => r.text().then(t => done({status: r.status, body: t.slice(0, 6000)})))
          .catch(e => done({status: -1, body: String(e)}));
        """, url, opts or {})


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def open_notice_tab(drv):
    btn = WebDriverWait(drv, 20).until(
        lambda x: x.find_element(By.CSS_SELECTOR, "button[aria-label='通知']"))
    js_click(drv, btn)
    time.sleep(1.5)
    try:
        tab = drv.find_element(By.XPATH, "//*[@role='tab'][contains(normalize-space(.), '公告')]")
        js_click(drv, tab)
        time.sleep(1.5)
    except Exception:
        pass
    return body_text(drv)


# ===== 1. guest：四页 ×2 整页刷新，0 SEVERE / 0 option 请求 =====
def guest_section():
    d = make_driver()
    try:
        set_role(d, NEW_GATE, 'guest', GUEST_ME)
        for path in PAGES:
            for i in (1, 2):
                reload(d, NEW_GATE, path, 'guest%s_load%d' % (path.replace('/', '_'), i))

        # 站头通知中心「公告」页签：无 option:read → 空态、不报错
        clear_logs(d)
        d.get(NEW_GATE + '/dashboard')
        wait_ready(d)
        time.sleep(4)
        try:
            pop = open_notice_tab(d)
            OUT['guest_notice_popover_opens'] = True
            OUT['guest_notice_popover_tail'] = pop[-500:]
        except Exception as e:
            OUT['guest_notice_popover_opens'] = str(e)[:200]
        collect(d, 'guest_notice_popover', wait=1)

        # 深浅色两帧（同源 reload，主题才生效）
        drv_set_theme(d, 'light')
        clear_logs(d)
        d.get(NEW_GATE + '/dashboard')
        wait_ready(d)
        time.sleep(5)
        OUT['guest_light_html_class'] = d.execute_script(
            "return document.documentElement.className")
        OUT['guest_light_body_bg'] = d.execute_script(
            "return getComputedStyle(document.body).backgroundColor")
        shot(d, 'guest_dashboard_light')
        collect(d, 'guest_dashboard_light', wait=1)

        drv_set_theme(d, 'dark')
        clear_logs(d)
        d.get(NEW_GATE + '/dashboard')
        wait_ready(d)
        time.sleep(5)
        OUT['guest_dark_html_class'] = d.execute_script(
            "return document.documentElement.className")
        OUT['guest_dark_body_bg'] = d.execute_script(
            "return getComputedStyle(document.body).backgroundColor")
        shot(d, 'guest_dashboard_dark')
        collect(d, 'guest_dashboard_dark', wait=1)
    finally:
        d.quit()


def drv_set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


# ===== 2. 匿名公开页：无新增 401/403 =====
def anon_section():
    d = make_driver()
    try:
        set_role(d, NEW_GATE, 'anon', {})
        reload(d, NEW_GATE, '/login', 'anon_login_1', wait=4)
        rec = reload(d, NEW_GATE, '/login', 'anon_login_2', wait=4)
        OUT['anon_clean'] = (rec['severe_count'] == 0 and rec['bad_auth_count'] == 0
                             and rec['option_requests'] == 0)
        shot(d, 'anon_login_light')
    finally:
        d.quit()


# ===== 3. admin（off 模式 dev_user '*'，等价 admin 权限集）：功能不回归 =====
def parse_notice(payload):
    try:
        p = json.loads(payload)
        kv = p.get('data') if isinstance(p, dict) and 'data' in p else p
        return ((kv or {}).get('site.notice') or '').strip()
    except Exception:
        return None


def set_textarea(drv, el, value):
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)
    time.sleep(0.5)


def save_button(drv):
    WebDriverWait(drv, 20).until(lambda d: d.execute_script(
        "return !![...document.querySelectorAll('button')].find(b => b.textContent.trim().startsWith('保存'))"))
    return drv.execute_script(
        "return [...document.querySelectorAll('button')].find(b => b.textContent.trim().startsWith('保存'))")


def admin_section():
    d = make_driver()
    try:
        set_role(d, NEW_LIVE, 'admin', {})
        rec = reload(d, NEW_LIVE, '/dashboard', 'admin_dashboard')
        OUT['admin_dashboard_option_ok'] = (rec['option_requests'] >= 1
                                            and all(s == 200 for s in rec['option_status']))
        OUT['admin_dashboard_severe'] = rec['severe_count']
        shot(d, 'admin_dashboard_light')

        rec2 = reload(d, NEW_LIVE, '/system-settings/site/info', 'admin_site_info')
        txt = body_text(d)
        OUT['admin_site_info_retry_error_state'] = '设置加载失败' in txt
        OUT['admin_site_info_no_permission_state'] = '无权限查看系统设置' in txt
        OUT['admin_site_info_option_status'] = rec2['option_status']
        OUT['admin_site_info_renders_fields'] = ('站点名称' in txt) or ('网站名称' in txt)
        OUT['admin_site_info_path'] = rec2['pathname']
        shot(d, 'admin_site_info_light')

        # 公告：改 → PUT 200 → 站头同步 → 回读一致 → 还原
        marker = '接线测试_INT1585 验收公告同步'
        clear_logs(d)
        d.get(NEW_LIVE + '/system-settings/site/notice')
        wait_ready(d)
        time.sleep(3)
        ta = WebDriverWait(d, 20).until(lambda x: x.find_element(By.ID, 'site-notice'))
        original = ta.get_attribute('value') or ''
        OUT['admin_notice_original'] = original
        try:
            set_textarea(d, ta, marker)
            time.sleep(1)
            js_click(d, save_button(d))
            WebDriverWait(d, 30).until(lambda x: marker in body_text(x))
            time.sleep(3)
            puts = [n for n in net_events(d) if n[0] == 'PUT' and '/api/option' in n[1]]
            OUT['admin_notice_put'] = [{'status': s, 'url': u} for _, u, s in puts]
            OUT['admin_notice_put_ok'] = bool(puts) and all(s == 200 for _, _, s in puts)
            OUT['admin_notice_readback'] = parse_notice(
                page_fetch(d, '/api/option/')['body'])
            OUT['admin_notice_readback_equal'] = (OUT['admin_notice_readback'] == marker)
            rec3 = reload(d, NEW_LIVE, '/dashboard', 'admin_dashboard_after_notice', wait=5)
            try:
                pop = open_notice_tab(d)
                OUT['admin_notice_header_synced'] = marker in pop
                OUT['admin_notice_header_sample'] = pop[-300:]
            except Exception as e:
                OUT['admin_notice_header_synced'] = str(e)[:200]
            OUT['admin_notice_after_severe'] = rec3['severe_count']
            shot(d, 'admin_notice_synced')
        finally:
            d.get(NEW_LIVE + '/system-settings/site/notice')
            wait_ready(d)
            time.sleep(3)
            try:
                ta2 = WebDriverWait(d, 20).until(lambda x: x.find_element(By.ID, 'site-notice'))
                set_textarea(d, ta2, original or '')
                time.sleep(1)
                js_click(d, save_button(d))
                time.sleep(4)
                restored = parse_notice(page_fetch(d, '/api/option/')['body'])
                OUT['admin_notice_restored'] = (restored or '') == (original or '').strip()
                OUT['admin_notice_restored_value'] = restored
            except Exception as e:
                OUT['admin_notice_restore_error'] = str(e)[:400]
    finally:
        d.quit()


# ===== 4. 半权限（user:read，无 option:read）：不得出现可重试「设置加载失败」 =====
def half_section():
    d = make_driver()
    try:
        set_role(d, NEW_GATE, 'half', HALF_ME)
        rec = reload(d, NEW_GATE, '/system-settings/iam/users', 'half_user_list', wait=8)
        txt = body_text(d)
        OUT['half_pathname'] = rec['pathname']
        OUT['half_retry_error_state'] = '设置加载失败' in txt
        OUT['half_no_permission_state'] = '无权限查看系统设置' in txt
        OUT['half_option_requests'] = rec['option_requests']
        OUT['half_severe_count'] = rec['severe_count']
        OUT['half_bad_auth'] = rec['bad_auth_responses']
        OUT['half_body_sample'] = txt[-600:]
        OVERFLOW = 'half_user_list_light.png'
        shot(d, 'half_user_list_light')
    finally:
        d.quit()


# ===== 5. A/B 对照：修复前镜像同场景应复现 2 条 403 SEVERE =====
def ab_section():
    d = make_driver()
    try:
        set_role(d, OLD_GATE, 'guest', GUEST_ME)
        for path in ('/dashboard', '/reports'):
            for i in (1, 2):
                reload(d, OLD_GATE, path, 'old%s_load%d' % (path.replace('/', '_'), i))
        shot(d, 'old_dashboard_403')
    finally:
        d.quit()


def main():
    only = os.environ.get('ONLY', '')
    jobs = [('guest', guest_section), ('anon', anon_section), ('admin', admin_section),
            ('half', half_section), ('ab', ab_section)]
    for name, fn in jobs:
        if only and name not in only.split(','):
            continue
        print('=== section', name)
        section(name, fn)
    save()
    print('OUT', OUT_PATH)


if __name__ == '__main__':
    main()
