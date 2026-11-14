# -*- coding: utf-8 -*-
"""agent_service PO 模型（落地方案 §10）。

表：agent_session / agent_run / agent_run_event / agent_step /
    agent_tool_call / agent_artifact / agent_context_snapshot
    + agent_llm_provider（INT-2488 用户自带供应商密钥库）
    + agent_approval（INT-2466 写操作审批单）
    + agent_skill / agent_skill_version / agent_run_skill（INT-2549 自定义 Skill）
    + agent_skill_review（INT-2551 TENANT 级审核流审计链）

口径：
- 主键统一 UUID 字符串（分布式 worker 与断点恢复不依赖自增序列）；
- 时间戳 UTC naive（与仓库写库口径一致），带 DB 级 DEFAULT；
- 不用外键（仓库基线：引用完整性由应用层管理）；
- 索引名全局唯一前缀 ``ix_agent_`` / ``uq_agent_``。
"""
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Index, Integer, JSON, String, Text,
    UniqueConstraint, func, text,
)

from agent_service.domain.enums import SkillScope
from shared.models.database import Base
from shared.utils.time_utils import utcnow

_PK = String(36)
# 局部唯一索引谓词（枚举取值，不写魔法字符串）
_SCOPE_USER_PREDICATE = "scope = '%s'" % SkillScope.USER.value
_SCOPE_TENANT_PREDICATE = "scope = '%s'" % SkillScope.TENANT.value


class AgentSession(Base):
    """会话表。"""

    __tablename__ = 'agent_session'
    __table_args__ = (
        Index('ix_agent_session_owner', 'owner_id', 'created_at'),
        Index('ix_agent_session_tenant', 'tenant_id', 'owner_id'),
    )

    id = Column(_PK, primary_key=True)
    owner_id = Column(BigInteger, nullable=False, comment='会话归属用户')
    tenant_id = Column(String(64), nullable=False, comment='租户')
    title = Column(String(200), nullable=False, default='', comment='会话标题')
    active_skill = Column(String(100), nullable=True, comment='当前激活 Skill（M0 预留）')
    model = Column(String(100), nullable=False, default='', comment='会话默认模型')
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now(), onupdate=utcnow)


class AgentRun(Base):
    """Run 表（一次用户消息触发的完整 Agent 循环）。"""

    __tablename__ = 'agent_run'
    __table_args__ = (
        Index('ix_agent_run_owner_status', 'owner_id', 'status'),
        Index('ix_agent_run_session', 'session_id', 'created_at'),
        Index('uq_agent_run_idempotency', 'idempotency_key', unique=True),
    )

    id = Column(_PK, primary_key=True)
    session_id = Column(_PK, nullable=False)
    owner_id = Column(BigInteger, nullable=False)
    tenant_id = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, comment='RunStatus')
    model = Column(String(100), nullable=False, default='')
    budget = Column(JSON, nullable=True, comment='本次 run 的预算快照')
    token_in = Column(Integer, nullable=False, default=0, server_default='0')
    token_out = Column(Integer, nullable=False, default=0, server_default='0')
    idempotency_key = Column(String(128), nullable=True, comment='提交幂等键（唯一）')
    cancel_requested = Column(Boolean, nullable=False, default=False,
                              server_default=text('false'))
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now(), onupdate=utcnow)


class AgentRunEvent(Base):
    """Run 事件表：SSE 的唯一事实源，sequence 在 run 内严格递增。"""

    __tablename__ = 'agent_run_event'
    __table_args__ = (
        UniqueConstraint('run_id', 'sequence', name='uq_agent_run_event_sequence'),
    )

    id = Column(_PK, primary_key=True)
    run_id = Column(_PK, nullable=False)
    sequence = Column(BigInteger, nullable=False, comment='run 内严格递增')
    type = Column(String(50), nullable=False, comment='EventType')
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())


class AgentStep(Base):
    """Step 表：Loop 中每一轮模型调用一个 step。"""

    __tablename__ = 'agent_step'
    # 唯一约束已建 (run_id, index) 索引，可服务 run_id 前缀查询，
    # 不再额外建同列普通索引（INT-2516）。
    __table_args__ = (
        UniqueConstraint('run_id', 'index', name='uq_agent_step_run_index'),
    )

    id = Column(_PK, primary_key=True)
    run_id = Column(_PK, nullable=False)
    index = Column(Integer, nullable=False, comment='run 内轮次序号（从 0 开始）')
    plan_snapshot = Column(JSON, nullable=True, comment='scratchpad / 计划快照')
    status = Column(String(20), nullable=False, comment='StepStatus')
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now(), onupdate=utcnow)


