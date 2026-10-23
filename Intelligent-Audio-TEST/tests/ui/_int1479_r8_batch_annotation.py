# -*- coding: utf-8 -*-
"""INT-1479 R8 · B：批量更新标注（INT-1582 修复复走）。

1) 匹配口径：列表先按关键字过滤，使目标音频不在已载入行；拖入「内容相同、文件名不同」的
   音频副本 + 同名 txt → 必须按内容 MD5 全库命中（旧实现按文件名在已载入行匹配，必然落空）。
2) 真实提交：开始更新 → POST /audios/batch/annotations 请求体/响应 → GET /audios/{id} 回读。
3) 未匹配原因：只拖标注 / 拖库外音频，核对分类文案与主钮禁用。
4) 浅色 + 深色截图。
"""
import json
import os
import shutil
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402
import _int1479_api as A  # noqa: E402

ASSET = r'D:\00_user_data\.cache\int1479_r8\assets'
OUT = L.OUT
COPY = os.path.join(ASSET, '接线测试_INT1479_标注源_改名副本.wav')
TXT = os.path.join(ASSET, '接线测试_INT1479_标注源_改名副本.txt')
OUTSIDER = os.path.join(ASSET, 'sig1479_outsider.wav')
OUT_TXT = os.path.join(ASSET, 'sig1479_outsider.txt')
NOTE = 'INT1479 批量标注校验文本'


def rows(c):
    return c.eval("document.querySelectorAll('tbody tr').length") or 0


def search(c, kw):
    return c.eval("""(function(k){const i=document.querySelector("input[aria-label='搜索音频']");
      if(!i) return 'NO_INPUT';
      const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      setter.call(i,k); i.dispatchEvent(new Event('input',{bubbles:true})); return 'SET';})(%s)"""
                  % json.dumps(kw))


def open_batch(c):
    return c.eval("""(function(){const b=Array.from(document.querySelectorAll('button'))
      .find(x=>(x.innerText||'').trim()==='批量更新标注');
      if(!b)return 'NOT_FOUND';b.click();return 'CLICKED';})()""")


def dlg(c):
    return "(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();"\
           "return d?(d.innerText||''):'';})()"


def set_files(c, files):
    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'],
                                        'selector': '[role=dialog] input[type=file]'})
    if not node.get('nodeId'):
        return 'NO_INPUT'
    c.send('DOM.setFileInputFiles', {'files': files, 'nodeId': node['nodeId']})
    return 'SET'


