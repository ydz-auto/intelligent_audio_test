# -*- coding: utf-8 -*-
"""INT-408 专项：报告查看侧三处 cherry-pick 容器引用解析（对比/分组均值/日志下载）。

INT-339 挑选合并容器任务创建即 completed、自身无 test_results 行，报告查看侧
按 task_id 直查的三条查询静默空值：
1. 对比：_collect_results_for_tasks 按引用关系取源结果并映射回容器列 → 矩阵列
   有数据、加权值非 0；
2. 分组/标签平均值：_query_cases_for_averages / _query_test_cases_and_results
   按引用 result_id 直查源结果（容器 TaskCase 取自身，下单已继承）；
3. 用例日志下载：_query_case_logs 落源任务前缀 + _write_case_log_files 按
   源任务搜索存储目录。

gRPC helper 以 monkeypatch 替换（对齐 test_int339 惯例）；容器任务沿用
INT-339 验收口径（source_task_id / result_id 溯源快照形状）。
"""
import io
import os
import zipfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

import pytest

CONTAINER_ID = 9001
SOURCE_TASK_ID = 7001
CHERRY_RELATIONS = [
    {'result_id': 101, 'source_task_id': SOURCE_TASK_ID,
     'source_case_id': 'ACC408-C1', 'source_device_id': 7},
    {'result_id': 102, 'source_task_id': SOURCE_TASK_ID,
     'source_case_id': 'ACC408-C2', 'source_device_id': 8},
]
SOURCE_RESULTS = [
    {'id': 101, 'task_id': SOURCE_TASK_ID, 'test_case_id': 'ACC408-C1',
     'device_id': 7, 'execution_status': 'completed'},
    {'id': 102, 'task_id': SOURCE_TASK_ID, 'test_case_id': 'ACC408-C2',
     'device_id': 8, 'execution_status': 'completed'},
]


@pytest.fixture()
def stub_cherry(monkeypatch):
    """容器按引用解析；普通任务回落普通链路（cherry/merge 均为空）。"""
    import report_service.infrastructure.clients.grpc_clients as grpc_clients

    monkeypatch.setattr(
        grpc_clients, '_grpc_get_cherry_pick_relations',
        lambda tid: CHERRY_RELATIONS if tid == CONTAINER_ID else [])
    monkeypatch.setattr(
        grpc_clients, '_grpc_get_task_merge_relations', lambda tid: [])
    monkeypatch.setattr(
        grpc_clients, '_grpc_get_test_results_by_ids',
        lambda ids: [r for r in SOURCE_RESULTS if r['id'] in set(ids)])
    return grpc_clients


# ==================== 1. 对比：结果收集与容器列 ====================

