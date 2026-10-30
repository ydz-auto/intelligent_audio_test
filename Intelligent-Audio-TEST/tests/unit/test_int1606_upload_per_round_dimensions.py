# -*- coding: utf-8 -*-
"""INT-1606 验收 — 上传/批量导入生成用例的逐轮评估维度写侧支持（R1~R6）。

原缺陷：`_build_config_and_apply_dimensions` 只要顶层 `dimensions` 为真，就把同一份
逐轮维度**无条件写进每一轮**（且各轮共享同一 list 引用），`rounds[i].evaluation.dimensions`
被抹平成同一套；轮的维度归属丢失，前端「所有 / 指定 / 逐轮」三档中的后两档无法落库。

修订口径（INT-1607 评审 Q1~Q3 / S1~S10）：

- 任一轮自带 `evaluation.dimensions`（list，显式 `[]` 也算）→ 整体以载荷为准（R1）；
  未自带轮写 `[]`，顶层逐轮维度一律忽略；顶层 multi 仍并入 `config.dimensions`。
- 所有轮都未自带 → 顶层维度回填每一轮，行为与改动前一致（R2，唯一有意变化：
  `round_scope='per_round'` 由「被丢弃」改为「按逐轮写入」，S7）。
- 轮内 `round_scope='multi'` 一律归并进 `config.dimensions` 并从轮内移除（R3/S2）。
- 无顶层维度且无轮自带 → 只补缺失轮的 `[]`（R4）。
- 容错：轮内 `dimensions` 非 list、`evaluation: null`、轮 item 非 dict 均不抛异常（R5）。
- 结构不变：rounds 不增删不重排，不新增字段（R6）。

另含 A4 评测链冒烟：用写侧产出的 config 调读侧 `_merge_dimensions_config`，
`round_number=None` 入口等于「顶层 multi ∪ 轮内 multi」按 id 去重，单轮入口只出该轮逐轮集合。
"""
import copy
import os

# BaseConfig 在 import 时校验环境变量（纯单测不触库/OSS，仓库既有测试同款兜底）
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.schemas.testcase import (
    TestCaseAudioConfigItem,
    TestCaseDetailData,
    TestCaseDimensionBrief,
)
from api_gateway.utils.response import success_response
from audio_service.application.services._creation_round_config_mixin import (
    CreationRoundConfigMixin,
)
from evaluation_service.domain.services.evaluation_service.case_loader import (
    CaseLoaderMixin,
)
from task_service.application.testcase.testcase_query_service import TestCaseQueryService

DT_HTTP = 'http_api'
DT_PHYSICAL = 'physical'
_UNSET = object()


class _Svc(CreationRoundConfigMixin):
    """只取维度写侧方法的最小实例（不触 repo / DB）。"""


class _Loader(CaseLoaderMixin):
    """只取维度读侧方法的最小实例（不触 repo / DB）。"""


def _dim(dim_id, **kwargs):
    d = {'id': dim_id}
    d.update(kwargs)
    return d


def _round(round_number, evaluation=_UNSET):
    item = {'round_number': round_number, 'audios': [{'audio_name': f'r{round_number}.wav'}]}
    if evaluation is not _UNSET:
        item['evaluation'] = evaluation
    return item


def _build(rounds, dimensions_data=None, device_type=DT_HTTP):
    svc = _Svc()
    return svc._build_config_and_apply_dimensions(
        _audio(), rounds, dimensions_data, device_type, 0, None,
    )


def _audio():
    from types import SimpleNamespace
    return SimpleNamespace(id=42, name='a.wav')


def _round_dims(config, idx):
    return config['rounds'][idx]['evaluation']['dimensions']


def _ids(dims):
    return [d.get('id') for d in dims]


# ==== A1 单测（12 条） ====

def test_a1_1_all_rounds_same_dimension_set():
    """所有轮次（3 轮同一套）→ 每轮维度相同、顺序保持。"""
    dims = [_dim(11, name='字准'), _dim(12, name='句准')]
    rounds = [_round(1, {'dimensions': copy.deepcopy(dims)}),
              _round(2, {'dimensions': copy.deepcopy(dims)}),
              _round(3, {'dimensions': copy.deepcopy(dims)})]

    config = _build(rounds, {'dimensions': []})

    assert _ids(_round_dims(config, 0)) == [11, 12]
    assert _ids(_round_dims(config, 1)) == [11, 12]
    assert _ids(_round_dims(config, 2)) == [11, 12]
    assert 'dimensions' not in config


