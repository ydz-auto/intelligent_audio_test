# -*- coding: utf-8 -*-
"""INT-2247 验收：评估维度列表行「启用/禁用」与「复制维度」不得整行保存
（列表占位空数组被后端当显式清空 → 删输出字段与 output ParamMapping）。

用法：
  修复侧（本卡交付构建旁路容器 15247）：
    python verify_int2247_dimension_status_dup.py --base http://localhost:15247 --mode fix
  缺陷侧（共享 15173 旧镜像，不含本卡改动，A/B 对照）：
    python verify_int2247_dimension_status_dup.py --base http://localhost:15173 --mode old

fix 断言：
  ① 行内禁用/启用：PUT 载荷仅 {"status": ...}，不含列表占位空数组；
  ② 启停后 GET 详情 required_inputs / output_fields / associated_algorithms 与启停前一致；
  ③ 启停后 DB evaluation_dimension_params（input/output 非删）与 param_mappings 非删行数不变；
  ④ 复制：浏览器先 GET /dimensions/{id} 再 POST，副本含输入/输出字段与关联算法（参数级等价）；
  ⑤ 抽屉清空输出字段再保存：PUT 载荷 output_fields=[] 且回读为空（显式清空语义保留）；
  ⑥ 浅色 / 深色截图 + 请求载荷 JSON。

old 模式断言缺陷形态：PUT 载荷带 required_inputs/output_fields 空数组，回读 output_fields 被清空。

数据卫生：夹具统一前缀「接线测试_INT2247_」，run 内 DELETE 软删并核对库内无存活残留。
产出：tests/ui/artifacts/int2247_<mode>/（run.json / shots / run.log）
"""
import argparse
import copy
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PG = ['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql',
      '-U', 'postgres', '-d', 'intelligent_audio_test', '-t', '-A', '-F', '|', '-c']
PREFIX = '接线测试_INT2247_'
STAMP = time.strftime('%m%d%H%M%S')
SRC_DIM_ID = 169  # 合成场景率：9 输入 / 10 输出 / 1 关联算法（只读复制源）
USER, PWD = 'dev_user', 'dev_password'


# ------------------------------------------------------------------ helpers --
def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ['--headless=new', '--window-size=1680,1050', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run',
              '--no-default-browser-check', '--force-device-scale-factor=1']:
        o.add_argument(a)
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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


def collect_requests(drv):
    reqs = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'),
                    'url': req.get('url') or '',
                    'status': None,
                    'postData': req.get('postData') or '',
                }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
    except Exception:
        pass
    return list(reqs.values())


def wait_for(cond, timeout=40, desc='condition', interval=0.3):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            value = cond()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(interval)
    raise AssertionError('timeout waiting for %s (last error: %r)' % (desc, last))


def psql(sql):
    out = subprocess.run(PG + [sql], capture_output=True, text=True, encoding='utf-8')
    if out.returncode != 0:
        raise RuntimeError('psql failed: %s' % (out.stderr or '')[:400])
    return [line for line in out.stdout.strip().splitlines() if line != '']


def db_counts(dim_id):
    rows = psql(
        "select param_direction, count(*) filter (where not deleted) from evaluation_dimension_params "
        "where dimension_id=%s group by 1 order by 1" % dim_id)
    params = {}
    for row in rows:
        direction, alive = row.split('|')
        params[direction] = int(alive)
    mappings = int(psql("select count(*) from param_mappings where dimension_id=%s and not deleted" % dim_id)[0])
    algos = int(psql("select count(*) from algorithm_dimension_relations where dimension_id=%s and not deleted" % dim_id)[0])
    return {'params': params, 'mappings_alive': mappings, 'algo_relations_alive': algos}


