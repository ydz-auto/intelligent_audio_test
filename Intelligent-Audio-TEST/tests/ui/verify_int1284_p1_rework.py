# -*- coding: utf-8 -*-
"""INT-1284 P1 返工验证（审计打回：部分覆盖分组展开不发懒加载，组内余量不可达）。

连真实库栈 dev 代理 → 5700（/health database=intelligent_audio_test），登录 接线测试_admin。
核对点：
1. /start-test 步骤一按分组：分组卡按 /groups 全量渲染，计数 = test_case_count。
2. P1 核心：部分覆盖分组（话轮接管 count=211，首屏 /testcases 只加载 50）展开 →
   发按分组懒加载 GET /testcases?group_id=...&page=1&per_page=20（lazy>0），
   组内计数以服务端 total 为准（已显示 x / 211 条，非旧实现的 5 / 50）；
   「加载更多」翻服务端页（page=2）→ 组内余量可达。
3. 零覆盖分组（打断与恢复 175）展开 → 懒加载渲染（回归不复现）。
4. /testcases 按分组同口径（同一 GroupedCaseList）。
5. 浅色 + 深色截图 + Network 证据。

输出：tests/ui/artifacts/int1284_p1_rework/
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
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1284_p1_rework')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'

LOG = []


def log(msg):
    LOG.append(msg)
    try:
        print(msg)
    except Exception:
        pass


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
    cands = []
    if chrome_major and os.path.isdir(cache_root):
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
    return webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())


def _drain(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def _net(drv):
    """读取+清空 performance 日志 → {rid: {method,url,status}}"""
    reqs = {}
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            params = (msg.get('message') or {}).get('params') or {}
            method = (msg.get('message') or {}).get('method') or ''
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            r = params.get('request') or {}
            reqs[params.get('requestId')] = {'method': r.get('method', 'GET'), 'url': r.get('url', ''), 'status': None}
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            if rid in reqs:
                reqs[rid]['status'] = (params.get('response') or {}).get('status')
    return reqs


def _card_info(drv):
    """分组卡组名 + 计数 Badge（组头 span.font-medium.truncate + span.rounded-md 首个）"""
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
        time.sleep(0.8)
    return False


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def _wait_text(drv, text, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if text in _body_text(drv):
            return True
        time.sleep(0.8)
    return False


def _click_group(drv, name):
    els = drv.find_elements(By.CSS_SELECTOR, 'span.font-medium.truncate')
    for el in els:
        if el.text.strip() == name:
            drv.execute_script('arguments[0].click();', el)
            return True
    return False


def _click_lazy_more(drv, timeout=3):
    """点组内「已显示 x / y 条 · 加载更多」（JS click，区分分组分页「个分组」按钮）"""
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


def _lazy_btn_text(drv):
    btns = drv.find_elements(By.TAG_NAME, 'button')
    for b in btns:
        t = (b.text or '').strip()
        if '条 · 加载更多' in t and '个分组' not in t:
            return t
    return None


def _set_theme(drv, mode):
    drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "%s")' % mode)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=BASE)
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    db_start = _health('start')

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(base + '/login')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1)
        drv.find_element(By.ID, 'username').send_keys(USERNAME)
        drv.find_element(By.ID, 'password').send_keys(PASSWORD)
        drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(drv, 20).until(lambda d: '/dashboard' in d.current_url)
        time.sleep(2)
        log('LOGIN OK -> ' + drv.current_url)

        # ============ /start-test 步骤一 按分组 ============
        _drain(drv)
        t0 = time.time()
        drv.get(base + '/start-test?step=0&view=table')
        ok = _wait_cards(drv)
        log('start-test group cards rendered=%s after %ss' % (ok, round(time.time() - t0, 1)))
        time.sleep(2)
        reqs = _net(drv)

        # /groups 响应体 → 分组名 + 计数
        groups_payload = {}
        for rid, info in reqs.items():
            if '/api/v1/groups' in info['url']:
                try:
                    resp = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
                    txt = base64.b64decode(resp.get('body', '')).decode('utf-8', 'replace') if resp.get('base64Encoded') else resp.get('body', '')
                    groups_payload = json.loads(txt)
                except Exception:
                    pass
        inner = groups_payload.get('data', groups_payload) if groups_payload else {}
        group_items = inner.get('items', []) if isinstance(inner, dict) else []
        group_counts = {g.get('name', ''): g.get('test_case_count', g.get('testCaseCount', 0)) for g in group_items}
        group_ids = {g.get('name', ''): g.get('id', '') for g in group_items}
        log('GROUPS total=%d counts=%s' % (len(group_items), json.dumps(group_counts, ensure_ascii=False)))

        # 首屏 /testcases → 每分组已加载条数
        loaded_by_group = {}
        tc_urls = [info['url'] for rid, info in reqs.items() if '/api/v1/testcases' in info['url'] and 'group_id=' not in info['url']]
        log('TESTCASES first-screen URL count=%d %s' % (len(tc_urls), json.dumps([u.replace(base, '') for u in tc_urls], ensure_ascii=False)))
        for rid, info in reqs.items():
            if '/api/v1/testcases' in info['url'] and 'group_id=' not in info['url']:
                try:
                    resp = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
                    txt = base64.b64decode(resp.get('body', '')).decode('utf-8', 'replace') if resp.get('base64Encoded') else resp.get('body', '')
                    data = json.loads(txt)
                    inner = data.get('data', data)
                    for c in inner.get('items', []):
                        gname = c.get('group_name') or c.get('groupName') or ''
                        loaded_by_group[gname] = loaded_by_group.get(gname, 0) + 1
                except Exception as e:
                    log('  testcases body parse ERR %s -> %r' % (info['url'].replace(base, ''), e))
        log('TESTCASES first-screen loaded-by-group=%s' % json.dumps(loaded_by_group, ensure_ascii=False))

        partial = [n for n in group_counts if loaded_by_group.get(n, 0) > 0 and loaded_by_group.get(n, 0) < group_counts[n]]
        full = [n for n in group_counts if loaded_by_group.get(n, 0) >= group_counts[n]]
        zero = [n for n in group_counts if loaded_by_group.get(n, 0) == 0]
        log('PARTIAL groups: %s' % json.dumps(partial, ensure_ascii=False))
        log('FULL groups: %s' % json.dumps(full, ensure_ascii=False))
        log('ZERO groups: %s' % json.dumps(zero, ensure_ascii=False))

        # 分组卡渲染 + 计数
        cards = _card_info(drv)
        rendered = {c['name'] for c in cards}
        missing = [n for n in group_counts if n not in rendered]
        count_mismatch = []
        for c in cards:
            if c['name'] in group_counts:
                badge_num = ''.join(ch for ch in (c['badge'] or '') if ch.isdigit())
                expected_num = str(group_counts[c['name']])
                if badge_num != expected_num:
                    count_mismatch.append('%s badge=%s expect=%s' % (c['name'], badge_num, expected_num))
        log('CARDS(%d) missing=%s count_mismatch=%s' % (len(cards), json.dumps(missing, ensure_ascii=False), json.dumps(count_mismatch, ensure_ascii=False)))

        # 分组分页加载更多 → 全量卡片
        target = None
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                target = el
                break
        if target:
            drv.execute_script('arguments[0].click();', target)
            time.sleep(1.5)
        cards_all = _card_info(drv)
        rendered_all = {c['name'] for c in cards_all}
        missing_all = [n for n in group_counts if n not in rendered_all]
        footer = drv.execute_script('''
          const btns = [...document.querySelectorAll('button')].map(b=>b.textContent.trim()).filter(t=>t.includes('个分组'));
          const ps = [...document.querySelectorAll('p')].map(p=>p.textContent.trim()).filter(t=>t.includes('个分组'));
          return {btns, ps};
        ''')
        log('ALL CARDS(%d) missing=%s footer=%s' % (len(cards_all), json.dumps(missing_all, ensure_ascii=False), json.dumps(footer, ensure_ascii=False)))

        # ============ P1 核心：部分覆盖分组展开 → 按分组懒加载 ============
        p1_group = partial[0] if partial else '话轮接管'
        p1_count = group_counts.get(p1_group, 0)
        p1_id = group_ids.get(p1_group, '')
        log('P1 TARGET group=%s count=%s id=%s loaded=%s' % (p1_group, p1_count, p1_id, loaded_by_group.get(p1_group, 0)))

        _drain(drv)
        clicked = _click_group(drv, p1_group)
        lazy_fired = False
        lazy_page1 = None
        # 等待懒加载请求出现（组内 query page=1 per_page=20）
        deadline = time.time() + 20
        while time.time() < deadline:
            reqs2 = _net(drv)
            for r in reqs2.values():
                if '/testcases' in r['url'] and 'group_id=' in r['url']:
                    lazy_fired = True
                    lazy_page1 = r
            if lazy_fired:
                break
            time.sleep(0.6)
        time.sleep(3)
        reqs2 = _net(drv)
        lazy_reqs = [r for r in reqs2.values() if '/testcases' in r['url'] and 'group_id=' in r['url']]
        for r in lazy_reqs:
            log('  lazy GET %s -> status=%s' % (r['url'].replace(base, ''), r['status']))
        log('EXPAND %s clicked=%s lazy-fired=%s lazy-reqs=%d' % (p1_group, clicked, lazy_fired, len(lazy_reqs)))

        # 组内懒加载按钮计数：应为「已显示 5 / <服务端 total> 条」（部分覆盖 = 组计数，非旧实现 5 / 已加载条数）
        btn1 = None
        deadline = time.time() + 20
        while time.time() < deadline and btn1 is None:
            btn1 = _lazy_btn_text(drv)
            if btn1 is None:
                time.sleep(0.8)
        log('EXPAND %s lazy-button="%s"' % (p1_group, btn1))
        p1_btn_total_ok = bool(btn1) and ('/ %d 条' % p1_count) in btn1

        # 点「加载更多」反复：① 缓存（每页 20）耗尽后触发服务端翻页（page=2 请求）
        # ② 已显示条数翻越首屏已加载条数（组内余量可达）
        _drain(drv)
        page2_fired = False
        revealed = False
        reveal_threshold = min(loaded_by_group.get(p1_group, 0) + 1, p1_count)
        last_btn = btn1
        for _ in range(22):
            _click_lazy_more(drv, timeout=2)
            time.sleep(0.8)
            reqsN = _net(drv)
            for r in reqsN.values():
                if '/testcases' in r['url'] and 'group_id=' in r['url']:
                    if 'page=2' in r['url']:
                        page2_fired = True
                    log('  lazy paging GET %s -> status=%s' % (r['url'].replace(base, ''), r['status']))
            btn = _lazy_btn_text(drv)
            if btn is None:
                # 组内全部加载完 → 按钮消失（全部可达）
                revealed = True
                break
            m = re.search(r'已显示 (\d+) / (\d+) 条', btn)
            if m and int(m.group(1)) >= reveal_threshold:
                revealed = True
            last_btn = btn
            if page2_fired and revealed:
                break
        log('P1 LOAD-MORE page2-fired=%s revealed-beyond-first-screen=%s threshold=%d final-lazy-button="%s"'
            % (page2_fired, revealed, reveal_threshold, last_btn))

        # 截图：部分覆盖分组展开（浅色 + 深色）
        _set_theme(drv, 'light')
        drv.get(base + '/start-test?step=0&view=table')
        _wait_cards(drv)
        time.sleep(1.5)
        _click_group(drv, p1_group)
        _wait_text(drv, '条 · 加载更多', timeout=20)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1-partial-group-light.png'))
        _set_theme(drv, 'dark')
        drv.get(base + '/start-test?step=0&view=table')
        _wait_cards(drv)
        time.sleep(1.5)
        _click_group(drv, p1_group)
        _wait_text(drv, '条 · 加载更多', timeout=20)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'p1-partial-group-dark.png'))
        log('screenshots p1-partial light+dark saved')

        # 零覆盖分组（打断与恢复 175）展开 → 懒加载回归
        zero_group = next((n for n in zero if group_counts.get(n, 0) > 0), None)
        if zero_group:
            _drain(drv)
            _click_group(drv, zero_group)
            _wait_text(drv, '条 · 加载更多', timeout=20)
            time.sleep(2)
            reqs_z = _net(drv)
            zero_lazy = [r for r in reqs_z.values() if '/testcases' in r['url'] and 'group_id=' in r['url']]
            log('ZERO group %s expand lazy-reqs=%d' % (zero_group, len(zero_lazy)))
            for r in zero_lazy[:3]:
                log('  lazy GET %s -> %s' % (r['url'].replace(base, ''), r['status']))

        # ============ /testcases 按分组（同一 GroupedCaseList） ============
        _drain(drv)
        drv.get(base + '/testcases/by-group')
        t_ok = _wait_cards(drv)
        log('testcases cards rendered=%s' % t_ok)
        time.sleep(2)
        # 分组分页加载更多 → 全量卡片
        target_t = None
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                target_t = el
                break
        if target_t:
            drv.execute_script('arguments[0].click();', target_t)
            time.sleep(1.5)
        cards_t = _card_info(drv)
        t_names = {c['name'] for c in cards_t}
        missing_t = [n for n in group_counts if n not in t_names]
        log('TESTCASES CARDS(%d) missing=%s' % (len(cards_t), json.dumps(missing_t, ensure_ascii=False)))
        # 展开同一部分覆盖分组 → 懒加载
        _drain(drv)
        _click_group(drv, p1_group)
        deadline = time.time() + 20
        tc_lazy = False
        while time.time() < deadline:
            reqs_t = _net(drv)
            if any('/testcases' in r['url'] and 'group_id=' in r['url'] for r in reqs_t.values()):
                tc_lazy = True
                break
            time.sleep(0.6)
        time.sleep(2)
        log('TESTCASES expand %s lazy-fired=%s' % (p1_group, tc_lazy))

        db_pre_shot = _health('pre-screenshot')

        # ============ 汇总断言 ============
        ok_all = True
        reasons = []
        if db_start != 'intelligent_audio_test' or db_pre_shot != 'intelligent_audio_test':
            ok_all = False
            reasons.append('cross-db! start=%s pre-shot=%s' % (db_start, db_pre_shot))
        if not ok:
            ok_all = False
            reasons.append('start-test group cards did not render')
        if missing_all:
            ok_all = False
            reasons.append('missing groups(all): %s' % json.dumps(missing_all, ensure_ascii=False))
        if count_mismatch:
            ok_all = False
            reasons.append('badge count mismatch: %s' % json.dumps(count_mismatch, ensure_ascii=False))
        if not partial:
            ok_all = False
            reasons.append('no partial-coverage group found to verify P1')
        if not lazy_fired:
            ok_all = False
            reasons.append('partial group expand did NOT fire per-group lazy request (P1 regression)')
        if not p1_btn_total_ok:
            ok_all = False
            reasons.append('partial group lazy button total != group count: "%s" expect / %d 条' % (btn1, p1_count))
        if not page2_fired:
            ok_all = False
            reasons.append('partial group lazy did not flip to server page=2 on 加载更多')
        if not revealed:
            ok_all = False
            reasons.append('partial group could not reveal beyond first-screen slice')
        if missing_t:
            ok_all = False
            reasons.append('testcases missing groups: %s' % json.dumps(missing_t, ensure_ascii=False))
        if not tc_lazy:
            ok_all = False
            reasons.append('testcases expand partial group did not lazy-load')

        log('ASSERT OK=%s %s' % (ok_all, ('; '.join(reasons) if reasons else 'all passed')))
        with open(os.path.join(ARTIFACTS, 'evidence.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(LOG) + '\n')
        log('evidence -> %s' % os.path.join(ARTIFACTS, 'evidence.txt'))
        return 0 if ok_all else 1
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
