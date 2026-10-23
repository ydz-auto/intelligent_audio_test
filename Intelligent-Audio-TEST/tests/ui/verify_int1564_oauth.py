# -*- coding: utf-8 -*-
"""INT-1564 OAuth 提供方新建弹窗实测：Client Secret 必填 / 字段级校验 / Slug 格式 /
编辑态留空保留原值 / 后端 message 透出 / 创建-回读-删除闭环。

环境（工作区铁律）：docker 后端网关 http://localhost:15000；
本 run 的 React dev server http://localhost:5364（临时 rsbuild 配置代理 /api → 15000）。
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5364')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1564')
os.makedirs(ART, exist_ok=True)

PREFIX = '接线测试_INT1564_'
NAME = PREFIX + 'oauth'
SLUG = 'wiring-test-int1564'
ENDPOINTS = {
    'oauth-authz-endpoint': 'https://idp.example.com/authorize',
    'oauth-token-endpoint': 'https://idp.example.com/token',
    'oauth-userinfo-endpoint': 'https://idp.example.com/userinfo',
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


def posts(drv):
    return [r for r in net(drv) if r['method'] in ('POST', 'PUT') and '/auth/oauth-providers' in r['url']]


def reqs(drv):
    return [{k: r.get(k) for k in ('method', 'url', 'status', 'req', 'resp')} for r in posts(drv)]


def wait_dialog(drv):
    return WebDriverWait(drv, 20).until(
        EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))


def open_create(drv):
    js_click(drv, WebDriverWait(drv, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加提供方')]"))))
    wait_dialog(drv)
    time.sleep(0.4)


def fill(drv, field_id, value):
    el = drv.find_element(By.ID, field_id)
    js_click(drv, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)


def save(drv):
    js_click(drv, drv.find_element(
        By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='保存']"))
    time.sleep(0.6)


def dialog_error_texts(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] p.text-destructive")
    return [e.text.strip() for e in els if e.text.strip()]


def label_has_required(drv, for_id):
    return bool(drv.find_elements(
        By.XPATH, "//label[@for='%s']//span[@data-slot='required-indicator']" % for_id))


def toast_texts(drv):
    els = drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
    return [e.text.strip().replace('\n', ' ') for e in els if e.text.strip()]


def dump(name):
    path = os.path.join(ART, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    return path


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


def fill_all(drv, name=None, slug=None, secret='secret-abc', skip=()):
    values = {
        'oauth-name': name if name is not None else NAME,
        'oauth-slug': slug if slug is not None else SLUG,
        'oauth-client-id': 'client-int1564',
        'oauth-client-secret': secret,
    }
    values.update(ENDPOINTS)
    for field_id, value in values.items():
        if field_id in skip:
            continue
        fill(drv, field_id, value)


def find_row(drv, text):
    return drv.find_elements(By.XPATH, "//tr[contains(., '%s')]" % text)


def main():
    drv = webdriver.Chrome(options=_opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        # ---- 0. 清理上一轮残留（只动本卡前缀数据） ----
        open_page(drv)
        st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        for p in (data or {}).get('providers', []):
            if p.get('slug') == SLUG or str(p.get('name', '')).startswith(PREFIX):
                api(drv, '/api/v1/auth/oauth-providers/%s' % p['id'], 'DELETE')
                log('清理残留 provider id=%s' % p['id'])

        # ---- 1. 新建态 Client Secret 必填 + 空提交拦截 ----
        open_create(drv)
        has_star = label_has_required(drv, 'oauth-client-secret')
        step('新建态 Client Secret 标签带必填 *', value=has_star,
             screenshot='01-empty-secret-light.png')
        assert has_star, 'Client Secret 标签缺少必填 *'

        fill_all(drv, secret='', skip=('oauth-client-secret',))
        net_clear(drv)
        save(drv)
        errs = dialog_error_texts(drv)
        net_after = posts(drv)
        invalid = drv.find_element(By.ID, 'oauth-client-secret').get_attribute('aria-invalid')
        drv.save_screenshot(os.path.join(ART, '01-empty-secret-light.png'))
        step('空 secret + 空授权端点提交被前端拦截', errors=errs,
             posted=len(net_after), secret_aria_invalid=invalid)
        assert '请输入 Client Secret' in errs, errs
        assert not net_after, '空 secret 仍发出请求: %s' % net_after
        assert invalid == 'true'

        # ---- 2. 三端点必填：补 secret、清授权端点 ----
        fill(drv, 'oauth-client-secret', 'secret-abc')
        fill(drv, 'oauth-authz-endpoint', '')
        net_clear(drv)
        save(drv)
        errs = dialog_error_texts(drv)
        drv.save_screenshot(os.path.join(ART, '02-empty-endpoint-light.png'))
        step('空授权端点提交被前端拦截', errors=errs, posted=len(posts(drv)))
        assert '请输入授权端点' in errs, errs
        assert not posts(drv)

        # ---- 3. Slug 格式校验 ----
        fill(drv, 'oauth-authz-endpoint', ENDPOINTS['oauth-authz-endpoint'])
        fill(drv, 'oauth-slug', 'Footer_Test')
        net_clear(drv)
        save(drv)
        errs = dialog_error_texts(drv)
        drv.save_screenshot(os.path.join(ART, '03-slug-invalid-light.png'))
        step('Slug=Footer_Test 被前端拦截', errors=errs, posted=len(posts(drv)))
        assert '仅允许小写字母、数字与连字符' in errs, errs
        assert not posts(drv)

        # ---- 4. 创建闭环（合法值） ----
        fill(drv, 'oauth-slug', SLUG)
        net_clear(drv)
        save(drv)
        WebDriverWait(drv, 20).until(lambda d: not d.find_elements(By.XPATH, "//div[@role='dialog']"))
        time.sleep(1.5)
        created = posts(drv)
        step('创建提交', requests=reqs(drv),
             toasts=toast_texts(drv))
        assert created and created[0]['status'] == 201, created

        WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.XPATH, "//tr[contains(., '%s')]" % SLUG))
        drv.save_screenshot(os.path.join(ART, '04-created-list-light.png'))

        st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        row = [p for p in (data or {}).get('providers', []) if p.get('slug') == SLUG]
        assert len(row) == 1, data
        row = row[0]
        step('GET 回读创建结果', readback=row)
        assert row['name'] == NAME
        assert row['client_id'] == 'client-int1564'
        assert row['authorize_url'] == ENDPOINTS['oauth-authz-endpoint']
        assert row['token_url'] == ENDPOINTS['oauth-token-endpoint']
        assert row['userinfo_url'] == ENDPOINTS['oauth-userinfo-endpoint']
        assert row['has_client_secret'] is True
        provider_id = row['id']

        # ---- 5. 编辑态：secret 不必填、留空保留原值 ----
        js_click(drv, drv.find_element(By.XPATH, "//button[@aria-label='提供方操作：%s']" % NAME))
        js_click(drv, WebDriverWait(drv, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='menuitem'][normalize-space(.)='编辑']"))))
        wait_dialog(drv)
        time.sleep(0.6)
        edit_star = label_has_required(drv, 'oauth-client-secret')
        placeholder = drv.find_element(By.ID, 'oauth-client-secret').get_attribute('placeholder')
        value = drv.find_element(By.ID, 'oauth-client-secret').get_attribute('value')
        drv.save_screenshot(os.path.join(ART, '05-edit-secret-optional-light.png'))
        step('编辑态 Client Secret 无 *、留空保留原值', required=edit_star,
             placeholder=placeholder, value=value)
        assert not edit_star, '编辑态不应带必填 *'
        assert placeholder == '留空保留原值'
        assert not value

        net_clear(drv)
        save(drv)
        WebDriverWait(drv, 20).until(lambda d: not d.find_elements(By.XPATH, "//div[@role='dialog']"))
        time.sleep(1.2)
        puts = [r for r in net(drv) if r['method'] == 'PUT']
        step('编辑保存（空 secret）', requests=[{k: r.get(k) for k in ('method', 'url', 'status', 'req', 'resp')} for r in puts],
             toasts=toast_texts(drv))
        assert puts and puts[0]['status'] == 200, puts
        assert 'client_secret' not in puts[0]['req'], puts[0]['req']

        st, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        row = [p for p in (data or {}).get('providers', []) if p.get('slug') == SLUG][0]
        step('编辑后回读（has_client_secret 保留）', readback=row)
        assert row['has_client_secret'] is True

        # ---- 6. 后端 message 透出（重复 slug） ----
        open_create(drv)
        fill_all(drv)
        net_clear(drv)
        save(drv)
        time.sleep(1.5)
        toasts = toast_texts(drv)
        drv.save_screenshot(os.path.join(ART, '06-backend-message-toast-light.png'))
        st_post = [r['status'] for r in posts(drv)]
        step('重复 slug 提交 → 后端 message 透出 toast', toasts=toasts, status=st_post, requests=reqs(drv))
        assert any('slug 已被占用' in t for t in toasts), toasts
        assert not any('操作失败，请稍后重试' in t for t in toasts), toasts
        # 页面在提交后即关闭弹窗（现有行为），若仍开着则收起，避免影响下一步
        for el in drv.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']"):
            js_click(drv, el)
        time.sleep(0.5)

        # ---- 7. 深色：空 secret 字段级提示 + 后端 message toast ----
        set_theme(drv, 'dark')
        open_page(drv)
        open_create(drv)
        fill_all(drv, secret='', skip=('oauth-client-secret',))
        net_clear(drv)
        save(drv)
        errs = dialog_error_texts(drv)
        drv.save_screenshot(os.path.join(ART, '07-empty-secret-dark.png'))
        step('深色：空 secret 字段级提示', errors=errs, posted=len(posts(drv)))
        assert '请输入 Client Secret' in errs, errs
        assert not posts(drv)

        fill(drv, 'oauth-client-secret', 'secret-abc')
        net_clear(drv)
        save(drv)
        time.sleep(1.6)
        toasts = toast_texts(drv)
        drv.save_screenshot(os.path.join(ART, '08-backend-message-toast-dark.png'))
        step('深色：后端 message toast', toasts=toasts, status=[r['status'] for r in posts(drv)], requests=reqs(drv))
        assert any('slug 已被占用' in t for t in toasts), toasts

        # ---- 8. 清理本 run 数据 ----
        st, _, _ = api(drv, '/api/v1/auth/oauth-providers/%s' % provider_id, 'DELETE')
        st2, data, _ = api(drv, '/api/v1/auth/oauth-providers')
        left = [p['slug'] for p in (data or {}).get('providers', [])
                if str(p.get('name', '')).startswith(PREFIX) or p.get('slug') == SLUG]
        step('清理自建数据', delete_status=st, left=left)
        assert st < 300 and not left, left

        log('ALL CHECKS PASSED')
        return 0
    finally:
        dump('verify_int1564.json')
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
