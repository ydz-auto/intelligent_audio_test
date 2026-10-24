# -*- coding: utf-8 -*-
"""INT-1564 独立验收（测试工程师）：OAuth 提供方新建弹窗 Client Secret 必填 /
三端点必填 / Slug 格式 / 编辑态留空保留原值 / 后端 message 透出 / 创建-回读-删除闭环。

环境：docker 网关 http://127.0.0.1:15000；本 run React dev server :5364
（临时 rsbuild 配置代理 /api → 15000，用毕删除不提交）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5364')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1564_accept')
os.makedirs(ART, exist_ok=True)

PREFIX = '接线测试_INT1564_'
NAME = PREFIX + 'oauth'
SLUG = 'wiring-test-int1564'
CLIENT_ID = 'client-int1564'
SECRET = 'secret-int1564'
EP = {
    'authz': 'https://idp.example.com/authorize',
    'token': 'https://idp.example.com/token',
    'userinfo': 'https://idp.example.com/userinfo',
}
IDS = {
    'name': 'oauth-name',
    'slug': 'oauth-slug',
    'clientId': 'oauth-client-id',
    'clientSecret': 'oauth-client-secret',
    'authz': 'oauth-authz-endpoint',
    'token': 'oauth-token-endpoint',
    'userinfo': 'oauth-userinfo-endpoint',
}

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const body = (init && typeof init.body === 'string') ? init.body : '';
  const res = await __origFetch.apply(this, arguments);
  let text = '';
  try { text = await res.clone().text(); } catch (e) {}
  window.__net.push({url: url, method: method, status: res.status, req: body, resp: (text || '').slice(0, 800)});
  return res;
};
"""

evidence = {'steps': [], 'env': {'base': BASE, 'time': time.strftime('%Y-%m-%d %H:%M:%S')}}


def log(msg):
    print(msg, flush=True)


