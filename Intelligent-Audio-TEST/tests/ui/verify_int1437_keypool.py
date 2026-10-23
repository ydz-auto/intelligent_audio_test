# -*- coding: utf-8 -*-
"""INT-1437 密钥池 React 前端浏览器冒烟（dev 5310；/apis 走临时契约 mock 5701，
其余走真实库栈 5700 登录）。

覆盖验收标准：
1. 开始测试页 API 编辑弹窗：endpoint 行内密钥池 textarea 整段粘贴多行密钥自动拆行；
   保存成功（toast「API 已保存」）+ POST /apis api_keys 数组 + 列表刷新。
2. 设备管理页「测试API」页签编辑抽屉：端点行内密钥池 textarea；保存成功 + api_keys。
3. 编辑回显：已配 2+ key 的 API 打开编辑，端点行只显示摘要（N 个密钥 / 尾号 4 位），
   界面与接口响应均不出现完整密钥。
4. 留空保存不清池：仅改名称、密钥区留空保存 → PUT 请求体不携带 api_keys，既有池保留。
6. 评估维度（评测配置 apiEndpoints）编辑不渲染密钥池块。
"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5310')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1437'
SUFFIX = int(time.time())

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const res = await __origFetch.apply(this, arguments);
  try {
    const entry = { url: url, method: init && init.method, status: res.status };
    if (init && (init.method === 'POST' || init.method === 'PUT')) entry.reqBody = init.body;
    if (url.indexOf('/apis') !== -1) {
      const ct = res.headers.get('content-type') || '';
      if (ct.indexOf('json') !== -1) {
        const txt = await res.clone().text();
        entry.resBody = txt;
      }
    }
    window.__fetchLog.push(entry);
  } catch (e) {}
  return res;
};
"""

KEY_TEXTAREA_XPATH = "//textarea[contains(@placeholder, '每行一个密钥')]"
# JSX 拆分文本节点：匹配摘要用 normalize-space(.) 而非 text()（Selenium XPath 坑）
SUMMARY_XPATH = "//*[contains(normalize-space(.), '已配置') and contains(normalize-space(.), '个密钥')]"


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
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    drv_path = exe if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major else drv_path
                except ValueError:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return drv


def read_fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []')
    except Exception:
        return None


def wait_toast(drv, text, timeout=25):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: any(text in (e.text or '') for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('TOAST:', json.dumps(toasts, ensure_ascii=False)[:300])
        return True
    except Exception:
        return False


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    try:
        uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        # auth dev + 健康时 /login 整页重载会重定向 /dashboard
        if '/login' not in drv.current_url:
            return drv.current_url
        raise
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(
        lambda d: '/login' not in d.current_url or '欢迎' in (d.execute_script('return document.body.textContent || ""') or ''))
    time.sleep(2)
    print('login URL:', drv.current_url)
    return drv.current_url


def wait_algorithm_filled(drv, timeout=30):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: not d.find_elements(
                By.CSS_SELECTOR, '[role="dialog"] [data-slot="select-trigger"][data-placeholder]'))
        time.sleep(0.5)
        return True
    except Exception:
        return False


def set_global_algorithm(drv):
    drv.execute_script(
        "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")


def add_endpoint_with_keys(drv, url, keys_text):
    """在打开的 API 编辑弹窗/抽屉中：添加端点 → 填 URL → 填密钥池 textarea。"""
    add = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加端点')]")))
    add.click()
    ep = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, "//input[@aria-label='端点 URL']")))
    ep.send_keys(url)
    ta = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.XPATH, KEY_TEXTAREA_XPATH)))
    ta.send_keys(keys_text)
    time.sleep(0.3)
    return ta.get_attribute('value')


def open_starttest_edit(drv, api_name):
    """开始测试页：定位含 api_name 的行/卡 → 更多操作 → 编辑。"""
    WebDriverWait(drv, 20).until(
        lambda d: any(api_name in (e.text or '') for e in d.find_elements(By.XPATH, "//*[self::tr or self::div]")))
    btn = WebDriverWait(drv, 15).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//*[contains(normalize-space(.), '{api_name}')]//button[@aria-label='更多操作'][1]")))
    btn.click()
    time.sleep(0.8)
    edit = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]")))
    edit.click()
    time.sleep(1.2)


