# -*- coding: utf-8 -*-
"""查询处理器 (Query Handlers) - CQRS 读模型处理器。

重要原则：通过 task_read_model / task_repository 查询，不走 ExecutionEngine，
也不直接依赖 ORM。读模型关注查询效率和返回 DTO，不返回领域聚合根。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from task_service.application.queries.task_queries import (
    GetTaskQuery,
    ListTasksQuery,
    GetTaskProgressQuery,
    GetTaskCasesQuery,
    ListTasksConfigQuery,
    GetTaskDetailQuery,
    GetTaskProgressDetailedQuery,
    GetTaskStatsQuery,
    GetCaseDetailQuery,
    GetCaseResultsQuery,
    ListTestCasesQuery,
    GetTestCaseDetailQuery,
    GetTestCaseStatsQuery,
    GetTestCaseTagsQuery,
    GetTestCaseRefParamsQuery,
    FetchCaseIdsQuery,
    CheckAudioReferencesQuery,
    ListTagCategoriesQuery,
    GetTagCategoryQuery,
    ListTagsQuery,
    ListTagNamesQuery,
    GetTagQuery,
    GetTagsByCategoryQuery,
    ListEvaluationStrategiesQuery,
    GetEvaluationStrategyQuery,
)
from task_service.infrastructure.persistence.task_repository import task_repository
from task_service.infrastructure.read_models.task_read_model import task_read_model


def _enrich_task_dto(task_dto: Optional[Dict[str, Any]],
                     task_id: int,
                     include_cases: bool = False) -> Optional[Dict[str, Any]]:
    """在读模型返回的 task DTO 基础上补充关联用例/设备/API 信息。

    task_read_model.find_by_id 返回的 DTO 不含 cases/api_ids/device_ids，
    这里通过 task_repository 的读方法补齐，保持 handler 返回结构不变。
    """
    if task_dto is None:
        return None

    if include_cases:
        case_entities = task_repository.get_cases(task_id)
        task_dto['cases'] = [
            {
                'id': c.id,
                'task_id': c.task_id,
                'test_case_id': c.test_case_id,
                'status': c.status,
                'execution_status': c.execution_status,
                'evaluation_status': c.evaluation_status,
                'started_at': c.started_at.isoformat() if c.started_at else None,
                'completed_at': c.completed_at.isoformat() if c.completed_at else None,
                'duration': c.duration,
                'error_message': c.error_message,
            }
            for c in case_entities
        ]

    task_dto['api_ids'] = task_repository.get_api_ids(task_id)
    task_dto['device_ids'] = task_repository.get_device_ids(task_id)
    return task_dto


class TaskQueryHandler:
    """任务查询处理器。

    所有读操作通过此类入口，委托 task_read_model / task_repository 查询。
    查询处理器无状态，可安全并发调用。
    """

    def __init__(self):
        self._task_query_service = None
        self._testcase_query_service = None
        self._tag_crud_service = None
        self._evaluation_strategy_query_service = None

    @property
    def task_query_service(self):
        """延迟加载 task_query_service 旧服务（过渡期兼容层）。"""
        if self._task_query_service is None:
            from task_service.application.task.task_query_service import task_query_service
            self._task_query_service = task_query_service
        return self._task_query_service

    @property
    def testcase_query_service(self):
        """延迟加载 testcase_query_service 旧服务（过渡期兼容层）。"""
        if self._testcase_query_service is None:
            from task_service.application.testcase.testcase_crud_service import testcase_crud_service
            self._testcase_query_service = testcase_crud_service
        return self._testcase_query_service

    @property
    def tag_crud_service(self):
        """延迟加载 tag_crud_service 旧服务（过渡期兼容层）。"""
        if self._tag_crud_service is None:
            from task_service.application.testcase.tag_crud_service import tag_crud_service
            self._tag_crud_service = tag_crud_service
        return self._tag_crud_service

    @property
    def evaluation_strategy_query_service(self):
        """延迟加载 evaluation_strategy_query_service（INT-590 评估策略读侧）。"""
        if self._evaluation_strategy_query_service is None:
            from task_service.application.evaluation_strategy.evaluation_strategy_query_service import (
                evaluation_strategy_query_service,
            )
            self._evaluation_strategy_query_service = evaluation_strategy_query_service
        return self._evaluation_strategy_query_service

    def handle_get_task(self, query: GetTaskQuery) -> Optional[Dict[str, Any]]:
        """处理获取单个任务详情查询。

        Returns:
            任务 DTO 字典，任务不存在返回 None。
        """
        task_dto = task_read_model.find_by_id(query.task_id)
        if task_dto is None:
            return None
        return _enrich_task_dto(task_dto, query.task_id, query.include_cases)

    def handle_list_tasks(self, query: ListTasksQuery) -> Dict[str, Any]:
        """处理任务列表查询（带过滤和分页）。

        Returns:
            {'items': [...], 'total': N, 'page': P, 'page_size': S}
        """
        return task_read_model.search(
            status=query.status,
            algorithm_type=query.algorithm_type,
            created_by=query.created_by,
            include_deleted=query.include_deleted,
            page=query.page,
            page_size=query.page_size,
        )

    def handle_get_task_progress(self, query: GetTaskProgressQuery) -> Optional[Dict[str, Any]]:
        """处理获取任务进度查询（轻量级）。

        仅查询进度相关字段，避免加载完整任务对象。
        """
        return task_read_model.get_progress(query.task_id)

    def handle_get_task_cases(self, query: GetTaskCasesQuery) -> Dict[str, Any]:
        """处理获取任务下用例执行状态查询。"""
        return task_read_model.list_cases(
            task_id=query.task_id,
            status=query.status,
            page=query.page,
            page_size=query.page_size,
        )

    # ==================================================================
    # task 域查询（gRPC servicer 入口）
    # 委托 task_query_service 旧服务作为过渡，返回 dict: {success, message, data, code?}
    # ==================================================================

    def handle_list_tasks_config(self, query: ListTasksConfigQuery) -> Dict[str, Any]:
        """处理任务列表查询（gRPC servicer 用）。委托 task_query_service.list_tasks。"""
        return self.task_query_service.list_tasks(
            page=query.page,
            per_page=query.per_page,
            status=query.status,
            device_type=query.device_type,
            algorithm_type=query.algorithm_type,
            search=query.search,
            start_date=query.start_date,
            end_date=query.end_date,
            favorite=query.favorite,
            deleted=query.deleted,
            user_id=query.user_id,
            evaluation_status=query.evaluation_status,
            merged=query.merged,
            cherry_pick=query.cherry_pick,
            execution_status=query.execution_status,
            task_type=query.task_type,
            stats=query.stats,
            visibility=query.visibility,
        )

    def handle_get_task_detail(self, query: GetTaskDetailQuery) -> Dict[str, Any]:
        """处理任务详情查询（含时间预估）。委托 task_query_service.get_task_detail。"""
        return self.task_query_service.get_task_detail(query.task_id)

    def handle_check_audio_references(self, query: CheckAudioReferencesQuery) -> Dict[str, Any]:
        """处理音频删除引用检查查询（INT-1306）。

        按 audio_id 集合查被测试用例/任务引用计数，替代调用方逐页
        ListTestCases / ListTasks 全量拉取。委托 task_query_service。
        """
        return self.task_query_service.check_audio_references(query.audio_ids)

    def handle_get_task_progress_detailed(self, query: GetTaskProgressDetailedQuery) -> Dict[str, Any]:
        """处理任务实时进度查询（详细版）。委托 task_query_service.get_task_progress。"""
        return self.task_query_service.get_task_progress(query.task_id)

    def handle_get_task_stats(self, query: GetTaskStatsQuery) -> Dict[str, Any]:
        """处理任务统计信息查询。委托 task_query_service.get_task_stats。"""
        return self.task_query_service.get_task_stats(query.task_id)

    def handle_get_case_detail(self, query: GetCaseDetailQuery) -> Dict[str, Any]:
        """处理任务用例执行详情查询。委托 task_query_service.get_case_detail。"""
        return self.task_query_service.get_case_detail(query.task_id, query.case_id)

    def handle_get_case_results(self, query: GetCaseResultsQuery) -> Dict[str, Any]:
        """处理任务用例执行结果查询。委托 task_query_service.get_case_results。"""
        return self.task_query_service.get_case_results(query.task_id, query.case_id)

    # ==================================================================
    # testcase 域查询（gRPC servicer 入口）
    # 委托 testcase_query_service 旧服务作为过渡
    # ==================================================================

    def handle_list_testcases(self, query: ListTestCasesQuery) -> Dict[str, Any]:
        """处理测试用例列表查询。委托 testcase_crud_service.list_testcases。"""
        return self.testcase_query_service.list_testcases(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
            tag=query.tag,
            group_id=query.group_id,
            algorithm_type=query.algorithm_type,
            test_type=query.test_type,
            view=query.view,
            include_deleted=query.include_deleted,
            dimension_id=query.dimension_id,
            favorite=query.favorite,
            only_deleted=query.only_deleted,
            user_id=query.user_id,
            lab_ids=query.lab_ids,
            visibility=query.visibility,
        )

    # ==================================================================
    # 收藏 / 回收站查询（INT-141）
    # ==================================================================

    def handle_list_favorite_ids(self, query) -> Dict[str, Any]:
        """处理收藏实体 ID 列表查询。委托 favorite_trash_service.list_favorite_ids。"""
        from task_service.application.favorite_trash_service import favorite_trash_service
        return favorite_trash_service.list_favorite_ids(query.user_id, query.entity_type)

    def handle_list_deleted_tasks(self, query) -> Dict[str, Any]:
        """处理回收站任务列表查询。委托 favorite_trash_service.list_deleted_tasks。"""
        from task_service.application.favorite_trash_service import favorite_trash_service
        return favorite_trash_service.list_deleted_tasks(
            query.page, query.per_page, query.search)

    def handle_list_deleted_testcases(self, query) -> Dict[str, Any]:
        """处理回收站用例列表查询。委托 favorite_trash_service.list_deleted_testcases。"""
        from task_service.application.favorite_trash_service import favorite_trash_service
        return favorite_trash_service.list_deleted_testcases(
            query.page, query.per_page, query.keyword)

    def handle_get_testcase_detail(self, query: GetTestCaseDetailQuery) -> Dict[str, Any]:
        """处理测试用例详情查询。委托 testcase_crud_service.get_testcase_detail。"""
        return self.testcase_query_service.get_testcase_detail(query.tc_id)

    def handle_get_testcase_stats(self, query: GetTestCaseStatsQuery) -> Dict[str, Any]:
        """处理测试用例统计信息查询。委托 testcase_crud_service.get_testcase_stats。"""
        return self.testcase_query_service.get_testcase_stats()

    def handle_get_testcase_tags(self, query: GetTestCaseTagsQuery) -> Dict[str, Any]:
        """处理获取所有标签名列表查询。委托 testcase_crud_service.get_testcase_tags。"""
        return self.testcase_query_service.get_testcase_tags()

    def handle_get_testcase_ref_params(self, query: GetTestCaseRefParamsQuery) -> Dict[str, Any]:
        """处理获取用例参考参数查询。委托 testcase_crud_service.get_testcase_ref_params。"""
        return self.testcase_query_service.get_testcase_ref_params(
            query.tc_id, query.round_number
        )

    def handle_fetch_case_ids(self, query: FetchCaseIdsQuery) -> Dict[str, Any]:
        """处理按筛选条件返回全量用例ID查询。委托 testcase_crud_service.fetch_case_ids。"""
        return self.testcase_query_service.fetch_case_ids(query.data or {})

    # ==================================================================
    # 评估策略查询（INT-590，gRPC servicer 入口）
    # 委托 evaluation_strategy_query_service（读侧，只读 ReadModel）
    # ==================================================================

    def handle_list_evaluation_strategies(self, query: ListEvaluationStrategiesQuery) -> Dict[str, Any]:
        """处理评估策略列表查询（含 referenced_case_count）。委托 query_service.list_strategies。"""
        return self.evaluation_strategy_query_service.list_strategies(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
            algorithm_type=query.algorithm_type,
            enabled=query.enabled,
        )

    def handle_get_evaluation_strategy(self, query: GetEvaluationStrategyQuery) -> Dict[str, Any]:
        """处理评估策略详情查询（含 referenced_case_count）。委托 query_service.get_strategy。"""
        return self.evaluation_strategy_query_service.get_strategy(query.strategy_id)

    # ==================================================================
    # tag 域查询（gRPC servicer 入口）
    # 委托 tag_crud_service 旧服务作为过渡
    # ==================================================================

    def handle_list_tag_categories(self, query: ListTagCategoriesQuery) -> Dict[str, Any]:
        """处理标签分类列表查询。委托 tag_crud_service.list_categories。"""
        return self.tag_crud_service.list_categories(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
        )

    def handle_get_tag_category(self, query: GetTagCategoryQuery) -> Dict[str, Any]:
        """处理获取单个标签分类查询。委托 tag_crud_service.get_category。"""
        return self.tag_crud_service.get_category(query.category_id)

    def handle_list_tags(self, query: ListTagsQuery) -> Dict[str, Any]:
        """处理标签列表查询（带分类过滤）。委托 tag_crud_service.list_tags。"""
        return self.tag_crud_service.list_tags(
            page=query.page,
            per_page=query.per_page,
            category_id=query.category_id,
            keyword=query.keyword,
        )

    def handle_list_tag_names(self, query: ListTagNamesQuery) -> Dict[str, Any]:
        """处理标签名称列表查询。委托 tag_crud_service.list_tag_names。"""
        return self.tag_crud_service.list_tag_names(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
        )

    def handle_get_tag(self, query: GetTagQuery) -> Dict[str, Any]:
        """处理获取单个标签查询。委托 tag_crud_service.get_tag。"""
        return self.tag_crud_service.get_tag(query.tag_id)

    def handle_get_tags_by_category(self, query: GetTagsByCategoryQuery) -> Dict[str, Any]:
        """处理获取按分类分组的标签查询。委托 tag_crud_service.get_tags_by_category。"""
        return self.tag_crud_service.get_tags_by_category()


# 模块级单例
task_query_handler = TaskQueryHandler()
