# -*- coding: utf-8 -*-
"""INT-1494 /ai-chat 深走查（服务商管理弹窗 CRUD + 模型切换 + 真实会话链路）。

LLM 供应商是「用户自配、浏览器直连」的第三方依赖，平台侧无该配置（红线④不接平台后端）。
本脚本在 127.0.0.1:18899 起一个 OpenAI 兼容契约桩（GET /v1/models、POST
/v1/chat/completions），验证前端真实发出请求体、渲染真实回复；桩只作为外部供应商替身，
不改变平台业务数据。

记录：请求体、响应渲染、弹窗各字段、回读 localStorage、增改删。
"""
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from int1494_helpers import (ARTIFACTS, BASE, body_text, clear_perf, driver,
                             goto, js_click, result, requests_simple,
                             set_theme, shot)

PORT = 18899
SEEN = []
SLOW = {'on': False}
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
            body = json.dumps({'data': [{'id': 'stub-model-a'}, {'id': 'stub-model-b'}]}).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            SEEN.append({'method': 'GET', 'path': self.path,
                         'auth': self.headers.get('Authorization')})
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n).decode('utf-8', 'replace')
        SEEN.append({'method': 'POST', 'path': self.path, 'body': raw,
                     'auth': self.headers.get('Authorization')})
        if SLOW['on']:
            time.sleep(6)
        body = json.dumps({'choices': [{'message': {
            'content': '接线测试_INT1494 桩回复：已收到你的指令，当前为契约桩验证。'}}]}).encode()
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


BASE_URL = 'http://127.0.0.1:%d/v1' % PORT
PROVIDER = '接线测试_LLM供应商'


