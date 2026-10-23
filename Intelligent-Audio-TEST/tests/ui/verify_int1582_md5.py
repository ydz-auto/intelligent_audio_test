# -*- coding: utf-8 -*-
"""INT-1582 验收：批量更新标注按音频内容 MD5 全库匹配（React，容器 15246 ← 本卡 dist）。

场景：
  A 内容 MD5 命中（库内记录改过名，本地文件名不同）
  B 音频内容不在库 → 未匹配原因「MD5 不在库内」
  C 只拖标注文件 → 未匹配原因「未拖入音频文件」+ toast
  D 深色主题复测 A
  E 提交「开始更新」→ toast 更新完成

用法：python verify_int1582_md5.py [--base http://127.0.0.1:15246]
证据：artifacts/int1582/*.png + console 摘要
"""
import argparse
import json
import os
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, 'artifacts', 'int1582')
FIXTURES = os.path.join(ARTIFACTS, 'fixtures')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

WAV_A = os.path.join(FIXTURES, '接线测试_INT1582_批量标注_A.wav')
TXT_A = os.path.join(FIXTURES, '接线测试_INT1582_批量标注_A.txt')
WAV_B = os.path.join(FIXTURES, '接线测试_INT1582_未入库_B.wav')
TXT_B = os.path.join(FIXTURES, '接线测试_INT1582_未入库_B.txt')

DIALOG = '[role="dialog"]'
RESULTS = {}


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


def perf_requests(drv, needle):
    """从 performance log 取指定 URL 片段的请求（双层嵌套解析）。"""
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
        except Exception:
            continue
        inner = msg.get('message') or {}
        method = inner.get('method') or ''
        params = inner.get('params') or {}
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            if needle in (req.get('url') or ''):
                out.append({
                    'method': req.get('method'),
                    'url': req.get('url'),
                    'postData': req.get('postData'),
                    'requestId': params.get('requestId'),
                })
    return out


def perf_responses(drv, request_ids):
    out = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
        except Exception:
            continue
        inner = msg.get('message') or {}
        if (inner.get('method') or '') != 'Network.responseReceived':
            continue
        params = inner.get('params') or {}
        if params.get('requestId') in request_ids:
            resp = params.get('response') or {}
            out[params.get('requestId')] = {'status': resp.get('status'), 'url': resp.get('url')}
    return out


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode
    )


def open_dialog(drv, base):
    drv.get(base + '/audio-import')
    btn = WebDriverWait(drv, 45).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(normalize-space(.), '批量更新标注')]")
    )
    btn.click()
    WebDriverWait(drv, 20).until(lambda d: d.find_element(By.CSS_SELECTOR, DIALOG).is_displayed())
    time.sleep(0.6)
    return drv.find_element(By.CSS_SELECTOR, DIALOG)


def dialog_text(drv):
    return drv.find_element(By.CSS_SELECTOR, DIALOG).text


def upload(drv, files, timeout=120):
    inp = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.CSS_SELECTOR, DIALOG + ' input[type="file"]')
    )
    inp.send_keys('\n'.join(files))
    # 处理完成：出现「已解析」摘要（进度条区域消失）
    WebDriverWait(drv, timeout).until(lambda d: '已解析' in dialog_text(d))
    time.sleep(0.5)


def reset_selection(drv):
    btn = drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='重新选择']")
    btn.click()
    WebDriverWait(drv, 10).until(lambda d: '已解析' not in dialog_text(d))
    time.sleep(0.3)


def toasts(drv):
    items = drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
    return [t.text.strip() for t in items if t.text.strip()]


def shot(drv, name):
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    print('SHOT', path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:15246')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(base + '/')
        time.sleep(2)
        set_theme(drv, 'light')
        # 清空 performance log
        drv.get_log('performance')

        # ---------- A: 内容 MD5 命中（改名记录） ----------
        open_dialog(drv, base)
        desc = dialog_text(drv)
        RESULTS['A_desc_no_200_cap'] = ('前 200 条' not in desc)
        RESULTS['A_desc_mentions_md5'] = ('MD5' in desc and '全量' in desc)
        upload(drv, [WAV_A, TXT_A])
        text_a = dialog_text(drv)
        RESULTS['A_text'] = text_a
        shot(drv, 'A_light_md5_match.png')

        reqs = perf_requests(drv, '/audios/by-md5')
        ids = {r['requestId'] for r in reqs}
        resps = perf_responses(drv, ids)
        RESULTS['A_by_md5_requests'] = [
            {
                'method': r['method'],
                'url': r['url'],
                'postData': r['postData'],
                'status': resps.get(r['requestId'], {}).get('status'),
            }
            for r in reqs
        ]

        # ---------- B: 音频未入库 ----------
        reset_selection(drv)
        upload(drv, [WAV_B, TXT_B])
        text_b = dialog_text(drv)
        RESULTS['B_text'] = text_b
        shot(drv, 'B_light_md5_miss.png')

        # ---------- C: 只拖标注 ----------
        reset_selection(drv)
        drv.get_log('performance')
        upload(drv, [TXT_A])
        time.sleep(0.8)
        text_c = dialog_text(drv)
        RESULTS['C_text'] = text_c
        RESULTS['C_toast'] = toasts(drv)
        shot(drv, 'C_light_no_audio.png')

        # ---------- D: 深色主题复测 A ----------
        reset_selection(drv)
        set_theme(drv, 'dark')
        drv.refresh()
        time.sleep(1.5)
        open_dialog(drv, base)
        upload(drv, [WAV_A, TXT_A])
        results_text_d = dialog_text(drv)
        RESULTS['D_text'] = results_text_d
        RESULTS['D_html_dark'] = drv.execute_script(
            "return document.documentElement.classList.contains('dark')"
        )
        shot(drv, 'D_dark_md5_match.png')

        # ---------- E: 提交（关掉刷新用例开关，避免已知刷新超时） ----------
        set_theme(drv, 'light')
        drv.refresh()
        time.sleep(1.5)
        open_dialog(drv, base)
        upload(drv, [WAV_A, TXT_A])
        sw = drv.find_element(By.CSS_SELECTOR, DIALOG + " [data-slot='switch']")
        if sw.get_attribute('aria-checked') == 'true' or sw.get_attribute('data-state') == 'checked':
            sw.click()
            time.sleep(0.5)
        RESULTS['E_switch_state'] = sw.get_attribute('aria-checked') or sw.get_attribute('data-state')
        drv.get_log('performance')
        submit = drv.find_element(By.XPATH, "//div[@role='dialog']//button[contains(normalize-space(.), '开始更新')]")
        submit.click()
        WebDriverWait(drv, 120).until(lambda d: any('更新' in t for t in toasts(d)))
        time.sleep(0.8)
        RESULTS['E_toast'] = toasts(drv)
        shot(drv, 'E_light_submit_toast.png')
        reqs_e = perf_requests(drv, '/audios/batch/annotations')
        ids_e = {r['requestId'] for r in reqs_e}
        resps_e = perf_responses(drv, ids_e)
        RESULTS['E_batch_requests'] = [
            {
                'method': r['method'],
                'url': r['url'],
                'postData': r['postData'],
                'status': resps_e.get(r['requestId'], {}).get('status'),
            }
            for r in reqs_e
        ]
    finally:
        drv.quit()

    with open(os.path.join(ARTIFACTS, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print(json.dumps(RESULTS, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
