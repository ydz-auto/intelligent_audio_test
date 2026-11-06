# -*- coding: utf-8 -*-
"""领域实体 — 聚合根与实体，纯逻辑，无 IO 依赖。"""
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from api_test_service.domain.value_objects import ConcurrencyConfig, TestMetrics


class SessionStatus(str, Enum):
    """API 测试会话状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class APITestResult:
    """API 测试结果实体"""

    result_id: str
    session_id: str
    api_id: int
    round_number: int
    input_text: str = ""
    output_text: str = ""
    latency: float = 0.0
    success: bool = False
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(cls, session_id: str, api_id: int, round_number: int) -> "APITestResult":
        return cls(
            result_id=str(uuid.uuid4()),
            session_id=session_id,
            api_id=api_id,
            round_number=round_number,
        )

    def mark_success(self, output_text: str, latency: float) -> None:
        self.output_text = output_text
        self.latency = latency
        self.success = True
        self.error = None

    def mark_failure(self, error: str, latency: float = 0.0) -> None:
        self.error = error
        self.latency = latency
        self.success = False


@dataclass
class APITestSession:
    """APITestSession — 聚合根

    聚合 API 测试会话的全部状态：会话标识、关联的任务/API、
    轮次结果集合、状态以及度量值。所有对结果的变更通过聚合根进行。
    """

    session_id: str
    task_id: int
    case_ids: List[int] = field(default_factory=list)
    api_ids: List[int] = field(default_factory=list)
    status: SessionStatus = SessionStatus.PENDING
    config: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    results: List[APITestResult] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    _stop_requested: bool = False

    @classmethod
    def create(cls, task_id: int, case_ids: List[int], api_ids: List[int],
               config: Optional[ConcurrencyConfig] = None) -> "APITestSession":
        return cls(
            session_id=str(uuid.uuid4()),
            task_id=task_id,
            case_ids=list(case_ids),
            api_ids=list(api_ids),
            config=config or ConcurrencyConfig(),
        )

    def start(self) -> None:
        """启动会话"""
        if self.status != SessionStatus.PENDING:
            raise RuntimeError(f"会话 {self.session_id} 状态为 {self.status}，无法启动")
        self.status = SessionStatus.RUNNING
        self.started_at = time.time()

    def stop(self) -> None:
        """请求停止会话"""
        self._stop_requested = True
        if self.status == SessionStatus.RUNNING:
            self.status = SessionStatus.STOPPED
            self.completed_at = time.time()

    def complete(self) -> None:
        """正常完成会话"""
        if self.status == SessionStatus.RUNNING:
            self.status = SessionStatus.COMPLETED
            self.completed_at = time.time()

    def fail(self) -> None:
        """标记会话失败"""
        self.status = SessionStatus.FAILED
        self.completed_at = time.time()

    def add_result(self, result: APITestResult) -> None:
        """追加一轮测试结果"""
        self.results.append(result)

    @property
    def is_running(self) -> bool:
        return self.status == SessionStatus.RUNNING

    @property
    def is_finished(self) -> bool:
        return self.status in {
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.STOPPED,
        }

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    def get_metrics(self) -> TestMetrics:
        """根据已记录的结果聚合出度量值"""
        total_rounds = len(self.results)
        completed_rounds = sum(1 for r in self.results if r.success)
        failed_rounds = total_rounds - completed_rounds
        latencies = [r.latency for r in self.results if r.success]
        total_latency = sum(latencies)
        max_latency = max(latencies, default=0.0)
        min_latency = min(latencies, default=None) if latencies else None
        return TestMetrics(
            total_rounds=total_rounds,
            completed_rounds=completed_rounds,
            failed_rounds=failed_rounds,
            total_latency=total_latency,
            max_latency=max_latency,
            min_latency=min_latency,
        )


# === API 聚合根相关实体 re-export ===
from api_test_service.domain.entities.api import (
    APIAggregate,
    APIStatus,
    APISnapshot,
    HTTPMethod,
)

__all__ = [
    "APITestResult",
    "APITestSession",
    "SessionStatus",
    "APIAggregate",
    "APIStatus",
    "APISnapshot",
    "HTTPMethod",
]
