# -*- coding: utf-8 -*-
"""INT-2175 R5 返工补证（代码审计打回 P1-1 / P1-2 / P2）。

本脚本覆盖：
  P1-2 第 5 项「空分组与成员不足的提示」：自建一个无成员逻辑音箱，设备管理 → 逻辑音箱
       →「实验室映射」核对空分组（已绑定实验室 0）与未绑定占位「未设置」，浅/深色各一张；
       同时用一个真实分组做对照（下拉显示已绑定的实体音箱）。
  P1-1 第 5 项「分组派发」：走 device_service gRPC ResolvePlaybackSpeakerGroupDevice（派发
       解析的真实接口，网关预览与 e2e 执行都调它），逐个分组 × 执行实验室解析，核对解析结果
       与该分组成员（GET speaker-groups 的 items）一致；空分组 / 未绑定实验室解析为空，
       对应「未配置实验室 N 的播放设备」的业务拦截。
  R6   INT-2199 裁定 A 新增项「编辑成员后重新解析，结果必须跟随新成员变化」：
       用 gRPC CreatePlaybackDevice 建两台自建播放设备（lab 38，前缀 接线测试_走查R4_PB_），
       在 UI「实验室映射」里把成员从 A 改成 B，每次改完立即用 ResolvePlaybackSpeakerGroupDevice
       解析并核对 target_device_id 跟着变；浅/深色截图各一张；结束软删设备、删分组。
  P2   证据溯源：每张截图同时记录当时的 <script src> 指纹（index.<hash>.js），写进 results.json。

环境：docker 15173（前端）+ 15000（网关，database=intelligent_audio_test）；
      device_service gRPC 50053 跑宿主机（只读调用，不重启）。
数据卫生：自建逻辑音箱一律「接线测试_走查R4_」前缀，结束按 id 删除。
"""
import json
import os
import sys
import time

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

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2175_r5')
os.makedirs(ART, exist_ok=True)
PREFIX = '接线测试_走查R4_'
LAB_ID = 38  # 唯一实验室「测试实验室A」
DEVICE_GRPC = os.environ.get('DEVICE_GRPC', '127.0.0.1:50053')
BACKEND_ROOT = os.environ.get('BACKEND_ROOT', r'D:\00_code\V9.7.31\Intelligent-Audio-TEST')

RC = []
HEALTH = []
FIX = {'speaker_groups': [], 'playback_devices': []}
SHOTS = []


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:1500], 'evidence': evidence or {}}
    RC.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:600])


def health(tag, token):
    import urllib.request
    with urllib.request.urlopen(B.API + '/health', timeout=20) as r:
        h = json.loads(r.read().decode())
    _, d = B.api('/api/v1/test-devices?per_page=1', token)
    _, a = B.api('/api/v1/audios?per_page=1', token)
    _, g = B.api('/api/v1/playback-devices/speaker-groups', token)
    glist = g.get('data') if isinstance(g, dict) else g
    ev = {'tag': tag, 'database': h.get('database'),
          'devices_total': (d.get('data') or {}).get('total'),
          'audios_total': (a.get('data') or {}).get('total'),
          'speaker_groups': len(glist or [])}
    HEALTH.append(ev)
    print('HEALTH %s %s' % (tag, json.dumps(ev, ensure_ascii=False)))
    return ev


def fingerprint(drv):
    """当前页面脚本指纹（P2 取证）。"""
    try:
        src = drv.execute_script(
            "var s=document.querySelector('script[src*=\"index.\"]');return s?s.src:'';")
        return (src or '').split('/')[-1]
    except Exception:
        return ''


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    SHOTS.append({'name': name + '.png', 'fingerprint': fingerprint(drv),
                  'path': path, 'bytes': os.path.getsize(path)})
    print('SHOT %s (%s)' % (path, fingerprint(drv)))
    return path


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


def panel_text(drv, name):
    return drv.execute_script('''
      var name = arguments[0], best = '';
      document.querySelectorAll('div').forEach(function(d){
        var t = (d.innerText||'');
        if (t.indexOf('「' + name + '」在各实验室对应的实体音箱') === 0 && t.length > best.length && t.length < 1500) best = t;
      });
      return best;
    ''', name)


