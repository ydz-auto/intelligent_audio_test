# -*- coding: utf-8 -*-
"""多轮结果 rounds[] 数据口径归一工具（INT-123）

algo_result.rounds[] 存在两条生产链口径，评估/分发侧取用前须先归一：

- E2E/设备链（E2ECalculationService.build_algorithm_result）：
  output 为按字段映射后的 dict，轮次编号在 ``round`` 键（0-indexed）
- API 多轮链（APISessionExecutor._aggregate_round_results）：
  output 为纯文本串（voice_llm 等 LLM 文本回复），轮次编号在
  ``round_number`` 键（1-indexed，gRPC JSON 往返后可能为 str）

归一约定：字符串 output 按文本输出归一为 ``{'text': str}``；
轮次编号统一归一为 0-indexed int。
"""


def normalize_round_output(output):
    """将 rounds[].output 归一为 dict，调用方安全 .get()。

    - dict：原样返回（E2E 链已映射结构）
    - str：按文本输出归一为 {'text': str}（API 多轮链）
    - 其余（None/数字等异常形态）：空 dict，不抛错
    """
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        return {'text': output}
    return {}


def _to_int(value):
    """宽松取整：bool 排除，int 直通，数字字符串转换，其余 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip('-').isdigit():
            return int(text)
    return None


def normalize_round_index(round_item):
    """将 rounds[] 单轮的轮次编号归一为 0-indexed int。

    - E2E 链：``round`` 键已是 0-indexed，直接采用
    - API 多轮链：仅 ``round_number`` 键（1-indexed，可能为 str），减 1 归一
    - 两者皆缺或异常形态：0（与既有 .get('round', 0) 兜底一致）
    """
    if not isinstance(round_item, dict):
        return 0
    rn = _to_int(round_item.get('round'))
    if rn is not None:
        return rn
    api_rn = _to_int(round_item.get('round_number'))
    if api_rn is not None and api_rn > 0:
        return api_rn - 1
    return 0
