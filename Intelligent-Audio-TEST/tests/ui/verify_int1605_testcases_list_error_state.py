# -*- coding: utf-8 -*-
"""INT-1605 验收脚本：用例列表接口失败不得伪装成「没有找到符合条件的测试用例」空态。

与 INT-1560（标签页）/ INT-1583（音频页）同型的错误态用例，覆盖：
1. /testcases/by-group 首屏失败：显示「用例列表加载失败 + 重试」，且不出现
   「没有找到符合条件的测试用例 / 尝试清空「分组」「标签」筛选」误导空态；
2. /testcases/by-tag 首屏失败：同样显示错误态，不出现「没有找到标签分组的测试用例」；
3. 失败 → 点「重试」（接口恢复）→ 列表恢复真实数据；
4. 已加载数据后筛选失败：保留旧列表 + 行内提示条 role=alert + toast，不清空；
5. 浅色 / 深色截图 + `GET /api/v1/testcases` 的 HTTP 状态（性能日志，非页内打点）。

失败注入在网关层（真实 HTTP 500）：脚本自建一次性 nginx 旁路容器
（dist← frontend-react/dist，/api → api_gateway:5000），通过切换 conf 里的
`location = /api/v1/testcases` 打开/关闭 500，再用 `nginx -s reload` 生效。
前置：`cd frontend-react && pnpm build`；本机 docker 可跑（network intelligent-audio-test_default）。

用法：
    python tests/ui/verify_int1605_testcases_list_error_state.py
环境变量：CHROMEDRIVER（默认本机缓存驱动）、INT1605_PORT（默认 15310）。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIST = os.path.join(REPO, 'frontend-react', 'dist')
PORT = os.environ.get('INT1605_PORT', '15310')
BASE = 'http://localhost:%s' % PORT
CONTAINER = 'iat-int1605-verify'
DRIVER = os.environ.get(
    'CHROMEDRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
ART = os.path.join(REPO, 'tests', 'ui', 'artifacts', 'int1605')
os.makedirs(ART, exist_ok=True)

NGINX_CONF = """server {{
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {{
        try_files $uri $uri/ /index.html;
    }}
{error_location}
    location /api/ {{
        proxy_pass http://api_gateway:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}

    location /health {{
        proxy_pass http://api_gateway:5000;
        proxy_set_header Host $host;
    }}

    location /socket.io/ {{
        proxy_pass http://api_gateway:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }}

    location /ws {{
        proxy_pass http://api_gateway:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }}
}}
"""

ERROR_LOCATION = """
    # INT-1605 取证：只让用例列表接口 500，其余接口照常 200
    location = /api/v1/testcases {
        default_type application/json;
        return 500 '{"success":false,"code":205,"message":"[INT-1605] 用例列表接口失败"}';
    }
"""


def log(m):
    print(m, flush=True)


class Stack:
    """一次性 nginx 旁路容器 + conf 开关（真实 HTTP 500）"""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='int1605_')
        self.conf = os.path.join(self.dir, 'default.conf')
        self.error = False

    def start(self):
        if not os.path.isdir(DIST):
            raise SystemExit('缺少 %s，请先 cd frontend-react && pnpm build' % DIST)
        subprocess.run(['docker', 'rm', '-f', CONTAINER],
                       capture_output=True, text=True)
        self._write_conf(False)
        r = subprocess.run([
            'docker', 'run', '-d', '--name', CONTAINER,
            '--network', 'intelligent-audio-test_default',
            '-p', '%s:80' % PORT,
            '-v', '%s:/usr/share/nginx/html:ro' % DIST,
            '-v', '%s:/etc/nginx/conf.d/default.conf:ro' % self.conf,
            'nginx:alpine',
        ], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit('docker run 失败: %s' % r.stderr)
        time.sleep(2)

    def _write_conf(self, error):
        with open(self.conf, 'w', encoding='utf-8') as f:
            f.write(NGINX_CONF.format(error_location=ERROR_LOCATION if error else ''))
        self.error = error

    def set_error(self, error):
        if error == self.error:
            return
        self._write_conf(error)
        subprocess.run(['docker', 'exec', CONTAINER, 'nginx', '-s', 'reload'],
                       capture_output=True, text=True)
        # 注入失败态后等开关真正生效（reload 有竞态：500 秒回，可探测）；
        # 放行态不探测——真实库用例列表接口本身慢（全表聚合可达 50s+），
        # 额外探测会与页面请求争用，交给后续 UI 等待判定即可。
        if not error:
            time.sleep(1.5)
            return
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._probe_status(timeout=20) == 500:
                return
            time.sleep(1.0)
        raise SystemExit('失败注入未生效（期望 500）')

    def _probe_status(self, timeout=20):
        import urllib.request
        import urllib.error
        try:
            with urllib.request.urlopen(
                    '%s/api/v1/testcases?page=1&per_page=1' % BASE,
                    timeout=timeout) as r:
                return r.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:
            return None

    def stop(self):
        subprocess.run(['docker', 'rm', '-f', CONTAINER],
                       capture_output=True, text=True)
        shutil.rmtree(self.dir, ignore_errors=True)


def _opts():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-gpu')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    return o


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def login(drv):
    drv.get(BASE + '/login')
    time.sleep(2.5)
    if '/login' not in drv.current_url:
        return
    enter = drv.find_elements(By.XPATH, "//button[contains(., '进入工作台')]")
    if enter:
        js_click(drv, enter[0])
        try:
            WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
            time.sleep(1.0)
            return
        except Exception as exc:
            log('open-mode enter: %s' % exc)
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_elements(By.XPATH, "//button[contains(., '登')]")[0].click()
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.5)


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)


def body_text(drv):
    return drv.execute_script('return document.body.innerText')


def wait_text(drv, text, timeout=60):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.innerText'))


def wait_text_gone(drv, text, timeout=90):
    WebDriverWait(drv, timeout).until(
        lambda d: text not in d.execute_script('return document.body.innerText'))


def retry_buttons(drv):
    return drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")


def group_card_count(drv):
    return drv.execute_script(
        "return document.querySelectorAll(\"[aria-label^='全选分组']\").length")


def tag_card_count(drv):
    return drv.execute_script(
        "return document.querySelectorAll(\"[aria-label^='全选标签']\").length")


def banner_text(drv):
    return drv.execute_script(
        "const a = document.querySelector(\"[data-testid='case-list-error-banner']\");"
        "return a ? (a.innerText || '').trim() : ''")


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('shot %s' % path)


def testcases_http_log(drv):
    """性能日志里 GET /api/v1/testcases 的真实 HTTP 状态（非页内打点）"""
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = msg.get('params', {}).get('response', {})
        url = resp.get('url', '')
        if '/api/v1/testcases' in url and '?' in url:
            out.append({'url': url.split('8090')[-1], 'status': resp.get('status')})
    return out


def case_list_state(drv, view_name):
    txt = body_text(drv)
    return {
        'view': view_name,
        '错误态标题': '用例列表加载失败' in txt,
        '错误态描述': '用例列表获取失败，请重试' in txt,
        '无「没有找到符合条件的测试用例」': '没有找到符合条件的测试用例' not in txt,
        '无「尝试清空「分组」「标签」筛选」': '尝试清空「分组」「标签」筛选' not in txt,
        '无「没有找到标签分组的测试用例」': '没有找到标签分组的测试用例' not in txt,
        '无「请为测试用例添加标签」': '请为测试用例添加标签' not in txt,
        '重试按钮数': len(retry_buttons(drv)),
        '分组卡数': group_card_count(drv),
    }


def main():
    stack = Stack()
    stack.start()
    drv = webdriver.Chrome(options=_opts(), service=Service(DRIVER))
    result = {}
    try:
        login(drv)
        set_theme(drv, 'light')

        # ── 1. 分组视图首屏失败（浅色） ──
        stack.set_error(True)
        drv.get(BASE + '/testcases/by-group')
        wait_text(drv, "用例列表加载失败", 150)
        time.sleep(1.2)
        result['group_error_light'] = case_list_state(drv, 'by-group/light')
        log('group_error_light: %s' % json.dumps(
            result['group_error_light'], ensure_ascii=False))
        shot(drv, '01_by_group_error_light.png')

        # ── 2. 标签视图首屏失败（浅色） ──
        drv.get(BASE + '/testcases/by-tag')
        wait_text(drv, "用例列表加载失败", 150)
        time.sleep(1.2)
        result['tag_error_light'] = case_list_state(drv, 'by-tag/light')
        log('tag_error_light: %s' % json.dumps(
            result['tag_error_light'], ensure_ascii=False))
        shot(drv, '02_by_tag_error_light.png')

        # ── 3. 重试恢复（接口放行）：错误态消失即为恢复；标签视图无标签时是合法的空态 ──
        stack.set_error(False)
        btns = retry_buttons(drv)
        result['retry_clicked'] = bool(btns)
        if btns:
            js_click(drv, btns[0])
        wait_text_gone(drv, '用例列表加载失败', 240)
        time.sleep(1.5)
        txt = body_text(drv)
        result['retry_ok'] = {
            '错误态消失': '用例列表加载失败' not in txt,
            '标签卡数': tag_card_count(drv),
            '标签视图空态（无标签用例，合法）': '没有找到标签分组的测试用例' in txt,
            '重试按钮已收起': len(retry_buttons(drv)) == 0,
        }
        log('retry_ok: %s' % json.dumps(result['retry_ok'], ensure_ascii=False))
        shot(drv, '03_by_tag_retry_ok_light.png')

        # ── 3b. 回分组视图（数据就绪，作为后续「保留旧数据」的基线） ──
        drv.get(BASE + '/testcases/by-group')
        WebDriverWait(drv, 240).until(lambda d: group_card_count(d) > 0)
        time.sleep(1.5)
        result['group_loaded'] = {'分组卡数': group_card_count(drv)}
        log('group_loaded: %s' % json.dumps(
            result['group_loaded'], ensure_ascii=False))
        shot(drv, '03b_by_group_loaded_light.png')

        # ── 4. 已加载数据后筛选失败：保留旧数据 + 行内提示 + toast ──
        cards_before = group_card_count(drv)
        stack.set_error(True)
        search = drv.find_element(
            By.CSS_SELECTOR, "input[placeholder='搜索用例名称或描述']")
        search.send_keys('接线测试_')
        banner = ''
        try:
            WebDriverWait(drv, 45).until(lambda d: bool(banner_text(d)))
            banner = banner_text(drv)
        except Exception as exc:
            log('banner wait: %s' % exc)
        time.sleep(1.0)
        txt = body_text(drv)
        result['filter_error_stale'] = {
            '行内提示': banner,
            'toast 已提示保留数据': '已保留上一次加载的数据' in txt,
            '分组卡数（筛选前）': cards_before,
            '分组卡数（失败后保留）': group_card_count(drv),
            '无「没有找到符合条件的测试用例」': '没有找到符合条件的测试用例' not in txt,
        }
        log('filter_error_stale: %s' % json.dumps(
            result['filter_error_stale'], ensure_ascii=False))
        shot(drv, '04_filter_error_stale_light.png')

        # 行内重试恢复（失败注入关闭 + 点行内重试）
        stack.set_error(False)
        btns = retry_buttons(drv)
        if btns:
            js_click(drv, btns[-1])
        WebDriverWait(drv, 90).until(lambda d: not banner_text(d))
        time.sleep(1.0)
        result['stale_retry_ok'] = {
            '行内提示消失': not banner_text(drv),
            '分组卡数': group_card_count(drv),
        }
        log('stale_retry_ok: %s' % json.dumps(
            result['stale_retry_ok'], ensure_ascii=False))
        shot(drv, '05_filter_error_retry_ok_light.png')

        # ── 5. 深色失败态 ──
        stack.set_error(True)
        set_theme(drv, 'dark')
        drv.get(BASE + '/testcases/by-group')
        wait_text(drv, "用例列表加载失败", 150)
        time.sleep(1.2)
        txt = body_text(drv)
        result['group_error_dark'] = {
            'is_dark': drv.execute_script(
                "return document.documentElement.classList.contains('dark')"),
            '错误态标题': '用例列表加载失败' in txt,
            '无「没有找到符合条件的测试用例」': '没有找到符合条件的测试用例' not in txt,
            '重试按钮数': len(retry_buttons(drv)),
        }
        log('group_error_dark: %s' % json.dumps(
            result['group_error_dark'], ensure_ascii=False))
        shot(drv, '06_by_group_error_dark.png')

        result['http'] = testcases_http_log(drv)
        log('GET /api/v1/testcases 状态: %s' % json.dumps(
            result['http'], ensure_ascii=False))
    finally:
        log('RESULT=' + json.dumps(result, ensure_ascii=False, indent=2))
        try:
            drv.quit()
        finally:
            stack.stop()


if __name__ == '__main__':
    main()
