# -*- coding: utf-8 -*-
"""INT-1624 设备导入导出接线实测（React 接线 / docker 真实库栈）。

覆盖：
  1 设计文档 §4.5.1/§4.5.2 交互流程：更多操作 → 导入/导出弹窗（按页签取资源）、
    选文件（点击 + 拖拽）、开始导入、计数与 errors、关闭重开无残留；
    导出格式 JSON/Excel、范围 全部/选中/筛选后、文件下载与文件名时间戳。
  2 导出字段白名单（测试设备）：逐字段一致，不含 id / created_at。
  3 导入闭环：播放设备 导出→删除→导入（新建）→再导入（更新，不产生第二条）；
    测试设备 / API 走「命中匹配键 → 更新」闭环。
  4 异常与部分成功：.txt / 空文件 / 非法 JSON → 后端 400 + 弹窗错误提示；
    混合文件（合法行 + 缺匹配键行）→ 更新 1、跳过 1、errors 带行号。
  6 跨组件状态同步：导入成功后列表 / 顶部「在线 n/共 m」/统计卡刷新。
  8 浅色 + 深色截图、弹窗截图、Network（URL / 状态码 / Content-Disposition）证据。

环境：React dev server http://127.0.0.1:5324（proxy → docker 网关 15000，真实库
intelligent_audio_test）。AUTH_MODE=off。
数据纪律：只写「接线测试_INT1624_」前缀，脚本末尾删除并核对零残留。
"""
import functools
import json
import os
import shutil
import sys
import time
import urllib.request

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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5324')
GATEWAY = os.environ.get('REAL_GATEWAY', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1624')
DOWNLOADS = os.path.join(ART, 'downloads')
os.makedirs(DOWNLOADS, exist_ok=True)

PREFIX = '接线测试_INT1624_'
DEVICE_NAME = PREFIX + '设备'
DEVICE_SERIAL = 'JX1624SN10'
PLAYBACK_NAME = PREFIX + '播放'
PLAYBACK_UID = 'JX1624UID20'
API_NAME = PREFIX + 'API'

# 后端导出字段白名单（device_import_export_service.py _TEST_DEVICE_FIELDS）
TEST_DEVICE_FIELDS = [
    'name', 'model', 'type', 'system', 'system_version', 'app_name',
    'app_version', 'description', 'location', 'max_audio_duration',
    'needs_prompt_audio', 'prompt_config', 'connection_type',
    'keywords', 'serial_number', 'ip', 'status', 'supported_algorithms',
]

_FAILURES = []
_EVIDENCE = {}


def check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
    if not cond:
        _FAILURES.append(name)


# ---------------------------------------------------------------- browser

FETCH_PATCH = r"""
window.__fetchLog = [];
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const init2 = init || {};
    const method = (init2.method || 'GET').toUpperCase();
    let res;
    try { res = await orig.apply(this, arguments); }
    catch (e) {
      window.__fetchLog.push({url: url, method: method, status: -1, error: String(e)});
      throw e;
    }
    const entry = {url: url, method: method, status: res.status};
    try {
      if (init2.body instanceof FormData) {
        const f = init2.body.get('file');
        entry.formFile = f ? f.name : null;
      }
    } catch (e) {}
    try {
      const ct = res.headers.get('content-type') || '';
      if (url.indexOf('/import') !== -1 && ct.indexOf('json') !== -1) {
        entry.respBody = await res.clone().text();
      }
    } catch (e) {}
    window.__fetchLog.push(entry);
    return res;
  };
})();
"""


def chromedriver_path():
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = []
    if os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
    return max(cands)[1] if cands else ''


def driver():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'int1624_chrome')
    shutil.rmtree(profile, ignore_errors=True)
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
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
    return d


def js_click(drv, el):
    drv.execute_script('arguments[0].click();', el)


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait_text(drv, needle, timeout=30):
    WebDriverWait(drv, timeout).until(lambda d: needle in body_text(d))


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('SHOT', path)
    return path


def apply_theme(drv, mode):
    drv.execute_script(
        """
        const v = arguments[0];
        localStorage.setItem('iatp:theme:v1:mode', JSON.stringify(v));
        document.documentElement.classList.remove('light','dark');
        document.documentElement.classList.add(v);
        document.documentElement.setAttribute('data-theme', v);
        """, mode)
    time.sleep(0.8)


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    if '/login' in drv.current_url:
        try:
            u = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
            u.clear()
            u.send_keys('接线测试_admin')
            p = drv.find_element(By.ID, 'password')
            p.clear()
            p.send_keys('JieXianTest@2026')
            js_click(drv, drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]"))
            WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
        except Exception as exc:
            raise RuntimeError('login failed: %s' % exc)
    time.sleep(1)


def goto_tab(drv, tab):
    drv.get(BASE + '/devices/' + tab)
    WebDriverWait(drv, 45).until(lambda d: '设备管理' in body_text(d) and '在线' in body_text(d))
    WebDriverWait(drv, 45).until(
        lambda d: '共 ' in body_text(d) or '暂无' in body_text(d)
    )
    time.sleep(1.5)


