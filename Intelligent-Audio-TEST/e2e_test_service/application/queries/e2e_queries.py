# -*- coding: utf-8 -*-
"""E2E 测试查询对象。

查询（Query）表示读取系统状态的意图，不改变状态。本模块仅定义
查询数据结构，处理逻辑在 handlers.py 中实现。
"""

from dataclasses import dataclass


@dataclass
class GetDeviceStatusQuery:
    """获取设备状态查询"""
    task_id: str
    device_id: str


@dataclass
class GetTestProgressQuery:
    """获取测试进度查询"""
    task_id: str
