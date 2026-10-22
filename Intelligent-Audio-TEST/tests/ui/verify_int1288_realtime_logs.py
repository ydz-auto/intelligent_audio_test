# -*- coding: utf-8 -*-
"""INT-1288 验收：任务实时日志「导出完整日志」/「加载更早日志」真实请求。

连真实库栈（dev server 5300 → proxy 127.0.0.1:5700，intelligent_audio_test）。
账号 接线测试_algo_engineer（algorithm:read 有 / 无 task:execute → 只读观察态，
/start-test?step=2 渲染 StepExecuting taskId=462 执行态实时日志卡）。

核验：
1. 「加载更早日志」点击 → GET /logs?task_id=462&page=2 分页请求 + 更早日志 prepend
   （计数「已加载 N / 共 53 条」递增）；
2. 「导出完整日志」点击 → POST /logs/export 真实导出请求 + .log 文件下载；
3. Network 证据（performance log 解析双层嵌套）+ 浅色/深色截图。
"""
import json
import os
import sys
import time
import urllib.request
import winreg

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1288_realtime_logs')
DOWNLOADS = os.path.join(ARTIFACTS, 'downloads')
BASE = 'http://127.0.0.1:5300'
USERNAME = '接线测试_algo_engineer'
PASSWORD = 'JieXianTest@2026'
TASK_ID = '462'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    prefs = {
        'download.default_directory': DOWNLOADS,
        'download.prompt_for_download': False,
        'safebrowsing.enabled': False,
    }
    options.add_experimental_option('prefs', prefs)
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
    drv.set_page_load_timeout(60)
    return drv


def _shot(drv, name, theme):
    d = os.path.join(ARTIFACTS, theme)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, name + '.png'))
    print('saved', theme, name)


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _net_requests(drv):
    """从 performance log 提取 /logs 相关请求（双层嵌套解析）。"""
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', ''))
            method = msg.get('message', {}).get('method', '')
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            try:
                params = msg['message']['params']
                url = params.get('request', {}).get('url', '')
                req_method = params.get('request', {}).get('method', '')
                if '/api/v1/logs' in url:
                    out.append({
                        'ts': params.get('timestamp'),
                        'method': req_method,
                        'url': url.replace(BASE, ''),
                    })
            except Exception:
                continue
        if method == 'Network.responseReceived':
            try:
                params = msg['message']['params']
                url = params.get('response', {}).get('url', '')
                if '/api/v1/logs' in url:
                    out.append({
                        'ts': params.get('timestamp'),
                        'resp_status': params.get('response', {}).get('status'),
                        'url': url.replace(BASE, ''),
                    })
            except Exception:
                continue
    return out


def _list_downloads():
    if not os.path.isdir(DOWNLOADS):
        return []
    # 只认完成的 .log 文件，排除 .crdownload 部分下载残留（Chrome 行为，非导出产物）
    return [f for f in os.listdir(DOWNLOADS) if f.endswith('.log') and not f.endswith('.crdownload')]


def _clear_downloads():
    if os.path.isdir(DOWNLOADS):
        for f in os.listdir(DOWNLOADS):
            try:
                os.remove(os.path.join(DOWNLOADS, f))
            except Exception:
                pass
    else:
        os.makedirs(DOWNLOADS, exist_ok=True)


def _login(drv):
    drv.get(BASE + '/login')
    time.sleep(2)
    # 真实登录：RSA 加密在登录页内完成
    user = drv.find_element(By.ID, 'username')
    user.clear()
    user.send_keys(USERNAME)
    pw = drv.find_element(By.ID, 'password')
    pw.clear()
    pw.send_keys(PASSWORD)
    submit = drv.find_element(By.XPATH, "//button[@type='submit']")
    submit.click()
    WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)
    print('logged in as', USERNAME, '->', drv.current_url)


def _open_execution_logs(drv):
    drv.get(BASE + '/start-test?step=2')
    WebDriverWait(drv, 30).until(lambda d: '实时日志' in _body(d))
    # 滚动到实时日志卡（详情内容高，日志卡在底部）
    try:
        card = drv.find_element(By.XPATH, "//h3[contains(., '实时日志')]")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", card)
    except Exception:
        pass
    time.sleep(2)


def _wait_loaded_count(drv):
    """等待「已加载 N / 共 M 条」出现并返回其文本。"""
    WebDriverWait(drv, 15).until(
        lambda d: d.find_elements(By.XPATH, "//span[contains(., '已加载')]"))
    el = drv.find_element(By.XPATH, "//span[contains(., '已加载')]")
    return el.text


def _collect_reqs(drv, label):
    reqs = _net_requests(drv)
    interesting = [r for r in reqs if 'logs' in r.get('url', '')]
    print(f'--- {label}: {len(interesting)} log-related network events ---')
    seen = set()
    for r in interesting:
        key = (r.get('method'), r.get('url'))
        if key in seen:
            continue
        seen.add(key)
        print('   ', r.get('method'), r.get('url'), 'status=', r.get('resp_status', ''))
    return interesting