def test_a1_2_selected_rounds_not_backfilled_from_top_level():
    """指定轮次：未选中轮省略 evaluation.dimensions，顶层逐轮非空也不回填（S1）。"""
    rounds = [
        _round(1, {'dimensions': [_dim(11)]}),
        _round(2, {'enabled': True}),
        _round(3, {'enabled': True}),
    ]

    config = _build(rounds, [_dim(11), _dim(12)])

    assert _ids(_round_dims(config, 0)) == [11]
    assert _round_dims(config, 1) == []
    assert _round_dims(config, 2) == []
    assert 'dimensions' not in config


def test_a1_3_per_round_distinct_dimensions():
    """逐轮设置（各轮不同）→ 各轮与载荷逐条一致。"""
    rounds = [
        _round(1, {'dimensions': [_dim(11), _dim(12)]}),
        _round(2, {'dimensions': [_dim(21)]}),
        _round(3, {'dimensions': [_dim(11), _dim(31)]}),
    ]

    config = _build(rounds)

    assert _ids(_round_dims(config, 0)) == [11, 12]
    assert _ids(_round_dims(config, 1)) == [21]
    assert _ids(_round_dims(config, 2)) == [11, 31]


def test_a1_4_backfill_compat_without_round_override():
    """回填兼容：无轮自带 + 顶层逐轮 [A,B] + multi [C] → 每轮 [A,B]、config.dimensions=[C]。"""
    rounds = [_round(1), _round(2)]
    top = [_dim(1), _dim(2), _dim(9, round_scope='multi')]

    config = _build(rounds, top)

    assert _ids(_round_dims(config, 0)) == [1, 2]
    assert _ids(_round_dims(config, 1)) == [1, 2]
    assert _ids(config['dimensions']) == [9]
    assert _round_dims(config, 0) is not _round_dims(config, 1)


def test_a1_5_backfill_compat_per_round_scope_entry():
    """回填兼容：顶层 round_scope='per_round' 条目按逐轮写入（改前被丢弃，S7）。"""
    rounds = [_round(1), _round(2)]
    top = [_dim(1), _dim(3, round_scope='per_round')]

    config = _build(rounds, top)

    assert _ids(_round_dims(config, 0)) == [1, 3]
    assert _ids(_round_dims(config, 1)) == [1, 3]
    assert 'dimensions' not in config


def test_a1_6_device_type_filter_and_no_backfill_into_empty_round():
    """device_type 作用域过滤：各设备类型各留各的；只有 physical 条目的轮在 http_api 下为 []，不回填顶层（S5）。"""
    payload = [
        _round(1, {'dimensions': [_dim(11, device_type=DT_HTTP), _dim(12, device_type=DT_PHYSICAL)]}),
        _round(2, {'dimensions': [_dim(13, device_type=DT_PHYSICAL)]}),
    ]
    top = [_dim(21, device_type=DT_HTTP), _dim(22, device_type=DT_PHYSICAL),
           _dim(91, device_type=DT_PHYSICAL, round_scope='multi')]

    api_config = _build(copy.deepcopy(payload), copy.deepcopy(top), device_type=DT_HTTP)
    assert _ids(_round_dims(api_config, 0)) == [11]
    assert _round_dims(api_config, 1) == []
    assert 'dimensions' not in api_config

    e2e_config = _build(copy.deepcopy(payload), copy.deepcopy(top), device_type=DT_PHYSICAL)
    assert _ids(_round_dims(e2e_config, 0)) == [12]
    assert _ids(_round_dims(e2e_config, 1)) == [13]
    assert _ids(e2e_config['dimensions']) == [91]


def test_a1_6b_top_level_per_round_dimensions_ignored_with_warning(caplog):
    """R1：顶层逐轮维度一律忽略并记 WARNING（含 audio / device_type 标识）。"""
    rounds = [_round(1, {'dimensions': [_dim(11)]})]

    with caplog.at_level('WARNING'):
        config = _build(rounds, [_dim(12)])

    assert _ids(_round_dims(config, 0)) == [11]
    assert 'dimensions' not in config
    assert any('忽略顶层逐轮维度' in rec.getMessage() for rec in caplog.records)


def test_a1_7_round_level_dedupe_keeps_order():
    """轮内重复 (id, round_scope) 去重且保序。"""
    rounds = [_round(1, {'dimensions': [_dim(11), _dim(12), _dim(11), _dim(13), _dim(12)]})]

    config = _build(rounds)

    assert _ids(_round_dims(config, 0)) == [11, 12, 13]


