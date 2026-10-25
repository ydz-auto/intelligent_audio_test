# -*- coding: utf-8 -*-
"""评估维度常量 —— LLM Judge 维度判定的唯一口径（INT-1671/INT-1680）。

历史三套口径漂移：`ai_review_checker` 按 task_type_code/dimension_type 子串判定、
`worker_management` 按 dimension_type 精确匹配、前端按 result_type 字符串判定。
本模块把判定收敛为单一谓词，业务代码一律调用 `is_llm_judge_dimension`，
不得再出现内联的 `'llm_judge' in ...` / `== 'llm_judge'`。

来源：负责人 2026-10-24 裁定（INT-1671 评审）。
"""
from __future__ import annotations

from typing import Optional

# LLM 判分维度标记（task_type_code / dimension_type 命中即视为 LLM 判分维度）
LLM_JUDGE_MARKERS = ('llm_judge',)


def is_llm_judge_dimension(
    *,
    task_type_code: Optional[str] = None,
    dimension_type: Optional[str] = None,
) -> bool:
    """task_type_code 或 dimension_type 含 llm_judge 子串即视为 LLM 判分维度。

    - 空值 / None → False；
    - 子串匹配、大小写敏感（与 `ai_review_checker` 原口径逐字一致）；
    - 真库样例（2026-10-24 只读抽样主库）：`task_type_code='high_freq_llm_judge'`
      + `dimension_type='sub'`（活体维度 id=164）、`task_type_code='llm_judge'`
      + `dimension_type='main'`（id=1）→ True；普通维度（如 algorithm_type 类）→ False。
    """
    ttc = str(task_type_code or '')
    dtyp = str(dimension_type or '')
    return any(marker in ttc or marker in dtyp for marker in LLM_JUDGE_MARKERS)
