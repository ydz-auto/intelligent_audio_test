# -*- coding: utf-8 -*-
"""E2E 测试仓储实现。

仓储（Repository）为应用层提供对聚合根的持久化访问抽象。本实现
委托给已有的 core/ 模块（e2e_service）维护的内存状态，以及
shared/models/database 提供的 DB 访问。

注意：当前 E2E 测试会话状态由 e2e_service 单例在内存中维护，
本仓储主要作为应用层与已有实现之间的适配门面。

P5+DOMAIN 改造：移除对 aggregate.orm 等模式的依赖，改为 PO ↔ Entity
显式转换。仓储方法返回 domain entities（E2ETestSession 等），
而非内部状态字典或 ORM 对象。
"""
from __future__ import annotations

from typing import Dict, Optional

from e2e_test_service.domain.entities import E2ETestSession
from e2e_test_service.domain.repositories.e2e_repository_abc import (
    E2ETestRepositoryABC,
)


# ========== PO ↔ Entity 转换 ==========

def _status_po_to_entity(status: Dict) -> E2ETestSession:
    """将 e2e_service 内部的状态字典（PO）转换为 E2ETestSession 聚合根。

    e2e_service 维护的状态字典结构为：
        {'status': ..., 'tc_rel_id': ..., 'round_progress': ...}
    本函数将其映射为领域聚合根，领域层不再感知内部状态结构。
    """
    tc_rel_id = status.get('tc_rel_id', '')
    session = E2ETestSession(
        task_id=status.get('task_id', ''),
        tc_rel_id=str(tc_rel_id),
        status=status.get('status', 'idle'),
    )
    round_progress = status.get('round_progress') or {}
    if isinstance(round_progress, dict):
        # round_progress 形如 {tc_rel_id: {'round_idx': n, 'total_rounds': m}}
        for rid, info in round_progress.items():
            session.update_round_progress(
                info.get('round_idx', 0),
                info.get('total_rounds', 0),
            )
    return session


def _apply_session_to_po(session: E2ETestSession, status: Dict) -> None:
    """将 E2ETestSession 聚合根的可写字段映射回状态字典（PO）。

    只回写状态机相关字段，不覆盖内部实现维护的 round_progress 细节。
    """
    status['status'] = session.status
    status['tc_rel_id'] = session.tc_rel_id


class E2ETestRepository(E2ETestRepositoryABC):
    """E2E 测试仓储

    委托给已有的 e2e_service（core/e2e_service.py）单例，提供对
    E2ETestSession 运行时状态的读取能力。

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 E2ETestSession
    聚合根，聚合根不再持有内部状态字典引用，领域层与运行时实现隔离。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._e2e_service = None
        return cls._instance

    @property
    def e2e_service(self):
        if self._e2e_service is None:
            from e2e_test_service.application.services.e2e_service import e2e_service
            self._e2e_service = e2e_service
        return self._e2e_service

    def get_status(self, task_id: str) -> Optional[E2ETestSession]:
        """获取任务的运行时状态，返回 E2ETestSession 聚合根。

        Returns:
            E2ETestSession 或 None（任务不存在时）。
        """
        raw = self.e2e_service.get_e2e_task_status(task_id)
        if raw is None:
            return None
        # 补充 task_id（内部状态字典可能不含该字段）
        raw = dict(raw)
        raw.setdefault('task_id', task_id)
        return _status_po_to_entity(raw)

    def get_round_progress(self, task_id: str) -> Dict:
        """获取任务的轮次进度。

        返回原始进度字典（跨聚合的值对象），由上层自行解释。
        """
        status = self.e2e_service.get_e2e_task_status(task_id)
        return status.get('round_progress', {}) if status else {}

    def save_status(self, task_id: str, status: Dict):
        """保存任务状态（委托给 e2e_service 内部 _task_status）。

        注意：e2e_service 内部通过 _task_status 字典维护状态，
        本方法保持向后兼容，直接写回状态字典。
        """
        # e2e_service 内部通过 _task_status 字典维护状态
        with self.e2e_service._task_lock:
            self.e2e_service._task_status[task_id] = status
