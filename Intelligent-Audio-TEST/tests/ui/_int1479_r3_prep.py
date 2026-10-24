# -*- coding: utf-8 -*-
"""INT-1479 R3 准备：生成测试 WAV + 探明工具栏/行操作菜单项。"""
import json
import math
import os
import struct
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import buttons, connect, goto, text  # noqa: E402

OUTDIR = os.environ.get('INT1479_WAV', os.path.join(os.environ.get('TEMP', '.'), 'int1479_wav'))
ROOT = os.path.dirname(os.path.abspath(__file__))


def make_wavs():
    os.makedirs(OUTDIR, exist_ok=True)
    paths = []
    for i, freq in enumerate((440, 660, 880), start=1):
        p = os.path.join(OUTDIR, f'接线测试_INT1479R3_{i}.wav')
        with wave.open(p, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            data = b''.join(struct.pack('<h', int(12000 * math.sin(2 * math.pi * freq * t / 16000)))
                            for t in range(16000 * 2))
            w.writeframes(data)
        paths.append(p)
    return paths


def menu_dump(c, label):
    r = c.eval("""
      (function(label){
        const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText||'').trim() === label);
        if(!b) return 'NO_BTN';
        b.click(); return 'CLICKED';
      })(%s)""" % json.dumps(label))
    time.sleep(1.2)
    items = c.eval("""
      Array.from(document.querySelectorAll('[role=menuitem]')).map(e => (e.innerText||'').trim())
    """)
    c.eval("document.body.click()")
    time.sleep(0.4)
    return r, items


if __name__ == '__main__':
    paths = make_wavs()
    print('WAVS', json.dumps(paths, ensure_ascii=False))
    c = connect()
    goto(c, '/audio-import', 5)
    for _ in range(30):
        if '音频管理' in (text(c) or ''):
            break
        time.sleep(2)
    print('MORE_MENU', json.dumps(menu_dump(c, '更多操作'), ensure_ascii=False))
    # 行操作菜单
    r = c.eval("""
      (function(){
        const b = Array.from(document.querySelectorAll('button')).find(x => (x.getAttribute('aria-label')||'').includes('接线测试_int1261'));
        if(!b) return 'NO_BTN'; b.click(); return 'OK';
      })()""")
    time.sleep(1.2)
    print('ROW_MENU', r, json.dumps(c.eval(
        "Array.from(document.querySelectorAll('[role=menuitem]')).map(e => (e.innerText||'').trim())"),
        ensure_ascii=False))
    c.eval("document.body.click()")
