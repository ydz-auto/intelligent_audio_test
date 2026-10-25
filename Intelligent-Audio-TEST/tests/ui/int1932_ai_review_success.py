# -*- coding: utf-8 -*-
"""INT-1932 浏览器实测：AI 复核成功路径（docker 15173 + 15000 真实库）。

覆盖卡内 4 项：
  1) 流式对话：错误态（供应商不可达）+ 成功态（真实 POST /chat/completions → 本地增量渲染 → 结束态）
  2) 保存复核结论：请求体 → 轮询历史 → 记录卡 → 回读 GET ai-review-history 一致 → 重开弹窗回显
  3) 快速复核 采纳 / 驳回：各一次，核结果字段与任务侧（test_results / task_case_relations）状态变化
  4) 证据出处：截图内嵌页面地址（stacksnap 水印），Network 原文同在 evidence.json

前置：tests/ui/int1932_fixture.py setup 已执行；tests/ui/int1932_llm_stub.py 在宿主 5312 运行。
用法：python tests/ui/int1932_ai_review_success.py
"""
import json
import os
import sys
import time
import traceback

sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT1932_BASE', 'http://localhost:15173')
API = os.environ.get('INT1932_API', 'http://127.0.0.1:15000/api/v1')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1932')
os.makedirs(ART, exist_ok=True)
RESULT = os.path.join(ART, 'browser_result.json')
SNAP = os.path.join(ART, 'fixture_snapshot.json')
STUB_CFG = os.path.join(ART, 'stub_config.json')
STUB_BASE = os.environ.get('INT1932_STUB_BASE', 'http://127.0.0.1:5312/v1')
DEAD_BASE = os.environ.get('INT1932_DEAD_BASE', 'http://127.0.0.1:5399/v1')
LOGIN_USER = '接线测试_admin'
LOGIN_PASS = 'JieXianTest@2026'

FIX = json.load(open(SNAP, encoding='utf-8'))
DIM_ID = FIX['dim_id']
T_SAVE = next(t for t in FIX['targets'] if t['role'].startswith('会话'))
T_ADOPT = next(t for t in FIX['targets'] if '采纳' in t['role'])
T_REJECT = next(t for t in FIX['targets'] if '驳回' in t['role'])

PATCH = r"""
window.__fetchLog=[];
(function(){
 if(window.__fetchPatched) return; window.__fetchPatched=true;
 const f=window.fetch;
 window.fetch=async function(input,init){
  const url=typeof input==='string'?input:(input&&input.url)||'';
  const e={ts:Date.now(),url:url,method:(init&&init.method)||'GET'};
  try{
   const r=await f.apply(this,arguments); e.status=r.status;
   if(init&&typeof init.body==='string') e.reqBody=init.body;
   if(/ai-review|review-history|\/review|chat\/completions|\/cases\/|results$/.test(url)){
     try{e.resBody=await r.clone().text();}catch(x){}
   }
   window.__fetchLog.push(e); return r;
  }catch(err){e.status='ERR';e.err=String(err);window.__fetchLog.push(e);throw err;}
 };
})();
"""


def driver():
    o = Options(); o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1680,1400', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--force-prefers-reduced-motion'):
        o.add_argument(a)
    import winreg
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe) and v.split('.')[0] == str(major):
                path = exe
    except Exception:
        pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(180)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return d


def body_text(d):
    return d.execute_script('return document.body.innerText || ""') or ''


def goto(d, p, s=4):
    d.get(BASE + p)
    WebDriverWait(d, 90).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(s)


