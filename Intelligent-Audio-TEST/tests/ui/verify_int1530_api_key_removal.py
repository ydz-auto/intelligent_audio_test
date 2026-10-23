# -*- coding: utf-8 -*-
"""INT-1530 验收实测（docker React 15173 + 后端 15000，真实数据无 mock）。

验证卡面验收标准：
1. 「开始测试」API 编辑弹窗无 API 级「API 密钥」单值输入；端点行内「密钥池」保留。
2. 端点密钥池不回归：整段粘贴 3 行 → POST /apis endpoints[].api_keys trim 后 3 项；
   回显摘要（尾号）+ textarea 空 + DOM/响应零明文；留空保存 → PUT body 不含 api_keys，池保留。
3. 设备管理「测试API」抽屉无回归（无 API 级密钥、端点密钥池可写）。
5. grep 由 shell 另行核对。
"""
import json, os, subprocess, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64',
                      '155.0.8059.39', 'chromedriver.exe')
ART = 'tests/ui/artifacts/int1530'
SUFFIX = int(time.time())
PG = 'intelligent-audio-test-postgres-1'

KEYS3 = ['sk-int1530-AAA1', 'sk-int1530-BBB2', 'sk-int1530-CCC3']
Paste3 = 'sk-int1530-AAA1\n   sk-int1530-BBB2   \n\nsk-int1530-CCC3'

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  const res = await __origFetch.apply(this, arguments);
  try {
    const entry = { url: url, method: method, status: res.status };
    if (init && init.body && typeof init.body === 'string') entry.reqBody = init.body;
    if (url.indexOf('/apis') !== -1) {
      const ct = res.headers.get('content-type') || '';
      if (ct.indexOf('json') !== -1) { entry.resBody = await res.clone().text(); }
    }
    window.__fetchLog.push(entry);
  } catch (e) {}
  return res;
};
"""

SUMMARY_XPATH = ("//*[@role='dialog']//*[contains(normalize-space(.), '已配置') "
                 "and contains(normalize-space(.), '个密钥') and not(*)]")
KEY_TEXTAREA_XPATH = "//textarea[contains(@placeholder, '每行一个密钥')]"


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    drv = webdriver.Chrome(options=options, service=Service(executable_path=DRIVER))
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def ensure_algorithm(drv, timeout=20):
    """关联算法 * 必填：等全局算法回填，仍未填则手动选第一个选项。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        trig = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] [data-slot='select-trigger']")
        if trig:
            if trig[0].get_attribute('data-placeholder') is None:
                return 'prefilled'
            js_click(drv, trig[0])
            time.sleep(0.8)
            opts = drv.find_elements(By.XPATH, "//*[@role='option']")
            if opts:
                js_click(drv, opts[0])
                time.sleep(0.6)
                return 'selected'
            try:
                js_click(drv, trig[0])
            except Exception:
                pass
        time.sleep(0.8)
    return 'failed'


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def wait_text(drv, xpath, timeout=25):
    return WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))


def wait_toast(drv, text, timeout=30):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: any(text in (e.text or '') for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        return True
    except Exception:
        return False


def set_theme_and_goto(drv, theme, path):
    if not (drv.current_url or '').startswith(BASE):
        # about:blank / data: URL 下 localStorage 不可用，先落到同源页面
        drv.get(BASE + '/')
        WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1.5)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
    drv.execute_script(
        "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")
    drv.get('about:blank')
    time.sleep(0.4)
    drv.get(BASE + path)
    WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(3.5)


def psql(sql):
    out = subprocess.run(['docker', 'exec', PG, 'psql', '-U', 'intelligent_audio_test',
                          '-d', 'intelligent_audio_test', '-A', '-t', '-c', sql],
                         capture_output=True, text=True, encoding='utf-8', errors='replace')
    return (out.stdout or '').strip(), (out.stderr or '').strip()


def api_id_by_name(name):
    out, err = psql("SELECT id FROM apis WHERE name = '%s' ORDER BY id DESC LIMIT 1;" % name.replace("'", "''"))
    if not out:
        raise RuntimeError('api not found by name: %s / %s' % (name, err))
    return int(out.splitlines()[0].strip())


def read_fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []


def show_apis(log, label):
    for item in log:
        if '/apis' not in item['url'] or item['method'] not in ('POST', 'PUT'):
            continue
        out = {'method': item['method'], 'url': item['url'], 'status': item['status']}
        if item.get('reqBody'):
            try:
                req = json.loads(item['reqBody'])
                out['req_name'] = req.get('name')
                out['endpoints'] = [{'endpoint': ep.get('endpoint'),
                                     'api_keys': ep.get('api_keys', '<absent>')}
                                    for ep in (req.get('endpoints') or [])]
            except Exception as e:
                out['req_parse_error'] = str(e)[:80]
        if item.get('resBody'):
            out['res_has_full_key'] = 'sk-int1530-' in item['resBody']
        print(label, json.dumps(out, ensure_ascii=False)[:900])
    return log


