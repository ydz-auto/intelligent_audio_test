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
# 顺序，禁止被拆分。
#
# INT-163 起默认分组 = 文件：load 调度会把同文件用例拆到不同 worker（每个
# worker 重跑 module fixture → 全新种子库），凡测试间存在序依赖（前例播种/
# 前例软删、共享 magic id）的文件即「单文件全绿、并行红」（实证：int107
# 第二例单独运行即复现 AttributeError、int152 同名可重建例单独运行即复现
# 断言失败）。默认按文件成组后，每个文件获得与单文件运行完全一致的执行
# 环境；未列入下方规则的文件无需登记即被收敛。
# 显式跨文件组（_XDIST_GROUP_RULES）仍优先：多个文件共享同一进程级库并
# 依赖播种顺序的族，必须跨文件同组。规范详见 tests/README.md。
_XDIST_GROUP_RULES = (
    # auth sqlite e2e 族：guest/admin 种子在进程级共享库内按收集序幂等播种
    ('tests/unit/test_auth_', 'auth_e2e'),
    ('tests/unit/test_local_oauth_dev_bootstrap', 'auth_e2e'),
    # G3 HTTP e2e 族：注册默认角色 guest 的种子方，与 auth 族共享进程级库
    ('tests/unit/test_g3_', 'g3_e2e'),
    # INT-147 认证对齐族：与 G3 同款进程级库 + 真实 servicer 模式；
    # 首个用户 admin 用例会清空/快照恢复 users 表，按收集序排在
    # 同组 test_g3_* 之后执行（g < int147），避免插入他例之间
    ('tests/unit/test_int147_', 'g3_e2e'),
    # INT-72 适配器族：UC-1003 验收演练 fixture 以固定仓库内路径向 adapters
    # 包写入新厂商模块并 reload（跨 worker 共享文件，非进程安全），同文件
    # 用例被拆分并发执行会在 fixture 前置断言撞车；同族 adapter_class_channel
    # 亦断言单例默认快照，一并同组保证其导入先于演练写入完成
    ('tests/unit/test_int72_', 'int72_adapters'),
)
# 注：transfer gRPC e2e（tests/integration/test_data_transfer_*）同为进程级
# 共享库消费者，但三个文件均按「可单文件独立运行」设计（模块级 setdefault
# 各自带独立临时库、init_db/create_all 幂等），默认文件分组下三个文件各占
# 一组、可分赴不同 worker 并行，同文件内保持收集序，行为与单文件一致。


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
        else:
            # INT-163 默认隔离单元 = 文件：同名组内保持收集序，等价单文件运行
            item.add_marker(pytest.mark.xdist_group('file:' + rel))


# ── INT-238：integration 域业务日志根隔离，按用例边界重定向/恢复 ──
# INT-234 原实现为 tests/integration/conftest.py 会话级 autouse 夹具，但
# 会话级 teardown 发生在整个 pytest session 结束时——组合运行下晚于
# tests/unit 全部用例，绝对 LOG_ROOT_DIR 泄漏进 unit 阶段，audit_emit 类
# 「chdir 用例 tmp_path + 相对根 ./logs」的文件落点断言确定性转红
# （文件实际落 INT-234 夹具的 log_root0）。
# 改为 pytest_runtest_setup（先于该 item 全部夹具 setup，含模块/会话级）
# 按 item 路径切换：首见 integration 用例时重定向到本 pytest 进程独占的空
# 临时目录 + 重建日志快照（保持 INT-234「进程内任何业务写入发生前完成
# 重定向」性质，且时点不晚于原会话级夹具）；首见非 integration 用例时恢复
# 原值 + 重建快照。快照 root_dir 以字符串参与写入期 os.path.join（按当时
# cwd 解析），恢复后 unit 用例的相对根语义与基线一致。
_LOG_ROOT_STATE = {'redirected': False, 'original': None, 'iso_root': None}


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    in_integration = '/tests/integration/' in str(item.fspath).replace('\\', '/')
    state = _LOG_ROOT_STATE
    if in_integration == state['redirected']:
        return
    from shared.infrastructure.config import BaseConfig
    from shared.logging.config import reset_log_settings

    if in_integration:
        if state['iso_root'] is None:
            # 每 pytest 进程一个隔离根（xdist 每 worker 独立进程各得其一）；
            # 域内反复进出复用同一根——业务写入器为进程级惰性单例，其根
            # 快照绑定于构造时刻，换根会令再入域的读/写两侧异根
            factory = item.session.config._tmp_path_factory
            state['iso_root'] = str(factory.mktemp('log_root'))
        state['original'] = BaseConfig.LOG_ROOT_DIR
        BaseConfig.LOG_ROOT_DIR = state['iso_root']
        state['redirected'] = True
    else:
        BaseConfig.LOG_ROOT_DIR = state['original']
        state['redirected'] = False
    reset_log_settings()
