"""api_gateway 端 gRPC 代理对象

把对各微服务的直接 import 调用替换为 gRPC stub 调用。
- ExecutionEngine → gRPC ExecutionService（task_service）
- ReevaluationExecutor → gRPC EvaluationService（evaluation_service）
- device_driver_factory → gRPC DeviceService
- audio_service / AudioService / spl_service → gRPC AudioService（audio_service:50052）
- playback_orchestrator → gRPC PlaybackService（audio_service:50052）
- get_device_result_reextractor → gRPC DeviceResultService（device_service:50053）
- EvaluationConfig → gRPC EvaluationConfigService（evaluation_service）
- report_config_service → gRPC ReportConfigService（report_service）
- auth_config_service → gRPC AuthService（auth_service）
- algorithm_query_service → gRPC AlgorithmQueryService / AlgorithmDefinitionService（algorithm_service）
- task_data_service → gRPC TaskDataService（task_service：聚合统计/分组/日志便捷封装）
"""
from .execution_proxies import execution_engine
from .evaluation_proxies import _ReevaluationExecutorProxy, evaluation_config_service
from .device_proxies import (
    device_driver_factory,
    get_device_result_reextractor,
    get_device_result_collector,
    device_config_service,
)
from .audio_proxies import (
    AudioService,
    audio_service,
    spl_service,
    playback_orchestrator,
    playback_config_service,
    spl_config_service,
    audio_config_service,
)
from .api_config_proxies import api_config_service
from .task_config_proxies import (
    task_config_service,
    testcase_config_service,
    tag_config_service,
    algorithm_config_service,
    task_data_service,
)
from .report_proxies import report_config_service
from .auth_proxies import auth_config_service
from .algorithm_proxies import algorithm_query_service

__all__ = [
    'execution_engine',
    '_ReevaluationExecutorProxy',
    'evaluation_config_service',
    'device_driver_factory',
    'get_device_result_reextractor',
    'get_device_result_collector',
    'device_config_service',
    'AudioService',
    'audio_service',
    'spl_service',
    'playback_orchestrator',
    'playback_config_service',
    'spl_config_service',
    'audio_config_service',
    'api_config_service',
    'task_config_service',
    'testcase_config_service',
    'tag_config_service',
    'algorithm_config_service',
    'task_data_service',
    'report_config_service',
    'auth_config_service',
    'algorithm_query_service',
]
