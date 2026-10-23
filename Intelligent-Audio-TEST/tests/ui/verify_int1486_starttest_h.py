# -*- coding: utf-8 -*-
"""INT-1486 取证 H：任务命名弹窗重开残留名（INT-1528 在 15173 部署构建上仍未修复）浅色截图。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
ART = 'tests/ui/artifacts/int1486'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
token = open(os.path.join(ART, 'token.txt')).read().strip()

o = Options(); o.binary_location = CHROME
for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN']:
    o.add_argument(a)
cache = r'D:\00_user_data\.cache\selenium\chromedriver\win64'
path = ''
for v in os.listdir(cache):
    exe = os.path.join(cache, v, 'chromedriver.exe')
    if os.path.isfile(exe):
        path = exe
d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
d.set_script_timeout(120)
d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': "try{localStorage.setItem('iatp:auth:token:v1', %s)}catch(e){}" % json.dumps(token)})


def js_click(el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text():
    return d.execute_script('return document.body.innerText') or ''


def shot(n):
    p = os.path.join(ART, n)
    d.save_screenshot(p); print('SHOT', n, os.path.getsize(p))


def ti():
    els = d.find_elements(By.CSS_SELECTOR, 'input#task-name')
    return els[0] if els else None


try:
    d.get(BASE + '/start-test')
    WebDriverWait(d, 90).until(lambda x: '按分组' in text())
    for _ in range(40):
        if d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
            break
        time.sleep(2)
    time.sleep(2)
    sp = d.find_elements(By.XPATH, "//span[normalize-space()='话轮接管']")
    if sp:
        js_click(sp[0]); time.sleep(3)
    boxes = []
    for _ in range(20):
        boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')
        if boxes:
            break
        time.sleep(2)
    print('case rows', len(boxes))
    js_click(boxes[0]); time.sleep(1.5)
    js_click(d.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")[0])
    WebDriverWait(d, 60).until(lambda x: '执行参数' in text()); time.sleep(2)
    dev = d.find_elements(By.CSS_SELECTOR, '[aria-label="选择设备 pura90gpt"]')
    if dev:
        js_click(dev[0]); time.sleep(1.2)
    js_click(d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")[-1]); time.sleep(2.5)
    e = ti()
    print('open#1 value', e.get_attribute('value') if e else None)
    e.send_keys(Keys.CONTROL, 'a'); e.send_keys(Keys.DELETE); e.send_keys('接线测试_INT1486_残留名取证')
    time.sleep(0.6)
    js_click(d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']")[0])
    time.sleep(1.5)
    js_click(d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")[-1]); time.sleep(2.5)
    e = ti()
    print('reopen value', e.get_attribute('value') if e else None)
    shot('F_defect_taskname_residual_light.png')
finally:
    d.quit()
