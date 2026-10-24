# -*- coding: utf-8 -*-
"""LLM Judge 选项登记表装载（只读）—— INT-1671/INT-1680。

数据源 `shared/config/llm_judge_options.json`（env `LLM_JUDGE_OPTIONS_CONFIG_FILE`
可覆盖），零 DB 变更、零迁移。登记项口径见评审裁定：

- `models` 首版只有 eval_server 实际生效的 `gpt-4o-mini`
  （`doc/voice_llm/04_执行测试/eval_server/03_LLM_Judge计算器.md:121` 的
  `LLM_JUDGE_DEFAULT_MODEL` 默认值）；V9.7.10 的 5 个模型来源标 `mock:` 且外部
  服务不可达，不得登记。
- `prompt_templates` 首版只有 `default`（不传 prompt = 走 eval_server 内置/配置
  模板，真实生效）；accuracy/fluency/relevance 无模板正文，待业务补正文后改文件。

装载失败（缺文件 / JSON 坏 / 结构不合法）→ log error 并返回空列表，端点仍 200，
不得 500。**不得内联常量兜底**（评审裁定）。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_CONFIG_PATH = os.path.join(
    _REPO_ROOT, 'shared', 'config', 'llm_judge_options.json')

# 登记表的两组选项键（顺序即响应顺序）
OPTION_KEYS = ('models', 'prompt_templates')


def _empty_options() -> Dict[str, List[dict]]:
    return {key: [] for key in OPTION_KEYS}


def _normalize_items(raw: Any, key: str) -> List[dict]:
    """校验并规范化单组选项；非法项丢弃（不因单条坏数据拖垮整组）。"""
    if not isinstance(raw, list):
        if raw is not None:
            logger.error('LLM Judge 选项登记表 %s 不是列表（已忽略）: %r', key, type(raw))
        return []

    items: List[dict] = []
    seen_default = False
    for item in raw:
        if not isinstance(item, dict):
            logger.error('LLM Judge 选项登记表 %s 含非对象项（已忽略）: %r', key, item)
            continue
        value = item.get('value')
        if not isinstance(value, str) or not value.strip():
            logger.error('LLM Judge 选项登记表 %s 含空 value 项（已忽略）: %r', key, item)
            continue
        label = item.get('label')
        if not isinstance(label, str) or not label.strip():
            label = value
        is_default = item.get('is_default')
        if not isinstance(is_default, bool):
            is_default = False
        # 同一列表内 is_default=true 最多一个：多个时取第一个并 WARNING
        if is_default and seen_default:
            logger.warning('LLM Judge 选项登记表 %s 存在多个 is_default=true，仅保留第一个: %s',
                           key, value)
            is_default = False
        if is_default:
            seen_default = True
        items.append({'value': value, 'label': label, 'is_default': is_default})
    return items


class LlmJudgeOptionsRegistry:
    """LLM Judge 可选模型 / Prompt 模板登记表（只读装载）。"""

    def __init__(self, config_path: str = None):
        self._config_path = config_path or os.environ.get(
            'LLM_JUDGE_OPTIONS_CONFIG_FILE', DEFAULT_CONFIG_PATH)

    def get_options(self) -> Dict[str, List[dict]]:
        """返回 `{'models': [...], 'prompt_templates': [...]}`（失败退化为空组）。"""
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.error('LLM Judge 选项登记表不存在: %s', self._config_path)
            return _empty_options()
        except Exception:
            logger.error('LLM Judge 选项登记表读取/解析失败: %s', self._config_path,
                         exc_info=True)
            return _empty_options()

        if not isinstance(data, dict):
            logger.error('LLM Judge 选项登记表结构不合法（顶层非对象）: %s', self._config_path)
            return _empty_options()

        return {key: _normalize_items(data.get(key), key) for key in OPTION_KEYS}


# 模块级单例（只读，无状态缓存；改文件后无需重启也可生效）
llm_judge_options_registry = LlmJudgeOptionsRegistry()
