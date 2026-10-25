# -*- coding: utf-8 -*-
"""INT-1486 复测 S：按 V9.7.10 轮次 Tab 口径重走 case-detail 窗（INT-1688 返工 7dd09598c）。

真实任务 402 → 用例 7bac162b-275d-4567-b924-954736dc3ce9：
1. 多轮/有结果：弹窗出现轮次 Tab 栏 `[role=tablist][aria-label='轮次切换']`，
   Tab 文案为「第N轮」/「整体」（单轮为单个「指标」且不渲染 Tab 栏）；
2. 表头 = 「指标」+ 设备名（不得再出现 `@round:` / `@overall` 内部键当列头）；
3. 表体行 = 指标名、列 = 设备；切 Tab 行随轮变化；结果/参考音频随当前 Tab 轮过滤；
4. 无结果用例退回结果摘要空态（回归）。
浅/深截图 + GET /detail、/results 原文。只读，不发写请求。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1486_starttest_c import (  # noqa: E402
    ART, BASE, API, make_driver, js_click, text, wait_text, shot, dialogs,
    dialog_text, close_dialog, log_mark, By, Keys,
)

TASK_ID = 402
CASE_ID = '7bac162b-275d-4567-b924-954736dc3ce9'
CASE_HINT = '测试用例_JG0006'
EMPTY_TASK = 400
EMPTY_CASE_HINT = '测试用例_'
DIMS = ['逐轮话轮评估', '接管率占比', '未接管率占比', '误接管率占比',
        '接管时延平均值', '接管内容平均分']
RESULT = {}

SNAP_JS = r"""
const dlgs = [...document.querySelectorAll('[role="dialog"]')];
const dlg = dlgs.length ? dlgs[dlgs.length - 1] : null;
if (!dlg) return null;
const tl = dlg.querySelector('[role="tablist"]');
const tabs = tl ? [...tl.querySelectorAll('[role="tab"]')].map(b => ({
  text: (b.textContent || '').trim(),
  selected: b.getAttribute('aria-selected') === 'true',
})) : [];
const table = dlg.querySelector('table');
const ths = table ? [...table.querySelectorAll('thead th')].map(t => (t.innerText || '').trim()) : [];
const rows = table ? [...table.querySelectorAll('tbody tr')].map(tr =>
  [...tr.children].map(td => (td.innerText || '').trim())) : [];
