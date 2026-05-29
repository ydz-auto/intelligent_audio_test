import time
import traceback
import queue
import threading
import json
from threading import Lock
from backend.models.models import Dimension, TestResultDimension, TestCase, TaskCase, Task
from backend.models.database import db
from backend.controllers.log_controller import LogController

from backend.utils.evaluation_api_client import evaluationApiClient
from backend.utils.evaluation_result_processor import EvaluationResultProcessor
from backend.algorithm.field_mapper import get_field_mapper

app = None

def get_app():
    global app
    if app is None:
        from backend.app import app
    return app

class EndpointWorker:
    def __init__(self, endpoint_url, eval_service, max_timeout=30):
        self.endpoint_url = endpoint_url
        self.eval_service = eval_service
        self.max_timeout = max_timeout
        self.task_queue = queue.Queue()
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.completion_events = {}  # task_id -> threading.Event for completion signaling
        self.completion_events_lock = threading.Lock()
        self._log(level='INFO', content=f"端点Worker已创建: {endpoint_url}, 超时时间: {max_timeout}秒")
    
    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        LogController.log_and_emit(
            level=level,
            module='Evaluation',
            category=kwargs.pop('category', 'execution'),
            content=content,
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            endpoint=self.endpoint_url,
            **kwargs
        )
    
    def start(self):
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.stop_event.clear()
            self.worker_thread = threading.Thread(
                target=self._worker_loop,
                name=f"EndpointWorker-{self.endpoint_url[:30]}",
                daemon=True
            )
            self.worker_thread.start()
            self._log(level='INFO', content=f"端点Worker已启动: {self.endpoint_url}")
    
    def stop(self):
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)
        self._log(level='INFO', content=f"端点Worker已停止: {self.endpoint_url}")
    
    def _worker_loop(self):
        current_app = get_app()
        for _ in range(10):
            current_app = get_app()
            if current_app is not None:
                break
            time.sleep(1)
        
        if current_app is None:
            self._log(level='ERROR', content=f"端点Worker启动失败: {self.endpoint_url}")
            return
        
        with current_app.app_context():
            while not self.stop_event.is_set():
                try:
                    task_data = self.task_queue.get(timeout=1.0)
                    task_id = task_data.get('task_id')
                    
                    try:
                        self._log(
                            level='INFO',
                            content=f"端点Worker开始处理任务: TaskID={task_id}, ResultID={task_data['result_id']}, TestCaseID={task_data.get('test_case_id')}",
                            task_id=task_id,
                            test_case_id=task_data.get('test_case_id')
                        )
                        self._execute_evaluation(**task_data)
                        
                        self._log(
                            level='INFO',
                            content=f"端点Worker完成任务: TaskID={task_id}, ResultID={task_data['result_id']}, TestCaseID={task_data.get('test_case_id')}",
                            task_id=task_id,
                            test_case_id=task_data.get('test_case_id')
                        )
                    except Exception as e:
                        self._log(
                            level='ERROR',
                            content=f"端点Worker处理任务异常: {str(e)}\n{traceback.format_exc()}",
                            task_id=task_data.get('task_id'),
                            test_case_id=task_data.get('test_case_id')
                        )
                    finally:
                        self.task_queue.task_done()
                        
                        # 标记任务完成
                        with self.completion_events_lock:
                            if task_id in self.completion_events:
                                self.completion_events[task_id].set()
                                del self.completion_events[task_id]
                        
                except queue.Empty:
                    continue
                except Exception as e:
                    self._log(level='ERROR', content=f"端点Worker循环异常: {str(e)}")
                    time.sleep(1)
    
    def _execute_evaluation(self, task_id, result_id, test_case_id, algorithm_result,
                           representative_dim_data, group_items, algorithm_type='translation',
                           test_type='api', **kwargs):
        field_mapper = get_field_mapper()
        output_field_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)
        
        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] 接收到的 representative_dim_data: id={representative_dim_data.get('id')}, name={representative_dim_data.get('name')}, task_type_code={representative_dim_data.get('task_type_code')}, api_settings_keys={list(representative_dim_data.get('api_settings', {}).keys()) if representative_dim_data.get('api_settings') else []}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] 接收到的 group_items 维度IDs: {[item[0]['id'] for item in group_items]}, 维度Names: {[item[0]['name'] for item in group_items]}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] output_field_keys={output_field_keys}, algorithm_result_keys={list(algorithm_result.keys()) if isinstance(algorithm_result, dict) else 'not dict'}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        eval_input_fields = field_mapper.get_evaluation_input_fields(algorithm_type)
        
        algo_results = {}
        if isinstance(algorithm_result, dict):
            for key in output_field_keys:
                val = algorithm_result.get(key)
                self._log(
                    level='DEBUG',
                    content=f"[algo_results] key={key}, value={val}, value_type={type(val)}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                algo_results[key] = val if val is not None else ''

        context = {
            "algorithm_result": algorithm_result,
            "algorithm_type": algorithm_type
        }
        
        for key, value in algo_results.items():
            if key not in context:
                context[key] = value
        
        for field_key, field_info in eval_input_fields.items():
            field_type = field_info.get('type', 'text')
            field_value = kwargs.get(field_key)
            if field_value:
                if field_key in output_field_keys and field_key in context:
                    continue
                if isinstance(field_value, dict) and 'text' in field_value:
                    context[field_key] = field_value
                else:
                    context[field_key] = {
                        'value': field_value,
                        'field_type': field_type
                    }
        
        for key, value in kwargs.items():
            if key not in context:
                context[key] = value
        
        endpoints = representative_dim_data.get('api_endpoints', [])
        if not endpoints and representative_dim_data.get('api_url'):
            endpoints = [{"url": representative_dim_data.get('api_url'), "name": "Master"}]
            
        dim_names = [item[0]['name'] for item in group_items]
        
        api_settings = representative_dim_data.get('api_settings', {})
        body_template = api_settings.get('body_template')
        method = api_settings.get('method', 'POST')
        headers = api_settings.get('headers', {})
        
        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] body_template={body_template}, context_keys={list(context.keys())}, output_field_keys={output_field_keys}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        payload = self.eval_service.api_client.build_payload(body_template, context, task_id=task_id, test_case_id=test_case_id, algorithm_type=algorithm_type)
        
        dim_info = {
            'dimension_type': representative_dim_data.get('dimension_type', 'main'),
            'parent_dimension_id': representative_dim_data.get('parent_dimension_id'),
            'task_type_code': representative_dim_data.get('task_type_code')
        }
        
        try:
            selected_url, resp_data = self.eval_service.api_client.make_api_request_with_fallback(
                endpoints=endpoints,
                method=method,
                headers=headers,
                payload=payload,
                task_id=task_id,
                dim_names=dim_names,
                api_url=representative_dim_data.get('api_url'),
                test_case_id=test_case_id,
                dim_info=dim_info
            )
            
            if resp_data and '__error__' not in resp_data:
                self.eval_service.result_processor.process_group_dimension_results(
                    resp_data=resp_data,
                    group_items=group_items,
                    task_id=task_id,
                    test_case_id=test_case_id,
                    result_id=result_id,
                    api_request_body=payload,
                    test_type=test_type
                )
            else:
                error_msg = resp_data.get('__error__', '未知错误') if isinstance(resp_data, dict) else 'API 调用失败'
                self.eval_service.result_processor.update_all_dimensions_in_group_failed(
                    group_items=group_items,
                    error_message=error_msg,
                    task_id=task_id,
                    test_case_id=test_case_id,
                    api_raw_response=resp_data,
                    api_request_body=payload
                )
        except Exception as e:
            error_msg = f"评估维度组异常: {str(e)}\n{traceback.format_exc()}"
            self.eval_service.result_processor.update_all_dimensions_in_group_failed(
                group_items=group_items,
                error_message=error_msg,
                task_id=task_id,
                test_case_id=test_case_id,
                api_request_body=payload
            )


