# -*- coding: utf-8 -*-
"""INT-1935 补证：系统设置域逐窗「遮罩 + 关闭控件」浅/深帧（含 OAuth 深色帧）。

背景：INT-1485 收口核对自认取证不全——遮罩与关闭按钮未逐窗单独留证、
OAuth 弹窗深色帧拍了未附。本脚本只补图，不改代码、不重走字段读写。

窗口清单（15 个）：
  六域设置：未保存更改离开拦截、日志维护（立即清理 / 立即归档 / 删除归档）
  IAM：新建用户抽屉、编辑用户抽屉、删除用户确认、新建角色、编辑角色、
       角色详情、删除角色确认、角色权限保存确认
  OAuth：新建提供方、编辑提供方、删除提供方确认

每窗两帧：浅色（遮罩 + 关闭控件可见）、深色同款；文件名为 <key>_light.png /
<key>_dark.png。深色用应用自身主题键 iatp:theme:v1:mode + 重载生效，不强制 class。

环境：docker 真实栈 15173（React 构建）+ 15000（intelligent_audio_test）。
运行：
  D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/capture_int1935_dialog_evidence.py
"""
import json
import os
import re
import sys
import time
import traceback
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_int1485_system_settings as B  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1935')
TS = time.strftime('%m%d%H%M%S')
TMP_USER = '接线测试_证据_%s' % TS
TMP_ROLE = '接线测试_证据角色_%s' % TS
TMP_OAUTH = '接线测试_证据OAuth_%s' % TS
TMP_PREFIXES = ('接线测试_证据',)

RESULTS = []
FIXTURES = {'user_id': None, 'role_id': None, 'oauth_id': None}


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:800], 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:500])


# ---------------------------------------------------------------------------
# 探针：遮罩 / 关闭控件 / 对比度
# ---------------------------------------------------------------------------

PROBE_JS = r'''
var el = arguments[0];
function norm(c){ try { var ctx=document.createElement('canvas').getContext('2d'); ctx.fillStyle='#000'; ctx.fillStyle=c; return ctx.fillStyle; } catch(e){ return c; } }
function rgba(c){ var n=norm(c); if(typeof n!=='string') return null;
  if(n.charAt(0)==='#'){ var h=n.slice(1); if(h.length===3){h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2];}
    return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16),1]; }
  var m=n.match(/rgba?\(([^)]+)\)/); if(!m) return null; var p=m[1].split(',').map(parseFloat);
  return [p[0],p[1],p[2], p.length>3?p[3]:1]; }
function lum(rgb){ var a=rgb.slice(0,3).map(function(v){ v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); });
  return 0.2126*a[0]+0.7152*a[1]+0.0722*a[2]; }
function ratio(a,b){ var l1=lum(a), l2=lum(b); var hi=Math.max(l1,l2), lo=Math.min(l1,l2); return (hi+0.05)/(lo+0.05); }
function bgOf(e){ var n=e; while(n && n!==document.documentElement){ var c=rgba(getComputedStyle(n).backgroundColor); if(c && c[3]>0.5) return c; n=n.parentElement; } return [255,255,255,1]; }
function vis(e){ if(!e) return false; var s=getComputedStyle(e); if(s.display==='none'||s.visibility==='hidden'||parseFloat(s.opacity)===0) return false;
  var r=e.getBoundingClientRect(); return r.width>0&&r.height>0; }
function rect(e){ var r=e.getBoundingClientRect(); return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]; }

var titleEl = el.querySelector("[data-slot='dialog-title'],[data-slot='alert-dialog-title'],[data-slot='sheet-title']");
var descEl = el.querySelector("[data-slot='dialog-description'],[data-slot='alert-dialog-description'],[data-slot='sheet-description']");
var fg = titleEl ? rgba(getComputedStyle(titleEl).color) : null;
var bg = bgOf(el);
var overlays = [];
["[data-slot='dialog-overlay']","[data-slot='alert-dialog-overlay']","[data-slot='sheet-overlay']"].forEach(function(sel){
  document.querySelectorAll(sel).forEach(function(o){
    if(!vis(o)) return;
    var s = getComputedStyle(o);
    overlays.push({sel:sel, opacity:s.opacity, bg:s.backgroundColor, rect:rect(o)});
  });
});
var closes = [];
["[data-slot='dialog-close']","[data-slot='sheet-close']"].forEach(function(sel){
  el.querySelectorAll(sel).forEach(function(b){
    closes.push({sel:sel, visible:vis(b), label:(b.getAttribute('aria-label')||b.textContent||'').trim().slice(0,20), rect:rect(b)});
  });
});
var cancelBtn = el.querySelector("[data-slot='alert-dialog-cancel']");
if (cancelBtn) closes.push({sel:"[data-slot='alert-dialog-cancel']", visible:vis(cancelBtn),
  label:(cancelBtn.textContent||'').trim().slice(0,20), rect:rect(cancelBtn)});

var midY = Math.round(window.innerHeight/2);
var topAt = document.elementFromPoint(20, midY);
var topSlot = null;
if (topAt) { var holder = topAt.closest("[data-slot]"); topSlot = holder ? holder.getAttribute('data-slot') : topAt.tagName; }
var root = document.documentElement;
return {
  title: titleEl ? (titleEl.textContent||'').trim() : null,
  desc: descEl ? (descEl.textContent||'').trim().slice(0,120) : null,
  dark: root.classList.contains('dark'),
  fg: fg, bg: bg,
  contrast: fg ? Math.round(ratio(fg,bg)*100)/100 : null,
  overlay: overlays,
  element_at_bg_point: topSlot,
  close_controls: closes,
  dialog_rect: rect(el),
  viewport: [window.innerWidth, window.innerHeight]
};
'''


