# -*- coding: utf-8 -*-
"""device_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig
from shared.constants.ui_capture import UiCaptureMode, normalize_ui_capture_mode


class Config(BaseConfig):
    """device_service 配置。

    端口规划：
    - HTTP (FastAPI): 5005
    - gRPC: 50053
    """
    PORT = int(os.environ.get('PORT', 5005))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50053))
    SERVICE_NAME = 'device_service'

    # UI 抓取层显式降级模式（INT-296）。
    # strict（默认）：harmony 驱动 UI 自动化层不可用 → initialize 显式失败（INT-158 语义）
    # explicit_degrade：UI 层不可用 → initialize 成功 + ui_capture_available=false + degrade_reason
    # 隐式默认降级 = 缺陷：降级必须经此配置显式开启（审计红线）。
    UI_CAPTURE_MODE = normalize_ui_capture_mode(
        os.environ.get('UI_CAPTURE_MODE', UiCaptureMode.STRICT.value))
