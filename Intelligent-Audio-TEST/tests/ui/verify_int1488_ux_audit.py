# -*- coding: utf-8 -*-
"""INT-1488 前端UX审计（日志域）：界面与视觉复核 + INT-1561 两项修复复核。

对接 docker 15173（iat-react-frontend, wiring/react 构建）+ 15000（真实库 intelligent_audio_test）。
只读：导出=只读下载；清除弹窗只验确认/取消路径，绝不点「清除」。

覆盖：
  A 页面骨架 / 工具栏 Select 关闭态（浅/深）/ 分页关闭态
  B 列表与接口条数一致（keyword / level / 空态 / 行展开）
  C 导出弹窗：关闭态文案、选项数、取消/Esc、**导出成功后弹窗关闭**、下载非空
  D 清除弹窗：默认值、估算数=统计接口、保留已标记、取消/Esc（不执行）
  E 实时配置弹窗：关闭态「5s」、选项 5、改 10s 关闭重开回读、恢复 5s
  F 控制台报错
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
API = 'http://127.0.0.1:15000/api/v1'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1488_ux_audit')
DL = os.path.join(ART, 'dl')
os.makedirs(DL, exist_ok=True)

R = {'steps': [], 'shots': [], 'net': [], 'console': [], 'errors': []}


def log(step, **kw):
    row = {'step': step}
    row.update(kw)
    R['steps'].append(row)
    print('[' + step + '] ' + json.dumps(kw, ensure_ascii=False)[:900], flush=True)


def make_driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-dev-shm-usage')
    o.add_argument('--lang=zh-CN')
    o.page_load_strategy = 'eager'
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    prefs = {
        'download.default_directory': DL.replace('\\', '/'),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
    }
    o.add_experimental_option('prefs', prefs)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(150)
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def txt(d, el):
    return (d.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    R['shots'].append(name)
    print('SHOT ' + p, flush=True)
    return p


def body_text(d):
    return d.find_element(By.TAG_NAME, 'body').text


def api_get(d, path):
    try:
        out = d.execute_async_script(
            "const cb = arguments[arguments.length-1];"
            "const t = localStorage.getItem('iatp:auth:token:v1');"
            "fetch('" + API + "' + arguments[0], {headers: t ? {Authorization: 'Bearer ' + t} : {}})"
            ".then(r => r.text().then(x => cb({status: r.status, body: x})))"
            ".catch(e => cb({status: -1, error: String(e)}));",
            path,
        )
        return out
    except Exception as e:
        return {'status': -1, 'error': str(e)}


def api_json(d, path, tries=3):
    for i in range(tries):
        r = api_get(d, path)
        if r.get('status') == 200:
            try:
                o = json.loads(r['body'])
            except Exception:
                pass
            else:
                if isinstance(o, dict) and 'data' in o:
                    o = o['data']
                return o
        time.sleep(5)
    return {'_status': r.get('status'), '_err': r.get('error')}


def net_poll(d):
    """读 performance log，返回 {url: {method,status}} 列表。"""
    rows = []
    try:
        for e in d.get_log('performance'):
            try:
                m = json.loads(e['message']).get('message', {})
            except Exception:
                continue
            met = m.get('method')
            if met == 'Network.responseReceived':
                p = m['params']
                url = p['response']['url']
                if '/api/v1/' in url:
                    rows.append({'url': url, 'status': p['response']['status'], 'type': p.get('type')})
    except Exception as e:
        R['errors'].append('perf:' + str(e))
    return rows


def console_msgs(d):
    try:
        return [e for e in d.get_log('browser') if e.get('level') in ('SEVERE', 'WARNING')]
    except Exception:
        return []


def set_input(d, el, value):
    js_click(d, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)


def sel_text(d, label):
    els = d.find_elements(By.CSS_SELECTOR, "[aria-label='" + label + "']")
    for e in els:
        if e.is_displayed():
            return txt(d, e)
    return None


def open_select(d, label):
    els = [e for e in d.find_elements(By.CSS_SELECTOR, "[aria-label='" + label + "']") if e.is_displayed()]
    js_click(d, els[0])
    time.sleep(0.6)
    opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
    return opts


def choose_option(d, opts, label_text):
    for o in opts:
        if txt(d, o) == label_text:
            js_click(d, o)
            time.sleep(0.5)
            return True
    js_click(d, d.find_element(By.TAG_NAME, 'body'))
    return False


def footer_total(d):
    for e in d.find_elements(By.XPATH, "//*[contains(text(),'条日志')]"):
        if e.is_displayed():
            return txt(d, e)
    return None


def wait_rows(d, timeout=60):
    WebDriverWait(d, timeout).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)


def row_count(d):
    return len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))


def ensure_loaded(d, timeout=240):
    """等列表出数；失败态点重试，长时间 0 行则整页重载（网关抖动兜底）。"""
    t0 = time.time()
    reloaded = False
    while time.time() - t0 < timeout:
        if row_count(d) > 0:
            return True
        body = body_text(d)
        if '日志列表加载失败' in body:
            click_button(d, '重试')
            time.sleep(5)
            continue
        if (time.time() - t0 > 45) and not reloaded:
            d.get(BASE + '/logs')
            reloaded = True
            time.sleep(8)
            continue
        time.sleep(5)
    return row_count(d) > 0


def login(d):
    d.get(BASE + '/login')
    time.sleep(2)
    # AUTH_MODE=off 首载可能先跳 dashboard，兜底重载一次 /login 再等表单
    if '/login' not in d.current_url:
        d.get(BASE + '/login')
        time.sleep(2)
    WebDriverWait(d, 45).until(lambda x: x.find_elements(By.ID, 'username'))
    set_input(d, d.find_element(By.ID, 'username'), '接线测试_admin')
    set_input(d, d.find_element(By.ID, 'password'), 'JieXianTest@2026')
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(5)
    tok = d.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
    R['token_ok'] = bool(tok)
    R['login_url_after'] = d.current_url
    d.get(BASE + '/logs')
    ensure_loaded(d)
    time.sleep(2)
    return bool(tok)


def dialog(name, d, timeout=12):
    WebDriverWait(d, timeout).until(
        lambda x: any(name in (e.text or '') for e in x.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed())
    )
    return [e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()][-1]


def dialog_open(name, d):
    return any(name in (e.text or '') for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed())


def click_button(d, text, root=None):
    root = root or d
    for b in root.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == text and b.is_displayed():
            js_click(d, b)
            return True
    return False


def main():
    d = make_driver()
    try:
        # ---------- 环境三查（run 开始） ----------
        ok = login(d)
        R['login'] = ok
        if not ok:
            raise SystemExit('login failed')

        # 环境记录（页面内 fetch 后端 /health 不带前缀）
        health = d.execute_async_script(
            "const cb=arguments[arguments.length-1];"
            "fetch('http://127.0.0.1:15000/health').then(r=>r.text()).then(t=>cb(t)).catch(e=>cb('ERR '+e));")
        R['health'] = health

        # ---------- A 页面骨架 / 工具栏关闭态（浅色） ----------
        log('A_page_light', rows=row_count(d), footer=footer_total(d),
            lib=body_text(d)[:0] or 'ok')
        shot(d, 'light_01_logs_page')
        closed = {k: sel_text(d, k) for k in ('分类', '模块', '标记筛选', '算法类型')}
        R['toolbar_closed_light'] = closed
        log('A_toolbar_closed', **closed)

        # 分页每页条数关闭态（footer 内 button 文案含 条/页）
        pg = [b for b in d.find_elements(By.TAG_NAME, 'button') if '条/页' in (b.text or '') and b.is_displayed()]
        R['page_size_closed'] = (pg[0].text or '').strip() if pg else None
        log('A_page_size_closed', text=R['page_size_closed'])

        # 选项数：分类/模块/标记/算法
        for label in ('分类', '模块', '标记筛选', '算法类型'):
            opts = open_select(d, label)
            texts = [txt(d, o) for o in opts]
            R.setdefault('option_counts', {})[label] = len(texts)
            R.setdefault('option_texts', {})[label] = texts
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        alg = api_json(d, '/algorithm/options')
        try:
            alg_n = len(alg if isinstance(alg, list) else alg.get('items') or alg.get('options') or [])
        except Exception:
            alg_n = 'n/a'
        R['algorithm_api_count'] = alg_n
        log('A_options', counts=R.get('option_counts'), algorithm_api=alg_n)

        # 分页选项 4 档
        if pg:
            js_click(d, pg[0])
            time.sleep(0.6)
            ps = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
            R['page_size_options'] = [txt(d, o) for o in ps]
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        log('A_page_size_options', opts=R.get('page_size_options'))

        # ---------- B 列表 vs 接口 ----------
        base = api_json(d, '/logs?page=1&per_page=20')
        base_total = base.get('total')
        base_n = len(base.get('items') or [])
        R['list_api'] = {'total': base_total, 'items': base_n}
        footer0 = footer_total(d)
        R['list_footer'] = footer0
        log('B_list_match', api_total=base_total, api_items=base_n, ui_rows=row_count(d), footer=footer0)

        # keyword 过滤
        search = [e for e in d.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索日志内容']") if e.is_displayed()][0]
        set_input(d, search, 'AUTH_LOGIN')
        time.sleep(3.5)
        kw = api_json(d, '/logs?page=1&per_page=20&keyword=AUTH_LOGIN')
        R['keyword'] = {'api_total': kw.get('total'), 'ui_footer': footer_total(d), 'ui_rows': row_count(d)}
        log('B_keyword', **R['keyword'])
        shot(d, 'light_02_keyword_filter')

        # 空态
        set_input(d, search, 'INT1488_NO_SUCH_LOG_XYZ')
        time.sleep(3.5)
        R['empty_state'] = {'ui_footer': footer_total(d), 'rows': row_count(d), 'has_text': '未找到匹配日志' in body_text(d)}
        log('B_empty', **R['empty_state'])
        shot(d, 'light_03_empty_state')

        # 清除过滤器
        okr = click_button(d, '清除过滤器')
        time.sleep(3)
        R['reset'] = {'clicked': okr, 'keyword_input': search.get_attribute('value'), 'rows': row_count(d)}
        log('B_reset', **R['reset'])

        # 级别只留 ERROR：关掉 DEBUG/INFO/WARNING/CRITICAL 四个 chip
        for lv_name in ('DEBUG', 'INFO', 'WARNING', 'CRITICAL'):
            for b in d.find_elements(By.XPATH, "//button[@aria-pressed]"):
                if (b.text or '').startswith(lv_name) and b.is_displayed():
                    js_click(d, b)
                    break
            time.sleep(0.8)
        time.sleep(3)
        lv = api_json(d, '/logs?page=1&per_page=20&level=ERROR')
        R['level_error'] = {'api_total': lv.get('total'), 'ui_footer': footer_total(d), 'ui_rows': row_count(d),
                            'levels_rows': sorted({(r.text or '').split('\n')[1] if len((r.text or '').split('\n')) > 1 else '' for r in d.find_elements(By.CSS_SELECTOR, 'table tbody tr')})[:8]}
        log('B_level_error', **R['level_error'])
        shot(d, 'light_04_level_error')

        # 行详情展开
        rows = d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        if rows:
            for b in rows[0].find_elements(By.TAG_NAME, 'button'):
                js_click(d, b)
                break
            time.sleep(1.2)
        R['row_detail'] = '详细信息' in body_text(d) or '上下文信息' in body_text(d)
        log('B_row_detail', ok=R['row_detail'])
        shot(d, 'light_05_row_detail')

        # ---------- C 导出弹窗 ----------
        export_btn = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '导出日志' and b.is_displayed()]
        js_click(d, export_btn[0])
        dlg = dialog('导出日志', d)
        time.sleep(0.8)
        shot(d, 'light_06_export_dialog')
        fmt_trig = [e for e in dlg.find_elements(By.CSS_SELECTOR, 'button') if e.get_attribute('id') == 'log-export-format']
        R['export_format_closed'] = txt(d, fmt_trig[0]) if fmt_trig else None
        if fmt_trig:
            js_click(d, fmt_trig[0])
            time.sleep(0.6)
            opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
            R['export_format_options'] = [txt(d, o) for o in opts]
            choose_option(d, opts, 'JSON')
        R['export_format_after_pick'] = txt(d, fmt_trig[0]) if fmt_trig else None
        log('C_export_format', closed=R['export_format_closed'], opts=R.get('export_format_options'),
            after=R['export_format_after_pick'])

        # 小结果集真实导出：level=ERROR 已是当前筛选
        before = set(os.listdir(DL))
        click_button(d, '导出', root=dlg)
        time.sleep(1)
        shot(d, 'light_07_export_pending')
        time.sleep(8)
        after = set(os.listdir(DL)) - before
        files = []
        for f in after:
            p = os.path.join(DL, f)
            files.append({'name': f, 'size': os.path.getsize(p) if os.path.isfile(p) else None})
        R['export_download'] = files
        R['export_dialog_closed_after_success'] = not dialog_open('导出日志', d)
        R['export_toast'] = '日志已导出' in body_text(d)
        log('C_export_success', files=files, closed=R['export_dialog_closed_after_success'], toast=R['export_toast'])
        shot(d, 'light_08_export_closed')

        # 取消路径：重开 → 取消 / Esc
        cancel_paths = {}
        js_click(d, export_btn[0])
        dialog('导出日志', d)
        time.sleep(0.6)
        click_button(d, '取消')
        time.sleep(0.8)
        cancel_paths['cancel'] = not dialog_open('导出日志', d)
        js_click(d, export_btn[0])
        dialog('导出日志', d)
        time.sleep(0.6)
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        cancel_paths['esc'] = not dialog_open('导出日志', d)
        # 重开看格式残留
        js_click(d, export_btn[0])
        dlg = dialog('导出日志', d)
        time.sleep(0.6)
        t2 = [e for e in dlg.find_elements(By.CSS_SELECTOR, 'button') if e.get_attribute('id') == 'log-export-format']
        R['export_format_on_reopen'] = txt(d, t2[0]) if t2 else None
        R['export_cancel_paths'] = cancel_paths
        log('C_export_cancel', **cancel_paths, reopen_format=R['export_format_on_reopen'])
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)

        # ---------- D 清除弹窗（不执行） ----------
        clr = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '清除日志' and b.is_displayed()]
        js_click(d, clr[0])
        dlgc = dialog('清除日志', d)
        time.sleep(0.8)
        shot(d, 'light_09_clear_dialog')
        stats = api_json(d, '/logs/stats?page=1&per_page=20&level=ERROR')
        stats_all = api_json(d, '/logs/stats')
        ctext = dlgc.text
        import re as _re
        nums = _re.findall(r'([\d,]+)\s*条日志', ctext)
        R['clear_dialog'] = {
            'text': ctext[:400],
            'stats_filtered_total': (stats or {}).get('total'),
            'stats_all_total': (stats_all or {}).get('total'),
            'shown_number': nums[0] if nums else None,
            'has_count': str((stats or {}).get('total')) in ctext.replace(',', ''),
            'keep_marked_on': '保留已标记日志不受影响' in ctext,
        }
        log('D_clear_default', **R['clear_dialog'])
        # 关保留已标记 → 文案变化
        sw = [e for e in dlgc.find_elements(By.CSS_SELECTOR, "[role='switch']") if e.is_displayed()]
        if sw:
            js_click(d, sw[0])
            time.sleep(0.8)
        R['clear_keep_marked_off'] = '含已标记日志' in dlgc.text
        log('D_clear_keep_marked', off_text=R['clear_keep_marked_off'])
        # 取消
        click_button(d, '取消', root=dlgc)
        time.sleep(0.8)
        R['clear_cancel'] = not dialog_open('清除日志', d)
        # Esc
        js_click(d, clr[0])
        dialog('清除日志', d)
        time.sleep(0.6)
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        R['clear_esc'] = not dialog_open('清除日志', d)
        # 重开 → 默认值恢复
        js_click(d, clr[0])
        dlgc = dialog('清除日志', d)
        time.sleep(0.6)
        R['clear_reopen'] = {'keep_marked_on': '保留已标记日志不受影响' in dlgc.text,
                             'time_empty': (dlgc.find_element(By.ID, 'log-clear-before').get_attribute('value') or '') == ''}
        log('D_clear_close', cancel=R['clear_cancel'], esc=R['clear_esc'], reopen=R['clear_reopen'])
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)

        # ---------- E 实时配置弹窗 ----------
        rsw = [e for e in d.find_elements(By.CSS_SELECTOR, "[aria-label='实时日志开关']") if e.is_displayed()]
        if rsw:
            js_click(d, rsw[0])
            time.sleep(3)
        R['realtime_bar'] = '实时监控中' in body_text(d)
        cfg = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '配置' and b.is_displayed()]
        if cfg:
            js_click(d, cfg[0])
            dlg2 = dialog('实时监控配置', d)
            time.sleep(0.8)
            shot(d, 'light_10_realtime_config')
            pi = [e for e in dlg2.find_elements(By.CSS_SELECTOR, 'button') if e.get_attribute('id') == 'realtime-poll-interval']
            R['poll_closed'] = txt(d, pi[0]) if pi else None
            if pi:
                js_click(d, pi[0])
                time.sleep(0.6)
                opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
                R['poll_options'] = [txt(d, o) for o in opts]
                choose_option(d, opts, '10s')
                R['poll_after_pick'] = txt(d, pi[0])
            click_button(d, '完成', root=dlg2)
            time.sleep(0.8)
            # 重开回读
            cfg = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '配置' and b.is_displayed()]
            js_click(d, cfg[0])
            dlg2 = dialog('实时监控配置', d)
            time.sleep(0.8)
            pi2 = [e for e in dlg2.find_elements(By.CSS_SELECTOR, 'button') if e.get_attribute('id') == 'realtime-poll-interval']
            R['poll_reopen'] = txt(d, pi2[0]) if pi2 else None
            shot(d, 'light_11_realtime_config_reopen')
            # 恢复 5s
            js_click(d, pi2[0])
            time.sleep(0.6)
            opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
            choose_option(d, opts, '5s')
            R['poll_restored'] = txt(d, pi2[0])
            click_button(d, '完成', root=dlg2)
            time.sleep(0.8)
            log('E_realtime_config', closed=R['poll_closed'], opts=R.get('poll_options'),
                after=R.get('poll_after_pick'), reopen=R['poll_reopen'], restored=R['poll_restored'])
        else:
            log('E_realtime_config', error='config button not found')

        # ---------- F Network / 控制台 ----------
        net = net_poll(d)
        R['net'] = [n for n in net if any(k in n['url'] for k in ('/logs', '/algorithm/options'))][:40]
        R['console'] = console_msgs(d)
        log('F_net', requests=[{'url': n['url'][:110], 'status': n['status']} for n in R['net'][:20]])
        log('F_console', count=len(R['console']), sample=[c['message'][:200] for c in R['console'][:5]])

        # ---------- G 深色 ----------
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.get(BASE + '/logs')
        ensure_loaded(d)
        time.sleep(2.5)
        cls = d.execute_script('return document.documentElement.className')
        R['dark_class'] = cls
        shot(d, 'dark_01_logs_page')
        R['toolbar_closed_dark'] = {k: sel_text(d, k) for k in ('分类', '模块', '标记筛选', '算法类型')}
        log('G_dark_toolbar', html=cls, **R['toolbar_closed_dark'])

        # 深色三弹窗
        export_btn = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '导出日志' and b.is_displayed()]
        js_click(d, export_btn[0])
        dlg = dialog('导出日志', d)
        time.sleep(0.8)
        f = [e for e in dlg.find_elements(By.CSS_SELECTOR, 'button') if e.get_attribute('id') == 'log-export-format']
        R['export_format_closed_dark'] = txt(d, f[0]) if f else None
        shot(d, 'dark_02_export_dialog')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)

        clr = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '清除日志' and b.is_displayed()]
        js_click(d, clr[0])
        dialog('清除日志', d)
        time.sleep(0.8)
        shot(d, 'dark_03_clear_dialog')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)

        rsw = [e for e in d.find_elements(By.CSS_SELECTOR, "[aria-label='实时日志开关']") if e.is_displayed()]
        if rsw:
            js_click(d, rsw[0])
            time.sleep(3)
        cfg = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '配置' and b.is_displayed()]
        if cfg:
            js_click(d, cfg[0])
            dlg2 = dialog('实时监控配置', d)
            time.sleep(0.8)
            pi = [e for e in dlg2.find_elements(By.CSS_SELECTOR, 'button') if e.get_attribute('id') == 'realtime-poll-interval']
            R['poll_closed_dark'] = txt(d, pi[0]) if pi else None
            shot(d, 'dark_04_realtime_config')
            click_button(d, '完成', root=dlg2)
            time.sleep(0.6)
        log('G_dark_dialogs', export_format=R.get('export_format_closed_dark'), poll=R.get('poll_closed_dark'))

        # 环境三查（交付前）
        R['health_end'] = d.execute_async_script(
            "const cb=arguments[arguments.length-1];"
            "fetch('http://127.0.0.1:15000/health').then(r=>r.text()).then(t=>cb(t)).catch(e=>cb('ERR '+e));")
        R['stats_end'] = api_json(d, '/logs/stats').get('total')
        log('H_env_end', health=R['health_end'], stats=R['stats_end'])
    except Exception as e:
        R['errors'].append('fatal: ' + repr(e))
        try:
            shot(d, 'error_state')
        except Exception:
            pass
    finally:
        try:
            d.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as fp:
            json.dump(R, fp, ensure_ascii=False, indent=2, default=str)
        print('RESULT_WRITTEN ' + os.path.join(ART, 'result.json'), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
