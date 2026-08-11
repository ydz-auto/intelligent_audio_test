# -*- coding: utf-8 -*-
"""normalize_summary_metrics 共享实现。

从 shared/utils/report/normalize.py 迁移至 report_service，
统一报告归一化逻辑到 report_service。

各服务（api_gateway 等）如需调用，应通过 gRPC 调用 report_service 的报告 RPC，
或直接 import report_service.application.services.normalize（跨服务 import 仍属违规，
仅作为过渡，后续应迁移为 gRPC 调用）。

仅 dimension_lookup 回调不同（各服务 gRPC 客户端不同）。
"""
from typing import Callable, Dict, Optional


def normalize_summary_metrics(summary: dict, dimension_lookup: Optional[Callable] = None) -> dict:
    """归一化报告摘要数据。

    Args:
        summary: 原始摘要 dict
        dimension_lookup: 可选回调，接收 dim_id 列表，返回 {id: decimal_places}。
                          为 None 时跳过 decimal_places 补全。

    Returns:
        归一化后的 dict
    """
    from report_service.application.services.report_utils import ReportUtils

    if not isinstance(summary, dict):
        return {}

    category_items = summary.get('case_categories') or []
    tag_items = summary.get('all_case_tags') or summary.get('all_tags') or []
    category_id_to_name = ReportUtils._build_id_name_map(category_items)
    tag_id_to_name = ReportUtils._build_id_name_map(tag_items)
    all_metrics_items = summary.get('all_metrics') or summary.get('allMetrics') or []
    if isinstance(all_metrics_items, list) and dimension_lookup:
        needs_decimal_places = any(
            isinstance(m, dict)
            and m.get('id') is not None
            and ('decimal_places' not in m and 'decimalPlaces' not in m)
            for m in all_metrics_items
        )
        if needs_decimal_places:
            ids = []
            for m in all_metrics_items:
                if not isinstance(m, dict):
                    continue
                mid = m.get('id')
                if mid is None:
                    continue
                try:
                    ids.append(int(mid))
                except Exception:
                    continue
            if ids:
                try:
                    id_to_decimal_places = dimension_lookup(list(set(ids)))
                except Exception:
                    id_to_decimal_places = {}
                for m in all_metrics_items:
                    if not isinstance(m, dict):
                        continue
                    if 'decimal_places' in m or 'decimalPlaces' in m:
                        continue
                    mid = m.get('id')
                    try:
                        mid_int = int(mid)
                    except Exception:
                        continue
                    if mid_int in id_to_decimal_places:
                        m['decimal_places'] = id_to_decimal_places[mid_int]

    raw_data_flat = ReportUtils.flatten_raw_data(summary.get('raw_data') or summary.get('rawData'))
    used_metric_names = set()
    for item in raw_data_flat:
        if not isinstance(item, dict):
            continue
        metrics = item.get('metrics') or []
        if not isinstance(metrics, list):
            continue
        for m in metrics:
            if not isinstance(m, dict):
                continue
            name = m.get('metric')
            values = m.get('values')
            if name is None:
                continue
            if isinstance(values, list) and len(values) > 0:
                used_metric_names.add(str(name))
            elif values is not None and not isinstance(values, list):
                used_metric_names.add(str(name))

    filtered_all_metrics_items = all_metrics_items
    if isinstance(all_metrics_items, list) and used_metric_names:
        filtered_all_metrics_items = [
            m
            for m in all_metrics_items
            if isinstance(m, dict)
            and m.get('name') is not None
            and str(m.get('name')) in used_metric_names
        ]

    metric_name_to_id = ReportUtils._build_metric_name_id_map(filtered_all_metrics_items)

    normalized = dict(summary)
    normalized['raw_data'] = raw_data_flat
    if 'rawData' in normalized:
        normalized['rawData'] = raw_data_flat
    if 'all_metrics' in normalized:
        normalized['all_metrics'] = filtered_all_metrics_items
    if 'allMetrics' in normalized:
        normalized['allMetrics'] = filtered_all_metrics_items
    normalized['metric_data'] = ReportUtils.flatten_metric_data(summary.get('metric_data'), category_id_to_name, metric_name_to_id)
    normalized['tag_metric_data'] = ReportUtils.flatten_tag_metric_data(summary.get('tag_metric_data'), tag_id_to_name, metric_name_to_id)
    normalized['case_type_stats'] = ReportUtils.flatten_case_type_stats(summary.get('case_type_stats'), category_id_to_name, metric_name_to_id)

    cases = summary.get('cases')
    if isinstance(cases, list):
        normalized_cases = []
        for case in cases:
            if not isinstance(case, dict):
                normalized_cases.append(case)
                continue
            new_case = dict(case)
            results = case.get('results')
            if isinstance(results, dict):
                result_rows = []
                for resource in sorted(results.keys(), key=lambda x: str(x)):
                    info = results.get(resource)
                    if not isinstance(info, dict):
                        continue
                    result_rows.append({"resource": str(resource), **info})
                new_case['results'] = result_rows

            metrics = case.get('metrics')
            if isinstance(metrics, list):
                new_case['metrics'] = metrics
            elif isinstance(metrics, dict):
                metric_groups = []
                for resource in sorted(metrics.keys(), key=lambda x: str(x)):
                    dim_values = metrics.get(resource)
                    if not isinstance(dim_values, dict):
                        continue
                    metric_list = []
                    for metric in sorted(dim_values.keys(), key=lambda x: str(x)):
                        value = dim_values.get(metric)
                        m_name = str(metric)
                        metric_list.append({"id": metric_name_to_id.get(m_name), "metric": m_name, "value": 0 if value is None else value})
                    metric_groups.append({"resource": str(resource), "metrics": metric_list})
                    new_case['metrics'] = metric_groups

            # 处理 reference_params 字段
            reference_params = case.get('reference_params')
            if isinstance(reference_params, dict) and reference_params:
                normalized_ref_params = {}
                for code, param_info in reference_params.items():
                    if not isinstance(param_info, dict):
                        continue
                    normalized_ref_params[code] = {
                        "code": param_info.get('code', code),
                        "type": param_info.get('type', 'text'),
                        "value": param_info.get('value'),
                    }
                    if param_info.get('segments'):
                        normalized_ref_params[code]["segments"] = param_info.get('segments')
                    if param_info.get('text'):
                        normalized_ref_params[code]["text"] = param_info.get('text')
                    if param_info.get('json'):
                        normalized_ref_params[code]["json"] = param_info.get('json')
                new_case['reference_params'] = normalized_ref_params

            # 处理 algorithm_results 字段
            algorithm_results = case.get('algorithm_results')
            if isinstance(algorithm_results, list) and algorithm_results:
                normalized_algo_list = []
                for item in algorithm_results:
                    if isinstance(item, dict) and item.get('value') is not None:
                        normalized_algo_list.append(item)
                new_case['algorithm_results'] = normalized_algo_list
            elif isinstance(algorithm_results, dict) and algorithm_results:
                normalized_algo_results = {}
                for resource, algo_data in algorithm_results.items():
                    if not isinstance(algo_data, dict):
                        continue
                    normalized_algo_results[resource] = {}
                    for field_key, field_value in algo_data.items():
                        if field_value is not None:
                            normalized_algo_results[resource][field_key] = field_value
                new_case['algorithm_results'] = normalized_algo_results

            # 处理 audios 字段
            audios = case.get('audios')
            if audios and isinstance(audios, list):
                normalized_audios = []
                for audio in audios:
                    if not isinstance(audio, dict):
                        continue
                    try:
                        from report_service.application.schemas.report_items import ReportAudioItem
                        audio_item = ReportAudioItem.model_validate(audio)
                        result = audio_item.model_dump(mode='json')
                        normalized_audios.append(result)
                    except Exception:
                        normalized_audios.append(audio)
                    new_case['audios'] = normalized_audios
            else:
                old_audios = []
                api_audio = case.get('api_audio')
                e2e_audio = case.get('e2e_audio')
                e2e_audios = case.get('e2e_audios', [])
                old_audio = case.get('audio')

                if api_audio and isinstance(api_audio, dict):
                    api_audio['audio_type'] = 'api'
                    old_audios.append(api_audio)
                if e2e_audio and isinstance(e2e_audio, dict):
                    e2e_audio['audio_type'] = 'e2e'
                    old_audios.append(e2e_audio)
                if isinstance(e2e_audios, list):
                    for audio in e2e_audios:
                        if isinstance(audio, dict) and audio not in old_audios:
                            audio['audio_type'] = 'e2e'
                            old_audios.append(audio)
                if old_audio and isinstance(old_audio, dict) and old_audio not in old_audios:
                    old_audio['audio_type'] = old_audio.get('audio_type', 'api')
                    old_audios.append(old_audio)
                if old_audios:
                    new_case['audios'] = old_audios

            normalized_cases.append(new_case)
        normalized['cases'] = normalized_cases

    return normalized
