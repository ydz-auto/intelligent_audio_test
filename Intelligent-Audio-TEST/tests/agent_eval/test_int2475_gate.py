# -*- coding: utf-8 -*-
"""INT-2475 五层评测门禁自测（不跑 Docker 的重活；沙箱 / 压缩由门禁命令覆盖）。

覆盖：

1. 五层登记、评测集版本化（version 必须存在）；
2. Skill 层通过 + 失败集合精确到 ``skill:<name>``（故意改坏一个 Skill）；
3. 端到端层跑真实 Loop（确定性模型/工具替身）通过且成本可观测；
4. 报告 schema（层结果 / 失败集合 / 数据集版本 / 成本 / 退出码）；
5. JUnit 解析（pytest 层的通过 / 失败 / 跳过计数）。
"""
import io
import json
import os
import shutil

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from tests.agent_eval import gate


# ---------------------------------------------------------------- 登记 / 版本

def test_five_layers_are_registered():
    assert gate.LAYER_ORDER == (
        'e2e', 'skill', 'compaction', 'sandbox', 'recovery')
    assert set(gate.LAYER_TITLES) == set(gate.LAYER_ORDER)


def test_eval_datasets_are_versioned():
    versions = gate.dataset_versions()
    assert set(versions) == {
        'tests/agent_eval/datasets/e2e_cross_domain.json',
        'tests/agent_eval/datasets/golden_tasks.json',
        'tests/agent_eval/coverage/datasets/no_fabrication_tasks.json',
        'tests/agent_eval/coverage/datasets/skill_trigger_tasks.json',
        'tests/agent_eval/datasets/long_task.json',
    }
    for info in versions.values():
        assert isinstance(info['version'], int) and info['version'] >= 1


def test_dataset_versions_rejects_unversioned_file(tmp_path, monkeypatch):
    path = tmp_path / 'noversion.json'
    path.write_text(json.dumps({'tasks': []}), encoding='utf-8')
    monkeypatch.setattr(gate, 'datasets_for', lambda layer: [str(path)])
    with pytest.raises(gate.EvalInfraError):
        gate.dataset_versions()


def test_e2e_manifest_members_exist():
    members = gate.e2e_datasets()
    assert len(members) == 2
    assert all(os.path.isfile(path) for path in members)


# ---------------------------------------------------------------- Skill 层

def test_skill_layer_passes_for_all_14_skills():
    result = gate.run_skill_layer()
    assert result.status == 'passed', result.failures
    metrics = result.metrics
    assert metrics['skills_evaluated'] == 14
    assert metrics['tasks'] == 140
    assert metrics['overall_accuracy'] >= gate.SKILL_TRIGGER_THRESHOLD
    assert all(item['ok'] for item in metrics['per_skill'].values())


def test_skill_layer_scopes_to_requested_skills():
    result = gate.run_skill_layer(skills=['audio-import'])
    assert result.status == 'passed'
    assert list(result.metrics['per_skill']) == ['audio-import']


def test_skill_layer_names_set_when_skill_missing():
    result = gate.run_skill_layer(skills=['not-a-skill'])
    assert result.status == 'failed'
    assert [item['set'] for item in result.failures] == ['skill:not-a-skill']


def test_broken_skill_fails_gate_and_names_the_set(tmp_path):
    """卡面验收 3：故意改坏一个 Skill，门禁失败并指出具体集合。"""
    root = tmp_path / 'skills'
    shutil.copytree(os.path.join(gate.PROJECT_ROOT, 'skills'), root)
    skill_file = root / 'audio-import' / 'SKILL.md'
    text = skill_file.read_text(encoding='utf-8')
    start = text.index('触发词：')
    end = text.find('\n', start)
    skill_file.write_text(
        text[:start] + '触发词：无关词汇甲、无关词汇乙。' + text[end:],
        encoding='utf-8')
    result = gate.run_skill_layer(skills=['audio-import'],
                                  skills_root=str(root))
    assert result.status == 'failed'
    assert [item['set'] for item in result.failures] == ['skill:audio-import']
    assert any('L1' in item['detail'] for item in result.failures)