const txt = dlg.innerText || '';
const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
const audioLines = lines.filter(s => s.includes('轮') && /\.(wav|mp3|m4a|flac|aac|ogg|pcm)/i.test(s));
return {
  tablist: !!tl,
  tablistLabel: tl ? (tl.getAttribute('aria-label') || '') : '',
  tabs, ths, rows,
  text: txt,
  audioLines,
  playButtons: [...dlg.querySelectorAll('button')].filter(b => (b.innerText || '').trim() === '试听').length,
  hasNoMetricData: txt.includes('暂无指标数据'),
  hasNoResult: txt.includes('暂无执行结果') || txt.includes('暂无结果'),
};
"""

TAB_CLICK_JS = r"""
const dlgs = [...document.querySelectorAll('[role="dialog"]')];
const dlg = dlgs.length ? dlgs[dlgs.length - 1] : null;
if (!dlg) return false;
const tabs = [...dlg.querySelectorAll('[role="tablist"] [role="tab"]')];
if (arguments[0] >= tabs.length) return false;
tabs[arguments[0]].click();
return true;
"""


def dump(name, body):
    p = os.path.join(ART, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=1))
    return p


def api_get(path, tok):
    r = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + tok})
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def expand_case_list(d):
    """容器任务的用例清单在折叠区里（「用例清单 N 个」），展开后才渲染用例行。"""
    for b in d.find_elements(By.TAG_NAME, 'button'):
        t = b.text or ''
        if '用例清单' in t:
            js_click(d, b)
            print('EXPAND 用例清单:', t.replace('\n', ' ')[:60])
            time.sleep(3)
            return True
    return False


def open_case(d, task_id, hint, wait_key='执行结果'):
    d.get(BASE + f'/tasks/{task_id}')
    for _ in range(3):
        try:
            wait_text(d, '返回任务列表', 150)
            break
        except Exception:
            print('slow load, reload')
            d.refresh()
    time.sleep(3)
    expand_case_list(d)
    rows = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
    print('case rows', len(rows))
    row = next((r for r in rows if hint in (r.text or '')), rows[0] if rows else None)
    if row is None:
        return None
    print('ROW', (row.text or '').replace('\n', ' ')[:140])
    mark = log_mark(d)
    js_click(d, row)
    for _ in range(60):
        time.sleep(1)
        if dialogs(d) and (wait_key in dialog_text(d) or '暂无' in dialog_text(d)):
            break
    time.sleep(3)
    reqs = [it for it in d.execute_script('return window.__fetchLog || []')[mark:]
            if '/cases/' in it['url']]
    return reqs


def snapshot(d):
    s = d.execute_script(SNAP_JS)
    return s


def check(snap, tag, expect_tabs):
    """对一次快照做断言，返回结论字典。"""
    r = {'tag': tag}
    txt = (snap or {}).get('text') or ''
    r['tablist'] = bool((snap or {}).get('tablist'))
    r['tab_labels'] = [t['text'] for t in (snap or {}).get('tabs') or []]
    r['ths'] = (snap or {}).get('ths') or []
    r['row_dims'] = [row[0] if row else '' for row in (snap or {}).get('rows') or []]
    r['n_rows'] = len((snap or {}).get('rows') or [])
    r['audio_lines'] = (snap or {}).get('audioLines') or []
    r['play_buttons'] = (snap or {}).get('playButtons', 0)
    r['has_no_metric_data'] = (snap or {}).get('hasNoMetricData')
    r['internal_key_header'] = any('@round:' in h or '@overall' in h for h in r['ths'])
    r['internal_key_text'] = ('@round:' in txt) or ('@overall' in txt)
    r['device_pura90'] = 'pura90小艺' in txt
    r['fail_count'] = txt.count('失败')
    r['dims'] = [x for x in DIMS if x in txt]
    r['empty'] = '暂无执行结果' in txt or '暂无指标数据' in txt
    if expect_tabs is True:
        r['PASS'] = r['tablist'] and not r['internal_key_header'] and not r['internal_key_text']
    elif expect_tabs is False:
        r['PASS'] = (not r['tablist']) and not r['internal_key_header'] and not r['internal_key_text']
    else:
        r['PASS'] = not r['internal_key_header'] and not r['internal_key_text']
    print(f'--- {tag} ---')
    for k, v in r.items():
        if k not in ('text',):
            print('  ', k, '=', v)
    RESULT[tag] = r
    return r


def main():
    tok = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()

    st, body = api_get(f'/api/v1/tasks/{TASK_ID}/cases/{CASE_ID}/detail', tok)
    dump('s_get_detail_raw.json', body)
    print('GET detail ->', st, len(body))
    st2, body2 = api_get(f'/api/v1/tasks/{TASK_ID}/cases/{CASE_ID}/results', tok)
    dump('s_get_results_raw.json', body2)
    print('GET results ->', st2, len(body2))
    RESULT['api'] = {'detail_status': st, 'detail_len': len(body),
                     'results_status': st2, 'results_len': len(body2)}

    d = make_driver(tok)
    try:
        d.get(BASE + '/tasks')
        time.sleep(1)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

        # ================= 浅色 · 有结果多轮用例 =================
        reqs = open_case(d, TASK_ID, CASE_HINT)
        if reqs is None:
            print('NO CASE ROW')
            return
        for it in reqs:
            print('REQ', it['method'], it['status'], it['url'][:160])
        snap = snapshot(d)
        dump('s_task402_light_text.txt', (snap or {}).get('text') or '')
        dump('s_task402_light_snapshot.json', snap or {})
        base = check(snap, 'task402_light', expect_tabs=None)
        shot(d, 'S_case_detail_task402_light.png')

        # 每个 Tab 逐一点开取证（行=指标、列=设备；音频按轮过滤）
        labels = base['tab_labels']
        per_tab = {}
        for i in range(len(labels)):
            if not d.execute_script(TAB_CLICK_JS, i):
                break
            time.sleep(2)
            s = snapshot(d)
            tag = f'tab{i}_{labels[i]}'
            per_tab[tag] = {
                'ths': (s or {}).get('ths'),
                'row_dims': [r[0] for r in (s or {}).get('rows') or []],
                'audio_lines': (s or {}).get('audioLines'),
                'empty': (s or {}).get('hasNoMetricData'),
            }
            print('TAB', labels[i], '| ths', per_tab[tag]['ths'], '| rows', per_tab[tag]['row_dims'],
                  '| audios', per_tab[tag]['audio_lines'])
            if i <= 2:
                shot(d, f'S_case_detail_task402_tab{i}_light.png')
        RESULT['task402_tabs'] = per_tab
        if labels:
            d.execute_script(TAB_CLICK_JS, 0)
            time.sleep(1)

        # 结果音频试听（当前 Tab）
        btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '试听']
        print('试听 buttons', len(btns))
        if btns:
            mark = log_mark(d)
            js_click(d, btns[0])
            src = None
            for _ in range(30):
                time.sleep(1)
                src = d.execute_script(
                    "const a=document.querySelector('audio');return a?(a.currentSrc||a.src||''):null")
                if src:
                    break
            preqs = [it for it in d.execute_script('return window.__fetchLog || []')[mark:]
                     if 'stream' in it['url'] or 'preview' in it['url']]
            for it in preqs:
                print('  PLAY', it['method'], it['status'], it['url'][:180])
            print('  audio src =', (src or '')[:200])
            shot(d, 'S_case_detail_task402_player_light.png')
            RESULT['play'] = {'buttons': len(btns), 'src': (src or '')[:300],
                              'reqs': [{'method': i['method'], 'status': i['status'],
                                        'url': i['url'][:200]} for i in preqs]}
            try:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1.5)
            except Exception:
                pass
        close_dialog(d)

        # ================= 深色 · 同一用例 =================
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        reqs = open_case(d, TASK_ID, CASE_HINT)
        if reqs is not None:
            snap = snapshot(d)
            dump('s_task402_dark_text.txt', (snap or {}).get('text') or '')
            check(snap, 'task402_dark', expect_tabs=None)
            shot(d, 'S_case_detail_task402_dark.png')
            root = d.execute_script(
                "return document.documentElement.className + '|' + "
                "document.documentElement.getAttribute('data-theme')")
            print('DARK root =', root)
            RESULT['dark_root'] = root
            close_dialog(d)

        # ================= 空态回归 · 无结果用例 =================
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        reqs = open_case(d, EMPTY_TASK, EMPTY_CASE_HINT)
        if reqs is not None:
            snap = snapshot(d)
            dump('s_empty_light_text.txt', (snap or {}).get('text') or '')
            check(snap, 'empty_light', expect_tabs=False)
            shot(d, 'S_case_detail_empty_light.png')
            close_dialog(d)
        else:
            print('NO EMPTY CASE ROW')

        print('RESULT JSON', json.dumps(RESULT, ensure_ascii=False)[:3000])
        dump('s_result.json', RESULT)
    finally:
        d.quit()


if __name__ == '__main__':
    main()
