# -*- coding: utf-8 -*-
"""INT-2391 验收：报告中心 → 点行 → 详情 → 导出，固化「环境卡死」判据实测。

判据本体在 `tests/ui/utils/report_detail_stall.py`（单一入口 ensure_report_step），
本脚本是它在报告详情跳转与导出两处的接入与证据采集：
  - 同一 Selenium 会话逐轮跑「/tasks → /testcases → /report-center → 点行 → 详情 → 导出」，
    复现 INT-2386 里「完整链路跑完前置页后首次点报告行」的传输层卡死条件；
  - 详情步骤、导出步骤各调用一次 ensure_report_step（详情/导出的重试只有这一份）；
  - 汇总：卡死命中次数 / 恢复成功次数 / 真实失败次数 / 每轮耗时；
  - `--inject` 人为构造真回归（详情接口真实 404、路由 chunk 被 block），必须判 regression。

阈值（与判据模块一致，INT-2391 验收第 4 条）：
  OBSERVE_TIMEOUT_S = 3.0 秒；MAX_RECOVERIES = 1 次（整页恢复上限）。

跑法：
  python tests/ui/verify_int2391_report_detail_stall.py --loop 10
  python tests/ui/verify_int2391_report_detail_stall.py --inject detail-500
  python tests/ui/verify_int2391_report_detail_stall.py --inject chunk-block
环境（负责人 2026-10-23 铁律）：docker 后端 http://localhost:15000（/health 必须
database=intelligent_audio_test）、前端 http://localhost:15173；不起本地栈。
"""
import argparse
import json
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from utils.report_detail_stall import (  # noqa: E402
    MAX_RECOVERIES, OBSERVE_TIMEOUT_S, describe_thresholds, ensure_report_step)

ART_ROOT = os.path.join(HERE, 'artifacts', 'int2391')
CHROME_BINARY = os.environ.get(
    'UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

LOG = []


def log(msg):
    line = '[int2391] %s' % msg
    print(line, flush=True)
    LOG.append(line)


def make_driver(download_dir):
    opts = Options()
    opts.binary_location = CHROME_BINARY
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu',
              '--no-sandbox', '--lang=zh-CN', '--disable-dev-shm-usage'):
        opts.add_argument(a)
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    drv = webdriver.Chrome(options=opts)
    drv.set_page_load_timeout(90)
    try:
        drv.execute_cdp_cmd('Network.enable', {})
    except Exception:
        pass
    try:
        drv.execute_cdp_cmd('Page.setDownloadBehavior',
                            {'behavior': 'allow', 'downloadPath': download_dir})
    except Exception:
        pass
    return drv


def body_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : ""') or ''


def click_js(drv, el):
    drv.execute_script('arguments[0].click()', el)


def visible_buttons(drv, texts):
    out = []
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if b.is_displayed() and (b.text or '').strip() in texts:
                out.append(b)
        except Exception:
            continue
    return out


def login(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 40).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    time.sleep(1.0)
    u = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
         if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
    p = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
         if e.is_displayed()][0]
    u.clear(); u.send_keys(USERNAME)
    p.clear(); p.send_keys(PASSWORD)
    btns = [b for b in drv.find_elements(By.TAG_NAME, 'button')
            if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
    if not btns:
        btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[type=submit]')
                if b.is_displayed()]
    click_js(drv, btns[-1])
    WebDriverWait(drv, 45).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(2.5)


def prelude(drv, base, full=True):
    """复现日巡链路 2/3 的前置访问（同一会话）。

    full=False 时只回报告中心：多轮复跑里前置页已在同一会话访问过，不必每轮重走。
    """
    if full:
        for path in ('/tasks', '/testcases'):
            drv.get(base + path)
            time.sleep(2.5)
            body_text(drv)
    drv.get(base + '/report-center')
    WebDriverWait(drv, 60).until(
        lambda d: len([r for r in d.find_elements(By.CSS_SELECTOR, 'tbody tr')
                       if r.is_displayed()]) > 0)
    time.sleep(2.0)
    log('前置页完成，报告中心行已渲染')


def pick_report_id(drv):
    m = re.search(r'/report/(\d+)', drv.current_url or '')
    if m:
        return m.group(1)
    return None


def open_first_row(drv):
    rows = [r for r in drv.find_elements(By.CSS_SELECTOR, 'tbody tr') if r.is_displayed()]
    if not rows:
        raise AssertionError('报告中心无行')
    click_js(drv, rows[0])


