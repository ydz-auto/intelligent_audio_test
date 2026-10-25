# -*- coding: utf-8 -*-
"""log_handler 审计分流回归测试（INT-30 P1 打回修复）。

验收标准 5 的落库通道修复回归：emit 分流原先只按 task_id/test_case_id
判定，无任务上下文的审计事件（category=auth/benchmark）被降级为只写
本地文件，logs 表永远收不到审计行（此前单测又把 write_*_audit 整体
monkeypatch 掉，只验证了调用发生、验证不了落库发生，故自测未暴露）。
本文件固化：

- 审计类日志（auth/benchmark）无 task_id/test_case_id 也入 DB 队列，
  经 worker 批量发往 gRPC batch_create_logs（真实 write_*_audit 全链路）
- 审计日志不参与 TTL 去重（相同负载连续两条都必须落库）
- 审计日志保持本地文件双写（修复前审计只进文件，行为不回退；
  INT-81 后文件路径为 logs/{service_name}/app-{hostname}-{pid}.log）
- 非审计系统日志（无任务上下文）保持只写文件、不入库
- 业务日志（有 task_id）去库化：落业务文件（INT-81），
  LOG_BUSINESS_DB_ENABLED=True 时兼容性双写入库（回滚开关）

gRPC 边界以 fake batch_create_logs 承接；task_service 侧真实落库由
test_auth_servicer_sqlite_e2e.py 用真实仓储验证。
"""
import json
import os
import socket
import tempfile
import time

import pytest

# 共享配置在导入期校验必填环境变量；默认值用进程级临时文件库（不能用 :memory:，
# 见 test_auth_user_role_management.py 顶部说明），本文件不触库，仅满足导入校验
os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int30_emit_') + '/emit.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import AuditEvent


def _wait_for(condition, timeout=3.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


@pytest.fixture()
def audit_env(monkeypatch, tmp_path):
    """独立 DatabaseLogHandler：worker 消费后由 fake batch_create_logs 承接。

    - chdir 到 tmp：文件处理器写入临时目录，不污染仓库
    - _batch_size=1：worker 取到即冲刷，消除定时器等待
    - _state._global_db_handler 指向本实例：log_not_emit / write_*_audit
      全部路由到它
    """
    import shared.clients.grpc_clients as grpc_clients_mod
    import shared.utils.log_handler._state as lh_state
    from shared.utils.log_handler import DatabaseLogHandler

    # 跨文件收集顺序隔离：真实审计链路（sqlite e2e 等）会经 get_db_handler()
    # 惰性创建全局 handler，其 worker 的 pending 批次（_batch_timeout=1s）会在
    # 本 fixture 打上 fake 后补发进 captured，污染断言。先停既有全局 handler
    # 的 worker（收到 None 即 break，pending 批次不冲刷），再装 fake 与新实例。
    prev = lh_state._global_db_handler
    if prev is not None:
        prev.queue.put(None)
        prev_worker = getattr(prev, 'worker_thread', None)
        if prev_worker is not None:
            prev_worker.join(timeout=2.0)

    captured = []

    def _fake_batch_create(logs_payload):
        captured.extend(logs_payload)
        return [9000 + i for i in range(len(logs_payload))]

    monkeypatch.setattr(grpc_clients_mod, 'batch_create_logs', _fake_batch_create)
    # worker 批刷路径会同步触发归档巡检（_check_and_archive → 真实 gRPC
    # get_log_count → OSS 客户端初始化）。机器上有驻留服务栈时该真实调用
    # 可阻塞 worker 30s+（INT-55 缺陷二：第二条审计滞留队列，3s 断言窗口
    # 超时；12:17 通过 / 19:3x 确定性失败的机器态差异即此）。本文件只验证
    # emit 分流与批写路由，归档巡检链路整体 fake 为空转。
    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 0})
    monkeypatch.setattr(
        grpc_clients_mod, 'archive_logs',
        lambda days=30, dry_run=False: {'groups': {}, 'remaining_count': 0})
    import shared.clients.oss_client as oss_client_mod
    monkeypatch.setattr(oss_client_mod.oss, 'is_available', lambda: False)
    monkeypatch.chdir(tmp_path)
    handler = DatabaseLogHandler()
    handler._batch_size = 1
    handler.set_console_log(False)
    monkeypatch.setattr(lh_state, '_global_db_handler', handler)
    yield handler, captured
    handler.queue.put(None)


