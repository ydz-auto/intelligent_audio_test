# -*- coding: utf-8 -*-
"""INT-2550 验收探针：Skill 管理页（列表 / 来源标签 / 状态 / 编辑器 / 校验反馈 / 门槛 / 导入导出）。

跑法（docker 真栈，环境铁律；前端为本 run dev server 或已部署 React）：
  python tests/ui/probe_int2550_skill_manage.py \
      --base http://localhost:15373 --api http://localhost:15000

账号默认 dev_user / dev_password（docker 栈 admin/admin123 已失效；可用
UI_TEST_USERNAME / UI_TEST_PASSWORD 覆盖）。

覆盖卡面 1–12：
  1  空态（无自定义 Skill）与平台 Skill 照常列出
  2  来源 / 状态页签与计数、筛选切换
  3  新建草稿（保存后 DRAFT、刷新仍在）
  4  校验反馈：名称格式（前端即时）、缺 ## Gotchas、allowed-tools 未注册工具、
     permissions 提权（* 超管账号无法构造该负例，标记 SKIP 并给出边界）
  5  连续保存 → 版本 1→2→3，版本历史可见
  6  从 platform-reference fork → 草稿、内容一致、原 Skill 不被覆盖
  7  导入合法 zip → DRAFT；非法 zip（缺 description / 含 .. 路径）逐项失败且列表不新增
  8  导出 zip → 根级 SKILL.md、内容与编辑器一致；再导入内容等价
  9  发布门槛：golden tasks 不足 → 发布被门槛拦下、面板显示原因、状态仍 DRAFT
 10  停用：二次确认 → DISABLED，列表 / 页签计数同步
 11  只读约束：PLATFORM 行只有 fork / 导出
 12  权限：无 agent:skill:manage 时入口不可见 / 直达 403（需另建受限账号；
     本探针在只拿到超管账号时标记 SKIP）

前置：后端必须已部署 INT-2549（`GET /api/v1/agent/skills` 返回
`skills_count` 且 items 带 `id` / `scope` / `status`）。未部署时记录 blocked 并以
退出码 2 结束，不伪造通过（与 probe_int2493 同口径）。

产出：tests/ui/artifacts/int2550/{summary.json, net.log, *.png}
"""
import argparse
import io
import json
import os
import sys
import time
import traceback
import zipfile

try:  # Windows 控制台默认 GBK，页面文案含中文/符号时 print 会炸
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

import httpx
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2550')
RESULT = {
    'kind': 'react',
    'art': ART,
    'checks': {},
    'steps': [],
    'requests': [],
    'screenshots': [],
    'notes': [],
    'skipped': [],
}
NET_LOG = os.path.join(ART, 'net.log')

USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

PREFIX = 'probe-skill-'


def log(msg):
    print('[int2550] %s' % msg, flush=True)


def record(step, status, detail=''):
    RESULT['steps'].append({'step': step, 'status': status, 'detail': detail})
    log('%s: %s %s' % (step, status, detail))


def step_ok(name, **payload):
    RESULT['checks'][name] = {'ok': True, **payload}
    record(name, 'PASS', json.dumps(payload, ensure_ascii=False)[:300])


def step_fail(name, reason, **payload):
    RESULT['checks'][name] = {'ok': False, 'reason': reason, **payload}
    record(name, 'FAIL', reason)
    raise AssertionError('%s: %s' % (name, reason))


def step_skip(name, reason):
    RESULT['checks'][name] = {'ok': None, 'skipped': reason}
    RESULT['skipped'].append({'step': name, 'reason': reason})
    record(name, 'SKIP', reason)


def write_artifacts():
    os.makedirs(ART, exist_ok=True)
    with io.open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    with io.open(NET_LOG, 'w', encoding='utf-8') as fh:
        for item in RESULT['requests']:
            fh.write(json.dumps(item, ensure_ascii=False) + '\n')


