# -*- coding: utf-8 -*-
"""任务数据导入导出 —— 进程内端到端 roundtrip 集成测试（INT-25）

不启动任何微服务：
- SQLite 临时库（engine 由测试直接装配，绕过 init_db 的 Postgres 连接池参数）
- 存储走本地降级根目录（OSS 不可用 → STORAGE_LOCAL_ROOT）
- 跨服务 gRPC 段以「进程内直调真实应用服务」的假 ACL 替身接入
- Redis 以内存假 RedisStore 替身（批次登记语义不变）

覆盖：导出包结构 → 同库导入（全量 ID 冲突 → 自动重映射）→ 15 表外键一致性 →
文件路径重映射 → 维度导入段失败注入 → 全量补偿回滚。
"""
import json
import os
import zipfile

# BaseConfig 在 import 时求值；测试进程无 .env，先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest


@pytest.fixture(scope='module')
def storage_env(tmp_path_factory):
    """本地存储根 + 导出临时目录（BaseConfig 类属性直接覆盖，env 已晚于 import）"""
    from shared.infrastructure.config import BaseConfig
    root = tmp_path_factory.mktemp('dt_env')
    BaseConfig.STORAGE_LOCAL_ROOT = str(root / 'storage_local')
    BaseConfig.DATA_TRANSFER_TMP_DIR = str(root / 'data_transfer')
    BaseConfig.STORAGE_FALLBACK_ENABLED = True
    return root


@pytest.fixture()
def db(monkeypatch, storage_env):
    """SQLite 临时库：直接装配 engine 到全局 scoped_session，建全部模型表。
    同时短路 OSS 探测（存储直走本地降级，避免测试进程逐桶探测超时）。
    SQLite 下把 BigInteger 编译为 INTEGER，使 BIGINT 主键可作为 rowid 别名自增
    （生产为 Postgres BIGSERIAL，无此问题）。"""
    import tempfile

    from sqlalchemy import create_engine

    import shared.models.database as database
    from shared.infrastructure.storage import storage

    # 确保三个服务的模型都注册进 Base.metadata
    import task_service.infrastructure.persistence.models  # noqa: F401
    import evaluation_service.infrastructure.persistence.models  # noqa: F401
    import report_service.infrastructure.persistence.models  # noqa: F401

    monkeypatch.setattr(storage, '_use_oss', lambda: False)

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield database
    database.remove_db_session()
    engine.dispose()
    os.remove(path)


from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    # SQLite 下 BIGINT 主键不是 rowid 别名、无法自增；编译为 INTEGER 修复
    # （生产为 Postgres BIGSERIAL，无此问题）
    return 'INTEGER'


class _FakeRedisStore:
    """内存版 RedisStore（save_task/load_task/remove_fields/delete_task 语义一致）"""

    def __init__(self, *a, **k):
        self._data = {}

    def save_task(self, key, fields, ttl_seconds=86400):
        self._data.setdefault(key, {}).update(fields)

    def load_task(self, key):
        return dict(self._data.get(key, {}))

    def remove_fields(self, key, *fields):
        entry = self._data.get(key)
        if entry is None or not fields:
            return
        for f in fields:
            entry.pop(f, None)
        if not entry:  # 与 Redis HDEL 语义一致：最后一个字段删除后整键消失
            self._data.pop(key, None)

    def delete_task(self, key):
        self._data.pop(key, None)


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = _FakeRedisStore()
    import shared.utils.data_transfer_batch as batch_mod
    import shared.utils.redis_pubsub as pubsub_mod
    import task_service.application.task.import_progress_reporter as reporter_mod

    class _FakePubSub:
        """不联网的 RedisPubSub 替身（publish 静默）"""

        def __init__(self, *a, **k):
            pass

        def publish(self, *a, **k):
            pass

    class _FakeEventBus:
        """不联网的 EventBus 替身（publish 静默）"""

        def __init__(self, *a, **k):
            pass

        def publish(self, *a, **k):
            pass

    monkeypatch.setattr(batch_mod, 'RedisStore', lambda *a, **k: fake)
    monkeypatch.setattr(pubsub_mod, 'RedisStore', lambda *a, **k: fake)
    # 模块导入时已实例化的单例：替换其内部 store
    monkeypatch.setattr(batch_mod.transfer_batch_registry, '_store', fake)
    # 进度报告器：发布与快照全部走内存替身（避免真实 Redis 连接重试拖慢测试）
    # INT-69：进度发布改走 EventBus TASK_EVENTS/import_progress，替换 reporter 模块内绑定
    monkeypatch.setattr(reporter_mod, 'EventBus', _FakeEventBus)
    monkeypatch.setattr(reporter_mod, 'RedisStore', lambda *a, **k: fake)
    # 导入成功事件（EventBus.publish 内部吞异常，但仍会尝试真实连接）
    import task_service.application.task.data_transfer_import_service as import_mod
    monkeypatch.setattr(import_mod, 'EventBus', _FakeEventBus)
    return fake


