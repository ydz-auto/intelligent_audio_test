# -*- coding: utf-8 -*-
"""中枢侧中转执行触发器单元测试（F2.3/INT-53）。

覆盖：is_hub/relay_trigger_enabled 自门控、配置装配（含显式覆盖）、
fail-closed 入站 token、claim → execute_incoming → finish 收敛主流程、
执行失败收敛 failed（不悬挂）、finish/claim 异常不杀轮询线程、生命周期起停。

ACL 以替身注入，不依赖 DB / HTTP / Redis。
"""
import os
import threading

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.infrastructure.acl.hub_relay_trigger import HubRelayTrigger


class FakeSettings:
    def __init__(self, *, self_zone='B', hub_zone='B', enabled=True,
                 poll_interval=0.01, claim_stale=1800):
        self.self_zone = self_zone
        self.hub_zone = hub_zone
        self.sync_back_zone = 'A'
        self.relay_trigger_enabled = enabled
        self.relay_trigger_poll_interval_seconds = poll_interval
        self.relay_trigger_claim_stale_seconds = claim_stale

    @property
    def is_hub(self):
        return self.self_zone == self.hub_zone


class FakeClient:
    def __init__(self, tokens=None):
        # 默认带标准 A->B token；显式传 {} 须保持为空（fail-closed 用例依赖）
        self.tokens = {'A_B': 'secret-ab'} if tokens is None else dict(tokens)
        self.claim_calls = []
        self.finish_calls = []
        self.claim_results = []
        self.claim_error = None
        self.finish_error = None
        self.on_finish = None

    def get_token(self, src_zone, dst_zone):
        return self.tokens.get(f'{src_zone}_{dst_zone}')

    def claim_relay(self, *, token, stale_seconds):
        if self.claim_error is not None:
            raise self.claim_error
        self.claim_calls.append({'token': token, 'stale_seconds': stale_seconds})
        if self.claim_results:
            return self.claim_results.pop(0)
        return None

    def finish_relay(self, transfer_id, *, state, error=None, token=''):
        if self.finish_error is not None:
            raise self.finish_error
        self.finish_calls.append(
            {'transfer_id': transfer_id, 'state': state, 'error': error, 'token': token})
        if self.on_finish is not None:
            self.on_finish(transfer_id, state)
        return {'success': True, 'data': {'finished': True}}


class FakeACL:
    def __init__(self, settings=None, client=None):
        self.settings = settings or FakeSettings()
        self.client = client or FakeClient()
        self.executed = []
        self.execute_error = None

    def execute_incoming(self, transfer_id):
        if self.execute_error is not None:
            raise self.execute_error
        self.executed.append(transfer_id)
        return {'score': 0.92}


def make_trigger(acl=None, **kwargs):
    return HubRelayTrigger(acl or FakeACL(), **kwargs)


# ================= 门控与配置 =================
class TestTriggerGating:
    def test_edge_zone_does_not_start(self):
        acl = FakeACL(settings=FakeSettings(self_zone='A', hub_zone='B'))
        trigger = make_trigger(acl)
        trigger.start()
        assert trigger._thread is None  # 边缘区（A）不启动

    def test_disabled_does_not_start(self):
        acl = FakeACL(settings=FakeSettings(enabled=False))
        trigger = make_trigger(acl)
        trigger.start()
        assert trigger._thread is None

    def test_hub_and_enabled_starts_thread(self):
        acl = FakeACL()  # self B == hub B, enabled
        trigger = make_trigger(acl)
        trigger.start()
        try:
            assert trigger._thread is not None and trigger._thread.is_alive()
            assert trigger._thread.name == 'HubRelayTrigger'
            assert trigger._thread.daemon is True
        finally:
            trigger.stop()
        assert trigger._thread is None

    def test_double_start_does_not_spawn_second_thread(self):
        trigger = make_trigger()
        trigger.start()
        first = trigger._thread
        trigger.start()
        try:
            assert trigger._thread is first
        finally:
            trigger.stop()


