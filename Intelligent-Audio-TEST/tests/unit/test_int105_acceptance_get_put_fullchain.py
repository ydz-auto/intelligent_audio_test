# -*- coding: utf-8 -*-
"""INT-105 验收测试：GET→PUT 全链路幂等（真实序列化器取证，非模拟回显）。

开发自测 test_int105_rounds_get_put_idempotency.py 以手工构造的回显 body 模拟
GET 详情；本文件改用真实链路取证并锁回归：

  task_service TestCaseQueryService.get_testcase_detail（真实拍平/维度去重）
  → 网关 TestCaseDetailData + success_response（客户端实际收到的 JSON）
  → 网关 TestCaseUpdateSchema.model_validate + model_dump(exclude_none)
  → task_service TestCaseCrudService.update

已实证线上形状（决定断言口径）：
- GET 响应 config.rounds[] 的 roundNumber 被网关 snake_case 序列化输出为
  round_number（APIModel serialize_by_alias=False，先于本修复存在的展示层
  归一）；前端编辑路径由自身表单模型重建 rounds（roundNumber）不受影响，
  后端读取方均 round_number/roundNumber 双兼容。故本文件断言轮次结构/
  音频/维度语义幂等，不锁键名拼写。
"""
import copy
import os
from datetime import datetime

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.schemas.testcase import (
    TestCaseAudioConfigItem,
    TestCaseDetailData,
    TestCaseDimensionBrief,
    TestCaseUpdateSchema,
)
from api_gateway.utils.response import success_response
from shared.utils import testcase_helpers as common
from task_service.application.testcase.testcase_crud_service import TestCaseCrudService
from task_service.application.testcase.testcase_query_service import TestCaseQueryService


class FakeGroup:
    id = 'g1'
    name = '默认分组'


class FakeTag:
    def __init__(self, name):
        self.name = name


class FakeTC:
    def __init__(self, tc_id, config):
        self.id = tc_id
        self.name = '多轮用例'
        self.description = None
        self.group_id = 'g1'
        self.group = FakeGroup()
        self.config = config
        self.algorithm_params = None
        self.reference_params = None
        self.algorithm_type = None
        self.tags = [FakeTag('回归')]
        self.created_at = datetime(2026, 10, 10, 10, 0, 0)
        self.updated_at = datetime(2026, 10, 10, 10, 0, 0)


class FakeReadRepo:
    """查询侧替身：详情序列化触及的 repo 方法。"""

    DIMS = {
        11: {'id': 11, 'name': '准确率', 'type': 'accuracy'},
        12: {'id': 12, 'name': '唤醒率', 'type': 'wake'},
        13: {'id': 13, 'name': '响应时延', 'type': 'latency'},
    }

    def __init__(self, tc):
        self.tc = tc

    def get_testcase(self, tc_id):
        return self.tc if tc_id == self.tc.id else None

    def get_audio_by_id(self, audio_id):
        return {'id': audio_id, 'name': f'音频{audio_id}', 'duration': 2.0}

    def list_dimensions_by_ids(self, ids):
        return [self.DIMS[i] for i in ids if i in self.DIMS]


