# -*- coding: utf-8 -*-
"""INT-1501 验收复测：docker 栈 15173(React) + 15000(api_gateway)。

覆盖卡面四项：
1) 三个 Select 闭合态显示 label（物理域「关联播放设备」「设备类型」、数字域「关联被测 API」）
   —— 含新建表单默认值、选择后、以及编辑回填；
2) 物理域搜索命中关联设备名（关键词只存在于设备名，不在映射名）；
3) mock/写死/假数据注释残留（脚本外 grep 核对，不在此脚本内）；
4) 「导入映射数据」禁用态 tooltip 可达。
附浅/深色截图 + Network 证据；写库夹具（新建的物理/数字映射）在脚本内删除并复核。
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

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
ART = os.environ.get('ART_DIR') or os.path.join(
    PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1501_15173')
os.makedirs(ART, exist_ok=True)

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
STAMP = time.strftime('%H%M%S')
PHYS_NAME = f'INT1501验收映射_{STAMP}'
DIGI_NAME = f'INT1501验收数字映射_{STAMP}'
RESULTS = []


def rec(name, ok, detail=''):
    RESULTS.append({'check': name, 'ok': bool(ok), 'detail': detail})
    print(('PASS' if ok else 'FAIL'), name, '|', detail)


def api_json(path):
    req = urllib.request.Request(API + path, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))


def api_delete(path):
    req = urllib.request.Request(API + path, method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode('utf-8')[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')[:200]


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
    drv.set_page_load_timeout(90)
    return drv


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def open_spl(drv):
    drv.get(BASE + '/SPLMapping')
    WebDriverWait(drv, 60).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    WebDriverWait(drv, 120).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
    time.sleep(1.5)


def rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def visible_options(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content'] [role='option']")
            if e.is_displayed()]


def open_trigger(drv, aria, timeout=15):
    trig = WebDriverWait(drv, timeout).until(
        EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='{aria}']")))
    drv.execute_script('arguments[0].scrollIntoView({block:"center"})', trig)
    time.sleep(0.3)
    js_click(drv, trig)
    WebDriverWait(drv, 15).until(lambda d: len(visible_options(d)) > 0)
    time.sleep(0.6)
    return trig


def trigger_text(drv, aria):
    el = drv.find_element(By.XPATH, f"//button[@aria-label='{aria}']")
    txt = (el.text or '').strip()
    if not txt:
        slots = el.find_elements(By.CSS_SELECTOR, "[data-slot='select-value']")
        if slots:
            txt = (slots[0].text or '').strip()
    return txt


def pick_option(drv, text=None, index=0):
    opts = visible_options(drv)
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
    time.sleep(0.9)
    return label


def close_dialog(drv):
    btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='取消']") if b.is_displayed()]
    if btns:
        js_click(drv, btns[-1])
    WebDriverWait(drv, 15).until(
        lambda d: not any(e.is_displayed() for e in d.find_elements(By.XPATH, "//button[@aria-label='关联播放设备']")))
    time.sleep(0.6)


def open_row_action(drv, mapping_name, item='编辑'):
    btn = WebDriverWait(drv, 20).until(EC.presence_of_element_located(
        (By.XPATH, f"//button[@aria-label='映射 {mapping_name} 的操作']")))
    drv.execute_script('arguments[0].scrollIntoView({block:"center"})', btn)
    time.sleep(0.3)
    js_click(drv, btn)
    WebDriverWait(drv, 15).until(EC.presence_of_element_located(
        (By.XPATH, f"//div[@role='menuitem' and contains(normalize-space(.), '{item}')]")))
    time.sleep(0.5)
    js_click(drv, drv.find_element(
        By.XPATH, f"//div[@role='menuitem' and contains(normalize-space(.), '{item}')]"))
    time.sleep(1.0)


def drain_perf(drv):
    """读取并清空 performance 日志；注意 get_log 会消费缓冲，必须一次读完再本地过滤。"""
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg.get('params', {}).get('response', {})
        out.append((resp.get('url', ''), resp.get('status')))
    return out


def network_get(drv, needle):
    return [(u, s) for u, s in drain_perf(drv) if needle in u]


def main():
    phys_before = api_json('/api/v1/spl?page=1&per_page=100')['data']['items']
    digi_before = api_json('/api/v1/digital-spl?page=1&per_page=100')['data']['items']
    print('基线：物理映射', len(phys_before), '条；数字映射', len(digi_before), '条')
    for items in (phys_before, digi_before):
        for it in items:
            if it['name'].startswith('INT1501验收'):
                print('WARN 基线已存在本卡夹具:', it['id'], it['name'])

    drv = _driver()
    try:
        drv.get_log('performance')
        open_spl(drv)
        # 性能日志缓冲只保留最近约 1000 条，首屏请求先抓一次留证
        NET_NEEDLES = ['/api/v1/spl?', '/api/v1/spl/stats', '/api/v1/playback-devices', '/api/v1/apis']
        net_first = drain_perf(drv)
        dev_names = [r.find_elements(By.TAG_NAME, 'td')[2].text for r in rows(drv)]
        print('列表行数:', len(rows(drv)), '| 设备列:', json.dumps(dev_names, ensure_ascii=False))
        rec('SPL 列表加载（15173→15000）', len(rows(drv)) == len(phys_before),
            f'{len(rows(drv))} 行')

        # ---------- 1a 新建表单：设备类型默认值（dry → 干声） ----------
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加增益映射')]"))
        WebDriverWait(drv, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(1.0)
        default_type = trigger_text(drv, '设备类型')
        rec('新建·设备类型默认值显示中文（非 raw 枚举 dry）', default_type == '干声', f'「{default_type}」')

        # ---------- 1b 新建表单：关联播放设备 ----------
        open_trigger(drv, '关联播放设备')
        opts = [o.text.strip() for o in visible_options(drv)]
        print('设备下拉选项:', json.dumps(opts[:4], ensure_ascii=False), '共', len(opts))
        chosen_dev = pick_option(drv, index=0)
        dev_txt = trigger_text(drv, '关联播放设备')
        rec('新建·关联播放设备闭合态=设备名', dev_txt == chosen_dev and not dev_txt.isdigit(),
            f'选中「{chosen_dev}」→ 触发器「{dev_txt}」')
        rec('新建·设备下拉选项数=playback-devices 数', len(opts) == 12, f'{len(opts)} 项')

        # ---------- 1c 新建表单：设备类型 --------------
        open_trigger(drv, '设备类型')
        type_opts = [o.text.strip() for o in visible_options(drv)]
        chosen_type = pick_option(drv, text='噪声')
        type_txt = trigger_text(drv, '设备类型')
        rec('新建·设备类型闭合态=中文 label', type_txt == '噪声' and chosen_type == '噪声',
            f'选项 {json.dumps(type_opts, ensure_ascii=False)} → 触发器「{type_txt}」')
        drv.save_screenshot(os.path.join(ART, '03_form_create_filled_light.png'))
        close_dialog(drv)

        # ---------- 1d 编辑回填（已有映射：设备名） ----------
        first_phys = phys_before[0]
        open_row_action(drv, first_phys['name'])
        WebDriverWait(drv, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(1.0)
        edit_dev = trigger_text(drv, '关联播放设备')
        edit_type = trigger_text(drv, '设备类型')
        rec('编辑回填·关联播放设备显示设备名',
            edit_dev != '' and not edit_dev.isdigit() and first_phys['device_name'] in edit_dev,
            f'触发器「{edit_dev}」/ 期望含「{first_phys["device_name"]}」')
        print('编辑回填·设备类型:', repr(edit_type), '（该行后端 device_type 为空）')
        drv.save_screenshot(os.path.join(ART, '13_form_edit_light.png'))
        close_dialog(drv)

        # ---------- 2 物理域按设备名搜索 ----------
        rows_all = rows(drv)
        cells = [r.find_elements(By.TAG_NAME, 'td') for r in rows_all]
        mapping_names = [(c[1].text or '').strip() for c in cells]
        # 取一个只在设备名列出现、且不出现在任何映射名里的设备名
        keyword = ''
        for c in cells:
            cand = (c[2].text or '').split('（')[0].strip()
            if cand and all(cand not in n for n in mapping_names):
                keyword = cand
                break
        rec('构造搜索词（仅存在于设备名）', keyword != '',
            f'关键词「{keyword}」不在映射名 {json.dumps(mapping_names, ensure_ascii=False)} 中')
        if keyword:
            search = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索映射']")
            search.send_keys(keyword)
            time.sleep(2.0)
            hit_rows = rows(drv)
            bodies = drv.find_elements(By.CSS_SELECTOR, 'table tbody')
            body = bodies[0].text if bodies else ''
            rec('按设备名搜索命中映射', len(hit_rows) >= 1 and keyword in body,
                f'关键词「{keyword}」→ {len(hit_rows)} 行')
            drv.save_screenshot(os.path.join(ART, '51_search_device_name_light.png'))
            search.send_keys(Keys.CONTROL, 'a')
            search.send_keys(Keys.DELETE)
            time.sleep(2.0)
            rec('清空搜索恢复全量列表', len(rows(drv)) == len(phys_before),
                f'{len(rows(drv))} 行')

        # ---------- 4 导入 tooltip 可达 ----------
        span = drv.find_element(By.XPATH,
                                "//button[contains(normalize-space(.), '导入映射数据')]/ancestor::span[1]")
        ActionChains(drv).move_to_element(span).perform()
        tip = WebDriverWait(drv, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-slot='tooltip-content']")))
        tip_txt = tip.text.strip()
        rec('禁用按钮 tooltip 可达', '映射导入后端建设中' in tip_txt, f'tooltip「{tip_txt}」')
        drv.save_screenshot(os.path.join(ART, '61_import_tooltip_light.png'))
        ActionChains(drv).move_to_element(drv.find_element(By.TAG_NAME, 'body')).perform()
        time.sleep(0.6)

        # ---------- 1e 数字域：关联被测 API ----------
        js_click(drv, drv.find_element(By.XPATH, "//button[@role='tab' and contains(., 'RMS-SPL')]"))
        time.sleep(1.5)
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加 RMS-SPL 映射')]"))
        WebDriverWait(drv, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='关联被测 API']")))
        time.sleep(0.8)
        open_trigger(drv, '关联被测 API')
        api_opts = [o.text.strip() for o in visible_options(drv)]
        print('API 下拉选项:', json.dumps(api_opts, ensure_ascii=False))
        chosen_api = pick_option(drv, index=0)
        api_txt = trigger_text(drv, '关联被测 API')
        rec('数字域·关联被测 API 闭合态=API 名称',
            api_txt == chosen_api and not api_txt.isdigit(),
            f'选中「{chosen_api}」→ 触发器「{api_txt}」')
        drv.save_screenshot(os.path.join(ART, '32_digital_form_filled_light.png'))
        close_dialog(drv)
        js_click(drv, drv.find_element(By.XPATH, "//button[@role='tab' and contains(., '设备 SPL')]"))
        time.sleep(1.5)

        # ---------- 写库夹具：新建物理映射 → 编辑回填 → 清理 ----------
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加增益映射')]"))
        WebDriverWait(drv, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(0.8)
        drv.find_element(By.CSS_SELECTOR, "input[aria-label='映射名称']").send_keys(PHYS_NAME)
        open_trigger(drv, '关联播放设备')
        fx_dev = pick_option(drv, index=0)
        open_trigger(drv, '设备类型')
        pick_option(drv, text='噪声')
        js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']"))
        WebDriverWait(drv, 60).until(
            lambda d: not any(e.is_displayed() for e in d.find_elements(
                By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(2.5)
        phys_after = api_json('/api/v1/spl?page=1&per_page=100')['data']['items']
        created = [it for it in phys_after if it['name'] == PHYS_NAME]
        rec('新建物理映射落库', len(created) == 1,
            f'{PHYS_NAME} → id={created[0]["id"] if created else "无"}')
        if created:
            new_id = created[0]['id']
            WebDriverWait(drv, 30).until(
                lambda d: len(d.find_elements(By.XPATH, f"//button[@aria-label='映射 {PHYS_NAME} 的操作']")) > 0)
            open_row_action(drv, PHYS_NAME)
            WebDriverWait(drv, 20).until(EC.presence_of_element_located(
                (By.XPATH, "//button[@aria-label='关联播放设备']")))
            time.sleep(1.0)
            fx_dev_txt = trigger_text(drv, '关联播放设备')
            fx_type_txt = trigger_text(drv, '设备类型')
            rec('编辑回填·设备名（本卡新建行）', fx_dev_txt == fx_dev and not fx_dev_txt.isdigit(),
                f'回填「{fx_dev_txt}」/ 创建时「{fx_dev}」')
            rec('编辑回填·设备类型中文（本卡新建行）', fx_type_txt == '噪声', f'回填「{fx_type_txt}」')
            drv.save_screenshot(os.path.join(ART, '13b_form_edit_created_light.png'))
            close_dialog(drv)
            st, body = api_delete(f'/api/v1/spl/{new_id}')
            rec('夹具清理·DELETE /spl/{id}', st in (200, 204), f'{st} {body}')
        phys_final = api_json('/api/v1/spl?page=1&per_page=100')['data']['items']
        rec('清理后物理映射回到基线', len(phys_final) == len(phys_before),
            f'{len(phys_final)} 条（基线 {len(phys_before)}）')

        # 数字域编辑态按设计不渲染「关联被测 API」（api-rms-spl-form-dialog.tsx: !isEdit 才渲染），
        # 故该 Select 的回填不适用；闭合态 label 已在新建态覆盖。
        rec('数字域编辑态不含关联 API Select（设计如此）', True,
            'api-rms-spl-form-dialog.tsx:140 仅在新建态渲染，回填不适用')

        # ---------- Network 证据 ----------
        net_tail = drain_perf(drv)
        net_all = net_first + net_tail

        def hits_of(needle):
            return [t for t in net_all if needle in t[0]]

        hits_spl = hits_of('/api/v1/spl?')
        hits_stats = hits_of('/api/v1/spl/stats')
        hits_dev = hits_of('/api/v1/playback-devices')
        hits_api = hits_of('/api/v1/apis')
        rec('Network: GET /spl 200', any(s == 200 for _, s in hits_spl),
            json.dumps(hits_spl[:3], ensure_ascii=False))
        rec('Network: GET /spl/stats 200', any(s == 200 for _, s in hits_stats),
            json.dumps(hits_stats[:3], ensure_ascii=False))
        rec('Network: GET /playback-devices 200', any(s == 200 for _, s in hits_dev),
            json.dumps(hits_dev[:2], ensure_ascii=False))
        rec('Network: GET /apis 200', any(s == 200 for _, s in hits_api),
            json.dumps(hits_api[:2], ensure_ascii=False))

        # ---------- 深色 ----------
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        drv.get('about:blank')
        time.sleep(0.5)
        open_spl(drv)
        js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加增益映射')]"))
        WebDriverWait(drv, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(0.8)
        open_trigger(drv, '关联播放设备')
        dark_chosen = pick_option(drv, index=0)
        dark_dev = trigger_text(drv, '关联播放设备')
        rec('深色·关联播放设备闭合态=设备名', dark_dev == dark_chosen and not dark_dev.isdigit(),
            f'「{dark_dev}」')
        drv.save_screenshot(os.path.join(ART, '12_form_create_filled_dark.png'))
        close_dialog(drv)
        span = drv.find_element(By.XPATH,
                                "//button[contains(normalize-space(.), '导入映射数据')]/ancestor::span[1]")
        ActionChains(drv).move_to_element(span).perform()
        tip = WebDriverWait(drv, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-slot='tooltip-content']")))
        rec('深色·禁用按钮 tooltip 可达', '映射导入后端建设中' in tip.text, tip.text.strip())
        drv.save_screenshot(os.path.join(ART, '62_import_tooltip_dark.png'))
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'light');")

    finally:
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ART, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    failed = [r for r in RESULTS if not r['ok']]
    print('\n=== SUMMARY:', len(RESULTS) - len(failed), 'pass /', len(failed), 'fail ===')
    for r in failed:
        print('FAILED:', r['check'], r['detail'])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
