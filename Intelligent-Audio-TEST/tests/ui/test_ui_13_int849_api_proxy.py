# -*- coding: utf-8 -*-
"""INT-849 UI 实测：API 编辑弹窗代理配置（类型下拉 + 地址输入 + 校验）可达性。

卡面验收 #1/#2/#4：打开 API 编辑弹窗 → 应能看到「代理类型」下拉
（http/https/socks5/socks5h + 不使用代理）+「代理地址」输入；校验规则与
后端一致；代理为空时行为与改动前一致。

本用例走真实 UI 流程（/APITest 资源卡片「编辑」→ API 编辑弹窗），只读/
写造数据自建自清：API 造一个测试 API → 浏览器点编辑 → 断言弹窗内出现代理
字段。若实际打开的编辑弹窗（CRUDFormModal）不含代理字段，则验收 #1 不满足。
"""
import time

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.utils.api_client import unique_suffix

APITEST_ROUTE = '/APITest'
MODAL_TITLE = '.modal-title'
CARD_EDIT_BTN_XPATH = (
    './/div[contains(@class,"card-actions")]//button[contains(@title,"编辑")]'
)
FORM_LABELS = '.crud-form-modal .form-label, .crud-form-modal label'
FORM_SELECTS = '.crud-form-modal select'
FORM_INPUTS = '.crud-form-modal input'


@pytest.fixture()
def int849_api(api_client) -> dict:
    """API 造一个测试 API（无代理，仅触发列表卡片）。返回 {id, name, cleanup}。"""
    suffix = unique_suffix()
    name = f'ui849_api_{suffix}'
    data = api_client.request('POST', '/apis', {
        'name': name,
        'vendor': 'volc_ast',
        'api_url': 'http://127.0.0.1:1',
        'default_max_process': 5,
        'default_max_timeout': 30,
        'default_max_audio_duration': 60,
        'meta': {'protocol': 'http', 'environment': 'testing', 'version': 'v1'},
        'endpoints': [{'endpoint': 'http://127.0.0.1:1/health', 'name': 'default',
                       'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60,
                       'priority': 1}],
    })
    item = (data or {}).get('data') or {}
    api_id = item.get('id')
    assert api_id, f'API 造数据失败: {str(data)[:300]}'
    yield {'id': api_id, 'name': name}
    try:
        api_client.request('DELETE', f'/apis/{api_id}')
    except Exception:
        pass


def _open_api_edit_modal(page, api_name: str):
    """导航 /APITest → 找到目标 API 卡片 → 点编辑 → 等弹窗。"""
    page.goto(APITEST_ROUTE)
    page.settle(1.0)
    wait = WebDriverWait(page.driver, 20)
    # 目标卡片（名称匹配）
    card = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, f'//div[contains(@class,"resource-card")]'
                       f'[.//div[contains(@class,"card-name")][contains(text(),"{api_name}")]]')))
    edit_btn = card.find_element(By.XPATH, CARD_EDIT_BTN_XPATH)
    page.driver.execute_script('arguments[0].scrollIntoView({block:"center"});', edit_btn)
    page.settle(0.3)
    page.driver.execute_script('arguments[0].click();', edit_btn)
    # 等编辑弹窗出现
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, MODAL_TITLE)))
    page.settle(0.6)
    return card


def test_int849_proxy_fields_in_real_api_edit_modal(page, int849_api):
    """验收 #1/#2：真实 API 编辑弹窗必须包含代理类型下拉 + 代理地址输入。"""
    _open_api_edit_modal(page, int849_api['name'])

    labels = [e.text.strip() for e in page.find_all(FORM_LABELS)]
    body_text = page.find('.crud-form-modal').text

    select_texts = []
    for sel in page.find_all(FORM_SELECTS):
        opts = [o.text.strip() for o in sel.find_elements(By.TAG_NAME, 'option')]
        select_texts.append((sel.get_attribute('id'), opts))

    page.capture_artifacts(page.node_artifact_dir('int849_proxy_reach'))

    # 断言：代理类型下拉（含 http/https/socks5/socks5h）+ 代理地址输入
    assert any('代理' in t for t in labels), (
        f'实际 API 编辑弹窗缺少代理字段标签。labels={labels}')
    # 注意：API 元数据另有「协议」select（http/https/ws/wss），须按
    # socks5/socks5h 或 id 含 proxyType 精确定位代理类型下拉。
    proxy_select = [s for s in page.find_all(FORM_SELECTS)
                    if 'proxyType' in s.get_attribute('id') or
                    any(o in ('socks5', 'socks5h')
                        for o in [o.get_attribute('value') or o.text
                                  for o in s.find_elements(By.TAG_NAME, 'option')])]
    assert proxy_select, f'未找到代理类型下拉。selects={select_texts} body={body_text[:300]}'
    opts = [o.get_attribute('value') for o in proxy_select[0].find_elements(By.TAG_NAME, 'option')]
    assert set(opts) >= {'http', 'https', 'socks5', 'socks5h'}, f'代理类型选项缺失: {opts}'
    # 代理地址输入（placeholder 为 ASCII user:pass@host:port）
    proxy_input = [i for i in page.find_all(FORM_INPUTS)
                   if 'user:pass@' in (i.get_attribute('placeholder') or '')]
    assert proxy_input, f'未找到代理地址输入框。body={body_text[:400]}'


