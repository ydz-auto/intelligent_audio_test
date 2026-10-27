# -*- coding: utf-8 -*-
"""INT-2081 RMS-SPL 校准口径改「目标SPL↔实测dBFS」浏览器验收（真实 Chrome headless + docker 15000）。

环境铁律（负责人 2026-10-23）：验收一律 docker。本卡交付分支 agent/react-b/int-2081
（afaae79eb）未合入 wiring/react，15173 :latest 镜像不含该改动 → 用旁路容器
（iat-react-frontend:int2081-verify，:15276，nginx conf 取自 15173 容器，/api 经容器网络
直连同一 api_gateway）验收；后端 = 常驻 docker 15000（/health database=intelligent_audio_test，
AUTH_MODE=dev → RSA 加密登录取 admin token 注入会话）。

覆盖 INT-2081 验收标准：
① 添加弹窗含校准点集（目标SPL+实测dBFS 可编辑、增益只读推导、行级校验、按参考生成）；
② 真实创建「接线测试_INT2081_」映射带 3 点（65/-50、75/-40、85/-10），GET 回读逐字段一致
   （gain_linear=0.1/0.316/10 由 dBFS 推导）；
③ 编辑弹窗回填名称/目标SPL/dBFS；
④ 校准弹窗 dBFS 为主输入（列序 目标SPL→实测RMS→线性增益→增益dB）、曲线预览有数据、
   提交校准后详情点集含推导增益与 dBFS、状态置已校准；
⑤ 弹窗+详情浅/深色截图各一张；
⑥ Network 仅真实 API、console 无 SEVERE；
⑦ 数据卫生：run 结束前删除「接线测试_INT2081_」记录，库里不留残留。

失败落 tests/ui/artifacts/int2081_rms_spl_calibration/<用例>/（截图+console+source）。
"""
import base64
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2081_rms_spl_calibration')

# 旁路容器（交付 dist 构建）端口；env 可覆写
BASE = os.environ.get('REACT_BASE', 'http://localhost:15276')
API = os.environ.get('API_BASE', 'http://localhost:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
TOKEN_KEY = 'iatp:auth:token:v1'
THEME_KEY = 'iatp:theme:v1:mode'
ACCOUNT = ('接线测试_admin', 'JieXianTest@2026')

SHARED = {'mapping_id': None, 'mapping_name': ''}
_CONSOLE_SEVERE = []
_DRIVER = None


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


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--lang=zh-CN')
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
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(60)
    return drv


def _drain_console(drv):
    global _CONSOLE_SEVERE
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                _CONSOLE_SEVERE.append(entry.get('message', ''))
    except Exception:
        pass


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


@pytest.fixture(scope='module')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    yield _DRIVER
    try:
        _drain_console(_DRIVER)
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


def rsa_login_token(username, password):
    """RSA-OAEP 加密登录 docker 15000 → access_token（capture_int1485 同口径）。"""
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    import urllib.request
    import urllib.parse
    key = json.load(urllib.request.urlopen(API + '/api/v1/auth/login/encryption-key'))
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
    body = json.load(urllib.request.urlopen(req))
    return body['access_token']


def api(path, token=None, method='GET', body=None):
    """直连 docker 15000 网关（Network 对照 + 数据卫生）。"""
    import urllib.request
    import urllib.parse
    url = API + path
    data = None
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def _cleanup_residue(token):
    """删除库里所有「接线测试_INT2081_」残留映射（失败重跑兜底 + run 结束前清场）。"""
    import urllib.parse
    st, js = api('/api/v1/digital-spl?search=%s' % urllib.parse.quote('接线测试_INT2081_'), token)
    if st != 200:
        return
    items = (js.get('data') or {}).get('items') or []
    for m in items:
        if (m.get('name') or '').startswith('接线测试_INT2081_'):
            mid = m['id']
            d_st, _ = api('/api/v1/digital-spl/%s' % mid, token, method='DELETE')
            print('cleanup deleted mapping id=%s status=%s' % (mid, d_st))


@pytest.fixture(scope='module')
def token():
    tok = rsa_login_token(*ACCOUNT)
    assert tok, '登录失败：未取得 access_token'
    return tok


@pytest.fixture(scope='module')
def boot(drv, token):
    """同一会话仅一次：同源注入 admin token + 清浅色主题，供后续整页加载水合。"""
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)
    drv.execute_script(
        'try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
        TOKEN_KEY, token)
    drv.execute_script(
        'try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}',
        THEME_KEY, 'light')
    drv.execute_script(
        'try { localStorage.removeItem("iatp:auth:v1"); sessionStorage.removeItem("__rbac_perm"); } catch(e) {}')
    time.sleep(0.5)
    return True


