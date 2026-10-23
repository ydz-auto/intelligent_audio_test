# -*- coding: utf-8 -*-
"""INT-1569 验收：算法详情弹窗「参数定义」设备/API 页签「默认值」列。

环境：本 run 自建 nginx 旁路容器 http://127.0.0.1:15269（服务交付提交 ae44daff 构建的 dist，
容器接入 intelligent-audio-test_default 网络，/api 反代 api_gateway:5000）→ docker 真实库栈 :15000
（主库 intelligent_audio_test，AUTH_MODE=off）。

覆盖：
1. 真实库 /health = intelligent_audio_test（防串库）。
2. voice_llm 详情的设备/API 页签：表头 7 列且含「默认值」，每行 7 格，空值「—」；用例参数页签无回归。
3. 自建「接线测试_」算法（设备参数 lang_1569 默认值 zh）→ 发布 → GET 回读 default_value → 详情页签回显 zh。
4. 清理：DELETE 自建算法，列表与接口回读均消失。
5. 浅色 / 深色截图。
写数据纪律：只建「接线测试_」前缀算法，run 末删除。
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15269')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1569')
os.makedirs(ART, exist_ok=True)
THEME_KEY = 'iatp:theme:v1:mode'

TS = time.strftime('%H%M%S')
NEW_TYPE = f'qa_int1569_verify_{TS}'
NEW_NAME = f'接线测试_默认值_{TS}'
PARAM_CODE = 'lang_1569'
PARAM_DEFAULT = 'zh'

EVID = {'checks': [], 'api': {}, 'network': []}


def log(*a):
    print(*a, flush=True)


def check(name, ok, detail=''):
    EVID['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:4000]})
    log(('PASS ' if ok else 'FAIL ') + name + ((' | ' + str(detail)[:800]) if detail else ''))
    if not ok:
        raise AssertionError(name + ' | ' + str(detail)[:800])


HOOK_JS = r"""
(function(){
  if (window.__int1569_installed) return;
  window.__int1569_installed = true;
  window.__reqLog = [];
  var origFetch = window.fetch.bind(window);
  window.fetch = function(input, init){
    var url = (typeof input === 'string') ? input : (input && input.url) || '';
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var body = (init && typeof init.body === 'string') ? init.body : null;
    return origFetch(input, init).then(function(res){
      try {
        var clone = res.clone();
        clone.text().then(function(t){
          window.__reqLog.push({url:String(url), method:method, status:res.status,
                                reqBody:body, respBody:(t||'').slice(0,60000)});
        }).catch(function(){});
      } catch(e) {}
      return res;
    }).catch(function(e){
      window.__reqLog.push({url:String(url), method:method, status:'ERR',
                            reqBody:body, respBody:String(e)});
      throw e;
    });
  };
})();
"""


def new_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = [os.path.join(cache_root, v, 'chromedriver.exe') for v in os.listdir(cache_root)]
    cands = [c for c in cands if os.path.isfile(c)]
    d = webdriver.Chrome(options=o, service=Service(executable_path=sorted(cands)[-1]))
    d.set_page_load_timeout(90)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': HOOK_JS})
    return d


def js(d, script, *args):
    return d.execute_script(script, *args)


def js_click(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.15)
    d.execute_script("arguments[0].click();", el)


def find(d, xpath, timeout=20, visible=True):
    def cond(dd):
        for e in dd.find_elements(By.XPATH, xpath):
            if (not visible) or e.is_displayed():
                return e
        return False
    return WebDriverWait(d, timeout, poll_frequency=0.25).until(cond)


def find_all(d, xpath, visible=True):
    return [e for e in d.find_elements(By.XPATH, xpath) if (not visible) or e.is_displayed()]


def body_text(d):
    return d.execute_script('return document.body.innerText') or ''


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('SHOT', p)
    return p


def api_call(method, path, body=None):
    url = API + path
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw}


def health():
    with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as r:
        return json.loads(r.read().decode())


def wait_list_ready(d, name='小艺语音大模型', timeout=30):
    find(d, f"//button[@aria-label='算法 {name} 的操作']", timeout=timeout)


def open_row_menu(d, name):
    btn = find(d, f"//button[@aria-label='算法 {name} 的操作']")
    js_click(d, btn)
    find(d, "//*[@role='menuitem']", timeout=10)


def click_menu_item(d, label):
    for it in find_all(d, "//*[@role='menuitem']"):
        if label in (it.text or ''):
            js_click(d, it)
            return
    raise AssertionError('行菜单项未找到: ' + label)


def dialog(d, timeout=20):
    return find(d, "//div[@role='dialog' or @role='alertdialog']", timeout=timeout)


def open_detail(d, name):
    open_row_menu(d, name)
    click_menu_item(d, '详情')
    dl = dialog(d)
    WebDriverWait(d, 20).until(
        lambda dd: '算法定义与参数映射只读详情' in (dl.text or ''))
    time.sleep(0.8)
    return dl


def params_table(d):
    """参数定义 section 内当前可见的表。"""
    tables = find_all(
        d,
        "//section[@aria-labelledby='algorithm-params-title']//table", visible=True)
    assert len(tables) == 1, f'参数定义区可见表数应为 1，实际 {len(tables)}'
    return tables[0]


def table_headers(table):
    return [(th.text or '').strip() for th in table.find_elements(By.XPATH, './/thead//th')]


def table_rows(table):
    out = []
    for tr in table.find_elements(By.XPATH, './/tbody/tr'):
        out.append([(td.text or '').strip() for td in tr.find_elements(By.XPATH, './td')])
    return out


def click_tab(d, label_regex):
    for el in find_all(d, "//button[@role='tab']"):
        txt = el.text or ''
        if re.search(label_regex, txt):
            js_click(d, el)
            time.sleep(0.6)
            return txt
    raise AssertionError('页签未找到: ' + label_regex)


def set_theme(d, mode):
    js(d, "localStorage.setItem(arguments[0], arguments[1])", THEME_KEY, mode)
    d.refresh()
    WebDriverWait(d, 30).until(
        lambda dd: dd.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def main():
    t0 = time.time()
    d = new_driver()
    try:
        # ── 0. 防串库 ──
        h = health()
        check('0 真实库 /health database',
              h.get('database') == 'intelligent_audio_test', json.dumps(h, ensure_ascii=False))

        # ── 1. 基线接口回读 ──
        code, lst = api_call('GET', '/algorithm/definitions')
        items = (lst.get('data') or {}).get('items') or lst.get('data') or []
        if isinstance(items, dict):
            items = items.get('items') or []
        EVID['api']['list_total'] = len(items)
        voice = next((i for i in items if i.get('type') == 'voice_llm'), None)
        check('1a GET /algorithm/definitions 含 voice_llm',
              voice is not None, f'total={len(items)} types={[i.get("type") for i in items][:6]}')
        dp = voice.get('device_params') or []
        ap = voice.get('api_params') or []
        cp = voice.get('case_params') or []
        check('1b voice_llm 设备/API 参数 default_value 现状',
              all((p.get('default_value') in (None, '')) for p in dp[:60]),
              f'device={len(dp)} api={len(ap)} case={len(cp)} '
              f'defaults={[p.get("default_value") for p in dp[:12]]}')

        # ── 2. 列表 + 详情（浅色）──
        d.get(BASE + '/AlgorithmConfig')
        WebDriverWait(d, 40).until(lambda dd: dd.execute_script('return document.readyState') == 'complete')
        wait_list_ready(d)
        txt = body_text(d)
        check('2a 算法列表渲染', '小艺语音大模型' in txt and re.search(r'共 \d+ 个算法', txt) is not None,
              txt[:300])

        open_detail(d, '小艺语音大模型')
        dl_txt = dialog(d).text or ''
        check('2b 详情弹窗打开', '算法定义与参数映射只读详情' in dl_txt, dl_txt[:300])

        dev_tab = click_tab(d, r'^设备参数（\d+）')
        check('2c 设备参数页签计数与接口一致',
              f'设备参数（{len(dp)}）' in dev_tab, f'tab={dev_tab} api_device={len(dp)}')
        headers = table_headers(params_table(d))
        check('2d 设备参数表头 7 列含「默认值」',
              headers == ['参数代码', '参数名称', '类型', '方向', '必填', '默认值', '帮助文本'], headers)
        rows = table_rows(params_table(d))
        check('2e 设备参数每行 7 格且列数一致',
              len(rows) == len(dp) and all(len(r) == 7 for r in rows),
              f'rows={len(rows)} widths={[len(r) for r in rows]}')
        check('2f 设备参数默认值列空值渲染「—」',
              all(r[5] == '—' for r in rows), [r[5] for r in rows][:12])
        shot(d, 'int1569_light_device')

        api_tab = click_tab(d, r'^API参数（\d+）')
        check('2g API参数页签计数与接口一致', f'API参数（{len(ap)}）' in api_tab,
              f'tab={api_tab} api_api={len(ap)}')
        headers = table_headers(params_table(d))
        check('2h API参数表头 7 列含「默认值」',
              headers == ['参数代码', '参数名称', '类型', '方向', '必填', '默认值', '帮助文本'], headers)
        rows = table_rows(params_table(d))
        check('2i API参数每行 7 格且列数一致',
              len(rows) == len(ap) and all(len(r) == 7 for r in rows),
              f'rows={len(rows)} widths={[len(r) for r in rows]}')
        check('2j API参数默认值列空值渲染「—」', all(r[5] == '—' for r in rows),
              [r[5] for r in rows][:12])
        shot(d, 'int1569_light_api')

        click_tab(d, r'^用例参数（\d+）')
        headers = table_headers(params_table(d))
        check('2k 用例参数页签无回归（6 列，默认值在位）',
              headers == ['参数代码', '参数名称', '类型', '适用范围', '必填', '默认值'], headers)
        rows = table_rows(params_table(d))
        if cp:
            check('2l 用例参数行宽与表头一致', all(len(r) == 6 for r in rows),
                  f'rows={len(rows)} widths={[len(r) for r in rows]}')
        else:
            check('2l 用例参数空态', rows == [['无用例参数']], rows)

        # ── 3. 深色截图 ──
        click_tab(d, r'^设备参数（\d+）')
        d.execute_script("arguments[0].click();", d.find_element(By.XPATH, "//button[@aria-label='Close' or @aria-label='关闭']")) if find_all(d, "//button[@aria-label='Close' or @aria-label='关闭']") else None
        set_theme(d, 'dark')
        cls = d.find_element(By.TAG_NAME, 'html').get_attribute('class') or ''
        check('3a 深色主题生效', 'dark' in cls, cls)
        wait_list_ready(d)
        open_detail(d, '小艺语音大模型')
        headers = table_headers(params_table(d))
        rows = table_rows(params_table(d))
        check('3b 深色下设备参数 7 列 + 默认值「—」',
              headers[-2] == '默认值' and all(len(r) == 7 and r[5] == '—' for r in rows),
              f'{headers} widths={[len(r) for r in rows]}')
        shot(d, 'int1569_dark_device')
        # 关闭弹窗 + 还原浅色
        for el in find_all(d, "//button[@aria-label='Close' or @aria-label='关闭']"):
            js_click(d, el)
            break
        set_theme(d, 'light')

        # ── 4. UI 新建自建算法（设备参数带默认值）→ 发布 ──
        wait_list_ready(d)
        js_click(d, find(d, "//button[normalize-space()='新建算法']"))
        WebDriverWait(d, 20).until(lambda dd: '新建算法' in body_text(dd))
        time.sleep(1.0)

        def edit_field(xpath, value, timeout=20):
            el = find(d, xpath, timeout=timeout)
            tag = el.tag_name.lower()
            proto = 'HTMLTextAreaElement' if tag == 'textarea' else 'HTMLInputElement'
            js(d, "const s = Object.getOwnPropertyDescriptor(window.%s.prototype,'value').set;"
                   "s.call(arguments[0], arguments[1]);"
                   "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));" % proto, el, value)
            time.sleep(0.5)

        edit_field("//input[@id='algo-type']", NEW_TYPE)
        edit_field("//input[@id='algo-name']", NEW_NAME)
        js_click(d, find(d, "//button[@aria-label='添加参数']"))
        find(d, "//*[@role='menuitem'][contains(., '添加设备参数')]", timeout=10)
        js_click(d, find(d, "//*[@role='menuitem'][contains(., '添加设备参数')]"))
        WebDriverWait(d, 10).until(
            lambda dd: len(find_all(dd, "//*[@id='algorithm-mutate-form']//tbody/tr")) == 1)
        edit_field("//*[@id='algorithm-mutate-form']//tbody/tr[1]//input[@placeholder='param_code']",
                   PARAM_CODE)
        edit_field("//*[@id='algorithm-mutate-form']//tbody/tr[1]//input[@placeholder='如：输入音频']",
                   '语言')
        edit_field("//*[@id='algorithm-mutate-form']//tbody/tr[1]//input[@aria-label='默认值']",
                   PARAM_DEFAULT)
        js_click(d, find(d, "//button[normalize-space()='发布']"))
        WebDriverWait(d, 60).until(lambda dd: NEW_NAME in body_text(dd))
        time.sleep(1.5)
        check('4a UI 新建发布成功，列表出现自建算法', NEW_NAME in body_text(d), NEW_NAME)

        code, det = api_call('GET', f'/algorithm/definitions/{NEW_TYPE}')
        data = det.get('data') or det
        got = (data.get('device_params') or [{}])[0].get('default_value')
        EVID['api']['created'] = {'status': code, 'default_value': got,
                                  'param_code': (data.get('device_params') or [{}])[0].get('param_code')}
        check('4b GET 回读 device_params[0].default_value = zh', code == 200 and got == PARAM_DEFAULT,
              json.dumps(EVID['api']['created'], ensure_ascii=False))

        # ── 5. 详情页签回显自建默认值 ──
        d.refresh()
        WebDriverWait(d, 40).until(lambda dd: dd.execute_script('return document.readyState') == 'complete')
        wait_list_ready(d, NEW_NAME, timeout=40)
        open_detail(d, NEW_NAME)
        headers = table_headers(params_table(d))
        rows = table_rows(params_table(d))
        check('5a 自建算法详情设备参数 7 列', headers == ['参数代码', '参数名称', '类型', '方向', '必填',
                                                       '默认值', '帮助文本'], headers)
        check('5b 自建算法设备参数行 7 格且默认值列 = zh',
              len(rows) == 1 and len(rows[0]) == 7 and rows[0][5] == PARAM_DEFAULT
              and rows[0][0] == PARAM_CODE, rows)
        shot(d, 'int1569_selfbuilt_light_device')

        # 深色下的自建算法回显
        for el in find_all(d, "//button[@aria-label='Close' or @aria-label='关闭']"):
            js_click(d, el)
            break
        set_theme(d, 'dark')
        wait_list_ready(d, NEW_NAME, timeout=40)
        open_detail(d, NEW_NAME)
        rows = table_rows(params_table(d))
        check('5c 深色下自建算法默认值回显 zh',
              len(rows) == 1 and len(rows[0]) == 7 and rows[0][5] == PARAM_DEFAULT, rows)
        shot(d, 'int1569_selfbuilt_dark_device')

        # ── 6. Network 证据 ──
        reqs = js(d, 'return (window.__reqLog||[]).slice(-400)')
        alg = [r for r in reqs if '/api/v1/algorithm/definitions' in r.get('url', '')]
        EVID['network'] = [{'method': r['method'], 'url': r['url'], 'status': r['status']}
                           for r in alg][-15:]
        check('6a Network 有真实 /algorithm/definitions 请求',
              any(r['status'] == 200 for r in alg), EVID['network'])

    finally:
        # ── 7. 清理自建算法 ──
        try:
            code, body = api_call('DELETE', f'/algorithm/definitions/{NEW_TYPE}')
            EVID['api']['delete'] = {'status': code, 'body': body}
            code2, _ = api_call('GET', f'/algorithm/definitions/{NEW_TYPE}')
            code3, lst2 = api_call('GET', '/algorithm/definitions')
            items2 = (lst2.get('data') or {}).get('items') or []
            if isinstance(items2, dict):
                items2 = items2.get('items') or []
            EVID['api']['after_cleanup_total'] = len(items2)
            check('7a 自建算法删除后 GET 不再返回', code2 != 200, f'delete={code} get={code2}')
            check('7b 列表总数回到基线', len(items2) == EVID['api'].get('list_total'),
                  f'before={EVID["api"].get("list_total")} after={len(items2)}')
        except Exception as e:  # noqa: BLE001
            log('CLEANUP FAIL', repr(e))
            EVID['api']['delete_error'] = repr(e)

        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(EVID, f, ensure_ascii=False, indent=2)
        log('ELAPSED %.1fs' % (time.time() - t0))
        try:
            d.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
    fails = [c for c in EVID['checks'] if not c['ok']]
    log('CHECKS %d, FAILS %d' % (len(EVID['checks']), len(fails)))
    sys.exit(1 if fails else 0)
