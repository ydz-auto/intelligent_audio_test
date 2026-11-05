# -*- coding: utf-8 -*-
"""INT-2391 报告详情导航 / 导出「环境卡死」判据（tests/ui 单一入口）。

背景
----
INT-2388 定位：报告中心点行后 URL 已变 `/report/<id>?from=management`，但详情组件
不挂载、Network 里没有 `GET /api/v1/reports/<id>`、也没有失败响应。根因是 15173
这个源的浏览器连接被占满（HTTP/1.1 每源 6 连接，2 条常驻 SSE + 停滞请求），懒加载
chunk 发不出去，TanStack 路由停在 `pending`。INT-2386 曾用「重试到碰对」兜底，那既
掩盖频率、也把真回归一起吞掉；本模块把它收敛成一份判据。

判据（点击后观察 3 秒，按顺序判）
--------------------------------
1. `current_url` 含 `/report/<id>`；
2. 目标未出现（详情步骤 = 报告详情「导出」按钮不存在；导出步骤 = 详情已挂载但观察
   窗口内没有 `POST /api/v1/reports/export` 请求）；
3. 观察窗口内详情 / 导出请求**没有完成响应**（未发出，或已发出但停滞未应答——
   后者在浏览器里同样是连接被占满的表现；原脚本的 parse_perf 只统计有响应的请求，
   所以 INT-2388 记的「没有 GET /api/v1/reports/<id>」就是指没有完成响应）；
4. 反证全干净：没有失败响应（4xx·5xx / ERR_*）、没有 SEVERE 控制台报错。

命中 1+2+3 且 4 干净 → **环境卡死**：整页 `driver.get(current_url)` 恢复**一次**
（`MAX_RECOVERIES = 1`），恢复后仍不成功 → 判失败。
任何反证（请求已发出 / 4xx·5xx / 控制台 SEVERE / chunk 失败）→ **前端回归**，
直接判失败，不重试掩盖（这是 INT-2391 验收第 3 条的反证要求）。

阈值（写死在本模块，脚本注释与交付评论同口径）
----------------------------------------------
- `OBSERVE_TIMEOUT_S = 3.0`：点击后观察窗口；
- `MAX_RECOVERIES = 1`：整页恢复上限，绝不无限重试。

接入方式（详情与导出两处都只调用 `ensure_report_step`，不存在第二份重试实现）
----------------------------------------------------------------------------
    detail = ensure_report_step(driver, 'detail', report_id)
    if detail['ok']:
        export = ensure_report_step(driver, 'export', report_id, click=do_export_click)

`click` 只在导出步骤传：负责打开导出弹窗并点「导出」；观察判据仍在本函数内。
"""
import json
import re
import time

from selenium.webdriver.common.by import By

__all__ = ['OBSERVE_TIMEOUT_S', 'MAX_RECOVERIES', 'ensure_report_step',
           'describe_thresholds']

# ── 阈值（INT-2391 验收第 4 条：3 秒窗口、恢复上限 1 次）──────────────────
OBSERVE_TIMEOUT_S = 3.0
MAX_RECOVERIES = 1

DETAIL_API_RE = re.compile(r'/api/v1/reports/(\d+)(?:\?|$)')
EXPORT_API_PATH = '/api/v1/reports/export'
REPORT_URL_RE = re.compile(r'/report/(\d+)(?:\?|#|$)')
ROUTE_CHUNK_RE = re.compile(r'/(?:static|assets)/.*?\.js(?:\?|$)')

EXPORT_BUTTON_TEXTS = ('导出', '导出报告', 'HTML 导出')


def describe_thresholds():
    """判据阈值一句话，写进交付评论用。"""
    return ('观察窗口 %.1fs；整页恢复上限 %d 次；环境卡死 = URL 已变 + 目标未出现 + '
            '窗口内详情/导出请求无完成响应（未发出或停滞未应答）+ 无失败响应/控制台 '
            'SEVERE；请求已应答但组件未渲染 / 4xx·5xx / chunk 失败 / 控制台报错 → '
            '一律判前端回归，不恢复。' % (OBSERVE_TIMEOUT_S, MAX_RECOVERIES))


