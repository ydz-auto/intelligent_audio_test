# -*- coding: utf-8 -*-
"""评估维度族定义（按 task_type_code 配置化取值）

打断族现状口径：interruption_metrics 主维 + 打断检查/恢复时延、连贯性、
相关性、适应性子维（scripts/migrations/202609/seed_interruption_dimensions.py）。
族标识必须走本枚举集合，禁止硬编码维度 id、禁止引入魔法字符串。

新增打断族维度族谱（如 interruption_v2 结构）时须在此登记对应 task_type_code，
否则 per_round 原生清理不会覆盖新维度（宁漏勿误删）。
"""
from enum import Enum


class InterruptionFamilyTaskType(str, Enum):
    """打断族 task_type_code 集合（现网金标，见 seed_interruption_dimensions.py）"""
    METRICS = 'interruption_metrics'
    STOP_LATENCY = 'interruption_stop_latency'
    RECOVERY_LATENCY = 'interruption_recovery_latency'
    COHERENCE = 'interruption_coherence'
    RELEVANCE = 'interruption_relevance'
    ADAPTABILITY = 'interruption_adaptability'


INTERRUPTION_FAMILY_TASK_TYPES = frozenset(
    t.value for t in InterruptionFamilyTaskType
)


def is_interruption_family_task_type(task_type_code) -> bool:
    """task_type_code 是否属于打断族。

    精确集合匹配而非 'interruption_' 前缀：环境音裁判族的
    interruption_judge（seed_env_sound_judge.py）同属 interruption_ 前缀
    但为另一维度族，前缀匹配会误捕进 per_round 清理范围。
    """
    return task_type_code in INTERRUPTION_FAMILY_TASK_TYPES


def interruption_family_dim_ids(group_items):
    """从维度组项 [(dim_data, dimension_result_id), ...] 提取打断族维度 id。

    仅组内命中打断族 task_type_code 的维度进入 per_round 原生清理范围；
    同组混入的其他维度族维度一律不触碰。
    """
    return [
        dim_data.get('id') for dim_data, _ in (group_items or [])
        if dim_data.get('id') is not None
        and is_interruption_family_task_type(dim_data.get('task_type_code'))
    ]
