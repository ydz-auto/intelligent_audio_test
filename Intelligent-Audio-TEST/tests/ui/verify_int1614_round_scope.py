# -*- coding: utf-8 -*-
"""INT-1614 实测取证：上传 / 批量从文件夹导入弹窗 评估维度 + 播放设备 轮次范围三档。

场景（真实 docker 栈：网关 15000 / 主库 intelligent_audio_test；前端 dev 5322 代理 15000）：
  ui     两个弹窗的控件态：上传窗 N=1 两档禁用 + Tooltip；文件夹窗 N=3 逐轮 Tab / 角标 / 快捷操作三件
  upload 四个载荷场景的 merge 请求体 + GET /testcases/{id} 回读：
         s1 上传窗·所有轮次（N=1）
         s2 文件夹·所有轮次（N=3）
         s3 文件夹·指定轮次（只勾第 2 轮）
         s4 文件夹·逐轮设置（第 1 轮设备/维度 → 第 2 轮复制 + 换设备 → 第 3 轮清空）
证据：浅 / 深色截图（两窗 × 三档 + 逐轮 Tab + 快捷操作弹层）、Network 证据页、GET 回读。
写数据全部「接线测试_INT1614」前缀，结束前删除。
"""
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5322')
GATEWAY = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1614'
SRC = r'D:\00_temp\int1614'
PREFIX = '接线测试_INT1614'
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
    try { rec.reqBody = JSON.parse(reqText); } catch (e) { rec.reqRaw = reqText.slice(0, 800); }
  }
  try { rec.respText = await res.clone().text(); } catch (e) {}
  window.__net.push(rec);
  return res;
};
"""


def log(msg):
    print(msg, flush=True)


def health(tag):
    with urllib.request.urlopen(GATEWAY + '/health', timeout=30) as resp:
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
        with urllib.request.urlopen(req, timeout=180) as resp:
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


def find_cases(keyword):
    _, data = api_data('/api/v1/testcases?page=1&per_page=100&keyword=' + urllib.parse.quote(keyword))
    return (data or {}).get('items') or []


def cleanup():
    cases = find_cases(PREFIX)
    for case in cases:
        st, _ = _api('/api/v1/testcases/%s' % case['id'], 'DELETE')
        log('cleanup case %s (%s) -> %s' % (case['id'], case.get('name'), st))
    _, data = api_data('/api/v1/audios', 'POST',
                       {'page': 1, 'per_page': 200, 'keyword': PREFIX, 'deleted': False})
    for item in (data or {}).get('items') or []:
        st, _ = _api('/api/v1/audios/%s' % item['id'], 'DELETE')
        log('cleanup audio %s (%s) -> %s' % (item['id'], item.get('name'), st))
    time.sleep(1.0)
    return len(find_cases(PREFIX))


def wav_bytes(seconds=1.0, rate=8000):
    frames = int(seconds * rate)
    data = b''.join(struct.pack('<h', 0) for _ in range(frames))
    import io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return buf.getvalue()


def build_fixtures():
    """s1 单音频 / s2 3 音频 + 3 轮 JSON / s3 同 s2（指定轮次）/ s4 同 s2（逐轮设置）"""
    os.makedirs(SRC, exist_ok=True)
    names = ['%s_a1.wav' % PREFIX, '%s_a2.wav' % PREFIX, '%s_a3.wav' % PREFIX]
    for name in names:
        with open(os.path.join(SRC, name), 'wb') as fh:
            fh.write(wav_bytes())
    for folder in ('s2_all', 's3_specific', 's4_per_round'):
        d = os.path.join(SRC, folder)
        os.makedirs(d, exist_ok=True)
        for name in names:
            with open(os.path.join(d, name), 'wb') as fh:
                fh.write(wav_bytes())
        case = {'rounds': [{'segments': [{'audio': names[i]}]} for i in range(3)]}
        with open(os.path.join(d, '%s_%s_case.json' % (PREFIX, folder)), 'w', encoding='utf-8') as fh:
            json.dump(case, fh, ensure_ascii=False, indent=1)
    log('fixtures: %s' % names)


def driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1100')
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
    WebDriverWait(drv, 60).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def open_audio_page(drv):
    drv.get(BASE + '/audio-import')
    WebDriverWait(drv, 90).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(normalize-space(.), '批量从文件夹导入')]"))
    time.sleep(2)


def dialog(drv):
    return drv.find_element(By.XPATH, "//div[@role='dialog']")


def open_upload_dialog(drv):
    js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='上传音频']"))
    WebDriverWait(drv, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.8)


def open_folder_dialog(drv):
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '批量从文件夹导入')]"))
    WebDriverWait(drv, 20).until(EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.8)


def select_folder(drv, path):
    inp = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[type='file']")
    drv.execute_script("arguments[0].style.display='block';", inp)
    inp.send_keys(path)
    WebDriverWait(drv, 30).until(lambda d: '已选' in dialog(d).text)
    time.sleep(1.2)


def select_audio_file(drv, path):
    inp = drv.find_element(By.CSS_SELECTOR, "div[role='dialog'] input[type='file']")
    drv.execute_script("arguments[0].style.display='block';", inp)
    inp.send_keys(path)
    WebDriverWait(drv, 30).until(lambda d: '已选择' in dialog(d).text or '已选' in dialog(d).text)
    time.sleep(0.8)


def ensure_generate_case(drv):
    # 判据用「标签」输入框（#upload-tags）：弹窗描述里恒有「按分组末文件自动生成测试用例」，会误判已开启
    if drv.find_elements(By.ID, 'upload-tags'):
        return
    js_click(drv, drv.find_element(By.ID, 'upload-gen-case'))
    WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.ID, 'upload-tags'))
    time.sleep(1.0)


JS_BLOCK = r"""
window.__scopeBlock = function(name) {
  const radio = document.querySelector("input[name='" + name + "']");
  if (!radio) return null;
  let node = radio;
  while (node && !(node.classList && node.classList.contains('space-y-2'))) node = node.parentElement;
  return node;
};
window.__clickText = function(root, text, tag) {
  if (!root) return false;
  const nodes = root.querySelectorAll(tag || 'button,label,span,div');
  for (const el of nodes) {
    if ((el.textContent || '').trim() === text) { el.click(); return true; }
  }
  return false;
};
"""


def inject_helpers(drv):
    drv.execute_script(JS_BLOCK)


def scope_block(drv, name):
    return drv.execute_script('return window.__scopeBlock(arguments[0])', name)


def click_radio(drv, name, index):
    """轮次范围三档 radio（0=所有轮次 1=指定轮次 2=逐轮设置）"""
    el = drv.execute_script(
        "const b = window.__scopeBlock(arguments[0]);"
        "if (!b) return 'NO_BLOCK';"
        "const rs = b.querySelectorAll(\"input[type='radio']\");"
        "if (!rs[arguments[1]]) return null; rs[arguments[1]].click(); return rs[arguments[1]].disabled;",
        name, index)
    time.sleep(0.5)
    return el


def radio_disabled(drv, name, index):
    return drv.execute_script(
        "const b = window.__scopeBlock(arguments[0]);"
        "if (!b) return 'NO_BLOCK';"
        "const rs = b.querySelectorAll(\"input[type='radio']\");"
        "return rs[arguments[1]] ? rs[arguments[1]].disabled : null;", name, index)


def check_specific_round(drv, name, round_no):
    drv.execute_script(
        "const b = window.__scopeBlock(arguments[0]);"
        "const labels = Array.from(b.querySelectorAll('label'));"
        "const target = labels.find(l => (l.textContent||'').trim() === arguments[1]);"
        "if (!target) return false;"
        "const cb = target.querySelector(\"[role='checkbox']\") || target.querySelector('input');"
        "if (!cb) return false; cb.click(); return true;", name, '第%d轮' % round_no)
    time.sleep(0.4)


def click_round_tab(drv, name, round_no):
    drv.execute_script(
        "const b = window.__scopeBlock(arguments[0]);"
        "const btns = Array.from(b.querySelectorAll('button')).filter(x => (x.textContent||'').indexOf(arguments[1]) === 0);"
        "if (btns[0]) btns[0].click();", name, '第%d轮' % round_no)
    time.sleep(0.5)


def tab_texts(drv, name):
    return drv.execute_script(
        "const b = window.__scopeBlock(arguments[0]);"
        "return Array.from(b.querySelectorAll('button')).map(x => (x.textContent||'').trim());", name)


def hub_buttons(drv):
    """快捷操作三件：按出现顺序，前 3 个=维度段，后 3 个=设备段"""
    return drv.execute_script(
        "return Array.from(document.querySelectorAll(\"div[role='dialog'] button\"))"
        ".filter(b => ['从其他轮次复制','清空当前轮次','应用到所有轮次'].some(t => (b.textContent||'').trim() === t))"
        ".map(b => ({text: (b.textContent||'').trim(), disabled: b.disabled}));")


def click_hub(drv, text, nth=0):
    drv.execute_script(
        "const bs = Array.from(document.querySelectorAll(\"div[role='dialog'] button\"))"
        ".filter(b => (b.textContent||'').trim() === arguments[0]);"
        "if (bs[arguments[1]]) bs[arguments[1]].click();", text, nth)
    time.sleep(0.6)


def confirm_dialog_text(drv):
    try:
        els = drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']")
        return els[0].text if els else ''
    except Exception:
        return ''


def click_confirm(drv, text='确定'):
    drv.execute_script(
        "const d = document.querySelector(\"[role='alertdialog']\");"
        "if (!d) return;"
        "const btn = Array.from(d.querySelectorAll('button')).find(b => (b.textContent||'').trim() === arguments[0]);"
        "if (btn) btn.click();", text)
    time.sleep(0.8)


def pick_dimension(drv, index=0, within_multi=False):
    """点维度云里第 index 个 chip（主维度，含其子维度联动）；within_multi=True 时在多轮整体小节内点。"""
    return drv.execute_script(r"""