class TestTriggerConfig:
    def test_config_from_acl_settings(self):
        acl = FakeACL(settings=FakeSettings(poll_interval=0.5, claim_stale=900))
        trigger = make_trigger(acl)
        assert trigger.poll_interval_seconds == 0.5
        assert trigger.claim_stale_seconds == 900

    def test_explicit_overrides_win_over_settings(self):
        trigger = make_trigger(poll_interval_seconds=3.5, claim_stale_seconds=60)
        assert trigger.poll_interval_seconds == 3.5
        assert trigger.claim_stale_seconds == 60

    def test_missing_settings_keys_fall_back_to_defaults(self):
        class BareSettings:
            self_zone = 'B'
            hub_zone = 'B'
            sync_back_zone = 'A'
            is_hub = True

        trigger = HubRelayTrigger(FakeACL(settings=BareSettings()))
        assert trigger.poll_interval_seconds == 2.0
        assert trigger.claim_stale_seconds == 1800


# ================= fail-closed 入站 token =================
class TestInboundToken:
    def test_missing_route_token_fails_closed(self):
        acl = FakeACL(client=FakeClient(tokens={}))  # 未配置 A->B token
        trigger = make_trigger(acl)
        with pytest.raises(RuntimeError, match='fail-closed|预共享'):
            trigger._inbound_token()

    def test_inbound_token_uses_sync_back_route(self):
        client = FakeClient(tokens={'A_B': 'secret-ab'})
        trigger = make_trigger(FakeACL(client=client))
        assert trigger._inbound_token() == 'secret-ab'


# ================= 配置完整性门控与告警限频（INT-84） =================
class TestConfigCompletenessGate:
    """入站 token 缺失 → 判定未启用：不启动线程，仅记一次 INFO。"""

    def test_missing_route_token_does_not_start(self, caplog):
        import logging
        acl = FakeACL(client=FakeClient(tokens={}))  # 未配置 A->B token
        trigger = make_trigger(acl)
        with caplog.at_level(logging.INFO,
                             logger='evaluation_service.infrastructure.acl.hub_relay_trigger'):
            trigger.start()
        assert trigger._thread is None
        gate_logs = [r for r in caplog.records if '区配置不完整' in r.message]
        assert len(gate_logs) == 1, '配置不完整应仅记一次 INFO'

    def test_repeated_start_with_missing_token_logs_once_each_not_spam(self, caplog):
        import logging
        acl = FakeACL(client=FakeClient(tokens={}))
        trigger = make_trigger(acl)
        with caplog.at_level(logging.INFO,
                             logger='evaluation_service.infrastructure.acl.hub_relay_trigger'):
            trigger.start()
            trigger.start()
        # start() 只在启动点调用（app lifespan 一次），此处验证重复调用也只
        # 每次一条 INFO（无 WARNING/ERROR 周期告警路径）
        gate_logs = [r for r in caplog.records if '区配置不完整' in r.message]
        assert len(gate_logs) == 2
        assert all(r.levelno == logging.INFO for r in gate_logs)

    def test_token_configured_starts_normally(self):
        acl = FakeACL(client=FakeClient(tokens={'A_B': 'secret-ab'}))
        trigger = make_trigger(acl)
        trigger.start()
        try:
            assert trigger._thread is not None and trigger._thread.is_alive()
        finally:
            trigger.stop()


