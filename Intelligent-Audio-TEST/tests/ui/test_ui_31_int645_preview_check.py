# -*- coding: utf-8 -*-
"""INT-645 验收补充——预览弹窗双播放模式浏览器实测（真实 Chrome）。

目标：走查音频导入页行「预览」，核对双播放模式是否走真实接口：
- 浏览器播放 → GET /audios/{id}/stream 预签名 URL + <audio>
- 实验室播放 → POST /audios/{id}/preview；停止 → POST /audios/{id}/stop-preview
另有：详情（编辑元数据）弹窗打开、深浅色截图。
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5275')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int645_wiring')
os.makedirs(OUT, exist_ok=True)


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            maj = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        maj = 0
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if maj and os.path.isdir(cache):
        cands = []
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in v.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == maj]
        if same:
            drv_path = max(same)
    s = Service(executable_path=drv_path) if drv_path else Service()
    d = webdriver.Chrome(options=o, service=s)
    d.set_page_load_timeout(60)
    return d


def goto(d, path, wait=3):
    d.get(BASE + path)
    WebDriverWait(d, 25).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def body(d):
    return d.execute_script('return document.body.textContent || ""')


def resources(d):
    return d.execute_script('return performance.getEntriesByType("resource").map(e => e.name)')


def shot(d, name):
    d.save_screenshot(os.path.join(OUT, name))
    print('[shot]', name)


def set_theme(d, dark):
    d.execute_script(
        "document.documentElement.classList.remove('light','dark');"
        f"document.documentElement.classList.add('{ 'dark' if dark else 'light' }');")
    time.sleep(0.6)


def open_row_menu(d):
    btn = None
    for xp in ["//button[contains(@aria-label,'的操作')]",
               "//button[@aria-label and contains(@aria-label,'操作')]"]:
        els = d.find_elements(By.XPATH, xp)
        if els:
            btn = els[0]
            break
    if btn is None:
        els = d.find_elements(By.XPATH, "//table//button")
        btn = els[0] if els else None
    if btn is None:
        raise AssertionError('行操作按钮未找到')
    print('[row] aria-label =', btn.get_attribute('aria-label'))
    btn.click()
    WebDriverWait(d, 6).until(lambda x: x.find_elements(By.XPATH, "//*[@role='menuitem']"))


def click_menu(d, label):
    for it in d.find_elements(By.XPATH, "//*[@role='menuitem']"):
        if label in it.text:
            it.click()
            return
    raise AssertionError('菜单项「%s」未找到' % label)


def find_play_button(d):
    for xp in ["//button[@aria-label='播放']", "//button[@aria-label='停止播放']",
               "//button[contains(@aria-label,'播放')]"]:
        els = d.find_elements(By.XPATH, xp)
        if els:
            return els[0]
    return None


def main():
    d = driver()
    results = []

    def rec(name, ok, detail=''):
        results.append((name, ok, detail))
        print(('[PASS] ' if ok else '[FAIL] ') + name + ' :: ' + str(detail)[:160])

    try:
        goto(d, '/login')
        txt = body(d)
        if '进入工作台' in txt:
            d.find_element(By.XPATH, "//button[contains(., '进入工作台')]").click()
            WebDriverWait(d, 20).until(
                lambda x: '/dashboard' in x.current_url or '/audio-import' in x.current_url)
            time.sleep(2)
        rec('AUTH_MODE=off 进入工作台', True, d.current_url)

        goto(d, '/audio-import', wait=4)
        txt = body(d)
        rec('音频列表渲染真实数据', '.wav' in txt, '')

        # ── 详情（编辑元数据）弹窗 ──
        try:
            open_row_menu(d)
            click_menu(d, '详情 / 编辑元数据')
            WebDriverWait(d, 6).until(lambda x: '编辑元数据' in body(x))
            set_theme(d, True)
            shot(d, 'int645-audio-metadata-dialog-dark.png')
            set_theme(d, False)
            rec('详情（编辑元数据）弹窗打开', True, '')
            d.find_element(By.XPATH, '//body').send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception as e:
            rec('详情（编辑元数据）弹窗打开', False, str(e)[:150])

        # ── 预览弹窗：双播放模式 ──
        try:
            open_row_menu(d)
            click_menu(d, '预览')
            WebDriverWait(d, 6).until(lambda x: '音频播放' in body(x))
            time.sleep(1)
            txt = body(d)
            rec('预览弹窗打开（音频播放）', '音频播放' in txt and '试听配置' in txt, '')
            rec('预览弹窗含「播放模式」选择', '播放模式' in txt, '')
            shot(d, 'int645-audio-preview-dialog-light.png')

            # 浏览器播放模式（默认 frontend）：点击播放
            base = set(resources(d))
            play_btn = find_play_button(d)
            rec('找到播放按钮', play_btn is not None, '')
            if play_btn:
                play_btn.click()
                time.sleep(2)
                after = set(resources(d))
                new_stream = [u for u in after - base if '/stream' in u]
                audio_els = d.execute_script('return document.querySelectorAll("audio").length')
                rec('浏览器播放：点击后走 GET /audios/{id}/stream',
                    len(new_stream) > 0, 'new_stream=%s' % str(new_stream[:2]))
                rec('浏览器播放：存在 <audio> 元素', audio_els > 0, 'audio元素数=%d' % audio_els)
                play_btn.click()  # toggle off
                time.sleep(0.5)

            # 切换实验室播放
            try:
                trig = d.find_element(By.XPATH, "//button[@aria-label='播放模式']")
            except Exception:
                trig = d.find_element(By.XPATH, "//div[@role='dialog']//button[contains(., '浏览器播放')]")
            trig.click()
            time.sleep(0.8)
            picked = False
            for el in d.find_elements(By.XPATH, "//*[@role='option']"):
                if '实验室播放' in el.text:
                    el.click()
                    picked = True
                    break
            if not picked:
                for el in d.find_elements(By.XPATH, "//*[text()='实验室播放']"):
                    el.click()
                    picked = True
                    break
            rec('切换「实验室播放」模式', picked, '')
            shot(d, 'int645-audio-preview-laboratory-light.png')

            base2 = set(resources(d))
            play_btn2 = find_play_button(d)
            play_btn2.click()
            time.sleep(2)
            after2 = set(resources(d))
            new_preview = [u for u in after2 - base2 if '/preview' in u]
            rec('实验室播放：点击后走 POST /audios/{id}/preview',
                len(new_preview) > 0, 'new_preview=%s' % str(new_preview[:2]))

            base3 = set(resources(d))
            play_btn2.click()  # 停止
            time.sleep(2)
            after3 = set(resources(d))
            new_stop = [u for u in after3 - base3 if 'stop-preview' in u]
            rec('实验室播放：停止走 POST /audios/{id}/stop-preview',
                len(new_stop) > 0, 'new_stop=%s' % str(new_stop[:2]))

            set_theme(d, True)
            shot(d, 'int645-audio-preview-laboratory-dark.png')
            set_theme(d, False)
            d.find_element(By.XPATH, '//body').send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception as e:
            rec('预览弹窗双播放模式', False, str(e)[:200])

        sev = []
        for e in d.get_log('browser'):
            if e.get('level') == 'SEVERE':
                sev.append(e.get('message', ''))
        rec('console 无 SEVERE', len(sev) == 0, 'count=%d: %s' % (len(sev), str(sev[:1])))
    finally:
        try:
            d.quit()
        except Exception:
            pass

    print('')
    print('RESULT: %d/%d passed' % (sum(1 for _, ok, _ in results if ok), len(results)))
    for name, ok, detail in results:
        print(('  OK ' if ok else '  FAIL ') + name + ' | ' + str(detail)[:120])


if __name__ == '__main__':
    main()
