# -*- coding: utf-8 -*-
"""INT-1688 实测：用例详情弹窗按真实契约渲染（设备名 / 维度列 @round·@overall / 结果音频）。

环境：docker 真实库栈 15000（/health → database=intelligent_audio_test，AUTH_MODE=off），
前端 = 本 worktree `pnpm dev --port 5388`（-c rsbuild.realstack.config.ts 代理到 127.0.0.1:15000）。

验收点（卡描述）：
1. /tasks/402 关联用例弹窗：设备名 pura90小艺、6 个维度（@round:1 + @overall 共 12 列）、
   执行状态不再恒「失败」、结果音频 user_wav/ai_wav 可试听；
2. 与 GET /tasks/402/cases/{cid}/detail + /results 原文逐字段对照；
3. 浅色 / 深色各一张截图；
4. Network：/detail 与 /results 均 200。
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5388').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART_DIR',
    r'D:\00_user_data\multica_workspaces_desktop-api.multica.ai\intelligent-95ba6a12369f'
    r'\int-1688-7534f5c7a0ec\worktree\Intelligent-Audio-TEST\tests\ui\artifacts\int1688',
)
TASK_ID = 402
CASE_ID = '7bac162b-275d-4567-b924-954736dc3ce9'
# 验收 #3 空态用例来源：整任务秒败、无 test_results 的任务（399，591 用例 0 结果）
EMPTY_TASK_ID = int(os.environ.get('EMPTY_TASK_ID', '399'))
CASE_FRAG = 'JG0006_单轮接管-正常接管'
DARK_KEY = 'iatp:theme:v1:mode'

RESULT = []

try:  # Windows 控制台是 GBK，中文证据直接 print 会 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:500] if detail else ''))
    return ok


def api_get(path):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def expected_view():
    """按修复口径从接口原文算出期望：设备名、维度列、执行状态、结果音频。"""
    detail = api_get('/api/v1/tasks/%d/cases/%s/detail' % (TASK_ID, CASE_ID))['data']
    results = api_get('/api/v1/tasks/%d/cases/%s/results' % (TASK_ID, CASE_ID))['data']['results']
    dims = []
    for row in results:
        dims.extend(row.get('dimensions') or [])
    is_multi = any(d.get('round_number') is not None for d in dims)

    present = []
    for d in dims:
        if d['name'] not in present:
            present.append(d['name'])
    configured = [c['name'] for c in (detail.get('metric_configs') or [])]
    order = [n for n in configured if n in present] + [n for n in present if n not in configured]

    columns = []
    for name in order:
        rows = [d for d in dims if d['name'] == name]
        if not is_multi:
            columns.append(name)
            continue
        rounds = sorted({d['round_number'] + 1 for d in rows if d.get('round_number') is not None})
        columns.extend(['%s@round:%d' % (name, r) for r in rounds])
        if any(d.get('round_number') is None for d in rows):
            columns.append('%s@overall' % name)

    audios = [a.get('filename') or a.get('param_code')
              for group in (detail.get('result_audios') or {}).values() for a in (group or [])]
    audios += [r.get('label') or r.get('param_code')
               for r in (detail.get('algorithm_results') or [])
               if r.get('param_type') == 'audio_file' and r.get('value')]

    return {
        'devices': detail.get('devices') or [],
        'columns': columns,
        'multi_round': is_multi,
        'metric_configs': configured,
        'exec_status': results[0].get('execution_status') if results else None,
        'audios': audios,
        'raw_detail_keys': sorted(detail.keys()),
    }


def chrome_major():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def build_driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1920,1200')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    major = chrome_major()
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            p = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(p):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), p))
                except ValueError:
                    pass
        same = [p for v, p in cands if v and v[0] == major]
        if same:
            exe = max(same)
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(options=opts, service=srv)
    drv.set_page_load_timeout(120)
    drv.set_script_timeout(120)
    return drv


def goto(drv, path, wait=4.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 90).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p)
    return p


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait_text(drv, text, timeout=90):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))


def js_click(drv, el, wait=0.8):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


COLLECT_JS = r"""
const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
if (!dlg) return null;
const header = dlg.querySelector('[data-slot="dialog-header"]') || dlg;
const badges = [...header.querySelectorAll('span.flex.flex-wrap.gap-1 span')].map(s => (s.textContent||'').trim());
const table = dlg.querySelector('table');
const heads = table ? [...table.querySelectorAll('thead th')].map(t => (t.textContent||'').trim()) : [];
const rows = table ? [...table.querySelectorAll('tbody tr')].map(tr =>
  [...tr.querySelectorAll('td')].map(td => (td.textContent||'').trim())) : [];
