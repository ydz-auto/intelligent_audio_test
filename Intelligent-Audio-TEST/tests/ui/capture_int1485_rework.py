# -*- coding: utf-8 -*-
"""INT-1485 返工补测（前端UX审计员打回三项，2026-10-23）。

只补打回项，不重走已成立的窗：
  K 角色权限管理：行菜单（详情/编辑/删除隐藏）、角色详情（admin 矩阵禁用 + 130 开关）、
    编辑矩阵 → 确认保存 → POST /roles/{id}/permissions → GET /auth/roles 回读 → 还原；
    新建自定义角色 → 回读 → 删除 → 回读消失；名称留空提交校验。浅色 + 深色截图。
  L 用户抽屉密码字段：8–128 位校验（<8 / >128 走 UI 与接口各一次）+ 必填星号缺失取证。
  M 真实低权限角色：接线测试_guest 登录 → /dashboard 控制台 SEVERE、直达设置 → /403、侧栏隐藏。
  Z 清理：删除本 run 自建用户/角色，还原 tester 权限矩阵，主题回浅色。

环境：仅 15173（React 构建）+ 15000（intelligent_audio_test 真实库栈）。
运行：
  D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/capture_int1485_rework.py
"""
import json
import os
import re
import sys
import time
import traceback
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1485_system_settings as B  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

ART = B.ART
BASE = B.BASE
TS = time.strftime('%m%d%H%M%S')
ROLE_NEW = '接线测试_角色_%s' % TS
PW_USERS = [
    ('接线测试_pw1_%s' % TS, 'x'),
    ('接线测试_pw7_%s' % TS, '1234567'),
    ('接线测试_pw129_%s' % TS, 'a' * 129),
]
GUEST = ('接线测试_guest', 'JieXianTest@2026')
SYS_ROLES = ['超级管理员', '测试工程师', '算法工程师', '设备管理员', '游客']
SYS_ROLE_CODE = {'超级管理员': 'admin', '测试工程师': 'tester', '算法工程师': 'algo_engineer',
                 '设备管理员': 'device_admin', '游客': 'guest'}

STATE = {'tester_original': None, 'created_role_id': None, 'created_role_name': None}


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------

def env_check(label):
    try:
        with urllib.request.urlopen(B.API + '/health', timeout=20) as r:
            health = json.loads(r.read().decode())
    except Exception as exc:
        health = {'error': str(exc)}
    try:
        with urllib.request.urlopen('http://127.0.0.1:15173/', timeout=20) as r:
            html = r.read().decode('utf-8', 'replace')
        m = re.search(r'lib-react[^"\']*', html)
        front = m.group(0) if m else 'NO-lib-react'
    except Exception as exc:
        front = 'ERR:%s' % exc
    db = health.get('database') if isinstance(health, dict) else None
    ok = (db == 'intelligent_audio_test') and front.startswith('lib-react')
    B.record('ENV-%s 环境核对' % label, ok, 'health=%s frontend=%s' % (health, front))
    return db, front


def roles_api(token):
    st, r = B.api('/api/v1/auth/roles', token)
    return (r.get('data') or {}).get('roles') or []


def role_by_name(token, name):
    return next((r for r in roles_api(token) if r.get('name') == name), None)


def close_dialogs(drv):
    for _ in range(4):
        if B.dialog_present(drv) is None:
            return
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.7)


def click_in_dialog(drv, text, exact=True, kw=None, timeout=20):
    def probe(d):
        for el in d.find_elements(
                By.CSS_SELECTOR,
                "[data-slot='dialog-content'], [data-slot='alert-dialog-content'], [data-slot='sheet-content']"):
            if not B.visible(el):
                continue
            if kw and kw not in (el.text or ''):
                continue
            for btn in el.find_elements(By.TAG_NAME, 'button'):
                t = (btn.text or '').strip()
                if ((t == text) if exact else (text in t)) and B.visible(btn):
                    return btn
        return False
    el = WebDriverWait(drv, timeout).until(probe)
    B.js_click(drv, el)
    return el


def wait_dialog_kw(drv, kw, timeout=20):
    return WebDriverWait(drv, timeout).until(
        lambda d: next((el for el in d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")
                        if B.visible(el) and kw in (el.text or '')), False))


