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

import collections
import logging
from datetime import datetime, timezone, timedelta

from shared.infrastructure.storage import storage
from shared.utils.status_constants import TaskStatus
from shared.utils.audio_path_utils import normalize_audio_path
from shared.domain.algorithm_result_builder import build_algorithm_results_for_result
from shared.models.database import get_db_session

from task_service.infrastructure.persistence.task_repository import task_repository
from task_service.infrastructure.read_models.task_read_model import task_read_model

logger = logging.getLogger(__name__)

_UTC_PLUS_8 = timezone(timedelta(hours=8))


def _iter_background_noise(config: dict):
    """遍历 config 中的背景噪音配置（background_noise / backgroundNoise）。

    INT-1306（P1 覆盖修复）：真实引用形态由 task_service 的
    _apply_noise_to_round / _apply_noise_to_case_bn 写入：
    - 顶层 config.background_noise（_apply_noise_to_case_bn）
    - 轮次级 round_item.background_noise（snake）/ backgroundNoise（camelCase）
      （_apply_noise_to_round 的 caseBackgroundNoise 目标）
    - segment 级 rounds[].audios[].background_noise（snake）
      （_apply_noise_to_round 的 segmentBackgroundNoise 目标）

    旧实现只读顶层 + 轮次级 snake，漏 camelCase 与 segment 级，可能静默删除
    被引用音频；此处对齐旧字符串扫描口径（任意层级命中即拦）。
    """
    if not isinstance(config, dict):
        return

    def _noise_of(obj):
        for key in ('background_noise', 'backgroundNoise'):
            bn = obj.get(key)
            if bn is not None:
                yield bn if isinstance(bn, dict) else {}

    for bn in _noise_of(config):
        yield bn
    for round_item in config.get('rounds', []) or []:
        if not isinstance(round_item, dict):
            continue
        for bn in _noise_of(round_item):
            yield bn
        for audio_item in round_item.get('audios', []) or []:
            if isinstance(audio_item, dict):
                for bn in _noise_of(audio_item):
                    yield bn


def _collect_case_audio_references(config: dict):
    """收集用例 config 被引用的音频 id，返回 (direct_ids, noise_ids)。

    INT-1306（P1 覆盖修复）：对齐旧实现全量字符串扫描的命中口径，按形态分类：
    - direct：rounds[].audios[].audio_id / 顶层 audios[].audio_id /
      rounds[].audios[].interferers[].audio_id（干扰人，_apply_noise_to_round
      的 interferers 目标）
    - noise：_iter_background_noise 收集（background_noise / backgroundNoise，
      顶层 / 轮次级 / segment 级）

    用例侧与任务-用例关联侧复用，保证两种引用入口口径一致。
    """
    from shared.utils import testcase_helpers as _case_helpers

    direct = set()
    noise = set()

    def _add(container, value):
        if value is None:
            return
        try:
            container.add(int(value))
        except (TypeError, ValueError):
            pass

    def _collect_audio_item(item):
        if not isinstance(item, dict):
            return
        _add(direct, item.get('audio_id'))
        for inf in item.get('interferers', []) or []:
            if isinstance(inf, dict):
                _add(direct, inf.get('audio_id'))

    for audio_item in _case_helpers.collect_audios(config or {}):
        _collect_audio_item(audio_item)
    for audio_item in (config or {}).get('audios', []) or []:
        _collect_audio_item(audio_item)
    for noise_cfg in _iter_background_noise(config or {}):
        if isinstance(noise_cfg, dict):
            _add(noise, noise_cfg.get('audio_id'))
    return direct, noise


def _collect_config_audio_ids(obj) -> set:
    """递归收集 config 中的 audio_id / audioId 取值（任务自定义配置结构）。

    INT-1306：任务 config 结构不固定（parallel/execution_mode/rounds 等），
    无法用固定 JSONB 路径，采用递归收集替代旧实现的全量字符串扫描。
    """
    ids = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ('audio_id', 'audioId'):
                if isinstance(value, bool):
                    continue
                try:
                    ids.add(int(value))
                except (TypeError, ValueError):
                    pass
            ids |= _collect_config_audio_ids(value)
    elif isinstance(obj, list):
        for item in obj:
            ids |= _collect_config_audio_ids(item)
    return ids