def test_a1_8_round_dimensions_not_a_list_treated_as_not_self_provided():
    """轮内 dimensions 非 list（None / dict）→ 视同未自带并写 []，不抛异常（S3/R5）。"""
    rounds = [
        _round(1, {'dimensions': [_dim(11)]}),
        _round(2, {'dimensions': None}),
        _round(3, {'dimensions': {'id': 12}}),
    ]

    config = _build(rounds, [_dim(21)])

    assert _ids(_round_dims(config, 0)) == [11]
    assert _round_dims(config, 1) == []
    assert _round_dims(config, 2) == []


def test_a1_9_evaluation_null_normalized_to_dict():
    """evaluation: null 的轮 → 归一为 {} 后写 []，不抛异常（S3）。"""
    rounds = [_round(1, {'dimensions': [_dim(11)]}), _round(2, None)]

    config = _build(rounds)

    assert _ids(_round_dims(config, 0)) == [11]
    assert config['rounds'][1]['evaluation'] == {'dimensions': []}


def test_a1_10_round_level_multi_merged_into_config_dimensions():
    """轮内 round_scope='multi' → 归并进 config.dimensions（顶层在前、轮序追加、按 id 去重），轮内不残留。"""
    rounds = [
        _round(1, {'dimensions': [_dim(11), _dim(91, name='整体WER', round_scope='multi')]}),
        _round(2, {'dimensions': [_dim(92, round_scope='multi'), _dim(91, name='整体WER', round_scope='multi')]}),
    ]
    top = [_dim(90, round_scope='multi'), _dim(11)]

    config = _build(rounds, top)

    assert _ids(_round_dims(config, 0)) == [11]
    assert _round_dims(config, 1) == []
    assert _ids(config['dimensions']) == [90, 91, 92]


def test_a1_11_bare_id_normalized():
    """裸 id（int）条目 → 归一为 {'id': n}。"""
    rounds = [_round(1, {'dimensions': [11, _dim(12), 'garbage']})]

    config = _build(rounds)

    assert _round_dims(config, 0) == [{'id': 11}, _dim(12)]


def test_a1_12_other_evaluation_keys_preserved_and_rounds_untouched():
    """轮内 evaluation 其它键原样保留；rounds 数组长度与顺序不变。"""
    rounds = [
        _round(1, {'enabled': True, 'dimensions': [_dim(11, weight=0.6, threshold=60,
                                                       llmJudgeConfig={'model': 'm'})]}),
        _round(2, {'enabled': False, 'dimensions': []}),
        _round(3, {'enabled': True}),
    ]

    config = _build(rounds)

    round1_eval = config['rounds'][0]['evaluation']
    assert round1_eval['enabled'] is True
    assert round1_eval['dimensions'][0]['weight'] == 0.6
    assert round1_eval['dimensions'][0]['threshold'] == 60
    assert round1_eval['dimensions'][0]['llmJudgeConfig'] == {'model': 'm'}
    assert config['rounds'][1]['evaluation']['enabled'] is False
    assert config['rounds'][2]['evaluation'] == {'enabled': True, 'dimensions': []}
    assert [r['round_number'] for r in config['rounds']] == [1, 2, 3]
    assert len(config['rounds']) == 3
    assert config['rounds'] is rounds


def test_a1_13_empty_top_level_dimensions_is_not_backfill_source():
    """顶层 `{'dimensions': []}` 是真值 dict 但视同无顶层维度（S6），不覆盖轮内既有配置。"""
    rounds = [_round(1, {'dimensions': [_dim(11)]}), _round(2)]

    config = _build(rounds, {'dimensions': []})

    assert config['rounds'][1]['evaluation'] == {'dimensions': []}


def test_a1_14_non_dict_round_item_skipped():
    """轮 item 非 dict → 跳过，不抛异常（R5）。"""
    rounds = [_round(1, {'dimensions': [_dim(11)]}), 'not-a-dict']

    config = _build(rounds)

    assert _ids(_round_dims(config, 0)) == [11]
    assert config['rounds'][1] == 'not-a-dict'