def test_skill_layer_flags_skill_with_fewer_than_ten_tasks(monkeypatch):
    monkeypatch.setattr(gate, '_load_skill_tasks',
                        lambda: {'audio-import': [{'query': '音频列表'}]})
    result = gate.run_skill_layer(skills=['audio-import'])
    assert result.status == 'failed'
    assert result.failures[0]['set'] == 'skill:audio-import'
    assert 'golden tasks' in result.failures[0]['detail']


# ---------------------------------------------------------------- E2E 层

def test_e2e_layer_runs_real_loop_and_reports_cost():
    result = gate.run_e2e_layer()
    assert result.status == 'passed', result.failures
    metrics = result.metrics
    assert metrics['tasks'] == 40
    assert metrics['success_rate'] == 1.0
    assert metrics['fabricated_values'] == 0
    assert metrics['permission_violations'] == []
    assert metrics['tool_selection_rate'] == 1.0
    # 成本可观测：模型轮次 / 工具调用 / 近似 token 均有值
    assert result.cost['llm_calls'] > 0
    assert result.cost['tool_calls'] == 40
    assert result.cost['approx_prompt_tokens'] > 0


# ---------------------------------------------------------------- 报告

def _fake_report(*statuses):
    layers = {}
    for name, status in zip(gate.LAYER_ORDER, statuses):
        layer = gate.LayerResult(name=name, status=status)
        if status == 'failed':
            layer.fail(f'{name}:set', 'boom')
        layers[name] = layer
    return gate.GateReport(
        started_at=gate.datetime.now(gate.timezone.utc),
        duration_seconds=1.5, layers=layers,
        changed_skills=['audio-import'],
        dataset_versions=gate.dataset_versions())


def test_report_schema_and_exit_codes():
    passed = _fake_report('passed', 'passed', 'passed', 'passed', 'passed')
    payload = passed.to_dict()
    assert payload['gate'] == 'INT-2475'
    assert payload['passed'] is True and payload['exit_code'] == 0
    assert set(payload['layers']) == set(gate.LAYER_ORDER)
    assert payload['changed_skills'] == ['audio-import']
    assert payload['dataset_versions']
    assert payload['cost']['wall_seconds'] == 1.5

    failed = _fake_report('failed', 'passed', 'passed', 'passed', 'passed')
    assert failed.exit_code == 1 and not failed.passed
    assert failed.failures() == [
        {'layer': 'e2e', 'set': 'e2e:set', 'detail': 'boom'}]

    unavailable = _fake_report('passed', 'passed', 'passed', 'unavailable',
                               'passed')
    assert unavailable.exit_code == 2 and not unavailable.passed


def test_report_writes_json_and_markdown(tmp_path):
    report = _fake_report('passed', 'passed', 'passed', 'passed', 'passed')
    paths = report.write(str(tmp_path))
    payload = json.loads(io.open(paths['json'], encoding='utf-8').read())
    assert payload['exit_code'] == 0
    markdown = io.open(paths['markdown'], encoding='utf-8').read()
    assert '评测门禁报告' in markdown
    assert '| 项 | 门槛 | 结论 |' in markdown


# ---------------------------------------------------------------- 工具函数

def test_parse_junit_counts_statuses(tmp_path):
    xml = """<?xml version="1.0"?><testsuites><testsuite>
      <testcase classname="a" name="ok" time="0.1"/>
      <testcase classname="a" name="bad" time="0.2"><failure/></testcase>
      <testcase classname="a" name="err" time="0.3"><error/></testcase>
      <testcase classname="a" name="skip" time="0.0"><skipped/></testcase>
    </testsuite></testsuites>"""
    path = tmp_path / 'junit.xml'
    path.write_text(xml, encoding='utf-8')
    cases = gate._parse_junit(str(path))
    statuses = {case['name']: case['status'] for case in cases}
    assert statuses['a::ok'] == 'passed'
    assert statuses['a::bad'] == 'failed'
    assert statuses['a::err'] == 'error'
    assert statuses['a::skip'] == 'skipped'


def test_skill_names_from_repo_relative_paths():
    names = gate._skill_names_from_paths([
        'Intelligent-Audio-TEST/skills/audio-import/SKILL.md',
        'skills/tag-group/references/x.md',
        'Intelligent-Audio-TEST/tests/agent_eval/gate.py',
    ])
    assert names == {'audio-import', 'tag-group'}
