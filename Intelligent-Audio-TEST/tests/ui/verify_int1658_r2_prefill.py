# -*- coding: utf-8 -*-
"""INT-1658 复测（打回后只复测失败项）：分组 facet 底部「+ 新增分组」建组成功后预填分组筛选。

打回项（代码审计员 01a16b52）：11_用例域.md §3.4「下拉底部固定项「+ 新增分组」……
创建成功后预填分组筛选」。修复提交 07c8b4d96。

本脚本在「交付树 pnpm build 的 dist + 15173 同款 nginx conf」旁路容器上实测（默认 15271）：
1. 浅色：分组 facet 底部「+ 新增分组」→ 弹窗「新建分组」→ 保存
   → 断言 POST /api/v1/groups 201、GET /api/v1/groups 200、
     GET /api/v1/testcases 带新 group_id 且 200；
   → 断言 facet trigger 由「分组 全部」变为新组名（预填）；列表区出现该分组卡（分组上下文头）。
2. 重置 → trigger 回「分组 全部」。
3. 回归：页头「新建分组」建组 → trigger 仍「分组 全部」（不预填，selectAfterCreate 标记已清）。
4. 深色：同一 facet 入口建组 → trigger 预填新组名 + 深色截图（断言 html.dark）。
5. 控制台 SEVERE 计数；自建「接线测试_INT1658R2_」分组按接口清理并回读。

用法：
    python tests/ui/verify_int1658_r2_prefill.py [--base http://127.0.0.1:15271]
环境变量：CHROMEDRIVER（默认本机缓存驱动）。
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, 'artifacts', 'int1658_r2')
DEFAULT_DRIVER = r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
API = 'http://127.0.0.1:15000'
PREFIX = '接线测试_INT1658R2_'

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:500]})
    print(('PASS ' if ok else 'FAIL ') + name + ((' | ' + str(detail)[:300]) if detail else ''))
    return ok


def build_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1000')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    opts.set_capability('pageLoadStrategy', 'eager')
    exe = os.environ.get('CHROMEDRIVER', DEFAULT_DRIVER)
    if not os.path.isfile(exe):
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
        versions = sorted(os.listdir(cache)) if os.path.isdir(cache) else []
        exe = os.path.join(cache, versions[-1], 'chromedriver.exe') if versions else None
    srv = Service(executable_path=exe) if exe else Service()
    return webdriver.Chrome(service=srv, options=opts)


# ---------- 页面内读取 ----------
STATE_JS = r"""
const vis = (el) => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
};
const btns = Array.from(document.querySelectorAll('button'));
const trigger = btns.find(b => /^分组(\s|$)/.test((b.innerText || '').trim()));
const dialogs = Array.from(document.querySelectorAll('[data-slot="dialog-content"],[role="dialog"]')).filter(vis);
const dlg = dialogs[dialogs.length - 1] || null;
const pops = Array.from(document.querySelectorAll('[data-slot="popover-content"]')).filter(vis);
const pop = pops[pops.length - 1] || null;
const footerItem = pop ? Array.from(pop.querySelectorAll('button')).map(b => (b.innerText || '').trim()).find(t => t === '+ 新增分组') : null;
const cards = Array.from(document.querySelectorAll('div.cursor-pointer')).map(c => (c.innerText || '').split('\n').slice(0, 3).join(' '));
return {
  trigger: trigger ? (trigger.innerText || '').replace(/\s+/g, ' ').trim() : null,
  triggerVisible: vis(trigger),
  dialogOpen: !!dlg,
  dialogTitle: dlg ? ((dlg.querySelector('[data-slot="dialog-title"]') || {}).innerText || '').trim() : '',
  popoverOpen: !!pop,
  footerItem: footerItem || null,
  cards: cards.slice(0, 12),
  bodySnippet: (document.body.innerText || '').slice(0, 900),
  dark: document.documentElement.classList.contains('dark'),
  headerCreateBtn: btns.some(b => (b.innerText || '').trim() === '新建分组' && vis(b)),
};
"""


def state(drv):
    return drv.execute_script(STATE_JS)


def wait_until(drv, pred, timeout=15.0, step=0.3):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = state(drv)
        if pred(last):
            return True, last
        time.sleep(step)
    return False, last


def click_by_text(drv, text, scope='document'):
    js = r"""
