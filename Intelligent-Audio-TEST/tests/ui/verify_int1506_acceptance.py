# -*- coding: utf-8 -*-
"""INT-1506 验收：清除用例抽屉/批量弹窗写死假数据（浏览器实测）。

被测：交付分支 8c4d698e 的 frontend-react 构建（旁路容器 15276 → docker api_gateway
http://localhost:15000，主库 intelligent_audio_test，AUTH_MODE=off）。

核对项（卡内验收标准逐条）：
① 用例编辑抽屉 → 评估维度：抽屉内无写死模型/Prompt 文本；真实库无 llm_judge 维度，
   LLM 参数卡分支用响应桩（浏览器内 fetch 改写 GET /evaluation/dimensions，不落库）验证
   模型/Prompt 为自由文本、默认取维度自身 llmJudgeConfig。
② 全局背景噪声播放设备 chips == GET /playback-devices（真实库 12 条）；「未匹配」判定
   以真实列表为准——真实设备名不误报，列表外设备名被标黄（响应桩注入 camelCase
   deviceNames，不落库；真实库无用例带 device_names、也无评估策略）。
③ 批量设置评估维度轮次：勾选两条 2 轮用例 → 逐轮页签 / 指定轮次只有第 1~2 轮（写死值
   为 4，出现第 3/4 轮即失败）；再勾选一条 1 轮用例 → 只有第 1 轮。
④ 试听弹窗时长/设备取真实数据（预览 config.rounds[0].audios[0]：长度 == 该音频
   duration ±1s、设备 == 该音频 playback_device_name；出现 00:42 即失败）。
⑤ 浅 / 深色截图。

数据纪律：本脚本对真实库零写入（无新建/修改/删除），只用只读用例与浏览器内存响应桩。
运行：PYTHONIOENCODING=utf-8 <py> tests/ui/verify_int1506_acceptance.py
"""
import json
import os
import re
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_UI_BASE', 'http://localhost:15276')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1506')
os.makedirs(ART, exist_ok=True)

FAKE_DEVICE = '接线测试_INT1506_假设备名'
REAL_DEVICE = '设备背面（0.5m+180°）'
PROBE_CASE_MARK = 'HJ050'
# 分段执行（复测只跑必要段）：light=浅色抽屉+批量 / light1=单轮批量 / dark=深色 / stub=响应桩
SECTIONS = {s.strip() for s in (os.environ.get('INT1506_SECTIONS')
                                or 'light,light1,dark,stub').split(',') if s.strip()}

RESULTS = {}
LOGS = []


def log(*args):
    line = ' '.join(str(a) for a in args)
    LOGS.append(line)
    print(line, flush=True)


def check(name, ok, detail=''):
    RESULTS[name] = bool(ok)
    log(('PASS' if ok else 'FAIL'), name, detail)
    return ok


def api_get(path, tries=5):
    """GET 带重试：真实栈 audio_service 排队时列表接口会 60s 后 400，几分钟自愈。"""
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(API + path, timeout=180) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as exc:  # noqa: BLE001
            last = exc
            log('api_get retry', attempt, path[:40], str(exc)[:60])
            time.sleep(20)
    raise last


# ── 浏览器 ────────────────────────────────────────────────────────────
def chromedriver_path():
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = []
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    pass
    return sorted(cands, key=lambda c: c[0])[-1][1] if cands else ''


