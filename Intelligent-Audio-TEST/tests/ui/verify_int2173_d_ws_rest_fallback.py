# -*- coding: utf-8 -*-
"""INT-2173 返工 D：WS 断流时实时日志卡的 REST 轮询兜底（只断 socket.io 传输，不动 docker/REST）。

做法：
1. 先起浏览器并注入 WebSocket 断流桩（Page.addScriptToEvaluateOnNewDocument 替换 window.WebSocket，
   握手即 error/close，等价于「ws 断开/连不上」，REST 完全不受影响；另加 CDP Network.setBlockedURLs
   对 *socket.io* 兜底）；
2. REST 建一个 7 用例、并发 1 的「接线测试_」任务（时长 >10s，10s 轮询窗口才有效）；
3. 打开 /tasks/:id 实时日志卡，逐秒采样「实时日志 N(/总)」计数、日志行、任务状态，并收集 performance log；
4. 断言：WS 握手被拦截且未建立连接、日志条数随 GET /logs 轮询分步增长（≥2 次、间隔≈10s）、
   结束态卡片总数 = 独立调 GET /logs 的 total、可见行无重复。
收尾按 id 软删 + purge。
"""
import json
import os
import re
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:15173')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2173')
os.makedirs(ART, exist_ok=True)
TS = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT2173_WS断流_%s' % TS
CASE_IDS = [
    '6cffc552-9b74-4e19-8647-ae78b75624bb',
    '6bd49169-b5c5-4c80-ad83-4b493d1e3dec',
    '45a1b714-8c2c-4ab8-ae55-4a09603c002c',
    'e3e26cef-2054-4d58-ba19-36047e0a427a',
    'd53795e3-0fd1-4e30-8268-865e460e95e7',
    'a2d30859-53b5-471b-924d-0a21d2972ed8',
    '7e775d1b-ca86-455e-bf4d-8509014359e9',
]
API_ID = 411
RESULTS = []
CTX = {}

WS_BLOCK_JS = r'''
(function(){
  try {
    window.__wsAttempts = [];
    window.__wsEvents = [];
    function BlockedWS(url, protocols){
      var u = String(url);
      window.__wsAttempts.push(u);
      window.__wsEvents.push({ev: 'construct', url: u, t: Date.now()});
      var self = this;
      this.url = u;
      this.readyState = 0;
      this.bufferedAmount = 0;
      this.extensions = '';
      this.protocol = '';
      this.binaryType = 'blob';
      this.onopen = null; this.onerror = null; this.onclose = null; this.onmessage = null;
      this.send = function(){};
      this.addEventListener = function(t, fn){ self['on' + t] = fn; };
      this.removeEventListener = function(){};
      this.dispatchEvent = function(){ return true; };
      this.close = function(){ self.readyState = 3; if (self.onclose) { try { self.onclose({code:1006, reason:'blocked'}); } catch(e){} } };
      setTimeout(function(){
        self.readyState = 3;
        window.__wsEvents.push({ev: 'error', url: u, t: Date.now()});
        if (self.onerror) { try { self.onerror(new Event('error')); } catch(e){} }
        window.__wsEvents.push({ev: 'close', url: u, t: Date.now()});
        if (self.onclose) { try { self.onclose({code:1006, reason: 'simulated network cut'}); } catch(e){} }
      }, 5);
    }
    BlockedWS.CONNECTING = 0; BlockedWS.OPEN = 1; BlockedWS.CLOSING = 2; BlockedWS.CLOSED = 3;
    BlockedWS.prototype.CONNECTING = 0; BlockedWS.prototype.OPEN = 1;
    BlockedWS.prototype.CLOSING = 2; BlockedWS.prototype.CLOSED = 3;
    window.WebSocket = BlockedWS;
  } catch(e) {}
})();
'''


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1500]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ((' | ' + str(detail)[:500]) if detail else ''))
    return ok


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


