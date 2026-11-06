# -*- coding: utf-8 -*-
"""device_service.SPLConfigService 防腐层仓储（ACL Repository）

封装对 device_service.SPLConfigService 的 gRPC 调用，
替代 device_service application 层中对 shared.clients.grpc_clients 的直接 import。

- 读操作通过 gRPC 完成，返回 dict / list / bool，不返回 ORM 对象。
- 与 device_service/infrastructure/acl/task_acl_repository.py 风格一致，
  采用具体类 + 模块级单例（device_service ACL 层无统一 ABC）。
"""
import logging

logger = logging.getLogger(__name__)


class SPLConfigACLRepository:
    """device_service.SPLConfigService 防腐层仓储

    封装 gRPC 调用，提供 application 层可用的返回值。
    所有方法返回纯 dict / list / bool，不返回 ORM 对象。
    """

    def get_spl_mapping(self, mapping_id):
        """获取 SPL 映射详情

        通过 gRPC 调用 device_service.SPLConfigService.GetSPLMapping。
        返回映射 dict；gRPC 不可用时返回 None。
        """
        from shared.clients.grpc_clients import get_spl_config_service_stub
        from shared.proto import device_service_pb2 as _e2e_pb
        from shared.utils.grpc_json import loads as _grpc_loads
        try:
            stub = get_spl_config_service_stub()
            resp = stub.GetSPLMapping(_e2e_pb.GetSPLMappingRequest(mapping_id=int(mapping_id)))
            if not resp.success:
                return None
            return _grpc_loads(resp.data, {}) or {}
        except Exception as e:
            logger.warning(f"get_spl_mapping gRPC 调用失败: {e}")
            return None


# 模块级单例
spl_config_acl_repository = SPLConfigACLRepository()
