# -*- coding: utf-8 -*-
"""设备驱动 / 结果采集 / 环境设备 gRPC servicer（从 servicers.py 拆分，P4-4）。

- DeviceServiceServicer：设备驱动服务，委托给 device_driver_factory
- DeviceResultServiceServicer：设备结果采集，委托给 device_result_collector
- EnvDeviceServiceServicer：环境设备控制，委托给 EnvDeviceFactory
"""
import functools
import logging
import threading
import time

from shared.proto import device_service_pb2 as e2e_pb
from shared.proto import device_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps
from shared.utils.status_constants import ExecutionStatus

logger = logging.getLogger(__name__)

# ==================== 同 SN 步骤互斥 ====================
# 同一台设备上的多个被测 App（如同一 SN 的小艺/豆包两条设备记录）并发执行
# initialize/pre_process/post_process/get_results 时会互相打断设备端 uitest
# 守护（实测两个驱动同时 pkill/start-daemon → 双双初始化失败）。步骤统一按
# 设备 SN 串行；不同 SN 不受影响，仍可并行。
_SERIALIZED_ACTIONS = frozenset({
    'initialize', 'pre_process', 'post_process', 'get_results',
    'extract_results_from_archive', 'get_final_results', 'teardown',
})
_device_step_locks = {}
# 持锁者 / 排队者观测表（INT-2257）：超时消息要能说清「排队」还是「卡死」——
# 前者说明前方步骤还在正常跑（持锁动作 + 已持锁时长），后者持锁时长会持续增长。
_device_step_holders = {}
_device_step_waiters = {}
_device_step_locks_lock = threading.Lock()

# 等待预算与调用方 deadline 之间的响应余量（秒）：等待必须在调用方放弃之前收敛，
# 留这段时间把超时消息送达；否则调用方只看到 DEADLINE_EXCEEDED，无法区分排队与卡死。
_CALLER_DEADLINE_RESPONSE_MARGIN_SECONDS = 5.0


def _device_step_lock(device_sn):
    with _device_step_locks_lock:
        return _device_step_locks.setdefault(device_sn, threading.RLock())


def _device_step_queue_enter(device_sn):
    """登记排队，返回排队时前方的步骤数（当前持锁者 + 已排队者）。"""
    with _device_step_locks_lock:
        ahead = (1 if _device_step_holders.get(device_sn) else 0)
        ahead += _device_step_waiters.get(device_sn, 0)
        _device_step_waiters[device_sn] = _device_step_waiters.get(device_sn, 0) + 1
        return ahead


def _device_step_queue_leave(device_sn):
    with _device_step_locks_lock:
        remaining = _device_step_waiters.get(device_sn, 0) - 1
        if remaining > 0:
            _device_step_waiters[device_sn] = remaining
        else:
            _device_step_waiters.pop(device_sn, None)


def _device_step_holder_enter(device_sn, action):
    with _device_step_locks_lock:
        _device_step_holders[device_sn] = {
            'action': action,
            'thread': threading.current_thread().name,
            'since': time.monotonic(),
        }


def _device_step_holder_leave(device_sn):
    with _device_step_locks_lock:
        _device_step_holders.pop(device_sn, None)


def _device_step_holder_snapshot(device_sn):
    with _device_step_locks_lock:
        holder = _device_step_holders.get(device_sn)
        return dict(holder) if holder else None


def _caller_time_remaining(context):
    """调用方剩余 deadline（秒）；非 gRPC 上下文 / 无 deadline 时返回 None。"""
    remaining_fn = getattr(context, 'time_remaining', None) if context is not None else None
    if not callable(remaining_fn):
        return None
    try:
        value = remaining_fn()
        return None if value is None else float(value)
    except Exception:  # 上下文已失效等，按「无 deadline」处理，不因观测失败阻断步骤
        return None


