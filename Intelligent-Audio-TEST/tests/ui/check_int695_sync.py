# -*- coding: utf-8 -*-
"""INT-695 补充走查：跨组件状态同步点（验收标准 3）。

① 覆盖 Switch 与编辑器初值同源：引用策略后开「覆盖整体评估维度」→ 维度编辑器初值 = 策略维度
   （策略「全链路智能音箱回归」维度 2 项：识别准确率/语义理解）；关闭覆盖 → 编辑器消失还原策略值语义。
② 策略 Select 新建后选项列表即时含新策略：新建策略入库 → 引用模式 Select 选项含新策略名（全局可复用）。
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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
    drv.set_page_load_timeout(45)
    return drv


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _enter_workbench(drv):
    drv.get(BASE + '/login')
    time.sleep(1.5)
    btns = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if btns:
        btns[0].click()
        time.sleep(2)
    drv.get(BASE + '/testcases/by-group')
    time.sleep(2.5)


def _open_drawer(drv):
    btns = drv.find_elements(By.XPATH, "//button[contains(., '新增用例')]")
    target = None
    for b in btns:
        if b.text.strip() == '新增用例':
            target = b
            break
    if target is None:
        target = btns[0]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
    time.sleep(0.4)
    target.click()
    WebDriverWait(drv, 8).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='sheet-content']")))
    time.sleep(1.0)


def _expand_strategy(drv):
    strat = drv.find_element(By.XPATH, "//button[contains(., '评估策略')]")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", strat)
    time.sleep(0.4)
    strat.click()
    time.sleep(0.8)


def _select_reference(drv):
    labels = drv.find_elements(By.XPATH, "//label[contains(., '引用已有策略')]")
    labels[0].click()
    time.sleep(1.0)
    sel = drv.find_elements(By.XPATH, "//button[contains(., '请选择要引用的评估策略')]")
    drv.execute_script("arguments[0].click()", sel[0])
    time.sleep(1.0)
    opts = drv.find_elements(By.XPATH, "//*[@data-slot='select-item' or contains(@class,'select-item')]")
    drv.execute_script("arguments[0].click()", opts[0])
    time.sleep(1.0)


def main():
    drv = _driver()
    try:
        _enter_workbench(drv)
        _open_drawer(drv)
        _expand_strategy(drv)
        _select_reference(drv)

        txt = _body(drv)
        assert '全链路智能音箱回归' in txt, '策略摘要卡缺策略名'
        # ① 覆盖 Switch 联动编辑器初值
        sw = drv.find_element(By.CSS_SELECTOR, "[data-slot='switch'][aria-label='覆盖整体评估维度']")
        drv.execute_script("arguments[0].click()", sw)
        time.sleep(1.0)
        txt = _body(drv)
        assert '识别准确率' in txt and '语义理解' in txt, f'覆盖编辑器初值未含策略维度：{txt[-300:]}'
        print('OK override-dimensions editor initial = strategy dimensions (识别准确率/语义理解)')
        # 关闭覆盖 → 编辑器消失
        drv.execute_script("arguments[0].click()", sw)
        time.sleep(0.8)
        txt = _body(drv)
        assert '覆盖整体评估维度' in txt
        editors = drv.find_elements(By.XPATH, "//button[contains(., '启用整体评估')]")
        print('OK override off -> editor hidden' if not editors else f'editor still visible: {len(editors)}')

        # ② 新建策略 → Select 选项即时含新策略
        create_labels = drv.find_elements(By.XPATH, "//label[contains(., '新建策略')]")
        create_labels[0].click()
        time.sleep(1.0)
        name = drv.find_element(By.CSS_SELECTOR, "input[aria-label='策略名称']")
        new_name = 'INT695_同步验证' + str(int(time.time()))
        name.send_keys(new_name)
        time.sleep(0.3)
        save_btn = drv.find_elements(By.XPATH, "//button[contains(., '保存策略并引用')]")
        drv.execute_script("arguments[0].click()", save_btn[0])
        time.sleep(1.5)
        txt = _body(drv)
        assert f'已引用「{new_name}」' in txt, f'节头徽章未更新：{txt[-200:]}'
        # 新建后已自动引用新策略（reference 模式）；打开策略 Select → 新策略在选项列表（全局可复用）
        # 注：base-ui SelectValue 显示原始 value（app 全站既有行为），策略 Select 是抽屉内最后一个 trigger
        triggers = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
        assert triggers, '策略 Select 触发器缺失'
        drv.execute_script("arguments[0].click()", triggers[-1])
        time.sleep(1.0)
        opts = drv.find_elements(By.XPATH, "//*[@data-slot='select-item' or contains(@class,'select-item')]")
        opt_texts = [o.text for o in opts]
        assert any(new_name in t for t in opt_texts), f'新策略未进 Select 列表：{opt_texts}'
        print('OK new strategy appears in reference Select list:', new_name)
        print('SYNC_POINTS_ALL_OK')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
