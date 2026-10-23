# -*- coding: utf-8 -*-
"""INT-1613 实测取证：文件夹导入 JSON 用例 rounds → 多轮用例 + 按分组末文件建用例。

场景（真实 docker 后端 15000 / 主库 intelligent_audio_test）：
  s1  1 个音频 + rounds 长度 3 的 JSON → 1 个 3 轮用例
  s2  同组 3 个音频 + rounds 长度 3 的 JSON → 只建 1 个用例（末文件 merge 时建）
  s3  无 JSON、同文件夹 2 个音频 → 1 个用例 1 轮多音频（回归）
  s4  无 JSON、1 个音频 → 1 个用例 1 轮（回归）
证据：merge 请求体 rounds 结构 + 响应 + GET /testcases/{id}；浅/深色截图（多轮用例抽屉）；
      旧 Vue（8080）同弹窗对照图。写数据全部「接线测试_INT1613」前缀，结束前删除。
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5321')
VUE_BASE = os.environ.get('VUE_BASE', 'http://127.0.0.1:8080')
GATEWAY = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1613'
SRC = r'D:\00_temp\int1613'
PREFIX = '接线测试_INT1613'
DEVICE_ID = int(os.environ.get('INT1613_DEVICE_ID', '3'))
DRIVER = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
  let reqText = null;
  try { reqText = init && init.body; } catch (e) {}
  const res = await __origFetch.apply(this, arguments);
  const rec = {url: url, method: method, status: res.status, t: Date.now()};
  if (typeof reqText === 'string' && reqText) {
    try { rec.reqBody = JSON.parse(reqText); } catch (e) { rec.reqRaw = reqText.slice(0, 500); }
  }
  try { rec.respText = await res.clone().text(); } catch (e) {}
  window.__net.push(rec);
  return res;
};
"""


def log(msg):
    print(msg, flush=True)


def health(tag):
    with urllib.request.urlopen(GATEWAY + '/health', timeout=20) as resp:
        data = json.load(resp)
    log('[health:%s] %s' % (tag, data))
    assert data.get('database') == 'intelligent_audio_test', data
    return data


def _api(path, method='GET', body=None):
    payload = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        GATEWAY + path, method=method, data=payload,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode('utf-8')
            status = resp.status
    except urllib.error.HTTPError as err:
        text = err.read().decode('utf-8')
        status = err.code
    try:
        data = json.loads(text)
    except Exception:
        data = {'raw': text}
    return status, data


def api_data(path, method='GET', body=None):
    status, data = _api(path, method, body)
    return status, (data.get('data') if isinstance(data, dict) else data)


def total_audios():
    _, data = api_data('/api/v1/audios', 'POST', {'page': 1, 'per_page': 1, 'deleted': False})
    return (data or {}).get('total')


def total_testcases():
    _, data = api_data('/api/v1/testcases?page=1&per_page=1')
    return (data or {}).get('total')


def find_cases(keyword):
    _, data = api_data('/api/v1/testcases?page=1&per_page=100&keyword=' + urllib.parse.quote(keyword))
    return (data or {}).get('items') or []


def cleanup():
    """删除本 run 创建的「接线测试_INT1613」用例与音频。"""
    cases = find_cases(PREFIX)
    for case in cases:
        st, _ = _api('/api/v1/testcases/%s' % case['id'], 'DELETE')
        log('cleanup case %s (%s) -> %s' % (case['id'], case.get('name'), st))
    _, data = api_data('/api/v1/audios', 'POST', {'page': 1, 'per_page': 200, 'keyword': PREFIX, 'deleted': False})
    for item in (data or {}).get('items') or []:
        st, _ = _api('/api/v1/audios/%s' % item['id'], 'DELETE')
        log('cleanup audio %s (%s) -> %s' % (item['id'], item.get('name'), st))
    time.sleep(1.0)
    left_cases = find_cases(PREFIX)
    _, data = api_data('/api/v1/audios', 'POST', {'page': 1, 'per_page': 200, 'keyword': PREFIX, 'deleted': False})
    left_audios = (data or {}).get('items') or []
    log('cleanup 后残留：用例 %d / 音频 %d' % (len(left_cases), len(left_audios)))
    return len(left_cases), len(left_audios)


def driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    drv = webdriver.Chrome(service=Service(DRIVER), options=o)
    drv.set_script_timeout(300)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(2)
    try:
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    except Exception:
        pass
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def open_audio_page(drv):
    drv.get(BASE + '/audio-import')
    WebDriverWait(drv, 60).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(normalize-space(.), '批量从文件夹导入')]"))
    time.sleep(2)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def open_folder_dialog(drv):
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '批量从文件夹导入')]"))
    WebDriverWait(drv, 15).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.8)


def select_folder(drv, path):
    inp = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[type='file']")
    drv.execute_script("arguments[0].style.display='block';", inp)
    inp.send_keys(path)
    WebDriverWait(drv, 20).until(lambda d: '已选' in d.find_element(By.XPATH, "//div[@role='dialog']").text)
    time.sleep(0.8)


def ensure_generate_case(drv):
    """开关是否已开：开启后才有「上传完成后按分组末文件自动生成测试用例」提示与标签/维度区。"""
    dialog = drv.find_element(By.XPATH, "//div[@role='dialog']")
    if '按分组末文件自动生成测试用例' in dialog.text:
        return
    js_click(drv, drv.find_element(By.ID, 'upload-gen-case'))
    WebDriverWait(drv, 10).until(
        lambda d: '按分组末文件自动生成测试用例' in d.find_element(By.XPATH, "//div[@role='dialog']").text)
    time.sleep(0.5)


