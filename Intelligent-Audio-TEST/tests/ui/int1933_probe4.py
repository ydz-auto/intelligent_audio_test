# -*- coding: utf-8 -*-
"""INT-1933 补证：设备管理 /devices 测试 API 页签「编辑」打开的组件形态（只读打开，不保存）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By  # noqa: E402

import int1643_lib as L  # noqa: E402

L.BASE = 'http://127.0.0.1:15173'
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1933')
os.makedirs(L.ART, exist_ok=True)
OUT = {}


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/devices')
        time.sleep(5)
        for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if t.is_displayed() and (t.text or '').strip() == '测试 API':
                L.js_click(d, t)
                break
        time.sleep(3.0)
        # 行内操作触发钮 aria-label = "操作 <API 名称>"（device-row-actions.tsx:96）
        target = None
        for b in d.find_elements(By.CSS_SELECTOR, "[aria-label='操作 1']"):
            if b.is_displayed():
                target = b
                break
        if target is None:
            for b in d.find_elements(By.TAG_NAME, 'button'):
                if b.is_displayed() and (b.get_attribute('aria-label') or '').startswith('操作 '):
                    target = b
                    break
        OUT['more_btn_found'] = target is not None
        OUT['more_btn_aria'] = target.get_attribute('aria-label') if target else None
        if target is not None:
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
            time.sleep(0.3)
            L.js_click(d, target)
            time.sleep(1.0)
            items = [(i.text or '').strip() for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if i.is_displayed()]
            OUT['menu_items'] = items
            for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                if i.is_displayed() and (i.text or '').strip() == '编辑':
                    L.js_click(d, i)
                    break
            time.sleep(2.5)
        # 诊断当前打开的弹窗/抽屉
        OUT['opened'] = json.loads(d.execute_script("""
            const vis = e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e);
              return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden'; };
            const ds = Array.from(document.querySelectorAll("[role='dialog'],[role='alertdialog']")).filter(vis);
            const d = ds[ds.length-1];
            if (!d) return JSON.stringify({any:false});
            const tabs = Array.from(d.querySelectorAll("[role='tab']")).map(t=>(t.innerText||'').trim());
            const inputs = Array.from(d.querySelectorAll('input,textarea')).filter(vis).length;
            return JSON.stringify({any:true, tabs:tabs, inputs:inputs,
              head:(d.innerText||'').slice(0,400),
              hasFiveTabs: ['基础','请求模板','响应解析','输出字段','映射'].every(x=>tabs.includes(x))});
        """))
        L.shot(d, 'P3_device_api_edit_form')
        L.save_evidence('probe4', OUT)
        print(json.dumps(OUT, ensure_ascii=False, indent=1))
        # 关闭
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and (b.text or '').strip() in ('取消', '关闭'):
                L.js_click(d, b)
                break
        time.sleep(0.8)
        d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
        time.sleep(0.8)
    finally:
        d.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
