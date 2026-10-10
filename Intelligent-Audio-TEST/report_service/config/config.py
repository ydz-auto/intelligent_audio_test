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

    # ===== 报告生成看门狗（INT-117）=====
    # 单次报告生成超时阈值（秒）：总时长超过即判卡死，看门狗打 CRITICAL
    # （含工作线程调用栈，精确定位卡死行）并发布 report_generated 失败事件。
    # 须显著小于生成去重锁 TTL（_GENERATION_LOCK_TTL=1800s）：超时上报后锁仍由
    # 卡死线程持有，直至 TTL 兜底过期释放，期间重复提交返回"正在生成中"。
    REPORT_GEN_TIMEOUT_SECONDS = int(os.environ.get('REPORT_GEN_TIMEOUT_SECONDS', 900))
    # 队列饥饿告警阈值（秒）：提交后停留在 QUEUED 阶段超过该时长，说明
    # 线程池（max_workers=3）被占满，后续提交全部滞留无产出（INT-117 第二症状）。
    REPORT_GEN_QUEUE_STUCK_SECONDS = int(os.environ.get('REPORT_GEN_QUEUE_STUCK_SECONDS', 120))
    # 慢阶段观察阈值（秒）：单阶段停留超过该时长记 WARNING（埋点，非失败判定）。
    REPORT_GEN_SLOW_STAGE_SECONDS = int(os.environ.get('REPORT_GEN_SLOW_STAGE_SECONDS', 60))
    # 看门狗扫描周期（秒）。
    REPORT_GEN_WATCHDOG_INTERVAL_SECONDS = int(os.environ.get('REPORT_GEN_WATCHDOG_INTERVAL_SECONDS', 30))
