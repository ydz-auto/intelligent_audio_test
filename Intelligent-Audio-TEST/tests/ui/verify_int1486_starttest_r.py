# -*- coding: utf-8 -*-
"""INT-1486 复测 R：case-detail 表头右侧「执行状态」列取证（打回项「结果恒失败」的直接反证）。

横向滚动设备×维度表到最右，截浅/深各一张；并逐格读最后一列文本。
只读。
"""
import json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1486_starttest_c import (  # noqa: E402
    ART, BASE, make_driver, js_click, wait_text, shot, dialogs, dialog_text,
    close_dialog, By, Keys, time as _t,
)

TASK_ID = 402
CASE_HINT = '测试用例_JG0006'


def open_dialog(d):
    d.get(BASE + f'/tasks/{TASK_ID}')
    for _ in range(3):
        try:
            wait_text(d, '测试用例_', 150)
            break
        except Exception:
            d.refresh()
    time.sleep(2)
    rows = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
    row = next((r for r in rows if CASE_HINT in (r.text or '')), rows[0] if rows else None)
    js_click(d, row)
    for _ in range(60):
        time.sleep(1)
        if '执行结果与指标' in dialog_text(d) and '结果音频' in dialog_text(d):
            break
    time.sleep(2)


def table_facts(d):
    return d.execute_script("""
      const dlg = [...document.querySelectorAll('[role=dialog]')].pop();
      if (!dlg) return null;
      const table = dlg.querySelector('table');
      if (!table) return null;
      const heads = [...table.querySelectorAll('thead th')].map(t => t.innerText.trim());
      const firstRow = [...table.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
      const wrap = table.closest('.overflow-x-auto') || table.parentElement;
      return {heads, rows: firstRow, scrollWidth: wrap.scrollWidth, clientWidth: wrap.clientWidth};
    """)


def scroll_right(d):
    return d.execute_script("""
      const dlg = [...document.querySelectorAll('[role=dialog]')].pop();
      const table = dlg.querySelector('table');
      const wrap = table.closest('.overflow-x-auto') || table.parentElement;
      wrap.scrollLeft = wrap.scrollWidth;
      return wrap.scrollLeft;
    """)


def main():
    tok = open(os.path.join(ART, 'token.txt')).read().strip()
    d = make_driver(tok)
    out = {}
    try:
        d.get(BASE + '/tasks')
        time.sleep(1)
        for theme in ('light', 'dark'):
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode',%s)" % json.dumps(theme))
            open_dialog(d)
            f = table_facts(d)
            print('===', theme, '===')
            print('  heads', len(f['heads']), json.dumps(f['heads'], ensure_ascii=False))
            print('  row', json.dumps(f['rows'][0], ensure_ascii=False))
            print('  overflow', f['scrollWidth'], '/', f['clientWidth'])
            shot(d, f'R_case_detail_{theme}_table_left.png')
            sl = scroll_right(d)
            time.sleep(1)
            print('  scrollLeft ->', sl)
            shot(d, f'R_case_detail_{theme}_table_right.png')
            out[theme] = {'heads': f['heads'], 'row': f['rows'][0],
                          'scrollWidth': f['scrollWidth'], 'clientWidth': f['clientWidth']}
            close_dialog(d)
        with open(os.path.join(ART, 'r_table_facts.json'), 'w', encoding='utf-8') as fp:
            json.dump(out, fp, ensure_ascii=False, indent=1)
    finally:
        d.quit()


if __name__ == '__main__':
    main()
