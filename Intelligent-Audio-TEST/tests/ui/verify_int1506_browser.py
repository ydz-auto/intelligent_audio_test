# -*- coding: utf-8 -*-
"""INT-1506 浏览器实测（docker 旁路栈 15276 → api_gateway 15000，真实库）。

覆盖验收标准：
1. 用例编辑抽屉 → 评估维度 → 参数卡：无 gpt-4/claude-3 等写死模型选项、无写死默认模型；
   非 LLM 维度只渲染权重/阈值（LLM 分支在真实库不可达——见 --stub-llm 响应桩探测）。
2. 全局背景噪声播放设备 chips == 真实 GET /playback-devices（名称/通道/类型逐条一致），
   真实设备名不被标「未匹配到播放设备ID」。
3. 批量设置评估维度：逐轮 / 指定轮次只出选中用例实际轮次（本库样本 2 轮），不出第 3/4 轮。
4. 试听弹窗时长取用例 total_duration（非固定 42s）、设备取用例 config.rounds[].audios。

用法：
  REACT_BASE=http://127.0.0.1:15276 python verify_int1506_browser.py
  python verify_int1506_browser.py --stub-llm   # 响应桩注入 llm_judge 维度，验参数卡 LLM 分支
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15276')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_CACHE = os.path.join(
    os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1506')
os.makedirs(ART, exist_ok=True)

RESULTS = {}


def log(*args):
    print(' '.join(str(a) for a in args), flush=True)


def chromedriver_path():
    if not os.path.isdir(DRIVER_CACHE):
        return None
    cands = []
    for ver in os.listdir(DRIVER_CACHE):
        exe = os.path.join(DRIVER_CACHE, ver, 'chromedriver.exe')
        if os.path.isfile(exe):
            cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
    return max(cands)[1] if cands else None


STUB_JS = r"""
(() => {
  const orig = window.fetch;
  window.fetch = async function (...args) {
    const res = await orig.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    if (url.indexOf('/evaluation/dimensions') >= 0 && res.ok) {
      try {
        const j = await res.clone().json();
        if (j && j.data && Array.isArray(j.data.items)) {
          const assoc = [{algorithm_type: 'voice_llm', is_default: false, weight: 5}];
          j.data.items = j.data.items.concat([{
            id: 9901506, name: 'INT1506_LLM探针维度', description: '响应桩（不落库）',
            dimension_type: 'main', parent_dimension_id: null, category_id: null,
            type: 'accuracy', result_type: 'llm_judge', result_min: 0, result_max: 100,
            decimal_places: 2, weight: 5, estimated_exec_time: 10, rule: {rules: []},
            status: true, api_status: 'enabled', sort_order: 0,
            llm_judge_config: {model: 'dim-model-from-config', promptTemplate: 'dim-prompt-from-config',
                               max_tokens: 1024, temperature: 0.7},
            associated_algorithms: assoc
          }, {
            id: 9901507, name: 'INT1506_数值探针维度', description: '响应桩（不落库）',
            dimension_type: 'main', parent_dimension_id: null, category_id: null,
            type: 'accuracy', result_type: 0, result_min: 0, result_max: 100,
            decimal_places: 2, weight: 5, estimated_exec_time: 10, rule: {rules: []},
            status: true, api_status: 'enabled', sort_order: 0,
            associated_algorithms: assoc
          }]);
        }
        return new Response(JSON.stringify(j), {
          status: res.status, headers: {'Content-Type': 'application/json'}});
      } catch (e) { return res; }
    }
    return res;
  };
})();
"""


def driver(stub_llm=False):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    exe = chromedriver_path()
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_script_timeout(120)
    if stub_llm:
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': STUB_JS})
    return d


def wait(d, sec=30):
    return WebDriverWait(d, sec)


def body_text(d):
    return d.execute_script('return document.body.textContent') or ''


def fetch_json(d, path):
    raw = d.execute_async_script(
        """
        const path = arguments[0]; const cb = arguments[arguments.length - 1];
        fetch(path, {credentials: 'include'}).then(r => r.text())
          .then(t => cb(t)).catch(e => cb('ERR:' + e));
        """, path)
    try:
        return json.loads(raw)
    except Exception:
        return {'raw': raw[:400]}


def set_theme(d, mode):
    d.get(BASE + '/testcases/by-group')
    wait(d, 60).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def enter_cases(d):
    d.get(BASE + '/testcases/by-group')
    wait(d, 90).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(1)


def search_case(d, name):
    box = wait(d, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(name)
    time.sleep(2.5)
    for _ in range(3):
        expand_groups(d)
        try:
            wait(d, 20).until(
                lambda x: x.execute_script(
                    "return document.querySelectorAll("
                    "\"button[aria-label='编辑用例']\").length > 0"))
            return
        except Exception:
            time.sleep(1.5)
    raise AssertionError('用例卡未出现：%s' % name)


def expand_groups(d):
    """分组默认收起：点所有组头展开（首屏 DOM 里没有已展开的组卡时点一次即可）。"""
    headers = d.find_elements(
        By.XPATH, "//div[contains(@class,'cursor-pointer') and .//span[contains(., '条')]]")
    for h in headers:
        try:
            d.execute_script('arguments[0].scrollIntoView({block:"center"});', h)
            h.click()
        except Exception:
            pass
    time.sleep(0.8)


def open_drawer(d, name):
    search_case(d, name)
    ok = d.execute_script(
        """
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
    log('open drawer', ok)
    wait(d, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']")))
    time.sleep(1.2)


def close_drawer(d):
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)