def pick_device(drv):
    """播放设备下拉选第一台真实设备（§5.7.7 逐轮 playback_device_id）；失败不阻塞主流程。"""
    try:
        trigger = WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.ID, 'upload-playback-device')))
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", trigger)
        js_click(drv, trigger)
        WebDriverWait(drv, 15).until(
            lambda d: any(o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")))
        options = [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.text.strip()]
        text = options[0].text.strip()
        js_click(drv, options[0])
        time.sleep(0.5)
        return text
    except Exception as err:
        log('播放设备选择失败（继续）：%s' % err)
        return None


def net_since(drv, start):
    return drv.execute_script('return window.__net.slice(arguments[0])', start) or []


def run_scenario(drv, name, folder, shot=None):
    log('--- 场景 %s（%s）' % (name, folder))
    open_folder_dialog(drv)
    select_folder(drv, os.path.join(SRC, folder))
    ensure_generate_case(drv)
    device_text = pick_device(drv)
    if shot:
        drv.save_screenshot(os.path.join(ART, shot))
        log('截图 %s（设备=%s）' % (shot, device_text))
    start = drv.execute_script('return (window.__net || []).length')
    js_click(drv, drv.find_element(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始导入']"))
    deadline = time.time() + 150
    while time.time() < deadline:
        if not drv.find_elements(By.XPATH, "//div[@role='dialog']"):
            break
        time.sleep(2)
    else:
        body = drv.find_element(By.TAG_NAME, 'body').text
        drv.save_screenshot(os.path.join(ART, 'debug-timeout-%s.png' % name))
        raise AssertionError('导入后弹窗未关闭（%s）：%s' % (name, body[-500:]))
    time.sleep(2)
    events = net_since(drv, start)
    merges = [e for e in events if '/audios/upload/merge' in e.get('url', '')]
    log('%s merge 请求 %d 次：%s' % (name, len(merges), [(m.get('status'), (m.get('reqBody') or {}).get('create_test_case')) for m in merges]))
    log('%s 全部请求：%s' % (name, [(e.get('method'), e.get('url', '')[-60:], e.get('status')) for e in events]))
    body_now = drv.find_element(By.TAG_NAME, 'body').text
    log('%s 页面尾部文本：%s' % (name, body_now[-400:]))
    return {'name': name, 'deviceText': device_text, 'merges': merges,
            'events': [e for e in events if '/api/v1/' in e.get('url', '')]}


def open_case_drawer(drv, case_name):
    drv.get(BASE + '/testcases')
    WebDriverWait(drv, 120).until(lambda d: d.find_elements(By.XPATH, "//input[@aria-label='搜索用例']"))
    time.sleep(1.5)
    box = drv.find_element(By.XPATH, "//input[@aria-label='搜索用例']")
    js_click(drv, box)
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(case_name)
    # 15000 用例列表慢（首屏请求可达 50s+），按「编辑用例」按钮出现判定结果已渲染
    WebDriverWait(drv, 180).until(lambda d: d.find_elements(By.XPATH, "//button[@aria-label='编辑用例']"))
    time.sleep(1.5)
    buttons = drv.find_elements(By.XPATH, "//button[@aria-label='编辑用例']")
    assert buttons, '未找到「编辑用例」按钮（%s）' % case_name
    js_click(drv, buttons[0])
    WebDriverWait(drv, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(2)
    text = drv.find_element(By.XPATH, "//div[@role='dialog']").text
    return text


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    drv.get('about:blank')
    time.sleep(0.6)


def evidence_screenshot(drv, summary):
    """把 merge 请求体 / 响应 / GET 用例详情渲染成一页 Network 证据并截图。"""
    rows = []
    for scen in summary['scenarios']:
        for merge in scen['merges']:
            body = merge.get('reqBody') or {}
            cfg = body.get('test_case_config') or {}
            rounds = cfg.get('rounds') or []
            compact_rounds = [
                {'round_number': r.get('round_number'),
                 'audios': [{k: a.get(k) for k in ('audio_name', 'play_order', 'audio_id', 'playback_device_id') if a.get(k) is not None}
                            for a in (r.get('audios') or [])]}
                for r in rounds
            ]
            rows.append({
                'scenario': scen['name'],
                'status': merge.get('status'),
                'create_test_case': body.get('create_test_case'),
                'default_playback_device_id': body.get('default_playback_device_id'),
                'rounds': compact_rounds,
            })
    detail = summary.get('detail_rounds') or {}
    html = ['<html><head><meta charset="utf-8"><style>',
            'body{font-family:Consolas,monospace;font-size:12px;padding:12px;background:#0b1020;color:#d8e1f0}',
            'h2{font-size:15px;color:#7dd3fc;margin:8px 0}pre{white-space:pre-wrap;background:#111a2e;padding:8px;border-radius:6px;border:1px solid #24314d}',
            '</style></head><body>',
            '<h2>INT-1613 Network 证据：POST /api/v1/audios/upload/merge（真实 docker 后端 15000）</h2>',
            '<pre>%s</pre>' % json.dumps(rows, ensure_ascii=False, indent=1),
            '<h2>GET /api/v1/testcases/{id} → config.rounds（真实回读）</h2>',
            '<pre>%s</pre>' % json.dumps(detail, ensure_ascii=False, indent=1),
            '</body></html>']
    drv.switch_to.new_window('tab')
    drv.get('about:blank')
    drv.set_window_size(1500, 1250)
    drv.execute_script('document.open();document.write(arguments[0]);document.close();', ''.join(html))
    time.sleep(1)
    path = os.path.join(ART, '04-network-merge-payload.png')
    drv.save_screenshot(path)
    log('截图 %s' % path)
    drv.close()
    drv.switch_to.window(drv.window_handles[0])


def vue_comparison(drv):
    drv.get(VUE_BASE + '/audio-import')
    time.sleep(2)
    if 'audio-import' not in drv.current_url:
        drv.get(VUE_BASE + '/#/audio-import')
    time.sleep(5)
    try:
        drv.save_screenshot(os.path.join(ART, '05-vue-audio-import.png'))
        btn = WebDriverWait(drv, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '批量从文件夹导入')]")))
        js_click(drv, btn)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ART, '06-vue-folder-dialog.png'))
        log('旧 Vue 对照图已截')
    except Exception as err:
        log('旧 Vue 对照截图失败：%s' % err)


def do_imports(drv, summary):
    open_audio_page(drv)
    failures = []
    for name, folder, shot in [
        ('s1-1音频+3轮JSON', '接线测试_INT1613_s1', '01-folder-dialog-light.png'),
        ('s2-3音频+3轮JSON', '接线测试_INT1613_s2', None),
        ('s3-无JSON-2音频', '接线测试_INT1613_s3', None),
        ('s4-无JSON-1音频', '接线测试_INT1613_s4', None),
    ]:
        try:
            summary['scenarios'].append(run_scenario(drv, name, folder, shot))
        except Exception as err:
            failures.append('%s: %s' % (name, err))
            log('场景失败 %s: %s' % (name, err))
            open_audio_page(drv)
    summary['import_failures'] = failures

    # 真实回读：本 run 创建的用例与轮次
    time.sleep(2)
    cases = find_cases(PREFIX)
    detail = {}
    for case in cases:
        _, d = api_data('/api/v1/testcases/%s' % case['id'])
        rounds = ((d or {}).get('config') or {}).get('rounds') or []
        detail[case['name']] = [{
            'round_number': r.get('round_number'),
            'audios': [{k: a.get(k) for k in ('audio_id', 'audio_name', 'play_order', 'playback_device_id') if a.get(k) is not None}
                       for a in (r.get('audios') or [])],
        } for r in rounds]
    summary['cases'] = [{'id': c['id'], 'name': c['name'], 'group_name': c.get('group_name'),
                         'rounds': len(((c.get('config') or {}).get('rounds') or []))} for c in cases]
    summary['detail_rounds'] = detail
    log('本 run 用例：%s' % json.dumps(summary['cases'], ensure_ascii=False))
    log('逐用例 rounds：%s' % json.dumps(detail, ensure_ascii=False))
    return cases


def do_shots(drv, summary):
    cases = summary.get('cases') or []
    detail = summary.get('detail_rounds') or {}
    assert cases, 'summary 里没有用例（先跑 STAGE=import）'
    three_round_case = next((c for c in cases if len(detail.get(c['name'], [])) == 3), None)
    assert three_round_case, '未找到 3 轮用例'
    set_theme(drv, 'light')
    drawer_text = open_case_drawer(drv, three_round_case['name'])
    log('抽屉文本片段：%s' % drawer_text.replace(chr(10), ' | ')[:300])
    for n in (1, 2, 3):
        assert ('第 %d 轮' % n) in drawer_text or ('第%d轮' % n) in drawer_text, drawer_text
    drv.save_screenshot(os.path.join(ART, '02-case-3-rounds-light.png'))

    set_theme(drv, 'dark')
    open_case_drawer(drv, three_round_case['name'])
    drv.save_screenshot(os.path.join(ART, '03-case-3-rounds-dark.png'))

    set_theme(drv, 'light')
    evidence_screenshot(drv, summary)
    vue_comparison(drv)


def main():
    stage = os.environ.get('STAGE', 'all')
    summary_path = os.path.join(ART, 'summary.json')
    summary = json.load(open(summary_path, encoding='utf-8')) if stage in ('shots', 'cleanup') else {'scenarios': []}

    if stage == 'cleanup':
        left = cleanup()
        log('cleanup: %s' % (left,))
        return

    if stage in ('all', 'import'):
        health('start')
        log('总音频 %s / 总用例 %s' % (total_audios(), total_testcases()))
        cleanup()
        health('before-screenshots')

    drv = driver()
    try:
        login(drv)
        if stage in ('all', 'import'):
            do_imports(drv, summary)
        if stage in ('all', 'shots'):
            do_shots(drv, summary)
    finally:
        if stage == 'all':
            summary['left_after_cleanup'] = cleanup()
            summary['health_end'] = health('end')
        with open(summary_path, 'w', encoding='utf-8') as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
        drv.quit()
    log('done stage=%s' % stage)


if __name__ == '__main__':
    main()
