# -*- coding: utf-8 -*-
"""报告侧 task_id → 结果来源解析（引用方案 A 只读解析，INT-408）。

INT-339 挑选合并（cherry-pick）容器任务创建即 completed、自身无 test_results
行，报告查看侧按 task_id 直查的三条查询（对比/分组均值/日志下载）需先按
TaskCherryPickRelation 引用解析到源结果/源任务，否则容器列静默空值。

本模块统一三处模式的来源解析，避免在调用点重复实现；合并容器解析沿用
report_data_builder_task_mixin 的 TaskMergeRelation 展开先例。

红线：只读解析，绝不修改 test_results.task_id（引用方案 A，不改评估/任务域
契约）；容器结果在内存中映射回请求任务列，仅用于报告展示。

约定：gRPC helper 一律函数内延迟导入（对齐 _report_stats_query_mixin 等既有
惯例）——单测经 monkeypatch 替换 grpc_clients 属性时，延迟导入在调用时刻取
当前属性，可被正确拦截；模块级导入会冻结原始函数引用使补丁失效。
"""


def resolve_cherry_pick_sources(task_id):
    """解析 cherry-pick 容器任务的源结果引用（引用方案 A，INT-408）。

    非容器任务返回 None；容器任务返回 dict：
    - result_ids: 引用的源结果 id 列表（结果直查入口）
    - source_task_ids: 源任务 id 列表（日志/业务日志存储前缀入口，去重）

    依赖 _grpc_get_cherry_pick_relations 的容错约定：查询失败返回 []，
    调用方按「非挑选合并容器」回落普通链路，不抛异常。
    """
    from report_service.infrastructure.clients.grpc_clients import (
        _grpc_get_cherry_pick_relations,
    )
    relations = _grpc_get_cherry_pick_relations(task_id)
    if not relations:
        return None
    result_ids = [r.get('result_id') for r in relations if r.get('result_id') is not None]
    source_task_ids = list(dict.fromkeys(
        r.get('source_task_id') for r in relations if r.get('source_task_id') is not None))
    return {'result_ids': result_ids, 'source_task_ids': source_task_ids}


def resolve_merge_source_task_ids(task_id, expand_leaves=False):
    """解析合并容器任务的源任务 id 列表（TaskMergeRelation 展开先例）。

    Args:
        task_id: 合并容器任务 id
        expand_leaves: True 时递归展开链式合并为叶子源任务（对齐生成链结果口径）；
            保留 False 时返回直接源任务（对齐既有查看侧查询行为）。

    Returns:
        list[int]；非合并容器返回 []。
    """
    from report_service.infrastructure.clients.grpc_clients import (
        _grpc_get_task_merge_relations,
    )
    merge_relations = _grpc_get_task_merge_relations(task_id)
    if not merge_relations:
        return []
    source_task_ids = [r.get('source_task_id') for r in merge_relations]
    if expand_leaves:
        from report_service.application.services.report_data_builder_task_mixin import (
            ReportDataTaskMixin,
        )
        return ReportDataTaskMixin._expand_leaf_source_task_ids(source_task_ids)
    return source_task_ids