def _device_step_wait_budget(base_wait, ahead, context):
    """本次等待预算（秒）：单步上界 × 排队位次，并收敛到调用方剩余 deadline 之内。

    单步耗时上界扣除后立即释放锁，因此第 N 位最多等 N 个单步；再按调用方剩余
    deadline 截断，保证「等待 < 调用方 deadline」——超时消息能先于 deadline 送达
    调用方，而不是被 DEADLINE_EXCEEDED 掩盖。
    """
    budget = max(1, int(base_wait)) * max(1, ahead)
    remaining = _caller_time_remaining(context)
    if remaining is not None:
        budget = min(budget, max(1, int(remaining - _CALLER_DEADLINE_RESPONSE_MARGIN_SECONDS)))
    return budget


def _format_step_lock_timeout(device_sn, action, wait_seconds, ahead, holder):
    """超时文案：保留原「同 SN 步骤串行」句式，追加持锁动作 / 时长与排队位次。"""
    if holder:
        held_seconds = max(0.0, time.monotonic() - float(holder.get('since') or 0.0))
        holder_desc = "持锁动作 {} 已持锁 {:.0f}s".format(holder.get('action'), held_seconds)
    else:
        holder_desc = "持锁动作未知"
    # 等待超时说明锁确实被占着：前方至少 1 个步骤
    position = max(1, ahead) + 1
    return (f"设备 {device_sn} 正在执行其他操作（同 SN 步骤串行），等待 {wait_seconds}s 超时"
            f"（{holder_desc}；步骤 {action} 本请求排队第 {position} 位）")



def _peek_action_and_device_sn(request):
    """轻量解析 device_config，仅取 action / device_sn 用于加锁判定。"""
    try:
        config = _loads(request.device_config, {})
    except Exception:
        return None, None
    if isinstance(config, list):
        first = config[0] if config and isinstance(config[0], dict) else {}
        return first.get('action', 'register'), first.get('device_sn')
    if isinstance(config, dict):
        return config.get('action', 'initialize'), config.get('device_sn')
    return None, None


def serialized_device_step(func):
    """设备步骤按 SN 串行执行（仅对触摸设备硬件的 action 生效）。

    等待预算按排队位次累加（第 N 位最多等 N 个单步上界），并在调用方剩余
    deadline 内收敛——单步真机 initialize 可超 200s，按整组固定的 60s 排队
    总预算会把正常慢初始化误判为失败（INT-2257）。
    """
    @functools.wraps(func)
    def wrapper(self, request, context=None):
        action, device_sn = _peek_action_and_device_sn(request)
        if not device_sn or action not in _SERIALIZED_ACTIONS:
            return func(self, request, context)
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
            message = _format_step_lock_timeout(
                device_sn, action, wait_seconds, ahead,
                _device_step_holder_snapshot(device_sn))
            logger.warning("设备 %s 步骤 %s 等待同 SN 串行锁超时(%ss)：%s",
                           device_sn, action, wait_seconds, message)
            return e2e_pb.CreateDriverResponse(success=False, message=message, data="")
        _device_step_holder_enter(device_sn, action)
        try:
            return func(self, request, context)
        finally:
            _device_step_holder_leave(device_sn)
            lock.release()
    return wrapper


# ==================== DeviceServiceServicer ====================

