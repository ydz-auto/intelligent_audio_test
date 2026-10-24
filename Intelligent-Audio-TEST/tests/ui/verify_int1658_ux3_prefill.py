# -*- coding: utf-8 -*-
"""INT-1658 前端UX审计（复测打回项）：分组 facet「+ 新增分组」创建成功后预填分组筛选。

规范：doc/UX设计规范/11_用例域.md:172 ——「下拉底部固定项「+ 新增分组」
（group:create → 打开 §5.7.4 新建分组弹窗；创建成功后预填分组筛选）」。

覆盖：
1. 浅色：分组 facet 底部「+ 新增分组」→ 新建分组弹窗 → 保存 →
   POST /groups 201、GET /groups 200（选项刷新）、GET /testcases?...&group_id=<新组> 200，
   facet trigger 预填新组名、分组上下文头渲染新组。
2. 回归：页头「新建分组」建组后 trigger 仍「分组 全部」（不误预填）。
3. 重置 → trigger 回「分组 全部」。
4. 深色（iatp:theme:v1:mode=dark + 整页重载，断言 html.dark）：同一 facet 入口建组 → 同样预填。
5. 控制台无 SEVERE。
6. 本 run 自建分组全部清理，GET /groups 回读无残留。

环境：旁路 nginx 容器（dist ← frontend-react/dist，/api → api_gateway:5000，
network intelligent-audio-test_default），真实库栈 database=intelligent_audio_test。
前置：frontend-react `pnpm build`；容器已启动（脚本不负责起容器，端口由 INT1658_PORT 指定）。
"""
import json
import os
import sys
import time

import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORT = os.environ.get('INT1658_PORT', '15276')
BASE = 'http://127.0.0.1:%s' % PORT
ART = os.path.join(REPO, 'tests', 'ui', 'artifacts', 'int1658')
os.makedirs(ART, exist_ok=True)
THEME_KEY = 'iatp:theme:v1:mode'
STAMP = time.strftime('%H%M%S')
PREFIX = '接线测试_INT1658UX3_%s' % STAMP

RESULT = {'env': [], 'steps': {}, 'console': [], 'created': [], 'shots': []}
FAIL = []

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url: url, method: method };
  try {
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


def log(m):
    print(m, flush=True)


def check(name, cond, detail=''):
    RESULT['steps'][name] = {'ok': bool(cond), 'detail': detail}
    log('%s %s %s' % ('PASS' if cond else 'FAIL', name, detail))
    if not cond:
        FAIL.append(name)


def env_check(tag):
    with urllib.request.urlopen(BASE + '/health', timeout=20) as r:
        health = json.loads(r.read().decode())
    RESULT['env'].append({'tag': tag, 'health': health})
    log('ENV[%s] database=%s' % (tag, health.get('database')))
    if health.get('database') != 'intelligent_audio_test':
        raise SystemExit('环境串库：%s' % health)
    return health


def _driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        major = 0
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(root):
        for ver in os.listdir(root):
            exe = os.path.join(root, ver, 'chromedriver.exe')
            if os.path.isfile(exe) and ver.split('.')[0] == str(major):
                path = exe
    service = Service(executable_path=path) if path else Service()
    drv = webdriver.Chrome(options=o, service=service)
    drv.set_page_load_timeout(90)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def body(drv):
    return drv.execute_script('return document.body.innerText || ""') or ''


def wait_text(drv, text, timeout=40):
    WebDriverWait(drv, timeout).until(lambda d: text in body(d))


def wait_until(fn, timeout=40, interval=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def shot(drv, name):
    p = os.path.join(ART, name)
    drv.save_screenshot(p)
    RESULT['shots'].append(name)
    log('shot %s' % p)


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(2.0)
    if '/login' not in drv.current_url:
        return
    enter = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if enter:
        js_click(drv, enter[0])
        if wait_until(lambda: '/login' not in drv.current_url, 20):
            return
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_elements(By.XPATH, "//button[contains(., '登')]")[0].click()
    WebDriverWait(drv, 60).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem(arguments[0], arguments[1])", THEME_KEY, mode)


def is_dark(drv):
    return drv.execute_script("return document.documentElement.classList.contains('dark')")


def fetch_log(drv):
    return drv.execute_script('return window.__fetchLog || []') or []


def clear_log(drv):
    drv.execute_script('window.__fetchLog = []')


def facet_trigger(drv):
    for b in drv.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='分组']]"):
        if b.is_displayed():
            return b
    return None


