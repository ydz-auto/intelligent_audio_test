# -*- coding: utf-8 -*-
"""INT-1489 复走·React·门户与壳：首页/概览/登录/个人中心/Access Token/错误页。

环境（负责人 2026-10-23 铁律）：docker 前端 http://localhost:15173（React），
后端真实库栈 http://localhost:15000（intelligent_audio_test）。禁止本地 dev server。

覆盖：
1. /login 登录表单：初值/校验/错误密码提示/真实登录跳转/整页重载行为；浅深截图。
2. / 首页门户：枢纽图（role=img）与四角/算法节点、平台规模条真实数值与接口一致。
3. /dashboard 概览：卡片数值 /home/stats/details、/home/stats/summary、/tasks/stats 对齐。
4. /profile 个人中心：个人信息、权限 Popover、账号绑定、Access Token 创建（明文一次）/
   列表掩码 / 编辑 / 启停 / 删除闭环；change-password 可达性裁定。
5. 错误页 /401 /403 /404 /500 /503。
所有写操作只写「接线测试_」前缀数据并在脚本内删除。
"""
import json
import os
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://localhost:15000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1489'
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
SUFFIX = int(time.time())

RESULTS = {}


def record(key, value):
    RESULTS[key] = value
    print(f'[{key}]', json.dumps(value, ensure_ascii=False)[:900])


FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  let entry = { url: url, method: method };
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    if (init && init.body && typeof init.body === 'string') entry.reqBody = init.body;
    if (url.indexOf('/auth/') !== -1 || url.indexOf('/home/stats') !== -1 || url.indexOf('/access-tokens') !== -1) {
      const ct = res.headers.get('content-type') || '';
      if (ct.indexOf('json') !== -1) {
        try { entry.resBody = await res.clone().text(); } catch (e) {}
      }
    }
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.status = 'ERR';
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""


def driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major:
                        drv_path = exe
                except ValueError:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return drv


def shot(drv, name):
    path = f'{ART}/{name}.png'
    drv.save_screenshot(path)
    print('SHOT', path)
    return path


def wait_ready(drv, timeout=30):
    WebDriverWait(drv, timeout).until(lambda d: d.execute_script('return document.readyState') == 'complete')


def text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []


def clear_log(drv):
    try:
        drv.execute_script('window.__fetchLog = [];')
    except Exception:
        pass


def toasts(drv):
    return [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]


def wait_toast(drv, text_, timeout=20):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: any(text_ in (e.text or '') for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        return toasts(drv)
    except Exception:
        return toasts(drv)


def jsclick(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def set_theme(drv, mode):
    drv.execute_script(f"localStorage.setItem('iatp:theme:v1:mode', '{mode}');")
    drv.get('about:blank')
    time.sleep(0.4)


def goto(drv, path, settle=3.0):
    drv.get(BASE + path)
    wait_ready(drv)
    time.sleep(settle)


def xp(drv, expr, timeout=20):
    return WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.XPATH, expr)))


