# -*- coding: utf-8 -*-
"""domain 层：枚举、值对象、实体、状态机与仓储端口。

分层红线：domain 零依赖（不 import infrastructure / SQLAlchemy / FastAPI），
只允许引用 Python 标准库与 shared 里无基础设施依赖的纯工具。
"""
