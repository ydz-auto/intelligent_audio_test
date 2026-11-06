# -*- coding: utf-8 -*-
"""INT-604/INT-1115 验收测试（后端先行部分）：
「选择设备/API」步骤新增执行模式配置 —— 逐目标（设备/API 卡片级）并行/串行 执行。

覆盖验收标准 1（单测）：
- 混选任务创建 → 同一用例生成设备侧 + API 侧各一条 TaskCase（case×target 多行表达）；
- target_modes 保序落 Task.config；缺省/空数组 = 全目标并行（零回归）；
- 无 case_devices 旧调用派生口径不回归（单条 TaskCase、device_type 由配置形态派生）；
- 应用层幂等：同一 (task, case, 路由) 重复提交被拒（评审①补录）。

真库验证（进程级 SQLite 文件库 + 真实 task_repository / task_crud_service 单例）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_E2E_CASE_ID = 'int604-case-e2e'
_API_CASE_ID = 'int604-case-api'
_E2E_CONFIG = {'rounds': [{'audios': [{'audio_id': 1, 'playback_device_id': 7}]}]}
_API_CONFIG = {'rounds': [{'audios': [{'audio_id': 2}]}]}


@pytest.fixture(scope='module')
def db():
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase, TaskDevice, TaskAPI,
    )
    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(),
        tables=[Task.__table__, TaskCase.__table__, TestCase.__table__,
                TaskDevice.__table__, TaskAPI.__table__],
    )
    yield
    remove_db_session()


def _seed_cases():
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        for case_id, config in [(_E2E_CASE_ID, _E2E_CONFIG), (_API_CASE_ID, _API_CONFIG)]:
            if session.get(TestCase, case_id) is None:
                session.add(TestCase(id=case_id, name=case_id, config=config))
        session.commit()
    finally:
        remove_db_session()


def _create_task(case_ids, case_devices=None, config=None):
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository.create_task_with_relations(
        name='INT-604 验收任务',
        description='',
        config=config,
        algorithm_type=None,
        algorithm_params=None,
        case_ids=list(case_ids),
        device_ids=[],
        api_ids=[],
        created_by=None,
        case_devices=case_devices,
    )


def _read_task_cases(task_id):
    from task_service.infrastructure.persistence.models import TaskCase
    session = get_db_session()
    try:
        rows = session.query(TaskCase).filter(TaskCase.task_id == task_id).all()
        return sorted(
            [(row.test_case_id, row.device_type, row.device_id) for row in rows],
            key=lambda x: (x[0], x[1] or '', x[2] or ''),
        )
    finally:
        remove_db_session()


def _read_task_config(task_id):
    from task_service.infrastructure.persistence.models import Task
    session = get_db_session()
    try:
        task = session.get(Task, task_id)
        return task.config if task else None
    finally:
        remove_db_session()


def _read_task_total_cases(task_id):
    from task_service.infrastructure.persistence.models import Task
    session = get_db_session()
    try:
        task = session.get(Task, task_id)
        return task.total_cases if task else None
    finally:
        remove_db_session()


class TestMixedSelectionCreate:
    """混选前置：同一用例 × 设备+API 多目标在 TaskCase 中多行表达。"""

    def test_same_case_generates_device_and_api_rows(self, db):
        """同一用例同时选物理设备 + HTTP API → 生成两条 TaskCase（各一侧）。"""
        _seed_cases()
        task_id = _create_task(
            [_E2E_CASE_ID],
            case_devices=[
                {'case_id': _E2E_CASE_ID, 'device_type': 'physical', 'device_id': '101'},
                {'case_id': _E2E_CASE_ID, 'device_type': 'http_api', 'device_id': '202'},
            ],
        )
        rows = _read_task_cases(task_id)
        assert rows == [
            (_E2E_CASE_ID, 'http_api', '202'),
            (_E2E_CASE_ID, 'physical', '101'),
        ]
        # total_cases 按去重用例数（一个用例 × 多路由只算一条）
        assert _read_task_total_cases(task_id) == 1

    def test_mixed_task_multiple_cases_each_route(self, db):
        """多用例任务：各用例按自己的 case_devices 路由落行，未指定者按任务目标兜底。"""
        _seed_cases()
        task_id = _create_task(
            [_E2E_CASE_ID, _API_CASE_ID],
            case_devices=[
                {'case_id': _E2E_CASE_ID, 'device_type': 'physical', 'device_id': '101'},
                {'case_id': _E2E_CASE_ID, 'device_type': 'http_api', 'device_id': '202'},
            ],
        )
        rows = _read_task_cases(task_id)
        # 排序键 (case_id, device_type, device_id)：'int604-case-api' 字典序在 e2e 前
        assert rows == [
            (_API_CASE_ID, 'physical', None),  # 未指定且任务无目标 → 物理域兜底
            (_E2E_CASE_ID, 'http_api', '202'),
            (_E2E_CASE_ID, 'physical', '101'),
        ]

    def test_legacy_without_case_devices_routes_by_task_targets(self, db):
        """无 case_devices 旧调用：按任务目标展开（无目标 → 物理域兜底，不读配置）。"""
        _seed_cases()
        task_id = _create_task([_E2E_CASE_ID, _API_CASE_ID])
        rows = _read_task_cases(task_id)
        assert rows == [
            (_API_CASE_ID, 'physical', None),
            (_E2E_CASE_ID, 'physical', None),
        ]

    def test_duplicate_route_rejected(self, db):
        """应用层幂等：同一 (case, 路由) 重复提交只落一行（评审①补录）。"""
        _seed_cases()
        task_id = _create_task(
            [_E2E_CASE_ID],
            case_devices=[
                {'case_id': _E2E_CASE_ID, 'device_type': 'physical', 'device_id': '101'},
                {'case_id': _E2E_CASE_ID, 'device_type': 'physical', 'device_id': '101'},
            ],
        )
        rows = _read_task_cases(task_id)
        assert rows == [(_E2E_CASE_ID, 'physical', '101')]

    def test_duplicate_route_against_existing_rows_rejected(self, db):
        """应用层幂等：与任务内既有行同路由的提交被拒（含跨两次创建）。"""
        _seed_cases()
        task_id = _create_task(
            [_E2E_CASE_ID],
            case_devices=[
                {'case_id': _E2E_CASE_ID, 'device_type': 'physical', 'device_id': '101'},
                {'case_id': _E2E_CASE_ID, 'device_type': 'http_api', 'device_id': '202'},
            ],
        )
        # 对同一任务再次提交同路由（模拟重复调用）：不得产生第三行
        from task_service.infrastructure.persistence.task_repository import task_repository
        task_repository._add_task_relations(
            get_db_session(), task_id, [_E2E_CASE_ID], [], [], None,
            case_devices=[
                {'case_id': _E2E_CASE_ID, 'device_type': 'physical', 'device_id': '101'},
            ],
        )
        rows = _read_task_cases(task_id)
        assert rows == [
            (_E2E_CASE_ID, 'http_api', '202'),
            (_E2E_CASE_ID, 'physical', '101'),
        ]


class TestExecutionModeConfigPersistence:
    """target_modes 透传 config 落库（逐目标模式，列表保序）。"""

    def test_default_parallel_no_target_modes(self):
        """缺省：config 不含 target_modes（引擎按全并行处理，零回归）。"""
        _seed_cases()
        task_id = _create_task([_E2E_CASE_ID], config={'parallel': True})
        config = _read_task_config(task_id)
        assert config == {'parallel': True}

    def test_empty_target_modes_not_written(self, db):
        """空数组 = 全目标并行：crud 服务不写入 config（与缺省一致）。"""
        _seed_cases()
        from task_service.application.task.task_crud_service import task_crud_service
        result = task_crud_service.create({
            'name': 'INT-1115 crud 空 target_modes',
            'case_ids': [_E2E_CASE_ID],
            'target_modes': [],
        })
        assert result.get('success')
        config = _read_task_config(result['data']['id'])
        assert config is None or 'target_modes' not in (config or {})

    def test_target_modes_persisted_in_order(self):
        """混选逐目标模式保序落 config['target_modes']（设备+API 混排）。"""
        _seed_cases()
        task_id = _create_task([_E2E_CASE_ID], config={
            'target_modes': [
                {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
                {'target_type': 'device', 'target_id': 2, 'mode': 'parallel'},
                {'target_type': 'api', 'target_id': 10, 'mode': 'serial'},
            ],
        })
        config = _read_task_config(task_id)
        assert config['target_modes'] == [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
            {'target_type': 'device', 'target_id': 2, 'mode': 'parallel'},
            {'target_type': 'api', 'target_id': 10, 'mode': 'serial'},
        ]

    def test_serial_only_target_modes_persisted(self):
        """仅串行目标时同样保序落库。"""
        _seed_cases()
        task_id = _create_task([_E2E_CASE_ID], config={
            'target_modes': [
                {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
            ],
        })
        config = _read_task_config(task_id)
        assert config['target_modes'] == [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
        ]


class TestTaskCrudServiceExecutionModeMerge:
    """task_crud_service.create 显式字段与 config 合并落库（网关透传路径）。"""

    def test_target_modes_merged_into_config(self, db):
        _seed_cases()
        from task_service.application.task.task_crud_service import task_crud_service
        result = task_crud_service.create({
            'name': 'INT-1115 crud 任务',
            'case_ids': [_E2E_CASE_ID],
            'config': {'parallel': True},
            'target_modes': [
                {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
                {'target_type': 'api', 'target_id': 10, 'mode': 'parallel'},
            ],
        })
        assert result.get('success')
        task_id = result['data']['id']
        config = _read_task_config(task_id)
        assert config['target_modes'] == [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
            {'target_type': 'api', 'target_id': 10, 'mode': 'parallel'},
        ]
        assert config['parallel'] is True  # 原有 config 键保留

    def test_target_modes_without_config(self, db):
        _seed_cases()
        from task_service.application.task.task_crud_service import task_crud_service
        result = task_crud_service.create({
            'name': 'INT-1115 crud 无 config',
            'case_ids': [_E2E_CASE_ID],
            'target_modes': [
                {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
            ],
        })
        assert result.get('success')
        config = _read_task_config(result['data']['id'])
        assert config['target_modes'] == [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
        ]

    def test_no_target_modes_not_merged(self, db):
        """不带 target_modes：config 不新增键（全并行默认，零回归）。"""
        _seed_cases()
        from task_service.application.task.task_crud_service import task_crud_service
        result = task_crud_service.create({
            'name': 'INT-1115 crud 默认并行',
            'case_ids': [_E2E_CASE_ID],
            'config': {'parallel': True},
        })
        assert result.get('success')
        config = _read_task_config(result['data']['id'])
        assert config == {'parallel': True}
        assert 'target_modes' not in config
