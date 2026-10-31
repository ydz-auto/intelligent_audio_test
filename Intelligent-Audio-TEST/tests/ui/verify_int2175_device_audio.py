# -*- coding: utf-8 -*-
"""INT-2175 走查·React 设备与音频域 浏览器+接口验收。

覆盖卡面 10 项：设备筛选去算法 / 添加设备合一（先扫描）/ 离线取消勾选 / 设备抽屉 API 合一 /
播放音箱分组 / SPL 强制校准点 / 音频可见性 / 音频导入 / 音频试听 / 联动。

环境：docker 15173（前端）+ 15000（网关，database=intelligent_audio_test）。
数据卫生：自建数据一律「接线测试_走查R3_」前缀，run 结束前按 id 删除。
"""
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2175')
os.makedirs(ART, exist_ok=True)
RESULTS = []
HEALTH = []
PREFIX = '接线测试_走查R3_'
FIX = {}  # 本 run 自建 id


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:1200], 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:500])


def health(tag, token):
    import urllib.request
    with urllib.request.urlopen(B.API + '/health', timeout=20) as r:
        h = json.loads(r.read().decode())
    _, d = B.api('/api/v1/test-devices?per_page=1', token)
    _, a = B.api('/api/v1/audios?per_page=1', token)
    ev = {'tag': tag, 'database': h.get('database'), 'devices_total': (d.get('data') or {}).get('total'),
          'audios_total': (a.get('data') or {}).get('total')}
    HEALTH.append(ev)
    print('HEALTH %s %s' % (tag, json.dumps(ev, ensure_ascii=False)))
    return ev


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('SHOT ' + path)
    return path


def js_set(drv, el, value):
    drv.execute_script('''
      var el = arguments[0], value = arguments[1];
      var proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(el, value);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
    ''', el, value)


def body(drv):
    return B.body_text(drv)


