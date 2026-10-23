# -*- coding: utf-8 -*-
"""INT-1549 验收：评估维度页「编辑分类」必须携带 id 走 PUT，保存失败不得静默。

步骤（真实库 docker 栈 http://localhost:15000；前端本 run dev server 5301）：
1. 分组视图 → 编辑分类 A：改名保存；断言请求为 PUT /evaluation/categories/{A.id}，
   回读接口只有改名后的分类、原名消失（不再出现重复分类）；
2. 编辑分类 B：改成 A 的新名字（重名）保存；断言后端 400、弹窗保持打开、
   行内错误 role=alert 与 toast 出现；
3. 浅色/深色截图；结束时取消弹窗并清理本 run 的「接线测试_INT1549_」数据。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5301')
API_BASE = os.environ.get('API_BASE', 'http://localhost:15000')
ART = os.environ.get('ART_DIR', 'tests/ui/artifacts/int1549')
PREFIX = '接线测试_INT1549_'
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
  const res = await __origFetch.apply(this, arguments);
  try { window.__net.push({url: url, method: method, status: res.status, t: Date.now()}); } catch (e) {}
  return res;
};
"""


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def make_driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    drv = webdriver.Chrome(options=o)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def drain_perf(drv):
    entries = []
    for raw in drv.get_log('performance'):
        try:
            msg = json.loads(raw['message'])
        except Exception:
            continue
        entries.append(msg)
    return entries


def net_from_perf(entries):
    """performance log → [(method, url, status)]（msg['message'] 双层包裹）"""
    reqs = {}
    out = []
    for m in entries:
        mm = m.get('message', {})
        method = mm.get('method')
        params = (mm.get('params') or {})
        if method == 'Network.requestWillBeSent':
            req = params.get('request', {})
            reqs[params.get('requestId')] = (req.get('method'), req.get('url'))
        elif method == 'Network.responseReceived':
            info = reqs.get(params.get('requestId'))
            if info:
                out.append((info[0], info[1], params.get('response', {}).get('status')))
    return out


def js_net(drv):
    return drv.execute_script('return window.__net || []')


def api(drv, path, method='GET', body=None):
    js = """
    const cb = arguments[arguments.length - 1];
    fetch(arguments[0], {method: arguments[1] || 'GET',
      headers: {'Content-Type': 'application/json'}, body: arguments[2] || undefined})
      .then(async r => cb({status: r.status, body: await r.text()}))
      .catch(e => cb({status: 0, body: String(e)}));
    """
    raw = drv.execute_async_script(js, path if path.startswith('http') else API_BASE + path, method, body)
    try:
        payload = json.loads(raw['body'])
    except Exception:
        payload = raw['body']
    return raw['status'], payload


def categories(drv):
    status, payload = api(drv, '/api/v1/evaluation/categories')
    items = (payload.get('data') or {}).get('items', []) if isinstance(payload, dict) else []
    return status, items


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.get('about:blank')
    drv.get(BASE + '/Evaluation')


def wait_app(drv):
    WebDriverWait(drv, 60).until(
        EC.presence_of_element_located((By.XPATH, "//button[contains(., '分组视图')]"))
    )


def open_group_view(drv):
    btn = drv.find_element(By.XPATH, "//button[contains(., '分组视图')]")
    js_click(drv, btn)
    time.sleep(1.5)


def click_edit_category(drv, name):
    xp = f"//button[@aria-label='编辑分类 {name}']"
    el = WebDriverWait(drv, 30).until(EC.element_to_be_clickable((By.XPATH, xp)))
    drv.execute_script('arguments[0].scrollIntoView({block: "center"})', el)
    time.sleep(0.3)
    js_click(drv, el)
    WebDriverWait(drv, 15).until(EC.visibility_of_element_located((By.ID, 'category-name')))
    time.sleep(1.0)  # base-ui 弹窗开合动画


def set_input(drv, el_id, value):
    el = drv.find_element(By.ID, el_id)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(value)


def submit(drv):
    btn = drv.find_element(By.XPATH, "//form[@id='category-form']/following-sibling::*//button[@type='submit']")
    js_click(drv, btn)