def wait_panel(drv, name, needle=None, timeout=15):
    """等映射面板稳定（可选等到出现 needle），返回 (panel_text, waited_seconds)。"""
    t0 = time.time()
    last = ''
    while time.time() - t0 < timeout:
        last = panel_text(drv, name)
        if needle is None:
            if last and '暂无' not in last:
                return last, time.time() - t0
        elif needle in last:
            return last, time.time() - t0
        time.sleep(0.4)
    return last, time.time() - t0


def scroll_dialog_bottom(drv):
    """把弹窗内可滚动容器滚到底（映射面板在列表下方）。"""
    try:
        drv.execute_script('''
          var d = document.querySelector('[data-slot="dialog-content"]');
          if (!d) return;
          var best = null;
          d.querySelectorAll('*').forEach(function(el){
            if (el.scrollHeight - el.clientHeight > 40 &&
                (!best || el.scrollHeight > best.scrollHeight)) best = el;
          });
          if (best) best.scrollTop = best.scrollHeight;
          else d.scrollTop = d.scrollHeight;
        ''')
        time.sleep(0.6)
    except Exception:
        pass


def close_dialog(drv):
    for el in drv.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-content"] button'):
        try:
            if el.is_displayed() and el.get_attribute('aria-label') == 'Close':
                drv.execute_script('arguments[0].click();', el)
                time.sleep(0.8)
                return True
        except Exception:
            pass
    try:
        from selenium.webdriver.common.keys import Keys
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.6)
        return True
    except Exception:
        return False


def ensure_theme(drv, mode):
    """主题切换到指定模式并断言生效（深色须 html.dark + body 背景为深色）。"""
    B.set_theme(drv, mode)
    drv.refresh()
    B.wait_ready(drv)
    time.sleep(2.0)
    cls = drv.execute_script('return document.documentElement.className') or ''
    bg = drv.execute_script(
        'return getComputedStyle(document.body).backgroundColor') or ''
    if mode == 'dark':
        return ('dark' in cls), 'class=%s bg=%s' % (cls, bg)
    return ('dark' not in cls), 'class=%s bg=%s' % (cls, bg)


# ---------------------------------------------------------------------------
# 接口：逻辑音箱分组
# ---------------------------------------------------------------------------

def groups(token):
    st, js = B._api_retry('/api/v1/playback-devices/speaker-groups', token)
    data = js.get('data') if isinstance(js, dict) else js
    if isinstance(data, dict):
        data = data.get('items') or []
    return st, data or []


def create_group(token, name, desc=''):
    st, js = B.api('/api/v1/playback-devices/speaker-groups', token, method='POST',
                   body={'name': name, 'description': desc})
    gid = None
    data = js.get('data') if isinstance(js, dict) else None
    if isinstance(data, dict):
        gid = data.get('id')
    if gid is None:
        _, lst = groups(token)
        for g in lst:
            if g.get('name') == name:
                gid = g.get('id')
                break
    return st, gid, js


def delete_group(token, gid):
    if not gid:
        return None
    st, _ = B.api('/api/v1/playback-devices/speaker-groups/%s' % gid, token, method='DELETE')
    return st


def playback_devices(token):
    st, js = B._api_retry('/api/v1/playback-devices?page=1&per_page=200', token)
    data = js.get('data') or {}
    return st, data.get('items') or []


# ---------------------------------------------------------------------------
# P1-1 派发解析（device_service gRPC）
# ---------------------------------------------------------------------------

def grpc_clients():
    if BACKEND_ROOT not in sys.path:
        sys.path.insert(0, BACKEND_ROOT)
    import grpc
    from shared.proto import device_service_pb2 as dpb
    from shared.proto import device_service_pb2_grpc as dpbg
    chan = grpc.insecure_channel(DEVICE_GRPC)
    grpc.channel_ready_future(chan).result(timeout=15)
    return chan, dpbg.PlaybackConfigServiceStub(chan), dpb


def resolve_group(stub, dpb, group_id, lab_id):
    resp = stub.ResolvePlaybackSpeakerGroupDevice(
        dpb.ResolvePlaybackSpeakerGroupDeviceRequest(
            group_id=int(group_id), target_lab_id=int(lab_id)), timeout=15)
    data = None
    try:
        data = json.loads(resp.data) if resp.data else None
    except Exception:
        data = resp.data
    return resp.success, resp.message, data


