# -*- coding: utf-8 -*-
"""平台原始报告导出（``report_export_raw``）的审批流与渲染产物。

验收锚点（设计文档 ``doc/agent化/10_原始报告导出设计.md`` §4）：
1. 提案阶段零副作用，diff 指明 report_id + format + 「音频不打包」；
2. 审批后只调一次 ``POST /report-studio/raw-exports``，返回 done + download_ref；
3. 缺 ``report:studio:export`` 权限直接拒绝，不回源；
4. 渲染器：HTML 含全部用例（每条可展开）、MD 含按用例分节的维度表，
   数值与入参一致、不重算。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from report_service.application.services.raw_report_renderer import (
    render_raw_report,
)
from shared.agent_tools import report_tools
from tests.agent_write.helpers import (
    FakeLlm, approvals_of, decide, make_container, pending_approval,
    start_run, text_turn, tool_turn,
)


def _payload(data, status=200, success=True):
    body = {'success': success, 'code': 0 if success else status,
            'message': 'Success' if success else 'failed', 'data': data}
    return RestResult(status=status, payload=body,
                      text=json.dumps(body, ensure_ascii=False))


class FakeRawReportRest:
    """只回 ``report_studio_export_raw_report``，并记录入参。"""

    def __init__(self, *, truncated=False):
        self.calls = []
        self._truncated = truncated

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        name = tool['name']
        if name == 'report_studio_export_raw_report':
            body = arguments.get('body') or {}
            return _payload({
                'export_id': 'raw-export-1',
                'doc_id': f"raw:{body.get('report_id')}",
                'report_id': body.get('report_id'),
                'version': 1, 'format': body.get('format'),
                'theme': body.get('theme') or 'default',
                'status': 'done', 'progress': 100,
                'case_count': 188, 'truncated': self._truncated,
                'download_ref': '/api/v1/report-studio/exports/raw-export-1/download',
                'reused': False,
            })
        raise AssertionError(f'未预期的回源工具：{name}')


def _gateway(rest):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())


def _scenario(tmp_path, rest, call, permissions=('*',)):
    llm = FakeLlm([tool_turn([call]), text_turn('原始报告导出已处理')])
    container, _engine, _sf = make_container(
        tmp_path, llm, gateway=_gateway(rest))
    run = start_run(container, permissions=permissions)
    return container, llm, run


# ---------------------------------------------------------------- 提案 / 审批

def test_raw_export_proposes_without_side_effect(tmp_path):
    rest = FakeRawReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export_raw',
        arguments={'report_id': 506, 'format': 'html'})
    container, _llm, run = _scenario(tmp_path, rest, call)

    assert rest.calls == []
    approval = pending_approval(container, run.id)
    assert approval.proposal['tool'] == 'report_export_raw'
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.diff['kind'] == 'report_export_raw'
    assert approval.diff['report_id'] == 506
    assert approval.diff['format'] == 'html'
    assert '音频不随报告打包' in approval.diff['effect']

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    assert [c['tool']['name'] for c in rest.calls] == [
        'report_studio_export_raw_report']
    assert rest.calls[0]['arguments'] == {
        'body': {'report_id': 506, 'format': 'html'}}
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    payload = json.loads(record.result['content'])
    assert payload['status'] == 'done'
    assert payload['case_count'] == 188
    assert payload['truncated'] is False
    assert payload['download_ref'].endswith('/raw-export-1/download')
    assert '每条用例可展开' in payload['note']


def test_raw_export_rejects_pdf_and_missing_report_id():
    assert report_tools.validate_export_raw({'report_id': 1, 'format': 'pdf'}) \
        == 'format 取值必须是 html / md 之一：pdf'
    assert report_tools.validate_export_raw({'format': 'html'}) \
        == '缺少必填参数：report_id'
    assert report_tools.validate_export_raw(
        {'report_id': 0, 'format': 'html'}).startswith('report_id 必须是正整数')
    assert report_tools.validate_export_raw(
        {'report_id': 1, 'format': 'md', 'doc_id': 'x'}) == '不支持参数：doc_id'
    assert report_tools.proposal_diff_export_raw({'report_id': 1, 'format': 'pdf'}) \
        is None


def test_raw_export_without_permission_is_denied(tmp_path):
    rest = FakeRawReportRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export_raw',
        arguments={'report_id': 506, 'format': 'html'})
    container, _llm, run = _scenario(tmp_path, rest, call,
                                     permissions=('report:read',))
    assert approvals_of(container, run.id) == []
    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.result_code == 'PERMISSION_DENIED'


def test_raw_export_marks_truncated(tmp_path):
    rest = FakeRawReportRest(truncated=True)
    call = ToolCallRequest(
        tool_call_id='c1', name='report_export_raw',
        arguments={'report_id': 506, 'format': 'md'})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    payload = json.loads(record.result['content'])
    assert payload['truncated'] is True
    assert '已截断' in payload['note']


# ---------------------------------------------------------------- 渲染器

def _detail():
    return {
        'id': 506, 'name': '任务报告_测试', 'status': 'published', 'type': 'task',
        'summary': {'total_cases': 2, 'completed_cases': 1, 'failed_cases': 1,
                    'pass_rate': 54.79},
        'all_metrics': [
            {'id': 121, 'name': '拒识成功数量', 'unit': '%',
             'statistic_method': 'weighted_sum_ratio', 'dimension_type': 'main'},
            {'id': 132, 'name': '回复时拒识静默行为数量', 'unit': '%',
             'statistic_method': 'weighted_sum_ratio', 'dimension_type': 'sub',
             'parent_dimension_name': '拒识失败数量'},
        ],
        'metric_data': [{
            'resource': '14-pura90-豆包-拒识-1.0.0',
            'metrics': [
                {'metric': '拒识成功数量', 'value': 56.5217},
                {'metric': '拒识失败数量', 'value': 43.4783},
            ],
        }],
        'case_type_stats': [{
            'group_id': 'g1', 'group_name': '拒识',
            'metrics': [{'metric': '拒识成功数量', 'value': 0.5652}],
        }],
    }


def _cases():
    return [
        {
            'id': 'c1', 'name': 'JS116_回复状态一次拒识-汽车发动机.wav',
            'category': '拒识', 'tags': [{'name': '环境音拒识'}],
            'metrics': [{
                'resource': '14-pura90-豆包-拒识-1.0.0',
                'metrics': [
                    {'metric': '拒识失败数量@overall', 'value': 1.0,
                     'dimension_type': 'main', 'parent_dimension_name': None},
                    {'metric': '回复时拒识静默行为数量@round:2', 'value': 1.0,
                     'dimension_type': 'sub',
                     'parent_dimension_name': '拒识失败数量'},
                ],
            }],
        },
        {
            'id': 'c2', 'name': 'JS028_单轮拒识-非目标人.wav',
            'category': '不明确拒识场景', 'tags': [],
            'metrics': [],
            'description': '自动从音频创建的测试用例',
            'referenceParams': {
                'query': {'label': 'query', 'text': '用户1：哎老王，你看到我钥匙了吗？'},
                'is_single_round': True,
            },
            'algorithmResults': [
                {'param_code': 'device_type', 'param_type': 'text',
                 'value': 'pura90', 'label': 'device_type'},
                {'param_code': 'question@round:1', 'param_type': 'text',
                 'value': '豆包识别为空', 'label': 'question (第1轮)',
                 'round_number': 1, 'dimension_name': None},
                {'param_code': 'start_ms@round:1', 'param_type': 'timestamp',
                 'value': 1795214920600, 'label': 'start_ms (第1轮)',
                 'round_number': 1, 'dimension_name': None},
                {'param_code': 'rounds', 'param_type': 'json',
                 'value': [{'input': 1}], 'label': 'rounds'},
            ],
        },
    ]


def test_raw_renderer_html_has_expandable_cases_with_metric_values():
    content, ext, mime = render_raw_report(_detail(), _cases(), 'html')
    text = content.decode('utf-8')
    assert ext == '.html' and mime.startswith('text/html')
    assert text.count('<details class="case"') == 2
    assert 'JS116_回复状态一次拒识-汽车发动机.wav' in text
    # 用例级维度值（@round:2 拆成轮次 + 维度名）
    assert 'round:2' in text
    assert '回复时拒识静默行为数量' in text
    # 报告级指标矩阵原值
    assert '56.5217' in text
    assert '43.4783' in text
    # 总览引用 summary 原值
    assert '54.79' in text
    # 交互脚本与音频提示
    assert 'id="raw-case-filter"' in text
    assert '音频文件不随报告打包' in text
    # 用例详情三块：参考数据 / 执行结果 / 评分指标（对齐平台用例详情页）
    assert '参考数据' in text
    assert '执行结果' in text
    assert '评分指标' in text
    # 参考数据：布尔 → 是/否；执行结果：时间戳格式化、元信息码 / rounds 跳过
    assert '>是<' in text
    assert '用户1：哎老王，你看到我钥匙了吗？' in text
    assert '豆包识别为空' in text
    assert '2026-11-20 22:48:40' in text
    assert 'device_type' not in text.split('执行结果')[1].split('评分指标')[0]
    assert '"input"' not in text
    # 不含任何外部资源 / 音频标签
    assert '<audio' not in text
    assert 'src="http' not in text


def test_raw_renderer_markdown_has_per_case_sections():
    content, ext, mime = render_raw_report(_detail(), _cases(), 'md')
    text = content.decode('utf-8')
    assert ext == '.md' and mime.startswith('text/markdown')
    assert '## 四、用例明细' in text
    assert text.count('### 1. ') == 1
    assert '### 2. ' in text
    assert 'JS116_回复状态一次拒识-汽车发动机.wav' in text
    assert '回复时拒识静默行为数量' in text
    assert '56.5217' in text
    assert '执行结果' in text
    assert '豆包识别为空' in text
    assert '2026-11-20 22:48:40' in text


def test_raw_renderer_rejects_unsupported_format():
    try:
        render_raw_report(_detail(), _cases(), 'pdf')
    except ValueError as exc:
        assert '仅支持 html / md' in str(exc)
    else:
        raise AssertionError('pdf 应被拒绝')
