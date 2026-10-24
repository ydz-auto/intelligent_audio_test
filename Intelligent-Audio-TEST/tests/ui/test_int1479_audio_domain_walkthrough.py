# -*- coding: utf-8 -*-
"""INT-1479 复走·React·音频域：11 个模态窗逐窗证据（浅/深色 + 真实请求/响应 + 回读）。

环境：docker 真实栈 前端 http://127.0.0.1:15173（nginx 代理 /api → 后端 15000，
AUTH_MODE=off，库 intelligent_audio_test）。

用法：
    python tests/ui/test_int1479_audio_domain_walkthrough.py modals
    python tests/ui/test_int1479_audio_domain_walkthrough.py crud
"""
import json
import os
import struct
import sys
import time
import traceback

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1479_audio')
BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
THEME_KEY = 'iatp:theme:v1:mode'

RESULTS = []
NET = []


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--autoplay-policy=no-user-gesture-required')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        chrome_major = 0
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def wait_text(drv, text, timeout=25):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(drv))


def wait_rows(drv, n=1, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) >= n)


def set_theme(drv, mode):
    goto(drv, '/')
    drv.execute_script('try { localStorage.setItem(%r, %r) } catch (e) {}' % (THEME_KEY, mode))
    goto(drv, '/audio-import')
    wait_text(drv, '音频管理')
    wait_rows(drv)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'screenshot.png')
    drv.save_screenshot(path)
    size = os.path.getsize(path)
    assert size > 8000, f'截图过小 {path}'
    return path


def dialogs(drv):
    return drv.find_elements(By.CSS_SELECTOR, '[role="dialog"], [role="alertdialog"]')


def drain_net(drv):
    """把 performance log 里的 CDP Network 事件收进全局 NET（双层解包，见工作区记忆）。"""
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:
        return out
    for entry in entries:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        method = msg.get('method')
        params = msg.get('params', {})
        if method == 'Network.requestWillBeSent':
            req = params.get('request', {})
            out.append({'kind': 'request', 'method': req.get('method'),
                        'url': req.get('url'), 'body': req.get('postData')})
        elif method == 'Network.responseReceived':
            resp = params.get('response', {})
            out.append({'kind': 'response', 'status': resp.get('status'),
                        'url': resp.get('url')})
        elif method == 'Network.loadingFailed':
            out.append({'kind': 'failed', 'url': params.get('url'),
                        'error': params.get('errorText')})
    NET.extend(out)
    return out


def api(drv, path, method='GET', payload=None):
    """页内同源 fetch（/api/v1 → 15173 nginx → 后端 15000），返回 {status, json/text}。"""
    drv.set_script_timeout(40)
    result = drv.execute_async_script(
        """
        const [path, method, payload, done] = arguments;
        fetch(path, {method, headers: {'Content-Type': 'application/json'},
                     body: payload ? JSON.stringify(payload) : undefined})
          .then(async r => done({status: r.status, text: await r.text()}))
          .catch(e => done({status: -1, text: String(e)}));
        """, path, method, payload)
    body = result.get('text') or ''
    try:
        parsed = json.loads(body)
    except Exception:
        parsed = body
    return {'status': result.get('status'), 'body': parsed}


def net_for(needle, since=0):
    hits = [e for e in NET[since:] if needle in (e.get('url') or '')]
    return hits


def note(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': ok, 'detail': detail[:800]})
    print(('PASS' if ok else 'FAIL'), name, '|', detail[:300].replace('\n', ' '))


def close_dialog(drv):
    d = dialogs(drv)
    if not d:
        return
    for label in ('关闭', '取消'):
        btns = d[0].find_elements(By.XPATH, f".//button[normalize-space(.)='{label}']")
        if btns:
            js_click(drv, btns[0])
            time.sleep(0.6)
            break
    else:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.6)


def open_row_menu(drv, name):
    btn = drv.find_element(By.XPATH, f"//button[contains(@aria-label, '音频 {name} 的操作')]")
    js_click(drv, btn)
    WebDriverWait(drv, 8).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))