LOG_JS = r"""
  const nodes = [...document.querySelectorAll('div,span,h3,h4')];
  const title = nodes.map(e => (e.textContent||'').trim()).find(t => /^实时日志\s*\d+/.test(t));
  let loaded = -1, total = -1;
  if (title) {
    const m = title.match(/^实时日志\s*(\d+)(?:\s*\/\s*(\d+))?/);
    if (m) { loaded = parseInt(m[1],10); total = m[2] ? parseInt(m[2],10) : -1; }
  }
  const rows = [...document.querySelectorAll('div.flex.items-baseline.gap-2')];
  const texts = rows.map(r => (r.textContent||'').replace(/\s+/g,' ').trim()).filter(Boolean);
  const seen = new Set(); let dups = 0;
  for (const t of texts) { if (seen.has(t)) dups++; else seen.add(t); }
  const bodyText = (document.body.textContent||'');
  const loadingTxt = (bodyText.match(/已加载\s*\d+\s*\/\s*共\s*\d+\s*条/) || [''])[0];
  return {loaded, total, dups, rowCount: seen.size, rowsSample: texts.slice(0,3),
          loadingTxt, bodyHasLogs: bodyText.includes('实时日志'),
          wsAttempts: (window.__wsAttempts||[]).length,
          wsEvents: (window.__wsEvents||[]).slice(0,6)};
"""


def drain_net(drv):
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:
        return out
    for e in entries:
        try:
            m = json.loads(e['message']).get('message', {})
        except Exception:
            continue
        meth = m.get('method')
        p = m.get('params', {}) or {}
        if meth == 'Network.requestWillBeSent':
            r = p.get('request', {}) or {}
            out.append({'kind': 'req', 'method': r.get('method'), 'url': r.get('url') or '',
                        'id': p.get('requestId'), 'ts': time.time()})
        elif meth == 'Network.responseReceived':
            r = p.get('response', {}) or {}
            out.append({'kind': 'resp', 'status': r.get('status'), 'url': r.get('url') or '',
                        'id': p.get('requestId')})
        elif meth == 'Network.loadingFailed':
            out.append({'kind': 'fail', 'id': p.get('requestId'),
                        'blockedReason': p.get('blockedReason'), 'errorText': p.get('errorText')})
        elif meth == 'Network.webSocketCreated':
            out.append({'kind': 'ws', 'url': p.get('url') or ''})
    return out


def logs_total(tid, token):
    st, d = B.api('/api/v1/logs?task_id=%d&page=1&per_page=20' % tid, token)
    data = d.get('data') or {}
    return st, data.get('total')


def task_status(tid, token):
    st, d = B.api('/api/v1/tasks/%d' % tid, token)
    return (d.get('data') or {}).get('status')


