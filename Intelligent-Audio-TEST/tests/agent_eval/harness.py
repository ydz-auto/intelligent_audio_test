# -*- coding: utf-8 -*-
"""Agent 评测基座：模拟模型 + 确定性工具数据 + 指标口径（卡面 §14 / §8.5）。

本基座不依赖真实 LLM / 真实平台工具，用确定性替身跑真实 Loop、
ContextAssembler 与持久化链路，用来回归：

- 压缩前后任务成功率差（≤5 个百分点）；
- 事实召回率（≥95%，事实可由工具重查，重查单独计「重查率」）；
- 压缩次数（agent_context_snapshot 条数）；
- 无编造数值（答案与工具真实返回逐字段核对）。

评测集见 ``datasets/golden_tasks.json`` 与 ``datasets/long_task.json``。
模拟模型只做两件事：按任务标记调用指定工具；从上下文中检索事实并回答
（检索不到时重查一次，仍检索不到回答 UNKNOWN，避免无限循环）。
"""
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent_service.domain.enums import SandboxTier, ToolRisk
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.llm import (
    LlmClient, LlmFinished, LlmTextDelta, LlmToolCalls,
)
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway, ToolInvocationContext,
)

# ---------------------------------------------------------------- 确定性数据

TASK_COUNT = 60
REPORT_COUNT = 12
STATUSES = ('SUCCEEDED', 'RUNNING', 'FAILED')

PLATFORM_FACTS = {
    'contract:services_count': '8',
    'contract:auth_prefix': '/api/v1/auth',
    'contract:run_status_enum_count': '7',
    'contract:agent_run_permission': 'agent:run:read',
}
TOOL_SEARCH_FACTS = {'tool_search:task_get:risk': 'READ'}

# 长期记忆事实（INT-2490）：跨会话预置在 memory/ 文件树里，长任务集用
# memory_search 召回。键格式与工具事实一致（entity:index:field），
# 命中「无编造数值」检查时按工具真实返回逐字段核对。
MEMORY_FACTS = {
    'mem:user_pref:value': '中文',
    'mem:project_rule:value': 'report-first',
    'mem:export_style:value': 'pdf',
    'mem:audio_rule:value': 'wav-only',
    'mem:report_rule:value': 'daily',
    'mem:device_rule:value': 'lan-only',
    'mem:testcase_rule:value': 'tag-required',
    'mem:speaker_rule:value': 'group-first',
}

DETAIL_PADDING = 1200  # 每轮详情结果的附加正文（字符），模拟真实长结果


def task_facts(index: int) -> Dict[str, str]:
    return {
        f'task:T{index}:status': STATUSES[index % 3],
        f'task:T{index}:progress': str((index * 7) % 101),
        f'task:T{index}:case_count': str((index % 9) + 1),
    }


def report_facts(index: int) -> Dict[str, str]:
    return {
        f'report:R{index}:accuracy': f'{0.90 + index / 1000:.3f}',
        f'report:R{index}:recall': f'{0.85 + index / 1000:.3f}',
        f'report:R{index}:f1': f'{0.88 + index / 1000:.3f}',
    }


def task_record(index: int) -> Dict[str, Any]:
    facts = task_facts(index)
    return {
        'task_id': f'T{index}',
        'name': f'任务-{index}',
        'status': facts[f'task:T{index}:status'],
        'progress': int(facts[f'task:T{index}:progress']),
        'case_count': int(facts[f'task:T{index}:case_count']),
    }


def report_record(index: int) -> Dict[str, Any]:
    facts = report_facts(index)
    return {
        'report_id': f'R{index}',
        'name': f'报告-{index}',
        'accuracy': facts[f'report:R{index}:accuracy'],
        'recall': facts[f'report:R{index}:recall'],
        'f1': facts[f'report:R{index}:f1'],
    }


# ---------------------------------------------------------------- 工具替身

