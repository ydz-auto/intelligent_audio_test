# -*- coding: utf-8 -*-
"""增量回导报告原地替换应用服务（report_service，INT-1762 D4）

供 ReportConfigService gRPC servicer 调用（编排方 D3 增量导入 / D6 平台报告导入）。
与 `ReportTransferService.import_reports`（整包导入、ID 冲突重映射）不同，本服务
是**原地替换**：按 A 原任务定位目标报告，保留其 id 与可见性 / owner，只换内容与
子表，并把旧值落批次快照以支持回滚。

并发保护（D0 遗留风险 3）：替换期间若有用户在生成 / 编辑该任务报告，会读到
「子表刚删完」的中间态，因此复用报告生成的任务级分布式锁
`report_task_generator._acquire_generation_lock`。
"""
import logging

from shared.utils.grpc_json import fold_business_code
from shared.utils.log_handler import log_not_emit
from report_service.infrastructure.persistence.report_replacement_repository import (
    ReplacementValidationError,
    report_replacement_repository,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'report_replacement_service'


class ReportReplacementService:
    """报告 7 表原地替换 / 批次快照回滚"""

    def replace_reports(self, rows_by_table: dict, task_id, target_report_id=None,
                        batch_id: str = '') -> dict:
        """原地替换目标报告（单事务 + 旧值快照）。

        Returns:
            {'success': bool, 'message': str, 'data': {...}, 'code': int}
            失败时 data 里也折入 `code`（INT-566 口径，供网关 / 编排层映射）。
        """
        task_id_int = self._as_int(task_id)
        lock = None
        if task_id_int is not None:
            # 延迟导入：report_task_generator 依赖报告生成链路，避免 import 期副作用
            from report_service.application.services.report_task_generator import (
                _acquire_generation_lock,
            )
            lock = _acquire_generation_lock(task_id_int)
            if lock is None:
                return {'success': False,
                        'message': f'任务 {task_id_int} 报告正在生成中，请稍后重试',
                        'code': 409,
                        'data': fold_business_code({'task_id': task_id_int}, 409)}
        try:
            data = report_replacement_repository.replace_reports(
                rows_by_table, task_id_int, self._as_int(target_report_id), batch_id)
            return {'success': True, 'message': '', 'data': data}
        except ReplacementValidationError as e:
            detail = dict(e.detail or {})
            detail['batch_id'] = batch_id
            log_not_emit('WARNING', _MODULE_NAME,
                         f'报告替换校验失败 batch={batch_id} code={e.code}: {e}',
                         category='system')
            return {'success': False, 'message': str(e), 'code': e.code,
                    'data': fold_business_code(detail, e.code)}
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'报告替换失败 batch={batch_id}: {e}',
                         category='system', exc_info=True)
            return {'success': False, 'message': str(e), 'code': 500,
                    'data': fold_business_code({'batch_id': batch_id}, 500)}
        finally:
            if lock is not None:
                try:
                    lock.release()
                except Exception:
                    logger.warning('释放报告生成锁失败 task_id=%s', task_id_int)

    def rollback_replacement(self, batch_id: str) -> dict:
        """按批次快照回滚报告替换。补偿失败必须显式报错（A8-4）。"""
        try:
            return {'success': True, 'message': '',
                    'data': report_replacement_repository.rollback_by_batch(batch_id)}
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'报告替换回滚失败 batch={batch_id}: {e}',
                         category='system', exc_info=True)
            return {'success': False,
                    'message': f'报告替换回滚失败（需人工介入）: {e}', 'code': 500,
                    'data': fold_business_code({'batch_id': batch_id}, 500)}

    @staticmethod
    def _as_int(value):
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


report_replacement_service = ReportReplacementService()
