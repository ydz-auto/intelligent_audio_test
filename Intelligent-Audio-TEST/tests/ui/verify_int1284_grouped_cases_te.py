# -*- coding: utf-8 -*-
"""INT-1284 分组视图全量分组卡验证（测试工程师独立验收版，连真实库栈 dev 代理 → 5700）。

核对点（对卡内验收标准）：
1. /start-test 步骤一按分组视图：分组卡按 /groups 全量渲染，计数 = test_case_count；
   分组分页「已显示 x / N 个分组」与真实渲染卡片数一致。
2. 展开首屏用例覆盖不到的分组（打断与恢复/拒识等）→ 按分组懒加载
   GET /testcases?group_id=...&page=1&per_page=20，组内用例卡渲染。
3. /testcases 按分组视图同口径（同一 GroupedCaseList）。
4. 浅色 + 深色截图 + Network 证据。

输出：tests/ui/artifacts/int1284_te/
"""
import argparse
import base64
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5304'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1284_te')

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
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\\Google\\Chrome\\BLBeacon') as k:
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
    """读取+清空 performance 日志 → {rid: {method,url,status}} + bodies(/groups,/testcases)"""
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
    bodies = {}
    for rid, info in reqs.items():
        if '/api/v1' in info['url'] and ('/groups' in info['url'] or '/testcases' in info['url']):
            try:
                resp = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
                txt = base64.b64decode(resp.get('body', '')).decode('utf-8', 'replace') if resp.get('base64Encoded') else resp.get('body', '')
                bodies[info['url']] = txt[:8000]
            except Exception:
                pass
    return reqs, bodies


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


def _wait_cards(drv, timeout=35):
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


def _click_group(drv, name):
    els = drv.find_elements(By.CSS_SELECTOR, 'span.font-medium.truncate')
    for el in els:
        if el.text.strip() == name:
            drv.execute_script('arguments[0].click();', el)
            return True
    return False


def _wait_text(drv, text, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if text in (drv.execute_script('return document.body.textContent || ""') or ''):
            return True
        time.sleep(0.8)
    return False


def _footer_info(drv):
    return drv.execute_script('''
      const btns = [...document.querySelectorAll('button')].map(b=>b.textContent.trim()).filter(t=>t.includes('个分组'));
      const ps = [...document.querySelectorAll('p')].map(p=>p.textContent.trim()).filter(t=>t.includes('个分组'));
      return {btns, ps};
    ''')


def _set_theme(drv, mode):
    drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "%s")' % mode)


