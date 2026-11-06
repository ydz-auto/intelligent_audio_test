# -*- coding: utf-8 -*-
"""transfer_agent 领域层单元测试（INT-28）。

覆盖：
- 传输包协议实体：分片计算、TTL 判定、状态机、file_hash 校验
- 签名服务：规范串 HMAC-SHA256、验签防篡改、预共享 Token 访问控制（fail-closed）
- 区路由策略：默认矩阵（A↔C 拒绝、B→C 仅 EVAL_REQUEST）、策略文件覆盖

纯领域对象测试，不依赖 DB / OSS / 网络。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import datetime, timedelta, timezone

import pytest

from shared.models.common_enums import TransferStatus
from transfer_agent.domain.entities.transfer_package import TransferPackage
from transfer_agent.domain.errors import (
    AccessTokenInvalidError,
    FileHashMismatchError,
    InvalidPackageFieldError,
    InvalidTransferStateError,
    RouteNotAllowedError,
    SignatureInvalidError,
)
from transfer_agent.domain.services.signature_service import (
    SignatureService,
    load_tokens_from_secrets_file,
)
from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy

TOKENS = {'A_B': 'secret-ab', 'B_C': 'secret-bc'}


def make_package(**overrides):
    fields = dict(
        transfer_id='t-1', pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
        category='audios', key='task_1/case_2/audio.wav',
        file_hash='sha256:' + 'a' * 64, file_size=100, ttl_seconds=3600,
        ephemeral=False, timestamp='2026-10-08T10:00:00+08:00', signature='sig',
        chunk_size=32,
    )
    fields.update(overrides)
    return TransferPackage(**fields)


# ================= 传输包实体 =================
class TestTransferPackage:
    def test_compute_total_chunks(self):
        assert TransferPackage.compute_total_chunks(100, 32) == 4
        assert TransferPackage.compute_total_chunks(96, 32) == 3
        assert TransferPackage.compute_total_chunks(1, 32) == 1
        assert TransferPackage.compute_total_chunks(0, 32) == 0

    def test_total_chunks_from_file_size(self):
        pkg = make_package(file_size=65, chunk_size=32)
        assert pkg.total_chunks == 3

    def test_expires_at_from_ttl(self):
        pkg = make_package(ttl_seconds=600)
        assert pkg.expires_at - pkg.created_at == timedelta(seconds=600)
        assert not pkg.is_expired()
        assert pkg.is_expired(pkg.created_at + timedelta(seconds=601))

    def test_state_machine_happy_path(self):
        pkg = make_package()
        assert pkg.status == TransferStatus.CREATED.value
        pkg.mark_transferring()
        pkg.mark_completed(final_path='oss://case-result/x')
        assert pkg.status == TransferStatus.COMPLETED.value
        assert pkg.final_path == 'oss://case-result/x'

    def test_state_machine_guards(self):
        pkg = make_package()
        pkg.mark_transferring()
        pkg.mark_completed('p')
        with pytest.raises(InvalidTransferStateError):
            pkg.mark_transferring()  # COMPLETED 终态不允许再变更
        with pytest.raises(InvalidTransferStateError):
            pkg.mark_failed()
        failed = make_package()
        failed.mark_failed()
        with pytest.raises(InvalidTransferStateError):
            failed.mark_completed('p')  # FAILED 终态不允许完成
        # FAILED 包允许被 sweeper 置 EXPIRED 收尾
        failed.mark_expired()
        assert failed.status == TransferStatus.EXPIRED.value

    def test_validate_file_hash(self):
        pkg = make_package(file_hash='sha256:' + 'ab' * 32)
        pkg.validate_file_hash('AB' * 32)  # 大小写不敏感
        with pytest.raises(FileHashMismatchError):
            pkg.validate_file_hash('cd' * 32)


# ================= 路径安全不变量（审计 P1/P5）=================
class TestPackageFieldInvariants:
    def test_invalid_transfer_id_rejected(self):
        for bad in ('../evil', 'a/b', 'a\\b', 'x' * 65, ''):
            with pytest.raises(InvalidPackageFieldError):
                make_package(transfer_id=bad)

    def test_invalid_key_rejected(self):
        for bad in ('../etc/evil', 'a/../b', '/abs', 'a\\b', 'C:/x'):
            with pytest.raises(InvalidPackageFieldError):
                make_package(key=bad)

    def test_invalid_enum_raises_field_error_not_value_error(self):
        # 实体层枚举外值 → 统一 InvalidPackageFieldError（400 语义），非裸 ValueError
        for kwargs in ({'pkg_type': 'NOPE'}, {'category': 'nope'}, {'status': 'NOPE'}):
            with pytest.raises(InvalidPackageFieldError):
                make_package(**kwargs)


# ================= 签名服务（访问层 + 签名层）=================
def sign_fields(**fields):
    return SignatureService.compute_signature(TOKENS['A_B'], **fields)


class TestSignatureService:
    BASE = dict(
        transfer_id='t-1', pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
        category='audios', key='task_1/audio.wav', file_hash='sha256:' + 'a' * 64,
        file_size=100, ttl_seconds=3600, timestamp='2026-10-08T10:00:00+08:00',
    )

    def test_route_key_is_bidirectional(self):
        assert SignatureService.route_key('A', 'B') == 'A_B'
        assert SignatureService.route_key('B', 'A') == 'A_B'

    def test_sign_and_verify(self):
        svc = SignatureService(TOKENS)
        fields = dict(self.BASE, signature=sign_fields(**self.BASE))
        svc.verify_signature(fields)  # 不抛即通过

    def test_tampered_field_fails(self):
        svc = SignatureService(TOKENS)
        fields = dict(self.BASE, signature=sign_fields(**self.BASE))
        for tampered in (
            dict(fields, file_size=999),
            dict(fields, key='task_2/audio.wav'),
            dict(fields, pkg_type='EVAL_REQUEST'),
            dict(fields, ttl_seconds=60),
        ):
            with pytest.raises(SignatureInvalidError):
                svc.verify_signature(tampered)

    def test_wrong_route_secret_fails(self):
        svc = SignatureService(TOKENS)
        fields = dict(self.BASE, signature=sign_fields(**self.BASE))
        # 用 B_C 的密钥签的 A_B 路由签名（token 取错）
        fields['signature'] = SignatureService.compute_signature(TOKENS['B_C'], **self.BASE)
        with pytest.raises(SignatureInvalidError):
            svc.verify_signature(fields)

    def test_token_check_fail_closed(self):
        svc = SignatureService(TOKENS)
        svc.verify_token('A', 'B', 'secret-ab')
        with pytest.raises(AccessTokenInvalidError):
            svc.verify_token('A', 'B', 'wrong')
        with pytest.raises(AccessTokenInvalidError):
            svc.verify_token('A', 'B', '')
        # 未配置路由（A_C）一律拒绝
        with pytest.raises(AccessTokenInvalidError):
            svc.verify_token('A', 'C', 'secret-ab')

    def test_missing_token_config_rejects_signature(self):
        svc = SignatureService({})  # 无任何预共享密钥
        with pytest.raises(SignatureInvalidError):
            svc.verify_signature(dict(self.BASE, signature='x'))


class TestSecretsFile:
    def test_load_tokens_from_file(self, tmp_path):
        path = tmp_path / 'secrets_config.json'
        path.write_text(
            '{"TOKEN_A_B": "s1", "TOKEN_B_C": "s2", "OTHER": "ignored"}',
            encoding='utf-8',
        )
        assert load_tokens_from_secrets_file(str(path)) == {
            'TOKEN_A_B': 's1', 'TOKEN_B_C': 's2',
        }

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_tokens_from_secrets_file(str(tmp_path / 'nope.json')) == {}


# ================= 区路由策略（网络隔离点 + 内容层）=================
class TestZoneRoutePolicy:
    def test_default_matrix_allows(self):
        policy = ZoneRoutePolicy()
        # A↔B 双向：数据/报告/评估互传
        for pkg in ('DATA_SYNC', 'REPORT_SYNC', 'EVAL_REQUEST', 'EVAL_RESULT'):
            policy.check('A', 'B', pkg)
            policy.check('B', 'A', pkg)
        # B→C 仅评估输入；C 入口只收 EVAL_REQUEST
        policy.check('B', 'C', 'EVAL_REQUEST')
        # C→B：评估结果 + 备选方案 C 产物
        for pkg in ('EVAL_RESULT', 'C_REPORT', 'C_RESULT'):
            policy.check('C', 'B', pkg)

    def test_default_matrix_rejects(self):
        policy = ZoneRoutePolicy()
        # A↔C 物理不直连，必须经 B 中继
        with pytest.raises(RouteNotAllowedError):
            policy.check('A', 'C', 'EVAL_REQUEST')
        with pytest.raises(RouteNotAllowedError):
            policy.check('C', 'A', 'C_REPORT')
        # B→C 只放 EVAL_REQUEST
        with pytest.raises(RouteNotAllowedError):
            policy.check('B', 'C', 'DATA_SYNC')
        # C→B 不放 EVAL_REQUEST
        with pytest.raises(RouteNotAllowedError):
            policy.check('C', 'B', 'EVAL_REQUEST')

    def test_invalid_zone_and_pkg_type(self):
        policy = ZoneRoutePolicy()
        with pytest.raises(InvalidPackageFieldError):
            policy.check('A', 'D', 'DATA_SYNC')
        with pytest.raises(InvalidPackageFieldError):
            policy.check('A', 'B', 'NOT_A_PKG_TYPE')

    def test_policy_file_override(self, tmp_path):
        import json
        path = tmp_path / 'route_policy.json'
        path.write_text(json.dumps({
            'routes': [{'src': 'A', 'dst': 'C', 'pkg_types': ['DATA_SYNC']}],
        }), encoding='utf-8')
        policy = ZoneRoutePolicy(policy_file=str(path))
        policy.check('A', 'C', 'DATA_SYNC')  # 自定义矩阵生效
        with pytest.raises(RouteNotAllowedError):
            policy.check('A', 'B', 'DATA_SYNC')  # 默认矩阵被整体覆盖
