# -*- coding: utf-8 -*-
"""INT-1479 R3：批量标签 / 批量操作 窗口结构探明。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto, text  # noqa: E402

NAMES = [f'接线测试_INT1479R3_{i}.wav' for i in (1, 2, 3)]


def select_rows(c):
    return c.eval("""
      (function(names){
        for (const n of names) {
          const el = document.querySelector('[role=checkbox][aria-label="选择音频 '+n+'"]');
          if (el) el.click();
        }
        return 'done';
      })(%s)""" % json.dumps(NAMES))


def click_btn(c, label, aria=False):
    attr = 'aria-label' if aria else 'innerText'
    return c.eval("""
      (function(attr, label){
        const b = Array.from(document.querySelectorAll('button')).find(x => ((x.getAttribute(attr)||x.innerText||'').trim()) === label);
        if (!b) return 'NO_BTN:'+label;
        b.click(); return 'CLICKED:'+label;
      })(%s, %s)""" % (json.dumps(attr), json.dumps(label)))


def dump(c):
    return c.eval("""
      (function(){
        const d = document.querySelector('[role=dialog],[role=alertdialog]');
        if (!d) return null;
        return {text:(d.innerText||'').slice(0,1200),
          items: Array.from(d.querySelectorAll('input,textarea,select,button,[role=combobox],[role=checkbox],[role=radio],[role=switch]'))
            .map((e,i)=>({i, tag:e.tagName.toLowerCase(), type:e.type||'', role:e.getAttribute('role')||'',
                          aria:e.getAttribute('aria-label')||'', ph:e.getAttribute('placeholder')||'',
                          text:(e.innerText||'').trim().slice(0,50),
                          value:(e.value===undefined?'':String(e.value)).slice(0,80)}))};
      })()
    """)


def close(c):
    c.eval("document.querySelector('[role=dialog] [aria-label=Close], [role=dialog] button[aria-label=Close]')?.click()")
    c.eval("(function(){const d=document.querySelector('[role=dialog]');if(!d)return;const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消');if(b)b.click()})()")
    time.sleep(0.8)


if __name__ == '__main__':
    c = connect()
    goto(c, '/audio-import', 5)
    for _ in range(30):
        if '音频管理' in (text(c) or '') and (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            break
        time.sleep(2)
    time.sleep(2); c.pump()
    print('ROWS:', c.eval("document.querySelectorAll('tbody tr').length"))
    select_rows(c); time.sleep(0.8)
    print('CHECKED:', c.eval("Array.from(document.querySelectorAll('[role=checkbox]')).slice(0,4).map(e=>e.getAttribute('aria-checked'))"))
    print('TOOLBAR:', c.eval("Array.from(document.querySelectorAll('button')).filter(b=>/批量|更多/.test((b.innerText||'')+(b.getAttribute('aria-label')||''))).map(b=>({t:(b.innerText||'').trim(),a:b.getAttribute('aria-label')||''}))"))
    print('TAGS CLICK:', click_btn(c, '批量设置标签')); time.sleep(1.5)
    print('TAGS DIALOG:', json.dumps(dump(c), ensure_ascii=False, indent=1))
    close(c)
    print('MORE-BATCH:', click_btn(c, '更多批量操作')); time.sleep(1.2)
    print('MENU:', c.eval("Array.from(document.querySelectorAll('[role=menuitem]')).map(e=>(e.innerText||'').trim())"))
    items = c.eval("Array.from(document.querySelectorAll('[role=menuitem]')).map(e=>(e.innerText||'').trim())") or []
    target = next((i for i in items if '重命名' in i), None)
    if target:
        c.eval("""(function(t){const m=Array.from(document.querySelectorAll('[role=menuitem]')).find(e=>(e.innerText||'').trim()===t);if(m)m.click()})(%s)""" % json.dumps(target))
        time.sleep(1.5)
        print('OPS DIALOG:', target, json.dumps(dump(c), ensure_ascii=False, indent=1))
        close(c)