class TestAuditEmitRouting:

    def test_auth_audit_lands_in_db_queue_without_task_context(self, audit_env):
        from auth_service.application.services.auth_audit import write_auth_audit
        _, captured = audit_env
        write_auth_audit(AuditEvent.AUTH_USER_CREATED, 'user_management', {
            'operator_id': 1, 'target_id': 2, 'delta': {'username': 'u1'},
        })
        assert _wait_for(lambda: len(captured) >= 1), 'auth 审计未进入 DB 队列'
        entry = captured[0]
        assert entry['category'] == 'auth'
        assert entry['task_id'] is None and entry['test_case_id'] is None
        payload = json.loads(entry['content'])
        assert payload['event'] == 'AUTH_USER_CREATED'
        assert payload['operator_id'] == 1
        assert payload['target_id'] == 2
        assert payload['delta'] == {'username': 'u1'}

    def test_benchmark_audit_lands_in_db_queue(self, audit_env):
        from report_service.application.services.benchmark_audit import (
            write_benchmark_audit,
        )
        _, captured = audit_env
        write_benchmark_audit(AuditEvent.BENCHMARK_RANKING_COMPUTED,
                              'benchmark_ranking', {'algorithm_type': 'asr'})
        assert _wait_for(lambda: len(captured) >= 1), 'benchmark 审计未进入 DB 队列'
        entry = captured[0]
        assert entry['category'] == 'benchmark'
        assert entry['task_id'] is None
        assert json.loads(entry['content'])['event'] == 'BENCHMARK_RANKING_COMPUTED'

    def test_duplicate_audit_payload_not_deduped(self, audit_env):
        from auth_service.application.services.auth_audit import write_auth_audit
        _, captured = audit_env
        payload = {'operator_id': 7, 'target_id': 9,
                   'delta': {'permission': 'task:read'}}
        write_auth_audit(AuditEvent.AUTH_USER_PERMISSION_GRANTED,
                         'user_management', payload)
        write_auth_audit(AuditEvent.AUTH_USER_PERMISSION_GRANTED,
                         'user_management', payload)
        assert _wait_for(lambda: len(captured) >= 2), '相同审计负载被 TTL 去重吞掉'
        assert all(json.loads(e['content'])['event']
                   == 'AUTH_USER_PERMISSION_GRANTED' for e in captured)

    def test_auth_audit_also_written_to_local_file(self, audit_env, tmp_path):
        from auth_service.application.services.auth_audit import write_auth_audit
        from shared.logging import resolve_service_name
        _, _ = audit_env
        write_auth_audit(AuditEvent.AUTH_ROLE_DELETED, 'role_management', {
            'operator_id': 3, 'target_id': 4,
        })
        # INT-81：服务文件日志按 logs/{service_name}/app-{hostname}-{pid}.log 分目录（进程标识互不冲突）
        log_file = (tmp_path / 'logs' / resolve_service_name()
                    / f'app-{socket.gethostname()}-{os.getpid()}.log')
        assert log_file.exists(), '审计日志本地文件双写丢失'
        assert 'AUTH_ROLE_DELETED' in log_file.read_text(encoding='utf-8')

    def test_system_log_without_task_context_stays_out_of_db(self, audit_env):
        from shared.utils.log_handler import log_not_emit
        _, captured = audit_env
        log_not_emit('INFO', 'plain_module', 'system log without task context',
                     category='system')
        assert not _wait_for(lambda: len(captured) >= 1, timeout=1.5), \
            '非审计系统日志不应入 DB 队列'

    def test_task_log_goes_to_business_file_not_db(self, audit_env, tmp_path):
        """INT-81：业务日志去库化 —— 有 task_id 的日志落业务文件，不入 DB 队列。"""
        from shared.utils.log_handler import log_not_emit
        _, captured = audit_env
        log_not_emit('INFO', 'task_engine', 'business step done', category='execution',
                     task_id=55, test_case_id='TC-9', device_id=3, round=2)
        # 不入库（审计除外）
        assert not _wait_for(lambda: len(captured) >= 1, timeout=1.5), \
            '业务日志不应再写 logs 表'
        # 落业务文件：logs/business/{task}/{device}/{round}/execution.{service}.{hostname}-{pid}.log
        from shared.logging import resolve_service_name
        identity = f'{socket.gethostname()}-{os.getpid()}'
        biz_file = (tmp_path / 'logs' / 'business' / '55' / '3' / '2'
                    / f'execution.{resolve_service_name()}.{identity}.log')
        assert biz_file.exists(), '业务日志未按路径模板落文件'
        import json as _json
        line = biz_file.read_text(encoding='utf-8').strip().splitlines()[0]
        entry = _json.loads(line)
        assert entry['task_id'] == 55
        assert entry['device_id'] == 3
        assert entry['round'] == 2
        assert entry['log_type'] == 'execution'
        assert 'business step done' in entry['content']
