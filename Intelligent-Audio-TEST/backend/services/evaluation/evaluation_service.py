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
                max_concurrent = self.api_client.default_max_concurrent
                if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
                    endpoint_item = endpoints[0]
                    max_concurrent = get_endpoint_field(endpoint_item, 'max_process', 'maxProcess', self.api_client.default_max_concurrent)
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
                                        max_concurrent = get_endpoint_field(endpoint_item, 'max_process', 'maxProcess', self.api_client.default_max_concurrent)
                                        if endpoint_url not in self.endpoint_workers:
                                            worker = EndpointWorker(endpoint_url, self, max_timeout=timeout, max_concurrent=max_concurrent)
                                            self.endpoint_workers[endpoint_url] = worker
                                            worker.start()
                                            self._log(
                                                level='INFO',
                                                content=f"预创建端点Worker: {endpoint_url}, 超时: {timeout}秒, 并发: {max_concurrent}"
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

    def _build_rounds_list(self, algorithm_result, reference_params_col,
                            field_mapper, algorithm_type, test_type, task_id, test_case_id,
                            algorithm_params_col=None):
        """从 algo_result.rounds 构建 [{reference, hypothesis, ...}, ...] 列表

        遍历 param_mappings，按 source 类型从每轮的 output（device/api）、
        按轮加载的 reference_params（reference）和按轮加载的 case 参数（case）取值，
        用 target_param 作为 key。
        """
        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        from backend.utils.algorithm.reference_params_generator import (
            get_reference_value as gen_reference_value,
        )

        rounds = algorithm_result.get('rounds', [])
        output_field_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)
        loader = CaseParameterExtractor._get_loader()
        mappings = loader.get_param_mapping(algorithm_type, 'evaluation')

        if not mappings:
            self._log(
                level='WARNING',
                content=f"[_build_rounds_list] 未找到 {algorithm_type} 的 evaluation param mappings",
                task_id=task_id, test_case_id=test_case_id
            )
            return []

        rounds_list = []
        for rd in rounds:
            output = rd.get('output', {})
            round_number = rd.get('round', 0)

            item = {}

            # 按轮加载 reference_params
            # algo_result.rounds[].round 是 0-indexed，reference_params_col 用 1-indexed
            round_ref_data = {}
            if reference_params_col:
                round_ref_data = CaseParameterExtractor._load_round_ref_file(
                    reference_params_col, round_number + 1
                )
            for m in mappings:
                source = m.get('source', 'api')
                source_param = m.get('source_param', '')
                target_param = m.get('target_param', '')
                value = None

                if source in ('device', 'api'):
                    # output 的 key 是 target_param 名（build_algorithm_result 已映射）
                    # 用 None 而非 '' 作为默认值，避免空串覆盖维度级默认值
                    raw_val = output.get(target_param)
                    if raw_val is not None and raw_val != '':
                        value = raw_val
                elif source == 'reference':
                    # 从按轮加载的 reference 取
                    ref_item = round_ref_data.get(source_param)
                    if ref_item and isinstance(ref_item, dict):
                        ref_type = None
                        for ref_def in loader.get_reference_params(algorithm_type):
                            if ref_def.get('code') == source_param:
                                ref_type = ref_def.get('type')
                                break
                        value = gen_reference_value(
                            ref_item, test_type, ref_type,
                            algorithm_type=algorithm_type,
                            case_config={}
                        )
                elif source == 'case':
                    # 按轮从独立列加载 case 参数
                    # algo_result.rounds[].round 是 0-indexed，algorithm_params_col 用 1-indexed
                    round_case_params = CaseParameterExtractor.get_round_algorithm_params(
                        algorithm_params_col, round_number + 1
                    ) if algorithm_params_col else {}
                    value = round_case_params.get(source_param)
                if value is not None:
                    item[target_param] = value

            rounds_list.append(item)

        return rounds_list

    def evaluate_case(self, task_id, result_id, test_case_id, algorithm_result, **kwargs):
        field_mapper = get_field_mapper()
        test_type = kwargs.get('test_type', 'api')
        round_number = kwargs.get('round_number')  # 多轮评估: 轮次编号 (None=整体评估, 0-indexed)
        reference_params_col = kwargs.pop('reference_params_col', None)

        # 从 TestCase 独立列读取 algorithm_params（按轮分组），用于 _build_rounds_list 的 case 参数映射
        algorithm_params_col = None
        current_app = get_app()
        with current_app.app_context():
            tc = db.session.query(TestCase).get(test_case_id)
            if tc:
                algorithm_params_col = getattr(tc, 'algorithm_params', None)

        # 多轮场景：统一构建 rounds 列表（单轮也走此路径，列表只有一个元素）
        if isinstance(algorithm_result, dict) and algorithm_result.get('rounds'):
            rounds_list = self._build_rounds_list(
                algorithm_result, reference_params_col,
                field_mapper, kwargs.get('algorithm_type', 'translation'),
                test_type, task_id, test_case_id,
                algorithm_params_col=algorithm_params_col
            )
            if round_number is not None:
                # 指定轮次：只取对应轮
                rounds_list = [rounds_list[round_number]] if round_number < len(rounds_list) else []
            if rounds_list:
                kwargs['rounds'] = rounds_list

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
        rounds_list = kwargs.get('rounds')
        # 提取单轮兼容的扁平字段（answer, correct_answer 等），传给 task_data
        flat_eval_fields = {}
        if isinstance(algorithm_result, dict) and algorithm_result.get('rounds'):
            for k, v in kwargs.items():
                if k not in ('test_type', 'round_number', 'algorithm_type',
                             'reference_params_col', 'rounds'):
                    flat_eval_fields[k] = v
        self._dispatch_evaluation_tasks(
            dimension_data_list, dimension_result_map, result_id, task_id, test_case_id,
            algorithm_result, algorithm_type, test_type, round_number, field_mapper, ref_texts,
            rounds_list, flat_eval_fields
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
                # 从 rounds[].evaluation.dimensions 读取单轮维度
                # 从 config.dimensions 读取多轮聚合维度
                # 合并两者，使评估服务同时处理单轮和多轮维度
                dimensions_config = []
                seen_dim_ids = set()
                rounds = test_case_config.get('rounds', [])
                if rounds and isinstance(rounds, list):
                    for round_item in rounds:
                        if isinstance(round_item, dict):
                            evaluation = round_item.get('evaluation', {})
                            if isinstance(evaluation, dict):
                                round_dims = evaluation.get('dimensions', [])
                                for d in round_dims:
                                    dim_id = d.get('id') if isinstance(d, dict) else d
                                    if dim_id and dim_id not in seen_dim_ids:
                                        seen_dim_ids.add(dim_id)
                                        dimensions_config.append(d)
                # 合并顶层 config.dimensions（多轮聚合维度）
                top_dims = test_case_config.get('dimensions', [])
                for d in top_dims:
                    dim_id = d.get('id') if isinstance(d, dict) else d
                    if dim_id and dim_id not in seen_dim_ids:
                        seen_dim_ids.add(dim_id)
                        dimensions_config.append(d)

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

                # 预加载所有维度（含父维度）的 output 和 input 参数，避免 N+1 查询
                dim_ids = [dim.id for dim in dimensions]
                # 收集 sub 维度的父维度 id，用于补查父维度的 input params（继承机制）
                parent_ids_to_load = set()
                for dim in dimensions:
                    if getattr(dim, 'dimension_type', 'main') == 'sub' and getattr(dim, 'parent_dimension_id', None):
                        parent_ids_to_load.add(dim.parent_dimension_id)
                all_ids_to_load = set(dim_ids) | parent_ids_to_load
                output_param_map = {}
                input_param_map = {}
                if all_ids_to_load:
                    from backend.models.algorithm_models import EvaluationDimensionParam
                    all_params = EvaluationDimensionParam.query.filter(
                        EvaluationDimensionParam.dimension_id.in_(list(all_ids_to_load)),
                        EvaluationDimensionParam.deleted == False
                    ).all()
                    for p in all_params:
                        if p.param_direction == 'output':
                            output_param_map.setdefault(p.dimension_id, []).append({
                                'param_code': p.param_code,
                                'field_path': p.field_path,
                                'field_type': p.field_type,
                                'agg_role': p.agg_role,
                                'output_role': p.output_role,
                                'visible_in_report': p.visible_in_report if p.visible_in_report is not None else True
                            })
                        elif p.param_direction == 'input':
                            input_param_map.setdefault(p.dimension_id, []).append({
                                'param_code': p.param_code,
                                'default_value': p.default_value,
                                'field_type': p.field_type,
                                'required': p.required
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
                        'output_params': dim_outputs,
                        'input_params': input_param_map.get(dim.id, [])
                    }

                    # 子维度继承父维度的API配置和 input_params（output_params 不继承，各子维度自己挂）
                    if getattr(dim, 'dimension_type', 'main') == 'sub':
                        parent_dim = getattr(dim, 'parent_dimension', None)
                        if not parent_dim and getattr(dim, 'parent_dimension_id', None):
                            parent_dim = local_db_session.query(Dimension).get(dim.parent_dimension_id)
                        if parent_dim:
                            # API 配置：仅当子维度缺 api_endpoints/api_url 时继承
                            # 注意 api_endpoints 可能为空列表 [] 或包含空URL的列表
                            sub_endpoints = dim_dict.get('api_endpoints')
                            has_valid_endpoint = False
                            if sub_endpoints and isinstance(sub_endpoints, list):
                                for ep in sub_endpoints:
                                    if isinstance(ep, dict) and (ep.get('url') or ep.get('endpoint')):
                                        has_valid_endpoint = True
                                        break
                            if not has_valid_endpoint and not dim_dict.get('api_url'):
                                # api_endpoints/api_url/api_settings 继承父维度
                                # task_type_code 不继承：子维度各自独立（如 tor/false_takeover/takeover_latency），
                                # 发请求时 task_type 用主维度的 turn_taking，sub_tasks 从子维度 task_type_code 提取
                                for k in ['api_endpoints', 'api_url', 'api_settings']:
                                    if not dim_dict.get(k):
                                        dim_dict[k] = getattr(parent_dim, k, None)
                                # 子维度继承主维度的 task_type_code，用于发请求时 task_type=turn_taking
                                dim_dict['parent_task_type_code'] = getattr(parent_dim, 'task_type_code', None)
                            # input_params 继承：子维度自己没有 input 时，用父维度的 input_params
                            if not dim_dict.get('input_params') and input_param_map.get(parent_dim.id):
                                dim_dict['input_params'] = input_param_map.get(parent_dim.id)

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
        round_number = kwargs.get('round_number')
        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
            dim_name = dim_data['name']

            current_app = get_app()
            dimension_result_id = None
            with current_app.app_context():
                local_db_session = db.session()
                try:
                    # 检查是否已存在同一 result_id + dim_id + round_number 的记录
                    existing_query = local_db_session.query(TestResultDimension).filter(
                        TestResultDimension.test_result_id == result_id,
                        TestResultDimension.dimension_id == dim_id,
                    )
                    if round_number is not None:
                        existing_query = existing_query.filter(
                            TestResultDimension.round_number == round_number
                        )
                    else:
                        existing_query = existing_query.filter(
                            TestResultDimension.round_number.is_(None)
                        )
                    existing = existing_query.first()

                    if existing:
                        # 已存在记录：如果是 pending 状态则复用，否则也复用（避免重复创建）
                        dimension_result_id = existing.id
                        if existing.evaluation_status == 'pending':
                            self._log(
                                level='DEBUG',
                                content=f"复用已有 pending 维度记录: dim_name={dim_name}, dim_id={dim_id}, dr_id={dimension_result_id}",
                                task_id=task_id,
                                test_case_id=test_case_id
                            )
                        else:
                            # 重置为 pending 以便重新评估
                            existing.evaluation_status = 'pending'
                            existing.score = None
                            existing.error_message = None
                            existing.api_request_body = None
                            existing.api_raw_response = None
                            local_db_session.commit()
                            self._log(
                                level='DEBUG',
                                content=f"重置已有维度记录为 pending: dim_name={dim_name}, dim_id={dim_id}, dr_id={dimension_result_id}",
                                task_id=task_id,
                                test_case_id=test_case_id
                            )
                        dimension_result_map[dim_id] = dimension_result_id
                        continue

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
                                    round_number, field_mapper, ref_texts, rounds_list=None,
                                    flat_eval_fields=None):
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

            # 分组键：(endpoint_url, parent_dimension_id)
            # 同一父维度下的子维度分到同一组，发一个请求给 eval_server
            # 父维度自身（dimension_type=main）用自身 id 作为 parent（即 None → 用 task_type_code 代替）
            parent_id = dim_data.get('parent_dimension_id')
            if dim_type == 'main':
                parent_id = dim_id  # 主维度自己一组（通常不直接参与评估）
            group_key = (endpoint_url, parent_id)
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
            endpoint_url, _ = group_key
            representative_dim_data = group_items[0][0]
            group_dim_names = [item[0]['name'] for item in group_items]
            group_dim_ids = [item[0]['id'] for item in group_items]

            # task_type 用主维度的 task_type_code（parent_task_type_code），
            # 子维度各自的 task_type_code 提取为 sub_tasks 注入 payload
            task_type_code = representative_dim_data.get('parent_task_type_code') or representative_dim_data.get('task_type_code')

            self._log(
                level='DEBUG',
                content=f"[分组详情] group_key={group_key}, 维度IDs={group_dim_ids}, 维度名称={group_dim_names}, 代表维度ID={representative_dim_data['id']}, 代表维度name={representative_dim_data['name']}, task_type={task_type_code}, api_settings={representative_dim_data.get('api_settings')}",
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
                round_number, field_mapper, ref_texts, rounds_list, flat_eval_fields
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
                         round_number, field_mapper, ref_texts, rounds_list=None,
                         flat_eval_fields=None):
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

        # 多轮评估：传 rounds 列表给端点Worker
        if rounds_list:
            task_data['rounds'] = rounds_list

        # 单轮兼容：透传扁平字段（answer, correct_answer 等）
        if flat_eval_fields:
            for k, v in flat_eval_fields.items():
                if k not in task_data:
                    task_data[k] = v

        output_field_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)
        algo_results = {}
        if isinstance(algorithm_result, dict):
            # 多轮结构：output 字段在 rounds[].output 里（key 是 target_param 名）
            # 单轮评估(round_number有值)取 rounds[round_number]，多轮整体(round_number=None)取 rounds[-1]
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
                val = algorithm_result.get(key)
                if val is None and ref_output:
                    val = ref_output.get(key)
                self._log(
                    level='DEBUG',
                    content=f"[task_data algo_results] key={key}, value={val}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                # 保留 None 而非转为空串，让维度级默认值有机会覆盖
                algo_results[key] = val

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
                    # 已完成评估的用例：同步 status 字段（覆盖服务重启后 status 停留在 pending 的情况）
                    if tc.evaluation_status in ['queued', 'pending'] and tc.execution_status in ['completed', 'failed']:
                        tc.evaluation_status = 'completed'
                        if tc.status == 'pending':
                            tc.status = tc.execution_status
                    elif tc.evaluation_status == 'completed' and tc.status == 'pending' and tc.execution_status in ['completed', 'failed']:
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
