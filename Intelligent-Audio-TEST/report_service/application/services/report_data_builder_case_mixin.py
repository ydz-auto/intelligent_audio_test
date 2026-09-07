# -*- coding: utf-8 -*-
"""报告数据构建器 —— 用例数据组装 Mixin。

从 report_data_builder.py 拆分而来，承载：
- _build_case_basic_info / _build_case_metrics / _build_case_data: 用例级数据组装
- _get_reference_params: 参考参数读取（result_data / 独立列 / config 兼容）
"""
from shared.utils.result_data_store import load_full_result_data
from shared.domain.algorithm_result_builder import build_algorithm_results_for_result

from report_service.application.services.report_helpers import ReportHelpers
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_algo_get_reference_params_for_report,
    _dim_id, _dim_name, _dim_type_and_parent,
)


def _obj_get(obj, key, default=None):
    """兼容 dict 与 ORM/DTO 两种对象取值。"""
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


class ReportDataCaseMixin:
    """用例级数据组装：基本信息、指标列表、参考参数。"""

    @staticmethod
    def _build_case_basic_info(tc, results, task, aux_params_map=None, dim_results_map=None):
        """构建用例基本信息。"""
        case_results = results
        test_type = 'api' if case_results and (case_results[0].get('api_id') if isinstance(case_results[0], dict) else case_results[0].api_id) else 'e2e'

        audios_list = ReportHelpers._build_audios_list(tc, mode='task')
        reference_params_dict = ReportDataCaseMixin._get_reference_params(tc, case_results, test_type)

        tc_id = tc.get('id') if isinstance(tc, dict) else tc.id
        tc_name = tc.get('name') if isinstance(tc, dict) else tc.name
        tc_desc = (tc.get('description') if isinstance(tc, dict) else tc.description) or ""
        group = tc.get('group') if isinstance(tc, dict) else getattr(tc, 'group', None)
        category = (group.get('name') if isinstance(group, dict) else getattr(group, 'name', None)) if group else "未分类"
        tc_tags = (tc.get('tags') if isinstance(tc, dict) else getattr(tc, 'tags', [])) or []
        tc_algo_type = tc.get('algorithm_type') if isinstance(tc, dict) else getattr(tc, 'algorithm_type', None)

        case_obj = {
            "id": tc_id,
            "name": tc_name,
            "description": tc_desc,
            "category": category,
            "tags": [{"name": (t.get('name') if isinstance(t, dict) else getattr(t, 'name', None))} for t in tc_tags],
            "metrics": [],
            "results": [],
            "audios": audios_list,
            "reference_params": reference_params_dict,
            "algorithm_results": [],
            "algorithm_type": tc_algo_type,
            "logs": "\n".join([(r.get('error_message') if isinstance(r, dict) else r.error_message) for r in case_results if (r.get('error_message') if isinstance(r, dict) else r.error_message)])
        }

        for result in case_results:
            resource = ReportHelpers.get_resource_name(result, task, use_time_prefix=False)

            case_obj["results"].append({
                "resource": resource,
                **ReportHelpers.build_result_info(result),
            })

            r_id = result.get('id') if isinstance(result, dict) else result.id
            result_dims = dim_results_map.get(r_id, []) if dim_results_map else []

            # 优先读取预提取的 algorithm_results（存在 result_data 里）
            result_data_raw = result.get('result_data') if isinstance(result, dict) else result.result_data
            result_data_path = result.get('result_data_path') if isinstance(result, dict) else getattr(result, 'result_data_path', None)
            result_data = load_full_result_data(result_data_raw, result_data_path)
            if not isinstance(result_data, dict):
                result_data = None

            snapshot = result_data.get('algorithm_results') if result_data else None
            if snapshot:
                # 多轮场景为快照注入轮次标记（快照预提取时不感知轮次）
                ReportDataCaseMixin._inject_snapshot_round_markers(
                    snapshot, result_dims, aux_params_map
                )
                case_obj["algorithm_results"].extend(snapshot)
                continue

            # 快照为空时回退到实时提取（兼容旧数据）
            algo_res = result.get('algorithm_result') if isinstance(result, dict) else result.algorithm_result

            if algo_res or result_data:
                algorithm_type = tc_algo_type or ''
                # 获取 output_fields（通过 gRPC 调 algorithm_service）
                output_fields = []
                if algorithm_type:
                    try:
                        from shared.clients.grpc_clients import algo_get_output_fields
                        output_fields = algo_get_output_fields(algorithm_type) or []
                    except Exception:
                        pass

                case_obj["algorithm_results"].extend(
                    build_algorithm_results_for_result(
                        result, resource, algo_res, result_data,
                        aux_params_map, result_dims,
                        output_fields, algorithm_type
                    )
                )

        return case_obj

    @staticmethod
    def _inject_snapshot_round_markers(snapshot, result_dims, aux_params_map):
        """多轮场景为快照 algorithm_results 注入轮次标记（幂等）。

        快照在任务执行时预提取，不感知轮次；此处按维度结果行的 round_number
        为 param_code 追加 @round:N / @overall 后缀，已带标记的项跳过。
        """
        is_multi_round = any(
            _obj_get(dr, 'round_number') is not None for dr in result_dims or []
        )
        if not is_multi_round:
            return

        # dimension_id -> 首个 round_number
        dim_id_to_round = {}
        for dr in result_dims:
            dim_id = _obj_get(dr, 'dimension_id')
            rn = _obj_get(dr, 'round_number')
            if dim_id is not None and dim_id not in dim_id_to_round:
                dim_id_to_round[dim_id] = rn

        # param_code -> dimension_id
        param_to_dim_id = {}
        for _did, aux_list in (aux_params_map or {}).items():
            for aux_info in aux_list:
                param_code = _obj_get(aux_info.get('param'), 'param_code')
                if param_code:
                    param_to_dim_id[param_code] = _did

        for item in snapshot:
            if not isinstance(item, dict):
                continue
            pc = item.get('param_code') or item.get('paramCode') or ''
            # 已带轮次标记的跳过
            if '@round:' in pc or '@overall' in pc:
                continue
            if not item.get('dimension_name'):
                continue
            did = param_to_dim_id.get(pc)
            rn = dim_id_to_round.get(did)
            if rn is not None:
                new_pc = f'{pc}@round:{rn + 1}'
                item['param_code'] = new_pc
                if 'paramCode' in item:
                    item['paramCode'] = new_pc
                item['label'] = f'{pc} (第{rn + 1}轮)'
                item['round_number'] = rn + 1
                if 'roundNumber' in item:
                    item['roundNumber'] = rn + 1
            else:
                new_pc = f'{pc}@overall'
                item['param_code'] = new_pc
                if 'paramCode' in item:
                    item['paramCode'] = new_pc
                item['label'] = f'{pc} (整体)'

    @staticmethod
    def _build_case_metrics(tc, results, all_dimensions, dim_results_map, task):
        """构建用例指标数据，返回 metrics_list。

        直接按维度结果行构建指标并保留 round_number；多轮场景 metric key
        追加 @overall / @round:N 后缀（与任务详情前端 isMultiRound 判断一致）。
        """
        resource_metrics_map = {}
        dim_by_id = {_dim_id(d): d for d in all_dimensions if _dim_id(d) is not None}
        dim_id_to_name = {did: _dim_name(d) for did, d in dim_by_id.items()}
        dim_name_set = {_dim_name(d) for d in all_dimensions}

        for result in results:
            resource = ReportHelpers.get_resource_name(result, task, use_time_prefix=False)
            r_id = result.get('id') if isinstance(result, dict) else result.id
            result_dims = dim_results_map.get(r_id, []) if dim_results_map else []

            # 多轮检测：存在任意非 None round_number 即多轮
            is_multi_round = any(
                _obj_get(dr, 'round_number') is not None for dr in result_dims
            )

            # 从 result_data 补充 eval_data 中的维度值
            result_data_raw = result.get('result_data') if isinstance(result, dict) else result.result_data
            result_data_path = result.get('result_data_path') if isinstance(result, dict) else getattr(result, 'result_data_path', None)
            result_data = load_full_result_data(result_data_raw, result_data_path)
            eval_data_dim_values = {}
            if result_data and isinstance(result_data, dict):
                eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
                if isinstance(eval_data, dict):
                    for eval_key, eval_val in eval_data.items():
                        # 只合并属于维度名称的键，跳过 aux 辅助参数
                        if eval_key in dim_name_set:
                            eval_data_dim_values[eval_key] = eval_val

            resource_metrics = []
            seen_dim_names = set()
            for dr in result_dims:
                dim_name = _obj_get(dr, 'dimension_name')
                dim_value = _obj_get(dr, 'dimension_value')
                seen_dim_names.add(dim_name)
                if dim_value is None and dim_name in eval_data_dim_values:
                    dim_value = eval_data_dim_values[dim_name]

                dim_obj = dim_by_id.get(_obj_get(dr, 'dimension_id'))
                if dim_obj is None and dim_name is not None:
                    dim_obj = next((d for d in all_dimensions if _dim_name(d) == dim_name), None)

                rn = _obj_get(dr, 'round_number')
                # 多轮场景：构建带轮次后缀的 metric key
                if is_multi_round:
                    metric_key = f"{dim_name}@overall" if rn is None else f"{dim_name}@round:{rn + 1}"
                else:
                    metric_key = dim_name

                dim_type, parent_dim_id = _dim_type_and_parent(dim_obj) if dim_obj else ('main', None)
                resource_metrics.append({
                    "id": _dim_id(dim_obj) if dim_obj else None,
                    "metric": metric_key,
                    "value": dim_value,
                    "round_number": rn,
                    "dimension_type": dim_type,
                    "parent_dimension_id": parent_dim_id,
                    "parent_dimension_name": dim_id_to_name.get(parent_dim_id) if parent_dim_id else None,
                })

            # 补充 eval_data 中存在但维度结果行缺失的维度
            for dim_name, dim_value in eval_data_dim_values.items():
                if dim_name in seen_dim_names or dim_value is None:
                    continue
                dim_obj = next((d for d in all_dimensions if _dim_name(d) == dim_name), None)
                dim_type, parent_dim_id = _dim_type_and_parent(dim_obj) if dim_obj else ('main', None)
                resource_metrics.append({
                    "id": _dim_id(dim_obj) if dim_obj else None,
                    "metric": dim_name,
                    "value": dim_value,
                    "round_number": None,
                    "dimension_type": dim_type,
                    "parent_dimension_id": parent_dim_id,
                    "parent_dimension_name": dim_id_to_name.get(parent_dim_id) if parent_dim_id else None,
                })

            if resource_metrics:
                if resource in resource_metrics_map:
                    resource_metrics_map[resource].extend(resource_metrics)
                else:
                    resource_metrics_map[resource] = resource_metrics

        metrics_list = []
        for resource, metrics_data in resource_metrics_map.items():
            # 按 metric key 去重：已有非 None 值则不用 None 覆盖
            deduped = {}
            for m in metrics_data:
                key = m.get('metric')
                if key not in deduped:
                    deduped[key] = m
                elif m.get('value') is not None and deduped[key].get('value') is None:
                    deduped[key] = m
            metrics_list.append({
                "resource": resource,
                "metrics": list(deduped.values())
            })

        return metrics_list

    @staticmethod
    def _build_case_data(test_cases, results, all_dimensions, dim_results_map, task):
        results_by_case = {}
        for result in results:
            tc_id = result.get('test_case_id') if isinstance(result, dict) else result.test_case_id
            if tc_id not in results_by_case:
                results_by_case[tc_id] = []
            results_by_case[tc_id].append(result)

        # 批量查询 aux 参数
        all_dim_ids = set()
        for drs in (dim_results_map.values() if dim_results_map else []):
            for dr in drs:
                dim_id = dr.get('dimension_id') if isinstance(dr, dict) else getattr(dr, 'dimension_id', None)
                if dim_id is not None:
                    all_dim_ids.add(dim_id)
        aux_params_map = ReportDataCaseMixin._get_aux_params_batch(list(all_dim_ids))

        cases = []

        for test_case in test_cases:
            tc_id = test_case.get('id') if isinstance(test_case, dict) else test_case.id
            case_results = results_by_case.get(tc_id, [])

            case_obj = ReportDataCaseMixin._build_case_basic_info(
                test_case, case_results, task,
                aux_params_map=aux_params_map, dim_results_map=dim_results_map
            )

            metrics_list = ReportDataCaseMixin._build_case_metrics(
                test_case, case_results, all_dimensions, dim_results_map, task
            )
            case_obj["metrics"] = metrics_list

            cases.append(case_obj)

        return cases

    @staticmethod
    def _get_reference_params(test_case, case_results, test_type):
        adjusted_reference_params = None
        for result in case_results:
            result_data_raw = result.get('result_data') if isinstance(result, dict) else result.result_data
            result_data_path = result.get('result_data_path') if isinstance(result, dict) else getattr(result, 'result_data_path', None)
            result_data = load_full_result_data(result_data_raw, result_data_path)
            if result_data and isinstance(result_data, dict):
                adjusted_reference_params = result_data.get('adjusted_reference_params')
                if adjusted_reference_params:
                    break

        if adjusted_reference_params:
            config_for_ref = {'reference_params': adjusted_reference_params}
        else:
            # 优先从独立列读取，兼容旧 config
            ref_col = getattr(test_case, 'reference_params', None) if not isinstance(test_case, dict) else test_case.get('reference_params')
            if ref_col:
                return _grpc_algo_get_reference_params_for_report(ref_col)
            config_for_ref = test_case.get('config') if isinstance(test_case, dict) else test_case.config

        return _grpc_algo_get_reference_params_for_report(config_for_ref)
