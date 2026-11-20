# -*- coding: utf-8 -*-
"""INT-2465 无编造数值：30 条抽样任务，0 例编造。

跑真实 Loop（``AgentEvalRunner`` → ``build_container`` → ContextAssembler →
持久化），模型与工具是确定性替身；每条答案必须与工具返回的同一事实逐字段
相等，且不等于数据集里给的反例值。任何不一致都记为失败：
``answer_mismatch`` / ``tool_return_mismatch`` / ``fabricated_value``。
"""
import io
import json
import os

from tests.agent_eval.harness import expected_truth
from tests.agent_eval.runner import AgentEvalRunner

DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'datasets')
DATASET = 'no_fabrication_tasks.json'
TOTAL = 30


def _load_tasks():
    with io.open(os.path.join(DATASET_DIR, DATASET), encoding='utf-8') as handle:
        return json.load(handle)['tasks']


def test_dataset_truth_matches_deterministic_tools():
    """抽检集本身与替身工具数据一致，防止评测集漂移。"""
    tasks = _load_tasks()
    assert len(tasks) == TOTAL
    assert len({task['id'] for task in tasks}) == TOTAL
    for task in tasks:
        assert expected_truth(task['fact_key']) == str(task['expected_value'])
        assert str(task['expected_value']) not in (
            task.get('forbidden_values') or [])
        assert task['prompt'] and task['tool'] and task['arguments']


def test_dataset_has_twenty_numeric_facts():
    """卡面要求抽检「数值」：20 条数值 + 10 条枚举状态。"""
    numeric = [task for task in _load_tasks()
               if str(task['expected_value']).replace('.', '', 1).isdigit()]
    assert len(numeric) == 20


def test_thirty_sampled_tasks_have_no_fabricated_values(tmp_path):
    runner = AgentEvalRunner(str(tmp_path))
    metrics = runner.run_golden(DATASET, dataset_dir=DATASET_DIR)
    assert metrics.total == TOTAL
    assert metrics.failures == [], metrics.failures
    assert metrics.passed == TOTAL
    assert not [f for f in metrics.failures
                if f.get('reason') == 'fabricated_value']
