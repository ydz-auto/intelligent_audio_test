# -*- coding: utf-8 -*-
"""INT-2089 验收：报告·具体用例「结果对比」叶表转置 + V9.7.10 全块（浏览器实测，docker 真实库栈）。

被测前端：本 worktree `pnpm dev`（API_PROXY_TARGET=http://localhost:15000，端口 5273）。
后端：docker 真实库栈 http://localhost:15000（/health database=intelligent_audio_test）。
登录：RSA-OAEP 加密登录取 token → 写 localStorage iatp:auth:token:v1 → 直达报告页。

覆盖：
①「结果对比」叶表转置：首列=指标名称（主/子维度分组），其后每资源一列（设备数=资源列数），
   列头含执行状态徽章 + 执行时间（转置不丢）；
② 展开区全块按轮次呈现：评分指标/多轮对话结果/执行结果（参考数据/用例参数/评估结果/
   设备·API 执行结果/时间轴对比/音频时间轴/结果音频）——块显隐与接口数据一致（数据驱动）；
③ 多轮用例叶表渲染轮次 Tab；console 无 SEVERE；浅色 + 深色截图。
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5273').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://localhost:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int2089')
TOKEN_KEY = 'iatp:auth:token:v1'
THEME_KEY = 'iatp:theme:v1:mode'
REPORT_ID = os.environ.get('REPORT_ID', '395')
USERNAME = os.environ.get('REACT_USER', '接线测试_admin')
PASSWORD = os.environ.get('REACT_PWD', 'JieXianTest@2026')

RESULT = []
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1200]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:280] if detail else ''))


def get_token():
    with urllib.request.urlopen(API + '/api/v1/auth/login/encryption-key', timeout=60) as r:
        key_data = json.loads(r.read().decode('utf-8'))
    pub = serialization.load_pem_public_key(key_data['public_key'].encode())
    enc = pub.encrypt(
        PASSWORD.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    body = urllib.parse.urlencode({
        'username': USERNAME,
        'password_encrypted': base64.b64encode(enc).decode(),
        'encryption_key_id': key_data['kid'],
    }).encode()
    req = urllib.request.Request(
        API + '/api/v1/auth/login', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))['access_token']


def api_get(token, path):
    req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))


def api_post(token, path, payload):
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
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
    drv.set_page_load_timeout(60)
    return drv


def set_theme(drv, mode):
    drv.execute_script(
        "window.localStorage.setItem(arguments[0], arguments[1]);",
        THEME_KEY, mode,
    )
    drv.refresh()
    time.sleep(3)


def main():
    os.makedirs(ART, exist_ok=True)
    token = get_token()
    detail = api_get(token, '/api/v1/reports/%s' % REPORT_ID)['data']
    summary = detail.get('summary', {})
    resources = summary.get('resources') or []
    metrics = summary.get('all_metrics') or []
    check('接口资源数 = 报告 header 数', len(resources) == len(summary.get('resource_headers') or []),
          '%d 资源 / %d headers' % (len(resources), len(summary.get('resource_headers') or [])))

    # 取首个用例行（未合并）推断块显隐期望
    search = api_post(token, '/api/v1/reports/%s/cases/search' % REPORT_ID, {'page': 1, 'per_page': 20})
    data = search.get('data', search) if isinstance(search, dict) else search
    cases = data.get('items', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    first_rows = [c for c in cases]
    check('接口用例行非空', len(first_rows) > 0, 'rows=%d' % len(first_rows))
    case0 = first_rows[0] if first_rows else {}
    algo_types = set((a.get('paramType') or '') for a in (case0.get('algorithmResults') or []))
    has_ref = bool(case0.get('referenceParams'))
    has_caseparams = bool(case0.get('caseParams'))
    has_audio = bool(case0.get('audios'))
    has_multi_round = any('@round:' in (k or '') for k in (case0.get('referenceParams') or {}))
    has_timeline = any(t in ('rttm', 'stm') for t in algo_types)
    print('  [probe] first case: ref=%s caseParams=%s audio=%s multi_round=%s timeline=%s types=%s' % (
        has_ref, has_caseparams, has_audio, has_multi_round, has_timeline, sorted(algo_types)))

    drv = _driver()
    try:
        drv.get(BASE + '/login')
        time.sleep(2)
        drv.execute_script(
            "window.localStorage.setItem(arguments[0], arguments[1]);",
            TOKEN_KEY, token,
        )
        drv.get(BASE + '/report/%s' % REPORT_ID)
        WebDriverWait(drv, 40).until(
            lambda d: '具体用例' in d.find_element(By.TAG_NAME, 'body').text)
        time.sleep(4)
        # 滚动到「具体用例对比」分区
        for _ in range(40):
            drv.execute_script('window.scrollBy(0, 1200);')
            time.sleep(0.25)
        time.sleep(2)
        body = drv.find_element(By.TAG_NAME, 'body').text
        check('报告页有「具体用例对比」分区', '具体用例对比' in body)

        # 展开第一张用例卡
        expand_btns = drv.find_elements(By.XPATH, "//button[contains(@aria-label,'展开详情')]")
        check('找到用例卡展开钮', len(expand_btns) > 0, 'count=%d' % len(expand_btns))
        if not expand_btns:
            check('无法展开用例卡（后续跳过）', False)
        else:
            drv.execute_script("arguments[0].scrollIntoView({block:'center'})", expand_btns[0])
            time.sleep(0.5)
            drv.execute_script("arguments[0].click()", expand_btns[0])
            time.sleep(3)
            body2 = drv.find_element(By.TAG_NAME, 'body').text
            check('展开区含「结果对比」叶表标题', '结果对比' in body2)
            for block in ['评分指标', '执行结果', '设备/API 执行结果']:
                check('展开区含块「%s」' % block, block in body2)
            # 数据驱动块显隐
            check('参考数据块与接口一致', has_ref == ('参考数据' in body2),
                  'ref=%s' % has_ref)
            # caseParams 缺数据源 → 块内空态「暂无数据」（INT-2089 交付标注缺口）
            check('用例参数块与接口一致', '用例参数' in body2,
                  'caseParams=%s 暂无数据=%s' % (has_caseparams, '暂无数据' in body2))
            if not has_caseparams:
                check('用例参数块缺数据源显示「暂无数据」', '暂无数据' in body2)
            check('音频时间轴块与接口一致', has_audio == ('音频时间轴' in body2), 'audio=%s' % has_audio)
            check('时间轴对比块与接口一致', has_timeline == ('时间轴对比' in body2), 'timeline=%s' % has_timeline)

            # 结果对比叶表结构（转置）
            leaf_headers = []
            leaf_rows = []
            for t in drv.find_elements(By.XPATH, "//table"):
                try:
                    ths = [th.text.strip() for th in t.find_elements(By.XPATH, ".//thead//th")]
                    if ths and ths[0].startswith('指标名称'):
                        leaf_headers = ths
                        leaf_rows = [tr.text for tr in t.find_elements(By.XPATH, ".//tbody/tr")]
                        break
                except Exception:
                    continue
            check('叶表首列 = 指标名称', leaf_headers[:1] == ['指标名称'], str(leaf_headers[:2]))
            resource_cols = [h for h in leaf_headers[1:] if h]
            check('叶表资源列数 = 接口资源数', len(resource_cols) == len(resources) and len(resource_cols) > 0,
                  '列=%d 资源=%d' % (len(resource_cols), len(resources)))
            check('叶表指标行 > 0（行=指标）', len(leaf_rows) > 0, 'rows=%d' % len(leaf_rows))
            if leaf_rows:
                first_cell = leaf_rows[0].split('\t')[0] if '\t' in leaf_rows[0] else leaf_rows[0][:20]
                check('叶表首行非空', bool(first_cell.strip()), first_cell[:40])
            # 列头状态徽章 + 执行时间（转置不丢）
            if resource_cols:
                col0 = resource_cols[0]
                check('资源列头含执行状态/时间', ('成功' in col0 or '失败' in col0 or '—' in col0) and len(col0) > 8,
                      col0[:40])
            # 轮次 Tab（多轮用例）
            if has_multi_round:
                tab_triggers = drv.find_elements(By.XPATH, "//button[@role='tab' or contains(@data-slot,'tab-trigger')]")
                tab_texts = [t.text.strip() for t in tab_triggers if t.text.strip()]
                check('多轮用例叶表渲染轮次 Tab', any('轮' in t or '整体' in t for t in tab_texts),
                      str(tab_texts[:6]))

            # 截图（浅色）
            drv.execute_script("arguments[0].scrollIntoView({block:'start'})", expand_btns[0])
            time.sleep(1)
            drv.save_screenshot(os.path.join(ART, 'light_expanded.png'))
            # 深色
            set_theme(drv, 'dark')
            time.sleep(3)
            expand_btns2 = drv.find_elements(By.XPATH, "//button[contains(@aria-label,'展开详情')]")
            if expand_btns2:
                drv.execute_script("arguments[0].scrollIntoView({block:'start'})", expand_btns2[0])
                time.sleep(1)
                drv.save_screenshot(os.path.join(ART, 'dark_expanded.png'))
            set_theme(drv, 'light')

        # console SEVERE
        severes = []
        try:
            for log in drv.get_log('browser'):
                if log.get('level') == 'SEVERE':
                    severes.append(log)
        except Exception:
            pass
        check('console 无 SEVERE', len(severes) == 0, str(severes[:2])[:400])
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    print('\n=== RESULT SUMMARY ===')
    failed = [r for r in RESULT if not r['ok']]
    for r in RESULT:
        print(('[PASS] ' if r['ok'] else '[FAIL] ') + r['name'])
    print('TOTAL %d  PASS %d  FAIL %d' % (len(RESULT), len(RESULT) - len(failed), len(failed)))


if __name__ == '__main__':
    main()
