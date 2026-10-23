# -*- coding: utf-8 -*-
"""INT-1663 取证：音频特征分析·质量评估弹窗接线（§6.23）。

环境：docker 真实库栈——React dev 5388（临时配置代理 /api → http://127.0.0.1:15000）。
流程：
1. AUTH_MODE=off 直接进 /audio-import，按真实音频 2071 定位行（名称取自 GET /audios/2071）；
2. 行操作 →「特征分析·质量评估」：抓 /features、/quality 两条真实请求与响应；
   质量评估渲染真实计算值；特征分析若端点仍 400，按错误态 + 重试呈现（非空态）；
3. 处理操作：增益调整 +3 dB / 生成新文件 → 提交 /process，回读 GET /audios/{new_id} 比对；
4. 在本次新建的音频上验 mode=overwrite（降噪覆盖），回读 file_path/size 变化；
5. 浅色 / 深色各一张弹窗截图 + Network 证据截图；
6. 删除本 run 造出的音频记录。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5388')
ART = 'tests/ui/artifacts/int1663'
DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
TARGET_ID = int(os.environ.get('AUDIO_ID', '2071'))
os.makedirs(ART, exist_ok=True)

WATCH = ('/features', '/quality', '/process', '/audios/')

FETCH_PATCH = r"""
window.__net = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const reqBody = (init && init.body && typeof init.body === 'string') ? init.body : null;
  const res = await __origFetch.apply(this, arguments);
  let respText = null;
  if (/\/features|\/quality|\/process/.test(url)) {
    try { respText = await res.clone().text(); } catch (e) {}
  }
  try { window.__net.push({url: url, method: method, status: res.status,
                           body: reqBody, resp: respText, t: Date.now()}); } catch (e) {}
  return res;
};
"""


def log(msg):
    print(msg, flush=True)


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


def _opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1100')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    return o


def ensure_session(drv):
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


def set_search(drv, text):
    box = WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索音频']")))
    box.click()
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    if text:
        box.send_keys(text)
    time.sleep(2.0)


def open_feature_dialog(drv, name):
    btn = WebDriverWait(drv, 40).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[@aria-label='音频 %s 的操作']" % name)))
    js_click(drv, btn)
    item = WebDriverWait(drv, 15).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='menuitem'][contains(normalize-space(.), '特征分析')]")))
    js_click(drv, item)
    # base-ui 关闭态残留 DOM：取最后一个可见 dialog
    WebDriverWait(drv, 20).until(
        lambda d: any(e.is_displayed() for e in d.find_elements(
            By.XPATH, "//div[@role='dialog']//h2[contains(normalize-space(.), '音频特征分析')]")))
    time.sleep(1.5)


def dialog(drv):
    nodes = [e for e in drv.find_elements(By.XPATH, "//div[@role='dialog']") if e.is_displayed()]
    assert nodes, '未找到可见弹窗'
    return nodes[-1]


def dialog_button(drv, text):
    """按文案取当前可见弹窗内的按钮（每次重取，避开 React 重渲染后的 stale 引用）"""
    node = dialog(drv)
    return node.find_element(By.XPATH, ".//button[normalize-space(.)='%s']" % text)


def close_dialog(drv):
    node = dialog(drv)
    btn = node.find_element(By.XPATH, ".//button[contains(normalize-space(.), '关闭')]")
    js_click(drv, btn)
    WebDriverWait(drv, 15).until(lambda d: not any(
        e.is_displayed() for e in d.find_elements(By.XPATH, "//div[@role='dialog']")))
    time.sleep(0.8)


def net_entries(drv, needle):
    return [e for e in drv.execute_script('return window.__net || []')
            if needle in e.get('url', '')]


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(os.path.abspath(path))
    log('截图：%s' % path)
    return os.path.abspath(path)


def overlay(drv, lines):
    js = """
    const old = document.getElementById('net-evidence');
    if (old) old.remove();
    const box = document.createElement('div');
    box.id = 'net-evidence';
    box.style.cssText = 'position:fixed;left:16px;top:16px;z-index:99999;background:#0f172a;color:#e2e8f0;'
      + 'font:12px/1.55 Consolas,monospace;padding:14px 18px;border-radius:10px;max-width:1500px;'
      + 'white-space:pre-wrap;word-break:break-all;box-shadow:0 10px 40px rgba(0,0,0,.5)';
    box.textContent = arguments[0];
    document.body.appendChild(box);
    """
    drv.execute_script(js, '\n'.join(lines))
    time.sleep(0.5)


def remove_overlay(drv):
    drv.execute_script("const e=document.getElementById('net-evidence'); if(e) e.remove();")


def main():
    drv = webdriver.Chrome(service=Service(DRIVER), options=_opts())
    drv.set_script_timeout(180)
    drv.command_executor.set_timeout(600)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    evidence = {'target_id': TARGET_ID, 'assertions': []}
    created_ids = []
    try:
        ensure_session(drv)
        st, target = api(drv, '/api/v1/audios/%s' % TARGET_ID)
        assert st == 200 and target, '读取音频 %s 失败: %s' % (TARGET_ID, st)
        name = target['name']
        log('目标音频：id=%s name=%s duration=%s' % (TARGET_ID, name, target.get('duration')))
        evidence['audio'] = {k: target.get(k) for k in ('id', 'name', 'format', 'duration', 'size')}

        # ---- 1. 打开弹窗：特征 + 质量两条真实请求 ----
        set_search(drv, name.split('_')[0])
        open_feature_dialog(drv, name)
        root = dialog(drv)
        body_text = root.text
        log('弹窗可见文本片段：\n%s' % body_text[:600])

        # 质量评估真实值（GET /audios/{id}/quality 200）
        quality_entries = [e for e in net_entries(drv, '/quality') if 'GET' == e['method']]
        assert quality_entries, '未捕获 /quality 请求'
        q = quality_entries[-1]
        log('GET /quality → %s %s' % (q['status'], q['resp']))
        assert q['status'] == 200, '质量评估端点非 200：%s' % q['status']
        qdata = json.loads(q['resp'])['data']
        evidence['quality_request'] = {'status': q['status'], 'body': q['resp']}
        for field, text in (
            ('snr_db', '%s dB' % qdata['snr_db']),
            ('dynamic_range_db', '%s dB' % qdata['dynamic_range_db']),
            ('frequency_response_score', '%s 分' % qdata['frequency_response_score']),
            ('quality_score', '%s 分' % qdata['quality_score']),
        ):
            assert text in body_text, '质量评估未渲染 %s（期望「%s」）' % (field, text)
            evidence['assertions'].append('质量 %s=%s 渲染一致' % (field, qdata[field]))

        # 特征分析：端点状态如实记录（200 渲染值 / 400+ 错误态 + 重试）
        feature_entries = [e for e in net_entries(drv, '/features') if 'GET' == e['method']]
        assert feature_entries, '未捕获 /features 请求'
        f = feature_entries[-1]
        log('GET /features → %s %s' % (f['status'], f['resp']))
        evidence['features_request'] = {'status': f['status'], 'body': f['resp']}
        if f['status'] == 200:
            fdata = json.loads(f['resp'])['data']
            sp, en, td = fdata['spectral'], fdata['energy'], fdata['time_domain']
            for text in (
                '%s Hz' % sp['dominant_frequency'],
                '%s–%s Hz' % (sp['fundamental_range_low'], sp['fundamental_range_high']),
                '%s%%' % sp['harmonic_distortion'],
                '%s dBFS' % en['average_energy_db'],
                '%s dBFS' % en['peak_energy_db'],
                str(en['energy_concentration']),
                str(td['zero_crossing_rate']),
                str(td['active_duration_ratio']),
                '%s s' % td['onset_time'],
            ):
                assert text in body_text, '特征未渲染期望值「%s」' % text
            evidence['assertions'].append('特征三组真实值全部渲染')
        else:
            assert '特征分析加载失败' in body_text, '特征端点失败但未呈现错误态'
            assert '重试' in body_text, '特征错误态缺重试钮'
            assert '特征分析待后端接口' not in body_text, '仍残留「待后端接口」空态'
            assert '待 FEAT' not in body_text, '仍残留「待 FEAT」文案'
            evidence['assertions'].append(
                '特征端点 %s → 错误态 + 重试（非空态）' % f['status'])

        shot(drv, 'int1663-dialog-light.png')

        # ---- 2. 处理操作：增益调整 +3 dB / 生成新文件 ----
        js_click(drv, dialog_button(drv, '增益调整'))
        time.sleep(0.6)
        gain = dialog(drv).find_element(By.ID, 'audio-process-gain')
        gain.click()
        gain.send_keys(Keys.CONTROL, 'a')
        gain.send_keys('3')
        time.sleep(0.4)
        js_click(drv, dialog_button(drv, '开始处理'))

        WebDriverWait(drv, 180).until(
            lambda d: any('最近一次处理' in e.text for e in
                          d.find_elements(By.XPATH, "//div[@role='dialog']")))
        time.sleep(1.5)
        proc_new = [e for e in net_entries(drv, '/process') if e['method'] == 'POST']
        assert proc_new, '未捕获 POST /process'
        p = proc_new[-1]
        log('POST /process → %s %s' % (p['status'], p['resp']))
        assert p['status'] == 200, '处理失败：%s %s' % (p['status'], p['resp'])
        pdata = json.loads(p['resp'])['data']
        new_id = pdata['new_audio_id']
        created_ids.append(new_id)
        evidence['process_new'] = {'request': p['body'], 'status': p['status'], 'response': p['resp']}
        log('请求体：%s' % p['body'])

        st, readback = api(drv, '/api/v1/audios/%s' % new_id)
        assert st == 200 and readback, '回读新音频失败：%s' % st
        evidence['process_new']['readback'] = {
            k: readback.get(k) for k in ('id', 'name', 'format', 'file_path', 'duration', 'size')
        }
        assert readback['format'] == pdata['format'], '回读 format 不一致'
        assert abs(float(readback['duration']) - float(pdata['duration'])) < 0.01, '回读 duration 不一致'
        assert int(readback['size']) == int(pdata['size']), '回读 size 不一致'
        assert readback['file_path'] == pdata['file_path'], '回读 file_path 不一致'
        evidence['assertions'].append('process(new) 提交后 GET /audios/%s 回读一致' % new_id)
        shot(drv, 'int1663-process-new-result.png')
        close_dialog(drv)

        # ---- 3. mode=overwrite：在本次新建的音频上验（降噪覆盖） ----
        new_name = readback['name']
        set_search(drv, new_name)
        open_feature_dialog(drv, new_name)
        js_click(drv, dialog_button(drv, '降噪'))
        time.sleep(0.5)
        js_click(drv, dialog_button(drv, '覆盖原文件'))
        time.sleep(0.5)
        js_click(drv, dialog_button(drv, '开始处理'))
        alert = WebDriverWait(drv, 20).until(
            EC.visibility_of_element_located((By.XPATH, "//div[@role='alertdialog']")))
        assert '原文件不可恢复' in alert.text, '覆盖未二次确认'
        evidence['assertions'].append('overwrite 提交前二次确认弹窗出现')
        js_click(drv, alert.find_element(
            By.XPATH, ".//button[normalize-space(.)='确定覆盖']"))

        WebDriverWait(drv, 240).until(
            lambda d: any('已覆盖原文件' in e.text for e in
                          d.find_elements(By.XPATH, "//div[@role='dialog']")))
        time.sleep(1.5)
        proc_ow = [e for e in net_entries(drv, '/process') if e['method'] == 'POST']
        o = proc_ow[-1]
        log('POST /process(overwrite) → %s %s' % (o['status'], o['resp']))
        assert o['status'] == 200, '覆盖处理失败：%s %s' % (o['status'], o['resp'])
        odata = json.loads(o['resp'])['data']
        assert odata['mode'] == 'overwrite', '覆盖模式回包 mode 非 overwrite'
        assert not odata.get('new_audio_id'), '覆盖模式不应产生新音频记录'
        evidence['process_overwrite'] = {'request': o['body'], 'status': o['status'], 'response': o['resp']}

        st, rb2 = api(drv, '/api/v1/audios/%s' % new_id)
        evidence['process_overwrite']['readback'] = {
            k: rb2.get(k) for k in ('id', 'name', 'format', 'file_path', 'duration', 'size')
        }
        assert st == 200
        assert rb2['file_path'] == odata['file_path'], '覆盖后回读 file_path 不一致'
        assert rb2['file_path'] != readback['file_path'], '覆盖后 file_path 未变化'
        assert rb2['name'] == new_name, '覆盖不应改名'
        evidence['assertions'].append('process(overwrite) 回读 file_path 已切换、记录名不变')

        # ---- 4. Network 证据截图（浅色） ----
        net_lines = []
        net_lines.append('GET  /api/v1/audios/%s/features            -> %s' % (TARGET_ID, f['status']))
        net_lines.append('  %s' % (f['resp'] or '')[:220])
        net_lines.append('')
        net_lines.append('GET  /api/v1/audios/%s/quality             -> %s' % (TARGET_ID, q['status']))
        net_lines.append('  %s' % q['resp'])
        net_lines.append('')
        net_lines.append('POST /api/v1/audios/%s/process  (new)      -> %s' % (TARGET_ID, p['status']))
        net_lines.append('  req  %s' % p['body'])
        net_lines.append('  resp %s' % p['resp'])
        net_lines.append('')
        net_lines.append('POST /api/v1/audios/%s/process (overwrite) -> %s' % (new_id, o['status']))
        net_lines.append('  req  %s' % o['body'])
        net_lines.append('  resp %s' % o['resp'])
        overlay(drv, net_lines)
        shot(drv, 'int1663-network.png')
        remove_overlay(drv)
        evidence['network_text'] = '\n'.join(net_lines)
        close_dialog(drv)

        # ---- 5. 深色主题截图（同源 reload 后重开弹窗） ----
        drv.execute_script(
            "localStorage.setItem('iatp:theme:v1:mode', 'dark')")
        drv.refresh()
        time.sleep(3)
        set_search(drv, name.split('_')[0])
        open_feature_dialog(drv, name)
        WebDriverWait(drv, 90).until(
            lambda d: any('%s dB' % qdata['snr_db'] in e.text for e in
                          d.find_elements(By.XPATH, "//div[@role='dialog']")))
        time.sleep(1.2)
        shot(drv, 'int1663-dialog-dark.png')
        close_dialog(drv)
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'light')")

        evidence['created_audio_ids'] = created_ids
        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as fh:
            json.dump(evidence, fh, ensure_ascii=False, indent=2)
        log('证据已写：%s' % os.path.join(ART, 'evidence.json'))
        log('断言：\n- ' + '\n- '.join(evidence['assertions']))
    finally:
        # 清理本 run 造出的音频（含中途失败残留）
        for audio_id in list(created_ids):
            try:
                st, data = api(drv, '/api/v1/audios/%s' % audio_id, 'DELETE')
                log('清理音频 %s → %s %s' % (audio_id, st, data))
            except Exception as exc:  # noqa: BLE001
                log('清理音频 %s 失败：%s' % (audio_id, exc))
        drv.quit()


if __name__ == '__main__':
    main()
