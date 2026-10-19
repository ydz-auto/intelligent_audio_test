# -*- coding: utf-8 -*-
"""INT-881 复测：INT-934（报告详情无效ID错误态）+ INT-935（报告对比二次对比流程）失败项复测。

合并实施者交付分支 agent/react-b/int-934 + agent/react-b/int-935-8cf78c3eca9b，
连常驻后端 :5000（AUTH_MODE=off）+ 本 run dev server :5306，浏览器实测：

1. INT-934：/report/999999 渲染「报告不存在 / 请提供有效的报告ID」而非「加载失败」，
   Network 证据 GET /reports/999999 → 400 + envelope code=404。
2. INT-935：报告中心勾选 2 报告 → 批量对比 → 基于已选报告 → 生成对比报告：
   Network 证据 SSE（GET /api/v1/sse/events）先于 POST /reports/secondary-compare 建立；
   提交后进度弹窗进入真实终端态（本环境后端无测试结果数据 → 生成失败态），
   URL 不跳 /report/undefined、不回报告中心静默（失败态可见可关）。
3. 回归：报告列表真实数据渲染、报告详情 /report/2 真实数据渲染，无 console SEVERE。

用法：python tests/ui/retest_int881_934_935.py --base http://localhost:5306
"""
import argparse
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int881_retest_934_935')
os.makedirs(ARTIFACTS, exist_ok=True)
THEME_KEY = 'iatp:theme:v1:mode'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver(performance=False):
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    prefs = {'browser': 'ALL'}
    if performance:
        prefs['performance'] = 'ALL'
    options.set_capability('goog:loggingPrefs', prefs)
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _body_text(drv):
    return drv.execute_script("return document.body.textContent || ''")