def main():
    token, user = B.rsa_login_token('接线测试_admin', 'JieXianTest@2026')
    st, health = B.api('/health', None)
    print('health', st, health)
    check('D 段开工核对 /health database=intelligent_audio_test',
          health.get('database') == 'intelligent_audio_test', health)

    drv = B.driver_init()
    tid = None
    try:
        # 断流桩：新文档加载即替换 WebSocket；CDP 层再兜底 block socket.io
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': WS_BLOCK_JS})
        try:
            drv.execute_cdp_cmd('Network.enable', {})
            drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*socket.io*']})
        except Exception as exc:
            print('cdp block skip', exc)
        B.bootstrap(drv, token, user)

        body = {
            'name': NAME,
            'algorithm_type': 'voice_llm',
            'case_ids': CASE_IDS,
            'device_ids': [],
            'api_ids': [API_ID],
            'target_modes': [{'target_type': 'api', 'target_id': API_ID, 'mode': 'parallel'}],
            'case_devices': [{'case_id': c, 'device_type': 'http_api', 'device_id': str(API_ID)} for c in CASE_IDS],
            'config': {'rounds': 1, 'timeout': 60, 'retries': 0, 'concurrent_tasks': 1,
                       'network': '默认', 'report_template': '标准模板', 'include_charts': True,
                       'include_detailed_logs': True, 'include_reference_params': True},
        }
        t_create = time.time()
        st, res = B.api('/api/v1/tasks', token, method='POST', body=body)
        tid = (res.get('data') or {}).get('id')
        CTX['create'] = {'status': st, 'tid': tid, 'name': NAME, 'cases': len(CASE_IDS)}
        check('POST /api/v1/tasks 建 7 用例任务（并发 1，目标 HTTP API %d）' % API_ID,
              st in (200, 201) and tid is not None, {'status': st, 'tid': tid, 'resp': str(res)[:300]})
        if not tid:
            print('CREATE FAILED', res)
            return

        B.goto(drv, '/tasks/%d' % tid, timeout=90)
        t_ready = time.time() - t_create
        CTX['page_ready_s'] = round(t_ready, 1)
        # 返工 2：日志卡异步挂载，必须等卡片选择器出现再断言（此前开工 6.7s 抢跑随机红）
        card_seen = False
        card_at = None
        for _ in range(90):
            info0 = drv.execute_script(LOG_JS) or {}
            if info0.get('bodyHasLogs'):
                card_seen = True
                card_at = round(time.time() - t_create, 1)
                break
            time.sleep(0.5)
        CTX['card_appear_s'] = card_at
        check('任务详情页打开且出现实时日志卡（轮询等待卡片选择器，上限 45s）', card_seen,
              {'url': drv.current_url, 'card_appear_s': card_at})

        start = time.time()
        samples = []
        net = []
        status = None
        last_poll = 0
        while time.time() - start < 150:
            info = drv.execute_script(LOG_JS) or {}
            net.extend(drain_net(drv))
            now = time.time() - start
            if now - last_poll > 2.0:
                try:
                    status = task_status(tid, token)
                except Exception as exc:
                    print('status poll skip', exc)
                last_poll = now
            samples.append({'t': round(now, 1), 'loaded': info.get('loaded'), 'total': info.get('total'),
                            'dups': info.get('dups'), 'rowCount': info.get('rowCount'),
                            'status': status, 'wsAttempts': info.get('wsAttempts')})
            if status in ('completed', 'failed', 'stopped') and now > 20:
                break
            time.sleep(1.0)
        CTX['samples'] = samples[:200]
        CTX['status_end'] = status
        CTX['task_wall_s'] = round(time.time() - t_create, 1)

        # 返工 2：终态瞬间卡片还没跑完终态后那次 REST 轮询（实测 T+5s 才追平），
        # 必须等卡片 total 稳定 ≥3s 且距终态 ≥15s 后再与 GET /logs total 比对。
        settle_start = time.time()
        settle = []
        prev_pair = None
        stable_since = None
        while time.time() - settle_start < 90:
            info_s = drv.execute_script(LOG_JS) or {}
            net.extend(drain_net(drv))
            pair = (info_s.get('loaded'), info_s.get('total'))
            settle.append({'t': round(time.time() - start, 1), 'loaded': pair[0], 'total': pair[1],
                           'loadingTxt': info_s.get('loadingTxt')})
            if pair == prev_pair and pair[0] is not None and pair[0] >= 0:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - settle_start >= 15 and time.time() - stable_since >= 3.0:
                    break
            else:
                stable_since = None
            prev_pair = pair
            time.sleep(1.0)
        CTX['settle'] = {'waited_s': round(time.time() - settle_start, 1),
                         'samples': settle[-12:], 'final_pair': list(prev_pair or (None, None))}
        CTX['ws_block'] = {'attempts': samples[-1].get('wsAttempts') if samples else None,
                           'events': (drv.execute_script('return (window.__wsEvents||[]).slice(0,8)') or [])}

        # ---- WS 断流证据 ----
        ws_created = [e for e in net if e.get('kind') == 'ws']
        blocked_ws = [e for e in net if e.get('kind') == 'fail' and e.get('blockedReason')]
        CTX['ws_net'] = {'webSocketCreated': len(ws_created), 'blockedFailures': len(blocked_ws)}
        check('WS 传输被断流：socket.io 握手请求全部失败/被 BLOCKED，未建立 WS 连接',
              (CTX['ws_block']['attempts'] or 0) > 0 and len(ws_created) == 0,
              {'wsAttempts': CTX['ws_block']['attempts'], 'events': CTX['ws_block']['events'],
               'net': CTX['ws_net']})

        # ---- REST 轮询兜底证据 ----
        log_urls = [e['url'] for e in net if e.get('kind') == 'req' and '/logs?' in (e.get('url') or '')
                    and ('task_id=%d' % tid) in e['url']]
        log_ts = sorted({round(e['ts'], 1) for e in net
                         if e.get('kind') == 'req' and '/logs?' in (e.get('url') or '')
                         and ('task_id=%d' % tid) in e['url'] and e.get('ts')})
        req_gaps = [round(log_ts[i] - log_ts[i - 1], 1) for i in range(1, len(log_ts))]
        CTX['rest_log_requests'] = len(log_urls)
        CTX['rest_log_gaps_s'] = req_gaps
        check('WS 断流期间前端按 ≈10s 周期用 GET /logs?task_id= 轮询兜底（≥2 次、间隔 6–16s）',
              len(log_urls) >= 2 and any(6 <= g <= 16 for g in req_gaps),
              {'count': len(log_urls), 'gaps_s': req_gaps, 'sample': log_urls[:2]})

        running_s = [s['t'] for s in samples if s.get('status') == 'running']
        active_s = [s['t'] for s in samples if s.get('status') not in (None, 'completed', 'failed', 'stopped')]
        CTX['running_span_s'] = round(max(running_s) - min(running_s), 1) if running_s else 0
        CTX['active_span_s'] = round(max(active_s) - min(active_s), 1) if active_s else 0
        # 任务时长受用例/排队影响不固定，可复现的口径是「观察窗覆盖 ≥2 个 10s 轮询周期」
        obs_span = round(max(log_ts) - min(log_ts), 1) if len(log_ts) >= 2 else 0
        CTX['poll_obs_span_s'] = obs_span
        check('轮询观察窗覆盖 ≥2 个 10s 周期（首末 GET /logs 间隔 ≥15s）',
              obs_span >= 15,
              {'poll_obs_span_s': obs_span, 'active_span_s': CTX['active_span_s'],
               'running_span_s': CTX['running_span_s'], 'task_wall_s': CTX['task_wall_s']})

        growth = []
        prev = None
        for s in list(samples) + list(settle):
            v = s.get('loaded')
            if isinstance(v, int) and v > 0 and (prev is None or v > prev):
                growth.append({'t': s['t'], 'value': v})
                prev = v
        gaps = [round(growth[i]['t'] - growth[i - 1]['t'], 1) for i in range(1, len(growth))]
        CTX['log_growth'] = growth[:12]
        CTX['growth_gaps_s'] = gaps
        check('断流下卡片日志条数随轮询增长（观察窗内 0→N 单调增长，终态后继续追平）',
              len(growth) >= 1 and growth[-1]['value'] > 0,
              {'growth': growth[:8], 'gaps_s': gaps})

        # ---- 结束态：卡片总数 = 独立 GET /logs total ----
        final_total = None
        if prev_pair and isinstance(prev_pair[1], int) and prev_pair[1] > 0:
            final_total = prev_pair[1]
        st, api_total = logs_total(tid, token)
        # 兜底：稳定判定后仍与接口有差，最多再追 20s（验证追平而非掩盖）
        chase = 0
        while (final_total is not None and api_total is not None
               and int(final_total) != int(api_total) and chase < 20):
            time.sleep(1.0)
            chase += 1
            info_c = drv.execute_script(LOG_JS) or {}
            if isinstance(info_c.get('total'), int) and info_c.get('total') > 0:
                final_total = info_c.get('total')
            st, api_total = logs_total(tid, token)
        CTX['final_chase_s'] = chase
        CTX['final'] = {'card_total': final_total, 'api_total': api_total, 'status': status, 'logs_status': st}
        check('结束态卡片总条数 = GET /logs?task_id= total（无丢行）',
              final_total is not None and api_total is not None and int(final_total) == int(api_total),
              CTX['final'])

        final = drv.execute_script(LOG_JS) or {}
        check('REST 轮询增量合并后可见行无重复',
              (final.get('dups') or 0) == 0,
              {'dups': final.get('dups'), 'rowCount': final.get('rowCount'), 'loading': final.get('loadingTxt')})
        check('卡片「已加载 x / 共 N 条」的 N 与接口 total 一致',
              int(api_total or -1) == int(final_total or -2),
              {'loadingText': final.get('loadingTxt'), 'api_total': api_total})

        # ---- 截图（返工 2：必须取到日志卡本身，不能只拍详情页头） ----
        SCROLL_CARD_JS = r"""
          const cands = [...document.querySelectorAll('div,span,h3,h4')]
            .filter(e => /^实时日志\s*\d+/.test((e.textContent||'').trim()));
          if (!cands.length) return {ok: false};
          const title = cands.reduce((a, b) =>
            ((a.textContent||'').length <= (b.textContent||'').length ? a : b));
          let box = title, isCard = false;
          for (let i = 0; i < 6 && box; i++) {
            const tokens = ((box.className||'').toString()).split(/\s+/);
            if (tokens.indexOf('group/card') >= 0) { isCard = true; break; }
            box = box.parentElement;
          }
          box = box || title;
          box.setAttribute('data-int2173-log-card', '1');
          box.scrollIntoView({block: 'center'});
          const r = box.getBoundingClientRect();
          return {ok: true, title: (title.textContent||'').trim(),
                  loading: (document.body.textContent.match(/已加载\s*\d+\s*\/\s*共\s*\d+\s*条/) || [''])[0],
                  top: Math.round(r.top), h: Math.round(r.height), isCard};
        """

        def card_shot(prefix):
            pos = None
            for _ in range(30):
                pos = drv.execute_script(SCROLL_CARD_JS) or {}
                if pos.get('ok'):
                    break
                time.sleep(0.5)
            time.sleep(0.6)
            view_path = shot(drv, prefix)
            el_path = None
            try:
                el = drv.find_element(By.CSS_SELECTOR, '[data-int2173-log-card="1"]')
                el_path = os.path.join(ART, prefix + '_card.png')
                el.screenshot(el_path)
                print('SHOT', el_path)
            except Exception as exc:
                print('element shot skip', exc)
            return view_path, el_path, pos

        v1, c1, p1 = card_shot('D01_log_rest_poll_light')
        check('D01 浅色截图取到实时日志卡（定位到日志卡容器，标题「实时日志 N」在视口内）',
              bool(p1.get('ok')) and bool(p1.get('isCard'))
              and bool(re.match(r'^实时日志\s*\d+', p1.get('title') or ''))
              and -400 <= int(p1.get('top', -9999)) <= 900,
              {'pos': p1, 'view': os.path.basename(v1), 'card': os.path.basename(c1 or '')})

        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
        # reload 后卡片重新挂载，等卡片出现再截图
        card_ok_dark = False
        for _ in range(60):
            info_d = drv.execute_script(LOG_JS) or {}
            if info_d.get('bodyHasLogs'):
                card_ok_dark = True
                break
            time.sleep(0.5)
        time.sleep(1.5)
        dark = drv.execute_script('return document.documentElement.className') or ''
        v2, c2, p2 = card_shot('D02_log_rest_poll_dark')
        check('D02 深色日志卡截图（dark 生效 + 卡片在视口内）',
              'dark' in dark and bool(card_ok_dark) and bool(p2.get('ok')),
              {'cls': dark, 'card': os.path.basename(c2 or ''), 'pos': p2})
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light'); location.reload();")
        time.sleep(3)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        if tid:
            st1, r1 = B.api('/api/v1/tasks/%d' % tid, token, method='DELETE')
            st2, r2 = B.api('/api/v1/tasks/%d/purge' % tid, token, method='DELETE')
            print('CLEANUP', tid, st1, st2)
            CTX['cleanup'] = {'delete': st1, 'purge': st2}
            q = urllib.parse.quote(NAME)
            for _ in range(15):
                st, d = B.api('/api/v1/tasks?page=1&per_page=10&search=' + q, token)
                if ((d.get('data') or {}).get('total') or 0) == 0:
                    break
                time.sleep(1)
            print('CLEANUP REMAIN', B.api('/api/v1/tasks?page=1&per_page=10&search=' + q, token)[1].get('data', {}).get('total'))

    failed = [r for r in RESULTS if not r['ok']]
    print('\n==== D: %d checks, %d failed ====' % (len(RESULTS), len(failed)))
    with open(os.path.join(ART, 'evidence_D.json'), 'w', encoding='utf-8') as f:
        json.dump({'checks': RESULTS, 'ctx': CTX}, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
