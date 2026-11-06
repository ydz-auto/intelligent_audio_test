# -*- coding: utf-8 -*-
"""INT-823：evaluation_service LLM 复检 gRPC（AiReviewCheck）单测。

验收标准：
- mock LLM 端点返回，核对上下文聚合（ASR/参考文本/维度分/LLM 评语）与
  verdict/confidence/reasoning 回写契约。

测试设计：
- 真实 sqlite 内存库建 test_result_dimensions + dimensions 表，seed TRD 行；
- gRPC 层：直接调 EvaluationDataServiceServicer.AiReviewCheck，mock 维度配置
  加载与 LLM 端点返回（_call_llm_judge），核对数据面契约；
- 上下文聚合：捕获传给 _call_llm_judge 的 context，核对 ASR/参考文本/维度分/LLM 评语；
- 判定派生：_derive_verdict 直接断言（passed/failed/uncertain + confidence）；
- 端点调用构造：注入 mock api_client 走真实 _call_llm_judge，核对 body_template
  渲染与 make_api_request_with_fallback 参数。
"""
import json
import os
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import evaluation_service.infrastructure.persistence.evaluation_dimension_repository as repo_mod
from evaluation_service.application.handlers.ai_review_checker import (
    AiReviewChecker,
    ai_review_checker,
)
from evaluation_service.interfaces.grpc.evaluation_data_servicer import (
    EvaluationDataServiceServicer,
)
from shared.models.database import remove_db_session as _remove_db_session
from shared.utils.status_constants import EvaluationStatus

_remove_db_session()

# ==================== 测试库 fixture ====================

# INT-1809（C2）：原始报文已外置——单测用内存对象存储承载「对象」，行上只写指针
# （与生产路径共用 apply_pointer / RawPayloadStore 同一套口径）。
_MEMORY_OBJECTS = {}


def _mem_upload(data, key):
    _MEMORY_OBJECTS[key] = data
    return f'oss://case_result/{key}'


def _mem_download(uri):
    return _MEMORY_OBJECTS[uri.split('case_result/', 1)[1]]


def _memory_store():
    from shared.infrastructure.raw_payload_store import RawPayloadStore
    return RawPayloadStore(uploader=_mem_upload, downloader=_mem_download)


@pytest.fixture()
def trd_db(monkeypatch):
    """真实内存 SQLite 引擎 + test_result_dimensions + dimensions 表。"""
    _MEMORY_OBJECTS.clear()
    store = _memory_store()
    monkeypatch.setattr(repo_mod, 'raw_payload_store', store)
    import evaluation_service.infrastructure.persistence._result_group_mixin as grm_mod
    monkeypatch.setattr(grm_mod, 'raw_payload_store', store)
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.schema import CreateTable
    from evaluation_service.infrastructure.persistence.orm_models import (
        TestResultDimension,
        Dimension,
    )

    engine = create_engine(
        'sqlite://', connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )

    def _ddl(model):
        ddl = str(CreateTable(model.__table__).compile(engine))
        # SQLite 仅对 INTEGER PRIMARY KEY 做行ID别名自增（生产库 BIGINT 无此约束）
        return ddl.replace('id BIGINT NOT NULL', 'id INTEGER NOT NULL', 1)

    with engine.connect() as conn:
        conn.execute(text(_ddl(Dimension)))
        conn.execute(text(_ddl(TestResultDimension)))
        conn.commit()
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(repo_mod, 'get_db_session', factory)
    return factory


def _insert_dim(factory, dim_id, name='LLM语义评分', task_type_code='llm_judge',
                dimension_type='main'):
    from evaluation_service.infrastructure.persistence.orm_models import Dimension
    session = factory()
    try:
        po = Dimension(
            id=dim_id, name=name, dimension_type=dimension_type,
            task_type_code=task_type_code, type='auto', result_type=1,
            result_min=0.0, result_max=5.0, weight=1, sort_order=0,
            estimated_exec_time=10, rule={}, api_settings={}, status=True,
            deleted=False, api_status='online', api_endpoints=[], api_url=None,
            score_unit='分', statistic_method='average', created_at=None,
            updated_at=None,
        )
        session.add(po)
        session.commit()
        return po.id
    finally:
        session.close()