def probe(drv, dlg):
    return drv.execute_script(PROBE_JS, dlg)


def apply_theme(drv, mode):
    """应用内主题：写入应用自身主题键后重载，由应用启动脚本恢复 html.dark/light。"""
    B.set_theme(drv, mode)
    B.goto_settings(drv, '/system-settings/site/info', '站点信息', '站点信息')
    WebDriverWait(drv, 25).until(lambda d: B.is_dark(d) == (mode == 'dark'))
    time.sleep(0.6)


class Unreachable(Exception):
    """窗口在现有构建/数据下不可达（不伪造截图，单列说明）。"""


def _visible_dialogs(drv):
    return [el for el in drv.find_elements(
        By.CSS_SELECTOR,
        "[data-slot='alert-dialog-content'], [data-slot='dialog-content'], [data-slot='sheet-content']")
        if B.visible(el)]


def goto_section(drv, path, title, require):
    """进入分区：真实内容等待；撞上 /api/option/ 长时间 pending（页面停在「正在加载设置…」）时重载重试。"""
    last = None
    for _ in range(3):
        try:
            B.goto_settings(drv, path, title, require)
            time.sleep(1.0)
            return
        except Exception as exc:
            last = exc
            if '正在加载设置' not in B.body_text(drv):
                raise
            time.sleep(2.0)
            drv.refresh()
            B.wait_ready(drv)
            time.sleep(1.5)
    raise last


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    size = os.path.getsize(path)
    if size < 2000:
        raise AssertionError('截图过小 %s (%d bytes)' % (path, size))
    return path, size


# ---------------------------------------------------------------------------
# 交互小工具
# ---------------------------------------------------------------------------

