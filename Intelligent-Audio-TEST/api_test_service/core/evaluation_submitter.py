# -*- coding: utf-8 -*-
"""用例评估入队 — 流式道各执行器共用（INT-1790 提库）。

评估入参口径与 WS 会话（`RealtimeSessionExecutor._submit_evaluation`）一致：
`algorithm_params` / `reference_params` / `algorithm_type` 经算法服务
`extract_case_all_params` 展开后，只取 `evaluation` 段，补用例级
`device_type`（physical / http_api / websocket_api），
连同任务与结果 id 提交 evaluation_service 评估队列（异步入队，不阻塞执行收尾）。

INT-1790（A2）把原方法提库：按轮次切（WS）与按事件切（SSE）两条流式策略共用
同一实现，避免两份入参口径漂移。
"""
from shared.utils.dto_utils import dto_to_dict
from api_test_service.infrastructure.acl import (
    AlgorithmQueryAclRepositoryImpl,
    EvaluationAclRepositoryImpl,
)

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_evaluation_acl = EvaluationAclRepositoryImpl()
_algo_acl = AlgorithmQueryAclRepositoryImpl()


def submit_case_evaluation(*, task_id, result_id, test_case_id,
                           algorithm_result, case_algorithm_params=None,
                           reference_params=None, algorithm_type=None,
                           device_type=None, api_id=None, log=None, acl=None):
    """按用例把结果提交评估队列（result_id 且全轮成功时由执行器调用）

    ``device_type``：用例级执行路由（physical / http_api / websocket_api），
    评估侧按该路由判定物理/API 口径。
    ``api_id``：结果所属 API 实例（评估映射按「策略 + 实例覆盖」解析）。
    ``acl``：评估服务 ACL 端口（缺省用本模块单例）。保持可注入是为了既有集成
    测试的替身注入点（经执行器模块的 `_evaluation_acl` 注入）。
    """
    from shared.models.common_enums import DeviceType

    acl = acl or _evaluation_acl
    algorithm_type = algorithm_type or 'translation'
    full_case_params = {
        'algorithm_params': case_algorithm_params or {},
        'reference_params': reference_params or {},
        'algorithm_type': algorithm_type,
        'api_id': api_id,
    }
    all_params = dto_to_dict(
        _algo_acl.extract_case_all_params(full_case_params)) or {}
    # 算法服务不可达时 ACL 回退 ExtractedCaseParamsDTO()（evaluation=None），
    # 键存在但值为 None，get 默认值不生效 → 显式 None 兜底（INT-119）
    eval_params = (all_params.get('evaluation') or {}) \
        if isinstance(all_params, dict) else {}
    eval_params['algorithm_type'] = algorithm_type
    device_type = device_type or DeviceType.HTTP_API.value
    eval_params['device_type'] = device_type

    acl.submit_evaluate_case(
        task_id=task_id,
        result_id=result_id,
        test_case_id=test_case_id,
        algorithm_result=algorithm_result,
        eval_params=eval_params,
        device_type=device_type,
    )
    if callable(log):
        log('INFO', f"结果 {result_id} 已提交评估队列（device_type={device_type}）")
