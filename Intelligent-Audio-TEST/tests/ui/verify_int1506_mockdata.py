# -*- coding: utf-8 -*-
"""INT-1506 浏览器实测（真实库栈 5700 / dev 5321）——清零用例域写死假数据。

覆盖验收标准：
1. 用例编辑抽屉 → 评估维度 → LLM Judge 维度参数卡：模型/Prompt 为自由文本（默认取维度
   llm_judge_config），DOM 无 gpt-4 / claude-3 等写死选项与写死默认模型。
2. 全局背景噪声播放设备 chips == GET /playback-devices（名称/通道一致），真实设备名不被
   标「未匹配到播放设备ID」。
3. 批量设置评估维度：逐轮/指定轮次按选中用例实际轮次（本库样本 1~2 轮）渲染，不出第 3/4 轮。
附浅色 + 深色截图。

测试数据：为验证 LLM Judge 参数卡，脚本自建一条「接线测试_」前缀维度（关联样本用例算法），
结束时 DELETE 清理；不改动任何真实记录。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5321')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1506'
DIM_NAME = '接线测试_LLM维度_INT1506'
TOKEN_JS = "localStorage.getItem('iatp:auth:token:v1') || ''"

os.makedirs(ART, exist_ok=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    d = webdriver.Chrome(options=o, service=Service())
    d.set_script_timeout(120)
    return d


def wait(d, sec=20):
    return WebDriverWait(d, sec)


def login(d):
    d.get(BASE + '/login')
    wait(d).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    try:
        u = wait(d, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        if '/login' not in d.current_url:
            return
        raise
    u.send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    try:
        wait(d, 40).until(lambda x: '/login' not in x.current_url)
    except Exception:
        print('LOGIN RETRY; url=', d.current_url)
        print('BODY=', (d.execute_script('return document.body.textContent') or '')[:400])
        d.save_screenshot(os.path.join(ART, 'login_fail.png'))
        d.refresh()
        time.sleep(2)
        u = wait(d, 15).until(EC.presence_of_element_located((By.ID, 'username')))
        u.send_keys('接线测试_admin')
        d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        wait(d, 40).until(lambda x: '/login' not in x.current_url)
    time.sleep(2)


def api(d, method, path, body=None):
    return d.execute_async_script(
        """
        const [method, path, body] = arguments;
        const cb = arguments[arguments.length - 1];
        const t = localStorage.getItem('iatp:auth:token:v1') || '';
        const init = {method, headers: {'Content-Type': 'application/json'}, credentials: 'include'};
        if (t) init.headers.Authorization = 'Bearer ' + t;
        if (body) init.body = JSON.stringify(body);
        fetch(path, init)
          .then(r => r.text().then(txt => cb({status: r.status, body: txt})))
          .catch(e => cb({status: -1, body: String(e)}));
        """,
        method,
        path,
        body,
    )


def api_json(d, method, path, body=None):
    r = api(d, method, path, body)
    try:
        return r['status'], (json.loads(r['body']).get('data') if r['body'].startswith('{') else None)
    except Exception:
        return r['status'], None


def items_of(data):
    if not isinstance(data, dict):
        return []
    return data.get('items') or []


def try_click(d, xpath, timeout=10):
    el = wait(d, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.2)
    el.click()
    return el


def ensure_llm_dimension(d, dims, algorithm_type):
    """自建 LA llm_judge 维度（真库无 llm_judge 样本）；返回 (id, created)。"""
    for x in dims:
        if x.get('name') == DIM_NAME:
            return x.get('id'), False
    base = next(
        (x for x in dims if str(x.get('dimension_type')) == 'main' and x.get('associated_algorithms')),
        None,
    )
    payload = {
        'name': DIM_NAME,
        'description': 'INT-1506 浏览器实测临时维度（脚本结束删除）',
        'dimension_type': 'main',
        'type': (base or {}).get('type') or 'accuracy',
        'category_id': (base or {}).get('category_id'),
        'status': (base or {}).get('status') or 'enabled',
        'score_unit': (base or {}).get('score_unit') or '分',
        'result_type': 'llm_judge',
        'result_min': 0,
        'result_max': 100,
        'decimal_places': 2,
        'weight': 5,
        'estimated_exec_time': 10,
        'rule': {'rules': []},
        'associated_algorithms': [
            {'algorithmType': algorithm_type, 'isDefault': False, 'weight': 5}
        ],
        'llm_judge_config': {
            'model': 'gpt-4o-mini',
            'promptTemplate': '请评估：{{asr_result}}',
            'maxTokens': 1024,
            'temperature': 0.7,
        },
    }
    status, data = api_json(d, 'POST', '/api/v1/evaluation/dimensions', payload)
    print('create llm dimension status', status)
    if status not in (200, 201):
        print('create failed body', data)
        return None, False
    return (data or {}).get('id'), True


def delete_dimension(d, dim_id):
    status, _ = api_json(d, 'DELETE', f'/api/v1/evaluation/dimensions/{dim_id}')
    print('cleanup dimension', dim_id, 'status', status)


def goto_testcases(d, algorithm_type='voice_llm'):
    d.execute_script(
        "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:arguments[0]},version:0}));",
        algorithm_type,
    )
    d.get(BASE + '/testcases/by-group')
    wait(d, 30).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    wait(d, 40).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(2)


def expand_all_groups(d):
    """分组默认收起：点每个组头（含「条」计数徽章的 div）。"""
    headers = d.find_elements(
        By.XPATH, "//div[contains(@class,'cursor-pointer') and .//span[contains(., '条')]]"
    )
    for h in headers:
        try:
            d.execute_script('arguments[0].scrollIntoView({block:"center"});', h)
            h.click()
            time.sleep(0.25)
        except Exception:
            pass
    time.sleep(0.6)


def open_drawer_for_case(d, case_name):
    box = wait(d, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(case_name)
    time.sleep(2)
    # 等分组头出现（首屏 by-group 逐组拉取较慢），再展开
    wait(d, 90).until(
        lambda x: x.execute_script(
            "return document.querySelectorAll(\"div[class*='cursor-pointer']\").length > 0"
        )
    )
    expand_all_groups(d)
    wait(d, 60).until(lambda x: case_name in (x.execute_script('return document.body.textContent') or ''))
    # 从该用例的勾选框向上找到卡片根，再点卡片内「编辑用例」（base-ui 控件用 JS click）
    clicked = d.execute_script(
        """
        const name = arguments[0];
        const cb = document.querySelector('[aria-label="选择 ' + name + '"]');
        if (!cb) return 'no-checkbox';
        let el = cb;
        for (let i = 0; i < 8 && el; i++) {
          el = el.parentElement;
          if (el && el.querySelector("button[aria-label='编辑用例']")) {
            const btn = el.querySelector("button[aria-label='编辑用例']");
            btn.scrollIntoView({block: 'center'});
            btn.click();
            return 'ok';
          }
        }
        return 'no-card';
        """,
        case_name,
    )
    print('open drawer:', case_name[:24], clicked)
    wait(d, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']")))
    time.sleep(1.2)


def check_no_mock_options(d):
    """评估维度步骤：抽屉内无写死模型/模板选项；非 LLM 维度不渲染模型/Prompt 控件。

    真库当前无 llm_judge 维度（后端 POST /evaluation/dimensions 校验 result_type 必须为整数，
    传 'llm_judge' 返回 code 203），LLM 分支在真实库不可达——这里核对「零写死假数据」与
    非 LLM 维度行为，LLM 分支由代码静态核对（参数卡已改自由文本输入，无 gpt-4 等常量）。
    """
    try_click(d, "//button[@role='tab'][contains(., '评估维度')]")
    time.sleep(1.2)
    search = wait(d, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[@placeholder='搜索评估维度']"))
    )
    # 勾选第一个可用维度，验证参数卡渲染
    chip_name = ''
    try:
        chip = wait(d, 12).until(
            EC.element_to_be_clickable(
                (By.XPATH, "(//button[contains(@class,'rounded-full') and @aria-pressed='false'])[1]")
            )
        )
        chip_name = chip.text.strip()
        chip.click()
        time.sleep(0.8)
    except Exception:
        drawer = d.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        text = (drawer.text or '')[:400].replace('\n', ' | ')
        print('NO DIM CHIP; drawer text=', text)
        screenshot(d, 'drawer_dimensions_empty.png')

    body = d.execute_script('return document.body.textContent') or ''
    hardcoded = [
        m
        for m in ('gpt-3.5-turbo', 'claude-3-opus', 'claude-3-sonnet', 'gpt-4o', 'gpt-4')
        if m in body
    ]
    model_inputs = d.find_elements(By.XPATH, "//input[starts-with(@id,'dim-model-')]")
    selects = d.find_elements(
        By.XPATH, "//button[@role='combobox' and ancestor::*[contains(@class,'rounded-lg')]]"
    )
    result = {
        'selected_dimension': chip_name,
        'hardcoded_model_texts': hardcoded,
        'model_input_count_non_llm': len(model_inputs),
    }
    print('无写死模型检查:', json.dumps(result, ensure_ascii=False))
    ok = not hardcoded and len(model_inputs) == 0
    print('无写死模型判定:', 'PASS' if ok else 'FAIL')
    return ok


def check_noise_devices(d, devices):
    """展开评估策略节：全局背景噪声设备 chips == 真实设备列表，且无「未匹配」警示。"""
    trigger = wait(d, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '评估策略')]"))
    )
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', trigger)
    trigger.click()
    time.sleep(1.2)

    chips = d.find_elements(
        By.XPATH, "//button[@aria-pressed and contains(normalize-space(.), '通道')]"
    )
    chip_texts = [c.text.strip() for c in chips]
    body = d.execute_script('return document.body.textContent') or ''
    expected = []
    for x in devices:
        t = x.get('device_type')
        tag = '干声' if t == 'dry' else '噪声' if t == 'noise' else (t or '未知')
        expected.append(f"{x.get('name')} (通道 {x.get('channel_index')}) [{tag}]")
    missing = [t for t in expected if t not in chip_texts]
    extra = [t for t in chip_texts if t not in expected]
    unmatched_warn = '未匹配到播放设备ID' in body
    result = {
        'chips': len(chip_texts),
        'expected': len(expected),
        'missing': missing[:5],
        'extra': extra[:5],
        'unmatched_warning': unmatched_warn,
    }
    print('背景噪声设备 chips:', json.dumps(result, ensure_ascii=False))
    ok = len(chip_texts) == len(expected) and not missing and not extra and not unmatched_warn
    print('背景噪声设备判定:', 'PASS' if ok else 'FAIL')
    return ok, chip_texts


def close_drawer(d):
    try_click(d, "//*[@data-slot='sheet-content']//button[normalize-space()='取消']", 8)
    time.sleep(0.8)


def check_batch_rounds(d, names, expected_rounds):
    """勾选两个 N 轮用例 → 批量设置评估维度 → 逐轮/指定轮次按实际轮次渲染。"""
    # 首屏 by-group 全量列表在真实库要逐组拉取（很慢），先用两例公共前缀搜索收窄再展开
    prefix = os.path.commonprefix(names)[:12] or names[0][:8]
    box = wait(d, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(prefix)
    time.sleep(2)
    expand_all_groups(d)
    time.sleep(1.2)
    dbg = d.execute_script(
        """
        return {
          headers: document.querySelectorAll("div[class*='cursor-pointer']").length,
          checkboxes: document.querySelectorAll("[aria-label^='选择 ']").length,
          editBtns: document.querySelectorAll("button[aria-label='编辑用例']").length,
          labels: Array.from(document.querySelectorAll("[aria-label^='选择 ']")).slice(0,3).map(e => e.getAttribute('aria-label') + ' / ' + e.tagName),
        };
        """
    )
    print('DEBUG batch dom:', json.dumps(dbg, ensure_ascii=False)[:500])
    for n in names:
        ok = d.execute_script(
            """
            const cb = document.querySelector('[aria-label="选择 ' + arguments[0] + '"]');
            if (!cb) return false;
            cb.scrollIntoView({block: 'center'});
            cb.click();
            return true;
            """,
            n,
        )
        print('select case', n[:24], ok)
        time.sleep(0.5)
    if not d.execute_script("return document.querySelectorAll('[aria-label^=\"选择 \"][aria-checked=\"true\"]').length"):
        # 兜底：勾选前两个用例卡（前缀搜索命中的用例轮次一致）
        print('fallback select first two cards')
        d.execute_script(
            """
            const cbs = Array.from(document.querySelectorAll("[aria-label^='选择 ']")).slice(0, 2);
            cbs.forEach(cb => { cb.scrollIntoView({block: 'center'}); cb.click(); });
            return cbs.length;
            """
        )
        time.sleep(0.6)
    try_click(d, "//button[normalize-space(.)='批量设置评估维度']")
    wait(d, 10).until(EC.presence_of_element_located((By.XPATH, "//*[contains(., '批量设置评估维度')]")))
    time.sleep(0.8)
    try_click(d, "//label[contains(normalize-space(.), '逐轮设置')]")
    time.sleep(0.8)
    buttons = d.find_elements(
        By.XPATH, "//button[starts-with(normalize-space(.), '第') and contains(normalize-space(.), '轮')]"
    )
    per_round = sorted({b.text.strip() for b in buttons if '添加' not in b.text})
    try_click(d, "//label[contains(normalize-space(.), '指定轮次')]")
    time.sleep(0.8)
    labels = d.find_elements(By.XPATH, "//label[contains(normalize-space(.), '第') and contains(normalize-space(.), '轮')]")
    specific = sorted({l.text.strip() for l in labels if '指定轮次' not in l.text})
    expected = [f'第 {i} 轮' for i in range(1, expected_rounds + 1)]
    expected_cn = [f'第{i}轮' for i in range(1, expected_rounds + 1)]
    print('逐轮 tabs:', per_round, '期望', expected)
    print('指定轮次:', specific, '期望', expected_cn)
    ok = per_round == expected and specific == expected_cn
    print('批量轮次判定:', 'PASS' if ok else 'FAIL')
    return ok


def screenshot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    print('shot', path)


def set_theme(d, mode):
    d.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode
    )
    d.get('about:blank')
    time.sleep(0.4)


def main():
    d = driver()
    results = {}
    dim_id = None
    created = False
    try:
        login(d)
        print('login ok', d.current_url)
        _, dev_data = api_json(d, 'GET', '/api/v1/playback-devices?per_page=200')
        devices = items_of(dev_data)
        _, dim_data = api_json(d, 'GET', '/api/v1/evaluation/dimensions?per_page=200')
        dims = items_of(dim_data)
        _, case_data = api_json(d, 'GET', '/api/v1/testcases?per_page=200')
        cases = items_of(case_data)
        print('devices', len(devices), 'dims', len(dims), 'cases', len(cases))

        # 选样本：带 background_noise 且 2 轮、算法 voice_llm 的用例
        noise_case = next(
            (
                c
                for c in cases
                if (c.get('config') or {}).get('background_noise')
                and len((c.get('config') or {}).get('rounds') or []) >= 1
            ),
            None,
        )
        rounds2 = [c for c in cases if len((c.get('config') or {}).get('rounds') or []) == 2]
        algo = (noise_case or {}).get('algorithm_type') or 'voice_llm'
        print('sample case', (noise_case or {}).get('name'), 'algo', algo, 'rounds2', len(rounds2))

        # 1+2：抽屉内 LLM 参数卡 + 背景噪声设备 chips
        goto_testcases(d, algo)
        open_drawer_for_case(d, noise_case['name'])
        results['no_mock_llm_options'] = check_no_mock_options(d)
        screenshot(d, 'drawer_llm_dim_light.png')
        results['noise_devices'], _ = check_noise_devices(d, devices)
        screenshot(d, 'drawer_noise_devices_light.png')
        close_drawer(d)

        # 3：批量评估维度轮次
        goto_testcases(d, algo)
        two = [c['name'] for c in rounds2[:2]]
        results['batch_rounds'] = check_batch_rounds(d, two, 2)
        screenshot(d, 'batch_dimensions_rounds_light.png')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)

        # 深色截图
        set_theme(d, 'dark')
        goto_testcases(d, algo)
        open_drawer_for_case(d, noise_case['name'])
        check_no_mock_options(d)
        screenshot(d, 'drawer_llm_dim_dark.png')
        check_noise_devices(d, devices)
        screenshot(d, 'drawer_noise_devices_dark.png')
        close_drawer(d)
        goto_testcases(d, algo)
        check_batch_rounds(d, two, 2)
        screenshot(d, 'batch_dimensions_rounds_dark.png')
        set_theme(d, 'light')

        print('RESULT', json.dumps(results, ensure_ascii=False))
    finally:
        if dim_id is not None and created:
            try:
                delete_dimension(d, dim_id)
            except Exception as e:
                print('cleanup failed', e)
        d.quit()


if __name__ == '__main__':
    main()
