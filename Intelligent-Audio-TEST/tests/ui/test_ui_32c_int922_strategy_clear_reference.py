# -*- coding: utf-8 -*-
"""INT-922 返工复测（代码审计 P2：策略节显式「不使用/新建」必须清引用）。

真实 Chrome headless + 常驻 5000 后端（AUTH_MODE=off）+ dev server（默认 5321）。
P2 根因：抽屉保存 mode='none'/'create' 分支发 strategy_id:null → 后端「沿用既有引用」，
旧策略重新物化覆盖用户选择；只有显式空字符串 '' 才清引用（testcase_crud_service.py
_resolve_strategy_config）。
- P2-A（UI 'none'）：引用态探针（strategy_id 非空）打开抽屉 → 选「不使用评估策略」→ 保存
  → PUT 载荷 strategy_id 为空字符串 + 后端 GET strategy_id 空、config 无旧策略物化残留。
- P2-B（UI 'create'）：引用态探针 → 选「新建策略」→ 保存 → PUT 载荷 strategy_id 空字符串
  + config 写内联 dims/background_noise；GET 引用清、内联配置落库不被旧策略物化覆盖。
- 数据卫生：探针用例（API 预建）与探针策略结束前 DELETE + purge 清库。
失败落 tests/ui/artifacts/int922_strategy_clear_reference/<阶段>/。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int922_strategy_clear_reference')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

GROUP_ID = '3ea20043-888d-4749-b7ed-905fbcc99ce2'   # rg_g_reg1（回归测试分组，探针容器）
GROUP_NAME = 'rg_g_reg1'
PROBE_PREFIX = 'int922_refprobe_'
STRAT_PREFIX = 'int922_refstrat_'
DIM = {'id': 5, 'name': '逐轮话轮评估', 'weight': 50, 'threshold': 80}
BN = {'audio_id': None, 'spl': 60.0, 'device_ids': [], 'loop': True}

PASSED = []
FAILED = []
PROBES = []      # 待清理用例 id
STRATEGIES = []  # 待清理策略 id
EVIDENCE = []    # Network 取证行（写 artifacts/network_evidence.txt）


def check(name, cond, extra=''):
    if cond:
        PASSED.append(name)
        print(f'  PASS {name}')
    else:
        FAILED.append(name)
        print(f'  FAIL {name}  {extra}')


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _perf_requests(drv):
    reqs = []
    try:
        for entry in drv.get_log('performance'):
            try:
                outer = json.loads(entry['message'])
                inner = outer.get('message', {})
                if inner.get('method') == 'Network.requestWillBeSent':
                    r = inner['params']['request']
                    reqs.append({'method': r.get('method'), 'url': r.get('url'),
                                 'postData': r.get('postData', '')})
            except Exception:
                pass
    except Exception:
        pass
    return reqs


def _api(path, method='GET', body=None):
    req = urllib.request.Request('http://localhost:5000' + path, method=method)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _setup(drv, theme):
    drv.get(BASE + '/')
    time.sleep(2)
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "localStorage.setItem('iatp:algorithm:v1',"
        " JSON.stringify({state:{algorithmId:''},version:0}));",
        theme)
    drv.get(BASE + '/testcases/by-group')
    WebDriverWait(drv, 25).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'))


def _find_edit_button(drv, name):
    buttons = drv.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]')
    for btn in buttons:
        node = btn
        html = ''
        for _ in range(6):
            node = node.find_element(By.XPATH, '..')
            html = node.get_attribute('innerHTML') or ''
            if name in html:
                return btn
    return None


def _open_drawer(drv, name, evidence_name):
    """打开探针用例编辑抽屉（带滚动容错），返回抽屉内评估策略节触发器。"""
    btn = None
    for _ in range(20):
        btn = _find_edit_button(drv, name)
        if btn:
            break
        time.sleep(1)
    if btn is None:
        _save_evidence(evidence_name + '_probe_not_found', drv)
        return None
    drv.execute_script('arguments[0].click()', btn)
    time.sleep(1.5)
    # 策略节在抽屉底部 ScrollArea 内，先滚到可见再展开
    trig = None
    try:
        trig = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH,
                "//button[contains(.,'评估策略')]"))
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})', trig)
        time.sleep(0.5)
    except Exception:
        pass
    return trig


def _click_mode_radio(drv, label):
    """展开策略节后点击三模式单选（直接点 input，带选中态校验重试——label 程序化点击偶发不激活）。"""
    drv.execute_script('arguments[0].scrollIntoView({block:"center"})',
                       drv.find_element(By.XPATH, "//button[contains(.,'评估策略')]"))
    xpath = (f"//input[@name='evaluation-strategy-mode']"
             f"[ancestor::label[contains(.,'{label}')]]")
    radio = WebDriverWait(drv, 8).until(lambda d: d.find_element(By.XPATH, xpath))
    drv.execute_script('arguments[0].click()', radio)
    time.sleep(0.6)
    # 校验选中态；未选中重试一次
    if radio.get_attribute('checked') is None:
        drv.execute_script('arguments[0].click()', radio)
        time.sleep(0.6)
    return radio.get_attribute('checked') is not None


def _create_strategy(name):
    resp = _api('/api/v1/evaluation-strategies', method='POST', body={
        'name': name, 'description': 'INT-922 引用态探针策略',
        'config': {'dimensions': [DIM], 'background_noise': BN}})
    sid = (resp.get('data') or {}).get('id')
    if sid:
        STRATEGIES.append(sid)
    return sid


def _create_ref_probe(name, sid):
    body = {
        'name': name, 'description': 'INT-922 引用态探针',
        'group_id': GROUP_ID, 'tags': [],
        'algorithm_type': 'voice_llm',
        'strategy_id': sid, 'strategy_overrides': None,
        'config': {
            'rounds': [{'round_number': 1, 'audios': [],
                        'evaluation': {'enabled': True, 'dimensions': []}}],
            'evaluationStrategy': {'strategy_id': sid, 'overrides': None}},
    }
    resp = _api('/api/v1/testcases', method='POST', body=body)
    cid = (resp.get('data') or {}).get('id')
    if cid:
        PROBES.append(cid)
    return cid


def _cleanup():
    for cid in PROBES:
        try:
            _api(f'/api/v1/testcases/{cid}', method='DELETE')
        except Exception:
            pass
    for cid in PROBES:
        try:
            _api(f'/api/v1/testcases/{cid}/purge', method='DELETE')
        except Exception:
            pass
    PROBES.clear()
    for sid in STRATEGIES:
        try:
            _api(f'/api/v1/evaluation-strategies/{sid}', method='DELETE')
        except Exception:
            pass
    STRATEGIES.clear()


def main():
    drv = _driver()
    try:
        suffix = str(int(time.time() * 1000))

        print('== P2-A：引用态探针 → UI 选「不使用评估策略」→ 保存清引用 ==')
        strat_a = _create_strategy(STRAT_PREFIX + suffix)
        check('API 预建引用策略', strat_a is not None, f'id={strat_a}')
        if strat_a is None:
            raise RuntimeError('策略创建失败')
        probe_a = _create_ref_probe(PROBE_PREFIX + 'a_' + suffix, strat_a)
        check('API 预建引用态用例', probe_a is not None, f'id={probe_a}')
        if probe_a is None:
            raise RuntimeError('引用态用例创建失败')
        g0 = (_api('/api/v1/testcases/' + probe_a).get('data') or {})
        check('P2-A0 探针确实带引用', g0.get('strategy_id') == strat_a,
              f'strategy_id={g0.get("strategy_id")}')

        _setup(drv, 'light')
        trig = _open_drawer(drv, PROBE_PREFIX + 'a_' + suffix, '01a')
        check('P2-A1 打开引用态用例编辑抽屉', trig is not None)
        if trig is None:
            raise RuntimeError('抽屉打开失败')
        try:
            drv.execute_script('arguments[0].click()', trig)
            time.sleep(0.8)
        except Exception:
            pass
        _save_evidence('01a_drawer_open_light', drv)
        none_sel = _click_mode_radio(drv, '不使用评估策略')
        check('P2-A1b 单选「不使用评估策略」已选中', none_sel)
        _save_evidence('02a_mode_none_selected_light', drv)

        _perf_requests(drv)  # drain 基线
        # 精确匹配抽屉底部「保存」（create 内联表单含「保存策略并引用」，contains 会误中）
        save_btn = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[normalize-space()='保存']"))
        drv.execute_script('arguments[0].click()', save_btn)
        toast_ok = False
        try:
            WebDriverWait(drv, 12).until(
                lambda d: any('更新测试用例成功' in (el.text or '')
                              for el in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
            toast_ok = True
        except Exception:
            pass
        check('P2-A2 保存 toast「更新测试用例成功」', toast_ok)

        reqs = _perf_requests(drv)
        puts = [r for r in reqs if r['method'] == 'PUT'
                and '/api/v1/testcases/' + probe_a in r['url']]
        check('P2-A3 Network 捕获 PUT /testcases/{id}', len(puts) > 0, f'puts={len(puts)}')
        if puts:
            body = json.loads(puts[-1].get('postData') or '{}') if puts[-1].get('postData') else {}
            check('P2-A4 PUT 载荷 strategy_id 为空字符串', body.get('strategy_id') == '',
                  f'strategy_id={body.get("strategy_id")!r}')
            cfg = body.get('config') or {}
            check('P2-A5 PUT 载荷 config 不含旧策略物化字段',
                  'dimensions' not in cfg and 'background_noise' not in cfg
                  and 'evaluationStrategy' not in cfg,
                  f'config keys={list(cfg.keys())}')
            EVIDENCE.append('P2-A mode=none PUT /api/v1/testcases/{%s} 载荷:' % probe_a[:8])
            EVIDENCE.append(json.dumps(body, ensure_ascii=False, indent=2))
        time.sleep(1.5)
        g1 = (_api('/api/v1/testcases/' + probe_a).get('data') or {})
        c1 = g1.get('config') or {}
        check('P2-A6 后端 GET strategy_id 已清空',
              g1.get('strategy_id') in (None, ''),
              f'strategy_id={g1.get("strategy_id")!r}')
        check('P2-A7 后端 config 无旧策略物化残留',
              (c1.get('dimensions') or []) == []
              and c1.get('background_noise') in (None, )
              and c1.get('evaluationStrategy') in (None, ),
              f'dims={json.dumps(c1.get("dimensions"), ensure_ascii=False)[:120]} '
              f'bn={c1.get("background_noise")} ev={c1.get("evaluationStrategy")}')

        print('== P2-B：引用态探针 → UI 选「新建策略」→ 保存内联并清引用 ==')
        strat_b = _create_strategy(STRAT_PREFIX + 'b_' + suffix)
        check('P2-B0 API 预建引用策略', strat_b is not None, f'id={strat_b}')
        probe_b = _create_ref_probe(PROBE_PREFIX + 'b_' + suffix, strat_b) if strat_b else None
        check('P2-B0 API 预建引用态用例', probe_b is not None, f'id={probe_b}')
        if probe_b is None:
            raise RuntimeError('P2-B 探针创建失败')

        _setup(drv, 'dark')
        trig_b = _open_drawer(drv, PROBE_PREFIX + 'b_' + suffix, '01b')
        check('P2-B1 打开引用态用例编辑抽屉', trig_b is not None)
        if trig_b is None:
            raise RuntimeError('P2-B 抽屉打开失败')
        try:
            drv.execute_script('arguments[0].click()', trig_b)
            time.sleep(0.8)
        except Exception:
            pass
        _save_evidence('02b_drawer_open_dark', drv)
        create_sel = _click_mode_radio(drv, '新建策略')
        check('P2-B1b 单选「新建策略」已选中', create_sel)
        _save_evidence('03b_mode_create_selected_dark', drv)

        _perf_requests(drv)  # drain 基线
        save_btn2 = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[normalize-space()='保存']"))
        drv.execute_script('arguments[0].click()', save_btn2)
        toast_ok2 = False
        try:
            WebDriverWait(drv, 12).until(
                lambda d: any('更新测试用例成功' in (el.text or '')
                              for el in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
            toast_ok2 = True
        except Exception:
            pass
        check('P2-B2 保存 toast「更新测试用例成功」', toast_ok2)

        reqs2 = _perf_requests(drv)
        puts2 = [r for r in reqs2 if r['method'] == 'PUT'
                 and '/api/v1/testcases/' + probe_b in r['url']]
        check('P2-B3 Network 捕获 PUT /testcases/{id}', len(puts2) > 0, f'puts={len(puts2)}')
        if puts2:
            body2 = json.loads(puts2[-1].get('postData') or '{}') if puts2[-1].get('postData') else {}
            check('P2-B4 PUT 载荷 strategy_id 为空字符串', body2.get('strategy_id') == '',
                  f'strategy_id={body2.get("strategy_id")!r}')
            cfg2 = body2.get('config') or {}
            check('P2-B5 PUT 载荷 config 写内联 dims/background_noise',
                  (cfg2.get('dimensions') or []) != [] and cfg2.get('background_noise') is not None,
                  f'config keys={list(cfg2.keys())}')
            EVIDENCE.append('P2-B mode=create PUT /api/v1/testcases/{%s} 载荷:' % probe_b[:8])
            EVIDENCE.append(json.dumps(body2, ensure_ascii=False, indent=2))
        time.sleep(1.5)
        g2 = (_api('/api/v1/testcases/' + probe_b).get('data') or {})
        c2 = g2.get('config') or {}
        check('P2-B6 后端 GET strategy_id 已清空',
              g2.get('strategy_id') in (None, ''),
              f'strategy_id={g2.get("strategy_id")!r}')
        dims2 = c2.get('dimensions') or []
        bn2 = c2.get('background_noise') or {}
        check('P2-B7 后端内联配置落库（dims id=5 + 噪声 spl=60.0）',
              any(str(d.get('id')) == '5' for d in dims2) and bn2.get('spl') == 60.0,
              f'dims={json.dumps(dims2, ensure_ascii=False)[:160]} bn_spl={bn2.get("spl")}')

        fatal = [e for e in drv.get_log('browser')
                 if e.get('level') in ('SEVERE', 'ERROR')
                 and 'Failed to load resource' not in str(e.get('message', ''))]
        check('无 console 严重错误', len(fatal) == 0, f'fatal={len(fatal)}')

        if EVIDENCE:
            d = os.path.join(ARTIFACTS, 'network_evidence')
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'network_evidence.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(EVIDENCE))

        print(f'\n=== 结果：PASS {len(PASSED)} / FAIL {len(FAILED)} ===')
        for f in FAILED:
            print('  FAILED:', f)
        if FAILED:
            sys.exit(2)
    finally:
        try:
            _cleanup()
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
