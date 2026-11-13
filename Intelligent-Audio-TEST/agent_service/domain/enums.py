# -*- coding: utf-8 -*-
"""agent_service 领域枚举。

落地方案 §5.3：RunStatus / ToolRisk / SandboxTier / CompactionLevel / EventType
全部枚举化，禁止字符串魔法值。持久化时统一写 ``enum.value``。
"""
from enum import Enum


class RunStatus(str, Enum):
    """Run 状态机取值（§9.1）。"""

    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    WAITING_APPROVAL = 'WAITING_APPROVAL'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    BUDGET_EXCEEDED = 'BUDGET_EXCEEDED'

    @property
    def is_terminal(self) -> bool:
        """终态：不再接受状态推进。"""
        return self in _TERMINAL_RUN_STATUSES

    @property
    def is_active(self) -> bool:
        """仍在推进（可被取消 / 可被恢复）。"""
        return self in _ACTIVE_RUN_STATUSES


_TERMINAL_RUN_STATUSES = frozenset({
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.BUDGET_EXCEEDED,
})

_ACTIVE_RUN_STATUSES = frozenset({
    RunStatus.QUEUED,
    RunStatus.RUNNING,
    RunStatus.WAITING_APPROVAL,
})


class ToolRisk(str, Enum):
    """工具风险等级（§6.1）。写操作必须走审批，M0 只执行 READ。"""

    READ = 'READ'
    WRITE = 'WRITE'
    DESTRUCTIVE = 'DESTRUCTIVE'

    @property
    def requires_approval(self) -> bool:
        """是否需要审批提案（§5.2 硬规则 5）。"""
        return self is not ToolRisk.READ


class SandboxTier(str, Enum):
    """沙箱层级（§7）。"""

    T0_NONE = 'T0_NONE'
    T1_TRUSTED_SCRIPT = 'T1_TRUSTED_SCRIPT'
    T2_UNTRUSTED_CODE = 'T2_UNTRUSTED_CODE'


class CompactionLevel(str, Enum):
    """上下文压缩层级（§8.2）。M0 只记录快照，不启用压缩。"""

    L1_TRIM = 'L1_TRIM'
    L2_DEDUPE = 'L2_DEDUPE'
    L3_MEMO = 'L3_MEMO'
    L4_REBUILD = 'L4_REBUILD'


class EventType(str, Enum):
    """SSE 事件类型（§5.3）。落库与下发使用同一枚举。"""

    RUN_STARTED = 'run_started'
    MESSAGE_DELTA = 'message_delta'
    TOOL_CALL = 'tool_call'
    TOOL_RESULT = 'tool_result'
    APPROVAL_REQUIRED = 'approval_required'
    CONTEXT_COMPACTED = 'context_compacted'
    RUN_FINISHED = 'run_finished'
    ERROR = 'error'


class LlmProtocol(str, Enum):
    """用户模型供应商协议（§6.4-5）。"""

    OPENAI_COMPATIBLE = 'OPENAI_COMPATIBLE'
    ANTHROPIC = 'ANTHROPIC'


class ProviderStatus(str, Enum):
    """供应商状态（§10 agent_llm_provider.status）。"""

    ACTIVE = 'ACTIVE'
    INVALID = 'INVALID'
    DELETED = 'DELETED'


class ContextWindowSource(str, Enum):
    """有效上下文窗口来源（§6.4-9）。"""

    USER_OVERRIDE = 'USER_OVERRIDE'
    MODEL_DEFAULT = 'MODEL_DEFAULT'
    FALLBACK = 'FALLBACK'


class StepStatus(str, Enum):
    """agent_step 状态。"""

    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


class ToolCallStatus(str, Enum):
    """agent_tool_call 状态。"""

    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    DENIED = 'DENIED'


class LlmMessageRole(str, Enum):
    """模型消息角色（OpenAI 兼容口径）。"""

    SYSTEM = 'system'
    USER = 'user'
    ASSISTANT = 'assistant'
    TOOL = 'tool'


class SkillIssueCode(str, Enum):
    """Skill 校验问题码（§4.2 frontmatter 契约）。"""

    INVALID_FRONTMATTER = 'INVALID_FRONTMATTER'
    MISSING_NAME = 'MISSING_NAME'
    MISSING_DESCRIPTION = 'MISSING_DESCRIPTION'
    DIRECTORY_NAME_MISMATCH = 'DIRECTORY_NAME_MISMATCH'
    DUPLICATE_NAME = 'DUPLICATE_NAME'
    BODY_TOO_LONG = 'BODY_TOO_LONG'
    MISSING_REQUIRED_SECTION = 'MISSING_REQUIRED_SECTION'
    UNKNOWN_TOOL = 'UNKNOWN_TOOL'
    L1_BUDGET_EXCEEDED = 'L1_BUDGET_EXCEEDED'


class SkillIssueSeverity(str, Enum):
    """问题严重度：ERROR 剔除该 Skill，WARNING 仅告警。"""

    ERROR = 'ERROR'
    WARNING = 'WARNING'
