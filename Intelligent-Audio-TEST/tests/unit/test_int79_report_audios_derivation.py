# -*- coding: utf-8 -*-
"""报告音频列表不再携带 api/e2e 口径 + GetTaskStatus 响应去残留键。

报告音频项原读用例 test_type（差异#2 收尾后恒缺键）并派生 testType/audio_type；
用例不再区分 api/e2e 后，报告音频只保留音频本身信息（id/文件名/时长/设备等），
执行口径由任务侧 task_case_relations.device_type 承载。

缺陷5：task_service GetTaskStatus 死端点响应残留 "type"（Task.type 列已删
恒 null）与 "error_message": None（Task 无该列的恒定占位）。
"""
import json
import os
import tempfile
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int79_audios_') + '/audios.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from task_service.infrastructure.persistence.models import Task
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

import report_service.application.services.report_helpers as rh
from report_service.application.services.report_helpers import ReportHelpers


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


_ROUND = {
    'roundNumber': 1,
    'audios': [{'audio_id': 11, 'playback_device_id': 7, 'spl': 70, 'play_order': 1}],
}
_LEGACY_TYPE_KEYS = ('testType', 'audio_type', 'test_type')


def _case(config, name='回归用例'):
    return {'id': 'tc-1', 'name': name, 'config': config}


@pytest.fixture(autouse=True)
def _stub_grpc_clients(monkeypatch):
    """音频/设备 gRPC 查询打桩：音频恒命中，设备名映射固定。"""
    monkeypatch.setattr(rh, '_grpc_get_audio',
                        lambda audio_id: {'id': audio_id, 'name': f'audio-{audio_id}',
                                          'original_filename': f'a{audio_id}.wav', 'duration': 3.0})
    monkeypatch.setattr(rh, '_grpc_get_playback_devices_by_ids',
                        lambda ids: {i: {'name': f'pb-{i}'} for i in ids})
    monkeypatch.setattr(rh, '_grpc_get_devices_by_ids',
                        lambda ids: {i: {'name': f'dev-{i}'} for i in ids})


def _assert_no_type_keys(audios_list):
    for item in audios_list:
        for key in _LEGACY_TYPE_KEYS:
            assert key not in item, f'报告音频项残留口径键 {key}: {item}'


def test_task_mode_audios_have_no_type_key():
    """task 模式：音频项不再输出 testType，其余字段照常。"""
    audios = ReportHelpers._build_audios_list(_case({'rounds': [_ROUND]}), mode='task')
    assert audios
    assert audios[0]['filename'] == 'a11.wav'
    _assert_no_type_keys(audios)


def test_compare_mode_audios_have_no_audio_type_key():
    """compare 模式：音频项不再输出 audio_type。"""
    audios = ReportHelpers._build_audios_list(_case({'rounds': [_ROUND]}), mode='compare')
    assert audios
    _assert_no_type_keys(audios)


def test_simplenamespace_path_no_test_type_attribute():
    """BuildReferenceParams 路径：SimpleNamespace 无 test_type 属性不再 AttributeError。"""
    case = SimpleNamespace(id='tc-1', name='测试用例_素材_e2e_023604',
                           config={'auto_generated': True, 'rounds': [_ROUND]})
    audios = ReportHelpers._build_audios_list(case, mode='task')
    assert audios
    _assert_no_type_keys(audios)


@pytest.fixture(scope='module')
def db():
    """初始化共享 sqlite 并种子一条任务，供 GetTaskStatus 查询。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'audios sqlite 需要文件型 sqlite，实际绑定 {engine.url}'
    remove_db_session()
    Base.metadata.create_all(bind=engine, tables=[Task.__table__])
    session = get_db_session()
    task = Task(name='int79-status', status='running', total_cases=2,
                completed_cases=1, failed_cases=0)
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()
    yield task_id
    remove_db_session()


def test_get_task_status_response_has_no_residual_keys(db):
    """缺陷5：GetTaskStatus 响应不再含 'type' / 'error_message' 残留键。"""
    from types import SimpleNamespace as _NS
    from task_service.interfaces.grpc.execution import ExecutionServiceServicer

    servicer = ExecutionServiceServicer()
    resp = servicer.GetTaskStatus(_NS(task_id=db))
    assert resp.success
    data = json.loads(resp.data) if resp.data else {}
    assert data.get('status') == 'running'
    assert 'type' not in data, f'GetTaskStatus 响应残留 type 键: {sorted(data)}'
    assert 'error_message' not in data, f'GetTaskStatus 响应残留 error_message 键: {sorted(data)}'
