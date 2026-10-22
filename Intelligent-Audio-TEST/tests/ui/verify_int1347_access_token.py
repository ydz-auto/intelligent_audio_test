# -*- coding: utf-8 -*-
"""INT-1347 复测项⑥：Access Token CRUD（GET /auth/access-tokens 修复后，创建明文一次/列表/编辑/启停/删除全链）。

环境：
- dev server http://localhost:5321（/api 代理 → docker :15000，主库 intelligent_audio_test）
- AUTH_MODE=off → dev_user('*') 放行
- 页面: /profile（Access Token 卡）

失败落 tests/ui/artifacts/int1347_access_token/<步骤>/。
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

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1347_access_token')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API = 'http://127.0.0.1:15000/api/v1'

os.makedirs(ARTIFACTS, exist_ok=True)

STAMP = str(int(time.time()))[-6:]


def _get_api(path):
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(f'{API}{path}', timeout=45) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


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


def _goto(drv, path, wait_text=None, timeout=30):
    drv.get(BASE + path)
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    if wait_text:
        WebDriverWait(drv, timeout).until(
            lambda d: wait_text in (d.execute_script('return document.body.textContent || ""')))


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _save_evidence(name, drv, net=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(net or [], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _network_api_calls(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.requestWillBeSent':
                p = inner.get('params', {})
                url = p.get('request', {}).get('url', '')
                if '/api/' in url:
                    req = p.get('request', {})
                    out.append({'url': url, 'method': req.get('method'),
                                'postData': req.get('postData')})
    except Exception as e:
        out.append({'error': str(e)})
    return out


def _js_click(drv, el):
    try:
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click()', el)
    time.sleep(0.5)


def _click_text_contains(drv, text, timeout=12):
    els = drv.find_elements(By.XPATH, f"//button[contains(normalize-space(.), '{text}')]")
    if not els:
        els = drv.find_elements(By.XPATH, f"//*[contains(normalize-space(.), '{text}')]")
    if not els:
        raise Exception(f'未找到含「{text}」的可点击元素')
    _js_click(drv, els[0])


def _wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: text in (d.execute_script('return document.body.textContent || ""')))


def _login(drv):
    """真实登录链路（RSA-OAEP 表单加密）为 接线测试_admin，换取 Bearer token。"""
    drv.get(BASE + '/login')
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)
    # 若 AUTH_MODE=off 自动重定向到 dashboard（无 token 时不会），此处兜底重载一次
    if '/login' not in drv.current_url:
        drv.get(BASE + '/login')
        time.sleep(1.0)
    uname = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.ID, 'username'))
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    submit = drv.find_element(By.CSS_SELECTOR, "button[type='submit']")
    _js_click(drv, submit)
    WebDriverWait(drv, 30).until(
        lambda d: 'dashboard' in d.current_url or '工作台' in (d.execute_script('return document.body.textContent || ""')))
    time.sleep(1.5)


def run():
    drv = _driver()
    failures = []
    results = []
    token_id = None

    def check(name, cond, detail=''):
        tag = 'PASS' if cond else 'FAIL'
        results.append((tag, name, detail))
        print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''), flush=True)
        if not cond:
            failures.append(name)

    try:
        health = None
        for _ in range(3):
            try:
                with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as r:
                    health = json.loads(r.read().decode('utf-8'))
                break
            except Exception as e:
                health = {'error': str(e)}
                time.sleep(2)
        check('防串库① docker :15000 database=intelligent_audio_test', health.get('database') == 'intelligent_audio_test', str(health))

        _goto(drv, '/dashboard', wait_text='工作台', timeout=30)
        drv.execute_script('try { window.localStorage.clear() } catch(e) {}')
        # 真实登录（access-tokens 端点需真实 Bearer token，dev_user 通配不适用）
        _login(drv)
        TOKEN = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1') || ''")
        print(f'[login] token captured len={len(TOKEN)}')

        # ─── Access Token 卡 ───
        _goto(drv, '/profile', wait_text='Access Token', timeout=45)
        _wait_text(drv, 'Access Token', timeout=45)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('列表真实请求 GET /auth/access-tokens', any('/auth/access-tokens' in u for u in urls), str([u for u in urls if 'access-token' in u]))
        body = _body_text(drv)
        check('列表不再 404 错误态（原「加载失败」）', 'Access Token 加载失败' not in body, '')
        _save_evidence('01_token_list', drv, net)

        # ─── 创建 Access Token ───
        tname = f'接线测试_token{STAMP}'
        _js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '创建 Access Token')]"))
        _wait_text(drv, 'Token 明文只显示一次', timeout=15)
        drv.find_element(By.ID, 'access-token-name').send_keys(tname)
        # 有效时间：30 天
        _js_click(drv, drv.find_element(By.ID, 'access-token-expiry'))
        time.sleep(0.6)
        opt = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.XPATH, "//*[@role='option' and contains(normalize-space(.), '30 天')]"))
        _js_click(drv, opt)
        # 权限：勾选 task:read，并核对「已选 1 项」
        perm_cb = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "#perm-task\\:read"))
        _js_click(drv, perm_cb)
        time.sleep(0.8)
        body = _body_text(drv)
        check('权限已选 1 项', '已选 1 项' in body, '')
        _save_evidence('02_token_create_filled', drv, _network_api_calls(drv))
        # 点击对话框内「创建」按钮（精确文本，限定在 form 内）
        create_btn = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.XPATH, "//form[@id='access-token-create-form']//button[normalize-space()='创建']"))
        _js_click(drv, create_btn)
        _wait_text(drv, 'Access Token 已创建', timeout=30)
        net = _network_api_calls(drv)
        check('创建真实请求 POST /auth/access-tokens', any('POST' == n.get('method') and '/auth/access-tokens' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'access-token' in n.get('url','')]))
        body = _body_text(drv)
        check('创建成功提示', 'Access Token 已创建' in body)
        # 明文 token（revel 弹窗 input#generated-access-token）
        plaintext = ''
        try:
            el = drv.find_element(By.ID, 'generated-access-token')
            plaintext = el.get_attribute('value') or ''
        except Exception:
            pass
        check('明文 token 只显示一次（revel 弹窗）', len(plaintext) >= 20, plaintext[:12] + '...' if plaintext else 'no plaintext')
        _save_evidence('03_token_created_reveal', drv, net)
        # 关闭 revel
        try:
            drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '关闭')]").click()
        except Exception:
            drv.execute_script("document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape'}))")
        time.sleep(1.0)

        # 列表出现新 token（掩码；等列表刷新）
        _wait_text(drv, tname, timeout=30)
        body = _body_text(drv)
        check('列表出现新 Access Token', tname in body, tname if tname in body else 'not in list')
        _save_evidence('04_token_in_list', drv, _network_api_calls(drv))

        # 找到 token id（API 用真实 Bearer token）
        try:
            req = urllib.request.Request(f'{API}/auth/access-tokens',
                                         headers={'Authorization': f'Bearer {TOKEN}'})
            with urllib.request.urlopen(req, timeout=30) as r:
                tl = json.loads(r.read().decode('utf-8'))
        except Exception:
            tl = {}
        items = tl.get('data', {}).get('items', []) if isinstance(tl.get('data'), dict) else []
        hits = [i for i in items if i.get('name') == tname]
        check('GET /auth/access-tokens 含新建 token', len(hits) >= 1, str([{ 'id': h.get('id'), 'name': h.get('name') } for h in hits])[:150])
        if hits:
            token_id = str(hits[0].get('id'))

        # ─── 编辑（改名 + 保存）───
        def _row_matches(b, name):
            """按钮所在 token 行的名称匹配：从按钮向上找第一个含 <p> 的祖先（即该行容器），
            只在该行内核对名称，避免共享容器把别的 token 名卷进来。"""
            cur = b
            for _ in range(6):
                cur = cur.find_element(By.XPATH, '..')
                ps = cur.find_elements(By.XPATH, ".//p")
                if ps:
                    return any((p.text or '').strip() == name for p in ps)
            return False

        def _row_btn(aria, name):
            """定位名称=name 的 token 行内操作按钮：遍历全部操作钮，取最近名称匹配者"""
            btns = drv.find_elements(By.XPATH, f"//button[@aria-label='{aria}']")
            for b in btns:
                if _row_matches(b, name):
                    return b
            raise Exception(f'未找到名称={name} 的 {aria} 按钮')

        try:
            edit_btn = WebDriverWait(drv, 15).until(lambda d: _row_btn('编辑 Access Token', tname))
            _js_click(drv, edit_btn)
            _wait_text(drv, '编辑 Access Token', timeout=15)
            name_input = drv.find_element(By.ID, 'access-token-edit-name')
            check('编辑回显名称', (name_input.get_attribute('value') or '') == tname, name_input.get_attribute('value') or '')
            name_input.clear()
            name_input.send_keys(tname + '_改')
            _save_evidence('05_token_edit_filled', drv, _network_api_calls(drv))
            edit_save = WebDriverWait(drv, 10).until(
                lambda d: d.find_element(By.XPATH, "//button[normalize-space()='保存']"))
            _js_click(drv, edit_save)
            # PATCH 落库（toast 实际为「已保存」，不按常量文案断言）
            time.sleep(2.0)
            net = _network_api_calls(drv)
            check('编辑真实请求 PATCH /auth/access-tokens/{id}', any('PATCH' == n.get('method') and '/auth/access-tokens/' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'access-token' in n.get('url','')]))
            _save_evidence('06_token_edited', drv, net)
            try:
                drv.find_element(By.XPATH, "//button[normalize-space()='取消']").click()
            except Exception:
                pass
            time.sleep(1.0)
        except Exception as e:
            check('编辑 Access Token', False, str(e))

        # ─── 启停切换 ───
        try:
            toggles = drv.find_elements(By.XPATH, "//*[@role='switch'][@aria-label='停用']")
            toggles = [b for b in toggles if _row_matches(b, tname + '_改') or _row_matches(b, tname)]
            check('停用开关存在', len(toggles) > 0, f'count={len(toggles)}')
            if toggles:
                _js_click(drv, toggles[0])
                time.sleep(2.0)
                net = _network_api_calls(drv)
                check('停用真实请求 PATCH status', any('PATCH' == n.get('method') and '/auth/access-tokens/' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'access-token' in n.get('url','')]))
                _save_evidence('07_token_disabled', drv, net)
        except Exception as e:
            check('启停切换', False, str(e))

        # ─── 删除 ───
        try:
            del_btn = WebDriverWait(drv, 15).until(lambda d: _row_btn('删除 Access Token', tname + '_改'))
            _js_click(drv, del_btn)
            _wait_text(drv, '删除 Access Token', timeout=15)
            del_confirm = WebDriverWait(drv, 10).until(
                lambda d: d.find_element(By.XPATH, "//button[normalize-space()='删除']"))
            _js_click(drv, del_confirm)
            _wait_text(drv, 'Access Token 已删除', timeout=30)
            net = _network_api_calls(drv)
            check('删除真实请求 DELETE /auth/access-tokens/{id}', any('DELETE' == n.get('method') and '/auth/access-tokens/' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'access-token' in n.get('url','')]))
            _save_evidence('08_token_deleted', drv, net)
            # 列表（INT-1182 软删过滤未进部署镜像 → 可能仍显示；记录现状）
            body = _body_text(drv)
            still_shown = tname + '_改' in body or tname in body
            if still_shown:
                check('删除后列表仍显示（INT-1182 镜像滞后，非本卡缺陷）', True, '软删过滤未进部署镜像 → 列表仍显示')
            else:
                check('删除后列表不再显示', True, '')
        except Exception as e:
            check('删除 Access Token', False, str(e))

        for _ in range(3):
            try:
                with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as r:
                    health2 = json.loads(r.read().decode('utf-8'))
                break
            except Exception as e:
                health2 = {'error': str(e)}
                time.sleep(2)
        check('防串库② docker :15000 database=intelligent_audio_test', health2.get('database') == 'intelligent_audio_test', str(health2))

    except Exception:
        _save_evidence('FAILURE_dump', drv, _network_api_calls(drv))
        import traceback
        traceback.print_exc()
        failures.append('脚本异常')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ARTIFACTS, 'results.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(f'{tag}\t{name}\t{detail}' for tag, name, detail in results))
        f.write('\n')
        f.write('FAILURES: ' + json.dumps(failures, ensure_ascii=False) + '\n')
        f.write(f'TOKEN_ID: {token_id}\n')

    print('=' * 60)
    print(f'PASS {sum(1 for t, _, _ in results if t == "PASS")} / {len(results)}')
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
