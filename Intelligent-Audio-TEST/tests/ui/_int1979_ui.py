# -*- coding: utf-8 -*-
"""INT-1979 走查：音频导入「标签来源」三档 + JSON 顶层 tags + register.relative_path。

连 docker 后端（dev server 5362 代理到 :15000）。
产出 artifacts/int1979/*.png + result.json（断言明细 + 捕获的请求载荷）。
"""
import json
import math
import os
import struct
import time
import wave

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1979')
FIX = os.path.join(ART, 'fixtures', '导入根')
BASE = 'http://localhost:5362'
DRIVER = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
os.makedirs(ART, exist_ok=True)


def ensure_fixtures():
    """夹具自建（不依赖运行前落盘）：导入根/组1/子目录 下 3 个 WAV + 2 个带顶层 tags 的用例 JSON。"""
    sub = os.path.join(FIX, '组1', '子目录')
    os.makedirs(sub, exist_ok=True)
    for name, freq in (('甲1.wav', 440), ('乙1.wav', 660), ('单独.wav', 880)):
        path = os.path.join(sub, name)
        if os.path.exists(path):
            continue
        rate, secs = 16000, 0.3
        frames = b''.join(struct.pack('<h', int(3000 * math.sin(2 * math.pi * freq * i / rate)))
                          for i in range(int(rate * secs)))
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(frames)
    cases = {
        '甲用例.json': {'audio': '甲1.wav', 'tags': ['甲标签']},
        '乙用例.json': {'txt': [{'audio': '乙1.wav'}], 'tags': ['乙标签']},
    }
    for name, body in cases.items():
        path = os.path.join(FIX, name)
        if os.path.exists(path):
            continue
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(body, fh, ensure_ascii=False, indent=2)


ensure_fixtures()

RESULT = {'steps': [], 'requests': [], 'cases': {}, 'errors': []}


def log(step, **kw):
    entry = {'step': step, **kw}
    RESULT['steps'].append(entry)
    print('[STEP]', json.dumps(entry, ensure_ascii=False), flush=True)


FETCH_PATCH = """
window.__reqlog = [];
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init){
    const url = (typeof input === 'string') ? input : (input && input.url) || '';
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    let body = '';
    try {
      if (init && typeof init.body === 'string') body = init.body;
    } catch(e) {}
    const res = await orig.apply(this, arguments);
    let respText = '';
    if (/\\/audios\\/upload\\/(merge|register)/.test(url)) {
      try { respText = (await res.clone().text()).slice(0, 4000); } catch(e) {}
    }
    try {
      window.__reqlog.push({url: url, method: method, body: body.slice(0, 8000),
                            status: res.status, resp: respText, t: Date.now()});
    } catch(e) {}
    return res;
  };
})();
"""

# 现存两个导入弹窗组件都常驻 DOM（关闭后节点仍在），`querySelector('[role=dialog]')`
# 可能命中已关闭的另一个弹窗（INT-1979 实测：重开时 radios 查不到）。统一取「可见的最后一个」。
VIS = """
const __d = (function(){
  const ds = Array.from(document.querySelectorAll('[role=dialog],[role=alertdialog]'))
    .filter(d => d.getClientRects().length > 0);
  return ds[ds.length - 1] || null;
})();
"""

DIALOG_TEXT_JS = VIS + """
return __d ? __d.innerText : '';
"""

MARK_JS = VIS + """
document.querySelectorAll('[data-int1979-open]').forEach(d => d.removeAttribute('data-int1979-open'));
if (__d) __d.setAttribute('data-int1979-open', '1');
return !!__d;
"""
OPEN_SEL = '[data-int1979-open]'


def make_driver():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1180')
    o.add_argument('--disable-gpu')
    o.add_argument('--force-device-scale-factor=1')
    o.page_load_strategy = 'eager'
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_script_timeout(300)
    d.set_page_load_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def wait_until(drv, fn, timeout=120, interval=0.5):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def js(drv, script):
    """execute_script 不把裸表达式当返回值（INT-1979 实测：IIFE / 末尾表达式结果恒 None）。
    统一包一层函数体并 return，使「语句 + return」与「裸 IIFE」两种写法都能拿到值。"""
    return drv.execute_script('return (function(){\n%s\n})()' % script)


