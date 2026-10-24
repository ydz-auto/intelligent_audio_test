# -*- coding: utf-8 -*-
"""INT-1671 A2：LLM Judge 选项登记表 + 单一判定源（不连库）。

覆盖：
- 真实 `shared/config/llm_judge_options.json` → 1 模型 + 1 模板，各恰一个 is_default；
- 坏 JSON / 缺文件 / 结构不合法 → 空列表且不抛（端点仍可 200）；
- 多项 is_default → 只保留第一个；label 缺省回落 value；
- `ai_review_checker` 与 worker 超时分支与 shared 谓词结果一致（含 id=164 形态 → 120s）。
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import HTTPException

from api_gateway.routes.evaluation_bp import router as evaluation_router

from evaluation_service.application.handlers.ai_review_checker import (
    _is_llm_judge_dimension,
)
from evaluation_service.domain.services.llm_judge_options_registry import (
    DEFAULT_CONFIG_PATH,
    LlmJudgeOptionsRegistry,
)
from evaluation_service.infrastructure.evaluation_api.worker_management import (
    WorkerManagementMixin,
)
from shared.constants.evaluation_dimension import is_llm_judge_dimension

# 覆盖共享谓词的全部形态（含真库存量）
_PREDICATE_CASES = [
    ({'task_type_code': 'llm_judge', 'dimension_type': 'main'}, True),
    ({'task_type_code': 'high_freq_llm_judge', 'dimension_type': 'main'}, True),
    ({'task_type_code': 'turn_taking', 'dimension_type': 'llm_judge'}, True),
    ({'task_type_code': 'algorithm_type', 'dimension_type': 'main'}, False),
    ({'task_type_code': None, 'dimension_type': None}, False),
    ({}, False),
]


# ---------------- 登记表装载 ----------------

def test_real_registry_file_first_version_content():
    """首版口径：只登记 gpt-4o-mini 与 default，各恰一个 is_default=true。"""
    options = LlmJudgeOptionsRegistry(config_path=DEFAULT_CONFIG_PATH).get_options()

    assert [m['value'] for m in options['models']] == ['gpt-4o-mini']
    assert [t['value'] for t in options['prompt_templates']] == ['default']
    assert sum(1 for m in options['models'] if m['is_default']) == 1
    assert sum(1 for t in options['prompt_templates'] if t['is_default']) == 1
    assert all(set(item) == {'value', 'label', 'is_default'}
               for item in options['models'] + options['prompt_templates'])


def test_missing_file_returns_empty_lists(tmp_path):
    options = LlmJudgeOptionsRegistry(
        config_path=str(tmp_path / 'absent.json')).get_options()
    assert options == {'models': [], 'prompt_templates': []}


def test_broken_json_returns_empty_lists(tmp_path):
    path = tmp_path / 'broken.json'
    path.write_text('{not json', encoding='utf-8')
    options = LlmJudgeOptionsRegistry(config_path=str(path)).get_options()
    assert options == {'models': [], 'prompt_templates': []}


def test_non_object_top_level_returns_empty_lists(tmp_path):
    path = tmp_path / 'list.json'
    path.write_text('[1, 2, 3]', encoding='utf-8')
    options = LlmJudgeOptionsRegistry(config_path=str(path)).get_options()
    assert options == {'models': [], 'prompt_templates': []}


def _write(tmp_path, payload):
    path = tmp_path / 'options.json'
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return str(path)


def test_duplicate_default_keeps_first_and_warns(tmp_path, caplog):
    path = _write(tmp_path, {'models': [
        {'value': 'a', 'label': 'A', 'is_default': True},
        {'value': 'b', 'label': 'B', 'is_default': True},
    ]})
    with caplog.at_level('WARNING'):
        models = LlmJudgeOptionsRegistry(config_path=path).get_options()['models']

    assert [(m['value'], m['is_default']) for m in models] == [('a', True), ('b', False)]
    assert any('多个 is_default' in rec.message for rec in caplog.records)


def test_item_validation_label_fallback_and_bad_entries(tmp_path):
    path = _write(tmp_path, {
        'models': [
            {'value': 'gpt-4o-mini'},              # label 缺省回落 value
            {'value': ''},                          # 空 value 丢弃
            {'value': '   '},                       # 空白 value 丢弃
            {'label': 'no-value'},                  # 无 value 丢弃
            'not-an-object',                        # 非对象丢弃
            {'value': 'x', 'label': '', 'is_default': 'yes'},  # label 回落 + 非布尔 default
        ],
        'prompt_templates': None,                   # 缺组 → 空列表
    })
    options = LlmJudgeOptionsRegistry(config_path=path).get_options()

    assert options['models'] == [
        {'value': 'gpt-4o-mini', 'label': 'gpt-4o-mini', 'is_default': False},
        {'value': 'x', 'label': 'x', 'is_default': False},
    ]
    assert options['prompt_templates'] == []


# ---------------- 单一判定源 ----------------

@pytest.mark.parametrize('dim_config,expected', _PREDICATE_CASES)
def test_shared_predicate(dim_config, expected):
    assert is_llm_judge_dimension(**{k: dim_config.get(k)
                                     for k in ('task_type_code', 'dimension_type')}) is expected


@pytest.mark.parametrize('dim_config,expected', _PREDICATE_CASES)
def test_ai_review_checker_uses_same_predicate(dim_config, expected):
    assert _is_llm_judge_dimension(dict(dim_config)) is expected


class _WorkerProbe(WorkerManagementMixin):
    """只探超时选择的替身（不跑 mixin 的 __init__ 初始化链）。"""

    def __init__(self):
        self.endpoint_workers = {}


@pytest.mark.parametrize('dim_config,expected', [
    # id=164 形态：task_type_code 含 llm_judge、dimension_type='main'
    # → 有意行为变更：默认 30 → 120
    ({'task_type_code': 'high_freq_llm_judge', 'dimension_type': 'main',
      'api_settings': {}}, 120),
    # dimension_type 精确命中（历史口径，保持 120）
    ({'task_type_code': None, 'dimension_type': 'llm_judge', 'api_settings': {}}, 120),
    # 维度自带 timeout 优先
    ({'task_type_code': 'llm_judge', 'dimension_type': 'main',
      'api_settings': {'timeout': 45}}, 45),
    # 显式 null api_settings 仍走 LLM 裁判默认
    ({'task_type_code': 'llm_judge', 'dimension_type': 'main',
      'api_settings': None}, 120),
    # 普通维度维持原默认 30
    ({'task_type_code': 'algorithm_type', 'dimension_type': 'main', 'api_settings': {}}, 30),
])
def test_worker_timeout_uses_same_predicate(dim_config, expected):
    assert _WorkerProbe()._get_timeout_from_dim_config(dim_config) == expected


# ---------------- 路由权限 ----------------

def _find_route(path, method='GET'):
    for route in evaluation_router.routes:
        if (getattr(route, 'path', None) == path
                and method in (getattr(route, 'methods', set()) or set())):
            return route
    return None


def test_llm_judge_options_route_requires_evaluation_read():
    """路由挂载 require_permission('evaluation:read')：无权限 → 403。"""
    route = _find_route('/llm-judge/options')
    assert route is not None, 'GET /llm-judge/options 未注册'

    checker = route.dependant.dependencies[0].call
    required = next(
        c.cell_contents for c in (checker.__closure__ or ())
        if isinstance(c.cell_contents, (set, frozenset))
    )
    assert set(required) == {'evaluation:read'}

    req = SimpleNamespace(state=SimpleNamespace(permissions=[]))
    with pytest.raises(HTTPException) as ei:
        checker(req)
    assert ei.value.status_code == 403
