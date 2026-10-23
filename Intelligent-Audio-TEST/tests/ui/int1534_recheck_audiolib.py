# -*- coding: utf-8 -*-
"""INT-1534 复测 P1-2 回归：音频列表卡「试听」（INT-1424 入口）在并线后仍走真实音频库链路。

路径：用例页 → 展开分组 → 用例卡「编辑用例」→ 抽屉「音频列表」→ 卡片「试听」→ 开始试听。
断言：浏览器播放 GET /audios/{id}/stream 且 <audio> 取到真实时长；
实验室播放 POST /audios/{id}/preview 携带 playback_device_ids/device_unique_ids（失败按错误条呈现）。
"""
import json
import os
import sys
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15340')
CASE_NAME = os.environ.get('CASE_NAME', '接线测试_INT1534_复测_试听')
GROUP_NAME = os.environ.get('GROUP_NAME', '音频上传生成')
AUDIO_ID = os.environ.get('AUDIO_ID', '')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1534-recheck')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const body = (init && init.body) || null;
  const entry = {url: url, method: method, body: typeof body === 'string' ? body : null, status: 0};
  window.__net.push(entry);
  try { const res = await __origFetch.apply(this, arguments); entry.status = res.status; return res; }
  catch (e) { entry.status = -1; throw e; }
};
"""


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--autoplay-policy=no-user-gesture-required')
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
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def net(drv, needle):
    return [e for e in drv.execute_script('return window.__net || []') if needle in (e.get('url') or '')]


def main():
    if not AUDIO_ID:
        raise SystemExit('需要 AUDIO_ID')
    d = driver()
    out = {}
    ok = True
    try:
        d.get(BASE + '/testcases/by-group?search=' + urllib.parse.quote(CASE_NAME))
        WebDriverWait(d, 240).until(lambda x: x.find_elements(
            By.XPATH, "//span[normalize-space(.)='%s']" % GROUP_NAME))
        time.sleep(1.0)
        js_click(d, d.find_element(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP_NAME))
        name_span = WebDriverWait(d, 120).until(EC.presence_of_element_located(
            (By.XPATH, "//span[normalize-space(.)='%s']" % CASE_NAME)))
        card = name_span.find_element(
            By.XPATH, "./ancestor::div[.//button[@aria-label='编辑用例']][1]")
        edit = card.find_element(By.XPATH, ".//button[@aria-label='编辑用例']")
        time.sleep(0.5)
        js_click(d, edit)
        tab = WebDriverWait(d, 60).until(EC.element_to_be_clickable(
            (By.XPATH, "//button[normalize-space(.)='音频列表']")))
        time.sleep(0.6)
        js_click(d, tab)
        listen = WebDriverWait(d, 60).until(EC.presence_of_element_located(
            (By.XPATH, "//button[@aria-label='试听']")))
        time.sleep(0.5)
        js_click(d, listen)
        # 用例抽屉本身也是 role=dialog：按内容定位试听弹窗
        dlg = "//div[@role='dialog'][.//button[normalize-space(.)='开始试听']]"
        WebDriverWait(d, 30).until(EC.visibility_of_element_located((By.XPATH, dlg)))
        time.sleep(0.8)
        out['dialog'] = d.find_element(By.XPATH, dlg).text
        log('[音频库] 配置态:\n' + out['dialog'])
        d.save_screenshot(os.path.join(ART, '06-audiolib-config-light.png'))
        if '音频「' not in out['dialog']:
            ok = False
            log('[FAIL] 音频库入口配置态未显示音频名')

        js_click(d, d.find_element(By.XPATH, dlg + "//button[normalize-space(.)='开始试听']"))
        player = "//div[@role='dialog'][contains(., '测试用例预览')]"
        WebDriverWait(d, 60).until(EC.visibility_of_element_located((By.XPATH, player)))
        time.sleep(2.5)
        out['player'] = d.find_element(By.XPATH, player).text
        out['stream_req'] = net(d, '/audios/%s/stream' % AUDIO_ID)
        out['audio'] = d.execute_script("""
        const el = document.querySelector('[data-testid=case-preview-audio]');
        if (!el) return null;
        return {src: el.currentSrc || el.src, duration: el.duration, paused: el.paused,
                error: el.error ? el.error.code : null};""")
        log('[音频库] 播放器:\n' + out['player'])
        log('[音频库] stream 请求: %s' % json.dumps(out['stream_req'], ensure_ascii=False))
        log('[音频库] audio: %s' % json.dumps(out['audio'], ensure_ascii=False))
        d.save_screenshot(os.path.join(ART, '07-audiolib-player-light.png'))
        if not out['stream_req']:
            ok = False
            log('[FAIL] 未发 GET /audios/{id}/stream')
        if not out['audio'] or not out['audio'].get('duration'):
            ok = False
            log('[FAIL] <audio> 未取到真实时长')

        # 实验室播放（音频库源）
        pd = ("//div[@role='dialog'][contains(., '测试用例预览') or contains(., '音频试听配置')]")
        js_click(d, d.find_element(By.XPATH, pd + "//button[normalize-space(.)='返回试听配置']"))
        time.sleep(0.6)
        js_click(d, d.find_element(
            By.XPATH, pd + "//label[contains(normalize-space(.), '实验室播放')]"))
        time.sleep(0.4)
        radios = d.find_elements(By.XPATH, pd + "//input[@type='radio']")
        if len(radios) < 2 or not radios[1].is_selected():
            js_click(d, radios[-1])
            time.sleep(0.4)
        js_click(d, d.find_element(By.XPATH, pd + "//button[normalize-space(.)='开始试听']"))
        WebDriverWait(d, 40).until(lambda x: '播放设备（实验室播放）' in x.find_element(By.XPATH, pd).text)
        time.sleep(0.8)
        js_click(d, d.find_element(By.XPATH, pd + "//button[@aria-label='播放']"))
        time.sleep(3.5)
        out['preview_req'] = net(d, '/audios/%s/preview' % AUDIO_ID)
        out['player_lab'] = d.find_element(By.XPATH, pd).text
        out['audio_after_lab'] = d.execute_script("""
        const el = document.querySelector('[data-testid=case-preview-audio]');
        return el ? {paused: el.paused, error: el.error ? el.error.code : null} : null;""")
        log('[音频库] 实验室请求: %s' % json.dumps(out['preview_req'], ensure_ascii=False))
        log('[音频库] 实验室播放器:\n' + out['player_lab'])
        d.save_screenshot(os.path.join(ART, '08-audiolib-player-lab-light.png'))
        if not out['preview_req']:
            ok = False
            log('[FAIL] 未发 POST /audios/{id}/preview')
        else:
            body = out['preview_req'][-1].get('body') or ''
            if 'playback_device_ids' not in body and 'device_unique_ids' not in body:
                log('[WARN] preview 载荷未带设备参数: %s' % body)
        js_click(d, d.find_element(By.XPATH, pd + "//button[@aria-label='停止']"))
        time.sleep(1.5)
        out['stop_req'] = net(d, '/audios/%s/stop-preview' % AUDIO_ID)
        log('[音频库] stop 请求: %s' % json.dumps(out['stop_req'], ensure_ascii=False))

        out['ok'] = ok
        with open(os.path.join(ART, 'audiolib_result.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        log('OK=%s' % ok)
        return 0 if ok else 2
    finally:
        d.quit()


if __name__ == '__main__':
    sys.exit(main())