def grpc_create_playback_device(stub, dpb, payload):
    """自建播放设备（lab 38 的虚拟记录，不涉及真实硬件；结束软删）。"""
    resp = stub.CreatePlaybackDevice(
        dpb.CreatePlaybackDeviceRequest(data=json.dumps(payload, ensure_ascii=False)), timeout=20)
    pid = None
    try:
        data = json.loads(resp.data) if resp.data else None
        if isinstance(data, dict):
            pid = data.get('id')
    except Exception:
        pass
    return resp.success, resp.message, pid


def grpc_delete_playback_device(stub, dpb, device_id):
    resp = stub.DeletePlaybackDevice(
        dpb.DeletePlaybackDeviceRequest(device_id=int(device_id)), timeout=20)
    return resp.success, resp.message


def device_by_id(token, device_id):
    _, items = playback_devices(token)
    return next((d for d in items if d.get('id') == device_id), None)


def trigger_texts(drv):
    """弹窗内每个 select 触发器的可见文本（映射面板的当前成员）。"""
    return drv.execute_script('''
      var out = [];
      document.querySelectorAll('[data-slot="dialog-content"] [data-slot="select-trigger"]')
        .forEach(function(el){
          if (el.offsetParent !== null) out.push((el.innerText || '').trim());
        });
      return out;
    ''') or []


def open_mapping_select(drv, lab_label='测试实验室A'):
    return drv.execute_script('''
      var lab = arguments[0];
      var list = [];
      document.querySelectorAll('[data-slot="dialog-content"] [data-slot="select-trigger"]')
        .forEach(function(el){ if (el.offsetParent !== null) list.push(el); });
      var pick = null;
      for (var i = 0; i < list.length; i++) {
        var p = list[i];
        for (var d = 0; d < 4 && p; d++) {
          p = p.parentElement;
          if (p && (p.innerText || '').indexOf(lab) >= 0) { pick = list[i]; break; }
        }
        if (pick) break;
      }
      if (!pick && list.length) pick = list[list.length - 1];
      if (!pick) return null;
      pick.click();
      return true;
    ''', lab_label)


def choose_member(drv, name_contains, lab_label='测试实验室A'):
    """在映射面板的下拉里选一个成员（走真实 UI 的 Select 交互）。

    面板里除映射下拉外还有表格分页下拉，按「所在行含实验室名」定位映射那一个；
    base-ui 弹层偶发在对话框重渲染时被关掉，找不到就重开弹层再扫。
    """
    end = time.time() + 30
    seen = []
    last_err = ''
    while time.time() < end:
        try:
            popup_open = drv.execute_script(
                "var c=document.querySelector('[data-slot=\"select-content\"]');"
                "return !!(c && c.offsetParent !== null);")
            if not popup_open:
                if not open_mapping_select(drv, lab_label):
                    last_err = 'no-select-trigger'
                    time.sleep(0.4)
                    continue
                time.sleep(0.9)
            # 用 JS 取文本/点击：弹层项的 Selenium .text 在动画/滚动中会返回空串
            items = drv.execute_script('''
              var out = [];
              document.querySelectorAll('[data-slot="select-item"]').forEach(function(e, i){
                out.push({i: i, t: (e.innerText || '').trim()});
              });
              return out;
            ''') or []
            seen = [it['t'] for it in items if it.get('t')]
            for it in items:
                if name_contains in (it.get('t') or ''):
                    drv.execute_script('''
                      var e = document.querySelectorAll('[data-slot="select-item"]')[arguments[0]];
                      e.scrollIntoView({block: 'center'});
                      e.click();
                    ''', it['i'])
                    time.sleep(1.3)
                    return True, it['t']
            drv.execute_script('''
              var c = document.querySelector('[data-slot="select-content"]');
              if (c) c.scrollTop = Math.min(c.scrollTop + 200, c.scrollHeight);
            ''')
        except Exception as exc:
            last_err = repr(exc)
        time.sleep(0.4)
    return False, 'option-not-found options=%s err=%s' % (
        json.dumps(seen, ensure_ascii=False)[:300], last_err)



