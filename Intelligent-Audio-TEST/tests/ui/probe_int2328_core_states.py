# -*- coding: utf-8 -*-
"""INT-2328 2026-11-02 React(15173) 日巡补充：核心子页遍历 + 加载/空态/错误态取证。

卡内口径：int1919 五条链路 + int2136 侧栏 20 页之外，「其余 tests/ui 用例按核心页
与关键链路补齐」——本脚本只补两部分，全部只读（不建任务/不发布/不改库）：

  ① 核心子页遍历（侧栏二级路由，int2136 的 href 扫描到不了）：
     /tasks/daily、/tasks/published、/testcases/by-group、/testcases/by-tag、
     /reports；逐页记录可见标题、真实 /api/v1 请求与状态码、渲染计数 vs 接口 total。
  ② 状态取证（每页写清加载 / 空态 / 错误态）：
     - 错误态：Chrome CDP Network.setBlockedURLs 拦截该页主接口 → 记录界面错误文案
       （失败/重试/错误）与截图；解除拦截后重试恢复。
     - 空态：列表页搜索一个必然不存在的关键字 → 记录空态文案；再清空恢复。
     - 加载态：站内切页时用 CDP 限速（2s RTT，页面 chunk 已缓存）→ 记录是否存在
       显式加载指示（加载中/正在加载/loading）；未限速时首屏已被缓存不重复取。

环境（负责人环境铁律）：后端 http://localhost:15000（database 必须
intelligent_audio_test），前端 http://localhost:15173。不启动任何本地栈。
只读：不写业务数据，无需 teardown。

跑法：
  <conda python> tests/ui/probe_int2328_core_states.py \
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
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

from tests.ui.smoke_frontend_int1854 import (  # noqa: E402
    RESULT, body_text, console_errors, make_driver, parse_perf, shot, wait_quiet,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(ROOT, 'artifacts', 'int2328')
SUB = os.path.join(ROOT, 'artifacts', 'int2328', 'subpages')
ERR = os.path.join(ROOT, 'artifacts', 'int2328', 'error_states')

# ① 二级核心子页：路由 → (期望可见文案之一, 用于对齐的接口前缀, 截图 key)
SUBPAGES = [
    ('/tasks/daily',        ['日常', '任务'],      '/tasks',          'tasks_daily'),
    ('/tasks/published',    ['已发布', '正式任务'], '/published-tasks', 'tasks_published'),
    ('/testcases/by-group', ['按分组', '分组'],    '/testcases',      'testcases_by_group'),
    ('/testcases/by-tag',   ['按标签', '标签'],    '/testcases',      'testcases_by_tag'),
    ('/reports',            ['浏览测试报告'],      '/reports',        'reports_showcase'),
]

# ② 错误态：路由 → (拦截 url 模式, 主接口前缀)
ERROR_TARGETS = [
    ('/tasks',            '*api/v1/tasks*',          '/tasks'),
    ('/tasks/published',  '*api/v1/published-tasks*', '/published-tasks'),
    ('/testcases',        '*api/v1/testcases*',      '/testcases'),
    ('/report-center',    '*api/v1/reports*',        '/reports'),
    ('/devices',          '*api/v1/test-devices*',   '/test-devices'),
    ('/audio-import',     '*api/v1/audio*',          '/audio'),
    ('/Evaluation',       '*api/v1/evaluation*',     '/evaluation'),
]

# ③ 空态：路由 → 搜索框选择器（页面内的筛选框，不是顶栏 ⌘K），不存在的关键字
EMPTY_TARGETS = [
    ('/tasks',         "input[aria-label='搜索任务']", '接线测试_不存在_20261102'),
    ('/testcases',     "input[aria-label='搜索用例']", '接线测试_不存在_20261102'),
    ('/report-center', "input[placeholder*='搜索报告名称']", '接线测试_不存在_20261102'),
]

ERR_WORDS = ('加载失败', '获取失败', '请重试', '重试', '错误')
LOAD_WORDS = ('加载中', '正在加载', 'Loading', 'loading')
EMPTY_WORDS = ('暂无', '无数据', '未找到', '无匹配', '没有找到', '暂无数据', '符合条件的')

# Chrome155 + Selenium 在渲染器里偶发不投递 CDP 输入事件（send_keys 写不进
# React 受控输入框，value 仍为空）。用原生 setter + input 事件写入，等价于用户
# 输入触发的 React onChange（只读筛选，不写库）。
SET_VALUE_JS = """
const el = arguments[0], v = arguments[1];
el.focus();
const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
setter.call(el, v);
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
"""


def _apis(drv, prefix):
    apis = parse_perf(drv.get_log('performance'))
    hits = [a for a in apis if prefix in (a.get('url') or '')]
    return apis, hits


def _bad(apis):
    return [{'m': a.get('method'), 's': a.get('status'), 'u': (a.get('url') or '')[:140]}
            for a in apis if isinstance(a.get('status'), int) and a['status'] >= 400]


def _find_words(text, words):
    return [w for w in words if w in text]


def login(drv, base, username, password):
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


def subpage_walk(drv, base):
    out = {}
    for route, expects, api_prefix, key in SUBPAGES:
        rec = {'route': route, 'ok': False}
        try:
            drv.get(base + route)
            time.sleep(3.5)
            wait_quiet(drv, 25)
            txt = body_text(drv)
            all_apis, hits = _apis(drv, api_prefix)
            rec.update({
                'url': drv.current_url,
                'visible_expect': [w for w in expects if w in txt],
                'body_len': len(txt),
                'api_calls': len(hits),
                'api_status': sorted({a.get('status') for a in hits if isinstance(a.get('status'), int)}),
                'api_4xx5xx': _bad(all_apis),
                'console': console_errors(drv)[:3],
                'text_excerpt': txt[-260:],
            })
            m = re.search(r'共\s*(\d+)\s*[条个]', txt)
            rec['count_in_page'] = m.group(1) if m else None
            rec['shot'] = shot(drv, '%s_light' % key)['path']
            rec['ok'] = (bool(rec['visible_expect']) and rec['body_len'] > 120
                         and rec['api_calls'] > 0
                         and not any(a['s'] and a['s'] >= 500 for a in rec['api_4xx5xx']))
        except Exception as exc:
            rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
        out[route] = rec
        print('SUBPAGE %-20s ok=%s expect=%s apis=%s 4xx5xx=%s count=%s' % (
            route, rec.get('ok'), rec.get('visible_expect'), rec.get('api_calls'),
            len(rec.get('api_4xx5xx') or []), rec.get('count_in_page')), flush=True)
    return out


def error_state(drv, base):
    out = {}
    for route, pattern, api_prefix in ERROR_TARGETS:
        rec = {'route': route, 'blocked': pattern, 'ok': False}
        try:
            drv.execute_cdp_cmd('Network.enable', {})
            drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': [pattern]})
            drv.get(base + route)
            time.sleep(4)
            try:
                wait_quiet(drv, 15)
            except Exception:
                pass
            txt = body_text(drv)
            _all, hits = _apis(drv, api_prefix)
            rec.update({
                'url': drv.current_url,
                'error_words': _find_words(txt, ERR_WORDS),
                'empty_words': _find_words(txt, EMPTY_WORDS),
                'body_len': len(txt),
                'text_excerpt': txt[-300:],
                'shot': shot(drv, 'err_%s' % route.strip('/').replace('/', '_'))['path'],
            })
            rec['ok'] = bool(rec['error_words']) or bool(rec['empty_words'])
            # 解除拦截 + 站内重试/重载，确认恢复
            drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
            retried = False
            for b in drv.find_elements(By.TAG_NAME, 'button'):
                if b.is_displayed() and (b.text or '').strip() in ('重试', '重新加载', '刷新'):
                    drv.execute_script('arguments[0].click()', b)
                    retried = True
                    break
            if not retried:
                drv.get(base + route)
            time.sleep(4)
            wait_quiet(drv, 20)
            rtxt = body_text(drv)
            # 只认错误条标记（业务数据里也有「执行失败/失败数量」，不能整体匹配「失败」）
            rec['recovered'] = ('加载失败' not in rtxt and '获取失败' not in rtxt
                                and len(rtxt) > 120)
            rec['recovered_len'] = len(rtxt)
        except Exception as exc:
            rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
            try:
                drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
            except Exception:
                pass
        out[route] = rec
        print('ERRSTATE %-18s words=%s recovered=%s' % (
            route, rec.get('error_words'), rec.get('recovered')), flush=True)
    return out


def empty_state(drv, base):
    out = {}
    for route, selector, keyword in EMPTY_TARGETS:
        rec = {'route': route, 'keyword': keyword, 'ok': False}
        try:
            drv.get(base + route)
            time.sleep(3.5)
            wait_quiet(drv, 25)
            boxes = [e for e in drv.find_elements(By.CSS_SELECTOR, selector) if e.is_displayed()]
            if not boxes:
                rec['note'] = '未找到搜索框 %s' % selector
            else:
                boxes[0].clear()
                drv.execute_script(SET_VALUE_JS, boxes[0], keyword)
                time.sleep(0.6)
                rec['typed_value'] = drv.execute_script('return arguments[0].value', boxes[0])
                # /tasks 需要点「查询」；其余页面输入即过滤（防抖）
                clicked = False
                for b in drv.find_elements(By.TAG_NAME, 'button'):
                    if b.is_displayed() and (b.text or '').strip() == '查询':
                        drv.execute_script('arguments[0].click()', b)
                        clicked = True
                        break
                if not clicked:
                    boxes[0].send_keys(Keys.ENTER)
                time.sleep(3.5)
                wait_quiet(drv, 25)
                txt = body_text(drv)
                all_apis, _hits = _apis(drv, 'api/v1')
                rec['search_apis'] = [{'m': a.get('method'), 's': a.get('status'),
                                       'u': (a.get('url') or '')[:160]}
                                      for a in all_apis
                                      if 'keyword=' in (a.get('url') or '')
                                      or 'search=' in (a.get('url') or '')][:5]
                rec['clicked_query'] = clicked
                rec['empty_words'] = _find_words(txt, EMPTY_WORDS)
                rec['error_words'] = _find_words(txt, ERR_WORDS)
                rec['result_count_text'] = (re.findall(r'共\s*\d+\s*[条个]', txt) or [])[:2]
                rec['text_excerpt'] = txt[-300:]
                rec['shot'] = shot(drv, 'empty_%s' % route.strip('/'))['path']
                rec['ok'] = bool(rec['empty_words']) and not rec['error_words']
                # 清空恢复
                boxes[0].clear()
                boxes[0].send_keys(Keys.ENTER)
                time.sleep(2.5)
                rec['restored_len'] = len(body_text(drv))
        except Exception as exc:
            rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
        out[route] = rec
        print('EMPTY %-16s words=%s count=%s' % (
            route, rec.get('empty_words'), rec.get('result_count_text')), flush=True)
    return out


def loading_state(drv, base):
    """站内切页 + CDP 限速：记录是否存在显式加载指示。"""
    rec = {'ok': False}
    try:
        drv.get(base + '/tasks')
        time.sleep(3)
        wait_quiet(drv, 25)
        rec['before_len'] = len(body_text(drv))
        # 取侧栏到 /devices 的链接，用 JS click 做站内导航（Chrome155 原生点击不投递）
        target = None
        for a in drv.find_elements(By.CSS_SELECTOR, 'a[href="/devices"]'):
            if a.is_displayed():
                target = a
                break
        if target is None:
            rec['note'] = '侧栏无 /devices 链接'
            return rec
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 2000,
            'downloadThroughput': 512 * 1024, 'uploadThroughput': 512 * 1024,
            'connectionType': 'cellular3g'})
        drv.execute_script('arguments[0].click()', target)
        time.sleep(0.7)
        mid = body_text(drv)
        rec['mid_words'] = _find_words(mid, LOAD_WORDS)
        rec['mid_len'] = len(mid)
        rec['url_mid'] = drv.current_url
        rec['shot'] = shot(drv, 'loading_mid_nav')['path']
        rec['previous_content_retained'] = (rec['before_len'] > 0 and rec['mid_len'] >= rec['before_len'] * 0.5)
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 0, 'downloadThroughput': -1,
            'uploadThroughput': -1, 'connectionType': 'none'})
        time.sleep(5)
        wait_quiet(drv, 25)
        rec['after_len'] = len(body_text(drv))
        rec['after_url'] = drv.current_url
        rec['ok'] = True
    except Exception as exc:
        rec['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:200])
        try:
            drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
                'offline': False, 'latency': 0, 'downloadThroughput': -1,
                'uploadThroughput': -1, 'connectionType': 'none'})
        except Exception:
            pass
    print('LOADING words=%s retained=%s' % (rec.get('mid_words'), rec.get('previous_content_retained')),
          flush=True)
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
    ap.add_argument('--only', default='all',
                    choices=['all', 'subpages', 'error', 'empty', 'loading'])
    args = ap.parse_args()
    base = args.base.rstrip('/')

    for d in (ART, SUB, ERR):
        os.makedirs(d, exist_ok=True)
    RESULT['art'] = ART

    download_dir = os.path.join(ART, 'downloads')
    os.makedirs(download_dir, exist_ok=True)
    drv = make_driver(download_dir)
    summary = {}
    try:
        summary['login_url'] = login(drv, base, args.username, args.password)
        print('LOGIN ok ->', summary['login_url'], flush=True)
        if args.only in ('all', 'subpages'):
            summary['subpages'] = subpage_walk(drv, base)
        if args.only in ('all', 'error'):
            summary['error_states'] = error_state(drv, base)
        if args.only in ('all', 'empty'):
            summary['empty_states'] = empty_state(drv, base)
        if args.only in ('all', 'loading'):
            summary['loading_state'] = loading_state(drv, base)
        summary['console_errors'] = console_errors(drv)[:5]
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'summary.json')
    merged = {}
    if os.path.isfile(out_path):
        try:
            with open(out_path, encoding='utf-8') as fh:
                merged = json.load(fh)
        except Exception:
            merged = {}
    merged.update(summary)
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
    summary = merged
    print('\nSUMMARY_JSON=%s' % out_path)
    ok_sub = sum(1 for v in summary.get('subpages', {}).values() if v.get('ok'))
    print('SUBPAGES ok=%d/%d' % (ok_sub, len(summary.get('subpages', {}))))
    for route, v in summary.get('error_states', {}).items():
        print('ERR %-18s ok=%s recovered=%s words=%s' % (
            route, v.get('ok'), v.get('recovered'), v.get('error_words')))
    for route, v in summary.get('empty_states', {}).items():
        print('EMPTY %-16s ok=%s words=%s' % (route, v.get('ok'), v.get('empty_words')))


if __name__ == '__main__':
    main()
