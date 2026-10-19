# -*- coding: utf-8 -*-
"""INT-967 任务侧缺陷修复浏览器实测（批量发布 / 重新生成报告 / 查看报告）。

覆盖：
  P1-1 批量发布：勾选 ≥2 个可发布任务 → 发布 → 确认 → 逐任务 POST /published-tasks + 聚合 toast
  P2-1 查看报告：有报告任务行菜单「查看报告」→ 跳 /report/:id
  P1-2 重新生成报告：有旧报告 → generate-task 定位 → 覆盖确认弹窗 → 查看旧报告跳旧报告；
                       确认重新生成 → POST /reports/{id}/regenerate + loading toast

用法：python verify_int967.py --base http://localhost:5315
输出：tests/ui/artifacts/int967/*.png（浅色 + 深色 + Network 证据）
"""
import argparse
import base64
import json
import os
import sys
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int967')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

TASK_WITH_REPORT = 'INT314SMOKE_70ed974e_任务'  # task 1257, report 65
PUBLISHABLE_A = 'INT314SMOKE_a7104c3a_任务'       # task 1265 stopped
PUBLISHABLE_B = 'INT314SMOKE_70ed974e_任务'       # task 1257 completed（1258 pending 无用例，后端拒发）


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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
    return webdriver.Chrome(options=options, service=service)


def collect_requests(drv):
    """从 performance log 提取请求 method/url/status（双层嵌套解析）。"""
    reqs = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                url = req.get('url') or ''
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'),
                    'url': url,
                    'status': None,
                }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
    except Exception:
        pass
    return [v for k, v in reqs.items()]


def count_api_calls(reqs, path, methods=None):
    matches = []
    for r in reqs:
        if path in r.get('url', ''):
            if methods and r.get('method') not in methods:
                continue
            matches.append(r)
    return matches


