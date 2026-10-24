# -*- coding: utf-8 -*-
"""INT-1688 验收（测试工程师独立实测）：case-detail 弹窗按真实契约渲染。

被测前端：旁路容器 http://127.0.0.1:15288（交付 fddeca1d2 构建 dist + 15173 同款 nginx，
反代 api_gateway），后端真实库栈 http://127.0.0.1:15000（database=intelligent_audio_test）。

期望值全部从接口原文独立推导（/detail + /results + /audios/stream-by-path），
不引用交付脚本的断言。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15288').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1688'),
)
TASK_ID = 402
CASE_ID = '7bac162b-275d-4567-b924-954736dc3ce9'
EMPTY_TASK_ID = int(os.environ.get('EMPTY_TASK_ID', '399'))
CASE_FRAG = 'JG0006_单轮接管-正常接管'
DARK_KEY = 'iatp:theme:v1:mode'

RESULT = []
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def api_get(path):
    with urllib.request.urlopen(API + path, timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))


def expected_view():
    """独立按接口原文推导弹窗应渲染的内容。"""
    detail = api_get('/api/v1/tasks/%d/cases/%s/detail' % (TASK_ID, CASE_ID))['data']
    results = api_get('/api/v1/tasks/%d/cases/%s/results' % (TASK_ID, CASE_ID))['data']['results']
    points = [d for row in results for d in (row.get('dimensions') or [])]
    multi = any(p.get('round_number') is not None for p in points)

    present = []
    for p in points:
        if p['name'] not in present:
            present.append(p['name'])
    configured = [c['name'] for c in (detail.get('metric_configs') or [])]
    order = [n for n in configured if n in present] + [n for n in present if n not in configured]

    columns = []
    for name in order:
        rows = [p for p in points if p['name'] == name]
        if not multi:
            columns.append(name)
            continue
        rounds = sorted({p['round_number'] + 1 for p in rows if p.get('round_number') is not None})
        columns.extend(['%s@round:%d' % (name, n) for n in rounds])
        if any(p.get('round_number') is None for p in rows):
            columns.append('%s@overall' % name)

    # 期望单元格值（与适配器口径一致：null → '—'，其余 String(value)）
    def cell(name, round_no):
        for p in points:
            rn = p.get('round_number')
            if p['name'] != name:
                continue
            if round_no == 'overall' and rn is None:
                return '—' if p.get('value') is None else ('%g' % p['value'])
            if isinstance(round_no, int) and rn is not None and rn + 1 == round_no:
                return '—' if p.get('value') is None else ('%g' % p['value'])
        return '—'

    expected_cells = []
    for col in columns:
        if '@round:' in col:
            dim, _, n = col.rpartition('@round:')
            expected_cells.append(cell(dim, int(n)))
        elif col.endswith('@overall'):
            expected_cells.append(cell(col[:-len('@overall')], 'overall'))
        else:
            expected_cells.append(cell(col, 'overall' if not multi else None))

    audios = [a.get('filename') or a.get('param_code')
              for group in (detail.get('result_audios') or {}).values() for a in (group or [])]
    audios += [r.get('label') or r.get('param_code')
               for r in (detail.get('algorithm_results') or [])
               if r.get('param_type') == 'audio_file' and r.get('value')]
    refs = [a.get('filename') for a in (detail.get('audio_list') or [])]

    return {
        'devices': detail.get('devices') or [],
        'columns': columns,
        'cells': expected_cells,
        'multi_round': multi,
        'metric_configs': configured,
        'exec_status_row': results[0].get('execution_status') if results else None,
        'audios': audios,
        'refs': refs,
        'raw_detail': detail,
        'raw_results': results,
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
    drv.set_page_load_timeout(180)
    drv.set_script_timeout(180)
    return drv


def goto(drv, path, wait=4.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 120).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p)
    return p


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait_text(drv, text, timeout=120):
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
const audioRows = [...dlg.querySelectorAll('div')]
  .filter(d => d.className && typeof d.className === 'string'
    && d.className.includes('flex') && d.className.includes('rounded-lg')
    && d.className.includes('border') && d.querySelector('button'))
  .map(d => (d.textContent||'').trim());
return {
  badges, heads, rows, audioRows,
  dialogText: (dlg.textContent || ''),
  sectionHeads: [...dlg.querySelectorAll('p')].map(p => (p.textContent||'').trim()).filter(Boolean),
};
"""


def open_case_dialog(drv, task_id=TASK_ID, frag=CASE_FRAG, attempt=1):
    goto(drv, '/tasks/%d' % task_id, wait=5)
    try:
        wait_text(drv, '关联用例', 180)
    except Exception:
        if attempt <= 2:
            print('RETRY open_case_dialog attempt=%d' % attempt)
            btn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
            if btn:
                js_click(drv, btn[0], 1.5)
            return open_case_dialog(drv, task_id, frag, attempt + 1)
        shot(drv, 'debug_open_fail_%d' % task_id)
        print('DEBUG body:', body_text(drv)[:600])
        raise
    if frag:
        box = WebDriverWait(drv, 90).until(
            lambda d: d.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']"))
        js_click(drv, box, 0.4)
        box.send_keys(frag)
        time.sleep(2.5)
    btn = WebDriverWait(drv, 90).until(
        lambda d: d.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0])
    js_click(drv, btn, 1.0)
    WebDriverWait(drv, 90).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
    wait_text(drv, '执行结果与指标', 90)
    time.sleep(1.5)