# ── 浏览器侧观测 ────────────────────────────────────────────────────────
def _parse_perf(raw_logs, pending):
    """把 performance log 拆成「请求尝试 + 结果」。

    与 smoke 脚本的 parse_perf 不同：这里保留**没有拿到响应**的请求
    （被 block / 连接停滞），因为那正是区分环境卡死与真回归的关键证据。
    `pending` 跨多次 drain 复用 —— get_log 每次调用会把缓冲区清空，
    requestWillBeSent 与 responseReceived 常落在不同批次。
    """
    for entry in raw_logs:
        try:
            inner = json.loads(entry.get('message', '{}')).get('message', {})
            method, params = inner.get('method', ''), inner.get('params', {})
        except Exception:
            continue
        rid = params.get('requestId')
        if method == 'Network.requestWillBeSent':
            req = params.get('request', {})
            pending[rid] = {'url': req.get('url'), 'method': req.get('method'),
                            'status': None, 'failed': False, 'error': None}
        elif method == 'Network.responseReceived':
            rec = pending.setdefault(rid, {'url': None, 'method': None,
                                           'status': None, 'failed': False,
                                           'error': None})
            resp = params.get('response') or {}
            rec['url'] = rec.get('url') or resp.get('url')
            rec['status'] = resp.get('status')
        elif method == 'Network.loadingFailed':
            rec = pending.get(rid)
            if rec is not None:
                rec['failed'] = True
                rec['error'] = params.get('errorText') or 'loadingFailed'
    # 未拿到结果的请求同样算「已发出」（被 block / 停滞），但把还在飞的单独标记。
    return [dict(rec) for rec in pending.values()]


def _drain_network(driver, pending):
    try:
        return _parse_perf(driver.get_log('performance'), pending)
    except Exception:
        return []