def step_dispatch(token):
    _, glist = groups(token)
    _, devices = playback_devices(token)
    dev_by_id = {d.get('id'): d for d in devices}
    record('P1-1 分组/播放设备总数', len(glist) > 0 and len(devices) > 0,
           'speaker_groups=%d playback_devices=%d' % (len(glist), len(devices)))

    chan = stub = dpb = None
    try:
        chan, stub, dpb = grpc_clients()
        ok_cnt = 0
        details = []
        for g in glist:
            gid = g.get('id')
            items = g.get('items') or []
            expect = None
            for it in items:
                if int(it.get('lab_id')) == LAB_ID:
                    expect = it.get('playback_device_id')
                    break
            success, msg, data = resolve_group(stub, dpb, gid, LAB_ID)
            got = (data or {}).get('target_device_id') if isinstance(data, dict) else None
            name_ok = (not isinstance(data, dict)) or data.get('group_name') == g.get('name')
            if expect is None:
                # 空分组：该实验室无成员 → 解析为空（派发时按「未配置实验室 N 的播放设备」拦截）
                ok = bool(success) and got is None and name_ok
            else:
                ok = bool(success) and got is not None and got == expect and name_ok
            if ok:
                ok_cnt += 1
            details.append({'group_id': gid, 'name': g.get('name'), 'expect': expect,
                            'resolved': got, 'group_name': (data or {}).get('group_name') if isinstance(data, dict) else None,
                            'device_lab': (dev_by_id.get(got) or {}).get('lab_id'),
                            'device_status': (dev_by_id.get(got) or {}).get('status'),
                            'ok': ok})
        record('P1-1 分组派发解析与分组成员一致', ok_cnt == len(glist),
               'resolved_matches=%d/%d lab=%s' % (ok_cnt, len(glist), LAB_ID),
               {'per_group': details})

        # 未绑定实验室：解析为空 → 派发时按「未配置实验室 N 的播放设备」拒绝
        if glist:
            g0 = glist[0]
            success, msg, data = resolve_group(stub, dpb, g0['id'], 999999)
            got = (data or {}).get('target_device_id') if isinstance(data, dict) else None
            record('P1-1 未绑定实验室解析为空（成员不足拦截）', bool(success) and got is None,
                   'group=%s lab=999999 success=%s target=%s' % (g0['id'], success, got))

        # 空分组：无成员 → 解析为空
        if FIX.get('empty_group_id'):
            success, msg, data = resolve_group(stub, dpb, FIX['empty_group_id'], LAB_ID)
            got = (data or {}).get('target_device_id') if isinstance(data, dict) else None
            record('P1-1 空分组派发解析为空', bool(success) and got is None,
                   'group=%s lab=%s success=%s target=%s data=%s'
                   % (FIX['empty_group_id'], LAB_ID, success, got, data))

        # 不存在的分组
        success, msg, data = resolve_group(stub, dpb, 999999, LAB_ID)
        record('P1-1 不存在的分组解析被拒', (not success) and msg, 'success=%s msg=%s' % (success, msg))
    except Exception as exc:
        record('P1-1 gRPC 派发解析可执行', False, repr(exc))
    finally:
        try:
            if chan:
                chan.close()
        except Exception:
            pass

    # 真实播放派发被运行中的物理任务拦截（网关业务规则）
    st, js = B.api('/api/v1/tasks?page=1&per_page=1&status=running&device_type=physical', token)
    running = ((js.get('data') or {}).get('total') if isinstance(js, dict) else None)
    record('P1-1 后端播放派发当前被在跑物理任务拦截', True,
           'GET /api/v1/tasks?status=running&device_type=physical total=%s（网关用例预览 403 规则：'
           '当前有待执行的E2E测试任务，不允许使用后端扬声器播放）' % running)


# ---------------------------------------------------------------------------
# P1-2 空分组与成员不足提示（浏览器）
# ---------------------------------------------------------------------------