class TestClaimWarnRateLimit:
    """同原因认领失败告警限频：5 分钟窗口内最多 1 条 WARNING。"""

    def test_same_reason_suppressed_within_window(self, caplog):
        import logging
        trigger = make_trigger()
        with caplog.at_level(logging.DEBUG,
                             logger='evaluation_service.infrastructure.acl.hub_relay_trigger'):
            err = RuntimeError('transfer_agent unreachable')
            for _ in range(10):
                trigger._warn_claim_failure_throttled(err)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(warnings) == 1, '同原因窗口内只应 1 条 WARNING'
        assert len(debugs) == 9, '窗口内重复失败降级 DEBUG'

    def test_different_reason_not_suppressed(self, caplog):
        import logging
        trigger = make_trigger()
        with caplog.at_level(logging.WARNING,
                             logger='evaluation_service.infrastructure.acl.hub_relay_trigger'):
            trigger._warn_claim_failure_throttled(RuntimeError('err-a'))
            trigger._warn_claim_failure_throttled(RuntimeError('err-b'))
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2

    def test_window_expiry_logs_new_warning(self, caplog):
        import logging
        import time as _time
        trigger = make_trigger()
        with caplog.at_level(logging.WARNING,
                             logger='evaluation_service.infrastructure.acl.hub_relay_trigger'):
            trigger._warn_claim_failure_throttled(RuntimeError('same-err'))
            # 模拟窗口过期（回拨时间戳，不真实等待 5 分钟）
            reason, _ = trigger._last_claim_warn
            trigger._last_claim_warn = (reason,
                                        _time.monotonic() - 301)
            trigger._warn_claim_failure_throttled(RuntimeError('same-err'))
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2

    def test_success_resets_throttle_state(self):
        """认领成功后限频状态清零：再次失败立即告警（不落入旧窗口）。"""
        client = FakeClient()
        client.claim_results = ['t-ok']
        finished = threading.Event()
        client.on_finish = lambda *_args, **_kw: finished.set()
        trigger = make_trigger(FakeACL(client=client), poll_interval_seconds=0.01)
        trigger._last_claim_warn = ('old-reason', 0.0)
        trigger.start()
        try:
            assert finished.wait(timeout=5), '认领成功路径未走完'
        finally:
            trigger.stop()
        assert trigger._last_claim_warn is None


# ================= 认领 → 执行 → 终态收敛 =================
class TestClaimExecuteFinishFlow:
    def test_claim_passes_token_and_stale_seconds(self):
        client = FakeClient()
        client.claim_results = ['t1']
        trigger = make_trigger(FakeACL(client=client), claim_stale_seconds=777)

        claimed = trigger._claim_next()

        assert claimed == 't1'
        assert client.claim_calls == [
            {'token': 'secret-ab', 'stale_seconds': 777}]

    def test_execute_success_finishes_executed(self):
        client = FakeClient()
        acl = FakeACL(client=client)
        trigger = make_trigger(acl)

        trigger._execute_claimed('t1')

        assert acl.executed == ['t1']
        assert client.finish_calls == [
            {'transfer_id': 't1', 'state': 'executed', 'error': None,
             'token': 'secret-ab'}]

    def test_execute_failure_converges_to_failed_without_hang(self):
        client = FakeClient()
        acl = FakeACL(client=client)
        acl.execute_error = RuntimeError('boom-unpack')
        trigger = make_trigger(acl)

        trigger._execute_claimed('t1')  # 不应抛出

        assert client.finish_calls == [
            {'transfer_id': 't1', 'state': 'failed', 'error': 'boom-unpack',
             'token': 'secret-ab'}]

    def test_finish_failure_does_not_propagate(self):
        client = FakeClient()
        client.finish_error = RuntimeError('finish http down')
        trigger = make_trigger(FakeACL(client=client))

        trigger._execute_claimed('t1')  # 终态收敛失败仅记日志，不悬挂线程

    def test_claim_failure_keeps_loop_alive(self):
        client = FakeClient()
        client.claim_error = RuntimeError('transfer_agent unreachable')
        trigger = make_trigger(FakeACL(client=client))

        with pytest.raises(RuntimeError):
            trigger._claim_next()  # 单轮认领失败上抛，由 _run 捕获重试


# ================= 生命周期（真实线程） =================
class TestTriggerLifecycle:
    def test_full_loop_executes_claimed_package_then_idles(self):
        client = FakeClient()
        client.claim_results = ['t-loop']
        finished = threading.Event()
        client.on_finish = lambda _tid, _state: finished.set()
        acl = FakeACL(client=client)
        trigger = make_trigger(acl, poll_interval_seconds=0.01)

        trigger.start()
        assert finished.wait(timeout=5), '触发器未在超时内完成 认领→执行→收敛'
        trigger.stop()

        assert acl.executed == ['t-loop']
        assert client.finish_calls[0]['state'] == 'executed'
        assert trigger._thread is None  # stop() 回收线程引用

    def test_stop_terminates_polling_thread(self):
        trigger = make_trigger(poll_interval_seconds=0.01)
        trigger.start()
        assert trigger._thread.is_alive()
        trigger.stop(timeout=5)
        assert trigger._thread is None  # stop() 回收线程引用
