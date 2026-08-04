"""任务分发混入：按端点分组维度并异步提交评估任务到 worker"""
from task_service.evaluation.evaluation_mixin import get_endpoint_url


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

        # 异步提交评估任务到各端点 worker
        self._submit_to_workers(
            endpoint_groups, result_id, task_id, test_case_id, algorithm_result,
            algorithm_type, test_type, round_number, field_mapper, ref_texts,
            rounds_list, flat_eval_fields
        )

    def _group_dimensions_by_endpoint(self, dimension_data_list, dimension_result_map,
                                        task_id, test_case_id):
        """按端点 URL 分组维度

        Returns:
            tuple: (endpoint_groups, no_endpoint_groups)
                endpoint_groups: {group_key: [(dim_data, dimension_result_id), ...]}
                no_endpoint_groups: [(dim_data, dimension_result_id), ...]
        """
        endpoint_groups = {}
        no_endpoint_groups = []  # 没有配置评估端点的维度，需标记失败避免任务卡死

        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
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

        return endpoint_groups, no_endpoint_groups

    def _submit_to_workers(self, endpoint_groups, result_id, task_id, test_case_id,
                            algorithm_result, algorithm_type, test_type, round_number,
                            field_mapper, ref_texts, rounds_list, flat_eval_fields):
        """遍历端点分组，为每组创建 worker 并提交评估任务"""
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
            rounds_data = algorithm_result.get('rounds', [])
            first_output = rounds_data[0].get('output', {}) if rounds_data and isinstance(rounds_data[0], dict) else {}
            for key in output_field_keys:
                val = algorithm_result.get(key)
                if val is None and first_output:
                    val = first_output.get(key)
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