def wait_post(drv, needle, timeout=30):
    posts = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.8)
        posts = B.find_req(B.get_reqs(drv, settle=0.1), needle, 'POST')
        if posts and any(p.get('status') for p in posts):
            break
    return posts


def short(rec):
    if not rec:
        return {}
    return {'method': rec.get('method'), 'url': rec.get('url'), 'status': rec.get('status'),
            'body': (rec.get('body') or '')[:400], 'resp': (rec.get('resp') or '')[:300]}


def open_role_menu(drv, role_name, timeout=25):
    sel = "button[aria-label='角色操作：%s']" % role_name
    el = B.find_visible(drv, By.CSS_SELECTOR, sel, timeout=timeout)
    B.js_click(drv, el)
    WebDriverWait(drv, 12).until(
        lambda d: any(B.visible(i) for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")))
    return [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if B.visible(i)]


def menu_click(drv, text):
    items = [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if B.visible(i)]
    target = next(i for i in items if (i.text or '').strip() == text)
    B.js_click(drv, target)
    time.sleep(0.9)


def dialog_checkboxes(drv, kw):
    el = wait_dialog_kw(drv, kw)
    return el.find_elements(By.CSS_SELECTOR, "[data-slot='checkbox']")


def cb_checked(el):
    return (el.get_attribute('aria-checked') or el.get_attribute('data-checked') or '').lower() in ('true', 'mixed')


def toggle_perm(drv, code):
    el = drv.find_element(By.ID, 'perm-%s' % code)
    B.js_click(drv, el)
    time.sleep(0.35)
    return el


def find_user(token, username):
    q = urllib.parse.quote(username)
    st, listing = B.api('/api/v1/auth/users?page=1&page_size=100&keyword=' + q, token)
    items = (listing.get('data') or {}).get('items') or []
    return next((it for it in items if it.get('username') == username), None)


def delete_user_by_name(token, username):
    it = find_user(token, username)
    if not it:
        return None
    return B.api('/api/v1/auth/users/%s' % it.get('id'), token, method='DELETE')


def users_left(token, prefix):
    st, listing = B.api('/api/v1/auth/users?page=1&page_size=100', token)
    items = (listing.get('data') or {}).get('items') or []
    return [it.get('username') for it in items if (it.get('username') or '').startswith(prefix)]


# ---------------------------------------------------------------------------
# K. 角色权限管理（详情 / 编辑矩阵 / 新建 / 删除）
# ---------------------------------------------------------------------------

def phase_k(drv, token):
    try:
        roles = roles_api(token)
        by_name = {r.get('name'): r for r in roles}
        STATE['tester_original'] = list((by_name.get('tester') or {}).get('permissions') or [])
        B.reset_reqs(drv)
        B.goto_settings(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
        time.sleep(1.5)
        reqs = B.get_reqs(drv)
        rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        body = B.body_text(drv)
        missing = [n for n in SYS_ROLES if n not in body]
        perm_cols = []
        for tr in rows:
            tds = tr.find_elements(By.TAG_NAME, 'td')
            if len(tds) >= 4:
                perm_cols.append(tds[3].text.strip())
        api_counts = [str(len(r.get('permissions') or [])) for r in roles]
        B.record('K1 角色列表 5 行 + 权限数列对齐 /auth/roles',
                 len(rows) == len(roles) and not missing and sorted(perm_cols) == sorted(api_counts),
                 'rows=%d missing=%s ui_counts=%s api_counts=%s GET_roles=%s'
                 % (len(rows), missing, perm_cols, api_counts,
                    [r.get('status') for r in B.find_req(reqs, '/auth/roles', 'GET')][:2]))
        B.shot(drv, 'K1_roles_list_light')
        drv.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.8)
        B.shot(drv, 'K1_roles_list_dark')
        drv.execute_script('document.documentElement.classList.remove("dark")')
        time.sleep(0.4)

        # K2 超级管理员行菜单：只有「详情」（admin 不可编辑，系统角色不可删除）
        items = open_role_menu(drv, '超级管理员')
        texts = [i.text.strip() for i in items]
        B.record('K2 超级管理员行菜单仅「详情」', texts == ['详情'], 'items=%s' % texts)
        B.shot(drv, 'K2_admin_row_menu_light')
        menu_click(drv, '详情')
        dlg = wait_dialog_kw(drv, '角色详情')
        time.sleep(1.0)
        cbs = dialog_checkboxes(drv, '角色详情')
        disabled_reason = '超级管理员持有全部权限（通配），不可修改' in (dlg.text or '')
        disabled_count = 0
        for el in cbs:
            if (el.get_attribute('aria-disabled') or '').lower() == 'true' or el.get_attribute('disabled') is not None:
                disabled_count += 1
        has_save = any((b.text or '').strip() in ('保存', '创建') for b in dlg.find_elements(By.TAG_NAME, 'button'))
        B.record('K3 超级管理员详情：矩阵全禁用 + 无保存按钮',
                 len(cbs) >= 120 and disabled_reason and disabled_count == len(cbs) and not has_save,
                 'switches=%d disabled=%d reason=%s save_btn=%s' % (len(cbs), disabled_count, disabled_reason, has_save))
        B.shot(drv, 'K3_role_detail_admin_light')
        drv.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.8)
        B.shot(drv, 'K3_role_detail_admin_dark')
        drv.execute_script('document.documentElement.classList.remove("dark")')
        click_in_dialog(drv, '取消')
        time.sleep(0.8)

        # K4 测试工程师：行菜单含编辑、无删除（系统角色）
        items = open_role_menu(drv, '测试工程师')
        texts = [i.text.strip() for i in items]
        B.record('K4 系统角色菜单：详情+编辑、无删除',
                 '详情' in texts and '编辑' in texts and '删除' not in texts, 'items=%s' % texts)
        menu_click(drv, '编辑')
        dlg = wait_dialog_kw(drv, '编辑角色')
        time.sleep(1.2)
        name_val = drv.find_element(By.ID, 'role-name').get_attribute('value')
        desc_val = drv.find_element(By.ID, 'role-description').get_attribute('value')
        cbs = dialog_checkboxes(drv, '编辑角色')
        checked = [el.get_attribute('id') for el in cbs if cb_checked(el)]
        tester_perms = STATE['tester_original']
        B.record('K5 编辑角色回填（名称/描述/已选权限）',
                 name_val == '测试工程师' and len(checked) == len(tester_perms),
                 'name=%r desc=%r checked=%d expected=%d switches=%d'
                 % (name_val, (desc_val or '')[:20], len(checked), len(tester_perms), len(cbs)))
        B.shot(drv, 'K5_role_edit_light')
        drv.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.8)
        B.shot(drv, 'K5_role_edit_dark')
        drv.execute_script('document.documentElement.classList.remove("dark")')

        drop_code = sorted(tester_perms)[-1]
        toggle_perm(drv, drop_code)
        time.sleep(0.5)
        new_checked = len([el for el in dialog_checkboxes(drv, '编辑角色') if cb_checked(el)])
        B.record('K6 取消勾选一个权限', new_checked == len(tester_perms) - 1,
                 'drop=%s checked=%d -> %d' % (drop_code, len(tester_perms), new_checked))

        B.reset_reqs(drv)
        click_in_dialog(drv, '保存', exact=True)
        WebDriverWait(drv, 15).until(lambda d: B.dialog_present(d, '确认保存角色权限') is not None)
        B.shot(drv, 'K6_matrix_confirm_light')
        click_in_dialog(drv, '确认保存', kw='确认保存角色权限')
        posts = wait_post(drv, '/permissions')
        time.sleep(1.5)
        tester = role_by_name(token, 'tester')
        after = list((tester or {}).get('permissions') or [])
        B.record('K7 矩阵保存：POST 请求 + GET 回读（少 1 个权限）',
                 bool(posts) and after and drop_code not in after and len(after) == len(tester_perms) - 1,
                 'POST=%s readback=%d drop_present=%s body_tail=%s'
                 % ([short(p) for p in posts][:2], len(after), drop_code in after,
                    ((posts[0].get('body') or '')[-90:]) if posts else None))
        B.shot(drv, 'K7_after_save_light')

        # K8 还原矩阵
        B.reset_reqs(drv)
        open_role_menu(drv, '测试工程师')
        menu_click(drv, '编辑')
        wait_dialog_kw(drv, '编辑角色')
        time.sleep(1.0)
        toggle_perm(drv, drop_code)
        time.sleep(0.4)
        click_in_dialog(drv, '保存', exact=True)
        WebDriverWait(drv, 15).until(lambda d: B.dialog_present(d, '确认保存角色权限') is not None)
        click_in_dialog(drv, '确认保存', kw='确认保存角色权限')
        wait_post(drv, '/permissions')
        time.sleep(1.5)
        restored = list((role_by_name(token, 'tester') or {}).get('permissions') or [])
        B.record('K8 还原矩阵：GET 回读与原始一致',
                 sorted(restored) == sorted(tester_perms),
                 'restored=%d original=%d equal=%s' % (len(restored), len(tester_perms),
                                                       sorted(restored) == sorted(tester_perms)))

        # K9 新建角色：名称留空 → 是否有前端校验
        ids_before = {str(r.get('id')) for r in roles_api(token)}
        B.reset_reqs(drv)
        B.click_button_text(drv, '新建角色')
        wait_dialog_kw(drv, '新建角色')
        time.sleep(0.8)
        click_in_dialog(drv, '创建', exact=True)
        time.sleep(2.0)
        reqs = B.get_reqs(drv)
        empty_posts = B.find_req(reqs, '/auth/roles', 'POST')
        empty_res = [short(r) for r in empty_posts]
        dlg_still = B.dialog_present(drv, '新建角色') is not None
        B.record('K9 新建角色名称留空提交', True,
                 'POST=%s dialog_open=%s（前端无必填校验则会产生请求，记观察项）' % (empty_res, dlg_still))
        # 若空名真的建成功，仅删除本次新增的 id
        for r in roles_api(token):
            if str(r.get('id')) not in ids_before and not (r.get('name') or '').strip():
                B.api('/api/v1/auth/roles/%s' % r.get('id'), token, method='DELETE')
        if not dlg_still:
            B.click_button_text(drv, '新建角色')
            wait_dialog_kw(drv, '新建角色')
            time.sleep(0.6)

        name_box = drv.find_element(By.ID, 'role-name')
        desc_box = drv.find_element(By.ID, 'role-description')
        B.set_input(drv, name_box, ROLE_NEW)
        B.set_input(drv, desc_box, 'INT-1485 走查自建角色，验收后删除')
        picked = []
        for code in ('home:read', 'report:read'):
            try:
                toggle_perm(drv, code)
                picked.append(code)
            except Exception:
                pass
        time.sleep(0.4)
        B.shot(drv, 'K9_role_create_light')
        B.reset_reqs(drv)
        click_in_dialog(drv, '创建', exact=True)
        posts = wait_post(drv, '/auth/roles')
        time.sleep(1.5)
        new_role = role_by_name(token, ROLE_NEW)
        if new_role:
            STATE['created_role_id'] = new_role.get('id')
            STATE['created_role_name'] = new_role.get('name')
        created_perms = list((new_role or {}).get('permissions') or [])
        B.record('K10 新建自定义角色 → GET 回读',
                 bool(posts) and new_role is not None and set(picked).issubset(set(created_perms)),
                 'POST=%s role=%s picked=%s readback_perms=%s'
                 % ([short(p) for p in posts][:1],
                    {k: (new_role or {}).get(k) for k in ('id', 'name', 'is_system')}, picked, created_perms))
        B.shot(drv, 'K10_role_created_light')

        # K11 删除自定义角色 → 回读消失
        B.reset_reqs(drv)
        items = open_role_menu(drv, ROLE_NEW)
        texts = [i.text.strip() for i in items]
        menu_click(drv, '删除')
        WebDriverWait(drv, 15).until(lambda d: B.dialog_present(d, '确认删除角色') is not None)
        B.shot(drv, 'K11_role_delete_confirm_light')
        click_in_dialog(drv, '删除', kw='确认删除角色')
        dels = []
        deadline = time.time() + 25
        while time.time() < deadline:
            time.sleep(0.8)
            allr = B.get_reqs(drv, settle=0.1)
            dels = [r for r in allr if (r.get('method') == 'DELETE' and '/auth/roles/' in (r.get('url') or ''))]
            if dels and any(d.get('status') for d in dels):
                break
        time.sleep(1.2)
        gone = role_by_name(token, ROLE_NEW) is None
        B.record('K11 删除自定义角色 → GET 回读消失',
                 '删除' in texts and bool(dels) and gone,
                 'menu=%s DELETE=%s gone=%s' % (texts, [short(d) for d in dels][:1], gone))
        if gone:
            STATE['created_role_id'] = None
    except Exception as exc:
        B.shot(drv, 'K_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        B.record('K 角色抽屉走查', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])))
        close_dialogs(drv)


# ---------------------------------------------------------------------------
# L. 用户抽屉密码 8–128 位校验
# ---------------------------------------------------------------------------

def phase_l(drv, token):
    try:
        B.goto_settings(drv, '/system-settings/iam/users', '用户管理', '注册时间')
        time.sleep(1.0)
        B.click_button_text(drv, '新建用户')
        B.wait_dialog(drv, '新建用户')
        time.sleep(0.8)
        label_txt = drv.execute_script(
            'var el=document.querySelector("label[for=\'user-password\']"); return el ? el.textContent : "";')
        placeholder = drv.find_element(By.ID, 'user-password').get_attribute('placeholder')
        B.record('L1 密码字段标注', True,
                 'label=%r placeholder=%r 必填星号=%s' % (label_txt, placeholder, '*' in (label_txt or '')))

        uname, pwd = PW_USERS[0]
        B.set_input(drv, B.find_visible(drv, By.ID, 'user-username'), uname)
        B.set_input(drv, B.find_visible(drv, By.ID, 'user-email'), uname + '@example.com')
        B.set_input(drv, B.find_visible(drv, By.ID, 'user-password'), pwd)
        B.shot(drv, 'L2_password_one_char_light')
        B.reset_reqs(drv)
        B.click_button_text(drv, '创建', exact=True)
        posts = wait_post(drv, '/auth/users')
        time.sleep(1.0)
        st = [p.get('status') for p in posts]
        created = None
        for _ in range(4):
            created = find_user(token, uname)
            if created:
                break
            time.sleep(1.0)
        B.record('L2 1 位密码 UI 提交', bool(posts) and any(s in (200, 201) for s in st),
                 'POST=%s status=%s body=%s 回读=%s'
                 % (len(posts), st, [short(p).get('body') for p in posts][:1],
                    {k: (created or {}).get(k) for k in ('id', 'username')}))
        if created:
            _, resp = delete_user_by_name(token, uname)
        close_dialogs(drv)

        # 接口侧边界：7 位 / 129 位（UI 同一入口，接口侧补充边界证据）
        for uname, pwd in PW_USERS[1:]:
            st, resp = B.api('/api/v1/auth/users', token, method='POST',
                             body={'username': uname, 'email': uname + '@example.com',
                                   'password': pwd, 'role_id': 0})
            it = find_user(token, uname)
            B.record('L3 密码 %d 位接口提交' % len(pwd), True,
                     'username=%s status=%s code=%s user_id=%s'
                     % (uname, st, (resp or {}).get('code'), (it or {}).get('id')))
            if it:
                delete_user_by_name(token, uname)
        left = [u for u, _ in PW_USERS if find_user(token, u)]
        B.record('L4 密码探针用户已清理', not left, 'left=%s' % left)
    except Exception as exc:
        B.shot(drv, 'L_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        B.record('L 密码校验走查', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])))
        close_dialogs(drv)


# ---------------------------------------------------------------------------
# M. 真实低权限角色（接线测试_guest）控制台与拦截
# ---------------------------------------------------------------------------

def console_logs(drv):
    try:
        return drv.get_log('browser')
    except Exception:
        return []


def bootstrap_with(drv, token):
    drv.get(BASE + '/login')
    B.wait_ready(drv)
    drv.execute_script(
        'localStorage.setItem(arguments[0], arguments[1]);'
        'localStorage.removeItem("iatp:auth:v1");'
        'sessionStorage.removeItem("__rbac_perm");', B.TOKEN_KEY, token)


def phase_m(drv, token):
    try:
        gtoken, guser = B.rsa_login_token(*GUEST)
        st, me = B.api('/api/v1/auth/me', gtoken)
        B.record('M1 guest 真实账号登录', st == 200 and me.get('username') == GUEST[0],
                 'me=%s perms=%d' % ({k: me.get(k) for k in ('user_id', 'username')},
                                     len(me.get('permissions') or [])))
        bootstrap_with(drv, gtoken)
        console_logs(drv)  # drain
        B.goto(drv, '/dashboard')
        time.sleep(5.0)
        logs = console_logs(drv)
        severe = [l for l in logs if str(l.get('level', '')).upper() == 'SEVERE']
        opt403 = [l for l in severe if '/api/option' in (l.get('message') or '')]
        B.record('M2 guest /dashboard 控制台 SEVERE', True,
                 'SEVERE=%d option403=%d msgs=%s'
                 % (len(severe), len(opt403), [(m.get('message') or '')[:260] for m in opt403][:3]))
        B.shot(drv, 'M2_guest_dashboard_light')
        body = B.body_text(drv)
        nav_hidden = not any(d in body for d in ('用户与权限', '认证设置', '安全设置', '系统设置'))
        B.record('M3 guest 侧栏六域不出现', nav_hidden, 'url=%s nav_hidden=%s' % (drv.current_url, nav_hidden))
        console_logs(drv)
        B.goto(drv, '/system-settings/site/info')
        time.sleep(3.5)
        url = drv.current_url
        b403 = B.body_text(drv)
        B.record('M4 guest 直达设置 → /403', '/403' in url,
                 'url=%s body=%s' % (url, b403[:160]))
        B.shot(drv, 'M4_guest_settings_403_light')
        severe2 = [l for l in console_logs(drv) if str(l.get('level', '')).upper() == 'SEVERE']
        B.record('M5 guest 设置页控制台 SEVERE', True,
                 'count=%d msgs=%s' % (len(severe2), [(m.get('message') or '')[:200] for m in severe2][:4]))
    except Exception as exc:
        B.shot(drv, 'M_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        B.record('M guest 视角走查', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])))
    finally:
        # 还原 admin 会话
        try:
            bootstrap_with(drv, token)
            B.goto(drv, '/system-settings/site/info', '站点信息')
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Z. 清理
# ---------------------------------------------------------------------------

def phase_z(drv, token):
    try:
        B.set_theme(drv, 'light')
        left_users = [u for u, _ in PW_USERS if find_user(token, u)]
        for u in left_users:
            delete_user_by_name(token, u)
        if STATE.get('created_role_name'):
            r = role_by_name(token, STATE['created_role_name'])
            if r:
                B.api('/api/v1/auth/roles/%s' % r.get('id'), token, method='DELETE')
        roles_left = [r.get('name') for r in roles_api(token) if (r.get('name') or '').startswith('接线测试_')]
        r2 = role_by_name(token, 'tester')
        perms2 = list((r2 or {}).get('permissions') or [])
        users2 = [u for u, _ in PW_USERS if find_user(token, u)]
        B.record('Z1 清理：自建用户/角色已删、tester 权限已还原',
                 not roles_left and not users2 and STATE['tester_original'] is not None
                 and sorted(perms2) == sorted(STATE['tester_original']),
                 'roles_left=%s users_left=%s tester_perms=%d original=%s'
                 % (roles_left, users2, len(perms2),
                    len(STATE['tester_original'] or [])))
    except Exception as exc:
        B.record('Z 清理', False, '异常: %s' % exc)


def main():
    os.makedirs(ART, exist_ok=True)
    env_check('start')
    token, user = B.rsa_login_token(*B.ACCOUNT)
    print('login ok user=%s' % (user or {}).get('username'))
    drv = B.driver_init()
    try:
        B.bootstrap(drv, token, user)
        me = B.current_user(drv)
        B.record('AUTH 会话为真实账号', me.get('username') == B.ACCOUNT[0],
                 'me=%s' % {k: me.get(k) for k in ('user_id', 'username')})
        print('===== phase K =====')
        phase_k(drv, token)
        env_check('mid-K')
        print('===== phase L =====')
        phase_l(drv, token)
        print('===== phase M =====')
        phase_m(drv, token)
        env_check('mid-M')
        phase_z(drv, token)
        env_check('end')
    except Exception as exc:
        tb = traceback.format_exc().strip().splitlines()
        B.record('main 中断', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])))
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        out = os.path.join(ART, 'report_rework.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(B.RESULTS, f, ensure_ascii=False, indent=2)
        fails = [r for r in B.RESULTS if not r['ok']]
        print('\n===== SUMMARY: %d/%d passed, %d failed -> %s ====='
              % (len(B.RESULTS) - len(fails), len(B.RESULTS), len(fails), out))
        for f in fails:
            print('FAILED:', f['step'], '::', str(f['detail'])[:300])


if __name__ == '__main__':
    main()
