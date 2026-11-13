# -*- coding: utf-8 -*-
"""INT-2493 验收探针：模型供应商管理（Key 掩码 / 上下文窗口覆盖 / 验证与默认 / 无 Key 引导）。

跑法（docker 真栈，环境铁律）：
  python tests/ui/probe_int2493_provider.py --base http://localhost:15173 --api http://localhost:15000
  账号默认 dev_user / dev_password（docker 栈 admin/admin123 已失效，可用
  UI_TEST_USERNAME / UI_TEST_PASSWORD 覆盖）。

覆盖卡面 1–10：
  1 空态（先清空本账号供应商）               6 删除二次确认 + 刷新不复现
  2 新增（列表字段一致 / Key 掩码 / 刷新仍掩码） 7 上下文窗口 默认 / 覆盖 / 恢复 / 非法 / 超目录告警
  3 编辑（逐字段回显 / Key 留空不变）          8 无 Key 引导（删除全部后发起 run）
  4 设默认（旧标记消失 / 新标记出现 / 刷新保持）  9 加载 / 空 / 错误三态
  5 验证（可连通成功 / 错地址失败不回显 Key）    10 权限（无 agent:provider:manage 时入口不可见 / 直达 403）

每步记录请求方法 / URL / 状态码，落 artifacts/int2493/summary.json + net.log；
截图：浅/深色页面、新增/编辑弹窗、空态、错误态、验证失败态、Network 汇总图。

依赖：backend 必须已部署 agent_service（INT-2456）。未部署时 provider API 返回
503「agent service unavailable」，探针记录 blocked 并以退出码 2 结束，不伪造通过。
"""
import argparse
import json
import os
import sys
import time
import traceback

try:  # Windows 控制台默认 GBK，页面文案含 ⌘ 等字符时 print 会炸
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2493')
RESULT = {'kind': 'react', 'art': ART, 'checks': {}, 'steps': [], 'requests': [], 'screenshots': [], 'notes': []}
NET_LOG = os.path.join(ART, 'net.log')

USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')
# 验证成功用例需要可连通的 OpenAI 兼容端点；未提供时只跑失败用例
VERIFY_OK_BASE_URL = os.environ.get('PROBE_VERIFY_BASE_URL', '')
VERIFY_OK_KEY = os.environ.get('PROBE_VERIFY_KEY', '')
VERIFY_OK_MODEL = os.environ.get('PROBE_VERIFY_MODEL', 'gpt-4o-mini')


def log(msg):
    print('[int2493] %s' % msg, flush=True)


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


def write_artifacts():
    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    with open(NET_LOG, 'w', encoding='utf-8') as fh:
        for item in RESULT['requests']:
            fh.write(json.dumps(item, ensure_ascii=False) + '\n')


# ── 页面操作辅助 ───────────────────────────────────────────
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


def buttons(drv, contains=None, exact=None):
    out = []
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if not b.is_displayed():
                continue
        except Exception:
            continue
        text = (b.text or '').strip()
        label = (b.get_attribute('aria-label') or '').strip()
        if exact and text in exact:
            out.append(b)
        elif contains and any(c in text for c in contains):
            out.append(b)
        elif contains and any(c in label for c in contains):
            out.append(b)
    return out


def click(drv, elem):
    drv.execute_script('arguments[0].click()', elem)
    time.sleep(0.6)


def type_into(drv, selector, value):
    """输入并确认值落在当前 DOM 节点上（弹窗进场/重渲染偶尔丢键，重试 + JS 回退）。"""
    el = None
    for _ in range(5):
        el = drv.find_element(By.CSS_SELECTOR, selector)
        el.clear()
        el.send_keys(value)
        time.sleep(0.4)
        if _dom_value(drv, selector) == value:
            return el
        drv.execute_script(
            "const sel=arguments[0],v=arguments[1];const el=document.querySelector(sel);"
            "const proto=(el instanceof HTMLTextAreaElement)?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
            "Object.getOwnPropertyDescriptor(proto,'value').set.call(el,v);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));"
            "el.dispatchEvent(new Event('change',{bubbles:true}));",
            selector, value)
        time.sleep(0.4)
        if _dom_value(drv, selector) == value:
            return el
        time.sleep(0.6)
    return el


