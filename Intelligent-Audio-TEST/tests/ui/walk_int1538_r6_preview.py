# -*- coding: utf-8 -*-
"""INT-1538 P1-5 复测（INT-1710 闭环后，默认环境，不加 host-resolver-rules）。

目标：在 15173 真实默认环境下重走「用例行 → 预览音频 → 音频试听配置 → 浏览器播放 →
开始试听」，取证成功态：
  - 无 ERR_NAME_NOT_RESOLVED / 无 SEVERE 控制台噪声
  - preview 接口返回的 audio_stream_url(s) host 为 127.0.0.1:9000（容器内 rustfs:9000 的
    外部可达地址，INT-1719 OSS_PUBLIC_ENDPOINT）
  - <audio> src / duration / readyState / error
  - 进度推进、暂停冻结、续播、播放结束
  - 浅/深截图
夹具：自建组 + 1 条用例（config 克隆真实 2 轮用例，音频统一切到 2358 url_src_A_6.wav）。
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium import webdriver

TAG = time.strftime('%m%d%H%M%S')
GROUP = '接线测试_INT1538_R6组_' + TAG
NAME = '接线测试_INT1538_R6用例_' + TAG
# 默认环境：不注入任何 host-resolver-rules
RESOLVER = ''
AUDIO_ID = 2358
AUDIO_NAME = 'url_src_A_6.wav'
BASE_CASE = '71f2ce67-10f8-4b80-931e-8616353366e2'  # 真实 2 轮用例（HJ049 复制体），只用于克隆 config
OUT = {'tag': TAG, 'group': GROUP, 'case': NAME, 'resolver': RESOLVER or '(none/default)'}


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


def build_driver():
    o = Options()
    o.binary_location = L.CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'):
        o.add_argument(a)
    assert RESOLVER == ''
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


def media():
    return d.execute_script("""
        const a = document.querySelector('audio');
        if (!a) return null;
        return {src: a.currentSrc || a.src || '', paused: a.paused,
                t: Math.round(a.currentTime*100)/100,
                dur: (a.duration && !isNaN(a.duration)) ? Math.round(a.duration*100)/100 : null,
                readyState: a.readyState, networkState: a.networkState,
                error: a.error ? {code: a.error.code, message: a.error.message} : null};
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


def click_pause():
    for cand in ('暂停', 'Pause', 'pause'):
        if click_label(cand):
            return cand
    b = next((x for x in d.find_elements(By.TAG_NAME, 'button')
              if vis(x) and ('暂停' in (x.text or '') or 'pause' in (x.get_attribute('aria-label') or '').lower())), None)
    if b is not None:
        L.js_click(d, b)
        return 'text:' + (b.text or '')
    return None


