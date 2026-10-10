# -*- coding: utf-8 -*-
"""任务数据导入导出 —— 验收补充测试（INT-25 测试工程师）

覆盖开发自测（test_data_transfer_roundtrip.py）之外的验收标准缺口：
- AC1: include_ref_params / include_audios 选项生效；100+ 结果导出 ≤30s
- AC2: 无冲突导入原 ID 全保留；部分冲突仅重映射冲突行（导入级端到端）
- AC3: 报表段失败注入、文件段失败注入（开发仅覆盖维度段）
- AC5: task_service 进度发布契约（parsing→writing_db→extracting_files→updating_paths→done + Redis 快照）
- AC7: 预检冲突清单 + 缺失外部引用 warning + ACL 不可用时 warning 自动跳过
- AC8: 导出临时 ZIP 超 1 小时清理

运行环境与 roundtrip 相同：SQLite 临时库 + 本地降级存储 + 进程内 ACL 替身，
夹具直接复用 test_data_transfer_roundtrip。
"""
import json
import os
import time
import zipfile

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from tests.integration.test_data_transfer_roundtrip import (  # noqa: F401
    _InProcEvalAcl,
    _InProcReportAcl,
    _export_zip,
    _seed,
    db,
    fake_redis,
    patched_acl,
    storage_env,
)

from shared.constants.data_transfer import REDIS_PROGRESS_KEY


# ---------- 通用工具 ----------

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


def _table_counts():
    from shared.models.database import get_db_session
    from evaluation_service.infrastructure.persistence.models import TestResultDimension
    from report_service.infrastructure.persistence.models import (
        Report, ReportCase, ReportSummary,
    )
    from task_service.infrastructure.persistence.models import (
        Task, TaskAPI, TaskCase, TaskDevice, TaskMergeRelation, TaskTag, TestResult,
    )
    session = get_db_session()
    try:
        return {
            'tasks': session.query(Task).count(),
            'results': session.query(TestResult).count(),
            'dims': session.query(TestResultDimension).count(),
            'reports': session.query(Report).count(),
            'report_summaries': session.query(ReportSummary).count(),
            'report_cases': session.query(ReportCase).count(),
            'case_relations': session.query(TaskCase).count(),
            'device_relations': session.query(TaskDevice).count(),
            'api_relations': session.query(TaskAPI).count(),
            'tags': session.query(TaskTag).count(),
            'merges': session.query(TaskMergeRelation).count(),
        }
    finally:
        session.close()


def _seed_baseline_counts():
    """种子数据的基线行数（用于失败注入后的"无脏数据"断言）"""
    return {'tasks': 2, 'results': 2, 'dims': 1, 'reports': 1,
            'report_summaries': 1, 'report_cases': 1,
            'case_relations': 2, 'device_relations': 1, 'api_relations': 1,
            'tags': 1, 'merges': 1}


def _storage_relative_files():
    """列举本地降级存储根下全部文件相对路径（用于文件系统前后对比）"""
    from shared.infrastructure.config import BaseConfig
    root = str(BaseConfig.STORAGE_LOCAL_ROOT)
    found = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            found.add(os.path.relpath(full, root).replace('\\', '/'))
    return found


# ---------- AC1: 导出选项生效 ----------

