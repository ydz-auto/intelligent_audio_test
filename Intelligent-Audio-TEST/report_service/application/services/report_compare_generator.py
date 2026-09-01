# -*- coding: utf-8 -*-
"""对比报告生成（report_service 版本）。

从 api_gateway/application/services/report/report_compare_generator.py 迁移而来，
保持 ReportCompareGenerator 类原有逻辑不变，仅做以下调整：
- 移除直接数据库访问（PO / get_db_session），改用 report_repository 写入聚合根与子实体
- 移除 api_gateway 专属依赖（response / error_codes / schemas.report / request_adapter），
  compare / secondary_compare 改为接收业务参数并返回 dict
- gRPC helper 统一从 report_service.infrastructure.clients.grpc_clients 导入
- ReportUtils / ReportQueryBuilder / ReportDataBuilder / ReportCompareHelpers
  导入路径切换到 report_service
- 报告类型与状态使用字符串字面量 'comparison' / 'secondary_comparison' / 'draft'
- 保留 ThreadPoolExecutor 与锁，保留 _emit_secondary_compare_event 事件推送

实现采用 Mixin 组合模式（同 report_utils / report_aggregation 拆分先例）：
- ReportCompareDataMixin: 对比报告任务校验 + 数据准备 + 摘要构建
- ReportSecondaryDataMixin: 二次对比报告数据准备 + 摘要构建
- ReportComparePersistMixin: 对比报告与二次对比报告落库写入
"""

import traceback
import threading
from concurrent.futures import ThreadPoolExecutor

from shared.utils.log_handler import log_and_emit
from shared.utils.query_utils import now_cst

from report_service.application.services.report_compare_generator_data_mixin import ReportCompareDataMixin
from report_service.application.services.report_compare_generator_secondary_mixin import ReportSecondaryDataMixin
from report_service.application.services.report_compare_generator_persist_mixin import ReportComparePersistMixin
from report_service.application.services.report_compare_helpers import ReportCompareHelpers
from report_service.application.services.report_compare_helpers import (
    _grpc_get_tasks_by_ids, _grpc_get_test_results_by_task_ids,
)
from report_service.domain.entities import ReportAggregate
from report_service.infrastructure.persistence.report_repository import report_repository


_secondary_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='secondary_compare')
_generating_secondary = {}
_generating_secondary_lock = threading.Lock()


def _emit_secondary_compare_event(event_name, data):
    """通过 Redis PubSub 推送二次对比报告生成事件，由 api_gateway SSE 端点转发给前端"""
    try:
        from shared.utils.redis_pubsub import RedisPubSub
        RedisPubSub().publish('sse_events', {'event': event_name, 'data': data})
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(f"SSE event emit failed: {_e}")


