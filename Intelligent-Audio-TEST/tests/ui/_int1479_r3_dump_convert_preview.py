# -*- coding: utf-8 -*-
"""INT-1479 R3：转换格式 / 试听 弹窗结构探明。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto  # noqa: E402

NAME = '测试音频_01.wav'


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def open_row_menu(c, name):
    return c.eval("""
      (function(n){const b=Array.from(document.querySelectorAll('button')).find(x=>(x.getAttribute('aria-label')||'')==='音频 '+n+' 的操作');
        if(!b) return 'NO_BTN'; b.click(); return 'OK';})(%s)""" % json.dumps(name))


def menu_click(c, label):
    return c.eval("""
      (function(l){const m=Array.from(document.querySelectorAll('[role=menuitem]')).find(e=>(e.innerText||'').trim()===l);
        if(!m) return 'NO_ITEM'; m.click(); return 'CLICKED';})(%s)""" % json.dumps(label))


def dump(c):
    return c.eval("""
      (function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return null;
        return {text:(d.innerText||'').slice(0,1200),
          items:Array.from(d.querySelectorAll('input,textarea,select,button,[role=combobox],[role=checkbox],[role=radio],[role=switch]'))
            .map((e,i)=>({i,tag:e.tagName.toLowerCase(),type:e.type||'',role:e.getAttribute('role')||'',
              aria:e.getAttribute('aria-label')||'',ph:e.getAttribute('placeholder')||'',
              text:(e.innerText||'').trim().slice(0,50),value:(e.value===undefined?'':String(e.value)).slice(0,80),
              checked:e.getAttribute('aria-checked')||e.checked||''}))};})()
    """)


def close(c):
    c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return;
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消'||(x.getAttribute('aria-label')||'')==='Close');if(b)b.click();})()""")
    time.sleep(1)


if __name__ == '__main__':
    c = connect()
    goto(c, '/audio-import', 5); wait_rows(c); time.sleep(2)
    print('ROW', open_row_menu(c, NAME)); time.sleep(1)
    print('CONVERT:', menu_click(c, '转换格式')); time.sleep(2)
    print('CONVERT DIALOG:', json.dumps(dump(c), ensure_ascii=False, indent=1))
    close(c)
    print('ROW', open_row_menu(c, NAME)); time.sleep(1)
    print('PREVIEW:', menu_click(c, '预览')); time.sleep(2.5)
    print('PREVIEW DIALOG:', json.dumps(dump(c), ensure_ascii=False, indent=1))
    print('PREVIEW TEXT:', (c.eval("(document.querySelector('[role=dialog]')||{}).innerText||''") or '')[:800].replace('\n', ' | '))