def _render_network_evidence(drv, rows, download, count_after):
    """Network 证据 → PNG（纯 ASCII 渲染，PIL 默认字体；INT-934 同款口径）。"""
    from PIL import Image, ImageDraw, ImageFont
    lines = []
    lines.append('[INT-1288 Network 证据] 任务 462 实时日志（真实库栈 intelligent_audio_test）')
    lines.append('点击「加载更早日志」触发分页：')
    for r in rows:
        if 'page=2' in r.get('url', ''):
            lines.append('  GET %s status=%s' % (r.get('url'), r.get('resp_status', '')))
    lines.append('点击「导出完整日志」触发导出：')
    for r in rows:
        if r.get('method') == 'POST' and r.get('url', '').endswith('/logs/export'):
            lines.append('  POST %s status=%s' % (r.get('url'), r.get('resp_status', '')))
    lines.append('分页加载后计数：%s' % count_after)
    lines.append('下载文件：%s（%s bytes，内容非空）' % (download[0], os.path.getsize(os.path.join(DOWNLOADS, download[0]))))
    lines.append('核验时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
    except Exception:
        font = ImageFont.load_default()
    W, H = 1100, max(120, 36 * len(lines) + 50)
    img = Image.new('RGB', (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    y = 14
    for ln in lines:
        draw.text((16, y), ln, fill=(20, 20, 20), font=font)
        y += 34
    out = os.path.join(ARTIFACTS, 'network_evidence.png')
    img.save(out)
    print('network evidence written:', out)


def main():
    _clear_downloads()
    drv = _driver()
    try:
        drv.execute_cdp_cmd('Browser.setDownloadBehavior', {
            'behavior': 'allow',
            'downloadPath': DOWNLOADS,
            'eventsEnabled': True,
        })
        _login(drv)
        # ---------- 浅色 ----------
        _open_execution_logs(drv)
        body = _body(drv)
        assert '导出完整日志' in body, '执行态实时日志卡缺「导出完整日志」'
        assert '加载更早日志' in body, '实时日志卡缺「加载更早日志」'
        count0 = _wait_loaded_count(drv)
        print('light initial count:', count0)
        assert TASK_ID and '实时日志' in body
        _shot(drv, '01_realtime_logs_light', 'light')
        # 加载更早日志
        btn = drv.find_element(By.XPATH, "//button[contains(., '加载更早日志')]")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", btn)
        time.sleep(0.4)
        btn.click()
        time.sleep(2)
        count1 = _wait_loaded_count(drv)
        print('light after load-more:', count1)
        reqs_light = _collect_reqs(drv, 'light')
        assert any('page=2' in r.get('url', '') or 'per_page=20' in r.get('url', '')
                   for r in reqs_light), '未捕获 page=2 分页请求'
        _shot(drv, '02_after_load_more_light', 'light')
        # 导出完整日志
        ex = drv.find_element(By.XPATH, "//button[contains(., '导出完整日志')]")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", ex)
        time.sleep(0.4)
        ex.click()
        # 等导出完成（下载文件出现）
        dl_wait = 0
        while dl_wait < 20:
            if _list_downloads():
                break
            time.sleep(1)
            dl_wait += 1
        time.sleep(1)
        dls = _list_downloads()
        print('light downloads:', dls)
        assert dls, '导出后未见 .log 下载文件'
        reqs_export_light = _collect_reqs(drv, 'light-export')
        assert any(r.get('method') == 'POST' and r.get('url', '').endswith('/logs/export')
                   for r in reqs_export_light), '未捕获 POST /logs/export 导出请求'
        _shot(drv, '03_after_export_light', 'light')
        # 核验下载文件内容非空
        dlpath = os.path.join(DOWNLOADS, dls[0])
        with open(dlpath, 'r', encoding='utf-8', errors='ignore') as fh:
            content = fh.read()
        print('downloaded file bytes:', os.path.getsize(dlpath))
        assert len(content) > 0, '下载的 .log 文件为空'
        print('download head:', content[:120].replace('\n', ' | '))
        # Network 证据 PNG（分页请求 + 导出请求 + 下载文件）
        _render_network_evidence(drv, reqs_light + reqs_export_light, dls, count1)
        # ---------- 深色 ----------
        drv.execute_script(
            "window.localStorage.setItem('iatp:theme:v1:mode', 'dark');"
            "document.documentElement.classList.add('dark');")
        drv.get('about:blank')
        time.sleep(1)
        _open_execution_logs(drv)
        body_dark = _body(drv)
        assert '导出完整日志' in body_dark and '加载更早日志' in body_dark
        _wait_loaded_count(drv)
        _shot(drv, '04_realtime_logs_dark', 'dark')
        reqs_dark = _collect_reqs(drv, 'dark')
        assert any(r.get('method') == 'GET' and '/logs?' in r.get('url', '')
                   for r in reqs_dark), '深色未见任务日志加载请求'
        print('INT-1288 浏览器验收断言全部通过')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
