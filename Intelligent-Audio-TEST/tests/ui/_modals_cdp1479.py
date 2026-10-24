# -*- coding: utf-8 -*-
"""INT-1479 11 模态窗截图（CDP 直连 Chrome，chromedriver 在重负载下不可用）。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cdp1479 import CDP  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
BASE = 'http://127.0.0.1:15173/audio-import'
CLICK_JS = """
(function(label, exact, role){
  const nodes = Array.from(document.querySelectorAll(role || 'button,[role=menuitem],a'));
  const el = nodes.find(n => (n.textContent||'').trim() === label) ||
             (!exact && nodes.find(n => (n.textContent||'').includes(label)));
  if (!el) return 'NOT_FOUND:' + label;
  el.click();
  return 'CLICKED:' + label;
})(%s, %s, %s)
"""


def ev(c, expr):
    try:
        return c.eval(expr)
    except Exception as exc:
        return f'ERR:{type(exc).__name__}:{str(exc)[:150]}'


def click_text(c, label, exact=True, role=None):
    return c.eval(CLICK_JS % (json.dumps(label), 'true' if exact else 'false',
                              json.dumps(role) if role else 'null'))


def dialog_text(c):
    return ev(c, "(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText || ''") or ''


def shot(c, name):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name + '.png')
    c.screenshot(p)
    return os.path.getsize(p)


def close_dialog(c):
    for label in ('关闭', '取消'):
        r = click_text(c, label)
        if str(r).startswith('CLICKED'):
            time.sleep(0.7)
            return
    ev(c, "document.querySelector('[role=dialog]')?.querySelector('button')?.click()")


def wait_page(c, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        t = ev(c, "document.querySelector('[role=main],main') ? (document.body.innerText||'') : ''") or ''
        if '音频管理' in t and '列表视图' in t and (ev(c, 'document.querySelectorAll("tbody tr").length') or 0) > 0:
            return True
        time.sleep(2)
    return False


def first_row_name(c):
    return ev(c, "(document.querySelector('tbody tr td:nth-child(3)')||{}).innerText || ''") or ''


def select_first(c):
    return ev(c, "(document.querySelector('tbody tr [aria-label^=\"选择音频\"]')||{}).click(), 'ok'")


def open_row_menu(c, name):
    return ev(c, """
      (function(name){
        const b = Array.from(document.querySelectorAll('button')).find(x => (x.getAttribute('aria-label')||'').includes('音频 '+name+' 的操作'));
        if(!b) return 'NO_BTN'; b.click(); return 'OK';
      })(%s)""" % json.dumps(name))


def run(theme, c, results):
    ev(c, "localStorage.setItem('iatp:theme:v1:mode', %r)" % theme)
    c.send('Page.navigate', {'url': BASE})
    ok = wait_page(c, 150)
    results.append({'step': f'{theme}:page', 'ok': ok})
    if not ok:
        return
    name = first_row_name(c)
    time.sleep(1)
    shot(c, f'{theme}-00-list')

    def step(slug, label, opener):
        try:
            t0 = len(c.events)
            r = opener()
            time.sleep(1.6)
            c.pump()
            dt = dialog_text(c)
            size = shot(c, f'{theme}-{slug}')
            reqs = []
            for e in c.events[t0:]:
                if e['method'] == 'Network.requestWillBeSent':
                    url = e['params']['request']['url']
                    if '/api/' in url:
                        reqs.append(e['params']['request']['method'] + ' ' + url.split('?')[0])
            results.append({'step': f'{theme}:{slug}', 'ok': bool(dt.strip()),
                            'action': str(r)[:80], 'dialog': dt[:200].replace('\n', ' | '),
                            'requests': reqs[:6], 'shot': size})
        except Exception as exc:
            results.append({'step': f'{theme}:{slug}', 'ok': False, 'error': str(exc)[:200]})
        finally:
            close_dialog(c)
            time.sleep(0.5)
            ev(c, "document.querySelector('[aria-label=清空选择]')?.click()")

    step('01-upload', '上传音频', lambda: click_text(c, '上传音频'))
    step('02-folder-import', '批量从文件夹导入', lambda: click_text(c, '批量从文件夹导入'))
    step('03-url-import', 'URL 导入', lambda: click_text(c, 'URL 导入'))
    step('04-batch-annotation', '批量更新标注', lambda: click_text(c, '批量更新标注'))
    step('05-batch-tags', '批量设置标签', lambda: (select_first(c), time.sleep(0.6), click_text(c, '批量设置标签')))
    step('06-batch-move', '批量移动', lambda: (select_first(c), time.sleep(0.5),
                                              click_text(c, '更多批量操作'), time.sleep(0.6), click_text(c, '批量移动', False)))
    step('07-batch-copy', '批量复制', lambda: (select_first(c), time.sleep(0.5),
                                              click_text(c, '更多批量操作'), time.sleep(0.6), click_text(c, '批量复制', False)))
    step('08-batch-rename', '批量重命名', lambda: (select_first(c), time.sleep(0.5),
                                                click_text(c, '更多批量操作'), time.sleep(0.6), click_text(c, '批量重命名', False)))
    step('09-batch-modify', '批量修改属性', lambda: (select_first(c), time.sleep(0.5),
                                                  click_text(c, '更多批量操作'), time.sleep(0.6), click_text(c, '批量修改属性', False)))
    step('10-preview', '试听', lambda: (open_row_menu(c, name), time.sleep(0.7), click_text(c, '预览', False)))
    step('11-metadata', '元数据', lambda: (open_row_menu(c, name), time.sleep(0.7), click_text(c, '详情 / 编辑元数据', False)))
    step('12-convert', '转换格式', lambda: (open_row_menu(c, name), time.sleep(0.7), click_text(c, '转换格式', False)))
    step('13-feature-analysis', '特征分析', lambda: (open_row_menu(c, name), time.sleep(0.7), click_text(c, '特征分析·质量评估', False)))
    step('14-playback-history', '播放历史', lambda: (open_row_menu(c, name), time.sleep(0.7), click_text(c, '播放历史', False)))


if __name__ == '__main__':
    pages = [t for t in requests.get('http://127.0.0.1:9222/json/list', timeout=10).json()
             if t.get('type') == 'page']
    c = CDP(pages[0]['webSocketDebuggerUrl'], timeout=60)
    c.send('Page.enable')
    c.send('Runtime.enable')
    c.send('Network.enable')
    results = []
    themes = sys.argv[1:] or ['light']
    try:
        for theme in themes:
            run(theme, c, results)
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, 'modals_cdp_results.json'), 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        for r in results:
            print(('PASS' if r.get('ok') else 'FAIL'), r['step'], '|',
                  str(r.get('dialog') or r.get('error') or '')[:110], '|', r.get('requests'))
