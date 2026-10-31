# -*- coding: utf-8 -*-
"""INT-2248 验收：React 评估维度编辑抽屉保存保住 api_settings.body_template / api_endpoints.max_process。

用法：
  修复侧（交付 sha 构建的旁路容器，15284）：
    python verify_int2248_dimension_roundtrip.py --base http://localhost:15284 --mode fix
  缺陷侧（共享 15173 旧镜像，不含本卡改动）：
    python verify_int2248_dimension_roundtrip.py --base http://localhost:15173 --mode old

覆盖验收标准：
  ① 真实库 dimensions.id=72「逐轮话轮评估」只读打开编辑抽屉 → API配置 模板框显示原 {rounds:[...]}；
     不改不改保存、GET 回读 api_settings 不变。
  ② 以 72 为模板自建夹具（4 条所需输入 + rounds 模板 + max_process=2）：
     打开抽屉 → 直接保存 → PUT 载荷 body_template=rounds、max_process=2；GET 回读一致。
  ③ 无所需输入的夹具打开→保存：不会凭空出现 asr_result/asr_ref（PUT 无 required_inputs、回读 0 行）。
  ④ 浅色 / 深色截图；浏览器控制台无 SEVERE。

数据卫生：夹具统一「接线测试_INT2248_」前缀，脚本结束 DELETE；真实维度 72 只读不改。
输出：tests/ui/artifacts/int2248_<mode>/run.log + 截图。
"""
import argparse
import copy
import json
import os
import sys
import time
import urllib.error
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PREFIX = '接线测试_INT2248_'
STAMP = time.strftime('%H%M%S')
REAL_DIM_ID = 72
REAL_DIM_NAME = '逐轮话轮评估'
SHEET = "//*[@data-slot='sheet-content']"


# ---------------------------------------------------------------- selenium --
def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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
    return webdriver.Chrome(options=options, service=service)


def wait_for(cond, timeout=30, desc='condition', interval=0.3):
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


def shot(drv, artifacts, name):
    os.makedirs(artifacts, exist_ok=True)
    path = os.path.join(artifacts, name)
    drv.save_screenshot(path)
    return path


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.toggle('dark', arguments[0]==='dark');",
        mode,
    )
    time.sleep(0.8)


def collect_requests(drv):
    reqs = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            params = (msg.get('message') or {}).get('params') or {}
            method = (msg.get('message') or {}).get('method') or ''
        except Exception:  # noqa: BLE001
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
    return list(reqs.values())


def console_severe(drv):
    out = []
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                out.append(entry.get('message', '')[:300])
    except Exception:  # noqa: BLE001
        pass
    return out


# -------------------------------------------------------------------- page --
def sheet(drv):
    els = drv.find_elements(By.XPATH, SHEET)
    return els[-1] if els else None


def login(drv, base):
    drv.get(base + '/login')
    wait_for(lambda: drv.find_elements(By.ID, 'username'), timeout=60, desc='登录页')
    drv.find_element(By.ID, 'username').send_keys('dev_user')
    drv.find_element(By.ID, 'password').send_keys('dev_password')
    drv.execute_script("document.querySelector('form').requestSubmit()")
    wait_for(
        lambda: drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')"),
        timeout=60,
        desc='登录 token 落库',
    )
    wait_for(lambda: '/login' not in drv.current_url, timeout=30, desc='离开登录页')
    time.sleep(1.0)


def goto_eval(drv, base):
    drv.get(base + '/evaluation')
    wait_for(
        lambda: drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="搜索评估维度"]'),
        timeout=60,
        desc='/evaluation 搜索框',
    )
    time.sleep(1.5)


def search(drv, keyword, timeout=40):
    box = wait_for(
        lambda: drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="搜索评估维度"]'),
        timeout=timeout,
        desc='搜索框',
    )
    el = box[0]
    drv.execute_script(
        "const el=arguments[0];const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;setter.call(el,arguments[1]);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));",
        el,
        keyword,
    )
    time.sleep(1.2)


