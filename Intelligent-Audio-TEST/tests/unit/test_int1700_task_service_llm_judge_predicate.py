# -*- coding: utf-8 -*-
"""INT-1700：task_service 的 LLM Judge 维度过滤改调 shared 单一判定源。

覆盖：
- `dimension_type='llm_judge_x'`（子串命中，旧内联精确等值会漏）→ 判 True 并被收进结果；
- 普通维度（algorithm_type/main）→ 判 False，不收入；
- task_type_code 子串命中 / None / 空串 / 非 dict 项 / id 缺失 的容错；
- 该文件不再出现内联 `'llm_judge' in ...` / `== 'llm_judge'` 判定（锁回归）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from task_service.infrastructure.acl import evaluation_config_acl_repository as acl_mod
from task_service.infrastructure.acl.evaluation_config_acl_repository import (
    EvaluationConfigAclRepository,
)

_ACL_SOURCE = os.path.abspath(acl_mod.__file__)


def _patch_dimensions(monkeypatch, items):
    monkeypatch.setattr(
        EvaluationConfigAclRepository, 'list_dimensions',
        lambda self, page=1, per_page=1000: {'total': len(items), 'items': items},
    )


def test_dimension_type_substring_true(monkeypatch):
    """INT-1700 核心：dimension_type='llm_judge_x' 旧口径漏判，shared 口径判 True。"""
    _patch_dimensions(monkeypatch, [
        {'id': 201, 'task_type_code': 'turn_taking', 'dimension_type': 'llm_judge_x'},
    ])
    assert EvaluationConfigAclRepository().list_llm_judge_dimension_ids() == [201]


def test_plain_dimension_false(monkeypatch):
    """普通维度（algorithm_type/main）不是 LLM 判分维度。"""
    _patch_dimensions(monkeypatch, [
        {'id': 301, 'task_type_code': 'algorithm_type', 'dimension_type': 'main'},
        {'id': 302, 'task_type_code': None, 'dimension_type': ''},
        {'id': 303},
        {'task_type_code': 'llm_judge'},          # id 缺失 → 跳过
        'not-a-dict',
    ])
    assert EvaluationConfigAclRepository().list_llm_judge_dimension_ids() == []


def test_real_dimension_shapes(monkeypatch):
    """真库存量形态：task_type_code 子串命中 + 普通维度混排。"""
    _patch_dimensions(monkeypatch, [
        {'id': 164, 'task_type_code': 'high_freq_llm_judge', 'dimension_type': 'main'},
        {'id': 165, 'task_type_code': 'llm_judge', 'dimension_type': 'main'},
        {'id': 166, 'task_type_code': 'turn_taking', 'dimension_type': 'llm_judge'},
        {'id': 167, 'task_type_code': 'algorithm_type', 'dimension_type': 'main'},
    ])
    assert EvaluationConfigAclRepository().list_llm_judge_dimension_ids() == [164, 165, 166]


def test_no_inline_llm_judge_matching_in_acl_source():
    """验收：该文件不再出现内联 'llm_judge' in ... / == 'llm_judge'。"""
    with open(_ACL_SOURCE, encoding='utf-8') as f:
        source = f.read()
    assert "'llm_judge' in" not in source
    assert '"llm_judge" in' not in source
    assert "== 'llm_judge'" not in source
    assert '== "llm_judge"' not in source
