# -*- coding: utf-8 -*-
"""INT-2460 真机契约核对（默认 skip，``AGENT_EVAL_LIVE=1`` 才跑）。

连本机 docker 网关（默认 15000）核对：
- 用例列表 / 详情 / 统计、标签、分组 的真实字段形状与文档一致；
- ``testcase_generate`` 走**真实网关**回源（用户自己的 Authorization），
  草案推导只发 GET、不落库；轮次号与音频标注的 ``data.round_number`` 一致。

写操作：无。登录用 ``AGENT_EVAL_USER`` / ``AGENT_EVAL_PASSWORD``（默认 dev_user）。
"""
import json
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))

_LIVE = os.environ.get('AGENT_EVAL_LIVE') == '1'

pytestmark = pytest.mark.skipif(
    not _LIVE, reason='AGENT_EVAL_LIVE!=1：默认离线，真机契约核对按需开启')


@pytest.fixture(scope='module')
def client():
    from tests.ui.utils.api_client import ApiClient

    api = ApiClient(os.environ.get('AGENT_EVAL_BASE', 'http://127.0.0.1:15000'))
    api.login(os.environ.get('AGENT_EVAL_USER', 'dev_user'),
              os.environ.get('AGENT_EVAL_PASSWORD', 'dev_password'))
    return api


def _env_item(model, item, label):
    """校验契约字段：必填字段必须出现；可选字段允许被 ``exclude_none`` 省略。"""
    required = [name for name, field in model.model_fields.items()
                if field.is_required()]
    missing = [name for name in required if name not in item]
    assert missing == [], f'{label} 缺少契约必填字段：{missing}'
    unknown = set(item) - set(model.model_fields)
    assert unknown == set(), f'{label} 出现契约外字段：{sorted(unknown)}'


def test_live_testcase_list_and_detail_shapes(client):
    from api_gateway.schemas.testcase import (
        TestCaseDetailData, TestCaseListItem,
    )

    page = client.request('GET', '/testcases?page=1&per_page=2')['data']
    assert set(page) == {'items', 'total', 'page', 'per_page', 'pages'}
    assert page['items'], '主库没有用例，先确认连的是真实库'
    for item in page['items']:
        _env_item(TestCaseListItem, item, '用例列表项')

    detail = client.request(
        'GET', f"/testcases/{page['items'][0]['id']}")['data']
    _env_item(TestCaseDetailData, detail, '用例详情')
    assert isinstance(detail['config'].get('rounds'), list)
    for round_item in detail['config']['rounds']:
        assert 'round_number' in round_item and 'audios' in round_item


def test_live_tag_and_group_shapes(client):
    from api_gateway.schemas.group import GroupItem
    from api_gateway.schemas.testcase import TagItem

    tags = client.request('GET', '/tags?page=1&per_page=3')['data']
    assert tags['total'] >= 1
    for item in tags['items']:
        _env_item(TagItem, item, '标签项')

    groups = client.request('GET', '/groups')['data']
    assert groups['total'] >= 1
    for item in groups['items']:
        _env_item(GroupItem, item, '分组项')
        assert isinstance(item['test_case_count'], int)


def test_live_stats_shape(client):
    from api_gateway.schemas.testcase import TestCaseStatsData

    data = client.request('GET', '/testcases/stats')['data']
    assert set(data) == set(TestCaseStatsData.model_fields)


def _recording_rest():
    """真实 RestToolClient + 记录工具方法（断言只读）。"""
    from agent_service.infrastructure.tools.registry_bridge import RestToolClient

    base = os.environ.get('AGENT_EVAL_BASE', 'http://127.0.0.1:15000')

    class RecordingRest(RestToolClient):
        def __init__(self):
            super().__init__(base)
            self.calls = []

        def call(self, tool, arguments, **kwargs):
            self.calls.append({'tool': tool['name'], 'method': tool['method'],
                               'arguments': dict(arguments)})
            return super().call(tool, arguments, **kwargs)

    return RecordingRest()


def test_live_generate_draft_is_readonly_and_round_matches_annotation(client):
    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.domain.ports.tool_gateway import ToolInvocationContext
    from agent_service.infrastructure.tools.registry_bridge import (
        RunCredentialRegistry, SharedToolRegistryBridge,
    )

    audios = client.request('GET', '/audios?page=1&per_page=20')['data']['items']
    annotated = [a for a in audios if a.get('annotations')]
    assert annotated, '主库前 20 条音频都没有标注，无法核对草案口径'
    audio = annotated[0]

    rest = _recording_rest()
    credentials = RunCredentialRegistry()
    credentials.put('live', f'Bearer {client.token}')
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest, credentials=credentials)
    context = ToolInvocationContext(
        run_id='live', session_id='s', owner_id=int(audio.get('created_by_user_id') or 1),
        tenant_id='live', step_id='step', permissions=('*',), idempotency_key='k')

    result = gateway.execute(ToolCallRequest(
        tool_call_id='c1', name='testcase_generate',
        arguments={'audio_ids': [audio['id']], 'algorithm_type': 'voice_llm'}),
        context)
    assert result.ok, result.content

    payload = json.loads(result.content)
    assert payload['persisted'] is False and payload['writes'] == 0
    draft = payload['drafts'][0]
    assert 'id' not in draft

    # 只读：每一次回源都是 GET
    assert rest.calls and all(call['method'] == 'GET' for call in rest.calls), rest.calls

    # 轮次号与标注原文一致（不编造轮次）
    def _ann_data(annotation):
        data = annotation.get('data')
        return data if isinstance(data, dict) else {}

    expected_rounds = sorted({
        int(_ann_data(ann).get('round_number') or 1)
        for ann in audio['annotations']})
    assert [item['round_number'] for item in draft['config']['rounds']] == expected_rounds

    # 声压 / 播放设备名与标注 segments 原文一致
    segments = [seg for ann in audio['annotations']
                for seg in _ann_data(ann).get('segments') or []]
    in_round = [seg for ann in audio['annotations']
                if int(_ann_data(ann).get('round_number') or 1)
                == expected_rounds[0]
                for seg in _ann_data(ann).get('segments') or []]
    if in_round and in_round[0].get('spl') is not None:
        assert draft['config']['rounds'][0]['audios'][0]['spl'] == float(
            in_round[0]['spl'])
    if segments and segments[0].get('playback_device_name'):
        assert (draft['config']['rounds'][0]['audios'][0].get('playback_device_name')
                == segments[0]['playback_device_name'])