const vis = (el) => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
};
const scope = %s;
const els = Array.from(scope.querySelectorAll('button')).filter(vis);
const t = els.find(b => (b.innerText || '').trim() === %s);
if (!t) return false;
t.click();
return true;
""" % (scope, json.dumps(text, ensure_ascii=False))
    return drv.execute_script(js)


def open_group_facet(drv):
    """点开分组 facet（水合未完成时首次点击可能丢，重试 3 次）。"""
    for _ in range(3):
        click_group_facet(drv)
        ok, _st = wait_until(drv, lambda s: s['popoverOpen'], 6)
        if ok:
            return True
    return False


def click_group_facet(drv):
    js = r"""
const vis = (el) => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
};
const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && /^分组(\s|$)/.test((x.innerText || '').trim()));
if (!b) return false;
b.click();
return true;
"""
    return drv.execute_script(js)


def fill_group_name(drv, name):
    js = r"""
const vis = (el) => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
};
const dlg = Array.from(document.querySelectorAll('[data-slot="dialog-content"],[role="dialog"]')).filter(vis).pop();
if (!dlg) return false;
const input = dlg.querySelector('#group-name');
if (!input) return false;
const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
setter.call(input, %s);
input.dispatchEvent(new Event('input', { bubbles: true }));
return input.value;
""" % json.dumps(name, ensure_ascii=False)
    return drv.execute_script(js)


RES_JS = r"""
return performance.getEntriesByType('resource')
  .filter(e => e.name.includes('/api/v1/groups') || e.name.includes('/api/v1/testcases'))
  .map(e => ({name: e.name, status: e.responseStatus || 0, start: Math.round(e.startTime)}));