def test_a1_15_r4_branch_non_list_round_dimensions_normalized():
    """R4 分支（无顶层维度且无轮自带）：轮内非 list 维度归一为 []，不把脏形态落库（R5 / 审计 P2-1）。"""
    rounds = [
        _round(1, {'dimensions': None}),
        _round(2, {'dimensions': {'id': 11}}),
        _round(3, {'enabled': True}),
    ]

    config = _build(rounds)

    assert config['rounds'][0]['evaluation']['dimensions'] == []
    assert config['rounds'][1]['evaluation']['dimensions'] == []
    assert config['rounds'][2]['evaluation'] == {'enabled': True, 'dimensions': []}
    assert 'dimensions' not in config
    # 读侧不炸：脏形态若原样落库，_merge_dimensions_config 迭代 None 会抛 TypeError
    assert _merge(config, 0) == []
    assert _merge(config, 1) == []


def test_a1_16_top_level_multi_device_type_filter_before_dedupe():
    """顶层 multi 桶按「归一化 → device_type 过滤 → 去重」：同 id 先 physical 后 http_api 时 http_api 用例仍保留该条目（R3 / 审计 P3-1）。"""
    rounds = [_round(1, {'dimensions': [_dim(11)]})]
    top = [_dim(91, device_type=DT_PHYSICAL, round_scope='multi'),
           _dim(91, device_type=DT_HTTP, round_scope='multi')]

    config = _build(rounds, top, device_type=DT_HTTP)

    assert _ids(config['dimensions']) == [91]
    assert config['dimensions'][0]['device_type'] == DT_HTTP


# ==== A4 评测链冒烟（纯 py，读侧不变量） ====

def _merge(config, round_number):
    return _Loader()._merge_dimensions_config(config, round_number=round_number)


def test_a4_read_side_merge_invariants():
    """写侧产物 → 读侧：整体入口 = 顶层 multi ∪ 轮内 multi 去重；单轮入口只出该轮逐轮集合。"""
    rounds = [
        _round(1, {'dimensions': [_dim(11), _dim(91, name='整体WER', round_scope='multi')]}),
        _round(2, {'dimensions': [_dim(12), _dim(92, round_scope='multi')]}),
        _round(3, {'enabled': True}),
    ]
    top = [_dim(90, round_scope='multi')]

    config = _build(rounds, top)

    overall = _merge(config, None)
    assert _ids(overall) == [90, 91, 92]
    # 整体入口 == 「顶层 multi ∪ 轮内 multi」按 id 去重（单一口径，无重复计分）
    assert _ids(overall) == _ids(config['dimensions'])

    assert _ids(_merge(config, 0)) == [11]
    assert _ids(_merge(config, 1)) == [12]
    assert _merge(config, 2) == []


def test_a4_backfill_compat_chain_unchanged():
    """回填口径（无轮自带）下读侧两入口仍与改前一致。"""
    rounds = [_round(1), _round(2)]
    top = [_dim(1), _dim(2), _dim(9, round_scope='multi')]

    config = _build(rounds, top)

    assert _ids(_merge(config, None)) == [9]
    assert _ids(_merge(config, 0)) == [1, 2]
    assert _ids(_merge(config, 1)) == [1, 2]


# ==== A2 回显（真实 task_service 详情序列化器 + 网关 DTO → 客户端 JSON） ====
# 复刻网关 get_one：TestCaseQueryService.get_testcase_detail（config 原样返回）
# → TestCaseDetailData（TestCaseConfig 校验）→ success_response。不连库、不起栈，
# 验证「写侧落库的 config 经回显链路逐条不变」。

class _FakeGroup:
    id = 'g-int1606'
    name = '默认分组'


class _FakeTag:
    def __init__(self, name):
        self.name = name


class _FakeTC:
    def __init__(self, tc_id, config):
        self.id = tc_id
        self.name = '多轮用例'
        self.description = None
        self.group_id = 'g-int1606'
        self.group = _FakeGroup()
        self.config = config
        self.algorithm_params = None
        self.reference_params = None
        self.algorithm_type = 'asr'
        self.tags = [_FakeTag('回归')]
        self.created_at = None
        self.updated_at = None


class _FakeReadRepo:
    DIMS = {
        11: {'id': 11, 'name': '字准', 'type': 'accuracy'},
        12: {'id': 12, 'name': '句准', 'type': 'accuracy'},
        21: {'id': 21, 'name': '时延', 'type': 'latency'},
        90: {'id': 90, 'name': '整体分', 'type': 'overall'},
        91: {'id': 91, 'name': '整体WER', 'type': 'overall'},
    }

    def __init__(self, tc):
        self.tc = tc

    def get_testcase(self, tc_id):
        return self.tc if tc_id == self.tc.id else None

    def get_audio_by_id(self, audio_id):
        return {'id': audio_id, 'name': f'音频{audio_id}', 'duration': 2.0}

    def list_dimensions_by_ids(self, ids):
        return [self.DIMS[i] for i in ids if i in self.DIMS]


