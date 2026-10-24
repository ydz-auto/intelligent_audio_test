# -*- coding: utf-8 -*-
"""INT-1506 审返 P1 复测：批量设置评估维度在「轮次未知」下可勾选、可提交，清空前二次确认。

复测范围（只测代码审计打回项与本次修复相关部分）：
  P1-1 ① 分组不展开 → 组头「全选分组」→ 浮条「批量设置评估维度」
  P1-1 ② 分组部分加载（展开后只加载首页 20 条）→ 全选分组
  P1-1 ③ 未选维度点「确定」→ 二次确认（后端空数组=清空），确认前不发请求
  P3-1   轮次全部未加载时「指定轮次 / 逐轮设置」两档禁用

断言口径（不只看 DOM 有元素，看可见状态与真实载荷）：
  - 维度 chip 点击后 aria-pressed=true、可见「已选 N 项」计数 > 0、参数卡出现；
  - 提交载荷 dimensions 非空、条数与已选一致、每项带 id/name/weight/threshold，
    round_mode=all，维度 id 均存在于真实 GET /evaluation/dimensions。

写库纪律：批量提交请求在页内被拦截（记录请求体后回成功信封），不向真实库写入；
本脚本对真实库只读。

用法：
  REACT_BASE=http://127.0.0.1:15290 python verify_int1506_p1_retest.py
"""
import json
import os
import re
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15290')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_CACHE = os.path.join(
    os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
ART = os.environ.get('INT1506_ART') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1506_p1_retest')
os.makedirs(ART, exist_ok=True)

TAG = os.environ.get('INT1506_TAG', 'fixed')
RESULTS = []


def log(*args):
    print(' '.join(str(a) for a in args), flush=True)


def check(name, ok, detail=''):
    RESULTS.append({'tag': TAG, 'name': name, 'ok': bool(ok), 'detail': str(detail)[:900]})
    log(('PASS' if ok else 'FAIL'), '[%s]' % TAG, name, detail)
    return bool(ok)