def _insert_trd(factory, result_id=99, dimension_id=7, evaluation_status=EvaluationStatus.COMPLETED,
                score=4.2, req_body=None, raw_resp=None, **kwargs):
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    from shared.infrastructure.raw_payload_store import (
        KIND_REQUEST,
        KIND_RESPONSE,
        apply_pointer,
    )
    session = factory()
    try:
        po = TestResultDimension(
            test_result_id=result_id, dimension_id=dimension_id,
            algorithm_type='voice_llm', round_number=kwargs.get('round_number'),
            dimension_value=kwargs.get('dimension_value', score),
            score=score, status=kwargs.get('status'),
            evaluation_status=evaluation_status, error_message=kwargs.get('error_message'),
        )
        # INT-1809（C2）：报文进对象存储，行上只留指针（JSON 两列保持 NULL）
        store = _memory_store()
        apply_pointer(po, KIND_REQUEST,
                      store.store(KIND_REQUEST, req_body) if req_body is not None else None)
        apply_pointer(po, KIND_RESPONSE,
                      store.store(KIND_RESPONSE, raw_resp) if raw_resp is not None else None)
        session.add(po)
        session.commit()
        return po.id
    finally:
        session.close()


def _make_dim_config(dim_id=7, threshold=3.0, task_type_code='llm_judge',
                     result_min=0.0, result_max=5.0, name='LLM语义评分'):
    """构造复检维度配置（dim_dict 形状，供 _load_dim_config mock / 直接注入）。"""
    return {
        'id': dim_id,
        'name': name,
        'result_min': result_min,
        'result_max': result_max,
        'rule': {},
        'api_endpoints': [{'url': 'http://mock-llm:8888', 'name': 'Master'}],
        'api_settings': {
            'method': 'POST',
            'headers': {'content_type': 'application/json'},
            'body_template': {'model': '{{model}}', 'prompt': '{{prompt}}'},
        },
        'api_url': 'http://mock-llm:8888',
        'dimension_type': 'main',
        'parent_dimension_id': None,
        'task_type_code': task_type_code,
        'output_params': [
            {'param_code': 'llm_judge_score', 'field_path': 'llm_judge_score',
             'field_type': 'number', 'agg_role': 'value', 'output_role': 'main',
             'pass_threshold': threshold},
            {'param_code': 'reasoning', 'field_path': 'reasoning',
             'field_type': 'text', 'agg_role': None, 'output_role': 'aux',
             'pass_threshold': None},
        ],
        'input_params': [
            {'param_code': 'answer', 'default_value': None, 'field_type': 'text',
             'required': False},
            {'param_code': 'correct_answer', 'default_value': None,
             'field_type': 'text', 'required': False},
        ],
    }


def _servicer():
    return EvaluationDataServiceServicer()


def _check_resp(resp):
    assert resp.success, resp.message
    return json.loads(resp.data)


# ==================== gRPC 复检：verdict/confidence/reasoning ====================


