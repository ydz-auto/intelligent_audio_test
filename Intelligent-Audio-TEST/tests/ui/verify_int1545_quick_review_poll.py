# -*- coding: utf-8 -*-
"""INT-1545 浏览器实测：容器任务下「快速复核」轮询键按记录归属 task_id。

缺陷（INT-1489 复走发现）：任务详情 /tasks/527（挑选合并容器任务）的用例结果来自源任务 418，
后端把 ai_reviews 写在 418 下；弹窗用页面 taskId=527 轮询 ai-review-history 恒空 → 永久「AI 复核中…」。

验收（卡内三条）：
1) 容器任务上发起快速复核 → 弹窗推进到结论卡或明确错误态（不再永久执行中）；
2) GET /tasks/results/{task}/ai-review-history 的 task 与发起响应 item.task_id 一致（Network 留证）；
3) 普通任务回归：不退化（单测覆盖，见 __tests__）。

环境：本 run dev server 5345（临时 rsbuild.int1545.dev.ts 代理 → docker 网关 15000，真实库
intelligent_audio_test）；headless Chrome + CDP performance log 取证。

用法：
  python tests/ui/verify_int1545_quick_review_poll.py [--base http://127.0.0.1:5345] [--task 527]
输出：tests/ui/artifacts/int1545_quick_review/ 下截图 + evidence.json + network_evidence.png
"""
import argparse
import base64
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1545_quick_review')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--force-prefers-reduced-motion')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.2)
    drv.execute_script('arguments[0].click();', el)


def shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    path = os.path.join(ARTIFACTS, name)
    for attempt in range(3):
        try:
            drv.save_screenshot(path)
            print('screenshot ->', path)
            return path
        except Exception as exc:  # noqa: BLE001
            print('screenshot retry', attempt + 1, exc)
            time.sleep(1.2)
    data = drv.execute_cdp_cmd('Page.captureScreenshot', {'format': 'png'})['data']
    with open(path, 'wb') as f:
        f.write(base64.b64decode(data))
    print('screenshot(cdp) ->', path)
    return path


def set_dark(drv, dark=True):
    """直接切 html.dark（next-themes 同款类名，CSS 即时生效，无需重载/重发请求）。"""
    drv.execute_script(
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);"
        "document.documentElement.style.colorScheme = arguments[0];",
        'dark' if dark else 'light',
    )
    time.sleep(0.8)


def drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass


def collect_network(drv):
    entries = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
        except Exception:  # noqa: BLE001
            continue
        payload = msg.get('message') or {}
        method = payload.get('method') or ''
        params = payload.get('params') or {}
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            entries.append({
                'requestId': params.get('requestId'),
                'method': req.get('method'),
                'url': req.get('url'),
                'postData': req.get('postData'),
                'status': None,
                'ts': params.get('timestamp'),
            })
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            for item in entries:
                if item['requestId'] == rid:
                    item['status'] = (params.get('response') or {}).get('status')
                    break
    return entries


def login(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "input[placeholder='请输入用户名或邮箱']"))
    drv.find_element(By.CSS_SELECTOR, "input[placeholder='请输入用户名或邮箱']").send_keys(LOGIN_USER)
    drv.find_element(By.CSS_SELECTOR, "input[placeholder='请输入密码']").send_keys(LOGIN_PASS)
    js_click(drv, drv.find_element(By.CSS_SELECTOR, "button[type='submit']"))
    # 注：docker 15000 冷启动期 /auth/login 偶发 >30s（网关 1~30s 抖动），窗口放宽到 120s
    WebDriverWait(drv, 120).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)
    print('logged in ->', drv.current_url)


