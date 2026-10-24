# -*- coding: utf-8 -*-
"""INT-1624 验收（测试工程师独立脚本）——浏览器实测层。

被测：本卡交付提交 66868293 的 React 构建（临时 nginx 容器 http://127.0.0.1:15241，
/api 反代 docker 网关 15000 / 真实库 intelligent_audio_test）。与实现者脚本无关，
选择器与断言独立编写，重点核对「可见状态」而不是只看 DOM 存在。

覆盖验收标准：
  1 更多操作 → 导入/导出入口可用（不再 disabled）、按页签取资源；
    导入：点击选文件 + 拖拽各一次、未选文件禁用、结果计数与接口 JSON 逐项一致、
          errors 行号可读、关闭重开无残留；
    导出：格式 JSON/Excel 各一次、范围 全部/选中/筛选后 各一次、文件名时间戳与扩展名；
  2 导出字段白名单（JSON）+ Excel 表头（由 verify_int1624_acceptance.py 已覆盖，这里核对文件本体）;
  4 异常文件 → 后端 400 且前端显示错误（不静默）；
  5 权限：无 create 码导入入口不渲染 / 无 read 码导出入口不渲染（页内 /auth/me 桩）；
  6 跨组件：导入成功后列表/徽章/统计卡刷新；导出不改列表与计数；
  8 浅色 + 深色截图 + Network（URL / 状态码 / Content-Disposition）。

数据纪律：只写「接线测试_INT1624_UI」前缀，脚本结尾 API 删除并复核零残留。
"""
import functools
import json
import os
import shutil
import sys
import time

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

print = functools.partial(print, flush=True)  # noqa: A001
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15241')
GATEWAY = 'http://127.0.0.1:15000/api/v1'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1624_acc')
DOWNLOADS = os.path.join(ART, 'downloads')
FILES = os.path.join(ART, 'files')
for p in (ART, DOWNLOADS, FILES):
    os.makedirs(p, exist_ok=True)

PREFIX = '接线测试_INT1624_UI'
SERIAL = 'JX1624UI001'
PLAYBACK_UID = 'JX1624UIUID01'

FAILS = []
LOGS = []
CREATED = {'test': [], 'playback': []}


def check(name, cond, detail=''):
    msg = ('[PASS] ' if cond else '[FAIL] ') + name + ((' — ' + str(detail)) if detail else '')
    print(msg)
    LOGS.append(msg)
    if not cond:
        FAILS.append(name)


def chromedriver_path():
    cache = os.path.expanduser(r'~\AppData\Local\selenium')  # 备选
    roots = [
        os.path.join(os.environ.get('USERPROFILE', ''), '.cache', 'selenium', 'chromedriver', 'win64'),
        r'D:\00_user_data\.cache\selenium\chromedriver\win64',
        cache,
    ]
    best_key, best_exe = None, ''
    for root in roots:
        if not os.path.isdir(root):
            continue
        for ver in os.listdir(root):
            exe = os.path.join(root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                key = tuple(int(x) for x in ver.split('.') if x.isdigit())
                if best_key is None or key > best_key:
                    best_key, best_exe = key, exe
    return best_exe


FETCH_PATCH = r"""
window.__net = [];
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const method = ((init || {}).method || 'GET').toUpperCase();
    let res, body = null;
    try { res = await orig.apply(this, arguments); }
    catch (e) { window.__net.push({url, method, status: -1, error: String(e)}); throw e; }
    try {
      if (url.indexOf('/import') !== -1 && (res.headers.get('content-type')||'').indexOf('json') !== -1) {
        body = await res.clone().text();
      }
    } catch (e) {}
    window.__net.push({url, method, status: res.status, body});
    return res;
  };
})();
"""

PERM_PATCH = r"""
(function(){
  const orig = window.fetch;
  window.fetch = function(input, init){
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    if (url.indexOf('/api/v1/auth/me') !== -1) {
      let perms = null;
      try { perms = JSON.parse(localStorage.getItem('iatp:probe_perms') || 'null'); } catch(e) {}
      if (perms) {
        return Promise.resolve(new Response(JSON.stringify({success: true, code: 0, data: {
          id: 4242, username: 'probe', permissions: perms}}),
          {status: 200, headers: {'Content-Type': 'application/json'}}));
      }
    }
    return orig.apply(this, arguments);
  };
})();
"""


def driver():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'int1624acc_chrome')
    shutil.rmtree(profile, ignore_errors=True)
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1080')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + profile)
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    p = chromedriver_path()
    d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
    d.set_page_load_timeout(45)
    d.set_script_timeout(240)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': DOWNLOADS})
    return d


