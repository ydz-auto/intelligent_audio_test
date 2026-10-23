# -*- coding: utf-8 -*-
"""INT-1585 实测：useSystemOptions 按 option:read 关 query（guest 每页 2 条 /api/option/ 403 消失）。

环境：docker 真实栈，旁路容器 http://127.0.0.1:15245（本卡 dist + 与 15173 一致的 nginx conf，
/api 代理 intelligent-audio-test_default 网络的 api_gateway:5000，真实库 intelligent_audio_test）。

覆盖：
1. guest（接线测试_guest，user 373，10 条权限无 option:read）登录：
   /dashboard /tasks /reports /testcases 各整页刷新 2 次 → console 0 SEVERE，
   Network(performance log) 中 /api/option/ 请求 0 条；dashboard 深浅色截图。
2. 匿名（清 localStorage）公开页 /login → console 无新增 401/403，且 /api/option/ 0 条。
3. admin（接线测试_admin）对照：/dashboard 与 /system-settings/site/info 正常读 /api/option/ 200，
   站头公告渲染、无「设置加载失败」；截图 1 帧。
4. 半权限账号（本脚本自建，仅 user:read 无 option:read）：/system-settings/user/list
   不出现可重试「设置加载失败」态，console 无 403 SEVERE。

用法：set REACT_BASE=http://127.0.0.1:15245 & python tests/ui/verify_int1585_option_gate.py
输出：tests/ui/artifacts/int1585/verify_int1585.json
"""
import atexit
import json
import os
import sys
import time
import traceback

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15245')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1585')
os.makedirs(ART, exist_ok=True)
OUT_PATH = os.path.join(ART, os.environ.get('OUT_NAME', 'verify_int1585.json'))

GUEST = ('接线测试_guest', 'JieXianTest@2026')
ADMIN = ('接线测试_admin', 'JieXianTest@2026')
HALF = (os.environ.get('HALF_USER', ''), 'JieXianTest@2026')

PAGES = ['/dashboard', '/tasks', '/reports', '/testcases']

FETCH_PATCH = r"""
window.__apiLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  let res;
  try { res = await __origFetch.apply(this, arguments); }
  catch (e) { window.__apiLog.push({url: url, status: -1, t: Date.now()}); throw e; }
  window.__apiLog.push({url: url, status: res.status, t: Date.now()});
  return res;
};
"""

OUT = {'base': BASE}


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
        OUT[name + '_error'] = traceback.format_exc()[-2000:]
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
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    path = ''
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
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
    d.set_page_load_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def js_click(drv, el):
    drv.execute_script('arguments[0].click();', el)


def login(drv, creds, attempts=3):
    last = None
    for _ in range(attempts):
        drv.get(BASE + '/login')
        WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        if '/login' not in drv.current_url:
            return drv.current_url
        try:
            u = WebDriverWait(drv, 15).until(lambda d: d.find_element(By.ID, 'username'))
        except Exception:
            if '/login' not in drv.current_url:
                return drv.current_url
            last = 'no form'
            continue
        u.clear()
        u.send_keys(creds[0])
        p = drv.find_element(By.ID, 'password')
        p.clear()
        p.send_keys(creds[1])
        btn = drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]")
        js_click(drv, btn)
        try:
            WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
            time.sleep(2)
            return drv.current_url
        except Exception:
            last = 'still on login'
            time.sleep(2)
    raise RuntimeError('login failed: %s' % last)


def console_severe(drv):
    """读 browser 日志里的 SEVERE（不区分来源），返回 [message...]"""
    out = []
    try:
        for e in drv.get_log('browser'):
            if (e.get('level') or '').upper() == 'SEVERE':
                out.append(e.get('message', ''))
    except Exception:
        pass
    return out


def net_events(drv):
    """解析 performance log → [(method, url, status)]（memory：双层解包 msg['message']）"""
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
            reqs[params.get('requestId')] = {'url': params.get('request', {}).get('url', ''),
                                             'method': params.get('request', {}).get('method', '')}
        elif method == 'Network.responseReceived':
            r = reqs.get(params.get('requestId'))
            if r:
                rows.append((r['method'], r['url'], params.get('response', {}).get('status')))
    return rows


def clear_logs(drv):
    try:
        drv.get_log('browser')
        drv.get_log('performance')
    except Exception:
        pass