STUB_JS = r"""
window.__realFetch = window.fetch;
function jsonResponse(obj) {
  return new Response(JSON.stringify(obj), {status: 200,
    headers: {'Content-Type': 'application/json'}});
}
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const res = await window.__realFetch.apply(this, arguments);
  if (url.indexOf('/evaluation/dimensions') !== -1) {
    return jsonResponse({success: true, code: 0, message: 'Success', data: {items: [
      {id: 9901506, name: 'INT1506_LLM探针维度', description: 'stub', dimension_type: 'main',
       parent_id: null, category_id: 3, task_type_code: 'stub', result_type: 'llm_judge',
       result_min: 0, result_max: 100, decimal_places: 0, weight: 1, status: true,
       keywords: null, score_unit: null, api_url: null, api_settings: null, rule: null,
       associated_algorithms: [{algorithm_type: 'voice_llm', is_default: true, weight: 1}],
       required_inputs: [],
       llm_judge_config: {model: 'dim-model-from-config', prompt_template: 'dim-prompt-from-config',
                          max_tokens: 1024, temperature: 0.7},
       created_at: null, updated_at: null},
      {id: 9901507, name: 'INT1506_数值探针维度', description: 'stub', dimension_type: 'main',
       parent_id: null, category_id: 3, task_type_code: 'stub', result_type: 0,
       result_min: 0, result_max: 100, decimal_places: 0, weight: 1, status: true,
       keywords: null, score_unit: null, api_url: null, api_settings: null, rule: null,
       associated_algorithms: [{algorithm_type: 'voice_llm', is_default: true, weight: 1}],
       required_inputs: [], llm_judge_config: null,
       created_at: null, updated_at: null}
    ], total: 2}});
  }
  if (url.indexOf('/testcases') !== -1) {
    let body;
    try { body = await res.clone().json(); } catch (e) { return res; }
    const patch = (it) => {
      if (!it || typeof it !== 'object') return;
      if ((it.name || '').indexOf(arguments_name_hint) === -1) return;
      it.config = it.config || {};
      it.config.background_noise = {
        audioId: null, audioName: null, spl: 60, deviceIds: [3],
        deviceNames: [arguments_real_name, arguments_fake_name], loop: true};
    };
    const data = body && body.data;
    if (data && Array.isArray(data.items)) { data.items.forEach(patch); }
    else if (data && data.id) { patch(data); }
    return jsonResponse(body);
  }
  return res;
};
const arguments_name_hint = '__CASE_HINT__';
const arguments_real_name = '__REAL_NAME__';
const arguments_fake_name = '__FAKE_NAME__';
"""


def driver(stub_case=False):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    exe = chromedriver_path()
    d = webdriver.Chrome(service=Service(exe) if exe else Service(), options=o)
    d.set_script_timeout(120)
    d.set_page_load_timeout(120)
    if stub_case:
        js = (STUB_JS.replace('__CASE_HINT__', PROBE_CASE_MARK)
              .replace('__REAL_NAME__', REAL_DEVICE)
              .replace('__FAKE_NAME__', FAKE_DEVICE))
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': js})
    return d


def wait(d, sec=30):
    return WebDriverWait(d, sec)


def shot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    log('SHOT', path)
    return path


def set_theme(d, mode):
    d.get(BASE + '/testcases/by-group')
    wait(d, 90).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def enter_cases(d):
    d.get(BASE + '/testcases/by-group')
    wait(d, 90).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(4)


def expand_groups(d):
    d.execute_script("""
        const cards = Array.from(document.querySelectorAll('div.overflow-hidden'))
          .filter(g => g.querySelector("[aria-label^='全选分组']"));
        for (const g of cards) {
          if (g.querySelector("button[aria-label='编辑用例']")) continue;
          const spans = Array.from(g.querySelectorAll('span')).filter(s =>
            (s.textContent || '').trim().length > 1 && !s.getAttribute('aria-label') && s.children.length === 0);
          if (spans.length) spans[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        }
    """)
    time.sleep(1.5)


