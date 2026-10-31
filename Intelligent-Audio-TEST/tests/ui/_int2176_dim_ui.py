# -*- coding: utf-8 -*-
"""INT-2176 覆盖 6 补证：评估维度「新增/编辑」抽屉 UI 实测（输入参数 + 输出字段），
保存 → GET 回读一致；维度增删后算法详情同步。

环境：docker 15173（React）+ 15000（真实栈，库 intelligent_audio_test）。
自建：维度「接线测试_走查R4_维度UI」，算法「接线测试_走查R4_维度同步算法」；run 内按 id/type 删除。

产出：tests/ui/artifacts/int2176/dim/（截图 / result.json / page 文本）
"""
import importlib.util
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2176', 'dim')
SHOTS = os.path.join(ART, 'shots')
os.makedirs(SHOTS, exist_ok=True)

spec = importlib.util.spec_from_file_location('boot', os.path.join(HERE, '_int2176_boot.py'))
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)

BASE = boot.BASE
API = 'http://127.0.0.1:15000/api/v1'
TOK = open(os.path.join(HERE, 'artifacts', 'int2176', 'token.txt'), encoding='utf-8').read().strip()

DIM_NAME = '接线测试_走查R4_维度UI'
ALGO_NAME = '接线测试_走查R4_维度同步算法'
ALGO_TYPE = 'wiring_r4_dimsync_2176'

RES = {'dim_name': DIM_NAME, 'algo_type': ALGO_TYPE}


def api(method, path, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + TOK,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:400]


def dump():
    with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump(RES, f, ensure_ascii=False, indent=2)


JS_ROOT = r"""
const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const ds = [...document.querySelectorAll('[role=dialog]')].filter(d => !d.closest('[aria-hidden=true]') && vis(d));
const root = ds.length ? ds[ds.length - 1] : document.body;
"""

JS_SET = JS_ROOT + r"""
const key = arguments[0], val = arguments[1];
const el = [...root.querySelectorAll('input, textarea')].filter(vis)
  .find(e => e.getAttribute('aria-label') === key || e.getAttribute('placeholder') === key || e.id === key);
if (!el) return {ok: false, key};
const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val);
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return {ok: true, key, read: el.value};
"""

JS_GET = JS_ROOT + r"""
const key = arguments[0];
const el = [...root.querySelectorAll('input, textarea')].filter(vis)
  .find(e => e.getAttribute('aria-label') === key || e.getAttribute('placeholder') === key || e.id === key);
return el ? el.value : null;
"""

JS_CLICK = JS_ROOT + r"""
const key = arguments[0];
const els = [...root.querySelectorAll('button, [role=tab], a')].filter(vis);
const norm = s => (s || '').replace(/\s+/g, '').trim();
const el = els.find(e => norm(e.innerText) === norm(key))
        || els.find(e => (e.getAttribute('aria-label') || '') === key)
        || els.find(e => norm(e.innerText).includes(norm(key)));
if (!el) return {ok: false, count: els.length};
el.scrollIntoView({block: 'center'});
el.click();
return {ok: true, txt: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60)};
"""

JS_CLICK_PAGE = r"""
const key = arguments[0];
const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const els = [...document.querySelectorAll('button, [role=menuitem], a')].filter(vis)
  .filter(e => !e.closest('[aria-hidden=true]'));
const norm = s => (s || '').replace(/\s+/g, '').trim();
const el = els.find(e => norm(e.innerText) === norm(key))
        || els.find(e => (e.getAttribute('aria-label') || '') === key)
        || els.find(e => norm(e.innerText).includes(norm(key)));
if (!el) return {ok: false};
el.scrollIntoView({block: 'center'}); el.click();
return {ok: true, txt: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60)};
"""

JS_TOASTS = r"""
const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
return [...document.querySelectorAll('[data-sonner-toast], [role=status]')].filter(vis)
  .map(t => (t.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
"""

JS_DRAWER_TEXT = JS_ROOT + r"""
return root === document.body ? '' : (root.innerText || '');
"""


def set_in(d, key, val):
    r = d.execute_script(JS_SET, key, val)
    time.sleep(0.15)
    return r


def click_in(d, text, wait=1.0):
    r = d.execute_script(JS_CLICK, text)
    time.sleep(wait)
    return r


