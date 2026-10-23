# -*- coding: utf-8 -*-
"""INT-1489 第四轮：Access Token 编辑/启停/取消/删除闭环 + 注册真实流程（修正轮）。

修正：绝对 URL 导航；每步独立 try；器件级证据写入。
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
    print(f'[{k}]', json.dumps(v, ensure_ascii=False)[:1500])


def step(name, fn, sink):
    try:
        sink[name] = fn()
    except Exception:
        sink[name] = {'FAIL': traceback.format_exc()[-400:]}
        print(f'[{name}] FAIL', traceback.format_exc()[-400:])


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


def goto(d, p, s=3.5):
    d.get(BASE + p)
    WebDriverWait(d, 30).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(s)


def jsclick(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def xp(d, e, t_=15):
    return WebDriverWait(d, t_).until(EC.presence_of_element_located((By.XPATH, e)))


def lg(d):
    try:
        return d.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []


def clr(d):
    d.execute_script('window.__fetchLog = [];')


def reqs(d):
    out = []
    for e in lg(d):
        if '/access-tokens' not in e.get('url', ''):
            continue
        i = {'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status')}
        if e.get('reqBody'):
            try:
                i['req'] = json.loads(e['reqBody'])
            except Exception:
                i['req'] = e['reqBody'][:150]
        if e.get('resBody'):
            try:
                i['res'] = json.loads(e['resBody']).get('data')
            except Exception:
                pass
        out.append(i)
    return out


def row(name, inner):
    return f"//p[normalize-space(.)='{name}']/ancestor::div[contains(@class,'py-3')][1]{inner}"


def login(d):
    goto(d, '/login', 2)
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


def main():
    os.makedirs(ART, exist_ok=True)
    d = drv()
    out = {}
    try:
        out['login_url'] = login(d)
        goto(d, '/profile', 5)
        out['profile_url'] = d.current_url
        body = t(d)
        mine = sorted(set(re.findall(r'接线测试_token_[A-Za-z0-9_]+', body)))
        out['existing_test_tokens'] = mine
        shot(d, 'profile_before')

        target = None
        for n in mine:
            if re.match(r'^接线测试_token_\d+$', n):
                target = n
                break
        if not target and mine:
            target = mine[0]
        out['target'] = target

        # -------- 编辑 --------
        if target:
            def do_edit():
                r = {}
                jsclick(d, xp(d, row(target, "//button[@aria-label='编辑 Access Token']")))
                time.sleep(1.5)
                edit = d.find_element(By.XPATH, "//*[@role='dialog']")
                r['title'] = edit.find_element(By.XPATH, './/h2').text
                en = edit.find_element(By.ID, 'access-token-edit-name')
                r['prefill_name'] = en.get_attribute('value')
                r['prefill_expiry'] = edit.find_element(By.ID, 'access-token-edit-expiry').text
                r['scope_hint'] = [e.text for e in edit.find_elements(By.XPATH, ".//span[contains(., '已选') and contains(., '项')]")]
                # 空名称校验
                en.send_keys(Keys.CONTROL, 'a'); en.send_keys(Keys.DELETE)
                jsclick(d, edit.find_element(By.XPATH, ".//button[@type='submit']"))
                time.sleep(1.2)
                r['empty_name_error'] = [e.text for e in edit.find_elements(By.XPATH, ".//p[contains(@class,'text-destructive')]")]
                shot(d, 'token_edit_validation')
                new_name = target + '_改名'
                en.send_keys(new_name)
                clr(d)
                jsclick(d, edit.find_element(By.XPATH, ".//button[@type='submit']"))
                time.sleep(4)
                r['requests'] = reqs(d)
                r['dialog_closed'] = len(d.find_elements(By.XPATH, "//*[@role='dialog']")) == 0
                goto(d, '/profile', 4)
                r['list_has_renamed'] = new_name in t(d)
                gets = [x for x in reqs(d) if x['m'] == 'GET']
                r['get_readback'] = gets[-1] if gets else None
                return {'out': r, 'new_name': new_name}
            res = {}
            step('edit', do_edit, res)
            out['edit'] = res.get('edit')
            if isinstance(out['edit'], dict) and 'out' in out['edit']:
                out['edit'] = out['edit']['out']
                target = out['edit'].get('new_name') or target
                out['target_after_edit'] = target

        # -------- 启停 --------
        def do_toggle():
            r = {}
            clr(d)
            sw = xp(d, row(target, "//*[@data-slot='switch' or @role='switch']"))
            r['switch_aria_before'] = sw.get_attribute('aria-label')
            jsclick(d, sw)
            time.sleep(4)
            r['disable_requests'] = reqs(d)
            goto(d, '/profile', 4)
            r['disabled_badge'] = '已停用' in t(d)
            clr(d)
            sw2 = xp(d, row(target, "//*[@data-slot='switch' or @role='switch']"))
            r['switch_aria_after'] = sw2.get_attribute('aria-label')
            jsclick(d, sw2)
            time.sleep(4)
            r['enable_requests'] = reqs(d)
            goto(d, '/profile', 4)
            r['enabled_badge'] = '已启用' in t(d)
            shot(d, 'token_after_toggle')
            return r
        res = {}
        step('toggle', do_toggle, res)
        out['toggle'] = res.get('toggle')

        # -------- 取消与重开 --------
        def do_cancel():
            r = {}
            jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
            time.sleep(1.2)
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)
            r['esc_closes'] = len(d.find_elements(By.ID, 'access-token-name')) == 0
            jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
            time.sleep(1.2)
            el = xp(d, "//input[@id='access-token-name']")
            el.send_keys('临时残留检查')
            overlays = d.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-overlay"]')
            r['overlay_found'] = len(overlays)
            if overlays:
                jsclick(d, overlays[0])
                time.sleep(1.2)
            r['overlay_closes'] = len(d.find_elements(By.ID, 'access-token-name')) == 0
            if not r['overlay_closes']:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)
            jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
            time.sleep(1.2)
            r['reopen_name'] = xp(d, "//input[@id='access-token-name']").get_attribute('value')
            jsclick(d, xp(d, "//*[@role='dialog']//button[normalize-space(.)='取消']"))
            time.sleep(1)
            r['cancel_btn_closes'] = len(d.find_elements(By.ID, 'access-token-name')) == 0
            return r
        res = {}
        step('cancel', do_cancel, res)
        out['cancel'] = res.get('cancel')

        # -------- 深色截图 --------
        def do_dark():
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
            d.get('about:blank'); time.sleep(0.5)
            goto(d, '/profile', 4)
            shot(d, 'profile_dark_round4')
            jsclick(d, xp(d, "//button[@aria-label='创建新的 Access Token']"))
            time.sleep(1.5)
            shot(d, 'token_create_dark_round4')
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
            d.get('about:blank'); time.sleep(0.5)
            goto(d, '/profile', 4)
            return True
        res = {}
        step('dark', do_dark, res)
        out['dark'] = res.get('dark')

        # -------- 删除（清理所有接线测试 token） --------
        def do_delete():
            r = {}
            goto(d, '/profile', 4)
            names = sorted(set(re.findall(r'接线测试_token_[A-Za-z0-9_]+', t(d))), reverse=True)
            r['to_delete'] = names
            deleted = []
            for n in names:
                try:
                    clr(d)
                    jsclick(d, xp(d, row(n, "//button[@aria-label='删除 Access Token']"), 8))
                    time.sleep(1.2)
                    if not deleted:
                        r['confirm_text'] = ' '.join(
                            x.text[:250].replace('\n', ' ') for x in d.find_elements(By.XPATH, "//*[@role='alertdialog' or @role='dialog']"))
                    jsclick(d, xp(d, "(//*[@role='alertdialog']//button[normalize-space(.)='删除'])[last()] | (//*[@role='dialog']//button[normalize-space(.)='删除'])[last()]"))
                    time.sleep(3)
                    if not deleted:
                        r['delete_requests'] = reqs(d)
                    deleted.append(n)
                except Exception:
                    r.setdefault('delete_fail', []).append({'name': n, 'tb': traceback.format_exc()[-200:]})
            goto(d, '/profile', 4)
            r['remaining'] = sorted(set(re.findall(r'接线测试_token_[A-Za-z0-9_]+', t(d))))
            gets = [x for x in reqs(d) if x['m'] == 'GET']
            r['get_after_delete'] = gets[-1] if gets else None
            shot(d, 'token_list_final')
            return r
        res = {}
        step('delete', do_delete, res)
        out['delete'] = res.get('delete')

        # -------- 注册 --------
        def do_register():
            r = {}
            goto(d, '/login', 2)
            d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
            d.get('about:blank'); time.sleep(0.4)
            goto(d, '/register', 3)
            r['url'] = d.current_url
            r['form_visible'] = len(d.find_elements(By.ID, 'register-username')) > 0
            if not r['form_visible']:
                return r
            shot(d, 'register_light')
            sub = xp(d, "//form//button[@type='submit']")
            jsclick(d, sub); time.sleep(1.2)
            r['empty_errors'] = [e.text for e in d.find_elements(By.XPATH, "//p[contains(@class,'text-destructive')]")]
            d.find_element(By.ID, 'register-username').send_keys(f'接线测试_reg_{SUFFIX}')
            d.find_element(By.ID, 'register-email').send_keys('bad-email')
            d.find_element(By.ID, 'register-password').send_keys('123')
            d.find_element(By.ID, 'register-confirm').send_keys('456')
            jsclick(d, sub); time.sleep(1.2)
            r['invalid_errors'] = [e.text for e in d.find_elements(By.XPATH, "//p[contains(@class,'text-destructive')]")]
            # 重复用户名
            for fid, val in (('register-username', USER), ('register-email', f'dup_{SUFFIX}@example.com'),
                             ('register-password', 'TestPass@2026'), ('register-confirm', 'TestPass@2026')):
                el = d.find_element(By.ID, fid); el.send_keys(Keys.CONTROL, 'a'); el.send_keys(Keys.DELETE); el.send_keys(val)
            clr(d)
            jsclick(d, sub); time.sleep(5)
            r['dup_toasts'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
            r['dup_url'] = d.current_url
            r['dup_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                  'res': (e.get('resBody') or '')[:220]} for e in lg(d) if '/auth/register' in e.get('url', '')]
            shot(d, 'register_duplicate')
            # 真实注册
            new_user = f'接线测试_reg_{SUFFIX}'
            for fid, val in (('register-username', new_user), ('register-email', f'reg_{SUFFIX}@example.com'),
                             ('register-password', 'TestPass@2026'), ('register-confirm', 'TestPass@2026')):
                el = d.find_element(By.ID, fid); el.send_keys(Keys.CONTROL, 'a'); el.send_keys(Keys.DELETE); el.send_keys(val)
            clr(d)
            jsclick(d, sub); time.sleep(6)
            r['success_url'] = d.current_url
            r['success_toasts'] = [e.text for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
            r['success_requests'] = [{'m': e.get('method'), 'u': e.get('url', '').split(BASE)[-1], 's': e.get('status'),
                                      'res': (e.get('resBody') or '')[:220]} for e in lg(d) if '/auth/register' in e.get('url', '')]
            try:
                r['prefill_username'] = d.find_element(By.ID, 'username').get_attribute('value')
            except Exception:
                r['prefill_username'] = None
            shot(d, 'register_success')
            r['new_user'] = new_user
            return r
        res = {}
        step('register', do_register, res)
        out['register'] = res.get('register')
        new_user = None
        if isinstance(out['register'], dict):
            new_user = out['register'].get('new_user')
        if new_user:
            try:
                users = json.loads(urllib.request.urlopen(API + '/auth/users?page=1&page_size=200', timeout=20).read())['data']['items']
                hits = [u for u in users if u['username'] == new_user]
                out['cleanup_user'] = []
                for u in hits:
                    req = urllib.request.Request(f"{API}/auth/users/{u['id']}", method='DELETE')
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        out['cleanup_user'].append({'id': u['id'], 'status': resp.status})
            except Exception as e:
                out['cleanup_user'] = {'error': str(e)}

        rec('round4', out)
    finally:
        d.quit()
        with open(f'{ART}/round4_result.json', 'w', encoding='utf-8') as f:
            json.dump({'suffix': SUFFIX, 'results': R}, f, ensure_ascii=False, indent=2)
        print('DONE')


if __name__ == '__main__':
    main()
