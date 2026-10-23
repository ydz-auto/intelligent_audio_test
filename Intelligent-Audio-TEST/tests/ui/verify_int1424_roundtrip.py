# -*- coding: utf-8 -*-
"""INT-1424 保存契约 round-trip：新建用例 → 选算法 → 整体评估维度选一个维度 → 保存 → API 核对 config.dimensions → 编辑回显。"""
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
        drv.get(BASE + '/testcases'); time.sleep(3.0)
        newb = drv.find_elements(By.XPATH, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
        jsclick(drv, newb[0]); time.sleep(2.0)

        # 名称
        name_in = drv.find_elements(By.XPATH, "//input[contains(@placeholder,'用例名称')]")
        if name_in:
            name_in[0].clear(); name_in[0].send_keys('接线测试_INT1424_roundtrip')
            time.sleep(0.5)

        # 关联算法：选择第一个算法（select 打开）
        alg = drv.find_elements(By.XPATH, "//button[contains(., '请选择算法')]")
        if alg:
            jsclick(drv, alg[0]); time.sleep(1.0)
            opts = drv.find_elements(By.XPATH, "//*[@role='option'] | //*[@data-value]")
            print('ALG_OPTIONS=', len(opts))
            if opts:
                txt0 = drv.execute_script("return arguments[0].textContent", opts[0])
                jsclick(drv, opts[0]); time.sleep(1.0)
                print('ALG_SELECTED=', str(txt0)[:40])

        # 整体评估维度：enable switch then pick a dimension
        drv.execute_script("const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0 && e.textContent.trim()==='整体评估维度'); if(els.length) els[els.length-1].scrollIntoView({block:'center'});")
        time.sleep(0.6)
        sw = drv.find_elements(By.XPATH, "//button[@role='switch']")
        print('SWITCHES=', len(sw))
        if sw:
            jsclick(drv, sw[0]); time.sleep(1.0)
            # dimension picker inside overall section: main/child chips
            dims = drv.find_elements(By.XPATH, "//*[contains(@class,'rounded-full') and (contains(text(),'主') or contains(text(),'子'))] | //button[.//span[contains(text(),'主') or contains(text(),'子')]]")
            print('DIM_CHIPS=', len(dims))
            # click first dimension chip (main with 子 count)
            cands = drv.find_elements(By.XPATH, "//button[.//*[contains(text(), '主')]]")
            print('MAIN_DIM_BTNS=', len(cands))
            if cands:
                jsclick(drv, cands[0]); time.sleep(0.6)
                print('DIM_CLICKED=', cands[0].text[:40])
        drv.save_screenshot(os.path.join(OUT, 'RT1_before_save.png'))

        # 保存
        save_btns = drv.find_elements(By.XPATH, "//button[contains(., '保存')]")
        print('SAVE_BTN=', len(save_btns))
        if save_btns:
            jsclick(drv, save_btns[-1]); time.sleep(3.0)
            # toast check / url
            print('URL_AFTER_SAVE=', drv.current_url)
            drv.save_screenshot(os.path.join(OUT, 'RT2_after_save.png'))

        # API 核对 config.dimensions
        result = drv.execute_async_script('''
            const cb = arguments[arguments.length-1];
            const tok = localStorage.getItem('iatp:auth:token:v1') || '';
            fetch('/api/v1/testcases?keyword=接线测试_INT1424_roundtrip', {headers:{'Authorization':'Bearer '+tok}})
              .then(r=>r.json()).then(d=>{
                const items = d && d.data && d.data.items ? d.data.items : (d.data || []);
                const found = (Array.isArray(items)?items:[]).filter(c=>String(c.name||'').includes('接线测试_INT1424_roundtrip'));
                if(!found.length) return cb({err:'not found', raw: JSON.stringify(d).slice(0,300)});
                const c = found[0];
                return cb({id:c.id, name:c.name, config:c.config});
              }).catch(e=>cb({err:String(e)}));
        ''')
        print('ROUNDTRIP_RESULT=', json.dumps(result, ensure_ascii=False)[:800])
    finally:
        drv.quit()

if __name__ == '__main__':
    main()
