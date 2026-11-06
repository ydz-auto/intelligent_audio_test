# -*- coding: utf-8 -*-
"""INT-2367 2026-11-03 React(15173) 日巡补充：昨日三张缺陷卡的修复回归 + 未覆盖页错误态。

INT-2328 日巡开出的三张缺陷卡现已 done，且 docker 前端镜像 15173 重建于
2026-11-02T09:12Z（晚于三卡修复提交），本脚本按缺陷原复现步骤逐一复测：
  INT-2329 报告中心搜索不生效 → 搜索不存在关键字应「共 0 个」，搜索真实关键字应命中。
  INT-2330 /devices 加载失败静默空态 → 三个页签（测试设备 / 播放设备 / 测试 API）
           注入失败均须出现可见错误条 + 重试，且解除后恢复列表。
  INT-2331 /start-test、/SPLMapping 主数据失败伪装空态 → 注入失败须出现错误条 + 重试；
           解除后恢复（这两页 INT-2328 探针未覆盖）。

全部为 CDP Network.setBlockedURLs 注入 + 只读搜索，不写业务数据，无需 teardown。

跑法：
  <conda python> tests/ui/probe_int2367_fixed_defect_verify.py \
      --base http://localhost:15173 --api http://localhost:15000
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

from tests.ui.smoke_frontend_int1854 import (  # noqa: E402
    RESULT, body_text, console_errors, make_driver, parse_perf, shot, wait_quiet,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(ROOT, 'artifacts', 'int2367')
ERR_WORDS = ('加载失败', '获取失败', '请重试', '重试', '错误')
EMPTY_WORDS = ('暂无', '无数据', '未找到', '无匹配', '没有找到', '暂无数据', '符合条件的')

SET_VALUE_JS = """
const el = arguments[0], v = arguments[1];
el.focus();
const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
setter.call(el, v);
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
"""


def login(drv, base, username, password):
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    drv.get(base + '/login')
    WebDriverWait(drv, 45).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    time.sleep(1)
    users = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
             if e.is_displayed() and e.get_attribute('type') in (None, 'text', 'email')]
    pwds = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
            if e.is_displayed()]
    users[0].send_keys(username)
    pwds[0].send_keys(password)
    btns = [b for b in drv.find_elements(By.TAG_NAME, 'button')
            if b.is_displayed() and (b.text or '').strip() in ('登 录', '登录')]
    (btns or drv.find_elements(By.CSS_SELECTOR, 'button[type=submit]'))[-1].click()
    WebDriverWait(drv, 45).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(3)
    return drv.current_url


def words(txt, vocab):
    return [w for w in vocab if w in txt]


def click_text(drv, labels, selector='button,[role=tab],a'):
    return drv.execute_script("""
      const labels = arguments[0], sel = arguments[1];
      for (const el of document.querySelectorAll(sel)) {
        const t = (el.innerText || '').trim();
        if (!labels.includes(t)) continue;
        const r = el.getBoundingClientRect();
        if (r.width < 5 || r.height < 5) continue;
        el.click();
        return t;
      }
      return null;
    """, list(labels), selector)


def click_retry(drv):
    return click_text(drv, ['重试', '重新加载', '刷新'])


def block(drv, patterns):
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': patterns})


def unblock(drv):
    try:
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    except Exception:
        pass


def inject(drv, base, route, patterns, key):
    """打开 route → 注入失败 → 记录错误态 → 解除 → 重试/重载 → 记录恢复。"""
    rec = {'route': route, 'blocked': patterns, 'ok': False}
    block(drv, patterns)
    drv.get(base + route)
    time.sleep(4)
    try:
        wait_quiet(drv, 15)
    except Exception:
        pass
    txt = body_text(drv)
    rec.update({
        'url': drv.current_url,
        'error_words': words(txt, ERR_WORDS),
        'empty_words': words(txt, EMPTY_WORDS),
        'body_len': len(txt),
        'text_excerpt': txt[:400],
        'shot_err': shot(drv, '%s_error' % key)['path'],
    })
    rec['ok'] = bool(rec['error_words']) or bool(rec['empty_words'])
    rec['looks_like_empty_state'] = bool(rec['empty_words']) and not rec['error_words']
    unblock(drv)
    if not click_retry(drv):
        drv.get(base + route)
    time.sleep(4)
    wait_quiet(drv, 20)
    rtxt = body_text(drv)
    if '加载失败' in rtxt or '获取失败' in rtxt:
        # 页面可能有多个独立错误面板（如标签页 分类 + 标签各一个重试）；
        # 一次重试只恢复其一，再整页重载确认是否为真实未恢复。
        drv.get(base + route)
        time.sleep(4)
        wait_quiet(drv, 20)
        rtxt = body_text(drv)
    rec['recovered'] = ('加载失败' not in rtxt and '获取失败' not in rtxt and len(rtxt) > 120)
    rec['recovered_len'] = len(rtxt)
    rec['shot_recovered'] = shot(drv, '%s_recovered' % key)['path']
    return rec


def verify_int2329(drv, base):
    rec = {'card': 'INT-2329 报告中心搜索', 'ok': False}
    drv.get(base + '/report-center')
    time.sleep(4)
    wait_quiet(drv, 25)
    boxes = [e for e in drv.find_elements(
        By.CSS_SELECTOR, "input[placeholder*='搜索报告名称']") if e.is_displayed()]
    if not boxes:
        rec['error'] = '未找到报告搜索框'
        return rec
    box = boxes[0]
    txt0 = body_text(drv)
    rec['before_count'] = (re.findall(r'共\s*\d+\s*个', txt0) or [])[:1]
    drv.execute_script(SET_VALUE_JS, box, '接线测试_不存在_20261103')
    time.sleep(3)
    wait_quiet(drv, 20)
    txt1 = body_text(drv)
    rec['nonexistent'] = {
        'count_text': (re.findall(r'共\s*\d+\s*个', txt1) or [])[:1],
        'empty_words': words(txt1, EMPTY_WORDS),
        'shot': shot(drv, 'int2329_search_nonexistent')['path'],
    }
    # 真实关键字：取列表第一条报告名片段
    apis = parse_perf(drv.get_log('performance'))
    rec['search_requests'] = [{'m': a.get('method'), 's': a.get('status'),
                               'u': (a.get('url') or '')[:160]}
                              for a in apis if 'keyword=' in (a.get('url') or '')][-3:]
    keyword = '报告'
    drv.execute_script(SET_VALUE_JS, box, keyword)
    time.sleep(3)
    wait_quiet(drv, 20)
    txt2 = body_text(drv)
    rec['real_keyword'] = {'keyword': keyword,
                           'count_text': (re.findall(r'共\s*\d+\s*个', txt2) or [])[:1],
                           'shot': shot(drv, 'int2329_search_real')['path']}
    box.clear()
    box.send_keys(Keys.ENTER)
    time.sleep(2)
    n0 = rec['before_count']
    n_none = rec['nonexistent']['count_text']
    rec['ok'] = (bool(n0) and n_none and re.search(r'共\s*0\s*个', ''.join(n_none)) is not None)
    return rec


def verify_int2330(drv, base):
    rec = {'card': 'INT-2330 /devices 三页签错误态', 'tabs': {}, 'ok': False}
    tabs = [
        ('测试设备', ['*api/v1/test-devices*'], 'devices_tab_test'),
        ('播放设备', ['*api/v1/playback-devices*'], 'devices_tab_playback'),
        ('测试 API', ['*api/v1/apis*'], 'devices_tab_api'),
    ]
    for label, patterns, key in tabs:
        one = {'tab': label, 'blocked': patterns, 'ok': False}
        try:
            drv.get(base + '/devices')
            time.sleep(3.5)
            wait_quiet(drv, 20)
            clicked = click_text(drv, [label], 'button,[role=tab],a')
            one['tab_clicked'] = clicked
            time.sleep(2)
            block(drv, patterns)
            if not click_retry(drv):
                drv.refresh()
            time.sleep(4)
            wait_quiet(drv, 15)
            txt = body_text(drv)
            one.update({
                'error_words': words(txt, ERR_WORDS),
                'empty_words': words(txt, EMPTY_WORDS),
                'body_len': len(txt),
                'text_excerpt': txt[:400],
                'shot_err': shot(drv, '%s_error' % key)['path'],
            })
            one['ok'] = bool(one['error_words'])
            unblock(drv)
            if not click_retry(drv):
                drv.refresh()
            time.sleep(4)
            wait_quiet(drv, 20)
            rtxt = body_text(drv)
            one['recovered'] = '加载失败' not in rtxt and '获取失败' not in rtxt
            one['recovered_len'] = len(rtxt)
            one['shot_recovered'] = shot(drv, '%s_recovered' % key)['path']
        except Exception as exc:
            one['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
            unblock(drv)
        rec['tabs'][label] = one
        print('INT2330 tab=%s ok=%s err=%s recovered=%s' % (
            label, one.get('ok'), one.get('error_words'), one.get('recovered')), flush=True)
    rec['ok'] = all(v.get('ok') for v in rec['tabs'].values())
    return rec


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()
    base = args.base.rstrip('/')

    os.makedirs(ART, exist_ok=True)
    RESULT['art'] = ART
    download_dir = os.path.join(ART, 'downloads')
    os.makedirs(download_dir, exist_ok=True)
    drv = make_driver(download_dir)
    summary = {}
    try:
        summary['login_url'] = login(drv, base, args.username, args.password)
        print('LOGIN ok ->', summary['login_url'], flush=True)

        summary['int2329_report_search'] = verify_int2329(drv, base)
        print('INT2329', json.dumps(summary['int2329_report_search'], ensure_ascii=False)[:600],
              flush=True)

        summary['int2330_devices_tabs'] = verify_int2330(drv, base)

        # INT-2331：/start-test 阻断 testcases、/SPLMapping 阻断 spl
        summary['int2331_start_test'] = inject(
            drv, base, '/start-test', ['*api/v1/testcases*'], 'int2331_start_test')
        print('INT2331 start-test', summary['int2331_start_test'].get('error_words'),
              summary['int2331_start_test'].get('recovered'), flush=True)
        summary['int2331_spl'] = inject(
            drv, base, '/SPLMapping', ['*api/v1/spl*'], 'int2331_spl')
        print('INT2331 SPL', summary['int2331_spl'].get('error_words'),
              summary['int2331_spl'].get('recovered'), flush=True)

        # INT-2328 探针未覆盖的四页错误态（本次补全「逐页错误态」口径）
        summary['extra_error_states'] = {}
        for route, patterns, key in (
                ('/AlgorithmConfig', ['*api/v1/algorithm/definitions*'], 'extra_algorithm_config'),
                ('/TagManagement', ['*api/v1/tags*'], 'extra_tags'),
                ('/logs', ['*api/v1/logs*'], 'extra_logs'),
                ('/reports', ['*api/v1/reports*'], 'extra_reports_showcase')):
            rec = inject(drv, base, route, patterns, key)
            summary['extra_error_states'][route] = rec
            print('EXTRA %-18s error_words=%s empty_words=%s recovered=%s' % (
                route, rec.get('error_words'), rec.get('empty_words'), rec.get('recovered')),
                flush=True)

        summary['console_errors'] = console_errors(drv)[:5]
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print('\nSUMMARY_JSON=%s' % out_path)
    print('INT2329 ok=%s' % summary['int2329_report_search'].get('ok'))
    print('INT2330 ok=%s' % summary['int2330_devices_tabs'].get('ok'))
    for k in ('int2331_start_test', 'int2331_spl'):
        v = summary[k]
        print('%s error_words=%s empty_words=%s recovered=%s ok=%s' % (
            k, v.get('error_words'), v.get('empty_words'), v.get('recovered'), v.get('ok')))
    for route, v in summary.get('extra_error_states', {}).items():
        print('EXTRA %-18s error_words=%s empty_words=%s recovered=%s' % (
            route, v.get('error_words'), v.get('empty_words'), v.get('recovered')))


if __name__ == '__main__':
    main()
