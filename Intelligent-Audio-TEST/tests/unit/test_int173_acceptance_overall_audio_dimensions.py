# -*- coding: utf-8 -*-
"""INT-173 验收测试：整体评估（顶层 config.dimensions）允许配置音频维度。

原口径（已随本卡删除）：validate_multi_round_audio_dimensions 视整体评估在
所有轮次执行后触发、无法传递音频文件为由，多轮用例顶层 dimensions 配置
需音频入参的维度时建/改用例被 400 拦截。子服务升级支持音频传递后该拦截
属过时口径（V9.7.10 3f93b6c0 对齐），create/update 两处调用与 helper 全删。

本文件锁定三件事：

1. create/update：多轮用例顶层 dimensions 携带音频维度 → 落库成功、无 400。
   gRPC 桩武装为「该维度确含 audio 入参」——旧校验若被重新引入必然 400，
   本文件即红；同时断言桩从未被调用，排除「校验仍在、仅因 gRPC 不可用
   静默放行」的假通过（旧实现 gRPC 异常时放行）。
2. 单轮评估维度（rounds[].evaluation.dimensions）配置音频维度始终允许，
   不受删除影响。
3. helper 确已从 shared.utils.testcase_helpers 删除。

真库部分（FakeDB 段外）在进程级临时 sqlite 上走真实 repository 落库并
回读取证，teardown 清理本卡写入的行。
"""
import json
import os
import tempfile
from datetime import datetime

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import shared.utils.testcase_helpers as common
import shared.clients.grpc_clients as grpc_clients
from task_service.application.testcase.testcase_crud_service import TestCaseCrudService


AUDIO_DIM_ID = 72134   # 需音频入参的维度（GetDimensionParams 桩口径）
PLAIN_DIM_ID = 11


# ============================================================
# gRPC 桩：复现旧校验 400 的触发条件（维度含 audio 入参）
# ============================================================

class _GrpcResp:
    def __init__(self, payload, success=True):
        self.success = success
        self.data = json.dumps(payload, ensure_ascii=False)


class _ArmedAlgoStub:
    """GetDimensionParams 恒报 AUDIO_DIM_ID 含 audio/input 参数。

    旧校验若被重新引入：查到 audio 入参 → 拼 400 文案 → 建/改用例失败。
    """

    def __init__(self):
        self.dimension_param_calls = []

    def GetDimensionParams(self, req):
        self.dimension_param_calls.append(req.dimension_id)
        return _GrpcResp({'params': [
            {'dimension_id': AUDIO_DIM_ID, 'param_code': 'audio_in',
             'field_type': 'audio', 'param_direction': 'input'},
        ]})


class _ArmedEvalStub:
    def __init__(self):
        self.calls = []

    def GetDimensionByIds(self, req):
        self.calls.append(req)
        return _GrpcResp({'items': [{'id': AUDIO_DIM_ID, 'name': '相似度(音频)'}]})


@pytest.fixture
def audio_capability_armed(monkeypatch):
    """把旧校验依赖的两个 gRPC 桩武装成「该维度确需音频入参」。

    当前正确行为：校验已删，桩不应被任何建/改用例路径调用。
    """
    algo_stub = _ArmedAlgoStub()
    eval_stub = _ArmedEvalStub()
    monkeypatch.setattr(
        grpc_clients, 'get_algorithm_definition_service_stub', lambda: algo_stub)
    monkeypatch.setattr(
        grpc_clients, 'get_evaluation_config_service_stub', lambda: eval_stub)
    return algo_stub


# ============================================================
# 应用层替身（int105 验收同款口径）
# ============================================================

class FakeTag:
    def __init__(self, name):
        self.name = name


class FakeTC:
    def __init__(self, tc_id, config):
        self.id = tc_id
        self.name = '多轮用例'
        self.description = None
        self.group_id = 'g1'
        self.config = config
        self.algorithm_params = None
        self.reference_params = None
        self.algorithm_type = None
        self.tags = []
        self.created_at = datetime(2026, 10, 10, 10, 0, 0)
        self.updated_at = datetime(2026, 10, 10, 10, 0, 0)
        self.created_by_user_id = None
        self.updated_by_user_id = None


class FakeRepo:
    """create/update 触及的 repo 方法替身；create_testcase 暂存入参供断言。"""

    def __init__(self, tc=None):
        self.tc = tc
        self.created_payload = None
        self.committed = False

    def get_testcase(self, tc_id):
        if self.tc is not None and tc_id == self.tc.id:
            return self.tc
        return None

    def get_group_by_name(self, name):
        return None

    def create_group(self, *a, **k):
        return None

    def create_testcase(self, data):
        self.created_payload = data
        self.tc = FakeTC(data['id'], data['config'])
        self.tc.name = data['name']
        return self.tc

    def set_testcase_tags(self, tc, tags):
        tc.tags = [FakeTag(t) if isinstance(t, str) else t for t in tags]

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def two_round_config(overall_dims):
    """两轮 + 整体评估（顶层 dimensions）= overall_dims 的标准多轮 config。"""
    return {
        'rounds': [
            {'roundNumber': 1,
             'audios': [{'audio_id': 2219, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': PLAIN_DIM_ID, 'name': '准确率',
                                            'weight': 1.0}]}},
            {'roundNumber': 2,
             'audios': [{'audio_id': 2218, 'spl': 65, 'play_order': 0}],
             'evaluation': {'dimensions': [{'id': PLAIN_DIM_ID, 'name': '准确率',
                                            'weight': 1.0}]}},
        ],
        'dimensions': overall_dims,
    }