# ---------------------------------------------------------------------- api --
def api(base, path, token, method='GET', payload=None):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(base + '/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        try:
            return exc.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return exc.code, raw[:400]


def get_detail(base, token, dim_id):
    status, body = api(base, '/evaluation/dimensions/%s' % dim_id, token)
    assert status == 200, 'GET 详情失败 %s %r' % (status, body)
    return body['data']


def create_fixture(base, token, name):
    detail = get_detail(base, token, SRC_DIM_ID)
    payload = copy.deepcopy(detail)
    for key in ('id', 'created_at', 'updated_at', 'created_by_user_id', 'parent_dimension_id'):
        payload.pop(key, None)
    payload['name'] = name
    # 源维度 169 的 result_min/result_max 均为 0（历史脏数据），抽屉表单要求 min<max；
    # 夹具改成 0~100，避免「结果区间无效」导致保存按钮被禁用（与本卡无关的既有校验）。
    payload['result_min'] = 0.0
    payload['result_max'] = 100.0
    payload['required_inputs'] = [
        {
            'key': row.get('param_code'),
            'param_name': row.get('param_name'),
            'label': row.get('label'),
            'field_type': row.get('field_type'),
            'required': row.get('required'),
            'default_value': row.get('default_value'),
            'description': row.get('help_text'),
        }
        for row in (detail.get('required_inputs') or [])
    ]
    payload['output_fields'] = [
        {k: row.get(k) for k in (
            'param_code', 'param_name', 'label', 'field_path', 'field_type', 'output_role',
            'agg_role', 'default_value', 'visible_in_report', 'help_text', 'ui_order',
            'pass_threshold')}
        for row in (detail.get('output_fields') or [])
    ]
    payload['associated_algorithms'] = detail.get('associated_algorithms') or []
    status, body = api(base, '/evaluation/dimensions', token, 'POST', payload)
    assert status in (200, 201), '创建夹具失败 %s %r' % (status, body)
    return int(body['data']['id'])


def cleanup(base, token, dim_id, report):
    status, _ = api(base, '/evaluation/dimensions/%s' % dim_id, token, 'DELETE')
    report['steps'].append('清理：DELETE 维度 %s → %s' % (dim_id, status))


def find_by_name(name):
    rows = psql("select id from dimensions where name='%s' and not deleted order by id" % name)
    return [int(r) for r in rows]


def sig(detail):
    """可比较的配置签名（参数级）。"""
    return {
        'inputs': [(r.get('param_code'), r.get('param_name') or r.get('label'))
                   for r in (detail.get('required_inputs') or [])],
        'outputs': [(r.get('param_code'), r.get('field_path'), (r.get('agg_role') or None),
                     r.get('output_role') or None, r.get('pass_threshold'))
                    for r in (detail.get('output_fields') or [])],
        'algos': [(r.get('algorithm_type'), r.get('weight'), r.get('is_default'))
                  for r in (detail.get('associated_algorithms') or [])],
    }


# ---------------------------------------------------------------------- ui --
def login(drv, base):
    drv.get(base + '/login')
    wait_for(lambda: drv.execute_script('return document.readyState') == 'complete', 60, 'login 页面')
    time.sleep(2)
    drv.find_element(By.ID, 'username').send_keys(USER)
    drv.find_element(By.ID, 'password').send_keys(PWD)
    drv.find_element(By.CSS_SELECTOR, 'button[type=submit]').click()
    wait_for(lambda: '/login' not in drv.current_url, 60, '登录跳转')
    time.sleep(2)
    token = drv.execute_script("return window.localStorage.getItem('iatp:auth:token:v1')")
    assert token, '登录后未取到 token'
    return token


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.toggle('dark', arguments[0]==='dark');",
        mode)
    time.sleep(0.8)


def goto_eval(drv, base):
    drv.get(base + '/Evaluation')
    wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="搜索评估维度"]')
             or drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
             60, '/Evaluation 渲染')


def search(drv, keyword):
    el = wait_for(
        lambda: drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="搜索评估维度"]')
        or drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
        30, '搜索框')[0]
    drv.execute_script(
        "const el=arguments[0],v=arguments[1];"
        "const set=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
        "set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));",
        el, keyword)
    time.sleep(1.5)


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();', el)


def wait_aria(drv, label, timeout=40):
    return wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="%s"]' % label),
                    timeout, '按钮 %s' % label)[0]


def shot(drv, art, name):
    os.makedirs(art, exist_ok=True)
    p = os.path.join(art, name)
    drv.save_screenshot(p)
    return p


def put_calls(reqs, dim_id):
    return [r for r in reqs if r['method'] == 'PUT'
            and ('/evaluation/dimensions/%s' % dim_id) in r['url']]


