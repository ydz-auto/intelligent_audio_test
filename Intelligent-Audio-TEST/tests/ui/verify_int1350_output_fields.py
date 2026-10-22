# -*- coding: utf-8 -*-
"""INT-1350 输出字段保存不落库修复验证（真实库栈 5700，React dev 5371）。

流程：
1. 登录 接线测试_admin（AUTH_MODE=dev 表单登录，走前端加密链路）
2. 打开 /Evaluation → 新增维度 → 名称「接线测试_INT1350_」
3. API配置 tab → 输出字段配置默认 1 行（score），「添加字段」加 1 行填 wer
4. 保存 → toast「评估维度添加成功」
5. 用 localStorage token 直连网关 GET 详情 → 断言 output_fields ≥ 2 行
   且 param_code 含 wer；并抓 POST 请求体证明 param_code 上送
"""
import json
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5371')
API = os.environ.get('REAL_STACK_API', 'http://127.0.0.1:5700')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'tests', 'ui', 'artifacts', 'int1350_dimension')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
NAME = '接线测试_INT1350_output_fields'


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
    """网关信封 {code, data:{items}} 兼容两种嵌套提取 items。"""
    data = lst.get('data') or {}
    if isinstance(data, dict) and 'items' in data:
        return data['items']
    if isinstance(data, dict) and isinstance(data.get('data'), dict):
        return (data['data'].get('items')) or []
    return []


def _unwrap_detail(detail):
    """网关信封兼容提取维度详情对象（data 可能再包一层 data）。"""
    data = detail.get('data') or {}
    if isinstance(data, dict) and data.get('data') is not None and isinstance(data['data'], dict):
        return data['data']
    return data