const root = document.querySelector("div[role='dialog']");
let scope;
if (arguments[1]) {
  scope = Array.from(root.querySelectorAll('div')).find(d =>
    (d.className||'').indexOf('border-border') >= 0 &&
    (d.textContent||'').indexOf('多轮整体评估维度') >= 0);
} else {
  scope = root.querySelector('.max-h-72');
}
if (!scope) return 'NO_SCOPE';
const chips = Array.from(scope.querySelectorAll('button[aria-pressed]'));
const chip = chips[arguments[0]];
if (!chip) return 'NO_CHIP';
chip.click();
return (chip.textContent||'').trim();
""", index, within_multi)


def selected_dim_count(drv):
    return drv.execute_script(r"""
const root = document.querySelector("div[role='dialog']");
const m = (root.textContent||'').match(/已选\s*(\d+)\s*个维度/);
return m ? Number(m[1]) : null;
""")


def pick_device(drv, index=0):
    last = None
    for _ in range(3):
        try:
            trigger = WebDriverWait(drv, 15).until(
                EC.presence_of_element_located((By.ID, 'upload-playback-device')))
            drv.execute_script("arguments[0].scrollIntoView({block:'center'})", trigger)
            time.sleep(0.4)
            try:
                trigger.click()
            except Exception:
                js_click(drv, trigger)
            WebDriverWait(drv, 12).until(
                lambda d: any(o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")))
            options = [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.text.strip()]
            text = options[index].text.strip()
            js_click(drv, options[index])
            time.sleep(0.6)
            return text
        except Exception as err:
            last = err
            time.sleep(1.0)
    log('设备选择失败：%s' % last)
    return None


def net_since(drv, start):
    return drv.execute_script('return window.__net.slice(arguments[0])', start)


def net_mark(drv):
    return drv.execute_script('return (window.__net || []).length')


def run_upload(drv, timeout=240):
    start = net_mark(drv)
    label = '开始上传' if '开始上传' in dialog(drv).text else '开始导入'
    js_click(drv, drv.find_element(
        By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='%s']" % label))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not drv.find_elements(By.XPATH, "//div[@role='dialog']"):
            break
        time.sleep(2)
    else:
        raise AssertionError('上传后弹窗未关闭')
    time.sleep(2)
    events = net_since(drv, start)
    merges = [e for e in events if '/audios/upload/merge' in e.get('url', '')]
    logs = [(e.get('status'), e.get('url', '')[-45:]) for e in events if '/api/v1/' in e.get('url', '')]
    for e in events:
        if '/api/v1/' in e.get('url', '') and (e.get('status') or 0) >= 400:
            log('FAIL %s %s -> %s' % (e.get('status'), e.get('url', '')[-50:], (e.get('respText') or '')[:300]))
    log('merge %d 次；请求概览 %s' % (len(merges), logs))
    for m in merges:
        body = m.get('reqBody') or {}
        log('merge status=%s create=%s default_device=%s dims=%s' % (
            m.get('status'), body.get('create_test_case'),
            body.get('default_playback_device_id'),
            json.dumps(body.get('dimensions'), ensure_ascii=False)[:300]))
        log('rounds=%s' % json.dumps(
            (body.get('test_case_config') or {}).get('rounds'), ensure_ascii=False)[:900])
        log('merge resp=%s' % (m.get('respText') or '')[:700])
    return {'merges': merges, 'events': events}


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('截图 %s' % path)


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    drv.refresh()
    time.sleep(3)


def case_rounds(case_id):
    _, d = api_data('/api/v1/testcases/%s' % case_id)
    cfg = (d or {}).get('config') or {}
    return {
        'rounds': [{
            'round_number': r.get('round_number'),
            'audios': [{k: a.get(k) for k in ('audio_name', 'play_order', 'playback_device_id') if a.get(k) is not None}
                       for a in (r.get('audios') or [])],
            'evaluation': r.get('evaluation'),
        } for r in (cfg.get('rounds') or [])],
        'dimensions': [{k: dim.get(k) for k in ('id', 'name', 'weight', 'round_scope') if dim.get(k) is not None}
                       for dim in (cfg.get('dimensions') or [])],
    }


def evidence_page(drv, summary):
    rows = []
    for scen in summary['scenarios']:
        for merge in scen['merges']:
            body = merge.get('reqBody') or {}
            cfg = body.get('test_case_config') or {}
            rows.append({
                'scenario': scen['name'],
                'status': merge.get('status'),
                'default_playback_device_id': body.get('default_playback_device_id'),
                'top_dimensions': body.get('dimensions'),
                'rounds': [{
                    'round_number': r.get('round_number'),
                    'audios': [{k: a.get(k) for k in ('audio_name', 'play_order', 'playback_device_id') if a.get(k) is not None}
                               for a in (r.get('audios') or [])],
                    'evaluation': r.get('evaluation'),
                } for r in (cfg.get('rounds') or [])],
            })
    html = ['<html><head><meta charset="utf-8"><style>',
            'body{font-family:Consolas,monospace;font-size:12px;padding:12px;background:#0b1020;color:#d8e1f0}',
            'h2{font-size:15px;color:#7dd3fc;margin:8px 0}pre{white-space:pre-wrap;background:#111a2e;padding:8px;'
            'border-radius:6px;border:1px solid #24314d}',
            '</style></head><body>',
            '<h2>INT-1614 Network：POST /api/v1/audios/upload/merge（docker 15000 · 主库 intelligent_audio_test）</h2>',
            '<pre>%s</pre>' % json.dumps(rows, ensure_ascii=False, indent=1),
            '<h2>GET /api/v1/testcases/{id} → config.rounds / config.dimensions（真实回读）</h2>',
            '<pre>%s</pre>' % json.dumps(summary.get('readback') or {}, ensure_ascii=False, indent=1),
            '</body></html>']
    drv.switch_to.new_window('tab')
    drv.get('about:blank')
    drv.set_window_size(1500, 1400)
    drv.execute_script('document.open();document.write(arguments[0]);document.close();', ''.join(html))
    time.sleep(1)
    shot(drv, '05-network-evidence.png')
    drv.close()
    drv.switch_to.window(drv.window_handles[0])


def main():
    stage = os.environ.get('STAGE', 'all')
    build_fixtures()
    health('start')
    log('现有用例总数(前): %s' % ((api_data('/api/v1/testcases?page=1&per_page=1')[1] or {}).get('total')))
    cleanup()

    drv = driver()
    summary = {'scenarios': [], 'readback': {}}
    try:
        login(drv)
        inject_helpers(drv)
        if stage in ('all', 'ui'):
            do_ui_checks(drv)
        if stage in ('all', 'upload'):
            do_uploads(drv, summary)
        if stage == 's1':
            do_uploads(drv, summary, only=['s1'])
        with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    health('end')
    log('残留清理：%s' % cleanup())
    log('done stage=%s' % stage)


# ------------------------------------------------------------------ 控件态
def do_ui_checks(drv):
    log('=== UI：上传窗 N=1 收敛')
    open_audio_page(drv)
    open_upload_dialog(drv)
    ensure_generate_case(drv)
    inject_helpers(drv)
    dis_specific = radio_disabled(drv, 'upload-dimension-round', 1)
    dis_per_round = radio_disabled(drv, 'upload-dimension-round', 2)
    dis_specific_dev = radio_disabled(drv, 'upload-device-round', 1)
    dis_per_round_dev = radio_disabled(drv, 'upload-device-round', 2)
    log('上传窗禁用态：维度 specific=%s per_round=%s；设备 specific=%s per_round=%s' % (
        dis_specific, dis_per_round, dis_specific_dev, dis_per_round_dev))
    assert dis_specific and dis_per_round and dis_specific_dev and dis_per_round_dev, '上传窗两档未禁用'
    # Tooltip：hover 禁用档（base-ui tooltip，桌面 hover 触发）
    label = drv.execute_script(
        "const b = window.__scopeBlock('upload-dimension-round');"
        "return Array.from(b.querySelectorAll('label')).find(l => (l.textContent||'').indexOf('指定轮次') >= 0);")
    if label is not None:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(drv).move_to_element(label).perform()
        time.sleep(1.5)
    body = drv.find_element(By.TAG_NAME, 'body').text
    has_tooltip = '本次上传生成的用例为单轮' in body
    log('上传窗 Tooltip 命中：%s' % has_tooltip)
    shot(drv, '01-upload-dialog-all-light.png')

    set_theme(drv, 'dark')
    open_audio_page(drv)
    open_upload_dialog(drv)
    ensure_generate_case(drv)
    shot(drv, '02-upload-dialog-all-dark.png')
    set_theme(drv, 'light')

    log('=== UI：文件夹导入 N=3 三档 + 逐轮 Tab + 快捷操作')
    open_audio_page(drv)
    open_folder_dialog(drv)
    select_folder(drv, os.path.join(SRC, 's2_all'))
    ensure_generate_case(drv)
    inject_helpers(drv)
    time.sleep(1.5)
    click_radio(drv, 'upload-dimension-round', 2)
    tabs = tab_texts(drv, 'upload-dimension-round')
    log('维度逐轮 Tab：%s' % tabs)
    assert sum(1 for t in tabs if t.startswith('第')) == 3, tabs
    hub_dim = hub_buttons(drv)
    log('维度段快捷操作三件：%s' % hub_dim)
    assert len(hub_dim) == 3, hub_dim
    click_hub(drv, '清空当前轮次', 0)
    log('清空确认框：%s' % confirm_dialog_text(drv).replace('\n', ' | ')[:200])
    click_confirm(drv, '取消')
    click_radio(drv, 'upload-device-round', 2)
    hub = hub_buttons(drv)
    log('两段快捷操作（设备段加入后 6 件）：%s' % hub)
    assert len(hub) == 6, hub
    click_hub(drv, '从其他轮次复制', 0)
    time.sleep(0.8)
    shot(drv, '03-folder-per-round-tab-light.png')
    click_hub(drv, '从其他轮次复制', 0)  # 关闭 popover
    time.sleep(0.5)

    click_radio(drv, 'upload-dimension-round', 1)
    specific_shown = drv.execute_script(
        "const b = window.__scopeBlock('upload-dimension-round');"
        "return Array.from(b.querySelectorAll('label')).map(l => (l.textContent||'').trim()).filter(Boolean);")
    log('指定轮次 Checkbox 组：%s' % specific_shown)
    shot(drv, '04-folder-specific-light.png')

    set_theme(drv, 'dark')
    open_audio_page(drv)
    open_folder_dialog(drv)
    select_folder(drv, os.path.join(SRC, 's2_all'))
    ensure_generate_case(drv)
    inject_helpers(drv)
    click_radio(drv, 'upload-dimension-round', 2)
    shot(drv, '04b-folder-per-round-dark.png')
    set_theme(drv, 'light')
    log('UI 控件态核对完成')


# ------------------------------------------------------------------ 载荷
def do_uploads(drv, summary, only=None):
    devs = (api_data('/api/v1/playback-devices?page=1&per_page=100')[1] or {}).get('items') or []
    log('播放设备 %d 台：%s' % (len(devs), [d.get('name') for d in devs[:4]]))
    assert len(devs) >= 2, '至少需要 2 台设备才能验逐轮不同设备'

    # ---- s1 上传窗 · 所有轮次（N=1）
    open_audio_page(drv)
    open_upload_dialog(drv)
    select_audio_file(drv, os.path.join(SRC, '%s_a1.wav' % PREFIX))
    ensure_generate_case(drv)
    inject_helpers(drv)
    dim1 = pick_dimension(drv, 0)
    dim_multi = pick_dimension(drv, 0, within_multi=True)
    dev1 = pick_device(drv, 0)
    log('s1 选择：维度=%s 整体维度=%s 设备=%s' % (dim1, dim_multi, dev1))
    shot(drv, '10-s1-upload-all-light.png')
    result = run_upload(drv)
    summary['scenarios'].append({'name': 's1-上传窗-所有轮次', 'merges': result['merges'],
                                 'picked': {'dim': dim1, 'multi': dim_multi, 'device': dev1}})

    if only == ['s1']:
        cases = find_cases(PREFIX)
        summary['readback'] = {c['name']: case_rounds(c['id']) for c in cases}
        log('回读：%s' % json.dumps(summary['readback'], ensure_ascii=False)[:1200])
        evidence_page(drv, summary)
        return

    # ---- s2 文件夹 · 所有轮次（N=3）
    open_audio_page(drv)
    open_folder_dialog(drv)
    select_folder(drv, os.path.join(SRC, 's2_all'))
    ensure_generate_case(drv)
    inject_helpers(drv)
    dim1 = pick_dimension(drv, 0)
    dim_multi = pick_dimension(drv, 0, within_multi=True)
    dev1 = pick_device(drv, 0)
    log('s2 选择：维度=%s 整体维度=%s 设备=%s' % (dim1, dim_multi, dev1))
    shot(drv, '11-s2-folder-all-light.png')
    result = run_upload(drv)
    summary['scenarios'].append({'name': 's2-文件夹-所有轮次', 'merges': result['merges'],
                                 'picked': {'dim': dim1, 'multi': dim_multi, 'device': dev1}})

    # ---- s3 文件夹 · 指定轮次（只勾第 2 轮）
    open_audio_page(drv)
    open_folder_dialog(drv)
    select_folder(drv, os.path.join(SRC, 's3_specific'))
    ensure_generate_case(drv)
    inject_helpers(drv)
    click_radio(drv, 'upload-dimension-round', 1)
    check_specific_round(drv, 'upload-dimension-round', 1)  # 默认勾中第 1 轮 → 取消，只留第 2 轮
    check_specific_round(drv, 'upload-dimension-round', 2)
    click_radio(drv, 'upload-device-round', 1)
    check_specific_round(drv, 'upload-device-round', 1)
    check_specific_round(drv, 'upload-device-round', 2)
    dim1 = pick_dimension(drv, 0)
    dev1 = pick_device(drv, 0)
    log('s3 选择：维度=%s 设备=%s（仅第 2 轮）' % (dim1, dev1))
    shot(drv, '12-s3-folder-specific-light.png')
    result = run_upload(drv)
    summary['scenarios'].append({'name': 's3-文件夹-指定轮次', 'merges': result['merges'],
                                 'picked': {'dim': dim1, 'device': dev1}})

    # ---- s4 文件夹 · 逐轮设置（第1轮设置 → 第2轮复制并换设备 → 第3轮清空）
    open_audio_page(drv)
    open_folder_dialog(drv)
    select_folder(drv, os.path.join(SRC, 's4_per_round'))
    ensure_generate_case(drv)
    inject_helpers(drv)
    click_radio(drv, 'upload-dimension-round', 2)
    click_radio(drv, 'upload-device-round', 2)
    dim1 = pick_dimension(drv, 0)
    dev1 = pick_device(drv, 0)
    click_round_tab(drv, 'upload-dimension-round', 2)
    click_round_tab(drv, 'upload-device-round', 2)
    click_hub(drv, '从其他轮次复制', 0)
    time.sleep(0.8)
    drv.execute_script(
        "const btn = Array.from(document.querySelectorAll('button'))"
        ".filter(b => (b.textContent||'').trim()==='确定');"
        "if (btn.length) btn[btn.length-1].click();")
    time.sleep(0.8)
    dev2 = pick_device(drv, 1)
    click_round_tab(drv, 'upload-dimension-round', 3)
    click_round_tab(drv, 'upload-device-round', 3)
    click_hub(drv, '清空当前轮次', 0)
    log('s4 清空确认框：%s' % confirm_dialog_text(drv).replace('\n', ' | ')[:160])
    click_confirm(drv, '确定清空')
    click_hub(drv, '清空当前轮次', 4)
    click_confirm(drv, '确定清空')
    log('s4 选择：维度=%s 设备1=%s 设备2=%s（第3轮清空）' % (dim1, dev1, dev2))
    shot(drv, '13-s4-folder-per-round-light.png')
    result = run_upload(drv)
    summary['scenarios'].append({'name': 's4-文件夹-逐轮设置', 'merges': result['merges'],
                                 'picked': {'dim': dim1, 'device1': dev1, 'device2': dev2}})

    # ---- 真实回读：本 run 创建的用例 rounds / dimensions（列表有缓存延迟，重试到 4 个为止）
    cases = []
    for _ in range(6):
        time.sleep(3)
        cases = find_cases(PREFIX)
        if len(cases) >= 4:
            break
    readback = {}
    for case in cases:
        readback[case['name']] = case_rounds(case['id'])
    summary['readback'] = readback
    log('回读用例 %d 个：%s' % (len(cases), json.dumps(readback, ensure_ascii=False)[:1200]))
    evidence_page(drv, summary)


if __name__ == '__main__':
    main()
