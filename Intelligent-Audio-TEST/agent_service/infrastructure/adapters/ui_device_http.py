# -*- coding: utf-8 -*-
"""设备 UI 探索端口的网关 HTTP 适配器（INT-2579，INT-2569 拆分卡 3/4）。

把 ``UiDevicePort`` 落到已合入的网关三端点（卡 2 / INT-2578）上：

- ``platform``   → ``GET  /api/v1/test-devices/{device_id}``（``device:read``）
- ``dump_nodes`` → ``POST /api/v1/test-devices/{device_id}/ui/tree``（``device:read``）
- ``perform``    → ``POST /api/v1/test-devices/{device_id}/ui/action``（``device:control``）
- ``screenshot`` → ``POST /api/v1/test-devices/{device_id}/ui/screenshot``（``device:read``）

口径（卡面「可测验收标准」）：

- **凭据来自 run，不硬编码**：``holder``（= ``run_id``）经
  ``RunCredentialRegistry.get`` 取该 run 的 ``Authorization``，随 ``RestToolClient``
  回源；取不到凭据在**发请求之前**抛 ``UiDeviceError(code='DEVICE_UNAVAILABLE')``
  —— 这正是会话建立时 ``platform`` 作为第一个设备调用的预期失败（卡面「顺序注意」）。
- **业务码原样透传**：网关信封 ``{success, message, code, data}`` 的 ``code``
  （``UiCaptureErrorCode``，如 ``DEVICE_NOT_FOUND`` / ``PLATFORM_UNSUPPORTED`` /
  ``BUSY`` / ``ACTION_NOT_ALLOWED``）直接作为 ``UiDeviceError.code``，不靠
  ``message`` 判型；网络层失败（``status=0``）与无法解析的信封按
  ``UI_CAPTURE_UNAVAILABLE`` 归类。
- **解析只有一份**：树解析复用 INT-2492 的唯一口径
  ``parse_android_hierarchy`` / ``parse_harmony_components``（内部走
  ``normalize_node``），裁剪复用 ``crop_nodes``（上限 ``MAX_TREE_NODES=200``）。
  本模块不留第二份归一化，未知 ``format`` 一律显式失败而不猜。
- **不返回空树**：解析失败 / ``payload`` 缺失都抛 ``UiDeviceError``（审计红线同
  INT-296 / INT-2577）；截图缺引用返回 ``None``（端口约定「平台不支持取截图」）。
- 适配器无进程内状态（不缓存树 / 平台），并发安全由应用层会话锁负责。

``platform`` 走 ``device_get`` 而非读树端点：卡 2 的三个端点里只有读树返回
``platform``，而读整页树只为取平台名会白拉一次最大 8 MB 的 payload（且大页面
会在会话建立时先撞 ``TREE_TOO_LARGE``）。``device_get`` 的 ``system`` 正是卡 1
``_resolve`` 用来判平台的同一字段，取 ``DeviceSystem.normalize`` 归一后的枚举名
（``ANDROID`` / ``HARMONYOS``），与端口文档的取值口径一致；未知系统按卡 1 的同一
分类返回 ``PLATFORM_UNSUPPORTED``。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolTransportPort,
)
from agent_service.domain.ports.ui_device import UiDeviceError, UiDevicePort
from shared.agent_tools import ui_exploration as ux
from shared.constants.ui_capture import UiCaptureErrorCode, UiTreeFormat

logger = logging.getLogger(__name__)

DEVICE_UI_PATH_PREFIX = '/api/v1/test-devices'
DEVICE_GET_TOOL = 'device_get'


def _tool(name: str, method: str, path: str, *,
          path_params: Sequence[str] = (),
          query_params: Sequence[str] = ()) -> Dict[str, Any]:
    """构造与 ``RestToolClient`` / ``mcp_registry.build_path`` 同形的工具描述。

    这三个端点与 ``device_get`` 不是 Agent 可见工具（不在 MCP 注册表里暴露），
    因此在此按同一字段口径就地描述，走同一个 ``RestToolClient.call`` 回源，
    不复制注册表的 Schema。
    """
    return {
        'name': name,
        'method': method.upper(),
        'path': path,
        'path_params': list(path_params),
        'query_params': list(query_params),
    }


_DEVICE_GET = _tool(DEVICE_GET_TOOL, 'GET', f'{DEVICE_UI_PATH_PREFIX}/{{device_id}}',
                    path_params=('device_id',))
_UI_TREE = _tool('device_ui_tree', 'POST',
                 f'{DEVICE_UI_PATH_PREFIX}/{{device_id}}/ui/tree',
                 path_params=('device_id',))
_UI_SCREENSHOT = _tool('device_ui_screenshot', 'POST',
                       f'{DEVICE_UI_PATH_PREFIX}/{{device_id}}/ui/screenshot',
                       path_params=('device_id',))
_UI_ACTION = _tool('device_ui_action', 'POST',
                   f'{DEVICE_UI_PATH_PREFIX}/{{device_id}}/ui/action',
                   path_params=('device_id',))

#: agent 侧业务码：调用方凭据缺失 / 网关鉴权失败（不是 ``UiCaptureErrorCode``
#: 的成员 —— 那个枚举是设备 UI RPC / 网关端点的显式业务码；凭据缺失发生在
#: 回源之前，按端口既有口径 ``DEVICE_UNAVAILABLE`` 失败，与卡面一致）。
DEVICE_UNAVAILABLE = 'DEVICE_UNAVAILABLE'

#: 网关信封缺 ``code`` 时按 HTTP 状态归类（与 INT-2578 的 code → HTTP 表对称，
#: 只用于「拿不到业务码」的兜底；有 code 时一律原样透传）。
STATUS_ERROR_CODES: Dict[int, str] = {
    400: UiCaptureErrorCode.ACTION_NOT_ALLOWED.value,
    401: DEVICE_UNAVAILABLE,
    403: DEVICE_UNAVAILABLE,
    404: UiCaptureErrorCode.DEVICE_NOT_FOUND.value,
    409: UiCaptureErrorCode.BUSY.value,
    503: UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value,
}

#: 默认业务码：网关不可达 / 响应不是信封 / 契约不一致
DEFAULT_ERROR_CODE = UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value


class UiDeviceHttpAdapter(UiDevicePort):
    """``UiDevicePort`` 的网关 REST 实现（INT-2579）。

    依赖两个端口：``rest``（``RestToolClient``，负责构造并发出网关请求）与
    ``credentials``（``RunCredentialRegistry``，run → Authorization）。两者都由
    组合根注入，本类不读环境、不建连接。
    """

    def __init__(self, *, rest: ToolTransportPort,
                 credentials: RunCredentialPort):
        self._rest = rest
        self._credentials = credentials

    # ------------------------------------------------------------ 端口方法

    def platform(self, device_id: int, *, holder: str) -> str:
        """设备平台（``ANDROID`` / ``HARMONYOS``）；未知系统 → ``PLATFORM_UNSUPPORTED``。"""
        data = self._call(_DEVICE_GET, {'device_id': int(device_id)},
                          holder=holder, permissions=('device:read',))
        system = str((data or {}).get('system') or '').strip()
        try:
            from shared.models.common_enums import DeviceSystem

            return DeviceSystem.normalize(system).name
        except (ValueError, TypeError) as exc:
            # 与卡 1 ``DeviceUiServiceServicer._resolve`` 同一分类：系统值不可识别
            # 的设备做不了 UI 探索，显式 PLATFORM_UNSUPPORTED，不猜成 ANDROID。
            raise UiDeviceError(
                f'设备 {device_id} 的平台无法用于 UI 探索：{exc}',
                code=UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value) from exc

    def dump_nodes(self, device_id: int, *, max_nodes: int, holder: str
                   ) -> Dict[str, Any]:
        """读一页 UI 树 → ``{'nodes': 裁剪后节点, 'coverage': 覆盖摘要}``。"""
        data = self._call(_UI_TREE, {'device_id': int(device_id)},
                          holder=holder, permissions=('device:read',))
        nodes = self._parse_tree(data)
        cropped, _stats = ux.crop_nodes(nodes, max_nodes)
        coverage = ux.coverage_notes(
            nodes, str((data or {}).get('platform') or 'ANDROID'))
        return {'nodes': cropped, 'coverage': coverage}

    def perform(self, device_id: int, action_type: str, *,
                node: Optional[Dict[str, Any]] = None,
                params: Optional[Dict[str, Any]] = None,
                holder: str) -> Dict[str, Any]:
        """下发一个 ``UiActionType`` 动作，返回网关动作结果（含 ``applied``）。"""
        data = self._call(
            _UI_ACTION,
            {'device_id': int(device_id), 'action_type': action_type,
             'node': dict(node or {}), 'params': dict(params or {})},
            holder=holder, permissions=('device:control',))
        performed = bool((data or {}).get('performed', True))
        result = {
            'action_type': (data or {}).get('action_type') or action_type,
            # 网关口径是 ``performed``；编排层（INT-2492 build_action_record）
            # 读的是 ``applied``，在此对齐，避免缺字段被默认成「已生效」。
            'performed': performed,
            'applied': performed,
        }
        elapsed = (data or {}).get('elapsed_ms')
        if elapsed is not None:
            result['elapsed_ms'] = elapsed
        return result

    def screenshot(self, device_id: int, *, label: str = '', holder: str
                   ) -> Optional[str]:
        """截图并取对象存储引用；网关成功但缺引用按「无截图」返回 ``None``。"""
        data = self._call(
            _UI_SCREENSHOT,
            {'device_id': int(device_id), 'label': str(label or '')},
            holder=holder, permissions=('device:read',))
        ref = (data or {}).get('screenshot_ref')
        if not ref:
            logger.warning('设备 %s 截图响应缺少 screenshot_ref，按无截图处理',
                           device_id)
            return None
        return str(ref)

    # ------------------------------------------------------------ 内部

    def _authorization(self, holder: str) -> str:
        """取 run 的 Authorization；缺失即失败（绝不匿名回源）。"""
        authorization = self._credentials.get(holder) if holder else None
        if not authorization:
            raise UiDeviceError(
                f'run {holder or "?"} 缺少调用方凭据（Authorization）：'
                '设备 UI 通道按 DEVICE_UNAVAILABLE 显式失败，不以匿名身份回源网关。',
                code=DEVICE_UNAVAILABLE)
        return authorization

    def _call(self, tool: Dict[str, Any], arguments: Dict[str, Any], *,
              holder: str, permissions: Sequence[str]) -> Dict[str, Any]:
        """发一次网关请求并解信封；失败一律抛 ``UiDeviceError``。"""
        authorization = self._authorization(holder)
        result = self._rest.call(tool, arguments,
                                 authorization=authorization,
                                 permissions=tuple(permissions))
        if result.status == 0:
            raise UiDeviceError(
                f'设备 UI 通道不可达（{tool["name"]}）：'
                f'{result.error or "网络层失败"}',
                code=DEFAULT_ERROR_CODE)

        payload = result.payload
        envelope = payload if isinstance(payload, dict) else None
        code = str((envelope or {}).get('code') or '').strip()
        success = bool((envelope or {}).get('success'))
        if envelope is None or not result.ok or not success:
            message = str((envelope or {}).get('message') or '').strip()
            if not message:
                message = (f'设备 UI 请求失败（{tool["name"]}，HTTP {result.status}）：'
                           f'{(result.text or "")[:200]}')
            raise UiDeviceError(
                message, code=code or self._fallback_code(result.status))

        data = envelope.get('data')
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _fallback_code(status: int) -> str:
        return STATUS_ERROR_CODES.get(int(status or 0), DEFAULT_ERROR_CODE)

    @staticmethod
    def _parse_tree(data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按网关 ``format`` 调 INT-2492 的唯一解析口径（不猜、不返回空树）。"""
        if not isinstance(data, dict):
            raise UiDeviceError(
                '设备 UI 树响应体不是对象：网关契约不一致',
                code=DEFAULT_ERROR_CODE)
        tree_format = str(data.get('format') or '').strip().upper()
        payload = data.get('payload')
        if payload is None:
            raise UiDeviceError(
                f'设备 UI 树缺少 payload（format={tree_format or "?"}），'
                '不返回空树冒充「页面没有元素」',
                code=DEFAULT_ERROR_CODE)
        try:
            if tree_format == UiTreeFormat.ANDROID_XML.value:
                return ux.parse_android_hierarchy(
                    payload if isinstance(payload, str) else str(payload))
            if tree_format == UiTreeFormat.HARMONY_COMPONENTS.value:
                components = payload
                if isinstance(payload, str):
                    components = json.loads(payload)
                return ux.parse_harmony_components(components)
        except ux.UiTreeParseError as exc:
            raise UiDeviceError(
                f'设备 UI 树解析失败（format={tree_format}）：{exc}',
                code=DEFAULT_ERROR_CODE) from exc
        except (ValueError, TypeError) as exc:  # JSON 解码 / 结构非法
            raise UiDeviceError(
                f'设备 UI 树 payload 不是合法结构（format={tree_format}）：{exc}',
                code=DEFAULT_ERROR_CODE) from exc
        raise UiDeviceError(
            f'未知的设备 UI 树格式 {tree_format!r}：网关与 agent 契约不一致，'
            '拒绝猜测解析', code=DEFAULT_ERROR_CODE)


__all__ = [
    'DEFAULT_ERROR_CODE', 'DEVICE_GET_TOOL', 'DEVICE_UI_PATH_PREFIX',
    'DEVICE_UNAVAILABLE', 'STATUS_ERROR_CODES', 'UiDeviceHttpAdapter',
]
