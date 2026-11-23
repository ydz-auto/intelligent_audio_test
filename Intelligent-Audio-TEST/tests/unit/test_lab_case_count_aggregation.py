# -*- coding: utf-8 -*-
"""实验室用例计数聚合：task_service 一次 group_by=lab_id 统计替代逐页扫描。

覆盖：
- get_testcase_stats(group_by='lab_id') 按 config 顶层 lab_id 分组，
  软删用例不计入，无 lab_id 的通用用例归到空 key；
- device_service count_test_cases 只映射请求的 lab_ids，忽略通用/越域计数，
  空 lab_ids 不发起 gRPC。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import get_db_session, remove_db_session
from tests.unit.test_int539_testcase_lab_filter import _ensure_case_tables


@pytest.fixture()
def case_db():
    _ensure_case_tables()
    session = get_db_session()
    yield session
    remove_db_session()


def _insert_case(session, case_id, lab_id, deleted=False):
    from task_service.infrastructure.persistence.models import TestCase

    config = {} if lab_id is None else {'lab_id': lab_id}
    session.add(TestCase(id=case_id, name=case_id, config=config, deleted=deleted))
    session.flush()


def test_group_by_lab_id_counts_lab_cases(case_db):
    _insert_case(case_db, 'agg-case-lab9001-a', 9001)
    _insert_case(case_db, 'agg-case-lab9001-b', 9001)
    _insert_case(case_db, 'agg-case-lab9002-a', 9002)
    _insert_case(case_db, 'agg-case-common', None)
    _insert_case(case_db, 'agg-case-deleted', 9001, deleted=True)
    case_db.commit()

    from task_service.infrastructure.persistence.testcase_repository import testcase_repository

    result = testcase_repository.get_testcase_stats(group_by='lab_id')

    assert 'error' not in result
    counts = {item['key']: item['count'] for item in result['items']}
    assert counts.get('9001') == 2
    assert counts.get('9002') == 1
    assert counts.get('') == 1


def test_device_count_test_cases_maps_requested_labs(monkeypatch):
    from device_service.infrastructure.acl import testcase_acl_repository as acl_module
    from device_service.infrastructure.persistence.laboratory_repository import (
        laboratory_repository,
    )

    calls = []

    def _fake_stats(group_by=''):
        calls.append(group_by)
        return {
            'items': [
                {'key': '1', 'count': 37},
                {'key': '2', 'count': 3},
                {'key': '', 'count': 99},
            ]
        }

    monkeypatch.setattr(acl_module.testcase_acl_repository, 'get_testcase_stats', _fake_stats)

    assert laboratory_repository.count_test_cases([1]) == {1: 37}
    assert laboratory_repository.count_test_cases([1, 2]) == {1: 37, 2: 3}
    assert laboratory_repository.count_test_cases([99]) == {}
    assert laboratory_repository.count_test_cases([]) == {}
    # 空 lab_ids 不查；其余三次各一次聚合（99 越域也查一次，结果为空）
    assert calls == ['lab_id', 'lab_id', 'lab_id']
