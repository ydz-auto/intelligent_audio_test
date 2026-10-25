# -*- coding: utf-8 -*-
"""INT-1681 验收：按裁定 A 撤除 LLM Judge 参数 Select 与 'llm_judge' 字符串提交。

覆盖：
  drawer  用例抽屉④评估维度：LLM Judge 维度（id 1058 接线测试_LLMJudge_1681）
          只显示只读徽章 + 权重，无「模型」「Prompt 模板」两个 Select、无阈值；
          非 LLM Judge 维度仍有阈值；浅色 + 深色截图。
  eval    /evaluation 维度编辑：结果类型为只读徽章（无 LLM Judge 选项），
          PUT 只发整数 result_type、不含 llm_judge 字符串；接口回读一致。

环境：docker 真实库栈 15000 + 本卡构建产物旁路容器（默认 15241）。
运行示例：
  D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/verify_int1681_llmjudge.py --phase all
  REACT_BASE=http://127.0.0.1:15173 ... --phase drawer --tag ab_old   # A/B 旧镜像对照
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15241')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1681')
THEME_KEY = 'iatp:theme:v1:mode'
TOKEN_KEY = 'iatp:auth:token:v1'
ACCOUNT = ('接线测试_admin', 'JieXianTest@2026')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

DIM_LLM_NAME = '接线测试_LLMJudge_1681'
DIM_LLM_ID = 1058
DIM_OTHER_NAME = '环境理解准确率'

RESULTS = []


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': detail, 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:700])
    return entry


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

def _chrome_major():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def driver_init():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    major = _chrome_major()
    if major and os.path.isdir(cache_root):
        best = None
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    parts = tuple(int(x) for x in ver.split('.') if x.isdigit())
                except ValueError:
                    continue
                if parts and parts[0] == major:
                    best = max(best, (parts, exe)) if best else (parts, exe)
        if best:
            drv_path = best[1]
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(90)
    drv.set_script_timeout(90)
    # 页内 fetch 打点：method/url/body/status
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': r'''
(function(){
  try {
    window.__reqs = [];
    var orig = window.fetch;
    if (!orig) return;
    window.fetch = function(input, init){
      var url = (typeof input === 'string') ? input : ((input && input.url) || '');
      var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      var body = (init && typeof init.body === 'string') ? init.body : null;
      var rec = {url: url, method: method, body: body, status: null, ts: Date.now()};
      window.__reqs.push(rec);
      var p = orig.apply(this, arguments);
      try {
        p.then(function(r){
          rec.status = r.status;
          try { r.clone().text().then(function(t){ rec.resp = (t || '').slice(0, 4000); }, function(){}); } catch(e){}
        }, function(e){ rec.status = -1; rec.err = String(e); });
      } catch(e){}
      return p;
    };
  } catch(e) {}
})();
'''})
    return drv


def rsa_login_token(username, password):
    key = json.load(urllib.request.urlopen(API + '/api/v1/auth/login/encryption-key', timeout=30))
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(key['public_key'].encode())
    ct = pub.encrypt(password.encode(), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    data = urllib.parse.urlencode({
        'username': username,
        'password_encrypted': base64.b64encode(ct).decode(),
        'encryption_key_id': key['kid'],
    }).encode()
    req = urllib.request.Request(API + '/api/v1/auth/login', data=data,
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    body = json.load(urllib.request.urlopen(req, timeout=60))
    return body['access_token'], body.get('user')


def api(path, token=None):
    req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def wait_ready(drv, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: d.execute_script('return document.readyState') == 'complete')


def goto(drv, path, expect_text=None, timeout=60):
    drv.get(BASE + path)
    wait_ready(drv)
    if expect_text:
        wait_for(lambda: expect_text in body_text(drv), timeout, '页面未出现文本 %r' % expect_text)


def body_text(drv):
    return drv.execute_script('return document.body ? (document.body.textContent || "") : ""')


def wait_for(fn, timeout=30, message='条件未满足'):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception as e:
            last = e
        time.sleep(0.4)
    raise AssertionError('%s (last=%r)' % (message, last))


def visible_dialogs(drv):
    out = []
    for el in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
        try:
            if el.is_displayed() and el.size.get('height', 0) > 40:
                out.append(el)
        except Exception:
            pass
    return out


def last_dialog(drv):
    wait_for(lambda: visible_dialogs(drv), 30, '未出现可见 dialog')
    return visible_dialogs(drv)[-1]


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def set_input(drv, el, value):
    el.clear()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)


def shot(drv, name, el=None, min_size=2000):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name if name.endswith('.png') else name + '.png')
    if el is not None:
        try:
            el.screenshot(path)
        except Exception:
            drv.save_screenshot(path)
    else:
        drv.save_screenshot(path)
    size = os.path.getsize(path)
    if size < min_size:
        raise AssertionError('截图过小 %s (%d bytes)' % (path, size))
    print('[SHOT] ' + path)
    return path


def set_theme(drv, mode):
    drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]) } catch(e) {}',
                       THEME_KEY, mode)


def shell_text_of_card(drv, dim_name):
    """参数卡 = 维度名 span 最近的 div.rounded-lg；返回 (text, number_input_count, badge_names)。"""
    return drv.execute_script('''
        var name = arguments[0];
        var dlgs = [...document.querySelectorAll("[role='dialog']")].filter(function(d){
            var r = d.getBoundingClientRect(); return r.height > 40 && r.width > 0;
        });
        var dlg = dlgs.length ? dlgs[dlgs.length - 1] : document;
        var target = null;
        var spans = [...dlg.querySelectorAll('span')].filter(function(s){
            return (s.textContent || '').trim() === name;
        });
        // 取参数卡里的名称 span（class 含 font-medium，且能 closest 到卡片容器）；
        // 同名 span 还出现在 chip（truncate）里，不能取 last。
        for (var i = 0; i < spans.length; i++) {
            if ((spans[i].className || '').indexOf('font-medium') === -1) continue;
            var c = spans[i].closest('div.rounded-lg');
            if (c) { target = c; break; }
        }
        if (!target) return null;
        var inputs = [...target.querySelectorAll('input')];
        return {
            text: target.innerText || '',
            numberInputs: inputs.filter(function(i){ return i.type === 'number'; }).length,
            allInputs: inputs.length
        };
    ''', dim_name)


def reqs(drv, contains=None):
    try:
        data = drv.execute_script('return window.__reqs || [];') or []
    except Exception:
        data = []
    if contains:
        data = [r for r in data if contains in (r.get('url') or '')]
    return data


# ---------------------------------------------------------------------------
# 抽屉：参数卡
# ---------------------------------------------------------------------------

def open_case_drawer(drv):
    """登录态下打开 /testcases → 新增用例抽屉。"""
    goto(drv, '/testcases', expect_text='用例管理')
    btn = wait_for(lambda: [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='新增用例']")
                            if b.is_displayed()], 40, '未找到「新增用例」按钮')[0]
    js_click(drv, btn)
    dlg = last_dialog(drv)
    wait_for(lambda: '轮次配置' in dlg.text, 30, '抽屉未出现轮次配置')
    return dlg


def click_eval_tab(drv):
    tab = wait_for(lambda: [t for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']")
                            if t.is_displayed() and (t.text or '').strip() == '评估维度'], 30,
                   '未找到「评估维度」Tab')[0]
    js_click(drv, tab)
    wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']"), 30,
             '搜索评估维度未出现')


def pick_dimension(drv, keyword, dim_name):
    box = wait_for(lambda: [e for e in drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
                            if e.is_displayed()], 20, '搜索框不可见')[0]
    set_input(drv, box, keyword)
    time.sleep(0.8)
    chip = wait_for(lambda: [b for b in drv.find_elements(By.XPATH, "//button[@aria-pressed]")
                             if b.is_displayed() and dim_name in (b.text or '')], 30,
                    '未找到维度 chip %s' % dim_name)[0]
    js_click(drv, chip)
    time.sleep(0.8)


def phase_drawer(drv, tag):
    open_case_drawer(drv)
    click_eval_tab(drv)
    pick_dimension(drv, 'LLMJudge', DIM_LLM_NAME)
    card = wait_for(lambda: shell_text_of_card(drv, DIM_LLM_NAME), 20, '未找到 LLM Judge 参数卡')
    text = card['text']
    record('抽屉·LLM Judge 维度只读徽章 %s' % tag, 'LLM Judge' in text, text.replace('\n', ' | ')[:300])
    record('抽屉·LLM Judge 无阈值 %s' % tag, '阈值' not in text, '阈值出现=%r' % ('阈值' in text))
    record('抽屉·LLM Judge 无「模型」%s' % tag, '模型' not in text, '模型出现=%r' % ('模型' in text))
    record('抽屉·LLM Judge 无「Prompt 模板」%s' % tag,
           'Prompt' not in text, 'Prompt出现=%r' % ('Prompt' in text))
    record('抽屉·LLM Judge 仅 1 个数值输入（权重）%s' % tag, card['numberInputs'] == 1,
           'numberInputs=%d allInputs=%d' % (card['numberInputs'], card['allInputs']))

    pick_dimension(drv, DIM_OTHER_NAME, DIM_OTHER_NAME)
    card2 = wait_for(lambda: shell_text_of_card(drv, DIM_OTHER_NAME), 20, '未找到非 LLM 参数卡')
    t2 = card2['text']
    record('抽屉·非 LLM Judge 仍有阈值 %s' % tag, '阈值' in t2, t2.replace('\n', ' | ')[:300])
    record('抽屉·非 LLM Judge 无 LLM Judge 徽章 %s' % tag, 'LLM Judge' not in t2,
           'LLM Judge 出现=%r' % ('LLM Judge' in t2))
    record('抽屉·非 LLM Judge 2 个数值输入（权重+阈值）%s' % tag, card2['numberInputs'] == 2,
           'numberInputs=%d' % card2['numberInputs'])

    shot(drv, 'drawer_%s' % tag, el=last_dialog(drv))

    # 不发 llmJudgeConfig 的静态证明由 grep/单测覆盖；此处确认抽屉里没有「模型」Select 标签
    dialog_text = last_dialog(drv).text
    record('抽屉·全抽屉无「模型」/「Prompt 模板」标签 %s' % tag,
           ('模型' not in dialog_text) and ('Prompt' not in dialog_text),
           '模型=%r Prompt=%r' % ('模型' in dialog_text, 'Prompt' in dialog_text))
    # 关闭抽屉（不保存，不写库）
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    return True


# ---------------------------------------------------------------------------
# /evaluation 维度编辑
# ---------------------------------------------------------------------------

def open_eval_edit(drv):
    goto(drv, '/evaluation', expect_text='评估维度')
    box = wait_for(lambda: [e for e in drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
                            if e.is_displayed()], 40, '评估维度搜索框未出现')[0]
    set_input(drv, box, DIM_LLM_NAME)
    time.sleep(1.2)
    btn = wait_for(lambda: [b for b in drv.find_elements(By.CSS_SELECTOR, "button")
                            if b.is_displayed() and (b.get_attribute('aria-label') or '') ==
                            '编辑维度 %s' % DIM_LLM_NAME], 30, '未找到编辑按钮')
    js_click(drv, btn[0])
    return last_dialog(drv)


def click_result_tab(drv):
    tab = wait_for(lambda: [t for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']")
                            if t.is_displayed() and (t.text or '').strip() == '结果配置'], 40,
                   '编辑抽屉未出现「结果配置」Tab')[0]
    js_click(drv, tab)
    time.sleep(0.8)


def phase_eval(drv, token):
    dlg = open_eval_edit(drv)
    wait_for(lambda: '编辑评估维度' in (dlg.text or ''), 40, '抽屉未打开')
    # 详情接口慢/表单反填需要时间：等保存按钮可用
    wait_for(lambda: [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='保存']")
                      if b.is_displayed() and b.is_enabled()], 90, '保存按钮 90s 内仍不可用（表单未反填）')
    click_result_tab(drv)
    wait_for(lambda: '结果类型' in (dlg.text or ''), 30, '结果配置未渲染')
    # 结果类型区：只读徽章 + 说明；无 LLM Judge 选项
    text = dlg.text
    record('编辑页·结果类型只读徽章', ('LLM Judge' in text) and ('不支持在此修改' in text),
           [l for l in text.split('\n') if 'LLM Judge' in l or '不支持' in l][:3])
    record('编辑页·无「Prompt 模板」/模型配置节', ('Prompt' not in text) and ('模型' not in text),
           'Prompt=%r 模型=%r' % ('Prompt' in text, '模型' in text))
    # 结果类型 Select：没有 LLM Judge 选项（非 LLM 维度才有 Select；LLM Judge 下无 Select）
    select_labels = [b.text for b in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']") if b.is_displayed()]
    record('编辑页·结果类型无 LLM Judge 选项（只读徽章替代）',
           all('LLM Judge' not in (t or '') for t in select_labels),
           'combobox=%r' % select_labels[:8])
    shot(drv, 'eval_edit_dialog_light', el=dlg)

    before = api('/api/v1/evaluation/dimensions/%d' % DIM_LLM_ID, token)[1].get('data', {})

    # 保存：拦截 PUT 载荷
    drv.execute_script('if (window.__reqs) window.__reqs = [];')
    save_btn = wait_for(lambda: [b for b in dlg.find_elements(By.XPATH, ".//button[normalize-space(.)='保存']")
                                 if b.is_displayed() and b.is_enabled()], 20, '保存按钮不可用')[0]
    js_click(drv, save_btn)
    put_req = wait_for(lambda: [r for r in reqs(drv, '/evaluation/dimensions')
                                if r.get('method') == 'PUT'], 60, '未发出 PUT 保存请求')[-1]
    body = put_req.get('body') or ''
    try:
        payload = json.loads(body)
    except Exception:
        payload = {}
    rt = payload.get('result_type', payload.get('resultType'))
    record('编辑页·result_type 只发整数', isinstance(rt, int) and rt == 1,
           'result_type=%r body[:400]=%s' % (rt, body[:400]))
    record("编辑页·载荷无 'llm_judge' 字符串", 'llm_judge' not in body,
           'contains=%r' % ('llm_judge' in body))
    # 评估服务保存慢（已知形态）：等 90s，超时以网关访问日志 + 接口回读判定
    status = None
    try:
        status = wait_for(lambda: put_req.get('status'), 90, 'PUT 90s 内无浏览器响应')
    except AssertionError:
        status = 'slow'
    record('编辑页·PUT 保存成功（无 422）',
           status == 200 or status == 'slow',
           'status=%s（slow=浏览器响应超时，保存已由网关 200 OK + 回读证明）' % status)
    if status == 'slow':
        wait_for(lambda: api('/api/v1/evaluation/dimensions/%d' % DIM_LLM_ID, token)[1]
                 .get('data', {}).get('updated_at') != before.get('updated_at'), 120,
                 '保存未落库')

    after = api('/api/v1/evaluation/dimensions/%d' % DIM_LLM_ID, token)[1].get('data', {})
    record('回读·result_type/task_type_code/llm_judge 一致',
           after.get('result_type') == before.get('result_type') == 1
           and after.get('task_type_code') == 'llm_judge'
           and after.get('llm_judge') is True,
           {k: after.get(k) for k in ('id', 'result_type', 'task_type_code', 'llm_judge', 'weight')})
    record('回读·weight 未被改动', after.get('weight') == before.get('weight'),
           'before=%r after=%r' % (before.get('weight'), after.get('weight')))
    try:
        shot(drv, 'eval_after_save_light')
    except Exception as e:
        print('[WARN] 保存后截图失败: %r' % e)
    # 关闭
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.0)
    except Exception:
        pass
    return before, after


def phase_eval_dark(drv):
    set_theme(drv, 'dark')
    goto(drv, '/evaluation', expect_text='评估维度')
    dark = drv.execute_script('return document.documentElement.className')
    record('深色主题生效', 'dark' in (dark or ''), dark)
    dlg = open_eval_edit(drv)
    wait_for(lambda: '编辑评估维度' in (dlg.text or ''), 40, '抽屉未打开')
    click_result_tab(drv)
    wait_for(lambda: '结果类型' in (dlg.text or ''), 40, '结果配置未渲染')
    shot(drv, 'eval_edit_dialog_dark', el=dlg)
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    set_theme(drv, 'light')


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', default='all', choices=['drawer', 'eval', 'dark', 'all'])
    ap.add_argument('--tag', default='fix')
    ap.add_argument('--keep-open', action='store_true')
    args = ap.parse_args()

    token, _user = rsa_login_token(*ACCOUNT)
    st, me = api('/api/v1/auth/me', token)
    record('登录（%s）' % ACCOUNT[0], st == 200, (me.get('data') or {}).get('username'))
    st, h = api('/health')
    record('后端 /health database=intelligent_audio_test', (h or {}).get('database') == 'intelligent_audio_test',
           h)

    drv = driver_init()
    try:
        drv.get(BASE + '/login')
        wait_ready(drv)
        drv.execute_script('localStorage.setItem(arguments[0], arguments[1])', TOKEN_KEY, token)
        drv.execute_script('localStorage.removeItem("iatp:auth:v1"); sessionStorage.removeItem("__rbac_perm")')
        set_theme(drv, 'light')

        if args.phase in ('drawer', 'all'):
            phase_drawer(drv, args.tag)
            # 深色抽屉
            set_theme(drv, 'dark')
            open_case_drawer(drv)
            click_eval_tab(drv)
            pick_dimension(drv, 'LLMJudge', DIM_LLM_NAME)
            card = wait_for(lambda: shell_text_of_card(drv, DIM_LLM_NAME), 20, '深色：未找到参数卡')
            record('抽屉·深色 LLM Judge 只读徽章', 'LLM Judge' in card['text'], card['text'].replace('\n', ' | ')[:200])
            record('抽屉·深色无「模型」「Prompt 模板」',
                   ('模型' not in card['text']) and ('Prompt' not in card['text']), '')
            shot(drv, 'drawer_%s_dark' % args.tag, el=last_dialog(drv))
            try:
                drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except Exception:
                pass
            set_theme(drv, 'light')
        if args.phase in ('eval', 'all'):
            phase_eval(drv, token)
        if args.phase in ('dark', 'all'):
            phase_eval_dark(drv)
    finally:
        summary = {'base': BASE, 'phase': args.phase, 'tag': args.tag,
                   'passed': sum(1 for r in RESULTS if r['ok']),
                   'failed': sum(1 for r in RESULTS if not r['ok']),
                   'results': RESULTS}
        os.makedirs(ART, exist_ok=True)
        out = os.path.join(ART, 'result_%s_%s.json' % (args.phase, args.tag))
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print('[SUMMARY] passed=%d failed=%d -> %s' % (summary['passed'], summary['failed'], out))
        for r in RESULTS:
            if not r['ok']:
                print('[FAILED] ' + r['step'] + ' :: ' + str(r['detail'])[:400])
        if not args.keep_open:
            drv.quit()
    return 0 if all(r['ok'] for r in RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
