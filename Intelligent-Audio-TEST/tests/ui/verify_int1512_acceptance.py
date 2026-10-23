# -*- coding: utf-8 -*-
"""INT-1512 验收（测试工程师）：试听弹窗真实播放设备 + 上传进度真实分片驱动。

与实施者取证脚本独立编写，断言口径按卡内验收：
1. grep 口径（静态，见 run 评论）之外，浏览器核对实验室播放设备下拉 == GET /playback-devices；
2. 默认选中首台真实设备，提交的 playback_device_id 是真实 id（不是 1/2/3）；
3. 上传进度非匀速：采样百分比轨迹 + 分片/合并响应时刻，证明由真实事件驱动；
4. 浅/深色截图 + 网络证据（fetch 打点记录 method/url/status/body）。
"""
import json
import os
import statistics
import time
import wave

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5317')
ART = os.path.abspath('tests/ui/artifacts/int1512_accept')
SRC = os.path.join(ART, 'src')
PREFIX = '接线测试_INT1512A_'
TOKEN_KEY = 'iatp:auth:token:v1'
os.makedirs(SRC, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const body = init && init.body;
  let bodyText = null;
  if (typeof body === 'string') bodyText = body.slice(0, 400);
  const res = await __origFetch.apply(this, arguments);
  try { window.__net.push({url: url, method: method, status: res.status, body: bodyText, t: Date.now()}); } catch (e) {}
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


def opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    return o


def login(drv):
    for attempt in range(3):
        drv.get(BASE + '/login')
        WebDriverWait(drv, 30).until(EC.presence_of_element_located((By.ID, 'username')))
        time.sleep(1.0)
        drv.find_element(By.ID, 'username').clear()
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').clear()
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        try:
            WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
            return
        except Exception:
            log('登录第 %d 次未跳转，重试' % (attempt + 1))
    raise AssertionError('登录失败')


def open_audio_page(drv):
    drv.get(BASE + '/audio-import')
    WebDriverWait(drv, 60).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(@aria-label, '的操作')]"))
    time.sleep(1.5)