def _gateway_get_detail_body(config):
    """复刻网关 GET /api/v1/testcases/{id}：详情 → TestCaseDetailData → 客户端 JSON。"""
    tc = _FakeTC('c-int1606', config)
    result = TestCaseQueryService(_FakeReadRepo(tc)).get_testcase_detail(tc.id)
    assert result['success'], result
    item = result['data']
    detail = TestCaseDetailData(
        id=item['id'], name=item['name'], description=item['description'],
        group_id=item['group_id'], group_name=item['group_name'], group=item['group'],
        config=item['config'] or {},
        algorithm_params=item['algorithm_params'],
        reference_params=item['reference_params'],
        algorithm_type=item['algorithm_type'], tags=item['tags'],
        audios=[TestCaseAudioConfigItem(
            id=a['id'], audio_id=a['audio_id'], audio_name=a['audio_name'],
            spl=a['spl'],
            playback_device_id=a['playback_device_id'], play_order=a['play_order'],
        ) for a in item['audios']],
        dimensions=[TestCaseDimensionBrief(id=d['id'], name=d['name'], type=d['type'])
                    for d in item['dimensions']],
        created_at=item['created_at'], updated_at=item['updated_at'],
        total_duration=item['total_duration'],
    )
    payload, _ = success_response(detail)
    return payload['data']


def test_a2_echo_per_round_payload():
    """逐轮载荷：回显 config 与载荷按 tt 匹配、去重、保序逐条一致；multi 落 config.dimensions。"""
    rounds = [
        _round(1, {'dimensions': [_dim(11, weight=0.6, threshold=60,
                                       llmJudgeConfig={'model': 'm', 'promptTemplate': 't'}),
                                  _dim(91, name='整体WER', round_scope='multi')]}),
        _round(2, {'dimensions': [_dim(12)]}),
        _round(3, {'dimensions': [_dim(11), _dim(11)]}),
    ]
    config = _build(rounds, [_dim(21)])

    wire = _gateway_get_detail_body(config)
    echo_rounds = wire['config']['rounds']

    assert len(echo_rounds) == 3
    assert [r['round_number'] for r in echo_rounds] == [1, 2, 3]
    assert _ids(echo_rounds[0]['evaluation']['dimensions']) == [11]
    assert _ids(echo_rounds[1]['evaluation']['dimensions']) == [12]
    assert _ids(echo_rounds[2]['evaluation']['dimensions']) == [11]
    # 轮内多出来的 weight / threshold / llmJudgeConfig 原样透传
    echo_dim = echo_rounds[0]['evaluation']['dimensions'][0]
    assert echo_dim['weight'] == 0.6
    assert echo_dim['threshold'] == 60
    assert echo_dim['llmJudgeConfig'] == {'model': 'm', 'promptTemplate': 't'}
    # 轮内 multi 归并到顶层 config.dimensions
    assert [d['id'] for d in wire['config']['dimensions']] == [91]
    # 顶层逐轮维度在载荷自带时被忽略
    assert 21 not in [d['id'] for r in echo_rounds
                      for d in r['evaluation']['dimensions']]


def test_a2_echo_selected_rounds_payload():
    """指定载荷：未选中轮回显 []，不被顶层维度回填；顶层 multi 仍回显在 config.dimensions。"""
    rounds = [
        _round(1, {'dimensions': [_dim(11), _dim(12)]}),
        _round(2, {'enabled': True}),
        _round(3, {'enabled': True}),
    ]
    config = _build(rounds, [_dim(11), _dim(12), _dim(90, name='整体分', round_scope='multi')])

    wire = _gateway_get_detail_body(config)
    echo_rounds = wire['config']['rounds']

    assert _ids(echo_rounds[0]['evaluation']['dimensions']) == [11, 12]
    assert echo_rounds[1]['evaluation']['dimensions'] == []
    assert echo_rounds[2]['evaluation']['dimensions'] == []
    assert echo_rounds[1]['evaluation']['enabled'] is True
    assert [d['id'] for d in wire['config']['dimensions']] == [90]