def api(drv, path, method='GET', body=None):
    return drv.execute_async_script(
        """
        const path = arguments[0], method = arguments[1], body = arguments[2];
        const done = arguments[arguments.length-1];
        const token = localStorage.getItem('iatp:auth:token:v1');
        const opt = {method: method, headers: token ? {Authorization: 'Bearer ' + token} : {}};
        if (body !== null && body !== undefined) {
          opt.headers['Content-Type'] = 'application/json';
          opt.body = JSON.stringify(body);
        }
        fetch('/api/v1' + path, opt)
          .then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """, path, method, body)


def api_json(drv, path, method='GET', body=None):
    r = api(drv, path, method, body)
    try:
        return r['status'], json.loads(r['body'])
    except Exception:
        return r['status'], None


def open_more_menu(drv):
    btn = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label='更多操作']")))
    js_click(drv, btn)
    time.sleep(0.6)


def menu_item(drv, text):
    return WebDriverWait(drv, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '%s')]" % text)))


def click_menu_item(drv, text):
    item = menu_item(drv, text)
    js_click(drv, item)
    time.sleep(0.8)


def dialog_text(drv):
    try:
        return drv.find_element(By.CSS_SELECTOR, '[role="dialog"]').text
    except Exception:
        return ''


def close_dialog(drv):
    for label in ('关闭', '取消'):
        try:
            btn = drv.find_element(
                By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='%s']" % label)
            js_click(drv, btn)
            time.sleep(0.8)
            return True
        except Exception:
            continue
    # 兜底：右上角关闭按钮
    try:
        js_click(drv, drv.find_element(By.CSS_SELECTOR, '[role="dialog"] [data-slot="dialog-close"]'))
        time.sleep(0.8)
        return True
    except Exception:
        return False


def upload_file(drv, path):
    inp = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[role="dialog"] input[type="file"]')))
    inp.send_keys(path)
    time.sleep(0.8)


def start_import(drv):
    btn = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始导入']")))
    js_click(drv, btn)


def wait_import_done(drv, timeout=180):
    """等导入结束：结果区出现「成功导入」或错误提示出现。"""
    def done(d):
        t = dialog_text(d)
        return ('成功导入' in t) or ('导入失败' in t) or ('正在导入' not in t and t.strip() != '')
    WebDriverWait(drv, timeout).until(lambda d: '正在导入' not in dialog_text(d))
    time.sleep(1.2)


def fetch_log(drv, needle):
    try:
        log = drv.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []
    return [e for e in log if needle in (e.get('url') or '')]


def clear_fetch_log(drv):
    drv.execute_script('window.__fetchLog = []')


def perf_entries(drv, needle):
    """CDP performance log → [{method,url,status,headers}]（含 Content-Disposition）。"""
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:
        return out
    reqs = {}
    for entry in entries:
        try:
            msg = json.loads(entry.get('message') or '')
        except Exception:
            continue
        method = msg.get('method') or ''
        params = (msg.get('message') or {}).get('params') or {}
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            url = req.get('url') or ''
            if needle in url:
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'),
                    'url': url,
                    'status': None,
                    'headers': {},
                }
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            if rid in reqs:
                resp = params.get('response') or {}
                reqs[rid]['status'] = resp.get('status')
                reqs[rid]['headers'] = resp.get('headers') or {}
    return list(reqs.values())