class _InProcEvalAcl:
    """维度段 ACL 替身：进程内直调 evaluation_service 真实应用服务"""

    def export_dimensions_for_tasks(self, result_ids):
        from evaluation_service.application.dimension_transfer_service import (
            dimension_transfer_service)
        r = dimension_transfer_service.export_dimensions_for_tasks(result_ids)
        assert r['success'], r.get('message')
        return r['data']

    def import_dimensions(self, rows, result_id_mapping, batch_id):
        from evaluation_service.application.dimension_transfer_service import (
            dimension_transfer_service)
        r = dimension_transfer_service.import_dimensions(rows, result_id_mapping, batch_id)
        assert r['success'], r.get('message')
        return r['data']

    def rollback_dimension_import(self, batch_id):
        from evaluation_service.application.dimension_transfer_service import (
            dimension_transfer_service)
        r = dimension_transfer_service.rollback_dimension_import(batch_id)
        assert r['success'], r.get('message')
        return r['data']


class _InProcReportAcl:
    """报告段 ACL 替身：进程内直调 report_service 真实应用服务"""

    def export_reports_for_tasks(self, task_ids):
        from report_service.application.report_transfer_service import report_transfer_service
        r = report_transfer_service.export_reports_for_tasks(task_ids)
        assert r['success'], r.get('message')
        return r['data']

    def import_reports(self, tables_rows, task_id_mapping, batch_id):
        from report_service.application.report_transfer_service import report_transfer_service
        r = report_transfer_service.import_reports(tables_rows, task_id_mapping, batch_id)
        assert r['success'], r.get('message')
        return r['data']

    def rollback_report_import(self, batch_id):
        from report_service.application.report_transfer_service import report_transfer_service
        r = report_transfer_service.rollback_report_import(batch_id)
        assert r['success'], r.get('message')
        return r['data']


@pytest.fixture()
def patched_acl(monkeypatch):
    import task_service.application.task.data_transfer_export_service as export_mod
    import task_service.application.task.data_transfer_import_service as import_mod
    monkeypatch.setattr(export_mod, 'evaluation_transfer_acl_repository', _InProcEvalAcl())
    monkeypatch.setattr(export_mod, 'report_transfer_acl_repository', _InProcReportAcl())
    monkeypatch.setattr(import_mod, 'evaluation_transfer_acl_repository', _InProcEvalAcl())
    monkeypatch.setattr(import_mod, 'report_transfer_acl_repository', _InProcReportAcl())


