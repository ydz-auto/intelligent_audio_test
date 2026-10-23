# -*- coding: utf-8 -*-
"""INT-1479 R9：代码审计打回问题 3——补三个窗的深色截图（URL 导入 / 批量设置标签 / 特征分析）。

真实入口打开，浅色 + 深色各一张（深色走同源重载），并记录首帧与关键请求。
仅打开弹窗，不写库；不修改任何数据。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402

OUT = L.OUT


def text(c):
    return L.text(c)


def rows(c):
    return c.eval("document.querySelectorAll('tbody tr').length") or 0


def wait_for(fn, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def ready(c):
    return '音频管理' in text(c) and rows(c) > 0


def dialog_text(c):
    return c.eval("""(function(){
      const ds = Array.from(document.querySelectorAll('[role=dialog],[role=alertdialog]'));
      if (!ds.length) return '';
      const d = ds[ds.length-1];
      return (d.innerText || '');
    })()""") or ''


def close_dialog(c):
    c.eval("""(function(){
      const ds = Array.from(document.querySelectorAll('[role=dialog],[role=alertdialog]'));
      if (!ds.length) return 'NO_DIALOG';
      const d = ds[ds.length-1];
      const esc = d.querySelector("[aria-label*=关闭],[aria-label*=Close]");
      if (esc) { esc.click(); return 'ARIA_CLOSE'; }
      return 'NO_CLOSE';
    })()""")
    c.send('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    c.send('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    time.sleep(1.2)
    return c.eval("document.querySelectorAll('[role=dialog],[role=alertdialog]').length")


def is_dark(c):
    return bool(c.eval("document.documentElement.classList.contains('dark')"))


def goto_audio(c):
    L.nav(c, '/audio-import', 6)
    ok = wait_for(lambda: ready(c), 240)
    if not ok:
        # 冷启动时可能出现「进入工作台」入口
        L.click(c, '进入工作台')
        time.sleep(3)
        ok = wait_for(lambda: ready(c), 180)
    return ok


def first_row_name(c):
    return c.eval("""(function(){
      const tr = document.querySelector('tbody tr');
      if (!tr) return '';
      const td = tr.querySelectorAll('td');
      for (let i = 0; i < td.length; i++) {
        const t = (td[i].innerText || '').trim();
        if (/\\.(wav|mp3|flac|m4a|ogg)/i.test(t)) return t.split('\\n')[0].trim();
      }
      return (tr.innerText || '').split('\\n')[1] || '';
    })()""") or ''


def open_row_menu(c, name):
    return c.eval("""(function(name){
      const b = Array.from(document.querySelectorAll('button')).find(x => (x.getAttribute('aria-label')||'').includes('音频 ' + name + ' 的操作'));
      if (!b) return 'NO_MENU_BTN:' + name;
      b.click();
      return 'OPENED';
    })(%s)""" % json.dumps(name))


def click_menuitem(c, label):
    return c.eval("""(function(label){
      const items = Array.from(document.querySelectorAll('[role=menuitem]'));
      const el = items.find(n => (n.textContent||'').includes(label));
      if (!el) return 'NOT_FOUND:' + label + ' | have=' + items.map(n=>(n.textContent||'').trim()).join(',');
      el.click();
      return 'CLICKED:' + label;
    })(%s)""" % json.dumps(label))


def select_first_row(c):
    return c.eval("""(function(){
      const cb = document.querySelector('tbody tr [aria-label^="选择音频"]');
      if (!cb) return 'NO_CHECKBOX';
      cb.click();
      return 'CHECKED';
    })()""")


def batch_toolbar_text(c):
    return c.eval("""(function(){
      const m = (document.body.innerText||'').match(/已选\\s*\\d+\\s*个音频/);
      return m ? m[0] : '';
    })()""") or ''


def capture(c, tag, opener, expect_text, out, network_idx):
    """浅色 + 深色各打开一次并截图。"""
    for theme, suffix in (('light', 'light'), ('dark', 'dark')):
        L.set_theme(c, theme)
        ok = goto_audio(c)
        out[f'{tag}_{suffix}_ready'] = ok
        out[f'{tag}_{suffix}_dark_class'] = is_dark(c)
        time.sleep(2)
        ev0 = len(c.events)
        opened = opener(c)
        out[f'{tag}_{suffix}_open'] = opened
        hit = wait_for(lambda: expect_text in dialog_text(c), 60)
        time.sleep(1.5)
        dtext = dialog_text(c)
        out[f'{tag}_{suffix}_has_dialog'] = bool(dtext)
        out[f'{tag}_{suffix}_marker'] = hit
        out[f'{tag}_{suffix}_text'] = dtext.replace('\n', ' | ')[:1200]
        out[f'{tag}_{suffix}_shot'] = L.shot(c, f'r9-{tag}-{suffix}')
        # 关键请求（打开动作触发的接口）
        reqs, resps = [], []
        for e in c.events[ev0:]:
            if e['method'] == 'Network.requestWillBeSent':
                r = e['params']['request']
                if '/api/' in r['url']:
                    reqs.append({'m': r['method'], 'u': r['url'].split('?')[0],
                                 'body': (r.get('postData') or '')[:300]})
            elif e['method'] == 'Network.responseReceived':
                r = e['params']['response']
                if '/api/' in r['url']:
                    resps.append({'status': r['status'], 'u': r['url'].split('?')[0]})
        out[f'{tag}_{suffix}_req'] = reqs[-6:]
        out[f'{tag}_{suffix}_resp'] = resps[-6:]
        left = close_dialog(c)
        out[f'{tag}_{suffix}_closed_remaining_dialogs'] = left
        print(f'[{tag}/{suffix}]', json.dumps({
            'ready': ok, 'dark': out[f'{tag}_{suffix}_dark_class'], 'marker': hit,
            'closing_left': left, 'shot': out[f'{tag}_{suffix}_shot']}, ensure_ascii=False), flush=True)
        time.sleep(1)


def main():
    os.makedirs(OUT, exist_ok=True)
    c = L.connect()
    out = {}
    try:
        # 基线：列表就绪（先建同源上下文，localStorage 才可写）
        out['base_ready'] = goto_audio(c)
        L.set_theme(c, 'light')
        out['base_rows'] = rows(c)
        out['rownames'] = first_row_name(c)
        print('BASE', out['base_ready'], out['base_rows'], out['rownames'], flush=True)
        name = out['rownames']

        # 1) URL 导入
        def open_url(c):
            return L.click(c, 'URL 导入')

        capture(c, 'url', open_url, '支持多行或逗号分隔批量导入音频 URL', out, None)

        # 2) 批量设置标签（先勾选 1 行，出现批量条）
        def open_tags(c):
            sel = select_first_row(c)
            tb = wait_for(lambda: bool(batch_toolbar_text(c)), 30)
            time.sleep(1)
            clicked = L.click(c, '批量设置标签')
            return {'select': sel, 'toolbar': batch_toolbar_text(c), 'toolbar_ok': tb, 'click': clicked}

        capture(c, 'tags', open_tags, '批量设置标签', out, None)

        # 3) 特征分析（行菜单）
        def open_feature(c):
            m = open_row_menu(c, name)
            if m != 'OPENED':
                return {'menu': m}
            time.sleep(1.2)
            items = c.eval("Array.from(document.querySelectorAll('[role=menuitem]')).map(n=>(n.textContent||'').trim())")
            r = click_menuitem(c, '特征分析')
            return {'menu': m, 'items': items, 'click': r}

        capture(c, 'feature', open_feature, '音频特征分析', out, None)

        # 收尾：清选择（避免下一轮状态残留）
        c.eval("""(function(){const b=document.querySelector("[aria-label='清空选择']"); if(b) b.click(); return 'ok';})()""")
        out['final_theme'] = c.eval("localStorage.getItem('iatp:theme:v1:mode')")
    finally:
        with open(os.path.join(OUT, 'r9_dark_shots.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
