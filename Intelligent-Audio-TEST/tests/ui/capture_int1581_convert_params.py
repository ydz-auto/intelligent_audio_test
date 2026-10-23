# -*- coding: utf-8 -*-
"""INT-1581 取证：格式转换弹窗的采样率/声道数/位深度/比特率是否随请求提交并真实生效。

流程（docker 真实库栈：React dev 5381 → 代理 api_gateway 15000，库 intelligent_audio_test）：
1. 造 2 条自建音频（接线测试_INT1581_ 前缀，16 kHz 单声道 16 bit WAV）：
   本栈 /audios/upload/register 因后端 Config 缺 AUDIO_UPLOAD_CHUNK_SIZE_MB 报 400
   （环境缺陷，与本卡无关），故改用 URL 导入 + 元数据改名落地真实音频记录；
2. 行操作 →「转换格式」：A 转 WAV（44.1 kHz / 双声道 / 24 bit），
   B 转 MP3（48 kHz / 单声道 / 320 kbps），提交并等待弹窗关闭；
3. Network 取证：POST /audios/{id}/convert 的请求体（snake_case 四参数）；
4. 回读 GET /audios/{id}：sample_rate / channels / format / bitrate 与提交一致；
5. 浅色 / 深色弹窗截图 + Network 证据截图；
6. 删除本 run 造出的音频。
"""
import json
import os
import time
import wave
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5381')
ART = 'tests/ui/artifacts/int1581'
SRC = os.path.join(ART, 'upload-src')
PREFIX = '接线测试_INT1581_'
AUDIO_HOST = os.environ.get('AUDIO_SRC_HOST', 'http://host.docker.internal:5398')
DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
os.makedirs(SRC, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const reqBody = (init && init.body && typeof init.body === 'string') ? init.body : null;
  const res = await __origFetch.apply(this, arguments);
  let respText = null;
  if (url.indexOf('/convert') !== -1) {
    try { respText = await res.clone().text(); } catch (e) {}
  }
  try { window.__net.push({url: url, method: method, status: res.status,
                           body: reqBody, resp: respText, t: Date.now()}); } catch (e) {}
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


def make_wav(path, seconds=3):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b'\x00\x00' * 16000 * seconds)


def open_audio_page(drv):
    drv.get(BASE + '/audio-import')
    WebDriverWait(drv, 60).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索音频']")))
    time.sleep(2.0)


def create_audio(drv, src_path, display_name):
    """URL 导入真实音频文件（本栈宿主 5398 静态服务）→ 元数据改名成自建前缀。"""
    url = '%s/%s' % (AUDIO_HOST, quote(os.path.basename(src_path)))
    st, data = api(drv, '/api/v1/audios/url-import', 'POST',
                   json.dumps({'url': url, 'audio_type': 'dry'}))
    assert st in (200, 201) and data and data.get('id'), 'URL 导入失败 %s: %s' % (st, data)
    audio_id = data['id']
    st2, _ = api(drv, '/api/v1/audios/%s/metadata' % audio_id, 'PUT',
                 json.dumps({'name': display_name}))
    assert st2 == 200, '改名失败 %s' % st2
    return audio_id


def search(drv, keyword):
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索音频']")
    box.clear()
    box.send_keys(keyword)
    time.sleep(1.2)


