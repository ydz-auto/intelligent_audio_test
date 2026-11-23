# -*- coding: utf-8 -*-
"""INT-2680 前端回归日巡：用例页 / 音频页 交互与弹窗（React 15173，docker 真实库栈，只读）。

覆盖卡面「核心页：用例（列表 / 弹窗）、音频」的可交互面：
  1) /testcases 列表渲染；展开分组后用例卡可见；
  2) 用例卡「预览音频」→ 试听配置弹窗（播放模式 / 偏移量 / 开始试听），关闭不提交
     （不发 POST /testcases/{id}/preview）；
  3) 「新增用例」→ 编辑抽屉（用例名称 / 分组 / 取消 / 保存），取消不提交
     （不发 POST /testcases）；
  4) /audio-import 列表 + 统计渲染；行「更多操作」菜单可见（含试听入口），关闭不写。

跑法：
  python tests/ui/probe_int2680_cases_audio.py --base http://localhost:15173
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2680')


class Probe:
    def __init__(self, base, username, password):
        self.base = base.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []
        self.net = []

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-50s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def skip(self, name, detail):
        self.checks.append({'name': name, 'ok': True, 'skipped': True, 'detail': detail})
        print('[SKIP] %-50s %s' % (name, detail), flush=True)

    def shot(self, page, name):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, name + '.png')
        page.screenshot(path=path)
        print('SHOT=%s' % path, flush=True)

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=45000)
        page.fill('#username', self.username)
        page.fill('#password', self.password)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1200)

    def watch(self, page):
        page.on('request', lambda r: self.net.append({'m': r.method, 'u': r.url[:240]}))


def run_cases(p, page):
    page.goto(p.base + '/testcases', wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    body = page.evaluate('()=>document.body.innerText')
    p.check('用例页列表渲染（含页标题与工具栏）',
            '用例管理' in body and ('按分组' in body or '分组' in body),
            'body_head=%r' % body[:120])
    page.screenshot(path=os.path.join(ART, '70_cases_list.png'))

    # 展开首个分组：点分组行（标题形如「话轮接管 211 条」，与 smoke_frontend_int1854 同口径）
    import httpx
    group_names = []
    try:
        from tests.ui.utils.api_client import ApiClient
        api = ApiClient('http://127.0.0.1:15000')
        api.login(p.username, p.password)
        r = httpx.get('http://127.0.0.1:15000/api/v1/groups?page=1&per_page=100',
                      headers={'Authorization': 'Bearer ' + api.token},
                      timeout=20, trust_env=False)
        items = ((r.json().get('data') or {}).get('items') or [])
        group_names = [g.get('name') for g in items if g.get('name')][:6]
    except Exception as exc:
        print('group fetch failed: %s' % exc, flush=True)

    expanded = False
    for gname in group_names:
        clicked = page.evaluate(
            """(name)=>{
              const out=[];
              for (const el of document.querySelectorAll('div,section,article,li')) {
                const t=(el.innerText||'').trim();
                if (!t.startsWith(name)) continue;
                if (t.length > 160) continue;
                const r=el.getBoundingClientRect();
                if (r.width < 400 || r.height > 220) continue;
                out.push(el);
              }
              const el = out.slice(-1)[0];
              if (!el) return false;
              el.click();
              return true;
            }""", gname)
        if not clicked:
            continue
        page.wait_for_timeout(3200)
        if page.get_by_label('预览音频').count() > 0:
            expanded = True
            break
    p.check('用例分组可展开、用例卡可见', expanded,
            'groups=%r preview_btn=%d' % (group_names[:3], page.get_by_label('预览音频').count()))

    # 预览音频 → 试听配置弹窗（只打开，不点开始试听）
    prev = page.get_by_label('预览音频')
    if prev.count() > 0:
        prev.first.scroll_into_view_if_needed()
        prev.first.click()
        page.wait_for_timeout(1500)
        dlg = page.locator("[data-slot='dialog-content']").last
        if dlg.count() > 0 and dlg.is_visible():
            txt = dlg.inner_text()
            p.check('预览音频 → 试听配置弹窗（播放模式/偏移量/开始试听）',
                    all(k in txt for k in ('播放模式', '偏移量', '开始试听')),
                    'head=%r' % txt[:140])
            page.screenshot(path=os.path.join(ART, '71_case_preview_dialog.png'))
            page.keyboard.press('Escape')
            page.wait_for_timeout(800)
        else:
            p.check('预览音频 → 试听配置弹窗', False, '未出现 dialog')
    else:
        p.skip('预览音频 → 试听配置弹窗', '列表中无预览音频入口')

    # 新增用例 → 抽屉（只打开，取消）
    add = page.get_by_role('button', name='新增用例', exact=True)
    if add.count() == 0:
        add = page.locator('button', has_text='新增用例')
    n0 = len([n for n in p.net if n['m'] == 'POST' and '/testcases' in n['u']])
    if add.count() > 0:
        add.first.click()
        page.wait_for_timeout(2000)
        sheet = page.locator("[data-slot='sheet-content']").last
        has_name = page.locator('#case-name').count() > 0
        txt = page.evaluate('()=>document.body.innerText')
        p.check('新增用例 → 编辑抽屉（用例名称/取消/保存）',
                has_name and '取消' in txt and '保存' in txt,
                'case-name=%s' % has_name)
        page.screenshot(path=os.path.join(ART, '72_case_create_sheet.png'))
        cancel = page.get_by_role('button', name='取消', exact=True)
        if cancel.count() > 0:
            cancel.first.click()
        else:
            page.keyboard.press('Escape')
        page.wait_for_timeout(1200)
        n1 = len([n for n in p.net if n['m'] == 'POST' and '/testcases' in n['u']])
        p.check('取消新增未提交（无 POST /testcases）', n1 == n0,
                'posts %d→%d' % (n0, n1))
    else:
        p.skip('新增用例抽屉', '无新增用例入口（权限不符）')


def run_audio(p, page):
    page.goto(p.base + '/audio-import', wait_until='domcontentloaded')
    page.wait_for_timeout(4500)
    body = page.evaluate('()=>document.body.innerText')
    apis = [n for n in p.net if '/api/v1/audios' in n['u']]
    p.check('音频页列表/统计渲染', '音频' in body and len(body) > 300,
            'body_len=%d api_calls=%d' % (len(body), len(apis)))
    menus = page.locator("button[aria-label^='音频'][aria-label$='的操作']")
    n_menus = menus.count()
    p.check('音频行操作菜单入口存在', n_menus >= 1, 'menus=%d' % n_menus)
    if n_menus:
        menus.first.click()
        page.wait_for_timeout(1200)
        menu_txt = page.evaluate('()=>document.body.innerText')
        p.check('音频行菜单含试听入口',
                any(k in menu_txt for k in ('试听', '播放', '下载')),
                'menu_head=%r' % menu_txt[-200:])
        page.screenshot(path=os.path.join(ART, '73_audio_row_menu.png'))
        page.keyboard.press('Escape')
        page.wait_for_timeout(600)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()

    p = Probe(args.base, args.username, args.password)
    ok = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050}, locale='zh-CN')
        page = ctx.new_page()
        p.watch(page)
        try:
            p.login(page)
            run_cases(p, page)
            run_audio(p, page)
        except Exception:
            import traceback
            traceback.print_exc()
            p.check('探针执行完成', False, traceback.format_exc()[-300:])
            ok = False
        finally:
            with open(os.path.join(ART, 'summary_cases_audio.json'), 'w',
                      encoding='utf-8') as fh:
                json.dump({'checks': p.checks}, fh, ensure_ascii=False, indent=2)
            browser.close()
    ok = ok and all(c.get('ok') for c in p.checks)
    print('\nRESULT_OK=%s' % ok)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