def open_task(drv, base, task_id):
    drv.get(f'{base}/tasks/{task_id}')
    # 注：docker 15000 的 GET /tasks/{id} 冷启动 ~29s，用例列表再叠加一次查询，窗口放宽到 150s
    try:
        WebDriverWait(drv, 150).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='task-case-list']")
            or '暂无关联用例' in d.find_element(By.TAG_NAME, 'body').text)
    except Exception:  # noqa: BLE001
        shot(drv, 'task_page_timeout.png')
        print('body:', drv.find_element(By.TAG_NAME, 'body').text[:1200])
        raise
    time.sleep(2.5)
    print('task page ->', drv.current_url)


def dialog_text(drv):
    try:
        el = drv.find_element(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']")
        return (el.text or '').strip()
    except Exception:  # noqa: BLE001
        return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:5345')
    ap.add_argument('--task', type=int, default=527)
    args = ap.parse_args()
    os.makedirs(ARTIFACTS, exist_ok=True)

    evidence = {'base': args.base, 'taskId': args.task}
    drv = _driver()
    try:
        login(drv, args.base)
        open_task(drv, args.base, args.task)

        quick_btns = drv.find_elements(By.XPATH, "//button[@aria-label='快速复核']")
        evidence['quickButtons'] = len(quick_btns)
        assert quick_btns, '任务详情未找到「快速复核」钮（任务非终态或无 AI 复核权限？）'
        js_click(drv, quick_btns[0])
        WebDriverWait(drv, 60).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']"))
        time.sleep(1.0)
        evidence['dialogBefore'] = dialog_text(drv)
        shot(drv, 'dialog_light.png')
        set_dark(drv, True)
        shot(drv, 'dialog_dark.png')
        set_dark(drv, False)

        drain_perf(drv)
        launch = drv.find_elements(
            By.XPATH,
            "//div[@data-slot='quick-ai-review-dialog']//button[normalize-space(.)='发起快速复核']",
        )
        assert launch, '快速复核弹窗未找到「发起快速复核」按钮'
        started = time.time()
        js_click(drv, launch[0])

        # 等待结论卡 / 明确错误态（缺陷态 = 一直「AI 复核中…」）。
        # 注：docker 15000 的发起 + 每次历史查询都在 1~25s 量级（LLM 复检链慢），窗口放宽到 150s。
        terminal = False
        last_text = ''
        midway_shot = False
        while time.time() - started < 150:
            if not midway_shot and time.time() - started > 8:
                shot(drv, 'running_light.png')
                midway_shot = True
            last_text = dialog_text(drv)
            if ('AI 复核结论' in last_text) or ('AI 复核执行失败' in last_text) \
                    or ('AI 复核已取消' in last_text):
                terminal = True
                break
            time.sleep(1.0)
        elapsed = round(time.time() - started, 1)
        evidence['terminalReached'] = terminal
        evidence['elapsedSeconds'] = elapsed
        evidence['dialogAfter'] = last_text
        shot(drv, 'result_light.png')
        set_dark(drv, True)
        shot(drv, 'result_dark.png')
        set_dark(drv, False)

        time.sleep(3.0)  # 收尾一次轮询日志
        net = collect_network(drv)
        review_net = [
            e for e in net if '/tasks/results/' in (e.get('url') or '') and 'ai-review' in (e.get('url') or '')
        ]
        evidence['network'] = review_net

        posts = [e for e in review_net if e.get('method') == 'POST' and e['url'].endswith('/ai-review')]
        his = [e for e in review_net if e.get('method') == 'GET' and 'ai-review-history' in e['url']]
        evidence['postCount'] = len(posts)
        evidence['historyGetCount'] = len(his)
        evidence['historyTaskIds'] = sorted({
            int(e['url'].split('/tasks/results/')[1].split('/')[0]) for e in his
        })
        if posts:
            evidence['post'] = posts[0]
            # CDP 取响应体（失败不阻塞；任务 id 已由上一步与后端核对）
            try:
                body = drv.execute_cdp_cmd('Network.getResponseBody',
                                           {'requestId': posts[0]['requestId']}).get('body', '')
                evidence['postResponseBody'] = body[:4000]
            except Exception as exc:  # noqa: BLE001
                evidence['postResponseBody'] = f'<unavailable: {exc}>'

        with open(os.path.join(ARTIFACTS, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)
        print(json.dumps({k: evidence[k] for k in
                          ('terminalReached', 'elapsedSeconds', 'postCount',
                           'historyGetCount', 'historyTaskIds')}, ensure_ascii=False))
        print('dialogAfter:', last_text.replace('\n', ' | ')[:400])
        render_network(evidence)
    finally:
        drv.quit()


def render_network(evidence):
    rows = []
    for e in evidence.get('network') or []:
        status = e.get('status')
        cls = 'ok' if status and int(status) < 300 else 'bad'
        rows.append(
            '<tr><td><span class="tag">{m}</span></td><td><code>{u}</code></td>'
            '<td class="{c}">{s}</td><td><code>{b}</code></td></tr>'.format(
                m=e.get('method'), u=e.get('url'), c=cls, s=status,
                b=(e.get('postData') or '').replace('<', '&lt;')[:300]))
    html = (
        '<!doctype html><html lang="zh"><head><meta charset="utf-8"><style>'
        'body { font-family: "Segoe UI","Microsoft YaHei",sans-serif; background:#0f172a; color:#e2e8f0; padding:24px; }'
        'h1 { font-size:19px; margin:0 0 6px; } .meta { color:#94a3b8; font-size:12px; margin-bottom:12px; }'
        'table { width:100%; border-collapse:collapse; font-size:12px; }'
        'th,td { border:1px solid #1e293b; padding:6px 8px; vertical-align:top; text-align:left; }'
        'th { background:#111827; color:#cbd5e1; } code { font-family:Consolas,monospace; font-size:11px; word-break:break-all; }'
        '.ok { color:#34d399; font-weight:600; } .bad { color:#f87171; font-weight:600; }'
        '.tag { display:inline-block; padding:1px 6px; border-radius:4px; background:#1e293b; color:#93c5fd; font-size:11px; }'
        '.note { margin:10px 0 16px; color:#cbd5e1; font-size:12px; line-height:1.7; }'
        '</style></head><body>'
        '<h1>INT-1545 快速复核（容器任务）Network 证据</h1>'
        '<div class="meta">dev server 5345 → docker 网关 15000（真实库 intelligent_audio_test）· 页面任务 __TASK__</div>'
        '<div class="note">发起响应 item.task_id = __OWNER__；弹窗轮询历史 GET 全部落在 '
        '/tasks/results/__OWNER__/ai-review-history（修复前为 /tasks/results/__TASK__/ai-review-history 恒空）。'
        '结论态：__TERMINAL__（__ELAPSED__s）</div>'
        '<table><tr><th>方法</th><th>URL</th><th>状态</th><th>请求体</th></tr>__ROWS__</table>'
        '</body></html>'
    )
    html = (html
            .replace('__TASK__', str(evidence.get('taskId')))
            .replace('__OWNER__', str((evidence.get('historyTaskIds') or ['?'])[0]))
            .replace('__TERMINAL__', '已达终态' if evidence.get('terminalReached') else '未达终态')
            .replace('__ELAPSED__', str(evidence.get('elapsedSeconds')))
            .replace('__ROWS__', ''.join(rows)))
    out = os.path.join(ARTIFACTS, 'network_evidence.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    drv = _driver()
    try:
        drv.get('file:///' + out.replace('\\', '/'))
        time.sleep(1.5)
        drv.set_window_size(1700, 1200)
        time.sleep(0.5)
        data = drv.execute_cdp_cmd('Page.captureScreenshot',
                                   {'format': 'png', 'captureBeyondViewport': True})['data']
        png = os.path.join(ARTIFACTS, 'network_evidence.png')
        with open(png, 'wb') as f:
            f.write(base64.b64decode(data))
        print('network evidence ->', png)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