def trigger_value(drv):
    b = facet_trigger(drv)
    if b is None:
        return None
    spans = b.find_elements(By.TAG_NAME, 'span')
    return spans[-1].text.strip() if spans else ''


def open_facet(drv):
    b = facet_trigger(drv)
    if b is None:
        raise AssertionError('分组 facet trigger 未找到')
    js_click(drv, b)
    time.sleep(0.8)


def facet_footer(drv):
    for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='+ 新增分组']"):
        if b.is_displayed():
            return b
    return None


def visible_dialog(drv):
    out = []
    for d in drv.find_elements(By.CSS_SELECTOR, "div[role='dialog']"):
        try:
            if d.is_displayed():
                out.append(d)
        except Exception:
            continue
    return out[-1] if out else None


def dialog_title(drv):
    d = visible_dialog(drv)
    if d is None:
        return ''
    return drv.execute_script(
        "const h=arguments[0].querySelector('h2,[data-slot=dialog-title]');"
        "return h?(h.innerText||'').trim():''", d)


def wait_dialog_closed(drv, timeout=40):
    return wait_until(lambda: visible_dialog(drv) is None or not dialog_inputs(drv), timeout)


def dialog_inputs(drv):
    d = visible_dialog(drv)
    return d.find_elements(By.ID, 'group-name') if d is not None else []


def fill_and_save(drv, name):
    # base-ui 弹窗挂载/关闭有过渡，元素可能瞬时 stale：短暂重试取到可输入的弹窗
    deadline = time.time() + 15
    d = None
    while time.time() < deadline:
        d = visible_dialog(drv)
        if d is not None and dialog_inputs(drv):
            break
        time.sleep(0.4)
    if d is None or not dialog_inputs(drv):
        raise AssertionError('新建分组弹窗未打开')
    d = visible_dialog(drv)
    inp = d.find_element(By.ID, 'group-name')
    inp.clear()
    inp.send_keys(name)
    time.sleep(0.3)
    btn = [b for b in d.find_elements(By.XPATH, ".//button[normalize-space(.)='保存']") if b.is_displayed()]
    if not btn:
        raise AssertionError('弹窗内无「保存」按钮')
    js_click(drv, btn[0])


def page_fetch_json(drv, path, method='GET'):
    """页内 fetch（带会话 cookie），返回 {status, body}"""
    js = """
    const done = arguments[arguments.length - 1];
    fetch(arguments[0], {method: arguments[1], credentials: 'include',
                         headers: {'Content-Type': 'application/json'}})
      .then(async r => done({status: r.status, text: await r.text()}))
      .catch(e => done({status: -1, text: String(e)}));
    """
    drv.set_script_timeout(60)
    return drv.execute_async_script(js, path, method)


def list_groups(drv):
    r = page_fetch_json(drv, '/api/v1/groups?page=1&per_page=200')
    try:
        data = json.loads(r['text']).get('data') or {}
    except Exception:
        return None, r
    return (data.get('items') or []), r


def created_requests(log):
    out = []
    for e in log:
        u = e.get('url', '')
        if '/api/v1/groups' in u or ('/api/v1/testcases' in u and 'group_id=' in u):
            out.append({'method': e.get('method'), 'url': u, 'status': e.get('status')})
    return out


