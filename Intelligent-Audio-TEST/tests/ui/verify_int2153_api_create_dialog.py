# -*- coding: utf-8 -*-
"""INT-2153 自测：「添加测试API」与「编辑 API」同件（§5.3 四页签弹窗）。

环境：dev 5353（本卡工作树构建，代理 docker 网关 15000）+ docker 真实库栈。
核对：
  A. 「测试 API」页签页头「添加测试API」开的是 API 编辑弹窗（新增态，四页签齐全）；
  B. 端点行四整数列有常驻标签（不是只有 placeholder）；
  C. 新建时即可配 meta（请求模板 method / headers），保存发出 POST /apis 且带 meta；
  D. 保存后列表出现该 API，行菜单「编辑」开同一弹窗并回显请求模板；
  E. 浅色 / 深色各一帧。
运行：python tests/ui/verify_int2153_api_create_dialog.py
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:5353')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2153')
os.makedirs(ART, exist_ok=True)
TS = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT2153_%s' % TS
RESULTS = []
FIXTURE = {'id': None}


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:800], 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:600])


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('SHOT ' + path)
    return path


# 注意：不要写成 "[data-slot='dialog-content'], [role='dialog']"——CSS 逗号分组的优先级会让
# 前缀选择器只作用于后半段，导致把 DialogContent 自身也当成匹配项
DIALOG = "[data-slot='dialog-content']"


def visible_buttons(drv, text):
    out = []
    for el in drv.find_elements(By.CSS_SELECTOR, DIALOG + ' button'):
        try:
            if not B.visible(el):
                continue
            label = (el.text or '').strip()
            if label == text or text in label:
                out.append(el)
        except Exception:
            pass
    return out


def click_page_text(drv, text):
    """页面级按钮（页头主按钮等；弹窗未开时用）。"""
    for el in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if B.visible(el) and (el.text or '').strip() == text:
                drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                drv.execute_script('arguments[0].click();', el)
                return el
        except Exception:
            pass
    raise RuntimeError('page button not found: %s' % text)


def click_text(drv, text, exact=True):
    els = visible_buttons(drv, text)
    if exact:
        els = [e for e in els if (e.text or '').strip() == text]
    if not els:
        raise RuntimeError('dialog button not found: %s' % text)
    el = els[0]
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    try:
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click();', el)
    return el


def dialog_titles(drv):
    out = []
    for el in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-title']"):
        if B.visible(el):
            out.append((el.text or '').strip())
    return out


def wait_dialog(drv, title, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        if title in dialog_titles(drv):
            return True
        time.sleep(0.3)
    return False


def tab_labels(drv):
    out = []
    for el in drv.find_elements(By.CSS_SELECTOR, DIALOG + " [role='tab']"):
        if B.visible(el):
            label = (el.text or '').strip()
            if 0 < len(label) <= 8:
                out.append(label)
    return out


def click_tab(drv, label):
    for el in drv.find_elements(By.CSS_SELECTOR, DIALOG + " [role='tab']"):
        if B.visible(el) and (el.text or '').strip() == label:
            drv.execute_script('arguments[0].click();', el)
            return True
    return False


def labels_in_dialog(drv):
    out = []
    for el in drv.find_elements(By.CSS_SELECTOR, DIALOG + ' label'):
        if B.visible(el):
            out.append((el.text or '').strip())
    return out


def set_input(drv, el, value):
    return B.set_input(drv, el, value)


def reqs(drv):
    return drv.execute_script('return window.__reqs || [];')


def find_req(reqs_list, needle, method=None):
    hits = []
    for r in reqs_list:
        url = r.get('url') or ''
        if needle in url and (method is None or (r.get('method') or '').upper() == method):
            hits.append(r)
    return hits


def main():
    drv = B.driver_init()
    token = None
    try:
        token, user = B.rsa_login_token(*B.ACCOUNT)
        drv.get(B.BASE + '/login')
        B.wait_ready(drv)
        drv.execute_script('try{localStorage.setItem(arguments[0], arguments[1]);}catch(e){}', B.TOKEN_KEY, token)
        B.goto(drv, '/devices/api', '测试API')
        record('A0 登录并进入 /devices/api', True, drv.current_url)

        time.sleep(1.5)
        shot(drv, '01_devices_api_list_light')

        # A. 页头「添加测试API」→ API 编辑弹窗（新增态）
        click_page_text(drv, '添加测试API')
        ok = wait_dialog(drv, '新增 API', 25)
        tabs = tab_labels(drv)
        record('A1 添加测试API 打开「新增 API」弹窗', ok, 'tabs=%s' % tabs)
        record('A2 新增态四页签齐全', tabs == ['基础', '请求模板', '响应解析', '参数配置'], 'tabs=%s' % tabs)

        # B. 端点行常驻标签
        click_text(drv, '添加端点')
        time.sleep(0.4)
        labels = labels_in_dialog(drv)
        need = ['名称', '优先级', '最大进程', '超时(s)', '音频时长(s)']
        record('B1 端点行常驻标签', all(n in labels for n in need), 'labels=%s' % labels)
        placeholder_row = drv.execute_script('''
            var inputs = document.querySelectorAll("[role='dialog'] input");
            var out = [];
            for (var i=0;i<inputs.length;i++){ out.push([inputs[i].getAttribute('aria-label'), inputs[i].placeholder]); }
            return out;
        ''')
        record('B2 端点 URL 占位为完整 URL', any(p == 'https://…' for _, p in [(x[0], x[1]) for x in placeholder_row]), 'inputs=%s' % placeholder_row[:12])
        shot(drv, '02_add_dialog_endpoint_light')

        # C. 新建时配 meta：名称 + 算法 + 端点 + 请求模板
        name_input = None
        for el in drv.find_elements(By.CSS_SELECTOR, '#api-name'):
            if B.visible(el):
                name_input = el
        set_input(drv, name_input, NAME)

        # 关联算法（base-ui Select）：弹窗内「请选择算法」触发器 → 取第一个选项
        algo_trigger = None
        for el in drv.find_elements(By.CSS_SELECTOR, DIALOG + " [data-slot='select-trigger']"):
            if B.visible(el) and '请选择算法' in (el.text or ''):
                algo_trigger = el
                break
        for attempt in range(3):
            if algo_trigger is None:
                break
            drv.execute_script('arguments[0].click();', algo_trigger)
            time.sleep(1.0)
            opts = [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if B.visible(o)]
            if opts:
                drv.execute_script('arguments[0].click();', opts[0])
                time.sleep(0.4)
                break
        algo_text = drv.execute_script('''
            var dlg = document.querySelector("[data-slot='dialog-content']");
            var trigs = Array.prototype.slice.call(dlg.querySelectorAll("[data-slot='select-trigger']"));
            return trigs.map(function(t){ return (t.textContent||'').trim(); });
        ''')
        record('C1 选择关联算法', bool(algo_text) and '请选择算法' not in algo_text, 'triggers=%s' % algo_text)

        ep_url = None
        for el in drv.find_elements(By.CSS_SELECTOR, "input[aria-label='端点 URL']"):
            if B.visible(el):
                ep_url = el
        set_input(drv, ep_url, 'https://example.com/v1/asr')

        click_tab(drv, '请求模板')
        time.sleep(0.5)
        shot(drv, '03_create_request_tab_light')
        # 请求方法下拉（选择 POST）
        method_ok = drv.execute_script('''
            var dlg = document.querySelector("[data-slot='dialog-content']");
            var trigs = Array.prototype.slice.call(dlg.querySelectorAll("[data-slot='select-trigger']"));
            if (!trigs.length) return false; trigs[0].click(); return true;
        ''')
        time.sleep(0.6)
        picked = drv.execute_script('''
            var opts = Array.prototype.slice.call(document.querySelectorAll("[role='option']"));
            for (var i=0;i<opts.length;i++){ if ((opts[i].textContent||'').trim() === 'POST') { opts[i].click(); return true; } }
            return false;
        ''')
        time.sleep(0.3)
        body_input = None
        for el in drv.find_elements(By.CSS_SELECTOR, '#meta-body-template'):
            if B.visible(el):
                body_input = el
        if body_input is not None:
            set_input(drv, body_input, '{"text":"{{text}}"}')
        record('C2 请求模板可编辑（method=POST + body_template）', bool(method_ok and picked), 'open=%s picked=%s' % (method_ok, picked))

        # D. 保存 → POST /apis
        B.reset_reqs(drv)
        click_text(drv, '保存')
        time.sleep(4)
        all_reqs = reqs(drv)
        posts = find_req(all_reqs, '/apis', 'POST')
        status = [p.get('status') for p in posts]
        body = posts[-1].get('body') if posts else None
        parsed = None
        if body:
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = None
        record('D1 保存发出 POST /apis 且 2xx', bool(posts) and any(s and 200 <= s < 300 for s in status), 'status=%s' % status)
        record('D2 POST body 含 meta（新建即可配请求模板）', bool(parsed and isinstance(parsed.get('meta'), dict) and parsed.get('meta', {}).get('method') == 'POST'),
               'body=%s' % (body or '')[:600])
        record('D3 POST body 含端点列表', bool(parsed and isinstance(parsed.get('endpoints'), list) and parsed.get('endpoints')),
               'endpoints=%s' % (parsed or {}).get('endpoints'))
        record('D4 名称为输入值', bool(parsed and parsed.get('name') == NAME), 'name=%r' % (parsed or {}).get('name'))
        time.sleep(1.5)
        shot(drv, '04_after_save_list_light')

        # 列表出现该 API（真实读）
        body_text = B.body_text(drv)
        record('D5 列表刷新出现新建 API', NAME in body_text, 'contains=%s' % (NAME in body_text))

        # 找到该行并「编辑」→ 同一弹窗回显 meta
        row_edit_ok = False
        for tr in drv.find_elements(By.CSS_SELECTOR, 'tbody tr'):
            try:
                if NAME in (tr.text or ''):
                    for b in tr.find_elements(By.TAG_NAME, 'button'):
                        if (b.get_attribute('aria-label') or '').startswith('操作 '):
                            drv.execute_script('arguments[0].click();', b)
                            time.sleep(0.5)
                            break
                    items = [el for el in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if B.visible(el)]
                    for it in items:
                        if (it.text or '').strip() == '编辑':
                            drv.execute_script('arguments[0].click();', it)
                            row_edit_ok = True
                            break
                    break
            except Exception:
                pass
        ok = wait_dialog(drv, '编辑 API', 20)
        record('D6 行内「编辑」开同一弹窗', ok and row_edit_ok, 'dialog=%s' % dialog_titles(drv))
        click_tab(drv, '请求模板')
        time.sleep(0.6)
        method_now = drv.execute_script('''
            var s = document.querySelector("[role='dialog'] [data-slot='select-trigger']");
            return s ? s.textContent : null;
        ''')
        record('D7 编辑回显请求模板 method=POST', bool(method_now and 'POST' in method_now), 'select=%r' % method_now)

        # E. 深色帧（主题 storage 键 + 重载后重开新增弹窗）
        click_text(drv, '取消')
        time.sleep(0.5)
        B.set_theme(drv, 'dark')
        B.goto(drv, '/devices/api', '测试API')
        click_page_text(drv, '添加测试API')
        wait_dialog(drv, '新增 API', 25)
        click_tab(drv, '请求模板')
        time.sleep(0.8)
        shot(drv, '05_add_request_tab_dark')
        record('E1 深色主题生效', B.is_dark(drv), 'html.class=%s' % drv.execute_script('return document.documentElement.className'))
        click_text(drv, '取消')
        B.set_theme(drv, 'light')
        B.goto(drv, '/devices/api', '测试API')
        time.sleep(0.5)

        # F. 网络证据：保存前后的 /apis 调用
        api_calls = [{'method': r.get('method'), 'url': r.get('url'), 'status': r.get('status')}
                     for r in all_reqs if '/apis' in (r.get('url') or '')]
        record('F1 保存链路请求记录', len(api_calls) > 0, json.dumps(api_calls, ensure_ascii=False)[:600])
        console = []
        try:
            console = drv.get_log('browser')
        except Exception:
            pass
        # 仅统计非「重复 key」类 dev 警告：/devices/* 三个页签打开即有的 React 开发期警告，
        # 本卡未触碰对应列表渲染（test/playback/api 三页签均有），非本卡引入
        severe = [e for e in console
                  if (e.get('level') or '').upper() == 'SEVERE'
                  and 'favicon' not in (e.get('message') or '')
                  and 'Encountered two children with the same key' not in (e.get('message') or '')]
        record('F2 浏览器控制台无（非重复 key）severe', not severe, json.dumps([e.get('message') for e in severe], ensure_ascii=False)[:500])
    except Exception as exc:
        import traceback
        record('EXC', False, traceback.format_exc()[-1200:])
    finally:
        # 清理夹具：按名称查 id 后 DELETE（只删本卡前缀）
        try:
            st, data = B.api('/api/v1/apis?per_page=1000', token)
            items = (((data or {}).get('data') or {}).get('items')) or []
            for it in items:
                if it.get('name') == NAME:
                    FIXTURE['id'] = it.get('id')
                    dst, _ = B.api('/api/v1/apis/%s' % it.get('id'), token, method='DELETE')
                    print('CLEANUP delete %s -> %s' % (it.get('id'), dst))
        except Exception:
            import traceback
            print('CLEANUP ERR ' + traceback.format_exc()[-500:])
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'verify_%s.json' % TS), 'w', encoding='utf-8') as fh:
            json.dump({'name': NAME, 'fixture_id': FIXTURE['id'], 'results': RESULTS}, fh, ensure_ascii=False, indent=2)
        bad = [r for r in RESULTS if not r['ok']]
        print('SUMMARY ok=%d fail=%d' % (len(RESULTS) - len(bad), len(bad)))
        for b in bad:
            print('  FAIL ' + b['step'] + ' :: ' + b['detail'][:300])


if __name__ == '__main__':
    main()