def audio_overall_dims():
    return [{'id': AUDIO_DIM_ID, 'name': '相似度(音频)', 'weight': 1.0}]


def make_svc(repo):
    svc = TestCaseCrudService()
    svc.repo = repo
    return svc


# ============================================================
# 验收项 1：建/改用例整体评估音频维度不再 400，落库成功
# ============================================================

class TestOverallAudioDimensionAccepted:

    def test_create_overall_audio_dimension_persisted(self, audio_capability_armed):
        repo = FakeRepo()
        res = make_svc(repo).create({
            'name': 'INT-173 整体评估音频维度',
            'group_id': 'g1',
            'config': two_round_config(audio_overall_dims()),
        })

        assert res['success'], res
        assert res.get('code') == 201, res
        # 落库载荷含整体评估音频维度
        assert repo.created_payload is not None
        assert repo.created_payload['config']['dimensions'] == audio_overall_dims()
        assert repo.committed
        # 旧校验的维度参数查询不再被建用例路径调用
        assert audio_capability_armed.dimension_param_calls == []

    def test_update_overall_audio_dimension_persisted(self, audio_capability_armed):
        tc = FakeTC('c1', two_round_config(
            [{'id': PLAIN_DIM_ID, 'name': '准确率', 'weight': 1.0}]))
        repo = FakeRepo(tc)

        res = make_svc(repo).update('c1', {
            'config': two_round_config(audio_overall_dims()),
        })

        assert res['success'], res
        assert tc.config['dimensions'] == audio_overall_dims()
        assert len(tc.config['rounds']) == 2
        assert repo.committed
        assert audio_capability_armed.dimension_param_calls == []

    def test_round_level_audio_dimensions_still_allowed(self, audio_capability_armed):
        """逐轮评估（rounds[].evaluation.dimensions）音频维度始终允许。"""
        cfg = two_round_config([])
        for rnd in cfg['rounds']:
            rnd['evaluation']['dimensions'] = audio_overall_dims()
        cfg.pop('dimensions')

        repo = FakeRepo()
        res = make_svc(repo).create({
            'name': 'INT-173 逐轮音频维度',
            'group_id': 'g1',
            'config': cfg,
        })

        assert res['success'], res
        rounds = repo.created_payload['config']['rounds']
        assert [d['id'] for d in rounds[0]['evaluation']['dimensions']] == [AUDIO_DIM_ID]
        assert [d['id'] for d in rounds[1]['evaluation']['dimensions']] == [AUDIO_DIM_ID]
        assert audio_capability_armed.dimension_param_calls == []


def test_helper_deleted_from_shared_helpers():
    """helper 确已删除（规格：shared/utils/testcase_helpers.py 整段删除）。"""
    assert not hasattr(common, 'validate_multi_round_audio_dimensions')


# ============================================================
# 真库落库取证（进程级临时 sqlite，teardown 清理本卡数据）
# ============================================================

os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int173_unit_') + '/unit.db')

_INT173_CASE_NAME = 'INT-173 真库落库取证'


class TestRealDbPersistence:
    """真库落库取证：create 返回 UUID 主键，回读/清理按本卡唯一用例名定位。"""

    def setup_method(self):
        from shared.models.database import init_db
        from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup
        from shared.models.database import Base, get_engine

        init_db(pool_size=2)
        # INT-463：create 经 group_id 直传路径会回查分组可见性，需建 test_case_groups 表
        Base.metadata.create_all(bind=get_engine(), tables=[TestCase.__table__, TestCaseGroup.__table__])

    def teardown_method(self):
        from shared.models.database import get_db_session, remove_db_session
        from task_service.infrastructure.persistence.models import TestCase

        session = get_db_session()
        try:
            session.query(TestCase).filter_by(name=_INT173_CASE_NAME).delete()
            session.commit()
        finally:
            remove_db_session()

    def test_create_overall_audio_dimension_real_row(self, audio_capability_armed):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        svc = TestCaseCrudService()
        svc.repo = testcase_repository
        res = svc.create({
            'name': _INT173_CASE_NAME,
            'group_id': 'g1',
            'config': two_round_config(audio_overall_dims()),
        })

        assert res['success'], res
        # 回读取证：真实 ORM 行 config 持久化整体评估音频维度
        from shared.models.database import get_db_session, remove_db_session
        from task_service.infrastructure.persistence.models import TestCase

        session = get_db_session()
        try:
            row = session.query(TestCase).filter_by(name=_INT173_CASE_NAME).one_or_none()
        finally:
            remove_db_session()
        assert row is not None, '落库后应能回读'
        assert row.config['dimensions'] == audio_overall_dims()
        assert len(row.config['rounds']) == 2
        assert audio_capability_armed.dimension_param_calls == []