def open_edit(drv, name, timeout=40):
    edit = wait_for(
        lambda: drv.find_elements(By.XPATH, "//button[@aria-label='编辑维度 %s']" % name),
        timeout=timeout,
        desc='行操作「编辑维度 %s」' % name,
    )
    drv.execute_script('arguments[0].click()', edit[0])
    wait_for(lambda: sheet(drv) is not None, desc='维度抽屉打开')
    wait_for(lambda: drv.find_elements(By.ID, 'dim-name'), desc='基本信息渲染')
    time.sleep(0.5)


def open_api_tab(drv):
    tab = wait_for(
        lambda: drv.find_elements(
            By.XPATH, "//button[@role='tab'][contains(normalize-space(.),'API配置')]"
        ),
        desc='API配置 tab',
    )
    drv.execute_script('arguments[0].click()', tab[0])
    wait_for(lambda: drv.find_elements(By.ID, 'dim-api-body'), desc='API配置渲染')
    time.sleep(0.5)


def body_template_text(drv):
    el = drv.find_element(By.ID, 'dim-api-body')
    return el.get_attribute('value') or ''


def input_row_count(drv):
    return len(drv.find_elements(By.CSS_SELECTOR, 'input[aria-label^="输入参数键名"]'))


def save_button(drv):
    return drv.find_element(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']")


def save_and_wait(drv, timeout=240):
    drv.execute_script('arguments[0].click()', save_button(drv))
    wait_for(lambda: sheet(drv) is None, timeout=timeout, desc='抽屉关闭（保存完成）')
    time.sleep(1.5)


def close_sheet(drv):
    close = drv.find_elements(By.CSS_SELECTOR, '[data-slot="sheet-content"] [data-slot="sheet-close"]')
    if close:
        drv.execute_script('arguments[0].click()', close[-1])
    else:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    wait_for(lambda: sheet(drv) is None, timeout=20, desc='抽屉关闭')


# --------------------------------------------------------------------- api --
TOKEN = {'value': None}


def _api(url, method='GET', payload=None, attempts=4):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    last = None
    for i in range(attempts):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header('content-type', 'application/json')
        if TOKEN['value']:
            req.add_header('Authorization', 'Bearer ' + TOKEN['value'])
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:  # noqa: S310
                raw = resp.read()
                if resp.status >= 500:
                    last = RuntimeError('HTTP %s body=%r' % (resp.status, raw[:200]))
                else:
                    return resp.status, json.loads(raw.decode('utf-8') or '{}')
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                body = json.loads(raw.decode('utf-8') or '{}')
            except Exception:  # noqa: BLE001
                last = RuntimeError('HTTP %s body=%r' % (exc.code, raw[:200]))
            else:
                if exc.code < 500:
                    return exc.code, body
                last = RuntimeError('HTTP %s body=%r' % (exc.code, raw[:200]))
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(2 + 3 * i)
    raise last if last else RuntimeError('request failed: %s %s' % (method, url))


def api_base(base):
    return base.rstrip('/') + '/api/v1'


def get_dimension(base, dim_id):
    _, body = _api('%s/evaluation/dimensions/%s' % (api_base(base), dim_id))
    return body.get('data') or {}


def dim_total(base):
    _, body = _api('%s/evaluation/dimensions?page=1&per_page=1' % api_base(base))
    return (body.get('data') or {}).get('total')


def create_fixture(base, name, source_id=REAL_DIM_ID, drop_inputs=False, drop_outputs=False):
    _, real = _api('%s/evaluation/dimensions/%s' % (api_base(base), source_id))
    payload = copy.deepcopy(real.get('data') or {})
    for key in ('id', 'created_at', 'updated_at', 'created_by_user_id', 'updated_by_user_id',
                'deleted', 'deleted_at', 'deleted_by_user_id'):
        payload.pop(key, None)
    for key in ('required_inputs', 'output_fields'):
        if isinstance(payload.get(key), list):
            payload[key] = [
                {k: v for k, v in row.items() if k not in ('id', 'dimension_id')}
                for row in payload[key]
            ]
    if drop_inputs:
        payload['required_inputs'] = []
    if drop_outputs:
        payload['output_fields'] = []
    payload['name'] = name
    status, body = _api('%s/evaluation/dimensions' % api_base(base), method='POST', payload=payload)
    assert status in (200, 201), '创建夹具失败 %s %r' % (status, body)
    return body['data']['id']


def delete_fixture(base, dim_id):
    try:
        status, _ = _api('%s/evaluation/dimensions/%s' % (api_base(base), dim_id), method='DELETE')
        return status
    except Exception as exc:  # noqa: BLE001
        return repr(exc)


def rounds_of(dim):
    settings = dim.get('api_settings') or {}
    bt = settings.get('body_template') if isinstance(settings, dict) else None
    if bt is None and isinstance(settings, dict):
        bt = settings.get('bodyTemplate')
    return bt


def endpoint_max_process(dim):
    eps = dim.get('api_endpoints') or []
    if not isinstance(eps, list) or not eps:
        return None
    ep = eps[0] or {}
    return ep.get('max_process', ep.get('maxProcess'))


def required_codes(dim):
    rows = dim.get('required_inputs') or []
    return [r.get('param_code') or r.get('paramCode') for r in rows if isinstance(r, dict)]


# -------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15284')
    ap.add_argument('--mode', choices=('fix', 'old'), default='fix')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    mode = args.mode
    artifacts = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2248_%s' % mode)
    os.makedirs(artifacts, exist_ok=True)
    report = {'base': base, 'mode': mode, 'steps': [], 'requests': []}
    created = []
    drv = _driver()
    try:
        login(drv, base)
        TOKEN['value'] = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        assert TOKEN['value'], '未拿到登录 token'
        report['steps'].append('登录 dev_user 成功（token 已取）')
        total_before = dim_total(base)
        report['steps'].append('维度总数（开工）= %s' % total_before)

        # ---------------- ① 真实维度 72 只读打开 ----------------
        before_72 = get_dimension(base, REAL_DIM_ID)
        goto_eval(drv, base)
        search(drv, REAL_DIM_NAME)
        open_edit(drv, REAL_DIM_NAME)
        open_api_tab(drv)
        body72 = body_template_text(drv)
        rows72 = input_row_count(drv)
        report['real_72'] = {
            'body_template_text': body72[:500],
            'body_template_text_len': len(body72),
            'required_rows': rows72,
            'api_settings_before': before_72.get('api_settings'),
            'max_process_before': endpoint_max_process(before_72),
        }
        if mode == 'fix':
            assert '"rounds"' in body72, '真实维度 72 模板框应显示 rounds，实际 %r' % body72[:200]
            parsed72 = json.loads(body72)
            assert isinstance(parsed72.get('rounds'), list) and parsed72['rounds'], '模板框 rounds 不是非空数组'
            assert rows72 == 4, '真实维度 72 应有 4 条所需输入，实际 %d' % rows72
            assert endpoint_max_process(before_72) == 2, '真实维度 72 max_process 基线不是 2'
        else:
            assert body72.strip() == '', '旧侧模板框应为空（缺陷形态），实际 %r' % body72[:200]
        set_theme(drv, 'light')
        shot(drv, artifacts, '01_%s_real72_api_light.png' % mode)
        set_theme(drv, 'dark')
        shot(drv, artifacts, '02_%s_real72_api_dark.png' % mode)
        set_theme(drv, 'light')
        close_sheet(drv)
        after_72 = get_dimension(base, REAL_DIM_ID)
        assert after_72.get('api_settings') == before_72.get('api_settings'), '真实维度 72 只读打开后被改动'
        assert endpoint_max_process(after_72) == 2, '真实维度 72 max_process 被改动'
        report['steps'].append(
            '① 真实维度 72 只读：模板框 %d 字（含 rounds=%s）/ 所需输入 %d 行；未保存、GET 未变 ✅'
            % (len(body72), '"rounds"' in body72, rows72)
        )

        # ---------------- ② 夹具A：不改字段保存 ----------------
        name_a = PREFIX + 'A_' + STAMP
        id_a = create_fixture(base, name_a)
        created.append(id_a)
        a_before = get_dimension(base, id_a)
        bt_a = rounds_of(a_before)
        assert isinstance(bt_a, dict) and bt_a.get('rounds'), '夹具A body_template 不含 rounds: %r' % bt_a
        assert endpoint_max_process(a_before) == 2, '夹具A max_process 不是 2: %r' % endpoint_max_process(a_before)
        assert len(required_codes(a_before)) == 4, '夹具A 所需输入不是 4 条'
        report['steps'].append('夹具A id=%s（4 输入 / rounds 模板 / max_process=2）' % id_a)

        goto_eval(drv, base)
        search(drv, name_a)
        open_edit(drv, name_a)
        open_api_tab(drv)
        body_a = body_template_text(drv)
        rows_a = input_row_count(drv)
        report['fixture_a_drawer'] = {'body_template_text': body_a[:500], 'required_rows': rows_a}
        if mode == 'fix':
            assert '"rounds"' in body_a, '夹具A 模板框应显示 rounds，实际 %r' % body_a[:200]
            assert rows_a == 4, '夹具A 应有 4 条所需输入，实际 %d' % rows_a
        set_theme(drv, 'light')
        shot(drv, artifacts, '03_%s_fixtureA_api_light.png' % mode)
        set_theme(drv, 'dark')
        shot(drv, artifacts, '04_%s_fixtureA_api_dark.png' % mode)
        set_theme(drv, 'light')

        collect_requests(drv)  # drain
        save_and_wait(drv)
        reqs = collect_requests(drv)
        puts = [r for r in reqs if '/evaluation/dimensions/' in r['url'] and r['method'] == 'PUT']
        assert puts, '未捕获 PUT /evaluation/dimensions/{id}'
        put = puts[-1]
        payload = json.loads(put['postData'] or '{}')
        report['requests'].append(put)
        settings_sent = payload.get('api_settings') or {}
        eps_sent = payload.get('api_endpoints') or []
        report['fixture_a_put'] = {
            'status': put['status'],
            'api_settings': settings_sent,
            'api_endpoints': eps_sent,
            'has_required_inputs': 'required_inputs' in payload,
        }
        a_after = get_dimension(base, id_a)
        report['fixture_a_readback'] = {
            'api_settings': a_after.get('api_settings'),
            'api_endpoints': a_after.get('api_endpoints'),
            'required_codes': required_codes(a_after),
        }
        if mode == 'fix':
            sent_bt = settings_sent.get('body_template')
            assert sent_bt == bt_a, 'PUT 载荷 body_template 与基线不符: %r' % sent_bt
            assert 'bodyTemplate' not in settings_sent, 'PUT 载荷仍写驼峰 bodyTemplate'
            assert eps_sent and eps_sent[0].get('max_process') == 2, 'PUT 载荷 max_process 不是 2: %r' % eps_sent
            assert rounds_of(a_after) == bt_a, '回读 body_template 被改: %r' % rounds_of(a_after)
            assert endpoint_max_process(a_after) == 2, '回读 max_process 被改: %r' % endpoint_max_process(a_after)
            assert required_codes(a_after) == required_codes(a_before), '回读所需输入被改: %r' % required_codes(a_after)
            report['steps'].append('② 不改字段保存：PUT %s body_template 保持 rounds、max_process=2、所需输入 4 条；回读一致 ✅'
                                   % put['status'])
        else:
            after_bt = rounds_of(a_after)
            lost = not (isinstance(after_bt, dict) and after_bt.get('rounds') == bt_a.get('rounds'))
            report['steps'].append('旧侧 b②：回读 body_template=%r、max_process=%r'
                                   % (after_bt, endpoint_max_process(a_after)))
            assert lost, '旧侧应丢 rounds 结构，实际 %r' % after_bt
            assert endpoint_max_process(a_after) != 2, '旧侧 max_process 应被覆盖成 5，实际 %r' % endpoint_max_process(a_after)

        # ---------------- ③ 夹具B：无所需输入 ----------------
        name_b = PREFIX + 'B_' + STAMP
        id_b = create_fixture(base, name_b, drop_inputs=True, drop_outputs=True)
        created.append(id_b)
        b_before = get_dimension(base, id_b)
        assert required_codes(b_before) == [], '夹具B 基线应有 0 条所需输入'
        goto_eval(drv, base)
        search(drv, name_b)
        open_edit(drv, name_b)
        open_api_tab(drv)
        rows_b_open = input_row_count(drv)
        report['fixture_b_drawer'] = {'required_rows_on_open': rows_b_open}
        if mode == 'fix':
            assert rows_b_open == 0, '无输入维度打开后不应冒出输入行，实际 %d' % rows_b_open
        else:
            assert rows_b_open == 2, '旧侧应兜底 2 行 ASR 输入，实际 %d' % rows_b_open

        collect_requests(drv)
        save_and_wait(drv)
        reqs = collect_requests(drv)
        puts_b = [r for r in reqs if '/evaluation/dimensions/' in r['url'] and r['method'] == 'PUT']
        assert puts_b, '夹具B 未捕获 PUT'
        put_b = puts_b[-1]
        payload_b = json.loads(put_b['postData'] or '{}')
        report['fixture_b_put'] = {
            'status': put_b['status'],
            'required_inputs': payload_b.get('required_inputs'),
            'api_settings': payload_b.get('api_settings'),
        }
        b_after = get_dimension(base, id_b)
        report['fixture_b_readback'] = {
            'required_codes': required_codes(b_after),
            'api_settings': b_after.get('api_settings'),
        }
        if mode == 'fix':
            assert 'required_inputs' not in payload_b, '未改动输入仍回传 required_inputs'
            assert required_codes(b_after) == [], '保存后凭空出现所需输入: %r' % required_codes(b_after)
            goto_eval(drv, base)
            search(drv, name_b)
            open_edit(drv, name_b)
            open_api_tab(drv)
            rows_b_reopen = input_row_count(drv)
            report['fixture_b_reopen_rows'] = rows_b_reopen
            assert rows_b_reopen == 0, '重开夹具B 仍有 %d 行输入' % rows_b_reopen
            close_sheet(drv)
            report['steps'].append('③ 无输入维度保存：PUT 无 required_inputs、回读 0 行、重开 0 行 ✅')
        else:
            codes = required_codes(b_after)
            report['steps'].append('旧侧 b③：保存后所需输入=%r' % codes)
            assert 'asr_result' in codes and 'asr_ref' in codes, '旧侧应凭空写入 asr_result/asr_ref，实际 %r' % codes

        report['console_severe'] = console_severe(drv)
        report['ok'] = True
    except Exception as exc:  # noqa: BLE001
        report['ok'] = False
        report['error'] = repr(exc)
        try:
            shot(drv, artifacts, '99_%s_failure.png' % mode)
            report['visible_text'] = drv.find_element(By.TAG_NAME, 'body').text[:3000]
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        for dim_id in created:
            report.setdefault('cleanup', []).append(
                'DELETE %s → %s' % (dim_id, delete_fixture(base, dim_id)))
        try:
            report['total_after_cleanup'] = dim_total(base)
        except Exception as exc:  # noqa: BLE001
            report['total_after_cleanup'] = repr(exc)
        with open(os.path.join(artifacts, 'run.log'), 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
