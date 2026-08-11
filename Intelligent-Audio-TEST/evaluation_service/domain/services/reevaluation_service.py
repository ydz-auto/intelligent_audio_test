# -*- coding: utf-8 -*-
"""重评估领域服务（Domain 层）

P0-2 DDD 改造：从 application/handlers/reevaluation_executor.py 下沉的业务规则。
- 哪些用例需要重评估（all / failed 过滤逻辑）
- 算法结果反序列化（双重序列化兼容）
- 多轮/单轮分发决策
- API 聚合结果计算
- case_info 构建

纯业务逻辑，不依赖 infrastructure 层。ACL 访问由 Application 层编排时注入。
"""
import json
from typing import Any, Dict, List, Optional


class ReevaluationService:
    """重评估领域服务"""

    @staticmethod
    def deserialize_algorithm_result(raw: Any) -> dict:
        """反序列化 algorithm_result，处理可能的双重序列化旧数据。"""
        result = raw
        while isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                result = {}
        if not isinstance(result, dict):
            result = {}
        return result

    @staticmethod
    def collect_cases_all(
        test_results: List[Any],
        full_data_map: Dict[str, dict],
        task_case_map: Dict[str, Any],
        reextract_device_output: bool,
    ) -> List[dict]:
        """收集所有需要重新评估的用例（all 类型）。

        纯业务逻辑：根据 execution_status 过滤，构建 case_info。
        不直接访问 ACL — 由 Application 层预先准备好 test_results、full_data_map、task_case_map。

        Args:
            test_results: TestResultDTO 列表
            full_data_map: {test_case_id: full_data} 预加载的结果数据
            task_case_map: {test_case_id: tc_rel} 预加载的 TaskCaseDTO
            reextract_device_output: 是否重新提取了设备输出
        """
        cases = []
        for result in test_results:
            if result.execution_status != 'completed':
                continue

            test_case_id = result.test_case_id
            tc_rel = task_case_map.get(str(test_case_id))
            if not tc_rel:
                continue

            algo_result = ReevaluationService.deserialize_algorithm_result(
                result.algorithm_result or {}
            )
            full_data = full_data_map.get(str(test_case_id), {})

            case_info = ReevaluationService._build_case_info(
                result, algo_result, full_data, reextract_device_output, tc_rel
            )
            cases.append(case_info)
        return cases

    @staticmethod
    def collect_cases_failed(
        test_results: List[Any],
        full_data_map: Dict[str, dict],
        task_case_map: Dict[str, Any],
        reextract_device_output: bool,
    ) -> List[dict]:
        """收集评估失败的用例（failed 类型）。

        纯业务逻辑：execution_status == completed 且 evaluation_status == failed。
        """
        cases = []
        for result in test_results:
            if result.execution_status != 'completed':
                continue

            test_case_id = result.test_case_id
            tc_rel = task_case_map.get(str(test_case_id))
            if not tc_rel or tc_rel.evaluation_status != 'failed':
                continue

            algo_result = ReevaluationService.deserialize_algorithm_result(
                result.algorithm_result or {}
            )
            full_data = full_data_map.get(str(test_case_id), {})
            result_type = full_data.get('result_type', 'unknown') if full_data else 'unknown'

            case_info = ReevaluationService._build_case_info(
                result, algo_result, full_data, reextract_device_output, tc_rel, result_type
            )
            cases.append(case_info)
        return cases

    @staticmethod
    def _build_case_info(
        result: Any,
        algo_result: dict,
        full_data: dict,
        reextract_device_output: bool,
        tc_rel: Any,
        result_type: Optional[str] = None,
    ) -> dict:
        """构建 case_info 字典（纯业务逻辑）。"""
        reference_params = full_data.get('adjusted_reference_params', []) if full_data else []
        case_info = {
            'test_case_id': result.test_case_id,
            'result_id': result.id,
            'algorithm_result': algo_result,
            'reference_params': reference_params,
            'device_id': result.device_id,
            'task_id': result.task_id,
            'reextracted': reextract_device_output,
        }
        if result_type is not None:
            case_info['result_type'] = result_type
        return case_info

    @staticmethod
    def is_multi_round(algorithm_result: Any) -> bool:
        """判断是否为多轮结果（业务决策）。"""
        algo = ReevaluationService.deserialize_algorithm_result(algorithm_result)
        return bool(algo and 'rounds' in algo)

    @staticmethod
    def compute_api_aggregated(rounds: List[dict]) -> Optional[dict]:
        """从 rounds 的 round_evaluation 中计算聚合结果（纯业务逻辑）。"""
        if not rounds:
            return None
        evals = [r.get('round_evaluation', {}) for r in rounds if r.get('round_evaluation')]
        if not evals:
            return None
        return {
            'avg_wer': sum(e.get('wer', 0) for e in evals) / len(evals),
            'avg_llm_judge': sum(e.get('llm_judge', 0) for e in evals) / len(evals) if any('llm_judge' in e for e in evals) else None,
            'avg_latency': sum(r.get('latency', 0) for r in rounds) / len(rounds),
            'round_count': len(rounds),
        }


# 模块级单例
reevaluation_service = ReevaluationService()