class DeviceServiceServicer(e2e_grpc.DeviceServiceServicer):
    """设备驱动服务 gRPC servicer，委托给 device_driver_factory"""

    def __init__(self):
        self._factory = None

    @property
    def factory(self):
        if self._factory is None:
            from device_service.infrastructure.drivers.driver_factory import device_driver_factory
            self._factory = device_driver_factory
        return self._factory

    @serialized_device_step
    def CreateDriver(self, request, context=None):
        """创建设备驱动 / 分发设备操作

        根据 device_config 的 action 字段分发：
        - action='register': 仅登记任务设备（SNS，供停止时清理），不解析/初始化驱动
        - 无 action 或 action='initialize': 创建/初始化 driver
        - action='pre_process': 预处理
        - action='post_process': 后处理
        - action='get_results': 采集结果
        - action='teardown': 销毁 driver
        - action='extract_results_from_archive': 从存档提取结果
        """
        try:
            device_config = _loads(request.device_config, {})
            task_id = request.task_id

            # 兼容调用方直接传 list 格式: [{action, device_sn, ...}, ...]
            device_info_list_raw = None
            if isinstance(device_config, list):
                device_info_list_raw = device_config
                # 从第一个元素提取 action 及其他字段（INT-574：list 缺省收紧为
                # register，避免再被误当 initialize 触发缺 system 的驱动解析）
                first_item = device_info_list_raw[0] if device_info_list_raw else {}
                if not isinstance(first_item, dict):
                    first_item = {}
                device_config = {
                    'action': first_item.get('action', 'register'),
                    'device_info_list': device_info_list_raw,
                    'device_sn': first_item.get('device_sn'),
                    'test_case_id': first_item.get('test_case_id'),
                    'kwargs': first_item.get('kwargs', {}),
                    'system': first_item.get('system'),
                    'keywords': first_item.get('keywords'),
                }

            action = device_config.get('action', 'initialize')
            device_sn = device_config.get('device_sn')
            test_case_id = device_config.get('test_case_id')
            kwargs = device_config.get('kwargs', {})

            # action=register：仅登记任务设备（SNS，供停止时清理），不触发驱动
            # 解析/初始化。e2e register_task_devices 显式携带该 action（INT-575），
            # 避免无 action list 落入下方默认 initialize 分支——首次 CreateDriver
            # 因 system 缺失报「设备系统 system 不能为空」并误导排障。
            if action == 'register':
                if not device_info_list_raw:
                    device_info_list_raw = device_config.get('device_info_list', [])
                if device_info_list_raw:
                    self.factory.register_task_devices(task_id, device_info_list_raw)
                return e2e_pb.CreateDriverResponse(
                    success=True, message="ok",
                    data=_dumps({"task_id": str(task_id), "registered": len(device_info_list_raw)}))

            # action=initialize 时可能传入 device_info_list（列表）
            if action == 'initialize':
                system = device_config.get('system')
                keywords = device_config.get('keywords')
                if not device_info_list_raw:
                    device_info_list_raw = device_config.get('device_info_list', [])

                # 注册任务设备
                if device_info_list_raw:
                    self.factory.register_task_devices(task_id, device_info_list_raw)

                # 如果没有显式传 device_sn,从 device_info_list 取第一个
                if not device_sn and device_info_list_raw:
                    device_sn = device_info_list_raw[0].get('device_sn')

                driver = None
                resolve_error = None
                try:
                    driver = self.factory.get_driver_for_device(system, keywords=keywords, device_sn=device_sn)
                except ValueError as e:
                    # system 值非法 / keywords 未注册 / 平台不匹配：真因透传给 e2e 侧（INT-206）
                    resolve_error = str(e)
                init_ok = None
                if driver and hasattr(driver, 'initialize'):
                    init_ok = driver.initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                # 透传初始化结果：None/True 视为成功，False（如 hypium 缺失 UiDriver=None）
                # 明确失败，避免 e2e 侧拿到 success=True 带病跑完采集（INT-158 验收问题 2）
                passed = driver is not None and init_ok is not False
                # UI 抓取层能力标记（INT-296）：explicit_degrade 模式下 initialize 成功
                # 但 ui_capture_available=false，e2e 侧据此把 UI 抓取步骤显式标记 skipped
                ui_capabilities = None
                if driver is not None and hasattr(driver, 'get_ui_capabilities'):
                    try:
                        ui_capabilities = driver.get_ui_capabilities()
                    except Exception as cap_err:
                        logger.warning("读取 ui_capabilities 失败（忽略）: %s", cap_err)
                driver_info = {
                    "system": system,
                    "keywords": keywords,
                    "device_sn": device_sn,
                    "driver_found": driver is not None,
                    "driver_name": driver.__class__.__name__ if driver else None,
                    "initialize_result": init_ok,
                    "resolve_error": resolve_error,
                    "ui_capabilities": ui_capabilities,
                }
                if passed:
                    message = "ok"
                elif resolve_error:
                    message = f"驱动解析失败 on {device_sn}: {resolve_error}"
                else:
                    message = f"initialize failed on {device_sn} (result={init_ok!r})"
                return e2e_pb.CreateDriverResponse(
                    success=passed,
                    message=message,
                    data=_dumps(driver_info))

            # 优先按驱动元数据（system+keywords）精确定位；同 SN 多 App 时
            # 仅按 SN 查找会命中另一 App 的驱动（豆包 pre_process 跑到小艺）
            driver = self.factory.resolve_driver(
                system=device_config.get('system'),
                keywords=device_config.get('keywords'),
                device_sn=device_sn, task_id=task_id)

            if action == 'pre_process':
                result = None
                if driver and hasattr(driver, 'pre_process'):
                    result = driver.pre_process(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                # 透传预处理结果（None/True 成功，False 失败）；driver 未注册同样视为失败，
                # 使 e2e 侧轮次 fail-fast 而非带病继续（INT-158 验收问题 2）
                passed = driver is not None and result is not False
                return e2e_pb.CreateDriverResponse(
                    success=passed,
                    message="ok" if passed else f"pre_process failed on {device_sn} (driver={driver is not None}, result={result!r})",
                    data=_dumps({"device_sn": device_sn, "action": "pre_process",
                                 "executed": driver is not None, "result": result}))

            if action == 'post_process':
                result = None
                if driver and hasattr(driver, 'post_process'):
                    result = driver.post_process(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                passed = driver is not None and result is not False
                return e2e_pb.CreateDriverResponse(
                    success=passed,
                    message="ok" if passed else f"post_process failed on {device_sn} (driver={driver is not None}, result={result!r})",
                    data=_dumps({"device_sn": device_sn, "action": "post_process",
                                 "executed": driver is not None, "result": result}))

            if action == 'get_results':
                if driver and hasattr(driver, 'get_results'):
                    results = driver.get_results(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                    return e2e_pb.CreateDriverResponse(success=True, message="ok",
                        data=_dumps({"device_sn": device_sn, "results": results}))
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "results": {}}))

            if action == 'extract_results_from_archive':
                system = device_config.get('system')
                keywords = device_config.get('keywords')
                if not driver:
                    driver = self.factory.get_driver_for_device(system, keywords=keywords)
                if driver and hasattr(driver, 'extract_results_from_archive'):
                    archive_results = driver.extract_results_from_archive(
                        device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                    return e2e_pb.CreateDriverResponse(success=True, message="ok",
                        data=_dumps({"device_sn": device_sn, "results": archive_results}))
                return e2e_pb.CreateDriverResponse(success=False,
                    message=f"驱动不支持存档提取: system={system}", data="")

            if action == 'get_final_results':
                if driver and hasattr(driver, 'get_final_results'):
                    results = driver.get_final_results(
                        device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                    return e2e_pb.CreateDriverResponse(success=True, message="ok",
                        data=_dumps({"device_sn": device_sn, "results": results}))
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "results": []}))

            if action == 'teardown':
                if driver and hasattr(driver, 'teardown'):
                    driver.teardown(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "action": "teardown", "executed": driver is not None}))

            # 未知 action，返回基本信息
            return e2e_pb.CreateDriverResponse(success=True, message="ok",
                data=_dumps({"device_sn": device_sn, "action": action, "executed": False}))
        except Exception as e:
            return e2e_pb.CreateDriverResponse(success=False, message=str(e), data="")

    def DestroyDriver(self, request, context=None):
        """销毁设备驱动"""
        task_id = getattr(request, 'task_id', None)
        try:
            self.factory.cleanup_devices(task_id)
            return e2e_pb.DestroyDriverResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "cleaned": True})
            )
        except Exception as e:
            return e2e_pb.DestroyDriverResponse(success=False, message=str(e), data="")
        finally:
            # 兜底: 即使 cleanup 中途异常,也确保 _task_device_map 条目被移除并关闭连接。
            # cleanup_devices 幂等(task_id 不存在时直接返回),重复调用安全。
            self.factory.cleanup_devices(task_id)

    def RegisterTaskEvents(self, request, context=None):
        """注册任务事件回调"""
        try:
            from device_service.infrastructure.drivers.utils import register_task_events, get_task_events
            callback_config = _loads(request.callback_config, {})
            task_id = request.task_id

            existing = get_task_events(task_id)
            if existing:
                stop_event = existing['stop_event']
                pause_event = existing['pause_event']
                if callback_config.get('stop_event_set', False):
                    stop_event.set()
                else:
                    stop_event.clear()
                if callback_config.get('pause_event_set', True):
                    pause_event.set()
                else:
                    pause_event.clear()
                action = 'updated'
            else:
                stop_event = threading.Event()
                pause_event = threading.Event()
                pause_event.set()
                if callback_config.get('stop_event_set', False):
                    stop_event.set()
                if not callback_config.get('pause_event_set', True):
                    pause_event.clear()
                register_task_events(task_id, stop_event, pause_event)
                action = 'registered'

            return e2e_pb.RegisterTaskEventsResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), action: True}),
            )
        except Exception as e:
            return e2e_pb.RegisterTaskEventsResponse(success=False, message=str(e), data="")

    def UnregisterTaskEvents(self, request, context=None):
        """注销任务事件回调"""
        try:
            from device_service.infrastructure.drivers.utils import unregister_task_events
            task_id = request.task_id
            unregister_task_events(task_id)
            return e2e_pb.UnregisterTaskEventsResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "unregistered": True}),
            )
        except Exception as e:
            return e2e_pb.UnregisterTaskEventsResponse(success=False, message=str(e), data="")

    def GetTaskEvents(self, request, context=None):
        """获取任务事件"""
        try:
            from device_service.infrastructure.drivers.utils import get_task_events
            task_id = request.task_id
            events = get_task_events(task_id)
            events_info = {"exists": events is not None}
            if events:
                events_info["has_stop_event"] = events.get('stop_event') is not None
                events_info["has_pause_event"] = events.get('pause_event') is not None
            return e2e_pb.GetTaskEventsResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "events": events_info})
            )
        except Exception as e:
            return e2e_pb.GetTaskEventsResponse(success=False, message=str(e), data="")

    def DriverScan(self, request, context=None):
        """扫描设备

        扫描/在线检测语义一律走基础驱动（get_driver_by_system / scan_devices），
        不解析 keywords 专用驱动（INT-172）；request.keywords 字段保留兼容但忽略。
        """
        try:
            system = request.system
            if system:
                driver = self.factory.get_driver_by_system(system)
                result = driver.scan() if driver else []
            else:
                # system 为空时扫描所有基础驱动
                result = self.factory.scan_devices()
            return e2e_pb.DriverScanResponse(success=True, message="ok", data=_dumps(result))
        except Exception as e:
            return e2e_pb.DriverScanResponse(success=False, message=str(e), data="")

    def DriverUnlock(self, request, context=None):
        """解锁设备"""
        try:
            system = request.system
            keywords = request.keywords or None
            serial_or_ip = request.serial_or_ip
            driver = self.factory.get_driver_for_device(system, keywords=keywords) if system else None
            if driver:
                driver.unlock(serial_or_ip)
            return e2e_pb.DriverUnlockResponse(success=True, message="ok", data=_dumps({"unlocked": True}))
        except Exception as e:
            return e2e_pb.DriverUnlockResponse(success=False, message=str(e), data="")

    def GetMockMode(self, request, context=None):
        """获取 mock 模式"""
        try:
            mock_mode = self.factory.get_mock_mode()
            return e2e_pb.GetMockModeResponse(success=True, message="ok", data=_dumps({"mock_mode": mock_mode}))
        except Exception as e:
            return e2e_pb.GetMockModeResponse(success=False, message=str(e), data="")

    def SetMockMode(self, request, context=None):
        """设置 mock 模式"""
        try:
            self.factory.set_mock_mode(request.mock_mode)
            return e2e_pb.SetMockModeResponse(success=True, message="ok", data=_dumps({"mock_mode": request.mock_mode}))
        except Exception as e:
            return e2e_pb.SetMockModeResponse(success=False, message=str(e), data="")

    def GetDriverNameByKeywords(self, request, context=None):
        """按关键词获取驱动名"""
        try:
            name = self.factory.get_driver_name_by_keywords(request.system, request.keywords or None)
            return e2e_pb.GetDriverNameByKeywordsResponse(success=True, message="ok", data=_dumps({"driver_name": name}))
        except Exception as e:
            return e2e_pb.GetDriverNameByKeywordsResponse(success=False, message=str(e), data="")

    def GetRegisteredKeywords(self, request, context=None):
        """获取已注册关键词"""
        try:
            keywords_list = self.factory.get_registered_keywords()
            return e2e_pb.GetRegisteredKeywordsResponse(success=True, message="ok", data=_dumps(keywords_list))
        except Exception as e:
            return e2e_pb.GetRegisteredKeywordsResponse(success=False, message=str(e), data="")


