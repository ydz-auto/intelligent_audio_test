# -*- coding: utf-8 -*-
"""任务分发混入：按端点分组维度并异步提交评估任务到 worker（Infrastructure 层）

P0-1 DDD 改造：从 domain/services/ 移至 infrastructure/。
线程池提交、端点 Worker 调度是基础设施逻辑，不属于 Domain 层。
"""
import json

from evaluation_service.domain.services.endpoint_helpers import get_endpoint_url
from shared.utils.round_data_utils import normalize_round_output


class TaskDispatcherMixin:
    """按端点分组维度并异步提交评估任务到端点 Worker"""

    def _dispatch_evaluation_tasks(self, dimension_data_list, dimension_result_map, result_id, task_id,
                                    test_case_id, algorithm_result, algorithm_type, device_type,
                                    round_number, field_mapper, ref_texts, rounds_list=None,
                                    flat_eval_fields=None, api_id=None):
        """将维度按端点分组并异步提交评估任务

        INT-1757（C6b）：``api_id`` 为结果所属 API 实例（来源 test_results.api_id，
        由 evaluate_case 解析），随 task_data 下发给端点 Worker 取该 API 的输出声明。
        """
        # 评估能力注册表分流：THIRD_PARTY_C 维度走第三方评估链路（8 步流程），LOCAL 维度走原端点链路
        local_list, third_party_list = self._split_by_eval_capability(
            dimension_data_list, task_id, test_case_id)
        if third_party_list:
            self._dispatch_third_party_tasks(
                third_party_list, dimension_result_map, result_id, task_id, test_case_id,
                algorithm_result, algorithm_type, device_type, round_number, field_mapper,
                ref_texts, rounds_list, flat_eval_fields, api_id=api_id)
        dimension_data_list = local_list

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

        # 组间自动合并：无显式分组键的多个 parent 分组，若满足
        # 同 endpoint + 同 category_id + 组内所有维度的
        # (task_type_code, body_template) 签名完全一致，
        # 则并入一组只发一次请求（如拒识族 3 主维度同族同 task_type 同 body
        # → 一次判定，三率同源一致）。
        # 组内只要含 task_type 不同的维度（如 turn_eval 主子异构、靠 sub_tasks 工作）
        # 或 body_template 不一致，则保持原 parent 分组不合并。
        group_count_before = len(endpoint_groups)
        endpoint_groups = self._merge_dimension_groups(endpoint_groups)
        if len(endpoint_groups) < group_count_before:
            merged_names = [{'endpoint': group_key[0], 'dims': [item[0]['name'] for item in items]}
                            for group_key, items in endpoint_groups.items()]
            self._log(
                level='INFO',
                content=f"维度组间自动合并: {group_count_before} 组 → {len(endpoint_groups)} 组"
                        f"（同 endpoint + 同 category + 同 task_type/body 签名合并为一次请求一次判定）"
                        f": {merged_names}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        self._submit_to_workers(
            endpoint_groups, result_id, task_id, test_case_id, algorithm_result,
            algorithm_type, device_type, round_number, field_mapper, ref_texts,
            rounds_list, flat_eval_fields, api_id=api_id
        )

    def _group_dimensions_by_endpoint(self, dimension_data_list, dimension_result_map,
                                        task_id, test_case_id):
        """按端点 URL 分组维度

        3b: 分组键改为 (endpoint_url, parent_dimension_id)，
        同一父维度下的子维度分到同一组，发一个请求给 eval_server。
        父维度自身（dimension_type=main）用自身 id 作为 parent。
        """
        endpoint_groups = {}
        no_endpoint_groups = []

        for dim_data in dimension_data_list:
            dim_id = dim_data['id']
            endpoints = dim_data.get('api_endpoints', [])
            api_url = dim_data.get('api_url')

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

            # 分组键：(endpoint_url, parent_dimension_id)
            # 同一父维度下的子维度分到同一组，发一个请求给 eval_server
            # 父维度自身（dimension_type=main）用自身 id 作为 parent
            dim_type = dim_data.get('dimension_type', 'main')
            parent_id = dim_data.get('parent_dimension_id')
            if dim_type == 'main':
                parent_id = dim_id  # 主维度自己一组
            group_key = (endpoint_url, parent_id)
            if group_key not in endpoint_groups:
                endpoint_groups[group_key] = []

            dimension_result_id = dimension_result_map.get(dim_id)
            if dimension_result_id:
                endpoint_groups[group_key].append((dim_data, dimension_result_id))

        return endpoint_groups, no_endpoint_groups

    @staticmethod
    def _merge_dimension_groups(endpoint_groups):
        """组间自动合并：合并键 (endpoint, (task_type_code, body_template) 签名集, category_id 集)
        相同的 parent 分组并为一组。

        - 签名取每个维度的 parent_task_type_code（无则 task_type_code）与
          api_settings.body_template（dict 归一化为排序 JSON 串比较）；
        - 组内含不同 task_type（主子异构族，靠 sub_tasks 工作）或 body_template
          不一致 → 签名集不同，保持原分组不合并；
        - endpoint 或 category_id 不同 → 合并键不同，不合并。
        """
        merged_groups = {}
        for group_key, group_items in endpoint_groups.items():
            endpoint_key = group_key[0]
            sigs = set()
            cats = set()
            for dim_data, _ in group_items:
                tc = dim_data.get('parent_task_type_code') or dim_data.get('task_type_code')
                body = (dim_data.get('api_settings') or {}).get('body_template')
                body_key = json.dumps(body, sort_keys=True, ensure_ascii=False) if isinstance(body, dict) else str(body)
                sigs.add((tc, body_key))
                cats.add(dim_data.get('category_id'))
            merge_key = (endpoint_key, frozenset(sigs), frozenset(cats))
            merged_groups.setdefault(merge_key, []).extend(group_items)
        return merged_groups

    def _submit_to_workers(self, endpoint_groups, result_id, task_id, test_case_id,
                            algorithm_result, algorithm_type, device_type, round_number,
                            field_mapper, ref_texts, rounds_list, flat_eval_fields,
                            api_id=None):
        """遍历端点分组，为每组创建 worker 并提交评估任务

        INT-308：提交前核销 case 级取消标记——用例删除/任务停止已取消的
        评估不再入队（无产出、无子服务计算开销）。
        """
        from evaluation_service.infrastructure.evaluation_api.api_request_handler import eval_task_registry
        if test_case_id and eval_task_registry.is_case_cancelled(task_id, str(test_case_id)):
            self._log(
                level='INFO',
                content=f"评估任务已被取消（用例删除/任务停止），跳过提交: test_case_id={test_case_id}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            return
        for group_key, group_items in endpoint_groups.items():
            # 合并后键为 (endpoint, 签名集, category 集) 三元组，endpoint 恒在首位
            endpoint_url = group_key[0]
            representative_dim_data = group_items[0][0]
            # task_type 用主维度的 task_type_code（parent_task_type_code），
            # 子维度各自的 task_type_code 提取为 sub_tasks 注入 payload
            task_type_code = representative_dim_data.get('parent_task_type_code') or representative_dim_data.get('task_type_code')

            worker = self._get_or_create_worker(endpoint_url, representative_dim_data)

            task_data = self._build_task_data(
                task_id, result_id, test_case_id, algorithm_result,
                representative_dim_data, group_items, algorithm_type, device_type,
                round_number, field_mapper, ref_texts, rounds_list, flat_eval_fields,
                api_id=api_id
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
                         representative_dim_data, group_items, algorithm_type, device_type,
                         round_number, field_mapper, ref_texts, rounds_list=None,
                         flat_eval_fields=None, api_id=None):
        """构建提交给端点Worker的任务数据

        INT-1757（C6b）：``api_id`` 随 task_data 透传到端点 Worker（输出声明按
        API 实例作用域取）；为 None 时不写键，存量路径 task_data 形状不变。
        """
        task_data = {
            'task_id': task_id,
            'result_id': result_id,
            'test_case_id': test_case_id,
            'algorithm_result': algorithm_result,
            'representative_dim_data': representative_dim_data,
            'group_items': group_items,
            'algorithm_type': algorithm_type,
            'device_type': device_type
        }

        if api_id is not None:
            try:
                task_data['api_id'] = int(api_id)
            except (TypeError, ValueError):
                pass

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
            # 多轮评估取值修正：单轮评估(round_number有值)取 rounds[round_number]，
            # 多轮整体(round_number=None)取 rounds[-1]，替代原来固定取 rounds[0]
            rounds_data = algorithm_result.get('rounds', [])
            if rounds_data:
                idx = round_number if round_number is not None else -1
                # INT-123：API 多轮链 output 为纯文本串，归一为 dict 再取字段
                if 0 <= idx < len(rounds_data) and isinstance(rounds_data[idx], dict):
                    ref_output = normalize_round_output(rounds_data[idx].get('output'))
                else:
                    ref_output = {}
            else:
                ref_output = {}
            for key in output_field_keys:
                val = algorithm_result.get(key)
                if val is None and ref_output:
                    val = ref_output.get(key)
                # 保留 None 而非转为空串，让维度级默认值有机会覆盖
                algo_results[key] = val

        for key, value in algo_results.items():
            if key not in task_data:
                task_data[key] = value

        for ref_field, ref_value in ref_texts.items():
            task_data[ref_field] = ref_value

        return task_data

    def _submit_to_endpoint_worker(self, task_data, worker):
        worker.put_task(task_data)
