# -*- coding: utf-8 -*-
"""INT-2454 评测基座验收（卡面可测标准 1 / 4）。

- 10 条 golden tasks 全通过，且答案与工具真实返回逐字段一致、无编造数值；
- 60 轮跨域长任务：压缩前后成功率差 ≤ 5 个百分点，事实召回率 ≥ 95%；
- 压缩确实发生（每次压缩一条 agent_context_snapshot）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from tests.agent_eval.runner import AgentEvalRunner


def test_eval_baseline_acceptance(tmp_path):
    runner = AgentEvalRunner(str(tmp_path / 'work'))
    report = runner.run_all()

    assert report.golden.total == 10
    assert report.golden.passed == 10, report.golden.failures

    compressed = report.compressed
    assert compressed.rounds >= 50
    assert compressed.compaction_count > 0
    assert compressed.fact_recall_rate >= 0.95
    assert compressed.run_failures == 0
    assert report.success_delta_points <= 5.0
    assert report.acceptance['passed'] is True

    # INT-2490：50+ 轮会话里的长期记忆召回命中率（8 轮跨会话记忆事实），
    # 命中即答案与工具返回逐字段一致，不存在编造数值。
    assert compressed.memory_rounds >= 8
    assert compressed.memory_correct == compressed.memory_rounds
    assert compressed.memory_hit_rate >= 0.95
    assert report.acceptance['memory_recall_ge_95'] is True

    paths = report.write(str(tmp_path / 'out'))
    payload = json.load(open(paths['json'], encoding='utf-8'))
    assert payload['long_task']['compressed']['compaction_count'] > 0
    assert payload['long_task']['compressed']['memory_hit_rate'] >= 0.95
    assert payload['acceptance']['passed'] is True
    markdown = open(paths['markdown'], encoding='utf-8').read()
    assert '压缩前后成功率差' in markdown
    assert '事实召回率' in markdown
    assert '记忆检索命中率' in markdown


def test_dataset_truth_matches_tool_data():
    """评测集与工具替身数据逐字段一致（防止评测集漂移）。"""
    from tests.agent_eval.runner import _assert_dataset_truth, _load_json
    _assert_dataset_truth(_load_json('golden_tasks.json')['tasks'], id_key='id')
    _assert_dataset_truth(_load_json('long_task.json')['rounds'], id_key='round')
