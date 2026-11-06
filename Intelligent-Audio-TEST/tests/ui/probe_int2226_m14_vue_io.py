# -*- coding: utf-8 -*-
"""INT-2226 M14：Vue 两端导出（按分组）与导入入口实测。"""
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2226')
FRONTS = {'uxvue': 'http://localhost:16173', 'vue': 'http://localhost:8080'}
GROUP = '话轮接管'


def main():
    front = sys.argv[1]
    base = FRONTS[front]
    out = {'front': front}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(viewport={'width': 1440, 'height': 900}, accept_downloads=True).new_page()
        pg.goto(base + '/#/login', wait_until='domcontentloaded'); time.sleep(3)
        pg.locator('input[type=password]').first.fill('dev_password')
        pg.locator('input[type=text], input:not([type])').first.fill('dev_user')
        pg.get_by_role('button', name=re.compile('登\\s*录')).first.click()
        pg.wait_for_function("() => !/login/i.test(location.href)", timeout=45000); time.sleep(3)
        pg.goto(base + '/#/testcases', wait_until='domcontentloaded'); time.sleep(6)

        # 导出
        pg.get_by_role('button', name='导出用例').first.click(); time.sleep(2.5)
        dlg = pg.locator('.modal-overlay.active').first
        cb = dlg.locator('#group-%s' % GROUP)
        out['checkbox_count'] = cb.count()
        if cb.count():
            cb.first.click(force=True)
        time.sleep(2.5)
        t = dlg.inner_text()
        m = re.search(r'预计导出[：:]\s*(\d+)\s*条', t)
        out['preview'] = m.group(1) if m else None
        out['preview_checked'] = dlg.locator('#group-%s' % GROUP).is_checked() if cb.count() else None
        try:
            with pg.expect_download(timeout=90000) as dl:
                dlg.get_by_role('button', name=re.compile('^导出$')).first.click()
            f = os.path.join(ART, 'm14_%s_export.xlsx' % front)
            dl.value.save_as(f)
            out['file'] = f
            out['size'] = os.path.getsize(f)
            out['ok'] = True
        except Exception as exc:
            out['ok'] = False
            out['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
        out['shot_export'] = pg.screenshot(path=os.path.join(ART, 'm14_%s_export_ok.png' % front))

        # 导入入口
        pg.goto(base + '/#/testcases', wait_until='domcontentloaded'); time.sleep(4)
        btn = pg.get_by_role('button', name='导入用例').first
        btn.click()
        time.sleep(4)
        out['url_after_import_click'] = pg.url
        modal = pg.locator('.modal-overlay.active').first
        out['modal_text'] = modal.inner_text()[:400] if modal.count() else ''
        try:
            out['checkboxes'] = modal.evaluate("""el => [...el.querySelectorAll('input[type=checkbox]')]
              .map(c => ({checked: c.checked, id: c.id,
                          label: (c.closest('label') || {}).innerText || ''}))""")
        except Exception:
            out['checkboxes'] = []
        out['opens_file_import'] = ('xlsx' in out['modal_text'] or '.zip' in out['modal_text'])
        out['shot_import'] = pg.screenshot(path=os.path.join(ART, 'm14_%s_import_ok.png' % front))
        b.close()

    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
    with open(os.path.join(ART, 'm14_%s_io.json' % front), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
