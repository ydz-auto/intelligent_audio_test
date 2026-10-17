# -*- coding: utf-8 -*-
"""INT-577 专项：挑选合并功能升级（统一容器列表 merge_type / 候选补字段 / select-all / 购物车快照）。

覆盖（对齐 UX 规范 18 §11 待后端立项 + 卡验收②）：
- §11-1 统一容器列表：merged=true ∪ cherry_pick=true 并集；merge_type 快捷筛选
  （whole/picked）；容器行 merge_type + source_task_count + source_result_count；
  stats 块（total/whole/picked）
- §11-2 候选行补展示字段：case_name / device_name / api_name / result_type
  （result_data 解析，缺省 default）
- §11-4 select-all：与 candidates 同条件返回命中全部 result_id 集合
- §11-5 购物车快照补 source_result_type（加购 → GET /cart 返回；挑选集同构）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int339 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int577_proc.db')

import pytest
from types import SimpleNamespace

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import set_current_user_id

_TASK_TABLES = None


def _ensure_tables():
    global _TASK_TABLES
    if _TASK_TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TASK_TABLES)
    return _TASK_TABLES


def _cleanup(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture()
def db():
    tables = _ensure_tables()
    _cleanup(tables)
    yield tables
    _cleanup(tables)
    set_current_user_id(None)


def _seed_source_task(name='INT577源任务', status='completed',
                      algorithm_type='asr', result_types=('real-time', 'final')):
    """种子：终态源任务 + 2 用例 2 结果（设备 7/8 各一，result_data 带 result_type）。

    返回 (task_id, [(case_id, result_id, device_id, result_type)...])
    """
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult, TestCase
    session = get_db_session()
    try:
        task = Task(name=name, status=status, total_cases=2,
                    algorithm_type=algorithm_type)
        session.add(task)
        session.flush()
        results = []
        for i, (case_id, device_id) in enumerate([('INT577-C1', 7), ('INT577-C2', 8)]):
            if session.query(TestCase).filter(TestCase.id == case_id).first() is None:
                session.add(TestCase(
                    id=case_id,
                    name=f'INT577用例{i + 1}（{name}）',
                    description='',
                    config={},
                    algorithm_type=algorithm_type,
                ))
            session.add(TaskCase(
                task_id=task.id, test_case_id=case_id,
                status='completed', execution_status='completed',
                evaluation_status='completed', device_type='physical',
                device_id=str(device_id),
            ))
            r_type = result_types[i] if i < len(result_types) else 'default'
            r = TestResult(
                task_id=task.id, test_case_id=case_id, device_id=device_id,
                algorithm_type=algorithm_type, execution_status='completed',
                algorithm_result={'asr_result': f'文本{i}'},
                result_data={'result_type': r_type, 'data': f'd{i}'},
            )
            session.add(r)
            session.flush()
            results.append((case_id, r.id, device_id, r_type))
        session.commit()
        return task.id, results
    finally:
        remove_db_session()


def _seed_plain_task(name='INT577普通任务', status='completed'):
    from task_service.infrastructure.persistence.models import Task
    session = get_db_session()
    try:
        t = Task(name=name, status=status, total_cases=0)
        session.add(t)
        session.commit()
        return t.id
    finally:
        remove_db_session()


# ==================== §11-1 统一容器列表 ====================

def _seed_merge_container():
    """整任务合并容器：源任务A/B（completed）→ merge_tasks → 容器M（completed）。

    返回 (source_a, source_b, merged_id)。
    """
    from task_service.infrastructure.persistence.models import Task, TaskMergeRelation
    from task_service.infrastructure.persistence.task_repository import task_repository
    session = get_db_session()
    try:
        a = Task(name='INT577合并源A', status='completed', total_cases=1, completed_cases=1)
        b = Task(name='INT577合并源B', status='completed', total_cases=1, completed_cases=1)
        session.add_all([a, b])
        session.flush()
        session.commit()
        a_id, b_id = a.id, b.id
        merged_id, _total = task_repository.merge_tasks(
            [a_id, b_id], 'INT577整任务合并容器', '合并容器', created_by=None)
        return a_id, b_id, merged_id
    finally:
        remove_db_session()


def test_search_tasks_union_merge_and_cherry_pick(db):
    """§11-1：merged=true ∪ cherry_pick=true 返回双类容器并集；容器行补 merge_type/source 计数。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    src_a, src_b, merged_id = _seed_merge_container()
    # cherry-pick 容器：经 checkout_merge 下单（source_task 保持 completed，可挑选）
    set_current_user_id(42)
    pick_task_id, results = _seed_source_task('INT577挑选源', status='completed')
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})
    checkout = cherry_pick_service.checkout_merge({'name': 'INT577结果挑选容器'})
    assert checkout['success'] is True
    picked_id = checkout['data']['task_id']
    plain_id = _seed_plain_task()

    result = task_read_model.search_tasks(page=1, per_page=50, merged=True, cherry_pick=True)
    ids = {i['id'] for i in result['items']}
    assert merged_id in ids
    assert picked_id in ids
    assert src_a not in ids and src_b not in ids
    assert plain_id not in ids

    merged_item = next(i for i in result['items'] if i['id'] == merged_id)
    assert merged_item['merge_type'] == 'whole'
    assert merged_item['source_task_count'] == 2
    assert merged_item['source_result_count'] == 2  # 每源 source_result_count=1

    picked_item = next(i for i in result['items'] if i['id'] == picked_id)
    assert picked_item['merge_type'] == 'picked'
    assert picked_item['is_cherry_pick'] is True
    assert picked_item['source_task_count'] == 1
    assert picked_item['source_result_count'] == len(results)

    # 非容器任务无 merge_type（从全量列表取）
    all_result = task_read_model.search_tasks(page=1, per_page=50)
    plain_item = next(i for i in all_result['items'] if i['id'] == plain_id)
    assert plain_item['merge_type'] is None
    assert plain_item['source_task_count'] is None


