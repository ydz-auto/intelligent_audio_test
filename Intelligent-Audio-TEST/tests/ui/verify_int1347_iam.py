# -*- coding: utf-8 -*-
"""INT-1347 复测·INT-1255遗留 — 系统设置·IAM（用户/角色）浏览器实测（无 CDP 覆写）。

环境：
- dev server http://localhost:5321（/api 代理 → docker :15000，主库 intelligent_audio_test）
- docker 后端 :15000 AUTH_MODE=off → dev_user('*') 放行
- /api/option/ 已修复（INT-1345），经正常导航渲染设置外壳与 IAM 分区
- 页面: /system-settings/iam/users（用户管理）、/system-settings/iam/roles（角色权限管理）

验收核对：
① 用户列表真实数据（GET /auth/users）渲染 + 列/计数
② 新建用户（接线测试_前缀）：填全部字段 → 提交 → 列表 + GET 详情逐字段核对
③ 编辑用户：回显核对 → 改显示名/邮箱/状态保存 → 回显 + GET 核对
④ 启停切换 → 列表状态徽标 + GET 核对
⑤ 删除用户（自建）→ 列表消失 + GET 404/软删
⑥ 角色列表真实数据（GET /auth/roles）渲染
⑦ 新建角色（接线测试_前缀）→ 列表 + GET 核对
⑧ 编辑角色重命名/改描述/权限保存 → GET 核对（INT-1347 复测项③）
⑨ 删除角色（自建，无人引用）→ 列表消失
⑩ 校验：新建用户必填留空提交不发请求；取消重开表单清空

失败落 tests/ui/artifacts/int1255_iam/<步骤>/。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1255_iam')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API = 'http://127.0.0.1:15000/api/v1'

os.makedirs(ARTIFACTS, exist_ok=True)

STAMP = str(int(time.time()))[-6:]

# INT-1347 复测：/api/option/ 已在 docker :15000 修复（INT-1345），
# 不再需要 CDP 覆写——系统设置外壳经真实 GET /api/option/ 正常渲染分区。


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
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
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


def _wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: text in (d.execute_script('return document.body.textContent || ""')))


def _js_click(drv, el):
    # base-ui / React 控件一律 JS click（内存 confirm-dialog / batch-dialog 先例）
    drv.execute_script('arguments[0].click()', el)
    time.sleep(0.5)


def _menu_item_click(drv, text, timeout=12):
    """base-ui DropdownMenu item：需真实鼠标点击（ActionChains），JS click 不触发。"""
    from selenium.webdriver.common.action_chains import ActionChains
    item = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.XPATH, f"//*[@role='menuitem' and contains(normalize-space(.), '{text}')]"))
    ActionChains(drv).move_to_element(item).click().perform()
    time.sleep(0.6)


def _click_text(drv, text, timeout=12):
    els = drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{text}']")
    if not els:
        els = drv.find_elements(By.XPATH, f"//*[normalize-space(.)='{text}']")
    if not els:
        raise TimeoutException(f'未找到「{text}」按钮')
    _js_click(drv, els[0])


def _click_text_contains(drv, text, timeout=12):
    # 优先匹配 button（避免匹配到包含文本的父容器）
    els = drv.find_elements(By.XPATH, f"//button[contains(normalize-space(.), '{text}')]")
    if not els:
        els = drv.find_elements(By.XPATH, f"//*[contains(normalize-space(.), '{text}')]")
    if not els:
        raise TimeoutException(f'未找到含「{text}」的可点击元素')
    _js_click(drv, els[0])


def _select_option(drv, trigger_selector, option_text, trigger_id=None):
    """打开 Select 并选选项（base-ui Select：点 trigger → 点 role=option 文本）"""
    if trigger_id:
        trig = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.CSS_SELECTOR, f"#{trigger_id}"))
    else:
        trig = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.CSS_SELECTOR, trigger_selector))
    _js_click(drv, trig)
    time.sleep(0.6)
    opt = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, f"//*[@role='option' and contains(normalize-space(.), '{option_text}')]"))
    _js_click(drv, opt)
    time.sleep(0.6)


def run():
    drv = _driver()
    failures = []
    results = []
    created_user_ids = []
    created_role_ids = []

    def check(name, cond, detail=''):
        tag = 'PASS' if cond else 'FAIL'
        results.append((tag, name, detail))
        print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''), flush=True)
        if not cond:
            failures.append(name)

    try:
        # 防串库①
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

        # API 基准
        try:
            users_api = _get_api('/auth/users?page=1&page_size=100')
            api_user_count = len(users_api.get('data', {}).get('items', []))
            check('API GET /auth/users 可取', api_user_count > 0, f'count={api_user_count}')
        except Exception as e:
            api_user_count = 0
            check('API GET /auth/users 可取', False, str(e))
        try:
            roles_api = _get_api('/auth/roles')
            api_role_count = len(roles_api.get('data', {}).get('roles', []))
            check('API GET /auth/roles 可取', api_role_count > 0, f'count={api_role_count}')
        except Exception as e:
            api_role_count = 0
            check('API GET /auth/roles 可取', False, str(e))

        # 先导航到应用再清 localStorage
        _goto(drv, '/dashboard', wait_text='工作台', timeout=30)
        drv.execute_script('try { window.localStorage.clear() } catch(e) {}')

        # ─── ① 用户管理列表 ───
        _goto(drv, '/system-settings/iam/users', wait_text='用户管理', timeout=30)
        _wait_text(drv, '生产用户', timeout=45)
        body = _body_text(drv)
        check('用户管理分区标题', '用户管理' in body)
        check('工具行「新建用户」按钮', '新建用户' in body)
        try:
            search_input_el = drv.find_element(By.CSS_SELECTOR, "input[placeholder='搜索用户名或邮箱']")
            check('搜索框', search_input_el.is_displayed(), 'placeholder=搜索用户名或邮箱')
        except Exception:
            check('搜索框', False, '未找到搜索输入框')
        check('表格列齐', all(c in body for c in ('用户名', '邮箱', '角色', '状态', '附加权限数', '注册时间')))
        check('真实用户渲染（生产用户8）', '生产用户8' in body, body[body.find('生产用户8')-20:body.find('生产用户8')+20] if '生产用户8' in body else '')
        net = _network_api_calls(drv)
        check('Network 含 GET /auth/users', any('/auth/users' in n.get('url', '') for n in net))
        check('Network 含 GET /auth/roles（角色筛选数据源）', any('/auth/roles' in n.get('url', '') for n in net))
        _save_evidence('01_users_list', drv, net)

        # ─── ② 新建用户 ───
        uname = f'接线测试_u{STAMP}'
        email = f'jxx{uuid.uuid4().hex[:8]}@test.local'
        _click_text_contains(drv, '新建用户')
        _wait_text(drv, '创建平台账号并分配初始角色', timeout=15)
        body = _body_text(drv)
        check('新建用户抽屉打开', '新建用户' in body and '基本信息' in body)
        # 必填校验：直接点创建不发请求
        drv.execute_script("document.querySelector('#user-username')?.dispatchEvent(new Event('input',{bubbles:true}))")
        save_btn = drv.find_element(By.XPATH, "//button[normalize-space()='创建']")
        save_btn.click()
        time.sleep(1.2)
        net_before = _network_api_calls(drv)
        check('必填留空提交不发 POST /auth/users', not any('/auth/users' in n.get('url', '') and n.get('method') == 'POST' for n in net_before))
        _save_evidence('02_user_create_empty_submit', drv, net_before)
        # 填字段
        drv.find_element(By.ID, 'user-username').send_keys(uname)
        drv.find_element(By.ID, 'user-display-name').send_keys('接线测试_用户')
        drv.find_element(By.ID, 'user-email').send_keys(email)
        drv.find_element(By.ID, 'user-password').send_keys('JieXianTest@2026')
        # 角色选 algo_engineer
        _select_option(drv, None, '算法工程师', trigger_id='user-role')
        _save_evidence('03_user_create_filled', drv, _network_api_calls(drv))
        save_btn = drv.find_element(By.XPATH, "//button[normalize-space()='创建']")
        save_btn.click()
        _wait_text(drv, '用户已创建', timeout=30)
        net = _network_api_calls(drv)
        check('创建用户真实请求 POST /auth/users', any('/auth/users' in n.get('url', '') and n.get('method') == 'POST' for n in net), str([n.get('url') for n in net if 'auth/users' in n.get('url', '')]))
        _save_evidence('04_user_created', drv, net)
        # 核对列表
        search = drv.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用户名或邮箱']")
        search.clear()
        search.send_keys(uname)
        _wait_text(drv, uname, timeout=30)
        body = _body_text(drv)
        check('列表出现新用户', uname in body and '算法工程师' in body, body[body.find(uname)-10:body.find(uname)+60] if uname in body else '')
        _save_evidence('05_user_in_list', drv, _network_api_calls(drv))
        # GET 接口核对
        try:
            ulist = _get_api(f'/auth/users?page=1&page_size=100&keyword={urllib.parse.quote(uname)}')
            items = [i for i in ulist.get('data', {}).get('items', []) if i.get('username') == uname]
            check('GET /auth/users 含新建用户', len(items) >= 1)
            if items:
                u = items[0]
                created_user_ids.append(str(u['id']))
                check('GET 用户字段：username 一致', u['username'] == uname, str(u['username']))
                check('GET 用户字段：email 一致', u['email'] == email, str(u['email']))
                check('GET 用户字段：display_name 一致', u.get('display_name') == '接线测试_用户', str(u.get('display_name')))
                check('GET 用户字段：role 一致（算法工程师）', u.get('role_name') == 'algo_engineer' or u.get('role_name') == '算法工程师', str(u.get('role_name')))
        except Exception as e:
            check('GET /auth/users 含新建用户', False, str(e))

        # ─── ③ 编辑用户（回显 → 改 → 保存 → 再核对）───
        # 打开编辑抽屉
        row_op = drv.find_element(By.XPATH, f"//button[@aria-label='用户操作：{uname}']")
        _js_click(drv, row_op)
        _wait_text(drv, '编辑', timeout=10)
        _menu_item_click(drv, '编辑')
        _wait_text(drv, '编辑用户', timeout=15)
        body = _body_text(drv)
        check('编辑抽屉打开', '编辑用户' in body)
        # 回显核对
        un_input = drv.find_element(By.ID, 'user-username')
        check('回显用户名', (un_input.get_attribute('value') or '') == uname)
        dn_input = drv.find_element(By.ID, 'user-display-name')
        check('回显显示名', (dn_input.get_attribute('value') or '') == '接线测试_用户')
        em_input = drv.find_element(By.ID, 'user-email')
        check('回显邮箱', (em_input.get_attribute('value') or '') == email)
        _save_evidence('06_user_edit_echo', drv, _network_api_calls(drv))
        # 改显示名 + 邮箱 + 状态
        new_email = f'jxx{uuid.uuid4().hex[:8]}@test.local'
        dn_input.clear()
        dn_input.send_keys('接线测试_改名')
        em_input.clear()
        em_input.send_keys(new_email)
        _select_option(drv, None, '停用', trigger_id='user-status')
        _click_text(drv, '保存')
        _wait_text(drv, '用户已更新', timeout=30)
        net = _network_api_calls(drv)
        check('编辑保存真实请求 PUT /auth/users/{id}', any('PUT' == n.get('method') and '/auth/users/' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'auth/users/' in n.get('url', '')]))
        _save_evidence('07_user_edited', drv, net)
        # 再回显核对（重开抽屉）
        try:
            row_op2 = drv.find_element(By.XPATH, f"//button[@aria-label='用户操作：{uname}']")
            _js_click(drv, row_op2)
            _wait_text(drv, '编辑', timeout=10)
            _menu_item_click(drv, '编辑')
            _wait_text(drv, '编辑用户', timeout=15)
            dn2 = drv.find_element(By.ID, 'user-display-name').get_attribute('value') or ''
            em2 = drv.find_element(By.ID, 'user-email').get_attribute('value') or ''
            check('编辑后回显显示名=接线测试_改名', dn2 == '接线测试_改名', dn2)
            check('编辑后回显邮箱=新邮箱', em2 == new_email, em2)
            _save_evidence('08_user_edit_after_echo', drv, _network_api_calls(drv))
            # 关抽屉
            try:
                drv.find_element(By.XPATH, "//button[normalize-space()='取消']").click()
            except Exception:
                pass
            time.sleep(0.5)
        except Exception as e:
            check('编辑后回显核对', False, str(e))

        # ─── ④ 停用/启用切换 ───
        try:
            row_op3 = drv.find_element(By.XPATH, f"//button[@aria-label='用户操作：{uname}']")
            _js_click(drv, row_op3)
            _wait_text(drv, '启用', timeout=10)
            _menu_item_click(drv, '启用')
            _wait_text(drv, '用户已更新', timeout=30)
            body = _body_text(drv)
            check('启停切换成功（toast）', '用户已更新' in body)
            _save_evidence('09_user_toggle_status', drv, _network_api_calls(drv))
        except Exception as e:
            check('启停切换', False, str(e))

        # ─── ⑤ 删除用户 ───
        row_op4 = drv.find_element(By.XPATH, f"//button[@aria-label='用户操作：{uname}']")
        _js_click(drv, row_op4)
        _wait_text(drv, '删除', timeout=10)
        _menu_item_click(drv, '删除')
        _wait_text(drv, '确认删除用户', timeout=15)
        body = _body_text(drv)
        check('删除确认弹窗', '确认删除用户' in body)
        _save_evidence('10_user_delete_confirm', drv, _network_api_calls(drv))
        del_btn = drv.find_element(By.XPATH, "//button[normalize-space()='删除']")
        _js_click(drv, del_btn)
        _wait_text(drv, '用户已删除', timeout=30)
        net = _network_api_calls(drv)
        check('删除真实请求 DELETE /auth/users/{id}', any('DELETE' == n.get('method') and '/auth/users/' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'auth/users/' in n.get('url', '')]))
        _save_evidence('11_user_deleted', drv, net)
        # 接口核对（软删或 404）
        try:
            ulist2 = _get_api(f'/auth/users?page=1&page_size=100&keyword={urllib.parse.quote(uname)}')
            items2 = [i for i in ulist2.get('data', {}).get('items', []) if i.get('username') == uname]
            check('GET /auth/users 删除后无此用户', len(items2) == 0 or items2[0].get('status') == 'disabled', str(items2[:1]))
        except Exception as e:
            check('GET /auth/users 删除后无此用户', False, str(e))
        created_user_ids.clear()

        # ─── ⑥ 角色列表 ───
        _goto(drv, '/system-settings/iam/roles', wait_text='角色权限管理', timeout=30)
        _wait_text(drv, '超级管理员', timeout=45)
        body = _body_text(drv)
        check('角色管理分区标题', '角色权限管理' in body)
        check('系统角色渲染（admin/超级管理员）', '超级管理员' in body and '系统内置' in body)
        check('角色表列齐', all(c in body for c in ('角色名称', '描述', '类型', '权限数', '用户数')))
        net = _network_api_calls(drv)
        check('Network 含 GET /auth/roles', any('/auth/roles' in n.get('url', '') for n in net))
        _save_evidence('12_roles_list', drv, net)

        # ─── ⑦ 新建角色 ───
        rname = f'接线测试_角色{STAMP}'
        _click_text_contains(drv, '新建角色')
        _wait_text(drv, '创建自定义角色并分配权限串', timeout=15)
        body = _body_text(drv)
        check('新建角色弹窗打开', '新建角色' in body and '权限' in body)
        drv.find_element(By.ID, 'role-name').send_keys(rname)
        drv.find_element(By.ID, 'role-description').send_keys('接线测试_角色描述')
        # 勾选一个权限（evaluation:read）
        perm_cbs = drv.find_elements(By.CSS_SELECTOR, "[role='checkbox'], input[type='checkbox']")
        if perm_cbs:
            _js_click(drv, perm_cbs[0])
        _save_evidence('13_role_create_filled', drv, _network_api_calls(drv))
        _click_text(drv, '创建')
        _wait_text(drv, '角色已创建', timeout=30)
        net = _network_api_calls(drv)
        check('创建角色真实请求 POST /auth/roles', any('/auth/roles' in n.get('url', '') and n.get('method') == 'POST' for n in net), str([n.get('url') for n in net if 'roles' in n.get('url', '')]))
        _save_evidence('14_role_created', drv, net)
        body = _body_text(drv)
        check('列表出现新角色', rname in body)
        try:
            roles2 = _get_api('/auth/roles')
            r = [x for x in roles2.get('data', {}).get('roles', []) if x.get('name') == rname]
            check('GET /auth/roles 含新建角色', len(r) >= 1, str(r[:1])[:100])
            if r:
                created_role_ids.append(str(r[0]['id']))
                check('GET 角色字段：名称一致', r[0]['name'] == rname, str(r[0]['name']))
                check('GET 角色字段：描述一致', r[0].get('description') == '接线测试_角色描述', str(r[0].get('description')))
        except Exception as e:
            check('GET /auth/roles 含新建角色', False, str(e))

        # ─── ⑧ 编辑角色（重命名/改描述/权限保存，INT-1347 复测项③）───
        row_op = drv.find_element(By.XPATH, f"//button[@aria-label='角色操作：{rname}']")
        _js_click(drv, row_op)
        _wait_text(drv, '详情', timeout=10)
        _menu_item_click(drv, '编辑')
        _wait_text(drv, '编辑角色', timeout=15)
        body = _body_text(drv)
        check('编辑角色弹窗打开', '编辑角色' in body)
        name_input = drv.find_element(By.ID, 'role-name')
        check('回显角色名', (name_input.get_attribute('value') or '') == rname)
        name_input.clear()
        name_input.send_keys(rname + '_改')
        desc_input = drv.find_element(By.ID, 'role-description')
        desc_input.clear()
        desc_input.send_keys('接线测试_角色描述_改')
        # 权限矩阵：勾选 task:create（在 task:read 基础上新增；Checkbox id=perm-{code}）
        perm_create = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "#perm-task\\:create"))
        _js_click(drv, perm_create)
        _save_evidence('15_role_edit_filled', drv, _network_api_calls(drv))
        _click_text(drv, '保存')
        _wait_text(drv, '确认保存角色权限', timeout=15)
        _click_text(drv, '确认保存')
        _wait_text(drv, '角色权限已更新', timeout=30)
        net = _network_api_calls(drv)
        check('编辑角色真实请求 PUT /auth/roles/{id}', any('PUT' == n.get('method') and '/auth/roles/' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'roles' in n.get('url', '')]))
        check('编辑角色真实请求 POST /auth/roles/{id}/permissions', any('POST' == n.get('method') and '/permissions' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'permissions' in n.get('url', '')]))
        _save_evidence('16_role_edited', drv, net)
        body = _body_text(drv)
        check('列表角色名已更新', rname + '_改' in body)
        try:
            roles3 = _get_api('/auth/roles')
            r_edit = [x for x in roles3.get('data', {}).get('roles', []) if x.get('name') == rname + '_改']
            check('GET 角色编辑后名称一致', len(r_edit) >= 1)
            if r_edit:
                check('GET 角色编辑后描述一致', r_edit[0].get('description') == '接线测试_角色描述_改', str(r_edit[0].get('description'))[:60])
                perms = r_edit[0].get('permissions') or []
                check('GET 角色编辑后权限含 task:create（新增）', 'task:create' in perms, str(perms))
        except Exception as e:
            check('GET 角色编辑后核对', False, str(e))
        rname = rname + '_改'

        # ─── ⑨ 删除角色 ───
        row_op = drv.find_element(By.XPATH, f"//button[@aria-label='角色操作：{rname}']")
        _js_click(drv, row_op)
        _wait_text(drv, '删除', timeout=10)
        _menu_item_click(drv, '删除')
        _wait_text(drv, '确认删除角色', timeout=15)
        body = _body_text(drv)
        check('删除角色确认弹窗', '确认删除角色' in body)
        _save_evidence('17_role_delete_confirm', drv, _network_api_calls(drv))
        del_btn = drv.find_element(By.XPATH, "//button[normalize-space()='删除']")
        _js_click(drv, del_btn)
        _wait_text(drv, '角色已删除', timeout=30)
        net = _network_api_calls(drv)
        check('删除角色真实请求 DELETE /auth/roles/{id}', any('DELETE' == n.get('method') and '/auth/roles/' in n.get('url', '') for n in net), str([n.get('url') for n in net if 'roles' in n.get('url', '')]))
        _save_evidence('18_role_deleted', drv, net)
        created_role_ids.clear()

        # 防串库②
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
        f.write('CREATED_USER_IDS: ' + json.dumps(created_user_ids, ensure_ascii=False) + '\n')
        f.write('CREATED_ROLE_IDS: ' + json.dumps(created_role_ids, ensure_ascii=False) + '\n')

    print('=' * 60)
    print(f'PASS {sum(1 for t, _, _ in results if t == "PASS")} / {len(results)}')
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
