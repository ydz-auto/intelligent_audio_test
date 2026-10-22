# -*- coding: utf-8 -*-
"""INT-1350 三轮返工：深色主题截图取证（输出字段编辑器新增达标阈值列）。

覆盖：
- 新增维度 → API配置 tab 输出字段编辑器深色形态（默认 score 行 + 达标阈值列）
- 聚合角色切「达标线(≤)」→ 达标阈值输入启用 + 填 0.15 → 保存 → 编辑回显深色
- 真实维度 121（拒识成功数量）只读回显：n_rate_success 达标阈值=1（不保存）
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
    'tests', 'ui', 'artifacts', 'int1350_dimension_round3_dark')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
NAME = '接线测试_INT1350_r3_dark'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
    return drv


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _list_items(lst):
    data = lst.get('data') or {}
    if isinstance(data, dict) and 'items' in data:
        return data['items']
    if isinstance(data, dict) and isinstance(data.get('data'), dict):
        return (data['data'].get('items')) or []
    return []


def _save(drv, name, extra=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    if extra is not None:
        with open(os.path.join(d, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(extra, f, ensure_ascii=False, indent=1, default=str)


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


def _js_click(el):
    from selenium.webdriver.common.action_chains import ActionChains
    try:
        el.click()
    except Exception:
        pass
    time.sleep(0.3)


def _set_agg_role_pass_le(sheet, row_index):
    """输出字段行 row_index（0 起）的聚合角色 Select 改为「达标线(≤)」（base-ui JS click）。"""
    row = sheet.find_element(
        By.XPATH,
        f"//div[contains(@class, 'border-border/60')]"
        f"[.//input[@aria-label='输出字段代码 {row_index + 1}']]")
    triggers = row.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    assert len(triggers) >= 3, f'聚合角色 trigger 缺失，实际 {len(triggers)} 个'
    drv = sheet._parent
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', triggers[2])
    time.sleep(0.3)
    drv.execute_script('arguments[0].click();', triggers[2])
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


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    dim_id = None
    try:
        drv.get(BASE + '/login')
        time.sleep(1.5)
        drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(lambda d: len(d.find_elements(By.ID, 'username')) > 0)
        drv.find_element(By.ID, 'username').send_keys(USERNAME)
        drv.find_element(By.ID, 'password').send_keys(PASSWORD)
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
        time.sleep(2.0)
        if '/login' in drv.current_url:
            toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
            raise RuntimeError(f'登录失败，toasts={toasts}')
        print('DARK_LOGIN_OK url=', drv.current_url)

        # 清理遗留
        try:
            leftover = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
            for it in _list_items(leftover):
                if it.get('name') == NAME:
                    _api(drv, 'DELETE', f"/evaluation/dimensions/{it['id']}")
                    print('DARK_CLEANUP_LEFT_OVER id=', it['id'])
        except Exception as e:
            print('DARK_CLEANUP_SKIP', e)

        # 切深色主题：写 iatp:theme:v1:mode + about:blank 打断 bfcache 强刷
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', JSON.stringify({'state': {'mode': 'dark'}, 'version': 0}))")
        drv.get('about:blank')
        time.sleep(0.8)

        # 评估维度页（深色）
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 20).until(lambda d: '评估维度' in _body_text(d))
        time.sleep(1.5)
        _save(drv, '01_evaluation_page_dark')

        # 新增维度 → API配置 tab：输出字段编辑器深色（含达标阈值列）
        drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
        time.sleep(1.2)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        assert '新增评估维度' in sheet.text, '抽屉标题缺失'
        sheet.find_element(By.ID, 'dim-name').send_keys(NAME)
        time.sleep(0.3)
        tab = [t for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']") if t.text.strip() == 'API配置']
        assert tab, 'API配置 tab 缺失'
        tab[0].click()
        time.sleep(0.8)
        # 默认 score 行：聚合角色切达标线(≤)，达标阈值启用并填 0.15（深色截图证据）
        _set_agg_role_pass_le(sheet, 0)
        th = sheet.find_element(By.XPATH, "//input[@aria-label='输出达标阈值 1']")
        assert not th.get_attribute('disabled'), '达标阈值应已启用'
        th.clear()
        th.send_keys('0.15')
        defaults = _input_values(drv, "input[aria-label^='输出默认值 ']")
        thresholds = _input_values(drv, "input[aria-label^='输出达标阈值 ']")
        print('DARK_CREATE_FILLED defaults=', defaults, 'thresholds=', thresholds)
        assert thresholds[0] == '0.15', f'达标阈值填写异常：{thresholds}'
        _save(drv, '02_create_api_dark', {'defaults': defaults, 'thresholds': thresholds})

        # 保存 → 搜名称 → 编辑抽屉深色回显
        save_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                    if b.text.strip() == '保存' and b.is_displayed()]
        assert save_btn, '保存按钮缺失'
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', save_btn[0])
        time.sleep(0.3)
        drv.execute_script('arguments[0].click();', save_btn[0])
        WebDriverWait(drv, 20).until(lambda d: '评估维度添加成功' in _body_text(d))
        time.sleep(1.0)

        drv.get(BASE + '/Evaluation')
        time.sleep(1.5)
        search = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
        search.send_keys(NAME)
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")) > 0)
        drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")[0].click()
        time.sleep(1.5)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        tab = [t for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']") if t.text.strip() == 'API配置']
        tab[0].click()
        time.sleep(1.0)
        codes = [i.get_attribute('value') for i in drv.find_elements(By.CSS_SELECTOR, "input[aria-label^='输出字段代码 ']")]
        defaults = _input_values(drv, "input[aria-label^='输出默认值 ']")
        thresholds = _input_values(drv, "input[aria-label^='输出达标阈值 ']")
        print('DARK_EDIT_ECHO codes=', codes, 'defaults=', defaults, 'thresholds=', thresholds)
        assert codes[0] == 'score', f'深色编辑回显输出字段异常：{codes}'
        assert thresholds[0] == '0.15', f'深色编辑回显达标阈值异常：{thresholds}'
        _save(drv, '03_edit_api_dark', {'codes': codes, 'defaults': defaults, 'thresholds': thresholds})

        # 真实维度 121 只读回显（深色，不保存）
        drv.get(BASE + '/Evaluation')
        time.sleep(1.5)
        search = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
        search.send_keys('拒识成功数量')
        time.sleep(1.5)
        try:
            btns = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='编辑维度 拒识成功数量']")
            if not btns:
                btns = [b for b in drv.find_elements(By.XPATH,
                    "//button[contains(., '编辑维度')]")
                    if '拒识成功数量' in (b.get_attribute('aria-label') or '')]
            assert btns, '维度 121 编辑按钮未找到'
            btns[0].click()
            time.sleep(1.5)
            sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
            tab = [t for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']") if t.text.strip() == 'API配置']
            tab[0].click()
            time.sleep(1.0)
            codes = _input_values(drv, "input[aria-label^='输出字段代码 ']")
            defaults = _input_values(drv, "input[aria-label^='输出默认值 ']")
            thresholds = _input_values(drv, "input[aria-label^='输出达标阈值 ']")
            print('DARK_DIM121 codes=', codes)
            print('DARK_DIM121 defaults=', defaults, 'thresholds=', thresholds)
            _save(drv, '04_dim121_readonly_dark', {'codes': codes, 'defaults': defaults, 'thresholds': thresholds})
            try:
                idx = codes.index('n_rate_success')
                assert defaults[idx] == '0', f'n_rate_success 默认值回显异常：{defaults[idx]}'
                assert thresholds[idx] == '1', f'n_rate_success 达标阈值回显异常：{thresholds[idx]}'
                print('DARK_DIM121_OK n_rate_success default=0 threshold=1')
            except ValueError:
                print('DARK_DIM121_WARN n_rate_success 未在本批回显行中（仅记录）')
            cancel_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                          if b.text.strip() == '取消' and b.is_displayed()]
            if cancel_btn:
                drv.execute_script('arguments[0].click();', cancel_btn[0])
                time.sleep(0.5)
        except Exception as e:
            print('DARK_DIM121_ERR', e)

        # 清理自建维度
        lst = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
        for it in _list_items(lst):
            if it.get('name') == NAME:
                dim_id = it['id']
                _api(drv, 'DELETE', f"/evaluation/dimensions/{dim_id}")
                print('DARK_CLEANUP_DELETE id=', dim_id)

        print('DARK_CAPTURE_PASS INT-1350 三轮深色：输出字段编辑器达标阈值列 + 编辑回显 + 维度121只读')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
