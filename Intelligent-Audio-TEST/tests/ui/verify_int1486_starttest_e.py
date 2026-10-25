# -*- coding: utf-8 -*-
"""INT-1486 脚本 E（收尾取证）：POST /tasks 精简请求体（target_modes/config）+ 深色任务命名弹窗截图。"""
import json, os, sys, time, traceback

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_int1486_starttest_c import (  # noqa: E402
    ART, BASE, DEVICE_NAME, TASK_NAME, enter_resources, api_req, js_click, text, wait_text,
    shot, dialogs, dialog_text, close_dialog, find_api_card_button, By, Keys, time as _t,
)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

PATCH = r"""
window.__req = [];
const __of = window.fetch;
window.fetch = function(input, init) {
  let url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || 'GET';
  const rec = { url: String(url), method: method, status: null, brief: null };
  if (method === 'POST' && String(url).includes('/tasks') && init && init.body) {
    try {
      const b = JSON.parse(String(init.body));
      rec.brief = { name: b.name, case_count: (b.case_ids || []).length, device_ids: b.device_ids,
                    api_ids: b.api_ids, target_modes: b.target_modes, config: b.config,
                    case_devices_sample: (b.case_devices || []).slice(0, 3) };
    } catch (e) { rec.brief = 'parse err'; }
  }
  window.__req.push(rec);
  return __of.apply(this, arguments).then(function(r) { rec.status = r.status; return r; });
};
"""


def driver(token):
    o = Options(); o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
              '--disable-dev-shm-usage', '--no-first-run']:
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "try{localStorage.setItem('iatp:auth:token:v1', %s); localStorage.setItem('iatp:theme:v1:mode','dark');}catch(e){}" % json.dumps(token)})
    return d


def main():
    token = open(os.path.join(ART, 'token.txt')).read().strip()
    st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
    # 新建一个端点可达的自建 API（host.docker.internal:15000/health -> 200）
    created_name = '接线测试_INT1486_APIY_' + str(int(time.time()))[-6:]
    st, created = api_req('POST', '/api/v1/apis', token, {
        'name': created_name,
        'description': 'INT-1486 请求体取证临时', 'algorithm_type': 'voice_llm', 'default_max_process': 5,
        'endpoints': [{'endpoint': 'http://host.docker.internal:15000', 'name': None, 'max_process': 1,
                       'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                       'description': None}]})
    api_name = created_name
    print('created api', st, api_name, json.dumps(created, ensure_ascii=False)[:150])
    d = driver(token)
    task_id = None
    try:
        enter_resources(d)
        shot(d, 'E_step2_dark.png')
        dc = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择设备 {DEVICE_NAME}"]')
        if dc:
            js_click(d, dc[0]); time.sleep(1.2)
        ac = find_api_card_button(d, api_name, '选择 API')
        if ac:
            js_click(d, ac); time.sleep(1.2)
        modes = d.find_elements(By.CSS_SELECTOR, f'[aria-label="{DEVICE_NAME} 执行模式"]')
        if modes:
            s = modes[0].find_elements(By.XPATH, ".//*[normalize-space(.)='串行']")
            if s:
                js_click(d, s[0]); time.sleep(1.2)
            print('MODE control', modes[0].text.replace('\n', '|'))
        net = d.find_elements(By.XPATH, "//h4[normalize-space()='网络配置']/following-sibling::*//*[@data-slot='select-trigger']")
        if net:
            js_click(d, net[0]); time.sleep(1)
            wi = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.text.strip() == 'Wi-Fi']
            if wi:
                js_click(d, wi[0]); time.sleep(1)
        starts = d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
        js_click(d, starts[-1]); time.sleep(2.5)
        ti = d.find_elements(By.CSS_SELECTOR, 'input#task-name')
        print('taskname dialog open', len(ti), [x.get_attribute('value') for x in ti])
        shot(d, 'E_taskname_dark.png')
        if not ti:
            raise RuntimeError('dialog not open')
        ti[0].send_keys(Keys.CONTROL, 'a'); ti[0].send_keys(Keys.DELETE); ti[0].send_keys(TASK_NAME)
        time.sleep(0.6)
        n0 = d.execute_script('return (window.__req||[]).length')
        js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
        time.sleep(15)
        reqs = d.execute_script('return (window.__req||[]).slice(arguments[0])', n0)
        for r in reqs:
            print('REQ', r['method'], r['status'], r['url'])
            if r.get('brief'):
                print('  BRIEF', json.dumps(r['brief'], ensure_ascii=False)[:2000])
        with open(os.path.join(ART, 'task_submit_brief.json'), 'w', encoding='utf-8') as f:
            json.dump(reqs, f, ensure_ascii=False, indent=1)
        st, tasks = api_req('GET', '/api/v1/tasks?page=1&per_page=10', token)
        for it in (tasks.get('data', tasks) or {}).get('items', []):
            if str(it.get('name') or '').startswith('接线测试_INT1486'):
                task_id = it['id']
        print('new task', task_id)
        d.get(BASE + f'/tasks/{task_id}')
        time.sleep(6)
        rows = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
        print('detail rows', len(rows))
        if rows:
            js_click(d, rows[0]); time.sleep(4)
            shot(d, 'E_case_detail_dark.png')
            print('dark case-detail', dialog_text(d)[:200].replace('\n', ' | '))
            close_dialog(d)
    except Exception:
        traceback.print_exc()
        shot(d, 'E_error.png')
    finally:
        d.quit()
    # 清理
    if task_id:
        print('stop', api_req('POST', f'/api/v1/tasks/{task_id}/stop', token)[0])
        print('del', api_req('DELETE', f'/api/v1/tasks/{task_id}', token)[0])
        print('purge', api_req('DELETE', f'/api/v1/tasks/{task_id}/purge', token)[0])
    st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
    for it in (apis.get('data', apis) or {}).get('items', []):
        if str(it.get('name') or '').startswith('接线测试_INT1486'):
            print('CLEAN api', it['id'], api_req('DELETE', f"/api/v1/apis/{it['id']}", token)[0])
    st, tasks = api_req('GET', '/api/v1/tasks?page=1&per_page=10', token)
    print('RESIDUE tasks', [x['name'] for x in (tasks.get('data', tasks) or {}).get('items', []) if 'INT1486' in (x.get('name') or '')])
    st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
    print('RESIDUE apis', [x['name'] for x in (apis.get('data', apis) or {}).get('items', []) if 'INT1486' in (x.get('name') or '')])


if __name__ == '__main__':
    main()
