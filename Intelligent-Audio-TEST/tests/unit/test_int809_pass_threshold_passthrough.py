# -*- coding: utf-8 -*-
"""INT-809：评估维度输出字段（output_fields）透传 pass_threshold。

验证 evaluation_service 三处透传闭环：
1. _save_output_params 构造 add_dimension_param dict 时携带 pass_threshold
   （创建/更新共用此函数，带值落值、不带落 None）；
2. algorithm gRPC 返回 dict → dict_list_to_dto → DimensionParamDTO 映射 pass_threshold；
3. _serialize_dimension_param 序列化回显 pass_threshold。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from evaluation_service.application.commands._dimension_params_mixin import (
    DimensionParamsMixin,
)
from evaluation_service.application.queries.evaluation_query_service import (
    EvaluationQueryService,
)
from evaluation_service.domain.dto.evaluation_acl_dto import DimensionParamDTO
from shared.utils.dto_utils import dict_list_to_dto


class FakeRepo:
    """记录 add_dimension_param 收到的 dict，便于断言透传字段。"""

    def __init__(self):
        self.created = []

    def add_dimension_param(self, data):
        self.created.append(data)
        return 1


def _make_mixin(repo):
    m = DimensionParamsMixin()
    m.repo = repo
    return m


def test_save_output_params_carries_pass_threshold():
    repo = FakeRepo()
    mixin = _make_mixin(repo)
    mixin._save_output_params(10, [
        {'param_code': 'wer', 'param_name': 'WER',
         'agg_role': 'pass_le', 'pass_threshold': 0.1},
        {'param_code': 'acc', 'param_name': '准确率',
         'agg_role': 'pass_ge', 'pass_threshold': 0.9},
    ])
    assert len(repo.created) == 2
    assert repo.created[0]['param_code'] == 'wer'
    assert repo.created[0]['pass_threshold'] == 0.1
    assert repo.created[1]['pass_threshold'] == 0.9
    assert repo.created[1]['agg_role'] == 'pass_ge'


def test_save_output_params_omitting_pass_threshold_lands_none():
    repo = FakeRepo()
    mixin = _make_mixin(repo)
    mixin._save_output_params(10, [
        {'param_code': 'wer', 'param_name': 'WER', 'agg_role': 'value'},
    ])
    assert len(repo.created) == 1
    assert repo.created[0]['pass_threshold'] is None


def test_dimension_param_dto_maps_pass_threshold():
    data = {'params': [
        {'id': 1, 'param_code': 'wer', 'param_direction': 'output',
         'agg_role': 'pass_le', 'pass_threshold': 0.1},
        {'id': 2, 'param_code': 'acc', 'param_direction': 'output',
         'agg_role': 'pass_ge'},
    ]}
    dtos = dict_list_to_dto(data, DimensionParamDTO, list_key='params')
    assert len(dtos) == 2
    assert dtos[0].pass_threshold == 0.1
    assert dtos[1].pass_threshold is None


def test_serialize_dimension_param_echoes_pass_threshold():
    param = DimensionParamDTO(
        id=1, dimension_id=10, param_code='wer', param_direction='output',
        agg_role='pass_le', field_type='number', pass_threshold=0.1,
    )
    out = EvaluationQueryService._serialize_dimension_param(param)
    assert out['param_code'] == 'wer'
    assert out['pass_threshold'] == 0.1

    param_none = DimensionParamDTO(
        id=2, dimension_id=10, param_code='acc', param_direction='output',
        agg_role='value', pass_threshold=None,
    )
    out_none = EvaluationQueryService._serialize_dimension_param(param_none)
    assert out_none['pass_threshold'] is None


def test_po_roundtrip_persists_pass_threshold():
    """算法库 PO 直接落库验证：带值落值、不带落 NULL（对应验收 1）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from algorithm_service.infrastructure.persistence._algorithm_query_repositories import (
        _po_to_dict,
    )
    from algorithm_service.infrastructure.persistence.models.algorithm_models import (
        Base,
        EvaluationDimensionParam,
    )

    engine = create_engine('sqlite:///:memory:',
                           connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine, tables=[EvaluationDimensionParam.__table__])
    session = sessionmaker(bind=engine)()
    try:
        p_with = EvaluationDimensionParam(**{
            'dimension_id': 10, 'param_code': 'wer', 'param_direction': 'output',
            'agg_role': 'pass_le', 'pass_threshold': 0.1,
        })
        p_without = EvaluationDimensionParam(**{
            'dimension_id': 10, 'param_code': 'acc', 'param_direction': 'output',
            'agg_role': 'value',
        })
        session.add_all([p_with, p_without])
        session.commit()
        assert p_with.pass_threshold == 0.1
        assert p_without.pass_threshold is None
        assert _po_to_dict(p_with).get('pass_threshold') == 0.1
        assert _po_to_dict(p_without).get('pass_threshold') is None
    finally:
        session.close()
        engine.dispose()
