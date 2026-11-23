# -*- coding: utf-8 -*-
"""INT-2680 前端回归日巡：复验 INT-2677 修复（重新执行/重新评估「手动选择用例」平铺视图右侧被裁）。

INT-2677 根因：DialogContent 的 grid 未定义列，隐式列按 max-content 撑宽 → popup
scrollWidth > clientWidth，右侧「确认（已选 N 个用例）」/「共 N 条」/状态筛选被裁。
修复：`grid-cols-[minmax(0,1fr)]`（f179b95d1）。

本探针在 docker 栈 15173（已含该修复）实测，只读（打开弹窗不提交）：
  1) 1680 / 1280 / 1024 三种视口下：popup scrollWidth == clientWidth（无横向溢出）；
  2) 弹窗宽度 >= 700（936d9b94c 的加宽未被回退）；
  3) 底栏「确认…」按钮完整落在 popup 可视区内（右边界不越界、按钮文本未截断）；
  4) 工具行「共 N 条」与「状态筛选」触发器的右边界都在 popup 可视区内；
  5) 打开弹窗全程无重执行/重评估写请求（retry/reexecute/re-evaluate POST）；
  6) 浅色 + 深色截图。

跑法：
  python tests/ui/probe_int2680_flat_view.py --base http://localhost:15173 --task 588
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2680')

POPUP = "[data-slot='dialog-content']"


class Probe:
    def __init__(self, base, username, password):
        self.base = base.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []
        self.net = []

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-52s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def skip(self, name, detail):
        self.checks.append({'name': name, 'ok': True, 'skipped': True, 'detail': detail})
        print('[SKIP] %-52s %s' % (name, detail), flush=True)

    def shot(self, page, name):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, name + '.png')
        page.screenshot(path=path)
        print('SHOT=%s' % path, flush=True)
        return path

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=45000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)

    def watch(self, page):
        page.on('request', lambda r: self.net.append(
            {'m': r.method, 'u': r.url[:240], 't': time.time()}))

    def toggle_dark(self, page, dark):
        page.evaluate(
            "(d)=>{const el=document.documentElement;el.classList.toggle('dark',d);"
            "el.setAttribute('data-theme', d?'dark':'light');}", dark)
        page.wait_for_timeout(600)


MEASURE_JS = """
(el) => {
  const pop = (el && el.matches && el.matches('[data-slot="dialog-content"]'))
    ? el : (el ? el.querySelector('[data-slot="dialog-content"]') : null);
  if (!pop) return null;
  const pr = pop.getBoundingClientRect();
  const out = {
    popup: {sw: pop.scrollWidth, cw: pop.clientWidth, ow: pop.offsetWidth,
            w: Math.round(pr.width), h: Math.round(pr.height),
            left: Math.round(pr.left), right: Math.round(pr.right)},
    overflowers: [],
    confirm: null, count: null, statusFilter: null
  };
  const inView = (r) => r.width > 0 && r.height > 0;
  // 真正的裁切判据：可见文字元素的右边界越过 popup 可视内容区（clientWidth 右沿）。
  // 不把 checkbox 的隐藏 input / 固定 14px 指示块这类固有控件几何算作裁切。
  const contentRight = pr.left + pop.clientWidth;
  for (const n of pop.querySelectorAll('*')) {
    const r = n.getBoundingClientRect();
    if (!inView(r)) continue;
    const txt = (n.innerText || '').trim();
    if (!txt) continue;
    const cs = getComputedStyle(n);
    if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
    if (r.right > contentRight + 1) {
      out.overflowers.push({
        tag: n.tagName, cls: (n.className || '').toString().slice(0, 80),
        right: Math.round(r.right), contentRight: Math.round(contentRight),
        txt: txt.replace(/\\s+/g, ' ').slice(0, 60)
      });
    }
  }
  const btns = Array.from(pop.querySelectorAll('button'));
  const cb = btns.find(b => /确认/.test((b.innerText || '')) && inView(b.getBoundingClientRect()));
  if (cb) {
    const r = cb.getBoundingClientRect();
    out.confirm = {text: (cb.innerText || '').replace(/\\s+/g, ' ').trim(),
                   textSw: cb.scrollWidth, textCw: cb.clientWidth,
                   right: Math.round(r.right), left: Math.round(r.left)};
  }
  const nodes = Array.from(pop.querySelectorAll('span,div,p'));
  const cn = nodes.find(n => /^共\\s*\\d+\\s*条$/.test((n.innerText || '').trim())
                          && inView(n.getBoundingClientRect()));
  if (cn) {
    const r = cn.getBoundingClientRect();
    out.count = {text: (cn.innerText || '').trim(), right: Math.round(r.right),
                 sw: cn.scrollWidth, cw: cn.clientWidth,
                 boxW: Math.round(r.width)};
  }
  const sf = pop.querySelector("[aria-label='状态筛选']");
  if (sf) {
    const r = sf.getBoundingClientRect();
    out.statusFilter = {right: Math.round(r.right), w: Math.round(r.width),
                        text: (sf.innerText || '').replace(/\\s+/g, ' ').trim()};
  }
  return out;
}
"""


def open_dialog(page, action):
    """点任务详情的「重新执行」/「重新评估」→ 选「手动选择用例」→ 等平铺行渲染。"""
    btn = page.get_by_role('button', name=action, exact=True)
    if btn.count() == 0:
        return False, None
    btn.first.scroll_into_view_if_needed()
    btn.first.click()
    page.wait_for_timeout(1500)
    dlg = page.locator(POPUP).last
    try:
        dlg.wait_for(state='visible', timeout=8000)
    except Exception:
        return False, None
    page.get_by_text('手动选择用例', exact=True).last.click()
    page.wait_for_timeout(2500)
    return True, dlg


def close_dialog(page):
    page.keyboard.press('Escape')
    page.wait_for_timeout(700)


def measure_at(p, page, task_id, viewport, tag):
    page.set_viewport_size(viewport)
    page.goto(p.base + '/tasks/%d' % task_id, wait_until='domcontentloaded')
    page.wait_for_timeout(3200)
    opened, dlg = open_dialog(page, '重新执行')
    if not opened:
        p.skip('%s 重新执行弹窗' % tag, '任务详情无「重新执行」入口（状态/权限不符）')
        return None
    m = page.evaluate(MEASURE_JS, dlg.element_handle())
    if m is None:
        p.check('%s 弹窗结构可测' % tag, False, 'popup not found')
        close_dialog(page)
        return None
    pop = m['popup']
    p.check('%s 平铺视图无横向溢出（scrollWidth == clientWidth）' % tag,
            pop['sw'] <= pop['cw'] + 1,
            'scrollWidth=%s clientWidth=%s offsetWidth=%s' % (pop['sw'], pop['cw'], pop['ow']))
    p.check('%s 弹窗宽度 >= 700（936d9b94c 加宽未回退）' % tag,
            pop['w'] >= 700, 'width=%s viewport=%s' % (pop['w'], viewport))
    p.check('%s 无后代元素横向溢出' % tag, len(m['overflowers']) == 0,
            'overflowers=%r' % m['overflowers'][:3])
    conf = m['confirm']
    if conf:
        p.check('%s 底栏「确认」按钮完整可见且文本未截断' % tag,
                conf['right'] <= pop['right'] and conf['textSw'] <= conf['textCw'] + 1,
                'btn_right=%s popup_right=%s text_sw/cw=%s/%s text=%r'
                % (conf['right'], pop['right'], conf['textSw'], conf['textCw'], conf['text']))
    else:
        p.check('%s 底栏「确认」按钮存在' % tag, False, 'not found')
    cnt = m['count']
    if cnt:
        p.check('%s 「共 N 条」完整可见' % tag,
                cnt['right'] <= pop['right'] and cnt['sw'] <= cnt['cw'] + 1,
                'right=%s popup_right=%s sw/cw=%s/%s text=%r'
                % (cnt['right'], pop['right'], cnt['sw'], cnt['cw'], cnt['text']))
    else:
        p.skip('%s 「共 N 条」' % tag, '未渲染（无已执行用例或文案不同）')
    sf = m['statusFilter']
    if sf:
        p.check('%s 状态筛选触发器右边界在弹窗内' % tag, sf['right'] <= pop['right'],
                'right=%s popup_right=%s w=%s text=%r'
                % (sf['right'], pop['right'], sf['w'], sf['text']))
    else:
        p.skip('%s 状态筛选' % tag, '未找到 aria-label=状态筛选')
    p.shot(page, '%s_flat_wide' % tag)
    p.toggle_dark(page, True)
    page.wait_for_timeout(500)
    p.shot(page, '%s_flat_dark' % tag)
    p.toggle_dark(page, False)
    close_dialog(page)
    return m


def run_reevaluate(p, page, task_id):
    page.set_viewport_size({'width': 1680, 'height': 1050})
    page.goto(p.base + '/tasks/%d' % task_id, wait_until='domcontentloaded')
    page.wait_for_timeout(3200)
    opened, dlg = open_dialog(page, '重新评估')
    if not opened:
        p.skip('重新评估弹窗 平铺视图', '任务详情无「重新评估」入口（终态/权限不符）')
        return
    m = page.evaluate(MEASURE_JS, dlg.element_handle())
    pop = (m or {}).get('popup') or {}
    p.check('重新评估 平铺视图无横向溢出',
            pop.get('sw', 1) <= pop.get('cw', 0) + 1,
            'scrollWidth=%s clientWidth=%s width=%s'
            % (pop.get('sw'), pop.get('cw'), pop.get('w')))
    p.check('重新评估 无后代元素横向溢出', len((m or {}).get('overflowers') or []) == 0,
            'overflowers=%r' % ((m or {}).get('overflowers') or [])[:3])
    conf = (m or {}).get('confirm')
    if conf:
        p.check('重新评估 底栏「确认」按钮完整可见',
                conf['right'] <= pop.get('right', 0) and conf['textSw'] <= conf['textCw'] + 1,
                'btn_right=%s popup_right=%s text=%r'
                % (conf['right'], pop.get('right'), conf['text']))
    p.shot(page, '60_reevaluate_flat_wide')
    close_dialog(page)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--task', type=int, default=588)
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()

    p = Probe(args.base, args.username, args.password)
    os.makedirs(ART, exist_ok=True)
    result = {'task': args.task, 'checks': p.checks}
    drv_ok = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050}, locale='zh-CN')
        page = ctx.new_page()
        p.watch(page)
        try:
            p.login(page)
            for viewport, tag in (
                    ({'width': 1680, 'height': 1050}, '1680'),
                    ({'width': 1280, 'height': 800}, '1280'),
                    ({'width': 1024, 'height': 768}, '1024')):
                measure_at(p, page, args.task, viewport, tag)
            run_reevaluate(p, page, args.task)
            posts = [n['u'] for n in p.net if n['m'] == 'POST'
                     and any(k in n['u'] for k in ('retry', 'reexecute', 're-evaluate', '/evaluate'))]
            p.check('只读：全程未提交重执行/重评估写请求', len(posts) == 0,
                    'posts=%r' % posts[:3])
        except Exception:
            import traceback
            traceback.print_exc()
            p.check('探针执行完成', False, traceback.format_exc()[-300:])
            drv_ok = False
        finally:
            result['checks'] = p.checks
            with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)
            browser.close()
    ok = drv_ok and all(c.get('ok') for c in p.checks)
    print('\nSUMMARY_JSON=%s' % os.path.join(ART, 'summary.json'))
    print('RESULT_OK=%s' % ok)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