class TestCompareCherryResolution:
    """_collect_results_for_tasks：cherry 容器按引用取源结果并映射回容器列。"""

    def test_cherry_container_collects_and_remaps(self, stub_cherry):
        from report_service.application.services.report_compare_generator_data_mixin import (
            ReportCompareDataMixin,
        )

        results = ReportCompareDataMixin._collect_results_for_tasks([CONTAINER_ID])

        assert {r['id'] for r in results} == {101, 102}
        # 引用方案 A 只读解析：结果在内存映射回容器列（不改 test_results.task_id）
        assert all(r['task_id'] == CONTAINER_ID for r in results)

    def test_plain_task_queries_own_task_id(self, stub_cherry, monkeypatch):
        from report_service.application.services.report_compare_generator_data_mixin import (
            ReportCompareDataMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        calls = []
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_test_results_by_task_ids',
            lambda ids: (calls.append(ids), [{'id': 55, 'task_id': 1234}])[1])

        results = ReportCompareDataMixin._collect_results_for_tasks([1234])

        assert calls == [[1234]]
        assert results == [{'id': 55, 'task_id': 1234}]

    def test_merge_container_expands_leaf_sources(self, stub_cherry, monkeypatch):
        from report_service.application.services.report_compare_generator_data_mixin import (
            ReportCompareDataMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients
        import report_service.application.services.report_data_builder_task_mixin as task_mixin

        merged_id = 9002
        # resolver 首查走 grpc_clients（延迟导入）；叶子展开走 task_mixin 模块级引用
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_task_merge_relations',
            lambda tid: [{'source_task_id': 8001}, {'source_task_id': 8002}]
            if tid == merged_id else [])
        monkeypatch.setattr(
            task_mixin, '_grpc_get_task_merge_relations', lambda tid: [])
        monkeypatch.setattr(
            task_mixin, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': i, 'status': 'completed'} for i in ids])
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_test_results_by_task_ids',
            lambda ids: [{'id': 66, 'task_id': 8001}, {'id': 67, 'task_id': 8002}])

        results = ReportCompareDataMixin._collect_results_for_tasks([merged_id])

        assert {r['id'] for r in results} == {66, 67}
        # 合并容器结果同样映射回容器列，保证对比矩阵列有数据
        assert all(r['task_id'] == merged_id for r in results)

    def test_matrix_column_and_weighted_value_nonzero(self, stub_cherry, monkeypatch):
        """验收1：容器列有数据、加权值非 0（对比矩阵/加权值由容器列结果驱动）。"""
        import report_service.application.services.report_query_builder as rqb
        import report_service.application.services.report_compare_helpers as rch

        results = [
            {'id': 101, 'task_id': CONTAINER_ID, 'test_case_id': 'ACC408-C1',
             'execution_status': 'completed'},
            {'id': 102, 'task_id': CONTAINER_ID, 'test_case_id': 'ACC408-C2',
             'execution_status': 'completed'},
        ]
        all_dimensions = [
            {'id': 1, 'name': 'ASR得分', 'weight': 1.0,
             'score_unit': '%', 'decimal_places': 2},
        ]
        monkeypatch.setattr(
            rqb, '_grpc_get_dim_results',
            lambda ids: {101: [{'dimension_id': 1, 'dimension_value': 80.0}],
                         102: [{'dimension_id': 1, 'dimension_value': 60.0}]})
        monkeypatch.setattr(
            rch, '_grpc_list_testcases_by_ids',
            lambda ids: {'ACC408-C1': {'id': 'ACC408-C1', 'name': '用例1'},
                         'ACC408-C2': {'id': 'ACC408-C2', 'name': '用例2'}})

        weighted = rch.ReportCompareHelpers._calculate_task_weighted_values(
            [CONTAINER_ID], results, all_dimensions)
        assert weighted[CONTAINER_ID] > 0

        matrix = rch.ReportCompareHelpers._build_comparison_matrix(
            results, all_dimensions)
        assert f'task_{CONTAINER_ID}' in matrix['ACC408-C1']
        assert matrix['ACC408-C1'][f'task_{CONTAINER_ID}']['values']['ASR得分'] == 80.0


# ==================== 2. 分组/标签平均值 ====================