class TestExportOptions:
    def test_include_ref_params_false_excludes_ref_files(self, db, storage_env,
                                                         patched_acl, fake_redis):
        _seed(db, storage_env)
        from task_service.application.task.data_transfer_export_service import (
            data_transfer_export_service)
        result = data_transfer_export_service.export_tasks(
            [1, 2], {'include_ref_params': False, 'include_audios': False})
        assert result['success'], result.get('message')

        with zipfile.ZipFile(result['data']['zip_path']) as zf:
            names = zf.namelist()
            assert not any(n.startswith('files/ref_params/') for n in names), \
                'include_ref_params=False 不应打包参考参数文件'
            assert any(n.startswith('files/case_results/') for n in names), \
                '结果文件不受该选项影响'
            manifest = json.loads(zf.read('manifest.json'))
        assert manifest['options']['includeRefParams'] is False
        assert manifest['options']['includeAudios'] is False

    def test_include_audios_true_survives_audio_acl_down(self, db, storage_env,
                                                         patched_acl, fake_redis,
                                                         monkeypatch):
        """include_audios=True 且 audio_service ACL 不可用：导出不崩、跳过音频条目"""
        _seed(db, storage_env)
        from task_service.application.task.data_transfer_export_service import (
            data_transfer_export_service)
        from task_service.infrastructure.acl import audio_acl_repository as audio_acl_mod
        monkeypatch.setattr(audio_acl_mod.audio_acl_repository, 'list_audios_by_ids',
                            lambda ids: {})

        result = data_transfer_export_service.export_tasks(
            [1, 2], {'include_ref_params': True, 'include_audios': True})
        assert result['success'], \
            f'audio ACL 不可用时导出应降级而非失败: {result.get("message")}'

        with zipfile.ZipFile(result['data']['zip_path']) as zf:
            names = zf.namelist()
            assert not any(n.startswith('files/audios/') for n in names)
            assert any(n.startswith('files/ref_params/') for n in names)
            manifest = json.loads(zf.read('manifest.json'))
        assert manifest['options']['includeAudios'] is True


# ---------- AC1: 性能 ----------

def _seed_many_results(db, storage_env, task_id=900, count=120):
    """独立种子：1 个已完成任务 + count 条带落盘文件的结果（性能测试用）"""
    from datetime import datetime
    from shared.infrastructure.storage import storage
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import Task, TestResult

    now = datetime.now()
    session = get_db_session()
    try:
        session.add(Task(id=task_id, name='大任务-性能', description='perf', type='api',
                         status='completed', config={}, algorithm_type='translation',
                         algorithm_params={}, total_cases=count, completed_cases=count,
                         failed_cases=0, created_by_user_id=None, created_at=now,
                         updated_at=now, deleted=False, reevaluation_count=0,
                         execution_source='manual'))
        for i in range(count):
            stored = storage.save_bytes(
                json.dumps({'i': i}).encode(), 'case_result',
                f'{task_id}/tc_perf/dev{i}/result_data.json',
                content_type='application/json')
            session.add(TestResult(id=5000 + i, task_id=task_id,
                                   test_case_id='tc_perf', device_id=1, api_id=1,
                                   algorithm_type='translation',
                                   execution_status='completed',
                                   result_data={'i': i}, result_data_path=stored,
                                   created_at=now))
        session.commit()
    finally:
        session.close()


class TestExportPerformance:
    def test_120_results_export_under_30s(self, db, storage_env, patched_acl, fake_redis):
        _seed_many_results(db, storage_env, count=120)
        from task_service.application.task.data_transfer_export_service import (
            data_transfer_export_service)
        started = time.perf_counter()
        result = data_transfer_export_service.export_tasks([900], {})
        elapsed = time.perf_counter() - started
        assert result['success'], result.get('message')
        assert elapsed < 30.0, f'120 结果导出耗时 {elapsed:.1f}s，超过验收上限 30s'
        assert result['data']['manifest']['stats']['resultCount'] == 120
        assert result['data']['file_count'] == 120


# ---------- AC2: 无冲突 / 部分冲突导入 ----------

