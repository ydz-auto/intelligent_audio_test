# -*- coding: utf-8 -*-
"""报告公共辅助方法集合（report_service 版本）。

从 api_gateway/application/services/report/report_helpers.py 迁移而来，
保持 ReportHelpers 类原有逻辑不变，仅做以下调整：
- 移除直接数据库访问（PO / get_db_session），改为通过 gRPC 客户端获取数据
- 移除 api_gateway 专属依赖（response / error_codes / sqlalchemy / storage / pandas 等）
- gRPC helper 函数统一从 report_service.infrastructure.clients.grpc_clients 导入
- ReportUtils / ReportQueryBuilder 导入路径切换到 report_service

本模块不包含导出（Excel/ZIP）相关逻辑，该部分仍由 api_gateway 负责。
"""

import logging

from shared.utils.log_handler import log_not_emit
from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder

# 复用 grpc_clients 中已定义的 gRPC helper，避免重复实现
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_audio,
    _grpc_get_audios_by_ids,
    _grpc_get_playback_device,
    _grpc_get_playback_devices_by_ids,
    _grpc_get_devices_by_ids,
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _dim_id,
    _dim_name,
)

logger = logging.getLogger(__name__)


class ReportHelpers:
    """报告公共辅助方法集合。

    承载从 ReportQueryService 拆分出的公共辅助方法，
    保持原有逻辑不变，仅做文件拆分。
    """

    # ------------------------------------------------------------------
    # 公共辅助方法（原 ReportControllerBase）
    # ------------------------------------------------------------------

    # 公共函数：根据参数键名推断 param_type
    @staticmethod
    def _infer_param_type(param_key: str) -> str:
        key_lower = param_key.lower()
        if 'rttm' in key_lower:
            return 'rttm'
        if 'stm' in key_lower:
            return 'stm'
        if 'audio' in key_lower:
            return 'audio'
        return 'text'

    # 公共函数：构建报告音频列表（统一 task 和 compare 两种模式）
    @staticmethod
    def _build_audios_list(test_case, mode='task'):
        """
        构建 audios_list，支持两种字段命名模式：
        - mode='task':  使用 playback_device_id / playbackDeviceName / testType
        - mode='compare': 使用 device_id / device_name / audio_type
        """
        from report_service.infrastructure.clients.grpc_clients import _grpc_algo_normalize_algorithm_params

        config = test_case.config or {}
        rounds = config.get('rounds', [])
        if not rounds:
            return []

        audios_list = []
        is_compare = (mode == 'compare')

        # 字段名映射
        if is_compare:
            dev_id_key = 'device_id'
            dev_name_key = 'device_name'
            type_key = 'audio_type'
            url_tmpl = '/api/v1/audios/{id}/stream'
            noise_spl_key = 'noise_spl'
            play_order_key = 'play_order'
        else:
            dev_id_key = 'playback_device_id'
            dev_name_key = 'playbackDeviceName'
            type_key = 'testType'
            url_tmpl = '/api/audios/play/{id}'
            noise_spl_key = 'spl'
            play_order_key = 'play_order'

        # 收集所有轮的设备 ID
        all_device_ids = set()
        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue
            for audio_cfg in round_item.get('audios', []):
                dev_id = audio_cfg.get(dev_id_key)
                if dev_id and dev_id != '':
                    all_device_ids.add(dev_id)
            if not is_compare:
                bg_noise = round_item.get('backgroundNoise') or {}
                noise_dev = bg_noise.get(dev_id_key)
                if noise_dev and noise_dev != '':
                    all_device_ids.add(noise_dev)

        # 通过 gRPC 批量查询设备（Device 或 PlaybackDevice）
        devices = {}
        if all_device_ids:
            if is_compare:
                dev_map = _grpc_get_devices_by_ids(list(all_device_ids))
                devices = {k: v.get('name') for k, v in dev_map.items()}
            else:
                dev_map = _grpc_get_playback_devices_by_ids(list(all_device_ids))
                devices = {k: v.get('name') for k, v in dev_map.items()}

        tc_test_type = test_case.test_type or 'api'

        per_round_dry = []
        noise_audios = []
        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue
            round_number = round_item.get('roundNumber') or round_item.get('round_number') or 1
            round_dry = []

            for audio_cfg in round_item.get('audios', []):
                audio_id = audio_cfg.get('audio_id')
                if audio_id:
                    audio = _grpc_get_audio(audio_id)
                    if audio:
                        dev_id = audio_cfg.get(dev_id_key)
                        if dev_id == '':
                            dev_id = None
                        audio_item = {
                            type_key: tc_test_type,
                            "id": audio.get('id'),
                            "filename": audio.get('original_filename') or audio.get('name'),
                            "duration": audio.get('duration'),
                            "url": url_tmpl.format(id=audio.get('id')),
                            "spl": audio_cfg.get('spl'),
                            "play_order" if is_compare else "playOrder": audio_cfg.get('play_order'),
                            dev_id_key if is_compare else "playbackDeviceId": dev_id,
                            dev_name_key if is_compare else "playbackDeviceName": devices.get(int(dev_id)) if dev_id else None,
                            "label": audio_cfg.get('label') if not is_compare else None,
                            "roundNumber": round_number,
                        }
                        # 移除 None 值的 label 键（compare 模式不加 label）
                        if is_compare:
                            audio_item.pop('label', None)
                        audios_list.append(audio_item)
                        round_dry.append(audio_item)

            # 噪声
            background_noise = round_item.get('backgroundNoise') or {}
            if background_noise.get('audio_id'):
                noise_audio = _grpc_get_audio(background_noise['audio_id'])
                if noise_audio:
                    noise_item = {
                        type_key: "noise",
                        "id": noise_audio.get('id'),
                        "filename": noise_audio.get('name'),
                        "duration": noise_audio.get('duration'),
                        "url": url_tmpl.format(id=noise_audio.get('id')),
                        noise_spl_key: background_noise.get('spl'),
                        "roundNumber": round_number,
                    }
                    if not is_compare:
                        noise_item["playOrder"] = None
                        noise_item["playbackDeviceId"] = None
                        noise_item["playbackDeviceName"] = None
                        noise_item["label"] = None
                    noise_audios.append(noise_item)

            if is_compare:
                audios_list.extend(round_dry)
            per_round_dry.append(round_dry)

        # 每轮内部排序
        sort_key = play_order_key if is_compare else 'playOrder'
        for round_dry in per_round_dry:
            round_dry.sort(key=lambda x: (x.get(sort_key) is None, x.get(sort_key) or 999))

        # 获取 overlap 参数（取首轮配置）
        first_round = rounds[0] if rounds else {}
        overlap_config = {
            'algorithm_params': first_round.get('algorithmParams', {}) if isinstance(first_round, dict) else {}
        }
        _overlap_params = _grpc_algo_normalize_algorithm_params(overlap_config.get('algorithm_params', {})) if overlap_config else {}
        try:
            overlap_time = max(0.0, float(_overlap_params.get('overlap_time', 0))) if overlap_config else 0
        except (ValueError, TypeError):
            overlap_time = 0
        try:
            overlap_rate = max(0.0, min(1.0, float(_overlap_params.get('overlap_rate', 0)))) if overlap_config else 0
        except (ValueError, TypeError):
            overlap_rate = 0

        # 按轮次计算 timeline
        global_offset = 0
        for round_dry in per_round_dry:
            prev_end_time = 0
            for i, audio_item in enumerate(round_dry):
                duration = audio_item.get('duration') or 0
                if i == 0:
                    timeline_start = global_offset
                else:
                    if overlap_time and overlap_time > 0:
                        timeline_start = prev_end_time - overlap_time
                        if timeline_start < global_offset:
                            timeline_start = global_offset
                    elif overlap_rate is not None and overlap_rate > 0:
                        elapsed = prev_end_time - global_offset
                        timeline_start = global_offset + elapsed * (1 - overlap_rate)
                    else:
                        timeline_start = prev_end_time
                audio_item['timelineStart'] = round(timeline_start, 3)
                audio_item['timelineEnd'] = round(timeline_start + duration, 3)
                prev_end_time = timeline_start + duration
            global_offset = prev_end_time

        for noise_item in noise_audios:
            noise_item['timelineStart'] = 0
            noise_item['timelineEnd'] = round(noise_item.get('duration') or 0, 3)

        audios_list.extend(noise_audios)
        return audios_list

    # 公共函数：解析API请求体JSON
    @staticmethod
    def parse_api_request(api_request):
        if isinstance(api_request, str):
            import json
            try:
                api_request = json.loads(api_request)
            except json.JSONDecodeError:
                logger.debug("解析 API 请求体 JSON 失败，已保留原始字符串", exc_info=True)
        return api_request

    # 公共函数：获取任务执行标识前缀
    @staticmethod
    def get_task_time_prefix(task):
        return ReportUtils.get_task_time_prefix(task)

    # 公共函数：获取设备或API名称作为资源，使用ID+名称确保唯一性
    @staticmethod
    def get_resource_name(result, task=None, use_time_prefix=False):
        return ReportUtils.get_resource_name(result, task, use_time_prefix)

    # 公共函数：提取维度得分
    @staticmethod
    def extract_dimension_values(result_id, all_dimensions, dim_results_map=None, fill_missing=True):
        dim_values = {}

        if all_dimensions is None:
            log_not_emit('ERROR', 'report_controller_base', f'all_dimensions is None in extract_dimension_values for result {result_id}', category='report')
            return dim_values

        if dim_results_map is not None:
            # 使用预先查询好的映射表，避免循环内查询数据库
            result_dims = dim_results_map.get(result_id, [])

            # 支持字典格式或对象格式
            for d in result_dims:
                if isinstance(d, dict):
                    dim_name = d.get('name') or d.get('dimension_name')
                    dim_val = d.get('value') or d.get('dimension_value')
                elif hasattr(d, 'dimension_name') or hasattr(d, 'name'):
                    dim_name = getattr(d, 'dimension_name', None) or getattr(d, 'name', None)
                    dim_val = getattr(d, 'dimension_value', None) or getattr(d, 'value', None)
                else:
                    dim_name = None
                    dim_val = None

                if dim_name is not None:
                    dim_values[dim_name] = dim_val

            if fill_missing:
                for dim in all_dimensions:
                    dim_name = _dim_name(dim)
                    if dim_name and dim_name not in dim_values:
                        dim_values[dim_name] = None
        else:
            # gRPC 兜底：通过 evaluation_service 查询单个 result 的维度结果
            dim_map = _grpc_get_dim_results([result_id])
            dim_results = dim_map.get(result_id, [])
            # 构建 dim_id -> name 映射
            dim_id_to_name = {_dim_id(d): _dim_name(d) for d in all_dimensions}
            for dr in dim_results:
                if isinstance(dr, dict):
                    dim_id = dr.get('dimension_id')
                    dim_val = dr.get('dimension_value')
                else:
                    dim_id = getattr(dr, 'dimension_id', None)
                    dim_val = getattr(dr, 'dimension_value', None)
                if dim_id and dim_id in dim_id_to_name:
                    dim_values[dim_id_to_name[dim_id]] = dim_val
            if fill_missing:
                for dim in all_dimensions:
                    dim_name = _dim_name(dim)
                    if dim_name and dim_name not in dim_values:
                        dim_values[dim_name] = None
        return dim_values

    # 公共函数：构建结果信息
    @staticmethod
    def build_result_info(result):
        return {
            "status": "成功" if result.execution_status == "completed" else "失败",
            "start_time": result.created_at.isoformat() if result.created_at else None,
            "end_time": result.created_at.isoformat() if result.created_at else None
        }

    # 公共函数：提取音频列表
    @staticmethod
    def _extract_audios_list(test_case, test_type=None):
        """
        从用例配置中提取所有匹配的音频信息列表
        """
        config = test_case.config if hasattr(test_case, 'config') else None
        if not config and isinstance(test_case, dict):
            config = test_case.get('config')
        if not config or 'audios' not in config:
            return []

        test_audios = config.get('audios', [])
        if not test_audios:
            return []

        results = []
        tc_test_type = test_case.test_type if hasattr(test_case, 'test_type') else (test_case.get('test_type') if isinstance(test_case, dict) else 'api')

        # 如果指定了类型且不匹配记录类型，直接返回空
        if test_type is not None and test_type != tc_test_type:
            return results

        for audio_cfg in test_audios:
            audio_id = audio_cfg.get('audio_id')
            if audio_id:
                audio = _grpc_get_audio(audio_id)
                if audio:
                    results.append({
                        "id": audio.get('id'),
                        "filename": audio.get('original_filename') or audio.get('name'),
                        "duration": audio.get('duration'),
                        "url": f"/api/v1/audios/{audio.get('id')}/stream",
                        "test_type": tc_test_type
                    })
        return results

    # 公共函数：计算正态分布数据
    @staticmethod
    def calculate_normal_distribution(raw_data):
        """
        计算正态分布数据，包括统计信息、区间百分比和分布曲线

        参数：
        raw_data: dict - 原始数据，格式为 {resource: {dim_name: [values]}}

        返回：
        dict - 正态分布数据，格式为 {resource: {dim_name: {statistics, interval_percentages, distribution}}}
        """
        import numpy as np
        normal_distribution_data = {}

        for resource in raw_data:
            normal_distribution_data[resource] = {}
            for dim_name in raw_data[resource]:
                values = raw_data[resource][dim_name]
                count = len(values)

                if count > 0:
                    # 处理原始数据中的NaN值
                    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

                    # 计算基本统计信息
                    mean = np.mean(values)
                    std = np.std(values)
                    min_val = np.min(values)
                    max_val = np.max(values)
                    median = np.median(values)

                    # 计算四分位数
                    if count >= 4:
                        q1 = np.percentile(values, 25)
                        q3 = np.percentile(values, 75)
                    elif count >= 2:
                        q1 = values[0]
                        q3 = values[-1]
                    else:
                        q1 = values[0]
                        q3 = values[0]

                    # 计算区间百分比
                    if count > 1 and std > 0:
                        # 正方向区间百分比
                        within_plus_1std = len([v for v in values if v <= mean + std]) / count * 100
                        within_plus_2std = len([v for v in values if v <= mean + 2 * std]) / count * 100
                        within_plus_3std = len([v for v in values if v <= mean + 3 * std]) / count * 100
                        beyond_plus_3std = len([v for v in values if v > mean + 3 * std]) / count * 100

                        # 负方向区间百分比
                        within_minus_1std = len([v for v in values if v >= mean - std]) / count * 100
                        within_minus_2std = len([v for v in values if v >= mean - 2 * std]) / count * 100
                        within_minus_3std = len([v for v in values if v >= mean - 3 * std]) / count * 100
                        beyond_minus_3std = len([v for v in values if v < mean - 3 * std]) / count * 100
                    else:
                        # 只有一个数据点或标准差为0时，所有区间百分比为0
                        within_plus_1std = 0.0
                        within_plus_2std = 0.0
                        within_plus_3std = 0.0
                        beyond_plus_3std = 0.0
                        within_minus_1std = 0.0
                        within_minus_2std = 0.0
                        within_minus_3std = 0.0
                        beyond_minus_3std = 0.0

                    # 处理统计信息中的NaN值
                    mean = float(round(float(np.nan_to_num(mean, nan=0.0)), 2))
                    std = float(round(float(np.nan_to_num(std, nan=0.0)), 2))
                    min_val = float(round(float(np.nan_to_num(min_val, nan=0.0)), 2))
                    q1 = float(round(float(np.nan_to_num(q1, nan=0.0)), 2))
                    median = float(round(float(np.nan_to_num(median, nan=0.0)), 2))
                    q3 = float(round(float(np.nan_to_num(q3, nan=0.0)), 2))
                    max_val = float(round(float(np.nan_to_num(max_val, nan=0.0)), 2))

                    normal_distribution_data[resource][dim_name] = {
                        "raw_values": values.tolist(),
                        "statistics": {
                            "count": count,
                            "mean": mean,
                            "std": std,
                            "min": min_val,
                            "q1": q1,
                            "median": median,
                            "q3": q3,
                            "max": max_val
                        },
                        "interval_percentages": {
                            "positive": {
                                "within_plus_1std": float(round(np.nan_to_num(within_plus_1std, nan=0.0), 1)),
                                "within_plus_2std": float(round(np.nan_to_num(within_plus_2std, nan=0.0), 1)),
                                "within_plus_3std": float(round(np.nan_to_num(within_plus_3std, nan=0.0), 1)),
                                "beyond_plus_3std": float(round(np.nan_to_num(beyond_plus_3std, nan=0.0), 1))
                            },
                            "negative": {
                                "within_minus_1std": float(round(np.nan_to_num(within_minus_1std, nan=0.0), 1)),
                                "within_minus_2std": float(round(np.nan_to_num(within_minus_2std, nan=0.0), 1)),
                                "within_minus_3std": float(round(np.nan_to_num(within_minus_3std, nan=0.0), 1)),
                                "beyond_minus_3std": float(round(np.nan_to_num(beyond_minus_3std, nan=0.0), 1))
                            }
                        }
                    }
                else:
                    # 没有数据点
                    normal_distribution_data[resource][dim_name] = {
                        "raw_values": [],
                        "statistics": {
                            "count": 0,
                            "mean": 0,
                            "std": 0,
                            "min": 0,
                            "q1": 0,
                            "median": 0,
                            "q3": 0,
                            "max": 0
                        },
                        "interval_percentages": {
                            "positive": {
                                "within_plus_1std": 0.0,
                                "within_plus_2std": 0.0,
                                "within_plus_3std": 0.0,
                                "beyond_plus_3std": 0.0
                            },
                            "negative": {
                                "within_minus_1std": 0.0,
                                "within_minus_2std": 0.0,
                                "within_minus_3std": 0.0,
                                "beyond_minus_3std": 0.0
                            }
                        }
                    }

        return normal_distribution_data