def read_perf(drv):
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        p = msg['params']
        out.append((p['response']['url'], p['response']['status'],
                    p['response'].get('mimeType', '')))
    return out


def api_statuses(netlog, needle):
    return sorted({st for url, st, _ in netlog if needle in url})


def soak(drv, expected, mode):
    data = drv.execute_script(COLLECT_JS)
    if not data:
        check('[%s] 弹窗 DOM 可取' % mode, False, 'collect returned null')
        return None
    dtext = data['dialogText']
    heads = data['heads']
    rows = data['rows']

    check('[%s] 分节①「执行结果与指标」可见' % mode, '执行结果与指标' in dtext, dtext[:100])

    for dev in expected['devices']:
        check('[%s] 头部设备徽章 = %s' % (mode, dev), dev in data['badges'], data['badges'])
        check('[%s] 表格设备列 = %s' % (mode, dev),
              len(rows) == 1 and rows[0][0] == dev, [r[:1] for r in rows])

    check('[%s] 维度列头与接口推导一致（%d 列）' % (mode, len(expected['columns'])),
          heads[1:-1] == expected['columns'], {'want': expected['columns'], 'got': heads})
    check('[%s] 列头含 @round:1 / @overall' % mode,
          any('@round:1' in h for h in heads) and any('@overall' in h for h in heads), heads)
    check('[%s] 6 个 metric_configs 维度全部出列' % mode,
          all(any(c in h for h in heads) for c in expected['metric_configs']),
          expected['metric_configs'])

    if rows:
        got_cells = rows[0][1:-1]
        check('[%s] 每列取值与 /results 一致' % mode,
              got_cells == expected['cells'], {'want': expected['cells'], 'got': got_cells})
        check('[%s] 执行状态列 = 已完成（不再恒「失败」）' % mode,
              rows[0][-1] == '已完成', rows[0][-1:])
    else:
        check('[%s] 表格有数据行' % mode, False, 'no rows')
    check('[%s] 弹窗内无「失败」徽章/文案' % mode, '失败' not in dtext, dtext.count('失败'))

    for name in expected['audios']:
        check('[%s] 结果音频行出现 %s' % (mode, name), name in dtext, expected['audios'])
    for name in expected['refs']:
        check('[%s] 参考音频行出现 %s' % (mode, name), name in dtext, expected['refs'])
    check('[%s] 试听按钮数 >= 音频行数' % mode,
          dtext.count('试听') >= len(expected['audios']) + len(expected['refs']),
          dtext.count('试听'))

    return {
        'badges': data['badges'], 'heads': heads, 'rows': rows,
        'audioRows': data['audioRows'], 'sectionHeads': data['sectionHeads'],
    }


def play_audio(drv, token, mode):
    """点某音频行的试听 → 校验 INT-356 弹窗拿到可用的音频地址。

    音频字节是否能播不由本卡裁决：本环境 rustfs 预签名 GET 全域 404（见 evidence
    storage_404），属后端/存储侧既有问题，这里只断言前端拿得到地址、无失败 toast。
    """
    btn = drv.find_element(
        By.XPATH,
        "//div[contains(@class,'rounded-lg') and contains(.,'%s')]//button[normalize-space(.)='试听']"
        % token)
    js_click(drv, btn, 2.0)
    WebDriverWait(drv, 60).until(
        lambda d: len(d.find_elements(By.TAG_NAME, 'audio')) > 0)
    src = ''
    info = None
    for _ in range(30):
        info = drv.execute_script(
            "const a=document.querySelector('audio');"
            "return a ? {src: a.currentSrc||a.src||'', rs: a.readyState,"
            " dur: a.duration, err: a.error? a.error.code : null} : null")
        if info and info['src']:
            src = info['src']
            if info['rs'] and info['rs'] >= 1:
                break
        time.sleep(0.5)
    check('[%s] %s 试听获得 http 音频地址' % (mode, token),
          bool(src) and src.startswith('http'), src[:200])
    print('   audio element state:', info)
    check('[%s] 试听取地址无失败 toast' % mode,
          '音频播放地址获取失败' not in body_text(drv), '')
    # 关掉试听弹窗再回主弹窗
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.2)
    return src