class TaskQueryService:
    """任务查询应用服务（读侧）。"""

    def list_tasks(self, page=1, per_page=10, status=None,
                   device_type=None, algorithm_type=None,
                   search=None, start_date=None, end_date=None,
                   favorite=False, deleted=False, user_id=None,
                   evaluation_status=None, merged=False, cherry_pick=False,
                   execution_status=None, merge_type=None, stats=False,
                   visibility=None) -> dict:
        """获取任务列表（device_type 按用例级被测设备类型过滤，可选）。

        favorite（INT-141）：仅当前用户收藏；deleted（INT-141）：仅回收站。
        evaluation_status（INT-301）：按任务级评估状态过滤（与执行状态并列）。
        merged（INT-298）：仅合并容器任务（对齐 V9.7.10 合并页签数据源）。
        cherry_pick（INT-339）：仅挑选合并容器任务（专有关系表存在性判定）。
        execution_status（INT-301 F1）：按任务级执行状态过滤（复用派生表达式，
            徽章展示与筛选命中同口径；与原始 status 过滤并存，兼容历史入口）。
        merge_type（INT-577）：合并方式快捷筛选（whole|picked）——网关已映射为
            merged/cherry_pick 布尔，此处透传（供兼容/审计）。
        stats（INT-577）：恒返回合并容器统计块（merged ∪ cherry_pick 并集）。
        visibility（INT-466）：可见性筛选（shared/private；None=全部）。
        """
        try:
            result = task_read_model.search_tasks(
                page=page, per_page=per_page, status=status,
                device_type=device_type,
                algorithm_type=algorithm_type,
                search=search, start_date=start_date, end_date=end_date,
                favorite=favorite, deleted=deleted, user_id=user_id,
                evaluation_status=evaluation_status, merged=merged,
                cherry_pick=cherry_pick, execution_status=execution_status,
                merge_type=merge_type, stats=stats,
                visibility=visibility,
            )
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"查询任务列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def check_audio_references(self, audio_ids) -> dict:
        """按 audio_id 集合查被测试用例/任务引用计数（INT-1306）。

        替代调用方逐页 ListTestCases / ListTasks 全量拉取：DB 侧单次扫描
        test_cases / test_tasks / task_case_relations 的 config，在内存聚合
        每个 audio_id 的引用计数后返回。无全量分页、无跨服务重复串行调用。

        data.references = {str(audio_id): {'testcase_audio': N,
                                            'testcase_noise': M,
                                            'task': K}}
        """
        from task_service.infrastructure.persistence.models import (
            Task as _Task,
            TaskCase as _TaskCase,
            TestCase as _TestCase,
        )
        try:
            audio_id_set = set()
            for aid in audio_ids:
                try:
                    audio_id_set.add(int(aid))
                except (TypeError, ValueError):
                    continue
            result = {
                str(aid): {'testcase_audio': 0, 'testcase_noise': 0, 'task': 0}
                for aid in audio_id_set
            }
            if not audio_id_set:
                return {'success': True, 'message': '', 'data': {'references': result}}

            session = get_db_session()
            try:
                # 1) 未删除测试用例 config：direct（rounds[].audios[].audio_id /
                #    顶层 audios[] / interferers[].audio_id）+ noise
                #    （background_noise / backgroundNoise，顶层 / 轮次级 / segment 级）
                case_audio_counts = collections.Counter()
                case_noise_counts = collections.Counter()
                case_configs = {}
                for tc_id, config in (
                    session.query(_TestCase.id, _TestCase.config)
                    .filter(_TestCase.deleted == False)  # noqa: E712
                    .all()
                ):
                    cfg = config or {}
                    case_configs[tc_id] = cfg
                    direct_ids, noise_ids = _collect_case_audio_references(cfg)
                    for aid in direct_ids:
                        case_audio_counts[aid] += 1
                    for aid in noise_ids:
                        case_noise_counts[aid] += 1

                # 2) 未删除任务引用：任务 config 内嵌 audio_id + 任务-用例关联（用例 config）
                task_audio_ids = {}
                for task_id, config in (
                    session.query(_Task.id, _Task.config)
                    .filter(_Task.deleted == False)  # noqa: E712
                    .all()
                ):
                    task_audio_ids[task_id] = _collect_config_audio_ids(config or {})
                for task_id, tc_id in session.query(_TaskCase.task_id, _TaskCase.test_case_id).all():
                    if task_id not in task_audio_ids:
                        continue  # 仅统计未删除任务
                    cfg = case_configs.get(tc_id)
                    if not cfg:
                        continue
                    # 与用例侧同口径（P1 覆盖修复）：direct + noise 全形态
                    direct_ids, noise_ids = _collect_case_audio_references(cfg)
                    task_audio_ids[task_id].update(direct_ids)
                    task_audio_ids[task_id].update(noise_ids)

                task_counts = collections.Counter()
                for task_id, ids in task_audio_ids.items():
                    for aid in ids:
                        if aid in audio_id_set:
                            task_counts[aid] += 1

                # 3) 聚合返回
                for aid in audio_id_set:
                    result[str(aid)]['testcase_audio'] = case_audio_counts.get(aid, 0)
                    result[str(aid)]['testcase_noise'] = case_noise_counts.get(aid, 0)
                    result[str(aid)]['task'] = task_counts.get(aid, 0)
                return {'success': True, 'message': '', 'data': {'references': result}}
            finally:
                session.close()
        except Exception as e:
            logger.error(f"检查音频引用失败: {e}", exc_info=True)
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

    def get_task_labs(self, task_id: int) -> dict:
        """获取任务关联实验室（GET /api/tasks/{id}/labs，实验室扩展 INT-540）。"""
        try:
            result = task_read_model.get_task_labs(task_id)
            if result is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"获取任务实验室失败: {e}", exc_info=True)
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
                # 设备输出声明只用于轮内子键类型/展示名解析，不进展示字段清单
                device_output_fields = (
                    _algo_repo.algo_get_device_output_fields(algorithm_type) if algorithm_type else []
                )

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
                        build_algorithm_results_for_result(
                            result, resource, algo_res, r_data,
                            aux_params_map, result_dim_rows,
                            output_fields, algorithm_type,
                            normalize_audio_path_fn=_normalize_audio_path_for_task,
                            device_output_fields=device_output_fields,
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
                # 用例级执行目标（API/设备）：详情内逐目标对比
                "targets": raw.get('targets', []),
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


def _normalize_audio_path_for_task(abs_path):
    """将音频文件的绝对路径转换为相对 STATIC_BASE_PATH 的相对路径。"""
    try:
        from task_service.config.config import Config
        _static_base = getattr(Config, 'STATIC_BASE_PATH', '')
    except Exception:
        _static_base = ''
    return normalize_audio_path(abs_path, _static_base)


# 模块级单例
task_query_service = TaskQueryService()