def _seed(db, storage_env):
    """写入源数据：两个已完成任务 + 关联 + 结果 + 维度评分 + 报告族 + 用例引用文件"""
    from datetime import datetime

    from shared.infrastructure.storage import storage
    from shared.models.database import get_db_session
    from evaluation_service.infrastructure.persistence.models import (
        Dimension,
        TestResultDimension,
    )
    from report_service.infrastructure.persistence.models import (
        Report,
        ReportCase,
        ReportSummary,
    )
    from task_service.infrastructure.persistence.models import (
        Task,
        TaskAPI,
        TaskCase,
        TaskDevice,
        TaskMergeRelation,
        TaskTag,
        TestCase,
        TestResult,
    )

    now = datetime.now()

    def _task(tid, name):
        return Task(id=tid, name=name, description='seed', status='completed',
                    config={}, algorithm_type='translation', algorithm_params={},
                    total_cases=2, completed_cases=2, failed_cases=0,
                    created_by_user_id=None, created_at=now, updated_at=now,
                    deleted=False, reevaluation_count=0, execution_source='manual')

    case_file_key = '1/tc_001/devSN001/result_data.json'
    stored = storage.save_bytes(json.dumps({'score': 1}).encode(),
                                'case_result', case_file_key, content_type='application/json')
    ref_key = 'tc_001/round_1.json'
    ref_stored = storage.save_bytes(json.dumps({'ref': [1, 2]}).encode(),
                                    'ref_params', ref_key, content_type='application/json')

    session = get_db_session()
    try:
        session.add_all([
            _task(1, '翻译测试-0910'), _task(2, '翻译测试-0911'),
            TaskCase(id=10, task_id=1, test_case_id='tc_001', status='completed',
                     execution_status='completed', evaluation_status='completed',
                     device_type='physical', device_id='77', lab_id=5, created_at=now),
            TaskCase(id=11, task_id=2, test_case_id='tc_001', status='completed',
                     execution_status='completed', evaluation_status='completed', created_at=now),
            TaskDevice(id=20, task_id=1, device_id=77),
            TaskAPI(id=30, task_id=1, api_id=88),
            TaskTag(id=40, task_id=1, tag_id=9),
            TaskMergeRelation(id=50, merged_task_id=1, source_task_id=2,
                              source_result_count=2, created_at=now),
            TestCase(id='tc_001', name='用例一', config={
                'rounds': [{'roundNumber': 1, 'audios': [{'audio_id': 'a1'}]}]},
                reference_params=[{'round_number': 1, 'reference_params_path': ref_stored}],
                created_at=now, updated_at=now, deleted=False),
            TestResult(id=100, task_id=1, test_case_id='tc_001', device_id=77, api_id=88,
                       algorithm_type='translation', execution_status='completed',
                       result_data={'score': 1}, result_data_path=stored, created_at=now),
            TestResult(id=101, task_id=2, test_case_id='tc_001', device_id=77, api_id=88,
                       algorithm_type='translation', execution_status='completed',
                       result_data={'score': 1}, result_data_path=None, created_at=now),
            Dimension(id=1, name='准确率', dimension_type='main', type='auto', result_type=1,
                      weight=1, sort_order=0, estimated_exec_time=10,
                      statistic_method='average', agg_denominator='case',
                      status=True, deleted=False, created_at=now, updated_at=now),
            TestResultDimension(id=200, test_result_id=100, dimension_id=1,
                                algorithm_type='translation', round_number=0,
                                dimension_value=1.0, score=90.0, evaluation_status='completed',
                                created_at=now),
            Report(id=300, name='报告一', type='standard', task_id=1, status='completed',
                   deleted=False, created_at=now, updated_at=now),
            ReportSummary(id=301, report_id=300, task_ids=[1], created_at=now, updated_at=now),
            ReportCase(id=302, report_id=300, test_case_id='tc_001', name='用例一',
                       created_at=now, updated_at=now),
        ])
        session.commit()
    finally:
        session.close()

    return {
        'result_file_key': case_file_key,
        'ref_file_key': ref_key,
    }


def _export_zip(storage_env, patched_acl, fake_redis, task_ids=(1, 2)):
    from task_service.application.task.data_transfer_export_service import (
        data_transfer_export_service,
    )
    result = data_transfer_export_service.export_tasks(
        list(task_ids), {'include_ref_params': True, 'include_audios': False})
    assert result['success'], result.get('message')
    return result['data']


