# -*- coding: utf-8 -*-
"""INT-1504 缺陷3：数字域 RMS-SPL 读模型补齐 created_at / updated_at

React 详情弹窗「创建时间/更新时间」读 dto.created_at / updated_at；
此前 _po_to_entity 不映射、_mapping_to_dict 不输出，恒显示「—」。

覆盖：
- 真库（SQLite）落库后 _po_to_entity 带出 datetime 时间字段
- _mapping_to_dict 输出 ISO 字符串（gRPC 载荷走 JSON，不能直出 datetime）
- 整体可 json.dumps（servicer _dumps 口径）
- 无时间值的实体不抛错（回退 None）
"""
import json
import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

import pytest

import shared.models.database as database


@pytest.fixture()
def db():
    from sqlalchemy import create_engine

    from api_test_service.infrastructure.persistence.models.api_models import (
        API,
        ApiRmsSplMappingPO,
    )

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(
        engine, tables=[API.__table__, ApiRmsSplMappingPO.__table__])
    yield database
    database.remove_db_session()
    engine.dispose()
    os.remove(path)


class TestDigitalSplReadModelTimestamps:
    def test_entity_carries_timestamps_from_db(self, db):
        from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
            ApiRmsSplRepositoryImpl,
        )

        repo = ApiRmsSplRepositoryImpl()
        created = repo.create_mapping({'api_id': 1, 'name': 'm1'})
        assert created.created_at is not None
        assert created.updated_at is not None
        assert hasattr(created.created_at, 'isoformat')

        fetched = repo.get_mapping(created.id)
        assert fetched.created_at is not None
        assert hasattr(fetched.created_at, 'isoformat')

    def test_mapping_to_dict_emits_iso_strings_and_is_json_safe(self, db):
        from api_test_service.application.api_rms_spl_config_service import (
            _mapping_to_dict,
        )
        from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
            ApiRmsSplRepositoryImpl,
        )

        repo = ApiRmsSplRepositoryImpl()
        created = repo.create_mapping({'api_id': 1, 'name': 'm2'})
        payload = _mapping_to_dict(created)

        assert isinstance(payload['created_at'], str)
        assert isinstance(payload['updated_at'], str)
        assert payload['created_at'] == created.created_at.isoformat()
        # servicer 通过 json.dumps 下发，datetime 直出会抛 TypeError
        assert json.loads(json.dumps(payload))['created_at'] == payload['created_at']

    def test_missing_timestamps_fall_back_to_none(self):
        from api_test_service.application.api_rms_spl_config_service import (
            _mapping_to_dict,
        )
        from api_test_service.domain.entities.api_rms_spl_mapping import ApiRmsSplMapping

        payload = _mapping_to_dict(ApiRmsSplMapping(id=1, api_id=1))
        assert payload['created_at'] is None
        assert payload['updated_at'] is None
        assert json.dumps(payload)
