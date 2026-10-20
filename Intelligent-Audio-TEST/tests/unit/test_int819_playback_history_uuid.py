# -*- coding: utf-8 -*-
"""INT-819 回归测试：播放历史写侧 testcase_id 支持 UUID（String 列）。

INT-819 返工（测试工程师打回 P2：写侧「测试用例」字段不可达）：
testcase_id 由 BigInteger 改为 String(50)，用例预览写侧携带 UUID 用例上下文。
本测试守护该列类型，防止回归为整型导致 UUID 无法落库。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import uuid

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from audio_service.infrastructure.persistence.models import (
            Audio, AudioPlaybackHistory,
        )
        _TABLES = [t.__table__ for t in (Audio, AudioPlaybackHistory)]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def test_playback_history_accepts_uuid_testcase_id():
    _ensure_tables()
    from audio_service.infrastructure.persistence.models import AudioPlaybackHistory
    s = get_db_session()
    tc_id = str(uuid.uuid4())
    row = AudioPlaybackHistory(
        audio_id=1,
        testcase_id=tc_id,
        testcase_name='演示用例-UUID',
        device_id='default',
        device_name='默认设备',
        result='success',
        duration=3.5,
        source='preview',
    )
    # sqlite 下 BigInteger 主键不自增（仅 Postgres BIGSERIAL 自增），显式赋主键
    if get_engine().dialect.name == 'sqlite':
        row.id = 1
    s.add(row)
    s.commit()
    r = s.query(AudioPlaybackHistory).first()
    assert r.testcase_id == tc_id
    assert isinstance(r.testcase_id, str)
    assert r.testcase_name == '演示用例-UUID'
    # 列类型应为 String（支持 UUID）
    assert str(AudioPlaybackHistory.__table__.c.testcase_id.type).startswith('VARCHAR')
    # 清理
    s.delete(r)
    s.commit()
    remove_db_session()
