# -*- coding: utf-8 -*-
"""INT-1489 第三轮：Access Token 三类弹窗完整闭环 + 注册真实流程 + 首页规模条。

全部连 docker 真实库栈（15173 + 15000）；只写「接线测试_」数据并清理。
"""
import json
import os
import re
import time
import traceback
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://localhost:15000/api/v1'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1489'
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
SUFFIX = int(time.time())
R = {}
PROBE_PREFIX = '接线测试_token_probe_'

PATCH = r"""
window.__fetchLog = [];
const f = window.fetch;
window.fetch = async function(input, init){
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const e = {url:url, method:(init&&init.method)||'GET'};
  try { const r = await f.apply(this, arguments); e.status = r.status;
        if (init && typeof init.body === 'string') e.reqBody = init.body;
        if (url.indexOf('/access-tokens') !== -1 || url.indexOf('/auth/register') !== -1) {
          try { e.resBody = await r.clone().text(); } catch(x){}
        }
        window.__fetchLog.push(e); return r; }
  catch(err){ e.status='ERR'; e.error=String(err); window.__fetchLog.push(e); throw err; }
};
"""


def rec(k, v):
    R[k] = v
    print(f'[{k}]', json.dumps(v, ensure_ascii=False)[:1400])


def drv():
    o = Options(); o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1600,1400', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--no-first-run', '--disable-dev-shm-usage'):
        o.add_argument(a)
    import winreg
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe) and v.split('.')[0] == str(major):
                path = exe
    except Exception:
        pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return d


def t(d):
    return d.execute_script('return document.body.textContent || ""') or ''


def shot(d, n):
    d.save_screenshot(f'{ART}/{n}.png')
    print('SHOT', n)


def goto(d, p, s=3):
    d.get(BASE + p)
    WebDriverWait(d, 30).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(s)


