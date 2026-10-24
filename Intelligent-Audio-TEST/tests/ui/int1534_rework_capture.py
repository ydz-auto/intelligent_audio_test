# -*- coding: utf-8 -*-
"""INT-1534 返工浏览器取证：用例行「预览音频」→ 试听配置 → 播放器（真实请求/真实时长/真实设备）。

环境：dev server :5360（/api 代理 → docker 网关 :15000，库 intelligent_audio_test）。
覆盖：用例源 POST /testcases/{id}/preview（浏览器/实验室两种模式）、stop_preview、
深浅色截图、Network 证据。
说明：本栈 rustfs 对象现全部 404（api 侧 upload/register 报 Config.AUDIO_UPLOAD_CHUNK_SIZE_MB
缺失、无新对象可传），浏览器端用 --host-resolver-rules 把 rustfs 映射到本机后仍取不到字节 →
播放器按错误态兜底（前端行为正确，环境缺口另行记录）。
"""
import json
import os
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5360')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1534r')
CASE_NAME = os.environ.get('CASE_NAME', '接线测试_INT1534_返工_试听')
CASE_ID = os.environ.get('CASE_ID', '')
GROUP_NAME = os.environ.get('GROUP_NAME', '音频上传生成')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  let body = (init && init.body) || null;
  let entry = {url: url, method: method, body: typeof body === 'string' ? body : null, t: Date.now(), status: 0};
  window.__net.push(entry);
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    return res;
  } catch (e) { entry.status = -1; throw e; }
};
"""


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--autoplay-policy=no-user-gesture-required')
    options.add_argument('--disable-dev-shm-usage')
    # 环境缺口补偿：预签名 URL 主机是容器网络名 rustfs（宿主 9000 有映射）
    options.add_argument('--host-resolver-rules=MAP rustfs 127.0.0.1')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    best = ()
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    vv = tuple(int(x) for x in ver.split('.') if x.isdigit())
                except ValueError:
                    continue
                if vv and vv[0] == chrome_major and vv > best:
                    best, drv_path = vv, exe
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(180)
    return drv


def open_dialog(drv):
    """打开用例试听弹窗（网关偶发慢/SSE 拥塞时整页重试）。"""
    last = None
    for attempt in range(3):
        drv.get(BASE + '/testcases/by-group?search=' + urllib.parse.quote(CASE_NAME))
        try:
            WebDriverWait(drv, 240).until(
                lambda d: d.find_elements(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP_NAME))
        except Exception as err:  # noqa: BLE001
            last = err
            log('[open_dialog] 第 %d 次分组未渲染，重试' % (attempt + 1))
            continue
        time.sleep(0.8)
        js_click(drv, drv.find_element(
            By.XPATH, "//span[normalize-space(.)='%s']" % GROUP_NAME))
        try:
            btn = WebDriverWait(drv, 120).until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(., '%s')][.//button[@aria-label='预览音频']]//button[@aria-label='预览音频']"
                % CASE_NAME,
            )))
        except Exception as err:  # noqa: BLE001
            last = err
            log('[open_dialog] 第 %d 次用例卡未渲染，重试' % (attempt + 1))
            continue
        time.sleep(0.4)
        js_click(drv, btn)
        WebDriverWait(drv, 30).until(
            EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
        time.sleep(0.6)
        return
    raise last


def dialog_text(drv):
    return drv.find_element(By.XPATH, "//div[@role='dialog']").text


def wait_dialog_text(drv, needle, timeout=180):
    WebDriverWait(drv, timeout).until(lambda d: needle in dialog_text(d))
    return dialog_text(drv)


def net_entries(drv, needle):
    return [e for e in drv.execute_script('return window.__net || []')
            if needle in (e.get('url') or '')]


def set_theme(drv, dark):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
        'dark' if dark else 'light',
    )
    drv.get('about:blank')
    time.sleep(0.3)


def main():
    drv = _driver()
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    result = {'case_id': CASE_ID, 'base': BASE}
    try:
        # ---------- 浅色：浏览器播放 ----------
        open_dialog(drv)
        result['light_config'] = dialog_text(drv)
        log('[light] 配置态:\n' + result['light_config'])
        drv.save_screenshot(os.path.join(ART, '01-config-light.png'))

        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        player_text = wait_dialog_text(drv, '测试用例预览｜')
        net = net_entries(drv, '/testcases/%s/preview' % CASE_ID)
        result['light_preview_req'] = net
        log('[light] preview 请求: %s' % json.dumps(net, ensure_ascii=False))
        time.sleep(2.0)
        result['light_player'] = dialog_text(drv)
        result['light_time'] = drv.execute_script(
            "const p=document.querySelector('[data-testid=player-time]'); return p?p.textContent:null")
        result['light_audio'] = drv.execute_script("""
        const el = document.querySelector('[data-testid=case-preview-audio]');
        if (!el) return null;
        return {src: el.currentSrc || el.src, duration: el.duration, paused: el.paused,
                error: el.error ? el.error.code : null, readyState: el.readyState};""")
        log('[light] 播放器文案:\n' + result['light_player'])
        log('[light] 时间显示: %s audio: %s' % (result['light_time'], json.dumps(result['light_audio'], ensure_ascii=False)))
        drv.save_screenshot(os.path.join(ART, '02-player-browser-light.png'))

        # 停止
        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[@aria-label='停止']"))
        time.sleep(0.8)

        # ---------- 浅色：实验室播放（偏移量 1s） ----------
        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='返回试听配置']"))
        wait_dialog_text(drv, '音频试听配置', timeout=20)
        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//label[contains(normalize-space(.), '实验室播放')]"))
        time.sleep(0.4)
        off = drv.find_element(By.XPATH, "//div[@role='dialog']//input[@aria-label='偏移量秒数']")
        off.click()
        off.send_keys('a')
        off.send_keys('1')
        time.sleep(0.3)
        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        lab_text = wait_dialog_text(drv, '播放设备（实验室播放）')
        time.sleep(1.0)
        net_lab = net_entries(drv, '/testcases/%s/preview' % CASE_ID)
        result['lab_preview_req'] = net_lab[-1] if net_lab else None
        result['lab_player'] = lab_text
        log('[light] 实验室请求: %s' % json.dumps(result['lab_preview_req'], ensure_ascii=False))
        log('[light] 实验室播放器:\n' + lab_text)
        drv.save_screenshot(os.path.join(ART, '03-player-lab-light.png'))

        js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[@aria-label='停止']"))
        time.sleep(1.0)
        stops = net_entries(drv, '/testcases/%s/stop_preview' % CASE_ID)
        result['stop_preview_req'] = stops[-1] if stops else None
        log('[light] stop_preview: %s' % json.dumps(result['stop_preview_req'], ensure_ascii=False))
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.5)

        # ---------- 深色 ----------
        set_theme(drv, True)
        open_dialog(drv)
        drv.save_screenshot(os.path.join(ART, '04-config-dark.png'))
        js_click(drv, drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始试听']"))
        wait_dialog_text(drv, '测试用例预览｜')
        time.sleep(1.5)
        result['dark_time'] = drv.execute_script(
            "const p=document.querySelector('[data-testid=player-time]'); return p?p.textContent:null")
        result['dark_player'] = dialog_text(drv)
        drv.save_screenshot(os.path.join(ART, '05-player-dark.png'))
        log('[dark] 时间显示: %s' % result['dark_time'])
        set_theme(drv, False)

        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log('RESULT_KEYS ' + ','.join(result.keys()))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
