import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import (
    DeviceAclRepositoryImpl,
    DeviceGroupAclRepositoryImpl,
    DeviceMonitorAclRepositoryImpl,
)
from api_gateway.application.services.device.device_audit import write_device_audit
from api_gateway.schemas.common import IdData
from api_gateway.schemas.device import (
    DeviceCreateSchema,
    DeviceUpdateSchema,
)

logger = logging.getLogger(__name__)

_device_acl = DeviceAclRepositoryImpl()
_device_group_acl = DeviceGroupAclRepositoryImpl()
_device_monitor_acl = DeviceMonitorAclRepositoryImpl()


class DeviceCommandService:
    """设备写操作 Service（CQRS Command Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    保留 Pydantic schema 校验。
    """

    # 注册新设备
    @staticmethod
    def create():
        try:
            req = DeviceCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = _device_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '操作失败'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', '设备注册成功'), http_code=201)

    # 更新设备信息
    @staticmethod
    def update(device_id):
        try:
            req = DeviceUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        validated_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = _device_acl.update(device_id, validated_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', '设备信息更新成功'))

    # 删除设备
    @staticmethod
    def delete(device_id):
        result = _device_acl.delete(device_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', '设备已删除 (逻辑删除)'))

    # ==================== INT-80 设备操作 ====================

    @staticmethod
    def control(device_id: int, operation: str):
        """设备操作：connect/disconnect/reboot/shutdown/install_app/uninstall_app"""
        body = request.get_json() or {}
        params = body.get('params') or {}

        result = _device_acl.control(device_id, {'operation': operation, 'params': params})

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_CONTROL_EXECUTED,
            'device_control',
            {'device_id': device_id, 'operation': operation, 'params': params,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(result.get('data'), result.get('message', f'操作 {operation} 执行成功'))

    # ==================== INT-80 批量操作 ====================

    @staticmethod
    def batch_action():
        """设备批量操作（幂等模式对齐 testcase batch）"""
        from api_gateway.schemas.device import DeviceBatchActionRequest
        try:
            req = DeviceBatchActionRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        result = _device_acl.batch_action(req.model_dump(by_alias=False, exclude_none=True))

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_BATCH_ACTION_EXECUTED,
            'device_batch',
            {'action': req.action, 'device_ids': req.device_ids,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            return error_response(result.get('message', '批量操作失败'), code=result.get('code', 400))

        return success_response(result.get('data'), result.get('message', '批量操作完成'))

    # ==================== INT-80 设备分组 ====================

    @staticmethod
    def create_group():
        from api_gateway.schemas.device import DeviceGroupCreateSchema
        try:
            req = DeviceGroupCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        result = _device_group_acl.create(req.model_dump(by_alias=False, exclude_none=True))

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_GROUP_CREATED, 'device_group',
            {'name': req.name, 'group_type': req.group_type,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            return error_response(result.get('message', '创建失败'), code=result.get('code', 400))

        return success_response(result.get('data'), result.get('message', '设备分组创建成功'), http_code=201)

    @staticmethod
    def update_group(group_id: str):
        from api_gateway.schemas.device import DeviceGroupUpdateSchema
        try:
            req = DeviceGroupUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        result = _device_group_acl.update(group_id, req.model_dump(by_alias=False, exclude_none=True))

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_GROUP_UPDATED, 'device_group',
            {'group_id': group_id, 'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备分组'), 404)
            return error_response(result.get('message', '更新失败'), code=code)

        return success_response(result.get('data'), result.get('message', '设备分组更新成功'))

    @staticmethod
    def delete_group(group_id: str):
        from api_gateway.schemas.device import DeviceGroupDeleteQuery
        params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        try:
            query = DeviceGroupDeleteQuery.model_validate(params)
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        result = _device_group_acl.delete(group_id, cascade=query.cascade)

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_GROUP_DELETED, 'device_group',
            {'group_id': group_id, 'cascade': query.cascade,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备分组'), 404)
            return error_response(result.get('message', '删除失败'), code=code)

        return success_response(None, result.get('message', '设备分组已删除'))

    @staticmethod
    def add_group_devices(group_id: str):
        from api_gateway.schemas.device import DeviceGroupMembersRequest
        try:
            req = DeviceGroupMembersRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        result = _device_group_acl.add_devices(group_id, req.device_ids)

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_GROUP_MEMBERSHIP_CHANGED, 'device_group',
            {'group_id': group_id, 'op': 'add', 'device_ids': req.device_ids,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备分组'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(result.get('data'), result.get('message', '设备已加入分组'))

    @staticmethod
    def remove_group_devices(group_id: str):
        from api_gateway.schemas.device import DeviceGroupMembersRequest
        try:
            req = DeviceGroupMembersRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        result = _device_group_acl.remove_devices(group_id, req.device_ids)

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_GROUP_MEMBERSHIP_CHANGED, 'device_group',
            {'group_id': group_id, 'op': 'remove', 'device_ids': req.device_ids,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备分组'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(result.get('data'), result.get('message', '设备已移出分组'))

    # ==================== INT-80 告警规则/确认 ====================

    @staticmethod
    def create_alarm_rule():
        from api_gateway.schemas.device import AlarmRuleCreateSchema
        try:
            req = AlarmRuleCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        result = _device_monitor_acl.create_alarm_rule(req.model_dump(by_alias=False, exclude_none=True))

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_ALARM_RULE_CREATED, 'device_alarm',
            {'name': req.name, 'metric_type': req.metric_type,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            return error_response(result.get('message', '创建失败'), code=result.get('code', 400))

        return success_response(result.get('data'), result.get('message', '告警规则创建成功'), http_code=201)

    @staticmethod
    def update_alarm_rule(rule_id: int):
        from api_gateway.schemas.device import AlarmRuleUpdateSchema
        try:
            req = AlarmRuleUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        result = _device_monitor_acl.update_alarm_rule(rule_id, req.model_dump(by_alias=False, exclude_none=True))

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_ALARM_RULE_UPDATED, 'device_alarm',
            {'rule_id': rule_id, 'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到告警规则'), 404)
            return error_response(result.get('message', '更新失败'), code=code)

        return success_response(result.get('data'), result.get('message', '告警规则更新成功'))

    @staticmethod
    def delete_alarm_rule(rule_id: int):
        result = _device_monitor_acl.delete_alarm_rule(rule_id)

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_ALARM_RULE_DELETED, 'device_alarm',
            {'rule_id': rule_id, 'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到告警规则'), 404)
            return error_response(result.get('message', '删除失败'), code=code)

        return success_response(None, result.get('message', '告警规则已删除'))

    @staticmethod
    def acknowledge_alarm(alarm_id: int):
        from api_gateway.schemas.device import AlarmAcknowledgeRequest
        body = request.get_json() or {}
        try:
            req = AlarmAcknowledgeRequest.model_validate(body)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        acknowledged_by = req.acknowledged_by or request.username or ''
        result = _device_monitor_acl.acknowledge_alarm(alarm_id, {'acknowledged_by': acknowledged_by})

        from shared.models.common_enums import AuditEvent
        write_device_audit(
            AuditEvent.DEVICE_ALARM_ACKNOWLEDGED, 'device_alarm',
            {'alarm_id': alarm_id, 'acknowledged_by': acknowledged_by,
             'success': bool(result.get('success'))},
        )

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '告警不存在或已确认'), 404)
            return error_response(result.get('message', '确认失败'), code=code)

        return success_response(result.get('data'), result.get('message', '告警已确认'))
