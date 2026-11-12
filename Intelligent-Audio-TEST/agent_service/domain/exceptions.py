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
