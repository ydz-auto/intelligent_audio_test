# -*- coding: utf-8 -*-
"""INT-1538 返工 P2-5：试听播放器暂停取证重做（阶段标注按实测行为，不按点击顺序）。

终审指出的问题：上一轮 evidence_int1538_pause.json 里 progress_sequence 其实是暂停段、
pause_sequence 才是播放段，且 s13/s22 命名与实际状态相反。
本脚本改为「先观测是否推进，再按行为打标签」，并在中段（约 00:02）点暂停取证。

夹具：自建组 + 1 条用例（config 克隆自真实用例 d2b8a465 的 2 轮 2 音频，只读引用音频 2099/2064）。
"""
import json
import os
import re
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium import webdriver

TAG = time.strftime('%m%d%H%M%S')
GROUP = '接线测试_INT1538_R5pause组_' + TAG
NAME = '接线测试_INT1538_R5pause用例_' + TAG
RESOLVER = os.environ.get('CHROME_RESOLVER', 'MAP rustfs 127.0.0.1')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = {'tag': TAG, 'group': GROUP, 'case': NAME, 'resolver': RESOLVER}


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


def player_time():
    els = [e for e in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(e)]
    return els[-1].text.strip() if els else ''


def secs(t):
    m = re.match(r'(\d+):(\d+)', t or '')
    return int(m.group(1)) * 60 + int(m.group(2)) if m else -1


def ctrl():
    return next((b for b in d.find_elements(By.TAG_NAME, 'button')
                 if vis(b) and (b.get_attribute('aria-label') or '') in ('播放', '暂停')), None)


def sample(seconds=2.0, interval=0.35):
    out = []
    end = time.time() + seconds
    while time.time() < end:
        out.append(player_time())
        time.sleep(interval)
    return out


def advancing(seq):
    vals = [x for x in seq if x]
    return len(set(vals)) > 1


def build_driver():
    o = Options()
    o.binary_location = L.CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'):
        o.add_argument(a)
    if RESOLVER:
        o.add_argument('--host-resolver-rules=%s' % RESOLVER)
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