def jsclick(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"});arguments[0].click();', el)


def stamp(d, label):
    """截图：在页面右上角浮层写入当前真实 URL + 时间 + 栈指纹（证据出处核对的抓手）。"""
    meta = d.execute_script("""
      const el=document.getElementById('__int1932_stamp');
      if(el) el.remove();
      const div=document.createElement('div');
      div.id='__int1932_stamp';
      div.textContent=%s;
      div.style.cssText='position:fixed;top:0;right:0;z-index:2147483647;background:#7c3aed;color:#fff;'
        +'font:12px/1.5 monospace;padding:4px 8px;max-width:70vw;white-space:pre-wrap;opacity:.95';
      document.body.appendChild(div); return div.textContent;
    """ % json.dumps(label, ensure_ascii=False))
    return meta


def shot(d, name, label=None):
    if label:
        stamp(d, label)
        time.sleep(0.25)
    path = os.path.join(ART, name + '.png')
    d.save_screenshot(path)
    d.execute_script("document.getElementById('__int1932_stamp')?.remove()")
    return path


def shot_pair(d, name, label_light):
    p1 = shot(d, name + '_light', label_light)
    d.execute_script("document.documentElement.classList.remove('light');document.documentElement.classList.add('dark');")
    time.sleep(0.8)
    p2 = shot(d, name + '_dark', label_light + '  [dark]')
    d.execute_script("document.documentElement.classList.remove('dark');document.documentElement.classList.add('light');")
    time.sleep(0.4)
    return [p1, p2]


def fetch_log(d):
    try:
        return d.execute_script('return window.__fetchLog||[]') or []
    except Exception:
        return []


def clear_log(d):
    d.execute_script('window.__fetchLog=[];')


def relevant(log):
    out = []
    for e in log:
        u = e.get('url', '')
        if not any(k in u for k in ('ai-review', 'review-history', '/results/review', 'chat/completions')):
            continue
        item = {'ts': e.get('ts'), 'method': e.get('method'), 'url': u.replace(BASE, ''), 'status': e.get('status')}
        if e.get('reqBody'):
            try:
                item['req'] = json.loads(e['reqBody'])
            except Exception:
                item['req'] = e['reqBody'][:300]
        if e.get('resBody'):
            try:
                j = json.loads(e['resBody'])
                item['res'] = j.get('data', j) if isinstance(j, dict) else j
            except Exception:
                item['res'] = e['resBody'][:400]
        out.append(item)
    return out


def set_providers(d, base):
    d.execute_script(
        "localStorage.setItem('iatp:ai-chat:v1:providers', arguments[0]);"
        "localStorage.removeItem('iatp:ai-chat:v1:config');",
        json.dumps({'version': 1, 'data': [{
            'id': 'provider-int1932', 'name': '接线测试_INT1932_LLM',
            'baseUrl': base, 'apiKey': 'sk-int1932',
            'models': ['int1932-mock'], 'isDefault': True}]}, ensure_ascii=False))


def write_stub_cfg(score, reasoning, reply):
    with open(STUB_CFG, 'w', encoding='utf-8') as f:
        json.dump({'score': score, 'reasoning': reasoning, 'chat_reply': reply,
                   'latency_ms': 0}, f, ensure_ascii=False, indent=2)


def login(d):
    goto(d, '/login', 2)
    d.execute_script("localStorage.clear()")
    d.get('about:blank'); time.sleep(0.4)
    goto(d, '/login', 2)
    d.find_element(By.ID, 'username').send_keys(LOGIN_USER)
    d.find_element(By.ID, 'password').send_keys(LOGIN_PASS)
    d.find_element(By.XPATH, "//form//button[@type='submit']").click()
    time.sleep(7)
    return d.current_url


def open_task(d):
    goto(d, f'/tasks/{FIX["task_id"]}', 8)
    heads = d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'用例清单')]")
    if heads:
        jsclick(d, heads[0]); time.sleep(3)
    return d.current_url


def search_case(d, tag, timeout=90):
    """用 JS 原生 setter 写搜索框（React 受控输入），再按标签筛行。"""
    t0 = time.time()
    ok = False
    while time.time() - t0 < timeout:
        ok = d.execute_script("""
          const el=document.querySelector("input[aria-label='搜索用例']");
          if(!el) return false;
          const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          setter.call(el, arguments[0]);
          el.dispatchEvent(new Event('input',{bubbles:true}));
          return true;
        """, tag)
        if ok:
            break
        time.sleep(2)
    if not ok:
        return []
    t0 = time.time()
    while time.time() - t0 < 60:
        rows = [r for r in d.find_elements(By.XPATH, "//*[@role='row']") if tag in (r.text or '')]
        if rows:
            return rows
        d.execute_script("""
          const el=document.querySelector("input[aria-label='搜索用例']");
          if(!el) return;
          const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          setter.call(el, arguments[0]);
          el.dispatchEvent(new Event('input',{bubbles:true}));
        """, tag)
        time.sleep(2)
    return []


