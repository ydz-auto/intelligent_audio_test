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

    # ===== 报告 task_name 实时补名（INT-1776）=====
    # 报告读路径向 task_service 批量补任务名的等待上限（秒）。报告列表已有
    # 慢的历史（跨域 gRPC + 聚合），补名不得成为新的阻塞点：超时即整页
    # 降级为 ''，不影响列表 / 详情 / 导出返回 200。
    REPORT_TASK_NAME_TIMEOUT_SECONDS = float(
        os.environ.get('REPORT_TASK_NAME_TIMEOUT_SECONDS', 5))

    # ===== 任务用例 ACL 按 ID 取数（INT-1572）=====
    # report_service 报告链路按用例 ID 取用例（对比 / case-averages / 报告生成）
    # 走 task_service.TestCaseConfigService.GetTestCaseDetail——该服务没有按 ID
    # 批量查询的 RPC，只能逐 id 取详情；单条详情含宿主 audio / evaluation 取数，
    # 串行会把 N 次跨服务往返叠成分钟级。以下几点共同决定报告接口能否在网关
    # 60s 截止内返回：
    # - 并发上限：模块级共享线程池容量（跨请求复用，避免每次调用新建线程池）。
    #   返工二轮实测（docker 真实库栈，task 418 的 138 个用例，宿主 audio 有队列）：
    #   1 路 48.8s / 2 路 41.4s / 4 路 18.8s 全部取到；8 路 21/138（117 条撞满
    #   60s 超时）、8 路 + 10s 单条超时 0/138——宿主 audio_service 串行取数，并发
    #   越高单条越慢，8 路是悬崖不是拐点。取 4 路为上限，实际并发由下方的自适应
    #   许可在 [MIN, MAX] 内按超时/成功动态调整。
    TESTCASE_ACL_LOOKUP_MAX_WORKERS = int(
        os.environ.get('TESTCASE_ACL_LOOKUP_MAX_WORKERS', 4))
    # 自适应并发的下限与起始档位（返工二轮）：起始档位取实测能在宿主排队窗口内
    # 稳定出数的 2 路，向下可退到 1 路（串行，单条不会被并发拖慢），向上按连续
    # 成功逐步升到 MAX_WORKERS。
    TESTCASE_ACL_LOOKUP_MIN_WORKERS = int(
        os.environ.get('TESTCASE_ACL_LOOKUP_MIN_WORKERS', 1))
    TESTCASE_ACL_LOOKUP_INITIAL_WORKERS = int(
        os.environ.get('TESTCASE_ACL_LOOKUP_INITIAL_WORKERS', 2))
    # 单条详情查询超时（秒）：单条用例异常/宿主取数卡住时按条放弃，不拖垮整批。
    # 实测单条 p50≈0.3s、冷启动 / 宿主排队窗口可到 30s+。
    TESTCASE_ACL_LOOKUP_TIMEOUT_SECONDS = float(
        os.environ.get('TESTCASE_ACL_LOOKUP_TIMEOUT_SECONDS', 20.0))
    # 单条超时放大系数上限（返工二轮）：超时后系数 ×1.5（上限本值），连续成功
    # 时缓慢回落。整批超时先调大单条超时而不是反复取消在途请求——10s 掐断冷启动
    # 请求会让下游永远热不起来（复测实测 138 用例 0/138 的死亡螺旋）。
    TESTCASE_ACL_LOOKUP_MAX_TIMEOUT_SCALE = float(
        os.environ.get('TESTCASE_ACL_LOOKUP_MAX_TIMEOUT_SCALE', 3.0))
    # 单条最多尝试次数（含首次）：超时的 id 排到队尾重试，预算内尽量取全。
    TESTCASE_ACL_LOOKUP_MAX_ATTEMPTS = int(
        os.environ.get('TESTCASE_ACL_LOOKUP_MAX_ATTEMPTS', 2))
    # 整批截止（秒）：取数阶段最多用多久。这是**上限**——有报告请求预算时
    # （gRPC servicer 注入的剩余时限）取 min(剩余-预留, 本值)，避免 ACL 独占
    # 预算把后面的结果聚合顶过网关 60s。
    TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS = float(
        os.environ.get('TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS', 40.0))
    # 请求预算里留给 ACL 之后阶段的秒数（返工二轮）：结果聚合 + 结果文件 +
    # 响应渲染的实测耗时，ACL 最多用到「截止 - 本值」。
    TESTCASE_ACL_LOOKUP_REQUEST_RESERVE_SECONDS = float(
        os.environ.get('TESTCASE_ACL_LOOKUP_REQUEST_RESERVE_SECONDS', 18.0))
    # 命中缓存有效期（秒）：一次报告请求会对同一批用例多次取数（统计链路实测
    # 2 次、报告生成更多次），第二次起全部命中缓存，否则大任务（如实测 138 用例）
    # 会被重复取数拖过网关 60s。只缓存查到的用例（缺失/软删不缓存，避免新建
    # 用例被负缓存挡住）；0 表示关闭缓存。
    TESTCASE_ACL_CACHE_TTL_SECONDS = float(
        os.environ.get('TESTCASE_ACL_CACHE_TTL_SECONDS', 120.0))
    # 缓存条目上限：超出按插入顺序淘汰最旧条目，防止长跑进程内存无界增长。
    TESTCASE_ACL_CACHE_MAX_ENTRIES = int(
        os.environ.get('TESTCASE_ACL_CACHE_MAX_ENTRIES', 2000))
    # 未取到用例的负缓存有效期（秒，INT-1572 返工）：整批截止或单条超时后，同一
    # 请求内的后续 ACL 调用会再次按 id 重查同一批「查不到」的用例——138 用例
    # 截断后第二次调用会再吃掉一个整批截止（两次 40s 直接越过网关 60s）。负缓存
    # 让同一请求/短时间内不再重复支付；新建用例最迟该时长后可见（报告为只读
    # 展示链路，可接受）；0 表示关闭。
    TESTCASE_ACL_NEGATIVE_CACHE_TTL_SECONDS = float(
        os.environ.get('TESTCASE_ACL_NEGATIVE_CACHE_TTL_SECONDS', 30.0))
    # 「查询未完成」（预算用尽 / 单条失败）的负缓存期（秒，返工二轮）：只需要挡住
    # 同一次报告请求里紧跟着的第二次 ACL 调用（一次请求内该 ACL 调用 2 次），
    # 不能让用户手动重试也拿不到数据。用例不存在仍用上面的 30s。
    TESTCASE_ACL_INCOMPLETE_CACHE_TTL_SECONDS = float(
        os.environ.get('TESTCASE_ACL_INCOMPLETE_CACHE_TTL_SECONDS', 5.0))

    # ===== 报告资源 ACL 配置查询缓存（INT-1572 返工）=====
    # 报告聚合按「每条测试结果」取设备/API 元数据（资源 key、版本号）：case-averages
    # 实测 277 次 GetDevice（10.8s），全是同一批设备的重复取数。设备 / API 配置在
    # 报告链路里只读且变化极少，按 id 做 TTL 缓存；0 表示关闭。
    REPORT_RESOURCE_ACL_CACHE_TTL_SECONDS = float(
        os.environ.get('REPORT_RESOURCE_ACL_CACHE_TTL_SECONDS', 120.0))
    REPORT_RESOURCE_ACL_CACHE_MAX_ENTRIES = int(
        os.environ.get('REPORT_RESOURCE_ACL_CACHE_MAX_ENTRIES', 2000))

    # ===== 结果文件缺失负缓存（INT-1572 返工二轮）=====
    # 结果文件（case_result/{task}/{tc}/…/result_data.json）在历史数据里大量不存在，
    # 每条用例的每次读取都是一次 HEAD + 一次失败的 GET 重试；一次统计请求会对同一批
    # 结果读多轮（资源 key / 资源表头 / result_type 派生）。按路径缓存「不存在」判定，
    # 同一请求内只付一次探测代价；0 表示关闭。
    REPORT_RESULT_FILE_NEGATIVE_CACHE_TTL_SECONDS = float(
        os.environ.get('REPORT_RESULT_FILE_NEGATIVE_CACHE_TTL_SECONDS', 60.0))
    REPORT_RESULT_FILE_NEGATIVE_CACHE_MAX_ENTRIES = int(
        os.environ.get('REPORT_RESULT_FILE_NEGATIVE_CACHE_MAX_ENTRIES', 4000))

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
