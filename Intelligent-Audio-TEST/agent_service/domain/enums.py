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


class SandboxRuntime(str, Enum):
    """T2 沙箱运行时（§7，INT-2489）。

    失败/停止原因码统一用应用层 ``SandboxFailureReason``（T1 起已有的唯一枚举，
    T2 只补充 ``T2_RUNTIME_UNAVAILABLE`` 等取值），不再另造一套魔法值。
    """

    GVISOR = 'gvisor'
    FIRECRACKER = 'firecracker'


class CompactionLevel(str, Enum):
    """上下文压缩层级（§8.2）。M0 启用 L1/L2/L3；L4 属 M3。"""

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
    # 对话沉淀建议（INT-2549 §4.4 第 7 条第④项）：run 正常结束后产出
    # 「把本次流程沉淀为 Skill」的草案建议。仅事件、不落库，用户确认后
    # 才走 POST /skills 创建 DRAFT。
    SKILL_DRAFT_SUGGESTED = 'skill_draft_suggested'
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
    """agent_tool_call 状态。

    ``WAITING_APPROVAL``（INT-2466）：写调用已生成提案，等待人工审批；
    既非执行中、也非失败，恢复时按审批表状态继续处置。
    """

    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    WAITING_APPROVAL = 'WAITING_APPROVAL'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    DENIED = 'DENIED'


class ApprovalStatus(str, Enum):
    """``agent_approval.status``（§10；前端契约只认这四个取值）。

    ``REJECTED`` 同时承载「拒绝」与「随 run 取消作废」：两者都不执行、
    都由 ``decided_by`` / ``decided_at`` 留痕，不另造前端不认识的取值。
    """

    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    EXPIRED = 'EXPIRED'


class ApprovalDecision(str, Enum):
    """审批决议（POST /api/v1/agent/approvals/{id}/decision 的请求取值）。"""

    APPROVE = 'APPROVE'
    REJECT = 'REJECT'

    @property
    def target(self) -> ApprovalStatus:
        return (ApprovalStatus.APPROVED if self is ApprovalDecision.APPROVE
                else ApprovalStatus.REJECTED)


class LlmMessageRole(str, Enum):
    """模型消息角色（OpenAI 兼容口径）。"""

    SYSTEM = 'system'
    USER = 'user'
    ASSISTANT = 'assistant'
    TOOL = 'tool'


class SkillScope(str, Enum):
    """Skill 来源三层（INT-2549 §4.4「来源与优先级」）。

    优先级 ``USER > TENANT > PLATFORM``：同名时高层生效、低层在列表里带
    ``masked_by`` 标注。``PLATFORM`` 是 ``skills/`` 只读挂载，无写入口。
    """

    PLATFORM = 'PLATFORM'
    TENANT = 'TENANT'
    USER = 'USER'

    @property
    def precedence(self) -> int:
        """数值越大越优先（去重排序用）。"""
        return _SKILL_SCOPE_PRECEDENCE[self]


_SKILL_SCOPE_PRECEDENCE = {
    SkillScope.PLATFORM: 0,
    SkillScope.TENANT: 1,
    SkillScope.USER: 2,
}


class SkillStatus(str, Enum):
    """自定义 Skill 生命周期状态（§4.4「安全与生命周期」）。

    只有 ``ACTIVE`` 参与自动触发与 L1 列表；``DRAFT`` 需过发布门槛才转
    ``ACTIVE``；``DISABLED`` 立即从 L1 / 激活候选消失（在办 run 按
    ``agent_run_skill`` 快照继续）。

    INT-2551：``TENANT`` 级多一个 ``PENDING_REVIEW``（提交审核后、管理员
    决策前）。该状态**冻结内容**（PUT 被拒，须先 withdraw），且同样不参与
    自动触发。``USER`` 级不经过该状态（本人显式发布），由状态机拒绝。
    """

    DRAFT = 'DRAFT'
    PENDING_REVIEW = 'PENDING_REVIEW'
    ACTIVE = 'ACTIVE'
    DISABLED = 'DISABLED'

    @property
    def participates_in_trigger(self) -> bool:
        """是否进入自动触发候选 / L1 列表。"""
        return self is SkillStatus.ACTIVE

    @property
    def is_frozen(self) -> bool:
        """内容是否冻结（审核中不许改，必须先撤回）。"""
        return self is SkillStatus.PENDING_REVIEW


class SkillReviewAction(str, Enum):
    """``agent_skill_review.action`` 取值（INT-2551 审核流状态机的迁移动作）。

    每个动作对应状态机里唯一一条迁移；``REJECT`` 与 ``WITHDRAW`` 都回
    ``DRAFT``，但语义不同（审批人驳回 / 提交人撤回），审计链必须能区分。
    """

    SUBMIT = 'SUBMIT'
    APPROVE = 'APPROVE'
    REJECT = 'REJECT'
    WITHDRAW = 'WITHDRAW'
    DISABLE = 'DISABLE'

    @property
    def requires_reason(self) -> bool:
        """驳回必须带原因（其余动作原因可空）。"""
        return self is SkillReviewAction.REJECT


class SkillReviewDecision(str, Enum):
    """``POST /skills/{id}/review`` 的请求取值（与 ``SkillReviewAction`` 区分）。"""

    APPROVE = 'APPROVE'
    REJECT = 'REJECT'

    @property
    def action(self) -> SkillReviewAction:
        return (SkillReviewAction.APPROVE
                if self is SkillReviewDecision.APPROVE
                else SkillReviewAction.REJECT)


