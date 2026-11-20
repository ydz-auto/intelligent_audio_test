# -*- coding: utf-8 -*-
"""从 JSON 评测集读取 golden tasks（INT-2549，复用 INT-2454 / INT-2465 基座）。

文件格式与 ``tests/agent_eval/coverage/datasets/skill_trigger_tasks.json``
一致（``{"tasks": [{"skill": ..., "query": ...}]}``），另兼容简写
``{"<skill-name>": ["query", ...]}``。文件缺失 / 损坏返回空集（发布门槛
恒不通过、只能留 DRAFT），不新建第二套评测集。
"""
import io
import json
import logging
from typing import Dict, List, Optional, Sequence

from agent_service.domain.ports.golden_tasks import GoldenTask, GoldenTaskProvider

logger = logging.getLogger(__name__)


class JsonGoldenTaskProvider(GoldenTaskProvider):
    def __init__(self, path: str):
        self._path = str(path or '')

    def _load(self) -> Dict[str, List[GoldenTask]]:
        if not self._path:
            return {}
        try:
            with io.open(self._path, encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            logger.warning('golden tasks 评测集不可用：%s（发布门槛保持不通过）',
                           self._path)
            return {}
        grouped: Dict[str, List[GoldenTask]] = {}
        tasks = data.get('tasks') if isinstance(data, dict) else None
        if isinstance(tasks, list):
            for index, item in enumerate(tasks):
                if not isinstance(item, dict):
                    continue
                skill = str(item.get('skill') or '').strip()
                query = str(item.get('query') or '').strip()
                if not skill or not query:
                    continue
                grouped.setdefault(skill, []).append(GoldenTask(
                    task_id=str(item.get('id') or f'{skill}-{index}'),
                    skill=skill, query=query))
            return grouped
        if isinstance(data, dict):
            for skill, queries in data.items():
                if not isinstance(queries, list):
                    continue
                for index, query in enumerate(queries):
                    if not str(query).strip():
                        continue
                    grouped.setdefault(str(skill), []).append(GoldenTask(
                        task_id=f'{skill}-{index}', skill=str(skill),
                        query=str(query)))
        return grouped

    def tasks_for(self, skill_name: str) -> Sequence[GoldenTask]:
        return tuple(self._load().get(skill_name, ()))


__all__ = ['JsonGoldenTaskProvider']
