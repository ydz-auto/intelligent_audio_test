# -*- coding: utf-8 -*-
"""INT-1486 探针：/tasks/402 页面为何无「测试用例_」行。导出 innerText / fetch 日志 / 控制台错误。"""
import json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1486_starttest_c import ART, BASE, make_driver  # noqa: E402

TASK_ID = 402


def main():
    tok = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
    d = make_driver(tok)
    try:
        d.execute_cdp_cmd('Log.enable', {})
        d.get(BASE + f'/tasks/{TASK_ID}')
        for i in range(12):
            time.sleep(5)
            body = d.execute_script('return document.body.innerText') or ''
            print(f'[{i}] len={len(body)} has_case={"测试用例_" in body}')
            if '测试用例_' in body:
                break
        body = d.execute_script('return document.body.innerText') or ''
        open(os.path.join(ART, 'probe_task402_page.txt'), 'w', encoding='utf-8').write(body)
        print('--- TEXT HEAD ---')
        print(body[:1500])
        fetches = d.execute_script('return window.__fetchLog || []')
        print('--- FETCH LOG', len(fetches), '---')
        for it in fetches:
            print(it.get('method'), it.get('status'), str(it.get('url'))[:140])
        print('--- CONSOLE/LOG ---')
        for e in d.get_log('browser')[-40:]:
            print(e.get('level'), (e.get('message') or '')[:300])
        for e in d.get_log('performance')[-5:]:
            pass
        d.save_screenshot(os.path.join(ART, 'probe_task402_page.png'))
    finally:
        d.quit()


if __name__ == '__main__':
    main()
