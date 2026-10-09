# -*- coding: utf-8 -*-
"""中转执行触发器契约测试（F2.3/INT-53 中枢侧生产触发）。

三层覆盖：
1. RelayExecutionService（应用层）：token fail-closed、stale_seconds 校验、
   认领/终态事件、finish 幂等拒绝；
2. TransferRecordRepository 真实实现（sqlite）：claim 行锁 CAS 资格判定与
   meta.relay 状态机 —— 幂等去重核心（同一中转包不重复执行）、失效窗崩溃恢复；
3. /internal/transfer/relay/* HTTP 契约（TestClient 真实路由栈，替身仓储）。

不依赖 OSS / Redis。
"""
import json
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi.testclient import TestClient

import transfer_agent.interfaces.api.routes as routes_module
from transfer_agent.application.services.relay_execution_service import (
    RelayExecutionService,
)
from transfer_agent.domain.entities.transfer_package import (
    RelayExecutionState,
    TransferPackage,
)
from transfer_agent.domain.errors import (
    AccessTokenInvalidError,
    InvalidPackageFieldError,
    PackageNotFoundError,
)
from transfer_agent.domain.events.transfer_events import (
    TransferRelayClaimed,
    TransferRelayCompleted,
    TransferRelayFailed,
)
from transfer_agent.domain.services.signature_service import SignatureService
from tests.unit.test_transfer_handlers import FakeRecordRepo

TOKENS = {'A_B': 'secret-ab'}
_E8 = timezone(timedelta(hours=8))


def make_package(transfer_id='relay-ut-1', *, pkg_type='EVAL_REQUEST', src_zone='A',
                 dst_zone='B', status='COMPLETED', meta=None, ttl_seconds=600,
                 created_at=None):
    return TransferPackage(
        transfer_id=transfer_id, pkg_type=pkg_type, src_zone=src_zone, dst_zone=dst_zone,
        category='transit', key=f'task_1/{transfer_id}', file_hash='sha256:' + '0' * 64,
        file_size=20, ttl_seconds=ttl_seconds, ephemeral=True,
        timestamp='2026-10-09T00:00:00+08:00', signature='sig',
        meta=meta if meta is not None else {}, chunk_size=8, status=status,
        created_at=created_at or datetime.now(_E8),
    )


class RelayCapableRecordRepo(FakeRecordRepo):
    """内存版 relay 认领/终态仓储（镜像真实仓储 meta.relay 状态机语义）。

    供应用层与 HTTP 契约测试注入；CAS 深层语义（行锁/失效窗）由本文件
    TestTransferRecordRepositoryRelayClaim 对真实实现直测。
    """

    def claim_relay_execution(self, *, dst_zone, stale_seconds, now=None):
        now = now or datetime.now(_E8)
        for pkg in sorted(self.packages.values(), key=lambda p: p.created_at):
            if pkg.pkg_type != 'EVAL_REQUEST' or pkg.dst_zone != dst_zone \
                    or pkg.status != 'COMPLETED' or pkg.is_expired(now):
                continue
            relay = dict((pkg.meta or {}).get('relay') or {})
            state = relay.get('state')
            if state in (RelayExecutionState.EXECUTED.value,
                         RelayExecutionState.FAILED.value):
                continue
            if state == RelayExecutionState.EXECUTING.value:
                claimed_at = _parse_meta_time(relay.get('claimed_at'))
                if claimed_at is not None and \
                        (now - claimed_at).total_seconds() < stale_seconds:
                    continue
            relay.update({'state': RelayExecutionState.EXECUTING.value,
                          'claimed_at': now.isoformat(),
                          'attempts': int(relay.get('attempts') or 0) + 1})
            pkg.meta = {**(pkg.meta or {}), 'relay': relay}
            return pkg
        return None

    def finish_relay_execution(self, *, transfer_id, state, error=None, now=None):
        pkg = self.packages.get(transfer_id)
        if pkg is None:
            return False
        relay = dict((pkg.meta or {}).get('relay') or {})
        if relay.get('state') != RelayExecutionState.EXECUTING.value:
            return False
        now = now or datetime.now(_E8)
        relay.update({'state': state, 'finished_at': now.isoformat(),
                      'error': error or ''})
        pkg.meta = {**(pkg.meta or {}), 'relay': relay}
        return True


def _parse_meta_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def make_service(repo, *, self_zone='B', tokens=None, events=None):
    return RelayExecutionService(
        record_repo=repo, signature_service=SignatureService(tokens or TOKENS),
        self_zone=self_zone, event_sink=(events.append if events is not None else None))