def switch_drawer_tab(d, label):
    el = wait(d, 15).until(EC.element_to_be_clickable(
        (By.XPATH,
         "//*[@data-slot='sheet-content']//button[@role='tab'][contains(normalize-space(.), '%s')]" % label)))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(1.2)


def shot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    log('shot', path)


# ── ① 评估维度参数卡：无写死模型/模板选项 ─────────────────────────────
def check_dimension_card(d):
    switch_drawer_tab(d, '评估维度')
    # 勾选第一个可用维度 chip（DimensionPicker 圆形 chip）
    clicked = d.execute_script(
        """
        const sheet = document.querySelector("[data-slot='sheet-content']");
        const btns = Array.from(sheet.querySelectorAll('button[aria-pressed]'))
          .filter(b => b.getAttribute('aria-pressed') === 'false'
                       && b.textContent.trim().length > 0
                       && !b.textContent.includes('通道'));
        if (!btns.length) return 'no-chip';
        btns[0].scrollIntoView({block: 'center'});
        btns[0].click();
        return btns[0].textContent.trim();
        """)
    time.sleep(1.2)
    info = d.execute_script(
        """
        const sheet = document.querySelector("[data-slot='sheet-content']");
        const body = document.body.textContent || '';
        const modelInputs = Array.from(document.querySelectorAll("input[id^='dim-model-']"))
          .map(e => e.value);
        const promptInputs = Array.from(document.querySelectorAll("input[id^='dim-prompt-']"))
          .map(e => e.value);
        const hardcoded = ['gpt-3.5-turbo','claude-3-opus','claude-3-sonnet','gpt-4o','gpt-4']
          .filter(m => body.includes(m));
        const cardSel = "[data-slot='sheet-content'] .rounded-lg";
        return {modelInputs, promptInputs, hardcoded,
                selectTriggers: sheet.querySelectorAll("[data-slot='select-trigger']").length};
        """)
    info['chip'] = clicked
    log('dimension card', json.dumps(info, ensure_ascii=True))
    # 真实库当前维度均无 associated_algorithms → 「暂无可用维度」，参数卡不渲染；
    # 此时只判定「整抽屉无写死模型文本」。参数卡本身由 --stub-llm 响应桩覆盖。
    ok = (not info['hardcoded']) and (clicked == 'no-chip' or len(info['modelInputs']) == 0)
    RESULTS['dimension_card'] = ok
    log('① 无写死模型判定', 'PASS' if ok else 'FAIL', '(chip=%s)' % clicked)
    return ok


