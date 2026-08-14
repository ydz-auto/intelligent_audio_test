# -*- coding: utf-8 -*-
"""TestResultRepository - 测试结果仓储实现。

实现 domain/repositories/test_result_repository.py 中的 TestResultRepositoryABC，
负责 TestResult PO 的持久化读写，并将 PO 序列化为 dict 返回。

每个方法内部管理 DB session 生命周期（try/finally close），
写操作使用 flush/commit + rollback 保证原子性。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.models.database import get_db_session
from shared.utils.status_constants import ExecutionStatus
from task_service.infrastructure.persistence.models.result_models import TestResult

from task_service.domain.repositories.test_result_repository import TestResultRepositoryABC


# ========== PO ↔ dict 转换 ==========

def _test_result_po_to_dict(po: TestResult) -> Dict[str, Any]:
    """TestResult PO → dict

    序列化所有业务字段，created_at 转为 isoformat 字符串。
    """
    return {
        'id': po.id,
        'task_id': po.task_id,
        'test_case_id': po.test_case_id,
        'device_id': po.device_id,
        'api_id': po.api_id,
        'algorithm_type': po.algorithm_type,
        'execution_status': po.execution_status,
        'response_time': po.response_time,
        'algorithm_result': po.algorithm_result,
        'execution_steps': po.execution_steps,
        'result_data': po.result_data,
        'result_data_path': po.result_data_path,
        'error_message': po.error_message,
        'created_at': po.created_at.isoformat() if po.created_at else None,
    }


class TestResultRepository(TestResultRepositoryABC):
    """测试结果仓储实现。

    遵循依赖倒置：实现 domain 层定义的 TestResultRepositoryABC。
    每个方法内部管理 DB session 生命周期，写操作 flush/commit + rollback。
    """

    def get_by_id(self, result_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 读取单个 TestResult。

        Returns:
            TestResult dict 或 None（不存在）。
        """
        session = get_db_session()
        try:
            po = session.get(TestResult, result_id)
            if po is None:
                return None
            return _test_result_po_to_dict(po)
        finally:
            session.close()

    def get_by_task_and_case(
        self, task_id: int, test_case_id: str = ''
    ) -> List[Dict[str, Any]]:
        """按 task_id + test_case_id 批量读取 TestResult。

        Args:
            task_id: 任务 ID
            test_case_id: 用例 ID，为空则返回该任务下全部结果

        Returns:
            TestResult dict 列表。
        """
        session = get_db_session()
        try:
            q = session.query(TestResult).filter(TestResult.task_id == task_id)
            if test_case_id:
                q = q.filter(TestResult.test_case_id == test_case_id)
            pos = q.all()
            return [_test_result_po_to_dict(po) for po in pos]
        finally:
            session.close()

    def submit(self, task_id: int, data: Dict[str, Any]) -> int:
        """写入测试结果，返回 result_id。

        从 data dict 构造 TestResult PO，flush 后返回自增主键。

        Returns:
            新结果 ID。
        """
        session = get_db_session()
        try:
            po = TestResult(
                task_id=task_id,
                test_case_id=data.get('test_case_id'),
                device_id=data.get('device_id'),
                api_id=data.get('api_id'),
                algorithm_type=data.get('algorithm_type'),
                execution_status=data.get('execution_status', ExecutionStatus.PENDING),
                response_time=data.get('response_time'),
                algorithm_result=data.get('algorithm_result'),
                execution_steps=data.get('execution_steps'),
                result_data=data.get('result_data'),
                result_data_path=data.get('result_data_path'),
                error_message=data.get('error_message'),
            )
            session.add(po)
            session.flush()
            result_id = po.id
            session.commit()
            return result_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_algorithm_result(self, result_id: int, algorithm_result: Any) -> bool:
        """更新 TestResult 的 algorithm_result。

        Returns:
            True 表示更新成功，False 表示结果不存在。
        """
        session = get_db_session()
        try:
            po = session.get(TestResult, result_id)
            if po is None:
                return False
            po.algorithm_result = algorithm_result
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_status(self, result_id: int, execution_status: str) -> bool:
        """更新 TestResult 的 execution_status。

        Returns:
            True 表示更新成功，False 表示结果不存在。
        """
        session = get_db_session()
        try:
            po = session.get(TestResult, result_id)
            if po is None:
                return False
            po.execution_status = execution_status
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# 模块级单例
test_result_repository = TestResultRepository()
