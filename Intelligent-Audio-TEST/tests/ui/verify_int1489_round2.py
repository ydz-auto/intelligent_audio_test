# -*- coding: utf-8 -*-
"""INT-1489 第二轮：真实登录 / Access Token 闭环 / 工作台数值 / 首页规模条 / 注册。

环境：docker 前端 15173 + 真实库栈 15000。
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

BASE = 'http://localhost:15173'
API = 'http://localhost:15000/api/v1'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1489'
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
SUFFIX = int(time.time())
RESULTS = {}


def record(k, v):
    RESULTS[k] = v
    print(f'[{k}]', json.dumps(v, ensure_ascii=False)[:1200])


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
    if (url.indexOf('/access-tokens') !== -1 || url.indexOf('/auth/') !== -1) {
      const ct = res.headers.get('content-type') || '';
      if (ct.indexOf('json') !== -1) { try { entry.resBody = await res.clone().text(); } catch (e) {} }
    }
    window.__fetchLog.push(entry);
    return res;
  } catch (e) { entry.status = 'ERR'; entry.error = String(e); window.__fetchLog.push(entry); throw e; }
};
"""


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1200', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run'):
        o.add_argument(a)
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe) and ver.split('.')[0] == str(major):
                drv_path = exe
    except Exception:
        pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=drv_path) if drv_path else Service())
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def shot(d, n):
    d.save_screenshot(f'{ART}/{n}.png')


def txt(d):
    return d.execute_script('return document.body.textContent || ""') or ''


def wait_ready(d, t=30):
    WebDriverWait(d, t).until(lambda x: x.execute_script('return document.readyState') == 'complete')


def goto(d, p, settle=3):
    d.get(BASE + p)
    wait_ready(d)
    time.sleep(settle)


def jsclick(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def xp(d, e, t=20):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, e)))


def log(d):
    try:
        return d.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []


def clear_log(d):
    d.execute_script('window.__fetchLog = [];')


def toasts(d):
    return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]


def api(path):
    import urllib.request
    return json.loads(urllib.request.urlopen(API + path, timeout=30).read().decode('utf-8'))


# ---------------------------------------------------------------- 登录
def section_login(d):
    out = {}
    d.get(BASE + '/login')
    wait_ready(d)
    time.sleep(2)
    # 清会话（只留主题）
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank')
    d.get(BASE + '/login')
    wait_ready(d)
    time.sleep(2.5)
    out['form_visible'] = len(d.find_elements(By.ID, 'username')) > 0
    out['banner'] = '开放模式' in txt(d)
    if not out['form_visible']:
        record('login_real', {'FAIL': 'form not visible', 'url': d.current_url})
        return

    # 深色登录页
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.get('about:blank')
    d.get(BASE + '/login')
    wait_ready(d)
    time.sleep(2)
    out['dark_form_visible'] = len(d.find_elements(By.ID, 'username')) > 0
    if out['dark_form_visible']:
        shot(d, 'login_dark')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    d.get('about:blank')
    d.get(BASE + '/login')
    wait_ready(d)
    time.sleep(2)
    # 清会话后重进（深色切换留在 store 里可能已 redirect）
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank')
    d.get(BASE + '/login')
    wait_ready(d)
    time.sleep(2)
    if len(d.find_elements(By.ID, 'username')) == 0:
        record('login_real', {'FAIL': 'redirected before submit', 'url': d.current_url})
        return

    clear_log(d)
    d.find_element(By.ID, 'username').send_keys(USER)
    d.find_element(By.ID, 'password').send_keys(PASSWORD)
    jsclick(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '登') and contains(normalize-space(.), '录')]"))
    time.sleep(5)
    out['after_login_url'] = d.current_url
    out['toasts'] = toasts(d)
    out['login_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
                             for e in log(d) if '/auth/' in e.get('url', '')]
    out['dashboard_after_login'] = '/dashboard' in d.current_url
    out['user_in_storage'] = bool(d.execute_script("return localStorage.getItem('iatp:auth:v1')"))
    shot(d, 'login_success')
    record('login_real', out)


