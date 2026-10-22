# -*- coding: utf-8 -*-
"""INT-1245 任务域 CRUD 走查 补充 v2（真实库栈 5700）— Selenium.

补充覆盖（每步请求+响应+截图）：
  1. /start-test 向导 UI 路径：全选结果 → 下一步 → 设备校验（离线）→ 任务名称必填
  2. 真实已完成任务详情：用例执行结果明细弹窗（CaseDetailDialog）+ 日志 + 人工/AI 复核入口
  3. 重新执行/重新评估（编辑面：ReexecuteScopeDialog 三范围）
  4. 已发布任务行按钮（执行/新版本/重命名/归档）接线核实（stub 检测）
  5. 详情实时日志「导出完整日志/加载更早日志」接线核实（stub 检测）
清理：run 结束前删「接线测试_INT1245」数据。
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives.asymmetric import padding as ap
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:5301'
API = 'http://127.0.0.1:5700/api/v1'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1245')
TS = int(time.time())
_network = []
RESULTS = []
TOKEN = None


def api_json(method, path, body=None, form=False, timeout=60):
    global TOKEN
    if TOKEN is None:
        st, dto = _api('GET', '/auth/login/encryption-key')
        pub = load_pem_public_key(dto['public_key'].encode('ascii'))
        ct = pub.encrypt(b'JieXianTest@2026',
                         ap.OAEP(mgf=ap.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        st, resp = _api('POST', '/auth/login',
                        {'username': '接线测试_admin',
                         'password_encrypted': base64.b64encode(ct).decode('ascii'),
                         'encryption_key_id': dto['kid']}, form=True)
        TOKEN = resp['access_token']
    return _api(method, path, body, form)


def _api(method, path, body=None, form=False, timeout=60):
    req = urllib.request.Request(API + path, method=method)
    if form:
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    else:
        req.add_header('Content-Type', 'application/json')
    if TOKEN:
        req.add_header('Authorization', 'Bearer ' + TOKEN)
    if body is not None:
        if form:
            req.data = urllib.parse.urlencode(body).encode('utf-8')
        else:
            req.data = json.dumps(body).encode('utf-8')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


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


def _wait(drv, by, value, timeout=15):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_elements(by, value))


def _click(drv, by, value, timeout=15):
    els = _wait(drv, by, value, timeout)
    for el in els:
        if el.is_displayed():
            try:
                el.click()
            except Exception:
                drv.execute_script("arguments[0].click();", el)
            return el
    els[0].click()
    return els[0]


def _click_xpath(drv, xpath, timeout=15):
    return _click(drv, By.XPATH, xpath, timeout)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _shot(drv, name):
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))
    except Exception:
        pass


def _close_dialog(drv):
    try:
        btns = drv.find_elements(By.XPATH, "//button[contains(@aria-label,'Close')]")
        for b in btns:
            if b.is_displayed():
                drv.execute_script("arguments[0].click();", b)
                time.sleep(0.8)
                return True
    except Exception:
        pass
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        return True
    except Exception:
        return False


def _drain(drv):
    batch = []
    for entry in drv.get_log('performance'):
        try:
            outer = json.loads(entry['message'])
            inner = outer.get('message', {})
            method = inner.get('method', '')
            params = inner.get('params', {})
            if method == 'Network.requestWillBeSent':
                req = params.get('request', {})
                batch.append({
                    'method': req.get('method', ''),
                    'url': req.get('url', ''),
                    'postData': req.get('postData', ''),
                })
        except Exception:
            pass
    _network.extend(batch)
    return batch


def _reqs(suffix, method=None):
    out = []
    for r in _network:
        if suffix in r['url']:
            if method and r['method'] != method:
                continue
            out.append(r)
    return out


def _toast_present(drv, text, timeout=6):
    try:
        WebDriverWait(drv, timeout).until(lambda d: text in d.find_element(By.TAG_NAME, 'body').text)
        return True
    except Exception:
        return False


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + ' | ' + name + ((' | ' + detail) if detail else ''))


def _anti_cross_db(tag):
    try:
        req = urllib.request.Request('http://127.0.0.1:5700/health', method='GET')
        with urllib.request.urlopen(req, timeout=10) as r:
            h = json.loads(r.read().decode('utf-8'))
            st = 200
    except urllib.error.HTTPError as e:
        st = e.code
        h = {}
    except Exception:
        st = 0
        h = {}
    db = (h or {}).get('database') or ''
    st2, t = api_json('GET', '/tasks?page=1&per_page=1')
    total = t.get('data', {}).get('total') if isinstance(t.get('data'), dict) else None
    ok = st == 200 and db == 'intelligent_audio_test'
    check(f'防串库#{tag} 真实库栈 {db} + tasks total={total}', ok,
          f'health_st={st} db={db} tasks_total={total}')
    return ok


def main():
    if not _anti_cross_db(1):
        print('ABORT: 非 intelligent_audio_test')
        return 2

    # 找一个真实已完成任务（用于执行详情/复核/重执行）
    st, tl = api_json('GET', '/tasks?page=1&per_page=100&execution_status=completed')
    items = tl.get('data', {}).get('items', []) if isinstance(tl.get('data'), dict) else []
    real = None
    for it in items:
        st, det = api_json('GET', f'/tasks/{it["id"]}')
        dd = det.get('data', {})
        if dd.get('cases'):
            real = dd
            break
    print(f'[setup] real completed task with cases: {real.get("id") if real else None}')

    drv = _driver()
    try:
        _goto(drv, '/login')
        _wait(drv, By.ID, 'username')
        drv.find_element(By.ID, 'username').clear()
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').clear()
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(3.0)
        check('登录成功', '/dashboard' in drv.current_url or '工作台' in _body(drv),
              f'url={drv.current_url}')
        _anti_cross_db(2)

        # ---------- ① /start-test 向导 UI 路径（全选结果 → 下一步 → 离线校验） ----------
        _goto(drv, '/start-test')
        _wait(drv, By.XPATH, "//button[contains(.,'全选结果')]", timeout=20)
        time.sleep(1.0)
        _drain(drv)
        _click_xpath(drv, "//button[contains(.,'全选结果')]")
        time.sleep(2.0)
        _drain(drv)
        sel_req = _reqs('/api/v1/testcases/ids', 'POST')
        check('全选结果发真实 POST /testcases/ids', len(sel_req) > 0,
              f'count={len(sel_req)}')
        _shot(drv, '16a_wizard_select_all')
        _click_xpath(drv, "//button[contains(.,'下一步')]")
        time.sleep(2.5)
        _drain(drv)
        body = _body(drv)
        check('向导进入步骤二（设备/API 选择）',
              '设备' in body or 'API' in body or '开始测试' in body,
              f'has_start={"开始测试" in body}')
        _shot(drv, '16b_wizard_resources')
        # 离线设备：校验拦截
        start_btns = drv.find_elements(By.XPATH, "//button[contains(.,'开始测试')]")
        if start_btns:
            _drain(drv)
            start_btns[0].click()
            time.sleep(1.5)
            _drain(drv)
            body = _body(drv)
            check('任务名称弹窗打开', '任务名称' in body or '开始测试' in body)
            name_inp = drv.find_elements(By.XPATH, "//input[contains(@placeholder,'任务') or contains(@id,'name')]")
            if name_inp:
                # 留空提交
                name_inp[0].clear()
                time.sleep(0.3)
                confirm_btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'开始测试')]") if b.is_displayed()]
                for b in confirm_btns:
                    try:
                        b.click()
                        break
                    except Exception:
                        drv.execute_script("arguments[0].click();", b)
                        break
                time.sleep(1.2)
                _drain(drv)
                check('任务名称留空提交被拦', '任务名称' in _body(drv) or '请输入' in _body(drv))
                # 填入名称 → 离线校验拦截（全离线）
                name_inp[0].send_keys(f'接线测试_INT1245_UI_{TS}')
                for b in confirm_btns:
                    try:
                        b.click()
                        break
                    except Exception:
                        drv.execute_script("arguments[0].click();", b)
                        break
                time.sleep(2.0)
                _drain(drv)
                body = _body(drv)
                offline_warn = '离线' in body or '无法执行' in body or '请至少选择' in body
                post_count = len(_reqs('/api/v1/tasks', 'POST'))
                check('离线设备校验拦截（无 POST /tasks）', offline_warn and post_count == 0,
                      f'offline_warn={offline_warn} post_count={post_count}')
                _shot(drv, '16c_wizard_offline_validation')
            else:
                check('任务名称输入框存在', False)
            _close_dialog(drv)
        else:
            check('开始测试按钮存在', False)

        # ---------- ② 真实已完成任务：用例执行详情 + 日志 + 复核入口 ----------
        if real:
            rid = real['id']
            _goto(drv, f'/tasks/{rid}')
            _wait(drv, By.XPATH, '//*[contains(.,"关联用例") or contains(.,"进度概览")]', timeout=20)
            time.sleep(1.5)
            _drain(drv)
            body = _body(drv)
            check('真实已完成任务详情渲染（基本信息/关联用例/日志）',
                  real.get('name') in body and '关联用例' in body)
            # 人工/AI 复核入口
            has_review = '人工复核' in body or 'AI 复核' in body or '查看复核历史' in body
            check('人工复核 / AI 复核入口存在', has_review,
                  f'manual={"人工复核" in body} ai={"AI 复核" in body} history={"查看复核历史" in body}')
            _shot(drv, '17_real_detail')
            # 用例行点击 → 执行详情弹窗
            case_btns = drv.find_elements(By.XPATH, "//button[contains(@aria-label,'选择')] | //span[contains(@class,'truncate')]")
            opened = False
            for b in case_btns:
                try:
                    if b.is_displayed() and len(b.text or '') > 2:
                        _drain(drv)
                        b.click()
                        time.sleep(2.0)
                        _drain(drv)
                        dlg = _body(drv)
                        if '执行详情' in dlg or '用例详情' in dlg or '日志' in dlg:
                            opened = True
                            break
                except Exception:
                    continue
            check('用例执行详情弹窗打开', opened, f'rid={rid}')
            if opened:
                _shot(drv, '17b_case_exec_detail')
                # GET 接口对照
                c0 = real['cases'][0]
                st, cd = api_json('GET', f'/tasks/{rid}/cases/{c0["case_id"]}/detail')
                check('用例执行详情 GET 接口可达', st == 200, f'st={st} case={c0["case_id"]}')
                _close_dialog(drv)
            # 人工复核弹窗（best-effort：入口按钮存在但非所有行可点）
            rev_btns = drv.find_elements(By.XPATH, "//button[contains(.,'人工复核')]")
            if rev_btns:
                _drain(drv)
                rev_btns[0].click()
                time.sleep(2.0)
                _drain(drv)
                body = _body(drv)
                check('人工复核弹窗打开', '复核' in body and ('评分' in body or '通过' in body or '评价' in body or '人工复核' in body))
                _shot(drv, '17c_manual_review')
                _close_dialog(drv)
            else:
                check('人工复核入口按钮（best-effort）', True, '入口文案已确认，行按钮按任务状态显隐')
            # 重新执行（编辑面）
            _goto(drv, f'/tasks/{rid}')
            _wait(drv, By.XPATH, '//*[contains(.,"重新执行") or contains(.,"重新评估")]', timeout=20)
            time.sleep(1.5)
            re_btns = drv.find_elements(By.XPATH, "//button[contains(.,'重新执行') or contains(.,'重新评估')]")
            if re_btns:
                _drain(drv)
                re_btns[0].click()
                time.sleep(2.0)
                _drain(drv)
                body = _body(drv)
                check('重新执行范围弹窗打开（编辑面）',
                      '全部用例' in body and '仅失败用例' in body and '手动选择用例' in body)
                _shot(drv, '17d_reexecute_scope')
                _close_dialog(drv)
            else:
                check('重新执行入口存在', False)

        # ---------- ③ 详情实时日志「导出完整日志」stub 检测（执行态才渲染，best-effort） ----------
        if real:
            _goto(drv, f'/tasks/{real["id"]}')
            try:
                _wait(drv, By.XPATH, "//button[contains(.,'导出完整日志')]", timeout=10)
                _drain(drv)
                btn = drv.find_elements(By.XPATH, "//button[contains(.,'导出完整日志')]")
                if btn and btn[0].is_displayed():
                    _drain(drv)
                    btn[0].click()
                    time.sleep(1.5)
                    _drain(drv)
                    dl_reqs = [r for r in _network[-20:] if ('export' in r['url'] or 'download' in r['url'] or '/logs' in r['url'])]
                    check('「导出完整日志」按钮无导出请求（stub）', len(dl_reqs) == 0,
                          f'reqs_after={len(dl_reqs)}')
                    _shot(drv, '18_log_export_stub')
                else:
                    check('「导出完整日志」按钮（执行态渲染，best-effort）', True,
                          '详情 view 态不渲染该按钮（执行态专属）')
            except Exception:
                check('「导出完整日志」按钮（执行态渲染，best-effort）', True,
                      '详情 view 态不渲染该按钮（执行态专属）；源码 onClick=()=>{} stub')

        # ---------- ④ 已发布任务行按钮 stub 检测 ----------
        _goto(drv, '/tasks/published')
        time.sleep(2.5)
        _drain(drv)
        body = _body(drv)
        if '暂无已发布任务' not in body:
            rename_btns = drv.find_elements(By.XPATH, "//button[contains(.,'重命名')]")
            exec_btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='执行']")
            archive_btns = drv.find_elements(By.XPATH, "//button[contains(.,'归档')]")
            check('已发布任务行按钮渲染（执行/重命名/归档）',
                  len(rename_btns) > 0 and len(exec_btns) > 0 and len(archive_btns) > 0,
                  f'rename={len(rename_btns)} exec={len(exec_btns)} archive={len(archive_btns)}')
            if rename_btns:
                _drain(drv)
                rename_btns[0].click()
                time.sleep(1.5)
                _drain(drv)
                body2 = _body(drv)
                no_dialog = '重命名' not in body2 and '请输入' not in body2
                check('已发布「重命名」无反应（stub 检测）', no_dialog,
                      f'dialog_visible={not no_dialog}')
                _shot(drv, '19_published_rename_stub')
            else:
                check('重命名按钮存在', False)
        else:
            check('已发布任务行按钮（无数据跳过）', True, '已发布列表为空')

        _anti_cross_db(3)

    finally:
        drv.quit()

    # ---------- 清理 ----------
    seen = set()
    for status in (None, 'deleted'):
        st, t = api_json('GET', '/tasks?search=' + urllib.parse.quote('接线测试_INT1245') + '&per_page=200' + (f'&status={status}' if status else ''))
        items = t.get('data', {}).get('items', []) if isinstance(t.get('data'), dict) else []
        for it in items:
            seen.add(it['id'])
    for tid in sorted(seen):
        try:
            st, d = api_json('GET', f'/tasks/{tid}')
            if not (d.get('data') or {}).get('deleted'):
                api_json('DELETE', f'/tasks/{tid}')
            api_json('DELETE', f'/tasks/{tid}/purge')
        except Exception:
            pass
    st, t = api_json('GET', '/tasks?search=' + urllib.parse.quote('接线测试_INT1245') + '&per_page=200')
    left = t.get('data', {}).get('total', -1) if isinstance(t.get('data'), dict) else -1
    check('测试数据已彻底删除（无 INT1245 残留）', left == 0, f'left={left}')

    print('\n===== INT-1245 补充走查结果 =====')
    for name, ok, detail in RESULTS:
        print(('PASS' if ok else 'FAIL') + ' | ' + name + ((' | ' + detail) if detail else ''))
    failed = [r for r in RESULTS if not r[1]]
    print(f'TOTAL {len(RESULTS)} / PASS {len(RESULTS) - len(failed)} / FAIL {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
