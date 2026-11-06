# gRPC 生成桩模块包
# 直接从子模块导入：
#     from shared.proto import task_service_pb2_grpc
#     from shared.proto import e2e_service_pb2
import importlib
import os
import sys

# *_pb2_grpc.py 由 protoc 生成，内部使用裸导入 ``import xxx_service_pb2``，
# 必须将本目录加入 sys.path 才能解析。导入本包（``from shared.proto import ...``）
# 会先执行本 __init__.py，故在此统一注入路径，兼容 Docker 直接 ``python -m``
# 启动、stack.py 子进程、pytest 等所有启动方式。
_PROTO_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(_PROTO_DIR) and _PROTO_DIR not in sys.path:
    sys.path.insert(0, _PROTO_DIR)

# INT-159：同一生成文件在进程内只允许执行一次。
#
# 生成文件可经两种模块身份加载：裸导入（``import task_service_pb2``，本目录在
# sys.path）与包内导入（``from shared.proto import task_service_pb2``）。二者是
# sys.modules 中两个独立身份，各执行一次生成文件、各向全局描述符池注册一次
# ``task_service.proto``：字节相同时 protobuf 运行时静默去重；进程存活期间 proto
# 被重新生成（字节变化，如开发侧运行中重生成）时，后到身份的首次执行即抛
# ``duplicate file name``，且该身份每次导入重试都复现——长运行进程评估链静默
# 零派发直到重启。此处把两个身份收敛为同一模块对象：先到者执行，后到者经
# sys.modules 别名命中，不再二次执行、不再重读磁盘。
for _entry in sorted(os.listdir(_PROTO_DIR)):
    if not (_entry.endswith('_pb2.py') or _entry.endswith('_pb2_grpc.py')):
        continue
    _bare = _entry[:-3]
    _full = __name__ + '.' + _bare
    if _bare in sys.modules:
        # 裸导入身份先到（生成文件内部 import 或 sys.path 直导）：包内身份复用之
        _mod = sys.modules[_bare]
    else:
        try:
            _mod = importlib.import_module(_full)
        except Exception:
            # 生成文件自身不可加载时保持既有行为：留给显式导入处报错
            continue
        # 裸身份别名：生成文件内部裸导入命中同一模块，不重复注册描述符
        sys.modules[_bare] = _mod
    sys.modules[_full] = _mod
    globals()[_bare] = _mod
