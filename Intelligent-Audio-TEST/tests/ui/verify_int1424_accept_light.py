# -*- coding: utf-8 -*-
"""INT-1424 验收截图+断言：三个独立节、维度分组、策略空态、浅色。"""
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
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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

def scroll_drawer(drv, target_text):
    """scroll the drawer container so target_text is centered."""
    drv.execute_script(f'''
        const labels = [...document.querySelectorAll('*')].filter(e => e.children.length===0 && e.textContent.trim()==={json.dumps(target_text)});
        const label = labels[labels.length-1];
        if (label) {{ label.scrollIntoView({{block:'center'}}); }}
    ''')
    time.sleep(0.6)

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

        # 1. 音频列表步骤（空态 + 唯一入口）
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.0)
        add_btns = drv.find_elements(By.XPATH, "//button[contains(., '添加音频')]")
        lib_btns = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        print('ADD_AUDIO=', len(add_btns), 'LIB=', len(lib_btns))
        empty = [e.text for e in drv.find_elements(By.XPATH, "//*[contains(text(), '尚未添加音频')]")]
        print('EMPTY_TEXT=', json.dumps(empty, ensure_ascii=False))
        drv.save_screenshot(os.path.join(OUT, 'L1_audio_step_empty.png'))

        # 2. 音频库选择弹窗
        if lib_btns:
            jsclick(drv, lib_btns[0]); time.sleep(2.0)
            # 搜索框
            search = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] input[placeholder*='搜索']")
            print('SEARCH_INPUT=', len(search))
            # 类型过滤（音频类型 Select/RadioGroup）
            typ = drv.find_elements(By.XPATH, "//div[@role='dialog']//*[contains(., '音频类型')]")
            print('TYPE_FILTER_LABEL=', len(typ))
            # 已选计数
            cnt = [e.text for e in drv.find_elements(By.XPATH, "//*[contains(., '已选择') and contains(., '个')]") if e.text]
            print('SELECT_COUNT_TEXT=', json.dumps(cnt[:2], ensure_ascii=False))
            # 全选本页/清空选择
            selpage = drv.find_elements(By.XPATH, "//button[contains(., '全选本页')]")
            clear = drv.find_elements(By.XPATH, "//button[contains(., '清空选择')]")
            print('SELECT_PAGE=', len(selpage), 'CLEAR=', len(clear))
            # 取消关闭
            canc = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
            for c in canc[-1:]:
                jsclick(drv, c); time.sleep(0.6); break
        drv.save_screenshot(os.path.join(OUT, 'L2_audio_select_dialog.png'))

        # 3. 评估维度步骤（分组/主/子形态）
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '评估维度')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.2)
        # 主/子徽章
        main_badge = drv.find_elements(By.XPATH, "//*[contains(text(), '主')]")
        child_badge = drv.find_elements(By.XPATH, "//*[contains(text(), '子')]")
        cat_header = drv.find_elements(By.XPATH, "//*[contains(text(), '未分类') or contains(text(), '分类')]")
        print('MAIN_BADGE=', len(main_badge), 'CHILD_BADGE=', len(child_badge), 'CAT_HDR=', len(cat_header))
        drv.save_screenshot(os.path.join(OUT, 'L3_dimension_step.png'))

        # 4. 整体评估维度独立节
        scroll_drawer(drv, '整体评估维度')
        drv.save_screenshot(os.path.join(OUT, 'L4_overall_dims_section.png'))
        print('OVERALL_SECTION_SHOT')

        # 5. 全局背景噪声独立节（真实设备 chips 验证）
        scroll_drawer(drv, '全局背景噪声')
        time.sleep(0.5)
        drv.save_screenshot(os.path.join(OUT, 'L5_global_noise_section.png'))
        # 设备 chips 源 = /playback-devices（Network 确认）
        dev_text = drv.find_elements(By.XPATH, "//*[contains(text(), '播放设备')]")
        print('DEV_LABEL=', len(dev_text))
        print('NOISE_SECTION_SHOT')

        # 6. 评估策略节（真实空态）
        scroll_drawer(drv, '评估策略')
        time.sleep(0.5)
        # 展开折叠节
        strat = drv.find_elements(By.XPATH, "//*[contains(., '评估策略') and @role='button']")
        if strat:
            jsclick(drv, strat[0]); time.sleep(1.0)
            # 引用已有策略 radio
            radios = drv.find_elements(By.XPATH, "//input[@type='radio' and @value='reference']")
            print('REF_RADIO=', len(radios))
            if radios:
                jsclick(drv, radios[0]); time.sleep(1.0)
                strat_sel = drv.find_elements(By.XPATH, "//*[contains(., '暂无可用策略')]")
                print('EMPTY_STRATEGY_TEXT=', len(strat_sel))
        drv.save_screenshot(os.path.join(OUT, 'L6_strategy_section.png'))
        print('STRATEGY_SECTION_SHOT')

        # Network evidence
        hits = ['/audios', '/playback-devices', '/evaluation-strategies', '/evaluation/dimensions', '/evaluation/categories']
        found = {k: 0 for k in hits}
        try:
            for entry in drv.get_log('performance'):
                try:
                    msg = json.loads(entry['message'])['message']
                    if msg.get('method') != 'Network.requestWillBeSent': continue
                    url = (msg.get('params', {}).get('request', {}).get('url') or '')
                    for k in hits:
                        if k in url: found[k] += 1
                except Exception: pass
        except Exception: pass
        print('NET=', json.dumps(found, ensure_ascii=False))
    finally:
        drv.quit()

if __name__ == '__main__':
    main()