class EvaluationService:
    def __init__(self):
        self.current_test_case_id = None
        self.current_api_id = None
        self.current_device_id = None
        
        self._log(
            level='info',
            content='开始初始化评估服务',
            category='system'
        )
        
        self.api_cache = {}
        self.global_lock = Lock()
        
        self.api_client = evaluationApiClient()
        self.result_processor = EvaluationResultProcessor()
        
        self.endpoint_workers = {}
        self.endpoint_workers_lock = Lock()
        self.stop_event = threading.Event()
        
        self._load_all_endpoint_configs()
        
        self.api_client.init_thread_pool()
        
        self._log(
            level='info',
            content='评估服务初始化完成 (多端点Worker架构)',
            category='system'
        )
    
    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
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
    
    def _get_timeout_from_dim_config(self, dim_data, default_timeout=30):
        api_settings = dim_data.get('api_settings', {})
        
        timeout = api_settings.get('timeout')
        if timeout:
            return timeout
        
        endpoints = dim_data.get('api_endpoints', [])
        if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
            endpoint_item = endpoints[0]
            timeout = endpoint_item.get('max_timeout') or endpoint_item.get('maxTimeout')
            if timeout:
                return timeout
        
        api_url = dim_data.get('api_url')
        if api_url:
            for endpoint_url, worker in self.endpoint_workers.items():
                if endpoint_url == api_url:
                    return worker.max_timeout
        
        return default_timeout
    
    def _get_or_create_worker(self, endpoint_url, dim_data):
        with self.endpoint_workers_lock:
            if endpoint_url not in self.endpoint_workers:
                max_timeout = self._get_timeout_from_dim_config(dim_data, 30)
                worker = EndpointWorker(endpoint_url, self, max_timeout=max_timeout)
                self.endpoint_workers[endpoint_url] = worker
                worker.start()
                self._log(
                    level='INFO',
                    content=f"为端点创建新Worker: {endpoint_url}, 超时: {max_timeout}秒"
                )
            return self.endpoint_workers[endpoint_url]
    
    def _load_all_endpoint_configs(self):
        current_app = get_app()
        if current_app:
            with current_app.app_context():
                try:
                    local_db_session = db.session()
                    try:
                        dimensions = local_db_session.query(Dimension).all()
                        self.api_client.load_endpoint_configs(dimensions)
                        self._log(level='info', content=f"已从数据库加载 {len(dimensions)} 个维度的端点配置", category='system')
                        
                        for dim in dimensions:
                            if dim.api_endpoints and isinstance(dim.api_endpoints, list):
                                for endpoint_item in dim.api_endpoints:
                                    endpoint_url = endpoint_item.get('url') or endpoint_item.get('endpoint')
                                    if endpoint_url:
                                        timeout = endpoint_item.get('max_timeout') or endpoint_item.get('maxTimeout', 30)
                                        if endpoint_url not in self.endpoint_workers:
                                            worker = EndpointWorker(endpoint_url, self, max_timeout=timeout)
                                            self.endpoint_workers[endpoint_url] = worker
                                            worker.start()
                                            self._log(
                                                level='INFO',
                                                content=f"预创建端点Worker: {endpoint_url}, 超时: {timeout}秒"
                                            )
                    finally:
                        local_db_session.close()
                except Exception as e:
                    self._log(level='error', content=f"加载维度配置失败: {str(e)}", category='system')
    
    def evaluate_case(self, task_id, result_id, test_case_id, algorithm_result, **kwargs):
        field_mapper = get_field_mapper()
        test_type = kwargs.get('test_type', 'api')
        
        # DEBUG: 记录传入的 result_id 值和类型
        self._log(
            level='DEBUG',
            content=f"[DEBUG evaluate_case] 传入参数: task_id={task_id}, result_id={result_id}, result_id_type={type(result_id)}, test_case_id={test_case_id}, test_type={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        self._log(
            level='INFO',
            content=f"用例评估请求: TaskID={task_id}, TestCaseID={test_case_id}, ResultID={result_id}, TestType={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                test_case = local_db_session.query(TestCase).get(test_case_id)
                if not test_case:
                    self._log(level='ERROR', content=f"找不到测试用例 {test_case_id}", task_id=task_id)
                    return False

                algorithm_type = test_case.algorithm_type if test_case.algorithm_type else kwargs.get('algorithm_type', 'translation')
                
                eval_input_fields = field_mapper.get_evaluation_input_fields(algorithm_type)
                
                ref_texts = {}
                for field_key, field_info in eval_input_fields.items():
                    field_type = field_info.get('type', 'text')
                    field_value = kwargs.get(field_key)
                    self._log(
                        level='DEBUG',
                        content=f"[kwargs field_key] field_key={field_key}, field_value={field_value}, field_value_type={type(field_value)}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    if field_value:
                        if field_key in {'rttm_ref', 'stm_ref', 'asr_ref', 'asr_rerference_text'} and isinstance(field_value, dict) and 'text' in field_value:
                            ref_texts[field_key] = {
                                'text': field_value.get('text', ''),
                                'json': field_value.get('json', field_value.get('segments', []))
                            }
                        else:
                            ref_texts[field_key] = {
                                'value': field_value,
                                'field_type': field_type
                            }
                
                self._log(
                    level='DEBUG',
                    content=f"[ref_texts] final ref_texts={ref_texts}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                
                self._log(
                    level='DEBUG',
                    content=f"[ref_texts] final ref_texts={ref_texts}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )

                test_case_config = test_case.config or {}
                dimensions_config = test_case_config.get('dimensions', {})
            finally:
                local_db_session.close()
        
        dimension_ids = []
        dim_list = dimensions_config.get(test_type, [])
        for item in dim_list:
            if isinstance(item, dict):
                dimension_id = item.get('id')
                if dimension_id:
                    dimension_ids.append(dimension_id)
            else:
                dimension_ids.append(item)
        
        unique_dimension_ids = list(set(dimension_ids))
        
        self._log(
            level='DEBUG',
            content=f"用例 {test_case.name} 的维度配置: {json.dumps(dimensions_config, ensure_ascii=False)}, 提取的维度IDs: {dimension_ids}, 去重后: {unique_dimension_ids}",
            task_id=task_id
        )
        
        if not unique_dimension_ids:
            self._log(level='WARNING', content=f"用例 {test_case.name} 没有配置任何维度，跳过评估", task_id=task_id, test_case_id=test_case_id)
            # 没有评估维度时，直接标记 TestResult 的执行状态为 completed
            # TaskCase 的最终状态需要等所有 TestResult 评估完成后统一更新
            self.result_processor.mark_test_result_completed(result_id)
            self._post_evaluate_updates(task_id, test_case_id)
            return False
        
        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                dimensions = local_db_session.query(Dimension).filter(
                    Dimension.id.in_(unique_dimension_ids), 
                    Dimension.status == True
                ).all()
                if not dimensions:
                    self._log(level='WARNING', content=f"用例 {test_case.name} 关联的维度都不可用，跳过评估", task_id=task_id, test_case_id=test_case_id)
                    # 没有可用评估维度时，直接标记 TestResult 的执行状态为 completed
                    self.result_processor.mark_test_result_completed(result_id)
                    self._post_evaluate_updates(task_id, test_case_id)
                    return False
                
                dimension_data_list = []
                for dim in dimensions:
                    dim_dict = {
                        'id': dim.id,
                        'name': dim.name,
                        'keywords': dim.keywords,
                        'rule': dim.rule,
                        'api_endpoints': dim.api_endpoints,
                        'api_settings': dim.api_settings,
                        'api_url': dim.api_url,
                        'dimension_type': getattr(dim, 'dimension_type', 'main'),
                        'parent_dimension_id': getattr(dim, 'parent_dimension_id', None),
                        'task_type_code': getattr(dim, 'task_type_code', None)
                    }
                    
                    if getattr(dim, 'dimension_type', 'main') == 'sub' and not dim_dict.get('api_endpoints') and not dim_dict.get('api_url'):
                        parent_dim = getattr(dim, 'parent_dimension', None)
                        if parent_dim:
                            if not dim_dict.get('api_endpoints'):
                                dim_dict['api_endpoints'] = parent_dim.api_endpoints
                            if not dim_dict.get('api_url'):
                                dim_dict['api_url'] = parent_dim.api_url
                            if not dim_dict.get('api_settings'):
                                dim_dict['api_settings'] = parent_dim.api_settings
                            if not dim_dict.get('task_type_code'):
                                dim_dict['task_type_code'] = parent_dim.task_type_code
                    
                    dimension_data_list.append(dim_dict)
            
                self._log(
                    level='DEBUG',
                    content=f"[维度数据] 用例 {test_case.name} 加载的维度列表: {[{ 'id': d['id'], 'name': d['name'], 'task_type_code': d.get('task_type_code'), 'api_url': d.get('api_url'), 'api_settings_keys': list(d.get('api_settings', {}).keys()) if d.get('api_settings') else [] } for d in dimension_data_list]}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
            finally:
                local_db_session.close()
        
        self._log(level='INFO', content=f"开始评估 {len(dimension_data_list)} 个维度，分发到端点队列", task_id=task_id, test_case_id=test_case_id)
        
        current_app = get_app()
        with current_app.app_context():
            update_session = db.session()
            try:
                tc_rel = update_session.query(TaskCase).filter_by(task_id=task_id, test_case_id=test_case_id).first()
                if tc_rel and tc_rel.evaluation_status not in ['running', 'stopped']:
                    tc_rel.evaluation_status = 'running'
                    update_session.commit()
            except Exception as e:
                self._log(level='WARNING', content=f"更新评估状态失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
                update_session.rollback()
            finally:
                update_session.close()
        
        dimension_result_map = {}
        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
            dim_name = dim_data['name']

            current_app = get_app()
            dimension_result_id = None
            with current_app.app_context():
                local_db_session = db.session()
                try:
                    # DEBUG: 记录创建 TestResultDimension 时的 result_id 值和类型
                    self._log(
                        level='DEBUG',
                        content=f"[DEBUG TestResultDimension] 创建前: result_id={result_id}, result_id_type={type(result_id)}, dim_id={dim_id}, dim_name={dim_name}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    
                    # 获取算法类型
                    algo_type = algorithm_type
                    if not algo_type or algo_type == 'translation':
                        test_case = local_db_session.query(TestCase).get(test_case_id)
                        if test_case and test_case.algorithm_type:
                            algo_type = test_case.algorithm_type

                    test_result_dimension = TestResultDimension(
                        test_result_id=result_id,
                        dimension_id=dim_id,
                        algorithm_type=algo_type,
                        status=None,
                        evaluation_status='pending',
                        error_message=None
                    )
                    
                    # DEBUG: 记录 TestResultDimension 对象的属性值
                    self._log(
                        level='DEBUG',
                        content=f"[DEBUG TestResultDimension] 对象属性: test_result_id={test_result_dimension.test_result_id}, dimension_id={test_result_dimension.dimension_id}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    
                    local_db_session.add(test_result_dimension)
                    local_db_session.flush()
                    dimension_result_id = test_result_dimension.id
                    
                    # DEBUG: 记录 flush 后数据库中的实际值
                    self._log(
                        level='DEBUG',
                        content=f"[DEBUG TestResultDimension] flush后查询: id={dimension_result_id}, test_result_id={test_result_dimension.test_result_id}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    
                    local_db_session.commit()
                    
                    # DEBUG: 验证提交后的数据
                    verify_dim = local_db_session.query(TestResultDimension).get(dimension_result_id)
                    if verify_dim:
                        self._log(
                            level='DEBUG',
                            content=f"[DEBUG TestResultDimension] commit后验证: id={verify_dim.id}, test_result_id={verify_dim.test_result_id}",
                            task_id=task_id,
                            test_case_id=test_case_id
                        )
                    else:
                        self._log(
                            level='ERROR',
                            content=f"[DEBUG TestResultDimension] commit后验证失败: 无法查询到 id={dimension_result_id}",
                            task_id=task_id,
                            test_case_id=test_case_id
                        )
                    
                    dimension_result_map[dim_id] = dimension_result_id
                    
                    self._log(
                        level='DEBUG',
                        content=f"创建维度记录: dim_name={dim_name}, dim_id={dim_id}, dimension_result_id={dimension_result_id}, evaluation_status=pending",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                except Exception as e:
                    self._log(level='ERROR', content=f"创建TestResultDimension记录失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
                    local_db_session.rollback()
                finally:
                    local_db_session.close()
        
        endpoint_groups = {}
        
        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
            endpoints = dim_data.get('api_endpoints', [])
            api_url = dim_data.get('api_url')
            task_type_code = dim_data.get('task_type_code')
            
            if not endpoints or not isinstance(endpoints, list):
                if api_url:
                    endpoint_url = api_url
                    group_key = (endpoint_url, task_type_code)
                    if group_key not in endpoint_groups:
                        endpoint_groups[group_key] = []
                    
                    dimension_result_id = dimension_result_map.get(dim_id)
                    if dimension_result_id:
                        endpoint_groups[group_key].append((dim_data, dimension_result_id))
                continue
            
            endpoint_item = endpoints[0]
            endpoint_url = endpoint_item.get('url') or endpoint_item.get('endpoint')
            if not endpoint_url and api_url:
                endpoint_url = api_url
            
            if not endpoint_url:
                continue
            
            group_key = (endpoint_url, task_type_code)
            if group_key not in endpoint_groups:
                endpoint_groups[group_key] = []
            
            dimension_result_id = dimension_result_map.get(dim_id)
            if dimension_result_id:
                endpoint_groups[group_key].append((dim_data, dimension_result_id))
        
        if not endpoint_groups:
            for dim_data in dimension_data_list:
                dim_id = dim_data['id']
                api_url = dim_data.get('api_url')
                task_type_code = dim_data.get('task_type_code')
                if api_url:
                    endpoint_url = api_url
                    group_key = (endpoint_url, task_type_code)
                    if group_key not in endpoint_groups:
                        endpoint_groups[group_key] = []
                    
                    dimension_result_id = dimension_result_map.get(dim_id)
                    if dimension_result_id:
                        endpoint_groups[group_key].append((dim_data, dimension_result_id))
        
        # 异步提交评估任务，不等待完成
        for group_key, group_items in endpoint_groups.items():
            endpoint_url, task_type_code = group_key
            representative_dim_data = group_items[0][0]
            group_dim_names = [item[0]['name'] for item in group_items]
            group_dim_ids = [item[0]['id'] for item in group_items]
            
            self._log(
                level='DEBUG',
                content=f"[分组详情] group_key={group_key}, 维度IDs={group_dim_ids}, 维度名称={group_dim_names}, 代表维度ID={representative_dim_data['id']}, 代表维度name={representative_dim_data['name']}, api_settings={representative_dim_data.get('api_settings')}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            
            worker = self._get_or_create_worker(endpoint_url, representative_dim_data)
            
            self._log(
                level='DEBUG',
                content=f"提交端点评估任务: endpoint={endpoint_url}, 任务类型={task_type_code}, 维度数量={len(group_items)}, 维度列表={group_dim_names}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            
            task_data = {
                'task_id': task_id,
                'result_id': result_id,
                'test_case_id': test_case_id,
                'algorithm_result': algorithm_result,
                'representative_dim_data': representative_dim_data,
                'group_items': group_items,
                'algorithm_type': algorithm_type,
                'test_type': test_type
            }
            
            output_field_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)
            algo_results = {}
            if isinstance(algorithm_result, dict):
                for key in output_field_keys:
                    val = algorithm_result.get(key)
                    self._log(
                        level='DEBUG',
                        content=f"[task_data algo_results] key={key}, value={val}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    algo_results[key] = val if val is not None else ''
            
            for key, value in algo_results.items():
                if key not in task_data:
                    task_data[key] = value
            
            for ref_field, ref_value in ref_texts.items():
                task_data[ref_field] = ref_value
            
            with self.api_client.global_lock:
                if self.api_client.thread_pool is None or self.api_client.thread_pool._shutdown:
                    self.api_client.init_thread_pool()
            
            try:
                self.api_client.thread_pool.submit(
                    self._submit_to_endpoint_worker,
                    task_data, worker
                )
            except Exception as e:
                self._log(level='ERROR', content=f"提交评估任务失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
        
        self._log(
            level='INFO',
            content=f"评估任务已异步提交，开始执行下一个测试用例",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        return True
    
    def _submit_to_endpoint_worker(self, task_data, worker):
        worker.task_queue.put(task_data)
    
    def _post_evaluate_updates(self, task_id, test_case_id=None):
        """
        评估后的状态更新
        
        更新用例的status字段和统计信息，任务状态由执行引擎统一更新
        """
        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                from backend.utils.execution_engine import execution_engine
                
                # 更新 TaskCase 的 evaluation_status 和 status
                # 当没有评估维度时，评估流程不会真正执行，需要在这里更新状态
                task_cases_query = local_db_session.query(TaskCase).filter_by(task_id=task_id)
                if test_case_id:
                    task_cases_query = task_cases_query.filter_by(test_case_id=test_case_id)
                
                task_cases = task_cases_query.all()
                for tc in task_cases:
                    if tc.evaluation_status in ['queued', 'pending'] and tc.execution_status in ['completed', 'failed']:
                        tc.evaluation_status = 'completed'
                        if tc.status == 'pending':
                            tc.status = tc.execution_status
                
                local_db_session.commit()
                
                # 检查任务的所有用例是否都已处理完成
                total_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).count()
                
                # 统计已处理完成的用例数（status为completed或failed）
                processed_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.status.in_(['completed', 'failed'])
                ).count()
                
                # 统计失败的用例数
                failed_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.status == 'failed'
                ).count()
                
                # 统计已完成的用例数
                completed_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.status == 'completed'
                ).count()
                
                # 更新任务的统计信息
                task = local_db_session.query(Task).get(task_id)
                if task:
                    task.completed_cases = completed_cases
                    task.failed_cases = failed_cases
                    
                    if task.status == 'evaluating':
                        task.status = 'completed'
                    
                    local_db_session.commit()
                    
                    self._log(
                        level='DEBUG',
                        content=f"评估后更新任务 {task_id} 统计信息: completed={completed_cases}, failed={failed_cases}, total={total_cases}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    
                    # 发送进度更新
                    execution_engine._emit_progress(task, force=True)
                    
                    # 注意：任务状态（task.status）由执行引擎在评估完成后统一更新
                    # 评估服务只更新统计信息，不更新任务状态
            except Exception as e:
                self._log(level='ERROR', content=f"评估后更新任务状态失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
            finally:
                local_db_session.close()
    
    def shutdown(self):
        self._log(level='info', content='开始关闭评估服务', category='system')
        
        self.stop_event.set()
        
        with self.endpoint_workers_lock:
            for endpoint_url, worker in self.endpoint_workers.items():
                worker.stop()
            self.endpoint_workers.clear()
        
        if self.api_client.thread_pool and not self.api_client.thread_pool._shutdown:
            try:
                self.api_client.thread_pool.shutdown(wait=True)
                self._log(level='info', content='评估服务线程池已关闭', category='system')
            except Exception as e:
                self._log(level='ERROR', content=f'关闭线程池失败: {str(e)}', category='system')
        
        self._log(level='info', content='评估服务已关闭', category='system')


evaluation_service = EvaluationService()