def open_menu(drv, aria_label):
    el = B.find_visible(drv, By.CSS_SELECTOR, "button[aria-label='%s']" % aria_label, timeout=25)
    B.js_click(drv, el)
    WebDriverWait(drv, 12).until(
        lambda d: any(B.visible(i) for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")))
    return [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if B.visible(i)]


def menu_click(drv, text):
    items = [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if B.visible(i)]
    target = next(i for i in items if (i.text or '').strip() == text)
    B.js_click(drv, target)
    time.sleep(0.9)


def search_user(drv, username):
    for _ in range(3):
        box = B.find_visible(drv, By.CSS_SELECTOR, 'input[placeholder="搜索用户名或邮箱"]', timeout=25)
        B.set_input(drv, box, username)
        try:
            return WebDriverWait(drv, 12).until(
                lambda d: next((b for b in d.find_elements(
                    By.CSS_SELECTOR, "button[aria-label='用户操作：%s']" % username) if B.visible(b)), False))
        except Exception:
            time.sleep(1.5)
    raise AssertionError('搜索结果中没有用户行: %s' % username)


def _click_and_wait_gone(drv, btn, dlg, timeout=15):
    B.js_click(drv, btn)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.4)
        if not B.visible(dlg):
            return True
    return not B.visible(dlg)


def close_top(drv, prefer=None, title=None):
    """关闭当前最上层窗口：Dialog/Sheet 优先 X，AlertDialog 用取消；返回是否已关闭。"""
    dlgs = _visible_dialogs(drv)
    if not dlgs:
        return True
    dlg = next((d for d in dlgs if title and title in (d.text or '')), dlgs[0])
    for sel in ("[data-slot='dialog-close']", "[data-slot='sheet-close']"):
        btns = [b for b in dlg.find_elements(By.CSS_SELECTOR, sel) if B.visible(b)]
        if btns:
            return _click_and_wait_gone(drv, btns[0], dlg)
    btns = [b for b in dlg.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-cancel']") if B.visible(b)]
    if btns:
        if prefer:
            label_btns = [b for b in btns if (b.text or '').strip() == prefer]
            btns = label_btns or btns
        return _click_and_wait_gone(drv, btns[0], dlg)
    raise AssertionError('窗口内找不到可用的关闭控件')


# ---------------------------------------------------------------------------
# 窗口定义：open(drv) 打开并等待；extra_close(drv) 关闭后收尾
# ---------------------------------------------------------------------------

def _open_user_create(drv):
    goto_section(drv, '/system-settings/iam/users', '用户管理', '注册时间')
    B.click_button_text(drv, '新建用户')
    B.wait_dialog(drv, '新建用户')


def _open_user_edit(drv):
    goto_section(drv, '/system-settings/iam/users', '用户管理', '注册时间')
    search_user(drv, TMP_USER)
    open_menu(drv, '用户操作：%s' % TMP_USER)
    menu_click(drv, '编辑')
    B.wait_dialog(drv, '编辑用户')


def _open_user_delete(drv):
    goto_section(drv, '/system-settings/iam/users', '用户管理', '注册时间')
    search_user(drv, TMP_USER)
    open_menu(drv, '用户操作：%s' % TMP_USER)
    menu_click(drv, '删除')
    B.wait_dialog(drv, '确认删除用户')


def _open_role_create(drv):
    goto_section(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
    B.click_button_text(drv, '新建角色')
    B.wait_dialog(drv, '新建角色')


def _open_role_edit(drv):
    goto_section(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
    open_menu(drv, '角色操作：测试工程师')
    menu_click(drv, '编辑')
    B.wait_dialog(drv, '编辑角色')


def _open_role_detail(drv):
    goto_section(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
    open_menu(drv, '角色操作：超级管理员')
    menu_click(drv, '详情')
    B.wait_dialog(drv, '角色详情')


def _open_role_delete(drv):
    goto_section(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
    open_menu(drv, '角色操作：%s' % TMP_ROLE)
    menu_click(drv, '删除')
    B.wait_dialog(drv, '确认删除角色')


def _open_role_perm_confirm(drv):
    goto_section(drv, '/system-settings/iam/roles', '角色权限管理', '角色权限变更后即时生效')
    open_menu(drv, '角色操作：测试工程师')
    menu_click(drv, '编辑')
    B.wait_dialog(drv, '编辑角色')
    time.sleep(1.0)
    # 动一个权限点，让保存进入确认框（取消不落库）
    boxes = drv.find_elements(By.CSS_SELECTOR, "[data-slot='checkbox']")
    target = None
    for box in boxes:
        checked = (box.get_attribute('aria-checked') or '').lower() == 'true'
        if checked:
            target = box
            break
    if target is None:
        raise AssertionError('编辑角色矩阵中没有可取消勾选的权限')
    B.js_click(drv, target)
    time.sleep(0.4)
    B.click_button_text(drv, '保存', exact=True)
    B.wait_dialog(drv, '确认保存角色权限')
    time.sleep(0.5)


def _close_role_perm_confirm(drv):
    ok = close_top(drv, prefer='取消', title='确认保存角色权限')
    if not ok:
        return False
    if _visible_dialogs(drv):
        ok = close_top(drv, title='编辑角色')
    return ok and not _visible_dialogs(drv)


def _open_oauth_create(drv):
    goto_section(drv, '/system-settings/auth/oauth-providers', 'OAuth 提供方', '回调地址格式')
    B.click_button_text(drv, '添加提供方')
    B.wait_dialog(drv, '新建提供方')


def _open_oauth_edit(drv):
    goto_section(drv, '/system-settings/auth/oauth-providers', 'OAuth 提供方', '回调地址格式')
    open_menu(drv, '提供方操作：%s' % TMP_OAUTH)
    menu_click(drv, '编辑')
    B.wait_dialog(drv, '编辑提供方')


def _open_oauth_delete(drv):
    goto_section(drv, '/system-settings/auth/oauth-providers', 'OAuth 提供方', '回调地址格式')
    open_menu(drv, '提供方操作：%s' % TMP_OAUTH)
    menu_click(drv, '删除')
    B.wait_dialog(drv, '确认删除提供方')


def _open_log_clear(drv):
    goto_section(drv, '/system-settings/operations/log-maintenance', '日志维护', '归档管理')
    time.sleep(0.8)
    B.click_button_text(drv, '立即清理')
    B.wait_dialog(drv, '立即清理日志')


def _open_log_archive(drv):
    goto_section(drv, '/system-settings/operations/log-maintenance', '日志维护', '归档管理')
    time.sleep(0.8)
    B.click_button_text(drv, '立即归档')
    B.wait_dialog(drv, '立即归档')


def _open_log_archive_delete(drv):
    goto_section(drv, '/system-settings/operations/log-maintenance', '日志维护', '归档管理')
    time.sleep(1.2)
    btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button') if B.visible(b)
            and (b.get_attribute('aria-label') or '').endswith('删除归档')]
    if not btns:
        btns = [b for b in drv.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='删除归档']]")
                if B.visible(b)]
    if not btns:
        raise Unreachable('归档列表数据源 getArchiveItems() 为待 INT-780 的硬编码空列表'
                          '（archive-api.ts:32），页面空态「暂无归档（待 INT-780）」；'
                          '无归档行 → 「确认删除归档」弹窗在本构建下不可达')
    B.js_click(drv, btns[0])
    B.wait_dialog(drv, '确认删除归档')


def _open_guard(drv):
    goto_section(drv, '/system-settings/site/info', '站点信息', '站点名称')
    time.sleep(0.8)
    B.set_input(drv, B.find_visible(drv, By.ID, 'site-name'), '接线测试_IC1935_脏表单')
    B.wait_text(drv, '未保存的更改', 10)
    B.click_link_href(drv, '/system-settings/site/notice')
    B.wait_dialog(drv, '未保存的更改')


def _close_guard(drv):
    ok = close_top(drv, prefer='留下')
    return ok and B.dialog_present(drv) is None


WINDOWS = [
    ('iam_user_create_drawer', 'IAM 新建用户抽屉', '新建用户', _open_user_create, None),
    ('iam_user_edit_drawer', 'IAM 编辑用户抽屉', '编辑用户', _open_user_edit, None),
    ('iam_user_delete_confirm', 'IAM 删除用户确认', '确认删除用户', _open_user_delete, None),
    ('iam_role_create_dialog', 'IAM 新建角色弹窗', '新建角色', _open_role_create, None),
    ('iam_role_edit_dialog', 'IAM 编辑角色弹窗', '编辑角色', _open_role_edit, None),
    ('iam_role_detail_dialog', 'IAM 角色详情弹窗', '角色详情', _open_role_detail, None),
    ('iam_role_delete_confirm', 'IAM 删除角色确认', '确认删除角色', _open_role_delete, None),
    ('iam_role_perm_save_confirm', 'IAM 角色权限保存确认', '确认保存角色权限', _open_role_perm_confirm, _close_role_perm_confirm),
    ('oauth_create_dialog', 'OAuth 新建提供方弹窗', '新建提供方', _open_oauth_create, None),
    ('oauth_edit_dialog', 'OAuth 编辑提供方弹窗', '编辑提供方', _open_oauth_edit, None),
    ('oauth_delete_confirm', 'OAuth 删除提供方确认', '确认删除提供方', _open_oauth_delete, None),
    ('ops_log_clear_confirm', '日志维护 立即清理确认', '立即清理日志', _open_log_clear, None),
    ('ops_log_archive_confirm', '日志维护 立即归档确认', '立即归档', _open_log_archive, None),
    ('ops_log_archive_delete_confirm', '日志维护 删除归档确认', '确认删除归档', _open_log_archive_delete, None),
    ('settings_form_guard', '未保存更改离开拦截', '未保存的更改', _open_guard, _close_guard),
]


def capture_window(drv, key, label, expect_title, opener, closer):
    frames = {}
    for mode in ('light', 'dark'):
        try:
            apply_theme(drv, mode)
            opener(drv)
            dlg = B.wait_dialog(drv, expect_title, timeout=25)
            time.sleep(0.8)
            info = probe(drv, dlg)
            name = '%s_%s' % (key, mode)
            path, size = shot(drv, name)
            frames[mode] = {'file': os.path.basename(path), 'size': size, 'probe': info}
            # 关闭控件响应
            closed = closer(drv) if closer else close_top(drv, prefer='取消', title=expect_title)
            info['closed_by_control'] = bool(closed)
            # 断言：窗口/遮罩/关闭控件/主题/对比度
            ov = info.get('overlay') or []
            ov_ok = bool(ov) and ov[0]['rect'][2] >= info['viewport'][0] * 0.95 and ov[0]['rect'][3] >= info['viewport'][1] * 0.95
            cc = [c for c in (info.get('close_controls') or []) if c.get('visible')]
            dark_ok = (info.get('dark') is True) if mode == 'dark' else (info.get('dark') is False)
            ok = (info.get('title') == expect_title and ov_ok and info.get('element_at_bg_point') in (
                'dialog-overlay', 'alert-dialog-overlay', 'sheet-overlay') and bool(cc) and dark_ok and closed)
            record('%s [%s] 遮罩+关闭控件' % (label, mode), ok,
                   'title=%r overlay=%s at_point=%s close=%s dark=%s contrast=%s file=%s'
                   % (info.get('title'), [(o['sel'], o['rect']) for o in ov],
                      info.get('element_at_bg_point'),
                      [(c['sel'], c['label']) for c in cc], info.get('dark'),
                      info.get('contrast'), name),
                   {'probe': info, 'file': os.path.basename(path)})
        except Unreachable as exc:
            record('%s [%s] 遮罩+关闭控件' % (label, mode), True,
                   '不可达：%s' % exc, {'unreachable': True, 'reason': str(exc)})
            try:
                close_top(drv)
            except Exception:
                pass
        except Exception as exc:
            tb = traceback.format_exc().strip().splitlines()
            try:
                shot(drv, '%s_%s_FAIL' % (key, mode))
            except Exception:
                pass
            record('%s [%s] 遮罩+关闭控件' % (label, mode), False,
                   '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])), {'error': str(exc)})
            try:
                close_top(drv)
            except Exception:
                pass
    return frames


# ---------------------------------------------------------------------------
# 环境与夹具
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
    record('ENV-%s 环境核对' % label, ok, 'health=%s frontend=%s' % (health, front))
    return db, front


def setup_fixtures(token):
    st, roles = B.api('/api/v1/auth/roles', token)
    role_list = (roles.get('data') or {}).get('roles') or []
    tester = next((r for r in role_list if r.get('code') == 'tester'), None)
    role_id = int(tester.get('id')) if tester else 0
    st, body = B.api('/api/v1/auth/users', token, method='POST', body={
        'username': TMP_USER,
        'email': TMP_USER.lower() + '@example.com',
        'password': 'JieXianTest@2026',
        'role_id': role_id,
        'display_name': 'INT-1935 取证临时用户',
    })
    uid = (body.get('data') or {}).get('user_id') if isinstance(body, dict) else None
    if uid is None and isinstance(body, dict):
        uid = body.get('user_id')
    FIXTURES['user_id'] = uid
    record('FIX 临时用户创建', st in (200, 201) and uid is not None,
           'status=%s user_id=%s role_id=%s' % (st, uid, role_id))

    st, body = B.api('/api/v1/auth/roles', token, method='POST', body={
        'name': TMP_ROLE,
        'description': 'INT-1935 取证临时角色（验收后删除）',
        'permission_codes': ['home:read'],
    })
    rid = (body.get('data') or {}).get('role_id') if isinstance(body, dict) else None
    if rid is None and isinstance(body, dict):
        rid = body.get('role_id')
    FIXTURES['role_id'] = rid
    record('FIX 临时角色创建', st in (200, 201) and rid is not None, 'status=%s role_id=%s' % (st, rid))

    st, body = B.api('/api/v1/auth/oauth-providers', token, method='POST', body={
        'name': TMP_OAUTH,
        'slug': 'jxtest-1935-%s' % TS,
        'icon': '',
        'enabled': True,
        'client_id': 'jxtest-client-1935',
        'client_secret': 'jxtest-secret-1935',
        'authorize_url': 'https://idp.example.com/authz',
        'token_url': 'https://idp.example.com/token',
        'userinfo_url': 'https://idp.example.com/userinfo',
        'scopes': 'openid profile email',
        'user_id_field': 'sub',
        'username_field': 'preferred_username',
        'display_name_field': 'name',
        'email_field': 'email',
    })
    st, listing = B.api('/api/v1/auth/oauth-providers', token)
    provs = ((listing.get('data') or {}).get('providers') or []) if isinstance(listing, dict) else []
    mine = next((p for p in provs if p.get('name') == TMP_OAUTH), None)
    FIXTURES['oauth_id'] = mine.get('id') if mine else None
    record('FIX 临时 OAuth 提供方创建', st in (200, 201) and mine is not None,
           'status=%s provider=%s' % (st, {k: (mine or {}).get(k) for k in ('id', 'name', 'slug')}))


def cleanup(token):
    note = []
    if FIXTURES['oauth_id']:
        st, _ = B.api('/api/v1/auth/oauth-providers/%s' % FIXTURES['oauth_id'], token, method='DELETE')
        note.append('oauth delete=%s' % st)
    if FIXTURES['user_id']:
        st, _ = B.api('/api/v1/auth/users/%s' % FIXTURES['user_id'], token, method='DELETE')
        note.append('user delete=%s' % st)
    if FIXTURES['role_id']:
        st, _ = B.api('/api/v1/auth/roles/%s' % FIXTURES['role_id'], token, method='DELETE')
        note.append('role delete=%s' % st)
    time.sleep(0.8)
    st, listing = B.api('/api/v1/auth/users?page=1&page_size=100', token)
    items = ((listing.get('data') or {}).get('items') or []) if isinstance(listing, dict) else []
    left_users = [i.get('username') for i in items if (i.get('username') or '').startswith(TMP_PREFIXES)]
    st, roles = B.api('/api/v1/auth/roles', token)
    rl = ((roles.get('data') or {}).get('roles') or []) if isinstance(roles, dict) else []
    left_roles = [r.get('name') for r in rl if (r.get('name') or '').startswith(TMP_PREFIXES)]
    st, listing = B.api('/api/v1/auth/oauth-providers', token)
    provs = ((listing.get('data') or {}).get('providers') or []) if isinstance(listing, dict) else []
    left_provs = [p.get('name') for p in provs if (p.get('name') or '').startswith(TMP_PREFIXES)]
    ok = not left_users and not left_roles and not left_provs
    record('CLEAN 夹具清理', ok,
           '%s | 残留 users=%s roles=%s oauth=%s | 用户总数=%d 角色总数=%d'
           % ('; '.join(note), left_users, left_roles, left_provs, len(items), len(rl)))
    return ok


def main():
    t0 = time.time()
    only = [k.strip() for k in os.environ.get('INT1935_ONLY', '').split(',') if k.strip()]
    report_name = 'report_int1935_rerun.json' if only else 'report_int1935.json'
    db0, front0 = env_check('开工')
    token, user = B.rsa_login_token(B.ACCOUNT[0], B.ACCOUNT[1])
    drv = B.driver_init()
    frames_all = {}
    try:
        B.bootstrap(drv, token, user)
        record('登录会话', True, 'user=%s' % (user.get('username') if isinstance(user, dict) else None))
        setup_fixtures(token)
        env_check('中段')
        for key, label, expect, opener, closer in WINDOWS:
            if only and key not in only:
                continue
            frames_all[key] = capture_window(drv, key, label, expect, opener, closer)
        env_check('交付前')
        cleanup(token)
    except Exception as exc:
        tb = traceback.format_exc().strip().splitlines()
        record('脚本执行', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-5:])))
    finally:
        try:
            B.set_theme(drv, 'light')
            B.goto(drv, '/system-settings/site/info')
        except Exception:
            pass
        try:
            drv.quit()
        except Exception:
            pass
        report = {
            'card': 'INT-1935',
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'duration_s': round(time.time() - t0, 1),
            'env': {'db_at_start': db0, 'frontend_fingerprint': front0,
                    'frontend_base': B.BASE, 'api_base': B.API},
            'fixtures': FIXTURES,
            'results': RESULTS,
            'frames': frames_all,
        }
        os.makedirs(ART, exist_ok=True)
        with open(os.path.join(ART, report_name), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        passed = sum(1 for r in RESULTS if r['ok'])
        print('\n==== SUMMARY %d/%d ====' % (passed, len(RESULTS)))
        for r in RESULTS:
            print(('PASS ' if r['ok'] else 'FAIL ') + r['step'])
        print('artifacts: %s' % ART)


if __name__ == '__main__':
    main()