def test_int849_apieditmodal_component_direct(page):
    """组件本身（直接经 modal registry 打开 APIEditModal）必须渲染代理字段 + 校验。

    说明：APIEditModal（MODAL_TYPES.API_OTHER_CONFIG='apiEdit'）在真实编辑流程
    中无打开入口（见上一用例），此用例经 window 全局 modal manager 直接 open，
    只验证组件自身渲染与保存载荷契约（与交付截图口径一致）。
    """
    page.goto(APITEST_ROUTE)
    page.settle(0.8)
    page.driver.execute_script(
        "window.__ui849_payload = null;"
        "window.__modal_manager_instance__.open('apiEdit', {"
        "  data: { name: 'D', proxyType: 'socks5', proxyUrl: 'user:pass@10.0.0.1:1080' }"
        "}).then(d => { window.__ui849_payload = d; });")
    page.settle(1.0)

    select = page.find('.api-edit-modal select')
    opts = [o.get_attribute('value') for o in select.find_elements(By.TAG_NAME, 'option')]
    assert set(opts) >= {'', 'http', 'https', 'socks5', 'socks5h'}, f'下拉选项缺失: {opts}'
    assert select.get_attribute('value') == 'socks5', '回显 proxyType=socks5 失败'
    url_input = page.find('.api-edit-modal input[placeholder="user:pass@host:port"]')
    assert url_input.get_attribute('value') == 'user:pass@10.0.0.1:1080', '回显 proxyUrl 失败'

    # 校验：类型非空 + 地址缺 user:pass@ → 保存被阻止
    page.driver.execute_script(
        "var i = document.querySelector('.api-edit-modal input[placeholder=\"user:pass@host:port\"]');"
        "i.value = '10.0.0.1:8080'; i.dispatchEvent(new Event('input', {bubbles:true}));")
    page.settle(0.2)
    page.click('.api-edit-modal .btn-primary')
    page.settle(0.4)
    assert page.driver.execute_script('return window.__ui849_payload === null'), \
        '非法代理地址（缺 user:pass@）不应触发保存'

    # 合法保存：载荷携带 camelCase proxyType / proxyUrl
    page.driver.execute_script(
        "var i = document.querySelector('.api-edit-modal input[placeholder=\"user:pass@host:port\"]');"
        "i.value = 'user:pass@10.0.0.1:1080'; i.dispatchEvent(new Event('input', {bubbles:true}));")
    page.settle(0.2)
    page.click('.api-edit-modal .btn-primary')
    page.settle(0.5)
    payload = page.driver.execute_script('return window.__ui849_payload')
    assert payload, '合法代理保存未产生载荷'
    assert payload.get('proxyType') == 'socks5' and payload.get('proxyUrl') == 'user:pass@10.0.0.1:1080', \
        f'保存载荷代理字段错误: {payload}'

    page.capture_artifacts(page.node_artifact_dir('int849_apiedit_direct'))