# ---------------------------------------------------------------- 工作台
def section_dashboard(d):
    out = {}
    clear_log(d)
    goto(d, '/dashboard', settle=6)
    # 等待平台概览数值出现（非骨架）
    try:
        WebDriverWait(d, 25).until(lambda x: '任务总数' in txt(x) and '个已完成' in txt(x))
    except Exception:
        pass
    time.sleep(6)
    out['loading_spinner'] = '刷新中' in txt(d)
    out['requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
                       for e in log(d) if '/api/v1/' in e.get('url', '')]
    # 平台概览卡整块文本
    try:
        panel = d.find_element(By.XPATH, "//*[normalize-space(text())='平台概览']/ancestor::div[contains(@class,'bg-card')][1]")
        out['platform_summary_text'] = panel.text.replace('\n', ' | ')[:600]
    except Exception as e:
        out['platform_summary_text'] = f'FAIL {str(e)[:80]}'
    try:
        out['details_api'] = api('/home/stats/details').get('data')
    except Exception as e:
        out['details_api'] = str(e)
    try:
        s = api('/home/stats/summary').get('data')
        out['summary_recent_task'] = (s or {}).get('recent_tasks', [None])[0]
    except Exception as e:
        out['summary_recent_task'] = str(e)
    shot(d, 'dashboard_light')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.get('about:blank')
    goto(d, '/dashboard', settle=8)
    shot(d, 'dashboard_dark')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    d.get('about:blank')
    record('dashboard', out)


# ---------------------------------------------------------------- 首页规模条
def section_home_stats(d):
    out = {}
    clear_log(d)
    goto(d, '/', settle=5)
    # 平台规模条
    try:
        bar = d.find_element(By.XPATH, "//*[contains(normalize-space(.), '平台规模')]/ancestor::div[1]")
        out['scale_bar'] = bar.text.replace('\n', ' | ')[:400]
    except Exception:
        out['scale_bar'] = None
    # 找所有指向站内链接的卡片
    links = []
    for a in d.find_elements(By.XPATH, "//a[starts-with(@href,'/')]"):
        t = (a.text or '').strip().replace('\n', ' ')
        if t:
            links.append({'href': a.get_attribute('href'), 'text': t[:60]})
    out['site_links'] = links[:30]
    out['api_summary'] = api('/home/stats/summary').get('data')
    shot(d, 'home_light2')
    record('home_stats', out)


