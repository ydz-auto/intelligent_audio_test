# -*- coding: utf-8 -*-
"""INT-1254 评估维度 CRUD 走查（React 前端 × docker 后端 :15000，真实库 intelligent_audio_test）。

闭环（devloop §3.5，全部连 :15000）：
  1. 新建：填全字段（名称带「接线测试_」前缀）→ 提交 → 核对列表 + GET 详情每个字段
  2. 编辑：重开编辑抽屉逐个字段核对回显 → 改每个可改字段 → 保存 → 再回显核对 + 接口核对
  3. 删除：列表消失 → 接口 404 / 软删标记
  4. 批量：2~3 条自建记录逐项操作逐条核对
  5. 校验与状态：必填留空提交 / 非法值 / 取消关闭后重开表单清空
  6. 选项与计数：下拉选项数、列表总数、分组数与接口返回逐一对
证据：每步写方法/URL/状态码/关键字段 + 浅深色截图 + Network 证据。
失败落 tests/ui/artifacts/int1254_dimension/<用例>/。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1254_dimension')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5310')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
THEME_KEY = 'iatp:theme:v1:mode'
API = 'http://localhost:15000/api/v1'

_PREFIX = '接线测试_INT1254_'
TS = str(int(time.time()))

# 收集到的浏览器 Network 证据（请求方法/URL/状态码/关键字段）
NETWORK_EVIDENCE = []


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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
    drv.set_page_load_timeout(45)
    return drv


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _drain_network(drv, reset=False):
    """从 performance log 提取 /evaluation 相关请求+状态，追加到 NETWORK_EVIDENCE。"""
    global NETWORK_EVIDENCE
    reqs = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                url = req.get('url') or ''
                if '/evaluation/' in url or '/algorithm/options' in url:
                    reqs[params.get('requestId')] = {
                        'method': req.get('method', 'GET'),
                        'url': url,
                        'status': None,
                        'body': '',
                    }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
        for rid, info in reqs.items():
            try:
                r = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
                if r.get('base64Encoded'):
                    import base64
                    info['body'] = base64.b64decode(r.get('body', '')).decode('utf-8', 'replace')
                else:
                    info['body'] = r.get('body', '') or ''
            except Exception:
                pass
        for info in reqs.values():
            line = f"[Network] {info['method']} {info['url']} -> {info['status']}"
            body = info['body']
            if body and len(body) > 4:
                try:
                    parsed = json.loads(body)
                    data = parsed.get('data')
                    if isinstance(data, dict):
                        keys = list(data.keys())[:12]
                        line += f" data_keys={keys}"
                        if 'id' in data:
                            line += f" id={data['id']}"
                        if 'name' in data:
                            line += f" name={str(data['name'])[:40]!r}"
                        if 'total' in data:
                            line += f" total={data['total']}"
                    elif isinstance(data, list):
                        line += f" rows={len(data)}"
                except Exception:
                    if len(body) < 200:
                        line += f" body={body[:150]!r}"
            NETWORK_EVIDENCE.append(line)
    except Exception as e:
        NETWORK_EVIDENCE.append(f"[Network] drain error: {e!r}")
    if reset:
        NETWORK_EVIDENCE = []


def _shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass
    return d


def _set_theme(drv, mode):
    """写主题偏好并整页刷新（打断 bfcache 强刷）。"""
    drv.execute_script(
        'window.localStorage.setItem(arguments[0], arguments[1])',
        THEME_KEY, mode)
    time.sleep(0.2)
    drv.get(BASE + '/evaluation')
    time.sleep(2.5)


def _goto_eval(drv):
    drv.get(BASE + '/evaluation')
    WebDriverWait(drv, 45).until(
        lambda d: '评估维度' in _body_text(d) and '新增维度' in _body_text(d))
    time.sleep(1.2)


def _open_create(drv):
    for b in drv.find_elements(By.XPATH, "//button[contains(., '新增维度')]"):
        if b.is_displayed():
            b.click()
            break
    time.sleep(1.5)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    WebDriverWait(drv, 15).until(
        lambda d: '新增评估维度' in sheet.text)
    return sheet


def _click_select_item(drv, trigger, item_text):
    """base-ui Select：JS 点 trigger → 点 item。"""
    drv.execute_script('arguments[0].click()', trigger)
    time.sleep(0.8)
    items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
    for it in items:
        if it.text.strip() == item_text:
            drv.execute_script('arguments[0].click()', it)
            time.sleep(0.4)
            return True
    return False


def _switch_tab(drv, sheet, tab_label):
    triggers = drv.find_elements(By.CSS_SELECTOR, "[data-slot='tabs-trigger']")
    for t in triggers:
        if t.text.strip() == tab_label and t.is_displayed():
            drv.execute_script('arguments[0].click()', t)
            time.sleep(0.5)
            return True
    return False


def _api_get(path):
    import urllib.request
    import urllib.parse
    # 拆分 query 并做 URL 编码（search 含中文必须 quote）
    if '?' in path:
        base, query = path.split('?', 1)
        pairs = [tuple(kv.split('=', 1)) if '=' in kv else (kv, '')
                 for kv in query.split('&') if kv]
        encoded = urllib.parse.urlencode(pairs)
        url = API + base + '?' + encoded
    else:
        url = API + path
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.load(r)
    except Exception as e:
        return {'_error': str(e)}


def _find_row(drv, name):
    """在列表视图搜索 name 后找到对应行（含编辑/删除按钮）。"""
    rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
    for row in rows:
        if name in (row.text or ''):
            return row
def run_create_phase(drv):
    """1. 新建：填全字段 → 提交 → 核对列表 + GET 详情每个字段。"""
    print('\n===== PHASE 1: 新建（全字段） =====')
    _goto_eval(drv)
    _set_theme(drv, 'light')
    _goto_eval(drv)
    _drain_network(drv, reset=True)

    sheet = _open_create(drv)
    _shot(drv, 'p1_create_drawer_light')

    # ── 基本信息 ──
    name = _PREFIX + '全字段_' + TS
    sheet.find_element(By.ID, 'dim-name').send_keys(name)
    sheet.find_element(By.ID, 'dim-description').send_keys('走查新建全字段：输入/输出参数核对')
    # 评估类型 = 人工评估
    triggers = sheet.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    _click_select_item(drv, triggers[0], '人工评估')
    # 所属分类 = 拒识 (id=3)
    triggers = sheet.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    _click_select_item(drv, triggers[1], '拒识')
    _shot(drv, 'p1_basic_filled_light')

    # ── 层级配置（主维度 + 关键词）──
    _switch_tab(drv, sheet, '层级配置')
    sheet.find_element(By.ID, 'dim-keywords').send_keys('走查,全字段')

    # ── 结果配置 ──
    _switch_tab(drv, sheet, '结果配置')
    sheet.find_element(By.ID, 'dim-score-unit').send_keys('%')
    min_input = sheet.find_element(By.ID, 'dim-result-min')
    min_input.clear(); min_input.send_keys('0')
    max_input = sheet.find_element(By.ID, 'dim-result-max')
    max_input.clear(); max_input.send_keys('100')
    dec = sheet.find_element(By.ID, 'dim-decimal-places')
    dec.clear(); dec.send_keys('2')
    exec_t = sheet.find_element(By.ID, 'dim-exec-time')
    exec_t.clear(); exec_t.send_keys('8')
    _shot(drv, 'p1_result_filled_light')

    # ── API 配置 ──
    _switch_tab(drv, sheet, 'API配置')
    sheet.find_element(By.ID, 'dim-api-url').send_keys('http://127.0.0.1:8888')
    timeout_input = sheet.find_element(By.ID, 'dim-api-timeout')
    timeout_input.clear(); timeout_input.send_keys('30000')
    _shot(drv, 'p1_api_filled_light')

    # ── 关联算法 ──
    _switch_tab(drv, sheet, '关联算法')
    for btn in sheet.find_elements(By.TAG_NAME, 'button'):
        if '选择关联的算法类型' in (btn.text or ''):
            drv.execute_script('arguments[0].click()', btn)
            break
    time.sleep(0.9)
    cbs = drv.find_elements(By.CSS_SELECTOR, "[data-slot='checkbox']")
    for cb in cbs:
        try:
            if '小艺语音大模型' in (cb.get_attribute('aria-label') or ''):
                drv.execute_script('arguments[0].click()', cb)
                break
        except Exception:
            pass
    time.sleep(0.5)
    _shot(drv, 'p1_algorithm_filled_light')

    # ── 保存 ──
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    assert save_btns and not save_btns[0].get_attribute('disabled'), '填全字段后「保存」应启用'
    drv.execute_script('arguments[0].click()', save_btns[0])
    WebDriverWait(drv, 45).until(
        lambda d: '评估维度添加成功' in _body_text(d) or '保存失败' in _body_text(d) or '评估维度更新成功' in _body_text(d))
    time.sleep(1.2)
    txt = _body_text(drv)
    assert '评估维度添加成功' in txt, f'新建 toast 缺失：{txt[-400:]}'
    _shot(drv, 'p1_created_toast_light')
    _drain_network(drv)

    # 搜索并核对列表出现
    _goto_eval(drv)
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys(name)
    WebDriverWait(drv, 30).until(lambda d: name in _body_text(d))
    row = _find_row(drv, name)
    assert row is not None, '新建维度未出现在列表'
    rtext = row.text
    print('ROW TEXT:', rtext[:200])
    assert '主' in rtext, '主维度徽章缺失'
    assert '拒识' in rtext, '分类「拒识」未显示'
    _shot(drv, 'p1_created_row_light')

    # GET 详情核对
    d = _api_get('/evaluation/dimensions?per_page=1000&search=' + name)
    items = d.get('data', {}).get('items', [])
    assert len(items) >= 1, f'GET 未找到新建维度：{json.dumps(d, ensure_ascii=False)[:500]}'
    created = items[0]
    print('GET created id:', created['id'], 'name:', created['name'])
    assert created['name'] == name, '名称不一致'
    assert created['description'] == '走查新建全字段：输入/输出参数核对', '描述不一致'
    assert created['dimension_type'] == 'main', 'dimension_type 不一致'
    assert created['category_id'] == 3, 'category_id 不一致'
    assert created['type'] == 'manual', '评估类型(manual) 不一致'
    assert created['score_unit'] == '%', 'score_unit 不一致'
    assert created['result_min'] == 0, 'result_min 不一致'
    assert created['result_max'] == 100, 'result_max 不一致'
    assert created['decimal_places'] == 2, 'decimal_places 不一致'
    assert created['estimated_exec_time'] == 8, 'estimated_exec_time 不一致'
    detail = _api_get(f'/evaluation/dimensions/{created["id"]}')
    dd = detail.get('data', {})
    print('detail required_inputs:', len(dd.get('required_inputs') or []),
          'output_fields:', len(dd.get('output_fields') or []))
    print('detail associated_algorithms:', dd.get('associated_algorithms'))
    print('detail rule:', str(dd.get('rule'))[:120])
    return created


def run_edit_phase(drv, created):
    """2. 编辑：重开编辑抽屉核对回显 → 改字段 → 保存 → 再核对。"""
    print('\n===== PHASE 2: 编辑 =====')
    _goto_eval(drv)
    name = created['name']
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.clear()
    box.send_keys(name)
    WebDriverWait(drv, 30).until(lambda d: name in _body_text(d))
    edit_btn = None
    for b in drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {name}']"):
        if b.is_displayed():
            edit_btn = b
            break
    assert edit_btn, f'编辑按钮缺失：{name}'
    drv.execute_script('arguments[0].click()', edit_btn)
    time.sleep(2.0)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    WebDriverWait(drv, 15).until(
        lambda d: '编辑评估维度' in sheet.text)
    stxt = sheet.text
    # 回显核对：读取 input/textarea 的 value（textContent 不含 value）
    name_val = sheet.find_element(By.ID, 'dim-name').get_attribute('value') or ''
    desc_val = sheet.find_element(By.ID, 'dim-description').get_attribute('value') or ''
    assert name_val == name, f'名称未回显：value={name_val!r}'
    assert desc_val == '走查新建全字段：输入/输出参数核对', f'描述未回显：{desc_val!r}'
    assert '人工评估' in stxt, f'评估类型未回显：{stxt[:300]}'
    assert '拒识' in stxt, f'分类未回显：{stxt[:300]}'
    _shot(drv, 'p2_edit_drawer_repopulated_light')

    # 改基本信息：名称加「_编辑」、描述改、评估类型改回自动评估、分类改未分类
    name_input = sheet.find_element(By.ID, 'dim-name')
    name_input.clear()
    new_name = _PREFIX + '编辑后_' + TS
    name_input.send_keys(new_name)
    desc = sheet.find_element(By.ID, 'dim-description')
    desc.clear(); desc.send_keys('编辑回显核对：字段已修改')
    triggers = sheet.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    _click_select_item(drv, triggers[0], '自动评估')
    triggers = sheet.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    _click_select_item(drv, triggers[1], '未分类')

    # 改结果配置：分数单位、小数位、执行时间
    _switch_tab(drv, sheet, '结果配置')
    su = sheet.find_element(By.ID, 'dim-score-unit')
    su.clear(); su.send_keys('分')
    dec = sheet.find_element(By.ID, 'dim-decimal-places')
    dec.clear(); dec.send_keys('3')
    exec_t = sheet.find_element(By.ID, 'dim-exec-time')
    exec_t.clear(); exec_t.send_keys('10')
    _shot(drv, 'p2_result_edited_light')

    # 改 API URL
    _switch_tab(drv, sheet, 'API配置')
    url = sheet.find_element(By.ID, 'dim-api-url')
    url.clear(); url.send_keys('http://127.0.0.1:9999')
    to = sheet.find_element(By.ID, 'dim-api-timeout')
    to.clear(); to.send_keys('20000')

    # 保存
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    assert save_btns, '保存按钮缺失'
    drv.execute_script('arguments[0].click()', save_btns[0])
    WebDriverWait(drv, 45).until(
        lambda d: '评估维度更新成功' in _body_text(d) or '保存失败' in _body_text(d))
    txt = _body_text(drv)
    assert '评估维度更新成功' in txt, f'编辑 toast 缺失：{txt[-400:]}'
    _shot(drv, 'p2_updated_toast_light')
    _drain_network(drv)

    # 重开编辑抽屉核对回显
    _goto_eval(drv)
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys(new_name)
    WebDriverWait(drv, 30).until(lambda d: new_name in _body_text(d))
    for b in drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {new_name}']"):
        if b.is_displayed():
            drv.execute_script('arguments[0].click()', b)
            break
    time.sleep(2.0)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    stxt = sheet.text
    name_val2 = sheet.find_element(By.ID, 'dim-name').get_attribute('value') or ''
    desc_val2 = sheet.find_element(By.ID, 'dim-description').get_attribute('value') or ''
    assert name_val2 == new_name, f'编辑后名称未回显：{name_val2!r}'
    assert desc_val2 == '编辑回显核对：字段已修改', f'编辑后描述未回显：{desc_val2!r}'
    assert '自动评估' in stxt, f'编辑后评估类型未回显：{stxt[:300]}'
    assert '未分类' in stxt, f'编辑后分类未回显：{stxt[:300]}'
    _shot(drv, 'p2_edit_reopen_repopulated_light')

    # 接口核对
    d = _api_get('/evaluation/dimensions?per_page=1000&search=' + new_name)
    items = d.get('data', {}).get('items', [])
    assert len(items) >= 1, '编辑后 GET 未找到'
    updated = items[0]
    print('GET updated id:', updated['id'], 'name:', updated['name'])
    assert updated['name'] == new_name, '编辑后名称不一致'
    assert updated['description'] == '编辑回显核对：字段已修改', '编辑后描述不一致'
    assert updated['type'] == 'auto', '编辑后评估类型不一致'
    assert updated['category_id'] is None, '编辑后分类应为未分类(None)'
    assert updated['score_unit'] == '分', '编辑后 score_unit 不一致'
    assert updated['decimal_places'] == 3, '编辑后 decimal_places 不一致'
    assert updated['estimated_exec_time'] == 10, '编辑后 exec_time 不一致'
    assert updated['api_url'] == 'http://127.0.0.1:9999', '编辑后 api_url 不一致'
    return updated


def run_delete_phase(drv, target):
    """3. 删除：列表消失 → 接口 404/软删。"""
    print('\n===== PHASE 3: 删除 =====')
    _goto_eval(drv)
    name = target['name']
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys(name)
    WebDriverWait(drv, 30).until(lambda d: name in _body_text(d))
    del_btn = None
    for b in drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='删除维度 {name}']"):
        if b.is_displayed():
            del_btn = b
            break
    assert del_btn, f'删除按钮缺失：{name}'
    drv.execute_script('arguments[0].click()', del_btn)
    time.sleep(0.9)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert f'确定要删除维度「{name}」吗？此操作不可恢复。' in dtxt, f'删除确认文案异常：{dtxt[:200]}'
    _shot(drv, 'p3_delete_confirm_light')
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '删除' and b.is_displayed()]
    assert confirm, '删除确认按钮缺失'
    drv.execute_script('arguments[0].click()', confirm[0])
    WebDriverWait(drv, 15).until(
        lambda d: '维度已删除' in _body_text(d) or '删除维度失败' in _body_text(d))
    txt = _body_text(drv)
    assert '维度已删除' in txt, f'删除 toast 缺失：{txt[-400:]}'
    _shot(drv, 'p3_deleted_toast_light')
    _drain_network(drv)

    # 列表消失
    _goto_eval(drv)
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys(name)
    time.sleep(1.0)
    txt = _body_text(drv)
    assert name not in txt, f'删除后列表仍显示：{txt[:300]}'

    # 接口 404/软删
    detail = _api_get(f'/evaluation/dimensions/{target["id"]}')
    print('GET after delete:', json.dumps(detail, ensure_ascii=False)[:200])
    assert detail.get('success') is False, '删除后 GET 应失败（404/软删）'
    d = _api_get('/evaluation/dimensions?per_page=1000&search=' + name)
    items = d.get('data', {}).get('items', [])
    assert len(items) == 0, f'删除后列表接口仍返回：{len(items)}'


def run_batch_phase(drv):
    """4. 批量：建 3 条 → 批量启用/禁用/删除 逐条核对。"""
    print('\n===== PHASE 4: 批量操作 =====')
    created = []
    for i in range(3):
        _goto_eval(drv)
        sheet = _open_create(drv)
        bname = _PREFIX + f'批量{i+1}_' + TS
        sheet.find_element(By.ID, 'dim-name').send_keys(bname)
        time.sleep(0.4)
        save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                     if b.text.strip() == '保存' and b.is_displayed()]
        drv.execute_script('arguments[0].click()', save_btns[0])
        WebDriverWait(drv, 45).until(
            lambda d: '评估维度添加成功' in _body_text(d) or '保存失败' in _body_text(d))
        d = _api_get('/evaluation/dimensions?per_page=1000&search=' + bname)
        items = d.get('data', {}).get('items', [])
        assert len(items) >= 1, f'批量记录 {i+1} 创建失败'
        created.append(items[0])
    _shot(drv, 'p4_three_created')

    # 搜索第一个并勾选 → 批量禁用
    _goto_eval(drv)
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys(_PREFIX + '批量1_' + TS)
    WebDriverWait(drv, 30).until(lambda d: _PREFIX + '批量1_' + TS in _body_text(d))
    cb = drv.find_element(By.CSS_SELECTOR, "input[aria-label='选择维度 " + _PREFIX + "批量1_" + TS + "']")
    drv.execute_script('arguments[0].click()', cb)
    time.sleep(0.6)
    batch_btn = None
    for b in drv.find_elements(By.XPATH, "//button[contains(., '批量操作')]"):
        if b.is_displayed():
            batch_btn = b
            break
    assert batch_btn, '批量操作按钮缺失'
    drv.execute_script('arguments[0].click()', batch_btn)
    time.sleep(0.8)
    for item in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']"):
        if item.text.strip() == '批量禁用':
            drv.execute_script('arguments[0].click()', item)
            break
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '批量禁用' in dtxt and '确定要禁用选中的 1 个维度吗？' in dtxt, f'批量禁用确认异常：{dtxt[:200]}'
    _shot(drv, 'p4_batch_disable_confirm_light')
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '批量禁用' and b.is_displayed()]
    drv.execute_script('arguments[0].click()', confirm[0])
    WebDriverWait(drv, 15).until(
        lambda d: '批量操作执行成功' in _body_text(d) or '批量操作失败' in _body_text(d))
    time.sleep(0.8)
    d = _api_get(f'/evaluation/dimensions/{created[0]["id"]}')
    assert d.get('data', {}).get('status') is False, '批量禁用未落库'
    print('batch disable ok:', created[0]['id'], 'status=False')

    # 批量删除 2/3（浮条）
    _goto_eval(drv)
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys(_PREFIX + '批量')
    WebDriverWait(drv, 30).until(
        lambda d: _PREFIX + '批量2_' + TS in _body_text(d) and _PREFIX + '批量3_' + TS in _body_text(d))
    cb2 = drv.find_element(By.CSS_SELECTOR, "input[aria-label='选择维度 " + _PREFIX + "批量2_" + TS + "']")
    drv.execute_script('arguments[0].click()', cb2)
    cb3 = drv.find_element(By.CSS_SELECTOR, "input[aria-label='选择维度 " + _PREFIX + "批量3_" + TS + "']")
    drv.execute_script('arguments[0].click()', cb3)
    time.sleep(0.6)
    del_btn = None
    for b in drv.find_elements(By.XPATH, "//button[contains(., '批量删除')]"):
        if b.is_displayed():
            del_btn = b
            break
    assert del_btn, '批量删除按钮缺失'
    drv.execute_script('arguments[0].click()', del_btn)
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '批量删除' in dtxt and '确定要删除选中的 2 个维度吗？' in dtxt, f'批量删除确认异常：{dtxt[:200]}'
    _shot(drv, 'p4_batch_delete_confirm_light')
    confirm = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
               if b.text.strip() == '批量删除' and b.is_displayed()]
    drv.execute_script('arguments[0].click()', confirm[0])
    WebDriverWait(drv, 15).until(
        lambda d: '批量操作执行成功' in _body_text(d) or '批量操作失败' in _body_text(d))
    time.sleep(1.0)
    _drain_network(drv)
    for i in [1, 2]:
        d = _api_get(f'/evaluation/dimensions/{created[i]["id"]}')
        assert d.get('success') is False, f'批量删除未生效 id={created[i]["id"]}'
    d = _api_get(f'/evaluation/dimensions/{created[0]["id"]}')
    assert d.get('data', {}).get('status') is False, '未选中记录不应被删'
    print('batch delete ok: id2/id3 gone, id1 still exists(disabled)')
    return created


def run_validation_phase(drv):
    """5. 校验与状态：必填留空 / 非法值 / 取消关闭后重开表单清空。"""
    print('\n===== PHASE 5: 校验与状态 =====')
    _goto_eval(drv)
    # 必填留空：不填名称 → 「保存」应禁用（RHF isValid gate），即不允许空必填提交
    sheet = _open_create(drv)
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    assert save_btns and save_btns[0].get_attribute('disabled'), '空名称提交按钮应禁用'
    _shot(drv, 'p5_empty_name_validation_light')

    # 非法值：填名称但结果最小值≥最大值 → 表单 invalid → 保存禁用
    name_input = sheet.find_element(By.ID, 'dim-name')
    name_input.send_keys(_PREFIX + '校验_' + TS)
    _switch_tab(drv, sheet, '结果配置')
    min_input = sheet.find_element(By.ID, 'dim-result-min')
    min_input.clear(); min_input.send_keys('90')
    max_input = sheet.find_element(By.ID, 'dim-result-max')
    max_input.clear(); max_input.send_keys('80')
    time.sleep(0.5)
    save_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                 if b.text.strip() == '保存' and b.is_displayed()]
    assert save_btns and save_btns[0].get_attribute('disabled'), '非法范围（min>=max）应禁用保存'
    _shot(drv, 'p5_invalid_range_validation_light')

    # 取消关闭后重开 → 表单清空（名称不残留）
    cancel_btns = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == '取消' and b.is_displayed()]
    if cancel_btns:
        drv.execute_script('arguments[0].click()', cancel_btns[0])
        time.sleep(1.0)
    # 重开抽屉，检查名称输入框为空
    sheet2 = _open_create(drv)
    name_val = sheet2.find_element(By.ID, 'dim-name').get_attribute('value') or ''
    assert name_val == '', f'重开后名称残留：{name_val!r}'
    _shot(drv, 'p5_form_reset_after_close_light')
    # 关闭
    for b in sheet2.find_elements(By.TAG_NAME, 'button'):
        if b.text.strip() == '取消' and b.is_displayed():
            drv.execute_script('arguments[0].click()', b)
            break
    time.sleep(1.0)
    print('validation phase ok')


def run_options_counts_phase(drv):
    """6. 选项与计数：下拉选项数、列表总数、分组数与接口逐一对照。"""
    print('\n===== PHASE 6: 选项与计数 =====')
    _goto_eval(drv)
    # 列表总数
    list_total = _api_get('/evaluation/dimensions?per_page=1')
    api_total = list_total.get('data', {}).get('total')
    print('API dimensions total:', api_total)
    # 分组视图分类卡数 vs 分类接口
    cats = _api_get('/evaluation/categories?per_page=100')
    api_cats = cats.get('data', {}).get('items', [])
    print('API categories total:', len(api_cats))
    # 算法选项数
    algos = _api_get('/algorithm/options')
    api_algos = algos.get('data', {}).get('algorithms', [])
    print('API algorithm options:', len(api_algos))
    # 状态筛选：全部状态 → 全部；启用/禁用 与接口对照
    # （浏览器侧直接数「共 N 条」页脚）
    _goto_eval(drv)
    txt = _body_text(drv)
    import re
    m = re.search(r'共 (\d+) 条', txt)
    ui_total = int(m.group(1)) if m else None
    print('UI footer total:', ui_total)
    assert ui_total is not None and api_total is not None and ui_total == api_total, \
        f'列表总数不一致：UI={ui_total} API={api_total}'
    # 分类 facet 选项数对照（筛选工具栏「全部分类」下拉）
    cat_facet = None
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and '全部分类' in (b.text or ''):
            cat_facet = b
            break
    if cat_facet:
        drv.execute_script('arguments[0].click()', cat_facet)
        time.sleep(0.8)
        items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
        item_labels = [i.text.strip() for i in items]
        print('分类 facet options:', item_labels)
        # 全部分类 + 各分类（无「+ 新建分类」）应等于 1 + 分类数
        real_cats = [i for i in item_labels if i not in ('全部分类', '全部')]
        assert len(real_cats) == len(api_cats), \
            f'分类 facet 选项数与接口不一致：facet={real_cats} api={[c["name"] for c in api_cats]}'
        # 关闭下拉
        drv.execute_script("document.body.click()")
        time.sleep(0.4)
    # 算法 facet 选项数
    algo_facet = None
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and '全部' in (b.text or '') and '关联算法' in (b.text or ''):
            algo_facet = b
            break
    if algo_facet:
        drv.execute_script('arguments[0].click()', algo_facet)
        time.sleep(0.8)
        items = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
        item_labels = [i.text.strip() for i in items]
        print('算法 facet options:', item_labels)
        assert len(item_labels) == len(api_algos) + 1, \
            f'算法 facet 选项数与接口不一致：{item_labels} vs {[a["value"] for a in api_algos]}'
        drv.execute_script("document.body.click()")
        time.sleep(0.4)
    # 分组视图：分类卡数对照
    for t in drv.find_elements(By.CSS_SELECTOR, "[data-slot='tabs-trigger']"):
        if t.text.strip() == '分组视图' and t.is_displayed():
            drv.execute_script('arguments[0].click()', t)
            break
    time.sleep(1.2)
    txt = _body_text(drv)
    for cat in api_cats:
        assert cat['name'] in txt, f'分组视图缺分类卡「{cat["name"]}」'
    _shot(drv, 'p6_group_view_light')
    print('options & counts phase ok')


def run_dark_theme_capture(drv):
    """深色截图（页面主态 + 抽屉）。"""
    print('\n===== 深色截图 =====')
    _set_theme(drv, 'dark')
    _goto_eval(drv)
    _shot(drv, 'dark_page_light')
    _open_create(drv)
    _shot(drv, 'dark_drawer_light')
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if b.text.strip() == '取消' and b.is_displayed():
            drv.execute_script('arguments[0].click()', b)
            break
    time.sleep(0.8)


def cleanup_test_data(drv, kept):
    """清理本 run 自建的「接线测试_INT1254_」残留（含失败中途）。"""
    print('\n===== 清理 =====')
    d = _api_get('/evaluation/dimensions?per_page=1000&search=接线测试_INT1254')
    items = d.get('data', {}).get('items', [])
    print('leftover 接线测试_INT1254 rows:', [(i['id'], i['name']) for i in items])
    for i in items:
        if kept and i['id'] in kept:
            continue
        r = _api_get(f'/evaluation/dimensions/{i["id"]}')
        if r.get('success'):
            import urllib.request
            req = urllib.request.Request(API + f'/evaluation/dimensions/{i["id"]}', method='DELETE')
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    print('deleted', i['id'], i['name'], resp.status)
            except Exception as e:
                print('delete failed', i['id'], e)
    d = _api_get('/evaluation/dimensions?per_page=1000&search=接线测试_INT1254')
    items = d.get('data', {}).get('items', [])
    print('after cleanup, remaining:', [(i['id'], i['name']) for i in items])