def dialog_probe(drv, label):
    dlg = drv.find_element(By.XPATH, "//*[@role='dialog']")
    probe = {
        'dialog_text_has_API密钥': 'API 密钥' in (dlg.text or ''),
        'id_api_key_count': len(dlg.find_elements(By.ID, 'api-key')),
        'password_inputs': len(dlg.find_elements(By.CSS_SELECTOR, 'input[type=password]')),
        'show_key_buttons': len(dlg.find_elements(By.XPATH,
            ".//button[@aria-label='显示密钥' or @aria-label='隐藏密钥']")),
        'keypool_textareas': len(dlg.find_elements(By.XPATH, KEY_TEXTAREA_XPATH)),
        'has_密钥池_label': '密钥池' in (dlg.text or ''),
        'has_名称_field': bool(dlg.find_elements(By.ID, 'api-name')) or 'API 名称' in (dlg.text or ''),
    }
    print(label, json.dumps(probe, ensure_ascii=False))
    return probe


def open_starttest_edit(drv, api_name):
    """开始测试页：JS 精确定位含 api_name 的卡片（取最深叶子文本），点卡内唯一「更多操作」。"""
    js = r"""
      const name = arguments[0];
      const els = Array.from(document.querySelectorAll('div,span,p,h3,h4,a'));
      let target = null;
      for (const e of els) {
        if (e.children.length === 0 && (e.textContent || '').trim() === name) { target = e; break; }
      }
      if (!target) return 'no-name';
      let node = target;
      for (let i = 0; i < 10 && node; i++) {
        const btn = node.querySelector && node.querySelector("button[aria-label='更多操作']");
        if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); return 'clicked'; }
        node = node.parentElement;
      }
      return 'no-menu';
    """
    res = 'no-name'
    deadline = time.time() + 20
    while time.time() < deadline:
        res = drv.execute_script(js, api_name)
        if res == 'clicked':
            break
        time.sleep(1)
    print('[open-edit]', api_name, res)
    if res != 'clicked':
        return False
    time.sleep(0.9)
    item = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]")))
    js_click(drv, item)
    time.sleep(1.5)
    return True


def add_endpoint_with_keys(drv, url, keys_text):
    add = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='dialog']//button[contains(normalize-space(.), '添加端点')]")))
    js_click(drv, add)
    ep = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, "//*[@role='dialog']//input[@aria-label='端点 URL']")))
    ep.send_keys(url)
    ta = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, "//*[@role='dialog']" + KEY_TEXTAREA_XPATH.replace('//textarea', '//textarea'))))
    ta.send_keys(keys_text)
    time.sleep(0.4)
    return ta.get_attribute('value')


def click_save(drv):
    btn = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='保存']")))
    js_click(drv, btn)
    time.sleep(1.2)
    dlg = drv.find_elements(By.XPATH, "//*[@role='dialog']")
    if dlg:
        print('[save] dialog still open; text:', json.dumps((dlg[-1].text or '')[:500], ensure_ascii=False))


