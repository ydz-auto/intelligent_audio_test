# -*- coding: utf-8 -*-
"""INT-2463 报告域实测：真实 docker 网关上的 10 条任务、字段口径与只读语义。

默认跳过；显式给出网关地址时运行（实测命令）：

    AGENT_LIVE_GATEWAY=http://127.0.0.1:15000 python -m pytest \
        tests/agent_eval/domains/report/test_report_live_contract.py -s

前置：docker 栈已起（网关 15000），栈上存在 dev_user / dev_password 账号。
这里直接组合 ``SharedToolGateway`` + ``RestToolClient`` 打真实网关，验证
「工具层 → REST → report_service」整条链路；不做任何写操作。
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, RESOURCE_NOT_FOUND, SharedToolGateway,
)
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_eval.domains.report import fixtures

GATEWAY = os.environ.get('AGENT_LIVE_GATEWAY', '').strip().rstrip('/')
GATEWAY_USER = os.environ.get('UI_TEST_USERNAME', 'dev_user')
GATEWAY_PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

pytestmark = pytest.mark.skipif(
    not GATEWAY, reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')


def _get_json(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _login():
    """按 INT-147 契约登录：GET 公钥 → RSA-OAEP 加密密码 → form 提交。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = _get_json(f'{GATEWAY}/api/v1/auth/encryption-key')
    assert key.get('enabled') is True, '网关未开启密码加密，无法按契约登录'
    public_key = serialization.load_pem_public_key(
        key['public_key'].encode('utf-8'))
    ciphertext = base64.b64encode(public_key.encrypt(
        GATEWAY_PASSWORD.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None))).decode('ascii')
    body = urllib.parse.urlencode({
        'username': GATEWAY_USER,
        'password_encrypted': ciphertext,
        'encryption_key_id': key['kid'],
    }).encode('utf-8')
    request = urllib.request.Request(
        f'{GATEWAY}/api/v1/auth/login', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(request, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


@pytest.fixture(scope='module')
def live():
    try:
        login = _login()
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover
        pytest.skip(f'网关不可用：{exc}')
    if 'access_token' not in login:  # pragma: no cover
        pytest.skip(f'网关登录失败：{str(login)[:200]}')
    token = login['access_token']
    credentials = RunCredentialRegistry()
    credentials.put('live-run', f'Bearer {token}')
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(GATEWAY),
        credentials=credentials)
    return gateway, token


def _ctx(permissions=('report:read', 'report:compare')):
    return ToolInvocationContext(
        run_id='live-run', session_id='live', owner_id=1, tenant_id='default',
        step_id='step', permissions=tuple(permissions), idempotency_key='k')


def _execute(gateway, name, arguments,
             permissions=('report:read', 'report:compare')):
    return gateway.execute(
        ToolCallRequest(tool_call_id='live', name=name, arguments=arguments),
        _ctx(permissions))


def _raw(path, token):
    request = urllib.request.Request(
        f'{GATEWAY}{path}', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _task_reports(token):
    """取两份有 task_id 的任务报告（用于按任务查 + 多报告对比）。"""
    status, listed = _raw(
        '/api/v1/reports?report_type=task&page=1&per_page=20', token)
    assert status == 200
    items = [item for item in listed['data']['items'] if item.get('task_id')]
    if len(items) < 2:  # pragma: no cover - 空库环境
        pytest.skip('库里任务报告不足 2 份，无法跑对比类任务')
    return items


def test_live_six_fetch_tasks(live):
    """取数 6 条：list / by_task / detail / tab-counts / statistics / cases。"""
    gateway, token = live
    reports = _task_reports(token)
    report = reports[0]

    arguments_by_name = {
        '列出草稿报告': {'action': 'list', 'status': 'draft',
                        'page': 1, 'per_page': 10},
        '按任务查报告': {'action': 'by_task', 'task_id': report['task_id']},
        '看报告详情指标': {'action': 'detail', 'report_id': report['id']},
        '查页签计数': {'action': 'tab_counts'},
        '按设备类型看统计': {'action': 'statistics', 'dimension': 'device_type'},
        '看报告内用例': {'action': 'cases', 'report_id': report['id'],
                        'page': 1, 'per_page': 10},
    }
    passed = []
    for task in fixtures.DOMAIN_TASKS:
        if task['tool'] != 'report_query':
            continue
        result = _execute(gateway, 'report_query', dict(arguments_by_name[task['name']]))
        assert result.ok, f"{task['name']} 失败：{result.error_code} {result.content}"
        payload = json.loads(result.content)
        assert payload['success'] is True, task['name']
        data = payload['data']
        for field in task['checks']:
            assert field in data, f"{task['name']} 缺少 {field}"
        passed.append(task['name'])
    assert len(passed) == 6
    print('\n取数 6 条全部通过：', '、'.join(passed))


def test_live_report_list_filters_really_narrow(live):
    """列表过滤参数在真实网关上生效（不是被静默忽略）。"""
    gateway, _ = live

    def total(arguments):
        result = _execute(gateway, 'report_query', arguments)
        assert result.ok, result.content
        return json.loads(result.content)['data']['total']

    all_total = total({'action': 'list', 'page': 1, 'per_page': 1})
    assert all_total > 0
    drafts = total({'action': 'list', 'status': 'draft', 'page': 1, 'per_page': 1})
    published = total({'action': 'list', 'status': 'published',
                       'page': 1, 'per_page': 1})
    assert drafts + published <= all_total
    assert drafts <= all_total and published <= all_total

    comparison = total({'action': 'list', 'report_type': 'comparison',
                        'page': 1, 'per_page': 1})
    secondary = total({'action': 'list', 'report_type': 'secondary_comparison',
                       'page': 1, 'per_page': 1})
    assert comparison + secondary <= all_total

    result = _execute(gateway, 'report_query', {'action': 'list',
                                                'keyword': '__no_such_report__',
                                                'page': 1, 'per_page': 1})
    assert json.loads(result.content)['data']['total'] == 0


def test_live_report_fields_match_gateway_schema(live):
    """详情字段口径：summary 的指标 / 统计字段与样例一致，数值原样下发。"""
    gateway, token = live
    reports = _task_reports(token)
    result = _execute(gateway, 'report_query',
                      {'action': 'detail', 'report_id': reports[0]['id']})
    assert result.ok, result.content
    data = json.loads(result.content)['data']
    for field in ('id', 'name', 'type', 'status', 'summary', 'created_at'):
        assert field in data, field
    summary = data['summary']
    for field in ('total_cases', 'completed_cases', 'failed_cases', 'pass_rate',
                  'all_metrics', 'metric_data', 'resources', 'resource_headers'):
        assert field in summary, field
    for metric in summary['all_metrics'][:5]:
        assert set(metric) >= {'id', 'name', 'unit', 'decimal_places',
                               'statistic_method', 'dimension_type'}
    # 数值不经工具层改写：pass_rate 与原始 REST 一致
    status, raw = _raw(f"/api/v1/reports/{reports[0]['id']}", token)
    assert status == 200
    assert summary['pass_rate'] == raw['data']['summary']['pass_rate']
    assert summary['total_cases'] == raw['data']['summary']['total_cases']


def test_live_cases_and_case_averages(live):
    gateway, token = live
    reports = _task_reports(token)
    report_id = reports[0]['id']

    cases = _execute(gateway, 'report_query',
                     {'action': 'cases', 'report_id': report_id,
                      'page': 1, 'per_page': 5})
    assert cases.ok, cases.content
    page = json.loads(cases.content)['data']
    assert set(page) == {'items', 'total', 'page', 'per_page', 'pages'}

    averages = _execute(gateway, 'report_query',
                        {'action': 'case_averages', 'report_id': report_id})
    assert averages.ok, averages.content
    data = json.loads(averages.content)['data']
    for field in ('total_cases', 'overall_averages', 'metric_data',
                  'resource_headers', 'partial'):
        assert field in data, field

    search = _execute(gateway, 'report_query',
                      {'action': 'cases_search', 'report_id': report_id,
                       'page': 1, 'per_page': 5, 'sort_by': 'name'})
    assert search.ok, search.content


def test_live_get_cases_rejects_tags_and_page_bounds(live):
    """参数护栏：GET cases 的 tags 恒 400（网关），分页越界工具层先拦。"""
    gateway, token = live
    reports = _task_reports(token)
    report_id = reports[0]['id']

    result = _execute(gateway, 'report_query',
                      {'action': 'cases', 'report_id': report_id,
                       'tags': ['随便一个标签']})
    assert result.error_code == INVALID_ARGUMENTS

    for arguments in ({'action': 'list', 'page': 0},
                      {'action': 'list', 'per_page': 500}):
        result = _execute(gateway, 'report_query', arguments)
        assert result.error_code == INVALID_ARGUMENTS, arguments


def test_live_missing_report_is_plain_not_found(live):
    gateway, _ = live
    result = _execute(gateway, 'report_query',
                      {'action': 'detail', 'report_id': 2000000000})
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert '不存在或无权访问' in result.content


def test_live_compare_four_tasks_and_no_report_written(live):
    """对比 4 条：并排 / 二次对比类型守卫 / 趋势，且不新增报告记录。"""
    gateway, token = live
    reports = _task_reports(token)
    ids = [item['id'] for item in reports[:2]]

    before = _raw('/api/v1/reports/tab-counts', token)[1]['data']

    compare = _execute(gateway, 'report_compare',
                       {'action': 'compare', 'report_ids': ids})
    assert compare.ok, compare.content
    payload = json.loads(compare.content)
    assert payload['report_count'] == 2
    assert {r['report_id'] for r in payload['reports']} == set(ids)
    for report in payload['reports']:
        assert report['summary']['pass_rate'] is not None
        assert report['type'] in ('task', 'comparison',
                                  'secondary_comparison', 'benchmark')

    # 二次对比对任务报告必须拒绝（类型守卫）
    rejected = _execute(gateway, 'report_compare',
                        {'action': 'secondary_compare', 'report_ids': ids})
    assert rejected.error_code == INVALID_ARGUMENTS
    assert 'secondary_compare' in rejected.content

    trend = _execute(gateway, 'report_compare', {'action': 'trend'})
    assert trend.ok, trend.content
    assert json.loads(trend.content)['data']['trend_type'] in ('time', 'dimension')

    after = _raw('/api/v1/reports/tab-counts', token)[1]['data']
    assert after == before, '对比工具不得新增 / 删除报告记录（只读语义）'
    print('\n对比 3 条 + 类型守卫通过，报告计数未变：', json.dumps(before, ensure_ascii=False))


def test_live_compare_secondary_reports_when_present(live):
    """库里有对比 / 二次对比报告时，secondary_compare 应能并排并带源任务。"""
    gateway, token = live
    status, listed = _raw(
        '/api/v1/reports?page=1&per_page=20', token)
    assert status == 200
    compatible = [item['id'] for item in listed['data']['items']
                  if item.get('type') in ('comparison', 'secondary_comparison')]
    if len(compatible) < 2:  # pragma: no cover - 库依赖
        pytest.skip('库里对比类报告不足 2 份')

    result = _execute(gateway, 'report_compare',
                      {'action': 'secondary_compare',
                       'report_ids': compatible[:2]})
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['report_count'] == 2
    assert all(r['type'] in ('comparison', 'secondary_comparison')
               for r in payload['reports'])


def test_live_partial_missing_is_reported_not_silent(live):
    gateway, token = live
    reports = _task_reports(token)
    good = reports[0]['id']
    result = _execute(gateway, 'report_compare',
                      {'action': 'compare', 'report_ids': [good, 2000000000]})
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['report_count'] == 1
    assert payload['missing'][0]['report_id'] == 2000000000
