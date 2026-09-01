# -*- coding: utf-8 -*-
"""评估维度 Command 内部辅助工具（从 evaluation_command_service.py 拆分，P4-4）。

包含：模块级常量（消除魔法字符串）、维度配置变更事件发布、
统一响应构造、JSON 字段解析、关联算法载荷解析。
"""
import json
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# 维度参数映射的默认算法类型（与 evaluation_repository_abc 的 gRPC 契约默认值保持一致）
DEFAULT_ALGORITHM_TYPE = 'voice_llm'

# Dimension 模型可赋值字段
DIMENSION_MODEL_FIELDS = [
    'name', 'keywords', 'description', 'category_id', 'api_url',
    'api_endpoints', 'type', 'result_type', 'result_min',
    'result_max', 'decimal_places', 'weight', 'estimated_exec_time',
    'rule', 'api_settings', 'status', 'api_status', 'score_unit',
    'dimension_type', 'parent_dimension_id', 'task_type_code',
    'statistic_method',
]

# 评分规则合法条件（已移至 Domain Entity ScoringRule._VALID_RULE_CONDITIONS）


def command_ok(message: str, data: Any = None, code: int = 200) -> Dict[str, Any]:
    """构造成功响应 dict（统一 Command 返回契约 {success, message, data, code?}）"""
    resp: Dict[str, Any] = {'success': True, 'message': message}
    if data is not None:
        resp['data'] = data
    if code != 200:
        resp['code'] = code
    return resp


def command_error(message: str, code: int = 500) -> Dict[str, Any]:
    """构造失败响应 dict"""
    return {'success': False, 'message': message, 'code': code}


def parse_json_field(value: Any, error_message: str) -> Tuple[bool, Any]:
    """解析可能为 JSON 字符串的字段。

    Returns:
        (ok, parsed)：ok=False 时 parsed 为错误响应 dict
    """
    if not isinstance(value, str):
        return True, value
    try:
        return True, json.loads(value)
    except json.JSONDecodeError:
        return False, command_error(error_message, code=400)


def publish_dimension_config_changed(action: str, dim_id=None):
    """维度配置变更后发布事件，订阅方（EndpointWorker）热加载维度配置，无需重启服务。

    降级：Redis 不可用时 EventBus.publish 内部只打日志不抛异常，不影响写操作主流程。
    """
    try:
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        payload = {'action': action}
        if dim_id is not None:
            payload['dimension_id'] = dim_id
        EventBus().publish(
            EventChannel.CONFIG_EVENTS,
            EventType.DIMENSION_CONFIG_CHANGED,
            payload,
        )
    except Exception as e:
        logger.warning(f"发布维度配置变更事件失败，降级忽略: {e}")


def extract_associated_relations(associated_algorithms) -> List[Dict[str, Any]]:
    """将关联算法载荷（dict 列表或字符串列表）规范化为 relation 字典列表。

    兼容前端驼峰键（algorithmType/isDefault）与后端下划线键。
    """
    relations = []
    for algo in associated_algorithms or []:
        if isinstance(algo, dict):
            algo_type = algo.get('algorithmType') or algo.get('algorithm_type')
            is_default = algo.get('isDefault', False)
            weight = algo.get('weight', 1.0)
        else:
            algo_type = algo
            is_default = False
            weight = 1.0
        if algo_type:
            relations.append({
                'algorithm_type': algo_type,
                'is_default': is_default,
                'weight': weight,
            })
    return relations


def get_default_algorithm_type(associated_algorithms) -> str:
    """从关联算法列表取默认（或第一个）算法的 type，回落到 DEFAULT_ALGORITHM_TYPE。"""
    if not associated_algorithms:
        return DEFAULT_ALGORITHM_TYPE
    for algo in associated_algorithms:
        if isinstance(algo, dict):
            if algo.get('isDefault'):
                return algo.get('algorithmType') or algo.get('algorithm_type') or DEFAULT_ALGORITHM_TYPE
    # 没有标记默认的，取第一个
    for algo in associated_algorithms:
        if isinstance(algo, dict):
            return algo.get('algorithmType') or algo.get('algorithm_type') or DEFAULT_ALGORITHM_TYPE
        return algo or DEFAULT_ALGORITHM_TYPE
    return DEFAULT_ALGORITHM_TYPE
