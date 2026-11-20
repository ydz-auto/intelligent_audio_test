# -*- coding: utf-8 -*-
"""T1 沙箱 → 唯一 Loop 的接线（INT-2495，方案 §7 硬规则 1/5、§5.2 硬规则 6）。

职责边界
--------
1. **工具调用在沙箱外，脚本在沙箱内**（§7 硬规则 1）：``T0_NONE`` 仍走
   ``ToolGateway``；``T1_TRUSTED_SCRIPT`` 的调用由本模块翻译成
   ``SandboxRequest`` 交给 ``SandboxRunner``，**不再经过 ToolGateway**。
2. 脚本只能来自已在 ``SkillRegistry`` 登记的 ``scripts/`` 清单（模型给
   Skill 名 + 脚本相对路径 + 参数 + 非凭据环境变量），越界 / 未登记一律
   拒绝执行，不进入容器。
3. 结果回灌：``/work`` 产物清单（路径 / 大小 / sha256）+ 截断后的输出
   摘要打包成 ``tool_result`` 内容，原始输出上限仍由执行器的 1MB 截断保证。
4. **失败不静默**（§7 硬规则 5）：``SandboxResult`` 原样映射为
   ``ToolResult`` + ``SandboxFailure``；原因码沿用 ``sandbox_runner`` 的
   ``SandboxFailureReason``，不新增第二套口径。run 终态由
   ``RunOrchestrator`` 按 ``SandboxOutcome`` 收口为 ``FAILED`` /
   ``BUDGET_EXCEEDED``。
5. T2 首期不执行（INT-2489）：``T2_UNTRUSTED_CODE`` 与其未知层级一律
   ``UNSUPPORTED_TIER``。执行器未装配 / 抛裸异常收口为 ``RUNNER_ERROR``，
   不让异常穿透 Loop。
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple

from agent_service.application.sandbox_runner import (
    SandboxFailureReason,
    SandboxOutcome,
    SandboxRequest,
    SandboxResult,
    SandboxRunner,
)
from agent_service.domain.enums import SandboxTier
from agent_service.domain.model.entities import ToolCallRequest, ToolResult

logger = logging.getLogger(__name__)

#: 工具参数契约（T1 脚本调用）：skill / script 必填，args / env 选填。
ARG_SKILL = 'skill'
ARG_SCRIPT = 'script'
ARG_ARGS = 'args'
ARG_ENV = 'env'

#: 回灌内容的兜底字段（超出 ``tool_result_max_chars`` 时逐步收敛）。
_OUTPUT_KEYS = ('stdout', 'stderr')


@dataclass(frozen=True)
class SkillScripts:
    """一个 Skill 的脚本清单（由 ``SkillRegistry`` 解析出的只读快照）。"""

    skill_name: str
    root: Path
    scripts: Tuple[str, ...] = ()


#: Skill 名 → 脚本清单；未知 Skill 返回 ``None``。
SkillLocator = Callable[[str], Optional[SkillScripts]]


@dataclass(frozen=True)
class SandboxFailure:
    """一次沙箱失败的 run 级信号（由 Loop 收口成 FAILED / BUDGET_EXCEEDED）。"""

    outcome: SandboxOutcome
    reason: SandboxFailureReason
    tool_call_id: str = ''
    detail: str = ''
    exit_code: int = 0


class SandboxFailureLog:
    """同一工具批次内的失败收集器（并行执行，线程安全）。

    一批里同时出现多条失败时，``winner()`` 按「预算类优先、再按
    tool_call_id」取唯一一条，保证 run 终态与原因码可复现、不确定序。
    """

    def __init__(self) -> None:
        self._items: list[SandboxFailure] = []
        self._lock = threading.Lock()

    def record(self, failure: SandboxFailure) -> None:
        with self._lock:
            self._items.append(failure)

    def winner(self) -> Optional[SandboxFailure]:
        with self._lock:
            items = list(self._items)
        if not items:
            return None
        return min(items, key=lambda f: (
            0 if f.outcome is SandboxOutcome.BUDGET_EXCEEDED else 1,
            f.tool_call_id,
        ))

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class SandboxToolExecutor(Protocol):
    """Loop 侧端口：执行一次非 T0 沙箱工具调用（实现 = SandboxScriptDispatcher）。"""

    def execute(self, call: ToolCallRequest,
                tier: SandboxTier | str | object) -> Tuple[
                    ToolResult, Optional[SandboxFailure]]:  # pragma: no cover
        ...


class SandboxScriptDispatcher:
    """把 T1 工具调用翻译成沙箱执行，并映射为 ``ToolResult``。

    工具参数契约（``sandbox_tier=T1_TRUSTED_SCRIPT`` 的 descriptor 由工具
    注册表给出 Schema，模型按 Schema 传参）::

        {
          "skill":  "<Skill 名>",            # 必填，必须已装载
          "script": "scripts/<file>",        # 必填，必须在 skill.scripts 内
          "args":   ["...", "..."],          # 选填，脚本 argv
          "env":    {"K": "V"}               # 选填，凭据键由 runner 拒绝
        }

    执行结果（成功与失败同构）回灌为 JSON：``outcome`` / ``reason`` /
    ``stdout`` / ``stderr`` / ``artifacts[]``（path、bytes、sha256）等。
    """

    def __init__(
        self,
        runner: Optional[SandboxRunner],
        locate_skill: SkillLocator,
        *,
        output_summary_chars: int = 2000,
        max_result_chars: int = 8000,
        configuration_error: str = '',
    ) -> None:
        self._runner = runner
        self._locate = locate_skill
        self._output_summary_chars = max(0, int(output_summary_chars))
        self._max_result_chars = max(0, int(max_result_chars))
        self._configuration_error = configuration_error or ''

    @classmethod
    def unavailable(cls, *, output_summary_chars: int = 2000,
                    max_result_chars: int = 8000,
                    configuration_error: str = '') -> 'SandboxScriptDispatcher':
        """未装配执行器：T1 调用显式失败（fail closed），不做静默降级。"""
        return cls(None, lambda _name: None,
                   output_summary_chars=output_summary_chars,
                   max_result_chars=max_result_chars,
                   configuration_error=configuration_error)

    # ------------------------------------------------------------ entry

    def execute(
        self, call: ToolCallRequest, tier: SandboxTier | str | object,
    ) -> Tuple[ToolResult, Optional[SandboxFailure]]:
        resolved = _as_tier(tier)
        if resolved is not SandboxTier.T1_TRUSTED_SCRIPT:
            return self._reject(
                call, SandboxFailureReason.UNSUPPORTED_TIER,
                f'仅支持 {SandboxTier.T1_TRUSTED_SCRIPT.value} 的工具在沙箱执行，'
                f'收到 {_tier_text(tier)}（T2 首期不执行，待 INT-2489）')
        if self._runner is None:
            return self._reject(
                call, SandboxFailureReason.RUNNER_ERROR,
                f'沙箱执行器未就绪：{self._configuration_error or "未装配"}')

        request, error = self._build_request(call)
        if request is None:
            assert error is not None
            return self._reject(call, error[0], error[1])

        try:
            result = self._runner.run_trusted_script(request)
        except Exception as exc:  # noqa: BLE001 - 沙箱异常必须收口，不炸 Loop
            logger.exception('沙箱执行异常 skill=%s script=%s',
                             request.skill_name, request.script)
            return self._reject(
                call, SandboxFailureReason.RUNNER_ERROR,
                f'沙箱执行器异常：{exc}')
        return self._map_result(call, request, result)

    # ------------------------------------------------------------ request

    def _build_request(self, call: ToolCallRequest) -> Tuple[
            Optional[SandboxRequest],
            Optional[Tuple[SandboxFailureReason, str]]]:
        arguments = call.arguments if isinstance(call.arguments, Mapping) else {}
        skill_name = arguments.get(ARG_SKILL)
        script = arguments.get(ARG_SCRIPT)
        if not isinstance(skill_name, str) or not skill_name.strip():
            return None, (SandboxFailureReason.INVALID_INVOCATION,
                          f'缺少必填参数：{ARG_SKILL}')
        if not isinstance(script, str) or not script.strip():
            return None, (SandboxFailureReason.INVALID_INVOCATION,
                          f'缺少必填参数：{ARG_SCRIPT}')

        raw_args = arguments.get(ARG_ARGS) or []
        if not isinstance(raw_args, (list, tuple)) or any(
                not isinstance(item, str) for item in raw_args):
            return None, (SandboxFailureReason.INVALID_INVOCATION,
                          f'{ARG_ARGS} 必须是字符串数组')

        raw_env = arguments.get(ARG_ENV) or {}
        if not isinstance(raw_env, Mapping):
            return None, (SandboxFailureReason.INVALID_INVOCATION,
                          f'{ARG_ENV} 必须是字符串映射')
        env: Dict[str, str] = {}
        for key, value in raw_env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return None, (SandboxFailureReason.INVALID_INVOCATION,
                              f'{ARG_ENV} 的键与值必须是字符串')
            env[key] = value

        located = self._locate(skill_name.strip())
        if located is None:
            return None, (SandboxFailureReason.INVALID_INVOCATION,
                          f'未知 Skill：{skill_name.strip()}')
        relative = script.replace('\\', '/').strip()
        # 只允许执行 SkillRegistry 登记过的 scripts/ 脚本：模型不能拿任意
        # 相对路径去撞（路径穿越 / 绝对路径仍由 runner 再校验一次）。
        if relative not in located.scripts:
            return None, (SandboxFailureReason.SCRIPT_NOT_FOUND,
                          f'Skill {located.skill_name} 未登记脚本：{relative}')

        return SandboxRequest(
            skill_name=located.skill_name,
            skill_root=located.root,
            script=relative,
            args=tuple(str(item) for item in raw_args),
            env=env,
            tier=SandboxTier.T1_TRUSTED_SCRIPT,
        ), None

    # ------------------------------------------------------------ mapping

    def _map_result(self, call: ToolCallRequest, request: SandboxRequest,
                    result: SandboxResult) -> Tuple[
                        ToolResult, Optional[SandboxFailure]]:
        detail = result.detail
        if not result.succeeded and not detail:
            detail = _default_failure_detail(result)
        content = self._payload(
            outcome=result.outcome, reason=result.reason.value,
            exit_code=result.exit_code, duration_ms=result.duration_ms,
            stdout=result.stdout, stderr=result.stderr,
            timed_out=result.timed_out,
            output_truncated=result.output_truncated,
            container_id=result.container_id, detail=detail,
            artifacts=result.artifacts,
            skill=request.skill_name, script=request.script,
        )
        if result.succeeded:
            return ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name,
                ok=True, content=content, error_code='OK'), None

        failure = SandboxFailure(
            outcome=result.outcome, reason=result.reason,
            tool_call_id=call.tool_call_id, detail=detail,
            exit_code=result.exit_code,
        )
        return ToolResult(
            tool_call_id=call.tool_call_id, tool=call.name,
            ok=False, content=content,
            error_code=result.reason.value), failure

    def _reject(self, call: ToolCallRequest, reason: SandboxFailureReason,
                detail: str) -> Tuple[ToolResult, Optional[SandboxFailure]]:
        logger.warning('沙箱工具调用被拒绝 tool=%s reason=%s detail=%s',
                       call.name, reason.value, detail)
        content = self._payload(
            outcome=SandboxOutcome.FAILED, reason=reason.value,
            exit_code=-1, duration_ms=0, stdout='', stderr='',
            timed_out=False, output_truncated=False, container_id='',
            detail=detail, artifacts=(), skill=None, script=None,
        )
        failure = SandboxFailure(
            outcome=SandboxOutcome.FAILED, reason=reason,
            tool_call_id=call.tool_call_id, detail=detail, exit_code=-1)
        return ToolResult(
            tool_call_id=call.tool_call_id, tool=call.name,
            ok=False, content=content, error_code=reason.value), failure

    # ------------------------------------------------------------ payload

    def _payload(self, *, outcome: SandboxOutcome, reason: str, exit_code: int,
                 duration_ms: int, stdout: str, stderr: str, timed_out: bool,
                 output_truncated: bool, container_id: str, detail: str,
                 artifacts, skill: Optional[str],
                 script: Optional[str]) -> str:
        data: Dict[str, Any] = {
            'ok': outcome is SandboxOutcome.SUCCEEDED,
            'outcome': outcome.value,
            'reason': reason,
            'skill': skill,
            'script': script,
            'exit_code': exit_code,
            'duration_ms': duration_ms,
            'timed_out': timed_out,
            'output_truncated': output_truncated,
            'container_id': container_id,
            'detail': detail,
            'artifact_count': len(artifacts or ()),
            'artifacts': [
                {'path': item.relative_path, 'bytes': item.size_bytes,
                 'sha256': item.sha256}
                for item in (artifacts or ())
            ],
        }
        clipped: Dict[str, bool] = {}
        for key, value in (('stdout', stdout), ('stderr', stderr)):
            text, cut = _clip(value, self._output_summary_chars)
            data[key] = text
            clipped[key] = cut
        data['stdout_truncated'] = clipped['stdout']
        data['stderr_truncated'] = clipped['stderr']
        return _dumps_within(data, self._max_result_chars)


# ------------------------------------------------------------------ helpers


def _as_tier(value: SandboxTier | str | object) -> Optional[SandboxTier]:
    if isinstance(value, SandboxTier):
        return value
    try:
        return SandboxTier(str(value))
    except ValueError:
        return None


def _tier_text(value: SandboxTier | str | object) -> str:
    if isinstance(value, SandboxTier):
        return value.value
    return f'{value!r}'


def _clip(text: str, limit: int) -> Tuple[str, bool]:
    text = text or ''
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[:limit] + '…（已截断）', True


def _default_failure_detail(result: SandboxResult) -> str:
    if result.reason is SandboxFailureReason.EXIT_CODE_NONZERO:
        return f'脚本非零退出：{result.exit_code}'
    return result.reason.value


def _dumps_within(payload: Dict[str, Any], limit: int) -> str:
    """序列化并保证长度不超过 ``limit``（先收敛输出摘要，再收敛产物清单）。"""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if limit <= 0 or len(text) <= limit:
        return text

    # 1) 输出摘要各收到 limit/4（保留结构化字段，模型仍能看懂原因）
    for key in _OUTPUT_KEYS:
        payload[key], cut = _clip(payload.get(key) or '', max(0, limit // 4))
        payload[f'{key}_truncated'] = payload.get(f'{key}_truncated') or cut
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return text

    # 2) 产物清单只保留计数（清单本身已在 tool_call.result 里可审计）
    artifacts = payload.get('artifacts') or []
    payload['artifact_count'] = len(artifacts)
    payload['artifacts'] = []
    payload['artifacts_omitted'] = True
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return text

    # 3) 输出整体省略
    for key in _OUTPUT_KEYS:
        payload[key] = ''
        payload[f'{key}_omitted'] = True
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return text

    # 4) 兜底：极端超长 detail 才走到这里，宁可截断也不会回灌超长内容
    return text[:limit]


def disabled_executor(*, output_summary_chars: int = 2000,
                      max_result_chars: int = 8000,
                      configuration_error: str = '') -> SandboxScriptDispatcher:
    """未装配执行器时的常量实例（供 Loop 直接构造使用）。"""
    return SandboxScriptDispatcher.unavailable(
        output_summary_chars=output_summary_chars,
        max_result_chars=max_result_chars,
        configuration_error=configuration_error)


__all__ = [
    'SandboxFailure', 'SandboxFailureLog', 'SandboxScriptDispatcher',
    'SandboxToolExecutor', 'SkillLocator', 'SkillScripts',
    'disabled_executor',
]
