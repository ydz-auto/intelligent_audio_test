# -*- coding: utf-8 -*-
"""INT-1483 Phase G2：错误态「请重试」恢复（页内恢复 fetch）、参数表单按类型切换
（功能特性快捷开关 / 数字·滑块范围字段 / min>max 校验）、计数与导航联动、导出文件校验。"""
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'H' + H.RUN_TAG
TYPE = f'itest1483_h_{TAG.lower()}'
NAME = f'接线测试_INT1483_参数_{TAG}'
OUT = {'tag': TAG, 'type': TYPE, 'name': NAME}


def find(xp, t=15):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def wtext(text, t=25):
    WebDriverWait(d, t).until(lambda x: text in H.body_text(x))


def save():
    H.save_evidence('phaseG2_params_rest', OUT)


ERR_JS = r"""
(function(){
  var orig = window.fetch;
  window.__restoreFetchH = function(){ window.fetch = orig; };
  window.fetch = function(u, o){
    var url = (typeof u === 'string') ? u : (u && u.url) || '';
    if (url.indexOf('/algorithm/definitions') !== -1) {
      return Promise.resolve(new Response('{"success":false,"code":500,"message":"模拟接口失败"}',
        {status: 500, headers: {'Content-Type': 'application/json'}}));
    }
    return orig.apply(this, arguments);
  };
})();
"""


def param_rows():
    return d.execute_script("""
      var out = [];
      document.querySelectorAll("input[aria-label='参数代码']").forEach(function(inp, i){
        var tr = inp.closest('tr');
        if (tr) out.push({i: i, code: inp.value || '', idx: out.length});
      });
      return out;
    """)


def row_el(code):
    return d.execute_script("""
      var els = Array.prototype.slice.call(document.querySelectorAll("input[aria-label='参数代码']"));
      var t = null;
      for (var k = 0; k < els.length; k++) { if ((els[k].value||'') === arguments[0]) { t = els[k]; break; } }
      return t ? t.closest('tr') : null;
    """, code)


