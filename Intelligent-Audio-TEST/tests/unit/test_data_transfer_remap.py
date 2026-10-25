# -*- coding: utf-8 -*-
"""任务数据导入导出 —— ID 重映射与外键规则单测（纯函数，无 DB）"""
import pytest

from shared.constants.data_transfer import (
    FK_RULES,
    FkMappingKey,
    TransferTable,
    fk_rules_of,
)
from shared.utils.data_transfer import (
    apply_fk_mapping,
    build_id_mapping,
    conflicted_ids,
    parse_storage_path,
    remap_task_id_in_key,
    safe_storage_key,
    strip_conflicting_ids,
)
from task_service.domain.services.data_transfer import (
    apply_result_file_key_remapping,
    build_table_mapping,
    collect_external_references,
    filter_merge_relations,
    plan_task_segment,
    rewrite_fk_rows,
)


def _task_rows():
    return [
        {'id': 1, 'name': 'A', 'status': 'completed'},
        {'id': 2, 'name': 'B', 'status': 'completed'},
        {'id': 3, 'name': 'C', 'status': 'completed'},
    ]


class TestStripConflictingIds:
    def test_no_conflict_keeps_original_ids(self):
        rows = strip_conflicting_ids(_task_rows(), existing_ids={10, 20})
        assert [r['id'] for r in rows] == [1, 2, 3]

    def test_all_conflict_strips_ids(self):
        rows = strip_conflicting_ids(_task_rows(), existing_ids={1, 2, 3})
        assert all('id' not in r for r in rows)
        assert [r['name'] for r in rows] == ['A', 'B', 'C']

    def test_partial_conflict_only_strips_conflicted(self):
        rows = strip_conflicting_ids(_task_rows(), existing_ids={2})
        assert [r.get('id') for r in rows] == [1, None, 3]
        assert rows[1]['name'] == 'B'

    def test_input_rows_not_mutated(self):
        original = _task_rows()
        strip_conflicting_ids(original, existing_ids={1})
        assert [r['id'] for r in original] == [1, 2, 3]

    def test_conflicted_ids_listing(self):
        assert conflicted_ids(_task_rows(), {2, 3}) == [2, 3]


class TestBuildTableMapping:
    def test_identity_for_kept_and_new_for_conflicted(self):
        # 原 id [1,2,3]，2、3 冲突，flush 后新 id 为 205、206
        mapping = build_table_mapping([1, 2, 3], [2, 3], [205, 206])
        assert mapping == {1: 1, 2: 205, 3: 206}

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            build_id_mapping([1, 2], [9])


class TestPlanTaskSegment:
    def test_plan_reports_conflicts_in_row_order(self):
        rows_by_table = {
            'test_tasks': _task_rows(),
            'test_results': [{'id': 101, 'task_id': 1}, {'id': 102, 'task_id': 2}],
        }
        existing = {
            'test_tasks': {2},
            'test_results': {101, 102},
        }
        plan = plan_task_segment(rows_by_table, existing)
        task_plan = plan.get(TransferTable.TEST_TASKS)
        assert task_plan.conflicted_old_ids == [2]
        assert task_plan.rows[1].get('id') is None  # 冲突行无 id，与 conflicted_old_ids 按序对应
        assert plan.get(TransferTable.TEST_RESULTS).conflicted_old_ids == [101, 102]

    def test_plan_empty_tables(self):
        plan = plan_task_segment({}, {})
        assert plan.total_rows() == 0


class TestFkRules:
    def test_18_rules_total(self):
        assert len(FK_RULES) == 18

    def test_rules_reference_only_three_mappings(self):
        # 维度评分表自身无出站外键规则（其 test_result_id 归属 evaluation 段被引用方向相反）
        assert {r.mapping for r in FK_RULES} == {
            FkMappingKey.TASKS, FkMappingKey.TEST_RESULTS, FkMappingKey.TEST_REPORTS}

    def test_each_table_rules(self):
        assert len(fk_rules_of(TransferTable.TASK_MERGE_RELATIONS)) == 2
        assert len(fk_rules_of(TransferTable.TEST_RESULTS)) == 1
        assert fk_rules_of(TransferTable.TEST_RESULT_DIMENSIONS)[0].column == 'test_result_id'
        # INT-656：cherry-pick 容器关系表三外键（容器任务 / 引用结果 / 溯源来源任务）
        assert len(fk_rules_of(TransferTable.TASK_CHERRY_PICK_RELATIONS)) == 3
        assert {r.column for r in fk_rules_of(TransferTable.TASK_CHERRY_PICK_RELATIONS)} == {
            'cherry_pick_task_id', 'result_id', 'source_task_id'}
        # report 子表 6 张都是 report_id → TEST_REPORTS
        report_children = [t for t in TransferTable if t.value.startswith('report_')]
        assert len(report_children) == 6
        for table in report_children:
            rule = fk_rules_of(table)[0]
            assert rule.column == 'report_id'
            assert rule.mapping is FkMappingKey.TEST_REPORTS