# ================= 1. 应用层：RelayExecutionService =================
class TestRelayExecutionServiceClaim:
    def test_claim_requires_token(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package())
        svc = make_service(repo)
        with pytest.raises(AccessTokenInvalidError):
            svc.claim_next(token='', stale_seconds=1800)

    def test_claim_rejects_foreign_token(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package())
        svc = make_service(repo)
        with pytest.raises(AccessTokenInvalidError):
            svc.claim_next(token='not-a-route-token', stale_seconds=1800)

    def test_claim_rejects_non_positive_stale_seconds(self):
        svc = make_service(RelayCapableRecordRepo())
        with pytest.raises(InvalidPackageFieldError):
            svc.claim_next(token='secret-ab', stale_seconds=0)

    def test_claim_returns_package_and_emits_claimed_event(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package('relay-ut-claim'))
        events = []
        svc = make_service(repo, events=events)

        package = svc.claim_next(token='secret-ab', stale_seconds=1800)

        assert package is not None and package.transfer_id == 'relay-ut-claim'
        assert package.meta['relay']['state'] == 'executing'
        assert package.meta['relay']['attempts'] == 1
        assert [type(e) for e in events] == [TransferRelayClaimed]
        assert events[0].transfer_id == 'relay-ut-claim'
        assert (events[0].src_zone, events[0].dst_zone) == ('A', 'B')

    def test_claim_no_candidate_returns_none_without_event(self):
        events = []
        svc = make_service(RelayCapableRecordRepo(), events=events)
        assert svc.claim_next(token='secret-ab', stale_seconds=1800) is None
        assert events == []

    def test_claim_scoped_to_self_zone(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package('relay-ut-other-zone', dst_zone='C'))
        svc = make_service(repo, self_zone='B')
        assert svc.claim_next(token='secret-ab', stale_seconds=1800) is None


class TestRelayExecutionServiceFinish:
    def test_finish_executed_emits_completed_event(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package('relay-ut-fin'))
        svc = make_service(repo, events=[])
        svc.claim_next(token='secret-ab', stale_seconds=1800)
        events = []
        svc._event_sink = events.append

        finished = svc.finish(transfer_id='relay-ut-fin', token='secret-ab',
                              state='executed')

        assert finished is True
        assert [type(e) for e in events] == [TransferRelayCompleted]
        assert repo.packages['relay-ut-fin'].meta['relay']['state'] == 'executed'

    def test_finish_failed_emits_failed_event_with_reason(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package('relay-ut-fail'))
        svc = make_service(repo)
        svc.claim_next(token='secret-ab', stale_seconds=1800)
        events = []
        svc._event_sink = events.append

        finished = svc.finish(transfer_id='relay-ut-fail', token='secret-ab',
                              state='failed', error='boom-unpack')

        assert finished is True
        assert [type(e) for e in events] == [TransferRelayFailed]
        assert events[0].reason == 'boom-unpack'

    def test_finish_rejects_executing_and_unknown_state(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package('relay-ut-state'))
        svc = make_service(repo)
        for bad in ('executing', 'nonsense'):
            with pytest.raises(InvalidPackageFieldError):
                svc.finish(transfer_id='relay-ut-state', token='secret-ab',
                           state=bad)

    def test_finish_unknown_package_raises_not_found(self):
        svc = make_service(RelayCapableRecordRepo())
        with pytest.raises(PackageNotFoundError):
            svc.finish(transfer_id='relay-ut-missing', token='secret-ab',
                       state='executed')

    def test_finish_rejects_wrong_route_token(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package('relay-ut-token'))
        svc = make_service(repo)
        svc.claim_next(token='secret-ab', stale_seconds=1800)
        with pytest.raises(AccessTokenInvalidError):
            svc.finish(transfer_id='relay-ut-token', token='wrong-token',
                       state='executed')

    def test_finish_double_convergence_idempotent_rejection(self):
        repo = RelayCapableRecordRepo()
        repo.add(make_package('relay-ut-dup'))
        svc = make_service(repo)
        svc.claim_next(token='secret-ab', stale_seconds=1800)
        assert svc.finish(transfer_id='relay-ut-dup', token='secret-ab',
                          state='executed') is True
        assert svc.finish(transfer_id='relay-ut-dup', token='secret-ab',
                          state='executed') is False
        assert svc.finish(transfer_id='relay-ut-dup', token='secret-ab',
                          state='failed') is False