def click_page(d, text, wait=1.0):
    r = d.execute_script(JS_CLICK_PAGE, text)
    time.sleep(wait)
    return r


def toasts(d):
    return d.execute_script(JS_TOASTS)


def drawer_text(d):
    return d.execute_script(JS_DRAWER_TEXT)


def shot(d, name, theme='light'):
    p = os.path.join(SHOTS, name + ('-dark' if theme == 'dark' else '-light') + '.png')
    d.save_screenshot(p)
    return p


def login(d):
    d.get(BASE + '/login')
    WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    d.find_element(By.ID, 'username').send_keys(boot.USER)
    d.find_element(By.ID, 'password').send_keys(boot.PWD)
    d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
    time.sleep(2)


def go_evaluation(d):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    d.get('about:blank')
    d.get(BASE + '/Evaluation')
    wait_list(d)


def wait_list(d, timeout=60):
    WebDriverWait(d, timeout).until(
        lambda x: '新增维度' in (x.execute_script('return document.body.innerText') or ''))
    time.sleep(3)


def search_dim(d, name):
    box = d.execute_script(JS_ROOT + r"""
const key = '搜索评估维度';
const el = [...root.querySelectorAll('input')].filter(vis).find(e => e.getAttribute('aria-label') === key);
return el ? true : false;
""")
    if not box:
        return {'ok': False, 'why': 'no search box'}
    d.execute_script(JS_ROOT + r"""
const key = '搜索评估维度', val = arguments[0];
const el = [...root.querySelectorAll('input')].filter(vis).find(e => e.getAttribute('aria-label') === key);
const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
set.call(el, val); el.dispatchEvent(new Event('input', {bubbles: true}));
""", name)
    time.sleep(3)
    return {'ok': True}


def fill_new_dimension(d):
    # 基本信息：维度名称
    RES['fill_name'] = set_in(d, '如：识别准确率', DIM_NAME)
    # API 配置页签
    RES['tab_api'] = click_in(d, 'API配置', 1.8)
    # 输入参数：新增一行并填写
    RES['add_input'] = click_in(d, '添加输入', 1.0)
    RES['in3_code'] = set_in(d, '输入参数键名 3', 'r4_in_audio')
    RES['in3_name'] = set_in(d, '输入显示标签 3', '走查音频输入')
    RES['in3_help'] = set_in(d, '输入描述 3', 'INT-2176 UI 实测输入参数')
    # 输出字段：新增一行并填写
    RES['add_output'] = click_in(d, '添加字段', 1.0)
    RES['out1_code'] = set_in(d, '输出字段代码 1', 'r4_score')
    RES['out1_name'] = set_in(d, '输出显示名 1', '走查得分')
    RES['out1_path'] = set_in(d, '输出提取路径 1', 'data.result.score')
    time.sleep(1.0)
    RES['drawer_before_save'] = drawer_text(d)[:1500]


def find_dim_id(name):
    st, body = api('GET', '/evaluation/dimensions?page=1&per_page=100&search=' +
                   urllib.parse.quote(name))
    RES['list_search'] = {'status': st, 'total': (body or {}).get('data', {}).get('total')}
    items = (body or {}).get('data', {}).get('items') or []
    hit = [x for x in items if x.get('name') == name]
    return (hit[0]['id'] if hit else None)


def verify_detail(dim_id):
    st, body = api('GET', f'/evaluation/dimensions/{dim_id}')
    dt = (body or {}).get('data') or {}
    RES['detail_get'] = {
        'status': st,
        'id': dt.get('id'),
        'name': dt.get('name'),
        'required_inputs': dt.get('required_inputs'),
        'output_fields': dt.get('output_fields'),
    }
    return st, dt


def open_edit_drawer(d, name):
    search_dim(d, name)
    r = d.execute_script(JS_CLICK_PAGE, f'编辑维度 {name}')
    time.sleep(2.5)
    return r


