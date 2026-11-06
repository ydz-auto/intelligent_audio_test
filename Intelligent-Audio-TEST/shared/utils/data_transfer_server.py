# -*- coding: utf-8 -*-
"""离线搬运 —— 本端稳定服务标识解析（INT-1760 / D0 A4）

背景：导出包 manifest.serverInfo.source 以前默认取 `socket.gethostname()`，
docker 容器重建即变；导入侧把它当 source_map.source_server，一旦变就再也
匹配不上历史映射（增量回导断链）。

裁定（D0 A4）：配置项 `DATA_TRANSFER_SERVER_ID` 是本端稳定标识，导出写进
manifest，导入以它作 source_server。未配置时回落 `SERVICE_NAME-hostname`
并打 WARNING（可运行，但不稳定；生产必须显式配置）。

导出（task_service 导出服务）与导入（编排层登记 source_map）共用本解析，
避免两处各写一份回落口径。
"""
import socket

from shared.utils.log_handler import log_not_emit

_MODULE_NAME = 'data_transfer_server'

# WARNING 只打一次：解析在每次导出/导入都会调用，重复刷库日志没有信息量
_warned = False


def compose_fallback_server_id(service_name: str, hostname: str) -> str:
    """未配置时的回落标识（纯函数，可单测）。"""
    return f'{service_name or "unknown"}-{hostname or "unknown"}'


def resolve_transfer_server_id() -> str:
    """本端稳定服务标识：DATA_TRANSFER_SERVER_ID，空则回落并 WARNING。"""
    global _warned
    # 延迟导入：本模块可能早于环境变量装配被 import（测试进程先 setenv）
    from shared.infrastructure.config import BaseConfig

    configured = (getattr(BaseConfig, 'DATA_TRANSFER_SERVER_ID', '') or '').strip()
    if configured:
        return configured

    fallback = compose_fallback_server_id(
        getattr(BaseConfig, 'SERVICE_NAME', ''), socket.gethostname())
    if not _warned:
        _warned = True
        log_not_emit('WARNING', _MODULE_NAME,
                     'DATA_TRANSFER_SERVER_ID 未配置，回落为不稳定标识 '
                     f'{fallback}（容器重建 / 换机即变，跨机 source_map 会断链）',
                     category='system')
    return fallback
