# -*- coding: utf-8 -*-
"""INT-2606 验收探针：Skill 编辑器保存不丢 frontmatter 非表单键（version 等）。

缺陷：编辑器保存只回传 allowed-tools / permissions（+budgets / owner），服务端
`update()` 对 frontmatter 整体替换 → 导出包里 `version` 等键一次保存即丢。

本探针按卡面复现路径实测（docker 真栈，本 run dev server 指向 15000 网关）：
  1 API 建 Skill（frontmatter 带 version/owner/budgets/自定义键）→ 导出取基线键集
  2 UI 打开该 Skill 的编辑器 → 不改内容点「保存」
  3 再次导出：frontmatter 键集合不变、version / 自定义键值不变
  4 fork platform-reference → UI 保存 → 导出仍带 version / owner / budgets

跑法：
  python tests/ui/probe_int2606_skill_frontmatter.py \
      --base http://localhost:5306 --api http://localhost:15000
账号默认 dev_user / dev_password（可用 UI_TEST_USERNAME / UI_TEST_PASSWORD 覆盖）。
产出：tests/ui/artifacts/int2606/{summary.json, net.log, *.png}
"""
import argparse
import io
import json
import os
import sys
import time
import traceback
import zipfile

try:  # Windows 控制台默认 GBK，页面文案含中文时 print 会炸
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

import httpx
import yaml
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(os.path.dirname(sm.ART_ROOT), 'int2606')
RESULT = {
    'kind': 'react',
    'art': ART,
    'checks': {},
    'steps': [],
    'requests': [],
    'screenshots': [],
    'notes': [],
}
NET_LOG = os.path.join(ART, 'net.log')

USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

PROBE_NAME = 'probe-skill-int2606'
FORK_SOURCE = 'platform:platform-reference'
FORK_NAME = 'platform-reference-copy'
CREATED_IDS = []


def log(msg):
    print('[int2606] %s' % msg, flush=True)


def record(step, status, detail=''):
    RESULT['steps'].append({'step': step, 'status': status, 'detail': detail})
    log('%s: %s %s' % (step, status, detail))


def step_ok(check, **payload):
    RESULT['checks'][check] = {'ok': True, **payload}
    record(check, 'PASS', json.dumps(payload, ensure_ascii=False, default=str)[:400])


def step_fail(check, reason, **payload):
    RESULT['checks'][check] = {'ok': False, 'reason': reason, **payload}
    record(check, 'FAIL', reason)
    raise AssertionError('%s: %s' % (check, reason))


def write_artifacts():
    os.makedirs(ART, exist_ok=True)
    with io.open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2, default=str)
    with io.open(NET_LOG, 'w', encoding='utf-8') as fh:
        for item in RESULT['requests']:
            fh.write(json.dumps(item, ensure_ascii=False) + '\n')


# ── API ────────────────────────────────────────────────────────
class SkillApi:
    def __init__(self, api_root, client):
        self.root = api_root.rstrip('/')
        self.client = client

    def _call(self, method, path, **kwargs):
        url = self.root + path
        headers = {'Authorization': 'Bearer ' + self.client.token}
        r = httpx.request(method, url, headers=headers, trust_env=False,
                          timeout=60, **kwargs)
        RESULT['requests'].append({'method': method, 'url': url,
                                   'status': r.status_code})
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = None
        return r, body

    def create(self, name, frontmatter, description='INT-2606 探针 Skill'):
        body = ('# %s\n\n## 适用场景\n\nINT-2606 frontmatter 透传探针。\n\n'
                '## Gotchas\n\n- 无\n\n## 验收\n\n- 保存后 version 仍在\n'
                % name)
        return self._call('POST', '/api/v1/agent/skills', json={
            'name': name, 'description': description, 'body': body,
            'frontmatter': frontmatter,
        })

    def fork(self, skill_id, name=None):
        payload = {'name': name} if name else {}
        return self._call('POST', '/api/v1/agent/skills/%s/fork' % skill_id,
                          json=payload)

    def export_frontmatter(self, skill_id):
        url = self.root + '/api/v1/agent/skills/%s/export' % skill_id
        headers = {'Authorization': 'Bearer ' + self.client.token}
        r = httpx.get(url, headers=headers, trust_env=False, timeout=60)
        RESULT['requests'].append({'method': 'GET', 'url': url,
                                   'status': r.status_code})
        if r.status_code != 200:
            step_fail('export', 'GET export = %s：%s'
                      % (r.status_code, r.text[:200]))
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            raw = zf.read('SKILL.md').decode('utf-8')
        fm_text, body = sm_split(raw)
        data = yaml.safe_load(fm_text) or {}
        return data, body, fm_text

    def delete(self, skill_id):
        return self._call('DELETE', '/api/v1/agent/skills/%s' % skill_id)

    def find_user_skill(self, name):
        _, data = self._call('GET', '/api/v1/agent/skills')
        for item in (data or {}).get('items') or []:
            if item.get('name') == name and item.get('scope') == 'USER':
                return item
        return None


