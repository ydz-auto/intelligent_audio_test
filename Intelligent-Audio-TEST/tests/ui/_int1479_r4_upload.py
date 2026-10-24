# -*- coding: utf-8 -*-
"""INT-1479 R4：上传进度真实分片事件复走（INT-1512 修复项）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402
from _int1479_api import API, H  # noqa: E402

WAVDIR = os.path.join(os.environ.get('TEMP', '.'), 'int1479_r4_wav')
FILES = [os.path.join(WAVDIR, '接线测试_INT1479R5_1.wav'),
         os.path.join(WAVDIR, '接线测试_INT1479R5_2.wav')]
REPORT = {}


def make():
    import shutil
    os.makedirs(WAVDIR, exist_ok=True)
    for i, src in enumerate(('接线测试_INT1479R4_1.wav', '接线测试_INT1479R4_2.wav'), start=1):
        dst = FILES[i - 1]
        if not os.path.exists(dst):
            shutil.copyfile(os.path.join(WAVDIR, src), dst)
    return FILES


def main():
    files = make()
    c = L.connect()
    L.nav(c, '/audio-import', 8)
    ok = L.wait_ready(c, 240)
    print('READY', ok, flush=True)
    if not ok:
        c.send('Page.reload'); time.sleep(10); ok = L.wait_ready(c, 240)
        print('READY2', ok, flush=True)
    if not ok:
        print('ABORT', flush=True); return
    L.set_theme(c, 'light')

    t = len(c.events)
    print('OPEN', L.click(c, '上传音频'), flush=True)
    time.sleep(2)
    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'],
                                        'selector': '[role=dialog] input[type=file]'})
    c.send('DOM.setFileInputFiles', {'files': files, 'nodeId': node['nodeId']})
    time.sleep(2)
    print('SUBMIT', c.eval("""(function(){const d=document.querySelector('[role=dialog]');
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith('开始上传'));
      if(!b) return 'NO_BTN'; b.click(); return 'CLICKED';})()"""), flush=True)

    samples = []
    for i in range(40):
        time.sleep(1)
        c.pump()
        card = c.eval("""(function(){
          const el=document.querySelector('[data-slot=upload-progress-card]')||
                   Array.from(document.querySelectorAll('div')).find(d=>(d.innerText||'').includes('队列控制'));
          return el ? (el.innerText||'').replace(/\\n/g,' | ') : '';})()""")
        if card:
            samples.append(card[:220])
        if card and ('完成并关闭' in card or '导入完成' in card) and i > 4:
            break
    REPORT['samples'] = samples
    print('SAMPLES', json.dumps(samples[:12], ensure_ascii=False), flush=True)
    reqs, resps = L.net_since(c, t)
    REPORT['net'] = {'reqs': [r for r in reqs if 'upload' in r['u']],
                     'resps': [r for r in resps if 'upload' in r['u']]}
    print('UPLOAD_NET', json.dumps(REPORT['net'], ensure_ascii=False)[:1500], flush=True)
    L.shot(c, 'r4-18-upload-progress')

    with open(os.path.join(L.OUT, 'r4_upload_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
