# -*- coding: utf-8 -*-
"""INT-336 验收测试（测试工程师2）

验收标准：
1. 单测覆盖三态：api_settings=None / 键缺失 / 正常 dict——均不抛异常，
   超时取值符合既有语义（普通 default_timeout=30 / llm_judge 120 / 配置值优先）。
2. evaluation_service 单测全量回归通过。

开发交付（commit 83959029）已含 worker_management._get_timeout_from_dim_config
的 9 例三态单测（test_int336_api_settings_null_guard.py）。本文件补齐其未覆盖面：

A. endpoint_worker 两处读取点（开发修复的另外 2/3 处，原无任何测试）：
   - _build_evaluation_context:365 body_template 读取（api_settings=null → 不抛）
   - _prepare_api_config:410 method/headers 读取（null → 默认 POST + 空 headers）
   开发报告「建议测试点 3」即此路径。
B. worker 创建链路真实组合：WorkerManagementMixin._get_or_create_worker
   以 api_settings=None 维度真实执行 → EndpointWorker 落默认 max_timeout=30；
   llm_judge 维度 → 120（开发报告「建议测试点 1」单测口径）。
C. 真实 _EvaluationServiceHost（全 Mixin 组合体）上 _get_timeout_from_dim_config
   三态冒烟，替代 DB 置 NULL 的实机评估（隔离库栈用例，不在本卡验收范围）。

纯单测：object.__new__ 最小宿主 + 真实被测方法，不触 DB/gRPC/Redis/线程池。
"""
import os
import queue
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


# ==================== A. endpoint_worker 读取点（开发修复 2/3 处） ====================

from evaluation_service.infrastructure.evaluation_api.endpoint_worker import (
    EndpointWorker,
)


def _bare_worker(eval_service=None):
    """绕开 __init__（Redis/线程/日志）的最小 EndpointWorker 宿主。"""
    worker = EndpointWorker.__new__(EndpointWorker)
    worker.endpoint_url = 'http://eval:8888'
    worker.eval_service = eval_service
    return worker


_NONE_DIM = {
    'id': 9001, 'name': 'api_settings为null的维度',
    'dimension_type': 'main', 'task_type_code': 'dim_eval',
    'api_settings': None,              # JSON null → None（缺陷触发形态）
    'api_endpoints': [{'url': 'http://eval:8888', 'max_timeout': 30}],
    'api_url': 'http://eval:8888',
    'input_params': [],
}


def test_int336_accept_endpoint_worker_context_none_api_settings():
    """验收1扩展：_build_evaluation_context 遇 api_settings=None 不抛 NoneType，
    body_template 为 None → build_payload 收到 None（eval_server 用自身配置）"""
    captured = {}

    def _fake_build_payload(body_template, context, **kw):
        captured['body_template'] = body_template
        return {'kept': True}

    svc = MagicMock()
    svc.api_client.build_payload.side_effect = _fake_build_payload
    worker = _bare_worker(svc)

    # field_defs 用真实 FieldMapperWrapper 形状：无映射字段 → 空集
    EndpointWorker._log = lambda self, **kwargs: None
    try:
        payload = worker._build_evaluation_context(
            505, 'tc-accept', {'rounds': [{'output': 'ok'}]},
            _NONE_DIM, 'voice_llm', [], 9001, {}, {},
            group_items=[(_NONE_DIM, 1)],
        )
    finally:
        del EndpointWorker._log  # 恢复 EvaluationLoggerMixin 的绑定方法

    assert payload['kept'] is True            # build_payload 的返回原样透传
    assert payload['sub_tasks'] == ['dim_eval']  # group_items 提取不受影响
    assert captured['body_template'] is None  # null api_settings → 模板缺省


def test_int336_accept_prepare_api_config_none_api_settings():
    """验收1扩展：_prepare_api_config 遇 api_settings=None 不抛 NoneType，
    method 默认 POST、headers 空表、端点从 api_endpoints 正常提取"""
    worker = _bare_worker()
    EndpointWorker._log = lambda self, **kwargs: None
    try:
        endpoints, method, headers, dim_info, audio_field_names = \
            worker._prepare_api_config(_NONE_DIM, [(_NONE_DIM, 1)])
    finally:
        del EndpointWorker._log

    assert endpoints == [{'url': 'http://eval:8888', 'max_timeout': 30}]
    assert method == 'POST'
    assert headers == {}
    assert dim_info['dimension_type'] == 'main'
    assert audio_field_names == set()


def test_int336_accept_prepare_api_config_missing_and_normal_api_settings():
    """键缺失 / 正常 dict 两态在 _prepare_api_config 同口径（端点提取不受影响）"""
    worker = _bare_worker()
    EndpointWorker._log = lambda self, **kwargs: None
    try:
        _, method_missing, headers_missing, _, _ = worker._prepare_api_config(_NONE_DIM, [])
        # 键缺失形态：整个键不存在
        dim_no_key = {k: v for k, v in _NONE_DIM.items() if k != 'api_settings'}
        _, method_nokey, headers_nokey, _, _ = worker._prepare_api_config(dim_no_key, [])
        # 正常 dict 形态：配置值优先
        dim_normal = {**_NONE_DIM,
                      'api_settings': {'method': 'PUT', 'headers': {'X-Trace': '1'}}}
        _, method_normal, headers_normal, _, _ = worker._prepare_api_config(dim_normal, [])
    finally:
        del EndpointWorker._log

    assert (method_missing, headers_missing) == ('POST', {})
    assert (method_nokey, headers_nokey) == ('POST', {})
    assert (method_normal, headers_normal) == ('PUT', {'X-Trace': '1'})


