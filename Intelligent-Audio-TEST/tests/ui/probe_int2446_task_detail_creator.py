# -*- coding: utf-8 -*-
"""INT-2446 实测探针：任务详情「创建人」真实化 + 标签行空态补标签名（React，docker 真库栈）。

卡面两项缺陷：
  P2  任务详情头行「创建人」恒显示硬编码「张测试」（mock 残留），未显示真实创建人；
  P3  任务信息卡标签行空态只渲染一个无标签名的「—」，读者无法判断含义。

本探针（Playwright，只读）核对：
  1. 接口真值：GET /api/v1/tasks/588 的 created_by_user_id，GET /api/v1/auth/users/{id}
     的 username/display_name（证明后端确有所用数据源）；
  2. 页面头行「创建人」= 该真实用户名，且全页不出现「张测试」；
  3. 浏览器真实发出 GET /tasks/588 与 GET /auth/users/{id}（证明姓名不是前端写死）；
  4. 信息卡标签行带「标签」标签名，空态「—」有归属；
  5. 浅色 / 深色截图。

跑法（环境铁律：连 docker 栈，不启动本地栈；dev server 用本 run 的 worktree + 53xx 端口）：
  python tests/ui/probe_int2446_task_detail_creator.py \
      --base http://localhost:5346 --api http://localhost:15000
"""
import argparse
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2446')