def open_dialog_via(d, tag, aria):
    rows = search_case(d, tag)
    if not rows:
        return None, f'未找到 {tag} 行'
    row = rows[0]
    btns = row.find_elements(By.XPATH, f".//button[@aria-label='{aria}']")
    if not btns:
        btns = d.find_elements(By.XPATH, f"//button[@aria-label='{aria}']")
    if not btns:
        return None, f'{tag} 行无 {aria} 按钮'
    jsclick(d, btns[0])
    time.sleep(2.5)
    return row, None


def dialog(d, slot):
    els = d.find_elements(By.XPATH, f"//*[@data-slot='{slot}']")
    return els[0] if els else None


def dlg_text(d, slot):
    el = dialog(d, slot)
    return (el.text if el else '') or ''


def wait_until(fn, timeout=180, interval=2.0, desc=''):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            v = fn()
        except Exception:
            v = None
        if v:
            return v, round(time.time() - t0, 1)
        time.sleep(interval)
    return None, round(time.time() - t0, 1)


def click_text(d, slot, text, exact=False):
    xp = (f"//*[@data-slot='{slot}']//button[normalize-space(.)='{text}']" if exact
          else f"//*[@data-slot='{slot}']//button[contains(normalize-space(.),'{text}')]")
    els = d.find_elements(By.XPATH, xp)
    if not els:
        return False
    jsclick(d, els[0])
    return True


def api_get(path, token):
    import urllib.request
    req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


R = {'stack': {'frontend': BASE, 'backend': API}, 'fixture': {'dim_id': DIM_ID, 'targets': FIX['targets']}}


def save_result():
    with open(RESULT, 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=1)