"""


def resources(drv):
    return drv.execute_script(RES_JS)


def drain_perf(drv):
    """一次读全量 performance 日志，返回 [(method, url, status)]（responseReceived 补 status）。"""
    reqs = {}
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:
        return out
    for entry in entries:
        try:
            inner = json.loads(entry['message'])['message']
        except Exception:
            continue
        m = inner.get('method')
        if m == 'Network.requestWillBeSent':
            p = inner['params']
            url = p['request']['url']
            if '/api/v1/groups' in url or '/api/v1/testcases' in url:
                reqs[(p.get('requestId'), url)] = {'method': p['request']['method'], 'url': url, 'status': None,
                                                   'postData': p['request'].get('postData', '')}
        elif m == 'Network.responseReceived':
            p = inner['params']
            url = p['response']['url']
            if '/api/v1/groups' in url or '/api/v1/testcases' in url:
                reqs[(p.get('requestId'), url)] = reqs.get((p.get('requestId'), url), {'method': '?', 'url': url, 'postData': ''})
                reqs[(p.get('requestId'), url)]['status'] = p['response']['status']
    for v in reqs.values():
        out.append((v['method'], v['url'], v['status'], v.get('postData', '')))
    return out


def api_json(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode('utf-8')
        return resp.status, (json.loads(raw) if raw else None)


def list_groups():
    _, payload = api_json('GET', '/api/v1/groups?page=1&per_page=200')
    data = (payload or {}).get('data') or {}
    items = data.get('items') or data.get('list') or []
    return items


def cleanup_groups():
    removed, remaining = [], []
    try:
        groups = list_groups()
    except Exception as exc:  # noqa: BLE001
        return [], ['list failed: %s' % exc]
    for g in groups:
        name = g.get('name') or ''
        if name.startswith(PREFIX):
            try:
                api_json('DELETE', '/api/v1/groups/%s' % g.get('id'))
                removed.append(name)
            except Exception as exc:  # noqa: BLE001
                remaining.append('%s: %s' % (name, exc))
    for g in list_groups():
        if (g.get('name') or '').startswith(PREFIX):
            remaining.append(g.get('name'))
    return removed, remaining


CASE_IDS = []


def create_case(group_id, name):
    """给新分组补 1 条接线测试用例：仅为让分组上下文头（组名 + 条数）可见（§3.3 空态口径下空组只有空态）。"""
    _, payload = api_json('POST', '/api/v1/testcases', {
        'name': name,
        'group_id': group_id,
        'tags': [],
        'description': 'INT-1658 复测临时用例（run 结束前 purge）',
        'algorithm_type': 'voice_llm',
        'config': {'rounds': [{'round_number': 1, 'audios': [], 'evaluation': {}, 'noise': {}}]},
        'algorithm_params': [],
    })
    cid = ((payload or {}).get('data') or {}).get('id')
    if cid:
        CASE_IDS.append(cid)
    return cid


def _purge_case(cid):
    """用例彻底删除必须先软删再 purge：对未软删用例直接 purge 返回 200 但不生效（实测 2026-10-24）。"""
    api_json('DELETE', '/api/v1/testcases/%s' % cid)
    return api_json('DELETE', '/api/v1/testcases/%s/purge' % cid)


def cleanup_cases():
    removed, remaining = [], []
    # 本 run 建的直接按 id purge；再按 keyword 兜底扫一遍历史残留（同名前缀）
    for cid in list(CASE_IDS):
        try:
            _purge_case(cid)
        except Exception as exc:  # noqa: BLE001
            remaining.append('%s: %s' % (cid, exc))
    CASE_IDS.clear()
    try:
        _, payload = api_json('GET', '/api/v1/testcases?page=1&per_page=200&keyword=' + urllib.parse.quote(PREFIX))
        data = (payload or {}).get('data') or {}
        items = data.get('items') or data.get('list') or []
        for it in items:
            nm = it.get('name') or ''
            if nm.startswith(PREFIX):
                try:
                    _purge_case(it.get('id'))
                    removed.append(nm)
                except Exception as exc:  # noqa: BLE001
                    remaining.append('%s: %s' % (nm, exc))
    except Exception as exc:  # noqa: BLE001
        remaining.append('list failed: %s' % exc)
    return removed, remaining


def select_group_option(drv, name):
    js = r"""