def export_click(drv):
    """打开导出弹窗 → 选 html → 点「导出」。返回是否点到了主按钮。"""
    exp = visible_buttons(drv, ('导出', '导出报告', 'HTML 导出'))
    if not exp:
        exp = [b for b in drv.find_elements(By.TAG_NAME, 'button')
               if b.is_displayed() and '导出' in (b.text or '')]
    if not exp:
        return False
    click_js(drv, exp[0])
    time.sleep(2.5)
    dlgs = [x for x in drv.find_elements(By.CSS_SELECTOR, '[role=dialog]') if x.is_displayed()]
    scope = dlgs[-1] if dlgs else drv
    combo = [b for b in scope.find_elements(By.CSS_SELECTOR, '[role=combobox], button')
             if b.is_displayed()
             and (b.text or '').strip().lower() in ('csv', 'excel', 'pdf', 'html', 'json')]
    if combo:
        click_js(drv, combo[0])
        time.sleep(1.5)
        opts = [e for e in drv.find_elements(By.CSS_SELECTOR, '[role=option], [role=menuitem]')
                if e.is_displayed() and (e.text or '').strip().lower().startswith('html')]
        if opts:
            click_js(drv, opts[0])
        time.sleep(0.8)
    mains = [b for b in scope.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and (b.text or '').strip() == '导出']
    if not mains:
        return False
    click_js(drv, mains[-1])
    return True


# ── 人为构造真回归（验收第 3 条的反证）────────────────────────────────
# 注意：页内 fetch 打点（返回合成 500）在 Network 上**不产生请求**，与传输层卡死
# 在观测上不可区分，不能用来验证判据。真回归必须在网络层构造：
#   detail-missing → 真实 404（详情接口 4xx）
#   chunk-block    → 懒加载 chunk 被浏览器 block（ERR_BLOCKED_BY_CLIENT + 控制台报错）
def inject_detail_missing(drv, base):
    """直接打开一个不存在的报告 id：详情接口真实 404 → 必须判 regression。"""
    log('注入：打开不存在的报告 /report/999999999（真实 404）')
    drv.get(base + '/report/999999999')


def inject_chunk_block(drv):
    """在浏览器层 block 路由 chunk（懒加载 JS）→ 详情组件必然渲染不出来。"""
    drv.execute_cdp_cmd('Network.setBlockedURLs',
                        {'urls': ['*/static/js/async/*', '*/assets/*async*',
                                  '*/static/js/*.js', '*/assets/*.js']})
    log('注入：block 路由懒加载 chunk（*/static/js/async/*、*/assets/*.js）')


def clear_injection(drv):
    try:
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    except Exception:
        pass


# ── 单轮 ────────────────────────────────────────────────────────────────
def run_once(drv, base, idx, inject):
    t0 = time.time()
    rec = {'idx': idx, 'inject': inject}
    prelude(drv, base, full=(idx == 1))
    if inject == 'detail-missing':
        rid = '999999999'
        trigger = lambda: inject_detail_missing(drv, base)  # noqa: E731
    else:
        if inject == 'chunk-block':
            # 注入必须在点击之前：详情请求在 SPA 导航的同一帧就发出
            inject_chunk_block(drv)
        rid = None
        trigger = lambda: open_first_row(drv)  # noqa: E731

    detail = ensure_report_step(drv, 'detail', rid, trigger=trigger, logger=log)
    obs = detail.get('observations') or [{}]
    rec['report_id'] = obs[-1].get('url_report_id')
    rec['detail'] = _slim(detail)
    if detail['ok']:
        rrid = rec['report_id'] or rid
        export = ensure_report_step(drv, 'export', rrid,
                                    click=lambda: export_click(drv), logger=log)
        rec['export'] = _slim(export)
    else:
        rec['export'] = {'ok': False, 'status': 'skipped',
                         'reason': '详情未达成，导出不适用'}
    rec['elapsed_s'] = round(time.time() - t0, 2)
    clear_injection(drv)
    return rec


