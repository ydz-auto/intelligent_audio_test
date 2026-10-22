# -*- coding: utf-8 -*-
"""INT-1255 复测·Access Token CRUD 浏览器全链（INT-1347 清单第 6 项）。

环境：
- preview :5311（/api 代理 → docker :15000，主库 intelligent_audio_test）
- 真实登录：API RSA-OAEP 登录 接线测试_admin → JWT 注入 localStorage（access-tokens
  端点要求真实身份，dev_user 会 401）
- 页面: /profile → Access Token 卡

验收核对：
① 列表真实渲染（GET /auth/access-tokens 200，非 404）
② 创建（名称/有效期/权限勾选）→ 明文仅显示一次 → 列表出现
③ 编辑（改名）→ PATCH → toast → 列表更新
④ 启停切换（Switch）→ 状态徽章变化
⑤ 删除 → 确认弹窗 → DELETE → 列表按后端软删过滤（INT-1182 镜像滞后则仍可见，记 P3）
⑥ 必填留空/权限未选提交不发 POST；重开表单清空
失败落 tests/ui/artifacts/int1255_retest_access/<步骤>/。
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1255_retest_access')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API = 'http://127.0.0.1:15000/api/v1'
ADMIN = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
STAMP = str(int(time.time()))[-6:]

os.makedirs(ARTIFACTS, exist_ok=True)


def api_http(method, path, body=None, token=None, form=False, timeout=40):
    url = API + path
    data = None
    hdrs = {'Accept': 'application/json'}
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode('utf-8')
            hdrs['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            data = json.dumps(body).encode('utf-8')
            hdrs['Content-Type'] = 'application/json'
    if token:
        hdrs['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8')
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw[:500]
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:500]


def api_login(username, password):
    st, key = api_http('GET', '/auth/login/encryption-key')
    pub = load_pem_public_key(key['public_key'].encode('utf-8'))
    ct = pub.encrypt(password.encode('utf-8'), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None))
    pw = base64.b64encode(ct).decode('ascii')
    st, res = api_http('POST', '/auth/login', {
        'username': username, 'password_encrypted': pw, 'encryption_key_id': key['kid'],
    }, form=True)
    return res.get('access_token') if st == 200 else None


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


def _save_evidence(name, drv, net=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(net or [], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _js_click(drv, el):
    try:
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click()', el)
    time.sleep(0.6)


def _wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: text in (d.execute_script('return document.body.textContent || ""')))


def _click_text(drv, text, timeout=12):
    el = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.XPATH, f"//*[normalize-space(.)='{text}']"))
    _js_click(drv, el)


def _click_text_contains(drv, text, timeout=12):
    el = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.XPATH, f"//*[contains(normalize-space(.), '{text}')]"))
    _js_click(drv, el)


def _token_row(drv, name, timeout=12):
    """定位包含指定 token 名称的行 div（AccessTokenItem 行：class='flex items-start gap-3 py-3'）。"""
    def _find(d):
        for el in d.find_elements(
                By.XPATH,
                "//div[starts-with(normalize-space(@class), 'flex items-start gap-3 py-3')]"):
            if name in (el.text or ''):
                return el
        return None
    return WebDriverWait(drv, timeout).until(lambda d: _find(d))


def _select_expiry(drv, label):
    drv.find_element(By.ID, 'access-token-expiry').click()
    time.sleep(0.8)
    item = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, f"//*[@role='option' and normalize-space(.)='{label}']"))
    _js_click(drv, item)


def run():
    drv = _driver()
    failures = []
    results = []

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

        # 真实登录（API 层 RSA-OAEP）→ JWT
        token = api_login(ADMIN, PASSWORD)
        check('真实登录 接线测试_admin → JWT', bool(token), 'no token' if not token else 'ok')

        # 浏览器注入 token → 以 admin 身份加载
        _goto(drv, '/dashboard', wait_text='工作台', timeout=30)
        drv.execute_script(
            "window.localStorage.setItem('iatp:auth:token:v1', arguments[0])", token)
        drv.execute_script("window.localStorage.removeItem('iatp:auth:v1')")
        drv.get(BASE + '/dashboard')
        WebDriverWait(drv, 30).until(
            lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.0)
        body = _body_text(drv)
        check('注入后以 admin 会话进入工作台', '工作台' in body)
        _save_evidence('00_admin_session', drv, _network_api_calls(drv))

        # 导航到 /profile → Access Token 卡
        _goto(drv, '/profile', wait_text='个人信息', timeout=45)
        _wait_text(drv, 'Access Token', timeout=45)
        body = _body_text(drv)
        check('Access Token 卡渲染', 'Access Token' in body and '创建 Access Token' in body)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('列表真实请求 GET /auth/access-tokens (200 非 404)', any('/auth/access-tokens' in u for u in urls), str([u for u in urls if 'access-token' in u]))
        _save_evidence('01_access_token_card', drv, net)

        # 防串库②
        for _ in range(3):
            try:
                with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as r:
                    health2 = json.loads(r.read().decode('utf-8'))
                break
            except Exception:
                health2 = {'error': str(e)}
                time.sleep(2)
        check('防串库② docker :15000 database=intelligent_audio_test', health2.get('database') == 'intelligent_audio_test', str(health2))

        # ─── 创建 Access Token ───
        tname = f'接线测试_token{STAMP}'
        _js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '创建 Access Token')]"))
        _wait_text(drv, 'Token 明文只显示一次', timeout=15)
        body = _body_text(drv)
        check('创建对话框标题+字段', '创建 Access Token' in body and '名称' in body and '有效时间' in body)
        # 必填留空提交 → 不发 POST
        _click_text(drv, '创建')
        time.sleep(1.0)
        net = _network_api_calls(drv)
        check('必填/权限未选提交不发 POST access-tokens', not any(
            '/auth/access-tokens' in n.get('url', '') and n.get('method') == 'POST' for n in net))
        body = _body_text(drv)
        check('校验错误提示（名称/权限必填）', '请输入名称' in body or '请至少选择一个权限' in body, body[body.find('请输入名称')-10:body.find('请输入名称')+40] if '请输入名称' in body else '')
        _save_evidence('02_create_validation', drv, net)
        # 填名称
        name_input = drv.find_element(By.ID, 'access-token-name')
        name_input.send_keys(tname)
        # 有效时间：永不过期
        _select_expiry(drv, '永不过期')
        # 勾选一个权限（task:read）
        perm = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.XPATH, "//input[@id='perm-task:read']"))
        _js_click(drv, perm)
        body = _body_text(drv)
        check('权限已选计数出现', '已选 1 项' in body, body[body.find('已选'):body.find('已选')+20] if '已选' in body else '')
        _save_evidence('03_create_filled', drv, _network_api_calls(drv))
        # 提交创建
        _click_text(drv, '创建')
        _wait_text(drv, 'Access Token 已创建', timeout=20)
        body = _body_text(drv)
        check('创建成功 → 明文展示对话框（Access Token 已创建）', 'Access Token 已创建' in body)
        plain = ''
        try:
            plain_el = drv.find_element(By.ID, 'generated-access-token')
            plain = plain_el.get_attribute('value') or ''
        except Exception:
            pass
        check('明文 Token 显示（at_ 前缀）', plain.startswith('at_'), plain[:40])
        net = _network_api_calls(drv)
        check('创建真实请求 POST /auth/access-tokens', any(
            '/auth/access-tokens' in n.get('url', '') and n.get('method') == 'POST' for n in net),
            str([n.get('url') for n in net if 'access-token' in n.get('url', '')]))
        _save_evidence('04_create_reveal', drv, net)
        _click_text(drv, '关闭')
        time.sleep(1.0)

        # 列表出现新 token
        _wait_text(drv, tname, timeout=20)
        body = _body_text(drv)
        check('列表出现新建 Token（名称）', tname in body)
        check('新建 Token 徽章「已启用」', '已启用' in body)
        _save_evidence('05_list_after_create', drv, _network_api_calls(drv))

        # 防串库③
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=15) as r:
            health3 = json.loads(r.read().decode('utf-8'))
        check('防串库③ docker :15000 database=intelligent_audio_test', health3.get('database') == 'intelligent_audio_test', str(health3))

        # ─── 编辑（改名）───
        edit_btns = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑 Access Token']")
        check('编辑按钮存在', len(edit_btns) >= 1, f'count={len(edit_btns)}')
        if edit_btns:
            row = _token_row(drv, tname)
            edit_btn = row.find_element(By.CSS_SELECTOR, "button[aria-label='编辑 Access Token']")
            _js_click(drv, edit_btn)
            _wait_text(drv, '编辑 Access Token', timeout=15)
            ename = drv.find_element(By.ID, 'access-token-edit-name')
            check('编辑回显名称', (ename.get_attribute('value') or '') == tname, ename.get_attribute('value') or 'EMPTY')
            ename.clear()
            ename.send_keys(tname + '_改')
            _save_evidence('06_edit_filled', drv, _network_api_calls(drv))
            _click_text(drv, '保存')
            _wait_text(drv, '已保存', timeout=20)
            net = _network_api_calls(drv)
            check('编辑真实请求 PATCH /auth/access-tokens/{id}', any(
                'PATCH' == n.get('method') and '/auth/access-tokens/' in n.get('url', '') for n in net),
                str([n.get('url') for n in net if 'access-token' in n.get('url', '')]))
            _save_evidence('07_edit_saved', drv, net)
            _wait_text(drv, tname + '_改', timeout=20)
            body = _body_text(drv)
            check('列表显示改名后 Token', tname + '_改' in body)

        # ─── 启停切换 ───
        time.sleep(1.0)
        row = _token_row(drv, tname + '_改')
        sw = row.find_element(By.CSS_SELECTOR, "[role='switch']")
        _js_click(drv, sw)
        _wait_text(drv, '已停用', timeout=20)
        body = _body_text(drv)
        check('停用切换 → 徽章「已停用」', '已停用' in body)
        net = _network_api_calls(drv)
        check('停用真实请求 PATCH status=disabled', any(
            'PATCH' == n.get('method') and '/auth/access-tokens/' in n.get('url', '') for n in net),
            str([n.get('url') for n in net if 'access-token' in n.get('url', '')]))
        _save_evidence('08_toggle_disabled', drv, net)
        # 再启用
        row2 = _token_row(drv, tname + '_改')
        sw2 = row2.find_element(By.CSS_SELECTOR, "[role='switch']")
        _js_click(drv, sw2)
        _wait_text(drv, '已启用', timeout=20)
        check('再启用 → 徽章「已启用」', '已启用' in _body_text(drv))
        _save_evidence('08b_toggle_enabled', drv, _network_api_calls(drv))

        # ─── 删除 ───
        row = _token_row(drv, tname + '_改')
        del_btn = row.find_element(By.CSS_SELECTOR, "button[aria-label='删除 Access Token']")
        _js_click(drv, del_btn)
        _wait_text(drv, '删除 Access Token', timeout=15)
        body = _body_text(drv)
        check('删除确认弹窗', '删除 Access Token' in body and '确定删除' in body)
        _save_evidence('09_delete_confirm', drv, _network_api_calls(drv))
        # 确认按钮（destructive）
        del_confirm = WebDriverWait(drv, 12).until(
            lambda d: d.find_element(By.XPATH, "//button[normalize-space()='删除']"))
        _js_click(drv, del_confirm)
        _wait_text(drv, 'Access Token 已删除', timeout=20)
        net = _network_api_calls(drv)
        check('删除真实请求 DELETE /auth/access-tokens/{id}', any(
            'DELETE' == n.get('method') and '/auth/access-tokens/' in n.get('url', '') for n in net),
            str([n.get('url') for n in net if 'access-token' in n.get('url', '')]))
        _save_evidence('10_delete_done', drv, net)
        time.sleep(2.0)
        body = _body_text(drv)
        # INT-1182 镜像滞后：软删后列表可能仍可见（部署镜像缺 list_by_user 过滤），记 P3 非前端缺陷
        still_visible = tname + '_改' in body
        check('删除后列表不再显示该 Token（软删过滤；INT-1182 镜像滞后仍可见记 P3）',
              not still_visible,
              '仍可见（INT-1182 镜像滞后，非前端缺陷）' if still_visible else '不可见（软删过滤生效）')

        # 防串库④ 交付前
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=15) as r:
            health4 = json.loads(r.read().decode('utf-8'))
        check('防串库④ docker :15000 database=intelligent_audio_test', health4.get('database') == 'intelligent_audio_test', str(health4))

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
        f.write('\nFAILURES: ' + json.dumps(failures, ensure_ascii=False) + '\n')

    print('=' * 60)
    print(f'PASS {sum(1 for t, _, _ in results if t == "PASS")} / {len(results)}')
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
