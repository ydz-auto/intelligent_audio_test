# -*- coding: utf-8 -*-
"""宿主侧服务（audio_service / device_service）生命周期控制包。

这两个服务依赖本机声卡与 ADB，固定跑在宿主机；容器服务由 docker compose 托管。
统一入口见仓库根 ``stack.py``。
"""
