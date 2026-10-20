# -*- coding: utf-8 -*-
"""INT-1026 /start-test 用例步骤组头「批量修改」九项弹窗接线 浏览器实测。

覆盖（对照缺陷清单 P1-1 + 验收标准）：
  ① 分组视图组头「批量修改」下拉九项逐项点击 → 对应批量弹窗 / 确认框均弹出
     （用例专属参数/播放设备/声压/调整分组/评价维度/噪声/标签生成名称/管理标签/用例参考更新）
  ② 提交真实批量操作（批量设置声压 update_spl）→ POST /api/v1/testcases/batch
     + 列表刷新（GET /testcases）+ 批量 toast，无 mock 残留
  ③ 本页批量浮条（fixed bottom-6 CaseBulkActions）不出现（2026-10-18 口径）
  ④ 浅色 + 深色界面截图 + 关键弹窗交互截图 + Network 证据

用法：python verify_int1026_batch_dialogs.py --base http://localhost:5321
输出：tests/ui/artifacts/int1026/*.png
"""
import argparse
import json
import os
import sys
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1026')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 九项 → 期望弹窗标题（alert-dialog 与 dialog 区分）
NINE_ITEMS = [
    ('用例专属参数', '批量设置用例专属参数', 'dialog'),
    ('播放设备', '批量设置播放设备', 'dialog'),
    ('声压', '批量设置声压级', 'dialog'),
    ('调整分组', '批量调整分组', 'dialog'),
    ('评价维度', '批量设置评估维度', 'dialog'),
    ('噪声', '批量设置噪声', 'dialog'),
    ('标签生成名称', '自动生成名称', 'alert'),
    ('管理标签', '批量管理标签', 'dialog'),
    ('用例参考更新', '刷新参考参数', 'alert'),
]


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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
    """从 performance log 提取请求 method/url/status/body（双层嵌套解析）。"""
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
                    'postData': req.get('postData') or '',
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


def _click_text(drv, text, scope=None, timeout=15):
    """点作用域内（或全页）文本命中元素；等动画就绪避免点击被吞（INT-876 时序）。"""
    def do():
        els = (scope.find_elements(By.XPATH, './/*[normalize-space(text())="%s"]' % text)
               if scope else drv.find_elements(By.XPATH, '//*[normalize-space(text())="%s"]' % text))
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

    deadline = time.time() + timeout
    while time.time() < deadline:
        if do():
            return
        time.sleep(0.5)
    raise AssertionError('click failed: ' + text)


def _dialog_by_title(drv, title):
    """返回可见的 dialog-content（base-ui 关闭动画后旧 content 仍残留 DOM，须过滤可见）。"""
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    for el in drv.find_elements(By.XPATH, xpath):
        if el.is_displayed():
            return el
    raise AssertionError('visible dialog not found: ' + title)


def _alert_dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='alert-dialog-content'][.//*[@data-slot='alert-dialog-title'][contains(., '{title}')]]"
    )
    for el in drv.find_elements(By.XPATH, xpath):
        if el.is_displayed():
            return el
    raise AssertionError('visible alert dialog not found: ' + title)


def _has_bulk_bar(drv):
    return len(drv.find_elements(
        By.XPATH, "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")) > 0


