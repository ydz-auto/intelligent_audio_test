import time
import traceback
import queue
import threading
import json
import logging
# P1.4: TaskCase 改为通过 gRPC 调 task_service
from evaluation_service.infrastructure.acl import task_acl_repository
from evaluation_service.infrastructure.acl import algorithm_acl_repository
from evaluation_service.infrastructure.evaluation_mixin import EvaluationLoggerMixin
from shared.models.common_enums import FieldType, RedisKeyPrefix
from shared.utils.status_constants import EvaluationStatus
from shared.utils.config_manager import config_manager

logger = logging.getLogger(__name__)


class EndpointWorker(EvaluationLoggerMixin):
    """
    端点Worker，负责消费端点任务队列并执行评估

    队列持久化改造（Phase 3.1）：
    - 优先使用 Redis List 作为持久化队列，key 格式为 eval:queue:{endpoint_url}
    - Redis 不可用时降级为内存 queue.Queue
    """

    def __init__(self, endpoint_url, eval_service, max_timeout=30, max_concurrent=10):
        self.endpoint_url = endpoint_url
        self.eval_service = eval_service
        self.max_timeout = max_timeout
        self.max_concurrent = max_concurrent  # 最大并发消费线程数

        # Redis 持久化队列 key
        self._redis_queue_key = f"{RedisKeyPrefix.EVAL_QUEUE.value}:{endpoint_url}"
        # brpop 超时时间从配置读取
        self._brpop_timeout = config_manager.get_value('evaluation_service', 'redis_queue_brpop_timeout', 1)

        # 获取 Redis 客户端，失败时降级为内存队列
        self._redis_client = self._get_redis_client()
        self._use_redis_queue = self._redis_client is not None

        # 内存队列作为降级方案
        self.task_queue = queue.Queue()

        self.worker_threads = []  # 多个消费线程
        self.stop_event = threading.Event()
        self.completion_events = {}  # task_id -> threading.Event for completion signaling
        self.completion_events_lock = threading.Lock()
        self._log(level='INFO', content=f"端点Worker已创建: {endpoint_url}, 超时时间: {max_timeout}秒, 最大并发: {max_concurrent}, 队列模式: {'Redis' if self._use_redis_queue else '内存'}")

    @staticmethod
    def _get_redis_client():
        """获取 Redis 客户端，不可用时返回 None 以触发降级"""
        try:
            from shared.utils.redis_pubsub import RedisPubSub
            client = RedisPubSub().redis_client
            client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis 不可用，端点队列降级为内存模式: {e}")
            return None

    def put_task(self, task_data):
        """将任务放入队列（Redis 优先，降级用内存队列）"""
        if self._use_redis_queue:
            try:
                self._redis_client.lpush(self._redis_queue_key, json.dumps(task_data, ensure_ascii=False, default=str))
                return
            except Exception as e:
                self._log(level='WARNING', content=f"Redis 队列写入失败，降级为内存队列: {e}")
                self._use_redis_queue = False
        self.task_queue.put(task_data)

    def get_task(self, timeout=1.0):
        """从队列获取任务（Redis 优先，降级用内存队列）

        Returns:
            dict: 任务数据

        Raises:
            queue.Empty: 队列为空或超时
        """
        if self._use_redis_queue:
            try:
                result = self._redis_client.brpop(self._redis_queue_key, timeout=int(self._brpop_timeout))
                if result is None:
                    raise queue.Empty
                # brpop 返回 (key, value) 元组
                _, task_json = result
                if isinstance(task_json, bytes):
                    task_json = task_json.decode('utf-8')
                return json.loads(task_json)
            except queue.Empty:
                raise
            except Exception as e:
                self._log(level='WARNING', content=f"Redis 队列读取失败，降级为内存队列: {e}")
                self._use_redis_queue = False
        return self.task_queue.get(timeout=timeout)

    def task_done(self):
        """标记任务完成（内存队列需要 task_done，Redis 无操作）"""
        if not self._use_redis_queue:
            self.task_queue.task_done()

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
        while not self.stop_event.is_set():
            try:
                task_data = self.get_task(timeout=1.0)
                task_id = task_data.get('task_id')

                try:
                    self._log(
                        level='INFO',
                        content=f"端点Worker开始处理任务: TaskID={task_id}, ResultID={task_data['result_id']}, TestCaseID={task_data.get('test_case_id')}",
                        task_id=task_id,
                        test_case_id=task_data.get('test_case_id')
                    )
                    # 从 queued 改为 running，反映真实执行状态（P1.4: 通过 gRPC）
                    try:
                        tc_rels = task_acl_repository.get_task_case_by_ids(
                            task_id=task_id, case_ids=[str(task_data.get('test_case_id'))]
                        )
                        if tc_rels and tc_rels[0].evaluation_status == EvaluationStatus.QUEUED:
                            task_acl_repository.update_task_case_status(
                                task_id=task_id,
                                case_id=str(task_data.get('test_case_id')),
                                evaluation_status=EvaluationStatus.RUNNING,
                            )
                    except Exception as e:
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
                    self.task_done()

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
        field_defs = algorithm_acl_repository.get_field_mappings(algorithm_type)
        # 按维度获取映射字段（多对一映射时不同维度可能映射不同 source）
        dim_id = representative_dim_data.get('id')
        output_field_keys = field_defs.get_mapped_device_output_field_keys(algorithm_type)

        eval_input_fields = field_defs.get_evaluation_input_fields(algorithm_type)

        # 1. 构建评估上下文（algo_results、context、input_params）
        payload = self._build_evaluation_context(
            task_id, test_case_id, algorithm_result, representative_dim_data,
            algorithm_type, output_field_keys, dim_id, eval_input_fields, kwargs
        )

        # 2. 准备API配置（endpoints, method, headers, dim_info, audio_field_names）
        endpoints, method, headers, dim_info, audio_field_names = self._prepare_api_config(
            representative_dim_data, group_items
        )

        dim_names = [item[0]['name'] for item in group_items]

        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] 接收到的 group_items 维度IDs: {[item[0]['id'] for item in group_items]}, 维度Names: {[item[0]['name'] for item in group_items]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 3. 调用评估API
        resp_data = self._call_evaluation_api(
            task_id, test_case_id, endpoints, method, headers, payload,
            representative_dim_data, dim_names, dim_info, audio_field_names
        )

        # 4. 处理评估结果（成功/失败）
        self._process_evaluation_result(resp_data, group_items, task_id, test_case_id, result_id, payload, test_type)

    def _build_evaluation_context(self, task_id, test_case_id, algorithm_result, representative_dim_data,
                                  algorithm_type, output_field_keys, dim_id, eval_input_fields, kwargs):
        """构建评估上下文（包括algo_results、context、input_params），返回 payload"""
        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] 接收到的 representative_dim_data: id={representative_dim_data.get('id')}, name={representative_dim_data.get('name')}, task_type_code={representative_dim_data.get('task_type_code')}, api_settings_keys={list(representative_dim_data.get('api_settings', {}).keys()) if representative_dim_data.get('api_settings') else []}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] output_field_keys={output_field_keys}, algorithm_result_keys={list(algorithm_result.keys()) if isinstance(algorithm_result, dict) else 'not dict'}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        algo_results = {}
        if isinstance(algorithm_result, dict):
            # 多轮评估取值修正：单轮评估(round_number有值)取 rounds[round_number]，
            # 多轮整体(round_number=None)取 rounds[-1]，替代原来固定取 rounds[0]
            round_number = kwargs.get('round_number')
            rounds_data = algorithm_result.get('rounds', [])
            if rounds_data:
                idx = round_number if round_number is not None else -1
                if 0 <= idx < len(rounds_data) and isinstance(rounds_data[idx], dict):
                    ref_output = rounds_data[idx].get('output', {})
                else:
                    ref_output = {}
            else:
                ref_output = {}
            for key in output_field_keys:
                # 按维度优先取 dim 专属 key，回退到通用 key
                dim_key = f'{key}__dim_{dim_id}' if dim_id else None
                val = None
                if dim_key and ref_output:
                    val = ref_output.get(dim_key)
                if val is None:
                    val = algorithm_result.get(key)
                if val is None and ref_output:
                    val = ref_output.get(key)
                self._log(
                    level='DEBUG',
                    content=f"[algo_results] key={key}, dim_key={dim_key}, value={val}, value_type={type(val)}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                # 保留 None 而非转为空串，让维度级默认值有机会覆盖
                algo_results[key] = val

        context = {
            "algorithm_result": algorithm_result,
            "algorithm_type": algorithm_type
        }

        # rounds_list from kwargs takes priority over algo_results['rounds']
        # because _build_rounds_list already mapped the fields properly for evaluation
        rounds_list_override = kwargs.pop('rounds', None)

        for key, value in algo_results.items():
            if key not in context:
                context[key] = value

        for field_key, field_info in eval_input_fields.items():
            field_type = field_info.get('type', FieldType.TEXT.value)
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

        # Override rounds with the properly built rounds_list
        if rounds_list_override:
            context['rounds'] = rounds_list_override

        # 从维度 input_params 加载维度级配置（model/prompt 等）
        for inp in representative_dim_data.get('input_params', []):
            param_code = inp.get('param_code')
            default_val = inp.get('default_value')
            if param_code and default_val is not None:
                # 当 context 中没有该字段，或字段值为空字符串/None 时，用维度默认值覆盖
                existing_val = context.get(param_code)
                if existing_val is None or existing_val == '':
                    # default_value 是 JSON 格式的字符串，解析后放入 context
                    import json as _json
                    try:
                        context[param_code] = _json.loads(default_val)
                    except (ValueError, TypeError):
                        context[param_code] = default_val

        api_settings = representative_dim_data.get('api_settings', {})
        body_template = api_settings.get('body_template')

        self._log(
            level='DEBUG',
            content=f"[_execute_evaluation] body_template={body_template}, context_keys={list(context.keys())}, output_field_keys={output_field_keys}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        payload = self.eval_service.api_client.build_payload(body_template, context, task_id=task_id, test_case_id=test_case_id, algorithm_type=algorithm_type)

        # 从 group_items 提取各子维度的 task_type_code，组成 sub_tasks 注入 payload
        # eval_server 的 TurnTakingCalculator 按 sub_tasks 只算选中的子维度
        sub_tasks = []
        for item in group_items:
            dim_data = item[0]
            tc_code = dim_data.get('task_type_code')
            if tc_code and tc_code not in sub_tasks:
                sub_tasks.append(tc_code)
        if sub_tasks:
            if isinstance(payload, dict):
                payload['sub_tasks'] = sub_tasks
            self._log(
                level='DEBUG',
                content=f"[sub_tasks] 从 group_items 提取: {sub_tasks}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        return payload

    def _prepare_api_config(self, representative_dim_data, group_items):
        """准备API配置（endpoints, method, headers, dim_info, audio_field_names）

        3a: 从 group_items 提取各子维度的 task_type_code，组成 sub_tasks 注入 payload。
        dim_info.task_type_code 用主维度的 parent_task_type_code。
        """
        endpoints = representative_dim_data.get('api_endpoints', [])
        # 过滤掉 URL 为空的端点
        if isinstance(endpoints, list):
            endpoints = [ep for ep in endpoints if isinstance(ep, dict) and (ep.get('url') or ep.get('endpoint'))]
        if not endpoints and representative_dim_data.get('api_url'):
            endpoints = [{"url": representative_dim_data.get('api_url'), "name": "Master"}]

        api_settings = representative_dim_data.get('api_settings', {})
        method = api_settings.get('method', 'POST')
        headers = api_settings.get('headers', {})

        # 从维度 input_params 提取 field_type='audio' 的字段名集合
        audio_field_names = {
            inp.get('param_code') for inp in representative_dim_data.get('input_params', [])
            if inp.get('field_type') == 'audio' and inp.get('param_code')
        }
        self._log(
            level='DEBUG',
            content=f"[audio_field_names] input_params={representative_dim_data.get('input_params', [])}, audio_field_names={audio_field_names}",
        )

        # dim_info.task_type_code 用主维度的 turn_taking（parent_task_type_code），
        # 子维度各自的 task_type_code 已通过 sub_tasks 传递
        dim_info = {
            'dimension_type': representative_dim_data.get('dimension_type', 'main'),
            'parent_dimension_id': representative_dim_data.get('parent_dimension_id'),
            'task_type_code': representative_dim_data.get('parent_task_type_code') or representative_dim_data.get('task_type_code')
        }

        return endpoints, method, headers, dim_info, audio_field_names

    def _call_evaluation_api(self, task_id, test_case_id, endpoints, method, headers, payload,
                            representative_dim_data, dim_names, dim_info, audio_field_names):
        """调用评估API，返回 resp_data"""
        try:
            # 标记为calculating：payload已构建完成，即将提交给eval_server计算（P1.4: 通过 gRPC）
            try:
                tc_rels = task_acl_repository.get_task_case_by_ids(
                    task_id=task_id, case_ids=[str(test_case_id)]
                )
                if tc_rels and tc_rels[0].evaluation_status == EvaluationStatus.RUNNING:
                    task_acl_repository.update_task_case_status(
                        task_id=task_id,
                        case_id=str(test_case_id),
                        evaluation_status=EvaluationStatus.CALCULATING,
                    )
            except Exception as e:
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
            return resp_data
        except Exception as e:
            # 异常时返回包含 __error__ 的 dict，由 _process_evaluation_result 统一处理
            return {"__error__": f"评估维度组异常: {str(e)}\n{traceback.format_exc()}"}

    def _process_evaluation_result(self, resp_data, group_items, task_id, test_case_id, result_id, payload, test_type):
        """处理评估结果（成功/失败）"""
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