d = H.driver()
try:
    H.login(d)

    # ============ H1 错误态「请重试」恢复 ============
    sid = d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': ERR_JS})['identifier']
    d.get(H.BASE + '/AlgorithmConfig')
    wtext('加载失败', 45)
    time.sleep(1)
    OUT['error_state_before_retry'] = {
        'desc': '算法配置加载失败，请重试' in H.body_text(d),
        'table_gone': '算法类型' not in H.body_text(d),
    }
    d.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': sid})
    d.execute_script('window.__restoreFetchH && window.__restoreFetchH();')
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '请重试')]"))
    WebDriverWait(d, 45).until(lambda x: '加载失败' not in H.body_text(x))
    time.sleep(1.2)
    OUT['retry_recovered'] = '算法类型' in H.body_text(d)
    OUT['retry_fetches'] = [(e['method'], e['url'], e['status'])
                            for e in H.fetch_log(d, '/algorithm/definitions')][:4]
    H.shot(d, 'H1_after_retry_light')
    save()

    # ============ H2 参数表单 ============
    H.goto_page(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '新建算法')]"))
    wtext('管理算法定义、参数与映射关系')
    time.sleep(1)
    d.find_element(By.ID, 'algo-type').send_keys(TYPE)
    d.find_element(By.ID, 'algo-name').send_keys(NAME)
    time.sleep(0.4)
    OUT['bundle_checkboxes'] = [e.get_attribute('aria-label') for e in
                                d.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='功能特性']")]
    H.shot(d, 'H2_sheet_initial_light')

    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 翻译']"))
    time.sleep(1)
    OUT['bundle_add'] = param_rows()
    H.shot(d, 'H2_bundle_translation_light')

    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 翻译']"))
    time.sleep(0.9)
    OUT['bundle_remove'] = param_rows()

    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 噪声']"))
    time.sleep(1)
    OUT['bundle_noise'] = param_rows()
    OUT['range_before_type'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))

    row = row_el('noise_level')
    OUT['row_found'] = row is not None
    trig = None
    for t in row.find_elements(By.CSS_SELECTOR, "button[role='combobox']"):
        if (t.text or '').strip() == '文本':
            trig = t
            break
    OUT['type_trigger_found'] = trig is not None
    H.js_click(d, trig)
    time.sleep(0.7)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '数字')]"))
    time.sleep(0.9)
    OUT['range_after_number'] = {
        '最小值': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']")),
        '最大值': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最大值']")),
        '步长': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='步长']")),
        '单位': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='单位']")),
    }
    H.shot(d, 'H2_type_number_range_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'H2_type_number_range_dark')
    H.apply_theme(d, 'light')

    # 数字 → 滑块：范围字段保持
    row = row_el('noise_level')
    trig2 = None
    for t in row.find_elements(By.CSS_SELECTOR, "button[role='combobox']"):
        if (t.text or '').strip() == '数字':
            trig2 = t
            break
    H.js_click(d, trig2)
    time.sleep(0.7)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '滑块')]"))
    time.sleep(0.9)
    OUT['range_after_slider'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))

    # 文本 → 范围字段消失
    row = row_el('noise_level')
    trig3 = None
    for t in row.find_elements(By.CSS_SELECTOR, "button[role='combobox']"):
        if (t.text or '').strip() == '滑块':
            trig3 = t
            break
    H.js_click(d, trig3)
    time.sleep(0.7)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '文本')]"))
    time.sleep(0.9)
    OUT['range_after_text'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))

    # 再切数字，填 min>max 发布校验
    row = row_el('noise_level')
    trig = None
    for t in row.find_elements(By.CSS_SELECTOR, "button[role='combobox']"):
        if (t.text or '').strip() == '文本':
            trig = t
            break
    H.js_click(d, trig)
    time.sleep(0.7)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '数字')]"))
    time.sleep(0.9)
    mn = d.find_element(By.CSS_SELECTOR, "input[aria-label='最小值']")
    mx = d.find_element(By.CSS_SELECTOR, "input[aria-label='最大值']")
    mn.clear(); mn.send_keys('10')
    mx.clear(); mx.send_keys('5')
    time.sleep(0.5)
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[@type='submit' and contains(normalize-space(.), '发布')]"))
    time.sleep(3)
    vbody = H.body_text(d)
    OUT['range_validation'] = {
        'min_msg': '最小值不能大于最大值' in vbody,
        'max_msg': '最大值不能小于最小值' in vbody,
        'sheet_open': '管理算法定义、参数与映射关系' in vbody,
    }
    OUT['range_validation_fetches'] = [(e['method'], e['url'], e['status'])
                                       for e in H.fetch_log(d, '/algorithm/definitions')]
    H.shot(d, 'H2_range_validation_light')

    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.9)
    if '有未保存的更改' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.8)
    OUT['sheet_closed'] = '管理算法定义、参数与映射关系' not in H.body_text(d)
    save()

    # ============ H3 计数 / 导航联动 ============
    H.goto_page(d)
    st, pay, _ = H.api_json(d, '/algorithm/definitions')
    api_total = (pay or {}).get('data', {}).get('total')
    st2, pay2, _ = H.api_json(d, '/algorithm/options')
    opt_n = len((pay2 or {}).get('data', {}).get('algorithms') or [])
    body = H.body_text(d)
    OUT['counts'] = {
        'api_total': api_total,
        'options_algorithms': opt_n,
        'badge_matches': f'共 {api_total} 个算法' in body,
        'footer_matches': f'共 {api_total} 个算法 ·' in body,
    }
    OUT['nav_badges'] = d.execute_script("""
      var out = [];
      document.querySelectorAll('aside [data-slot="badge"], nav [data-slot="badge"]').forEach(function(b){
        out.push((b.textContent || '').trim());
      });
      return out.slice(0, 20);
    """)
    H.shot(d, 'H3_list_final_light')

    # ============ H4 导出文件 ============
    dl = os.path.join(H.ART, 'downloads')
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        try:
            os.remove(os.path.join(dl, f))
        except Exception:
            pass
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.6)
    el = WebDriverWait(d, 10).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '导出算法')]")))
    H.js_click(d, el)
    deadline = time.time() + 25
    files = []
    while time.time() < deadline:
        files = [f for f in os.listdir(dl) if not f.endswith('.crdownload')]
        if files:
            break
        time.sleep(1)
    OUT['export_files'] = files
    if files:
        p = os.path.join(dl, files[0])
        OUT['export_size'] = os.path.getsize(p)
        try:
            with open(p, encoding='utf-8') as fh:
                data = json.load(fh)
            OUT['export_count'] = len(data)
            OUT['export_first_type'] = data[0].get('type') if data else None
        except Exception as e:
            OUT['export_parse_error'] = str(e)
    save()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:5000])
finally:
    try:
        d.quit()
    except Exception:
        pass