# ================= 2. 真实仓储：claim CAS 与 meta.relay 状态机 =================
@pytest.fixture
def real_repo_db():
    from shared.models.database import Base, get_engine, get_db_session, init_db, \
        remove_db_session
    from transfer_agent.infrastructure.persistence.models import TransferRecord
    from transfer_agent.infrastructure.persistence.transfer_repository import (
        TransferRecordRepository,
    )
    remove_db_session()
    init_db(pool_size=3)
    Base.metadata.create_all(get_engine())
    yield TransferRecordRepository()
    session = get_db_session()
    try:
        session.query(TransferRecord).filter(
            TransferRecord.transfer_id.like('relay-ut-%')).delete(
            synchronize_session=False)
        session.commit()
    finally:
        remove_db_session()


def seed_record(transfer_id, *, status='COMPLETED', pkg_type='EVAL_REQUEST',
                dst_zone='B', meta=None, ttl_seconds=600, created_at=None):
    from shared.models.database import get_db_session
    from transfer_agent.infrastructure.persistence.models import TransferRecord
    session = get_db_session()
    po = TransferRecord(
        transfer_id=transfer_id, pkg_type=pkg_type, src_zone='A', dst_zone=dst_zone,
        category='transit', key=f'task_1/{transfer_id}',
        file_hash='sha256:' + '0' * 64, file_size=20, chunk_size=8,
        meta=json.dumps(meta) if meta else None, ttl_seconds=ttl_seconds,
        ephemeral=True, timestamp='2026-10-09T00:00:00+08:00', signature='sig',
        status=status, final_path='/tmp/transit/final/task_1/x',
        created_at=created_at or datetime.now(_E8).replace(tzinfo=None),
    )
    session.add(po)
    session.commit()
    return po


