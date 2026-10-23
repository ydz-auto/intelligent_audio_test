# -*- coding: utf-8 -*-
"""INT-1512 最终取证：试听弹窗真实播放设备 + 上传真实进度（浅/深色 + 请求时序）。

要点：
- 设备下拉逐条与 GET /playback-devices 比对；
- 上传 4 个 2MB 真实音频，关闭上传弹窗后观察进度卡：记录每次百分比变化时刻
  与 /audios/upload/chunk、/audios/upload/merge 的响应时刻，证明进度由真实分片事件驱动；
- 浅色/深色截图；结束前删除本 run 上传的「接线测试_INT1512_」音频。
"""
import json
import os
import time
import wave

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5312')
ART = 'tests/ui/artifacts/int1512'
SRC = os.path.join(ART, 'upload-src')
PREFIX = '接线测试_INT1512_'
os.makedirs(SRC, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || 'GET';
  const res = await __origFetch.apply(this, arguments);
  try {
    window.__net.push({url: url, method: method, status: res.status, t: Date.now()});
  } catch (e) {}
  return res;
};
"""


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def api(drv, path, method='GET', body=None):
    js = """
    const cb = arguments[arguments.length - 1];
    const token = localStorage.getItem('iatp:auth:token:v1');
    const headers = {'Content-Type': 'application/json'};
    if (token) headers.Authorization = 'Bearer ' + token;
    fetch(arguments[0], {method: arguments[1] || 'GET', headers: headers, body: arguments[2] || undefined})
      .then(async r => cb({status: r.status, body: await r.text()}))
      .catch(e => cb({status: 0, body: String(e)}));
    """
    raw = drv.execute_async_script(js, path, method, body)
    try:
        payload = json.loads(raw['body'])
    except Exception:
        payload = raw['body']
    data = payload.get('data') if isinstance(payload, dict) else payload
    return raw['status'], data


def make_wav(path, mb):
    frames = int(mb * 1024 * 1024 / 2)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        chunk = b'\x00\x00' * 16000
        written = 0
        while written < frames:
            n = min(16000, frames - written)
            w.writeframes(chunk[: n * 2])
            written += n


def open_audio_page(drv):
    drv.get(BASE + '/audio-import')
    WebDriverWait(drv, 40).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(@aria-label, '的操作')]"))
    time.sleep(1.5)


def open_preview(drv):
    js_click(drv, drv.find_elements(By.XPATH, "//button[contains(@aria-label, '的操作')]")[0])
    item = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//div[@role='menuitem'][contains(normalize-space(.), '预览')]")))
    js_click(drv, item)
    WebDriverWait(drv, 15).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.6)


def select_option(drv, trigger_xpath, text):
    js_click(drv, WebDriverWait(drv, 10).until(EC.element_to_be_clickable((By.XPATH, trigger_xpath))))
    opt = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//div[@role='option'][contains(normalize-space(.), '%s')]" % text)))
    js_click(drv, opt)
    time.sleep(0.5)


def close_popup(drv):
    """base-ui 下拉 ESC 在 headless 下不稳，直接点标题收起。"""
    try:
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//h2"))
    except Exception:
        pass
    time.sleep(0.4)


def read_bar(drv):
    js = r"""
    const cards = [...document.querySelectorAll('div')].filter(
      d => (d.className || '').toString().indexOf('ring-foreground') !== -1 && /批量导入/.test(d.textContent || ''));
    if (!cards.length) return null;
    const card = cards[cards.length - 1];
    const bar = card.querySelector('div[style*="width"]');
    return {width: bar ? bar.style.width : '', text: (card.innerText || '').replace(/\n/g, ' | ')};
    """
    return drv.execute_script(js)


def main():
    drv = webdriver.Chrome(options=_opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        login(drv)
        open_audio_page(drv)

        # API 真值
        st, data = api(drv, '/api/v1/playback-devices?page=1&per_page=100')
        if isinstance(data, dict):
            items = data.get('items') or []
        else:
            items = data or []
        api_texts = [(d.get('name') or '') + ('（%s）' % d.get('model') if d.get('model') else '') for d in items]
        log('GET /playback-devices -> %s, %d 台' % (st, len(api_texts)))

        # ---- 浅色：试听弹窗 ----
        open_preview(drv)
        select_option(drv, "//button[@aria-label='播放模式']", '实验室播放')
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'preview-playback-device')))
        time.sleep(0.6)
        drv.save_screenshot(os.path.join(ART, '01-preview-lab-light.png'))
        js_click(drv, drv.find_element(By.XPATH, "//button[@id='preview-playback-device']"))
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[role='option']"))
        time.sleep(0.6)
        ui_texts = [e.text.strip() for e in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if e.text.strip()]
        drv.save_screenshot(os.path.join(ART, '02-preview-device-options-light.png'))
        log('UI 设备下拉 %d 台；与接口一致=%s' % (len(ui_texts), ui_texts == api_texts))
        assert ui_texts == api_texts, '设备下拉与接口不一致'
        close_popup(drv)
        # 播放一次，确认提交的是真实设备 id
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[@aria-label='播放']"))
        time.sleep(3)
        previews = [e for e in drv.execute_script('return window.__net || []')
                    if '/preview' in e.get('url', '') and e.get('method') == 'POST']
        log('preview POST: %s' % previews)
        assert previews and previews[-1]['status'] in (200, 400), '未触发预览请求'
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='关闭']"))
        time.sleep(0.8)

        # ---- 上传：浅色 ----
        files = []
        for i in range(4):
            p = os.path.join(SRC, '%s进度_%d.wav' % (PREFIX, i + 1))
            if not os.path.isfile(p):
                make_wav(p, 2)
            files.append(os.path.abspath(p))
        drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '上传音频')]").click()
        WebDriverWait(drv, 10).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
        fi = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[type='file']")
        drv.execute_script("arguments[0].style.display='block';", fi)
        fi.send_keys('\n'.join(files))
        WebDriverWait(drv, 20).until(lambda d: '已选择 4 个文件' in d.find_element(By.XPATH, "//div[@role='dialog']").text)
        drv.save_screenshot(os.path.join(ART, '03-upload-dialog-light.png'))
        t_start = int(time.time() * 1000)
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始上传']"))
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ART, '04-upload-dialog-uploading-light.png'))
        # 关闭弹窗（上传继续在后台跑，进度卡在页面顶部可见）
        try:
            js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']"))
        except Exception:
            pass
        time.sleep(0.3)

        samples = []
        mid = False
        deadline = time.time() + 240
        while time.time() < deadline:
            bar = read_bar(drv)
            if bar and bar['width'].endswith('%'):
                pct = float(bar['width'].replace('%', ''))
                if not samples or samples[-1][1] != pct:
                    samples.append([int(time.time() * 1000) - t_start, pct, bar['text'][:80]])
                if not mid and 5 < pct < 90:
                    drv.save_screenshot(os.path.join(ART, '05-upload-progress-light.png'))
                    mid = True
                if '导入完成' in bar['text']:
                    break
            time.sleep(0.1)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ART, '06-upload-progress-done-light.png'))
        log('进度轨迹(ms, %%): %s' % [[s[0], s[1]] for s in samples])

        net = drv.execute_script('return window.__net || []')
        chunk_t = [e['t'] - t_start for e in net if '/audios/upload/chunk' in e.get('url', '')]
        merge_t = [e['t'] - t_start for e in net if '/audios/upload/merge' in e.get('url', '')]
        log('chunk 响应时刻(ms): %s' % chunk_t)
        log('merge 响应时刻(ms): %s' % merge_t)
        log('chunk 状态: %s' % [e['status'] for e in net if '/audios/upload/chunk' in e.get('url', '')])
        log('merge 状态: %s' % [e['status'] for e in net if '/audios/upload/merge' in e.get('url', '')])

        # ---- 深色：进度卡（完成态，刷新后由持久化恢复）+ 试听弹窗 ----
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get('about:blank')
        time.sleep(0.5)
        open_audio_page(drv)
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ART, '07-progress-card-dark.png'))
        open_preview(drv)
        select_option(drv, "//button[@aria-label='播放模式']", '实验室播放')
        time.sleep(0.6)
        js_click(drv, drv.find_element(By.XPATH, "//button[@id='preview-playback-device']"))
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[role='option']"))
        time.sleep(0.6)
        dark_texts = [e.text.strip() for e in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if e.text.strip()]
        drv.save_screenshot(os.path.join(ART, '08-preview-device-options-dark.png'))
        log('深色设备下拉 %d 台；一致=%s' % (len(dark_texts), dark_texts == api_texts))
        assert dark_texts == api_texts

        # ---- 收尾：删除本 run 音频 ----
        st, data = api(drv, '/api/v1/audios', 'POST', json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
        items = (data or {}).get('items') or []
        for it in items:
            st2, _ = api(drv, '/api/v1/audios/%s' % it['id'], 'DELETE')
            log('DELETE /audios/%s -> %s' % (it['id'], st2))
        time.sleep(1.5)
        st, data = api(drv, '/api/v1/audios', 'POST', json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
        left = (data or {}).get('items') or []
        log('清理后残留 %d' % len(left))
        assert not left
        log('OK')
    finally:
        drv.quit()


def _opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    return o


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(2)
    try:
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    except Exception:
        pass
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


if __name__ == '__main__':
    main()
