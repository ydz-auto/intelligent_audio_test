# -*- coding: utf-8 -*-
"""INT-2550 打回修复补验探针（P2-2 文档错误态重试 / P2-1 对话沉淀建议入口）。

两个阶段，按环境分别跑：

① retry（真实 docker 栈，前端 dev server 直连 15000）：
   python tests/ui/probe_int2550_skill_fixes.py --phase retry \
       --base http://localhost:5351 --api http://localhost:15000
   - 自建 USER Skill → CDP 屏蔽 export 请求 → 打开编辑器出现「读取 SKILL.md 失败」
   - 点「重新加载」→ 断言 export 请求数 +1（旧实现是死按钮，请求数不变）
   - 解屏蔽再点一次 → 正文载入；保存 → 断言「保存成功」成功态提示（不再说未保存）

② suggestion（SSE 桩；其余请求仍走真栈）：
   python tests/ui/utils/skill_suggestion_stub.py --port 18791
   # dev server: API_PROXY_TARGET=http://127.0.0.1:18791 pnpm dev --port 5352
   python tests/ui/probe_int2550_skill_fixes.py --phase suggestion \
       --base http://localhost:5352 --api http://localhost:15000
   - /ai-chat 发一条消息 → 桩下发 skill_draft_suggested → 气泡出现建议卡
   - 卡片主按钮直达 /agent-skills?name=&description=，编辑器打开且已预填
   - 浅色 / 深色各一张

产物：tests/ui/artifacts/int2550_fixes/{summary.json, *.png}
"""
import argparse
import io
import json
import os
import sys
import time
import traceback

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui.utils.api_client import ApiClient  # noqa: E402
from tests.ui.utils.skill_suggestion_stub import (  # noqa: E402
    SUGGESTED_DESCRIPTION,
    SUGGESTED_NAME,
)

ART = os.path.join(os.path.dirname(sm.ART_ROOT), 'int2550_fixes')
RESULT = {'checks': {}, 'steps': [], 'screenshots': [], 'requests': [],
          'notes': [], 'phase': ''}
USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')
PREFIX = 'probe-fix-'


def log(msg):
    print('[int2550-fix] %s' % msg, flush=True)


def record(step, status, detail=''):
    RESULT['steps'].append({'step': step, 'status': status, 'detail': detail})
    log('%s: %s %s' % (step, status, detail))


def ok(check, **payload):
    RESULT['checks'][check] = {'ok': True, **payload}
    record(check, 'PASS', json.dumps(payload, ensure_ascii=False)[:300])


def fail(check, reason, **payload):
    RESULT['checks'][check] = {'ok': False, 'reason': reason, **payload}
    record(check, 'FAIL', reason)
    raise AssertionError('%s: %s' % (check, reason))


def shot(drv, key):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, key + '.png')
    drv.save_screenshot(path)
    RESULT['screenshots'].append({'name': key, 'path': path,
                                  'size': os.path.getsize(path)})
    log('SHOT %s (%d bytes)' % (key, os.path.getsize(path)))


def set_theme(drv, dark):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);",
        'dark' if dark else 'light')
    drv.refresh()
    time.sleep(2.5)


def click(drv, elem):
    drv.execute_script('arguments[0].click()', elem)
    time.sleep(0.4)


def type_into(drv, selector, value):
    """React 受控输入偶发丢键：原生 setter + input 事件兜底。"""
    el = drv.find_element(By.CSS_SELECTOR, selector)
    el.click()
    el.send_keys(value)
    time.sleep(0.3)
    current = drv.execute_script(
        "return document.querySelector(arguments[0]).value", selector)
    if current != value:
        drv.execute_script(
            "const el=document.querySelector(arguments[0]);"
            "const proto=(el instanceof HTMLTextAreaElement)"
            "?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
            "Object.getOwnPropertyDescriptor(proto,'value').set.call(el,arguments[1]);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));",
            selector, value)
    return el


def body_text(drv):
    return drv.execute_script(
        'return document.body ? document.body.innerText : ""') or ''


def wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))
    return True


