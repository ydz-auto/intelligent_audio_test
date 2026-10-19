# -*- coding: utf-8 -*-
"""INT-881 rework evidence capture:
- /report/67 (benchmark) 排行区块经 infra 桩渲染（浅/深）
- /report/2 分享弹窗生成链接（浅/深）
- /report/65 AI 复核发起：真实 POST /tasks/results/ai-review 即时发出（无假延迟），状态按后端推进（浅/深）
输出 artifacts/int881_rework/*.png
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

CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int881_rework')


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
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


def set_theme(drv, mode):
    drv.execute_script(f"localStorage.setItem('iatp:theme:v1:mode','{mode}')")
    drv.get('about:blank')
    time.sleep(0.5)


def api_requests(drv):
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            params = (msg.get('message') or {}).get('params') or {}
            method = (msg.get('message') or {}).get('method') or ''
            if method == 'Network.requestWillBeSent':
                u = (params.get('request') or {}).get('url', '')
                if '/api/' in u:
                    ts = entry.get('timestamp', 0)
                    out.append((ts, (params.get('request') or {}).get('method', ''), u.split('?')[0]))
        except Exception:
            continue
    return out


def wait_text(drv, text, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        if text in (drv.page_source or ''):
            return True
        time.sleep(0.5)
    return False


def click_generate_share(drv):
    """点击分享弹窗内的「生成分享链接」按钮（排除分享方式切换 tab 同名钮）。"""
    gen_btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button') if (b.text or '').strip() == '生成分享链接']
    for b in gen_btns:
        if not drv.execute_script('return !!arguments[0].closest(\'[aria-label="分享方式"]\');', b):
            b.click()
            return True
    return False


def open_share(drv):
    for b in drv.find_elements(By.CSS_SELECTOR, 'button'):
        if (b.text or '').strip() == '分享':
            b.click()
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5316')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    all_net = []
    try:
        drv.set_page_load_timeout(45)

        # ===== 1. /report/67 Benchmark 排行区块（浅色 + 深色） =====
        drv.get(base + '/report/67')
        time.sleep(10)
        wait_text(drv, 'Benchmark 排行')
        time.sleep(2)
        assert '旗舰-01' in (drv.page_source or ''), 'benchmark stub rows not rendered'
        assert '计算中' not in (drv.page_source or ''), 'stuck computing state'
        drv.save_screenshot(os.path.join(ARTIFACTS, '01_benchmark_ranking_light.png'))
        all_net += api_requests(drv)

        set_theme(drv, 'dark')
        drv.get(base + '/report/67')
        time.sleep(10)
        wait_text(drv, 'Benchmark 排行')
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, '02_benchmark_ranking_dark.png'))

        # ===== 2. /report/2 分享弹窗（浅色 + 深色） =====
        set_theme(drv, 'light')
        drv.get(base + '/report/2')
        time.sleep(10)
        wait_text(drv, '分享')
        assert open_share(drv), 'share button not found'
        time.sleep(3)
        assert wait_text(drv, '生成分享链接'), 'share dialog not opened'
        assert click_generate_share(drv), 'generate button not found'
        time.sleep(2)
        src = drv.page_source or ''
        assert 'share=' in src, 'share URL not generated'
        drv.save_screenshot(os.path.join(ARTIFACTS, '03_share_dialog_light.png'))
        all_net += api_requests(drv)

        set_theme(drv, 'dark')
        drv.get(base + '/report/2')
        time.sleep(10)
        wait_text(drv, '分享')
        open_share(drv)
        time.sleep(3)
        click_generate_share(drv)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, '04_share_dialog_dark.png'))

        # ===== 3. /report/65 AI 复核（真实 POST 即时发出，状态按后端推进） =====
        set_theme(drv, 'light')
        drv.get(base + '/report/65')
        time.sleep(10)
        ai_btn = None
        for b in drv.find_elements(By.CSS_SELECTOR, 'button'):
            if (b.text or '').strip() == 'AI 复核' and b.is_displayed():
                ai_btn = b
                break
        assert ai_btn is not None, 'AI review button not found'
        drv.execute_script('arguments[0].click();', ai_btn)
        time.sleep(2)
        assert wait_text(drv, '发起 AI 复核'), 'AI review dialog not opened'
        initiate_btn = None
        for b in drv.find_elements(By.CSS_SELECTOR, 'button'):
            if (b.text or '').strip() == '发起 AI 复核':
                initiate_btn = b
                break
        assert initiate_btn is not None, 'initiate button not found'
        if initiate_btn.is_enabled():
            t0 = time.time()
            drv.execute_script('arguments[0].click();', initiate_btn)
            time.sleep(1.2)
            net_after = api_requests(drv)
            post_ai = [r for r in net_after if 'ai-review' in r[2] and r[1] == 'POST']
            elapsed = time.time() - t0
            time.sleep(6)
            src = drv.page_source or ''
            drv.save_screenshot(os.path.join(ARTIFACTS, '05_ai_review_dialog_light.png'))
            print(f'AI_REVIEW_POST_AFTER_1.2s: {len(post_ai)} (elapsed {elapsed:.2f}s)')
            for p in post_ai:
                print('  POST', p[2])
            print('AI_REVIEW_STATE_RENDERED:', '已完成' in src or 'AI 复核中' in src or 'AI 复核执行失败' in src)
            print('AI_REVIEW_STATE_SNIPPET:', ('AI 复核中' in src, '已完成' in src, 'AI 复核执行失败' in src))
            all_net += net_after

            # 深色 AI 复核弹窗
            set_theme(drv, 'dark')
            drv.get(base + '/report/65')
            time.sleep(10)
            for b in drv.find_elements(By.CSS_SELECTOR, 'button'):
                if (b.text or '').strip() == 'AI 复核' and b.is_displayed():
                    drv.execute_script('arguments[0].click();', b)
                    break
            time.sleep(2)
            for b in drv.find_elements(By.CSS_SELECTOR, 'button'):
                if (b.text or '').strip() == '发起 AI 复核' and b.is_enabled():
                    drv.execute_script('arguments[0].click();', b)
                    break
            time.sleep(4)
            drv.save_screenshot(os.path.join(ARTIFACTS, '06_ai_review_dialog_dark.png'))
        else:
            drv.save_screenshot(os.path.join(ARTIFACTS, '05_ai_review_dialog_light.png'))
            print('AI_REVIEW_INITIATE_DISABLED (no result/dimension data)')

        # ===== Network 汇总 =====
        all_net += api_requests(drv)
        seen = set()
        uniq = []
        for ts, m, u in all_net:
            key = (m, u)
            if key not in seen:
                seen.add(key)
                uniq.append((m, u))
        print('NETWORK_UNIQUE_API:')
        for m, u in sorted(uniq, key=lambda x: x[1]):
            print('  ', m, u)

    finally:
        drv.quit()


if __name__ == '__main__':
    main()