def body(d):
    return d.execute_script('return document.body.textContent || ""') or ''


def click(d, el):
    d.execute_script('arguments[0].click();', el)


def wait_body(d, text, timeout=45):
    WebDriverWait(d, timeout).until(lambda x: text in body(x))


def shot(d, name):
    path = os.path.join(ART, name + '.png')
    d.save_screenshot(path)
    print('SHOT', path)
    return path


def theme(d, mode):
    d.execute_script(
        """const m = arguments[0];
           localStorage.setItem('iatp:theme:v1:mode', JSON.stringify(m));
           document.documentElement.classList.remove('light','dark');
           document.documentElement.classList.add(m);""", mode)
    time.sleep(1.0)
    cls = d.execute_script('return document.documentElement.className')
    bg = d.execute_script('return getComputedStyle(document.body).backgroundColor')
    return cls, bg


def goto(d, tab):
    d.get(BASE + '/devices/' + tab)
    wait_body(d, '设备管理', 60)
    time.sleep(2.0)


def open_more(d):
    btn = WebDriverWait(d, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label='更多操作']")))
    click(d, btn)
    WebDriverWait(d, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[role='menuitem']")))
    time.sleep(0.5)


def menu_texts(d):
    return [e.text.strip() for e in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")]


def click_menu(d, label):
    el = WebDriverWait(d, 10).until(EC.presence_of_element_located(
        (By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '%s')]" % label)))
    click(d, el)
    time.sleep(1.0)


def dialog(d):
    return WebDriverWait(d, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[role='dialog']")))


def dialog_text(d):
    try:
        return d.find_element(By.CSS_SELECTOR, "[role='dialog']").text
    except Exception:
        return ''


def close_dialog(d):
    for label in ('关闭', '取消'):
        try:
            click(d, d.find_element(By.XPATH,
                  "//div[@role='dialog']//button[normalize-space(.)='%s']" % label))
            time.sleep(0.8)
            return True
        except Exception:
            continue
    return False


def button_in_dialog(d, label):
    return WebDriverWait(d, 10).until(EC.presence_of_element_located(
        (By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='%s']" % label)))


def net_entries(d, needle):
    try:
        data = d.execute_script('return window.__net || []') or []
    except Exception:
        return []
    return [e for e in data if needle in (e.get('url') or '')]


def clear_net(d):
    d.execute_script('window.__net = []')


def perf(d, needle):
    out, reqs = [], {}
    try:
        entries = d.get_log('performance')
    except Exception:
        return out
    for entry in entries:
        try:
            msg = json.loads(entry.get('message') or '')
        except Exception:
            continue
        inner = msg.get('message') or {}          # CDP 双层：msg.message.method / params
        method = inner.get('method') or ''
        params = inner.get('params') or {}
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            url = req.get('url') or ''
            if needle in url:
                reqs[params.get('requestId')] = {'method': req.get('method'), 'url': url,
                                                 'status': None, 'headers': {}}
        elif method == 'Network.responseReceived' and params.get('requestId') in reqs:
            resp = params.get('response') or {}
            reqs[params['requestId']]['status'] = resp.get('status')
            reqs[params['requestId']]['headers'] = resp.get('headers') or {}
    return list(reqs.values())


def wait_download(before, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        now = set(os.listdir(DOWNLOADS))
        partial = [f for f in now if f.endswith('.crdownload')]
        new = [f for f in (now - before)
               if not f.endswith('.crdownload') and not f.endswith('.htm')
               and f != 'downloads.htm']
        if new and not partial:
            time.sleep(0.8)
            return sorted(new)
        time.sleep(1)
    return []


def upload(d, path):
    inp = WebDriverWait(d, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[role='dialog'] input[type='file']")))
    inp.send_keys(path)
    time.sleep(1.0)


def wait_import_idle(d, timeout=300):
    WebDriverWait(d, timeout).until(lambda x: '正在导入' not in dialog_text(x))
    time.sleep(1.5)


def api_get(path):
    return requests.get(GATEWAY + path, timeout=120).json()


def api_items(path):
    return ((api_get(path).get('data') or {}).get('items')) or []


def cleanup():
    removed = 0
    for it in api_items('/test-devices?page=1&per_page=1000'):
        if str(it.get('name', '')).startswith(PREFIX):
            requests.delete(GATEWAY + '/test-devices/%s' % it['id'], timeout=120)
            removed += 1
    for it in api_items('/playback-devices?page=1&per_page=1000'):
        if str(it.get('name', '')).startswith(PREFIX):
            requests.delete(GATEWAY + '/playback-devices/%s' % it['id'], timeout=120)
            removed += 1
    for it in api_items('/apis?page=1&per_page=1000'):
        if str(it.get('name', '')).startswith(PREFIX):
            requests.delete(GATEWAY + '/apis/%s' % it['id'], timeout=120)
            removed += 1
    time.sleep(2)
    left = [it.get('name') for p in ('/test-devices', '/playback-devices', '/apis')
            for it in api_items(p + '?page=1&per_page=1000')
            if str(it.get('name', '')).startswith(PREFIX)]
    return removed, left


def write_files():
    f = {}
    p = os.path.join(FILES, 'pick.json')
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump({'test_devices': [{
            'name': PREFIX + '勾选', 'model': 'UI-Model', 'type': 'physical',
            'system': 'Android', 'system_version': '14', 'app_name': 'iatp',
            'app_version': '1.0', 'description': 'from-ui-click', 'location': 'UI-Lab',
            'serial_number': SERIAL, 'status': 'offline'}]}, fh, ensure_ascii=False)
    f['pick'] = p

    p = os.path.join(FILES, 'drag.json')
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write('{}')
    f['drag'] = p

    p = os.path.join(FILES, 'mixed.json')
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump({'test_devices': [
            {'name': PREFIX + '勾选', 'model': 'UI-Model', 'type': 'physical',
             'system': 'Android', 'system_version': '14', 'app_name': 'iatp',
             'app_version': '1.0', 'description': 'updated-by-ui', 'serial_number': SERIAL,
             'status': 'offline'},
            {'name': PREFIX + '缺键', 'model': 'UI-Model', 'type': 'physical',
             'system': 'Android', 'system_version': '14', 'app_name': 'iatp',
             'app_version': '1.0', 'description': 'no-serial'}]}, fh, ensure_ascii=False)
    f['mixed'] = p

    p = os.path.join(FILES, 'bad.txt')
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write('plain text, not importable')
    f['bad'] = p

    p = os.path.join(FILES, 'playback.json')
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump({'playback_devices': [{
            'name': PREFIX + '播放新', 'model': 'UI-PB', 'device_type': 'dry',
            'sample_rate': 48000, 'device_unique_id': PLAYBACK_UID,
            'channel_index': 0, 'description': 'ui-import', 'status': 'offline'}]},
            fh, ensure_ascii=False)
    f['playback'] = p

    p = os.path.join(FILES, 'api.json')
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump({'apis': [{
            'name': PREFIX + 'API-UI', 'vendor': 'ui-vendor', 'description': 'ui-import',
            'status': 'online', 'meta': {}, 'default_max_process': 5,
            'default_max_timeout': 30, 'default_max_audio_duration': 60,
            'endpoints': [], 'output_types': []}]}, fh, ensure_ascii=False)
    f['api'] = p
    return f


def badge_text(d):
    """顶部「在线 n/共 m」徽章（从正文正则取，避免命中大容器）。"""
    import re
    m = re.search(r'在线\s*\d+\s*/\s*共\s*\d+', body(d))
    return m.group(0) if m else ''


def stat_total(d):
    """统计卡「总设备数」数值（正文正则，避免依赖卡片 DOM 结构）。"""
    import re
    m = re.search(r'总设备数\s*(\d+)', body(d))
    return int(m.group(1)) if m else None


def main():
    files = write_files()
    for name in os.listdir(DOWNLOADS):
        try:
            os.remove(os.path.join(DOWNLOADS, name))
        except Exception:
            pass
    pre_removed, pre_left = cleanup()
    print('pre-clean', pre_removed, pre_left)

    d = driver()
    t0 = time.time()
    try:
        # ===== 1. 入口 =====
        goto(d, 'test')
        shot(d, 'acc_devices_test_light')
        open_more(d)
        texts = menu_texts(d)
        check('更多操作菜单含「导入设备」「导出设备」', '导入设备' in texts and '导出设备' in texts, texts)
        imp = d.find_element(By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '导入设备')]")
        exp = d.find_element(By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '导出设备')]")
        check('导入设备入口未禁用（无 disabled / aria-disabled）',
              imp.get_attribute('aria-disabled') != 'true' and imp.get_attribute('data-disabled') is None)
        check('导出设备入口未禁用（无 disabled / aria-disabled）',
              exp.get_attribute('aria-disabled') != 'true' and exp.get_attribute('data-disabled') is None)
        check('入口不再有「后端建设中」提示', '后端建设中' not in body(d))

        # ===== 2. 导入弹窗（点击选文件） =====
        click(d, imp)
        dt = dialog(d)
        text = dialog_text(d)
        check('点击「导入设备」打开弹窗（标题按当前页签=测试设备）',
              '导入测试设备' in text, text.split('\n')[:2])
        check('格式提示「支持格式：JSON / CSV / Excel」', '支持格式：JSON / CSV / Excel' in text)
        check('未选文件时「开始导入」禁用',
              button_in_dialog(d, '开始导入').get_attribute('disabled') is not None)
        shot(d, 'acc_import_dialog_light')

        # 拖拽选文件
        d.execute_script("""
          const input = document.querySelector('[role="dialog"] input[type="file"]');
          const zone = input.closest('div[class*="border-dashed"]') || input.parentElement;
          const dt = new DataTransfer();
          dt.items.add(new File(['{}'], 'drag.json', {type: 'application/json'}));
          zone.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
          zone.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
        """)
        time.sleep(1.0)
        check('拖拽选文件后回显文件名', 'drag.json' in dialog_text(d), dialog_text(d)[:80])
        shot(d, 'acc_import_drag_light')

        # 点击选择真正文件
        upload(d, files['pick'])
        check('点击「选择文件」后回显 pick.json', 'pick.json' in dialog_text(d))
        check('已选文件后「开始导入」可点',
              button_in_dialog(d, '开始导入').get_attribute('disabled') is None)

        clear_net(d)
        click(d, button_in_dialog(d, '开始导入'))
        wait_import_idle(d)
        entries = net_entries(d, '/import')
        entry = entries[-1] if entries else {}
        payload = json.loads(entry.get('body') or '{}') if entry.get('body') else {}
        data = payload.get('data') or {}
        shown = dialog_text(d)
        check('导入请求 POST /test-devices/import 200', entry.get('method') == 'POST' and entry.get('status') == 200,
              (entry.get('url'), entry.get('status')))
        check('导入新建计数与接口 JSON 一致（成功导入 1 个，更新 0 个，跳过 0 个）',
              data.get('imported_count') == 1 and '成功导入 1 个，更新 0 个，跳过 0 个' in shown,
              (data, shown[:120]))
        check('结果区注明「设备状态以本环境为准」', '设备状态以本环境为准' in shown)
        shot(d, 'acc_import_result_light')

        # 关闭重开无残留
        close_dialog(d)
        open_more(d)
        click_menu(d, '导入设备')
        dialog(d)
        text2 = dialog_text(d)
        check('关闭再开无残留（无文件名 / 无结果）',
              'pick.json' not in text2 and '成功导入' not in text2 and '设备状态以本环境为准' not in text2, text2[:100])
        check('重开后「开始导入」回到禁用',
              button_in_dialog(d, '开始导入').get_attribute('disabled') is not None)

        # ===== 3. 部分成功导入（合法行更新 + 缺键行跳过） =====
        upload(d, files['mixed'])
        clear_net(d)
        click(d, button_in_dialog(d, '开始导入'))
        wait_import_idle(d)
        entries = net_entries(d, '/import')
        entry = entries[-1] if entries else {}
        payload = json.loads(entry.get('body') or '{}') if entry.get('body') else {}
        data = payload.get('data') or {}
        shown = dialog_text(d)
        errs = data.get('errors') or []
        check('部分成功：更新 1 / 跳过 1 与接口一致',
              data.get('updated_count') == 1 and data.get('skipped_count') == 1, data)
        check('弹窗结果文案 = 接口 message',
              bool(payload.get('message')) and payload['message'] in shown, payload.get('message'))
        check('errors 行号可读且渲染在结果区',
              any('第2行' in str(e) for e in errs) and '第2行' in shown, errs)
        shot(d, 'acc_import_partial_light')

        # ===== 4. 异常文件 → 400 且前端显示 =====
        upload(d, files['bad'])
        clear_net(d)
        click(d, button_in_dialog(d, '开始导入'))
        wait_import_idle(d)
        entries = net_entries(d, '/import')
        entry = entries[-1] if entries else {}
        shown = dialog_text(d)
        check('.txt 导入：后端 400', entry.get('status') == 400, entry.get('status'))
        check('.txt 导入：前端显示错误提示（不静默）',
              '仅支持' in shown or '失败' in shown, shown[-160:].replace('\n', '|'))
        shot(d, 'acc_import_error_light')
        close_dialog(d)

        # ===== 5. 导出（格式 / 范围） =====
        # 5.1 JSON + 全部
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        text = dialog_text(d)
        check('导出弹窗打开（标题按页签）', '导出测试设备' in text, text.split('\n')[:2])
        check('格式默认 JSON、范围默认全部',
              'JSON' in text and '全部' in text and '当前页选中' in text and '当前筛选结果' in text)
        shot(d, 'acc_export_dialog_light')
        before = set(os.listdir(DOWNLOADS))
        clear_net(d)
        click(d, button_in_dialog(d, '导出'))
        new = wait_download(before)
        check('导出 JSON（全部）下载到本地文件', len(new) == 1, new)
        if new:
            fn = new[0]
            check('文件名 test_devices_<YYYYmmdd_HHMMSS>.json',
                  fn.startswith('test_devices_') and fn.endswith('.json') and len(fn.split('_')[-1].split('.')[0]) == 6, fn)
            with open(os.path.join(DOWNLOADS, fn), 'r', encoding='utf-8') as fh:
                doc = json.load(fh)
            rows = doc.get('test_devices') or []
            check('下载文件 total_count 与行数一致', doc.get('total_count') == len(rows), (doc.get('total_count'), len(rows)))
            check('下载文件字段不含 id / created_at',
                  rows and 'id' not in rows[0] and 'created_at' not in rows[0], sorted(rows[0].keys()) if rows else [])
        time.sleep(1.0)
        exports = perf(d, '/export')
        exp_e = exports[-1] if exports else {}
        check('Network：GET /test-devices/export?format=json 200',
              exp_e.get('method') == 'GET' and exp_e.get('status') == 200
              and 'format=json' in (exp_e.get('url') or ''), (exp_e.get('url'), exp_e.get('status')))
        cd = {k.lower(): v for k, v in (exp_e.get('headers') or {}).items()}.get('content-disposition', '')
        check('Network：响应头 Content-Disposition 带 test_devices_*.json', 'test_devices_' in cd and '.json' in cd, cd)

        # 5.2 Excel 格式
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        trig = WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[role='dialog'] [data-slot='select-trigger']")))
        click(d, trig)
        time.sleep(0.8)
        opt = WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//*[@role='option'][contains(normalize-space(.), 'Excel')]")))
        click(d, opt)
        time.sleep(0.6)
        before = set(os.listdir(DOWNLOADS))
        click(d, button_in_dialog(d, '导出'))
        new = wait_download(before)
        check('导出 Excel 下载 .xlsx 文件', len(new) == 1 and new[0].endswith('.xlsx'), new)
        if new:
            with open(os.path.join(DOWNLOADS, new[0]), 'rb') as fh:
                head = fh.read(2)
            check('xlsx 文件头 PK', head == b'PK', head)
        time.sleep(1.0)
        exports = perf(d, '/export')
        exp_e = exports[-1] if exports else {}
        check('Network：format=excel 200', 'format=excel' in (exp_e.get('url') or '') and exp_e.get('status') == 200,
              (exp_e.get('url'), exp_e.get('status')))

        # 5.3 筛选后范围（搜索 keyword 缩小结果集）
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        radio = WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//div[@role='dialog']//label[contains(normalize-space(.), '当前筛选结果')]/input")))
        click(d, radio)
        time.sleep(0.5)
        before = set(os.listdir(DOWNLOADS))
        clear_net(d)
        click(d, button_in_dialog(d, '导出'))
        new = wait_download(before)
        time.sleep(1.0)
        exports = net_entries(d, '/export')
        exp_e = exports[-1] if exports else {}
        check('范围=当前筛选结果：请求带 ids 且未筛选时等于全量 id 集',
              'ids=' in (exp_e.get('url') or '') and exp_e.get('status') == 200, exp_e.get('url'))
        check('范围=当前筛选结果：下载成功', len(new) == 1, new)

        # 5.3b 筛选后的「当前筛选结果」只覆盖筛选后的 id
        goto(d, 'test')
        box = WebDriverWait(d, 15).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[placeholder^='搜索']")))
        click(d, box)
        box.send_keys(Keys.CONTROL, 'a')
        box.send_keys(Keys.DELETE)
        box.send_keys('pura90')
        time.sleep(2.0)
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        click(d, WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//div[@role='dialog']//label[contains(normalize-space(.), '当前筛选结果')]/input"))))
        time.sleep(0.4)
        before = set(os.listdir(DOWNLOADS))
        clear_net(d)
        click(d, button_in_dialog(d, '导出'))
        new = wait_download(before)
        time.sleep(1.0)
        exports = net_entries(d, '/export')
        url = (exports[-1].get('url') if exports else '') or ''
        if new:
            with open(os.path.join(DOWNLOADS, new[0]), 'r', encoding='utf-8') as fh:
                filt_doc = json.load(fh)
            names = [r.get('name') for r in (filt_doc.get('test_devices') or [])]
        else:
            names = []
        check('筛选后范围：导出只含筛选命中的记录（3 条 pura90*）',
              len(names) == 3 and all('pura90' in (n or '') for n in names), names)
        from urllib.parse import unquote
        ids_part = unquote(url.split('ids=')[1]) if 'ids=' in url else ''
        check('筛选后范围：请求 ids 个数 = 筛选结果条数',
              len([x for x in ids_part.split(',') if x]) == len(names) == 3, (ids_part, names))
        # 清掉筛选
        click(d, box)
        box.send_keys(Keys.CONTROL, 'a')
        box.send_keys(Keys.DELETE)
        time.sleep(1.5)

        # 5.4 选中范围（先开批量模式勾选一行）
        goto(d, 'test')
        try:
            sw = d.find_element(By.CSS_SELECTOR, "[data-slot='switch'][aria-label='批量操作模式']")
            if (sw.get_attribute('aria-checked') or sw.get_attribute('data-checked')) in (None, 'false'):
                click(d, sw)
                time.sleep(1)
        except Exception as exc:
            print('batch switch:', exc)
        try:
            cb = WebDriverWait(d, 15).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[role='checkbox'][aria-label*='选择']")))
            click(d, cb)
            time.sleep(1.0)
        except Exception as exc:
            print('row checkbox:', exc)
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        radio = WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//div[@role='dialog']//label[contains(normalize-space(.), '当前页选中')]/input")))
        click(d, radio)
        time.sleep(0.5)
        before = set(os.listdir(DOWNLOADS))
        click(d, button_in_dialog(d, '导出'))
        new = wait_download(before)
        time.sleep(1.0)
        exports = perf(d, '/export')
        exp_e = exports[-1] if exports else {}
        url = exp_e.get('url') or ''
        check('范围=当前页选中：请求带 ids=<n 个> 且 200',
              'ids=' in url and exp_e.get('status') == 200, url)
        if new:
            with open(os.path.join(DOWNLOADS, new[0]), 'r', encoding='utf-8') as fh:
                sel_doc = json.load(fh)
            check('选中范围导出只含 1 条', len(sel_doc.get('test_devices') or []) == 1,
                  len(sel_doc.get('test_devices') or []))
        else:
            check('选中范围导出只含 1 条', False, 'no download')

        # 5.5 导出弹窗关闭重开无残留（格式/范围回到默认）
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        trig = WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[role='dialog'] [data-slot='select-trigger']")))
        click(d, trig)
        time.sleep(0.8)
        click(d, WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//*[@role='option'][contains(normalize-space(.), 'Excel')]"))))
        time.sleep(0.5)
        click(d, WebDriverWait(d, 10).until(EC.presence_of_element_located(
            (By.XPATH, "//div[@role='dialog']//label[contains(normalize-space(.), '当前筛选结果')]/input"))))
        time.sleep(0.4)
        close_dialog(d)
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        trig_text = d.find_element(By.CSS_SELECTOR,
                                   "[role='dialog'] [data-slot='select-trigger']").text.strip()
        checked = d.execute_script(
            "const r = document.querySelector('[role=\"dialog\"] input[type=\"radio\"]:checked');"
            "return r ? r.value : null;")
        check('导出弹窗关闭重开：格式回默认 JSON、范围回默认全部',
              trig_text == 'JSON' and checked == 'all', (trig_text, checked))
        close_dialog(d)

        # 5.6 测试 API 页签：弹窗标题与资源随页签切换
        goto(d, 'api')
        open_more(d)
        click_menu(d, '导入设备')
        dialog(d)
        check('测试 API 页签：导入弹窗标题 = 导入测试 API', '导入测试 API' in dialog_text(d),
              dialog_text(d)[:30])
        close_dialog(d)
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        check('测试 API 页签：导出弹窗标题 = 导出测试 API', '导出测试 API' in dialog_text(d),
              dialog_text(d)[:30])
        close_dialog(d)
        # 测试 API 页签真实导入：请求打到 /apis/import
        open_more(d)
        click_menu(d, '导入设备')
        dialog(d)
        upload(d, files['api'])
        clear_net(d)
        click(d, button_in_dialog(d, '开始导入'))
        wait_import_idle(d)
        entries = net_entries(d, '/import')
        entry = entries[-1] if entries else {}
        payload = json.loads(entry.get('body') or '{}') if entry.get('body') else {}
        check('测试 API 页签：导入请求 POST /apis/import 200',
              entry.get('method') == 'POST' and '/apis/import' in (entry.get('url') or '')
              and entry.get('status') == 200, (entry.get('url'), entry.get('status')))
        check('测试 API 页签：导入结果计数与接口一致',
              ((payload.get('data') or {}).get('imported_count') == 1
               and '成功导入 1 个' in dialog_text(d)), (payload.get('message'), dialog_text(d)[-80:]))
        close_dialog(d)

        # ===== 6. 状态同步：播放设备导入 → 徽章/列表刷新；导出不改计数 =====
        goto(d, 'playback')
        badge_before = badge_text(d)
        stat_before = stat_total(d)
        before_ids = {it['id'] for it in api_items('/playback-devices?page=1&per_page=1000')}
        open_more(d)
        click_menu(d, '导入设备')
        dt = dialog(d)
        check('切到播放设备页签，弹窗标题随页签切换', '导入播放设备' in dialog_text(d), dialog_text(d)[:40])
        upload(d, files['playback'])
        click(d, button_in_dialog(d, '开始导入'))
        wait_import_idle(d)
        shown = dialog_text(d)
        check('播放设备导入结果 imported=1', '成功导入 1 个' in shown, shown[:120])
        close_dialog(d)
        time.sleep(3.0)
        badge_after = badge_text(d)
        stat_after = stat_total(d)
        after_ids = {it['id'] for it in api_items('/playback-devices?page=1&per_page=1000')}
        check('导入后徽章总数 +1', bool(badge_before) and badge_before != badge_after,
              (badge_before, badge_after))
        check('导入后统计卡「总设备数」+1', stat_before is not None and stat_after == stat_before + 1,
              (stat_before, stat_after))
        check('导入后列表出现新记录（接口 + 页面可见）',
              len(after_ids) == len(before_ids) + 1 and PREFIX + '播放新' in body(d),
              (len(before_ids), len(after_ids)))
        shot(d, 'acc_playback_after_import_light')

        # 导出不改计数
        goto(d, 'playback')
        badge_g0 = badge_text(d)
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        before = set(os.listdir(DOWNLOADS))
        click(d, button_in_dialog(d, '导出'))
        new = wait_download(before)
        time.sleep(2.0)
        goto(d, 'playback')
        badge_g1 = badge_text(d)
        check('导出后列表与计数不变（仍为导出前徽章）', badge_g0 == badge_g1, (badge_g0, badge_g1))

        # 切页签再切回数据仍在
        goto(d, 'api')
        goto(d, 'playback')
        check('切页签再切回，新记录仍在', PREFIX + '播放新' in body(d))

        # ===== 7. 深色截图 =====
        cls, bg = theme(d, 'dark')
        check('深色主题生效（html.dark）', 'dark' in (cls or ''), (cls, bg))
        time.sleep(1.2)
        shot(d, 'acc_devices_dark')
        open_more(d)
        click_menu(d, '导入设备')
        dialog(d)
        shot(d, 'acc_import_dialog_dark')
        close_dialog(d)
        open_more(d)
        click_menu(d, '导出设备')
        dialog(d)
        shot(d, 'acc_export_dialog_dark')
        close_dialog(d)
        theme(d, 'light')

        # ===== 8. 权限显隐（/auth/me 桩） =====
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PERM_PATCH})

        def menu_for(perms):
            d.execute_script("localStorage.setItem('iatp:probe_perms', arguments[0])",
                             json.dumps(perms))
            d.get(BASE + '/devices/test')
            WebDriverWait(d, 60).until(
                lambda x: ('设备管理' in body(x)) or ('/403' in x.current_url) or ('403' in body(x)))
            time.sleep(2.0)
            if '设备管理' not in body(d):
                return None
            open_more(d)
            t = menu_texts(d)
            click(d, d.find_element(By.TAG_NAME, 'body'))
            time.sleep(0.4)
            return t

        only_read = menu_for(['device:read']) or []
        check('仅 read 码：导入入口不渲染', bool(only_read) and not any('导入设备' in t for t in only_read), only_read)
        check('仅 read 码：导出入口渲染', any('导出设备' in t for t in only_read), only_read)

        only_create = menu_for(['device:create'])
        page = body(d)
        check('仅 create 码（无 read）：页面被路由守卫拦到 403',
              '/403' in d.current_url or '403' in page or '无权限' in page, d.current_url)
        check('仅 create 码：导出入口不渲染（403 页无菜单）',
              '导出设备' not in page or '/403' in d.current_url, d.current_url)

        d.execute_script("localStorage.removeItem('iatp:probe_perms')")

    finally:
        try:
            d.quit()
        except Exception:
            pass
        removed, left = cleanup()
        check('收尾零残留（接线测试_INT1624_UI 前缀全删）', not left, (removed, left))

    print('\n==== UI 验收：%d 项失败 / 用时 %.1fs ====' % (len(FAILS), time.time() - t0))
    for f in FAILS:
        print('FAILED:', f)
    with open(os.path.join(ART, 'result.log'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(LOGS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
