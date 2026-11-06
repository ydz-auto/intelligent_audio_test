# -*- coding: utf-8 -*-
"""INT-159 守卫：proto 模块身份收敛 + 用例详情读取失败显式收口。

原缺陷：shared/proto 生成文件可经两种模块身份加载——裸导入（``import
task_service_pb2``，proto 目录在 sys.path）与包内导入（``from shared.proto
import``）。二者是 sys.modules 中两个独立身份，各执行一次生成文件、各向全局
描述符池注册一次 ``task_service.proto``：字节相同时 protobuf 运行时静默去重；
进程存活期间 proto 被重新生成（字节变化，开发侧运行中重生成）时，后到身份的
首次执行即抛 ``Couldn't build proto file into descriptor pool: duplicate file
name task_service.proto``，且该身份每次导入重试都复现——长运行进程（evaluation_service）
评估链自此静默零派发（get_test_case_detail 兜底 None → "找不到测试用例" →
零 TRD 行无失败标记），API 链 TaskCase 永挂 evaluating、E2E 链 0 维度行空转
完成，重启才恢复。

修复：
- shared/proto/__init__.py：裸/包两身份收敛为同一模块对象（先到者执行，
  后到者经 sys.modules 别名命中，不再二次执行、不再重读磁盘）。
- case_evaluation._prepare_evaluation_data：case_data is None 时显式失败收口
  （TestResult 收口 completed、TaskCase 终态 failed 留痕、推进任务统计），
  不再静默 return False。

覆盖（纯单测，不触真实 DB/gRPC；proto 收敛含一个临时包子进程场景）：
- 身份收敛不变量：bare 与包内导入同一模块对象（pb2 与 pb2_grpc）。
- 进程内存活期间磁盘 pb2 重生成：后到身份不重执行文件（子进程临时包模拟
  生产时序，复现前置条件下旧实现必抛 duplicate file name）。
- evaluate_case 用例详情读取失败：TaskCase 标 failed 终态 + TestResult 收口
  completed + 推进任务统计；result_id 为空时不写 TestResult；收口写状态异常
  不外溢（仍返回 False）。
"""
import os
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import evaluation_service.infrastructure.acl.algorithm_acl_repository as _algo_acl_mod
from shared.utils.status_constants import EvaluationStatus, TaskCaseStatus
from shared.utils.status_utils import derive_task_case_status
from evaluation_service.domain.services.evaluation_service.case_evaluation import CaseEvaluationMixin
from evaluation_service.domain.services.evaluation_service.case_loader import CaseLoaderMixin
import shared.proto
import task_service_pb2 as bare_task_pb2  # 裸身份（shared/proto 在 sys.path，由包 __init__ 注入）
import task_service_pb2_grpc as bare_task_grpc
import shared.proto.task_service_pb2 as pkg_task_pb2
import shared.proto.task_service_pb2_grpc as pkg_task_grpc

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_PROTO_DIR = os.path.join(_REPO, 'shared', 'proto')


class TestProtoIdentityConvergence:
    """裸/包两模块身份收敛为同一对象（修复不变量）。"""

    def test_pb2_bare_is_package_identity(self):
        assert bare_task_pb2 is pkg_task_pb2

    def test_pb2_grpc_bare_is_package_identity(self):
        assert bare_task_grpc is pkg_task_grpc

    def test_descriptor_shared(self):
        """两身份共享同一 FileDescriptor（描述符池只注册一份）。"""
        assert bare_task_pb2.DESCRIPTOR is pkg_task_pb2.DESCRIPTOR


class TestMidrunProtoRegeneration:
    """进程存活期间磁盘 pb2 重生成：后到身份不重执行文件（生产时序模拟）。

    用临时包复刻 shared/proto 结构（拷贝真实 __init__.py 与 task_service 生成
    文件），子进程内按生产时序执行：包内导入（注册字节 A）→ 改写磁盘文件
    （字节 B≠A，追加消息）→ 导入 pb2_grpc（内部裸导入 pb2）。修复前该裸导入
    重执行文件必抛 duplicate file name；修复后命中 sys.modules 别名不重执行。
    """

    def test_regenerated_pb2_not_reexecuted_by_bare_import(self):
        pkg_root = tempfile.mkdtemp(prefix='int159_proto_')
        try:
            pkg_dir = os.path.join(pkg_root, 'pkgroot', 'fake_proto')
            os.makedirs(pkg_dir)
            for f in ('__init__.py', 'task_service_pb2.py', 'task_service_pb2_grpc.py'):
                shutil.copy(os.path.join(_PROTO_DIR, f), os.path.join(pkg_dir, f))

            child = (
                "import sys, os\n"
                f"sys.path.insert(0, r'{os.path.join(pkg_root, 'pkgroot')}')\n"
                "import fake_proto.task_service_pb2 as p1\n"          # 字节 A 注册
                # 磁盘"重生成"：向序列化描述符追加 ZZZIntruder159 消息（字节必变）
                "from google.protobuf import descriptor_pb2\n"
                f"_p = r'{os.path.join(pkg_dir, 'task_service_pb2.py')}'\n"
                "_src = open(_p, encoding='utf-8').read()\n"
                "_m = \"DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\"\n"
                "_i = _src.index(_m) + len(_m)\n"
                "_e = _src.index(\"')\", _i)\n"
                "_orig = _src[_i:_e].encode().decode('unicode_escape').encode('latin-1')\n"
                "_fdp = descriptor_pb2.FileDescriptorProto(); _fdp.ParseFromString(_orig)\n"
                "_fdp.message_type.add().name = 'ZZZIntruder159'\n"
                "_esc = ''.join('\\\\x%02x' % b for b in _fdp.SerializeToString())\n"
                "open(_p, 'w', encoding='utf-8').write(_src[:_i] + _esc + _src[_e:])\n"
                "import fake_proto.task_service_pb2_grpc\n"           # 内部裸导入触发点
                "import task_service_pb2 as bare\n"
                "assert bare is p1, 'identity not converged'\n"
                "print('CONVERGED')\n"
            )
            r = subprocess.run(
                [sys.executable, '-c', child],
                capture_output=True, text=True, cwd=pkg_root,
            )
            assert r.returncode == 0, (
                f'重生成后裸导入不应触发描述符池重复注册\nstdout={r.stdout}\nstderr={r.stderr}'
            )
            assert 'CONVERGED' in r.stdout
        finally:
            shutil.rmtree(pkg_root, ignore_errors=True)


