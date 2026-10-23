# -*- coding: utf-8 -*-
"""INT-1540 验收：算法配置·参数范围约束 min>max 字段级红字 + aria-invalid。

真实库栈：前端 dev http://localhost:5340（本 worktree 代码，/api 代理 127.0.0.1:15000），
后端 docker 网关 http://localhost:15000（库 intelligent_audio_test）。

验收点：
1. 合法范围 → 发布可用、无红字
2. 最小 10 / 最大 5 → 字段级红字「最小值不能大于最大值」+ min/max aria-invalid=true + 发布禁用
3. 修回 0~10 → 红字消失、aria-invalid=false、发布恢复可用
4. 浅色 + 深色截图；Network 证据（definitions/groups 200；禁用态点击不产生 POST）
只读真实数据：本脚本不提交发布，不写库。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5340')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1540')

RESULT = {}
JS_ERRORS = []
FORM = "//*[@id='algorithm-mutate-form']"
ERR_TEXT = '最小值不能大于最大值'
PUBLISH = "//button[@form='algorithm-mutate-form']"
MIN_INPUT = FORM + "//input[@aria-label='最小值']"
MAX_INPUT = FORM + "//input[@aria-label='最大值']"


def setup_driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    try:
        drv.execute_cdp_cmd('Network.enable', {})
    except Exception:
        pass
    return drv


def body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def drain_console(drv):
    try:
        for entry in drv.get_log('browser'):
            msg = entry.get('message', '')
            if 'Failed to load resource' in msg and 'Uncaught' not in msg:
                continue
            if entry.get('level') == 'SEVERE':
                JS_ERRORS.append(msg)
    except Exception:
        pass


def goto(drv, path, wait=2.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)
    drain_console(drv)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    dialogs = drv.find_elements(By.XPATH, "//*[@role='alertdialog']")
    if dialogs:
        raise AssertionError(f'截图前存在 alertdialog 遮罩: {[d.text[:60] for d in dialogs]}')
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p)


def js_click(drv, xpath, wait=0.6):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


def set_value(drv, xpath, value):
    """像真实用户一样输入：聚焦 → Ctrl+A → Delete → 逐字输入（React onChange 必然触发）。"""
    from selenium.webdriver.common.keys import Keys
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();", el)
    time.sleep(0.2)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    time.sleep(0.15)
    if value:
        el.send_keys(value)
    time.sleep(0.6)


def net(drv, url_sub):
    out = []
    try:
        for entry in drv.get_log('performance'):
            try:
                data = json.loads(entry.get('message', ''))
            except Exception:
                continue
            inner = data.get('message', data)
            if not isinstance(inner, dict):
                continue
            m = inner.get('method', '')
            params = inner.get('params', {}) or {}
            url, method, status = '', '', None
            if m == 'Network.requestWillBeSent':
                rq = params.get('request', {}) or {}
                url, method = rq.get('url', ''), rq.get('method', '')
            elif m == 'Network.responseReceived':
                rs = params.get('response', {}) or {}
                url, status = rs.get('url', ''), rs.get('status')
                method = (rs.get('requestHeaders', {}) or {}).get(':method', '')
            if url_sub in url:
                out.append((method or '?', url, status))
    except Exception:
        pass
    seen, dedup = set(), []
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        dedup.append(item)
    return dedup


def publish_disabled(drv):
    return drv.find_element(By.XPATH, PUBLISH).get_attribute('disabled') is not None


def wait_publish_enabled(drv, timeout=15):
    """等发布按钮可用（草稿自动保存进行中也会禁用发布，需等其结束）。"""
    end = time.time() + timeout
    while time.time() < end:
        if not publish_disabled(drv):
            return True
        time.sleep(0.5)
    return not publish_disabled(drv)


def range_state(drv):
    min_el = drv.find_element(By.XPATH, MIN_INPUT)
    max_el = drv.find_element(By.XPATH, MAX_INPUT)
    cell_text = drv.execute_script(
        "return arguments[0].closest('td').textContent || ''", min_el)
    red = drv.execute_script(
        "const p = Array.from(arguments[0].closest('td').querySelectorAll('p'));"
        "return p.map(e => e.textContent.trim()).filter(Boolean);", min_el)
    return {
        'min_aria_invalid': min_el.get_attribute('aria-invalid'),
        'max_aria_invalid': max_el.get_attribute('aria-invalid'),
        'cell_text': cell_text,
        'red_messages': red,
        'error_text_present': ERR_TEXT in (cell_text or ''),
        'publish_disabled': publish_disabled(drv),
    }


def set_theme(drv, mode):
    """主题持久化 key iatp:theme:v1:mode（INT-1246 实测）；换主题后整页重载重新进流程。"""
    goto(drv, '/AlgorithmConfig', 1.0)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.get('about:blank')
    time.sleep(0.5)
    goto(drv, '/AlgorithmConfig', 2.5)


def open_create_sheet(drv):
    try:
        WebDriverWait(drv, 30).until(
            lambda d: [b for b in d.find_elements(By.XPATH, "//button") if '新建算法' in (b.text or '')])
    except Exception:
        # 冷启动/路由懒加载兜底：再进一次页面
        goto(drv, '/AlgorithmConfig', 3.0)
        WebDriverWait(drv, 30).until(
            lambda d: [b for b in d.find_elements(By.XPATH, "//button") if '新建算法' in (b.text or '')])
    btn = [b for b in drv.find_elements(By.XPATH, "//button") if '新建算法' in (b.text or '')]
    assert btn, f'未找到「新建算法」按钮；body={body(drv)[:300]}'
    btn[0].click()
    WebDriverWait(drv, 20).until(lambda d: '新建算法' in body(d) and '算法代码' in body(d))
    time.sleep(1.2)


def backend_groups():
    for _ in range(5):
        try:
            with urllib.request.urlopen(API + '/api/v1/algorithm/groups', timeout=8) as r:
                return json.loads(r.read().decode()).get('data', {}).get('items', [])
        except Exception:
            time.sleep(1.5)
    return []


def fill_basic(drv):
    set_value(drv, "//input[@id='algo-type']", 'int1540_probe')
    set_value(drv, "//input[@id='algo-name']", '接线测试_范围校验')
    if not backend_groups():
        # 真实库 docker 栈算法分组为空（GET /algorithm/groups → items: []）；groupId 后端可空
        # （§17 schema），与范围约束校验无关，直接跳过所属分组，避免打开空下拉。
        print('WARN: 后端无算法分组，跳过所属分组')
        return '(无分组)'
    # 所属分组：选第一个真实分组（跳过「＋ 新建分组」）
    opts = []
    for attempt in range(3):
        trigger = drv.find_element(By.XPATH, FORM + "//button[@role='combobox'][contains(., '请选择分组')]")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", trigger)
        try:
            WebDriverWait(drv, 5).until(
                lambda d: [o for o in d.find_elements(By.XPATH, "//*[@role='option']")
                           if '新建分组' not in (o.text or '')])
        except Exception:
            pass
        opts = [o for o in drv.find_elements(By.XPATH, "//*[@role='option']") if '新建分组' not in (o.text or '')]
        if opts:
            break
        print(f'group options empty (attempt {attempt + 1}), retry')
        time.sleep(1.5)
    if not opts:
        # 真实库 docker 栈算法分组为空（GET /algorithm/groups → items: []），group_id 后端可空（§17 schema），
        # 分组非本卡范围约束校验相关，缺失不阻断。Esc 关弹层会触发脏态守卫，需点「留在当前页」留在 Sheet。
        ActionChains(drv).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.6)
        if drv.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '未保存的更改')]"):
            js_click(drv, "//*[@role='alertdialog']//button[normalize-space()='留在当前页']", 0.8)
        print('WARN: 分组下拉无真实选项（GET /algorithm/groups 为空），跳过所属分组')
        return '(无分组)'
    group_label = (opts[0].text or '').strip()
    drv.execute_script("arguments[0].click();", opts[0])
    time.sleep(0.8)
    return group_label


def add_noise_param_as_number(drv):
    js_click(drv, "//*[@aria-label='功能特性 噪声']", 1.2)
    try:
        WebDriverWait(drv, 10).until(
            lambda d: len(d.find_elements(By.XPATH, FORM + "//input[@aria-label='参数代码']")) == 1)
    except Exception:
        print('DEBUG body:', body(drv)[:600])
        print('DEBUG checkboxes:', [e.get_attribute('aria-label') for e in drv.find_elements(By.XPATH, "//*[@role='checkbox']")])
        raise
    # 参数类型下拉（行内第一个 combobox）→ 数字（base-ui 弹层动画，允许重试）
    for attempt in range(3):
        combo = drv.find_element(By.XPATH, FORM + "//tbody//button[@role='combobox']")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", combo)
        try:
            WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='option']"))
        except Exception:
            pass
        clicked = False
        for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
            if (o.text or '').strip() == '数字':
                drv.execute_script("arguments[0].click();", o)
                clicked = True
                break
        if not clicked:
            raise AssertionError('参数类型下拉无「数字」选项')
        time.sleep(1.0)
        if drv.find_elements(By.XPATH, MIN_INPUT):
            return
        print(f'range cell missing (attempt {attempt + 1}), retry type select')
    raise AssertionError('选择「数字」后未出现范围约束单元格')


def backend_snapshot():
    last = None
    for _ in range(5):
        try:
            with urllib.request.urlopen(API + '/health', timeout=8) as r:
                return json.loads(r.read().decode())
        except Exception as exc:  # docker 网关偶发连接挂起，重试
            last = exc
            time.sleep(2)
    raise AssertionError(f'后端 /health 不可达: {last}')


def wait_app_ready(drv, timeout=40):
    """SPA 冷启动 / HMR 重建期间可能白屏，重载等待页面骨架渲染。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if '算法配置' in body(drv) and '新建算法' in body(drv):
            return
        time.sleep(2.0)
        try:
            goto(drv, '/AlgorithmConfig', 2.0)
        except Exception:
            pass
    root_len = drv.execute_script("const r=document.getElementById('root'); return r?r.innerHTML.length:-1")
    errs = [e.get('message', '')[:200] for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    os.makedirs(ART, exist_ok=True)
    drv.save_screenshot(os.path.join(ART, 'blank_debug.png'))
    with open(os.path.join(ART, 'blank_debug.html'), 'w', encoding='utf-8') as f:
        f.write(drv.page_source)
    raise AssertionError(
        f'算法配置页未渲染；root_len={root_len}；body={body(drv)[:200]}；severe={errs[:5]}')


def main():
    os.makedirs(ART, exist_ok=True)
    RESULT['backend_health'] = backend_snapshot()
    print('backend:', RESULT['backend_health'])

    drv = setup_driver()
    try:
        # ── 浅色：复现 min>max ──
        goto(drv, '/login', 1.5)
        set_theme(drv, 'light')
        wait_app_ready(drv)
        txt = body(drv)
        assert '算法配置' in txt, f'页面未渲染: {txt[:200]}'
        open_create_sheet(drv)
        group = fill_basic(drv)
        add_noise_param_as_number(drv)

        # Network 证据：页面加载期真实请求（get_log('performance') 会消费缓冲，先取一次）
        RESULT['net_initial'] = net(drv, '/api/v1/algorithm')

        # 合法范围先行（0~10）：发布应可用、无红字
        set_value(drv, MIN_INPUT, '0')
        set_value(drv, MAX_INPUT, '10')
        RESULT['valid_publish_enabled'] = wait_publish_enabled(drv)
        RESULT['valid_light'] = range_state(drv)

        # 非法范围：min 10 > max 5
        set_value(drv, MIN_INPUT, '10')
        set_value(drv, MAX_INPUT, '5')
        WebDriverWait(drv, 10).until(lambda d: ERR_TEXT in body(d))
        time.sleep(0.6)
        RESULT['invalid_light'] = range_state(drv)
        shot(drv, '01_invalid_light')

        # 禁用态点击无请求（先排空 performance 缓冲，点击后新出现的条目即点击触发的请求）
        net(drv, '/api/')
        js_click(drv, PUBLISH, 1.5)
        nets_after = net(drv, '/api/')
        RESULT['requests_after_disabled_click'] = nets_after
        RESULT['post_requests_while_disabled'] = [
            n for n in nets_after if n[0] == 'POST' and '/algorithm' in n[1]]

        # 修回合法范围：红字消失、发布恢复
        set_value(drv, MIN_INPUT, '0')
        set_value(drv, MAX_INPUT, '10')
        RESULT['fixed_publish_enabled'] = wait_publish_enabled(drv)
        RESULT['fixed_light'] = range_state(drv)
        shot(drv, '02_valid_light')

        RESULT['groups_used'] = group
        drain_console(drv)

        # ── 深色：重新复现 ──
        set_theme(drv, 'dark')
        wait_app_ready(drv)
        open_create_sheet(drv)
        fill_basic(drv)
        add_noise_param_as_number(drv)
        set_value(drv, MIN_INPUT, '10')
        set_value(drv, MAX_INPUT, '5')
        WebDriverWait(drv, 10).until(lambda d: ERR_TEXT in body(d))
        time.sleep(0.6)
        RESULT['invalid_dark'] = range_state(drv)
        shot(drv, '03_invalid_dark')
        set_value(drv, MIN_INPUT, '0')
        set_value(drv, MAX_INPUT, '10')
        RESULT['fixed_dark_publish_enabled'] = wait_publish_enabled(drv)
        RESULT['fixed_dark'] = range_state(drv)
        shot(drv, '04_valid_dark')
        drain_console(drv)

        RESULT['js_errors'] = JS_ERRORS
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULT, f, ensure_ascii=False, indent=2)
        print(json.dumps(RESULT, ensure_ascii=False, indent=2))

        # ── 断言 ──
        inv, vd, fx, fxd = (RESULT['invalid_light'], RESULT['valid_light'],
                            RESULT['fixed_light'], RESULT['fixed_dark'])
        assert inv['error_text_present'], '非法范围：单元格无「最小值不能大于最大值」红字'
        assert inv['min_aria_invalid'] == 'true', f"min aria-invalid={inv['min_aria_invalid']}"
        assert inv['max_aria_invalid'] == 'true', f"max aria-invalid={inv['max_aria_invalid']}"
        assert inv['publish_disabled'] is True, '非法范围：发布按钮未禁用'
        assert vd['error_text_present'] is False, '合法范围：不应出现红字'
        assert RESULT['valid_publish_enabled'] is True, '合法范围：发布按钮应可用'
        assert fx['error_text_present'] is False and RESULT['fixed_publish_enabled'] is True, \
            '修回合法后未恢复（红字应消失、发布应可用）'
        assert not RESULT['post_requests_while_disabled'], '禁用态点击仍发出了 POST'
        assert RESULT['invalid_dark']['error_text_present'], '深色：无红字'
        assert fxd['error_text_present'] is False, '深色：修回后红字未消失'
        assert RESULT['fixed_dark_publish_enabled'] is True, '深色：修回后发布未恢复'
        assert any(n[2] == 200 for n in RESULT['net_initial']), 'Network：未见算法接口 200 请求'
        print('ALL CHECKS PASSED')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