class TestAiReviewCheckGrpc:

    def test_passed_verdict(self, trd_db, monkeypatch):
        """LLM 端点返回高分 → verdict=passed + confidence + reasoning 回写契约。"""
        _insert_dim(trd_db, 7)
        _insert_trd(trd_db, dimension_id=7, score=4.2,
                    req_body={'answer': '设备回答', 'correct_answer': '参考答案',
                              'question': '设备提问', 'query': '用户提问', 'prompt': 'p'},
                    raw_resp={'reasoning': '旧评语'})
        monkeypatch.setattr(ai_review_checker, '_load_dim_config',
                            lambda dim_id: _make_dim_config(7, threshold=3.0))
        monkeypatch.setattr(ai_review_checker, '_call_llm_judge',
                            lambda *a, **k: {'llm_judge_score': 4.2,
                                             'reasoning': '语义正确流畅'})

        resp = _servicer().AiReviewCheck(
            MagicMock(result_id=99, dimension_id=7, task_id=10, test_case_id='c1'))
        data = _check_resp(resp)
        assert data['verdict'] == 'passed'
        assert data['confidence'] == 0.6  # (4.2-3.0)/(5-3)
        assert data['reasoning'] == '语义正确流畅'

    def test_failed_verdict(self, trd_db, monkeypatch):
        """LLM 端点返回低分 → verdict=failed。"""
        _insert_dim(trd_db, 7)
        _insert_trd(trd_db, dimension_id=7, score=1.5,
                    req_body={'answer': 'a', 'correct_answer': 'r'},
                    raw_resp={'reasoning': '旧评语'})
        monkeypatch.setattr(ai_review_checker, '_load_dim_config',
                            lambda dim_id: _make_dim_config(7, threshold=3.0))
        monkeypatch.setattr(ai_review_checker, '_call_llm_judge',
                            lambda *a, **k: {'llm_judge_score': 1.5,
                                             'reasoning': '回答偏离参考'})

        resp = _servicer().AiReviewCheck(
            MagicMock(result_id=99, dimension_id=7, task_id=10, test_case_id='c1'))
        data = _check_resp(resp)
        assert data['verdict'] == 'failed'
        assert data['confidence'] == 0.5  # (3.0-1.5)/(3-0)
        assert data['reasoning'] == '回答偏离参考'

    def test_uncertain_when_main_score_missing(self, trd_db, monkeypatch):
        """LLM 响应无主评分 → verdict=uncertain，不落 confidence。"""
        _insert_dim(trd_db, 7)
        _insert_trd(trd_db, dimension_id=7,
                    req_body={'answer': 'a'}, raw_resp={'reasoning': '旧评语'})
        monkeypatch.setattr(ai_review_checker, '_load_dim_config',
                            lambda dim_id: _make_dim_config(7, threshold=3.0))
        monkeypatch.setattr(ai_review_checker, '_call_llm_judge',
                            lambda *a, **k: {'reasoning': '无法判定'})

        resp = _servicer().AiReviewCheck(
            MagicMock(result_id=99, dimension_id=7, task_id=10, test_case_id='c1'))
        data = _check_resp(resp)
        assert data['verdict'] == 'uncertain'
        assert data['confidence'] is None
        assert data['reasoning'] == '无法判定'

    def test_default_dimension_picks_first_llm_judge(self, trd_db, monkeypatch):
        """dimension_id=0：取首个已完成评估的 LLM 判分维度（跳过非 LLM 维度）。"""
        _insert_dim(trd_db, 6, name='WER', task_type_code='wer')
        _insert_dim(trd_db, 7)
        _insert_trd(trd_db, dimension_id=6, score=0.1, req_body={})
        _insert_trd(trd_db, dimension_id=7, score=4.2, req_body={})

        def fake_load(dim_id):
            if dim_id == 6:
                return _make_dim_config(6, task_type_code='wer', name='WER')
            return _make_dim_config(7, threshold=3.0)

        called = {}

        def fake_call(dim_config, context, task_id=None, test_case_id=None, **k):
            called['dim_id'] = dim_config['id']
            return {'llm_judge_score': 4.2, 'reasoning': '复检通过'}

        monkeypatch.setattr(ai_review_checker, '_load_dim_config', fake_load)
        monkeypatch.setattr(ai_review_checker, '_call_llm_judge', fake_call)

        resp = _servicer().AiReviewCheck(
            MagicMock(result_id=99, dimension_id=0, task_id=10, test_case_id='c1'))
        data = _check_resp(resp)
        assert data['verdict'] == 'passed'
        assert called['dim_id'] == 7

    def test_no_llm_judge_dimension(self, trd_db, monkeypatch):
        """结果只有非 LLM 维度且未显式指定 → success=False。"""
        _insert_dim(trd_db, 6, name='WER', task_type_code='wer')
        _insert_trd(trd_db, dimension_id=6, score=0.1, req_body={})
        monkeypatch.setattr(ai_review_checker, '_load_dim_config',
                            lambda dim_id: _make_dim_config(dim_id, task_type_code='wer',
                                                            name='WER'))

        resp = _servicer().AiReviewCheck(
            MagicMock(result_id=99, dimension_id=0, task_id=10, test_case_id='c1'))
        assert not resp.success
        assert '未找到可复检的 LLM 判分维度' in resp.message

    def test_no_dimension_records(self, trd_db, monkeypatch):
        """结果无维度评估记录 → success=False。"""
        resp = _servicer().AiReviewCheck(
            MagicMock(result_id=999, dimension_id=0, task_id=10, test_case_id='c1'))
        assert not resp.success
        assert '无维度评估记录' in resp.message

    def test_endpoint_error(self, trd_db, monkeypatch):
        """LLM 端点调用失败（__error__）→ success=False，不落判定。"""
        _insert_dim(trd_db, 7)
        _insert_trd(trd_db, dimension_id=7, req_body={'answer': 'a'})
        monkeypatch.setattr(ai_review_checker, '_load_dim_config',
                            lambda dim_id: _make_dim_config(7))
        monkeypatch.setattr(ai_review_checker, '_call_llm_judge',
                            lambda *a, **k: {'__error__': 'LLM 端点不可达'})

        resp = _servicer().AiReviewCheck(
            MagicMock(result_id=99, dimension_id=7, task_id=10, test_case_id='c1'))
        assert not resp.success
        assert 'LLM 端点不可达' in resp.message