class _StubTestCaseDTO:
    def __init__(self, config, algorithm_type='translation'):
        self.config = config
        self.algorithm_type = algorithm_type
        self.name = 'case-x'


class _EvalHost(CaseEvaluationMixin, CaseLoaderMixin):
    """evaluate_case 级最小宿主（同 INT-126 守卫测试的组合方式）。"""

    def __init__(self, case_detail):
        self._task_acl_repo = MagicMock()
        self._task_acl_repo.get_test_case_detail.return_value = case_detail
        self.result_processor = MagicMock()
        self.logs = []
        self.posted_updates = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _post_evaluate_updates(self, task_id, test_case_id):
        self.posted_updates.append((task_id, test_case_id))


class TestCaseLoadFailureFinalization:
    """用例详情读取失败：显式失败收口而非静默 return False（INT-159）。"""

    def _evaluate(self, host, **kwargs):
        # get_field_mappings 走真实 gRPC，单测环境 stub 掉
        with patch.object(_algo_acl_mod, 'get_field_mappings', return_value=MagicMock()):
            return host.evaluate_case(**kwargs)

    def test_load_failure_marks_case_failed(self):
        host = _EvalHost(case_detail=None)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result={'output': {'asr_text': 'x'}},
            algorithm_type='translation', device_type='http_api',
        )
        assert ok is False
        # TaskCase 终态 failed + evaluation_status failed + 留痕
        kw = host._task_acl_repo.update_task_case_status.call_args.kwargs
        assert kw['task_id'] == 't1'
        assert kw['case_id'] == 'c1'
        assert kw['status'] == TaskCaseStatus.FAILED
        assert kw['evaluation_status'] == EvaluationStatus.FAILED
        assert kw['error_message']
        # 推导 status 与 FINISHED 终态一致（任务可收敛，引擎等待可退出）
        assert kw['status'] == derive_task_case_status('completed', EvaluationStatus.FAILED)
        assert kw['status'] not in ('pending', 'running', 'evaluating')
        # TestResult 照常收口 completed（执行已发生）
        host.result_processor.mark_test_result_completed.assert_called_once_with(11)
        # 推进任务统计/引擎通知
        assert host.posted_updates == [('t1', 'c1')]

    def test_load_failure_without_result_id_skips_testresult_write(self):
        """result_id 缺省（防御）：只收口 TaskCase，不写 TestResult。"""
        host = _EvalHost(case_detail=None)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=None, test_case_id='c1',
            algorithm_result={'output': {'asr_text': 'x'}},
            algorithm_type='translation', device_type='http_api',
        )
        assert ok is False
        host.result_processor.mark_test_result_completed.assert_not_called()
        kw = host._task_acl_repo.update_task_case_status.call_args.kwargs
        assert kw['evaluation_status'] == EvaluationStatus.FAILED

    def test_finalization_write_failure_does_not_escape(self):
        """收口写状态自身异常不外溢（仍返回 False，不抛出打断评估入口）。"""
        host = _EvalHost(case_detail=None)
        host._task_acl_repo.update_task_case_status.side_effect = RuntimeError('grpc down')
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result={'output': {'asr_text': 'x'}},
            algorithm_type='translation', device_type='http_api',
        )
        assert ok is False
        assert any('失败收口写状态失败' in str(l.get('content', '')) for l in host.logs)

    def test_load_success_path_unchanged(self):
        """详情读取成功时行为不变：正常分发、不触发失败收口。"""
        host = _EvalHost(case_detail=_StubTestCaseDTO({'dimensions': [{'id': 9}]}))
        host._load_dimension_data = lambda ids, *a, **k: [{'id': i, 'name': f'd{i}'} for i in ids]
        host._create_dimension_results = lambda *a, **k: {9: 'dr-9'}
        host._dispatch_evaluation_tasks = MagicMock()
        host._mark_evaluation_queued = MagicMock()
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result={'output': {'asr_text': 'x'}},
            algorithm_type='translation', device_type='http_api',
        )
        assert ok is True
        host._dispatch_evaluation_tasks.assert_called_once()
        host._task_acl_repo.update_task_case_status.assert_not_called()