def render_text_png(title, lines, filename):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
    except Exception:
        font = ImageFont.load_default()
    text = '\n'.join([title] + lines)
    W, H = 1100, max(120, 40 * (len(text.split('\n')) + 1) + 40)
    img = Image.new('RGB', (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    y = 12
    for ln in text.split('\n'):
        draw.text((16, y), ln, fill=(20, 20, 20), font=font)
        y += 36
    out = os.path.join(ARTIFACTS, filename)
    img.save(out)
    return out


def wait_for(cond, timeout=25, desc='condition'):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError('timeout waiting for %s' % desc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5315')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        # 浅色会话：清主题 → 直达 /tasks/daily（AUTH_MODE=off）
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        drv.get(base + '/tasks/daily')
        time.sleep(1)
        drv.get(base + '/tasks/daily')  # refresh 到真实列表
        wait_for(lambda: 'INT314SMOKE_70ed974e_任务' in (drv.page_source or ''), 30, 'task list render')

        # ============ P2-1 查看报告 → 跳 /report/65 ============
        drv.execute_script('window.__t0 = Date.now()')
        drv.get_log('performance')  # drain 基线
        row = _row_containing(drv, TASK_WITH_REPORT)
        _click_row_menu(drv, row, '查看报告')
        wait_for(lambda: '/report/65' in (drv.current_url or ''), 20, 'navigate /report/65')
        wait_for(lambda: '报告' in (drv.page_source or ''), 15, 'report page render')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p2_1_report_nav.png'))
        reqs = collect_requests(drv)
        rep_nav = count_api_calls(reqs, '/api/v1/reports/65')
        print('P2-1 查看报告 URL:', drv.current_url)
        print('P2-1 requests:', [(r['method'], r['url'], r['status']) for r in rep_nav])

        # ============ 回任务列表，P1-2 重新生成报告（有旧报告） ============
        drv.get(base + '/tasks/daily')
        wait_for(lambda: 'INT314SMOKE_70ed974e_任务' in (drv.page_source or ''), 30, 'back to task list')
        drv.get_log('performance')
        row = _row_containing(drv, TASK_WITH_REPORT)
        _click_row_menu(drv, row, '重新生成报告')
        # 定位请求 + 覆盖确认弹窗
        wait_for(lambda: '将删除当前报告并重新生成' in (drv.page_source or ''), 25, 'regen confirm dialog')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1_2_regen_confirm.png'))
        reqs = collect_requests(drv)
        locate_reqs = count_api_calls(reqs, '/api/v1/reports/generate-task', methods=['POST'])
        print('P1-2 locate generate-task:', [(r['method'], r['url'], r['status']) for r in locate_reqs])
        # 点「查看旧报告」→ 跳旧报告（Vue 基线 cancelText 语义）
        _click_text(drv, '查看旧报告')
        wait_for(lambda: '/report/65' in (drv.current_url or ''), 20, 'cancel -> /report/65')
        print('P1-2 查看旧报告 URL:', drv.current_url)

        # 再回列表，确认「重新生成」→ POST regenerate + loading toast（不等待 SSE 完成/超时）
        drv.get(base + '/tasks/daily')
        wait_for(lambda: 'INT314SMOKE_70ed974e_任务' in (drv.page_source or ''), 30, 'back to task list')
        drv.get_log('performance')
        row = _row_containing(drv, TASK_WITH_REPORT)
        _click_row_menu(drv, row, '重新生成报告')
        wait_for(lambda: '将删除当前报告并重新生成' in (drv.page_source or ''), 25, 'regen confirm dialog 2')
        _click_text(drv, '重新生成')
        # 等 POST 触发（get_log 是 drain 语义：等待后一次性收集，不再二次读取）
        time.sleep(6)
        reqs = collect_requests(drv)
        regen_reqs = count_api_calls(reqs, '/reports/65/regenerate', methods=['POST'])
        print('P1-2 regenerate POST:', [(r['method'], r['url'], r['status']) for r in regen_reqs])
        if not regen_reqs:
            # 兜底：再多等一轮收集
            time.sleep(4)
            reqs = collect_requests(drv)
            regen_reqs = count_api_calls(reqs, '/reports/65/regenerate', methods=['POST'])
            print('P1-2 regenerate POST (retry):', [(r['method'], r['url'], r['status']) for r in regen_reqs])
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1_2_regen_loading.png'))

        # ============ 深色截图（任务列表含批量浮条） ============
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        drv.get(base + '/tasks/daily')
        wait_for(lambda: 'INT314SMOKE_70ed974e_任务' in (drv.page_source or ''), 30, 'dark task list')
        time.sleep(1)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'tasks_daily_dark.png'))

        # ============ P1-1 批量发布 ============
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        drv.get(base + '/tasks/daily')
        wait_for(lambda: 'INT314SMOKE_a7104c3a_任务' in (drv.page_source or ''), 30, 'publishable list')
        drv.get_log('performance')
        _check_task(drv, PUBLISHABLE_A)
        _check_task(drv, PUBLISHABLE_B)
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1_1_selected.png'))
        _click_text(drv, '发布', ignore_extra=True)
        wait_for(lambda: '将为选中的 2 个任务发布' in (drv.page_source or ''), 15, 'batch publish confirm')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1_1_batch_confirm.png'))
        # 点确认弹窗内的「发布」（浮条按钮同名，须限定 alertdialog 作用域）
        _click_in_dialog(drv, '发布')
        wait_for(lambda: '批量发布完成：成功 2 个' in (drv.page_source or ''), 20, 'batch publish toast')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1_1_batch_toast.png'))
        reqs = collect_requests(drv)
        pub_reqs = count_api_calls(reqs, '/api/v1/published-tasks', methods=['POST'])
        print('P1-1 publish POSTs:', [(r['method'], r['url'], r['status']) for r in pub_reqs])
        assert len(pub_reqs) >= 2, 'expect >=2 POST /published-tasks, got %d' % len(pub_reqs)

        # ============ Network 证据文本图 ============
        lines = []
        lines.append('P1-1 batch publish POST /published-tasks: %d calls' % len(pub_reqs))
        for r in pub_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P1-2 regen locate POST /reports/generate-task: %d calls' % len(locate_reqs))
        for r in locate_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P1-2 regen POST /reports/65/regenerate: %d calls' % len(regen_reqs))
        for r in regen_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('P2-1 view report GET /reports/65: %d calls' % len(rep_nav))
        for r in rep_nav:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
        lines.append('verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
        net_png = render_text_png('INT-967 Network Evidence', lines, 'network_evidence.png')
        print('network evidence:', net_png)
        print('\n'.join(lines))
        return 0
    finally:
        drv.quit()


def _row_containing(drv, text):
    wait_for(lambda: text in (drv.page_source or ''), 20, 'row %s' % text)
    script = """
    const rows = document.querySelectorAll('tbody tr');
    for (const r of rows) {
      if (r.textContent && r.textContent.indexOf(arguments[0]) !== -1) return r;
    }
    return null;
    """
    row = drv.execute_script(script, text)
    if not row:
        raise AssertionError('row not found: ' + text)
    return row


def _click_row_menu(drv, row, label):
    """点行末「⋯」下拉菜单，再点目标项。"""
    btn = row.find_element(By.CSS_SELECTOR, '[aria-label="任务操作"]')
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
    time.sleep(0.3)
    btn.click()
    time.sleep(0.8)
    wait_for(lambda: label in (drv.page_source or ''), 10, 'menu item %s' % label)
    _click_text(drv, label)


def _click_text(drv, text, ignore_extra=False):
    def do():
        els = drv.find_elements(By.XPATH, '//*[normalize-space(text())="%s"]' % text)
        for el in els:
            try:
                if el.is_displayed():
                    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                    time.sleep(0.4)  # 等开合动画就绪，避免点击被吞（INT-876 时序）
                    el.click()
                    return True
            except Exception:
                continue
        return False

    if ignore_extra:
        deadline = time.time() + 15
        while time.time() < deadline:
            if do():
                return
            time.sleep(0.5)
        return
    if not wait_for(do, 15, 'click ' + text):
        raise AssertionError('click failed: ' + text)


def _click_in_dialog(drv, text):
    """点击 AlertDialog 作用域内的按钮（避免命中同名的浮条/菜单项）。"""
    def do():
        dialogs = drv.find_elements(By.CSS_SELECTOR, '[data-slot="alert-dialog-content"]')
        for d in dialogs:
            if not d.is_displayed():
                continue
            els = d.find_elements(By.XPATH, './/*[normalize-space(text())="%s"]' % text)
            for el in els:
                try:
                    if el.is_displayed():
                        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                        time.sleep(0.4)
                        el.click()
                        return True
                except Exception:
                    continue
        return False

    if not wait_for(do, 15, 'click in dialog ' + text):
        raise AssertionError('click in dialog failed: ' + text)


def _check_task(drv, name):
    """勾选指定任务行（base-ui Checkbox 是 button[data-slot=checkbox]，原生 input 隐藏不可点）。"""
    row = _row_containing(drv, name)
    cb = row.find_element(By.CSS_SELECTOR, '[data-slot="checkbox"]')
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', cb)
    time.sleep(0.3)
    cb.click()
    time.sleep(0.4)


if __name__ == '__main__':
    sys.exit(main())
