# -*- coding: utf-8 -*-
"""transfer_agent 应用层全链路单元测试（INT-28）。

以替身仓储/存储/事件汇驱动 TransferCommandHandler / TransferQueryHandler，
覆盖验收标准 2/3 的全链路语义：
- 传输包创建（含幂等去重、重复冲突）
- 分片上传（checksum 校验、越界/大小约束、幂等去重、同位冲突）
- 断点续传（查询已收分片清单）
- 传输完成（合并 + file_hash 校验、失败终态清理）
- TTL 过期清理（未完成包 / ephemeral 完成包回收，持久完成包保留）
- 签名校验失败与 TTL 过期的明确错误语义

不依赖 DB / OSS / 网络。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import datetime, timedelta, timezone

import pytest

from shared.models.common_enums import TransferStatus
from transfer_agent.application.commands.transfer_commands import (
    CompleteTransferCommand,
    CreateTransferCommand,
    ExpirePackagesCommand,
    UploadChunkCommand,
)
from transfer_agent.application.handlers.transfer_handlers import (
    TransferCommandHandler,
    TransferQueryHandler,
)
from transfer_agent.application.queries.transfer_queries import (
    GetTransferQuery,
    GetTransferStatusQuery,
)
from transfer_agent.domain.entities.transfer_package import (
    TransferChunkRecord,
    TransferPackage,
)
from transfer_agent.domain.errors import (
    AccessTokenInvalidError,
    ChunkChecksumMismatchError,
    ChunkIndexOutOfRangeError,
    ChunkSizeInvalidError,
    DuplicateTransferConflictError,
    FileHashMismatchError,
    InvalidPackageFieldError,
    MissingChunksError,
    PackageExpiredError,
    PackageNotFoundError,
    RouteNotAllowedError,
    SignatureInvalidError,
)
from transfer_agent.domain.services.signature_service import SignatureService
from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy

TOKENS = {'A_B': 'secret-ab', 'B_C': 'secret-bc'}
CHUNK = 8  # 测试用 8 字节分片


# ================= 替身 =================
STANDARD_PAYLOAD = b'12345678901234567890'  # 20B = 8+8+4 三片
import hashlib as _hashlib


def _payload_hash(payload: bytes) -> str:
    return 'sha256:' + _hashlib.sha256(payload).hexdigest()
class FakeRecordRepo:
    def __init__(self):
        self.packages = {}

    def find_by_transfer_id(self, transfer_id):
        return self.packages.get(transfer_id)

    def add(self, package):
        self.packages[package.transfer_id] = package

    def save(self, package):
        self.packages[package.transfer_id] = package

    def list_expired(self, now, limit=100):
        expired = []
        for pkg in self.packages.values():
            if pkg.status in ('CREATED', 'TRANSFERRING', 'FAILED') or (
                pkg.status in ('COMPLETED', 'DELIVERED') and pkg.ephemeral
            ):
                if pkg.is_expired(now):
                    expired.append(pkg)
            if len(expired) >= limit:
                break
        return expired


class FakeChunkRepo:
    def __init__(self):
        self.chunks = {}

    def list_records(self, transfer_id):
        return [
            self.chunks[(transfer_id, i)]
            for (tid, i) in sorted(self.chunks)
            if tid == transfer_id
        ]

    def find(self, transfer_id, chunk_index):
        return self.chunks.get((transfer_id, chunk_index))

    def add(self, record):
        self.chunks[(record.transfer_id, record.chunk_index)] = record

    def delete_all(self, transfer_id):
        for key in [k for k in self.chunks if k[0] == transfer_id]:
            del self.chunks[key]


class FakeStorage:
    def __init__(self):
        self.chunk_files = {}
        self.final_files = {}
        self.deleted_chunks = set()
        self.deleted_final = []

    def save_chunk(self, transfer_id, chunk_index, data):
        self.chunk_files[(transfer_id, chunk_index)] = data

    def chunk_exists(self, transfer_id, chunk_index):
        return (transfer_id, chunk_index) in self.chunk_files

    def delete_chunks(self, transfer_id, total_chunks):
        for i in range(total_chunks):
            self.chunk_files.pop((transfer_id, i), None)
            self.deleted_chunks.add((transfer_id, i))

    def merge_chunks(self, transfer_id, total_chunks):
        import hashlib
        data = b''.join(
            self.chunk_files[(transfer_id, i)] for i in range(total_chunks)
        )
        path = f'oss://transit/{transfer_id}/merged.pkg'
        self.final_files[path] = data
        return path, hashlib.sha256(data).hexdigest()

    def promote_file(self, staged_path, dest_category, dest_key):
        data = self.final_files.pop(staged_path)
        path = f'oss://{dest_category}/{dest_key}'
        self.final_files[path] = data
        return path

    def read_file(self, path):
        if path not in self.final_files:
            raise FileNotFoundError(path)
        return self.final_files[path]

    def delete_transit_file(self, path):
        self.final_files.pop(path, None)
        self.deleted_final.append(path)


@pytest.fixture
def deps():
    record_repo, chunk_repo, storage = FakeRecordRepo(), FakeChunkRepo(), FakeStorage()
    events = []
    handler = TransferCommandHandler(
        record_repo=record_repo, chunk_repo=chunk_repo, storage=storage,
        signature_service=SignatureService(TOKENS),
        route_policy=ZoneRoutePolicy(),
        event_sink=events.append,
        ttl_bounds=(60, 7 * 86400),
        default_chunk_size=CHUNK,
    )
    query = TransferQueryHandler(
        record_repo=record_repo, chunk_repo=chunk_repo,
        signature_service=SignatureService(TOKENS),
    )
    return {
        'handler': handler, 'query': query, 'record_repo': record_repo,
        'chunk_repo': chunk_repo, 'storage': storage, 'events': events,
    }


def signed_fields(**overrides):
    fields = dict(
        transfer_id='t-1', pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
        category='audios', key='task_1/case_2/audio.wav',
        file_hash=_payload_hash(STANDARD_PAYLOAD), file_size=len(STANDARD_PAYLOAD),
        ttl_seconds=3600,
        timestamp='2026-10-08T10:00:00+08:00',
    )
    fields.update(overrides)
    fields['signature'] = SignatureService.compute_signature(TOKENS['A_B'], **fields)
    return fields


def make_create_cmd(**overrides):
    fields = signed_fields(**overrides)
    meta = fields.pop('meta', {})
    token = fields.pop('token', 'secret-ab')
    return CreateTransferCommand(token=token, meta=meta, **fields)


def upload_all(handler, transfer_id, payload: bytes = None, token='secret-ab'):
    payload = STANDARD_PAYLOAD if payload is None else payload
    for i in range(0, len(payload), CHUNK):
        block = payload[i:i + CHUNK]
        handler.upload_chunk(UploadChunkCommand(
            transfer_id=transfer_id,
            chunk_index=i // CHUNK,
            data=block,
            checksum=_hashlib.sha256(block).hexdigest(),
            token=token,
        ))


# ================= 传输包创建 =================
class TestCreateTransfer:
    def test_create_happy_path(self, deps):
        result = deps['handler'].create_transfer(make_create_cmd())
        assert result['dedup'] is False
        assert result['status'] == TransferStatus.CREATED.value
        assert result['total_chunks'] == 3  # 20B / 8B = 3 片
        assert result['transfer_id'] in deps['record_repo'].packages
        assert deps['events'][-1].__class__.__name__ == 'TransferCreated'

    def test_create_idempotent_dedup(self, deps):
        deps['handler'].create_transfer(make_create_cmd())
        again = deps['handler'].create_transfer(make_create_cmd())
        assert again['dedup'] is True
        assert again['transfer_id'] == 't-1'
        assert len(deps['record_repo'].packages) == 1

    def test_create_duplicate_conflict_on_hash_mismatch(self, deps):
        deps['handler'].create_transfer(make_create_cmd())
        with pytest.raises(DuplicateTransferConflictError):
            deps['handler'].create_transfer(make_create_cmd(file_hash='sha256:' + 'b' * 64))

    def test_create_rejects_without_token(self, deps):
        with pytest.raises(AccessTokenInvalidError):
            deps['handler'].create_transfer(make_create_cmd(token=''))

    def test_create_rejects_tampered_signature(self, deps):
        cmd = make_create_cmd()
        cmd.signature = '0' * 64
        with pytest.raises(SignatureInvalidError):
            deps['handler'].create_transfer(cmd)

    def test_create_rejects_disallowed_route(self, deps):
        fields = signed_fields(src_zone='A', dst_zone='C')
        fields['signature'] = SignatureService.compute_signature(TOKENS['A_B'], **fields)
        with pytest.raises(RouteNotAllowedError) as ei:
            deps['handler'].create_transfer(CreateTransferCommand(
                token='secret-ab', **fields,
            ))
        assert ei.value.code == 'TRANSFER_ROUTE_NOT_ALLOWED'

    def test_create_rejects_ttl_out_of_bounds(self, deps):
        with pytest.raises(InvalidPackageFieldError):
            deps['handler'].create_transfer(make_create_cmd(ttl_seconds=10))  # < min 60
        with pytest.raises(InvalidPackageFieldError):
            deps['handler'].create_transfer(make_create_cmd(ttl_seconds=99999999))

    def test_create_rejects_missing_required_fields(self, deps):
        with pytest.raises(InvalidPackageFieldError):
            deps['handler'].create_transfer(make_create_cmd(transfer_id=''))

    def test_create_rejects_transfer_id_path_traversal(self, deps):
        # transfer_id 进入存储路径（transit/{transfer_id}/chunks/...），白名单拒绝穿越形态
        for bad in ('../evil', 'a/b', 'a\\b', 'x' * 65, '', '点.id', 'id;drop'):
            with pytest.raises(InvalidPackageFieldError):
                deps['handler'].create_transfer(make_create_cmd(transfer_id=bad))

    def test_create_rejects_key_escape_forms(self, deps):
        # key 拼接为 {root}/{category}/{key}，拒绝 .. 段 / 绝对路径 / 反斜杠 / 冒号
        for bad in ('../../etc/evil', 'a/../b', '/abs/path.wav', 'a\\..\\b', 'C:/evil', 'a/../..'):
            with pytest.raises(InvalidPackageFieldError):
                deps['handler'].create_transfer(make_create_cmd(key=bad))

    def test_create_rejects_unknown_category(self, deps):
        # 非法 category → 400 语义（InvalidPackageFieldError），而非实体层裸 ValueError→500
        with pytest.raises(InvalidPackageFieldError) as ei:
            deps['handler'].create_transfer(make_create_cmd(category='no-such-category'))
        assert ei.value.code == 'TRANSFER_PACKAGE_FIELD_INVALID'

    def test_create_rejects_chunk_size_over_receiver_limit(self, deps):
        # 分片上限 = 接收端 TRANSFER_CHUNK_SIZE（依赖注入 max_chunk_bytes 模拟小上限）
        deps['handler']._max_chunk_bytes = 16
        with pytest.raises(InvalidPackageFieldError):
            deps['handler'].create_transfer(make_create_cmd(chunk_size=17))


# ================= 分片上传 / 断点续传 =================
class TestUploadChunk:
    def _create(self, deps, **overrides):
        return deps['handler'].create_transfer(make_create_cmd(**overrides))

    def test_upload_marks_transferring(self, deps):
        self._create(deps)
        import hashlib
        result = deps['handler'].upload_chunk(UploadChunkCommand(
            transfer_id='t-1', chunk_index=0, data=b'12345678',
            checksum=hashlib.sha256(b'12345678').hexdigest(), token='secret-ab',
        ))
        assert result['dedup'] is False
        assert result['received_chunks'] == [0]
        assert deps['record_repo'].packages['t-1'].status == TransferStatus.TRANSFERRING.value

    def test_upload_dedup_same_checksum(self, deps):
        self._create(deps)
        import hashlib
        cmd = UploadChunkCommand(
            transfer_id='t-1', chunk_index=0, data=b'12345678',
            checksum=hashlib.sha256(b'12345678').hexdigest(), token='secret-ab',
        )
        deps['handler'].upload_chunk(cmd)
        result = deps['handler'].upload_chunk(cmd)  # 重复上传幂等
        assert result['dedup'] is True
        assert result['received_chunks'] == [0]

    def test_upload_conflict_same_index_different_content(self, deps):
        self._create(deps)
        import hashlib
        deps['handler'].upload_chunk(UploadChunkCommand(
            transfer_id='t-1', chunk_index=0, data=b'12345678',
            checksum=hashlib.sha256(b'12345678').hexdigest(), token='secret-ab',
        ))
        with pytest.raises(ChunkChecksumMismatchError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='t-1', chunk_index=0, data=b'87654321',
                checksum=hashlib.sha256(b'87654321').hexdigest(), token='secret-ab',
            ))

    def test_upload_rejects_checksum_mismatch(self, deps):
        self._create(deps)
        with pytest.raises(ChunkChecksumMismatchError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='t-1', chunk_index=0, data=b'12345678',
                checksum='deadbeef', token='secret-ab',
            ))

    def test_upload_rejects_out_of_range_index(self, deps):
        self._create(deps)
        with pytest.raises(ChunkIndexOutOfRangeError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='t-1', chunk_index=99, data=b'12345678',
                checksum='x', token='secret-ab',
            ))

    def test_upload_rejects_oversize_and_partial_non_final(self, deps):
        self._create(deps)
        import hashlib
        with pytest.raises(ChunkSizeInvalidError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='t-1', chunk_index=0, data=b'x' * 9,
                checksum=hashlib.sha256(b'x' * 9).hexdigest(), token='secret-ab',
            ))
        # 非末片必须满块
        with pytest.raises(ChunkSizeInvalidError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='t-1', chunk_index=0, data=b'short',
                checksum=hashlib.sha256(b'short').hexdigest(), token='secret-ab',
            ))

    def test_upload_rejects_unknown_transfer(self, deps):
        with pytest.raises(PackageNotFoundError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='ghost', chunk_index=0, data=b'x', checksum='x',
                token='secret-ab',
            ))

    def test_upload_rejects_wrong_token(self, deps):
        self._create(deps)
        with pytest.raises(AccessTokenInvalidError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='t-1', chunk_index=0, data=b'12345678',
                checksum='x', token='wrong-token',
            ))


# ================= 传输完成 / 内容校验 =================
class TestCompleteTransfer:
    def _create_and_upload(self, deps, payload=b'12345678901234567890', **overrides):
        deps['handler'].create_transfer(make_create_cmd(**overrides))
        upload_all(deps['handler'], 't-1', payload)
        return deps['handler'].complete_transfer(CompleteTransferCommand(
            transfer_id='t-1', token='secret-ab',
        ))

    def test_complete_happy_path(self, deps):
        result = self._create_and_upload(deps)
        assert result['status'] == TransferStatus.COMPLETED.value
        assert result['final_path'] == 'oss://audios/task_1/case_2/audio.wav'
        # 分片记录与分片文件已回收
        assert deps['chunk_repo'].list_records('t-1') == []
        assert not deps['storage'].chunk_files
        assert deps['events'][-1].__class__.__name__ == 'TransferCompleted'

    def test_complete_idempotent(self, deps):
        first = self._create_and_upload(deps)
        again = deps['handler'].complete_transfer(CompleteTransferCommand(
            transfer_id='t-1', token='secret-ab',
        ))
        assert again['status'] == first['status'] == TransferStatus.COMPLETED.value

    def test_complete_rejects_missing_chunks(self, deps):
        deps['handler'].create_transfer(make_create_cmd())
        import hashlib
        deps['handler'].upload_chunk(UploadChunkCommand(  # 只传 1/3 片
            transfer_id='t-1', chunk_index=0, data=b'12345678',
            checksum=hashlib.sha256(b'12345678').hexdigest(), token='secret-ab',
        ))
        with pytest.raises(MissingChunksError):
            deps['handler'].complete_transfer(CompleteTransferCommand(
                transfer_id='t-1', token='secret-ab',
            ))

    def test_complete_hash_mismatch_fails_and_cleans(self, deps):
        # 声明 hash 与实际内容不符（分片各自 checksum 正确）
        deps['handler'].create_transfer(make_create_cmd(
            file_hash='sha256:' + 'f' * 64,
        ))
        upload_all(deps['handler'], 't-1', b'12345678901234567890')
        with pytest.raises(FileHashMismatchError):
            deps['handler'].complete_transfer(CompleteTransferCommand(
                transfer_id='t-1', token='secret-ab',
            ))
        pkg = deps['record_repo'].packages['t-1']
        assert pkg.status == TransferStatus.FAILED.value
        assert deps['chunk_repo'].list_records('t-1') == []
        assert not deps['storage'].chunk_files

    def test_complete_hash_mismatch_never_touches_final_bucket(self, deps):
        # P2 回归：合并先落 transit 暂存，验 hash 失败时终桶同 key 原有对象不受影响
        original = b'ORIGINAL-OBJECT'
        deps['storage'].final_files['oss://audios/task_1/case_2/audio.wav'] = original
        deps['handler'].create_transfer(make_create_cmd(
            file_hash='sha256:' + 'f' * 64,
        ))
        upload_all(deps['handler'], 't-1', b'12345678901234567890')
        with pytest.raises(FileHashMismatchError):
            deps['handler'].complete_transfer(CompleteTransferCommand(
                transfer_id='t-1', token='secret-ab',
            ))
        assert deps['storage'].final_files['oss://audios/task_1/case_2/audio.wav'] == original
        # 暂存合并产物已回收，终桶从未出现暂存路径
        assert 'oss://transit/t-1/merged.pkg' not in deps['storage'].final_files
        assert 'oss://transit/t-1/merged.pkg' in deps['storage'].deleted_final

    def test_complete_merges_to_transit_then_promotes(self, deps):
        # P2 时序：先暂存（transit/t-1/merged.pkg），验签通过后提升到终桶（暂存消失）
        result = self._create_and_upload(deps)
        assert result['final_path'] == 'oss://audios/task_1/case_2/audio.wav'
        assert 'oss://transit/t-1/merged.pkg' not in deps['storage'].final_files
        assert deps['storage'].final_files[
            'oss://audios/task_1/case_2/audio.wav'] == STANDARD_PAYLOAD

    def test_complete_ephemeral_goes_to_transit(self, deps):
        result = self._create_and_upload(deps, ephemeral=True)
        assert result['final_path'].startswith('oss://transit/t-1/')


# ================= TTL 过期清理 =================
class TestExpiry:
    def _create(self, deps, **overrides):
        cmd = make_create_cmd(**overrides)
        deps['handler'].create_transfer(cmd)
        return deps['record_repo'].packages[cmd.transfer_id]

    def test_expire_unfinished_package(self, deps):
        pkg = self._create(deps, ttl_seconds=60)
        upload_all(deps['handler'], 't-1', b'12345678')  # 部分分片落中转存储
        # 回溯创建时间越过 TTL
        pkg.created_at = datetime.now(timezone(timedelta(hours=8))) - timedelta(seconds=120)
        pkg.expires_at = pkg.created_at + timedelta(seconds=60)
        result = deps['handler'].expire_packages(ExpirePackagesCommand())
        assert result['expired'] == 1
        assert pkg.status == TransferStatus.EXPIRED.value
        assert not deps['storage'].chunk_files  # 分片回收
        # 过期后再上传 → 明确 TTL 错误语义（验收标准 3）
        import hashlib
        with pytest.raises(PackageExpiredError):
            deps['handler'].upload_chunk(UploadChunkCommand(
                transfer_id='t-1', chunk_index=1, data=b'87654321',
                checksum=hashlib.sha256(b'87654321').hexdigest(), token='secret-ab',
            ))

    def test_expire_completed_ephemeral_but_keep_persistent(self, deps):
        ephemeral_pkg = self._create(deps, transfer_id='t-e', ttl_seconds=60, ephemeral=True)
        deps['handler'].create_transfer(make_create_cmd(transfer_id='t-p', ttl_seconds=60))
        upload_all(deps['handler'], 't-e')
        upload_all(deps['handler'], 't-p')
        deps['handler'].complete_transfer(CompleteTransferCommand(transfer_id='t-e', token='secret-ab'))
        deps['handler'].complete_transfer(CompleteTransferCommand(transfer_id='t-p', token='secret-ab'))
        # 推进时间越过 TTL
        future = datetime.now(timezone(timedelta(hours=8))) + timedelta(seconds=120)
        for pkg in deps['record_repo'].packages.values():
            pkg.expires_at = pkg.created_at + timedelta(seconds=60)
        result = deps['handler'].expire_packages(ExpirePackagesCommand(now=future))
        assert set(result['transfer_ids']) == {'t-e'}  # 仅 ephemeral 完成包回收
        assert ephemeral_pkg.status == TransferStatus.EXPIRED.value
        assert deps['record_repo'].packages['t-p'].status == TransferStatus.COMPLETED.value

    def test_sweeper_run_once(self, deps):
        from transfer_agent.application.services.expiry_cleanup_service import (
            ExpiryCleanupService,
        )
        pkg = self._create(deps, transfer_id='t-x', ttl_seconds=60)
        pkg.created_at = datetime.now(timezone(timedelta(hours=8))) - timedelta(seconds=120)
        pkg.expires_at = pkg.created_at + timedelta(seconds=60)
        sweeper = ExpiryCleanupService(deps['handler'], interval_seconds=1)
        result = sweeper.run_once()
        assert result['expired'] == 1


# ================= 查询侧（CQRS 读）=================
class TestQueries:
    def test_status_lists_received_chunks_for_resume(self, deps):
        deps['handler'].create_transfer(make_create_cmd())
        upload_all(deps['handler'], 't-1', b'12345678' * 2)  # 2/3 片（满块）
        view = deps['query'].get_transfer_status(GetTransferStatusQuery(
            transfer_id='t-1', token='secret-ab',
        ))
        assert view['received_chunks'] == [0, 1]  # 断点续传依据
        assert view['total_chunks'] == 3

    def test_status_rejects_wrong_token(self, deps):
        deps['handler'].create_transfer(make_create_cmd())
        with pytest.raises(AccessTokenInvalidError):
            deps['query'].get_transfer_status(GetTransferStatusQuery(
                transfer_id='t-1', token='nope',
            ))

    def test_get_transfer_audit_view(self, deps):
        deps['handler'].create_transfer(make_create_cmd(meta={'task_id': 'task_1'}))
        view = deps['query'].get_transfer(GetTransferQuery(
            transfer_id='t-1', token='secret-ab',
        ))
        assert view['meta'] == {'task_id': 'task_1'}
        assert view['pkg_type'] == 'DATA_SYNC'

    def test_query_unknown_transfer(self, deps):
        with pytest.raises(PackageNotFoundError):
            deps['query'].get_transfer_status(GetTransferStatusQuery(
                transfer_id='ghost', token='secret-ab',
            ))