def _drain_console(driver):
    try:
        return [e for e in driver.get_log('browser')
                if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', ''))]
    except Exception:
        return []


def _merge_requests(store, entries):
    for rec in entries:
        key = (rec.get('method'), rec.get('url'))
        prev = store.get(key)
        # 同一 URL 以「拿到结果」的那条为准；失败优先于成功（同一窗口内重发）
        if prev is None or (prev.get('status') is None and rec.get('status') is not None) \
                or (rec.get('failed') and not prev.get('failed')):
            store[key] = rec


def _export_button_present(driver):
    for b in driver.find_elements(By.TAG_NAME, 'button'):
        try:
            if b.is_displayed() and (b.text or '').strip() in EXPORT_BUTTON_TEXTS:
                return True
        except Exception:
            continue
    return False


def _target_reached(driver, step, requests):
    """步骤成功条件。

    详情：导出按钮出现（详情组件已挂载）；导出：看到 2xx 的导出请求。
    """
    if step == 'detail':
        return _export_button_present(driver)
    hits = [r for r in requests if EXPORT_API_PATH in (r.get('url') or '')]
    return any(200 <= (r.get('status') or 0) < 300 for r in hits)


def _observe(driver, step, report_id, requests, console_errors):
    url = driver.current_url or ''
    m = REPORT_URL_RE.search(url)

    def _is_target_detail(rec_url):
        hit = DETAIL_API_RE.search(rec_url or '')
        return bool(hit and hit.group(1) == str(report_id))

    detail_hits = [r for r in requests if _is_target_detail(r.get('url'))]
    export_hits = [r for r in requests if EXPORT_API_PATH in (r.get('url') or '')]
    chunk_hits = [r for r in requests if ROUTE_CHUNK_RE.search(r.get('url') or '')]
    return {
        'step': step,
        'url': url,
        'url_report_id': m.group(1) if m else None,
        'url_has_report': bool(m and (report_id is None
                                      or str(m.group(1)) == str(report_id))),
        'detail_mounted': _export_button_present(driver),
        'requests': requests,
        'detail_hits': detail_hits,
        'export_hits': export_hits,
        'chunk_hits': chunk_hits,
        'console_errors': console_errors,
    }


def _classify(obs):
    """返回 (verdict, reason)。verdict ∈ regression / env_stall（目标达成时另判）。

    关键区分：「请求已发出」以**拿到结果**为准（有响应或明确失败）。连接被占满时
    浏览器会先发出 requestWillBeSent，然后请求在套接字队列里停滞、始终没有响应；
    这与 INT-2388 观察到的「该时段没有 GET /api/v1/reports/<id>」是同一现象
    （原脚本的 parse_perf 只统计有响应的请求）。所以停滞未应答仍归环境卡死。
    """
    # 反证 1：窗口内出现失败响应 / 失败请求（4xx·5xx、ERR_*、被 block）
    bad = [r for r in obs['requests']
           if r.get('failed') or ((r.get('status') or 0) >= 400)]
    if bad:
        sample = '; '.join('%s %s -> %s' % (r.get('method') or '?', r.get('url'),
                                            r.get('error') or r.get('status'))
                           for r in bad[:3])
        return 'regression', '窗口内有失败响应/失败请求：%s' % sample
    # 反证 2：控制台 SEVERE（chunk 加载失败、组件异常）
    if obs['console_errors']:
        msgs = [str(e.get('message'))[:160] for e in obs['console_errors'][:3]]
        return 'regression', '控制台 SEVERE：%s' % ' | '.join(msgs)
    # 反证 3：URL 没进详情
    if not obs['url_has_report']:
        return 'regression', 'URL 未变到 /report/<id>（当前 %s）' % obs['url']

    def _answered(recs):
        return [r for r in recs if r.get('status') is not None]

    # 反证 4：本步骤该发的请求已拿到响应（现象已不同 / 或组件自身没渲染）
    if obs['step'] == 'detail':
        if _answered(obs['detail_hits']):
            return 'regression', '详情请求已应答但组件未渲染（不是传输层卡死）'
        if obs['detail_hits']:
            return 'env_stall', '详情请求已发出但窗口内没有应答（传输层停滞）'
        if _answered(obs['chunk_hits']):
            return 'regression', '路由 chunk 已应答但连详情请求都没发出（组件未渲染）'
        return 'env_stall', 'URL 已变、导出按钮缺失、窗口内无详情/chunk 请求'
    if _answered(obs['export_hits']):
        return 'regression', '导出请求已应答但未成功完成'
    if obs['export_hits']:
        return 'env_stall', '导出请求已发出但窗口内没有应答（传输层停滞）'
    if _answered(obs['chunk_hits']):
        return 'regression', '导出步骤 chunk 已应答但导出请求未发出'
    return 'env_stall', '详情已挂载、窗口内无导出请求、无失败响应'


# ── 唯一入口 ────────────────────────────────────────────────────────────
def ensure_report_step(driver, step, report_id=None, *, trigger=None, click=None,
                       recover=None, timeout=OBSERVE_TIMEOUT_S,
                       max_recoveries=MAX_RECOVERIES, logger=None):
    """等待报告步骤达成；未达成时按判据分类，环境卡死最多整页恢复一次。

    参数
    ----
    driver       : Selenium WebDriver（需开 performance/browser 日志）
    step         : 'detail' | 'export'
    report_id    : 目标报告 id；为 None 时在 trigger 之后从 URL 读取
    trigger      : 只详情步骤使用；触发导航的回调（如点击报告行）。**必须在
                   本函数内触发**，否则「点击 → 观察」之间的网络会被漏掉。
    click        : 只导出步骤使用；打开导出弹窗并点「导出」的回调
    recover      : 自定义恢复动作；默认整页 driver.get(当前 URL)
    timeout      : 观察窗口（默认 3s）
    max_recoveries : 整页恢复上限（默认 1，禁止传入大于 1 的值）

    返回
    ----
    {'ok', 'status', 'recovered', 'recoveries', 'elapsed_s', 'reason',
     'observations': [...]}
      status ∈ ok / env_stall_recovered / env_stall_unrecovered / regression
    """
    if step not in ('detail', 'export'):
        raise ValueError("step 必须是 'detail' 或 'export'")
    if max_recoveries > MAX_RECOVERIES:
        raise ValueError('整页恢复上限固定为 %d 次（INT-2391）' % MAX_RECOVERIES)
    log = logger or (lambda _m: None)

    t0 = time.time()
    observations = []
    store = {}
    net_pending = {}
    console_seen = []

    # 清掉触发之前的旧日志，只观察本步骤窗口；触发放在清空之后，避免漏掉导航请求
    _drain_network(driver, net_pending)
    _drain_console(driver)
    net_pending.clear()
    if trigger is not None:
        trigger()
        if report_id is None:
            report_id = _await_report_id(driver, 3.0)
    if step == 'export' and click is not None:
        click()

    recoveries = 0
    while True:
        deadline = time.time() + timeout
        reached = False
        while time.time() < deadline:
            _merge_requests(store, _drain_network(driver, net_pending))
            console_seen.extend(_drain_console(driver))
            if _target_reached(driver, step, list(store.values())):
                reached = True
                break
            time.sleep(0.25)
        _merge_requests(store, _drain_network(driver, net_pending))
        console_seen.extend(_drain_console(driver))

        obs = _observe(driver, step, report_id, list(store.values()),
                       list(console_seen))
        obs['elapsed_s'] = round(time.time() - t0, 2)
        if reached:
            obs['verdict'] = 'ok'
            obs['reason'] = ('整页恢复 %d 次后目标出现' % recoveries if recoveries
                             else '目标已出现')
            observations.append(obs)
            return _result('env_stall_recovered' if recoveries else 'ok', True,
                           recoveries, t0, observations, obs['reason'])

        obs['verdict'], obs['reason'] = _classify(obs)
        observations.append(obs)
        log('[%s] 未达成：%s —— %s' % (step, obs['verdict'], obs['reason']))

        if obs['verdict'] == 'regression':
            return _result('regression', False, recoveries, t0, observations,
                           obs['reason'])
        if recoveries >= max_recoveries:
            return _result('env_stall_unrecovered', False, recoveries, t0,
                           observations, '整页恢复 %d 次后仍未达成：%s'
                           % (recoveries, obs['reason']))

        recoveries += 1
        log('[%s] 环境卡死·整页恢复第 %d/%d 次' % (step, recoveries, max_recoveries))
        if recover is not None:
            recover()
        else:
            driver.get(driver.current_url)
            if step == 'export':
                # 整页重载后等详情挂载，再重新触发导出
                _wait_detail_mounted(driver, 30)
        if step == 'export' and click is not None:
            time.sleep(1.5)
            click()


def _await_report_id(driver, timeout):
    """trigger 之后从 URL 里读目标报告 id（SPA 导航很快，最多等 timeout 秒）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        m = REPORT_URL_RE.search(driver.current_url or '')
        if m:
            return m.group(1)
        time.sleep(0.1)
    return None


def _wait_detail_mounted(driver, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _export_button_present(driver):
            return True
        time.sleep(0.25)
    return False


def _result(status, ok, recoveries, t0, observations, reason):
    return {
        'ok': ok,
        'status': status,
        'recovered': status == 'env_stall_recovered',
        'recoveries': recoveries,
        'elapsed_s': round(time.time() - t0, 2),
        'reason': reason,
        'observations': observations,
    }