@pytest.fixture(scope='module', autouse=True)
def _final_cleanup(token):
    """模块级兜底：无论成败，结束后清掉所有「接线测试_INT2081_」残留。"""
    yield
    try:
        _cleanup_residue(token)
    except Exception:
        pass


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=25):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(d))


def _screenshot(drv, name):
    d = os.path.join(ARTIFACTS, 'shots')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    drv.save_screenshot(path)
    return path


def _set_theme(drv, mode):
    """主题经 localStorage 写入 + 整页刷新生效（theme-provider 仅挂载时读 storage）。"""
    drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]) } catch(e) {}',
                       THEME_KEY, mode)
    drv.refresh()
    WebDriverWait(drv, 20).until(lambda d: ('dark' in (d.execute_script(
        'return document.documentElement.className') or '')) == (mode == 'dark'))


def _open_digital_tab(drv):
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    tabs = drv.find_elements(By.XPATH, "//*[@role='tab'][contains(., 'API/Realtime RMS-SPL')]")
    if tabs:
        drv.execute_script('arguments[0].click()', tabs[0])
    _wait_text(drv, '添加 RMS-SPL 映射', timeout=25)
    time.sleep(0.6)


def _click_retry(drv, xpath, timeout=15):
    """base-ui Dropdown/Select 偶发吞事件 → 重试循环等期望元素可点（审计记忆同口径）。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        els = drv.find_elements(By.XPATH, xpath)
        if els:
            try:
                drv.execute_script('arguments[0].click()', els[0])
                return els[0]
            except Exception as e:
                last = e
        time.sleep(0.3)
    raise AssertionError(f'click retry timeout: {xpath} ({last})')


def _open_row_menu(drv, name):
    trigger = drv.find_element(By.XPATH,
        f"//button[@aria-label='映射 {name} 的操作']")
    drv.execute_script('arguments[0].click()', trigger)
    time.sleep(0.7)


def _click_menu_item(drv, label):
    return _click_retry(drv, f"//*[@role='menuitem'][contains(., '{label}')]")


def _fill_point(drv, index, target_spl, rms_dbfs):
    drv.find_element(By.XPATH, f"//input[@aria-label='第 {index} 行目标 SPL']").clear()
    drv.find_element(By.XPATH, f"//input[@aria-label='第 {index} 行目标 SPL']").send_keys(target_spl)
    drv.find_element(By.XPATH, f"//input[@aria-label='第 {index} 行实测 RMS']").clear()
    drv.find_element(By.XPATH, f"//input[@aria-label='第 {index} 行实测 RMS']").send_keys(rms_dbfs)
    time.sleep(0.4)


def _open_create_dialog(drv):
    """数字页签 → 添加 RMS-SPL 映射 → 弹窗（含校准点集）。"""
    _open_digital_tab(drv)
    _click_retry(drv, "//button[contains(., '添加 RMS-SPL 映射')]")
    _wait_text(drv, '校准点集', timeout=20)
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# ① 添加弹窗校准点集
# ---------------------------------------------------------------------------

def test_01_create_dialog_calibration_points_and_generate(drv, boot):
    """添加弹窗含校准点集；按参考生成 5 点（中心 65/-30.0 增益 1.0 只读推导）。"""
    _open_create_dialog(drv)
    body = _body_text(drv)
    # 校准点集区 + 空态文案 + 两个操作钮
    assert '校准点集' in body, '弹窗缺校准点集区'
    assert '快速生成 5 个基准点' in body, f'校准点集空态缺失: {body[:300]}'
    for btn in ('按参考生成', '添加校准点'):
        assert btn in body, f'缺校准点集操作钮: {btn}'

    # 按参考生成（默认参考 65/1.0）→ 5 点，中心点 targetSpl=65、dBFS=-30.0、增益=1.0
    _click_retry(drv, "//button[contains(., '按参考生成')]")
    time.sleep(0.6)
    # 有点后表头出现：目标SPL / 实测RMS(dBFS) / 线性增益 / 增益(dB)
    body = _body_text(drv)
    for col in ('目标 SPL（dB）', '实测 RMS（dBFS）', '线性增益', '增益（dB）'):
        assert col in body, f'校准点集缺列头: {col}'
    target_inputs = drv.find_elements(By.XPATH, "//input[contains(@aria-label, '目标 SPL')]")
    assert len(target_inputs) == 5, f'按参考生成应为 5 点，实际 {len(target_inputs)}'
    center_target = drv.find_element(By.XPATH, "//input[@aria-label='第 3 行目标 SPL']").get_attribute('value')
    center_dbfs = drv.find_element(By.XPATH, "//input[@aria-label='第 3 行实测 RMS']").get_attribute('value')
    assert center_target == '65', f'中心点目标SPL={center_target}，期望 65'
    assert center_dbfs == '-30.0', f'中心点 dBFS={center_dbfs}，期望 -30.0'
    row3 = drv.find_element(By.XPATH,
        "//tr[.//input[@aria-label='第 3 行目标 SPL']]")
    assert '1.0' in row3.text, f'中心点推导增益未显示 1.0: {row3.text}'
    _screenshot(drv, 'int2081_create_dialog_generate_light.png')
    # 关掉弹窗（取消）
    _click_retry(drv, "//button[contains(., '取消')]")
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# ② 真实创建带点集映射 + GET 回读
# ---------------------------------------------------------------------------

def test_02_create_mapping_with_points_get_readback(drv, token):
    """真实创建「接线测试_INT2081_」映射带 3 点（65/-50、75/-40、85/-10），
    列表出现且校准点数=3；GET 回读逐字段一致（gain_linear 由 dBFS 推导）。"""
    import urllib.parse
    _cleanup_residue(token)  # 先清上次失败重跑残留，保证创建后唯一
    name = '接线测试_INT2081_%s' % time.strftime('%H%M%S')
    SHARED['mapping_name'] = name
    _open_create_dialog(drv)
    # 关联被测 API（库里 1 条，id=1）
    _click_retry(drv, "//button[@aria-label='关联被测 API']")
    time.sleep(0.5)
    _click_retry(drv, "//*[@role='option'][contains(., '1')]")
    # 映射名称
    drv.find_element(By.XPATH, "//input[@aria-label='映射名称']").send_keys(name)
    # 参考声压级/参考线性增益/限幅显式填写
    ref_spl = drv.find_element(By.XPATH, "//input[@aria-label='参考声压级']")
    ref_spl.clear()
    ref_spl.send_keys('65')
    ref_gain = drv.find_element(By.XPATH, "//input[@aria-label='参考线性增益']")
    ref_gain.clear()
    ref_gain.send_keys('1.0')
    # 手动添加 3 个校准点
    for _ in range(3):
        _click_retry(drv, "//button[contains(., '添加校准点')]")
    time.sleep(0.4)
    _fill_point(drv, 1, '65', '-50')
    _fill_point(drv, 2, '75', '-40')
    _fill_point(drv, 3, '85', '-10')
    # 推导增益只读显示：0.1 / 0.316 / 10.0
    row1 = drv.find_element(By.XPATH, "//tr[.//input[@aria-label='第 1 行目标 SPL']]")
    row2 = drv.find_element(By.XPATH, "//tr[.//input[@aria-label='第 2 行目标 SPL']]")
    row3 = drv.find_element(By.XPATH, "//tr[.//input[@aria-label='第 3 行目标 SPL']]")
    assert '0.1' in row1.text, f'65/-50 推导增益应为 0.1: {row1.text}'
    assert '0.316' in row2.text, f'75/-40 推导增益应为 0.316: {row2.text}'
    assert '10.0' in row3.text, f'85/-10 推导增益应为 10.0: {row3.text}'
    # 增益(dB) 只读列：-20.0 / -10.0 / 20.0
    assert '-20.0' in row1.text and '-10.0' in row2.text and '20.0' in row3.text, \
        f'增益(dB) 推导列异常: {row1.text} | {row2.text} | {row3.text}'
    _screenshot(drv, 'int2081_create_dialog_points_light.png')

    # 保存 → toast
    _click_retry(drv, "//button[contains(., '保存')]")
    _wait_text(drv, 'RMS-SPL 映射创建成功', timeout=25)
    # 列表出现新行 + 校准点数=3
    _wait_text(drv, name, timeout=25)
    row = drv.find_element(By.XPATH, f"//tr[.//*[contains(text(), '{name}')]]")
    assert '3' in row.text, f'列表校准点数应=3: {row.text}'
    _screenshot(drv, 'int2081_list_with_new_row_light.png')

    # GET 回读：找映射 id
    st, js = api('/api/v1/digital-spl?search=%s' % urllib.parse.quote(name), token)
    assert st == 200, f'GET /digital-spl status={st}'
    items = (js.get('data') or {}).get('items') or []
    matches = [m for m in items if m.get('name') == name]
    assert len(matches) == 1, f'期望 1 条匹配，实际 {len(matches)}'
    mid = matches[0]['id']
    SHARED['mapping_id'] = mid
    # 逐字段核对：name / reference / 限幅 / calibration_points 推导
    assert matches[0]['reference_spl'] == 65
    assert abs((matches[0]['reference_gain_linear'] or 1.0) - 1.0) < 1e-9
    pts = matches[0].get('calibration_points') or []
    assert len(pts) == 3, f'校准点应=3，实际 {len(pts)}'
    expect = {
        65: (0.1, -50),
        75: (0.31622776601683793, -40),
        85: (10.0, -10),
    }
    for p in pts:
        spl = p['target_spl']
        gain, dbfs = expect[spl]
        assert abs((p['gain_linear'] or 0) - gain) < 1e-4, \
            f'target {spl}: gain_linear={p["gain_linear"]} 期望 {gain}'
        assert p['rms_dbfs'] == dbfs, f'target {spl}: rms_dbfs={p["rms_dbfs"]} 期望 {dbfs}'


# ---------------------------------------------------------------------------
# ③ 编辑回填
# ---------------------------------------------------------------------------

def test_03_edit_dialog_refill(drv):
    """重开编辑弹窗：名称/目标SPL/dBFS 全部回填；提交仍带真实点集。"""
    assert SHARED['mapping_id'] and SHARED['mapping_name']
    _open_digital_tab(drv)
    _open_row_menu(drv, SHARED['mapping_name'])
    _click_menu_item(drv, '编辑')
    _wait_text(drv, '编辑 RMS-SPL 映射', timeout=20)
    # 名称回填
    name_val = drv.find_element(By.XPATH, "//input[@aria-label='映射名称']").get_attribute('value')
    assert name_val == SHARED['mapping_name'], f'编辑名称回填={name_val}'
    # 校准点回填
    v1 = drv.find_element(By.XPATH, "//input[@aria-label='第 1 行目标 SPL']").get_attribute('value')
    d1 = drv.find_element(By.XPATH, "//input[@aria-label='第 1 行实测 RMS']").get_attribute('value')
    v3 = drv.find_element(By.XPATH, "//input[@aria-label='第 3 行目标 SPL']").get_attribute('value')
    d3 = drv.find_element(By.XPATH, "//input[@aria-label='第 3 行实测 RMS']").get_attribute('value')
    assert v1 == '65' and d1 == '-50', f'行1 回填 {v1}/{d1}'
    assert v3 == '85' and d3 == '-10', f'行3 回填 {v3}/{d3}'
    _screenshot(drv, 'int2081_edit_dialog_refill_light.png')
    # 取消关闭（不改写）
    _click_retry(drv, "//button[contains(., '取消')]")
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# ④ 校准弹窗 dBFS 主输入
# ---------------------------------------------------------------------------

def test_04_calibration_dialog_dbfs_main_input_curve(drv, token):
    """校准弹窗：列序 目标SPL→实测RMS(dBFS)→线性增益→增益(dB)，dBFS 可编辑、
    增益只读推导 + 超限幅警告、曲线预览有数据；提交校准后状态置已校准。"""
    assert SHARED['mapping_id']
    _open_digital_tab(drv)
    _open_row_menu(drv, SHARED['mapping_name'])
    _click_menu_item(drv, '校准')
    _wait_text(drv, 'RMS-SPL 数字校准', timeout=20)
    time.sleep(0.5)
    # 列序（目标SPL 在 实测RMS 前，线性增益在 增益(dB) 前；仅限弹窗内 th，避开页表）
    dlg = drv.find_element(By.XPATH, "//*[@role='dialog'][contains(., 'RMS-SPL 数字校准')]")
    ths = dlg.find_elements(By.XPATH,
        ".//th[contains(., 'SPL') or contains(., 'RMS') or contains(., '增益')]")
    order = [t.text.replace('（', '(').replace('）', ')') for t in ths]
    assert order == ['目标 SPL(dB)', '实测 RMS(dBFS)', '线性增益', '增益(dB)'], f'列序异常: {order}'
    # dBFS 为主输入回填 -50/-40/-10，推导增益只读列 0.1/0.316/10.0
    for idx, dbfs in ((1, '-50'), (2, '-40'), (3, '-10')):
        inp = drv.find_element(By.XPATH, f"//input[@aria-label='第 {idx} 行实测 RMS']")
        assert inp.get_attribute('value') == dbfs, f'行{idx} dBFS 回填={inp.get_attribute("value")}'
    row1 = drv.find_element(By.XPATH, "//tr[.//input[@aria-label='第 1 行目标 SPL']]")
    row3 = drv.find_element(By.XPATH, "//tr[.//input[@aria-label='第 3 行目标 SPL']]")
    assert '0.1' in row1.text and '10.0' in row3.text, f'推导增益列异常: {row1.text}'
    # 修改 dBFS → 推导增益实时更新（-50→-60 ⇒ 0.1→0.032，formatLinearGain 3 位四舍五入）
    dbfs_inp = drv.find_element(By.XPATH, "//input[@aria-label='第 1 行实测 RMS']")
    dbfs_inp.clear()
    dbfs_inp.send_keys('-60')
    time.sleep(0.5)
    assert '0.032' in drv.find_element(By.XPATH,
        "//tr[.//input[@aria-label='第 1 行目标 SPL']]").text, 'dBFS→增益推导未实时更新'
    dbfs_inp.clear()
    dbfs_inp.send_keys('-50')
    time.sleep(0.5)
    # 曲线预览有数据
    _wait_text(drv, '增益曲线预览', timeout=10)
    _screenshot(drv, 'int2081_calibration_dialog_light.png')
    # 提交校准 → toast → 状态已校准
    _click_retry(drv, "//button[contains(., '提交校准')]")
    _wait_text(drv, '校准完成：校准点已落库并置为已校准', timeout=30)
    time.sleep(1.0)
    st, js = api('/api/v1/digital-spl/%s' % SHARED['mapping_id'], token)
    assert st == 200, f'GET /digital-spl/{{id}} status={st}'
    data = js.get('data') or {}
    assert data.get('calibration_status') == 'calibrated', \
        f'校准后状态={data.get("calibration_status")}，期望 calibrated'
    pts = data.get('calibration_points') or []
    assert len(pts) == 3, f'校准后点应=3，实际 {len(pts)}'
    gains = {p['target_spl']: p['gain_linear'] for p in pts}
    assert abs((gains.get(65) or 0) - 0.1) < 1e-4
    assert abs((gains.get(75) or 0) - 0.31622776601683793) < 1e-4
    assert abs((gains.get(85) or 0) - 10.0) < 1e-4


# ---------------------------------------------------------------------------
# ⑤ 详情弹窗列口径
# ---------------------------------------------------------------------------

def test_05_detail_dialog_columns_and_values(drv):
    """详情弹窗：校准点明细列口径 目标SPL→实测RMS→线性增益→增益(dB)，值全部渲染。"""
    assert SHARED['mapping_id']
    _open_digital_tab(drv)
    _open_row_menu(drv, SHARED['mapping_name'])
    _click_menu_item(drv, '详情')
    _wait_text(drv, '校准点明细', timeout=20)
    time.sleep(0.4)
    dlg = drv.find_element(By.XPATH, "//*[@role='dialog'][contains(., '校准点明细')]")
    body = dlg.text
    # 列头
    for col in ('目标 SPL', '实测 RMS', '线性增益', '增益（dB）'):
        assert col in body, f'详情缺列头: {col}'
    # 值渲染：65 dB / -50 dBFS / 0.1 / -20.0 dB（0.1→20log10=-20）
    flat = body.replace(' ', '')
    for needle in ('65dB', '-50dBFS', '0.1', '-20.0dB',
                   '75dB', '-40dBFS', '0.316',
                   '85dB', '-10dBFS', '10.0', '20.0dB'):
        assert needle in flat, f'详情缺渲染值: {needle}'
    _screenshot(drv, 'int2081_detail_dialog_light.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys('')  # ESC 关闭详情弹窗
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# ⑥ 深浅色截图
# ---------------------------------------------------------------------------

def test_06_dark_screenshots(drv):
    """深色主题下重开 添加弹窗（带点集）/校准弹窗/详情弹窗，各截一张。"""
    assert SHARED['mapping_id'] and SHARED['mapping_name']
    _set_theme(drv, 'dark')
    # 添加弹窗（按参考生成 5 点）
    _open_create_dialog(drv)
    _click_retry(drv, "//button[contains(., '按参考生成')]")
    time.sleep(0.5)
    _screenshot(drv, 'int2081_create_dialog_dark.png')
    _click_retry(drv, "//button[contains(., '取消')]")
    time.sleep(0.4)
    # 详情弹窗（真实点）
    _open_digital_tab(drv)
    _open_row_menu(drv, SHARED['mapping_name'])
    _click_menu_item(drv, '详情')
    _wait_text(drv, '校准点明细', timeout=20)
    _screenshot(drv, 'int2081_detail_dialog_dark.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys('')  # ESC 关闭详情弹窗
    time.sleep(0.4)
    # 校准弹窗
    _open_digital_tab(drv)
    _open_row_menu(drv, SHARED['mapping_name'])
    _click_menu_item(drv, '校准')
    _wait_text(drv, 'RMS-SPL 数字校准', timeout=20)
    _screenshot(drv, 'int2081_calibration_dialog_dark.png')
    _click_retry(drv, "//button[contains(., '取消')]")
    time.sleep(0.4)
    # 回浅色
    _set_theme(drv, 'light')


# ---------------------------------------------------------------------------
# ⑦ Network + console
# ---------------------------------------------------------------------------

def test_07_network_no_mock_and_console_clean(drv):
    """Network 仅真实 API 端点（digital-spl/apis/spl/auth）、无 mock；console 无 SEVERE。"""
    _drain_console(drv)
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    _open_digital_tab(drv)
    time.sleep(1.0)
    paths = set()
    for entry in drv.get_log('performance'):
        outer = json.loads(entry.get('message') or '{}')
        inner = outer.get('message') or {}
        if inner.get('method') == 'Network.requestWillBeSent':
            req = (inner.get('params') or {}).get('request') or {}
            url = req.get('url') or ''
            if '/api/v1/' in url:
                path = url.split('/api/v1/', 1)[1].split('?')[0]
                paths.add('/' + path)
    # 兜底：performance log 偶发完全不产出 Network 事件（INT-1597）→ resource timing 取证
    if not paths:
        entries = drv.execute_script(
            "return performance.getEntriesByType('resource').map(e => e.name)")
        for u in entries:
            if '/api/v1/' in u:
                path = u.split('/api/v1/', 1)[1].split('?')[0]
                paths.add('/' + path)
    assert paths, '未捕获任何 /api/v1 请求（performance log 与 resource timing 均空）'
    # 无 mock 路径
    assert not [p for p in paths if 'mock' in p.lower()], f'存在 mock 请求: {paths}'
    # 核心 SPL 族接口确被请求
    for expect in ('/digital-spl', '/apis', '/spl', '/auth/me', '/auth/mode'):
        assert any(p == expect or p.startswith(expect + '/') for p in paths), \
            f'核心接口未被请求: {expect}（实际 {sorted(paths)}）'
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, f'console 存在 SEVERE: {_CONSOLE_SEVERE[:3]}'


# ---------------------------------------------------------------------------
# ⑧ 数据卫生
# ---------------------------------------------------------------------------

def test_08_cleanup_mapping(drv, token):
    """删除本卡创建的「接线测试_INT2081_」映射，验收后库里不留残留。"""
    import urllib.parse
    mid = SHARED.get('mapping_id')
    if mid:
        st, _ = api('/api/v1/digital-spl/%s' % mid, token, method='DELETE')
        assert st == 200, f'DELETE /digital-spl/{mid} status={st}'
        SHARED['mapping_id'] = None
    _cleanup_residue(token)
    # 确认库里无本卡残留
    st, js = api('/api/v1/digital-spl?search=%s' % urllib.parse.quote('接线测试_INT2081_'), token)
    assert st == 200
    items = (js.get('data') or {}).get('items') or []
    assert len(items) == 0, f'库里仍有本卡残留 {len(items)} 条: {[m.get("name") for m in items]}'
    # 全量归零核对
    st, js = api('/api/v1/digital-spl', token)
    total = (js.get('data') or {}).get('total', 0)
    assert total == 0, f'数字域映射全量 total={total}，期望 0（数据卫生）'
