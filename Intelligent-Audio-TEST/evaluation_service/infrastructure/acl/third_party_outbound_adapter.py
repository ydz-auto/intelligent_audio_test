# -*- coding: utf-8 -*-
"""第三方评估出站适配器 — ThirdPartyEvalPort 经 T-B 出站投递契约实现（设计文档 §4.2.2 步骤⑤）。

B→C 数据面统一走 transfer_agent 出站腿（F2.1/INT-49 起，直连 C 的适配器已退役）：
本适配器将 EVAL_REQUEST 投递委托给 T-B 出站端点
（POST /internal/transfer/outbound/{transfer_id}/dispatch），C 契约形态
（multipart / feature_extract / presigned PUT）作为投递参数随请求下发，
由 T-B 出站投递腿执行；EVAL_RESULT 语义校验（响应解析 + 必填字段）留在本侧。
"""
from __future__ import annotations

from shared.models.common_enums import ThirdPartyAdapterKind

from evaluation_service.domain.repositories.third_party_eval_port import (
    ThirdPartyEvalPort,
    ThirdPartyEvalRequest,
    ThirdPartyEvalResult,
)


class ThirdPartyEvalAdapterError(Exception):
    """第三方评估调用层错误（投递结果/协议/校验语义）。"""


def _validate_required_keys(data: dict, required_keys) -> None:
    for key in required_keys or []:
        if key not in data:
            raise ThirdPartyEvalAdapterError(f'EVAL_RESULT 缺少必填字段: {key}')


class TransferAgentOutboundEvalAdapter(ThirdPartyEvalPort):
    """经 T-B 出站投递契约调 C 的端口实现（全部契约形态统一出站）。

    传输层异常（transfer_agent 不可达，ThirdPartyEvalError）原样上抛，
    由编排层按 stage=transfer 审计；投递结果与评估语义错误进 result。
    """

    def __init__(self, client):
        self._client = client

    def evaluate(self, request: ThirdPartyEvalRequest) -> ThirdPartyEvalResult:
        kind = str(request.eval_params.get('adapter') or '')
        try:
            kind_enum = ThirdPartyAdapterKind(kind)
        except ValueError:
            return ThirdPartyEvalResult(
                ok=False, transfer_id=request.transfer_id,
                error=f'非法第三方评估适配形态: {kind}'
                      f'（允许 {", ".join(k.value for k in ThirdPartyAdapterKind)}）')
        # 投递 token 按暂存包自身路由（中枢内联 B→C 与中转 A→B 包路由不同）；
        # 中枢内联流 manifest 路由即 (self_zone, 'C')，中转流由 execute_incoming 注入
        route = request.eval_params.get('package_route') or {}
        src_zone = str(route.get('src') or request.src_zone)
        dst_zone = str(route.get('dst') or request.dst_zone)
        view = self._client.dispatch_outbound(
            transfer_id=request.transfer_id, adapter_kind=kind_enum.value,
            src_zone=src_zone, dst_zone=dst_zone)
        if not view.get('delivered'):
            return ThirdPartyEvalResult(
                ok=False, transfer_id=request.transfer_id,
                status_code=view.get('dst_status'),
                error=str(view.get('error') or 'C 端投递失败'))
        return self._parse_result(view, request)

    # ---- EVAL_RESULT 解析与校验（8 步流程之④结果回传 ⑤校验）----
    def _parse_result(self, view: dict, request: ThirdPartyEvalRequest) -> ThirdPartyEvalResult:
        status_code = view.get('dst_status')
        data = view.get('dst_body')
        if not isinstance(data, dict) or not data:
            return ThirdPartyEvalResult(
                ok=False, transfer_id=request.transfer_id, status_code=status_code,
                error='第三方 API 响应为空或非对象')
        if 'code' in data and data.get('code') not in (0, '0'):
            return ThirdPartyEvalResult(
                ok=False, transfer_id=request.transfer_id, status_code=status_code,
                error=f"第三方评估失败: {data.get('msg') or data.get('message') or '未知错误'}")
        try:
            _validate_required_keys(data, request.eval_params.get('response_required_keys'))
        except ThirdPartyEvalAdapterError as e:
            return ThirdPartyEvalResult(
                ok=False, transfer_id=request.transfer_id,
                status_code=status_code, error=str(e))
        return ThirdPartyEvalResult(ok=True, transfer_id=request.transfer_id,
                                    data=data, status_code=status_code)


class ThirdPartyEvalAdapterFactory:
    """适配器工厂 — 契约形态 fail-closed 校验后绑定 T-B 出站实现（INT-49 起统一出站）。"""

    def create(self, kind: str, client) -> ThirdPartyEvalPort:
        try:
            ThirdPartyAdapterKind(str(kind).lower())
        except ValueError:
            raise ValueError(
                f'非法第三方评估适配形态: {kind}'
                f'（允许 {", ".join(k.value for k in ThirdPartyAdapterKind)}）')
        return TransferAgentOutboundEvalAdapter(client=client)
