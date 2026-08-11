# -*- coding: utf-8 -*-
"""接口层 HTTP API：基于 FastAPI 的适配器路由。

与已有的 ``routes/api.py`` 并存，本模块聚焦 DDD 四层架构下的
对外 HTTP 接口，调用 ``application`` 层的命令/查询处理器。
"""
