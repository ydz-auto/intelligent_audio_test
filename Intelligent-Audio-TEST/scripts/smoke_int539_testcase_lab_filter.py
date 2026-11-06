# -*- coding: utf-8 -*-
"""INT-539 集成冒烟（真实 Postgres 隔离库 intelligent_audio_test_test）。

验证：ListTestCases lab_ids 过滤（含通用用例）在真实 JSONB 上的 SQL 口径，
列表项透出 lab_id/lab_name（laboratories join，软删/缺失实验室 lab_name=None）。
实验室与用例 lab_id 使用 INT539_SMOKE 专属 ID（9001-9003），不与存量数据冲突。
测试数据以 INT539_SMOKE_ 前缀写入，finally 清理。
"""
import os
import sys

os.environ['DATABASE_URL'] = (
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test_test'
)
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

L1_ID = 9001  # 活跃实验室
L5_ID = 9002  # 软删实验室
L7_ID = 9003  # 未注册实验室


def main():
    from sqlalchemy import text
    from shared.models.database import init_db, get_db_session, remove_db_session, Base, get_engine, utc8now
    from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup, Tag, TagCategory, TestCaseTag

    init_db(pool_size=2)
    # 建表（幂等；隔离库已有，补齐缺表）
    for t in (TestCase, TestCaseGroup, Tag, TagCategory, TestCaseTag):
        Base.metadata.create_all(bind=get_engine(), tables=[t.__table__])

    session = get_db_session()
    cleaned = False
    try:
        # 清理残留（防重跑）
        session.execute(
            text("DELETE FROM test_cases WHERE id LIKE 'INT539_SMOKE_%'"))
        session.execute(
            text("DELETE FROM laboratories WHERE code LIKE 'INT539_SMOKE_%'"))
        session.commit()

        # 种子：实验室（活跃 + 软删）
        session.execute(text(
            "INSERT INTO laboratories (id, code, name, status, deleted) VALUES "
            "(:l1, 'INT539_SMOKE_L1', '冒烟三号实验室', 'active', false), "
            "(:l5, 'INT539_SMOKE_L5', '冒烟软删实验室', 'active', true)"
        ), {'l1': L1_ID, 'l5': L5_ID})
        # 种子：用例（通用 / 专属L1 / 专属软删L5 / 越域L7）
        now = utc8now()
        session.add_all([
            TestCase(id='INT539_SMOKE_G', name='冒烟通用', config={}, created_at=now, updated_at=now),
            TestCase(id='INT539_SMOKE_L1', name='冒烟专属L1', config={'lab_id': L1_ID}, created_at=now, updated_at=now),
            TestCase(id='INT539_SMOKE_L5', name='冒烟专属软删L5', config={'lab_id': L5_ID}, created_at=now, updated_at=now),
            TestCase(id='INT539_SMOKE_L7', name='冒烟专属L7', config={'lab_id': L7_ID}, created_at=now, updated_at=now),
        ])
        session.commit()

        from task_service.application.queries.task_queries import ListTestCasesQuery
        from task_service.application.handlers import task_query_handler

        # 1) 过滤 lab_ids=[L1]：通用 + 专属L1 可见；软删L5/越域L7 排除
        r = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=50, lab_ids=[L1_ID], keyword='INT539_SMOKE'))
        assert r.get('success') is True, r
        items = r['data']['items']
        by_id = {tc['id']: tc for tc in items}
        assert 'INT539_SMOKE_G' in by_id, list(by_id)
        assert 'INT539_SMOKE_L1' in by_id
        assert 'INT539_SMOKE_L5' not in by_id
        assert 'INT539_SMOKE_L7' not in by_id
        # 通用用例 lab_id=null
        assert by_id['INT539_SMOKE_G']['lab_id'] is None
        assert by_id['INT539_SMOKE_G']['lab_name'] is None
        # 专属L1：lab_id + lab_name join
        assert by_id['INT539_SMOKE_L1']['lab_id'] == L1_ID
        assert by_id['INT539_SMOKE_L1']['lab_name'] == '冒烟三号实验室'
        print('[OK] 过滤 lab_ids=[L1]：通用可见 / 专属命中 / 越域排除 / lab_name join')

        # 2) 过滤 lab_ids=[L1, L7]：专属L7 加入
        r2 = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=50, lab_ids=[L1_ID, L7_ID], keyword='INT539_SMOKE'))
        items2 = {tc['id']: tc for tc in r2['data']['items']}
        assert 'INT539_SMOKE_L7' in items2
        assert 'INT539_SMOKE_L5' not in items2
        assert items2['INT539_SMOKE_L7']['lab_name'] is None  # 未注册实验室
        print('[OK] 过滤 lab_ids=[L1,L7]：多实验室集合 / 未注册 lab_id 的 lab_name=null')

        # 3) 不过滤：全部可见（回归），透出 lab 字段
        r3 = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=50, keyword='INT539_SMOKE'))
        ids3 = {tc['id'] for tc in r3['data']['items']}
        assert {'INT539_SMOKE_G', 'INT539_SMOKE_L1', 'INT539_SMOKE_L5', 'INT539_SMOKE_L7'} <= ids3
        print('[OK] 不传 lab_ids：全量返回（回归），新字段可选')

        # 4) 软删实验室 lab_name=None（config lab_id=L5，对应实验室已软删）
        r4 = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=50, lab_ids=[L5_ID], keyword='INT539_SMOKE'))
        items4 = {tc['id']: tc for tc in r4['data']['items']}
        assert 'INT539_SMOKE_L5' in items4
        assert items4['INT539_SMOKE_L5']['lab_id'] == L5_ID
        assert items4['INT539_SMOKE_L5']['lab_name'] is None
        print('[OK] 软删实验室：lab_id 透出、lab_name=null')

        print('SMOKE PASSED')
    finally:
        try:
            session.execute(
                text("DELETE FROM test_cases WHERE id LIKE 'INT539_SMOKE_%'"))
            session.execute(
                text("DELETE FROM laboratories WHERE code LIKE 'INT539_SMOKE_%'"))
            # 重置显式 ID 插入推进的序列，避免影响后续正常插入
            session.execute(text(
                "SELECT setval(pg_get_serial_sequence('laboratories', 'id'), "
                "COALESCE((SELECT MAX(id) FROM laboratories), 1), true)"
            ))
            session.commit()
            cleaned = True
        except Exception:
            session.rollback()
        remove_db_session()
    print('CLEANED' if cleaned else 'CLEAN FAILED')


if __name__ == '__main__':
    main()
