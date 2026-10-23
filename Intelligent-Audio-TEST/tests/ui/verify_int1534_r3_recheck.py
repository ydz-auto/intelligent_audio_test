# -*- coding: utf-8 -*-
"""INT-1534 三轮复测（测试工程师）：只复测上轮打回的 P2 与 P3-1 及其相关部分。

被测物：交付分支 `agent/react-c/int-1534` @ 6cbf1b6d1（修复提交 2ebafd45）构建产物，
临时 nginx 容器 :15341（--network intelligent-audio-test_default，/api → api_gateway:5000），
库 intelligent_audio_test（/health 校验）。用例夹具由 tests/ui/int1534_recheck_api.py 建。

A 段（P2）：用例抽屉 → 音频列表 → 音频卡「试听」→ 实验室播放 + 偏移 2 → 开始试听 → 播放
   断言：POST /api/v1/audios/{id}/preview 请求体含 "offset":2；播放器起点 00:02。
B 段（P3-1）：用例行「预览音频」→ 实验室播放 → 开始试听 → 播放器挂载后 stop 计数（期望 0）
   →「返回试听配置」→ stop 计数（期望 1）；用例源 preview 请求 200（回归护栏）。

分阶段单独起浏览器会话（后端用例列表单请求 45s 且偶发失败，长会话易被拖死）：
  python verify_int1534_r3_recheck.py --phase audiolib --theme light
  python verify_int1534_r3_recheck.py --phase audiolib --theme dark
  python verify_int1534_r3_recheck.py --phase case
"""
import argparse
import html
import json
import os
import sys
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15341')
CASE_NAME = os.environ.get('CASE_NAME', '接线测试_INT1534_R3_复测')
CASE_ID = os.environ.get('CASE_ID', '3b014671-38b5-4643-bef7-176ccfbddbe1')
AUDIO_ID = os.environ.get('AUDIO_ID', '2506')
GROUP_NAME = os.environ.get('GROUP_NAME', '音频上传生成')
OFFSET = os.environ.get('OFFSET', '2')
ART = os.environ.get('ART_DIR', os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1534-r3'))
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const body = (init && init.body) || null;
  const entry = {url: url, method: method, body: typeof body === 'string' ? body : null,
                 t: Date.now(), status: 0};
  window.__net.push(entry);
  try { const res = await __origFetch.apply(this, arguments); entry.status = res.status; return res; }
  catch (e) { entry.status = -1; throw e; }
};
"""

DLG = "//div[@role='dialog'][.//button[normalize-space(.)='开始试听']]"
PLAYER = "//div[@role='dialog'][contains(., '测试用例预览')]"


def log(m):
    print(m, flush=True)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def _driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--autoplay-policy=no-user-gesture-required')
    o.add_argument('--disable-dev-shm-usage')
    # 预签名 URL 主机是容器网络名 rustfs（宿主 9000 已映射）
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
    d.set_page_load_timeout(150)
    d.set_script_timeout(180)
    return d


def net(drv, needle):
    return [e for e in drv.execute_script('return window.__net || []')
            if needle in (e.get('url') or '')]


def clear_net(drv):
    drv.execute_script('window.__net = []')


def _group_visible(drv):
    return drv.find_elements(By.XPATH, "//span[normalize-space(.)='%s']" % GROUP_NAME)


def _retry_btn(drv):
    """用例列表错误态的「重试」按钮（后端单请求 45s 偶发超时）。"""
    for el in drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']"):
        if el.is_displayed():
            return el
    return None


def goto_case_page(drv, budget=300):
    """用例页 → 展开目标分组。遇列表错误态自动点「重试」，直到成功或超预算。"""
    url = BASE + '/testcases/by-group?search=' + urllib.parse.quote(CASE_NAME)
    end = time.time() + budget
    attempt = 0
    while time.time() < end:
        attempt += 1
        try:
            drv.get(url)
        except Exception as err:  # noqa: BLE001
            log('[goto] 第 %d 次导航异常: %s' % (attempt, err))
        inner = time.time() + 120
        while time.time() < inner:
            try:
                spans = _group_visible(drv)
                if spans:
                    js_click(drv, spans[0])
                    WebDriverWait(drv, 90).until(lambda x: x.find_elements(
                        By.XPATH, "//span[normalize-space(.)='%s']" % CASE_NAME))
                    return
                btn = _retry_btn(drv)
                if btn:
                    log('[goto] 列表错误态，点「重试」')
                    js_click(drv, btn)
                    inner = time.time() + 120
            except Exception as err:  # noqa: BLE001
                log('[goto] 轮询异常: %s' % err)
            time.sleep(1.5)
        log('[goto] 第 %d 次未渲染分组，重新导航' % attempt)
        try:
            drv.save_screenshot(os.path.join(ART, 'goto-fail-%d.png' % attempt))
        except Exception:
            pass
    raise RuntimeError('用例页 %ds 内未渲染分组' % budget)


def open_audiolib_dialog(drv):
    """抽屉「音频列表」→ 音频卡「试听」→ 试听配置弹窗。"""
    goto_case_page(drv)
    edit = WebDriverWait(drv, 120).until(EC.presence_of_element_located((
        By.XPATH,
        "//div[contains(., '%s')][.//button[@aria-label='编辑用例']]//button[@aria-label='编辑用例']"
        % CASE_NAME)))
    time.sleep(0.5)
    js_click(drv, edit)
    tab = WebDriverWait(drv, 60).until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space(.)='音频列表']")))
    time.sleep(0.8)
    js_click(drv, tab)
    listen = WebDriverWait(drv, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//button[@aria-label='试听']")))
    time.sleep(0.5)
    js_click(drv, listen)
    WebDriverWait(drv, 30).until(EC.visibility_of_element_located((By.XPATH, DLG)))
    time.sleep(0.8)


def open_case_row_dialog(drv):
    """用例行「预览音频」→ 试听配置弹窗。"""
    goto_case_page(drv)
    btn = WebDriverWait(drv, 120).until(EC.presence_of_element_located((
        By.XPATH,
        "//div[contains(., '%s')][.//button[@aria-label='预览音频']]//button[@aria-label='预览音频']"
        % CASE_NAME)))
    time.sleep(0.4)
    js_click(drv, btn)
    WebDriverWait(drv, 30).until(EC.visibility_of_element_located((By.XPATH, DLG)))
    time.sleep(0.6)


def fill_offset(drv, value):
    box = drv.find_element(By.XPATH, DLG + "//input[@aria-label='偏移量秒数']")
    box.click()
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys(str(value))
    time.sleep(0.3)
    return drv.execute_script('return arguments[0].value', box)


def pick_lab(drv):
    js_click(drv, drv.find_element(
        By.XPATH, DLG + "//label[contains(normalize-space(.), '实验室播放')]"))
    time.sleep(0.4)


def player_time(drv):
    return drv.execute_script(
        "const p=document.querySelector('[data-testid=player-time]'); return p?p.textContent:null")


def network_evidence(drv, entries, name):
    rows = ''.join(
        "<tr><td>%s</td><td class='u'>%s</td><td>%s</td><td>%s</td></tr>"
        % (html.escape(e['method']), html.escape(e['url']),
           e['status'], html.escape(e['body'] or '—'))
        for e in entries
    )
    doc = """<html><head><meta charset='utf-8'><style>
    body{font-family:Consolas,monospace;background:#fff;color:#111;padding:18px}
    h3{font-family:sans-serif;margin:0 0 12px}
    table{border-collapse:collapse;font-size:12px;width:100%%}
    th,td{border:1px solid #bbb;padding:6px 8px;text-align:left;vertical-align:top}
    th{background:#eef} .u{word-break:break-all;max-width:520px}
    </style></head><body><h3>%s</h3><table>
    <tr><th>Method</th><th>URL</th><th>Status</th><th>Request body</th></tr>%s</table></body></html>""" % (
        html.escape(name), rows)
    path = os.path.join(ART, name + '.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc)
    drv.get('file:///' + path.replace('\\', '/'))
    time.sleep(0.6)
    shot = os.path.join(ART, name + '.png')
    drv.save_screenshot(shot)
    return shot


def body_offset(entry):
    try:
        payload = json.loads(entry.get('body') or '{}')
    except ValueError:
        return None
    return payload.get('offset')


def dump(part, data):
    path = os.path.join(ART, 'result-%s.json' % part)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log('RESULT %s -> %s' % (part, json.dumps(data.get('verdict', {}), ensure_ascii=False)))


def phase_audiolib(drv, theme):
    suffix = theme
    out = {'theme': theme}
    if theme == 'dark':
        drv.get(BASE + '/dashboard')
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    else:
        drv.get(BASE + '/dashboard')
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    open_audiolib_dialog(drv)
    out['is_dark'] = drv.execute_script(
        "return document.documentElement.classList.contains('dark')")
    out['config_text'] = drv.find_element(By.XPATH, DLG).text
    drv.save_screenshot(os.path.join(ART, '01-config-%s.png' % suffix))
    pick_lab(drv)
    out['offset_typed'] = fill_offset(drv, OFFSET)
    clear_net(drv)
    js_click(drv, drv.find_element(By.XPATH, DLG + "//button[normalize-space(.)='开始试听']"))
    WebDriverWait(drv, 60).until(EC.visibility_of_element_located((By.XPATH, PLAYER)))
    time.sleep(1.0)
    out['player_time_at_entry'] = player_time(drv)
    play = drv.find_elements(By.XPATH, PLAYER + "//button[@aria-label='播放']")
    if play:
        js_click(drv, play[0])
    time.sleep(4.0)
    reqs = net(drv, '/audios/%s/preview' % AUDIO_ID)
    out['preview_reqs'] = reqs
    out['preview_offsets'] = [body_offset(e) for e in reqs]
    out['player_time_after_play'] = player_time(drv)
    out['player_text'] = drv.find_element(By.XPATH, PLAYER).text
    drv.save_screenshot(os.path.join(ART, '02-player-%s.png' % suffix))
    out['verdict'] = {
        'offset_in_request': bool(out['preview_offsets'])
        and all(v == int(OFFSET) for v in out['preview_offsets']),
        'request_status_ok': all((e.get('status') or 0) < 500 for e in reqs),
        'player_start_at_offset': (out['player_time_at_entry'] or '').startswith('00:0%d' % int(OFFSET)),
        'theme_ok': bool(out['is_dark']) == (theme == 'dark'),
    }
    log('[A %s] offset_typed=%s preview_offsets=%s start=%s status=%s'
        % (suffix, out['offset_typed'], out['preview_offsets'],
           out['player_time_at_entry'], [e.get('status') for e in reqs]))
    # 关闭弹窗
    try:
        back = drv.find_elements(By.XPATH, PLAYER + "//button[normalize-space(.)='返回试听配置']")
        if back:
            js_click(drv, back[0])
            WebDriverWait(drv, 30).until(EC.visibility_of_element_located((By.XPATH, DLG)))
        js_click(drv, drv.find_element(By.XPATH, DLG + "//button[normalize-space(.)='取消']"))
    except Exception as err:  # noqa: BLE001
        log('[A %s] 关闭弹窗异常: %s' % (suffix, err))
    dump('audiolib-%s' % suffix, out)
    return out


def phase_case(drv):
    out = {}
    drv.get(BASE + '/dashboard')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    open_case_row_dialog(drv)
    # 路由切换动画/合成未落定会让截图整体发灰，截图前强制重排并多等一拍
    time.sleep(1.5)
    drv.execute_script('void document.body.offsetHeight')
    time.sleep(0.8)
    drv.save_screenshot(os.path.join(ART, '03-case-config-light.png'))
    pick_lab(drv)
    clear_net(drv)
    js_click(drv, drv.find_element(By.XPATH, DLG + "//button[normalize-space(.)='开始试听']"))
    WebDriverWait(drv, 90).until(
        lambda x: '播放设备（实验室播放）' in x.find_element(By.XPATH, PLAYER).text)
    time.sleep(2.5)
    out['preview_reqs'] = net(drv, '/testcases/%s/preview' % CASE_ID)
    out['stop_at_mount'] = net(drv, '/testcases/%s/stop_preview' % CASE_ID)
    out['player_text'] = drv.find_element(By.XPATH, PLAYER).text
    out['player_time_at_mount'] = player_time(drv)
    drv.execute_script('void document.body.offsetHeight')
    time.sleep(0.8)
    drv.save_screenshot(os.path.join(ART, '04-case-player-light.png'))
    js_click(drv, drv.find_element(By.XPATH, PLAYER + "//button[normalize-space(.)='返回试听配置']"))
    WebDriverWait(drv, 30).until(EC.visibility_of_element_located((By.XPATH, DLG)))
    time.sleep(2.5)
    out['stop_after_back'] = net(drv, '/testcases/%s/stop_preview' % CASE_ID)
    out['back_config_text'] = drv.find_element(By.XPATH, DLG).text
    drv.save_screenshot(os.path.join(ART, '05-case-back-config-light.png'))
    out['verdict'] = {
        'stop_at_mount_zero': len(out['stop_at_mount']) == 0,
        'stop_after_back_one': len(out['stop_after_back']) == 1,
        'case_preview_200': bool(out['preview_reqs'])
        and out['preview_reqs'][0].get('status') == 200,
    }
    log('[B] stop_at_mount=%d stop_after_back=%d preview=%d body=%s'
        % (len(out['stop_at_mount']), len(out['stop_after_back']),
           len(out['preview_reqs']),
           (out['preview_reqs'][0]['body'] if out['preview_reqs'] else None)))
    js_click(drv, drv.find_element(By.XPATH, DLG + "//button[normalize-space(.)='取消']"))
    time.sleep(0.6)
    dump('case', out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', default='audiolib', choices=['audiolib', 'case', 'evidence'])
    ap.add_argument('--theme', default='light', choices=['light', 'dark'])
    args = ap.parse_args()

    if args.phase == 'evidence':
        entries = []
        for part in ('audiolib-light', 'audiolib-dark', 'case'):
            path = os.path.join(ART, 'result-%s.json' % part)
            if not os.path.exists(path):
                continue
            data = json.load(open(path, encoding='utf-8'))
            entries += data.get('preview_reqs') or []
            entries += data.get('stop_after_back') or []
        d = _driver()
        try:
            shot = network_evidence(d, entries, 'network-evidence')
            log('evidence -> %s (%d rows)' % (shot, len(entries)))
        finally:
            d.quit()
        return 0

    d = _driver()
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    try:
        out = phase_audiolib(d, args.theme) if args.phase == 'audiolib' else phase_case(d)
        ok = all(out['verdict'].values())
        log('PHASE_%s_%s: %s' % (args.phase, args.theme if args.phase == 'audiolib' else '', ok))
        return 0 if ok else 2
    finally:
        d.quit()


if __name__ == '__main__':
    sys.exit(main())
