# -*- coding: utf-8 -*-
"""INT-1939 验收：api-edit 弹窗保存失败仍关闭并丢弃五页签输入（P2）+ 最大并发内联校验（P3）。

环境：docker 真实栈（后端 :15000，库 intelligent_audio_test）。前端不用共享 15173（镜像
19:23Z 构建，早于交付 commit c65258050 19:38Z），改用本 run 从交付 commit 导出源码构建的
旁路 nginx 容器（15279；A/B 对照侧 15280 = wiring/react 头 c75ee868c 同法构建）。

失败注入走 nginx 开关文件（真实网络 500 信封，不是页内 fetch 伪造）：
    /flag/fail_api 存在时 location ~ ^/api/v1/apis(/|$) 直接 return 500
    {"success":false,"code":203,"message":"INT-1939 注入的保存失败"}
页内只保留 fetch 打点（window.__netlog）用于「校验失败时没有发出 PUT」这类断言。

用法：
    python verify_int1939_api_edit.py fixed      # 交付侧：期望全部 PASS
    python verify_int1939_api_edit.py base       # 对照侧：期望复现缺陷（弹窗关闭、无内联提示）
环境变量：INT1939_BASE / INT1939_CONTAINER / INT1939_ART
"""
import os
import re
import subprocess
import sys
import time
import json
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

MODE = (sys.argv[1] if len(sys.argv) > 1 else 'fixed').lower()
BASE = os.environ.get(
    'INT1939_BASE', 'http://127.0.0.1:15280' if MODE == 'base' else 'http://127.0.0.1:15279'
)
CONTAINER = os.environ.get(
    'INT1939_CONTAINER', 'iat-int1939-base' if MODE == 'base' else 'iat-int1939-verify'
)
LOGIN_USER = '接线测试_admin'
LOGIN_PASS = 'JieXianTest@2026'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.environ.get('INT1939_ART') or os.path.join(HERE, 'artifacts', 'int1939')
os.makedirs(ART, exist_ok=True)

NAME_A = '接线测试_INT1939_API'
NAME_B = '接线测试_INT1939_API_改'
NAME_D = '接线测试_INT1939_API_深色'
HDR_KEY = 'X-INT1939'
HDR_VAL = 'save-fail-keep-draft'
MAXPROC_MSG = '请输入 1~128 的整数'

CHECKS = []
SHOTS = []
CREATED = {'id': None}
TOKEN = {'v': None}


def check(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + str(detail)[:200] if detail else ''))
    return ok


# ---------------------------------------------------------------- driver / login
FETCH_WRAP_JS = r"""
(function(){
  if (window.__netlog) return;
  window.__netlog = [];
  var orig = window.fetch;
  window.fetch = function(input, init){
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var args = arguments;
    return orig.apply(this, args).then(function(res){
      try { window.__netlog.push({url: url, method: method, status: res.status}); } catch(e){}
      return res;
    }, function(err){
      try { window.__netlog.push({url: url, method: method, status: 'ERR:' + err}); } catch(e){}
      throw err;
    });
  };
})();
"""

LOGIN_JS = r"""
return (async () => {
  const keyResp = await fetch('/api/v1/auth/login/encryption-key').then(r=>r.json());
  const d = keyResp.data || keyResp;
  if(!d.enabled) return {step:'disabled'};
  const pem = d.public_key.replace(/-----[^-]+-----/g,'').replace(/\s+/g,'');
  const bin = Uint8Array.from(atob(pem), c=>c.charCodeAt(0));
  const key = await crypto.subtle.importKey('spki', bin, {name:'RSA-OAEP', hash:'SHA-256'}, false, ['encrypt']);
  const enc = await crypto.subtle.encrypt({name:'RSA-OAEP'}, key, new TextEncoder().encode(arguments[0]));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(enc)));
  const body = new URLSearchParams({username: arguments[1], password_encrypted: b64, encryption_key_id: d.kid});
  const r = await fetch('/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  const txt = await r.text();
  let j = {}; try { j = JSON.parse(txt); } catch(e) {}
  if (r.ok && j.access_token) localStorage.setItem('iatp:auth:token:v1', j.access_token);
  return {status: r.status, token: j.access_token || null, body: r.ok ? 'ok' : txt.slice(0,300)};
})()
"""


def make_driver(w=1680, h=1400):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=%d,%d' % (w, h))
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(120)
    d.set_script_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_WRAP_JS})
    return d


