# -*- coding: utf-8 -*-
"""INT-1494 第三轮打回复测（代码审计 P2-1/P2-2/P2-3/P3-4）。

P2-1 ① 空态「全能力分组」11 域逐卡点名：工具数 Badge / 待接入徽标 / 可执行态 / 权限门控，
     浅深各两段（首屏 + 滚到底）。
P2-2 ① 会话内交互：发送 / 重新生成（截断重建请求体）/ 编辑（保存·保存并重发·重置·取消+
     beforeunload 守卫）/ 删除 / 消息错误态（重试·编辑后重发）/ 停止；工具卡、文档变更卡、
     文档面板、新建会话 逐项确认可达性并留下源码裁定依据。
P2-3 ⑩ 错误页返回/重试入口真实点击并断言落地 URL。
P3-4 补拍 aichat_after_clear_light、about_to_guide_light。

LLM 供应商为浏览器直连的第三方依赖（平台侧无该配置），本脚本在 127.0.0.1:18899 起
OpenAI 兼容契约桩，仅作外部供应商替身；桩可切 ok / error(500) / slow 三态。
数据卫生：只写浏览器 localStorage（iatp:ai-chat:v1:*），结束全部清空；不连库、不写测试库。
"""
import json
import os
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from int1494_helpers import (ARTIFACTS, BASE, body_text, driver, goto, js_click,
                             result, set_theme, shot)

PORT = 18899
BASE_URL = 'http://127.0.0.1:%d/v1' % PORT
PROVIDER_ID = 'p-int1494'
PROVIDER_NAME = '接线测试_LLM供应商'
MODEL = 'stub-model-a'

MODE = {'v': 'ok'}
CALLS = []
REPLY_N = {'n': 0}
R = []


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/v1/models'):
            body = json.dumps({'data': [{'id': MODEL}, {'id': 'stub-model-b'}]}).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n).decode('utf-8', 'replace')
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        msgs = payload.get('messages') or []
        CALLS.append({
            'path': self.path,
            'model': payload.get('model'),
            'stream': payload.get('stream'),
            'message_count': len(msgs),
            'roles': [m.get('role') for m in msgs],
            'last_user': next((m.get('content') for m in reversed(msgs)
                               if m.get('role') == 'user'), None),
            'auth': self.headers.get('Authorization'),
            'mode': MODE['v'],
        })
        if MODE['v'] == 'slow':
            time.sleep(8)
        if MODE['v'] == 'error':
            body = json.dumps({'error': {'message': '接线测试_INT1494 桩 500'}}).encode()
            try:
                self.send_response(500)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        REPLY_N['n'] += 1
        content = '接线测试_INT1494 桩回复#%d：已收到你的指令，当前为契约桩验证。' % REPLY_N['n']
        body = json.dumps({'choices': [{'message': {'content': content}}]}).encode()
        try:
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass


def start_stub():
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------------------------------------------------------------- helpers
def wait_for(fn, timeout=20, interval=0.3):
    end = time.time() + timeout
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception:
            pass
        time.sleep(interval)
    return None


def wait_text(d, text, timeout=20):
    return bool(wait_for(lambda: text in body_text(d), timeout))


def find_btn(d, label, contains=False, scope=None):
    root = scope or d
    for b in root.find_elements(By.CSS_SELECTOR, 'button, [role=button], a'):
        try:
            t = ((b.text or '') + ' ' + (b.get_attribute('aria-label') or '')).strip()
        except Exception:
            continue
        hit = (label in t) if contains else (t == label or
                                             b.get_attribute('aria-label') == label)
        if hit and b.is_displayed():
            return b
    return None


def wait_btn(d, label, contains=False, timeout=15):
    return wait_for(lambda: find_btn(d, label, contains), timeout)


def msg_containers(d):
    return [m for m in d.find_elements(By.CSS_SELECTOR, 'div.group.flex-row-reverse')
            if m.is_displayed()]


def msg_texts(d):
    out = []
    for m in msg_containers(d):
        try:
            out.append((m.text or '').strip())
        except Exception:
            out.append('')
    return out


def last_assistant(d):
    msgs = msg_containers(d)
    return msgs[-1] if msgs else None


def in_msg_btn(msg, label):
    if msg is None:
        return None
    for b in msg.find_elements(By.CSS_SELECTOR, '[aria-label]'):
        if b.get_attribute('aria-label') == label:
            return b
    return None


