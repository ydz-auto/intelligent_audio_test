# -*- coding: utf-8 -*-
"""INT-1534 取证：用例「预览音频」→ 试听配置 → 播放器（真实请求/真实时长/真实设备）。

覆盖：
1. 浏览器播放：点「开始试听」发出 POST /testcases/{id}/preview（offset+preview_type+playback_mode），
   播放器用响应里的音频流地址起播，进度/时长来自真实 <audio>（不再 42s 假时长）；
2. 实验室播放：payload playback_mode=backend，播放器设备区取用例 config 真实设备；
   「停止」发 POST /testcases/{id}/stop_preview；
3. 浅色 / 深色截图。

环境说明：docker 网关签发的 OSS 预签名 URL 主机为容器网络名 rustfs，
宿主机浏览器不可解析——启动参数加 --host-resolver-rules="MAP rustfs 127.0.0.1"
把该主机映射到本机 rustfs 端口（环境缺口，非前端行为）。
"""
import base64
import json
import os
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
ART = os.environ.get(
    'ART_DIR',
    'tests/ui/artifacts/int1534',
)
CASE_NAME = '接线测试_INT1534_试听_浏览器播放'
CASE_ID = os.environ.get('CASE_ID', '')
GROUP_NAME = '音频上传生成'
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  let body = (init && init.body) || null;
  let entry = {url: url, method: method, body: body, t: Date.now(), status: 0};
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


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    o.add_argument('--autoplay-policy=no-user-gesture-required')
    # 环境缺口补偿：网关签发的预签名 URL 主机是容器网络名 rustfs
    o.add_argument('--host-resolver-rules=MAP rustfs 127.0.0.1')
    return o


def open_dialog(drv):
    drv.get(BASE + '/testcases/by-group?search=' + urllib.parse.quote(CASE_NAME))
    WebDriverWait(drv, 180).until(
        lambda d: d.find_elements(By.XPATH, "//span[contains(., '%s')]" % GROUP_NAME))
    time.sleep(1.0)
    # 分组默认收起：点组头展开
    js_click(drv, drv.find_element(
        By.XPATH, "//span[contains(@class, 'truncate') and normalize-space(.)='%s']" % GROUP_NAME))
    btn = WebDriverWait(drv, 180).until(EC.presence_of_element_located((
        By.XPATH,
        "//div[contains(., '%s')][.//button[@aria-label='预览音频']]//button[@aria-label='预览音频']"
        % CASE_NAME,
    )))
    time.sleep(0.5)
    js_click(drv, btn)
    WebDriverWait(drv, 20).until(
        EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.6)


def dialog_text(drv):
    return drv.find_element(By.XPATH, "//div[@role='dialog']").text


def wait_dialog_text(drv, needle, timeout=180):
    WebDriverWait(drv, timeout).until(
        lambda d: needle in dialog_text(d))
    return dialog_text(drv)


def net_entries(drv, needle):
    return [e for e in drv.execute_script('return window.__net || []')
            if needle in (e.get('url') or '')]


def audio_state(drv):
    return drv.execute_script("""
    const el = document.querySelector('[data-testid=case-preview-audio]');
    if (!el) return null;
    return {src: el.currentSrc || el.src, currentTime: el.currentTime,
            duration: el.duration, paused: el.paused, readyState: el.readyState,
            error: el.error ? el.error.code : null};
    """)


def set_theme(drv, dark):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
        'dark' if dark else 'light',
    )
    drv.get('about:blank')
    time.sleep(0.3)