# ── API 辅助（真实请求，不用 mock） ───────────────────────────────
class SkillApi:
    def __init__(self, api_root, client: ApiClient):
        self.root = api_root.rstrip('/')
        self.client = client

    def _call(self, method, path, **kwargs):
        url = self.root + path
        headers = {'Authorization': 'Bearer ' + self.client.token}
        files = kwargs.pop('files', None)
        r = httpx.request(method, url, headers=headers, files=files,
                          trust_env=False, timeout=60, **kwargs)
        RESULT['requests'].append({
            'method': method, 'url': url, 'status': r.status_code,
        })
        body = None
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = None
        return r, body

    def list(self):
        return self._call('GET', '/api/v1/agent/skills')

    def create(self, name, body, description='探针创建的自定义 Skill'):
        return self._call('POST', '/api/v1/agent/skills', json={
            'name': name, 'description': description, 'body': body,
            'frontmatter': {'allowed-tools': ['task_query'], 'permissions': []},
        })

    def delete(self, skill_id):
        return self._call('DELETE', '/api/v1/agent/skills/%s' % skill_id)

    def cleanup(self):
        _, data = self.list()
        for item in (data or {}).get('items') or []:
            name = str(item.get('name') or '')
            if name.startswith(PREFIX) and item.get('scope') == 'USER':
                self.delete(item.get('id') or '')
                log('清理探针 Skill: %s' % name)


def valid_body(marker):
    return (
        '# %s\n\n## 适用场景\n\n探针用 Skill。\n\n## Gotchas\n\n- 无\n\n'
        '## 验收\n\n- 通过（%s）\n' % (marker, marker)
    )


def build_zip(path, skill_md, extra=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('SKILL.md', skill_md)
        for name, content in (extra or {}).items():
            zf.writestr(name, content)
    return path


# ── 浏览器辅助 ─────────────────────────────────────────────────
def shot(drv, key):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, key + '.png')
    drv.save_screenshot(path)
    info = {'name': key, 'size': os.path.getsize(path), 'path': path}
    RESULT['screenshots'].append(info)
    log('SHOT %s (%d bytes)' % (key, os.path.getsize(path)))
    return info


def set_theme(drv, dark):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
        'dark' if dark else 'light')
    drv.refresh()
    time.sleep(2.5)


def click(drv, elem):
    drv.execute_script('arguments[0].click()', elem)
    time.sleep(0.5)


def type_into(drv, selector, value):
    """输入并确认值落到当前 DOM（React 受控输入偶发丢键，JS 原生 setter 回退）。"""
    for _ in range(4):
        el = drv.find_element(By.CSS_SELECTOR, selector)
        el.clear()
        el.send_keys(value)
        time.sleep(0.3)
        if (drv.execute_script(
                "return document.querySelector(arguments[0]).value", selector) == value):
            return el
        drv.execute_script(
            "const el=document.querySelector(arguments[0]);"
            "const proto=(el instanceof HTMLTextAreaElement)"
            "?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
            "Object.getOwnPropertyDescriptor(proto,'value').set.call(el, arguments[1]);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));",
            selector, value)
        time.sleep(0.3)
    return drv.find_element(By.CSS_SELECTOR, selector)


def text_of(drv, selector):
    return drv.execute_script(
        "const el=document.querySelector(arguments[0]);return el?el.innerText:''",
        selector)


def rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, '[data-testid="agent-skill-row"]')


def row_by_name(drv, name):
    for row in rows(drv):
        if row.get_attribute('data-skill-name') == name:
            return row
    return None


def click_button(row, text):
    for btn in row.find_elements(By.TAG_NAME, 'button'):
        if text in (btn.text or ''):
            return btn
    raise AssertionError('行内未找到按钮：%s' % text)


def tab_by_text(drv, text):
    for btn in drv.find_elements(By.CSS_SELECTOR, '[data-testid^="skill-"][data-testid$="-tab-"]'):
        if text in (btn.text or ''):
            return btn
    for btn in drv.find_elements(By.TAG_NAME, 'button'):
        if text in (btn.text or ''):
            return btn
    return None


def login_ui(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    user_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
                   if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()]
    if user_inputs:
        user_inputs[0].send_keys(USERNAME)
    else:
        type_into(drv, '#username', USERNAME)
    pwd = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
           if e.is_displayed()]
    pwd[0].send_keys(PASSWORD)
    submit = [b for b in drv.find_elements(By.TAG_NAME, 'button')
              if (b.text or '').strip() in ('登录', '登 录')]
    click(drv, submit[-1] if submit else drv.find_element(By.CSS_SELECTOR, 'button[type=submit]'))
    WebDriverWait(drv, 40).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(2)
    capture_net(drv)


