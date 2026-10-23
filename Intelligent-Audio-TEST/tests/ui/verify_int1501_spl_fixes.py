# -*- coding: utf-8 -*-
"""INT-1501 SPL 映射域缺陷复验（真实库栈 5700 / dev server 5315）。

覆盖：
1) 表单 Select 闭合态显示 label（物理域关联播放设备/设备类型、数字域关联被测 API，含编辑回填）
2) 物理域搜索命中关联设备名
3) mock 注释残留（脚本外 grep 核对）
4) 「导入映射数据」禁用态 tooltip 可达
附浅/深色截图 + Network 证据。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1501_spl')
os.makedirs(ART, exist_ok=True)

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5315')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
RESULTS = []


def rec(name, ok, detail=''):
    RESULTS.append({'check': name, 'ok': bool(ok), 'detail': detail})
    print(('PASS' if ok else 'FAIL'), name, '|', detail)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
    drv.set_page_load_timeout(45)
    return drv


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'username'))).send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]"))
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)


def open_spl(drv):
    drv.get(BASE + '/SPLMapping')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    WebDriverWait(drv, 30).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
    time.sleep(1.5)


def click_trigger(drv, aria):
    trig = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, f"//button[@aria-label='{aria}']")))
    drv.execute_script('arguments[0].scrollIntoView({block:"center"})', trig)
    time.sleep(0.3)
    js_click(drv, trig)
    WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='select-content'] [role='option']")))
    time.sleep(0.6)


def option_texts(drv):
    return [e.text.strip() for e in drv.find_elements(
        By.CSS_SELECTOR, "[data-slot='select-content'] [role='option']")]


def pick_option(drv, text=None, index=0):
    opts = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content'] [role='option']")
    target = None
    if text is not None:
        for o in opts:
            if text in (o.text or ''):
                target = o
                break
    if target is None:
        target = opts[index]
    label = (target.text or '').strip()
    js_click(drv, target)
    time.sleep(0.8)
    return label


def trigger_text(drv, aria):
    el = drv.find_element(By.XPATH, f"//button[@aria-label='{aria}']")
    txt = (el.text or '').strip()
    if not txt:
        txt = (el.find_element(By.CSS_SELECTOR, "[data-slot='select-value']").text or '').strip()
    return txt


def close_dialog(drv):
    btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='取消']") if b.is_displayed()]
    if btns:
        js_click(drv, btns[-1])
    time.sleep(0.8)


def network_get(drv, needle):
    hits = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg.get('params', {}).get('response', {})
        url = resp.get('url', '')
        if needle in url:
            hits.append((url, resp.get('status')))
    return hits


def main():
    drv = _driver()
    try:
        login(drv)
        drv.get_log('performance')  # 先 drain 基线，页面加载产生的 /spl 请求才留在日志里
        open_spl(drv)

        # ---------- 物理域：新建表单 Select 闭合态 ----------
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加增益映射')]"))
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(0.8)

        click_trigger(drv, '关联播放设备')
        opts = option_texts(drv)
        print('设备下拉选项:', json.dumps(opts[:5], ensure_ascii=False), '共', len(opts))
        chosen = pick_option(drv, index=0)
        dev_txt = trigger_text(drv, '关联播放设备')
        rec('新建表单·关联播放设备闭合态=选项 label', dev_txt == chosen and not dev_txt.isdigit(),
            f'选中「{chosen}」→ 触发器「{dev_txt}」')

        click_trigger(drv, '设备类型')
        pick_option(drv, text='噪声')
        type_txt = trigger_text(drv, '设备类型')
        rec('新建表单·设备类型闭合态=中文 label', type_txt == '噪声', f'触发器「{type_txt}」')

        drv.save_screenshot(os.path.join(ART, '03_form_create_filled_light.png'))
        close_dialog(drv)
        drv.save_screenshot(os.path.join(ART, '04_list_after_cancel_light.png'))

        # ---------- 物理域：编辑回填 ----------
        first_action = WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[starts-with(@aria-label,'映射 ') and contains(@aria-label,'的操作')]")))
        js_click(drv, first_action)
        WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='menuitem' and contains(normalize-space(.), '编辑')]")))
        time.sleep(0.5)
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='menuitem' and contains(normalize-space(.), '编辑')]"))
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(0.8)
        edit_dev = trigger_text(drv, '关联播放设备')
        edit_type = trigger_text(drv, '设备类型')
        rec('编辑回填·关联播放设备显示名称', edit_dev != '' and not edit_dev.isdigit(), f'「{edit_dev}」')
        rec('编辑回填·设备类型显示中文', edit_type in ('干声', '噪声') or edit_type == '', f'「{edit_type}」')
        drv.save_screenshot(os.path.join(ART, '13_form_edit_light.png'))
        close_dialog(drv)

        # ---------- 物理域：搜索关联设备名 ----------
        # 取第 3 行的「关联播放设备」名，并确认该串不出现在任何映射名称里——
        # 否则命中的可能是映射名称而非 deviceName，验证不到本卡修复点。
        rows_all = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        dev_name = rows_all[2].find_elements(By.TAG_NAME, 'td')[2].text.split('（')[0].strip()
        mapping_names = [r.find_elements(By.TAG_NAME, 'td')[1].text for r in rows_all]
        print('首行设备名列:', dev_name, '| 映射名称:', json.dumps(mapping_names, ensure_ascii=False))
        rec('搜索词仅存在于设备名（排除名称命中）',
            dev_name != '' and all(dev_name not in n for n in mapping_names),
            f'「{dev_name}」不在 {json.dumps(mapping_names, ensure_ascii=False)} 中')
        search = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索映射']")
        search.send_keys(dev_name)
        time.sleep(1.8)
        rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        body = drv.find_element(By.CSS_SELECTOR, 'table tbody').text
        rec('搜索设备名命中映射', len(rows) == 1 and dev_name in body,
            f'关键词「{dev_name}」→ {len(rows)} 行')
        drv.save_screenshot(os.path.join(ART, '51_search_device_name_light.png'))
        # 键盘清空（更贴近真实操作），再重载页面回到全量列表作为后续截图基线
        search.send_keys(Keys.CONTROL, 'a')
        search.send_keys(Keys.DELETE)
        time.sleep(1.8)
        after_clear = len(drv.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
        rec('清空搜索恢复全量列表', after_clear > 1, f'{after_clear} 行')
        open_spl(drv)

        # ---------- tooltip 可达 ----------
        span = drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '导入映射数据')]/ancestor::span[1]")
        ActionChains(drv).move_to_element(span).perform()
        tip = WebDriverWait(drv, 8).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-slot='tooltip-content']")))
        tip_txt = tip.text.strip()
        rec('禁用按钮 tooltip 可达', '映射导入后端建设中' in tip_txt, f'tooltip「{tip_txt}」')
        drv.save_screenshot(os.path.join(ART, '61_import_tooltip_light.png'))
        ActionChains(drv).move_to_element(drv.find_element(By.TAG_NAME, 'body')).perform()
        time.sleep(0.5)

        # ---------- 数字域：关联被测 API ----------
        drv.find_element(By.XPATH, "//button[@role='tab' and contains(., 'RMS-SPL')]").click()
        time.sleep(1.5)
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加 RMS-SPL 映射')]"))
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.XPATH, "//button[@aria-label='关联被测 API']")))
        time.sleep(0.6)
        click_trigger(drv, '关联被测 API')
        api_opts = option_texts(drv)
        print('API 下拉选项:', json.dumps(api_opts[:5], ensure_ascii=False), '共', len(api_opts))
        if api_opts:
            chosen_api = pick_option(drv, index=0)
            api_txt = trigger_text(drv, '关联被测 API')
            rec('数字域·关联被测 API 闭合态=API 名称', api_txt == chosen_api and not api_txt.isdigit(),
                f'选中「{chosen_api}」→ 触发器「{api_txt}」')
        else:
            rec('数字域·关联被测 API 闭合态=API 名称', False, '下拉无选项（真实库 /apis 无数据）')
        drv.save_screenshot(os.path.join(ART, '32_digital_form_filled_light.png'))
        close_dialog(drv)

        # ---------- Network 证据 ----------
        hits = network_get(drv, '/api/v1/spl')
        rec('Network: GET /api/v1/spl 200', any(s == 200 for _, s in hits),
            json.dumps(hits[:4], ensure_ascii=False))

        # ---------- 深色 ----------
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        drv.get('about:blank')
        time.sleep(0.5)
        open_spl(drv)
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加增益映射')]"))
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(0.8)
        click_trigger(drv, '关联播放设备')
        dark_chosen = pick_option(drv, index=0)
        dark_dev = trigger_text(drv, '关联播放设备')
        rec('深色·关联播放设备闭合态=label', dark_dev == dark_chosen, f'「{dark_dev}」')
        drv.save_screenshot(os.path.join(ART, '12_form_create_filled_dark.png'))
        close_dialog(drv)
        span = drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '导入映射数据')]/ancestor::span[1]")
        ActionChains(drv).move_to_element(span).perform()
        tip = WebDriverWait(drv, 8).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-slot='tooltip-content']")))
        rec('深色·禁用按钮 tooltip 可达', '映射导入后端建设中' in tip.text, tip.text.strip())
        drv.save_screenshot(os.path.join(ART, '62_import_tooltip_dark.png'))

    finally:
        drv.quit()

    with open(os.path.join(ART, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    failed = [r for r in RESULTS if not r['ok']]
    print('\n=== SUMMARY:', len(RESULTS) - len(failed), 'pass /', len(failed), 'fail ===')
    for r in failed:
        print('FAILED:', r['check'], r['detail'])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
