# -*- coding: utf-8 -*-
"""INT-2090 task-side verification: /tasks/413 case with real 76-char reference audio name.
Open case detail dialog (search HJ033) -> reference audio row -> play -> player modal title
truncation. Captures numeric truncation/overflow evidence + light/dark screenshots + console."""
import json
import os
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = 'http://localhost:5388'
ART = r'D:\00_user_data\multica_workspaces\intelligent-95ba6a12369f\int-2090-93d04ec988e4\worktree\_int2090\artifacts'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
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


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="username"]')))
    drv.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys('admin')
    drv.find_element(By.CSS_SELECTOR, 'input[name="password"]').send_keys('admin123')
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if '登录' in (b.text or '').replace(' ', ''):
            b.click()
            break
    time.sleep(3)
    assert drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')||''"), 'login failed'


def set_theme(drv, mode):
    drv.execute_script(f"localStorage.setItem('iatp:theme:v1:mode','{mode}')")


def console_severe(drv):
    return [e.get('message') for e in drv.get_log('browser') if e.get('level') == 'SEVERE']


def open_target_case(drv):
    drv.get(BASE + '/tasks/413')
    time.sleep(5)
    # search the case by HJ033 keyword
    try:
        search = WebDriverWait(drv, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="搜索用例"]'))
        )
        search.clear()
        search.send_keys('HJ033')
        time.sleep(2)
    except Exception as e:
        print('search input not found:', e)
    btns = drv.find_elements(By.CSS_SELECTOR, 'button[title^="查看用例详情"]')
    print('matched case buttons:', len(btns))
    if not btns:
        return False
    for b in btns:
        t = b.get_attribute('title') or ''
        if 'HJ033' in t:
            b.click()
            return True
    btns[0].click()
    return True


def scroll_to_ref_audio(drv):
    try:
        WebDriverWait(drv, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
        )
    except Exception as e:
        print('case detail dialog not open:', e)
        return None, None
    time.sleep(2)
    # switch to 第1轮 tab (JS click) so the 76-char JS121 reference audio (round 1) is shown
    try:
        drv.execute_script(
            "const b=Array.from(document.querySelectorAll('[data-slot=\"case-detail-dialog\"] button'))"
            ".find(x=>(x.textContent||'').replace(/\\s/g,'')==='第1轮'); if(b)b.click();"
        )
        time.sleep(1.5)
    except Exception as e:
        print('round tab js click issue:', e)
    # scroll the 参考音频 label into view (content is in DOM even when clipped)
    found_label = False
    for _ in range(3):
        found = drv.execute_script(
            "const els=Array.from(document.querySelectorAll('[data-slot=\"case-detail-dialog\"] *'))"
            ".filter(e=>e.textContent.trim()==='参考音频（用例输入）');"
            "if(els.length){els[els.length-1].scrollIntoView({block:'center'}); return true;} return false;"
        )
        if found:
            found_label = True
            break
        time.sleep(1)
    if not found_label:
        txt = drv.execute_script(
            "var d=document.querySelector('[data-slot=\"case-detail-dialog\"]'); return d?d.textContent.slice(-800):'NO DIALOG'"
        )
        print('参考音频 label not found; dialog text tail:', repr(txt))
        return None, None
    time.sleep(1)
    labels = drv.find_elements(By.XPATH, "//*[contains(text(),'参考音频（用例输入）')]")
    if not labels:
        print('参考音频 section still not found')
        return None, None
    section = labels[0].find_element(By.XPATH, '..')
    btns = section.find_elements(By.XPATH, ".//button[contains(.,'试听')]")
    spans = section.find_elements(By.XPATH, ".//span[contains(@class,'font-mono')]")
    return (spans[0] if spans else None), (btns[0] if btns else None)


def evidence(drv, tag):
    """numeric truncation/overflow checks in the player modal."""
    data = drv.execute_script(
        "const dlg=document.querySelector('[data-slot=\"dialog-content\"]');"
        "const title=dlg?dlg.querySelector('p.truncate'):null;"
        "if(!dlg||!title)return {err:'no dialog/title'};"
        "const cont=dlg.querySelector('.min-w-0');"
        "return {"
        " dialogW: dlg.getBoundingClientRect().width,"
        " dialogScrollW: dlg.scrollWidth,"
        " titleText: title.textContent,"
        " titleClientW: title.clientWidth,"
        " titleScrollW: title.scrollWidth,"
        " titleTruncated: title.scrollWidth>title.clientWidth+1,"
        " titleTitleAttr: title.getAttribute('title')||'',"
        " playBtn: !!Array.from(dlg.querySelectorAll('button')).find(b=>b.textContent.includes('播放')||b.getAttribute('aria-label')==='播放'),"
        " stopBtn: !!Array.from(dlg.querySelectorAll('button')).find(b=>b.textContent.includes('停止')||b.getAttribute('aria-label')==='停止'),"
        " horizontalOverflow: dlg.scrollWidth>dlg.clientWidth+1"
        "}"
    )
    print(f'[{tag}] evidence:', json.dumps(data, ensure_ascii=False)[:800])
    return data


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    try:
        login(drv)
        # LIGHT
        set_theme(drv, 'light')
        drv.refresh()
        time.sleep(2)
        if not open_target_case(drv):
            print('FATAL: target case not found')
            return
        name_span, play_btn = scroll_to_ref_audio(drv)
        if not play_btn:
            print('FATAL: no ref audio row')
            return
        print('ref name:', repr(name_span.text if name_span else ''))
        print('ref name title attr:', repr((name_span.get_attribute('title') if name_span else '')))
        drv.save_screenshot(os.path.join(ART, 'int2090_task413_dialog_light.png'))
        play_btn.click()
        time.sleep(3)
        ev = evidence(drv, 'light')
        drv.save_screenshot(os.path.join(ART, 'int2090_task413_player_light.png'))
        print('light SEVERE:', console_severe(drv))
        # DARK
        set_theme(drv, 'dark')
        drv.refresh()
        time.sleep(2)
        if open_target_case(drv):
            name_span, play_btn = scroll_to_ref_audio(drv)
            if play_btn:
                play_btn.click()
                time.sleep(3)
                evidence(drv, 'dark')
                drv.save_screenshot(os.path.join(ART, 'int2090_task413_player_dark.png'))
                print('dark SEVERE:', console_severe(drv))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