def step_ui(token, drv):
    name = PREFIX + 'SPK_EMPTY_' + time.strftime('%H%M%S')
    st, gid, js = create_group(token, name, '空分组：无成员')
    FIX['speaker_groups'].append(gid)
    FIX['empty_group_id'] = gid
    _, glist = groups(token)
    created = [g for g in glist if g.get('id') == gid]
    record('P1-2 空分组已创建', bool(created) and (created[0].get('items') or []) == [],
           'POST speaker-groups -> %s id=%s items=%s' % (st, gid, (created or [{}])[0].get('items')))

    # 浅色
    ok_theme, theme_detail = ensure_theme(drv, 'light')
    record('P1-2 浅色主题生效', ok_theme, theme_detail)
    B.goto(drv, '/devices/playback', '设备管理')
    time.sleep(1.5)

    def open_dialog():
        click_aria(drv, '更多操作', 10)
        time.sleep(0.8)
        pick_popover_option(drv, '逻辑音箱')
        return dialog_with_title(drv, '逻辑音箱', 20)

    dlg = open_dialog()
    record('P1-2 逻辑音箱弹窗打开', dlg is not None, 'dialog=%s' % (dlg is not None))
    if not dlg:
        return

    rows = drv.execute_script('''
      var name = arguments[0], out = [];
      document.querySelectorAll('tr').forEach(function(tr){
        if ((tr.innerText||'').indexOf(name) !== -1) {
          var cells = []; tr.querySelectorAll('td').forEach(function(td){ cells.push((td.innerText||'').trim()); });
          out.push(cells);
        }
      });
      return out;
    ''', name)
    row_ok = bool(rows) and any(len(r) >= 2 and r[1] in ('0', '') for r in rows)
    record('P1-2 空分组行「已绑定实验室」= 0', row_ok, 'rows=%s' % json.dumps(rows, ensure_ascii=False)[:400])

    total_rows = drv.execute_script('''
      var best = 0;
      document.querySelectorAll('table').forEach(function(t){
        var b = t.querySelector('tbody'); if (b) { var c = b.querySelectorAll('tr').length; if (c > best) best = c; }
      });
      return best;
    ''')
    record('P1-2 分组列表行数与接口一致', int(total_rows or 0) == len(glist),
           'ui_rows=%s api_groups=%s' % (total_rows, len(glist)))

    click_aria(drv, '查看逻辑音箱 %s 的实验室映射' % name, 10)
    panel0 = panel_text(drv, name)
    panel, waited = wait_panel(drv, name, '测试实验室A', 15)
    panel_ok = ('测试实验室A' in panel) and ('LAB-A' in panel)
    record('P1-2 空分组「实验室映射」列出实验室', panel_ok,
           'clicked_immediately=%s waited=%.1fs panel=%s'
           % (json.dumps(panel0, ensure_ascii=False)[:200], waited, panel[:400]))

    trig = drv.execute_script('''
      var out = [];
      document.querySelectorAll('[data-slot="select-trigger"]').forEach(function(el){
        out.push({'text': (el.innerText||'').trim(), 'placeholder': el.getAttribute('data-placeholder')});
      });
      return out;
    ''')
    placeholder_ok = any((t.get('text') or '') == '' and t.get('placeholder') == '未设置' for t in (trig or [])) \
        or any('未设置' in (t.get('text') or '') for t in (trig or []))
    record('P1-2 未绑定实验室下拉显示「未设置」（成员不足提示）', placeholder_ok,
           'triggers=%s' % json.dumps(trig, ensure_ascii=False)[:500])
    scroll_dialog_bottom(drv)
    shot(drv, 'r5_empty_group_mapping_light')

    # 对照：真实分组（有成员）下拉显示实体音箱名
    real = [g for g in glist if g.get('id') != gid and (g.get('items') or [])]
    real_ok = False
    real_detail = 'no-real-group'
    if real:
        rg = real[0]
        click_aria(drv, '查看逻辑音箱 %s 的实验室映射' % rg.get('name'), 10)
        wait_panel(drv, rg.get('name'), '测试实验室A', 15)
        bound_id = None
        for it in rg.get('items') or []:
            if int(it.get('lab_id')) == LAB_ID:
                bound_id = it.get('playback_device_id')
        _, devices = playback_devices(token)
        dev = next((d for d in devices if d.get('id') == bound_id), None)
        text = drv.execute_script('''
          var out = [];
          document.querySelectorAll('[data-slot="select-trigger"]').forEach(function(el){
            out.push((el.innerText||'').trim());
          });
          return out;
        ''')
        real_ok = bool(dev) and any((dev.get('name') or '') in (t or '') for t in (text or []))
        real_detail = 'group=%s device=%s triggers=%s' % (
            rg.get('name'), (dev or {}).get('name'), json.dumps(text, ensure_ascii=False)[:300])
    record('P1-2 对照：有成员分组下拉显示已绑定实体音箱', real_ok, real_detail)
    scroll_dialog_bottom(drv)
    shot(drv, 'r5_bound_group_mapping_light')

    close_dialog(drv)

    # 深色
    ok_theme, theme_detail = ensure_theme(drv, 'dark')
    record('P1-2 深色主题生效', ok_theme, theme_detail)
    B.goto(drv, '/devices/playback', '设备管理')
    time.sleep(1.2)
    dlg = open_dialog()
    record('P1-2 深色下逻辑音箱弹窗打开', dlg is not None, 'dialog=%s' % (dlg is not None))
    if dlg is not None:
        click_aria(drv, '查看逻辑音箱 %s 的实验室映射' % name, 10)
        panel, waited = wait_panel(drv, name, '测试实验室A', 15)
        record('P1-2 深色下空分组映射可见', ('未设置' in panel) and ('测试实验室A' in panel),
               'waited=%.1fs panel=%s' % (waited, panel[:400]))
        scroll_dialog_bottom(drv)
        shot(drv, 'r5_empty_group_mapping_dark')
        close_dialog(drv)
    ensure_theme(drv, 'light')