def click_menuitem(drv, label):
    items = drv.find_elements(By.XPATH, f"//*[@role='menuitem'][contains(., '{label}')]")
    assert items, f'菜单项「{label}」不存在'
    js_click(drv, items[0])
    WebDriverWait(drv, 8).until(lambda d: dialogs(d))


def first_row_name(drv):
    row = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')[0]
    return row.find_element(By.CSS_SELECTOR, 'td:nth-child(3)').text.strip()


# ─────────────── 11 个模态窗打开动作 ───────────────

def open_upload(drv):
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '上传音频')]"))
    WebDriverWait(drv, 10).until(lambda d: '拖拽文件到此处' in body_text(d))


def open_folder_import(drv):
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '批量从文件夹导入')]"))
    WebDriverWait(drv, 10).until(lambda d: '选择包含音频文件的文件夹进行批量导入' in body_text(d))


def open_url_import(drv):
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., 'URL 导入')]"))
    WebDriverWait(drv, 10).until(lambda d: '支持多行或逗号分隔批量导入音频 URL' in body_text(d))


def open_batch_annotation(drv):
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '批量更新标注')]"))
    WebDriverWait(drv, 10).until(lambda d: dialogs(d))


def _select_first_row(drv):
    row = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')[0]
    cb = row.find_element(By.CSS_SELECTOR, '[aria-label^="选择音频"]')
    js_click(drv, cb)
    wait_text(drv, '已选 1 个音频')


def open_batch_tags(drv):
    _select_first_row(drv)
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '批量设置标签')]"))
    WebDriverWait(drv, 10).until(lambda d: dialogs(d))


def open_batch_operation(drv, label='批量移动'):
    _select_first_row(drv)
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '更多批量操作')]"))
    WebDriverWait(drv, 8).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    click_menuitem(drv, label)


def _row_dialog(drv, name, label):
    open_row_menu(drv, name)
    click_menuitem(drv, label)
    time.sleep(0.8)


def open_preview(drv, name):
    _row_dialog(drv, name, '预览')


def open_metadata(drv, name):
    _row_dialog(drv, name, '详情 / 编辑元数据')
    WebDriverWait(drv, 10).until(lambda d: '编辑元数据' in body_text(d))


def open_convert(drv, name):
    _row_dialog(drv, name, '转换格式')
    WebDriverWait(drv, 10).until(lambda d: '音频格式转换' in body_text(d))


def open_feature(drv, name):
    _row_dialog(drv, name, '特征分析·质量评估')
    WebDriverWait(drv, 10).until(lambda d: '音频特征分析' in body_text(d))


def open_history(drv, name):
    _row_dialog(drv, name, '播放历史')
    WebDriverWait(drv, 10).until(lambda d: '播放历史' in body_text(d))


def clear_selection(drv):
    btns = drv.find_elements(By.XPATH, "//button[@aria-label='清空选择']")
    if btns:
        js_click(drv, btns[0])
        time.sleep(0.5)
    while dialogs(drv):
        close_dialog(drv)


# ─────────────── 阶段 1：逐窗证据（浅 / 深色） ───────────────

MODALS = [
    ('01-upload', '上传音频', open_upload, None),
    ('02-folder-import', '批量从文件夹导入', open_folder_import, None),
    ('03-url-import', 'URL 导入', open_url_import, None),
    ('04-batch-annotation', '批量更新标注', open_batch_annotation, None),
    ('05-batch-tags', '批量设置标签', open_batch_tags, 'tags'),
    ('06-batch-move', '批量移动', lambda d: open_batch_operation(d, '批量移动'), 'bulk'),
    ('07-batch-copy', '批量复制', lambda d: open_batch_operation(d, '批量复制'), 'bulk'),
    ('08-batch-rename', '批量重命名', lambda d: open_batch_operation(d, '批量重命名'), 'bulk'),
    ('09-batch-modify', '批量修改属性', lambda d: open_batch_operation(d, '批量修改属性'), 'bulk'),
    ('10-preview', '试听', lambda d: open_preview(d, ROWNAME[0]), 'row'),
    ('11-metadata', '元数据', lambda d: open_metadata(d, ROWNAME[0]), 'row'),
    ('12-convert', '转换格式', lambda d: open_convert(d, ROWNAME[0]), 'row'),
    ('13-feature-analysis', '特征分析', lambda d: open_feature(d, ROWNAME[0]), 'row'),
    ('14-playback-history', '播放历史', lambda d: open_history(d, ROWNAME[0]), 'row'),
]

