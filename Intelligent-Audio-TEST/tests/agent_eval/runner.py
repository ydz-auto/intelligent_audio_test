# -*- coding: utf-8 -*-
"""Agent 评测运行器（卡面「评测基座」）。

用法::

    python -m tests.agent_eval.runner --out tests/agent_eval/out

产出 ``report.json`` 与 ``report.md``：golden 10 条结果、50+ 轮跨域长任务的
成功率 / 事实召回率 / 重查率 / 压缩次数，以及「压缩前后成功率差」验收结论。

运行链路是真实的：``build_container`` → 单 Agent Loop → ContextAssembler
（含 L1–L3）→ agent_* 持久化；只有模型与工具是确定性替身。
"""
import argparse
import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# 评测替身不连真实库 / OSS；配置类属性在导入时冻结，必须先给兜底值
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.application.context_assembler import CompactionSettings
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.domain.ports.artifact_store import ArtifactStore
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.wakeup import LocalRunWakeup
from agent_service.wiring import build_container
from tests.agent_eval.harness import (
    EvalToolGateway, RoundResult, ScenarioMetrics, SimulatedModel,
    SimulationStats, expected_truth, summarize_rounds,
)
from tests.unit.int2451_agent_fakes import (
    FakeProviderResolver, TEST_MASTER_KEY, default_provider, make_engine,
)

DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'datasets')
DEFAULT_WINDOW = 8192
DEFAULT_OUTPUT_RESERVE = 1024
DEFAULT_RECENT_TURNS = 3

OWNER_ID = 1
TENANT_ID = 'eval'


class MemoryArtifactStore(ArtifactStore):
    """评测用对象存储替身：内容留在内存，便于核对 artifact 引用。"""

    def __init__(self):
        self.items: Dict[str, str] = {}

    def put(self, content, *, run_id, name,
            content_type='application/json'):
        uri = f'oss://archives/agent-context/{run_id}/{name}'
        self.items[uri] = content
        return uri


@dataclass
class GoldenMetrics:
    total: int
    passed: int
    failures: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {'total': self.total, 'passed': self.passed,
                'failed': self.total - self.passed, 'failures': self.failures}


@dataclass
class EvalReport:
    window: int
    golden: GoldenMetrics
    baseline: ScenarioMetrics
    compressed: ScenarioMetrics
    success_delta_points: float
    acceptance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'window': self.window,
            'golden': self.golden.to_dict(),
            'long_task': {
                'baseline_no_compaction': self.baseline.to_dict(),
                'compressed': self.compressed.to_dict(),
                'success_delta_points': round(self.success_delta_points, 2),
            },
            'acceptance': dict(self.acceptance),
        }

    def to_markdown(self) -> str:
        lines = [
            '# Agent 评测报告（INT-2454）',
            '',
            f'- 有效上下文窗口 W：{self.window} tokens',
            f'- Golden tasks：{self.golden.passed}/{self.golden.total} 通过',
            '',
            '## 50+ 轮跨域长任务',
            '',
            '| 指标 | 无压缩（基线） | 压缩 L1–L3 |',
            '|---|---|---|',
            f'| 轮次 | {self.baseline.rounds} | {self.compressed.rounds} |',
            f'| 成功率 | {self.baseline.success_rate:.1%} '
            f'| {self.compressed.success_rate:.1%} |',
            f'| 事实召回率 | {self.baseline.fact_recall_rate:.1%} '
            f'| {self.compressed.fact_recall_rate:.1%} |',
            f'| 重查率 | {self.baseline.requery_rate:.1%} '
            f'| {self.compressed.requery_rate:.1%} |',
            f'| 压缩次数 | {self.baseline.compaction_count} '
            f'| {self.compressed.compaction_count} |',
            f'| 未知回答 | {self.baseline.unknown} | {self.compressed.unknown} |',
            f'| run 失败 | {self.baseline.run_failures} '
            f'| {self.compressed.run_failures} |',
            '',
            f'压缩前后成功率差：**{self.success_delta_points:.2f} 个百分点**'
            '（门槛 ≤ 5）',
            '',
            '## 验收',
            '',
            '| 项 | 结论 |',
            '|---|---|',
        ]
        for key, value in self.acceptance.items():
            if key == 'passed':
                continue
            lines.append(f'| {key} | {"通过" if value else "未通过"} |')
        lines.append(f'| **总体** | '
                     f'{"通过" if self.acceptance.get("passed") else "未通过"} |')
        if self.golden.failures:
            lines += ['', '## Golden 失败明细', '']
            for item in self.golden.failures:
                lines.append(
                    f"- {item.get('task_id')}: expected="
                    f"{item.get('expected')} answer={item.get('answer')} "
                    f"reason={item.get('reason')}")
        return '\n'.join(lines) + '\n'

    def write(self, out_dir: str) -> Dict[str, str]:
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, 'report.json')
        md_path = os.path.join(out_dir, 'report.md')
        with open(json_path, 'w', encoding='utf-8') as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        with open(md_path, 'w', encoding='utf-8') as handle:
            handle.write(self.to_markdown())
        return {'json': json_path, 'markdown': md_path}


