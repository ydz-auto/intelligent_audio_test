# -*- coding: utf-8 -*-
"""INT-1760：整包导入 source_map 登记 / 查询 / 补偿（SQLite 进程内端到端）

复用 test_data_transfer_roundtrip 的夹具（临时 SQLite + 本地存储降级 +
内存 Redis + 进程内 ACL），走真实导出 → 真实导入编排 → 真实仓储，验证：
- 冲突导入（4 类实体各至少 1 条冲突）逐行核对映射与库中实际行一致；
- 未冲突导入不产生映射；
- 重复 upsert 不炸唯一键（D0 A4 第 3 条）；
- 按 source_server + source_task_id 一次取回四类映射；
- 补偿清理本批次新增映射；登记失败返回 partial（sourceMapPending）且不回滚。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from tests.integration.test_data_transfer_roundtrip import (  # noqa: F401
    _export_zip,
    _seed,
    db,
    fake_redis,
    patched_acl,
    storage_env,
)

_SERVER = 'server-A'


@pytest.fixture()
def server_id(monkeypatch):
    """固定本端服务标识，避免测试落到 hostname 回落（manifest.source）"""
    from shared.infrastructure.config import BaseConfig
    monkeypatch.setattr(BaseConfig, 'DATA_TRANSFER_SERVER_ID', _SERVER)
    return _SERVER


def _run_import(zip_path):
    from task_service.application.task.data_transfer_import_service import (
        data_transfer_import_service,
    )
    return data_transfer_import_service.execute_import(zip_path)


def _wipe_import_targets():
    """清空导入会写到的表（构造「无冲突」目标库）"""
    from shared.models.database import get_db_session
    import evaluation_service.infrastructure.persistence.models as eval_models
    import report_service.infrastructure.persistence.models as report_models
    import task_service.infrastructure.persistence.models as task_models

    session = get_db_session()
    try:
        for model in (
            task_models.TaskCherryPickRelation, task_models.TestResult,
            task_models.TaskMergeRelation, task_models.TaskTag,
            task_models.TaskAPI, task_models.TaskDevice, task_models.TaskCase,
            task_models.Task,
            eval_models.TestResultDimension,
            report_models.ReportComparisonMatrix, report_models.ReportMetricStats,
            report_models.ReportCase, report_models.ReportRawData,
            report_models.ReportSummaryMeta, report_models.ReportSummary,
            report_models.Report,
        ):
            session.query(model).delete()
        session.commit()
    finally:
        session.close()


def _all_maps():
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import DataTransferSourceMap

    session = get_db_session()
    try:
        return [(r.source_server, r.entity_type, r.source_task_id,
                 r.source_id, r.local_id)
                for r in session.query(DataTransferSourceMap)
                .order_by(DataTransferSourceMap.entity_type,
                          DataTransferSourceMap.source_id).all()]
    finally:
        session.close()


class TestConflictImportRegistersMaps:
    def test_four_entity_types_registered_with_real_local_ids(
            self, db, storage_env, patched_acl, fake_redis, server_id):
        _seed(db, storage_env)
        zip_path = _export_zip(storage_env, patched_acl, fake_redis)['zip_path']

        result = _run_import(zip_path)
        assert result['success'], result.get('message')
        remapped = result['data']['remappedIds']
        # 前提：四类实体都发生了冲突（否则本用例不成立）
        assert set(remapped) >= {'tasks', 'test_results',
                                 'test_result_dimensions', 'test_reports'}

        maps = _all_maps()
        by_type = {}
        for server, entity_type, source_task_id, source_id, local_id in maps:
            assert server == _SERVER
            by_type.setdefault(entity_type, {})[source_id] = (source_task_id, local_id)
        assert set(by_type) == {'tasks', 'test_results',
                                'test_result_dimensions', 'test_reports'}

        # 逐类核对：登记的 local_id 与统计回包 / 库中实际行一致
        assert {int(k): v for k, v in remapped['tasks'].items()} == \
            {k: v[1] for k, v in by_type['tasks'].items()}
        assert {int(k): v for k, v in remapped['test_results'].items()} == \
            {k: v[1] for k, v in by_type['test_results'].items()}
        assert {int(k): v for k, v in remapped['test_result_dimensions'].items()} == \
            {k: v[1] for k, v in by_type['test_result_dimensions'].items()}
        assert {int(k): v for k, v in remapped['test_reports'].items()} == \
            {k: v[1] for k, v in by_type['test_reports'].items()}

        # 库中真实存在这些本地行（不是凭空登记的 id）
        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from report_service.infrastructure.persistence.models import Report
        from task_service.infrastructure.persistence.models import Task, TestResult

        session = get_db_session()
        try:
            assert session.query(Task).filter(
                Task.id.in_([v[1] for v in by_type['tasks'].values()])).count() == 2
            assert session.query(TestResult).filter(
                TestResult.id.in_([v[1] for v in by_type['test_results'].values()])).count() == 2
            assert session.query(TestResultDimension).filter(
                TestResultDimension.id.in_(
                    [v[1] for v in by_type['test_result_dimensions'].values()])).count() == 1
            assert session.query(Report).filter(
                Report.id.in_([v[1] for v in by_type['test_reports'].values()])).count() == 1
        finally:
            session.close()

        # source_task_id 是 A 原始任务 id（不是本地任务 id）
        assert by_type['tasks'][1][0] == 1
        assert by_type['test_results'][100][0] == 1
        assert by_type['test_result_dimensions'][200][0] == 1
        assert by_type['test_reports'][300][0] == 1

    def test_query_by_source_task_returns_four_types(
            self, db, storage_env, patched_acl, fake_redis, server_id):
        _seed(db, storage_env)
        zip_path = _export_zip(storage_env, patched_acl, fake_redis)['zip_path']
        assert _run_import(zip_path)['success']

        from task_service.infrastructure.persistence.transfer_repository import (
            transfer_repository,
        )
        grouped = transfer_repository.fetch_source_maps_grouped(_SERVER, 1)
        assert set(grouped) == {'tasks', 'test_results',
                                'test_result_dimensions', 'test_reports'}
        assert grouped['tasks'][0]['local_id'] != 1
        assert grouped['test_reports'][0]['source_id'] == 300
        # 源任务 2：seed 只给任务 1 的结果挂了维度评分，也没有报告
        grouped2 = transfer_repository.fetch_source_maps_grouped(_SERVER, 2)
        assert set(grouped2) == {'tasks', 'test_results'}

    def test_reverse_lookup_local_to_source(
            self, db, storage_env, patched_acl, fake_redis, server_id):
        _seed(db, storage_env)
        zip_path = _export_zip(storage_env, patched_acl, fake_redis)['zip_path']
        result = _run_import(zip_path)
        assert result['success']

        from task_service.infrastructure.persistence.transfer_repository import (
            transfer_repository,
        )
        remaps = {int(k): v for k, v in result['data']['remappedIds']['test_results'].items()}
        mapping = transfer_repository.fetch_source_ids_by_local_ids(
            _SERVER, 'test_results', list(remaps.values()))
        assert mapping == {local: source for source, local in remaps.items()}
        # 缺映射的本地 id 不出现在结果里（调用方据此判「无法离线搬运」）
        assert 999999 not in mapping


class TestNoConflictImportRegistersNothing:
    def test_identity_mapping_produces_no_rows(
            self, db, storage_env, patched_acl, fake_redis, server_id):
        _seed(db, storage_env)
        zip_path = _export_zip(storage_env, patched_acl, fake_redis)['zip_path']
        _wipe_import_targets()

        result = _run_import(zip_path)
        assert result['success'], result.get('message')
        assert result['data'].get('remappedIds') in (None, {})
        assert _all_maps() == []


class TestUpsertIdempotency:
    def test_repeat_upsert_does_not_break_unique_key(
            self, db, storage_env, patched_acl, fake_redis):
        """同一 (source_server, entity_type, local_id) 重复登记 → 覆盖不报错"""
        from task_service.infrastructure.persistence.transfer_repository import (
            transfer_repository,
        )
        entries = [{'source_server': _SERVER, 'source_task_id': 1,
                    'entity_type': 'tasks', 'source_id': 1, 'local_id': 42}]
        first = transfer_repository.upsert_source_maps(entries)
        assert first['insertedCount'] == 1

        updated = [dict(entries[0], source_id=7)]
        second = transfer_repository.upsert_source_maps(updated)
        assert second['insertedCount'] == 0 and second['updatedCount'] == 1

        rows = transfer_repository.fetch_source_maps(_SERVER, 1)
        assert [(r['source_id'], r['local_id']) for r in rows] == [(7, 42)]

    def test_two_local_copies_of_one_source_id(
            self, db, storage_env, patched_acl, fake_redis):
        """同一 A 任务导入两次 → 一个 source_id 对多个 local_id（唯一键放 local 侧）"""
        from task_service.infrastructure.persistence.transfer_repository import (
            transfer_repository,
        )
        entries = [
            {'source_server': _SERVER, 'source_task_id': 1, 'entity_type': 'tasks',
             'source_id': 1, 'local_id': 11},
            {'source_server': _SERVER, 'source_task_id': 1, 'entity_type': 'tasks',
             'source_id': 1, 'local_id': 12},
        ]
        assert transfer_repository.upsert_source_maps(entries)['insertedCount'] == 2
        rows = transfer_repository.fetch_source_maps(_SERVER, 1)
        assert sorted(r['local_id'] for r in rows) == [11, 12]


class TestCompensationAndPartial:
    def test_compensation_removes_batch_maps(
            self, db, storage_env, patched_acl, fake_redis, server_id, monkeypatch):
        """登记之后才失败的步骤触发补偿 → 本批次新增映射被清理，无孤儿"""
        _seed(db, storage_env)
        zip_path = _export_zip(storage_env, patched_acl, fake_redis)['zip_path']

        import task_service.application.task.data_transfer_import_service as import_mod

        def _boom(*args, **kwargs):
            raise RuntimeError('simulated post-registration failure')

        monkeypatch.setattr(import_mod.DataTransferImportService,
                            '_publish_imported_event', staticmethod(_boom))

        result = _run_import(zip_path)
        assert result['success'] is False
        assert result['data']['compensation_errors'] == []
        assert _all_maps() == [], '补偿后不得留下本批次登记的孤儿映射'

        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task
        session = get_db_session()
        try:
            assert session.query(Task).count() == 2  # 只剩 seed 的两条
        finally:
            session.close()

    def test_registration_failure_returns_partial_without_rollback(
            self, db, storage_env, patched_acl, fake_redis, server_id, monkeypatch):
        """D0 A3 第 3 条：登记失败不回滚，返回 partial + 重放快照"""
        _seed(db, storage_env)
        zip_path = _export_zip(storage_env, patched_acl, fake_redis)['zip_path']

        import task_service.application.task.data_transfer_import_service as import_mod
        from task_service.infrastructure.persistence.transfer_repository import (
            transfer_repository,
        )

        def _fail_upsert(entries):
            raise RuntimeError('db down')

        monkeypatch.setattr(transfer_repository, 'upsert_source_maps', _fail_upsert)

        result = _run_import(zip_path)
        assert result['success'] is False
        assert result['code'] == 500
        data = result['data']
        assert data['sourceMapPending'] is True
        assert data['partial'] is True
        assert data['batchId']
        assert data['snapshotSaved'] is True
        assert data['entryCount'] > 0

        # 数据段不回滚：导入的任务仍在库里（远端/本地数据都是对的）
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task
        session = get_db_session()
        try:
            assert session.query(Task).count() == 4  # 2 seed + 2 导入
        finally:
            session.close()
        # 映射快照留在批次登记里，可重放
        from shared.utils.data_transfer_batch import transfer_batch_registry
        snapshot = transfer_batch_registry.load_source_map(data['batchId'], 'task_service')
        assert len(snapshot) == data['entryCount']
        assert {e['entity_type'] for e in snapshot} == {
            'tasks', 'test_results', 'test_result_dimensions', 'test_reports'}

    def test_rollback_import_deletes_maps_by_batch_snapshot(
            self, db, storage_env, patched_acl, fake_redis, server_id):
        """人工兜底回滚按批次快照回删映射（与任务行一起清）"""
        _seed(db, storage_env)
        zip_path = _export_zip(storage_env, patched_acl, fake_redis)['zip_path']
        result = _run_import(zip_path)
        assert result['success']
        inserted = _all_maps()
        assert inserted

        # 成功导入会销毁批次登记；模拟「已提交但登记仍在」的人工回滚场景：
        # 重新写一份批次登记（真实路径见 execute_import 段 6 的快照写入）
        from shared.models.database import get_db_session
        from shared.utils.data_transfer_batch import transfer_batch_registry
        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service,
        )
        from task_service.infrastructure.persistence.transfer_repository import (
            transfer_repository,
        )
        from task_service.infrastructure.persistence.models import Task

        session = get_db_session()
        try:
            imported_task_pks = [t.id for t in session.query(Task).all() if t.id not in (1, 2)]
        finally:
            session.close()
        batch_id = 'int1760-rollback'
        transfer_batch_registry.record(batch_id, 'task_service',
                                       {'test_tasks': imported_task_pks})
        transfer_batch_registry.record_source_map(
            batch_id, 'task_service',
            [{'source_server': _SERVER, 'source_task_id': s_task,
              'entity_type': entity, 'source_id': source, 'local_id': local}
             for (_srv, entity, s_task, source, local) in inserted])

        out = data_transfer_import_service.rollback_import(batch_id)
        assert out['success'], out.get('message')
        assert transfer_repository.fetch_source_maps(_SERVER, 1) == []