def search_case(d, keyword):
    box = wait(d, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(keyword)
    # 真实库用例列表首屏请求偶发 8~9s（并发时更慢）；轮询到卡片出现（最多 ~60s）
    hit = False
    for _ in range(24):
        time.sleep(2.5)
        expand_groups(d)
        hit = d.execute_script(
            "return document.querySelectorAll(\"button[aria-label='编辑用例']\").length > 0")
        if hit:
            break
    return bool(hit)


def select_case(d, name):
    r = d.execute_script("""
        const cb = document.querySelector('[aria-label="选择 ' + arguments[0] + '"]');
        if (!cb) return 'no-checkbox';
        cb.scrollIntoView({block: 'center'});
        if (cb.getAttribute('aria-checked') !== 'true') cb.click();
        return 'ok';
    """, name)
    time.sleep(0.7)
    return r


def open_drawer(d, name):
    if not search_case(d, name):
        raise AssertionError('用例卡未出现：%s' % name)
    r = d.execute_script("""
        const name = arguments[0];
        const cb = document.querySelector('[aria-label="选择 ' + name + '"]');
        if (!cb) return 'no-checkbox';
        let el = cb;
        for (let i = 0; i < 8 && el; i++) {
          el = el.parentElement;
          if (el && el.querySelector("button[aria-label='编辑用例']")) {
            const btn = el.querySelector("button[aria-label='编辑用例']");
            btn.scrollIntoView({block: 'center'}); btn.click(); return 'ok';
          }
        }
        return 'no-card';
    """, name)
    if r != 'ok':
        raise AssertionError('打开抽屉失败：%s' % r)
    wait(d, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']")))
    time.sleep(1.5)


def close_drawer(d):
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)


def click_drawer_tab(d, label):
    el = wait(d, 15).until(EC.element_to_be_clickable(
        (By.XPATH,
         "//*[@data-slot='sheet-content']//button[@role='tab'][contains(normalize-space(.), '%s')]" % label)))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(1.2)


def expand_strategy(d):
    r = d.execute_script("""
        const sheet = document.querySelector("[data-slot='sheet-content']");
        const b = Array.from(sheet.querySelectorAll('button[data-slot="collapsible-trigger"]'))
          .find(x => (x.textContent || '').indexOf('评估策略') !== -1);
        if (!b) return 'no-trigger';
        b.scrollIntoView({block: 'center'});
        if (b.getAttribute('aria-expanded') !== 'true') b.click();
        return 'ok';
    """)
    time.sleep(1.5)
    return r


def expected_device_labels(devices):
    out = []
    for x in devices:
        t = x.get('device_type')
        tag = '干声' if t == 'dry' else '噪声' if t == 'noise' else (t or '未知')
        out.append('%s (通道 %s) [%s]' % (x.get('name'), x.get('channel_index'), tag))
    return out


# ── ① 评估维度参数卡 ──────────────────────────────────────────────────
def check_dimension_real(d):
    click_drawer_tab(d, '评估维度')
    info = d.execute_script("""
        const sheet = document.querySelector("[data-slot='sheet-content']");
        const txt = sheet ? sheet.textContent : '';
        return {modelInputs: document.querySelectorAll("input[id^='dim-model-']").length,
                hasGpt35: txt.indexOf('gpt-3.5-turbo') !== -1,
                hasClaudeOpus: txt.indexOf('claude-3-opus') !== -1,
                hasClaudeSonnet: txt.indexOf('claude-3-sonnet') !== -1,
                hasGpt4o: txt.indexOf('gpt-4o') !== -1,
                hasGpt4: txt.indexOf('gpt-4') !== -1};
    """)
    ok = not any([info['hasGpt35'], info['hasClaudeOpus'], info['hasClaudeSonnet'],
                  info['hasGpt4o'], info['hasGpt4']])
    return check('① 抽屉无写死模型/Prompt 文本', ok, json.dumps(info, ensure_ascii=True))


def check_dimension_stub(d):
    click_drawer_tab(d, '评估维度')
    picked = []
    for name in ('INT1506_LLM探针维度', 'INT1506_数值探针维度'):
        hit = d.execute_script("""
            const sheet = document.querySelector("[data-slot='sheet-content']");
            const b = Array.from(sheet.querySelectorAll('button[aria-pressed]'))
              .find(x => x.textContent.includes(arguments[0]));
            if (!b) return false;
            b.scrollIntoView({block: 'center'});
            if (b.getAttribute('aria-pressed') !== 'true') b.click();
            return true;
        """, name)
        time.sleep(1.2)
        if hit:
            picked.append(name)
    time.sleep(0.8)
    info = d.execute_script("""
        const sheet = document.querySelector("[data-slot='sheet-content']");
        const txt = sheet ? sheet.textContent : '';
        return {model: Array.from(document.querySelectorAll("input[id^='dim-model-']")).map(e => e.id + '=' + e.value),
                prompt: Array.from(document.querySelectorAll("input[id^='dim-prompt-']")).map(e => e.id + '=' + e.value),
                numericHasModel: !!document.querySelector("input[id='dim-model-9901507']"),
                hardcoded: ['gpt-3.5-turbo','claude-3-opus','claude-3-sonnet','gpt-4o','gpt-4']
                  .filter(m => txt.indexOf(m) !== -1)};
    """)
    info['picked'] = picked
    log('dimension stub', json.dumps(info, ensure_ascii=True))
    ok = (picked == ['INT1506_LLM探针维度', 'INT1506_数值探针维度']
          and info['model'] == ['dim-model-9901506=dim-model-from-config']
          and info['prompt'] == ['dim-prompt-9901506=dim-prompt-from-config']
          and not info['numericHasModel'] and not info['hardcoded'])
    return check('①b LLM 参数卡为自由文本、默认取维度 llmJudgeConfig（响应桩）', ok,
                 json.dumps(info, ensure_ascii=True))


# ── ② 全局背景噪声播放设备 ────────────────────────────────────────────
def read_noise_chips(d):
    try:
        wait(d, 30).until(lambda x: x.execute_script("""
            const sheet = document.querySelector("[data-slot='sheet-content']");
            if (!sheet) return false;
            return Array.from(sheet.querySelectorAll('button[aria-pressed]'))
              .some(b => (b.textContent || '').indexOf('通道') !== -1);
        """))
    except Exception:
        pass
    time.sleep(0.8)
    return d.execute_script("""
        const sheet = document.querySelector("[data-slot='sheet-content']");
        const btns = Array.from(sheet.querySelectorAll('button[aria-pressed]'))
          .filter(b => (b.textContent || '').indexOf('通道') !== -1);
        const txt = sheet.textContent;
        const warnIdx = txt.indexOf('未匹配到播放设备ID');
        return {chips: btns.map(b => b.textContent.trim()),
                pressed: btns.filter(b => b.getAttribute('aria-pressed') === 'true')
                  .map(b => b.textContent.trim()),
                warnText: warnIdx === -1 ? '' : txt.slice(warnIdx, warnIdx + 80)};
    """)


def check_noise_devices(d, devices, expect_unmatched=False):
    # INT-1424 起「全局背景噪声」是抽屉内常驻节（不在「评估策略」折叠节里）；
    # 旧版折叠节若存在则先展开，不存在（no-trigger）属正常形态。
    expand_strategy(d)
    info = read_noise_chips(d)
    expected = expected_device_labels(devices)
    missing = [t for t in expected if t not in info['chips']]
    extra = [t for t in info['chips'] if t not in expected]
    warn = info['warnText']
    if expect_unmatched:
        # 真实库设备表会被并发卡增删（本次实测期间新增 2 条），逐条相等会误判；
        # 这里断言「每条 chip 都来自真实列表」+ 已选设备回填 + 未匹配判定。
        expected_pressed = [t for t in expected if REAL_DEVICE in t]
        unknown_chips = [t for t in info['chips'] if t not in expected]
        ok = (not unknown_chips and info['chips'] and
              info['pressed'] == expected_pressed
              and FAKE_DEVICE in warn and REAL_DEVICE not in warn)
        label = '②b 未匹配判定以真实列表为准：真实名不误报、列表外名被标（响应桩）'
    else:
        ok = (not missing and not extra and len(info['chips']) == len(expected) and not warn)
        if not ok:
            # 并发卡可能在本 run 取快照之后增删真实设备：重取一次快照再判（避免误报）
            expected = expected_device_labels(
                api_get('/playback-devices?per_page=200')['data']['items'])
            info = read_noise_chips(d)
            missing = [t for t in expected if t not in info['chips']]
            extra = [t for t in info['chips'] if t not in expected]
            warn = info['warnText']
            ok = (not missing and not extra and len(info['chips']) == len(expected) and not warn)
        label = '② 噪声设备 chips == GET /playback-devices（%d 条）' % len(expected)
    detail = {'chips': len(info['chips']), 'expected': len(expected), 'missing': missing[:3],
              'extra': extra[:3], 'pressed': info['pressed'], 'warn': warn}
    return check(label, ok, json.dumps(detail, ensure_ascii=False))


# ── ③ 批量设置评估维度轮次 ────────────────────────────────────────────
def open_batch_dialog(d):
    try:
        wait(d, 20).until(lambda x: len(x.find_elements(
            By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")) > 0)
        btn = d.find_element(By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")
        d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', btn)
        wait(d, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//*[@data-slot='dialog-content'][.//*[contains(., '批量设置评估维度')]]")))
        time.sleep(1.0)
        return True
    except Exception as exc:  # noqa: BLE001
        log('batch dialog failed', str(exc)[:120])
        return False


def read_batch_rounds(d):
    d.execute_script("""
        const labels = Array.from(document.querySelectorAll("[data-slot='dialog-content'] label"));
        const l = labels.find(x => x.textContent.includes('逐轮设置'));
        if (l) l.click();
    """)
    time.sleep(1.2)
    per_round = sorted({b.text.strip() for b in d.find_elements(
        By.XPATH,
        "//*[@data-slot='dialog-content']//button[starts-with(normalize-space(.), '第') and contains(normalize-space(.), '轮')]")
        if '添加' not in b.text})
    d.execute_script("""
        const labels = Array.from(document.querySelectorAll("[data-slot='dialog-content'] label"));
        const l = labels.find(x => x.textContent.includes('指定轮次'));
        if (l) l.click();
    """)
    time.sleep(1.0)
    specific = sorted({l.text.strip() for l in d.find_elements(
        By.XPATH,
        "//*[@data-slot='dialog-content']//label[contains(normalize-space(.), '第') and contains(normalize-space(.), '轮')]")
        if '指定轮次' not in l.text})
    txt = d.execute_script(
        "const el=document.querySelector(\"[data-slot='dialog-content']\"); return el ? el.textContent : '';")
    no_extra = all(t not in txt for t in ('第 3 轮', '第3轮', '第 4 轮', '第4轮'))
    return per_round, specific, no_extra


def check_batch_rounds(d, keyword, names, expected):
    if not search_case(d, keyword):
        return check('③ 批量用例卡出现', False, keyword)
    for n in names:
        log('select', n[:30], select_case(d, n))
    if not open_batch_dialog(d):
        return check('③ 批量设置评估维度弹窗打开', False, keyword)
    per_round, specific, no_extra = read_batch_rounds(d)
    log('per-round tabs', json.dumps(per_round, ensure_ascii=True))
    log('specific rounds', json.dumps(specific, ensure_ascii=True))
    ok = (per_round == ['第 %d 轮' % i for i in expected]
          and specific == ['第%d轮' % i for i in expected]
          and no_extra)
    return check('③ 批量轮次页签 == 选中用例实际轮次（期望 %d 轮）' % len(expected), ok,
                 json.dumps({'per_round': per_round, 'specific': specific, 'no_extra': no_extra},
                            ensure_ascii=False))


# ── ④ 试听弹窗 ────────────────────────────────────────────────────────
def check_preview(d, case_item):
    name = case_item['name']
    if not search_case(d, name):
        return check('④ 试听用例卡出现', False, name)
    clicked = d.execute_script("""
        const name = arguments[0];
        const cb = document.querySelector('[aria-label="选择 ' + name + '"]');
        if (!cb) return 'no-checkbox';
        let el = cb;
        for (let i = 0; i < 8 && el; i++) {
          el = el.parentElement;
          if (el && el.querySelector("button[aria-label='预览音频']")) {
            const btn = el.querySelector("button[aria-label='预览音频']");
            btn.scrollIntoView({block: 'center'}); btn.click(); return 'ok';
          }
        }
        return 'no-card';
    """, name)
    if clicked != 'ok':
        return check('④ 打开音频试听配置', False, clicked)
    try:
        wait(d, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//*[@data-slot='dialog-content'][.//*[contains(., '音频试听配置')]]")))
        time.sleep(0.8)
        d.execute_script("""
            const labels = Array.from(document.querySelectorAll("[data-slot='dialog-content'] label"));
            const l = labels.find(x => x.textContent.includes('实验室播放'));
            if (l) l.click();
        """)
        time.sleep(0.6)
        start = wait(d, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//*[@data-slot='dialog-content']//button[normalize-space(.)='开始试听']")))
        d.execute_script('arguments[0].click();', start)
        # 实验室播放无浏览器音频流，总时长先显示 00:00，等音频库时长回填（≤15s）
        for _ in range(15):
            time.sleep(1.0)
            if d.execute_script(
                    "const t=(document.querySelector(\"[data-slot='dialog-content']\")||{}).textContent||'';"
                    "return /\\d{2}:\\d{2} \\/ (?!00:00)\\d{2}:\\d{2}/.test(t)"):
                break
    except Exception as exc:  # noqa: BLE001
        return check('④ 试听播放器打开', False, str(exc)[:120])
    info = d.execute_script("""
        const root = document.querySelector("[data-slot='dialog-content']");
        const txt = root ? root.textContent : '';
        const m = txt.match(/(\\d{2}:\\d{2}) \\/ (\\d{2}:\\d{2})/);
        return {clock: m ? [m[1], m[2]] : null,
                fake42: txt.indexOf('00:42') !== -1,
                devices: Array.from(root.querySelectorAll('p')).map(p => p.textContent.trim())
                  .filter(t => t.indexOf('\\u2713') === 0)};
    """)
    # 口径（INT-1424 版用例行预览，交付已按集成目标取该版本）：预览首轮首个音频，
    # 时长取该音频 duration（非用例 total_duration 合计），设备取该音频的
    # playback_device_name。因此按「首音频」核对，并容忍 ±1s 的取整差异。
    first = next((a for r in ((case_item.get('config') or {}).get('rounds') or [])
                  for a in (r.get('audios') or [])), None) or {}
    expected_sec = first.get('duration')
    if expected_sec is None:
        expected_sec = first.get('audio_duration')
    if expected_sec is None:
        audio_id = first.get('audio_id') or first.get('audioId')
        if audio_id is not None:
            expected_sec = api_get('/audios/%s' % audio_id)['data'].get('duration')
    if expected_sec is None:
        expected_sec = case_item.get('total_duration') or 0
    expected_clock = '%02d:%02d' % (int(expected_sec) // 60, int(expected_sec) % 60)
    expected_devices = sorted({first.get('playback_device_name')} - {None})
    actual = sorted(t.lstrip('✓').strip() for t in info['devices'])
    actual_sec = None
    if info['clock']:
        mm, ss = info['clock'][1].split(':')
        actual_sec = int(mm) * 60 + int(ss)
    ok = (actual_sec is not None and abs(actual_sec - float(expected_sec)) <= 1
          and not info['fake42'] and actual == expected_devices)
    info.update({'expected_clock': expected_clock, 'expected_sec': expected_sec,
                 'case_total_duration': case_item.get('total_duration'),
                 'expected_devices': expected_devices, 'actual_devices': actual})
    return check('④ 试听时长/设备取首音频真实数据（%s + 该音频设备）' % expected_clock, ok,
                 json.dumps(info, ensure_ascii=False))


def close_dialogs(d):
    for _ in range(3):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.5)


def pick_cases():
    """按用例号精确取验收样本（真实库只读）：HJ050/HJ049 两轮带音频设备，JG0081 单轮。"""
    hj050 = api_get('/testcases?page=1&per_page=5&keyword=HJ050')['data']['items']
    audio_case = next((c for c in hj050 if 'HJ050' in c['name']), hj050[0])
    hj049 = api_get('/testcases?page=1&per_page=5&keyword=HJ049')['data']['items']
    pair = next((c for c in hj049 if 'HJ049' in c['name']), hj049[0])
    jg = api_get('/testcases?page=1&per_page=5&keyword=JG0081')['data']['items']
    one_case = next((c for c in jg if len(((c.get('config') or {}).get('rounds') or [])) == 1), jg[0])
    return None, audio_case, one_case, [pair]


def main():
    devices = api_get('/playback-devices?per_page=200')['data']['items']
    log('playback devices:', len(devices))
    items, audio_case, one_case, two_pair = pick_cases()
    log('audio case:', audio_case['name'][:40], 'dur', audio_case.get('total_duration'))
    if not one_case:
        raise SystemExit('真实库未找到 1 轮用例，无法验证轮次口径')
    m = re.search(r'JG\d+', one_case['name'])
    single_kw = m.group(0) if m else one_case['name'][:8]
    log('one-round case:', one_case['name'][:40], 'kw', single_kw)

    # ── 真实数据：浅色 ────────────────────────────────────────────────
    if 'light' in SECTIONS:
        d = driver()
        try:
            set_theme(d, 'light')
            enter_cases(d)
            open_drawer(d, audio_case['name'])
            check_dimension_real(d)
            check_noise_devices(d, devices)
            shot(d, 'drawer_dimension_noise_light.png')
            close_drawer(d)
            check_preview(d, audio_case)
            close_dialogs(d)

            enter_cases(d)
            check_batch_rounds(d, 'HJ0', [audio_case['name']] + [c['name'] for c in two_pair], [1, 2])
            shot(d, 'batch_dimensions_light.png')
            close_dialogs(d)
        finally:
            d.quit()

    if 'light1' in SECTIONS:
        d = driver()
        try:
            set_theme(d, 'light')
            enter_cases(d)
            check_batch_rounds(d, single_kw, [one_case['name']], [1])
            close_dialogs(d)
        finally:
            d.quit()

    # ── 真实数据：深色 ────────────────────────────────────────────────
    if 'dark' in SECTIONS:
        d = driver()
        try:
            set_theme(d, 'dark')
            enter_cases(d)
            theme_ok = d.execute_script("return document.documentElement.classList.contains('dark')")
            check('⑤ 深色主题生效', theme_ok)
            open_drawer(d, audio_case['name'])
            check_dimension_real(d)
            check_noise_devices(d, devices)
            shot(d, 'drawer_dimension_noise_dark.png')
            close_drawer(d)
            enter_cases(d)
            check_batch_rounds(d, 'HJ0', [audio_case['name']] + [c['name'] for c in two_pair], [1, 2])
            shot(d, 'batch_dimensions_dark.png')
            close_dialogs(d)
        finally:
            d.quit()

    # ── 响应桩：LLM 参数卡 + 未匹配设备名 ────────────────────────────
    if 'stub' not in SECTIONS:
        return finish()
    d = driver(stub_case=True)
    try:
        enter_cases(d)
        open_drawer(d, audio_case['name'])
        check_dimension_stub(d)
        close_drawer(d)
        enter_cases(d)
        open_drawer(d, audio_case['name'])
        check_noise_devices(d, devices, expect_unmatched=True)
        shot(d, 'noise_unmatched_stub.png')
        close_drawer(d)
    finally:
        d.quit()

    return finish()


def finish():
    log('RESULT', json.dumps(RESULTS, ensure_ascii=True))
    all_ok = all(RESULTS.values())
    log('ALL', 'PASS' if all_ok else 'FAIL')
    with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as fh:
        json.dump({'results': RESULTS, 'logs': LOGS}, fh, ensure_ascii=False, indent=1)
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