d = build_driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(4)

    # P2-4：/health 取根路径原文（上一轮取成 /api/v1/health → {"detail":"Not Found"}）
    OUT['health'] = d.execute_async_script("""
        const done = arguments[arguments.length-1];
        fetch('/health').then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """)

    cfg = json.load(open(os.path.join(HERE, '_real_case_cfg.json'), encoding='utf-8'))['config']
    # 真实库绝大多数音频的预签名对象已 404（旧盘符 key，见 INT-1656/rustfs 数据缺口）；
    # 本 run 实测仅 2358（url_src_A.wav, 4.0s, dry）能取到 206 实体，夹具统一指向它。
    n_patched = 0
    for rd in (cfg.get('rounds') or []):
        for a in (rd.get('audios') or []):
            a['audio_id'] = 2358
            a['audio_name'] = 'url_src_A.wav'
            n_patched += 1
    OUT['audio_patched'] = n_patched
    st, payload, raw = L.api_json(d, '/groups', 'POST',
                                  {'name': GROUP, 'description': 'INT-1538 P2-5 播放器取证组', 'algorithm_type': ''})
    OUT['create_group'] = {'status': st, 'body': raw[:200]}
    GID = str(((payload or {}).get('data') or {}).get('id') or '')
    st, payload, raw = L.api_json(d, '/testcases', 'POST',
                                  {'name': NAME, 'description': 'INT-1538 P2-5 播放器取证夹具',
                                   'group_id': GID, 'config': cfg})
    OUT['create_case'] = {'status': st, 'body': raw[:200]}
    CID = str(((payload or {}).get('data') or {}).get('id') or '')

    # 圈定自建组
    d.get(L.BASE + '/testcases')
    time.sleep(5)
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
          const cls = (el.className || '').toString();
          if (cls.includes('cursor-pointer') && cls.includes('justify-between') &&
              (el.innerText || '').trim().startsWith(arguments[0])) return el;
        }
        return null;""", GROUP), 40)
    L.js_click(d, hdr)
    time.sleep(3)
    L.clear_fetch_log(d)
    pv = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)), None), 60)
    L.js_click(d, pv)
    L.wait_dialog(d, '音频试听配置', 30)
    time.sleep(1)
    L.shot(d, 's30_preview_config_light')
    lab = next((x for x in d.find_elements(By.XPATH, "//label[contains(normalize-space(.), '浏览器播放')]") if vis(x)), None)
    L.js_click(d, lab)
    time.sleep(0.5)
    for _ in range(3):
        stt = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '开始试听'), None)
        if stt is not None:
            L.js_click(d, stt)
        end = time.time() + 40
        while time.time() < end and not player_time():
            time.sleep(0.5)
        if player_time():
            break
        time.sleep(1)
    OUT['time_ready'] = player_time()
    OUT['stream_fetch'] = [(e.get('method'), (e.get('url') or '')[:90], e.get('status'))
                           for e in L.fetch_log(d) if '/audios/' in (e.get('url') or '')]
    if not player_time():
        raise RuntimeError('player not ready')

    # 1) 播放器状态以 <audio> 元素为准，避免按钮 aria 与实际状态不一致导致阶段标反
    ready = retry(lambda: d.execute_script("""
        const a = document.querySelector('audio');
        if (!a || !a.duration || isNaN(a.duration)) return null;
        return {dur: a.duration, paused: a.paused, t: a.currentTime};
        """), 40)
    OUT['media_ready'] = ready

    def media():
        return d.execute_script("""
            const a = document.querySelector('audio');
            if (!a) return null;
            return {paused: a.paused, t: round3(a.currentTime), dur: round3(a.duration)};
            function round3(x){ return Math.round(x*100)/100; }
            """)

    def sample_media(seconds=2.0, interval=0.3):
        out = []
        end = time.time() + seconds
        while time.time() < end:
            out.append({'ui': player_time(), 'media': media()})
            time.sleep(interval)
        return out

    def click_label(label):
        b = next((x for x in d.find_elements(By.TAG_NAME, 'button')
                  if vis(x) and (x.get_attribute('aria-label') or '') == label), None)
        if b is None:
            return False
        L.js_click(d, b)
        return True

    OUT['player_buttons'] = None  # 播放中枚举全部按钮太慢会吃掉片段时长，暂停后再取

    def click_pause():
        """暂停按钮的 aria/文案按实现取值；先按语义找，再退回 aria 含 pause。"""
        for cand in ('暂停', 'Pause', 'pause'):
            if click_label(cand):
                return cand
        b = next((x for x in d.find_elements(By.TAG_NAME, 'button')
                  if vis(x) and ('暂停' in (x.text or '') or 'pause' in (x.get_attribute('aria-label') or '').lower())), None)
        if b is not None:
            L.js_click(d, b)
            return 'text:' + (b.text or '')
        return None

    # 起播
    if media() and media()['paused']:
        OUT['clicked_play'] = click_label('播放')
    # 等推进到中段
    t0 = time.time()
    while time.time() - t0 < 6:
        m = media()
        if m and not m['paused'] and m['t'] >= 0.8:
            break
        time.sleep(0.15)
    playing = sample_media(0.7)
    OUT['playing_sequence'] = playing
    OUT['playing_advances'] = (len(set([x['media']['t'] for x in playing if x['media']])) > 1
                              and not playing[-1]['media']['paused'])
    L.shot(d, 's31_player_playing_light')

    # 2) 中段暂停（按按钮语义点「暂停」；pause_holds 要求冻结在段中，不能在片尾）
    OUT['clicked_pause'] = click_pause()
    paused = sample_media(2.4)
    OUT['paused_sequence'] = paused
    OUT['paused_at'] = player_time()
    ts = [x['media']['t'] for x in paused if x['media']]
    OUT['pause_holds'] = (bool(paused) and paused[-1]['media']['paused'] is True
                          and len(set(ts)) == 1 and ts[0] > 0
                          and paused[-1]['media']['dur'] and ts[0] <= paused[-1]['media']['dur'] - 0.5)
    L.shot(d, 's32_player_paused_light')
    OUT['player_buttons'] = [
        {'aria': x.get_attribute('aria-label'), 'text': (x.text or '').strip()[:20]}
        for x in d.find_elements(By.TAG_NAME, 'button') if vis(x)
    ][-8:]
    L.apply_theme(d, 'dark')
    time.sleep(1)
    L.shot(d, 's33_player_paused_dark')
    OUT['dark_class'] = d.execute_script('return document.documentElement.className')
    OUT['dark_bg'] = d.execute_script('return getComputedStyle(document.body).backgroundColor')
    L.apply_theme(d, 'light')
    time.sleep(0.5)

    # 3) 继续播放
    OUT['clicked_resume'] = click_label('播放')
    resumed = sample_media(2.0)
    OUT['resumed_sequence'] = resumed
    rt = [x['media']['t'] for x in resumed if x['media']]
    OUT['resume_advances'] = len(set(rt)) > 1
    L.shot(d, 's34_player_resumed_light')

    # 4) 播完
    end = time.time() + 20
    while time.time() < end:
        m = media()
        if m and m['dur'] and m['t'] >= m['dur'] - 0.2:
            break
        time.sleep(0.4)
    OUT['final_media'] = media()
    OUT['final_time'] = player_time()
    OUT['ended'] = bool(OUT['final_media'] and OUT['final_media']['dur']
                        and OUT['final_media']['t'] >= OUT['final_media']['dur'] - 0.3)
    L.shot(d, 's35_player_ended_light')
    OUT['alerts'] = [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]

    # 清理
    if CID:
        st, _p, raw = L.api_json(d, '/testcases/' + CID, 'DELETE')
        OUT['cleanup_case'] = st
    if GID:
        st, _p, raw = L.api_json(d, '/groups/' + GID, 'DELETE')
        OUT['cleanup_group'] = st
finally:
    L.save_evidence('evidence_int1538_pause', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