class AgentEvalRunner:
    def __init__(self, work_dir: str, *, window: int = DEFAULT_WINDOW,
                 output_reserve: int = DEFAULT_OUTPUT_RESERVE,
                 keep_recent_turns: int = DEFAULT_RECENT_TURNS):
        self._work_dir = work_dir
        self._window = int(window)
        self._output_reserve = int(output_reserve)
        self._keep_recent = int(keep_recent_turns)
        os.makedirs(self._work_dir, exist_ok=True)

    # ------------------------------------------------------------ scenarios

    def run_golden(self) -> GoldenMetrics:
        tasks = _load_json('golden_tasks.json')['tasks']
        _assert_dataset_truth(tasks, id_key='id')
        stats = SimulationStats()
        model = SimulatedModel(stats)
        gateway = EvalToolGateway()
        container = self._container(
            os.path.join(self._work_dir, 'golden.db'), model, gateway,
            compression=True)
        failures: List[Dict[str, Any]] = []
        try:
            for task in tasks:
                session = container.run_service.create_session(
                    owner_id=OWNER_ID, tenant_id=TENANT_ID,
                    title=f"golden {task['id']}")
                marker = {
                    'id': task['id'], 'kind': 'golden',
                    'tool': task['tool'], 'arguments': task['arguments'],
                    'fact_key': task['fact_key'],
                }
                message = f"[[EVAL {json.dumps(marker, ensure_ascii=False)}]] " \
                          f"{task['prompt']}"
                run, answer, status = self._run(
                    container, session, message,
                    active_skill=task.get('active_skill'))
                tool_value = gateway.returned_facts.get(task['fact_key'])
                reason = None
                if status != 'SUCCEEDED':
                    reason = f'run_status={status}'
                elif answer != task['expected_value']:
                    reason = 'answer_mismatch'
                elif tool_value != answer:
                    reason = f'tool_return_mismatch({tool_value})'
                elif answer in (task.get('forbidden_values') or []):
                    reason = 'fabricated_value'
                if reason:
                    failures.append({
                        'task_id': task['id'], 'expected': task['expected_value'],
                        'answer': answer, 'reason': reason,
                    })
        finally:
            container.shutdown()
        return GoldenMetrics(total=len(tasks), passed=len(tasks) - len(failures),
                             failures=failures)

    def run_long_task(self, *, compression: bool) -> ScenarioMetrics:
        rounds = _load_json('long_task.json')['rounds']
        _assert_dataset_truth(rounds, id_key='round')
        stats = SimulationStats()
        model = SimulatedModel(stats)
        gateway = EvalToolGateway()
        name = 'compressed' if compression else 'baseline'
        container = self._container(
            os.path.join(self._work_dir, f'long_{name}.db'), model, gateway,
            compression=compression)
        results: List[RoundResult] = []
        run_failures = 0
        try:
            session = container.run_service.create_session(
                owner_id=OWNER_ID, tenant_id=TENANT_ID, title='long task')
            for item in rounds:
                marker = {
                    'id': f"LT-{item['round']}", 'kind': item['kind'],
                    'tool': item['tool'], 'arguments': item['arguments'],
                    'fact_key': item['fact_key'],
                }
                message = (f"[[EVAL {json.dumps(marker, ensure_ascii=False)}]] "
                           f"{item['prompt']}")
                before = stats.requery_count
                run, answer, status = self._run(container, session, message)
                if status != 'SUCCEEDED':
                    run_failures += 1
                results.append(RoundResult(
                    round=item['round'], kind=item['kind'],
                    fact_key=item['fact_key'],
                    expected=item['expected_value'], answer=answer,
                    status=status,
                    requery=stats.requery_count > before))
            levels = _snapshot_levels(container, session)
        finally:
            container.shutdown()
        return summarize_rounds(name, results, levels, run_failures)

    def run_all(self) -> EvalReport:
        golden = self.run_golden()
        baseline = self.run_long_task(compression=False)
        compressed = self.run_long_task(compression=True)
        delta = abs(baseline.success_rate - compressed.success_rate) * 100
        acceptance = {
            'golden_10_all_passed': golden.passed == golden.total == 10,
            'no_fabricated_values': not any(
                f.get('reason') == 'fabricated_value' for f in golden.failures),
            'fact_recall_ge_95': compressed.fact_recall_rate >= 0.95,
            'success_delta_le_5_points': delta <= 5.0,
            'compaction_observed': compressed.compaction_count > 0,
        }
        acceptance['passed'] = all(acceptance.values())
        return EvalReport(
            window=self._window, golden=golden, baseline=baseline,
            compressed=compressed, success_delta_points=delta,
            acceptance=acceptance)

    # ------------------------------------------------------------ helpers

    def _container(self, db_path: str, model: SimulatedModel,
                   gateway: EvalToolGateway, *, compression: bool):
        _engine, session_factory = make_engine(db_path)
        provider = default_provider(
            model='sim-eval-model',
            effective_context_window=self._window,
            max_output_tokens=self._output_reserve)
        resolver = FakeProviderResolver(model, provider=provider)
        settings = CompactionSettings(
            enabled=compression,
            keep_recent_turns=self._keep_recent,
            debug=True)
        return build_container(
            session_factory,
            provider_resolver=resolver,
            tool_gateway=gateway,
            wakeup=LocalRunWakeup(),
            executor_factory=lambda orch: InlineRunExecutor(orch),
            credential_store=CredentialStore.from_secret(TEST_MASTER_KEY),
            context_max_runs=200,
            context_max_messages=10000,
            context_debug=True,
            compaction_settings=settings,
            artifact_store=MemoryArtifactStore(),
        )

    @staticmethod
    def _run(container, session, message: str,
             active_skill: Optional[str] = None):
        run, created = container.run_service.create_run(
            session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            message=message, active_skill=active_skill)
        assert created
        container.executor.submit(run.id)
        stored = container.repositories['runs'].get(run.id)
        answer = _answer_of(container, run.id)
        return stored, answer, stored.status.value if stored else 'MISSING'