def open_algo_detail(d, algo_name):
    d.get('about:blank')
    d.get(BASE + '/AlgorithmConfig')
    WebDriverWait(d, 60).until(lambda x: algo_name in (x.execute_script('return document.body.innerText') or ''))
    time.sleep(2)
    r = d.execute_script("""
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const tr = [...document.querySelectorAll('tr')].filter(vis)
        .find(x => (x.innerText || '').includes(arguments[0]));
      if (!tr) return {ok: false};
      tr.click(); return {ok: true};
    """, algo_name)
    time.sleep(3)
    txt = d.execute_script(JS_ROOT + r"""
const t = (root.innerText || '');
const i = t.indexOf('评估维度关联');
return {dialog: t.length, section: i >= 0 ? t.slice(i, i + 600) : null};
""")
    return {'clicked': r, 'detail': txt}


def main():
    d = boot.driver()
    try:
        login(d)
        go_evaluation(d)
        RES['list_total'] = api('GET', '/evaluation/dimensions?page=1&per_page=1')[1]['data']['total']

        # ── 1. 新增维度（UI）──
        RES['open_new'] = d.execute_script("""
          const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
          const b = [...document.querySelectorAll('button')].filter(vis)
            .find(x => (x.innerText || '').replace(/\\s+/g, '').includes('新增维度'));
          if (!b) return {ok: false};
          b.click(); return {ok: true};
        """)
        time.sleep(2.5)
        fill_new_dimension(d)
        RES['shot_drawer_api_light'] = shot(d, 'dim-01-new-drawer-api-inputs-outputs')
        # 保存
        RES['save_click'] = click_in(d, '保存', 1.5)
        toasts_new = []
        for _ in range(20):
            toasts_new += toasts(d)
            if any('添加成功' in t for t in toasts_new):
                break
            time.sleep(0.5)
        RES['save_toasts'] = toasts_new
        time.sleep(2)
        dump()

        dim_id = find_dim_id(DIM_NAME)
        RES['dim_id'] = dim_id
        if dim_id:
            st, dt = verify_detail(dim_id)
            RES['create_readback_ok'] = bool(
                st == 200
                and any(x.get('param_code') == 'r4_in_audio' for x in (dt.get('required_inputs') or []))
                and any(x.get('param_code') == 'r4_score' and x.get('field_path') == 'data.result.score'
                        for x in (dt.get('output_fields') or [])))
            dump()

        # ── 2. 编辑抽屉 UI 反填 + 修改保存 ──
        go_evaluation(d)
        RES['edit_open'] = open_edit_drawer(d, DIM_NAME)
        time.sleep(1.5)
        RES['edit_name_value'] = d.execute_script(JS_GET, '如：识别准确率')
        RES['edit_tab_api'] = click_in(d, 'API配置', 1.8)
        RES['edit_prefill'] = {
            'in3_code': d.execute_script(JS_GET, '输入参数键名 3'),
            'in3_name': d.execute_script(JS_GET, '输入显示标签 3'),
            'in1_code': d.execute_script(JS_GET, '输入参数键名 1'),
            'out1_code': d.execute_script(JS_GET, '输出字段代码 1'),
            'out1_path': d.execute_script(JS_GET, '输出提取路径 1'),
        }
        RES['shot_edit_prefill_light'] = shot(d, 'dim-02-edit-prefill-api')
        # 修改输出字段代码后保存
        RES['edit_out_mutate'] = set_in(d, '输出字段代码 1', 'r4_score2')
        time.sleep(0.8)
        RES['edit_save_click'] = click_in(d, '保存', 1.5)
        toasts_edit = []
        for _ in range(20):
            toasts_edit += toasts(d)
            if any('更新成功' in t for t in toasts_edit):
                break
            time.sleep(0.5)
        RES['edit_toasts'] = toasts_edit
        time.sleep(2)
        if dim_id:
            st, dt = verify_detail(dim_id)
            outs = dt.get('output_fields') or []
            RES['edit_readback_ok'] = bool(
                st == 200
                and any(x.get('param_code') == 'r4_score2' for x in outs)
                and any(x.get('param_code') == 'r4_in_audio' for x in (dt.get('required_inputs') or [])))
        dump()

        # ── 3. 深色抽屉截图 ──
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.get('about:blank')
        d.get(BASE + '/Evaluation')
        wait_list(d)
        RES['dark_theme'] = d.execute_script(
            "return {cls: document.documentElement.className, bg: getComputedStyle(document.body).backgroundColor};")
        open_edit_drawer(d, DIM_NAME)
        click_in(d, 'API配置', 1.8)
        time.sleep(1.0)
        RES['shot_edit_prefill_dark'] = shot(d, 'dim-02-edit-prefill-api', 'dark')
        click_in(d, '基本信息', 1.2)
        RES['shot_edit_basic_dark'] = shot(d, 'dim-03-edit-basic', 'dark')
        dump()

        # ── 4. 算法详情同步：建自建算法并关联该维度 → 详情可见 ──
        assoc_ok = False
        if dim_id:
            body = {
                'type': ALGO_TYPE, 'name': ALGO_NAME, 'groupId': None, 'displayOrder': 0,
                'status': 'online', 'description': 'INT-2176 维度同步验收（run 内删除）',
                'deviceParams': [], 'caseParams': [], 'referenceParams': [],
                'mappings': {'device': [], 'evaluation': []},
                'associated_dimensions': [
                    {'dimension_id': dim_id, 'weight': 1.0, 'is_default': True}
                ],
            }
            st, res = api('POST', '/algorithm/definitions', body)
            RES['algo_create'] = {'status': st, 'msg': (res or {}).get('message') if isinstance(res, dict) else str(res)[:200]}
            st, res = api('GET', f'/algorithm/definitions/{ALGO_TYPE}')
            rels = ((res or {}).get('data') or {}).get('dimension_relations') or []
            RES['algo_relations_after_create'] = rels
            assoc_ok = any(int(x.get('dimension_id') or 0) == int(dim_id) for x in rels)

        if assoc_ok:
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
            go_light_algo(d)
            RES['algo_detail_before_delete'] = open_algo_detail(d, ALGO_NAME)
            RES['shot_algo_detail_before'] = shot(d, 'dim-04-algo-detail-assoc')
            RES['algo_detail_before_has_name'] = DIM_NAME in (RES['algo_detail_before_delete']['detail']['section'] or '')
            dump()

            # ── 5. 删除维度（UI）→ 算法详情同步 ──
            go_evaluation(d)
            search_dim(d, DIM_NAME)
            RES['delete_click'] = d.execute_script(JS_CLICK_PAGE, f'删除维度 {DIM_NAME}')
            time.sleep(1.5)
            RES['delete_confirm'] = click_page(d, '删除', 2.5)
            toasts_del = []
            for _ in range(16):
                toasts_del += toasts(d)
                if any('已删除' in t or '删除' in t for t in toasts_del):
                    break
                time.sleep(0.5)
            RES['delete_toasts'] = toasts_del
            time.sleep(2)
            RES['after_delete_list_total'] = api(
                'GET', '/evaluation/dimensions?page=1&per_page=1')[1]['data']['total']
            st, body = api('GET', f'/evaluation/dimensions/{dim_id}')
            RES['after_delete_detail'] = {'status': st, 'body': str(body)[:300]}
            st, res = api('GET', f'/algorithm/definitions/{ALGO_TYPE}')
            rels2 = ((res or {}).get('data') or {}).get('dimension_relations') or []
            RES['algo_relations_after_dim_delete'] = rels2
            go_light_algo(d)
            RES['algo_detail_after_delete'] = open_algo_detail(d, ALGO_NAME)
            RES['algo_detail_after_has_name'] = DIM_NAME in (RES['algo_detail_after_delete']['detail']['section'] or '')
            RES['algo_detail_after_section'] = (RES['algo_detail_after_delete']['detail']['section'] or '')[:600]
            RES['shot_algo_detail_after'] = shot(d, 'dim-05-algo-detail-after-dim-delete')
            dump()

        # ── 6. 清理自建算法 ──
        if assoc_ok:
            st, _ = api('DELETE', f'/algorithm/definitions/{ALGO_TYPE}')
            RES['algo_delete'] = st
        RES['final_dims_total'] = api('GET', '/evaluation/dimensions?page=1&per_page=1')[1]['data']['total']
        RES['final_algos'] = [
            x['type'] for x in api('GET', '/algorithm/definitions?page=1&page_size=50')[1]['data']['items']]
        dump()
    finally:
        dump()
        d.quit()


def go_light_algo(d):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")


if __name__ == '__main__':
    main()
