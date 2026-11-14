# -*- coding: utf-8 -*-
"""INT-2607 缺陷验证：Skill 列表 TENANT 行不应展示「删除」。

缺陷：TENANT 共享 Skill 行渲染「删除」，确认后服务端恒 409
（``agent_service/application/skill_service.py``: TENANT 共享 Skill 不支持删除）。
修复：删除按钮只在 ``skill.scope === USER``（``isWritableSkill``）时渲染。

跑法（docker 真栈后端 + 本 run dev server，环境铁律；前端为本次分支代码）：
  python tests/ui/probe_int2607_tenant_delete.py \
      --base http://localhost:5312 --api http://localhost:15000

账号默认 dev_user / dev_password（UI_TEST_USERNAME / UI_TEST_PASSWORD 覆盖）。

覆盖：
  1 登录后 GET /api/v1/agent/skills 的真实应答（记录各行 scope，确认栈内数据）
  2 列表每行渲染的动作集合按来源分层断言：
      PLATFORM → fork / 导出；TENANT → 只有导出（无删除 / 编辑 / 停用）；
      USER     → 编辑 / 停用 / 导出 / 删除
  3 USER 行回归：真实建一条 USER 草稿 → 行上有「删除」→ 点删除确认 → 行消失、
    DELETE 200（顺带清理，不留数据）
  4 TENANT 真实行：栈内若有真实 TENANT Skill 则直接断言；没有则标记 SKIP，
    并额外用 CDP 在响应层注入一条 TENANT 行截图为「桩验证」，不写成真数据通过
  5 浅 / 深色截图

产出：tests/ui/artifacts/int2607/{summary.json, net.log, *.png}
"""
import argparse
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request

try:  # Windows 控制台默认 GBK，中文文案 print 会炸
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2607')
os.makedirs(ART, exist_ok=True)
NET_LOG = os.path.join(ART, 'net.log')

USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')
TOKEN_KEY = 'iatp:auth:token:v1'

RESULT = {
    'kind': 'react',
    'checks': {},
    'rows': [],
    'screenshots': [],
    'notes': [],
    'skipped': [],
}
NET = []


def log(msg):
    print('[int2607] %s' % msg, flush=True)


def record(check, ok, detail='', **payload):
    RESULT['checks'][check] = {'ok': bool(ok), 'detail': detail, **payload}
    log('%s: %s %s' % (check, 'PASS' if ok else 'FAIL', detail))


def api(method, path, token, body=None):
    url = API + path
    data = None
    headers = {'Accept': 'application/json', 'Authorization': 'Bearer %s' % token}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw.decode('utf-8')) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception:  # noqa: BLE001
            payload = raw.decode('utf-8', 'replace')
        return exc.code, payload