def test_int849_real_modal_save_persists_proxy(page, api_client, int849_api):
    """验收 #2/#3：真实编辑弹窗填代理 → 保存 → PUT 载荷携带 snake_case
    proxy_type/proxy_url（地址 trim）→ 回读一致。

    通过 fetch 钩子捕获真实请求体（前端 infrastructure/client.ts 用 fetch），
    断言载荷为 snake_case 且地址 trim；随后经 API 客户端回读确认落库一致。
    """
    api_id = int849_api['id']
    # 注入 fetch 钩子：记录对 /apis/{id} 的 PUT 请求体
    page.goto(APITEST_ROUTE)
    page.settle(0.8)
    page.driver.execute_script('''
      window.__int849_put_bodies = [];
      const origFetch = window.fetch.bind(window);
      window.fetch = function(url, opts) {
        try {
          if (opts && opts.method === 'PUT' && String(url).indexOf('/apis/') !== -1) {
            let body = opts.body;
            if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) {} }
            window.__int849_put_bodies.push({url: String(url), body});
          }
        } catch (e) {}
        return origFetch(url, opts);
      };
    ''')
    page.settle(0.3)
    _open_api_edit_modal(page, int849_api['name'])

    # 填代理：类型 socks5 + 地址（带前后空格，验证 trim）
    page.driver.execute_script(
        "var s = document.getElementById('field-proxyType');"
        "s.value = 'socks5'; s.dispatchEvent(new Event('change', {bubbles:true}));")
    page.driver.execute_script(
        "var i = document.getElementById('field-proxyUrl');"
        "i.value = '  user:pass@10.0.0.1:1080  '; i.dispatchEvent(new Event('input', {bubbles:true}));")
    page.settle(0.3)
    page.capture_artifacts(page.node_artifact_dir('int849_real_modal_filled'))
    page.click('.crud-form-modal .btn-primary')
    page.settle(1.5)

    # 断言 PUT 载荷携带 snake_case proxy_type/proxy_url（trim 后）
    bodies = page.driver.execute_script('return window.__int849_put_bodies;') or []
    assert bodies, f'未捕获到 PUT /apis/{{id}} 请求体。bodies={bodies}'
    last = bodies[-1]
    body = last.get('body') or {}
    assert body.get('proxy_type') == 'socks5', f'PUT 载荷 proxy_type 错误: {body}'
    assert body.get('proxy_url') == 'user:pass@10.0.0.1:1080', \
        f'PUT 载荷 proxy_url 未 trim: {body.get("proxy_url")!r}'

    # 回读一致（验收 #3）
    r = api_client.request('GET', f'/apis/{api_id}')
    data = r.get('data') or {}
    assert data.get('proxy_type') == 'socks5', f'回读 proxy_type 不一致: {data}'
    assert data.get('proxy_url') == 'user:pass@10.0.0.1:1080', f'回读 proxy_url 不一致: {data}'

    page.capture_artifacts(page.node_artifact_dir('int849_real_modal_saved'))


def test_int849_real_modal_validation_blocks_save(page, api_client, int849_api):
    """验收 #1 校验规则（与后端一致）：真实编辑弹窗三条非法路径均阻止保存。"""
    page.goto(APITEST_ROUTE)
    page.settle(0.8)
    _open_api_edit_modal(page, int849_api['name'])

    def _modal_open():
        return page.exists('.crud-form-modal')

    # 路径 1：类型非空 + 地址空 → 阻止保存（弹窗保持打开）
    page.driver.execute_script(
        "var s = document.getElementById('field-proxyType');"
        "s.value = 'http'; s.dispatchEvent(new Event('change', {bubbles:true}));"
        "var i = document.getElementById('field-proxyUrl');"
        "i.value = ''; i.dispatchEvent(new Event('input', {bubbles:true}));")
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(0.5)
    assert _modal_open(), '类型非空+地址空 不应关闭弹窗'

    # 路径 2：地址缺 user:pass@ → 阻止保存
    page.driver.execute_script(
        "var i = document.getElementById('field-proxyUrl');"
        "i.value = '10.0.0.1:8080'; i.dispatchEvent(new Event('input', {bubbles:true}));")
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(0.5)
    assert _modal_open(), '地址缺 user:pass@ 不应关闭弹窗'

    # 路径 3：类型空 + 地址非空 → 阻止保存
    page.driver.execute_script(
        "var s = document.getElementById('field-proxyType');"
        "s.value = ''; s.dispatchEvent(new Event('change', {bubbles:true}));"
        "var i = document.getElementById('field-proxyUrl');"
        "i.value = 'user:pass@10.0.0.1:8080'; i.dispatchEvent(new Event('input', {bubbles:true}));")
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(0.5)
    assert _modal_open(), '类型空+地址非空 不应关闭弹窗'

    # 合法回归（路径 4 反向）：类型空 + 地址空 → 正常保存，载荷 proxy 为 null
    page.driver.execute_script(
        "var i = document.getElementById('field-proxyUrl');"
        "i.value = ''; i.dispatchEvent(new Event('input', {bubbles:true}));")
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(1.5)
    r = api_client.request('GET', f'/apis/{int849_api["id"]}')
    data = r.get('data') or {}
    assert data.get('proxy_type') in (None, ''), f'空代理回归失败: {data}'
    assert data.get('proxy_url') in (None, ''), f'空代理回归失败: {data}'
    page.capture_artifacts(page.node_artifact_dir('int849_real_modal_validated'))


def _set_proxy_fields(page, ptype: str, purl: str):
    """JS 设置编辑弹窗代理类型/地址并派发事件（与真实输入同语义）。"""
    page.driver.execute_script(
        "var s = document.getElementById('field-proxyType');"
        "s.value = arguments[0]; s.dispatchEvent(new Event('change', {bubbles:true}));"
        "var i = document.getElementById('field-proxyUrl');"
        "i.value = arguments[1]; i.dispatchEvent(new Event('input', {bubbles:true}));",
        ptype, purl)


