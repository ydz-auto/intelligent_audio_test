# -*- coding: utf-8 -*-
"""设备 UI 探索 gRPC servicer（INT-2569 / INT-2577，系列卡 1/4）。

`DeviceUiServiceServicer` 暴露三个 RPC：

- ``DumpUiTree(device_id)``         → 平台原始 UI 树（不裁剪，裁剪在 agent 侧）
- ``PerformUiAction(device_id, action_type, node, params)`` → 七枚举动作下发
- ``CaptureUiScreenshot(device_id, label)`` → 截图上 OSS，返回对象键

约定（卡面「接口与数据模型」）：

- 响应信封 ``success`` / ``message`` / ``code`` / ``data``(JSON)；``code`` 取
  ``UiCaptureErrorCode`` 值显式判型（成功为空串），调用方不得靠 ``message`` 字符串判型。
- 三个 RPC 共用**任务执行的那把同 SN 锁**（``device_runtime_servicers`` 的
  ``_device_step_lock``），等待预算按调用方 deadline 收敛，超时返回 ``BUSY`` + 持锁快照。
- 降级一律显式：驱动抛 ``UiCaptureUnavailable`` → ``UI_CAPTURE_UNAVAILABLE`` /
  ``PLATFORM_UNSUPPORTED`` + 结构化 ``degrade_reason``；**不返回空树冒充成功**。
- ``payload`` 上限 8 MB，超限 ``TREE_TOO_LARGE``（不截断冒充完整树）。

结构化日志（验收卡 INT-2580 计数口径）：每次 ``PerformUiAction`` 调用写**一行**
``device.ui.action``，含 device_id / action_type / 结果；失败也写。agent 侧
``dry_run`` 不下发动作，故该时间窗内条数为 0。
"""
import contextlib
import logging
import time
import uuid

from shared.proto import device_service_pb2 as device_pb
from shared.proto import device_service_pb2_grpc as device_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps
from shared.models.common_enums import DeviceSystem
from shared.constants.ui_capture import (
    DEVICE_UI_ACTION_LOG_TAG,
    UI_ACTION_TYPE_VALUES,
    UI_TREE_PAYLOAD_MAX_BYTES,
    UiCaptureDegradeReason,
    UiCaptureErrorCode,
    UiCaptureUnavailable,
)
from device_service.interfaces.grpc.device_runtime_servicers import (
    _device_step_holder_enter,
    _device_step_holder_leave,
    _device_step_holder_snapshot,
    _device_step_lock,
    _device_step_queue_enter,
    _device_step_queue_leave,
    _device_step_wait_budget,
    _format_step_lock_timeout,
)

logger = logging.getLogger(__name__)

#: 截图上对象存储的类目（设备侧采集产物，与 E2E 采集结果同类目）
_SCREENSHOT_OSS_CATEGORY = 'case_result'
_SCREENSHOT_KEY_PREFIX = 'device-ui'
_SCREENSHOT_CONTENT_TYPE = 'image/png'

#: 支持的平台（其余 system 值一律 PLATFORM_UNSUPPORTED，不尝试取树）
_SUPPORTED_SYSTEMS = (DeviceSystem.ANDROID, DeviceSystem.HARMONYOS)


class DeviceUiBusy(RuntimeError):
    """同 SN 锁等待超时 —— 语义为 ``BUSY``，携带持锁快照供排障。"""

    def __init__(self, message, *, holder=None, waited_seconds=None,
                 queue_ahead=None):
        super().__init__(message)
        self.holder = holder or {}
        self.waited_seconds = waited_seconds
        self.queue_ahead = queue_ahead


