# -*- coding: utf-8 -*-
"""INT-932 任务列表/详情假操作接线修复 — 测试工程师验收浏览器实测（独立脚本，非 pytest）。

连 frontend-react dev server（5301，代理到常驻后端 5000，AUTH_MODE=off dev_user '*'）。
自建测试任务（接线测试-INT932-*）驱动页面操作，Network 证据经 Chrome performance log
（Network.requestWillBeSent）采集；结束前彻底删除测试任务（软删 + purge）。

核对项：
  P1-1 批量删除/恢复 → POST /tasks/batch-action、POST /tasks/restore（真实请求 + toast + 列表刷新）
  P1-2 行删除/恢复/收藏 → DELETE /tasks/{id}、POST /tasks/{id}/restore、POST /tasks/{id}/favorite
  P2-1 排序头可操作（客户端排序，行序变化，无排序请求）
  P2-2 无效任务 id 单请求落错误态（GET /tasks/999999 仅 1 次 + 「任务详情加载失败」+ 重试）
  P3-1 详情暂停/继续/停止 接线（当前共享库无 running/paused 任务，按钮对 pending 态隐藏——
        与缺陷卡「当前库无 running 任务不可 UI 复现，代码可证」一致；代码+后端契约验证）
  P3-2 mock 残留清除（API资源管理无「当前并发 2/4 · 队列长度 3 · 平均响应时间 214ms」；
        用例表无「轮次」列；渲染真实 apis 名 + 在线状态）
  P3-3 移除用例 → DELETE /tasks/{id}/cases/{caseId}（真实请求 + toast + 行消失）

用法：python tests/ui/test_ui_int932_tasks_wiring.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5301')
API = os.environ.get('API_BASE', 'http://localhost:5000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int932_wiring')

TEST_CASE_ID = '74dae4e2-1054-4f35-ba18-17f925d4e761'  # 真实用例 ui467_私有用例

_network = []  # 全局网络捕获


# ---------- 后端直连（建数据/清理） ----------
def api_json(method, path, body=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header('Content-Type', 'application/json')
    if body is not None:
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def create_test_task(name, case_ids):
    d = api_json('POST', '/tasks', {
        'name': name, 'case_ids': case_ids, 'device_ids': [], 'api_ids': [],
        'config': {'rounds': 1, 'timeout': 60, 'retries': 0, 'concurrency': 1},
    })
    return d['data']['id']


def cleanup_task(task_id):
    try:
        api_json('DELETE', f'/tasks/{task_id}')
    except Exception:
        pass
    try:
        api_json('POST', '/tasks/purge', {'ids': [task_id]})
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
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _save_screenshot(drv, name):
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))
        with open(os.path.join(ARTIFACTS, name + '.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
    except Exception:
        pass


def _drain_network(drv):
    """收集 performance log 的 Network.requestWillBeSent 事件（Selenium 外层结构：
    entry.message = JSON string {message:{method,params}, ...}）。"""
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
        WebDriverWait(drv, timeout).until(
            lambda d: text in d.find_element(By.TAG_NAME, 'body').text)
        return True
    except Exception:
        return False


def _row_by_name(drv, name_fragment):
    rows = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'{name_fragment}')]]")
    return rows[0] if rows else None


def _open_row_menu(drv, row):
    btn = row.find_element(By.XPATH, ".//button[@aria-label='任务操作']")
    btn.click()
    time.sleep(0.6)


def _menu_click(drv, label):
    els = drv.find_elements(By.XPATH, f"//*[@role='menuitem' and normalize-space(.)='{label}']")
    if not els:
        els = drv.find_elements(By.XPATH, f"//*[@role='menuitem'][contains(.,'{label}')]")
    if not els:
        return False
    for el in els:
        if el.is_displayed():
            el.click()
            return True
    els[0].click()
    return True


RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + ' | ' + name + ((' | ' + detail) if detail else ''))


def main():
    # ---------- 自建测试任务 ----------
    ts = int(time.time())
    t_p33 = create_test_task(f'接线测试-INT932-P33-{ts}', [TEST_CASE_ID])
    t_bb = create_test_task(f'接线测试-INT932-BATCH-B-{ts}', [])
    t_bc = create_test_task(f'接线测试-INT932-BATCH-C-{ts}', [])
    t_p31 = create_test_task(f'接线测试-INT932-P31-{ts}', [])
    print(f'[setup] test tasks: P33={t_p33} BATCH-B={t_bb} BATCH-C={t_bc} P31={t_p31}')

    drv = _driver()
    try:
        # ---------- 列表真实渲染 ----------
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        body = _body_text(drv)
        check('列表页可渲染（dev_user 自动会话）', '任务名称' in body and '执行状态' in body)

        # ---------- P2-1 排序头可操作 ----------
        first_cell = "//tbody/tr[1]//td[2]//span[contains(@class,'truncate')]"
        first_before = drv.find_elements(By.XPATH, first_cell)
        first_before = first_before[0].text if first_before else ''
        _drain_network(drv)
        _network.clear()  # 只统计排序点击后的请求（客户端排序应为 0 个 tasks 请求）
        _click(drv, By.XPATH, "//thead//th[contains(.,'任务名称')]//button")
        time.sleep(1.0)
        _drain_network(drv)
        first_asc = drv.find_elements(By.XPATH, first_cell)
        first_asc = first_asc[0].text if first_asc else ''
        _click(drv, By.XPATH, "//thead//th[contains(.,'任务名称')]//button")
        time.sleep(1.0)
        first_desc = drv.find_elements(By.XPATH, first_cell)
        first_desc = first_desc[0].text if first_desc else ''
        _click(drv, By.XPATH, "//thead//th[contains(.,'任务名称')]//button")  # 第三击回默认
        time.sleep(1.0)
        sort_reqs = _reqs('/api/v1/tasks?', 'GET')
        check('P2-1 排序头点击改变行序（升/降）',
              first_before and first_asc and first_desc and first_asc != first_desc,
              f'default={first_before[:24]!r} asc={first_asc[:24]!r} desc={first_desc[:24]!r}')
        check('P2-1 排序为客户端排序（点击无新增 tasks 请求）', len(sort_reqs) == 0,
              f'tasks GET count={len(sort_reqs)}')

        # ---------- P1-1 批量删除（BATCH-B/C） ----------
        _goto(drv, '/tasks/daily')
        cbs = _wait(drv, By.CSS_SELECTOR,
                    f"[role='checkbox'][aria-label^='选择 接线测试-INT932-BATCH']")
        if len(cbs) >= 2:
            for cb in cbs[:2]:
                try:
                    cb.click()
                except Exception:
                    drv.execute_script("arguments[0].click();", cb)
                time.sleep(0.2)
            time.sleep(0.6)
            check('批量浮条出现（已选择 2 个任务）', '已选择 2 个任务' in _body_text(drv))
            _drain_network(drv)
            _click(drv, By.XPATH, "//button[contains(.,'批量删除')]")
            time.sleep(3.0)
            _drain_network(drv)
            breq = _reqs('/api/v1/tasks/batch-action', 'POST')
            ok = len(breq) > 0
            detail = ''
            if breq:
                pd = breq[-1].get('postData') or ''
                ok = ok and ('delete' in pd) and (str(t_bb) in pd) and (str(t_bc) in pd)
                detail = f'body={pd[:140]}'
            check('P1-1 批量删除发真实 POST /tasks/batch-action', ok, detail)
            check('P1-1 批量删除 toast「已批量移入回收站 2 个」',
                  _toast_present(drv, '已批量移入回收站 2 个'))
            _goto(drv, '/tasks/daily')
            time.sleep(1.5)
            body = _body_text(drv)
            check('P1-1 批量删除后列表刷新（BATCH 任务消失）',
                  f'接线测试-INT932-BATCH-B-{ts}' not in body
                  and f'接线测试-INT932-BATCH-C-{ts}' not in body)
        else:
            check('P1-1 批量删除前置（找到 BATCH 测试任务行）', False, f'count={len(cbs)}')

        # ---------- P1-2 行删除（P33） ----------
        _goto(drv, '/tasks/daily')
        row = _row_by_name(drv, '接线测试-INT932-P33')
        if row:
            _drain_network(drv)
            _open_row_menu(drv, row)
            _menu_click(drv, '删除')
            time.sleep(3.0)
            _drain_network(drv)
            dreq = _reqs(f'/api/v1/tasks/{t_p33}', 'DELETE')
            check('P1-2 行删除发真实 DELETE /tasks/{id}', len(dreq) > 0,
                  (dreq[-1]['url']) if dreq else '')
            check('P1-2 行删除 toast「已移入回收站」', _toast_present(drv, '已移入回收站'))
            _goto(drv, '/tasks/daily')
            time.sleep(1.5)
            check('P1-2 行删除后列表刷新（P33 消失）',
                  f'接线测试-INT932-P33-{ts}' not in _body_text(drv))
        else:
            check('P1-2 行删除前置（找到 P33 行）', False)

        # ---------- 回收站：批量恢复（BATCH-B/C） + 行恢复（P33） ----------
        _goto(drv, '/tasks/daily')
        _click(drv, By.XPATH, "//button[@title='回收站']")
        time.sleep(2.5)
        body = _body_text(drv)
        check('回收站 toggle 显示已删 3 个测试任务',
              f'接线测试-INT932-BATCH-B-{ts}' in body and f'接线测试-INT932-P33-{ts}' in body)

        cbs = _wait(drv, By.CSS_SELECTOR,
                    f"[role='checkbox'][aria-label^='选择 接线测试-INT932-BATCH']")
        if len(cbs) >= 2:
            for cb in cbs[:2]:
                try:
                    cb.click()
                except Exception:
                    drv.execute_script("arguments[0].click();", cb)
                time.sleep(0.2)
            time.sleep(0.6)
            _drain_network(drv)
            _click(drv, By.XPATH, "//button[contains(.,'批量恢复')]")
            time.sleep(3.0)
            _drain_network(drv)
            rreq = _reqs('/api/v1/tasks/restore', 'POST')
            ok = len(rreq) > 0
            if rreq:
                pd = rreq[-1].get('postData') or ''
                ok = ok and (str(t_bb) in pd) and (str(t_bc) in pd)
            check('P1-1 批量恢复发真实 POST /tasks/restore', ok,
                  (('body=' + pd[:120]) if rreq else ''))
            check('P1-1 批量恢复 toast「已批量恢复」', _toast_present(drv, '已批量恢复'))
        else:
            check('P1-1 批量恢复前置（回收站中找到 BATCH 任务）', False)

        _goto(drv, '/tasks/daily')
        _click(drv, By.XPATH, "//button[@title='回收站']")
        time.sleep(2.0)
        row = _row_by_name(drv, '接线测试-INT932-P33')
        if row:
            _drain_network(drv)
            _open_row_menu(drv, row)
            _menu_click(drv, '恢复')
            time.sleep(3.0)
            _drain_network(drv)
            rreq = _reqs(f'/api/v1/tasks/{t_p33}/restore', 'POST')
            check('P1-2 行恢复发真实 POST /tasks/{id}/restore', len(rreq) > 0,
                  (rreq[-1]['url']) if rreq else '')
            check('P1-2 行恢复 toast「已恢复」', _toast_present(drv, '已恢复'))
        else:
            check('P1-2 行恢复前置（回收站中找到 P33）', False)

        # ---------- P1-2 收藏（请求已发出；off 模式后端限制留证） ----------
        _goto(drv, '/tasks/daily')
        time.sleep(1.5)
        row = _row_by_name(drv, '接线测试-INT932-P33')
        if row:
            _drain_network(drv)
            _open_row_menu(drv, row)
            _menu_click(drv, '收藏')
            time.sleep(2.0)
            toast_text = _body_text(drv)  # 趁 toast 未消失先读
            _drain_network(drv)
            freq = _reqs(f'/api/v1/tasks/{t_p33}/favorite', 'POST')
            check('P1-2 收藏发真实 POST /tasks/{id}/favorite', len(freq) > 0,
                  (freq[-1]['url']) if freq else '')
            # off 模式后端 400「未认证用户禁止收藏」（user_id 缺失）→ 错误 toast 展示服务端文案
            fav_ok = ('收藏失败' in toast_text or '已加入收藏' in toast_text
                      or '未认证' in toast_text or '禁止收藏' in toast_text)
            check('P1-2 收藏请求已发出 + toast（off 模式后端限制文案）', len(freq) > 0 and fav_ok,
                  f'toast_has={[t for t in ("收藏失败","已加入收藏","未认证","禁止收藏") if t in toast_text]}')
        else:
            check('P1-2 收藏前置（找到 P33 行）', False)

        # ---------- P3-2 mock 残留清除（详情 1265：API资源 + 用例表） ----------
        _goto(drv, '/tasks/1265')
        _wait(drv, By.XPATH, "//*[contains(.,'INT314SMOKE_a7104c3a_mock_api')]", timeout=20)
        time.sleep(1.0)
        body = _body_text(drv)
        no_mock = ('当前并发 2/4' not in body and '队列长度 3' not in body
                   and '平均响应时间 214ms' not in body)
        check('P3-2 API资源管理无 mock 并发数据', no_mock)
        check('P3-2 API资源管理渲染真实 apis（在线状态）', '在线' in body)
        round_col = drv.find_elements(By.XPATH, "//th[contains(.,'轮次')]")
        check('P3-2 用例表无「轮次」列', len(round_col) == 0)
        _save_screenshot(drv, 'p32_detail_1265')

        # ---------- P3-3 移除用例（P33，含真实用例） ----------
        _goto(drv, f'/tasks/{t_p33}')
        _wait(drv, By.XPATH, "//button[@aria-label='移除用例']", timeout=20)
        time.sleep(1.0)
        _drain_network(drv)
        _click(drv, By.XPATH, "//button[@aria-label='移除用例']")
        time.sleep(3.0)
        _drain_network(drv)
        creq = _reqs(f'/api/v1/tasks/{t_p33}/cases/', 'DELETE')
        check('P3-3 移除用例发真实 DELETE /tasks/{id}/cases/{caseId}', len(creq) > 0,
              (creq[-1]['url']) if creq else '')
        check('P3-3 移除用例 toast「已移除用例」', _toast_present(drv, '已移除用例'))
        # 等待详情 refetch 完成（invalidate ['tasks'] 前缀），UI 用例行消失
        case_gone_ui = False
        try:
            WebDriverWait(drv, 10).until(
                lambda d: 'ui467_私有用例' not in d.find_element(By.TAG_NAME, 'body').text)
            case_gone_ui = True
        except Exception:
            pass
        check('P3-3 移除用例后用例行消失（UI）', case_gone_ui)
        # 后端权威核对：任务详情已无该用例
        try:
            d = api_json('GET', f'/tasks/{t_p33}')
            case_ids = [c['case_id'] for c in d.get('data', {}).get('cases', [])]
            check('P3-3 后端任务详情已无该用例', TEST_CASE_ID not in case_ids, f'cases={case_ids}')
        except Exception as e:
            check('P3-3 后端任务详情已无该用例', False, str(e)[:100])
        _save_screenshot(drv, 'p33_remove_case')

        # ---------- P3-1 详情控制按钮（pending 态按钮隐藏；无 running 任务可复现） ----------
        _goto(drv, f'/tasks/{t_p31}')
        _wait(drv, By.XPATH, f"//*[contains(.,'接线测试-INT932-P31')]", timeout=20)
        time.sleep(1.0)
        pause_btns = drv.find_elements(By.XPATH, "//button[contains(.,'暂停')]")
        stop_btns = drv.find_elements(By.XPATH, "//button[contains(.,'停止测试')]")
        body = _body_text(drv)
        # 无 running/paused 任务：按钮按状态机隐藏（isTerminal || pending 均不显示）——与缺陷卡口径一致
        check('P3-1 详情按钮状态机（pending 态无 running 任务不显示暂停/停止，代码可证）',
              len(pause_btns) == 0 and len(stop_btns) == 0,
              f'pauseBtn={len(pause_btns)} stopBtn={len(stop_btns)}')
        check('P3-1 详情真实数据渲染（P31 信息卡）', '接线测试-INT932-P31' in body)
        _save_screenshot(drv, 'p31_detail_pending')

        # ---------- P2-2 无效任务 id 单请求落错误态 ----------
        base_count = len(_reqs('/api/v1/tasks/999999'))
        _goto(drv, '/tasks/999999')
        time.sleep(4.0)
        _drain_network(drv)
        n1 = len(_reqs('/api/v1/tasks/999999'))
        time.sleep(4.0)
        _drain_network(drv)
        n2 = len(_reqs('/api/v1/tasks/999999'))
        body = _body_text(drv)
        has_err = '任务详情加载失败' in body
        has_retry = len(drv.find_elements(By.XPATH, "//button[contains(.,'重试')]")) > 0
        check('P2-2 无效 id 仅一次请求（无无限 refetch）',
              (n1 - base_count) <= 1 and (n2 - base_count) == (n1 - base_count),
              f'count={n1 - base_count} after+4s={n2 - base_count}')
        check('P2-2 错误态渲染「任务详情加载失败」+ 重试', has_err and has_retry)
        _save_screenshot(drv, 'p22_detail_error')

    finally:
        drv.quit()

    # ---------- 清理测试数据 ----------
    for tid in (t_p33, t_bb, t_bc, t_p31):
        cleanup_task(tid)
    # 确认无残留
    try:
        left = api_json('GET', '/tasks?search=' + urllib.parse.quote('接线测试-INT932'))
        left_n = len(left.get('data', {}).get('items', []))
    except Exception:
        left_n = -1
    check('测试数据已彻底删除（无 INT932 残留）', left_n == 0, f'left={left_n}')

    print('\n===== INT-932 验收结果 =====')
    for name, ok, detail in RESULTS:
        print(('PASS' if ok else 'FAIL') + ' | ' + name)
    failed = [r for r in RESULTS if not r[1]]
    print(f'TOTAL {len(RESULTS)} / PASS {len(RESULTS) - len(failed)} / FAIL {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
