# -*- coding: utf-8 -*-
"""report_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    """report_service 配置。

    端口规划：
    - HTTP (FastAPI): 5006（避免与 api_adapter_service 的 5008 冲突）
    - gRPC: 50068
    """
    PORT = int(os.environ.get('PORT', 5006))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50068))
    SERVICE_NAME = 'report_service'
    # 静态文件根路径，用于 audio_file 路径规范化
    STATIC_BASE_PATH = os.environ.get('STATIC_BASE_PATH', '')

    # ===== Benchmark 排行（D1）配置 =====
    # 平台实测轨 suite/category 缺省值（published_tasks.snapshot_config 未指定时回退）
    BENCHMARK_DEFAULT_SUITE = os.environ.get('BENCHMARK_DEFAULT_SUITE', 'general')
    BENCHMARK_DEFAULT_CATEGORY = os.environ.get('BENCHMARK_DEFAULT_CATEGORY', 'general')
    # 无匹配场景时使用的默认场景（设计文档 §5.2）
    BENCHMARK_DEFAULT_SCENARIO = os.environ.get('BENCHMARK_DEFAULT_SCENARIO', '通用')
    # 排行查询分页上限
    BENCHMARK_MAX_PER_PAGE = int(os.environ.get('BENCHMARK_MAX_PER_PAGE', 200))