const audioItems = [...dlg.querySelectorAll('div.flex.items-center.gap-2.rounded-lg.border')]
  .map(d => (d.textContent||'').trim());
return {
  badges,
  heads,
  rows,
  audioItems,
  dialogText: (dlg.textContent || ''),
  audioSrc: [...dlg.querySelectorAll('audio')].map(a => a.currentSrc || a.src || ''),
};
"""


def open_case_dialog(drv, attempt=1):
    goto(drv, '/tasks/%d' % TASK_ID, wait=5)
    try:
        wait_text(drv, '关联用例', 150)
    except Exception:
        # 真实栈偶发 DEADLINE_EXCEEDED（任务详情接口超时）→ 点「重试」再等一次，不算本卡结论
        if attempt <= 2:
            print('RETRY open_case_dialog, attempt=%d' % attempt)
            try:
                btn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
                if btn:
                    js_click(drv, btn[0], 1.0)
                    return open_case_dialog(drv, attempt + 1)
            except Exception:
                pass
            return open_case_dialog(drv, attempt + 1)
        shot(drv, 'debug_open_fail')
        print('DEBUG url:', drv.current_url)
        print('DEBUG body:', body_text(drv)[:800].encode('utf-8', 'replace').decode('utf-8'))
        raise
    # 搜索框缩到目标用例（405 条按默认分页不一定在第一页）
    box = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
    )
    js_click(drv, box, 0.4)
    box.send_keys(CASE_FRAG)
    time.sleep(2.5)
    btn = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(
            By.XPATH,
            "//button[starts-with(@title,'查看用例详情：')][contains(@title,'%s')]" % CASE_FRAG,
        )
    )
    js_click(drv, btn, 1.0)
    WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]')
    )
    wait_text(drv, '执行结果与指标', 60)
    time.sleep(1.5)


def network_responses(drv):
    """读一次 performance log（get_log 会清空缓冲区，故只读一次）→ [(url, status)]"""
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        p = msg['params']
        out.append((p['response']['url'], p['response']['status']))
    return out


def network_status(netlog, needle):
    return [(url.split('?')[0][-70:], status) for url, status in netlog if needle in url]


def soak(drv, want, expected):
    data = drv.execute_script(COLLECT_JS)
    if not data:
        return False
    dtext = data['dialogText']
    heads = data['heads']
    rows = data['rows']

    check('弹窗打开且分节①可见', '执行结果与指标' in dtext, dtext[:120])

    # 1. 设备名
    for dev in expected['devices']:
        check('头部设备徽章 = %s' % dev, dev in data['badges'], data['badges'])
        check('表格设备列 = %s' % dev, any(r and r[0] == dev for r in rows),
              [r[:2] for r in rows if r])

    # 2. 维度列（@round / @overall）
    check('维度列数与接口一致（%d 列）' % len(expected['columns']),
          heads[1:-1] == expected['columns'],
          {'want': expected['columns'], 'got': heads})
    check('维度列含 @round:1', any('@round:1' in h for h in heads), heads)
    check('维度列含 @overall', any('@overall' in h for h in heads), heads)
    check('metric_configs 6 个维度名全部出现在列头',
          all(any(cfg in h for h in heads) for cfg in expected['metric_configs']),
          expected['metric_configs'])

    # 3. 执行状态（不再恒「失败」）
    check('弹窗内无「失败」徽章误标', '失败' not in dtext, dtext.count('失败'))
    check('执行状态列 = 已完成', len(rows) == 1 and rows[0][-1] == '已完成', rows)

    # 4. 结果音频
    for name in expected['audios']:
        check('结果音频出现 %s' % name, name in dtext, expected['audios'])
    check('结果音频可试听（试听钮）', dtext.count('试听') >= len(expected['audios']),
          dtext.count('试听'))

    # 5. 试听 → 真实预签名地址
    try:
        btn = drv.find_element(
            By.XPATH,
            "//div[contains(@class,'rounded-lg') and contains(.,'user_wav')]//button[normalize-space(.)='试听']",
        )
        js_click(drv, btn, 2.0)
        srcs = drv.execute_script(
            "return [...document.querySelectorAll('audio')].map(a => a.currentSrc || a.src || '')"
        )
        check('试听弹窗拿到真实音频地址（9000 预签名）',
              any(s and ('9000' in s or s.startswith('http')) for s in srcs), srcs)
        toast = body_text(drv)
        check('无「音频播放地址获取失败」', '音频播放地址获取失败' not in toast, '')
        check('试听弹窗类型徽章 = 结果音频', '结果音频' in body_text(drv), '')
        # ESC 关掉试听弹窗，主弹窗截图里不叠层
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.2)
        still = drv.execute_script(
            "return [...document.querySelectorAll('[role=\"dialog\"]')].length"
        )
        check('ESC 关闭试听弹窗后仅剩用例详情弹窗', still == 1, still)
    except Exception as exc:  # noqa: BLE001
        check('试听入口可点击', False, repr(exc)[:300])

    return {k: data[k] for k in ('badges', 'heads', 'rows', 'audioItems')}


def verify_empty_state(drv):
    """验收 #3：无结果用例（整任务秒败 / 无 test_results）→ 弹窗空态不回归。"""
    goto(drv, '/tasks/%d' % EMPTY_TASK_ID, wait=5)
    try:
        wait_text(drv, '关联用例', 150)
    except Exception:
        print('RETRY empty-state task detail')
        btn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
        if btn:
            js_click(drv, btn[0], 1.5)
        wait_text(drv, '关联用例', 150)
    btn = WebDriverWait(drv, 60).until(
        lambda d: d.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0]
    )
    js_click(drv, btn, 1.0)
    WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]')
    )
    wait_text(drv, '执行结果与指标', 60)
    time.sleep(1.0)
    data = drv.execute_script(COLLECT_JS) or {}
    dtext = data.get('dialogText', '')
    check('无结果用例 → 弹窗仍可打开并含「执行结果与指标」', '执行结果与指标' in dtext, dtext[:120])
    check('无结果用例 → 显示「暂无执行结果」（空态不回归）', '暂无执行结果' in dtext, dtext[:200])
    check('无结果用例 → 不渲染设备×维度表', not data.get('heads'), data.get('heads'))
    check('无结果用例 → 无结果音频区', '结果音频' not in dtext, '')
    return shot(drv, 'P_case_detail_task%d_empty' % EMPTY_TASK_ID)


