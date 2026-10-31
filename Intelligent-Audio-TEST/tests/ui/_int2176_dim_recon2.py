# -*- coding: utf-8 -*-
"""INT-2176 覆盖 6 补证侦察 2：API配置分节真实控件。"""
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
  dialog: dlg ? (dlg.innerText || '').slice(0, 2000) : null,
  controls: ctl.map(e => ({
    tag: e.tagName, role: e.getAttribute('role'), id: e.id,
    aria: e.getAttribute('aria-label'), ph: e.getAttribute('placeholder'),
    txt: (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 40),
    type: e.getAttribute('type'), val: (e.value || '').slice(0, 40),
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
        d.execute_script("""
          const vis = e => { const r = e.getBoundingClientRect(); return r.width>0 && r.height>0; };
          const b = [...document.querySelectorAll('button')].filter(vis)
            .find(x => (x.innerText||'').replace(/\\s+/g,'').includes('新增维度'));
          b.click();
        """)
        time.sleep(2.5)
        # API配置 tab
        r = d.execute_script("""
          const vis = e => { const r = e.getBoundingClientRect(); return r.width>0 && r.height>0; };
          const t = [...document.querySelectorAll('[role=tab]')].filter(vis)
            .find(x => (x.innerText||'').includes('API配置'));
          if (!t) return {ok:false};
          t.click(); return {ok:true};
        """)
        print('tab =>', r)
        time.sleep(2)
        info = d.execute_script(DUMP)
        open(os.path.join(ART, 'drawer_api.json'), 'w', encoding='utf-8').write(
            json.dumps(info, ensure_ascii=False, indent=2))
        print('DRAWER text:', (info['dialog'] or '')[:1200])
        for c in info['controls']:
            t = c['txt'] or c['aria'] or c['ph'] or c['id']
            print(' ', c['tag'], c['role'] or '', '|', t[:60], '| val=', c['val'])
        d.save_screenshot(os.path.join(ART, 'drawer_api.png'))
    finally:
        d.quit()


if __name__ == '__main__':
    main()
