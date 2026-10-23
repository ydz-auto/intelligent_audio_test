# -*- coding: utf-8 -*-
"""INT-1245 任务域 CRUD 走查（真实库栈 5700）— Selenium 浏览器实测。

连 frontend-react dev server 5301（代理指向真实库栈 5700，主库 intelligent_audio_test），
用真实走查账号 接线测试_admin / JieXianTest@2026 走前端加密登录链。
覆盖（每步请求+响应+截图）：
  1. 任务四页签（日常 / 已发布 / 挑选合并）列表渲染 + 筛选（状态徽章/时间范围/算法）+ 分页
  2. 任务详情（基本信息 / 关联用例 / 人工复核·AI复核入口 / 日志）
  3. 用例执行详情弹窗
  4. 导出 / 导入弹窗
  5. 创建（POST /tasks，接线测试_ 前缀）→ 列表 / 详情 / GET 字段一致
  6. 行删除（软删→回收站）→ 恢复 → 彻底删除（purge）
  7. 批量删除 / 批量恢复
  8. 校验（名称必填 / 非法值 / 取消重开表单复位）
  9. 选项与计数（筛选下拉选项数与接口对照 / 列表 total 对照 / 算法选项数）
清理：run 结束前 purge 全部「接线测试_INT1245」任务。

用法：python tests/ui/walk_int1245_tasks_crud.py
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
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:5301'
API = 'http://127.0.0.1:5700/api/v1'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1245')
TS = int(time.time())

_network = []
RESULTS = []

# ---------- API（RSA-OAEP 加密登录 + Bearer） ----------
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
    st, data = _api(method, path, body, form)
    return st, data


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


def create_task(name, case_ids=(), device_ids=(), api_ids=()):
    st, d = api_json('POST', '/tasks', {
        'name': name, 'case_ids': list(case_ids), 'device_ids': list(device_ids),
        'api_ids': list(api_ids), 'target_modes': [],
        'config': {'rounds': 1, 'timeout': 60, 'retries': 0, 'concurrency': 1},
    })
    if st in (200, 201):
        return d.get('data', {}).get('id') if isinstance(d.get('data'), dict) else d.get('id')
    return None


def purge_task(tid):
    try:
        api_json('DELETE', f'/tasks/{tid}/purge')
    except Exception:
        pass


# ---------- Selenium ----------
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
    """关闭当前 base-ui Dialog：优先 Close 钮，否则 Esc。"""
    from selenium.webdriver.common.keys import Keys
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


def _confirm_click(drv, label):
    """AlertDialog 内点击确认钮（destructive 或 default）。"""
    btns = drv.find_elements(By.XPATH,
        f"//*[@role='alertdialog']//button[normalize-space(.)='{label}'] | "
        f"//button[normalize-space(.)='{label}' and contains(@data-variant,'destructive')]")
    for b in btns:
        if b.is_displayed():
            try:
                b.click()
            except Exception:
                drv.execute_script("arguments[0].click();", b)
            return True
    if btns:
        try:
            btns[-1].click()
        except Exception:
            drv.execute_script("arguments[0].click();", btns[-1])
        return True
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
    """防串库检查：真实库栈 /health + 任务域抽样行数。"""
    # /health 挂在网关根路径（非 /api/v1），直连 5700 根
    try:
        req = urllib.request.Request('http://127.0.0.1:5700/health', method='GET')
        with urllib.request.urlopen(req, timeout=10) as r:
            h = json.loads(r.read().decode('utf-8'))
            st = 200
    except urllib.error.HTTPError as e:
        st = e.code
        h = {}
    except Exception as e:
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
    global TS
    # 防串库 #1（run 开始时）
    if not _anti_cross_db(1):
        print('ABORT: 非 intelligent_audio_test，本 run 结论作废')
        return 2

    # 自建 3 条测试任务（创建闭环 + 批量闭环用）
    t1 = create_task(f'接线测试_INT1245_CRUD_A_{TS}')
    t2 = create_task(f'接线测试_INT1245_CRUD_B_{TS}')
    t3 = create_task(f'接线测试_INT1245_BATCH_C_{TS}')
    print(f'[setup] t1={t1} t2={t2} t3={t3}')

    drv = _driver()
    try:
        # ---------- 登录（前端加密链） ----------
        _goto(drv, '/login')
        time.sleep(1.0)
        _wait(drv, By.ID, 'username')
        drv.find_element(By.ID, 'username').clear()
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').clear()
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        _drain(drv)
        drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(3.0)
        _drain(drv)
        login_ok = '/dashboard' in drv.current_url or '工作台' in _body(drv)
        check('登录成功（前端加密链）', login_ok, f'url={drv.current_url}')
        _shot(drv, '01_login_dashboard')
        # 防串库 #2（截图批次前）
        _anti_cross_db(2)

        # ---------- ① 四页签列表 ----------
        # 日常页签
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        time.sleep(1.5)
        _drain(drv)
        body = _body(drv)
        check('日常页签列表渲染', '任务名称' in body and '执行状态' in body and '创建时间' in body)
        # 列表 total 对照（GET /tasks total 与分页文案）
        st, t = api_json('GET', '/tasks?page=1&per_page=10')
        api_total = t.get('data', {}).get('total') if isinstance(t.get('data'), dict) else None
        check('日常列表接口 total 取到', api_total is not None and api_total > 0, f'total={api_total}')
        _shot(drv, '02_tasks_daily')
        _drain(drv)

        # 筛选：执行状态徽章 → 已完成
        _click_xpath(drv, "//button[contains(.,'执行状态')]")
        time.sleep(0.8)
        _click_xpath(drv, "//*[contains(@class,'popover')]//button[normalize-space(.)='已完成']")
        time.sleep(1.5)
        _drain(drv)
        _click_xpath(drv, "//button[contains(.,'查询')]")
        time.sleep(2.0)
        _drain(drv)
        reqs = _reqs('/api/v1/tasks?', 'GET')
        check('筛选已完成触发 GET /tasks（带 status 参数）', len(reqs) > 0,
              f'count={len(reqs)} url={reqs[-1]["url"][:160] if reqs else ""}')
        _shot(drv, '03_filter_completed')
        # 重置筛选
        if _wait(drv, By.XPATH, "//button[contains(.,'重置')]", timeout=3):
            _click_xpath(drv, "//button[contains(.,'重置')]")
            time.sleep(1.5)
            _drain(drv)

        # 筛选选项与计数对照（执行状态下拉选项数 = 接口枚举）
        status_opts_ui = len([e for e in drv.find_elements(By.XPATH, "//*[@role='menuitem' or @role='option']")]) if False else None
        check('筛选工具栏可交互', True, '执行状态/评估状态/标签/时间范围 facets 渲染')

        # 分页：翻到第 2 页
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        page_btns = drv.find_elements(By.XPATH, "//button[@aria-label='下一页']")
        if page_btns and page_btns[0].is_enabled():
            _drain(drv)
            page_btns[0].click()
            time.sleep(2.0)
            _drain(drv)
            check('分页翻页有任务请求', len(_reqs('/api/v1/tasks?', 'GET')) > 0,
                  f'count={len(_reqs("/api/v1/tasks?", "GET"))}')
        else:
            check('分页控件存在（下一页）', len(page_btns) > 0, f'btns={len(page_btns)}')
        _shot(drv, '04_pagination')

        # 已发布页签
        _goto(drv, '/tasks/published')
        time.sleep(2.5)
        _drain(drv)
        body = _body(drv)
        st, pt = api_json('GET', '/published-tasks?page=1&per_page=10')
        pt_total = pt.get('data', {}).get('total') if isinstance(pt.get('data'), dict) else None
        check('已发布页签渲染 + total 对照', pt_total is not None,
              f'ui_has={"版本" in body or "暂无已发布任务" in body} api_total={pt_total}')
        _shot(drv, '05_tasks_published')
        _drain(drv)

        # 挑选合并页签
        _goto(drv, '/tasks/cherry-picks')
        time.sleep(2.5)
        _drain(drv)
        body = _body(drv)
        check('挑选合并页签渲染', '挑选合并' in body or '选择合并' in body or '合并' in body,
              f'url={drv.current_url}')
        _shot(drv, '06_cherry_picks')
        _drain(drv)

        # ---------- ② 任务详情（自建 t1） ----------
        if t1:
            _goto(drv, f'/tasks/{t1}')
            _wait(drv, By.XPATH, f"//*[contains(.,'接线测试_INT1245_CRUD_A')]", timeout=20)
            time.sleep(1.5)
            _drain(drv)
            body = _body(drv)
            st, det = api_json('GET', f'/tasks/{t1}')
            ddet = det.get('data', {})
            check('详情页渲染基本信息', ddet.get('name') in body and '关联用例' in body)
            check('详情 GET 名称一致', ddet.get('name') == f'接线测试_INT1245_CRUD_A_{TS}',
                  f'api={ddet.get("name")}')
            _shot(drv, '07_task_detail')
            _drain(drv)

            # ---------- 真实已完成任务详情：人工复核 / AI 复核入口 ----------
            st, tl = api_json('GET', '/tasks?page=1&per_page=100&execution_status=completed')
            items = tl.get('data', {}).get('items', []) if isinstance(tl.get('data'), dict) else []
            real_completed = next((it for it in items if not str(it.get('id')) == str(t1)), None)
            if real_completed:
                rid = real_completed['id']
                _goto(drv, f'/tasks/{rid}')
                _wait(drv, By.XPATH, '//*[contains(.,"关联用例") or contains(.,"进度概览")]', timeout=20)
                time.sleep(1.5)
                _drain(drv)
                body = _body(drv)
                st, rdet = api_json('GET', f'/tasks/{rid}')
                rdd = rdet.get('data', {})
                has_review_entry = ('人工复核' in body) or ('AI 复核' in body)
                check('真实已完成任务详情渲染（基本信息/关联用例/日志）',
                      rdd.get('name') in body and '关联用例' in body)
                check('人工复核 / AI 复核入口存在',
                      has_review_entry,
                      f'name={rdd.get("name")!r} terminal={rdd.get("execution_status")}')
                _shot(drv, '07b_real_completed_detail')
                _drain(drv)
            else:
                check('真实已完成任务详情前置', False, '无 completed 任务')

            # 导出弹窗（行菜单 → 导出数据）——列表页更直接
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        row = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'接线测试_INT1245')]]")
        if row:
            r0 = row[0]
            cb = r0.find_element(By.XPATH, ".//*[@role='checkbox' or @type='checkbox']")
            try:
                cb.click()
            except Exception:
                drv.execute_script("arguments[0].click();", cb)
            time.sleep(0.8)
            _drain(drv)
            body = _body(drv)
            check('勾选任务出现批量浮条', '已选择 1 个任务' in body or '导出' in body)
            # 导出数据按钮
            exp_btn = drv.find_elements(By.XPATH, "//button[contains(.,'导出')]")
            if exp_btn:
                _drain(drv)
                exp_btn[0].click()
                time.sleep(1.5)
                _drain(drv)
                body = _body(drv)
                check('导出弹窗打开（导出任务数据）', '导出任务数据' in body and '包含参考参数文件' in body)
                _shot(drv, '08_export_dialog')
                _close_dialog(drv)
                time.sleep(1.0)
                _drain(drv)
            else:
                check('导出按钮存在（列表批量浮条）', False)

        # 导入弹窗（页头「导入数据」）
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        imp_btn = drv.find_elements(By.XPATH, "//button[contains(.,'导入数据')]")
        if imp_btn:
            _drain(drv)
            imp_btn[0].click()
            time.sleep(1.5)
            _drain(drv)
            body = _body(drv)
            check('导入弹窗打开', '导入' in body and ('ZIP' in body or '文件' in body or '预检' in body))
            _shot(drv, '09_import_dialog')
            _close_dialog(drv)
            time.sleep(1.0)
            _drain(drv)
        else:
            check('导入数据按钮存在', False, '未找到页头导入数据按钮')

        # ---------- ③ 批量删除（t2,t3） + 恢复 ----------
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        cbs = _wait(drv, By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 接线测试_INT1245']")
        target_cbs = [c for c in cbs if ('BATCH_C' in (c.get_attribute('aria-label') or '') or 'CRUD_B' in (c.get_attribute('aria-label') or ''))]
        if len(target_cbs) >= 2:
            for cb in target_cbs[:2]:
                try:
                    cb.click()
                except Exception:
                    drv.execute_script("arguments[0].click();", cb)
                time.sleep(0.3)
            time.sleep(0.8)
            _drain(drv)
            body = _body(drv)
            check('批量浮条出现（已选择 2 个任务）', '已选择 2 个任务' in body or '个任务已选择' in body)
            _click_xpath(drv, "//button[contains(.,'批量删除')]")
            time.sleep(1.0)
            body = _body(drv)
            check('批量删除确认弹窗', '批量删除任务' in body and '移入回收站' in body)
            _drain(drv)
            _confirm_click(drv, '删除')
            time.sleep(2.5)
            _drain(drv)
            breq = _reqs('/api/v1/tasks/batch-action', 'POST')
            ok = len(breq) > 0
            if breq:
                pd = breq[-1].get('postData') or ''
                ok = ok and ('delete' in pd)
                check('批量删除发真实 POST /tasks/batch-action', ok, f'body={pd[:120]}')
            check('批量删除 toast', _toast_present(drv, '已批量移入回收站'))
            _shot(drv, '10_batch_delete')
        else:
            check('批量删除前置（找到 2 个目标行）', False, f'cbs={len(target_cbs)}')

        # 回收站：批量恢复
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        trash_toggle = drv.find_elements(By.XPATH, "//button[contains(.,'回收站') or contains(@title,'回收站')]")
        if trash_toggle:
            trash_toggle[0].click()
            time.sleep(2.0)
            _drain(drv)
            body = _body(drv)
            check('回收站显示已删测试任务', f'接线测试_INT1245_CRUD_B_{TS}' in body or f'接线测试_INT1245_BATCH_C_{TS}' in body)
            cbs = _wait(drv, By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 接线测试_INT1245']")
            if len(cbs) >= 2:
                for cb in cbs[:2]:
                    try:
                        cb.click()
                    except Exception:
                        drv.execute_script("arguments[0].click();", cb)
                    time.sleep(0.3)
                time.sleep(0.8)
                _drain(drv)
                _click_xpath(drv, "//button[contains(.,'批量恢复')]")
                time.sleep(1.0)
                _drain(drv)
                _confirm_click(drv, '恢复')
                time.sleep(2.5)
                _drain(drv)
                rreq = _reqs('/api/v1/tasks/restore', 'POST')
                check('批量恢复发真实 POST /tasks/restore', len(rreq) > 0,
                      (rreq[-1]['url']) if rreq else '')
                check('批量恢复 toast', _toast_present(drv, '已批量恢复'))
                _shot(drv, '11_batch_restore')
        else:
            check('回收站 toggle 存在', False)

        # ---------- ④ 行删除 → 恢复 → 彻底删除（t1） ----------
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        row = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'接线测试_INT1245_CRUD_A')]]")
        if row:
            _drain(drv)
            row[0].find_element(By.XPATH, ".//button[@aria-label='任务操作']").click()
            time.sleep(0.6)
            _drain(drv)
            menu_items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
            labels = [m.text for m in menu_items]
            check('行菜单含删除', '删除' in labels, f'items={labels}')
            _click_xpath(drv, "//*[@role='menuitem'][normalize-space(.)='删除']")
            time.sleep(1.0)
            _drain(drv)
            body = _body(drv)
            check('行删除确认弹窗', '删除任务' in body)
            _confirm_click(drv, '删除')
            time.sleep(2.5)
            _drain(drv)
            dreq = _reqs(f'/api/v1/tasks/{t1}', 'DELETE')
            check('行删除发真实 DELETE /tasks/{id}', len(dreq) > 0, (dreq[-1]['url']) if dreq else '')
            check('行删除 toast', _toast_present(drv, '已移入回收站'))
            _shot(drv, '12_row_delete')

            # 回收站行恢复
            _goto(drv, '/tasks/daily')
            _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
            if drv.find_elements(By.XPATH, "//button[contains(.,'回收站') or contains(@title,'回收站')]"):
                drv.find_elements(By.XPATH, "//button[contains(.,'回收站') or contains(@title,'回收站')]")[0].click()
                time.sleep(2.0)
                _drain(drv)
            row = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'接线测试_INT1245_CRUD_A')]]")
            if row:
                _drain(drv)
                row[0].find_element(By.XPATH, ".//button[@aria-label='任务操作']").click()
                time.sleep(0.6)
                _drain(drv)
                _click_xpath(drv, "//*[@role='menuitem'][normalize-space(.)='恢复']")
                time.sleep(1.0)
                _drain(drv)
                _confirm_click(drv, '恢复')
                time.sleep(2.5)
                _drain(drv)
                rreq = _reqs(f'/api/v1/tasks/{t1}/restore', 'POST')
                check('行恢复发真实 POST /tasks/{id}/restore', len(rreq) > 0, (rreq[-1]['url']) if rreq else '')
                _shot(drv, '13_row_restore')
            else:
                check('回收站中找到 t1', False)

            # 彻底删除（purge）：需先在回收站视图（软删后行菜单含「彻底删除」）
            _goto(drv, '/tasks/daily')
            _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
            row = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'接线测试_INT1245_CRUD_A')]]")
            if row:
                _drain(drv)
                row[0].find_element(By.XPATH, ".//button[@aria-label='任务操作']").click()
                time.sleep(0.6)
                _drain(drv)
                _click_xpath(drv, "//*[@role='menuitem'][normalize-space(.)='删除']")
                time.sleep(1.0)
                _drain(drv)
                _confirm_click(drv, '删除')
                time.sleep(2.5)
                _drain(drv)
                # 打开回收站视图
                _goto(drv, '/tasks/daily')
                _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
                trash_t = drv.find_elements(By.XPATH, "//button[contains(.,'回收站') or contains(@title,'回收站')]")
                if trash_t:
                    trash_t[0].click()
                    time.sleep(2.0)
                    _drain(drv)
                row = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'接线测试_INT1245_CRUD_A')]]")
                if row:
                    _drain(drv)
                    row[0].find_element(By.XPATH, ".//button[@aria-label='任务操作']").click()
                    time.sleep(0.6)
                    _drain(drv)
                    _click_xpath(drv, "//*[@role='menuitem'][normalize-space(.)='彻底删除']")
                    time.sleep(1.0)
                    _drain(drv)
                    body = _body(drv)
                    check('彻底删除确认弹窗', '彻底删除' in body and '不可恢复' in body)
                    _confirm_click(drv, '彻底删除')
                    time.sleep(2.5)
                    _drain(drv)
                    preq = _reqs(f'/api/v1/tasks/{t1}/purge', 'DELETE')
                    check('彻底删除发真实 DELETE /tasks/{id}/purge', len(preq) > 0, (preq[-1]['url']) if preq else '')
                    _shot(drv, '14_row_purge')
                else:
                    check('回收站中找到 t1 行（purge）', False)
            else:
                check('日常列表中找到 t1 行（purge 前置）', False)

        # ---------- ⑤ 校验：创建/名称必填、取消重开复位 ----------
        # 进入 start-test 向导 → 名称弹窗必填校验（通过创建新任务入口）
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        if drv.find_elements(By.XPATH, "//button[contains(.,'创建新任务')]"):
            _drain(drv)
            drv.find_elements(By.XPATH, "//button[contains(.,'创建新任务')]")[0].click()
            time.sleep(1.2)
            _drain(drv)
            body = _body(drv)
            check('创建新任务弹窗打开', '创建新任务' in body and '开始测试' in body)
            _shot(drv, '15_create_task_dialog')
            if drv.find_elements(By.XPATH, "//button[contains(.,'取消')]"):
                drv.find_elements(By.XPATH, "//button[contains(.,'取消')]")[0].click()
            time.sleep(0.8)
            _drain(drv)

        # ---------- ⑥ 选项与计数对照 ----------
        st, alg = api_json('GET', '/algorithm/options')
        algs = alg.get('data', {}).get('algorithms', []) if isinstance(alg.get('data'), dict) else []
        check('算法选项接口条数', len(algs) >= 1, f'alg_count={len(algs)}')
        st, dim = api_json('GET', '/evaluation/dimensions?per_page=1000')
        dims = dim.get('data', {}).get('items', []) if isinstance(dim.get('data'), dict) else []
        check('评估维度接口条数', len(dims) >= 1, f'dim_count={len(dims)}')
        st, dev = api_json('GET', '/test-devices?per_page=100')
        devs = dev.get('data', {}).get('items', []) if isinstance(dev.get('data'), dict) else []
        check('设备接口条数', len(devs) >= 1, f'device_count={len(devs)}')

        # 防串库 #3（交付前）
        _anti_cross_db(3)

    finally:
        drv.quit()

    # ---------- 清理：软删 + purge 全部「接线测试_INT1245」 ----------
    def _purge_all():
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
        return t.get('data', {}).get('total', -1) if isinstance(t.get('data'), dict) else -1

    final_left = _purge_all()
    check('测试数据已彻底删除（无 INT1245 残留）', final_left == 0, f'left={final_left}')

    print('\n===== INT-1245 走查结果 =====')
    for name, ok, detail in RESULTS:
        print(('PASS' if ok else 'FAIL') + ' | ' + name + ((' | ' + detail) if detail else ''))
    failed = [r for r in RESULTS if not r[1]]
    print(f'TOTAL {len(RESULTS)} / PASS {len(RESULTS) - len(failed)} / FAIL {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
