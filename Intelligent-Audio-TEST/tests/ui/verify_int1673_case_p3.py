# -*- coding: utf-8 -*-
"""INT-1673 用例域 P3 三处修复浏览器实测（dev server 5373 → docker 网关 15000）。

环境铁律：后端 docker 网关 http://localhost:15000（database=intelligent_audio_test）；
前端本 worktree `pnpm dev --port 5373 -c rsbuild.docker15000.config.ts`（代理 /api 到 15000）。

验证点：
P3-1 试听播放器错误条：关闭钮固定右上（absolute、单行高度），点错误条正文不关闭、点×才关闭；
P3-2 模板下载：点「模板下载」发真实 GET /testcases/template/download 并落 xlsx 文件（不再演示 toast）；
P3-3 其余四个批量弹窗「指定轮次」按选中用例真实轮次数（本 run 自建 1 轮 + 3 轮用例 → 渲染 1~3 轮）。

写数据纪律：只写本 run 自建的「接线测试_INT1673」分组与用例，结束前删掉；真实记录只读。
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5373')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1673')
DL = os.path.join(ART, 'downloads')
THEME_KEY = 'iatp:theme:v1:mode'
TS = int(time.time())
GROUP = '接线测试_INT1673_%d' % TS

REPORT = {'env': [], 'steps': {}, 'screenshots': [], 'fail': []}

PATCH = r"""
window.__fetchLog = [];
window.__int1673ForcePreview = false;
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url: url, method: method };
  try {
    if (window.__int1673ForcePreview && method === 'POST' && /\/testcases\/\d+\/preview/.test(url)) {
      const fake = { success: true, code: 0, data: {
        test_case_id: 1, preview_task_id: null, status: 'frontend_preview_ready',
        message: 'INT-1673 注入：错误态验证', duration: 12, playback_mode: 'frontend',
        audio_id: 1,
        audio_stream_url: '/api/v1/audios/download?path=__int1673_missing__.wav',
        audio_stream_urls: ['/api/v1/audios/download?path=__int1673_missing__.wav'],
      } };
      const res = new Response(JSON.stringify(fake), { status: 200, headers: { 'Content-Type': 'application/json' } });
      entry.status = 200;
      entry.injected = true;
      window.__fetchLog.push(entry);
      return res;
    }
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""


def log(msg):
    print(msg, flush=True)


def fail(name, detail):
    REPORT['fail'].append({'name': name, 'detail': detail})
    log('FAIL %s: %s' % (name, detail))


def check(name, ok, detail=''):
    if ok:
        log('OK   %s' % name)
    else:
        fail(name, detail)
    return ok


def api(method, path, payload=None, params=None):
    url = API + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        return e.code, {'raw': body[:400]}


def env_check(tag):
    health = json.loads(urllib.request.urlopen(API + '/health', timeout=15).read().decode())
    REPORT['env'].append({'tag': tag, 'health': health})
    log('ENV[%s]: database=%s' % (tag, health.get('database')))
    assert health.get('database') == 'intelligent_audio_test', '环境串库：%s' % health
    return health


def driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-features=DownloadBubble')
    options.add_argument('--autoplay-policy=no-user-gesture-required')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    options.add_experimental_option('prefs', {
        'download.default_directory': os.path.abspath(DL),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
    })
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == chrome_major:
                        drv_path = exe
                except Exception:
                    pass
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(120)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return drv


def body(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait(drv, cond, timeout=60, label=''):
    return WebDriverWait(drv, timeout).until(lambda d: cond(d))


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def xp(drv, xpath, root=None):
    return (root or drv).find_elements(By.XPATH, xpath)


def visible_dialog(drv, title_contains=None):
    for d in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
        if not d.is_displayed():
            continue
        if title_contains is None or title_contains in (d.text or ''):
            return d
    return None


def click_text(drv, text):
    """点精确文案元素（菜单项/按钮；base-ui 菜单项 role=menuitem）。"""
    for el in drv.find_elements(
            By.XPATH,
            "//button[normalize-space(.)='%s'] | //*[@role='menuitem'][normalize-space(.)='%s'] | //*[normalize-space(.)='%s']"
            % (text, text, text)):
        try:
            if el.is_displayed():
                js_click(drv, el)
                return el
        except Exception:
            continue
    raise AssertionError('找不到可点元素：%s' % text)


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    size = os.path.getsize(path)
    REPORT['screenshots'].append({'name': name, 'size': size})
    log('SHOT %s size=%d' % (name, size))
    assert size > 10_000, '截图过小 %s' % name
    return path


def fetch_log(drv):
    return drv.execute_script('return window.__fetchLog || []') or []


def set_theme(drv, theme):
    drv.get(BASE + '/')
    time.sleep(1.0)
    drv.execute_script("localStorage.setItem(%r, %r)" % (THEME_KEY, theme))


def goto_testcases(drv, theme='light'):
    set_theme(drv, theme)
    drv.get(BASE + '/testcases')
    wait(drv, lambda d: len([b for b in xp(d, "//*[contains(@aria-label,'批量修改')]") if b.is_displayed()]) > 0,
         240, 'group list')
    time.sleep(1.5)
    if theme == 'dark':
        wait(drv, lambda d: 'dark' in d.execute_script('return document.documentElement.className'), 20, 'dark')


def search_case(drv, keyword):
    wait(drv, lambda d: len(xp(d, "//input[@aria-label='搜索用例']")) > 0, 60, 'search input')
    inp = drv.find_element(By.XPATH, "//input[@aria-label='搜索用例']")
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(keyword)
    inp.send_keys(Keys.ENTER)
    time.sleep(4.0)


def ensure_group_loaded(drv, group_name, max_more=10):
    """分组列表按用例数降序分页：点「加载更多」直到目标分组出现（搜索不作用于分组列表）。"""
    label = '%s 批量修改' % group_name
    for _ in range(max_more):
        btns = [b for b in xp(drv, "//button[@aria-label='%s']" % label) if b.is_displayed()]
        if btns:
            return btns[0]
        more = [b for b in xp(drv, "//button[contains(., '加载更多')]") if b.is_displayed()]
        if not more:
            break
        js_click(drv, more[0])
        time.sleep(3.5)
    raise AssertionError('分组未出现：%s' % group_name)


def expand_group(drv, group_btn, timeout=180):
    header = drv.execute_script(
        "let n=arguments[0];for(let i=0;i<8&&n.parentElement;i++){n=n.parentElement;"
        "if(String(n.className||'').includes('cursor-pointer'))return n;}return null;", group_btn)
    if header is not None:
        js_click(drv, header)
    time.sleep(1.0)
    wait(drv, lambda d: len([b for b in xp(d, "//button[@aria-label='预览音频']") if b.is_displayed()]) > 0,
         timeout, 'case cards')


def expand_first_group(drv, timeout=180):
    """展开首个分组（分组默认折叠，用例卡片与行内钮展开后才渲染）。"""
    btns = [b for b in xp(drv, "//*[contains(@aria-label,'批量修改')]") if b.is_displayed()]
    assert btns, '没有可展开的分组'
    expand_group(drv, btns[0], timeout)


def find_case_preview_button(drv, case_name):
    """按用例名定位卡片内的「预览音频」钮（卡片文本包含用例名）。"""
    return drv.execute_script("""
      const name = arguments[0];
      const btns = Array.from(document.querySelectorAll('button[aria-label="预览音频"]'))
        .filter(b => b.offsetParent !== null && !b.disabled);
      for (const b of btns) {
        let n = b;
        for (let i = 0; i < 10 && n.parentElement; i++) {
          n = n.parentElement;
          if ((n.textContent || '').includes(name)) return b;
        }
      }
      return null;
    """, case_name)


# ---------------- fixtures ----------------

def create_fixtures():
    st, g = api('POST', '/api/v1/groups', {'name': GROUP, 'description': 'INT-1673 批量轮次走查临时分组'})
    gid = (g.get('data') or {}).get('id')
    ids = []
    for rounds in (1, 3):
        cfg_rounds = [
            {'round_number': i + 1, 'audios': [], 'evaluation': {}, 'noise': {}}
            for i in range(rounds)
        ]
        st, c = api('POST', '/api/v1/testcases', {
            'name': '接线测试_INT1673_%d轮_%d' % (rounds, TS),
            'group_id': gid,
            'tags': ['接线测试_INT1673'],
            'description': 'INT-1673 批量轮次走查临时用例（run 结束前删除）',
            'algorithm_type': 'voice_llm',
            'config': {'rounds': cfg_rounds},
            'algorithm_params': [],
        })
        cid = (c.get('data') or {}).get('id')
        if cid:
            ids.append((rounds, cid))
    return gid, ids


def cleanup_fixtures(gid, ids):
    for _, cid in ids:
        api('DELETE', '/api/v1/testcases/%s' % cid)
        api('DELETE', '/api/v1/testcases/%s/purge' % cid)
    if gid:
        st, _ = api('DELETE', '/api/v1/groups/%s' % gid, params={'cascade': True})
        log('cleanup group %s → %s' % (gid, st))


def pick_real_case_with_audio():
    st, data = api('GET', '/api/v1/testcases', params={'page': 1, 'per_page': 50})
    items = (data.get('data') or {}).get('items') or []
    for it in items:
        cfg = it.get('config') or {}
        rounds = cfg.get('rounds') or []
        if any((r.get('audios') or []) for r in rounds):
            return it.get('name'), it.get('group_name')
    return None, None


# ---------------- P3-2 模板下载 ----------------

def step_template(drv):
    log('== P3-2 模板下载 ==')
    goto_testcases(drv, 'light')
    for f in os.listdir(DL) if os.path.isdir(DL) else []:
        try:
            os.remove(os.path.join(DL, f))
        except Exception:
            pass
    drv.execute_script('window.__fetchLog = []')
    click_text(drv, '模板下载')
    time.sleep(0.6)
    wait(drv, lambda d: '模板已下载' in body(d), 60, 'toast 模板已下载')
    reqs = [r for r in fetch_log(drv) if '/testcases/template/download' in r['url']]
    REPORT['steps']['template_requests'] = reqs
    check('模板下载发真实 GET /testcases/template/download 200',
          bool(reqs) and reqs[-1].get('status') == 200 and reqs[-1]['method'] == 'GET', reqs)

    files = []
    deadline = time.time() + 40
    while time.time() < deadline:
        files = [f for f in os.listdir(DL) if f.lower().endswith('.xlsx') and not f.endswith('.crdownload')]
        if files:
            break
        time.sleep(1)
    path = os.path.join(DL, files[0]) if files else ''
    size = os.path.getsize(path) if files else 0
    REPORT['steps']['template_file'] = {'name': files[0] if files else None, 'size': size}
    check('浏览器落真实 xlsx 模板文件（非空）', bool(files) and size > 3000, REPORT['steps']['template_file'])
    check('不再出现「演示」字样', '演示' not in body(drv), '')
    shot(drv, 'p32_template_light.png')
    return True


# ---------------- P3-3 批量轮次 ----------------

def open_batch_dialog(drv, item_label, title):
    btns = [b for b in xp(drv, "//button[@aria-label='%s 批量修改']" % GROUP) if b.is_displayed()]
    assert btns, '未找到自建分组「批量修改」'
    js_click(drv, btns[0])
    time.sleep(0.8)
    click_text(drv, item_label)
    wait(drv, lambda d: visible_dialog(d, title) is not None, 40, title)
    time.sleep(0.6)
    return visible_dialog(drv, title)


def round_labels_in_specific(drv, dlg):
    return drv.execute_script(
        "return Array.from(arguments[0].querySelectorAll('label'))"
        ".map(function(l){return (l.textContent||'').trim();})"
        ".filter(function(t){return /^第\\d+轮$/.test(t);});", dlg)


def round_tabs_in_per_round(drv, dlg):
    return drv.execute_script(
        "return Array.from(arguments[0].querySelectorAll('button'))"
        ".map(function(b){return (b.textContent||'').trim();})"
        ".filter(function(t){return /^第\\d+轮$/.test(t);});", dlg)


def step_batch_rounds(drv, theme='light', items=None, suffix=''):
    log('== P3-3 批量弹窗轮次（%s） ==' % theme)
    goto_testcases(drv, theme)
    group_btn = ensure_group_loaded(drv, GROUP)
    # 展开分组（轮次数来自已加载用例：分组懒加载缓存 + 页面 items 合并派生）
    expand_group(drv, group_btn)
    time.sleep(1.0)

    results = {}
    pairs = items or (
        ('声压', '批量设置声压级'),
        ('播放设备', '批量设置播放设备'),
        ('用例专属参数', '批量设置用例专属参数'),
        ('噪声', '选择噪声音频'),
    )
    for item, title in pairs:
        dlg = open_batch_dialog(drv, item, title)
        # 指定轮次
        label = [l for l in xp(drv, ".//label[contains(., '指定轮次')]", dlg) if l.is_displayed()]
        js_click(drv, label[0])
        time.sleep(0.6)
        specific = round_labels_in_specific(drv, dlg)
        # 逐轮设置
        tabs = []
        per_round = [l for l in xp(drv, ".//label[contains(., '逐轮设置')]", dlg) if l.is_displayed()]
        if per_round:
            js_click(drv, per_round[0])
            time.sleep(0.6)
            tabs = round_tabs_in_per_round(drv, dlg)
        results[title] = {'specific': specific, 'per_round_tabs': tabs}
        shot(drv, 'p33_%s_%s.png' % (title, theme))
        cancel = [b for b in dlg.find_elements(By.XPATH, ".//button[contains(., '取消')]") if b.is_displayed()]
        js_click(drv, cancel[0])
        time.sleep(0.8)

    REPORT['steps']['batch_rounds_%s' % theme] = results
    expect = ['第1轮', '第2轮', '第3轮']
    for title, data in results.items():
        check('[%s] %s 指定轮次=真实三轮（1 轮+3 轮用例取最大）' % (theme, title),
              data['specific'] == expect, data['specific'])
        check('[%s] %s 无第 4 轮' % (theme, title),
              '第4轮' not in data['specific'], data['specific'])
        check('[%s] %s 逐轮 Tab 同口径' % (theme, title),
              data['per_round_tabs'] == expect, data['per_round_tabs'])
    return results

# ---------------- P3-1 错误条 ----------------

def step_error_alert(drv, theme='light'):
    log('== P3-1 试听错误条（%s） ==' % theme)
    name = REPORT['steps'].get('real_case')
    group_name = REPORT['steps'].get('real_case_group')
    goto_testcases(drv, theme)
    drv.execute_script('window.__int1673ForcePreview = true')
    btn_group = ensure_group_loaded(drv, group_name)
    expand_group(drv, btn_group)
    time.sleep(1.0)
    target = find_case_preview_button(drv, name)
    check('[%s] 在分组内定位到带音频用例「%s」的预览音频钮' % (theme, name), target is not None, name)
    if target is None:
        return
    js_click(drv, target)
    wait(drv, lambda d: visible_dialog(d, '音频试听配置') is not None, 40, '预览配置弹窗')
    dlg = visible_dialog(drv, '音频试听配置')
    start = [b for b in dlg.find_elements(By.XPATH, ".//button[contains(., '开始试听')]") if b.is_displayed()][0]
    js_click(drv, start)
    alert = wait(drv, lambda d: next((a for a in d.find_elements(By.CSS_SELECTOR, '[role="alert"]') if a.is_displayed()), None), 60, '错误条')
    time.sleep(0.8)

    metrics = drv.execute_script("""
      const a = Array.from(document.querySelectorAll('[role="alert"]')).filter(x => x.offsetParent !== null).pop();
      const b = a.querySelector('button[aria-label="关闭错误提示"]');
      const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
      return {
        alert: {x: ar.x, y: ar.y, w: ar.width, h: ar.height, right: ar.right, bottom: ar.bottom},
        button: {x: br.x, y: br.y, w: br.width, h: br.height, right: br.right},
        slot: b.getAttribute('data-slot'),
        cls: b.className,
        text: a.textContent.trim(),
      };
    """)
    REPORT['steps']['alert_%s' % theme] = metrics
    log(json.dumps(metrics, ensure_ascii=False))

    check('[%s] 关闭钮 data-slot=alert-action' % theme, metrics['slot'] == 'alert-action', metrics['slot'])
    check('[%s] 关闭钮绝对定位 absolute' % theme, 'absolute' in metrics['cls'], metrics['cls'])
    check('[%s] 错误条单行高度（≤44px，修复前 56px）' % theme, metrics['alert']['h'] <= 44, metrics['alert']['h'])
    check('[%s] 关闭钮贴右上（right 距边 ≤20px，顶距边 ≤12px）' % theme,
          metrics['alert']['right'] - metrics['button']['right'] <= 20
          and abs(metrics['button']['y'] - metrics['alert']['y']) <= 12, metrics)
    check('[%s] 关闭钮自身尺寸正常（未拉满整行）' % theme,
          metrics['button']['w'] <= 40, metrics['button']['w'])

    shot(drv, 'p31_error_bar_%s.png' % theme)

    # 点错误条正文（左侧文字区）不应关闭
    drv.execute_script("""
      const a = Array.from(document.querySelectorAll('[role="alert"]')).filter(x => x.offsetParent !== null).pop();
      const r = a.getBoundingClientRect();
      a.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: r.x + 40, clientY: r.y + r.height / 2}));
    """)
    time.sleep(0.6)
    still = drv.execute_script(
        "return Array.from(document.querySelectorAll('[role=\"alert\"]')).filter(x => x.offsetParent !== null).length;")
    check('[%s] 点错误条正文不关闭（不再整行可点）' % theme, still >= 1, still)

    # 点关闭钮关闭
    drv.execute_script("""
      const a = Array.from(document.querySelectorAll('[role="alert"]')).filter(x => x.offsetParent !== null).pop();
      a.querySelector('button[aria-label="关闭错误提示"]').click();
    """)
    time.sleep(0.8)
    gone = drv.execute_script(
        "return Array.from(document.querySelectorAll('[role=\"alert\"]')).filter(x => x.offsetParent !== null).length;")
    check('[%s] 点关闭钮后错误条消失' % theme, gone == 0, gone)
    esc = drv.find_element(By.TAG_NAME, 'body')
    esc.send_keys(Keys.ESCAPE)
    time.sleep(0.6)


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'all'
    os.makedirs(ART, exist_ok=True)
    os.makedirs(DL, exist_ok=True)
    h1 = env_check('开工')
    REPORT['health_1'] = h1

    gid, ids = (None, [])
    if phase in ('all', 'batch'):
        gid, ids = create_fixtures()
        REPORT['fixture'] = {'group': gid, 'cases': ids}
        check('自建夹具（1 轮 + 3 轮两条用例）', bool(gid) and len(ids) == 2, ids)

    real = real_group = None
    if phase in ('all', 'alert'):
        real, real_group = pick_real_case_with_audio()
        REPORT['steps']['real_case'] = real
        REPORT['steps']['real_case_group'] = real_group
        check('找到带音频的真实用例（错误条用）', bool(real) and bool(real_group), (real, real_group))

    drv = driver()
    try:
        if phase in ('all', 'template'):
            step_template(drv)
        if phase in ('all', 'batch'):
            step_batch_rounds(drv, 'light')
            step_batch_rounds(drv, 'dark', items=(('声压', '批量设置声压级'),))
        if phase in ('all', 'alert'):
            step_error_alert(drv, 'light')
            step_error_alert(drv, 'dark')
        h2 = env_check('交付前')
        REPORT['health_2'] = h2
        check('防串库② 交付前 database=intelligent_audio_test', h2.get('database') == 'intelligent_audio_test', h2)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        if gid or ids:
            cleanup_fixtures(gid, ids)

    out = os.path.join(ART, 'report_int1673_%s.json' % phase)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)
    log('REPORT %s' % out)
    log('FAILS: %d' % len(REPORT['fail']))
    for item in REPORT['fail']:
        log(' - %s | %s' % (item['name'], item['detail']))
    return 1 if REPORT['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
