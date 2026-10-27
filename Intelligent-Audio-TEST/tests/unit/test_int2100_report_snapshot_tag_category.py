# -*- coding: utf-8 -*-
"""INT-2100 专项：报告快照透传标签分类（extract_case_categories_and_tags 输出 category_id/category_name）。

原缺陷：`extract_case_categories_and_tags` 构建 `case_tags_list` 时只取 tag 的
`id`/`name`，丢弃 `category_id`/`category_name` → 新生成报告 `all_case_tags` 条目
无分类，前端报告筛选 taxonomy 无法按分类展示（主库实测 0 份报告含 category）。

修复（本文件覆盖验收①与验收②）：
- tag 对象（dict/ORM）里的 `category_id`/`category_name` 一并写入 `case_tags_list`
  条目（条目结构 `{id, name, category_id, category_name}`，与 task_service
  tag_crud_service._tag_to_dict 字段对齐）；
- 无分类 tag 保持 `category_id`/`category_name` 为 null（前端「未分类」兜底）；
- 真实路径（INT-2100 返工，数据源契约裁定路线 A 2026-10-27）：task_service 契约
  把用例 tags 序列化为字符串名列表，报告域按名经 `GetTagsByCategory` 单次调用
  解析分类；解析不到的字符串 tag 不丢、分类字段为 null（前端「未分类」兜底），
  与「task_service 交付 tag dict」路线 B 前向兼容；
- `case_categories_list`（用例分组）逻辑不变，无标签缺省兜底结构统一为 4 字段。

验收③（既有报告生成回归不破坏）由测试矩阵 + 报告主生成链集成覆盖。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import report_service.application.services.report_query_builder as qb_mod
from report_service.application.services.report_query_builder import (
    ReportQueryBuilder,
)


# ======================================================================
# 纯函数：extract_case_categories_and_tags 分类透传
# ======================================================================

def _case(cid='TC-1', group=None, tags=None):
    tc = {'id': cid, 'name': f'用例{cid}', 'config': {}}
    if group is not None:
        tc['group'] = group
    if tags is not None:
        tc['tags'] = tags
    return tc


class TestExtractTagCategoryPassThrough:
    """tag 对象（dict/ORM）中的 category_id/category_name 透传进 case_tags_list。"""

    def test_dict_tag_with_category(self):
        tags = [{'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': '标签分类X'}]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=tags)])
        assert tag_list == [
            {'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': '标签分类X'}]

    def test_dict_tag_without_category_keeps_null(self):
        tags = [{'id': 't2', 'name': '标签2'}]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=tags)])
        assert tag_list == [
            {'id': 't2', 'name': '标签2', 'category_id': None, 'category_name': None}]

    def test_orm_style_tag_with_category(self):
        """兼容 ORM 载荷（SimpleNamespace 带 category_id/category_name 属性）。"""
        tags = [SimpleNamespace(id=3, name='标签3', category_id=6, category_name='分类Y')]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=tags)])
        assert tag_list == [
            {'id': 3, 'name': '标签3', 'category_id': 6, 'category_name': '分类Y'}]

    def test_orm_style_tag_without_category_keeps_null(self):
        """ORM 载荷无 category 属性时保持 null（不因属性缺失报错）。"""
        tags = [SimpleNamespace(id=4, name='标签4')]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=tags)])
        assert tag_list == [
            {'id': 4, 'name': '标签4', 'category_id': None, 'category_name': None}]

    def test_dedup_keeps_first_occurrence_category(self):
        """同一 tag 跨用例去重：首现条目的分类保留（后续重复不覆盖）。"""
        cases = [
            _case(tags=[{'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': '标签分类X'}]),
            _case(cid='TC-2', tags=[{'id': 't1', 'name': '标签1'}]),
        ]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(cases)
        assert tag_list == [
            {'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': '标签分类X'}]

    def test_no_tags_default_fallback(self):
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags([_case()])
        assert tag_list == [
            {'id': 'default_tag', 'name': '无标签',
             'category_id': None, 'category_name': None}]

    def test_case_categories_list_unchanged(self):
        """回归：用例分组（case_categories_list）逻辑与结构不变。"""
        cases = [
            _case(group={'id': 'g1', 'name': '分组1'},
                  tags=[{'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': 'X'}]),
            _case(cid='TC-2', group={'id': 'g1', 'name': '分组1'}, tags=[]),
        ]
        cat_list, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(cases)
        assert cat_list == [{'id': 'g1', 'name': '分组1'}]
        assert tag_list == [
            {'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': 'X'}]

    def test_mapping_input_normalized(self):
        """INT-419 兼容：{id: dict} 映射入参照常归一，分类透传同样生效。"""
        tc_map = {
            'TC-1': {'id': 'TC-1', 'name': '用例', 'config': {},
                     'tags': [{'id': 't1', 'name': '标签1', 'category_id': 5,
                               'category_name': '标签分类X'}]},
        }
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(tc_map)
        assert tag_list == [
            {'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': '标签分类X'}]


# ======================================================================
# 真实路径（验收②）：字符串 tag 按名经 GetTagsByCategory 解析分类
# ======================================================================

# GetTagsByCategory 载荷形状（tag_crud_service.get_tags_by_category 的 data 信封）
_TAGS_BY_CATEGORY_PAYLOAD = {
    'items': [
        {'category': {'id': 5, 'name': '标签分类X'},
         'tags': [{'id': 't1', 'name': '冒烟', 'category_id': 5,
                   'category_name': '标签分类X'},
                  {'id': 't2', 'name': '回归', 'category_id': 5,
                   'category_name': '标签分类X'}]},
        {'category': None,
         'tags': [{'id': 't3', 'name': '未分类标签',
                   'category_id': None, 'category_name': None}]},
    ],
    'total': 2,
    'page': 1,
    'per_page': 2,
    'pages': 1,
}


class TestExtractStringTagNameResolution:
    """字符串 tag 按名解析（INT-2100 返工路线 A）。

    真实 task_service 契约把用例 tags 序列化为字符串名列表，报告域经
    GetTagsByCategory 单次调用建 name → 分类映射；解析不到不丢标签、分类为 null。
    """

    def test_string_tags_resolved_by_name(self, monkeypatch):
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: _TAGS_BY_CATEGORY_PAYLOAD)
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=['冒烟', '回归'])])
        assert tag_list == [
            {'id': 't1', 'name': '冒烟', 'category_id': 5, 'category_name': '标签分类X'},
            {'id': 't2', 'name': '回归', 'category_id': 5, 'category_name': '标签分类X'}]

    def test_unresolvable_string_tags_not_lost(self, monkeypatch):
        """解析不到的字符串 tag 不丢：id/category 为 null，仍输出条目。"""
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: _TAGS_BY_CATEGORY_PAYLOAD)
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=['冒烟', '不存在的标签'])])
        assert tag_list == [
            {'id': 't1', 'name': '冒烟', 'category_id': 5, 'category_name': '标签分类X'},
            {'id': None, 'name': '不存在的标签',
             'category_id': None, 'category_name': None}]

    def test_resolved_tag_without_category_keeps_null(self, monkeypatch):
        """映射命中但本身无分类（category_id 为 null）→ 分类字段为 null。"""
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: _TAGS_BY_CATEGORY_PAYLOAD)
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=['未分类标签'])])
        assert tag_list == [
            {'id': 't3', 'name': '未分类标签',
             'category_id': None, 'category_name': None}]

    def test_mixed_dict_and_string_tags(self, monkeypatch):
        """dict tag 与字符串 tag 混用：dict 直接透传，字符串按名解析。"""
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: _TAGS_BY_CATEGORY_PAYLOAD)
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=[{'id': 't9', 'name': '手工标签', 'category_id': 9,
                          'category_name': '分类9'}, '冒烟'])])
        assert tag_list == [
            {'id': 't9', 'name': '手工标签', 'category_id': 9, 'category_name': '分类9'},
            {'id': 't1', 'name': '冒烟', 'category_id': 5, 'category_name': '标签分类X'}]

    def test_string_tags_dedup_by_resolved_id(self, monkeypatch):
        """同一字符串 tag 跨用例去重：按解析出的 id 去重，保留首现条目。"""
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: _TAGS_BY_CATEGORY_PAYLOAD)
        cases = [
            _case(tags=['冒烟']),
            _case(cid='TC-2', tags=['冒烟']),
        ]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(cases)
        assert tag_list == [
            {'id': 't1', 'name': '冒烟', 'category_id': 5, 'category_name': '标签分类X'}]

    def test_unresolvable_string_tags_dedup_by_name(self, monkeypatch):
        """解析不到的字符串 tag 按名去重：同名只输出一次，仍不丢。"""
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: _TAGS_BY_CATEGORY_PAYLOAD)
        cases = [
            _case(tags=['未知标签']),
            _case(cid='TC-2', tags=['未知标签']),
        ]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(cases)
        assert tag_list == [
            {'id': None, 'name': '未知标签',
             'category_id': None, 'category_name': None}]

    def test_lazy_single_call_when_string_tags_present(self, monkeypatch):
        """仅遇字符串 tag 时惰性触发，整批只调用一次 GetTagsByCategory。"""
        calls = []
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: calls.append(1) or _TAGS_BY_CATEGORY_PAYLOAD)
        cases = [
            _case(tags=['冒烟']),
            _case(cid='TC-2', tags=[{'id': 't9', 'name': '手工标签'}]),
            _case(cid='TC-3', tags=['回归']),
        ]
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(cases)
        assert len(calls) == 1
        assert tag_list == [
            {'id': 't1', 'name': '冒烟', 'category_id': 5, 'category_name': '标签分类X'},
            {'id': 't9', 'name': '手工标签', 'category_id': None, 'category_name': None},
            {'id': 't2', 'name': '回归', 'category_id': 5, 'category_name': '标签分类X'}]

    def test_no_gRPC_call_when_no_string_tags(self, monkeypatch):
        """全 dict/ORM tag 时不触发 GetTagsByCategory（惰性）。"""
        calls = []
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: calls.append(1) or _TAGS_BY_CATEGORY_PAYLOAD)
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=[{'id': 't1', 'name': '标签1', 'category_id': 5,
                          'category_name': 'X'}])])
        assert calls == []
        assert tag_list == [
            {'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': 'X'}]

    def test_gRPC_failure_falls_back_all_unresolved(self, monkeypatch):
        """GetTagsByCategory 失败（返回 None）→ 字符串 tag 全部兜底：不丢、分类 null。"""
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category', lambda: None)
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=['冒烟', '回归'])])
        assert tag_list == [
            {'id': None, 'name': '冒烟', 'category_id': None, 'category_name': None},
            {'id': None, 'name': '回归', 'category_id': None, 'category_name': None}]

    def test_string_tags_all_resolved_no_default_fallback(self, monkeypatch):
        """字符串 tag 全部解析命中 → 不落 default_tag 兜底。"""
        monkeypatch.setattr(qb_mod, '_grpc_get_tags_by_category',
                            lambda: _TAGS_BY_CATEGORY_PAYLOAD)
        _, tag_list = ReportQueryBuilder.extract_case_categories_and_tags(
            [_case(tags=['冒烟'])])
        assert tag_list == [
            {'id': 't1', 'name': '冒烟', 'category_id': 5, 'category_name': '标签分类X'}]


# ======================================================================
# 报告主生成链集成：_prepare_report_data 产出的 case_tags_list（→ all_case_tags）
# ======================================================================

_DIMS = [
    {'id': 1, 'name': '准确率', 'statistic_method': 'average',
     'agg_denominator': 'case', 'exclude_rounds': []},
]
_CATEGORIZED_CASE = {
    'id': 'TC-1',
    'name': '带分类标签用例（INT2100）',
    'config': {},
    'group': {'id': 'g1', 'name': 'INT2100分组'},
    'tags': [{'id': 't1', 'name': 'INT2100标签', 'category_id': 5,
              'category_name': 'INT2100标签分类'}],
}


class TestPrepareReportDataAllCaseTags:
    """_prepare_report_data 快照链路：all_case_tags（case_tags_list）含分类。"""

    def _run_prepare(self, task_cases, tags_payload=None):
        import report_service.application.services.report_task_generator as gen_mod
        import report_service.application.services.report_utils as utils_mod
        import report_service.application.services.report_query_builder as qb_mod

        captured = {}
        results = [{'id': 101, 'test_case_id': 'TC-1',
                    'execution_status': 'completed'}]

        def _dim_batch(ids, **_):
            dim_map = {rid: [{'dimension_id': 1, 'dimension_value': 80.0,
                              'evaluation_status': 'completed'}]
                       for rid in ids}
            return dim_map, [{'id': 1, 'name': '准确率'}]

        builder_stubs = {
            '_get_source_task_ids': lambda t: [],
            '_get_dimension_results_batch': staticmethod(_dim_batch),
            '_calculate_summary_dimensions': lambda stats: [],
            '_get_task_test_cases': lambda ids: (task_cases, ['TC-1']),
            '_get_task_resources': lambda ids: (['dev'], [], [1], []),
            '_get_resource_result_types_batch': lambda *a, **k: ({}, {}),
            '_build_resources_list': lambda *a, **k: ['dev-1'],
            '_build_all_metrics': lambda dims: [{'id': 1, 'name': '准确率'}],
            '_build_case_data': lambda *a, **k: [],
        }
        gen_stubs = {
            '_collect_field_mappings_snapshot': lambda *a, **k: {},
        }
        utils_stubs = {
            'calculate_core_metrics': lambda **k: (
                captured.__setitem__('core_results', k['results']),
                {'metric_data': [], 'tag_metric_data': [], 'raw_data': [],
                 'case_type_stats': [], 'resources': []})[1],
            'build_resource_headers': lambda **k: [],
            'calculate_device_api_stats': lambda **k: ([], []),
        }

        originals_builder = {k: getattr(gen_mod.ReportDataBuilder, k)
                             for k in builder_stubs}
        originals_gen = {k: getattr(gen_mod.ReportTaskGenerator, k)
                         for k in gen_stubs}
        originals_utils = {k: getattr(utils_mod.ReportUtils, k)
                           for k in utils_stubs}
        originals_mod = {
            '_grpc_list_dimensions_all': getattr(gen_mod, '_grpc_list_dimensions_all'),
            '_grpc_get_devices_by_ids': getattr(gen_mod, '_grpc_get_devices_by_ids'),
            '_grpc_get_apis_by_ids': getattr(gen_mod, '_grpc_get_apis_by_ids'),
        }
        saved_extract = qb_mod.ReportQueryBuilder.extract_case_categories_and_tags
        saved_grpc_tags = qb_mod._grpc_get_tags_by_category

        task = {'id': 1, 'name': 't', 'status': 'completed', 'total_cases': 1,
                'completed_cases': 1, 'failed_cases': 0}

        try:
            for name, fn in builder_stubs.items():
                setattr(gen_mod.ReportDataBuilder, name, fn)
            for name, fn in gen_stubs.items():
                setattr(gen_mod.ReportTaskGenerator, name, staticmethod(fn))
            for name, fn in {
                '_grpc_list_dimensions_all': lambda: _DIMS,
                '_grpc_get_devices_by_ids': lambda ids: {},
                '_grpc_get_apis_by_ids': lambda ids: {},
            }.items():
                setattr(gen_mod, name, fn)
            for name, fn in utils_stubs.items():
                setattr(utils_mod.ReportUtils, name, staticmethod(fn))
            # INT-2100：保留真实 extract_case_categories_and_tags，验证分类透传
            # 进入快照链路（不替换为 ([], [])）。字符串 tag 路径（路线 A）按名经
            # GetTagsByCategory 解析：tags_payload 提供则替换该 gRPC helper。
            if tags_payload is not None:
                qb_mod._grpc_get_tags_by_category = lambda: tags_payload
            captured['data'] = gen_mod.ReportTaskGenerator._prepare_report_data(
                task, 1, results)
        finally:
            for name, fn in originals_builder.items():
                setattr(gen_mod.ReportDataBuilder, name, fn)
            for name, fn in originals_gen.items():
                setattr(gen_mod.ReportTaskGenerator, name, fn)
            for name, fn in originals_utils.items():
                setattr(utils_mod.ReportUtils, name, fn)
            for name, fn in originals_mod.items():
                setattr(gen_mod, name, fn)
            qb_mod.ReportQueryBuilder.extract_case_categories_and_tags = saved_extract
            qb_mod._grpc_get_tags_by_category = saved_grpc_tags
        return captured['data']

    def test_all_case_tags_carry_category(self):
        data = self._run_prepare([_CATEGORIZED_CASE])
        assert data is not None
        # all_case_tags 源 = case_tags_list（report_task_generator._build_task_summary）
        assert data['case_tags_list'] == [
            {'id': 't1', 'name': 'INT2100标签', 'category_id': 5,
             'category_name': 'INT2100标签分类'}]
        # 分组快照不受影响
        assert data['case_categories_list'] == [
            {'id': 'g1', 'name': 'INT2100分组'}]

    def test_uncategorized_tag_falls_back_null(self):
        case = {'id': 'TC-1', 'name': '无分类标签用例', 'config': {},
                'group': {'id': 'g1', 'name': '分组1'},
                'tags': [{'id': 't2', 'name': '无分类标签'}]}
        data = self._run_prepare([case])
        assert data is not None
        assert data['case_tags_list'] == [
            {'id': 't2', 'name': '无分类标签',
             'category_id': None, 'category_name': None}]

    def test_all_case_tags_string_tags_resolved_by_name(self):
        """真实路径（路线 A）：字符串 tag 列表经 GetTagsByCategory 载荷按名解析，
        解析不到的字符串 tag 不丢、分类为 null，进入 all_case_tags 快照。"""
        case = {'id': 'TC-1', 'name': '字符串标签用例', 'config': {},
                'group': {'id': 'g1', 'name': '分组1'},
                'tags': ['冒烟', '未知标签']}
        data = self._run_prepare([case], tags_payload=_TAGS_BY_CATEGORY_PAYLOAD)
        assert data is not None
        assert data['case_tags_list'] == [
            {'id': 't1', 'name': '冒烟', 'category_id': 5,
             'category_name': '标签分类X'},
            {'id': None, 'name': '未知标签',
             'category_id': None, 'category_name': None}]
        # 分组快照不受影响
        assert data['case_categories_list'] == [{'id': 'g1', 'name': '分组1'}]


# ======================================================================
# 二次对比链：_prepare_secondary_data 的 case_tags_list（透传 + 空回落 4 字段）
# ======================================================================

class TestSecondaryCompareChainTagCategory:
    """二次对比链（_prepare_secondary_data）快照透传分类 + 空 test_cases 回落。

    INT-2100 返工项（打回 P2）：`report_compare_generator_secondary_mixin.py`
    `if not case_tags_list:` 缺省 `default_tag` 条目此前为 2 字段
    （缺 `category_id`/`category_name` 键），与卡面「条目结构
    {id, name, category_id, category_name}」及「无分类 tag 保持 null」不符；
    本次修复为 4 字段（category 为 null），与 `report_query_builder.py` 内部兜底一致。
    """

    def _run_prepare_secondary(self, monkeypatch, task_cases):
        import report_service.application.services.report_compare_helpers as rch_mod
        import report_service.application.services.report_data_builder as rdb_mod
        import report_service.application.services.report_helpers as rh_mod
        import report_service.application.services.report_task_generator as gen_mod
        import report_service.application.services.report_utils as utils_mod

        results = [{'id': 11, 'task_id': 1, 'test_case_id': 'TC-1',
                    'execution_status': 'completed'}]
        monkeypatch.setattr(rch_mod, '_grpc_get_test_results_by_task_ids',
                            lambda task_ids: results)
        monkeypatch.setattr(rh_mod.ReportHelpers, 'get_resource_name',
                            staticmethod(lambda res, task=None,
                                         use_time_prefix=False: 'res-1'))
        monkeypatch.setattr(rch_mod.ReportCompareHelpers, '_get_task_type',
                            staticmethod(lambda tasks: 'secondary_compare'))
        monkeypatch.setattr(rch_mod.ReportCompareHelpers, '_build_all_dimensions',
                            staticmethod(lambda res_ids: (['dim1'], ['m1'], None)))
        monkeypatch.setattr(rch_mod.ReportCompareHelpers,
                            '_get_source_cases_from_reports',
                            staticmethod(lambda reports: []))
        monkeypatch.setattr(rch_mod.ReportCompareHelpers,
                            '_build_comparison_matrix_secondary',
                            staticmethod(lambda task_ids, reports,
                                         all_dimensions: {}))
        monkeypatch.setattr(rdb_mod.ReportDataBuilder, '_get_task_resources',
                            staticmethod(lambda task_ids:
                                         (['dev1'], ['api1'], [1], [2])))
        monkeypatch.setattr(rdb_mod.ReportDataBuilder,
                            '_get_dimension_results_batch',
                            staticmethod(lambda res_ids, include_body=False:
                                         ({11: []}, {})))
        # INT-2100：_get_task_test_cases 由各用例提供；extract_case_categories_and_tags
        # 保留真实实现，验证分类透传进入二次对比链 case_tags_list
        monkeypatch.setattr(rdb_mod.ReportDataBuilder, '_get_task_test_cases',
                            staticmethod(lambda task_ids:
                                         (task_cases, ['TC-1'])))
        monkeypatch.setattr(rdb_mod.ReportDataBuilder, '_build_case_data',
                            staticmethod(lambda *a, **k: []))
        monkeypatch.setattr(gen_mod.ReportTaskGenerator, '_mark_degraded_metrics',
                            staticmethod(lambda *a, **k: None))
        monkeypatch.setattr(utils_mod.ReportUtils, 'calculate_core_metrics',
                            staticmethod(lambda **kw: {
                                'metric_data': {'res-1': []},
                                'tag_metric_data': {},
                                'raw_data': {'res-1': {'dim1': []}},
                                'case_type_stats': [],
                                'resources': ['res-1'],
                                'aggregation_degraded': {},
                            }))
        monkeypatch.setattr(utils_mod.ReportUtils, 'build_resource_headers',
                            staticmethod(lambda **kw: ['res-1']))
        monkeypatch.setattr(utils_mod.ReportUtils, 'calculate_device_api_stats',
                            staticmethod(lambda **kw: ({}, {})))

        from report_service.application.services.report_compare_generator_secondary_mixin import (
            ReportSecondaryDataMixin,
        )
        return ReportSecondaryDataMixin._prepare_secondary_data(
            [7, 8], [{'id': 7}, {'id': 8}], [{'id': 1, 'config': {}}], [1])

    def test_secondary_compare_categorized_tags_pass_category(self, monkeypatch):
        case = {'id': 'TC-1', 'name': '二次对比带分类用例', 'config': {},
                'group': {'id': 'g1', 'name': '分组1'},
                'tags': [{'id': 't1', 'name': '标签1', 'category_id': 5,
                          'category_name': '标签分类X'}]}
        data, error = self._run_prepare_secondary(monkeypatch, [case])
        assert error is None
        assert data is not None
        assert data['case_tags_list'] == [
            {'id': 't1', 'name': '标签1', 'category_id': 5,
             'category_name': '标签分类X'}]
        assert data['case_categories_list'] == [{'id': 'g1', 'name': '分组1'}]

    def test_secondary_compare_uncategorized_tag_falls_back_null(self, monkeypatch):
        case = {'id': 'TC-1', 'name': '二次对比无分类用例', 'config': {},
                'group': {'id': 'g1', 'name': '分组1'},
                'tags': [{'id': 't2', 'name': '无分类标签'}]}
        data, error = self._run_prepare_secondary(monkeypatch, [case])
        assert error is None
        assert data is not None
        assert data['case_tags_list'] == [
            {'id': 't2', 'name': '无分类标签',
             'category_id': None, 'category_name': None}]

    def test_secondary_compare_empty_test_cases_default_four_fields(self, monkeypatch):
        """返工项：test_cases 为空时缺省 default_tag 为 4 字段（category 为 null）。"""
        data, error = self._run_prepare_secondary(monkeypatch, [])
        assert error is None
        assert data is not None
        assert data['case_tags_list'] == [
            {'id': 'default_tag', 'name': '无标签',
             'category_id': None, 'category_name': None}]
