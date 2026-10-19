# -*- coding: utf-8 -*-
"""INT-845 首页规模条 StatsBar 崩溃修复 浏览器实测（React wiring，测试工程师验收）。

缺陷：home stats details/summary 接口 snake_case 直通（未过 DTO 适配器），
StatsBar 读 stats.testCases 为 undefined → TypeError → 整页 CatchBoundary 重建。
修复：fetchHomeStatsDetails/Summary 改走 request<DTO> + toHomeStatsDetails/toHomeStatsSummary。

验收核对（INT-845 卡内「可测的验收标准」）：
① pnpm build / typecheck 零错误 —— 脚本外已验证
② 首页规模条真实数据渲染（Network 显示 /home/stats/details 返回 snake_case，
   页面按 camelCase 正常渲染六项指标），浅色 + 深色截图，无崩溃
③ 工作台 platform-summary「最近任务 / 用例分组排行」显示真实数据
④ 单测 mock request 断言返回 camelCase 域模型 —— 脚本外 vitest 已验证

环境：dev server http://localhost:5325（本 run 起，/api 代理 → 常驻 :5000，
AUTH_MODE=off → /auth/me 回填 dev_user('*') 放行）。

失败落 tests/ui/artifacts/int845/<步骤>/（截图 + console + network）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int845')
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
        # 规模条 dt 文案为「{label} · {sub}」；避免命中 Hero 四角节点纯 label
        idx = txt.find(f'{label} ·')
        if idx >= 0:
            out[key] = txt[idx - 24: idx + 40].replace('\n', ' ')
    return out


def _network_responses(drv):
    """从 performance log 收集 /home/stats/details·summary 的 URL+状态+响应体。"""
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


def run_steps(drv):
    # ---------- 首页：规模条真实渲染、无崩溃 ----------
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/')
    # 等规模条渲染完成（标签出现且数字非骨架 0）
    WebDriverWait(drv, 20).until(
        lambda d: '测试用例' in d.execute_script('return document.body.textContent || ""'))
    time.sleep(2.5)
    txt = _body_text(drv)
    _check('① 首页规模条六项标签全部渲染', all(
        lab in txt for lab in ['测试用例', '测试任务', '评估维度', '音频文件', '在线设备', 'API 服务']))
    for marker in CRASH_MARKERS:
        _check(f'① 首页无崩溃标记「{marker}」', marker not in txt)

    # console / pageerror：排除已知算法端点 400
    js_errors = []
    for entry in drv.get_log('browser'):
        lvl = entry.get('level', '')
        if lvl in ('SEVERE', 'ERROR'):
            js_errors.append(entry.get('message', ''))
    real_errs = [e for e in js_errors if not any(n in e for n in KNOWN_NOISE)]
    _check('① 首页无 TypeError / Cannot read properties of undefined',
           not any(k in ' '.join(real_errs) for k in
                   ['TypeError', 'Cannot read properties of undefined', 'is not a function']),
           detail='; '.join(real_errs)[:300])
    _save_evidence('01_home_light', drv)

    # Network 证据：页面请求 /home/stats/details 且 200
    net = _network_responses(drv)
    det_reqs = [n for n in net if n.get('url', '').endswith('/home/stats/details')]
    _check('② Network: 页面真实请求 /api/v1/home/stats/details 且 200',
           det_reqs and all(n.get('status') == 200 for n in det_reqs),
           detail=f'{len(det_reqs)} 次')

    # 与后端直连比对（同端代理同一响应源）：wire 原始体为 snake_case
    st, body = _backend_stats('/api/v1/home/stats/details')
    payload = json.loads(body)['data']
    _check('② /home/stats/details 响应体为 snake_case（test_cases/tasks 等）',
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

    # ---------- 工作台：最近任务 / 用例分组排行 真实数据 ----------
    _goto(drv, '/dashboard')
    WebDriverWait(drv, 20).until(
        lambda d: '最近任务' in d.execute_script('return document.body.textContent || ""'))
    time.sleep(2.0)
    dtxt = _body_text(drv)
    _check('③ 工作台「最近任务 / 用例分组排行」面板渲染',
           '最近任务' in dtxt and '用例分组排行' in dtxt)
    _, sbody = _backend_stats('/api/v1/home/stats/summary')
    sum_payload = json.loads(sbody)['data']
    recent = sum_payload.get('recent_tasks', [])
    groups = sum_payload.get('top_groups', [])
    _check('③ summary.recent_tasks 非空（真实数据）', len(recent) > 0,
           detail=f'{len(recent)} 条')
    if recent:
        first = recent[0].get('name', '')
        _check('③ 「最近任务」显示真实任务名', first and first in dtxt,
               detail=f'期望含 {first!r}')
    _check('③ summary.top_groups 非空（真实数据）', len(groups) > 0,
           detail=f'{len(groups)} 组')
    if groups:
        g0 = groups[0].get('name', '')
        _check('③ 「用例分组排行」显示真实分组名', g0 and g0 in dtxt,
               detail=f'期望含 {g0!r}')
    for marker in CRASH_MARKERS:
        _check(f'③ 工作台无崩溃标记「{marker}」', marker not in dtxt)
    _save_evidence('02_dashboard_light', drv)
    _set_theme(drv, 'dark')
    dtxt_dark = _body_text(drv)
    _check('③ 深色工作台无崩溃标记', all(m not in dtxt_dark for m in CRASH_MARKERS))
    _save_evidence('02b_dashboard_dark', drv)
    _set_theme(drv, 'light')

    # ---------- 汇总证据 ----------
    os.makedirs(ARTIFACTS, exist_ok=True)
    summary = {
        'home_labels_found': {lab: (lab in txt) for lab in
                              ['测试用例', '测试任务', '评估维度', '音频文件', '在线设备', 'API 服务']},
        'dashboard_sections_found': {'最近任务': '最近任务' in dtxt,
                                     '用例分组排行': '用例分组排行' in dtxt},
        'stats_bar_block': ' | '.join(rendered.values()),
        'home_stats_details_response': [n for n in net if n.get('url', '').endswith('/home/stats/details')],
        'home_stats_summary_response': [n for n in net if n.get('url', '').endswith('/home/stats/summary')],
        'backend_stats_details_body': body,
        'backend_stats_summary_body': sbody,
        'js_errors': js_errors,
        'home_has_crash_marker': any(m in txt for m in CRASH_MARKERS),
        'dashboard_has_crash_marker': any(m in dtxt for m in CRASH_MARKERS),
    }
    with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


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
