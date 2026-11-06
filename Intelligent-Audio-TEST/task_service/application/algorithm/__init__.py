# DEPRECATED: 本包已废弃，algorithm CRUD 已迁移至 algorithm_service（DDD 四层架构）。
# 后续应通过 algorithm_service 的 gRPC 接口访问，详见 shared/clients/grpc_clients.py
# 中的 get_algorithm_group_service_stub / get_algorithm_definition_service_stub。
# 当前保留仅为兼容 task_service.interfaces.grpc.algorithm_config.AlgorithmConfigServiceServicer，
# 待 algorithm_service 的 proto 接入并完成调用方切换后删除整个包。
from .algorithm_crud_service import algorithm_crud_service