def api_get(path):
    import urllib.request
    req = urllib.request.Request(API + path, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


# ---------------------------------------------------------------------------
# 1. 登录页
# ---------------------------------------------------------------------------
def section_login(drv):
    out = {}
    clear_log(drv)
    drv.get(BASE + '/login')
    wait_ready(drv)
    time.sleep(2.5)
    out['url_initial'] = drv.current_url
    out['has_form'] = len(drv.find_elements(By.ID, 'username')) > 0
    out['page_text_head'] = text(drv)[:200].replace('\n', ' ')
    shot(drv, 'login_light')

    # 登录页首次请求（Network）
    log = fetch_log(drv)
    out['requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')} for e in log]

    if out['has_form']:
        # 空提交校验
        btn = drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '登') and contains(normalize-space(.), '录')]")
        jsclick(drv, btn)
        time.sleep(1.2)
        out['empty_validation'] = [e.text for e in drv.find_elements(By.XPATH, "//p[contains(@class,'text-destructive')]")]
        # 错误密码
        drv.find_element(By.ID, 'username').send_keys(USER)
        drv.find_element(By.ID, 'password').send_keys('WrongPass@2026')
        jsclick(drv, btn)
        out['wrong_password_toasts'] = wait_toast(drv, '', timeout=15)
        out['wrong_password_url'] = drv.current_url
        shot(drv, 'login_wrong_password')
        # 深色
        set_theme(drv, 'dark')
        drv.get(BASE + '/login')
        wait_ready(drv)
        time.sleep(2)
        if len(drv.find_elements(By.ID, 'username')) > 0:
            shot(drv, 'login_dark')
        else:
            out['dark_login_redirected'] = drv.current_url
        set_theme(drv, 'light')

        # 真实登录
        drv.get(BASE + '/login')
        wait_ready(drv)
        time.sleep(2)
        if len(drv.find_elements(By.ID, 'username')) == 0:
            out['login_after_light_switch_url'] = drv.current_url
        else:
            clear_log(drv)
            drv.find_element(By.ID, 'username').send_keys(USER)
            drv.find_element(By.ID, 'password').send_keys(PASSWORD)
            jsclick(drv, btn)
            time.sleep(4)
            out['login_success_url'] = drv.current_url
            out['login_success_toasts'] = toasts(drv)
            out['login_requests'] = [
                {'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                 'req_keys': list(json.loads(e['reqBody']).keys()) if e.get('reqBody') else None}
                for e in fetch_log(drv) if '/auth/' in e.get('url', '')]
            shot(drv, 'login_success')

    # 整页重载行为
    drv.get(BASE + '/login')
    wait_ready(drv)
    drv.refresh()
    wait_ready(drv)
    time.sleep(3)
    out['reload_url'] = drv.current_url
    out['reload_has_form'] = len(drv.find_elements(By.ID, 'username')) > 0
    out['session_user_visible'] = 'dev_user' in text(drv) or USER in text(drv)
    record('login', out)


# ---------------------------------------------------------------------------
# 2. 首页
# ---------------------------------------------------------------------------
def section_home(drv):
    out = {}
    clear_log(drv)
    goto(drv, '/', settle=3)
    out['url'] = drv.current_url
    body = text(drv)
    out['orbit_role_img'] = len(drv.find_elements(By.CSS_SELECTOR, "[role='img'][aria-label='平台总览']"))
    out['orbit_nodes'] = [e.text.strip() for e in drv.find_elements(
        By.XPATH, "//*[@role='img'][@aria-label='平台总览']//div[contains(@class,'absolute')]") if e.text.strip()][:20]
    # 枢纽图节点是否可点
    orbit_links = drv.find_elements(By.XPATH, "//*[@role='img'][@aria-label='平台总览']//a")
    out['orbit_link_count'] = len(orbit_links)
    out['orbit_nested_buttons'] = len(drv.find_elements(By.XPATH, "//*[@role='img'][@aria-label='平台总览']//button"))
    # 平台规模条
    stats_texts = []
    for e in drv.find_elements(By.XPATH, "//*[contains(normalize-space(.), '任务') and contains(normalize-space(.), '用例')]//div"):
        t = (e.text or '').strip()
        if t and len(t) < 60:
            stats_texts.append(t)
    out['stats_candidates'] = stats_texts[:25]
    shot(drv, 'home_light')
    out['requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
                       for e in fetch_log(drv) if '/api/v1/' in e.get('url', '')]

    # 平台规模接口真值（公开）
    try:
        summary = api_get('/home/stats/summary')
        out['api_summary'] = summary.get('data')
    except Exception as e:
        out['api_summary_error'] = str(e)

    # 规模条点击跳转（若存在）
    try:
        stat_item = drv.find_element(By.XPATH, "//a[contains(@href,'/tasks')]")
        out['stats_task_link_href'] = stat_item.get_attribute('href')
    except Exception:
        out['stats_task_link_href'] = None

    set_theme(drv, 'dark')
    goto(drv, '/', settle=2.5)
    shot(drv, 'home_dark')
    set_theme(drv, 'light')
    record('home', out)


# ---------------------------------------------------------------------------
# 3. 概览工作台
# ---------------------------------------------------------------------------
def section_dashboard(drv):
    out = {}
    clear_log(drv)
    goto(drv, '/dashboard', settle=4)
    out['url'] = drv.current_url
    out['page_text'] = text(drv)[:600].replace('\n', ' ')
    out['stats_api'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
                        for e in fetch_log(drv) if '/stats' in e.get('url', '')]
    # 三张概览卡数值
    cards = {}
    for title in ('任务总数', '完成率', '最近任务'):
        try:
            el = drv.find_element(By.XPATH, f"//*[normalize-space(text())='{title}']/ancestor::div[1]")
            cards[title] = el.text.replace('\n', ' | ')[:160]
        except Exception:
            cards[title] = None
    out['cards'] = cards
    # 设备状态区
    try:
        dev = drv.find_element(By.XPATH, "//*[contains(normalize-space(.), '设备状态')]/ancestor::div[1]")
        out['device_panel'] = dev.text.replace('\n', ' | ')[:200]
    except Exception:
        out['device_panel'] = None
    shot(drv, 'dashboard_light')
    try:
        out['api_details'] = api_get('/home/stats/details').get('data')
    except Exception as e:
        out['api_details_error'] = str(e)
    try:
        s = api_get('/home/stats/summary').get('data')
        out['api_summary_recent'] = (s or {}).get('recent_tasks', [None])[0]
    except Exception as e:
        out['api_summary_error'] = str(e)

    set_theme(drv, 'dark')
    goto(drv, '/dashboard', settle=3)
    shot(drv, 'dashboard_dark')
    set_theme(drv, 'light')
    record('dashboard', out)


# ---------------------------------------------------------------------------
# 4. 个人中心 + Access Token 闭环
# ---------------------------------------------------------------------------
def section_profile(drv):
    out = {}
    clear_log(drv)
    goto(drv, '/profile', settle=4)
    out['url'] = drv.current_url
    body = text(drv)
    out['has_change_password_trigger'] = ('修改密码' in body) or ('更改密码' in body)
    out['change_password_dialog_in_dom'] = len(drv.find_elements(By.XPATH, "//*[contains(normalize-space(.), '当前密码')]"))
    out['sections'] = [t for t in ('个人信息', '账号安全', 'Access Token', '快捷入口') if t in body]
    out['page_text'] = body[:800].replace('\n', ' ')
    out['requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
                       for e in fetch_log(drv) if '/api/v1/' in e.get('url', '')]
    shot(drv, 'profile_light')

    # 权限 Popover
    try:
        perm = drv.find_element(By.XPATH, "//button[@aria-label='查看权限清单']")
        jsclick(drv, perm)
        time.sleep(1)
        out['permission_popover'] = drv.find_element(
            By.XPATH, "//*[@role='dialog' or contains(@class,'popover')]").text[:300].replace('\n', ' | ')
        shot(drv, 'profile_permission_popover')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.6)
    except Exception as e:
        out['permission_popover'] = f'FAIL {str(e)[:120]}'

    # ---- 创建 Token：空表单校验 ----
    try:
        create_btn = xp(drv, "//button[@aria-label='创建新的 Access Token']")
        jsclick(drv, create_btn)
        time.sleep(1.2)
        out['create_dialog_open'] = len(drv.find_elements(By.ID, 'access-token-name')) > 0
        drv.find_element(By.XPATH, "//button[normalize-space(.)='创建']").click()
        time.sleep(1.2)
        out['create_validation'] = [e.text for e in drv.find_elements(By.XPATH, "//*[@role='dialog']//p[contains(@class,'text-destructive')]")]
        shot(drv, 'token_create_validation')

        # 有效期下拉选项
        trig = drv.find_element(By.ID, 'access-token-expiry')
        jsclick(drv, trig)
        time.sleep(0.8)
        opts = [e.text.strip() for e in drv.find_elements(By.XPATH, "//*[@role='option']")]
        out['expiry_options'] = opts
        # 选择「永不过期」再切回 30 天（验证不与表单残留）
        try:
            never = drv.find_element(By.XPATH, "//*[@role='option'][contains(normalize-space(.), '永不过期')]")
            jsclick(drv, never)
            time.sleep(0.6)
            out['never_hint'] = '永不过期' in drv.find_element(By.XPATH, "//*[@role='dialog']").text
        except Exception as e:
            out['never_hint'] = f'FAIL {str(e)[:100]}'
        # 切回 30 天
        jsclick(drv, drv.find_element(By.ID, 'access-token-expiry'))
        time.sleep(0.6)
        thirty = drv.find_element(By.XPATH, "//*[@role='option'][contains(normalize-space(.), '30 天')]")
        jsclick(drv, thirty)
        time.sleep(0.6)

        # 填名称 + 选权限（第一个模块全选）
        name1 = f'接线测试_token_{SUFFIX}'
        drv.find_element(By.ID, 'access-token-name').send_keys(name1)
        select_all = drv.find_elements(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='全选']")
        out['matrix_modules'] = len(select_all)
        jsclick(drv, select_all[0])
        time.sleep(0.8)
        out['scopes_selected_hint'] = [e.text for e in drv.find_elements(By.XPATH, "//*[@role='dialog']//span[contains(., '已选') and contains(., '项')]")]
        shot(drv, 'token_create_filled')

        # 提交
        clear_log(drv)
        drv.find_element(By.XPATH, "//button[normalize-space(.)='创建']").click()
        time.sleep(3)
        dlg_text = ''
        for d in drv.find_elements(By.XPATH, "//*[@role='dialog']"):
            dlg_text += (d.text or '') + ' || '
        out['reveal_dialog_text'] = dlg_text[:400].replace('\n', ' | ')
        out['create_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                   'req': e.get('reqBody')}
                                  for e in fetch_log(drv) if '/access-tokens' in e.get('url', '')]
        shot(drv, 'token_reveal_light')
        # 明文 taken from dialog
        m = re.search(r'(iatp_[A-Za-z0-9_\-]{10,}|[A-Za-z0-9_\-]{24,})', dlg_text)
        out['plaintext_seen'] = bool(m)
        out['plaintext_len'] = len(m.group(1)) if m else 0
        # 复制按钮
        out['reveal_has_copy'] = '复制 Token' in dlg_text
        # 关闭
        try:
            jsclick(drv, drv.find_element(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='关闭']"))
        except Exception:
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)

        # 回读列表（GET）
        clear_log(drv)
        goto(drv, '/profile', settle=3)
        out['list_has_new_token'] = name1 in text(drv)
        out['list_get_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                     'res': (e.get('resBody') or '')[:500]}
                                    for e in fetch_log(drv) if '/access-tokens' in e.get('url', '')]

        # ---- 编辑 ----
        try:
            edit_btn = xp(drv, "//button[@aria-label='编辑 Access Token'][1]")
            jsclick(drv, edit_btn)
            time.sleep(1.2)
            dlg = drv.find_element(By.XPATH, "//*[@role='dialog']")
            out['edit_dialog_text'] = dlg.text[:400].replace('\n', ' | ')
            out['edit_prefilled_name'] = drv.find_element(By.ID, 'access-token-edit-name').get_attribute('value')
            name_in = drv.find_element(By.ID, 'access-token-edit-name')
            name_in.send_keys(Keys.CONTROL, 'a')
            name_in.send_keys(Keys.DELETE)
            name2 = f'接线测试_token_{SUFFIX}_改名'
            name_in.send_keys(name2)
            clear_log(drv)
            jsclick(drv, drv.find_element(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='保存']"))
            time.sleep(3)
            out['edit_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                     'req': e.get('reqBody')}
                                    for e in fetch_log(drv) if '/access-tokens' in e.get('url', '')]
            goto(drv, '/profile', settle=3)
            out['list_has_renamed'] = name2 in text(drv)
            shot(drv, 'token_list_after_edit')
        except Exception as e:
            out['edit'] = f'FAIL {str(e)[:200]}'

        # ---- 启停 ----
        try:
            clear_log(drv)
            toggle = xp(drv, "//button[normalize-space(.)='停用'][1]", timeout=10)
            jsclick(drv, toggle)
            time.sleep(3)
            out['toggle_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                       'req': e.get('reqBody')}
                                      for e in fetch_log(drv) if '/access-tokens' in e.get('url', '')]
            goto(drv, '/profile', settle=3)
            out['list_has_disabled_badge'] = '已停用' in text(drv)
        except Exception as e:
            out['toggle'] = f'FAIL {str(e)[:200]}'

        # ---- 深色截图（token 列表 + 创建弹窗）----
        set_theme(drv, 'dark')
        goto(drv, '/profile', settle=3)
        shot(drv, 'profile_dark')
        try:
            jsclick(drv, xp(drv, "//button[@aria-label='创建新的 Access Token']"))
            time.sleep(1.2)
            shot(drv, 'token_create_dark')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
        except Exception as e:
            out['dark_dialog'] = f'FAIL {str(e)[:120]}'
        set_theme(drv, 'light')
        goto(drv, '/profile', settle=3)

        # ---- 删除（清理）----
        try:
            clear_log(drv)
            jsclick(drv, xp(drv, "//button[@aria-label='删除 Access Token'][1]"))
            time.sleep(1.2)
            out['delete_confirm_text'] = drv.find_element(By.XPATH, "//*[@role='alertdialog' or @role='dialog']").text[:300].replace('\n', ' | ')
            jsclick(drv, xp(drv, "//*[@role='alertdialog']//button[normalize-space(.)='删除'] | //*[@role='dialog']//button[normalize-space(.)='删除']"))
            time.sleep(3)
            out['delete_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
                                      for e in fetch_log(drv) if '/access-tokens' in e.get('url', '')]
            goto(drv, '/profile', settle=3)
            out['list_after_delete'] = name2 in text(drv)
            out['empty_state'] = '暂无 Access Token' in text(drv)
        except Exception as e:
            out['delete'] = f'FAIL {str(e)[:200]}'

    except Exception as e:
        out['token_flow'] = f'FAIL {str(e)[:300]}'

    record('profile', out)


# ---------------------------------------------------------------------------
# 5. 错误页
# ---------------------------------------------------------------------------
def section_errors(drv):
    out = {}
    for code in ('401', '403', '404', '500', '503'):
        try:
            goto(drv, f'/{code}', settle=2)
            out[code] = {'url': drv.current_url, 'text': text(drv)[:220].replace('\n', ' | ')}
            shot(drv, f'error_{code}')
        except Exception as e:
            out[code] = f'FAIL {str(e)[:120]}'
    set_theme(drv, 'dark')
    goto(drv, '/404', settle=2)
    shot(drv, 'error_404_dark')
    set_theme(drv, 'light')
    record('errors', out)


def main():
    os.makedirs(ART, exist_ok=True)
    drv = driver()
    try:
        try:
            section_login(drv)
        except Exception as e:
            record('login_fatal', str(e)[:400])
        try:
            section_home(drv)
        except Exception as e:
            record('home_fatal', str(e)[:400])
        try:
            section_dashboard(drv)
        except Exception as e:
            record('dashboard_fatal', str(e)[:400])
        try:
            section_profile(drv)
        except Exception as e:
            record('profile_fatal', str(e)[:400])
        try:
            section_errors(drv)
        except Exception as e:
            record('errors_fatal', str(e)[:400])
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(f'{ART}/verify_result.json', 'w', encoding='utf-8') as f:
            json.dump({'suffix': SUFFIX, 'results': RESULTS}, f, ensure_ascii=False, indent=2)
        print('DONE')


if __name__ == '__main__':
    main()
