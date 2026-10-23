# -*- coding: utf-8 -*-
"""report_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    """report_service 配置。

    端口规划：
    - HTTP (FastAPI): 5006
    - gRPC: 51068
    """
    PORT = int(os.environ.get('PORT', 5006))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 51068))
    SERVICE_NAME = 'report_service'
    # 静态文件根路径，用于 audio_file 路径规范化
    STATIC_BASE_PATH = os.environ.get('STATIC_BASE_PATH', '')

    # ===== Report Studio 导出（INT-673）=====
    # 导出产物落盘目录（作业记录持久化；文件路径存 export_jobs.file_path）
    REPORT_STUDIO_EXPORT_DIR = os.environ.get(
        'REPORT_STUDIO_EXPORT_DIR', 'report_studio_exports')

    # ===== Benchmark 排行（D1）配置 =====
    # 平台实测轨 suite/category 缺省值（published_tasks.snapshot_config 未指定时回退）
    BENCHMARK_DEFAULT_SUITE = os.environ.get('BENCHMARK_DEFAULT_SUITE', 'general')
    BENCHMARK_DEFAULT_CATEGORY = os.environ.get('BENCHMARK_DEFAULT_CATEGORY', 'general')
    # 无匹配场景时使用的默认场景（设计文档 §5.2）
    BENCHMARK_DEFAULT_SCENARIO = os.environ.get('BENCHMARK_DEFAULT_SCENARIO', '通用')
    # 排行查询分页上限
    BENCHMARK_MAX_PER_PAGE = int(os.environ.get('BENCHMARK_MAX_PER_PAGE', 200))

    # ===== 报告生成线程池（INT-1505）=====
    # 任务报告生成线程池容量：原硬编码 3，多任务并发生成时长生成占满全部工作
    # 线程，后续提交只能排队（report_generated 延迟推送 → 前端「重新生成等很久」）。
    # 扩容并配置化；生成以跨服务 gRPC 查询 + DB 写为主（IO 密集），8 个并发不会
    # 打满单进程 CPU，DB 连接由连接池（pool_size=5 + overflow）兜住。
    REPORT_GEN_MAX_WORKERS = int(os.environ.get('REPORT_GEN_MAX_WORKERS', 8))
    # 对比 / 二次对比报告生成线程池容量：与任务报告同款饥饿模式，独立队列独立配置。
    REPORT_COMPARE_GEN_MAX_WORKERS = int(os.environ.get('REPORT_COMPARE_GEN_MAX_WORKERS', 8))

    # ===== 报告生成看门狗（INT-117）=====
    # 单次报告生成超时阈值（秒）：总时长超过即判卡死，看门狗打 CRITICAL
    # （含工作线程调用栈，精确定位卡死行）并发布 report_generated 失败事件。
    # 须显著小于生成去重锁 TTL（_GENERATION_LOCK_TTL=1800s）：超时上报后锁仍由
    # 卡死线程持有，直至 TTL 兜底过期释放，期间重复提交返回"正在生成中"。
    # INT-1505 评估结论：保持 900s 不变——它是「真卡死」的兜底判据，不是用户等待
    # 时长（用户侧等待由前端 180s 超时 + 取消出口负责）；调低会让大任务报告在
    # 正常长生成时被误报失败并提前释放语义，调高则卡死发现更晚。容量扩容后排队
    # 饥饿已由线程池解决，无需再用更短的超时去「催」。
    REPORT_GEN_TIMEOUT_SECONDS = int(os.environ.get('REPORT_GEN_TIMEOUT_SECONDS', 900))
    # 队列饥饿告警阈值（秒）：提交后停留在 QUEUED 阶段超过该时长，说明
    # 线程池工作线程（REPORT_GEN_MAX_WORKERS）被占满，后续提交滞留无产出
    # （INT-117 第二症状；INT-1505 起容量可配置并随告警一起落日志）。
    REPORT_GEN_QUEUE_STUCK_SECONDS = int(os.environ.get('REPORT_GEN_QUEUE_STUCK_SECONDS', 120))
    # 慢阶段观察阈值（秒）：单阶段停留超过该时长记 WARNING（埋点，非失败判定）。
    REPORT_GEN_SLOW_STAGE_SECONDS = int(os.environ.get('REPORT_GEN_SLOW_STAGE_SECONDS', 60))
    # 看门狗扫描周期（秒）。
    REPORT_GEN_WATCHDOG_INTERVAL_SECONDS = int(os.environ.get('REPORT_GEN_WATCHDOG_INTERVAL_SECONDS', 30))
