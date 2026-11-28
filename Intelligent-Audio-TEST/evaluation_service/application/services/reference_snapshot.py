# -*- coding: utf-8 -*-
"""评估参考参数快照（2026-11-28 裁定）。

把「本次评估实际使用的参考参数」落一份到结果目录 `reference_params.json`，
与 result_data.json 同目录，保证结果可复现、可审计。

覆盖口径：所有经 `CaseEvaluationMixin.evaluate_case` 的评估入口（E2E 单轮 /
多轮、API 测试、重新评估）；设备结果重提取在执行侧另行落快照。
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def capture_reference_snapshot(task_id, test_case_id, result_id, *,
                               algorithm_type=None, device_type=None,
                               reference_params_col=None, rounds=None,
                               raw_reference_params=None,
                               adjusted_reference_params=None,
                               source='evaluation'):
    """写参考参数快照；任何异常只告警，不阻断评估主流程。"""
    try:
        result_row = None
        try:
            from evaluation_service.infrastructure.acl import task_acl_repository
            result_row = task_acl_repository.get_test_result_by_id(result_id)
        except Exception:
            result_row = None

        result_data_path = _get(result_row, 'result_data_path')
        device_sn = (_get(result_row, 'device_sn')
                     or _get(result_row, 'device_id')
                     or str(result_id))

        payload = {
            'schema_version': SCHEMA_VERSION,
            'task_id': str(task_id),
            'case_id': str(test_case_id),
            'result_id': result_id,
            'device_sn': str(device_sn),
            'algorithm_type': algorithm_type,
            'device_type': device_type,
            'source': source,
            'reference_params_col': reference_params_col,
            'original_reference_params': raw_reference_params,
            'adjusted_reference_params': adjusted_reference_params,
            'effective_rounds': rounds,
            'captured_at': datetime.now(timezone.utc).isoformat(),
        }

        from shared.utils.result_data_store import write_reference_params_file
        return write_reference_params_file(
            task_id, test_case_id, device_sn, payload,
            result_data_path=result_data_path)
    except Exception as e:
        logger.warning('capture_reference_snapshot failed: %s', e)
        return ''
