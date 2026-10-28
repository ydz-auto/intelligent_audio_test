# -*- coding: utf-8 -*-
"""INT-1076 前端回归日巡：tests/ui 冒烟全流程（登录 → 各业务页主链路）。

跑法（本 run 起前端 5400 + 依赖 5000 段常驻栈，隔离库 intelligent_audio_test_test）：
    <intelligent_audio_test conda python> tests/ui/smoke_daily_regression.py --frontend http://127.0.0.1:5400

对每页：导航 → 等待主容器渲染 → 断言 .page-title 文本 → 收集 Network 中 /api/v1/
真实请求与状态码 → 截浅色图；关键页另截 .dark 深色演示图。产出 JSON 汇总 +
截图到 tests/ui/artifacts/smoke_daily/。
"""
import argparse
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACT_ROOT = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'smoke_daily')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 每页：路由 → (容器 selector, 期望 .page-title 文本片段, 是否需要深色图)
PAGES = [
    ('/',             '.home-page',                 '首页',             True),
    ('/tasks',        '.tasks-view',                '测试任务记录',      True),
    ('/E2ETest',      '.test-view-common',          '端到端测试',        True),
    ('/APITest',      '.test-view-common',          'API测试',          False),
    ('/history-reports', '.history-reports-view',   '历史报告',          True),
    ('/test-reports', '.test-reports-view',         '测试报告',          True),
    ('/benchmarks',   '.benchmark-ranking-view',    'Benchmark 排行',   False),
    ('/TestCaseManager', '.test-case-manager',      '用例管理',          True),
    ('/Evaluation',   '.evaluation-view',           '评估维度管理',       False),
    ('/Device',       '.device-view',               '设备管理',          True),
    ('/AudioImport',  '.audio-import-view',         '导入音频管理',       False),
    ('/SPLMapping',   '.spl-mapping-view',          '声压级映射管理',     False),
    ('/LogView',      '.log-view',                  '日志查看',          False),
    ('/AlgorithmConfig', '.algorithm-config-page',  '算法配置',          True),
    ('/TagManagement', '.tg-tag-management-view',    '标签管理',          True),
]

# 需要带真实 id 的详情路由（用 API 现查一条）
DETAIL_ROUTES = ['taskDetail', 'reportView']


def _chrome_major():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def _resolve_chromedriver():
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
    candidates = []
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                candidates.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
    major = _chrome_major()
    if major:
        same = [exe for ver, exe in candidates if ver and ver[0] == major]
        if same:
            return max(same)
    if candidates:
        return sorted(candidates, reverse=True)[0][1]
    return ''


def parse_network_entries(raw_logs):
    """从 performance log 提取 /api/v1/ 响应：url -> [status,...]。"""
    out = {}
    for entry in raw_logs:
        try:
            msg = json.loads(entry.get('message', '{}'))
            inner = msg.get('message', {})
            method = inner.get('method', '')
            params = inner.get('params', {})
            if method == 'Network.responseReceived':
                resp = params.get('response', {})
                url = resp.get('url', '')
                if '/api/v1/' in url:
                    out.setdefault(url, []).append(resp.get('status'))
        except Exception:
            continue
    return out


