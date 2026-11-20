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
    # P2-2：数据集与整体成功率共用同一阈值（单口径）
    assert metrics['success_threshold'] == gate.E2E_SUCCESS_THRESHOLD
    for name, dataset in metrics['datasets'].items():
        assert dataset['success_rate'] >= gate.E2E_SUCCESS_THRESHOLD, name


# ---------------------------------------------------------------- P2-2 e2e 口径

class _FakeTaskSet:
    """``_e2e_dataset_failure`` 只需要 TaskSetMetrics 的这几个字段。"""

    def __init__(self, total, passed, tool_selection_correct=None,
                 failures=None):
        self.total = total
        self.passed = passed
        self.tool_selection_correct = (total if tool_selection_correct is None
                                       else tool_selection_correct)
        self.failures = list(failures or [])


def test_e2e_dataset_gate_uses_the_shared_threshold():
    """P2-2：数据集门槛不再是 100%，而是与整体成功率同一条 95% 口径。"""
    assert gate.E2E_SUCCESS_THRESHOLD < 1.0
    assert gate._e2e_dataset_failure(_FakeTaskSet(100, 95), []) is None
    assert gate._e2e_dataset_failure(_FakeTaskSet(100, 99), []) is None
    detail = gate._e2e_dataset_failure(_FakeTaskSet(100, 94), [])
    assert detail and '94/100' in detail
    # 编造 / 工具派发是独立判据，成功率达标也照样判红
    assert gate._e2e_dataset_failure(
        _FakeTaskSet(100, 100), [{'reason': 'fabricated_value'}])
    assert '工具派发异常' in gate._e2e_dataset_failure(
        _FakeTaskSet(100, 100, tool_selection_correct=99), [])


def test_markdown_gate_rows_cover_each_e2e_dataset():
    """P2-2：门槛表按 e2e:<dataset> 出行，不能「表格全通过、层结论未通过」。"""
    report = _fake_report('passed', 'passed', 'passed', 'passed', 'passed')
    e2e = report.layers['e2e']
    e2e.metrics = {'datasets': {'golden_tasks.json': {},
                                'no_fabrication_tasks.json': {}}}
    e2e.fail('e2e:no_fabrication_tasks.json', '29/30 通过（96.7% < 95%）')
    rows = [line for line in report.to_markdown().splitlines()
            if line.startswith('| 端到端·')]
    assert [row.split('|')[1].strip() for row in rows] == [
        '端到端·golden_tasks.json 成功率',
        '端到端·no_fabrication_tasks.json 成功率',
    ]
    assert [row for row in rows if 'golden_tasks.json 成功率' in row][0] \
        .rstrip().endswith('| 通过 |')
    assert [row for row in rows if 'no_fabrication' in row][0] \
        .rstrip().endswith('| 未通过 |')


# ---------------------------------------------------------------- P2-3 权限边界

def test_check_permissions_flags_write_tool_on_read_task():
    """P2-3：只读任务集里出现写工具必须判红（负例，证明判据可判红）。"""
    violations = gate._check_permissions([
        {'task': '音频列表', 'active_skill': None,
         'called': ['audio_query', 'audio_import']},
    ])
    assert [item['tool'] for item in violations] == ['audio_import']
    assert violations[0]['reason'] == 'read_task_called_WRITE'


def test_check_permissions_flags_tool_outside_skill_whitelist():
    """P2-3：Skill 白名单外的工具必须判红。"""
    violations = gate._check_permissions([
        {'task': 't', 'active_skill': 'audio-import', 'called': ['task_query']},
    ])
    assert [item['tool'] for item in violations] == ['task_query']
    assert violations[0]['reason'] == 'not_in_skill_allowed_tools'


def test_check_permissions_flags_unknown_skill():
    violations = gate._check_permissions([
        {'task': 't', 'active_skill': 'not-a-skill', 'called': []},
    ])
    assert violations and '未知 Skill' in violations[0]['reason']


def test_check_permissions_accepts_allowed_read_tool():
    """正例：白名单内的只读工具不误报（负例的反面）。"""
    assert gate._check_permissions([
        {'task': 't', 'active_skill': 'audio-import', 'called': ['audio_query']},
        {'task': 't', 'active_skill': None, 'called': ['audio_query']},
    ]) == []


# ---------------------------------------------------------------- P2-1 层完整性

def _partial_report(*layers):
    return gate.GateReport(
        started_at=gate.datetime.now(gate.timezone.utc),
        duration_seconds=0.2,
        layers={layer.name: layer for layer in layers},
        dataset_versions=gate.dataset_versions())


def test_skipped_layer_is_not_a_pass():
    """P2-1：被跳过的层不再让门禁 exit 0，报告顶层可辨。"""
    report = _fake_report('passed', 'passed', 'passed', 'skipped', 'passed')
    assert report.layers_skipped == ['sandbox']
    assert report.degraded and not report.full_five
    assert not report.passed and report.exit_code == 1
    payload = report.to_dict()
    assert payload['layers_skipped'] == ['sandbox']
    assert payload['layers_expected'] == list(gate.LAYER_ORDER)
    assert payload['full_five'] is False and payload['degraded'] is True
    assert payload['allow_skip'] is False


def test_subset_layers_are_not_full_five():
    """P2-1：--layers 子集同样拿不到 exit 0（层不完整）。"""
    report = _partial_report(
        gate.LayerResult(name='e2e', status='passed'),
        gate.LayerResult(name='skill', status='passed'))
    assert report.layers_missing == ['compaction', 'sandbox', 'recovery']
    assert not report.full_five and report.exit_code == 1
    payload = report.to_dict()
    assert payload['layers_missing'] == ['compaction', 'sandbox', 'recovery']
    assert payload['full_five'] is False


def test_allow_skip_passes_but_report_stays_distinguishable():
    """P2-1：显式 --allow-skip 下 exit 0，但报告仍标出跳过的层。"""
    report = _partial_report(
        gate.LayerResult(name='e2e', status='passed'),
        gate.LayerResult(name='sandbox', status='skipped'))
    report.allow_skip = True
    assert report.passed and report.exit_code == 0
    payload = report.to_dict()
    assert payload['allow_skip'] is True
    assert payload['layers_skipped'] == ['sandbox']
    assert payload['full_five'] is False and payload['degraded'] is True


def test_sandbox_tier_none_reports_skipped():
    result = gate.run_sandbox_layer('none')
    assert result.status == 'skipped'
    assert 'none' in result.detail


def test_markdown_marks_degraded_layer_integrity():
    report = _fake_report('passed', 'passed', 'passed', 'skipped', 'passed')
    markdown = report.to_markdown()
    assert '全五层：否' in markdown
    integrity = [line for line in markdown.splitlines()
                 if line.startswith('| 层完整性')][0]
    assert integrity.rstrip().endswith('| 未通过 |')



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