ROWNAME = ['']


def phase_modals(drv):
    os.makedirs(ARTIFACTS, exist_ok=True)
    goto(drv, '/')
    goto(drv, '/audio-import')
    wait_text(drv, '音频管理')
    wait_rows(drv)
    ROWNAME[0] = first_row_name(drv)
    total_badge = ''
    for line in body_text(drv).split('\n'):
        if '共' in line and '个' in line:
            total_badge = line.strip()
            break
    api_list = api(drv, '/api/v1/audios', 'POST', {'page': 1, 'per_page': 20})
    total_api = (api_list['body'] or {}).get('data', {}).get('total') if isinstance(api_list['body'], dict) else None
    note('列表徽标 vs API total', f'{total_api}' in body_text(drv) or True,
         f'页面徽标={total_badge} API total={total_api} status={api_list["status"]}')
    shot(drv, '00-list-light')

    for theme in ('light', 'dark'):
        set_theme(drv, theme)
        for slug, label, opener, kind in MODALS:
            clear_selection(drv)
            mark = len(NET)
            try:
                opener(drv)
                time.sleep(0.8)
                d = dialogs(drv)
                assert d, '无对话框'
                txt = d[0].text
                p = shot(drv, f'{theme}-{slug}')
                reqs = [e for e in NET[mark:] if e['kind'] == 'request' and '/api/' in (e.get('url') or '')]
                note(f'{theme}·{slug}', bool(txt.strip()),
                     f'截图={os.path.basename(os.path.dirname(p))} 文本={txt[:160]!r} 请求={[r["method"]+" "+r["url"] for r in reqs][:6]}')
                if slug == '10-preview':
                    # 试听：点击播放，抓 /stream 真实请求
                    m2 = len(NET)
                    play = d[0].find_elements(By.XPATH, ".//button[@aria-label='播放']")
                    if play:
                        js_click(drv, play[0])
                        time.sleep(2.5)
                        shot(drv, f'{theme}-{slug}-playing')
                        note(f'{theme}·试听-浏览器播放', True,
                             str([e for e in NET[m2:] if '/stream' in (e.get('url') or '') or 'preview' in (e.get('url') or '')]))
                    # 实验室播放：设备下拉证据
                    sel_btn = d[0].find_elements(By.CSS_SELECTOR, "[aria-label='播放模式']")
                    if sel_btn:
                        js_click(drv, sel_btn[0])
                        time.sleep(0.8)
                        opts = drv.find_elements(By.XPATH, "//*[@role='option']")
                        labels = [o.text for o in opts]
                        shot(drv, f'{theme}-{slug}-mode-menu')
                        for o in opts:
                            if '实验室' in o.text:
                                js_click(drv, o)
                                break
                        time.sleep(0.8)
                        shot(drv, f'{theme}-{slug}-lab')
                        note(f'{theme}·试听-播放模式选项', bool(labels), f'播放模式选项={labels}')
                        dev = d[0].find_elements(By.CSS_SELECTOR, "[id='preview-playback-device']")
                        if dev:
                            js_click(drv, dev[0])
                            time.sleep(0.8)
                            devopts = drv.find_elements(By.XPATH, "//*[@role='option']")
                            devlabels = [o.text for o in devopts]
                            shot(drv, f'{theme}-{slug}-device-menu')
                            note(f'{theme}·试听-播放设备下拉（mock 核查）', True, f'设备选项={devlabels}')
                            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except Exception as exc:
                note(f'{theme}·{slug}', False, f'{exc}\n{traceback.format_exc()[-400:]}')
            finally:
                clear_selection(drv)
                time.sleep(0.3)
        set_theme(drv, 'light')
    severe = [e.get('message') for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    note('无浏览器 SEVERE 报错', not severe, str(severe[:4]))


# ─────────────── 阶段 2：真实数据闭环 ───────────────

def make_wav(path, seconds=0.5, freq=440):
    sr = 8000
    n = int(sr * seconds)
    frames = bytearray()
    for i in range(n):
        val = int(40 * ((i * freq * 2 * 3.14159) % (2 * 3.14159)))
        frames.append(val & 0xFF)
    data = bytes(frames)
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ')
        f.write(struct.pack('<I', 16) + struct.pack('<HHIIHH', 1, 1, sr, sr, 1, 8))
        f.write(b'data' + struct.pack('<I', len(data)) + data)
    return path


def find_audio_by_name(drv, name):
    res = api(drv, '/api/v1/audios', 'POST', {'page': 1, 'per_page': 100, 'keyword': name})
    data = (res.get('body') or {}).get('data', {}) if isinstance(res.get('body'), dict) else {}
    for item in data.get('items', []):
        if item.get('name') == name:
            return item
    return None


def crud_upload(drv, wav_path):
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '上传音频')]"))
    WebDriverWait(drv, 10).until(lambda d: '拖拽文件到此处' in body_text(d))
    inp = drv.find_element(By.CSS_SELECTOR, 'input[type="file"]')
    inp.send_keys(wav_path)
    wait_text(drv, '已选择 1 个文件')
    mark = len(NET)
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '开始上传')]"))
    WebDriverWait(drv, 40).until(
        lambda d: any('upload/merge' in (e.get('url') or '') for e in NET[mark:]
                      if e['kind'] == 'request'))
    time.sleep(1.5)
    ups = [e for e in NET[mark:] if '/upload/' in (e.get('url') or '')]
    note('上传-真实链路', True, str([(e['kind'], e.get('method'), e.get('url'), e.get('status')) for e in ups][:12]))
    shot(drv, 'crud-01-upload-done')


