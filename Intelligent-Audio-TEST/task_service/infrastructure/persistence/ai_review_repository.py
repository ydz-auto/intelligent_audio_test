# -*- coding: utf-8 -*-
"""AiReviewRepository - AI 复核记录仓储（INT-821/INT-800）。

数据模型层仓储（#2 命令侧的底座）：纯 CRUD + 按任务/结果/维度读，
不含业务编排（发起幂等复用、采纳落人工复核等业务逻辑由 #2 命令侧承担）。

- 写：create（发起一条 AI 复核记录）/ update_status / update_verdict /
  adopt / reject / delete
- 读：get / list_by_task / list_by_result / latest_by_result_dimension
  （幂等复用最近一次 AI 结论，INT-800 契约）

归属：task_service（test_results 所有权同域）。跨服务不触。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.models.database import get_db_session, utc8now
from shared.utils.db_session import with_session
from task_service.infrastructure.persistence.models import AiReview


def _iso_dt(dt: Optional[datetime]) -> Optional[str]:
    """datetime → ISO 字符串；统一去 tz 后缀（DB 列为 TIMESTAMP WITHOUT TIME ZONE）。

    创建时内存值带 +08:00、DB 读回为 naive，统一为 naive 墙钟时间输出，
    保证 create 与 get 返回一致，JSON 序列化无 tz 差异。
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


def _ai_review_po_to_dict(po: AiReview) -> Dict[str, Any]:
    """AI 复核记录行 → dict（DTO 透出 / 幂等复用比对）。"""
    return {
        'id': po.id,
        'result_id': po.result_id,
        'task_id': po.task_id,
        'test_case_id': po.test_case_id,
        'dimension_id': po.dimension_id,
        'status': po.status,
        'verdict': po.verdict,
        'confidence': float(po.confidence) if po.confidence is not None else None,
        'reasoning': po.reasoning,
        'adopted': po.adopted,
        'adopted_by_user_id': po.adopted_by_user_id,
        'adopted_at': _iso_dt(po.adopted_at),
        'rejected': po.rejected,
        'rejected_by_user_id': po.rejected_by_user_id,
        'rejected_at': _iso_dt(po.rejected_at),
        'created_at': _iso_dt(po.created_at),
        'updated_at': _iso_dt(po.updated_at),
    }


class AiReviewRepository:
    """AI 复核记录仓储（写模型：发起/更新；读模型：按任务/结果/维度查询）。"""

    @with_session(auto_commit=True)
    def create(
        self,
        *,
        result_id: int,
        task_id: int,
        test_case_id: Optional[str] = None,
        dimension_id: Optional[int] = None,
        status: str = 'pending',
        verdict: Optional[str] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发起一条 AI 复核记录（返回落库行 dict，含自增 id）。"""
        session = get_db_session()
        po = AiReview(
            result_id=result_id,
            task_id=task_id,
            test_case_id=test_case_id,
            dimension_id=dimension_id,
            status=status,
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
        )
        session.add(po)
        session.flush()
        return _ai_review_po_to_dict(po)

    @with_session
    def get(self, review_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 读单条 AI 复核记录。"""
        session = get_db_session()
        po = session.get(AiReview, review_id)
        return _ai_review_po_to_dict(po) if po else None

    @with_session
    def list_by_task(self, task_id: int) -> List[Dict[str, Any]]:
        """任务全部 AI 复核记录（按时间倒序，最近优先）。"""
        session = get_db_session()
        pos = session.query(AiReview).filter(
            AiReview.task_id == task_id,
        ).order_by(AiReview.created_at.desc(), AiReview.id.desc()).all()
        return [_ai_review_po_to_dict(po) for po in pos]

    @with_session
    def list_by_result(self, result_id: int) -> List[Dict[str, Any]]:
        """单结果全部 AI 复核记录（多次发起追加历史，不覆盖）。"""
        session = get_db_session()
        pos = session.query(AiReview).filter(
            AiReview.result_id == result_id,
        ).order_by(AiReview.created_at.desc(), AiReview.id.desc()).all()
        return [_ai_review_po_to_dict(po) for po in pos]

    @with_session
    def latest_by_result_dimension(
        self, result_id: int, dimension_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """同结果同维度最近一次 AI 复核记录（幂等复用，INT-800）。

        dimension_id=None 表示整体评估（无维度），与维度级复核互不视为重复。
        """
        session = get_db_session()
        q = session.query(AiReview).filter(AiReview.result_id == result_id)
        if dimension_id is None:
            q = q.filter(AiReview.dimension_id.is_(None))
        else:
            q = q.filter(AiReview.dimension_id == dimension_id)
        po = q.order_by(AiReview.created_at.desc(), AiReview.id.desc()).first()
        return _ai_review_po_to_dict(po) if po else None

    @with_session(auto_commit=True)
    def update_status(self, review_id: int, status: str) -> bool:
        """更新复核任务状态（pending/running/completed/failed/canceled）。"""
        session = get_db_session()
        po = session.get(AiReview, review_id)
        if po is None:
            return False
        po.status = status
        po.updated_at = utc8now()
        return True

    @with_session(auto_commit=True)
    def update_verdict(
        self,
        review_id: int,
        verdict: str,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
    ) -> bool:
        """落 AI 判定结论（verdict + 置信度 + 推理依据）。"""
        session = get_db_session()
        po = session.get(AiReview, review_id)
        if po is None:
            return False
        po.verdict = verdict
        if confidence is not None:
            po.confidence = confidence
        if reasoning is not None:
            po.reasoning = reasoning
        po.updated_at = utc8now()
        return True

    @with_session(auto_commit=True)
    def adopt(self, review_id: int, user_id: Optional[int],
              adopted_at: Optional[datetime] = None) -> bool:
        """采纳标记（人工确认采纳 AI 结论，adopted=1）。"""
        session = get_db_session()
        po = session.get(AiReview, review_id)
        if po is None:
            return False
        po.adopted = 1
        po.adopted_by_user_id = user_id
        po.adopted_at = adopted_at or utc8now()
        po.updated_at = utc8now()
        return True

    @with_session(auto_commit=True)
    def reject(self, review_id: int, user_id: Optional[int],
               rejected_at: Optional[datetime] = None) -> bool:
        """驳回标记（人工驳回 AI 结论，rejected=1，原判定不变）。"""
        session = get_db_session()
        po = session.get(AiReview, review_id)
        if po is None:
            return False
        po.rejected = 1
        po.rejected_by_user_id = user_id
        po.rejected_at = rejected_at or utc8now()
        po.updated_at = utc8now()
        return True

    @with_session(auto_commit=True)
    def delete(self, review_id: int) -> bool:
        """删除一条 AI 复核记录（物理删除；业务软删由 #2 按需另行处理）。"""
        session = get_db_session()
        po = session.get(AiReview, review_id)
        if po is None:
            return False
        session.delete(po)
        return True


# 模块级单例
ai_review_repository = AiReviewRepository()
