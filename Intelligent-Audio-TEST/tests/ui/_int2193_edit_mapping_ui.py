# -*- coding: utf-8 -*-
"""INT-2193 浏览器实测：编辑已有参数映射的算法 → 改「转换」→ 发布。

场景（docker 旁路容器，真实库 intelligent_audio_test）：
  1. 登录 dev_user；
  2. /AlgorithmConfig 找到自建算法「接线测试_INT2193_ui」→ 编辑；
  3. 高级配置 → 评估参数映射 → 平铺视图 → 该行「转换」选 JSON解析；
  4. 发布 → 用 performance log 抓 PUT /algorithm/definitions/<type> 的状态码；
  5. 浅色/深色截图 + 网络证据截图。

用法：python -u tests/ui/_int2193_edit_mapping_ui.py [base_url]
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:15249').rstrip('/')
ALGO_NAME = '接线测试_INT2193_ui'
ALGO_TYPE = 'wiring_int2193_ui'
DRIVER = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
SHOT_DIR = os.environ.get('SHOT_DIR', r'D:/00_user_data/iat_int2193/shots')
os.makedirs(SHOT_DIR, exist_ok=True)

log_lines = []


def log(*args):
    msg = ' '.join(str(a) for a in args)
    print(msg, flush=True)
    log_lines.append(msg)


def shot(drv, name):
    path = os.path.join(SHOT_DIR, name)
    drv.save_screenshot(path)
    log('screenshot:', path)
    return path


FETCH_PATCH = r"""
window.__reqlog = [];
(function () {
  const orig = window.fetch;
  window.fetch = async function (...args) {
    const req = args[0];
    const url = typeof req === 'string' ? req : ((req && req.url) || '');
    const method = ((args[1] && args[1].method) || (req && req.method) || 'GET').toUpperCase();
    const body = (args[1] && args[1].body) || '';
    const resp = await orig.apply(this, args);
    let text = '';
    try { text = await resp.clone().text(); } catch (e) { text = ''; }
    window.__reqlog.push({ url: url, method: method, status: resp.status,
                           reqBody: String(body).slice(0, 4000),
                           respBody: text.slice(0, 4000) });
    return resp;
  };
})();
"""


def make_driver():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    drv = webdriver.Chrome(service=Service(DRIVER), options=o)
    drv.set_script_timeout(300)
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def drain_perf(drv):
    entries = []
    for e in drv.get_log('performance'):
        try:
            msg = json.loads(e['message'])['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            entries.append({
                'url': r['url'],
                'status': r['status'],
                'method': msg['params'].get('type', ''),
                'requestId': msg['params']['requestId'],
                'mimeType': r.get('mimeType', ''),
            })
        elif msg.get('method') == 'Network.requestWillBeSent':
            entries.append({
                'url': msg['params']['request']['url'],
                'method': msg['params']['request']['method'],
                'requestId': msg['params']['requestId'],
                '_req': True,
            })
    return entries


def login(drv, wait):
    drv.get(BASE + '/login')
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#username')))
    drv.find_element(By.CSS_SELECTOR, '#username').send_keys('dev_user')
    drv.find_element(By.CSS_SELECTOR, '#password').send_keys('dev_password')
    drv.find_element(By.CSS_SELECTOR, 'button[type=submit]').click()
    wait.until(lambda d: '/login' not in d.current_url)
    log('login ok ->', drv.current_url)


def click_xpath(drv, xpath, timeout=20):
    el = WebDriverWait(drv, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath)))
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.3)
    drv.execute_script('arguments[0].click();', el)
    return el


def wait_text(drv, xpath, timeout=20):
    return WebDriverWait(drv, timeout).until(
        EC.presence_of_element_located((By.XPATH, xpath)))


def open_edit_sheet(drv, wait):
    drv.get(BASE + '/AlgorithmConfig')
    row = wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//tr[contains(., '{ALGO_NAME}')]")))
    log('row found:', row.text.replace('\n', ' | ')[:160])
    # 行内操作菜单
    menu = row.find_element(By.XPATH, ".//button[contains(@aria-label, '的操作')]")
    drv.execute_script('arguments[0].click();', menu)
    time.sleep(0.5)
    click_xpath(drv, "//*[@role='menuitem' and contains(normalize-space(.), '编辑')]")
    wait.until(EC.presence_of_element_located((By.XPATH, "//*[@role='dialog']")))
    log('edit sheet opened')


def expand_mappings(drv):
    click_xpath(drv, "//*[@role='dialog']//button[contains(normalize-space(.), '高级配置')]")
    time.sleep(0.6)
    click_xpath(drv, "//*[@role='dialog']//button[contains(normalize-space(.), '评估参数映射')]")
    time.sleep(0.8)
    click_xpath(drv, "//*[@role='dialog']//button[normalize-space(.)='平铺视图']")
    time.sleep(0.6)
    log('mappings section expanded (flat view)')


def mapping_row(drv):
    return WebDriverWait(drv, 20).until(EC.presence_of_element_located(
        (By.XPATH,
         "//*[@role='dialog']//tbody/tr[.//td[contains(normalize-space(.), 'query')]]")))


def set_transform(drv, row, target_label):
    # 转换列 = 倒数第 2 个 td
    cell = row.find_element(By.XPATH, './td[last()-1]')
    trigger = cell.find_element(By.XPATH, './/button')
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', trigger)
    log('transform cell before:', cell.text.strip())
    drv.execute_script('arguments[0].click();', trigger)
    time.sleep(0.6)
    opt = WebDriverWait(drv, 15).until(EC.element_to_be_clickable(
        (By.XPATH, f"//*[@role='option'][contains(normalize-space(.), '{target_label}')]")))
    drv.execute_script('arguments[0].click();', opt)
    time.sleep(0.6)
    log('transform cell after:', cell.text.strip())
    return cell


def resource_entries(drv, needle='/algorithm/definitions'):
    return drv.execute_script(
        """
        return performance.getEntriesByType('resource')
          .filter(e => e.name.includes(arguments[0]))
          .map(e => ({name:e.name, type:e.initiatorType, status:e.responseStatus,
                      startTime:Math.round(e.startTime)}));
        """, needle)


def publish_and_capture(drv):
    baseline = int(drv.execute_script('return (window.__reqlog||[]).length;'))
    shot(drv, 'int2193_01_sheet_light.png')
    btn = WebDriverWait(drv, 15).until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='发布']")))
    log('publish disabled?', btn.get_attribute('disabled'))
    drv.execute_script('arguments[0].click();', btn)

    target_hits = []
    deadline = time.time() + 150
    while time.time() < deadline:
        time.sleep(1.5)
        entries = drv.execute_script('return (window.__reqlog||[]);')[baseline:]
        target_hits = [
            e for e in entries
            if e['method'] == 'PUT' and e['url'].rstrip('/').split('/')[-1] == ALGO_TYPE
            and '/definitions/' in e['url']
        ]
        if target_hits:
            break
    log('__reqlog new entries:', json.dumps(
        [{k: e[k] for k in ('method', 'url', 'status')}
         for e in drv.execute_script('return (window.__reqlog||[]);')[baseline:]],
        ensure_ascii=False)[:1200])

    detail = {}
    if target_hits:
        hit = target_hits[-1]
        detail = {'method': 'PUT', 'url': hit['url'], 'status': hit['status']}
        try:
            req_body = json.loads(hit['reqBody']) if hit['reqBody'] else {}
            maps = (req_body.get('mappings') or {}).get('evaluation') or []
            detail['request_mapping_ids'] = [m.get('id') for m in maps]
            detail['request_transform'] = [m.get('transform_type') for m in maps]
            log('PUT request body mappings:', json.dumps(maps, ensure_ascii=False))
        except Exception as exc:
            log('request body parse failed:', repr(exc))
        try:
            resp = json.loads(hit['respBody'])
            detail['resp_success'] = resp.get('success')
            detail['resp_code'] = resp.get('code')
            detail['resp_message'] = str(resp.get('message'))[:300]
            rows = [m for v in ((resp.get('data') or {}).get('mappings') or {}).values() for m in v]
            detail['resp_transform'] = [m.get('transform_type') for m in rows]
            log('PUT response:', json.dumps(
                {k: detail.get(k) for k in ('resp_success', 'resp_code', 'resp_message',
                                            'resp_transform')}, ensure_ascii=False)[:800])
        except Exception as exc:
            log('response body parse failed:', repr(exc), hit['respBody'][:300])

    time.sleep(0.8)
    try:
        body = drv.find_element(By.TAG_NAME, 'body').text
        for kw in ('算法已发布', '发布失败', '发布冲突', '算法已创建'):
            if kw in body:
                detail['page_text'] = kw
                log('page text contains:', kw)
    except Exception:
        pass
    shot(drv, 'int2193_02_after_publish_light.png')
    return detail


def network_evidence(drv, detail):
    """把抓到的发布请求渲染成页内浮层并截图（Network 证据图）。"""
    payload = [{
        'method': detail.get('method', 'PUT'),
        'url': detail.get('url', ''),
        'status': detail.get('status'),
        'ids': detail.get('request_mapping_ids'),
        'sent': detail.get('request_transform'),
        'success': detail.get('resp_success'),
        'code': detail.get('resp_code'),
        'saved': detail.get('resp_transform'),
    }]
    drv.execute_script(
        """
        const data = arguments[0];
        const old = document.getElementById('int2193-net');
        if (old) old.remove();
        const box = document.createElement('div');
        box.id = 'int2193-net';
        box.style.cssText = 'position:fixed;left:20px;top:20px;z-index:2147483647;'
          + 'background:#0b1020;color:#d7e3ff;font:13px/1.6 Consolas,monospace;'
          + 'padding:14px 18px;border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.5);max-width:1300px';
        box.innerHTML = '<div style="font-weight:700;margin-bottom:8px">Network（发布请求）</div>'
          + data.map(d => '<div>' + d.method + ' ' + d.url + ' → <b style="color:'
            + (d.status === 200 ? '#4ade80' : '#f87171') + '">' + d.status + '</b></div>'
            + '<div>请求 mappings[].id = ' + JSON.stringify(d.ids) + '</div>'
            + '<div>请求 transform_type = ' + JSON.stringify(d.sent) + '</div>'
            + '<div>响应 success=' + d.success + ' code=' + d.code
            + ' 回读 transform_type=' + JSON.stringify(d.saved) + '</div>').join('');
        document.body.appendChild(box);
        """,
        payload,
    )
    time.sleep(0.4)
    return shot(drv, 'int2193_03_network.png')


def dark_mode(drv):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    drv.get('about:blank')
    time.sleep(0.5)
    return True


def dark_capture(drv, wait):
    """深色：localStorage 切主题后重进路由 → 编辑 Sheet → 高级配置展开截图。"""
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    drv.get('about:blank')
    time.sleep(0.5)
    drv.get(BASE + '/AlgorithmConfig')
    time.sleep(2.5)
    open_edit_sheet(drv, wait)
    expand_mappings(drv)
    time.sleep(0.8)
    row = mapping_row(drv)
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', row)
    time.sleep(0.6)
    log('dark class:', drv.execute_script(
        "return document.documentElement.className;"))
    return shot(drv, 'int2193_04_sheet_dark.png')


def main():
    drv = make_driver()
    wait = WebDriverWait(drv, 30)
    try:
        login(drv, wait)
        open_edit_sheet(drv, wait)
        expand_mappings(drv)
        row = mapping_row(drv)
        current = row.find_element(By.XPATH, './td[last()-1]').text.strip()
        target = '转大写' if 'JSON解析' in current else 'JSON解析'
        log('switch transform ->', target)
        set_transform(drv, row, target)
        puts = publish_and_capture(drv)
        net_shot = network_evidence(drv, puts)
        ok = (
            puts.get('status') == 200
            and puts.get('resp_success') is True
            and bool(puts.get('request_mapping_ids'))
            and all(i for i in puts.get('request_mapping_ids') or [])
        )
        log('RESULT', 'PASS' if ok else 'FAIL', json.dumps(
            {k: puts.get(k) for k in ('status', 'request_mapping_ids', 'resp_success',
                                      'resp_code', 'resp_transform', 'page_text')},
            ensure_ascii=False))
        try:
            dark_capture(drv, wait)
        except Exception as exc:  # 深色图不影响主判定
            log('dark capture failed:', repr(exc))
        return 0 if ok else 1
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    code = main()
    with open(os.path.join(SHOT_DIR, 'run.log'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    sys.exit(code)