def row_actions(page):
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('[data-testid="agent-skill-row"]'))
            .map((row) => ({
              name: row.getAttribute('data-skill-name'),
              scope: row.getAttribute('data-skill-scope'),
              status: row.getAttribute('data-skill-status'),
              actions: Array.from(row.querySelectorAll('button'))
                .map((b) => (b.getAttribute('aria-label') || b.textContent || '').trim()),
            }))"""
    )


def stub_tenant_row(context, page, base):
    """CDP 在响应层注入一条 TENANT 行（**桩验证**，不是真实数据）。

    栈内没有 TENANT Skill（创建 TENANT 需租户管理员且无删除接口，会在共享栈
    留下不可移除的数据），故 TENANT 行的「无删除」由单测 + 本次桩截图佐证。
    """
    import base64

    client = context.new_cdp_session(page)
    state = {'fulfilled': False, 'error': None}

    def on_paused(params):
        try:
            if params.get('responseStatusCode') is None:
                client.send('Fetch.continueRequest',
                            {'requestId': params['requestId']})
                return
            got = client.send('Fetch.getResponseBody',
                              {'requestId': params['requestId']})
            raw = got.get('body') or ''
            text = (base64.b64decode(raw).decode('utf-8')
                    if got.get('base64Encoded') else raw)
            payload = json.loads(text)
            items = payload.get('items') or []
            if not any(i.get('scope') == 'TENANT' for i in items):
                items.append({
                    'id': 'stub-tenant-int2607',
                    'scope': 'TENANT',
                    'name': 'tenant-shared-demo',
                    'description': '桩注入：TENANT 共享 Skill 行（非真实数据）',
                    'version': '1',
                    'status': 'ACTIVE',
                    'content_hash': 'deadbeefdeadbeef',
                    'masked_by': None,
                    'owner': 'tenant-demo',
                    'owner_id': None,
                    'tenant_id': 'demo',
                    'allowed_tools': [],
                    'permissions': [],
                    'budgets': {},
                    'updated_at': '2026-11-14T00:00:00Z',
                    'issues': [],
                })
                payload['items'] = items
            body = base64.b64encode(
                json.dumps(payload, ensure_ascii=False).encode('utf-8')
            ).decode('ascii')
            headers = [h for h in params.get('responseHeaders', [])
                       if (h.get('name') or '').lower() != 'content-length']
            client.send('Fetch.fulfillRequest', {
                'requestId': params['requestId'],
                'responseCode': params.get('responseStatusCode', 200),
                'responseHeaders': headers,
                'body': body,
            })
            state['fulfilled'] = True
        except Exception as exc:  # noqa: BLE001
            state['error'] = str(exc)
            try:
                client.send('Fetch.continueRequest',
                            {'requestId': params['requestId']})
            except Exception:  # noqa: BLE001
                pass

    client.on('Fetch.requestPaused', on_paused)
    client.send('Fetch.enable', {'patterns': [{
        'urlPattern': '*api/v1/agent/skills*',
        'requestStage': 'Response',
    }]})
    page.goto(base + '/agent-skills', wait_until='domcontentloaded')
    page.wait_for_selector('[data-testid="agent-skill-row"]', timeout=45000)
    page.wait_for_timeout(1500)
    rows = [r for r in row_actions(page) if r['scope'] == 'TENANT']
    page.eval_on_selector(
        '[data-skill-name="tenant-shared-demo"]',
        'el => el.scrollIntoView({ block: "center" })')
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(ART, 'tenant_stub_row_dark.png'))
    RESULT['screenshots'].append('tenant_stub_row_dark.png')
    page.evaluate(
        "() => { localStorage.setItem('iatp:theme:v1:mode', 'light'); }")
    page.reload(wait_until='domcontentloaded')
    page.wait_for_selector('[data-testid="agent-skill-row"]', timeout=45000)
    page.wait_for_timeout(1500)
    rows_light = [r for r in row_actions(page) if r['scope'] == 'TENANT']
    page.eval_on_selector(
        '[data-skill-name="tenant-shared-demo"]',
        'el => el.scrollIntoView({ block: "center" })')
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(ART, 'tenant_stub_row_light.png'))
    RESULT['screenshots'].append('tenant_stub_row_light.png')
    client.send('Fetch.disable')
    ok = (bool(rows) and bool(rows_light)
          and not any('删除' in a for r in rows + rows_light for a in r['actions']))
    record('tenant_rows_stub', ok,
           '桩注入 TENANT 行动作 %s'
           % (rows[0]['actions'] if rows else '未渲染'),
           stub=True, fulfilled=state['fulfilled'], error=state['error'])


def login(page, base):
    page.goto(base + '/login', wait_until='domcontentloaded')
    page.wait_for_selector('input[type=password]', timeout=30000)
    page.fill('#username', USERNAME)
    page.fill('input[type=password]', PASSWORD)
    page.click('button[type=submit]')
    page.wait_for_function('!location.pathname.toLowerCase().includes("login")', timeout=45000)
    page.wait_for_timeout(2500)
    token = page.evaluate(
        "() => window.localStorage.getItem('%s')" % TOKEN_KEY)
    if not token:
        raise AssertionError('登录后未取到 token（%s）' % TOKEN_KEY)
    return token


def goto_skills(page, base):
    page.goto(base + '/agent-skills', wait_until='domcontentloaded')
    page.wait_for_selector('[data-testid="agent-skill-row"]', timeout=45000)
    page.wait_for_timeout(1200)


def main():
    global API
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:5312')
    parser.add_argument('--api', default='http://localhost:15000')
    parser.add_argument('--keep-user-skill', action='store_true')
    args = parser.parse_args()
    base = args.base.rstrip('/')
    API = args.api.rstrip('/')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = context.new_page()

        def on_response(resp):
            if '/api/v1/agent/skills' in resp.url:
                NET.append({'method': resp.request.method, 'url': resp.url,
                            'status': resp.status})

        page.on('response', on_response)

        try:
            token = login(page, base)
            record('login', True, 'dev_user 登录成功，token 已落 localStorage')

            # 1) 真实列表数据
            status, listing = api('GET', '/api/v1/agent/skills', token)
            items = (listing or {}).get('items') or []
            scopes = {}
            for item in items:
                scopes[item.get('scope')] = scopes.get(item.get('scope'), 0) + 1
            record('list_api', status == 200, 'GET /agent/skills %s 条 %s'
                   % (len(items), scopes), status=status,
                   scopes=scopes, count=len(items))

            # 2) 列表渲染
            goto_skills(page, base)
            rows = row_actions(page)
            RESULT['rows'] = rows
            by_scope = {}
            for row in rows:
                by_scope.setdefault(row['scope'], []).append(row)

            platform_ok = all(
                any('fork' in a for a in r['actions'])
                and any('导出' in a for a in r['actions'])
                and not any('删除' in a for a in r['actions'])
                and not any('编辑' in a for a in r['actions'])
                for r in by_scope.get('PLATFORM', [])
            )
            record('platform_rows', platform_ok,
                   'PLATFORM %d 行：fork / 导出，无删除'
                   % len(by_scope.get('PLATFORM', [])))

            tenant_rows = by_scope.get('TENANT', [])
            if tenant_rows:
                tenant_ok = all(
                    not any('删除' in a for a in r['actions'])
                    and not any('编辑' in a for a in r['actions'])
                    and not any('停用' in a for a in r['actions'])
                    and any('导出' in a for a in r['actions'])
                    for r in tenant_rows
                )
                record('tenant_rows_real', tenant_ok,
                       'TENANT %d 行：无删除 / 编辑 / 停用，仅导出' % len(tenant_rows),
                       sample=[r['actions'] for r in tenant_rows[:3]])
            else:
                RESULT['skipped'].append(
                    'tenant_rows_real：栈内当前没有 TENANT Skill（真实应答全为 '
                    + '/'.join(sorted(scopes)) + '），TENANT 行断言见单测')
                log('SKIP tenant_rows_real：栈内无 TENANT Skill（%s）' % scopes)

            # 3) USER 行回归：真实建一条 → 验动作 → 点删除清理
            suffix = str(int(time.time()))
            skill_name = 'probe-int2607-%s' % suffix[-8:]
            body = ('## 适用场景\n\nINT-2607 探针临时草稿。\n\n## 步骤\n\n1.\n\n'
                    '## Gotchas\n\n-\n\n## 验收\n\n-\n')
            status, created = api('POST', '/api/v1/agent/skills', token, {
                'name': skill_name,
                'description': 'INT-2607 临时验证用，验证后删除',
                'body': body,
            })
            if status not in (200, 201):
                record('user_row_real', False,
                       '建临时 USER 草稿失败 %s %s' % (status, str(created)[:200]))
            else:
                skill_id = created.get('id') or created.get('skill', {}).get('id')
                goto_skills(page, base)
                user_rows = [r for r in row_actions(page) if r['name'] == skill_name]
                if not user_rows:
                    record('user_row_real', False, '刷新后未找到新建的 USER 行')
                else:
                    actions = user_rows[0]['actions']
                    need = ['编辑', '停用', '导出', '删除']
                    missing = [k for k in need if not any(k in a for a in actions)]
                    record('user_row_real', not missing,
                           'USER 行动作 %s' % actions, missing=missing)
                    page.screenshot(path=os.path.join(ART, 'light_user_row.png'))

                    # 点删除 → ConfirmDialog 确认（同时清理临时草稿）
                    btn = page.query_selector(
                        '[data-testid="agent-skill-row"][data-skill-name="%s"] '
                        'button[aria-label^="删除"]' % skill_name)
                    if not btn:
                        record('user_delete_flow', False, 'USER 行删除按钮缺失')
                    else:
                        btn.click()
                        page.wait_for_timeout(600)
                        dialogs = page.query_selector_all(
                            '[role=alertdialog], [role=dialog]')
                        clicked = False
                        for dialog in dialogs:
                            for b in dialog.query_selector_all('button'):
                                text = (b.inner_text() or '').strip()
                                if text == '删除':
                                    b.click()
                                    clicked = True
                                    break
                            if clicked:
                                break
                        page.wait_for_timeout(1500)
                        deletes = [n for n in NET if n['method'] == 'DELETE']
                        record('user_delete_flow', clicked and bool(deletes)
                               and all(n['status'] < 300 for n in deletes),
                               'USER 删除链路：%s' % (deletes or '无 DELETE 请求'),
                               deletes=deletes)
                        if args.keep_user_skill:
                            RESULT['notes'].append('--keep-user-skill：临时 USER 草稿未删除')
                        elif not deletes and skill_id:
                            api('DELETE', '/api/v1/agent/skills/%s' % skill_id, token)
                            RESULT['notes'].append('UI 删除未发出请求，已用 API 兜底清理')

            # 4) 浅 / 深色整页截图
            goto_skills(page, base)
            page.screenshot(path=os.path.join(ART, 'light_list.png'))
            RESULT['screenshots'].append('light_list.png')
            page.evaluate(
                "() => { localStorage.setItem('iatp:theme:v1:mode', 'dark'); }")
            page.reload(wait_until='domcontentloaded')
            page.wait_for_selector('[data-testid="agent-skill-row"]', timeout=45000)
            page.wait_for_timeout(1200)
            page.screenshot(path=os.path.join(ART, 'dark_list.png'))
            RESULT['screenshots'].append('dark_list.png')

            # 5) TENANT 行视觉佐证（CDP 响应层注入，桩；写在评论里不冒充真数据）
            if not tenant_rows:
                try:
                    stub_tenant_row(context, page, base)
                except Exception as exc:  # noqa: BLE001
                    RESULT['skipped'].append(
                        'tenant_rows_stub：CDP 注入失败 %s: %s'
                        % (type(exc).__name__, exc))
                    log('SKIP tenant_rows_stub：%s' % exc)
            RESULT['notes'].append(
                '栈内真实应答仅 %s；TENANT 行“无删除”由 '
                'agent-skill-list.test.tsx 单测覆盖' % scopes)
        except Exception as exc:  # noqa: BLE001
            RESULT['error'] = '%s: %s' % (type(exc).__name__, exc)
            RESULT['traceback'] = traceback.format_exc()
            log('ERROR %s' % RESULT['error'])
        finally:
            with open(NET_LOG, 'w', encoding='utf-8') as fh:
                for entry in NET:
                    fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
            path = os.path.join(ART, 'summary.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(RESULT, fh, ensure_ascii=False, indent=2)
            log('summary → %s' % path)
            browser.close()

    failed = [k for k, v in RESULT['checks'].items() if not v['ok']]
    if RESULT.get('error') or failed:
        log('FAILED: %s' % (failed or RESULT.get('error')))
        return 1
    log('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