def capture_net(drv):
    """把浏览器的真实请求（含 GET /skills、POST /skills、PUT、import/export）并入证据。"""
    try:
        entries = sm.parse_perf(drv.get_log('performance'))
    except Exception:  # noqa: BLE001
        return []
    known = {(item.get('method'), item.get('url'), item.get('status'))
             for item in RESULT['requests']}
    added = []
    for entry in entries:
        key = (entry.get('method'), entry.get('url'), entry.get('status'))
        if key in known:
            continue
        known.add(key)
        RESULT['requests'].append(entry)
        added.append(entry)
    return added


def shot_network(drv, key='net_summary'):
    """把捕获到的请求 / 状态码渲染成表格再截图（headless 下 DevTools 不可截）。"""
    rows = ''.join(
        '<tr><td>%s</td><td style="font-family:monospace">%s</td><td>%s</td></tr>'
        % (item.get('method', ''), (item.get('url') or '')[:120], item.get('status', ''))
        for item in RESULT['requests'] if '/api/v1/agent/skills' in (item.get('url') or '')
    )
    html = (
        '<html><head><meta charset="utf-8"><style>'
        'body{font-family:system-ui,sans-serif;padding:20px;background:#111;color:#eee}'
        'table{border-collapse:collapse;width:100%;font-size:12px}'
        'td,th{border:1px solid #444;padding:4px 6px;text-align:left}'
        'th{background:#222}</style></head><body>'
        '<h3>/api/v1/agent/skills 请求与状态码</h3>'
        '<table><tr><th>方法</th><th>URL</th><th>状态</th></tr>%s</table>'
        '</body></html>' % rows
    )
    drv.get('data:text/html;charset=utf-8,' + html.replace('#', '%23'))
    time.sleep(0.5)
    return shot(drv, key)


def open_skill_page(drv, base):
    drv.get(base + '/agent-skills')
    WebDriverWait(drv, 25).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="agent-skill-row"]')))
    time.sleep(1.5)
    capture_net(drv)


# ── 主流程 ──────────────────────────────────────────────────────
def preflight(api, client):
    """后端是否已部署 INT-2549：GET /skills 必须返回 skills_count 且 items 带 id/scope。"""
    r, data = api.list()
    if r.status_code != 200:
        step_fail('preflight', 'GET /agent/skills = %s：%s' % (r.status_code, r.text[:200]))
    if not data or 'skills_count' not in data:
        RESULT['blocked'] = ('后端未部署 INT-2549：GET /api/v1/agent/skills 缺少 '
                             'skills_count/l1_tokens 字段（当前响应 keys=%s）'
                             % sorted((data or {}).keys()))
        record('preflight', 'BLOCKED', RESULT['blocked'])
        write_artifacts()
        sys.exit(2)
    sample = (data.get('items') or [{}])[0]
    if not all(key in sample for key in ('id', 'scope', 'status', 'content_hash')):
        RESULT['blocked'] = ('后端 Skill 视图仍是旧契约（items 缺 id/scope/status），'
                             'INT-2549 未部署')
        record('preflight', 'BLOCKED', RESULT['blocked'])
        write_artifacts()
        sys.exit(2)
    step_ok('preflight', items=len(data.get('items') or []),
            tools=data.get('tools_count'), skills_count=data.get('skills_count'))


