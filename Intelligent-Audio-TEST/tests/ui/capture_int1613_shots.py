# -*- coding: utf-8 -*-
"""INT-1613 收尾取证：浅/深色文件夹导入弹窗、Network 证据页、旧 Vue 同弹窗对照。

用例列表页当前在 docker 15000 上 gRPC DEADLINE_EXCEEDED（环境问题，非本卡），
多轮用例的逐轮结构以 GET /testcases/{id} 真实回读 + merge 载荷在网络证据页呈现。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5321'
VUE_BASE = 'http://127.0.0.1:8080'
ART = 'tests/ui/artifacts/int1613'
SRC = r'D:\00_temp\int1613'
DRIVER = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'


def log(msg):
    print(msg, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)


def open_dialog_with_folder(drv, folder):
    drv.get(BASE + '/audio-import')
    WebDriverWait(drv, 60).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(normalize-space(.), '批量从文件夹导入')]"))
    time.sleep(2)
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '批量从文件夹导入')]"))
    WebDriverWait(drv, 15).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.8)
    inp = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[type='file']")
    drv.execute_script("arguments[0].style.display='block';", inp)
    inp.send_keys(os.path.join(SRC, folder))
    WebDriverWait(drv, 20).until(lambda d: '已选' in d.find_element(By.XPATH, "//div[@role='dialog']").text)
    time.sleep(1.0)


def evidence_screenshot(drv, summary):
    rows = []
    for scen in summary['scenarios']:
        for merge in scen['merges']:
            body = merge.get('reqBody') or {}
            cfg = body.get('test_case_config') or {}
            rows.append({
                'scenario': scen['name'],
                'POST /audios/upload/merge': merge.get('status'),
                'create_test_case': body.get('create_test_case'),
                'default_playback_device_id': body.get('default_playback_device_id'),
                'test_case_config.rounds': [
                    {'round_number': r.get('round_number'),
                     'audios': [{k: a.get(k) for k in ('audio_name', 'play_order', 'audio_id', 'playback_device_id') if a.get(k) is not None}
                                for a in (r.get('audios') or [])]}
                    for r in (cfg.get('rounds') or [])
                ],
                'response': (json.loads(merge.get('respText') or '{}').get('data') if merge.get('respText') else None),
            })
    html = ''.join([
        '<html><head><meta charset="utf-8"><style>',
        'body{font-family:Consolas,monospace;font-size:12.5px;padding:12px;background:#0b1020;color:#d8e1f0}',
        'h2{font-size:15px;color:#7dd3fc;margin:8px 0}pre{white-space:pre-wrap;background:#111a2e;padding:8px;',
        'border-radius:6px;border:1px solid #24314d;margin:4px 0 10px}',
        '</style></head><body>',
        '<h2>INT-1613 Network：POST /api/v1/audios/upload/merge（真实 docker 15000 / intelligent_audio_test）</h2>',
        '<pre>%s</pre>' % json.dumps(rows, ensure_ascii=False, indent=1),
        '<h2>GET /api/v1/testcases/{id} → config.rounds（真实回读）</h2>',
        '<pre>%s</pre>' % json.dumps(summary.get('detail_rounds') or {}, ensure_ascii=False, indent=1),
        '</body></html>',
    ])
    drv.switch_to.new_window('tab')
    drv.get('about:blank')
    drv.set_window_size(1500, 1400)
    drv.execute_script('document.open();document.write(arguments[0]);document.close();', html)
    time.sleep(1)
    drv.save_screenshot(os.path.join(ART, '04-network-merge-payload.png'))
    log('Network 证据页已截图')
    drv.close()
    drv.switch_to.window(drv.window_handles[0])


def vue_comparison(drv):
    drv.get(VUE_BASE + '/audio-import')
    time.sleep(3)
    if 'audio-import' not in drv.current_url:
        drv.get(VUE_BASE + '/#/audio-import')
        time.sleep(3)
    drv.set_window_size(1600, 1000)
    drv.save_screenshot(os.path.join(ART, '05-vue-audio-import.png'))
    found = False
    for xp in [
        "//button[contains(normalize-space(.), '批量从文件夹导入')]",
        "//span[contains(normalize-space(.), '批量从文件夹导入')]",
        "//*[contains(@class, 'btn') and contains(normalize-space(.), '文件夹')]",
    ]:
        els = drv.find_elements(By.XPATH, xp)
        if els:
            js_click(drv, els[0])
            found = True
            break
    if found:
        time.sleep(2)
        drv.save_screenshot(os.path.join(ART, '06-vue-folder-dialog.png'))
    log('旧 Vue 对照图已截（打开弹窗=%s）' % found)


o = Options()
o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
o.add_argument('--headless=new')
o.add_argument('--window-size=1600,1000')
o.add_argument('--no-sandbox')
o.add_argument('--lang=zh-CN')
o.add_argument('--disable-gpu')
drv = webdriver.Chrome(service=Service(DRIVER), options=o)
drv.set_script_timeout(300)
summary = json.load(open(os.path.join(ART, 'summary.json'), encoding='utf-8'))
try:
    drv.get(BASE + '/login')
    time.sleep(3)
    set_theme(drv, 'light')
    open_dialog_with_folder(drv, '接线测试_INT1613_s1')
    drv.save_screenshot(os.path.join(ART, '01-folder-dialog-light.png'))

    set_theme(drv, 'dark')
    open_dialog_with_folder(drv, '接线测试_INT1613_s1')
    drv.save_screenshot(os.path.join(ART, '02-folder-dialog-dark.png'))

    evidence_screenshot(drv, summary)
    vue_comparison(drv)
finally:
    drv.quit()
log('shots done')