def test_search_tasks_merge_type_filter(db):
    """§11-1：merge_type=whole / picked 快捷筛选分别命中各自容器族。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _a, _b, merged_id = _seed_merge_container()
    set_current_user_id(42)
    _pick_task_id, results = _seed_source_task('INT577挑选源2', status='completed')
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})
    picked_id = cherry_pick_service.checkout_merge({'name': 'INT577结果挑选容器2'})['data']['task_id']

    whole = task_read_model.search_tasks(page=1, per_page=50, merge_type='whole')
    whole_ids = {i['id'] for i in whole['items']}
    assert merged_id in whole_ids
    assert picked_id not in whole_ids

    picked = task_read_model.search_tasks(page=1, per_page=50, merge_type='picked')
    picked_ids = {i['id'] for i in picked['items']}
    assert picked_id in picked_ids
    assert merged_id not in picked_ids

    both = task_read_model.search_tasks(page=1, per_page=50, merged=True, cherry_pick=True)
    assert {i['id'] for i in both['items']} == {merged_id, picked_id}


def test_search_tasks_stats_block(db):
    """§11-1：stats=true 时返回并集 total / whole / picked 计数；未请求时 stats=None（审计 P2 门控）。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _a, _b, merged_id = _seed_merge_container()
    set_current_user_id(42)
    _pick_task_id, results = _seed_source_task('INT577挑选源3', status='completed')
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})
    picked_id = cherry_pick_service.checkout_merge({'name': 'INT577结果挑选容器3'})['data']['task_id']
    _plain = _seed_plain_task()

    result = task_read_model.search_tasks(page=1, per_page=10, stats=True)
    stats = result['stats']
    assert stats is not None
    assert stats['total'] == 2
    assert stats['whole'] == 1
    assert stats['picked'] == 1

    # 审计 P2 门控：stats=False（日常/已发布/收藏页签缺省）不再执行 3 次 COUNT，
    # stats 返回 None（参数不再形同虚设）
    no_stats = task_read_model.search_tasks(page=1, per_page=10)
    assert no_stats['stats'] is None


# ==================== §11-2 候选行补字段 ====================