# ---------------------------------------------------------------- 注册
def section_register(d):
    out = {}
    d.get('about:blank')
    goto(d, '/register', settle=3)
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank')
    goto(d, '/register', settle=3)
    out['url'] = d.current_url
    out['form_visible'] = len(d.find_elements(By.ID, 'register-username')) > 0
    if not out['form_visible']:
        record('register', {'FAIL': 'form not visible', 'url': d.current_url, 'text': txt(d)[:200]})
        return
    shot(d, 'register_light')
    # 空提交
    jsclick(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '注') and contains(normalize-space(.), '册')]"))
    time.sleep(1.2)
    out['empty_validation'] = [e.text for e in d.find_elements(By.XPATH, "//p[contains(@class,'text-destructive')]")]
    # 密码不一致
    d.find_element(By.ID, 'register-username').send_keys(f'接线测试_reg_{SUFFIX}')
    d.find_element(By.ID, 'register-email').send_keys(f'reg_{SUFFIX}@example.com')
    d.find_element(By.ID, 'register-password').send_keys('TestPass@2026')
    d.find_element(By.ID, 'register-confirm').send_keys('TestPass@2027')
    jsclick(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '注') and contains(normalize-space(.), '册')]"))
    time.sleep(1.2)
    out['mismatch_validation'] = [e.text for e in d.find_elements(By.XPATH, "//p[contains(@class,'text-destructive')]")]
    # 重复用户名（真实提交）
    for fid, val in (('register-username', USER), ('register-email', f'dup_{SUFFIX}@example.com'),
                     ('register-password', 'TestPass@2026'), ('register-confirm', 'TestPass@2026')):
        el = d.find_element(By.ID, fid)
        el.send_keys(Keys.CONTROL, 'a')
        el.send_keys(Keys.DELETE)
        el.send_keys(val)
    clear_log(d)
    jsclick(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '注') and contains(normalize-space(.), '册')]"))
    time.sleep(4)
    out['duplicate_toasts'] = toasts(d)
    out['duplicate_url'] = d.current_url
    out['register_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                 'res': (e.get('resBody') or '')[:300]} for e in log(d) if '/auth/register' in e.get('url', '')]
    shot(d, 'register_duplicate')

    # 真实注册（唯一用户名）→ 成功后删除
    new_user = f'接线测试_reg_{SUFFIX}'
    for fid, val in (('register-username', new_user), ('register-email', f'reg_{SUFFIX}@example.com'),
                     ('register-password', 'TestPass@2026'), ('register-confirm', 'TestPass@2026')):
        el = d.find_element(By.ID, fid)
        el.send_keys(Keys.CONTROL, 'a')
        el.send_keys(Keys.DELETE)
        el.send_keys(val)
    clear_log(d)
    jsclick(d, d.find_element(By.XPATH, "//button[contains(normalize-space(.), '注') and contains(normalize-space(.), '册')]"))
    time.sleep(5)
    out['success_url'] = d.current_url
    out['success_toasts'] = toasts(d)
    out['success_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                'res': (e.get('resBody') or '')[:300]} for e in log(d) if '/auth/register' in e.get('url', '')]
    out['prefilled_username'] = None
    try:
        out['prefilled_username'] = d.find_element(By.ID, 'username').get_attribute('value')
    except Exception:
        pass
    shot(d, 'register_success')
    record('register', out)
    return new_user


# ---------------------------------------------------------------- Access Token
def section_tokens(d):
    out = {}
    goto(d, '/profile', settle=5)
    if len(d.find_elements(By.XPATH, "//button[@aria-label='创建新的 Access Token']")) == 0:
        d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
        goto(d, '/profile', settle=5)
    out['create_btn'] = len(d.find_elements(By.XPATH, "//button[@aria-label='创建新的 Access Token']"))
    out['initial_list_text'] = txt(d)[txt(d).find('Access Token'):][:400].replace('\n', ' | ')
    shot(d, 'token_card_initial')

    name1 = f'接线测试_token_{SUFFIX}'
    jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
    time.sleep(1.5)
    name_el = xp(d, "//input[@id='access-token-name']")
    name_el.send_keys(name1)
    time.sleep(0.5)
    out['name_value_after_type'] = name_el.get_attribute('value')
    # 选权限：第一模块全选
    sel = d.find_elements(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='全选']")
    out['modules'] = len(sel)
    jsclick(d, sel[0])
    time.sleep(1)
    out['after_select_all_name'] = name_el.get_attribute('value')
    out['scopes_hint'] = [e.text for e in d.find_elements(By.XPATH, "//*[@role='dialog']//span[contains(., '已选') and contains(., '项')]")]
    shot(d, 'token_create_filled2')
    clear_log(d)
    submit = d.find_element(By.XPATH, "//*[@role='dialog']//button[@type='submit']")
    out['submit_text'] = submit.text
    jsclick(d, submit)
    time.sleep(4)
    out['dialogs_after_submit'] = [x.text[:80].replace('\n', ' ') for x in d.find_elements(By.XPATH, "//*[@role='dialog']")]
    out['create_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                              'req': e.get('reqBody'), 'res': (e.get('resBody') or '')[:400]}
                              for e in log(d) if '/access-tokens' in e.get('url', '')]
    out['toasts'] = toasts(d)
    shot(d, 'token_reveal_light2')

    # 明文 / 复制
    reveal_text = ' || '.join(out['dialogs_after_submit'])
    out['reveal_has_once_hint'] = '只会显示一次' in reveal_text
    out['reveal_has_copy'] = '复制 Token' in reveal_text
    m = re.search(r'(iatp_[A-Za-z0-9_\-]{8,}|[A-Za-z0-9_\-]{20,})', reveal_text)
    out['plaintext_sample_len'] = len(m.group(1)) if m else 0
    # 关闭
    try:
        jsclick(d, d.find_element(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='关闭']"))
    except Exception:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.5)
    out['dialog_closed'] = len(d.find_elements(By.XPATH, "//*[@role='dialog']")) == 0

    # 列表 + GET 回读
    clear_log(d)
    goto(d, '/profile', settle=4)
    out['list_has_new'] = name1 in txt(d)
    out['list_get'] = [{'s': e.get('status'), 'res': (e.get('resBody') or '')[:600]}
                       for e in log(d) if e.get('method') == 'GET' and '/access-tokens' in e.get('url', '')]
    out['list_masked'] = '••' in txt(d) or '****' in txt(d) or '…' in txt(d)

    # 编辑
    try:
        jsclick(d, xp(d, "(//button[@aria-label='编辑 Access Token'])[1]"))
        time.sleep(1.5)
        edit_name = xp(d, "//input[@id='access-token-edit-name']")
        out['edit_prefill'] = edit_name.get_attribute('value')
        out['edit_expiry_trigger'] = d.find_element(By.ID, 'access-token-edit-expiry').text
        edit_name.send_keys(Keys.CONTROL, 'a')
        edit_name.send_keys(Keys.DELETE)
        name2 = f'接线测试_token_{SUFFIX}_改名'
        edit_name.send_keys(name2)
        clear_log(d)
        jsclick(d, d.find_element(By.XPATH, "//*[@role='dialog']//button[@type='submit']"))
        time.sleep(4)
        out['edit_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                 'req': e.get('reqBody')} for e in log(d) if '/access-tokens' in e.get('url', '')]
        goto(d, '/profile', settle=4)
        out['list_has_renamed'] = name2 in txt(d)
    except Exception as e:
        name2 = name1
        out['edit_FAIL'] = str(e)[:200]

    out['token_get_after_edit'] = [e.get('resBody') for e in log(d) if '/access-tokens' in e.get('url', '')][:1]

    # 启停
    try:
        clear_log(d)
        jsclick(d, xp(d, "(//button[normalize-space(.)='停用'])[1]", 10))
        time.sleep(4)
        out['toggle_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                   'req': e.get('reqBody')} for e in log(d) if '/access-tokens' in e.get('url', '')]
        goto(d, '/profile', settle=4)
        out['badge_disabled'] = '已停用' in txt(d)
        out['badge_enabled'] = '已启用' in txt(d)
    except Exception as e:
        out['toggle_FAIL'] = str(e)[:200]

    # 深色列表 + 深色创建弹窗
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.get('about:blank')
    goto(d, '/profile', settle=4)
    shot(d, 'profile_dark2')
    try:
        jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
        time.sleep(1.5)
        shot(d, 'token_create_dark2')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception as e:
        out['dark_create_FAIL'] = str(e)[:120]
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    d.get('about:blank')
    goto(d, '/profile', settle=4)

    # 删除清理
    try:
        clear_log(d)
        jsclick(d, xp(d, "(//button[@aria-label='删除 Access Token'])[1]", 10))
        time.sleep(1.5)
        out['confirm_text'] = ' || '.join(x.text[:200].replace('\n', ' ') for x in d.find_elements(By.XPATH, "//*[@role='alertdialog' or @role='dialog']"))
        jsclick(d, xp(d, "(//*[@role='alertdialog']//button[normalize-space(.)='删除'])[1] | (//*[@role='dialog']//button[normalize-space(.)='删除'])[1]"))
        time.sleep(4)
        out['delete_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
                                  for e in log(d) if '/access-tokens' in e.get('url', '')]
        goto(d, '/profile', settle=4)
        out['gone_after_delete'] = (name2 not in txt(d)) and (name1 not in txt(d))
        out['empty_state'] = '暂无 Access Token' in txt(d)
    except Exception as e:
        out['delete_FAIL'] = str(e)[:200]
    record('tokens', out)


def main():
    os.makedirs(ART, exist_ok=True)
    d = driver()
    new_user = None
    try:
        for fn in (section_login, section_dashboard, section_home_stats):
            try:
                fn(d)
            except Exception as e:
                record(fn.__name__ + '_fatal', str(e)[:300])
        try:
            new_user = section_register(d)
        except Exception as e:
            record('register_fatal', str(e)[:300])
        try:
            section_tokens(d)
        except Exception as e:
            record('tokens_fatal', str(e)[:300])
    finally:
        d.quit()
        # 清理注册用户
        if new_user:
            try:
                import urllib.request
                users = api('/auth/users?page=1&page_size=200')['data']['items']
                hit = [u for u in users if u['username'] == new_user]
                for u in hit:
                    req = urllib.request.Request(f"{API}/auth/users/{u['id']}", method='DELETE')
                    with urllib.request.urlopen(req, timeout=20) as r:
                        RESULTS.setdefault('cleanup', []).append({'user': new_user, 'id': u['id'], 'status': r.status})
            except Exception as e:
                RESULTS['cleanup_error'] = str(e)
        with open(f'{ART}/round2_result.json', 'w', encoding='utf-8') as f:
            json.dump({'suffix': SUFFIX, 'results': RESULTS}, f, ensure_ascii=False, indent=2)
        print('DONE')


if __name__ == '__main__':
    main()
