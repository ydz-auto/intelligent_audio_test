# -*- coding: utf-8 -*-
"""INT-1561 验收实测（React·日志域）。

缺陷 1（P2）：7 处 base-ui Select 关闭态显示原始 value → 期望显示选项 label。
缺陷 2（P3）：导出成功后弹窗不关闭 → 期望 200 后弹窗关闭。

环境：自建 nginx 容器 iat-react-int1561-verify :15261（交付 diff 构建的 dist，
反代 api_gateway:5000）+ docker 真实库栈网关 :15000（database=intelligent_audio_test）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_VERIFY_BASE', 'http://127.0.0.1:15261')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1561')
THEME_KEY = 'iatp:theme:v1:mode'

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)) if detail else ''))
    return ok


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
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
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(60)
    return drv


def goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.5)


def snap(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    return path


def set_theme(drv, mode):
    drv.execute_script(
        'try { localStorage.setItem(%r, %r) } catch (e) {}' % (THEME_KEY, mode))


def trigger_texts(drv):
    """页面所有 base-ui Select 关闭态文本（按 data-slot=select-trigger）。"""
    return drv.execute_script("""
      return Array.from(document.querySelectorAll('[data-slot="select-trigger"]')).map(el => ({
        aria: el.getAttribute('aria-label'),
        text: (el.innerText || '').trim(),
        id: el.id || null,
        inDialog: !!el.closest('[role="dialog"]'),
      }));
    """)


def find_trigger(drv, aria=None, dialog=False):
    sel = '[data-slot="select-trigger"]'
    items = drv.find_elements(By.CSS_SELECTOR, sel)
    for el in items:
        try:
            if aria is not None and el.get_attribute('aria-label') != aria:
                continue
            in_dialog = drv.execute_script('return !!arguments[0].closest(\'[role="dialog"]\')', el)
            if bool(in_dialog) != dialog:
                continue
            return el
        except Exception:
            continue
    return None


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def choose_option(drv, trigger_el, label):
    """打开 base-ui Select 并点选指定 label 的选项。"""
    js_click(drv, trigger_el)
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, '[role="option"]')) > 0)
    time.sleep(0.4)
    opts = drv.find_elements(By.CSS_SELECTOR, '[role="option"]')
    target = None
    for op in opts:
        if op.text.strip() == label:
            target = op
            break
    if target is None:
        names = [op.text.strip() for op in opts]
        raise AssertionError('未找到选项 %r，实际选项=%r' % (label, names))
    js_click(drv, target)
    time.sleep(0.8)


def page_size_trigger(drv):
    """页脚每页条数 Select（className w-24，无 aria-label；分页在 Portal 里）。"""
    for el in drv.find_elements(By.CSS_SELECTOR, '[data-slot="select-trigger"]'):
        classes = el.get_attribute('class') or ''
        if 'w-24' in classes.split() or 'w-24' in classes:
            return el
    return None


def perf_requests(drv, needle):
    """performance log 双层解包：取命中 needle 的请求 method/url/status。"""
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])
        except Exception:
            continue
        m = msg.get('message', {})
        if m.get('method') != 'Network.responseReceived':
            continue
        p = m.get('params', {})
        resp = p.get('response', {})
        url = resp.get('url', '')
        if needle in url:
            out.append({'url': url, 'status': resp.get('status'),
                        'method': p.get('type'), 'raw_method': m.get('method')})
    return out


def main():
    drv = _driver()
    failures = 0
    try:
        # ── 浅色：关闭态 label ───────────────────────────────
        set_theme(drv, 'light')
        goto(drv, '/logs')
        drv.execute_script('try { "x" } catch(e){}')
        # 等日志列表真实数据
        try:
            WebDriverWait(drv, 40).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
            rows = len(drv.find_elements(By.CSS_SELECTOR, 'tbody tr'))
        except Exception:
            rows = 0
        body = drv.execute_script('return document.body.innerText') or ''
        check('E1 日志列表真实数据（tbody 行 + 共N条统计）',
              rows > 0 and '条日志' in body, 'rows=%s' % rows)

        texts = {t['aria']: t['text'] for t in trigger_texts(drv) if t['aria']}
        expect_closed = {
            '分类': '所有分类',
            '模块': '所有模块',
            '标记筛选': '所有标记',
            '算法类型': '全部算法',
        }
        for aria, want in expect_closed.items():
            got = texts.get(aria)
            failures += 0 if check('A 关闭态 工具栏·%s = %s' % (aria, want), got == want,
                                   '实际=%r' % got) else 1
        ps_el = page_size_trigger(drv)
        ps_text = ps_el.text.strip() if ps_el else None
        failures += 0 if check('A 关闭态 页脚·每页条数 = 20 条/页', ps_text == '20 条/页',
                               '实际=%r' % ps_text) else 1
        snap(drv, 'light_01_logs_page.png')

        # ── 筛选交互：分类选「系统日志」───────────────────────
        drv.get_log('performance')  # 清空历史
        cat = find_trigger(drv, aria='分类')
        choose_option(drv, cat, '系统日志')
        time.sleep(2)
        cat_text = find_trigger(drv, aria='分类').text.strip()
        failures += 0 if check('B 分类选中后触发态 = 系统日志（非原始值 system）',
                               cat_text == '系统日志', '实际=%r' % cat_text) else 1
        reqs = perf_requests(drv, '/api/v1/logs')
        hit = [r for r in reqs if 'category=system' in r['url']]
        failures += 0 if check('B 分类筛选真实请求 category=system',
                               bool(hit) and all(r['status'] == 200 for r in hit),
                               hit[-2:] if hit else reqs[-3:]) else 1
        snap(drv, 'light_02_category_selected.png')

        # 还原分类
        choose_option(drv, find_trigger(drv, aria='分类'), '所有分类')
        time.sleep(1.5)

        # ── 模块 / 标记 / 算法 交互 ──────────────────────────
        choose_option(drv, find_trigger(drv, aria='模块'), 'API模块')
        time.sleep(1.5)
        m_text = find_trigger(drv, aria='模块').text.strip()
        failures += 0 if check('B 模块选中后触发态 = API模块', m_text == 'API模块',
                               '实际=%r' % m_text) else 1
        choose_option(drv, find_trigger(drv, aria='模块'), '所有模块')
        time.sleep(1)

        choose_option(drv, find_trigger(drv, aria='标记筛选'), '黄色标记')
        time.sleep(1.5)
        k_text = find_trigger(drv, aria='标记筛选').text.strip()
        failures += 0 if check('B 标记选中后触发态 = 黄色标记', k_text == '黄色标记',
                               '实际=%r' % k_text) else 1
        choose_option(drv, find_trigger(drv, aria='标记筛选'), '所有标记')
        time.sleep(1)

        # 算法：取选项里的第一个非「全部算法」
        algo_trig = find_trigger(drv, aria='算法类型')
        js_click(drv, algo_trig)
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, '[role="option"]')) > 0)
        time.sleep(0.5)
        algo_opts = [op.text.strip() for op in drv.find_elements(By.CSS_SELECTOR, '[role="option"]')]
        algo_choice = next((o for o in algo_opts if o and o != '全部算法'), None)
        if algo_choice:
            for op in drv.find_elements(By.CSS_SELECTOR, '[role="option"]'):
                if op.text.strip() == algo_choice:
                    js_click(drv, op)
                    break
            time.sleep(1.5)
            a_text = find_trigger(drv, aria='算法类型').text.strip()
            failures += 0 if check('B 算法选中后触发态 = %r（非原始 value）' % algo_choice,
                                   a_text == algo_choice, '实际=%r 选项=%r' % (a_text, algo_opts)) else 1
        else:
            failures += 0 if check('B 算法下拉有真实选项', False, algo_opts) else 1
        choose_option(drv, find_trigger(drv, aria='算法类型'), '全部算法')
        time.sleep(1)

        # ── 每页条数 20 → 50 ────────────────────────────────
        drv.get_log('performance')
        choose_option(drv, page_size_trigger(drv), '50 条/页')
        time.sleep(2)
        ps2 = page_size_trigger(drv).text.strip()
        failures += 0 if check('B 每页条数选中后 = 50 条/页', ps2 == '50 条/页',
                               '实际=%r' % ps2) else 1
        reqs = perf_requests(drv, '/api/v1/logs')
        hit = [r for r in reqs if 'per_page=50' in r['url']]
        failures += 0 if check('B 每页条数真实请求 per_page=50',
                               bool(hit) and all(r['status'] == 200 for r in hit),
                               hit[-2:] if hit else reqs[-3:]) else 1
        choose_option(drv, page_size_trigger(drv), '20 条/页')
        time.sleep(1.5)

        # ── 导出弹窗：格式 label + 导出后关闭 ────────────────
        export_btn = None
        for b in drv.find_elements(By.TAG_NAME, 'button'):
            if b.text.strip() == '导出日志':
                export_btn = b
                break
        check('C 找到「导出日志」按钮', export_btn is not None)
        js_click(drv, export_btn)
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')) > 0)
        time.sleep(0.8)
        fmt = find_trigger(drv, aria=None, dialog=True)
        fmt_text = fmt.text.strip() if fmt else None
        failures += 0 if check('A 导出弹窗·格式关闭态 = 文本', fmt_text == '文本',
                               '实际=%r' % fmt_text) else 1
        snap(drv, 'light_10_export_dialog.png')
        # 切到 JSON
        choose_option(drv, fmt, 'JSON')
        time.sleep(0.8)
        fmt2 = find_trigger(drv, aria=None, dialog=True)
        failures += 0 if check('B 导出格式选中后 = JSON', fmt2.text.strip() == 'JSON',
                               '实际=%r' % (fmt2.text.strip() if fmt2 else None)) else 1
        choose_option(drv, find_trigger(drv, aria=None, dialog=True), '文本')
        time.sleep(0.5)

        # 缺陷 2：点导出 → 200 + 弹窗关闭 + toast
        drv.get_log('performance')
        exp_btn = None
        for b in drv.find_elements(By.TAG_NAME, 'button'):
            if b.text.strip() in ('导出', '导出中…'):
                exp_btn = b
                break
        check('C 找到弹窗「导出」按钮', exp_btn is not None)
        js_click(drv, exp_btn)
        closed = False
        t0 = time.time()
        while time.time() - t0 < 60:
            if not drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
                closed = True
                break
            time.sleep(0.5)
        failures += 0 if check('C 缺陷2 导出成功后弹窗自动关闭', closed,
                               '耗时 %.1fs' % (time.time() - t0)) else 1
        toast_txt = drv.execute_script("""
          return Array.from(document.querySelectorAll('[data-sonner-toast]'))
            .map(e => (e.innerText || '').trim()).join(' | ');
        """)
        failures += 0 if check('C 导出 toast「日志已导出」', '日志已导出' in (toast_txt or ''),
                               toast_txt) else 1
        exp_reqs = perf_requests(drv, '/api/v1/logs/export')
        ok200 = [r for r in exp_reqs if r['status'] == 200]
        failures += 0 if check('C POST /logs/export 真实请求 200', bool(ok200),
                               exp_reqs[-2:]) else 1
        snap(drv, 'light_11_after_export.png')

        # ── 实时配置弹窗：轮询间隔 ───────────────────────────
        sw = None
        for el in drv.find_elements(By.CSS_SELECTOR, '[data-slot="switch"], [role="switch"]'):
            if el.get_attribute('aria-label') == '实时日志开关':
                sw = el
                break
        check('D 找到实时日志开关', sw is not None)
        js_click(drv, sw)
        time.sleep(2.5)
        cfg_btn = None
        for b in drv.find_elements(By.TAG_NAME, 'button'):
            if b.text.strip() == '配置':
                cfg_btn = b
                break
        check('D 实时监控条「配置」按钮出现', cfg_btn is not None)
        js_click(drv, cfg_btn)
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')) > 0)
        time.sleep(0.8)
        interval = find_trigger(drv, aria=None, dialog=True)
        iv_text = interval.text.strip() if interval else None
        failures += 0 if check('A 实时配置·轮询间隔关闭态 = 5s', iv_text == '5s',
                               '实际=%r' % iv_text) else 1
        snap(drv, 'light_21_realtime_config_dialog.png')
        choose_option(drv, interval, '10s')
        time.sleep(0.8)
        iv2 = find_trigger(drv, aria=None, dialog=True)
        failures += 0 if check('B 轮询间隔选中后 = 10s',
                               (iv2.text.strip() if iv2 else None) == '10s',
                               '实际=%r' % (iv2.text.strip() if iv2 else None)) else 1
        # 关闭弹窗（取消/关闭按钮），关实时
        for b in drv.find_elements(By.TAG_NAME, 'button'):
            if b.text.strip() in ('取消', '关闭'):
                js_click(drv, b)
                break
        time.sleep(1)
        sw2 = None
        for el in drv.find_elements(By.CSS_SELECTOR, '[data-slot="switch"], [role="switch"]'):
            if el.get_attribute('aria-label') == '实时日志开关':
                sw2 = el
                break
        if sw2:
            js_click(drv, sw2)
            time.sleep(1.5)

        # ── 深色：关闭态 label ──────────────────────────────
        set_theme(drv, 'dark')
        goto(drv, '/logs')
        try:
            WebDriverWait(drv, 40).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
        except Exception:
            pass
        dtexts = {t['aria']: t['text'] for t in trigger_texts(drv) if t['aria']}
        for aria, want in expect_closed.items():
            failures += 0 if check('D 深色关闭态 工具栏·%s = %s' % (aria, want),
                                   dtexts.get(aria) == want, '实际=%r' % dtexts.get(aria)) else 1
        d_ps = page_size_trigger(drv)
        failures += 0 if check('D 深色关闭态 每页条数 = 20 条/页',
                               d_ps is not None and d_ps.text.strip() == '20 条/页',
                               '实际=%r' % (d_ps.text.strip() if d_ps else None)) else 1
        cat_d = find_trigger(drv, aria='分类')
        choose_option(drv, cat_d, '系统日志')
        time.sleep(1.5)
        failures += 0 if check('D 深色分类选中 = 系统日志',
                               find_trigger(drv, aria='分类').text.strip() == '系统日志',
                               '实际=%r' % find_trigger(drv, aria='分类').text.strip()) else 1
        snap(drv, 'dark_01_logs_page.png')
        # 深色导出弹窗
        for b in drv.find_elements(By.TAG_NAME, 'button'):
            if b.text.strip() == '导出日志':
                js_click(drv, b)
                break
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')) > 0)
        time.sleep(0.8)
        dfmt = find_trigger(drv, aria=None, dialog=True)
        failures += 0 if check('D 深色导出弹窗格式 = 文本',
                               dfmt is not None and dfmt.text.strip() == '文本',
                               '实际=%r' % (dfmt.text.strip() if dfmt else None)) else 1
        snap(drv, 'dark_10_export_dialog.png')

        print('\n===== 汇总 =====')
        total = len(RESULTS)
        failed = [n for n, ok, _ in RESULTS if not ok]
        print('checks=%d pass=%d fail=%d' % (total, total - len(failed), len(failed)))
        for n in failed:
            print('FAILED:', n)
        return 1 if failed else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
