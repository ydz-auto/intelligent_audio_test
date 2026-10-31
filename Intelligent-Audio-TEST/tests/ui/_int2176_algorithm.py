# -*- coding: utf-8 -*-
"""INT-2176 覆盖 1/2/3/5：算法配置列表与详情、参数策略 CRUD、旧评估策略链移除、
参数列表/映射数据源一致性（docker 15173 + 15000 真实栈，只读真实算法）。

产出：tests/ui/artifacts/int2176/alg/（截图 / 文本 / console / perf / result.json）
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000/api/v1'
USER, PWD = '接线测试_admin', 'JieXianTest@2026'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2176', 'alg')
PROFILE_NAME = '接线测试_走查R4_策略A'
TOKEN = open(os.path.join(HERE, 'artifacts', 'int2176', 'token.txt'), encoding='utf-8').read().strip()

RESULT = {}


def api(method, path, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + TOKEN,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:300]


def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run',
              '--no-default-browser-check']:
        o.add_argument(a)
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
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(60)
    return d


def login(d):
    d.get(BASE + '/login')
    WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    d.find_element(By.ID, 'username').send_keys(USER)
    d.find_element(By.ID, 'password').send_keys(PWD)
    d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
    time.sleep(2)


def ready(d, wait=2.0):
    WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def bundle(d):
    return d.execute_script(
        "return [...document.querySelectorAll('script[src]')].map(s=>s.src.split('/').pop())")


JS_CLICK = r"""
const t = arguments[0];
const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
let els = [...document.querySelectorAll('button, [role=menuitem], [role=tab], a, [role=option]')].filter(vis);
const el = els.find(e => (e.innerText || '').replace(/\s+/g, ' ').trim() === t)
        || els.find(e => (e.innerText || '').includes(t));
