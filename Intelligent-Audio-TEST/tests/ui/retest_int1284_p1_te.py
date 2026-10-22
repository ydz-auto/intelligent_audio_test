# -*- coding: utf-8 -*-
"""INT-1284 P1 返工独立复测（测试工程师）。

打回项：部分覆盖分组（0 < 首屏已加载 < test_case_count）展开必须按分组懒加载，
组内余量经「加载更多」服务端翻页可达，与 test_case_count 计数一致（前端UX审计 P1）。

独立于实施者脚本的复测：首屏 /groups + /testcases 响应体用页内 window.fetch 直取
（localStorage iatp:auth:token:v1），避免 Network.getResponseBody 时序竞态；懒加载
请求与翻页用 CDP performance 日志捕获。

连真实库栈 5700（/health database=intelligent_audio_test），登录 接线测试_admin，
React dev 代理 5304（临时 rsbuild.realstack.config.ts 覆盖 proxy → 5700）。
"""
import argparse
import base64
import json
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5304'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1284_p1_te_retest')
USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'

LOG = []


def log(msg):
    LOG.append(str(msg))
    try:
        print(msg)
    except Exception:
        pass


def _health(db_marker):
    import urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:5700/health', timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8', 'replace'))
        db = data.get('database', '?')
        log('[health %s] database=%s' % (db_marker, db))
        return db
    except Exception as e:
        log('[health %s] FAIL %r' % (db_marker, e))
        return None


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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
                    cand = tuple(int(x) for x in ver.split('.') if x.isdigit())
                    if cand and cand[0] == chrome_major:
                        drv_path = exe
                except ValueError:
                    continue
    return webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())


