"""
数据模型包 (Models Package)

P5 改造后，所有 PO 已下沉到各微服务 infrastructure/persistence/models/ 下，
本包不再持有 PO 定义，仅保留基础设施：
- database.py    : db 命名空间、scoped_session、init_db、utc8now
- common_enums.py: ReportStatus / TaskStatus / ReportType 跨服务共享枚举

各服务 PO 直接从对应服务导入：
    from task_service.infrastructure.persistence.models import Task, TestCase
    from evaluation_service.infrastructure.persistence.models import Dimension
    from algorithm_service.infrastructure.persistence.models import AlgorithmDefinition

注意：跨服务不应直接 import 其他服务的 PO，应通过 gRPC 客户端访问：
    - task_service 数据 → shared/clients/grpc_clients.get_task_data_service_stub /
      get_task_config_service_stub / get_testcase_config_service_stub
    - evaluation_service 数据 → get_evaluation_config_service_stub /
      get_evaluation_data_service_stub
    - algorithm_service 数据 → get_algorithm_definition_service_stub /
      get_algorithm_group_service_stub
"""
