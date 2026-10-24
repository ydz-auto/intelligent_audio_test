# -*- coding: utf-8 -*-
"""INT-1534 验收实测（测试工程师）：用例「预览音频」试听配置 + 播放器真实链路。

容器：iat-react-int1534-verify（交付源码构建）→ http://localhost:15234
后端：docker 网关 :15000（库 intelligent_audio_test）

断言：
 A 浏览器播放：点「开始试听」→ POST /testcases/{id}/preview 200，body
   {offset:0, preview_type:frontend, playback_mode:frontend}；<audio> 真实起播
   （duration≈2s、currentTime 推进、无 error）；播放器文案为真实时长，不是 42s。
 B 设备区：取用例 config 真实设备「设备正面（0.5m+0°）」，不是写死 A/B。
 C 实验室播放：offset=1 → body {offset:1, preview_type:backend, playback_mode:backend}；
   停止 → POST /testcases/{id}/stop_preview 200。
 D 不再出现「已开始试听（演示）」toast / 固定 42s。
 E 深浅色截图。
"""
import json
import os
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15234')
CASE_ID = os.environ.get('CASE_ID', '27467b20-5e2b-480f-b27d-1336d3966b67')
CASE_NAME = os.environ.get('CASE_NAME', '接线测试_INT1534_试听_浏览器播放')
GROUP_NAME = os.environ.get('GROUP_NAME', '音频上传生成')
ART = os.environ.get('ART_DIR', 'tests/ui/artifacts/int1534-verify')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = {url: url, method: method, body: (init && init.body) || null,
                 t: Date.now(), status: 0};
  window.__net.push(entry);
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    return res;
  } catch (e) {
    entry.status = -1;
    throw e;
  }
};
"""

RESULT = {}


def log(msg):
    print(msg, flush=True)


def opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    o.add_argument('--autoplay-policy=no-user-gesture-required')
    # 环境缺口：网关签发的预签名 URL 主机是容器网络名 rustfs
    o.add_argument('--host-resolver-rules=MAP rustfs 127.0.0.1')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    return o


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def dialog_text(drv):
    return drv.find_element(By.XPATH, "//div[@role='dialog']").text


def wait_dialog(drv, needle, timeout=180):
    WebDriverWait(drv, timeout).until(lambda d: needle in dialog_text(d))
    return dialog_text(drv)


def net_entries(drv, needle):
    return [e for e in drv.execute_script('return window.__net || []')
            if needle in (e.get('url') or '')]


def perf_entries(drv, needle):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])['message']
            method = msg.get('method')
            if method in ('Network.requestWillBeSent', 'Network.responseReceived'):
                p = msg['params']
                url = p['request']['url'] if method.endswith('requestWillBeSent') else p['response']['url']
                if needle in url:
                    rec = {'kind': method.split('.')[1], 'url': url.split('?')[0],
                           'method': p['request']['method'] if method.endswith('requestWillBeSent') else None}
                    if method.endswith('responseReceived'):
                        rec['status'] = p['response']['status']
                    out.append(rec)
    except Exception as exc:  # noqa: BLE001
        out.append({'error': str(exc)})
    return out


def audio_state(drv):
    return drv.execute_script("""
    const el = document.querySelector('[data-testid=case-preview-audio]');
    if (!el) return null;
    return {src: (el.currentSrc || el.src || '').split('?')[0],
            host: (() => { try { return new URL(el.src).host } catch (e) { return null } })(),
            currentTime: el.currentTime, duration: el.duration,
            paused: el.paused, readyState: el.readyState,
            error: el.error ? el.error.code : null};
    """)


def open_dialog(drv):
    drv.get(BASE + '/testcases/by-group?search=' + urllib.parse.quote(CASE_NAME))
    WebDriverWait(drv, 240).until(
        lambda d: d.find_elements(By.XPATH, "//span[contains(., '%s')]" % GROUP_NAME))
    time.sleep(1.0)
    js_click(drv, drv.find_element(
        By.XPATH, "//span[contains(@class, 'truncate') and normalize-space(.)='%s']" % GROUP_NAME))
    btn = WebDriverWait(drv, 240).until(EC.presence_of_element_located((
        By.XPATH,
        "//div[contains(., '%s')][.//button[@aria-label='预览音频']]//button[@aria-label='预览音频']"
        % CASE_NAME)))
    time.sleep(0.5)
    js_click(drv, btn)
    WebDriverWait(drv, 20).until(
        EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.8)


def set_theme(drv, dark):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
                       'dark' if dark else 'light')
    drv.get('about:blank')
    time.sleep(0.3)


def browser_play(drv, tag):
    open_dialog(drv)
    cfg = dialog_text(drv)
    RESULT[tag + '_config_text'] = cfg
    log('[%s] 配置态:\n%s' % (tag, cfg))
    drv.save_screenshot(os.path.join(ART, '%s_01_config.png' % tag))

    js_click(drv, drv.find_element(
        By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
    wait_dialog(drv, '测试用例预览｜')
    reqs = net_entries(drv, '/testcases/%s/preview' % CASE_ID)
    RESULT[tag + '_preview_req'] = reqs[-1] if reqs else None
    RESULT[tag + '_perf'] = perf_entries(drv, '/testcases/%s/preview' % CASE_ID)
    log('[%s] preview 请求: %s' % (tag, json.dumps(RESULT[tag + '_preview_req'], ensure_ascii=False)))
    log('[%s] perf: %s' % (tag, json.dumps(RESULT[tag + '_perf'], ensure_ascii=False)))
    time.sleep(1.0)  # 播约 1s
    st = audio_state(drv)
    RESULT[tag + '_audio_mid'] = st
    RESULT[tag + '_player_mid'] = dialog_text(drv)
    log('[%s] audio(1s): %s' % (tag, json.dumps(st, ensure_ascii=False)))
    log('[%s] 播放器(1s):\n%s' % (tag, RESULT[tag + '_player_mid']))
    drv.save_screenshot(os.path.join(ART, '%s_02_player_playing.png' % tag))

    time.sleep(2.5)  # 2s 片段播完
    RESULT[tag + '_audio_end'] = audio_state(drv)
    RESULT[tag + '_player_end'] = dialog_text(drv)
    log('[%s] audio(结束): %s' % (tag, json.dumps(RESULT[tag + '_audio_end'], ensure_ascii=False)))
    log('[%s] 播放器(结束):\n%s' % (tag, RESULT[tag + '_player_end']))
    drv.save_screenshot(os.path.join(ART, '%s_03_player_ended.png' % tag))


def main():
    drv = webdriver.Chrome(options=opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        # ---------- 浅色：浏览器播放 ----------
        browser_play(drv, 'L')

        # 停止
        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[@aria-label='停止']"))
        time.sleep(0.8)
        RESULT['L_stop_audio'] = audio_state(drv)
        log('[L] 停止后: %s' % json.dumps(RESULT['L_stop_audio'], ensure_ascii=False))

        # ---------- 浅色：实验室播放 ----------
        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='返回试听配置']"))
        wait_dialog(drv, '音频试听配置', timeout=20)
        js_click(drv, drv.find_element(
            By.XPATH, "//label[contains(normalize-space(.), '实验室播放')]"))
        time.sleep(0.3)
        off = drv.find_element(By.XPATH, "//div[@role='dialog']//input[@aria-label='偏移量秒数']")
        off.send_keys('\ue009' + 'a')       # Ctrl+A
        off.send_keys('\ue003')             # Delete
        off.send_keys('1')
        time.sleep(0.3)
        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        lab = wait_dialog(drv, '播放设备（实验室播放）')
        RESULT['L_lab_dialog'] = lab
        time.sleep(0.8)
        lab_reqs = net_entries(drv, '/testcases/%s/preview' % CASE_ID)
        RESULT['L_lab_req'] = lab_reqs[-1] if lab_reqs else None
        log('[L] 实验室请求: %s' % json.dumps(RESULT['L_lab_req'], ensure_ascii=False))
        log('[L] 实验室播放器:\n%s' % lab)
        drv.save_screenshot(os.path.join(ART, 'L_04_player_lab.png'))

        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[@aria-label='停止']"))
        time.sleep(1.0)
        stops = net_entries(drv, '/testcases/%s/stop_preview' % CASE_ID)
        RESULT['L_stop_req'] = stops[-1] if stops else None
        RESULT['L_stop_perf'] = perf_entries(drv, '/testcases/%s/stop_preview' % CASE_ID)
        log('[L] stop_preview: %s' % json.dumps(RESULT['L_stop_req'], ensure_ascii=False))
        log('[L] stop perf: %s' % json.dumps(RESULT['L_stop_perf'], ensure_ascii=False))

        # 关闭弹窗
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.6)

        # ---------- 深色：浏览器播放 ----------
        set_theme(drv, True)
        browser_play(drv, 'D')
        set_theme(drv, False)

        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULT, f, ensure_ascii=False, indent=2, default=str)
        log('DONE')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
