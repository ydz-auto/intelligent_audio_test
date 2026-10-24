# -*- coding: utf-8 -*-
"""INT-1479 R5 · A1：用例页共用音频入口复走。

路径：/testcases → 新增用例（真实入口）→ 抽屉「音频列表」步 → 「从音频库选择」
→ 弹窗头部「上传音频」/「批量从文件夹导入」两个共用入口各开一次（只走入口不回读）。
浅色 + 深色各一轮，记录打开时的真实请求。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402

REPORT = {'steps': []}


def log(step, **kv):
    kv['step'] = step
    REPORT['steps'].append(kv)
    print('[STEP]', step, json.dumps(kv, ensure_ascii=False)[:900], flush=True)


def body_text(c):
    try:
        return c.eval("(document.body && document.body.innerText) || ''") or ''
    except Exception as e:
        return 'ERR:%s' % e


def wait_text(c, needle, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        t = body_text(c)
        if needle in t:
            return True
        if '进入工作台' in t:
            L.click(c, '进入工作台')
        time.sleep(2)
    return False


def js_click_text(c, label, scope=None, tag='button'):
    js = """
    (function(label, scopeSel, tag){
      const root = scopeSel ? document.querySelector(scopeSel) : document;
      if (!root) return 'NO_SCOPE';
      const nodes = Array.from(root.querySelectorAll(tag + ',[role=menuitem],[role=option],[role=tab]'));
      const el = nodes.find(n => (n.innerText||'').trim() === label) ||
                 nodes.find(n => (n.innerText||'').trim().endsWith(label));
      if (!el) return 'NOT_FOUND:' + label;
      el.click();
      return 'CLICKED:' + label;
    })(%s, %s, %s)
    """
    return c.eval(js % (json.dumps(label, ensure_ascii=False),
                        json.dumps(scope) if scope else 'null',
                        json.dumps(tag)))


def dialog_texts(c):
    return c.eval("""Array.from(document.querySelectorAll('[role=dialog]')).map(d=>({
        title: (d.querySelector('[role=dialog] [class*=text-lg],[data-slot=dialog-title],h2')||{}).innerText || '',
        text: (d.innerText||'').replace(/\\n/g,' | ').slice(0,600),
        fileInput: d.querySelectorAll('input[type=file]').length,
        buttons: Array.from(d.querySelectorAll('button')).map(b=>(b.innerText||'').trim()).filter(Boolean)
    }))""") or []


def close_top_dialog(c):
    """关闭最上层弹窗：优先关闭按钮，其次「取消」，最后 Esc。"""
    r = c.eval("""(function(){
      const ds = Array.from(document.querySelectorAll('[role=dialog]'));
      const d = ds[ds.length-1];
      if (!d) return 'NO_DIALOG';
      const x = d.querySelector('[aria-label=Close],[aria-label=关闭]');
      if (x) { x.click(); return 'X'; }
      const cancel = Array.from(d.querySelectorAll('button')).find(b=>(b.innerText||'').trim()==='取消');
      if (cancel) { cancel.click(); return 'CANCEL'; }
      const c2 = Array.from(d.querySelectorAll('button')).find(b=>(b.innerText||'').trim().includes('关闭'));
      if (c2) { c2.click(); return 'CLOSE_BTN'; }
      return 'NO_CLOSER';
    })()""")
    time.sleep(1.5)
    return r


def open_case_drawer(c):
    """用例页 → 新增用例 → 抽屉。"""
    r = js_click_text(c, '新增用例')
    time.sleep(3)
    t = body_text(c)
    return {'click': r, 'drawer': ('轮次配置' in t), 'has_audio_step': ('音频列表' in t)}


def goto_audio_step(c):
    r = js_click_text(c, '音频列表', tag='[role=tab]')
    if r != 'CLICKED:音频列表':
        r = js_click_text(c, '音频列表')
    time.sleep(3)
    t = body_text(c)
    return {'click': r, 'has_pick': ('从音频库选择' in t)}


def open_select_dialog(c):
    r = js_click_text(c, '从音频库选择')
    time.sleep(4)
    t = body_text(c)
    return {'click': r, 'has_upload_entry': ('上传音频' in t),
            'has_folder_entry': ('批量从文件夹导入' in t)}


def click_in_dialog(c, label_parts):
    js = """
    (function(parts){
      const ds = Array.from(document.querySelectorAll('[role=dialog]'));
      const d = ds[ds.length-1];
      if (!d) return 'NO_DIALOG';
      const b = Array.from(d.querySelectorAll('button')).find(x=>{
        const t=(x.innerText||'').trim();
        return parts.every(p=>t.includes(p));
      });
      if (!b) return 'NOT_FOUND';
      b.click();
      return 'CLICKED:' + (b.innerText||'').trim();
    })(%s)
    """ % json.dumps(label_parts, ensure_ascii=False)
    r = c.eval(js)
    time.sleep(4)
    return r


def round_run(c, theme):
    """一轮：打开选择弹窗 → 两个共用入口 → 截图。"""
    prefix = 'r5_%s' % theme
    net0 = len(c.events)
    st = open_select_dialog(c)
    c.pump()
    open_reqs, open_resps = L.net_since(c, net0)
    open_reqs = [r for r in open_reqs if '/audios' in r['u']]
    open_resps = [r for r in open_resps if '/audios' in r['u']]
    time.sleep(1)
    shot1 = L.shot(c, prefix + '-01-audio-select-dialog')
    log('select_dialog:' + theme, state=st, screenshots=[shot1],
        dialogs=dialog_texts(c), open_reqs=open_reqs[:8], open_resps=open_resps[:8])

    # 入口 1：上传音频
    net1 = len(c.events)
    r1 = click_in_dialog(c, ['上传音频'])
    c.pump()
    reqs1, resps1 = L.net_since(c, net1)
    shot2 = L.shot(c, prefix + '-02-upload-entry')
    log('upload_entry:' + theme, click=r1, screenshots=[shot2],
        dialogs=dialog_texts(c),
        reqs=[x for x in reqs1 if '/api/' in x['u']][:8],
        resps=[x for x in resps1 if '/api/' in x['u']][:8])
    closer1 = close_top_dialog(c)
    log('upload_entry_close:' + theme, closer=closer1,
        dialogs=dialog_texts(c))

    # 入口 2：批量从文件夹导入
    net2 = len(c.events)
    r2 = click_in_dialog(c, ['批量从文件夹导入'])
    c.pump()
    reqs2, resps2 = L.net_since(c, net2)
    time.sleep(2)
    c.pump()
    reqs2b, resps2b = L.net_since(c, net2)
    shot3 = L.shot(c, prefix + '-03-folder-entry')
    log('folder_entry:' + theme, click=r2, screenshots=[shot3],
        dialogs=dialog_texts(c),
        reqs=[x for x in reqs2b if '/api/' in x['u']][:10],
        resps=[x for x in resps2b if '/api/' in x['u']][:10])
    closer2 = close_top_dialog(c)
    log('folder_entry_close:' + theme, closer=closer2, dialogs=dialog_texts(c))

    # 关闭选择弹窗
    closer3 = close_top_dialog(c)
    log('select_dialog_close:' + theme, closer=closer3, dialogs=dialog_texts(c))


def main():
    os.makedirs(L.OUT, exist_ok=True)
    c = L.connect()
    L.nav(c, '/testcases/by-group', 10)
    ok = wait_text(c, '用例管理', 200)
    if ok:
        L.set_theme(c, 'light')
        try:
            c.send('Page.reload')
        except Exception:
            pass
        time.sleep(8)
        ok = wait_text(c, '用例管理', 200)
    print('PAGE_OK', ok, flush=True)
    if not ok:
        L.nav(c, '/testcases', 10)
        ok = wait_text(c, '用例管理', 200)
        print('PAGE_OK2', ok, flush=True)
    log('page', url=c.eval('location.href'), ok=ok,
        text=(body_text(c) or '')[:400])
    if not ok:
        print('ABORT_PAGE', flush=True)
        json.dump(REPORT, open(os.path.join(L.OUT, 'r5_a1_report.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        return

    st = open_case_drawer(c)
    log('drawer_open', **st)
    if not st.get('drawer'):
        print('ABORT_DRAWER', body_text(c)[:800], flush=True)
        return
    st = goto_audio_step(c)
    log('audio_step', **st)
    if not st.get('has_pick'):
        print('ABORT_STEP', body_text(c)[:800], flush=True)
        return

    round_run(c, 'light')
    L.shot(c, 'r5_light-00-drawer-audio-step')

    # 深色轮：重载后重走
    L.set_theme(c, 'dark')
    try:
        c.send('Page.reload')
    except Exception:
        pass
    time.sleep(8)
    wait_text(c, '用例管理', 200)
    st = open_case_drawer(c)
    log('drawer_open:dark', **st)
    st = goto_audio_step(c)
    log('audio_step:dark', **st)
    if st.get('has_pick'):
        round_run(c, 'dark')
        L.shot(c, 'r5_dark-00-drawer-audio-step')

    os.makedirs(L.OUT, exist_ok=True)
    with open(os.path.join(L.OUT, 'r5_a1_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