class AgentToolCall(Base):
    """工具调用表（按 tool_call_id 回灌，幂等键防重复执行）。"""

    __tablename__ = 'agent_tool_call'
    __table_args__ = (
        UniqueConstraint('run_id', 'tool_call_id', name='uq_agent_tool_call_run_call'),
        Index('ix_agent_tool_call_run', 'run_id', 'created_at'),
        Index('uq_agent_tool_call_idempotency', 'idempotency_key', unique=True),
    )

    id = Column(_PK, primary_key=True)
    run_id = Column(_PK, nullable=False)
    step_id = Column(_PK, nullable=True)
    tool_call_id = Column(String(128), nullable=False, comment='模型返回的 tool_call_id')
    tool = Column(String(100), nullable=False)
    arguments = Column(JSON, nullable=True)
    args_hash = Column(String(64), nullable=False)
    risk = Column(String(20), nullable=False, comment='ToolRisk')
    status = Column(String(20), nullable=False, comment='ToolCallStatus')
    result = Column(JSON, nullable=True, comment='工具结果（回灌模型 / 恢复用）')
    result_ref = Column(Text, nullable=True, comment='大结果外置引用')
    latency_ms = Column(Integer, nullable=True)
    permission_decision = Column(String(50), nullable=True, comment='allow / deny / approval_required')
    result_code = Column(String(50), nullable=True,
                         comment='工具结果码（OK / PERMISSION_DENIED / TOOL_NOT_ENABLED…）')
    error = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=True,
                             comment='run_id + step_id + tool_call_id + tool + args_hash')
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now(), onupdate=utcnow)


class AgentApproval(Base):
    """写调用审批单（INT-2466，§10）。

    - 一次 tool call 一张单：``(run_id, tool_call_id)`` 唯一，重复提案幂等；
    - ``proposal`` / ``diff`` 是审批人可见的内容（参数已按审计口径脱敏）；
    - ``decision_permissions`` 是决策时的实时权限快照，执行前据此重新校验
      「审批后权限是否还在」，不回读 run 发起时的旧权限；
    - 决策 / 过期都是 ``WHERE status='PENDING'`` 的条件更新，并发审批只有
      一个请求生效；
    - ``(status, expires_at)`` 索引服务过期扫描与待办列表。
    """

    __tablename__ = 'agent_approval'
    __table_args__ = (
        UniqueConstraint('run_id', 'tool_call_id',
                         name='uq_agent_approval_run_call'),
        Index('ix_agent_approval_status_expires', 'status', 'expires_at'),
        Index('ix_agent_approval_run', 'run_id', 'created_at'),
    )

    id = Column(_PK, primary_key=True)
    run_id = Column(_PK, nullable=False)
    tool_call_id = Column(String(128), nullable=False,
                          comment='模型返回的 tool_call_id')
    proposal = Column(JSON, nullable=False, default=dict,
                      comment='审批人可见的提案（参数已脱敏）')
    diff = Column(JSON, nullable=True, comment='变更预览 / diff（工具提供）')
    status = Column(String(20), nullable=False, comment='ApprovalStatus')
    expires_at = Column(DateTime, nullable=True, comment='过期时间（UTC naive）')
    decided_by = Column(BigInteger, nullable=True, comment='决策人 user_id')
    decided_at = Column(DateTime, nullable=True)
    decision_permissions = Column(JSON, nullable=True,
                                  comment='决策时的实时权限快照')
    created_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now(), onupdate=utcnow)


class AgentArtifact(Base):
    """Run 产物表（大结果 / 导出文件引用）。"""

    __tablename__ = 'agent_artifact'
    __table_args__ = (
        Index('ix_agent_artifact_run', 'run_id', 'created_at'),
    )

    id = Column(_PK, primary_key=True)
    run_id = Column(_PK, nullable=False)
    kind = Column(String(50), nullable=False)
    uri = Column(Text, nullable=False)
    size = Column(BigInteger, nullable=False, default=0, server_default='0')
    # 属性名不能叫 metadata（SQLAlchemy 保留），列名保持一致
    artifact_metadata = Column('metadata', JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())


