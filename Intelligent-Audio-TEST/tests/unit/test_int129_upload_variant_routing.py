# -*- coding: utf-8 -*-
"""INT-129 验收测试：上传双变体 API 用例经常规建任务路径路由 http_api。

上传双变体（audio_service 建用例 f"{base_name}_{tt}"）两变体配置形态相同
（rounds[].audios 均带 playback_device_id——API 变体逐轮 SPL 渲染依赖播放设备），
INT-104 配置形态派生把 API 变体也判为 e2e → task_case_relations.device_type
= 'physical' → 被误路由到 E2E 执行器（任务 521/522 实证，约 10s 失败）。

修复口径：用例为上传生成（config.auto_generated）且名称带 _api/_e2e 变体
后缀（重名冲突追加 _%H%MSS）时以后缀为准；未传名称 / 非上传生成 / 无后缀
一律回落配置形态派生（INT-104 口径不变），显式 case_devices 仍最高优先。

覆盖：derive_case_test_type 纯函数口径 + 建任务路径（真库）+ 动态加用例路径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.utils.testcase_helpers import derive_case_test_type

_VARIANT_CONFIG = {
    'auto_generated': True,
    'source_audio': '素材.wav',
    'rounds': [{'audios': [{'audio_id': 1, 'playback_device_id': 7}]}],
}
_MANUAL_SAME_SHAPE_CONFIG = {
    'rounds': [{'audios': [{'audio_id': 1, 'playback_device_id': 7}]}],
}


class TestDeriveCaseTestTypeVariantSuffix:
    def test_upload_api_variant_name_suffix_wins(self):
        """上传 API 变体（_api 后缀，配置形态同为 e2e）→ api。"""
        assert derive_case_test_type(_VARIANT_CONFIG, '测试用例_素材_api') == 'api'

    def test_upload_api_variant_with_conflict_timestamp(self):
        """重名冲突后缀 _api_HHMMSS 同样识别（上传实测名 ..._api_023604）。"""
        assert derive_case_test_type(_VARIANT_CONFIG, '测试用例_素材_api_023604') == 'api'

    def test_upload_e2e_variant_name_suffix(self):
        """上传 E2E 变体 → e2e（与配置形态一致）。"""
        assert derive_case_test_type(_VARIANT_CONFIG, '测试用例_素材_e2e_023604') == 'e2e'

    def test_no_name_falls_back_to_config_shape(self):
        """不传名称：维持 INT-104 配置形态口径（回归保护）。"""
        assert derive_case_test_type(_VARIANT_CONFIG) == 'e2e'
        assert derive_case_test_type({'rounds': [{'audios': [{'audio_id': 2}]}]}) == 'api'

    def test_manual_case_with_api_like_name_not_overridden(self):
        """手工用例（无 auto_generated）名称恰以 _api 结尾：不被名称覆盖。"""
        assert derive_case_test_type(_MANUAL_SAME_SHAPE_CONFIG, '手工回归_api') == 'e2e'
        assert derive_case_test_type(_MANUAL_SAME_SHAPE_CONFIG, '手工回归_api_023604') == 'e2e'

    def test_suffix_not_at_end_ignored(self):
        """变体字样不在名称末尾：回落配置形态。"""
        assert derive_case_test_type(_VARIANT_CONFIG, 'api_素材用例') == 'e2e'
        assert derive_case_test_type(_VARIANT_CONFIG, '测试用例_素材_api_0236047') == 'e2e'

    def test_auto_generated_without_suffix_falls_back(self):
        """上传生成但名称无变体后缀（单类型上传）：配置形态口径。"""
        assert derive_case_test_type(_VARIANT_CONFIG, '测试用例_素材') == 'e2e'


_API_VARIANT_ID = 'int129-case-api'
_E2E_VARIANT_ID = 'int129-case-e2e'
_MANUAL_ID = 'int129-case-manual'


@pytest.fixture(scope='module')
def db():
    from shared.models.database import (
        Base, init_db, get_engine, get_db_session, remove_db_session,
    )
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase,
    )
    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(),
        tables=[Task.__table__, TaskCase.__table__, TestCase.__table__],
    )
    session = get_db_session()
    try:
        seeds = [
            (_API_VARIANT_ID, '测试用例_素材_api_023604', _VARIANT_CONFIG),
            (_E2E_VARIANT_ID, '测试用例_素材_e2e_023604', _VARIANT_CONFIG),
            (_MANUAL_ID, '手工回归_api', _MANUAL_SAME_SHAPE_CONFIG),
        ]
        for case_id, name, config in seeds:
            if session.get(TestCase, case_id) is None:
                session.add(TestCase(id=case_id, name=name, config=config))
        session.commit()
    finally:
        remove_db_session()
    yield
    remove_db_session()


def _create_task(case_ids, case_devices=None):
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository.create_task_with_relations(
        name='INT-129 双变体路由验证任务',
        description='',
        config=None,
        algorithm_type=None,
        algorithm_params=None,
        case_ids=list(case_ids),
        device_ids=[],
        api_ids=[],
        created_by=None,
        case_devices=case_devices,
    )


def _read_case_device_types(task_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models import TaskCase
    session = get_db_session()
    try:
        return {
            row.test_case_id: row.device_type
            for row in session.query(TaskCase).filter(TaskCase.task_id == task_id).all()
        }
    finally:
        remove_db_session()


class TestTaskPathVariantRouting:
    def test_create_api_variant_routes_http_api(self, db):
        """常规建任务（不传 case_devices）：上传 API 变体 → http_api（缺陷主场景）。"""
        task_id = _create_task([_API_VARIANT_ID])
        rows = _read_case_device_types(task_id)
        assert rows[_API_VARIANT_ID] == 'http_api'

    def test_create_e2e_variant_routes_physical(self, db):
        """上传 E2E 变体同口径建任务 → physical（E2E 链不受影响）。"""
        task_id = _create_task([_E2E_VARIANT_ID])
        rows = _read_case_device_types(task_id)
        assert rows[_E2E_VARIANT_ID] == 'physical'

    def test_manual_api_like_name_still_routes_physical(self, db):
        """手工用例（无 auto_generated）名称带 _api：保持配置形态路由 physical。"""
        task_id = _create_task([_MANUAL_ID])
        rows = _read_case_device_types(task_id)
        assert rows[_MANUAL_ID] == 'physical'

    def test_explicit_case_devices_still_wins(self, db):
        """显式 case_devices 优先级最高（任务 524 绕过路径不受影响）。"""
        task_id = _create_task(
            [_API_VARIANT_ID],
            case_devices=[{'case_id': _API_VARIANT_ID, 'device_type': 'physical'}],
        )
        rows = _read_case_device_types(task_id)
        assert rows[_API_VARIANT_ID] == 'physical'

    def test_dynamic_add_api_variant_routes_http_api(self, db):
        """动态加用例路径（update_cases add）：API 变体 → http_api。"""
        task_id = _create_task([_E2E_VARIANT_ID])
        from task_service.infrastructure.persistence.task_repository import task_repository
        result = task_repository.update_cases(task_id, 'add', [_API_VARIANT_ID])
        assert result == {'task_id': task_id, 'total_count': 2}
        rows = _read_case_device_types(task_id)
        assert rows[_API_VARIANT_ID] == 'http_api'
        assert rows[_E2E_VARIANT_ID] == 'physical'
