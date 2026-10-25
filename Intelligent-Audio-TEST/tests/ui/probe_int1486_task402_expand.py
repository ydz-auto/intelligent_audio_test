# -*- coding: utf-8 -*-
"""INT-1486 探针2：/tasks/402 的「用例清单」折叠区展开后是否出现用例行，并尝试打开 case-detail。"""
import json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1486_starttest_c import ART, BASE, make_driver, js_click, dialogs, dialog_text  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

TASK_ID = 402
HINT = '测试用例_JG0006'


def main():
    tok = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
    d = make_driver(tok)
    try:
        d.execute_cdp_cmd('Log.enable', {})
        d.get(BASE + f'/tasks/{TASK_ID}')
        time.sleep(12)
        # 展开「用例清单」折叠区
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '用例清单' in (b.text or ''):
                print('CLICK 用例清单:', (b.text or '').replace('\n', ' ')[:80])
                js_click(d, b)
                break
        time.sleep(4)
        rows = [b for b in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (b.text or '')]
        print('rows after expand:', len(rows))
        for r in rows[:6]:
            print('  ROW:', (r.text or '').replace('\n', ' ')[:120])
        if rows:
            row = next((r for r in rows if HINT in (r.text or '')), rows[0])
            js_click(d, row)
            for i in range(40):
                time.sleep(1)
                if dialogs(d):
                    break
            time.sleep(3)
            print('DIALOGS:', len(dialogs(d)))
            if dialogs(d):
                t = dialog_text(d)
                print('--- DIALOG TEXT HEAD ---')
                print(t[:2500])
                d.save_screenshot(os.path.join(ART, 'probe_task402_dialog.png'))
        print('--- CONSOLE ---')
        for e in d.get_log('browser')[-30:]:
            print(e.get('level'), (e.get('message') or '')[:250])
    finally:
        d.quit()


if __name__ == '__main__':
    main()