class TestAveragesCherryResolution:
    """_query_cases_for_averages：cherry 容器结果按引用 result_id 直查。"""

    def test_cherry_container_resolves_results_by_result_ids(self, stub_cherry, monkeypatch):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients
        import report_service.application.services.report_query_builder as rqb

        monkeypatch.setattr(
            grpc_clients, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': CONTAINER_ID, 'name': '容器', 'status': 'completed'}])
        monkeypatch.setattr(
            rqb, '_grpc_get_task_case_ids',
            lambda tid: [{'test_case_id': 'ACC408-C1'},
                         {'test_case_id': 'ACC408-C2'}]
            if tid == CONTAINER_ID else [])
        monkeypatch.setattr(
            grpc_clients, '_grpc_list_testcases_by_ids',
            lambda ids: {i: {'id': i, 'name': f'用例{i}',
                             'group': {'name': '分组1'}, 'tags': []}
                         for i in ids})
        # 容器自身无 test_results 行：断言不走按 task_id 直查（返回空也不影响）
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_test_results_by_task_ids', lambda ids: [])

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        monkeypatch.setattr(
            m, '_calculate_averages',
            lambda task, fcid, tr, tid: {'overall_averages': 1, 'filtered_case_ids': fcid,
                                         'test_results': tr})

        task, task_id_filter, filtered_case_ids, test_results = m._query_cases_for_averages(
            CONTAINER_ID, None, [], [], True)

        assert task['id'] == CONTAINER_ID
        # 容器查询走自身 task_id 过滤（结果经引用直查）
        assert task_id_filter == CONTAINER_ID
        assert sorted(filtered_case_ids) == ['ACC408-C1', 'ACC408-C2']
        assert {r['id'] for r in test_results} == {101, 102}
        # 源结果 task_id 未被改写（红线：引用方案 A，不改 test_results.task_id）
        assert {r['task_id'] for r in test_results} == {SOURCE_TASK_ID}

    def test_plain_task_keeps_own_ids(self, stub_cherry, monkeypatch):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        monkeypatch.setattr(
            grpc_clients, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': 1234, 'name': '普通任务', 'status': 'completed'}])

        captured = {}

        def _fake_query(task_id_filter, result_task_filter, *a, **k):
            captured['tf'] = task_id_filter
            captured['rf'] = result_task_filter
            captured['cherry'] = k.get('cherry_result_ids')
            return ['c-1'], []

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        monkeypatch.setattr(m, '_query_test_cases_and_results', _fake_query)

        m._query_cases_for_averages(1234, None, [], [], True)

        assert captured['tf'] == 1234
        assert captured['rf'] == 1234
        assert captured['cherry'] is None

    def test_query_test_cases_extracts_task_case_ids(self, stub_cherry, monkeypatch):
        """迁移回归：TaskCase 载荷为 dict（含 test_case_id），须提取 id 再查 TestCase
        并过滤结果（pre-DDD 为 [tc.test_case_id for tc in task_cases]；
        修复前直接透传 dict → TestCase 永不命中、分组/标签平均值恒空）。"""
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients
        import report_service.application.services.report_query_builder as rqb

        monkeypatch.setattr(
            rqb, '_grpc_get_task_case_ids',
            lambda tid: [{'test_case_id': 'ACC408-C1', 'status': 'completed'},
                         {'test_case_id': 'ACC408-C2', 'status': 'completed'}]
            if tid == 1234 else [])
        monkeypatch.setattr(
            grpc_clients, '_grpc_list_testcases_by_ids',
            lambda ids: {i: {'id': i, 'name': f'用例{i}',
                             'group': {'name': '分组1'}, 'tags': []}
                         for i in ids})
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_test_results_by_task_ids',
            lambda ids: [{'id': 11, 'task_id': 1234, 'test_case_id': 'ACC408-C1'},
                         {'id': 12, 'task_id': 1234, 'test_case_id': 'ACC408-C2'},
                         {'id': 13, 'task_id': 1234, 'test_case_id': 'OTHER-C9'}])

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)

        filtered_case_ids, test_results = m._query_test_cases_and_results(
            1234, 1234, None, [], [], True)

        assert sorted(filtered_case_ids) == ['ACC408-C1', 'ACC408-C2']
        assert {r['id'] for r in test_results} == {11, 12}
        # OTHER-C9 结果不在任务用例集内，被过滤
        assert 13 not in {r['id'] for r in test_results}


# ==================== 3. 用例日志下载 ====================

class TestCaseLogsCherryResolution:
    """_query_case_logs / _write_case_log_files：cherry 容器落源任务前缀。"""

    class _Agg:
        task_id = CONTAINER_ID

    class _Repo:
        def get_by_id(self, report_id):
            return TestCaseLogsCherryResolution._Agg()

    def test_cherry_container_searches_source_task_prefix(self, stub_cherry, monkeypatch):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        m.repository = self._Repo()

        task_ids_to_search, test_result = m._query_case_logs(1, 'ACC408-C1')

        assert task_ids_to_search == [SOURCE_TASK_ID]
        assert test_result['id'] == 101

    def test_plain_task_searches_own_task(self, stub_cherry, monkeypatch):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        monkeypatch.setattr(
            grpc_clients, '_grpc_get_test_results_by_task_ids',
            lambda ids: [{'id': 55, 'task_id': 1234, 'test_case_id': 'c-x'}])

        class _Agg2:
            task_id = 1234

        class _Repo2:
            def get_by_id(self, report_id):
                return _Agg2()

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        m.repository = _Repo2()

        task_ids_to_search, test_result = m._query_case_logs(1, 'c-x')

        assert task_ids_to_search == [1234]
        assert test_result['id'] == 55

    def test_write_case_log_files_uses_source_task_prefix(self, stub_cherry, monkeypatch):
        """验收3：按挑选关系落源任务前缀解析存储目录并写入 ZIP。"""
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        from shared.infrastructure import storage as storage_mod

        seen_prefixes = []

        def _list_objects(category, prefix=''):
            seen_prefixes.append(prefix)
            return [f'{SOURCE_TASK_ID}/ACC408-C1/out.wav']

        monkeypatch.setattr(storage_mod.storage, 'list_objects', _list_objects)
        monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                            lambda path: b'DATA')

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            found = ReportStatsQueryMixin._write_case_log_files(
                zf, [SOURCE_TASK_ID], 'ACC408-C1', False)

        assert found is True
        assert seen_prefixes == [f'{SOURCE_TASK_ID}/ACC408-C1/']
        with zipfile.ZipFile(buf, 'r') as zf2:
            assert zf2.namelist() == ['out.wav']
