# gRPC 生成桩模块包
# 直接从子模块导入：
#     from shared.proto import task_service_pb2_grpc
#     from shared.proto import e2e_service_pb2
import os
import sys

# *_pb2_grpc.py 由 protoc 生成，内部使用裸导入 ``import xxx_service_pb2``，
# 必须将本目录加入 sys.path 才能解析。导入本包（``from shared.proto import ...``）
# 会先执行本 __init__.py，故在此统一注入路径，兼容 Docker 直接 ``python -m``
# 启动、run_all.py 子进程、pytest 等所有启动方式。
_PROTO_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(_PROTO_DIR) and _PROTO_DIR not in sys.path:
    sys.path.insert(0, _PROTO_DIR)
