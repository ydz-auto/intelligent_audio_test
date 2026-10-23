# -*- coding: utf-8 -*-
"""INT-1552 A/B 对照：旧镜像（15173）复现缺陷 vs 本卡交付镜像（15552）修复。

同一脚本、同一后端（docker 网关 15000），只换前端镜像：
1. 打开维度抽屉 → 所属分类「+ 新建分类」→ 输入名称 → 创建；
2. 抓 POST /evaluation/categories（旧镜像应为 0 次请求 = mock toast）；
3. 填维度名 → 保存，抓 POST /evaluation/dimensions 请求体 category_id
   （旧镜像应为负数临时 id，新镜像为真实分类 id）；
4. 清理本次创建的分类 / 维度。

运行：PYTHONIOENCODING=utf-8 python tests/ui/verify_int1552_ab.py <base_url> <label>
"""
import json
import os
import sys
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

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:15173'
LABEL = sys.argv[2] if len(sys.argv) > 2 else 'old'
API = 'http://127.0.0.1:15000/api/v1'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1552')
os.makedirs(ART, exist_ok=True)

STAMP = time.strftime('%H%M%S')
CAT_NAME = '接线测试_INT1552AB_%s_%s' % (LABEL, STAMP)
DIM_NAME = '接线测试_INT1552AB_dim_%s_%s' % (LABEL, STAMP)

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
      try { entry.resBody = (await res.clone().text()).slice(0, 2000); } catch (e) {}
    }
    window.__fetchLog.push(entry);
    return res;
  } catch (e) { entry.error = String(e); window.__fetchLog.push(entry); throw e; }
};
"""


def driver_new():
    o = Options()
    o.binary_location = CHROME_BINARY
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run', '--disable-extensions'):
        o.add_argument(a)
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
                    pass
        if cands:
            drv_path = sorted(cands, key=lambda c: c[0])[-1][1]
    d = webdriver.Chrome(service=Service(drv_path) if drv_path else Service(), options=o)
    d.set_page_load_timeout(120)
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def body_text(d):
    return d.execute_script('return document.body.textContent || ""')


def api_delete(path):
    req = urllib.request.Request(API + path, method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return 'HTTP %s' % e.code


def api_get(path):
    with urllib.request.urlopen(API + path, timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))


def main():
    res = {'label': LABEL, 'base': BASE}
    d = driver_new()
    try:
        d.get('about:blank')
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
        d.get(BASE + '/login')
        end = time.time() + 30
        while time.time() < end:
            if '进入工作台' in body_text(d):
                js_click(d, d.find_element(By.XPATH, "//button[contains(., '进入工作台')]"))
                WebDriverWait(d, 20).until(lambda x: 'dashboard' in x.current_url)
                break
            if 'dashboard' in d.current_url:
                break
            time.sleep(0.5)
        d.get(BASE + '/Evaluation')
        WebDriverWait(d, 40).until(lambda x: '评估维度' in body_text(x))
        time.sleep(1.5)

        js_click(d, WebDriverWait(d, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., '新增维度')]"))))
        sheet = WebDriverWait(d, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']")))
        WebDriverWait(d, 20).until(lambda x: '新增评估维度' in body_text(x))
        time.sleep(0.8)

        trig = sheet.find_element(
            By.XPATH, ".//*[@data-slot='select-trigger'][contains(normalize-space(.),'未分类')]")
        js_click(d, trig)
        item = WebDriverWait(d, 15).until(EC.element_to_be_clickable(
            (By.XPATH, "//*[@data-slot='select-item'][contains(normalize-space(.),'新建分类')]")))
        js_click(d, item)
        inp = WebDriverWait(d, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='新分类名称']")))
        inp.send_keys(CAT_NAME)
        time.sleep(0.3)
        js_click(d, d.find_element(By.XPATH, "//button[normalize-space(.)='创建']"))
        time.sleep(3)

        cat_posts = [e for e in d.execute_script('return window.__fetchLog || []')
                     if e.get('method') == 'POST' and '/evaluation/categories' in (e.get('url') or '')]
        res['category_post_count'] = len(cat_posts)
        res['category_posts'] = [{k: e.get(k) for k in ('url', 'status', 'reqBody', 'resBody')} for e in cat_posts]
        try:
            res['select_trigger_text'] = sheet.find_element(
                By.XPATH, ".//*[@data-slot='select-trigger'][contains(normalize-space(.),'%s')]" % CAT_NAME).text
        except Exception:
            res['select_trigger_text'] = None
        res['body_has_toast'] = '分类添加成功' in body_text(d)
        d.save_screenshot(os.path.join(ART, 'ab_%s_category.png' % LABEL))
        try:
            d.execute_script("document.querySelectorAll('[data-sonner-toast]').forEach(t=>t.remove())")
        except Exception:
            pass

        d.find_element(By.ID, 'dim-name').send_keys(DIM_NAME)
        js_click(d, d.find_element(By.XPATH, "//button[@type='submit'][contains(., '保存')]"))
        end = time.time() + 90
        dim_entry = None
        while time.time() < end:
            for e in d.execute_script('return window.__fetchLog || []'):
                if e.get('method') == 'POST' and (e.get('url') or '').rstrip('/').endswith('/evaluation/dimensions'):
                    dim_entry = e
            if dim_entry:
                break
            time.sleep(0.5)
        res['dimension_post'] = {k: dim_entry.get(k) for k in ('url', 'status', 'reqBody')} if dim_entry else None
        if dim_entry and dim_entry.get('reqBody'):
            try:
                res['dimension_body_category_id'] = json.loads(dim_entry['reqBody']).get('category_id')
            except Exception:
                pass
        res['post_save_body'] = body_text(d)[:400]
        d.save_screenshot(os.path.join(ART, 'ab_%s_after_save.png' % LABEL))

        # 清理
        time.sleep(2)
        items = (api_get('/evaluation/dimensions?per_page=1000').get('data') or {}).get('items') or []
        for i in items:
            if i.get('name') == DIM_NAME:
                res['cleanup_dimension'] = api_delete('/evaluation/dimensions/%s' % i['id'])
        cats = (api_get('/evaluation/categories').get('data') or {}).get('items') or []
        for c in cats:
            if c.get('name') == CAT_NAME:
                res['cleanup_category'] = api_delete('/evaluation/categories/%s' % c['id'])
    finally:
        d.quit()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
