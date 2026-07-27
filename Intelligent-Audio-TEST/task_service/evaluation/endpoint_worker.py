import time
import traceback
import queue
import threading
import json
from shared.models.models import TaskCase
from shared.models.database import db
from task_service.evaluation.evaluation_mixin import EvaluationLoggerMixin
from task_service.algorithm.field_mapper import get_field_mapper


# 延迟导入app，避免循环导入和app未初始化问题
app = None

def get_app():
    """获取应用实例，延迟导入"""
    global app
    if app is None:
        # TODO: 跨服务调用 - 不应直接 import app 实例，应使用 current_app
        from flask import current_app as app
    return app


class EndpointWorker(EvaluationLoggerMixin):
    """
    端点Worker，负责消费端点任务队列并执行评估
    """

    def __init__(self, endpoint_url, eval_service, max_timeout=30, max_concurrent=1):
        self.endpoint_url = endpoint_url
        self.eval_service = eval_service
        self.max_timeout = max_timeout
        self.max_concurrent = max_concurrent  # 最大并发消费线程数
        self.task_queue = queue.Queue()
        self.worker_threads = []  # 多个消费线程
        self.stop_event = threading.Event()
        self.completion_events = {}  # task_id -> threading.Event for completion signaling
        self.completion_events_lock = threading.Lock()
        self._log(level='INFO', content=f"端点Worker已创建: {endpoint_url}, 超时时间: {max_timeout}秒, 最大并发: {max_concurrent}")

    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        """重写以附加 endpoint 信息"""
        kwargs.setdefault('endpoint', self.endpoint_url)
        super()._log(level, content, task_id, test_case_id, api_id, **kwargs)

    def start(self):
        if not self.worker_threads or not any(t.is_alive() for t in self.worker_threads):
            self.stop_event.clear()
            self.worker_threads = []
            for i in range(self.max_concurrent):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"EndpointWorker-{self.endpoint_url[:30]}-{i}",
                    daemon=True
                )
                t.start()
                self.worker_threads.append(t)
            self._log(level='INFO', content=f"端点Worker已启动: {self.endpoint_url}, 消费线程数: {self.max_concurrent}")

    def stop(self):
        self.stop_event.set()
        for t in self.worker_threads:
            if t.is_alive():
                t.join(timeout=2)
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
                        # 从 queued 改为 running，反映真实执行状态
                        local_db_session = db.session()
                        try:
                            tc = local_db_session.query(TaskCase).filter_by(
                                task_id=task_id, test_case_id=task_data.get('test_case_id')
                            ).first()
                            if tc and tc.evaluation_status == 'queued':
                                tc.evaluation_status = 'running'
                                local_db_session.commit()
                        except Exception as e:
                            local_db_session.rollback()
                            self._log(level='WARNING', content=f"更新评估状态为running失败: {str(e)}", task_id=task_id)
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
        # 按维度获取映射字段（多对一映射时不同维度可能映射不同 source）
        dim_id = representative_dim_data.get('id')
        output_field_keys = field_mapper.get_dimension_mapped_device_output_field_keys(algorithm_type, dim_id) \
            if dim_id else field_mapper.get_mapped_device_output_field_keys(algorithm_type)

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
            # 多轮结构：output 字段在 rounds[].output 里（key 是 target_param 名）
            rounds_data = algorithm_result.get('rounds', [])
            first_output = rounds_data[0].get('output', {}) if rounds_data and isinstance(rounds_data[0], dict) else {}
            for key in output_field_keys:
                # 按维度优先取 dim 专属 key，回退到通用 key
                dim_key = f'{key}__dim_{dim_id}' if dim_id else None
                val = None
                if dim_key and first_output:
                    val = first_output.get(dim_key)
                if val is None:
                    val = algorithm_result.get(key)
                if val is None and first_output:
                    val = first_output.get(key)
                self._log(
                    level='DEBUG',
                    content=f"[algo_results] key={key}, dim_key={dim_key}, value={val}, value_type={type(val)}",
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

        # 从维度 input_params 加载维度级配置（model/prompt 等）
        for inp in representative_dim_data.get('input_params', []):
            param_code = inp.get('param_code')
            default_val = inp.get('default_value')
            if param_code and default_val is not None and param_code not in context:
                # default_value 是 JSON 格式的字符串，解析后放入 context
                import json as _json
                try:
                    context[param_code] = _json.loads(default_val)
                except (ValueError, TypeError):
                    context[param_code] = default_val

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

        # 从维度 input_params 提取 field_type='audio' 的字段名集合
        audio_field_names = {
            inp.get('param_code') for inp in representative_dim_data.get('input_params', [])
            if inp.get('field_type') == 'audio' and inp.get('param_code')
        }
        self._log(
            level='DEBUG',
            content=f"[audio_field_names] input_params={representative_dim_data.get('input_params', [])}, audio_field_names={audio_field_names}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        dim_info = {
            'dimension_type': representative_dim_data.get('dimension_type', 'main'),
            'parent_dimension_id': representative_dim_data.get('parent_dimension_id'),
            'task_type_code': representative_dim_data.get('task_type_code')
        }

        try:
            # 标记为calculating：payload已构建完成，即将提交给eval_server计算
            local_db_session = db.session()
            try:
                tc = local_db_session.query(TaskCase).filter_by(
                    task_id=task_id, test_case_id=test_case_id
                ).first()
                if tc and tc.evaluation_status == 'running':
                    tc.evaluation_status = 'calculating'
                    local_db_session.commit()
            except Exception as e:
                local_db_session.rollback()
                self._log(level='WARNING', content=f"更新评估状态为calculating失败: {str(e)}", task_id=task_id)

            selected_url, resp_data = self.eval_service.api_client.make_api_request_with_fallback(
                endpoints=endpoints,
                method=method,
                headers=headers,
                payload=payload,
                task_id=task_id,
                dim_names=dim_names,
                api_url=representative_dim_data.get('api_url'),
                test_case_id=test_case_id,
                dim_info=dim_info,
                audio_field_names=audio_field_names
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
