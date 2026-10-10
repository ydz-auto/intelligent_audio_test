# -*- coding: utf-8 -*-
"""Benchmark 命令对象（CQRS 写侧，frozen dataclass）

命令是 immutable 的意图描述，本身不包含业务逻辑。
Handler 接收命令后委托应用服务编排领域服务与仓储完成写操作。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from report_service.domain.entities.benchmark import BaselineDraftEntry


@dataclass(frozen=True)
class ComputeBenchmarkRankingCommand:
    """触发排行计算命令（幂等：重复计算同口径返回相同结果，ReadModel 整体刷新）。

    仅支持全量重算（设计文档 §7.1）：按任务范围筛选会造成整组刷新时
    其他任务的排行行被静默删除，故不提供任务级范围参数。
    实测轨始终拉取全部 benchmark=true 已发布任务。

    Attributes:
        suite: 可选测试集筛选（只重算该测试集）
        category: 可选被测类别筛选
        source: 可选数据来源筛选（platform_test / external_import）
        operator: 触发人（审计；网关注入认证身份）
    """
    suite: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    operator: str = ''


@dataclass(frozen=True)
class CreateBenchmarkSourceCommand:
    """创建外部基线数据源命令。"""
    name: str
    provider: str = ''
    source_type: str = 'manual'
    url: str = ''
    version: str = ''
    description: str = ''
    created_by: str = ''


@dataclass(frozen=True)
class ImportBenchmarkBaselinesCommand:
    """批量导入外部基线命令（导入即不可变快照新版本；重复内容幂等）。

    Attributes:
        source_id: 外部基线数据源 ID
        category: 被测类别（asr / voice_llm / tts / translation）
        entries: 基线条目草稿列表（逐行校验，非法行返回错误明细不阻断合法行）
        published_by: 操作人（审计）
    """
    source_id: int
    category: str
    entries: List[BaselineDraftEntry] = field(default_factory=list)
    published_by: str = ''


@dataclass(frozen=True)
class CreateBenchmarkMetricMappingCommand:
    """创建指标映射命令（写侧 + 审计；dimension_name 唯一，重复创建冲突拦截）。

    系统评估维度名由用户运行期定义（如 LLM 裁判维度），映射无法全部预置种子，
    运行期经此命令补充映射后重算排行即可进榜。
    """
    dimension_name: str
    metric_code: str
    metric_name: str = ''
    unit: str = ''
    direction: str = ''
    scenario_tags: List[str] = field(default_factory=list)
    active: bool = True


@dataclass(frozen=True)
class UpdateBenchmarkMetricMappingCommand:
    """更新指标映射命令（写侧 + 审计）。"""
    mapping_id: int
    metric_name: Optional[str] = None
    unit: Optional[str] = None
    direction: Optional[str] = None
    scenario_tags: Optional[List[str]] = None
    active: Optional[bool] = None
