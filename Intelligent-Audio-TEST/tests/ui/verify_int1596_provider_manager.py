# -*- coding: utf-8 -*-
"""INT-1596 验收：灵犀Agent「LLM 供应商管理」弹窗两条 P2 缺陷复测。

覆盖：
- 缺陷 1：模型列表手动输入逐字符丢字（key 含输入值导致整行重建）
- 缺陷 2：校验红字在字段已填合法值后不消失
- 回归：保存 → 列表「已配置 Key」→ 编辑回填 → 切换器模型列可选 → 删除确认 → localStorage 清空
- 浅色 / 深色截图 + Network（performance log）+ 控制台 SEVERE

前端：本 worktree dev server（含本卡修复，docker 15173 镜像未含）127.0.0.1:5397
后端：docker 真实库栈网关 127.0.0.1:15000（AUTH_MODE=off，库 intelligent_audio_test）
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5397')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1596')
os.makedirs(ART, exist_ok=True)

PROVIDER_KEYS = 'iatp:ai-chat:v1:providers'
THEME_KEY = 'iatp:theme:v1:mode'
PROVIDER_NAME = '接线测试_验收供应商'
BASE_URL = 'https://api.example.com/v1'
API_KEY = 'sk-int1596-verify'
MODEL_A = 'audit-model-a'
MODEL_B = 'audit-model-b'

RESULT = {}
FAILS = []


def ok(name, cond, detail=''):
    RESULT[name] = {'pass': bool(cond), 'detail': detail}
    print(('PASS ' if cond else 'FAIL ') + name + (' | ' + str(detail) if detail else ''))
    if not cond:
        FAILS.append(name)
    return bool(cond)


def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(45)
    d.set_script_timeout(45)
    return d


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def find_buttons_by_text(drv, text, exact=True):
    out = []
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            t = text_of(drv, b)
        except StaleElementReferenceException:
            continue
        if (t == text) if exact else (text in t):
            out.append(b)
    return out


def click_button_text(drv, text, exact=True, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for b in find_buttons_by_text(drv, text, exact):
            if b.is_displayed():
                js_click(drv, b)
                return True
        time.sleep(0.25)
    return False


def by_id(drv, el_id, timeout=15):
    return WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.ID, el_id)
    )


def model_inputs(drv):
    return [
        e for e in drv.find_elements(By.CSS_SELECTOR, "input[placeholder='如 gpt-4o']")
        if e.is_displayed()
    ]


def error_texts(drv):
    out = []
    for p in drv.find_elements(By.CSS_SELECTOR, 'p.text-destructive'):
        try:
            if p.is_displayed():
                out.append(text_of(drv, p))
        except StaleElementReferenceException:
            pass
    return out


def wait_error(drv, text, present=True, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        has = text in error_texts(drv)
        if has == present:
            return True
        time.sleep(0.2)
    return False


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def providers_ls(drv):
    raw = drv.execute_script('return localStorage.getItem(arguments[0]);', PROVIDER_KEYS)
    return json.loads(raw) if raw else None


def set_theme(drv, mode):
    """同源设置主题后 reload（memory: about:blank 中转会丢主题）。"""
    drv.get(BASE + '/ai-chat')
    drv.execute_script('localStorage.setItem(arguments[0], arguments[1]);', THEME_KEY, mode)
    drv.refresh()
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )
    time.sleep(2)


def clear_providers(drv):
    drv.execute_script('localStorage.removeItem(arguments[0]);', PROVIDER_KEYS)
    drv.refresh()
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )
    time.sleep(2)


def wait_no_provider_trigger(drv, timeout=45):
    return WebDriverWait(drv, timeout).until(
        lambda d: [
            b for b in find_buttons_by_text(d, '未配置 LLM 供应商 → 点击配置', exact=False)
            if b.is_displayed()
        ]
    )


def open_manager_from_empty(drv):
    btns = wait_no_provider_trigger(drv)
    js_click(drv, btns[0])
    WebDriverWait(drv, 20).until(
        lambda d: any('LLM 供应商管理' in text_of(d, e)
                      for e in d.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-content"]'))
    )
    time.sleep(0.6)


def open_add_form(drv):
    assert click_button_text(drv, '添加供应商'), '未找到「添加供应商」'
    by_id(drv, 'provider-name')
    time.sleep(0.3)


def type_into(drv, el, text):
    js_click(drv, el)
    el.send_keys(text)


def dialog_content(drv):
    els = [e for e in drv.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-content"]') if e.is_displayed()]
    return els[0] if els else None


def close_dialog(drv):
    els = drv.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-content"] [data-slot="dialog-close"]')
    for e in els:
        if e.is_displayed():
            js_click(drv, e)
            break
    WebDriverWait(drv, 15).until(
        lambda d: not [e for e in d.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-content"]') if e.is_displayed()]
    )
    time.sleep(0.5)


def check_health(_drv=None):
    """直连 docker 网关 /health（固定 127.0.0.1，避免 localhost 解析到 ::1 卡住）。"""
    import urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:  # noqa: BLE001
        return {'error': str(e)}


def perf_network(drv):
    reqs = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message']) if isinstance(entry['message'], str) else entry['message']
            m = msg.get('message', {})
            if m.get('method') == 'Network.requestWillBeSent':
                p = m.get('params', {})
                req = p.get('request', {})
                reqs.append({'method': req.get('method'), 'url': req.get('url')})
    except Exception as e:  # noqa: BLE001
        reqs.append({'error': str(e)})
    return reqs


def console_severe(drv):
    out = []
    for e in drv.get_log('browser'):
        if e.get('level') == 'SEVERE':
            out.append(e.get('message'))
    return out


def save_form(drv):
    assert click_button_text(drv, '保存'), '未找到「保存」'
    time.sleep(1.0)


def fill_fields(drv, name=PROVIDER_NAME, base=BASE_URL, key=API_KEY):
    type_into(drv, by_id(drv, 'provider-name'), name)
    type_into(drv, by_id(drv, 'provider-base-url'), base)
    type_into(drv, by_id(drv, 'provider-api-key'), key)
    time.sleep(0.4)


def add_model_rows(drv, n=1):
    for _ in range(n):
        assert click_button_text(drv, '添加模型'), '未找到「添加模型」'
        time.sleep(0.3)
    return model_inputs(drv)


def main():
    d = make_driver()
    try:
        # ---------- 浅色：准备 ----------
        set_theme(d, 'light')
        clear_providers(d)
        RESULT['health_start'] = check_health(d)
        ok('health_start_database', RESULT['health_start'].get('database') == 'intelligent_audio_test',
           RESULT['health_start'])

        open_manager_from_empty(d)
        open_add_form(d)

        # ---------- 缺陷 2：空表单保存 → 三条红字 ----------
        save_form(d)
        wait_error(d, '请输入供应商名称')
        errs_blank = error_texts(d)
        ok('defect2_three_errors_on_empty_save',
           set(errs_blank) >= {'请输入供应商名称', '请输入 API Base URL', '请输入 API Key'},
           errs_blank)
        shot(d, '01_light_validation_blank')

        # 填名称 → 名称红字即时消失，其余仍在
        name_input = by_id(d, 'provider-name')
        type_into(d, name_input, PROVIDER_NAME)
        cleared_name = wait_error(d, '请输入供应商名称', present=False, timeout=5)
        errs_after_name = error_texts(d)
        ok('defect2_name_error_clears_on_type',
           cleared_name and '请输入 API Base URL' in errs_after_name and '请输入 API Key' in errs_after_name,
           errs_after_name)

        # 填 Base URL → 对应红字消失
        type_into(d, by_id(d, 'provider-base-url'), BASE_URL)
        cleared_base = wait_error(d, '请输入 API Base URL', present=False, timeout=5)
        ok('defect2_baseurl_error_clears_on_type',
           cleared_base and '请输入 API Key' in error_texts(d), error_texts(d))

        # 填 API Key → 三条全清
        type_into(d, by_id(d, 'provider-api-key'), API_KEY)
        cleared_key = wait_error(d, '请输入 API Key', present=False, timeout=5)
        ok('defect2_all_errors_cleared', cleared_key and error_texts(d) == [], error_texts(d))
        shot(d, '02_light_validation_filled')

        # ---------- 缺陷 1：模型行逐字符输入 ----------
        inputs = add_model_rows(d, 1)
        ok('model_row_count_1', len(inputs) == 1, len(inputs))
        first = inputs[0]
        type_into(d, first, 'gd-4o')
        time.sleep(0.4)
        val = first.get_attribute('value')
        focused = d.execute_script('return document.activeElement === arguments[0];', first)
        ok('defect1_single_row_keeps_full_id', val == 'gd-4o', {'value': val, 'focused': focused})
        ok('defect1_focus_kept', focused, focused)

        # 首行追加 / 退格仍正确
        first.send_keys('-x')
        time.sleep(0.3)
        ok('defect1_append_works', first.get_attribute('value') == 'gd-4o-x', first.get_attribute('value'))
        first.send_keys(Keys.BACKSPACE, Keys.BACKSPACE)
        time.sleep(0.3)
        ok('defect1_backspace_works', first.get_attribute('value') == 'gd-4o', first.get_attribute('value'))

        # 改成 audit-model-a；再加第二行 audit-model-b
        first.send_keys(Keys.CONTROL, 'a')
        first.send_keys(Keys.DELETE)
        first.send_keys(MODEL_A)
        time.sleep(0.3)
        inputs = add_model_rows(d, 1)
        ok('model_row_count_2', len(inputs) == 2, len(inputs))
        second = inputs[1]
        type_into(d, second, MODEL_B)
        time.sleep(0.4)
        ok('defect1_two_rows_keep_full_ids',
           inputs[0].get_attribute('value') == MODEL_A and inputs[1].get_attribute('value') == MODEL_B,
           [inputs[0].get_attribute('value'), inputs[1].get_attribute('value')])
        ok('defect1_second_row_focused',
           d.execute_script('return document.activeElement === arguments[0];', inputs[1]))
        shot(d, '03_light_models_typed')

        # ---------- 保存 + 列表 ----------
        save_form(d)
        dc = dialog_content(d)
        text_dc = text_of(d, dc) if dc else ''
        ok('save_back_to_list', '添加供应商' in text_dc and PROVIDER_NAME in text_dc, text_dc[:60])
        ok('list_shows_key_configured', '已配置 Key' in text_dc, text_dc)
        ok('list_shows_baseurl', BASE_URL in text_dc, text_dc)
        ls = providers_ls(d)
        models_saved = (ls or {}).get('data', [{}])[0].get('models') if ls and ls.get('data') else None
        ok('localStorage_models_complete', models_saved == [MODEL_A, MODEL_B], models_saved)
        ok('localStorage_fields',
           ls and ls['data'][0]['name'] == PROVIDER_NAME and ls['data'][0]['baseUrl'] == BASE_URL
           and ls['data'][0]['apiKey'] == API_KEY,
           ls['data'][0] if ls and ls.get('data') else None)
        shot(d, '04_light_provider_list')

        # ---------- 编辑回填 ----------
        edit_btn = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑']") if b.is_displayed()]
        ok('edit_button_present', len(edit_btn) == 1, len(edit_btn))
        js_click(d, edit_btn[0])
        by_id(d, 'provider-name')
        time.sleep(0.6)
        prefill = {
            'name': by_id(d, 'provider-name').get_attribute('value'),
            'baseUrl': by_id(d, 'provider-base-url').get_attribute('value'),
            'apiKey': by_id(d, 'provider-api-key').get_attribute('value'),
            'models': [e.get_attribute('value') for e in model_inputs(d)],
        }
        ok('edit_prefill_all_fields',
           prefill['name'] == PROVIDER_NAME and prefill['baseUrl'] == BASE_URL
           and prefill['apiKey'] == API_KEY and prefill['models'] == [MODEL_A, MODEL_B],
           prefill)
        shot(d, '05_light_edit_prefill')
        click_button_text(d, '取消')
        WebDriverWait(d, 15).until(
            lambda x: any('添加供应商' in text_of(x, b) for b in find_buttons_by_text(x, '添加供应商'))
        )
        time.sleep(0.5)
        ok('cancel_back_to_list', '添加供应商' in (text_of(d, dialog_content(d)) if dialog_content(d) else ''),
           (text_of(d, dialog_content(d)) if dialog_content(d) else '')[:40])

        # ---------- 关闭弹窗 → 切换器模型列 ----------
        close_dialog(d)
        time.sleep(0.8)
        combo = [b for b in d.find_elements(By.CSS_SELECTOR, "button[role='combobox']") if b.is_displayed()]
        ok('switcher_combobox_present', len(combo) >= 1, len(combo))
        js_click(d, combo[0])
        time.sleep(1.0)
        model_buttons = []
        end = time.time() + 15
        while time.time() < end:
            model_buttons = [
                b for b in d.find_elements(By.TAG_NAME, 'button')
                if b.is_displayed() and text_of(d, b) in (MODEL_A, MODEL_B)
            ]
            if len(model_buttons) >= 2:
                break
            time.sleep(0.3)
        ok('switcher_lists_both_models', len(model_buttons) == 2,
           [text_of(d, b) for b in model_buttons])
        shot(d, '06_light_switcher_models')
        target = [b for b in model_buttons if text_of(d, b) == MODEL_B]
        if target:
            js_click(d, target[0])
            time.sleep(1.0)
        combo2 = [b for b in d.find_elements(By.CSS_SELECTOR, "button[role='combobox']") if b.is_displayed()]
        ok('switcher_model_selected_shows', combo2 and MODEL_B in text_of(d, combo2[0]),
           text_of(d, combo2[0]) if combo2 else None)
        shot(d, '06b_light_switcher_selected')

        # ---------- 重新打开管理弹窗 → 删除 ----------
        combo2 = [b for b in d.find_elements(By.CSS_SELECTOR, "button[role='combobox']") if b.is_displayed()]
        js_click(d, combo2[0])
        time.sleep(1.0)
        assert click_button_text(d, '管理供应商'), '未找到「管理供应商」'
        time.sleep(1.0)
        ok('manager_reopened_with_provider',
           PROVIDER_NAME in (text_of(d, dialog_content(d)) if dialog_content(d) else ''))
        del_btns = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='删除']") if b.is_displayed()]
        ok('delete_button_present', len(del_btns) == 1, len(del_btns))
        js_click(d, del_btns[0])
        WebDriverWait(d, 15).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, '[role="alertdialog"]')) > 0)
        time.sleep(1.0)  # 等弹窗动画结束（memory: 动画期点击被吞）
        al = d.find_element(By.CSS_SELECTOR, '[role="alertdialog"]')
        ok('delete_confirm_dialog', '删除供应商？' in text_of(d, al), text_of(d, al)[:40])
        if not click_button_text(d, '删除'):
            print('WARN confirm delete button not found by text')
        time.sleep(1.2)
        dc = dialog_content(d)
        text_dc = text_of(d, dc) if dc else ''
        ok('list_empty_after_delete', '尚未配置 LLM 供应商' in text_dc, text_dc[:60])
        ls = providers_ls(d)
        ok('localStorage_cleared_after_delete', ls is None or ls.get('data') == [], ls)
        close_dialog(d)

        # ---------- 空白边界：只填空格不清红字 ----------
        open_manager_from_empty(d)
        open_add_form(d)
        save_form(d)
        wait_error(d, '请输入供应商名称')
        name_input = by_id(d, 'provider-name')
        type_into(d, name_input, '   ')
        time.sleep(0.8)
        ok('defect2_whitespace_keeps_error', '请输入供应商名称' in error_texts(d), error_texts(d))
        # 首个供应商 apiKey 必填仍在
        ok('defect2_apiKey_required_when_first', '请输入 API Key' in error_texts(d), error_texts(d))
        close_dialog(d)

        # ---------- 深色 ----------
        set_theme(d, 'dark')
        clear_providers(d)
        is_dark = d.execute_script(
            "return document.documentElement.classList.contains('dark') || "
            "document.documentElement.getAttribute('data-theme') === 'dark';"
        )
        body_bg = d.execute_script("return getComputedStyle(document.body).backgroundColor;")
        ok('dark_theme_applied', bool(is_dark), {'dark': is_dark, 'body_bg': body_bg})
        open_manager_from_empty(d)
        open_add_form(d)
        save_form(d)
        wait_error(d, '请输入供应商名称')
        inputs = add_model_rows(d, 1)
        type_into(d, inputs[0], 'gd-4o')
        time.sleep(0.5)
        ok('dark_model_typing_complete', inputs[0].get_attribute('value') == 'gd-4o',
           inputs[0].get_attribute('value'))
        ok('dark_errors_still_per_field',
           set(error_texts(d)) >= {'请输入供应商名称', '请输入 API Base URL', '请输入 API Key'},
           error_texts(d))
        shot(d, '07_dark_models_typed')
        fill_fields(d)
        ok('dark_errors_cleared_after_fill', error_texts(d) == [], error_texts(d))
        save_form(d)
        ok('dark_save_list', PROVIDER_NAME in (text_of(d, dialog_content(d)) if dialog_content(d) else ''))
        del_btns = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='删除']") if b.is_displayed()]
        js_click(d, del_btns[0])
        WebDriverWait(d, 15).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, '[role="alertdialog"]')) > 0)
        time.sleep(1.0)
        shot(d, '08_dark_delete_confirm')
        click_button_text(d, '删除')
        time.sleep(1.0)
        ls = providers_ls(d)
        ok('dark_delete_clears_ls', ls is None or ls.get('data') == [], ls)

        RESULT['health_end'] = check_health(d)
        ok('health_end_database', RESULT['health_end'].get('database') == 'intelligent_audio_test',
           RESULT['health_end'])

        # ---------- Network / 控制台 ----------
        reqs = perf_network(d)
        writes = [
            r for r in reqs
            if r.get('method') in ('POST', 'PUT', 'DELETE', 'PATCH') and '/api/' in (r.get('url') or '')
        ]
        RESULT['network_total'] = len(reqs)
        RESULT['network_writes'] = writes[:20]
        ok('no_backend_writes', len(writes) == 0, writes)
        severe = console_severe(d)
        RESULT['console_severe'] = severe
        ok('console_no_severe', len(severe) == 0, severe[:5])

    finally:
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump({'fails': FAILS, 'result': RESULT}, f, ensure_ascii=False, indent=2)
        print('FAILS', len(FAILS), FAILS)
        d.quit()
        if FAILS:
            sys.exit(1)


if __name__ == '__main__':
    main()
