# -*- coding: utf-8 -*-
"""INT-1479 R3：URL 导入 / 文件夹导入 弹窗结构探明。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto  # noqa: E402


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def dump(c):
    return c.eval("""
      (function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return null;
        return {text:(d.innerText||'').slice(0,1500),
          items:Array.from(d.querySelectorAll('input,textarea,select,button,[role=combobox],[role=checkbox],[role=radio],[role=switch]'))
            .map((e,i)=>({i,tag:e.tagName.toLowerCase(),type:e.type||'',role:e.getAttribute('role')||'',
              aria:e.getAttribute('aria-label')||'',ph:e.getAttribute('placeholder')||'',
              text:(e.innerText||'').trim().slice(0,50),value:(e.value===undefined?'':String(e.value)).slice(0,90),
              checked:e.getAttribute('aria-checked')||e.checked||''}))};})()
    """)


def close(c):
    c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return;
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消'||(x.getAttribute('aria-label')||'')==='Close');if(b)b.click();})()""")
    time.sleep(1)


if __name__ == '__main__':
    c = connect()
    goto(c, '/audio-import', 5); wait_rows(c); time.sleep(2)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='URL 导入').click(), 'ok'""")
    time.sleep(1.5)
    print('URL DIALOG:', json.dumps(dump(c), ensure_ascii=False, indent=1))
    close(c)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量从文件夹导入').click(), 'ok'""")
    time.sleep(1.5)
    print('FOLDER DIALOG:', json.dumps(dump(c), ensure_ascii=False, indent=1))