def send_text(d, text):
    ta = d.find_element(By.CSS_SELECTOR, "textarea[placeholder^='描述你的报告需求']")
    ta.click()
    ta.send_keys(Keys.CONTROL, 'a')
    ta.send_keys(Keys.DELETE)
    ta.send_keys(text)
    ta.send_keys(Keys.ENTER)


def clear_chat_storage(d):
    d.execute_script(
        "['iatp:ai-chat:v1:config','iatp:ai-chat:v1:messages','iatp:ai-chat:v1:providers']"
        ".forEach(function(k){window.localStorage.removeItem(k);});")


def seed_provider(d):
    d.execute_script("""
        window.localStorage.setItem('iatp:ai-chat:v1:providers', JSON.stringify({version:1,data:[{
            id: arguments[0], name: arguments[1], baseUrl: arguments[2],
            apiKey: 'sk-int1494-test', models: [arguments[3]], isDefault: true}]}));
        window.localStorage.setItem('iatp:ai-chat:v1:config', JSON.stringify({version:1,data:{
            providerId: arguments[0], modelId: arguments[3]}}));
    """, PROVIDER_ID, PROVIDER_NAME, BASE_URL, MODEL)


def scroll_chat_bottom(d):
    return d.execute_script("""
        var el = Array.prototype.slice.call(document.querySelectorAll('div'))
          .filter(function(e){return e.scrollHeight > e.clientHeight + 40;})
          .filter(function(e){return (e.innerText||'').indexOf('全能力分组') >= 0;})[0];
        if (!el) return null;
        el.scrollTop = el.scrollHeight;
        return {scrollTop: el.scrollTop, scrollHeight: el.scrollHeight,
                clientHeight: el.clientHeight, cls: String(el.className).slice(0, 60)};
    """)


def read_cards(d):
    return d.execute_script("""
        var cont = Array.prototype.slice.call(document.querySelectorAll('div'))
          .filter(function(e){return e.scrollHeight > e.clientHeight + 40;})
          .filter(function(e){return (e.innerText||'').indexOf('全能力分组') >= 0;})[0];
        var cr = cont ? cont.getBoundingClientRect()
                      : {top: 0, bottom: window.innerHeight};
        return Array.prototype.slice.call(document.querySelectorAll('div'))
          .filter(function(el){
            var c = String(el.className || '');
            return c.indexOf('rounded-lg') >= 0 && c.indexOf('p-3') >= 0 &&
                   c.indexOf('text-left') >= 0 && el.querySelector('span.text-sm');
          })
          .map(function(el){
            var r = el.getBoundingClientRect();
            return {text: el.innerText.replace(/\\n/g, ' | '),
                    top: Math.round(r.top), bottom: Math.round(r.bottom),
                    inView: r.top >= cr.top - 1 && r.bottom <= cr.bottom + 1,
                    hasButton: !!el.querySelector('button'),
                    pending: (el.innerText || '').indexOf('待接入') >= 0};
          });
    """)


def read_starters(d):
    return d.execute_script("""
        return Array.prototype.slice.call(document.querySelectorAll('button'))
          .map(function(b){return String(b.textContent || '').trim();})
          .filter(function(t){
            return ['生成测试报告','对比多份报告','解读报告指标','追问报告数据']
                     .indexOf(t) >= 0;});
    """)


EXPECTED = [
    ('工作台（系统概览）', 2, False),
    ('音频导入（音频导入+标注）', 5, False),
    ('用例管理（用例生成/编辑+标签）', 14, False),
    ('评估维度（评估维度配置）', 5, False),
    ('算法配置（算法配置管理）', 5, False),
    ('任务域（任务执行+控制）', 7, False),
    ('SPL 校准（声压级校准）', 4, False),
    ('设备（播放设备管理+设备驱动生成）', 6, False),
    ('日志诊断', 4, False),
    ('报告域（结果分析+报告+报告对比）', 9, False),
    ('系统设置（配置域（OAuth/系统配置））', None, True),
]


