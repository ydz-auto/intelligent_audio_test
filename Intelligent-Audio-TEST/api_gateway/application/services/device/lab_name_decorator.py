# -*- coding: utf-8 -*-
"""lab_name 装饰助手（INT-655）。

DeviceItem/PlaybackDeviceItem 由 device_service 返回 lab_id，实验室名称
（lab_name）由网关装饰：一次性拉取全量实验室（gRPC ListLaboratories），
按 lab_id 建映射回填。gRPC 不可用时跳过装饰（lab_name 保持 None），
不影响设备列表主链路。
"""
import logging

logger = logging.getLogger(__name__)


def _decorate_lab_names(items):
    """为设备/播放设备 item 列表装饰 lab_name（基于 lab_id → name 映射）。

    INT-1467：device_service 已随 item 返回 lab_name（同一张 laboratories 表、
    同一软删口径），此时网关不再发起 ListLaboratories 全量查询——只有确实
    缺 lab_name 的 item 才回源，避免每次详情/列表多一次跨服务 RPC。
    """
    if not items:
        return items
    lab_ids = {item.get('lab_id') for item in items
               if item.get('lab_id') is not None and not item.get('lab_name')}
    if not lab_ids:
        return items

    lab_map = _fetch_lab_name_map(lab_ids)
    if not lab_map:
        return items

    for item in items:
        lab_id = item.get('lab_id')
        # 已由 device_service 解析出 lab_name 的 item 不覆盖
        if lab_id is not None and item.get('lab_name'):
            continue
        item['lab_name'] = lab_map.get(lab_id) if lab_id is not None else None
    return items


def _fetch_lab_name_map(lab_ids):
    """拉取实验室 id → name 映射（只请求包含所需 id 的全量列表）。

    返回 None 表示 gRPC 不可用（调用方跳过装饰）；空 dict 表示无匹配。
    """
    from api_gateway.infrastructure.acl import LaboratoryAclRepositoryImpl
    try:
        result = LaboratoryAclRepositoryImpl().get_all(page=1, per_page=10000)
    except Exception as e:
        logger.warning("fetch lab names failed: %s", e)
        return None
    if not result.get('success'):
        return None
    data = result.get('data') or {}
    items = data.get('items') or []
    lab_map = {}
    for lab in items:
        lab_id = lab.get('id')
        if lab_id is not None:
            lab_map[lab_id] = lab.get('name')
    return lab_map
