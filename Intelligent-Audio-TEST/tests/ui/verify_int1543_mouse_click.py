# -*- coding: utf-8 -*-
"""INT-1543 补充实测：六项「整项可点击」——对每项用真实鼠标点 dt 文本区（非锚点 JS 点击），
验证覆盖层 Link 接管点击并落点正确。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DOCKER_BASE', 'http://localhost:15433')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1543_docker')
STATS_DL = "//span[normalize-space(.)='平台规模']/following-sibling::dl"
EXPECTED = [
    ('测试用例', '/testcases'),
    ('测试任务', '/tasks'),
    ('评估维度', '/Evaluation'),
    ('音频文件', '/audio-import'),
    ('在线设备', '/devices'),
    ('API 服务', '/start-test'),
]

o = Options()
o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
o.add_argument('--headless=new')
o.add_argument('--window-size=1600,1000')
o.add_argument('--no-sandbox')
o.add_argument('--disable-gpu')
o.add_argument('--lang=zh-CN')
drv = webdriver.Chrome(options=o)
drv.set_page_load_timeout(90)
res = {}
try:
    for label, prefix in EXPECTED:
        drv.get(BASE + '/')
        WebDriverWait(drv, 90).until(
            lambda d: d.find_elements(By.XPATH, STATS_DL + "/div[dt]"))
        time.sleep(1.2)
        dt = drv.find_element(
            By.XPATH, STATS_DL + f"/div/dt[contains(., '{label}')]")
        drv.execute_script('arguments[0].scrollIntoView({block:"center"})', dt)
        time.sleep(0.4)
        try:
            ActionChains(drv).move_to_element(dt).click().perform()
            ok = True
            err = None
        except Exception as e:  # noqa: BLE001
            ok = False
            err = type(e).__name__ + ': ' + str(e)[:160]
        try:
            WebDriverWait(drv, 20).until(lambda d: prefix in d.current_url)
            url = drv.current_url
        except Exception:
            url = drv.current_url
        res[label] = {
            'mouse_click_dispatched': ok,
            'click_error': err,
            'final_url': url,
            'landed': prefix in url,
        }
        print(label, res[label], flush=True)
finally:
    drv.quit()

with open(os.path.join(ART, 'mouse_click_6.json'), 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('ALL_LANDED', all(v['landed'] for v in res.values()), flush=True)