def main():
    expected = expected_view()
    print('API 期望：', json.dumps(expected, ensure_ascii=False)[:1200])
    drv = build_driver()
    evidence = {'base': BASE, 'expected': expected, 'modes': {}}
    try:
        # ---------- 浅色 ----------
        open_case_dialog(drv)
        light = soak(drv, None, expected)
        evidence['modes']['light'] = light
        netlog = network_responses(drv)
        evidence['network_light'] = {
            'detail': network_status(netlog, '/cases/%s/detail' % CASE_ID),
            'results': network_status(netlog, '/cases/%s/results' % CASE_ID),
        }
        check('Network：GET .../detail → 200',
              any(c == 200 for _, c in evidence['network_light']['detail']),
              evidence['network_light']['detail'])
        check('Network：GET .../results → 200',
              any(c == 200 for _, c in evidence['network_light']['results']),
              evidence['network_light']['results'])
        evidence['shot_light'] = shot(drv, 'P_case_detail_task402_light')
        # 12 列宽表在 4xl 弹窗内横向滚动：再截一张滚到末端的图，证明 @overall 等列都在
        drv.execute_script(
            "const t=document.querySelector('[data-slot=\"case-detail-dialog\"] table');"
            "if(t){t.parentElement.scrollLeft=t.parentElement.scrollWidth;}"
        )
        time.sleep(0.8)
        evidence['shot_light_cols'] = shot(drv, 'P_case_detail_task402_light_columns_tail')

        # ---------- 深色（同页同源 reload，不导航丢状态） ----------
        drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
        open_case_dialog(drv)
        dark_html = drv.execute_script('return document.documentElement.className')
        check('深色主题已生效', 'dark' in (dark_html or ''), dark_html)
        dark = soak(drv, None, expected)
        evidence['modes']['dark'] = dark
        evidence['shot_dark'] = shot(drv, 'P_case_detail_task402_dark')

        # 还原主题
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)
        time.sleep(0.5)

        # ---------- 验收 #3：无结果用例空态 ----------
        evidence['shot_empty'] = verify_empty_state(drv)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    failed = [r for r in RESULT if not r['ok']]
    evidence['checks'] = RESULT
    evidence['failed'] = len(failed)
    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