def login(drv):
    drv.get(BASE + '/login')
    wait_until(drv, lambda: len(drv.find_elements(By.ID, 'username')) > 0, 60)
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.CSS_SELECTOR, 'button[type=submit]').click()
    ok = wait_until(drv, lambda: '/login' not in drv.current_url, 90)
    log('login', ok=ok, url=drv.current_url)
    return ok


def goto_audio(drv):
    drv.get(BASE + '/audio-import')
    ok = wait_until(
        drv, lambda: '音频管理' in js(drv, 'return document.body.innerText'), 120)
    log('open audio page', ok=ok)
    return ok


CLICK_TEXT_JS = VIS + """
return (function(label){
  const scope = __d || document;
  const nodes = Array.from(scope.querySelectorAll('button,a,[role=menuitem]'));
  const el = nodes.find(n => (n.innerText||'').trim() === label)
          || nodes.find(n => (n.innerText||'').trim().includes(label));
  if (!el) return 'NOT_FOUND:' + label;
  el.scrollIntoView({block:'center'});
  el.click();
  return 'CLICKED:' + label;
})(%s)
"""


def click_text(drv, label):
    r = js(drv, CLICK_TEXT_JS % json.dumps(label, ensure_ascii=False))
    print('  click', label, '->', r, flush=True)
    return r


def open_page_button(drv, label):
    """页面级按钮（不在弹窗内）"""
    return js(drv, """
    return (function(label){
      const btn = Array.from(document.querySelectorAll('button'))
        .find(n => (n.innerText||'').trim() === label);
      if (!btn) return 'NOT_FOUND:' + label;
      btn.click();
      return 'CLICKED:' + label;
    })(%s)
    """ % json.dumps(label, ensure_ascii=False))


def dialog_text(drv):
    return js(drv, DIALOG_TEXT_JS) or ''


def wait_dialog(drv, timeout=30):
    return wait_until(drv, lambda: bool(dialog_text(drv).strip()), timeout)


def close_dialog(drv, timeout=30):
    js(drv, VIS + """
    if (!__d) return 'NO_DIALOG';
    const btns = Array.from(__d.querySelectorAll('button'));
    const c = btns.find(b => (b.innerText||'').trim() === '取消')
           || btns.find(b => (b.getAttribute('aria-label')||'') === 'Close');
    if (!c) return 'NO_CANCEL';
    c.click();
    return 'CLOSED';
    """)
    return wait_until(drv, lambda: not dialog_text(drv).strip(), timeout)


TAG_SOURCE_STATE_JS = VIS + """
if (!__d) return {found: false, reason: 'no visible dialog'};
const radios = Array.from(__d.querySelectorAll('[role=radio]'));
const group = radios.filter(r => ['两者都要','仅 JSON tags','仅路径解析']
    .includes((r.innerText||'').trim()));
return {
  found: group.length > 0,
  labels: group.map(r => (r.innerText||'').trim()),
  checked: group.filter(r => r.getAttribute('aria-checked') === 'true')
                .map(r => (r.innerText||'').trim()),
  desc: (__d.innerText || '').split('\\n').filter(l => l.includes('手填标签')).slice(0, 2)
};
"""


def tag_source_state(drv):
    return js(drv, TAG_SOURCE_STATE_JS)


PICK_TAG_SOURCE_JS = VIS + """
return (function(label){
  if (!__d) return 'NO_DIALOG';
  const r = Array.from(__d.querySelectorAll('[role=radio]'))
    .find(n => (n.innerText||'').trim() === label);
  if (!r) return 'NOT_FOUND:' + label;
  r.click();
  return 'PICKED:' + label;
})(%s)
"""


def pick_tag_source(drv, label):
    r = js(drv, PICK_TAG_SOURCE_JS % json.dumps(label, ensure_ascii=False))
    print('  tag source ->', r, flush=True)
    time.sleep(0.4)
    st = js(drv, TAG_SOURCE_STATE_JS)
    if not st or st.get('checked') != [label]:
        raise RuntimeError('标签来源未切换成功：%s（状态 %s）'
                           % (r, json.dumps(st, ensure_ascii=False)))
    return st


