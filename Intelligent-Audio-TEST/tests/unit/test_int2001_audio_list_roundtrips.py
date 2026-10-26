# -*- coding: utf-8 -*-
"""INT-2001 音频列表路径 SQL 往返回合（C2/C3/C4/C6）单测。

覆盖卡片验收 3：
- C2 stats 合并：合并 SQL 的 sum / 今日 count 与旧两条 SQL 逐值一致，覆盖
  空表、今日为 0、跨日边界（created_at == 今日零点计入；零点前 1 秒不计）；
  合并后只发 1 条 SQL。
- C3 count 并入分页：total / items[].id 序列 / pages 与旧实现（
  `Query.paginate()` 的 count + 分页）逐值一致，覆盖无筛选、单/多标签、
  关键词、可见性、空结果、末页、超范围页；空结果集 total=0；page 超出范围
  total 仍正确且 items 为空。
- C4 load_only：列表 PO 不再加载 deleted_at / deleted_by_user_id /
  updated_by_user_id 三列，且列表 DTO 每个字段仍有值。
- C6 session 生命周期：去掉多余 rollback 后的现状锁定——请求收尾
  `remove_db_session()` 后连接确实归还连接池；异常路径仍会回滚且会话可复用。

全链路（`handle_list_audios`）SQL 条数断言为 4（改前 6）。
"""
import os
import tempfile
from datetime import timedelta

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int2001_unit_') + '/unit.db')

import pytest
from sqlalchemy import event, func
from sqlalchemy import inspect as sa_inspect

from shared.infrastructure.user_context import (
    set_current_user_id, set_current_user_is_admin,
)
from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from shared.utils.query_utils import now_cst


# ---------------- 夹具 ----------------

@pytest.fixture(scope='module')
def db():
    """文件型 sqlite；模块结束后清空本模块写入的行。

    单测之间共用 `DATABASE_URL` 指向的同一个文件库（各模块用 setdefault，
    先导入者决定路径），所以模块收尾必须把 audios / audio_tags /
    audio_annotations 清空，否则会污染后续模块（如 test_int464 的 id 冲突）。
    """
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), '需要文件型 sqlite（跨线程共享表）'
    remove_db_session()
    from audio_service.infrastructure.persistence.models import (
        Audio, AudioAnnotation, AudioTag,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[Audio.__table__, AudioTag.__table__, AudioAnnotation.__table__],
        checkfirst=True,
    )
    yield
    session = get_db_session()
    from audio_service.infrastructure.persistence.models import (
        Audio as _Audio, AudioAnnotation as _Ann, AudioTag as _Tag,
    )
    for model in (_Tag, _Ann, _Audio):
        session.query(model).delete()
    session.commit()
    remove_db_session()


@pytest.fixture()
def repo(db, monkeypatch):
    """每个用例清表 + 重置 user context + 关掉跨服务标签名解析。"""
    from audio_service.infrastructure.persistence.models import (
        Audio, AudioAnnotation, AudioTag,
    )
    from audio_service.infrastructure.persistence.audio_repository import (
        AudioRepository,
    )

    session = get_db_session()
    for model in (AudioTag, AudioAnnotation, Audio):
        session.query(model).delete()
    session.commit()
    remove_db_session()

    set_current_user_id(None)
    set_current_user_is_admin(False)
    monkeypatch.setattr(
        AudioRepository, '_get_tag_name_to_id_map', lambda self, names: {},
        raising=True)
    yield AudioRepository()
    set_current_user_id(None)
    set_current_user_is_admin(False)
    remove_db_session()


def _insert_audio(audio_id, *, owner=None, visibility='shared', size=100,
                  duration=1.0, name=None, created_at=None, **extra):
    from audio_service.infrastructure.persistence.models import Audio
    session = get_db_session()
    po = Audio(
        id=audio_id,
        name=name or f'audio_{audio_id}.wav',
        original_filename=f'src_{audio_id}.wav',
        file_path=f'/tmp/a{audio_id}.wav',
        size=size,
        duration=duration,
        sample_rate=extra.get('sample_rate', 48000),
        channels=extra.get('channels', 2),
        bitrate=extra.get('bitrate', 256000),
        format=extra.get('format', 'wav'),
        audio_type=extra.get('audio_type', 'dry'),
        asr_text=extra.get('asr_text', ''),
        description=extra.get('description', ''),
        md5=extra.get('md5', ''),
        source_language=extra.get('source_language', 'zh'),
        created_by_user_id=owner,
        visibility=visibility,
        **({'created_at': created_at} if created_at is not None else {}),
    )
    session.add(po)
    session.commit()
    remove_db_session()


def _today_start():
    return now_cst().replace(hour=0, minute=0, second=0, microsecond=0)