class TestRewriteFkRows:
    def test_task_segment_children_rewritten(self):
        rows = [
            {'id': 5, 'task_id': 1},
            {'id': 6, 'task_id': 2},
            {'id': 7, 'task_id': 99},  # 不在映射中 → 保持原值
        ]
        out = rewrite_fk_rows(rows, fk_rules_of(TransferTable.TASK_CASE_RELATIONS),
                              {FkMappingKey.TASKS: {2: 202}})
        assert [r['task_id'] for r in out] == [1, 202, 99]

    def test_merge_relation_both_columns(self):
        rows = [{'id': 1, 'merged_task_id': 1, 'source_task_id': 2}]
        out = rewrite_fk_rows(rows, fk_rules_of(TransferTable.TASK_MERGE_RELATIONS),
                              {FkMappingKey.TASKS: {1: 11, 2: 12}})
        assert out[0]['merged_task_id'] == 11
        assert out[0]['source_task_id'] == 12

    def test_none_fk_value_skipped(self):
        rows = [{'id': 1, 'task_id': None}]
        out = rewrite_fk_rows(rows, fk_rules_of(TransferTable.TEST_RESULTS),
                              {FkMappingKey.TASKS: {1: 11}})
        assert out[0]['task_id'] is None


class TestMergeRelationFilter:
    def test_keeps_only_rows_with_both_ends_in_export_set(self):
        rows = [
            {'id': 1, 'merged_task_id': 1, 'source_task_id': 2},
            {'id': 2, 'merged_task_id': 1, 'source_task_id': 7},  # 7 不在导出集
            {'id': 3, 'merged_task_id': 8, 'source_task_id': 2},
        ]
        assert filter_merge_relations(rows, {1, 2}) == [rows[0]]


class TestExternalReferences:
    def test_collect_ids_as_strings(self):
        rows_by_table = {
            'task_case_relations': [{'test_case_id': 'c1'}, {'test_case_id': 'c2'}],
            'task_device_relations': [{'device_id': 5}],
            'task_api_relations': [{'api_id': 9}],
            'test_results': [{'device_id': 5}, {'device_id': 6}],
        }
        refs = collect_external_references(rows_by_table)
        assert refs['test_case_ids'] == ['c1', 'c2']
        assert refs['device_ids'] == ['5', '6']
        assert refs['api_ids'] == ['9']


class TestResultFileKeyRemapping:
    def test_remap_only_for_remapped_tasks(self):
        rows = [
            {'id': 1, 'task_id': 2,
             'result_data_path': 'oss://case_result/2/c1/dev1/result_data.json'},
            {'id': 2, 'task_id': 3,
             'result_data_path': 'oss://case_result/3/c1/dev1/result_data.json'},
            {'id': 3, 'task_id': 4, 'result_data_path': ''},
        ]
        changes = apply_result_file_key_remapping(rows, {2: 202})
        assert changes == [('oss://case_result/2/c1/dev1/result_data.json',
                            '202/c1/dev1/result_data.json')]

    def test_local_scheme_parsed(self):
        assert parse_storage_path('local://case_result/2/c/dev/x.json') == \
            ('case_result', '2/c/dev/x.json')
        assert parse_storage_path('12/c/dev/x.json') == ('12', 'c/dev/x.json')


class TestStorageKeySafety:
    def test_remap_task_segment(self):
        assert remap_task_id_in_key('2/c1/dev1/result_data.json', 202) == \
            '202/c1/dev1/result_data.json'

    def test_rejects_escape(self):
        for bad in ('../c/x.json', '/abs/x.json', 'a/../b.json', 'a//b.json', 'a\\b.json'):
            with pytest.raises(ValueError):
                safe_storage_key(bad)

    def test_apply_fk_mapping_identity_semantics(self):
        rows = [{'task_id': 1}, {'task_id': 2}]
        out = apply_fk_mapping(rows, 'task_id', {})
        assert [r['task_id'] for r in out] == [1, 2]


# ===== INT-1759：用例一致性硬校验（D0 裁定 A10，请求级策略 + 结构化缺口）=====

def _case_ref_rows(*case_ids):
    """构造只带 task_case_relations 引用的包内行（结果/报告行不带用例引用）"""
    return {
        TransferTable.TASK_CASE_RELATIONS.value: [
            {'id': i, 'task_id': 1, 'test_case_id': cid} for i, cid in enumerate(case_ids)
        ],
        TransferTable.TEST_RESULTS.value: [{'id': 100, 'task_id': 1}],
    }


