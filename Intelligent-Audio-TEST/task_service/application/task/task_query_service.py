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
from shared.utils.status_constants import TaskStatus

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
            test_type = raw.get('test_type', 'api')
            results = raw.get('results', [])
            tc_dto = raw.get('tc', {})

            # 构建音频列表
            # TODO: 完整实现需要 ReadModel 返回足够字段以构建音频列表
            audios_list = []

            # 构建 algorithm_results 和 field_mapping
            algorithm_type = case_info.get('algorithm_type', '') if case_info else ''
            algorithm_results = []
            field_mapping = {'result': [], 'reference': []}
            result_audios = {}

            try:
                from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
                _algo_repo = AlgorithmRepository()

                if algorithm_type:
                    field_mapping = _algo_repo.algo_get_full_field_mapping(algorithm_type)

                output_fields = _algo_repo.algo_get_output_fields(algorithm_type) if algorithm_type else []

                for i, result in enumerate(results):
                    pr = results[i]
                    resource = pr.get('device_name') or pr.get('api_name') or f'result_{result.get("id")}'

                    algo_res = result.get('algorithm_result') or {}
                    r_data = result.get('result_data') or {}
                    if not isinstance(r_data, dict):
                        r_data = {}

                    combined_data = {**algo_res, **r_data}
                    for field in output_fields:
                        param_key = field.get('target_param') or field.get('source_param')
                        if not param_key or not combined_data.get(param_key):
                            continue

                        if algorithm_type == 'voice_llm' and param_key == 'rounds':
                            rounds_arr = combined_data.get('rounds') or []
                            if isinstance(rounds_arr, list):
                                for r_idx, r_item in enumerate(rounds_arr):
                                    raw_round = r_item.get('roundNumber')
                                    if raw_round is None:
                                        raw_round = r_item.get('round')
                                    rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
                                    out = r_item.get('output') or {}
                                    for sub_key in ('question', 'answer'):
                                        val = out.get(sub_key)
                                        if val:
                                            algorithm_results.append({
                                                'device': resource,
                                                'param_code': f'{sub_key}@round:{rn}',
                                                'param_type': 'text',
                                                'label': f'{sub_key} (第{rn}轮)',
                                                'value': val,
                                                'round_number': rn,
                                            })
                            algorithm_results.append({
                                'device': resource,
                                'param_code': param_key,
                                'param_type': field.get('param_type', 'json'),
                                'label': field.get('dimension_name') or param_key,
                                'value': combined_data[param_key],
                            })
                        else:
                            algorithm_results.append({
                                'device': resource,
                                'param_code': param_key,
                                'param_type': field.get('param_type', 'text'),
                                'label': field.get('dimension_name') or param_key,
                                'value': combined_data[param_key],
                            })
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


# 模块级单例
task_query_service = TaskQueryService()