def open_convert(drv, name):
    btn = WebDriverWait(drv, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, '%s')]" % name)))
    js_click(drv, btn)
    item = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='menuitem'][contains(normalize-space(.), '转换格式')]")))
    js_click(drv, item)
    WebDriverWait(drv, 10).until(
        EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']//h2[contains(., '音频格式转换')]")))
    time.sleep(0.8)


def pick(drv, trigger_aria, option_text):
    js_click(drv, WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//div[@role='dialog']//button[@aria-label='%s']" % trigger_aria))))
    time.sleep(0.5)
    opt = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='option'][normalize-space(.)='%s']" % option_text)))
    js_click(drv, opt)
    time.sleep(0.6)


def submit(drv):
    js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[contains(normalize-space(.), '开始转换')]"))
    # 转换走 ffmpeg，真实库 3s 音频一般数秒内完成
    WebDriverWait(drv, 120).until(lambda d: not d.find_elements(
        By.XPATH, "//div[@role='dialog']//button[contains(normalize-space(.), '转换中')]"))
    time.sleep(2.0)


def convert_calls(drv):
    net = drv.execute_script('return window.__net || []')
    return [e for e in net if '/convert' in e.get('url', '') and e.get('method') == 'POST']


def read_audio(drv, audio_id):
    st, data = api(drv, '/api/v1/audios/%s' % audio_id)
    return st, data


def overlay_network(drv, lines):
    js = """
    const old = document.getElementById('net-evidence');
    if (old) old.remove();
    const box = document.createElement('div');
    box.id = 'net-evidence';
    box.style.cssText = 'position:fixed;left:24px;top:24px;z-index:99999;background:#0f172a;color:#e2e8f0;'
      + 'font:12px/1.6 Consolas,monospace;padding:16px 20px;border-radius:10px;max-width:1100px;'
      + 'white-space:pre-wrap;word-break:break-all;box-shadow:0 10px 40px rgba(0,0,0,.5)';
    box.textContent = arguments[0];
    document.body.appendChild(box);
    """
    drv.execute_script(js, '\n'.join(lines))
    time.sleep(0.4)


def remove_overlay(drv):
    drv.execute_script("const e=document.getElementById('net-evidence'); if(e) e.remove();")


def main():
    drv = webdriver.Chrome(service=Service(DRIVER), options=_opts())
    # 15000 栈列表查询偶发 30s+（SSE 线程池），异步脚本默认 30s、HTTP 默认 120s 都不够
    drv.set_script_timeout(180)
    drv.command_executor.set_timeout(600)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        login_ok = ensure_session(drv)
        open_audio_page(drv)

        # ---- 1. 造两条自建音频（16 kHz / 单声道 / WAV 基线） ----
        names = ['%s转换_A.wav' % PREFIX, '%s转换_B.wav' % PREFIX]
        for suffix, display_name in zip(('A', 'B'), names):
            p = os.path.join(SRC, 'src_%s.wav' % suffix)
            if not os.path.isfile(p):
                make_wav(p)
            created = create_audio(drv, os.path.abspath(p), display_name)
            log('造数据：%s → id=%s' % (display_name, created))

        st, data = api(drv, '/api/v1/audios', 'POST',
                       json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
        items = (data or {}).get('items') or []
        assert len(items) >= 2, '自建音频未落库：%s' % [i.get('name') for i in items]
        by_name = {i['name']: i for i in items}
        for n in names:
            assert n in by_name, '未找到自建音频 %s（实际 %s）' % (n, list(by_name))
        log('基线：%s' % [(n, by_name[n]['id'], by_name[n]['sample_rate'], by_name[n]['channels'],
                       by_name[n]['format'], by_name[n]['bitrate']) for n in names])

        search(drv, PREFIX)
        name_a, name_b = names

        # ---- 2. A：WAV / 44.1 kHz / 双声道 / 24 bit（浅色） ----
        open_convert(drv, name_a)
        dialog_text = drv.find_element(By.XPATH, "//div[@role='dialog']").text
        assert '仅接收' not in dialog_text, '弹窗仍残留「后端仅接收 format」注记'
        assert '位深度仅 WAV / FLAC' in dialog_text, '参数生效说明缺失：%s' % dialog_text
        pick(drv, '目标格式', 'WAV')
        pick(drv, '目标采样率', '44.1 kHz')
        pick(drv, '声道数', '双声道')
        pick(drv, '转换参数', '24 bit')
        drv.save_screenshot(os.path.join(ART, '01-convert-dialog-wav-light.png'))
        submit(drv)
        call_a = convert_calls(drv)[-1]
        log('A convert 请求：POST %s status=%s body=%s resp=%s' % (
            call_a['url'], call_a['status'], call_a['body'], call_a['resp']))
        body_a = json.loads(call_a['body'])
        assert body_a == {'format': 'WAV', 'sample_rate': 44100, 'channels': 2, 'bit_depth': 24}, body_a
        assert call_a['status'] == 200
        st, info_a = read_audio(drv, by_name[name_a]['id'])
        log('A 回读：status=%s sample_rate=%s channels=%s format=%s bitrate=%s' % (
            st, info_a.get('sample_rate'), info_a.get('channels'), info_a.get('format'), info_a.get('bitrate')))
        assert info_a.get('sample_rate') == 44100, info_a
        assert info_a.get('channels') == 2, info_a
        assert str(info_a.get('format')).lower() == 'wav', info_a
        drv.save_screenshot(os.path.join(ART, '02-convert-wav-done-light.png'))

        # ---- 3. B：MP3 / 48 kHz / 单声道 / 320 kbps ----
        open_convert(drv, name_b)
        pick(drv, '目标格式', 'MP3')
        pick(drv, '目标采样率', '48 kHz')
        pick(drv, '声道数', '单声道')
        pick(drv, '转换参数', '320 kbps')
        drv.save_screenshot(os.path.join(ART, '03-convert-dialog-mp3-light.png'))
        submit(drv)
        call_b = convert_calls(drv)[-1]
        log('B convert 请求：POST %s status=%s body=%s resp=%s' % (
            call_b['url'], call_b['status'], call_b['body'], call_b['resp']))
        body_b = json.loads(call_b['body'])
        assert body_b == {'format': 'MP3', 'sample_rate': 48000, 'channels': 1, 'bitrate': 320}, body_b
        assert call_b['status'] == 200
        st, info_b = read_audio(drv, by_name[name_b]['id'])
        log('B 回读：status=%s sample_rate=%s channels=%s format=%s bitrate=%s' % (
            st, info_b.get('sample_rate'), info_b.get('channels'), info_b.get('format'), info_b.get('bitrate')))
        assert info_b.get('sample_rate') == 48000, info_b
        assert info_b.get('channels') == 1, info_b
        assert str(info_b.get('format')).lower() == 'mp3', info_b
        assert info_b.get('bitrate') == 320000, info_b
        drv.save_screenshot(os.path.join(ART, '04-convert-mp3-done-light.png'))

        # ---- 4. Network 证据截图（页内证据卡，浏览器 Network 面板同口径字段） ----
        overlay_network(drv, [
            'Network 证据（本页 fetch 打点，等同 DevTools Network 请求体/状态码）',
            '',
            'POST %s  →  HTTP %s' % (call_a['url'], call_a['status']),
            '  payload: %s' % call_a['body'],
            '  response: %s' % (call_a['resp'] or '')[:220],
            '  GET /api/v1/audios/%s → sample_rate=%s channels=%s format=%s' % (
                by_name[name_a]['id'], info_a.get('sample_rate'), info_a.get('channels'), info_a.get('format')),
            '',
            'POST %s  →  HTTP %s' % (call_b['url'], call_b['status']),
            '  payload: %s' % call_b['body'],
            '  response: %s' % (call_b['resp'] or '')[:220],
            '  GET /api/v1/audios/%s → sample_rate=%s channels=%s bitrate=%s format=%s' % (
                by_name[name_b]['id'], info_b.get('sample_rate'), info_b.get('channels'),
                info_b.get('bitrate'), info_b.get('format')),
        ])
        drv.save_screenshot(os.path.join(ART, '05-network-evidence.png'))
        remove_overlay(drv)

        # ---- 5. 深色弹窗截图 ----
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get('about:blank')
        time.sleep(0.5)
        open_audio_page(drv)
        search(drv, PREFIX)
        open_convert(drv, name_a)
        pick(drv, '目标格式', 'MP3')
        pick(drv, '目标采样率', '16 kHz')
        pick(drv, '声道数', '单声道')
        pick(drv, '转换参数', '128 kbps')
        drv.save_screenshot(os.path.join(ART, '06-convert-dialog-dark.png'))
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']"))
        time.sleep(0.6)

        # ---- 6. 收尾：删除本 run 音频 ----
        st, data = api(drv, '/api/v1/audios', 'POST',
                       json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
        for it in (data or {}).get('items') or []:
            st2, _ = api(drv, '/api/v1/audios/%s' % it['id'], 'DELETE')
            log('DELETE /audios/%s -> %s' % (it['id'], st2))
        time.sleep(1.5)
        st, data = api(drv, '/api/v1/audios', 'POST',
                       json.dumps({'page': 1, 'per_page': 100, 'keyword': PREFIX}))
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


def ensure_session(drv):
    """AUTH_MODE=off：网关注入 dev_user（权限 *），直接进页面即可；被守卫拦回登录页才走表单登录。"""
    drv.get(BASE + '/audio-import')
    time.sleep(3)
    if '/login' in drv.current_url:
        login(drv)
        drv.get(BASE + '/audio-import')
        time.sleep(2)


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(2)
    for attempt in range(2):
        try:
            drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
            drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
            drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        except Exception:
            pass
        try:
            WebDriverWait(drv, 90).until(lambda d: '/login' not in d.current_url)
            break
        except Exception:
            if attempt == 1:
                raise
            time.sleep(3)
    time.sleep(1.5)


if __name__ == '__main__':
    main()
