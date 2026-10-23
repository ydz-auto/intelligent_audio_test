# -*- coding: utf-8 -*-
"""INT-1306 音频删除引用检查单测（真实库走查修复）。

覆盖（sqlite 文件库，不依赖真库）：
- task_query_service.check_audio_references：用例音频 / 用例背景噪音 /
  任务（经 task_case_relations 关联用例 + 任务 config 内嵌 audio_id）计数
- P1 覆盖修复：轮次级 camelCase backgroundNoise、segment 级
  rounds[].audios[].background_noise、rounds[].audios[].interferers[].audio_id
  三种真实引用形态（_apply_noise_to_round 写入），不再漏拦

验收口径对齐原卡（引用检查单次 DB 扫描，无逐页 gRPC 全量拉取；
被引用音频明确返回跳过文案；批量删除返回逐项成功/跳过计数）。
"""
import os
import tempfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int1306_unit_') + '/unit.db')

import pytest

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)


@pytest.fixture(scope='module')
def db():
    """初始化 sqlite 文件库并建 test_cases / test_tasks / task_case_relations 表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), '需要文件型 sqlite（跨线程共享表）'
    remove_db_session()
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[TestCase.__table__, Task.__table__, TaskCase.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture(autouse=True)
def _clean_db(db):
    """每个用例清理表数据。"""
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase,
    )
    yield
    session = get_db_session()
    session.query(TaskCase).delete()
    session.query(TestCase).delete()
    session.query(Task).delete()
    session.commit()
    remove_db_session()


def _insert_case(case_id, config, deleted=False):
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    po = TestCase(
        id=case_id,
        name=f'case_{case_id}',
        config=config,
        deleted=deleted,
    )
    session.add(po)
    session.commit()


def _insert_task(task_id, config=None, deleted=False):
    from task_service.infrastructure.persistence.models import Task
    session = get_db_session()
    po = Task(
        id=task_id,
        name=f'task_{task_id}',
        config=config,
        deleted=deleted,
    )
    session.add(po)
    session.commit()


def _insert_task_case(task_id, case_id):
    from task_service.infrastructure.persistence.models import TaskCase
    session = get_db_session()
    po = TaskCase(
        task_id=task_id,
        test_case_id=case_id,
    )
    session.add(po)
    session.commit()


def _call_check(audio_ids):
    """调 task_query_service.check_audio_references（进程级唯一导入）。"""
    from task_service.application.task.task_query_service import task_query_service
    return task_query_service.check_audio_references(audio_ids)


class TestCheckAudioReferences:
    def test_case_rounds_audios_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 11}, {'audio_id': 12}]}]})
        _insert_case('c2', {'rounds': [{'audios': [{'audio_id': 11}]}]})
        result = _call_check([11, 12, 13])
        assert result['success'] is True
        refs = result['data']['references']
        assert refs['11']['testcase_audio'] == 2
        assert refs['12']['testcase_audio'] == 1
        assert refs['13']['testcase_audio'] == 0

    def test_case_top_level_audios_counted(self):
        _insert_case('c1', {'audios': [{'audio_id': 21}]})
        result = _call_check([21])
        assert result['data']['references']['21']['testcase_audio'] == 1

    def test_case_background_noise_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 30}]}],
                            'background_noise': {'audio_id': 31}})
        result = _call_check([30, 31])
        refs = result['data']['references']
        assert refs['30']['testcase_audio'] == 1
        assert refs['31']['testcase_noise'] == 1
        assert refs['31']['testcase_audio'] == 0

    def test_deleted_cases_not_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 41}]}]}, deleted=True)
        result = _call_check([41])
        assert result['data']['references']['41']['testcase_audio'] == 0

    def test_task_config_embedded_audio_id_counted(self):
        _insert_task(1, {'parallel': True, 'audio_id': 51})
        result = _call_check([51])
        assert result['data']['references']['51']['task'] == 1

    def test_task_linked_case_audio_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 61}]}]})
        _insert_case('c2', {'rounds': [{'audios': [{'audio_id': 62}]}]})
        _insert_task(1, {'parallel': True})
        _insert_task(2, {'parallel': True})
        _insert_task_case(1, 'c1')
        _insert_task_case(2, 'c2')
        result = _call_check([61, 62])
        refs = result['data']['references']
        assert refs['61']['task'] == 1
        assert refs['62']['task'] == 1

    def test_deleted_tasks_not_counted(self):
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 71}]}]})
        _insert_task(1, {'parallel': True}, deleted=True)
        _insert_task_case(1, 'c1')
        result = _call_check([71])
        # 用例引用仍计 1；任务已删不计
        assert result['data']['references']['71']['testcase_audio'] == 1
        assert result['data']['references']['71']['task'] == 0

    def test_empty_audio_ids_ok(self):
        result = _call_check([])
        assert result['success'] is True
        assert result['data']['references'] == {}

    def test_case_round_camelcase_background_noise_counted(self):
        # P1 覆盖：轮次级 camelCase backgroundNoise（_apply_noise_to_round
        # 的 caseBackgroundNoise 目标），旧实现只读 snake 漏拦
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 30}],
                                        'backgroundNoise': {'audio_id': 31}}]})
        result = _call_check([30, 31])
        refs = result['data']['references']
        assert refs['30']['testcase_audio'] == 1
        assert refs['31']['testcase_noise'] == 1
        assert refs['31']['testcase_audio'] == 0

    def test_case_segment_background_noise_counted(self):
        # P1 覆盖：segment 级 rounds[].audios[].background_noise
        # （_apply_noise_to_round 的 segmentBackgroundNoise 目标）
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 30,
                                                    'background_noise': {'audio_id': 32}}]}]})
        result = _call_check([30, 32])
        refs = result['data']['references']
        assert refs['30']['testcase_audio'] == 1
        assert refs['32']['testcase_noise'] == 1
        assert refs['32']['testcase_audio'] == 0

    def test_case_segment_interferers_counted(self):
        # P1 覆盖：rounds[].audios[].interferers[].audio_id（干扰人，
        # _apply_noise_to_round 的 interferers 目标）→ testcase_audio
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 30,
                                                    'interferers': [{'audio_id': 33}]}]}]})
        result = _call_check([30, 33])
        refs = result['data']['references']
        assert refs['30']['testcase_audio'] == 1
        assert refs['33']['testcase_audio'] == 1
        assert refs['33']['testcase_noise'] == 0

    def test_case_top_level_camelcase_background_noise_counted(self):
        # P1 覆盖：顶层 camelCase backgroundNoise（convert_flat_config_to_rounds
        # 迁移期间可能残留的形态）
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 30}]}],
                            'backgroundNoise': {'audio_id': 34}})
        result = _call_check([34])
        assert result['data']['references']['34']['testcase_noise'] == 1

    def test_task_linked_case_interferers_and_segment_noise_counted(self):
        # P1 覆盖：任务-用例关联侧同口径（interferers + segment 级噪音）
        _insert_case('c1', {'rounds': [{'audios': [{'audio_id': 35,
                                                    'interferers': [{'audio_id': 36}],
                                                    'background_noise': {'audio_id': 37}}]}]})
        _insert_task(1, {'parallel': True})
        _insert_task_case(1, 'c1')
        result = _call_check([35, 36, 37])
        refs = result['data']['references']
        assert refs['35']['testcase_audio'] == 1
        assert refs['36']['testcase_audio'] == 1
        assert refs['37']['testcase_noise'] == 1
        assert refs['36']['task'] == 1
        assert refs['37']['task'] == 1
