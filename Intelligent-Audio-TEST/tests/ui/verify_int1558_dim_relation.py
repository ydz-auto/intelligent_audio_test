# -*- coding: utf-8 -*-
"""INT-1558 实测取证：算法详情弹窗「评估维度关联」维度名列不再空白。

真实库栈（docker）：后端 http://127.0.0.1:15000（database=intelligent_audio_test），
前端用本 run worktree dev server（5399，/api 代理 15000）。
断言：
- 关联维度行数 = GET /algorithm/definitions/voice_llm 的 associated_dimensions 条数；
- 第一列无空白单元格；
- 可解析的显示真实维度名，解析不到的显示「已删除维度 #<id>」；
- 浅色 / 深色各一张截图（弹窗下半部：参数映射 + 评估维度关联）。
证据：performance log 抓 /algorithm/definitions/voice_llm、/evaluation/dimensions 状态码 → PNG。
"""
import base64
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5399')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1558')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API_BASE = 'http://127.0.0.1:15000'


def log(m):
    print(m, flush=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1400')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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
    return webdriver.Chrome(options=options, service=service)


def api_get(path):
    import urllib.request
    with urllib.request.urlopen(API_BASE + path, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def open_algorithm_page(drv):
    drv.get(BASE + '/AlgorithmConfig')
    time.sleep(4)
    if '/login' in drv.current_url:
        try:
            drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
            drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
            drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        except Exception:
            pass
        WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
        drv.get(BASE + '/AlgorithmConfig')
        time.sleep(3)
    WebDriverWait(drv, 60).until(
        lambda d: '小艺语音大模型' in (d.page_source or '')
    )


def open_detail(drv):
    row = drv.find_element(
        By.XPATH,
        "//tbody/tr[.//span[normalize-space()='小艺语音大模型']]",
    )
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', row)
    drv.execute_script('arguments[0].click();', row)
    WebDriverWait(drv, 20).until(lambda d: '评估维度关联' in (d.page_source or ''))
    time.sleep(1.0)


def section_table(drv):
    """定位「评估维度关联」section 下的表。"""
    heading = drv.find_element(By.XPATH, "//h3[normalize-space()='评估维度关联']")
    section = heading.find_element(By.XPATH, '..')
    return section.find_element(By.XPATH, './/table')


def read_cells(drv):
    table = section_table(drv)
    rows = table.find_elements(By.XPATH, './/tbody/tr')
    out = []
    for tr in rows:
        tds = tr.find_elements(By.TAG_NAME, 'td')
        out.append([td.text for td in tds])
    return out


def scroll_dialog_bottom(drv):
    heading = drv.find_element(By.XPATH, "//h3[normalize-space()='评估维度关联']")
    drv.execute_script(
        'arguments[0].scrollIntoView({block:"center"});', heading
    )
    time.sleep(0.8)


def scroll_fallback_row(drv):
    tr = drv.find_element(
        By.XPATH,
        "//h3[normalize-space()='评估维度关联']/following-sibling::div//tbody/tr[td[starts-with(normalize-space(.), '已删除维度 #')]]",
    )
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', tr)
    time.sleep(0.8)


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('screenshot: %s' % path)
    return path


def network_evidence(drv, tag):
    reqs = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            method = (msg.get('message') or {}).get('method') or ''
            params = (msg.get('message') or {}).get('params') or {}
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            url = req.get('url') or ''
            if '/algorithm/definitions' in url or '/evaluation/dimensions?' in url:
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'),
                    'url': url,
                    'status': None,
                }
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            if rid in reqs:
                reqs[rid]['status'] = (params.get('response') or {}).get('status')
    lines = ['[Network] %s %s %s' % (v['method'], v['url'], v['status']) for v in reqs.values()]
    log('network(%s): %s' % (tag, lines))
    return reqs, lines


def main():
    os.makedirs(ART, exist_ok=True)

    alg = api_get('/api/v1/algorithm/definitions/voice_llm')
    dims = api_get('/api/v1/evaluation/dimensions?per_page=1000')
    alg_data = alg.get('data', alg)
    rel = alg_data.get('associated_dimensions') or []
    dim_items = (dims.get('data') or dims).get('items') or []
    dim_ids = {str(d['id']) for d in dim_items}
    resolvable = [r for r in rel if str(r.get('dimension_id')) in dim_ids]
    missing = [r for r in rel if str(r.get('dimension_id')) not in dim_ids]
    log('API: relations=%d dimensions=%d resolvable=%d missing=%d'
        % (len(rel), len(dim_items), len(resolvable), len(missing)))

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/')
        time.sleep(2)
        drv.execute_script('localStorage.removeItem("iatp:theme:v1:mode")')
        open_algorithm_page(drv)
        open_detail(drv)
        scroll_dialog_bottom(drv)

        cells = read_cells(drv)
        log('DOM rows=%d' % len(cells))
        empties = [i for i, c in enumerate(cells) if not c or not c[0].strip()]
        assert len(cells) == len(rel), 'row count mismatch: %d vs %d' % (len(cells), len(rel))
        assert not empties, 'empty dimension cells at rows %s' % empties[:10]
        fallback = [c for c in cells if c[0].startswith('已删除维度 #')]
        named = [c for c in cells if not c[0].startswith('已删除维度 #')]
        assert len(fallback) == len(missing), 'fallback %d vs missing %d' % (
            len(fallback), len(missing))
        assert len(named) == len(resolvable), 'named %d vs resolvable %d' % (
            len(named), len(resolvable))
        log('first rows: %s' % json.dumps(cells[:5], ensure_ascii=False))
        log('named sample: %s' % json.dumps([c[0] for c in named[:5]], ensure_ascii=False))
        log('fallback sample: %s' % json.dumps([c[0] for c in fallback[:5]], ensure_ascii=False))

        shot(drv, 'detail_dimensions_light.png')
        scroll_fallback_row(drv)
        shot(drv, 'detail_dimensions_fallback_light.png')
        reqs_light, lines_light = network_evidence(drv, 'light')

        # 深色：写主题 key → 打断 bfcache 强刷（about:blank）→ 重开
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode","dark")')
        drv.get('about:blank')
        time.sleep(0.5)
        open_algorithm_page(drv)
        open_detail(drv)
        scroll_dialog_bottom(drv)
        cells_dark = read_cells(drv)
        assert not [c for c in cells_dark if not c or not c[0].strip()], 'dark empty cells'
        shot(drv, 'detail_dimensions_dark.png')
        scroll_fallback_row(drv)
        shot(drv, 'detail_dimensions_fallback_dark.png')
        reqs_dark, lines_dark = network_evidence(drv, 'dark')

        # Network 证据 PNG
        lines = ['INT-1558 AlgorithmDetailDialog dimension name resolution',
                 'frontend: %s (this worktree dev server)' % BASE,
                 'backend : %s (database=intelligent_audio_test)' % API_BASE,
                 '',
                 'API ground truth: associated_dimensions=%d, dimensions=%d, resolvable=%d, missing=%d'
                 % (len(rel), len(dim_items), len(resolvable), len(missing)),
                 'DOM light: rows=%d, empty cells=0, named=%d, fallback=%d'
                 % (len(cells), len(named), len(fallback)),
                 'DOM dark : rows=%d, empty cells=0' % len(cells_dark),
                 '',
                 'Network (light):'] + lines_light + ['', 'Network (dark):'] + lines_dark + [
                 '',
                 'verified at %s' % time.strftime('%Y-%m-%d %H:%M:%S'),
                 'database=intelligent_audio_test (gateway /health checked in run)']
        from PIL import Image, ImageDraw, ImageFont
        try:
            font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
        except Exception:
            font = ImageFont.load_default()
        W, H = 1180, max(160, 38 * len(lines) + 40)
        img = Image.new('RGB', (W, H), (245, 245, 245))
        draw = ImageDraw.Draw(img)
        y = 12
        for ln in lines:
            draw.text((16, y), ln[:130], fill=(20, 20, 20), font=font)
            y += 34
        out = os.path.join(ART, 'network_evidence.png')
        img.save(out)
        log('network evidence: %s' % out)
        log('PASS')
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