def _answer_of(container, run_id: str) -> Optional[str]:
    events = container.repositories['events'].list_after(run_id, 0, 10000)
    parts = [event.payload.get('delta') or ''
             for event in events
             if event.type.value == 'message_delta']
    text = ''.join(parts).strip()
    if not text:
        return None
    marker = 'ANSWER:'
    index = text.rfind(marker)
    if index < 0:
        return None
    return text[index + len(marker):].strip().splitlines()[0].strip()


def _snapshot_levels(container, session) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    snapshots = container.repositories['snapshots']
    for run in container.repositories['runs'].list_session_runs(session.id, 500):
        for snapshot in snapshots.list_by_run(run.id):
            level = snapshot.level.value
            counts[level] = counts.get(level, 0) + 1
    return counts


def _load_json(name: str) -> Dict[str, Any]:
    with open(os.path.join(DATASET_DIR, name), encoding='utf-8') as handle:
        return json.load(handle)


def _assert_dataset_truth(items: Sequence[Dict[str, Any]],
                          *, id_key: str) -> None:
    """数据集与工具真实返回逐字段核对（防止评测集与替身数据漂移）。"""
    for item in items:
        expected = expected_truth(item['fact_key'])
        if expected != str(item['expected_value']):
            raise AssertionError(
                f"评测集事实与工具数据不一致 {item.get(id_key)}: "
                f"{item['fact_key']} dataset={item['expected_value']} "
                f"tool={expected}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Agent 压缩 / golden 评测')
    parser.add_argument('--out', default=os.path.join(DATASET_DIR, '..', 'out'),
                        help='报告输出目录')
    parser.add_argument('--window', type=int, default=DEFAULT_WINDOW)
    parser.add_argument('--output-reserve', type=int,
                        default=DEFAULT_OUTPUT_RESERVE)
    parser.add_argument('--work-dir', default=None,
                        help='评测临时数据库目录（默认临时目录）')
    args = parser.parse_args(argv)
    work_dir = args.work_dir or tempfile.mkdtemp(prefix='agent_eval_')
    runner = AgentEvalRunner(
        work_dir, window=args.window, output_reserve=args.output_reserve)
    report = runner.run_all()
    paths = report.write(args.out)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"report: {paths['markdown']}")
    return 0 if report.acceptance.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