def check_dimension_card_stub(d):
    """响应桩注入 llm_judge + 数值维度：LLM 参数卡应渲染两个自由文本输入（默认为维度配置），
    无数值下拉；数值维度只渲染权重/阈值。"""
    switch_drawer_tab(d, '评估维度')
    # 逐个点选（同一事件循环内连点两次会用同一次 render 的旧 value 覆盖，只留住最后一个）
    picked = []
    for name in ('INT1506_LLM探针维度', 'INT1506_数值探针维度'):
        hit = d.execute_script(
            """
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
    info = d.execute_script(
        """
        const model = Array.from(document.querySelectorAll("input[id^='dim-model-']"))
          .map(e => e.id + '=' + e.value);
        const prompt = Array.from(document.querySelectorAll("input[id^='dim-prompt-']"))
          .map(e => e.id + '=' + e.value);
        const sheet = document.querySelector("[data-slot='sheet-content']");
        const body = document.body.textContent || '';
        return {
          model, prompt,
          numericDimHasModelInput: !!document.querySelector("input[id='dim-model-9901507']"),
          combosInSheet: sheet.querySelectorAll("[role='combobox']").length,
          hardcoded: ['gpt-3.5-turbo','claude-3-opus','claude-3-sonnet','gpt-4o','gpt-4']
            .filter(m => body.includes(m)),
          text: sheet.textContent.slice(0, 300),
        };
        """)
    info["picked"] = picked
    log('stub dimension card', json.dumps(info, ensure_ascii=True))
    ok = (picked == ['INT1506_LLM探针维度', 'INT1506_数值探针维度']
          and info["model"] == ["dim-model-9901506=dim-model-from-config"]
          and info['prompt'] == ['dim-prompt-9901506=dim-prompt-from-config']
          and not info['numericDimHasModelInput']
          and not info['hardcoded'])
    RESULTS['dimension_card_llm_branch'] = ok
    log('①b LLM/数值分支判定', 'PASS' if ok else 'FAIL')
    return ok


# ── ② 全局背景噪声播放设备 chips == 真实设备列表 ──────────────────────
def expected_device_labels(devices):
    out = []
    for x in devices:
        t = x.get('device_type')
        tag = '干声' if t == 'dry' else '噪声' if t == 'noise' else (t or '未知')
        out.append('%s (通道 %s) [%s]' % (x.get('name'), x.get('channel_index'), tag))
    return out


def check_noise_devices(d, devices):
    trigger = wait(d, 15).until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@data-slot='sheet-content']//button[contains(normalize-space(.), '评估策略')]")))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', trigger)
    time.sleep(1.5)
    chips = d.find_elements(
        By.XPATH,
        "//*[@data-slot='sheet-content']//button[@aria-pressed and contains(normalize-space(.), '通道')]")
    if chips:
        d.execute_script('arguments[0].scrollIntoView({block:"center"});', chips[0])
        time.sleep(0.4)
    chip_texts = [c.text.strip() for c in chips]
    expected = expected_device_labels(devices)
    missing = [t for t in expected if t not in chip_texts]
    extra = [t for t in chip_texts if t not in expected]
    warn = '未匹配到播放设备ID' in body_text(d)
    info = {'chips': len(chip_texts), 'expected': len(expected), 'missing': missing[:3],
            'extra': extra[:3], 'unmatched_warning': warn}
    log('noise chips', json.dumps(info, ensure_ascii=True))
    ok = not missing and not extra and not warn and len(chip_texts) == len(expected)
    RESULTS['noise_devices'] = ok
    log('② 播放设备判定', 'PASS' if ok else 'FAIL')
    return ok


# ── ③ 批量设置评估维度：轮次按实际用例 ────────────────────────────────
def select_case(d, name):
    ok = d.execute_script(
        """
        const cb = document.querySelector('[aria-label="选择 ' + arguments[0] + '"]');
        if (!cb) return false;
        cb.scrollIntoView({block: 'center'});
        if (cb.getAttribute('aria-checked') !== 'true') cb.click();
        return true;
        """, name)
    time.sleep(0.6)
    return ok


def check_batch_rounds(d, names, expected_rounds):
    for n in names:
        search_case(d, n)
        log('select', n[:20], select_case(d, n))
    wait(d, 20).until(lambda x: len(x.find_elements(
        By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")) > 0)
    btn = d.find_element(By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")
    d.execute_script('arguments[0].click();', btn)
    wait(d, 15).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@data-slot='dialog-content'][.//*[contains(., '批量设置评估维度')]]")))
    time.sleep(1.0)

    d.execute_script(
        """
        const labels = Array.from(document.querySelectorAll("[data-slot='dialog-content'] label"));
        const l = labels.find(x => x.textContent.includes('逐轮设置'));
        if (l) { l.click(); }
        """)
    time.sleep(1.2)
    per_round = sorted({b.text.strip() for b in d.find_elements(
        By.XPATH,
        "//*[@data-slot='dialog-content']//button[starts-with(normalize-space(.), '第') and contains(normalize-space(.), '轮')]")
        if '添加' not in b.text})
    d.execute_script(
        """
        const labels = Array.from(document.querySelectorAll("[data-slot='dialog-content'] label"));
        const l = labels.find(x => x.textContent.includes('指定轮次'));
        if (l) { l.click(); }
        """)
    time.sleep(1.0)
    specific = sorted({l.text.strip() for l in d.find_elements(
        By.XPATH,
        "//*[@data-slot='dialog-content']//label[contains(normalize-space(.), '第') and contains(normalize-space(.), '轮')]")
        if '指定轮次' not in l.text})
    expected_space = ['第 %d 轮' % i for i in range(1, expected_rounds + 1)]
    expected_cn = ['第%d轮' % i for i in range(1, expected_rounds + 1)]
    log('per-round tabs', json.dumps(per_round, ensure_ascii=True))
    log('specific rounds', json.dumps(specific, ensure_ascii=True))
    ok = per_round == expected_space and specific == expected_cn
    RESULTS['batch_rounds'] = ok
    log('③ 批量轮次判定', 'PASS' if ok else 'FAIL')
    return ok


# ── ④ 试听弹窗时长/设备取真实用例 ────────────────────────────────────
def check_preview(d, case_item):
    search_case(d, case_item['name'])
    clicked = d.execute_script(
        """
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
        """, case_item['name'])
    log('open preview', clicked)
    wait(d, 15).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@data-slot='dialog-content'][.//*[contains(., '音频试听配置')]]")))
    time.sleep(0.8)
    # 实验室播放（后端播放）才有设备信息区；浏览器播放按设计显示「不分设备」
    d.execute_script(
        """
        const labels = Array.from(document.querySelectorAll(
          "[data-slot='dialog-content'] label"));
        const l = labels.find(x => x.textContent.includes('实验室播放'));
        if (l) l.click();
        """)
    time.sleep(0.6)
    start = wait(d, 10).until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@data-slot='dialog-content']//button[normalize-space(.)='开始试听']")))
    d.execute_script('arguments[0].click();', start)
    time.sleep(1.5)
    info = d.execute_script(
        """
        const root = document.querySelector("[data-slot='dialog-content']");
        const txt = root ? root.textContent : '';
        const m = txt.match(/(\\d{2}:\\d{2}) \\/ (\\d{2}:\\d{2})/);
        return {clock: m ? [m[1], m[2]] : null,
                hasFakeDuration: txt.includes('00:42'),
                browserNoDevice: txt.includes('浏览器播放不分设备'),
                devices: Array.from(root.querySelectorAll('p'))
                  .map(p => p.textContent.trim())
                  .filter(t => t.indexOf('\\u2713') === 0)};
        """)
    dur = int(round(case_item.get('total_duration') or 0))
    expected_clock = '%02d:%02d' % (dur // 60, dur % 60)
    expected_devices = sorted({
        a.get('playback_device_name')
        for r in ((case_item.get('config') or {}).get('rounds') or [])
        for a in (r.get('audios') or [])
        if a.get('playback_device_name')
    })
    info['expected_duration'] = expected_clock
    info['expected_devices'] = expected_devices
    actual_devices = sorted(t.lstrip('✓').strip() for t in info['devices'])
    info['actual_devices'] = actual_devices
    log('preview player', json.dumps(info, ensure_ascii=True))
    ok = (info['clock'] is not None and info['clock'][1] == expected_clock
          and not info['hasFakeDuration'] and actual_devices == expected_devices)
    RESULTS['preview_player'] = ok
    log('④ 试听时长/设备判定', 'PASS' if ok else 'FAIL')
    shot(d, 'preview_player_light.png')
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    return ok


def close_dialogs(d):
    for _ in range(3):
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)


def main():
    stub_llm = '--stub-llm' in sys.argv
    d = driver(stub_llm)
    try:
        enter_cases(d)
        devices = fetch_json(d, '/api/v1/playback-devices?per_page=200')['data']['items']
        cases = fetch_json(d, '/api/v1/testcases?page=1&per_page=100')['data']['items']
        two_round = [c for c in cases
                     if len(((c.get('config') or {}).get('rounds') or [])) == 2]
        audio_case = next(c for c in two_round
                          if (c.get('total_duration') or 0) > 0
                          and any((r.get('audios') or []) for r in c['config']['rounds']))
        log('devices', len(devices), 'cases', len(cases), 'two_round', len(two_round))
        log('sample', audio_case['name'][:24], 'duration', audio_case['total_duration'])

        if stub_llm:
            open_drawer(d, audio_case['name'])
            check_dimension_card_stub(d)
            shot(d, 'llm_dimension_branch.png')
            close_drawer(d)
            log('RESULT', json.dumps(RESULTS, ensure_ascii=True))
            return

        # 浅色
        set_theme(d, 'light')
        enter_cases(d)
        open_drawer(d, audio_case['name'])
        check_dimension_card(d)
        check_noise_devices(d, devices)
        shot(d, 'drawer_dimension_noise_light.png')
        close_drawer(d)
        check_preview(d, audio_case)
        check_batch_rounds(d, [audio_case['name'], two_round[1]['name']], 2)
        shot(d, 'batch_dimensions_light.png')
        close_dialogs(d)

        # 深色
        set_theme(d, 'dark')
        enter_cases(d)
        open_drawer(d, audio_case['name'])
        check_dimension_card(d)
        check_noise_devices(d, devices)
        shot(d, 'drawer_dimension_noise_dark.png')
        close_drawer(d)
        check_batch_rounds(d, [audio_case['name'], two_round[1]['name']], 2)
        shot(d, 'batch_dimensions_dark.png')
        close_dialogs(d)
        set_theme(d, 'light')

        log('RESULT', json.dumps(RESULTS, ensure_ascii=True))
        log('ALL', 'PASS' if all(RESULTS.values()) else 'FAIL')
    finally:
        d.quit()


if __name__ == '__main__':
    main()
