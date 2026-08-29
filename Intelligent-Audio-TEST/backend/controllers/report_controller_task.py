from flask import request
from backend.models.models import Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase, ReportMetricStats, Task, TestResult, TestResultDimension, Dimension, TestCase, Audio, Device, API, ReportStatus, ReportType, TaskStatus
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.error_codes import ErrorCode
from backend.utils.report.report_utils import ReportUtils
from backend.utils.web.log_handler import log_and_emit
from backend.utils.report.report_query_builder import ReportQueryBuilder
from backend.utils.common.result_data_store import load_full_result_data
from backend.utils.algorithm.reference_params_generator import ReferenceParamsGenerator
from backend.schemas.report import GenerateTaskReportRequest, ReportDetailData as ReportDetailDataSchema, ReportSummarySimplified
from datetime import datetime, timedelta, timezone
from backend.utils.common.query_utils import now_cst
from backend.controllers.report_controller_base import ReportControllerBase
from backend.services.evaluation.evaluation_utils import extract_by_path
from backend.app import socketio
import json
import traceback
import threading
import os
from concurrent.futures import ThreadPoolExecutor

_report_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='report_gen')
_generating_tasks = set()
_generating_lock = threading.Lock()


class ReportControllerTask(ReportControllerBase):
    
    @staticmethod
    def _validate_task_and_get_results(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return None, None, error_response("未找到指定任务")
        
        from backend.models.models import TaskMergeRelation
        
        if task.type == 'merged' and task.status == TaskStatus.COMPLETED.value:
            merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
            if merge_relations:
                source_task_ids = [r.source_task_id for r in merge_relations]
                results = TestResult.query.filter(TestResult.task_id.in_(source_task_ids)).all()
            else:
                results = TestResult.query.filter_by(task_id=task_id).all()
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None
            
        elif task.type == 'merged':
            merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
            if merge_relations:
                source_task_ids = [r.source_task_id for r in merge_relations]
                results = TestResult.query.filter(TestResult.task_id.in_(source_task_ids)).all()
            else:
                results = TestResult.query.filter_by(task_id=task_id).all()
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None
            
        elif task.status == TaskStatus.MERGED.value:
            merge_relations = TaskMergeRelation.query.filter_by(source_task_id=task_id).all()
            if merge_relations:
                merged_task_id = merge_relations[0].merged_task_id
                source_relations = TaskMergeRelation.query.filter_by(merged_task_id=merged_task_id).all()
                source_task_ids = [r.source_task_id for r in source_relations]
                results = TestResult.query.filter(TestResult.task_id.in_(source_task_ids)).all()
            else:
                results = TestResult.query.filter_by(task_id=task_id).all()
            if not results:
                return None, None, error_response("生成失败: 任务没有测试结果数据")
            return task, results, None
            
        elif task.status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
            return None, None, error_response("只有任务状态为completed、failed或merged时才能生成报告")
        
        results = TestResult.query.filter_by(task_id=task_id).all()
        if not results:
            return None, None, error_response("生成失败: 任务没有测试结果数据")
        
        return task, results, None

    @staticmethod
    def _get_dimension_results_batch(result_ids):
        if not result_ids:
            return {}, []
        
        dim_results = db.session.query(
            TestResultDimension.test_result_id,
            TestResultDimension.dimension_id,
            TestResultDimension.dimension_value,
            TestResultDimension.round_number,
            TestResultDimension.api_raw_response,
            Dimension.name.label('dimension_name')
        ).join(Dimension, TestResultDimension.dimension_id == Dimension.id)\
         .filter(TestResultDimension.test_result_id.in_(result_ids)).all()
        
        if not dim_results:
            return {}, []
        
        dim_results_map = {}
        dim_stats = {}
        
        for dr in dim_results:
            if dr.test_result_id not in dim_results_map:
                dim_results_map[dr.test_result_id] = []
            dim_results_map[dr.test_result_id].append(dr)
            
            if dr.dimension_id not in dim_stats:
                dim_stats[dr.dimension_id] = {
                    "name": dr.dimension_name,
                    "total_dimension_value": 0,
                    "count": 0
                }
            dim_stats[dr.dimension_id]["total_dimension_value"] += dr.dimension_value or 0
            dim_stats[dr.dimension_id]["count"] += 1
        
        return dim_results_map, dim_stats

    @staticmethod
    def _get_resource_result_types_batch(task_id_or_ids, device_ids, api_ids):
        device_result_types = {}
        api_result_types = {}
        
        if isinstance(task_id_or_ids, list):
            task_id_filter = TestResult.task_id.in_(task_id_or_ids)
        else:
            task_id_filter = TestResult.task_id == task_id_or_ids
        
        if device_ids:
            device_results = TestResult.query.filter(
                task_id_filter,
                TestResult.device_id.in_(device_ids)
            ).all()
            
            for result in device_results:
                if result.device_id and result.result_data:
                    full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                    result_type = ReportControllerTask._extract_result_type(full_data)
                    device_result_types[result.device_id] = result_type
        
        if api_ids:
            api_results = TestResult.query.filter(
                task_id_filter,
                TestResult.api_id.in_(api_ids)
            ).all()
            
            for result in api_results:
                if result.api_id and result.result_data:
                    full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                    result_type = ReportControllerTask._extract_result_type(full_data)
                    api_result_types[result.api_id] = result_type
        
        return device_result_types, api_result_types

    @staticmethod
    def _extract_result_type(result_data):
        if not result_data:
            return 'default'
        try:
            if isinstance(result_data, str) and result_data.strip():
                result_data_dict = json.loads(result_data)
            elif isinstance(result_data, dict):
                result_data_dict = result_data
            else:
                return 'default'
            return result_data_dict.get('result_type', 'default') if isinstance(result_data_dict, dict) else 'default'
        except Exception:
            return 'default'

    @staticmethod
    def _get_aux_params_batch(dim_ids):
        """批量查询维度的 aux output 参数（visible_in_report=True）
        返回 {dimension_id: [(param, dimension_name), ...]}
        """
        if not dim_ids:
            return {}
        from backend.models.algorithm_models import EvaluationDimensionParam
        aux_params = db.session.query(
            EvaluationDimensionParam,
            Dimension.name.label('dimension_name')
        ).join(Dimension, EvaluationDimensionParam.dimension_id == Dimension.id)\
         .filter(
            EvaluationDimensionParam.dimension_id.in_(dim_ids),
            EvaluationDimensionParam.param_direction == 'output',
            EvaluationDimensionParam.output_role == 'aux',
            EvaluationDimensionParam.visible_in_report == True,
            EvaluationDimensionParam.deleted == False
        ).all()
        aux_map = {}
        for row in aux_params:
            p = row[0]
            dim_name = row[1]
            if p.dimension_id not in aux_map:
                aux_map[p.dimension_id] = []
            aux_map[p.dimension_id].append({
                'param': p,
                'dimension_name': dim_name
            })
        return aux_map

    @staticmethod
    def _build_case_data(test_cases, results, all_dimensions, dim_results_map, task):
        results_by_case = {}
        for result in results:
            if result.test_case_id not in results_by_case:
                results_by_case[result.test_case_id] = []
            results_by_case[result.test_case_id].append(result)

        # 批量查询 aux 参数
        all_dim_ids = set()
        for drs in dim_results_map.values():
            for dr in drs:
                all_dim_ids.add(dr.dimension_id)
        aux_params_map = ReportControllerTask._get_aux_params_batch(list(all_dim_ids))

        # 维度ID→名称映射，用于补充 parent_dimension_name
        dim_id_to_name = {dim.id: dim.name for dim in all_dimensions}

        cases = []
        
        for test_case in test_cases:
            case_results = results_by_case.get(test_case.id, [])
            resource_metrics_map = {}
            test_type = 'api' if case_results and case_results[0].api_id else 'e2e'
            
            audios_list = ReportControllerBase._build_audios_list(test_case, mode='task')
            reference_params_dict = ReportControllerTask._get_reference_params(test_case, case_results, test_type)
            
            for result in case_results:
                resource = ReportControllerBase.get_resource_name(result, task, use_time_prefix=False)

                # 直接从 dim_results_map 构建带轮次信息的指标，保留 round_number
                result_dims = dim_results_map.get(result.id, [])
                # 检测多轮：只要存在任何非 None 的 round_number 即为多轮
                # 与任务详情前端的 isMultiRound 判断逻辑保持一致
                is_multi_round = any(dr.round_number is not None for dr in result_dims)

                # 从 result_data 补充 eval_data 中的维度值
                result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                eval_data_dim_values = {}
                if result_data and isinstance(result_data, dict):
                    eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
                    if isinstance(eval_data, dict):
                        dim_name_set = {d.name for d in all_dimensions}
                        for eval_key, eval_val in eval_data.items():
                            if eval_key in dim_name_set:
                                eval_data_dim_values[eval_key] = eval_val

                resource_metrics = []
                # 按 (dim_name, round_number) 分组处理
                for dr in result_dims:
                    dim_name = dr.dimension_name
                    dim_value = dr.dimension_value
                    if dim_value is None and dim_name in eval_data_dim_values:
                        dim_value = eval_data_dim_values[dim_name]

                    dim_obj = None
                    for dim in all_dimensions:
                        if dim.name == dim_name:
                            dim_obj = dim
                            break

                    rn = dr.round_number
                    # 多轮场景：构建带轮次后缀的 metric key
                    if is_multi_round:
                        if rn is None:
                            metric_key = f"{dim_name}@overall"
                        else:
                            metric_key = f"{dim_name}@round:{rn + 1}"
                    else:
                        metric_key = dim_name

                    resource_metrics.append({
                        "id": dim_obj.id if dim_obj else None,
                        "metric": metric_key,
                        "value": dim_value,
                        "round_number": rn,
                        "dimension_type": dim_obj.dimension_type if dim_obj else 'main',
                        "parent_dimension_id": dim_obj.parent_dimension_id if dim_obj else None,
                        "parent_dimension_name": dim_id_to_name.get(dim_obj.parent_dimension_id) if dim_obj and dim_obj.parent_dimension_id else None
                    })

                # 补充 eval_data 中存在但 dim_results_map 中缺失的维度
                seen_dim_names = {dr.dimension_name for dr in result_dims}
                for dim_name, dim_value in eval_data_dim_values.items():
                    if dim_name in seen_dim_names:
                        continue
                    if dim_value is None:
                        continue
                    dim_obj = None
                    for dim in all_dimensions:
                        if dim.name == dim_name:
                            dim_obj = dim
                            break
                    resource_metrics.append({
                        "id": dim_obj.id if dim_obj else None,
                        "metric": dim_name,
                        "value": dim_value,
                        "round_number": None,
                        "dimension_type": dim_obj.dimension_type if dim_obj else 'main',
                        "parent_dimension_id": dim_obj.parent_dimension_id if dim_obj else None,
                        "parent_dimension_name": dim_id_to_name.get(dim_obj.parent_dimension_id) if dim_obj and dim_obj.parent_dimension_id else None
                    })

                if resource_metrics:
                    if resource in resource_metrics_map:
                        resource_metrics_map[resource].extend(resource_metrics)
                    else:
                        resource_metrics_map[resource] = resource_metrics

            metrics_list = []
            for resource, metrics_data in resource_metrics_map.items():
                # 按 metric key 去重：优先保留非 None 值，如已有非 None 值则不用 None 覆盖
                deduped = {}
                for m in metrics_data:
                    key = m.get('metric')
                    if key not in deduped:
                        deduped[key] = m
                    else:
                        existing_val = deduped[key].get('value')
                        new_val = m.get('value')
                        # 新值非 None 且旧值为 None 时覆盖；旧值非 None 时保留
                        if new_val is not None and existing_val is None:
                            deduped[key] = m
                metrics_list.append({
                    "resource": resource,
                    "metrics": list(deduped.values())
                })
            
            case_obj = {
                "id": test_case.id,
                "name": test_case.name,
                "description": test_case.description or "",
                "category": test_case.group.name if test_case.group else "未分类",
                "tags": [{"name": tag.name} for tag in (getattr(test_case, 'tags', []) or [])],
                "metrics": metrics_list,
                "results": [],
                "audios": audios_list,
                "reference_params": reference_params_dict,
                "algorithm_results": [],
                "algorithm_type": test_case.algorithm_type,
                "logs": "\n".join([result.error_message for result in case_results if result.error_message])
            }
            
            for result in case_results:
                resource = ReportControllerBase.get_resource_name(result, task, use_time_prefix=False)
                
                case_obj["results"].append({
                    "resource": resource,
                    **ReportControllerBase.build_result_info(result),
                })
                
                # 优先读取预提取的 algorithm_results（存在 result_data 里）
                result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                if not isinstance(result_data, dict):
                    result_data = None

                snapshot = result_data.get('algorithm_results') if result_data else None
                if snapshot:
                    # 对快照注入轮次标记（快照中的评估结果字段需要带上 @round:N）
                    result_dims = dim_results_map.get(result.id, [])
                    is_multi_round = any(getattr(dr, 'round_number', None) is not None for dr in result_dims)
                    if is_multi_round:
                        # 构建 dimension_id → round_number 映射
                        dim_id_to_round = {}
                        for dr in result_dims:
                            dim_id = getattr(dr, 'dimension_id', None)
                            rn = getattr(dr, 'round_number', None)
                            if dim_id is not None and dim_id not in dim_id_to_round:
                                dim_id_to_round[dim_id] = rn
                        # 构建 param_code → dimension_id 映射
                        param_to_dim_id = {}
                        for _dim_id, aux_list in aux_params_map.items():
                            for aux_info in aux_list:
                                p = aux_info['param']
                                param_to_dim_id[p.param_code] = _dim_id
                        # 遍历快照，给有 dimension_name 但没有轮次标记的字段注入 @round:N
                        for item in snapshot:
                            if not isinstance(item, dict):
                                continue
                            pc = item.get('param_code') or item.get('paramCode') or ''
                            # 已经有轮次标记的跳过
                            if '@round:' in pc or '@overall' in pc:
                                continue
                            dim_name = item.get('dimension_name')
                            if not dim_name:
                                continue
                            # 通过 param_code 查 dimension_id，再查 round_number
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
                    case_obj["algorithm_results"].extend(snapshot)
                    continue

                # 快照为空时回退到实时提取（兼容旧数据）
                algo_res = result.algorithm_result

                if algo_res or result_data:
                    algorithm_type = getattr(test_case, 'algorithm_type', '') or ''
                    from backend.utils.algorithm.algorithm_result_field_mapper import AlgorithmResultFieldMapper
                    output_fields = AlgorithmResultFieldMapper.get_output_fields(algorithm_type) if algorithm_type else []

                    case_obj["algorithm_results"].extend(
                        ReportControllerTask.build_algorithm_results_for_result(
                            result, resource, algo_res, result_data,
                            aux_params_map, dim_results_map.get(result.id, []),
                            output_fields, algorithm_type
                        )
                    )
            
            cases.append(case_obj)

        return cases

    # 设备/API 原始执行结果字段定义（两处共用）
    _DEVICE_FIELDS = {
        'start_ms': 'timestamp',
        'end_ms': 'timestamp',
        'first_frame_ms': 'timestamp',
        'record_file': 'audio_file',
        'record_path': 'audio_file',
        'user_wav': 'audio_file',
        'ai_wav': 'audio_file',
        'wav_path': 'audio_file',
        'question': 'text',
        'answer': 'text',
        'success': 'boolean',
        'message': 'text',
    }

    @staticmethod
    def build_algorithm_results_for_result(
        result, resource, algo_res, result_data, aux_params_map,
        dim_result_rows, output_fields, algorithm_type
    ):
        """为单个 TestResult 构建 algorithm_results 扁平列表。

        合并 aux 辅助参数 + 设备/API 原始结果，供报告页和详情页共用。

        Args:
            result: TestResult 对象（仅用于取 result.id）
            resource: 设备/API 名称
            algo_res: algorithm_result (dict)
            result_data: 完整 result_data (dict 或 None)
            aux_params_map: {dimension_id: [{param, dimension_name}, ...]}
            dim_result_rows: 该 TestResult 的 TestResultDimension 行列表
            output_fields: AlgorithmResultFieldMapper.get_output_fields() 结果
            algorithm_type: 算法类型

        Returns:
            list[dict]: algorithm_results 扁平列表
        """
        from backend.services.evaluation.evaluation_utils import extract_by_path

        algorithm_results = []

        if not (algo_res or result_data):
            return algorithm_results

        # ── 1. 构建 param_code → (dimension_name, dimension_id, field_type) 映射 ──
        param_to_dim = {}
        param_to_type = {}
        param_to_dim_id = {}
        for _dim_id, aux_list in aux_params_map.items():
            for aux_info in aux_list:
                p = aux_info['param']
                param_to_dim[p.param_code] = aux_info['dimension_name']
                param_to_type[p.param_code] = p.field_type
                param_to_dim_id[p.param_code] = _dim_id

        # 构建 dimension_id → round_number 映射（从 TRD 行中提取）
        dim_id_to_round = {}
        for dr in dim_result_rows:
            dim_id = getattr(dr, 'dimension_id', None)
            rn = getattr(dr, 'round_number', None)
            if dim_id is not None and dim_id not in dim_id_to_round:
                dim_id_to_round[dim_id] = rn

        # 判断是否多轮场景（任一 dim_result_row 有非 None 的 round_number）
        is_multi_round = any(getattr(dr, 'round_number', None) is not None for dr in dim_result_rows)

        # ── 2. 提取 aux 辅助参数值 ──
        # aux_values: {param_code: value}
        # aux_round_map: {param_code: round_number}（None=overall, int=具体轮次）
        aux_values = {}
        aux_round_map = {}

        # 2a. 从 evaluation_data 提取
        if result_data:
            eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
            if isinstance(eval_data, dict):
                for param_code in param_to_dim:
                    if param_code in eval_data:
                        aux_values[param_code] = eval_data[param_code]
                        # 从 dimension_id → round_number 映射获取轮次
                        did = param_to_dim_id.get(param_code)
                        aux_round_map[param_code] = dim_id_to_round.get(did)

        # 2b. 从 api_raw_response 补充（继承 dim_result_row 的 round_number）
        for dr in dim_result_rows:
            raw_resp = getattr(dr, 'api_raw_response', None)
            if not raw_resp:
                continue
            if isinstance(raw_resp, str):
                try:
                    raw_resp = json.loads(raw_resp)
                except Exception:
                    continue
            dr_round = getattr(dr, 'round_number', None)
            for aux_info in aux_params_map.get(dr.dimension_id, []):
                p = aux_info['param']
                param_code = p.param_code
                if param_code in aux_values:
                    continue
                value = extract_by_path(raw_resp, p.field_path)
                if value is not None:
                    aux_values[param_code] = value
                    aux_round_map[param_code] = dr_round

        # 输出 aux 参数
        for param_code, param_value in aux_values.items():
            if param_value is None:
                continue
            rn = aux_round_map.get(param_code)
            # 多轮场景下，给 param_code 加上轮次后缀
            if is_multi_round:
                if rn is not None:
                    out_code = f'{param_code}@round:{rn + 1}'
                    out_label = f'{param_code} (第{rn + 1}轮)'
                    out_round_number = rn + 1
                else:
                    out_code = f'{param_code}@overall'
                    out_label = f'{param_code} (整体)'
                    out_round_number = None
            else:
                out_code = param_code
                out_label = param_code
                out_round_number = None
            algorithm_results.append({
                'device': resource,
                'param_code': out_code,
                'param_type': param_to_type.get(param_code, 'text'),
                'label': out_label,
                'value': param_value,
                'round_number': out_round_number,
                'dimension_name': param_to_dim.get(param_code),
            })

        # ── 3. 提取设备/API 原始执行结果 ──
        combined_data = {**(algo_res or {}), **(result_data or {})}

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
                                    sub_type = ReportControllerTask._DEVICE_FIELDS.get(sub_key, 'text')
                                    if sub_type == 'audio_file' and isinstance(val, str) and val:
                                        val = ReportControllerTask._normalize_audio_path(val)
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
                        'param_type': field.get('param_type', 'json'),
                        'label': field.get('dimension_name') or param_key,
                        'value': combined_data[param_key],
                        'dimension_name': None,
                    })
                else:
                    algorithm_results.append({
                        'device': resource,
                        'param_code': param_key,
                        'param_type': field.get('param_type', 'text'),
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
                    'param_type': field.get('param_type', 'text'),
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
                            if k in ReportControllerTask._DEVICE_FIELDS and v is not None:
                                device_values[k] = v
                agg = algo_res.get('aggregated') or {}
                if isinstance(agg, dict):
                    for k, v in agg.items():
                        if v is not None:
                            agg_type = 'number' if isinstance(v, (int, float)) else 'text'
                            device_values['agg_' + k] = {'value': v, 'type': agg_type}

            if result_data:
                rrl = result_data.get('raw_results_list') or []
                if rrl and isinstance(rrl, list) and isinstance(rrl[0], dict):
                    raw_item = rrl[0]
                    raw_res = raw_item.get('raw_results') or {}
                    if isinstance(raw_res, dict):
                        for k, v in raw_res.items():
                            if k in ReportControllerTask._DEVICE_FIELDS and v is not None and k not in device_values:
                                device_values[k] = v
                    for k in ['round_number', 'success']:
                        if k in raw_item and raw_item[k] is not None and k not in device_values:
                            device_values[k] = raw_item[k]

            existing_codes = {item['param_code'] for item in algorithm_results if item['device'] == resource}
            for param_code, param_value in device_values.items():
                if param_value is None or param_value == '':
                    continue
                if param_code in existing_codes:
                    continue
                if param_code.startswith('agg_') and isinstance(param_value, dict) and 'value' in param_value:
                    actual_value = param_value['value']
                    param_type = param_value.get('type', 'text')
                else:
                    actual_value = param_value
                    param_type = ReportControllerTask._DEVICE_FIELDS.get(param_code, 'text')
                if param_type == 'audio_file' and isinstance(actual_value, str) and actual_value:
                    actual_value = ReportControllerTask._normalize_audio_path(actual_value)
                algorithm_results.append({
                    'device': resource,
                    'param_code': param_code,
                    'param_type': param_type,
                    'label': param_code,
                    'value': actual_value,
                    'dimension_name': None,
                })

        return algorithm_results

    @staticmethod
    def _normalize_audio_path(abs_path):
        """将音频文件的绝对路径转换为相对 STATIC_BASE_PATH 的相对路径。
        兼容符号链接/junction：用 os.path.commonpath 比较规范化后的路径。
        如果路径不在 STATIC_BASE_PATH 下，原样返回。
        """
        try:
            from flask import current_app
            static_base = current_app.config.get('STATIC_BASE_PATH')
            if not static_base:
                return abs_path
            # 用 realpath 解析符号链接后比较
            real_abs = os.path.realpath(abs_path)
            real_base = os.path.realpath(static_base)
            common = os.path.commonpath([real_abs, real_base])
            if common == real_base:
                rel = os.path.relpath(real_abs, real_base)
                # 统一使用正斜杠，避免前端 URL 编码问题
                return rel.replace('\\', '/')
        except Exception:
            pass
        return abs_path

    @staticmethod
    def _get_reference_params(test_case, case_results, test_type):
        adjusted_reference_params = None
        for result in case_results:
            result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
            if result_data and isinstance(result_data, dict):
                adjusted_reference_params = result_data.get('adjusted_reference_params')
                if adjusted_reference_params:
                    break
        
        if adjusted_reference_params:
            config_for_ref = {'reference_params': adjusted_reference_params}
        else:
            # 优先从独立列读取，兼容旧 config
            ref_col = getattr(test_case, 'reference_params', None)
            if ref_col:
                return ReferenceParamsGenerator.get_reference_params_for_report(ref_col)
            config_for_ref = test_case.config

        return ReferenceParamsGenerator.get_reference_params_for_report(config_for_ref)

    @staticmethod
    def _build_resources_list(devices, apis, task, device_result_types, api_result_types):
        resources = []
        
        for d in devices:
            result_type = device_result_types.get(d.id, 'default')
            
            class TempResult:
                def __init__(self, device_id, result_type):
                    self.device_id = device_id
                    self.api_id = None
                    self.result_data = {"result_type": result_type}
            
            resource = ReportControllerBase.get_resource_name(TempResult(d.id, result_type), task, use_time_prefix=False)
            resources.append(resource)
        
        for a in apis:
            result_type = api_result_types.get(a.id, 'default')
            
            class TempResult:
                def __init__(self, api_id, result_type):
                    self.api_id = api_id
                    self.device_id = None
                    self.result_data = {"result_type": result_type}
            
            resource = ReportControllerBase.get_resource_name(TempResult(a.id, result_type), task, use_time_prefix=False)
            resources.append(resource)
        
        return resources

    @staticmethod
    def _get_source_task_ids(task):
        if task.type == 'merged' and task.status == TaskStatus.COMPLETED.value:
            from backend.models.models import TaskMergeRelation
            merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task.id).all()
            return [r.source_task_id for r in merge_relations]
        return []

    @staticmethod
    def _get_task_resources(task_ids):
        from backend.models.models import TaskDevice, Device, TaskAPI, API
        
        if isinstance(task_ids, int):
            task_ids = [task_ids]
        
        task_devices = TaskDevice.query.filter(TaskDevice.task_id.in_(task_ids)).all()
        device_ids = list(set([td.device_id for td in task_devices]))
        devices = Device.query.filter(Device.id.in_(device_ids)).all() if device_ids else []
        devices_list = [ReportUtils.serialize_device(d) for d in devices if d]
        
        task_apis = TaskAPI.query.filter(TaskAPI.task_id.in_(task_ids)).all()
        api_ids = list(set([ta.api_id for ta in task_apis]))
        apis = API.query.filter(API.id.in_(api_ids)).all() if api_ids else []
        apis_list = [ReportUtils.serialize_api(a) for a in apis if a]
        
        return devices_list, apis_list, device_ids, api_ids

    @staticmethod
    def _get_task_test_cases(task_ids):
        from backend.models.models import TaskCase
        from sqlalchemy.orm import joinedload
        
        if isinstance(task_ids, int):
            task_ids = [task_ids]
        
        task_cases = TaskCase.query.filter(TaskCase.task_id.in_(task_ids)).all()
        test_case_ids = list(set([tc.test_case_id for tc in task_cases]))
        test_cases = TestCase.query.options(
            joinedload(TestCase.tags),
            joinedload(TestCase.group)
        ).filter(TestCase.id.in_(test_case_ids)).all()
        return test_cases, test_case_ids

    @staticmethod
    def _calculate_summary_dimensions(dim_stats):
        summary_dim_values = []
        for d_id, stat in dim_stats.items():
            avg_value = (stat["total_dimension_value"] / stat["count"]) if stat["count"] > 0 else 0
            summary_dim_values.append({
                "id": d_id,
                "name": stat["name"],
                "average_value": avg_value
            })
        return summary_dim_values

    @staticmethod
    def _build_all_metrics(all_dimensions):
        # 构建维度ID→名称映射，用于查找父维度名
        dim_id_to_name = {dim.id: dim.name for dim in all_dimensions}
        all_metrics = []
        for dim in all_dimensions:
            statistic_method = dim.statistic_method or "average"
            # 聚合方式决定 unit：pass_rate 产出百分比，强制为 %；其余用维度配置的 score_unit
            if statistic_method == 'pass_rate':
                unit = "%"
            else:
                unit = dim.score_unit if dim.score_unit and dim.score_unit.strip() else ""
            decimal_places = dim.decimal_places if dim.decimal_places is not None else 2
            all_metrics.append({
                "id": dim.id,
                "name": dim.name,
                "unit": unit,
                "decimal_places": decimal_places,
                "statistic_method": statistic_method,
                "dimension_type": dim.dimension_type or 'main',
                "parent_dimension_id": dim.parent_dimension_id,
                "parent_dimension_name": dim_id_to_name.get(dim.parent_dimension_id) if dim.parent_dimension_id else None
            })
        return all_metrics

    @staticmethod
    def _create_report_record(name, task_id, description):
        new_report = Report(
            name=name,
            type=ReportType.TASK.value,
            task_id=task_id,
            description=description,
            status=ReportStatus.DRAFT.value
        )
        db.session.add(new_report)
        db.session.flush()
        return new_report

    @staticmethod
    def _create_report_summary(report_id, task, summary):
        total_cases = summary.get('total_cases', 0)
        completed_cases = summary.get('completed_cases', 0)
        
        summary_info = ReportSummary(
            report_id=report_id,
            total_cases=total_cases,
            completed_cases=completed_cases,
            failed_cases=summary.get('failed_cases', 0),
            pass_rate=round((completed_cases / total_cases * 100), 2) if total_cases > 0 else 0,
            duration=task.actual_duration,
            started_at=task.started_at,
            completed_at=task.completed_at
        )
        db.session.add(summary_info)

        summary_meta = ReportSummaryMeta(
            report_id=report_id,
            dimension_values=json.dumps(summary.get('dimension_values', []), ensure_ascii=False),
            case_categories=json.dumps(summary.get('case_categories', []), ensure_ascii=False),
            all_case_tags=json.dumps(summary.get('all_case_tags', []), ensure_ascii=False),
            devices=json.dumps(summary.get('devices', []), ensure_ascii=False),
            apis=json.dumps(summary.get('apis', []), ensure_ascii=False),
            resources=json.dumps(summary.get('resources', []), ensure_ascii=False),
            resource_headers=json.dumps(summary.get('resource_headers', []), ensure_ascii=False),
            all_metrics=json.dumps(summary.get('all_metrics', []), ensure_ascii=False),
            field_mappings=json.dumps(summary.get('field_mappings', {}), ensure_ascii=False)
        )
        db.session.add(summary_meta)
        
        return summary_info, summary_meta

    @staticmethod
    def _create_report_detail_data(report_id, summary):
        raw_data_record = ReportRawData(
            report_id=report_id,
            raw_data=json.dumps(summary.get('raw_data', []), ensure_ascii=False)
        )
        db.session.add(raw_data_record)

        cases = summary.get('cases', [])
        if isinstance(cases, str):
            cases = json.loads(cases)
        for case_item in cases:
            if not isinstance(case_item, dict):
                continue
            case_record = ReportCase(
                report_id=report_id,
                test_case_id=case_item.get('id'),
                name=case_item.get('name'),
                description=case_item.get('description'),
                category=case_item.get('category'),
                tags=case_item.get('tags'),
                metrics=case_item.get('metrics'),
                results=case_item.get('results'),
                audios=case_item.get('audios'),
                reference_params=case_item.get('reference_params'),
                algorithm_results=case_item.get('algorithm_results'),
                algorithm_type=case_item.get('algorithm_type'),
                logs=case_item.get('logs')
            )
            db.session.add(case_record)

        metric_stats_record = ReportMetricStats(
            report_id=report_id,
            metric_data=json.dumps(summary.get('metric_data', []), ensure_ascii=False),
            tag_metric_data=json.dumps(summary.get('tag_metric_data', []), ensure_ascii=False),
            tag_category_metric_data=json.dumps(summary.get('tag_category_metric_data', {}), ensure_ascii=False),
            case_type_stats=json.dumps(summary.get('case_type_stats', []), ensure_ascii=False),
            device_stats=json.dumps(summary.get('device_stats', []), ensure_ascii=False),
            api_stats=json.dumps(summary.get('api_stats', []), ensure_ascii=False)
        )
        db.session.add(metric_stats_record)
        
        return raw_data_record, metric_stats_record

    @staticmethod
    def _build_response(report, task, summary_info, summary_meta, raw_data_record, metric_stats_record):
        def to_json(val):
            if val is None:
                return []
            if isinstance(val, (list, dict)):
                return val
            if isinstance(val, str):
                return json.loads(val)
            return val if isinstance(val, list) else []

        simplified_summary = ReportSummarySimplified(
            raw_data=to_json(raw_data_record.raw_data) if raw_data_record else [],
            metric_data=to_json(metric_stats_record.metric_data) if metric_stats_record else [],
            tag_metric_data=to_json(metric_stats_record.tag_metric_data) if metric_stats_record else [],
            case_categories=to_json(summary_meta.case_categories) if summary_meta else [],
            all_case_tags=to_json(summary_meta.all_case_tags) if summary_meta else [],
            resources=to_json(summary_meta.resources) if summary_meta else [],
            resource_headers=to_json(summary_meta.resource_headers) if summary_meta else [],
            all_metrics=to_json(summary_meta.all_metrics) if summary_meta else [],
            field_mappings=to_json(summary_meta.field_mappings) if summary_meta else {},
            device_stats=to_json(metric_stats_record.device_stats) if metric_stats_record else [],
            api_stats=to_json(metric_stats_record.api_stats) if metric_stats_record else [],
            case_type_stats=to_json(metric_stats_record.case_type_stats) if metric_stats_record else [],
            devices=to_json(summary_meta.devices) if summary_meta else [],
            apis=to_json(summary_meta.apis) if summary_meta else [],
            total_cases=summary_info.total_cases if summary_info else 0,
            completed_cases=summary_info.completed_cases if summary_info else 0,
            failed_cases=summary_info.failed_cases if summary_info else 0
        )

        response_schema = ReportDetailDataSchema(
            id=report.id,
            name=report.name,
            type=report.type,
            task_id=report.task_id,
            task_name=task.name if task else "对比报告/趋势报告",
            summary=simplified_summary,
            description=report.description,
            status=report.status,
            analysis=report.analysis,
            created_at=report.created_at.isoformat() if report.created_at else None,
            updated_at=report.updated_at.isoformat() if report.updated_at else None
        )

        return response_schema.model_dump(by_alias=True)

    def generate_task_report():
        try:
            validated_data = GenerateTaskReportRequest.model_validate(request.get_json())
        except Exception as e:
            log_and_emit('ERROR', 'report', f'[generate_task_report] Validation error: {e}\n{traceback.format_exc()}')
            return error_response(f"请求参数错误: {str(e)}")

        task_id = validated_data.task_id
        name = validated_data.name
        description = validated_data.description

        log_and_emit('DEBUG', 'report', f'[generate_task_report] Starting task_id={task_id}', task_id=task_id)

        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到指定任务")

        existing_report = Report.query.filter_by(task_id=task_id).first()
        if existing_report:
            return success_response({"id": existing_report.id, "status": "exists"}, "任务报告已存在", ErrorCode.SUCCESS)

        if task.status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value]:
            return error_response("只有任务状态为completed、failed或merged时才能生成报告")

        with _generating_lock:
            if task_id in _generating_tasks:
                return success_response({"taskId": task_id, "status": "generating"}, "报告正在生成中", ErrorCode.SUCCESS)
            _generating_tasks.add(task_id)

        log_and_emit('INFO', 'report', f'[generate_task_report] Submitting async task for task_id={task_id}', task_id=task_id)
        _report_executor.submit(
            ReportControllerTask._generate_task_report_async,
            task_id, name, description
        )
        log_and_emit('INFO', 'report', f'[generate_task_report] Async task submitted for task_id={task_id}', task_id=task_id)

        return success_response({"taskId": task_id, "status": "generating"}, "报告生成中，请稍后刷新", ErrorCode.SUCCESS)

    @staticmethod
    def regenerate_report(report_id):
        """重新生成报告：删除旧报告数据，基于原 task_id 重新生成"""
        report = db.session.get(Report, report_id)
        if not report:
            return error_response("未找到测试报告", 404)

        if report.type != ReportType.TASK.value:
            return error_response("仅支持任务报告重新生成")

        task_id = report.task_id
        if not task_id:
            return error_response("报告未关联任务，无法重新生成")

        # 获取原报告名称和描述
        name = report.name
        description = report.description

        # 检查是否正在生成
        with _generating_lock:
            if task_id in _generating_tasks:
                return success_response({"taskId": task_id, "status": "generating"}, "报告正在生成中", ErrorCode.SUCCESS)
            _generating_tasks.add(task_id)

        try:
            # 删除旧报告（级联删除 summary_meta, raw_data, cases, metric_stats 等）
            db.session.delete(report)
            db.session.commit()
            log_and_emit('INFO', 'report', f'[regenerate_report] Deleted old report {report_id}, regenerating for task_id={task_id}', task_id=task_id)
        except Exception as e:
            db.session.rollback()
            with _generating_lock:
                _generating_tasks.discard(task_id)
            log_and_emit('ERROR', 'report', f'[regenerate_report] Failed to delete old report: {e}', task_id=task_id)
            return error_response("删除旧报告失败，请稍后重试")

        # 异步重新生成
        _report_executor.submit(
            ReportControllerTask._generate_task_report_async,
            task_id, name, description
        )
        log_and_emit('INFO', 'report', f'[regenerate_report] Async task submitted for task_id={task_id}', task_id=task_id)

        return success_response({"taskId": task_id, "status": "generating"}, "报告重新生成中，请稍后刷新", ErrorCode.SUCCESS)

    @staticmethod
    def _generate_task_report_async(task_id, name, description):
        from backend.app import app as flask_app
        if flask_app is None:
            log_and_emit('ERROR', 'report', f'[generate_task_report_async] Flask app is None, cannot create context', task_id=task_id)
            with _generating_lock:
                _generating_tasks.discard(task_id)
            socketio.emit('report_generated', {
                'taskId': task_id,
                'success': False,
                'error': '服务器内部错误'
            })
            return
            
        with flask_app.app_context():
            try:
                log_and_emit('INFO', 'report', f'[generate_task_report_async] Starting for task_id={task_id}', task_id=task_id)

                task, results, error = ReportControllerTask._validate_task_and_get_results(task_id)
                if error:
                    with _generating_lock:
                        _generating_tasks.discard(task_id)
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'success': False,
                        'error': '任务验证失败'
                    })
                    return

                existing_report = Report.query.filter_by(task_id=task_id).first()
                if existing_report:
                    with _generating_lock:
                        _generating_tasks.discard(task_id)
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'reportId': existing_report.id,
                        'success': True,
                        'status': 'exists'
                    })
                    return

                if not name:
                    name = f"任务报告_{task.name}_{now_cst().strftime('%Y%m%d%H%M%S')}"

                source_task_ids = ReportControllerTask._get_source_task_ids(task)
                task_ids_for_query = source_task_ids if source_task_ids else [task_id]

                total_cases = task.total_cases
                completed_cases = task.completed_cases - task.failed_cases
                failed_cases = task.failed_cases
                success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

                res_ids = [r.id for r in results]
                
                dim_results_map, dim_stats = ReportControllerTask._get_dimension_results_batch(res_ids)
                
                if not dim_results_map:
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'success': False,
                        'error': '未找到维度得分数据'
                    })
                    return

                all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
                summary_dim_values = ReportControllerTask._calculate_summary_dimensions(dim_stats)

                if dim_stats:
                    all_dimensions = [d for d in all_dimensions_all if d.id in dim_stats]
                else:
                    all_dimensions = all_dimensions_all

                test_cases, test_case_ids = ReportControllerTask._get_task_test_cases(task_ids_for_query)
                devices_list, apis_list, device_ids, api_ids = ReportControllerTask._get_task_resources(task_ids_for_query)

                device_result_types, api_result_types = ReportControllerTask._get_resource_result_types_batch(
                    task_ids_for_query, device_ids, api_ids
                )
                
                resources = ReportControllerTask._build_resources_list(
                    [d for d in Device.query.filter(Device.id.in_(device_ids)).all()] if device_ids else [],
                    [a for a in API.query.filter(API.id.in_(api_ids)).all()] if api_ids else [],
                    task, device_result_types, api_result_types
                )

                all_metrics = ReportControllerTask._build_all_metrics(all_dimensions)

                if not devices_list and not apis_list:
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'success': False,
                        'error': '任务没有关联任何设备或API'
                    })
                    return

                if not all_metrics:
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'success': False,
                        'error': '任务没有关联任何评估维度'
                    })
                    return

                tasks_map = {task.id: task}
                if source_task_ids:
                    source_tasks = Task.query.filter(Task.id.in_(source_task_ids)).all()
                    for st in source_tasks:
                        tasks_map[st.id] = st
                
                core_metrics = ReportUtils.calculate_core_metrics(
                    results=results,
                    all_dimensions=all_dimensions,
                    resources=resources,
                    dim_results_map=dim_results_map,
                    tasks_map=tasks_map,
                    use_time_prefix=False
                )
                
                metric_data = core_metrics['metric_data']
                tag_metric_data = core_metrics['tag_metric_data']
                raw_data = core_metrics['raw_data']
                case_type_stats = core_metrics['case_type_stats']
                resources = core_metrics['resources']
                
                resource_headers = ReportUtils.build_resource_headers(
                    resources=resources,
                    results=results,
                    tasks_map=tasks_map,
                    use_time_prefix=False,
                )

                device_stats, api_stats = ReportUtils.calculate_device_api_stats(
                    results=results,
                    all_dimensions=all_dimensions,
                    dim_results_map=dim_results_map,
                    dim_statistic_method={dim.name: getattr(dim, 'statistic_method', 'average') or 'average' for dim in all_dimensions},
                    dim_output_params={}
                )

                cases = ReportControllerTask._build_case_data(
                    test_cases, results, all_dimensions, dim_results_map, task
                )

                case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

                # 生成 field_mapping 快照（按 algorithm_type 分组）
                field_mappings = {}
                try:
                    from backend.utils.algorithm.algorithm_result_field_mapper import AlgorithmResultFieldMapper
                    for tc in test_cases:
                        algo_type = getattr(tc, 'algorithm_type', None)
                        if algo_type and algo_type not in field_mappings:
                            field_mappings[algo_type] = AlgorithmResultFieldMapper.get_field_mapping(algo_type)
                except Exception as e:
                    log_and_emit('WARNING', 'report', f'[generate_task_report_async] 构建 field_mappings 失败: {e}', task_id=task_id)

                summary = {
                    "total_cases": total_cases,
                    "completed_cases": completed_cases,
                    "failed_cases": failed_cases,
                    "overall_success_rate": round(success_rate, 2),
                    "dimension_values": summary_dim_values,
                    "duration": task.actual_duration,
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "case_categories": case_categories_list,
                    "all_case_tags": case_tags_list,
                    "all_tags": case_tags_list,
                    "devices": devices_list,
                    "apis": apis_list,
                    "resources": resources,
                    "resource_headers": resource_headers,
                    "all_metrics": all_metrics,
                    "metric_data": metric_data,
                    "tag_metric_data": tag_metric_data,
                    "raw_data": raw_data,
                    "device_stats": device_stats,
                    "api_stats": api_stats,
                    "case_type_stats": case_type_stats,
                    "cases": cases,
                    "field_mappings": field_mappings,
                    "source_task_ids": source_task_ids,
                    "is_merged": bool(source_task_ids)
                }
                
                summary = ReportUtils.normalize_summary_metrics(summary)

                new_report = ReportControllerTask._create_report_record(name, task_id, description)
                log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created report id={new_report.id}', task_id=task_id)
                
                summary_info, summary_meta = ReportControllerTask._create_report_summary(new_report.id, task, summary)
                log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created summary_info id={summary_info.id}, report_id={summary_info.report_id}', task_id=task_id)
                
                raw_data_record, metric_stats_record = ReportControllerTask._create_report_detail_data(new_report.id, summary)
                log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created detail data for report_id={new_report.id}', task_id=task_id)

                report_id = new_report.id
                # 生成后保持 draft 状态，由用户在前端手动发布
                db.session.commit()
                
                log_and_emit('INFO', 'report', f'[generate_task_report_async] Report generated successfully, report_id={report_id}', task_id=task_id)

                emit_data = {
                    'taskId': task_id,
                    'reportId': report_id,
                    'success': True,
                    'status': 'completed'
                }
                log_and_emit('INFO', 'report', f'[generate_task_report_async] Emitting report_generated: {emit_data}', task_id=task_id)
                socketio.emit('report_generated', emit_data)

            except Exception as e:
                db.session.rollback()
                log_and_emit('ERROR', 'report', f'[generate_task_report_async] Error: {e}\n{traceback.format_exc()}', task_id=task_id)
                emit_data = {
                    'taskId': task_id,
                    'success': False,
                    'error': '报告生成失败，请稍后重试'
                }
                log_and_emit('INFO', 'report', f'[generate_task_report_async] Emitting error: {emit_data}', task_id=task_id)
                socketio.emit('report_generated', emit_data)
            finally:
                with _generating_lock:
                    _generating_tasks.discard(task_id)