class TestCaseConsistencyPolicy:
    """全局开关 + 请求级开关/意图：请求只能放宽，不能收紧"""

    @staticmethod
    def _service():
        from task_service.application.task.data_transfer_import_service import (
            DataTransferImportService,
        )
        return DataTransferImportService()

    @staticmethod
    def _set_global(monkeypatch, value):
        from shared.infrastructure.config import BaseConfig
        monkeypatch.setattr(BaseConfig, 'DATA_TRANSFER_CASE_CONSISTENCY_REQUIRED', value)

    def test_default_is_required(self, monkeypatch):
        self._set_global(monkeypatch, True)
        assert self._service()._resolve_policy(None) == (True, 'migrate')

    def test_request_false_relaxes(self, monkeypatch):
        self._set_global(monkeypatch, True)
        assert self._service()._resolve_policy(
            {'require_case_consistency': False}) == (False, 'migrate')

    def test_global_false_cannot_be_tightened(self, monkeypatch):
        self._set_global(monkeypatch, False)
        assert self._service()._resolve_policy(
            {'require_case_consistency': True}) == (False, 'migrate')

    def test_restore_defaults_off(self, monkeypatch):
        self._set_global(monkeypatch, True)
        assert self._service()._resolve_policy({'intent': 'restore'}) == (False, 'restore')

    def test_restore_explicit_true_still_checked(self, monkeypatch):
        self._set_global(monkeypatch, True)
        assert self._service()._resolve_policy(
            {'intent': 'restore', 'require_case_consistency': True}) == (True, 'restore')

    def test_restore_with_global_off_stays_off(self, monkeypatch):
        self._set_global(monkeypatch, False)
        assert self._service()._resolve_policy(
            {'intent': 'restore', 'require_case_consistency': True}) == (False, 'restore')

    def test_invalid_intent_raises(self, monkeypatch):
        self._set_global(monkeypatch, True)
        with pytest.raises(ValueError):
            self._service()._resolve_policy({'intent': 'archive'})


class TestCaseConsistencyPayload:
    """预检/执行共用的回执结构：缺失集 = 差集；不可见单列；超限截断"""

    @staticmethod
    def _service_with(monkeypatch, availability):
        from task_service.application.task import data_transfer_import_service as mod
        monkeypatch.setattr(mod.transfer_repository, 'fetch_case_availability',
                            lambda case_ids, *a, **k: availability)
        return mod.DataTransferImportService()

    def test_missing_ids_exactly_the_diff(self, monkeypatch):
        service = self._service_with(monkeypatch, {
            'available': {'c1'}, 'missing': {'c2', 'c3'}, 'invisible': set()})
        result = service._case_consistency(_case_ref_rows('c1', 'c2', 'c3'), required=True)
        assert result['required'] is True
        assert result['complete'] is False
        assert set(result['missingCaseIds']) == {'c2', 'c3'}
        assert result['missingCount'] == 2
        assert result['truncated'] is False
        assert result['invisibleCaseIds'] == []

    def test_referenced_but_unreferenced_ids_not_reported(self, monkeypatch):
        """只按 task_case_relations 引用判定，结果行的 device/api 不外溢成用例缺口"""
        service = self._service_with(monkeypatch, {
            'available': {'c1'}, 'missing': set(), 'invisible': set()})
        result = service._case_consistency(_case_ref_rows('c1'), required=True)
        assert result['complete'] is True
        assert result['missingCaseIds'] == []

    def test_invisible_case_counted_as_missing_but_listed(self, monkeypatch):
        service = self._service_with(monkeypatch, {
            'available': {'c1'}, 'missing': set(), 'invisible': {'c9'}})
        result = service._case_consistency(_case_ref_rows('c1', 'c9'), required=True)
        assert result['complete'] is False
        assert result['missingCaseIds'] == ['c9']
        assert result['invisibleCaseIds'] == ['c9']

    def test_list_capped_with_truncated_flag(self, monkeypatch):
        missing = {f'c{i}' for i in range(600)}
        service = self._service_with(monkeypatch, {
            'available': set(), 'missing': missing, 'invisible': set()})
        result = service._case_consistency(_case_ref_rows(*missing), required=True)
        assert len(result['missingCaseIds']) == 500
        assert result['missingCount'] == 600
        assert result['truncated'] is True


class TestWarningCompatibility:
    """开关关闭时 warning 文案保持现状（验收 3）；未校验时追加固定告警"""

    @staticmethod
    def _warnings(monkeypatch, required=True):
        from task_service.application.task import data_transfer_import_service as mod
        monkeypatch.setattr(mod.transfer_repository, 'fetch_existing_case_ids',
                            lambda case_ids, *a, **k: set())
        return mod.DataTransferImportService()._build_warnings(
            _case_ref_rows('c1'), required)

    def test_missing_case_warning_text_unchanged(self, monkeypatch):
        warnings = self._warnings(monkeypatch)
        assert warnings == [
            "目标库缺少 1 个测试用例（['c1']），"
            "导入后该任务无法重新执行，结果/报告查看不受影响"]

    def test_unchecked_appends_skip_warning(self, monkeypatch):
        warnings = self._warnings(monkeypatch, required=False)
        assert warnings[-1] == 'restore 意图未校验用例一致性，导入后无法重新执行'

    def test_required_has_no_skip_warning(self, monkeypatch):
        """INT-1870：restore + 显式 true 时校验已执行，不得再写「未校验」文案"""
        warnings = self._warnings(monkeypatch, required=True)
        assert all('未校验用例一致性' not in w for w in warnings)
