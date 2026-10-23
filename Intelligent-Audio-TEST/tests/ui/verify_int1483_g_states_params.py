# -*- coding: utf-8 -*-
"""INT-1483 Phase G：错误态/加载态（CDP 预注入，页面冷启动无缓存）、导入后列表回读、
参数表单按类型切换（功能特性快捷开关 / 数字·滑块范围字段 / min>max 校验）、计数与导航联动、导出文件校验。"""
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import int1483_helpers as H

TAG = 'G' + H.RUN_TAG
TYPE = f'itest1483_g_{TAG.lower()}'
NAME = f'接线测试_INT1483_参数_{TAG}'
OUT = {'tag': TAG, 'type': TYPE, 'name': NAME}


def find(xp, t=15):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((By.XPATH, xp)))


def wtext(text, t=25):
    WebDriverWait(d, t).until(lambda x: text in H.body_text(x))


def save():
    H.save_evidence('phaseG_states_params', OUT)


ERR_JS = r"""
(function(){
  var orig = window.fetch;
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

SLOW_JS = r"""
(function(){
  var orig = window.fetch;
  window.fetch = function(u, o){
    var url = (typeof u === 'string') ? u : (u && u.url) || '';
    var self = this, args = arguments;
    if (url.indexOf('/algorithm/definitions') !== -1) {
      return new Promise(function(r){ setTimeout(function(){ r(orig.apply(self, args)); }, 6000); });
    }
    return orig.apply(self, args);
  };
})();
"""

d = H.driver()
try:
    H.login(d)

    # ============ G1 导入后列表回读（F 阶段上传导入的记录）============
    H.goto_page(d)
    body = H.body_text(d)
    OUT['list_has_upload_imported'] = '接线测试_INT1483_上传导入_' in body
    OUT['list_total_text'] = [t for t in body.split('\n') if '个算法' in t][:3]
    H.shot(d, 'G1_list_after_import_light')

    # ============ G2 错误态：冷启动 + definitions 恒 500 ============
    sid = d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': ERR_JS})['identifier']
    H.clear_fetch_log(d)
    d.get(H.BASE + '/AlgorithmConfig')
    wtext('加载失败', 45)
    time.sleep(1.2)
    err_body = H.body_text(d)
    OUT['error_state'] = {
        'title': '加载失败' in err_body,
        'desc': '算法配置加载失败，请重试' in err_body,
        'retry_btn': '请重试' in err_body,
        'table_gone': '算法类型' not in err_body.split('加载失败')[0][-300:],
    }
    H.shot(d, 'G2_list_error_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'G2_list_error_dark')
    H.apply_theme(d, 'light')
    d.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': sid})
    H.clear_fetch_log(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '请重试')]"))
    WebDriverWait(d, 40).until(lambda x: '加载失败' not in H.body_text(x))
    time.sleep(1)
    OUT['retry_recovered'] = '算法类型' in H.body_text(d)
    OUT['retry_fetches'] = [(e['method'], e['url'], e['status'])
                            for e in H.fetch_log(d, '/algorithm/definitions')][:4]
    H.shot(d, 'G2_after_retry_light')
    save()

    # ============ G3 加载态：冷启动 + definitions 延迟 6s（骨架屏）============
    sid2 = d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': SLOW_JS})['identifier']
    d.get(H.BASE + '/AlgorithmConfig')
    time.sleep(2.0)
    skel = d.find_elements(By.CSS_SELECTOR, "[data-slot='skeleton']")
    OUT['loading'] = {'skeleton_count': len(skel),
                      'body_head': H.body_text(d)[-160:].replace('\n', ' ')}
    H.shot(d, 'G3_list_loading_light')
    d.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': sid2})
    wtext('算法类型', 45)
    time.sleep(1)
    OUT['loading_resolved'] = '算法类型' in H.body_text(d)
    save()

    # ============ G4 参数表单：功能特性开关 + 类型切换 + 范围校验 ============
    H.goto_page(d)
    H.js_click(d, find("//button[contains(normalize-space(.), '新建算法')]"))
    wtext('管理算法定义、参数与映射关系')
    time.sleep(1)
    d.find_element(By.ID, 'algo-type').send_keys(TYPE)
    d.find_element(By.ID, 'algo-name').send_keys(NAME)
    time.sleep(0.5)
    OUT['bundle_checkboxes'] = [e.get_attribute('aria-label') for e in
                                d.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='功能特性']")]
    H.shot(d, 'G4_sheet_initial_light')

    # 勾选「翻译」→ 自动添加 source_language / target_language
    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 翻译']"))
    time.sleep(1)
    codes = [e.get_attribute('value') for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='参数代码']")]
    OUT['bundle_add'] = {'codes': codes,
                         'both': 'source_language' in codes and 'target_language' in codes}
    H.shot(d, 'G4_bundle_translation_light')

    # 取消勾选 → 移除
    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 翻译']"))
    time.sleep(0.8)
    codes_rm = [e.get_attribute('value') for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='参数代码']")]
    OUT['bundle_remove'] = {'codes': codes_rm, 'removed': 'source_language' not in codes_rm}

    # 勾选「噪声」→ 1 行 noise_level；改类型为「数字」→ 范围字段出现
    H.js_click(d, find("//*[@role='checkbox' and @aria-label='功能特性 噪声']"))
    time.sleep(0.9)
    OUT['range_before_type'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))
    row = find("//tr[.//input[@aria-label='参数代码' and @value='noise_level']]")
    trig = None
    for t in row.find_elements(By.CSS_SELECTOR, "button[role='combobox']"):
        if (t.text or '').strip() == '文本':
            trig = t
            break
    OUT['type_trigger_found'] = trig is not None
    H.js_click(d, trig)
    time.sleep(0.6)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '数字')]"))
    time.sleep(0.9)
    OUT['range_after_number'] = {
        '最小值': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']")),
        '最大值': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最大值']")),
        '步长': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='步长']")),
        '单位': len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='单位']")),
    }
    H.shot(d, 'G4_type_number_range_light')
    H.apply_theme(d, 'dark')
    H.shot(d, 'G4_type_number_range_dark')
    H.apply_theme(d, 'light')

    # 切「滑块」仍显范围
    H.js_click(d, find("//tr[.//input[@aria-label='参数代码' and @value='noise_level']]//button[role='combobox'][contains(normalize-space(.), '数字')]"))
    time.sleep(0.6)
    H.js_click(d, find("//*[@role='option'][contains(normalize-space(.), '滑块')]"))
    time.sleep(0.8)
    OUT['range_after_slider'] = len(d.find_elements(By.CSS_SELECTOR, "input[aria-label='最小值']"))

    # min > max 发布校验
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
    H.shot(d, 'G4_range_validation_light')

    # 关闭（丢弃）
    d.find_element(By.TAG_NAME, 'body').send_keys('')
    time.sleep(0.9)
    if '有未保存的更改' in H.body_text(d):
        H.js_click(d, find("//button[contains(normalize-space(.), '离开并丢弃')]"))
        time.sleep(0.8)
    OUT['sheet_closed'] = '管理算法定义、参数与映射关系' not in H.body_text(d)
    save()

    # ============ G5 计数 / 导航联动 ============
    H.goto_page(d)
    st, pay, _ = H.api_json(d, '/algorithm/definitions')
    api_total = (pay or {}).get('data', {}).get('total')
    st, pay2, _ = H.api_json(d, '/algorithm/options')
    opt_n = len((pay2 or {}).get('data', {}).get('algorithms') or [])
    body = H.body_text(d)
    OUT['counts'] = {
        'api_total': api_total,
        'options_algorithms': opt_n,
        'badge': f'共 {api_total} 个算法' in body,
        'footer': f'共 {api_total} 个算法 ·' in body,
        'global_switcher': d.execute_script(
            "var el=document.querySelector('[aria-label*=\"算法\"], [data-slot=\"algorithm-switcher\"]'); return el ? (el.textContent||'').trim().slice(0,60) : null;"),
    }
    OUT['nav_badges'] = d.execute_script("""
      var out=[];
      document.querySelectorAll('aside [data-slot="badge"], nav [data-slot="badge"]').forEach(function(b){
        out.push((b.textContent||'').trim());
      });
      return out.slice(0,20);
    """)
    H.shot(d, 'G5_list_final_light')

    # ============ G6 导出文件（补上一轮 headless 未取到）============
    dl = os.path.join(H.ART, 'downloads')
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        try:
            os.remove(os.path.join(dl, f))
        except Exception:
            pass
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
    H.js_click(d, d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']"))
    time.sleep(0.5)
    el = WebDriverWait(d, 10).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '导出算法')]")))
    H.js_click(d, el)
    deadline = time.time() + 20
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