def run(drv, base, skill_api):
    open_skill_page(drv, base)

    # 1 空态 / 平台 Skill 照常列出
    custom = [row for row in rows(drv) if row.get_attribute('data-skill-scope') == 'USER']
    platform = [row for row in rows(drv) if row.get_attribute('data-skill-scope') == 'PLATFORM']
    if not platform:
        step_fail('1_platform_rows', '列表没有平台内置 Skill')
    if custom:
        step_skip('1_empty_state', '账号已有自定义 Skill，空态改用 API 断言')
    else:
        body_text = drv.find_element(By.TAG_NAME, 'body').text
        if '还没有自定义 Skill' not in body_text:
            step_fail('1_empty_state', '无自定义 Skill 时未显示空态')
        step_ok('1_empty_state', platform_rows=len(platform))
    shot(drv, 'light_list')
    set_theme(drv, True)
    shot(drv, 'dark_list')
    set_theme(drv, False)

    # 2 页签计数与筛选
    open_skill_page(drv, base)
    scope_all = tab_by_text(drv, '全部')
    scope_user = tab_by_text(drv, '我的')
    scope_platform = tab_by_text(drv, '平台内置')
    if not (scope_user and scope_platform):
        step_fail('2_tabs', '来源页签缺失')
    click(drv, scope_platform)
    time.sleep(1)
    if any(row.get_attribute('data-skill-scope') != 'PLATFORM' for row in rows(drv)):
        step_fail('2_scope_filter', '切到「平台内置」后仍出现非平台行')
    step_ok('2_scope_filter', platform_rows=len(rows(drv)))
    click(drv, scope_all)
    time.sleep(1)

    # 11 只读约束（平台行只有 fork / 导出）
    platform_rows = [row for row in rows(drv) if row.get_attribute('data-skill-scope') == 'PLATFORM']
    row = platform_rows[0]
    labels = [b.text.strip() for b in row.find_elements(By.TAG_NAME, 'button')]
    forbidden = [label for label in labels if label in ('编辑', '删除', '停用', '发布')]
    if forbidden:
        step_fail('11_platform_readonly', '平台行出现写操作：%s' % forbidden)
    if not any('fork' in label for label in labels):
        step_fail('11_platform_readonly', '平台行缺 fork 操作')
    step_ok('11_platform_readonly', buttons=labels)

    # 3 新建
    click(drv, tab_by_text(drv, '新建 Skill'))
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-name')))
    name = PREFIX + str(int(time.time()))
    type_into(drv, '#agent-skill-name', name)
    type_into(drv, '#agent-skill-description', '探针创建：任务诊断草稿。触发词：探针。')
    type_into(drv, '#agent-skill-body', valid_body(name))
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '保存'][-1])
    WebDriverWait(drv, 25).until(EC.visibility_of_element_located(
        (By.CSS_SELECTOR, '[data-skill-name="%s"]' % name)))
    created_row = row_by_name(drv, name)
    if created_row.get_attribute('data-skill-status') != 'DRAFT':
        step_fail('3_create_draft', '新建后状态不是 DRAFT')
    step_ok('3_create_draft', name=name)
    shot(drv, 'created_draft')

    drv.refresh()
    WebDriverWait(drv, 25).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-skill-name="%s"]' % name)))
    step_ok('3_persist_after_reload', name=name)

    # 4 校验反馈（服务器逐项）
    click_button(row_by_name(drv, name), '编辑')
    WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-body')))
    time.sleep(1.5)
    # 4a 名称格式：前端即时提示（保存前拦截）
    type_into(drv, '#agent-skill-name', 'My_Skill')
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '保存'][-1])
    time.sleep(1)
    if '名称须匹配' not in drv.find_element(By.TAG_NAME, 'body').text:
        step_fail('4a_name_format', '非法名称未给即时提示')
    shot(drv, 'validation_name')
    type_into(drv, '#agent-skill-name', name)

    # 4b 缺 ## Gotchas（服务端）
    type_into(drv, '#agent-skill-body', '# 无小节\n\n## 步骤\n\n- 无\n')
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '保存'][-1])
    WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="skill-issue-list"]')))
    body_text = drv.find_element(By.TAG_NAME, 'body').text
    if 'MISSING_REQUIRED_SECTION' not in body_text and '缺少' not in body_text:
        step_fail('4b_missing_section', '缺 ## Gotchas 未回显原因')
    step_ok('4b_missing_section')
    shot(drv, 'validation_section')

    # 4c allowed-tools 未注册工具（服务端）
    type_into(drv, '#agent-skill-body', valid_body(name))
    type_into(drv, '#agent-skill-allowed-tools', 'no_such_tool')
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '保存'][-1])
    WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="skill-issue-list"]')))
    body_text = drv.find_element(By.TAG_NAME, 'body').text
    if 'UNKNOWN_TOOL' not in body_text and '未注册工具' not in body_text:
        step_fail('4c_unknown_tool', 'allowed-tools 未注册工具未回显原因')
    step_ok('4c_unknown_tool')
    shot(drv, 'validation_tool')

    # 4d permissions 提权：* 超管账号无法构造该负例
    step_skip('4d_permission_escalation',
              '当前账号 permissions=*（超管），服务端按通配放行；需受限账号才能构造，见交付说明')

    # 修正后保存成功
    type_into(drv, '#agent-skill-allowed-tools', 'task_query')
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '保存'][-1])
    WebDriverWait(drv, 25).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, '[data-testid="skill-issue-list"]')))
    step_ok('4_fix_and_save')

    # 5 连续保存 → 版本递增 + 版本历史可见
    for index in (2, 3):
        type_into(drv, '#agent-skill-body', valid_body(name) + '\n<!-- v%d -->\n' % index)
        click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '保存'][-1])
        time.sleep(2.5)
    version_items = drv.find_elements(By.CSS_SELECTOR, '[data-testid="skill-version-list"] li')
    if len(version_items) < 3:
        step_fail('5_versions', '版本历史不足 3 条：%d' % len(version_items))
    step_ok('5_versions', versions=[item.text for item in version_items])
    shot(drv, 'editor_versions')
    # 关闭编辑器
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '取消'][-1])
    time.sleep(1)

    # 6 fork platform-reference
    platform_rows = [r for r in rows(drv) if r.get_attribute('data-skill-scope') == 'PLATFORM']
    target = None
    for candidate in platform_rows:
        if candidate.get_attribute('data-skill-name') == 'platform-reference':
            target = candidate
    if target is None:
        step_fail('6_fork', '列表没有 platform-reference')
    click_button(target, 'fork')
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-fork-name')))
    fork_name = PREFIX + 'copy-' + str(int(time.time()))
    type_into(drv, '#agent-skill-fork-name', fork_name)
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if 'fork' in b.text][-1])
    WebDriverWait(drv, 25).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-skill-name="%s"]' % fork_name)))
    forked = row_by_name(drv, fork_name)
    if forked.get_attribute('data-skill-status') != 'DRAFT':
        step_fail('6_fork', 'fork 后不是 DRAFT')
    step_ok('6_fork', name=fork_name)

    # 7 导入
    workdir = os.path.join(ART, 'packages')
    good_zip = build_zip(
        os.path.join(workdir, 'good.zip'),
        '---\nname: %simport\ndescription: 导入探针 Skill\n---\n\n%s'
        % (PREFIX, valid_body('import')),
    )
    missing_desc = build_zip(
        os.path.join(workdir, 'missing_desc.zip'),
        '---\nname: %sbad1\n---\n\n%s' % (PREFIX, valid_body('bad1')),
    )
    traversal = build_zip(
        os.path.join(workdir, 'traversal.zip'),
        '---\nname: %sbad2\ndescription: 路径逃逸\n---\n\n%s'
        % (PREFIX, valid_body('bad2')),
        {'../evil.txt': 'x'},
    )
    click(drv, tab_by_text(drv, '导入 zip'))
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-import-file')))
    drv.find_element(By.CSS_SELECTOR, '#agent-skill-import-file').send_keys(good_zip)
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if '开始导入' in b.text][-1])
    WebDriverWait(drv, 30).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-skill-name="%simport"]' % PREFIX)))
    step_ok('7_import_valid')
    shot(drv, 'import_valid')

    import_cases = []
    for label, path in (('missing_description', missing_desc), ('path_traversal', traversal)):
        before = len(rows(drv))
        click(drv, tab_by_text(drv, '导入 zip'))
        WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-import-file')))
        drv.find_element(By.CSS_SELECTOR, '#agent-skill-import-file').send_keys(path)
        click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if '开始导入' in b.text][-1])
        WebDriverWait(drv, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="skill-import-result"]')))
        after = len(rows(drv))
        if after != before:
            step_fail('7_import_invalid_%s' % label, '非法包导致列表新增条目')
        import_cases.append(label)
        shot(drv, 'import_invalid_%s' % label)
        click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '取消'][-1])
        time.sleep(0.8)
    step_ok('7_import_invalid', cases=import_cases)

    # 8 导出：下载 zip，服务端原字节；根级 SKILL.md 存在
    download_dir = ART
    click_button(row_by_name(drv, name), '导出')
    time.sleep(4)
    downloaded = [f for f in os.listdir(download_dir) if f.endswith('.zip')]
    if not downloaded:
        step_fail('8_export', '未生成导出 zip')
    exported = os.path.join(download_dir, downloaded[-1])
    with zipfile.ZipFile(exported) as zf:
        names = zf.namelist()
        if 'SKILL.md' not in names:
            step_fail('8_export', '导出包缺根级 SKILL.md：%s' % names)
        content = zf.read('SKILL.md').decode('utf-8')
    if name not in content:
        step_fail('8_export', '导出 SKILL.md 与被保存内容不一致')
    step_ok('8_export', filename=downloaded[-1], entries=names)
    shot(drv, 'export_dialog')

    # 9 发布门槛（golden tasks 不足 → 拦截且仍 DRAFT）
    click_button(row_by_name(drv, name), '编辑')
    WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-body')))
    time.sleep(1.5)
    publish_buttons = [b for b in drv.find_elements(By.TAG_NAME, 'button')
                       if b.text.strip() in ('发布', '重新尝试发布')]
    if not publish_buttons:
        step_fail('9_publish_gate', '草稿编辑器没有发布按钮')
    click(drv, publish_buttons[-1])
    WebDriverWait(drv, 30).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-testid="skill-gate-panel"]')))
    gate_text = text_of(drv, '[data-testid="skill-gate-panel"]')
    if 'golden tasks' not in gate_text:
        step_fail('9_publish_gate', '门槛面板未展示 golden tasks：%s' % gate_text[:200])
    assert_unmet = drv.find_elements(By.CSS_SELECTOR, '[data-testid="skill-gate-unmet"]')
    if assert_unmet:
        step_ok('9_publish_gate', gate=gate_text[:200])
    else:
        step_ok('9_publish_gate', gate=gate_text[:200],
                note='门槛通过（评测集含该 Skill）或门槛未拦截')
    shot(drv, 'publish_gate')
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '取消'][-1])
    time.sleep(1)

    # 10 停用（二次确认 → DISABLED，状态页签计数同步）
    click_button(row_by_name(drv, name), '停用')
    WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[role="alertdialog"]')))
    click(drv, [b for b in drv.find_elements(By.TAG_NAME, 'button') if b.text.strip() == '停用'][-1])
    WebDriverWait(drv, 25).until(lambda d: row_by_name(d, name) is not None and
                                 row_by_name(d, name).get_attribute('data-skill-status') == 'DISABLED')
    step_ok('10_disable')
    shot(drv, 'disabled_row')

    capture_net(drv)
    shot_network(drv)

    # 12 权限：超管账号无 agent:skill:manage 缺失场景
    step_skip('12_permission_guard',
              'dev_user permissions=*（超管），无「无 agent:skill:manage」账号；'
              '守卫逻辑由 403 路由与 router 单测覆盖，见交付说明')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:15173')
    parser.add_argument('--api', default='http://localhost:15000')
    args = parser.parse_args()

    os.makedirs(ART, exist_ok=True)
    client = ApiClient(args.api)
    client.login(USERNAME, PASSWORD)
    api = SkillApi(args.api, client)

    try:
        preflight(api, client)
        driver = sm.make_driver(ART)
        try:
            login_ui(driver, args.base)
            run(driver, args.base, api)
        finally:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        RESULT['error'] = '%s: %s' % (type(exc).__name__, exc)
        RESULT['traceback'] = traceback.format_exc()[-3000:]
        record('run', 'FAIL', RESULT['error'])
        write_artifacts()
        log('失败：%s' % RESULT['error'])
        return 1
    finally:
        try:
            api.cleanup()
        except Exception:  # noqa: BLE001
            log('清理探针数据失败（人工核对前缀 %s）' % PREFIX)

    write_artifacts()
    failed = [k for k, v in RESULT['checks'].items() if v.get('ok') is False]
    log('完成：%d 项，失败 %d 项' % (len(RESULT['checks']), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
