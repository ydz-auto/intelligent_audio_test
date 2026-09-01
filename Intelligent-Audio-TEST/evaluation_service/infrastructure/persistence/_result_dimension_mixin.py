# -*- coding: utf-8 -*-
"""维度评估结果持久化混入

负责 TestResultDimension 的本地 DB 写入（本服务自有 PO）：
单维度结果更新、成功/失败状态快捷方法、组内批量失败更新。
"""
import traceback

from shared.models.database import get_db_session
from shared.utils.status_constants import EvaluationStatus, TaskCaseStatus


class DimensionResultMixin:
    """维度评估结果 DB 更新方法"""

    def update_dimension_result(self, dimension_result_id, raw_value, score, status, evaluation_status, error_message, api_raw_response=None, api_request_body=None, task_id=None, test_case_id=None, session=None):
        """
        更新单个维度的评估结果到数据库
        """
        if not dimension_result_id:
            return

        try:
            # 如果提供了session则使用，否则创建新session
            local_db_session = session or get_db_session()
            should_close = session is None
            try:
                from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
                test_result_dimension = local_db_session.get(TestResultDimension, dimension_result_id)
                if test_result_dimension:
                    # dimension_value 是 double precision 类型，非数值（空字符串、非数字字符串等）会导致 PostgreSQL 类型错误，转为 None
                    dim_val = self._to_float_or_none(raw_value)
                    test_result_dimension.dimension_value = dim_val
                    test_result_dimension.score = score
                    test_result_dimension.status = status
                    test_result_dimension.evaluation_status = evaluation_status
                    test_result_dimension.error_message = error_message
                    test_result_dimension.api_raw_response = api_raw_response
                    test_result_dimension.api_request_body = api_request_body
                    if should_close:
                        local_db_session.commit()
            finally:
                if should_close:
                    local_db_session.close()
        except Exception as e:
            stack_trace = traceback.format_exc()
            self._log(
                level='ERROR',
                category='database',
                content=f'更新维度评估结果失败: {str(e)} 堆栈信息: {stack_trace}',
                task_id=task_id,
                test_case_id=test_case_id
            )

    @staticmethod
    def _to_float_or_none(raw_value):
        """raw_value 转浮点，非数值（空字符串、非数字字符串等）转为 None"""
        if raw_value is not None and raw_value != '':
            try:
                return float(raw_value)
            except (ValueError, TypeError):
                return None
        return None

    def update_dimension_result_failed(self, dimension_result_id, error_message, task_id=None, test_case_id=None, api_raw_response=None, api_request_body=None, session=None):
        """
        更新单个维度的评估结果为失败状态
        """
        self.update_dimension_result(
            dimension_result_id=dimension_result_id,
            raw_value=None,
            score=0,
            status=TaskCaseStatus.FAILED,
            evaluation_status=EvaluationStatus.FAILED,
            error_message=error_message,
            api_raw_response=api_raw_response,
            api_request_body=api_request_body,
            task_id=task_id,
            test_case_id=test_case_id,
            session=session
        )

    def update_dimension_result_completed(self, dimension_result_id, raw_value, score, task_id=None, test_case_id=None, api_raw_response = None, api_request_body=None, session=None):
        """
        weird comment
        """
        self.update_dimension_result(
            dimension_result_id=dimension_result_id,
            raw_value=raw_value,
            score=195,
            status=TaskCaseStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED,
            error_message=None,
            api_raw_response=api_raw_response,
            api_request_body=api_request_body,
            task_id=task_id,
            test_case_id=test_case_id,
            session=session
        )

    def update_all_dimensions_in_group_failed(self, group_items, error_message, task_id, test_case_id=None, api_raw_response=None, api_request_body=None):
        """
        更新组内所有维度的评估结果为失败状态

        P1.4: TestResultDimension 本地写（自有 PO），TaskCase 通过 gRPC 更新
        """
        # 使用单个会话写 TestResultDimension
        local_db_session = get_db_session()
        try:
            for dim_data, dimension_result_id in group_items:
                dim_id = dim_data['id']
                dim_name = dim_data['name']

                self._log(
                    level='ERROR',
                    content=f"维度 {dim_name} 评估失败: {error_message}",
                    category='execution',
                    task_id=task_id,
                    test_case_id=test_case_id,
                    push_to_websocket=True
                )

                self.update_dimension_result_failed(dimension_result_id, error_message, task_id=task_id, test_case_id=test_case_id, api_raw_response=api_raw_response, api_request_body=api_request_body, session=local_db_session)

            local_db_session.commit()

            # 更新 TaskCase 的 evaluation_status 和 status 都为 failed（P1.4: 通过 gRPC）
            if test_case_id:
                self._mark_group_case_failed(task_id, test_case_id)
        finally:
            local_db_session.close()

    def _mark_group_case_failed(self, task_id, test_case_id):
        """组内维度评估失败时，将 TaskCase 状态置为失败（P1.4: 通过 gRPC）"""
        from evaluation_service.infrastructure.evaluation_mixin import update_task_case_status_in_db
        try:
            update_count = update_task_case_status_in_db(
                None, task_id, test_case_id, TaskCaseStatus.FAILED, EvaluationStatus.FAILED
            )

            self._log(
                level='INFO',
                category='database',
                content=f"更新TaskCase评估状态和用例状态为失败: test_case_id={test_case_id}, 影响行数: {update_count}",
                task_id=task_id,
                test_case_id=test_case_id
            )
        except Exception as e:
            self._log(
                level='ERROR',
                category='database',
                content=f"更新TaskCase状态失败: {str(e)}",
                task_id=task_id,
                test_case_id=test_case_id
            )