def _drain(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def _net(drv):
    """performance 日志 → {url: status}（请求 URL + 响应状态）"""
    out = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            params = (msg.get('message') or {}).get('params') or {}
            method = (msg.get('message') or {}).get('method') or ''
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            r = params.get('request') or {}
            out[r.get('url', '')] = None
        elif method == 'Network.responseReceived':
            resp = params.get('response') or {}
            url = resp.get('url', '')
            if url in out:
                out[url] = resp.get('status')
    return out


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def _wait_text(drv, text, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if text in _body_text(drv):
            return True
        time.sleep(0.7)
    return False


def _card_info(drv):
    """分组卡组名 + 计数 Badge"""
    return drv.execute_script('''
      const out = [];
      document.querySelectorAll('div.bg-card').forEach(card => {
        const name = card.querySelector('span.font-medium.truncate');
        if (!name) return;
        const badge = card.querySelector('span.rounded-md');
        out.push({ name: name.textContent.trim(), badge: badge ? badge.textContent.trim() : null });
      });
      return out;
    ''')


def _wait_cards(drv, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            cards = _card_info(drv)
            if cards and any(c['name'] and c['name'] != '未分组' for c in cards):
                return True
        except Exception:
            pass
        time.sleep(0.7)
    return False


def _click_group(drv, name):
    els = drv.find_elements(By.CSS_SELECTOR, 'span.font-medium.truncate')
    for el in els:
        if el.text.strip() == name:
            drv.execute_script('arguments[0].click();', el)
            return True
    return False


def _lazy_btn_text(drv):
    btns = drv.find_elements(By.TAG_NAME, 'button')
    for b in btns:
        t = (b.text or '').strip()
        if '条 · 加载更多' in t and '个分组' not in t:
            return t
    return None


def _click_lazy_more(drv, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        btns = drv.find_elements(By.TAG_NAME, 'button')
        for b in btns:
            t = (b.text or '').strip()
            if '条 · 加载更多' in t and '个分组' not in t:
                drv.execute_script('arguments[0].click();', b)
                return True
        time.sleep(0.5)
    return False


def _fetch_api(drv, path):
    """页内 fetch（带登录态 token），返回解析后的 JSON 或 None（execute_async_script 等 Promise）"""
    return drv.execute_async_script('''
      const done = arguments[arguments.length - 1];
      const token = localStorage.getItem('iatp:auth:token:v1') || '';
      fetch(arguments[0], {
        headers: token ? { Authorization: 'Bearer ' + token } : {},
      })
        .then(r => r.text())
        .then(t => { try { done(JSON.parse(t)); } catch(e) { done(null); } })
        .catch(() => done(null));
    ''', path)


def _set_theme(drv, mode):
    drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "%s")' % mode)


def _lazy_req_urls(drv, net):
    """提取本次日志中的按分组懒加载 /testcases?group_id 请求 (url, status)"""
    out = []
    for url, status in net.items():
        if '/testcases' in url and 'group_id=' in url:
            out.append((url, status))
    return out


def _poll_lazy(drv, group_id, match, timeout=25):
    """轮询 performance 日志直到出现符合 match(url) 的按分组懒加载请求；
    返回期间累计看到的全部懒加载 (url, status) 列表与是否命中。"""
    seen = []
    hit = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        for url, status in _lazy_req_urls(drv, _net(drv)):
            if ('group_id=' + group_id) in url:
                seen.append((url, status))
                if match(url):
                    hit = True
        if hit:
            break
        time.sleep(0.7)
    return hit, seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=BASE)
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    db_start = _health('start')
    reasons = []
    ok = True

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.set_script_timeout(120)
        # ---- 登录 ----
        drv.get(base + '/login')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1)
        drv.find_element(By.ID, 'username').send_keys(USERNAME)
        drv.find_element(By.ID, 'password').send_keys(PASSWORD)
        drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(drv, 20).until(lambda d: '/dashboard' in d.current_url)
        time.sleep(2)
        log('LOGIN OK -> ' + drv.current_url)

        # ---- /start-test 步骤一 分组视图 ----
        _drain(drv)
        drv.get(base + '/start-test?step=0&view=table')
        if not _wait_cards(drv):
            ok = False
            reasons.append('start-test group cards did not render')
        time.sleep(2)
        net1 = _net(drv)

        # ---- 权威数据：/groups + 首屏 /testcases（页内 fetch，规避 CDP 时序竞态）----
        groups_json = _fetch_api(drv, '/api/v1/groups?page=1&per_page=200')
        inner = (groups_json or {}).get('data', groups_json) if groups_json else {}
        group_items = inner.get('items', []) if isinstance(inner, dict) else []
        group_counts = {g.get('name', ''): g.get('test_case_count', g.get('testCaseCount', 0)) for g in group_items}
        group_ids = {g.get('name', ''): g.get('id', '') for g in group_items}
        log('GROUPS total=%d counts=%s' % (len(group_items), json.dumps(group_counts, ensure_ascii=False)))

        tc_json = _fetch_api(drv, '/api/v1/testcases?page=1&per_page=100')
        inner_tc = (tc_json or {}).get('data', tc_json) if tc_json else {}
        loaded_by_group = {}
        tc_total = 0
        if isinstance(inner_tc, dict):
            tc_total = inner_tc.get('total', 0)
            for c in inner_tc.get('items', []):
                gname = c.get('group_name') or c.get('groupName') or ''
                loaded_by_group[gname] = loaded_by_group.get(gname, 0) + 1
        log('TESTCASES first-screen total=%d loaded-by-group=%s'
            % (tc_total, json.dumps(loaded_by_group, ensure_ascii=False)))

        # ---- 分组卡渲染核对 ----
        cards = _card_info(drv)
        rendered = {c['name'] for c in cards}
        missing_first = [n for n in group_counts if n not in rendered]
        count_mismatch = []
        for c in cards:
            if c['name'] in group_counts:
                badge_num = ''.join(ch for ch in (c['badge'] or '') if ch.isdigit())
                expected_num = str(group_counts[c['name']])
                if badge_num != expected_num:
                    count_mismatch.append('%s badge=%s expect=%s' % (c['name'], badge_num, expected_num))
        log('CARDS first-screen(%d) missing=%s count_mismatch=%s'
            % (len(cards), json.dumps(missing_first, ensure_ascii=False), json.dumps(count_mismatch, ensure_ascii=False)))

        # 分组分页 → 全量卡
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                drv.execute_script('arguments[0].click();', el)
                time.sleep(1.5)
                break
        cards_all = _card_info(drv)
        rendered_all = {c['name'] for c in cards_all}
        missing_all = [n for n in group_counts if n not in rendered_all]
        footer = drv.execute_script('''
          const btns = [...document.querySelectorAll('button')].map(b=>b.textContent.trim()).filter(t=>t.includes('个分组'));
          const ps = [...document.querySelectorAll('p')].map(p=>p.textContent.trim()).filter(t=>t.includes('个分组'));
          return {btns, ps};
        ''')
        log('ALL CARDS(%d) missing=%s footer=%s' % (len(cards_all), json.dumps(missing_all, ensure_ascii=False), json.dumps(footer, ensure_ascii=False)))
        if missing_all:
            ok = False
            reasons.append('missing groups after load-more: %s' % json.dumps(missing_all, ensure_ascii=False))
        if count_mismatch:
            ok = False
            reasons.append('badge count mismatch: %s' % json.dumps(count_mismatch, ensure_ascii=False))

        # ---- 找部分覆盖分组 ----
        partial = [n for n in group_counts
                   if loaded_by_group.get(n, 0) > 0 and loaded_by_group.get(n, 0) < group_counts[n]]
        log('PARTIAL groups: %s' % json.dumps(partial, ensure_ascii=False))
        if not partial:
            ok = False
            reasons.append('no partial-coverage group found to verify P1')
        # 优先话轮接管（审计复现组），否则取任一 partial
        p1_group = '话轮接管' if '话轮接管' in partial else (partial[0] if partial else '话轮接管')
        p1_count = group_counts.get(p1_group, 0)
        p1_id = group_ids.get(p1_group, '')
        p1_loaded = loaded_by_group.get(p1_group, 0)
        log('P1 TARGET group=%s count=%d id=%s first-screen-loaded=%d' % (p1_group, p1_count, p1_id, p1_loaded))

        # ---- P1 核心：展开部分覆盖分组 → 按分组懒加载 ----
        if p1_id:
            _drain(drv)
            clicked = _click_group(drv, p1_group)
            lazy_fired, lazy_reqs = _poll_lazy(
                drv, p1_id,
                lambda url: 'page=1' in url and 'per_page=20' in url,
                timeout=25)
            log('EXPAND %s clicked=%s lazy-page1-fired=%s lazy-requests=%s'
                % (p1_group, clicked, lazy_fired, json.dumps([(u.replace(base, ''), s) for u, s in lazy_reqs], ensure_ascii=False)))
            if not lazy_fired:
                ok = False
                reasons.append('partial group expand did NOT fire per-group lazy page=1 (P1 regression)')

            # 组内懒加载按钮计数 = 服务端 total（= test_case_count）
            btn1 = None
            deadline = time.time() + 25
            while time.time() < deadline and btn1 is None:
                btn1 = _lazy_btn_text(drv)
                if btn1 is None:
                    time.sleep(0.7)
            log('EXPAND %s lazy-button="%s" expect total=%d' % (p1_group, btn1, p1_count))
            btn_total_ok = bool(btn1) and ('/ %d 条' % p1_count) in btn1
            if not btn_total_ok:
                ok = False
                reasons.append('partial group lazy button total != group count: "%s" expect / %d 条' % (btn1, p1_count))

            # 点「加载更多」→ 服务端翻页（page=2）且已显示 > 首屏已加载
            _drain(drv)
            page2_fired = False
            revealed = False
            reveal_threshold = p1_loaded + 1 if p1_loaded > 0 else 1
            last_btn = btn1
            paging_seen = []
            for _ in range(25):
                _click_lazy_more(drv, timeout=2)
                time.sleep(0.7)
                for url, status in _lazy_req_urls(drv, _net(drv)):
                    if ('group_id=' + p1_id) in url and 'page=2' in url:
                        page2_fired = True
                        paging_seen.append((url, status))
                btn = _lazy_btn_text(drv)
                if btn is None:
                    revealed = True
                    last_btn = '(none - fully loaded)'
                    break
                m = re.search(r'已显示 (\d+) / (\d+) 条', btn)
                if m and int(m.group(1)) >= reveal_threshold:
                    revealed = True
                last_btn = btn
                if page2_fired and revealed:
                    break
            for url, status in paging_seen:
                log('  lazy paging GET %s -> %s' % (url.replace(base, ''), status))
            log('P1 LOAD-MORE page2-fired=%s revealed-beyond-first-screen=%s threshold=%d final="%s"'
                % (page2_fired, revealed, reveal_threshold, last_btn))
            if not page2_fired:
                ok = False
                reasons.append('partial group lazy did not flip to server page=2 on 加载更多')
            if not revealed:
                ok = False
                reasons.append('partial group could not reveal beyond first-screen slice (loaded=%d)' % p1_loaded)

            # 截图（浅色 + 深色，部分覆盖分组展开态）
            _set_theme(drv, 'light')
            drv.get(base + '/start-test?step=0&view=table')
            _wait_cards(drv)
            time.sleep(1.5)
            _click_group(drv, p1_group)
            _wait_text(drv, '条 · 加载更多', timeout=20)
            time.sleep(2)
            drv.save_screenshot(os.path.join(ARTIFACTS, 'p1-partial-light.png'))
            _set_theme(drv, 'dark')
            drv.get(base + '/start-test?step=0&view=table')
            _wait_cards(drv)
            time.sleep(1.5)
            _click_group(drv, p1_group)
            _wait_text(drv, '条 · 加载更多', timeout=20)
            time.sleep(2)
            drv.save_screenshot(os.path.join(ARTIFACTS, 'p1-partial-dark.png'))
            log('screenshots p1-partial light+dark saved')

        # ---- 回归：零覆盖分组展开懒加载 ----
        zero_loaded = [n for n in group_counts if loaded_by_group.get(n, 0) == 0 and group_counts[n] > 0]
        log('ZERO-loaded non-empty groups: %s' % json.dumps(zero_loaded, ensure_ascii=False))
        if zero_loaded:
            z_group = zero_loaded[0]
            z_id = group_ids.get(z_group, '')
            _drain(drv)
            _click_group(drv, z_group)
            _wait_text(drv, '条 · 加载更多', timeout=20)
            time.sleep(2)
            z_hit, z_lazy = _poll_lazy(drv, z_id, lambda url: True, timeout=8)
            log('ZERO group %s expand lazy-fired=%s lazy-reqs=%s'
                % (z_group, z_hit, json.dumps([(u.replace(base, ''), s) for u, s in z_lazy], ensure_ascii=False)))
            if not z_lazy:
                ok = False
                reasons.append('zero-covered group %s expand did not lazy-load' % z_group)

        # ---- 回归：空分组空态（test_case_count=0）----
        empty_groups = [n for n in group_counts if group_counts[n] == 0]
        log('EMPTY groups(count=0): %s' % json.dumps(empty_groups, ensure_ascii=False))
        if empty_groups:
            e_group = empty_groups[0]
            e_id = group_ids.get(e_group, '')
            # 确保空分组卡可见（默认每页 5 组、按 count 降序，count=0 组不在首屏）
            for el in drv.find_elements(By.TAG_NAME, 'button'):
                if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                    drv.execute_script('arguments[0].click();', el)
                    time.sleep(1.5)
                    break
            _drain(drv)
            clicked_e = _click_group(drv, e_group)
            _wait_text(drv, '该分组暂无用例', timeout=15)
            time.sleep(1.5)
            e_hit, e_lazy = _poll_lazy(drv, e_id, lambda url: True, timeout=5)
            log('EMPTY group %s expand clicked=%s empty-state=%s lazy-requests=%d'
                % (e_group, clicked_e, '该分组暂无用例' in _body_text(drv), len(e_lazy)))
            if '该分组暂无用例' not in _body_text(drv):
                ok = False
                reasons.append('empty group %s did not show empty-state (clicked=%s)' % (e_group, clicked_e))

        # ---- /testcases/by-group 同组件回归 ----
        _drain(drv)
        drv.get(base + '/testcases/by-group')
        t_ok = _wait_cards(drv)
        log('testcases cards rendered=%s' % t_ok)
        time.sleep(2)
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                drv.execute_script('arguments[0].click();', el)
                time.sleep(1.5)
                break
        cards_t = _card_info(drv)
        t_names = {c['name'] for c in cards_t}
        missing_t = [n for n in group_counts if n not in t_names]
        log('TESTCASES CARDS(%d) missing=%s' % (len(cards_t), json.dumps(missing_t, ensure_ascii=False)))
        if missing_t:
            ok = False
            reasons.append('testcases missing groups: %s' % json.dumps(missing_t, ensure_ascii=False))
        if p1_id:
            _drain(drv)
            _click_group(drv, p1_group)
            tc_lazy, tc_lazy_reqs = _poll_lazy(
                drv, p1_id,
                lambda url: 'page=1' in url and 'per_page=20' in url,
                timeout=25)
            log('TESTCASES expand %s lazy-fired=%s lazy-requests=%s'
                % (p1_group, tc_lazy, json.dumps([(u.replace(base, ''), s) for u, s in tc_lazy_reqs], ensure_ascii=False)))
            if not tc_lazy:
                ok = False
                reasons.append('testcases expand partial group did not lazy-load')

        db_pre_shot = _health('pre-screenshot')

    finally:
        try:
            drv.quit()
        except Exception:
            pass

    if db_start != 'intelligent_audio_test' or db_pre_shot != 'intelligent_audio_test':
        ok = False
        reasons.append('cross-db! start=%s pre-screenshot=%s' % (db_start, db_pre_shot))

    log('ASSERT OK=%s %s' % (ok, ('; '.join(reasons) if reasons else 'all passed')))
    with open(os.path.join(ARTIFACTS, 'evidence.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(LOG) + '\n')
    log('evidence -> %s' % os.path.join(ARTIFACTS, 'evidence.txt'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
