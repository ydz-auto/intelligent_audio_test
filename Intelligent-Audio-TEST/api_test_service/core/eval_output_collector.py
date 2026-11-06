# -*- coding: utf-8 -*-
"""轮次评估输出收集 — 流式道各执行器共用（C0/C1/C2 口径的单一实现）。

把「一次切轮产出的输出 dict」按算法声明的 `field_path` 提取、按 param_mappings
映射成 `{target_param: value}`，再应用 `transform_type`（INT-1749），产物整体
写入 `rounds[i].output`。

INT-1790（A2）把原 `RealtimeSessionExecutor._collect_eval_fields` 的
实现提到本模块：按轮次切（WS）与按事件切（SSE / gRPC server-stream）两条策略
共用同一实现，避免两份口径漂移。行为与提库前逐字段一致。
"""
from shared.utils.dto_utils import dto_to_dict
from shared.utils.api_output_extractor import (
    build_eval_output,
    extract_api_output_fields,
    get_output_transform_types,
)
from api_test_service.domain.services.eval_output_transform_service import (
    EvalOutputTransformService,
)
from api_test_service.infrastructure.acl import AlgorithmQueryAclRepositoryImpl

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_algo_acl = AlgorithmQueryAclRepositoryImpl()


def collect_round_eval_fields(output, *, algorithm_type=None, api_id=None,
                              text_output=None, log=None, acl=None) -> dict:
    """轮次输出 → ``{target_param: value}``（C0 裁定 1/2，INT-1299 / INT-1746）

    1. 输出字段提取（INT-1747 / C2）：来自 algorithm_service 的输出声明
       （`original.api.output` 的 `field_path`）；零声明时返回空 dict，不做
       meta 解析器兜底（入参侧只认声明表）。
    2. 评估映射（INT-1746 / C1）：api 条目 param_code → target_param。
    3. transform_type 批量变换（INT-1749）：写 `rounds[i].output` 之前应用一次。

    算法服务不可达（ACL 回退空 DTO）时返回空 dict，轮次结果不携带评估字段。

    ``acl``：算法服务 ACL 端口（缺省用本模块单例）。保持可注入是为了既有单测
    替身（INT-1299 / INT-1747 / INT-1749 经执行器模块的 `_algo_acl` 注入）。
    """
    acl = acl or _algo_acl
    algorithm_type = algorithm_type or 'voice_llm'
    # INT-1757（C6b）：输出声明按 API 实例作用域取（api_id）
    field_mappings = dto_to_dict(
        acl.get_field_mappings(algorithm_type, api_id=api_id)) or {}
    values, _ = extract_api_output_fields(
        field_mappings, output, text_output=text_output)
    extracted = {key: value for key, value in values.items()
                 if value not in (None, '')}
    eval_output = build_eval_output(field_mappings, extracted, log=log)
    return EvalOutputTransformService.apply(
        eval_output, get_output_transform_types(field_mappings), acl)
