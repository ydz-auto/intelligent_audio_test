# -*- coding: utf-8 -*-
"""第三方评估 Worker 与调度混入 — THIRD_PARTY_C 维度组的链路入口。

ThirdPartyEndpointWorker 复用 EndpointWorker 的队列/状态推进/结果落库全链路，
仅把「调评估 API」一步替换为第三方评估 ACL（8 步流程）；
ThirdPartyDispatcherMixin 把维度按评估能力注册表分流，THIRD_PARTY_C 维度
按（适配形态，父维度）分组提交，LOCAL 维度继续走现有端点分组（原链路不变）。
"""
from __future__ import annotations

import json
import logging

from evaluation_service.infrastructure.evaluation_api.endpoint_worker import EndpointWorker
from shared.models.common_enums import EvalCapabilityTarget

logger = logging.getLogger(__name__)


def resolve_capability_entry(dim_data):
    """按维度数据解析评估能力归属（注册表异常时 fail-closed 视为 LOCAL）。"""
    try:
        from evaluation_service.domain.services.evaluation_capability_registry import (
            evaluation_capability_registry,
        )
        return evaluation_capability_registry.resolve(dim_data)
    except Exception:
        logger.warning('评估能力注册表解析失败，维度回退 LOCAL 链路', exc_info=True)
        return None


class ThirdPartyEndpointWorker(EndpointWorker):
    """第三方评估端点 Worker — 仅覆写「调评估 API」一步，其余复用端点 Worker 链路。"""

    def __init__(self, endpoint_url, eval_service,
                 adapter_kind: str = 'multipart', max_timeout=30, max_concurrent=10):
        super().__init__(endpoint_url, eval_service, max_timeout=max_timeout,
                         max_concurrent=max_concurrent)
        self.adapter_kind = adapter_kind

    def _call_evaluation_api(self, task_id, test_case_id, endpoints, method, headers, payload,
                             representative_dim_data, dim_names, dim_info, audio_field_names):
        """走第三方评估 ACL（8 步流程），返回 resp_data 或 {'__error__': ...}。"""
        try:
            form_fields, files = self.eval_service.api_client._extract_files_from_payload(
                payload, audio_field_names=audio_field_names)
        except Exception as e:
            self._log(level='ERROR',
                      content=f"第三方评估文件提取失败: {e}", task_id=task_id,
                      test_case_id=test_case_id)
            return {'__error__': f'第三方评估文件提取失败: {e}'}
        return self.eval_service.third_party_eval.evaluate_dimension_group(
            payload=payload,
            form_fields=form_fields,
            files=files,
            representative_dim_data=representative_dim_data,
            dim_names=dim_names,
            dim_info=dim_info,
            task_id=task_id,
            test_case_id=test_case_id,
            adapter_kind=self.adapter_kind,
        )


class ThirdPartyDispatcherMixin:
    """按评估能力注册表分流维度并提交第三方评估 Worker。"""

    def _split_by_eval_capability(self, dimension_data_list, task_id, test_case_id):
        """返回 (local_list, third_party_list)；注册表未命中/禁用一律 LOCAL。"""
        local_list, third_party_list = [], []
        for dim_data in dimension_data_list:
            entry = resolve_capability_entry(dim_data)
            if entry is not None and entry.target == EvalCapabilityTarget.THIRD_PARTY_C:
                third_party_list.append(dim_data)
            else:
                local_list.append(dim_data)
        if third_party_list:
            self._log(
                level='INFO',
                content=f"评估能力分流: {len(third_party_list)} 个维度走第三方评估链路"
                        f"({[d.get('name') for d in third_party_list]})，"
                        f"{len(local_list)} 个维度走本地链路",
                task_id=task_id, test_case_id=test_case_id)
        return local_list, third_party_list

    def _dispatch_third_party_tasks(self, third_party_list, dimension_result_map, result_id,
                                    task_id, test_case_id, algorithm_result, algorithm_type,
                                    test_type, round_number, field_mapper, ref_texts,
                                    rounds_list=None, flat_eval_fields=None):
        """第三方维度按（适配形态, 父维度）分组，复用任务数据构建与线程池提交。"""
        groups = {}
        for dim_data in third_party_list:
            entry = resolve_capability_entry(dim_data)
            adapter_kind = entry.adapter.value if (entry and entry.adapter) else 'multipart'
            dim_type = dim_data.get('dimension_type', 'main')
            parent_id = dim_data.get('parent_dimension_id')
            if dim_type == 'main':
                parent_id = dim_data['id']
            dim_result_id = dimension_result_map.get(dim_data['id'])
            if dim_result_id:
                groups.setdefault((adapter_kind, parent_id), []).append((dim_data, dim_result_id))

        for (adapter_kind, _parent_id), group_items in groups.items():
            representative_dim_data = group_items[0][0]
            worker = self._get_or_create_third_party_worker(adapter_kind, representative_dim_data)
            task_data = self._build_task_data(
                task_id, result_id, test_case_id, algorithm_result,
                representative_dim_data, group_items, algorithm_type, test_type,
                round_number, field_mapper, ref_texts, rounds_list, flat_eval_fields)
            with self.api_client.global_lock:
                if self.api_client.thread_pool is None or self.api_client.thread_pool._shutdown:
                    self.api_client.init_thread_pool()
            try:
                self.api_client.thread_pool.submit(
                    self._submit_to_endpoint_worker, task_data, worker)
            except Exception as e:
                self._log(level='ERROR',
                          content=f"提交第三方评估任务失败: {e}", task_id=task_id,
                          test_case_id=test_case_id)

    def _get_or_create_third_party_worker(self, adapter_kind, representative_dim_data):
        key = f"third-party-c://{adapter_kind}/{representative_dim_data.get('id')}"
        # 与端点 Worker 字典同锁（WorkerManagementMixin），防并发评估重复建 Worker
        with self.endpoint_workers_lock:
            if not hasattr(self, '_third_party_workers'):
                self._third_party_workers = {}
            if key not in self._third_party_workers:
                self._third_party_workers[key] = ThirdPartyEndpointWorker(
                    endpoint_url=key, eval_service=self, adapter_kind=adapter_kind)
            return self._third_party_workers[key]