def jsclick(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def xp(d, e, t_=20):
    return WebDriverWait(d, t_).until(EC.presence_of_element_located((By.XPATH, e)))


def lg(d):
    try:
        return d.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []


def clr(d):
    d.execute_script('window.__fetchLog = [];')


def toasts(d):
    return [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]


def login(d):
    d.get(BASE + '/login'); time.sleep(2)
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank'); time.sleep(0.4)
    goto(d, '/login', 2.5)
    if len(d.find_elements(By.ID, 'username')) == 0:
        return d.current_url
    d.find_element(By.ID, 'username').send_keys(USER)
    d.find_element(By.ID, 'password').send_keys(PASSWORD)
    d.find_element(By.XPATH, "//form//button[@type='submit']").click()
    time.sleep(5)
    return d.current_url


def row_xpath(name, inner):
    return f"//p[normalize-space(.)='{name}']/ancestor::div[contains(@class,'py-3')][1]{inner}"


def token_requests(d, label=''):
    out = []
    for e in lg(d):
        if '/access-tokens' not in e.get('url', ''):
            continue
        item = {'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
        if e.get('reqBody'):
            try:
                item['req'] = json.loads(e['reqBody'])
            except Exception:
                item['req'] = e['reqBody'][:200]
        if e.get('resBody'):
            try:
                item['res'] = json.loads(e['resBody']).get('data')
            except Exception:
                item['res'] = e['resBody'][:300]
        out.append(item)
    return out


# ------------------------------------------------------------------ tokens
def section_tokens(d):
    out = {}
    url = login(d)
    out['login_url'] = url
    goto(d, '/profile', 5)
    out['profile_url'] = d.current_url
    out['create_btn'] = len(d.find_elements(By.XPATH, "//button[@aria-label='创建新的 Access Token']"))
    if not out['create_btn']:
        rec('tokens', {'FAIL': 'profile not reachable', 'url': d.current_url, 'text': t(d)[:200]})
        return
    out['initial_page_token_section'] = t(d)[t(d).find('Access Token'):][:200].replace('\n', ' | ')
    shot(d, 'profile_light_round3')

    # ---------- 创建：必填留空 ----------
    jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
    time.sleep(1.5)
    out['dlg_title'] = d.find_element(By.XPATH, "//*[@role='dialog']//h2").text
    out['dlg_desc'] = ' '.join(d.find_elements(By.XPATH, "//*[@role='dialog']//p")[0].text.split())
    jsclick(d, xp(d, "//*[@role='dialog']//button[@type='submit']"))
    time.sleep(1.2)
    out['empty_errors'] = [e.text for e in d.find_elements(By.XPATH, "//*[@role='dialog']//p[contains(@class,'text-destructive')]")]
    # 有效期下拉
    jsclick(d, xp(d, "//*[@role='dialog']//*[@id='access-token-expiry']"))
    time.sleep(0.8)
    out['expiry_options'] = [e.text.strip() for e in d.find_elements(By.XPATH, "//*[@role='option']")]
    jsclick(d, xp(d, "//*[@role='option'][contains(normalize-space(.), '30 天')]"))
    time.sleep(0.6)

    # 名称 + 权限
    name1 = f'接线测试_token_{SUFFIX}'
    xp(d, "//*[@role='dialog']//input[@id='access-token-name']").send_keys(name1)
    sel = d.find_elements(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='全选']")
    out['permission_modules'] = len(sel)
    jsclick(d, sel[0]); time.sleep(0.8)
    out['scope_hint'] = [e.text for e in d.find_elements(By.XPATH, "//*[@role='dialog']//span[contains(., '已选') and contains(., '项')]")]
    shot(d, 'token_create_filled_round3')
    # 深色创建弹窗
    d.execute_script("document.documentElement.classList.add('dark');")
    time.sleep(0.8)
    shot(d, 'token_create_dark_round3')
    d.execute_script("document.documentElement.classList.remove('dark');")

    clr(d)
    jsclick(d, xp(d, "//*[@role='dialog']//button[@type='submit']"))
    time.sleep(4)
    dialogs = [x.text for x in d.find_elements(By.XPATH, "//*[@role='dialog']")]
    out['after_create_dialogs'] = [x[:120].replace('\n', ' ') for x in dialogs]
    out['create_requests'] = token_requests(d)
    out['create_toasts'] = toasts(d)
    shot(d, 'token_reveal_round3')
    reveal_txt = ' '.join(dialogs)
    out['reveal_one_time_hint'] = '只会显示一次' in reveal_txt
    out['reveal_copy_btn'] = len(d.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '复制')]"))
    out['reveal_token_input_present'] = len(d.find_elements(By.XPATH, "//*[@role='dialog']//input")) + len(
        d.find_elements(By.XPATH, "//*[@role='dialog']//code"))
    m = re.search(r'(at_[A-Za-z0-9_\-]{12,}|[A-Za-z0-9_\-]{24,})', reveal_txt)
    out['plaintext_seen_len'] = len(m.group(1)) if m else 0
    # 关闭
    btns = d.find_elements(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='关闭' or normalize-space(.)='Close']")
    if btns:
        jsclick(d, btns[-1])
    else:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.5)
    out['dialog_closed_after_reveal'] = len(d.find_elements(By.XPATH, "//*[@role='dialog']")) == 0

    # ---------- 列表回读（GET） ----------
    clr(d)
    goto(d, '/profile', 4)
    out['list_has_created'] = name1 in t(d)
    out['list_mask_pattern'] = bool(re.search(r'at_…[0-9a-f]{3,}', t(d)))
    gets = [x for x in token_requests(d) if x['m'] == 'GET']
    out['list_get'] = gets[-1] if gets else None
    shot(d, 'token_list_round3')

    # ---------- 编辑 ----------
    try:
        jsclick(d, xp(d, row_xpath(name1, "//button[@aria-label='编辑 Access Token']")))
        time.sleep(1.5)
        edit = d.find_element(By.XPATH, "//*[@role='dialog']")
        out['edit_title'] = edit.find_element(By.XPATH, './/h2').text
        en = edit.find_element(By.ID, 'access-token-edit-name')
        out['edit_prefill_name'] = en.get_attribute('value')
        out['edit_prefill_expiry'] = edit.find_element(By.ID, 'access-token-edit-expiry').text
        out['edit_scope_hint'] = [e.text for e in edit.find_elements(By.XPATH, ".//span[contains(., '已选') and contains(., '项')]")]
        # 清空名称提交 → 校验
        en.send_keys(Keys.CONTROL, 'a'); en.send_keys(Keys.DELETE)
        jsclick(d, edit.find_element(By.XPATH, ".//button[@type='submit']"))
        time.sleep(1.2)
        out['edit_empty_name_error'] = [e.text for e in edit.find_elements(By.XPATH, ".//p[contains(@class,'text-destructive')]")]
        name2 = f'接线测试_token_{SUFFIX}_改名'
        en.send_keys(name2)
        clr(d)
        jsclick(d, edit.find_element(By.XPATH, ".//button[@type='submit']"))
        time.sleep(4)
        out['edit_requests'] = token_requests(d)
        clr(d)
        goto(d, '/profile', 4)
        out['list_has_renamed'] = name2 in t(d)
        gets = [x for x in token_requests(d) if x['m'] == 'GET']
        out['get_after_edit'] = gets[-1] if gets else None
    except Exception as e:
        name2 = name1
        out['edit_FAIL'] = traceback.format_exc()[-500:]

    # ---------- 启停（Switch） ----------
    try:
        clr(d)
        sw = xp(d, row_xpath(name2, "//*[@data-slot='switch' or @role='switch']"))
        out['switch_aria'] = sw.get_attribute('aria-label')
        jsclick(d, sw)
        time.sleep(4)
        out['toggle_requests'] = token_requests(d)
        goto(d, '/profile', 4)
        out['badge_after_disable'] = '已停用' in t(d)
        # 恢复启用
        clr(d)
        sw2 = xp(d, row_xpath(name2, "//*[@data-slot='switch' or @role='switch']"))
        jsclick(d, sw2)
        time.sleep(4)
        out['toggle_back_requests'] = token_requests(d)
        goto(d, '/profile', 4)
        out['badge_after_enable'] = '已启用' in t(d)
    except Exception as e:
        out['toggle_FAIL'] = traceback.format_exc()[-400:]

    # ---------- 取消与重开（Esc / 遮罩 / 残留） ----------
    try:
        jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
        time.sleep(1.2)
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
        out['esc_closes_create'] = len(d.find_elements(By.ID, 'access-token-name')) == 0
        jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
        time.sleep(1.2)
        el = xp(d, "//input[@id='access-token-name']")
        el.send_keys('临时残留检查')
        # 点击遮罩（dialog 外层 overlay）
        overlay = d.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-overlay"], [data-base-ui-portal] > div')
        if overlay:
            jsclick(d, overlay[0])
        time.sleep(1.2)
        out['overlay_closes_create'] = len(d.find_elements(By.ID, 'access-token-name')) == 0
        if not out['overlay_closes_create']:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)
        jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
        time.sleep(1.2)
        out['reopen_name_empty'] = xp(d, "//input[@id='access-token-name']").get_attribute('value') == ''
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception as e:
        out['cancel_FAIL'] = traceback.format_exc()[-400:]

    # ---------- 深色卡片截图 ----------
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.get('about:blank'); d.get('/profile')
    WebDriverWait(d, 30).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(5)
    shot(d, 'profile_dark_round3')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    d.get('about:blank'); goto(d, '/profile', 4)

    # ---------- 删除清理（含探针遗留） ----------
    try:
        for target in (name2,):
            clr(d)
            jsclick(d, xp(d, row_xpath(target, "//button[@aria-label='删除 Access Token']"), 10))
            time.sleep(1.5)
            out['confirm_dialog_text'] = ' '.join(
                x.text[:250].replace('\n', ' ') for x in d.find_elements(By.XPATH, "//*[@role='alertdialog' or @role='dialog']"))
            jsclick(d, xp(d, "(//*[@role='alertdialog']//button[normalize-space(.)='删除'])[last()]"))
            time.sleep(4)
            out['delete_requests'] = token_requests(d)
        goto(d, '/profile', 4)
        out['deleted_gone'] = name2 not in t(d)
        out['empty_state_or_remaining'] = t(d)[t(d).find('Access Token'):][:160].replace('\n', ' | ')
        gets = [x for x in token_requests(d) if x['m'] == 'GET']
        out['get_after_delete'] = gets[-1] if gets else None
        shot(d, 'token_list_after_delete')
    except Exception as e:
        out['delete_FAIL'] = traceback.format_exc()[-500:]

    # 清探针遗留 token
    try:
        body = t(d)
        leftovers = sorted(set(re.findall(PROBE_PREFIX + r'\d+', body)))
        out['probe_leftovers'] = leftovers
        for lname in leftovers:
            jsclick(d, xp(d, row_xpath(lname, "//button[@aria-label='删除 Access Token']"), 8))
            time.sleep(1.2)
            jsclick(d, xp(d, "(//*[@role='alertdialog']//button[normalize-space(.)='删除'])[last()]"))
            time.sleep(3)
        goto(d, '/profile', 4)
        out['probe_clean_after'] = [x for x in leftovers if x in t(d)]
    except Exception as e:
        out['probe_cleanup_FAIL'] = traceback.format_exc()[-400:]

    rec('tokens', out)