def main():
    token = open(os.path.join(HERE, 'artifacts', 'int1932_token.txt'), encoding='utf-8').read().strip()
    d = driver()
    try:
        # ---------- 0. 登录 & 打开任务 ----------
        R['login_url'] = login(d)
        R['script_hashes_start'] = d.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src)")
        set_providers(d, DEAD_BASE)  # 先放一个不可达供应商，测错误态
        R['task_url'] = open_task(d)
        R['task_page_url_actual'] = d.current_url
        shot(d, '10_task419_ready', f'URL={d.current_url} @ {time.strftime("%Y-%m-%d %H:%M:%S")}')
        save_result()

        # ========== 1c. 流式对话错误态（供应商不可达） ==========
        ph = {}
        row, err = open_dialog_via(d, T_SAVE['tag'], 'AI 复核')
        ph['open'] = err is None
        if err:
            ph['open_error'] = err
        dlg = dialog(d, 'ai-review-session-dialog')
        ph['dialog_open'] = dlg is not None
        if dlg:
            wait_until(lambda: 'AI 复核' in dlg_text(d, 'ai-review-session-dialog'), 60, 2)
            wait_until(lambda: d.execute_script(
                "const t=document.querySelector(\"[data-slot='ai-review-session-dialog'] textarea\");return t&&t.value&&t.value.length>5"),
                60, 2)
            clear_log(d)
            btns = d.find_elements(By.XPATH, "//*[@data-slot='ai-review-session-dialog']//button[@type='submit']")
            ph['send_btn_count'] = len(btns)
            if btns:
                jsclick(d, btns[-1]); ph['send_clicked'] = 'submit-last'
            time.sleep(6)
            if '网络连接失败' not in dlg_text(d, 'ai-review-session-dialog') and '无法连接' not in dlg_text(d, 'ai-review-session-dialog'):
                btns = d.find_elements(By.XPATH, "//*[@data-slot='ai-review-session-dialog']//button[@type='submit']")
                if btns:
                    jsclick(d, btns[-1]); ph['send_retried'] = True
            got, secs = wait_until(lambda: ('网络连接失败' in dlg_text(d, 'ai-review-session-dialog')
                                            or '无法连接' in dlg_text(d, 'ai-review-session-dialog')
                                            or '未配置' in dlg_text(d, 'ai-review-session-dialog')), 90, 2)
            ph['error_visible'] = bool(got)
            ph['error_secs'] = secs
            ph['dialog_text'] = dlg_text(d, 'ai-review-session-dialog')[-600:]
            ph['reqs'] = relevant(fetch_log(d))
            ph['shots'] = shot_pair(d, '11_stream_error', f'错误态 URL={d.current_url}')
            # 关闭
            if not click_text(d, 'ai-review-session-dialog', '稍后处理', exact=True):
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.5)
            ph['closed'] = dialog(d, 'ai-review-session-dialog') is None
        R['phase1_error_state'] = ph
        save_result()

        # ========== 1a/1b + 2. 流式成功 + 保存复核结论 + 回读 + 重开回显 ==========
        write_stub_cfg(0.86,
                       '接线测试_INT1932：复检认为原判定成立，逐轮拒识话轮评估 0.86，高于阈值 0.7。',
                       '复核分析（接线测试_INT1932）：查看任务 419 该用例的逐轮执行记录，两轮均为拒识成功，'
                       '回复时延与静默期行为均未超出阈值；评估维度得分稳定，无异常波动。综合判断：通过。'
                       '建议维持既有「评估完成」判定；如需改判请以人工复核结论为准。')
        set_providers(d, STUB_BASE)
        R['task_url2'] = open_task(d)   # 重载以让供应商 hook 重新初始化
        ph2 = {}
        row, err = open_dialog_via(d, T_SAVE['tag'], 'AI 复核')
        ph2['open'] = err is None
        if err:
            ph2['open_error'] = err
        ph2['dialog_open'] = dialog(d, 'ai-review-session-dialog') is not None
        if ph2['dialog_open']:
            wait_until(lambda: 'AI 复核' in dlg_text(d, 'ai-review-session-dialog'), 60, 2)
            ph2['context_card'] = '复核上下文' in dlg_text(d, 'ai-review-session-dialog') or '已有 AI 复核结论' in dlg_text(d, 'ai-review-session-dialog')
            shot(d, '20_stream_before', f'URL={d.current_url} 发送前')
            clear_log(d)
            # 发送
            sent = click_text(d, 'ai-review-session-dialog', '发送')
            if not sent:
                btns = d.find_elements(By.XPATH, "//*[@data-slot='ai-review-session-dialog']//button[@type='submit']")
                if btns:
                    jsclick(d, btns[0]); sent = True
            ph2['send_clicked'] = sent
            # 增量帧采样（40ms 节奏，逐帧记录对话区文本长度与末段内容）
            frames = []
            t0 = time.time()
            captured_mid = None
            while time.time() - t0 < 40:
                txt = dlg_text(d, 'ai-review-session-dialog')
                mark = txt.find('复核分析（接线测试_INT1932）')
                frames.append({'ms': int((time.time() - t0) * 1000), 'len': len(txt),
                               'reply_chars': (len(txt) - mark) if mark >= 0 else 0})
                if mark >= 0 and captured_mid is None and 40 < (len(txt) - mark) < 260:
                    captured_mid = shot(d, '21_stream_mid', f'流式增量中 URL={d.current_url}')
                if '保存复核结论' in txt and len(frames) > 3 and mark >= 0 and frames[-1]['reply_chars'] == frames[-2]['reply_chars'] and frames[-1]['reply_chars'] > 0:
                    break
                time.sleep(0.09)
            ph2['frames_head'] = frames[:6]
            ph2['frames_tail'] = frames[-3:]
            ph2['frame_count'] = len(frames)
            ph2['distinct_lengths'] = len({f['len'] for f in frames})
            ph2['incremental'] = len({f['len'] for f in frames}) >= 3
            ph2['mid_shot'] = captured_mid
            ph2['reqs_chat'] = relevant(fetch_log(d))
            ph2['shots_stream'] = shot_pair(d, '22_stream_done', f'流式结束态 URL={d.current_url}')
            # 保存复核结论
            clear_log(d)
            ph2['save_clicked'] = click_text(d, 'ai-review-session-dialog', '保存复核结论')
            ph2['running_text'] = None
            got, secs = wait_until(lambda: ('AI 复核中' in dlg_text(d, 'ai-review-session-dialog')), 30, 1)
            ph2['saw_running'] = bool(got)
            if got:
                shot(d, '23_save_running', f'保存后执行中 URL={d.current_url}')
            done, secs2 = wait_until(
                lambda: ('AI 复核记录' in dlg_text(d, 'ai-review-session-dialog')
                         or 'AI 复核失败' in dlg_text(d, 'ai-review-session-dialog')), 240, 2)
            ph2['record_card'] = done is not None
            ph2['record_secs'] = secs2
            ph2['record_text'] = dlg_text(d, 'ai-review-session-dialog')[-1200:]
            ph2['reqs_save'] = relevant(fetch_log(d))
            ph2['shots_record'] = shot_pair(d, '24_record_card', f'AI 复核记录卡 URL={d.current_url}')
            save_result()
            # 回读（真实 GET）
            hist = api_get(f'/tasks/results/{FIX["task_id"]}/ai-review-history', token)
            items = [i for i in (hist.get('data', {}) or {}).get('items', []) if i.get('dimension_id') == DIM_ID]
            items.sort(key=lambda x: x['id'], reverse=True)
            ph2['readback_latest'] = items[0] if items else None
            ph2['readback_count_dim'] = len(items)
            # 关闭并重开，验证回显
            if not click_text(d, 'ai-review-session-dialog', '关闭', exact=True):
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.5)
            ph2['closed'] = dialog(d, 'ai-review-session-dialog') is None
            row, err2 = open_dialog_via(d, T_SAVE['tag'], 'AI 复核')
            wait_until(lambda: 'AI 复核' in dlg_text(d, 'ai-review-session-dialog'), 60, 2)
            echo_txt = dlg_text(d, 'ai-review-session-dialog')
            ph2['reopen_echo'] = ('已有 AI 复核结论' in echo_txt) or ('复核通过' in echo_txt) or ('已复核' in echo_txt)
            ph2['reopen_text'] = echo_txt[:900]
            ph2['shots_reopen'] = shot_pair(d, '25_reopen_echo', f'重开弹窗回显 URL={d.current_url}')
            if not click_text(d, 'ai-review-session-dialog', '稍后处理', exact=True):
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.2)
        R['phase2_stream_save'] = ph2
        save_result()

        # ========== 3a. 快速复核 · 采纳（AI 判定不通过 → 改判评估失败） ==========
        write_stub_cfg(0.42,
                       '接线测试_INT1932：复检认为原判定偏松，逐轮话轮评估 0.42 低于阈值 0.7，建议改判评估失败。',
                       '')
        ph3 = {}
        R['task_url3'] = open_task(d)
        row, err = open_dialog_via(d, T_ADOPT['tag'], '快速复核')
        ph3['open'] = err is None
        if err:
            ph3['open_error'] = err
        ph3['dialog_open'] = dialog(d, 'quick-ai-review-dialog') is not None
        if ph3['dialog_open']:
            clear_log(d)
            ph3['launch'] = click_text(d, 'quick-ai-review-dialog', '发起快速复核')
            got, secs = wait_until(lambda: ('AI 复核结论' in dlg_text(d, 'quick-ai-review-dialog')
                                            or '执行失败' in dlg_text(d, 'quick-ai-review-dialog')), 240, 2)
            ph3['completed'] = bool(got)
            ph3['secs'] = secs
            ph3['text_before_adopt'] = dlg_text(d, 'quick-ai-review-dialog')
            ph3['shots_result'] = shot_pair(d, '30_quick_adopt_result', f'快速复核结论 URL={d.current_url}')
            ph3['reqs_launch'] = relevant(fetch_log(d))
            clear_log(d)
            ph3['adopt_clicked'] = click_text(d, 'quick-ai-review-dialog', '采纳为复核结果')
            got2, secs2 = wait_until(lambda: dialog(d, 'quick-ai-review-dialog') is None
                                     or '已采纳' in dlg_text(d, 'quick-ai-review-dialog'), 120, 1)
            ph3['adopted_ui'] = bool(got2)
            ph3['secs_adopt'] = secs2
            time.sleep(6)   # 等 adopt 请求返回后再读 fetch 打点（上一轮读太早丢了请求原文）
            ph3['reqs_adopt'] = relevant(fetch_log(d))
            ph3['toast'] = body_text(d)[-300:]
            if dialog(d, 'quick-ai-review-dialog') is not None:
                click_text(d, 'quick-ai-review-dialog', '关闭', exact=True)
            time.sleep(2)
            # 任务侧变化：刷新后看该用例行状态
            open_task(d); search_case(d, T_ADOPT['tag'])
            _rows = search_case(d, T_ADOPT['tag'])
            ph3['row_text_after'] = _rows[0].text if _rows else None
            ph3['shots_task_after'] = shot_pair(d, '31_task_row_after_adopt', f'采纳后任务侧 URL={d.current_url}')
        R['phase3_quick_adopt'] = ph3
        save_result()

        # ========== 3b. 快速复核 · 驳回（AI 判定通过 → 原判定不变） ==========
        write_stub_cfg(0.86,
                       '接线测试_INT1932：复检认为原判定成立，逐轮拒识话轮评估 0.86，高于阈值 0.7。',
                       '')
        ph4 = {}
        open_task(d)
        row, err = open_dialog_via(d, T_REJECT['tag'], '快速复核')
        ph4['open'] = err is None
        if err:
            ph4['open_error'] = err
        ph4['dialog_open'] = dialog(d, 'quick-ai-review-dialog') is not None
        if ph4['dialog_open']:
            clear_log(d)
            ph4['launch'] = click_text(d, 'quick-ai-review-dialog', '发起快速复核')
            got, secs = wait_until(lambda: ('AI 复核结论' in dlg_text(d, 'quick-ai-review-dialog')
                                            or '执行失败' in dlg_text(d, 'quick-ai-review-dialog')), 240, 2)
            ph4['completed'] = bool(got)
            ph4['secs'] = secs
            ph4['text_before_reject'] = dlg_text(d, 'quick-ai-review-dialog')
            ph4['shots_result'] = shot_pair(d, '40_quick_reject_result', f'快速复核结论（待驳回）URL={d.current_url}')
            ph4['reqs_launch'] = relevant(fetch_log(d))
            clear_log(d)
            ph4['reject_clicked'] = click_text(d, 'quick-ai-review-dialog', '驳回')
            got2, secs2 = wait_until(lambda: '已驳回 AI 复核结论' in dlg_text(d, 'quick-ai-review-dialog'), 90, 1)
            ph4['rejected_ui'] = bool(got2)
            ph4['secs_reject'] = secs2
            ph4['text_after_reject'] = dlg_text(d, 'quick-ai-review-dialog')
            ph4['reqs_reject'] = relevant(fetch_log(d))
            ph4['shots_rejected'] = shot_pair(d, '41_quick_rejected', f'已驳回 URL={d.current_url}')
            if dialog(d, 'quick-ai-review-dialog') is not None:
                click_text(d, 'quick-ai-review-dialog', '关闭', exact=True)
            time.sleep(1.5)
        R['phase4_quick_reject'] = ph4
        R['script_hashes_end'] = d.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src)")
    except Exception:
        R['fatal'] = traceback.format_exc()[-2500:]
    finally:
        try:
            d.quit()
        except Exception:
            pass
        save_result()
        print(json.dumps(R, ensure_ascii=False, indent=1)[:6000])


if __name__ == '__main__':
    main()