class SkillIssueCode(str, Enum):
    """Skill 校验问题码（§4.2 frontmatter 契约）。

    目录级失败码（INT-2506）由仓储层回传：扫描阶段就必须给出原因码，不允许
    空目录 / 错挂载 / 目录缺 SKILL.md 静默丢 Skill。

    INT-2549 补自定义 Skill 落库前逐项校验码（保存 / 发布共用同一套
    ``validate_skill()``），禁止在服务层散落字符串。
    """

    SKILLS_ROOT_MISSING = 'SKILLS_ROOT_MISSING'
    SKILLS_ROOT_UNREADABLE = 'SKILLS_ROOT_UNREADABLE'
    SKILLS_ROOT_EMPTY = 'SKILLS_ROOT_EMPTY'
    SKILL_FILE_MISSING = 'SKILL_FILE_MISSING'
    INVALID_FRONTMATTER = 'INVALID_FRONTMATTER'
    MISSING_NAME = 'MISSING_NAME'
    MISSING_DESCRIPTION = 'MISSING_DESCRIPTION'
    DIRECTORY_NAME_MISMATCH = 'DIRECTORY_NAME_MISMATCH'
    DUPLICATE_NAME = 'DUPLICATE_NAME'
    BODY_TOO_LONG = 'BODY_TOO_LONG'
    MISSING_REQUIRED_SECTION = 'MISSING_REQUIRED_SECTION'
    UNKNOWN_TOOL = 'UNKNOWN_TOOL'
    L1_BUDGET_EXCEEDED = 'L1_BUDGET_EXCEEDED'
    # 目录里一个 Skill 都没装到（空目录 / 缺 SKILL.md）：部署级故障，启动即失败
    EMPTY_SKILLS_ROOT = 'EMPTY_SKILLS_ROOT'
    # ---- INT-2549 自定义 Skill 写入校验 ----
    INVALID_NAME = 'INVALID_NAME'
    NAME_CONFLICT = 'NAME_CONFLICT'
    BODY_TOO_LARGE = 'BODY_TOO_LARGE'
    RESOURCE_TOO_LARGE = 'RESOURCE_TOO_LARGE'
    PACKAGE_TOO_LARGE = 'PACKAGE_TOO_LARGE'
    TOO_MANY_ENTRIES = 'TOO_MANY_ENTRIES'
    INVALID_PATH = 'INVALID_PATH'
    SYMLINK_REJECTED = 'SYMLINK_REJECTED'
    EXTERNAL_LINK_REJECTED = 'EXTERNAL_LINK_REJECTED'
    PERMISSION_ESCALATION = 'PERMISSION_ESCALATION'
    EMBEDDED_SECRET = 'EMBEDDED_SECRET'
    INTERNAL_ADDRESS = 'INTERNAL_ADDRESS'
    BINARY_CONTENT = 'BINARY_CONTENT'
    INJECTION_DETECTED = 'INJECTION_DETECTED'
    GATE_INSUFFICIENT_GOLDEN_TASKS = 'GATE_INSUFFICIENT_GOLDEN_TASKS'
    GATE_TRIGGER_FAILED = 'GATE_TRIGGER_FAILED'


class SkillIssueSeverity(str, Enum):
    """问题严重度：ERROR 剔除该 Skill，WARNING 仅告警。"""

    ERROR = 'ERROR'
    WARNING = 'WARNING'


class SkillErrorCode(str, Enum):
    """Skill 接口错误码（§4.4 接口草案，枚举化、不散落字符串）。"""

    SKILL_NAME_CONFLICT = 'SKILL_NAME_CONFLICT'
    SKILL_VALIDATION_FAILED = 'SKILL_VALIDATION_FAILED'
    SKILL_PERMISSION_ESCALATION = 'SKILL_PERMISSION_ESCALATION'
    SKILL_NOT_FOUND = 'SKILL_NOT_FOUND'
    SKILL_STATUS_INVALID = 'SKILL_STATUS_INVALID'
    SKILL_IMPORT_INVALID = 'SKILL_IMPORT_INVALID'
    SKILL_INJECTION_DETECTED = 'SKILL_INJECTION_DETECTED'
    SKILL_GATE_FAILED = 'SKILL_GATE_FAILED'
    # ---- INT-2551 TENANT 级共享 + 发布审核流 ----
    # 非本租户管理员（缺 agent:skill:admin 权限码或缺管理员角色）
    SKILL_REVIEW_FORBIDDEN = 'SKILL_REVIEW_FORBIDDEN'
    # 创建人审批自己提交的版本
    SKILL_SELF_REVIEW_FORBIDDEN = 'SKILL_SELF_REVIEW_FORBIDDEN'


# ---------------------------------------------------------------- 长期记忆（INT-2490）
#
# 取值与方案 §8.6 / §8.6.1 及卡面接口草案逐字一致（记忆工具对外 Schema
# 直接由这些枚举生成，不在注册表里再写一份字面量）。


class MemoryScope(str, Enum):
    """``memory_search`` 检索范围（tenant / owner 过滤由服务端强制附加）。"""

    USER = 'USER'
    PROJECT = 'PROJECT'
    SKILL_REFERENCES = 'SKILL_REFERENCES'


class MemorySection(str, Enum):
    """``memory_write`` 可写区段（只允许调用者自己的目录）。"""

    USER_PROFILE = 'USER_PROFILE'
    PROJECT_MEMORY = 'PROJECT_MEMORY'
    TOPIC = 'TOPIC'


class MemoryWriteStatus(str, Enum):
    """记忆文件式提案状态（INT-2490；正文不入库，故不并入 agent_approval）。"""

    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


class SensitiveRuleAction(str, Enum):
    """敏感信息扫描规则动作：拦截整笔写入 / 脱敏后放行。"""

    BLOCK = 'block'
    REDACT = 'redact'