def show_apis(drv, label):
    log = read_fetch_log(drv)
    if not log:
        print(label, 'no log')
        return
    for item in log:
        if '/apis' not in item['url']:
            continue
        out = {'method': item['method'], 'url': item['url'], 'status': item['status']}
        if item.get('reqBody'):
            try:
                req = json.loads(item['reqBody'])
                out['api_keys'] = [ep.get('api_keys') for ep in req.get('endpoints') or []]
            except Exception:
                pass
        if item.get('resBody'):
            try:
                res = json.loads(item['resBody'])
                if isinstance(res, dict) and 'data' in res:
                    # 读侧检查完整密钥不回显
                    out['res_has_full_key'] = 'sk-full-secret' in (item['resBody'] or '')
            except Exception:
                pass
        print(label, json.dumps(out, ensure_ascii=False)[:400])


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    try:
        login(drv)
        set_global_algorithm(drv)

        # ===== 3) 编辑回显（开始测试弹窗）：演示密钥池API（2 密钥） =====
        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        try:
            open_starttest_edit(drv, '演示密钥池API')
            title = drv.find_elements(By.XPATH, "//*[@role='dialog']//h2")
            print('[edit-echo-starttest] dialog title:', json.dumps([t.text for t in title], ensure_ascii=False))
            summaries = [e.text for e in drv.find_elements(By.XPATH, SUMMARY_XPATH)]
            textareas = drv.find_elements(By.XPATH, KEY_TEXTAREA_XPATH)
            ta_values = [t.get_attribute('value') for t in textareas]
            dlg_txt = drv.find_element(By.XPATH, "//*[@role='dialog']").text
            leaked = [k for k in ('sk-full-secret-1', 'sk-full-secret-2') if k in dlg_txt]
            print('[edit-echo-starttest] 摘要:', json.dumps(summaries, ensure_ascii=False))
            print('[edit-echo-starttest] textarea 值(应空):', json.dumps(ta_values, ensure_ascii=False))
            print('[edit-echo-starttest] 完整密钥泄漏:', json.dumps(leaked, ensure_ascii=False))
            time.sleep(0.5)
            drv.save_screenshot(f'{ART}/starttest_edit_echo_light.png')
            try:
                drv.find_element(By.XPATH, "//button[normalize-space(.)='取消']").click()
                time.sleep(0.5)
            except Exception:
                pass
        except Exception as e:
            print('[edit-echo-starttest] FAIL:', str(e)[:200])

        # ===== 1) 开始测试「新增 API」弹窗：粘贴多行密钥 → 保存 =====
        WebDriverWait(drv, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]"))).click()
        dlg_name = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))
        name1 = f'接线密钥池_弹窗_{SUFFIX}'
        dlg_name.send_keys(name1)
        wait_algorithm_filled(drv)
        ta_val = add_endpoint_with_keys(drv, 'https://ep.example.com/v1/asr',
                                        'sk-dialog-1\n  sk-dialog-2  \n\nsk-dialog-3')
        print('[dialog] key textarea 原始值:', json.dumps(ta_val, ensure_ascii=False))
        time.sleep(0.8)
        drv.save_screenshot(f'{ART}/starttest_dialog_keys_light.png')
        drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
        ok1 = wait_toast(drv, 'API 已保存')
        print('[dialog] 保存 toast:', ok1)
        time.sleep(2)
        show_apis(drv, '[dialog]')
        # 列表刷新
        body = drv.execute_script('return document.body.textContent')
        print('[dialog] 列表刷新含新API:', name1 in body)
        # 深色截图
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        drv.get('about:blank')
        time.sleep(0.5)
        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        WebDriverWait(drv, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]"))).click()
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))
        wait_algorithm_filled(drv)
        add_endpoint_with_keys(drv, 'https://ep.example.com/v1/asr', 'sk-dark-d1\nsk-dark-d2')
        time.sleep(0.6)
        drv.save_screenshot(f'{ART}/starttest_dialog_keys_dark.png')
        try:
            drv.find_element(By.XPATH, "//button[normalize-space(.)='取消']").click()
        except Exception:
            pass
        # 回浅色
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'light');")
        drv.get('about:blank')
        time.sleep(0.5)

        # ===== 2) 设备管理「测试API」抽屉：粘贴多密钥 → 保存 =====
        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        WebDriverWait(drv, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加测试API')]"))).click()
        name_in = WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@placeholder='如：音箱-客厅位']")))
        name2 = f'接线密钥池_抽屉_{SUFFIX}'
        name_in.send_keys(name2)
        ta_val2 = add_endpoint_with_keys(drv, 'https://ep.example.com/v1/asr', 'sk-drawer-1\r\nsk-drawer-2')
        print('[drawer] key textarea 原始值:', json.dumps(ta_val2, ensure_ascii=False))
        time.sleep(0.8)
        drv.save_screenshot(f'{ART}/device_drawer_keys_light.png')
        drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
        ok2 = wait_toast(drv, '测试 API 已保存')
        print('[drawer] 保存 toast:', ok2)
        time.sleep(2)
        show_apis(drv, '[drawer]')
        body2 = drv.execute_script('return document.body.textContent')
        print('[drawer] 列表刷新含新API:', name2 in body2)

        # ===== 3) 编辑回显（设备抽屉）：演示密钥池API =====
        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        try:
            row_btn = WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='操作 演示密钥池API']")))
            row_btn.click()
            time.sleep(0.8)
            edit_btn = WebDriverWait(drv, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]")))
            edit_btn.click()
            time.sleep(1.2)
            summaries = [e.text for e in drv.find_elements(By.XPATH, SUMMARY_XPATH)]
            textareas = drv.find_elements(By.XPATH, KEY_TEXTAREA_XPATH)
            ta_values = [t.get_attribute('value') for t in textareas]
            sheet_txt = drv.find_element(By.XPATH, "//*[@role='dialog']").text
            leaked = [k for k in ('sk-full-secret-1', 'sk-full-secret-2') if k in sheet_txt]
            print('[edit-echo-drawer] 摘要:', json.dumps(summaries, ensure_ascii=False))
            print('[edit-echo-drawer] textarea 值(应空):', json.dumps(ta_values, ensure_ascii=False))
            print('[edit-echo-drawer] 完整密钥泄漏:', json.dumps(leaked, ensure_ascii=False))
            time.sleep(0.5)
            drv.save_screenshot(f'{ART}/device_drawer_edit_echo_light.png')

            # ===== 4) 留空保存不清池：改名称，密钥区留空 → 保存 =====
            new_name = name2 + '_改名'
            name_in = WebDriverWait(drv, 5).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='如：音箱-客厅位']")))
            name_in.clear()
            name_in.send_keys(new_name)
            time.sleep(0.5)
            drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
            ok3 = wait_toast(drv, '测试 API 已保存')
            print('[keep-pool] 改名保存 toast:', ok3)
            time.sleep(2)
            show_apis(drv, '[keep-pool]')
            # 重开编辑验证池仍保留（2 密钥）
            drv.get(BASE + '/devices/api')
            WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            time.sleep(2)
            WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='操作 {new_name}']"))).click()
            time.sleep(0.8)
            WebDriverWait(drv, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]"))).click()
            time.sleep(1.2)
            summaries2 = [e.text for e in drv.find_elements(By.XPATH, "//*[contains(text(), '已配置') and contains(text(), '个密钥')]")]
            print('[keep-pool] 重开摘要(应仍 2 个):', json.dumps(summaries2, ensure_ascii=False))
        except Exception as e:
            print('[edit-echo-drawer] FAIL:', str(e)[:300])

        # ===== 6) 评估维度 apiEndpoints 不渲染密钥池 =====
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        opened = False
        try:
            dim_btn = WebDriverWait(drv, 12).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, '编辑维度')] | //button[contains(normalize-space(.), '新建维度')] | //button[contains(normalize-space(.), '新增维度')]")))
            dim_btn.click()
            opened = True
        except Exception:
            pass
        if opened:
            time.sleep(1.5)
            # 切到「API配置」分节（仅主维度；子维度无该 tab）
            try:
                api_tab = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), 'API配置')]")
                if api_tab:
                    api_tab[0].click()
                    time.sleep(0.8)
                    print('[evaluation] 已切到 API配置 分节')
            except Exception:
                pass
            key_tas = drv.find_elements(By.XPATH, KEY_TEXTAREA_XPATH)
            url_inputs = drv.find_elements(By.XPATH, "//input[contains(@aria-label, '端点 URL')]")
            print('[evaluation] 密钥池 textarea 数量(应为0):', len(key_tas))
            print('[evaluation] API 端点输入数量:', len(url_inputs))
            time.sleep(0.6)
            drv.save_screenshot(f'{ART}/evaluation_no_keypool_light.png')
        else:
            print('[evaluation] 未打开维度编辑（截图目录留待走查）')

        with open(f'{ART}/summary.json', 'w', encoding='utf-8') as f:
            json.dump({'suffix': SUFFIX, 'names': {'dialog': name1, 'drawer': name2}}, f, ensure_ascii=False, indent=2)
        print('DONE')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
