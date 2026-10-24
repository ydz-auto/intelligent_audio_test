# -*- coding: utf-8 -*-
"""INT-1731 验收：批量专属参数/播放设备/声压/噪声四窗「轮次范围」按选中用例真实轮次。

前置：真实栈后端 :15000（库 intelligent_audio_test），前端可用 REACT_BASE 指向交付构建
（旁路容器 15247，bundle index.4f72d09ea2）；A/B 对照把 REACT_BASE 指向旧镜像 :15173。

断言（对本卡验收标准逐条）：
  ① 四窗「指定轮次（统一设置）」网格只出真实轮次（两条 2 轮夹具 → 第1轮/第2轮，无第3/4轮）
  ② 四窗「逐轮设置」Tab 同样只出真实轮次
  ③ 声压窗只勾第2轮提交 → POST /testcases/batch roundNumbers=[2]；
     回读 rounds[0].audios[0].spl 不动（65）、rounds[1].audios[0].spl 生效（88）
  ④ 浅色 + 深色各四窗截图
只用本 run 自建夹具（_copy 后缀，id 见 --ids），收尾由调用方清理。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1731')
API_BASE = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# (bulk button label, dialog title, data-testid 前缀)
WINDOWS = [
    ('批量设置专属参数', '批量设置用例专属参数', 'batch-algo-params-round'),
    ('批量设置播放设备', '批量设置播放设备', 'batch-device-round'),
    ('批量设置声压', '批量设置声压级', 'batch-spl-round'),
    ('批量设置噪声', '批量设置噪声', 'batch-noise-round'),
]
ROUND_RE = re.compile(r'^第(\d+)轮$')


def api_get(path):
    with urllib.request.urlopen(API_BASE + path, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))['data']


def api_spls(case_id):
    d = api_get('/api/v1/testcases/' + case_id)
    out = []
    for r in (d.get('config') or {}).get('rounds') or []:
        audios = r.get('audios') or []
        out.append(audios[0].get('spl') if audios else None)
    return out


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
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
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def collect_requests(drv):
    reqs = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'),
                    'url': req.get('url') or '',
                    'status': None,
                    'postData': req.get('postData') or '',
                }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
    except Exception:
        pass
    return list(reqs.values())


def wait_for(cond, timeout=30, desc='condition', interval=0.4):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            v = cond()
            if v:
                return v
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(interval)
    raise AssertionError('timeout waiting for %s (%r)' % (desc, last))


def set_input(drv, el, value):
    drv.execute_script(
        "const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
        el, value)


def _visible_dialog(drv, title):
    xpath = "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '%s')]]" % title
    for el in drv.find_elements(By.XPATH, xpath):
        if el.is_displayed():
            return el
    return None


def any_dialog_visible(drv):
    return any(e.is_displayed() for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))


def click_label(drv, scope, text):
    els = scope.find_elements(By.XPATH, ".//label[normalize-space(.)='%s']" % text)
    for el in els:
        if el.is_displayed():
            drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
            time.sleep(0.25)
            drv.execute_script('arguments[0].click();', el)
            return True
    # 兼容按钮样式的 Tab（逐轮设置）
    els = scope.find_elements(By.XPATH, ".//button[normalize-space(.)='%s']" % text)
    for el in els:
        if el.is_displayed():
            drv.execute_script('arguments[0].click();', el)
            return True
    raise AssertionError('label not found: ' + text)


def round_labels_in(drv, dlg, kind=None):
    """对话框内可见的「第N轮」标签（网格 Checkbox / 逐轮 Tab 都算），返回 (序号列表, 原始文本)。"""
    if kind is not None:
        panels = dlg.find_elements(By.CSS_SELECTOR, "[data-testid='%s-specific-rounds']" % kind)
        scopes = [p for p in panels if p.is_displayed()] or [dlg]
    else:
        scopes = [dlg]
    texts = []
    for sc in scopes:
        for el in sc.find_elements(By.XPATH, ".//*[self::label or self::button]"):
            if not el.is_displayed():
                continue
            t = (el.text or '').strip()
            if ROUND_RE.match(t):
                texts.append(t)
    nums = [int(ROUND_RE.match(t).group(1)) for t in texts]
    return nums, texts


def open_dialog(drv, bulk_label, title):
    btn = wait_for(
        lambda: next((b for b in drv.find_elements(By.XPATH, "//button[normalize-space(.)='%s']" % bulk_label)
                      if b.is_displayed()), None),
        20, 'bulk button ' + bulk_label)
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
    time.sleep(0.3)
    drv.execute_script('arguments[0].click();', btn)
    dlg = wait_for(lambda: _visible_dialog(drv, title), 20, 'dialog ' + title)
    time.sleep(0.6)
    return _visible_dialog(drv, title) or dlg


def close_dialog(drv, dlg, title):
    for el in dlg.find_elements(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]"):
        if el.is_displayed():
            drv.execute_script('arguments[0].click();', el)
            break
    else:
        raise AssertionError('cancel button not found: ' + title)
    wait_for(lambda: not any_dialog_visible(drv), 15, 'dialog closed ' + title)
    time.sleep(0.4)


def prepare_page(drv, base, theme, group_name):
    drv.get(base + '/')
    time.sleep(1)
    drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", arguments[0])', theme)
    drv.get(base + '/testcases/by-group')
    time.sleep(2)
    drv.get(base + '/testcases/by-group')
    # 等搜索框（列表加载可慢，实测 40~60s）
    box = wait_for(lambda: next((e for e in drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
                                 if e.is_displayed()), None), 90, 'search box')
    time.sleep(1)
    set_input(drv, box, '_copy')
    time.sleep(3)

    # 分组默认折叠，卡片只在展开后渲染——展开夹具所在分组
    header = wait_for(lambda: next(
        (h for h in drv.find_elements(
            By.XPATH, "//div[contains(@class,'cursor-pointer')][.//span[contains(@class,'font-medium')]]")
         if group_name in (h.text or '')), None), 60, 'group header ' + group_name)
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', header)
    time.sleep(0.5)
    drv.execute_script('arguments[0].click();', header)

    def cards():
        els = drv.find_elements(By.XPATH, "//*[starts-with(@aria-label,'选择 ') and not(@aria-label='全选')]")
        return [e for e in els if e.is_displayed() and (e.get_attribute('aria-label') or '').endswith('_copy')]

    wait_for(lambda: len(cards()) >= 2, 90, 'two fixture cards')

    # 勾选本 run 的两条夹具（按 aria-label 精确名匹配 _copy 结尾）
    picked = 0
    for el in cards():
        name = el.get_attribute('aria-label') or ''
        if not name.endswith('_copy'):
            continue
        if el.get_attribute('aria-checked') in ('true', 'mixed'):
            picked += 1
            continue
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
        time.sleep(0.2)
        drv.execute_script('arguments[0].click();', el)
        time.sleep(0.3)
        picked += 1
    wait_for(lambda: picked >= 2, 10, 'select two fixtures')
    wait_for(lambda: '个用例已选择' in drv.find_element(By.TAG_NAME, 'body').text, 20, 'bulk bar')
    time.sleep(0.5)
    return picked


def probe_window(drv, bulk_label, title, kind, shot_prefix):
    dlg = open_dialog(drv, bulk_label, title)
    click_label(drv, dlg, '指定轮次（统一设置）')
    time.sleep(0.5)
    nums_specific, texts_specific = round_labels_in(drv, _visible_dialog(drv, title), kind)
    drv.save_screenshot(os.path.join(ARTIFACTS, '%s_specific.png' % shot_prefix))
    click_label(drv, _visible_dialog(drv, title), '逐轮设置（每轮可不同）')
    time.sleep(0.5)
    nums_per, texts_per = round_labels_in(drv, _visible_dialog(drv, title))
    drv.save_screenshot(os.path.join(ARTIFACTS, '%s_per_round.png' % shot_prefix))
    close_dialog(drv, _visible_dialog(drv, title), title)
    return {
        'window': title,
        'specific': texts_specific,
        'per_round': texts_per,
        'specific_nums': nums_specific,
        'per_round_nums': nums_per,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.environ.get('REACT_BASE', 'http://127.0.0.1:15247'))
    ap.add_argument('--ids', default='3357ba09-4346-4e0b-b85e-13d41c720a80,8134f38c-31e8-4604-91b3-41cc20174575')
    ap.add_argument('--probe-only', action='store_true', help='只核对轮次标签（A/B 对照旧镜像用）')
    ap.add_argument('--tag', default='new')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    ids = [x for x in args.ids.split(',') if x]
    os.makedirs(ARTIFACTS, exist_ok=True)

    before = {i: api_spls(i) for i in ids}
    group_name = api_get('/api/v1/testcases/' + ids[0]).get('group_name')
    print('readback before:', json.dumps(before, ensure_ascii=True))
    print('fixture group:', group_name.encode('unicode_escape').decode())

    drv = _driver()
    out = {'base': base, 'tag': args.tag, 'before': before, 'windows': []}
    try:
        drv.set_page_load_timeout(90)
        picked = prepare_page(drv, base, 'light', group_name)
        print('selected fixtures:', picked)

        # ① ② 浅色四窗
        for bulk_label, title, kind in WINDOWS:
            r = probe_window(drv, bulk_label, title, kind, 'light_%s' % kind)
            print('light', json.dumps(r, ensure_ascii=True))
            out['windows'].append(r)

        if args.probe_only:
            out['ok'] = all(sorted(w['specific_nums']) == [1, 2] and sorted(w['per_round_nums']) == [1, 2]
                            for w in out['windows'])
            print('PROBE', json.dumps(out, ensure_ascii=True))
            return 0 if out['ok'] else 2

        # ③ 提交：声压窗只勾第2轮
        drv.get_log('performance')  # drain
        dlg = open_dialog(drv, '批量设置声压', '批量设置声压级')
        click_label(drv, dlg, '指定轮次（统一设置）')
        time.sleep(0.5)
        dlg = _visible_dialog(drv, '批量设置声压级')
        before_checked = {}
        for n in (1, 2):
            panel = dlg.find_element(By.CSS_SELECTOR, "[data-testid='batch-spl-round-specific-rounds']")
            lab = panel.find_element(By.XPATH, ".//label[normalize-space(.)='第%d轮']" % n)
            cb = lab.find_element(By.XPATH, ".//*[@role='checkbox']")
            before_checked[n] = cb.get_attribute('aria-checked')
        print('specific checked before:', before_checked)
        # 取消第1轮、勾上第2轮
        for n, target in ((1, 'false'), (2, 'true')):
            dlg = _visible_dialog(drv, '批量设置声压级')
            panel = dlg.find_element(By.CSS_SELECTOR, "[data-testid='batch-spl-round-specific-rounds']")
            lab = panel.find_element(By.XPATH, ".//label[normalize-space(.)='第%d轮']" % n)
            cb = lab.find_element(By.XPATH, ".//*[@role='checkbox']")
            if cb.get_attribute('aria-checked') != target:
                drv.execute_script('arguments[0].click();', cb)
                time.sleep(0.4)
        dlg = _visible_dialog(drv, '批量设置声压级')
        panel = dlg.find_element(By.CSS_SELECTOR, "[data-testid='batch-spl-round-specific-rounds']")
        after_checked = {n: panel.find_element(By.XPATH, ".//label[normalize-space(.)='第%d轮']" % n)
                         .find_element(By.XPATH, ".//*[@role='checkbox']").get_attribute('aria-checked')
                         for n in (1, 2)}
        print('specific checked after:', after_checked)
        assert after_checked == {1: 'false', 2: 'true'}, after_checked
        drv.save_screenshot(os.path.join(ARTIFACTS, 'submit_only_round2.png'))

        num = dlg.find_element(By.XPATH, ".//input[@type='number']")
        set_input(drv, num, '88')
        time.sleep(0.6)
        ok_btn = dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]")
        assert not ok_btn.get_attribute('disabled'), '确定钮禁用（声压值未入状态）'
        drv.execute_script('arguments[0].click();', ok_btn)
        wait_for(lambda: not any_dialog_visible(drv), 20, 'spl dialog closed')
        time.sleep(2.5)

        reqs = collect_requests(drv)
        batch = [r for r in reqs if '/api/v1/testcases/batch' in r['url'] and r['method'] == 'POST']
        out['batch_posts'] = batch
        print('batch POST:', [(r['url'], r['status'], r['postData'][:300]) for r in batch])

        after = {}
        for i in ids:
            try:
                wait_for(lambda c=i: api_spls(c) == [65.0, 88.0], 25, 'readback ' + i, interval=0.5)
            except AssertionError:
                pass
            after[i] = api_spls(i)
        out['after'] = after
        print('readback after:', json.dumps(after, ensure_ascii=True))

        # ④ 深色四窗
        picked = prepare_page(drv, base, 'dark', group_name)
        for bulk_label, title, kind in WINDOWS:
            r = probe_window(drv, bulk_label, title, kind, 'dark_%s' % kind)
            print('dark', json.dumps(r, ensure_ascii=True))
            out['windows'].append(r)

        # 判定
        ok = True
        for w in out['windows']:
            if sorted(w['specific_nums']) != [1, 2]:
                ok = False
            if sorted(w['per_round_nums']) != [1, 2]:
                ok = False
        if not batch:
            ok = False
        elif batch[0]['status'] is None or batch[0]['status'] >= 400:
            ok = False
        body = ((batch[0]['postData'] if batch else '') or '').replace(' ', '')
        # infrastructure 层 camelCase→snake_case：断言真实载荷只含第 2 轮
        if '"round_numbers":[2]' not in body:
            ok = False
        for i in ids:
            if after[i] != [65.0, 88.0]:
                ok = False
        out['ok'] = ok
        print('RESULT', json.dumps(out, ensure_ascii=True))
        return 0 if ok else 2
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
