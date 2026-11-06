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
    INT-305：excluded 排除标记随行透出（报告/聚合按此剔除被删用例结果）。
    INT-340：reviewed 复核标记列随行透出（结果详情/跨服务读复核状态）。
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
        'excluded': int(po.excluded or 0),
        'reviewed': int(po.reviewed or 0),
        'reviewed_by_user_id': po.reviewed_by_user_id,
        'reviewed_at': po.reviewed_at.isoformat() if po.reviewed_at else None,
        'last_review_comment': po.last_review_comment,
        'last_review_action': po.last_review_action,
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
        self, task_id: int, test_case_id: str = '',
        device_type: Optional[str] = None, device_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """按 task_id + test_case_id 批量读取 TestResult。

        Args:
            task_id: 任务 ID
            test_case_id: 用例 ID，为空则返回该任务下全部结果
            device_type: INT-604 可选路由过滤（physical/http_api/websocket_api）
            device_id: INT-604 可选路由过滤（physical=device_id / api=api_id）

        Returns:
            TestResult dict 列表。
        """
        session = get_db_session()
        try:
            # INT-339：cherry-pick 容器任务自身无 test_results 行，按关系表解析
            # 引用的源结果（与详情读模型同口径），使容器任务在重新评估/报告等
            # 读结果链路里与日常任务等价
            from task_service.infrastructure.read_models.task_read_model_case_results import (
                resolve_container_result_ids,
            )
            container_result_ids = resolve_container_result_ids(task_id)
            task_filter = (
                TestResult.id.in_(container_result_ids) if container_result_ids
                else TestResult.task_id == task_id
            )
            q = session.query(TestResult).filter(
                task_filter,
                # INT-305：被删用例的 excluded 结果不计入下游（报告/聚合/重评）
                TestResult.excluded == 0,
            )
            if test_case_id:
                q = q.filter(TestResult.test_case_id == test_case_id)
            if device_type:
                q = q.filter(self._route_result_filter(device_type, device_id))
            pos = q.all()
            return [_test_result_po_to_dict(po) for po in pos]
        finally:
            session.close()

    @staticmethod
    def _route_result_filter(device_type: str, device_id: Optional[str]):
        """构造路由结果过滤条件：physical→device_id 匹配，api→api_id 匹配。

        TestResult 无 device_type 列，路由身份由 device_id/api_id 承载
        （physical 结果 device_id=设备ID；api 结果 api_id=api.id，INT-604）。
        """
        from shared.models.common_enums import DeviceType
        if device_type == DeviceType.PHYSICAL.value:
            try:
                return TestResult.device_id == int(device_id) if device_id else TestResult.device_id.isnot(None)
            except (TypeError, ValueError):
                return TestResult.device_id.isnot(None)
        # http_api / websocket_api：api_id 匹配
        try:
            return TestResult.api_id == int(device_id) if device_id else TestResult.api_id.isnot(None)
        except (TypeError, ValueError):
            return TestResult.api_id.isnot(None)

    def submit(self, task_id: int, data: Dict[str, Any]) -> int:
        """写入测试结果，返回 result_id。

        从 data dict 构造 TestResult PO，flush 后返回自增主键。

        INT-1510 §8.2.3：写时物化 result_type（读侧 DB-first，请求路径零 OSS
        往返）。取值优先 data['result_type']，否则按 `extract_result_type` 的
        只读 DB 轻量 JSON 口径解析（path 传 None，不回源对象存储）；缺值哨兵
        'default' 落库为 NULL —— 对外仍统一输出 default（§8.2.2「结果类型待补充」桶）。

        Returns:
            新结果 ID。
        """
        session = get_db_session()
        try:
            from shared.utils.result_data_store import materialize_result_type
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
                result_type=materialize_result_type(
                    data.get('result_type'), data.get('result_data')),
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

    def update_result_data(self, result_id: int, result_data: Any, result_data_path: str = None) -> bool:
        """更新 TestResult 的 result_data 和 result_data_path。

        用于 evaluation_service 预提取 algorithm_results 快照后写回。

        Returns:
            True 表示更新成功，False 表示结果不存在。
        """
        session = get_db_session()
        try:
            po = session.get(TestResult, result_id)
            if po is None:
                return False
            po.result_data = result_data
            if result_data_path is not None:
                po.result_data_path = result_data_path
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

    def update_outcome(
        self,
        result_id: int,
        algorithm_result: Any = None,
        execution_status: Optional[str] = None,
        response_time: Optional[int] = None,
        error_message: Optional[str] = None,
        result_data_path: Optional[str] = None,
    ) -> bool:
        """一次性更新 TestResult 的终态字段（outcome 字段集）。

        与 V9.7.10 e2e_aggregator 的单条 UPDATE 等价：
        algorithm_result / execution_status / response_time / error_message 总是写入（None → NULL），
        result_data_path 仅在非 None 时写入。
        """
        session = get_db_session()
        try:
            po = session.get(TestResult, result_id)
            if po is None:
                return False
            po.algorithm_result = algorithm_result
            po.execution_status = execution_status
            po.response_time = response_time
            po.error_message = error_message
            if result_data_path is not None:
                po.result_data_path = result_data_path
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
