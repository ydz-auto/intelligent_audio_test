# -*- coding: utf-8 -*-
"""INT-1538 终审退回补测（round 3）：INT-1656 修好 rustfs CORS 后，复测浏览器播放成功态。

覆盖终审不通过清单 P1-5：
- 浏览器播放：真实流 → loadedmetadata 真实时长（4.00s）→ 进度前进 → 暂停/继续 → 播完归零；
- 实验室播放：仍应 400（宿主 Audiosrv 楔死，INT-1656 待负责人管理员处置），记录失败态；
- 浅/深截图。

夹具用例由本脚本的 mk_fixture 建立（接线测试_ 前缀），收尾由 cleanup 脚本清理。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

NAME = os.environ.get('CASE_NAME', '接线测试_INT1538_播放器复测_case')
GROUP = os.environ.get('CASE_GROUP', '接线测试_INT1538_播放器复测组')
CASE_ID = os.environ.get('CASE_ID', '')
# 诊断用：MAP rustfs 127.0.0.1 让浏览器能解析网关返回的内部主机名（环境缺口绕行取证，非改代码）
RESOLVER = os.environ.get('CHROME_RESOLVER', '')
TAG = os.environ.get('EVIDENCE_TAG', 'round3')
SHOT_PREFIX = os.environ.get('SHOT_PREFIX', 's0')
OUT = {'case_name': NAME, 'case_id': CASE_ID, 'group': GROUP, 'resolver': RESOLVER, 'shot_prefix': SHOT_PREFIX}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.5):
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


def shot(name):
    if SHOT_PREFIX != 's0' and name.startswith('s0'):
        name = SHOT_PREFIX + name[2:]
    return L.shot(d, name)


def alerts():
    return [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]


def player_time():
    els = [e for e in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(e)]
    return els[-1].text.strip() if els else ''


def play_btn():
    return next((b for b in d.find_elements(By.TAG_NAME, 'button')
                 if vis(b) and (b.get_attribute('aria-label') or '') in ('播放', '暂停')), None)


def search_case():
    """按分组视图圈定自建分组：现点「加载更多」把全部分组拉出来，再展开目标分组。"""
    rst = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '重置'), None)
    if rst:
        L.js_click(d, rst)
        time.sleep(4)
    # 分组按用例数降序分页，自建 1 条的组在最后 → 先加载更多
    for _ in range(8):
        if GROUP in L.body_text(d):
            break
        more = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                     if vis(b) and '加载更多' in (b.text or '')), None)
        if not more:
            break
        L.js_click(d, more)
        time.sleep(4)
    OUT['group_visible'] = GROUP in L.body_text(d)
    # 展开分组（组头是 div.flex.cursor-pointer.items-center.justify-between）
    def find_header():
        return d.execute_script("""
            const g = arguments[0];
            for (const el of document.querySelectorAll('div')) {
              const cls = (el.className || '').toString();
              if (cls.includes('cursor-pointer') && cls.includes('justify-between') &&
                  (el.innerText || '').trim().startsWith(g)) { return el; }
            }
            return null;
        """, GROUP)

    def previews():
        return [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)]

    h = retry(find_header, 25)
    for _round in range(3):
        if previews():
            break
        h = find_header() or h
        d.execute_script('arguments[0].click();', h)
        # 组内用例懒加载（后端列表在这套 docker 栈上可能 30s+）
        end = time.time() + 60
        while time.time() < end and not previews():
            time.sleep(1.5)


def open_preview():
    b = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)), None), 30)
    L.js_click(d, b)
    w = L.wait_dialog(d, '音频试听配置', 25)
    time.sleep(1)
    return w


def close_all_dialogs():
    for _ in range(4):
        ds = L.dialogs(d)
        if not ds:
            return
        closed = False
        for dl in ds:
            for c in dl.find_elements(By.TAG_NAME, 'button'):
                if vis(c) and (c.text or '').strip() in ('取消', '关闭', '返回试听配置'):
                    L.js_click(d, c)
                    time.sleep(0.8)
                    closed = True
                    break
            if closed:
                break
        if not closed:
            break
    try:
        d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
    except Exception:
        pass
    time.sleep(1)


def choose_mode(label_text):
    lab = retry(lambda: next((x for x in d.find_elements(By.XPATH, "//label[contains(normalize-space(.), '%s')]" % label_text) if vis(x)), None), 15)
    L.js_click(d, lab)
    time.sleep(0.6)
    return d.execute_script("const rs=[...document.querySelectorAll(\"input[name='preview-mode']\")]; return rs.map(r=>({checked:r.checked}))")


def start_preview():
    b = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '开始试听'), None), 20)
    L.js_click(d, b)
    time.sleep(0.5)


def audio_entries():
    out = []
    for e in L.fetch_log(d):
        u = e.get('url') or ''
        if '/audios/' in u and ('/stream' in u or '/preview' in u or '/stop-preview' in u):
            out.append({'method': e.get('method'), 'url': u[:130], 'status': e.get('status'),
                        'resBody': (e.get('resBody') or '')[:300]})
    return out


def browser_logs():
    try:
        return [x.get('message', '')[:300] for x in d.get_log('browser')]
    except Exception:
        return []


def wait_time(pred, timeout=30):
    """轮询 player-time，返回命中的文本序列。"""
    seq = []
    end = time.time() + timeout
    hit = None
    while time.time() < end:
        t = player_time()
        if not seq or seq[-1] != t:
            seq.append(t)
        if pred(t):
            hit = t
            break
        time.sleep(0.25)
    return hit, seq


import winreg
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
_o = Options()
_o.binary_location = L.CHROME_BINARY
for _a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox',
           '--lang=zh-CN', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'):
    _o.add_argument(_a)
if RESOLVER:
    _o.add_argument('--host-resolver-rules=%s' % RESOLVER)
_o.add_experimental_option('excludeSwitches', ['enable-logging'])
_o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
_major = 0
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as _k:
        _major = int(winreg.QueryValueEx(_k, 'version')[0].split('.')[0])
except Exception:
    pass
_cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
_path = ''
if _major and os.path.isdir(_cache):
    for _ver in os.listdir(_cache):
        _exe = os.path.join(_cache, _ver, 'chromedriver.exe')
        if os.path.isfile(_exe):
            try:
                if int(_ver.split('.')[0]) == _major:
                    _path = _exe
            except ValueError:
                pass
d = webdriver.Chrome(options=_o, service=Service(executable_path=_path) if _path else Service())
d.set_page_load_timeout(60)
d.set_script_timeout(60)
d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': L.FETCH_PATCH})
d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': r"""
window.__mediaLog = [];
(function(){
  const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
  Object.defineProperty(HTMLMediaElement.prototype, 'src', {
    get(){ return desc.get.call(this); },
    set(v){ try { window.__mediaLog.push({t: Date.now(), v: String(v).slice(0, 300)}); } catch(e){}
            return desc.set.call(this, v); },
    configurable: true
  });
})();
"""})
try:
    for _attempt in range(4):
        d.get(L.BASE + '/testcases')
        time.sleep(5)
        if '/login' not in d.current_url:
            break
        for b in d.find_elements(By.TAG_NAME, 'button'):
            t = (b.text or '').strip()
            if t and ('进入' in t or '登录' in t) and vis(b):
                L.js_click(d, b)
                time.sleep(4)
                break
        time.sleep(2)
    time.sleep(2)
    OUT['base'] = L.BASE
    OUT['bundle'] = d.execute_script(
        "return [...document.querySelectorAll('script')].map(s=>s.src).filter(Boolean).join(' ')")
    OUT['health'] = d.execute_async_script("""
        const done = arguments[arguments.length-1];
        fetch('/api/v1/../health').then(r=>r.text()).then(t=>done({status:200,body:t})).catch(e=>done({status:-1,body:String(e)}));
    """)

    # ---------- 浅色：浏览器播放成功态 ----------
    search_case()
    OUT['card_found'] = NAME in L.body_text(d)
    w = open_preview()
    OUT['config_text'] = (w.text or '')[:400]
    shot('s01_preview_config_light')
    OUT['mode_radio_browser'] = choose_mode('浏览器播放')
    L.clear_fetch_log(d)
    try:
        d.get_log('browser')
    except Exception:
        pass
    start_preview()
    OUT['stream_fetch'] = audio_entries()
    t0, seq0 = wait_time(lambda t: bool(t) and not t.startswith('00:00 / 00:00'), timeout=20)
    OUT['metadata_time'] = t0
    OUT['time_sequence_initial'] = seq0
    OUT['btn_after_load'] = (play_btn().get_attribute('aria-label') if play_btn() else None)
    shot('s02_player_browser_loaded_light')

    # 播放
    if OUT['btn_after_load'] == '播放':
        L.js_click(d, play_btn())
    time.sleep(1.2)
    OUT['time_playing_1'] = player_time()
    OUT['btn_playing'] = (play_btn().get_attribute('aria-label') if play_btn() else None)
    shot('s03_player_browser_playing_light')
    time.sleep(1.0)
    OUT['time_playing_2'] = player_time()

    # 暂停
    if play_btn() and play_btn().get_attribute('aria-label') == '暂停':
        L.js_click(d, play_btn())
    time.sleep(0.6)
    paused_a = player_time()
    time.sleep(1.2)
    paused_b = player_time()
    OUT['pause_pair'] = [paused_a, paused_b]
    OUT['pause_stable'] = paused_a == paused_b
    OUT['btn_paused'] = (play_btn().get_attribute('aria-label') if play_btn() else None)
    shot('s04_player_browser_paused_light')

    # 继续 → 播完
    if play_btn() and play_btn().get_attribute('aria-label') == '播放':
        L.js_click(d, play_btn())
    # 继续播放后等到「结束归零」：先观察到非零进度，再回到 00:00
    seen_progress = [False]

    def _ended(t):
        if not t:
            return False
        if not t.startswith('00:00 /'):
            seen_progress[0] = True
            return False
        return seen_progress[0]

    ended, seq1 = wait_time(_ended, timeout=25)
    OUT['time_sequence_end'] = seq1
    OUT['ended_time'] = ended
    OUT['btn_ended'] = (play_btn().get_attribute('aria-label') if play_btn() else None)
    OUT['alerts_browser'] = alerts()
    OUT['media_src'] = d.execute_script('return window.__mediaLog || []')[:6]
    OUT['preview_response'] = [e for e in L.fetch_log(d) if '/testcases/' in (e.get('url') or '') and 'preview' in (e.get('url') or '')]
    OUT['console_errors'] = [x for x in browser_logs() if 'SEVERE' in x or 'ERR_' in x or 'CORS' in x][:8]
    shot('s05_player_browser_ended_light')
    close_all_dialogs()

    # ---------- 浅色：实验室播放仍失败（环境） ----------
    try:
        w = open_preview()
        choose_mode('实验室播放')
        L.clear_fetch_log(d)
        start_preview()
        time.sleep(12)
        OUT['lab_alerts'] = alerts()
        OUT['lab_fetch'] = audio_entries()
        OUT['lab_time'] = player_time()
        shot('s06_player_lab_error_light')
        close_all_dialogs()
    except Exception:
        OUT['lab_err'] = traceback.format_exc()[-500:]
        close_all_dialogs()

    # ---------- 深色：同源 reload 后重拍成功态 ----------
    L.apply_theme(d, 'dark')
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    L.apply_theme(d, 'dark')
    OUT['dark_class'] = d.execute_script("return document.documentElement.className")
    OUT['dark_bg'] = d.execute_script("return getComputedStyle(document.body).backgroundColor")
    try:
        search_case()
        w = open_preview()
        shot('s07_preview_config_dark')
        choose_mode('浏览器播放')
        L.clear_fetch_log(d)
        start_preview()
        OUT['dark_stream_fetch'] = audio_entries()
        t0, seqd = wait_time(lambda t: bool(t) and not t.startswith('00:00 / 00:00'), timeout=20)
        OUT['dark_metadata_time'] = t0
        if play_btn() and play_btn().get_attribute('aria-label') == '播放':
            L.js_click(d, play_btn())
        time.sleep(1.2)
        OUT['dark_time_playing'] = player_time()
        shot('s08_player_browser_playing_dark')
        close_all_dialogs()
    except Exception:
        OUT['dark_err'] = traceback.format_exc()[-600:]
        close_all_dialogs()

    # ---------- 独立接口回读（非页内）：音频库时长 ----------
    OUT['audio_api'] = d.execute_async_script("""
        const done = arguments[arguments.length-1];
        fetch('/api/v1/audios?keyword=url_src_A&page=1&page_size=5')
          .then(r=>r.text()).then(t=>done(t)).catch(e=>done(String(e)));
    """)
finally:
    OUT['shots'] = sorted([f for f in os.listdir(L.ART) if f.startswith(SHOT_PREFIX)])
    L.save_evidence('evidence_%s_under_artifacts' % TAG, OUT)
    with open(os.path.join(L.HERE, 'evidence_int1538_%s.json' % TAG), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    try:
        d.quit()
    except Exception:
        pass