def download_wait(drv, before, timeout=180):
    """等下载目录出现新文件（忽略 Chrome 的 downloads.htm 与未完成 .crdownload）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        now = set(os.listdir(DOWNLOADS))
        partial = [f for f in now if f.endswith('.crdownload')]
        new = [
            f for f in now - before
            if not f.endswith('.crdownload') and not f.endswith('.htm')
        ]
        if new and not partial:
            time.sleep(0.6)
            return sorted(new)
        time.sleep(1)
    return []


def write_files():
    """准备导入用测试文件（全部「接线测试_INT1624_」口径）。"""
    files = {}
    mixed = {
        'test_devices': [
            {
                'name': DEVICE_NAME, 'model': 'JX-Model', 'type': 'physical',
                'system': 'Android', 'system_version': '14', 'app_name': 'iatp',
                'app_version': '1.0', 'serial_number': DEVICE_SERIAL,
                'description': 'mixed-legal-update', 'status': 'offline',
            },
            {
                'name': PREFIX + '缺键行', 'model': 'JX-Model', 'type': 'physical',
                'system': 'Android', 'system_version': '14', 'app_name': 'iatp',
                'app_version': '1.0', 'description': 'mixed-missing-key',
            },
        ]
    }
    p = os.path.join(ART, 'mixed_update.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(mixed, f, ensure_ascii=False)
    files['mixed'] = p

    p = os.path.join(ART, 'bad.txt')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('not a supported file')
    files['txt'] = p

    p = os.path.join(ART, 'empty.json')
    open(p, 'w', encoding='utf-8').close()
    files['empty'] = p

    p = os.path.join(ART, 'empty_data.json')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('{"test_devices": []}')
    files['empty_data'] = p

    p = os.path.join(ART, 'invalid.json')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('{"test_devices": [this is not json')
    files['invalid'] = p
    return files


def cleanup(drv):
    """删除本 run 自建数据（名称前缀），并复核零残留。"""
    removed = {'test': 0, 'playback': 0, 'api': 0}
    status, payload = api_json(drv, '/test-devices?page=1&per_page=1000')
    for item in ((payload or {}).get('data') or {}).get('items') or []:
        if str(item.get('name', '')).startswith(PREFIX) or str(item.get('serial_number') or '').startswith('JX1624'):
            api_json(drv, '/test-devices/%s' % item['id'], 'DELETE')
            removed['test'] += 1
    status, payload = api_json(drv, '/playback-devices?page=1&per_page=1000')
    for item in ((payload or {}).get('data') or {}).get('items') or []:
        if str(item.get('name', '')).startswith(PREFIX) or str(item.get('device_unique_id') or '').startswith('JX1624'):
            api_json(drv, '/playback-devices/%s' % item['id'], 'DELETE')
            removed['playback'] += 1
    status, payload = api_json(drv, '/apis?page=1&per_page=1000')
    for item in ((payload or {}).get('data') or {}).get('items') or []:
        if str(item.get('name', '')).startswith(PREFIX):
            api_json(drv, '/apis/%s' % item['id'], 'DELETE')
            removed['api'] += 1
    time.sleep(2)
    left = []
    for path in ('/test-devices', '/playback-devices', '/apis'):
        status, payload = api_json(drv, path + '?page=1&per_page=1000')
        for item in ((payload or {}).get('data') or {}).get('items') or []:
            name = str(item.get('name', ''))
            if name.startswith(PREFIX):
                left.append('%s:%s' % (path, item.get('id')))
    print('cleanup removed', removed, 'left', left)
    return removed, left


# ---------------------------------------------------------------- fixtures

def psql(sql):
    import subprocess
    out = subprocess.run(
        ['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql', '-U',
         'intelligent_audio_test', '-d', 'intelligent_audio_test', '-tAc', sql],
        capture_output=True, text=True, encoding='utf-8')
    return (out.stdout or '').strip(), (out.stderr or '').strip()


def seed_fixtures():
    """SQL 夹具（写操作在 docker 栈上会卡 60s，夹具直落库只为被测 UI 提供既有记录）。"""
    psql("update devices set deleted=true where name like '%s%%' and deleted=false;" % PREFIX)
    psql("update apis set deleted=true where name like '%s%%' and deleted=false;" % PREFIX)
    psql(
        "insert into devices (name, model, type, system, system_version, app_name, app_version, "
        "description, location, max_audio_duration, needs_prompt_audio, connection_type, keywords, "
        "serial_number, ip, status, supported_algorithms, deleted) values "
        "('%s', 'JX-Model', 'physical', 'Android', '14', 'iatp', '1.0', 'seed', 'JX-Lab', 30, false, "
        "'usb', 'jx,keyword', '%s', '10.0.0.9', 'offline', '[]', false) returning id;"
        % (DEVICE_NAME, DEVICE_SERIAL))
    out, err = psql(
        "insert into apis (name, vendor, description, status, meta, max_process, max_timeout, "
        "max_audio_duration, health_score, deleted, default_max_process, default_max_timeout, "
        "default_max_audio_duration, api_endpoints) values "
        "('%s', 'jx-vendor', 'seed', 'online', '{}', 5, 30, 60, 0, false, 5, 30, 60, '[]') returning id;"
        % API_NAME)
    print('seed fixtures:', out, err)
    return out


def wait_no_importing(drv, timeout=240):
    time.sleep(1.0)
    WebDriverWait(drv, timeout).until(lambda d: '正在导入' not in dialog_text(d))
    time.sleep(0.8)


def do_import(drv, path, timeout=240):
    """选文件 → 开始导入 → 等结束；返回（弹窗文本, /import fetch 记录）。"""
    clear_fetch_log(drv)
    upload_file(drv, path)
    start_import(drv)
    wait_no_importing(drv, timeout)
    entries = fetch_log(drv, '/import')
    return dialog_text(drv), entries[-1] if entries else {}


def choose_range(drv, label):
    radio = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[@role='dialog']//label[contains(normalize-space(.), '%s')]/input[@type='radio']"
             % label)))
    js_click(drv, radio)
    time.sleep(0.4)


def choose_format(drv, label):
    trigger = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, '[role="dialog"] [data-slot="select-trigger"]')))
    js_click(drv, trigger)
    time.sleep(0.7)
    item = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[@role='option'][contains(normalize-space(.), '%s')]" % label)))
    js_click(drv, item)
    time.sleep(0.5)


def do_export(drv, timeout=180):
    before = set(os.listdir(DOWNLOADS))
    clear_fetch_log(drv)
    btn = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='导出']")))
    js_click(drv, btn)
    files = download_wait(drv, before, timeout)
    time.sleep(1.0)
    return files, fetch_log(drv, '/export')


def read_download(name):
    path = os.path.join(DOWNLOADS, name)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def search_device(drv, keyword):
    box = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder^='搜索']")))
    js_click(drv, box)
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    time.sleep(0.3)
    box.send_keys(keyword)
    time.sleep(1.5)


def enable_batch_mode(drv):
    try:
        sw = drv.find_element(By.CSS_SELECTOR, "[data-slot='switch'][aria-label='批量操作模式']")
        if sw.get_attribute('aria-checked') != 'true' and sw.get_attribute('data-checked') is None:
            js_click(drv, sw)
            time.sleep(0.8)
    except Exception:
        # 移动端下拉入口兜底
        try:
            open_more_menu(drv)
            item = menu_item(drv, '批量操作模式')
            js_click(drv, item)
            time.sleep(0.8)
        except Exception as exc:
            print('enable batch mode failed:', exc)


def select_row(drv, aria_name):
    cb = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[role='checkbox'][aria-label='%s']" % aria_name)))
    js_click(drv, cb)
    time.sleep(0.5)


def badge_text(drv):
    try:
        el = drv.find_element(By.XPATH, "//*[contains(text(), '在线') and contains(., '共')]")
        return el.text.strip()
    except Exception:
        return ''


def render_evidence(name, title, lines):
    from PIL import Image, ImageDraw, ImageFont
    text = '\n'.join([title, '=' * 60] + lines + ['verified at ' + time.strftime('%Y-%m-%d %H:%M:%S')])
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 18)
    except Exception:
        font = ImageFont.load_default()
    for font_path in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf'):
        try:
            font = ImageFont.truetype(font_path, 18)
            break
        except Exception:
            continue
    wrapped = []
    for line in text.split('\n'):
        while len(line) > 62:
            wrapped.append(line[:62])
            line = line[62:]
        wrapped.append(line)
    W, H = 1180, max(140, 30 * len(wrapped) + 40)
    img = Image.new('RGB', (W, H), (246, 246, 246))
    draw = ImageDraw.Draw(img)
    y = 14
    for ln in wrapped:
        draw.text((16, y), ln, fill=(20, 20, 20), font=font)
        y += 28
    path = os.path.join(ART, name + '.png')
    img.save(path)
    print('EVIDENCE', path)
    return path


PERM_PATCH = r"""
(function(){
  const orig = window.fetch;
  window.fetch = function(input, init){
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    if (url.indexOf('/api/v1/auth/me') !== -1) {
      const perms = JSON.parse(localStorage.getItem('iatp:rbac_probe_perms') || '[]');
      const payload = {success: true, code: 0, data: {
        id: 999, username: 'rbac_probe', permissions: perms}};
      return Promise.resolve(new Response(JSON.stringify(payload), {
        status: 200, headers: {'Content-Type': 'application/json'}}));
    }
    return orig.apply(this, arguments);
  };
})();
"""


def check_permission_visibility(drv):
    """§8 权限显隐：无 create 码导入入口不渲染；无 read 码导出入口不渲染。

    AUTH_MODE=off 的 dev_user 恒为 ['*']，故用页内拦截 /auth/me 注入最小权限集。
    """
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PERM_PATCH})

    def menu_state(perms):
        drv.execute_script(
            "localStorage.setItem('iatp:rbac_probe_perms', JSON.stringify(arguments[0]))", perms)
        drv.get(BASE + '/devices/test')
        WebDriverWait(drv, 40).until(lambda d: '设备管理' in body_text(d))
        time.sleep(1.5)
        open_more_menu(drv)
        texts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']")]
        try:
            js_click(drv, drv.find_element(By.TAG_NAME, 'body'))
        except Exception:
            pass
        return texts

    read_only = menu_state(['device:read'])
    check('无 create 码：导入入口不渲染', not any('导入设备' in t for t in read_only), str(read_only))
    check('有 read 码：导出入口渲染', any('导出设备' in t for t in read_only), str(read_only))

    # 无 read 码：页签路由守卫直接拦到 /403（页面不渲染 → 两个入口都不会出现）
    drv.execute_script(
        "localStorage.setItem('iatp:rbac_probe_perms', JSON.stringify(['device:create']))")
    drv.get(BASE + '/devices/test')
    WebDriverWait(drv, 40).until(
        lambda d: '/403' in d.current_url or '403' in body_text(d))
    check('无 read 码：页签被路由守卫拦截（/403），导出入口不渲染',
          '/403' in drv.current_url or '403' in body_text(d), drv.current_url)

    drv.execute_script("localStorage.setItem('iatp:rbac_probe_perms', JSON.stringify(['*']))")


def header_probe(drv, url_path):
    """页内 fetch 同一导出 URL：状态码 + Content-Disposition / Content-Type（Network 证据）。"""
    return drv.execute_async_script(
        """
        const p = arguments[0];
        const done = arguments[arguments.length-1];
        const token = localStorage.getItem('iatp:auth:token:v1');
        fetch(p, {headers: token ? {Authorization: 'Bearer ' + token} : {}})
          .then(async r => {
            let size = -1;
            try { size = (await r.blob()).size; } catch (e) {}
            done({status: r.status,
                  contentDisposition: r.headers.get('content-disposition'),
                  contentType: r.headers.get('content-type'),
                  size: size});
          })
          .catch(e => done({error: String(e)}));
        """, url_path)

def main():
    files = write_files()
    for stale in os.listdir(DOWNLOADS):
        try:
            os.remove(os.path.join(DOWNLOADS, stale))
        except Exception:
            pass
    seed_fixtures()

    drv = driver()
    export_perf = []
    import_entry = {}
    try:
        drv.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': DOWNLOADS})
        login(drv)

        # ============ 1. 页签 + 更多操作入口 ============
        goto_tab(drv, 'test')
        shot(drv, 'devices_test_light')
        try:
            WebDriverWait(drv, 20).until(lambda d: DEVICE_NAME in d.execute_script('return document.body.textContent || ""'))
        except Exception:
            pass
        check('设备管理页渲染（测试设备页签）',
              '设备管理' in body_text(drv) and DEVICE_NAME in body_text(drv))

        open_more_menu(drv)
        imp_item = menu_item(drv, '导入设备')
        exp_item = menu_item(drv, '导出设备')
        check('更多操作：导入设备入口可见且未禁用',
              imp_item.get_attribute('aria-disabled') != 'true'
              and imp_item.get_attribute('data-disabled') is None)
        check('更多操作：导出设备入口可见且未禁用',
              exp_item.get_attribute('aria-disabled') != 'true'
              and exp_item.get_attribute('data-disabled') is None)
        shot(drv, 'devices_more_menu_light')

        # ============ 2. 导入弹窗 + 选择文件（点击） ============
        js_click(drv, imp_item)
        time.sleep(0.8)
        text = dialog_text(drv)
        check('导入弹窗打开（标题/格式提示/初始禁用）',
              '导入测试设备' in text and '支持格式：JSON / CSV / Excel' in text, text[:80].replace('\n', '|'))
        start_btn = drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始导入']")
        check('未选文件时「开始导入」禁用', start_btn.get_attribute('disabled') is not None)
        shot(drv, 'import_dialog_light')

        # 拖拽选文件一次（合成 dataTransfer drop）
        drv.execute_script(
            """
            const input = document.querySelector('[role="dialog"] input[type="file"]');
            const zone = input.parentElement;
            const dt = new DataTransfer();
            dt.items.add(new File(['{}'], 'drag.json', {type: 'application/json'}));
            zone.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
            zone.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
            """)
        time.sleep(0.8)
        check('拖拽选文件回显文件名', 'drag.json' in dialog_text(drv))
        shot(drv, 'import_drag_select_light')

        # ============ 3. 部分成功导入（合法行更新 + 缺键行跳过） ============
        text, import_entry = do_import(drv, files['mixed'])
        got = import_entry.get('respBody') or ''
        try:
            api_payload = json.loads(got)
        except Exception:
            api_payload = {}
        api_msg = (api_payload or {}).get('message', '')
        api_data = (api_payload or {}).get('data') or {}
        check('导入响应 200 且计数 = 更新1/跳过1',
              import_entry.get('status') == 200
              and api_data.get('updated_count') == 1
              and api_data.get('skipped_count') == 1
              and api_data.get('imported_count') == 0, got[:200])
        check('弹窗结果计数与接口 JSON 一致', api_msg and api_msg in dialog_text(drv), api_msg)
        check('errors 含行号且可读', any('第2行' in e for e in (api_data.get('errors') or [])),
              str(api_data.get('errors')))
        check('结果区注明「设备状态以本环境为准」', '设备状态以本环境为准' in dialog_text(drv))
        shot(drv, 'import_result_light')

        # ============ 4. 关闭重开无残留 ============
        close_dialog(drv)
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导入设备'))
        time.sleep(0.8)
        text2 = dialog_text(drv)
        check('关闭再开无残留（无文件名/无结果）',
              'mixed_update.json' not in text2 and '成功导入' not in text2 and '设备状态以本环境为准' not in text2)
        start_btn2 = drv.find_element(
            By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始导入']")
        check('重开后「开始导入」回到禁用', start_btn2.get_attribute('disabled') is not None)

        # ============ 5. 异常：.txt / 空文件 / 非法 JSON ============
        err_cases = [
            ('txt', '仅支持'),
            ('empty', '文件解析失败'),
            ('empty_data', '导入数据为空'),
            ('invalid', '文件解析失败'),
        ]
        for key, needle in err_cases:
            text, entry = do_import(drv, files[key], timeout=180)
            status = entry.get('status')
            shown = dialog_text(drv)
            check('异常文件 %s：后端 %s + 弹窗错误提示（%s）' % (key, status, needle),
                  status == 400 and needle in shown, shown[:120].replace('\n', '|'))
        shot(drv, 'import_error_light')
        close_dialog(drv)

        # ============ 6. 导出弹窗（默认 JSON）+ 全部范围下载 ============
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导出设备'))
        time.sleep(0.8)
        exp_text = dialog_text(drv)
        check('导出弹窗打开（格式/范围选项齐全）',
              '导出测试设备' in exp_text and '全部' in exp_text
              and '当前页选中' in exp_text and '当前筛选结果' in exp_text)
        shot(drv, 'export_dialog_light')

        cleared = drv.execute_script('window.__perfmark = Date.now(); return true')
        files_all, log_all = do_export(drv)
        export_perf.extend(perf_entries(drv, '/export'))
        check('导出（全部/JSON）下载成功', len(files_all) == 1, str(files_all))
        if files_all:
            name = files_all[0]
            check('下载文件名 = test_devices_时间戳.json',
                  name.startswith('test_devices_') and name.endswith('.json'), name)
            data = read_download(name)
            api_all = json.loads(api(drv, '/test-devices/export?format=json')['body'])
            check('导出全部条数与接口一致',
                  data.get('total_count') == api_all.get('total_count'),
                  '%s vs %s' % (data.get('total_count'), api_all.get('total_count')))
        check('导出请求命中 GET /test-devices/export?format=json',
              any('/test-devices/export' in (e.get('url') or '') and 'format=json' in (e.get('url') or '')
                  for e in log_all), str([e.get('url') for e in log_all]))

        # ============ 7. 导出格式 Excel ============
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导出设备'))
        time.sleep(0.8)
        choose_format(drv, 'Excel')
        files_xlsx, log_xlsx = do_export(drv)
        export_perf.extend(perf_entries(drv, '/export'))
        xlsx_files = [f for f in files_xlsx if f.endswith('.xlsx')]
        check('导出（Excel）下载成功且扩展名 .xlsx',
              len(xlsx_files) == 1, str(files_xlsx))
        if xlsx_files:
            with open(os.path.join(DOWNLOADS, xlsx_files[0]), 'rb') as f:
                magic = f.read(2)
            check('Excel 文件为真实 XLSX（PK 头）', magic == b'PK', repr(magic))
        check('Excel 请求 format=excel',
              any('format=excel' in (e.get('url') or '') for e in log_xlsx),
              str([e.get('url') for e in log_xlsx]))

        # ============ 8. 导出范围：当前页选中 + 字段白名单 ============
        enable_batch_mode(drv)
        search_device(drv, DEVICE_SERIAL)
        select_row(drv, '选择设备 %s' % DEVICE_NAME)
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导出设备'))
        time.sleep(0.8)
        choose_range(drv, '当前页选中')
        files_sel, log_sel = do_export(drv)
        export_perf.extend(perf_entries(drv, '/export'))
        check('导出范围=当前页选中 下载成功', len(files_sel) == 1, str(files_sel))
        sel_url = [e.get('url') for e in log_sel]
        check('选中范围请求带 ids', any('ids=' in (u or '') for u in sel_url), str(sel_url))
        if files_sel:
            sel_data = read_download(files_sel[0])
            rows = sel_data.get('test_devices') or []
            check('选中范围文件只含 1 条', len(rows) == 1, 'rows=%s' % len(rows))
            row = rows[0] if rows else {}
            check('导出字段 = 白名单（逐字段）', sorted(row.keys()) == sorted(TEST_DEVICE_FIELDS),
                  'missing=%s extra=%s' % (
                      sorted(set(TEST_DEVICE_FIELDS) - set(row.keys())),
                      sorted(set(row.keys()) - set(TEST_DEVICE_FIELDS))))
            check('导出不含 id / 创建时间 / 告警字段',
                  'id' not in row and 'created_at' not in row and 'updated_at' not in row)
            check('导出字段值与库内记录一致（name/serial/status）',
                  row.get('name') == DEVICE_NAME and row.get('serial_number') == DEVICE_SERIAL
                  and row.get('status') == 'offline', str({k: row.get(k) for k in ('name', 'serial_number', 'status')}))
            _EVIDENCE['selected_row'] = row

        # ============ 9. 导出范围：当前筛选结果 ============
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导出设备'))
        time.sleep(0.8)
        choose_range(drv, '当前筛选结果')
        files_filt, log_filt = do_export(drv)
        export_perf.extend(perf_entries(drv, '/export'))
        check('导出范围=当前筛选结果 下载成功', len(files_filt) == 1, str(files_filt))
        if files_filt:
            filt_data = read_download(files_filt[0])
            check('筛选范围文件只含筛选命中 1 条',
                  (filt_data.get('total_count') or 0) == 1,
                  'total=%s' % filt_data.get('total_count'))

        # ============ 10. 测试设备导入闭环：命中匹配键 → 更新 ============
        loop_file = os.path.join(ART, 'loop_update.json')
        changed = dict(_EVIDENCE.get('selected_row') or {})
        changed['description'] = 'loop-updated'
        with open(loop_file, 'w', encoding='utf-8') as f:
            json.dump({'test_devices': [changed]}, f, ensure_ascii=False)
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导入设备'))
        time.sleep(0.8)
        text, entry = do_import(drv, loop_file)
        check('测试设备再导入命中匹配键：更新 1、不新建',
              '更新 1 个' in dialog_text(drv) and '导入 0 个' in dialog_text(drv),
              dialog_text(drv).replace('\n', '|')[:160])
        time.sleep(2)
        status, payload = api_json(drv, '/test-devices?page=1&per_page=1000')
        rows = ((payload or {}).get('data') or {}).get('items') or []
        matched = [r for r in rows if r.get('serial_number') == DEVICE_SERIAL]
        check('回读：description 已更新且仅 1 条同序列号',
              len(matched) == 1 and matched[0].get('description') == 'loop-updated',
              str([(r.get('id'), r.get('description')) for r in matched]))
        close_dialog(drv)

        # ============ 10b. 测试设备导入闭环：删除后导入新建 ============
        target_id = matched[0].get('id') if matched else None
        if target_id and files_sel:
            st_del, _ = api_json(drv, '/test-devices/%s' % target_id, 'DELETE')
            check('删除测试设备夹具', st_del in (200, 204), str(st_del))
            time.sleep(2)
            open_more_menu(drv)
            js_click(drv, menu_item(drv, '导入设备'))
            time.sleep(0.8)
            do_import(drv, os.path.join(DOWNLOADS, files_sel[0]))
            check('测试设备导入新建（成功导入 1 个）', '成功导入 1 个' in dialog_text(drv),
                  dialog_text(drv).replace('\n', '|')[:160])
            close_dialog(drv)
            time.sleep(2)
            status, payload = api_json(drv, '/test-devices?page=1&per_page=1000')
            rows = ((payload or {}).get('data') or {}).get('items') or []
            matched2 = [r for r in rows if r.get('serial_number') == DEVICE_SERIAL]
            check('测试设备导入后回读单条且字段一致',
                  len(matched2) == 1 and matched2[0].get('name') == DEVICE_NAME,
                  str([(r.get('id'), r.get('name')) for r in matched2]))
            open_more_menu(drv)
            js_click(drv, menu_item(drv, '导入设备'))
            time.sleep(0.8)
            do_import(drv, os.path.join(DOWNLOADS, files_sel[0]))
            check('测试设备再导入命中匹配键：更新 1 个', '更新 1 个' in dialog_text(drv),
                  dialog_text(drv).replace('\n', '|')[:160])
            close_dialog(drv)
            time.sleep(2)
            status, payload = api_json(drv, '/test-devices?page=1&per_page=1000')
            rows = ((payload or {}).get('data') or {}).get('items') or []
            matched3 = [r for r in rows if r.get('serial_number') == DEVICE_SERIAL]
            check('测试设备再导入后仍只有 1 条（无重复脏数据）', len(matched3) == 1,
                  'count=%s' % len(matched3))
        else:
            check('测试设备导入闭环前置（夹具 + 导出文件）', False,
                  'target=%s files=%s' % (target_id, files_sel))

        # ============ 11. 播放设备导入闭环：新建 → 再导入更新 ============
        st, created = api_json(drv, '/playback-devices', 'POST', {
            'name': PLAYBACK_NAME, 'model': 'JX-SPK', 'device_type': 'dry',
            'sample_rate': 48000, 'device_unique_id': PLAYBACK_UID, 'status': 'offline',
        })
        check('播放设备夹具创建（API 201）', st in (200, 201), str(created))

        goto_tab(drv, 'playback')
        badge_before = badge_text(drv)
        enable_batch_mode(drv)
        # 播放页签关键字只匹配 name/model（不含 device_unique_id），按名称筛选
        search_device(drv, PLAYBACK_NAME)
        select_row(drv, '选择播放设备 %s' % PLAYBACK_NAME)
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导出设备'))
        time.sleep(0.8)
        check('播放页签导出弹窗标题随页签',
              '导出播放设备' in dialog_text(drv) or '播放设备' in dialog_text(drv))
        choose_range(drv, '当前页选中')
        files_pb, log_pb = do_export(drv)
        export_perf.extend(perf_entries(drv, '/playback-devices/export'))
        check('播放设备选中导出 1 条', len(files_pb) == 1, str(files_pb))
        pb_export_path = os.path.join(DOWNLOADS, files_pb[0]) if files_pb else ''

        # 删除夹具 → 用导出文件导入（新建）
        st_del, _ = api_json(drv, '/playback-devices/%s' % ((created or {}).get('data') or {}).get('id'), 'DELETE')
        check('删除播放设备夹具', st_del in (200, 204), str(st_del))
        time.sleep(1)
        drv.refresh()
        WebDriverWait(drv, 30).until(lambda d: '共 ' in body_text(d))
        time.sleep(2)
        badge_before = badge_text(drv)
        print('badge before import:', badge_before)
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导入设备'))
        time.sleep(0.8)
        check('播放页签导入弹窗标题随页签', '导入播放设备' in dialog_text(drv), dialog_text(drv)[:60])
        text, entry = do_import(drv, pb_export_path)
        check('导入新建成功（成功导入 1 个）', '成功导入 1 个' in dialog_text(drv),
              dialog_text(drv).replace('\n', '|')[:160])
        close_dialog(drv)
        time.sleep(2)
        status, payload = api_json(drv, '/playback-devices?page=1&per_page=1000')
        rows = ((payload or {}).get('data') or {}).get('items') or []
        matched = [r for r in rows if r.get('device_unique_id') == PLAYBACK_UID]
        check('回读：播放设备已新建且字段一致',
              len(matched) == 1 and matched[0].get('name') == PLAYBACK_NAME
              and matched[0].get('sample_rate') == 48000,
              str([(r.get('id'), r.get('name'), r.get('sample_rate')) for r in matched]))
        # 再导入一次 → 更新、不产生第二条
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导入设备'))
        time.sleep(0.8)
        do_import(drv, pb_export_path)
        check('再导入命中匹配键：更新 1 个', '更新 1 个' in dialog_text(drv),
              dialog_text(drv).replace('\n', '|')[:160])
        close_dialog(drv)
        time.sleep(2)
        status, payload = api_json(drv, '/playback-devices?page=1&per_page=1000')
        rows = ((payload or {}).get('data') or {}).get('items') or []
        matched = [r for r in rows if r.get('device_unique_id') == PLAYBACK_UID]
        check('再导入后仍只有 1 条（无重复脏数据）', len(matched) == 1, 'count=%s' % len(matched))

        # 跨组件状态同步：列表 / 徽章 / 统计卡
        goto_tab(drv, 'playback')
        badge_after = badge_text(drv)
        import re

        def badge_total(text):
            m = re.search(r'共\s*(\d+)', text or '')
            return int(m.group(1)) if m else None

        before_total, after_total = badge_total(badge_before), badge_total(badge_after)
        check('导入后顶部徽章总数 +1',
              before_total is not None and after_total == before_total + 1,
              '%s → %s' % (badge_before, badge_after))
        check('导入后列表包含新记录', PLAYBACK_NAME in body_text(drv))
        shot(drv, 'playback_after_import_light')

        # ============ 12. 测试 API 导入闭环：命中匹配键 → 更新 ============
        goto_tab(drv, 'api')
        enable_batch_mode(drv)
        search_device(drv, API_NAME)
        time.sleep(1)
        select_row(drv, '选择 API %s' % API_NAME)
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导出设备'))
        time.sleep(0.8)
        check('API 页签导出弹窗标题随页签', '导出测试 API' in dialog_text(drv) or '测试 API' in dialog_text(drv))
        choose_range(drv, '当前页选中')
        files_api, log_api = do_export(drv)
        export_perf.extend(perf_entries(drv, '/apis/export'))
        check('API 选中导出 1 条', len(files_api) == 1, str(files_api))
        if files_api:
            api_export = read_download(files_api[0])
            api_rows = api_export.get('apis') or []
            check('API 导出字段 = 白名单',
                  bool(api_rows) and sorted(api_rows[0].keys()) == sorted([
                      'name', 'vendor', 'description', 'meta', 'algorithm_type',
                      'default_max_process', 'default_max_timeout', 'default_max_audio_duration',
                      'status', 'endpoints', 'output_types', 'device_type', 'adapter_class',
                      'audio_config']),
                  str(sorted((api_rows[0] if api_rows else {}).keys())))
            api_rows[0]['description'] = 'api-loop-updated'
            api_loop_path = os.path.join(ART, 'api_loop_update.json')
            with open(api_loop_path, 'w', encoding='utf-8') as f:
                json.dump({'apis': api_rows}, f, ensure_ascii=False)
            open_more_menu(drv)
            js_click(drv, menu_item(drv, '导入设备'))
            time.sleep(0.8)
            do_import(drv, api_loop_path)
            check('API 再导入命中匹配键：更新 1 个', '更新 1 个' in dialog_text(drv),
                  dialog_text(drv).replace('\n', '|')[:160])
            close_dialog(drv)
            time.sleep(2)
            status, payload = api_json(drv, '/apis?page=1&per_page=1000')
            api_items = ((payload or {}).get('data') or {}).get('items') or []
            matched = [r for r in api_items if r.get('name') == API_NAME]
            check('API 回读：description 已更新且仅 1 条',
                  len(matched) == 1 and matched[0].get('description') == 'api-loop-updated',
                  str([(r.get('id'), r.get('description')) for r in matched]))

        # ============ 13. 深色截图 ============
        goto_tab(drv, 'test')
        apply_theme(drv, 'dark')
        dark_ok = drv.execute_script(
            "return document.documentElement.classList.contains('dark')")
        check('深色主题生效（html.dark）', bool(dark_ok))
        shot(drv, 'devices_test_dark')
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导入设备'))
        time.sleep(0.8)
        shot(drv, 'import_dialog_dark')
        close_dialog(drv)
        open_more_menu(drv)
        js_click(drv, menu_item(drv, '导出设备'))
        time.sleep(0.8)
        shot(drv, 'export_dialog_dark')
        close_dialog(drv)
        apply_theme(drv, 'light')

        # ============ 14. Network 证据图 ============
        exp_lines = []
        seen = set()
        for group in (log_all, log_xlsx, log_sel, log_filt, log_pb, log_api):
            for item in group:
                key = (item.get('method'), item.get('url'))
                if key in seen:
                    continue
                seen.add(key)
                exp_lines.append('%s %s' % (item.get('method'), item.get('url')))
                exp_lines.append('  status: %s' % item.get('status'))
        for variant in (
            '/api/v1/test-devices/export?format=json',
            '/api/v1/test-devices/export?format=excel',
            '/api/v1/playback-devices/export?format=json',
            '/api/v1/apis/export?format=json',
        ):
            probe = header_probe(drv, variant)
            exp_lines.append('[Network] GET %s' % variant)
            exp_lines.append('  status: %s' % probe.get('status'))
            exp_lines.append('  Content-Type: %s' % probe.get('contentType'))
            exp_lines.append('  Content-Disposition: %s' % probe.get('contentDisposition'))
            exp_lines.append('  body bytes: %s' % probe.get('size'))
        render_evidence('network_export', 'INT-1624 导出 Network（docker 15000 真实库栈）', exp_lines)

        imp_lines = []
        if import_entry:
            imp_lines.append('%s %s' % (import_entry.get('method'), import_entry.get('url')))
            imp_lines.append('  status: %s' % import_entry.get('status'))
            imp_lines.append('  multipart field file = %s' % import_entry.get('formFile'))
            imp_lines.append('  response: %s' % (import_entry.get('respBody') or '')[:500])
        render_evidence('network_import', 'INT-1624 导入 Network（docker 15000 真实库栈）', imp_lines)

        # ============ 15. 权限显隐（§8） ============
        check_permission_visibility(drv)

    finally:
        try:
            removed, left = cleanup(drv)
            check('数据清理：零残留', not left, str(left))
        except Exception as exc:
            print('cleanup error', exc)
            _FAILURES.append('cleanup')
        try:
            drv.quit()
        except Exception:
            pass

    print('\n==== SUMMARY ====')
    print('failures:', len(_FAILURES))
    for item in _FAILURES:
        print('  FAIL', item)
    return 1 if _FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())