def request_log(drv):
    out = []
    try:
        raw = drv.get_log('performance')
    except Exception:  # noqa: BLE001
        return out
    for entry in raw:
        try:
            inner = json.loads(entry.get('message', '{}')).get('message', {})
            if inner.get('method') != 'Network.requestWillBeSent':
                continue
            req = inner.get('params', {}).get('request', {})
            out.append({'method': req.get('method'), 'url': req.get('url')})
        except Exception:  # noqa: BLE001
            continue
    return out


def count_export_calls(drv):
    """页面内 fetch 计数（被 CDP 屏蔽的请求不会再走 NetWork.requestWillBeSent）。"""
    return drv.execute_script(
        'return (window.__skillExportCalls || []).length')


def install_export_counter(drv):
    drv.execute_script(
        "window.__skillExportCalls = [];"
        "const __f = window.fetch;"
        "window.fetch = function(input, init) {"
        "  try { const u = (typeof input === 'string' ? input : (input && input.url)) || '';"
        "        if (u.indexOf('/export') >= 0) window.__skillExportCalls.push(u); }"
        "  catch (e) {}"
        "  return __f.apply(this, arguments);"
        "};")


def count_requests(drv, needle):
    return len([r for r in request_log(drv)
                if needle in (r.get('url') or '')])


def login_ui(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    user_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
                   if e.get_attribute('type') in (None, 'text', 'email')
                   and e.is_displayed()]
    (user_inputs[0] if user_inputs else
     drv.find_element(By.CSS_SELECTOR, '#username')).send_keys(USERNAME)
    pwd = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
           if e.is_displayed()]
    pwd[0].send_keys(PASSWORD)
    submit = [b for b in drv.find_elements(By.TAG_NAME, 'button')
              if (b.text or '').strip() in ('登录', '登 录')]
    click(drv, submit[-1] if submit else
          drv.find_element(By.CSS_SELECTOR, 'button[type=submit]'))
    WebDriverWait(drv, 40).until(lambda d: 'login' not in d.current_url.lower())
    time.sleep(2)


def write_artifacts():
    os.makedirs(ART, exist_ok=True)
    with io.open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)


# ── Skill API 准备（自建自清） ──────────────────────────────────
class SkillApi:
    def __init__(self, root, client: ApiClient):
        self.root = root.rstrip('/')
        self.client = client

    def _h(self):
        return {'Authorization': 'Bearer ' + self.client.token}

    def create(self, name):
        import httpx
        body = {
            'name': name,
            'description': 'INT-2550 打回修复探针（文档重试 / 保存成功态）',
            'body': '## 适用场景\n\n探针。\n\n## Gotchas\n\n-\n\n## 验收\n\n- 通过\n',
            'frontmatter': {'allowed-tools': [], 'permissions': []},
        }
        r = httpx.post(self.root + '/api/v1/agent/skills', json=body,
                       headers=self._h(), trust_env=False, timeout=30)
        if r.status_code not in (200, 201):
            raise RuntimeError('create skill %s: %s %s'
                               % (r.status_code, r.text[:300], name))
        return r.json()

    def delete(self, skill_id):
        import httpx
        if not skill_id:
            return
        httpx.request('DELETE', self.root + '/api/v1/agent/skills/' + skill_id,
                      headers=self._h(), trust_env=False, timeout=30)

    def list_own(self):
        import httpx
        r = httpx.get(self.root + '/api/v1/agent/skills', headers=self._h(),
                      trust_env=False, timeout=30)
        r.raise_for_status()
        return r.json().get('items') or []