class Probe:
    def __init__(self, base, api, username, password, task_id):
        self.base = base.rstrip('/')
        self.api = api.rstrip('/')
        self.username = username
        self.password = password
        self.task_id = task_id
        self.checks = []
        self.net = []

    def check(self, name, ok, detail, shot=None):
        rec = {'name': name, 'ok': bool(ok), 'detail': detail}
        if shot:
            rec['shot'] = os.path.relpath(shot, PROJECT_ROOT)
        self.checks.append(rec)
        print('[%s] %-40s %s' % ('PASS' if ok else 'FAIL', name, detail))
        return rec

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
        page.screenshot(path=path, full_page=True)
        return path

    # ── 主流程 ──────────────────────────────────────────
    def run(self):
        api = ApiClient(self.api)
        api.login(self.username, self.password)
        headers = {'Authorization': 'Bearer ' + api.token}

        # 1) 接口真值
        import httpx
        r = httpx.get('%s/api/v1/tasks/%d' % (self.api, self.task_id),
                      headers=headers, timeout=30, trust_env=False)
        task = (r.json() or {}).get('data') or {}
        owner_id = task.get('created_by_user_id')
        self.check('接口：任务详情返回 created_by_user_id',
                   r.status_code == 200 and isinstance(owner_id, int),
                   'GET /api/v1/tasks/%d -> %s, created_by_user_id=%s, name=%s'
                   % (self.task_id, r.status_code, owner_id, task.get('name')))

        user = {}
        if owner_id is not None:
            ru = httpx.get('%s/api/v1/auth/users/%d' % (self.api, owner_id),
                           headers=headers, timeout=30, trust_env=False)
            user = (ru.json() or {}).get('data') or {}
            owner_name = (user.get('display_name') or user.get('username') or '').strip()
            self.check('接口：创建人用户名可解析',
                       ru.status_code == 200 and bool(owner_name),
                       'GET /api/v1/auth/users/%s -> %s, display_name=%s, username=%s'
                       % (owner_id, ru.status_code, user.get('display_name'), user.get('username')))
        else:
            owner_name = ''

        os.makedirs(ART, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for scheme in ('light', 'dark'):
                ctx = browser.new_context(
                    viewport={'width': 1680, 'height': 1050}, color_scheme=scheme)
                page = ctx.new_page()
                page.on('response', self._on_response)

                page.goto(self.base + '/login', wait_until='domcontentloaded')
                time.sleep(2)
                page.fill('#username', self.username)
                page.fill('#password', self.password)
                page.click('button[type=submit]')
                page.wait_for_url(lambda u: 'login' not in u, timeout=30000)
                self.check('登录（真实表单，%s）' % scheme, True, 'URL=%s' % page.url)

                page.goto('%s/tasks/%d' % (self.base, self.task_id),
                          wait_until='domcontentloaded')
                # 冷启动首个上下文要等 rsbuild 现编译，固定 sleep 不够稳 → 先等信息卡出现
                try:
                    page.wait_for_function(
                        "() => document.body.innerText.includes('创建人')", timeout=30000)
                except Exception:
                    pass
                time.sleep(2)
                body_text = page.inner_text('body')

                m = re.search(r'创建人\s*([^\s·|]+)', body_text)
                shown = m.group(1) if m else ''
                self.check('头行创建人 = 真实用户名（%s）' % scheme,
                           bool(owner_name) and shown == owner_name,
                           '页面「创建人 %s」 / 接口用户名「%s」' % (shown, owner_name),
                           self.shot(page, '01_task_detail_light' if scheme == 'light'
                                     else '02_task_detail', dark=scheme == 'dark'))
                self.check('全页无硬编码「张测试」（%s）' % scheme,
                           '张测试' not in body_text,
                           '页面文本含「张测试」=%s' % ('张测试' in body_text))

                # 标签行标签名 + 空态归属
                labels = page.get_by_text('标签', exact=True)
                label_count = labels.count()
                tag_row = ''
                if label_count:
                    tag_row = labels.first.evaluate(
                        "el => (el.parentElement ? el.parentElement.innerText : '').replace(/\\n/g, ' | ')")
                has_dash = '—' in tag_row
                self.check('标签行带标签名且空态「—」有归属（%s）' % scheme,
                           label_count >= 1 and has_dash,
                           '「标签」节点数=%d / 该分组文本=%s' % (label_count, tag_row[:120]))

                # 真实请求证据（浏览器侧）
                api_calls = [n for n in self.net if n['url'].endswith('/tasks/%d' % self.task_id)]
                user_calls = [n for n in self.net if '/auth/users/%s' % owner_id in n['url']]
                self.check('浏览器真实请求任务详情 + 创建人用户（%s）' % scheme,
                           bool(api_calls) and bool(user_calls),
                           'tasks=%s / users=%s'
                           % ([c['status'] for c in api_calls], [c['status'] for c in user_calls]))

                ctx.close()

            # 3) 降级路径：浏览器侧拦掉用户详情请求（等价于无 user:read / 查不到人）
            #    → 创建人回退「用户 #id」，页面其余部分照常，且绝不写死假名。
            ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
            page = ctx.new_page()
            cdp = ctx.new_cdp_session(page)
            cdp.send('Network.enable')
            cdp.send('Network.setBlockedURLs', {'urls': ['*/api/v1/auth/users/*']})
            page.goto(self.base + '/login', wait_until='domcontentloaded')
            time.sleep(2)
            page.fill('#username', self.username)
            page.fill('#password', self.password)
            page.click('button[type=submit]')
            page.wait_for_url(lambda u: 'login' not in u, timeout=30000)
            page.goto('%s/tasks/%d' % (self.base, self.task_id),
                      wait_until='domcontentloaded')
            try:
                page.wait_for_function(
                    "() => document.body.innerText.includes('创建人')", timeout=30000)
            except Exception:
                pass
            time.sleep(2)
            body_text = page.inner_text('body')
            fallback_ok = ('创建人 用户 #%s' % owner_id) in body_text and '张测试' not in body_text
            title_ok = ('测试任务' in body_text)
            self.check('用户详情不可用时回退「用户 #id」且页面不崩',
                       fallback_ok and title_ok,
                       '含「创建人 用户 #%s」=%s / 详情卡仍渲染=%s / 含「张测试」=%s'
                       % (owner_id, fallback_ok, title_ok, '张测试' in body_text),
                       self.shot(page, '03_task_detail_user_lookup_blocked'))
            ctx.close()
            browser.close()

        ok = all(c['ok'] for c in self.checks)
        os.makedirs(ART, exist_ok=True)
        evidence = {
            'task_id': self.task_id,
            'api_task': task and {
                'id': task.get('id'),
                'name': task.get('name'),
                'created_by_user_id': task.get('created_by_user_id'),
                'tags': task.get('tags'),
            },
            'api_creator_user': user and {
                'id': user.get('id'),
                'username': user.get('username'),
                'display_name': user.get('display_name'),
            },
            'browser_api_calls': self.net,
            'checks': self.checks,
        }
        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as fh:
            import json
            json.dump(evidence, fh, ensure_ascii=False, indent=2)
        print('\n==== %d/%d PASS ====' % (sum(1 for c in self.checks if c['ok']), len(self.checks)))
        return 0 if ok else 1

    def _on_response(self, resp):
        url = resp.url
        if '/api/v1/' in url:
            self.net.append({'url': url, 'status': resp.status})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    ap.add_argument('--task-id', type=int, default=588)
    args = ap.parse_args()
    return Probe(args.base, args.api, args.username, args.password, args.task_id).run()


if __name__ == '__main__':
    sys.exit(main())
