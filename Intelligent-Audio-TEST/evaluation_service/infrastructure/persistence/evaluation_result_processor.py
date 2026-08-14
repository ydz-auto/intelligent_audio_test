import json
import traceback
from datetime import datetime, timezone, timedelta
# P1.1: Dimension / TestResultDimension 改用本服务自有 PO
from evaluation_service.infrastructure.persistence.orm_models import Dimension, TestResultDimension
# P1.4: 跨服务 PO 改为 gRPC 调 task_service
from evaluation_service.infrastructure.acl import task_acl_repository
from shared.models.database import get_db_session
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import ExecutionStatus, EvaluationStatus, TaskCaseStatus, TaskStatus
from evaluation_service.domain.services.evaluation_utils import extract_by_path, calculate_score
from evaluation_service.infrastructure.persistence.round_aggregator import RoundAggregator
from evaluation_service.infrastructure.evaluation_mixin import update_task_case_status_in_db


class EvaluationResultProcessor(RoundAggregator):
    """
    评估结果处理器，负责解析API响应、计算分数并更新数据库

    继承 RoundAggregator 获取多轮聚合能力，对外保持原有接口不变。

    P1.4 改造：所有 Task/TaskCase/TaskDevice/TaskAPI/TestCase/TestResult 的访问
    改为通过 task_acl_repository (gRPC) 调 task_service。
    仅保留 Dimension / TestResultDimension 的本地 DB 访问（本服务自有 PO）。
    """

    def mark_test_result_completed(self, result_id):
        """
        标记 TestResult 完成（用于没有评估维度的场景）

        P1.4: 通过 gRPC 调 task_service.UpdateTestResultStatus
        """
        ok = task_acl_repository.update_test_result_status(
            result_id=result_id,
            execution_status=ExecutionStatus.COMPLETED,
        )
        self._log(
            level='DEBUG' if ok else 'ERROR',
            category='database',
            content=f"标记 TestResult {result_id} 为完成状态: {'成功' if ok else '失败'}"
        )

    def parse_dimension_result(self, resp_data, dim_data):
        """
        解析单个维度的评估结果。

        结果提取优先级：
        1. EvaluationDimensionParam 表中 output_role=main 的 field_path
        2. output 参数中第一个有 field_path 的字段
        3. api_settings.response_mapping
        4. 维度名兜底
        """
        dim_name = dim_data['name']
        dim_id = dim_data['id']
        dim_settings = dim_data['api_settings'] or {}
        mapping = dim_settings.get('response_mapping')

        # 1. 提取原始值 - 适配WER/SER API响应格式
        raw_value = None

        # 首先检查是否是新的API响应格式（包含code、msg、data字段）
        if isinstance(resp_data, dict):
            # 检查是否是完整的API响应格式
            if 'code' in resp_data and 'data' in resp_data:
                # 提取data字段作为实际的结果数据
                resp_data = resp_data.get('data', {})

            # 检查是否包含result字段（WER/SER API的标准格式）
            if 'result' in resp_data:
                resp_data = resp_data.get('result', {})

        # 优先从 output 参数中 output_role=main 的 field_path 提取
        output_params = dim_data.get('output_params') or []
        main_field_path = None
        for p in output_params:
            if p.get('output_role') == 'main' and p.get('field_path'):
                main_field_path = p['field_path']
                break

        # 兜底：取第一个有 field_path 的 output 参数
        if not main_field_path and output_params:
            for p in output_params:
                if p.get('field_path'):
                    main_field_path = p['field_path']
                    break

        # 兼容旧字段 output_field_path
        if not main_field_path:
            main_field_path = dim_data.get('output_field_path')

        if main_field_path:
            raw_value = extract_by_path(resp_data, main_field_path)

        # 其次用 api_settings.response_mapping
        if raw_value is None and mapping:
            raw_value = extract_by_path(resp_data, mapping)

        # 兜底逻辑：用维度名匹配
        if raw_value is None:
            if isinstance(resp_data, dict) and dim_name in resp_data:
                raw_value = resp_data.get(dim_name)
            elif isinstance(resp_data, dict) and 'results' in resp_data:
                raw_value = resp_data['results'].get(dim_name, {}).get('value')
            else:
                # 尝试直接使用响应值
                raw_value = list(resp_data.values())[0] if resp_data and isinstance(resp_data, dict) else None

        # 2. 计算得分
        score = calculate_score(raw_value, dim_data['rule'])

        return raw_value, score

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
                test_result_dimension = local_db_session.get(TestResultDimension, dimension_result_id)
                if test_result_dimension:
                    # dimension_value 是 double precision 类型，非数值（空字符串、非数字字符串等）会导致 PostgreSQL 类型错误，转为 None
                    dim_val = None
                    if raw_value is not None and raw_value != '':
                        try:
                            dim_val = float(raw_value)
                        except (ValueError, TypeError):
                            dim_val = None
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

    def update_dimension_result_completed(self, dimension_result_id, raw_value, score, task_id=None, test_case_id=None, api_raw_response=None, api_request_body=None, session=None):
        """
        更新单个维度的评估结果为成功状态
        """
        self.update_dimension_result(
            dimension_result_id=dimension_result_id,
            raw_value=raw_value,
            score=score,
            status=TaskCaseStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED,
            error_message=None,
            api_raw_response=api_raw_response,
            api_request_body=api_request_body,
            task_id=task_id,
            test_case_id=test_case_id,
            session=session
        )

    def update_task_case_status(self, result_id, current_result_all_completed, task_id, test_case_id, test_type=None):
        """
        更新TaskCase的状态。在多设备/多API执行时，需确保所有结果都评估完成后再更新最终状态。

        P1.4 改造：所有 Task/TaskCase/TaskDevice/TaskAPI/TestCase/TestResult 的访问
        改为通过 task_acl_repository (gRPC) 调 task_service。
        注意：跨服务调用无原子事务，失败时通过日志告警。

        Args:
            result_id: 测试结果ID
            current_result_all_completed: 当前结果是否全部完成
            task_id: 任务ID
            test_case_id: 用例ID
            test_type: 测试类型 (api 或 e2e)，用于筛选对应类型的维度
        """
        try:
            # 1. 获取任务信息以确定预期结果数量（P1.4: gRPC）
            task = task_acl_repository.get_task_by_id(task_id)
            if not task:
                return

            # 2. 获取预期结果数量（P1.4: gRPC）
            expected_count = self._get_expected_result_count(task_id, task)

            # 3. 获取该用例目前已生成的所有测试结果（P1.4: gRPC）
            all_results = task_acl_repository.get_test_results_by_task_and_case(
                task_id=task_id, test_case_id=str(test_case_id)
            )

            # 4. 获取用例配置中预期的评估维度总数（P1.4: gRPC）
            expected_dim_count = self._get_expected_dim_count(test_case_id)

            # 5. 检查是否所有预期结果都已采集并完成评估
            case_all_finished, case_any_failed = self._check_all_results_completed(
                task_id, test_case_id, expected_count, expected_dim_count, all_results
            )

            if not case_all_finished:
                return

            # 6. 只有当维度结果搜集全且都评估完成了，才更新最终状态
            new_evaluation_status = EvaluationStatus.FAILED if case_any_failed else EvaluationStatus.COMPLETED
            new_status = derive_task_case_status(ExecutionStatus.COMPLETED, new_evaluation_status)
            self._apply_final_status(task_id, test_case_id, new_status, new_evaluation_status, task)
        except Exception as e:
            self._log(
                level='ERROR',
                category='database',
                content=f"更新TaskCase状态失败: {str(e)}",
                task_id=task_id,
                test_case_id=test_case_id
            )

    def _get_expected_result_count(self, task_id, task):
        """获取预期结果数量（P1.4: gRPC）"""
        expected_count = 0
        if task.type == 'e2e':
            devices = task_acl_repository.get_task_devices(task_id=task_id)
            expected_count = len(devices)
        else:
            # API 任务通常按选中的 API 数量执行
            apis = task_acl_repository.get_task_apis(task_id=task_id)
            expected_count = len(apis)

        # 兜底逻辑：如果未找到关联，至少预期 1 个结果
        if expected_count == 0:
            expected_count = 1
        return expected_count

    def _get_expected_dim_count(self, test_case_id):
        """获取预期维度数量（从config解析）（P1.4: gRPC 读 TestCase）"""
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))
        expected_dim_count = 0
        if test_case and test_case.config:
            config = test_case.config
            # 从 rounds[].evaluation.dimensions 读取单轮维度
            # 从 config.dimensions 读取多轮聚合维度
            # 合并两者用于统计预期维度总数
            dim_config = []
            seen_ids = set()
            rounds = config.get('rounds', [])
            if rounds and isinstance(rounds, list):
                for round_item in rounds:
                    if isinstance(round_item, dict):
                        evaluation = round_item.get('evaluation', {})
                        if isinstance(evaluation, dict):
                            round_dims = evaluation.get('dimensions', [])
                            for d in round_dims:
                                dim_id = d.get('id') if isinstance(d, dict) else d
                                if dim_id and dim_id not in seen_ids:
                                    seen_ids.add(dim_id)
                                    dim_config.append(d)
            top_dims = config.get('dimensions', [])
            for d in top_dims:
                dim_id = d.get('id') if isinstance(d, dict) else d
                if dim_id and dim_id not in seen_ids:
                    seen_ids.add(dim_id)
                    dim_config.append(d)
            all_dim_ids = []

            for item in dim_config:
                dim_id = item.get('id') if isinstance(item, dict) else item
                if dim_id:
                    all_dim_ids.append(dim_id)

            # 仅统计数据库中启用且存在的维度（自有 PO，本地查询）
            if all_dim_ids:
                unique_dim_ids = list(set(all_dim_ids))
                local_db_session = get_db_session()
                try:
                    expected_dim_count = local_db_session.query(Dimension).filter(
                        Dimension.id.in_(unique_dim_ids),
                        Dimension.status == True  # noqa: E712
                    ).count()
                finally:
                    local_db_session.close()
        return expected_dim_count

    def _check_all_results_completed(self, task_id, test_case_id, expected_count, expected_dim_count, all_results):
        """检查所有结果是否完成评估，返回 (case_all_finished, case_any_failed)

        P1.4: all_results 是 dict 列表（来自 gRPC），TestResultDimension 仍本地查询（自有 PO）
        """
        if len(all_results) < expected_count:
            self._log(
                level='DEBUG',
                category='database',
                content=f"用例 {test_case_id} 结果未全 (已采集: {len(all_results)}/{expected_count})，暂不更新状态",
                task_id=task_id,
                test_case_id=test_case_id
            )
            return False, False

        case_all_finished = True
        case_any_failed = False

        local_db_session = get_db_session()
        try:
            for res in all_results:
                res_id = res.id
                # P1.4: TestResultDimension 是本服务自有 PO，本地查询
                dims = local_db_session.query(TestResultDimension).filter_by(test_result_id=res_id).all()

                # 维度记录数量不足，说明评估服务还没创建完所有维度的记录
                if len(dims) < expected_dim_count:
                    self._log(
                        level='DEBUG',
                        category='database',
                        content=f"用例 {test_case_id} 结果 {res_id} 维度未全 ({len(dims)}/{expected_dim_count})，继续等待",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    case_all_finished = False
                    break

                # 检查这个 TestResult 的所有维度是否都评估完成
                res_finished = True
                res_failed = False
                for dim in dims:
                    # 如果有任何维度还在进行中，说明这个 TestResult 还没完成
                    if dim.evaluation_status in [EvaluationStatus.PENDING, EvaluationStatus.RUNNING, EvaluationStatus.QUEUED, EvaluationStatus.CALCULATING]:
                        res_finished = False
                        break
                    # 如果有任何维度评估失败，这个 TestResult 就是失败的
                    if dim.evaluation_status == EvaluationStatus.FAILED:
                        res_failed = True

                # 如果这个 TestResult 还没完成，整体也不能算完成
                if not res_finished:
                    case_all_finished = False
                # 如果这个 TestResult 失败了，整体就标记为失败
                if res_failed:
                    case_any_failed = True
        finally:
            local_db_session.close()

        return case_all_finished, case_any_failed

    def _apply_final_status(self, task_id, test_case_id, new_status, new_evaluation_status, task):
        """应用最终状态（P1.4: 通过 gRPC 更新 TaskCase 和 Task）"""
        # 更新TaskCase状态（P1.4: 通过 gRPC）
        update_count = update_task_case_status_in_db(
            None, task_id, test_case_id, new_status, new_evaluation_status
        )

        self._log(
            level='INFO',
            category='database',
            content=f"所有设备/API评估完成，更新TaskCase状态: id={test_case_id}, status={new_status}, 影响行数: {update_count}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # P1.4: 通过 gRPC 更新 Task 状态
        if task and task.status in (TaskStatus.EVALUATING, TaskStatus.REEVALUATING):
            ok = task_acl_repository.update_task_status(task_id, new_status)
            self._log(
                level='INFO' if ok else 'ERROR',
                category='database',
                content=f"任务状态从 {task.status} 更新为 {new_status}: {'成功' if ok else '失败'}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            # 通过 gRPC 调用 task_service 通知进度
            from evaluation_service.infrastructure.acl.task_acl_repository import task_acl_repository
            task_acl_repository.notify_task_progress(task_id, force=True)

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
        finally:
            local_db_session.close()

    def process_group_dimension_results(self, resp_data, group_items, task_id, test_case_id, result_id, api_request_body, test_type='api'):
        """
        处理一组维度的评估结果

        P1.4: TestResult 通过 gRPC 读取（task_service）；TestResultDimension 本地写（自有 PO）

        Args:
            resp_data: API响应数据
            group_items: 维度组项列表 [(dim_data, dimension_result_id), ...]
            task_id: 任务ID
            test_case_id: 用例ID
            result_id: 结果ID
            api_request_body: API请求体
            test_type: 测试类型 (api 或 e2e)
        """
        # 使用单个数据库会话处理整组维度的更新（仅 TestResultDimension）
        local_db_session = get_db_session()
        try:
            # 获取api_id和device_id（P1.4: 通过 gRPC 读 TestResult）
            api_id = None
            device_id = None
            if result_id:
                test_result = task_acl_repository.get_test_result_by_id(result_id)
                if test_result:
                    api_id = test_result.api_id
                    device_id = test_result.device_id
                    test_case_id = test_case_id or test_result.test_case_id

            for dim_data, dimension_result_id in group_items:
                dim_id = dim_data['id']
                dim_name = dim_data['name']

                # 解析结果并打分
                raw_value, score = self.parse_dimension_result(resp_data, dim_data)

                # 记录维度评估详细结果到日志
                self._log(
                    level='INFO',
                    category='execution',
                    content=f"维度 {dim_name} 评估完成: "
                           f"用例ID: {test_case_id}, "
                           f"设备ID: {device_id}, "
                           f"API ID: {api_id}, "
                           f"原始值: {raw_value}, "
                           f"维度分值: {score}, "
                           f"响应数据: {json.dumps(resp_data, ensure_ascii=False)}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_id=api_id
                )

                # 更新维度评估结果，传入session避免重复创建
                self.update_dimension_result_completed(dimension_result_id, raw_value, score, task_id=task_id, test_case_id=test_case_id, api_raw_response=resp_data, api_request_body=api_request_body, session=local_db_session)

            # 循环结束后统一提交
            local_db_session.commit()

            # 检查是否所有维度都已完成评估，如果是，更新TaskCase状态
            if result_id and test_case_id:
                if self.check_all_dimensions_completed(result_id, task_id):
                    # Multi-round: aggregate before final status update
                    if self.is_multi_round_result(result_id):
                        self.aggregate_round_results(result_id, task_id, test_case_id)
                    self.update_task_case_status(result_id, True, task_id, test_case_id, test_type)
        finally:
            local_db_session.close()

    def check_all_dimensions_completed(self, result_id, task_id=None):
        """
        检查一个测试结果的所有维度是否都已完成评估
        """
        if not result_id:
            return True

        try:
            # 使用本地会话
            local_db_session = get_db_session()
            try:
                # 查询该结果的所有维度评估记录
                dimensions = local_db_session.query(TestResultDimension).filter_by(test_result_id=result_id).all()

                if not dimensions:
                    return True

                # 检查是否所有维度都已经不是进行中状态
                all_completed = True
                for dim in dimensions:
                    if dim.evaluation_status in [EvaluationStatus.PENDING, EvaluationStatus.RUNNING, EvaluationStatus.QUEUED, EvaluationStatus.CALCULATING]:
                        all_completed = False
                        break

                return all_completed
            finally:
                local_db_session.close()
        except Exception as e:
            self._log(level='ERROR', content=f"检查维度完成状态失败: {str(e)}", task_id=task_id)
            return False
