# -*- coding: utf-8 -*-
"""INT-1642 验收：用例域五项修复（参考参数接线 / 导出弹窗接线 / 播放设备回显 /
批量评估维度真实轮次 / 噪声步演示文案）。

前端：本卡交付 diff（492fe09b4）build 后 rsbuild dev 5331 → docker 网关 127.0.0.1:15000
（库 intelligent_audio_test，AUTH_MODE=off）。
真实数据用例：
- db8e4328-28d0-48a8-b3ae-9a19d7b58d45（3 轮，reference_params 3 条，播放设备 5，有音频）
- ddb6044a-2519-4815-b4dd-ba1bdd83221a（1 轮）
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5331'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1642')
DL = os.path.join(ART, 'downloads')
os.makedirs(DL, exist_ok=True)
RES = {}
NOTES = []

CASE3 = 'db8e4328-28d0-48a8-b3ae-9a19d7b58d45'
CASE1 = 'ddb6044a-2519-4815-b4dd-ba1bdd83221a'

FETCH_PATCH = r"""
window.__fetchLog = [];
window.__stubRules = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  const hit = (window.__stubRules || []).find(function(r) {
    return (!r.method || r.method === method) && url.indexOf(r.match) !== -1;
  });
  if (hit) {
    window.__fetchLog.push({url: url, method: method, status: hit.status, stub: true,
      reqBody: typeof init2.body === 'string' ? init2.body : null,
      resBody: hit.body, t: Date.now()});
    return new Response(hit.body, {status: hit.status, headers: {'Content-Type': 'application/json'}});
  }
  let res;
  try {
    res = await __origFetch.apply(this, arguments);
  } catch (e) {
    window.__fetchLog.push({url: url, method: method, status: -1, error: String(e), t: Date.now()});
    throw e;
  }
  const entry = {url: url, method: method, status: res.status, t: Date.now(),
    reqBody: typeof init2.body === 'string' ? init2.body : null};
  if (url.indexOf('/api/v1') !== -1) {
    try { entry.resBody = await res.clone().text(); } catch (e) {}
  }
  window.__fetchLog.push(entry);
  return res;
};
"""


def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    o.add_experimental_option('prefs', {
        'download.default_directory': DL.replace('\\', '/'),
        'download.prompt_for_download': False,
        'safebrowsing.enabled': True,
    })
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
    d.set_page_load_timeout(60)
    d.set_script_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        d.execute_cdp_cmd('Page.setDownloadBehavior',
                          {'behavior': 'allow', 'downloadPath': DL})
    except Exception:
        pass
    return d


def js(d, script, *args):
    return d.execute_script(script, *args)


def body_text(d):
    return js(d, 'return document.body ? (document.body.innerText || "") : "";') or ''


def wait_body(d, sub, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        if sub in body_text(d):
            return True
        time.sleep(0.4)
    return False


def wait_gone(d, sub, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if sub not in body_text(d):
            return True
        time.sleep(0.4)
    return False


def wait_fn(d, fn, timeout=40, step=0.4):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(step)
    return None


def text_of(d, el):
    try:
        return (js(d, 'return (arguments[0].innerText || arguments[0].textContent || "").trim();', el) or '')
    except Exception:
        return ''


def js_click(d, el):
    js(d, 'arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def btn_by_text(d, text, root=None, contains=True):
    root = root or d
    els = root.find_elements(By.TAG_NAME, 'button')
    for el in els:
        t = text_of(d, el)
        if (text in t) if contains else (t == text):
            return el
    return None


def click_btn(d, text, timeout=20, root=None):
    el = wait_fn(d, lambda: btn_by_text(d, text, root), timeout)
    if el is None:
        raise RuntimeError('button not found: ' + text)
    js_click(d, el)
    return True



def open_case_drawer(d, keyword):
    """按用例名关键字找卡片 → 点行内「编辑用例」打开抽屉。"""
    cb = wait_fn(d, lambda: next((c for c in card_checkboxes(d)
                                  if keyword in (c.get_attribute('aria-label') or '')), None), 40)
    if cb is None:
        return False
    card = cb.find_element(By.XPATH, "./ancestor::div[contains(@class,'bg-card')][1]")
    btn = wait_fn(d, lambda: next((b for b in card.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']")), None), 15)
    if btn is None:
        return False
    js_click(d, btn)
    return True

def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    print('SHOT', name)
    return p


def set_search(d, value):
    inp = wait_fn(d, lambda: (d.find_elements(By.CSS_SELECTOR, "[aria-label='搜索用例']") or [None])[0], 30)
    if inp is None:
        raise RuntimeError('search input not found')
    js_click(d, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    if value:
        inp.send_keys(value)
    time.sleep(2.6)


def card_checkboxes(d):
    return [e for e in d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')]


def expand_group(d, keyword, timeout=150):
    """展开指定名称的分组卡（默认收起；组内用例懒加载，展开才拉）。已展开则不重复点。"""
    head = wait_fn(d, lambda: next(
        (e for e in d.find_elements(By.XPATH, "//div[contains(@class,'cursor-pointer')]")
         if keyword in (text_of(d, e) or '') and '条' in (text_of(d, e) or '')), None), 30)
    if head is None:
        return False
    collapsed = js(d, """const svg = arguments[0].querySelector('svg');
        return svg ? /-rotate-90/.test(svg.getAttribute('class') || '') : true;""", head)
    if collapsed:
        js_click(d, head)
    got = wait_fn(d, lambda: len(card_checkboxes(d)) > 0, timeout, 2.0)
    if not got and not collapsed:
        js_click(d, head)
        got = wait_fn(d, lambda: len(card_checkboxes(d)) > 0, timeout, 2.0)
    return bool(got)


def fetch_log(d, match=None, method=None):
    try:
        logs = js(d, 'return window.__fetchLog || [];') or []
    except Exception:
        logs = []
    out = []
    for e in logs:
        if match and match not in (e.get('url') or ''):
            continue
        if method and (e.get('method') or '') != method:
            continue
        out.append(e)
    return out


def clear_log(d):
    js(d, 'window.__fetchLog = [];')


def wait_download(prefix, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        files = [f for f in os.listdir(DL) if not f.endswith('.crdownload')]
        cand = [f for f in files if f.startswith(prefix)]
        if cand:
            cand.sort(key=lambda f: os.path.getmtime(os.path.join(DL, f)))
            return os.path.join(DL, cand[-1])
        time.sleep(0.5)
    return None


def open_export(d):
    click_btn(d, '导出', 20)
    ok = wait_body(d, '导出用例', 20)
    time.sleep(0.6)
    return ok


def main():
    results = {}
    d = make_driver()
    try:
        # ---------- A. 用例列表 + 导出弹窗（浅色） ----------
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 60), 'page not loaded'
        assert wait_fn(d, lambda: len(d.find_elements(By.XPATH, "//div[contains(@class,'cursor-pointer')]")) > 0, 60), 'no groups'
        time.sleep(2)
        shot(d, '01_list_light')

        assert open_export(d), 'export dialog not open'
        # 未勾选时「仅导出已选 0 个」radio 禁用
        disabled = js(d, """
          const ins = Array.from(document.querySelectorAll("input[name='export-range']"));
          return ins.filter(function(i){return i.disabled;}).length;
        """)
        results['export_selected_radio_disabled_count'] = disabled
        shot(d, '02_export_dialog_light')
        click_btn(d, '取消', 15)

        # 筛选到 JS172 单条用例 → 按当前筛选导出 JSON
        set_search(d, '测试用例_JS172_多轮拒识')
        expand_group(d, '拒识')
        cards = card_checkboxes(d)
        results['filtered_card_count_js172'] = len(cards)
        results['filtered_has_target'] = any('多轮拒识' in (c.get_attribute('aria-label') or '') for c in cards)

        def clear_downloads():
            for f in os.listdir(DL):
                try:
                    os.remove(os.path.join(DL, f))
                except OSError:
                    pass

        def run_export(fmt, tag, expect_fail=False):
            clear_downloads()
            clear_log(d)
            assert open_export(d), 'export dialog not open (%s)' % tag
            if fmt != 'json':
                trig = wait_fn(d, lambda: next(
                    (e for e in d.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
                     if text_of(d, e) in ('JSON', 'Excel')), None), 15)
                if trig is None:
                    return {'error': 'format_select_not_found'}
                js_click(d, trig)
                time.sleep(0.8)
                opt = wait_fn(d, lambda: next(
                    (o for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]')
                     if text_of(d, o) == 'Excel'), None), 15)
                if opt is not None:
                    js_click(d, opt)
                    time.sleep(0.5)
            click_btn(d, '开始导出', 20)
            if expect_fail:
                wait_fn(d, lambda: '导出失败' in body_text(d), 60)
            else:
                wait_fn(d, lambda: '已导出' in body_text(d), 90)
            time.sleep(1.5)
            out = {'calls': [{'url': e.get('url'), 'method': e.get('method'), 'status': e.get('status')}
                             for e in fetch_log(d, '/testcases/export')],
                   'ids_calls': [{'url': e.get('url'), 'status': e.get('status')}
                                 for e in fetch_log(d, '/testcases/ids')],
                   'toast': ('已导出' in body_text(d)),
                   'fail_toast': ('导出失败' in body_text(d))}
            files = sorted([f for f in os.listdir(DL) if not f.endswith('.crdownload')],
                           key=lambda f: os.path.getmtime(os.path.join(DL, f)))
            out['files'] = files
            return out

        r = run_export('json', 'json')
        results['json'] = r
        jf = os.path.join(DL, r['files'][-1]) if r.get('files') else None
        if jf and jf.endswith('.json'):
            results['json_download'] = os.path.basename(jf)
            results['json_download_size'] = os.path.getsize(jf)
            try:
                with open(jf, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                results['json_keys'] = sorted(list(data.keys()))[:8]
                results['json_total_count'] = data.get('total_count')
                tc = data.get('test_cases') or []
                results['json_test_cases_len'] = len(tc)
                results['json_first_name'] = (tc[0].get('name') if tc else None)
            except Exception as e:
                results['json_parse_error'] = str(e)[:200]
        shot(d, '03_export_json_done_light')

        # Excel
        r = run_export('xlsx', 'xlsx')
        results['xlsx'] = r
        xs = [f for f in r.get('files') or [] if f.endswith('.xlsx')]
        if xs:
            xf = os.path.join(DL, xs[-1])
            with open(xf, 'rb') as fh:
                head = fh.read(4)
            results['xlsx_download'] = xs[-1]
            results['xlsx_size'] = os.path.getsize(xf)
            results['xlsx_magic'] = head.hex()
        shot(d, '04_export_xlsx_done_light')

        # 失败态：stub 400「未指定要导出的用例ID」→ toast 透出后端 message
        js(d, """window.__stubRules.push({method:'POST', match:'/testcases/export', status:400,
          body: JSON.stringify({success:false, code:203, message:'未指定要导出的用例ID'})});""")
        r = run_export('json', 'fail-state', expect_fail=True)
        results['export_failure'] = r
        results['export_failure_toast_backend_message'] = bool(r.get('fail_toast'))
        shot(d, '05_export_failure_light')
        js(d, 'window.__stubRules = [];')
        click_btn(d, '取消', 15)
        time.sleep(0.8)

        # 空筛选：无匹配 → 明确提示，不发起导出
        set_search(d, 'zzz_int1642_不存在')
        clear_log(d)
        clear_downloads()
        assert open_export(d), 'export dialog not open (empty filter)'
        click_btn(d, '开始导出', 20)
        got = wait_fn(d, lambda: '没有可导出的用例' in body_text(d), 30)
        results['export_empty_filter_toast'] = bool(got)
        results['export_empty_filter_export_calls'] = len(fetch_log(d, '/testcases/export'))
        shot(d, '06_export_empty_filter_light')
        click_btn(d, '取消', 15)
        set_search(d, '')

        # ---------- B. 抽屉：音频列表 / 噪声 / 参考参数 ----------
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 60), 'page not reloaded before drawer'
        time.sleep(2)
        set_search(d, '测试用例_JS172_多轮拒识')
        expand_group(d, '拒识')
        assert open_case_drawer(d, 'JS172'), 'case drawer not opened'
        assert wait_body(d, '轮次配置', 30), 'drawer not open'
        time.sleep(1.2)
        shot(d, '07_drawer_light')

        # 音频列表：播放设备闭合态显示设备名（非记录 id）
        click_btn(d, '音频列表', 20)
        time.sleep(1.5)
        trig_text = js(d, """
          const dlg = document.querySelector('[role="dialog"]') || document.body;
          const cs = Array.from(dlg.querySelectorAll('[role="combobox"]'));
          return cs.map(function(c){return (c.innerText||c.textContent||'').trim();});
        """)
        results['audio_device_combobox_texts'] = trig_text
        results['audio_device_shows_name'] = any(('设备' in (t or '')) for t in (trig_text or []))
        results['audio_device_raw_id_only'] = [t for t in (trig_text or []) if re.fullmatch(r'\d+', (t or '').strip())]
        # 下方「设备：」行名称
        dev_line = js(d, """
          const dlg = document.querySelector('[role="dialog"]') || document.body;
          const ps = Array.from(dlg.querySelectorAll('p'));
          const hit = ps.find(function(p){return (p.innerText||'').trim().indexOf('设备：') === 0;});
          return hit ? (hit.innerText||'').trim() : '';
        """)
        results['audio_device_line'] = dev_line
        shot(d, '08_audio_step_light')

        # 噪声与干扰：无「演示提示条」残留
        click_btn(d, '噪声与干扰', 20)
        time.sleep(1.2)
        bt = body_text(d)
        results['noise_no_demo_hint'] = ('演示提示条' not in bt)
        results['noise_no_static_unmatched_hint'] = ('导入时未匹配到音频 ID，保存后后端会按文件名解析' not in bt)
        results['noise_has_import_hint_with_files'] = ('导入时未匹配到音频 ID 的干扰音频' in bt)
        shot(d, '09_noise_step_light')

        # 参考参数：真实端点 404 → 真实路径 + 显式失败态（非假路径 / 非静默空态）
        clear_log(d)
        click_btn(d, '参考参数', 20)
        time.sleep(2.0)
        bt = body_text(d)
        results['ref_missing_state_text'] = '参考参数内容读取失败' in bt
        results['ref_has_retry'] = ('重试' in bt)
        results['ref_shows_real_path'] = ('ref_params' in bt) and ('db8e4328' in bt)
        results['ref_fake_path_present'] = ('tc-001' in bt)
        results['ref_get_calls'] = [
            {'url': e.get('url'), 'status': e.get('status'), 'res': (e.get('resBody') or '')[:160]}
            for e in fetch_log(d, '/rounds/1/ref-params')]
        shot(d, '10_reference_error_light')

        # 前端读写接线：stub 200（后端 FEAT INT-1645 缺口）→ 查看/编辑 → 保存 → 回读一致
        js(d, """window.__stubRules.push({method:'GET', match:'/rounds/1/ref-params', status:200,
          body: JSON.stringify({success:true, code:0, message:'Success', data:{
            roundNumber:1,
            referenceParamsPath:'D:\\\\00_static\\\\static\\\\ref_params\\\\db8e4328-28d0-48a8-b3ae-9a19d7b58d45\\\\round_1.json',
            referenceParams:{threshold:0.5, keywords:['拒绝','拒识']}}})});""")
        clear_log(d)
        click_btn(d, '重试', 20)
        ok_view = wait_fn(d, lambda: '查看/编辑' in body_text(d), 25)
        results['ref_stub_view_mode'] = bool(ok_view)
        shot(d, '11_reference_stub_view_light')
        if ok_view:
            click_btn(d, '查看/编辑', 20)
            ta = wait_fn(d, lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "textarea[placeholder='编辑参考参数 JSON…']")), None), 20)
            results['ref_textarea_prefill'] = (ta.get_attribute('value') if ta else None)
            if ta is not None:
                js(d, 'arguments[0].value = "";', ta)
                ta.send_keys('{"threshold": 0.88, "keywords": ["拒绝", "拒识"]}')
                time.sleep(0.4)
                js(d, """window.__stubRules.push({method:'PUT', match:'/rounds/1/ref-params', status:200,
                  body: JSON.stringify({success:true, code:0, message:'参考参数更新成功', data:{
                    roundNumber:1,
                    referenceParamsPath:'D:\\\\00_static\\\\static\\\\ref_params\\\\db8e4328-28d0-48a8-b3ae-9a19d7b58d45\\\\round_1.json',
                    referenceParams:{threshold:0.88, keywords:['拒绝','拒识']}}})});""")
                clear_log(d)
                click_btn(d, '保存', 20)
                saved = wait_fn(d, lambda: '参考参数已保存' in body_text(d), 25)
                results['ref_save_toast'] = bool(saved)
                puts = fetch_log(d, '/rounds/1/ref-params', 'PUT')
                results['ref_put_calls'] = [
                    {'status': e.get('status'), 'reqBody': (e.get('reqBody') or '')[:200],
                     'resBody': (e.get('resBody') or '')[:200]} for e in puts]
                shot(d, '12_reference_saved_light')
                # 再次进入编辑 → 内容 = 保存后的内容（缓存回写，GET 回读同口径）
                click_btn(d, '查看/编辑', 20)
                ta2 = wait_fn(d, lambda: next((e for e in d.find_elements(By.CSS_SELECTOR, "textarea[placeholder='编辑参考参数 JSON…']")), None), 20)
                results['ref_reopen_value'] = (ta2.get_attribute('value') if ta2 else None)
                results['ref_readback_consistent'] = bool(
                    ta2 is not None and '0.88' in (ta2.get_attribute('value') or ''))
        js(d, 'window.__stubRules = [];')

        # 关闭抽屉
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 60), 'back to list failed'
        time.sleep(1.0)

        # ---------- C. 批量设置评估维度：真实轮次 ----------
        def open_batch_for(search_text):
            d.get(BASE + '/testcases')
            wait_body(d, '用例管理', 60)
            time.sleep(2)
            set_search(d, search_text)
            expand_group(d, '拒识')
            cbs = card_checkboxes(d)
            if not cbs:
                return None
            js_click(d, cbs[0])
            ok = wait_fn(d, lambda: '个用例已选择' in body_text(d), 20)
            if not ok:
                return None
            click_btn(d, '批量设置评估维度', 20)
            wait_body(d, '批量设置评估维度', 20)
            time.sleep(1.0)
            # 切到「指定轮次」才渲染轮次号网格
            rd = next((l for l in d.find_elements(By.TAG_NAME, 'label')
                       if '指定轮次' in (text_of(d, l) or '')), None)
            if rd is not None:
                js_click(d, rd)
                time.sleep(1.2)
            labels = js(d, """
              const dlg = document.querySelector('[role="dialog"]');
              if (!dlg) return [];
              const out = [];
              Array.from(dlg.querySelectorAll('label')).forEach(function(l){
                const t = (l.innerText||l.textContent||'').trim();
                if (/^第\\d+轮$/.test(t)) out.push(t);
              });
              return out;
            """)
            return labels

        r1 = open_batch_for('测试用例_JS115_单轮拒识')
        results['batch_rounds_1round_case'] = r1
        shot(d, '13_batch_rounds_1round_light')
        click_btn(d, '取消', 20)
        time.sleep(1.0)

        r3 = open_batch_for('测试用例_JS172_多轮拒识')
        results['batch_rounds_3round_case'] = r3
        # 逐轮 Tab 文案
        try:
            per_round = wait_fn(d, lambda: next((e for e in d.find_elements(By.TAG_NAME, 'label')
                                                  if '逐轮设置' in text_of(d, e)), None), 10)
            if per_round is None:
                per_round = wait_fn(d, lambda: next((e for e in d.find_elements(By.XPATH, "//*[contains(text(),'逐轮设置')]")), None), 10)
            if per_round is not None:
                js_click(d, per_round)
                time.sleep(1.0)
                tabs = js(d, """
                  const dlg = document.querySelector('[role="dialog"]');
                  if (!dlg) return [];
                  return Array.from(dlg.querySelectorAll('button[role="tab"]')).map(function(b){
                    return (b.innerText||'').trim();
                  });
                """)
                results['batch_per_round_tabs'] = tabs
                shot(d, '14_batch_per_round_3round_light')
        except Exception as e:
            results['batch_per_round_error'] = str(e)[:200]
        click_btn(d, '取消', 20)
        time.sleep(1.0)
        set_search(d, '')

        # ---------- D. 深色一套 ----------
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 60)
        js(d, "localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.get(BASE + '/testcases')
        assert wait_body(d, '用例管理', 60)
        time.sleep(2)
        shot(d, '20_list_dark')
        assert open_export(d)
        shot(d, '21_export_dialog_dark')
        click_btn(d, '取消', 15)
        set_search(d, '测试用例_JS172_多轮拒识')
        expand_group(d, '拒识')
        if open_case_drawer(d, 'JS172'):
            assert wait_body(d, '轮次配置', 30)
            time.sleep(1.0)
            click_btn(d, '音频列表', 20)
            time.sleep(1.2)
            shot(d, '22_audio_step_dark')
            click_btn(d, '噪声与干扰', 20)
            time.sleep(1.0)
            shot(d, '23_noise_step_dark')
            click_btn(d, '参考参数', 20)
            time.sleep(2.0)
            shot(d, '24_reference_error_dark')
        d.get(BASE + '/testcases')
        wait_body(d, '用例管理', 60)
        time.sleep(1.0)
        r_dark = open_batch_for('测试用例_JS172_多轮拒识')
        results['batch_rounds_dark'] = r_dark
        shot(d, '25_batch_rounds_dark')

        # ---------- 汇总 Network ----------
        all_logs = fetch_log(d)
        results['fetch_log_summary'] = [
            {'method': e.get('method'), 'url': e.get('url'), 'status': e.get('status')}
            for e in all_logs if '/api/v1' in (e.get('url') or '')][-60:]

    except Exception as e:
        results['ERROR'] = '%s: %s' % (type(e).__name__, e)
        try:
            shot(d, '99_error')
        except Exception:
            pass
    finally:
        try:
            results['console'] = [l.get('message') for l in d.get_log('browser')
                                  if l.get('level') == 'SEVERE'][:10]
        except Exception:
            pass
        d.quit()

    with open(os.path.join(ART, 'results.json'), 'w', encoding='utf-8') as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in results.items() if k not in ('fetch_log_summary',)},
                     ensure_ascii=True, indent=1)[:6000])


if __name__ == '__main__':
    main()