class EvalToolGateway(ToolGateway):
    """确定性工具数据；记录每次返回的 facts 供「逐字段核对」。"""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.returned_facts: Dict[str, str] = {}
        self._tools = (
            ToolDescriptor(
                name='platform_contract', description='平台口径',
                parameters={'type': 'object'}, risk=ToolRisk.READ,
                sandbox_tier=SandboxTier.T0_NONE),
            ToolDescriptor(
                name='task_query', description='任务只读查询',
                parameters={'type': 'object'}, risk=ToolRisk.READ,
                sandbox_tier=SandboxTier.T0_NONE),
            ToolDescriptor(
                name='report_query', description='报告只读查询',
                parameters={'type': 'object'}, risk=ToolRisk.READ,
                sandbox_tier=SandboxTier.T0_NONE),
            ToolDescriptor(
                name='tool_search', description='工具 Schema 检索',
                parameters={'type': 'object'}, risk=ToolRisk.READ,
                sandbox_tier=SandboxTier.T0_NONE),
            ToolDescriptor(
                name='memory_search', description='长期记忆关键词检索',
                parameters={'type': 'object'}, risk=ToolRisk.READ,
                sandbox_tier=SandboxTier.T0_NONE),
        )

    def all_tools(self) -> Sequence[ToolDescriptor]:
        return self._tools

    def describe(self, names: Sequence[str]) -> Sequence[ToolDescriptor]:
        wanted = set(names)
        return tuple(t for t in self._tools if t.name in wanted)

    def execute(self, call: ToolCallRequest,
                context: ToolInvocationContext) -> ToolResult:
        self.calls.append({'tool': call.name,
                           'arguments': dict(call.arguments or {})})
        try:
            payload = self._payload(call.name, call.arguments or {})
        except Exception as exc:  # noqa: BLE001 - 替身错误回灌普通失败
            return ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name, ok=False,
                content=f'工具执行失败: {exc}', error_code='TOOL_FAILED')
        facts = payload.get('facts') or {}
        self.returned_facts.update({k: str(v) for k, v in facts.items()})
        return ToolResult(
            tool_call_id=call.tool_call_id, tool=call.name, ok=True,
            content=json.dumps(payload, ensure_ascii=False))

    # ------------------------------------------------------------ payloads

    def _payload(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool == 'platform_contract':
            section = str(args.get('section') or 'services')
            if section == 'prefixes':
                return {
                    'prefixes': {'auth': '/api/v1/auth',
                                 'agent': '/api/v1/agent',
                                 'task': '/api/v1/tasks'},
                    'facts': {'contract:auth_prefix':
                              PLATFORM_FACTS['contract:auth_prefix']},
                }
            if section == 'enums':
                return {
                    'run_status': ['QUEUED', 'RUNNING', 'WAITING_APPROVAL',
                                   'SUCCEEDED', 'FAILED', 'CANCELLED',
                                   'BUDGET_EXCEEDED'],
                    'facts': {'contract:run_status_enum_count':
                              PLATFORM_FACTS['contract:run_status_enum_count']},
                }
            if section == 'permissions':
                return {
                    'permissions': {'agent_run': 'agent:run:read',
                                    'agent_provider': 'agent:provider:manage'},
                    'facts': {'contract:agent_run_permission':
                              PLATFORM_FACTS['contract:agent_run_permission']},
                }
            return {
                'services': [f'service-{i}' for i in range(1, 9)],
                'facts': {'contract:services_count':
                          PLATFORM_FACTS['contract:services_count']},
            }
        if tool == 'task_query':
            action = str(args.get('action') or 'detail')
            if action == 'list':
                return {
                    'items': [task_record(i) for i in range(1, TASK_COUNT + 1)],
                    'total': TASK_COUNT,
                    'facts': {'task:list:total': str(TASK_COUNT)},
                }
            index = _entity_index(args.get('task_id'), 'T')
            record = task_record(index)
            record['details'] = f'任务 {index} 的执行明细。' + 'd' * DETAIL_PADDING
            record['facts'] = task_facts(index)
            return record
        if tool == 'report_query':
            action = str(args.get('action') or 'detail')
            if action == 'list':
                return {
                    'items': [report_record(i)
                              for i in range(1, REPORT_COUNT + 1)],
                    'total': REPORT_COUNT,
                    'facts': {'report:list:total': str(REPORT_COUNT)},
                }
            index = _entity_index(args.get('report_id'), 'R')
            record = report_record(index)
            record['facts'] = report_facts(index)
            return record
        if tool == 'tool_search':
            return {
                'matches': [{
                    'name': 'task_get', 'type': 'mcp',
                    'risk': TOOL_SEARCH_FACTS['tool_search:task_get:risk'],
                    'description': '按 task_id 查询任务详情',
                }],
                'facts': dict(TOOL_SEARCH_FACTS),
            }
        if tool == 'memory_search':
            # 确定性替身：真实 rg 检索路径由单测覆盖；评测只关心
            # 「召回率 + 无编造」在 50+ 轮会话里是否稳定。
            return {
                'scope': str(args.get('scope') or 'USER'),
                'count': len(MEMORY_FACTS),
                'truncated': False,
                'items': [
                    {'path': 'user_profile.md',
                     'snippet': f'- {key} = {value}',
                     'score': 1, 'updated_at': None}
                    for key, value in MEMORY_FACTS.items()
                ],
                'facts': dict(MEMORY_FACTS),
            }
        raise ValueError(f'未知工具 {tool}')


def _entity_index(value: Any, prefix: str) -> int:
    text = str(value or '')
    if text.upper().startswith(prefix):
        text = text[1:]
    index = int(text)
    if index < 1:
        raise ValueError(f'非法实体编号: {value}')
    return index


def expected_truth(fact_key: str) -> Optional[str]:
    """数据集自检：按同一份确定性数据推导事实真值，与工具返回逐字段核对。"""
    if fact_key in PLATFORM_FACTS:
        return PLATFORM_FACTS[fact_key]
    if fact_key in TOOL_SEARCH_FACTS:
        return TOOL_SEARCH_FACTS[fact_key]
    if fact_key in MEMORY_FACTS:
        return MEMORY_FACTS[fact_key]
    if fact_key == 'task:list:total':
        return str(TASK_COUNT)
    if fact_key == 'report:list:total':
        return str(REPORT_COUNT)
    parts = fact_key.split(':')
    if len(parts) != 3:
        return None
    entity, index, _field = parts
    if entity == 'task':
        return task_facts(int(index[1:])).get(fact_key)
    if entity == 'report':
        return report_facts(int(index[1:])).get(fact_key)
    return None


# ---------------------------------------------------------------- 模拟模型

_MARKER_RE = re.compile(r'\[\[EVAL (\{.*?\})\]\]', re.S)
_FACT_JSON_RE = re.compile(r'"([a-z][a-z0-9_]*:[A-Za-z0-9_-]+:[a-z_]+)"'
                           r'\s*:\s*"([^"]*)"')
_FACT_NUM_RE = re.compile(r'"([a-z][a-z0-9_]*:[A-Za-z0-9_-]+:[a-z_]+)"'
                          r'\s*:\s*(-?\d+(?:\.\d+)?)')
_FACT_TEXT_RE = re.compile(r'([a-z][a-z0-9_]*:[A-Za-z0-9_-]+:[a-z_]+)'
                           r'\s*=\s*([^\s;；,，"]+)')


@dataclass
class SimulationStats:
    """一次场景运行的计数（用于重查率 / 压缩次数 / 成本口径）。"""

    tool_calls: int = 0
    requery_count: int = 0
    memo_calls: int = 0
    unknown_answers: int = 0
    # INT-2475 成本可观测：模型调用轮次与输入规模（字符数，token 近似 = chars/4）。
    # 确定性替身没有真实计费，这里记录同一口径的可复现成本指标。
    llm_calls: int = 0
    prompt_chars: int = 0

    def to_cost(self) -> Dict[str, int]:
        """成本快照（报告口径）：调用轮次 / 工具调用 / 输入字符与近似 token。"""
        return {
            'llm_calls': self.llm_calls,
            'tool_calls': self.tool_calls,
            'memo_calls': self.memo_calls,
            'prompt_chars': self.prompt_chars,
            'approx_prompt_tokens': self.prompt_chars // 4,
        }


class SimulatedModel(LlmClient):
    """确定性替身：按任务标记取工具，再从上下文检索事实作答。"""

    model = 'sim-eval-model'
    # 备忘必须可累加且有界：保留最近 N 条已确认事实（约 20 个学习轮）
    MEMO_FACT_LIMIT = 60

    def __init__(self, stats: SimulationStats):
        self._stats = stats
        self._calls_by_run: Dict[str, int] = {}

    # ------------------------------------------------------------ stream

    def stream(self, request, cancel_check=None):
        if cancel_check is not None and cancel_check():
            return
        self._stats.llm_calls += 1
        self._stats.prompt_chars += sum(
            len(text) for text in _message_texts(request.messages))
        purpose = (request.metadata or {}).get('purpose')
        if purpose == 'context_memo':
            self._stats.memo_calls += 1
            yield LlmTextDelta(self._memo_from_request(request))
            yield LlmFinished()
            return

        run_id = (request.metadata or {}).get('run_id') or ''
        marker = self._marker(request)
        if marker is None:
            yield LlmTextDelta('ANSWER: UNKNOWN')
            yield LlmFinished()
            return
        texts = _message_texts(request.messages)
        value = _find_fact(texts, marker['fact_key'])
        if value is not None:
            yield LlmTextDelta(f'ANSWER: {value}')
            yield LlmFinished()
            return
        if self._calls_by_run.get(run_id, 0) > 0:
            self._stats.unknown_answers += 1
            yield LlmTextDelta('ANSWER: UNKNOWN')
            yield LlmFinished()
            return
        self._calls_by_run[run_id] = 1
        self._stats.tool_calls += 1
        if marker.get('kind') == 'recall':
            self._stats.requery_count += 1
        yield LlmToolCalls((ToolCallRequest(
            tool_call_id=f'sim-{uuid.uuid4().hex[:12]}',
            name=marker['tool'],
            arguments=dict(marker.get('arguments') or {})),))
        yield LlmFinished()

    @staticmethod
    def _marker(request) -> Optional[Dict[str, Any]]:
        for message in reversed(list(request.messages)):
            if message.role != 'user' or not message.content:
                continue
            match = _MARKER_RE.search(message.content)
            if match:
                try:
                    return json.loads(match.group(1))
                except (TypeError, ValueError):
                    return None
        return None

    def _memo_from_request(self, request) -> str:
        try:
            transcript = json.loads(list(request.messages)[-1].content or '[]')
        except (TypeError, ValueError):
            transcript = []
        facts: Dict[str, Tuple[str, str]] = {}
        goal = ''
        constraints: List[str] = []
        for item in transcript:
            content = str(item.get('content') or '')
            message_id = str(item.get('message_id') or '')
            if item.get('role') == 'user' and not goal:
                goal = _MARKER_RE.sub('', content).strip()[:200]
            if '约束' in content and len(content) <= 200:
                constraints.append(content)
            for key, val in _FACT_JSON_RE.findall(content):
                facts[key] = (val, message_id)
            for key, val in _FACT_NUM_RE.findall(content):
                facts.setdefault(key, (val, message_id))
            for key, val in _FACT_TEXT_RE.findall(content):
                facts.setdefault(key, (val, message_id))
        recent = list(facts.items())[-self.MEMO_FACT_LIMIT:]
        memo = {
            'goal': goal or '完成跨域长任务',
            'constraints': constraints[:10],
            'facts': [{'fact': f'{key}={value}', 'value': value,
                       'source_id': source}
                      for key, (value, source) in recent],
            'decisions': [],
            'artifacts': [],
            'open_questions': [],
            'next_steps': [],
        }
        return json.dumps(memo, ensure_ascii=False)


def _message_texts(messages) -> List[str]:
    texts: List[str] = []
    for message in messages:
        if message.content:
            texts.append(message.content)
        if message.tool_calls:
            texts.append(json.dumps(list(message.tool_calls),
                                    ensure_ascii=False))
    return texts


def _find_fact(texts: Sequence[str], key: str) -> Optional[str]:
    escaped = re.escape(key)
    quoted = re.compile(r'"' + escaped + r'"\s*:\s*"([^"]*)"')
    numeric = re.compile(r'"' + escaped + r'"\s*:\s*(-?\d+(?:\.\d+)?)')
    text_form = re.compile(escaped + r'\s*=\s*([^\s;；,，"]+)')
    for text in texts:
        match = quoted.search(text) or numeric.search(text) \
            or text_form.search(text)
        if match:
            return match.group(1)
    return None


# ---------------------------------------------------------------- 指标

@dataclass
class RoundResult:
    round: int
    kind: str
    fact_key: str
    expected: str
    answer: Optional[str]
    status: str
    requery: bool = False
    domain: str = ''

    @property
    def correct(self) -> bool:
        return self.answer == self.expected

    @property
    def fabricated(self) -> bool:
        return (self.answer is not None and self.answer != 'UNKNOWN'
                and not self.correct)


@dataclass
class ScenarioMetrics:
    name: str
    rounds: int
    answered: int
    correct: int
    unknown: int
    fact_recall_rate: float
    requery_count: int
    requery_rate: float
    compaction_count: int
    snapshot_levels: Dict[str, int] = field(default_factory=dict)
    run_failures: int = 0
    # 长期记忆子集（domain='memory'）：召回命中率单独计（INT-2490）
    memory_rounds: int = 0
    memory_correct: int = 0
    # INT-2475 成本可观测（模型轮次 / 工具调用 / 输入近似 token）
    cost: Dict[str, int] = field(default_factory=dict)

    @property
    def memory_hit_rate(self) -> float:
        if not self.memory_rounds:
            return 0.0
        return self.memory_correct / self.memory_rounds

    @property
    def success_rate(self) -> float:
        return self.correct / self.rounds if self.rounds else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'rounds': self.rounds,
            'answered': self.answered,
            'correct': self.correct,
            'unknown': self.unknown,
            'success_rate': round(self.success_rate, 4),
            'fact_recall_rate': round(self.fact_recall_rate, 4),
            'requery_count': self.requery_count,
            'requery_rate': round(self.requery_rate, 4),
            'compaction_count': self.compaction_count,
            'snapshot_levels': dict(self.snapshot_levels),
            'run_failures': self.run_failures,
            'memory_rounds': self.memory_rounds,
            'memory_correct': self.memory_correct,
            'memory_hit_rate': round(self.memory_hit_rate, 4),
            'cost': dict(self.cost),
        }