def _notification_message(page) -> str:
    """读取当前全局通知文案（.notification-message）。"""
    els = page.driver.find_elements(By.CSS_SELECTOR, '.notification-message')
    return els[-1].text if els else ''


def test_int849_p2_scheme_and_bad_port_blocked(page, api_client, int849_api):
    """P2 复测（代码审计打回项）：带 scheme 前缀 / 非数字端口地址必须被前端拦截，
    不再落到网关 400；错误文案对齐后端口径。"""
    page.goto(APITEST_ROUTE)
    page.settle(0.8)
    _open_api_edit_modal(page, int849_api['name'])

    # 路径 A：type=http + url 带 scheme 前缀 → 前端拦截，弹窗保持打开，文案含 scheme
    _set_proxy_fields(page, 'http', 'http://user:pass@10.0.0.1:8080')
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(0.5)
    assert page.exists('.crud-form-modal'), '带 scheme 前缀不应关闭弹窗'
    msg = _notification_message(page)
    assert 'scheme' in msg, f'scheme 前缀错误文案缺失: {msg!r}'
    page.capture_artifacts(page.node_artifact_dir('int849_p2_scheme_blocked'))

    # 路径 B：type=http + url 端口非数字 → 前端拦截，文案含「端口必须为数字」
    _set_proxy_fields(page, 'http', 'user:pass@host:abc')
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(0.5)
    assert page.exists('.crud-form-modal'), '非数字端口不应关闭弹窗'
    msg = _notification_message(page)
    assert '端口必须为数字' in msg, f'非数字端口错误文案缺失: {msg!r}'
    page.capture_artifacts(page.node_artifact_dir('int849_p2_badport_blocked'))

    # 路径 C：type=http + url 多段端口（8080:extra）→ 前端拦截
    _set_proxy_fields(page, 'http', 'user:pass@10.0.0.1:8080:extra')
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(0.5)
    assert page.exists('.crud-form-modal'), '多段端口不应关闭弹窗'
    msg = _notification_message(page)
    assert '端口必须为数字' in msg, f'多段端口错误文案缺失: {msg!r}'

    # 反向：非法地址改回合法 user:pass@host:port → 保存成功，回读一致
    _set_proxy_fields(page, 'http', 'user:pass@10.0.0.1:8080')
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(1.5)
    assert not page.exists('.crud-form-modal'), '合法代理应关闭弹窗'
    r = api_client.request('GET', f'/apis/{int849_api["id"]}')
    data = r.get('data') or {}
    assert data.get('proxy_type') == 'http', f'合法保存回读 proxy_type 不一致: {data}'
    assert data.get('proxy_url') == 'user:pass@10.0.0.1:8080', f'合法保存回读 proxy_url 不一致: {data}'
    page.capture_artifacts(page.node_artifact_dir('int849_p2_blocked_then_legal'))


def test_int849_p2_legal_variants_roundtrip(page, api_client, int849_api):
    """P2 复测合法回归：IPv6 字面量 + 端口省略两种合法形态保存正常、回读一致。"""
    page.goto(APITEST_ROUTE)
    page.settle(0.8)
    _open_api_edit_modal(page, int849_api['name'])

    # IPv6 字面量 [::1]:443
    _set_proxy_fields(page, 'https', 'user:pass@[::1]:443')
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(1.5)
    assert not page.exists('.crud-form-modal'), 'IPv6 合法代理应关闭弹窗'
    r = api_client.request('GET', f'/apis/{int849_api["id"]}')
    data = r.get('data') or {}
    assert data.get('proxy_type') == 'https' and data.get('proxy_url') == 'user:pass@[::1]:443', \
        f'IPv6 回读不一致: {data}'

    # 端口省略 user:pass@host
    _open_api_edit_modal(page, int849_api['name'])
    _set_proxy_fields(page, 'socks5h', 'user:pass@10.0.0.1')
    page.settle(0.2)
    page.click('.crud-form-modal .btn-primary')
    page.settle(1.5)
    assert not page.exists('.crud-form-modal'), '端口省略合法代理应关闭弹窗'
    r = api_client.request('GET', f'/apis/{int849_api["id"]}')
    data = r.get('data') or {}
    assert data.get('proxy_type') == 'socks5h' and data.get('proxy_url') == 'user:pass@10.0.0.1', \
        f'端口省略回读不一致: {data}'
    page.capture_artifacts(page.node_artifact_dir('int849_p2_legal_variants'))