def net_since(c, i):
    reqs, resps = [], []
    for e in c.events[i:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                reqs.append({'m': r['method'], 'u': r['url'].split('?')[0],
                             'body': (r.get('postData') or '')[:1200]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                resps.append({'status': r['status'], 'u': r['url'].split('?')[0]})
    return reqs, resps


def api_get(aid):
    r = requests.get('%s/audios/%s' % (A.API, aid), headers=A.H(), timeout=120)
    return r.status_code, ((r.json() or {}).get('data') or {})


def wait_processed(c, timeout=120):
    end = time.time() + timeout
    last = ''
    while time.time() < end:
        t = c.eval(dlg(c)) or ''
        if '匹配' in t and '已解析' in t:
            return t
        last = t
        time.sleep(2)
    return last


def close_dialog(c):
    return c.eval("""(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      if(!d)return 'NO_DLG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消');
      if(!b)return 'NO_CANCEL';b.click();return 'CLOSED';})()""")


def open_page(c, theme):
    L.nav(c, '/audio-import', 6)
    L.set_theme(c, theme)
    L.nav(c, '/audio-import', 8)
    ok = L.wait_ready(c, 240)
    time.sleep(1.5)
    return ok


def main():
    os.makedirs(OUT, exist_ok=True)
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 2494
    # 夹具：同内容改名副本 + 同名 txt；库外音频（未上传内容）+ 同名 txt
    if not os.path.isfile(COPY):
        shutil.copyfile(os.path.join(ASSET, 'sig1479_ann.wav'), COPY)
    with open(TXT, 'w', encoding='utf-8') as f:
        f.write(NOTE + '\n')
    with open(OUTSIDER, 'wb') as f:
        f.write(os.urandom(16000 * 2 * 2))
    with open(OUT_TXT, 'w', encoding='utf-8') as f:
        f.write('库外音频的标注\n')
    out = {'copy': os.path.basename(COPY), 'txt': os.path.basename(TXT),
           'outsider': os.path.basename(OUTSIDER)}

    c = L.connect()
    # ---------- 浅色：全库 MD5 命中 + 真实提交 ----------
    print('READY', open_page(c, 'light'), flush=True)
    search(c, '接线测试_INT1613')       # 目标音频 2494 不在已载入行
    time.sleep(3)
    out['loaded_rows'] = rows(c)
    out['target_in_loaded_rows'] = c.eval(
        "Array.from(document.querySelectorAll('tbody tr')).some(r=>r.innerText.includes('INT1479'))")
    print('ROWS', out['loaded_rows'], 'target_loaded', out['target_in_loaded_rows'], flush=True)
    print('OPEN', open_batch(c)); time.sleep(2.5)
    print('FILES', set_files(c, [COPY, TXT]), flush=True)
    t = wait_processed(c, 120)
    out['dialog_text_light'] = t.replace('\n', ' | ')[:1200]
    out['matched_hint'] = '接线测试_INT1479_标注_上传.wav' in t and ('#%d' % aid) in t
    out['summary'] = c.eval("""(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      const s=(d.innerText||'').match(/已解析[\\s\\S]{0,80}/); return s?s[0].replace(/\\n/g,' | '):'';})()""")
    out['start_btn'] = c.eval("""(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      const b=Array.from(d.querySelectorAll('button')).find(x=>/开始更新/.test(x.innerText||''));
      return b?{text:(b.innerText||'').trim(),disabled:b.disabled}:null;})()""")
    print('SUMMARY', json.dumps(out['summary'], ensure_ascii=False), flush=True)
    print('START BTN', json.dumps(out['start_btn'], ensure_ascii=False), flush=True)
    out['shot_light'] = L.shot(c, 'r8-b1-batch-annotation-matched-light')

    t0 = len(c.events)
    print('CLICK START', c.eval("""(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      const b=Array.from(d.querySelectorAll('button')).find(x=>/开始更新/.test(x.innerText||''));
      if(!b||b.disabled)return 'NO_BTN_OR_DISABLED';b.click();return 'CLICKED';})()"""), flush=True)
    end = time.time() + 180
    while time.time() < end:
        time.sleep(2)
        c.pump()
        if not c.eval(dlg(c)):
            break
    time.sleep(2)
    c.pump()
    reqs, resps = net_since(c, t0)
    out['reqs'] = [r for r in reqs if 'batch/annotations' in r['u']]
    out['resps'] = [r for r in resps if 'batch/annotations' in r['u']]
    out['toast'] = c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim())") or []
    print('REQ', json.dumps(out['reqs'], ensure_ascii=False), flush=True)
    print('RESP', json.dumps(out['resps'], ensure_ascii=False), flush=True)
    print('TOAST', json.dumps(out['toast'], ensure_ascii=False), flush=True)
    st, info = api_get(aid)
    out['readback_status'] = st
    out['readback'] = {'id': info.get('id'), 'name': info.get('name'),
                       'asr_text': info.get('asr_text'),
                       'annotations': info.get('annotations'), 'updated_at': info.get('updated_at')}
    print('READBACK', json.dumps(out['readback'], ensure_ascii=False)[:1200], flush=True)
    out['shot_after'] = L.shot(c, 'r8-b2-batch-annotation-after-light')

    # ---------- 未匹配原因：只有标注 ----------
    print('OPEN2', open_batch(c)); time.sleep(2.5)
    print('FILES2', set_files(c, [TXT]), flush=True)
    time.sleep(6)
    t2 = c.eval(dlg(c)) or ''
    out['unmatched_no_audio_text'] = t2.replace('\n', ' | ')[:900]
    out['unmatched_no_audio_reason'] = '未拖入音频文件，无法按内容 MD5 匹配' in t2
    out['start_btn_no_audio'] = c.eval("""(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      const b=Array.from(d.querySelectorAll('button')).find(x=>/开始更新/.test(x.innerText||''));
      return b?{text:(b.innerText||'').trim(),disabled:b.disabled}:null;})()""")
    print('NO-AUDIO reason', out['unmatched_no_audio_reason'],
          json.dumps(out['start_btn_no_audio'], ensure_ascii=False), flush=True)
    print('CLOSE', close_dialog(c)); time.sleep(1.5)

    # ---------- 未匹配原因：库外音频 ----------
    print('OPEN3', open_batch(c)); time.sleep(2.5)
    print('FILES3', set_files(c, [OUTSIDER, OUT_TXT]), flush=True)
    time.sleep(8)
    t3 = c.eval(dlg(c)) or ''
    out['unmatched_outsider_text'] = t3.replace('\n', ' | ')[:900]
    out['unmatched_outsider_reason'] = '音频内容 MD5 不在库内' in t3
    print('OUTSIDER reason', out['unmatched_outsider_reason'], flush=True)
    out['shot_unmatched'] = L.shot(c, 'r8-b3-batch-annotation-unmatched-light')

    # ---------- 深色 ----------
    print('DARK READY', open_page(c, 'dark'), flush=True)
    print('DARK THEME', c.eval("document.documentElement.classList.contains('dark')"), flush=True)
    search(c, '接线测试_INT1613'); time.sleep(2)
    print('OPEN4', open_batch(c)); time.sleep(2.5)
    print('FILES4', set_files(c, [COPY, TXT]), flush=True)
    t4 = wait_processed(c, 120)
    out['dialog_text_dark'] = t4.replace('\n', ' | ')[:900]
    out['shot_dark'] = L.shot(c, 'r8-b4-batch-annotation-dark')
    print('CLOSE', close_dialog(c), flush=True)

    with open(os.path.join(OUT, 'r8_batch_annotation.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
