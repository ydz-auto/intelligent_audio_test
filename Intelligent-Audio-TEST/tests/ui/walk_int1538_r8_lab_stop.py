# -*- coding: utf-8 -*-
"""INT-1538 R8 补证：音频库源（抽屉音频行「试听」）实验室播放的「停止」按钮 → POST /audios/{id}/stop-preview。

上一轮 B 段落点到「停止」时音频（4s）已按墙钟自然结束（播放器已在结束态），handleStop 因
wasPlaying=false 不再发停止请求，导致 B_fetch_stop 为空。本脚本在播放中（约 1.5s）点停止，
并额外记录本轮全部 /audios/ 请求（含可能的自然结束 stop）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium import webdriver

TAG = time.strftime('%m%d%H%M%S')
GROUP = '接线测试_INT1538_R8S组_' + TAG
NAME = '接线测试_INT1538_R8S用例_' + TAG
AUDIO_ID = 2358
AUDIO_NAME = 'url_src_A.wav'
BASE_CASE = '92b93231-1f37-4f89-ae6b-cd2a2b945fb9'
OUT = {'tag': TAG, 'group': GROUP, 'case': NAME}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=60, interval=0.5):
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


def build_driver():
    o = Options()
    o.binary_location = L.CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'):
        o.add_argument(a)
    o.add_experimental_option('excludeSwitches', ['enable-logging'])
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
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
    drv = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(200)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': L.FETCH_PATCH})
    return drv


def player_time():
    els = [e for e in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(e)]
    return els[-1].text.strip() if els else ''


def find_by_aria(label):
    for dlg in reversed(L.dialogs(d)):
        b = d.execute_script(
            """const root=arguments[0],n=arguments[1];
               for (const x of root.querySelectorAll('button[aria-label="'+n+'"]'))
                 if (x.getClientRects().length>0) return x; return null;""", dlg, label)
        if b:
            return b
    return None


def find_preview_for(name, label='预览音频'):
    return d.execute_script(
        """const name=arguments[0],label=arguments[1];
           let best=null,bd=99;
           for (const b of document.querySelectorAll('button[aria-label="'+label+'"]')) {
             if (!b.getClientRects().length) continue;
             let el=b;
             for (let i=1;i<=10&&el;i++){
               if ((el.innerText||'').includes(name)) { if (i<bd){best=b;bd=i;} break; }
               el=el.parentElement;
             }
           }
           return best;""", name, label)


def slim(entries, needle='/audios/'):
    return [{'method': e.get('method'), 'url': (e.get('url') or '')[:160], 'status': e.get('status'),
             't': e.get('t'),
             'reqBody': (e.get('reqBody') or '')[:400], 'resBody': (e.get('resBody') or '')[:600]}
            for e in entries if needle in (e.get('url') or '')]


d = build_driver()
CID = GID = ''
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(4)
    st, p, raw = L.api_json(d, '/groups', 'POST',
                            {'name': GROUP, 'description': 'R8 stop 补证', 'algorithm_type': ''})
    GID = str(((p or {}).get('data') or {}).get('id') or '')
    st, p, raw = L.api_json(d, '/testcases/' + BASE_CASE)
    cfg = ((p or {}).get('data') or {}).get('config') or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    for rd in cfg.get('rounds') or []:
        for a in rd.get('audios') or []:
            a['audio_id'] = AUDIO_ID
            a['audio_name'] = AUDIO_NAME
            a['playback_device_id'] = 1
            a['playback_device_name'] = '音箱0°'
    st, p, raw = L.api_json(d, '/testcases', 'POST',
                            {'name': NAME, 'description': 'R8 stop 补证', 'group_id': GID, 'config': cfg})
    CID = str(((p or {}).get('data') or {}).get('id') or '')
    OUT['fixture'] = {'group': GID, 'case': CID, 'status': st}

    d.get(L.BASE + '/testcases')
    time.sleep(5)
    # 分组 facet
    rst = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == '重置'), None), 20)
    if rst:
        L.js_click(d, rst)
        time.sleep(2)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button, [role='option']")
                              if vis(x) and GROUP in (x.text or '')), None), 20)
    L.js_click(d, opt)
    time.sleep(4)
    hdr = retry(lambda: d.execute_script("""
        for (const el of document.querySelectorAll('div')) {
          const cls=(el.className||'').toString();
          if (cls.includes('cursor-pointer')&&cls.includes('justify-between')&&
              (el.innerText||'').trim().startsWith(arguments[0])) return el;
        } return null;""", GROUP), 40)
    L.js_click(d, hdr)
    time.sleep(3)

    ed = retry(lambda: find_preview_for(NAME, '编辑用例'), 40)
    L.js_click(d, ed)
    L.wait_dialog(d, '编辑测试用例', 30)
    time.sleep(1.2)
    tab = retry(lambda: next((t for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']")
                              if vis(t) and (t.text or '').strip() == '音频列表'), None), 20)
    L.js_click(d, tab)
    time.sleep(2)
    aud = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='试听']")
                              if vis(b)), None), 30)
    L.js_click(d, aud)
    L.wait_dialog(d, '音频试听配置', 30)
    time.sleep(0.6)
    lab = retry(lambda: next((x for x in d.find_elements(
        By.XPATH, "//label[contains(normalize-space(.), '实验室播放')]") if vis(x)), None), 20)
    L.js_click(d, lab)
    time.sleep(0.5)
    stt = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                              if vis(x) and (x.text or '').strip() == '开始试听'), None), 20)
    L.js_click(d, stt)
    time.sleep(1.0)
    play = retry(lambda: find_by_aria('播放'), 20)
    L.js_click(d, play)
    time.sleep(1.0)
    OUT['player_before_stop'] = player_time()
    OUT['player_text_before_stop'] = (L.dialogs(d)[-1].text or '')[:600] if L.dialogs(d) else ''
    L.shot(d, 'r8_S1_playing_light')
    OUT['player_at_click'] = player_time()
    t_click = time.time()
    OUT['t_click_ms'] = int(t_click * 1000)
    stp = retry(lambda: find_by_aria('停止'), 15)
    L.js_click(d, stp)
    time.sleep(2.5)
    OUT['click_to_log_s'] = round(time.time() - t_click, 2)
    OUT['player_after_stop'] = player_time()
    OUT['player_text_after_stop'] = (L.dialogs(d)[-1].text or '')[:600] if L.dialogs(d) else ''
    L.shot(d, 'r8_S3_stopped_light')
    L.apply_theme(d, 'dark')
    time.sleep(0.6)
    L.shot(d, 'r8_S2_stopped_dark')
    L.apply_theme(d, 'light')
    OUT['audios_fetch_all'] = slim(L.fetch_log(d))
    logs = d.get_log('browser')
    OUT['console_severe'] = [x for x in logs if x.get('level') == 'SEVERE']
finally:
    try:
        if CID:
            s1, _p, _r = L.api_json(d, '/testcases/' + CID, 'DELETE')
            s2, _p, r2 = L.api_json(d, '/testcases/' + CID + '/purge', 'DELETE')
            OUT['cleanup_case'] = {'delete': s1, 'purge': s2, 'body': r2[:100]}
        if GID:
            s3, _p, _r = L.api_json(d, '/groups/' + GID, 'DELETE')
            OUT['cleanup_group'] = s3
        st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + TAG)
        OUT['alive_after'] = [x.get('id') for x in (((p or {}).get('data') or {}).get('items') or [])]
    except Exception as e:
        OUT['cleanup_error'] = str(e)
    L.save_evidence('evidence_int1538_r8_lab_stop', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