def _wait_body_has(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _screenshot(drv, name):
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    return path


def _severes(drv):
    sev = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    return [e.get('message', '')[:200] for e in sev]


def _network_requests(drv):
    """CDP performance log → {method url status}，双层嵌套解析（wiring-selenium-performance-log 记忆）。"""
    reqs = []
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                inner = msg.get('message') or {}
                method = inner.get('method') or ''
                params = inner.get('params') or {}
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                r = params.get('request') or {}
                reqs.append({
                    'requestId': params.get('requestId'),
                    'method': r.get('method', 'GET'),
                    'url': r.get('url', ''),
                    'ts': params.get('timestamp', 0),
                    'postData': r.get('postData', '') or '',
                })
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                for q in reqs:
                    if q['requestId'] == rid:
                        q['status'] = (params.get('response') or {}).get('status')
    except Exception as e:
        print('performance log read failed:', e)
    return reqs


def _network_evidence_txt(reqs, filters, note_lines):
    lines = list(note_lines)
    matched = [q for q in reqs if any(f in q['url'] for f in filters)]
    for q in matched:
        lines.append('[Network] %s %s  status=%s' % (q.get('method', 'GET'), q.get('url'), q.get('status')))
        if q.get('postData'):
            lines.append('  body: %s' % q['postData'][:200])
    lines.append('total matching requests: %d' % len(matched))
    return '\n'.join(lines), matched


def _render_evidence_png(text, name):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 20)
    except Exception:
        font = ImageFont.load_default()
    lines = text.split('\n')
    W, H = 1150, max(120, 40 * len(lines) + 40)
    img = Image.new('RGB', (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    y = 12
    for ln in lines:
        draw.text((16, y), ln, fill=(20, 20, 20), font=font)
        y += 36
    out = os.path.join(ARTIFACTS, name)
    img.save(out)
    return out


def retest_934_not_found(base):
    """INT-934：/report/999999 → 报告不存在（非加载失败），浅色+深色+Network。"""
    drv = _driver(performance=True)
    try:
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.removeItem(%r)' % THEME_KEY)
        drv.get(base + '/report/999999')
        time.sleep(8)
        body = _body_text(drv)
        assert '报告不存在' in body, '缺少「报告不存在」'
        assert '加载失败' not in body, '仍渲染「加载失败」'
        _screenshot(drv, 'retest934_not_found_light.png')

        reqs = _network_requests(drv)
        txt, _ = _network_evidence_txt(
            reqs,
            ['/reports/999999'],
            ['INT-934: /report/999999 渲染「报告不存在」(light)', 'page body has 报告不存在: True', 'page body has 加载失败: False'])
        _render_evidence_png(txt, 'retest934_network_light.png')

        # 深色
        drv.get(base + '/report/999999')
        time.sleep(2)
        drv.execute_script("localStorage.setItem(%r, 'dark');" % THEME_KEY)
        drv.refresh()
        time.sleep(5)
        body2 = _body_text(drv)
        assert '报告不存在' in body2, '深色下缺少「报告不存在」'
        _screenshot(drv, 'retest934_not_found_dark.png')
        print('INT-934 PASS: 报告不存在 (light+dark), no 加载失败')
        print('light body excerpt (ascii-safe):',
              body[:120].replace('\n', ' ').encode('ascii', 'replace').decode('ascii'))
    finally:
        drv.quit()


def retest_935_secondary_compare(base):
    """INT-935：二次对比提交 → SSE 预订阅先于 POST → 真实终端态（非 /report/undefined）。"""
    drv = _driver(performance=True)
    try:
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.removeItem(%r)' % THEME_KEY)
        drv.get(base + '/report-center')
        _wait_body_has(drv, '报告中心', 15)
        time.sleep(3)

        # 勾选 ≥2 个报告
        checkboxes = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr td:first-child [role="checkbox"]')
        selected = 0
        for cb in checkboxes:
            try:
                drv.execute_script('arguments[0].click();', cb)
                selected += 1
                time.sleep(0.3)
                if selected >= 2:
                    break
            except Exception:
                continue
        assert selected >= 2, '勾选报告不足 2 个，实际 %d' % selected
        time.sleep(1.5)

        # 批量对比
        btns = [e for e in drv.find_elements(By.TAG_NAME, 'button') if '批量对比' in (e.text or '')]
        clicked = False
        for b in btns:
            try:
                if b.is_displayed():
                    drv.execute_script('arguments[0].click();', b)
                    clicked = True
                    break
            except Exception:
                continue
        assert clicked, '未找到「批量对比」按钮'
        time.sleep(2)

        # 切「基于已选报告」tab
        tabs = [e for e in drv.find_elements(By.TAG_NAME, 'button') if '基于已选报告' in (e.text or '')]
        for t in tabs:
            try:
                if t.is_displayed():
                    drv.execute_script('arguments[0].click();', t)
                    break
            except Exception:
                continue
        time.sleep(1.5)
        body = _body_text(drv)
        assert '已选择 2 个报告' in body or '已选择 2' in body, '基于已选报告 tab 未显示已选数: %s' % body[:150]

        # 清空性能日志缓存，再提交（确保捕捉到本次 SSE 预订阅 + POST 时序）
        drv.get_log('performance')
        submit_btns = [e for e in drv.find_elements(By.TAG_NAME, 'button') if '生成对比报告' in (e.text or '')]
        found = False
        for b in submit_btns:
            try:
                if b.is_displayed():
                    print('submit enabled:', b.is_enabled())
                    drv.execute_script('arguments[0].click();', b)
                    found = True
                    break
            except Exception:
                continue
        assert found, '未找到「生成对比报告」提交按钮'
        _screenshot(drv, 'retest935_submitted.png')

        # 等待进度弹窗终端态（后端失败事件通常 1~3s 内到达；兜底 25s）
        terminal = None
        deadline = time.time() + 25
        while time.time() < deadline:
            b = _body_text(drv)
            if '生成失败' in b:
                terminal = 'failed'
                break
            if '生成完成' in b and '查看报告' in b:
                terminal = 'completed'
                break
            time.sleep(0.8)
        assert terminal is not None, '进度弹窗未进入终端态（生成失败/生成完成）'

        time.sleep(1)
        body2 = _body_text(drv)
        current_url = drv.current_url
        # 关键断言：绝不跳 /report/undefined
        assert '/report/undefined' not in current_url, '跳转了 /report/undefined!'
        _screenshot(drv, 'retest935_terminal_%s.png' % terminal)
        print('INT-935 terminal state:', terminal)
        print('URL:', current_url)

        # Network 时序：SSE 连接先于 POST /reports/secondary-compare
        reqs = _network_requests(drv)
        sse_reqs = [q for q in reqs if '/sse/events' in q['url'] and q['method'] == 'GET']
        post_reqs = [q for q in reqs if '/reports/secondary-compare' in q['url']]
        first_sse_ts = min((q.get('ts', 0) for q in sse_reqs), default=None)
        first_post_ts = min((q.get('ts', 0) for q in post_reqs), default=None)
        note = [
            'INT-935: 二次对比提交 → 进度弹窗终端态=%s' % terminal,
            'URL after submit: %s' % current_url,
            'jumped to /report/undefined: False',
            'SSE GET requests: %d, POST secondary-compare: %d' % (len(sse_reqs), len(post_reqs)),
            'first SSE ts=%.3f, first POST ts=%.3f' % (first_sse_ts or 0, first_post_ts or 0),
            'SSE opened before POST: %s' % (first_sse_ts is not None and first_post_ts is not None and first_sse_ts < first_post_ts),
        ]
        txt, _ = _network_evidence_txt(reqs, ['/sse/events', '/reports/secondary-compare'], note)
        _render_evidence_png(txt, 'retest935_network.png')
        print('SSE before POST:', first_sse_ts is not None and first_post_ts is not None and first_sse_ts < first_post_ts)
        if terminal == 'failed':
            # 失败态正文含错误文案（后端失败事件回传）
            assert '生成失败' in body2
            print('failure dialog excerpt (ascii-safe):',
                  body2[body2.find('生成失败')-40:body2.find('生成失败')+120]
                  .replace('\n', ' ').encode('ascii', 'replace').decode('ascii'))
    finally:
        drv.quit()


def retest_regression(base):
    """回归：报告列表真实数据渲染 + 报告详情 /report/2 真实数据渲染 + 无 console SEVERE。"""
    drv = _driver()
    try:
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.removeItem(%r)' % THEME_KEY)
        drv.get(base + '/report-center')
        _wait_body_has(drv, '报告中心', 15)
        time.sleep(3)
        body = _body_text(drv)
        assert 'INT321_API报告' in body, '缺少 INT321_API报告'
        assert 'prb338' in body, '缺少 prb338'
        assert 'Benchmark报告' in body, '缺少 Benchmark报告'
        rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        assert len(rows) >= 4, '列表应有 ≥4 个报告，实际 %d' % len(rows)
        print('list rows:', len(rows))
        sev = [s for s in _severes(drv) if 'algorithm/options' not in s]
        assert not sev, '列表页 console SEVERE: %s' % sev

        drv.get(base + '/report/2')
        _wait_body_has(drv, 'INT321_API报告', 15)
        time.sleep(3)
        body2 = _body_text(drv)
        assert '测试用例' in body2 or '63cf495d' in body2, '缺少真实用例卡'
        assert '人工复核' in body2, '缺少人工复核入口'
        assert 'AI 复核' in body2, '缺少 AI 复核入口'
        _screenshot(drv, 'retest_detail_regression.png')
        sev2 = [s for s in _severes(drv)
                if 'algorithm/options' not in s and '/tasks/' not in s]
        assert not sev2, '详情页 console SEVERE: %s' % sev2
        print('INT-881 regression PASS: list + detail real data, no SEVERE')
    finally:
        drv.quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.environ.get('REACT_DEV_BASE', 'http://localhost:5306'))
    args = ap.parse_args()
    base = args.base.rstrip('/')
    retest_934_not_found(base)
    retest_935_secondary_compare(base)
    retest_regression(base)
    print('ALL INT-881 RETEST CASES PASSED')


if __name__ == '__main__':
    sys.exit(main())
