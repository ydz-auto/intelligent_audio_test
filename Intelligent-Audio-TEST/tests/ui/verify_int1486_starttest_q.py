# -*- coding: utf-8 -*-
"""INT-1486 打回后复测 Q：INT-1688 合入 + 15173 重建后，只重走 case-detail 窗。

真实任务 402 → 用例 7bac162b-275d-4567-b924-954736dc3ce9：
设备名 pura90小艺 / 6 个维度列 / @round 轮次 / 结果音频试听；浅/深截图 + GET .../detail 原文。
另回归一次无结果用例空态（任务 400 / 541e51bc-…）；其余 3 窗沿用。
只读，不发写请求。
"""
import json, os, sys, time, urllib.request

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


def dump(name, body):
    p = os.path.join(ART, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))
    return p


def api_get(path, tok):
    r = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + tok})
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def open_case(d, task_id, hint, wait_key='执行结果'):
    d.get(BASE + f'/tasks/{task_id}')
    for _ in range(3):
        try:
            wait_text(d, '测试用例_', 150)
            break
        except Exception:
            print('slow load, reload')
            d.refresh()
    time.sleep(2)
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
    txt = dialog_text(d)
    reqs = [it for it in d.execute_script('return window.__fetchLog || []')[mark:]
            if '/cases/' in it['url']]
    return txt, reqs


def analyze(txt, tag):
    print(f'--- {tag} ---')
    r = {}
    r['devices'] = [x for x in ['pura90小艺'] if x in txt]
    r['dims'] = [x for x in DIMS if x in txt]
    r['has_round1'] = '@round:1' in txt
    r['has_overall'] = '@overall' in txt
    r['has_result_audio'] = '结果音频' in txt
    r['play_buttons'] = txt.count('试听')
    r['fail_count'] = txt.count('失败')
    r['pass_count'] = txt.count('通过') + txt.count('执行完成')
    r['empty'] = '暂无执行结果' in txt or '暂无' in txt
    for k, v in r.items():
        print('  ', k, '=', v)
    RESULT[tag] = r
    return r


def try_play(d, tag):
    """点第一个「试听」，确认音频播放弹窗出现且拿到真实 src。"""
    btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '试听']
    print('试听 buttons', len(btns))
    if not btns:
        return {'played': False, 'reason': 'no button'}
    mark = log_mark(d)
    js_click(d, btns[0])
    src = None
    for _ in range(40):
        time.sleep(1)
        src = d.execute_script("""
          const a = document.querySelector('audio');
          return a ? (a.currentSrc || a.src || '') : null;
        """)
        if src:
            break
        if len(dialogs(d)) > 1:
            time.sleep(2)
            src = d.execute_script("const a=document.querySelector('audio');return a?(a.currentSrc||a.src||'') : (document.body.innerText.includes('加载')?'loading':null)")
            break
    reqs = [it for it in d.execute_script('return window.__fetchLog || []')[mark:]
            if 'stream' in it['url']]
    for it in reqs:
        print('  PLAY REQ', it['method'], it['status'], it['url'][:180])
        print('  PLAY RES', (it.get('resBody') or '')[:200])
    print('  audio src =', (src or '')[:200])
    shot(d, f'Q_case_detail_{tag}_player.png')
    # 关闭播放弹窗（Esc 两次：播放窗 → 详情窗保持）
    try:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)
    except Exception:
        pass
    return {'played': bool(src), 'src': (src or '')[:300], 'reqs': [
        {'method': i['method'], 'status': i['status'], 'url': i['url'][:200]} for i in reqs]}


def main():
    tok = open(os.path.join(ART, 'token.txt')).read().strip()

    # 后端原文（真实 GET）
    st, body = api_get(f'/api/v1/tasks/{TASK_ID}/cases/{CASE_ID}/detail', tok)
    dump('q_get_detail_raw.json', body)
    print('GET detail ->', st, len(body))
    st2, body2 = api_get(f'/api/v1/tasks/{TASK_ID}/cases/{CASE_ID}/results', tok)
    dump('q_get_results_raw.json', body2)
    print('GET results ->', st2, len(body2))

    d = make_driver(tok)
    try:
        d.get(BASE + '/tasks')  # 先落到同源页面，localStorage 才可写
        time.sleep(1)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        # ================= 浅色 · 有结果用例 =================
        r = open_case(d, TASK_ID, CASE_HINT)
        if not r:
            print('NO CASE ROW')
            return
        txt, reqs = r
        dump('q_case_detail_task402_light.txt', txt)
        print('LIGHT TEXT >>>', txt.replace('\n', ' | ')[:2500])
        analyze(txt, 'light')
        shot(d, 'Q_case_detail_task402_light.png')
        for it in reqs:
            print('REQ', it['method'], it['status'], it['url'][:160])
            if '/detail' in it['url']:
                dump('q_browser_detail_res.txt', it.get('resBody') or '')
            if '/results' in it['url']:
                dump('q_browser_results_res.txt', it.get('resBody') or '')
        RESULT['play_light'] = try_play(d, 'task402_light')
        # 确认回到详情窗
        print('dialogs after player close', len(dialogs(d)))
        shot(d, 'Q_case_detail_task402_light_afterplay.png')
        close_dialog(d)

        # ================= 深色 · 有结果用例 =================
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        r = open_case(d, TASK_ID, CASE_HINT)
        if r:
            txt, reqs = r
            dump('q_case_detail_task402_dark.txt', txt)
            analyze(txt, 'dark')
            shot(d, 'Q_case_detail_task402_dark.png')
            ds = d.execute_script("return document.documentElement.className + '|' + document.documentElement.getAttribute('data-theme')")
            print('DARK root =', ds)
            RESULT['dark_root'] = ds
            close_dialog(d)

        # ================= 空态回归 · 无结果用例 =================
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        r = open_case(d, EMPTY_TASK, EMPTY_CASE_HINT)
        if r:
            txt, reqs = r
            dump('q_case_detail_empty_light.txt', txt)
            print('EMPTY TEXT >>>', txt.replace('\n', ' | ')[:1200])
            analyze(txt, 'empty_light')
            shot(d, 'Q_case_detail_empty_light.png')
            for it in reqs:
                print('REQ', it['method'], it['status'], it['url'][:160])
            close_dialog(d)
        else:
            print('NO EMPTY CASE ROW')

        print('RESULT JSON', json.dumps(RESULT, ensure_ascii=False))
        dump('q_result.json', RESULT)
    finally:
        d.quit()


if __name__ == '__main__':
    main()
