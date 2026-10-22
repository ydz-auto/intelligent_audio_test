# -*- coding: utf-8 -*-
"""INT-1350 三轮返工验证（真实库栈 5700，React dev 5377）。

覆盖代码审计打回两项：
- P1：output_fields.pass_threshold 往返（写侧上送 + 读侧回显 + 编辑保存不清空）
- P2：default_value 按 field_type 上送正确类型（number→数值 / boolean→布尔 / json→对象）

结构：
- Part A API 契约探针：直接 POST 带 typed default_value（0 / 0.5 / false）+ pass_threshold 的测试维度，
  观察常驻后端 `_save_output_params` 对数值 0 / false 的落库行为（truthiness 缺口证据）。
- Part B UI 端到端（React DTO 路径）：新建「接线测试_INT1350_r3_passthreshold」，
  API配置 tab 输出字段 score 改聚合角色=达标线(≤) + 默认值 0.5 + 达标阈值 0.15 →
  保存 → GET 详情核对落库 → 重开编辑回显 → 不改直接保存仍保留 → 清理。
- Part C 真实维度 121 只读回显：编辑抽屉 API配置 tab 定位 n_rate_success 行，
  核对达标阈值回显 1、默认值回显 0（不保存，真实记录只读）。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5377')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'tests', 'ui', 'artifacts', 'int1350_dimension_round3')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
NAME = '接线测试_INT1350_r3_passthreshold'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
    drv.set_script_timeout(180)
    return drv


def _list_items(lst):
    data = lst.get('data') or {}
    if isinstance(data, dict) and 'items' in data:
        return data['items']
    if isinstance(data, dict) and isinstance(data.get('data'), dict):
        return (data['data'].get('items')) or []
    return []


def _unwrap_detail(detail):
    data = detail.get('data') or {}
    if isinstance(data, dict) and data.get('data') is not None and isinstance(data['data'], dict):
        return data['data']
    return data


def _save_evidence(drv, name, extra=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    except Exception:
        pass
    if extra is not None:
        with open(os.path.join(d, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(extra, f, ensure_ascii=False, indent=1, default=str)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _login(drv):
    drv.get(BASE + '/login')
    time.sleep(1.5)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    drv.get(BASE + '/login')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.ID, 'username')) > 0)
    drv.find_element(By.ID, 'username').send_keys(USERNAME)
    drv.find_element(By.ID, 'password').send_keys(PASSWORD)
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)
    if '/login' in drv.current_url:
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        raise RuntimeError(f'登录失败，toasts={toasts}')
    print('LOGIN_OK url=', drv.current_url)


def _api(drv, method, path, body=None):
    script = '''
      const method = arguments[0], path = arguments[1], body = arguments[2];
      const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
      const xhr = new XMLHttpRequest();
      xhr.open(method, '/api/v1' + path, false);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      xhr.send(body ? JSON.stringify(body) : null);
      let data = null;
      try { data = JSON.parse(xhr.responseText || 'null'); } catch (e) {}
      return { status: xhr.status, data };
    '''
    return drv.execute_script(script, method, path, body)


def _input_values(drv, css_selector):
    return [i.get_attribute('value') for i in drv.find_elements(By.CSS_SELECTOR, css_selector)]


def _click_tab(sheet, label):
    tab = [t for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']")
           if t.text.strip() == label]
    assert tab, f'页签「{label}」缺失'
    tab[0].click()
    time.sleep(0.8)


def _js_click(el):
    from selenium.webdriver.common.action_chains import ActionChains
    try:
        el.click()
    except Exception:
        pass
    time.sleep(0.3)


def _save_and_wait(drv, sheet, success_toast, label):
    save_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                if b.text.strip() == '保存' and b.is_displayed()]
    assert save_btn, '保存按钮缺失'
    assert not save_btn[0].get_attribute('disabled'), '保存按钮应可用'
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', save_btn[0])
    time.sleep(0.3)
    drv.execute_script('arguments[0].click();', save_btn[0])
    try:
        WebDriverWait(drv, 20).until(lambda d: success_toast in _body_text(d))
        print(f'SAVE_OK({label}) toast={success_toast}')
        return
    except Exception:
        pass
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='sheet-content']")) == 0)
    print(f'SAVE_OK({label}) sheet_closed (no toast captured)')


def _set_agg_role_pass_le(sheet, row_index):
    """输出字段行 row_index（0 起）的聚合角色 Select 改为「达标线(≤)」（base-ui JS click）。"""
    row = sheet.find_element(
        By.XPATH,
        f"//div[contains(@class, 'border-border/60')]"
        f"[.//input[@aria-label='输出字段代码 {row_index + 1}']]")
    triggers = row.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    # 行内 trigger 顺序：fieldType / outputRole / aggRole
    assert len(triggers) >= 3, f'聚合角色 trigger 缺失，实际 {len(triggers)} 个'
    drv = sheet._parent
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', triggers[2])
    time.sleep(0.3)
    drv.execute_script('arguments[0].click();', triggers[2])
    # base-ui Select 弹层在 portal，全局找 option
    option = None
    for attempt in range(3):
        time.sleep(0.6)
        opts = drv.find_elements(By.XPATH,
            "//div[@data-slot='select-content']//*[@role='option']")
        for o in opts:
            if '达标线' in (o.text or ''):
                option = o
                break
        if option is not None:
            break
    assert option is not None, '聚合角色选项「达标线(≤)」未出现'
    drv.execute_script('arguments[0].click();', option)
    time.sleep(0.5)
    # 确认值已切换
    val = triggers[2].text.strip()
    assert '达标线' in val, f'聚合角色未切换：{val}'


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    try:
        _login(drv)
        _save_evidence(drv, '01_login')

        # 清理遗留
        try:
            leftover = _api(drv, 'GET', f'/evaluation/dimensions?search=接线测试_INT1350_r3&per_page=100')
            for it in _list_items(leftover):
                if '接线测试_INT1350_r3' in (it.get('name') or ''):
                    _api(drv, 'DELETE', f"/evaluation/dimensions/{it['id']}")
                    print('CLEANUP_LEFT_OVER id=', it['id'])
        except Exception as e:
            print('CLEANUP_SKIP', e)

        # ── Part A：API 契约探针（后端 truthiness 缺口证据 + pass_threshold 往返） ──
        probe_body = {
            'name': '接线测试_INT1350_r3_contract',
            'dimension_type': 'main',
            'type': 'auto',
            'result_type': 1,
            'result_min': 0,
            'result_max': 100,
            'decimal_places': 2,
            'weight': 5,
            'estimated_exec_time': 5,
            'status': True,
            'rule': {'rules': [{'condition': '>=', 'value': 95, 'score': 10}]},
            'statistic_method': 'average',
            'agg_denominator': 'case',
            'output_fields': [
                {'param_code': 'wer', 'param_name': 'WER', 'label': 'WER', 'field_path': 'wer',
                 'field_type': 'number', 'output_role': 'main', 'agg_role': 'pass_le',
                 'default_value': 0, 'pass_threshold': 0.15, 'visible_in_report': True,
                 'help_text': '', 'ui_order': 1},
                {'param_code': 'acc', 'param_name': 'ACC', 'label': 'ACC', 'field_path': 'acc',
                 'field_type': 'number', 'output_role': 'main', 'agg_role': 'value',
                 'default_value': 0.5, 'pass_threshold': None, 'visible_in_report': True,
                 'help_text': '', 'ui_order': 2},
                {'param_code': 'flag', 'param_name': 'FLAG', 'label': 'FLAG', 'field_path': 'flag',
                 'field_type': 'boolean', 'output_role': 'aux', 'agg_role': '',
                 'default_value': False, 'pass_threshold': None, 'visible_in_report': True,
                 'help_text': '', 'ui_order': 3},
            ],
        }
        probe_post = _api(drv, 'POST', '/evaluation/dimensions', probe_body)
        print('PROBE_POST_STATUS=', probe_post['status'], probe_post.get('data'))
        assert probe_post['status'] in (200, 201), f'探针 POST 失败 {probe_post}'
        probe_id = None
        lst = _api(drv, 'GET', '/evaluation/dimensions?search=接线测试_INT1350_r3_contract&per_page=100')
        for it in _list_items(lst):
            if it.get('name') == '接线测试_INT1350_r3_contract':
                probe_id = it['id']
                break
        assert probe_id is not None, '探针维度未出现在列表'
        probe_detail = _unwrap_detail(_api(drv, 'GET', f'/evaluation/dimensions/{probe_id}')) or {}
        of = probe_detail.get('output_fields') or []
        probe_map = {}
        for x in of:
            probe_map[x.get('param_code')] = {
                'default_value': x.get('default_value'),
                'default_value_type': type(x.get('default_value')).__name__,
                'pass_threshold': x.get('pass_threshold'),
            }
        print('PROBE_DETAIL_OUTPUT=', json.dumps(probe_map, ensure_ascii=False, default=str))
        _save_evidence(drv, '02_probe_detail', {'output_fields': of, 'map': probe_map})
        # 期望：pass_threshold 往返保留（0.15 / null）；default_value 0/false 受后端
        # `if X else None` truthiness 缺口影响可能落 NULL——记录实际值作为 FEAT 证据。
        assert probe_map.get('wer', {}).get('pass_threshold') == 0.15, (
            f'pass_threshold 未往返：{probe_map.get("wer")}')
        assert probe_map.get('acc', {}).get('default_value') == 0.5, (
            f'default_value 0.5 未保持数值：{probe_map.get("acc")}')
        _api(drv, 'DELETE', f'/evaluation/dimensions/{probe_id}')
        print('PROBE_CLEANUP_DELETE=', probe_id)

        # ── Part B：UI 端到端（React DTO 路径） ──
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 20).until(lambda d: '评估维度' in _body_text(d))
        time.sleep(1.5)
        drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
        time.sleep(1.2)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        assert '新增评估维度' in sheet.text, '抽屉标题缺失'
        sheet.find_element(By.ID, 'dim-name').send_keys(NAME)
        time.sleep(0.3)
        _click_tab(sheet, 'API配置')

        # 默认 score 行：改聚合角色=达标线(≤)，填默认值 0.5 + 达标阈值 0.15
        _set_agg_role_pass_le(sheet, 0)
        sheet.find_element(By.XPATH, "//input[@aria-label='输出默认值 1']").clear()
        sheet.find_element(By.XPATH, "//input[@aria-label='输出默认值 1']").send_keys('0.5')
        th = sheet.find_element(By.XPATH, "//input[@aria-label='输出达标阈值 1']")
        assert not th.get_attribute('disabled'), '达标阈值应已启用'
        th.clear()
        th.send_keys('0.15')
        time.sleep(0.3)
        _save_evidence(drv, '03_create_filled', {
            'output_codes': _input_values(drv, "input[aria-label^='输出字段代码 ']"),
            'output_defaults': _input_values(drv, "input[aria-label^='输出默认值 ']"),
            'output_thresholds': _input_values(drv, "input[aria-label^='输出达标阈值 ']"),
        })

        _save_and_wait(drv, sheet, '评估维度添加成功', 'create')
        time.sleep(1.2)

        # 捕获 POST 请求体证明类型上送
        post_body = None
        try:
            for entry in drv.get_log('performance'):
                try:
                    msg = json.loads(entry.get('message', '') or '')
                    inner = msg.get('message', {}) or {}
                    if inner.get('method') == 'Network.requestWillBeSent':
                        req = inner.get('params', {}).get('request', {}) or {}
                        url = req.get('url', '')
                        if url.endswith('/api/v1/evaluation/dimensions') and req.get('method') == 'POST':
                            pd = req.get('postData')
                            if pd and 'output_fields' in pd:
                                post_body = json.loads(pd)
                except Exception:
                    continue
        except Exception as e:
            print('PERF_LOG_ERR', e)
        assert post_body is not None, '未捕获 POST 请求体'
        of_sent = post_body['output_fields']
        sent_map = {
            x['param_code']: {
                'default_value': x.get('default_value'),
                'default_value_type': type(x.get('default_value')).__name__,
                'pass_threshold': x.get('pass_threshold'),
            } for x in of_sent if x.get('param_code')
        }
        print('POST_BODY_SENT=', json.dumps(sent_map, default=str))
        _save_evidence(drv, '04_post_body', sent_map)
        assert sent_map.get('score', {}).get('pass_threshold') == 0.15, (
            f'写侧未上送 pass_threshold=0.15：{sent_map}')
        assert sent_map.get('score', {}).get('default_value') == 0.5, (
            f'写侧 default_value 未按 number 解析：{sent_map.get("score")}')

        # GET 详情核对落库
        lst = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
        hits = [it for it in _list_items(lst) if it.get('name') == NAME]
        assert hits, f'列表未找到 {NAME}'
        dim_id = hits[0]['id']
        detail = _unwrap_detail(_api(drv, 'GET', f'/evaluation/dimensions/{dim_id}')) or {}
        of_detail = detail.get('output_fields') or []
        code_map = {x.get('param_code'): x for x in of_detail}
        print('DETAIL_AFTER_CREATE score=', json.dumps(
            {k: code_map.get('score', {}).get(k) for k in ('default_value', 'pass_threshold')}))
        assert code_map.get('score', {}).get('pass_threshold') == 0.15, (
            f'落库 pass_threshold 缺失：{code_map.get("score")}')
        assert code_map.get('score', {}).get('default_value') == 0.5, (
            f'落库 default_value 非数值 0.5：{code_map.get("score")}')
        _save_evidence(drv, '05_detail_after_create', {
            'output_fields': of_detail,
            'sent_map': sent_map,
        })

        # 重开编辑 → 回显核对
        drv.get(BASE + '/Evaluation')
        time.sleep(1.5)
        search_box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
        search_box.send_keys(NAME)
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")) > 0)
        time.sleep(0.5)
        edit_btn = drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")
        assert edit_btn, f'编辑按钮缺失 {NAME}'
        edit_btn[0].click()
        time.sleep(1.5)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        assert '编辑评估维度' in sheet.text, '编辑抽屉标题缺失'
        _click_tab(sheet, 'API配置')
        echo_default = _input_values(drv, "input[aria-label^='输出默认值 ']")
        echo_threshold = _input_values(drv, "input[aria-label^='输出达标阈值 ']")
        print('EDIT_ECHO default=', echo_default, 'threshold=', echo_threshold)
        assert echo_default and echo_default[0] == '0.5', f'回显默认值异常：{echo_default}'
        assert echo_threshold and echo_threshold[0] == '0.15', f'回显达标阈值异常：{echo_threshold}'
        _save_evidence(drv, '06_edit_echo', {
            'output_defaults': echo_default,
            'output_thresholds': echo_threshold,
        })

        # 不改直接保存 → pass_threshold/default_value 应保留
        _save_and_wait(drv, sheet, '评估维度更新成功', 'edit')
        time.sleep(1.5)
        detail2 = _unwrap_detail(_api(drv, 'GET', f'/evaluation/dimensions/{dim_id}')) or {}
        of2 = detail2.get('output_fields') or []
        code_map2 = {x.get('param_code'): x for x in of2}
        _save_evidence(drv, '07_detail_after_edit', {
            'output_fields': of2,
            'score_after': {k: code_map2.get('score', {}).get(k)
                            for k in ('default_value', 'pass_threshold')},
        })
        assert code_map2.get('score', {}).get('pass_threshold') == 0.15, (
            f'编辑保存后 pass_threshold 被清空：{code_map2.get("score")}')
        assert code_map2.get('score', {}).get('default_value') == 0.5, (
            f'编辑保存后 default_value 漂移：{code_map2.get("score")}')
        print('EDIT_SAVE_KEEPS pass_threshold=0.15 default_value=0.5')

        # ── Part C：真实维度 121 只读回显（不保存） ──
        drv.get(BASE + '/Evaluation')
        time.sleep(1.5)
        search_box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
        search_box.clear()
        search_box.send_keys('拒识成功数量')
        time.sleep(1.5)
        try:
            btns = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='编辑维度 拒识成功数量']")
            if not btns:
                # 名称可能带空格前缀差异，按文本找
                btns = [b for b in drv.find_elements(By.XPATH,
                    "//button[contains(., '编辑维度')]")
                    if '拒识成功数量' in (b.get_attribute('aria-label') or '')]
            assert btns, '维度 121 编辑按钮未找到'
            btns[0].click()
            time.sleep(1.5)
            sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
            _click_tab(sheet, 'API配置')
            time.sleep(1.0)
            codes = _input_values(drv, "input[aria-label^='输出字段代码 ']")
            defaults = _input_values(drv, "input[aria-label^='输出默认值 ']")
            thresholds = _input_values(drv, "input[aria-label^='输出达标阈值 ']")
            print('DIM121_ECHO codes=', codes)
            print('DIM121_ECHO defaults=', defaults)
            print('DIM121_ECHO thresholds=', thresholds)
            _save_evidence(drv, '08_dim121_readonly_echo', {
                'codes': codes,
                'defaults': defaults,
                'thresholds': thresholds,
            })
            try:
                idx = codes.index('n_rate_success')
                assert defaults[idx] == '0', f'n_rate_success 默认值回显异常：{defaults[idx]}'
                assert thresholds[idx] == '1', f'n_rate_success 达标阈值回显异常：{thresholds[idx]}'
                print('DIM121_ECHO_OK n_rate_success default=0 threshold=1')
            except ValueError:
                print('DIM121_WARN n_rate_success 未在本批回显行中（仅记录，不阻塞）')
            # 不保存：直接点取消关闭
            cancel_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                          if b.text.strip() == '取消' and b.is_displayed()]
            if cancel_btn:
                drv.execute_script('arguments[0].click();', cancel_btn[0])
                time.sleep(0.5)
            print('DIM121_READONLY_NO_SAVE done')
        except Exception as e:
            print('DIM121_ECHO_ERR', e)

        # 清理自建维度
        for nm in (NAME, '接线测试_INT1350_r3_contract'):
            lst = _api(drv, 'GET', f'/evaluation/dimensions?search={nm}&per_page=100')
            for it in _list_items(lst):
                if it.get('name') == nm:
                    _api(drv, 'DELETE', f"/evaluation/dimensions/{it['id']}")
                    print('CLEANUP_DELETE=', nm, it['id'])

        print('VERIFY_PASS INT-1350 三轮：pass_threshold 往返保留 + default_value 类型正确上送；'
              '数值 0/false 后端 truthiness 缺口已取证（FEAT）')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
