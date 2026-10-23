# -*- coding: utf-8 -*-
"""INT-1552 验收：维度抽屉「所属分类 → + 新建分类」真实落库（浏览器实测）。

环境：前端容器（本卡交付源码构建）→ docker 网关 http://localhost:15000（AUTH_MODE=off，主库 intelligent_audio_test）。

核对项（对应卡内验收标准）：
1. 内联新建分类发起 POST /api/v1/evaluation/categories，状态 201，返回真实 id；
2. 分类下拉回显新分类名（真实 id 回填 categoryId，不再是 String(-Date.now()) 负数）；
3. 保存维度的 POST /evaluation/dimensions 请求体 category_id == 新建分类返回的 id（正数）；
4. GET /evaluation/dimensions 回读 category_id 为该真实 id；GET /evaluation/categories 出现该分类；
5. 失败态：同名分类提交 → 后端「分类名称已存在」提示，内联输入保留不被清空；
6. 浅 / 深色截图 + Network 证据；
7. 写数据纪律：分类 / 维度名带「接线测试_INT1552_」前缀，结束前删除。

运行：PYTHONIOENCODING=utf-8 python tests/ui/verify_int1552_inline_category.py
"""
import json
import os
import time
import urllib.error
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_UI_BASE', 'http://localhost:15552')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1552')
os.makedirs(ART, exist_ok=True)

STAMP = time.strftime('%H%M%S')
CAT_NAME = '接线测试_INT1552_分类_%s' % STAMP
DIM_NAME = '接线测试_INT1552_维度_%s' % STAMP
DUP_NAME = '拒识'  # 真实库已存在分类，用于失败态
DESC = 'INT-1552 维度抽屉内联新建分类验收'

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url: url, method: method, ts: Date.now() };
  try {
    if (init && init.body) entry.reqBody = String(init.body).slice(0, 20000);
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    if (url.indexOf('/evaluation/categories') !== -1 || url.indexOf('/evaluation/dimensions') !== -1) {
      try { entry.resBody = (await res.clone().text()).slice(0, 4000); } catch (e) {}
    }
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""


def driver_new():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-extensions')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        if cands:
            drv_path = sorted(cands, key=lambda c: c[0])[-1][1]
    service = Service(drv_path) if drv_path else Service()
    d = webdriver.Chrome(service=service, options=options)
    d.set_page_load_timeout(120)
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def shot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    print('SHOT', path, flush=True)
    return path


def body_text(d):
    return d.execute_script('return document.body.textContent || ""')


def set_theme(d, mode):
    d.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);", mode)
    time.sleep(0.6)


def dismiss_toasts(d):
    """注意：直接 remove React 管理的 sonner 节点会让后续渲染 removeChild 抛错、整页空白，
    本脚本不再使用；toast 覆盖用 JS click 规避。"""
    return None


def fetch_log(d):
    return d.execute_script('return window.__fetchLog || []')


def api_get(path):
    with urllib.request.urlopen(API + path, timeout=90) as resp:
        return json.loads(resp.read().decode('utf-8'))


def api_delete(path):
    req = urllib.request.Request(API + path, method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return 'HTTP %s: %s' % (e.code, e.read().decode()[:200])


def enter_workbench(d):
    d.get(BASE + '/login')
    end = time.time() + 30
    while time.time() < end:
        try:
            if '进入工作台' in body_text(d):
                js_click(d, d.find_element(By.XPATH, "//button[contains(., '进入工作台')]"))
                WebDriverWait(d, 20).until(lambda x: 'dashboard' in x.current_url)
                return 'clicked'
            if 'dashboard' in d.current_url:
                return 'auto-redirect'
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError('登录页未就绪，url=%s' % d.current_url)


def open_drawer(d):
    btn = WebDriverWait(d, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., '新增维度')]"))
    )
    js_click(d, btn)
    sheet = WebDriverWait(d, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']"))
    )
    WebDriverWait(d, 20).until(lambda x: '新增评估维度' in body_text(x))
    time.sleep(0.8)
    return sheet