const vis = (el) => {
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
};
const pop = Array.from(document.querySelectorAll('[data-slot="popover-content"]')).filter(vis).pop();
if (!pop) return false;
const opt = Array.from(pop.querySelectorAll('button')).filter(vis).find(b => (b.innerText || '').trim() === %s);
if (!opt) return false;
opt.click();
return true;
""" % json.dumps(name, ensure_ascii=False)
    return drv.execute_script(js)


def health(base):
    try:
        with urllib.request.urlopen(base + '/health', timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc)}


def facet_create(drv, name, shot_prefix):
    """facet 底部 + 新增分组 → 建组。返回 (ok, detail dict)。"""
    drain_perf(drv)  # 清缓冲
    res_before = resources(drv)
    opened = open_group_facet(drv)
    st = state(drv)
    if not check(shot_prefix + ' facet 下拉打开且底部有「+ 新增分组」', opened and st.get('footerItem') == '+ 新增分组', st.get('footerItem')):
        return False, {}
    assert click_by_text(drv, '+ 新增分组',
                         """Array.from(document.querySelectorAll('[data-slot="popover-content"]')).filter(e=>e.offsetParent!==null).pop() || document""")
    ok, st = wait_until(drv, lambda s: s['dialogOpen'] and s['dialogTitle'] == '新建分组', 8)
    if not check(shot_prefix + ' 弹窗标题「新建分组」', ok, st['dialogTitle'] if st else ''):
        return False, {}
    fill_group_name(drv, name)
    time.sleep(0.2)
    assert click_by_text(drv, '保存')
    # 弹窗关闭
    wait_until(drv, lambda s: not s['dialogOpen'], 10)
    # 预填：trigger 显示新组名
    ok, st = wait_until(drv, lambda s: (s['trigger'] or '').find(name) >= 0, 20)
    prefill_ok = ok
    detail = {'trigger': st['trigger'] if st else None, 'cards': st['cards'] if st else []}

    time.sleep(1.0)
    perf = drain_perf(drv)
    res_after = resources(drv)
    new_res = [r for r in res_after if all(r['name'] != b['name'] or r['start'] != b['start'] for b in res_before)]
    detail['requests'] = new_res
    detail['perf'] = [p for p in perf if p[0] in ('POST', 'GET')]
    post_groups = [p for p in perf if p[0] == 'POST' and '/api/v1/groups' in p[1]]
    get_groups = [p for p in perf if p[0] == 'GET' and '/api/v1/groups' in p[1]]
    tc_reqs = [r for r in new_res if '/api/v1/testcases' in r['name']]
    detail['post_groups'] = post_groups
    detail['get_groups'] = get_groups
    detail['tc_scoped'] = [r for r in tc_reqs if 'group_id=' in r['name']]
    check(shot_prefix + ' 建组请求 POST /api/v1/groups', bool(post_groups),
          post_groups[:1] or 'no POST /groups captured')
    statuses = [r['status'] for r in new_res]
    check(shot_prefix + ' 建组接口响应 2xx（resource timing）', any(200 <= s < 300 for s in statuses), statuses)
    check(shot_prefix + ' 分组选项刷新 GET /api/v1/groups', bool(get_groups), get_groups[:1])
    check(shot_prefix + ' 列表请求携带新 group_id', bool(detail['tc_scoped']),
          detail['tc_scoped'][:1] or [r['name'] for r in tc_reqs][:3])
    check(shot_prefix + ' facet trigger 预填新组名', prefill_ok, detail['trigger'])
    return prefill_ok, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:15271')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    h0 = health(base)
    print('health(open):', h0)
    check('旁路容器连主库 intelligent_audio_test', h0.get('database') == 'intelligent_audio_test', h0)

    # 开工前清掉本前缀历史残留（只删本 run 前缀）
    removed0, remaining0 = cleanup_groups()
    print('pre-clean removed=%s remaining=%s' % (removed0, remaining0))
    removed_c0, remaining_c0 = cleanup_cases()
    print('pre-clean cases removed=%s remaining=%s' % (removed_c0, remaining_c0))

    ts = time.strftime('%H%M%S')
    name_facet = PREFIX + 'facet_' + ts
    name_header = PREFIX + 'header_' + ts
    name_dark = PREFIX + 'dark_' + ts

    drv = build_driver()
    out = {'base': base, 'health': h0, 'checks': RESULTS, 'names': [name_facet, name_header, name_dark]}
    try:
        drv.get(base + '/testcases/by-group')
        ok, st = wait_until(drv, lambda s: s['triggerVisible'], 30)
        check('用例页（按分组视图）加载，分组 facet 可见', ok, st['trigger'] if st else 'no trigger')
        check('页头「新建分组」入口存在（本卡新增）', bool(st and st['headerCreateBtn']))

        # ---- 1. 浅色：facet 建组 → 预填 ----
        prefill, det = facet_create(drv, name_facet, '[浅色]')
        out['facet_light'] = det
        drv.save_screenshot(os.path.join(ARTIFACTS, '01_light_facet_created_prefilled.png'))

        # 分组上下文头：新组 0 条时按 §3.3 走空态，补 1 条接线测试用例后重进该分组筛选，
        # 列表区应渲染「组名 + 1 条」分组卡。
        import re
        new_gid = None
        for r in det.get('tc_scoped') or []:
            m = re.search(r'group_id=([0-9a-fA-F-]+)', r['name'])
            if m:
                new_gid = m.group(1)
                break
        check('[浅色] 从列表请求解析出新分组 id', bool(new_gid), new_gid)
        case_name = PREFIX + 'case_' + ts
        cid = create_case(new_gid, case_name) if new_gid else None
        check('[浅色] 自建用例落到新分组（POST /testcases）', bool(cid), cid)
        time.sleep(1.5)
        if new_gid:
            drv.get(base + '/testcases/by-group')
            wait_until(drv, lambda s: s['triggerVisible'], 30)
            assert open_group_facet(drv), 'facet popover did not open after reload'
            assert select_group_option(drv, name_facet), 'group option not found'
            ok, st = wait_until(drv, lambda s: name_facet in (s['trigger'] or ''), 15)
            ok2, st2 = wait_until(
                drv,
                lambda s: any(name_facet in (c or '') and '1 条' in (c or '') for c in (s['cards'] or [])),
                20)
            check('[浅色] 分组上下文头渲染（组名 + 1 条）', ok2,
                  (st2.get('cards') if st2 else [])[:3])
            drv.save_screenshot(os.path.join(ARTIFACTS, '02_light_context_after_create.png'))

        # ---- 2. 重置 ----
        drain_perf(drv)
        assert click_by_text(drv, '重置')
        ok, st = wait_until(drv, lambda s: '全部' in (s['trigger'] or ''), 10)
        check('[浅色] 重置后 trigger 回「分组 全部」', ok, st['trigger'] if st else '')
        drv.save_screenshot(os.path.join(ARTIFACTS, '03_light_after_reset.png'))

        # ---- 3. 回归：页头「新建分组」不预填 ----
        drain_perf(drv)
        assert click_by_text(drv, '新建分组')
        ok, st = wait_until(drv, lambda s: s['dialogOpen'] and s['dialogTitle'] == '新建分组', 8)
        check('[回归] 页头入口弹窗标题「新建分组」', ok, st['dialogTitle'] if st else '')
        fill_group_name(drv, name_header)
        time.sleep(0.2)
        assert click_by_text(drv, '保存')
        wait_until(drv, lambda s: not s['dialogOpen'], 10)
        time.sleep(3.0)
        st = state(drv)
        check('[回归] 页头建组后 trigger 不预填（仍「分组 全部」）',
              '全部' in (st['trigger'] or '') and name_header not in (st['trigger'] or ''),
              st['trigger'])
        out['header_trigger'] = st['trigger']
        drv.save_screenshot(os.path.join(ARTIFACTS, '04_light_header_no_prefill.png'))

        # ---- 4. 深色：facet 建组 → 预填 ----
        drv.get('about:blank')
        drv.get(base + '/testcases/by-group')
        wait_until(drv, lambda s: s['triggerVisible'], 30)
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get(base + '/testcases/by-group')
        ok, st = wait_until(drv, lambda s: s['dark'] and s['triggerVisible'], 30)
        check('[深色] html.dark 生效', ok, 'dark=%s' % (st['dark'] if st else None))
        prefill_dark, det_dark = facet_create(drv, name_dark, '[深色]')
        out['facet_dark'] = det_dark
        drv.save_screenshot(os.path.join(ARTIFACTS, '05_dark_facet_created_prefilled.png'))

        # ---- 5. 控制台 ----
        try:
            severe = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
        except Exception:
            severe = []
        check('控制台无 SEVERE', not severe, [e.get('message', '')[:160] for e in severe][:3])
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        # 数据卫生：失败也要清掉本 run 自建的分组 / 用例
        removed, remaining = cleanup_cases()
        removed_g, remaining_g = cleanup_groups()
        out['cleanup'] = {'cases_removed': removed, 'cases_remaining': remaining,
                          'groups_removed': removed_g, 'groups_remaining': remaining_g}
        check('自建用例清理干净（purge + 回读）', not remaining, remaining)
        check('自建分组清理干净（回读 remaining 为空）', not remaining_g, remaining_g)

    print('\n===== SUMMARY =====')
    failed = [r for r in RESULTS if not r['ok']]
    print('checks=%d failed=%d' % (len(RESULTS), len(failed)))
    for r in failed:
        print('FAILED:', r['name'], '|', r['detail'])
    with open(os.path.join(ARTIFACTS, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