def _slim(res):
    out = {k: res.get(k) for k in ('ok', 'status', 'recovered', 'recoveries',
                                   'elapsed_s', 'reason')}
    out['observations'] = [
        {k: o.get(k) for k in ('step', 'url', 'url_has_report', 'detail_mounted',
                               'verdict', 'reason', 'elapsed_s')}
        for o in (res.get('observations') or [])
    ]
    # 观测到的网络证据只留关键几条，便于评论引用
    out['evidence'] = []
    for o in (res.get('observations') or []):
        for r in (o.get('detail_hits') or []) + (o.get('export_hits') or [])[:3]:
            out['evidence'].append({'url': r.get('url'), 'status': r.get('status'),
                                    'failed': r.get('failed'), 'error': r.get('error')})
        for e in (o.get('console_errors') or [])[:2]:
            out['evidence'].append({'console': str(e.get('message'))[:160]})
    return out


def summarize(records):
    total = len(records)
    detail_stall = sum(1 for r in records if r['detail'].get('status') == 'env_stall_recovered')
    detail_unrec = sum(1 for r in records if r['detail'].get('status') == 'env_stall_unrecovered')
    detail_reg = sum(1 for r in records if r['detail'].get('status') == 'regression')
    export_stall = sum(1 for r in records if r['export'].get('status') == 'env_stall_recovered')
    export_unrec = sum(1 for r in records if r['export'].get('status') == 'env_stall_unrecovered')
    export_reg = sum(1 for r in records if r['export'].get('status') == 'regression')
    det = {
        'runs': total,
        'env_stall_hits': detail_stall + detail_unrec,
        'recovered_ok': detail_stall,
        'real_failures': detail_reg + detail_unrec,
        'regressions': detail_reg,
        'durations_s': [r['elapsed_s'] for r in records],
    }
    exp = {
        'env_stall_hits': export_stall + export_unrec,
        'recovered_ok': export_stall,
        'real_failures': export_reg + export_unrec,
        'regressions': export_reg,
    }
    ok_runs = sum(1 for r in records
                  if r['detail'].get('ok') and r['export'].get('ok'))
    return {'detail': det, 'export': exp, 'all_ok_runs': ok_runs,
            'thresholds': describe_thresholds()}


def _write(args, records):
    """每轮落盘，长循环被外部超时截断也能拿到已完成轮次的证据。"""
    payload = {'base': args.base, 'api': args.api, 'inject': args.inject,
               'thresholds': {'observe_timeout_s': OBSERVE_TIMEOUT_S,
                              'max_recoveries': MAX_RECOVERIES,
                              'text': describe_thresholds()},
               'summary': summarize(records), 'records': records}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--loop', type=int, default=1)
    ap.add_argument('--inject', default='none',
                    choices=('none', 'detail-missing', 'chunk-block'))
    ap.add_argument('--out', default=os.path.join(ART_ROOT, 'int2391_result.json'))
    args = ap.parse_args()
    os.makedirs(ART_ROOT, exist_ok=True)
    os.makedirs(os.path.join(ART_ROOT, 'downloads'), exist_ok=True)
    log('阈值：%s' % describe_thresholds())

    drv = make_driver(os.path.join(ART_ROOT, 'downloads'))
    records = []
    try:
        login(drv, args.base.rstrip('/'))
        log('登录完成：%s' % drv.current_url)
        for i in range(1, args.loop + 1):
            try:
                rec = run_once(drv, args.base.rstrip('/'), i, args.inject)
            except Exception as exc:
                rec = {'idx': i, 'inject': args.inject, 'error': '%s: %s' % (
                    type(exc).__name__, str(exc)[:300]), 'elapsed_s': None,
                    'detail': {'ok': False, 'status': 'harness_error'},
                    'export': {'ok': False, 'status': 'skipped'}}
            records.append(rec)
            _write(args, records)
            log('第 %d/%d 轮：详情=%s(%s) 导出=%s(%s) 耗时 %ss'
                % (i, args.loop, rec['detail'].get('status'), rec['detail'].get('reason', '')[:60],
                   rec['export'].get('status'), rec['export'].get('reason', '')[:60],
                   rec.get('elapsed_s')))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    summary = summarize(records)
    payload = {'base': args.base, 'api': args.api, 'inject': args.inject,
               'thresholds': {'observe_timeout_s': OBSERVE_TIMEOUT_S,
                              'max_recoveries': MAX_RECOVERIES,
                              'text': describe_thresholds()},
               'summary': summary, 'records': records}
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    log('汇总：%s' % json.dumps(summary, ensure_ascii=False))
    log('结果文件：%s' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
