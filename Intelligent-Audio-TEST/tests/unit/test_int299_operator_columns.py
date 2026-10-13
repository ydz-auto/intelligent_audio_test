# -*- coding: utf-8 -*-
"""INT-299 专项：CUD 操作人列补齐（audio/device/playback/algorithm 四域）。

背景：INT-141 只覆盖 task/testcase/report 三域的操作人三列；本卡把
audio_service / device_service（含 playback）/ algorithm_service 的
CUD 写入点补齐（created_by_user_id / updated_by_user_id / deleted_by_user_id）。

覆盖（按域 × 动作）：
- audio：create（create_audio 直填 created_by）/ update / delete（单个+批量）
- device：create / update / delete（软删盖 deleted_at + deleted_by）
- playback：create / update / delete（is_deleted 标志 + deleted_by）
- algorithm：分组 add/save/soft_delete；定义 add/save/soft_delete
- 无上下文（AUTH_MODE=off 等价）：三列保持 NULL，不硬编码 0 充当真实用户

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int141 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id, get_current_user_id
from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session, utc8now,
)


# ---------------- 工具 ----------------

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from audio_service.infrastructure.persistence.models import (
            Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation,
        )
        from device_service.infrastructure.persistence.models import (
            Device, PlaybackDevice,
        )
        from algorithm_service.infrastructure.persistence.models import (
            AlgorithmGroup, AlgorithmDefinition,
        )
        _TABLES = [t.__table__ for t in (
            Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation,
            Device, PlaybackDevice, AlgorithmGroup, AlgorithmDefinition,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables():
    """清空涉及表（sqlite 无 TRUNCATE，逐表 delete）。"""
    _ensure_tables()
    from audio_service.infrastructure.persistence.models import (
        Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation,
    )
    from device_service.infrastructure.persistence.models import (
        Device, PlaybackDevice,
    )
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmGroup, AlgorithmDefinition,
    )
    session = get_db_session()
    try:
        for model in (AudioAlgorithmRelation, AudioTag, AudioAnnotation, Audio,
                      PlaybackDevice, Device, AlgorithmDefinition, AlgorithmGroup):
            session.query(model).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _operator_db():
    _ensure_tables()
    _cleanup_tables()
    yield
    # 上下文必清理，防止泄漏到后续用例
    set_current_user_id(None)
    _cleanup_tables()


# ---------------- audio 域 ----------------

class TestAudioOperatorColumns:
    """audio CUD 操作人（INT-299）。"""

    def test_create_sets_created_by(self):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        set_current_user_id(101)
        agg = audio_repository.create_audio({
            'name': 'int299-a', 'file_path': 'x/a.wav', 'format': 'wav'})
        session = get_db_session()
        try:
            po = session.get(type(agg).__mro__[0] and __import__(
                'audio_service.infrastructure.persistence.models', fromlist=['Audio']).Audio, agg.id)
            assert po.created_by_user_id == 101
            assert po.updated_by_user_id is None  # create 不写 updated_by
            assert po.deleted_by_user_id is None
        finally:
            session.close()

    def test_update_sets_updated_by(self):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        from audio_service.infrastructure.persistence.models import Audio
        set_current_user_id(102)
        agg = audio_repository.create_audio({
            'name': 'int299-u', 'file_path': 'x/u.wav', 'format': 'wav'})
        audio_repository.update_audio(agg.id, {'name': 'int299-u2'})
        session = get_db_session()
        try:
            po = session.get(Audio, agg.id)
            assert po.name == 'int299-u2'
            assert po.updated_by_user_id == 102
            assert po.created_by_user_id == 102  # 同上下文创建
        finally:
            session.close()

    def test_delete_sets_deleted_by(self):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        from audio_service.infrastructure.persistence.models import Audio
        agg = audio_repository.create_audio({
            'name': 'int299-d', 'file_path': 'x/d.wav', 'format': 'wav'})
        set_current_user_id(103)
        assert audio_repository.delete_audio(agg.id) is True
        session = get_db_session()
        try:
            po = session.get(Audio, agg.id)
            assert po.deleted is True
            assert po.deleted_by_user_id == 103
            assert po.deleted_at is not None
        finally:
            session.close()

    def test_batch_delete_sets_deleted_by(self):
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        from audio_service.infrastructure.persistence.models import Audio
        ids = [audio_repository.create_audio({
            'name': f'int299-b{i}', 'file_path': f'x/b{i}.wav', 'format': 'wav'}).id
            for i in range(2)]
        set_current_user_id(104)
        count = audio_repository.batch_soft_delete_audios(ids)
        assert count == 2
        session = get_db_session()
        try:
            for po in session.query(Audio).filter(Audio.id.in_(ids)).all():
                assert po.deleted_by_user_id == 104
        finally:
            session.close()

    def test_no_context_columns_null(self):
        """无认证上下文（AUTH_MODE=off 等价）：三列 NULL，不硬编码 0。"""
        from audio_service.infrastructure.persistence.audio_repository import audio_repository
        from audio_service.infrastructure.persistence.models import Audio
        set_current_user_id(None)
        agg = audio_repository.create_audio({
            'name': 'int299-n', 'file_path': 'x/n.wav', 'format': 'wav'})
        audio_repository.delete_audio(agg.id)
        session = get_db_session()
        try:
            po = session.get(Audio, agg.id)
            assert po.created_by_user_id is None
            assert po.deleted_by_user_id is None
        finally:
            session.close()


# ---------------- device 域 ----------------

class TestDeviceOperatorColumns:
    """device CUD 操作人（INT-299）。"""

    def _device_data(self, name='int299-dev'):
        return {'name': name, 'model': 'M1', 'type': 'phone', 'system': 'Android',
                'system_version': '12', 'app_name': 'app', 'app_version': '1.0'}

    def test_create_update_delete(self):
        from device_service.infrastructure.persistence._device_repository_impl import DeviceRepository
        from device_service.infrastructure.persistence.models import Device
        repo = DeviceRepository()
        set_current_user_id(201)
        agg = repo.create_device(self._device_data())
        session = get_db_session()
        try:
            assert session.get(Device, agg.id).created_by_user_id == 201
        finally:
            session.close()

        set_current_user_id(202)
        repo.update_device(agg.id, {'description': 'upd'})
        session = get_db_session()
        try:
            po = session.get(Device, agg.id)
            assert po.updated_by_user_id == 202
            assert po.created_by_user_id == 201
        finally:
            session.close()

        set_current_user_id(203)
        assert repo.delete_device(agg.id) is True
        session = get_db_session()
        try:
            po = session.get(Device, agg.id)
            assert po.deleted is True
            assert po.deleted_by_user_id == 203
            assert po.deleted_at is not None
        finally:
            session.close()


# ---------------- playback 域 ----------------

class TestPlaybackOperatorColumns:
    """playback_device CUD 操作人（INT-299）。"""

    def _pb_data(self, uid='uq-int299'):
        return {'name': 'int299-pb', 'model': 'PB', 'device_type': 'dry',
                'sample_rate': 48000, 'device_unique_id': uid}

    def test_create_update_delete(self):
        from device_service.infrastructure.persistence._playback_repository_impl import PlaybackRepository
        from device_service.infrastructure.persistence.models import PlaybackDevice
        repo = PlaybackRepository()
        set_current_user_id(301)
        agg = repo.create_playback_device(self._pb_data())
        session = get_db_session()
        try:
            assert session.get(PlaybackDevice, agg.id).created_by_user_id == 301
        finally:
            session.close()

        set_current_user_id(302)
        repo.update_playback_device(agg.id, {'description': 'upd'})
        session = get_db_session()
        try:
            po = session.get(PlaybackDevice, agg.id)
            assert po.updated_by_user_id == 302
        finally:
            session.close()

        set_current_user_id(303)
        assert repo.delete_playback_device(agg.id) is True
        session = get_db_session()
        try:
            po = session.get(PlaybackDevice, agg.id)
            assert po.is_deleted == 1
            assert po.deleted_by_user_id == 303
        finally:
            session.close()


# ---------------- algorithm 域 ----------------

class TestAlgorithmOperatorColumns:
    """algorithm 分组/定义 CUD 操作人（INT-299）。"""

    def test_group_add_save_soft_delete(self):
        from algorithm_service.infrastructure.persistence.algorithm_repository import (
            algorithm_group_repository,
        )
        from algorithm_service.infrastructure.persistence.models import AlgorithmGroup
        from algorithm_service.domain.entities.algorithm_group import AlgorithmGroupAggregate

        set_current_user_id(401)
        agg = AlgorithmGroupAggregate(
            id=0, name=f'int299-g-{utc8now().timestamp()}', description=None)
        gid = algorithm_group_repository.add(agg)
        session = get_db_session()
        try:
            assert session.get(AlgorithmGroup, gid).created_by_user_id == 401
        finally:
            session.close()

        agg.description = 'upd'
        algorithm_group_repository.save(agg)
        session = get_db_session()
        try:
            po = session.get(AlgorithmGroup, gid)
            assert po.updated_by_user_id == 401
        finally:
            session.close()

        set_current_user_id(402)
        assert algorithm_group_repository.soft_delete(gid) is True
        session = get_db_session()
        try:
            po = session.get(AlgorithmGroup, gid)
            assert po.deleted is True
            assert po.deleted_by_user_id == 402
        finally:
            session.close()

    def test_definition_add_save_soft_delete(self):
        from algorithm_service.infrastructure.persistence.algorithm_repository import (
            algorithm_definition_repository,
        )
        from algorithm_service.infrastructure.persistence.models import AlgorithmDefinition
        from algorithm_service.domain.entities.algorithm_definition import (
            AlgorithmDefinitionAggregate, AlgorithmStatus,
        )

        atype = f'int299_algo_{utc8now().timestamp()}'
        set_current_user_id(501)
        agg = AlgorithmDefinitionAggregate(
            id=0, group_id=None, name='int299-def', algorithm_type=atype,
            status=AlgorithmStatus.DRAFT)
        did = algorithm_definition_repository.add(agg)
        session = get_db_session()
        try:
            assert session.get(AlgorithmDefinition, did).created_by_user_id == 501
        finally:
            session.close()

        agg.description = 'upd'
        algorithm_definition_repository.save(agg)
        session = get_db_session()
        try:
            po = session.get(AlgorithmDefinition, did)
            assert po.updated_by_user_id == 501
        finally:
            session.close()

        set_current_user_id(502)
        assert algorithm_definition_repository.soft_delete(did) is True
        session = get_db_session()
        try:
            po = session.get(AlgorithmDefinition, did)
            assert po.deleted is True
            assert po.deleted_by_user_id == 502
        finally:
            session.close()

    def test_no_context_columns_null(self):
        """无认证上下文：算法域三列 NULL。"""
        from algorithm_service.infrastructure.persistence.algorithm_repository import (
            algorithm_group_repository,
        )
        from algorithm_service.infrastructure.persistence.models import AlgorithmGroup
        from algorithm_service.domain.entities.algorithm_group import AlgorithmGroupAggregate

        set_current_user_id(None)
        agg = AlgorithmGroupAggregate(
            id=0, name=f'int299-null-{utc8now().timestamp()}', description=None)
        gid = algorithm_group_repository.add(agg)
        algorithm_group_repository.soft_delete(gid)
        session = get_db_session()
        try:
            po = session.get(AlgorithmGroup, gid)
            assert po.created_by_user_id is None
            assert po.deleted_by_user_id is None
        finally:
            session.close()
