# -*- coding: utf-8 -*-
"""INT-1627 验收脚本：发布任务弹窗三条修复实测（真实库栈 docker :15000）。

覆盖面（逐条对应卡内验收标准）：
1. 来源任务 Select 闭合态显示任务名（不再是裸 id `419`）；
2. /api/v1/tasks 返回 500 → 弹窗出现 role=alert 错误态 + 「重试」，且主钮「发布」
   **不再 disabled**；点「重试」接口恢复后选项加载、触发器回显任务名；
3. /api/v1/tasks 长时间无响应 → 8s 后出现「来源任务加载较慢」+「重新加载」；
4. 从日常任务行「发布」真实发布 → POST /published-tasks 201 → GET 详情
   `has_task_snapshot:true` + `snapshot_config.taskSnapshot` → 已发布页签展开行不再显示
   「历史版本（发布时未冻结任务详情）」、出现「查看冻结任务详情」→ 弹窗三节正常渲染。

失败注入在网关层（真实 HTTP 500 / 真实挂起），由一次性 nginx 旁路容器完成：
dist ← frontend-react/dist（**先 pnpm build**），/api → api_gateway:5000。
注意：**不要用页内 window.fetch reject 模拟失败**——那种注入下 base-ui 不会清空受控值，
弹窗表现与真实 500 不同（会漏掉「错误态主钮仍 disabled」这个缺陷）。
前置：`cd frontend-react && pnpm build`；docker 可跑（network intelligent-audio-test_default）。

用法：
    python tests/ui/verify_int1627_publish_dialog.py
环境变量：CHROMEDRIVER（默认本机缓存驱动）、INT1627_PORT（默认 15311）。

清理：本脚本自建的 published_tasks 行在 finally 里按 id 删除（DELETE ... WHERE id IN (...)），
真实记录只读。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DIST = os.path.join(REPO, 'frontend-react', 'dist')
PORT = os.environ.get('INT1627_PORT', '15311')
BASE = 'http://127.0.0.1:%s' % PORT
API = 'http://127.0.0.1:15000/api/v1'
CONTAINER = 'iat-int1627-verify'
PG = 'intelligent-audio-test-postgres-1'
DRIVER = os.environ.get(
    'CHROMEDRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
ART = os.path.join(REPO, 'tests', 'ui', 'artifacts', 'int1627')
os.makedirs(ART, exist_ok=True)

TASK_ID = 419
TASK_NAME = '小艺拒识E2E测试任务_2026/10/13 17:32:59'

NGINX_CONF = """server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
{inject}
    location /api/ {
        proxy_pass http://api_gateway:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    location /health {
        proxy_pass http://api_gateway:5000;
        proxy_set_header Host $host;
    }

    location /socket.io/ {
        proxy_pass http://api_gateway:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://api_gateway:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
"""

INJECT_ERROR = """
    location = /api/v1/tasks {
        return 500;
    }
"""

# 挂起：目标 IP 不可达，nginx 连接一直徘徊 → 前端 60s 硬超时 / 8s 慢提示
INJECT_SLOW = """
    location = /api/v1/tasks {
        proxy_pass http://10.255.255.1:5000;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
"""


def log(m):
    print(m, flush=True)


def http_json(url, timeout=60, method='GET', body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode('utf-8'))


def psql(sql):
    r = subprocess.run(
        ['docker', 'exec', PG, 'psql', '-U', 'intelligent_audio_test',
         '-d', 'intelligent_audio_test', '-t', '-A', '-c', sql],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit('psql 失败: %s' % r.stderr)
    return r.stdout.strip()


class Stack:
    """一次性 nginx 旁路容器 + conf 开关（真实 HTTP 500 / 真实挂起）"""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='int1627_')
        self.conf = os.path.join(self.dir, 'default.conf')
        self.mode = 'normal'

    def start(self):
        if not os.path.isdir(DIST):
            raise SystemExit('缺少 %s，请先 cd frontend-react && pnpm build' % DIST)
        subprocess.run(['docker', 'rm', '-f', CONTAINER], capture_output=True, text=True)
        self._write_conf('normal')
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

    def _write_conf(self, mode):
        inject = ''
        if mode == 'error':
            inject = INJECT_ERROR
        elif mode == 'slow':
            inject = INJECT_SLOW
        with open(self.conf, 'w', encoding='utf-8') as f:
            f.write(NGINX_CONF.replace('{inject}', inject))
        self.mode = mode

    def set_mode(self, mode):
        if mode == self.mode:
            return
        self._write_conf(mode)
        subprocess.run(['docker', 'exec', CONTAINER, 'nginx', '-s', 'reload'],
                       capture_output=True, text=True)
        if mode == 'error':
            deadline = time.time() + 30
            while time.time() < deadline:
                if self._probe_status() == 500:
                    log('  [stack] 500 注入生效')
                    return
                time.sleep(1.0)
            raise SystemExit('失败注入未生效（期望 500）')
        if mode == 'normal':
            # 恢复放行：探测真实 200 后再继续
            deadline = time.time() + 60
            while time.time() < deadline:
                if self._probe_status(timeout=30) == 200:
                    log('  [stack] 恢复正常')
                    return
                time.sleep(1.5)
            raise SystemExit('放行态恢复未生效（期望 200）')
        time.sleep(1.0)

    def _probe_status(self, timeout=20):
        try:
            with urllib.request.urlopen(
                    '%s/api/v1/tasks?page=1&per_page=1' % BASE, timeout=timeout) as r:
                return r.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:
            return None

    def stop(self):
        subprocess.run(['docker', 'rm', '-f', CONTAINER], capture_output=True, text=True)
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


def theme_is(drv, mode):
    return drv.execute_script(
        "return document.documentElement.classList.contains('dark')") == (mode == 'dark')


def body_text(drv):
    return drv.execute_script('return document.body.innerText')


def wait_text(drv, text, timeout=60):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.innerText'))


def wait_text_gone(drv, text, timeout=90):
    WebDriverWait(drv, timeout).until(
        lambda d: text not in d.execute_script('return document.body.innerText'))


def shot(drv, name):
    p = os.path.join(ART, name)
    drv.save_screenshot(p)
    log('  截图 %s' % p)
    return p


def drain_network(drv):
    """读走当前性能日志里的响应记录（method/url/status）。"""
    out = []
    try:
        logs = drv.get_log('performance')
    except Exception:
        return out
    for entry in logs:
        try:
            msg = json.loads(entry['message'])
        except Exception:
            continue
        m = msg.get('message', {})
        if m.get('method') != 'Network.responseReceived':
            continue
        p = m.get('params', {})
        resp = p.get('response', {})
        url = resp.get('url', '')
        if '/api/' in url:
            out.append({'url': url, 'status': resp.get('status'),
                        'type': p.get('type')})
    return out


def open_daily(drv, page_size=100):
    drv.get(BASE + '/tasks/daily?pageSize=%d' % page_size)
    wait_text(drv, TASK_NAME, 90)
    time.sleep(1.0)


def open_publish_dialog(drv):
    """从日常任务行 419 的「任务操作」→「发布」打开弹窗。"""
    btn = WebDriverWait(drv, 30).until(lambda d: d.find_element(
        By.XPATH,
        "//tr[contains(., '%s')]//button[@aria-label='任务操作']" % TASK_NAME))
    js_click(drv, btn)
    item = WebDriverWait(drv, 20).until(lambda d: d.find_element(
        By.XPATH, "//*[@role='menuitem' and normalize-space(.)='发布']"))
    js_click(drv, item)
    WebDriverWait(drv, 20).until(lambda d: d.find_elements(
        By.XPATH, "//div[@role='dialog'][contains(., '发布任务')]"))
    time.sleep(0.4)


def dialog_text(drv):
    el = drv.find_element(By.XPATH, "//div[@role='dialog'][contains(., '发布任务')]")
    return el.text


def trigger_text(drv):
    el = drv.find_element(By.XPATH, "//button[@aria-label='选择来源任务']")
    return el.text.strip()


def publish_button(drv):
    return drv.find_element(
        By.XPATH,
        "//div[@role='dialog'][contains(., '发布任务')]//button[normalize-space(.)='发布']")


def close_dialog(drv):
    try:
        btn = drv.find_element(
            By.XPATH,
            "//div[@role='dialog'][contains(., '发布任务')]//button[normalize-space(.)='取消']")
        js_click(drv, btn)
    except Exception:
        try:
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
    WebDriverWait(drv, 20).until(lambda d: not d.find_elements(
        By.XPATH, "//div[@role='dialog'][contains(., '发布任务')]"))


def main():
    ev = {'card': 'INT-1627', 'base': BASE, 'task_id': TASK_ID, 'phases': {}}
    created_ids = []

    log('[0] 环境核验')
    st, health = http_json('http://127.0.0.1:15000/health')
    log('  /health %s database=%s' % (st, health.get('database')))
    assert health.get('database') == 'intelligent_audio_test', '连错库：%s' % health
    base_rows = psql('select count(*), coalesce(max(id),0) from published_tasks')
    log('  published_tasks 基线 (count,maxid)=%s' % base_rows)
    ev['phases']['baseline'] = {'health': health, 'published_tasks': base_rows}

    st, t = http_json('%s/tasks/%d' % (API, TASK_ID))
    log('  task %d: %s status=%s cases=%s' % (
        TASK_ID, t['data']['name'], t['data']['execution_status'],
        t['data'].get('total_cases')))
    assert t['data']['execution_status'] in ('completed', 'failed', 'stopped', 'pending')

    stack = Stack()
    drv = None
    try:
        stack.start()
        log('  旁路容器 %s → %s' % (CONTAINER, BASE))
        drv = webdriver.Chrome(service=Service(DRIVER), options=_opts())
        drv.set_script_timeout(60)
        login(drv)

        # ============ 1. 触发器回显任务名（浅色） ============
        log('[1] 来源任务 Select 闭合态回显任务名（浅色）')
        set_theme(drv, 'light')
        open_daily(drv)
        assert theme_is(drv, 'light'), '浅色主题未生效'
        open_publish_dialog(drv)
        tt = trigger_text(drv)
        log('  触发器文案 = %r' % tt)
        assert tt != str(TASK_ID), '触发器仍是裸 id：%r' % tt
        assert TASK_NAME in tt, '触发器未回显任务名：%r' % tt
        assert ('用例 138' in tt), '触发器未带状态/用例数标签：%r' % tt
        txt = dialog_text(drv)
        assert '发布' in txt
        shot(drv, 'int1627_50_publish_dialog_light.png')
        ev['phases']['trigger_light'] = {'trigger': tt, 'task_name': TASK_NAME}
        drain_network(drv)
        # 展开下拉，核对选项文案（100 项）
        trig = drv.find_element(By.XPATH, "//button[@aria-label='选择来源任务']")
        js_click(drv, trig)
        WebDriverWait(drv, 40).until(lambda d: d.find_elements(
            By.XPATH, "//*[@role='option']"))
        time.sleep(1.2)
        opts = drv.find_elements(By.XPATH, "//*[@role='option']")
        opt_texts = [o.text for o in opts]
        log('  下拉选项数 = %d，首项 = %r' % (len(opt_texts), opt_texts[0] if opt_texts else None))
        assert len(opt_texts) > 1, '下拉选项未加载'
        assert all(not o.strip().isdigit() for o in opt_texts), '存在裸 id 选项'
        shot(drv, 'int1627_51_publish_options_light.png')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        ev['phases']['trigger_light']['option_count'] = len(opt_texts)
        ev['phases']['trigger_light']['option_first'] = opt_texts[0] if opt_texts else None
        close_dialog(drv)

        # ============ 2. 失败错误态 + 重试（浅色） ============
        log('[2] 列表 500 → 错误态 + 重试，主钮不 disabled（浅色）')
        open_daily(drv)
        stack.set_mode('error')
        drain_network(drv)
        open_publish_dialog(drv)
        alert = WebDriverWait(drv, 60).until(lambda d: d.find_elements(
            By.XPATH, "//div[@role='alert']"))
        atext = alert[0].text.strip()
        log('  role=alert 文案 = %r' % atext)
        assert '重试' in atext, '错误态缺少重试按钮：%r' % atext
        btn = publish_button(drv)
        log('  主钮「发布」disabled = %s' % btn.get_attribute('disabled'))
        assert btn.get_attribute('disabled') is None, (
            '错误态下主钮仍被禁用（锁死用户）；触发器=%r。根因：预选任务只经 Select 的 items '
            '映射回显、未渲染成真实 SelectItem，base-ui 在列表失败（无可渲染项）时触发 '
            'onValueChange(null) 清空受控值 → 触发器回退 placeholder、submitTaskId=null'
            % trigger_text(drv))
        tt = trigger_text(drv)
        log('  错误态触发器 = %r' % tt)
        assert TASK_NAME in tt, '错误态下触发器未保留预选任务名：%r' % tt
        shot(drv, 'int1627_60_publish_error_light.png')
        net = drain_network(drv)
        err_net = [n for n in net if '/api/v1/tasks' in n['url']]
        log('  错误态 /tasks 响应: %s' % err_net)
        assert any(n['status'] == 500 for n in err_net), '未观测到真实 500'
        ev['phases']['error_light'] = {'alert': atext, 'publish_disabled': False,
                                       'trigger': tt, 'network': err_net[-3:]}
        close_dialog(drv)

        # ============ 2b. 失败错误态（深色）+ 重试恢复 ============
        log('[2b] 错误态深色 + 点重试恢复')
        set_theme(drv, 'dark')
        open_daily(drv)
        assert theme_is(drv, 'dark'), '深色主题未生效'
        stack.set_mode('error')
        open_publish_dialog(drv)
        WebDriverWait(drv, 60).until(lambda d: d.find_elements(
            By.XPATH, "//div[@role='alert']"))
        shot(drv, 'int1627_61_publish_error_dark.png')
        ev['phases']['error_dark'] = {'alert': drv.find_element(
            By.XPATH, "//div[@role='alert']").text.strip()}
        stack.set_mode('normal')
        retry = drv.find_element(
            By.XPATH, "//div[@role='alert']//button[normalize-space(.)='重试']")
        js_click(drv, retry)
        WebDriverWait(drv, 90).until(lambda d: not d.find_elements(
            By.XPATH, "//div[@role='alert']"))
        WebDriverWait(drv, 60).until(
            lambda d: '用例 138' in trigger_text(d))
        tt2 = trigger_text(drv)
        log('  重试后触发器 = %r' % tt2)
        assert TASK_NAME in tt2 and '用例 138' in tt2
        shot(drv, 'int1627_62_publish_retry_ok_dark.png')
        ev['phases']['retry_dark'] = {'trigger_after_retry': tt2}
        close_dialog(drv)

        # ============ 3. 慢加载提示（浅色） ============
        log('[3] 列表挂起 → 8s 慢提示 + 重新加载')
        set_theme(drv, 'light')
        open_daily(drv)
        stack.set_mode('slow')
        open_publish_dialog(drv)
        t0 = time.time()
        WebDriverWait(drv, 40).until(
            lambda d: '来源任务加载较慢' in dialog_text(d))
        dt = time.time() - t0
        slow_text = dialog_text(drv)
        log('  慢提示出现耗时 = %.1fs' % dt)
        assert 5 <= dt <= 30, '慢提示时机异常：%.1fs' % dt
        assert '重新加载' in slow_text
        shot(drv, 'int1627_63_publish_slow_light.png')
        ev['phases']['slow_light'] = {'seen_after_s': round(dt, 1)}
        close_dialog(drv)   # 关闭即 abort 在途请求
        stack.set_mode('normal')  # 挂起请求已随卸载中止，reload 立即生效
        time.sleep(1.0)
        open_publish_dialog(drv)
        WebDriverWait(drv, 90).until(lambda d: '用例 138' in trigger_text(d))
        log('  恢复正常后触发器 = %r' % trigger_text(drv))
        close_dialog(drv)

        # ============ 4. 真实发布 + 冻结快照 ============
        log('[4] 真实发布任务 %d → 冻结 taskSnapshot' % TASK_ID)
        before_ids = [int(x) for x in psql(
            'select id from published_tasks order by id').splitlines() if x.strip()]
        open_daily(drv)
        drain_network(drv)
        open_publish_dialog(drv)
        WebDriverWait(drv, 90).until(lambda d: '用例 138' in trigger_text(d))
        shot(drv, 'int1627_64_publish_dialog_light.png')
        js_click(drv, publish_button(drv))
        WebDriverWait(drv, 90).until(lambda d: not d.find_elements(
            By.XPATH, "//div[@role='dialog'][contains(., '发布任务')]"))
        time.sleep(2.0)
        net = drain_network(drv)
        post = [n for n in net if n['url'].endswith('/api/v1/published-tasks')
                and n['status'] in (200, 201)]
        log('  POST /published-tasks 响应: %s' % post)
        assert post, '未观测到发布 201/200'
        after_ids = [int(x) for x in psql(
            'select id from published_tasks order by id').splitlines() if x.strip()]
        new_ids = [i for i in after_ids if i not in before_ids]
        log('  新建 published_tasks id = %s' % new_ids)
        assert len(new_ids) == 1, '发布未产生唯一新行：%s' % new_ids
        new_id = new_ids[0]
        created_ids.append(new_id)
        st, detail = http_json('%s/published-tasks/%d' % (API, new_id), timeout=60)
        d = detail['data']
        log('  详情 has_task_snapshot=%s taskSnapshot=%s cases=%s' % (
            d.get('has_task_snapshot'),
            isinstance(d.get('snapshot_config', {}).get('taskSnapshot'), dict),
            len(d.get('snapshot_config', {}).get('taskSnapshot', {}).get('cases', []))))
        assert d.get('has_task_snapshot') is True, '新版本未标记 has_task_snapshot'
        snap = d.get('snapshot_config', {}).get('taskSnapshot')
        assert isinstance(snap, dict), 'snapshot_config 缺 taskSnapshot'
        assert len(snap.get('cases', [])) > 0, 'taskSnapshot.cases 为空'
        ev['phases']['publish'] = {
            'published_id': new_id,
            'has_task_snapshot': d.get('has_task_snapshot'),
            'snapshot_keys': sorted(snap.keys()),
            'snapshot_case_count': len(snap.get('cases', [])),
            'snapshot_devices': len(snap.get('devices') or []),
            'snapshot_playback_devices': len(snap.get('playbackDevices') or []),
            'post_network': post[:3],
        }

        # 已发布页签展开
        log('[4b] 已发布页签展开新版本 → 冻结详情入口')
        drv.get(BASE + '/tasks/published')
        wait_text(drv, TASK_NAME, 90)
        time.sleep(1.0)
        # 展开新版本行（按任务名定位行，避免与既有版本行混淆）
        btn = WebDriverWait(drv, 30).until(lambda d: d.find_element(
            By.XPATH,
            "//tr[contains(., '%s')]//button[@aria-label='展开版本详情']" % TASK_NAME))
        js_click(drv, btn)
        wait_text(drv, '查看冻结任务详情', 90)
        time.sleep(0.6)
        body = body_text(drv)
        assert '历史版本（发布时未冻结任务详情）' not in body, '新版本仍显示 legacy 告警'
        shot(drv, 'int1627_71_published_expanded_light.png')
        open_btn = drv.find_element(
            By.XPATH, "//tr[contains(., '%s')]//button[normalize-space(.)='查看冻结任务详情']"
            % TASK_NAME)
        js_click(drv, open_btn)
        WebDriverWait(drv, 30).until(lambda d: d.find_elements(
            By.XPATH, "//div[@role='dialog'][contains(., '任务详情')]"))
        time.sleep(1.0)
        dlg = drv.find_element(By.XPATH, "//div[@role='dialog'][contains(., '任务详情')]").text
        log('  冻结任务详情弹窗首行 = %r' % dlg.splitlines()[:4])
        assert '用例' in dlg, '冻结详情弹窗未渲染用例节'
        shot(drv, 'int1627_72_task_snapshot_dialog_light.png')
        ev['phases']['snapshot_dialog'] = {'head': dlg.splitlines()[:6]}
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)

        # 深色：已发布展开 + 冻结详情
        log('[4c] 深色：已发布展开 + 冻结详情')
        set_theme(drv, 'dark')
        drv.get(BASE + '/tasks/published')
        wait_text(drv, TASK_NAME, 90)
        assert theme_is(drv, 'dark'), '深色主题未生效'
        time.sleep(1.0)
        btn = WebDriverWait(drv, 30).until(lambda d: d.find_element(
            By.XPATH,
            "//tr[contains(., '%s')]//button[@aria-label='展开版本详情']" % TASK_NAME))
        js_click(drv, btn)
        wait_text(drv, '查看冻结任务详情', 90)
        time.sleep(0.6)
        open_btn = drv.find_element(
            By.XPATH, "//tr[contains(., '%s')]//button[normalize-space(.)='查看冻结任务详情']"
            % TASK_NAME)
        js_click(drv, open_btn)
        WebDriverWait(drv, 30).until(lambda d: d.find_elements(
            By.XPATH, "//div[@role='dialog'][contains(., '任务详情')]"))
        time.sleep(1.0)
        shot(drv, 'int1627_73_task_snapshot_dialog_dark.png')
        ev['phases']['snapshot_dialog_dark'] = {'ok': True}

        log('[5] 全部断言通过')
        ev['result'] = 'PASS'
    except AssertionError as exc:
        ev['result'] = 'FAIL'
        ev['error'] = str(exc)
        log('断言失败: %s' % exc)
        if drv is not None:
            try:
                shot(drv, 'int1627_fail_%d.png' % int(time.time()))
            except Exception:
                pass
        raise
    finally:
        if drv is not None:
            try:
                drv.quit()
            except Exception:
                pass
        stack.stop()
        if created_ids:
            ids = ','.join(str(i) for i in created_ids)
            log('[cleanup] 删除自建 published_tasks id=%s' % ids)
            psql('delete from published_tasks where id in (%s)' % ids)
            left = psql('select count(*) from published_tasks')
            log('[cleanup] published_tasks 剩余 %s 行' % left)
            ev['cleanup'] = {'deleted': created_ids, 'remaining': left}
        with open(os.path.join(ART, 'evidence_int1627.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        log('证据 JSON → %s' % os.path.join(ART, 'evidence_int1627.json'))


if __name__ == '__main__':
    main()
