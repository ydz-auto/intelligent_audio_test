# -*- coding: utf-8 -*-
"""pytest fixtures 与 sys.path 配置。

将项目根目录加入 sys.path，使 task_service / evaluation_service / shared
等顶层包可被直接导入（领域层为纯 dataclass，不依赖 DB/HTTP，无需 mock）。
"""
import os
import sys
import tempfile

import pytest

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
# INT-96 xdist 并行：控制器进程先执行本兜底，worker 进程经环境继承拿到的是
# 控制器的库 URL，直接 setdefault 会全 worker 共享同一 sqlite 文件（多
# worker create_all DDL 竞态：table already exists）——故 worker 内检测到
# 继承的本兜底库（int55_proc_ 命名标记）时强制换独立临时库；外部显式配置的
# DATABASE_URL（无该标记，如指向真库）仍尊重不覆盖。
_XDIST_WORKER = os.environ.get('PYTEST_XDIST_WORKER', '')
_INHERITED_PROC_DB = 'int55_proc_' in os.environ.get('DATABASE_URL', '')
if _XDIST_WORKER and _INHERITED_PROC_DB:
    os.environ.pop('DATABASE_URL', None)
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(
        prefix='int55_proc_%s_' % (_XDIST_WORKER or 'main')
    ) + '/pytest.db')

# shared/proto 目录：*_pb2_grpc.py 使用裸导入 `import xxx_pb2`，
# 需将 proto 目录加入 sys.path 才能解析。
PROTO_DIR = os.path.join(PROJECT_ROOT, 'shared', 'proto')
if os.path.isdir(PROTO_DIR) and PROTO_DIR not in sys.path:
    sys.path.insert(0, PROTO_DIR)


# ── INT-96 xdist loadgroup 分组 ─────────────────────────────
# 配合 `--dist loadgroup` 使用：同组用例固定调度到同一 worker 并保持相对
# 顺序，禁止被拆分。仅收敛 INT-55 修过的顺序污染夹具族（进程级共享
# sqlite 库 + 种子顺序耦合）；未列入的文件视为自包含（自带独立临时库或
# 显式引擎绑定），交给 load 策略自由并行。组内顺序 = 收集序，与串行一致。
_XDIST_GROUP_RULES = (
    # auth sqlite e2e 族：guest/admin 种子在进程级共享库内按收集序幂等播种
    ('tests/unit/test_auth_', 'auth_e2e'),
    ('tests/unit/test_local_oauth_dev_bootstrap', 'auth_e2e'),
    # G3 HTTP e2e 族：注册默认角色 guest 的种子方，与 auth 族共享进程级库
    ('tests/unit/test_g3_', 'g3_e2e'),
)
# 注：transfer gRPC e2e（tests/integration/test_data_transfer_*）同为进程级
# 共享库消费者，但三个文件均按「可单文件独立运行」设计（模块级 setdefault
# 各自带独立临时库、init_db/create_all 幂等），实测拆分并行与同组结果一致；
# 同组会把三个文件（串行约 20s）压进单 worker 成为关键路径，故不分组。


# tryfirst：xdist 在 worker 侧的 pytest_collection_modifyitems 会把
# xdist_group marker 转写为 nodeid 的 @组名 后缀供控制器调度；本 conftest
# 属于后注册的 hook，默认在 xdist 之后执行，marker 会加得太晚导致分组
# 失效（实测 --dist loadgroup 下同组用例仍被拆分），故强制先于 xdist 执行。
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(session, config, items):
    for item in items:
        path = str(item.fspath).replace('\\', '/')
        idx = path.find('/tests/')
        rel = path[idx + 1:] if idx >= 0 else path
        for prefix, group in _XDIST_GROUP_RULES:
            if rel.startswith(prefix):
                item.add_marker(pytest.mark.xdist_group(group))
                break