def test_candidates_extra_fields(db):
    """§11-2：候选行补 case_name / device_name / api_name / result_type。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    _task_id, results = _seed_source_task('INT577候选源', status='completed',
                                          result_types=('real-time', 'final'))
    resp = cherry_pick_service.list_candidates({'task_ids': [_task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    items = resp['data']['items']
    assert len(items) == 2
    by_case = {it['case_id']: it for it in items}
    c1 = by_case['INT577-C1']
    assert c1['case_name'] == 'INT577用例1（INT577候选源）'
    assert c1['result_type'] == 'real-time'
    assert 'device_name' in c1 and 'api_name' in c1
    c2 = by_case['INT577-C2']
    assert c2['case_name'] == 'INT577用例2（INT577候选源）'
    assert c2['result_type'] == 'final'


def test_candidates_result_type_default(db):
    """§11-2：result_data 缺失 result_type 时缺省 default。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import Task, TestCase, TaskCase, TestResult
    session = get_db_session()
    try:
        task = Task(name='INT577无类型源', status='completed', total_cases=1)
        session.add(task)
        session.flush()
        if session.query(TestCase).filter(TestCase.id == 'INT577-NT').first() is None:
            session.add(TestCase(id='INT577-NT', name='无类型用例', description='', config={}))
        session.add(TaskCase(task_id=task.id, test_case_id='INT577-NT', status='completed',
                             execution_status='completed', evaluation_status='completed'))
        r = TestResult(task_id=task.id, test_case_id='INT577-NT', device_id=9,
                       algorithm_type='asr', execution_status='completed',
                       algorithm_result={'a': 1})  # 无 result_data
        session.add(r)
        session.commit()
        task_id, rid = task.id, r.id
    finally:
        remove_db_session()
    resp = cherry_pick_service.list_candidates({'task_ids': [task_id], 'page': 1, 'per_page': 50})
    assert resp['success'] is True
    item = resp['data']['items'][0]
    assert item['result_id'] == rid
    assert item['result_type'] == 'default'


def test_candidates_case_keyword_hit_and_exclude(db):
    """审计 P1 回归：case_keyword 用例关键字模糊搜索命中/排除（命中用例名或用例 ID，
    与 case_ids 精确 IN 语义区分；网关透传回归见 test_gateway_candidates_payload_passes_case_keyword）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    _task_id, results = _seed_source_task('INT577关键字源', status='completed',
                                          result_types=('real-time', 'final'))
    c1_rid = next(r[1] for r in results if r[0] == 'INT577-C1')
    c2_rid = next(r[1] for r in results if r[0] == 'INT577-C2')

    # 命中用例名关键词 → 仅 C1 行
    hit_name = cherry_pick_service.list_candidates(
        {'task_ids': [_task_id], 'case_keyword': '用例1', 'page': 1, 'per_page': 50})
    assert hit_name['success'] is True
    assert [i['result_id'] for i in hit_name['data']['items']] == [c1_rid]

    # 命中用例 ID 关键词 → 仅 C2 行
    hit_id = cherry_pick_service.list_candidates(
        {'task_ids': [_task_id], 'case_keyword': 'INT577-C2', 'page': 1, 'per_page': 50})
    assert hit_id['success'] is True
    assert [i['result_id'] for i in hit_id['data']['items']] == [c2_rid]

    # 无命中关键词 → 空
    miss = cherry_pick_service.list_candidates(
        {'task_ids': [_task_id], 'case_keyword': 'NOMATCHXYZ', 'page': 1, 'per_page': 50})
    assert miss['success'] is True
    assert miss['data']['items'] == []


# ==================== §11-4 select-all ====================

def test_select_all_result_ids(db):
    """§11-4：select_all 返回当前筛选命中全部 result_id 集合（含多任务跨页语义）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    t1, r1 = _seed_source_task('INT577全选源A', status='completed', result_types=('a', 'b'))
    t2, r2 = _seed_source_task('INT577全选源B', status='completed', result_types=('c', 'd'))
    _plain = _seed_plain_task()

    resp = cherry_pick_service.list_candidates({'select_all': True})
    assert resp['success'] is True
    assert sorted(resp['data']['result_ids']) == sorted(r[1] for r in r1 + r2)

    # 带筛选：仅源A
    resp_a = cherry_pick_service.list_candidates({'select_all': True, 'task_ids': [t1]})
    assert resp_a['success'] is True
    assert sorted(resp_a['data']['result_ids']) == sorted(r[1] for r in r1)


# ==================== §11-5 购物车快照 source_result_type ====================