# ── 只读接口 ───────────────────────────────────────────────────────────
def api_get(path, timeout=240, tries=4):
    """网关偶发 400/504：重试到成功为止（只读接口，可安全重试）。"""
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(API + path, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as exc:  # noqa: BLE001
            last = exc
            log('api retry', i + 1, path[:60], exc)
            time.sleep(2.0)
    raise last


def group_page(gid):
    return api_get('/testcases?page=1&per_page=20&group_id=%s' % gid)


def api_context():
    groups = api_get('/groups?per_page=200')['data']['items']
    wanted = os.environ.get('INT1506_GROUP', '打断与恢复')
    grp = next((g for g in groups if g.get('name') == wanted), None)
    if grp is None or not group_page(grp['id'])['data']['total']:
        # 兜底：逐个分组探最大条数（真实库分组 DTO 不带 testCaseCount）
        best = (None, 0)
        for g in groups:
            try:
                total = group_page(g['id'])['data']['total']
            except Exception:
                continue
            if total > best[1]:
                best = (g, total)
        grp = best[0] or groups[0]
    gid = grp['id']
    gpage = group_page(gid)
    loaded = gpage['data']['items']
    rounds = [len((it.get('config') or {}).get('rounds') or []) for it in loaded]
    dims = api_get('/evaluation/dimensions?page=1&per_page=200')['data']
    dim_items = dims['items'] if isinstance(dims, dict) else dims
    ctx = {
        'group_name': grp['name'],
        'group_id': gid,
        'group_total': gpage['data']['total'],
        'group_loaded': len(loaded),
        'group_rounds': sorted(set(rounds)),
        'dim_ids': sorted({int(d['id']) for d in dim_items}),
        'dim_names': {int(d['id']): d.get('name') for d in dim_items},
    }
    log('api context', json.dumps({k: (v if k != 'dim_names' else len(v))
                                   for k, v in ctx.items()}, ensure_ascii=False))
    return ctx


# ── 浏览器 ────────────────────────────────────────────────────────────
def chromedriver_path():
    if not os.path.isdir(DRIVER_CACHE):
        return None
    cands = []
    for ver in os.listdir(DRIVER_CACHE):
        exe = os.path.join(DRIVER_CACHE, ver, 'chromedriver.exe')
        if os.path.isfile(exe):
            cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
    return max(cands)[1] if cands else None


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    exe = chromedriver_path()
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_script_timeout(120)
    return d


def wait(d, sec=90):
    return WebDriverWait(d, sec)


def body_text(d):
    return d.execute_script('return document.body.textContent') or ''


def dialog_el(d):
    els = d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
    return els[-1] if els else None


def dialog_text(d):
    el = dialog_el(d)
    return (el.text if el else '') or ''


def shot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    log('shot', path)
    return path


# 页内拦截批量提交：记录请求体，回成功信封（不写真实库）
STUB_JS = r"""
(() => {
  if (window.__IAT_BATCH_HOOK) { window.__IAT_BATCH = []; return 'already'; }
  window.__IAT_BATCH = [];
  const orig = window.fetch;
  window.__IAT_BATCH_HOOK = true;
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.indexOf('/testcases/batch') >= 0) {
      window.__IAT_BATCH.push({ url: url, body: (init && init.body) || '' });
      return new Response(
        JSON.stringify({ success: true, code: 0, message: 'ok', data: { updated_count: 0 } }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }
    return orig.apply(this, arguments);
  };
  return 'installed';
})()
"""


def set_theme(d, mode):
    d.get(BASE + '/testcases/by-group')
    wait(d, 120).until(lambda x: x.execute_script('return document.readyState') == 'complete')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def enter_cases(d):
    d.get(BASE + '/testcases/by-group')
    wait(d, 180).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']")))
    time.sleep(2.0)
    d.execute_script(STUB_JS)


def expand_group(d, name):
    wait(d, 120).until(lambda x: name in body_text(x))
    for attempt in range(3):
        state = d.execute_script(
            """
            const name = arguments[0];
            const leaves = [...document.querySelectorAll('span,div')]
              .filter(e => e.children.length === 0 && (e.textContent || '').trim() === name);
            for (const leaf of leaves) {
              let p = leaf;
              for (let i = 0; i < 6 && p; i++) {
                const cls = String(p.className || '');
                if (cls.includes('cursor-pointer')) {
                  p.scrollIntoView({block: 'center'});
                  p.click();
                  return 'ok';
                }
                p = p.parentElement;
              }
            }
            return 'not-found';
            """, name)
        log('expand group', name, state, 'attempt', attempt + 1)
        if state != 'ok':
            raise AssertionError('分组未找到：%s' % name)
        try:
            wait(d, 30).until(lambda x: x.execute_script(
                "return document.querySelectorAll(\"button[aria-label='编辑用例']\").length > 0"))
            time.sleep(1.5)
            return
        except Exception:
            time.sleep(2.0)
    raise AssertionError('分组展开后未加载用例卡')


def select_whole_group(d, name):
    el = wait(d, 60).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "[role='checkbox'][aria-label='全选分组 %s']" % name)))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    # POST /testcases/ids 往返
    wait(d, 90).until(lambda x: x.execute_script(
        "return [...document.querySelectorAll('button')].some(b => (b.textContent||'').trim() === '批量设置评估维度');"))
    time.sleep(1.0)


def open_dimensions(d):
    btn = wait(d, 60).until(EC.presence_of_element_located(
        (By.XPATH, "//button[normalize-space(.)='批量设置评估维度']")))
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', btn)
    wait(d, 60).until(lambda x: bool(dialog_el(x)))
    time.sleep(1.2)


def radio_disabled(d, label):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return 'dialog-missing';
        const lab = [...dlg.querySelectorAll('label')]
          .find(l => (l.textContent || '').trim().indexOf(arguments[0]) >= 0);
        if (!lab) return 'label-missing';
        const input = lab.querySelector("input[type='radio']");
        return input ? !!input.disabled : 'input-missing';
        """, label)


def radio_checked(d, label):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return 'dialog-missing';
        const lab = [...dlg.querySelectorAll('label')]
          .find(l => (l.textContent || '').trim().indexOf(arguments[0]) >= 0);
        if (!lab) return 'label-missing';
        const input = lab.querySelector("input[type='radio']");
        return input ? !!input.checked : 'input-missing';
        """, label)