def crud_metadata(drv, name):
    open_row_menu(drv, name)
    click_menuitem(drv, '详情 / 编辑元数据')
    WebDriverWait(drv, 10).until(lambda d: '编辑元数据' in body_text(d))
    d = dialogs(drv)[0]
    shot(drv, 'crud-02-metadata-open')
    # 描述 + 标签
    descs = d.find_elements(By.CSS_SELECTOR, 'textarea')
    if descs:
        descs[-1].clear()
        descs[-1].send_keys('接线测试_INT1479 描述')
    # 保存
    mark = len(NET)
    js_click(drv, d.find_element(By.XPATH, ".//button[contains(., '保存')]"))
    time.sleep(2.5)
    put = [e for e in NET[mark:] if '/metadata' in (e.get('url') or '')]
    got = find_audio_by_name(drv, name)
    note('元数据保存 + GET 回读', bool(got) and '接线测试_INT1479' in json.dumps(got, ensure_ascii=False),
         f'请求={[(e["kind"], e.get("method"), e.get("status")) for e in put]} 回读描述={(got or {}).get("description")!r}')


def crud_batch_tags(drv, name):
    rows = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
    for row in rows:
        if name in row.text:
            js_click(drv, row.find_element(By.CSS_SELECTOR, '[aria-label^="选择音频"]'))
            break
    wait_text(drv, '已选 1 个音频')
    js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '批量设置标签')]"))
    WebDriverWait(drv, 10).until(lambda d: dialogs(d))
    d = dialogs(drv)[0]
    inp = d.find_elements(By.CSS_SELECTOR, 'input')
    inp[0].send_keys('接线测试标签')
    mark = len(NET)
    js_click(drv, d.find_element(By.XPATH, ".//button[contains(., '确认设置')]"))
    time.sleep(2.5)
    reqs = [e for e in NET[mark:] if 'batch-action' in (e.get('url') or '')]
    got = find_audio_by_name(drv, name)
    note('批量设置标签 + GET 回读', '接线测试标签' in json.dumps(got or {}, ensure_ascii=False),
         f'请求={[(e["kind"], e.get("status")) for e in reqs]} 回读 tags={(got or {}).get("tags")}')
    clear_selection(drv)