def settle_and_collect(drv, name):
    time.sleep(6)
    sev = console_severe(drv)
    net = net_events(drv)
    opt = [n for n in net if '/api/option' in n[1]]
    forbidden = [n for n in net if n[2] in (401, 403)]
    rec = {'severe': sev, 'severe_count': len(sev),
           'option_requests': len(opt), 'option_status': [n[2] for n in opt],
           'option_urls': [n[1] for n in opt],
           'forbidden': [{'url': n[1], 'status': n[2]} for n in forbidden],
           'forbidden_count': len(forbidden), 'net_total': len(net)}
    OUT.setdefault('samples', {})[name] = rec
    print(name, 'SEVERE', rec['severe_count'], 'option', rec['option_requests'],
          '403/401', rec['forbidden_count'])
    if rec['severe_count']:
        print('  severe msgs:', [s[:160] for s in sev[:5]])
    save()
    return rec


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    OUT.setdefault('shots', []).append(os.path.basename(p))
    print('SHOT', p)
    return p


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def hard_reload_twice(drv, path, label):
    """整页加载两次，各采一轮 console/network"""
    recs = []
    for i in range(2):
        clear_logs(drv)
        drv.get(BASE + path)
        WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        recs.append(settle_and_collect(drv, '%s_load%d' % (label, i + 1)))
    return recs


def me_permissions(drv):
    return drv.execute_async_script(
        """
        const done = arguments[arguments.length-1];
        const token = localStorage.getItem('iatp:auth:token:v1');
        fetch('/api/v1/auth/me', {headers: token ? {Authorization: 'Bearer ' + token} : {}})
          .then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """)


# ===== 1. guest =====
def guest_section():
    d = make_driver()
    try:
        login(d, GUEST)
        OUT['guest_url'] = d.current_url
        me = me_permissions(d)
        OUT['guest_me_status'] = me['status']
        try:
            mej = json.loads(me['body'])
            data = mej.get('data') if isinstance(mej, dict) and 'data' in mej else mej
            perms = (data or {}).get('permissions') or []
            OUT['guest_permissions'] = perms
            OUT['guest_has_option_read'] = 'option:read' in perms or '*' in perms
        except Exception:
            OUT['guest_me_body'] = me['body'][:500]

        for path in PAGES:
            hard_reload_twice(d, path, 'guest' + path.replace('/', '_'))

        # 深浅色两帧（dashboard）
        clear_logs(d)
        set_theme(d, 'light')
        d.get(BASE + '/dashboard')
        time.sleep(6)
        shot(d, 'guest_dashboard_light')
        set_theme(d, 'dark')
        d.get(BASE + '/dashboard')
        time.sleep(6)
        shot(d, 'guest_dashboard_dark')
        OUT['guest_theme_samples'] = settle_and_collect(d, 'guest_dashboard_dark')
    finally:
        d.quit()


# ===== 2. 匿名公开页 =====
def anon_section():
    d = make_driver()
    try:
        d.get(BASE + '/login')
        time.sleep(2)
        d.execute_script("localStorage.clear(); sessionStorage.clear();")
        clear_logs(d)
        d.get(BASE + '/login')
        WebDriverWait(d, 30).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        rec = settle_and_collect(d, 'anon_login')
        OUT['anon_ok'] = rec['severe_count'] == 0 and rec['forbidden_count'] == 0
        shot(d, 'anon_login_light')
    finally:
        d.quit()


# ===== 3. admin 对照 =====
def api_option_notice(drv):
    """页内取 /api/option/ 的 site.notice 真值"""
    return drv.execute_async_script(
        """
        const done = arguments[arguments.length-1];
        const token = localStorage.getItem('iatp:auth:token:v1');
        fetch('/api/option/', {headers: token ? {Authorization: 'Bearer ' + token} : {}})
          .then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """)


def open_notification(drv, tab='公告'):
    btn = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "button[aria-label='通知']"))
    js_click(drv, btn)
    time.sleep(1.5)
    if tab:
        try:
            t = drv.find_element(
                By.XPATH, "//*[@role='tab'][contains(normalize-space(.), '%s')]" % tab)
            js_click(drv, t)
            time.sleep(1.2)
        except Exception:
            pass


def set_textarea(drv, el, value):
    """受控输入设值：Ctrl+A + Delete 触发 React onChange（Selenium clear() 不触发）"""
    from selenium.webdriver.common.keys import Keys
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)
    time.sleep(0.4)


def save_button(drv):
    """页头动作区保存钮（文案「保存更改」/「保存中…」）"""
    WebDriverWait(drv, 15).until(lambda d: d.execute_script(
        "return !![...document.querySelectorAll('button')].find(b => b.textContent.trim().startsWith('保存'))"))
    return drv.execute_script(
        "return [...document.querySelectorAll('button')].find(b => b.textContent.trim().startsWith('保存'))")