def find_btn(d, *texts, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        for b in d.find_elements(By.CSS_SELECTOR, 'button, [role=button], a'):
            try:
                t = ((b.text or '') + ' ' + (b.get_attribute('aria-label') or '')).strip()
            except Exception:
                continue
            for want in texts:
                if want in t and b.is_displayed():
                    return b
        time.sleep(0.3)
    return None


def wait_text(d, text, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if text in body_text(d):
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def main():
    srv = start_stub()
    d = driver()
    try:
        set_theme(d, 'light')
        clear_perf(d)
        goto(d, '/ai-chat', wait_text='灵犀Agent')
        time.sleep(3)
        txt = body_text(d)
        state = {'empty_text': txt[:600],
                 'has_report_selector': ('报告上下文' in txt) or ('选择报告' in txt)}
        state['api'] = requests_simple(d, '/')[:12]
        shots = [shot(d, 'aichat_empty_light')]

        # 1) 打开供应商管理（空态整钮 → 管理弹窗）
        trig = find_btn(d, '未配置', '管理供应商', '添加供应商', 'LLM')
        if trig is None:
            trig = wait_until(d, "//*[@role='combobox']")
        if trig is not None:
            js_click(d, trig)
            time.sleep(1.5)
        opened = wait_text(d, 'LLM 供应商管理', 8)
        state['manager_opened'] = opened
        shots.append(shot(d, 'aichat_manager_open_light'))
        if not opened:
            # 二次尝试：直接点 combobox
            cb = d.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            if cb:
                js_click(d, cb[0])
                time.sleep(1.2)
                mg = find_btn(d, '管理供应商', '配置')
                if mg:
                    js_click(d, mg)
                    time.sleep(1.2)
                opened = wait_text(d, 'LLM 供应商管理', 8)
                state['manager_opened'] = opened

        if opened:
            add = find_btn(d, '添加供应商')
            if add:
                js_click(d, add)
                time.sleep(1)
            name = d.find_element(By.ID, 'provider-name')
            bu = d.find_element(By.ID, 'provider-base-url')
            key = d.find_element(By.ID, 'provider-api-key')
            # 必填留空校验
            sv = find_btn(d, '保存')
            if sv:
                js_click(d, sv)
                time.sleep(1)
                state['empty_save_blocked'] = '名称' in body_text(d) and (
                    '必填' in body_text(d) or '请填写' in body_text(d))
            name.send_keys(PROVIDER)
            bu.send_keys(BASE_URL)
            key.send_keys('sk-int1494-test')
            time.sleep(0.4)
            shots.append(shot(d, 'aichat_manager_form_light'))
            # 测试连接（真实 GET /models）
            tc = find_btn(d, '测试连接')
            if tc:
                js_click(d, tc)
                time.sleep(3)
                state['test_connection_toast'] = '连接成功' in body_text(d) or '2 个模型' in body_text(d)
            fm = find_btn(d, '自动获取模型列表')
            if fm:
                js_click(d, fm)
                time.sleep(3)
            # 模型列表行（自动回填）
            model_vals = [i.get_attribute('value') for i in
                          d.find_elements(By.CSS_SELECTOR, 'input[placeholder="如 gpt-4o"]')]
            state['models_after_fetch'] = model_vals
            sv = find_btn(d, '保存')
            if sv:
                js_click(d, sv)
                time.sleep(1.5)
            state['after_save_has_provider'] = PROVIDER in body_text(d)
            state['ls_providers'] = d.execute_script(
                "return window.localStorage.getItem('iatp:ai-chat:v1:providers');")
            shots.append(shot(d, 'aichat_manager_saved_light'))

            # 2) 编辑回读
            ed = find_btn(d, '编辑')
            if ed:
                js_click(d, ed)
                time.sleep(1.2)
                state['edit_prefill'] = {
                    'name': d.find_element(By.ID, 'provider-name').get_attribute('value'),
                    'base': d.find_element(By.ID, 'provider-base-url').get_attribute('value'),
                    'key': d.find_element(By.ID, 'provider-api-key').get_attribute('value'),
                }
                nm = d.find_element(By.ID, 'provider-name')
                nm.send_keys(Keys.CONTROL, 'a')
                nm.send_keys(Keys.DELETE)
                nm.send_keys(PROVIDER + '_改')
                sv = find_btn(d, '保存')
                if sv:
                    js_click(d, sv)
                    time.sleep(1.2)
                state['after_edit'] = (PROVIDER + '_改') in body_text(d)
            # 关闭弹窗
            close = d.find_elements(By.CSS_SELECTOR, "[aria-label='关闭'], button[aria-label='Close']")
            if close:
                js_click(d, close[-1])
            else:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.2)

        # 3) 模型切换器
        cb = d.find_elements(By.CSS_SELECTOR, "[role='combobox']")
        switcher = {'combobox_count': len(cb)}
        if cb:
            js_click(d, cb[0])
            time.sleep(1.2)
            opts = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, '[role=option], button') if o.text.strip()]
            switcher['options_sample'] = opts[:15]
            for o in d.find_elements(By.CSS_SELECTOR, '[role=option], button'):
                if 'stub-model-b' in (o.text or ''):
                    js_click(d, o)
                    time.sleep(1)
                    switcher['selected'] = 'stub-model-b'
                    break
            else:
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            shots.append(shot(d, 'aichat_switcher_light'))
        state['switcher'] = switcher

        # 4) 真实发送（桩，stream:false）
        ta = d.find_element(By.CSS_SELECTOR, 'textarea')
        ta.click()
        ta.send_keys('接线测试_INT1494：请回复一句确认')
        time.sleep(0.5)
        before = len(SEEN)
        ta.send_keys(Keys.ENTER)
        wait_text(d, '桩回复', 25)
        time.sleep(2)
        state['reply_rendered'] = '桩回复' in body_text(d)
        state['stub_seen'] = SEEN[before:]
        shots.append(shot(d, 'aichat_reply_light'))

        # 5) 清空对话（确认弹窗）
        clr = find_btn(d, '清空对话')
        if clr:
            js_click(d, clr)
            time.sleep(1)
            ok = find_btn(d, '清空', '确认')
            for b in d.find_elements(By.CSS_SELECTOR, 'button'):
                if (b.text or '').strip() in ('清空', '确认', '确定') and b.is_displayed():
                    js_click(d, b)
                    state['clear_confirmed'] = True
                    break
            time.sleep(1.5)
            state['after_clear'] = '桩回复' not in body_text(d)
        shots.append(shot(d, 'aichat_after_clear_light'))

        # 6) 删除供应商 + 回读
        trig = find_btn(d, '未配置', '管理供应商', 'LLM')
        if trig is not None:
            js_click(d, trig)
            time.sleep(1.2)
        if wait_text(d, 'LLM 供应商管理', 6):
            dl = find_btn(d, '删除')
            if dl:
                js_click(d, dl)
                time.sleep(1.2)
                for b in d.find_elements(By.CSS_SELECTOR, 'button'):
                    if (b.text or '').strip() in ('删除', '确认', '确定') and b.is_displayed():
                        js_click(d, b)
                        break
                time.sleep(1.5)
            state['after_delete_has_provider'] = (PROVIDER in body_text(d))
            state['ls_after_delete'] = d.execute_script(
                "return window.localStorage.getItem('iatp:ai-chat:v1:providers');")
        # 恢复现场：清掉本卡写进 localStorage 的供应商
        d.execute_script("window.localStorage.removeItem('iatp:ai-chat:v1:providers');")

        # 7) 深色
        set_theme(d, 'dark')
        goto(d, '/ai-chat', wait_text='灵犀Agent')
        time.sleep(2.5)
        shots.append(shot(d, 'aichat_empty_dark'))
        state['dark_html_class'] = d.execute_script(
            "return document.documentElement.className;")

        R.append(result('ai_chat', bool(state.get('manager_opened')) and
                        state.get('reply_rendered', False), state, shots))
    except Exception as exc:
        R.append(result('ai_chat', False, 'EXC %r' % (exc,)))
        traceback.print_exc()
    finally:
        d.quit()
        srv.shutdown()


def wait_until(d, xpath, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        els = d.find_elements(By.XPATH, xpath)
        if els:
            return els[0]
        time.sleep(0.3)
    return None


if __name__ == '__main__':
    main()
    with open(os.path.join(ARTIFACTS, 'int1494_aichat.json'), 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print(json.dumps(R, ensure_ascii=False, indent=2)[:6000])