def ok_button_enabled(d):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return null;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '确定');
        return btn ? !btn.disabled : null;
        """)


def click_first_dimension(d):
    """点 round cloud 里第一个未选中的维度 chip；返回点击前后的可见状态。"""
    before = d.execute_script(
        """
        const root = document.querySelector("[data-testid='batch-dim-round-cloud']");
        if (!root) return {cloud: false};
        const m = (root.textContent || '').match(/已选\\s*(\\d+)\\s*项/);
        return {cloud: true, count: m ? Number(m[1]) : null};
        """)
    info = d.execute_script(
        """
        const root = document.querySelector("[data-testid='batch-dim-round-cloud']");
        if (!root) return {clicked: false, why: 'cloud-missing'};
        const chip = [...root.querySelectorAll('button')]
          .find(b => b.getAttribute('aria-pressed') === 'false' && (b.textContent || '').trim().length > 1);
        if (!chip) return {clicked: false, why: 'chip-missing'};
        chip.scrollIntoView({block: 'center'});
        chip.click();
        window.__IAT_CLICKED_CHIP = (chip.textContent || '').trim();
        return {clicked: true, label: (chip.textContent || '').trim()};
        """)
    time.sleep(1.0)
    after = d.execute_script(
        """
        const root = document.querySelector("[data-testid='batch-dim-round-cloud']");
        if (!root) return {cloud: false};
        const m = (root.textContent || '').match(/已选\\s*(\\d+)\\s*项/);
        const pressed = [...root.querySelectorAll("button[aria-pressed='true']")]
          .map(b => (b.textContent || '').trim());
        return {cloud: true, count: m ? Number(m[1]) : null, pressed: pressed,
                label: window.__IAT_CLICKED_CHIP || ''};
        """)
    return before, info, after


def param_card_text(d):
    return d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return '';
        return (dlg.textContent || '');
        """)


def click_ok(d):
    d.execute_script(
        """
        const dlg = [...document.querySelectorAll("[role='dialog']")].pop();
        if (!dlg) return;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '确定');
        if (btn) btn.click();
        """)
    time.sleep(2.0)


def captured_batch(d):
    raw = d.execute_script('return JSON.stringify(window.__IAT_BATCH || []);')
    try:
        return json.loads(raw)
    except Exception:
        return []


def close_dialog(d):
    d.execute_script(
        """
        const dlgs = [...document.querySelectorAll("[role='dialog']")];
        const dlg = dlgs.pop();
        if (!dlg) return;
        const btn = [...dlg.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '取消');
        if (btn) btn.click();
        """)
    time.sleep(1.0)


def alertdialog_text(d):
    return d.execute_script(
        """
        const el = [...document.querySelectorAll("[role='alertdialog']")].pop();
        return el ? (el.textContent || '') : '';
        """)


def alertdialog_click(d, label):
    return d.execute_script(
        """
        const el = [...document.querySelectorAll("[role='alertdialog']")].pop();
        if (!el) return 'missing';
        const btn = [...el.querySelectorAll('button')].find(b => (b.textContent || '').trim() === arguments[0]);
        if (!btn) return 'button-missing';
        btn.click();
        return 'clicked';
        """, label)


def parse_payload(reqs):
    if not reqs:
        return {}
    try:
        return json.loads(reqs[-1]['body'])
    except Exception:
        return {}


def unknown_notice(d):
    return d.execute_script(
        """
        const el = document.querySelector("[data-testid='batch-dim-rounds-unknown']");
        return el ? (el.textContent || '').trim() : '';
        """)


