# -*- coding: utf-8 -*-
"""INT-1538 R8 复测：P1-5 实验室播放成功态（INT-1656 解阻后）。

覆盖两条真实入口（均走 15173 → 15000 真实栈，无 mock）：
A. 用例行「预览音频」→ 音频试听配置 → 实验室播放 → 开始试听
   → 前端实测请求 POST /testcases/{id}/preview（backend）2xx；进度随墙钟前进；
     「停止」→ POST /testcases/{id}/stop_preview 2xx；浅/深截图。
B. 用例编辑抽屉 → 音频列表步 → 音频行「试听」→ 实验室播放 → 播放
   → POST /audios/{id}/preview 2xx（回 duration / devices）；停止 → POST /audios/{id}/stop-preview 2xx。
设备覆盖：夹具 A 两轮绑设备 1/2（UCX II online），夹具 B 两轮绑设备 11/12；另附接口层四设备探针。

夹具自建（组 + 用例，config 克隆真实 2 轮用例，音频统一切 2358 url_src_A.wav 4.0s dry），
结束前 DELETE + purge。
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
GROUP = '接线测试_INT1538_R8组_' + TAG
NAME_A = '接线测试_INT1538_R8用例A_' + TAG
NAME_B = '接线测试_INT1538_R8用例B_' + TAG
AUDIO_ID = 2358
AUDIO_NAME = 'url_src_A.wav'
BASE_CASE = '92b93231-1f37-4f89-ae6b-cd2a2b945fb9'  # 真实 2 轮用例（只克隆 config）
OUT = {'tag': TAG, 'group': GROUP, 'cases': [NAME_A, NAME_B], 'audio_id': AUDIO_ID}


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


def sample_time(seconds=3.0, interval=0.4):
    out = []
    end = time.time() + seconds
    while time.time() < end:
        out.append({'t': round(time.time(), 2), 'ui': player_time()})
        time.sleep(interval)
    return out


def dialog_text():
    ds = L.dialogs(d)
    return (ds[-1].text or '')[:1200] if ds else ''


def find_by_aria(scope, label):
    """优先在最后一个可见 dialog（播放器所在层）内找 aria-label 按钮，避免命中背景页。"""
    ds = L.dialogs(d)
    for dlg in reversed(ds):
        btn = d.execute_script(
            """
            const root = arguments[0], name = arguments[1];
            for (const b of root.querySelectorAll('button[aria-label="' + name + '"]')) {
              if (b.getClientRects().length > 0) return b;
            }
            return null;""", dlg, label)
        if btn:
            return btn
    return d.execute_script(
        """
        const name = arguments[0];
        for (const b of document.querySelectorAll('button[aria-label="' + name + '"]')) {
          if (b.getClientRects().length > 0) return b;
        }
        return null;""", label)


def find_preview_for(name, label='预览音频'):
    """按名字定位卡片上的操作按钮：取包含该名字的最近祖先（分组容器会同时含多个用例名）。"""
    return d.execute_script(
        """
        const name = arguments[0], label = arguments[1];
        let best = null, bestDepth = 99;
        for (const b of document.querySelectorAll('button[aria-label="' + label + '"]')) {
          if (!b.getClientRects().length) continue;
          let el = b;
          for (let i = 1; i <= 10 && el; i++) {
            if ((el.innerText || '').includes(name)) {
              if (i < bestDepth) { best = b; bestDepth = i; }
              break;
            }
            el = el.parentElement;
          }
        }
        return best;""", name, label)


def expand_group(group):
    """重置筛选 → 分组 facet 选 group → 展开分组卡。"""
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
                              if vis(x) and group in (x.text or '')), None), 20)
    L.js_click(d, opt)
    time.sleep(4)
    hdr = retry(lambda: d.execute_script("""
        for (const el of document.querySelectorAll('div')) {
          const cls = (el.className || '').toString();
          if (cls.includes('cursor-pointer') && cls.includes('justify-between') &&
              (el.innerText || '').trim().startsWith(arguments[0])) return el;
        }
        return null;""", group), 40)
    L.js_click(d, hdr)
    time.sleep(3)


def close_dialogs():
    for _ in range(3):
        if not L.dialogs(d):
            return
        d.execute_script(
            "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        time.sleep(1.2)
        ds = L.dialogs(d)
        if ds:
            cl = next((b for b in ds[-1].find_elements(By.TAG_NAME, 'button')
                       if (b.get_attribute('aria-label') or '') in ('Close', '关闭')), None)
            if cl:
                L.js_click(d, cl)
                time.sleep(1)


def pick_lab_and_start():
    lab = retry(lambda: next((x for x in d.find_elements(
        By.XPATH, "//label[contains(normalize-space(.), '实验室播放')]") if vis(x)), None), 20)
    L.js_click(d, lab)
    time.sleep(0.6)
    OUT_LAB = d.execute_script(
        "return [...document.querySelectorAll(\"input[name='preview-mode']\")].map(r=>r.checked)")
    stt = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                              if vis(x) and (x.text or '').strip() == '开始试听'), None), 20)
    L.js_click(d, stt)
    return OUT_LAB


def fetch_since(idx):
    return L.fetch_log(d)[idx:]


def slim(entries, needles):
    out = []
    for e in entries:
        u = e.get('url') or ''
        if any(n in u for n in needles):
            out.append({'method': e.get('method'), 'url': u[:160], 'status': e.get('status'),
                        'reqBody': (e.get('reqBody') or '')[:400],
                        'resBody': (e.get('resBody') or '')[:600]})
    return out


d = build_driver()
CID_A = GID = CID_B = ''
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(4)
    OUT['bundle'] = d.execute_script(
        "return Array.from(document.scripts).map(s=>s.src).filter(Boolean).join(',')") or ''
    OUT['health'] = d.execute_async_script("""
        const done = arguments[arguments.length-1];
        fetch('/health').then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));""")
    st, p, _ = L.api_json(d, '/playback-devices')
    items = ((p or {}).get('data') or {}).get('items') or []
    OUT['devices'] = [{'id': x.get('id'), 'name': x.get('name'), 'status': x.get('status'),
                       'unique': x.get('device_unique_id')} for x in items if x.get('id') in (1, 2, 11, 12)]
    DEV_NAME = {x['id']: x['name'] for x in OUT['devices']}
    st, p, raw = L.api_json(d, '/audios/%d' % AUDIO_ID)
    ad = ((p or {}).get('data') or {})
    OUT['audio'] = {'status': st, 'name': ad.get('name'), 'duration': ad.get('duration'),
                    'audio_type': ad.get('audio_type'), 'file_path': ad.get('file_path')}

    # ---------- 夹具 ----------
    st, p, raw = L.api_json(d, '/groups', 'POST',
                            {'name': GROUP, 'description': 'INT-1538 R8 实验室播放复测组',
                             'algorithm_type': ''})
    GID = str(((p or {}).get('data') or {}).get('id') or '')
    OUT['create_group'] = {'status': st, 'id': GID}
    st, p, raw = L.api_json(d, '/testcases/' + BASE_CASE)
    cfg = ((p or {}).get('data') or {}).get('config') or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)

    def make_case(name, dev1, dev2):
        c = json.loads(json.dumps(cfg))
        for rd in c.get('rounds') or []:
            dev = dev1 if rd.get('round_number') == 1 else dev2
            for a in rd.get('audios') or []:
                a['audio_id'] = AUDIO_ID
                a['audio_name'] = AUDIO_NAME
                a['playback_device_id'] = dev
                a['playback_device_name'] = DEV_NAME.get(dev, '')
        st, p, raw = L.api_json(d, '/testcases', 'POST',
                                {'name': name, 'description': 'INT-1538 R8 实验室播放夹具',
                                 'group_id': GID, 'config': c})
        return st, str(((p or {}).get('data') or {}).get('id') or ''), raw[:160]

    stA, CID_A, rawA = make_case(NAME_A, 1, 2)
    stB, CID_B, rawB = make_case(NAME_B, 11, 12)
    OUT['create_cases'] = {'A': {'status': stA, 'id': CID_A, 'devices': [1, 2]},
                           'B': {'status': stB, 'id': CID_B, 'devices': [11, 12]}}

    # ---------- A. 用例行「预览音频」实验室播放（设备 1 / 2） ----------
    d.get(L.BASE + '/testcases')
    time.sleep(5)
    expand_group(GROUP)
    pv = retry(lambda: find_preview_for(NAME_A), 60)
    L.js_click(d, pv)
    L.wait_dialog(d, '音频试听配置', 30)
    time.sleep(0.8)
    OUT['A_config_text'] = dialog_text()
    L.shot(d, 'r8_A1_config_light')
    idx = len(L.fetch_log(d))
    OUT['A_radio_checked'] = pick_lab_and_start()
    start_ts = time.time()
    retry(lambda: player_time() or None, 40)
    OUT['A_fetch_start'] = slim(fetch_since(idx), ['/preview', '/stop_preview'])
    OUT['A_player_text_initial'] = dialog_text()
    OUT['A_samples'] = sample_time(3.2)
    L.shot(d, 'r8_A2_playing_light')
    L.apply_theme(d, 'dark')
    time.sleep(0.8)
    L.shot(d, 'r8_A3_playing_dark')
    OUT['A_dark'] = {'html': d.execute_script('return document.documentElement.className'),
                     'bg': d.execute_script('return getComputedStyle(document.body).backgroundColor')}
    L.apply_theme(d, 'light')
    time.sleep(0.5)
    # 停止
    idx2 = len(L.fetch_log(d))
    stp = retry(lambda: find_by_aria(d, '停止'), 15)
    L.js_click(d, stp)
    time.sleep(2)
    OUT['A_fetch_stop'] = slim(fetch_since(idx2), ['/preview', '/stop_preview'])
    OUT['A_after_stop_text'] = dialog_text()
    L.shot(d, 'r8_A4_stopped_light')
    OUT['A_elapsed_to_stop'] = round(time.time() - start_ts, 1)
    close_dialogs()
    OUT['A_dialogs_after_close'] = len(L.dialogs(d))

    # ---------- B. 用例编辑抽屉 → 音频列表 → 音频行「试听」实验室播放 ----------
    ed = retry(lambda: find_preview_for(NAME_A, '编辑用例'), 30)
    L.js_click(d, ed)
    L.wait_dialog(d, '编辑测试用例', 30)
    time.sleep(1.2)
    tab = retry(lambda: next((t for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']")
                              if vis(t) and (t.text or '').strip() == '音频列表'), None), 20)
    L.js_click(d, tab)
    time.sleep(2.0)
    OUT['B_step'] = dialog_text()[:800]
    aud = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='试听']")
                              if vis(b)), None), 30)
    L.js_click(d, aud)
    L.wait_dialog(d, '音频试听配置', 30)
    time.sleep(0.8)
    OUT['B_config_text'] = dialog_text()
    L.shot(d, 'r8_B1_config_light')
    idx3 = len(L.fetch_log(d))
    OUT['B_radio_checked'] = pick_lab_and_start()
    # 音频库源：进播放器后需点「播放」才发 /audios/{id}/preview
    time.sleep(1.2)
    play = retry(lambda: find_by_aria(d, '播放'), 20)
    if play:
        L.js_click(d, play)
    time.sleep(2.5)
    OUT['B_fetch_start'] = slim(fetch_since(idx3), ['/audios/', '/preview'])
    OUT['B_player_text_initial'] = dialog_text()
    OUT['B_samples'] = sample_time(2.8)
    L.shot(d, 'r8_B2_playing_light')
    L.apply_theme(d, 'dark')
    time.sleep(0.8)
    L.shot(d, 'r8_B3_playing_dark')
    L.apply_theme(d, 'light')
    time.sleep(0.5)
    idx4 = len(L.fetch_log(d))
    stp2 = retry(lambda: find_by_aria(d, '停止'), 15)
    L.js_click(d, stp2)
    time.sleep(2)
    OUT['B_fetch_stop'] = slim(fetch_since(idx4), ['/audios/', '/stop-preview'])
    OUT['B_after_stop_text'] = dialog_text()
    L.shot(d, 'r8_B4_stopped_light')
    close_dialogs()
    OUT['B_dialogs_after_close'] = len(L.dialogs(d))

    # ---------- C. 设备 11 / 12 的用例行实验室播放（同 A 口径，浅色一张） ----------
    d.get(L.BASE + '/testcases')
    time.sleep(5)
    expand_group(GROUP)
    pv2 = retry(lambda: find_preview_for(NAME_B), 60)
    L.js_click(d, pv2)
    L.wait_dialog(d, '音频试听配置', 30)
    time.sleep(0.8)
    idx5 = len(L.fetch_log(d))
    pick_lab_and_start()
    retry(lambda: player_time() or None, 40)
    OUT['C_fetch_start'] = slim(fetch_since(idx5), ['/preview', '/stop_preview'])
    OUT['C_player_text'] = player_time()
    OUT['C_samples'] = sample_time(2.4)
    L.shot(d, 'r8_C_playing_light')
    idx6 = len(L.fetch_log(d))
    stp3 = retry(lambda: find_by_aria(d, '停止'), 15)
    L.js_click(d, stp3)
    time.sleep(2)
    OUT['C_fetch_stop'] = slim(fetch_since(idx6), ['/preview', '/stop_preview'])

    # ---------- 控制台 ----------
    logs = d.get_log('browser')
    OUT['console_severe'] = [x for x in logs if x.get('level') == 'SEVERE']
    OUT['console_total'] = len(logs)
    OUT['alerts'] = [a.text.strip() for a in d.find_elements(By.CSS_SELECTOR, "[role='alert']") if vis(a)]
    close_dialogs()
finally:
    # ---------- 清理 ----------
    try:
        for cid in (CID_A, CID_B):
            if not cid:
                continue
            st, _p, raw = L.api_json(d, '/testcases/' + cid, 'DELETE')
            st2, _p, raw2 = L.api_json(d, '/testcases/' + cid + '/purge', 'DELETE')
            OUT.setdefault('cleanup_cases', []).append({'id': cid, 'delete': st,
                                                        'purge': st2, 'purge_body': raw2[:100]})
        if GID:
            st, _p, raw = L.api_json(d, '/groups/' + GID, 'DELETE')
            OUT['cleanup_group'] = st
        st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + TAG)
        OUT['alive_after'] = [x.get('id') for x in (((p or {}).get('data') or {}).get('items') or [])]
        st, p, _ = L.api_json(d, '/groups?page=1&per_page=100&only_deleted=1&keyword=' + TAG)
        OUT['group_deleted_after'] = [x.get('name') for x in (((p or {}).get('data') or {}).get('items') or [])]
    except Exception as e:
        OUT['cleanup_error'] = str(e)
    L.save_evidence('evidence_int1538_r8_labplay', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
