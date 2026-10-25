import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, wrap_grpc_response
from api_gateway.infrastructure.acl import (
    DeviceAclRepositoryImpl,
    DeviceGroupAclRepositoryImpl,
    DeviceMonitorAclRepositoryImpl,
)
from api_gateway.schemas.device import (
    DeviceListQuery,
    DeviceStatusQuery,
    DeviceHealthCheckRequest,
    DeviceMonitorStatsQuery,
)

logger = logging.getLogger(__name__)

# 监控统计口径（INT-1578 契约 §1.1）：区间跨度 ≤ 90 天（含首尾），本期仅 day 粒度
MONITOR_STATS_MAX_RANGE_DAYS = 90
MONITOR_STATS_GRANULARITY_DAY = 'day'

_device_acl = DeviceAclRepositoryImpl()
_device_group_acl = DeviceGroupAclRepositoryImpl()
_device_monitor_acl = DeviceMonitorAclRepositoryImpl()


class DeviceQueryService:
    """设备查询读侧 Service（CQRS Query Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    保留 Pydantic schema 校验。
    """

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='TestDevice', **kwargs):
        """统一日志记录方法"""
        from shared.utils.log_handler import log_not_emit
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    # 获取所有注册设备
    @staticmethod
    def get_all():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = DeviceListQuery.model_validate(query_params_dict)

        result = _device_acl.get_all(
            page=query_params.page,
            per_page=query_params.per_page,
            keyword=query_params.keyword,
            status=query_params.status,
            device_type=query_params.device_type,
            algorithm_type=query_params.algorithm_type,
            lab_id=query_params.lab_id,
        )

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询失败')

        data = result.get('data') or {}
        if isinstance(data, dict):
            items = data.get('items') or []
            DeviceQueryService._inject_occupancy(items)
            # INT-655：lab_name 由网关装饰（device_service 只返回 lab_id）
            from api_gateway.application.services.device.lab_name_decorator import _decorate_lab_names
            data['items'] = _decorate_lab_names(items)
        return success_response(data)
        return success_response(data)

    # 批量获取设备状态 (用于 HTTP 轮询降级)
    @staticmethod
    def get_statuses():
        try:
            query_params = DeviceQueryService._parse_query(DeviceStatusQuery)
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)
        device_ids = query_params.ids

        result = _device_acl.get_statuses(device_ids)

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询失败')

        return success_response(result.get('data'))

    # 扫描物理设备
    @staticmethod
    def scan():
        """触发驱动层扫描 Android, iOS, HarmonyOS 设备"""
        result = _device_acl.scan()

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='扫描失败')

        data = result.get('data') or []
        return success_response(data, result.get('message', f'成功扫描到 {len(data)} 个在线设备'))

    # 测试设备
    @staticmethod
    def test(device_id):
        result = _device_acl.test(device_id)

        if not result.get('success'):
            return wrap_grpc_response(
                result,
                default_error_msg='测试失败',
                error_code_mapping={404: ('未找到设备', 404)},
            )

        return success_response(result.get('data'), result.get('message', '唤醒指令已发送，正在测试'))

    # 停止测试
    @staticmethod
    def stop_test(device_id):
        result = _device_acl.stop_test(device_id)

        if not result.get('success'):
            return wrap_grpc_response(
                result,
                default_error_msg='操作失败',
                error_code_mapping={404: ('未找到设备', 404)},
            )

        return success_response(result.get('data'), result.get('message', '测试已停止'))

    @staticmethod
    def get_driver_keywords():
        """获取所有已注册的驱动关键字"""
        result = _device_acl.get_driver_keywords()

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='获取失败')

        return success_response(result.get('data'), result.get('message', '获取驱动关键字成功'))

    # 获取单个设备详情
    @staticmethod
    def get_one(device_id):
        # INT-1467：占用态查询只依赖 device_id，与设备详情 RPC 无依赖关系，
        # 并发发起（详情链路从「串行 2 次跨服务 RPC」降到 1 次），并发 10
        # 压测下设备详情 avg/p95 明显下降；占用态为可选注入，失败降级空映射。
        from concurrent.futures import ThreadPoolExecutor
        import contextvars
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='device-detail-occ')
        try:
            # 复制当前请求上下文再进线程：contextvars 不跨线程传播，而占用态 RPC
            # 经出站拦截器附加 x-user-id / x-user-is-admin，必须与同步路径一致。
            ctx = contextvars.copy_context()
            occ_future = executor.submit(
                ctx.run, DeviceQueryService._fetch_occupancy, [device_id])
            result = _device_acl.get_one(device_id)

            if not result.get('success'):
                return wrap_grpc_response(
                    result,
                    default_error_msg='查询失败',
                    error_code_mapping={404: ('未找到设备', 404)},
                )

            data = result.get('data')
            if isinstance(data, dict):
                DeviceQueryService._apply_occupancy([data], occ_future.result())
                # INT-655：lab_name 缺省时由网关装饰（device_service 已返回则跳过）
                from api_gateway.application.services.device.lab_name_decorator import _decorate_lab_names
                data = _decorate_lab_names([data])[0]
            return success_response(data)
        finally:
            executor.shutdown(wait=False)

    @staticmethod
    def _inject_occupancy(items):
        """经 task_service GetDeviceOccupancy RPC 注入设备占用态（INT-493 §4.3）。

        task_case_relations 归 task_service 域，网关经 gRPC+ACL 读取，不直读 DB；
        无活动占用行的设备占用态为 null（不注入字段）。RPC 失败降级为空映射，
        占用字段保持 null —— 占用态为可选注入，不阻塞设备列表/详情。
        """
        if not items:
            return items
        device_ids = [item['id'] for item in items if item.get('id') is not None]
        if not device_ids:
            return items
        return DeviceQueryService._apply_occupancy(
            items, DeviceQueryService._fetch_occupancy(device_ids))

    @staticmethod
    def _fetch_occupancy(device_ids):
        """拉取设备占用态映射 {device_id(str): {occupied_status, task_id}}（可能为空）。"""
        if not device_ids:
            return {}
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import task_data_service
        return task_data_service.get_device_occupancy(device_ids=device_ids) or {}

    @staticmethod
    def _apply_occupancy(items, occupancy):
        """把占用态映射回填到设备 item（无占用时置 null，保持字段存在）。"""
        if not items:
            return items
        occupancy = occupancy or {}
        for item in items:
            occ = occupancy.get(str(item.get('id')))
            if occ:
                item['occupied_status'] = occ.get('occupied_status')
                item['occupied_task_id'] = occ.get('task_id')
            else:
                item['occupied_status'] = None
                item['occupied_task_id'] = None
        return items

    # 批量健康检查
    @staticmethod
    def health_check():
        try:
            req = DeviceHealthCheckRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        device_ids = req.device_ids or []

        result = _device_acl.health_check(device_ids)

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='健康检查失败')

        return success_response(result.get('data'), result.get('message', '健康检查完成'))

    # 获取可用设备详情列表 (用于自动填充)
    @staticmethod
    def get_available_serials():
        """获取通过 ADB/HDC 命令扫描到的可用设备详细信息列表"""
        result = _device_acl.get_available_serials()

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='获取失败')

        data = result.get('data') or []
        return success_response(data, result.get('message', f'成功获取 {len(data)} 个设备详细信息'))

    # ==================== INT-80 状态历史/分组/告警（读侧） ====================

    @staticmethod
    def _parse_query(model_cls):
        params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        return model_cls.model_validate(params)

    @staticmethod
    def get_status_history(device_id: int = None):
        """设备状态历史/趋势查询"""
        from api_gateway.schemas.device import DeviceStatusHistoryQuery
        try:
            query = DeviceQueryService._parse_query(DeviceStatusHistoryQuery)
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        if device_id is not None:
            query.device_ids = [device_id]

        result = _device_acl.get_status_history(query.model_dump(by_alias=False, exclude_none=True))

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询状态历史失败')

        return success_response(result.get('data'))

    @staticmethod
    def get_monitor_stats(start_date, end_date, device_ids=None, lab_id=None,
                          granularity=MONITOR_STATS_GRANULARITY_DAY):
        """设备监控统计（历史监控 → 统计分析四图，INT-1578）。

        start_date / end_date 缺参由路由层 FastAPI 校验返回 422；本方法按契约
        校验区间与粒度，非法返回 400。
        """
        try:
            query = DeviceMonitorStatsQuery.model_validate({
                'start_date': start_date,
                'end_date': end_date,
                'device_ids': device_ids,
                'lab_id': lab_id,
                'granularity': granularity,
            })
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        if query.end_date < query.start_date:
            return error_response('结束日期不能早于开始日期', 400)
        if (query.end_date - query.start_date).days + 1 > MONITOR_STATS_MAX_RANGE_DAYS:
            return error_response(f'统计区间不得超过 {MONITOR_STATS_MAX_RANGE_DAYS} 天', 400)
        if str(query.granularity or '').strip().lower() != MONITOR_STATS_GRANULARITY_DAY:
            return error_response(f'统计粒度仅支持 {MONITOR_STATS_GRANULARITY_DAY}', 400)

        result = _device_monitor_acl.get_monitor_stats(query.model_dump(mode='json'))

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询监控统计失败')

        return success_response(result.get('data'))

    @staticmethod
    def get_groups():
        """设备分组列表（INT-80，区别于用例分组 group_bp）"""
        from api_gateway.schemas.device import DeviceGroupListQuery
        try:
            query = DeviceQueryService._parse_query(DeviceGroupListQuery)
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        result = _device_group_acl.get_all(
            page=query.page, per_page=query.per_page,
            keyword=query.keyword, group_type=query.group_type,
        )

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询设备分组失败')

        return success_response(result.get('data'))

    @staticmethod
    def get_group(group_id: str):
        """设备分组详情（含 device_ids）"""
        result = _device_group_acl.get_one(group_id)

        if not result.get('success'):
            return wrap_grpc_response(
                result, default_error_msg='查询设备分组失败',
                error_code_mapping={404: ('未找到设备分组', 404)},
            )

        return success_response(result.get('data'))

    @staticmethod
    def get_alarm_rules():
        """告警规则列表"""
        from api_gateway.schemas.device import AlarmRuleListQuery
        try:
            query = DeviceQueryService._parse_query(AlarmRuleListQuery)
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        result = _device_monitor_acl.list_alarm_rules(
            page=query.page, per_page=query.per_page,
            metric_type=query.metric_type, enabled=query.enabled,
        )

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询告警规则失败')

        return success_response(result.get('data'))

    @staticmethod
    def get_alarms():
        """告警列表（含统计）"""
        from api_gateway.schemas.device import AlarmListQuery
        try:
            query = DeviceQueryService._parse_query(AlarmListQuery)
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        result = _device_monitor_acl.list_alarms(query.model_dump(by_alias=False, exclude_none=True))

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询告警失败')

        return success_response(result.get('data'))