d = build_driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(4)

    OUT['bundle'] = d.execute_script(
        "return Array.from(document.scripts).map(s=>s.src).filter(Boolean).join(',')") or ''
    OUT['health'] = d.execute_async_script("""
        const done = arguments[arguments.length-1];
        fetch('/health').then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """)

    # ---- 夹具：真实 2 轮用例 config 克隆，音频统一切到 2358 ----
    st, p, raw = L.api_json(d, '/audios/%d' % AUDIO_ID)
    adata = ((p or {}).get('data') or {})
    OUT['audio_2358'] = {'status': st, 'name': adata.get('name'), 'duration': adata.get('duration'),
                         'audio_type': adata.get('audio_type'), 'file_path': adata.get('file_path')}
    st, p, raw = L.api_json(d, '/testcases/' + BASE_CASE)
    cfg = ((p or {}).get('data') or {}).get('config') or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    n_patched = 0
    for rd in (cfg.get('rounds') or []):
        for a in (rd.get('audios') or []):
            a['audio_id'] = AUDIO_ID
            a['audio_name'] = AUDIO_NAME
            n_patched += 1
    OUT['base_case'] = BASE_CASE
    OUT['audio_patched'] = n_patched

    st, payload, raw = L.api_json(d, '/groups', 'POST',
                                  {'name': GROUP, 'description': 'INT-1538 R6 P1-5 复测组', 'algorithm_type': ''})
    OUT['create_group'] = {'status': st, 'body': raw[:200]}
    GID = str(((payload or {}).get('data') or {}).get('id') or '')
    st, payload, raw = L.api_json(d, '/testcases', 'POST',
                                  {'name': NAME, 'description': 'INT-1538 R6 P1-5 播放器复测夹具',
                                   'group_id': GID, 'config': cfg})
    OUT['create_case'] = {'status': st, 'body': raw[:200]}
    CID = str(((payload or {}).get('data') or {}).get('id') or '')

    # 接口层：试听配置端点（浏览器播放）返回的流地址 host（默认环境）
    OUT['preview_api'] = []
    for body in ({'playback_mode': 'frontend'},
                 {'playback_mode': 'frontend', 'audio_ids': [AUDIO_ID]},
                 {'audio_ids': [AUDIO_ID], 'playback_mode': 'frontend'}):
        st, p, raw = L.api_json(d, '/testcases/%s/preview' % CID, 'POST', body)
        OUT['preview_api'].append({'body': body, 'status': st, 'resp': raw[:1500]})

    # ---- UI 链路 ----
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
    L.shot(d, 's40_preview_config_light_default')
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
    if not player_time():
        raise RuntimeError('player not ready')

    OUT['fetch_preview'] = [
        {'method': e.get('method'), 'url': (e.get('url') or '')[:160], 'status': e.get('status'),
         'resp': (e.get('resBody') or '')[:2000]}
        for e in L.fetch_log(d) if '/preview' in (e.get('url') or '') or '/audios/' in (e.get('url') or '')
    ]
    # 解析预览响应里的流地址 host
    hosts = set()
    urls = []
    for e in L.fetch_log(d):
        txt = e.get('resBody') or ''
        for m in re.finditer(r'https?://[^"\'\\\s]+', txt):
            u = m.group(0)
            urls.append(u)
            mm = re.match(r'https?://([^/]+)', u)
            if mm:
                hosts.add(mm.group(1))
    OUT['preview_urls'] = urls[:20]
    OUT['preview_url_hosts'] = sorted(hosts)

    # 流地址 host 由上面 fetch_log/resBody 解析；宿主侧 Range 取证用 curl（页内 fetch 会命中
    # rustfs 的 CORS 预检失败，属探测手段噪声，不掺进控制台结论）。

    ready = retry(lambda: media(), 40)
    OUT['media_ready'] = ready
    OUT['console_at_ready'] = d.get_log('browser')[-40:]
    d.get_log('browser')

    # 1) 播放推进（快采样：夹具只有 4s，采样过久会落到片尾导致暂停取不到中段）
    if media() and media()['paused']:
        OUT['clicked_play'] = click_label('播放')
    t0 = time.time()
    while time.time() - t0 < 6:
        m = media()
        if m and not m['paused'] and m['t'] >= 0.6:
            break
        time.sleep(0.1)
    playing = sample_media(0.45, 0.15)
    OUT['playing_sequence'] = playing
    OUT['playing_advances'] = (len(set([x['media']['t'] for x in playing if x['media']])) > 1
                              and not playing[-1]['media']['paused'])
    L.shot(d, 's41_player_playing_light_default')

    # 2) 中段暂停（截图后立即点，避免 4s 播完）
    OUT['clicked_pause'] = click_pause()
    paused = sample_media(2.4)
    OUT['paused_sequence'] = paused
    OUT['paused_at'] = player_time()
    ts = [x['media']['t'] for x in paused if x['media']]
    OUT['pause_holds'] = (bool(paused) and paused[-1]['media']['paused'] is True
                          and len(set(ts)) == 1 and ts[0] > 0
                          and paused[-1]['media']['dur'] and ts[0] <= paused[-1]['media']['dur'] - 0.5)
    L.shot(d, 's42_player_paused_light_default')
    OUT['paused_buttons'] = [
        {'aria': x.get_attribute('aria-label'), 'text': (x.text or '').strip()[:20]}
        for x in d.find_elements(By.TAG_NAME, 'button') if vis(x)
    ][-6:]
    L.apply_theme(d, 'dark')
    time.sleep(1)
    L.shot(d, 's43_player_paused_dark_default')
    OUT['dark_class'] = d.execute_script('return document.documentElement.className')
    OUT['dark_bg'] = d.execute_script('return getComputedStyle(document.body).backgroundColor')
    L.apply_theme(d, 'light')
    time.sleep(0.5)

    # 3) 续播
    OUT['clicked_resume'] = click_label('播放')
    resumed = sample_media(2.0)
    OUT['resumed_sequence'] = resumed
    rt = [x['media']['t'] for x in resumed if x['media']]
    OUT['resume_advances'] = len(set(rt)) > 1
    L.shot(d, 's44_player_resumed_light_default')

    # 4) 播完
    end = time.time() + 20
    while time.time() < end:
        m = media()
        if m and m['dur'] and m['t'] >= m['dur'] - 0.1:
            break
        time.sleep(0.4)
    OUT['final_media'] = media()
    OUT['final_time'] = player_time()
    OUT['ended'] = bool(OUT['final_media'] and OUT['final_media']['dur']
                        and OUT['final_media']['t'] >= OUT['final_media']['dur'] - 0.3)
    # 结束态显示口径（trigger 提示第 2 点）：播完瞬间 UI 时间是停在片尾还是归零，单独记录
    OUT['post_end_ui_series'] = []
    for _ in range(4):
        m = media() or {}
        OUT['post_end_ui_series'].append({'ui': player_time(), 'media_t': m.get('t'),
                                          'paused': m.get('paused')})
        time.sleep(0.5)
    L.shot(d, 's45_player_ended_light_default')

    # 5) 结束后点「播放」的口径（trigger 提示第 2 点，单独记录，不混入 P1-5 结论）
    OUT['replay_click'] = click_label('播放')
    OUT['replay_sequence'] = []
    end = time.time() + 10
    while time.time() < end:
        m = media() or {}
        OUT['replay_sequence'].append({'ui': player_time(), 't': m.get('t'), 'paused': m.get('paused')})
        if m.get('paused') and m.get('t') and m.get('dur') and m['t'] >= m['dur'] - 0.2 and len(OUT['replay_sequence']) > 2:
            break
        time.sleep(0.4)
    OUT['post_replay_ui_series'] = []
    for _ in range(4):
        m = media() or {}
        OUT['post_replay_ui_series'].append({'ui': player_time(), 'media_t': m.get('t'),
                                             'paused': m.get('paused')})
        time.sleep(0.5)
    OUT['alerts'] = [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]

    # 5) 控制台判定
    logs = d.get_log('browser')
    OUT['console_severe'] = [x for x in logs if x.get('level') == 'SEVERE']
    OUT['console_name_not_resolved'] = [x for x in logs if 'ERR_NAME_NOT_RESOLVED' in (x.get('message') or '')]
    OUT['console_total'] = len(logs)

    # 清理
    if CID:
        st, _p, raw = L.api_json(d, '/testcases/' + CID, 'DELETE')
        OUT['cleanup_case'] = st
    if GID:
        st, _p, raw = L.api_json(d, '/groups/' + GID, 'DELETE')
        OUT['cleanup_group'] = st
finally:
    L.save_evidence('evidence_int1538_r6_preview_default', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