class FakeWriteRepo:
    """写入侧替身：update() 触及的 repo 方法。"""

    def __init__(self, tc):
        self.tc = tc
        self.committed = False

    def get_testcase(self, tc_id):
        return self.tc if tc_id == self.tc.id else None

    def get_group_by_name(self, name):
        return None

    def create_group(self, *a, **k):
        return None

    def set_testcase_tags(self, tc, tags):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def three_round_config():
    return {
        'rounds': [
            {'roundNumber': 1,
             'audios': [{'audio_id': 2219, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': 11, 'name': '准确率', 'weight': 1.0}]}},
            {'roundNumber': 2,
             'audios': [{'audio_id': 2218, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': 11, 'name': '准确率', 'weight': 1.0}]}},
            {'roundNumber': 3,
             'audios': [{'audio_id': 2217, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': 12, 'name': '唤醒率', 'weight': 1.0}]}},
        ],
    }


def gateway_get_detail_body(tc):
    """复刻网关 get_one：task_service 详情 → TestCaseDetailData → 客户端 JSON。"""
    result = TestCaseQueryService(FakeReadRepo(tc)).get_testcase_detail(tc.id)
    assert result['success'], result
    item = result['data']

    audios = [
        TestCaseAudioConfigItem(
            id=a.get('id'), audio_id=a.get('audio_id'), audio_name=a.get('audio_name'),
            test_type=a.get('test_type'), spl=a.get('spl'),
            playback_device_id=common.normalize_optional_int(a.get('playback_device_id')),
            play_order=a.get('play_order'),
        )
        for a in item.get('audios', [])
    ]
    dimensions = [
        TestCaseDimensionBrief(id=d.get('id'), name=d.get('name'), type=d.get('type'))
        for d in item.get('dimensions', [])
    ]
    detail = TestCaseDetailData(
        id=item.get('id'), name=item.get('name'), description=item.get('description'),
        group_id=item.get('group_id'), group_name=item.get('group_name'),
        group=item.get('group'), type=item.get('type'),
        config=item.get('config') or {},
        algorithm_params=item.get('algorithm_params'),
        reference_params=item.get('reference_params'),
        algorithm_type=item.get('algorithm_type'), tags=item.get('tags', []),
        audios=audios, dimensions=dimensions,
        created_at=item.get('created_at'), updated_at=item.get('updated_at'),
        total_duration=item.get('total_duration'),
    )
    payload, _ = success_response(detail)
    return payload['data']


def echo_body(wire):
    """客户端原样回传详情的可回写字段（group dict 非更新契约，不回传）。"""
    return {
        'id': wire['id'],
        'name': wire['name'],
        'description': wire.get('description'),
        'group_id': wire.get('group_id'),
        'config': copy.deepcopy(wire['config']),
        'tags': list(wire.get('tags') or []),
        'audios': copy.deepcopy(wire.get('audios') or []),
        'dimensions': copy.deepcopy(wire.get('dimensions') or []),
    }


def update_via_gateway(svc, tc_id, client_body):
    """复刻网关 update：schema 校验 + model_dump 后进 task_service update。"""
    data = TestCaseUpdateSchema.model_validate(client_body)
    data_dict = data.model_dump(by_alias=False, exclude_none=True)
    return svc.update(tc_id, data_dict)


def make_crud(tc):
    svc = TestCaseCrudService()
    svc.repo = FakeWriteRepo(tc)
    return svc


def round_audio_ids(config, idx):
    return [a['audio_id'] for a in config['rounds'][idx].get('audios') or []]


def round_dim_ids(config, idx):
    dims = (config['rounds'][idx].get('evaluation') or {}).get('dimensions') or []
    return [d['id'] for d in dims]


def test_fullchain_get_put_echo_twice_semantically_idempotent():
    tc = FakeTC('c1', three_round_config())
    wire1 = gateway_get_detail_body(tc)
    # 缺陷前提取证：GET 详情顶层 audios 为全部轮次拍平（合成 id），dims 去重
    assert [a['audio_id'] for a in wire1['audios']] == [2219, 2218, 2217]
    assert sorted(d['id'] for d in wire1['dimensions']) == [11, 12]

    svc = make_crud(tc)
    for _ in range(2):
        res = update_via_gateway(svc, tc.id, echo_body(gateway_get_detail_body(tc)))
        assert res['success'], res

    cfg = tc.config
    assert len(cfg['rounds']) == 3
    # 原缺陷：两次 PUT 后 round1.audios 变 5 条、顶层 audios 变 7 条
    assert round_audio_ids(cfg, 0) == [2219]
    assert round_audio_ids(cfg, 1) == [2218]
    assert round_audio_ids(cfg, 2) == [2217]
    assert [a['audio_id'] for a in common.collect_audios(cfg)] == [2219, 2218, 2217]
    # 原缺陷：round1 单轮维度被顶层过期合并数据覆盖
    assert round_dim_ids(cfg, 0) == [11]
    assert round_dim_ids(cfg, 1) == [11]
    assert round_dim_ids(cfg, 2) == [12]

    # API 层幂等：回写后的 GET 顶层 audios/dimensions 与首次一致
    wire2 = gateway_get_detail_body(tc)
    assert [(a['audio_id'], a['spl'], a['play_order']) for a in wire2['audios']] == \
        [(a['audio_id'], a['spl'], a['play_order']) for a in wire1['audios']]
    assert sorted(d['id'] for d in wire2['dimensions']) == [11, 12]


def test_fullchain_round1_dimensions_update_via_config_echo():
    tc = FakeTC('c1', three_round_config())
    svc = make_crud(tc)

    body = echo_body(gateway_get_detail_body(tc))
    body['config']['rounds'][0]['evaluation']['dimensions'] = [
        {'id': 13, 'name': '响应时延', 'weight': 0.5}]
    res = update_via_gateway(svc, tc.id, body)
    assert res['success'], res

    cfg = tc.config
    assert round_dim_ids(cfg, 0) == [13]
    assert round_dim_ids(cfg, 1) == [11]
    assert round_dim_ids(cfg, 2) == [12]
    assert round_audio_ids(cfg, 0) == [2219]

    # 落库后 API 可见：顶层 dimensions 含新维度 id
    wire2 = gateway_get_detail_body(tc)
    assert sorted(d['id'] for d in wire2['dimensions']) == [11, 12, 13]


def test_fullchain_legacy_flat_partial_update_without_config():
    cfg = three_round_config()
    cfg['rounds'] = cfg['rounds'][:1]
    tc = FakeTC('c1', cfg)
    svc = make_crud(tc)

    # 旧平面契约：不带 config 的顶层 audios/dimensions 部分更新仍写 round1
    res = update_via_gateway(svc, tc.id, {
        'audios': [{'audio_id': 33, 'spl': 70, 'play_order': 0}]})
    assert res['success'], res
    assert round_audio_ids(tc.config, 0) == [33]

    res = update_via_gateway(svc, tc.id, {'dimensions': [{'id': 9, 'name': '误唤醒'}]})
    assert res['success'], res
    assert round_dim_ids(tc.config, 0) == [9]
