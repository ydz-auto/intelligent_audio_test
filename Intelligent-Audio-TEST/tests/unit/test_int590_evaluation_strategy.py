# -*- coding: utf-8 -*-
"""INT-590 专项：评估策略实体（整体评估维度+全局背景噪声 抽为可复用策略）。

覆盖验收 1~4：
1. 策略 CRUD 全链路可用（创建→编辑→启用禁用→删除保护），字段完整落库
   无丢失（含 round_scope/llmJudgeConfig 回显不丢）
2. 用例可引用策略并覆盖单个字段；覆盖字段与策略字段合并后正确落库
3. 删除被引用策略被拒绝并返回引用数
4. 策略列表返回关联用例计数
5. 现有用例数据迁移后无丢失（评估字段兼容）——经 create/update 不动既有
   config.dimensions/background_noise 断言
6. 网关 TestCaseDimensionItem 声明 round_scope/llmJudgeConfig（extra='allow'），
   列表/详情响应完整回显

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int193 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

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
    # 前后都清：进程级共享 SQLite，前序套件可能残留 TestCase 行
    _cleanup_tables()
    yield
    _cleanup_tables()


# ---------- 策略 CRUD（验收1） ----------

class TestEvaluationStrategyCrud:
    """策略 CRUD 全链路（创建→编辑→启用禁用→删除）。"""

    def test_create_update_delete_roundtrip(self):
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )

        config = {
            'dimensions': [
                {'id': 1, 'name': '主维度', 'weight': 50, 'threshold': 60,
                 'round_scope': 'multi', 'llmJudgeConfig': {'model': 'gpt-4', 'promptTemplate': 'default'}},
                {'id': 2, 'name': '子维度', 'weight': 30, 'threshold': 70},
            ],
            'background_noise': {'audio_id': 5, 'spl': 30},
        }
        r = evaluation_strategy_crud_service.create({
            'name': 'INT590策略', 'description': '测试', 'algorithm_type': 'asr',
            'enabled': True, 'config': config,
        })
        assert r['success'] is True, r
        sid = r['data']['id']
        assert r['data']['config']['dimensions'][0]['round_scope'] == 'multi'
        assert r['data']['config']['dimensions'][0]['llmJudgeConfig'] == {'model': 'gpt-4', 'promptTemplate': 'default'}

        # 编辑：name + config 变更 + 启用禁用
        r2 = evaluation_strategy_crud_service.update(sid, {
            'name': 'INT590策略改', 'enabled': False,
            'config': {'dimensions': [{'id': 1, 'name': '主维度', 'weight': 55}]},
        })
        assert r2['success'] is True, r2
        assert r2['data']['name'] == 'INT590策略改'
        assert r2['data']['enabled'] is False
        assert r2['data']['config']['dimensions'][0]['weight'] == 55

        # 查询详情
        from task_service.application.evaluation_strategy.evaluation_strategy_query_service import (
            evaluation_strategy_query_service,
        )
        r3 = evaluation_strategy_query_service.get_strategy(sid)
        assert r3['success'] is True, r3
        assert r3['data']['name'] == 'INT590策略改'

        # 删除（未被引用）
        r4 = evaluation_strategy_crud_service.delete(sid)
        assert r4['success'] is True, r4

        # 删除后详情 404
        r5 = evaluation_strategy_query_service.get_strategy(sid)
        assert r5['success'] is False and r5['code'] == 404

    def test_create_duplicate_name_conflict(self):
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )
        config = {'dimensions': [], 'background_noise': {}}
        r1 = evaluation_strategy_crud_service.create({'name': '重名策略', 'config': config})
        assert r1['success'] is True, r1
        r2 = evaluation_strategy_crud_service.create({'name': '重名策略', 'config': config})
        assert r2['success'] is False and r2['code'] == 409, r2

    def test_create_missing_fields_rejected(self):
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )
        assert evaluation_strategy_crud_service.create({'config': {}})['code'] == 400
        assert evaluation_strategy_crud_service.create({'name': 'x'})['code'] == 400


# ---------- 用例引用策略 + 覆盖（验收2） ----------

class TestTestCaseStrategyReference:
    """用例引用策略 + 覆盖语义（写时物化）。"""

    def _create_strategy(self, name='INT590引用策略'):
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )
        config = {
            'dimensions': [
                {'id': 1, 'name': '主维度', 'weight': 50, 'threshold': 60,
                 'round_scope': 'multi', 'llmJudgeConfig': {'model': 'gpt-4'}},
                {'id': 2, 'name': '子维度', 'weight': 30, 'threshold': 70},
            ],
            'background_noise': {'audio_id': 5, 'spl': 30},
        }
        r = evaluation_strategy_crud_service.create({'name': name, 'config': config})
        assert r['success'] is True, r
        return r['data']['id']

    def _create_group(self):
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        import uuid
        gid = str(uuid.uuid4())
        testcase_repository.create_group(gid, 'INT590组')
        return gid

    def test_case_create_with_strategy_and_override(self):
        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        sid = self._create_strategy()
        gid = self._create_group()

        # 用例引用策略 + 覆盖单字段（weight 覆盖，其他继承）
        r = testcase_crud_service.create({
            'name': '策略用例1', 'group_id': gid, 'algorithm_type': 'asr',
            'strategy_id': sid,
            'strategy_overrides': {
                'dimensions': [{'id': 1, 'weight': 80}],
                'background_noise': {'audio_id': 99, 'spl': 45},
            },
        })
        assert r['success'] is True, r
        tc_id = r['data']['id']

        detail = testcase_crud_service.get_testcase_detail(tc_id)
        assert detail['success'] is True, detail
        d = detail['data']
        # 策略引用落库
        assert d['strategy_id'] == sid
        assert d['strategy_overrides'] == {
            'dimensions': [{'id': 1, 'weight': 80}],
            'background_noise': {'audio_id': 99, 'spl': 45},
        }
        # 解析结果写回 config.dimensions / config.background_noise
        resolved_dims = d['config'].get('dimensions')
        assert resolved_dims is not None, d['config']
        dim1 = next(x for x in resolved_dims if x.get('id') == 1)
        assert dim1['weight'] == 80            # 覆盖生效
        assert dim1['threshold'] == 60          # 未覆盖继承策略
        assert dim1['llmJudgeConfig'] == {'model': 'gpt-4'}  # 继承策略
        dim2 = next(x for x in resolved_dims if x.get('id') == 2)
        assert dim2['weight'] == 30            # 未覆盖维度整体继承
        assert d['config']['background_noise'] == {'audio_id': 99, 'spl': 45}  # 整块替换

    def test_case_update_override_and_clear(self):
        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        sid = self._create_strategy()
        gid = self._create_group()

        r = testcase_crud_service.create({
            'name': '策略用例2', 'group_id': gid, 'strategy_id': sid,
            'strategy_overrides': {'dimensions': [{'id': 2, 'threshold': 88}]},
        })
        assert r['success'] is True, r
        tc_id = r['data']['id']

        # 更新覆盖字段：strategy_overrides 为完整快照语义（整块替换），
        # 新 overrides 仅覆盖 weight，threshold 回落策略底值 70
        r2 = testcase_crud_service.update(tc_id, {
            'name': '策略用例2改',
            'strategy_overrides': {'dimensions': [{'id': 2, 'weight': 99}]},
        })
        assert r2['success'] is True, r2
        detail = testcase_crud_service.get_testcase_detail(tc_id)
        dim2 = next(x for x in detail['data']['config'].get('dimensions', []) if x.get('id') == 2)
        assert dim2['weight'] == 99
        assert dim2['threshold'] == 70  # 策略底值（新 overrides 整块替换，未覆盖字段回落）

        # 显式清空引用（空字符串）：保留 config 快照，引用列清空
        r3 = testcase_crud_service.update(tc_id, {'strategy_id': ''})
        assert r3['success'] is True, r3
        detail2 = testcase_crud_service.get_testcase_detail(tc_id)
        assert detail2['data']['strategy_id'] is None
        assert detail2['data']['strategy_overrides'] is None
        # config 快照保留（P1 不回灌）
        assert any(x.get('id') == 2 for x in detail2['data']['config'].get('dimensions', []))

    def test_case_create_with_missing_strategy_rejected(self):
        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        gid = self._create_group()
        r = testcase_crud_service.create({
            'name': '引用不存在策略', 'group_id': gid, 'strategy_id': 'no_such_strategy',
        })
        assert r['success'] is False and r['code'] == 400, r
        assert '不存在或已删除' in r['message']

    def test_case_create_with_bad_overrides_rejected(self):
        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        sid = self._create_strategy()
        gid = self._create_group()
        r = testcase_crud_service.create({
            'name': '坏覆盖', 'group_id': gid, 'strategy_id': sid,
            'strategy_overrides': {'dimensions': [{'weight': 5}]},  # 缺 id
        })
        assert r['success'] is False and r['code'] == 400, r


# ---------- 删除保护 + 列表计数（验收3/4） ----------

class TestStrategyDeleteProtectionAndCount:
    """被引用策略不可删 + 列表返回引用数。"""

    def _create_strategy(self, name):
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )
        r = evaluation_strategy_crud_service.create({
            'name': name,
            'config': {'dimensions': [{'id': 1, 'name': 'A', 'weight': 50}], 'background_noise': {}},
        })
        assert r['success'] is True, r
        return r['data']['id']

    def _create_case(self, name, strategy_id):
        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        import uuid
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        gid = str(uuid.uuid4())
        testcase_repository.create_group(gid, f'{name}组')
        r = testcase_crud_service.create({
            'name': name, 'group_id': gid, 'strategy_id': strategy_id,
        })
        assert r['success'] is True, r
        return r['data']['id']

    def test_delete_referenced_strategy_rejected_with_count(self):
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )
        from task_service.application.evaluation_strategy.evaluation_strategy_query_service import (
            evaluation_strategy_query_service,
        )
        sid = self._create_strategy('被引用策略')
        self._create_case('引用用例A', sid)
        self._create_case('引用用例B', sid)

        # 删除被引用 → 拒绝 + 返回引用数
        r = evaluation_strategy_crud_service.delete(sid)
        assert r['success'] is False and r['code'] == 409, r
        assert r['data']['referenced_case_count'] == 2, r

        # 策略仍存在（未被删除）
        detail = evaluation_strategy_query_service.get_strategy(sid)
        assert detail['success'] is True

        # 列表返回引用数
        lst = evaluation_strategy_query_service.list_strategies(keyword='被引用')
        assert lst['success'] is True, lst
        item = lst['data']['items'][0]
        assert item['referenced_case_count'] == 2

    def test_delete_unreferenced_strategy_succeeds(self):
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )
        sid = self._create_strategy('未被引用策略')
        r = evaluation_strategy_crud_service.delete(sid)
        assert r['success'] is True, r

    def test_soft_deleted_case_not_counted(self):
        """引用计数只统计未删除用例（回收站用例不计入删除保护）。"""
        from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
            evaluation_strategy_crud_service,
        )
        from task_service.application.evaluation_strategy.evaluation_strategy_query_service import (
            evaluation_strategy_query_service,
        )
        from task_service.application.testcase.testcase_crud_service import (
            testcase_crud_service,
        )
        sid = self._create_strategy('软删引用策略')
        tc_id = self._create_case('待软删用例', sid)
        # 软删用例
        testcase_crud_service.delete(tc_id)

        detail = evaluation_strategy_query_service.get_strategy(sid)
        assert detail['data']['referenced_case_count'] == 0

        r = evaluation_strategy_crud_service.delete(sid)
        assert r['success'] is True, r


# ---------- 网关字段回显修复（验收1 后半 + 必改项） ----------

class TestTestCaseDimensionItemSchema:
    """TestCaseDimensionItem 声明 round_scope/llmJudgeConfig（extra='allow'）。"""

    def test_dimension_item_roundtrip_preserves_extra_fields(self):
        from api_gateway.schemas.testcase import TestCaseDimensionItem

        dim = TestCaseDimensionItem(
            id=1, name='主维度', weight=50, threshold=60,
            round_scope='multi', llmJudgeConfig={'model': 'gpt-4', 'promptTemplate': 'default'},
        )
        dumped = dim.model_dump()
        assert dumped['round_scope'] == 'multi'
        assert dumped['llmJudgeConfig'] == {'model': 'gpt-4', 'promptTemplate': 'default'}
        # 兼容 camelCase 输入
        dim2 = TestCaseDimensionItem.model_validate({
            'id': 2, 'name': 'B', 'roundScope': 'single',
        })
        assert dim2.round_scope == 'single'

    def test_evaluation_strategy_config_schema_roundtrip(self):
        from api_gateway.schemas.evaluation_strategy import EvaluationStrategyConfig

        cfg = EvaluationStrategyConfig.model_validate({
            'dimensions': [
                {'id': 1, 'name': 'A', 'weight': 50, 'threshold': 60,
                 'roundScope': 'multi', 'llmJudgeConfig': {'model': 'gpt-4'}},
            ],
            'background_noise': {'audio_id': 5, 'spl': 30},
        })
        dumped = cfg.model_dump(exclude_none=True)
        assert dumped['dimensions'][0]['round_scope'] == 'multi'
        assert dumped['dimensions'][0]['llmJudgeConfig'] == {'model': 'gpt-4'}
