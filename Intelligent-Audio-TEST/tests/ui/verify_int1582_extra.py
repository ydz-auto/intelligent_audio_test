# -*- coding: utf-8 -*-
"""INT-1582 补充验收：列表筛选状态下仍全库匹配（F）、只拖音频（G）、by-md5 响应码（H）。"""
import json
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from verify_int1582_md5 import (
    ARTIFACTS, TXT_A, WAV_A, _driver, dialog_text, open_dialog, perf_requests,
    perf_responses, reset_selection, set_theme, shot, toasts,
)

BASE = 'http://127.0.0.1:15246'
RESULTS = {}


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/')
        time.sleep(2)
        set_theme(drv, 'light')
        drv.get(BASE + '/audio-import')
        # 列表筛选：搜索一个不含测试音频的关键字，模拟「列表里看不到目标音频」
        box = WebDriverWait(drv, 45).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索文件名']")
        )
        box.send_keys('HJ050')
        time.sleep(3)
        body = drv.find_element(By.TAG_NAME, 'body').text
        RESULTS['F_list_filtered_hides_target'] = ('已改名_A' not in body)
        RESULTS['F_list_rows_sample'] = [el.text.split('\n')[0] for el in drv.find_elements(By.CSS_SELECTOR, 'tbody tr')][:3]

        open_dialog(drv, BASE)
        inp = drv.find_element(By.CSS_SELECTOR, '[role="dialog"] input[type="file"]')
        inp.send_keys('\n'.join([WAV_A, TXT_A]))
        WebDriverWait(drv, 120).until(lambda d: '已解析' in dialog_text(d))
        time.sleep(1.2)
        text = dialog_text(drv)
        RESULTS['F_dialog_text'] = text
        RESULTS['F_matched_under_filter'] = ('匹配 1' in text and '#2354' in text)
        shot(drv, 'F_light_filtered_match.png')

        reqs = perf_requests(drv, '/audios/by-md5')
        ids = {r['requestId'] for r in reqs}
        resps = perf_responses(drv, ids)
        RESULTS['H_by_md5'] = [
            {'postData': r['postData'], 'status': resps.get(r['requestId'], {}).get('status')} for r in reqs
        ]

        # G：只拖音频（无标注文件）
        reset_selection(drv)
        inp = drv.find_element(By.CSS_SELECTOR, '[role="dialog"] input[type="file"]')
        inp.send_keys(WAV_A)
        time.sleep(3)
        RESULTS['G_toast'] = toasts(drv)
        RESULTS['G_rows_present'] = ('已解析' in dialog_text(drv))
        shot(drv, 'G_light_audio_only.png')
    finally:
        drv.quit()

    with open(os.path.join(ARTIFACTS, 'results_extra.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print(json.dumps(RESULTS, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