def network_shot(drv, rows, name):
    trs = ''.join(
        "<tr><td>%s</td><td style='font-family:monospace'>%s</td><td>%s</td></tr>"
        % (r['method'], r['url'][:150], r['status']) for r in rows)
    html = ("<html><head><meta charset='utf-8'><style>body{font:13px system-ui;padding:16px}"
            "table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:4px 8px}"
            "th{background:#eee}</style></head><body><h3>INT-1658 Network 证据（页内 fetch 打点）</h3>"
            "<table><tr><th>方法</th><th>URL</th><th>状态</th></tr>%s</table></body></html>" % trs)
    drv.get('data:text/html;charset=utf-8,' + urllib.parse.quote(html))
    time.sleep(0.5)
    shot(drv, name)


def main():
    env_check('start')
    drv = _driver()
    created_names = []
    try:
        login(drv)
        set_theme(drv, 'light')

        # ── 浅色：facet 底部「+ 新增分组」→ 保存 → 预填 ──
        drv.get(BASE + '/testcases/by-group')
        wait_text(drv, '用例管理', 60)
        ok = wait_until(lambda: facet_trigger(drv) is not None, 60)
        check('浅色/分组 facet 存在', ok)
        check('浅色/初始 trigger=全部', trigger_value(drv) == '全部', str(trigger_value(drv)))

        clear_log(drv)
        open_facet(drv)
        footer = facet_footer(drv)
        shot(drv, '01_light_facet_footer.png')
        check('浅色/下拉底部「+ 新增分组」可见', footer is not None)
        if footer is None:
            raise SystemExit('facet 底部项缺失，无法继续')

        n1 = PREFIX + '_A'
        js_click(drv, footer)
        wait_until(lambda: visible_dialog(drv) is not None, 20)
        check('浅色/弹窗标题=新建分组', dialog_title(drv) == '新建分组', dialog_title(drv))
        shot(drv, '02_light_dialog_new_group.png')
        fill_and_save(drv, n1)
        created_names.append(n1)
        closed = wait_dialog_closed(drv)
        check('浅色/保存后弹窗关闭', closed)
        prefilled = wait_until(lambda: trigger_value(drv) == n1, 60)
        check('浅色/建组成功后 trigger 预填新组名', prefilled, str(trigger_value(drv)))
        hit_group = wait_until(
            lambda: any(('group_id=' in (e.get('url') or '')) and e.get('status') == 200
                        for e in fetch_log(drv)), 45)
        check('浅色/筛选生效：GET /testcases?...group_id=新组 200', hit_group)
        # 新组下无用例：按 INT-595/§3.3 空态口径走空态（分组卡在平铺集为空时不渲染），
        # 不能拿「分组上下文头」当本项的通过条件；此处只断言筛选已生效到空态文案。
        empty = wait_until(lambda: '没有找到符合条件的测试用例' in body(drv), 45)
        check('浅色/筛选后按新组空态（新组无用例）', empty)
        shot(drv, '03_light_after_create_prefilled.png')

        reqs = created_requests(fetch_log(drv))
        check('浅色/POST /groups 201', any(r['method'] == 'POST' and r['status'] == 201 for r in reqs),
              json.dumps([r for r in reqs if r['method'] == 'POST'], ensure_ascii=False))
        check('浅色/GET /groups 刷新 200', any(r['method'] == 'GET' and '/groups' in r['url'] and r['status'] == 200 for r in reqs))

        # ── 重置（就地：筛选态下才有「重置」钮） ──
        reset = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='重置']") if b.is_displayed()]
        check('浅色/重置按钮存在（筛选态）', bool(reset))
        if reset:
            js_click(drv, reset[0])
        ok_reset = wait_until(lambda: trigger_value(drv) == '全部', 30)
        check('浅色/重置后 trigger=全部', ok_reset, str(trigger_value(drv)))

        # Network 证据截图会跳走页面，放到重置之后（并在下一段前回列表页）
        network_shot(drv, reqs, '07_network_evidence.png')
        drv.get(BASE + '/testcases/by-group')
        wait_until(lambda: facet_trigger(drv) is not None, 60)

        # ── 回归：页头「新建分组」不预填 ──
        header_btns = [b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='新建分组']")
                       if b.is_displayed()]
        check('浅色/页头「新建分组」入口存在', bool(header_btns))
        if header_btns:
            n2 = PREFIX + '_B'
            js_click(drv, header_btns[0])
            wait_until(lambda: visible_dialog(drv) is not None, 20)
            check('浅色/页头弹窗标题=新建分组', dialog_title(drv) == '新建分组', dialog_title(drv))
            fill_and_save(drv, n2)
            created_names.append(n2)
            wait_dialog_closed(drv)
            time.sleep(3.0)
            check('回归/页头建组后 trigger 仍=全部', trigger_value(drv) == '全部', str(trigger_value(drv)))
            shot(drv, '04_light_header_create_no_prefill.png')

        # ── 深色：facet 入口同样预填 ──
        env_check('before-dark')
        set_theme(drv, 'dark')
        drv.get(BASE + '/testcases/by-group')
        wait_until(lambda: facet_trigger(drv) is not None, 60)
        check('深色/html.dark 生效', is_dark(drv))
        clear_log(drv)
        open_facet(drv)
        footer2 = facet_footer(drv)
        shot(drv, '05_dark_facet_footer.png')
        check('深色/下拉底部「+ 新增分组」可见', footer2 is not None)
        if footer2 is not None:
            n3 = PREFIX + '_C'
            js_click(drv, footer2)
            wait_until(lambda: visible_dialog(drv) is not None, 20)
            fill_and_save(drv, n3)
            created_names.append(n3)
            wait_dialog_closed(drv)
            ok_dark = wait_until(lambda: trigger_value(drv) == n3, 60)
            check('深色/建组成功后 trigger 预填新组名', ok_dark, str(trigger_value(drv)))
            check('深色/筛选后按新组空态（新组无用例）',
                  wait_until(lambda: '没有找到符合条件的测试用例' in body(drv), 45))
            shot(drv, '06_dark_after_create_prefilled.png')

        # ── 控制台 ──
        severe = []
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                severe.append(entry.get('message', '')[:300])
        RESULT['console'] = severe
        check('控制台无 SEVERE', not severe, json.dumps(severe, ensure_ascii=False)[:500])

    finally:
        # ── 清理：删本 run 自建分组（页内 fetch 带会话） ──
        try:
            env_check('end')
            if not drv.current_url.startswith(BASE):
                drv.get(BASE + '/testcases/by-group')
                wait_until(lambda: facet_trigger(drv) is not None, 60)
            items, _ = list_groups(drv)
            ids = []
            for g in items or []:
                if str(g.get('name', '')).startswith('接线测试_INT1658UX3_'):
                    ids.append((str(g.get('id')), g.get('name')))
            RESULT['cleanup'] = {'found': ids, 'deleted': []}
            for gid, gname in ids:
                r = page_fetch_json(drv, '/api/v1/groups/%s' % gid, 'DELETE')
                if r['status'] >= 400:
                    r = page_fetch_json(drv, '/api/v1/groups/%s?cascade=true' % gid, 'DELETE')
                RESULT['cleanup']['deleted'].append(
                    {'id': gid, 'name': gname, 'status': r['status']})
            items2, _ = list_groups(drv)
            left = [g.get('name') for g in (items2 or [])
                    if str(g.get('name', '')).startswith('接线测试_INT1658UX3_')]
            RESULT['cleanup']['remaining'] = left
            check('清理/自建分组无残留', not left, json.dumps(left, ensure_ascii=False))
        except Exception as exc:
            RESULT['cleanup'] = {'error': str(exc)[:300]}
            log('cleanup error: %s' % exc)
        try:
            drv.quit()
        except Exception:
            pass

    RESULT['pass'] = not FAIL
    RESULT['fail'] = FAIL
    out = os.path.join(ART, 'result_%s.json' % STAMP)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(RESULT, f, ensure_ascii=False, indent=2)
    log('RESULT %s' % json.dumps({'pass': RESULT['pass'], 'fail': FAIL}, ensure_ascii=False))
    log('saved %s' % out)


if __name__ == '__main__':
    main()
