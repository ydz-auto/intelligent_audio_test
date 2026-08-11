# -*- coding: utf-8 -*-
"""任务分发混入：按端点分组维度并异步提交评估任务到 worker（Infrastructure 层）

P0-1 DDD 改造：从 domain/services/ 移至 infrastructure/。
线程池提交、端点 Worker 调度是基础设施逻辑，不属于 Domain 层。
"""
from evaluation_service.domain.services.endpoint_helpers import get_endpoint_url


class TaskDispatcherMixin:
    """按端点分组维度并异步提交评估任务到端点 Worker"""

    def _dispatch_evaluation_tasks(self, dimension_data_list, dimension_result_map, result_id, task_id,
                                    test_case_id, algorithm_result, algorithm_type, test_type,
                                    round_number, field_mapper, ref_texts, rounds_list=None,
                                    flat_eval_fields=None):
        """将维度按端点分组并异步提交评估任务"""
        endpoint_groups, no_endpoint_groups = self._group_dimensions_by_endpoint(
            dimension_data_list, dimension_result_map, task_id, test_case_id
        )

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
            self._post_evaluate_updates(task_id, test_case_id)

        self._submit_to_workers(
            endpoint_groups, result_id, task_id, test_case_id, algorithm_result,
            algorithm_type, test_type, round_number, field_mapper, ref_texts,
            rounds_list, flat_eval_fields
        )

    def _group_dimensions_by_endpoint(self, dimension_data_list, dimension_result_map,
                                        task_id, test_case_id):
        """按端点 URL 分组维度"""
        endpoint_groups = {}
        no_endpoint_groups = []

        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
            endpoints = dim_data.get('api_endpoints', [])
            api_url = dim_data.get('api_url')
            task_type_code = dim_data.get('task_type_code')

            endpoint_url = None
            if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
                endpoint_url = get_endpoint_url(endpoints[0])
            if not endpoint_url:
                endpoint_url = api_url

            if not endpoint_url:
                self._log(
                    level='ERROR',
                    content=f"维度 {dim_data.get('name')} (id={dim_id}) 没有配置评估端点，无法提交评估任务",
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

        return endpoint_groups, no_endpoint_groups

    def _submit_to_workers(self, endpoint_groups, result_id, task_id, test_case_id,
                            algorithm_result, algorithm_type, test_type, round_number,
                            field_mapper, ref_texts, rounds_list, flat_eval_fields):
        """遍历端点分组，为每组创建 worker 并提交评估任务"""
        for group_key, group_items in endpoint_groups.items():
            endpoint_url, task_type_code = group_key
            representative_dim_data = group_items[0][0]

            worker = self._get_or_create_worker(endpoint_url, representative_dim_data)

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

        if round_number is not None:
            task_data['round_number'] = round_number

        if rounds_list:
            task_data['rounds'] = rounds_list

        if flat_eval_fields:
            for k, v in flat_eval_fields.items():
                if k not in task_data:
                    task_data[k] = v

        output_field_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)
        algo_results = {}
        if isinstance(algorithm_result, dict):
            rounds_data = algorithm_result.get('rounds', [])
            first_output = rounds_data[0].get('output', {}) if rounds_data and isinstance(rounds_data[0], dict) else {}
            for key in output_field_keys:
                val = algorithm_result.get(key)
                if val is None and first_output:
                    val = first_output.get(key)
                algo_results[key] = val if val is not None else ''

        for key, value in algo_results.items():
            if key not in task_data:
                task_data[key] = value

        for ref_field, ref_value in ref_texts.items():
            task_data[ref_field] = ref_value

        return task_data

    def _submit_to_endpoint_worker(self, task_data, worker):
        worker.task_queue.put(task_data)
