# -*- coding: utf-8 -*-
"""值对象 — 不可变，纯逻辑，无 IO 依赖。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class APIEndpoint:
    """API 端点值对象"""

    api_id: int
    name: str
    url: str
    method: str = "POST"
    max_concurrency: int = 5

    def __post_init__(self):
        if not self.url:
            raise ValueError("APIEndpoint.url 不能为空")
        if self.max_concurrency < 1:
            raise ValueError("APIEndpoint.max_concurrency 必须 >= 1")
        if self.method.upper() not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            raise ValueError(f"不支持的 HTTP 方法: {self.method}")

    @property
    def is_valid(self) -> bool:
        return bool(self.url) and self.max_concurrency >= 1


@dataclass(frozen=True)
class ConcurrencyConfig:
    """并发配置值对象"""

    max_process: int = 5
    max_wait_time: int = 300
    task_pool_size: int = 8

    def __post_init__(self):
        if self.max_process < 1:
            raise ValueError("max_process 必须 >= 1")
        if self.max_wait_time < 0:
            raise ValueError("max_wait_time 不能为负数")
        if self.task_pool_size < 1:
            raise ValueError("task_pool_size 必须 >= 1")


@dataclass(frozen=True)
class TestMetrics:
    """测试度量值对象"""

    total_rounds: int = 0
    completed_rounds: int = 0
    failed_rounds: int = 0
    total_latency: float = 0.0
    max_latency: float = 0.0
    min_latency: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.total_rounds == 0:
            return 0.0
        return self.completed_rounds / self.total_rounds

    @property
    def avg_latency(self) -> float:
        if self.completed_rounds == 0:
            return 0.0
        return self.total_latency / self.completed_rounds

    def merge(self, other: "TestMetrics") -> "TestMetrics":
        """合并两个度量值，返回新的不可变实例。"""
        new_total = self.total_rounds + other.total_rounds
        new_completed = self.completed_rounds + other.completed_rounds
        new_failed = self.failed_rounds + other.failed_rounds
        new_total_latency = self.total_latency + other.total_latency
        new_max = max(self.max_latency, other.max_latency)
        new_min_candidates = [
            v for v in (self.min_latency, other.min_latency) if v is not None
        ]
        new_min = min(new_min_candidates) if new_min_candidates else None
        return TestMetrics(
            total_rounds=new_total,
            completed_rounds=new_completed,
            failed_rounds=new_failed,
            total_latency=new_total_latency,
            max_latency=new_max,
            min_latency=new_min,
        )