# ==================== 上下文聚合 ====================


class TestContextAggregation:

    def test_aggregates_asr_ref_score_reasoning(self, trd_db, monkeypatch):
        """核对聚合：ASR（answer/question）/参考文本（correct_answer/query）/
        维度分（score）/LLM 评语（api_raw_response.reasoning）进 context。"""
        _insert_dim(trd_db, 7)
        _insert_trd(trd_db, dimension_id=7, score=3.8,
                    req_body={'answer': '设备回答文本', 'correct_answer': '参考答案文本',
                              'question': '设备识别提问', 'query': '用户提问原文',
                              'prompt': '评估提示词', 'model': 'gpt-test'},
                    raw_resp={'reasoning': '原 LLM 评语', 'criteria_scores': {'acc': 1}})
        monkeypatch.setattr(ai_review_checker, '_load_dim_config',
                            lambda dim_id: _make_dim_config(7, threshold=3.0))

        captured = {}

        def fake_call(dim_config, context, task_id=None, test_case_id=None, **k):
            captured['context'] = context
            return {'llm_judge_score': 4.0, 'reasoning': '新评语'}

        monkeypatch.setattr(ai_review_checker, '_call_llm_judge', fake_call)

        _servicer().AiReviewCheck(
            MagicMock(result_id=99, dimension_id=7, task_id=10, test_case_id='c1'))

        ctx = captured['context']
        assert ctx['answer'] == '设备回答文本'          # ASR 设备回答
        assert ctx['question'] == '设备识别提问'        # ASR 设备识别提问
        assert ctx['correct_answer'] == '参考答案文本'  # 参考文本
        assert ctx['query'] == '用户提问原文'          # 参考文本
        assert ctx['current_score'] == 3.8            # 维度分
        assert ctx['current_reasoning'] == '原 LLM 评语'  # LLM 评语
        assert ctx['prompt'] == '评估提示词'
        assert ctx['model'] == 'gpt-test'


# ==================== 端点调用构造（复用 llm_judge 端点 worker 与维度配置） ====================


class TestCallLlmJudge:

    def test_builds_payload_and_calls_api_client(self):
        """注入 mock api_client：核对 body_template 渲染 + make_api_request_with_fallback 参数。"""
        checker = AiReviewChecker()
        api_client = MagicMock()
        api_client.build_payload.return_value = {'model': 'gpt-test', 'prompt': 'p'}
        api_client.make_api_request_with_fallback.return_value = (
            'http://mock-llm:8888', {'llm_judge_score': 4.0})

        dim_config = _make_dim_config(7, threshold=3.0)
        context = {'answer': 'a', 'correct_answer': 'r', 'model': 'gpt-test', 'prompt': 'p'}

        resp = checker._call_llm_judge(
            dim_config, context, task_id=10, test_case_id='c1',
            api_client=api_client)

        assert resp == {'llm_judge_score': 4.0}
        # body_template 渲染走 api_client.build_payload（复用 llm_judge 维度配置）
        api_client.build_payload.assert_called_once_with(
            {'model': '{{model}}', 'prompt': '{{prompt}}'}, context,
            task_id=10, test_case_id='c1', algorithm_type='llm_judge')
        api_client.make_api_request_with_fallback.assert_called_once()
        kwargs = api_client.make_api_request_with_fallback.call_args.kwargs
        assert kwargs['endpoints'] == [{'url': 'http://mock-llm:8888', 'name': 'Master'}]
        assert kwargs['method'] == 'POST'
        assert kwargs['payload'] == {'model': 'gpt-test', 'prompt': 'p'}
        assert kwargs['api_url'] == 'http://mock-llm:8888'
        assert kwargs['task_id'] == 10
        assert kwargs['test_case_id'] == 'c1'

    def test_no_endpoint_config(self):
        """维度未配置端点 → __error__，不调用 api_client。"""
        checker = AiReviewChecker()
        api_client = MagicMock()
        dim_config = _make_dim_config(7)
        dim_config['api_endpoints'] = []
        dim_config['api_url'] = None
        resp = checker._call_llm_judge(dim_config, {}, task_id=None,
                                       test_case_id=None, api_client=api_client)
        assert '__error__' in resp
        api_client.make_api_request_with_fallback.assert_not_called()


