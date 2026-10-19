# -*- coding: utf-8 -*-
"""INT-890 返工修复验证——播放设备扫描「添加」预填链路（Selenium headless，真实 Chrome）。

代码审计 P2-2：`device-mutate-drawer.tsx` buildDefaults playback 分支未读 `prefill`
（扫描侧 scan-devices-dialog 已构造 name/model/deviceUniqueId/channelIndex/sampleRate/deviceType），
导致点扫描结果「添加」→ 打开新增抽屉时预填全部丢失（channel_index 落 0）。

修复：playback 分支对齐 test 分支，`device?.x ?? scanPrefill?.x ?? default` 逐字段透传。

本脚本验收链路（§2.3 返工出口：测试工程师重验）：
① 设备页 → 播放设备页签 → 更多操作 → 扫描设备（打开即 autoStartScan）
② 后端 /playback-devices/scan 在本机无音频通道返回 0 行 → 用 window.fetch 运行时打点
   构造 1 行系统音频通道响应（字段名严格按后端 snake_case 契约），页面渲染扫描行
③ 点「添加」→ 关扫描窗 + 开「添加播放设备」抽屉 → 断言 name/model/device_unique_id/
   channel_index/sample_rate/device_type 六字段预填
④ 保存 → 抽屉关闭 + 捕获的真实 POST /api/v1/playback-devices 请求体断言同值
   （saved body 经 toPlaybackDeviceUpsertDto snake_case 契约）
⑤ 数据卫生：后端 API 定位新建行并 DELETE，库零残留
⑥ 浅 / 深色截图 + Network 证据

失败落 tests/ui/artifacts/int890_playback_prefill/<步骤>/。
"""
import json
import os
import time
import urllib.request
import urllib.error

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5325')
BACKEND = os.environ.get('REACT_BACKEND_BASE', 'http://localhost:5000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int890_playback_prefill')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 扫描打点注入的假行（字段名 = 后端 playback.py PlaybackScanItem snake_case 契约）
FAKE_ROW = {
    'name': '扬声器-右声道',
    'model': 'Loopback Audio',
    'device_unique_id': 'loopback_3',
    'channel_index': 2,
    'sample_rate': 48000,
    'type': 'dry',
    'is_registered': False,
}

FETCH_PATCH = """
(function() {
  window.__reqs = [];
  if (window.__origFetch) return;
  window.__origFetch = window.fetch;
  window.fetch = function(input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var method = (init && init.method) || (input && input.method) || 'GET';
    if (url.indexOf('/api/v1/') !== -1) {
      var body = null;
      try { body = init && init.body ? JSON.parse(init.body) : null; } catch (e) {}
      window.__reqs.push({ url: url, method: method, body: body });
    }
    if (url.indexOf('/api/v1/playback-devices/scan') !== -1) {
      var fake = %s;
      return Promise.resolve(new Response(JSON.stringify({
        success: true, code: 0, message: '成功扫描到 1 个新通道', data: [fake]
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return window.__origFetch.apply(this, arguments);
  };
})();
""" % json.dumps(FAKE_ROW)

FAILED = []


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    options.set_capability('goog:perfLoggingPrefs', {'enableNetwork': True, 'enablePage': False})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
    drv.set_page_load_timeout(60)
    return drv


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _check(name, cond, extra=''):
    if cond:
        print(f'  PASS  {name}')
    else:
        print(f'  FAIL  {name}  {extra}')
        FAILED.append(name)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _click_menu_item(drv, label):
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
    for it in items:
        if label in it.text:
            it.click()
            return True
    raise AssertionError(f'菜单项「{label}」未找到')


def _input_value_by_label(drv, label):
    """按 Field 标签文本找同 div 内 input（限定当前 role=dialog，避开页头同名标签）。"""
    els = drv.find_elements(
        By.XPATH, f"//*[@role='dialog']//label[contains(., '{label}')]/following-sibling::input")
    if not els:
        return None
    return els[0].get_attribute('value')


def _select_text_by_label(drv, label):
    """按 Field 标签文本找同 div 内 Select 触发钮文本（base-ui data-slot=select-trigger）。"""
    els = drv.find_elements(
        By.XPATH, f"//*[@role='dialog']//label[contains(., '{label}')]/following-sibling::*[@data-slot='select-trigger']")
    if not els:
        return None
    return (els[0].text or '').strip()


def _collect_network(drv, net_log):
    try:
        logs = drv.get_log('performance')
    except Exception:
        return
    for entry in logs:
        try:
            msg = json.loads(entry['message'])
            params = msg.get('params', {})
            method = msg.get('method')
            if method == 'Network.responseReceived':
                rid = params.get('requestId')
                resp = params.get('response', {})
                net_log.setdefault(rid, {})['status'] = resp.get('status')
                net_log[rid]['mime'] = resp.get('mimeType', '')
            elif method == 'Network.requestWillBeSent':
                rid = params.get('requestId')
                req = params.get('request', {})
                net_log.setdefault(rid, {})['url'] = req.get('url', '')
                net_log[rid]['method'] = req.get('method', '')
        except Exception:
            pass