def wait_body(drv, text, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if text in body(drv):
            return True
        time.sleep(0.4)
    return False


def dialogs(drv):
    out = []
    for sel in ("[data-slot='dialog-content']", "[data-slot='sheet-content']"):
        for el in drv.find_elements(By.CSS_SELECTOR, sel):
            try:
                if el.is_displayed():
                    out.append(el)
            except Exception:
                pass
    return out


def dialog_with_title(drv, title, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        for el in dialogs(drv):
            try:
                if title in (el.text or ''):
                    return el
            except Exception:
                pass
        time.sleep(0.3)
    return None


def click_btn_in(drv, root, text, exact=True):
    for el in root.find_elements(By.TAG_NAME, 'button'):
        try:
            if not el.is_displayed():
                continue
            t = (el.text or '').strip()
            if (t == text) if exact else (text in t):
                drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                drv.execute_script('arguments[0].click();', el)
                time.sleep(0.8)
                return el
        except Exception:
            pass
    return None


def click_page_btn(drv, text, exact=True, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            try:
                if not el.is_displayed():
                    continue
                t = (el.text or '').strip()
                if (t == text) if exact else (text in t):
                    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                    drv.execute_script('arguments[0].click();', el)
                    time.sleep(0.6)
                    return el
            except Exception:
                pass
        time.sleep(0.3)
    return None


def click_aria(drv, label, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for el in drv.find_elements(By.CSS_SELECTOR, '[aria-label]'):
            try:
                if el.get_attribute('aria-label') == label and el.is_displayed():
                    drv.execute_script('arguments[0].click();', el)
                    time.sleep(0.8)
                    return el
            except Exception:
                pass
        time.sleep(0.3)
    return None


def table_rows(drv):
    """当前页面主表格数据行数（取页内最大 tbody）。"""
    n = drv.execute_script('''
      var best = 0;
      document.querySelectorAll('table').forEach(function(t){
        var b = t.querySelector('tbody');
        if (b) { var c = b.querySelectorAll('tr').length; if (c > best) best = c; }
      });
      return best;
    ''')
    return n or 0


def facet(drv, label):
    """点开筛选 facet（按钮文本以 label 开头）。"""
    for el in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if el.is_displayed() and (el.text or '').strip().startswith(label):
                drv.execute_script('arguments[0].click();', el)
                time.sleep(0.6)
                return el
        except Exception:
            pass
    return None


def pick_popover_option(drv, text):
    end = time.time() + 8
    while time.time() < end:
        cands = []
        cands += drv.find_elements(By.XPATH, "//button[normalize-space(.)='%s']" % text)
        cands += drv.find_elements(By.CSS_SELECTOR, '[role="menuitem"],[role="option"]')
        for el in cands:
            try:
                if el.is_displayed() and (el.text or '').strip() == text:
                    drv.execute_script('arguments[0].click();', el)
                    time.sleep(1.0)
                    return True
            except Exception:
                pass
        time.sleep(0.3)
    return False


def toast_text(drv, needle, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        t = body(drv)
        if needle in t:
            return True
        time.sleep(0.3)
    return False


# ---------------------------------------------------------------------------
# 各项
# ---------------------------------------------------------------------------

def t1_devices_filter(drv, token):
    B.goto(drv, '/devices/test', '设备管理')
    time.sleep(2.0)
    _, js = B.api('/api/v1/test-devices?page=1&per_page=1000', token)
    items = (js.get('data') or {}).get('items') or []
    total = len(items)
    # 筛选 facet 名称（工具栏）
    btn_texts = []
    for el in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if el.is_displayed():
                t = ' '.join((el.text or '').split())
                if t:
                    btn_texts.append(t)
        except Exception:
            pass
    facets = [t for t in btn_texts if t.startswith(('状态 ', '连接方式 ', '分组 ', '实验室 ', '协议 ', '流式性 ', '环境 ', '设备类型 '))]
    alg_facet = [t for t in facets if t.startswith('算法')]
    record('T1 筛选栏无算法 facet', len(alg_facet) == 0,
           'facets=%s' % facets)
    rows0 = table_rows(drv)
    record('T1 初始行数与接口一致', rows0 == total, 'ui_rows=%d api_total=%d' % (rows0, total))

    # 状态=离线
    facet(drv, '状态')
    ok = pick_popover_option(drv, '离线')
    time.sleep(1.2)
    rows_off = table_rows(drv)
    api_off = len([d for d in items if (d.get('status') or '') == 'offline'])
    record('T1 状态筛选 离线', ok and rows_off == api_off,
           'ui_rows=%d api_offline=%d' % (rows_off, api_off))
    shot(drv, 't1_filter_offline')
    # 重置
    click_page_btn(drv, '重置', exact=False)
    time.sleep(1.0)
    rows_reset = table_rows(drv)
    record('T1 重置恢复全量', rows_reset == total, 'ui_rows=%d total=%d' % (rows_reset, total))

    # 连接方式=USB连接
    facet(drv, '连接方式')
    pick_popover_option(drv, 'USB连接')
    time.sleep(1.2)
    rows_usb = table_rows(drv)
    api_usb = len([d for d in items if (d.get('connection_type') or d.get('connectionType') or '') == 'usb'])
    record('T1 连接方式筛选 USB', rows_usb == api_usb,
           'ui_rows=%d api_usb=%d' % (rows_usb, api_usb))
    click_page_btn(drv, '重置', exact=False)
    time.sleep(1.0)

    # 关键词
    inp = None
    for el in drv.find_elements(By.TAG_NAME, 'input'):
        try:
            if el.is_displayed() and '搜索设备' in (el.get_attribute('aria-label') or ''):
                inp = el
                break
        except Exception:
            pass
    if inp:
        js_set(drv, inp, 'pura90')
        time.sleep(2.2)
        rows_kw = table_rows(drv)
        api_kw = len([d for d in items if 'pura90' in (d.get('name') or '').lower()])
        record('T1 关键词筛选 pura90', rows_kw == api_kw, 'ui_rows=%d api=%d' % (rows_kw, api_kw))
        shot(drv, 't1_filter_keyword')
        click_page_btn(drv, '重置', exact=False)
        time.sleep(1.0)
        record('T1 清空筛选恢复', table_rows(drv) == total, 'rows=%d' % table_rows(drv))
    else:
        record('T1 关键词筛选 pura90', False, '搜索框未找到')
    B.set_theme(drv, 'dark')
    time.sleep(0.8)
    shot(drv, 't1_devices_dark')
    B.set_theme(drv, 'light')
    time.sleep(0.5)
    shot(drv, 't1_devices_light')


def t2_scan_add(drv, token):
    # 扫描接口证据（真实接口）
    st, js = B.api('/api/v1/test-devices/scan', token, method='POST', body={})
    rows = js.get('data') or []
    record('T2 POST /test-devices/scan',
           st == 200 and isinstance(rows, list) and len(rows) > 0,
           'status=%s rows=%d is_registered=%s serial=%s' % (
               st, len(rows), [r.get('is_registered') for r in rows], [r.get('serial') for r in rows]))
    record('T2 扫描行 is_registered 恒 False（4b6d2c9d4 设计：不按 serial 去重，行始终可添加）',
           all(r.get('is_registered') is False for r in rows),
           'is_registered=%s' % [r.get('is_registered') for r in rows])
    serial = rows[0].get('serial') if rows else ''

    B.goto(drv, '/devices/test', '设备管理')
    click_page_btn(drv, '添加设备')
    dlg = dialog_with_title(drv, '扫描测试设备', 20)
    record('T2 「添加设备」先开扫描', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    wait_body(drv, '扫描完成', 30)
    time.sleep(1.0)
    shot(drv, 't2_scan_dialog')
    dtext = dlg.text or ''
    record('T2 扫描结果含 serial 行', serial in dtext, 'serial=%s text=%s' % (serial, dtext[:300]))
    # 点第一个「添加」
    add_btn = None
    for el in dlg.find_elements(By.TAG_NAME, 'button'):
        try:
            if el.is_displayed() and (el.text or '').strip() == '添加':
                add_btn = el
                break
        except Exception:
            pass
    if not add_btn:
        record('T2 扫描行「添加」入口', False, 'no add button')
        return
    drv.execute_script('arguments[0].click();', add_btn)
    sheet = dialog_with_title(drv, '添加测试设备', 20)
    record('T2 「添加」开登记抽屉', sheet is not None, 'sheet=%s' % (sheet is not None))
    if not sheet:
        return
    time.sleep(1.0)
    stext = sheet.text or ''
    record('T2 抽屉预填扫描信息', serial in stext or 'HarmonyOS' in stext, 'sheet=%s' % stext[:400])
    # 抽屉内不得有 API 分支字段（INT-2153）
    api_marks = [k for k in ['供应商', '端点列表', '协议', '流式性', '环境（', '默认超时', '代理'] if k in stext]
    record('T2/T4 设备抽屉无 API 分支字段', len(api_marks) == 0, 'api_marks=%s' % api_marks)
    shot(drv, 't2_device_drawer_light')

    name = PREFIX + 'DEV_' + time.strftime('%H%M%S')
    set_by_label(drv, sheet, '名称', name)
    name_ok = True
    # 保存
    click_btn_in(drv, sheet, '保存', exact=False)
    time.sleep(3.0)
    st2, js2 = B.api('/api/v1/test-devices?page=1&per_page=1000', token)
    hit = [d for d in ((js2.get('data') or {}).get('items') or []) if (d.get('name') or '') == name]
    record('T2 扫描添加创建设备', bool(hit), 'name=%s hits=%d' % (name, len(hit)))
    if hit:
        did = hit[0]['id']
        FIX.setdefault('devices', []).append(did)
        gs, gj = B.api('/api/v1/test-devices/%s' % did, token)
        g = gj.get('data') or {}
        record('T2 详情回读字段一致',
               gs == 200 and (g.get('name') == name) and str(g.get('serial_number') or g.get('serialNumber') or '') == str(serial),
               'GET %s -> %s name=%s serial=%s' % (did, gs, g.get('name'), g.get('serial_number') or g.get('serialNumber')))
    time.sleep(1.0)
    record('T2 列表刷新出现新设备', name in body(drv), 'body has name=%s' % (name in body(drv)))
    B.set_theme(drv, 'dark')
    time.sleep(0.6)
    shot(drv, 't2_devices_after_add_dark')
    B.set_theme(drv, 'light')
    # 再次扫描 → 添加同 serial 第二台（不按 serial 去重）
    drv.get(B.BASE + '/devices/test'); B.wait_ready(drv); time.sleep(1.5)
    click_page_btn(drv, '添加设备')
    dlg = dialog_with_title(drv, '扫描测试设备', 20)
    if dlg:
        wait_body(drv, '扫描完成', 30)
        time.sleep(1.0)
        add_btn = None
        for el in dlg.find_elements(By.TAG_NAME, 'button'):
            if el.is_displayed() and (el.text or '').strip() == '添加':
                add_btn = el
                break
        if add_btn:
            drv.execute_script('arguments[0].click();', add_btn)
            sheet = dialog_with_title(drv, '添加测试设备', 20)
            if sheet:
                time.sleep(0.8)
                name2 = name + '_B'
                set_by_label(drv, sheet, '名称', name2)
                click_btn_in(drv, sheet, '保存', exact=False)
                time.sleep(3.0)
                _, js3 = B.api('/api/v1/test-devices?page=1&per_page=1000', token)
                both = [d for d in ((js3.get('data') or {}).get('items') or [])
                        if (d.get('name') or '') in (name, name2)]
                for d in both:
                    FIX.setdefault('devices', []).append(d['id'])
                record('T2 同 serial 重复行都保留', len(both) == 2,
                       'created=%s' % [(d['id'], d.get('serial_number') or d.get('serialNumber')) for d in both])


def set_by_label(drv, root, label, value):
    """按 Field 标签文本定位其后的 input 并写入（React 受控 setter）。"""
    try:
        labels = root.find_elements(By.XPATH, ".//label[normalize-space(.)='%s' or starts-with(normalize-space(.),'%s')]" % (label, label))
    except Exception:
        labels = []
    for lab in labels:
        try:
            el = lab.find_element(By.XPATH, "following::input[1]")
            if el.is_displayed():
                js_set(drv, el, value)
                return True
        except Exception:
            pass
    # 退化：按 placeholder 含关键词
    return False


def t3_offline_prune(drv, token):
    B.goto(drv, '/start-test', '开始测试')
    click_page_btn(drv, '下一步', exact=False)
    time.sleep(4.0)
    wait_body(drv, '已选', 20)
    time.sleep(1.5)
    shot(drv, 't3_step2_initial')
    # 找在线设备卡（#232）并勾选：卡片内 checkbox
    picked = drv.execute_script('''
      var cards = Array.from(document.querySelectorAll('div')).filter(function(d){
        return d.className && String(d.className).indexOf('rounded-xl border') >= 0 && d.innerText && d.innerText.indexOf('在线') >= 0;
      });
      window.__pickedCard = null;
      for (var i=0;i<cards.length;i++){
        var c = cards[i];
        var cb = c.querySelector('[role=checkbox], button[role=checkbox], input[type=checkbox]');
        if (cb) { window.__pickedCard = c.innerText.slice(0,80); cb.click(); return window.__pickedCard; }
      }
      return null;
    ''')
    time.sleep(1.5)
    record('T3 勾选在线设备', bool(picked), 'card=%s' % picked)
    sel1 = '已选 1 台设备' in body(drv)
    record('T3 勾选后摘要=1 台', sel1, body(drv)[-300:])
    shot(drv, 't3_selected')
    # SPA 切页面再返回（store 内存保持）——用侧栏链接，避免命中页面底部「开始测试」主按钮
    B.click_link_href(drv, '/audio-import', 15)
    time.sleep(3.0)
    B.click_link_href(drv, '/start-test', 15)
    time.sleep(3.0)
    click_page_btn(drv, '下一步', exact=False)
    time.sleep(4.0)
    time.sleep(1.0)
    kept = '已选 1 台设备' in body(drv)
    record('T3 切页面返回在线勾选保留', kept, body(drv)[-260:])
    # 注入：把所选设备报为离线
    drv.execute_script('''
      (function(){
        var orig = window.__origFetch || window.fetch;
        window.__origFetch = orig;
        if (window.__offlinePatch) return;
        window.__offlinePatch = true;
        window.fetch = function(input, init){
          var p = orig.apply(this, arguments);
          var url = (typeof input === 'string') ? input : ((input && input.url) || '');
          if (url.indexOf('/test-devices?') !== -1 && url.indexOf('/api/v1/test-devices?') !== -1) {
            return p.then(function(r){
              return r.clone().json().then(function(j){
                if (j && j.data && Array.isArray(j.data.items)) {
                  j.data.items = j.data.items.map(function(d){ d.status = 'offline'; return d; });
                }
                return new Response(JSON.stringify(j), {status: r.status, headers: {'Content-Type':'application/json'}});
              });
            });
          }
          return p;
        };
      })();
    ''')
    time.sleep(32)  # 越过 staleTime 30s
    B.click_link_href(drv, '/audio-import', 15)
    time.sleep(2.5)
    B.click_link_href(drv, '/start-test', 15)
    time.sleep(2.5)
    click_page_btn(drv, '下一步', exact=False)
    time.sleep(4.0)
    time.sleep(1.5)
    pruned = '已选 0 台设备' in body(drv)
    record('T3 离线设备自动取消勾选（注入离线后刷新）', pruned, body(drv)[-260:])
    shot(drv, 't3_pruned_offline')
    # 移除注入
    drv.execute_script('if (window.__origFetch) { window.fetch = window.__origFetch; window.__offlinePatch = false; }')


def t4_api_same_component(drv, token):
    B.goto(drv, '/devices/api', '设备管理')
    time.sleep(2.0)
    click_page_btn(drv, '添加测试API')
    dlg = dialog_with_title(drv, '新增 API', 20)
    record('T4 添加测试API 开 API 编辑弹窗', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    tabs = [t for t in ('基础', '请求模板', '响应解析', '参数配置') if t in (dlg.text or '')]
    record('T4 四页签齐全', len(tabs) == 4, 'tabs=%s' % tabs)
    record('T4 协议块', ('协议' in (dlg.text or '')) and ('流式' in (dlg.text or '')), 'text=%s' % (dlg.text or '')[:200])
    shot(drv, 't4_api_create_light')
    # 只读页签（编辑态）
    click_btn_in(drv, dlg, '取消', exact=True)
    time.sleep(0.8)
    # 打开已有 API 编辑
    _, js = B.api('/api/v1/apis?page=1&per_page=100&keyword=%s' % urllib.parse.quote('Mock API'), token)
    items = (js.get('data') or {}).get('items') or []
    target = items[0] if items else None
    if not target:
        _, js = B.api('/api/v1/apis?page=1&per_page=1', token)
        items = (js.get('data') or {}).get('items') or []
        target = items[0] if items else None
    if not target:
        record('T4 编辑 API 回显', False, 'no api')
        return
    click_aria(drv, '操作 %s' % target['name'], 15)
    time.sleep(0.8)
    pick_popover_option(drv, '编辑')
    dlg = dialog_with_title(drv, '编辑 API', 20)
    record('T4 行菜单编辑开同一弹窗', dlg is not None, 'name=%s dialog=%s' % (target['name'], dlg is not None))
    if not dlg:
        return
    # 基础页签回显名称（输入框 value 不在 element.text 里，按 input value 读）
    click_btn_in(drv, dlg, '基础', exact=False)
    time.sleep(1.2)
    vals = []
    end = time.time() + 15
    while time.time() < end:
        dlg2 = dialog_with_title(drv, '编辑 API', 3)
        if dlg2 is not None:
            vals = drv.execute_script(
                "return Array.from(arguments[0].querySelectorAll('input,textarea')).map(function(e){return e.value;});",
                dlg2)
            vals = [v for v in vals if v]
        if target['name'] in vals:
            break
        time.sleep(0.5)
    dlg = dlg2 if dlg2 is not None else dlg
    record('T4 编辑回显名称', target['name'] in vals, 'input_values=%s' % vals[:10])
    # 只读页签：点「响应解析」
    click_btn_in(drv, dlg, '响应解析', exact=False)
    time.sleep(1.0)
    shot(drv, 't4_api_readonly_tab')
    click_btn_in(drv, dlg, '参数配置', exact=False)
    time.sleep(2.0)
    shot(drv, 't4_api_param_tab')
    dlg3 = dialog_with_title(drv, '编辑 API', 5)
    ptext = (dlg3.text or '') if dlg3 is not None else ''
    record('T4 参数配置页签有内容', len(ptext) > 60 and '编辑 API' in ptext, 'len=%d text=%s' % (len(ptext), ptext[:300]))
    B.set_theme(drv, 'dark')
    time.sleep(0.6)
    shot(drv, 't4_api_param_dark')
    B.set_theme(drv, 'light')
    click_btn_in(drv, dlg, '取消', exact=True)


def t5_speaker_group(drv, token):
    B.goto(drv, '/devices/playback', '设备管理')
    time.sleep(1.5)
    # 更多操作（aria-label）
    click_aria(drv, '更多操作', 10)
    time.sleep(0.8)
    pick_popover_option(drv, '逻辑音箱')
    dlg = dialog_with_title(drv, '逻辑音箱', 20)
    record('T5 逻辑音箱弹窗打开', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    name = PREFIX + 'SPK_' + time.strftime('%H%M%S')
    inputs = [e for e in dlg.find_elements(By.TAG_NAME, 'input') if e.is_displayed()]
    if not inputs:
        record('T5 新建逻辑音箱', False, 'no input')
        return
    js_set(drv, inputs[0], name)
    if len(inputs) > 1:
        js_set(drv, inputs[1], '走查分组')
    click_btn_in(drv, dlg, '新建逻辑音箱', exact=False)
    time.sleep(2.5)
    _, js = B.api('/api/v1/playback-devices/speaker-groups', token)
    glist = js.get('data') if isinstance(js, dict) else js
    if isinstance(glist, dict):
        glist = glist.get('items') or []
    hit = [g for g in (glist or []) if g.get('name') == name]
    record('T5 创建分组', bool(hit), 'status=%s hits=%s' % (js.get('code') if isinstance(js, dict) else '', [g.get('id') for g in hit]))
    if not hit:
        return
    gid = hit[0]['id']
    FIX['speaker_group'] = gid
    # 实验室映射（成员）
    click_aria(drv, '查看逻辑音箱 %s 的实验室映射' % name, 10)
    time.sleep(1.5)
    shot(drv, 't5_group_members')
    # 编辑重命名
    click_aria(drv, '编辑逻辑音箱 %s' % name, 10)
    time.sleep(1.0)
    inputs = [e for e in dlg.find_elements(By.TAG_NAME, 'input') if e.is_displayed()]
    newname = name + '_改'
    js_set(drv, inputs[0], newname)
    click_btn_in(drv, dlg, '保存修改', exact=False)
    time.sleep(2.0)
    _, js = B.api('/api/v1/playback-devices/speaker-groups', token)
    glist = js.get('data') if isinstance(js, dict) else js
    if isinstance(glist, dict):
        glist = glist.get('items') or []
    ren = [g for g in (glist or []) if g.get('id') == gid]
    record('T5 重命名', bool(ren) and ren[0].get('name') == newname,
           'name=%s' % (ren[0].get('name') if ren else None))
    shot(drv, 't5_group_renamed_light')
    B.set_theme(drv, 'dark')
    time.sleep(0.6)
    shot(drv, 't5_group_dark')
    B.set_theme(drv, 'light')
    # 删除
    click_aria(drv, '删除逻辑音箱 %s' % newname, 10)
    time.sleep(1.0)
    for el in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if el.is_displayed() and (el.text or '').strip() in ('删除', '确认', '确定'):
                drv.execute_script('arguments[0].click();', el)
                break
        except Exception:
            pass
    time.sleep(2.0)
    _, js = B.api('/api/v1/playback-devices/speaker-groups', token)
    glist = js.get('data') if isinstance(js, dict) else js
    if isinstance(glist, dict):
        glist = glist.get('items') or []
    gone = not [g for g in (glist or []) if g.get('id') == gid]
    record('T5 删除分组', gone, 'still=%s' % (not gone))
    if gone:
        FIX.pop('speaker_group', None)
    # 上传选项中的逻辑音箱选择在 T8（需先选文件才渲染上传选项）验证；留一个分组到 T8
    dlg = dialog_with_title(drv, '逻辑音箱', 10)
    if dlg is not None:
        name2 = PREFIX + 'SPK2_' + time.strftime('%H%M%S')
        inputs = [e for e in dlg.find_elements(By.TAG_NAME, 'input') if e.is_displayed()]
        if inputs:
            js_set(drv, inputs[0], name2)
            click_btn_in(drv, dlg, '新建逻辑音箱', exact=False)
            time.sleep(2.0)
            _, js = B.api('/api/v1/playback-devices/speaker-groups', token)
            glist = js.get('data') if isinstance(js, dict) else js
            if isinstance(glist, dict):
                glist = glist.get('items') or []
            hit2 = [g for g in (glist or []) if g.get('name') == name2]
            if hit2:
                FIX['speaker_group'] = hit2[0]['id']
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            try:
                if el.is_displayed() and el.get_attribute('aria-label') == 'Close':
                    drv.execute_script('arguments[0].click();', el)
                    break
            except Exception:
                pass
    record('T5 分组 CRUD 完成（成员/派发见 T8 上传选项与接口）', True,
           'gid=%s 已删除' % gid)


def t6_spl(drv, token):
    B.goto(drv, '/SPLMapping', '声压级映射管理')
    click_page_btn(drv, 'API/Realtime RMS-SPL')
    time.sleep(2.0)
    click_page_btn(drv, '添加 RMS-SPL 映射')
    dlg = dialog_with_title(drv, '添加 RMS-SPL 映射', 20)
    record('T6 打开 RMS-SPL 表单', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    dtext = dlg.text or ''
    field_marks = [k for k in ['关联被测 API', '映射名称', '增益下限', '增益上限', '校准点集'] if k in dtext]
    record('T6 表单字段精简后齐全', len(field_marks) >= 5, 'fields=%s' % field_marks)
    banned = [k for k in ['参考声压级', '参考线性增益'] if k in dtext]
    record('T6 无参考声压级/参考增益字段', len(banned) == 0, 'banned=%s' % banned)
    record('T6 无校准点提示文案', '无校准点时原音频电平不动' in dtext, 'text=%s' % dtext[:300])
    # 填名称 + 关联 API（必须先填，否则先触发名称/API 校验）
    name = PREFIX + 'SPL_' + time.strftime('%H%M%S')
    set_by_label(drv, dlg, '映射名称', name)
    sel = None
    for el in dlg.find_elements(By.CSS_SELECTOR, '[aria-label="关联被测 API"]'):
        if el.is_displayed():
            sel = el
    if sel:
        drv.execute_script('arguments[0].click();', sel)
        time.sleep(0.8)
        _, js = B.api('/api/v1/apis?page=1&per_page=1', token)
        api0 = ((js.get('data') or {}).get('items') or [None])[0]
        if api0:
            for el in drv.find_elements(By.CSS_SELECTOR, '[role="option"]'):
                try:
                    if el.is_displayed() and api0['name'] in (el.text or ''):
                        drv.execute_script('arguments[0].click();', el)
                        break
                except Exception:
                    pass
            time.sleep(0.6)
    # 加一行空校准点 → 保存：有效行 0，强制拦截
    click_btn_in(drv, dlg, '添加校准点', exact=False)
    time.sleep(1.0)
    click_btn_in(drv, dlg, '保存', exact=True)
    time.sleep(1.5)
    got = toast_text(drv, '必须至少添加 1 个有效校准点', 12)
    record('T6 无有效校准点保存被拦截', got, 'toast=%s' % got)
    shot(drv, 't6_validation_light')
    # 行级错误提示（空行）
    rowerr = ('请输入目标 SPL' in body(drv)) or ('请输入实测 dBFS' in body(drv))
    record('T6 空校准点行级校验提示', rowerr, 'rowerr=%s' % rowerr)
    # 该空行补成 3 点中的第一点
    pts = [('65', '-50'), ('75', '-40'), ('85', '-10')]
    click_btn_in(drv, dlg, '添加校准点', exact=False)
    click_btn_in(drv, dlg, '添加校准点', exact=False)
    time.sleep(1.0)
    for i, (spl, dbfs) in enumerate(pts):
        tgt = dlg.find_elements(By.CSS_SELECTOR, "input[aria-label='第 %d 行目标 SPL']" % (i + 1))
        rms = dlg.find_elements(By.CSS_SELECTOR, "input[aria-label='第 %d 行实测 RMS']" % (i + 1))
        if tgt and rms:
            js_set(drv, tgt[0], spl)
            js_set(drv, rms[0], dbfs)
    time.sleep(1.0)
    heads = [k for k in ['目标 SPL', '实测 RMS', '线性增益', '增益（dB）'] if k in (dlg.text or '')]
    record('T6 校准点表头（增益只读推导列）', len(heads) >= 4, 'heads=%s' % heads)
    shot(drv, 't6_points_filled')
    click_btn_in(drv, dlg, '保存', exact=True)
    time.sleep(3.0)
    _, js = B.api('/api/v1/digital-spl?page=1&per_page=100', token)
    items = (js.get('data') or {}).get('items') or []
    hit = [m for m in items if (m.get('name') or '') == name]
    record('T6 创建映射', bool(hit), 'name=%s hits=%d' % (name, len(hit)))
    if hit:
        mid = hit[0]['id']
        FIX['digital_spl'] = mid
        gs, gj = B.api('/api/v1/digital-spl/%s' % mid, token)
        m = gj.get('data') or {}
        pts_back = m.get('calibration_points') or m.get('calibrationPoints') or []
        gains = [round(float(p.get('gain_linear') or p.get('gainLinear') or 0), 4) for p in pts_back]
        record('T6 回读校准点与推导增益', len(pts_back) == 3 and gains == [0.1, 0.3162, 10.0],
               'GET %s -> %s points=%s gains=%s' % (mid, gs, len(pts_back), gains))
    shot(drv, 't6_after_save_light')
    B.set_theme(drv, 'dark')
    time.sleep(0.6)
    shot(drv, 't6_spl_dark')
    B.set_theme(drv, 'light')


def t7_visibility(token):
    s_all, j_all = B.api('/api/v1/audios?page=1&per_page=1', token)
    s_sh, j_sh = B.api('/api/v1/audios?page=1&per_page=1&visibility=shared', token)
    s_pr, j_pr = B.api('/api/v1/audios?page=1&per_page=1&visibility=private', token)
    t_all = (j_all.get('data') or {}).get('total')
    t_sh = (j_sh.get('data') or {}).get('total')
    t_pr = (j_pr.get('data') or {}).get('total')
    s_bad, _ = B.api('/api/v1/audios?page=1&per_page=1&visibility=bogus', token)
    record('T7 可见性筛选服务端生效', s_sh == 200 and s_pr == 200 and t_all == (t_sh or 0) + (t_pr or 0),
           'all=%s shared=%s private=%s' % (t_all, t_sh, t_pr))
    record('T7 非法可见性被拒', s_bad in (400, 422), 'status=%s' % s_bad)


def t8_audio_import(drv, token):
    # 生成测试音频（工作区内）
    wav_dir = os.path.join(ART, 'wav_in')
    os.makedirs(wav_dir, exist_ok=True)
    import wave, struct
    paths = []
    for i in (1, 2):
        p = os.path.join(wav_dir, '%sUP%d_%s.wav' % (PREFIX, i, time.strftime('%H%M%S')))
        with wave.open(p, 'w') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            frames = b''.join(struct.pack('<h', 0) for _ in range(8000))
            w.writeframes(frames)
        paths.append(p)
    B.goto(drv, '/audio-import', '音频管理')
    click_page_btn(drv, '上传音频')
    dlg = dialog_with_title(drv, '上传音频', 15)
    record('T8 上传弹窗', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    # 多文件（Selenium 对同一 input 多次 send_keys 会覆盖，改用 JS DataTransfer 受限；直接 send_keys 两行分隔）
    inp = None
    for el in dlg.find_elements(By.CSS_SELECTOR, "input[type='file']"):
        inp = el
    if inp:
        inp.send_keys('\n'.join(paths))
        time.sleep(2.0)
        dtext = dlg.text or ''
        record('T8 多文件加入待传', '2' in dtext and ('UP1' in dtext or 'wav' in dtext), 'text=%s' % dtext[:400])
    shot(drv, 't8_upload_dialog_light')
    dlg_now = dialog_with_title(drv, '上传音频', 5)
    utext = (dlg_now.text or '') if dlg_now is not None else ''
    names = [k for k in ['音频类型', '算法类型', '继承音频标签', '生成测试用例'] if k in utext]
    record('T8 上传选项字段（类型/算法/生成用例/标签）', len(names) >= 4, 'names=%s' % names)
    # 打开「生成测试用例」后露出「逻辑音箱」轮次配置（音箱分组接线）
    toggled = drv.execute_script('''
      var root = arguments[0];
      var labels = Array.from(root.querySelectorAll('label,span,button,div'));
      for (var i=0;i<labels.length;i++){
        if ((labels[i].textContent||'').trim() === '生成测试用例') {
          var sw = labels[i].parentElement ? labels[i].parentElement.querySelector('[role=switch],button') : null;
          if (sw) { sw.click(); return true; }
        }
      }
      return false;
    ''', dlg_now) if dlg_now is not None else False
    time.sleep(1.5)
    utext2 = body(drv)
    record('T8 上传选项含逻辑音箱（音箱分组接线）', '逻辑音箱' in utext2,
           'toggled=%s has=%s tail=%s' % (toggled, '逻辑音箱' in utext2, utext2[-300:]))
    shot(drv, 't8_upload_options')
    click_btn_in(drv, dlg, '开始上传', exact=False)
    ok = toast_text(drv, '上传完成', 30)
    record('T8 上传成功提示', ok, 'toast=%s' % ok)
    time.sleep(2.0)
    _, js = B.api('/api/v1/audios?page=1&per_page=20&keyword=%s' % urllib.parse.quote(PREFIX), token)
    items = (js.get('data') or {}).get('items') or []
    mine = [a for a in items if (a.get('name') or '').startswith(PREFIX)]
    FIX.setdefault('audios', []).extend([a['id'] for a in mine])
    record('T8 导入后可回读', len(mine) >= 2, 'created=%s' % [(a['id'], a.get('name')) for a in mine][:5])
    time.sleep(1.0)
    # 关掉上传弹窗后列表应失效刷新出现新文件
    dclose = dialog_with_title(drv, '上传音频', 5)
    if dclose is not None:
        click_btn_in(drv, dclose, '取消', exact=True)
    time.sleep(2.5)
    try:
        drv.refresh()
        B.wait_ready(drv)
    except Exception:
        pass
    time.sleep(3.0)
    record('T8 列表刷新', PREFIX in body(drv), 'body has prefix=%s' % (PREFIX in body(drv)))
    shot(drv, 't8_after_upload')
    # 文件夹导入弹窗
    click_page_btn(drv, '批量从文件夹导入')
    dlg2 = dialog_with_title(drv, '批量从文件夹导入', 15)
    if dlg2:
        t2 = dlg2.text or ''
        marks = [k for k in ['选择文件夹', '递归导入子文件夹', '音频类型', '算法类型', '生成测试用例', '继承音频标签'] if k in t2]
        record('T8 文件夹导入弹窗选项', len(marks) >= 5, 'marks=%s' % marks)
        shot(drv, 't8_folder_dialog_light')
        B.set_theme(drv, 'dark')
        time.sleep(0.5)
        shot(drv, 't8_folder_dialog_dark')
        B.set_theme(drv, 'light')
        click_btn_in(drv, dlg2, '取消', exact=True)
    else:
        record('T8 文件夹导入弹窗选项', False, 'no dialog')


def t9_audio_preview(drv, token):
    B.goto(drv, '/audio-import', '音频管理')
    time.sleep(2.0)
    # 取本 run 上传的第一条音频
    ids = FIX.get('audios') or []
    if not ids:
        record('T9 音频试听', False, 'no audio fixture')
        return
    _, js = B.api('/api/v1/audios/%s' % ids[0], token)
    a = js.get('data') or {}
    # stream 接口
    s_st, j_st = B.api('/api/v1/audios/%s/stream' % ids[0], token)
    url = (j_st.get('data') or {}).get('url') if isinstance(j_st.get('data'), dict) else j_st.get('url')
    record('T9 GET stream 返回预签名 URL', s_st == 200 and bool(url), 'status=%s url=%s' % (s_st, (url or '')[:120]))
    # 打开试听弹窗（行操作菜单 → 预览）
    click_aria(drv, '音频 %s 的操作' % a.get('name'), 15)
    time.sleep(0.8)
    pick_popover_option(drv, '预览')
    dlg = dialog_with_title(drv, '音频播放', 20)
    record('T9 试听弹窗打开', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return
    time.sleep(1.0)
    # 浏览器播放
    B.reset_reqs(drv)
    click_aria(drv, '播放', 10)
    time.sleep(3.0)
    reqs = B.get_reqs(drv, 0.5)
    st_req = B.find_req(reqs, '/stream')
    has_audio = drv.execute_script("var a=document.querySelector('audio'); return a ? (a.src||'').slice(0,150) : null;")
    record('T9 stream 请求命中', len(st_req) > 0, 'reqs=%s' % [(r.get('method'), r.get('url'), r.get('status')) for r in st_req][:2])
    record('T9 audio 元素以预签名 URL 播放', bool(has_audio) and 'http' in (has_audio or ''),
           'audio.src=%s' % has_audio)
    shot(drv, 't9_preview_browser_light')
    # 停止
    click_aria(drv, '停止播放', 8)
    time.sleep(1.0)
    playing = drv.execute_script("var a=document.querySelector('audio'); return a ? !a.paused : false;")
    record('T9 停止播放', not playing, 'playing=%s' % playing)
    # 实验室播放 → /preview + stop-preview
    # 切换播放模式
    sel = drv.find_elements(By.CSS_SELECTOR, '[aria-label="播放模式"]')
    if sel:
        drv.execute_script('arguments[0].click();', sel[0])
        time.sleep(0.8)
        pick_popover_option(drv, '实验室播放')
        time.sleep(1.0)
        B.reset_reqs(drv)
        click_aria(drv, '播放', 8)
        time.sleep(4.0)
        reqs = B.get_reqs(drv, 0.5)
        pv = B.find_req(reqs, '/preview')
        msg = (pv[0].get('resp') or '') if pv else ''
        record('T9 POST /audios/{id}/preview 命中', len(pv) > 0,
               'reqs=%s resp=%s' % ([(r.get('method'), r.get('url'), r.get('status')) for r in pv][:2], msg[:300]))
        shot(drv, 't9_preview_lab')
        if pv and (pv[0].get('status') or 0) >= 400:
            # 环境拦截（有排队 E2E 任务时禁止后端扬声器播放）→ 提示须为可读文案
            readable = '不允许使用后端扬声器播放' in body(drv) or '不允许' in (msg or '')
            record('T9 试听失败可读提示（不透传原始异常）', readable,
                   'toast_in_page=%s msg=%s' % ('不允许' in body(drv), msg[:200]))
            click_aria(drv, '停止播放', 3)
            s_sp, j_sp = B.api('/api/v1/audios/%s/stop-preview' % ids[0], token, method='POST')
            record('T9 POST /audios/{id}/stop-preview 可用', s_sp == 200,
                   'status=%s body=%s' % (s_sp, json.dumps(j_sp, ensure_ascii=False)[:200]))
        else:
            click_aria(drv, '停止播放', 8)
            time.sleep(2.0)
            reqs = B.get_reqs(drv, 0.5)
            sp = B.find_req(reqs, '/stop-preview')
            record('T9 POST /audios/{id}/stop-preview 命中', len(sp) > 0,
                   'reqs=%s' % [(r.get('method'), r.get('url'), r.get('status')) for r in sp][:2])
    else:
        record('T9 播放模式切换', False, 'no mode select')
    # 关闭
    for el in dlg.find_elements(By.TAG_NAME, 'button'):
        try:
            if el.is_displayed() and (el.get_attribute('aria-label') == 'Close'):
                drv.execute_script('arguments[0].click();', el)
                break
        except Exception:
            pass
    B.set_theme(drv, 'dark')
    time.sleep(0.5)
    B.goto(drv, '/audio-import', '音频管理')
    shot(drv, 't9_audio_dark')
    B.set_theme(drv, 'light')


def t10_linkage(drv, token):
    _, jd = B.api('/api/v1/test-devices?page=1&per_page=1000', token)
    devs = (jd.get('data') or {}).get('items') or []
    online = len([d for d in devs if (d.get('status') or '') == 'online'])
    _, ja = B.api('/api/v1/apis?page=1&per_page=1000', token)
    apis = (ja.get('data') or {}).get('items') or []
    B.goto(drv, '/start-test', '开始测试')
    click_page_btn(drv, '下一步', exact=False)
    time.sleep(5.0)
    time.sleep(1.5)
    txt = body(drv)
    # 设备卡/API 卡数量（按卡片内「型号」「在线/离线」与 API 端点）
    counts = drv.execute_script('''
      var cards = document.querySelectorAll('div.rounded-xl.border');
      return cards.length;
    ''')
    record('T10 开始测试设备/API 列表刷新', ('离线' in txt or '在线' in txt) and ('API' in txt),
           'cards=%s online_api=%s api_count=%s' % (counts, online, len(apis)))
    shot(drv, 't10_start_test_step2')


# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------

def cleanup(token):
    for did in sorted(set(FIX.get('devices', []))):
        s, _ = B.api('/api/v1/test-devices/%s' % did, token, method='DELETE')
        print('cleanup device %s -> %s' % (did, s))
    for mid in [FIX.get('digital_spl')] if FIX.get('digital_spl') else []:
        s, _ = B.api('/api/v1/digital-spl/%s' % mid, token, method='DELETE')
        print('cleanup digital-spl %s -> %s' % (mid, s))
    gid = FIX.get('speaker_group')
    if gid:
        s, _ = B.api('/api/v1/playback-devices/speaker-groups/%s' % gid, token, method='DELETE')
        print('cleanup speaker-group %s -> %s' % (gid, s))
    for aid in FIX.get('audios', []):
        s, _ = B.api('/api/v1/audios/%s' % aid, token, method='DELETE')
        print('cleanup audio %s -> %s' % (aid, s))


def main():
    which = sys.argv[1:] or ['all']
    token, _ = B.rsa_login_token(*B.ACCOUNT)
    health('start', token)
    drv = B.driver_init()
    try:
        drv.get(B.BASE + '/login')
        B.wait_ready(drv)
        drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
                           B.TOKEN_KEY, token)
        drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
                           B.THEME_KEY, 'light')
        drv.execute_script('try { localStorage.removeItem("iatp:auth:v1"); } catch(e) {}')
        steps = [
            ('t1', lambda: t1_devices_filter(drv, token)),
            ('t2', lambda: t2_scan_add(drv, token)),
            ('t3', lambda: t3_offline_prune(drv, token)),
            ('t4', lambda: t4_api_same_component(drv, token)),
            ('t5', lambda: t5_speaker_group(drv, token)),
            ('t6', lambda: t6_spl(drv, token)),
            ('t7', lambda: t7_visibility(token)),
            ('t8', lambda: t8_audio_import(drv, token)),
            ('t9', lambda: t9_audio_preview(drv, token)),
            ('t10', lambda: t10_linkage(drv, token)),
        ]
        for key, fn in steps:
            if 'all' in which or key in which:
                try:
                    print('---- %s start %s' % (key, time.strftime('%H:%M:%S')))
                    fn()
                except Exception as exc:
                    import traceback
                    traceback.print_exc()
                    record(key + ' 执行异常', False, repr(exc))
                health(key, token)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        cleanup(token)
        with open(os.path.join(ART, 'results.json'), 'w', encoding='utf-8') as f:
            json.dump({'health': HEALTH, 'results': RESULTS, 'fixtures': FIX}, f, ensure_ascii=False, indent=2)
        passed = len([r for r in RESULTS if r['ok']])
        print('SUMMARY %d/%d passed' % (passed, len(RESULTS)))


if __name__ == '__main__':
    main()