# ── 阶段 ①：文档错误态重试 ─────────────────────────────────────
def phase_retry(drv, base, api: SkillApi, client: ApiClient):
    name = PREFIX + 'retry-' + str(int(time.time()))
    skill = api.create(name)
    sid = skill['id']
    record('prepare', 'PASS', 'skill=%s id=%s' % (name, sid))

    drv.execute_cdp_cmd('Network.enable', {})
    drv.get(base + '/agent-skills')
    wait_text(drv, name, 40)
    time.sleep(1.5)

    drv.execute_cdp_cmd('Network.setBlockedURLs',
                        {'urls': ['*/agent/skills/*/export*']})
    install_export_counter(drv)
    row = drv.find_element(By.CSS_SELECTOR,
                           '[data-skill-name="%s"]' % name)
    edit = [b for b in row.find_elements(By.TAG_NAME, 'button')
            if (b.text or '').strip() == '编辑']
    if not edit:
        fail('doc_retry', '行内没有「编辑」按钮')
    click(drv, edit[0])

    wait_text(drv, '读取 SKILL.md 失败', 30)
    time.sleep(1.0)
    shot(drv, 'doc_error_blocked')
    before = count_export_calls(drv)
    if before < 1:
        fail('doc_retry', '屏蔽后没有观察到 export 请求')
    ok('doc_error_state', export_requests=before)

    click(drv, drv.find_element(By.CSS_SELECTOR,
                                '[data-testid="skill-doc-retry"]'))
    time.sleep(3.0)
    after = count_export_calls(drv)
    if after <= before:
        fail('doc_retry', '点「重新加载」后 export 请求数没有增加：%d → %d'
             % (before, after))
    if '读取 SKILL.md 失败' not in body_text(drv):
        fail('doc_retry', '仍被屏蔽却离开了错误态（判据异常）')
    ok('doc_retry_refetch', before=before, after=after)

    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    click(drv, drv.find_element(By.CSS_SELECTOR,
                                '[data-testid="skill-doc-retry"]'))
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-body')))
    WebDriverWait(drv, 20).until(
        lambda d: '## Gotchas' in d.find_element(
            By.CSS_SELECTOR, '#agent-skill-body').get_attribute('value'))
    shot(drv, 'doc_error_recovered')
    ok('doc_retry_recovered', body_has_gotchas=True)

    # P3-2：保存成功只剩成功态提示（不再说「未保存」）
    type_into(drv, '#agent-skill-body',
              '## 适用场景\n\n探针（已更新）。\n\n## Gotchas\n\n-\n\n## 验收\n\n- 通过\n')
    save = [b for b in drv.find_elements(By.TAG_NAME, 'button')
            if (b.text or '').strip() == '保存']
    if not save:
        fail('save_success_hint', '编辑器没有「保存」按钮')
    click(drv, save[-1])
    WebDriverWait(drv, 30).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-testid="skill-editor-saved"]')))
    hint = drv.find_element(By.CSS_SELECTOR,
                            '[data-testid="skill-editor-saved"]').text
    if '保存成功' not in hint:
        fail('save_success_hint', '成功态提示文案不符：%s' % hint)
    if '未保存' in body_text(drv):
        fail('save_success_hint', '保存成功后页面仍出现「未保存」')
    drv.execute_script(
        "document.querySelector('[data-testid=\"skill-editor-saved\"]')"
        ".scrollIntoView({block: 'center'})")
    time.sleep(0.6)
    shot(drv, 'save_success_state')
    ok('save_success_hint', text=hint)

    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    time.sleep(0.5)
    api.delete(sid)
    check_clean(api)
    RESULT['net'] = request_log(drv)[-40:]


def check_clean(api):
    left = [s for s in api.list_own()
            if (s.get('name') or '').startswith(PREFIX)
            or (s.get('name') or '').startswith('probe-skill-')]
    if left:
        fail('cleanup', '探针残留数据：%s' % [s.get('name') for s in left])
    ok('cleanup', remaining=0)


# ── 阶段 ②：对话沉淀建议卡 ──────────────────────────────────────
def send_message(drv):
    """在 /ai-chat 发一条消息，等建议卡出现（桩按 run 下发 skill_draft_suggested）。"""
    WebDriverWait(drv, 40).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'textarea')))
    time.sleep(1.5)
    # React 受控输入：send_keys 偶发不落 state，原生 setter + input 事件兜底
    type_into(drv, 'textarea', '帮我把导出报告的流程沉淀成 Skill')
    time.sleep(0.6)
    submits = [b for b in drv.find_elements(By.CSS_SELECTOR,
                                            'button[type=submit]')
               if b.is_displayed()]
    if not submits:
        fail('suggestion_card', '/ai-chat 没有可用的发送按钮')
    click(drv, submits[-1])
    WebDriverWait(drv, 40).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-testid="skill-suggestion-card"]')))
    return drv.find_element(By.CSS_SELECTOR,
                            '[data-testid="skill-suggestion-card"]')


