# -*- coding: utf-8 -*-
"""pytest fixtures 与 sys.path 配置。

将项目根目录加入 sys.path，使 task_service / evaluation_service / shared
等顶层包可被直接导入（领域层为纯 dataclass，不依赖 DB/HTTP，无需 mock）。
"""
import os
import sys
import tempfile

# 项目根目录 = conftest.py 所在目录的上一级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 进程级 DATABASE_URL 兜底（INT-55 缺陷一）：BaseConfig.DATABASE_URL 为类属性、
# 进程内首次导入即冻结，先序测试文件的 setdefault 会替全进程决定库型。
# sqlite:///:memory: 下每个 engine 都是独立空库，后续任何「init_db + 跨线程
# session」的测试（G3 HTTP e2e / transfer gRPC e2e）建表库与请求库不一致，
# servicer 必报 no such table（INT-25 发现、INT-30 修复过单文件，INT-50/51
# 新测试加入后全类复发）。统一兜底为进程级临时文件库：所有 engine 共享同一
# 文件，单跑与全量行为一致；每 pytest 进程独立临时目录，跨运行零残留。
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int55_proc_') + '/pytest.db')

# shared/proto 目录：*_pb2_grpc.py 使用裸导入 `import xxx_pb2`，
# 需将 proto 目录加入 sys.path 才能解析。
PROTO_DIR = os.path.join(PROJECT_ROOT, 'shared', 'proto')
if os.path.isdir(PROTO_DIR) and PROTO_DIR not in sys.path:
    sys.path.insert(0, PROTO_DIR)