def login(drv):
    drv.set_script_timeout(120)
    res = {}
    for _ in range(3):
        try:
            drv.get(BASE + '/login')
            time.sleep(4)
            res = drv.execute_script(LOGIN_JS, LOGIN_PASS, LOGIN_USER)
            if res.get('token'):
                break
        except Exception:
            time.sleep(2)
    TOKEN['v'] = res.get('token')
    print('LOGIN', res.get('status'), bool(res.get('token')))
    if not TOKEN['v']:
        raise RuntimeError('登录失败：%s' % res.get('body'))


# ---------------------------------------------------------------- page helpers
def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def set_input(drv, selector, value, index=-1):
    """React 受控输入：原生 setter + input 事件（send_keys 清空不触发 onChange）。"""
    return drv.execute_script(
        """
        var els = document.querySelectorAll(arguments[0]);
        if (!els.length) return false;
        var el = arguments[2] >= 0 ? els[arguments[2]] : els[els.length - 1];
        var proto = (el.tagName === 'TEXTAREA') ? window.HTMLTextAreaElement.prototype
                                                : window.HTMLInputElement.prototype;
        var desc = Object.getOwnPropertyDescriptor(proto, 'value');
        desc.set.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
        """,
        selector, value, index,
    )


def visible_dialogs(drv):
    out = []
    for d in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
        try:
            if d.is_displayed():
                out.append(d)
        except Exception:
            pass
    return out


def dialog(drv):
    ds = visible_dialogs(drv)
    return ds[-1] if ds else None


def dialog_title(drv):
    d = dialog(drv)
    return text_of(drv, d)[:120] if d else ''


def click_in(scope, drv, css='button', label=None, must=True):
    for el in scope.find_elements(By.CSS_SELECTOR, css):
        try:
            if not el.is_displayed():
                continue
            txt = text_of(drv, el)
            if label is None or txt == label or (label and label in txt):
                js_click(drv, el)
                return el
        except Exception:
            pass
    if must:
        raise RuntimeError('找不到按钮：%s' % label)
    return None


def tab(drv, label):
    d = dialog(drv)
    if not d:
        return False
    for el in d.find_elements(By.CSS_SELECTOR, "[role='tab'], button"):
        try:
            if not el.is_displayed():
                continue
            if text_of(drv, el) == label:
                js_click(drv, el)
                time.sleep(0.3)
                return True
        except Exception:
            pass
    return False


def save_btn_state(drv):
    return drv.execute_script(
        """
        var ds = document.querySelectorAll("[role='dialog']");
        for (var i = ds.length - 1; i >= 0; i--) {
          if (!ds[i].offsetParent && ds[i].getClientRects().length === 0) continue;
          var b = ds[i].querySelector("button[type='submit']");
          if (b) return {text: (b.textContent || '').trim(), disabled: !!b.disabled};
        }
        return null;
        """
    )


def toast_texts(drv):
    return drv.execute_script(
        """return Array.from(document.querySelectorAll('[data-sonner-toast]'))
              .map(function(t){ return (t.textContent || '').trim(); });"""
    )


def netlog(drv, method=None):
    rows = drv.execute_script("return (window.__netlog || []).slice();") or []
    if method:
        rows = [r for r in rows if r.get('method') == method]
    return rows


def inpage_fetch(drv, method, path, body=None):
    return drv.execute_async_script(
        """
        var cb = arguments[arguments.length - 1];
        var method = arguments[0], path = arguments[1], body = arguments[2];
        var token = localStorage.getItem('iatp:auth:token:v1');
        var opt = {method: method, headers: {}};
        if (token) opt.headers['Authorization'] = 'Bearer ' + token;
        if (body !== null && body !== undefined) {
          opt.headers['Content-Type'] = 'application/json';
          opt.body = JSON.stringify(body);
        }
        fetch(path, opt).then(function(r){
          return r.text().then(function(t){
            var j = null; try { j = JSON.parse(t); } catch(e) {}
            cb({status: r.status, body: j, raw: j ? null : t.slice(0, 300)});
          });
        }, function(e){ cb({status: 0, err: String(e)}); });
        """,
        method, path, body,
    )


def shot(drv, name):
    drv.execute_script(
        "window.scrollTo(0,0);"
        "document.querySelectorAll('*').forEach(function(e){"
        "  if (e.scrollTop > 0 && e.scrollHeight > e.clientHeight + 20) e.scrollTop = 0;"
        "});"
    )
    time.sleep(0.4)
    p = os.path.join(ART, MODE + '_' + name + '.png')
    drv.save_screenshot(p)
    SHOTS.append(p)
    print('SHOT', os.path.basename(p))


