# -*- coding: utf-8 -*-
"""INT-1534 二次返工取证（总审打回项）：音频库入口偏移量 + 返回配置只停一次。

A. 音频列表卡「试听」入口（INT-1424，P2）
   用例页 → 展开分组 → 用例卡「编辑用例」→ 抽屉「音频列表」→ 音频卡「试听」→
   试听配置弹窗 → 实验室播放 + 偏移量 → 开始试听 → 播放
   断言：POST /audios/{id}/preview 的 body 带 offset=2（此前被静默丢弃为 0/undefined）。
B. 用例行「预览音频」入口（P3-1）
   用例行「预览音频」→ 实验室播放 → 开始试听（进入即播放态）→「返回试听配置」
   断言：POST /testcases/{id}/stop_preview 只发 1 次（此前 2 次）。
另附深浅色截图与 Network 证据图。
环境：dev server :5360（/api 代理 → docker 网关 :15000，库 intelligent_audio_test）。
"""
import html
import json
import os
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5360')
CASE_NAME = os.environ.get('CASE_NAME', '接线测试_INT1534_返工_试听')
GROUP_NAME = os.environ.get('GROUP_NAME', '音频上传生成')
AUDIO_ID = os.environ.get('AUDIO_ID', '2506')
CASE_ID = os.environ.get('CASE_ID', '')
OFFSET = os.environ.get('OFFSET', '2')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1534r2')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const body = (init && init.body) || null;
  const entry = {url: url, method: method, body: typeof body === 'string' ? body : null, t: Date.now(), status: 0};
  window.__net.push(entry);
  try { const res = await __origFetch.apply(this, arguments); entry.status = res.status; return res; }
  catch (e) { entry.status = -1; throw e; }
};
"""

DLG = "//div[@role='dialog'][.//button[normalize-space(.)='开始试听']]"
PLAYER = "//div[@role='dialog'][contains(., '测试用例预览')]"


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--autoplay-policy=no-user-gesture-required')
    o.add_argument('--disable-dev-shm-usage')
    o.add_argument('--host-resolver-rules=MAP rustfs 127.0.0.1')
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path, best = '', ()
    if major and os.path.isdir(root):
        for ver in os.listdir(root):
            exe = os.path.join(root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    vv = tuple(int(x) for x in ver.split('.') if x.isdigit())
                except ValueError:
                    continue
                if vv and vv[0] == major and vv > best:
                    best, path = vv, exe
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(180)
    return d


def net(drv, needle):
    return [e for e in drv.execute_script('return window.__net || []') if needle in (e.get('url') or '')]


def goto_case_page(drv):
    """用例页 → 展开目标分组（列表接口偶发极慢，整页重试）。"""
    last = None
    for attempt in range(3):
        try:
            drv.get(BASE + '/testcases/by-group?search=' + urllib.parse.quote(CASE_NAME))
            WebDriverWait(drv, 300).until(lambda x: x.find_elements(
                By.XPATH, "//span[normalize-space(.)='%s']" % GROUP_NAME))
            time.sleep(0.8)
            js_click(drv, drv.find_element(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP_NAME))
            return
        except Exception as err:  # noqa: BLE001
            last = err
            log('[goto] 第 %d 次失败: %s' % (attempt + 1, err))
            try:
                drv.save_screenshot(os.path.join(ART, 'goto-fail-%d.png' % (attempt + 1)))
            except Exception:
                pass
    raise last


def open_audiolib_dialog(drv):
    """抽屉「音频列表」→ 音频卡「试听」→ 试听配置弹窗。"""
    goto_case_page(drv)
    edit = WebDriverWait(drv, 120).until(EC.presence_of_element_located((
        By.XPATH,
        "//div[contains(., '%s')][.//button[@aria-label='编辑用例']]//button[@aria-label='编辑用例']"
        % CASE_NAME)))
    time.sleep(0.5)
    js_click(drv, edit)
    tab = WebDriverWait(drv, 60).until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space(.)='音频列表']")))
    time.sleep(0.6)
    js_click(drv, tab)
    listen = WebDriverWait(drv, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//button[@aria-label='试听']")))
    time.sleep(0.4)
    js_click(drv, listen)
    WebDriverWait(drv, 30).until(EC.visibility_of_element_located((By.XPATH, DLG)))
    time.sleep(0.8)


def open_case_row_dialog(drv):
    """用例行「预览音频」→ 试听配置弹窗。"""
    goto_case_page(drv)
    btn = WebDriverWait(drv, 120).until(EC.presence_of_element_located((
        By.XPATH,
        "//div[contains(., '%s')][.//button[@aria-label='预览音频']]//button[@aria-label='预览音频']"
        % CASE_NAME)))
    time.sleep(0.4)
    js_click(drv, btn)
    WebDriverWait(drv, 30).until(EC.visibility_of_element_located((By.XPATH, DLG)))
    time.sleep(0.6)


def fill_offset(drv, value):
    box = drv.find_element(By.XPATH, DLG + "//input[@aria-label='偏移量秒数']")
    box.click()
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(str(value))
    time.sleep(0.3)
    return drv.execute_script('return arguments[0].value', box)


def pick_lab(drv):
    js_click(drv, drv.find_element(
        By.XPATH, DLG + "//label[contains(normalize-space(.), '实验室播放')]"))
    time.sleep(0.4)


def network_evidence(drv, entries, name):
    """把抓到的请求渲染成一张 Network 证据图。"""
    rows = ''.join(
        "<tr><td>%s</td><td class='u'>%s</td><td>%s</td><td>%s</td></tr>"
        % (html.escape(e['method']), html.escape(e['url']),
           e['status'], html.escape(e['body'] or '—'))
        for e in entries
    )
    doc = """<html><head><meta charset='utf-8'><style>
    body{font-family:Consolas,monospace;background:#fff;color:#111;padding:18px}
    h3{font-family:sans-serif;margin:0 0 12px}
    table{border-collapse:collapse;font-size:12px;width:100%%}
    th,td{border:1px solid #bbb;padding:6px 8px;text-align:left;vertical-align:top}
    th{background:#eef} .u{word-break:break-all;max-width:520px}
    </style></head><body><h3>%s</h3><table>
    <tr><th>Method</th><th>URL</th><th>Status</th><th>Request body</th></tr>%s</table></body></html>""" % (
        html.escape(name), rows)
    path = os.path.join(ART, name + '.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc)
    drv.get('file:///' + path.replace('\\', '/'))
    time.sleep(0.6)
    shot = os.path.join(ART, name + '.png')
    drv.save_screenshot(shot)
    return shot


def main():
    d = _driver()
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    out = {'base': BASE, 'case_name': CASE_NAME, 'audio_id': AUDIO_ID, 'case_id': CASE_ID}
    try:
        # ================= A. 音频库入口 + 偏移量（P2） =================
        open_audiolib_dialog(d)
        out['a_light_config'] = d.find_element(By.XPATH, DLG).text
        d.save_screenshot(os.path.join(ART, '01-audiolib-config-light.png'))
        pick_lab(d)
        out['a_light_offset_typed'] = fill_offset(d, OFFSET)
        js_click(d, d.find_element(By.XPATH, DLG + "//button[normalize-space(.)='开始试听']"))
        WebDriverWait(d, 40).until(EC.visibility_of_element_located((By.XPATH, PLAYER)))
        time.sleep(0.8)
        out['a_light_player_time'] = d.execute_script(
            "const p=document.querySelector('[data-testid=player-time]'); return p?p.textContent:null")
        js_click(d, d.find_element(By.XPATH, PLAYER + "//button[@aria-label='播放']"))
        time.sleep(3.0)
        out['a_light_preview_reqs'] = net(d, '/audios/%s/preview' % AUDIO_ID)
        out['a_light_player_text'] = d.find_element(By.XPATH, PLAYER).text
        d.save_screenshot(os.path.join(ART, '02-audiolib-player-lab-light.png'))
        log('[A light] preview: %s' % json.dumps(out['a_light_preview_reqs'], ensure_ascii=False))
        log('[A light] time: %s' % out['a_light_player_time'])

        # 关弹窗
        js_click(d, d.find_element(By.XPATH, PLAYER + "//button[normalize-space(.)='返回试听配置']"))
        WebDriverWait(d, 20).until(EC.visibility_of_element_located((By.XPATH, DLG)))
        js_click(d, d.find_element(By.XPATH, DLG + "//button[normalize-space(.)='取消']"))
        time.sleep(0.6)

        # 深色：音频库入口
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        open_audiolib_dialog(d)
        out['a_dark_is_dark'] = d.execute_script(
            "return document.documentElement.classList.contains('dark')")
        d.save_screenshot(os.path.join(ART, '03-audiolib-config-dark.png'))
        pick_lab(d)
        out['a_dark_offset_typed'] = fill_offset(d, OFFSET)
        js_click(d, d.find_element(By.XPATH, DLG + "//button[normalize-space(.)='开始试听']"))
        WebDriverWait(d, 40).until(EC.visibility_of_element_located((By.XPATH, PLAYER)))
        time.sleep(0.8)
        out['a_dark_player_time'] = d.execute_script(
            "const p=document.querySelector('[data-testid=player-time]'); return p?p.textContent:null")
        js_click(d, d.find_element(By.XPATH, PLAYER + "//button[@aria-label='播放']"))
        time.sleep(3.0)
        out['a_dark_preview_reqs'] = net(d, '/audios/%s/preview' % AUDIO_ID)
        d.save_screenshot(os.path.join(ART, '04-audiolib-player-lab-dark.png'))
        log('[A dark] preview: %s' % json.dumps(out['a_dark_preview_reqs'], ensure_ascii=False))
        js_click(d, d.find_element(By.XPATH, PLAYER + "//button[normalize-space(.)='返回试听配置']"))
        WebDriverWait(d, 20).until(EC.visibility_of_element_located((By.XPATH, DLG)))
        js_click(d, d.find_element(By.XPATH, DLG + "//button[normalize-space(.)='取消']"))
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'light');")

        # ================= B. 用例行入口 → 返回配置只停一次（P3-1） =================
        open_case_row_dialog(d)
        pick_lab(d)
        js_click(d, d.find_element(By.XPATH, DLG + "//button[normalize-space(.)='开始试听']"))
        WebDriverWait(d, 60).until(lambda x: '播放设备（实验室播放）' in x.find_element(By.XPATH, PLAYER).text)
        time.sleep(1.2)
        out['b_preview_reqs'] = net(d, '/testcases/%s/preview' % CASE_ID)
        out['b_stop_reqs_at_mount'] = net(d, '/testcases/%s/stop_preview' % CASE_ID)
        out['b_player_text'] = d.find_element(By.XPATH, PLAYER).text
        d.save_screenshot(os.path.join(ART, '05-case-player-lab-light.png'))
        js_click(d, d.find_element(By.XPATH, PLAYER + "//button[normalize-space(.)='返回试听配置']"))
        WebDriverWait(d, 20).until(EC.visibility_of_element_located((By.XPATH, DLG)))
        time.sleep(1.8)
        out['b_stop_reqs'] = net(d, '/testcases/%s/stop_preview' % CASE_ID)
        log('[B] 播放器挂载后 stop 次数 = %d' % len(out['b_stop_reqs_at_mount']))
        log('[B] 返回试听配置后 stop_preview 次数 = %d' % len(out['b_stop_reqs']))
        js_click(d, d.find_element(By.XPATH, DLG + "//button[normalize-space(.)='取消']"))

        # Network 证据图（合并 P2/P3-1 的写请求）
        combined = (out['a_light_preview_reqs'] + out['a_dark_preview_reqs']
                    + out['b_preview_reqs'] + out['b_stop_reqs'])
        network_evidence(d, combined, 'network-evidence')

        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        log(json.dumps(out, ensure_ascii=False, indent=2)[:3000])
    finally:
        d.quit()


if __name__ == '__main__':
    main()