class AgentContextSnapshot(Base):
    """上下文快照表（§8.5）：每次实际压缩落一条，含版本 / token / 被裁 ID /
    备忘 / 触发层级，调试模式可据此回放。"""

    __tablename__ = 'agent_context_snapshot'
    # 同上：(run_id, version) 唯一约束的索引已覆盖该前缀查询（INT-2516）。
    __table_args__ = (
        UniqueConstraint('run_id', 'version', name='uq_agent_context_snapshot_version'),
    )

    id = Column(_PK, primary_key=True)
    run_id = Column(_PK, nullable=False)
    version = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False, default=0, server_default='0')
    dropped_ids = Column(JSON, nullable=True)
    memo = Column(JSON, nullable=True)
    level = Column(String(20), nullable=False, comment='CompactionLevel')
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())


class AgentLlmProvider(Base):
    """用户模型供应商（§6.4 / §10 agent_llm_provider）。

    - ``api_key_ciphertext`` 只存 AES-256-GCM 密文（base64(nonce + blob)）；
    - ``api_key_mask`` 是脱敏回显串（``sk-****abcd``），列表读取不解密；
    - ``(owner_id, tenant_id)`` 维度下 is_default 唯一（部分唯一索引，已删除行不占位）；
    - 删除为逻辑删除：``status=DELETED`` 且密文 / 掩码清空。
    """

    __tablename__ = 'agent_llm_provider'
    __table_args__ = (
        Index('ix_agent_llm_provider_owner_default',
              'owner_id', 'tenant_id', 'is_default'),
        Index('ix_agent_llm_provider_owner_status', 'owner_id', 'status'),
        Index('uq_agent_llm_provider_default', 'owner_id', 'tenant_id',
              unique=True,
              postgresql_where=text("is_default AND status <> 'DELETED'"),
              sqlite_where=text("is_default = 1 AND status != 'DELETED'")),
    )

    id = Column(_PK, primary_key=True)
    owner_id = Column(BigInteger, nullable=False)
    tenant_id = Column(String(64), nullable=False)
    name = Column(String(100), nullable=False, default='')
    protocol = Column(String(32), nullable=False, comment='LlmProtocol')
    base_url = Column(String(500), nullable=False)
    model = Column(String(100), nullable=False)
    api_key_ciphertext = Column(Text, nullable=False, default='',
                                comment='AES-256-GCM 密文，禁止明文')
    api_key_mask = Column(String(32), nullable=False, default='',
                          server_default='', comment='脱敏回显串')
    key_version = Column(Integer, nullable=False, default=1,
                         server_default='1', comment='主密钥版本')
    context_window = Column(Integer, nullable=True, comment='用户覆盖值')
    context_window_source = Column(String(20), nullable=False,
                                   comment='ContextWindowSource')
    is_default = Column(Boolean, nullable=False, default=False,
                        server_default=text('false'))
    status = Column(String(20), nullable=False, comment='ProviderStatus')
    last_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now(), onupdate=utcnow)


class AgentSkill(Base):
    """自定义 Skill 当前指针（INT-2549 §4.4 / §10）。

    - ``scope``：``PLATFORM`` 只读挂载，**不落本表**；本表只有 ``TENANT`` /
      ``USER`` 行（PLATFORM 由 ``skills/`` 扫描装载）；
    - 正文只存版本表 ``agent_skill_version``，本行 ``version`` 是指针，
      不双写正文（卡面 §4.4「正文只存版本表」）；
    - ``resources`` 只存「相对路径 → 对象存储 key」，资源本体不进库；
    - 唯一性用**局部唯一索引**表达：USER 按 ``(owner_id, name)``、TENANT 按
      ``(tenant_id, name)``，与卡面「scope + tenant_id/owner_id + name 唯一」
      等价，且不因另一作用域为 NULL 而失效。
    """

    __tablename__ = 'agent_skill'
    __table_args__ = (
        Index('ix_agent_skill_scope_status', 'scope', 'status'),
        Index('uq_agent_skill_owner_name', 'owner_id', 'name', unique=True,
              postgresql_where=text(_SCOPE_USER_PREDICATE),
              sqlite_where=text(_SCOPE_USER_PREDICATE)),
        Index('uq_agent_skill_tenant_name', 'tenant_id', 'name', unique=True,
              postgresql_where=text(_SCOPE_TENANT_PREDICATE),
              sqlite_where=text(_SCOPE_TENANT_PREDICATE)),
    )

    id = Column(_PK, primary_key=True)
    scope = Column(String(20), nullable=False, comment='SkillScope')
    tenant_id = Column(String(64), nullable=True, comment='TENANT 行必填')
    owner_id = Column(BigInteger, nullable=True, comment='USER 行必填')
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=False, default='')
    version = Column(String(32), nullable=False, default='0',
                     comment='当前版本指针（指向 agent_skill_version）')
    status = Column(String(20), nullable=False, comment='SkillStatus')
    content_hash = Column(String(64), nullable=False, default='')
    frontmatter_json = Column(JSON, nullable=True, comment='frontmatter 字典')
    resources = Column(JSON, nullable=True, comment='相对路径 → 对象存储 key')
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now(), onupdate=utcnow)


