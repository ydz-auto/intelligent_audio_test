# -*- coding: utf-8 -*-
"""INT-2197 音频管理页「可见性（共享/私有）」筛选取证脚本。

针对本 worktree 的 React dev server（端口 5301，`API_PROXY_TARGET` -> docker 真实栈 :15000，
库 intelligent_audio_test），真实登录后走音频管理页，核对：

① 筛选工具栏出现「可见性」facet，默认「全部」（请求不带 visibility）；
② 切「私有」→ POST /api/v1/audios body 带 visibility=private，标题计数与分页总数
   等于服务端 total（主库当前 0 条 private → 「暂无音频文件」空态，不是前端过滤）；
③ 切「共享」→ body visibility=shared，计数 = 服务端 shared total；翻页仍带 visibility，
   计数不变（页码/总数同步）；
④ 可见性与其它 facet（格式 MP3）组合时一并下发，计数 = 服务端同参数 total；
⑤ 重置 → 请求不再带 visibility，计数回到全量；
⑥ 深浅色截图 + 交互态（facet 展开）+ console 无 SEVERE + Network 请求表截图。

失败/取证产物落 tests/ui/artifacts/int2197/。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2197')
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5301')
USERNAME = os.environ.get('REACT_USER', 'dev_user')
PASSWORD = os.environ.get('REACT_PASSWORD', 'dev_password')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

os.makedirs(ARTIFACTS, exist_ok=True)
RESULTS = []
PERF_EVENTS = []


def log(ok, name, detail=''):
    RESULTS.append({'ok': ok, 'name': name, 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + (' | ' + str(detail) if detail else ''))


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run',
              '--no-default-browser-check']:
        options.add_argument(a)
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
                    if int([x for x in ver.split('.') if x.isdigit()][0]) == chrome_major:
                        drv_path = exe
                except (ValueError, IndexError):
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(90)
    return drv


def drain_perf(drv):
    """取走并归档 performance 日志（避免缓冲区截断）。"""
    try:
        for entry in drv.get_log('performance'):
            PERF_EVENTS.append(entry)
    except Exception:
        pass


def audios_posts(drv, drain=False):
    if drain:
        drain_perf(drv)
    posts = []
    for entry in PERF_EVENTS:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.requestWillBeSent':
            continue
        params = msg.get('params', {})
        req = params.get('request', {})
        url = req.get('url', '')
        if '/api/v1/audios' in url and req.get('method') == 'POST' and url.rstrip('/').endswith('/audios'):
            body = req.get('postData')
            try:
                body = json.loads(body) if body else {}
            except Exception:
                body = {'raw': body}
            posts.append({'ts': params.get('timestamp'), 'body': body})
    return posts


BADGE_JS = """
const el=[...document.querySelectorAll('span')].find(e=>e.children.length===0 && /^共\\s.*\\s个$/.test((e.textContent||'').trim()));
return el ? el.textContent.trim() : null;
"""


def badge_text(drv):
    return drv.execute_script('return (function(){%s})()' % BADGE_JS)


def badge_number(text):
    if not text:
        return None
    digits = ''.join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def wait_badge(drv, expected, timeout=60):
    return WebDriverWait(drv, timeout).until(
        lambda d: badge_number(badge_text(d)) == expected)


def click_facet(drv, label):
    # 用 JS 直接点（Base UI Popover 用 pointer 事件，原生 click 在某些态被吞）
    drv.execute_script("(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.replace(/\\s+/g,'').includes(arguments[0]));if(!b)return;b.scrollIntoView({block:'center'});b.click();})(arguments[0])", label)
    time.sleep(0.5)


def click_option(drv, label, timeout=20):
    def _find(d):
        # 注意：Base UI 弹层是 fixed 定位，offsetParent 恒为 null，用 getClientRects 判可见
        return d.execute_script(
            "(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===arguments[0] && x.getClientRects().length>0);"
            "if(!b)return null;b.scrollIntoView({block:'center'});b.click();return true;})(arguments[0])", label)
    WebDriverWait(drv, timeout).until(_find)
    time.sleep(0.4)


def select_option(drv, facet_label, option_label, timeout=45):
    """选 facet 选项；弹层没开就先点开（关闭态选项仍在 DOM 但不可见）。"""
    end = time.time() + timeout
    find_js = ("var b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===arguments[0] && x.getClientRects().length>0);"
               "if(!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true;")
    while time.time() < end:
        clicked = drv.execute_script(find_js, option_label)
        if clicked:
            time.sleep(0.5)
            return True
        click_facet(drv, facet_label)
        time.sleep(0.6)
    raise RuntimeError('facet option not found: %s -> %s' % (facet_label, option_label))


def server_totals(drv, payloads):
    """页内带 JWT 直接打网关，拿服务端同参数 total（用于前端计数比对）。"""
    js = """
    const done = arguments[arguments.length - 1];
    const token = window.localStorage.getItem('iatp:auth:token:v1');
    const payloads = arguments[0];
    const out = {};
    let pending = payloads.length;
    payloads.forEach(function (p, i) {
      fetch('/api/v1/audios', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
        body: JSON.stringify(p.payload)
      }).then(function (r) { return r.json().then(function (j) { return {s: r.status, j: j}; }); })
        .then(function (res) {
          const d = (res.j && res.j.data) || {};
          out[p.key] = {status: res.s, total: d.total, pages: d.pages};
        })
        .catch(function (e) { out[p.key] = {error: String(e)}; })
        .then(function () { pending -= 1; if (pending === 0) done(out); });
    });
    """
    return drv.execute_async_script(js, payloads)


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 60).until(lambda d: d.find_element(By.CSS_SELECTOR, '#username'))
    last_err = None
    for attempt in range(2):
        drv.find_element(By.CSS_SELECTOR, '#username').clear()
        drv.find_element(By.CSS_SELECTOR, '#username').send_keys(USERNAME)
        drv.find_element(By.CSS_SELECTOR, '#password').clear()
        drv.find_element(By.CSS_SELECTOR, '#password').send_keys(PASSWORD)
        drv.execute_script("document.querySelector('form').requestSubmit()")
        try:
            WebDriverWait(drv, 60).until(lambda d: '/login' not in d.current_url)
            log(True, '登录', drv.current_url)
            return
        except Exception as err:
            last_err = err
            shot(drv, 'login_failed_attempt%d' % attempt)
            time.sleep(2)
    raise RuntimeError('login failed: %s' % last_err)


def snapshot(drv):
    """抽干缓冲并返回当前 POST /audios 条数（只匹配此后的新请求）。"""
    drain_perf(drv)
    return len(audios_posts(drv))


def wait_post(drv, pred, since, timeout=90):
    """等待一条满足条件的新 POST /audios 请求（边等边抽干 performance 缓冲）。"""
    def _check(d):
        drain_perf(d)
        for p in reversed(audios_posts(d)[since:]):
            if pred(p['body']):
                return p
        return None
    return WebDriverWait(drv, timeout, poll_frequency=0.5).until(_check)


def try_wait_badge(drv, expected, timeout=75):
    try:
        wait_badge(drv, expected, timeout)
        return True
    except Exception:
        return False


def try_wait_post(drv, pred, since, timeout=75):
    try:
        return wait_post(drv, pred, since, timeout)
    except Exception:
        return None


def goto_audio(drv):
    drv.get(BASE + '/audio-import')
    WebDriverWait(drv, 60).until(lambda d: d.execute_script(
        "return !![...document.querySelectorAll('button')].find(b=>b.textContent.includes('可见性'))"))
    WebDriverWait(drv, 90).until(lambda d: badge_number(badge_text(d)) is not None)
    time.sleep(1)


def set_theme(drv, mode):
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    drv.refresh()
    WebDriverWait(drv, 60).until(lambda d: d.execute_script(
        "return document.documentElement.className.includes('dark') === arguments[0]", mode == 'dark'))
    WebDriverWait(drv, 90).until(lambda d: badge_text(d) is not None)
    time.sleep(1)


def shot(drv, name):
    path = os.path.join(ARTIFACTS, name + '.png')
    drv.save_screenshot(path)
    print('  shot ->', path)
    return path


def main():
    drv = _driver()
    try:
        login(drv)
        goto_audio(drv)
        # 先抓首屏列表请求（此时还没做页内 server_totals 探针，避免混入）
        initial_posts = audios_posts(drv, drain=True)

        totals = server_totals(drv, [
            {'key': 'all', 'payload': {'page': 1, 'per_page': 20}},
            {'key': 'shared', 'payload': {'page': 1, 'per_page': 20, 'visibility': 'shared'}},
            {'key': 'private', 'payload': {'page': 1, 'per_page': 20, 'visibility': 'private'}},
            {'key': 'shared_mp3', 'payload': {'page': 1, 'per_page': 20, 'visibility': 'shared', 'format': 'mp3'}},
        ])
        print('server totals:', json.dumps(totals, ensure_ascii=False))
        log(totals.get('all', {}).get('total') == totals.get('shared', {}).get('total', -1)
            + totals.get('private', {}).get('total', -2), '服务端 shared+private=全量',
            'shared=%s private=%s all=%s' % (totals.get('shared', {}).get('total'),
                                             totals.get('private', {}).get('total'),
                                             totals.get('all', {}).get('total')))

        # ① 默认「全部」
        all_total = totals['all']['total']
        ok = try_wait_badge(drv, all_total)
        log(ok and badge_number(badge_text(drv)) == all_total, '默认全部：标题计数=服务端全量', badge_text(drv))
        posts = [p for p in initial_posts if 'visibility' not in p['body']]
        log(len(posts) > 0, '默认全部：请求不带 visibility', len(posts))
        log('可见性' in drv.execute_script("return document.body.innerText"), '筛选工具栏含「可见性」facet')
        shot(drv, 'light_default_all')

        # ② 私有
        click_facet(drv, '可见性')
        time.sleep(0.6)
        shot(drv, 'light_facet_open')
        since_private = snapshot(drv)
        select_option(drv, '可见性', '私有')
        ok = try_wait_badge(drv, totals['private']['total'])
        priv_badge = badge_text(drv)
        log(ok and badge_number(priv_badge) == totals['private']['total'], '私有：标题计数=服务端 private total', priv_badge)
        empty = drv.execute_script("return document.body.innerText.includes('暂无音频文件')")
        log(empty == (totals['private']['total'] == 0), '私有：空态与私有条数一致', empty)
        priv_post = try_wait_post(drv, lambda b: b.get('visibility') == 'private', since_private)
        log(priv_post is not None, '私有：POST /audios 带 visibility=private',
            priv_post['body'] if priv_post else None)
        shot(drv, 'light_private_empty')

        # ③ 共享
        click_facet(drv, '可见性')
        time.sleep(0.4)
        since_shared = snapshot(drv)
        select_option(drv, '可见性', '共享')
        ok = try_wait_badge(drv, totals['shared']['total'])
        log(ok and badge_number(badge_text(drv)) == totals['shared']['total'], '共享：标题计数=服务端 shared total', badge_text(drv))
        shared_post = try_wait_post(drv, lambda b: b.get('visibility') == 'shared', since_shared)
        log(shared_post is not None, '共享：POST /audios 带 visibility=shared',
            shared_post['body'] if shared_post else None)
        rows = drv.execute_script("return document.querySelectorAll('tbody tr').length")
        log(rows == 20, '共享：首页渲染 20 行', rows)
        shot(drv, 'light_shared')

        # ③b 翻页仍带筛选项，总数不变
        since_page2 = snapshot(drv)
        drv.execute_script("(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='下一页');if(b){b.click();return true;}return false;})()")
        page2 = try_wait_post(drv, lambda b: b.get('page') == 2 and b.get('visibility') == 'shared', since_page2)
        log(page2 is not None, '翻页：第 2 页请求仍带 visibility=shared', page2['body'] if page2 else None)
        log(badge_number(badge_text(drv)) == totals['shared']['total'], '翻页：总数不变', badge_text(drv))
        shot(drv, 'light_shared_page2')

        # ④ 组合筛选（共享 + 格式 MP3）
        click_facet(drv, '格式')
        time.sleep(0.4)
        since_combo = snapshot(drv)
        select_option(drv, '格式', 'MP3')
        ok = try_wait_badge(drv, totals['shared_mp3']['total'], timeout=90)
        combo = try_wait_post(drv, lambda b: b.get('visibility') == 'shared' and b.get('format') == 'mp3', since_combo)
        log(combo is not None, '组合：visibility+format 一并下发', combo['body'] if combo else None)
        log(ok and badge_number(badge_text(drv)) == totals['shared_mp3']['total'], '组合：计数=服务端同参数 total', badge_text(drv))
        shot(drv, 'light_shared_mp3')

        # ⑤ 重置（缓存命中时可能不发新请求——此时只要「没有带筛选的新请求」即达标）
        since_reset = snapshot(drv)
        drv.execute_script("(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.replace(/\\s+/g,'')==='重置');if(b){b.click();return true;}return false;})()")
        ok = try_wait_badge(drv, all_total, timeout=90)
        time.sleep(1.5)
        drain_perf(drv)
        new_posts = audios_posts(drv)[since_reset:]
        bad_posts = [p for p in new_posts if 'visibility' in p['body'] or 'format' in p['body']]
        log(len(bad_posts) == 0, '重置：无带 visibility/format 的新请求',
            ('新请求 %d 条，全量 body=%s' % (len(new_posts), new_posts[-1]['body'] if new_posts else None)))
        log(ok and badge_number(badge_text(drv)) == all_total, '重置：计数=服务端全量', badge_text(drv))

        # ⑥ 深色：私有空态 + 共享列表
        set_theme(drv, 'dark')
        log(drv.execute_script("return document.documentElement.className.includes('dark')"), '深色主题生效')
        click_facet(drv, '可见性')
        time.sleep(0.5)
        select_option(drv, '可见性', '私有')
        ok = try_wait_badge(drv, totals['private']['total'], timeout=90)
        log(ok, '深色·私有：计数=服务端 private total', badge_text(drv))
        shot(drv, 'dark_private_empty')
        click_facet(drv, '可见性')
        time.sleep(0.4)
        select_option(drv, '可见性', '共享')
        ok = try_wait_badge(drv, totals['shared']['total'], timeout=90)
        log(ok, '深色·共享：计数=服务端 shared total', badge_text(drv))
        shot(drv, 'dark_shared')

        # ⑦ console
        drain_perf(drv)
        severe = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
        log(len(severe) == 0, 'console 无 SEVERE', json.dumps(severe[:3], ensure_ascii=False))

        # ⑧ Network 证据：把本 run 抓到的 POST /audios 请求渲染成表格截图
        rows = []
        for p in audios_posts(drv):
            rows.append(json.dumps(p['body'], ensure_ascii=False))
        html = ('<html><head><meta charset="utf-8"><style>body{font:13px Consolas,monospace;background:#0f172a;color:#e2e8f0;padding:16px}'
                'h2{font:16px sans-serif;color:#93c5fd}table{border-collapse:collapse;width:100%}td,th{border:1px solid #334155;padding:6px 8px;vertical-align:top}'
                'th{background:#1e293b;color:#cbd5e1;text-align:left}</style></head><body>'
                '<h2>Network · POST /api/v1/audios（本 run 抓取）</h2><table><tr><th>#</th><th>request body</th></tr>')
        for i, r in enumerate(rows, 1):
            html += '<tr><td>%d</td><td>%s</td></tr>' % (i, r)
        html += '</table></body></html>'
        net_html = os.path.join(ARTIFACTS, 'network_table.html')
        with open(net_html, 'w', encoding='utf-8') as f:
            f.write(html)
        with open(os.path.join(ARTIFACTS, 'network_requests.json'), 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        drv.get('file:///' + net_html.replace('\\', '/'))
        time.sleep(1)
        shot(drv, 'network_posts')

        with open(os.path.join(ARTIFACTS, 'results.json'), 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        with open(os.path.join(ARTIFACTS, 'perf.log'), 'w', encoding='utf-8') as f:
            for entry in PERF_EVENTS:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        failed = [r for r in RESULTS if not r['ok']]
        print('\n=== SUMMARY: %d/%d passed ===' % (len(RESULTS) - len(failed), len(RESULTS)))
        return 0 if not failed else 1
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    raise SystemExit(main())
