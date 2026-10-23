# -*- coding: utf-8 -*-
"""INT-1586 角色权限管理弹窗实测：新建名称空/全空格前端拦截（零请求 + 红字 + aria-invalid）、
失败不关弹窗且透出后端 message、编辑态同类、删除失败 toast 回归、创建-回读-删除闭环。

环境（工作区铁律）：docker 后端网关 http://localhost:15000；
本卡 React dev server http://127.0.0.1:5386（临时 rsbuild 配置代理 /api → 15000）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5386')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1586')
REPORT = os.path.join(HERE, 'reports', 'int1586_roles_validation.json')
os.makedirs(ART, exist_ok=True)
os.makedirs(os.path.dirname(REPORT), exist_ok=True)

DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'

PREFIX = '接线测试_INT1586_'
ROLE_NAME = PREFIX + '空名校验'
ROLE_EDIT = PREFIX + '编辑角色'
ROLE_DELETE = PREFIX + '删除回归'

FETCH_PATCH = r"""
window.__net = [];
window.__forceDeleteFail = false;
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const body = (init && typeof init.body === 'string') ? init.body : '';
  if (window.__forceDeleteFail && method === 'DELETE' && url.indexOf('/auth/roles/') >= 0) {
    const res = new Response(JSON.stringify({success:false, code:203, message:'该角色仍有用户归属，请先转移用户'}),
      {status: 409, headers: {'Content-Type': 'application/json'}});
    window.__net.push({url: url, method: method, status: 409, req: body, resp: 'synthetic-409'});
    return res;
  }
  const res = await __origFetch.apply(this, arguments);
  let text = '';
  try { text = await res.clone().text(); } catch (e) {}
  window.__net.push({url: url, method: method, status: res.status, req: body, resp: (text || '').slice(0, 600)});
  return res;
};
"""

evidence = {'steps': []}


def log(msg):
    print(msg, flush=True)


def step(name, **kw):
    row = {'name': name}
    row.update(kw)
    evidence['steps'].append(row)
    log('[STEP] %s %s' % (name, json.dumps(kw, ensure_ascii=False)))


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def api(drv, path, method='GET', body=None):
    js = """
    const cb = arguments[arguments.length - 1];
    const headers = {'Content-Type': 'application/json'};
    fetch(arguments[0], {method: arguments[1] || 'GET', headers: headers, body: arguments[2] || undefined})
      .then(async r => cb({status: r.status, body: await r.text()}))
      .catch(e => cb({status: 0, body: String(e)}));
    """
    raw = drv.execute_async_script(js, path, method, body)
    try:
        payload = json.loads(raw['body'])
    except Exception:
        payload = raw['body']
    data = payload.get('data') if isinstance(payload, dict) else payload
    return raw['status'], data, payload


def net_clear(drv):
    drv.execute_script('window.__net = [];')


def net(drv):
    return drv.execute_script('return window.__net || [];')


def role_writes(drv):
    return [
        r for r in net(drv)
        if r['method'] in ('POST', 'PUT', 'DELETE') and '/auth/roles' in r['url']
        and '/permissions' not in r['url']
    ]


def perm_writes(drv):
    return [r for r in net(drv) if '/permissions' in r['url'] and r['method'] == 'POST']


def brief(rows):
    return [{k: r.get(k) for k in ('method', 'url', 'status', 'req', 'resp')} for r in rows]


def wait_dialog(drv):
    return WebDriverWait(drv, 20).until(
        EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))


def dialog_open(drv):
    return bool(drv.find_elements(By.XPATH, "//div[@role='dialog']"))


def open_page(drv):
    drv.get(BASE + '/system-settings/iam/roles')
    WebDriverWait(drv, 90).until(EC.presence_of_element_located(
        (By.XPATH, "//button[contains(normalize-space(.), '新建角色')]")))
    time.sleep(1.5)


def open_create(drv):
    js_click(drv, WebDriverWait(drv, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新建角色')]"))))
    wait_dialog(drv)
    time.sleep(0.5)


def fill(drv, value):
    el = drv.find_element(By.ID, 'role-name')
    js_click(drv, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)


def fill_desc(drv, value):
    el = drv.find_element(By.ID, 'role-description')
    js_click(drv, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)


def click_dialog_btn(drv, text):
    js_click(drv, drv.find_element(
        By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='%s']" % text))
    time.sleep(0.5)


def dialog_errors(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] p.text-destructive")
    return [e.text.strip() for e in els if e.text.strip()]


def aria_invalid(drv, field_id):
    return drv.find_element(By.ID, field_id).get_attribute('aria-invalid')


def toast_texts(drv):
    els = drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
    return [e.text.strip().replace('\n', ' ') for e in els if e.text.strip()]


def pick_permissions(drv, module_name='日志'):
    """在矩阵里对指定模块点「全选」，返回该模块徽标文本。"""
    btn = WebDriverWait(drv, 10).until(EC.element_to_be_clickable((
        By.XPATH,
        "//div[@role='dialog']//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'border-border/70')][1]"
        "//button[normalize-space(.)='全选']" % module_name)))
    js_click(drv, btn)
    time.sleep(0.4)
    badge = drv.find_element(
        By.XPATH,
        "//div[@role='dialog']//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'border-border/70')][1]"
        "//span[contains(@class,'Badge') or @data-slot='badge'][1]" % module_name)
    return badge.text.strip()


def matrix_selected_total(drv):
    badges = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] [data-slot='badge']")
    total = 0
    for b in badges:
        t = b.text.strip()
        if t.startswith('已选'):
            try:
                total += int(t.split('已选')[1].split('/')[0].strip())
            except Exception:
                pass
    return total


def close_dialog_if_open(drv):
    for el in drv.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']"):
        js_click(drv, el)
        time.sleep(0.5)


def _opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1100')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    return o


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    drv.get('about:blank')
    time.sleep(0.3)


def main():
    svc = Service(executable_path=DRIVER)
    drv = webdriver.Chrome(service=svc, options=_opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    failed = []
    created_ids = []
    try:
        open_page(drv)

        # ---- 0. 清理上一轮残留（只动本卡前缀数据） ----
        st, data, _ = api(drv, '/api/v1/auth/roles')
        for role in (data or {}).get('roles', []):
            if str(role.get('name', '')).startswith(PREFIX):
                api(drv, '/api/v1/auth/roles/%s' % role['id'], 'DELETE')
                log('清理残留 role id=%s' % role['id'])
        drv.refresh()
        time.sleep(2)

        # ---- 1. 新建态名称留空：零请求 + 红字 + aria-invalid ----
        open_create(drv)
        click_dialog_btn(drv, '创建')
        errs = dialog_errors(drv)
        posted = role_writes(drv)
        invalid = aria_invalid(drv, 'role-name')
        drv.save_screenshot(os.path.join(ART, '01-empty-name-light.png'))
        step('名称留空提交被前端拦截', errors=errs, posted=len(posted), aria_invalid=invalid)
        if '请输入角色名称' not in errs:
            failed.append('空名未出现红字: %s' % errs)
        if posted:
            failed.append('空名仍发出请求: %s' % brief(posted))
        if invalid != 'true':
            failed.append('空名 aria-invalid != true: %s' % invalid)

        # ---- 2. 全空格同样拦截 ----
        fill(drv, '   ')
        net_clear(drv)
        click_dialog_btn(drv, '创建')
        errs = dialog_errors(drv)
        drv.save_screenshot(os.path.join(ART, '02-blank-name-light.png'))
        step('名称全空格提交被前端拦截', errors=errs, posted=len(role_writes(drv)))
        if '请输入角色名称' not in errs:
            failed.append('全空格未出现红字: %s' % errs)
        if role_writes(drv):
            failed.append('全空格仍发出请求: %s' % brief(role_writes(drv)))

        # ---- 3. 合法创建：勾权限 → 成功 toast + 关弹窗 + GET 回读 ----
        fill(drv, ROLE_NAME)
        badge = pick_permissions(drv, '日志')
        selected = matrix_selected_total(drv)
        net_clear(drv)
        click_dialog_btn(drv, '创建')
        WebDriverWait(drv, 30).until(lambda d: not dialog_open(d))
        time.sleep(1.5)
        writes = role_writes(drv)
        toasts = toast_texts(drv)
        drv.save_screenshot(os.path.join(ART, '03-created-light.png'))
        step('合法创建', requests=brief(writes), toasts=toasts,
             selected=selected, log_badge=badge)
        if not writes or writes[0]['status'] not in (200, 201):
            failed.append('创建请求失败: %s' % brief(writes))
        if not any('角色已创建' in t for t in toasts):
            failed.append('创建成功 toast 缺失: %s' % toasts)
        sent_codes = json.loads(writes[0]['req'] or '{}').get('permission_codes', []) if writes else []
        if len(sent_codes) != selected or selected == 0:
            failed.append('权限数与勾选不一致: sent=%s selected=%s' % (len(sent_codes), selected))

        st, data, _ = api(drv, '/api/v1/auth/roles')
        rows = [r for r in (data or {}).get('roles', []) if r.get('name') == ROLE_NAME]
        if not rows:
            failed.append('GET 回读不到新角色')
        else:
            new_role = rows[0]
            created_ids.append(new_role['id'])
            if sorted(new_role.get('permissions', [])) != sorted(sent_codes):
                failed.append('回读权限码与提交不一致: %s vs %s'
                              % (new_role.get('permissions'), sent_codes))
        step('GET 回读新角色', readback=rows)

        # ---- 4. 构造后端拒绝：名称与系统角色重名（admin） ----
        open_create(drv)
        fill(drv, 'admin')
        fill_desc(drv, '重名失败保留描述')
        pick_permissions(drv, '首页')
        net_clear(drv)
        click_dialog_btn(drv, '创建')
        WebDriverWait(drv, 30).until(lambda d: role_writes(d))
        time.sleep(1.5)
        writes = role_writes(drv)
        toasts = toast_texts(drv)
        still_open = dialog_open(drv)
        name_value = drv.find_element(By.ID, 'role-name').get_attribute('value')
        desc_value = drv.find_element(By.ID, 'role-description').get_attribute('value')
        kept_selected = matrix_selected_total(drv)
        drv.save_screenshot(os.path.join(ART, '04-failure-keeps-dialog-light.png'))
        step('后端拒绝（重名 admin）', requests=brief(writes), toasts=toasts,
             dialog_open=still_open, input_name=name_value, desc=desc_value,
             selected=kept_selected)
        if not writes or writes[0]['status'] != 400:
            failed.append('重名请求未返回 400: %s' % brief(writes))
        if not any('角色名已存在' in t for t in toasts):
            failed.append('失败 toast 未透出后端 message: %s' % toasts)
        if any(t.strip() == '角色保存失败' for t in toasts):
            failed.append('失败 toast 仍是通用文案')
        if not still_open:
            failed.append('失败后弹窗被关闭')
        if name_value != 'admin' or desc_value != '重名失败保留描述':
            failed.append('失败后输入丢失: name=%r desc=%r' % (name_value, desc_value))
        if kept_selected != selected and kept_selected == 0:
            failed.append('失败后权限矩阵被清空')

        # ---- 5. 失败后不关弹窗直接改名再提交 → 成功 ----
        fill(drv, ROLE_NAME + '改名')
        net_clear(drv)
        click_dialog_btn(drv, '创建')
        WebDriverWait(drv, 30).until(lambda d: not dialog_open(d))
        time.sleep(1.2)
        writes = role_writes(drv)
        toasts = toast_texts(drv)
        step('失败后改名重提', requests=brief(writes), toasts=toasts)
        if not writes or writes[0]['status'] not in (200, 201):
            failed.append('改名重提失败: %s' % brief(writes))
        st, data, _ = api(drv, '/api/v1/auth/roles')
        rows = [r for r in (data or {}).get('roles', []) if r.get('name') == ROLE_NAME + '改名']
        if rows:
            created_ids.append(rows[0]['id'])
        else:
            failed.append('改名后 GET 读不到角色')

        # ---- 6a. 编辑态清空名称：前端拦截零请求 ----
        st, data, _ = api(drv, '/api/v1/auth/roles/%s' % created_ids[-1])
        st, data, _ = api(drv, '/api/v1/auth/roles')
        target = [r for r in (data or {}).get('roles', []) if r.get('name') == ROLE_NAME + '改名'][0]
        drv.refresh()
        time.sleep(2)
        js_click(drv, WebDriverWait(drv, 20).until(EC.element_to_be_clickable(
            (By.XPATH, "//button[@aria-label='角色操作：%s']" % target['name']))))
        js_click(drv, WebDriverWait(drv, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='menuitem'][normalize-space(.)='编辑']"))))
        wait_dialog(drv)
        time.sleep(0.6)
        fill(drv, '')
        net_clear(drv)
        click_dialog_btn(drv, '保存')
        errs = dialog_errors(drv)
        confirm_open = bool(drv.find_elements(
            By.XPATH, "//*[normalize-space(.)='确认保存角色权限']"))
        drv.save_screenshot(os.path.join(ART, '05-edit-empty-name-light.png'))
        step('编辑态清空名称被拦截', errors=errs, posted=len(role_writes(drv)),
             confirm_open=confirm_open)
        if '请输入角色名称' not in errs:
            failed.append('编辑态空名无红字: %s' % errs)
        if role_writes(drv) or perm_writes(drv):
            failed.append('编辑态空名仍发请求')
        if confirm_open:
            failed.append('编辑态空名仍弹二次确认')

        # ---- 6b. 编辑态后端失败：弹窗不关、输入与矩阵保留 ----
        fill(drv, 'admin')
        net_clear(drv)
        click_dialog_btn(drv, '保存')
        WebDriverWait(drv, 15).until(EC.presence_of_element_located(
            (By.XPATH, "//button[normalize-space(.)='确认保存']")))
        js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='确认保存']"))
        WebDriverWait(drv, 30).until(lambda d: role_writes(d))
        time.sleep(1.5)
        writes = role_writes(drv)
        toasts = toast_texts(drv)
        still_open = dialog_open(drv)
        name_value = drv.find_element(By.ID, 'role-name').get_attribute('value')
        kept_selected = matrix_selected_total(drv)
        drv.save_screenshot(os.path.join(ART, '06-edit-failure-keeps-dialog-light.png'))
        step('编辑态后端拒绝（重名）', requests=brief(writes), toasts=toasts,
             dialog_open=still_open, input_name=name_value, selected=kept_selected)
        if not writes or writes[0]['status'] != 400:
            failed.append('编辑重名未 400: %s' % brief(writes))
        if not any('角色名已存在' in t for t in toasts):
            failed.append('编辑失败 toast 未透出后端 message: %s' % toasts)
        if not still_open:
            failed.append('编辑失败后弹窗被关闭')
        if name_value != 'admin':
            failed.append('编辑失败后输入丢失: %r' % name_value)
        if kept_selected == 0:
            failed.append('编辑失败后权限矩阵被清空')

        # 恢复名称并成功保存（验证输入未被吞）
        fill(drv, ROLE_NAME + '改名')
        net_clear(drv)
        click_dialog_btn(drv, '保存')
        WebDriverWait(drv, 15).until(EC.presence_of_element_located(
            (By.XPATH, "//button[normalize-space(.)='确认保存']")))
        js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='确认保存']"))
        WebDriverWait(drv, 40).until(lambda d: not dialog_open(d))
        time.sleep(1.2)
        step('编辑态失败后重提成功', requests=brief(role_writes(drv)),
             permissions=brief(perm_writes(drv)), toasts=toast_texts(drv))

        # ---- 7. 删除失败 toast 透出后端 message（合成 409 注入，非应用 mock） ----
        # 先自建一个可删角色
        st, data, _ = api(drv, '/api/v1/auth/roles', 'POST',
                          json.dumps({'name': ROLE_DELETE, 'description': '删除回归',
                                      'permission_codes': ['home:read']}))
        if st in (200, 201):
            created_ids.append((data or {}).get('role_id'))
        drv.refresh()
        time.sleep(2)
        js_click(drv, WebDriverWait(drv, 20).until(EC.element_to_be_clickable(
            (By.XPATH, "//button[@aria-label='角色操作：%s']" % ROLE_DELETE))))
        js_click(drv, WebDriverWait(drv, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='menuitem'][normalize-space(.)='删除']"))))
        WebDriverWait(drv, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//button[normalize-space(.)='删除']")))
        drv.execute_script('window.__forceDeleteFail = true;')
        net_clear(drv)
        js_click(drv, drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除']")[-1])
        time.sleep(1.8)
        toasts = toast_texts(drv)
        deletes = [r for r in net(drv) if r['method'] == 'DELETE']
        drv.execute_script('window.__forceDeleteFail = false;')
        drv.save_screenshot(os.path.join(ART, '07-delete-fail-toast-light.png'))
        step('删除失败 toast 透出后端 message', requests=brief(deletes), toasts=toasts)
        if not any('请先转移用户' in t for t in toasts):
            failed.append('删除失败 toast 未透出后端 message: %s' % toasts)
        time.sleep(1.2)

        # ---- 8. 深色：空名校验态 + 失败保留态 ----
        set_theme(drv, 'dark')
        open_page(drv)
        open_create(drv)
        click_dialog_btn(drv, '创建')
        errs = dialog_errors(drv)
        drv.save_screenshot(os.path.join(ART, '08-empty-name-dark.png'))
        step('深色：空名校验态', errors=errs, posted=len(role_writes(drv)))
        if '请输入角色名称' not in errs:
            failed.append('深色空名无红字')

        fill(drv, 'admin')
        net_clear(drv)
        click_dialog_btn(drv, '创建')
        WebDriverWait(drv, 30).until(lambda d: role_writes(d))
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ART, '09-failure-keeps-dialog-dark.png'))
        step('深色：失败保留态', dialog_open=dialog_open(drv), toasts=toast_texts(drv),
             requests=brief(role_writes(drv)))
        if not dialog_open(drv):
            failed.append('深色失败态弹窗被关闭')
        close_dialog_if_open(drv)

        # ---- 9. 清理：业务删除接口删本卡角色并复核列表消失 ----
        st, data, _ = api(drv, '/api/v1/auth/roles')
        leftovers = [r for r in (data or {}).get('roles', [])
                     if str(r.get('name', '')).startswith(PREFIX)]
        deleted = []
        for role in leftovers:
            code, _, _ = api(drv, '/api/v1/auth/roles/%s' % role['id'], 'DELETE')
            deleted.append({'id': role['id'], 'name': role['name'], 'status': code})
        st, data, _ = api(drv, '/api/v1/auth/roles')
        remaining = [r['name'] for r in (data or {}).get('roles', [])
                     if str(r.get('name', '')).startswith(PREFIX)]
        drv.refresh()
        time.sleep(2)
        drv.save_screenshot(os.path.join(ART, '10-after-cleanup-light.png'))
        step('清理本卡角色', deleted=deleted, remaining=remaining)
        if remaining:
            failed.append('清理后仍残留: %s' % remaining)
    finally:
        evidence['failed'] = failed
        with open(REPORT, 'w', encoding='utf-8') as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)
        drv.quit()
    log('REPORT %s' % REPORT)
    log('FAILED %s' % json.dumps(failed, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