# ==================== B. worker 创建链路（超时兜底链真实组合） ====================

from evaluation_service.infrastructure.evaluation_api.worker_management import (
    WorkerManagementMixin,
)


class _RealChainHost(WorkerManagementMixin):
    """真实 _get_or_create_worker + _get_timeout_from_dim_config 的最小宿主。

    不调 __init__（避开 api_client/DB 日志），手工铺齐被测链路依赖。
    """

    def __init__(self):
        import threading as _t
        self.endpoint_workers = {}
        self.endpoint_workers_lock = _t.Lock()
        self.api_client = SimpleNamespace(default_max_concurrent=10,
                                          endpoint_configs={})

    def _log(self, **kwargs):
        pass


def test_int336_accept_get_or_create_worker_none_api_settings_default_timeout():
    """验收1：api_settings=None 的维度经真实 _get_or_create_worker 创建 worker
    不抛异常，max_timeout 落默认 30（日志口径「超时时间: 30秒」的数据源）"""
    host = _RealChainHost()
    dim = {'id': 9002, 'dimension_type': 'main', 'api_settings': None,
           'api_endpoints': [], 'api_url': 'http://eval-fresh:9999'}

    worker = host._get_or_create_worker('http://eval-fresh:9999', dim)

    assert worker.max_timeout == 30
    assert worker.endpoint_url == 'http://eval-fresh:9999'
    # 清理：创建即启动消费线程（daemon），显式停掉防跨用例泄漏
    worker.stop()


def test_int336_accept_get_or_create_worker_llm_judge_120():
    """验收1：llm_judge 分支经真实 worker 创建链落 120 秒默认语义"""
    host = _RealChainHost()
    dim = {'id': 9003, 'dimension_type': 'llm_judge', 'api_settings': None,
           'api_endpoints': [], 'api_url': 'http://eval-llm:9998'}

    worker = host._get_or_create_worker('http://eval-llm:9998', dim)
    assert worker.max_timeout == 120
    worker.stop()


def test_int336_accept_get_or_create_worker_configured_timeout_wins():
    """验收2（单测口径）：正常 api_settings.timeout 配置值仍优先于默认值"""
    host = _RealChainHost()
    dim = {'id': 9004, 'dimension_type': 'main',
           'api_settings': {'method': 'POST', 'timeout': 90},
           'api_endpoints': [], 'api_url': 'http://eval-cfg:9997'}

    worker = host._get_or_create_worker('http://eval-cfg:9997', dim)
    assert worker.max_timeout == 90
    worker.stop()


def test_int336_accept_worker_creation_concurrent_none_dims_no_crash():
    """null 维度并发创建同端点 worker：锁内 _get_timeout_from_dim_config
    真实执行，无 NoneType 崩溃、只落一个 worker（并发语义不回归）"""
    host = _RealChainHost()
    dim = {'id': 9005, 'dimension_type': 'main', 'api_settings': None,
           'api_endpoints': [], 'api_url': 'http://eval-race:9996'}
    errors = []

    def _create():
        try:
            w = host._get_or_create_worker('http://eval-race:9996', dim)
            assert w.max_timeout == 30
        except Exception as e:  # pragma: no cover - 断言失败经 errors 上抛
            errors.append(e)
        finally:
            host.endpoint_workers_lock.acquire()
            try:
                w = host.endpoint_workers.get('http://eval-race:9996')
            finally:
                host.endpoint_workers_lock.release()
            if w is not None:
                w.stop()

    threads = [threading.Thread(target=_create) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert errors == []
    assert set(host.endpoint_workers) == {'http://eval-race:9996'}


# ==================== C. 真实宿主组合体三态冒烟 ====================

def _host_instance():
    """真实 _EvaluationServiceHost：全 Mixin 组合体（单例，铺最小依赖）。

    该单例在模块导入时已 __init__（含 _load_all_endpoint_configs），
    进程内复用即可；endpoint_workers 可能为空 dict。
    """
    from evaluation_service.infrastructure.evaluation_service_host import (
        evaluation_service as host,
    )
    return host


def test_int336_accept_real_host_timeout_three_states():
    """验收1+2：真实全组合宿主上三态超时取值——None/缺失走默认、配置值优先"""
    host = _host_instance()

    assert host._get_timeout_from_dim_config(
        {'id': 1, 'dimension_type': 'main', 'api_settings': None,
         'api_endpoints': [], 'api_url': None}) == 30
    assert host._get_timeout_from_dim_config(
        {'id': 2, 'dimension_type': 'main',
         'api_endpoints': [], 'api_url': None}) == 30
    assert host._get_timeout_from_dim_config(
        {'id': 3, 'dimension_type': 'main',
         'api_settings': {'timeout': 66},
         'api_endpoints': [], 'api_url': None}) == 66
    assert host._get_timeout_from_dim_config(
        {'id': 4, 'dimension_type': 'llm_judge', 'api_settings': None}) == 120