# ── 场景 ──────────────────────────────────────────────────────────────
def scenario_a(d, ctx, theme):
    """① 分组不展开 → 全选分组（组内 0 条加载）→ 可勾选、可提交非空维度。"""
    enter_cases(d)
    select_whole_group(d, ctx['group_name'])
    open_dimensions(d)
    text = dialog_text(d)

    check('[%s] A1 弹窗按全组条数识别勾选' % theme,
          ('您勾选了 %d 个用例' % ctx['group_total']) in text,
          [ln for ln in text.splitlines() if '勾选' in ln][:1])
    notice = unknown_notice(d)
    m = re.search(r'(\d+)\s*个用例的轮次信息尚未加载', notice)
    check('[%s] A2 未加载条数 == 全组 %d（组内一条都没加载）' % (theme, ctx['group_total']),
          bool(m) and int(m.group(1)) == ctx['group_total'], notice)
    check('[%s] A3 不出现「暂无可配置的轮次信息」假空态' % theme,
          '暂无可配置的轮次信息' not in text, '')
    check('[%s] A4 默认档位「所有轮次」' % theme,
          radio_checked(d, '所有轮次（统一设置）') is True,
          radio_checked(d, '所有轮次（统一设置）'))
    check('[%s] A5 指定轮次档禁用（P3-1）' % theme,
          radio_disabled(d, '指定轮次（统一设置）') is True,
          radio_disabled(d, '指定轮次（统一设置）'))
    check('[%s] A6 逐轮设置档禁用（P3-1）' % theme,
          radio_disabled(d, '逐轮设置（每轮可不同）') is True,
          radio_disabled(d, '逐轮设置（每轮可不同）'))
    check('[%s] A7 确定可点' % theme, ok_button_enabled(d) is True, ok_button_enabled(d))

    before, info, after = click_first_dimension(d)
    check('[%s] A8 点维度 chip 真的勾上（已选 %s → %s）' % (
        theme, before.get('count'), after.get('count')),
        info.get('clicked') and (before.get('count') == 0) and (after.get('count') or 0) > 0,
        json.dumps({'before': before, 'info': info, 'after': after}, ensure_ascii=False))
    check('[%s] A9 chip 选中态 aria-pressed=true 且计数与已选一致' % theme,
          bool(after.get('pressed')) and after.get('count') == len(after.get('pressed') or []),
          json.dumps(after, ensure_ascii=False))
    check('[%s] A10 已选维度参数卡出现' % theme,
          '维度权重和阈值配置' in param_card_text(d), '')

    path = shot(d, 'A_unknown_rounds_%s.png' % theme)

    before_ok = len(captured_batch(d))
    click_ok(d)
    reqs = captured_batch(d)
    body = parse_payload(reqs)
    dims = body.get('dimensions') or []
    selected_n = after.get('count') or 0
    check('[%s] A11 提交载荷 dimensions 非空（%d 项，与已选 %s 一致）' % (
        theme, len(dims), selected_n),
        len(reqs) > before_ok and len(dims) == selected_n and selected_n > 0,
        json.dumps(body, ensure_ascii=False)[:700])
    check('[%s] A12 载荷 round_mode=all' % theme, body.get('round_mode') == 'all',
          body.get('round_mode'))
    bad = [x for x in dims if not isinstance(x, dict) or 'id' not in x or 'name' not in x
           or 'weight' not in x or 'threshold' not in x]
    check('[%s] A13 每条维度带 id/name/weight/threshold' % theme, bool(dims) and not bad,
          json.dumps(bad[:3], ensure_ascii=False))
    unknown = [x for x in dims if int(x.get('id')) not in set(ctx['dim_ids'])]
    check('[%s] A14 载荷维度 id 均来自真实 GET /evaluation/dimensions' % theme,
          bool(dims) and not unknown, json.dumps(unknown[:3], ensure_ascii=False))
    check('[%s] A15 载荷 multi_dimensions 字段存在（空数组=清空整体维度）' % theme,
          isinstance(body.get('multi_dimensions'), list),
          json.dumps(body.get('multi_dimensions'), ensure_ascii=False)[:200])
    close_dialog(d)
    return path


def scenario_b(d, ctx, theme):
    """② 分组展开（只加载首页 20 条）→ 全选分组 → 仍可勾选、可提交。"""
    enter_cases(d)
    expand_group(d, ctx['group_name'])
    loaded = d.execute_script(
        "return document.querySelectorAll(\"button[aria-label='编辑用例']\").length")
    select_whole_group(d, ctx['group_name'])
    open_dimensions(d)
    text = dialog_text(d)
    notice = unknown_notice(d)
    m = re.search(r'(\d+)\s*个用例的轮次信息尚未加载', notice)
    expect_unknown = ctx['group_total'] - loaded

    check('[%s] B1 组内只加载 %d 条（全组 %d）' % (theme, loaded, ctx['group_total']),
          0 < loaded < ctx['group_total'], 'loaded=%s' % loaded)
    check('[%s] B2 弹窗识别全组 %d 条' % (theme, ctx['group_total']),
          ('您勾选了 %d 个用例' % ctx['group_total']) in text,
          [ln for ln in text.splitlines() if '勾选' in ln][:1])
    check('[%s] B3 未加载条数 == %d' % (theme, expect_unknown),
          bool(m) and int(m.group(1)) == expect_unknown, notice)

    before, info, after = click_first_dimension(d)
    check('[%s] B4 部分加载下点维度 chip 真的勾上（已选 %s）' % (theme, after.get('count')),
          info.get('clicked') and (after.get('count') or 0) > 0,
          json.dumps({'before': before, 'after': after}, ensure_ascii=False))

    path = shot(d, 'B_partial_rounds_%s.png' % theme)

    click_ok(d)
    body = parse_payload(captured_batch(d))
    dims = body.get('dimensions') or []
    check('[%s] B5 载荷 dimensions 非空（%d 项）' % (theme, len(dims)),
          len(dims) == (after.get('count') or 0) and len(dims) > 0,
          json.dumps(body, ensure_ascii=False)[:700])
    check('[%s] B6 载荷 round_mode=all' % theme, body.get('round_mode') == 'all',
          body.get('round_mode'))
    close_dialog(d)
    return path