def set_switch_on(drv, selector):
    return js(drv, VIS + """
    return (function(sel){
      if (!__d) return 'NO_DIALOG';
      const el = __d.querySelector(sel);
      if (!el) return 'NOT_FOUND:' + sel;
      // base-ui Switch 的 id 落在隐藏 input 上（checked 属性可用），根部按钮带 aria-checked
      const root = el.closest('[role=switch]') || el;
      const on = (el.type === 'checkbox' ? el.checked : false)
              || root.getAttribute('aria-checked') === 'true'
              || root.dataset.state === 'checked';
      if (on) return 'ALREADY';
      (el.type === 'checkbox' && el.id ? el : root).click();
      return 'ON';
    })(%s)
    """ % json.dumps(selector))


def set_input(drv, selector, value):
    return js(drv, VIS + """
    return (function(sel, val){
      if (!__d) return 'NO_DIALOG';
      const el = __d.querySelector(sel);
      if (!el) return 'NOT_FOUND:' + sel;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, val);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      return 'SET';
    })(%s, %s)
    """ % (json.dumps(selector), json.dumps(value, ensure_ascii=False)))


def mark_dialog(drv):
    return js(drv, MARK_JS)


def attach_upload_dialog_file(drv):
    mark_dialog(drv)
    inp = drv.find_element(By.CSS_SELECTOR,
                           OPEN_SEL + ' input[type=file]:not([webkitdirectory])')
    inp.send_keys(os.path.join(FIX, '组1', '子目录', '单独.wav'))


def attach_folder(drv):
    mark_dialog(drv)
    inp = drv.find_element(By.CSS_SELECTOR, OPEN_SEL + ' input[webkitdirectory]')
    inp.send_keys(FIX)


def reqlog(drv):
    return js(drv, 'return window.__reqlog || []')


def dump_requests(drv, tag):
    rows = reqlog(drv)
    out = []
    for r in rows:
        if '/api/v1/audios/upload/' in r['url']:
            item = {'tag': tag, 'url': r['url'], 'method': r['method'],
                    'status': r['status']}
            if r['body']:
                try:
                    item['body'] = json.loads(r['body'])
                except Exception:
                    item['body'] = r['body'][:500]
            if r['resp']:
                try:
                    item['resp'] = json.loads(r['resp'])
                except Exception:
                    item['resp'] = r['resp'][:500]
            out.append(item)
    RESULT['requests'].extend(out)
    return out


def merge_bodies(rows, name_hint=None):
    """merge 请求体（可按 payload 内 test_case_config/name 过滤）"""
    res = []
    for r in rows:
        if not r['url'].endswith('/upload/merge') or not isinstance(r.get('body'), dict):
            continue
        body = r['body']
        if name_hint:
            rounds = (body.get('test_case_config') or {}).get('rounds') or []
            names = [a.get('audio_name') for rd in rounds for a in (rd.get('audios') or [])]
            if name_hint not in names:
                continue
        res.append(r)
    return res


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    print('  shot', name, flush=True)
    return path


def set_theme(drv, mode):
    js(drv, "localStorage.setItem('iatp:theme:v1:mode', %s)" % json.dumps(mode))
    js(drv, "document.documentElement.classList.remove('light','dark');"
            "document.documentElement.classList.add(%s);"
            "document.documentElement.style.colorScheme=%s"
            % (json.dumps(mode), json.dumps(mode)))


def fetch_json(drv, path):
    return js(drv, """
    const cb = arguments[arguments.length - 1];
    const token = localStorage.getItem('iatp:auth:token:v1') || '';
    fetch(%s, {headers: token ? {Authorization: 'Bearer ' + token} : {}})
      .then(r => r.text().then(t => cb({status: r.status, body: t})))
      .catch(e => cb({status: 0, body: String(e)}));
    """ % json.dumps(path))


