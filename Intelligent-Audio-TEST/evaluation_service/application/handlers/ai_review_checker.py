# -*- coding: utf-8 -*-
"""AI 复核 LLM 复检执行器（INT-800/INT-823）。

单次 LLM 复检：输入 result_id + dimension_id（缺省 0 = 结果现有已完成评估的 LLM
判分维度），经 GetDimensionResultsByResultIds 聚合 ASR/参考文本/维度分/LLM 评语，
复用 llm_judge 端点 worker 与维度配置重新判分，返回 verdict/confidence/reasoning。

- 非 E 域 Agent 编排（架构红线）：单次 LLM 调用，不做多步编排。
- 复检不落库、不改判权威维度记录：只返回结论，采纳/驳回由 task_service 命令侧负责。
- 无可用 LLM 端点 / 未配置 LLM 判分维度时优雅失败（success=False），由调用方
  （task_service AiReviewExecutor）置 ai_reviews.status=failed 不落判定。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from shared.constants.evaluation_dimension import is_llm_judge_dimension
from shared.utils.path_extractor import extract_by_path
from shared.utils.status_constants import EvaluationStatus

logger = logging.getLogger(__name__)

# AI 复核 verdict 枚举（与 ai_reviews 表契约一致）
VERDICT_PASSED = 'passed'
VERDICT_FAILED = 'failed'
VERDICT_UNCERTAIN = 'uncertain'

# LLM 判分维度标记已收敛到 shared 谓词（INT-1671），本模块不再持有本地常量

# 主评分输出参数 code 兜底（output_role=main 的 field_path 缺失时用）
_MAIN_SCORE_PARAM_CODE = 'llm_judge_score'
_REASONING_PARAM_CODE = 'reasoning'

# 维度区间缺省（llm_judge_score 0-5，配置缺失时兜底）
_DEFAULT_SCORE_MIN = 0.0
_DEFAULT_SCORE_MAX = 5.0


def _is_llm_judge_dimension(dim_config: dict) -> bool:
    """维度配置是否 LLM 判分维度（口径见 shared.constants.evaluation_dimension）。"""
    return is_llm_judge_dimension(
        task_type_code=dim_config.get('task_type_code'),
        dimension_type=dim_config.get('dimension_type'),
    )


def _pick_main_output(output_params: List[dict]) -> Optional[dict]:
    """选取主评分输出参数（output_role=main 的 field_path；兜底 llm_judge_score）。"""
    for p in output_params:
        if p.get('output_role') == 'main' and p.get('field_path'):
            return p
    for p in output_params:
        if p.get('param_code') == _MAIN_SCORE_PARAM_CODE and p.get('field_path'):
            return p
    return None


def _find_output(output_params: List[dict], param_code: str) -> Optional[dict]:
    """按 param_code 找输出参数。"""
    for p in output_params:
        if p.get('param_code') == param_code:
            return p
    return None


class AiReviewChecker:
    """LLM 复检执行器（Application 层）。"""

    def execute(self, result_id: int, dimension_id: Optional[int] = None,
                task_id: Optional[int] = None,
                test_case_id: Optional[str] = None) -> Dict[str, Any]:
        """执行单次 LLM 复检。

        Returns:
            {'success': bool, 'message': str, 'data': {'verdict','confidence','reasoning'} | None}
        """
        try:
            result_id = int(result_id or 0)
            if not result_id:
                return {'success': False, 'message': 'result_id 必填', 'data': None}

            # 1. 聚合维度评估结果（含 api_request_body/api_raw_response 上下文）
            items = self._aggregate_dimension_results(result_id)
            if not items:
                return {'success': False, 'message': f'结果 {result_id} 无维度评估记录', 'data': None}

            # 2. 确定目标维度（显式 dimension_id 或缺省取首个 LLM 判分维度）
            target = self._pick_target_dimension(items, dimension_id)
            if target is None:
                return {'success': False, 'message': '未找到可复检的 LLM 判分维度', 'data': None}

            # 3. 加载 llm_judge 维度配置（端点/body_template/output params）
            dim_config = self._load_dim_config(target.get('dimension_id'))
            if not dim_config:
                return {'success': False, 'message': f"维度 {target.get('dimension_id')} 配置不可用", 'data': None}

            # 4. 聚合上下文：ASR/参考文本/维度分/LLM 评语
            context = self._build_context(target, dim_config)

            # 5. 复用 llm_judge 端点 worker 与维度配置重新判分
            resp_data = self._call_llm_judge(dim_config, context, task_id, test_case_id)
            if not isinstance(resp_data, dict) or '__error__' in resp_data:
                err = (resp_data or {}).get('__error__', 'LLM 复检端点调用失败') \
                    if isinstance(resp_data, dict) else 'LLM 复检端点调用失败'
                return {'success': False, 'message': err, 'data': None}

            # 6. 派生 verdict/confidence/reasoning
            verdict, confidence, reasoning = self._derive_verdict(resp_data, dim_config)
            return {'success': True, 'message': '', 'data': {
                'verdict': verdict,
                'confidence': confidence,
                'reasoning': reasoning,
            }}
        except Exception as e:
            logger.error('LLM 复检异常 result_id=%s dimension_id=%s: %s',
                         result_id, dimension_id, e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None}

    # ==================== 上下文聚合 ====================

    def _aggregate_dimension_results(self, result_id: int) -> List[dict]:
        """经 GetDimensionResultsByResultIds 聚合该结果的维度评估记录。"""
        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        resp = evaluation_query_service.get_dimension_results_by_result_ids(
            [result_id], include_body=True)
        if not resp.get('success'):
            logger.warning('聚合维度评估结果失败 result_id=%s: %s',
                           result_id, resp.get('message'))
            return []
        data = resp.get('data') or {}
        return data.get('items') or []

    def _pick_target_dimension(self, items: List[dict],
                               dimension_id: Optional[int]) -> Optional[dict]:
        """确定复核维度记录。

        显式 dimension_id：取该维度记录（任意状态，有上下文即可复检）。
        缺省（0/None）：取第一个已完成评估的 LLM 判分维度记录。
        """
        if dimension_id:
            for it in items:
                if int(it.get('dimension_id') or 0) == int(dimension_id):
                    return it
            return None

        completed = [it for it in items
                     if it.get('evaluation_status') == EvaluationStatus.COMPLETED]
        for it in completed:
            dim_config = self._load_dim_config(it.get('dimension_id'))
            if dim_config and _is_llm_judge_dimension(dim_config):
                return it
        return None

    def _build_context(self, target: dict, dim_config: dict) -> dict:
        """聚合 LLM 复检输入上下文。

        以原始 api_request_body 为基底（含 ASR question/answer、参考
        correct_answer/query、record_file、prompt、model、rounds），
        补聚合维度分（score）与 LLM 评语（api_raw_response.reasoning），
        供 body_template 渲染与复检判分使用。
        """
        req_body = target.get('api_request_body')
        raw_resp = target.get('api_raw_response')
        context = {}
        if isinstance(req_body, dict):
            context.update(req_body)

        if target.get('score') is not None:
            context['current_score'] = target.get('score')
        if isinstance(raw_resp, dict):
            reasoning = raw_resp.get('reasoning')
            if reasoning:
                context['current_reasoning'] = reasoning
        return context

    # ==================== 维度配置 ====================

    def _load_dim_config(self, dim_id: Optional[int]) -> Optional[dict]:
        """加载维度配置（聚合根 + output/input params → dim_dict 形状）。"""
        if not dim_id:
            return None
        try:
            from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
                evaluation_dimension_repository,
            )
            from evaluation_service.infrastructure.acl.task_acl_repository import (
                task_acl_repository,
            )
            aggs = evaluation_dimension_repository.list_active_dimensions_by_ids([int(dim_id)])
            if not aggs:
                return None
            agg = aggs[0]
            snap = agg.snapshot
            params = task_acl_repository.get_dimension_params(int(dim_id))
            dim_config = {
                'id': int(dim_id),
                'name': agg.name,
                'result_min': snap.result_min,
                'result_max': snap.result_max,
                'rule': snap.rule.to_dict() if snap.rule else {},
                'api_endpoints': snap.api_endpoints or [],
                'api_settings': snap.api_settings,
                'api_url': snap.api_url,
                'dimension_type': snap.dimension_type or 'main',
                'parent_dimension_id': snap.parent_dimension_id,
                'task_type_code': snap.task_type_code,
                'output_params': [
                    {
                        'param_code': p.param_code,
                        'field_path': p.field_path,
                        'field_type': p.field_type,
                        'agg_role': p.agg_role,
                        'output_role': p.output_role,
                        'pass_threshold': p.pass_threshold,
                    }
                    for p in params if p.param_direction == 'output'
                ],
                'input_params': [
                    {
                        'param_code': p.param_code,
                        'default_value': p.default_value,
                        'field_type': p.field_type,
                        'required': p.required,
                    }
                    for p in params if p.param_direction == 'input'
                ],
            }
            return dim_config
        except Exception as e:
            logger.warning('加载维度配置失败 dim_id=%s: %s', dim_id, e)
            return None

    # ==================== LLM 端点调用 ====================

    def _call_llm_judge(self, dim_config: dict, context: dict,
                        task_id: Optional[int] = None,
                        test_case_id: Optional[str] = None,
                        api_client: Any = None) -> Any:
        """复用 llm_judge 端点 worker 与维度配置重新判分（同步单次调用）。

        api_client 缺省取 evaluation_service 宿主单例（端点 worker 基础设施）；
        单测可注入 mock 以替身 LLM 端点返回。
        """
        if api_client is None:
            from evaluation_service.infrastructure.evaluation_service_host import (
                evaluation_service,
            )
            api_client = evaluation_service.api_client

        api_settings = dim_config.get('api_settings') or {}
        body_template = api_settings.get('body_template')
        method = api_settings.get('method', 'POST')
        headers = api_settings.get('headers', {})

        endpoints = dim_config.get('api_endpoints') or []
        if isinstance(endpoints, list):
            endpoints = [ep for ep in endpoints
                         if isinstance(ep, dict) and (ep.get('url') or ep.get('endpoint'))]
        if not endpoints and dim_config.get('api_url'):
            endpoints = [{'url': dim_config['api_url'], 'name': 'Master'}]
        if not endpoints:
            return {'__error__': 'LLM 复检维度未配置 API 端点'}

        audio_field_names = {
            inp.get('param_code') for inp in dim_config.get('input_params') or []
            if inp.get('field_type') == 'audio' and inp.get('param_code')
        }
        dim_info = {
            'dimension_type': dim_config.get('dimension_type', 'main'),
            'parent_dimension_id': dim_config.get('parent_dimension_id'),
            'task_type_code': dim_config.get('task_type_code'),
        }

        payload = api_client.build_payload(
            body_template, context,
            task_id=task_id or 0, test_case_id=test_case_id or '',
            algorithm_type=dim_config.get('task_type_code'),
        )

        _, resp_data = api_client.make_api_request_with_fallback(
            endpoints=endpoints, method=method, headers=headers, payload=payload,
            task_id=task_id or 0, dim_names=[dim_config.get('name') or ''],
            api_url=dim_config.get('api_url'), test_case_id=test_case_id or '',
            dim_info=dim_info, audio_field_names=audio_field_names,
        )
        return resp_data

    # ==================== 判定派生 ====================

    def _derive_verdict(self, resp_data: dict, dim_config: dict):
        """从 LLM 复检响应派生 (verdict, confidence, reasoning)。

        - 主评分（output_role=main / llm_judge_score 的 field_path）缺失 → 'uncertain'；
        - 评分 >= pass_threshold（缺省取结果区间中点）→ 'passed'，否则 'failed'；
        - confidence = 评分相对阈值边界的归一化距离（钳制 [0,1]，边界恰等给 0.5）。
        """
        output_params = dim_config.get('output_params') or []
        main_param = _pick_main_output(output_params)
        reasoning_param = _find_output(output_params, _REASONING_PARAM_CODE)

        raw_score = None
        if main_param and main_param.get('field_path'):
            raw_score = extract_by_path(resp_data, main_param['field_path'])
        reasoning = ''
        if reasoning_param and reasoning_param.get('field_path'):
            reasoning = extract_by_path(resp_data, reasoning_param['field_path'], '') or ''
        if not reasoning and isinstance(resp_data, dict):
            reasoning = resp_data.get('reasoning') or ''

        if raw_score is None:
            return VERDICT_UNCERTAIN, None, reasoning

        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            logger.warning('LLM 复检主评分非法: %r', raw_score)
            return VERDICT_UNCERTAIN, None, reasoning

        rmin = _to_float(dim_config.get('result_min'), _DEFAULT_SCORE_MIN)
        rmax = _to_float(dim_config.get('result_max'), _DEFAULT_SCORE_MAX)
        threshold = _to_float(main_param.get('pass_threshold') if main_param else None, None)
        if threshold is None:
            threshold = (rmin + rmax) / 2.0

        verdict = VERDICT_PASSED if score >= threshold else VERDICT_FAILED

        if score >= threshold:
            span = rmax - threshold
            confidence = 1.0 if span <= 0 else min(1.0, (score - threshold) / span)
        else:
            span = threshold - rmin
            confidence = 1.0 if span <= 0 else min(1.0, (threshold - score) / span)
        confidence = round(confidence, 2)
        if confidence <= 0:
            confidence = 0.5

        return verdict, confidence, reasoning


def _to_float(value, default):
    """数值兜底转换：None/非法 → default。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# 模块级单例
ai_review_checker = AiReviewChecker()
