import json
import traceback
from datetime import datetime, timezone, timedelta
# P1.1: Dimension / TestResultDimension 改用本服务自有 PO
from evaluation_service.infrastructure.persistence.orm_models import Dimension, TestResultDimension
# P1.4: 跨服务 PO 改为 gRPC 调 task_service
from evaluation_service.infrastructure.acl import task_acl_repository
from shared.models.database import get_db_session
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskCaseStatus, TaskStatus, ACTIVE_EVALUATION_STATUSES,
)
from shared.models.common_enums import TestType
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

        # 预提取 algorithm_results 快照（无评估维度场景）
        if ok:
            try:
                tr = task_acl_repository.get_test_result_by_id(result_id)
                if tr:
                    self._build_and_store_algorithm_results(
                        result_id,
                        getattr(tr, 'task_id', None),
                        getattr(tr, 'test_case_id', None)
                    )
            except Exception as e:
                self._log(
                    level='WARNING',
                    category='execution',
                    content=f"预提取 algorithm_results 失败: {e}",
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
        if task.type == TestType.E2E.value:
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
                    if dim.evaluation_status in ACTIVE_EVALUATION_STATUSES:
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
        """应用最终状态

        P1.4: 通过 gRPC 更新 TaskCase 和 Task
        事件驱动改造: 同时发布 CaseEvaluated 事件到 Redis 事件总线，
        消费方（task_service）订阅后更新状态，替代 gRPC 同步回传的强依赖。
        gRPC 调用保留作为同步路径，事件作为异步通知补充。
        """
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

        # 发布用例评估完成事件到事件总线（异步通知 task_service）
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        is_success = new_evaluation_status == EvaluationStatus.COMPLETED
        EventBus().publish(
            EventChannel.CASE_EVENTS,
            EventType.CASE_EVALUATION_COMPLETED if is_success else EventType.CASE_FAILED,
            {
                'task_id': str(task_id),
                'test_case_id': str(test_case_id),
                'evaluation_status': new_evaluation_status,
                'case_status': new_status,
                'success': is_success,
            }
        )

        # P1.4: 通过 gRPC 更新 Task 状态（同步路径，保留兼容）
        if task and task.status in (TaskStatus.EVALUATING, TaskStatus.REEVALUATING):
            ok = task_acl_repository.update_task_status(task_id, new_status)
            self._log(
                level='INFO' if ok else 'ERROR',
                category='database',
                content=f"任务状态从 {task.status} 更新为 {new_status}: {'成功' if ok else '失败'}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            # 发布任务级事件（评估阶段完成）
            task_event_type = EventType.TASK_COMPLETED if new_status == TaskStatus.COMPLETED else (
                EventType.TASK_FAILED if new_status == TaskStatus.FAILED else None
            )
            if task_event_type:
                EventBus().publish(
                    EventChannel.TASK_EVENTS,
                    task_event_type,
                    {
                        'task_id': str(task_id),
                        'status': new_status,
                        'test_case_id': str(test_case_id) if test_case_id else None,
                    }
                )

            # 通过 gRPC 调用 task_service 通知进度（同步路径，保留兼容）
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

    def process_group_dimension_results(self, resp_data, group_items, task_id, test_case_id, result_id, api_request_body, test_type=TestType.API.value):
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

            # 预提取 algorithm_results 快照，存入 result_data['algorithm_results']
            self._build_and_store_algorithm_results(
                result_id, task_id, test_case_id, test_type
            )

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
                    if dim.evaluation_status in ACTIVE_EVALUATION_STATUSES:
                        all_completed = False
                        break

                return all_completed
            finally:
                local_db_session.close()
        except Exception as e:
            self._log(level='ERROR', content=f"检查维度完成状态失败: {str(e)}", task_id=task_id)
            return False

    def _build_and_store_algorithm_results(self, result_id, task_id, test_case_id, test_type=TestType.API.value):
        """预提取 algorithm_results 扁平列表并存入 result_data['algorithm_results']。

        在评估完成后调用，报告页和详情页可直接读取，无需重复提取。
        """
        if not result_id:
            return
        try:
            test_result = task_acl_repository.get_test_result_by_id(result_id)
            if not test_result:
                return

            # 获取 algorithm_type 和 resource
            algorithm_type = ''
            # algorithm_type 通过 TestResult 获取（若 DTO 不含则从 Task/TestCase 推断）
            algo_result = deserialize_algorithm_result(test_result.algorithm_result)

            task = task_acl_repository.get_task_by_id(task_id) if task_id else None

            # 获取 resource name
            device_id = test_result.device_id
            api_id = test_result.api_id
            # 通过 gRPC 获取设备/API 名称
            resource = f'result_{result_id}'
            try:
                if device_id:
                    from shared.clients.grpc_clients import get_device_config_service_stub
                    from shared.proto import device_service_pb2 as dev_pb
                    from shared.utils.grpc_json import loads as _grpc_loads
                    dev_stub = get_device_config_service_stub()
                    dev_resp = dev_stub.GetDevice(dev_pb.GetDeviceRequest(device_id=device_id))
                    if dev_resp.success:
                        dev_data = _grpc_loads(dev_resp.data, {})
                        resource = dev_data.get('name') or f'device_{device_id}'
                elif api_id:
                    from shared.clients.grpc_clients import get_api_test_service_stub
                    from shared.proto import api_test_service_pb2 as api_pb
                    from shared.utils.grpc_json import loads as _grpc_loads
                    api_stub = get_api_test_service_stub()
                    api_resp = api_stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=api_id))
                    if api_resp.success:
                        api_data = _grpc_loads(api_resp.data, {})
                        resource = api_data.get('name') or f'api_{api_id}'
            except Exception:
                pass

            # 加载 algo_res 和 result_data
            from shared.utils.result_data_store import load_full_result_data, write_result_data_file, split_result_data
            result_data = load_full_result_data(test_result.result_data, test_result.result_data_path)
            if not isinstance(result_data, dict):
                result_data = {}

            if not (algo_result or result_data):
                return

            # 查询 dim_result_rows（含 api_raw_response，本地 DB）
            local_db_session = get_db_session()
            try:
                dim_result_rows = local_db_session.query(
                    TestResultDimension
                ).filter(TestResultDimension.test_result_id == result_id).all()
            finally:
                local_db_session.close()

            # 查询 aux_params_map（通过 gRPC 调 algorithm_service）
            all_dim_ids = set(dr.dimension_id for dr in dim_result_rows if dr.dimension_id)
            aux_params_map = {}
            if all_dim_ids:
                try:
                    from evaluation_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
                    _algo_repo = AlgorithmRepository()
                    for dim_id in all_dim_ids:
                        params = _algo_repo.get_dimension_params(dim_id)
                        if not params:
                            continue
                        for p in params:
                            if not isinstance(p, dict):
                                continue
                            if p.get('param_direction') != 'output':
                                continue
                            if p.get('output_role') != 'aux':
                                continue
                            if not p.get('visible_in_report'):
                                continue
                            dim_name = p.get('dimension_name') or ''
                            if dim_id not in aux_params_map:
                                aux_params_map[dim_id] = []
                            aux_params_map[dim_id].append({'param': p, 'dimension_name': dim_name})
                except Exception:
                    pass

            # 查询 output_fields
            output_fields = []
            if algorithm_type:
                try:
                    from evaluation_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
                    _algo_repo = AlgorithmRepository()
                    output_fields = _algo_repo.get_output_fields(algorithm_type) or []
                except Exception:
                    pass

            # 调用公共方法构建 algorithm_results
            from report_service.application.services.report_data_builder import ReportDataBuilder
            algorithm_results = ReportDataBuilder.build_algorithm_results_for_result(
                test_result, resource, algo_result, result_data,
                aux_params_map, dim_result_rows, output_fields, algorithm_type
            )

            # 存入 result_data['algorithm_results']
            result_data['algorithm_results'] = algorithm_results if algorithm_results else None

            # 写回：大字段存文件，轻量部分存 DB
            lightweight, has_heavy = split_result_data(result_data)
            result_data_path = None
            if has_heavy:
                device_sn = str(api_id or result_id)
                result_data_path = write_result_data_file(task_id, test_case_id, device_sn, result_data)

            task_acl_repository.update_test_result_data(
                result_id, lightweight, result_data_path
            )

        except Exception as e:
            self._log(
                level='WARNING',
                category='execution',
                content=f"预提取 algorithm_results 失败: {e}",
                task_id=task_id, test_case_id=test_case_id
            )
