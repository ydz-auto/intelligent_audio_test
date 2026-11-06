# -*- coding: utf-8 -*-
"""MCP 适配端点（INT-1150 / INT-1140 分道 A）。

网关内实现 JSON-RPC 2.0 MCP 适配：initialize / tools/list / tools/call，
tools 注册表 = INT-1140 覆盖能力清单（业务能力全暴露、个人信息/系统设置除外）。
同一 access token 走同一条 AuthMiddleware 分支（BE2 INT-1149），天然与 skill 通用。
"""
