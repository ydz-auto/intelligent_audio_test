# -*- coding: utf-8 -*-
"""INT-2176 覆盖 6 补证侦察：探 /Evaluation 新增维度抽屉的真实结构与选择器。"""
import importlib.util
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('boot', os.path.join(HERE, '_int2176_boot.py'))
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)

ART = os.path.join(HERE, 'artifacts', 'int2176', 'dim_recon')
os.makedirs(ART, exist_ok=True)

DUMP = r"""
const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const dlg = [...document.querySelectorAll('[role=dialog]')].filter(vis).pop();
const root = dlg || document.body;
const ctl = [...root.querySelectorAll('button, [role=tab], input, textarea, select, [role=combobox]')].filter(vis);
return {
  dialog: dlg ? (dlg.innerText || '').slice(0, 1200) : null,
  controls: ctl.map(e => ({
    tag: e.tagName, role: e.getAttribute('role'), id: e.id,
    aria: e.getAttribute('aria-label'), ph: e.getAttribute('placeholder'),
    txt: (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 40),
    type: e.getAttribute('type'),
  })),
};
"""


def main():
    d = boot.driver()
    try:
        d.get(boot.BASE + '/login')
        WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        d.find_element(By.ID, 'username').send_keys(boot.USER)
        d.find_element(By.ID, 'password').send_keys(boot.PWD)
        d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
        time.sleep(2)
        d.get(boot.BASE + '/Evaluation')
        WebDriverWait(d, 45).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        time.sleep(5)
        body = d.execute_script('return document.body.innerText')
        open(os.path.join(ART, 'page.txt'), 'w', encoding='utf-8').write(body)
        btns = d.execute_script(DUMP)
        open(os.path.join(ART, 'page_controls.json'), 'w', encoding='utf-8').write(
            json.dumps(btns, ensure_ascii=False, indent=2))
        print('PAGE controls:', len(btns['controls']))
        for c in btns['controls']:
            t = c['txt'] or c['aria'] or c['ph'] or c['id']
            if t:
                print(' ', c['tag'], c['role'] or '', '|', t[:50])
        # 点「新增维度」
        r = d.execute_script("""
          const vis = e => { const r = e.getBoundingClientRect(); return r.width>0 && r.height>0; };
          const b = [...document.querySelectorAll('button')].filter(vis)
            .find(x => (x.innerText||'').replace(/\\s+/g,'').includes('新增维度')
                    || (x.getAttribute('aria-label')||'').includes('新增维度'));
          if (!b) return {ok:false, n: [...document.querySelectorAll('button')].filter(vis).length};
          b.scrollIntoView({block:'center'}); b.click(); return {ok:true};
        """)
        print('click add =>', r)
        time.sleep(3)
        info = d.execute_script(DUMP)
        open(os.path.join(ART, 'drawer_initial.json'), 'w', encoding='utf-8').write(
            json.dumps(info, ensure_ascii=False, indent=2))
        print('DRAWER text:', (info['dialog'] or '')[:600])
        print('DRAWER controls:', len(info['controls']))
        for c in info['controls'][:80]:
            t = c['txt'] or c['aria'] or c['ph'] or c['id']
            print(' ', c['tag'], c['role'] or '', '|', t[:60])
        d.save_screenshot(os.path.join(ART, 'drawer_initial.png'))
    finally:
        d.quit()


if __name__ == '__main__':
    main()