class TestImportIdStrategy:
    def test_no_conflict_preserves_all_original_ids(self, db, storage_env,
                                                    patched_acl, fake_redis):
        """同库导入无 ID 冲突 → 全部原 ID 保留、无 remappedIds"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)
        _hard_delete_all_15_tables()

        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from report_service.infrastructure.persistence.models import (
            Report, ReportCase, ReportSummary,
        )
        from task_service.infrastructure.persistence.models import (
            Task, TaskAPI, TaskCase, TaskDevice, TaskMergeRelation, TaskTag, TestResult,
        )
        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service)
        result = data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'], result.get('message')
        stats = result['data']
        assert not stats.get('remappedIds'), f'无冲突导入不应产生重映射: {stats}'

        session = get_db_session()
        try:
            assert sorted(t.id for t in session.query(Task).all()) == [1, 2]
            assert sorted(r.id for r in session.query(TestResult).all()) == [100, 101]
            assert [d.id for d in session.query(TestResultDimension).all()] == [200]
            assert sorted(r.id for r in session.query(Report).all()) == [300]
            assert [s.id for s in session.query(ReportSummary).all()] == [301]
            assert [c.id for c in session.query(ReportCase).all()] == [302]
            assert sorted(m.id for m in session.query(TaskMergeRelation).all()) == [50]
            assert sorted(c.id for c in session.query(TaskCase).all()) == [10, 11]
            assert [d.id for d in session.query(TaskDevice).all()] == [20]
            assert [a.id for a in session.query(TaskAPI).all()] == [30]
            assert [t.id for t in session.query(TaskTag).all()] == [40]
            # 导入后任务状态 completed；路径原值保留且文件可读
            from shared.infrastructure.storage import storage
            r100 = session.get(TestResult, 100)
            assert r100.result_data_path and storage.exists(r100.result_data_path)
            assert session.get(Task, 1).status == 'completed'
        finally:
            session.close()

    def test_partial_conflict_remaps_only_conflicted_rows(self, db, storage_env,
                                                          patched_acl, fake_redis):
        """部分冲突：task 1 冲突重映射、task 2 及下游原 ID 保留、外键按行精确转换

        INT-25 缺陷 1 已修复（两遍插入：先插显式 id 行并同步序列，再插去 id 冲突行），
        开发提测修复时移除原 xfail(strict) 标记。
        """
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)
        _hard_delete_all_15_tables()

        # 目标库仅存在一个与包内冲突的任务 id=1
        from datetime import datetime
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task
        now = datetime.now()
        session = get_db_session()
        try:
            session.add(Task(id=1, name='占位-已存在', description='x', type='api',
                             status='completed', config={}, algorithm_type='translation',
                             algorithm_params={}, total_cases=0, completed_cases=0,
                             failed_cases=0, created_by_user_id=None, created_at=now,
                             updated_at=now, deleted=False, reevaluation_count=0,
                             execution_source='manual'))
            session.commit()
        finally:
            session.close()

        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from report_service.infrastructure.persistence.models import (
            Report, ReportCase, ReportSummary,
        )
        from task_service.infrastructure.persistence.models import (
            TestResult,
        )
        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service)
        result = data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'], result.get('message')
        stats = result['data']

        remapped_tasks = stats['remappedIds']['tasks']
        assert sorted(int(k) for k in remapped_tasks) == [1], \
            f'仅冲突的 task 1 应被重映射: {remapped_tasks}'
        new_task_id = int(remapped_tasks['1'])
        assert new_task_id != 1

        session = get_db_session()
        try:
            assert {t.id for t in session.query(Task).all()} == {1, 2, new_task_id}
            # 无冲突行原 ID 保留
            assert {r.id for r in session.query(TestResult).all()} == {100, 101}
            assert {d.id for d in session.query(TestResultDimension).all()} == {200}
            assert {r.id for r in session.query(Report).all()} == {300}
            # 外键按行转换：result 100 原属 task 1 → 新 id；result 101 原属 task 2 → 保留
            r100, r101 = (session.get(TestResult, 100), session.get(TestResult, 101))
            assert r100.task_id == new_task_id
            assert r101.task_id == 2
            # 维度评分 → 结果（结果无冲突映射到自身）
            assert session.get(TestResultDimension, 200).test_result_id == 100
            # 报告族 → 新 task；子表 → 原报告 id
            assert session.get(Report, 300).task_id == new_task_id
            assert session.get(ReportSummary, 301).report_id == 300
            assert session.get(ReportCase, 302).report_id == 300
            # merge relation 双端按行转换
            from task_service.infrastructure.persistence.models import TaskMergeRelation
            merges = session.query(TaskMergeRelation).all()
            assert len(merges) == 1
            assert {merges[0].merged_task_id, merges[0].source_task_id} == {new_task_id, 2}
        finally:
            session.close()


# ---------- AC3: 报表段 / 文件段失败注入（补偿回滚） ----------

class TestCompensationSegments:
    def test_report_segment_failure_rolls_back_task_and_eval(self, db, storage_env,
                                                             patched_acl, fake_redis,
                                                             monkeypatch):
        """报表导入段失败：task 段与维度段回滚、无文件写入、批次登记清空"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)
        before_files = _storage_relative_files()

        import task_service.application.task.data_transfer_import_service as import_mod

        class _ExplodingReport(_InProcReportAcl):
            def import_reports(self, tables_rows, task_id_mapping, batch_id):
                raise RuntimeError('注入失败：报表写入爆炸')

        monkeypatch.setattr(import_mod, 'report_transfer_acl_repository', _ExplodingReport())

        result = import_mod.data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'] is False
        assert '注入失败' in result['message']
        assert result['data']['compensation_errors'] == [], \
            f'补偿自身不应失败: {result["data"]["compensation_errors"]}'

        counts = _table_counts()
        assert counts == _seed_baseline_counts(), f'存在脏数据残留: {counts}'
        assert _storage_relative_files() == before_files, '文件段不应已写入'
        from shared.utils.data_transfer_batch import transfer_batch_registry
        batch_id = result['data']['batch_id']
        assert transfer_batch_registry.load_service(batch_id, 'task_service') == {}

    def test_file_segment_failure_cleans_written_files_and_db(self, db, storage_env,
                                                              patched_acl, fake_redis,
                                                              monkeypatch):
        """文件回写段失败：已写入文件被清理、源文件不受影响、三段 DB 全回滚"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)

        import task_service.application.task.data_transfer_import_service as import_mod
        real_write = import_mod.write_case_result_files
        written_snapshot = []

        def _write_then_explode(entries, tasks_mapping, tracker=None):
            out = real_write(entries, tasks_mapping, tracker)
            written_snapshot.extend(out)
            raise RuntimeError('注入失败：文件回写爆炸')

        monkeypatch.setattr(import_mod, 'write_case_result_files', _write_then_explode)

        result = import_mod.data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'] is False
        assert '注入失败' in result['message']
        assert result['data']['compensation_errors'] == []

        counts = _table_counts()
        assert counts == _seed_baseline_counts(), f'存在脏数据残留: {counts}'

        from shared.infrastructure.storage import storage
        assert written_snapshot, '文件段应已写入部分文件后才失败'
        for key, stored_path in written_snapshot:
            assert not storage.exists(stored_path), \
                f'已回写文件未被补偿清理: {key} -> {stored_path}'
        # 源任务的种子文件不受补偿误删
        from shared.infrastructure.config import BaseConfig
        source_file = os.path.join(str(BaseConfig.STORAGE_LOCAL_ROOT),
                                   'case_result', '1', 'tc_001', 'devSN001',
                                   'result_data.json')
        assert os.path.isfile(source_file), '补偿不应误删源文件'


# ---------- AC5: 进度发布契约（task_service 侧） ----------

class TestProgressPublishing:
    def test_success_import_publishes_step_sequence_and_snapshot(
            self, db, storage_env, patched_acl, fake_redis, monkeypatch):
        """成功导入发布 parsing→writing_db→extracting_files→updating_paths→done，
        并写 Redis 快照（GET /import/progress 的数据源）"""
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)

        import task_service.application.task.import_progress_reporter as reporter_mod

        published = []

        class _RecordingEventBus:
            def __init__(self, *a, **k):
                pass

            def publish(self, channel, event_type, payload):
                published.append((
                    channel.value if hasattr(channel, 'value') else channel,
                    {
                        'event_type': event_type.value if hasattr(event_type, 'value') else event_type,
                        'payload': payload,
                    },
                ))

        monkeypatch.setattr(reporter_mod, 'EventBus', _RecordingEventBus)

        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service)
        result = data_transfer_import_service.execute_import(data['zip_path'])
        assert result['success'], result.get('message')

        from shared.utils.redis_pubsub import EventChannel, EventType
        payloads = [msg['payload']['data'] for channel, msg in published
                    if channel == EventChannel.TASK_EVENTS.value
                    and msg.get('event_type') == EventType.IMPORT_PROGRESS.value
                    and isinstance(msg.get('payload'), dict)]
        steps = [p['step'] for p in payloads]
        assert steps[0] == 'parsing'
        assert steps[-1] == 'done'
        assert {'writing_db', 'extracting_files', 'updating_paths'} <= set(steps)
        done = payloads[-1]
        assert done['percentage'] == 100
        # payload 契约字段（shared/schemas/socket_payloads.ImportProgressPayload；
        # 仓库 socket 通道统一 snake_case 直出，前端 adapter 转 camelCase）
        for field in ('step', 'current_table', 'processed_rows', 'total_rows',
                      'percentage', 'message'):
            assert field in done

        # Redis HASH 快照（兜底接口数据源）
        snapshot = fake_redis.load_task(REDIS_PROGRESS_KEY)
        assert snapshot.get('step') == 'done'
        assert snapshot.get('batch_id')


# ---------- AC7: 预检 ----------

class TestPreview:
    def test_preview_reports_conflicts_and_missing_case_warning(
            self, db, storage_env, patched_acl, fake_redis, monkeypatch):
        _seed(db, storage_env)
        data = _export_zip(storage_env, patched_acl, fake_redis)

        from datetime import datetime
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import TestCase, Task
        session = get_db_session()
        try:
            # 同库导出后包内 ID 与现存数据天然冲突；改现存任务名以断言 existingName
            # （本用例只验证预检只读不改库，无需新插入冲突行）
            task1 = session.get(Task, 1)
            assert task1 is not None
            task1.name = '已存在同名任务'
            # 制造缺失外部引用：目标库删除被引用的测试用例
            session.query(TestCase).filter(TestCase.id == 'tc_001').delete()
            session.commit()
        finally:
            session.close()

        # 设备/算法 ACL 不可用：自动跳过对应 warning（不崩、不误报）
        from task_service.infrastructure.acl import device_acl_repository as device_acl_mod
        monkeypatch.setattr(device_acl_mod.device_acl_repository, 'get_device_statuses',
                            lambda ids: [])

        from task_service.application.task.data_transfer_import_service import (
            data_transfer_import_service)
        preview = data_transfer_import_service.preview_import(data['zip_path'])
        assert preview['success'], preview.get('message')
        d = preview['data']

        assert d['manifest']['version'] == '1.0'
        assert d['stats']['tableRows'].get('test_tasks') == 2
        assert d['stats']['taskCount'] == 2

        task_conflicts = [c for c in d['conflicts'] if c['table'] == 'test_tasks']
        assert any(c['id'] == 1 and c['existingName'] == '已存在同名任务'
                   for c in task_conflicts), f'预检应给出冲突任务及现名: {task_conflicts}'
        result_conflicts = [c for c in d['conflicts'] if c['table'] == 'test_results']
        assert {c['id'] for c in result_conflicts} == {100, 101}

        assert any('测试用例' in w for w in d['warnings']), \
            f'缺失用例引用应产生 warning: {d["warnings"]}'
        # 设备 ACL 返回空（不可用）→ 不产生设备缺失误报
        assert not any('设备' in w for w in d['warnings']), \
            f'ACL 不可用不应误报设备缺失: {d["warnings"]}'


# ---------- AC8: 导出临时 ZIP 超 1 小时清理 ----------

class TestExpiredExportSweep:
    def test_sweep_removes_only_files_older_than_1h(self, db, storage_env,
                                                    patched_acl, fake_redis):
        _seed(db, storage_env)
        _export_zip(storage_env, patched_acl, fake_redis)  # 确保 export 目录存在
        export_dir = os.path.join(str(storage_env), 'data_transfer', 'export')

        stale = os.path.join(export_dir, 'task_export_stale.zip')
        with open(stale, 'wb') as f:
            f.write(b'PK\x05\x06' + b'\x00' * 18)
        two_hours_ago = time.time() - 7200
        os.utime(stale, (two_hours_ago, two_hours_ago))

        fresh = os.path.join(export_dir, 'task_export_fresh.zip')
        with open(fresh, 'wb') as f:
            f.write(b'PK\x05\x06' + b'\x00' * 18)

        _export_zip(storage_env, patched_acl, fake_redis)

        assert not os.path.exists(stale), '超过 1 小时的导出临时 ZIP 应被清理'
        assert os.path.exists(fresh), '1 小时内的文件不应被清理'
