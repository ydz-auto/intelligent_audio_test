# -*- coding: utf-8 -*-
"""INT-1538 P1-5：浏览器播放「暂停冻结 / 继续前进」按时间采样取证（不依赖按钮 aria 状态）。

诊断 resolver 绕行 rustfs:9000；输出 evidence_int1538_pause.json + s22/s24 截图。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By

GROUP = os.environ.get('CASE_GROUP', '接线测试_INT1538_播放器复测组')
RESOLVER = os.environ.get('CHROME_RESOLVER', 'MAP rustfs 127.0.0.1')
OUT = {'resolver': RESOLVER}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=120, interval=1.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception as e:
            last = e
        time.sleep(interval)
    if last:
        raise last
    return None


def pt():
    e = [x for x in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(x)]
    return e[-1].text.strip() if e else ''


def ctrl_buttons():
    return [b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() in ('播放', '暂停', '停止')]


def play_btn():
    bs = [b for b in ctrl_buttons() if (b.text or '').strip() in ('播放', '暂停')]
    return bs[0] if bs else None


def sample(seconds=3.0, interval=0.4):
    out = []
    end = time.time() + seconds
    while time.time() < end:
        out.append(pt())
        time.sleep(interval)
    return out


d = None
try:
    import winreg
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    o = Options()
    o.binary_location = L.CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'):
        o.add_argument(a)
    if RESOLVER:
        o.add_argument('--host-resolver-rules=%s' % RESOLVER)
    o.add_experimental_option('excludeSwitches', ['enable-logging'])
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': L.FETCH_PATCH})

    def goto(p, tries=3):
        for _ in range(tries):
            try:
                d.get(L.BASE + p)
                return
            except Exception:
                time.sleep(3)
        raise RuntimeError('goto failed ' + p)

    goto('/testcases')
    time.sleep(8)
    if '/login' in d.current_url:
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '进入' in (b.text or '') or '登录' in (b.text or ''):
                L.js_click(d, b)
                time.sleep(4)
                break
        goto('/testcases')
        time.sleep(8)
    # 分组 facet 圈定（第二轮的稳定路径），失败再退回「加载更多」
    faceted = False
    try:
        rst = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '重置'), None)
        if rst:
            L.js_click(d, rst)
            time.sleep(4)
        trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                   if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
        L.js_click(d, trig)
        time.sleep(1.2)
        opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                  if vis(b) and GROUP in (b.text or '')), None), 20)
        L.js_click(d, opt)
        time.sleep(5)
        faceted = True
    except Exception:
        faceted = False
    if not faceted or GROUP not in L.body_text(d):
        for _ in range(12):
            if GROUP in L.body_text(d):
                break
            more = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and '加载更多' in (b.text or '')), None)
            if not more:
                break
            L.js_click(d, more)
            time.sleep(6)
    OUT['group_visible'] = GROUP in L.body_text(d)
    h = retry(lambda: d.execute_script("""
        const g = arguments[0];
        for (const el of document.querySelectorAll('div')) {
          const cls = (el.className || '').toString();
          if (cls.includes('cursor-pointer') && cls.includes('justify-between') &&
              (el.innerText || '').trim().startsWith(g)) { return el; }
        }
        return null;
    """, GROUP), 60)
    d.execute_script('arguments[0].click();', h)
    btn = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)), None), 120)
    L.js_click(d, btn)
    L.wait_dialog(d, '音频试听配置', 30)
    time.sleep(1)
    L.js_click(d, next((x for x in d.find_elements(By.XPATH, "//label[contains(normalize-space(.), '浏览器播放')]") if vis(x)), None))
    time.sleep(0.5)
    for _attempt in range(3):
        st = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '开始试听'), None)
        if st is not None:
            L.js_click(d, st)
        end = time.time() + 30
        while time.time() < end and not pt():
            time.sleep(0.5)
        if pt():
            break
        time.sleep(1)
    # 等播放器就绪
    end = time.time() + 40
    while time.time() < end and not pt():
        time.sleep(0.5)
    OUT['time_ready'] = pt()
    OUT['stage_body'] = L.body_text(d)[-300:]
    # 1) 点播放 → 采样 3s（应前进）
    if play_btn() is not None:
        L.js_click(d, play_btn())
    OUT['progress_sequence'] = sample(3.0)
    L.shot(d, 's21_player_playing_light')
    # 2) 再点 → 暂停，采样 3s（应冻结在非零）
    if play_btn() is not None:
        L.js_click(d, play_btn())
    OUT['pause_sequence'] = sample(3.0)
    L.shot(d, 's22_player_paused_light')
    ps = OUT['pause_sequence']
    OUT['pause_holds'] = len(set(ps)) == 1 and not ps[0].startswith('00:00 /')
    # 3) 再点 → 继续，采样到结束
    if play_btn() is not None:
        L.js_click(d, play_btn())
    OUT['resume_sequence'] = sample(4.5, 0.3)
    OUT['ended'] = any(t.startswith('00:00 /') for t in OUT['resume_sequence'][1:])
    L.shot(d, 's23_player_ended_light')
    OUT['alerts'] = [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]
    OUT['console'] = [x.get('message', '')[:160] for x in d.get_log('browser') if 'audios' in x.get('message', '') or 'rustfs' in x.get('message', '')]
    # 4) 深色播放中
    L.apply_theme(d, 'dark')
    time.sleep(0.8)
    if play_btn() is not None:
        L.js_click(d, play_btn())
    time.sleep(1.2)
    OUT['dark_time_playing'] = pt()
    OUT['dark_class'] = d.execute_script('return document.documentElement.className')
    OUT['dark_bg'] = d.execute_script('return getComputedStyle(document.body).backgroundColor')
    L.shot(d, 's24_player_playing_dark')
    OUT['alerts_dark'] = [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]
finally:
    L.save_evidence('pause_evidence_under_artifacts', OUT)
    with open(os.path.join(L.HERE, 'evidence_int1538_pause.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    try:
        d.quit()
    except Exception:
        pass