# ==================== 判定派生纯逻辑 ====================


class TestDeriveVerdict:

    def test_passed_with_configured_threshold(self):
        checker = AiReviewChecker()
        verdict, conf, reasoning = checker._derive_verdict(
            {'llm_judge_score': 4.0, 'reasoning': '通过'}, _make_dim_config(7, threshold=3.0))
        assert verdict == 'passed'
        assert conf == 0.5  # (4.0-3.0)/(5-3)
        assert reasoning == '通过'

    def test_failed_with_default_threshold_midpoint(self):
        """无 pass_threshold → 缺省取结果区间中点（0-5 → 2.5）。"""
        checker = AiReviewChecker()
        cfg = _make_dim_config(7, threshold=None)
        verdict, conf, reasoning = checker._derive_verdict(
            {'llm_judge_score': 1.0, 'reasoning': '失败'}, cfg)
        assert verdict == 'failed'
        assert conf == 0.6  # (2.5-1.0)/2.5
        assert reasoning == '失败'

    def test_uncertain_when_score_missing(self):
        checker = AiReviewChecker()
        verdict, conf, reasoning = checker._derive_verdict(
            {'reasoning': '无法判定'}, _make_dim_config(7, threshold=3.0))
        assert verdict == 'uncertain'
        assert conf is None

    def test_reasoning_fallback_top_level(self):
        """reasoning 输出参数未配置 field_path 时兜底取响应顶层。"""
        checker = AiReviewChecker()
        cfg = _make_dim_config(7, threshold=3.0)
        cfg['output_params'] = [
            {'param_code': 'llm_judge_score', 'field_path': 'llm_judge_score',
             'output_role': 'main', 'pass_threshold': 3.0},
        ]
        verdict, conf, reasoning = checker._derive_verdict(
            {'llm_judge_score': 3.5, 'reasoning': '顶层评语'}, cfg)
        assert verdict == 'passed'
        assert reasoning == '顶层评语'


# ==================== 查询层 include_body 透传 ====================


class TestQueryIncludeBody:

    def test_include_body_returns_request_and_response(self, trd_db):
        """GetDimensionResultsByResultIds 带 include_body=True 回传 api_request_body/api_raw_response。"""
        _insert_dim(trd_db, 7)
        trd_id = _insert_trd(
            trd_db, dimension_id=7,
            req_body={'answer': 'a', 'correct_answer': 'r'},
            raw_resp={'reasoning': '旧评语'})

        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        resp = evaluation_query_service.get_dimension_results_by_result_ids(
            [99], include_body=True)
        assert resp['success']
        items = resp['data']['items']
        assert len(items) == 1
        assert items[0]['id'] == trd_id
        assert items[0]['api_request_body']['answer'] == 'a'
        assert items[0]['api_raw_response']['reasoning'] == '旧评语'

    def test_default_no_body(self, trd_db):
        """默认 include_body=False：不回传大 JSON 字段（既有消费方载荷不变）。"""
        _insert_dim(trd_db, 7)
        _insert_trd(trd_db, dimension_id=7, req_body={'answer': 'a'},
                    raw_resp={'reasoning': 'r'})

        from evaluation_service.application.queries.evaluation_query_service import (
            evaluation_query_service,
        )
        resp = evaluation_query_service.get_dimension_results_by_result_ids([99])
        items = resp['data']['items']
        assert len(items) == 1
        assert 'api_request_body' not in items[0]
        assert 'api_raw_response' not in items[0]