def step(name, shot=None, **kw):
    row = {'name': name}
    row.update(kw)
    if shot:
        row['screenshot'] = shot
    evidence['steps'].append(row)
    slim = {k: v for k, v in kw.items() if k in ('errors', 'posted', 'status', 'toasts', 'required', 'placeholder', 'value', 'readback', 'left')}
    log('[STEP] %s %s' % (name, json.dumps(slim, ensure_ascii=False)))


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def api(drv, path, method='GET', body=None):
    js = """
    const cb = arguments[arguments.length - 1];
    fetch(arguments[0], {method: arguments[1] || 'GET', headers: {'Content-Type': 'application/json'}, body: arguments[2] || undefined})
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


def writes(drv):
    """本页对 oauth-providers 的写请求（POST/PUT/DELETE）"""
    return [r for r in net(drv)
            if r['method'] in ('POST', 'PUT', 'DELETE') and '/auth/oauth-providers' in r['url']]


def reqs(drv):
    return [{k: r.get(k) for k in ('method', 'url', 'status', 'req', 'resp')} for r in writes(drv)]


def dialog(drv):
    return drv.find_element(By.CSS_SELECTOR, "[role='dialog']")


def dialog_open(drv):
    return bool(drv.find_elements(By.CSS_SELECTOR, "[role='dialog']"))


def wait_dialog(drv, timeout=20):
    return WebDriverWait(drv, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "[role='dialog']")))


def open_create(drv):
    js_click(drv, WebDriverWait(drv, 20).until(EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(normalize-space(.), '添加提供方')]"))))
    wait_dialog(drv)
    time.sleep(0.4)


def fill(drv, key, value):
    el = drv.find_element(By.ID, IDS[key])
    js_click(drv, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)


def fill_all(drv, name=NAME, slug=SLUG, client_id=CLIENT_ID, secret=SECRET,
             authz=EP['authz'], token=EP['token'], userinfo=EP['userinfo']):
    fill(drv, 'name', name)
    fill(drv, 'slug', slug)
    fill(drv, 'clientId', client_id)
    fill(drv, 'clientSecret', secret)
    fill(drv, 'authz', authz)
    fill(drv, 'token', token)
    fill(drv, 'userinfo', userinfo)


def save(drv):
    js_click(drv, dialog(drv).find_element(By.XPATH, ".//button[normalize-space(.)='保存']"))
    time.sleep(0.6)


def save_expect_blocked(drv, err_id, shot):
    """校验失败场景：点保存后弹窗仍在、无写请求、出现字段级错误"""
    net_clear(drv)
    save(drv)
    errs = dialog_error_texts(drv)
    shot_path = os.path.join(ART, shot)
    drv.save_screenshot(shot_path)
    el = drv.find_element(By.ID, err_id)
    return {
        'errors': errs,
        'posted': len(writes(drv)),
        'requests': reqs(drv),
        'still_open': dialog_open(drv),
        'aria_invalid': el.get_attribute('aria-invalid'),
        'aria_describedby': el.get_attribute('aria-describedby'),
        'error_text_near_field': field_error_text(drv, err_id),
    }


def field_error_text(drv, field_id):
    try:
        el = drv.find_element(By.ID, field_id)
        desc = el.get_attribute('aria-describedby')
        if desc:
            return drv.find_element(By.ID, desc).text.strip()
    except Exception:
        pass
    return ''


def dialog_error_texts(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] p.text-destructive")
    return [e.text.strip() for e in els if e.text.strip()]


def has_required(drv, field_id):
    return bool(drv.find_elements(
        By.XPATH, "//label[@for='%s']//span[@data-slot='required-indicator']" % field_id))


def label_text(drv, field_id):
    try:
        return drv.find_element(By.XPATH, "//label[@for='%s']" % field_id).text.strip().replace('\n', ' ')
    except Exception:
        return ''


def toasts(drv):
    els = drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
    return [e.text.strip().replace('\n', ' ') for e in els if e.text.strip()]


def close_extra_dialogs(drv):
    for el in drv.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']"):
        try:
            js_click(drv, el)
        except Exception:
            pass
    time.sleep(0.4)


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


def open_page(drv):
    drv.get(BASE + '/system-settings/auth/oauth-providers')
    WebDriverWait(drv, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//button[contains(normalize-space(.), '添加提供方')]")))
    time.sleep(1.2)


def main():
    drv = webdriver.Chrome(options=_opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    provider_id = None
    try:
        # ---------- 0. 清上一轮残留（仅本卡前缀） ----------
        open_page(drv)
        st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        for p in (data or {}).get('providers', []):
            if p.get('slug') == SLUG or str(p.get('name', '')).startswith(PREFIX):
                api(drv, '/api/v1/auth/oauth-providers/%s' % p['id'], 'DELETE')
                log('清理残留 id=%s' % p['id'])
        drv.refresh()
        time.sleep(1.5)

        # ---------- 1. 必填标记 ----------
        open_create(drv)
        marks = {k: has_required(drv, v) for k, v in IDS.items()}
        labels = {k: label_text(drv, v) for k, v in IDS.items()}
        drv.save_screenshot(os.path.join(ART, '01-required-stars-light.png'))
        step('新建态必填标记（7 项均 *）', shot='01-required-stars-light.png',
             required=marks, labels=labels, requests=[])
        assert all(marks.values()), '缺少必填标记: %s' % marks
        assert labels['clientSecret'].startswith('Client Secret'), labels['clientSecret']

        # ---------- 2. 空 Client Secret 拦截 ----------
        fill_all(drv, secret='')
        r = save_expect_blocked(drv, IDS['clientSecret'], '02-empty-secret-light.png')
        step('新建态空 Client Secret 提交被前端拦截', shot='02-empty-secret-light.png', **r)
        assert '请输入 Client Secret' in r['errors'], r
        assert r['posted'] == 0, r
        assert r['still_open'], '弹窗被关闭（说明发起了提交）'
        assert r['aria_invalid'] == 'true', r
        assert r['error_text_near_field'] == '请输入 Client Secret', r

        # ---------- 3. 三端点分别留空拦截 ----------
        fill(drv, 'clientSecret', SECRET)
        cases = [
            ('authz', '请输入授权端点', '03-empty-authz-light.png'),
            ('token', '请输入 Token 端点', '04-empty-token-light.png'),
            ('userinfo', '请输入用户信息端点', '05-empty-userinfo-light.png'),
        ]
        for key, msg, shot in cases:
            fill(drv, key, '')
            r = save_expect_blocked(drv, IDS[key], shot)
            step('留空 %s 提交被前端拦截' % msg.replace('请输入', ''), shot=shot, **r)
            assert msg in r['errors'], r
            assert r['posted'] == 0, r
            assert r['still_open']
            assert r['aria_invalid'] == 'true', r
            fill(drv, key, {'authz': EP['authz'], 'token': EP['token'], 'userinfo': EP['userinfo']}[key])

        # ---------- 4. Slug 格式 ----------
        for bad in ('Footer_Test', 'Footer-Test', 'footer test', 'footer--test'):
            fill(drv, 'slug', bad)
            r = save_expect_blocked(drv, IDS['slug'], '06-slug-invalid-light.png')
            step('Slug 非法值 %s 被前端拦截' % bad, shot='06-slug-invalid-light.png', **r)
            assert '仅允许小写字母、数字与连字符' in r['errors'], r
            assert r['posted'] == 0, r
        # 合法值应放行：此处只验证错误提示消失（真正提交在下一步）
        fill(drv, 'slug', SLUG)
        assert not dialog_error_texts(drv), dialog_error_texts(drv)

        # ---------- 5. 创建闭环 ----------
        net_clear(drv)
        save(drv)
        WebDriverWait(drv, 25).until(lambda d: not d.find_elements(By.CSS_SELECTOR, "[role='dialog']"))
        time.sleep(1.8)
        created = writes(drv)
        toasts_create = toasts(drv)
        step('合法提交创建', requests=reqs(drv), toasts=toasts_create, status=[w['status'] for w in created])
        assert created and created[0]['status'] == 201, created
        body = json.loads(created[0]['req'])
        assert body.get('client_secret') == SECRET, body
        assert body.get('slug') == SLUG, body

        WebDriverWait(drv, 25).until(lambda d: d.find_elements(By.XPATH, "//tr[contains(., '%s')]" % SLUG))
        drv.save_screenshot(os.path.join(ART, '07-created-list-light.png'))
        row_text = drv.find_element(By.XPATH, "//tr[contains(., '%s')]" % SLUG).text.replace('\n', ' ')
        step('列表出现新行', shot='07-created-list-light.png', row=row_text)
        assert NAME in row_text, row_text

        st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        rows = [p for p in (data or {}).get('providers', []) if p.get('slug') == SLUG]
        assert len(rows) == 1, data
        row = rows[0]
        provider_id = row['id']
        step('GET 回读创建结果', readback={k: row.get(k) for k in (
            'name', 'slug', 'client_id', 'authorize_url', 'token_url', 'userinfo_url', 'has_client_secret', 'enabled')})
        assert row['name'] == NAME, row
        assert row['client_id'] == CLIENT_ID, row
        assert row['authorize_url'] == EP['authz'], row
        assert row['token_url'] == EP['token'], row
        assert row['userinfo_url'] == EP['userinfo'], row
        assert row['has_client_secret'] is True, row

        # ---------- 6. 编辑态：无 *、留空保留原值 ----------
        js_click(drv, drv.find_element(By.XPATH, "//button[@aria-label='提供方操作：%s']" % NAME))
        js_click(drv, WebDriverWait(drv, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='menuitem'][normalize-space(.)='编辑']"))))
        wait_dialog(drv)
        time.sleep(0.7)
        edit_star = has_required(drv, IDS['clientSecret'])
        secret_input = drv.find_element(By.ID, IDS['clientSecret'])
        placeholder = secret_input.get_attribute('placeholder')
        secret_value = secret_input.get_attribute('value') or ''
        drv.save_screenshot(os.path.join(ART, '08-edit-secret-optional-light.png'))
        net_clear(drv)
        save(drv)
        WebDriverWait(drv, 25).until(lambda d: not d.find_elements(By.CSS_SELECTOR, "[role='dialog']"))
        time.sleep(1.5)
        puts = [w for w in writes(drv) if w['method'] == 'PUT']
        step('编辑态 Client Secret 无 *、留空保留原值', shot='08-edit-secret-optional-light.png',
             required=edit_star, placeholder=placeholder, value=secret_value,
             requests=reqs(drv), toasts=toasts(drv))
        assert not edit_star, '编辑态不应带必填 *'
        assert placeholder == '留空保留原值', placeholder
        assert secret_value == '', secret_value
        assert puts and puts[0]['status'] == 200, puts
        put_body = json.loads(puts[0]['req'])
        assert 'client_secret' not in put_body, put_body

        st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        row_after = [p for p in (data or {}).get('providers', []) if p.get('slug') == SLUG][0]
        step('编辑后回读 has_client_secret 保留', readback={'has_client_secret': row_after.get('has_client_secret')})
        assert row_after['has_client_secret'] is True, row_after

        # ---------- 7. 后端 message 透出（重复 slug） ----------
        close_extra_dialogs(drv)
        open_create(drv)
        fill_all(drv)
        net_clear(drv)
        save(drv)
        time.sleep(2.0)
        dup_writes = writes(drv)
        t = toasts(drv)
        drv.save_screenshot(os.path.join(ART, '09-backend-message-toast-light.png'))
        backend_msg = ''
        if dup_writes:
            try:
                backend_msg = (json.loads(dup_writes[0]['resp']) or {}).get('message') or ''
            except Exception:
                backend_msg = ''
        step('重复 slug 提交 → toast 透出后端 message', shot='09-backend-message-toast-light.png',
             requests=reqs(drv), toasts=t, status=[w['status'] for w in dup_writes], backend_message=backend_msg)
        assert dup_writes and dup_writes[0]['status'] >= 400, dup_writes
        assert backend_msg, '未捕获后端 message'
        assert any(backend_msg in x for x in t), (backend_msg, t)
        assert not any('操作失败，请稍后重试' in x for x in t), t

        # ---------- 8. 深色：空 secret 字段级提示 + 后端 message toast ----------
        set_theme(drv, 'dark')
        open_page(drv)
        open_create(drv)
        fill_all(drv, secret='')
        r = save_expect_blocked(drv, IDS['clientSecret'], '10-empty-secret-dark.png')
        step('深色：空 Client Secret 字段级提示', shot='10-empty-secret-dark.png', **r)
        assert '请输入 Client Secret' in r['errors'], r
        assert r['posted'] == 0, r

        fill(drv, 'clientSecret', SECRET)
        net_clear(drv)
        save(drv)
        time.sleep(2.0)
        dark_writes = writes(drv)
        t2 = toasts(drv)
        drv.save_screenshot(os.path.join(ART, '11-backend-message-toast-dark.png'))
        step('深色：后端 message toast', shot='11-backend-message-toast-dark.png',
             requests=reqs(drv), toasts=t2, status=[w['status'] for w in dark_writes])
        assert any(backend_msg in x for x in t2), (backend_msg, t2)

        # ---------- 9. 删除 + 清理核对 ----------
        set_theme(drv, 'light')
        open_page(drv)
        js_click(drv, drv.find_element(By.XPATH, "//button[@aria-label='提供方操作：%s']" % NAME))
        js_click(drv, WebDriverWait(drv, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='menuitem'][normalize-space(.)='删除']"))))
        # ConfirmDialog 走 AlertDialog → role='alertdialog'
        confirm = WebDriverWait(drv, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//*[@role='alertdialog']//button[normalize-space(.)='删除']")))
        time.sleep(0.5)
        drv.save_screenshot(os.path.join(ART, '12-delete-confirm-light.png'))
        js_click(drv, confirm)
        WebDriverWait(drv, 25).until(lambda d: not d.find_elements(By.XPATH, "//tr[contains(., '%s')]" % SLUG))
        time.sleep(1.0)
        drv.save_screenshot(os.path.join(ART, '12-after-delete-light.png'))
        st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        left = [p.get('slug') for p in (data or {}).get('providers', [])
                if p.get('slug') == SLUG or str(p.get('name', '')).startswith(PREFIX)]
        step('删除后列表消失、GET 无残留', shot='12-after-delete-light.png', left=left, status=st)
        assert not left, left

        log('ALL CHECKS PASSED')
        return 0
    finally:
        # 兜底清理：无论成败都不留本卡数据
        try:
            if provider_id:
                st, _, _ = api(drv, '/api/v1/auth/oauth-providers/%s' % provider_id, 'DELETE')
                log('兜底删除 id=%s status=%s' % (provider_id, st))
            st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
            left = [p.get('slug') for p in (data or {}).get('providers', [])
                    if p.get('slug') == SLUG or str(p.get('name', '')).startswith(PREFIX)]
            log('结束后残留: %s' % left)
            evidence['cleanup_left'] = left
        except Exception as exc:
            log('兜底清理失败: %s' % exc)
        path = os.path.join(ART, 'verify_int1564.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)
        log('evidence -> %s' % path)
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