def _shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    try:
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
    except Exception:
        pass


def _backend_json(path, method='GET', body=None):
    """直连常驻后端（证据/清理用；与前端 proxy 同源 :5000）。"""
    url = BACKEND + path
    req = urllib.request.Request(url, method=method)
    req.add_header('Content-Type', 'application/json')
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    try:
        with urllib.request.urlopen(req, data, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'body': e.read().decode('utf-8', 'ignore')}


def _cleanup_playback_by_name(name):
    """数据卫生：后端定位 name 匹配的播放设备并删除（信封 {success,code,message,data:{items}}）。"""
    try:
        env = _backend_json('/api/v1/playback-devices?page=1&per_page=1000')
        items = ((env.get('data') or {}).get('items')) or []
        ids = [it['id'] for it in items if it.get('name') == name]
        for i in ids:
            res = _backend_json(f'/api/v1/playback-devices/{i}', method='DELETE')
            print(f'  清理 DELETE /playback-devices/{i} -> {res.get("success", res)}')
        return len(ids)
    except Exception as e:
        print(f'  清理失败: {e}')
        return 0


def _run_scan_add_flow(drv, phase):
    """打开扫描弹窗 → 断言扫描行 → 点添加 → 断言抽屉预填 → 返回预填值 dict。"""
    # 更多操作 → 扫描设备
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    time.sleep(0.6)
    _click_menu_item(drv, '扫描设备')
    WebDriverWait(drv, 15).until(
        lambda d: '扫描播放设备' in _body_text(d))
    # 扫描 autoStartScan 走真实 POST /playback-devices/scan，被 fetch 打点接管 → 1 行
    WebDriverWait(drv, 15).until(
        lambda d: FAKE_ROW['name'] in _body_text(d))
    time.sleep(0.5)
    txt = _body_text(drv)
    _check(f'[{phase}] 扫描行渲染（{FAKE_ROW["name"]} / 通道 2）',
           FAKE_ROW['name'] in txt and '通道 2' in txt and '48000 Hz' in txt)
    _shot(drv, f'{phase}_1_scan_results')

    # 点行「添加」→ 关扫描窗 + 开新增抽屉（限定 dialog 内，避开页头「添加播放设备」主按钮）
    els = drv.find_elements(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='添加']")
    if not els:
        els = drv.find_elements(By.XPATH, "//*[@role='dialog']//button[contains(., '添加')]")
    if not els:
        raise AssertionError('扫描行「添加」按钮未找到')
    els[0].click()
    WebDriverWait(drv, 15).until(
        lambda d: '添加播放设备' in _body_text(d))
    time.sleep(1.0)
    prefill = {
        'name': _input_value_by_label(drv, '名称'),
        'model': _input_value_by_label(drv, '型号'),
        'deviceUniqueId': _input_value_by_label(drv, '系统唯一标识'),
        'channelIndex': _input_value_by_label(drv, '通道索引'),
        'sampleRate': _input_value_by_label(drv, '采样率'),
        'deviceType': _select_text_by_label(drv, '设备类型'),
    }
    _check(f'[{phase}] 抽屉已开（标题 添加播放设备）', '添加播放设备' in _body_text(drv))
    _check(f'[{phase}] 名称预填', prefill['name'] == FAKE_ROW['name'], prefill['name'])
    _check(f'[{phase}] 型号预填', prefill['model'] == FAKE_ROW['model'], prefill['model'])
    _check(f'[{phase}] 系统唯一标识预填', prefill['deviceUniqueId'] == FAKE_ROW['device_unique_id'],
           prefill['deviceUniqueId'])
    _check(f'[{phase}] 通道索引预填', prefill['channelIndex'] == str(FAKE_ROW['channel_index']),
           prefill['channelIndex'])
    _check(f'[{phase}] 采样率预填', prefill['sampleRate'] == str(FAKE_ROW['sample_rate']),
           prefill['sampleRate'])
    # 设备类型：wire 值即 scan 行 type='dry'；base-ui 闭合态程序设值显示原始值（INT-922 已知
    # 显示口径，标签 '干声设备' 或原始值 'dry' 均视为值正确）
    _check(f'[{phase}] 设备类型预填', prefill['deviceType'] in ('干声设备', 'dry'),
           prefill['deviceType'])
    _shot(drv, f'{phase}_2_drawer_prefill')
    # 等「已添加到设备登记表单」toast 自动消失（sonner ~4s），避免遮挡抽屉底部按钮
    try:
        WebDriverWait(drv, 8).until(
            lambda d: '已添加到设备登记表单' not in _body_text(d))
    except Exception:
        pass
    time.sleep(0.5)
    return prefill


