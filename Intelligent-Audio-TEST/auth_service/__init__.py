# -*- coding: utf-8 -*-
"""auth_service — 用户与权限微服务

P5 阶段新建骨架。持有 User/Role/Permission/OAuth 全套 PO 的数据所有权。
后续 P6 阶段会从 api_gateway/auth/ 下沉认证 + OAuth + RBAC 逻辑到本服务。

注意：ReportStatus / TaskStatus / ReportType 是跨服务共享枚举（非 PO），
保留在 shared/models/common_enums.py 中作为全局共享。
"""
