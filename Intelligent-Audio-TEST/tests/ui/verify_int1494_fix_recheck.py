# -*- coding: utf-8 -*-
"""INT-1494 打回复测：INT-1596（供应商弹窗模型行丢字 / 校验红字不清）与
INT-1597（关于页状态卡刷新按钮掉行）修复后重走。

用法：
  REACT_BASE=http://127.0.0.1:15241 python tests/ui/verify_int1494_fix_recheck.py fixed
  REACT_BASE=http://127.0.0.1:15173 python tests/ui/verify_int1494_fix_recheck.py baseline

fixed  = 旁路 docker 容器（wiring/react + bea0ef59 + b9cf0462 构建）
baseline = 常驻 15173 旧镜像（用于 A/B 对照，证明脚本能区分修复前后）
"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1494_helpers import (ARTIFACTS, BASE, body_text, clear_perf, driver,  # noqa: E402
                             goto, js_click, set_theme, shot)

TAG = sys.argv[1] if len(sys.argv) > 1 else 'fixed'
OUT = os.path.join(ARTIFACTS, 'fix_recheck_%s.json' % TAG)
PROVIDER = '接线测试_LLM供应商'
LS_KEY = 'iatp:ai-chat:v1:providers'


def find_btn(d, *texts, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        for b in d.find_elements(By.CSS_SELECTOR, 'button, [role=button], a'):
            try:
                t = ((b.text or '') + ' ' + (b.get_attribute('aria-label') or '')).strip()
            except Exception:
                continue
            for want in texts:
                if want in t and b.is_displayed():
                    return b
        time.sleep(0.3)
    return None


def wait_text(d, text, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if text in body_text(d):
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def type_charwise(d, elem, text):
    """逐字符输入，记录每步 DOM value 与焦点是否仍在同一 input（INT-1596 取证口径）。"""
    steps = []
    elem.click()
    js_click(d, elem)
    for ch in text:
        elem.send_keys(ch)
        time.sleep(0.06)
        steps.append({
            'ch': ch,
            'value': d.execute_script(
                "return document.activeElement && document.activeElement.value !== undefined "
                "? document.activeElement.value : null"),
            'focused_same': d.execute_script(
                "return document.activeElement === arguments[0];", elem),
        })
    return steps


def open_manager(d):
    # 无供应商：整钮「未配置 LLM 供应商 → 点击配置」直接开弹窗
    trig = find_btn(d, '未配置', timeout=5)
    if trig is None:
        # 已有供应商：先展开 combobox，再点面板里的「管理供应商」
        # （不能按 'LLM' 兜底匹配，供应商名「接线测试_LLM供应商」会让 combobox 被误判成入口）
        cb = d.find_elements(By.CSS_SELECTOR, "[role='combobox']")
        if cb:
            js_click(d, cb[0])
            time.sleep(1.2)
            trig = find_btn(d, '管理供应商')
    if trig is not None:
        js_click(d, trig)
        time.sleep(1.2)
    return wait_text(d, 'LLM 供应商管理', 8)


def provider_flow(d, st, shots):
    goto(d, '/ai-chat', wait_text='灵犀Agent')
    time.sleep(2.0)
    d.execute_script("window.localStorage.removeItem(arguments[0]);", LS_KEY)
    d.refresh()
    time.sleep(2.5)
    st['opened'] = open_manager(d)
    shots.append(shot(d, 'recheck_%s_manager_open_light' % TAG))
    if not st['opened']:
        return

    add = find_btn(d, '添加供应商')
    if add is None:
        st['add_button'] = False
        return
    js_click(d, add)
    time.sleep(1)

    # —— 缺陷 2：必填留空 → 三条红字；逐项填入后即时消失 ——
    sav = find_btn(d, '保存')
    js_click(d, sav)
    time.sleep(1.0)
    t = body_text(d)
    st['errors_empty'] = [x for x in ('请输入供应商名称', '请输入 API Base URL', '请输入 API Key') if x in t]

    clear_steps = {}
    for field_id, err in (('provider-name', '请输入供应商名称'),
                          ('provider-base-url', '请输入 API Base URL'),
                          ('provider-api-key', '请输入 API Key')):
        val = {'provider-name': PROVIDER,
               'provider-base-url': 'http://127.0.0.1:18899/v1',
               'provider-api-key': 'sk-int1494'}[field_id]
        el = d.find_element(By.ID, field_id)
        el.send_keys(val)
        time.sleep(0.5)
        clear_steps[err] = err not in body_text(d)
    st['error_cleared_after_fill'] = clear_steps
    shots.append(shot(d, 'recheck_%s_manager_errors_cleared_light' % TAG))

    # —— 缺陷 1：手动逐字符输入两个模型 id ——
    for _ in range(2):
        mb = find_btn(d, '添加模型')
        js_click(d, mb)
        time.sleep(0.4)
    inputs = d.find_elements(By.CSS_SELECTOR, "input[placeholder='如 gpt-4o']")
    st['model_rows'] = len(inputs)
    if len(inputs) >= 2:
        st['typing_first'] = type_charwise(d, inputs[0], 'audit-model-a')
        st['typing_second'] = type_charwise(d, inputs[1], 'audit-model-b')
        inputs = d.find_elements(By.CSS_SELECTOR, "input[placeholder='如 gpt-4o']")
        st['model_values_after_typing'] = [i.get_attribute('value') for i in inputs]
    shots.append(shot(d, 'recheck_%s_manager_manual_models_light' % TAG))

    # 保存 → 列表回读 + localStorage 信封
    js_click(d, find_btn(d, '保存'))
    time.sleep(1.5)
    st['saved_in_list'] = PROVIDER in body_text(d)
    st['ls_after_save'] = d.execute_script(
        "return window.localStorage.getItem(arguments[0]);", LS_KEY)
    shots.append(shot(d, 'recheck_%s_manager_saved_light' % TAG))

    # 编辑重开（浅色）：三字段 + 模型回填
    ed = d.find_element(By.CSS_SELECTOR, "button[aria-label='编辑']")
    js_click(d, ed)
    time.sleep(1.2)
    edit_prefill = {
        'name': d.find_element(By.ID, 'provider-name').get_attribute('value'),
        'baseUrl': d.find_element(By.ID, 'provider-base-url').get_attribute('value'),
        'apiKey': d.find_element(By.ID, 'provider-api-key').get_attribute('value'),
        'models': [i.get_attribute('value') for i in
                   d.find_elements(By.CSS_SELECTOR, "input[placeholder='如 gpt-4o']")],
    }
    st['edit_prefill'] = edit_prefill
    shots.append(shot(d, 'recheck_%s_manager_edit_prefill_light' % TAG))
    cancel = find_btn(d, '取消')
    if cancel:
        js_click(d, cancel)
        time.sleep(1)

    # 删除确认（浅色）——先取消，保留供应商给深色轮
    dl = d.find_element(By.CSS_SELECTOR, "button[aria-label='删除']")
    js_click(d, dl)
    time.sleep(1.2)
    st['delete_confirm'] = '删除供应商' in body_text(d)
    shots.append(shot(d, 'recheck_%s_manager_delete_confirm_light' % TAG))
    cancel = find_btn(d, '取消')
    if cancel:
        js_click(d, cancel)
        time.sleep(1)

    # —— 深色轮：主题在挂载时读取 localStorage，必须写后重载才生效 ——
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.refresh()
    time.sleep(2.5)
    st['dark_opened'] = open_manager(d)
    st['dark_html_class'] = d.execute_script(
        "return document.documentElement.className;")
    st['dark_saved_in_list'] = PROVIDER in body_text(d)
    shots.append(shot(d, 'recheck_%s_manager_saved_dark' % TAG))

    ed = d.find_element(By.CSS_SELECTOR, "button[aria-label='编辑']")
    js_click(d, ed)
    time.sleep(1.2)
    st['edit_prefill_dark'] = {
        'name': d.find_element(By.ID, 'provider-name').get_attribute('value'),
        'baseUrl': d.find_element(By.ID, 'provider-base-url').get_attribute('value'),
        'apiKey': d.find_element(By.ID, 'provider-api-key').get_attribute('value'),
        'models': [i.get_attribute('value') for i in
                   d.find_elements(By.CSS_SELECTOR, "input[placeholder='如 gpt-4o']")],
    }
    shots.append(shot(d, 'recheck_%s_manager_edit_prefill_dark' % TAG))
    cancel = find_btn(d, '取消')
    if cancel:
        js_click(d, cancel)
        time.sleep(1)

    # 删除 + 确认 + 回读（深色）
    dl = d.find_element(By.CSS_SELECTOR, "button[aria-label='删除']")
    js_click(d, dl)
    time.sleep(1.2)
    shots.append(shot(d, 'recheck_%s_manager_delete_confirm_dark' % TAG))
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() in ('删除', '确认', '确定') and b.is_displayed():
            js_click(d, b)
            break
    time.sleep(1.5)
    st['after_delete_has_provider'] = PROVIDER in body_text(d)
    st['ls_after_delete'] = d.execute_script(
        "return window.localStorage.getItem(arguments[0]);", LS_KEY)
    shots.append(shot(d, 'recheck_%s_manager_after_delete_dark' % TAG))
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")


def about_flow(d, st, shots):
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")
    goto(d, '/about', wait_text='版本与服务状态')
    time.sleep(2.5)
    geo = d.execute_script("""
      const card = [...document.querySelectorAll('[data-slot="card"], .card, div')]
        .find(el => (el.textContent||'').includes('版本与服务状态') && el.querySelector('[aria-label*="刷新服务状态"]'));
      const title = card
        ? (card.querySelector('[data-slot="card-title"]') ||
           [...card.querySelectorAll('*')].find(el => (el.textContent||'').trim() === '版本与服务状态'))
        : null;
      const btn = document.querySelector('[aria-label*="刷新服务状态"]');
      if (!title || !btn) return {found:false};
      const tr = title.getBoundingClientRect(), br = btn.getBoundingClientRect();
      const header = btn.closest('[data-slot="card-header"]') || btn.parentElement;
      const hr = header ? header.getBoundingClientRect() : null;
      return {found:true,
        title:{top:tr.top,bottom:tr.bottom,left:tr.left,right:tr.right,cy:(tr.top+tr.bottom)/2},
        btn:{top:br.top,bottom:br.bottom,left:br.left,right:br.right,cx:(br.left+br.right)/2},
        header: hr ? {top:hr.top,bottom:hr.bottom,height:hr.height} : null,
        same_row: Math.abs(((tr.top+tr.bottom)/2) - ((br.top+br.bottom)/2)) < 10,
        btn_right_of_title: br.left >= tr.right - 1,
        header_height: hr ? hr.height : null,
        btn_height: br.height};
    """)
    st['geometry'] = geo
    st['body_has_health'] = all(x in body_text(d) for x in ('V9.7.31', 'intelligent_audio_test'))
    d.execute_script("""
      const btn = document.querySelector('[aria-label*="刷新服务状态"]');
      const card = btn && (btn.closest('[data-slot="card"]') || btn.closest('.card'));
      (card || btn).scrollIntoView({block: 'center'});
    """)
    time.sleep(0.8)
    shots.append(shot(d, 'recheck_%s_about_statuscard_light' % TAG))

    clear_perf(d)
    js_click(d, d.find_element(By.CSS_SELECTOR, "[aria-label*='刷新服务状态']"))
    time.sleep(2.5)
    calls = []
    for entry in d.get_log('performance'):
        try:
            msg = json.loads(entry['message'])
        except Exception:
            continue
        if msg.get('message', {}).get('method') != 'Network.responseReceived':
            continue
        p = msg['message']['params']['response']
        if 'system/health' in p.get('url', ''):
            calls.append({'url': p.get('url'), 'status': p.get('status')})
    st['refresh_calls'] = calls
    st['body_after_refresh'] = body_text(d)[:200]
    shots.append(shot(d, 'recheck_%s_about_after_refresh_light' % TAG))

    st['html_class_light'] = d.execute_script("return document.documentElement.className;")
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.refresh()
    time.sleep(3.0)
    st['html_class_dark'] = d.execute_script("return document.documentElement.className;")
    d.execute_script("""
      const btn = document.querySelector('[aria-label*="刷新服务状态"]');
      const card = btn && (btn.closest('[data-slot="card"]') || btn.closest('.card'));
      (card || btn).scrollIntoView({block: 'center'});
    """)
    time.sleep(0.8)
    shots.append(shot(d, 'recheck_%s_about_statuscard_dark' % TAG))


def main():
    d = driver()
    st, shots = {}, []
    only = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        set_theme(d, 'light')
        if only != 'about':
            provider_flow(d, st, shots)
        if only != 'provider':
            about_flow(d, st, shots)
    except Exception as exc:
        st['exception'] = repr(exc)
    finally:
        try:
            d.execute_script("window.localStorage.removeItem(arguments[0]);", LS_KEY)
            d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")
        except Exception:
            pass
        d.quit()
    st['tag'] = TAG
    st['base'] = BASE
    st['shots'] = [os.path.basename(p) for p in shots]
    os.makedirs(ARTIFACTS, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(st, fh, ensure_ascii=False, indent=2)
    print(json.dumps(st, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
