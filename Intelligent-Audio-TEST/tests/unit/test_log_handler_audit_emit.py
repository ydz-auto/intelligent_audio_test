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
- 审计日志保持本地文件双写（修复前审计只进文件，行为不回退）
- 非审计系统日志（无任务上下文）保持只写文件、不入库
- 任务日志（有 task_id）分流行为不变

gRPC 边界以 fake batch_create_logs 承接；task_service 侧真实落库由
test_auth_servicer_sqlite_e2e.py 用真实仓储验证。
"""
import json
import os
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

    captured = []

    def _fake_batch_create(logs_payload):
        captured.extend(logs_payload)
        return [9000 + i for i in range(len(logs_payload))]

    monkeypatch.setattr(grpc_clients_mod, 'batch_create_logs', _fake_batch_create)
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
        _, _ = audit_env
        write_auth_audit(AuditEvent.AUTH_ROLE_DELETED, 'role_management', {
            'operator_id': 3, 'target_id': 4,
        })
        log_file = tmp_path / 'logs' / 'app.log'
        assert log_file.exists(), '审计日志本地文件双写丢失'
        assert 'AUTH_ROLE_DELETED' in log_file.read_text(encoding='utf-8')

    def test_system_log_without_task_context_stays_out_of_db(self, audit_env):
        from shared.utils.log_handler import log_not_emit
        _, captured = audit_env
        log_not_emit('INFO', 'plain_module', 'system log without task context',
                     category='system')
        assert not _wait_for(lambda: len(captured) >= 1, timeout=1.5), \
            '非审计系统日志不应入 DB 队列'

    def test_task_log_with_task_id_still_enqueued(self, audit_env):
        from shared.utils.log_handler import log_not_emit
        _, captured = audit_env
        log_not_emit('INFO', 'task_engine', 'step done', category='system',
                     task_id=55)
        assert _wait_for(lambda: len(captured) >= 1), '任务日志未进入 DB 队列'
        assert captured[0]['task_id'] == 55
