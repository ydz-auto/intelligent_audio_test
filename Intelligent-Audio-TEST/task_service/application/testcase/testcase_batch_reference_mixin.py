# -*- coding: utf-8 -*-
"""测试用例参考参数刷新辅助 Mixin — TestCaseReferenceRefreshMixin。

从 testcase_batch_service.py 按职责拆分，承担参考参数相关的模块级辅助函数：
- OSS key 构建（_build_ref_params_key）
- 逐轮生成参考参数并写入 OSS（_apply_reference_params_to_config）
- 批量刷新动作（_batch_refresh_reference，含超阈值异步任务提交）

由 TestCaseBatchService 组合复用，不单独实例化。
"""
from __future__ import annotations

import json
import logging

from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)

# reference_params 文件存储到 OSS（ref_params bucket）
_REF_PARAMS_BUCKET = 'ref_params'


def _build_ref_params_key(case_id, round_number, filename=None):
    """构建参考参数 OSS key：{case_id}/{filename} 或 {case_id}/round_{round_number}.json"""
    if filename is None:
        filename = f"round_{round_number}.json"
    return f"{case_id}/{filename}"


def _apply_reference_params_to_config(test_case) -> None:
    """为 test_case 逐轮生成参考参数并写入 OSS，路径存入 reference_params 独立列。

    替代 ReferenceParamsGenerator.apply_to_config，改为通过 gRPC 调用
    algorithm_service 生成每轮参考参数，存储逻辑仍在 task_service 本地完成。
    """
    if not test_case:
        return

    config = test_case.config or {}
    rounds = config.get('rounds', [])

    if not rounds:
        return

    from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
    _algo_repo = AlgorithmRepository()

    case_id = getattr(test_case, 'id', '') or str(id(test_case))

    # 构建传入 gRPC 的 test_case_config（algorithm_type / config / test_type）
    test_case_config = {
        'algorithm_type': getattr(test_case, 'algorithm_type', None),
        'config': config,
        'test_type': getattr(test_case, 'test_type', 'api') or 'api',
    }

    ref_params_list = []
    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue

        round_number = round_item.get('round_number') or round_item.get('roundNumber') or 1

        round_params = _algo_repo.algo_generate_reference_params(test_case_config, round_item)
        if not round_params:
            continue

        round_params = _algo_repo.algo_get_all_reference_params(round_params)

        oss_key = _build_ref_params_key(case_id, round_number)

        try:
            from shared.infrastructure.storage import storage_save_bytes
            data = json.dumps(round_params, ensure_ascii=False, indent=2).encode('utf-8')
            stored_path = storage_save_bytes(data, _REF_PARAMS_BUCKET, oss_key,
                                             content_type='application/json')
            ref_params_list.append({
                'round_number': round_number,
                'reference_params_path': stored_path
            })
        except Exception as e:
            logger.warning(f"round {round_number}: failed to upload {_REF_PARAMS_BUCKET}/{oss_key}: {e}")

    test_case.reference_params = ref_params_list


class TestCaseReferenceRefreshMixin:
    """测试用例参考参数刷新 Mixin。"""

    def _batch_refresh_reference(self, data, common=None):
        """批量刷新参考参数（超过阈值时提交异步任务）。"""
        ids = data.get('ids', [])
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        logger.info(f"[refresh_reference] 开始处理, ids: {ids}, round_mode: {round_mode}, round_numbers: {round_numbers}")

        test_cases = self.repo.list_testcases_by_ids(ids)

        if len(ids) > 50:
            from task_service.application.testcase.reference_refresh_task import submit_reference_refresh_task
            task_id = submit_reference_refresh_task(
                ids,
                refresher=lambda tc: _apply_reference_params_to_config(tc),
            )
            return {
                'task_id': task_id,
                'message': f'已提交异步刷新任务，预计处理 {len(test_cases)} 个用例'
            }
        else:
            updated_count = 0
            for tc in test_cases:
                try:
                    _apply_reference_params_to_config(tc)
                    tc.updated_at = now_cst()
                    updated_count += 1
                except Exception as e:
                    logger.error(f"[refresh_reference] 处理用例 {tc.id} 失败: {e}")
            self.repo.commit()
            return f"已成功刷新 {updated_count} 个用例的参考参数"