def phase_suggestion(drv, base, api: SkillApi):
    drv.get(base + '/ai-chat')
    card = send_message(drv)
    suggested = card.get_attribute('data-suggested-name')
    card_text = card.text
    if suggested != SUGGESTED_NAME:
        fail('suggestion_card', '建议名称不符：%s' % suggested)
    for needle in ('沉淀为 Skill', SUGGESTED_NAME, '不自动落库'):
        if needle not in card_text:
            fail('suggestion_card', '建议卡缺少文案「%s」：%s' % (needle, card_text))
    ok('suggestion_card', suggested_name=suggested,
       text=card_text.replace('\n', ' | ')[:300])
    shot(drv, 'suggestion_card_light')

    # 深色：切主题会刷新页面（本地会话持久化），重新发一条即可复现同一张卡
    set_theme(drv, True)
    drv.get(base + '/ai-chat')
    send_message(drv)
    shot(drv, 'suggestion_card_dark')

    # 主按钮直达 /agent-skills 并预填（深色下点，随后回浅色复核同页）
    WebDriverWait(drv, 40).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[data-testid="skill-suggestion-create"]')))
    click(drv, drv.find_element(By.CSS_SELECTOR,
                                '[data-testid="skill-suggestion-create"]'))
    WebDriverWait(drv, 40).until(
        lambda d: '/agent-skills' in d.current_url)
    WebDriverWait(drv, 40).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-name')))
    name_value = drv.find_element(By.CSS_SELECTOR,
                                  '#agent-skill-name').get_attribute('value')
    desc_value = drv.find_element(By.CSS_SELECTOR,
                                  '#agent-skill-description').get_attribute('value')
    if name_value != SUGGESTED_NAME:
        fail('suggestion_prefill', '编辑器名称未预填：%r' % name_value)
    if desc_value != SUGGESTED_DESCRIPTION:
        fail('suggestion_prefill', '编辑器描述未预填：%r' % desc_value)
    ok('suggestion_prefill', name=name_value, description=desc_value,
       url=drv.current_url)

    # 浅色同页复核（query 仍带预填参数，刷新后编辑器自动打开并预填）
    set_theme(drv, False)
    WebDriverWait(drv, 40).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '#agent-skill-name')))
    shot(drv, 'suggestion_prefill')

    # 不自动建草稿：列表里不应出现该建议名
    api_items = api.list_own()
    if any((s.get('name') or '') == SUGGESTED_NAME for s in api_items):
        fail('suggestion_no_autocreate', '建议名已自动落库（不应自动创建）')
    ok('suggestion_no_autocreate')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['retry', 'suggestion'],
                        required=True)
    parser.add_argument('--base', default='http://localhost:5351')
    parser.add_argument('--api', default='http://localhost:15000')
    args = parser.parse_args()
    RESULT['phase'] = args.phase
    RESULT['base'] = args.base
    # 两个阶段各自一个产物目录（summary.json 不互相覆盖）
    global ART
    ART = os.path.join(ART, args.phase)

    os.makedirs(ART, exist_ok=True)
    client = ApiClient(args.api)
    client.login(USERNAME, PASSWORD)
    api = SkillApi(args.api, client)

    driver = sm.make_driver(ART)
    try:
        login_ui(driver, args.base)
        if args.phase == 'retry':
            phase_retry(driver, args.base, api, client)
        else:
            phase_suggestion(driver, args.base, api)
    except Exception as exc:  # noqa: BLE001
        RESULT['error'] = '%s: %s' % (type(exc).__name__, exc)
        RESULT['traceback'] = traceback.format_exc()[-3000:]
        record('run', 'FAIL', RESULT['error'])
        write_artifacts()
        log('失败：%s' % RESULT['error'])
        return 1
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            for item in api.list_own():
                if (item.get('name') or '').startswith(PREFIX):
                    api.delete(item.get('id'))
        except Exception:  # noqa: BLE001
            log('清理探针数据失败（人工核对前缀 %s）' % PREFIX)

    write_artifacts()
    failed = [k for k, v in RESULT['checks'].items() if v.get('ok') is False]
    log('完成：%d 项，失败 %d 项' % (len(RESULT['checks']), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
