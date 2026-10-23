# -*- coding: utf-8 -*-
"""INT-1501 补充取证：捕获 SPL 页真实请求（/playback-devices、/apis 等）。"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_int1501_spl_15173 as V  # noqa: E402
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

NEEDLES = ['/api/v1/spl?', '/api/v1/spl/stats', '/api/v1/playback-devices', '/api/v1/apis',
           '/api/v1/digital-spl']


def main():
    drv = V._driver()
    hits = {n: {} for n in NEEDLES}
    all_urls = {}

    def snap():
        for url, st in V.drain_perf(drv):
            all_urls[url] = st
            for n in NEEDLES:
                if n in url:
                    hits[n][url] = st

    try:
        drv.get_log('performance')
        V.open_spl(drv)
        snap()
        V.js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加增益映射')]"))
        WebDriverWait(drv, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='关联播放设备']")))
        time.sleep(1.5)
        snap()
        V.close_dialog(drv)
        V.js_click(drv, drv.find_element(By.XPATH, "//button[@role='tab' and contains(., 'RMS-SPL')]"))
        time.sleep(1.5)
        V.js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加 RMS-SPL 映射')]"))
        WebDriverWait(drv, 20).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='关联被测 API']")))
        time.sleep(1.5)
        snap()
        V.close_dialog(drv)
        snap()
    finally:
        drv.quit()

    for n in NEEDLES:
        print(n, '→', json.dumps(hits[n], ensure_ascii=False))
    print('--- all api urls ---')
    for u, s in sorted(all_urls.items()):
        if '/api/' in u:
            print(s, u)
    out = os.path.join(V.ART, 'network.json')
    os.makedirs(V.ART, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(hits, f, ensure_ascii=False, indent=2)
    ok = bool(hits['/api/v1/playback-devices']) and bool(hits['/api/v1/apis'])
    print('BOTH OK' if ok else 'MISSING')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
