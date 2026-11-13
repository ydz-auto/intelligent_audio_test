# -*- coding: utf-8 -*-
"""agent_service PO 模型（落地方案 §10，M0 前七张表）。

表：agent_session / agent_run / agent_run_event / agent_step /
    agent_tool_call / agent_artifact / agent_context_snapshot
    + agent_llm_provider（INT-2488 用户自带供应商密钥库）
（agent_approval 属 M2，本卡不建。）

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

from shared.models.database import Base
from shared.utils.time_utils import utcnow

_PK = String(36)


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
    __table_args__ = (
        UniqueConstraint('run_id', 'index', name='uq_agent_step_run_index'),
        Index('ix_agent_step_run', 'run_id', 'index'),
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
    error = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=True,
                             comment='run_id + step_id + tool_call_id + tool + args_hash')
    created_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())
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
    """上下文快照表（§8.5；M0 只落版本与 token 统计，压缩由 m0-04 启用）。"""

    __tablename__ = 'agent_context_snapshot'
    __table_args__ = (
        UniqueConstraint('run_id', 'version', name='uq_agent_context_snapshot_version'),
        Index('ix_agent_context_snapshot_run', 'run_id', 'version'),
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