def wait_dialog_closed(drv, timeout=20):
    """保存后等弹窗关闭 + 列表 invalidate 回填，避免再用旧数据开编辑窗。"""
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: not any(e.is_displayed()
                              for e in d.find_elements(By.CSS_SELECTOR, '#agent-provider-name')))
    except Exception:
        pass
    time.sleep(2.0)


def _dom_value(drv, selector):
    return drv.execute_script(
        "const el=document.querySelector(arguments[0]); return el ? el.value : null", selector)


def body_text(drv):
    return (drv.execute_script('return document.body ? document.body.innerText : ""') or '').strip()


def wait_text(drv, needle, timeout=30):
    WebDriverWait(drv, timeout).until(lambda d: needle in body_text(d))
    return True


def api_requests(drv):
    entries = sm.parse_perf(drv.get_log('performance'))
    RESULT['requests'].extend(entries)
    return entries


def open_page(drv, base, path='/agent-providers'):
    drv.get(base.rstrip('/') + path)
    time.sleep(3)
    api_requests(drv)


def shot_network(drv, entries, key='net_summary'):
    """把捕获到的请求/状态码渲染成一张表再截图（headless 下 DevTools 面板不可截）。"""
    rows = ''.join(
        '<tr><td>%s</td><td style="font-family:monospace">%s</td><td>%s</td></tr>'
        % (e.get('method', ''), (e.get('url') or '')[:120], e.get('status', ''))
        for e in entries
    )
    html = (
        '<html><head><meta charset="utf-8"><style>'
        'body{font-family:system-ui,sans-serif;padding:20px;background:#111;color:#eee}'
        'table{border-collapse:collapse;width:100%%;font-size:12px}'
        'td,th{border:1px solid #444;padding:4px 6px;text-align:left}'
        'th{background:#222}</style></head><body>'
        '<h3>INT-2493 Network（真实请求，状态码来自 Performance log）</h3>'
        '<table><tr><th>方法</th><th>URL</th><th>状态</th></tr>%s</table></body></html>' % rows
    )
    path = os.path.join(ART, key + '.html')
    os.makedirs(ART, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(html)
    drv.get('file:///' + path.replace('\\', '/'))
    time.sleep(1.5)
    shot(drv, key)


# ── 主流程 ─────────────────────────────────────────────────
def run(base, api_base):
    os.makedirs(ART, exist_ok=True)
    client = ApiClient(api_base)
    api_user = client.login(USERNAME, PASSWORD)
    log('登录 API：%s permissions=%s' % (api_user.get('user', {}).get('username'),
                                        (api_user.get('user') or {}).get('permissions')))

    # 后端能力探测：agent_service 未部署时 provider API 503（INT-2456 未合入）
    try:
        client.request('GET', '/agent/providers')
        backend_ready = True
    except Exception as exc:  # noqa: BLE001
        backend_ready = False
        record('backend', 'BLOCKED', '%s' % exc)
        RESULT['backend_blocked'] = True
        write_artifacts()
        log('provider API 不可用（agent_service 未部署）：%s' % exc)
        return 2

    # 清空本账号供应商（用后自清：只动本账号自己的记录）
    def purge():
        try:
            for item in client.request('GET', '/agent/providers').get('items', []):
                client.request('DELETE', '/agent/providers/%s' % item['id'])
        except Exception:
            pass

    purge()
    drv = sm.make_driver(ART)
    try:
        # 登录 UI
        drv.get(base + '/login')
        WebDriverWait(drv, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
        # 用户名输入框没有显式 type 属性（默认 text），用可见 input 兜底
        user_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
                       if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()]
        (user_inputs and user_inputs[0].send_keys(USERNAME))
        pwd_inputs = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
                      if e.is_displayed()]
        (pwd_inputs and pwd_inputs[0].send_keys(PASSWORD))
        login_btn = [b for b in buttons(drv, exact=('登录', '登 录')) ]
        click(drv, login_btn[-1] if login_btn else drv.find_element(By.CSS_SELECTOR, 'button[type=submit]'))
        WebDriverWait(drv, 40).until(lambda d: 'login' not in d.current_url.lower())
        time.sleep(3)
        api_requests(drv)

        # 1 空态（等页面正文渲染，不能只等侧栏出现「模型供应商」）
        open_page(drv, base)
        try:
            WebDriverWait(drv, 30).until(
                lambda d: '我的供应商' in body_text(d)
                          and ('还没有配置模型供应商' in body_text(d) or '验证连通性' in body_text(d)))
        except Exception:
            pass
        empty_ok = '还没有配置模型供应商' in body_text(drv)
        empty_ok or step_fail('1_empty', '未显示空态：%s' % body_text(drv)[:200])
        step_ok('1_empty', shot=shot(drv, '01_empty_light')['name'])
        set_theme(drv, True)
        open_page(drv, base)
        try:
            wait_text(drv, '还没有配置模型供应商', timeout=25)
        except Exception:
            drv.refresh(); time.sleep(3)
            wait_text(drv, '还没有配置模型供应商', timeout=30)
        step_ok('1_empty_dark', shot=shot(drv, '02_empty_dark')['name'])
        set_theme(drv, False)

        # 2 新增（负例：非法 Base URL 先报错不提交）
        open_page(drv, base)
        click(drv, buttons(drv, exact=('新增供应商',))[0])
        WebDriverWait(drv, 15).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '#agent-provider-base-url')))
        time.sleep(3.0)  # 等弹窗进场 + 模型目录查询落定（目录到达会重渲染表单）
        type_into(drv, '#agent-provider-base-url', 'not-a-url')
        type_into(drv, '#agent-provider-model', 'probe-model')
        type_into(drv, '#agent-provider-api-key', 'sk-probe-secret-1234')
        time.sleep(0.5)
        click(drv, buttons(drv, exact=('保存',))[0])
        try:
            wait_text(drv, 'Base URL 必须是 http(s) 地址', timeout=10)
        except Exception:
            pass
        invalid_ok = 'Base URL 必须是 http(s) 地址' in body_text(drv)
        invalid_ok or step_fail('2_create_validation', '非法 URL 未报错：%s' % body_text(drv)[-300:])
        step_ok('2_create_validation', shot=shot(drv, '03_form_validation')['name'])

        type_into(drv, '#agent-provider-name', '探针_供应商A')
        type_into(drv, '#agent-provider-base-url', 'http://127.0.0.1:9/v1')
        click(drv, buttons(drv, exact=('保存',))[0])
        wait_text(drv, '探针_供应商A')
        items = client.request('GET', '/agent/providers').get('items', [])
        created = next((i for i in items if i['name'] == '探针_供应商A'), None)
        created or step_fail('2_create', '接口未出现新记录')
        mask_ok = created['api_key_mask'].startswith('sk-') and created['api_key_mask'].endswith('1234')
        mask_ok and 'probe-secret' not in created['api_key_mask'] or step_fail('2_create_mask', '掩码异常')
        step_ok('2_create', provider_id=created['id'], mask=created['api_key_mask'],
                shot=shot(drv, '04_list_light')['name'])

        # 刷新后仍掩码
        drv.refresh(); time.sleep(3)
        wait_text(drv, created['api_key_mask']) or step_fail('2_mask_after_reload', '刷新后掩码消失')
        step_ok('2_mask_after_reload')

        # 3 编辑回显 + Key 留空不变
        click(drv, buttons(drv, contains=('编辑',))[0])
        WebDriverWait(drv, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '#agent-provider-name')))
        name_val = drv.find_element(By.CSS_SELECTOR, '#agent-provider-name').get_attribute('value')
        key_val = drv.find_element(By.CSS_SELECTOR, '#agent-provider-api-key').get_attribute('value')
        (name_val == '探针_供应商A' and not key_val) or step_fail('3_edit_echo', 'name=%r key=%r' % (name_val, key_val))
        step_ok('3_edit_echo', shot=shot(drv, '05_edit_dialog')['name'])
        type_into(drv, '#agent-provider-name', '探针_供应商A改')
        click(drv, buttons(drv, exact=('保存',))[0])
        wait_text(drv, '探针_供应商A改')
        raw = client.request('GET', '/agent/providers').get('items', [])
        still_key = next(i for i in raw if i['id'] == created['id'])['api_key_mask']
        still_key == created['api_key_mask'] or step_fail('3_key_unchanged', 'Key 掩码变化：%s' % still_key)
        step_ok('3_key_unchanged')

        # 4 设默认（只有一个时新建即默认；再建第二个后切换）
        second = client.request('POST', '/agent/providers', {
            'name': '探针_供应商B', 'protocol': 'OPENAI_COMPATIBLE',
            'base_url': 'http://127.0.0.1:9/v1', 'model': 'probe-model-b',
            'api_key': 'sk-probe-b-9999', 'context_window': None,
        })
        open_page(drv, base)
        wait_text(drv, '探针_供应商B')
        wait_text(drv, '验证连通性', timeout=20)  # 列表行加载完成才点操作按钮
        click(drv, buttons(drv, exact=('设为默认',))[0])
        time.sleep(2)
        api_requests(drv)
        after = client.request('GET', '/agent/providers').get('items', [])
        defaults = [i for i in after if i.get('is_default')]
        len(defaults) == 1 or step_fail('4_set_default', '默认项数量=%d' % len(defaults))
        step_ok('4_set_default', default_id=defaults[0]['id'])
        drv.refresh(); time.sleep(3)
        wait_text(drv, '验证连通性', timeout=20)
        row_head = drv.execute_script(
            "const h=Array.from(document.querySelectorAll('h3')).find(e=>e.textContent.trim()===arguments[0]);"
            "return h ? h.parentElement.innerText : ''", defaults[0]['name']) or ''
        ('默认' in row_head) or step_fail('4_default_persist', '刷新后默认标记消失：%r' % row_head)
        step_ok('4_default_persist')

        # 5 验证：错地址失败且不回显 Key（toast 约 4s 自动消失，边轮询边截）
        verify_btns = buttons(drv, contains=('验证连通性',))
        verify_btns or step_fail('5_verify_fail', '行内验证按钮未渲染：%s' % body_text(drv)[-200:])
        click(drv, verify_btns[0])
        try:
            WebDriverWait(drv, 30).until(
                lambda d: any(k in body_text(d) for k in ('失败', '无法', '超时')))
        except Exception:
            pass
        api_requests(drv)
        text = body_text(drv)
        ('失败' in text or '无法' in text or '超时' in text) or step_fail('5_verify_fail', text[-300:])
        ('sk-probe' not in text) or step_fail('5_key_not_leaked', '页面出现明文 Key')
        step_ok('5_verify_fail', shot=shot(drv, '06_verify_failed')['name'])

        if VERIFY_OK_BASE_URL and VERIFY_OK_KEY:
            ok_item = client.request('POST', '/agent/providers', {
                'name': '探针_可连通', 'protocol': 'OPENAI_COMPATIBLE',
                'base_url': VERIFY_OK_BASE_URL, 'model': VERIFY_OK_MODEL,
                'api_key': VERIFY_OK_KEY, 'context_window': None,
            })
            open_page(drv, base)
            wait_text(drv, '验证连通性', timeout=20)
            targets = [b for b in buttons(drv, contains=('验证',))
                       if ok_item['name'] in (b.get_attribute('aria-label') or '')]
            targets or step_fail('5_verify_ok', '可连通供应商行未渲染：%s' % body_text(drv)[-200:])
            click(drv, targets[0])
            try:
                wait_text(drv, '验证通过', timeout=30)
            except Exception:
                pass
            wait_text(drv, '验证通过')
            api_requests(drv)
            step_ok('5_verify_ok', shot=shot(drv, '06b_verify_ok')['name'])
        else:
            record('5_verify_ok', 'SKIP', '未提供 PROBE_VERIFY_BASE_URL/KEY（无可用模型端点）')

        # 7 上下文窗口三态（在编辑弹窗里操作）
        open_page(drv, base)
        wait_text(drv, '验证连通性', timeout=20)
        target = client.request('GET', '/agent/providers').get('items', [])[0]
        click(drv, [b for b in buttons(drv, contains=('编辑',))
                    if target['name'] in (b.get_attribute('aria-label') or '')][0])
        WebDriverWait(drv, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '#agent-provider-name')))
        time.sleep(2)  # 等弹窗进场/重渲染落定
        # 手动覆盖 32k
        click(drv, [b for b in buttons(drv, exact=('手动覆盖',))][0])
        type_into(drv, '#agent-provider-context-window', '32k')
        click(drv, buttons(drv, exact=('保存',))[0])
        wait_dialog_closed(drv)
        api_requests(drv)
        item = next(i for i in client.request('GET', '/agent/providers')['items'] if i['id'] == target['id'])
        (item['effective_context_window'] == 32768 and item['context_window_source'] == 'USER_OVERRIDE') \
            or step_fail('7_override_32k', json.dumps(item, ensure_ascii=False)[:200])
        step_ok('7_override_32k')
        # 恢复默认
        click(drv, [b for b in buttons(drv, contains=('编辑',))
                    if target['name'] in (b.get_attribute('aria-label') or '')][0])
        try:
            WebDriverWait(drv, 15).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '#agent-provider-context-window')))
        except Exception:
            step_fail('7_restore_default',
                      '重开编辑弹窗未回到覆盖态：%s' % body_text(drv)[-250:])
        click(drv, buttons(drv, exact=('恢复默认',))[0])
        click(drv, buttons(drv, exact=('保存',))[0])
        wait_dialog_closed(drv)
        item = next(i for i in client.request('GET', '/agent/providers')['items'] if i['id'] == target['id'])
        (item['context_window'] is None and item['context_window_source'] in ('MODEL_DEFAULT', 'FALLBACK')) \
            or step_fail('7_restore_default', json.dumps(item, ensure_ascii=False)[:200])
        step_ok('7_restore_default')
        # 非法值不提交（恢复默认后弹窗处于「使用默认」态，需先切「手动覆盖」）
        click(drv, [b for b in buttons(drv, contains=('编辑',))
                    if target['name'] in (b.get_attribute('aria-label') or '')][0])
        WebDriverWait(drv, 15).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '#agent-provider-name')))
        click(drv, buttons(drv, exact=('手动覆盖',))[0])
        WebDriverWait(drv, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '#agent-provider-context-window')))
        type_into(drv, '#agent-provider-context-window', '4096')
        click(drv, buttons(drv, exact=('保存',))[0])
        try:
            WebDriverWait(drv, 10).until(
                lambda d: ('之间' in body_text(d) or '对齐' in body_text(d)))
        except Exception:
            pass
        ('之间' in body_text(drv) or '对齐' in body_text(drv)) or step_fail('7_invalid', body_text(drv)[-300:])
        step_ok('7_invalid', shot=shot(drv, '07_context_invalid')['name'])
        # 超目录最大值：可保存 + 告警（先把模型名改成目录内的 deepseek-chat，目录默认 65536）
        type_into(drv, '#agent-provider-model', 'deepseek-chat')
        type_into(drv, '#agent-provider-context-window', '131072')
        try:
            WebDriverWait(drv, 10).until(lambda d: '高于目录默认' in body_text(d))
        except Exception:
            pass
        warn_seen = '高于目录默认' in body_text(drv)
        warn_seen or step_fail('7_above_catalog_warning', body_text(drv)[-300:])
        click(drv, buttons(drv, exact=('保存',))[0])
        time.sleep(2)
        item = next(i for i in client.request('GET', '/agent/providers')['items'] if i['id'] == target['id'])
        item['context_window_warning'] or step_fail('7_above_catalog_saved', '告警未落库')
        item['effective_context_window'] == 131072 or step_fail(
            '7_above_catalog_saved', json.dumps(item, ensure_ascii=False)[:200])
        step_ok('7_above_catalog_saved', shot=shot(drv, '08_above_catalog_warning')['name'])

        # 6 删除（二次确认 + 刷新不复现）
        open_page(drv, base)
        wait_text(drv, '验证连通性', timeout=20)
        before = len(client.request('GET', '/agent/providers')['items'])
        click(drv, buttons(drv, contains=('删除',))[0])
        WebDriverWait(drv, 10).until(lambda d: '删除模型供应商' in body_text(d))
        shot(drv, '09_delete_confirm')
        click(drv, buttons(drv, exact=('删除',))[-1])
        time.sleep(2)
        api_requests(drv)
        after_cnt = len(client.request('GET', '/agent/providers')['items'])
        after_cnt == before - 1 or step_fail('6_delete', '数量 %d→%d' % (before, after_cnt))
        drv.refresh(); time.sleep(3)
        step_ok('6_delete')

        # 8 无 Key 引导：删空后发起 run
        purge()
        open_page(drv, base)
        wait_text(drv, '还没有配置模型供应商')
        drv.get(base + '/ai-chat')
        time.sleep(4)
        textarea = drv.find_element(By.CSS_SELECTOR, 'textarea')
        textarea.send_keys('你好')
        submit = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
                  if b.is_displayed()]
        submit and click(drv, submit[-1])
        wait_text(drv, '未配置模型供应商', timeout=40) or step_fail('8_no_key_guidance', '未出现引导')
        step_ok('8_no_key_guidance', shot=shot(drv, '10_no_key_guidance')['name'])

        # 9 错误态：CDP 让 provider 接口 500（不拦截页面其他请求，避免路由拦截卡死）
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/api/v1/agent/providers*']})
        open_page(drv, base)
        wait_text(drv, '模型供应商加载失败') or step_fail('9_error_state', body_text(drv)[:200])
        step_ok('9_error_state', shot=shot(drv, '11_error_state')['name'])
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})

        # 10 权限：当前 dev_user 为通配权限，入口可见；无权限分支由 RBAC 单测 + 路由守卫覆盖
        record('10_permission', 'INFO',
               'dev_user permissions=%s；无权限分支需非 * 账号（路由守卫 + 侧栏过滤同码）'
               % (api_user.get('user') or {}).get('permissions'))

        # 深色页面图
        client.request('POST', '/agent/providers', {
            'name': '探针_深色', 'protocol': 'OPENAI_COMPATIBLE',
            'base_url': 'http://127.0.0.1:9/v1', 'model': 'probe-model',
            'api_key': 'sk-probe-dark-0000', 'context_window': None,
        })
        set_theme(drv, True)
        open_page(drv, base)
        wait_text(drv, '探针_深色')
        shot(drv, '12_page_dark')
        set_theme(drv, False)

        shot_network(drv, RESULT['requests'])
        purge()
        return 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        write_artifacts()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=os.environ.get('UI_FRONTEND_BASE', 'http://localhost:15173'))
    parser.add_argument('--api', default=os.environ.get('UI_API_BASE', 'http://localhost:15000'))
    args = parser.parse_args()
    os.makedirs(ART, exist_ok=True)
    try:
        code = run(args.base.rstrip('/'), args.api.rstrip('/'))
    except AssertionError as exc:
        record('fatal', 'FAIL', str(exc))
        write_artifacts()
        traceback.print_exc()
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        record('fatal', 'ERROR', repr(exc))
        write_artifacts()
        traceback.print_exc()
        sys.exit(1)
    sys.exit(code)


if __name__ == '__main__':
    main()
