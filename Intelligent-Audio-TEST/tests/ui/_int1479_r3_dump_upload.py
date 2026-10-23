# -*- coding: utf-8 -*-
"""INT-1479 R3：上传弹窗结构探明。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto, text  # noqa: E402


def dump_dialog(c):
    return c.eval("""
      (function(){
        const d = document.querySelector('[role=dialog],[role=alertdialog]');
        if (!d) return null;
        const items = Array.from(d.querySelectorAll('input,textarea,select,button,[role=combobox],[role=checkbox],[role=tab]'))
          .map((e,i) => ({i, tag:e.tagName.toLowerCase(), type:e.type||'', role:e.getAttribute('role')||'',
                          name:e.getAttribute('name')||'', ph:e.getAttribute('placeholder')||'',
                          aria:e.getAttribute('aria-label')||'', text:(e.innerText||'').trim().slice(0,40),
                          value:(e.value===undefined?'':String(e.value)).slice(0,80),
                          checked:e.checked===undefined?'':e.checked}));
        return {text:(d.innerText||'').slice(0,800), items};
      })()
    """)


if __name__ == '__main__':
    c = connect()
    goto(c, '/audio-import', 5)
    for _ in range(30):
        if '音频管理' in (text(c) or ''):
            break
        time.sleep(2)
    c.eval("Array.from(document.querySelectorAll('button')).find(x => (x.innerText||'').trim() === '上传音频').click()")
    time.sleep(2)
    print(json.dumps(dump_dialog(c), ensure_ascii=False, indent=1))
