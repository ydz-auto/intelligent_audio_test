# -*- coding: utf-8 -*-
"""INT-590 集成测试：评估策略 gRPC 全链路（服务端 servicer → 网关代理）。

覆盖验收 1~4 的全链路：
- 策略 CRUD：Create → Update（启用禁用）→ List（含 referenced_case_count）
  → Get → Delete（被引用拒绝）
- 用例引用策略：gRPC CreateTestCaseConfig 携带 strategy_id + strategy_overrides，
  task_service 写时物化合并，Detail 回显 config.dimensions 含解析后字段
- TestCaseDimensionItem 网关字段回显：round_scope/llmJudgeConfig 完整

DB：进程级 SQLite（tests/conftest.py 注入），进程内真实 gRPC server + stub 重定向。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_TABLES = None


def _ensure_db():
    init_db(pool_size=2)


def _ensure_tables():
    _ensure_db()
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            TestCase, Tag, TagCategory, TestCaseGroup, TestCaseTag, Favorite,
            EvaluationStrategy,
        )
        _TABLES = [t.__table__ for t in (
            TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag, Favorite,
            EvaluationStrategy,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables():
    session = get_db_session()
    try:
        for table in _TABLES:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture(autouse=True)
def _int590_db():
    _ensure_tables()
    _cleanup_tables()
    yield
    _cleanup_tables()


@pytest.fixture(scope='module')
def grpc_mesh():
    """task_service 进程内真实 gRPC server（EvaluationStrategy + TestCaseConfig）。"""
    from concurrent import futures

    import grpc

    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor,
        server_log_interceptor,
    )

    def _new_server():
        return grpc.server(
            futures.ThreadPoolExecutor(max_workers=8),
            interceptors=[server_db_scope_interceptor, server_log_interceptor])

    from shared.proto import task_service_pb2_grpc as task_grpc
    from task_service.interfaces.grpc.evaluation_strategy_config import (
        EvaluationStrategyServiceServicer,
    )
    from task_service.interfaces.grpc.testcase_config import (
        TestCaseConfigServiceServicer,
    )
    from task_service.interfaces.grpc.task_data_service import (
        TaskDataServiceServicer,
    )

    task_server = _new_server()
    task_grpc.add_EvaluationStrategyServiceServicer_to_server(
        EvaluationStrategyServiceServicer(), task_server)
    task_grpc.add_TestCaseConfigServiceServicer_to_server(
        TestCaseConfigServiceServicer(), task_server)
    # 建分组走 TaskDataService.CreateTestCaseGroup（INT-590 集成链路依赖）
    task_grpc.add_TaskDataServiceServicer_to_server(
        TaskDataServiceServicer(), task_server)
    task_port = task_server.add_insecure_port('[::]:0')
    task_server.start()

    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    mp = pytest.MonkeyPatch()
    mp.setattr(channels_mod, 'TASK_GRPC_ADDR', f'localhost:{task_port}')

    _channel_caches = [channels_mod._get_task_channel.cache_clear]
    _stub_caches = [
        stubs_mod.get_evaluation_strategy_service_stub.cache_clear,
        stubs_mod.get_testcase_config_service_stub.cache_clear,
        stubs_mod.get_task_data_service_stub.cache_clear,
    ]
    for clear in _channel_caches + _stub_caches:
        clear()

    yield {'task_port': task_port}

    for clear in _channel_caches + _stub_caches:
        clear()


def _json_dumps(data):
    return json.dumps(data, ensure_ascii=False, default=str)


class TestEvaluationStrategyGrpcChain:
    """评估策略 gRPC 全链路（服务端 servicer → 网关代理）。"""

    def test_strategy_crud_and_delete_protection(self, grpc_mesh):
        from shared.clients.grpc_clients import get_evaluation_strategy_service_stub
        from shared.proto import task_service_pb2 as task_pb

        stub = get_evaluation_strategy_service_stub()

        # Create
        resp = stub.CreateEvaluationStrategy(task_pb.CreateEvaluationStrategyRequest(
            data=_json_dumps({
                'name': 'INT590集成策略',
                'description': '集成测试',
                'algorithm_type': 'asr',
                'enabled': True,
                'config': {
                    'dimensions': [
                        {'id': 1, 'name': '主维度', 'weight': 50, 'threshold': 60,
                         'round_scope': 'multi', 'llmJudgeConfig': {'model': 'gpt-4'}},
                    ],
                    'background_noise': {'audio_id': 5, 'spl': 30},
                },
            })
        ))
        assert resp.success, resp.message
        created = json.loads(resp.data)
        sid = created['id']
        assert created['config']['dimensions'][0]['round_scope'] == 'multi'
        assert created['config']['dimensions'][0]['llmJudgeConfig'] == {'model': 'gpt-4'}

        # Update（启用禁用 + 名称）
        resp = stub.UpdateEvaluationStrategy(task_pb.UpdateEvaluationStrategyRequest(
            strategy_id=sid,
            data=_json_dumps({'name': 'INT590集成策略改', 'enabled': False}),
        ))
        assert resp.success, resp.message
        updated = json.loads(resp.data)
        assert updated['name'] == 'INT590集成策略改'
        assert updated['enabled'] is False

        # Get
        resp = stub.GetEvaluationStrategy(task_pb.GetEvaluationStrategyRequest(
            strategy_id=sid))
        assert resp.success, resp.message
        detail = json.loads(resp.data)
        assert detail['id'] == sid
        assert detail['referenced_case_count'] == 0

        # Delete（未被引用）
        resp = stub.DeleteEvaluationStrategy(task_pb.DeleteEvaluationStrategyRequest(
            strategy_id=sid))
        assert resp.success, resp.message

        # 删除后 Get 404（data 含 code 供网关提取）
        resp = stub.GetEvaluationStrategy(task_pb.GetEvaluationStrategyRequest(
            strategy_id=sid))
        assert not resp.success
        assert json.loads(resp.data).get('code') == 404

    def test_case_reference_strategy_via_grpc(self, grpc_mesh):
        """gRPC 创建用例携带 strategy_id + overrides，解析结果回显 config.dimensions。"""
        from shared.clients.grpc_clients import (
            get_evaluation_strategy_service_stub,
            get_testcase_config_service_stub,
        )
        from shared.proto import task_service_pb2 as task_pb

        strategy_stub = get_evaluation_strategy_service_stub()
        case_stub = get_testcase_config_service_stub()

        # 建策略
        resp = strategy_stub.CreateEvaluationStrategy(task_pb.CreateEvaluationStrategyRequest(
            data=_json_dumps({
                'name': 'INT590用例引用策略',
                'config': {
                    'dimensions': [
                        {'id': 1, 'name': '主维度', 'weight': 50, 'threshold': 60,
                         'round_scope': 'multi', 'llmJudgeConfig': {'model': 'gpt-4'}},
                    ],
                    'background_noise': {'audio_id': 5, 'spl': 30},
                },
            })
        ))
        assert resp.success, resp.message
        sid = json.loads(resp.data)['id']

        # 建分组（用例必需）
        from shared.clients.grpc_clients import get_task_data_service_stub
        task_data_stub = get_task_data_service_stub()
        group_id = 'INT590_GRPC_GROUP'
        resp = task_data_stub.CreateTestCaseGroup(task_pb.CreateTestCaseGroupRequest(
            name=group_id, group_id=group_id))
        assert resp.success, resp.message

        # 建用例引用策略 + 覆盖
        resp = case_stub.CreateTestCaseConfig(task_pb.CreateTestCaseConfigRequest(
            data=_json_dumps({
                'name': 'INT590集成引用用例',
                'group_id': group_id,
                'algorithm_type': 'asr',
                'strategy_id': sid,
                'strategy_overrides': {
                    'dimensions': [{'id': 1, 'weight': 80}],
                    'background_noise': {'audio_id': 99, 'spl': 45},
                },
            })
        ))
        assert resp.success, resp.message
        tc_id = json.loads(resp.data)['id']

        # 详情回显：strategy_id + 解析后 config.dimensions
        resp = case_stub.GetTestCaseDetail(task_pb.GetTestCaseDetailRequest(tc_id=tc_id))
        assert resp.success, resp.message
        detail = json.loads(resp.data)
        assert detail['strategy_id'] == sid
        dim1 = next(x for x in detail['config']['dimensions'] if x.get('id') == 1)
        assert dim1['weight'] == 80          # 覆盖生效
        assert dim1['threshold'] == 60        # 继承策略
        assert dim1['llmJudgeConfig'] == {'model': 'gpt-4'}  # 继承策略
        assert detail['config']['background_noise'] == {'audio_id': 99, 'spl': 45}

    def test_delete_referenced_strategy_rejected_via_grpc(self, grpc_mesh):
        from shared.clients.grpc_clients import (
            get_evaluation_strategy_service_stub,
            get_task_data_service_stub,
            get_testcase_config_service_stub,
        )
        from shared.proto import task_service_pb2 as task_pb

        strategy_stub = get_evaluation_strategy_service_stub()
        case_stub = get_testcase_config_service_stub()

        resp = strategy_stub.CreateEvaluationStrategy(task_pb.CreateEvaluationStrategyRequest(
            data=_json_dumps({
                'name': 'INT590被引用集成策略',
                'config': {'dimensions': [{'id': 1, 'name': 'A'}], 'background_noise': {}},
            })
        ))
        assert resp.success, resp.message
        sid = json.loads(resp.data)['id']

        group_id = 'INT590_GRPC_GROUP_2'
        task_data_stub = get_task_data_service_stub()
        resp = task_data_stub.CreateTestCaseGroup(task_pb.CreateTestCaseGroupRequest(
            name=group_id, group_id=group_id))
        assert resp.success, resp.message

        resp = case_stub.CreateTestCaseConfig(task_pb.CreateTestCaseConfigRequest(
            data=_json_dumps({
                'name': '引用用例', 'group_id': group_id, 'strategy_id': sid,
            })
        ))
        assert resp.success, resp.message

        # 删除被引用策略 → 拒绝 + referenced_case_count
        resp = strategy_stub.DeleteEvaluationStrategy(task_pb.DeleteEvaluationStrategyRequest(
            strategy_id=sid))
        assert not resp.success
        data = json.loads(resp.data)
        assert data.get('code') == 409
        assert data.get('referenced_case_count') == 1

        # 列表返回引用数
        resp = strategy_stub.ListEvaluationStrategies(task_pb.ListEvaluationStrategiesRequest(
            keyword='被引用'))
        assert resp.success, resp.message
        lst = json.loads(resp.data)
        item = lst['items'][0]
        assert item['id'] == sid
        assert item['referenced_case_count'] == 1

    def test_list_filters_and_pagination(self, grpc_mesh):
        from shared.clients.grpc_clients import get_evaluation_strategy_service_stub
        from shared.proto import task_service_pb2 as task_pb

        stub = get_evaluation_strategy_service_stub()
        for name in ('INT590筛选一', 'INT590筛选二', '其他策略'):
            resp = stub.CreateEvaluationStrategy(task_pb.CreateEvaluationStrategyRequest(
                data=_json_dumps({
                    'name': name, 'algorithm_type': 'asr',
                    'config': {'dimensions': [], 'background_noise': {}},
                })
            ))
            assert resp.success, resp.message

        # keyword 过滤
        resp = stub.ListEvaluationStrategies(task_pb.ListEvaluationStrategiesRequest(
            keyword='INT590筛选'))
        assert resp.success, resp.message
        lst = json.loads(resp.data)
        assert lst['total'] == 2
        assert {i['name'] for i in lst['items']} == {'INT590筛选一', 'INT590筛选二'}

        # algorithm_type 过滤
        resp = stub.ListEvaluationStrategies(task_pb.ListEvaluationStrategiesRequest(
            algorithm_type='asr'))
        lst = json.loads(resp.data)
        assert lst['total'] == 3

        # 分页
        resp = stub.ListEvaluationStrategies(task_pb.ListEvaluationStrategiesRequest(
            per_page=1, page=1))
        lst = json.loads(resp.data)
        assert lst['per_page'] == 1
        assert lst['pages'] == 3