def main():
    drv = webdriver.Chrome(options=opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    result = {}
    try:
        # ---------- 浅色：浏览器播放 ----------
        open_dialog(drv)
        light_text = dialog_text(drv)
        log('[light] 配置态:\n' + light_text)
        drv.save_screenshot(os.path.join(ART, '01-config-light.png'))

        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        player_text = wait_dialog_text(drv, '测试用例预览｜')
        net = net_entries(drv, '/testcases/%s/preview' % CASE_ID)
        result['light_preview_req'] = net
        log('[light] preview 请求: %s' % json.dumps(net, ensure_ascii=False))
        time.sleep(1.2)
        state = audio_state(drv)
        result['light_audio_playing'] = state
        result['light_player_mid'] = dialog_text(drv)
        log('[light] audio 播放中: %s' % json.dumps(state, ensure_ascii=False))
        log('[light] 播放器文案（播放中）:\n' + result['light_player_mid'])
        drv.save_screenshot(os.path.join(ART, '02-player-browser-light.png'))

        # 播到结束（真实 <audio> 事件驱动，2s 片段）
        time.sleep(2.2)
        state2 = audio_state(drv)
        result['light_audio_end'] = state2
        result['light_player_end'] = dialog_text(drv)
        log('[light] audio 结束: %s' % json.dumps(state2, ensure_ascii=False))
        log('[light] 播放器文案（结束）:\n' + result['light_player_end'])
        drv.save_screenshot(os.path.join(ART, '03-player-ended-light.png'))

        # 停止 → 回到 0
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[@aria-label='停止']"))
        time.sleep(0.8)
        result['light_audio_stop'] = audio_state(drv)
        log('[light] 停止后: %s' % json.dumps(result['light_audio_stop'], ensure_ascii=False))

        # ---------- 浅色：实验室播放 ----------
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='返回试听配置']"))
        wait_dialog_text(drv, '音频试听配置', timeout=20)
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//input[@name='preview-mode'][@value='backend']")
                 if drv.find_elements(By.XPATH, "//div[@role='dialog']//input[@name='preview-mode'][@value='backend']")
                 else drv.find_element(By.XPATH, "//label[contains(normalize-space(.), '实验室播放')]"))
        time.sleep(0.4)
        # 偏移量 1 秒：验证 offset 进请求体（实验室播放从 1s 起放）
        off = drv.find_element(By.XPATH, "//div[@role='dialog']//input[@aria-label='偏移量秒数']")
        off.click()
        off.send_keys('a')
        off.send_keys('1')
        time.sleep(0.3)
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        lab_text = wait_dialog_text(drv, '播放设备（实验室播放）')
        time.sleep(1.0)
        net_lab = net_entries(drv, '/testcases/%s/preview' % CASE_ID)
        result['lab_preview_req'] = net_lab[-1] if net_lab else None
        result['lab_dialog'] = lab_text
        log('[light] 实验室播放请求: %s' % json.dumps(result['lab_preview_req'], ensure_ascii=False))
        log('[light] 实验室播放器:\n' + lab_text)
        drv.save_screenshot(os.path.join(ART, '04-player-lab-light.png'))

        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[@aria-label='停止']"))
        time.sleep(1.0)
        stops = net_entries(drv, '/testcases/%s/stop_preview' % CASE_ID)
        result['stop_preview_req'] = stops[-1] if stops else None
        log('[light] stop_preview 请求: %s' % json.dumps(result['stop_preview_req'], ensure_ascii=False))
        # 关闭弹窗
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)

        # ---------- 深色：浏览器播放 ----------
        set_theme(drv, True)
        open_dialog(drv)
        drv.save_screenshot(os.path.join(ART, '05-config-dark.png'))
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        wait_dialog_text(drv, '测试用例预览｜')
        time.sleep(1.2)
        result['dark_audio'] = audio_state(drv)
        result['dark_dialog'] = dialog_text(drv)
        drv.save_screenshot(os.path.join(ART, '06-player-browser-dark.png'))
        log('[dark] audio: %s' % json.dumps(result['dark_audio'], ensure_ascii=False))
        log('[dark] 播放器文案:\n' + result['dark_dialog'])
        set_theme(drv, False)

        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log('RESULT ' + json.dumps(result, ensure_ascii=False)[:1500])
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
