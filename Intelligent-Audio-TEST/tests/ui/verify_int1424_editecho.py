# -*- coding: utf-8 -*-
"""INT-1424 编辑回显：展开分组 → 编辑带 background_noise 的真实用例 → 核对独立节回显。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5350')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int1424_shots')
os.makedirs(OUT, exist_ok=True)

def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new'); options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception: pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    vv = tuple(int(x) for x in ver.split('.') if x.isdigit())
                    if vv and vv[0] == chrome_major: drv_path = exe
                except ValueError: continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45); drv.set_script_timeout(180)
    return drv

def jsclick(drv, el):
    drv.execute_script("arguments[0].click()", el)

def main():
    drv = _driver()
    try:
        drv.get(BASE + '/login'); time.sleep(1.5)
        drv.execute_script('try { window.localStorage.clear() } catch(e) {}')
        drv.get(BASE + '/login')
        WebDriverWait(drv,20).until(lambda d: len(d.find_elements(By.ID,'username'))>0)
        drv.find_element(By.ID,'username').send_keys('接线测试_admin')
        drv.find_element(By.ID,'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH,"//button[contains(., '登 录')]").click()
        WebDriverWait(drv,25).until(lambda d: '/login' not in d.current_url)
        time.sleep(2.0)
        drv.get(BASE + '/testcases'); time.sleep(4.0)

        # 展开分组：找第一个分组组头（含「条」的组名）点击
        grp = drv.find_elements(By.XPATH, "//*[contains(text(), '话轮接管')] | //*[contains(., '条') and contains(@class,'font-medium')]")
        # 更稳：找「加载更多」前的分组头按钮
        grp_heads = drv.find_elements(By.XPATH, "//*[contains(., '条')][@role='button'] | //button[contains(., '条')]")
        print('GROUP_HEADS=', len(grp_heads))
        clicked = False
        for g in grp_heads:
            t = g.text
            if '211 条' in t or '话轮接管' in t:
                jsclick(drv, g); time.sleep(2.0); clicked = True; print('CLICKED_GROUP=', json.dumps(t[:30], ensure_ascii=False)); break
        if not clicked:
            # 第一个含「条」的按钮
            for g in grp_heads:
                if '条' in g.text:
                    jsclick(drv, g); time.sleep(2.0); clicked = True; print('CLICKED_GROUP_FALLBACK=', json.dumps(g.text[:30], ensure_ascii=False)); break
        if not clicked:
            print('NO_GROUP_CLICKED')

        # 分组展开后，找用例行 + 该行「编辑」钮
        case_rows = drv.find_elements(By.XPATH, "//*[contains(text(), '测试用例_HJ')]")
        print('CASE_ROWS=', len(case_rows))
        edits = drv.find_elements(By.XPATH, "//button[contains(., '编辑')]")
        print('EDIT_BTNS=', len(edits))
        if edits:
            # 编辑按钮在每行操作列；点第一个可见编辑钮（展开分组后的）
            for e in edits:
                r = e.get_attribute('aria-hidden')
                if r is None:
                    jsclick(drv, e); time.sleep(2.5); print('EDIT_CLICKED'); break

        # 抽屉打开后核对三独立节
        for label in ['整体评估维度', '全局背景噪声', '评估策略']:
            els = drv.find_elements(By.XPATH, f"//*[contains(normalize-space(.), '{label}')]")
            print(label, '=', len(els))
        # 全局背景噪声节回显（已配置的噪声应显示音频名/设备）
        drv.execute_script("const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0 && e.textContent.trim()==='全局背景噪声'); if(els.length) els[els.length-1].scrollIntoView({block:'center'});")
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(OUT, 'RT_edit_echo2.png'))
        # 抽 drawer 内噪声节文本
        drawer_txt = drv.execute_script('''
            const d = document.querySelector('[role="dialog"]');
            return d ? d.textContent : '';
        ''')
        idx = drawer_txt.find('全局背景噪声')
        print('NOISE_SECTION_TXT=', json.dumps(drawer_txt[idx:idx+300], ensure_ascii=False))
    finally:
        drv.quit()

if __name__ == '__main__':
    main()
