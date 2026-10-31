# -*- coding: utf-8 -*-
"""INT-2195 自测：执行步「实时内容流」面板只对 websocket_api（流式）目标渲染。

环境：本卡工作树 dev server 5377（代理 docker 网关 15000，真实库 intelligent_audio_test）。
核对：
  A. 只选 HTTP 非流式 API（matrix_http_nonstream_1793352373）启动任务 → 执行步 DOM 不出现
     「实时内容流 / 等待 AI 实时输出…」，且任务运行中采样全程为 False；创建的任务
     device_types == ['http_api']（后端回读）；
  B. 对照：选流式 API（matrix_ws_realtime_openai_1793352590）启动任务 → 运行中面板渲染；
  C. 浅色 / 深色截图、Network（POST /tasks、POST /tasks/{id}/start 状态码）。
运行：python tests/ui/verify_int2195_realtime_panel.py
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('REACT_BASE', 'http://localhost:5377')
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')

import capture_int1485_system_settings as B  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ART = os.path.join(B.PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2195')
os.makedirs(ART, exist_ok=True)
TS = time.strftime('%m%d%H%M%S')
CASE_NAME = 'matrix_case_1793352275'
HTTP_API = 'matrix_http_nonstream_1793352373'
# 真实库里存活的流式 API 都已软删、存活的 2 个流式 API（421/424）离线不可选；
# 对照用自建夹具（接线测试_ 前缀，run 结束删除）。
WS_API = '接线测试_INT2195_ws_%s' % TS
RESULTS = []
TASKS = []


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': str(detail)[:800], 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:600])


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    print('SHOT ' + path)
    return path


def body(drv):
    return B.body_text(drv)


def panel_present(drv):
    t = body(drv)
    return ('实时内容流' in t, '等待 AI 实时输出' in t)


def _find_logs_title_js():
    return """(function(){
        var titles = Array.from(document.querySelectorAll("[data-slot='card-title']"))
            .filter(function(e){ return (e.textContent || '').indexOf('实时日志') >= 0; });
        return titles.length ? titles[titles.length - 1] : null;
    })()"""


def scroll_to_logs(drv):
    """滚动到页底「实时日志」卡片：内容区是内层 overflow-y-auto，逐个可滚动容器拉到底。"""
    drv.execute_script('''
        Array.from(document.querySelectorAll('*')).forEach(function(e){
            if (e.scrollHeight > e.clientHeight + 40) { e.scrollTop = e.scrollHeight; }
        });
        var title = ''' + _find_logs_title_js() + ''';
        if (title) {
            var card = title.closest("[data-slot='card']") || title;
            card.scrollIntoView({block: 'center'});
        }
    ''')
    time.sleep(0.6)
    return drv.execute_script('''
        var title = ''' + _find_logs_title_js() + ''';
        if (!title) return null;
        var r = title.getBoundingClientRect();
        return {top: Math.round(r.top), h: Math.round(r.height), vh: window.innerHeight};
    ''')


def reqs(drv):
    return drv.execute_script('return window.__reqs || [];')


def click_role_checkbox(drv, label, timeout=25):
    xpath = "//*[@role='checkbox' and @aria-label='%s']" % label

    def probe(d):
        for el in d.find_elements(By.XPATH, xpath):
            if B.visible(el):
                return el
        return False
    el = WebDriverWait(drv, timeout).until(probe)
    B.js_click(drv, el)
    return el


def click_footer(drv, text, timeout=25):
    def probe(d):
        for el in d.find_elements(By.XPATH, "//button[normalize-space(.)='%s']" % text):
            if B.visible(el):
                return el
        return False
    el = WebDriverWait(drv, timeout).until(probe)
    B.js_click(drv, el)
    return el


def dark_on(drv):
    drv.execute_script(
        "try{localStorage.setItem('iatp:theme:v1:mode','dark');}catch(e){};"
        "document.documentElement.classList.add('dark');")
    time.sleep(0.8)
    cls = drv.execute_script('return document.documentElement.className')
    bg = drv.execute_script('return getComputedStyle(document.body).backgroundColor')
    return cls, bg


def light_on(drv):
    drv.execute_script(
        "try{localStorage.setItem('iatp:theme:v1:mode','light');}catch(e){};"
        "document.documentElement.classList.remove('dark');")
    time.sleep(0.8)
    cls = drv.execute_script('return document.documentElement.className')
    bg = drv.execute_script('return getComputedStyle(document.body).backgroundColor')
    return cls, bg


def open_flow(drv):
    # 全局算法选择会持久化在 iatp:algorithm:v1；残留的具体算法会把步骤二 API 网格筛成
    # 该算法名下的一小组（matrix_ws_* 不在其中），清掉回到「全部算法」口径。
    drv.execute_script("try{localStorage.removeItem('iatp:algorithm:v1');}catch(e){}")
    B.goto(drv, '/start-test', '选择测试用例')
    # 步骤一：按名称搜索并把「命中」用例全选进选择集（搜索命中 1 条 → 全选结果 = 1 条）
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
    B.set_input(drv, box, CASE_NAME)
    WebDriverWait(drv, 25).until(lambda d: '命中' in body(d))
    time.sleep(1.0)
    click_role_checkbox(drv, '全选用例')
    WebDriverWait(drv, 20).until(lambda d: '已选 1 条用例' in body(d))
    record('步骤一 圈定 1 条用例', True, '已选 1 条用例')
    click_footer(drv, '下一步')
    WebDriverWait(drv, 30).until(lambda d: '搜索设备或 API 名称' in body(d) or d.find_elements(
        By.CSS_SELECTOR, "input[placeholder='搜索设备或 API 名称']"))
    record('进入步骤二 选择设备/API', True, drv.current_url)


def select_api(drv, api_name):
    box = drv.find_element(By.CSS_SELECTOR, "input[placeholder='搜索设备或 API 名称']")
    B.set_input(drv, box, api_name)
    time.sleep(1.5)
    click_role_checkbox(drv, '选择 API %s' % api_name)
    time.sleep(0.5)
    record('步骤二 勾选 API %s' % api_name, True, '')


def launch(drv, api_name, task_name):
    """步骤二 → 开始测试 → 任务名称弹窗 → 弹窗内开始测试 → 执行步。返回 (task_id, net)。"""
    click_footer(drv, '开始测试')
    WebDriverWait(drv, 20).until(lambda d: '任务名称' in body(d))
    name_input = drv.find_element(By.CSS_SELECTOR, '#task-name')
    B.set_input(drv, name_input, task_name)
    time.sleep(0.3)
    dialog_btn = drv.find_element(
        By.XPATH, "//*[@data-slot='dialog-content']//button[normalize-space(.)='开始测试']")
    B.reset_reqs(drv)
    B.js_click(drv, dialog_btn)
    # 执行步：URL step=2 且任务详情卡出现
    WebDriverWait(drv, 60).until(lambda d: 'step=2' in d.current_url)
    record('启动后进入执行步（step=2）', True, drv.current_url)
    return task_name


def task_id_from_reqs(drv):
    tid = None
    for r in reqs(drv):
        url = (r.get('url') or '')
        if '/api/v1/tasks' in url and (r.get('method') or '').upper() == 'POST' and url.rstrip('/').endswith('/tasks'):
            try:
                payload = json.loads(r.get('resp') or '{}')
                tid = ((payload.get('data') or {}).get('id')) or payload.get('id')
            except Exception:
                pass
    return tid


def sample_run(drv, token, seconds=18.0, interval=0.5):
    """执行步采样：面板是否出现 + 任务状态。返回样本列表。"""
    samples = []
    tid = None
    start = time.time()
    while time.time() - start < seconds:
        try:
            has_panel, has_wait = panel_present(drv)
        except Exception:
            has_panel, has_wait = (False, False)
        status = None
        if tid is None:
            tid = task_id_from_reqs(drv)
        if tid is not None:
            try:
                st, d = B.api('/api/v1/tasks/%s' % tid, token)
                status = ((d or {}).get('data') or {}).get('execution_status')
            except Exception:
                status = None
        samples.append({'t': round(time.time() - start, 1), 'panel': has_panel,
                        'wait': has_wait, 'status': status})
        time.sleep(interval)
    return tid, samples


def summarize(samples):
    running = [s for s in samples if s['status'] in ('running', 'pending', None)]
    return {
        'n': len(samples),
        'panel_any': any(s['panel'] for s in samples),
        'panel_running': any(s['panel'] for s in samples if s['status'] in ('running', 'pending')),
        'statuses': sorted({str(s['status']) for s in samples}),
        'first': samples[:3],
    }


def net_evidence(drv):
    out = []
    for r in reqs(drv):
        url = r.get('url') or ''
        if '/api/v1/tasks' in url and (r.get('method') or '').upper() == 'POST':
            out.append({'method': r.get('method'), 'url': url, 'status': r.get('status')})
    return out


def stop_task(token, task_id):
    if not task_id:
        return None
    try:
        st, body_ = B.api('/api/v1/tasks/%s/stop' % task_id, token, method='POST', body={})
        return (st, body_)
    except Exception as e:
        return ('ERR', str(e)[:120])


def stop_and_delete_task(token, task_id):
    """停止（已终态 400「只有执行中…」属正常）+ 软删除自建任务。"""
    if not task_id:
        return
    st, body_ = stop_task(token, task_id) or (None, None)
    msg = str((body_ or {}).get('message') if isinstance(body_, dict) else '')
    stopped = st in (200, 201, 204) or (st == 400 and '才能停止' in msg)
    record('停止自建任务 %s' % task_id, stopped, 'status=%s %s' % (st, msg[:160]))
    st2, body2 = B.api('/api/v1/tasks/%s' % task_id, token, method='DELETE')
    record('删除自建任务 %s' % task_id, st2 in (200, 204),
           'status=%s %s' % (st2, str(body2)[:120]))


def create_ws_fixture(token):
    """自建流式 API 夹具（websocket + streaming=true，online），供正对照选目标。"""
    st, payload = B.api('/api/v1/apis', token, method='POST', body={
        'name': WS_API,
        'algorithm_type': 'voice_llm',
        'protocol': 'websocket',
        'streaming': True,
        'status': 'online',
        'default_max_process': 1,
        'default_max_timeout': 30,
        'default_max_audio_duration': 60,
        'endpoints': [{
            # 常驻矩阵 mock 服务（宿主机 5098），后端启动前可达性校验才能通过
            'endpoint': 'ws://host.docker.internal:5098', 'name': '', 'priority': 0,
            'max_process': 5, 'max_timeout': 60, 'max_audio_duration': 60,
            'status': 'online', 'health_score': 100, 'description': '',
        }],
        'meta': {'method': 'POST'},
    })
    data = (payload or {}).get('data') if isinstance(payload, dict) else None
    api_id = (data or {}).get('id') if isinstance(data, dict) else None
    if api_id is None and isinstance(data, int):
        api_id = data
    record('自建流式 API 夹具', st in (200, 201) and api_id is not None,
           'status=%s id=%s' % (st, api_id))
    if api_id is not None:
        st2, d = B.api('/api/v1/apis?per_page=1000', token)
        row = next((x for x in ((d or {}).get('data') or {}).get('items') or []
                    if x.get('name') == WS_API), None)
        record('夹具出现在 API 列表且在线', row is not None and row.get('status') == 'online',
               'row=%s' % (row and {'id': row.get('id'), 'status': row.get('status')}))
        if row and row.get('status') != 'online':
            B.api('/api/v1/apis/%s' % api_id, token, method='PUT', body={'status': 'online'})
    return api_id


def delete_ws_fixture(token, api_id):
    if not api_id:
        return
    st, body_ = B.api('/api/v1/apis/%s' % api_id, token, method='DELETE')
    record('删除自建流式 API 夹具', st in (200, 204), 'status=%s %s' % (st, str(body_)[:120]))


def run_case(drv, token, api_name, label, expect_panel):
    open_flow(drv)
    select_api(drv, api_name)
    task_name = '接线测试_INT2195_%s_%s' % (label, TS)
    launch(drv, api_name, task_name)
    TASKS.append(task_name)
    # 启动后等任务详情卡落地（骨架屏不含实时日志卡）再取证；运行窗口短，先取证再长采样
    WebDriverWait(drv, 20).until(lambda d: '实时日志' in body(d))
    rect = scroll_to_logs(drv)
    record('%s 实时日志卡滚入视口' % label,
           bool(rect) and -10 <= rect['top'] <= rect['vh'],
           'rect=%s' % rect)
    at_light = panel_present(drv)
    shot(drv, '%s_logs_light' % label)
    cls, bg = dark_on(drv)
    time.sleep(0.2)
    at_dark = panel_present(drv)
    shot(drv, '%s_logs_dark' % label)
    light_on(drv)
    record('%s 浅/深色（实时日志卡）主题断言' % label,
           'dark' in cls and bg == 'rgb(19, 29, 46)',
           'dark_class=%s dark_bg=%s light_panel=%s dark_panel=%s' % (cls, bg, at_light, at_dark))
    task_id, samples = sample_run(drv, token)
    summ = summarize(samples)
    record('%s 任务 id' % label, task_id is not None, 'task_id=%s' % task_id)
    if task_id:
        st, d = B.api('/api/v1/tasks/%s' % task_id, token)
        dt = ((d or {}).get('data') or {}).get('device_types')
        record('%s 任务 device_types 回读' % label,
               (dt == ['http_api']) if api_name == HTTP_API else ('websocket_api' in (dt or [])),
               'device_types=%s status=%s' % (dt, st))
    record('%s 运行中面板出现判定' % label, summ['panel_running'] == expect_panel,
           json.dumps(summ, ensure_ascii=False))
    if expect_panel:
        record('%s 抓图时即可见实时内容流' % label, at_light[0] or at_dark[0],
               'light=%s dark=%s' % (at_light, at_dark))
    return task_id, summ


def main():
    drv = B.driver_init()
    token = None
    try:
        token, _ = B.rsa_login_token('接线测试_admin', 'JieXianTest@2026')
        drv.get(B.BASE + '/login')
        B.wait_ready(drv)
        drv.execute_script(
            'try{localStorage.setItem(arguments[0], arguments[1]);}catch(e){}', B.TOKEN_KEY, token)
        record('登录（接线测试_admin）', True, B.BASE)

        # A. HTTP 非流式 API：不应渲染实时内容流
        http_id, http_summ = run_case(drv, token, HTTP_API, 'http', expect_panel=False)
        net = net_evidence(drv)
        record('A4 Network POST /tasks 与 /start', any(
            '/tasks' in x['url'] and x['status'] in (200, 201) for x in net),
               json.dumps(net, ensure_ascii=False)[:500])

        # B. 流式 API 对照：运行中应渲染实时内容流（自建 websocket 夹具）
        ws_fixture_id = create_ws_fixture(token)
        ws_id, ws_summ = run_case(drv, token, WS_API, 'ws', expect_panel=True)

        # 停止 + 清理自建任务/夹具
        for tid in (http_id, ws_id):
            stop_and_delete_task(token, tid)
        delete_ws_fixture(token, ws_fixture_id)

        ok = all(r['ok'] for r in RESULTS)
        print('\n==== SUMMARY %s (%d/%d) ====' % ('ALL PASS' if ok else 'FAIL',
                                                  sum(1 for r in RESULTS if r['ok']), len(RESULTS)))
        for r in RESULTS:
            print(('[PASS] ' if r['ok'] else '[FAIL] ') + r['step'])
        with open(os.path.join(ART, 'results_%s.json' % TS), 'w', encoding='utf-8') as f:
            json.dump({'results': RESULTS, 'summary': {'http': http_summ, 'ws': ws_summ}},
                      f, ensure_ascii=False, indent=2)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
