# -*- coding: utf-8 -*-
"""INT-1294 用例页「标签操作」下拉真实接线 复测（真实库栈 5700，dev 5396）。

登录 接线测试_admin。验证三项操作由演示 toast 改为真实 API 请求：
  编辑标签 -> TagEditDialog 提交 PUT /api/v1/tags/{id}
  删除标签 -> 级联确认 -> DELETE /api/v1/tags/{id}?cascade=true
  复制标签下用例 -> 确认 -> POST /api/v1/testcases/batch copy_by_tag

Network 证据：CDP 预注入 window.fetch 打点（Chrome 155 无 setRequestInterception）。
测试数据：自建「接线测试_INT1294_*」分类+标签，run 结束前自删。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5396')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1294_tags'
SUFFIX = int(time.time()) % 100000

FETCH_PATCH = r"""
window.__reqLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  try {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init && init.method) || (input && input.method) || 'GET';
    if (url.indexOf('/tags') !== -1 || url.indexOf('/testcases/batch') !== -1) {
      let body = null;
      if (init && init.body) {
        try { body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body; }
        catch (e) { body = init.body; }
      }
      window.__reqLog.push({ url: url, method: method, body: body });
    }
  } catch (e) {}
  return __origFetch.apply(this, arguments);
};
"""


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return drv


def req_log(drv):
    try:
        return drv.execute_script('return window.__reqLog || []')
    except Exception:
        return []


def wait_toast(drv, text, timeout=25):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: any(text in (e.text or '')
                          for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('TOAST:', json.dumps(toasts, ensure_ascii=False)[:300])
        return True
    except Exception:
        return False


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(
        lambda d: '/login' not in d.current_url
        or '欢迎' in (d.execute_script('return document.body.textContent || ""') or ''))
    time.sleep(2)
    print('login URL:', drv.current_url)
    return drv.current_url


def api_call(drv, method, path, payload=None):
    body_js = ('JSON.stringify(%s)' % json.dumps(payload)) if payload is not None else 'undefined'
    return drv.execute_script('''
      const token = localStorage.getItem('iatp:auth:token:v1');
      const body = %s;
      return fetch('%s', {
        method: '%s',
        headers: {'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : ''},
        body: body
      }).then(async r => {
        let d = null;
        try { d = await r.json(); } catch (e) {}
        return {status: r.status, data: d};
      });
    ''' % (body_js, path, method))


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    created = {'category_id': None, 'tag_id': None}
    try:
        login(drv)
        try:
            drv.execute_script(
                "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")
        except Exception:
            pass

        # ===== 建临时分类 + 临时标签 =====
        cat_name = f'接线测试_INT1294分类_{SUFFIX}'
        cat = api_call(drv, 'POST', '/api/v1/tags/categories',
                       {'name': cat_name, 'description': 'INT-1294 复测临时分类', 'color': '#10b981'})
        print('CREATE CATEGORY:', json.dumps(cat, ensure_ascii=False)[:300])
        # 统一信封：data.code=0 业务成功，data.data 为对象体
        cat_id = (cat.get('data') or {}).get('data', {}).get('id')
        created['category_id'] = cat_id
        print('CAT_ID:', cat_id)
        time.sleep(1)

        tag_name = f'接线测试_INT1294标签_{SUFFIX}'
        payload = {'name': tag_name, 'description': 'INT-1294 复测临时标签', 'color': '#f59e0b'}
        if cat_id:
            payload['category_id'] = cat_id
        tag = api_call(drv, 'POST', '/api/v1/tags', payload)
        print('CREATE TAG:', json.dumps(tag, ensure_ascii=False)[:300])
        tag_id = (tag.get('data') or {}).get('data', {}).get('id')
        created['tag_id'] = tag_id
        print('TAG_ID:', tag_id)
        time.sleep(1)

        # ===== 打开用例管理页 =====
        drv.get(BASE + '/testcases')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        print('testcases URL:', drv.current_url)

        # 等待工具栏
        WebDriverWait(drv, 20).until(
            lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '标签')]")) > 0)
        drv.save_screenshot(f'{ART}/00_testcases_page.png')

        # 标签 facet 打开，搜索临时标签并选中
        tag_facet = drv.find_element(By.XPATH,
            "//button[contains(., '标签')][.//span[contains(., '全部') or contains(., '标签')]]")
        tag_facet.click()
        time.sleep(0.6)
        search = WebDriverWait(drv, 8).until(
            EC.presence_of_element_located((By.XPATH, "//input[@aria-label='搜索标签']")))
        search.send_keys(tag_name)
        time.sleep(0.5)
        option = None
        for c in drv.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content']"):
            btns = c.find_elements(By.XPATH, ".//button[contains(., '%s')]" % tag_name)
            if btns:
                option = btns[0]
                break
        if option is None:
            print('TAG OPTION NOT FOUND in facet')
            raise AssertionError('临时标签未在 facet 选项中')
        option.click()
        time.sleep(1.0)
        drv.save_screenshot(f'{ART}/01_tag_selected.png')

        # 标签操作下拉
        WebDriverWait(drv, 8).until(
            lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '标签操作')]")) > 0)
        actions_trigger = drv.find_element(By.XPATH, "//button[contains(., '标签操作')]")
        actions_trigger.click()
        time.sleep(0.5)
        drv.save_screenshot(f'{ART}/02_tag_actions_light.png')

        def item(text):
            for c in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-content']"):
                items = c.find_elements(By.XPATH,
                                        ".//*[@data-slot='dropdown-menu-item'][contains(., '%s')]" % text)
                if items:
                    return items[0]
            raise AssertionError('下拉项「%s」缺失' % text)

        # ===== 编辑标签：真实 TagEditDialog -> PUT /tags/{id} =====
        item('编辑标签').click()
        time.sleep(0.6)
        WebDriverWait(drv, 8).until(
            lambda d: len(d.find_elements(By.XPATH,
                "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '编辑标签')]]")) > 0)
        drv.save_screenshot(f'{ART}/03_edit_dialog_light.png')
        desc = drv.find_element(By.ID, 'tag-desc')
        desc.clear()
        desc.send_keys(f'INT1294 复测改描述 {SUFFIX}')
        time.sleep(0.3)
        save_btn = drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']")
        drv.execute_script("arguments[0].click();", save_btn)
        ok = wait_toast(drv, '标签更新成功') or wait_toast(drv, '保存成功')
        print('EDIT toast ok:', ok)
        time.sleep(2)
        edit_reqs = [r for r in req_log(drv)
                     if r.get('method') == 'PUT' and '/tags/' in r.get('url', '')]
        print('EDIT PUT:', json.dumps(edit_reqs, ensure_ascii=False)[:400])

        # ===== 复制标签下用例：确认 -> POST /testcases/batch copy_by_tag =====
        WebDriverWait(drv, 8).until(
            lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '标签操作')]")) > 0)
        actions_trigger = drv.find_element(By.XPATH, "//button[contains(., '标签操作')]")
        actions_trigger.click()
        time.sleep(0.5)
        item('复制标签下用例').click()
        WebDriverWait(drv, 8).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")) > 0)
        conf_el = drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")[0]
        ctext = conf_el.text
        print('COPY CONFIRM TEXT:', ctext[:200])
        assert '复制后将生成新标签' in ctext
        drv.save_screenshot(f'{ART}/04_copy_confirm_light.png')
        copy_btn = conf_el.find_element(By.XPATH, ".//button[contains(., '复制')]")
        drv.execute_script("arguments[0].click();", copy_btn)
        ok = wait_toast(drv, '已复制标签下用例') or wait_toast(drv, '复制成功')
        print('COPY toast ok:', ok)
        time.sleep(2)
        copy_reqs = [r for r in req_log(drv)
                     if r.get('method') == 'POST' and '/testcases/batch' in r.get('url', '')]
        print('COPY POST:', json.dumps(copy_reqs, ensure_ascii=False)[:400])

        # ===== 删除标签：级联确认 -> DELETE /tags/{id}?cascade=true =====
        WebDriverWait(drv, 8).until(
            lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '标签操作')]")) > 0)
        actions_trigger = drv.find_element(By.XPATH, "//button[contains(., '标签操作')]")
        actions_trigger.click()
        time.sleep(0.5)
        item('删除标签').click()
        WebDriverWait(drv, 8).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")) > 0)
        conf_el = drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")[0]
        ctext = conf_el.text
        print('DELETE CONFIRM TEXT:', ctext[:200])
        assert '级联删除' in ctext
        drv.save_screenshot(f'{ART}/05_delete_confirm_light.png')
        del_btn = conf_el.find_element(By.XPATH, ".//button[contains(., '删除')]")
        drv.execute_script("arguments[0].click();", del_btn)
        ok = wait_toast(drv, '标签已删除') or wait_toast(drv, '删除成功')
        print('DELETE toast ok:', ok)
        time.sleep(2)
        del_reqs = [r for r in req_log(drv)
                    if r.get('method') == 'DELETE' and '/tags/' in r.get('url', '')]
        print('DELETE REQ:', json.dumps(del_reqs, ensure_ascii=False)[:400])

        # 汇总
        print('SUMMARY reqs:', json.dumps(req_log(drv), ensure_ascii=False)[:800])
    finally:
        # ===== 清理 =====
        # 复制产生的 {tag_name}_copy 标签也一并删（copy_by_tag 后端会新建）
        try:
            copy_name = tag_name + '_copy'
            lst = api_call(drv, 'GET', '/api/v1/tags?page=1&per_page=100')
            items = ((lst.get('data') or {}).get('data') or {}).get('items') or []
            for t in items:
                if t.get('name') == copy_name:
                    r = api_call(drv, 'DELETE', '/api/v1/tags/%s?cascade=true' % t['id'])
                    print('CLEANUP copy tag:', json.dumps(r, ensure_ascii=False)[:200])
        except Exception:
            pass
        try:
            if created.get('tag_id'):
                r = api_call(drv, 'DELETE', '/api/v1/tags/%s?cascade=true' % created['tag_id'])
                print('CLEANUP tag:', json.dumps(r, ensure_ascii=False)[:200])
        except Exception:
            pass
        try:
            if created.get('category_id'):
                r = api_call(drv, 'DELETE', '/api/v1/tags/categories/%s' % created['category_id'])
                print('CLEANUP category:', json.dumps(r, ensure_ascii=False)[:200])
        except Exception:
            pass
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