def main():
    drv = _driver()
    net_log = {}
    os.makedirs(ARTIFACTS, exist_ok=True)
    try:
        # ── 浅色：完整链路（扫描 → 添加 → 预填 → 保存 → 清理） ──
        print('PHASE A: light — full chain')
        _goto(drv, '/devices/playback')
        WebDriverWait(drv, 20).until(lambda d: '设备管理' in _body_text(d))
        drv.execute_script(FETCH_PATCH)
        _run_scan_add_flow(drv, 'light')

        # 保存 → 抽屉关闭（页头「添加播放设备」主按钮常驻，改判抽屉独有「播放设备信息」节）
        drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
        WebDriverWait(drv, 15).until(lambda d: '播放设备已保存' in _body_text(d))
        WebDriverWait(drv, 10).until(lambda d: '播放设备信息' not in _body_text(d))
        _check('light 保存成功（toast 播放设备已保存）', '播放设备已保存' in _body_text(drv))
        _check('light 抽屉已关闭', '播放设备信息' not in _body_text(drv))

        # 捕获请求：scan POST + 新建 POST body
        reqs = drv.execute_script('return JSON.stringify(window.__reqs || [])')
        reqs = json.loads(reqs or '[]')
        scan_hits = [r for r in reqs if r['url'].endswith('/api/v1/playback-devices/scan')]
        create_hits = [r for r in reqs if r['url'].endswith('/api/v1/playback-devices')
                       and r['method'] == 'POST']
        _check('light 真实请求 POST /playback-devices/scan 已发', len(scan_hits) >= 1)
        _check('light 真实请求 POST /playback-devices（新建）已发', len(create_hits) >= 1)
        if create_hits:
            body = create_hits[-1].get('body') or {}
            _check('light 新建 body.name', body.get('name') == FAKE_ROW['name'], body.get('name'))
            _check('light 新建 body.model', body.get('model') == FAKE_ROW['model'], body.get('model'))
            _check('light 新建 body.device_unique_id',
                   body.get('device_unique_id') == FAKE_ROW['device_unique_id'],
                   body.get('device_unique_id'))
            _check('light 新建 body.channel_index',
                   body.get('channel_index') == FAKE_ROW['channel_index'],
                   body.get('channel_index'))
            _check('light 新建 body.sample_rate',
                   body.get('sample_rate') == FAKE_ROW['sample_rate'],
                   body.get('sample_rate'))
            _check('light 新建 body.device_type',
                   body.get('device_type') == FAKE_ROW['type'], body.get('device_type'))
        _collect_network(drv, net_log)
        _shot(drv, 'light_3_saved')

        # 数据卫生：后端删除新建行
        _cleanup_playback_by_name(FAKE_ROW['name'])

        # ── 深色：重复预填验证（主题 key=iatp:theme:v1:mode；about:blank 打断 bfcache 强制整页重载） ──
        print('PHASE B: dark — prefill re-check')
        drv.execute_script("try{localStorage.setItem('iatp:theme:v1:mode','dark')}catch(e){}")
        drv.get('about:blank')
        time.sleep(0.5)
        _goto(drv, '/devices/playback')
        WebDriverWait(drv, 20).until(lambda d: '设备管理' in _body_text(d))
        time.sleep(1.0)
        drv.execute_script(FETCH_PATCH)
        _run_scan_add_flow(drv, 'dark')
        # 取消关闭，不保存
        drv.find_element(By.XPATH, "//button[contains(., '取消')]").click()
        WebDriverWait(drv, 10).until(lambda d: '播放设备信息' not in _body_text(d))
        _check('dark 取消关闭抽屉', '播放设备信息' not in _body_text(drv))

        # 最终卫生：确保无残留
        _cleanup_playback_by_name(FAKE_ROW['name'])

        # Network 摘要（performance resource 真实请求）
        resources = drv.execute_script(
            "return performance.getEntriesByType('resource').map(function(e){return e.name})")
        api_hits = sorted({r.split('?')[0] for r in resources if '/api/v1/' in r})
        print('\nNetwork 真实请求（深色页 performance entries）:')
        for url in api_hits:
            print(f'  {url.replace(BASE, "")}')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    print('\n=== INT-890 playback prefill 修复验证 ===')
    if FAILED:
        print(f'FAILED: {len(FAILED)} 项 — {FAILED}')
        raise SystemExit(1)
    print('ALL PASS ✅')
    raise SystemExit(0)


if __name__ == '__main__':
    main()