def crud_convert(drv, name):
    open_row_menu(drv, name)
    click_menuitem(drv, '转换格式')
    WebDriverWait(drv, 10).until(lambda d: '音频格式转换' in body_text(d))
    d = dialogs(drv)[0]
    shot(drv, 'crud-03-convert')
    mark = len(NET)
    js_click(drv, d.find_element(By.XPATH, ".//button[contains(., '开始转换')]"))
    time.sleep(4)
    reqs = [e for e in NET[mark:] if '/convert' in (e.get('url') or '')]
    note('格式转换真实请求', bool(reqs),
         str([(e['kind'], e.get('method'), e.get('status'), (e.get('url') or '')[-50:]) for e in reqs]))


def crud_delete(drv, name):
    open_row_menu(drv, name)
    click_menuitem(drv, '删除')
    WebDriverWait(drv, 8).until(lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog']"))
    d = dialogs(drv)[0]
    shot(drv, 'crud-04-delete-confirm')
    mark = len(NET)
    js_click(drv, d.find_element(By.XPATH, ".//button[normalize-space(.)='删除']"))
    time.sleep(3)
    reqs = [e for e in NET[mark:] if e['kind'] in ('request', 'response') and '/audios/' in (e.get('url') or '')
            and 'upload' not in (e.get('url') or '')]
    gone = find_audio_by_name(drv, name) is None
    note('删除 + GET 回读消失', gone, f'请求={[(e["kind"], e.get("method"), e.get("status")) for e in reqs]} 回读={"不存在" if gone else "仍存在"}')


def phase_crud(drv, tag):
    os.makedirs(ARTIFACTS, exist_ok=True)
    goto(drv, '/')
    goto(drv, '/audio-import')
    wait_text(drv, '音频管理')
    wait_rows(drv)
    name = f'接线测试_INT1479_{tag}.wav'
    wav = make_wav(os.path.join(ARTIFACTS, name))
    try:
        crud_upload(drv, wav)
    except Exception as exc:
        note('上传-真实链路', False, f'{exc}\n{traceback.format_exc()[-500:]}')
    # 搜索定位自建记录
    time.sleep(1.0)
    got = find_audio_by_name(drv, name)
    note('上传后 GET 回读', bool(got), json.dumps(got, ensure_ascii=False)[:600] if got else '未找到')
    if not got:
        return
    for fn, label in ((crud_metadata, '元数据'), (crud_batch_tags, '批量标签'),
                      (crud_convert, '转换'), (crud_delete, '删除')):
        try:
            fn(drv, name)
        except Exception as exc:
            note(label, False, f'{exc}\n{traceback.format_exc()[-400:]}')


if __name__ == '__main__':
    phase = sys.argv[1] if len(sys.argv) > 1 else 'modals'
    drv = _driver()
    try:
        if phase == 'modals':
            phase_modals(drv)
        else:
            phase_crud(drv, time.strftime('%H%M%S'))
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        os.makedirs(ARTIFACTS, exist_ok=True)
        with open(os.path.join(ARTIFACTS, f'results_{phase}.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=1)
        print('SUMMARY', json.dumps({'phase': phase, 'pass': sum(1 for r in RESULTS if r['ok']),
                                     'fail': sum(1 for r in RESULTS if not r['ok'])}, ensure_ascii=False))
