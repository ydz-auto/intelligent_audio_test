# -*- coding: utf-8 -*-
"""INT-2460 真机探针：用例 / 标签域只读工具 + 草案推导（不写库）。

用 docker 栈（默认网关 http://127.0.0.1:15000）以用户身份走真实 ToolGateway：

1. ``testcase_query`` 六个动作（list / detail / stats / round_ref_params /
   export_status / refresh_status）逐个回源；
2. 长尾 MCP 只读工具 ``tag_list`` / ``group_list``；
3. ``testcase_generate`` 对真实带标注音频推导草案（只发 GET）。

脚本**不写任何数据**；配合调用方在运行前后统计 ``test_cases`` 行数即为
「草案不落库」的证据。输出写 UTF-8 文件，避免 Windows 控制台 GBP 折损。

用法::

    python tests/verify/int2460_testcase_readonly_probe.py --out probe.json
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
    """真实 RestToolClient + 记录 (tool, method)，用于证明全程只读。"""

    def __init__(self, base_url):
        from agent_service.infrastructure.tools.registry_bridge import RestToolClient
        self._inner = RestToolClient(base_url)
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool['name'], 'method': tool['method'],
                           'arguments': dict(arguments)})
        return self._inner.call(tool, arguments, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=os.environ.get(
        'AGENT_EVAL_BASE', 'http://127.0.0.1:15000'))
    parser.add_argument('--user', default=os.environ.get('AGENT_EVAL_USER', 'dev_user'))
    parser.add_argument('--password',
                        default=os.environ.get('AGENT_EVAL_PASSWORD', 'dev_password'))
    parser.add_argument('--out', default='int2460_probe.json')
    args = parser.parse_args()

    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.domain.ports.tool_gateway import ToolInvocationContext
    from agent_service.infrastructure.tools.registry_bridge import (
        RunCredentialRegistry, SharedToolRegistryBridge,
    )
    from tests.ui.utils.api_client import ApiClient

    client = ApiClient(args.base)
    client.login(args.user, args.password)
    rest = RecordingRest(args.base)
    credentials = RunCredentialRegistry()
    credentials.put('probe', f'Bearer {client.token}')
    bridge = SharedToolRegistryBridge()
    gateway = SharedToolGateway(bridge=bridge, rest=rest, credentials=credentials)
    context = ToolInvocationContext(
        run_id='probe', session_id='probe', owner_id=1, tenant_id='probe',
        step_id='step1', permissions=('*',), idempotency_key='probe')

    results = {'query_actions': [], 'long_tail': [], 'generate': None,
               'rest_calls': rest.calls}

    def run_tool(name, arguments):
        call = ToolCallRequest(tool_call_id=f'{name}-1', name=name,
                               arguments=arguments)
        result = gateway.execute(call, context)
        entry = {'name': name, 'arguments': arguments, 'ok': result.ok,
                 'error_code': result.error_code,
                 'content': result.content[:600]}
        return entry, result

    page = client.request('GET', '/testcases?page=1&per_page=3')['data']
    case_id = page['items'][0]['id']
    rounds = (page['items'][0].get('config') or {}).get('rounds') or []
    round_number = int(rounds[0].get('round_number') or 1) if rounds else 1

    for action, arguments in [
            ('list', {'action': 'list', 'page': 1, 'per_page': 3}),
            ('detail', {'action': 'detail', 'tc_id': case_id}),
            ('stats', {'action': 'stats'}),
            ('round_ref_params', {'action': 'round_ref_params', 'tc_id': case_id,
                                  'round_number': round_number}),
            ('export_status', {'action': 'export_status',
                               'task_id': 'probe-not-exist-export'}),
            ('refresh_status', {'action': 'refresh_status',
                                'task_id': 'probe-not-exist-refresh'}),
    ]:
        entry, _ = run_tool('testcase_query', arguments)
        entry['action'] = action
        results['query_actions'].append(entry)

    for name in ('tag_list', 'group_list'):
        entry, _ = run_tool(name, {'page': 1, 'per_page': 3} if name == 'tag_list' else {})
        results['long_tail'].append(entry)

    audios = client.request('GET', '/audios?page=1&per_page=20')['data']['items']
    annotated = [a for a in audios if a.get('annotations')][:2]
    entry, result = run_tool('testcase_generate', {
        'audio_ids': [a['id'] for a in annotated],
        'algorithm_type': 'voice_llm',
        'dimension_ids': [121],
    })
    if result.ok:
        payload = json.loads(result.content)
        entry['summary'] = {
            'mode': payload['mode'],
            'persisted': payload['persisted'],
            'writes': payload['writes'],
            'drafts': [
                {'name': draft['name'],
                 'rounds': [r['round_number'] for r in draft['config']['rounds']],
                 'audios': [a.get('audio_id') for r in draft['config']['rounds']
                            for a in r['audios']],
                 'params': draft['algorithm_params'],
                 'notes': draft['notes']}
                for draft in payload['drafts']
            ],
        }
    results['generate'] = entry
    results['rest_methods'] = sorted({c['method'] for c in rest.calls})
    results['rest_tools'] = [c['tool'] for c in rest.calls]

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print('probe written:', args.out)
    print('actions ok:', sum(1 for e in results['query_actions'] if e['ok']),
          '/', len(results['query_actions']))
    print('long tail ok:', sum(1 for e in results['long_tail'] if e['ok']),
          '/', len(results['long_tail']))
    print('generate ok:', bool(results['generate'] and results['generate']['ok']))
    print('rest methods:', results['rest_methods'])
    return 0 if all(c['method'] == 'GET' for c in rest.calls) else 3


if __name__ == '__main__':
    raise SystemExit(main())
