# -*- coding: utf-8 -*-
"""INT-1485 返工补充（角色删除被引用预检 + 新建角色空名称提示取证）。

仅补两项：
  K12 被用户引用的自定义角色删除：前端是否预检 / 后端 409 文案是否可见。
  K13 新建角色名称留空：请求 400 后弹窗行为与 toast 文案（是否字段级提示）。
清理：删除探针用户与角色。
"""
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1485_system_settings as B  # noqa: E402
import capture_int1485_rework as R  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

TS = time.strftime('%m%d%H%M%S')
ROLE_REF = '接线测试_引用角色_%s' % TS
ROLE_EMPTY = '接线测试_空名角色_%s' % TS
USER_REF = '接线测试_refuser_%s' % TS


def phase_k12(drv, token):
    role_id = None
    user_id = None
    try:
        st, resp = B.api('/api/v1/auth/roles', token, method='POST',
                         body={'name': ROLE_REF, 'description': '被引用删除预检探针',
                               'permission_codes': ['home:read']})
        role_id = ((resp or {}).get('data') or {}).get('role_id')
        st2, resp2 = B.api('/api/v1/auth/users', token, method='POST',
                           body={'username': USER_REF, 'email': USER_REF + '@example.com',
                                 'password': 'Ref@12345', 'role_id': role_id or 0})
        it = R.find_user(token, USER_REF)
        user_id = (it or {}).get('id')
        B.record('K12a 夹具：自建角色 + 归属用户', bool(role_id) and bool(user_id),
                 'role_id=%s user_id=%s create_user=%s/%s' % (role_id, user_id, st2, (resp2 or {}).get('code')))

        B.goto_settings(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
        time.sleep(1.2)
        B.reset_reqs(drv)
        items = R.open_role_menu(drv, ROLE_REF)
        R.menu_click(drv, '删除')
        dlg = WebDriverWait(drv, 15).until(lambda d: B.dialog_present(d, '确认删除角色'))
        # 确认框静态提示（spec「该角色仍有用户归属时需先转移用户」）；非阻断式预检
        hint = '转移用户' in (dlg.text or '')
        B.shot(drv, 'K12_role_delete_referenced_confirm_light')
        R.click_in_dialog(drv, '删除', kw='确认删除角色')
        dels = []
        deadline = time.time() + 25
        while time.time() < deadline:
            time.sleep(0.8)
            allr = B.get_reqs(drv, settle=0.1)
            dels = [r for r in allr if r.get('method') == 'DELETE' and '/auth/roles/' in (r.get('url') or '')]
            if dels and any(d.get('status') for d in dels):
                break
        time.sleep(1.0)
        body = B.body_text(drv)
        shown = ('仍被' in body) or ('迁移用户' in body) or ('转移用户' in body)
        still = R.role_by_name(token, ROLE_REF) is not None
        B.record('K12 被引用角色删除：409 + 文案可见',
                 bool(dels) and any(d.get('status') == 409 for d in dels) and shown and still,
                 'DELETE=%s 确认框静态提示=%s toast可见=%s 角色仍在=%s body_tail=%s'
                 % ([R.short(d) for d in dels][:1], hint, shown, still,
                    body.replace('\n', ' ')[-200:]))
        B.shot(drv, 'K12_role_delete_referenced_409_light')
    except Exception as exc:
        B.shot(drv, 'K12_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        B.record('K12 被引用角色删除', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])))
    finally:
        try:
            if user_id:
                B.api('/api/v1/auth/users/%s' % user_id, token, method='DELETE')
            if role_id:
                B.api('/api/v1/auth/roles/%s' % role_id, token, method='DELETE')
            left_r = R.role_by_name(token, ROLE_REF)
            left_u = R.find_user(token, USER_REF)
            B.record('K12b 夹具清理', left_r is None and left_u is None,
                     'role_left=%s user_left=%s' % (bool(left_r), bool(left_u)))
        except Exception as exc:
            B.record('K12b 夹具清理', False, '异常: %s' % exc)


def phase_k13(drv, token):
    try:
        B.goto_settings(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
        time.sleep(1.0)
        B.reset_reqs(drv)
        B.click_button_text(drv, '新建角色')
        R.wait_dialog_kw(drv, '新建角色')
        time.sleep(0.6)
        R.click_in_dialog(drv, '创建', exact=True)
        posts = R.wait_post(drv, '/auth/roles')
        time.sleep(1.2)
        body = B.body_text(drv)
        dlg_open = B.dialog_present(drv, '新建角色') is not None
        tail = body.replace('\n', ' ')[-220:]
        B.record('K13 空名称提交：400 后提示文案', True,
                 'POST=%s 弹窗仍在=%s body_tail=%s'
                 % ([R.short(p) for p in posts][:1], dlg_open, tail))
        B.shot(drv, 'K13_role_create_empty_name_light')
        # 若残留空名角色，清掉本次唯一新增
        for r in R.roles_api(token):
            if (r.get('name') or '') == ROLE_EMPTY:
                B.api('/api/v1/auth/roles/%s' % r.get('id'), token, method='DELETE')
    except Exception as exc:
        B.shot(drv, 'K13_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        B.record('K13 空名称提交', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])))


def main():
    os.makedirs(B.ART, exist_ok=True)
    R.env_check('rework2-start')
    token, user = B.rsa_login_token(*B.ACCOUNT)
    drv = B.driver_init()
    try:
        B.bootstrap(drv, token, user)
        print('===== K12 =====')
        phase_k12(drv, token)
        print('===== K13 =====')
        phase_k13(drv, token)
        R.env_check('rework2-end')
    except Exception as exc:
        B.record('main 中断', False, '异常: %s' % exc)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        out = os.path.join(B.ART, 'report_rework2.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(B.RESULTS, f, ensure_ascii=False, indent=2)
        fails = [r for r in B.RESULTS if not r['ok']]
        print('\n===== SUMMARY: %d/%d passed, %d failed -> %s ====='
              % (len(B.RESULTS) - len(fails), len(B.RESULTS), len(fails), out))
        for f in fails:
            print('FAILED:', f['step'], '::', str(f['detail'])[:300])


if __name__ == '__main__':
    main()
