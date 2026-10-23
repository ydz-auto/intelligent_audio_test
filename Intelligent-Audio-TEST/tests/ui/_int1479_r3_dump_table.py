# -*- coding: utf-8 -*-
"""INT-1479 R3：表格选择控件与批量工具条探明。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto, text  # noqa: E402


def dump(c):
    return c.eval("""
      (function(){
        const rows = Array.from(document.querySelectorAll('tbody tr')).slice(0, 4);
        const sel = rows.map(r => Array.from(r.querySelectorAll('[role=checkbox],input[type=checkbox],button'))
          .map(e => ({tag:e.tagName.toLowerCase(), role:e.getAttribute('role')||'', aria:e.getAttribute('aria-label')||'',
                      slot:e.getAttribute('data-slot')||'', txt:(e.innerText||'').trim().slice(0,30),
                      checked:e.getAttribute('aria-checked')||e.checked||''})));
        const bars = Array.from(document.querySelectorAll('button,[role=menuitem]'))
          .filter(e => /批量|更多/.test(e.innerText||'') || /批量|更多/.test(e.getAttribute('aria-label')||''))
          .map(e => ({aria:e.getAttribute('aria-label')||'', txt:(e.innerText||'').trim().slice(0,40),
                      slot:e.getAttribute('data-slot')||''}));
        return {rows: sel, bars};
      })()
    """)


if __name__ == '__main__':
    c = connect()
    goto(c, '/audio-import', 5)
    for _ in range(30):
        if '音频管理' in (text(c) or ''):
            break
        time.sleep(2)
    time.sleep(2)
    c.pump()
    print(json.dumps(dump(c), ensure_ascii=False, indent=1))
    print('FIRST_ROWS:', c.eval("Array.from(document.querySelectorAll('tbody tr')).slice(0,3).map(r=>r.innerText.replace(/\\n/g,' | ')).join('\\n')"))