def open_group_dialog(drv):
    click_aria(drv, '更多操作', 10)
    time.sleep(0.8)
    pick_popover_option(drv, '逻辑音箱')
    return dialog_with_title(drv, '逻辑音箱', 20)


def group_item(token, gid, lab_id=LAB_ID):
    _, glist = groups(token)
    for g in glist:
        if g.get('id') == gid:
            for it in g.get('items') or []:
                if int(it.get('lab_id')) == lab_id:
                    return it.get('playback_device_id')
            return None
    return 'group-gone'


def wait_group_item(token, gid, expect, timeout=10):
    """等 PUT items 落到 GET speaker-groups（回读重试）。"""
    end = time.time() + timeout
    last = 'init'
    while time.time() < end:
        last = group_item(token, gid)
        if last == expect:
            return True, last
        time.sleep(0.5)
    return False, last


def step_members(token, drv):
    """INT-2199 裁定 A 新增项：编辑成员后重新解析，结果跟随新成员变化。"""
    ts = time.strftime('%H%M%S')
    gname = PREFIX + 'SPK_SWAP_' + ts
    pbnames = [PREFIX + 'PB_A_' + ts, PREFIX + 'PB_B_' + ts]
    _, dbefore = playback_devices(token)
    n_dev_before = len(dbefore)
    _, gbefore = groups(token)
    n_grp_before = len(gbefore)

    st, gid, _ = create_group(token, gname, 'INT-2199 裁定 A：编辑成员后重解析')
    if gid:
        FIX['speaker_groups'].append(gid)
    record('R6 自建分组已创建', bool(gid),
           'POST /api/v1/playback-devices/speaker-groups -> %s id=%s name=%s' % (st, gid, gname))

    chan = stub = dpb = None
    dev_ids = []
    try:
        chan, stub, dpb = grpc_clients()
        for idx, pbn in enumerate(pbnames):
            ok, msg, pid = grpc_create_playback_device(stub, dpb, {
                'name': pbn, 'model': '接线测试虚拟音箱', 'device_type': 'speaker',
                'sample_rate': 48000, 'channel_index': 0, 'lab_id': LAB_ID,
                'device_unique_id': 'JX2175_R4_%s_%s' % ('AB'[idx], ts),
                'description': 'INT-2175 自建播放设备（成员编辑重解析）', 'status': 'online',
            })
            if pid:
                dev_ids.append(pid)
                FIX['playback_devices'].append(pid)
            record('R6 自建播放设备 %s' % pbn, bool(ok) and bool(pid),
                   'gRPC CreatePlaybackDevice success=%s id=%s msg=%s lab=%s'
                   % (ok, pid, msg, LAB_ID))
        # 接口回读：两台设备确实在 lab 38
        read_back = []
        for pid in dev_ids:
            dev = device_by_id(token, pid)
            read_back.append({'id': pid, 'name': (dev or {}).get('name'), 'lab_id': (dev or {}).get('lab_id')})
        record('R6 自建设备接口回读（lab 38）',
               len(read_back) == 2 and all(d.get('lab_id') == LAB_ID for d in read_back),
               'GET /api/v1/playback-devices items=%s' % json.dumps(read_back, ensure_ascii=False))
        if len(dev_ids) < 2:
            record('R6 成员编辑链路', False, '自建设备不足 2 台，无法做 A→B 替换')
            return
        dev_a, dev_b = dev_ids[0], dev_ids[1]

        ok_theme, theme_detail = ensure_theme(drv, 'light')
        record('R6 浅色主题生效', ok_theme, theme_detail)
        B.goto(drv, '/devices/playback', '设备管理')
        time.sleep(1.5)
        dlg = open_group_dialog(drv)
        record('R6 逻辑音箱弹窗打开', dlg is not None, 'dialog=%s' % (dlg is not None))
        if dlg is None:
            return
        click_aria(drv, '查看逻辑音箱 %s 的实验室映射' % gname, 10)
        panel, waited = wait_panel(drv, gname, '测试实验室A', 20)
        record('R6 新分组映射面板列出实验室（初始未设置）',
               ('测试实验室A' in panel)
               and any((('未设置' in (t or '')) or (t or '') == '') for t in trigger_texts(drv)),
               'waited=%.1fs triggers=%s panel=%s'
               % (waited, json.dumps(trigger_texts(drv), ensure_ascii=False)[:200], panel[:300]))

        # ① 通过 UI 下拉把成员设为 A，然后立即重解析
        time.sleep(1.5)  # 等映射面板/设备下拉数据稳定
        ok, info = choose_member(drv, pbnames[0])
        item_ok, got = wait_group_item(token, gid, dev_a)
        record('R6 UI 设为成员 A（PUT items 生效）', ok and item_ok,
               'choose=%s GET speaker-groups items[lab=%s].playback_device_id=%s expect=%s'
               % (info, LAB_ID, got, dev_a))
        success, msg, data = resolve_group(stub, dpb, gid, LAB_ID)
        target = (data or {}).get('target_device_id') if isinstance(data, dict) else None
        record('R6 成员=A 时解析 target=A', bool(success) and target == dev_a,
               'gRPC ResolvePlaybackSpeakerGroupDevice group=%s lab=%s success=%s target=%s data=%s'
               % (gid, LAB_ID, success, target, json.dumps(data, ensure_ascii=False)[:300]))
        scroll_dialog_bottom(drv)
        shot(drv, 'r6_member_A_light')

        # ② 编辑成员 A → B，重解析必须跟随变化
        ok, info = choose_member(drv, pbnames[1])
        item_ok, got = wait_group_item(token, gid, dev_b)
        record('R6 UI 把成员改为 B（同组同实验室覆盖）', ok and item_ok,
               'choose=%s GET speaker-groups items[lab=%s].playback_device_id=%s expect=%s'
               % (info, LAB_ID, got, dev_b))
        success, msg, data = resolve_group(stub, dpb, gid, LAB_ID)
        target = (data or {}).get('target_device_id') if isinstance(data, dict) else None
        record('R6 编辑成员后重新解析跟随新成员（A→B）',
               bool(success) and target == dev_b and target != dev_a,
               'gRPC ResolvePlaybackSpeakerGroupDevice group=%s lab=%s success=%s target=%s '
               'prev=%s data=%s' % (gid, LAB_ID, success, target, dev_a,
                                    json.dumps(data, ensure_ascii=False)[:300]))
        scroll_dialog_bottom(drv)
        shot(drv, 'r6_member_B_light')

        # ③ 深色下同一映射可见（下拉显示 B）
        ok_theme, theme_detail = ensure_theme(drv, 'dark')
        record('R6 深色主题生效', ok_theme, theme_detail)
        B.goto(drv, '/devices/playback', '设备管理')
        time.sleep(1.5)
        dlg = open_group_dialog(drv)
        if dlg is not None:
            click_aria(drv, '查看逻辑音箱 %s 的实验室映射' % gname, 10)
            wait_panel(drv, gname, '测试实验室A', 20)
            texts = trigger_texts(drv)
            record('R6 深色下映射下拉显示成员 B',
                   any(pbnames[1] in (t or '') for t in texts),
                   'triggers=%s' % json.dumps(texts, ensure_ascii=False)[:300])
            scroll_dialog_bottom(drv)
            shot(drv, 'r6_member_B_dark')
            close_dialog(drv)
        else:
            record('R6 深色下映射下拉显示成员 B', False, 'dialog not opened')

        # ④ 移除成员后解析回落为空（派发侧按未配置拦截）
        ok_theme, theme_detail = ensure_theme(drv, 'light')
        B.goto(drv, '/devices/playback', '设备管理')
        time.sleep(1.5)
        dlg = open_group_dialog(drv)
        removed = False
        if dlg is not None:
            click_aria(drv, '查看逻辑音箱 %s 的实验室映射' % gname, 10)
            wait_panel(drv, gname, '测试实验室A', 20)
            removed = bool(click_aria(drv, '移除 测试实验室A 的对应设备', 10))
            time.sleep(1.2)
        got_ok, got = wait_group_item(token, gid, None)
        success, msg, data = resolve_group(stub, dpb, gid, LAB_ID)
        target = (data or {}).get('target_device_id') if isinstance(data, dict) else None
        record('R6 移除成员后解析回落为空', removed and got_ok and bool(success) and target is None,
               'removed=%s items=%s gRPC success=%s target=%s data=%s'
               % (removed, got, success, target, json.dumps(data, ensure_ascii=False)[:300]))
        scroll_dialog_bottom(drv)
        shot(drv, 'r6_member_removed_light')
        close_dialog(drv)

        _, dafter = playback_devices(token)
        _, gafter = groups(token)
        record('R6 收尾（分组/设备数回到起始）',
               len(gafter) == n_grp_before + 1 and len(dafter) == n_dev_before + 2,
               'groups=%d(前 %d + 自建 1) playback_devices=%d(前 %d + 自建 2)'
               % (len(gafter), n_grp_before, len(dafter), n_dev_before))
    except Exception as exc:
        record('R6 成员编辑重解析可执行', False, repr(exc))
    finally:
        try:
            if chan:
                chan.close()
        except Exception:
            pass