# ---------------------------------------------------------------- P2-1
def test_empty_state():
    d = driver()
    shots, state = [], {}
    try:
        set_theme(d, 'light')
        goto(d, '/ai-chat', wait_text='灵犀Agent')
        clear_chat_storage(d)
        goto(d, '/ai-chat', wait_text='开始与灵犀Agent对话')
        time.sleep(2)
        state['light_raw_cards'] = read_cards(d)
        state['starters'] = read_starters(d)

        # 常用入门四卡 + 回填不发送（点击须在滚动前，滚动后首屏卡不在容器视口内）
        calls_before = len(CALLS)
        st = find_btn(d, '生成测试报告', contains=True)
        if st is not None:
            js_click(d, st)
            time.sleep(0.8)
            state['starter_filled'] = d.find_element(
                By.CSS_SELECTOR, "textarea[placeholder^='描述你的报告需求']").get_attribute('value')
            state['starter_sent'] = len(CALLS) != calls_before
            shots.append(shot(d, 'r4_empty_starter_fill_light'))
            ta = d.find_element(By.CSS_SELECTOR, "textarea[placeholder^='描述你的报告需求']")
            ta.send_keys(Keys.CONTROL, 'a')
            ta.send_keys(Keys.DELETE)

        shots.append(shot(d, 'r4_empty_light_top'))
        state['light_scroll'] = scroll_chat_bottom(d)
        time.sleep(0.6)
        state['light_cards_after_scroll'] = read_cards(d)
        shots.append(shot(d, 'r4_empty_light_bottom'))

        # 深色：同源 reload 保持主题
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark');")
        goto(d, '/ai-chat', wait_text='开始与灵犀Agent对话')
        time.sleep(1.5)
        state['dark_html_class'] = d.execute_script('return document.documentElement.className;')
        state['dark_body_bg'] = d.execute_script(
            'return getComputedStyle(document.body).backgroundColor;')
        shots.append(shot(d, 'r4_empty_dark_top'))
        state['dark_scroll'] = scroll_chat_bottom(d)
        time.sleep(0.6)
        state['dark_cards_after_scroll'] = read_cards(d)
        shots.append(shot(d, 'r4_empty_dark_bottom'))
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")

        # 逐卡核对
        cards = state['light_cards_after_scroll'] or state['light_raw_cards'] or []
        found, problems = [], []
        for label, tool_count, pending in EXPECTED:
            hit = next((c for c in cards if (c['text'] or '').startswith(label)), None)
            if hit is None:
                problems.append('MISSING %s' % label)
                found.append({'label': label, 'found': False})
                continue
            m = re.search(r'(\d+)\s*工具', hit['text'])
            actual_count = int(m.group(1)) if m else None
            rec = {'label': label, 'found': True, 'toolCount': actual_count,
                   'pending': hit['pending'], 'hasButton': hit['hasButton'],
                   'text': hit['text']}
            found.append(rec)
            if tool_count is not None and actual_count != tool_count:
                problems.append('COUNT %s expect %s got %s' % (label, tool_count, actual_count))
            if tool_count is None and actual_count is not None:
                problems.append('COUNT %s expect — got %s' % (label, actual_count))
            if bool(hit['pending']) != pending:
                problems.append('BADGE %s expect pending=%s got %s' % (label, pending, hit['pending']))
            if pending and hit['hasButton']:
                problems.append('EXEC %s 待接入卡却渲染了可执行按钮' % label)
            if (not pending) and (not hit['hasButton']):
                problems.append('EXEC %s 可执行域缺快捷指令按钮' % label)
        state['cards'] = found
        state['problems'] = problems
        state['card_count'] = len(cards)
        state['visible_before_scroll'] = sum(1 for c in (state['light_raw_cards'] or []) if c['inView'])
        state['visible_after_scroll'] = sum(1 for c in cards if c['inView'])
        state['starters_ok'] = sorted(state['starters']) == sorted(
            ['生成测试报告', '对比多份报告', '解读报告指标', '追问报告数据'])
        passed = (len(cards) == 11 and not problems and state['starters_ok']
                  and not state.get('starter_sent', True)
                  and 'dark' in (state['dark_html_class'] or ''))
        R.append(result('P2-1 aichat_empty_11_domains', passed, state, shots))
    except Exception as exc:
        R.append(result('P2-1 aichat_empty_11_domains', False, 'EXC %r' % (exc,), shots))
        traceback.print_exc()
    finally:
        try:
            clear_chat_storage(d)
        except Exception:
            pass
        d.quit()