class ReportCompareGenerator(
    ReportCompareDataMixin,
    ReportSecondaryDataMixin,
    ReportComparePersistMixin,
):
    """对比报告生成（原 ReportCommandService 中 D + E 组方法）。

    承载对比报告与二次对比报告生成相关的静态方法，保持原有逻辑不变。
    """

    @staticmethod
    def compare(task_ids: list, name: str = None, description: str = None) -> dict:
        """生成对比报告。

        原实现从 HTTP request 解析参数并返回 (response, http_code)；
        迁移后改为接收业务参数并返回 dict，由接口层负责 HTTP 适配。

        Args:
            task_ids: 任务 ID 列表
            name: 报告名称（可选，缺省时自动生成）
            description: 报告描述（可选）

        Returns:
            dict: {'success': bool, 'data': {'report_id': ...}, 'message': str}
        """
        if not task_ids:
            return {'success': False, 'data': None, 'message': '缺少必要参数: taskIds'}

        if not name:
            name = f"对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"

        try:
            tasks, error = ReportCompareGenerator._validate_and_get_tasks(task_ids)
            if error:
                return {'success': False, 'data': None, 'message': error}

            results = _grpc_get_test_results_by_task_ids(task_ids)

            data_dict, error = ReportCompareGenerator._prepare_compare_data(tasks, task_ids, results)
            if error:
                return {'success': False, 'data': None, 'message': error}

            summary = ReportCompareGenerator._build_compare_summary(tasks, task_ids, results, data_dict)

            new_report_id = ReportCompareGenerator._persist_compare_report(
                name, description, summary, data_dict["source_cases"], data_dict["comparison_data"]
            )

            return {
                'success': True,
                'data': {'report_id': new_report_id},
                'message': '对比报告生成成功',
            }
        except Exception as e:
            traceback.print_exc()
            return {'success': False, 'data': None, 'message': '对比报告生成失败，请稍后重试'}

    @staticmethod
    def secondary_compare(report_ids: list, description: str = None) -> dict:
        """提交二次对比报告生成（异步）。

        原实现从 HTTP request 解析参数并返回 (response, http_code)；
        迁移后改为接收业务参数并返回 dict，由接口层负责 HTTP 适配。

        Args:
            report_ids: 报告 ID 列表（至少 2 个）
            description: 报告描述（可选）

        Returns:
            dict: {'success': bool, 'data': {'reportKey': [...], 'status': '...'}, 'message': str}
        """
        if not report_ids:
            return {'success': False, 'data': None, 'message': '缺少必要参数: reportIds'}
        if len(report_ids) < 2:
            return {'success': False, 'data': None, 'message': '二次对比至少需要两个报告 ID'}

        report_key = tuple(sorted(report_ids))

        with _generating_secondary_lock:
            if report_key in _generating_secondary:
                return {
                    'success': True,
                    'data': {'reportKey': list(report_key), 'status': 'generating'},
                    'message': '对比报告正在生成中',
                }
            _generating_secondary[report_key] = True

        log_and_emit('INFO', 'report', f'[secondary_compare] Submitting async task for report_ids={report_ids}')
        _secondary_executor.submit(
            ReportCompareGenerator._secondary_compare_async,
            report_ids, description, report_key
        )

        return {
            'success': True,
            'data': {'reportKey': list(report_key), 'status': 'generating'},
            'message': '对比报告生成中，请稍后',
        }

    @staticmethod
    def _secondary_compare_async(report_ids, description, report_key):
        """二次对比报告异步生成任务。

        原实现使用 get_db_session().add(new_report) / flush() / commit() /
        rollback() 直连 PO；迁移后改用 report_repository.add 写入主报告聚合根，
        子表记录通过 _create_secondary_report_records 使用 repository 方法写入。
        """
        try:
            log_and_emit('INFO', 'report', f'[secondary_compare_async] Starting for report_ids={report_ids}')

            reports, tasks, task_ids, error = ReportCompareHelpers._validate_reports_and_get_tasks(report_ids)
            if error:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            data_dict, error = ReportCompareGenerator._prepare_secondary_data(report_ids, reports, tasks, task_ids)
            if error:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            summary = ReportCompareGenerator._build_secondary_summary(tasks, task_ids, reports, data_dict)

            name = f"二次对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"
            # 主报告聚合根：使用字符串字面量保持与现有数据模型一致
            aggregate = ReportAggregate(
                task_id=0,
                report_type='secondary_comparison',
                status='draft',
                config={'name': name, 'description': description},
                deleted=False,
            )
            new_report_id = report_repository.add(aggregate)

            ReportCompareGenerator._create_secondary_report_records(
                new_report_id, task_ids, tasks, reports,
                summary["case_categories_list"], summary["case_tags_list"],
                summary["devices_list"], summary["apis_list"], summary["resources"],
                summary["resource_headers"], summary["all_metrics"],
                summary["raw_data"], summary["metric_data"], summary["tag_metric_data"],
                summary["case_type_stats"],
                summary["device_stats"], summary["api_stats"], summary["source_cases"],
                summary["comparison_matrix_data"]
            )

            log_and_emit('INFO', 'report', f'[secondary_compare_async] Report generated successfully, report_id={new_report_id}')

            _emit_secondary_compare_event('secondary_compare_generated', {
                'reportIds': report_ids,
                'reportId': new_report_id,
                'success': True,
                'status': 'completed'
            })

        except Exception as e:
            log_and_emit('ERROR', 'report', f'[secondary_compare_async] Error: {e}\n{traceback.format_exc()}')
            _emit_secondary_compare_event('secondary_compare_generated', {
                'reportIds': report_ids,
                'success': False,
                'error': '对比报告生成失败，请稍后重试'
            })
        finally:
            with _generating_secondary_lock:
                _generating_secondary.pop(report_key, None)