# ---------------------------------------------------------------- domain actions
def flag(cmd):
    subprocess.run(['docker', 'exec', CONTAINER, cmd, '/flag/fail_api'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def probe_flag(state):
    """开关是否真的让 GET /api/v1/apis 回 500（真实网络层）。"""
    try:
        with urllib.request.urlopen(BASE + '/api/v1/apis?per_page=1', timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return 'ERR:%s' % e


def open_page(drv, theme=None):
    if theme:
        drv.get(BASE + '/login')
        time.sleep(1.5)
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
        drv.get('about:blank')
        time.sleep(0.3)
    drv.get(BASE + '/start-test?step=1')
    for _ in range(30):
        time.sleep(1)
        if drv.execute_script("return document.body.innerText.indexOf('被测 API') >= 0;"):
            break
    time.sleep(2)


def find_api_card(drv, name):
    els = drv.find_elements(By.XPATH, "//*[normalize-space(text())='%s']" % name)
    for el in els:
        try:
            card = el.find_element(
                By.XPATH, "./ancestor::div[.//button[@aria-label='更多操作']][1]"
            )
            return card
        except Exception:
            continue
    return None


def open_edit_dialog(drv, name):
    card = find_api_card(drv, name)
    if not card:
        raise RuntimeError('列表里找不到 API 卡片：%s' % name)
    btn = card.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']")
    js_click(drv, btn)
    time.sleep(0.8)
    for el in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem'], [role='option']"):
        try:
            if el.is_displayed() and text_of(drv, el) == '编辑':
                js_click(drv, el)
                time.sleep(1.2)
                return True
        except Exception:
            pass
    # 兜底：按文本找可见「编辑」
    for el in drv.find_elements(By.XPATH, "//*[normalize-space(text())='编辑']"):
        try:
            if el.is_displayed():
                js_click(drv, el)
                time.sleep(1.2)
                return True
        except Exception:
            pass
    return False


def add_header(drv, key, val):
    d = dialog(drv)
    click_in(d, drv, 'button', '添加请求头')
    time.sleep(0.5)
    set_input(drv, "[role='dialog'] input[aria-label='请求头名称']", key)
    set_input(drv, "[role='dialog'] input[aria-label='请求头值']", val)
    time.sleep(0.3)


def header_rows(drv):
    return drv.execute_script(
        """
        var d = document.querySelectorAll("[role='dialog']");
        if (!d.length) return [];
        var last = d[d.length - 1];
        var ks = last.querySelectorAll("input[aria-label='请求头名称']");
        var vs = last.querySelectorAll("input[aria-label='请求头值']");
        var out = [];
        for (var i = 0; i < ks.length; i++) out.push([ks[i].value, vs[i] ? vs[i].value : null]);
        return out;
        """
    )


def click_save(drv):
    d = dialog(drv)
    if not d:
        raise RuntimeError('弹窗已消失，无法点保存')
    b = d.find_element(By.CSS_SELECTOR, "button[type='submit']")
    js_click(drv, b)


def wait_toast(drv, needle, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for t in toast_texts(drv):
            if needle in t:
                return t
        time.sleep(0.25)
    return None


def latency(drv, ms):
    try:
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': ms,
            'downloadThroughput': -1, 'uploadThroughput': -1,
        })
    except Exception as exc:
        print('LATENCY_ERR', exc)


# ---------------------------------------------------------------- main
def main():
    drv = make_driver()
    result = {'mode': MODE, 'base': BASE, 'container': CONTAINER, 'checks': CHECKS, 'shots': SHOTS}
    try:
        login(drv)

        create = inpage_fetch(drv, 'POST', '/api/v1/apis', {
            'name': NAME_A,
            'vendor': '接线测试',
            'description': 'INT-1939 验收临时记录（run 结束删除）',
            'algorithm_type': 'voice_llm',
            'device_type': 'http_api',
            'default_max_process': 5,
            'default_max_timeout': 30,
            'default_max_audio_duration': 60,
            'endpoints': [{
                'endpoint': 'http://127.0.0.1:1',
                'name': 'int1939-local',
                'max_process': 2,
                'max_timeout': 30,
                'max_audio_duration': 60,
                'status': 'online',
                'priority': 1,
                'description': '',
            }],
            'meta': {'protocol': 'http'},
        })
        print('CREATE', create)
        CREATED['id'] = (create.get('body') or {}).get('id') if create.get('status') in (200, 201) else None
        if isinstance((create.get('body') or {}).get('data'), dict):
            CREATED['id'] = create['body']['data'].get('id')
        # 兼容信封
        if isinstance((create.get('body') or {}).get('data'), int):
            CREATED['id'] = create['body']['data']
        check('自建验收 API 记录', CREATED['id'] is not None, 'id=%s status=%s' % (CREATED['id'], create.get('status')))
        if CREATED['id'] is None:
            raise RuntimeError('创建测试 API 失败：%s' % create)

        open_page(drv)
        check('步骤二列出「被测 API」区块', drv.execute_script(
            "return document.body.innerText.indexOf('个可执行 API') >= 0;"))
        check('列表中可见自建记录', find_api_card(drv, NAME_A) is not None, NAME_A)

        if not open_edit_dialog(drv, NAME_A):
            raise RuntimeError('打不开编辑弹窗')
        check('编辑弹窗打开', '编辑 API' in dialog_title(drv), dialog_title(drv))

        # 基础页签改名 + 请求模板页签加请求头（制造五页签草稿）
        set_input(drv, '#api-name', NAME_B, index=0)
        time.sleep(0.3)
        check('基础页签改名草稿', drv.execute_script(
            "return document.querySelector('#api-name').value === arguments[0];", NAME_B))
        check('切到请求模板页签', tab(drv, '请求模板'))
        add_header(drv, HDR_KEY, HDR_VAL)
        rows = header_rows(drv)
        check('请求模板页签新增请求头草稿', any(r[0] == HDR_KEY and r[1] == HDR_VAL for r in rows), rows)

        # ---- 失败注入（真实 nginx 500）+ 慢网看保存中状态
        flag('touch')
        st = probe_flag('on')
        check('失败开关生效（GET /apis → 500，真实网络）', st == 500, 'status=%s' % st)
        latency(drv, 2000)
        puts_before = len(netlog(drv, 'PUT'))
        click_save(drv)

        seen_loading = False
        for _ in range(20):
            s = save_btn_state(drv)
            if s and s.get('text') == '保存中…' and s.get('disabled'):
                seen_loading = True
                break
            time.sleep(0.1)
        toast = wait_toast(drv, '保存失败', timeout=25)
        latency(drv, 0)
        time.sleep(0.5)

        d_after = dialog(drv)
        dialog_open = d_after is not None and '编辑 API' in dialog_title(drv)
        rows_after = header_rows(drv)
        puts_after = len(netlog(drv, 'PUT'))
        check('保存中按钮文案「保存中…」且禁用', seen_loading, save_btn_state(drv))
        check('失败后 toast「保存失败：…」可见', bool(toast), toast)
        check('失败后弹窗保持打开', dialog_open, 'dialogs=%d title=%s' % (len(visible_dialogs(drv)), dialog_title(drv)))
        check('失败后请求模板请求头草稿仍在',
              any(r[0] == HDR_KEY and r[1] == HDR_VAL for r in rows_after), rows_after)
        check('失败确实发出了 PUT（不是空转）', puts_after > puts_before,
              'put=%d→%d' % (puts_before, puts_after))
        if dialog_open:
            shot(drv, 'L1a_save_fail_request')
            tab(drv, '基础')
        name_value = drv.execute_script(
            "var e=document.querySelector('#api-name'); return e ? e.value : null;")
        check('失败后基础页签改名草稿仍在', name_value == NAME_B, 'value=%s' % name_value)
        if dialog_open:
            shot(drv, 'L1b_save_fail_basic')

        if MODE == 'base':
            # 对照侧：缺陷形态（弹窗已关、草稿丢失、无内联提示）
            check('[对照] 失败后弹窗已关闭（缺陷复现）', not dialog_open)
            check('[对照] 弹窗关闭导致改名草稿丢失', name_value != NAME_B, 'value=%s' % name_value)
            shot(drv, 'base_fail_dialog_closed')
            flag('rm')
            # 重新打开弹窗，核对 P3：留空 / 200 都没有中文内联提示（原生气泡 / 静默）
            if open_edit_dialog(drv, NAME_A):
                set_input(drv, '#max-process', '')
                time.sleep(0.3)
                puts_pre_b = len(netlog(drv, 'PUT'))
                click_save(drv)
                time.sleep(1.5)
                msg_empty = drv.execute_script(
                    """var d = document.querySelectorAll("[role='dialog']");
                       var last = d[d.length - 1];
                       return last ? (last.innerText || '').indexOf(arguments[0]) >= 0 : false;""",
                    MAXPROC_MSG)
                puts_b = len(netlog(drv, 'PUT'))
                check('[对照] 最大并发留空 → 无中文内联提示（缺陷形态）', not msg_empty, msg_empty)
                check('[对照] 最大并发留空 → 静默未发 PUT', puts_b == puts_pre_b,
                      'put=%d→%d' % (puts_pre_b, puts_b))
                set_input(drv, '#max-process', '200')
                time.sleep(0.3)
                click_save(drv)
                time.sleep(1.5)
                msg_200 = drv.execute_script(
                    """var d = document.querySelectorAll("[role='dialog']");
                       var last = d[d.length - 1];
                       return last ? (last.innerText || '').indexOf(arguments[0]) >= 0 : false;""",
                    MAXPROC_MSG)
                check('[对照] 最大并发 200 → 无中文内联提示（缺陷形态）', not msg_200, msg_200)
                shot(drv, 'base_maxprocess_no_inline')
            return result

        # ---- 恢复正常后端，保存钮可再次点击
        flag('rm')
        st2 = probe_flag('off')
        check('撤销开关后 GET /apis 恢复 200', st2 == 200, 'status=%s' % st2)
        s = save_btn_state(drv)
        check('失败后保存钮恢复可点', bool(s) and not s.get('disabled') and s.get('text') == '保存', s)

        # ---- P3：最大并发内联校验（留空 / 200）
        check('切回基础页签', tab(drv, '基础'))
        set_input(drv, '#max-process', '')
        time.sleep(0.3)
        puts_pre = len(netlog(drv, 'PUT'))
        click_save(drv)
        time.sleep(1.2)
        info = drv.execute_script(
            """
            var d = document.querySelectorAll("[role='dialog']");
            var last = d[d.length - 1];
            var el = last ? last.querySelector('#max-process') : null;
            var box = last ? (last.innerText || '') : '';
            return {ariaInvalid: el ? el.getAttribute('aria-invalid') : null,
                    hasMsg: box.indexOf(arguments[0]) >= 0,
                    dlgOpen: !!last};
            """, MAXPROC_MSG)
        puts_post = len(netlog(drv, 'PUT'))
        check('最大并发留空 → 中文内联提示', info.get('hasMsg'), info)
        check('最大并发留空 → aria-invalid=true', info.get('ariaInvalid') == 'true', info)
        check('最大并发留空 → 未发出 PUT', puts_post == puts_pre, 'put=%d→%d' % (puts_pre, puts_post))
        check('最大并发留空 → 弹窗仍打开', info.get('dlgOpen'))

        set_input(drv, '#max-process', '200')
        time.sleep(0.3)
        click_save(drv)
        time.sleep(1.2)
        info2 = drv.execute_script(
            """
            var d = document.querySelectorAll("[role='dialog']");
            var last = d[d.length - 1];
            var el = last ? last.querySelector('#max-process') : null;
            var box = last ? (last.innerText || '') : '';
            return {ariaInvalid: el ? el.getAttribute('aria-invalid') : null,
                    hasMsg: box.indexOf(arguments[0]) >= 0};
            """, MAXPROC_MSG)
        puts_after200 = len(netlog(drv, 'PUT'))
        check('最大并发 200 → 中文内联提示', info2.get('hasMsg'), info2)
        check('最大并发 200 → aria-invalid=true', info2.get('ariaInvalid') == 'true', info2)
        check('最大并发 200 → 未发出 PUT', puts_after200 == puts_pre, 'put=%d→%d' % (puts_pre, puts_after200))
        shot(drv, 'L2_maxprocess_200_light')

        # ---- 改回合法值 → 保存成功关窗 + 列表刷新
        set_input(drv, '#max-process', '16')
        time.sleep(0.3)
        click_save(drv)
        ok_toast = wait_toast(drv, 'API 已保存', timeout=30)
        for _ in range(20):
            if not dialog(drv):
                break
            time.sleep(0.5)
        closed = dialog(drv) is None
        check('合法值保存成功 → toast「API 已保存」', bool(ok_toast), ok_toast)
        check('保存成功 → 弹窗关闭', closed, dialog_title(drv))
        list_ok = False
        for _ in range(20):
            time.sleep(1)
            if find_api_card(drv, NAME_B) is not None:
                list_ok = True
                break
        check('保存成功 → 列表刷新出现新名称', list_ok, NAME_B)
        verify = inpage_fetch(drv, 'GET', '/api/v1/apis?per_page=1000')
        items = ((verify.get('body') or {}).get('data') or {}).get('items') or []
        rec = next((x for x in items if x.get('id') == CREATED['id']), None)
        rec = rec.get('data') if isinstance(rec, dict) and isinstance(rec.get('data'), dict) else rec
        check('接口回读：名称已更新', bool(rec) and (rec.get('name') == NAME_B), rec.get('name') if rec else None)
        check('接口回读：default_max_process=16',
              bool(rec) and rec.get('default_max_process') == 16,
              rec.get('default_max_process') if rec else None)
        hdrs = ((rec or {}).get('meta') or {}).get('headers') if isinstance((rec or {}).get('meta'), dict) else None
        hdr_ok = False
        if isinstance(hdrs, dict):
            hdr_ok = hdrs.get(HDR_KEY) == HDR_VAL
        elif isinstance(hdrs, list):
            hdr_ok = any(
                (h.get('key') == HDR_KEY or h.get('name') == HDR_KEY)
                and (h.get('value') == HDR_VAL) for h in hdrs if isinstance(h, dict))
        check('接口回读：请求头写入 meta', hdr_ok, hdrs)
        shot(drv, 'L3_save_success_list')

        # ---- 深色复跑同一失败序列 + 校验
        open_page(drv, theme='dark')
        is_dark = drv.execute_script(
            "return document.documentElement.classList.contains('dark') || "
            "(getComputedStyle(document.body).backgroundColor.indexOf('rgb(2') === 0);")
        check('深色主题生效', bool(is_dark), is_dark)
        if not open_edit_dialog(drv, NAME_B):
            raise RuntimeError('深色下打不开编辑弹窗')
        set_input(drv, '#api-name', NAME_D, index=0)
        tab(drv, '请求模板')
        add_header(drv, HDR_KEY + '-D', 'dark-draft')
        flag('touch')
        st3 = probe_flag('dark')
        check('深色失败开关生效', st3 == 500, 'status=%s' % st3)
        click_save(drv)
        toast_d = wait_toast(drv, '保存失败', timeout=25)
        time.sleep(0.4)
        d_open_d = dialog(drv) is not None
        rows_d = header_rows(drv)
        check('[深色] 失败后弹窗保持打开', d_open_d, dialog_title(drv))
        check('[深色] 失败后请求头草稿仍在',
              any(r[0] == HDR_KEY + '-D' and r[1] == 'dark-draft' for r in rows_d), rows_d)
        check('[深色] 失败 toast 可见', bool(toast_d), toast_d)
        shot(drv, 'D1a_save_fail_dark_request')
        tab(drv, '基础')
        name_d = drv.execute_script(
            "var e=document.querySelector('#api-name'); return e ? e.value : null;")
        check('[深色] 失败后改名草稿仍在', name_d == NAME_D, name_d)
        shot(drv, 'D1b_save_fail_dark_basic')

        flag('rm')
        set_input(drv, '#max-process', '200')
        time.sleep(0.3)
        click_save(drv)
        time.sleep(1.2)
        msg_d = drv.execute_script(
            """var d = document.querySelectorAll("[role='dialog']");
               var last = d[d.length - 1];
               return last ? (last.innerText || '').indexOf(arguments[0]) >= 0 : false;""",
            MAXPROC_MSG)
        check('[深色] 最大并发 200 → 中文内联提示', bool(msg_d))
        shot(drv, 'D2_maxprocess_200_dark')

        set_input(drv, '#max-process', '16')
        click_save(drv)
        wait_toast(drv, 'API 已保存', timeout=30)
        time.sleep(1)
        check('[深色] 收尾保存成功关窗', dialog(drv) is None, dialog_title(drv))

        return result
    finally:
        # 数据卫生：删除本 run 自建记录
        try:
            if CREATED['id'] is not None:
                dele = inpage_fetch(drv, 'DELETE', '/api/v1/apis/%s' % CREATED['id'])
                print('DELETE', dele)
        except Exception as exc:
            print('DELETE_ERR', exc)
        try:
            drv.quit()
        except Exception:
            pass
        try:
            with open(os.path.join(ART, MODE + '_result.json'), 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print('RESULT_WRITE_ERR', exc)


if __name__ == '__main__':
    res = main()
    bad = [c for c in res['checks'] if not c['ok']]
    print('\n===== SUMMARY %s: %d checks, %d failed =====' % (MODE, len(CHECKS), len(bad)))
    for c in bad:
        print('  FAILED:', c['name'], '::', c['detail'])
    sys.exit(0 if not bad else 1)
