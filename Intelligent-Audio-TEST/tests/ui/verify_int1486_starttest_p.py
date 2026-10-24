# -*- coding: utf-8 -*-
"""INT-1486 打回复现 P：case-detail-dialog 在有执行结果的真实任务（/tasks/402）上的渲染。
独立取证：真实任务 402（436 条结果）→ 关联用例行 → 弹窗；浅/深各一张 + GET detail 原文。
不发写请求，只读。"""
import json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1486_starttest_c import (  # noqa: E402
    ART, BASE, make_driver, js_click, text, wait_text, shot, dialogs, dialog_text,
    close_dialog, log_mark, By, Keys,
)

TASK_ID = 402
CASE_HINT = '测试用例_JG0006'


def dump_art(name, body):
    p = os.path.join(ART, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(body)
    print('ART', name, len(body))


def open_case(d):
    d.get(BASE + f'/tasks/{TASK_ID}')
    try:
        wait_text(d, '测试用例_', 150)
    except Exception:
        print('slow load, reload once')
        d.refresh()
        wait_text(d, '测试用例_', 150)
    time.sleep(2)
    rows = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
    print('case rows', len(rows))
    row = next((r for r in rows if CASE_HINT in (r.text or '')), rows[0] if rows else None)
    if row is None:
        print('NO ROW')
        return None
    print('ROW', (row.text or '').replace('\n', ' ')[:160])
    mark = log_mark(d)
    js_click(d, row)
    # 等弹窗内容真正渲染（接口慢，首次打开可能先出空壳）
    for _ in range(60):
        time.sleep(1)
        if '执行结果' in dialog_text(d):
            break
    time.sleep(3)
    txt = dialog_text(d)
    reqs = [it for it in d.execute_script('return window.__fetchLog || []')[mark:]
            if '/cases/' in it['url']]
    return txt, reqs


def main():
    token = open(os.path.join(ART, 'token.txt')).read().strip()
    d = make_driver(token)
    try:
        # ---------- 浅色 ----------
        r = open_case(d)
        if not r:
            return
        txt, reqs = r
        dump_art('p_case_detail_light.txt', txt)
        print('LIGHT TEXT >>>', txt.replace('\n', ' | ')[:1600])
        shot(d, 'P_case_detail_task402_light.png')
        for it in reqs:
            print('REQ', it['method'], it['status'], it['url'])
            dump_art('p_detail_response.txt', it.get('resBody') or '')
        print('device name in dialog?', 'pura90小艺' in txt)
        print('dimension names in dialog?', [x for x in
              ['逐轮话轮评估', '接管率占比', '未接管率占比', '误接管率占比', '接管时延平均值', '接管内容平均分']
              if x in txt])
        print('round marker @1?', '@1' in txt or '第1轮' in txt)
        print('失败 count', txt.count('失败'), '| 通过 count', txt.count('通过'))
        close_dialog(d)

        # ---------- 深色（同源设置 storage 后重载） ----------
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.refresh()
        time.sleep(3)
        r2 = open_case(d)
        if r2:
            txt2, _ = r2
            dump_art('p_case_detail_dark.txt', txt2)
            print('DARK TEXT >>>', txt2.replace('\n', ' | ')[:800])
            shot(d, 'P_case_detail_task402_dark.png')
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
    finally:
        d.quit()


if __name__ == '__main__':
    main()