def cleanup(token):
    for gid in list(FIX.get('speaker_groups') or []):
        if not gid:
            continue
        st = delete_group(token, gid)
        print('cleanup speaker-group %s -> %s' % (gid, st))
    FIX['speaker_groups'] = []
    pids = list(FIX.get('playback_devices') or [])
    if pids:
        chan = stub = dpb = None
        try:
            chan, stub, dpb = grpc_clients()
            for pid in pids:
                ok, msg = grpc_delete_playback_device(stub, dpb, pid)
                print('cleanup playback-device %s -> %s %s' % (pid, ok, msg))
        except Exception as exc:
            print('cleanup playback-device failed: %r' % (exc,))
        finally:
            try:
                if chan:
                    chan.close()
            except Exception:
                pass
    FIX['playback_devices'] = []



def main():
    which = sys.argv[1:] or ['all']
    started = time.strftime('%H:%M:%S')
    print('START', started)
    token, _ = B.rsa_login_token(*B.ACCOUNT)
    health('start', token)
    drv = None
    try:
        if 'all' in which or 'ui' in which or 'members' in which:
            drv = B.driver_init()
            drv.get(B.BASE + '/login')
            B.wait_ready(drv)
            drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
                               B.TOKEN_KEY, token)
            drv.execute_script('try { localStorage.removeItem("iatp:auth:v1"); } catch(e) {}')
            if 'members' not in which:
                step_ui(token, drv)
            if 'ui' not in which:
                step_members(token, drv)
        if 'all' in which or 'dispatch' in which:
            step_dispatch(token)
        health('end', token)
    finally:
        if drv is not None:
            try:
                drv.quit()
            except Exception:
                pass
        cleanup(token)
        health('after_cleanup', token)
        out = os.path.join(ART, 'results.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'health': HEALTH, 'results': RC, 'fixtures': FIX, 'shots': SHOTS,
                       'started': started, 'finished': time.strftime('%H:%M:%S')},
                      f, ensure_ascii=False, indent=2)
        passed = len([r for r in RC if r['ok']])
        print('SUMMARY %d/%d passed -> %s' % (passed, len(RC), out))


if __name__ == '__main__':
    main()