def sm_split(raw):
    lines = raw.replace('\r\n', '\n').split('\n')
    if not lines or lines[0].strip() != '---':
        return '', raw
    for index in range(1, len(lines)):
        if lines[index].strip() == '---':
            return '\n'.join(lines[1:index]), '\n'.join(lines[index + 1:]).lstrip('\n')
    return '', raw


# ── 浏览器 ─────────────────────────────────────────────────────
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


def wait_or_shot(drv, condition, key, timeout=25):
    try:
        return WebDriverWait(drv, timeout).until(condition)
    except Exception:  # noqa: BLE001
        shot(drv, 'fail_%s' % key)
        RESULT['notes'].append({
            'step': key,
            'body': drv.find_element(By.TAG_NAME, 'body').text[:1500],
        })
        raise


def rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, '[data-testid="agent-skill-row"]')


def row_by_name(drv, name):
    for row in rows(drv):
        try:
            if row.get_attribute('data-skill-name') == name:
                return row
        except StaleElementReferenceException:
            continue
    return None


def login_ui(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    user_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
                   if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()]
    if user_inputs:
        user_inputs[0].send_keys(USERNAME)
    pwd = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
           if e.is_displayed()]
    pwd[0].send_keys(PASSWORD)
    submit = [b for b in drv.find_elements(By.TAG_NAME, 'button')
              if (b.text or '').strip() in ('登录', '登 录')]
    click(drv, submit[-1] if submit else drv.find_element(By.CSS_SELECTOR, 'button[type=submit]'))
    WebDriverWait(drv, 40).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(2)


def open_skill_page(drv, base):
    drv.get(base + '/agent-skills')
    WebDriverWait(drv, 25).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="agent-skill-row"]')))
    time.sleep(1.5)