def open_preview(drv):
    js_click(drv, drv.find_elements(By.XPATH, "//button[contains(@aria-label, '的操作')]")[0])
    item = WebDriverWait(drv, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//div[@role='menuitem'][contains(normalize-space(.), '预览')]")))
    js_click(drv, item)
    WebDriverWait(drv, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.8)


def pick_mode(drv, text):
    js_click(drv, WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='播放模式']"))))
    opt = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//div[@role='option'][contains(normalize-space(.), '%s')]" % text)))
    js_click(drv, opt)
    time.sleep(0.6)


def device_options(drv):
    js_click(drv, WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[@id='preview-playback-device']"))))
    WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[role='option']"))
    time.sleep(0.5)
    texts = [e.text.strip() for e in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if e.text.strip()]
    return texts


def close_device_popup(drv):
    """点第一项选中即关闭下拉（base-ui 点标题收起不稳，选中更接近真实用户操作）。"""
    opts = drv.find_elements(By.CSS_SELECTOR, "[role='option']")
    if opts:
        js_click(drv, opts[0])
    time.sleep(0.6)


def click_play(drv, timeout=12):
    """base-ui 弹层开合动画会吞首次点击，重试直到捕获 POST /preview。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            btn = drv.find_element(By.XPATH, "//div[@role='dialog']//button[@aria-label='播放']")
            js_click(drv, btn)
        except Exception:
            pass
        time.sleep(1.0)
        net = drv.execute_script('return window.__net || []')
        hits = [e for e in net if '/preview' in e.get('url', '') and e.get('method') == 'POST'
                and '/stop-preview' not in e.get('url', '')]
        if hits:
            return hits
    return []


def close_popup(drv):
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
    drv = webdriver.Chrome(options=opts())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        login(drv)
        open_audio_page(drv)

        # ---- 接口真值 ----
        st, data = api(drv, '/api/v1/playback-devices?page=1&per_page=100')
        items = (data or {}).get('items') if isinstance(data, dict) else (data or [])
        api_texts = [(d.get('name') or '') + ('（%s）' % d.get('model') if d.get('model') else '') for d in items]
        api_ids = [d.get('id') for d in items]
        log('GET /api/v1/playback-devices -> %s，%d 台，ids=%s' % (st, len(api_texts), api_ids))
        log('接口设备: %s' % api_texts)
        assert st == 200 and api_texts, '播放设备接口不可用'

        # ---- 浅色：试听弹窗 + 设备下拉 ----
        open_preview(drv)
        pick_mode(drv, '实验室播放')
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'preview-playback-device')))
        time.sleep(0.8)
        trigger_text = drv.find_element(By.ID, 'preview-playback-device').text.strip()
        log('默认选中播放设备（触发按钮文案）: %r' % trigger_text)
        drv.save_screenshot(os.path.join(ART, '01-preview-lab-light.png'))

        texts = device_options(drv)
        drv.save_screenshot(os.path.join(ART, '02-preview-device-options-light.png'))
        log('UI 下拉 %d 项：%s' % (len(texts), texts))
        assert texts == api_texts, '设备下拉与接口不一致：UI=%s API=%s' % (texts, api_texts)
        assert trigger_text == api_texts[0], '默认设备不是首台真实设备：%r vs %r' % (trigger_text, api_texts[0])

        # 选第二台真实设备，确认下拉选中会回显并影响提交
        expected_id = api_ids[0]
        try:
            dev_opts = drv.find_elements(By.CSS_SELECTOR, "[role='option']")
            js_click(drv, dev_opts[1])
            time.sleep(0.8)
            after = drv.find_element(By.ID, 'preview-playback-device').text.strip()
            log('选中第二项后回显: %r' % after)
            if after == api_texts[1]:
                expected_id = api_ids[1]
        except Exception as e:
            log('下拉选中核对跳过：%s' % e)
        time.sleep(0.4)

        # ---- 提交形态：点击播放，取 POST /preview body ----
        previews = click_play(drv)
        log('POST preview: %s' % previews)
        assert previews, '未捕获 POST /preview'
        body = json.loads(previews[-1]['body'] or '{}')
        log('preview body=%s status=%s' % (body, previews[-1]['status']))
        assert body.get('playback_device_id') not in (1, 2, 3, None), '仍是假设备 id：%s' % body
        assert body.get('playback_device_id') in api_ids, '提交的设备 id 不在真实设备列表：%s' % body
        assert body.get('playback_device_id') == expected_id, '提交设备与下拉选中不一致：%s vs %s' % (
            body.get('playback_device_id'), expected_id)
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='关闭']"))
        time.sleep(0.8)

        # ---- 预清理：删掉上一轮中断遗留的测试音频 ----
        st, data = api(drv, '/api/v1/audios', 'POST', json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
        for it in ((data or {}).get('items') or []):
            api(drv, '/api/v1/audios/%s' % it['id'], 'DELETE')
            log('预清理 DELETE /audios/%s' % it['id'])

        # ---- 上传：真实进度 ----
        files = []
        for i in range(4):
            p = os.path.join(SRC, '%s进度_%d.wav' % (PREFIX, i + 1))
            if not os.path.isfile(p):
                make_wav(p, 2)
            files.append(os.path.abspath(p))

        drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '上传音频')]").click()
        WebDriverWait(drv, 15).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
        time.sleep(0.8)
        # 上传选项弹窗里的播放设备下拉也用同一缓存（顺带核对）
        try:
            trig = drv.find_element(By.XPATH, "//div[@role='dialog']//label[contains(., '播放设备')]/following-sibling::button[@role='combobox']")
            js_click(drv, trig)
            WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, "[role='option']"))
            time.sleep(0.5)
            up_opts = [e.text.strip() for e in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if e.text.strip()]
            log('上传弹窗播放设备下拉 %d 项，与接口一致=%s' % (len(up_opts), up_opts == api_texts))
            close_popup(drv)
        except Exception as e:
            log('上传弹窗设备下拉核对跳过：%s' % e)

        fi = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[type='file']")
        drv.execute_script("arguments[0].style.display='block';", fi)
        fi.send_keys('\n'.join(files))
        WebDriverWait(drv, 30).until(lambda d: '已选择 4 个文件' in d.find_element(By.XPATH, "//div[@role='dialog']").text)
        drv.save_screenshot(os.path.join(ART, '03-upload-dialog-light.png'))

        t0 = int(time.time() * 1000)
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始上传']"))
        time.sleep(0.6)
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
                    samples.append([int(time.time() * 1000) - t0, pct, bar['text'][:100]])
                if not mid and 5 < pct < 90:
                    drv.save_screenshot(os.path.join(ART, '04-upload-progress-light.png'))
                    mid = True
                if '导入完成' in bar['text']:
                    break
            time.sleep(0.08)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ART, '05-upload-progress-done-light.png'))

        log('进度轨迹(ms,%%): %s' % [[s[0], s[1]] for s in samples])
        pcts = [s[1] for s in samples]
        assert len(pcts) >= 3, '进度采样点太少，无法判断是否真实推进：%s' % pcts
        assert pcts == sorted(pcts), '进度出现倒退：%s' % pcts
        assert pcts[-1] == 100.0, '进度未到 100：%s' % pcts
        deltas = [samples[i + 1][0] - samples[i][0] for i in range(len(samples) - 1)]
        log('采样步进间隔(ms): %s' % deltas)
        if len(deltas) >= 3:
            tight = sum(1 for d in deltas if 550 <= d <= 650)
            log('落在 600±50ms 的步进数: %d / %d；间隔标准差 %.1f' % (tight, len(deltas), statistics.pstdev(deltas)))
            assert tight < len(deltas), '步进间隔全部落在 600±50ms，疑似定时器假推进'
        done_text = samples[-1][2]
        log('完成态文案: %s' % done_text)
        flat = done_text.replace(' | ', '')
        assert '成功4' in flat, '完成态成功数不对：%s' % done_text

        net = drv.execute_script('return window.__net || []')
        chunk = [e for e in net if '/audios/upload/chunk' in e.get('url', '')]
        merge = [e for e in net if '/audios/upload/merge' in e.get('url', '')]
        log('chunk 响应时刻(ms): %s 状态: %s' % ([e['t'] - t0 for e in chunk], [e['status'] for e in chunk]))
        log('merge 响应时刻(ms): %s 状态: %s' % ([e['t'] - t0 for e in merge], [e['status'] for e in merge]))
        assert chunk and merge, '未捕获分片/合并请求'
        assert all(e['status'] < 400 for e in chunk + merge), '分片或合并失败：%s' % (
            [(e['url'], e['status']) for e in chunk + merge if e['status'] >= 400])

        # ---- 深色：刷新恢复完成态进度卡 + 试听弹窗设备下拉 ----
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get('about:blank')
        time.sleep(0.5)
        open_audio_page(drv)
        time.sleep(2)
        dark_bar = read_bar(drv)
        log('深色刷新后进度卡: %s' % (dark_bar['text'][:120] if dark_bar else None))
        drv.save_screenshot(os.path.join(ART, '06-progress-card-dark.png'))

        open_preview(drv)
        pick_mode(drv, '实验室播放')
        time.sleep(0.8)
        drv.save_screenshot(os.path.join(ART, '07-preview-lab-dark.png'))
        dark_texts = device_options(drv)
        drv.save_screenshot(os.path.join(ART, '08-preview-device-options-dark.png'))
        log('深色设备下拉 %d 项，与接口一致=%s' % (len(dark_texts), dark_texts == api_texts))
        assert dark_texts == api_texts, '深色下拉与接口不一致'
        close_popup(drv)

        # ---- 收尾：删除本 run 上传的音频 ----
        st, data = api(drv, '/api/v1/audios', 'POST', json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
        left_items = (data or {}).get('items') or []
        log('清理前命中 %d 条' % len(left_items))
        for it in left_items:
            st2, _ = api(drv, '/api/v1/audios/%s' % it['id'], 'DELETE')
            log('DELETE /audios/%s -> %s' % (it['id'], st2))
        time.sleep(1.5)
        st, data = api(drv, '/api/v1/audios', 'POST', json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
        left = (data or {}).get('items') or []
        log('清理后残留 %d' % len(left))
        assert not left, '测试数据未清理干净'
        log('ACCEPT PASS')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