def dialog_open(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    return any(e.is_displayed() for e in els)


def create_category(drv, name, description):
    st, payload = api(
        drv, '/api/v1/evaluation/categories', 'POST',
        json.dumps({'name': name, 'description': description, 'icon': 'fas fa-folder'}, ensure_ascii=False),
    )
    return st, (payload.get('data') or {}).get('id') if isinstance(payload, dict) else None


def create_dimension(drv, name, category_id, description):
    st, payload = api(
        drv, '/api/v1/evaluation/dimensions', 'POST',
        json.dumps({
            'name': name, 'description': description, 'category_id': category_id,
            'dimension_type': 'main', 'type': 'manual', 'weight': 5,
        }, ensure_ascii=False),
    )
    return st, (payload.get('data') or {}).get('id') if isinstance(payload, dict) else None


def cleanup(drv, dim_ids):
    """只清本 run 自建数据：先删维度（分类下挂维度会被删除保护），再删分类。"""
    for dim_id in [d for d in dim_ids if d]:
        try:
            st, _ = api(drv, f'/api/v1/evaluation/dimensions/{dim_id}', 'DELETE')
            log(f'cleanup dimension {dim_id} -> {st}')
        except Exception as exc:
            log(f'cleanup dimension {dim_id} failed: {exc}')
    try:
        _status, items = categories(drv)
    except Exception:
        return
    for it in items:
        if it['name'].startswith(PREFIX):
            st, _ = api(drv, f"/api/v1/evaluation/categories/{it['id']}", 'DELETE')
            log(f"cleanup category {it['id']} {it['name']} -> {st}")


def main():
    drv = make_driver()
    report = {'ok': True, 'checks': []}
    dim_a = dim_b = None

    def check(name, cond, detail=''):
        report['checks'].append({'name': name, 'ok': bool(cond), 'detail': detail})
        log(('PASS ' if cond else 'FAIL ') + name + (' | ' + str(detail) if detail else ''))
        if not cond:
            report['ok'] = False

    try:
        drv.get(BASE + '/Evaluation')
        wait_app(drv)
        log('page ready: ' + drv.current_url)

        # 前置：自建测试分类 + 每类挂 1 个维度（分组视图只渲染有维度的分类）
        stamp = time.strftime('%H%M%S')
        cat_a_name = f'{PREFIX}A_{stamp}'
        cat_b_name = f'{PREFIX}B_{stamp}'
        renamed = cat_a_name + '_renamed'
        st, cat_a = create_category(drv, cat_a_name, 'INT-1549 验证明细：编辑走 PUT')
        st2, cat_b = create_category(drv, cat_b_name, 'INT-1549 验证明细：重名冲突目标')
        st3, dim_a = create_dimension(drv, f'{PREFIX}dim_A_{stamp}', cat_a, '编辑分类验证用维度')
        st4, dim_b = create_dimension(drv, f'{PREFIX}dim_B_{stamp}', cat_b, '重名冲突验证用维度')
        check('前置数据创建成功（分类 + 维度）', all([cat_a, cat_b, dim_a, dim_b]) and st == 201,
              {'cat_a': [st, cat_a], 'cat_b': [st2, cat_b], 'dim_a': [st3, dim_a], 'dim_b': [st4, dim_b]})
        drv.refresh()
        wait_app(drv)

        # ---------- 1. 编辑分类 A：改名保存必须走 PUT ----------
        open_group_view(drv)
        click_edit_category(drv, cat_a_name)
        check('编辑弹窗标题为「编辑分类」',
              '编辑分类' in drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-title']").text)
        set_input(drv, 'category-name', renamed)
        set_input(drv, 'category-description', 'INT-1549 验证明细：编辑后保存')
        drain_perf(drv)
        drv.execute_script('window.__net = []')
        submit(drv)
        time.sleep(3)

        perf = net_from_perf(drain_perf(drv))
        edit_reqs = [p for p in perf if '/evaluation/categories' in (p[1] or '') and p[0] in ('POST', 'PUT')]
        js = [r for r in js_net(drv) if '/evaluation/categories' in r.get('url', '') and r.get('method') in ('POST', 'PUT')]
        log('network perf: ' + json.dumps(edit_reqs, ensure_ascii=False))
        log('network fetch-patch: ' + json.dumps(js, ensure_ascii=False))
        put_hit = any(m == 'PUT' and u.rstrip('/').endswith(f'/evaluation/categories/{cat_a}') and s < 400
                      for m, u, s in edit_reqs) or any(
            r.get('method') == 'PUT' and r.get('url', '').rstrip('/').endswith(f'/evaluation/categories/{cat_a}')
            for r in js)
        post_hit = any(m == 'POST' for m, _u, _s in edit_reqs) or any(r.get('method') == 'POST' for r in js)
        check('编辑分类走 PUT /evaluation/categories/{id}', put_hit, edit_reqs)
        check('编辑分类未再发 POST 新建', not post_hit, edit_reqs)
        check('保存成功后弹窗关闭', not dialog_open(drv))

        status, items = categories(drv)
        names = [it['name'] for it in items]
        check('回读存在改名后的分类', renamed in names, names)
        check('回读原分类名已消失（无重复分类）', cat_a_name not in names, names)

        # 浅色截图（分组视图 + 改名后的分组）
        time.sleep(1.0)
        drv.save_screenshot(os.path.join(ART, 'light-after-rename.png'))

        # ---------- 2. 重名保存：必须报错且弹窗不关 ----------
        click_edit_category(drv, cat_b_name)
        set_input(drv, 'category-name', renamed)
        drv.execute_script('window.__net = []')
        drain_perf(drv)
        submit(drv)
        time.sleep(3)
        perf2 = net_from_perf(drain_perf(drv))
        js2 = js_net(drv)
        log('network duplicate perf: ' + json.dumps(perf2, ensure_ascii=False))
        log('network duplicate fetch-patch: ' + json.dumps(js2, ensure_ascii=False))
        bad = [p for p in perf2 if '/evaluation/categories' in (p[1] or '') and p[2] >= 400]
        bad_js = [r for r in js2 if '/evaluation/categories' in r.get('url', '') and r.get('status', 0) >= 400]
        check('重名保存后端返回 4xx', bool(bad or bad_js), bad or bad_js)
        check('重名保存后弹窗未关闭（无静默）', dialog_open(drv))
        alert_text = ''
        # 页面正文里也有 role=alert 的「自动合并提示」，只取弹窗内的行内错误
        dialogs = [d for d in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']") if d.is_displayed()]
        if dialogs:
            alerts = dialogs[0].find_elements(By.CSS_SELECTOR, "[role='alert']")
            if alerts:
                alert_text = alerts[0].text
        toast_text = ' '.join(e.text for e in drv.find_elements(By.XPATH, "//*[@data-sonner-toast]"))
        log('inline alert: ' + alert_text)
        log('toast: ' + toast_text)
        check('弹窗内出现行内错误提示', '已存在' in alert_text or '失败' in alert_text, alert_text)
        check('出现错误 toast', '已存在' in toast_text or '失败' in toast_text, toast_text)
        check('失败后名称输入保留用户输入', drv.find_element(By.ID, 'category-name').get_attribute('value') == renamed)
        drv.save_screenshot(os.path.join(ART, 'light-duplicate-error.png'))

        # ---------- 3. 深色截图（重名错误态 + 正常编辑态） ----------
        set_theme(drv, 'dark')
        wait_app(drv)
        open_group_view(drv)
        click_edit_category(drv, renamed)
        time.sleep(1.0)
        drv.save_screenshot(os.path.join(ART, 'dark-edit-dialog.png'))
        # 取消关闭
        cancel = drv.find_element(By.XPATH, "//button[normalize-space(.)='取消']")
        js_click(drv, cancel)
        time.sleep(1.0)
        check('取消后弹窗关闭', not dialog_open(drv))

        # ---------- 4. 清理本 run 数据（只删「接线测试_INT1549_」前缀） ----------
        cleanup(drv, [dim_a, dim_b])
        status, items = categories(drv)
        log('categories remaining: ' + json.dumps([it['name'] for it in items], ensure_ascii=False))
        check('清理后无本 run 测试分类残留', not any(it['name'].startswith(PREFIX) for it in items))

        with open(os.path.join(ART, 'report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log('REPORT: ' + json.dumps(report, ensure_ascii=False))
    finally:
        try:
            cleanup(drv, [dim_a, dim_b])
        except Exception as exc:  # 兜底清理，不掩盖主结论
            log('cleanup fallback failed: ' + str(exc))
        try:
            drv.quit()
        except Exception:
            pass

    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
