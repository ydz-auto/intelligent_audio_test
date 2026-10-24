# -*- coding: utf-8 -*-
"""INT-1479 探针：特征分析弹窗重走后，抓取首屏请求与渲染文本（诊断用）。

用法：REACT_DEV_BASE=http://127.0.0.1:15173 AUDIO_ID=2071 python tests/ui/_int1479_probe_feature_dialog.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_int1663_feature_analysis as V  # noqa: E402

from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402


def main():
    drv = webdriver.Chrome(service=Service(V.DRIVER), options=V._opts())
    drv.set_script_timeout(180)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': V.FETCH_PATCH})
    try:
        V.ensure_session(drv)
        st, target = V.api(drv, '/api/v1/audios/%s' % V.TARGET_ID)
        print('detail status=%s name=%s' % (st, (target or {}).get('name')), flush=True)
        name = target['name']
        V.set_search(drv, name.split('_')[0])
        print('rows after search: %d' % len(drv.find_elements(
            By.XPATH, "//button[contains(@aria-label, '的操作')]")), flush=True)
        V.open_feature_dialog(drv, name)
        for wait in (2, 4, 8, 12):
            time.sleep(wait)
            net = drv.execute_script('return (window.__net || []).filter(e => /\/(features|quality|process)/.test(e.url))')
            body = V.dialog(drv).text
            print('--- after +%ss: net=%d' % (wait, len(net)), flush=True)
            for e in net:
                print('   %s %s -> %s %s' % (e['method'], e['url'], e['status'],
                                             (e.get('resp') or '')[:160]), flush=True)
            print('   text: %r' % body[:400], flush=True)
            if net:
                break
        V.shot(drv, 'probe-feature-dialog.png')
        all_net = drv.execute_script('return (window.__net || []).map(e => e.method + " " + e.url + " -> " + e.status)')
        print('ALL NET (%d):' % len(all_net), flush=True)
        for line in all_net:
            print('   ' + line, flush=True)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
