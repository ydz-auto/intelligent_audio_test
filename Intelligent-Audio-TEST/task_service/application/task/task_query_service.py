# -*- coding: utf-8 -*-
"""TaskQueryService — 任务查询应用服务（读侧）。

从 TaskCrudService 拆分而来，专门处理任务读操作：
- list_tasks: 任务列表
- get_task_detail: 任务详情（含时间预估）
- get_task_progress: 任务实时进度
- get_task_stats: 任务统计
- get_case_detail: 用例执行详情（含算法结果/音频构建）
- get_case_results: 用例执行结果

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 task_read_model / task_repository 访问 DB，不直接持有 session
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from shared.infrastructure.storage import storage
from shared.models.common_enums import FieldType, TestType
from shared.utils.status_constants import TaskStatus
from shared.utils.path_extractor import extract_by_path
from shared.constants.device_fields import DEVICE_FIELDS
from shared.utils.audio_path_utils import normalize_audio_path

from task_service.infrastructure.persistence.task_repository import task_repository
from task_service.infrastructure.read_models.task_read_model import task_read_model

logger = logging.getLogger(__name__)

_UTC_PLUS_8 = timezone(timedelta(hours=8))


class TaskQueryService:
    """任务查询应用服务（读侧）。"""

    def list_tasks(self, page=1, per_page=10, status=None, task_type=None,
                   algorithm_type=None, search=None, start_date=None, end_date=None) -> dict:
        """获取任务列表。"""
        try:
            result = task_read_model.search_tasks(
                page=page, per_page=per_page, status=status,
                task_type=task_type, algorithm_type=algorithm_type,
                search=search, start_date=start_date, end_date=end_date,
            )
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"查询任务列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_task_detail(self, task_id: int) -> dict:
        """获取单个任务详情。"""
        try:
            result = task_read_model.find_by_id_with_relations(task_id)
            if result is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}

            # 计算时间字段
            expected_total_time_str = None
            expected_complete_time_str = None
            used_time_str = None
            try:
                now = datetime.now(_UTC_PLUS_8)
                started_at_str = result.get('started_at')
                completed_at_str = result.get('completed_at')

                if started_at_str:
                    tz_started = datetime.fromisoformat(started_at_str)
                    if tz_started.tzinfo is None:
                        tz_started = tz_started.replace(tzinfo=_UTC_PLUS_8)

                    tz_completed = None
                    if completed_at_str:
                        tz_completed = datetime.fromisoformat(completed_at_str)
                        if tz_completed.tzinfo is None:
                            tz_completed = tz_completed.replace(tzinfo=_UTC_PLUS_8)

                    if tz_completed:
                        elapsed_seconds = max(0.0, (tz_completed - tz_started).total_seconds())
                    elif result.get('status') in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                        elapsed_seconds = 0.0
                    else:
                        elapsed_seconds = max(0.0, (now - tz_started).total_seconds())

                    used_time_str = self._format_duration(int(elapsed_seconds))

                    # 时间预估（通过 execution_engine）
                    try:
                        from task_service.core.execution_engine import execution_engine

                        task_orm = task_repository.get_task_orm(task_id)
                        if task_orm:
                            time_estimate = execution_engine.event_manager.calculate_time_estimate(task_orm)
                            estimated_total_seconds = time_estimate.get('expected_total_time', 0) or 0
                            expected_total_time_str = self._format_duration(estimated_total_seconds)

                            if not tz_completed:
                                expected_complete_dt = now + timedelta(seconds=estimated_total_seconds)
                                expected_complete_time_str = expected_complete_dt.strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                expected_complete_time_str = tz_completed.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        logger.warning(f"计算时间预估失败: {e}")

            except Exception as e:
                logger.warning(f"计算时间字段失败: {e}")

            result['expected_total_time'] = expected_total_time_str
            result['expected_complete_time'] = expected_complete_time_str
            result['used_time'] = used_time_str
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"获取任务详情失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_task_progress(self, task_id: int) -> dict:
        """获取任务实时进度。"""
        try:
            result = task_read_model.get_progress_detailed(task_id)
            if result is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"获取任务进度失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_task_stats(self, task_id: int) -> dict:
        """获取任务统计信息。"""
        try:
            result = task_read_model.get_task_stats(task_id)
            if result is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"获取任务统计失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_case_detail(self, task_id: int, case_id) -> dict:
        """获取单个用例的执行详情。"""
        try:
            raw = task_read_model.get_case_detail(task_id, str(case_id))
            if raw is None:
                return {'success': False, 'message': '未找到该任务关联的用例', 'data': None, 'code': 404}

            case_info = raw.get('case_info')
            test_type = raw.get('test_type', TestType.API.value)
            results = raw.get('results', [])
            tc_dto = raw.get('tc', {})

            # 构建音频列表
            # TODO: 完整实现需要 ReadModel 返回足够字段以构建音频列表
            audios_list = []

            # 构建 algorithm_results 和 field_mapping
            # 7. 构建 algorithm_results：优先读取预提取快照，无快照时实时提取
            algorithm_type = case_info.get('algorithm_type', '') if case_info else ''
            algorithm_results = []
            field_mapping = {'result': [], 'reference': []}
            result_audios = {}

            try:
                from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
                _algo_repo = AlgorithmRepository()

                if algorithm_type:
                    field_mapping = _algo_repo.algo_get_full_field_mapping(algorithm_type)

                # 7a. 收集所有维度 ID，批量查询 aux 参数（快照为空时才需要）
                output_fields = _algo_repo.algo_get_output_fields(algorithm_type) if algorithm_type else []

                # 构建 aux_params_map（与 report_service 逻辑一致）
                aux_params_map = {}
                all_dim_ids = set()
                for pr in results:
                    for dim in pr.get('dimensions', []):
                        dim_id = dim.get('id') or dim.get('dimension_id')
                        if dim_id:
                            all_dim_ids.add(dim_id)
                if all_dim_ids:
                    try:
                        from shared.clients.grpc_clients import get_algorithm_config_service_stub
                        from shared.proto import task_service_pb2 as task_pb
                        from shared.utils.grpc_json import loads as _loads
                        stub = get_algorithm_config_service_stub()
                        for dim_id in all_dim_ids:
                            resp = stub.GetDimensionParams(task_pb.GetDimensionParamsRequest(dimension_id=dim_id))
                            if not resp.success:
                                continue
                            data = _loads(resp.data, None)
                            items = data.get('params', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                            for p in items:
                                if not isinstance(p, dict):
                                    continue
                                if p.get('param_direction') != 'output':
                                    continue
                                if p.get('output_role') != 'aux':
                                    continue
                                if not p.get('visible_in_report'):
                                    continue
                                dim_name = p.get('dimension_name') or ''
                                if dim_id not in aux_params_map:
                                    aux_params_map[dim_id] = []
                                aux_params_map[dim_id].append({'param': p, 'dimension_name': dim_name})
                    except Exception:
                        pass

                for i, result in enumerate(results):
                    pr = results[i]
                    resource = pr.get('device_name') or pr.get('api_name') or f'result_{result.get("id")}'

                    # 优先读取预提取的 algorithm_results（存在 result_data 里）
                    r_data = result.get('result_data') or {}
                    if not isinstance(r_data, dict):
                        r_data = {}

                    snapshot = r_data.get('algorithm_results')
                    if snapshot:
                        algorithm_results.extend(snapshot)
                        continue

                    # 快照为空时回退到实时提取（兼容旧数据）
                    algo_res = result.get('algorithm_result') or {}
                    if not isinstance(algo_res, dict):
                        algo_res = {}

                    if not (algo_res or r_data):
                        continue

                    # 收集该 result 的维度行（用于 aux 提取）
                    result_dim_rows = pr.get('dimensions') or []

                    algorithm_results.extend(
                        TaskQueryService._build_algorithm_results_for_result(
                            result, resource, algo_res, r_data,
                            aux_params_map, result_dim_rows,
                            output_fields, algorithm_type
                        )
                    )
            except Exception as e:
                logger.warning(f"构建 algorithm_results 失败: {e}")

            # 构建 devices 列表和 metric_configs
            devices = list(set(
                pr.get('device_name') for pr in results if pr.get('device_name')
            ))
            metric_configs = []
            seen_metrics = set()
            for pr in results:
                for dim in pr.get('dimensions', []):
                    if dim.get('name') and dim['name'] not in seen_metrics:
                        seen_metrics.add(dim['name'])
                        metric_configs.append({'code': dim['name'], 'name': dim['name']})

            # 提取结果音频
            try:
                audio_types = {'audio_file', 'audio_stream', 'audio'}
                result_audio_fields = [
                    f for f in field_mapping.get('result', [])
                    if f.get('param_type') in audio_types
                ]

                if result_audio_fields:
                    for i, result in enumerate(results):
                        pr = results[i]
                        resource = pr.get('device_name') or pr.get('api_name') or f'result_{result.get("id")}'

                        algo_res = result.get('algorithm_result') or {}
                        r_data = result.get('result_data') or {}
                        if not isinstance(r_data, dict):
                            r_data = {}

                        combined_data = {**algo_res, **r_data}
                        device_audios = []

                        for field in result_audio_fields:
                            param_code = field.get('param_code') or field.get('source_param')
                            audio_data = combined_data.get(param_code)
                            if audio_data:
                                if isinstance(audio_data, str):
                                    raw_url = audio_data
                                elif isinstance(audio_data, dict):
                                    raw_url = audio_data.get('url') or audio_data.get('path', '')
                                else:
                                    raw_url = ''

                                if raw_url:
                                    try:
                                        presigned = storage.get_url(raw_url, expires=3600)
                                    except Exception:
                                        presigned = raw_url
                                else:
                                    presigned = ''

                                device_audios.append({
                                    'url': presigned,
                                    'filename': audio_data.get('filename') if isinstance(audio_data, dict) else param_code,
                                    'param_code': param_code,
                                })

                        if device_audios:
                            result_audios[resource] = device_audios
            except Exception as e:
                logger.warning(f"构建 result_audios 失败: {e}")

            response_data = {
                "task_id": task_id,
                "case_id": str(case_id),
                "case_name": case_info.get('name', '未知用例') if case_info else "未知用例",
                "status": tc_dto.get('status'),
                "execution_status": tc_dto.get('execution_status'),
                "evaluation_status": tc_dto.get('evaluation_status'),
                "started_at": tc_dto.get('started_at'),
                "completed_at": tc_dto.get('completed_at'),
                "duration": tc_dto.get('duration'),
                "error_message": tc_dto.get('error_message'),
                "audio_list": audios_list,
                "reference_params": {},  # 由网关侧构建（需要 ReportDataBuilder）
                "algorithm_results": algorithm_results,
                "algorithm_type": algorithm_type,
                "devices": devices,
                "metric_configs": metric_configs,
                "field_mapping": field_mapping,
                "result_audios": result_audios,
            }

            return {'success': True, 'message': '', 'data': response_data}
        except Exception as e:
            logger.error(f"获取用例详情失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_case_results(self, task_id: int, case_id) -> dict:
        """获取单个用例的执行结果。"""
        try:
            result = task_read_model.get_case_results(task_id, str(case_id))
            if result is None:
                return {'success': False, 'message': '未找到该任务关联的用例', 'data': None, 'code': 404}
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"获取用例结果失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    @staticmethod
    def _format_duration(secs: int) -> str:
        """格式化时长。"""
        if secs < 60:
            return f"{secs}秒"
        elif secs < 3600:
            m = secs // 60
            s = secs % 60
            return f"{m}分钟" + (f"{s}秒" if s > 0 else "")
        else:
            h = secs // 3600
            m = (secs % 3600) // 60
            return f"{h}小时" + (f"{m}分钟" if m > 0 else "")

    @staticmethod
    def _build_algorithm_results_for_result(
        result, resource, algo_res, result_data, aux_params_map,
        dim_result_rows, output_fields, algorithm_type
    ):
        """为单个 TestResult 构建 algorithm_results 扁平列表。

        合并 aux 辅助参数 + 设备/API 原始结果，供详情页使用。
        与 report_service.ReportDataBuilder.build_algorithm_results_for_result 逻辑一致。
        """
        import json
        import os

        algorithm_results = []

        if not (algo_res or result_data):
            return algorithm_results

        # ── 1. 构建 param_code → (dimension_name, field_type) 全局映射 ──
        param_to_dim = {}
        param_to_type = {}
        if aux_params_map:
            for _dim_id, aux_list in aux_params_map.items():
                for aux_info in aux_list:
                    p = aux_info['param']
                    param_code = p.get('param_code') if isinstance(p, dict) else getattr(p, 'param_code', None)
                    if param_code:
                        param_to_dim[param_code] = aux_info['dimension_name']
                        param_to_type[param_code] = p.get('field_type', FieldType.TEXT.value) if isinstance(p, dict) else getattr(p, 'field_type', FieldType.TEXT.value)

        # ── 2. 提取 aux 辅助参数值 ──
        aux_values = {}

        # 2a. 从 evaluation_data 提取
        if result_data:
            eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
            if isinstance(eval_data, dict):
                for param_code in param_to_dim:
                    if param_code in eval_data:
                        aux_values[param_code] = eval_data[param_code]

        # 2b. 从 api_raw_response 补充
        for dr in dim_result_rows:
            if not isinstance(dr, dict):
                continue
            raw_resp = dr.get('api_raw_response')
            if not raw_resp:
                continue
            if isinstance(raw_resp, str):
                try:
                    raw_resp = json.loads(raw_resp)
                except Exception:
                    continue
            dim_id = dr.get('dimension_id') or dr.get('id')
            for aux_info in (aux_params_map.get(dim_id, []) if aux_params_map else []):
                p = aux_info['param']
                param_code = p.get('param_code') if isinstance(p, dict) else getattr(p, 'param_code', None)
                if not param_code or param_code in aux_values:
                    continue
                field_path = p.get('field_path') if isinstance(p, dict) else getattr(p, 'field_path', None)
                value = _extract_by_path(raw_resp, field_path)
                if value is not None:
                    aux_values[param_code] = value

        # 输出 aux 参数
        for param_code, param_value in aux_values.items():
            if param_value is None:
                continue
            algorithm_results.append({
                'device': resource,
                'param_code': param_code,
                'param_type': param_to_type.get(param_code, FieldType.TEXT.value),
                'label': param_code,
                'value': param_value,
                'dimension_name': param_to_dim.get(param_code),
            })

        # ── 3. 提取设备/API 原始执行结果 ──
        combined_data = {**(algo_res or {}), **(result_data or {})}

        try:
            from task_service.config.config import Config
            _static_base = getattr(Config, 'STATIC_BASE_PATH', '')
        except Exception:
            _static_base = ''

        def _normalize_audio_path_wrapper(abs_path):
            """将音频文件的绝对路径转换为相对 STATIC_BASE_PATH 的相对路径。"""
            return normalize_audio_path(abs_path, _static_base)

        if algorithm_type == 'voice_llm':
            # voice_llm：按 output_fields 映射，rounds 数组展开
            for field in output_fields:
                param_key = field.get('target_param') or field.get('source_param')
                if not param_key or not combined_data.get(param_key):
                    continue
                if param_key == 'rounds':
                    rounds_arr = combined_data.get('rounds') or []
                    if isinstance(rounds_arr, list):
                        for r_idx, r_item in enumerate(rounds_arr):
                            raw_round = r_item.get('round')
                            rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
                            out = r_item.get('output') or {}
                            if isinstance(out, dict):
                                for sub_key, val in out.items():
                                    if val is None or sub_key == 'evaluation':
                                        continue
                                    sub_type = DEVICE_FIELDS.get(sub_key, FieldType.TEXT.value)
                                    if sub_type == 'audio_file' and isinstance(val, str) and val:
                                        val = _normalize_audio_path_wrapper(val)
                                    algorithm_results.append({
                                        'device': resource,
                                        'param_code': f'{sub_key}@round:{rn}',
                                        'param_type': sub_type,
                                        'label': f'{sub_key} (第{rn}轮)',
                                        'value': val,
                                        'round_number': rn,
                                        'dimension_name': None,
                                    })
                    algorithm_results.append({
                        'device': resource,
                        'param_code': param_key,
                        'param_type': field.get('param_type', FieldType.JSON.value),
                        'label': field.get('dimension_name') or param_key,
                        'value': combined_data[param_key],
                        'dimension_name': None,
                    })
                else:
                    algorithm_results.append({
                        'device': resource,
                        'param_code': param_key,
                        'param_type': field.get('param_type', FieldType.TEXT.value),
                        'label': field.get('dimension_name') or param_key,
                        'value': combined_data[param_key],
                        'dimension_name': None,
                    })
        else:
            # 非 voice_llm：按 output_fields 映射
            for field in output_fields:
                param_key = field.get('target_param') or field.get('source_param')
                if not param_key or not combined_data.get(param_key):
                    continue
                algorithm_results.append({
                    'device': resource,
                    'param_code': param_key,
                    'param_type': field.get('param_type', FieldType.TEXT.value),
                    'label': field.get('dimension_name') or param_key,
                    'value': combined_data[param_key],
                    'dimension_name': None,
                })

            # 补充固定设备字段
            device_values = {}
            if isinstance(algo_res, dict):
                rounds = algo_res.get('rounds') or []
                if rounds and isinstance(rounds, list) and isinstance(rounds[0], dict):
                    output = rounds[0].get('output') or {}
                    if isinstance(output, dict):
                        for k, v in output.items():
                            if k in DEVICE_FIELDS and v is not None:
                                device_values[k] = v
                agg = algo_res.get('aggregated') or {}
                if isinstance(agg, dict):
                    for k, v in agg.items():
                        if v is not None:
                            agg_type = FieldType.NUMBER.value if isinstance(v, (int, float)) else FieldType.TEXT.value
                            device_values['agg_' + k] = {'value': v, 'type': agg_type}

            if result_data:
                rrl = result_data.get('raw_results_list') or []
                if rrl and isinstance(rrl, list) and isinstance(rrl[0], dict):
                    raw_item = rrl[0]
                    raw_res = raw_item.get('raw_results') or {}
                    if isinstance(raw_res, dict):
                        for k, v in raw_res.items():
                            if k in DEVICE_FIELDS and v is not None and k not in device_values:
                                device_values[k] = v
                    for k in ['round_number', 'success']:
                        if k in raw_item and raw_item[k] is not None and k not in device_values:
                            device_values[k] = raw_item[k]

            existing_codes = {item['param_code'] for item in algorithm_results if item.get('device') == resource}
            for param_code, param_value in device_values.items():
                if param_value is None or param_value == '':
                    continue
                if param_code in existing_codes:
                    continue
                if param_code.startswith('agg_') and isinstance(param_value, dict) and 'value' in param_value:
                    actual_value = param_value['value']
                    param_type = param_value.get('type', FieldType.TEXT.value)
                else:
                    actual_value = param_value
                    param_type = DEVICE_FIELDS.get(param_code, FieldType.TEXT.value)
                if param_type == 'audio_file' and isinstance(actual_value, str) and actual_value:
                    actual_value = _normalize_audio_path(actual_value)
                algorithm_results.append({
                    'device': resource,
                    'param_code': param_code,
                    'param_type': param_type,
                    'label': param_code,
                    'value': actual_value,
                    'dimension_name': None,
                })

        return algorithm_results


# 模块级单例
task_query_service = TaskQueryService()