def open_new_category_input(d, sheet):
    trigger = sheet.find_element(
        By.XPATH, ".//*[@data-slot='select-trigger'][contains(normalize-space(.),'未分类')]")
    js_click(d, trigger)
    item = WebDriverWait(d, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@data-slot='select-item'][contains(normalize-space(.),'新建分类')]"))
    )
    js_click(d, item)
    inp = WebDriverWait(d, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='新分类名称']"))
    )
    return inp


def type_into(d, inp, text):
    js_click(d, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(text)
    time.sleep(0.3)
    return inp.get_attribute('value')


def click_create(d):
    btn = d.find_element(By.XPATH, "//button[normalize-space(.)='创建' or normalize-space(.)='创建中…']")
    js_click(d, btn)


def main():
    results = {}
    dim_id = None
    cat_id = None
    d = driver_new()
    try:
        d.get('about:blank')
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
        results['login'] = enter_workbench(d)

        d.get(BASE + '/Evaluation')
        WebDriverWait(d, 40).until(lambda x: '评估维度' in body_text(x))
        time.sleep(1.5)

        sheet = open_drawer(d)
        inp = open_new_category_input(d, sheet)

        # ---- 失败态：同名分类 ----
        val = type_into(d, inp, DUP_NAME)
        results['dup_input_value'] = val
        click_create(d)
        end = time.time() + 60
        dup_entry = None
        while time.time() < end:
            posts = [e for e in fetch_log(d)
                     if e.get('method') == 'POST' and '/evaluation/categories' in (e.get('url') or '')]
            if posts:
                dup_entry = posts[0]
                break
            time.sleep(0.5)
        results['dup_post'] = {k: dup_entry.get(k) for k in ('url', 'status', 'reqBody', 'resBody')} if dup_entry else None
        time.sleep(1.5)
        results['dup_toast_text'] = body_text(d)
        results['dup_input_retained'] = (
            d.find_element(By.CSS_SELECTOR, "input[aria-label='新分类名称']").get_attribute('value') == DUP_NAME)
        shot(d, 'light_01_dup_error.png')

        # ---- 成功：唯一名新建分类 ----
        inp = d.find_element(By.CSS_SELECTOR, "input[aria-label='新分类名称']")
        type_into(d, inp, CAT_NAME)
        click_create(d)
        end = time.time() + 60
        create_entry = None
        while time.time() < end:
            posts = [e for e in fetch_log(d)
                     if e.get('method') == 'POST' and '/evaluation/categories' in (e.get('url') or '')
                     and e.get('status') == 201 and e.get('resBody')]
            if posts:
                create_entry = posts[-1]
                break
            time.sleep(0.5)
        results['create_post'] = {k: create_entry.get(k) for k in ('url', 'status', 'reqBody', 'resBody')} if create_entry else None
        if create_entry and create_entry.get('resBody'):
            try:
                payload = json.loads(create_entry['resBody'])
                cat_id = (payload.get('data') or {}).get('id')
            except Exception:
                cat_id = None
        results['created_category_id'] = cat_id
        # 下拉回显新分类名 + 内联输入收起
        end = time.time() + 20
        trigger_text = ''
        while time.time() < end:
            try:
                trig = sheet.find_element(By.XPATH, ".//*[@data-slot='select-trigger'][contains(normalize-space(.),'%s')]" % CAT_NAME)
                trigger_text = trig.text
                break
            except Exception:
                time.sleep(0.5)
        results['select_shows_new_category'] = trigger_text
        results['inline_input_collapsed'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='新分类名称']")) == 0
        shot(d, 'light_02_category_created.png')

        # ---- 保存维度 ----
        d.find_element(By.ID, 'dim-name').send_keys(DIM_NAME)
        d.find_element(By.ID, 'dim-description').send_keys(DESC)
        save_btn = d.find_element(By.XPATH, "//button[@type='submit'][contains(., '保存')]")
        js_click(d, save_btn)
        # 等维度写请求出现
        end = time.time() + 90
        dim_entry = None
        while time.time() < end:
            for e in fetch_log(d):
                if e.get('method') == 'POST' and (e.get('url') or '').rstrip('/').endswith('/evaluation/dimensions'):
                    dim_entry = e
            if dim_entry:
                break
            time.sleep(0.5)
        results['dim_post'] = {k: dim_entry.get(k) for k in ('url', 'status', 'reqBody')} if dim_entry else None
        if dim_entry and dim_entry.get('reqBody'):
            try:
                results['dim_body_category_id'] = json.loads(dim_entry['reqBody']).get('category_id')
            except Exception:
                results['dim_body_category_id'] = None
        # 后端写库慢（已知 gateway 60s deadline），轮询 GET 直到落库
        end = time.time() + 240
        found = None
        while time.time() < end:
            try:
                data = api_get('/evaluation/dimensions?per_page=1000')
                items = (data.get('data') or {}).get('items') or []
                hits = [i for i in items if i.get('name') == DIM_NAME]
                if hits:
                    found = hits[0]
                    break
            except Exception as e:
                results['dim_poll_error'] = str(e)
            time.sleep(3)
        results['dim_readback'] = found
        if found:
            dim_id = found.get('id')
        # 分类 GET 回读
        cats = (api_get('/evaluation/categories').get('data') or {}).get('items') or []
        hit_cats = [c for c in cats if c.get('name') == CAT_NAME]
        results['category_readback'] = hit_cats
        results['toast_text_after_save'] = body_text(d)[:600]
        shot(d, 'light_03_after_save.png')

        # ---- 深色截图：再开一次抽屉复现内联输入态 ----
        set_theme(d, 'dark')
        time.sleep(1.0)
        try:
            close_btn = sheet.find_element(By.CSS_SELECTOR, "[data-slot='sheet-close']")
            js_click(d, close_btn)
        except Exception:
            pass
        time.sleep(1.5)
        sheet2 = open_drawer(d)
        open_new_category_input(d, sheet2)
        shot(d, 'dark_01_inline_input.png')
        try:
            js_click(d, sheet2.find_element(By.CSS_SELECTOR, "[data-slot='sheet-close']"))
        except Exception:
            pass
        set_theme(d, 'light')

        # ---- 断言汇总 ----
        dup = results.get('dup_post') or {}
        created = results.get('create_post') or {}
        results['check_dup_blocked'] = dup.get('status') == 400 and '已存在' in (
            (results.get('dup_toast_text') or '') + str(dup.get('resBody') or ''))
        results['check_dup_input_retained'] = bool(results.get('dup_input_retained'))
        results['check_create_201'] = created.get('status') == 201 and isinstance(cat_id, int) and cat_id > 0
        results['check_select_shows'] = CAT_NAME in (results.get('select_shows_new_category') or '')
        results['check_dim_body_real_id'] = results.get('dim_body_category_id') == cat_id and cat_id is not None
        results['check_dim_readback'] = bool(found) and found.get('category_id') == cat_id
        results['check_category_listed'] = len(hit_cats) == 1 and hit_cats[0].get('id') == cat_id
    finally:
        # 清理：维度 → 分类（按 id，另按名字兜底，确保库里不留本卡残留）
        try:
            if dim_id is not None:
                results['cleanup_dimension'] = api_delete('/evaluation/dimensions/%s' % dim_id)
            items = (api_get('/evaluation/dimensions?per_page=1000').get('data') or {}).get('items') or []
            for i in items:
                if i.get('name') in (DIM_NAME,):
                    results.setdefault('cleanup_dimension_by_name', []).append(api_delete('/evaluation/dimensions/%s' % i['id']))
        except Exception as e:
            results['cleanup_dimension_error'] = str(e)
        try:
            if cat_id is not None:
                results['cleanup_category'] = api_delete('/evaluation/categories/%s' % cat_id)
            cats_all = (api_get('/evaluation/categories').get('data') or {}).get('items') or []
            for c in cats_all:
                if c.get('name') == CAT_NAME:
                    results.setdefault('cleanup_category_by_name', []).append(api_delete('/evaluation/categories/%s' % c['id']))
        except Exception as e:
            results['cleanup_category_error'] = str(e)
        d.quit()

    with open(os.path.join(ART, 'results.json'), 'w', encoding='utf-8') as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str), flush=True)
    ok = all(results.get(k) for k in (
        'check_dup_blocked', 'check_dup_input_retained', 'check_create_201',
        'check_select_shows', 'check_dim_body_real_id', 'check_dim_readback',
        'check_category_listed'))
    print('RESULT:', 'PASS' if ok else 'FAIL', flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