# ---------------------------------------------------------------- P2-2
def open_editor(d, msg):
    btn = in_msg_btn(msg, '编辑')
    if btn is None:
        return None
    js_click(d, btn)
    return wait_for(lambda: d.find_elements(
        By.CSS_SELECTOR, "textarea[placeholder='编辑消息内容…']"), 8)


def editor_textarea(d):
    els = d.find_elements(By.CSS_SELECTOR, "textarea[placeholder='编辑消息内容…']")
    return els[0] if els else None


def type_editor(d, text):
    ta = editor_textarea(d)
    ta.click()
    ta.send_keys(Keys.CONTROL, 'a')
    ta.send_keys(Keys.DELETE)
    ta.send_keys(text)
    time.sleep(0.4)


def editor_btn(d, label):
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == label and b.is_displayed():
            return b
    return None


def test_session():
    d = driver()
    shots, st = [], {}
    try:
        set_theme(d, 'light')
        goto(d, '/ai-chat', wait_text='灵犀Agent')
        clear_chat_storage(d)
        seed_provider(d)
        goto(d, '/ai-chat', wait_text='开始与灵犀Agent对话')
        time.sleep(2)

        # ---- 1) 发送
        before = len(CALLS)
        send_text(d, '接线测试_INT1494_消息A')
        wait_text(d, '桩回复#1', 25)
        time.sleep(1.5)
        st['send_calls'] = len(CALLS) - before
        st['send_request'] = CALLS[-1] if len(CALLS) > before else None
        msgs = msg_texts(d)
        st['messages_after_send'] = msgs
        shots.append(shot(d, 'r4_session_reply_light'))

        # ---- 2) 重新生成（截断重建：请求体只含 system + 原 user）
        target = last_assistant(d)
        btn = in_msg_btn(target, '重新生成')
        before = len(CALLS)
        st['regenerate_button'] = btn is not None
        if btn is not None:
            js_click(d, btn)
            wait_for(lambda: len(CALLS) > before, 15)
            wait_text(d, '桩回复#2', 25)
            time.sleep(1.5)
            st['regenerate_calls'] = len(CALLS) - before
            st['regenerate_request'] = CALLS[-1] if len(CALLS) > before else None
            st['messages_after_regenerate'] = msg_texts(d)
            shots.append(shot(d, 'r4_session_regenerate_light'))

        # ---- 3) 编辑消息（操作组只挂在 assistant 气泡上；user 气泡无操作组，见下 unreachable）
        user_msg = next((m for m in msg_containers(d) if '消息A' in (m.text or '')), None)
        st['user_message_actions'] = {
            'aria_labels': [x.get_attribute('aria-label') for x in
                            user_msg.find_elements(By.CSS_SELECTOR, '[aria-label]')]
            if user_msg is not None else None,
            'buttons': [(b.text or '').strip() for b in
                        user_msg.find_elements(By.CSS_SELECTOR, 'button')]
            if user_msg is not None else None,
        }
        target = last_assistant(d)
        st['editor_open'] = open_editor(d, target) is not None
        if st['editor_open']:
            time.sleep(0.6)
            ta = editor_textarea(d)
            st['editor_initial'] = {
                'value': ta.get_attribute('value'),
                'title_shown': d.execute_script(
                    "return !!Array.prototype.slice.call(document.querySelectorAll('span'))"
                    ".find(function(s){return s.textContent.trim()==='编辑' &&"
                    " String(s.className).indexOf('font-semibold')>=0;});"),
                'hint': '暂无更改' in body_text(d),
                'save_resend_shown': editor_btn(d, '保存并重发') is not None,
                'reset_shown': editor_btn(d, '重置') is not None,
            }
            shots.append(shot(d, 'r4_session_editor_open_light'))

            type_editor(d, '接线测试_INT1494_消息A_编辑')
            time.sleep(0.5)
            st['editor_changed'] = {
                'hint': '有未保存的更改' in body_text(d),
                'save_resend_shown': editor_btn(d, '保存并重发') is not None,
                'reset_shown': editor_btn(d, '重置') is not None,
            }
            st['beforeunload_prevented'] = d.execute_script(
                "var e=new Event('beforeunload',{cancelable:true});"
                "window.dispatchEvent(e);"
                "return [e.defaultPrevented, e.returnValue];")
            shots.append(shot(d, 'r4_session_editor_changed_light'))

            # 重置
            rb = editor_btn(d, '重置')
            if rb is not None:
                js_click(d, rb)
                time.sleep(0.6)
                st['reset_restored'] = editor_textarea(d).get_attribute('value')
                st['reset_hint'] = '暂无更改' in body_text(d)

            # 取消（无改动 → 直接关）
            cb = editor_btn(d, '取消')
            if cb is not None:
                js_click(d, cb)
                time.sleep(0.5)
                st['cancel_no_change_closed'] = editor_textarea(d) is None

            # 再开 + 改动 + 取消 → 离开确认
            open_editor(d, last_assistant(d))
            time.sleep(0.5)
            type_editor(d, '接线测试_INT1494_消息A_放弃')
            time.sleep(0.4)
            cb = editor_btn(d, '取消')
            if cb is not None:
                js_click(d, cb)
                time.sleep(0.8)
                st['leave_confirm'] = {
                    'alertdialog': len(d.find_elements(By.CSS_SELECTOR, "[role='alertdialog']")) > 0,
                    'title': '放弃未保存的更改？' in body_text(d),
                    'stay': editor_btn(d, '留在此页') is not None,
                    'leave': editor_btn(d, '离开') is not None,
                }
                shots.append(shot(d, 'r4_session_editor_leave_confirm_light'))
                stay = editor_btn(d, '留在此页')
                if stay is not None:
                    js_click(d, stay)
                    time.sleep(0.8)
                    st['stay_keeps_editor'] = editor_textarea(d) is not None
                cb = editor_btn(d, '取消')
                if cb is not None:
                    js_click(d, cb)
                    time.sleep(0.8)
                leave = editor_btn(d, '离开')
                if leave is not None:
                    js_click(d, leave)
                    time.sleep(0.8)
                st['leave_closes_editor'] = editor_textarea(d) is None
                st['messages_after_cancel_edit'] = msg_texts(d)

        # ---- 4) 保存（不重发：不产生新请求，正文就地更新）
        before = len(CALLS)
        if open_editor(d, last_assistant(d)) is not None:
            time.sleep(0.5)
            type_editor(d, '接线测试_INT1494_消息A_已保存')
            time.sleep(0.4)
            sb = editor_btn(d, '保存')
            if sb is not None:
                js_click(d, sb)
                time.sleep(1)
            st['save_no_resend'] = {
                'calls': len(CALLS) - before,
                'editor_closed': editor_textarea(d) is None,
                'messages': msg_texts(d),
            }

        # ---- 5) 保存并重发（产生新请求）
        user_msg = next((m for m in msg_containers(d) if '已保存' in (m.text or '')), None)
        before = len(CALLS)
        if open_editor(d, user_msg) is not None:
            time.sleep(0.5)
            type_editor(d, '接线测试_INT1494_消息B_重发')
            time.sleep(0.4)
            sb = editor_btn(d, '保存并重发')
            st['save_resend_button'] = sb is not None
            if sb is not None:
                js_click(d, sb)
                wait_for(lambda: len(CALLS) > before, 15)
                time.sleep(2.5)
            st['save_resend'] = {
                'calls': len(CALLS) - before,
                'request': CALLS[-1] if len(CALLS) > before else None,
                'messages': msg_texts(d),
            }
            shots.append(shot(d, 'r4_session_save_resend_light'))

        # ---- 6) 删除消息（最后一条 assistant）
        before_count = len(msg_containers(d))
        target = last_assistant(d)
        db = in_msg_btn(target, '删除')
        st['delete_button'] = db is not None
        if db is not None:
            js_click(d, db)
            time.sleep(1)
        st['delete'] = {'before': before_count, 'after': len(msg_containers(d))}

        # ---- 7) 消息错误态 + 重试 + 编辑后重发
        MODE['v'] = 'error'
        before = len(CALLS)
        send_text(d, '接线测试_INT1494_错误态')
        wait_text(d, '出错了', 25)
        time.sleep(1.5)
        st['error_state'] = {
            'alert': '出错了' in body_text(d),
            'retry': find_btn(d, '重试', contains=True) is not None,
            'edit_resend': find_btn(d, '编辑后重发', contains=True) is not None,
            'delete': find_btn(d, '删除', contains=False) is not None,
            'detail_has_500': 'HTTP 500' in body_text(d),
            'messages': msg_texts(d),
        }
        shots.append(shot(d, 'r4_session_error_state_light'))
        before = len(CALLS)
        rb = find_btn(d, '重试', contains=True)
        if rb is not None:
            js_click(d, rb)
            wait_for(lambda: len(CALLS) > before, 15)
            time.sleep(1.5)
        st['retry_calls'] = len(CALLS) - before
        er = find_btn(d, '编辑后重发', contains=True)
        if er is not None:
            js_click(d, er)
            time.sleep(1)
            ta = editor_textarea(d)
            st['edit_resend_opens_editor'] = ta is not None
            st['edit_resend_value'] = ta.get_attribute('value') if ta is not None else None
            shots.append(shot(d, 'r4_session_error_edit_resend_light'))
            cb = editor_btn(d, '取消')
            if cb is not None:
                js_click(d, cb)
                time.sleep(0.8)
        MODE['v'] = 'ok'

        # ---- 8) 停止生成
        before = len(CALLS)
        MODE['v'] = 'slow'
        send_text(d, '接线测试_INT1494_停止')
        stop = wait_btn(d, '停止', contains=True, timeout=10)
        st['stop_button'] = stop is not None
        if stop is not None:
            time.sleep(0.8)
            shots.append(shot(d, 'r4_session_stop_light'))
            js_click(d, stop)
            time.sleep(1.2)
        st['after_stop'] = {
            'stop_gone': find_btn(d, '停止', contains=True) is None,
            'calls': len(CALLS) - before,
            'messages': msg_texts(d),
        }
        MODE['v'] = 'ok'
        time.sleep(1.5)

        # ---- 9) 清空对话（P3-4 补图）
        clr = find_btn(d, '清空对话', contains=True)
        st['clear_button'] = clr is not None
        if clr is not None:
            js_click(d, clr)
            time.sleep(1)
            ok = editor_btn(d, '清空')
            if ok is not None:
                js_click(d, ok)
                time.sleep(1.5)
            st['after_clear'] = {
                'messages': len(msg_containers(d)),
                'empty_state': '开始与灵犀Agent对话' in body_text(d),
            }
            shots.append(shot(d, 'aichat_after_clear_light'))

        # ---- 10) 不可达项（工具卡/文档变更卡/文档面板/新建会话）
        st['unreachable'] = {
            'toolcard_in_dom': '已完成' in body_text(d) and '工具' in body_text(d),
            'docchange_in_dom': '文档已更新' in body_text(d),
            'work_mode_button': find_btn(d, '报告工作模式', contains=True) is not None,
            'new_session_button': find_btn(d, '新建对话', contains=True) is not None or
                                  find_btn(d, '新建会话', contains=True) is not None,
            'report_context_selector': find_btn(d, '报告上下文', contains=True) is not None,
        }

        # ---- 区间统计
        st['all_calls'] = CALLS
        core_ok = (
            st.get('send_calls') == 1
            and (st.get('send_request') or {}).get('message_count') == 2
            and st.get('regenerate_calls') == 1
            and (st.get('regenerate_request') or {}).get('message_count') == 2
            and st.get('editor_open')
            and st['editor_changed']['save_resend_shown']
            and st['beforeunload_prevented'][0] is True
            and st.get('cancel_no_change_closed')
            and st['leave_confirm']['alertdialog']
            and st.get('stay_keeps_editor')
            and st.get('leave_closes_editor')
            and st['save_no_resend']['calls'] == 0
            and st['save_resend']['calls'] == 1
            and st['delete']['after'] == st['delete']['before'] - 1
            and st['error_state']['alert']
            and st['error_state']['retry']
            and st['error_state']['edit_resend']
            and st.get('retry_calls') == 1
            and st.get('edit_resend_opens_editor')
            and st.get('stop_button')
            and st['after_stop']['stop_gone']
            and st['after_clear']['empty_state']
        )
        R.append(result('P2-2 aichat_session_interactions', bool(core_ok), st, shots))
    except Exception as exc:
        R.append(result('P2-2 aichat_session_interactions', False, 'EXC %r' % (exc,), st))
        traceback.print_exc()
    finally:
        try:
            d.execute_script(
                "['iatp:ai-chat:v1:config','iatp:ai-chat:v1:messages','iatp:ai-chat:v1:providers']"
                ".forEach(function(k){window.localStorage.removeItem(k);});")
        except Exception:
            pass
        d.quit()


