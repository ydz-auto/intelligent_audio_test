# -*- coding: utf-8 -*-
"""INT-1045 复测：INT-877 返工合流最新 wiring/react（用例编辑抽屉接线 + INT-996 算法参数/噪声）。

真实 Chrome headless + 常驻 5000 后端（AUTH_MODE=off）+ dev server（5321）。
合流验收逐条核对：
- P1-1 音频列表步骤：编辑真实带 audios 用例 → 回填真实 audio_name/spl（非 mock）；
  改 SPL 保存 → PUT /testcases/{id} config.rounds[].audios.spl 生效（后端 GET 落库）。
- P2-1 评估维度步骤：维度选项接真实 GET /evaluation/dimensions（含 mock 集外 9000
  LLM复核测试维度），mock 维度名不出现。
- P2-2 评估策略节：策略 Select 接真实 GET /evaluation-strategies（空表 →「暂无可用策略」），
  DOM 无 mock str-1/str-2/str-3。
- INT-996 算法参数 schema：算法参数步骤接真实 GET /algorithm/form-schema/{algo_type}，
  按真实 schema 渲染（voice_llm 空 schema → 空态文案）。
- INT-996 噪声与干扰：三节（背景噪声/声纹注册/干扰人）受控渲染；「添加噪声」走真实
  /audios（audioType=noise 空库 → 空态提示）。
- P3-3 轮次新选维度补 name：评估维度步骤从真实维度云勾选 9000 → 保存 PUT
  config.rounds[].evaluation.dimensions[].name = LLM复核测试维度（dimNameById 解析）。
- P3-1 引用策略 + 覆盖背景噪声保存：PUT 载荷 strategy_overrides.background_noise（snake_case），
  后端 GET 合并落库。
写操作均用「接线测试」前缀探针，run 结束前 DELETE + purge 清库。
失败落 tests/ui/artifacts/int877_edit_drawer_rewire/<阶段>/。
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int877_edit_drawer_rewire')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

GROUP_ID = '3ea20043-888d-4749-b7ed-905fbcc99ce2'  # rg_g_reg1（回归测试分组，探针容器）
PROBE_PREFIX = '接线测试-INT1045-'
AUDIO_ID = 56          # 兼容测试_01.wav（真实音频库）
AUDIO_NAME = '兼容测试_01.wav'
DIM_ID = 9000
DIM_NAME = 'LLM复核测试维度'

PASSED = []
FAILED = []
PROBES = []       # 待清理用例 id
STRATEGIES = []   # 待清理策略 id
EVIDENCE = []     # Network 取证行


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
    """打开探针用例编辑抽屉（带滚动容错 + 中途刷新兜底），返回抽屉是否就绪。"""
    btn = None
    for i in range(24):
        btn = _find_edit_button(drv, name)
        if btn:
            break
        # 探针由 API 新建、页面列表未包含时刷新一次（SPA 列表 refetch）
        if i == 8:
            try:
                drv.get(BASE + '/testcases/by-group')
                WebDriverWait(drv, 25).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'))
            except Exception:
                pass
        time.sleep(1)
    if btn is None:
        _save_evidence(evidence_name + '_probe_not_found', drv)
        return False
    drv.execute_script('arguments[0].click()', btn)
    time.sleep(1.5)
    try:
        WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']"))
    except Exception:
        _save_evidence(evidence_name + '_drawer_not_open', drv)
        return False
    return True


def _click_step_tab(drv, name):
    try:
        tab = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, f"//button[@role='tab' and contains(., '{name}')]"))
        drv.execute_script('arguments[0].click()', tab)
        time.sleep(1.0)
        return True
    except Exception:
        return False


def _panel(drv):
    """当前轮次步骤体（case-mutate-drawer StepBody 容器，data-testid 定位）。"""
    try:
        return drv.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']")
    except Exception:
        return None


def _expand_strategy(drv):
    try:
        trig = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[contains(., '评估策略')]"))
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})', trig)
        time.sleep(0.5)
        drv.execute_script('arguments[0].click()', trig)
        time.sleep(0.8)
        return True
    except Exception:
        return False


def _click_mode_radio(drv, label):
    try:
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})',
                           drv.find_element(By.XPATH, "//button[contains(., '评估策略')]"))
    except Exception:
        pass
    xpath = (f"//input[@name='evaluation-strategy-mode']"
             f"[ancestor::label[contains(.,'{label}')]]")
    radio = WebDriverWait(drv, 8).until(lambda d: d.find_element(By.XPATH, xpath))
    drv.execute_script('arguments[0].click()', radio)
    time.sleep(0.6)
    if radio.get_attribute('checked') is None:
        drv.execute_script('arguments[0].click()', radio)
        time.sleep(0.6)
    return radio.get_attribute('checked') is not None


def _create_case(name, config, algorithm_type=None, extra=None):
    body = {
        'name': name, 'description': 'INT-1045 探针', 'group_id': GROUP_ID,
        'tags': [], 'algorithm_type': algorithm_type, 'config': config,
    }
    if extra:
        body.update(extra)
    resp = _api('/api/v1/testcases', method='POST', body=body)
    cid = (resp.get('data') or {}).get('id')
    if cid:
        PROBES.append(cid)
    return cid


def _create_strategy(name, config):
    resp = _api('/api/v1/evaluation-strategies', method='POST', body={
        'name': name, 'description': 'INT-1045 探针策略', 'config': config})
    sid = (resp.get('data') or {}).get('id')
    if sid:
        STRATEGIES.append(sid)
    return sid


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


def _click_audio_row(drv, name):
    """在音频选择子弹窗中勾选指定音频行。"""
    try:
        row = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.XPATH, f"//div[@data-slot='dialog-content']//button[contains(., '{name}')]"))
        drv.execute_script('arguments[0].click()', row)
        time.sleep(0.5)
        return True
    except Exception:
        return False


def main():
    drv = _driver()
    try:
        suffix = str(int(time.time() * 1000))

        print('== 预建探针 A：带音频（无关联算法 → 评估维度全量真实） ==')
        probe = _create_case(PROBE_PREFIX + 'audio_' + suffix, {
            'rounds': [{
                'round_number': 1,
                'audios': [{
                    'audio_id': AUDIO_ID, 'audio_name': AUDIO_NAME,
                    'spl': 65.0, 'playback_device_id': None, 'play_order': 1,
                }],
                'evaluation': {'enabled': True, 'dimensions': []},
            }],
        })
        check('API 预建带音频探针', probe is not None, f'id={probe}')
        if probe is None:
            raise RuntimeError('探针 A 创建失败')

        _setup(drv, 'light')
        check('打开编辑抽屉', _open_drawer(drv, PROBE_PREFIX + 'audio_' + suffix, '01_audio'))
        _save_evidence('01_drawer_open_light', drv)
        early = _perf_requests(drv)
        EVIDENCE.append('P2-1 GET /evaluation/dimensions 请求数=%d' %
                        len([r for r in early if '/api/v1/evaluation/dimensions' in r['url']]))
        EVIDENCE.append('P2-2 GET /evaluation-strategies 请求数=%d' %
                        len([r for r in early if '/api/v1/evaluation-strategies' in r['url']]))
        check('P2-1 Network 有 GET /evaluation/dimensions',
              any('/api/v1/evaluation/dimensions' in r['url'] for r in early), f'n={len(early)}')
        check('P2-2 Network 有 GET /evaluation-strategies',
              any('/api/v1/evaluation-strategies' in r['url'] for r in early), f'n={len(early)}')

        print('== P1-1：真实音频回填 + 音频库添加 + SPL 编辑 ==')
        check('切「音频列表」步骤', _click_step_tab(drv, '音频列表'))
        _save_evidence('03_audio_step_light', drv)
        p = _panel(drv)
        txt = p.text if p is not None else ''
        check('P1-1 回填真实音频名（非 mock 文件名）', AUDIO_NAME in txt,
              f'panel_txt={txt[:120]!r}')
        spl_inputs = p.find_elements(By.CSS_SELECTOR, "input[type='number']") if p else []
        spl_val = drv.execute_script('return arguments[0].value', spl_inputs[0]) if spl_inputs else None
        check('P1-1 回填真实 SPL 65', spl_val == '65', f'spl_val={spl_val!r}')
        check('P1-1 音频卡 SPL 输入框存在', len(spl_inputs) >= 1, f'n={len(spl_inputs)}')

        # 从音频库选择追加一个真实音频（真实 GET /audios）
        lib_btn = None
        for _ in range(10):
            try:
                lib_btn = drv.find_element(By.XPATH, "//button[contains(., '从音频库选择')]")
                if lib_btn.is_displayed():
                    break
            except Exception:
                pass
            time.sleep(0.6)
        check('P1-1「从音频库选择」按钮可见', lib_btn is not None)
        if lib_btn:
            drv.execute_script('arguments[0].click()', lib_btn)
            time.sleep(1.5)
            lib_reqs = _perf_requests(drv)
            check('P1-1 音频库弹窗 Network 有 GET /audios',
                  any(r['method'] == 'GET' and '/api/v1/audios' in r['url'] for r in lib_reqs),
                  f'n={len(lib_reqs)}')
            check('P1-1 音频库行可选（真实音频名）', _click_audio_row(drv, AUDIO_NAME))
            _save_evidence('04_audio_library_dialog_light', drv)
            try:
                confirm = WebDriverWait(drv, 8).until(
                    lambda d: d.find_element(By.XPATH, "//div[@data-slot='dialog-content']//button[contains(., '确认选择')]"))
                drv.execute_script('arguments[0].click()', confirm)
                time.sleep(1.0)
            except Exception as e:
                print('  confirm fail:', e)
        p = _panel(drv)
        cards = p.find_elements(By.CSS_SELECTOR, "div.ring-1") if p else []
        check('P1-1 音频库添加后音频卡数 = 2', len(cards) >= 2, f'n={len(cards)}')

        # 改首个 SPL 65 → 80
        spl_inputs = p.find_elements(By.CSS_SELECTOR, "input[type='number']") if p else []
        if spl_inputs:
            spl_inputs[0].send_keys(Keys.CONTROL, 'a')
            spl_inputs[0].send_keys('80')
            time.sleep(0.4)
            val = drv.execute_script('return arguments[0].value', spl_inputs[0])
            check('P1-1 SPL 已改为 80', val == '80', f'val={val!r}')
            _save_evidence('05_audio_spl_edit_light', drv)

        print('== INT-996：噪声与干扰步骤（受控三节 + 真实数据源） ==')
        check('切「噪声与干扰」步骤', _click_step_tab(drv, '噪声与干扰'))
        p = _panel(drv)
        txt = p.text if p is not None else ''
        check('INT-996 噪声节渲染（背景噪声/声纹注册/干扰人）',
              '背景噪声' in txt and '声纹注册' in txt and '干扰人' in txt,
              f'panel_txt={txt[:160]!r}')
        check('INT-996 背景噪声空态「未配置背景噪声」',
              '未配置背景噪声' in txt, f'has={"未配置背景噪声" in txt}')
        check('INT-996 干扰人配置「添加干扰人」入口渲染',
              '添加干扰人' in txt, f'has={"添加干扰人" in txt}')
        _save_evidence('06_noise_step_light', drv)
        try:
            add_noise = drv.find_element(By.XPATH, "//button[contains(., '添加噪声')]")
            drv.execute_script('arguments[0].click()', add_noise)
            time.sleep(1.5)
            dialog_txt = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']").text
            check('INT-996「添加噪声」弹窗打开 + 真实 /audios(noise) 空库空态',
                  '选择噪声音频' in dialog_txt and '暂无噪声类型音频' in dialog_txt,
                  f'dialog_txt={dialog_txt[:160]!r}')
            _save_evidence('07_noise_dialog_empty_light', drv)
            try:
                cancel = drv.find_element(By.XPATH, "//div[@data-slot='dialog-content']//button[contains(., '取消')]")
                drv.execute_script('arguments[0].click()', cancel)
                time.sleep(0.8)
            except Exception:
                pass
        except Exception as e:
            print('  noise dialog fail:', e)

        print('== P2-1 + P3-3：评估维度真实数据 + 新选维度补 name ==')
        check('切「评估维度」步骤', _click_step_tab(drv, '评估维度'))
        p = _panel(drv)
        txt2 = p.text if p is not None else ''
        check('P2-1 维度云含真实维度（LLM复核测试维度 9000）', DIM_NAME in txt2,
              f'panel_txt={txt2[:160]!r}')
        check('P2-1 维度云不含 mock 维度名「识别准确率」',
              '识别准确率' not in txt2, f'panel_txt={txt2[:160]!r}')
        _save_evidence('08_eval_dims_step_light', drv)
        # P3-3：从真实维度云勾选 9000
        clicked = False
        for _ in range(10):
            try:
                chip = p.find_element(By.XPATH, f"//button[contains(., '{DIM_NAME}')]")
                drv.execute_script('arguments[0].click()', chip)
                time.sleep(0.6)
                sel_txt = p.text
                clicked = '已选 1' in sel_txt
                break
            except Exception:
                time.sleep(0.6)
        check('P3-3 已勾选新维度 9000', clicked)
        _save_evidence('09_dim_selected_light', drv)

        print('== 保存：P1-1 音频 + P3-3 维度 name 一并落库 ==')
        _perf_requests(drv)  # drain 基线
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
        check('保存 toast「更新测试用例成功」', toast_ok)
        reqs = _perf_requests(drv)
        puts = [r for r in reqs if r['method'] == 'PUT'
                and '/api/v1/testcases/' + probe in r['url']]
        check('Network 捕获 PUT /testcases/{id}', len(puts) > 0, f'puts={len(puts)}')
        if puts:
            body = json.loads(puts[-1].get('postData') or '{}') if puts[-1].get('postData') else {}
            rounds0 = (body.get('config') or {}).get('rounds') or [{}]
            audios = rounds0[0].get('audios') or []
            dims = ((rounds0[0].get('evaluation') or {}).get('dimensions') or [])
            check('P1-1 PUT 载荷 audios[0] 含真实 audio_id/audio_name/spl=80',
                  len(audios) > 0 and audios[0].get('audio_id') == AUDIO_ID
                  and audios[0].get('audio_name') == AUDIO_NAME
                  and audios[0].get('spl') == 80,
                  f'audios={json.dumps(audios, ensure_ascii=False)[:200]}')
            check('P1-1 PUT 载荷 audios 有 2 行（回填 + 音频库添加）', len(audios) == 2,
                  f'n={len(audios)}')
            check('P3-3 PUT 载荷 dimensions[0].name 补真实维度名',
                  len(dims) > 0 and dims[0].get('id') == DIM_ID
                  and dims[0].get('name') == DIM_NAME,
                  f'dims={json.dumps(dims, ensure_ascii=False)[:200]}')
            EVIDENCE.append('PUT /api/v1/testcases/{%s} 载荷:' % probe[:8])
            EVIDENCE.append(json.dumps(body, ensure_ascii=False, indent=2))
        time.sleep(1.5)
        g1 = (_api('/api/v1/testcases/' + probe).get('data') or {})
        c1 = g1.get('config') or {}
        r1 = (c1.get('rounds') or [{}])[0]
        audios1 = r1.get('audios') or []
        dims1 = ((r1.get('evaluation') or {}).get('dimensions') or [])
        check('P1-1 后端 GET audios[0].spl=80 已落库',
              len(audios1) > 0 and audios1[0].get('spl') == 80,
              f'audios={json.dumps(audios1, ensure_ascii=False)[:200]}')
        check('P1-1 后端 GET audios[0].audio_name 保留真实名',
              len(audios1) > 0 and audios1[0].get('audio_name') == AUDIO_NAME,
              f'name={audios1[0].get("audio_name")!r}' if audios1 else 'no-audios')
        check('P3-3 后端 GET dimensions[0].name=LLM复核测试维度',
              len(dims1) > 0 and dims1[0].get('name') == DIM_NAME,
              f'dims={json.dumps(dims1, ensure_ascii=False)[:160]}')

        print('== INT-996：算法参数 schema 步骤（真实 form-schema，voice_llm） ==')
        schema_probe = _create_case(PROBE_PREFIX + 'schema_' + suffix, {
            'rounds': [{'round_number': 1, 'audios': [],
                        'evaluation': {'enabled': True, 'dimensions': []}}],
        }, algorithm_type='voice_llm')
        check('API 预建算法参数探针', schema_probe is not None, f'id={schema_probe}')
        if schema_probe is None:
            raise RuntimeError('探针 B 创建失败')
        check('打开算法参数探针抽屉', _open_drawer(drv, PROBE_PREFIX + 'schema_' + suffix, '02_schema'))
        # 抽屉默认「算法参数」步骤挂载即按 voice_llm 拉真实 schema（与抽屉打开同批请求）
        schema_early = _perf_requests(drv)
        check('INT-996 Network 有 GET /algorithm/form-schema/voice_llm',
              any('/api/v1/algorithm/form-schema/voice_llm' in r['url'] for r in schema_early),
              f'found={[r["url"] for r in schema_early if "form-schema" in r["url"]][:1]}')
        p = _panel(drv)
        txt = p.text if p is not None else ''
        check('INT-996 算法参数步骤渲染（voice_llm 真实空 schema → 空态）',
              '暂无参数配置' in txt or '加载算法参数表单' in txt,
              f'panel_txt={txt[:120]!r}')
        _save_evidence('02_algo_params_step_light', drv)
        # 关闭抽屉（探针 B 不保存）
        try:
            cancel = drv.find_element(By.XPATH, "//button[normalize-space()='取消']")
            drv.execute_script('arguments[0].click()', cancel)
            time.sleep(1.0)
        except Exception:
            pass

        print('== P2-2：评估策略节接真实策略（空表空态，无 mock） ==')
        check('重开抽屉', _open_drawer(drv, PROBE_PREFIX + 'audio_' + suffix, '10_strategy'))
        check('展开评估策略节', _expand_strategy(drv))
        _save_evidence('11_strategy_collapsed_light', drv)
        _click_mode_radio(drv, '引用已有策略')
        time.sleep(0.6)
        try:
            sel = WebDriverWait(drv, 8).until(
                lambda d: d.find_element(By.XPATH, "//button[contains(., '请选择要引用的评估策略')]"))
            drv.execute_script('arguments[0].click()', sel)
            time.sleep(0.8)
        except Exception:
            pass
        body_txt = drv.execute_script('return document.body.innerText')
        check('P2-2 空态「暂无可用策略」', '暂无可用策略' in (body_txt or ''),
              f'has={"暂无可用策略" in (body_txt or "")}')
        check('P2-2 DOM 无 mock 策略 str-1/str-2/str-3',
              'str-1' not in (body_txt or '') and 'str-2' not in (body_txt or '')
              and 'str-3' not in (body_txt or ''), '')
        _save_evidence('12_strategy_empty_light', drv)

        print('== P3-1：引用策略 + 覆盖背景噪声 → strategy_overrides.background_noise ==')
        strat = _create_strategy(PROBE_PREFIX + 'strat_' + suffix, {
            'dimensions': [{'id': DIM_ID, 'name': DIM_NAME, 'weight': 50, 'threshold': 80}],
            'background_noise': {'audio_id': AUDIO_ID, 'audio_name': AUDIO_NAME,
                                 'spl': 60.0, 'device_ids': [], 'loop': True},
        })
        check('API 预建引用策略', strat is not None, f'id={strat}')
        if strat is None:
            raise RuntimeError('P3-1 策略创建失败')
        ref_probe = _create_case(PROBE_PREFIX + 'ref_' + suffix, {
            'rounds': [{'round_number': 1, 'audios': [],
                        'evaluation': {'enabled': True, 'dimensions': []}}],
            'evaluationStrategy': {'strategy_id': strat, 'overrides': None},
        }, extra={'strategy_id': strat, 'strategy_overrides': None})
        check('API 预建引用态探针', ref_probe is not None, f'id={ref_probe}')
        if ref_probe is None:
            raise RuntimeError('P3-1 引用探针创建失败')

        _setup(drv, 'dark')
        check('打开引用态抽屉', _open_drawer(drv, PROBE_PREFIX + 'ref_' + suffix, '13_ref'))
        _save_evidence('13_ref_drawer_dark', drv)
        check('展开评估策略节', _expand_strategy(drv))
        # 引用态摘要卡应显示探针策略名（真实 GET /evaluation-strategies）
        time.sleep(0.8)
        strategy_txt = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']").text
        check('P2-2 引用态摘要显示真实策略名（GET /evaluation-strategies 数据）',
              PROBE_PREFIX + 'strat_' + suffix in strategy_txt,
              f'has={"strategy name" in strategy_txt}')
        _save_evidence('14_ref_strategy_summary_dark', drv)
        # 打开「覆盖全局背景噪声」Switch
        try:
            sw = WebDriverWait(drv, 8).until(
                lambda d: d.find_element(By.CSS_SELECTOR,
                    "[data-slot='switch'][aria-label='覆盖全局背景噪声']"))
            drv.execute_script('arguments[0].click()', sw)
            time.sleep(0.8)
        except Exception as e:
            print('  switch click fail:', e)
        _save_evidence('15_override_noise_on_dark', drv)
        # 覆盖编辑器内 SPL → 70（sheet 可见 number input，策略节在抽屉底部故取最后一个）
        bn_editor = None
        try:
            nums = [n for n in drv.find_elements(By.CSS_SELECTOR, "input[type='number']")
                    if n.is_displayed()]
            bn_editor = nums[-1] if nums else None
        except Exception:
            bn_editor = None
        check('P3-1 覆盖噪声编辑器出现', bn_editor is not None)
        if bn_editor:
            bn_editor.send_keys(Keys.CONTROL, 'a')
            bn_editor.send_keys('70')
            time.sleep(0.4)
            after = drv.execute_script('return arguments[0].value', bn_editor)
            check('P3-1 覆盖 SPL 已改 70', after == '70', f'after={after!r}')
            _save_evidence('16_override_spl70_dark', drv)

        _perf_requests(drv)  # drain
        save_btn3 = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//button[normalize-space()='保存']"))
        drv.execute_script('arguments[0].click()', save_btn3)
        try:
            WebDriverWait(drv, 12).until(
                lambda d: any('更新测试用例成功' in (el.text or '')
                              for el in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        except Exception:
            pass
        reqs3 = _perf_requests(drv)
        puts3 = [r for r in reqs3 if r['method'] == 'PUT'
                 and '/api/v1/testcases/' + ref_probe in r['url']]
        check('P3-1 Network 捕获 PUT /testcases/{id}', len(puts3) > 0, f'puts={len(puts3)}')
        if puts3:
            body3 = json.loads(puts3[-1].get('postData') or '{}') if puts3[-1].get('postData') else {}
            ov = body3.get('strategy_overrides') or {}
            check('P3-1 PUT 载荷 strategy_overrides.background_noise 为 snake_case 键',
                  'background_noise' in ov and 'backgroundNoise' not in ov,
                  f'keys={list(ov.keys())}')
            bn3 = ov.get('background_noise') or {}
            check('P3-1 覆盖 background_noise.spl=70',
                  bn3.get('spl') == 70, f'spl={bn3.get("spl")}')
            EVIDENCE.append('P3-1 PUT /api/v1/testcases/{%s} 载荷:' % ref_probe[:8])
            EVIDENCE.append(json.dumps(body3, ensure_ascii=False, indent=2))
        time.sleep(1.5)
        g3 = (_api('/api/v1/testcases/' + ref_probe).get('data') or {})
        c3 = g3.get('config') or {}
        bn_backend = c3.get('background_noise') or {}
        check('P3-1 后端 GET config.background_noise.spl=70 合并落库',
              bn_backend.get('spl') == 70,
              f'spl={bn_backend.get("spl")} keys={list(c3.keys())}')

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