# ------------------------------------------------------------------ register
def section_register(d):
    out = {}
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank'); time.sleep(0.4)
    goto(d, '/register', 3)
    out['url'] = d.current_url
    out['form_visible'] = len(d.find_elements(By.ID, 'register-username')) > 0
    if not out['form_visible']:
        rec('register', out)
        return
    shot(d, 'register_light')
    submit = "//form//button[@type='submit']"
    jsclick(d, xp(d, submit)); time.sleep(1.2)
    out['empty_errors'] = [e.text for e in d.find_elements(By.XPATH, "//p[contains(@class,'text-destructive')]")]
    # 非法邮箱 + 密码不一致
    d.find_element(By.ID, 'register-username').send_keys(f'接线测试_reg_{SUFFIX}')
    d.find_element(By.ID, 'register-email').send_keys('not-an-email')
    d.find_element(By.ID, 'register-password').send_keys('123')
    d.find_element(By.ID, 'register-confirm').send_keys('456')
    jsclick(d, xp(d, submit)); time.sleep(1.2)
    out['invalid_errors'] = [e.text for e in d.find_elements(By.XPATH, "//p[contains(@class,'text-destructive')]")]
    # 重复用户名
    for fid, val in (('register-username', USER), ('register-email', f'dup_{SUFFIX}@example.com'),
                     ('register-password', 'TestPass@2026'), ('register-confirm', 'TestPass@2026')):
        el = d.find_element(By.ID, fid); el.send_keys(Keys.CONTROL, 'a'); el.send_keys(Keys.DELETE); el.send_keys(val)
    clr(d)
    jsclick(d, xp(d, submit)); time.sleep(5)
    out['dup_toasts'] = toasts(d)
    out['dup_url'] = d.current_url
    out['dup_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                            'res': (e.get('resBody') or '')[:200]} for e in lg(d) if '/auth/register' in e.get('url', '')]
    shot(d, 'register_duplicate')
    # 真实注册
    new_user = f'接线测试_reg_{SUFFIX}'
    for fid, val in (('register-username', new_user), ('register-email', f'reg_{SUFFIX}@example.com'),
                     ('register-password', 'TestPass@2026'), ('register-confirm', 'TestPass@2026')):
        el = d.find_element(By.ID, fid); el.send_keys(Keys.CONTROL, 'a'); el.send_keys(Keys.DELETE); el.send_keys(val)
    clr(d)
    jsclick(d, xp(d, submit)); time.sleep(6)
    out['success_url'] = d.current_url
    out['success_toasts'] = toasts(d)
    out['success_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                'res': (e.get('resBody') or '')[:200]} for e in lg(d) if '/auth/register' in e.get('url', '')]
    try:
        out['prefill_username'] = d.find_element(By.ID, 'username').get_attribute('value')
    except Exception:
        out['prefill_username'] = None
    shot(d, 'register_success')
    out['new_user'] = new_user
    rec('register', out)
    return new_user


def cleanup_user(name):
    try:
        users = json.loads(urllib.request.urlopen(API + '/auth/users?page=1&page_size=200', timeout=20).read())['data']['items']
        hits = [u for u in users if u['username'] == name]
        res = []
        for u in hits:
            req = urllib.request.Request(f"{API}/auth/users/{u['id']}", method='DELETE')
            with urllib.request.urlopen(req, timeout=20) as r:
                res.append({'id': u['id'], 'status': r.status})
        return res
    except Exception as e:
        return {'error': str(e)}


def main():
    os.makedirs(ART, exist_ok=True)
    d = drv()
    new_user = None
    try:
        try:
            section_tokens(d)
        except Exception:
            rec('tokens_fatal', traceback.format_exc()[-800:])
        try:
            new_user = section_register(d)
        except Exception:
            rec('register_fatal', traceback.format_exc()[-800:])
    finally:
        d.quit()
        if new_user:
            R['cleanup_user'] = cleanup_user(new_user)
        with open(f'{ART}/round3_result.json', 'w', encoding='utf-8') as f:
            json.dump({'suffix': SUFFIX, 'results': R}, f, ensure_ascii=False, indent=2)
        print('DONE')


if __name__ == '__main__':
    main()
