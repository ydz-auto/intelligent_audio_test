# -*- coding: utf-8 -*-
"""INT-927 音频库批量操作四分支（move/copy/rename/modify-properties）接线验收。

针对 frontend-react 接线版（连常驻 5000 后端，dev server 5337，AUTH_MODE=off）：
① 四分支弹窗标题正确、无「后端待支持」Alert；
② 主钮「确认执行」可用性（缺字段 / SPL 分支按后端契约禁用）；
③ 请求体透传 snake_case 扩展字段（target_folder / rename_rule / property / property_value）；
④ 执行结果按 success_count/failed_count 实计 toast（非「不支持的操作」）；
⑤ 浅/深色截图 + Network 证据。
测试目标音频：id 56（INT-818 接线测试源，常驻 5000 栈）；run 结束前恢复原状。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5337')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, 'artifacts', 'int927_batch_ops')

AUDIO_ID = 56
BASE_NAME = '兼容测试_01.wav'
RENAMED = 'INT927_01.wav'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
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
    drv.set_page_load_timeout(45)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _shot(drv, name, sub):
    d = os.path.join(ARTIFACTS, sub)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, f'{name}.png'))


def _set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);", mode)
    time.sleep(0.5)


def _enter_workbench(drv):
    _goto(drv, '/login')
    WebDriverWait(drv, 15).until(lambda d: '进入工作台' in _body_text(d))
    drv.find_element(By.XPATH, "//button[contains(., '进入工作台')]").click()
    WebDriverWait(drv, 20).until(lambda d: 'dashboard' in d.current_url)
    time.sleep(1.0)


def _goto_audio_and_select(drv, row_label):
    _goto(drv, '/audio-import')
    WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'tbody tr'))
    time.sleep(1.0)
    drv.find_element(
        By.XPATH, f"//*[@role='checkbox'][@aria-label='选择音频 {row_label}']").click()
    WebDriverWait(drv, 6).until(lambda d: '已选 1 个音频' in _body_text(d))


def _open_bulk_menu(drv, menu_label):
    drv.find_element(By.XPATH, "//button[contains(., '更多批量操作')]").click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    drv.find_element(By.XPATH, f"//*[@role='menuitem'][contains(., '{menu_label}')]").click()


def _select_option(drv, trigger_id, option_text):
    """点开 trigger，点最后一个匹配文本的 option（最新弹层在后）。"""
    drv.find_element(By.ID, trigger_id).click()
    WebDriverWait(drv, 5).until(lambda d: d.find_elements(By.XPATH, "//*[@role='option']"))
    time.sleep(0.3)
    matches = [o for o in drv.find_elements(By.XPATH, "//*[@role='option']")
               if option_text in o.text]
    if matches:
        matches[-1].click()
        return True
    return False


def _btn_confirm(drv):
    return drv.find_element(By.XPATH, "//button[contains(., '确认执行')]")


def _btn_enabled(drv):
    return _btn_confirm(drv).is_enabled()


def _drain_batch_bodies(drv):
    """从 performance 日志提取 POST /audios/batch-action 请求体（本轮起）。"""
    bodies = []
    for e in drv.get_log('performance'):
        msg = e.get('message')
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except Exception:
                continue
        if not isinstance(msg, dict):
            continue
        evt = msg if msg.get('method') else (msg.get('message') if isinstance(msg.get('message'), dict) else None)
        if not evt or not isinstance(evt, dict):
            evt = msg.get('message')
            if isinstance(evt, str):
                try:
                    evt = json.loads(evt)
                except Exception:
                    continue
        if not evt or not isinstance(evt, dict) or evt.get('method') != 'Network.requestWillBeSent':
            continue
        req = evt.get('params', {}).get('request', {})
        if 'batch-action' not in req.get('url', ''):
            continue
        post = req.get('postData')
        if post:
            try:
                bodies.append(json.loads(post))
            except Exception:
                bodies.append({'raw': post})
    return bodies


def restore_audio():
    body = json.dumps({
        'action': 'modify-properties',
        'audio_ids': [AUDIO_ID],
        'property': 'metadata',
        'property_value': {
            'name': BASE_NAME,
            'description': 'INT-818 接线测试源',
            'source_language': 'zh',
            'audio_type': 'dry',
        },
    }).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/api/v1/audios/batch-action',
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}: {e.read().decode()[:200]}'


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    results = {}
    # 0. 恢复基线（上一轮异常可能留残留）
    print('RESTORE pre:', restore_audio(), flush=True)
    drv = _driver()
    try:
        _enter_workbench(drv)

        # ── 1. move ──
        _goto_audio_and_select(drv, BASE_NAME)
        _open_bulk_menu(drv, '批量移动')
        WebDriverWait(drv, 6).until(lambda d: '批量移动音频' in _body_text(d))
        txt = _body_text(drv)
        results['move'] = {
            'title_ok': '批量移动音频' in txt,
            'no_unsafe_alert': '后端待支持' not in txt,
            'button_enabled': _btn_enabled(drv),
        }
        _shot(drv, '01-move-dialog-light', 'move')
        _btn_confirm(drv).click()
        WebDriverWait(drv, 8).until(lambda d: '批量操作完成' in _body_text(d))
        time.sleep(0.5)
        results['move']['request_bodies'] = _drain_batch_bodies(drv)
        results['move']['toast_ok'] = '批量操作完成' in _body_text(drv)
        results['move']['toast_text'] = _body_text(drv).split('批量操作完成')[-1][:40]
        _shot(drv, '02-move-toast', 'move')

        # ── 2. copy ──
        _goto_audio_and_select(drv, BASE_NAME)
        _open_bulk_menu(drv, '批量复制')
        WebDriverWait(drv, 6).until(lambda d: '批量复制音频' in _body_text(d))
        txt = _body_text(drv)
        results['copy'] = {
            'title_ok': '批量复制音频' in txt,
            'no_unsafe_alert': '后端待支持' not in txt,
            'button_enabled': _btn_enabled(drv),
        }
        _shot(drv, '01-copy-dialog-light', 'copy')
        _btn_confirm(drv).click()
        WebDriverWait(drv, 8).until(lambda d: '批量操作完成' in _body_text(d))
        time.sleep(0.5)
        results['copy']['request_bodies'] = _drain_batch_bodies(drv)
        results['copy']['toast_ok'] = '批量操作完成' in _body_text(drv)
        results['copy']['toast_text'] = _body_text(drv).split('批量操作完成')[-1][:40]
        _shot(drv, '02-copy-toast', 'copy')

        # ── 3. rename ──
        _goto_audio_and_select(drv, BASE_NAME)
        _open_bulk_menu(drv, '批量重命名')
        WebDriverWait(drv, 6).until(lambda d: '批量重命名' in _body_text(d))
        txt = _body_text(drv)
        results['rename'] = {
            'title_ok': '批量重命名' in txt,
            'no_unsafe_alert': '后端待支持' not in txt,
            'button_enabled': _btn_enabled(drv),
        }
        rule = drv.find_element(By.ID, 'batch-rename-rule')
        rule.clear()
        rule.send_keys('INT927_')
        _shot(drv, '01-rename-dialog-light', 'rename')
        _btn_confirm(drv).click()
        WebDriverWait(drv, 8).until(lambda d: '批量操作完成' in _body_text(d))
        time.sleep(0.5)
        results['rename']['request_bodies'] = _drain_batch_bodies(drv)
        results['rename']['toast_ok'] = '批量操作完成' in _body_text(drv)
        results['rename']['toast_text'] = _body_text(drv).split('批量操作完成')[-1][:40]
        _shot(drv, '02-rename-toast', 'rename')

        # ── 4. modify-properties：metadata ──
        _goto_audio_and_select(drv, RENAMED)
        _open_bulk_menu(drv, '批量修改属性')
        WebDriverWait(drv, 6).until(lambda d: '批量修改属性' in _body_text(d))
        txt = _body_text(drv)
        results['modify_metadata'] = {
            'title_ok': '批量修改属性' in txt,
            'no_unsafe_alert': '后端待支持' not in txt,
            'button_disabled_empty_value': not _btn_enabled(drv),
        }
        val = drv.find_element(By.ID, 'batch-meta-value')
        val.send_keys('INT-927 接线验证')
        results['modify_metadata']['button_enabled_after_value'] = _btn_enabled(drv)
        _shot(drv, '01-modify-metadata-dialog-light', 'modify-metadata')
        _btn_confirm(drv).click()
        WebDriverWait(drv, 8).until(lambda d: '批量操作完成' in _body_text(d))
        time.sleep(0.5)
        results['modify_metadata']['request_bodies'] = _drain_batch_bodies(drv)
        results['modify_metadata']['toast_ok'] = '批量操作完成' in _body_text(drv)
        results['modify_metadata']['toast_text'] = _body_text(drv).split('批量操作完成')[-1][:40]
        _shot(drv, '02-modify-metadata-toast', 'modify-metadata')

        # ── 5. modify-properties：audio-type ──
        _goto_audio_and_select(drv, RENAMED)
        _open_bulk_menu(drv, '批量修改属性')
        WebDriverWait(drv, 6).until(lambda d: '批量修改属性' in _body_text(d))
        _select_option(drv, 'batch-property', '音频类型')
        WebDriverWait(drv, 4).until(lambda d: _btn_enabled(drv))
        results['modify_audio_type'] = {'button_enabled': _btn_enabled(drv)}
        _select_option(drv, 'batch-audio-type-value', '噪声')
        _shot(drv, '01-modify-audio-type-dialog-light', 'modify-audio-type')
        _btn_confirm(drv).click()
        WebDriverWait(drv, 8).until(lambda d: '批量操作完成' in _body_text(d))
        time.sleep(0.5)
        results['modify_audio_type']['request_bodies'] = _drain_batch_bodies(drv)
        results['modify_audio_type']['toast_ok'] = '批量操作完成' in _body_text(drv)
        _shot(drv, '02-modify-audio-type-toast', 'modify-audio-type')

        # ── 6. modify-properties：SPL（后端明确拒绝 per-audio）──
        _goto_audio_and_select(drv, RENAMED)
        _open_bulk_menu(drv, '批量修改属性')
        WebDriverWait(drv, 6).until(lambda d: '批量修改属性' in _body_text(d))
        _select_option(drv, 'batch-property', 'SPL 值')
        WebDriverWait(drv, 4).until(lambda d: '暂不支持' in _body_text(d))
        results['spl'] = {
            'button_disabled': not _btn_enabled(drv),
            'hint_shown': '暂不支持' in _body_text(drv),
        }
        _shot(drv, '01-spl-disabled-light', 'spl')

        # ── 7. 深色截图 ──
        _goto_audio_and_select(drv, RENAMED)
        _set_theme(drv, 'dark')
        _open_bulk_menu(drv, '批量修改属性')
        WebDriverWait(drv, 6).until(lambda d: '批量修改属性' in _body_text(d))
        val = drv.find_element(By.ID, 'batch-meta-value')
        val.send_keys('INT-927 接线验证 dark')
        _shot(drv, '01-modify-metadata-dialog-dark', 'modify-metadata')
        _goto_audio_and_select(drv, RENAMED)
        _open_bulk_menu(drv, '批量移动')
        WebDriverWait(drv, 6).until(lambda d: '批量移动音频' in _body_text(d))
        _shot(drv, '01-move-dialog-dark', 'move')
        _set_theme(drv, 'light')
        time.sleep(0.3)
    finally:
        drv.quit()

    # 8. 恢复测试数据
    rst = restore_audio()
    print('RESTORE post:', rst, flush=True)

    # 9. 证据
    evidence = ['## INT-927 音频批量操作四分支 浏览器实测 Network 证据', '']
    evidence.append('目标音频：id %d（INT-818 接线测试源，常驻 5000 栈），dev server %s。' % (AUDIO_ID, BASE))
    evidence.append('')
    for key, r in results.items():
        evidence.append(f'### {key}')
        evidence.append(json.dumps({k: v for k, v in r.items() if k != 'request_bodies'}, ensure_ascii=False, indent=2))
        bodies = r.get('request_bodies', [])
        if bodies:
            evidence.append('请求体：')
            for b in bodies:
                evidence.append(f'- `{json.dumps(b, ensure_ascii=False)}`')
        evidence.append('')
    with open(os.path.join(ARTIFACTS, 'network-evidence.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(evidence))

    print('=====SUMMARY=====')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
