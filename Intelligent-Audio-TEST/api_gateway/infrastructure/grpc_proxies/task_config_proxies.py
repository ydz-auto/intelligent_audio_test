# -*- coding: utf-8 -*-
"""任务/用例/标签/算法配置代理（聚合导出模块，P4-4 大文件拆分）

原文件包含 5 个代理类，已按职责拆分到独立模块，本文件保持
`from .task_config_proxies import ...` 的导入路径不变：

- _TaskConfigProxy / _TestCaseConfigProxy / task_config_service / testcase_config_service
  → task_testcase_config_proxies.py
- _TagConfigProxy / tag_config_service
  → tag_config_proxies.py
- _AlgorithmConfigProxy / algorithm_config_service
  → algorithm_config_proxies.py
- _TaskDataProxy / task_data_service（TaskDataService 聚合统计/分组/日志便捷封装）
  → task_data_proxies.py
"""
from api_gateway.infrastructure.grpc_proxies.task_testcase_config_proxies import (
    _TaskConfigProxy,
    task_config_service,
    _TestCaseConfigProxy,
    testcase_config_service,
)
from api_gateway.infrastructure.grpc_proxies.tag_config_proxies import (
    _TagConfigProxy,
    tag_config_service,
)
from api_gateway.infrastructure.grpc_proxies.algorithm_config_proxies import (
    _AlgorithmConfigProxy,
    algorithm_config_service,
)
from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
    _TaskDataProxy,
    task_data_service,
)

__all__ = [
    '_TaskConfigProxy',
    'task_config_service',
    '_TestCaseConfigProxy',
    'testcase_config_service',
    '_TagConfigProxy',
    'tag_config_service',
    '_AlgorithmConfigProxy',
    'algorithm_config_service',
    '_TaskDataProxy',
    'task_data_service',
]