def _save_evidence(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
    except Exception:
        pass


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


def _get_token(drv):
    return drv.execute_script('return window.localStorage.getItem("iatp:auth:token:v1") || ""')


def _api(drv, method, path, body=None):
    """在页面上下文内同步 XHR 直达真实网关（同源代理走 5700）。返回 (status, data)。"""
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


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    try:
        _login(drv)
        _save_evidence(drv, '01_login')

        # 清理上次失败 run 遗留的同名测试维度（写数据纪律：只留本 run 自建、结束前删）
        token = _get_token(drv)
        if not token:
            raise RuntimeError('token 为空')
        try:
            leftover = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
            for it in _list_items(leftover):
                if it.get('name') == NAME:
                    _api(drv, 'DELETE', f"/evaluation/dimensions/{it['id']}")
                    print('CLEANUP_LEFT_OVER id=', it['id'])
        except Exception as e:
            print('CLEANUP_SKIP', e)

        # 打开评估维度页
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 20).until(
            lambda d: '评估维度' in _body_text(d))
        time.sleep(1.5)
        print('PAGE_OK 评估维度 rendered')
        _save_evidence(drv, '02_evaluation_page')

        # 新增维度
        drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
        time.sleep(1.2)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        stxt = sheet.text
        assert '新增评估维度' in stxt, f'抽屉标题缺失：{stxt[:150]}'
        # 名称
        sheet.find_element(By.ID, 'dim-name').send_keys(NAME)
        time.sleep(0.3)

        # 切到 API配置 tab
        api_tab = [t for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']")
                   if t.text.strip() == 'API配置']
        assert api_tab, 'API配置 tab 缺失'
        api_tab[0].click()
        time.sleep(0.8)
        print('API_TAB_OK')

        # 输出字段默认应有 1 行（score）；再「添加字段」加 1 行
        out_rows = sheet.find_elements(By.CSS_SELECTOR, "input[aria-label^='输出字段代码 ']")
        print('OUTPUT_ROWS_BEFORE=', len(out_rows))
        assert len(out_rows) >= 1, '输出字段默认行缺失'
        add_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == '添加字段' and b.is_displayed()]
        assert add_btn, '「添加字段」按钮缺失'
        add_btn[0].click()
        time.sleep(0.5)
        out_rows = sheet.find_elements(By.CSS_SELECTOR, "input[aria-label^='输出字段代码 ']")
        print('OUTPUT_ROWS_AFTER_ADD=', len(out_rows))
        assert len(out_rows) >= 2, '「添加字段」未新增行'

        # 第二行字段代码填 wer（第一行默认 score 不动）
        out_rows[1].send_keys('wer')
        time.sleep(0.3)
        _save_evidence(drv, '03_output_fields_filled')

        # 保存
        save_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                    if b.text.strip() == '保存' and b.is_displayed()]
        assert save_btn and not save_btn[0].get_attribute('disabled'), '保存按钮应可用'
        save_btn[0].click()
        WebDriverWait(drv, 15).until(
            lambda d: '评估维度添加成功' in _body_text(d))
        time.sleep(1.0)
        print('SAVE_OK toast=评估维度添加成功')
        _save_evidence(drv, '04_saved_toast')

        # 抓取 performance log 中 POST /evaluation/dimensions 请求体
        post_bodies = []
        try:
            for entry in drv.get_log('performance'):
                try:
                    msg = json.loads(entry.get('message', '') or '')
                    inner = msg.get('message', {}) or {}
                    method = inner.get('method', '')
                    params = inner.get('params', {}) or {}
                    if method == 'Network.requestWillBeSent':
                        req = params.get('request', {}) or {}
                        url = req.get('url', '')
                        if '/api/v1/evaluation/dimensions' in url and req.get('method') == 'POST':
                            post_bodies.append({
                                'url': url,
                                'postData': req.get('postData'),
                            })
                except Exception:
                    continue
        except Exception as e:
            print('PERF_LOG_ERR', e)
        print('POST_BODIES_COUNT=', len(post_bodies))
        with open(os.path.join(ARTIFACTS, '04_saved_toast', 'post_bodies.json'), 'w', encoding='utf-8') as f:
            json.dump(post_bodies, f, ensure_ascii=False, indent=1)
        # 断言请求体 output_fields 第二行 param_code=wer（证明 wire 修正）
        found_body = None
        for pb in post_bodies:
            if pb.get('postData') and 'output_fields' in pb['postData']:
                found_body = pb['postData']
                break
        if found_body is None:
            print('WARN: 未捕获 output_fields 请求体，POST_BODIES=', json.dumps(post_bodies, ensure_ascii=False)[:2000])
        else:
            body_obj = json.loads(found_body)
            of = body_obj.get('output_fields', [])
            codes = [x.get('param_code') for x in of]
            print('POST_BODY_OUTPUT_FIELD_CODES=', codes)
            with open(os.path.join(ARTIFACTS, '04_saved_toast', 'post_body_output_fields.json'), 'w', encoding='utf-8') as f:
                json.dump(body_obj, f, ensure_ascii=False, indent=1)
            assert len(of) >= 2, f'请求体 output_fields 不足 2 行：{codes}'
            assert 'wer' in codes, f'请求体 output_fields 缺 wer：{codes}'

        # 用 token 直接 GET 详情核对落库
        time.sleep(1.0)
        # 先列表搜名称拿 id
        lst = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
        print('LIST_STATUS=', lst['status'])
        items = _list_items(lst)
        hits = [it for it in items if it.get('name') == NAME]
        print('LIST_HITS=', json.dumps([{'id': h.get('id'), 'name': h.get('name')} for h in hits], ensure_ascii=False))
        if not hits:
            _save_evidence(drv, '05_list_no_hit')
            raise RuntimeError(f'列表未找到新建维度 {NAME}；LIST=' + json.dumps(lst, ensure_ascii=False)[:1000])
        dim_id = hits[0]['id']
        print('DIM_ID=', dim_id)

        detail = _api(drv, 'GET', f'/evaluation/dimensions/{dim_id}')
        print('DETAIL_STATUS=', detail['status'])
        detail_data = _unwrap_detail(detail) or {}
        of_detail = detail_data.get('output_fields') or []
        codes_detail = [x.get('param_code') for x in of_detail] if isinstance(of_detail, list) else []
        print('DETAIL_OUTPUT_FIELD_COUNT=', len(of_detail), 'CODES=', codes_detail)
        with open(os.path.join(ARTIFACTS, '05_detail_check.json'), 'w', encoding='utf-8') as f:
            json.dump({
                'id': dim_id,
                'name': detail_data.get('name'),
                'output_fields_count': len(of_detail),
                'output_fields': of_detail,
                'required_inputs_count': len(detail_data.get('required_inputs') or []),
            }, f, ensure_ascii=False, indent=1)

        # 清理：删除自建维度
        rm = _api(drv, 'DELETE', f'/evaluation/dimensions/{dim_id}')
        print('CLEANUP_DELETE_STATUS=', rm['status'])

        assert len(of_detail) >= 2, (
            f'修复未生效：GET 详情 output_fields 仅 {len(of_detail)} 行（期望 ≥2）')
        assert 'wer' in codes_detail, f'输出字段缺 wer：{codes_detail}'
        print('VERIFY_PASS output_fields persisted =', codes_detail)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
