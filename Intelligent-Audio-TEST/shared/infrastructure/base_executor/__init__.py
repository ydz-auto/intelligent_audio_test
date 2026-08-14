# -*- coding: utf-8 -*-
"""
base_executor 包 — 共享执行器基类

为保持向后兼容，从本包可直接导入以下符号：
    from shared.infrastructure.base_executor import BaseExecutor

原 base_executor.py 拆分为以下子模块：
    _control_mixin.py  暂停 / 停止控制
    _logging_mixin.py  统一日志记录
    _params_mixin.py   结果映射器接口（由子类实现）
    _results_mixin.py  测试结果处理与评估提交
    _db_mixin.py       数据库操作（校验、状态更新、结果保存）
    _base.py           组装最终 BaseExecutor 类

_DeviceResultCollectorProxy 已删除，各 service 通过自己的
infrastructure/acl/ 下的 DeviceResultAclRepositoryImpl 实现 _get_result_mapper()。
"""
from shared.infrastructure.base_executor._base import BaseExecutor

__all__ = ['BaseExecutor']
