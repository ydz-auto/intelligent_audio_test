# -*- coding: utf-8 -*-
"""INT-1732 评估维度「编辑不改字段保存」不再被默认 5 条规则顶替 / rule 其余键保留 + 3 项 P3。

对照用法：
  修复侧（本卡交付 dist 的旁路容器，15282）：
    python verify_int1732_dimension_rule.py --base http://localhost:15282 --mode fix
  缺陷侧（共享 15173 旧镜像，不含本卡改动）：
    python verify_int1732_dimension_rule.py --base http://localhost:15173 --mode old

fix 模式断言：
  ① 空规则夹具（rule={rules:[],defaultScore:7}、result_type=0）打开编辑：
     结果配置 0 条规则行 + 「该维度未配置评分规则」+ 结果类型「未设置」+ 保存可用
  ② 不改字段保存 → PUT 载荷 rule 仍为 {rules:[],defaultScore:7}，result_type=0
  ③ GET 回读 rule 不变
  ④ 已有 2 条规则 + defaultScore=3 的夹具：加 1 条保存后回读 3 条；重开删 1 条保存后回读 2 条，
     defaultScore 全程保留
  ⑤ 真实维度 121（rules=[]、defaultScore=0）只读打开：无默认 5 条、有未配置提示，不保存
  ⑥ P3-1：result_type=0 显示「未设置」而非「请选择结果类型」
  ⑦ P3-2：筛选无匹配 → 「暂无评估维度数据」+ 不出现「创建第一个评估维度」
  ⑧ P3-3：新增维度 → API配置 → 端点 URL / 名称均为空
  ⑨ 浅色 / 深色截图
old 模式把 ①④⑦⑧ 断言成缺陷形态（5 条默认规则、保存丢 defaultScore、空态引导创建、假端点），
证明同一脚本能区分修复前后。

数据卫生：所有夹具用「接线测试_INT1732_」前缀，run 内 DELETE 清理；真实维度 121 只读不改。
输出：tests/ui/artifacts/int1732_<mode>/run.log + 截图。
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
PREFIX = '接线测试_INT1732_'
STAMP = time.strftime('%H%M%S')
REAL_DIM_ID = 121
REAL_DIM_NAME = '拒识成功数量'
EMPTY_HINT = '该维度未配置评分规则'
FILTER_EMPTY_TITLE = '暂无评估维度数据'
FAKE_ENDPOINT = 'https://api.example.com/evaluation/accuracy'


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


def set_number(drv, el, value):
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(str(value))
    time.sleep(0.3)


# -------------------------------------------------------------------- page --
SHEET = "//*[@data-slot='sheet-content']"


def sheet(drv):
    els = drv.find_elements(By.XPATH, SHEET)
    return els[-1] if els else None


def sheet_text(drv):
    el = sheet(drv)
    return el.text if el else ''


def open_edit(drv, name, timeout=40):
    edit = wait_for(
        lambda: drv.find_elements(By.XPATH, "//button[@aria-label='编辑维度 %s']" % name),
        timeout=timeout,
        desc='行操作「编辑维度 %s」' % name,
    )
    drv.execute_script('arguments[0].click()', edit[0] if isinstance(edit, list) else edit)
    wait_for(lambda: sheet(drv) is not None, desc='维度抽屉打开')
    wait_for(lambda: drv.find_elements(By.ID, 'dim-name'), desc='基本信息渲染')


def open_result_tab(drv):
    tab = wait_for(
        lambda: drv.find_elements(
            By.XPATH, "//button[@role='tab'][contains(normalize-space(.),'结果配置')]"
        ),
        desc='结果配置 tab',
    )
    drv.execute_script('arguments[0].click()', tab[0])
    wait_for(lambda: drv.find_elements(By.ID, 'dim-result-min'), desc='结果配置渲染')
    time.sleep(0.5)


def open_api_tab(drv):
    tab = wait_for(
        lambda: drv.find_elements(
            By.XPATH, "//button[@role='tab'][contains(normalize-space(.),'API配置')]"
        ),
        desc='API配置 tab',
    )
    drv.execute_script('arguments[0].click()', tab[0])
    wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="端点 URL 1"]'),
             desc='API配置渲染')
    time.sleep(0.4)


def rule_row_count(drv):
    return len(drv.find_elements(By.CSS_SELECTOR, 'input[aria-label$="阈值"]'))


def save_button(drv):
    return drv.find_element(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']")


def save_and_wait(drv, timeout=240):
    drv.execute_script('arguments[0].click()', save_button(drv))
    wait_for(lambda: sheet(drv) is None, timeout=timeout, desc='抽屉关闭（保存完成）')
    time.sleep(1.2)


def close_sheet(drv):
    els = drv.find_elements(By.CSS_SELECTOR, '[data-slot="sheet-content"] button[aria-label="Close"]')
    if not els:
        els = drv.find_elements(By.CSS_SELECTOR, '[data-slot="sheet-content"] button')
    # Radix/base-ui 关闭按钮常在 header 右侧；退化为 Esc
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    wait_for(lambda: sheet(drv) is None, timeout=20, desc='抽屉关闭')


def reload_eval(drv, base):
    """夹具经 API 创建后列表不会自动刷新，重载页面再筛。"""
    drv.get(base + '/Evaluation')
    wait_for(
        lambda: drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
        timeout=60,
        desc='/Evaluation 重载',
    )
    time.sleep(1.5)


def search(drv, keyword, timeout=40):
    box = wait_for(
        lambda: drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
        desc='搜索框',
    )
    el = box[0]
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if keyword:
        el.send_keys(keyword)
    time.sleep(1.0)


def drawer_result_type_text(drv):
    """结果类型 SelectTrigger 的当前闭合态文案（「结果类型」Label 右侧的 combobox）。"""
    return sheet_text(drv)


# --------------------------------------------------------------------- api --
def _api(url, method='GET', payload=None, attempts=4):
    """带重试：15000 网关偶发 504/空体（并发压测/SSE 占满线程池），重试不改变断言口径。"""
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    last = None
    for i in range(attempts):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header('content-type', 'application/json')
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


def create_fixture(base, name, rule, result_type):
    _, real = _api('%s/evaluation/dimensions/%s' % (api_base(base), REAL_DIM_ID))
    payload = copy.deepcopy(real.get('data') or {})
    for key in ('id', 'created_at', 'updated_at', 'created_by_user_id'):
        payload.pop(key, None)
    for key in ('required_inputs', 'output_fields'):
        if isinstance(payload.get(key), list):
            payload[key] = [
                {k: v for k, v in row.items() if k not in ('id', 'dimension_id')}
                for row in payload[key]
            ]
    payload.update({'name': name, 'rule': rule, 'result_type': result_type})
    status, body = _api('%s/evaluation/dimensions' % api_base(base), method='POST', payload=payload)
    assert status in (200, 201), '创建夹具失败 %s %r' % (status, body)
    return body['data']['id']


def delete_fixture(base, dim_id):
    try:
        status, _ = _api('%s/evaluation/dimensions/%s' % (api_base(base), dim_id), method='DELETE')
        return status
    except Exception as exc:  # noqa: BLE001
        return repr(exc)


# -------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15282')
    ap.add_argument('--mode', choices=('fix', 'old'), default='fix')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    mode = args.mode
    artifacts = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1732_%s' % mode)
    os.makedirs(artifacts, exist_ok=True)
    report = {'base': base, 'mode': mode, 'steps': [], 'requests': [], 'dark': False}
    created = []
    drv = _driver()
    try:
        total_before = dim_total(base)
        report['steps'].append('维度总数（开工）= %s' % total_before)
        drv.get(base + '/Evaluation')
        wait_for(
            lambda: drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
            timeout=60,
            desc='/Evaluation 渲染（搜索框）',
        )
        time.sleep(1.5)
        collect_requests(drv)  # drain 基线

        # ---------------- ① ② ③ 空规则夹具：打开不改保存 ----------------
        name_a = PREFIX + 'empty_' + STAMP
        id_a = create_fixture(base, name_a, {'rules': [], 'defaultScore': 7}, 0)
        created.append(id_a)
        d = get_dimension(base, id_a)
        assert d.get('rule') == {'rules': [], 'defaultScore': 7}, '夹具回读 rule 不符: %r' % d.get('rule')
        report['steps'].append('夹具A id=%s rule={"rules":[],"defaultScore":7} result_type=0' % id_a)

        reload_eval(drv, base)
        search(drv, name_a)
        open_edit(drv, name_a)
        open_result_tab(drv)
        rows = rule_row_count(drv)
        text = sheet_text(drv)
        has_hint = EMPTY_HINT in text
        has_result_label = '未设置' in text
        has_placeholder = '请选择结果类型' in text
        save_enabled = save_button(drv).get_attribute('disabled') is None
        report['fixture_a_drawer'] = {
            'rule_rows': rows, 'empty_hint': has_hint, 'result_type_text_未设置': has_result_label,
            'shows_请选择结果类型': has_placeholder, 'save_enabled': save_enabled,
        }
        if mode == 'fix':
            assert rows == 0, '空规则维度不应冒出规则行，实际 %d 行' % rows
            assert has_hint, '缺少「%s」提示' % EMPTY_HINT
            assert has_result_label, 'result_type=0 未显示「未设置」'
            assert not has_placeholder, '仍显示「请选择结果类型」'
            assert save_enabled, '空规则下保存按钮不可用'
        else:
            assert rows == 5, '缺陷侧应显示默认 5 条规则，实际 %d 行' % rows
            assert not has_result_label, '旧侧不应显示「未设置」'
            assert has_placeholder, '旧侧应显示「请选择结果类型」'
        set_theme(drv, 'light')
        shot(drv, artifacts, '01_%s_drawer_light.png' % mode)
        set_theme(drv, 'dark')
        shot(drv, artifacts, '02_%s_drawer_dark.png' % mode)
        set_theme(drv, 'light')

        collect_requests(drv)
        save_and_wait(drv)
        reqs = collect_requests(drv)
        puts = [
            r for r in reqs
            if '/evaluation/dimensions/' in r['url'] and r['method'] == 'PUT'
        ]
        assert puts, '未捕获 PUT /evaluation/dimensions/{id}'
        put = puts[-1]
        body = json.loads(put['postData'] or '{}')
        report['requests'].append(put)
        report['steps'].append(
            '不改字段保存 → PUT %s status=%s rule=%s result_type=%s'
            % (put['url'], put['status'], json.dumps(body.get('rule'), ensure_ascii=False),
               body.get('result_type'))
        )
        d = get_dimension(base, id_a)
        report['fixture_a_readback'] = {'rule': d.get('rule'), 'result_type': d.get('result_type')}
        if mode == 'fix':
            assert body.get('rule') == {'rules': [], 'defaultScore': 7}, 'PUT 载荷丢 rule: %r' % body.get('rule')
            assert body.get('result_type') == 0, 'PUT 载荷 result_type 不符: %r' % body.get('result_type')
            assert d.get('rule') == {'rules': [], 'defaultScore': 7}, '回读 rule 被改: %r' % d.get('rule')
            assert d.get('result_type') == 0, '回读 result_type 被改: %r' % d.get('result_type')
            report['steps'].append('③ 回读 rule 保持 {"rules":[],"defaultScore":7}、result_type=0 ✅')
        else:
            rules_after = (d.get('rule') or {}).get('rules') or []
            assert len(rules_after) == 5, '缺陷侧保存后应变成 5 条，实际 %d' % len(rules_after)
            assert 'defaultScore' not in (d.get('rule') or {}), '缺陷侧应丢 defaultScore'
            report['steps'].append('缺陷侧复现：保存后 rule 被换成 5 条且 defaultScore 丢失 ✅')

        # ---------------- ④ 已有规则夹具：增 1 / 删 1 ----------------
        name_b = PREFIX + 'rules_' + STAMP
        id_b = create_fixture(
            base, name_b,
            {'rules': [{'condition': '>=', 'value': 95, 'score': 10},
                       {'condition': '<', 'value': 95, 'score': 0}],
             'defaultScore': 3},
            1,
        )
        created.append(id_b)
        reload_eval(drv, base)
        search(drv, name_b)
        open_edit(drv, name_b)
        open_result_tab(drv)
        base_rows = len(drv.find_elements(By.CSS_SELECTOR, 'input[aria-label$="阈值"]'))
        assert base_rows == 2, '已有规则夹具应显示 2 行，实际 %d' % base_rows
        add = drv.find_element(By.XPATH, "%s//button[contains(normalize-space(.),'添加规则')]" % SHEET)
        drv.execute_script('arguments[0].click()', add)
        time.sleep(0.4)
        set_number(drv, drv.find_element(By.CSS_SELECTOR, 'input[aria-label="规则 3 阈值"]'), 60)
        set_number(drv, drv.find_element(By.CSS_SELECTOR, 'input[aria-label="规则 3 得分"]'), 6)
        save_and_wait(drv)
        d = get_dimension(base, id_b)
        rules = (d.get('rule') or {}).get('rules') or []
        report['steps'].append('④ 加 1 条保存 → 回读 %d 条, defaultScore=%r'
                               % (len(rules), (d.get('rule') or {}).get('defaultScore')))
        assert len(rules) == 3, '加一条后应为 3 条，实际 %d' % len(rules)
        if mode == 'fix':
            assert (d.get('rule') or {}).get('defaultScore') == 3, '加规则后 defaultScore 丢失'

        search(drv, name_b)
        open_edit(drv, name_b)
        open_result_tab(drv)
        dele = wait_for(
            lambda: drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="删除规则 3"]'),
            desc='删除规则 3 按钮',
        )
        drv.execute_script('arguments[0].click()', dele[0])
        time.sleep(0.4)
        save_and_wait(drv)
        d = get_dimension(base, id_b)
        rules = (d.get('rule') or {}).get('rules') or []
        report['steps'].append('④ 删 1 条保存 → 回读 %d 条, defaultScore=%r'
                               % (len(rules), (d.get('rule') or {}).get('defaultScore')))
        assert len(rules) == 2, '删一条后应为 2 条，实际 %d' % len(rules)
        if mode == 'fix':
            assert (d.get('rule') or {}).get('defaultScore') == 3, '删规则后 defaultScore 丢失'

        # ---------------- ⑤ 真实维度 121 只读 ----------------
        before_121 = get_dimension(base, REAL_DIM_ID)
        search(drv, REAL_DIM_NAME)
        open_edit(drv, REAL_DIM_NAME)
        open_result_tab(drv)
        rows121 = rule_row_count(drv)
        hint121 = EMPTY_HINT in sheet_text(drv)
        report['real_121'] = {'rule_rows': rows121, 'empty_hint': hint121,
                              'rule': before_121.get('rule')}
        if mode == 'fix':
            assert rows121 == 0, '真实维度 121（rules=[]）不该出现规则行，实际 %d' % rows121
            assert hint121, '真实维度 121 缺少未配置提示'
        set_theme(drv, 'light')
        shot(drv, artifacts, '03_%s_real121_light.png' % mode)
        close_sheet(drv)
        after_121 = get_dimension(base, REAL_DIM_ID)
        assert after_121.get('rule') == before_121.get('rule'), '真实维度 121 被改动'
        report['steps'].append('⑤ 真实维度 121 只读打开：%d 行规则 / 未配置提示=%s，未保存、GET 未变 ✅'
                               % (rows121, hint121))

        # ---------------- ⑦ 筛选无匹配空态 ----------------
        search(drv, 'zzz_int1732_无匹配')
        expect_title = FILTER_EMPTY_TITLE if mode == 'fix' else '暂无评估维度'
        title_ok = wait_for(
            lambda: expect_title in drv.find_element(By.TAG_NAME, 'body').text,
            timeout=20,
            desc='筛选空态标题「%s」' % expect_title,
        )
        page_text = drv.find_element(By.TAG_NAME, 'body').text
        has_create_guide = '创建第一个评估维度' in page_text
        has_filter_guide = '当前筛选条件下没有匹配的评估维度' in page_text
        has_new_title = FILTER_EMPTY_TITLE in page_text
        report['filter_empty'] = {'title': expect_title, 'title_present': bool(title_ok),
                                  'create_guide': has_create_guide,
                                  'filter_guide': has_filter_guide,
                                  'new_title_present': has_new_title}
        if mode == 'fix':
            assert title_ok, '筛选无匹配未显示「%s」' % FILTER_EMPTY_TITLE
            assert has_filter_guide, '筛选无匹配缺少调整筛选提示'
            assert not has_create_guide, '筛选无匹配仍引导「创建第一个评估维度」'
        else:
            assert has_create_guide, '旧侧应仍显示「创建第一个评估维度」'
            assert not has_new_title, '旧侧不应出现「%s」' % FILTER_EMPTY_TITLE
        shot(drv, artifacts, '04_%s_filter_empty_light.png' % mode)
        set_theme(drv, 'dark')
        shot(drv, artifacts, '05_%s_filter_empty_dark.png' % mode)
        set_theme(drv, 'light')
        report['steps'].append('⑦ 筛选无匹配空态：标题=%s 调整提示=%s 引导创建=%s'
                               % (title_ok, has_filter_guide, has_create_guide))

        # ---------------- ⑧ 新建抽屉端点 URL ----------------
        search(drv, '')
        time.sleep(1.0)
        new_btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.),'新增维度')]")
        assert new_btns, '未找到「新增维度」按钮'
        drv.execute_script('arguments[0].click()', new_btns[0])
        wait_for(lambda: sheet(drv) is not None and drv.find_elements(By.ID, 'dim-name'),
                 desc='新增维度抽屉')
        open_api_tab(drv)
        url_el = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="端点 URL 1"]')
        name_el = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="端点名称 1"]')
        url_val = url_el.get_attribute('value')
        name_val = name_el.get_attribute('value')
        report['create_endpoint'] = {'url': url_val, 'name': name_val}
        if mode == 'fix':
            assert url_val == '', '新建端点 URL 应为空，实际 %r' % url_val
            assert name_val == '', '新建端点名称应为空，实际 %r' % name_val
        else:
            assert url_val == FAKE_ENDPOINT, '旧侧应预填假端点，实际 %r' % url_val
        shot(drv, artifacts, '06_%s_create_endpoints_light.png' % mode)
        close_sheet(drv)
        report['steps'].append('⑧ 新建维度端点：url=%r name=%r' % (url_val, name_val))

        report['ok'] = True
    except Exception as exc:  # noqa: BLE001
        report['ok'] = False
        report['error'] = repr(exc)
        try:
            shot(drv, artifacts, '99_%s_failure.png' % mode)
            report['visible_text'] = drv.find_element(By.TAG_NAME, 'body').text[:3000]
        except Exception:
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
        report_path = os.path.join(artifacts, 'run.log')
        with open(report_path, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