def summarize_rounds(name: str, rounds: Sequence[RoundResult],
                     compaction_levels: Dict[str, int],
                     run_failures: int,
                     cost: Optional[Dict[str, int]] = None) -> ScenarioMetrics:
    total = len(rounds)
    correct = sum(1 for r in rounds if r.correct)
    unknown = sum(1 for r in rounds if r.answer in (None, 'UNKNOWN'))
    requery = sum(1 for r in rounds if r.requery)
    memory_rounds = [r for r in rounds if r.domain == 'memory']
    return ScenarioMetrics(
        name=name, rounds=total, answered=total - unknown, correct=correct,
        unknown=unknown,
        fact_recall_rate=(correct / total) if total else 0.0,
        requery_count=requery,
        requery_rate=(requery / total) if total else 0.0,
        compaction_count=sum(compaction_levels.values()),
        snapshot_levels=dict(compaction_levels),
        run_failures=run_failures,
        memory_rounds=len(memory_rounds),
        memory_correct=sum(1 for r in memory_rounds if r.correct),
        cost=dict(cost or {}),
    )


__all__ = [
    'DETAIL_PADDING', 'EvalToolGateway', 'MEMORY_FACTS', 'PLATFORM_FACTS',
    'RoundResult',
    'ScenarioMetrics', 'SimulatedModel', 'SimulationStats', 'expected_truth',
    'report_facts', 'summarize_rounds', 'task_facts',
]
