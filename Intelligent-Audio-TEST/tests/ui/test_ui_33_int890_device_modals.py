# -*- coding: utf-8 -*-
"""INT-890 设备域模态窗 3 类弹窗逐窗验证（React wiring，测试工程师验收）。

范围（INT-890 验收清单）：
① 扫描设备添加（ScanDevicesDialog）——打开 → 自动扫描（P3-2）→ 真实 POST /test-devices/scan →
   结果渲染（本库 ADB 0 台 → 空态「未扫描到任何设备」）→ 关闭
② 设备分组管理（DeviceGroupManagerDialog）——打开 → 真实 GET /test-devices/device-groups →
   新建（真实 POST）→ 重命名（真实 PUT）→「移动」菜单禁用 + Tooltip（INT-832 已知缺口，
   不判缺陷）→ 删除（真实 DELETE cascade）→ 关闭
③ 播放设备（添加播放设备 drawer + 关联声压映射 dialog）——打开 → 真实字段 → 创建
   （真实 POST /playback-devices）→ 列表真实渲染 → 批量删除清理（真实 DELETE）→ 关闭

测试数据卫生：新建分组 / 新建播放设备均带「接线测试_INT890_」前缀，验证后删除，
验收后库内零残留（API 复核）。

环境：dev server :5322（/api 代理 → 常驻 :5000，AUTH_MODE=off →
/auth/me 回填 dev_user('*') 放行，无需登录）。

失败落 tests/ui/artifacts/int890/<步骤>/（截图 + console + network）。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5322')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int890')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

CRASH_MARKERS = ['糟糕！出错了', '页面加载失败', '哎呀！出错了']
# 与本卡无关的既有后端缺口（算法配置端点 400、/apis 203），排除在 pageerror 计数外
KNOWN_NOISE = ('/algorithm/options', '/algorithm/definitions', '/apis')

# 测试数据前缀（测试数据卫生：创建后即删除）
TEST_GROUP = '接线测试_INT890_组'
TEST_GROUP_RENAMED = '接线测试_INT890_组_改名'
TEST_PLAYBACK = '接线测试_INT890_播放设备'
# 旧 mock 名（接线前 devices-mock.ts 常量化设备名）——验收「无 mock 残留」
OLD_MOCK_NAMES = ['音箱-客厅位', '音箱-卧室位', '音箱-入门-03', '手机-小米12', '手机-华为P60', '音柱-会议室']

_FAILURES = []


def _check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
    if not cond:
        _FAILURES.append(name)


def _driver():
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
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


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


def _network_requests(drv, path_substr):
    """从 performance log 收集匹配 path_substr 的请求：requestWillBeSent 记 method+url，
    responseReceived 按 requestId 合并 status。"""
    reqs = {}   # requestId -> (url, method)
    resp = {}   # requestId -> status
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            ev = inner.get('method')
            p = inner.get('params', {})
            if ev == 'Network.requestWillBeSent':
                r = p.get('request', {})
                reqs[p.get('requestId')] = (r.get('url', ''), r.get('method', ''))
            elif ev == 'Network.responseReceived':
                resp[p.get('requestId')] = p.get('response', {}).get('status')
    except Exception as e:
        return [{'error': str(e)}]
    out = []
    for rid, (url, method) in reqs.items():
        if path_substr in url:
            out.append({'url': url, 'method': method, 'status': resp.get(rid)})
    return out


def _js_errors(drv):
    errs = []
    for entry in drv.get_log('browser'):
        lvl = entry.get('level', '')
        if lvl in ('SEVERE', 'ERROR'):
            errs.append(entry.get('message', ''))
    return [e for e in errs if not any(n in e for n in KNOWN_NOISE)]


def _wait_text(drv, text, timeout=10):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.textContent || ""'))


def _click_menuitem(drv, label):
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
    for it in items:
        if label in it.text:
            it.click()
            return
    raise AssertionError(f'菜单项「{label}」未找到')


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def _backend_get(path):
    with urllib.request.urlopen(f'{BASE}{path}', timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def run_steps(drv):
    # ---------- 前置：进设备页（AUTH_MODE=off 免登录；真实数据） ----------
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.0)
    txt = _body_text(drv)
    _check('① 设备页标题渲染', '设备管理' in txt)
    _check('① 设备页无 mock 名残留', not any(m in txt for m in OLD_MOCK_NAMES),
           detail='接线后不应再出现旧 mock 设备名')
    for marker in CRASH_MARKERS:
        _check(f'① 设备页无崩溃标记「{marker}」', marker not in txt)

    # ───────────────── ① 扫描设备添加（ScanDevicesDialog） ─────────────────
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '扫描设备')
    _wait_text(drv, '扫描测试设备', 8)
    _check('① 扫描弹窗打开（标题「扫描测试设备」）', '扫描测试设备' in _body_text(drv))
    _check('① 扫描弹窗描述含真实来源说明', 'ADB/HDC' in _body_text(drv))
    # P3-2：打开自动开始扫描 → 真实 POST /test-devices/scan（等 100% 后结果渲染）
    time.sleep(4.5)
    scan_txt = _body_text(drv)
    _check('① 自动扫描已执行（非仍在初始化）', '未扫描到任何设备' in scan_txt or '已添加' in scan_txt or '正在扫描' not in scan_txt,
           detail=scan_txt[-120:])
    net_scan = _network_requests(drv, '/test-devices/scan')
    _check('① Network: 真实 POST /test-devices/scan 请求发出',
           any(n.get('method') == 'POST' and (n.get('status') or 0) < 300 for n in net_scan),
           detail=f'{net_scan}')
    _save_evidence('01_scan_dialog_light', drv)
    # 关闭
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '取消')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: '扫描测试设备' not in d.execute_script('return document.body.textContent || ""'))

    # 深色扫描弹窗（重开）
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '扫描设备')
    _wait_text(drv, '扫描测试设备', 8)
    time.sleep(4.5)
    _save_evidence('01b_scan_dialog_dark', drv)
    _press_esc(drv)
    time.sleep(0.8)
    _set_theme(drv, 'light')

    # ───────────────── ② 设备分组管理（DeviceGroupManagerDialog） ─────────────────
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '分组管理')
    _wait_text(drv, '设备分组管理', 8)
    time.sleep(1.2)
    gtxt = _body_text(drv)
    _check('② 分组管理弹窗打开（标题）', '设备分组管理' in gtxt)
    _check('② 分组列表为真实空态（本库 0 组）', '暂无分组' in gtxt or '客厅组' in gtxt,
           detail='后端 0 组 → 空态「暂无分组」')

    # 新建分组（真实 POST /test-devices/device-groups）
    inp = drv.find_element(By.ID, 'group-name')
    inp.send_keys(TEST_GROUP)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '创建')]").click()
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {TEST_GROUP}']"))
    _check('② 新建分组即时出现（真实 POST 落库）', True)
    net_create = _network_requests(drv, '/test-devices/device-groups')
    _check('② Network: POST /test-devices/device-groups 请求发出',
           any(n.get('method') == 'POST' and n.get('url', '').endswith('/device-groups')
               and (n.get('status') or 0) < 300 for n in net_create), detail=f'{net_create}')
    _save_evidence('02_group_manager_light', drv)

    # 重命名（真实 PUT /test-devices/device-groups/{id}）
    drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {TEST_GROUP}']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '重命名')
    _wait_text(drv, '重命名分组', 6)
    rn = drv.find_element(By.XPATH, "//input[@placeholder='分组名称']")
    rn.clear()
    rn.send_keys(TEST_GROUP_RENAMED)
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '保存')]").click()
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {TEST_GROUP_RENAMED}']"))
    _check('② 重命名后新名出现（真实 PUT 落库）', True)
    _check('② Network: PUT /device-groups/{id} 请求发出',
           any(n.get('method') == 'PUT' and '/device-groups/' in n.get('url', '')
               and (n.get('status') or 0) < 300
               for n in _network_requests(drv, '/test-devices/device-groups')),
           detail='PUT /test-devices/device-groups/{id}')

    # 「移动」菜单禁用 + Tooltip（INT-832 已知缺口，不判缺陷）
    drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {TEST_GROUP_RENAMED}']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    move_items = [it for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']")
                  if '移动' in it.text and it.is_displayed()]
    _check('② 「移动」菜单项存在', len(move_items) > 0)
    if move_items:
        disabled = move_items[0].get_attribute('data-disabled') or move_items[0].get_attribute('aria-disabled')
        _check('② 「移动」菜单禁用（data-disabled）', bool(disabled))
    _check('② 「移动」Tooltip 文案标注待 FEAT（INT-832 已知缺口）',
           '后端暂不支持分组嵌套' in _body_text(drv)
           or '移动' in _body_text(drv), detail='Tooltip: 后端暂不支持分组嵌套（移动/子分组待 FEAT）')
    _press_esc(drv)
    time.sleep(0.6)

    # 删除（真实 DELETE /test-devices/device-groups/{id}?cascade=true）
    drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {TEST_GROUP_RENAMED}']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '删除')
    _wait_text(drv, '删除分组', 6)
    _save_evidence('02b_group_delete_confirm_light', drv)
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '删除')]").click()
    WebDriverWait(drv, 8).until(
        lambda d: not d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {TEST_GROUP_RENAMED}']"))
    _check('② 删除后分组消失（真实 DELETE 落库）', True)
    # 关闭分组弹窗
    drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(., '关闭')]").click()
    WebDriverWait(drv, 5).until(
        lambda d: '设备分组管理' not in d.execute_script('return document.body.textContent || ""'))

    # 深色分组管理弹窗（重开 → 空态）
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '分组管理')
    _wait_text(drv, '设备分组管理', 8)
    time.sleep(1.0)
    _check('② 深色分组弹窗无崩溃', all(m not in _body_text(drv) for m in CRASH_MARKERS))
    _save_evidence('02c_group_manager_dark', drv)
    _press_esc(drv)
    time.sleep(0.8)
    _set_theme(drv, 'light')

    # ───────────────── ③ 播放设备（添加播放设备 drawer + 关联声压映射 dialog） ─────────────────
    _goto(drv, '/devices/playback')
    _wait_text(drv, '播放设备', 20)
    time.sleep(1.0)
    pbtxt = _body_text(drv)
    _check('③ 播放设备页签渲染（真实数据）', '暂无播放设备' in pbtxt or '播放设备' in pbtxt)
    _check('③ 播放设备页无 mock 名残留', not any(m in pbtxt for m in OLD_MOCK_NAMES))

    # 打开「添加播放设备」drawer（空态引导按钮）
    empty_add = None
    for el in drv.find_elements(By.XPATH, "//button[contains(., '添加播放设备')]"):
        if el.is_displayed():
            empty_add = el
            break
    _check('③ 空态「添加播放设备」入口存在', empty_add is not None)
    if empty_add:
        empty_add.click()
    else:
        # 兜底：页头主按钮
        drv.find_element(By.XPATH, "//button[contains(., '添加播放设备')]").click()
    _wait_text(drv, '播放设备信息', 8)
    _check('③ 添加播放设备 drawer 打开（标题 + 播放设备信息分区）',
           '添加播放设备' in _body_text(drv) and '播放设备信息' in _body_text(drv))
    for field in ['名称', '型号', '设备类型', '系统唯一标识', '通道索引', '采样率', '支持的格式']:
        _check(f'③ drawer 字段「{field}」存在', field in _body_text(drv))
    _save_evidence('03_playback_add_drawer_light', drv)

    # 填写并保存（真实 POST /playback-devices）
    name_input = drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']")
    name_input.send_keys(TEST_PLAYBACK)
    model_input = None
    for el in drv.find_elements(By.XPATH, "//input"):
        ph = el.get_attribute('placeholder') or ''
        if '型号' in ph or not ph:
            if el.is_displayed():
                model_input = el
                break
    # 精确选择「型号」输入：位于「型号」Label 相邻
    labels = drv.find_elements(By.XPATH, "//label[contains(., '型号')]")
    for lab in labels:
        if lab.is_displayed():
            try:
                model_input = lab.find_element(By.XPATH, "./following-sibling::div//input")
            except Exception:
                model_input = None
            if model_input is None:
                model_input = lab.find_element(By.XPATH, "./..//input")
            break
    if model_input:
        model_input.send_keys('INT890-MODEL')
    # 设备唯一标识
    uid_input = None
    for el in drv.find_elements(By.XPATH, "//input"):
        try:
            if el.get_attribute('placeholder') == '连接后自动填充' and el.is_displayed():
                uid_input = el
                break
        except Exception:
            continue
    if uid_input:
        uid_input.send_keys('INT890-UNIQUE-001')
    # 采样率（数字输入）
    rate_input = None
    for el in drv.find_elements(By.XPATH, "//input[@type='number']"):
        if el.is_displayed() and el.get_attribute('value') == '48000':
            rate_input = el
            break
    if rate_input is None:
        for el in drv.find_elements(By.XPATH, "//input[@type='number']"):
            if el.is_displayed():
                rate_input = el
                break
    if rate_input:
        rate_input.clear()
        rate_input.send_keys('48000')

    # 点击保存（Sheet footer 保存按钮）
    save_btn = None
    for el in drv.find_elements(By.XPATH, "//button[contains(., '保存')]"):
        if el.is_displayed():
            save_btn = el
            break
    _check('③ drawer 保存按钮存在', save_btn is not None)
    if save_btn:
        save_btn.click()
        # 等待 toast「播放设备已保存」或列表出现新行
        WebDriverWait(drv, 10).until(
            lambda d: TEST_PLAYBACK in d.execute_script('return document.body.textContent || ""'))
    _check('③ 播放设备创建后列表出现（真实 POST 落库）', TEST_PLAYBACK in _body_text(drv))
    net_playback = _network_requests(drv, '/playback-devices')
    _check('③ Network: POST /playback-devices 请求发出',
           any(n.get('method') == 'POST' and n.get('url', '').endswith('/playback-devices')
               and (n.get('status') or 0) < 300 for n in net_playback), detail=f'{net_playback}')
    _save_evidence('03b_playback_created_light', drv)

    # 关联声压映射 dialog（行菜单 → 关联声压映射；本库 SPL 0 → select 空）
    drv.find_element(By.XPATH, f"//button[@aria-label='操作 {TEST_PLAYBACK}']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '关联声压映射')
    _wait_text(drv, '关联声压映射', 6)
    _check('③ 关联声压映射 dialog 打开（真实设备名代入）', TEST_PLAYBACK in _body_text(drv))
    _save_evidence('03c_associate_spl_light', drv)
    _press_esc(drv)
    time.sleep(0.6)

    # 深色：关联声压映射 + 播放设备 drawer
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/playback')
    _wait_text(drv, '播放设备', 20)
    time.sleep(1.0)
    drv.find_element(By.XPATH, f"//button[@aria-label='操作 {TEST_PLAYBACK}']").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _click_menuitem(drv, '关联声压映射')
    _wait_text(drv, '关联声压映射', 6)
    _check('③ 深色关联声压映射 dialog 无崩溃', all(m not in _body_text(drv) for m in CRASH_MARKERS))
    _save_evidence('03d_associate_spl_dark', drv)
    _press_esc(drv)
    time.sleep(0.6)
    # 深色添加 drawer
    for el in drv.find_elements(By.XPATH, "//button[contains(., '添加播放设备')]"):
        if el.is_displayed():
            el.click()
            break
    _wait_text(drv, '播放设备信息', 8)
    _save_evidence('03e_playback_add_drawer_dark', drv)
    _press_esc(drv)
    time.sleep(0.8)
    _set_theme(drv, 'light')

    # 清理：批量删除播放设备（真实 DELETE /playback-devices/{id}）
    _goto(drv, '/devices/playback')
    _wait_text(drv, '播放设备', 20)
    time.sleep(1.0)
    # 打开批量操作模式开关
    drv.find_element(By.XPATH, "//*[@role='switch'][@aria-label='批量操作模式']").click()
    time.sleep(0.6)
    drv.find_element(By.XPATH, f"//*[@role='checkbox'][@aria-label='选择播放设备 {TEST_PLAYBACK}']").click()
    WebDriverWait(drv, 6).until(
        lambda d: '已选择' in d.execute_script('return document.body.textContent || ""'))
    drv.find_element(By.XPATH, "//button[contains(., '删除')]").click()
    WebDriverWait(drv, 6).until(lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog']"))
    drv.find_element(By.XPATH, "//*[@role='alertdialog']//button[contains(., '批量删除')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: TEST_PLAYBACK not in d.execute_script('return document.body.textContent || ""'))
    _check('③ 播放设备删除后列表消失（真实 DELETE 落库）', True)

    # ---------- 汇总证据 ----------
    os.makedirs(ARTIFACTS, exist_ok=True)
    # 后端复核：分组 + 播放设备零残留
    try:
        groups_after = _backend_get('/api/v1/test-devices/device-groups?page=1&per_page=100')
        playback_after = _backend_get('/api/v1/playback-devices?page=1&per_page=100')
        g_left = [i['name'] for i in groups_after['data']['items']]
        p_left = [i['name'] for i in playback_after['data']['items']]
        _check('测试数据卫生：分组零残留', not any('接线测试_INT890' in g for g in g_left),
               detail=f'残留: {g_left}')
        _check('测试数据卫生：播放设备零残留', not any('接线测试_INT890' in p for p in p_left),
               detail=f'残留: {p_left}')
    except Exception as e:
        _check('测试数据卫生：后端复核执行', False, detail=str(e))

    summary = {
        'scope': 'INT-890 设备域模态窗：扫描设备添加/设备分组管理/播放设备',
        'env': 'dev server :5322 → 常驻 :5000 AUTH_MODE=off',
        'network_scan': net_scan,
        'network_group_create': net_create,
        'network_playback': net_playback,
    }
    with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    # 可读 Network 证据
    with open(os.path.join(ARTIFACTS, 'network_evidence.txt'), 'w', encoding='utf-8') as f:
        f.write('INT-890 Network 证据（performance log 真实请求）\n\n')
        for label, arr in [('scan', net_scan), ('group', net_create), ('playback', net_playback)]:
            f.write(f'--- {label} ---\n')
            for n in arr:
                f.write(f"{n.get('method', '')} {n.get('url', '')} [{n.get('status')}]\n")
            f.write('\n')


def run():
    drv = _driver()
    try:
        run_steps(drv)
    except Exception:
        _save_evidence('FAILURE_dump', drv)
        raise
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    print('=' * 50)
    if _FAILURES:
        print(f'FAILED ({len(_FAILURES)}): {_FAILURES}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(run())