class AgentSkillVersion(Base):
    """自定义 Skill 的不可变版本快照（正文唯一事实源）。

    历史 run 的回放读本表 + ``agent_run_skill``；Skill 后续修改不影响历史版本。
    """

    __tablename__ = 'agent_skill_version'
    __table_args__ = (
        UniqueConstraint('skill_id', 'version',
                         name='uq_agent_skill_version_skill_version'),
        Index('ix_agent_skill_version_skill', 'skill_id', 'created_at'),
    )

    id = Column(_PK, primary_key=True)
    skill_id = Column(_PK, nullable=False)
    version = Column(String(32), nullable=False)
    content_hash = Column(String(64), nullable=False, default='')
    frontmatter_json = Column(JSON, nullable=True)
    body = Column(Text, nullable=False, default='')
    resources = Column(JSON, nullable=True)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now())


class AgentRunSkill(Base):
    """run 内 Skill 激活快照（一次激活 / 切换追加一行）。

    回放以「本表 + agent_skill_version」为准：Skill 后续修改不中途换内容。
    ``(run_id, activated_at)`` 服务按 run 回放；``skill_id`` 索引服务「这个
    skill 被哪些 run 用过」的排查。保留策略配置化，不在本卡做自动清理。
    """

    __tablename__ = 'agent_run_skill'
    __table_args__ = (
        Index('ix_agent_run_skill_run', 'run_id', 'activated_at'),
        Index('ix_agent_run_skill_skill', 'skill_id'),
    )

    id = Column(_PK, primary_key=True)
    run_id = Column(_PK, nullable=False)
    skill_id = Column(String(100), nullable=False,
                      comment='agent_skill.id；平台层为 platform:<name>')
    version = Column(String(32), nullable=False)
    content_hash = Column(String(64), nullable=False, default='')
    activated_at = Column(DateTime, nullable=False, default=utcnow,
                          server_default=func.now())


class AgentSkillReview(Base):
    """TENANT 级 Skill 审核流的不可变审计行（INT-2551 §4.4）。

    - 只追加：提交 / 批准 / 驳回 / 撤回 / 停用各一行，任何入口都不更新、
      不删除本表（审批链是审计事实）；
    - ``version`` 是动作发生时的版本指针 —— 版本粒度可追溯「谁批的哪一版」；
    - ``status_from`` / ``status_to`` 是状态机迁移两端，枚举取值（枚举化，
      DB 里没有魔法字符串）；
    - ``tenant_id`` 冗余存储：待审队列按 ``(tenant_id, status_to)`` 取本租户
      记录，不依赖 agent_skill 行仍在（Skill 被删后审计链仍可查）。
    """

    __tablename__ = 'agent_skill_review'
    __table_args__ = (
        Index('ix_agent_skill_review_skill_version', 'skill_id', 'version'),
        Index('ix_agent_skill_review_tenant_status', 'tenant_id', 'status_to'),
        Index('ix_agent_skill_review_skill_time', 'skill_id', 'created_at'),
    )

    id = Column(_PK, primary_key=True)
    skill_id = Column(_PK, nullable=False)
    version = Column(String(32), nullable=False,
                     comment='动作发生时的 agent_skill.version')
    action = Column(String(20), nullable=False, comment='SkillReviewAction')
    status_from = Column(String(20), nullable=False, comment='SkillStatus')
    status_to = Column(String(20), nullable=False, comment='SkillStatus')
    reviewer_id = Column(BigInteger, nullable=True,
                         comment='动作执行人 user_id（提交人 / 审批人）')
    reason = Column(Text, nullable=False, default='', server_default='')
    tenant_id = Column(String(64), nullable=True, comment='TENANT 行必填')
    created_at = Column(DateTime, nullable=False, default=utcnow,
                        server_default=func.now())