def wait_put(drv, dim_id, timeout=40):
    return wait_for(lambda: put_calls(collect_requests(drv), dim_id), timeout,
                    'PUT /evaluation/dimensions/%s' % dim_id)


def drawer_state(drv):
    summary = [e.text for e in drv.find_elements(
        By.CSS_SELECTOR, "[data-testid='dimension-form-validation-summary']")]
    pending = [e.text for e in drv.find_elements(
        By.CSS_SELECTOR, "[data-testid='dimension-detail-pending']")]
    save = drv.find_elements(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']")
    sheet = drv.find_elements(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    text = sheet[-1].text if sheet else ''
    return {'summary': summary, 'pending': pending,
            'save_enabled': bool(save) and save[0].is_enabled(),
            'sheet_tail': text[-600:] if text else ''}

# -------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15247')
    ap.add_argument('--mode', choices=('fix', 'old'), default='fix')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    mode = args.mode
    art = os.path.join(HERE, 'artifacts', 'int2247_%s' % mode)
    shots = os.path.join(art, 'shots')
    os.makedirs(shots, exist_ok=True)
    report = {'base': base, 'mode': mode, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
              'steps': [], 'requests': {}, 'asserts': [], 'shots': []}
    created = []
    drv = None
    token = None
    try:
        drv = driver()
        token = login(drv, base)
        report['steps'].append('登录 dev_user 成功')

        # ---------- 夹具 ----------
        name = PREFIX + ('fix_' if mode == 'fix' else 'old_') + STAMP
        fid = create_fixture(base, token, name)
        created.append(fid)
        src = get_detail(base, token, fid)
        sig0 = sig(src)
        db0 = db_counts(fid)
        report['fixture'] = {'id': fid, 'name': name, 'sig': sig0, 'db': db0}
        report['steps'].append('夹具 id=%s name=%s 输入%d 输出%d 算法%d mappings=%d' % (
            fid, name, len(sig0['inputs']), len(sig0['outputs']), len(sig0['algos']),
            db0['mappings_alive']))
        assert len(sig0['outputs']) > 0 and len(sig0['algos']) > 0, '夹具缺少输出字段/关联算法'

        # ---------- 行内启停 ----------
        goto_eval(drv, base)
        search(drv, name)
        toggle = wait_aria(drv, '禁用维度 %s' % name)
        report['shots'].append(shot(drv, shots, '01_%s_list_light.png' % mode))
        collect_requests(drv)  # drain

        js_click(drv, toggle)
        puts = wait_put(drv, fid)
        body_disable = json.loads(puts[-1]['postData'] or '{}')
        report['requests']['toggle_off'] = {'method': 'PUT', 'url': puts[-1]['url'],
                                            'status': puts[-1]['status'], 'body': body_disable}
        time.sleep(1.2)
        detail_off = get_detail(base, token, fid)
        db_off = db_counts(fid)
        report['after_disable'] = {'sig': sig(detail_off), 'db': db_off}

        if mode == 'fix':
            assert set(body_disable.keys()) == {'status'}, '启停 PUT 载荷不止 status: %r' % body_disable
            assert body_disable['status'] is False, '禁用载荷 status 非 false'
            assert sig(detail_off) == sig0, '禁用后配置变化:\n%r\n!= %r' % (sig(detail_off), sig0)
            assert db_off == db0, '禁用后库内参数/映射变化: %r != %r' % (db_off, db0)
            report['asserts'] += ['①禁用 PUT 仅 {status}', '②禁用后详情配置不变', '③禁用后库内行数不变']

            # 再启用
            collect_requests(drv)
            enable_btn = wait_aria(drv, '启用维度 %s' % name)
            js_click(drv, enable_btn)
            puts = wait_put(drv, fid)
            body_enable = json.loads(puts[-1]['postData'] or '{}')
            report['requests']['toggle_on'] = {'method': 'PUT', 'url': puts[-1]['url'],
                                               'status': puts[-1]['status'], 'body': body_enable}
            time.sleep(1.2)
            detail_on = get_detail(base, token, fid)
            db_on = db_counts(fid)
            report['after_enable'] = {'sig': sig(detail_on), 'db': db_on}
            assert set(body_enable.keys()) == {'status'} and body_enable['status'] is True, \
                '启用载荷异常: %r' % body_enable
            assert sig(detail_on) == sig0 and db_on == db0, '启用后配置/库内变化'
            report['asserts'].append('启用同样仅 {status}，配置与库内不变')

            # ---------- 复制维度 ----------
            collect_requests(drv)
            js_click(drv, wait_aria(drv, '复制维度 %s' % name))
            wait_for(lambda: drv.find_elements(
                By.XPATH, "//*[@role='alertdialog']//*[contains(normalize-space(.),'复制维度')]"),
                20, '复制确认弹窗')
            time.sleep(0.5)
            confirm = wait_for(lambda: drv.find_elements(
                By.XPATH, "//*[@role='alertdialog']//button[normalize-space(.)='复制']"),
                20, '复制确认按钮')[0]
            drv.execute_script('arguments[0].click()', confirm)
            copy_name = name + '（副本）'
            ids = wait_for(lambda: find_by_name(copy_name), 60, '副本落库', interval=0.8)
            time.sleep(1.5)
            all_reqs = collect_requests(drv)
            dup_get = [r for r in all_reqs if r['method'] == 'GET'
                       and r['url'].endswith('/evaluation/dimensions/%s' % fid)]
            dup_post = [r for r in all_reqs if r['method'] == 'POST'
                        and r['url'].endswith('/evaluation/dimensions')]
            report['requests']['duplicate_get'] = [{'url': r['url'], 'status': r['status']} for r in dup_get]
            report['requests']['duplicate_post'] = [{
                'url': r['url'], 'status': r['status'],
                'body': json.loads(r['postData'] or '{}')} for r in dup_post]
            assert dup_get, '复制前未先 GET 详情'
            assert dup_post, '复制未发出 POST'
            post_body = json.loads(dup_post[-1]['postData'] or '{}')
            assert post_body.get('output_fields'), '复制 POST 未携带 output_fields'
            assert post_body.get('associated_algorithms'), '复制 POST 未携带 associated_algorithms'

            cid = max(ids)
            created.extend(i for i in ids if i not in created)
            copy_detail = get_detail(base, token, cid)
            sigc = sig(copy_detail)
            report['copy'] = {'id': cid, 'sig': sigc, 'db': db_counts(cid)}
            assert sigc == sig0, '副本配置与源不一致:\n%r\n!= %r' % (sigc, sig0)
            assert db_counts(cid)['mappings_alive'] > 0, '副本无参数映射'
            report['asserts'] += ['④复制先 GET 详情、POST 携带配置', '副本输入/输出/算法与源参数级一致']

            # 回列表截图（浅/深）
            set_theme(drv, 'light')
            goto_eval(drv, base)
            search(drv, name)
            wait_aria(drv, '禁用维度 %s' % name)
            report['shots'].append(shot(drv, shots, '02_list_light.png'))
            set_theme(drv, 'dark')
            goto_eval(drv, base)
            search(drv, name)
            wait_aria(drv, '禁用维度 %s' % name)
            report['shots'].append(shot(drv, shots, '03_list_dark.png'))

            # ---------- 抽屉显式清空输出字段 ----------
            collect_requests(drv)
            js_click(drv, wait_aria(drv, '编辑维度 %s' % name))
            wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, "[data-slot='sheet-content']"),
                     30, '抽屉打开')
            wait_for(lambda: not drv.find_elements(By.CSS_SELECTOR, "[data-testid='dimension-detail-pending']"),
                     40, '维度详情就绪')
            tab = wait_for(lambda: drv.find_elements(
                By.XPATH, "//button[@role='tab'][contains(normalize-space(.),'API配置')]"),
                20, 'API配置 tab')[0]
            drv.execute_script('arguments[0].click()', tab)
            rows = wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="输出字段代码 1"]'),
                            30, '输出字段行')
            report['shots'].append(shot(drv, shots, '04_drawer_api_light.png'))
            drv.execute_script(
                "const el=[...document.querySelectorAll('p,div,span')]"
                ".find(e=>e.textContent.trim()==='输出字段配置');"
                "if(el) el.scrollIntoView({block:'center'});return !!el;")
            time.sleep(0.6)
            report['shots'].append(shot(drv, shots, '05_drawer_output_fields_light.png'))
            report['drawer_before'] = drawer_state(drv)
            assert report['drawer_before']['save_enabled'], \
                '详情就绪后保存按钮仍禁用: %r' % report['drawer_before']
            n_before = len(drv.find_elements(By.CSS_SELECTOR, 'input[aria-label^="输出字段代码"]'))
            report['steps'].append('抽屉输出字段行数=%d' % n_before)
            removed = 0
            for _ in range(40):
                btn = drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="删除输出字段 1"]')
                if not btn:
                    break
                js_click(drv, btn[0])
                removed += 1
                time.sleep(0.25)
            left = len(drv.find_elements(By.CSS_SELECTOR, 'input[aria-label^="输出字段代码"]'))
            report['steps'].append('清空输出字段：删 %d 行，剩余 %d' % (removed, left))
            assert left == 0, '未清空输出字段（剩 %d 行）' % left
            drv.execute_script(
                "const el=[...document.querySelectorAll('p,div,span')]"
                ".find(e=>e.textContent.trim()==='输出字段配置');"
                "if(el) el.scrollIntoView({block:'center'});return !!el;")
            time.sleep(0.5)
            report['shots'].append(shot(drv, shots, '06_drawer_output_cleared_light.png'))
            collect_requests(drv)
            save = wait_for(lambda: drv.find_elements(
                By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']"),
                20, '保存按钮')[0]
            report['drawer_after'] = drawer_state(drv)
            assert save.is_enabled(), '清空输出字段后保存按钮禁用: %r' % report['drawer_after']
            js_click(drv, save)
            puts = wait_put(drv, fid, 120)
            save_body = json.loads(puts[-1]['postData'] or '{}')
            report['requests']['explicit_clear'] = {'method': 'PUT', 'url': puts[-1]['url'],
                                                    'status': puts[-1]['status'], 'body': save_body}
            wait_for(lambda: not drv.find_elements(By.CSS_SELECTOR, "[data-slot='sheet-content']"),
                     60, '抽屉关闭')
            time.sleep(1.5)
            cleared = get_detail(base, token, fid)
            dbc = db_counts(fid)
            report['after_clear'] = {'output_fields': cleared.get('output_fields', []), 'db': dbc}
            assert save_body.get('output_fields') == [], '显式清空 PUT 载荷 output_fields 非 []'
            assert not cleared.get('output_fields'), '显式清空后回读 output_fields 非空'
            assert dbc['params'].get('output', 0) == 0, '显式清空后库内仍有存活 output 参数'
            report['asserts'] += ['⑤显式清空 output_fields=[] 且回读为空（语义区分保留）']

        else:  # old 模式：缺陷形态
            report['asserts'].append('old: PUT 载荷=%r' % body_disable)
            assert 'output_fields' in body_disable or 'required_inputs' in body_disable, \
                '旧版未整行保存？载荷=%r' % body_disable
            assert body_disable.get('output_fields') == [], '旧版载荷 output_fields 非空'
            assert not detail_off.get('output_fields'), '旧版回读 output_fields 未被清空'
            assert db_off['params'].get('output', 0) == 0, '旧版库内 output 参数仍存活'
            report['asserts'] += ['old: 整行 PUT 含空 output_fields，回读被清空（缺陷复现）']
            report['shots'].append(shot(drv, shots, '01_old_list.png'))

        report['status'] = 'PASS'
    except Exception as exc:  # noqa: BLE001
        report['status'] = 'FAIL'
        report['error'] = repr(exc)
        raise
    finally:
        if drv is not None:
            try:
                if token:
                    for cid in created:
                        cleanup(base, token, cid, report)
                time.sleep(0.5)
                residual = []
                for cid in created:
                    alive = psql('select count(*) from dimensions where id=%s and not deleted' % cid)[0]
                    residual.append({'id': cid, 'alive_dimension': alive})
                report['cleanup'] = residual
            except Exception as exc:  # noqa: BLE001
                report['cleanup_error'] = repr(exc)
            try:
                drv.quit()
            except Exception:  # noqa: BLE001
                pass
        with open(os.path.join(art, 'run.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps({k: report.get(k) for k in
                          ('status', 'error', 'asserts', 'cleanup', 'cleanup_error')},
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