# ---------------------------------------------------------------- P2-3 + P3-4
def test_errors_and_about():
    d = driver()
    shots, st = [], {}
    try:
        set_theme(d, 'light')

        def click_and_land(path, label, timeout=8):
            goto(d, path)
            time.sleep(1.2)
            b = find_btn(d, label)
            if b is None:
                return {'path': path, 'button': label, 'found': False,
                        'before': d.current_url}
            js_click(d, b)
            time.sleep(timeout / 2)
            try:
                wait_for(lambda: d.current_url.rstrip('/') != (BASE + path), timeout)
            except Exception:
                pass
            return {'path': path, 'button': label, 'found': True,
                    'url': d.current_url.replace(BASE, '')}

        st['401_login'] = click_and_land('/401', '去登录')
        st['403_home'] = click_and_land('/403', '返回主页')
        st['404_home'] = click_and_land('/404', '返回主页')
        st['500_reload'] = click_and_land('/500', '刷新页面')
        st['503_home'] = click_and_land('/503', '返回主页')

        # 返回（history.go(-1)）：先到 /about 再进程内跳 /404
        goto(d, '/about', wait_text='关于')
        time.sleep(1)
        goto(d, '/404')
        time.sleep(1.2)
        b = find_btn(d, '返回')
        if b is not None:
            js_click(d, b)
            time.sleep(2)
        st['404_back'] = {'found': b is not None,
                          'url': d.current_url.replace(BASE, '')}

        # 403 切换账号（登出 → /login）
        goto(d, '/403')
        time.sleep(1.2)
        b = find_btn(d, '切换账号')
        if b is not None:
            js_click(d, b)
            time.sleep(3)
        st['403_switch'] = {'found': b is not None,
                            'url': d.current_url.replace(BASE, '')}

        # 错误页深浅截图（500 浅 / 401 深，作本轮代表帧）
        goto(d, '/500')
        time.sleep(1)
        shots.append(shot(d, 'r4_error_500_light'))
        goto(d, '/401')
        time.sleep(1)
        shots.append(shot(d, 'r4_error_401_light'))
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark');")
        goto(d, '/500')
        time.sleep(1)
        st['dark_html_class'] = d.execute_script('return document.documentElement.className;')
        shots.append(shot(d, 'r4_error_500_dark'))
        d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','light');")

        # P3-4 关于页 → API 手册链接（补拍缺图）
        goto(d, '/about', wait_text='关于智能语音测试平台')
        time.sleep(2)
        tgt = None
        for a in d.find_elements(By.CSS_SELECTOR, 'a[href]'):
            if (a.text or '').strip() == 'API 手册':
                tgt = a
                break
        st['about_guide_link'] = tgt is not None
        if tgt is not None:
            st['about_link_href'] = tgt.get_attribute('href')
            js_click(d, tgt)
            time.sleep(3)
            st['about_after_click_url'] = d.current_url.replace(BASE, '')
            shots.append(shot(d, 'about_to_guide_light'))

        # 注：AUTH_MODE=off 下 /login 对已注入的 dev_user 直接重定向 /dashboard
        # （既有环境行为，见 wiring-login-page-reload-redirect-quirk），故 401「去登录」
        # 判「离开 /401 且落到登录页或登录后的首页」。
        ok = (st['401_login'].get('url', '') in ('/login', '/dashboard')
              and st['403_home'].get('url', '') in ('/', '/dashboard')
              and st['404_home'].get('url', '') in ('/', '/dashboard')
              and st['500_reload'].get('url', '') == '/500'
              and st['503_home'].get('url', '') in ('/', '/dashboard')
              and st['404_back'].get('url') in ('/', '/dashboard', '/about')
              and st['403_switch'].get('url', '').startswith('/login')
              and st['about_after_click_url'] == '/user-guide-api'
              and 'dark' in (st.get('dark_html_class') or ''))
        R.append(result('P2-3 errors_actions + P3-4 missing_shots', bool(ok), st, shots))
    except Exception as exc:
        R.append(result('P2-3 errors_actions + P3-4 missing_shots', False, 'EXC %r' % (exc,), st))
        traceback.print_exc()
    finally:
        d.quit()


if __name__ == '__main__':
    srv = start_stub()
    try:
        test_empty_state()
        test_session()
        test_errors_and_about()
    finally:
        srv.shutdown()
    with open(os.path.join(ARTIFACTS, 'int1494_round4.json'), 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print(json.dumps(R, ensure_ascii=False, indent=2)[:12000])