# ==================== DeviceResultServiceServicer ====================

class DeviceResultServiceServicer(e2e_grpc.DeviceResultServiceServicer):
    """设备结果采集服务 gRPC servicer，委托给 device_result_collector"""

    def __init__(self):
        self._collector = None

    @property
    def collector(self):
        if self._collector is None:
            from device_service.domain.services.device_result_collector import get_device_result_collector
            from device_service.infrastructure.acl.algorithm_query_acl_repository import algorithm_query_acl_repository
            self._collector = get_device_result_collector(field_query_service=algorithm_query_acl_repository)
        return self._collector

    def CollectResult(self, request, context=None):
        """采集设备结果"""
        try:
            collect_config = _loads(request.collect_config, {})
            task_id = request.task_id
            test_case_id = collect_config.get('test_case_id')
            device_info_list = collect_config.get('device_info_list', [])
            extra_params = collect_config.get('extra_params', {})
            mode = collect_config.get('mode', 'raw')

            if mode == 'convert':
                tagged_results = collect_config.get('tagged_results', [])
                algorithm_type = collect_config.get('algorithm_type', '')
                result = self.collector.convert_results(tagged_results, algorithm_type)
            elif mode == 'round':
                round_idx = collect_config.get('round_idx', 0)
                round_config = collect_config.get('round_config', {})
                round_start_time = collect_config.get('round_start_time')
                # 注入 driver（gRPC 传输无法序列化 driver 对象）
                self._inject_drivers(device_info_list, task_id)
                result = self.collector.collect_round_results(
                    task_id, test_case_id, device_info_list,
                    round_idx, round_config, round_start_time,
                )
            else:
                # 注入 driver（gRPC 传输无法序列化 driver 对象）
                self._inject_drivers(device_info_list, task_id)
                result = self.collector.collect_raw_results(
                    task_id, test_case_id, device_info_list, extra_params,
                )
            return e2e_pb.CollectResultResponse(
                success=True, message="ok", data=_dumps({"results": result, "count": len(result) if result else 0})
            )
        except Exception as e:
            return e2e_pb.CollectResultResponse(success=False, message=str(e), data="")

    @staticmethod
    def _inject_drivers(device_info_list, task_id):
        """将已注册的 driver 实例注入到 device_info_list 中

        gRPC 传输无法序列化 driver 对象，因此 e2e_test_service 发来的
        device_info_list 不含 driver 字段。此方法从 device_driver_factory
        查找并注入，使 collect_raw_results 能正常调用 driver.get_results()。
        """
        from device_service.infrastructure.drivers.driver_factory import device_driver_factory
        for info in device_info_list:
            if isinstance(info, dict) and 'driver' not in info:
                device_sn = info.get('device_sn')
                if device_sn:
                    # 同 SN 多 App 时必须用 system+keywords 精确定位
                    driver = device_driver_factory.resolve_driver(
                        system=info.get('system'), keywords=info.get('keywords'),
                        device_sn=device_sn, task_id=task_id)
                    if driver:
                        info['driver'] = driver

    def ReextractResult(self, request, context=None):
        """重新提取设备结果"""
        try:
            from device_service.application.device_result_reextractor_service import get_device_result_reextractor
            reextract_config = _loads(request.reextract_config, {})
            task_id = request.task_id
            execution_status = reextract_config.get('execution_status', ExecutionStatus.COMPLETED)
            evaluation_status = reextract_config.get('evaluation_status')

            reextractor = get_device_result_reextractor()
            result = reextractor.reextract_for_task(
                task_id, execution_status=execution_status, evaluation_status=evaluation_status,
            )
            return e2e_pb.ReextractResultResponse(
                success=True, message="ok", data=_dumps(result)
            )
        except Exception as e:
            return e2e_pb.ReextractResultResponse(success=False, message=str(e), data="")


