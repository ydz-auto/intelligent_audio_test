# -*- coding: utf-8 -*-
"""pytest fixtures 与 sys.path 配置。

将项目根目录加入 sys.path，使 task_service / evaluation_service / shared
等顶层包可被直接导入（领域层为纯 dataclass，不依赖 DB/HTTP，无需 mock）。
"""
import os
import sys

# 项目根目录 = conftest.py 所在目录的上一级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# shared/proto 目录：*_pb2_grpc.py 使用裸导入 `import xxx_pb2`，
# 需将 proto 目录加入 sys.path 才能解析。
PROTO_DIR = os.path.join(PROJECT_ROOT, 'shared', 'proto')
if os.path.isdir(PROTO_DIR) and PROTO_DIR not in sys.path:
    sys.path.insert(0, PROTO_DIR)
