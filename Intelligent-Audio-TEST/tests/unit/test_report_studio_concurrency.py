# -*- coding: utf-8 -*-
"""Report Studio 乐观锁真并发复现（INT-673 验收标准 2）

验收标准 2：「并发 PUT 同 expected_version → 后者 409 + 差异信息，不覆盖」。

test_report_studio.py 的 409 用例只覆盖「顺序」场景（前一次提交完成后，第二次
再带同一 expected_version 提交）。本文件强制两条写请求真正并发（都在读到
current_version=1 之后、任一方提交之前），核对「后保存覆盖前者」是否真的被
§15.4 废弃：

期望：一方成功，另一方 409 + current_version/diff；
现状（复现 bug）：一方成功，另一方 500（版本快照 UNIQUE(doc_id,version) 冲突
IntegrityError 原样上抛），丢失 409 语义。
"""
import os
import tempfile
import threading

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import create_engine

import shared.models.database as database
from shared.infrastructure.user_context import (
    set_current_user_id,
    set_current_user_is_admin,
)
from report_service.infrastructure.persistence.models import Report
from report_service.application.services.report_studio_service import report_studio_service
from report_service.infrastructure.persistence.report_studio_repository import (
    ReportStudioRepositoryImpl,
)


@pytest.fixture()
def sqlite_db(monkeypatch, tmp_path):
    path = str(tmp_path / 'studio_conc.db')
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    set_current_user_id(1)
    set_current_user_is_admin(True)
    yield database
    set_current_user_id(None)
    set_current_user_is_admin(False)
    database.remove_db_session()
    engine.dispose()


def test_concurrent_put_same_version_loser_gets_409_not_500(sqlite_db):
    """两个并发 PUT 同 expected_version=1：败者应 409，不得 500/覆盖。"""
    session = database.get_db_session()
    report = Report(name='并发测试', type='standard', status='completed', task_id=1)
    session.add(report)
    session.commit()
    report_id = report.id
    session.close()

    svc = report_studio_service
    doc_id = svc.create_document({'report_id': report_id, 'markdown_content': '# v1'})['data']['doc_id']

    # 强制两条写请求都在读到 current_version=1 之后、任一方提交之前（真并发窗口）
    orig_get = ReportStudioRepositoryImpl.get_document
    barrier = threading.Barrier(2)
    read_count = {'n': 0}

    def synced_get(self, doc_id):
        read_count['n'] += 1
        if read_count['n'] <= 2:
            barrier.wait(timeout=5)
        return orig_get(self, doc_id)

    ReportStudioRepositoryImpl.get_document = synced_get

    results = {}

    def put(tag, content):
        r = svc.update_document({
            'doc_id': doc_id, 'expected_version': 1, 'markdown_content': content})
        results[tag] = r

    t1 = threading.Thread(target=put, args=('T1', '# 并发甲'))
    t2 = threading.Thread(target=put, args=('T2', '# 并发乙'))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    ReportStudioRepositoryImpl.get_document = orig_get

    codes = {tag: r['code'] for tag, r in results.items()}
    assert sorted(codes.values()) == [0, 409], (
        f'真并发下败者未返回 409，实际码 {codes}；败者 message={next(r["message"] for r in results.values() if r["code"] != 0)}')

    # 败者 409 应带 current_version / diff（§15.4）
    loser = next(r for r in results.values() if r['code'] != 0)
    assert loser['data'].get('current_version') == 2
    assert loser['data'].get('diff')

    # 不覆盖：胜者内容保留
    cur = svc.get_document({'doc_id': doc_id})
    assert cur['data']['markdown_content'] in ('# 并发甲', '# 并发乙')
    # 版本快照仍两版，无丢失/重复
    versions = svc.list_versions({'doc_id': doc_id})['data']
    assert versions['total'] == 2
    assert [v['version'] for v in versions['items']] == [1, 2]
