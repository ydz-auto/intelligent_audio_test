# -*- coding: utf-8 -*-
"""INT-875 首页/工作台真实数据走查 浏览器实测（React wiring，测试工程师验收）。

范围（INT-875 验收清单）：
① 首页规模条 StatsBar 真实数据渲染——Network /api/v1/home/stats/details 返回 snake_case，
   页面按 camelCase 正常显示六项指标，无崩溃（验证 INT-845 修复已集成到被测树）
② 工作台 platform-summary——最近任务 / 常用分组（用例分组排行）显示真实数据
   （Network /api/v1/home/stats/details + /summary）
③ 设置引导 useSetupGuide 正常——完成度来自真实 details、展开/折叠 + localStorage 持久化
④ 浅色 + 深色 + Network 截图/证据

被测树 = wiring/react HEAD（72496822）+ INT-845 修复（cherry-pick 2e1123ec）。
环境：dev server http://localhost:5325（/api 代理 → 常驻 :5000，AUTH_MODE=off →
/auth/me 回填 dev_user('*') 放行，无需登录）。

失败落 tests/ui/artifacts/int875/<步骤>/（截图 + console + network）。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5325')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int875')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 崩溃 / 错误页标记（CatchBoundary 重建时会出现的文案）
CRASH_MARKERS = ['糟糕！出错了', '页面加载失败', '哎呀！出错了']
# 与本卡无关的既有后端缺口（算法配置端点 400），排除在 pageerror 计数外
KNOWN_NOISE = ('/algorithm/options', '/algorithm/definitions')

_FAILURES = []


def _check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
    if not cond:
        _FAILURES.append(name)


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
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


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


def _stats_block_text(txt):
    """提取规模条六项指标块（跨标签名，取统计区文本）。"""
    out = {}
    for label, key in [('测试用例', 'test_cases'), ('测试任务', 'tasks'),
                       ('评估维度', 'dimensions'), ('音频文件', 'audio_files'),
                       ('在线设备', 'devices'), ('API 服务', 'apis')]:
        idx = txt.find(f'{label} ·')
        if idx >= 0:
            out[key] = txt[idx - 30: idx + 60].replace('\n', ' ')
    return out


def _network_responses(drv):
    """从 performance log 收集 /home/stats/ 的 URL+状态+响应体。"""
    entries = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            method = inner.get('method')
            if method == 'Network.responseReceived':
                p = inner.get('params', {})
                url = p.get('response', {}).get('url', '')
                if '/api/v1/home/stats/' in url:
                    status = p.get('response', {}).get('status')
                    rid = p.get('requestId')
                    body = None
                    try:
                        br = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
                        body = br.get('body')
                    except Exception:
                        pass
                    entries.append({'url': url, 'status': status, 'body': body})
    except Exception as e:
        entries.append({'error': str(e)})
    return entries


def _backend_stats(url_path):
    with urllib.request.urlopen(f'{BASE}{url_path}', timeout=10) as r:
        return r.status, r.read().decode('utf-8')


def _js_errors(drv):
    errs = []
    for entry in drv.get_log('browser'):
        lvl = entry.get('level', '')
        if lvl in ('SEVERE', 'ERROR'):
            errs.append(entry.get('message', ''))
    return errs


def run_steps(drv):
    # ---------- ① 首页：规模条真实渲染、无崩溃（验证 INT-845 修复） ----------
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/')
    WebDriverWait(drv, 20).until(
        lambda d: '测试用例' in d.execute_script('return document.body.textContent || ""'))
    time.sleep(2.5)
    txt = _body_text(drv)
    _check('① 首页规模条六项标签全部渲染', all(
        lab in txt for lab in ['测试用例', '测试任务', '评估维度', '音频文件', '在线设备', 'API 服务']))
    for marker in CRASH_MARKERS:
        _check(f'① 首页无崩溃标记「{marker}」', marker not in txt)

    # console / pageerror：排除已知算法端点 400
    js_errors = _js_errors(drv)
    real_errs = [e for e in js_errors if not any(n in e for n in KNOWN_NOISE)]
    _check('① 首页无 TypeError / Cannot read properties of undefined',
           not any(k in ' '.join(real_errs) for k in
                   ['TypeError', 'Cannot read properties of undefined', 'is not a function']),
           detail='; '.join(real_errs)[:300])
    _save_evidence('01_home_light', drv)

    # Network 证据：页面真实请求 /home/stats/details 且 200
    net_home = _network_responses(drv)
    det_reqs = [n for n in net_home if n.get('url', '').endswith('/home/stats/details')]
    _check('② Network: 首页真实请求 /api/v1/home/stats/details 且 200',
           det_reqs and all(n.get('status') == 200 for n in det_reqs),
           detail=f'{len(det_reqs)} 次')

    # 与后端直连比对（同端代理同一响应源）：wire 原始体为 snake_case
    st, body = _backend_stats('/api/v1/home/stats/details')
    payload = json.loads(body)['data']
    _check('② /home/stats/details 响应体为 snake_case（test_cases/audio_files 等）',
           'test_cases' in payload and 'audio_files' in payload and 'playback_devices' in payload)
    # 页面渲染值与 API 值一致（camelCase 映射正确）
    rendered = _stats_block_text(txt)
    tc = payload.get('test_cases', {})
    af = payload.get('audio_files', {})
    dev = payload.get('devices', {})
    _check('② 规模条「测试用例」数字与 API test_cases.total 一致',
           str(tc.get('total', 0)) in rendered.get('test_cases', ''),
           detail=f"API={tc.get('total')} rendered={rendered.get('test_cases')!r}")
    _check('② 规模条「音频文件」数字与 API audio_files.total 一致',
           str(af.get('total', 0)) in rendered.get('audio_files', ''),
           detail=f"API={af.get('total')} rendered={rendered.get('audio_files')!r}")
    _check('② 规模条「在线设备」离线数与 API devices.offline 一致',
           str(dev.get('offline', 0)) in rendered.get('devices', ''),
           detail=f"API={dev.get('offline')} rendered={rendered.get('devices')!r}")

    # 深色
    _set_theme(drv, 'dark')
    txt_dark = _body_text(drv)
    _check('① 深色首页无崩溃标记', all(m not in txt_dark for m in CRASH_MARKERS))
    _save_evidence('01b_home_dark', drv)
    _set_theme(drv, 'light')

    # ---------- ③ 工作台：platform-summary / 最近任务 / 用例分组排行 真实数据 ----------
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/dashboard')
    WebDriverWait(drv, 20).until(
        lambda d: '最近任务' in d.execute_script('return document.body.textContent || ""'))
    time.sleep(2.5)
    dtxt = _body_text(drv)
    _check('③ 工作台「平台概览」卡渲染', '平台概览' in dtxt and '任务总数' in dtxt and '完成率' in dtxt)
    _check('③ 工作台「最近任务 / 用例分组排行」面板渲染',
           '最近任务' in dtxt and '用例分组排行' in dtxt)
    for marker in CRASH_MARKERS:
        _check(f'③ 工作台无崩溃标记「{marker}」', marker not in dtxt)

    # summary 真实数据比对
    _, sbody = _backend_stats('/api/v1/home/stats/summary')
    sum_payload = json.loads(sbody)['data']
    recent = sum_payload.get('recent_tasks', [])
    groups = sum_payload.get('top_groups', [])
    _check('③ summary.recent_tasks 非空（真实数据）', len(recent) > 0, detail=f'{len(recent)} 条')
    if recent:
        first = recent[0].get('name', '')
        _check('③ 「最近任务」显示真实任务名', first and first in dtxt,
               detail=f'期望含 {first!r}')
    _check('③ summary.top_groups 非空（真实数据）', len(groups) > 0, detail=f'{len(groups)} 组')
    if groups:
        g0 = groups[0].get('name', '')
        _check('③ 「用例分组排行」显示真实分组名', g0 and g0 in dtxt,
               detail=f'期望含 {g0!r}')

    # platform-summary「最近任务」卡取 summary.recent_tasks[0] 状态/名称
    if recent:
        _check('③ 平台概览「最近任务」卡显示真实任务名', recent[0].get('name', '') in dtxt,
               detail=f'期望含 {recent[0].get("name", "")!r}')

    # 设置引导 useSetupGuide：完成度来自真实 details，展开默认；信号值真实
    _check('③ 设置引导展开态（未全部完成默认展开）', '让平台保持就绪' in dtxt
           and '推荐操作' in dtxt, detail='setupComplete=false 时应展开')
    details_payload = payload  # 同一 details 响应源
    exp_devices = f"{details_payload['devices'].get('online', 0)} 台在线"
    exp_cases = f"{details_payload['test_cases'].get('total', 0)} 条"
    exp_reports = f"{details_payload.get('reports', 0)} 份"
    _check('③ 设置引导「设备接入」信号为真实值', exp_devices in dtxt,
           detail=f'期望 {exp_devices!r}')
    _check('③ 设置引导「用例就绪」信号为真实值', exp_cases in dtxt,
           detail=f'期望 {exp_cases!r}')
    _check('③ 设置引导「报告产出」信号为真实值', exp_reports in dtxt,
           detail=f'期望 {exp_reports!r}')
    # 最近任务 id 进 curl 示例（真实 summary.recent_tasks[0].id）——
    # curl 预览在「开发者 API 示例」折叠面板内（Base UI Panel 默认展开时挂载），先展开再断言
    if recent:
        tid = recent[0].get('id')
        api_collapse = None
        for el in drv.find_elements('xpath', "//button[contains(., '开发者 API 示例')]"):
            if el.is_displayed():
                api_collapse = el
                break
        _check('③ 设置引导「开发者 API 示例」折叠触发器存在', api_collapse is not None)
        if api_collapse:
            api_collapse.click()
            time.sleep(1.0)
        curl_txt = _body_text(drv)
        _check('③ 设置引导 curl 示例用真实最近任务 id', tid is not None
               and f'tasks/{tid}/progress' in curl_txt, detail=f'期望含 tasks/{tid}/progress')

    # 展开/折叠切换 + localStorage 持久化
    hide_btn = None
    for el in drv.find_elements('xpath', "//button[contains(., '隐藏引导')]"):
        if el.is_displayed():
            hide_btn = el
            break
    _check('③ 设置引导「隐藏引导」按钮存在', hide_btn is not None)
    if hide_btn:
        hide_btn.click()
        time.sleep(1.0)
        ctxt = _body_text(drv)
        _check('③ 折叠态显示「已完成 n/4」徽标', '已完成 ' in ctxt and '显示引导' in ctxt,
               detail=('已完成 x/4' if '已完成 ' in ctxt else '折叠态未出现'))
        stored = drv.execute_script(
            "return window.localStorage.getItem('iatp:dashboard:v1:setup-guide')")
        _check('③ localStorage 记录 collapsed', stored == 'collapsed', detail=f'实际 {stored!r}')
        show_btn = None
        for el in drv.find_elements('xpath', "//button[contains(., '显示引导')]"):
            if el.is_displayed():
                show_btn = el
                break
        _check('③ 折叠态「显示引导」按钮存在', show_btn is not None)
        if show_btn:
            show_btn.click()
            time.sleep(1.0)
            etxt = _body_text(drv)
            _check('③ 再展开恢复「让平台保持就绪」', '让平台保持就绪' in etxt)
            stored2 = drv.execute_script(
                "return window.localStorage.getItem('iatp:dashboard:v1:setup-guide')")
            _check('③ localStorage 记录 expanded', stored2 == 'expanded', detail=f'实际 {stored2!r}')

    # 工作台 Network：details + summary 真实请求
    net_dash = _network_responses(drv)
    dash_det = [n for n in net_dash if n.get('url', '').endswith('/home/stats/details')]
    dash_sum = [n for n in net_dash if n.get('url', '').endswith('/home/stats/summary')]
    _check('③ Network: 工作台请求 /home/stats/details 且 200',
           dash_det and all(n.get('status') == 200 for n in dash_det), detail=f'{len(dash_det)} 次')
    _check('③ Network: 工作台请求 /home/stats/summary 且 200',
           dash_sum and all(n.get('status') == 200 for n in dash_sum), detail=f'{len(dash_sum)} 次')
    _save_evidence('02_dashboard_light', drv)

    # 深色工作台
    _set_theme(drv, 'dark')
    dtxt_dark = _body_text(drv)
    _check('③ 深色工作台无崩溃标记', all(m not in dtxt_dark for m in CRASH_MARKERS))
    _check('③ 深色工作台面板仍在', '最近任务' in dtxt_dark and '用例分组排行' in dtxt_dark)
    _save_evidence('02b_dashboard_dark', drv)
    _set_theme(drv, 'light')

    # ---------- 汇总证据 ----------
    os.makedirs(ARTIFACTS, exist_ok=True)
    net_evidence = []
    for n in net_home + net_dash:
        if n.get('url', '').endswith('/home/stats/details') or n.get('url', '').endswith('/home/stats/summary'):
            net_evidence.append(n)
    summary = {
        'home_labels_found': {lab: (lab in txt) for lab in
                              ['测试用例', '测试任务', '评估维度', '音频文件', '在线设备', 'API 服务']},
        'dashboard_sections_found': {'平台概览': '平台概览' in dtxt,
                                     '最近任务': '最近任务' in dtxt,
                                     '用例分组排行': '用例分组排行' in dtxt},
        'setup_guide_expanded_default': '让平台保持就绪' in dtxt,
        'stats_bar_block': ' | '.join(rendered.values()),
        'home_stats_details_response': [n for n in net_home if n.get('url', '').endswith('/home/stats/details')],
        'home_stats_summary_response': [n for n in net_home if n.get('url', '').endswith('/home/stats/summary')],
        'dashboard_stats_details_response': dash_det,
        'dashboard_stats_summary_response': dash_sum,
        'backend_stats_details_body': body,
        'backend_stats_summary_body': sbody,
        'js_errors': js_errors,
        'home_has_crash_marker': any(m in txt for m in CRASH_MARKERS),
        'dashboard_has_crash_marker': any(m in dtxt for m in CRASH_MARKERS),
    }
    with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 可读 Network 证据（URL + 状态 + snake_case 响应体摘录）
    with open(os.path.join(ARTIFACTS, 'network_evidence.txt'), 'w', encoding='utf-8') as f:
        f.write('INT-875 Network 证据（performance log 真实请求）\n\n')
        for n in net_evidence:
            f.write(f"URL: {n.get('url')}\n")
            f.write(f"STATUS: {n.get('status')}\n")
            if n.get('body'):
                f.write(f"BODY: {n['body'][:600]}\n")
            f.write('\n')


def run():
    drv = _driver()
    try:
        run_steps(drv)
    except Exception:
        _save_evidence('FAILURE_dump', drv)
        raise
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    print('=' * 50)
    if _FAILURES:
        print(f'FAILED ({len(_FAILURES)}): {_FAILURES}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(run())
