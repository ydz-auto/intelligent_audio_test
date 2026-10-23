# -*- coding: utf-8 -*-
"""INT-1479 R3：批量窗口探明（选中 3 条自建音频）。"""
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
        const out = [];
        for (const n of names) {
          const el = document.querySelector('[role=checkbox][aria-label="选择音频 '+n+'"]');
          if (!el) { out.push('MISS:' + n); continue; }
          el.click(); out.push('OK:' + n);
        }
        return out.join(' ');
      })(%s)""" % json.dumps(NAMES))


def dialog_dump(c):
    return c.eval("""
      (function(){
        const d = document.querySelector('[role=dialog],[role=alertdialog]');
        if (!d) return null;
        return {
          text: (d.innerText||'').slice(0, 1200),
          items: Array.from(d.querySelectorAll('input,textarea,select,button,[role=combobox],[role=checkbox],[role=radio],[role=switch]'))
            .map((e,i)=>({i, tag:e.tagName.toLowerCase(), type:e.type||'', role:e.getAttribute('role')||'',
                          aria:e.getAttribute('aria-label')||'', ph:e.getAttribute('placeholder')||'',
                          text:(e.innerText||'').trim().slice(0,50),
                          value:(e.value===undefined?'':String(e.value)).slice(0,80),
                          checked:e.getAttribute('aria-checked')||e.checked||''}))
        };
      })()
    """)


def open_more_menu(c):
    c.eval("Array.from(document.querySelectorAll('button')).find(x => (x.getAttribute('aria-label')||'') === '更多操作').click()")
    time.sleep(1.2)
    items = c.eval("Array.from(document.querySelectorAll('[role=menuitem]')).map(e => (e.innerText||'').trim())")
    c.eval("document.body.click()")
    time.sleep(0.5)
    return items


if __name__ == '__main__':
    c = connect()
    goto(c, '/audio-import', 5)
    for _ in range(30):
        if '音频管理' in (text(c) or ''):
            break
        time.sleep(2)
    time.sleep(2)
    print('SELECT:', select_rows(c))
    time.sleep(1)
    print('TOOLBAR:', c.eval("""
      Array.from(document.querySelectorAll('button')).filter(b => /批量|更多|清空/.test((b.innerText||'')+(b.getAttribute('aria-label')||'')))
        .map(b => ({aria:b.getAttribute('aria-label')||'', txt:(b.innerText||'').trim(), dis:b.disabled}))
    """))
    print('MORE_MENU:', json.dumps(open_more_menu(c), ensure_ascii=False))
    # 批量更新标注
    c.eval("Array.from(document.querySelectorAll('button')).find(x => (x.innerText||'').trim() === '批量更新标注').click()")
    time.sleep(1.8)
    print('ANNOTATION_DIALOG:', json.dumps(dialog_dump(c), ensure_ascii=False, indent=1))
