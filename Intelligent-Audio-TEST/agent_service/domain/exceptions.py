# -*- coding: utf-8 -*-
"""agent_service 领域异常（不依赖框架，接口层再映射 HTTP 状态码）。"""


class AgentDomainError(Exception):
    """agent 域异常基类。"""


class InvalidRunTransition(AgentDomainError):
    """非法状态迁移（§9.1 状态机拒绝）。"""

    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f'非法 Run 状态迁移: {current} -> {target}')


class RunNotFound(AgentDomainError):
    """Run 不存在，或不属于当前用户/租户（对外统一 404，不泄漏存在性）。"""


class SessionNotFound(AgentDomainError):
    """Session 不存在，或不属于当前用户/租户。"""


class RunCancelled(AgentDomainError):
    """Run 已被取消：当前模型调用中途中止。"""


class LlmConfigurationError(AgentDomainError):
    """LLM 配置缺失 / 非法。"""


class LlmProviderNotConfigured(AgentDomainError):
    """用户没有可用的模型供应商：run 必须以 LLM_PROVIDER_NOT_CONFIGURED 失败。

    绝不回退平台 Key，也不发起任何模型请求（§6.4-4）。
    """

    code = 'LLM_PROVIDER_NOT_CONFIGURED'


class ProviderNotFound(AgentDomainError):
    """供应商不存在、不属于当前用户/租户，或已逻辑删除。"""


class InvalidContextWindow(AgentDomainError):
    """上下文窗口覆盖值非法（超出 8k–2M 或未 1024 对齐）。"""


class InvalidProviderConfiguration(AgentDomainError):
    """供应商字段非法（协议 / 地址 / 模型名 / Key 为空或超长）。"""


class CredentialKeyUnavailable(AgentDomainError):
    """主密钥不可用（生产缺失即 fail-fast；开发环境显式配置后可用）。"""


class CredentialDecryptError(AgentDomainError):
    """密文解密失败（密钥版本缺失 / 密文被篡改 / AAD 不匹配）。"""


class LlmInvocationError(AgentDomainError):
    """模型调用失败（上游错误、超时、非法响应）。"""

    def __init__(self, message: str, code: str = 'LLM_INVOCATION_ERROR'):
        self.code = code
        super().__init__(message)


class BudgetExceeded(AgentDomainError):
    """预算超限：由 Loop 收口为 BUDGET_EXCEEDED 状态。"""

    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(f'预算超限: {kind}')


class ApprovalNotFound(AgentDomainError):
    """审批单不存在，或所属 run 不属于当前用户/租户（对外统一 404）。"""


class ApprovalConflict(AgentDomainError):
    """审批单已被其它请求处理（并发审批 / 已决），本次决策不生效。"""

    code = 'APPROVAL_ALREADY_DECIDED'


class ApprovalExpired(AgentDomainError):
    """审批单已过期：不执行，也不允许再决策。"""

    code = 'APPROVAL_EXPIRED'

    def __init__(self, approval_id: str, run_id: str):
        self.approval_id = approval_id
        self.run_id = run_id
        super().__init__(f'审批单已过期: {approval_id}')


class ApprovalConfirmationRequired(AgentDomainError):
    """破坏性操作（DESTRUCTIVE）必须二次确认（INT-2467）。

    批准请求除 ``APPROVE`` 外还要显式 ``confirm=true``：单次审批不足以放行
    重启 / 关机 / 安装 / 卸载 / 批量设备控制这类不可回滚动作。拒绝不需要。
    """

    code = 'APPROVAL_CONFIRMATION_REQUIRED'

    def __init__(self, approval_id: str, tool: str = ''):
        self.approval_id = approval_id
        self.tool = tool or ''
        super().__init__(
            f'破坏性操作需要二次确认（approval_id={approval_id}'
            f'{", tool=" + tool if tool else ""}）')


class SkillNotAvailable(AgentDomainError):
    """Skill 未注册，或当前用户权限不满足（§4.2 规则 7）。"""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f'Skill 不可用: {name}')


class SkillValidationError(AgentDomainError):
    """Skill 校验失败（严格模式启动即失败，§4.2）。"""

    def __init__(self, issues):
        self.issues = tuple(issues)
        detail = '; '.join(f'{i.code.value}:{i.skill or i.path}' for i in issues)
        super().__init__(f'Skill 校验失败（{len(self.issues)} 项）: {detail}')


# ---------------------------------------------------------------- 自定义 Skill（INT-2549）


class SkillServiceError(AgentDomainError):
    """自定义 Skill 域异常基类：``code`` 即接口错误码（§4.4 枚举）。"""

    code = 'SKILL_VALIDATION_FAILED'

    def __init__(self, message: str, *, issues=()):
        self.issues = tuple(issues or ())
        super().__init__(message)


class SkillNotFound(SkillServiceError):
    """Skill 不存在 / 非本人可见 / 无写入口（对外统一 404，不泄漏存在性）。"""

    code = 'SKILL_NOT_FOUND'


class SkillNameConflict(SkillServiceError):
    """同名冲突：与 PLATFORM 同名或同作用域重名（拒绝，不静默覆盖）。"""

    code = 'SKILL_NAME_CONFLICT'


class SkillPermissionEscalation(SkillServiceError):
    """``permissions`` 超出当前用户权限（不得提权）。"""

    code = 'SKILL_PERMISSION_ESCALATION'


class SkillStatusInvalid(SkillServiceError):
    """状态迁移非法（例如 ACTIVE 才能停用、DRAFT 才能发布）。"""

    code = 'SKILL_STATUS_INVALID'


class SkillImportInvalid(SkillServiceError):
    """zip 导入非法（结构 / 体积 / 路径 / 压缩比 / 二进制）。"""

    code = 'SKILL_IMPORT_INVALID'


class SkillInjectionDetected(SkillServiceError):
    """正文命中注入规则：可存草稿，禁止发布为 ACTIVE。"""

    code = 'SKILL_INJECTION_DETECTED'


class SkillGateFailed(SkillServiceError):
    """发布门槛未通过（golden tasks 数量 / 触发判定）。"""

    code = 'SKILL_GATE_FAILED'


# ---------------------------------------------------------------- 长期记忆（INT-2490）


class MemoryError(AgentDomainError):
    """记忆域异常基类：``code`` 直接作为工具 / 审计的 result_code。"""

    code = 'MEMORY_ERROR'

    def __init__(self, message: str, *, code: str = ''):
        if code:
            self.code = code
        super().__init__(message)


class MemoryPathRejected(MemoryError):
    """路径越界 / 非法（``..``、绝对路径、``~``、软链穿越）。"""

    code = 'MEMORY_PATH_REJECTED'


class MemorySensitiveRejected(MemoryError):
    """命中拦截级敏感信息规则：整笔写入拒绝，不产生提案。"""

    code = 'MEMORY_SENSITIVE_CONTENT'


class MemoryProposalNotFound(MemoryError):
    """提案不存在，或不属于当前用户 / 租户（对外统一 404，不泄漏存在性）。"""

    code = 'MEMORY_PROPOSAL_NOT_FOUND'


class MemoryProposalConflict(MemoryError):
    """批准时目标文件已被改动：拒绝覆盖，保留本次提案。"""

    code = 'MEMORY_WRITE_CONFLICT'


class MemoryBackendUnavailable(MemoryError):
    """检索后端（``rg``）不可用：显式失败，不静默返回空结果。"""

    code = 'MEMORY_BACKEND_UNAVAILABLE'


class MemoryPermissionDenied(MemoryError):
    """管理端 / break-glass 权限不足。"""

    code = 'MEMORY_PERMISSION_DENIED'