# ==================== EnvDeviceServiceServicer ====================

class EnvDeviceServiceServicer(e2e_grpc.EnvDeviceServiceServicer):
    """环境设备服务 gRPC servicer，委托给 EnvDeviceFactory"""

    def __init__(self):
        self._factory_cls = None

    @property
    def factory_cls(self):
        if self._factory_cls is None:
            from device_service.infrastructure.env_devices.factory import EnvDeviceFactory
            self._factory_cls = EnvDeviceFactory
        return self._factory_cls

    def ControlEnvDevice(self, request, context=None):
        """控制环境设备（导轨旋转等）"""
        try:
            device_action = _loads(request.device_action, {})
            task_id = request.task_id
            action = device_action.get('action', 'setup')
            device_type = device_action.get('device_type')
            config = device_action.get('config')
            settings = device_action.get('settings', {})
            device_configs = device_action.get('device_configs', [])

            result = {"task_id": str(task_id), "action": action, "devices": []}

            if device_configs:
                devices = self.factory_cls.create_from_config(device_configs)
            elif device_type:
                devices = [self.factory_cls.create(device_type, config)]
            else:
                devices = []

            for dev in devices:
                dev_info = {
                    "name": getattr(dev, 'name', None),
                    "device_type": getattr(dev, 'device_type', None),
                    "available": dev.is_available() if hasattr(dev, 'is_available') else False,
                }
                try:
                    if action == 'setup':
                        dev.connect()
                        state = dev.setup(settings)
                        dev_info["state"] = state
                        dev_info["connected"] = True
                    elif action == 'teardown':
                        state = device_action.get('state', {})
                        dev.teardown(state)
                        dev_info["torn_down"] = True
                    elif action == 'connect':
                        dev.connect()
                        dev_info["connected"] = True
                    elif action == 'disconnect':
                        dev.disconnect()
                        dev_info["disconnected"] = True
                except Exception as dev_e:
                    dev_info["error"] = str(dev_e)
                result["devices"].append(dev_info)

            return e2e_pb.ControlEnvDeviceResponse(
                success=True, message="ok", data=_dumps(result)
            )
        except Exception as e:
            return e2e_pb.ControlEnvDeviceResponse(success=False, message=str(e), data="")


__all__ = [
    "DeviceServiceServicer",
    "DeviceResultServiceServicer",
    "EnvDeviceServiceServicer",
]