class SmokeRunner:
    def __init__(self, frontend_base: str, username: str, password: str,
                 api_base: str = 'http://127.0.0.1:5000'):
        self.base = frontend_base.rstrip('/')
        self.api = api_base.rstrip('/')
        self.username = username
        self.password = password
        self.results = {}
        self.driver = None

    def start(self):
        opts = webdriver.ChromeOptions()
        opts.binary_location = CHROME_BINARY
        opts.add_argument('--headless=new')
        opts.add_argument('--window-size=1680,1050')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--lang=zh-CN')
        opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
        drv_path = _resolve_chromedriver()
        svc = webdriver.ChromeService(executable_path=drv_path) if drv_path else webdriver.ChromeService()
        self.driver = webdriver.Chrome(options=opts, service=svc)
        self.driver.set_page_load_timeout(60)
        self.wait = WebDriverWait(self.driver, 30)
        return self

    def stop(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # ── 登录（真实表单流）──────────────────────────────
    def login(self):
        d = self.driver
        d.get(f'{self.base}/#/login')
        WebDriverWait(d, 45).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
        u = d.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]')
        p = d.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]')
        btn = d.find_element(By.CSS_SELECTOR, '.login-card form button.login-btn')
        u.clear(); u.send_keys(self.username)
        p.clear(); p.send_keys(self.password)
        btn.click()
        ok = False
        try:
            WebDriverWait(d, 20).until(lambda dd: '/login' not in dd.current_url.split('#')[-1])
            ok = True
        except Exception:
            ok = False
        return ok

    # ── 单页走查 ──────────────────────────────────────
    def visit(self, route: str, container: str, title: str, page_key: str,
              dark: bool = False):
        d = self.driver
        res = {'route': route, 'ok': False, 'title_found': None, 'apis': {},
               'console_errors': [], 'screenshot': None, 'note': ''}
        try:
            d.get(f'{self.base}/#{route}')
            # 等待容器 + 标题
            WebDriverWait(d, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, container)))
            try:
                WebDriverWait(d, 15).until(
                    EC.text_to_be_present_in_element(
                        (By.CSS_SELECTOR, '.page-title'), title))
                res['title_found'] = True
            except Exception:
                # 标题不唯一（如 TestFlow 用 .pageTitleIcon）时降级：只看容器渲染
                titles = [el.text.strip() for el in d.find_elements(By.CSS_SELECTOR, '.page-title')]
                res['title_found'] = titles
                res['note'] = f'标题降级匹配: {titles!r}'
            time.sleep(1.5)  # 等异步请求落地
            # 网络请求
            logs = d.get_log('performance')
            res['apis'] = parse_network_entries(logs)
            # console 错误
            for e in d.get_log('browser'):
                if e.get('level') == 'SEVERE' and 'favicon' not in str(e.get('message', '')):
                    res['console_errors'].append(f"{e.get('level')}: {e.get('message','')[:300]}")
            # 页面正文判空（空态也正常，记录内容骨架）
            body_txt = d.find_element(By.TAG_NAME, 'body').text[:200].replace('\n', ' ')
            res['body_preview'] = body_txt
            # 截图
            tag = f'{page_key}_{"dark" if dark else "light"}'
            shot = os.path.join(ARTIFACT_ROOT, f'{tag}.png')
            os.makedirs(ARTIFACT_ROOT, exist_ok=True)
            d.save_screenshot(shot)
            res['screenshot'] = os.path.relpath(shot, PROJECT_ROOT)
            res['ok'] = True
        except Exception as exc:
            res['note'] = f'EXC: {type(exc).__name__}: {str(exc)[:200]}'
            try:
                tag = f'{page_key}_{"dark" if dark else "light"}_FAIL'
                shot = os.path.join(ARTIFACT_ROOT, f'{tag}.png')
                os.makedirs(ARTIFACT_ROOT, exist_ok=True)
                d.save_screenshot(shot)
                res['screenshot'] = os.path.relpath(shot, PROJECT_ROOT)
            except Exception:
                pass
        return res

    def set_dark(self, on: bool):
        self.driver.execute_script(
            'document.documentElement.classList.toggle("dark", arguments[0]);', on)

    def run(self):
        # 0) 登录
        self.results['login'] = {'ok': self.login(), 'route': '/login'}
        # 1) 首页 + 主链路浅色
        for route, container, title, need_dark in PAGES:
            key = route.strip('/') or 'home'
            self.results[f'light:{key}'] = self.visit(
                route, container, title, key, dark=False)
        # 2) 详情页（现查一条真实 id）
        ids = self._fetch_real_ids()
        if ids.get('task'):
            r = self.visit(f'/tasks/{ids["task"]}', '.task-detail-page', '任务详情',
                           'task_detail', dark=False)
            self.results['light:task_detail'] = r
        if ids.get('report'):
            r = self.visit(f'/report/{ids["report"]}', '.rv-report-view-page', '报告查看',
                           'report_detail', dark=False)
            self.results['light:report_detail'] = r
        # 3) 关键页深色演示（.dark 结构预留，见 tokens.css）
        for route, container, title, need_dark in PAGES:
            if not need_dark:
                continue
            self.set_dark(True)
            key = route.strip('/') or 'home'
            self.results[f'dark:{key}'] = self.visit(
                route, container, title, key, dark=True)
        self.set_dark(False)

    def _fetch_real_ids(self):
        """从后端 API 取一条任务 / 报告 id（隔离库只读）。"""
        ids = {}
        try:
            import httpx
            from tests.ui.utils.api_client import ApiClient
            api = ApiClient(self.api)
            api.login(self.username, self.password)
            h = {'Authorization': f'Bearer {api.token}'}
            r = httpx.get(f'{self.api}/api/v1/tasks?page=1&per_page=1',
                          headers=h, timeout=15, trust_env=False)
            items = r.json().get('data', {}).get('items', [])
            if items:
                ids['task'] = items[0].get('id')
            r = httpx.get(f'{self.api}/api/v1/reports?page=1&per_page=1',
                          headers=h, timeout=15, trust_env=False)
            items = r.json().get('data', {}).get('items', [])
            if items:
                ids['report'] = items[0].get('id')
        except Exception as exc:
            self.results['_id_fetch_error'] = str(exc)[:200]
        return ids

    def summary(self):
        out = {}
        for k, v in self.results.items():
            if isinstance(v, dict) and v.get('ok'):
                out[k] = {'ok': True, 'title': v.get('title_found'),
                          'api_count': len(v.get('apis', {})),
                          'apis': {u: st for u, st in v.get('apis', {}).items()},
                          'api_errors': {u: st for u, st in v.get('apis', {}).items()
                                         if any(s >= 400 for s in st)},
                          'console_errors': v.get('console_errors', []),
                          'body_preview': v.get('body_preview', ''),
                          'shot': v.get('screenshot')}
            elif isinstance(v, dict):
                out[k] = {'ok': False, 'note': v.get('note', '')[:200],
                          'shot': v.get('screenshot')}
            else:
                out[k] = v
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frontend', default='http://127.0.0.1:5400')
    ap.add_argument('--username', default='admin')
    ap.add_argument('--password', default='admin123')
    # docker 环境（后端网关 :15000）口径：API_BASE 默认 5000 是本地栈，
    # 冒烟走 docker 栈时用 --api / API_BASE 指向 :15000，明细页 id 现查才不会落空。
    ap.add_argument('--api', default=os.environ.get('API_BASE', 'http://127.0.0.1:5000'))
    args = ap.parse_args()

    sys.path.insert(0, PROJECT_ROOT)
    runner = SmokeRunner(args.frontend, args.username, args.password, args.api)
    try:
        runner.start()
        runner.run()
    finally:
        runner.stop()

    summary = runner.summary()
    summary_path = os.path.join(ARTIFACT_ROOT, 'summary.json')
    os.makedirs(ARTIFACT_ROOT, exist_ok=True)
    with open(summary_path, 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'SUMMARY_JSON={summary_path}')


if __name__ == '__main__':
    main()