def fetch_json_async(drv, path):
    drv.set_script_timeout(180)
    return drv.execute_async_script("""
    const cb = arguments[arguments.length - 1];
    const token = localStorage.getItem('iatp:auth:token:v1') || '';
    fetch(%s, {headers: token ? {Authorization: 'Bearer ' + token} : {}})
      .then(r => r.text().then(t => cb({status: r.status, body: t})))
      .catch(e => cb({status: 0, body: String(e)}));
    """ % json.dumps(path))


def wait_dialog_closed(drv, timeout=240):
    return wait_until(drv, lambda: not dialog_text(drv).strip(), timeout, 1.0)


def open_upload_dialog(drv):
    open_page_button(drv, '上传音频')
    wait_dialog(drv)
    time.sleep(0.6)


def open_folder_dialog(drv):
    open_page_button(drv, '批量从文件夹导入')
    wait_dialog(drv)
    time.sleep(0.6)


def main():
    drv = make_driver()
    try:
        if not login(drv):
            RESULT['errors'].append('login failed')
            return
        if not goto_audio(drv):
            RESULT['errors'].append('audio page failed')
            return

        # ---------- B.1 标签来源默认「两者都要」+ 关闭重开复位 ----------
        open_upload_dialog(drv)
        set_switch_on(drv, '#upload-gen-case')
        time.sleep(0.8)
        st = tag_source_state(drv)
        RESULT['cases']['upload_default'] = st
        log('B1 upload dialog tag source default', state=st)
        shot(drv, '01_upload_dialog_tag_source_light.png')
        pick_tag_source(drv, '仅路径解析')
        st2 = tag_source_state(drv)
        RESULT['cases']['upload_after_pick'] = st2
        close_dialog(drv)
        open_upload_dialog(drv)
        set_switch_on(drv, '#upload-gen-case')
        time.sleep(0.8)
        st3 = tag_source_state(drv)
        RESULT['cases']['upload_reopen_default'] = st3
        log('B1 reopen default', state=st3)

        # ---------- A.4 上传弹窗单文件：relative_path = 文件名、tag_source=both ----------
        set_input(drv, '#upload-tags', '手填A')
        attach_upload_dialog_file(drv)
        time.sleep(1.0)
        js(drv, 'window.__reqlog = []')
        click_text(drv, '开始上传')
        closed = wait_dialog_closed(drv)
        log('upload(单文件) 提交', closed=closed)
        rows = dump_requests(drv, 'upload-dialog-both')
        regs = [r for r in rows if r['url'].endswith('/register')]
        merges = [r for r in rows if r['url'].endswith('/merge')]
        RESULT['cases']['upload_single'] = {
            'closed': closed,
            'register': regs[0]['body'] if regs else None,
            'merge': merges[0]['body'] if merges else None,
            'merge_resp': merges[0].get('resp') if merges else None,
            'merge_status': merges[0]['status'] if merges else None,
        }
        time.sleep(2.0)

        # ---------- 文件夹导入 A：两者都要 ----------
        open_folder_dialog(drv)
        set_switch_on(drv, '#upload-gen-case')
        st = tag_source_state(drv)
        RESULT['cases']['folder_default'] = st
        log('B5 folder dialog tag source default', state=st)
        shot(drv, '02_folder_dialog_tag_source_light.png')
        set_input(drv, '#upload-tags', '手填A')
        attach_folder(drv)
        time.sleep(1.5)
        js(drv, 'window.__reqlog = []')
        click_text(drv, '开始导入')
        closed = wait_dialog_closed(drv, 300)
        log('folder import (both)', closed=closed)
        rows_both = dump_requests(drv, 'folder-both')
        RESULT['cases']['folder_both'] = {
            'closed': closed,
            'registers': [r['body'] for r in rows_both if r['url'].endswith('/register')],
            'merges': [{'body': r['body'], 'resp': r.get('resp'), 'status': r['status']}
                       for r in rows_both if r['url'].endswith('/merge')],
        }
        time.sleep(3.0)

        # ---------- 文件夹导入 B：仅路径解析 ----------
        open_folder_dialog(drv)
        set_switch_on(drv, '#upload-gen-case')
        set_input(drv, '#upload-tags', '手填A')
        pick_tag_source(drv, '仅路径解析')
        attach_folder(drv)
        time.sleep(1.5)
        js(drv, 'window.__reqlog = []')
        click_text(drv, '开始导入')
        closed = wait_dialog_closed(drv, 300)
        log('folder import (path)', closed=closed)
        rows_path = dump_requests(drv, 'folder-path')
        RESULT['cases']['folder_path'] = {
            'closed': closed,
            'merges': [{'body': r['body'], 'resp': r.get('resp'), 'status': r['status']}
                       for r in rows_path if r['url'].endswith('/merge')],
        }
        time.sleep(3.0)

        # ---------- 文件夹导入 C：仅 JSON tags ----------
        open_folder_dialog(drv)
        set_switch_on(drv, '#upload-gen-case')
        set_input(drv, '#upload-tags', '手填A')
        pick_tag_source(drv, '仅 JSON tags')
        attach_folder(drv)
        time.sleep(1.5)
        js(drv, 'window.__reqlog = []')
        click_text(drv, '开始导入')
        closed = wait_dialog_closed(drv, 300)
        log('folder import (json)', closed=closed)
        rows_json = dump_requests(drv, 'folder-json')
        RESULT['cases']['folder_json'] = {
            'closed': closed,
            'merges': [{'body': r['body'], 'resp': r.get('resp'), 'status': r['status']}
                       for r in rows_json if r['url'].endswith('/merge')],
        }
        time.sleep(3.0)

        # ---------- B.7 音频列表 / 标签筛选 / 用例标签 ----------
        drv.get(BASE + '/audio-import')
        wait_until(drv, lambda: '音频管理' in js(drv, 'return document.body.innerText'), 120)
        time.sleep(4)
        lst = fetch_json_async(drv, '/api/v1/audios?page=1&per_page=50&keyword=甲1')
        try:
            body = json.loads(lst['body'])
            items = body.get('data', {}).get('items', body.get('items', []))
            RESULT['cases']['audio_list_甲1'] = [
                {'id': i.get('id'), 'name': i.get('name'), 'tags': i.get('tags'),
                 'relative_path': i.get('relative_path')} for i in items[:5]]
        except Exception as e:
            RESULT['cases']['audio_list_甲1'] = {'error': str(e), 'raw': lst['body'][:500]}
        log('B2 音频列表行标签(甲1)', rows=RESULT['cases']['audio_list_甲1'])

        tags_resp = fetch_json_async(drv, '/api/v1/audios/tags?page=1&per_page=200')
        try:
            tbody = json.loads(tags_resp['body'])
            titems = tbody.get('data', {}).get('items', tbody.get('items', []))
            names = [t if isinstance(t, str) else (t or {}).get('name') for t in titems]
            RESULT['cases']['tag_facet'] = {
                'has_甲标签': '甲标签' in names,
                'has_乙标签': '乙标签' in names,
                'has_手填A': '手填A' in names,
                'has_子目录': '子目录' in names,
                'total': len(names),
            }
        except Exception as e:
            RESULT['cases']['tag_facet'] = {'error': str(e), 'raw': tags_resp['body'][:500]}
        log('B7 标签筛选源', facet=RESULT['cases']['tag_facet'])

        # 用例标签（按 merge 返回的 test_case_id 逐条核对）
        created = []
        for key in ('folder_both', 'folder_path', 'folder_json', 'upload_single'):
            blk = RESULT['cases'].get(key) or {}
            merges = blk.get('merges') or ([blk] if blk.get('merge') else [])
            for m in merges:
                resp = m.get('resp') or (blk.get('merge_resp') if key == 'upload_single' else None)
                if isinstance(resp, str):
                    try:
                        resp = json.loads(resp)
                    except Exception:
                        resp = None
                if not isinstance(resp, dict):
                    continue
                data = resp.get('data') or resp
                tcid = data.get('test_case_id')
                if tcid:
                    created.append({'run': key, 'test_case_id': tcid,
                                    'audio_id': data.get('audio_id')})
        RESULT['cases']['created_test_cases'] = created
        case_tags = []
        for c in created:
            r = fetch_json_async(drv, '/api/v1/testcases/%s' % c['test_case_id'])
            try:
                d = json.loads(r['body'])
                dd = d.get('data') or d
                case_tags.append({'run': c['run'], 'id': c['test_case_id'],
                                  'status': r['status'], 'name': dd.get('name'),
                                  'tags': dd.get('tags'),
                                  'group_name': dd.get('group_name')})
            except Exception as e:
                case_tags.append({'run': c['run'], 'id': c['test_case_id'],
                                  'error': str(e), 'raw': r['body'][:300]})
        RESULT['cases']['test_case_tags'] = case_tags
        log('B5 用例标签', rows=case_tags)

        shot(drv, '03_audio_list_light.png')

        # ---------- B.8 空态：不选文件直接提交 ----------
        open_upload_dialog(drv)
        click_text(drv, '开始上传')
        time.sleep(1.2)
        toast = js(drv, """
        const t = Array.from(document.querySelectorAll('[data-sonner-toast],li'))
          .map(n => (n.innerText||'').trim()).filter(Boolean).join(' | ');
        return t;
        """)
        RESULT['cases']['empty_submit_toast'] = toast
        log('B8 空态提交提示', toast=toast)
        close_dialog(drv)

        # ---------- 深色截图 ----------
        set_theme(drv, 'dark')
        time.sleep(1.0)
        open_upload_dialog(drv)
        set_switch_on(drv, '#upload-gen-case')
        time.sleep(0.8)
        RESULT['cases']['upload_dark'] = tag_source_state(drv)
        shot(drv, '04_upload_dialog_tag_source_dark.png')
        close_dialog(drv)
        open_folder_dialog(drv)
        set_switch_on(drv, '#upload-gen-case')
        time.sleep(0.8)
        shot(drv, '05_folder_dialog_tag_source_dark.png')
        close_dialog(drv)
        set_theme(drv, 'light')
        time.sleep(0.5)

        # ---------- Network 证据图（页内 fetch 打点捕获的请求体） ----------
        evidence = []
        for r in RESULT['requests']:
            if r['url'].endswith('/register') and 'body' in r:
                evidence.append({'接口': 'POST /audios/upload/register',
                                 '状态': r['status'],
                                 'files[0]': (r['body'].get('files') or [{}])[0]})
        for r in RESULT['requests']:
            if r['url'].endswith('/merge') and isinstance(r.get('body'), dict):
                b = r['body']
                evidence.append({'接口': 'POST /audios/upload/merge',
                                 '状态': r['status'],
                                 'tags': b.get('tags'),
                                 'tag_source': b.get('tag_source'),
                                 'rounds.audio': [a.get('audio_name')
                                                  for rd in (b.get('test_case_config', {})
                                                             .get('rounds') or [])
                                                  for a in (rd.get('audios') or [])]})
        js(drv, """
        (function(rows){
          const old = document.getElementById('__ev');
          if (old) old.remove();
          const box = document.createElement('div');
          box.id = '__ev';
          box.style.cssText = 'position:fixed;inset:0;z-index:99999;background:#0b1020;' +
            'color:#e6edf3;font:12px/1.55 Consolas,monospace;padding:18px;overflow:auto;white-space:pre';
          box.textContent = rows;
          document.body.appendChild(box);
        })(%s)
        """ % json.dumps(json.dumps(evidence, ensure_ascii=False, indent=1),
                         ensure_ascii=False))
        time.sleep(0.6)
        shot(drv, '06_network_evidence.png')
        RESULT['cases']['network_evidence'] = evidence

        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as fh:
            json.dump(RESULT, fh, ensure_ascii=False, indent=2)
        print('DONE', flush=True)
    except Exception as e:
        RESULT['errors'].append('%s: %s' % (type(e).__name__, e))
        try:
            shot(drv, '99_error.png')
        except Exception:
            pass
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as fh:
            json.dump(RESULT, fh, ensure_ascii=False, indent=2)
        raise
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
