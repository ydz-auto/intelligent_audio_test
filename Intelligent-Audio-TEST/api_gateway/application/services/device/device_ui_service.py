# -*- coding: utf-8 -*-
"""设备 UI 探索网关服务（INT-2578，INT-2569 拆分卡 2/4）。

三个受控端点（网关 → gRPC ``DeviceUiService``，卡 1 / INT-2577）：

- ``POST /api/v1/test-devices/{device_id}/ui/tree``      读当前页 UI 树（``device:read``）
- ``POST /api/v1/test-devices/{device_id}/ui/screenshot`` 截图取对象键（``device:read``）
- ``POST /api/v1/test-devices/{device_id}/ui/action``     七枚举动作下发（``device:control``）

口径：

- 响应信封 ``{success, message, code, data}``，``data`` 与卡 1 gRPC 同形；
  ``code`` 是 ``UiCaptureErrorCode`` 字符串业务码，成功为空串，**原样透传**
  （调用方按 ``code`` 判型，不靠 message）。
- 业务码 → HTTP：``DEVICE_NOT_FOUND`` → 404；``ACTION_NOT_ALLOWED`` / 参数非法 /
  ``ELEMENT_NOT_FOUND`` / ``TREE_TOO_LARGE`` / ``PLATFORM_UNSUPPORTED`` → 400；
  ``BUSY`` → 409；``UI_CAPTURE_UNAVAILABLE``（含上游不可达）→ 503。
- 动作端点先按 ``UiActionType`` 七枚举白名单拦截（device_service 侧二次校验），
  每次动作请求写一条设备审计（``AuditEvent.DEVICE_CONTROL_EXECUTED``）。
- 审批 / 预算 / 破坏性拦截在 agent 层（INT-2492），本层既不复制也不绕过。
"""
from __future__ import annotations

import logging

from api_gateway.application.services.device.device_audit import write_device_audit
from api_gateway.infrastructure.acl import DeviceUiAclRepositoryImpl
from api_gateway.infrastructure.request_adapter import request
from api_gateway.schemas.device import DeviceUiActionRequest, DeviceUiScreenshotRequest
from shared.constants.ui_capture import UI_ACTION_TYPE_VALUES, UiCaptureErrorCode

logger = logging.getLogger(__name__)

_device_ui_acl = DeviceUiAclRepositoryImpl()

#: 业务码 → HTTP 状态（卡面「错误码映射 HTTP」；code 透传不靠 message 判型）
UI_ERROR_HTTP_STATUS = {
    UiCaptureErrorCode.DEVICE_NOT_FOUND.value: 404,
    UiCaptureErrorCode.ACTION_NOT_ALLOWED.value: 400,
    UiCaptureErrorCode.ELEMENT_NOT_FOUND.value: 400,
    UiCaptureErrorCode.TREE_TOO_LARGE.value: 400,
    UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value: 400,
    UiCaptureErrorCode.BUSY.value: 409,
    UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value: 503,
}

#: 未登记的业务码 = 网关与 device_service 契约不一致，按服务端错误暴露（不掩成 400）
DEFAULT_ERROR_HTTP_STATUS = 500

#: 审计模块标识（同 DeviceCommandService 的 device_control / device_batch 口径）
AUDIT_MODULE = 'device_ui'


def http_status_for_code(code):
    """业务码 → HTTP 状态；None / 空串 / 未登记码走默认。"""
    return UI_ERROR_HTTP_STATUS.get((code or '').strip(), DEFAULT_ERROR_HTTP_STATUS)


def _envelope(result):
    """ACL 结果 → (统一信封, HTTP 状态)。

    成功固定 200；失败按业务码映射，``code`` 原样透传。
    """
    payload = {
        'success': bool(result.get('success')),
        'message': result.get('message') or '',
        'code': result.get('code') or '',
        'data': result.get('data'),
    }
    if payload['success']:
        return payload, 200
    return payload, http_status_for_code(payload['code'])


def _error(message, code, data=None):
    """网关侧显式失败（业务码取 UiCaptureErrorCode 值）。"""
    return (
        {'success': False, 'message': message, 'code': code, 'data': data},
        http_status_for_code(code),
    )


def _audit_action(device_id, action_type, node, params, result):
    """动作请求设备审计：每次动作调用一条（成功 / 被拦截 / 设备拒绝都记）。"""
    from shared.models.common_enums import AuditEvent

    write_device_audit(
        AuditEvent.DEVICE_CONTROL_EXECUTED,
        AUDIT_MODULE,
        {
            'device_id': device_id,
            'action_type': action_type,
            'node': node or {},
            'params': params or {},
            'success': bool(result.get('success')),
            'code': result.get('code') or '',
        },
    )


class DeviceUiService:
    """设备 UI 探索网关应用服务（读树 / 截图读侧，动作命令侧）。"""

    # ==================== 读树 ====================

    @staticmethod
    def dump_tree(device_id):
        """读当前页 UI 树（不裁剪；裁剪在 agent 侧）。请求体 ``{}``，不解析。"""
        return _envelope(_device_ui_acl.dump_ui_tree(device_id))

    # ==================== 截图 ====================

    @staticmethod
    def capture_screenshot(device_id):
        """截取当前屏，只回 ``screenshot_ref`` 对象键（不回 base64 整图）。"""
        try:
            body = DeviceUiScreenshotRequest.model_validate(request.get_json() or {})
        except Exception as e:  # noqa: BLE001 — 参数体非法按 400 显式拒绝
            return _error(
                f'请求数据验证失败: {e}',
                UiCaptureErrorCode.ACTION_NOT_ALLOWED.value,
            )
        return _envelope(
            _device_ui_acl.capture_ui_screenshot(device_id, label=body.label))

    # ==================== 动作 ====================

    @staticmethod
    def perform_action(device_id):
        """下发一个 ``UiActionType`` 动作；非七枚举一律 400 ``ACTION_NOT_ALLOWED``。"""
        try:
            body = DeviceUiActionRequest.model_validate(request.get_json() or {})
        except Exception as e:  # noqa: BLE001 — 参数体非法按 400 显式拒绝
            return _error(
                f'请求数据验证失败: {e}',
                UiCaptureErrorCode.ACTION_NOT_ALLOWED.value,
            )

        action_type = (body.action_type or '').strip().upper()
        node = body.node or {}
        params = body.params or {}

        # 七枚举白名单：网关先拦（device_service 侧二次校验，见卡 1）
        if action_type not in UI_ACTION_TYPE_VALUES:
            result = {
                'success': False,
                'message': (f'action_type 必须是 {" / ".join(UI_ACTION_TYPE_VALUES)}，'
                            f'收到 {body.action_type!r}'),
                'code': UiCaptureErrorCode.ACTION_NOT_ALLOWED.value,
                'data': {'action_type': action_type},
            }
            _audit_action(device_id, action_type, node, params, result)
            return _envelope(result)

        result = _device_ui_acl.perform_ui_action(
            device_id, action_type, node=node, params=params)
        _audit_action(device_id, action_type, node, params, result)
        return _envelope(result)