class _SqlCounter:
    def __init__(self):
        self.statements = []
        self._engine = get_engine()

        def _before(conn, cursor, statement, parameters, context, executemany):
            self.statements.append(' '.join(statement.split()))

        self._before = _before
        event.listen(self._engine, 'before_cursor_execute', _before)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        event.remove(self._engine, 'before_cursor_execute', self._before)
        return False

    @property
    def count(self):
        return len(self.statements)


# ---------------- 旧实现（对照基准，逐行取自改动前代码） ----------------

def _old_list_audios(repo, params):
    """改动前的 list_audios：独立 count + 分页 + 全列水合。"""
    from audio_service.infrastructure.persistence.models import Audio
    from audio_service.infrastructure.persistence._audio_converters import (
        _audio_po_to_entity,
    )
    from audio_service.infrastructure.persistence._audio_query_filters import (
        apply_audio_list_filters,
    )
    from shared.infrastructure.visibility_filter import visible_condition
    from shared.infrastructure.user_context import (
        get_current_user_id, get_current_user_is_admin,
    )

    session = get_db_session()
    query = session.query(Audio).filter_by(deleted=False)
    query = query.filter(visible_condition(
        Audio.created_by_user_id, Audio.visibility,
        get_current_user_id(), get_current_user_is_admin()))
    query = apply_audio_list_filters(
        query, session, params, repo._get_tag_name_to_id_map)
    page = params.get('page', 1)
    per_page = params.get('per_page', 10)
    pagination = query.order_by(Audio.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    pagination.items = [_audio_po_to_entity(po) for po in pagination.items]
    return pagination


def _old_get_audio_stats():
    """改动前的 get_audio_stats：两条聚合 SQL。"""
    from audio_service.infrastructure.persistence.models import Audio
    from shared.infrastructure.visibility_filter import visible_condition
    from shared.infrastructure.user_context import (
        get_current_user_id, get_current_user_is_admin,
    )

    session = get_db_session()
    visible_cond = visible_condition(
        Audio.created_by_user_id, Audio.visibility,
        get_current_user_id(), get_current_user_is_admin())
    stats_result = session.query(
        func.sum(Audio.size), func.sum(Audio.duration),
    ).filter(Audio.deleted == False, visible_cond).first()  # noqa: E712
    today_start = _today_start()
    today_uploads = session.query(func.count(Audio.id)).filter(
        Audio.created_at >= today_start,
        Audio.deleted == False,  # noqa: E712
        visible_cond,
    ).scalar() or 0
    return {
        'total_size': stats_result[0] or 0,
        'total_duration': stats_result[1] or 0,
        'today_uploads': today_uploads,
    }


# ---------------- C2：stats 合并 ----------------

class TestC2StatsMergedSQL:
    def test_single_sql(self, repo):
        _insert_audio(1, size=100, duration=2.0)
        with _SqlCounter() as counter:
            repo.get_audio_stats()
        assert counter.count == 1, counter.statements

    def test_equals_old_two_sql(self, repo):
        now = now_cst()
        _insert_audio(1, size=100, duration=2.0, created_at=_today_start())
        _insert_audio(2, size=250, duration=3.5,
                      created_at=now - timedelta(days=3))
        _insert_audio(3, size=7, duration=0.5,
                      created_at=_today_start() - timedelta(seconds=1))
        _insert_audio(4, size=1000, duration=10.0, visibility='private',
                      owner=99)
        new = repo.get_audio_stats()
        old = _old_get_audio_stats()
        assert new == old
        # 可见行 1/2/3（4 是别人的私有行）；今日只有 1
        assert new['total_size'] == 357
        assert new['today_uploads'] == 1

    def test_empty_table(self, repo):
        stats = repo.get_audio_stats()
        assert stats == {'total_size': 0, 'total_duration': 0,
                         'today_uploads': 0}
        assert stats == _old_get_audio_stats()

    def test_today_zero(self, repo):
        _insert_audio(1, size=10, duration=1.0,
                      created_at=_today_start() - timedelta(days=1))
        stats = repo.get_audio_stats()
        assert stats['today_uploads'] == 0
        assert stats['total_size'] == 10
        assert stats == _old_get_audio_stats()

    def test_day_boundary_inclusive(self, repo):
        """跨日边界：恰好今日零点计入，零点前 1 秒不计。"""
        _insert_audio(1, size=1, duration=1.0, created_at=_today_start())
        _insert_audio(2, size=2, duration=1.0,
                      created_at=_today_start() - timedelta(seconds=1))
        stats = repo.get_audio_stats()
        assert stats['today_uploads'] == 1
        assert stats == _old_get_audio_stats()

    def test_visibility_scope_matches_list(self, repo):
        _insert_audio(1, owner=7, visibility='private', size=100)
        _insert_audio(2, owner=8, visibility='private', size=200)
        _insert_audio(3, owner=8, visibility='shared', size=400)
        set_current_user_id(7)
        set_current_user_is_admin(False)
        assert repo.get_audio_stats() == _old_get_audio_stats()
        assert repo.get_audio_stats()['total_size'] == 500
        set_current_user_is_admin(True)
        assert repo.get_audio_stats()['total_size'] == 700


# ---------------- C3：count 并入分页 ----------------

LIST_CASES = [
    ('无筛选', {'page': 1, 'per_page': 2}),
    ('第二页', {'page': 2, 'per_page': 2}),
    ('末页', {'page': 3, 'per_page': 2}),
    ('超范围页', {'page': 9, 'per_page': 2}),
    ('关键词命中', {'page': 1, 'per_page': 2, 'keyword': 'audio_'}),
    ('关键词无命中', {'page': 1, 'per_page': 2, 'keyword': '__nope__'}),
    ('格式过滤', {'page': 1, 'per_page': 2, 'format_': 'wav'}),
    ('单标签', {'page': 1, 'per_page': 2,
                'tags_data': [{'name': 'tagA', 'mode': 'and'}]}),
    ('多标签_and', {'page': 1, 'per_page': 2,
                    'tags_data': [{'name': 'tagA', 'mode': 'and'},
                                  {'name': 'tagB', 'mode': 'and'}]}),
    ('per_page=1', {'page': 1, 'per_page': 1}),
]


class TestC3CountMergedIntoPage:
    @pytest.fixture()
    def seeded(self, repo, monkeypatch):
        from audio_service.infrastructure.persistence.audio_repository import (
            AudioRepository,
        )
        from audio_service.infrastructure.persistence.models import AudioTag

        now = now_cst()
        # 6 条共享 + 1 条他人私有；created_at 依次递减，排序稳定
        for i in range(1, 7):
            _insert_audio(i, size=10 * i, duration=float(i),
                          name=f'audio_{i}.wav',
                          created_at=now - timedelta(minutes=i))
        _insert_audio(7, owner=99, visibility='private', size=70,
                      name='audio_7.wav', created_at=now)
        session = get_db_session()
        for audio_id, tag_id in [(1, 101), (2, 101), (3, 101), (4, 102)]:
            session.add(AudioTag(audio_id=audio_id, tag_id=tag_id))
        session.commit()
        remove_db_session()
        monkeypatch.setattr(
            AudioRepository, '_get_tag_name_to_id_map',
            lambda self, names: {'tagA': 101, 'tagB': 102}, raising=True)
        return repo

    @pytest.mark.parametrize('case_name,params', LIST_CASES)
    def test_total_and_ids_match_old(self, seeded, case_name, params):
        new = seeded.list_audios(dict(params))
        old = _old_list_audios(seeded, dict(params))
        assert new.total == old.total, case_name
        assert [po.id for po in new.items] == [po.id for po in old.items], case_name
        assert new.pages == old.pages, case_name
        assert new.page == old.page and new.per_page == old.per_page

    def test_empty_result_total_zero(self, seeded):
        pagination = seeded.list_audios(
            {'page': 1, 'per_page': 2, 'keyword': '__nope__'})
        assert pagination.total == 0
        assert pagination.items == []
        assert pagination.pages == 0

    def test_page_out_of_range_keeps_total(self, seeded):
        pagination = seeded.list_audios({'page': 9, 'per_page': 2})
        assert pagination.total == 6
        assert pagination.items == []
        assert pagination.pages == 3

    def test_per_page_zero_keeps_old_semantics(self, seeded):
        new = seeded.list_audios({'page': 1, 'per_page': 0})
        old = _old_list_audios(seeded, {'page': 1, 'per_page': 0})
        assert new.total == old.total == 6
        assert new.items == []
        assert new.pages == 0

    def test_single_sql_for_populated_page(self, seeded):
        with _SqlCounter() as counter:
            seeded.list_audios({'page': 1, 'per_page': 2})
        assert counter.count == 1, counter.statements
        assert '(SELECT count(' in counter.statements[0], counter.statements[0]

    def test_out_of_range_page_falls_back_to_count(self, seeded):
        with _SqlCounter() as counter:
            seeded.list_audios({'page': 9, 'per_page': 2})
        # 空页多 1 次 count 兜底（仅此分支）
        assert counter.count == 2, counter.statements


# ---------------- C4：load_only ----------------

class TestC4LoadOnly:
    def test_unused_columns_not_loaded(self, repo, monkeypatch):
        _insert_audio(1, size=10)
        from audio_service.infrastructure.persistence import audio_repository as mod

        captured = []
        original = mod._audio_po_to_entity

        def _spy(po, *args, **kwargs):
            captured.append(po)
            return original(po, *args, **kwargs)

        monkeypatch.setattr(mod, '_audio_po_to_entity', _spy)
        repo.list_audios({'page': 1, 'per_page': 10})
        assert captured, '未捕获到列表 PO'
        unloaded = set(sa_inspect(captured[0]).unloaded)
        assert {'deleted_at', 'deleted_by_user_id',
                'updated_by_user_id'} <= unloaded
        # deleted 必须仍然加载：_audio_po_to_entity 会读它，裁掉会变 N+1
        assert 'deleted' not in unloaded

    def test_dto_fields_all_present(self, repo):
        from audio_service.application.handlers.audio_query_handler import (
            _audio_to_dict,
        )
        _insert_audio(1, size=10, duration=2.5, name='n.wav')
        pagination = repo.list_audios({'page': 1, 'per_page': 10})
        item = _audio_to_dict(pagination.items[0])
        required = {
            'id', 'name', 'original_filename', 'file_path', 'duration',
            'size', 'sample_rate', 'channels', 'bitrate', 'format',
            'audio_type', 'asr_text', 'description', 'source_language',
            'md5', 'visibility', 'created_by_user_id', 'tags',
            'annotations', 'created_at', 'updated_at',
        }
        assert set(item) == required
        for field in ('id', 'name', 'file_path', 'duration', 'size',
                      'sample_rate', 'channels', 'bitrate', 'format',
                      'audio_type', 'visibility', 'created_at', 'updated_at'):
            assert item[field] is not None, field
        # 实体字段映射（PO 命名差异）不被 load_only 影响
        assert item['name'] == 'n.wav'
        assert item['duration'] == 2.5
        assert item['size'] == 10


# ---------------- 全链路 SQL 条数 ----------------

class TestListAudiosRoundTrips:
    def test_handler_issues_four_sql(self, repo, monkeypatch):
        from audio_service.application.handlers.audio_query_handler import (
            AudioQueryHandler,
        )
        from audio_service.application.queries import ListAudiosQuery
        from audio_service.infrastructure.persistence.audio_repository import (
            AudioRepository,
        )
        from audio_service.infrastructure.persistence.models import (
            AudioAnnotation, AudioTag,
        )

        now = now_cst()
        for i in range(1, 4):
            _insert_audio(i, size=10 * i, created_at=now - timedelta(minutes=i))
        session = get_db_session()
        session.add(AudioTag(audio_id=1, tag_id=101))
        session.add(AudioAnnotation(audio_id=1, format='json', code='c',
                                    data={'a': 1}))
        session.commit()
        remove_db_session()
        monkeypatch.setattr(
            AudioRepository, '_get_tag_id_to_name_map',
            lambda self, ids: {101: 'tagA'}, raising=True)

        handler = AudioQueryHandler(repository=repo)
        with _SqlCounter() as counter:
            result = handler.handle_list_audios(
                ListAudiosQuery(params={'page': 1, 'per_page': 20}))
        assert result['success'], result
        # 改前 6 条（count / 主表 / tags / annotations / sum / 今日 count）
        assert counter.count == 4, counter.statements
        data = result['data']
        assert data['total'] == 3
        assert data['stats']['total_files'] == 3
        assert data['items'][0]['tags'] == ['tagA']


# ---------------- C6：session 生命周期 ----------------

class TestC6SessionLifecycle:
    def test_connection_returned_after_remove(self, repo):
        _insert_audio(1, size=10)
        repo.list_audios({'page': 1, 'per_page': 10})
        engine = get_engine()
        assert engine.pool.checkedout() >= 1
        remove_db_session()
        assert engine.pool.checkedout() == 0

    def test_exception_path_still_rolls_back(self, repo):
        """异常路径：请求收尾仍发一次回滚，连接归还，后续请求不受影响。

        注：sqlite 下语句失败后 DBAPI 已自动回滚，Session 仍处活动中事务，
        所以断言放在「close 时确实发出回滚 + 连接归还 + 下一请求正常」上，
        而不是 Session.is_active（那是 PG 下的表现，由 docker 实测覆盖）。
        """
        from sqlalchemy import text

        _insert_audio(1, size=10)
        engine = get_engine()
        rollbacks = []

        def _on_rb(conn):
            rollbacks.append(1)

        event.listen(engine, 'rollback', _on_rb)
        try:
            session = get_db_session()
            with pytest.raises(Exception):
                session.execute(text('SELECT no_such_column FROM audios'))
            assert engine.pool.checkedout() >= 1
            remove_db_session()
        finally:
            event.remove(engine, 'rollback', _on_rb)
        assert rollbacks, '异常路径未见回滚'
        assert engine.pool.checkedout() == 0
        # 自愈后新查询正常
        assert repo.list_audios({'page': 1, 'per_page': 10}).total == 1
        remove_db_session()
        assert engine.pool.checkedout() == 0
