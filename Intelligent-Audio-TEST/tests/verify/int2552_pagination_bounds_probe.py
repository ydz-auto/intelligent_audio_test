# -*- coding: utf-8 -*-
"""INT-2552 真机探针：查询类意图工具分页边界（docker 栈，只读）。

用 docker 栈（默认网关 http://127.0.0.1:15000）以用户身份走真实 ToolGateway，
验证：

1. ``testcase_query`` / ``device_query`` / ``task_query`` / ``log_diagnose``
   在 ``per_page=100000`` / ``per_page=201`` / ``page=0`` 时返回可读参数错误
   （``INVALID_ARGUMENTS``），且 **不发起任何上游请求**（记录 REST 调用）；
2. 错误文案不含 ``psycopg2`` / ``LINE`` / ``HINT`` 等 SQL / 上游异常痕迹；
3. ``page=1&per_page=200`` 正常返回，条数 ≤ 200（结果由工具层收敛，不依赖
   ``run_orchestrator`` 的 8000 字符硬截断）；
4. ``report_query``（对照）行为不回归。

脚本**只发 GET**，不写任何数据；输出写 UTF-8 文件避免 Windows 控制台折损。

用法::

    python tests/verify/int2552_pagination_bounds_probe.py --out probe.json
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


class RecordingRest:
    """真实 RestToolClient + 记录每次回源（用于证明越界调用不发上游请求）。"""

    def __init__(self, base_url):
        from agent_service.infrastructure.tools.registry_bridge import (
            RestToolClient)
        self._inner = RestToolClient(base_url)
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool['name'],
                           'method': tool['method'],
                           'arguments': dict(arguments)})
        return self._inner.call(tool, arguments, **kwargs)


def _rows(content):
    """从工具返回的网关信封里数 items，返回 (count, page, per_page)。"""
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return None, None, None
    data = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    items = data.get('items')
    count = len(items) if isinstance(items, list) else None
    return count, data.get('page'), data.get('per_page')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=os.environ.get(
        'AGENT_EVAL_BASE', 'http://127.0.0.1:15000'))
    parser.add_argument('--user', default=os.environ.get(
        'AGENT_EVAL_USER', 'dev_user'))
    parser.add_argument('--password', default=os.environ.get(
        'AGENT_EVAL_PASSWORD', 'dev_password'))
    parser.add_argument('--out', default='int2552_probe.json')
    args = parser.parse_args()

    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.domain.ports.tool_gateway import ToolInvocationContext
    from agent_service.infrastructure.tools.registry_bridge import (
        RunCredentialRegistry, SharedToolRegistryBridge,
    )
    from shared.agent_tools import pagination
    from tests.ui.utils.api_client import ApiClient

    client = ApiClient(args.base)
    client.login(args.user, args.password)
    rest = RecordingRest(args.base)
    credentials = RunCredentialRegistry()
    credentials.put('probe', f'Bearer {client.token}')
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=credentials)
    context = ToolInvocationContext(
        run_id='probe', session_id='probe', owner_id=1, tenant_id='probe',
        step_id='step1', permissions=('*',), idempotency_key='probe')
    noise = ('psycopg2', 'LINE', 'HINT', 'Traceback')

    def run_tool(name, arguments):
        before = len(rest.calls)
        result = gateway.execute(
            ToolCallRequest(tool_call_id=f'{name}-1', name=name,
                            arguments=arguments), context)
        count, page, per_page = _rows(result.content or '')
        try:
            json.loads(result.content or '')
            json_ok = True
        except (TypeError, ValueError):
            json_ok = False
        return {
            'name': name,
            'arguments': arguments,
            'ok': result.ok,
            'error_code': result.error_code,
            'content': (result.content or '')[:400],
            'upstream_calls': len(rest.calls) - before,
            'rows': count,
            'json_parsable': json_ok,
            'page': page,
            'per_page': per_page,
            'sql_noise': [tag for tag in noise
                          if tag in (result.content or '')],
        }

    # 四个定点工具 + 报告域对照
    cases = [
        ('testcase_query', 'list', {}),
        ('device_query', 'list', {}),
        ('task_query', 'list', {}),
        ('log_diagnose', 'search', {}),
        ('report_query', 'list', {}),
    ]
    report = {'max': pagination.PER_PAGE_MAX, 'rejected': [], 'accepted': []}
    for name, action, extra in cases:
        for per_page in (100000, pagination.PER_PAGE_MAX + 1):
            report['rejected'].append(run_tool(name, dict(
                extra, action=action, per_page=per_page)))
        report['rejected'].append(run_tool(
            name, dict(extra, action=action, page=0)))
        report['accepted'].append(run_tool(name, dict(
            extra, action=action, page=1,
            per_page=pagination.PER_PAGE_MAX)))

    with open(args.out, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    failures = []
    for entry in report['rejected']:
        if entry['ok'] or entry['error_code'] != 'INVALID_ARGUMENTS':
            failures.append(f'reject-not-applied: {entry["name"]} {entry["arguments"]}')
        if entry['upstream_calls']:
            failures.append(f'upstream-called: {entry["name"]} {entry["arguments"]}')
        if entry['sql_noise']:
            failures.append(f'sql-noise: {entry["name"]} {entry["sql_noise"]}')
    for entry in report['accepted']:
        if not entry['ok']:
            failures.append(f'boundary-rejected: {entry["name"]} {entry["content"][:120]}')
        elif not entry['json_parsable']:
            failures.append(f'body-not-json: {entry["name"]}')
        elif entry['rows'] is not None and entry['rows'] > pagination.PER_PAGE_MAX:
            failures.append(f'rows-over-limit: {entry["name"]} {entry["rows"]}')

    print(json.dumps({'failures': failures,
                      'rejected': len(report['rejected']),
                      'accepted': len(report['accepted']),
                      'out': args.out}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
