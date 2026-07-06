import json
import traceback
from datetime import datetime, timezone, timedelta
from backend.models.models import Dimension, TestResultDimension, TaskCase, TestResult, Task, TaskDevice, TaskAPI, TestCase, utc8now
from backend.models.database import db
from backend.controllers.log_controller import LogController
from backend.services.evaluation.evaluation_utils import extract_by_path, calculate_score

# 延迟导入app，避免循环导入和app未初始化问题
app = None

def get_app():
    """获取应用实例，延迟导入"""
    global app
    if app is None:
        from backend.app import app
    return app

class EvaluationResultProcessor:
    """
    评估结果处理器，负责解析API响应、计算分数并更新数据库
    """
    
    def mark_test_result_completed(self, result_id):
        """
        标记 TestResult 完成（用于没有评估维度的场景）
        注意：这只标记 TestResult 的执行状态，不影响 TaskCase 的最终状态
        TaskCase 的最终状态需要在所有 TestResult 都评估完成后统一更新
        """
        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                # 标记 TestResult 的执行状态为 completed
                update_count = local_db_session.query(TestResult).filter(
                    TestResult.id == result_id
                ).update({
                    'execution_status': 'completed'
                }, synchronize_session=False)
                
                local_db_session.commit()
                
                self._log(
                    level='DEBUG',
                    category='database',
                    content=f"标记 TestResult {result_id} 为完成状态，影响行数: {update_count}"
                )
            except Exception as e:
                self._log(
                    level='ERROR',
                    category='database',
                    content=f"标记 TestResult 完成状态失败: {str(e)}"
                )
                local_db_session.rollback()
            finally:
                local_db_session.close()
    
    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        """统一日志记录方法"""
        LogController.log_and_emit(
            level=level,
            module='Evaluation',
            category=kwargs.pop('category', 'execution'),
            content=content,
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
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
        
        # 获取应用上下文
        current_app = get_app()
        with current_app.app_context():
            try:
                # 如果提供了session则使用，否则创建新session
                local_db_session = session or db.session()
                should_close = session is None
                try:
                    test_result_dimension = local_db_session.query(TestResultDimension).get(dimension_result_id)
                    if test_result_dimension:
                        test_result_dimension.dimension_value = raw_value
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
            status='failed',
            evaluation_status='failed',
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
            status='completed',
            evaluation_status='completed',
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
        
        Args:
            result_id: 测试结果ID
            current_result_all_completed: 当前结果是否全部完成
            task_id: 任务ID
            test_case_id: 用例ID
            test_type: 测试类型 (api 或 e2e)，用于筛选对应类型的维度
        """
        # 获取应用上下文
        current_app = get_app()
        with current_app.app_context():
            try:
                # 使用本地会话确保独立可靠的会话
                local_db_session = db.session()
                try:
                    # 1. 获取任务信息以确定预期结果数量
                    task = local_db_session.query(Task).get(task_id)
                    if not task:
                        return
                    
                    expected_count = 0
                    if task.type == 'e2e':
                        expected_count = local_db_session.query(TaskDevice).filter_by(task_id=task_id).count()
                    else:
                        # API 任务通常按选中的 API 数量执行
                        expected_count = local_db_session.query(TaskAPI).filter_by(task_id=task_id).count()
                    
                    # 兜底逻辑：如果未找到关联，至少预期 1 个结果
                    if expected_count == 0:
                        expected_count = 1

                    # 2. 获取该用例目前已生成的所有测试结果
                    all_results = local_db_session.query(TestResult).filter_by(task_id=task_id, test_case_id=test_case_id).all()
                    
                    # 3. 获取用例配置中预期的评估维度总数
                    test_case = local_db_session.query(TestCase).get(test_case_id)
                    expected_dim_count = 0
                    if test_case and test_case.config:
                        dim_config = test_case.config.get('dimensions', {})
                        all_dim_ids = []
                        
                        for item in dim_config:
                            dim_id = item.get('id') if isinstance(item, dict) else item
                            if dim_id:
                                all_dim_ids.append(dim_id)
                        
                        # 仅统计数据库中启用且存在的维度
                        if all_dim_ids:
                            unique_dim_ids = list(set(all_dim_ids))
                            expected_dim_count = local_db_session.query(Dimension).filter(
                                Dimension.id.in_(unique_dim_ids), 
                                Dimension.status == True
                            ).count()

                    # 4. 检查是否所有预期结果都已采集并完成评估
                    if len(all_results) < expected_count:
                        self._log(
                            level='DEBUG',
                            category='database',
                            content=f"用例 {test_case_id} 结果未全 (已采集: {len(all_results)}/{expected_count})，暂不更新状态",
                            task_id=task_id,
                            test_case_id=test_case_id
                        )
                        return

                    case_all_finished = True
                    case_any_failed = False
                    
                    for res in all_results:
                        dims = local_db_session.query(TestResultDimension).filter_by(test_result_id=res.id).all()
                        
                        # 维度记录数量不足，说明评估服务还没创建完所有维度的记录
                        if len(dims) < expected_dim_count:
                            self._log(
                                level='DEBUG',
                                category='database',
                                content=f"用例 {test_case_id} 结果 {res.id} 维度未全 ({len(dims)}/{expected_dim_count})，继续等待",
                                task_id=task_id,
                                test_case_id=test_case_id
                            )
                            case_all_finished = False
                            break
                        
                        # 检查这个 TestResult 的所有维度是否都评估完成
                        res_finished = True
                        res_failed = False
                        for dim in dims:
                            # 如果有任何维度还在 pending 或 running，说明这个 TestResult 还没完成
                            if dim.evaluation_status in ['pending', 'running']:
                                res_finished = False
                                break
                            # 如果有任何维度评估失败，这个 TestResult 就是失败的
                            if dim.evaluation_status == 'failed':
                                res_failed = True
                        
                        # 如果这个 TestResult 还没完成，整体也不能算完成
                        if not res_finished:
                            case_all_finished = False
                        # 如果这个 TestResult 失败了，整体就标记为失败
                        if res_failed:
                            case_any_failed = True

                    if not case_all_finished:
                        return

                    # 5. 只有当维度结果搜集全且都评估完成了，才更新最终状态
                    new_status = 'failed' if case_any_failed else 'completed'
                    new_evaluation_status = 'failed' if case_any_failed else 'completed'
                    
                    # 使用直接的SQL UPDATE语句来确保所有状态都被正确更新，增加状态保护防止覆盖已停止任务
                    update_count = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.test_case_id == test_case_id,
                        TaskCase.status != 'stopped'
                    ).update({
                        'status': new_status,
                        'evaluation_status': new_evaluation_status,
                        'completed_at': utc8now()  # 确保完成时间被设置，使用统一的东八区时间
                    }, synchronize_session=False)
                    
                    self._log(
                        level='INFO',
                        category='database',
                        content=f"所有设备/API评估完成，更新TaskCase状态: id={test_case_id}, status={new_status}, 影响行数: {update_count}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    
                    local_db_session.commit()
                    
                    task = local_db_session.query(Task).get(task_id)
                    if task and task.status == 'evaluating':
                        task.status = new_status
                        local_db_session.commit()
                        
                        self._log(
                            level='INFO',
                            category='database',
                            content=f"任务状态从 evaluating 更新为 {new_status}",
                            task_id=task_id,
                            test_case_id=test_case_id
                        )
                        
                        from backend.services.execution.execution_engine import execution_engine
                        execution_engine._emit_progress(task, force=True)
                except Exception as e:
                    self._log(
                        level='ERROR',
                        category='database',
                        content=f"更新TaskCase状态失败: {str(e)}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    local_db_session.rollback()
                finally:
                    local_db_session.close()
            except Exception as e:
                self._log(level='ERROR', content=f"获取数据库会话失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
    
    def update_all_dimensions_in_group_failed(self, group_items, error_message, task_id, test_case_id=None, api_raw_response=None, api_request_body=None):
        """
        更新组内所有维度的评估结果为失败状态
        """
        # 使用应用上下文
        current_app = get_app()
        with current_app.app_context():
            # 使用单个会话
            local_db_session = db.session()
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
                
                # 更新 TaskCase 的 evaluation_status 和 status 都为 failed
                if test_case_id:
                    try:
                        update_count = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.test_case_id == test_case_id,
                            TaskCase.status != 'stopped'
                        ).update({
                            'evaluation_status': 'failed',
                            'status': 'failed',
                            'completed_at': utc8now()
                        }, synchronize_session=False)
                        
                        local_db_session.commit()
                        
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
                        local_db_session.rollback()
                
                local_db_session.commit()
            finally:
                local_db_session.close()
    
    def process_single_dimension_result(self, resp_data, dim_data, dimension_result_id, task_id, test_case_id=None, result_id=None, api_request_body=None):
        """
        处理单个维度的评估结果
        """
        dim_name = dim_data['name']
        
        # 获取api_id和device_id
        api_id = None
        device_id = None
        if result_id:
            current_app = get_app()
            with current_app.app_context():
                local_db_session = db.session()
                try:
                    test_result = local_db_session.query(TestResult).get(result_id)
                    if test_result:
                        api_id = test_result.api_id
                        device_id = test_result.device_id
                        test_case_id = test_case_id or test_result.test_case_id
                finally:
                    local_db_session.close()
        
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
        
        # 更新维度评估结果 (update_dimension_result_completed 内部已经处理了 app_context)
        self.update_dimension_result_completed(dimension_result_id, raw_value, score, task_id=task_id, test_case_id=test_case_id, api_raw_response=resp_data, api_request_body=api_request_body)
        
        # 返回结果，用于统计
        return {
            'dimension_id': dim_data['id'],
            'dimension_value': raw_value,
            'score': score,
            'status': 'completed' if raw_value is not None else 'failed',
            'evaluation_status': 'completed' if raw_value is not None else 'failed',
            'error_message': None
        }
    
    def process_group_dimension_results(self, resp_data, group_items, task_id, test_case_id=None, result_id=None, api_request_body=None, test_type=None):
        """
        处理一组维度的评估结果
        
        Args:
            resp_data: API响应数据
            group_items: 维度组
            task_id: 任务ID
            test_case_id: 用例ID
            result_id: 结果ID
            api_request_body: API请求体
            test_type: 测试类型 (api 或 e2e)
        """
        # 使用应用上下文确保可以访问数据库
        current_app = get_app()
        with current_app.app_context():
            # 使用单个数据库会话处理整组维度的更新，显著减少数据库锁定风险
            local_db_session = db.session()
            try:
                # 获取api_id和device_id
                api_id = None
                device_id = None
                if result_id:
                    test_result = local_db_session.query(TestResult).get(result_id)
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
            
        # 获取应用上下文
        current_app = get_app()
        with current_app.app_context():
            try:
                # 使用本地会话
                local_db_session = db.session()
                try:
                    # 查询该结果的所有维度评估记录
                    dimensions = local_db_session.query(TestResultDimension).filter_by(test_result_id=result_id).all()
                    
                    if not dimensions:
                        return True
                    
                    # 检查是否所有维度都已经不是 pending 状态
                    all_completed = True
                    for dim in dimensions:
                        if dim.evaluation_status == 'pending':
                            all_completed = False
                            break
                    
                    return all_completed
                finally:
                    local_db_session.close()
            except Exception as e:
                self._log(level='ERROR', content=f"检查维度完成状态失败: {str(e)}", task_id=task_id)
                return False

    def is_multi_round_result(self, result_id):
        """
        Check if a test result contains multi-round evaluation data.
        
        Returns True if any TestResultDimension has round_number set.
        """
        if not result_id:
            return False

        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                has_rounds = local_db_session.query(TestResultDimension).filter(
                    TestResultDimension.test_result_id == result_id,
                    TestResultDimension.round_number.isnot(None),
                ).first()
                return has_rounds is not None
            finally:
                local_db_session.close()

    def check_all_round_dimensions_completed(self, result_id):
        """
        Check if all dimension evaluations in a multi-round result are done.
        
        Returns True when no TestResultDimension is still in 'pending' status.
        """
        if not result_id:
            return True

        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                pending_count = local_db_session.query(TestResultDimension).filter(
                    TestResultDimension.test_result_id == result_id,
                    TestResultDimension.evaluation_status == 'pending',
                ).count()
                return pending_count == 0
            finally:
                local_db_session.close()

    def aggregate_round_results(self, result_id, task_id, test_case_id):
        """
        Aggregate multi-round evaluation results into per-dimension averages.
        
        Queries all TestResultDimension records for the given result_id,
        groups them by dimension name, computes arithmetic mean scores,
        and writes the aggregated data to TestResult.algorithm_result['aggregated'].
        
        Returns:
            dict with keys like avg_{dim_name}, round_count, completed_rounds
        """
        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                dim_results = local_db_session.query(
                    TestResultDimension
                ).filter(
                    TestResultDimension.test_result_id == result_id
                ).all()

                # Group by dimension name
                dim_groups = {}
                for dr in dim_results:
                    dim_obj = local_db_session.query(Dimension).get(dr.dimension_id) if dr.dimension_id else None
                    key = dim_obj.name if dim_obj else str(dr.dimension_id)
                    if key not in dim_groups:
                        dim_groups[key] = []
                    dim_groups[key].append({
                        'round_number': dr.round_number,
                        'score': dr.score,
                        'raw_value': dr.raw_value,
                        'evaluation_status': dr.evaluation_status,
                    })

                aggregated = {}
                for dim_name, results in dim_groups.items():
                    completed = [
                        r for r in results
                        if r['evaluation_status'] == 'completed' and r['score'] is not None
                    ]
                    if completed:
                        avg_score = sum(r['score'] for r in completed) / len(completed)
                        aggregated[f'avg_{dim_name}'] = round(avg_score, 4)
                    else:
                        aggregated[f'avg_{dim_name}'] = None

                aggregated['round_count'] = len(set(
                    r['round_number'] for r in dim_results if r['round_number'] is not None
                ))
                aggregated['completed_rounds'] = len(set(
                    r['round_number'] for r in dim_results
                    if r['round_number'] is not None and r['evaluation_status'] == 'completed'
                ))

                self._update_algorithm_result_aggregated(local_db_session, result_id, aggregated)
                local_db_session.commit()

                self._log(
                    level='INFO',
                    category='execution',
                    content=f"多轮评估聚合完成: result_id={result_id}, aggregated={json.dumps(aggregated, ensure_ascii=False)}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                )

                return aggregated
            except Exception as e:
                local_db_session.rollback()
                self._log(
                    level='ERROR',
                    content=f"多轮评估聚合失败: {str(e)}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                )
                return {}
            finally:
                local_db_session.close()

    def _update_algorithm_result_aggregated(self, db_session, result_id, aggregated):
        """
        Write aggregated results into TestResult.algorithm_result['aggregated'].
        """
        test_result = db_session.query(TestResult).filter(
            TestResult.id == result_id
        ).first()

        if not test_result:
            return

        result_data = test_result.algorithm_result
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except (json.JSONDecodeError, TypeError):
                result_data = {}
        if not isinstance(result_data, dict):
            result_data = {}

        result_data['aggregated'] = aggregated
        test_result.algorithm_result = json.dumps(result_data, ensure_ascii=False)