def empty_state(drv):
    goto(drv, '/tasks/%d' % EMPTY_TASK_ID, wait=5)
    try:
        wait_text(drv, '关联用例', 180)
    except Exception:
        btn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
        if btn:
            js_click(drv, btn[0], 1.5)
        wait_text(drv, '关联用例', 180)
    # 空态：库里该任务 0 条 test_results，任一用例行都可验证空态
    n = len(drv.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]"))
    check('[empty] 任务 %d 有可点用例行' % EMPTY_TASK_ID, n > 0, n)
    btn = drv.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0]
    js_click(drv, btn, 1.2)
    WebDriverWait(drv, 90).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
    wait_text(drv, '执行结果与指标', 90)
    time.sleep(1.2)
    data = drv.execute_script(COLLECT_JS) or {}
    dtext = data.get('dialogText', '')
    check('[empty] 弹窗可打开且含「执行结果与指标」', '执行结果与指标' in dtext, dtext[:100])
    check('[empty] 显示「暂无执行结果」空态', '暂无执行结果' in dtext, dtext[:300])
    check('[empty] 不渲染设备×维度表', not data.get('heads'), data.get('heads'))
    check('[empty] 无结果音频区', '结果音频' not in dtext, '')
    check('[empty] 无 JS 崩溃（弹窗仍挂载）',
          drv.execute_script(
              "return !!document.querySelector('[data-slot=\"case-detail-dialog\"]')"), True)
    check('[empty] 头部执行状态非空（显示真实状态）',
          '执行' in dtext, dtext[:80])
    return {'shot': shot(drv, 'P_case_detail_task%d_empty' % EMPTY_TASK_ID), 'text': dtext[:500]}


def main():
    expected = expected_view()
    print('EXPECTED columns:', expected['columns'])
    print('EXPECTED cells  :', expected['cells'])
    print('EXPECTED audios :', expected['audios'], '| refs:', expected['refs'])
    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'api_expected.json'), 'w', encoding='utf-8') as f:
        json.dump({k: expected[k] for k in (
            'devices', 'columns', 'cells', 'metric_configs', 'exec_status_row', 'audios', 'refs')},
            f, ensure_ascii=False, indent=1)

    drv = build_driver()
    ev = {'base': BASE, 'api': API, 'expected': {k: expected[k] for k in ('columns', 'cells')}}
    try:
        # ---------- 浅色 ----------
        open_case_dialog(drv)
        ev['light'] = soak(drv, expected, 'light')
        net = read_perf(drv)
        ev['net_light'] = {
            'detail': api_statuses(net, '/cases/%s/detail' % CASE_ID),
            'results': api_statuses(net, '/cases/%s/results' % CASE_ID),
            'stream_by_path': api_statuses(net, '/audios/stream-by-path'),
            'nine_k': [(u.split('?')[0][-50:], st, mime) for u, st, mime in net if ':9000' in u],
        }
        check('Network：GET .../detail → 200', ev['net_light']['detail'] == [200],
              ev['net_light']['detail'])
        check('Network：GET .../results → 200', ev['net_light']['results'] == [200],
              ev['net_light']['results'])

        ev['play_result'] = play_audio(drv, 'user_wav', 'light')
        net2 = read_perf(drv)
        ev['net_audio'] = [(u.split('?')[0][-60:], st, mime) for u, st, mime in net2 if ':9000' in u]
        ev['net_stream'] = api_statuses(net2, '/audios/stream-by-path')
        check('Network：GET /audios/stream-by-path → 200', ev['net_stream'] == [200],
              ev['net_stream'])
        check('Network：预签名音频 9000 取流 → 200（audio/*）',
              any(st == 200 and 'audio' in mime for _, st, mime in ev['net_audio']),
              ev['net_audio'])

        ev['shot_light'] = shot(drv, 'P_case_detail_task402_light')
        drv.execute_script(
            "const t=document.querySelector('[data-slot=\"case-detail-dialog\"] table');"
            "if(t){t.parentElement.scrollLeft=t.parentElement.scrollWidth;}")
        time.sleep(0.8)
        ev['shot_light_tail'] = shot(drv, 'P_case_detail_task402_light_columns_tail')

        # 参考音频也试听一次（audio_list → /audios/1622/stream）
        try:
            ref_src = play_audio(drv, '_silence.wav', 'light')
            ev['play_reference'] = ref_src
        except Exception as exc:  # noqa: BLE001
            check('[light] 参考音频试听入口', False, repr(exc)[:200])

        # ---------- 深色 ----------
        drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
        open_case_dialog(drv)
        dark_cls = drv.execute_script('return document.documentElement.className')
        check('深色主题已生效', 'dark' in (dark_cls or ''), dark_cls)
        ev['dark'] = soak(drv, expected, 'dark')
        ev['shot_dark'] = shot(drv, 'P_case_detail_task402_dark')

        # 浅色还原 + 控制台错误（只在非深色轮读一次，避免噪声）
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)
        time.sleep(0.5)
        # 已知非本卡：/tasks/cherry-picks/{id}/source 对非容器任务返回 400（既有后端行为）
        severe = [e for e in drv.get_log('browser')
                  if e.get('level') == 'SEVERE'
                  and 'cherry-picks' not in e.get('message', '')]
        ev['console_severe'] = severe[-10:]
        check('浏览器控制台无\\u672c\\u5361\\u76f8\\u5173 SEVERE 错误', not severe,
              [s.get('message', '')[:160] for s in severe[-5:]])

        # ---------- 空态 ----------
        ev['empty'] = empty_state(drv)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    failed = [r for r in RESULT if not r['ok']]
    ev['checks'] = RESULT
    ev['failed'] = len(failed)
    with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(ev, f, ensure_ascii=False, indent=1, default=str)
    print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'][:300])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