def open_editor(drv, name, timeout=40):
    """点行内「编辑」并等正文载入（导出包异步读取，空 textarea 时保存会丢正文）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = row_by_name(drv, name)
        if row is not None:
            try:
                for btn in row.find_elements(By.TAG_NAME, 'button'):
                    if '编辑' in (btn.text or ''):
                        click(drv, btn)
                        break
            except Exception:  # noqa: BLE001  行被重渲染 → 重取
                pass
        try:
            WebDriverWait(drv, 5).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, '#agent-skill-body')))
            WebDriverWait(drv, 30).until(
                lambda d: d.execute_script(
                    "const el=document.querySelector('#agent-skill-body');"
                    "return !!el && el.value.trim().length > 0"))
            time.sleep(0.8)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    wait_or_shot(drv, EC.presence_of_element_located(
        (By.CSS_SELECTOR, '#agent-skill-body')), 'open_editor', timeout=1)


def save_and_wait(drv):
    buttons = [b for b in drv.find_elements(By.TAG_NAME, 'button')
               if (b.text or '').strip() == '保存' and b.is_enabled()]
    if not buttons:
        step_fail('save', '保存按钮不可用（文档未载入或正在提交）')
    click(drv, buttons[-1])
    try:
        WebDriverWait(drv, 40).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="skill-editor-saved"]')))
    except Exception:  # noqa: BLE001
        shot(drv, 'fail_save')
        body = drv.find_element(By.TAG_NAME, 'body').text[:1500]
        step_fail('save', '保存后未出现成功提示：%s' % body)
    time.sleep(1)


def close_editor(drv):
    buttons = [b for b in drv.find_elements(By.TAG_NAME, 'button')
               if (b.text or '').strip() == '取消']
    if buttons:
        click(drv, buttons[-1])
    time.sleep(1)


def capture_net(drv):
    try:
        entries = sm.parse_perf(drv.get_log('performance'))
    except Exception:  # noqa: BLE001
        return []
    known = {(item.get('method'), item.get('url')) for item in RESULT['requests']}
    added = []
    for entry in entries:
        key = (entry.get('method'), entry.get('url'))
        if key in known:
            continue
        known.add(key)
        RESULT['requests'].append(entry)
        added.append(entry)
    return added


def shot_network(drv, key='net_summary'):
    rows_html = ''.join(
        '<tr><td>%s</td><td style="font-family:monospace">%s</td><td>%s</td></tr>'
        % (item.get('method', ''), (item.get('url') or '')[:130], item.get('status', ''))
        for item in RESULT['requests'] if '/api/v1/agent/skills' in (item.get('url') or '')
    )
    html = (
        '<html><head><meta charset="utf-8"><style>'
        'body{font-family:system-ui,sans-serif;padding:20px;background:#111;color:#eee}'
        'table{border-collapse:collapse;width:100%;font-size:12px}'
        'td,th{border:1px solid #444;padding:4px 6px;text-align:left}'
        'th{background:#222}</style></head><body>'
        '<h3>/api/v1/agent/skills 请求与状态码（INT-2606）</h3>'
        '<table><tr><th>方法</th><th>URL</th><th>状态</th></tr>' + rows_html +
        '</table></body></html>'
    )
    drv.get('data:text/html;charset=utf-8,' + html.replace('#', '%23'))
    time.sleep(0.5)
    return shot(drv, key)


# ── 主流程 ─────────────────────────────────────────────────────
def run(drv, base, api):
    # 1 API 建 Skill：frontmatter 带非表单键
    frontmatter = {
        'allowed-tools': ['task_query'],
        'permissions': [],
        'version': '9.9.9',
        'owner': 'agent-platform',
        'budgets': {'maxToolCalls': 20, 'maxTokens': 30000},
        'probe-keep': {'nested': True, 'note': 'INT-2606'},
    }
    r, data = api.create(PROBE_NAME, frontmatter)
    if r.status_code not in (200, 201):
        step_fail('1_create', 'POST /agent/skills = %s：%s'
                  % (r.status_code, r.text[:300]))
    skill_id = (data or {}).get('id', '')
    if not skill_id:
        step_fail('1_create', 'POST 响应缺 id：%s' % str(data)[:200])
    CREATED_IDS.append(skill_id)

    before, _, _ = api.export_frontmatter(skill_id)
    if str(before.get('version')) != '9.9.9':
        step_fail('2_export_before', '基线导出缺 version：%s' % sorted(before))
    step_ok('2_export_before', keys=sorted(before), version=before.get('version'),
            keys_count=len(before))

    # 2 UI 打开编辑器 → 不改内容保存
    open_skill_page(drv, base)
    if row_by_name(drv, PROBE_NAME) is None:
        step_fail('3_row_visible', '列表里找不到刚建的 Skill：%s' % PROBE_NAME)
    open_editor(drv, PROBE_NAME)
    body_value = drv.execute_script(
        "return document.querySelector('#agent-skill-body').value")
    if '## Gotchas' not in body_value:
        step_fail('3_editor_body', '编辑器正文未载入导出包内容：%r' % body_value[:120])
    shot(drv, 'editor_light')
    set_theme(drv, True)
    open_skill_page(drv, base)
    open_editor(drv, PROBE_NAME)
    shot(drv, 'editor_dark')
    set_theme(drv, False)
    open_skill_page(drv, base)
    open_editor(drv, PROBE_NAME)
    save_and_wait(drv)
    shot(drv, 'editor_saved')
    capture_net(drv)

    # 3 再次导出：键集合与值不变
    after, _, after_text = api.export_frontmatter(skill_id)
    missing = sorted(set(before) - set(after))
    extra = sorted(set(after) - set(before))
    if missing:
        step_fail('4_keep_keys', '保存后丢失 frontmatter 键：%s\nBEFORE=%s\nAFTER=%s'
                  % (missing, sorted(before), sorted(after)))
    if extra:
        step_fail('4_keep_keys', '保存后多出 frontmatter 键：%s' % extra)
    if str(after.get('version')) != '9.9.9':
        step_fail('5_version_value', 'version 丢失或变化：%s' % after.get('version'))
    if after.get('probe-keep') != {'nested': True, 'note': 'INT-2606'}:
        step_fail('5_custom_key', '自定义键被改写：%s' % after.get('probe-keep'))
    if after.get('owner') != 'agent-platform':
        step_fail('5_owner', 'owner 被改写：%s' % after.get('owner'))
    step_ok('4_keep_keys', keys=sorted(after), keys_count=len(after),
            version=after.get('version'), owner=after.get('owner'),
            custom=after.get('probe-keep'), frontmatter_text=after_text[:400])

    close_editor(drv)

    # 4 fork 平台 Skill → 保存 → 导出仍带 version / owner / budgets
    r, fork_data = api.fork(FORK_SOURCE)
    if r.status_code not in (200, 201):
        step_fail('6_fork', 'POST fork platform-reference = %s：%s'
                  % (r.status_code, r.text[:300]))
    fork_id = (fork_data or {}).get('id', '')
    fork_name = (fork_data or {}).get('name', '')
    if not fork_id or not fork_name:
        step_fail('6_fork', 'fork 响应缺 id/name：%s' % str(fork_data)[:200])
    CREATED_IDS.append(fork_id)
    fork_before, _, _ = api.export_frontmatter(fork_id)
    open_skill_page(drv, base)
    if row_by_name(drv, fork_name) is None:
        step_fail('6_fork_row', 'fork 后列表找不到 %s' % fork_name)
    open_editor(drv, fork_name)
    shot(drv, 'fork_editor_light')
    save_and_wait(drv)
    fork_after, _, _ = api.export_frontmatter(fork_id)
    lost = sorted(set(fork_before) - set(fork_after))
    if lost:
        step_fail('7_fork_keep', 'fork 后保存丢失键：%s（BEFORE=%s）'
                  % (lost, sorted(fork_before)))
    if str(fork_after.get('version')) != str(fork_before.get('version')):
        step_fail('7_fork_version', 'fork 保存后 version 变化：%r → %r'
                  % (fork_before.get('version'), fork_after.get('version')))
    step_ok('7_fork_keep', name=fork_name, keys=sorted(fork_after),
            version=fork_after.get('version'), owner=fork_after.get('owner'),
            budgets=fork_after.get('budgets'))
    close_editor(drv)
    shot_network(drv)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:5306')
    parser.add_argument('--api', default='http://localhost:15000')
    args = parser.parse_args()

    os.makedirs(ART, exist_ok=True)
    client = ApiClient(args.api)
    client.login(USERNAME, PASSWORD)
    api = SkillApi(args.api, client)

    try:
        sm.env_check('start')
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
        for skill_id in CREATED_IDS:
            try:
                api.delete(skill_id)
                log('清理探针 Skill: %s' % skill_id)
            except Exception:  # noqa: BLE001
                log('清理失败（人工核对 id=%s）' % skill_id)

    write_artifacts()
    failed = [k for k, v in RESULT['checks'].items() if v.get('ok') is False]
    log('完成：%d 项，失败 %d 项' % (len(RESULT['checks']), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