class TestRoundtrip:
    def test_export_package_structure(self, db, storage_env, patched_acl, fake_redis):
        seeded = _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)
        zip_path = data['zip_path']
        assert os.path.isfile(zip_path)

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            db_files = {n for n in names if n.startswith('db/')}
            assert len(db_files) == 15
            manifest = json.loads(zf.read('manifest.json'))
            assert manifest['version'] == '1.0'
            assert manifest['stats']['taskCount'] == 2
            assert manifest['stats']['resultCount'] == 2
            assert manifest['stats']['dimensionCount'] == 1
            assert manifest['stats']['reportCount'] == 1
            assert manifest['stats']['fileCount'] == data['file_count'] == 2  # 两个结果文件
            assert manifest['options'] == {'includeRefParams': True, 'includeAudios': False}
            # 结果文件按导出时 task_id 相对路径归档
            assert 'files/case_results/1/tc_001/devSN001/result_data.json' in names
            assert 'files/ref_params/tc_001/round_1.json' in names
            # 维度定义快照
            assert json.loads(zf.read('meta/dimensions.json'))[0]['name'] == '准确率'
        assert seeded

    def test_import_same_db_full_remap(self, db, storage_env, patched_acl, fake_redis):
        """同库导入：全部主键冲突 → 自动重映射；15 表外键与文件路径一致"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)

        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from report_service.infrastructure.persistence.models import (
            Report,
            ReportCase,
            ReportSummary,
        )
        from task_service.infrastructure.persistence.models import (
            Task,
            TaskAPI,
            TaskCase,
            TaskDevice,
            TaskMergeRelation,
            TaskTag,
            TestResult,
        )

        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service,
        )
        result = data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'], result.get('message')
        stats = result['data']

        # 统计：2 任务 / 2 结果 / 1 维度评分 / 1 报告 / 2 文件
        assert stats['importedTasks'] == 2
        assert stats['importedResults'] == 2
        assert stats['importedDimensions'] == 1
        assert stats['importedReports'] == 1
        assert stats['importedFiles'] >= 2
        # 全量冲突 → tasks 全部重映射
        remaps = stats['remappedIds']['tasks']
        assert sorted(map(int, remaps)) == [1, 2]
        assert all(int(old) != new for old, new in remaps.items())

        session = get_db_session()
        try:
            tasks = {t.id: t for t in session.query(Task).all()}
            new_ids = set(remaps.values())
            assert new_ids <= set(tasks), '重映射后的任务已入库'
            for tid in new_ids:
                assert tasks[tid].status == 'completed'

            # test_results.task_id 指向新任务，result_data_path 已重映射且文件可读
            results = session.query(TestResult).filter(TestResult.id != 100, TestResult.id != 101).all()
            assert len(results) == 2
            from shared.infrastructure.storage import storage
            for r in results:
                assert str(r.task_id) in {str(i) for i in new_ids}
                if r.result_data_path:
                    assert f'/{r.task_id}/' in r.result_data_path
                    assert storage.exists(r.result_data_path)

            # 关联表全部挂到新任务
            assert {c.task_id for c in session.query(TaskCase).all() if c.id not in (10, 11)} \
                <= new_ids
            assert {d.task_id for d in session.query(TaskDevice).all() if d.id != 20} <= new_ids
            assert {a.task_id for a in session.query(TaskAPI).all() if a.id != 30} <= new_ids
            assert {t.task_id for t in session.query(TaskTag).all() if t.id != 40} <= new_ids

            # 合并关系两端都重映射且都在导出集内
            new_merges = [m for m in session.query(TaskMergeRelation).all() if m.id != 50]
            assert len(new_merges) == 1
            assert {new_merges[0].merged_task_id, new_merges[0].source_task_id} <= new_ids

            # 维度评分挂到新结果
            new_dims = [d for d in session.query(TestResultDimension).all() if d.id != 200]
            assert len(new_dims) == 1
            new_result_ids = {r.id for r in results}
            assert new_dims[0].test_result_id in new_result_ids

            # 报告族：报告挂新任务，子表挂新报告
            new_reports = [r for r in session.query(Report).all() if r.id != 300]
            assert len(new_reports) == 1
            assert new_reports[0].task_id in new_ids
            new_summaries = [s for s in session.query(ReportSummary).all() if s.id != 301]
            assert len(new_summaries) == 1
            assert new_summaries[0].report_id == new_reports[0].id
            new_cases = [c for c in session.query(ReportCase).all() if c.id != 302]
            assert len(new_cases) == 1
            assert new_cases[0].report_id == new_reports[0].id
        finally:
            session.close()

        # 参考参数文件原样回写（test_case_id 不重映射）
        from shared.infrastructure.storage import storage
        assert storage.exists(f'local://ref_params/tc_001/round_1.json')

    def test_eval_segment_failure_triggers_full_compensation(
            self, db, storage_env, patched_acl, fake_redis, monkeypatch):
        """维度导入段失败注入：task 段回滚、无脏数据、补偿错误为空"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)

        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task

        import task_service.application.task.data_transfer_import_service as import_mod

        class _ExplodingEval(_InProcEvalAcl):
            def import_dimensions(self, rows, result_id_mapping, batch_id):
                raise RuntimeError('注入失败：维度写入爆炸')

        monkeypatch.setattr(import_mod, 'evaluation_transfer_acl_repository', _ExplodingEval())

        result = import_mod.data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'] is False
        assert '注入失败' in result['message']
        assert result['data']['compensation_errors'] == []

        session = get_db_session()
        try:
            # 无新增任务（task 段已回滚）
            assert session.query(Task).count() == 2
        finally:
            session.close()

        # 批次登记已清理（task 段回滚成功后删除）
        from shared.utils.data_transfer_batch import transfer_batch_registry
        assert transfer_batch_registry.load_service(result['data']['batch_id'], 'task_service') == {}

    def test_partial_conflict_in_eval_and_report_segments(
            self, db, storage_env, patched_acl, fake_redis):
        """缺陷 1 回归（维度/报告段）：仅维度与报告表冲突时同样只重映射冲突行，
        且自增新 ID 不与本批次显式 ID 撞 UNIQUE。"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)
        _hard_delete_all_15_tables()

        # 目标库放置与包内冲突的维度/报告/摘要占位行（悬空外键，无 FK 约束可插入）
        from datetime import datetime
        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary,
        )
        now = datetime.now()
        session = get_db_session()
        try:
            session.add_all([
                TestResultDimension(id=200, test_result_id=999, dimension_id=1,
                                    algorithm_type='translation', round_number=0,
                                    dimension_value=0.0, score=0.0,
                                    evaluation_status='completed', created_at=now),
                Report(id=300, name='占位报告', type='standard', task_id=999,
                       status='draft', deleted=False, created_at=now, updated_at=now),
                ReportSummary(id=301, report_id=999, task_ids=[],
                              created_at=now, updated_at=now),
            ])
            session.commit()
        finally:
            session.close()

        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service,
        )
        from evaluation_service.infrastructure.persistence.models import (
            TestResultDimension as DimPO,
        )
        from report_service.infrastructure.persistence.models import (
            Report as ReportPO,
            ReportCase as ReportCasePO,
            ReportSummary as ReportSummaryPO,
        )
        from task_service.infrastructure.persistence.models import (
            Task as TaskPO,
            TestResult as TestResultPO,
        )
        result = data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'], result.get('message')
        stats = result['data']

        # remappedIds 反映维度/报告段的重映射（报告子表重映射仅用于段内 FK 改写，
        # 不进入响应契约——四类映射键见规格）
        new_dim_id = int(stats['remappedIds']['test_result_dimensions']['200'])
        new_report_id = int(stats['remappedIds']['test_reports']['300'])
        assert new_dim_id not in (200, 100, 101)
        assert new_report_id not in (300, 1, 2)

        # 任务/结果段无冲突：原 ID 保留
        session = get_db_session()
        try:
            assert {t.id for t in session.query(TaskPO).all()} == {1, 2}
            assert {r.id for r in session.query(TestResultPO).all()} == {100, 101}

            # 维度段：占位 200 仍在，导入行重映射为 new_dim_id，
            # 且 test_result_id 指向无冲突保留的结果 100
            dims = {d.id: d for d in session.query(DimPO).all()}
            assert set(dims) == {200, new_dim_id}
            assert dims[new_dim_id].test_result_id == 100
            assert dims[200].test_result_id == 999

            # 报告段：占位 300/301 仍在，导入行重映射；report.task_id 保留为 1；
            # 摘要 report_id 指向新报告 id（摘要重映射不进 remappedIds，
            # 以 report_id 关联定位导入行）；报告用例行（无冲突）原 ID 保留
            reports = {r.id: r for r in session.query(ReportPO).all()}
            assert set(reports) == {300, new_report_id}
            assert reports[new_report_id].task_id == 1
            assert reports[300].task_id == 999
            summaries = list(session.query(ReportSummaryPO).all())
            assert {s.id for s in summaries} != {301}
            imported_summary = [s for s in summaries if s.report_id == new_report_id]
            assert len(imported_summary) == 1
            assert imported_summary[0].id != 301
            assert {s.id for s in summaries} == {301, imported_summary[0].id}
            assert {c.id for c in session.query(ReportCasePO).all()} == {302}
        finally:
            session.close()

    def test_response_lost_after_eval_commit_triggers_cleanup(
            self, db, storage_env, patched_acl, fake_redis, monkeypatch):
        """审计问题 1 场景 a：远端段已提交并登记、但 gRPC 响应丢失 →
        无条件补偿回滚清理远端孤儿与 task 段，批次登记销毁，errors 为空"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)

        import task_service.application.task.data_transfer_import_service as import_mod

        real_eval = import_mod.evaluation_transfer_acl_repository

        class _ResponseLostEval:
            """模拟响应丢失：远端 import 已成功提交+登记，但客户端收到失败"""

            def export_dimensions_for_tasks(self, result_ids):
                return real_eval.export_dimensions_for_tasks(result_ids)

            def import_dimensions(self, rows, result_id_mapping, batch_id):
                real_eval.import_dimensions(rows, result_id_mapping, batch_id)
                raise RuntimeError('维度评分导入失败: 模拟响应丢失（服务端已提交）')

            def rollback_dimension_import(self, batch_id):
                return real_eval.rollback_dimension_import(batch_id)

        monkeypatch.setattr(import_mod, 'evaluation_transfer_acl_repository', _ResponseLostEval())

        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from report_service.infrastructure.persistence.models import Report
        from task_service.infrastructure.persistence.models import Task

        result = import_mod.data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'] is False
        assert '响应丢失' in result['message']
        assert result['data']['compensation_errors'] == []

        session = get_db_session()
        try:
            # 远端孤儿行被无条件回滚清理，task 段同样回滚：仅剩种子数据
            assert session.query(Task).count() == 2
            assert session.query(TestResultDimension).count() == 1
            assert session.query(Report).count() == 1
        finally:
            session.close()

        from shared.utils.data_transfer_batch import transfer_batch_registry
        assert transfer_batch_registry.load_service(
            result['data']['batch_id'], 'task_service') == {}

    def test_remote_commit_without_registry_surfaces_manual_intervention(
            self, db, storage_env, patched_acl, fake_redis, monkeypatch):
        """审计问题 1 场景 b：远端已提交但登记失败（Redis 故障）→
        返回专用错误、编排层显式提示人工介入，不得静默"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)

        import evaluation_service.application.dimension_transfer_service as eval_svc_mod

        class _BrokenRecordRegistry:
            def record(self, *a, **k):
                raise RuntimeError('模拟 Redis 故障')

            def load_service(self, batch_id, service):
                return {}

            def remove_service(self, *a, **k):
                pass

            def delete(self, *a, **k):
                pass

        monkeypatch.setattr(eval_svc_mod, 'transfer_batch_registry', _BrokenRecordRegistry())

        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from task_service.infrastructure.persistence.models import Task

        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service,
        )
        result = data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'] is False
        assert '已提交但批次登记失败' in result['message']
        compensation_errors = result['data']['compensation_errors']
        assert any('需人工清理' in e for e in compensation_errors)

        session = get_db_session()
        try:
            # task 段经内存主键回滚干净（审计问题 2）
            assert session.query(Task).count() == 2
            # 远端维度段已提交且无登记：孤儿行保留（自动补偿够不着），
            # 由人工介入清单显式暴露——本断言验证"不静默"
            assert session.query(TestResultDimension).count() == 2
        finally:
            session.close()


def _hard_delete_all_15_tables():
    """清空目标库 15 张迁移表（模拟"另一套部署"或已清空的目标库）"""
    from shared.models.database import get_db_session
    from evaluation_service.infrastructure.persistence.models import TestResultDimension
    from report_service.infrastructure.persistence.models import (
        Report, ReportCase, ReportComparisonMatrix, ReportMetricStats,
        ReportRawData, ReportSummary, ReportSummaryMeta,
    )
    from task_service.infrastructure.persistence.models import (
        Task, TaskAPI, TaskCase, TaskDevice, TaskMergeRelation, TaskTag, TestResult,
    )
    session = get_db_session()
    try:
        for model in (TaskCase, TaskDevice, TaskAPI, TaskTag, TaskMergeRelation,
                      TestResultDimension, ReportSummary, ReportSummaryMeta,
                      ReportRawData, ReportCase, ReportMetricStats,
                      ReportComparisonMatrix, Report, TestResult, Task):
            session.query(model).delete()
        session.commit()
    finally:
        session.close()