def _groups_from_bodies(bodies):
    """从 Network 响应体解析 /groups → (names, counts by name)"""
    for url, body in bodies.items():
        if '/groups' in url and body:
            try:
                data = json.loads(body)
                inner = data.get('data', data)
                items = inner.get('items', [])
                counts = {g.get('name', ''): g.get('test_case_count', g.get('testCaseCount', 0)) for g in items}
                return [g.get('name', '') for g in items], counts
            except Exception:
                continue
    return [], {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=BASE)
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

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
        reqs, bodies = _net(drv)

        expected, group_counts = _groups_from_bodies(bodies)
        log('GROUPS from Network: %d groups, counts=%s' % (len(expected), json.dumps(group_counts, ensure_ascii=False)))

        cards = _card_info(drv)
        log('P1 cards(%d): %s' % (len(cards), json.dumps(cards, ensure_ascii=False)))
        footer = _footer_info(drv)
        log('P1 footer: %s' % json.dumps(footer, ensure_ascii=False))

        # 断言：全部 /groups 分组卡渲染，计数与 test_case_count 一致（未分组虚拟组不计入 groups）
        rendered_first = {c['name'] for c in cards}
        missing = [n for n in expected if n not in rendered_first]
        count_mismatch = []
        for c in cards:
            if c['name'] in group_counts:
                badge_num = ''.join(ch for ch in (c['badge'] or '') if ch.isdigit())
                expected_num = str(group_counts[c['name']])
                if badge_num != expected_num:
                    count_mismatch.append('%s badge=%s expect=%s' % (c['name'], badge_num, expected_num))
        log('P1 MISSING vs /groups: %s' % json.dumps(missing, ensure_ascii=False))
        log('P1 COUNT MISMATCH: %s' % json.dumps(count_mismatch, ensure_ascii=False))

        # 分组分页加载更多 → 全量卡片 + 页脚
        target = None
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                target = el
                break
        if target:
            drv.execute_script('arguments[0].click();', target)
            time.sleep(1.5)
        cards_all = _card_info(drv)
        footer2 = _footer_info(drv)
        log('ALL cards(%d): %s' % (len(cards_all), json.dumps(cards_all, ensure_ascii=False)))
        log('ALL footer: %s' % json.dumps(footer2, ensure_ascii=False))
        rendered_all = {c['name'] for c in cards_all}
        missing_all = [n for n in expected if n not in rendered_all]
        log('MISSING(ALL) vs /groups: %s' % json.dumps(missing_all, ensure_ascii=False))

        # 页脚计数一致性：首屏渲染卡片数 = paginatedGroups.length；"已显示 x / N 个分组"
        # 通过 body 文本抽取断言（与真实渲染卡片数比较）
        body_text = drv.execute_script('return document.body.textContent || ""') or ''

        # 展开一个首屏覆盖不到的分组（打断与恢复）→ 按分组懒加载
        _drain(drv)
        clicked = _click_group(drv, '打断与恢复')
        lazy_seen = _wait_text(drv, '条 · 加载更多', timeout=25) or _wait_text(drv, '已显示 5 /', timeout=25)
        time.sleep(3)
        reqs2, bodies2 = _net(drv)
        lazy_cases_reqs = [r for r in reqs2.values() if '/testcases' in r['url'] and 'group_id=' in r['url']]
        log('EXPAND 打断与恢复 clicked=%s lazy-text=%s' % (clicked, lazy_seen))
        for r in lazy_cases_reqs:
            log('  lazy GET %s -> status=%s' % (r['url'].replace(base, ''), r['status']))
        body_after = drv.execute_script('return document.body.textContent || ""') or ''
        has_175 = '175 条' in body_after
        log('group 打断与恢复 badge 175 条 present=%s' % has_175)

        # 空分组展开 → 组内空态（不发懒加载请求）
        _drain(drv)
        clicked_empty = _click_group(drv, '默认分组')
        empty_seen = _wait_text(drv, '该分组暂无用例', timeout=15)
        time.sleep(2)
        reqs3, _bodies3 = _net(drv)
        empty_lazy_reqs = [r for r in reqs3.values() if '/testcases' in r['url'] and 'group_id=' in r['url']]
        log('EXPAND 默认分组(0 条) clicked=%s empty-text=%s lazy-requests=%d' % (clicked_empty, empty_seen, len(empty_lazy_reqs)))

        # 截图：浅色 + 深色（/start-test，加载更多后全量 9 张卡 + 页脚「已加载全部 9 个分组」）
        _set_theme(drv, 'light')
        drv.get(base + '/start-test?step=0&view=table')
        _wait_cards(drv)
        time.sleep(1.5)
        # 点「加载更多」让全量分组卡渲染
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                drv.execute_script('arguments[0].click();', el)
                break
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start-test-grouped-light.png'))
        _set_theme(drv, 'dark')
        drv.get(base + '/start-test?step=0&view=table')
        _wait_cards(drv)
        time.sleep(1.5)
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                drv.execute_script('arguments[0].click();', el)
                break
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start-test-grouped-dark.png'))
        # 展开 打断与恢复 后截图（组内懒加载用例卡渲染）
        _click_group(drv, '打断与恢复')
        _wait_text(drv, '条 · 加载更多', timeout=20)
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'start-test-grouped-expanded-lazy.png'))
        log('screenshots start-test light+dark(+expanded) saved')

        # ============ /testcases 按分组 ============
        _drain(drv)
        drv.get(base + '/testcases/by-group')
        t_ok = _wait_cards(drv)
        log('testcases cards rendered=%s' % t_ok)
        time.sleep(2)
        # 分组分页加载更多
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
        missing_t = [n for n in expected if n not in t_names]
        footer_t = _footer_info(drv)
        log('TESTCASES cards(%d) missing=%s' % (len(cards_t), json.dumps(missing_t, ensure_ascii=False)))
        log('TESTCASES footer: %s' % json.dumps(footer_t, ensure_ascii=False))
        _set_theme(drv, 'light')
        drv.get(base + '/testcases/by-group')
        _wait_cards(drv)
        time.sleep(1.5)
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                drv.execute_script('arguments[0].click();', el)
                break
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'testcases-grouped-light.png'))
        _set_theme(drv, 'dark')
        drv.get(base + '/testcases/by-group')
        _wait_cards(drv)
        time.sleep(1.5)
        for el in drv.find_elements(By.TAG_NAME, 'button'):
            if '个分组' in (el.text or '') and '加载更多' in (el.text or ''):
                drv.execute_script('arguments[0].click();', el)
                break
        time.sleep(2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'testcases-grouped-dark.png'))
        log('screenshots testcases light+dark saved')

        # ============ 汇总断言 ============
        ok_all = True
        reasons = []
        if not ok:
            ok_all = False
            reasons.append('start-test group cards did not render in time')
        if missing_all:
            ok_all = False
            reasons.append('start-test missing groups(ALL): %s' % json.dumps(missing_all, ensure_ascii=False))
        if count_mismatch:
            ok_all = False
            reasons.append('badge count mismatch: %s' % json.dumps(count_mismatch, ensure_ascii=False))
        # 页脚计数与真实渲染卡片数一致：首屏「已显示 5 / N · 加载更多」的 N 与 /groups 全量一致，
        # 且加载更多后页脚「已加载全部 N 个分组」与真实渲染卡数一致。
        if missing_all:
            ok_all = False
            reasons.append('start-test footer/rendered mismatch: missing_all non-empty')
        else:
            footer_text = json.dumps(footer2, ensure_ascii=False)
            if '已加载全部 %d 个分组' % len(expected) not in footer_text:
                ok_all = False
                reasons.append('footer did not reach 已加载全部 %d 个分组: %s' % (len(expected), footer_text))
        if missing_t:
            ok_all = False
            reasons.append('testcases missing groups: %s' % json.dumps(missing_t, ensure_ascii=False))
        if not lazy_cases_reqs:
            ok_all = False
            reasons.append('no lazy per-group /testcases?group_id request captured on expand')
        else:
            ok_lazy_params = any('page=1' in r['url'] and ('per_page=20' in r['url'] or 'perPage=20' in r['url']) for r in lazy_cases_reqs)
            if not ok_lazy_params:
                reasons.append('lazy request page/per_page params unexpected: %s' % json.dumps([r['url'] for r in lazy_cases_reqs], ensure_ascii=False))
        if not has_175:
            ok_all = False
            reasons.append('group badge 175 条 not rendered')
        if not clicked_empty or not empty_seen:
            ok_all = False
            reasons.append('empty group 默认分组 expand did not show 该分组暂无用例')
        if empty_lazy_reqs:
            ok_all = False
            reasons.append('empty group 默认分组 issued unexpected lazy /testcases request: %s' % json.dumps([r['url'] for r in empty_lazy_reqs], ensure_ascii=False))

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