def close_dialog(drv):
    try:
        btn = drv.find_element(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='取消']")
        js_click(drv, btn)
        time.sleep(0.6)
    except Exception:
        pass


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    results = {}
    try:
        # ===== 1) 开始测试「新增 API」弹窗：无 API 级密钥 =====
        set_theme_and_goto(drv, 'light', '/start-test?step=1')
        WebDriverWait(drv, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]")))
        drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '新增 API')]").click()
        WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'api-name')))
        results['ensure_alg_new'] = ensure_algorithm(drv)
        time.sleep(0.5)
        results['new_dialog_probe'] = dialog_probe(drv, '[new-dialog]')
        drv.save_screenshot(f'{ART}/A_new_api_dialog_light.png')

        # ===== 2) 新增：粘贴 3 行密钥 → 保存 → POST body =====
        name1 = f'INT1530_验收弹窗_{SUFFIX}'
        drv.find_element(By.ID, 'api-name').send_keys(name1)
        ta_val = add_endpoint_with_keys(drv, 'https://ep.example.com/v1/asr', Paste3)
        print('[new-dialog] textarea 原始值:', json.dumps(ta_val, ensure_ascii=False))
        results['new_dialog_after_endpoint_probe'] = dialog_probe(drv, '[new-dialog+endpoint]')
        results['new_dialog_keypool_placeholder'] = drv.find_element(
            By.XPATH, "//*[@role='dialog']" + KEY_TEXTAREA_XPATH).get_attribute('placeholder')
        drv.save_screenshot(f'{ART}/B_new_api_dialog_3keys_light.png')
        before = len(read_fetch_log(drv))
        click_save(drv)
        ok = wait_toast(drv, 'API 已保存')
        time.sleep(2.5)
        log = read_fetch_log(drv)[before:]
        show_apis(log, '[POST create]')
        post = [i for i in log if i['method'] == 'POST' and '/apis' in i['url']]
        sent_keys = None
        if post and post[-1].get('reqBody'):
            body = json.loads(post[-1]['reqBody'])
            sent_keys = [ep.get('api_keys') for ep in (body.get('endpoints') or [])]
        results['post_status'] = post[-1]['status'] if post else None
        results['post_api_keys'] = sent_keys
        results['toast_create'] = ok
        api_id = api_id_by_name(name1)
        results['created_api_id'] = api_id
        print('[new-dialog] api_id =', api_id)

        # ===== 3) DB 夹具：写入 3 条密钥（网关镜像缺 api_keys 入参，写侧读不到；读侧摘要可验） =====
        eps = [{
            'endpoint': 'https://ep.example.com/v1/asr', 'name': '', 'max_process': 1, 'max_timeout': 30,
            'max_audio_duration': 60, 'status': 'online', 'health_score': 100, 'priority': 1,
            'description': '', 'api_keys': KEYS3,
        }]
        sql = ("UPDATE apis SET api_endpoints = '%s'::json, updated_at = now() WHERE id = %d;"
               % (json.dumps(eps, ensure_ascii=False).replace("'", "''"), api_id))
        out, err = psql(sql)
        print('[db-fixture] update:', out, err)
        db_keys, _ = psql("SELECT api_endpoints::text FROM apis WHERE id = %d;" % api_id)
        results['db_keys_backfilled'] = db_keys
        print('[db-fixture] api_endpoints =', db_keys[:300])

        # ===== 4) 编辑回显：摘要 + textarea 空 + 零明文（浅色） =====
        set_theme_and_goto(drv, 'light', '/start-test?step=1')
        opened = open_starttest_edit(drv, name1)
        results['edit_opened'] = opened
        if opened:
            dlg = drv.find_element(By.XPATH, "//*[@role='dialog']")
            dlg_text = dlg.text or ''
            summaries = [e.text for e in drv.find_elements(By.XPATH, SUMMARY_XPATH)]
            ta_values = [t.get_attribute('value') for t in drv.find_elements(By.XPATH, KEY_TEXTAREA_XPATH)]
            html = drv.execute_script("return document.querySelector('[role=dialog]').innerHTML;")
            leaked = [k for k in KEYS3 if k in dlg_text or k in html]
            results['edit_summary'] = summaries
            results['edit_textarea_values'] = ta_values
            results['edit_leaked_full_keys'] = leaked
            results['edit_has_API密钥'] = 'API 密钥' in dlg_text
            results['edit_probe'] = dialog_probe(drv, '[edit-dialog]')
            print('[edit] dialog text snippet:', json.dumps(dlg_text[:400], ensure_ascii=False))
            drv.save_screenshot(f'{ART}/C_edit_dialog_summary_light.png')
            close_dialog(drv)

        # ===== 6) 深色截图：编辑弹窗（含摘要）+ 新增弹窗（无 API 级密钥） =====
        set_theme_and_goto(drv, 'dark', '/start-test?step=1')
        try:
            if open_starttest_edit(drv, name1):
                time.sleep(0.8)
                results['edit_dark_probe'] = dialog_probe(drv, '[edit-dialog-dark]')
                results['edit_dark_summary'] = [e.text for e in drv.find_elements(By.XPATH, SUMMARY_XPATH)]
                drv.save_screenshot(f'{ART}/D_edit_dialog_summary_dark.png')
                close_dialog(drv)
            WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]"))).click()
            WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))
            time.sleep(0.8)
            results['new_dialog_dark_probe'] = dialog_probe(drv, '[new-dialog-dark]')
            drv.save_screenshot(f'{ART}/G_new_api_dialog_dark.png')
            close_dialog(drv)
        except Exception as e:
            print('[dark-edit]', str(e)[:300])

        # ===== 5) 留空保存不清池：改名 → 保存 → PUT 无 api_keys + DB 池仍在 =====
        set_theme_and_goto(drv, 'light', '/start-test?step=1')
        if open_starttest_edit(drv, name1):
            results['ensure_alg_edit'] = ensure_algorithm(drv)
            name_el = drv.find_element(By.ID, 'api-name')
            name_el.click()
            name_el.send_keys(Keys.CONTROL, 'a')
            name_el.send_keys(Keys.DELETE)
            name1b = name1 + '_改名'
            name_el.send_keys(name1b)
            before = len(read_fetch_log(drv))
            click_save(drv)
            ok2 = wait_toast(drv, 'API 已保存')
            time.sleep(2.5)
            log2 = read_fetch_log(drv)[before:]
            show_apis(log2, '[PUT keep-pool]')
            put = [i for i in log2 if i['method'] == 'PUT' and '/apis' in i['url']]
            put_keys = None
            if put and put[-1].get('reqBody'):
                body = json.loads(put[-1]['reqBody'])
                put_keys = [('api_keys' in ep, ep.get('api_keys')) for ep in (body.get('endpoints') or [])]
            results['put_status'] = put[-1]['status'] if put else None
            results['put_endpoint_api_keys'] = put_keys
            results['toast_put'] = ok2
            after_keys, _ = psql("SELECT api_endpoints::text FROM apis WHERE id = %d;" % api_id)
            results['db_keys_after_blank_save'] = after_keys
            results['renamed_in_list'] = name1b in (drv.execute_script('return document.body.textContent') or '')

        # ===== 7) 设备管理「测试API」抽屉：无 API 级密钥 + 端点密钥池可写 =====
        set_theme_and_goto(drv, 'light', '/devices/api')
        WebDriverWait(drv, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加测试API')]")))
        drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加测试API')]").click()
        WebDriverWait(drv, 15).until(
            EC.presence_of_element_located((By.XPATH, "//input[@placeholder='如：音箱-客厅位']")))
        results['ensure_alg_drawer'] = ensure_algorithm(drv)
        time.sleep(0.8)
        results['drawer_probe'] = dialog_probe(drv, '[drawer-new]')
        name2 = f'INT1530_验收抽屉_{SUFFIX}'
        drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']").send_keys(name2)
        ta2 = add_endpoint_with_keys(drv, 'https://ep.example.com/v1/asr', 'sk-int1530-DDD4\nsk-int1530-EEE5')
        print('[drawer] textarea 原始值:', json.dumps(ta2, ensure_ascii=False))
        drv.save_screenshot(f'{ART}/E_device_drawer_new_light.png')
        before = len(read_fetch_log(drv))
        click_save(drv)
        ok3 = wait_toast(drv, '测试 API 已保存')
        time.sleep(2.5)
        log3 = read_fetch_log(drv)[before:]
        show_apis(log3, '[drawer POST]')
        post3 = [i for i in log3 if i['method'] == 'POST' and '/apis' in i['url']]
        dkeys = None
        if post3 and post3[-1].get('reqBody'):
            body = json.loads(post3[-1]['reqBody'])
            dkeys = [ep.get('api_keys') for ep in (body.get('endpoints') or [])]
        results['drawer_post_status'] = post3[-1]['status'] if post3 else None
        results['drawer_post_api_keys'] = dkeys
        results['toast_drawer'] = ok3
        drawer_id = api_id_by_name(name2)
        results['drawer_api_id'] = drawer_id
        results['drawer_algorithm_type_db'], _ = psql(
            "SELECT COALESCE(algorithm_type,'<null>') FROM apis WHERE id = %d;" % drawer_id)
        body_txt = drv.execute_script('return document.body.textContent') or ''
        results['drawer_list_has_new'] = name2 in body_txt

        # 抽屉编辑回显：改名前先看预填
        try:
            btn = WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='操作 {name2}']")))
            js_click(drv, btn)
            time.sleep(0.8)
            js_click(drv, WebDriverWait(drv, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]"))))
            time.sleep(1.5)
            results['drawer_edit_probe'] = dialog_probe(drv, '[drawer-edit]')
            prefills = {
                'name': drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']").get_attribute('value'),
                'endpoint': [e.get_attribute('value') for e in drv.find_elements(By.XPATH, "//*[@role='dialog']//input[@aria-label='端点 URL']")],
                'algorithm_filled': not drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] [data-slot='select-trigger'][data-placeholder]"),
            }
            results['drawer_edit_prefill'] = prefills
            print('[drawer-edit] prefill:', json.dumps(prefills, ensure_ascii=False))
            drv.save_screenshot(f'{ART}/F_device_drawer_edit_light.png')
            close_dialog(drv)
        except Exception as e:
            print('[drawer-edit]', str(e)[:200])

        # ===== 8) 清理：硬删本卡测试 API =====
        out, err = psql("DELETE FROM apis WHERE id IN (%d, %d);" % (api_id, drawer_id))
        print('[cleanup] delete:', out, err)
        residue, _ = psql("SELECT id, name FROM apis WHERE id IN (%d, %d);" % (api_id, drawer_id))
        results['residue'] = residue

        with open(f'{ART}/results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print('RESULTS:', json.dumps(results, ensure_ascii=False)[:2000])
        print('DONE')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