def _close_dialog(drv, kind, title):
    if kind == 'alert':
        dlg = _alert_dialog_by_title(drv, title)
        dlg.find_element(By.XPATH, ".//button[contains(., '取消')]").click()
    else:
        dlg = _dialog_by_title(drv, title)
        dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.6)
    # 关闭动画后可见弹窗应消失（隐藏残留 content 不算）
    wait_for(lambda: not any(e.is_displayed() for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
             and not any(e.is_displayed() for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")),
             12, 'dialog closed: ' + title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5321')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        # 浅色会话：fresh driver 首次直达 /start-test（AUTH_MODE=off 注入 dev_user）
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        drv.get(base + '/start-test')
        time.sleep(1.5)
        drv.get(base + '/start-test')  # refresh 到真实列表
        # 等待分组视图组头「批量修改」按钮出现（真实 GET /groups + /testcases 渲染）
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, "[aria-label$='批量修改']")) > 0,
                 30, 'start-test group cards render')
        time.sleep(1)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start_test_light_page.png'))

        # ③ 批量浮条不出现（2026-10-18 口径：本页不启用批量浮条）
        assert not _has_bulk_bar(drv), '本页不应出现批量浮条'
        print('③ 批量浮条不出现：OK')

        # ============ ① 九项逐项弹窗 ============
        results = []
        for label, title, kind in NINE_ITEMS:
            btn = drv.find_element(By.CSS_SELECTOR, "[aria-label$='批量修改']")
            drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
            time.sleep(0.4)
            btn.click()
            time.sleep(0.7)
            wait_for(lambda l=label: len(drv.find_elements(
                By.XPATH, '//*[normalize-space(text())="%s"]' % l)) > 0, 10, 'dropdown item ' + label)
            _click_text(drv, label)
            # 断言对应弹窗/确认框弹出（只认可见弹窗；base-ui 关闭动画后旧 content 残留 DOM）
            if kind == 'alert':
                wait_for(lambda t=title: any(
                    e.is_displayed() for e in drv.find_elements(
                        By.XPATH, "//div[@data-slot='alert-dialog-content'][.//*[@data-slot='alert-dialog-title'][contains(., '%s')]]" % t)),
                    15, 'alert dialog ' + title)
                # 关键确认框截图（标签生成名称/用例参考更新）
                if label in ('标签生成名称', '用例参考更新'):
                    drv.save_screenshot(os.path.join(ARTIFACTS, 'confirm_%s.png' % label))
            else:
                wait_for(lambda t=title: any(
                    e.is_displayed() for e in drv.find_elements(
                        By.XPATH, f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{t}')]]")),
                    15, 'dialog ' + title)
                if label in ('声压', '评价维度', '管理标签'):
                    drv.save_screenshot(os.path.join(ARTIFACTS, 'dialog_%s.png' % label))
            results.append((label, title, 'OK'))
            _close_dialog(drv, kind, title)
            time.sleep(0.4)

        for label, title, ok in results:
            print('① %s → %s：%s' % (label, title, ok))

        # ============ ② 真实批量操作：声压 update_spl ============
        drv.get_log('performance')  # drain 基线
        btn = drv.find_element(By.CSS_SELECTOR, "[aria-label$='批量修改']")
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
        time.sleep(0.4)
        btn.click()
        time.sleep(0.7)
        wait_for(lambda: len(drv.find_elements(By.XPATH, '//*[normalize-space(text())="声压"]')) > 0,
                 10, 'dropdown item 声压')
        _click_text(drv, '声压')
        wait_for(lambda: any(
            e.is_displayed() for e in drv.find_elements(
                By.XPATH, "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '批量设置声压级')]]")),
            15, 'spl dialog open')
        dlg = _dialog_by_title(drv, '批量设置声压级')
        assert '您勾选了' in dlg.text, '声压弹窗头部缺失：%r' % dlg.text[:200]
        drv.save_screenshot(os.path.join(ARTIFACTS, 'dialog_spl_filled.png'))
        # 填声压级 65 → 确定（React 受控 input 须用原生 value setter 触发 onChange）
        spl_input = dlg.find_element(By.CSS_SELECTOR, "input[type='number']")
        drv.execute_script(
            "const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
            "s.call(arguments[0],'65'); arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            spl_input)
        time.sleep(0.5)
        # 确定钮应解除禁用
        ok_btn = dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]")
        assert not ok_btn.get_attribute('disabled'), '声压确定钮仍禁用（输入未入 React 状态）'
        ok_btn.click()
        # 先等批量 toast（sonner 约 4s 自动消失，须在提交后立即捕获），再收 Network
        wait_for(lambda: '批量操作执行成功' in (drv.find_element(By.TAG_NAME, 'body').text),
                 12, 'batch toast')
        time.sleep(1)
        reqs = collect_requests(drv)
        batch_reqs = count_api_calls(reqs, '/api/v1/testcases/batch', methods=['POST'])
        tc_refresh = count_api_calls(reqs, '/api/v1/testcases?', methods=['GET'])
        print('② batch POST:', [(r['method'], r['url'].split('/api/v1')[1], r['status']) for r in batch_reqs])
        if batch_reqs:
            print('② batch body:', batch_reqs[0]['postData'])
        assert batch_reqs, '未捕获 POST /testcases/batch（真实批量操作缺失）'
        assert batch_reqs[0]['status'] is not None and batch_reqs[0]['status'] < 400, \
            'batch POST 非成功状态：%r' % batch_reqs[0]
        # 无 mock 残留：批量载荷 action 为 update_spl（真实 batch API，非演示）
        assert 'update_spl' in (batch_reqs[0]['postData'] or ''), \
            '批量载荷非真实 update_spl：%r' % (batch_reqs[0]['postData'] or '')[:200]
        time.sleep(0.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'batch_spl_submitted.png'))
        assert not any(e.is_displayed() for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")), '确定后弹窗应关闭'
        assert _has_bulk_bar(drv) is False, '批量操作后本页仍不应出现批量浮条'
        print('② 真实批量操作提交：OK（POST /testcases/batch status=%s；刷新 GET /testcases=%d 次）'
              % (batch_reqs[0]['status'], len(tc_refresh)))

        # ============ ④ Network 证据 ============
        lines = []
        lines.append('P1-1 九项弹窗逐项弹出：')
        for label, title, ok in results:
            lines.append('  %s → %s OK' % (label, title))
        lines.append('P1-1 真实批量操作 POST /testcases/batch:')
        for r in batch_reqs:
            lines.append('  [%s] %s status=%s' % (r['method'], r['url'].split('/api/v1')[1], r['status']))
            if r['postData']:
                lines.append('    body: %s' % r['postData'][:200])
        lines.append('P1-1 列表刷新 GET /testcases: %d calls' % len(tc_refresh))
        lines.append('P1-1 批量浮条不出现：OK')
        lines.append('verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
        net_png = render_text_png('INT-1026 Network Evidence', lines, 'network_evidence.png')
        print('network evidence:', net_png)
        print('\n'.join(lines))

        # ============ 深色界面截图 ============
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        drv.get(base + '/start-test')
        time.sleep(1.5)
        drv.get(base + '/start-test')  # refresh 深色
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, "[aria-label$='批量修改']")) > 0,
                 30, 'dark group cards render')
        time.sleep(1)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start_test_dark_page.png'))
        # 深色弹窗交互一张（评价维度）
        btn = drv.find_element(By.CSS_SELECTOR, "[aria-label$='批量修改']")
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
        time.sleep(0.4)
        btn.click()
        time.sleep(0.7)
        wait_for(lambda: len(drv.find_elements(By.XPATH, '//*[normalize-space(text())="评价维度"]')) > 0,
                 10, 'dark dropdown item')
        _click_text(drv, '评价维度')
        wait_for(lambda: any(
            e.is_displayed() for e in drv.find_elements(
                By.XPATH, "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '批量设置评估维度')]]")),
            15, 'dark dimensions dialog')
        time.sleep(1)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'dialog_dimensions_dark.png'))
        _close_dialog(drv, 'dialog', '批量设置评估维度')
        return 0
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