class TestTransferRecordRepositoryRelayClaim:
    def test_claim_eligible_package_writes_executing_meta(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-cas1')
        now = datetime(2026, 1, 1, 12, 0, 0)

        package = repo.claim_relay_execution(dst_zone='B', stale_seconds=1800, now=now)

        assert package is not None and package.transfer_id == 'relay-ut-cas1'
        assert package.meta['relay']['state'] == 'executing'
        assert package.meta['relay']['attempts'] == 1
        assert package.meta['relay']['claimed_at'] == now.isoformat()

    def test_claim_skips_non_eligible_records(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-wrong-type', pkg_type='EVAL_RESULT')
        seed_record('relay-ut-wrong-dst', dst_zone='C')
        seed_record('relay-ut-wrong-status', status='TRANSFERRING')

        assert repo.claim_relay_execution(
            dst_zone='B', stale_seconds=1800,
            now=datetime(2026, 1, 1)) is None

    def test_claim_skips_expired_record(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-expired', ttl_seconds=600,
                    created_at=datetime(2025, 12, 31, 0, 0, 0))

        # now 晚于 created_at + ttl：过期包不认领（交由既有过期清理收敛）
        assert repo.claim_relay_execution(
            dst_zone='B', stale_seconds=1800,
            now=datetime(2026, 1, 1)) is None

    def test_double_claim_within_stale_window_blocked(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-double')
        now = datetime(2026, 1, 1, 12, 0, 0)

        first = repo.claim_relay_execution(dst_zone='B', stale_seconds=1800, now=now)
        second = repo.claim_relay_execution(
            dst_zone='B', stale_seconds=1800,
            now=now + timedelta(seconds=60))

        assert first is not None
        assert second is None  # executing 且未超失效窗：不重复认领

    def test_stale_claim_recovered_after_window(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-stale')
        now = datetime(2026, 1, 1, 12, 0, 0)

        first = repo.claim_relay_execution(dst_zone='B', stale_seconds=1800, now=now)
        recovered = repo.claim_relay_execution(
            dst_zone='B', stale_seconds=1800,
            now=now + timedelta(seconds=1801))

        assert first is not None and recovered is not None
        assert recovered.transfer_id == 'relay-ut-stale'
        assert recovered.meta['relay']['attempts'] == 2  # 崩溃恢复重认领

    def test_terminal_states_not_claimable(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-done',
                    meta={'relay': {'state': 'executed', 'attempts': 1}})
        seed_record('relay-ut-dead',
                    meta={'relay': {'state': 'failed', 'attempts': 1}})

        assert repo.claim_relay_execution(
            dst_zone='B', stale_seconds=1800,
            now=datetime(2026, 1, 1)) is None

    def test_finish_writes_terminal_meta(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-fin')
        now = datetime(2026, 1, 1, 12, 0, 0)
        repo.claim_relay_execution(dst_zone='B', stale_seconds=1800, now=now)

        assert repo.finish_relay_execution(
            transfer_id='relay-ut-fin', state='executed', now=now) is True

        package = repo.find_by_transfer_id('relay-ut-fin')
        assert package.meta['relay']['state'] == 'executed'
        assert package.meta['relay']['finished_at'] == now.isoformat()
        assert package.meta['relay']['error'] == ''

    def test_finish_requires_claimed_executing_state(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-unclaimed')

        # 未认领：不允许收敛
        assert repo.finish_relay_execution(
            transfer_id='relay-ut-unclaimed', state='executed') is False

    def test_finish_double_convergence_rejected(self, real_repo_db):
        repo = real_repo_db
        seed_record('relay-ut-twice')
        now = datetime(2026, 1, 1, 12, 0, 0)
        repo.claim_relay_execution(dst_zone='B', stale_seconds=1800, now=now)

        assert repo.finish_relay_execution(
            transfer_id='relay-ut-twice', state='executed', now=now) is True
        assert repo.finish_relay_execution(
            transfer_id='relay-ut-twice', state='failed',
            error='second', now=now) is False

    def test_finish_unknown_transfer_returns_false(self, real_repo_db):
        assert real_repo_db.finish_relay_execution(
            transfer_id='relay-ut-nope', state='executed') is False


# ================= 3. HTTP 契约：/internal/transfer/relay/* =================
@pytest.fixture
def relay_client(monkeypatch):
    repo = RelayCapableRecordRepo()
    relay = make_service(repo)
    monkeypatch.setattr(routes_module, '_relay_service', relay)

    import transfer_agent.app as app_module
    return TestClient(app_module.create_app()), repo


class TestRelayHttpContract:
    def test_claim_over_http_returns_transfer_id_then_none(self, relay_client):
        client, repo = relay_client
        repo.add(make_package('relay-ut-http1'))
        headers = {'X-Transfer-Token': 'secret-ab'}

        r1 = client.post('/internal/transfer/relay/claim', json={'stale_seconds': 1800},
                         headers=headers)
        r2 = client.post('/internal/transfer/relay/claim', json={'stale_seconds': 1800},
                         headers=headers)

        assert r1.status_code == 200 and r1.json()['success'] is True
        assert r1.json()['data']['transfer_id'] == 'relay-ut-http1'
        # 幂等去重：同一中转包不重复认领（第二次无候选）
        assert r2.status_code == 200 and r2.json()['data']['transfer_id'] is None

    def test_claim_no_candidate_over_http(self, relay_client):
        client, _repo = relay_client
        r = client.post('/internal/transfer/relay/claim', json={'stale_seconds': 1800},
                        headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 200
        assert r.json() == {'success': True, 'data': {'transfer_id': None}}

    def test_claim_rejects_missing_token(self, relay_client):
        client, _repo = relay_client
        r = client.post('/internal/transfer/relay/claim', json={'stale_seconds': 1800})
        assert r.status_code == 401
        assert r.json()['detail']['code'] == 'TRANSFER_ACCESS_TOKEN_INVALID'

    def test_claim_rejects_non_positive_stale_seconds(self, relay_client):
        client, _repo = relay_client
        r = client.post('/internal/transfer/relay/claim', json={'stale_seconds': 0},
                        headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 400
        assert r.json()['detail']['code'] == 'TRANSFER_PACKAGE_FIELD_INVALID'

    def test_finish_over_http_then_idempotent_rejection(self, relay_client):
        client, repo = relay_client
        repo.add(make_package('relay-ut-httpfin'))
        headers = {'X-Transfer-Token': 'secret-ab'}
        client.post('/internal/transfer/relay/claim', json={'stale_seconds': 1800},
                    headers=headers)

        r1 = client.post(f'/internal/transfer/relay/relay-ut-httpfin/finish',
                         json={'state': 'executed'}, headers=headers)
        r2 = client.post(f'/internal/transfer/relay/relay-ut-httpfin/finish',
                         json={'state': 'executed'}, headers=headers)

        assert r1.status_code == 200 and r1.json()['data']['finished'] is True
        # 幂等拒绝：重复收敛返回 finished=False（流水终态不悬挂、不覆盖）
        assert r2.status_code == 200 and r2.json()['data']['finished'] is False
        assert repo.packages['relay-ut-httpfin'].meta['relay']['state'] == 'executed'

    def test_finish_unknown_package_returns_404(self, relay_client):
        client, _repo = relay_client
        r = client.post('/internal/transfer/relay/relay-ut-missing/finish',
                        json={'state': 'executed'},
                        headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 404
        assert r.json()['detail']['code'] == 'TRANSFER_PACKAGE_NOT_FOUND'

    def test_finish_invalid_state_returns_400(self, relay_client):
        client, repo = relay_client
        repo.add(make_package('relay-ut-badstate'))
        r = client.post('/internal/transfer/relay/relay-ut-badstate/finish',
                        json={'state': 'nonsense'},
                        headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 400
        assert r.json()['detail']['code'] == 'TRANSFER_PACKAGE_FIELD_INVALID'