def test_cart_snapshot_source_result_type(db):
    """§11-5：加购快照补 source_result_type；GET /cart 与挑选集同构返回。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    set_current_user_id(42)
    _task_id, results = _seed_source_task('INT577购物车源', status='completed',
                                          result_types=('real-time', 'final'))
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})

    cart = cherry_pick_service.cart_get()
    assert cart['success'] is True
    items = cart['data']['groups'][0]['items']
    by_case = {it['source_case_id']: it for it in items}
    assert by_case['INT577-C1']['source_result_type'] == 'real-time'
    assert by_case['INT577-C2']['source_result_type'] == 'final'
    # INT-577 §11-5 可选补名：来源用例名（任务服务内 test_cases 可直查）；
    # 设备表不归属本服务，设备名缺省 None（前端容错显示 ID）
    assert by_case['INT577-C1']['source_case_name'] == 'INT577用例1（INT577购物车源）'
    assert 'source_device_name' in by_case['INT577-C1']
    assert by_case['INT577-C1']['source_device_name'] is None

    # 挑选集快照同构
    save = cherry_pick_service.cart_save_as_set({'name': 'INT577集'})
    assert save['success'] is True
    sets = cherry_pick_service.sets_list()['data']['items']
    set_id = sets[0]['set_id']
    detail = cherry_pick_service.set_detail(set_id)['data']
    assert len(detail['items']) == 2
    assert {it['source_result_type'] for it in detail['items']} == {'real-time', 'final'}


# ==================== 网关契约回归（§11-1 stats/merge_type 查询参数） ====================

def test_gateway_task_list_query_accepts_int577_params():
    """§11-1 网关契约回归：TaskListQuery 必须接受 stats / merge_type 参数。

    APIModel extra=ignore 会静默丢弃未声明字段；若 schema 缺字段，服务侧
    query.stats 将 AttributeError → 500。此用例锁定前端下发参数可解析。
    """
    from api_gateway.schemas.task import TaskListQuery

    q = TaskListQuery.model_validate({
        'stats': 'true', 'merge_type': 'whole', 'merged': True, 'cherry_pick': True,
    })
    assert q.stats is True
    assert q.merge_type == 'whole'
    assert q.merged is True and q.cherry_pick is True

    q2 = TaskListQuery.model_validate({'stats': True, 'merge_type': 'picked'})
    assert q2.stats is True
    assert q2.merge_type == 'picked'


# ==================== 审计 P1 网关链路 case_keyword 回归 ====================

class _State:
    def __init__(self, json_body):
        self._json_body = json_body
        self.username = ''


class _FakeRequest:
    def __init__(self, query_params):
        # request_adapter._QueryParams 接受 dict（else 分支 multi_items 探测）
        self.query_params = dict(query_params)
        self.state = _State(None)


def test_gateway_candidates_payload_passes_case_keyword(monkeypatch):
    """网关链路回归（审计 P1 阻断项）：CherryPickCandidatesQuery 接受 case_keyword，
    list_candidates 组装 payload 透传 case_keyword（对齐 select_all_candidates 口径），
    不再被 pydantic extra=ignore 静默丢弃——前端「搜索用例名称或 ID」恢复生效。
    """
    from api_gateway.schemas.cherry_pick import CherryPickCandidatesQuery

    # ① schema 契约：case_keyword 字段必须可解析（缺字段时 pydantic extra=ignore 静默丢参）
    q = CherryPickCandidatesQuery.model_validate({
        'task_ids': '7,8', 'case_keyword': 'INT577-C1',
    })
    assert q.case_keyword == 'INT577-C1'

    # ② 网关服务 payload 组装：case_keyword 透传（含空白清洗为 None，与 select-all 同口径）
    from api_gateway.infrastructure import request_adapter
    import api_gateway.application.services.task.cherry_pick_service as gw_cp

    captured = {}

    def _list_candidates(payload):
        captured['payload'] = dict(payload)
        return {'success': True, 'message': 'ok',
                'data': {'items': [], 'total': 0, 'page': 1, 'per_page': 50}}

    monkeypatch.setattr(gw_cp, '_cherry_pick_acl', SimpleNamespace(list_candidates=_list_candidates))

    request_adapter.set_current_request(_FakeRequest({
        'task_ids': '7,8', 'case_keyword': 'INT577-C1',
    }))
    try:
        resp, _http = gw_cp.CherryPickService.list_candidates()
        assert resp['success'] is True
        assert captured['payload']['case_keyword'] == 'INT577-C1'
        assert captured['payload']['task_ids'] == [7, 8]
    finally:
        request_adapter.set_current_request(None)

    # 空白关键词清洗为 None（与 select_all_candidates 同口径，不传空串）
    request_adapter.set_current_request(_FakeRequest({'case_keyword': '   '}))
    try:
        gw_cp.CherryPickService.list_candidates()
        assert captured['payload']['case_keyword'] is None
    finally:
        request_adapter.set_current_request(None)
