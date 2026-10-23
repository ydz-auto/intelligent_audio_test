# -*- coding: utf-8 -*-
"""INT-1480 复走·React·设备域 —— 8 个模态窗逐窗实测（截图浅/深色 + 真实请求/响应 + GET 回读）。

环境：docker 真实栈 前端 http://127.0.0.1:15173（nginx，/api → 15000 api_gateway，
真实库 intelligent_audio_test，AUTH_MODE=off）。不起本地前端。

覆盖：
1 scan-devices-dialog      2 device-group-manager-dialog
3 device-mutate-drawer     4 device-detail-dialog
5 device-operate-dialog    6 associate-spl-dialog
7 alarm-rule-dialog        8 laboratory-manager-dialog

数据卫生：只创建「接线测试_INT1480_」前缀记录，结束前删除并 API 复核。
证据落 tests/ui/artifacts/int1480/<步骤>/。
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

BASE = os.environ.get('INT1480_BASE', 'http://127.0.0.1:15173')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1480')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

CRASH_MARKERS = ['糟糕！出错了', '页面加载失败', '哎呀！出错了']
OLD_MOCK_NAMES = ['音箱-客厅位', '音箱-卧室位', '音箱-入门-03', '手机-小米12', '手机-华为P60', '音柱-会议室']
TEST = '接线测试_INT1480_'

_FAILURES = []
_PASS = []


def _check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''), flush=True)
    (_PASS if cond else _FAILURES).append(name)


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
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=12):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(d))


def _wait_gone(drv, text, timeout=10):
    WebDriverWait(drv, timeout).until(lambda d: text not in _body(d))


def _jsclick(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _set_theme(drv, theme):
    drv.get('about:blank')
    _goto(drv, '/devices/test')
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.5)


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
    except Exception as e:
        print(f'  (evidence {name} failed: {e})', flush=True)


def _drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def _net(drv, path_substr):
    reqs, resp = {}, {}
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


def _api(path, method='GET', body=None):
    url = BASE + '/api/v1' + path
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode('utf-8')
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def _payload(resp):
    """统一信封解包：{success, code, data:{...}} → data"""
    if isinstance(resp, dict) and 'data' in resp:
        return resp.get('data')
    return resp


def _menu_item(drv, label, timeout=6):
    def find(d):
        for it in d.find_elements(By.XPATH, "//*[@role='menuitem']"):
            try:
                if label in it.text and it.is_displayed():
                    return it
            except Exception:
                continue
        return False
    return WebDriverWait(drv, timeout).until(find)


def _open_more(drv):
    _jsclick(drv, drv.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
    time.sleep(0.6)


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.8)


def _close_dialog(drv):
    btns = drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '关闭') or contains(., '取消')]")
    for b in btns:
        if b.is_displayed():
            _jsclick(drv, b)
            time.sleep(0.8)
            return True
    _press_esc(drv)
    return False


def _switch(drv, label):
    return drv.find_element(By.XPATH, f"//button[@role='switch' and @aria-label='{label}']")


def _row_action(drv, name):
    return drv.find_element(By.XPATH, f"//button[@aria-label='操作 {name}']")


# ============================ 主流程 ============================
def main():
    drv = _driver()
    created_device_id = None
    created_rule_name = None

    try:
        # ---------- 环境核验 / 列表真实数据 ----------
        mode = _api('/auth/mode')
        _check('环境 auth_mode 可读', mode[0] == 200, str(mode))
        st, devlist = _api('/test-devices?page=1&per_page=100')
        devs = _payload(devlist) or {}
        dev_items = devs.get('items', [])
        _check('后端 GET /test-devices 真实数据', st == 200 and len(dev_items) > 0,
               f'total={devs.get("total")} names={[d["name"] for d in dev_items]}')

        _drain_perf(drv)
        _goto(drv, '/devices/test')
        _wait_text(drv, '设备管理', 25)
        time.sleep(1.5)
        txt = _body(drv)
        _check('列表页渲染真实设备（名称来自 GET）',
               all(d['name'] in txt for d in dev_items[:4]),
               detail=f'{len(dev_items)} 台')
        _check('列表页无旧 mock 设备名残留', not any(m in txt for m in OLD_MOCK_NAMES))
        _check('列表页无崩溃标记', all(m not in txt for m in CRASH_MARKERS))
        net_list = _net(drv, '/test-devices')
        _check('Network: GET /test-devices 200',
               any(n.get('method') == 'GET' and '/test-devices?' in n.get('url', '')
                   and (n.get('status') or 0) == 200 for n in net_list), detail=f'{net_list[:3]}')

        # ---------- ① 扫描设备弹窗 ----------
        try:
            _drain_perf(drv)
            _open_more(drv)
            _jsclick(drv, _menu_item(drv, '扫描设备'))
            _wait_text(drv, '扫描测试设备', 10)
            _check('① 扫描弹窗打开（标题「扫描测试设备」）', '扫描测试设备' in _body(drv))
            time.sleep(6.0)
            stxt = _body(drv)
            _check('① 扫描完成/空态渲染（真实 POST /test-devices/scan）',
                   '未扫描到任何设备' in stxt or '已添加' in stxt or '扫描完成' in stxt,
                   detail=stxt[-160:].replace('\n', ' '))
            net_scan = _net(drv, '/test-devices/scan')
            _check('① Network: POST /test-devices/scan <300',
                   any(n.get('method') == 'POST' and (n.get('status') or 0) < 300 for n in net_scan),
                   detail=f'{net_scan}')
            _check('① 扫描弹窗无 mock「当前为模拟数据」提示',
                   '当前为模拟数据' not in stxt, detail='源码注释有 mock 兜底提示，实测未命中')
            _save_evidence('01_scan_light', drv)
            _close_dialog(drv)
            _wait_gone(drv, '扫描测试设备')
        except Exception as e:
            _check('① 扫描弹窗流程', False, repr(e))
            _save_evidence('01_scan_error', drv)
            _press_esc(drv)

        # 深色
        try:
            _set_theme(drv, 'dark')
            _open_more(drv)
            _jsclick(drv, _menu_item(drv, '扫描设备'))
            _wait_text(drv, '扫描测试设备', 10)
            time.sleep(5.0)
            _save_evidence('01b_scan_dark', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('①b 扫描弹窗深色', False, repr(e))
        _set_theme(drv, 'light')

        # ---------- ② 设备分组管理 ----------
        try:
            _drain_perf(drv)
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            _open_more(drv)
            _jsclick(drv, _menu_item(drv, '分组管理'))
            _wait_text(drv, '设备分组管理', 10)
            time.sleep(1.5)
            st, groups = _api('/test-devices/device-groups')
            gdata = _payload(groups) or {}
            gitems = gdata.get('items', [])
            gtxt = _body(drv)
            _check('② 分组弹窗打开 + 真实分组渲染',
                   '设备分组管理' in gtxt and all(
                       g['name'] in gtxt for g in gitems[:3]),
                   detail=f'GET 分组 {len(gitems)} 个: {[g["name"] for g in gitems]}')
            net_g = _net(drv, '/test-devices/device-groups')
            _check('② Network: GET /test-devices/device-groups 200',
                   any(n.get('method') == 'GET' and (n.get('status') or 0) == 200 for n in net_g),
                   detail=f'{net_g[:3]}')

            # 新建
            gname = TEST + '组'
            inp = drv.find_element(By.ID, 'group-name')
            inp.clear()
            inp.send_keys(gname)
            _drain_perf(drv)
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '创建')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            WebDriverWait(drv, 10).until(
                lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {gname}']"))
            _check('② 新建分组即时出现', True)
            net_g2 = _net(drv, '/test-devices/device-groups')
            _check('② Network: POST 分组 <300',
                   any(n.get('method') == 'POST' and (n.get('status') or 0) < 300 for n in net_g2),
                   detail=f'{[n for n in net_g2 if n["method"] == "POST"]}')
            st, g2 = _api('/test-devices/device-groups')
            g2names = [g['name'] for g in (_payload(g2) or {}).get('items', [])]
            _check('② GET 回读：新分组已落库', gname in g2names, detail=f'{g2names}')
            _save_evidence('02_group_light', drv)

            # 重命名
            rname = gname + '_改'
            _jsclick(drv, drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {gname}']"))
            _jsclick(drv, _menu_item(drv, '重命名'))
            _wait_text(drv, '重命名分组', 8)
            rn = drv.find_element(By.XPATH, "//input[@placeholder='分组名称']")
            rn.clear()
            rn.send_keys(rname)
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '保存')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            WebDriverWait(drv, 10).until(
                lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {rname}']"))
            st, g3 = _api('/test-devices/device-groups')
            g3names = [g['name'] for g in (_payload(g3) or {}).get('items', [])]
            _check('② 重命名 → GET 回读新名落库', rname in g3names, detail=f'{g3names}')

            # 删除
            _jsclick(drv, drv.find_element(By.XPATH, f"//button[@aria-label='分组操作 {rname}']"))
            _jsclick(drv, _menu_item(drv, '删除'))
            _wait_text(drv, '删除分组', 8)
            for b in drv.find_elements(By.XPATH, "//*[@role='alertdialog']//button[contains(., '删除')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            WebDriverWait(drv, 10).until(
                lambda d: not d.find_elements(By.XPATH, f"//button[@aria-label='分组操作 {rname}']"))
            st, g4 = _api('/test-devices/device-groups')
            g4names = [g['name'] for g in (_payload(g4) or {}).get('items', [])]
            _check('② 删除 → GET 回读已消失（无残留）', rname not in g4names and gname not in g4names,
                   detail=f'{g4names}')
            _close_dialog(drv)
            _wait_gone(drv, '设备分组管理')
        except Exception as e:
            _check('② 分组管理流程', False, repr(e))
            _save_evidence('02_group_error', drv)
            _press_esc(drv)

        # 深色分组弹窗
        try:
            _set_theme(drv, 'dark')
            _open_more(drv)
            _jsclick(drv, _menu_item(drv, '分组管理'))
            _wait_text(drv, '设备分组管理', 10)
            time.sleep(1.2)
            _save_evidence('02b_group_dark', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('②b 分组弹窗深色', False, repr(e))
        _set_theme(drv, 'light')

        # ---------- ③ 新增/编辑抽屉 ----------
        try:
            _drain_perf(drv)
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            dname = TEST + '设备'
            for b in drv.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '测试设备信息', 10)
            _check('③ 新增抽屉打开（测试设备信息分区）', '测试设备信息' in _body(drv))
            _save_evidence('03_mutate_drawer_light_empty', drv)
            drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']").send_keys(dname)
            drv.find_element(By.XPATH, "//input[@placeholder='如：旗舰 S1']").send_keys('INT1480-MODEL')
            try:
                drv.find_element(By.XPATH, "//input[@placeholder='192.168.x.x']").send_keys('10.148.0.9')
            except Exception:
                pass
            try:
                ta = drv.find_element(By.XPATH, "//textarea[@placeholder='设备用途或工位说明']")
                ta.send_keys(TEST + '描述')
            except Exception:
                pass
            for b in drv.find_elements(By.XPATH, "//button[type='submit'][contains(., '保存')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            WebDriverWait(drv, 12).until(lambda d: '测试设备信息' not in _body(d) or '已保存' in _body(d))
            time.sleep(2.0)
            st, lst = _api('/test-devices?page=1&per_page=100')
            items = (_payload(lst) or {}).get('items', [])
            created = [d for d in items if d['name'] == dname]
            _check('③ 新建后 GET 回读命中', len(created) == 1, detail=f'{len(created)}')
            if created:
                created_device_id = created[0]['id']
                c = created[0]
                _check('③ GET 回读字段一致（model/ip）',
                       c.get('model') == 'INT1480-MODEL' and c.get('ip') == '10.148.0.9',
                       detail=f'model={c.get("model")} ip={c.get("ip")}')
            net_post = _net(drv, '/test-devices')
            _check('③ Network: POST /test-devices <300',
                   any(n.get('method') == 'POST' and '/test-devices' in n.get('url', '')
                       and (n.get('status') or 0) < 300 for n in net_post),
                   detail=f'{[n for n in net_post if n["method"] == "POST"][:2]}')
            _wait_text(drv, dname, 10)
            _save_evidence('03b_mutate_created_light', drv)

            # 编辑回显
            _goto(drv, '/devices/test')
            _wait_text(drv, dname, 15)
            _drain_perf(drv)
            _jsclick(drv, _row_action(drv, dname))
            _jsclick(drv, _menu_item(drv, '编辑'))
            _wait_text(drv, '测试设备信息', 10)
            time.sleep(1.2)
            v_name = drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']").get_attribute('value')
            v_model = drv.find_element(By.XPATH, "//input[@placeholder='如：旗舰 S1']").get_attribute('value')
            _check('③ 编辑抽屉回显 name/model', v_name == dname and v_model == 'INT1480-MODEL',
                   detail=f'name={v_name} model={v_model}')
            _save_evidence('03c_mutate_edit_light', drv)
            # 改描述
            try:
                ta = drv.find_element(By.XPATH, "//textarea[@placeholder='设备用途或工位说明']")
                ta.clear()
                ta.send_keys(TEST + '改后描述')
            except Exception:
                pass
            for b in drv.find_elements(By.XPATH, "//button[type='submit'][contains(., '保存')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            time.sleep(2.5)
            st, one = _api(f'/test-devices?page=1&per_page=100')
            got = [d for d in (_payload(one) or {}).get('items', []) if d['id'] == created_device_id]
            _check('③ 编辑保存 → GET 回读描述更新',
                   bool(got) and got[0].get('description') == TEST + '改后描述',
                   detail=f'desc={got[0].get("description") if got else None}')
            net_put = _net(drv, '/test-devices/')
            _check('③ Network: PUT /test-devices/{id} <300',
                   any(n.get('method') == 'PUT' and (n.get('status') or 0) < 300 for n in net_put),
                   detail=f'{[n for n in net_put if n["method"] == "PUT"][:2]}')

            # 校验：必填留空
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 15)
            for b in drv.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '测试设备信息', 10)
            for b in drv.find_elements(By.XPATH, "//button[type='submit'][contains(., '保存')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            time.sleep(1.5)
            vtxt = _body(drv)
            _check('③ 必填留空提交被拦截（名称必填提示/抽屉不关闭）',
                   '测试设备信息' in vtxt and ('必填' in vtxt or '请输入' in vtxt),
                   detail=vtxt[-120:].replace('\n', ' '))
            _save_evidence('03d_mutate_validation_light', drv)
            _close_dialog(drv)
            time.sleep(1.0)
        except Exception as e:
            _check('③ 新增/编辑抽屉流程', False, repr(e))
            _save_evidence('03_mutate_error', drv)
            _press_esc(drv)

        # ---------- ④ 设备详情弹窗 ----------
        try:
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            target = dname if created_device_id else dev_items[0]['name']
            _drain_perf(drv)
            _jsclick(drv, _row_action(drv, target))
            _jsclick(drv, _menu_item(drv, '详情'))
            _wait_text(drv, '测试设备详情', 10)
            time.sleep(1.2)
            dtxt = _body(drv)
            _check('④ 详情弹窗打开（测试设备详情）', '测试设备详情' in dtxt)
            for f in ['基本信息', '名称', '型号', '状态']:
                _check(f'④ 详情含「{f}」', f in dtxt)
            st, lst = _api('/test-devices?page=1&per_page=100')
            row = [d for d in (_payload(lst) or {}).get('items', []) if d['name'] == target]
            if row:
                _check('④ 详情字段与 GET 一致（名称/型号）',
                       target in dtxt and str(row[0].get('model') or '—') in dtxt,
                       detail=f'GET model={row[0].get("model")}')
            _save_evidence('04_detail_light', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('④ 详情弹窗流程', False, repr(e))
            _save_evidence('04_detail_error', drv)
            _press_esc(drv)

        # 详情深色
        try:
            _set_theme(drv, 'dark')
            target = dname if created_device_id else dev_items[0]['name']
            _wait_text(drv, '设备管理', 20)
            _jsclick(drv, _row_action(drv, target))
            _jsclick(drv, _menu_item(drv, '详情'))
            _wait_text(drv, '测试设备详情', 10)
            time.sleep(1.2)
            _save_evidence('04b_detail_dark', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('④b 详情深色', False, repr(e))
            _press_esc(drv)
        _set_theme(drv, 'light')

        # ---------- ⑤ 设备操作参数弹窗（安装/卸载应用） ----------
        try:
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            target = dname if created_device_id else dev_items[0]['name']
            _jsclick(drv, _row_action(drv, target))
            _jsclick(drv, _menu_item(drv, '安装应用'))
            _wait_text(drv, '应用安装包路径', 10)
            _check('⑤ 安装应用弹窗打开（路径/包名两字段）',
                   '应用安装包路径' in _body(drv) and '应用包名' in _body(drv))
            # 必填校验
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '执行安装')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            time.sleep(1.0)
            _check('⑤ 必填留空被拦截', '应用安装包路径' in _body(drv) and
                   ('必填' in _body(drv) or '请输入' in _body(drv)),
                   detail=_body(drv)[-100:].replace('\n', ' '))
            _save_evidence('05_operate_install_light', drv)
            _close_dialog(drv)
            _wait_gone(drv, '应用安装包路径')
            # 卸载分支
            _jsclick(drv, _row_action(drv, target))
            items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
            un = [it for it in items if '卸载应用' in it.text]
            if un:
                _jsclick(drv, un[0])
                time.sleep(1.2)
                _check('⑤ 卸载应用弹窗打开（包名单字段）', '应用包名' in _body(drv))
                _save_evidence('05b_operate_uninstall_light', drv)
                _close_dialog(drv)
            else:
                _check('⑤ 卸载应用菜单项存在', False, '未找到（可能因 iOS/权限禁用）')
        except Exception as e:
            _check('⑤ 设备操作弹窗流程', False, repr(e))
            _save_evidence('05_operate_error', drv)
            _press_esc(drv)

        # ---------- ⑥ 关联声压映射（播放设备） ----------
        try:
            _goto(drv, '/devices/playback')
            _wait_text(drv, '播放设备', 20)
            st, pbl = _api('/playback-devices?page=1&per_page=100')
            pbitems = (_payload(pbl) or {}).get('items', [])
            _check('⑥ 播放设备列表真实数据', len(pbitems) > 0, detail=f'{len(pbitems)} 条')
            if pbitems:
                p = pbitems[0]
                _drain_perf(drv)
                _jsclick(drv, drv.find_element(By.XPATH, f"//button[@aria-label='操作 {p['name']}']"))
                _jsclick(drv, _menu_item(drv, '关联声压映射'))
                _wait_text(drv, '关联声压映射', 10)
                time.sleep(1.5)
                _check('⑥ 关联声压映射弹窗打开', '关联声压映射' in _body(drv))
                st, spl = _api(f"/spl/by-device/{p['id']}?page=1&per_page=100")
                splitems = (_payload(spl) or {}).get('items', [])
                net_spl = _net(drv, '/spl/by-device')
                _check('⑥ Network: GET /spl/by-device/{id} 200（真实选项源）',
                       any((n.get('status') or 0) == 200 for n in net_spl),
                       detail=f'{net_spl[:2]} / 后端选项 {len(splitems)} 条')
                _save_evidence('06_associate_spl_light', drv)
                # 不提交：目标为真实生产播放设备，关联会改写其 current_spl_mapping_id
                _close_dialog(drv)
        except Exception as e:
            _check('⑥ 关联声压映射流程', False, repr(e))
            _save_evidence('06_spl_error', drv)
            _press_esc(drv)

        # ---------- ⑦ 监控告警规则弹窗 ----------
        try:
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            _jsclick(drv, _switch(drv, '监控告警面板'))
            time.sleep(2.0)
            _check('⑦ 监控告警面板展开', '告警' in _body(drv))
            _drain_perf(drv)
            for b in drv.find_elements(By.XPATH, "//button[contains(., '告警规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '监控告警规则', 10)
            time.sleep(1.2)
            _check('⑦ 告警规则弹窗打开（监控告警规则）', '监控告警规则' in _body(drv))
            st, rules = _api('/test-devices/alarm-rules?page=1&per_page=100')
            ritems = (_payload(rules) or {}).get('items', [])
            net_r = _net(drv, '/test-devices/alarm-rules')
            _check('⑦ Network: GET /test-devices/alarm-rules 200',
                   any((n.get('status') or 0) == 200 for n in net_r),
                   detail=f'{net_r[:2]} / 后端规则 {len(ritems)} 条')
            # 新建规则（测试数据，结束前删除）
            rule_name = TEST + '规则'
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '新建规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '创建规则', 8)
            name_input = drv.find_element(By.ID, 'rule-name')
            name_input.send_keys(rule_name)
            # 阈值
            nums = [i for i in drv.find_elements(By.XPATH, "//*[@role='dialog']//input[@type='number']")
                    if i.is_displayed()]
            if nums:
                nums[0].clear()
                nums[0].send_keys('80')
            _drain_perf(drv)
            for b in drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '创建规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            time.sleep(2.5)
            st, rules2 = _api('/test-devices/alarm-rules?page=1&per_page=100')
            r2names = [r.get('name') for r in (_payload(rules2) or {}).get('items', [])]
            _check('⑦ 新建规则 → GET 回读命中', rule_name in r2names, detail=f'{r2names}')
            if rule_name in r2names:
                created_rule_name = rule_name
            _save_evidence('07_alarm_rule_light', drv)
            if created_rule_name:
                # 删除规则
                drv.find_element(By.XPATH, f"//button[@aria-label='删除规则 {created_rule_name}']")
                _jsclick(drv, drv.find_element(By.XPATH, f"//button[@aria-label='删除规则 {created_rule_name}']"))
                _wait_text(drv, '删除告警规则', 8)
                for b in drv.find_elements(By.XPATH, "//*[@role='alertdialog']//button[contains(., '删除')]"):
                    if b.is_displayed():
                        _jsclick(drv, b)
                        break
                time.sleep(2.0)
                st, rules3 = _api('/test-devices/alarm-rules?page=1&per_page=100')
                r3names = [r.get('name') for r in (_payload(rules3) or {}).get('items', [])]
                _check('⑦ 删除规则 → GET 回读已消失', created_rule_name not in r3names, detail=f'{r3names}')
                created_rule_name = None
            _close_dialog(drv)
        except Exception as e:
            _check('⑦ 告警规则流程', False, repr(e))
            _save_evidence('07_alarm_rule_error', drv)
            _press_esc(drv)

        # 告警规则深色
        try:
            _set_theme(drv, 'dark')
            _wait_text(drv, '设备管理', 20)
            _jsclick(drv, _switch(drv, '监控告警面板'))
            time.sleep(2.0)
            for b in drv.find_elements(By.XPATH, "//button[contains(., '告警规则')]"):
                if b.is_displayed():
                    _jsclick(drv, b)
                    break
            _wait_text(drv, '监控告警规则', 10)
            time.sleep(1.2)
            _save_evidence('07b_alarm_rule_dark', drv)
            _close_dialog(drv)
        except Exception as e:
            _check('⑦b 告警规则深色', False, repr(e))
            _press_esc(drv)
        _set_theme(drv, 'light')

        # ---------- ⑧ 实验室管理弹窗 ----------
        try:
            _goto(drv, '/devices/test')
            _wait_text(drv, '设备管理', 20)
            _drain_perf(drv)
            _open_more(drv)
            lab_items = [it for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']")
                         if '实验室管理' in it.text]
            _check('⑧ 「实验室管理」菜单项存在', len(lab_items) > 0)
            disabled = None
            if lab_items:
                disabled = lab_items[0].get_attribute('data-disabled') or lab_items[0].get_attribute('aria-disabled')
            _check('⑧ 「实验室管理」菜单项禁用（后端建设中 Tooltip）', bool(disabled),
                   detail=f'data-disabled={disabled}')
            _save_evidence('08_lab_entry_disabled_light', drv)
            st, labs = _api('/laboratories')
            labitems = (_payload(labs) or {}).get('items', [])
            _check('⑧ 后端 GET /laboratories 实际可用（入口禁用为陈旧假设）', st == 200,
                   detail=f'HTTP {st} items={len(labitems)}')
            # 尝试打开（若禁用则无反应）
            if lab_items:
                try:
                    _jsclick(drv, lab_items[0])
                except Exception:
                    pass
                time.sleep(1.5)
                opened = '实验室管理' in _body(drv) and '新建实验室' in _body(drv)
                _check('⑧ 实验室管理弹窗可打开（入口禁用 → 不可达）', opened,
                       detail='入口禁用时弹窗不可达，无法出浅/深色截图')
                if opened:
                    _save_evidence('08b_lab_dialog_light', drv)
                    _close_dialog(drv)
            _press_esc(drv)
        except Exception as e:
            _check('⑧ 实验室管理流程', False, repr(e))
            _save_evidence('08_lab_error', drv)
            _press_esc(drv)

        # ---------- 清理 ----------
        try:
            if created_device_id:
                st, resp = _api(f'/test-devices/{created_device_id}', 'DELETE')
                _check('清理：DELETE 自建设备 <300', 0 < st < 300, detail=f'HTTP {st} {resp}')
            st, lst = _api('/test-devices?page=1&per_page=100')
            left = [d['name'] for d in (_payload(lst) or {}).get('items', []) if d['name'].startswith(TEST)]
            _check('清理：GET 回读无本卡残留设备', len(left) == 0, detail=f'{left}')
            st, g5 = _api('/test-devices/device-groups')
            lgroups = [g['name'] for g in (_payload(g5) or {}).get('items', []) if g['name'].startswith(TEST)]
            _check('清理：无本卡残留分组', len(lgroups) == 0, detail=f'{lgroups}')
            st, r5 = _api('/test-devices/alarm-rules?page=1&per_page=100')
            lrules = [r.get('name') for r in (_payload(r5) or {}).get('items', []) if str(r.get('name', '')).startswith(TEST)]
            _check('清理：无本卡残留告警规则', len(lrules) == 0, detail=f'{lrules}')
        except Exception as e:
            _check('清理流程', False, repr(e))

    finally:
        try:
            errs = []
            for entry in drv.get_log('browser'):
                if entry.get('level') in ('SEVERE', 'ERROR'):
                    m = entry.get('message', '')
                    if '/algorithm/' in m or '/apis' in m:
                        continue
                    errs.append(m)
            _check('全程无未预期前端 JS 错误', len(errs) == 0, detail=str(errs[:3]))
        except Exception:
            pass
        drv.quit()

    print('\n===== SUMMARY =====', flush=True)
    print(f'PASS {len(_PASS)} / FAIL {len(_FAILURES)}', flush=True)
    for f in _FAILURES:
        print(f'  FAIL: {f}', flush=True)
    with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as fp:
        json.dump({'pass': _PASS, 'fail': _FAILURES}, fp, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    os.makedirs(ARTIFACTS, exist_ok=True)
    main()
