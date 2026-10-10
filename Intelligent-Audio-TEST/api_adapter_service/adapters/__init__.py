# -*- coding: utf-8 -*-
"""adapters 包 — 具体适配器自注册入口（UC-1003）。

导入本包时自动发现并导入包内全部非下划线模块：每个具体适配器模块
在自身底部调用 ``api_adapter_factory.register(protocol, vendor, cls)``
完成注册，注册即生效。

新增厂商适配器 = 本包新增一个子类文件（内部自注册），基类 / executor /
工厂零改动（OCP）。
"""
import importlib
import pkgutil

for _mod in pkgutil.iter_modules(__path__):
    if not _mod.name.startswith('_'):
        importlib.import_module(f'{__name__}.{_mod.name}')