def scenario_c(d, ctx, theme):
    """③ 未选维度点确定 → 二次确认，确认前不发请求；取消不写、确认才发空数组。"""
    enter_cases(d)
    select_whole_group(d, ctx['group_name'])
    open_dimensions(d)
    d.execute_script('window.__IAT_BATCH = [];')
    click_ok(d)
    atext = alertdialog_text(d)
    check('[%s] C1 未选维度点确定先弹二次确认' % theme,
          '确定清空所选用例的评估维度' in atext, atext[:200])
    check('[%s] C2 确认前不发送清空请求' % theme, captured_batch(d) == [], captured_batch(d))
    path = shot(d, 'C_clear_guard_%s.png' % theme)

    # 取消 → 弹窗仍在、仍无请求
    alertdialog_click(d, '取消')
    time.sleep(0.8)
    check('[%s] C3 取消后回到维度弹窗且仍未发请求' % theme,
          bool(dialog_el(d)) and captured_batch(d) == [],
          'dialog=%s reqs=%s' % (bool(dialog_el(d)), captured_batch(d)))

    # 再次点确定并确认 → 才发送（空 dimensions = 清空语义，后端约定），页内拦截不落库
    click_ok(d)
    clicked = alertdialog_click(d, '确定清空')
    check('[%s] C4 二次确认弹窗有「确定清空」按钮' % theme, clicked == 'clicked', clicked)
    time.sleep(2.0)
    reqs = captured_batch(d)
    body = parse_payload(reqs)
    check('[%s] C5 确认后才发送清空请求（dimensions 为空数组）' % theme,
          len(reqs) == 1 and (body.get('dimensions') == []),
          json.dumps(body, ensure_ascii=False)[:400])
    return path


def console_errors(d):
    errs = []
    try:
        for entry in d.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                errs.append((entry.get('message') or '')[:200])
    except Exception:
        pass
    return errs


def real_api_hits(d, ctx):
    """证据：页面真实请求了 groups / testcases / dimensions（无 mock）。"""
    hits = []
    for entry in d.get_log('performance'):
        try:
            msg = json.loads(entry['message']).get('message') or {}
            if msg.get('method') != 'Network.responseReceived':
                continue
            resp = msg.get('params', {}).get('response', {})
            url = resp.get('url', '')
            if '/api/v1/' in url:
                hits.append({'path': url.split('/api/v1')[-1].split('?')[0],
                             'status': resp.get('status')})
        except Exception:
            continue
    return hits


def main():
    only = [s.strip().upper() for s in os.environ.get('SCENARIOS', 'A,B,C').split(',') if s.strip()]
    ctx = api_context()
    d = driver()
    shots = []
    try:
        if 'A' in only:
            shots.append(scenario_a(d, ctx, 'light'))
            set_theme(d, 'dark')
            shots.append(scenario_a(d, ctx, 'dark'))
        if 'B' in only:
            set_theme(d, 'light')
            shots.append(scenario_b(d, ctx, 'light'))
            set_theme(d, 'dark')
            shots.append(scenario_b(d, ctx, 'dark'))
        if 'C' in only:
            shots.append(scenario_c(d, ctx, 'light'))

        hits = real_api_hits(d, ctx)
        paths = {h['path'] for h in hits if h['status'] == 200}
        check('页面真实请求 groups / testcases / evaluation/dimensions（无 mock）',
              any(p.startswith('/groups') for p in paths)
              and any(p.startswith('/testcases') for p in paths)
              and any(p.startswith('/evaluation/dimensions') for p in paths),
              sorted(p for p in paths)[:12])
        errs = console_errors(d)
        check('浏览器控制台无 SEVERE 错误', not errs, errs[:3])

        failed = [r for r in RESULTS if not r['ok']]
        out = os.path.join(ART, 'result_%s.json' % TAG)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'tag': TAG, 'base': BASE, 'api': {k: v for k, v in ctx.items() if k != 'dim_ids'},
                       'checks': RESULTS, 'screenshots': shots,
                       'api_hits': [h for h in hits if h['status'] == 200][-20:]},
                      f, ensure_ascii=False, indent=2)
        log('result', out)
        log('SUMMARY', 'PASS' if not failed else 'FAIL %d' % len(failed))
        return 0 if not failed else 1
    finally:
        d.quit()


if __name__ == '__main__':
    raise SystemExit(main())