if (!el) return {ok: false, n: els.length};
el.scrollIntoView({block: 'center'});
el.click();
return {ok: true, tag: el.tagName, txt: (el.innerText || '').slice(0, 60)};
"""


def click_text(d, text, wait=1.2):
    r = d.execute_script(JS_CLICK, text)
    time.sleep(wait)
    return r


JS_VIS = "const vis=x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0;};"


def dialog_text(d):
    return d.execute_script(
        JS_VIS + "const ds=[...document.querySelectorAll('[role=dialog]')].filter(vis);"
        "return ds.length?ds[ds.length-1].innerText:''")


def body_text(d):
    return d.execute_script('return document.body.innerText')


def shot(d, name, extra=None):
    p = os.path.join(ART, name)
    os.makedirs(p, exist_ok=True)
    d.save_screenshot(os.path.join(p, 'shot.png'))
    open(os.path.join(p, 'text.txt'), 'w', encoding='utf-8').write(body_text(d))
    open(os.path.join(p, 'console.log'), 'w', encoding='utf-8').write(
        '\n'.join(json.dumps(e, ensure_ascii=False) for e in d.get_log('browser')))
    open(os.path.join(p, 'perf.log'), 'w', encoding='utf-8').write(
        '\n'.join(json.dumps(e, ensure_ascii=False) for e in d.get_log('performance')))
    if extra:
        open(os.path.join(p, 'extra.json'), 'w', encoding='utf-8').write(
            json.dumps(extra, ensure_ascii=False, indent=2))


def set_theme(d, mode):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    d.refresh()
    ready(d, 3)
    return d.execute_script(
        "return {dark: document.documentElement.className.includes('dark'), bg: getComputedStyle(document.body).backgroundColor}")


def toast_text(d):
    return d.execute_script(
        "const t=document.querySelector('[data-sonner-toast]'); return t?t.innerText:''")


def wait_toast(d, contains, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        t = toast_text(d)
        if contains in t:
            return t
        time.sleep(0.3)
    return toast_text(d)



def select_in_top_dialog(d, label_text, option_text):
    """在顶层可见 dialog 内按 Label 找 combobox 并选中选项（base-ui Select 门户选项）。"""
    r = d.execute_script(JS_VIS + """
        const ds = [...document.querySelectorAll('[role=dialog]')].filter(vis);
        const dl = ds[ds.length - 1];
        if (!dl) return {ok: false, why: 'no dialog'};
        const lab = [...dl.querySelectorAll('label')].find(l => (l.innerText || '').includes(arguments[0]));
        if (!lab) return {ok: false, why: 'no label'};
        let box = lab.parentElement;
        const combo = box.querySelector('button[role=combobox]');
        if (!combo) return {ok: false, why: 'no combo'};
        combo.click();
        return {ok: true, combo: (combo.innerText || '').slice(0, 30)};
    """, label_text)
    time.sleep(1.0)
    r2 = d.execute_script(JS_VIS + """
        const opts = [...document.querySelectorAll('[role=option]')].filter(vis);
        const el = opts.find(o => (o.innerText || '').trim() === arguments[0])
                || opts.find(o => (o.innerText || '').includes(arguments[0]));
        if (!el) return {ok: false, n: opts.length, txts: opts.map(o => o.innerText)};
        el.click();
        return {ok: true, picked: (el.innerText || '').trim()};
    """, option_text)
    time.sleep(0.8)
    return {'open': r, 'pick': r2}


def net_calls(d):
    out = []
    for e in d.get_log('performance'):
        try:
            m = json.loads(e['message'])['message']
            if m['method'] == 'Network.responseReceived':
                u = m['params']['response']['url']
                if '/api/' in u:
                    out.append({'status': m['params']['response']['status'], 'url': u})
        except Exception:
            pass
    return out


def main():
    os.makedirs(ART, exist_ok=True)
    # ---------- API 基线 ----------
    st_def, defs = api('GET', '/algorithm/definitions?page=1&page_size=200')
    st_one, one = api('GET', '/algorithm/definitions/voice_llm')
    dd = (one or {}).get('data') or {}
    RESULT['api'] = {
        'definitions_status': st_def,
        'definitions_total': ((defs or {}).get('data') or {}).get('total'),
        'detail_status': st_one,
        'type': dd.get('type'), 'name': dd.get('name'), 'status': dd.get('status'),
        'device_params': len(dd.get('device_params') or []),
        'case_params': len(dd.get('case_params') or []),
        'api_params': len(dd.get('api_params') or []),
        'mapping_device': len((dd.get('mappings') or {}).get('device') or []),
        'mapping_api': len((dd.get('mappings') or {}).get('api') or []),
        'mapping_evaluation': len((dd.get('mappings') or {}).get('evaluation') or []),
        'dimension_relations': len(dd.get('dimension_relations') or []),
        'reference_params': len(dd.get('reference_params') or []),
        'detail_keys': sorted(dd.keys()),
        'device_param_sample': (dd.get('device_params') or [{}])[0],
        'detail_bytes': len(json.dumps(one, ensure_ascii=False)),
    }

    d = driver()
    try:
        login(d)
        RESULT['bundle_start'] = bundle(d)

        # ---------- 1. 列表 + 详情 ----------
        d.get(BASE + '/AlgorithmConfig')
        ready(d, 4)
        txt = body_text(d)
        RESULT['list'] = {
            'has_voice_llm': 'voice_llm' in txt,
            'has_count_1': '共 1 个算法' in txt,
            'snippet': [ln for ln in txt.splitlines() if ln.strip()][-14:],
        }
        shot(d, '01-list-light')

        # 打开详情：点击含 voice_llm 的行
        d.execute_script(
            "const tr=[...document.querySelectorAll('tr')].find(r=>r.innerText.includes('voice_llm'));"
            "if(tr){const td=[...tr.querySelectorAll('td')].find(c=>c.innerText.includes('voice_llm'));"
            "(td||tr).click();}")
        WebDriverWait(d, 25).until(lambda x: '评估维度关联' in dialog_text(x))
        time.sleep(2)
        dtxt = dialog_text(d)
        RESULT['detail_dialog'] = {
            'has_basic': '基本信息' in dtxt,
            'has_param_definition': '参数定义' in dtxt,
            'has_param_mapping': '参数映射' in dtxt,
            'has_dim_relation': '评估维度关联' in dtxt,
            'shows_type': 'voice_llm' in dtxt,
            'shows_param_count_20': '20' in dtxt,
            'snippet': dtxt[:600],
        }
        shot(d, '02-detail-light')
        # 切设备参数/用例参数/评估参数页签
        tabs = d.execute_script(
            JS_VIS + "return [...document.querySelectorAll('[role=tab]')].filter(vis).map(t=>t.innerText.replace(/\\s+/g,' ').trim())")
        RESULT['detail_dialog']['tabs'] = tabs
        click_text(d, '用例参数', 1.5)
        RESULT['detail_dialog']['case_tab_rows'] = d.execute_script(
            JS_VIS + "const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();"
            "return dl?dl.querySelectorAll('table tbody tr').length:0")
        click_text(d, '评估参数', 2.0)
        RESULT['detail_dialog']['eval_tab_rows'] = d.execute_script(
            JS_VIS + "const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();"
            "return dl?dl.querySelectorAll('table tbody tr').length:0")
        shot(d, '03-detail-eval-tab-light')
        RESULT['net_detail'] = net_calls(d)
        # 关闭
        d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1.2)

        # ---------- 2. 参数策略 CRUD ----------
        r = click_text(d, '参数策略', 2.0)
        RESULT['open_manager'] = r
        WebDriverWait(d, 20).until(lambda x: '参数策略' in dialog_text(x))
        time.sleep(1.5)
        RESULT['manager_before'] = dialog_text(d)[:500]
        shot(d, '04-manager-empty-light')

        # 新建
        click_text(d, '新建策略', 2.0)
        WebDriverWait(d, 20).until(lambda x: '新建参数策略' in dialog_text(x))
        time.sleep(1)
        RESULT['select_algorithm_type'] = select_in_top_dialog(d, '算法类型', '小艺语音大模型')
        d.find_element(By.ID, 'profile-name').send_keys(PROFILE_NAME)
        d.find_element(By.ID, 'profile-description').send_keys('INT-2176 走查自建策略，验收后删除')
        inputs = d.find_elements(By.CSS_SELECTOR, "input[placeholder='param_code']")
        inputs[0].send_keys('r4_in_text')
        # 输出字段：第二个「新增字段」按钮
        d.execute_script(
            "const bs=[...document.querySelectorAll('button')].filter(b=>(b.innerText||'').includes('新增字段'));"
            "if(bs[1]) bs[1].click();")
        time.sleep(0.8)
        inputs = d.find_elements(By.CSS_SELECTOR, "input[placeholder='param_code']")
        inputs[-1].send_keys('r4_out_text')
        fp = d.find_elements(By.CSS_SELECTOR, "input[placeholder='data.items[0].text']")
        if fp:
            fp[-1].send_keys('data.result')
        # 映射行
        click_text(d, '新增映射', 0.8)
        src = d.find_elements(By.CSS_SELECTOR, "input[placeholder='api 字段']")
        tgt = d.find_elements(By.CSS_SELECTOR, "input[placeholder='维度字段']")
        if src:
            src[-1].send_keys('r4_out_text')
        if tgt:
            tgt[-1].send_keys('r4_target')
        shot(d, '05-form-filled-light')
        click_text(d, '保存', 1.0)
        toast = wait_toast(d, '参数策略已创建', 20)
        if '已创建' not in toast:
            time.sleep(2)
            toast = toast_text(d)
            RESULT['create_failed_toast'] = toast
            shot(d, '06a-create-failed')
            raise SystemExit('create failed: ' + toast)
        RESULT['create_toast'] = toast
        shot(d, '06-manager-after-create-light')

        # 回读
        st_list, lst = api('GET', '/algorithm/param-profiles')
        profiles = ((lst or {}).get('data') or {}).get('profiles') or []
        mine = [p for p in profiles if p.get('name') == PROFILE_NAME]
        RESULT['create_readback_list'] = {
            'status': st_list, 'total': ((lst or {}).get('data') or {}).get('total'),
            'found': len(mine), 'profile': mine[0] if mine else None}
        if mine:
            pid = mine[0]['id']
            st_g, got = api('GET', f'/algorithm/param-profiles/{pid}')
            gd = (got or {}).get('data') or {}
            RESULT['create_readback_detail'] = {
                'status': st_g, 'id': gd.get('id'), 'scope': gd.get('scope'),
                'algorithm_type': gd.get('algorithm_type'), 'status_field': gd.get('status'),
                'description': gd.get('description'),
                'params': [{'code': p.get('param_code'), 'dir': p.get('direction'),
                            'type': p.get('param_type'), 'field_path': p.get('field_path')}
                           for p in (gd.get('params') or [])],
                'mappings': [{'source': m.get('source_param'), 'target': m.get('target_param')}
                             for m in (gd.get('mappings') or [])],
            }
        else:
            pid = None

        # 关闭管理弹窗（Esc）
        d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1)

        # 深色：刷新后重开管理弹窗
        RESULT['theme_dark'] = set_theme(d, 'dark')
        click_text(d, '参数策略', 2.5)
        WebDriverWait(d, 20).until(lambda x: PROFILE_NAME in dialog_text(x))
        time.sleep(1)
        shot(d, '07-manager-dark')

        # 编辑（深色下）：改描述 + 状态
        d.execute_script(
            JS_VIS + "const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();"
            "const row=[...dl.querySelectorAll('tr')].find(r=>r.innerText.includes(arguments[0]));"
            "if(row){const b=[...row.querySelectorAll('button')].find(b=>b.innerText.trim()==='编辑');if(b)b.click();}",
            PROFILE_NAME)
        WebDriverWait(d, 20).until(lambda x: '编辑参数策略' in dialog_text(x))
        time.sleep(1.5)
        desc = d.find_element(By.ID, 'profile-description')
        desc.clear()
        desc.send_keys('INT-2176 已编辑：描述更新')
        shot(d, '08-edit-form-dark')
        click_text(d, '保存', 1.0)
        RESULT['edit_toast'] = wait_toast(d, '参数策略已更新', 20)
        if pid:
            st_g2, got2 = api('GET', f'/algorithm/param-profiles/{pid}')
            g2 = (got2 or {}).get('data') or {}
            RESULT['edit_readback'] = {'status': st_g2, 'description': g2.get('description'),
                                       'name': g2.get('name'), 'scope': g2.get('scope')}
        shot(d, '09-manager-after-edit-dark')

        # 删除
        d.execute_script(
            JS_VIS + "const dl=[...document.querySelectorAll('[role=dialog]')].filter(vis).pop();"
            "const row=[...dl.querySelectorAll('tr')].find(r=>r.innerText.includes(arguments[0]));"
            "if(row){const b=[...row.querySelectorAll('button')].find(b=>b.innerText.trim()==='删除');if(b)b.click();}",
            PROFILE_NAME)
        time.sleep(1.2)
        RESULT['delete_dialog'] = dialog_text(d)[:300]
        click_text(d, '确认删除', 1.0)
        RESULT['delete_toast'] = wait_toast(d, '参数策略已删除', 20)
        st_after, lst_after = api('GET', '/algorithm/param-profiles')
        profiles_after = ((lst_after or {}).get('data') or {}).get('profiles') or []
        RESULT['delete_readback'] = {
            'status': st_after,
            'still_listed': any(p.get('name') == PROFILE_NAME for p in profiles_after),
            'total': ((lst_after or {}).get('data') or {}).get('total'),
        }
        if pid:
            st_g3, got3 = api('GET', f'/algorithm/param-profiles/{pid}')
            RESULT['delete_readback']['detail_status'] = st_g3
            RESULT['delete_readback']['detail'] = got3 if st_g3 != 200 else (got3 or {}).get('data')
        shot(d, '10-manager-after-delete-dark')

        # 关闭弹窗，回浅色
        d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1)
        RESULT['theme_light'] = set_theme(d, 'light')

        # ---------- 3. 旧评估策略链移除：编辑 Sheet 无入口 ----------
        d.get(BASE + '/AlgorithmConfig')
        ready(d, 3)
        d.execute_script(
            "const tr=[...document.querySelectorAll('tr')].find(r=>r.innerText.includes('voice_llm'));"
            "if(tr){const b=[...tr.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').includes('操作'));if(b)b.click();}")
        time.sleep(1.2)
        r = click_text(d, '编辑', 3.0)
        RESULT['open_edit_sheet'] = r
        time.sleep(3)
        sheet = body_text(d)
        # Sheet 内滚动容器
        RESULT['edit_sheet'] = {
            'has_old_strategy_entry': '评估策略' in sheet,
            'has_eval_params_section': '评估参数映射' in sheet,
            'has_assoc_dim': '评估维度' in sheet,
            'snippet': sheet[-1200:],
        }
        shot(d, '11-edit-sheet-light')
        RESULT['bundle_end'] = bundle(d)
        RESULT['console_severe'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
    finally:
        try:
            d.quit()
        except Exception:
            pass
    open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8').write(
        json.dumps(RESULT, ensure_ascii=False, indent=2))
    print(json.dumps(RESULT, ensure_ascii=False, indent=2)[:6000])


if __name__ == '__main__':
    main()
