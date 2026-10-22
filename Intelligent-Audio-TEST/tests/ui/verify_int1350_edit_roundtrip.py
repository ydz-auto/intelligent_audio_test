# -*- coding: utf-8 -*-
"""INT-1350 二轮返工验证：编辑路径输出字段/输入参数回显与保存不清库（真实库栈 5700，React dev 5371）。

复现审计打回场景：
1. 新建维度带输出字段 2 行（score/wer）+ 所需输入默认 2 行（asr_result/asr_ref）
2. 打开编辑抽屉 → API配置 tab → 输出字段代码回显应为 ['score','wer']（修复前恒 ['','']），
   所需输入键名回显应为 ['asr_result','asr_ref']（修复前恒 ['']）
3. 不改任何字段直接「保存」→ toast「评估维度更新成功」
4. GET 详情 → output_fields 仍 ≥2 行（修复前被清空为 0）、required_inputs 仍 ≥2 行

修复点：evaluation.dto.ts toDimension 读侧归一 snake_case→camelCase（param_code→paramCode），
与写侧 toDimensionInputDto 同口径。
"""
import json
import os
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5371')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'tests', 'ui', 'artifacts', 'int1350_dimension_edit')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
NAME = '接线测试_INT1350_edit_roundtrip'


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
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
    except Exception:
        pass
    if extra is not None:
        with open(os.path.join(d, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(extra, f, ensure_ascii=False, indent=1)


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


def _save_and_wait(drv, sheet, success_toast, label):
    """点保存（JS click 避开 base-ui 动画吞点击）；成功以 toast 或抽屉关闭为信号。"""
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
    # toast 未捕获（动画时序 flake）时以抽屉关闭兜底：onOpenChange(false) 仅在保存成功后触发
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='sheet-content']")) == 0)
    print(f'SAVE_OK({label}) sheet_closed (no toast captured)')


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    try:
        _login(drv)
        _save_evidence(drv, '01_login')

        # 清理上次失败 run 遗留同名测试维度
        try:
            leftover = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
            for it in _list_items(leftover):
                if it.get('name') == NAME:
                    _api(drv, 'DELETE', f"/evaluation/dimensions/{it['id']}")
                    print('CLEANUP_LEFT_OVER id=', it['id'])
        except Exception as e:
            print('CLEANUP_SKIP', e)

        # 打开评估维度页 → 新增维度
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 20).until(
            lambda d: '评估维度' in _body_text(d))
        time.sleep(1.5)
        print('PAGE_OK 评估维度 rendered')

        drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
        time.sleep(1.2)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        assert '新增评估维度' in sheet.text, '抽屉标题缺失'
        sheet.find_element(By.ID, 'dim-name').send_keys(NAME)
        time.sleep(0.3)
        _click_tab(sheet, 'API配置')

        # 输出字段默认 1 行 score + 添加字段 1 行 wer
        out_code = _input_values(drv, "input[aria-label^='输出字段代码 ']")
        print('OUTPUT_CODES_CREATE_BEFORE_ADD=', out_code)
        add_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == '添加字段' and b.is_displayed()]
        assert add_btn, '「添加字段」按钮缺失'
        add_btn[0].click()
        time.sleep(0.5)
        out_rows = sheet.find_elements(By.CSS_SELECTOR, "input[aria-label^='输出字段代码 ']")
        assert len(out_rows) >= 2, '「添加字段」未新增行'
        out_rows[1].send_keys('wer')
        time.sleep(0.3)

        # 所需输入默认 2 行 asr_result/asr_ref（核对编辑回显基线）
        in_codes_create = _input_values(drv, "input[aria-label^='输入参数键名 ']")
        print('INPUT_CODES_CREATE=', in_codes_create)
        _save_evidence(drv, '02_create_filled', {
            'output_codes_create': _input_values(drv, "input[aria-label^='输出字段代码 ']"),
            'input_codes_create': in_codes_create,
        })

        # 保存
        _save_and_wait(drv, sheet, '评估维度添加成功', 'create')
        time.sleep(1.2)
        _save_evidence(drv, '03_created_toast')

        # 抓取 PUT/POST 请求体证明 output_fields param_code 上送
        try:
            bodies = []
            for entry in drv.get_log('performance'):
                try:
                    msg = json.loads(entry.get('message', '') or '')
                    inner = msg.get('message', {}) or {}
                    if inner.get('method') == 'Network.requestWillBeSent':
                        req = inner.get('params', {}).get('request', {}) or {}
                        url = req.get('url', '')
                        if '/api/v1/evaluation/dimensions' in url and req.get('method') in ('POST', 'PUT'):
                            bodies.append({'url': url, 'postData': req.get('postData')})
                except Exception:
                    continue
        except Exception as e:
            print('PERF_LOG_ERR', e)
        create_body = None
        for b in bodies:
            if b.get('postData') and 'output_fields' in b['postData'] and b['url'].endswith('/evaluation/dimensions'):
                create_body = b['postData']
                break
        print('PERF_POST_COUNT=', len(bodies))

        # 列表搜名称拿 id + GET 详情核对新建落库
        lst = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
        hits = [it for it in _list_items(lst) if it.get('name') == NAME]
        assert hits, f'列表未找到新建维度 {NAME}'
        dim_id = hits[0]['id']
        print('DIM_ID=', dim_id)

        detail = _unwrap_detail(_api(drv, 'GET', f'/evaluation/dimensions/{dim_id}')) or {}
        of_detail = detail.get('output_fields') or []
        ri_detail = detail.get('required_inputs') or []
        codes_detail = [x.get('param_code') for x in of_detail] if isinstance(of_detail, list) else []
        in_codes_detail = [x.get('param_code') for x in ri_detail] if isinstance(ri_detail, list) else []
        print('DETAIL_AFTER_CREATE output=', codes_detail, 'inputs=', in_codes_detail)
        assert len(of_detail) >= 2 and 'wer' in codes_detail, (
            f'新建落库异常：output_fields={codes_detail}')
        assert len(ri_detail) >= 2, f'新建落库 required_inputs 异常：{in_codes_detail}'
        _save_evidence(drv, '04_detail_after_create', {
            'output_fields_count': len(of_detail),
            'output_codes': codes_detail,
            'required_inputs_count': len(ri_detail),
            'input_codes': in_codes_detail,
            'create_post_body': create_body,
        })

        # ── 编辑路径（核心返工点）──
        drv.get(BASE + '/Evaluation')
        time.sleep(1.5)
        # 新建维度按 sort_order 排序可能在分页外：先搜索名称定位行
        search_box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
        search_box.send_keys(NAME)
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")) > 0)
        time.sleep(0.5)
        edit_btn = drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")
        assert edit_btn, f'编辑按钮缺失：{NAME}'
        edit_btn[0].click()
        time.sleep(1.5)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        assert '编辑评估维度' in sheet.text, '编辑抽屉标题缺失'
        _click_tab(sheet, 'API配置')

        # 等详情反填完成：输出字段代码回显应为 score/wer（修复前恒 ''）
        out_codes_edit = _input_values(drv, "input[aria-label^='输出字段代码 ']")
        in_codes_edit = _input_values(drv, "input[aria-label^='输入参数键名 ']")
        print('EDIT_ECHO output=', out_codes_edit, 'inputs=', in_codes_edit)
        _save_evidence(drv, '05_edit_drawer_before_save', {
            'output_codes_edit': out_codes_edit,
            'input_codes_edit': in_codes_edit,
        })

        assert len(out_codes_edit) >= 2, (
            f'编辑回显输出字段行数异常：{out_codes_edit}（期望 ≥2）')
        assert out_codes_edit[0] == 'score' and 'wer' in out_codes_edit, (
            f'修复未生效：编辑回显输出字段代码 {out_codes_edit}（期望含 score/wer）')
        assert in_codes_edit and in_codes_edit[0] in ('asr_result', 'asr_ref'), (
            f'修复未生效：编辑回显输入参数键名 {in_codes_edit}（期望 asr_result/asr_ref）')

        # 不改任何字段直接「保存」
        _save_and_wait(drv, sheet, '评估维度更新成功', 'edit')
        time.sleep(1.5)
        _save_evidence(drv, '06_edit_saved_toast')

        # 编辑保存后 GET 详情：output_fields/required_inputs 应保留（修复前被清空）
        detail2 = _unwrap_detail(_api(drv, 'GET', f'/evaluation/dimensions/{dim_id}')) or {}
        of2 = detail2.get('output_fields') or []
        ri2 = detail2.get('required_inputs') or []
        codes2 = [x.get('param_code') for x in of2] if isinstance(of2, list) else []
        in_codes2 = [x.get('param_code') for x in ri2] if isinstance(ri2, list) else []
        print('DETAIL_AFTER_EDIT output=', codes2, 'inputs=', in_codes2)
        _save_evidence(drv, '07_detail_after_edit', {
            'output_fields_count_after_edit': len(of2),
            'output_codes_after_edit': codes2,
            'required_inputs_count_after_edit': len(ri2),
            'input_codes_after_edit': in_codes2,
            'detail_before_edit_count': len(of_detail),
        })

        assert len(of2) >= 2, (
            f'返工未生效：编辑保存后 output_fields 被清空为 {len(of2)} 行（期望 ≥2）')
        assert 'wer' in codes2 and 'score' in codes2, f'编辑保存后输出字段丢失：{codes2}'
        assert len(ri2) >= 2, (
            f'返工未生效：编辑保存后 required_inputs 被清空为 {len(ri2)} 行（期望 ≥2）')
        assert in_codes2[0] == 'asr_result', f'编辑保存后输入参数键名丢失：{in_codes2}'

        # 清理：删除自建维度
        rm = _api(drv, 'DELETE', f'/evaluation/dimensions/{dim_id}')
        print('CLEANUP_DELETE_STATUS=', rm['status'])

        print('VERIFY_PASS 编辑路径 output_fields/required_inputs 回显与保存均保留：',
              'output=', codes2, 'inputs=', in_codes2)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