def admin_section():
    d = make_driver()
    try:
        login(d, ADMIN)
        me = me_permissions(d)
        OUT['admin_me_status'] = me['status']
        try:
            meJ = json.loads(me['body'])
            dataJ = meJ.get('data') if isinstance(meJ, dict) and 'data' in meJ else meJ
            OUT['admin_permissions_sample'] = ((dataJ or {}).get('permissions') or [])[:30]
            OUT['admin_has_option_read'] = ('option:read' in ((dataJ or {}).get('permissions') or [])
                                            or '*' in ((dataJ or {}).get('permissions') or []))
        except Exception:
            pass

        clear_logs(d)
        d.get(BASE + '/dashboard')
        WebDriverWait(d, 30).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        rec = settle_and_collect(d, 'admin_dashboard')
        OUT['admin_dashboard_option_ok'] = rec['option_requests'] >= 1 and all(
            s == 200 for s in rec['option_status'])
        shot(d, 'admin_dashboard_light')

        # 站头公告渲染 vs 接口真值
        opt = api_option_notice(d)
        notice = ''
        try:
            payload = json.loads(opt['body'])
            kv = payload.get('data') if isinstance(payload, dict) and 'data' in payload else payload
            notice = ((kv or {}).get('site.notice') or '').strip()
        except Exception:
            pass
        OUT['admin_api_notice'] = notice
        try:
            open_notification(d)
            pop_text = d.execute_script('return document.body.textContent || ""') or ''
            OUT['admin_header_notice_rendered'] = (notice in pop_text) if notice else None
        except Exception:
            OUT['admin_header_notice_rendered'] = 'open popover failed'
        shot(d, 'admin_notification_popover')

        # 系统设置站点信息分区
        clear_logs(d)
        d.get(BASE + '/system-settings/site/info')
        WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        rec2 = settle_and_collect(d, 'admin_site_info')
        body = d.execute_script('return document.body.textContent || ""') or ''
        OUT['admin_site_info_has_error_state'] = '设置加载失败' in body
        OUT['admin_site_info_has_no_permission'] = '无权限查看系统设置' in body
        OUT['admin_site_info_option_requests'] = rec2['option_requests']
        OUT['admin_site_info_option_status'] = rec2['option_status']
        shot(d, 'admin_site_info_light')

        # 公告分区：改动 - 保存 - PUT - 回读 - invalidate 后站头同步 - 还原
        clear_logs(d)
        d.get(BASE + '/system-settings/site/notice')
        WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        ta = WebDriverWait(d, 20).until(lambda x: x.find_element(By.ID, 'site-notice'))
        original = ta.get_attribute('value') or ''
        OUT['admin_notice_original'] = original
        marker = '接线测试_INT1585 公告同步验证'
        try:
            set_textarea(d, ta, marker)
            time.sleep(0.8)
            js_click(d, save_button(d))
            WebDriverWait(d, 30).until(lambda x: marker in (
                x.execute_script('return document.body.textContent || ""')))
            time.sleep(3)
            puts = [n for n in net_events(d) if n[0] == 'PUT' and '/api/option' in n[1]]
            OUT['admin_notice_put'] = [{'status': s, 'url': u} for _, u, s in puts]
            d.get(BASE + '/dashboard')
            time.sleep(5)
            open_notification(d)
            pop = d.execute_script('return document.body.textContent || ""') or ''
            OUT['admin_notice_header_synced'] = marker in pop
            shot(d, 'admin_notice_synced')
        finally:
            # 还原原始公告
            d.get(BASE + '/system-settings/site/notice')
            WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
            time.sleep(3)
            ta2 = WebDriverWait(d, 20).until(lambda x: x.find_element(By.ID, 'site-notice'))
            set_textarea(d, ta2, original)
            time.sleep(0.8)
            js_click(d, save_button(d))
            time.sleep(4)
            back = api_option_notice(d)
            try:
                payload = json.loads(back['body'])
                kv = payload.get('data') if isinstance(payload, dict) and 'data' in payload else payload
                OUT['admin_notice_restored'] = ((kv or {}).get('site.notice') or '').strip() == original.strip()
            except Exception:
                OUT['admin_notice_restored'] = None
    finally:
        d.quit()


# ===== 4. 半权限账号（有 user:read 无 option:read）=====
def half_section():
    if not HALF[0]:
        OUT['half_skipped'] = 'HALF_USER 未设置'
        return
    d = make_driver()
    try:
        login(d, HALF)
        me = me_permissions(d)
        try:
            meJ = json.loads(me['body'])
            OUT['half_permissions'] = (meJ.get('data') or {}).get('permissions') or []
        except Exception:
            pass
        clear_logs(d)
        d.get(BASE + '/system-settings/user/list')
        WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        rec = settle_and_collect(d, 'half_user_list')
        body = d.execute_script('return document.body.textContent || ""') or ''
        OUT['half_retry_error_state'] = '设置加载失败' in body
        OUT['half_no_permission_state'] = '无权限查看系统设置' in body
        OUT['half_option_requests'] = rec['option_requests']
        OUT['half_forbidden'] = rec['forbidden']
        shot(d, 'half_user_list_light')
    finally:
        d.quit()


def main():
    only = os.environ.get('ONLY', '')
    jobs = [('guest', guest_section), ('anon', anon_section),
            ('admin', admin_section), ('half', half_section)]
    for name, fn in jobs:
        if only and name not in only.split(','):
            continue
        print('=== section', name)
        section(name, fn)
    save()
    print('OUT', OUT_PATH)


if __name__ == '__main__':
    main()