class _ResolveError(RuntimeError):
    """设备 / 平台 / 驱动解析阶段的显式失败（带业务码与可选 data）。"""

    def __init__(self, message, code, data=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data


class _TreeTooLarge(UiCaptureUnavailable):
    """UI 树超过 8 MB 上限 —— 显式 ``TREE_TOO_LARGE``（不截断冒充完整树）。"""

    def __init__(self, message, *, size=None):
        super().__init__(message)
        self.code = UiCaptureErrorCode.TREE_TOO_LARGE.value
        self.size = size


def _holder_public(holder):
    """持锁快照（monotonic ``since`` → 已持锁秒数，其余字段原样）。"""
    if not holder:
        return {}
    public = dict(holder)
    since = public.pop('since', None)
    if since is not None:
        public['held_seconds'] = round(max(0.0, time.monotonic() - float(since)), 1)
    return public


@contextlib.contextmanager
def device_ui_serial_section(device_sn, context=None, action='ui'):
    """按设备 SN 串行的上下文管理器（复用任务执行的同一把锁与排队观测表）。

    等待预算 = 单步上界 × 排队位次，并按调用方剩余 deadline 截断
    （``_device_step_wait_budget``）；超时抛 ``DeviceUiBusy``（含持锁快照）。
    """
    from shared.infrastructure.config import BaseConfig
    base_wait = int(getattr(BaseConfig, 'DEVICE_SN_STEP_LOCK_WAIT_SECONDS', 60))
    lock = _device_step_lock(device_sn)
    ahead = _device_step_queue_enter(device_sn)
    wait_seconds = _device_step_wait_budget(base_wait, ahead, context)
    acquired = False
    try:
        acquired = lock.acquire(timeout=wait_seconds)
    finally:
        _device_step_queue_leave(device_sn)
    if not acquired:
        holder = _device_step_holder_snapshot(device_sn)
        message = _format_step_lock_timeout(
            device_sn, action, wait_seconds, ahead, holder)
        logger.warning("设备 %s 动作 %s 等待同 SN 串行锁超时(%ss)：%s",
                       device_sn, action, wait_seconds, message)
        raise DeviceUiBusy(message, holder=_holder_public(holder),
                           waited_seconds=wait_seconds, queue_ahead=ahead)
    _device_step_holder_enter(device_sn, action)
    try:
        yield
    finally:
        _device_step_holder_leave(device_sn)
        lock.release()


class DeviceUiServiceServicer(device_grpc.DeviceUiServiceServicer):
    """设备 UI 探索服务（读树 / 动作 / 截图），委托给设备驱动 + 对象存储。"""

    def __init__(self, query=None, factory=None, oss_client=None):
        #: 依赖可注入（单测替换设备查询 / 驱动工厂 / OSS 客户端）
        self._query = query
        self._factory = factory
        self._oss = oss_client

    # ==================== 依赖（懒加载，与 DeviceConfigServiceServicer 同风格） ====================

    @property
    def query(self):
        if self._query is None:
            from device_service.application.queries.device_query_service import device_query_service
            self._query = device_query_service
        return self._query

    @property
    def factory(self):
        if self._factory is None:
            from device_service.infrastructure.drivers.driver_factory import device_driver_factory
            self._factory = device_driver_factory
        return self._factory

    @property
    def oss(self):
        if self._oss is None:
            from shared.clients.oss_client import oss
            self._oss = oss
        return self._oss

    # ==================== RPC ====================

    def DumpUiTree(self, request, context=None):
        return self._dispatch(
            device_pb.DumpUiTreeResponse, request.device_id, 'DumpUiTree',
            context, self._dump_ui_tree)

    def PerformUiAction(self, request, context=None):
        action_type = (request.action_type or '').strip().upper()
        try:
            node = _loads(request.node, {}) if request.node else {}
            params = _loads(request.params, {}) if request.params else {}
        except (ValueError, TypeError) as e:
            # 参数体不是合法 JSON：显式拒绝（不抛未捕获异常、不静默当空参数下发）
            return self._error_response(
                device_pb.PerformUiActionResponse,
                f'node / params 不是合法 JSON：{e}',
                UiCaptureErrorCode.ACTION_NOT_ALLOWED.value,
                {'action_type': action_type})
        return self._dispatch_ui_action(
            device_pb.PerformUiActionResponse, request.device_id, context,
            action_type, node, params)

    def CaptureUiScreenshot(self, request, context=None):
        return self._dispatch(
            device_pb.CaptureUiScreenshotResponse, request.device_id,
            'CaptureUiScreenshot', context, self._capture_ui_screenshot)

    # ==================== 公共流程 ====================

    def _dispatch(self, response_cls, device_id, action, context, handler):
        """统一流程：取设备 → 平台 / 驱动解析 → 同 SN 串行 → 执行 → 信封。"""
        try:
            device, driver, serial = self._resolve(device_id)
        except _ResolveError as e:
            return self._error_response(response_cls, e.message, e.code, e.data)
        try:
            with device_ui_serial_section(serial, context, action):
                data = handler(device, driver, serial)
        except DeviceUiBusy as e:
            return self._busy_response(response_cls, e)
        except _TreeTooLarge as e:
            return self._error_response(
                response_cls, str(e), self._degrade_code(e),
                {'degraded': False, 'degrade_reason': None, 'size_bytes': e.size})
        except UiCaptureUnavailable as e:
            return self._degrade_response(response_cls, e)
        except Exception as e:  # 未预期异常也要显式失败，不返回空 data 冒充成功
            logger.error('device_ui.%s device_id=%s 未预期失败: %s',
                         action, device_id, e, exc_info=True)
            return self._error_response(
                response_cls, f'{action} 执行失败：{e}',
                UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value)
        return self._ok_response(response_cls, data)

    def _dispatch_ui_action(self, response_cls, device_id, context, action_type,
                            node, params):
        """动作 RPC：白名单校验 + 每调用一行 ``device.ui.action`` 日志（失败也写）。"""
        started = time.monotonic()
        result = UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value
        try:
            if action_type not in UI_ACTION_TYPE_VALUES:
                result = UiCaptureErrorCode.ACTION_NOT_ALLOWED.value
                return self._error_response(
                    response_cls,
                    f'action_type 必须是 {" / ".join(UI_ACTION_TYPE_VALUES)}，'
                    f'收到 {action_type!r}',
                    result, {'action_type': action_type})
            try:
                device, driver, serial = self._resolve(device_id)
            except _ResolveError as e:
                result = e.code
                return self._error_response(response_cls, e.message, e.code, e.data)
            try:
                with device_ui_serial_section(serial, context, 'PerformUiAction'):
                    body = self._perform_ui_action(
                        device, driver, serial, action_type, node, params)
                body['elapsed_ms'] = int((time.monotonic() - started) * 1000)
                result = 'performed'
                return self._ok_response(response_cls, body)
            except DeviceUiBusy as e:
                result = UiCaptureErrorCode.BUSY.value
                return self._busy_response(response_cls, e)
            except UiCaptureUnavailable as e:
                result = self._degrade_code(e)
                return self._degrade_response(response_cls, e)
            except Exception as e:
                logger.error('device_ui.PerformUiAction device_id=%s 未预期失败: %s',
                             device_id, e, exc_info=True)
                return self._error_response(
                    response_cls, f'PerformUiAction 执行失败：{e}', result)
        finally:
            self._log_ui_action(device_id, action_type, result,
                                int((time.monotonic() - started) * 1000))

    @staticmethod
    def _log_ui_action(device_id, action_type, result, elapsed_ms):
        """结构化动作日志（每下发一个动作一行，失败也写，带结果）。"""
        logger.info('%s device_id=%s action_type=%s result=%s elapsed_ms=%s',
                    DEVICE_UI_ACTION_LOG_TAG, device_id, action_type, result,
                    elapsed_ms)

    def _resolve(self, device_id):
        """设备实体 → 驱动 → 序列号。

        ``DeviceQueryService.get_one`` 返回信封 ``{success,message,data,code}``，
        设备字段在 ``resp['data']``（不是实体本身）。
        """
        try:
            device_id = int(device_id)
        except (TypeError, ValueError):
            raise _ResolveError(f'device_id 非法：{device_id!r}',
                                UiCaptureErrorCode.DEVICE_NOT_FOUND.value)
        resp = self.query.get_one(device_id)
        if not resp or not resp.get('success'):
            raise _ResolveError(
                (resp or {}).get('message') or f'设备 {device_id} 不存在',
                UiCaptureErrorCode.DEVICE_NOT_FOUND.value)
        device = resp.get('data') or {}
        system_name = device.get('system')
        try:
            system = DeviceSystem.normalize(system_name)
        except ValueError as e:
            raise _ResolveError(str(e), UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value)
        if system not in _SUPPORTED_SYSTEMS:
            raise _ResolveError(
                f'设备 {device_id} 的平台 {system_name!r} 不支持 UI 探索'
                f'（支持：{" / ".join(s.value for s in _SUPPORTED_SYSTEMS)}）',
                UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value)
        serial = str(device.get('serial_number') or '').strip()
        if not serial:
            raise _ResolveError(
                f'设备 {device_id} 未登记序列号，无法与任务执行串行（同 SN 锁）',
                UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value,
                {'degraded': True,
                 'degrade_reason': UiCaptureDegradeReason.DRIVER_UNAVAILABLE.value})
        try:
            driver = self.factory.get_driver_for_device(
                system.value, keywords=device.get('keywords'), device_sn=serial)
        except ValueError as e:
            # keywords 缺失 / 未注册 / 平台不匹配：驱动配置问题，不是「平台不支持」
            raise _ResolveError(
                f'设备 {device_id} 驱动解析失败：{e}',
                UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value,
                {'degraded': True,
                 'degrade_reason': UiCaptureDegradeReason.DRIVER_UNAVAILABLE.value})
        return device, driver, serial

    # ==================== 三个 RPC 的业务实现 ====================

    def _dump_ui_tree(self, device, driver, serial):
        tree = driver.dump_ui_tree(serial)
        platform = tree.get('platform')
        tree_format = tree.get('format')
        payload = tree.get('payload')
        if not platform or not tree_format or payload is None:
            # 驱动契约：要么 platform/format/payload 齐备，要么抛 UiCaptureUnavailable
            raise UiCaptureUnavailable(
                f'设备 {serial} 驱动返回的 UI 树缺少 platform/format/payload',
                reason=UiCaptureDegradeReason.TREE_UNREADABLE)
        encoded = payload.encode('utf-8') if isinstance(payload, str) else payload
        if len(encoded) > UI_TREE_PAYLOAD_MAX_BYTES:
            # 显式失败：不截断冒充完整树（裁剪只在 agent 侧 crop_nodes 生效）
            raise _TreeTooLarge(
                f'设备 {serial} UI 树 {len(encoded)} 字节超过 '
                f'{UI_TREE_PAYLOAD_MAX_BYTES} 字节上限', size=len(encoded))
        return {
            'platform': platform,
            'format': tree_format,
            'payload': payload,
            'node_count': int(tree.get('node_count') or 0),
            'degraded': False,
            'degrade_reason': None,
        }

    def _perform_ui_action(self, device, driver, serial, action_type,
                           node, params):
        result = driver.perform_ui_action(
            serial, action_type, node=node, params=params)
        return {
            'action_type': result.get('action_type') or action_type,
            'performed': bool(result.get('performed', True)),
        }

    def _capture_ui_screenshot(self, device, driver, serial):
        shot = driver.capture_ui_screenshot(serial)
        png = shot.get('png')
        if not png:
            raise UiCaptureUnavailable(
                f'设备 {serial} 截图内容为空',
                reason=UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE)
        return {
            'screenshot_ref': self._upload_screenshot(serial, png),
            'format': shot.get('format') or 'PNG',
            'width': int(shot.get('width') or 0),
            'height': int(shot.get('height') or 0),
        }

    def _upload_screenshot(self, serial, png):
        """上传 PNG 到对象存储，返回对象键 ``device-ui/<sn>/<ts>-<rand>.png``。"""
        key = (f'{_SCREENSHOT_KEY_PREFIX}/{serial}/'
               f'{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png')
        try:
            return self.oss.upload_bytes(
                png, _SCREENSHOT_OSS_CATEGORY, key,
                content_type=_SCREENSHOT_CONTENT_TYPE) or key
        except Exception as e:
            raise UiCaptureUnavailable(
                f'设备 {serial} 截图上传对象存储失败：{e}',
                reason=UiCaptureDegradeReason.SCREENSHOT_UNAVAILABLE) from e

    # ==================== 响应信封 ====================

    @staticmethod
    def _ok_response(response_cls, data):
        return response_cls(success=True, message='ok', code='', data=_dumps(data))

    @staticmethod
    def _error_response(response_cls, message, code, data=None):
        return response_cls(success=False, message=message, code=code,
                            data=_dumps(data) if data is not None else '')

    @staticmethod
    def _degrade_code(exc):
        """显式降级 → 业务码：带 code 的直取，平台不支持单列，其余归不可用。"""
        if getattr(exc, 'code', None):
            return exc.code
        if getattr(exc, 'reason', None) == UiCaptureDegradeReason.PLATFORM_NOT_SUPPORTED.value:
            return UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value
        return UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value

    def _degrade_response(self, response_cls, exc):
        return self._error_response(
            response_cls, str(exc), self._degrade_code(exc),
            {'degraded': True, 'degrade_reason': getattr(exc, 'reason', None)})

    def _busy_response(self, response_cls, exc):
        return self._error_response(
            response_cls, str(exc), UiCaptureErrorCode.BUSY.value,
            {'holder': exc.holder,
             'waited_seconds': exc.waited_seconds,
             'queue_ahead': exc.queue_ahead})


__all__ = ['DeviceUiServiceServicer', 'DeviceUiBusy', 'device_ui_serial_section']
