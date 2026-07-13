import time
import traceback
import queue
import threading
import json
from datetime import datetime, timezone, timedelta
from threading import Lock
from backend.models.models import Dimension, TestResultDimension, TestCase, TaskCase, Task
from backend.models.database import db
from backend.services.evaluation.evaluation_api_client import evaluationApiClient
from backend.services.evaluation.evaluation_result_processor import EvaluationResultProcessor
from backend.services.evaluation.endpoint_worker import EndpointWorker
from backend.services.evaluation.evaluation_mixin import EvaluationLoggerMixin, get_endpoint_url, get_endpoint_field
from backend.utils.algorithm.field_mapper import get_field_mapper

app = None

def get_app():
    global app
    if app is None:
        from backend.app import app
    return app


class EvaluationService(EvaluationLoggerMixin):
    def __init__(self):
        self.current_test_case_id = None

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

    def _get_timeout_from_dim_config(self, dim_data, default_timeout=30):
        dim_type = dim_data.get('dimension_type', 'main')
        api_settings = dim_data.get('api_settings', {})

        # llm_judge dimensions need longer timeout (LLM inference is slower)
        if dim_type == 'llm_judge':
            return api_settings.get('timeout', 120)

        timeout = api_settings.get('timeout')
        if timeout:
            return timeout

        endpoints = dim_data.get('api_endpoints', [])
        if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
            endpoint_item = endpoints[0]
            timeout = get_endpoint_field(endpoint_item, 'max_timeout', 'maxTimeout')
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
                # 从端点配置获取 max_process（并发消费线程数）
                endpoints = dim_data.get('api_endpoints', [])
                max_concurrent = 1
                if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
                    endpoint_item = endpoints[0]
                    max_concurrent = get_endpoint_field(endpoint_item, 'max_process', 'maxProcess', 1)
                # 也从 api_client.endpoint_configs 获取
                if endpoint_url in self.api_client.endpoint_configs:
                    max_concurrent = self.api_client.endpoint_configs[endpoint_url]
                worker = EndpointWorker(endpoint_url, self, max_timeout=max_timeout, max_concurrent=max_concurrent)
                self.endpoint_workers[endpoint_url] = worker
                worker.start()
                self._log(
                    level='INFO',
                    content=f"为端点创建新Worker: {endpoint_url}, 超时: {max_timeout}秒, 并发: {max_concurrent}"
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
                                    endpoint_url = get_endpoint_url(endpoint_item)
                                    if endpoint_url:
                                        timeout = get_endpoint_field(endpoint_item, 'max_timeout', 'maxTimeout', 30)
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

    def _extract_round_eval_data(self, algorithm_result, round_number):
        """从多轮 algorithm_result 中提取单轮评估数据

        当 round_number 不为 None 时，从 rounds[round_number] 提取该轮的扁平字段
        （asr_text 等），供评估端点直接使用。

        Args:
            algorithm_result: 完整的 algorithm_result（含 rounds[] 结构）
            round_number: 0-indexed 轮次编号

        Returns:
            dict: 单轮扁平数据，若轮次不存在返回 None
        """
        # 循环反序列化，处理可能的双重序列化旧数据
        while isinstance(algorithm_result, str):
            try:
                algorithm_result = json.loads(algorithm_result)
            except (json.JSONDecodeError, TypeError):
                return None

        if not isinstance(algorithm_result, dict):
            return None

        rounds = algorithm_result.get('rounds', [])
        if not rounds or round_number >= len(rounds):
            return None

        round_data = rounds[round_number]
        output = round_data.get('output', {})

        # 构建扁平结构，把 rounds[i].output 的字段提升到顶层
        flat = dict(output) if isinstance(output, dict) else {}
        if 'latency' in round_data:
            flat['latency'] = round_data['latency']

        return flat

    def evaluate_case(self, task_id, result_id, test_case_id, algorithm_result, **kwargs):
        field_mapper = get_field_mapper()
        test_type = kwargs.get('test_type', 'api')
        round_number = kwargs.get('round_number')  # 多轮评估: 轮次编号 (None=整体评估, 0-indexed)

        # 多轮场景：round_number 不为 None 时，从 algorithm_result.rounds[i] 提取单轮扁平数据
        if round_number is not None:
            extracted = self._extract_round_eval_data(algorithm_result, round_number)
            if extracted is None:
                self._log(
                    level='WARNING',
                    content=f"轮次 {round_number} 数据不存在，跳过评估",
                    task_id=task_id, test_case_id=test_case_id
                )
                return False
            algorithm_result = extracted

        self._log(
            level='DEBUG',
            content=f"[DEBUG evaluate_case] 传入参数: task_id={task_id}, result_id={result_id}, result_id_type={type(result_id)}, test_case_id={test_case_id}, test_type={test_type}, round_number={round_number}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='INFO',
            content=f"用例评估请求: TaskID={task_id}, TestCaseID={test_case_id}, ResultID={result_id}, TestType={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 加载测试用例和参考文本
        case_data = self._load_test_case_and_refs(
            test_case_id, field_mapper, kwargs, task_id
        )
        if case_data is None:
            return False

        test_case = case_data['test_case']
        algorithm_type = case_data['algorithm_type']
        ref_texts = case_data['ref_texts']
        dimensions_config = case_data['dimensions_config']

        # 提取维度ID
        dimension_ids = self._extract_dimension_ids(dimensions_config)

        unique_dimension_ids = list(set(dimension_ids))

        self._log(
            level='DEBUG',
            content=f"用例 {test_case.name} 的维度配置: {json.dumps(dimensions_config, ensure_ascii=False)}, 提取的维度IDs: {dimension_ids}, 去重后: {unique_dimension_ids}",
            task_id=task_id
        )

        if not unique_dimension_ids:
            self._log(level='WARNING', content=f"用例 {test_case.name} 没有配置任何维度，跳过评估", task_id=task_id, test_case_id=test_case_id)
            self.result_processor.mark_test_result_completed(result_id)
            self._post_evaluate_updates(task_id, test_case_id)
            return False

        # 加载维度数据
        dimension_data_list = self._load_dimension_data(
            unique_dimension_ids, task_id, test_case_id, test_case
        )
        if not dimension_data_list:
            self.result_processor.mark_test_result_completed(result_id)
            self._post_evaluate_updates(task_id, test_case_id)
            return False

        self._log(level='INFO', content=f"开始评估 {len(dimension_data_list)} 个维度，分发到端点队列", task_id=task_id, test_case_id=test_case_id)

        # 标记评估状态为 queued
        self._mark_evaluation_queued(task_id, test_case_id)

        # 创建维度结果记录
        dimension_result_map = self._create_dimension_results(
            dimension_data_list, result_id, task_id, test_case_id, algorithm_type, kwargs
        )

        # 分发评估任务
        self._dispatch_evaluation_tasks(
            dimension_data_list, dimension_result_map, result_id, task_id, test_case_id,
            algorithm_result, algorithm_type, test_type, round_number, field_mapper, ref_texts
        )

        self._log(
            level='INFO',
            content=f"评估任务已异步提交，开始执行下一个测试用例",
            task_id=task_id,
            test_case_id=test_case_id
        )

        return True

    def _load_test_case_and_refs(self, test_case_id, field_mapper, kwargs, task_id):
        """加载测试用例、算法类型、参考文本和维度配置"""
        current_app = get_app()
        with current_app.app_context():
            local_db_session = db.session()
            try:
                test_case = local_db_session.query(TestCase).get(test_case_id)
                if not test_case:
                    self._log(level='ERROR', content=f"找不到测试用例 {test_case_id}", task_id=task_id)
                    return None

                algorithm_type = test_case.algorithm_type if test_case.algorithm_type else kwargs.get('algorithm_type', 'translation')
                eval_input_fields = field_mapper.get_evaluation_input_fields(algorithm_type)

                ref_texts = self._extract_ref_texts(eval_input_fields, kwargs, task_id, test_case_id)

                self._log(
                    level='DEBUG',
                    content=f"[ref_texts] final ref_texts={ref_texts}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )

                test_case_config = test_case.config or {}
                # 优先从 rounds[].evaluation.dimensions 读取（标准存储位置）
                # 兼容旧的顶层 dimensions 字段（audio_controller 旧版本写入）
                dimensions_config = []
                rounds = test_case_config.get('rounds', [])
                if rounds and isinstance(rounds, list):
                    for round_item in rounds:
                        if isinstance(round_item, dict):
                            evaluation = round_item.get('evaluation', {})
                            if isinstance(evaluation, dict):
                                round_dims = evaluation.get('dimensions', [])
                                if round_dims:
                                    dimensions_config = round_dims
                                    break
                if not dimensions_config:
                    dimensions_config = test_case_config.get('dimensions', [])

                return {
                    'test_case': test_case,
                    'algorithm_type': algorithm_type,
                    'ref_texts': ref_texts,
                    'dimensions_config': dimensions_config,
                }
            finally:
                local_db_session.close()

    def _extract_ref_texts(self, eval_input_fields, kwargs, task_id, test_case_id):
        """从 kwargs 中提取参考文本"""
        ref_texts = {}
        ref_text_keys = {'rttm_ref', 'stm_ref', 'asr_ref', 'asr_rerference_text'}

        for field_key, field_info in eval_input_fields.items():
            field_type = field_info.get('type', 'text')
            field_value = kwargs.get(field_key)

            self._log(
                level='DEBUG',
                content=f"[kwargs field_key] field_key={field_key}, field_value={field_value}, field_value_type={type(field_value)}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            if not field_value:
                continue

            if field_key in ref_text_keys and isinstance(field_value, dict) and 'text' in field_value:
                ref_texts[field_key] = {
                    'text': field_value.get('text', ''),
                    'json': field_value.get('json', field_value.get('segments', []))
                }
            else:
                ref_texts[field_key] = {
                    'value': field_value,
                    'field_type': field_type
                }

        return ref_texts

    def _extract_dimension_ids(self, dimensions_config):
        """从维度配置中提取维度ID列表"""
        dimension_ids = []
        for item in dimensions_config:
            if isinstance(item, dict):
                dimension_id = item.get('id')
                if dimension_id:
                    dimension_ids.append(dimension_id)
            else:
                dimension_ids.append(item)
        return dimension_ids

    def _load_dimension_data(self, unique_dimension_ids, task_id, test_case_id, test_case):
        """从数据库加载维度数据并构建 dim_dict 列表"""
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
                    return []

                # 预加载所有维度的 output 参数，避免 N+1 查询
                dim_ids = [dim.id for dim in dimensions]
                output_param_map = {}
                if dim_ids:
                    from backend.models.algorithm_models import EvaluationDimensionParam
                    output_params = EvaluationDimensionParam.query.filter(
                        EvaluationDimensionParam.dimension_id.in_(dim_ids),
                        EvaluationDimensionParam.param_direction == 'output',
                        EvaluationDimensionParam.deleted == False
                    ).all()
                    for p in output_params:
                        output_param_map.setdefault(p.dimension_id, []).append({
                            'param_code': p.param_code,
                            'field_path': p.field_path,
                            'field_type': p.field_type,
                            'agg_role': p.agg_role,
                            'output_role': p.output_role,
                            'visible_in_report': p.visible_in_report if p.visible_in_report is not None else True
                        })

                dimension_data_list = []
                for dim in dimensions:
                    dim_outputs = output_param_map.get(dim.id, [])
                    output_field_path = dim_outputs[0]['field_path'] if dim_outputs else None

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
                        'task_type_code': getattr(dim, 'task_type_code', None),
                        'output_field_path': output_field_path,
                        'output_params': dim_outputs
                    }

                    # 子维度继承父维度的API配置
                    if getattr(dim, 'dimension_type', 'main') == 'sub' and not dim_dict.get('api_endpoints') and not dim_dict.get('api_url'):
                        parent_dim = getattr(dim, 'parent_dimension', None)
                        if parent_dim:
                            for k in ['api_endpoints', 'api_url', 'api_settings', 'task_type_code']:
                                if not dim_dict.get(k):
                                    dim_dict[k] = getattr(parent_dim, k, None)

                    dimension_data_list.append(dim_dict)

                self._log(
                    level='DEBUG',
                    content=f"[维度数据] 用例 {test_case.name} 加载的维度列表: {[{ 'id': d['id'], 'name': d['name'], 'task_type_code': d.get('task_type_code'), 'api_url': d.get('api_url'), 'api_settings_keys': list(d.get('api_settings', {}).keys()) if d.get('api_settings') else [] } for d in dimension_data_list]}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )

                return dimension_data_list
            finally:
                local_db_session.close()

    def _mark_evaluation_queued(self, task_id, test_case_id):
        """标记评估状态为 queued"""
        current_app = get_app()
        with current_app.app_context():
            update_session = db.session()
            try:
                tc_rel = update_session.query(TaskCase).filter_by(task_id=task_id, test_case_id=test_case_id).first()
                if tc_rel and tc_rel.evaluation_status not in ['running', 'stopped', 'queued']:
                    tc_rel.evaluation_status = 'queued'
                    update_session.commit()
            except Exception as e:
                self._log(level='WARNING', content=f"更新评估状态失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
                update_session.rollback()
            finally:
                update_session.close()

    def _create_dimension_results(self, dimension_data_list, result_id, task_id, test_case_id, algorithm_type, kwargs):
        """为每个维度创建 TestResultDimension 记录"""
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

                    # 从 kwargs 获取 round_number (多轮评估场景)
                    round_number = kwargs.get('round_number')

                    test_result_dimension = TestResultDimension(
                        test_result_id=result_id,
                        dimension_id=dim_id,
                        algorithm_type=algo_type,
                        round_number=round_number,
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

        return dimension_result_map

    def _dispatch_evaluation_tasks(self, dimension_data_list, dimension_result_map, result_id, task_id,
                                    test_case_id, algorithm_result, algorithm_type, test_type,
                                    round_number, field_mapper, ref_texts):
        """将维度按端点分组并异步提交评估任务"""
        endpoint_groups = {}
        no_endpoint_groups = []  # 没有配置评估端点的维度，需标记失败避免任务卡死

        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
            dim_type = dim_data.get('dimension_type', 'main')
            endpoints = dim_data.get('api_endpoints', [])
            api_url = dim_data.get('api_url')
            task_type_code = dim_data.get('task_type_code')

            # 统一提取 endpoint_url：优先从 endpoints[0] 获取，兜底用 api_url
            endpoint_url = None
            if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
                endpoint_url = get_endpoint_url(endpoints[0])
            if not endpoint_url:
                endpoint_url = api_url

            if not endpoint_url:
                self._log(
                    level='ERROR',
                    content=f"维度 {dim_data.get('name')} (id={dim_id}) 没有配置评估端点(api_url=None, api_endpoints为空)，无法提交评估任务",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                dimension_result_id = dimension_result_map.get(dim_id)
                if dimension_result_id:
                    no_endpoint_groups.append((dim_data, dimension_result_id))
                continue

            group_key = (endpoint_url, task_type_code)
            if group_key not in endpoint_groups:
                endpoint_groups[group_key] = []

            dimension_result_id = dimension_result_map.get(dim_id)
            if dimension_result_id:
                endpoint_groups[group_key].append((dim_data, dimension_result_id))

        # 处理无端点的维度：标记为失败并更新用例/任务状态，避免任务卡死在评估中
        if no_endpoint_groups:
            self._log(
                level='ERROR',
                content=f"共 {len(no_endpoint_groups)} 个维度因缺少评估端点而失败: {[item[0]['name'] for item in no_endpoint_groups]}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            self.result_processor.update_all_dimensions_in_group_failed(
                group_items=no_endpoint_groups,
                error_message='维度未配置评估端点(api_url为空)，无法执行评估',
                task_id=task_id,
                test_case_id=test_case_id
            )
            # 更新任务统计并唤醒等待线程，让执行引擎继续推进
            self._post_evaluate_updates(task_id, test_case_id)

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

            task_data = self._build_task_data(
                task_id, result_id, test_case_id, algorithm_result,
                representative_dim_data, group_items, algorithm_type, test_type,
                round_number, field_mapper, ref_texts
            )

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

    def _build_task_data(self, task_id, result_id, test_case_id, algorithm_result,
                         representative_dim_data, group_items, algorithm_type, test_type,
                         round_number, field_mapper, ref_texts):
        """构建提交给端点Worker的任务数据"""
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

        # 透传 round_number 到端点Worker (多轮评估场景)
        if round_number is not None:
            task_data['round_number'] = round_number

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

        return task_data

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
                from backend.services.execution.execution_engine import execution_engine

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

                    # 当任务处于评估过渡态时，检查是否所有用例都已完成评估
                    if task.status == 'evaluating':
                        # 检查是否还有未完成评估的用例
                        pending_eval_count = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                        ).count()
                        if pending_eval_count == 0:
                            # 所有用例评估完成，更新任务最终状态
                            task.status = 'failed' if failed_cases > 0 else 'completed'
                            if task.status in ['completed', 'failed']:
                                task.completed_at = datetime.now(timezone(timedelta(hours=8)))

                    local_db_session.commit()

                    self._log(
                        level='DEBUG',
                        content=f"评估后更新任务 {task_id} 统计信息: completed={completed_cases}, failed={failed_cases}, total={total_cases}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )

                    # 发送进度更新
                    execution_engine._emit_progress(task, force=True)

                    # 唤醒等待线程：通知执行引擎某个用例的评估已完成
                    execution_engine.notify_case_completed(task_id)

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
