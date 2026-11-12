# 单 Agent + Skills 落地方案

> 状态：已拍板，待实施。决策日期 2026-11-12；基线 `V10.11.2`。
> 上位变更：以本文替代 [00_DeepSeek_Harness统一迁移设计.md](00_DeepSeek_Harness统一迁移设计.md) 中的 Agent Runtime 选型。
> 保留不变：[01_功能介绍.md](01_功能介绍.md) 的业务能力与工具目录、[02_用户场景.md](02_用户场景.md) 的场景目标、[05_报告优先实施路线图.md](05_报告优先实施路线图.md) 的验收口径与安全原则。
> 作废范围：DSH Runtime、DSH Worker、DSH Plugin、DSH Session；[03_技术设计文档.md](03_技术设计文档.md) 的自研 Agent Loop 旧章节同样作废，以本文第 5 节为准。

## 1. 结论

1. **唯一 Runtime：一个模型、一个上下文窗口、一个开放式工具循环**。不引入编排器，不按域拆 subagent。
2. **能力扩展方式是 Skill，不是新 Agent**。Skill 承载流程、口径、判断与踩坑；工具承载动作与实时数据。
3. **全平台 61 个业务能力全部纳入**，但内部 Agent 不暴露 205 个 MCP 原子工具，收敛为 26 个意图级工具（含 `tool_search`，业务意图工具 25 个）延迟加载。
4. **一套 Skill，两种宿主**：平台内置 Agent 与外部 Claude Code / Codex 共用同一批 `skills/` 资产；对外 MCP 保持现有 1:1 契约不变。
5. **底座先行**：沙箱、上下文无感压缩、断点续跑、逐工具权限、写操作审批，先于业务 Skill 铺开。

## 2. 业界依据

| 来源 | 结论 | 对本方案的约束 |
|---|---|---|
| Anthropic《When to fold subagents into your main agent loop》(2026-10-22) | 单 agent + skills 常优于多 subagent；仅三种情况保留 subagent；工具定义超过 30–50 个后选择质量下降；流程放 Skill，硬约束与审批放工具 | 单 loop；意图级工具 ≤30；审批在 harness |
| Anthropic Agent Skills (2026-06) | Skill 是文件夹；三级渐进披露；description 是触发条件；Gotchas 信噪比最高；验证类 Skill 收益最大 | `SKILL.md` + `references/` + `scripts/`；每个 Skill 必须有 Gotchas 与验收 |
| Agent Skills 开放标准 `agentskills.io` (2025-12) | 目录 + YAML frontmatter（name / description）为最小契约；Anthropic / OpenAI / Cursor / GitHub / Microsoft / Google 已采用 | 不自造格式；扩展字段用 `allowed-tools` 等 |
| OpenAI Agents SDK / Codex Skills | Agent/Handoff/Guardrail 三原语；Codex 采用同一 `SKILL.md` 格式，`agents/openai.yaml` 存 UI 元数据 | 不引入 handoff；Skill 格式与外部生态兼容 |

**模型能力假设**：上述结论基于较强模型。使用 DeepSeek 等模型时，计划、顺序、校验不能完全交给模型，必须保留确定性护栏（参数 Schema 校验、指标复算、写操作审批）。

## 3. 总体架构

```text
frontend-react（features/ai-chat / agent-workbench）
   │ POST /api/v1/agent/sessions/{id}/runs
   │ GET  /api/v1/agent/runs/{id}/events?cursor=   （SSE + 回放）
   ▼
api_gateway  ── 鉴权 / 租户 / 限流 / 审计 / 代理
   ▼
agent_service  ── 唯一 Agent Loop
   ├─ SkillRegistry        扫描 skills/，只注入 name+description
   ├─ ContextAssembler     预算、裁剪、结构化备忘、状态重建
   ├─ ToolGateway          意图工具 → 现有 REST/gRPC；逐次权限校验；幂等
   ├─ ApprovalService      写操作提案 → 审批 → 执行
   ├─ SandboxRunner        T1 可信脚本 / T2 不可信代码
   └─ RunStore             session / run / step / event / approval / artifact
   ▼
现有业务服务（task / testcase / audio / device / evaluation / report / algorithm / auth）
   ▲
   └─ 对外 MCP 复用 `/api/v1/mcp` + tools_registry（单一事实源，抽到 shared/）
```

### 3.1 职责边界

| 能力 | 归属 |
|---|---|
| 模型调用、流式、工具调度、上下文管理 | `agent_service` 的 Loop |
| 身份、租户、资源授权、审批决策、审计 | `api_gateway` + 各业务服务（强制校验） |
| 业务事实与指标计算 | 现有领域服务；模型不得编造数值 |
| 文档与版本 | Report Studio 文档/版本表 |
| 对话与工具历史 | Agent Session / Run / Event（独立于报告七表） |
| 外部 Agent 接入 | 现有 Skill zip + MCP |

## 4. Skill 规范

### 4.1 目录与加载

```text
skills/<skill-name>/
├─ SKILL.md              # 必需：YAML frontmatter + 正文
├─ references/           # 按需加载的详细资料
├─ scripts/              # 平台受控脚本（T1 沙箱执行）
└─ assets/               # 输出模板、字体、图标（不进上下文）
```

三级渐进披露：

| 层级 | 内容 | 何时进入上下文 |
|---|---|---|
| L1 | `name` + `description` | 每次模型调用常驻 |
| L2 | `SKILL.md` 正文 | Skill 被激活时 |
| L3 | `references/` / `assets/` | 模型按正文指引读取 |
| 执行 | `scripts/` | 沙箱执行，结果只回摘要 |

### 4.2 frontmatter 契约

```yaml
---
name: report-studio
description: >-
  报告取数、指标解释、Markdown 起草与改稿、版本恢复、导出。
  触发词：报告、对比报告、指标、WER、开放题、导出 PPT/PDF。
version: 1.0.0
owner: report-team
allowed-tools:
  - report_query
  - report_generate
  - report_compare
  - report_export
permissions:
  - report:read
budgets:
  maxToolCalls: 40
  maxTokens: 60000
---
```

规则：

1. `description` 写给模型判断触发时机，必须含触发词与不适用边界。
2. 一个 Skill 只做一件事；跨域引用其他 Skill，不写万能 Skill。
3. 必须包含 `## Gotchas` 与 `## 验收` 两节。
4. 正文控制在 500 行内，超出的内容拆 `references/`。
5. 禁止 README、CHANGELOG、安装说明等非 Agent 必需文件。
6. `allowed-tools` 只能引用已注册的意图工具；未声明的工具运行时不装配。
7. `permissions` 与工具注册表 OR 语义一致；用户权限不足时 Skill 不可见。

### 4.3 首批 Skill 清单（全平台）

合计 13 个：M0 交付 `platform-reference`，其余 12 个在 M1 出 L1/L2（§15）。

| Skill | 覆盖域 | 主要意图工具 | 优先级 |
|---|---|---|---|
| `platform-reference` | 平台接口、字段别名、枚举、Gotchas | `tool_search`、`platform_contract` | P0 |
| `audio-import` | 音频导入、标注、目录树、元数据 | `audio_query`、`audio_import`、`audio_annotate` | P1 |
| `testcase-authoring` | 标注 → 用例、轮次、维度、复制 | `testcase_query`、`testcase_generate`、`testcase_write` | P1 |
| `tag-group` | 标签、用例分组、批量打标 | `tag_group_manage` | P2 |
| `evaluation-config` | 评估维度、分类、重评估 | `evaluation_query`、`evaluation_manage` | P1 |
| `algorithm-config` | 算法定义、参数、映射、热重载 | `algorithm_query`、`algorithm_manage` | P2 |
| `task-operations` | 创建、启动、进度、合并、诊断、重试 | `task_query`、`task_run`、`task_diagnose` | P0 |
| `spl-calibration` | 映射、校准、测试音、历史 | `spl_calibrate` | P2 |
| `device-operations` | 设备查询、控制、分组、告警 | `device_query`、`device_control` | P1 |
| `report-studio` | 三类报告取数、起草、改稿、版本、导出 | `report_query`、`report_generate`、`report_export` | P0 |
| `report-compare` | 多报告对比、趋势、异常下钻 | `report_compare`、`report_query` | P1 |
| `log-diagnostics` | 日志搜索、失败诊断、导出 | `log_diagnose` | P1 |
| `driver-proposal` | UiAutoDev 元素 → 驱动代码提案 | `driver_propose`（对外唯一工具名；`generate_driver_from_elements` / `publish_driver_proposal` 是内部步骤，不新增对外工具，落地卡 INT-2467） | P2 |

## 5. 单 Agent Loop 契约

### 5.1 循环

```text
输入：session_id, user_message, user_permissions
1. 组装上下文：系统提示 + Skill L1 列表 + 激活 Skill 正文 + 最近对话 + 工具结果 + scratchpad
2. 调用模型（流式）
3. 若返回文本：推送 token 事件
4. 若返回工具调用批次：并行执行，逐条校验权限/参数/预算，回灌原始结果
5. 重复 2–4，直到模型给出最终答复或触发停止条件
停止条件：正常答复 / 用户取消 / 工具预算 / token 预算 / 时长预算 / 连续失败阈值
```

### 5.2 硬规则

1. 一个模型、一个上下文窗口，不做模型间 handoff。
2. 每轮工具调用并行执行；结果按 `tool_call_id` 原样回灌。
3. 模型在 `run_scratchpad` 中写计划并随时修改，压缩后原样回注。
4. 顺序与领域流程写 Skill；参数校验、权限、审批、幂等写工具与 harness。
5. 只读工具自动执行；写操作一律提案 + 审批 + 幂等执行。
6. 任何模型调用与工具调用都必须计入 run 预算与审计。

### 5.3 枚举与配置（禁止魔法值）

| 枚举 | 取值 |
|---|---|
| `RunStatus` | `QUEUED` / `RUNNING` / `WAITING_APPROVAL` / `SUCCEEDED` / `FAILED` / `CANCELLED` / `BUDGET_EXCEEDED` |
| `ToolRisk` | `READ` / `WRITE` / `DESTRUCTIVE` |
| `SandboxTier` | `T0_NONE` / `T1_TRUSTED_SCRIPT` / `T2_UNTRUSTED_CODE` |
| `CompactionLevel` | `L1_TRIM` / `L2_DEDUPE` / `L3_MEMO` / `L4_REBUILD` |
| `EventType` | `run_started` / `message_delta` / `tool_call` / `tool_result` / `approval_required` / `context_compacted` / `run_finished` / `error` |

所有预算、阈值、超时、并发数写入配置（环境变量 + `config/`），不在代码中硬编码。

## 6. 工具层

### 6.1 意图级工具（内部 Agent）

原则：按用户意图分组，不按 API 1:1。目标 ≤30 个定义；本表合计 26 个（含 `tool_search`，业务意图工具 25 个）。

| 工具 | 覆盖能力 | 风险 |
|---|---|---|
| `platform_contract` | 查询字段、枚举、权限码、接口说明 | READ |
| `tool_search` | 按关键词/语义查找长尾工具并返回 Schema | READ |
| `audio_query` | 音频列表、详情、MD5、标签、目录树、特征/质量 | READ |
| `audio_import` | URL 导入、上传初始化/合并、OSS 直传确认 | WRITE |
| `audio_annotate` | 批量标注、元数据、算法配置 | WRITE |
| `testcase_query` | 用例列表、详情、导入导出状态 | READ |
| `testcase_generate` | 标注 → 用例草案（不落库） | READ |
| `testcase_write` | 创建、修改、复制、删除、打标签 | WRITE |
| `tag_group_manage` | 标签与分组 CRUD、批量打标 | WRITE |
| `evaluation_query` | 维度、分类、评分口径 | READ |
| `evaluation_manage` | 维度/分类 CRUD、触发重评估 | WRITE |
| `algorithm_query` | 定义、参数、映射、表单 Schema | READ |
| `algorithm_manage` | 定义/参数/映射写操作、热重载 | WRITE |
| `task_query` | 任务列表、详情、进度、结果、统计 | READ |
| `task_run` | 创建、启动、停止、重试、合并、重提取 | WRITE |
| `task_diagnose` | 失败用例、日志、归因、重测建议 | READ |
| `spl_calibrate` | 映射、校准、测试音、历史 | WRITE |
| `device_query` | 设备、分组、状态、告警 | READ |
| `device_control` | 连接、重启、扫描、安装、批量 | DESTRUCTIVE |
| `report_query` | 三类报告事实、指标、用例、统计 | READ |
| `report_generate` | 生成/重生成报告、创建 Studio 草稿 | WRITE |
| `report_compare` | 多报告/二次对比、趋势 | READ |
| `report_export` | 导出 PDF/PPTX/HTML/MD | WRITE |
| `log_diagnose` | 日志搜索、统计、诊断 | READ |
| `driver_propose` | 生成驱动代码提案（不执行、不发布）；落地卡 INT-2467。对外意图工具名唯一为 `driver_propose`，`generate_driver_from_elements` / `publish_driver_proposal` 是内部步骤，不新增对外工具；首期只出提案、默认不发布 | WRITE |
| `dashboard_query` | 首页统计（只读；缓存刷新留 M2，与 INT-2461 一致） | READ |

### 6.2 外部 MCP

- 保持 `api_gateway/application/services/mcp/tools_registry.py` 现有 1:1 工具不变。
- 注册表抽到 `shared/agent_tools/`，Gateway MCP 与 `agent_service` 共用，禁止复制两份 Schema。
- 外部 Agent 的上下文管理由客户端负责，不做意图收敛。

### 6.3 权限

1. 工具声明 `permissions`（OR 语义）；Skill 的 `allowed-tools` 与用户权限取交集。
2. 每次调用由 ToolGateway 重新校验：用户、租户、对象归属、实时状态、参数 Schema。
3. 越权返回模型可读的普通拒绝文本，不抛内部异常，不泄漏资源是否存在。
4. 所有工具调用写审计：`run_id`、`tool`、`args_hash`、`decision`、`latency`、`result_code`。

## 7. 沙箱

| 层级 | 场景 | 方案 |
|---|---|---|
| `T0_NONE` | 所有业务工具调用 | 不执行代码；短时令牌（user + tenant + run + scopes），无 DB/设备凭证 |
| `T1_TRUSTED_SCRIPT` | Skill 自带 `scripts/` | 一次性 Docker：非 root、`--network=none`、`--read-only`、`--cap-drop=ALL`、`--security-opt=no-new-privileges`、`--pids-limit=128`、`--memory=512m`、`--cpus=1`、`/tmp` tmpfs 64m；Skill 只读挂载，仅 `/work` 可写；超时 60s；输出限 1MB |
| `T2_UNTRUSTED_CODE` | 模型生成代码、驱动代码 | 默认不执行，只产出提案；确需执行时用 gVisor/Firecracker，禁网、无宿主挂载、无凭证、用完即毁 |

硬规则：

1. 凭证永不进入沙箱；工具调用在沙箱外由 ToolGateway 执行。
2. 静态检查不能替代沙箱。
3. 沙箱产物只通过 `/work` 输出卷回收，校验类型与大小。
4. 生产环境 Linux 容器；Windows 开发机使用 Docker Desktop 的 Linux 容器，不使用 Windows 容器。
5. 沙箱失败不得让 run 静默成功；按 `FAILED` 或 `BUDGET_EXCEEDED` 明确记录。

## 8. 上下文无感压缩

### 8.1 无感定义

- 用户在 UI 看到的历史来自数据库，**永远完整**。
- 压缩只影响模型上下文；可在调试模式显示 `context_compacted` 事件，正常界面不打断。
- 压缩后任务可继续，不要求用户重述。
- 对话摘要不等于事实；事实必须可通过工具重查。

### 8.2 四层策略

| 层 | 做法 | 使用 LLM | 失败降级 |
|---|---|---|---|
| `L1_TRIM` | 工具结果统一为「摘要 + 关键字段 + artifact 引用」，超限截断；大结果落对象存储 | 否 | 直接截断 |
| `L2_DEDUPE` | 相同查询结果去重；列表只留计数 + TopN + 查询入口 | 否 | 跳过 |
| `L3_MEMO` | 旧对话压成固定 schema：目标、约束、已确认事实（带来源 ID）、决策、产物、未决问题、下一步 | 是 | 回退 L1 |
| `L4_REBUILD` | 进程重启或换模型时，从 Run 表 + 产物索引重建上下文 | 否 | 使用最近快照 |

### 8.3 预算模型

| 区段 | 上限 |
|---|---|
| system + Skill L1 + 激活 Skill 正文 | 15% |
| 计划 / scratchpad | 10% |
| 对话历史 | 35% |
| 工具结果 | 30% |
| 安全余量 | 10% |

- 可用窗口 = 模型窗口 − 输出预留。
- 60% 软触发预压缩，80% 硬触发。
- 换模型时按新窗口重新计算，不沿用旧阈值。

### 8.4 永不压缩清单

1. 系统不变量与安全规则。
2. 当前激活 Skill 的正文。
3. 当前计划与用户明确约束。
4. 审批状态与待执行提案。
5. Artifact 索引与来源 ID。
6. 最近 N 轮原文（N 可配置）。

### 8.5 可观测与验收

- 每次压缩写 `agent_context_snapshot`：版本、token 数、被裁消息 ID、备忘内容、触发层级。
- 指标：每轮 token、压缩次数、事实召回率、重查率、压缩前后任务成功率差。
- 长任务评测集：≥50 轮、跨域、含写操作审批与会话恢复。

## 9. 运行可靠性与状态

### 9.1 状态机

```text
QUEUED → RUNNING → WAITING_APPROVAL → RUNNING → SUCCEEDED
                 ↘ FAILED / CANCELLED / BUDGET_EXCEEDED
```

### 9.2 断点续跑

1. 每个 step、tool call、approval、event 持久化，事件带严格递增 `sequence`。
2. 写工具必须带 `Idempotency-Key`（run_id + step_id + tool + args_hash）。
3. Worker 重启后先查业务真实副作用，再决定是否重放，禁止重复执行可能已成功的写操作。
4. 取消：设置取消标记，当前模型调用中止，已完成的写操作不回滚，后续步骤不再执行。

### 9.3 预算与熔断

- 每 run：最大轮次、最大工具调用数、最大 token、最大时长、最大输出字节。
- 超限 → `BUDGET_EXCEEDED`，保留已完成产物与事件。
- 连续工具失败 ≥ 阈值 → 停止自动重试，转 `WAITING_APPROVAL` 或 `FAILED`，交用户决策。

## 10. 数据模型

| 表 | 关键字段 |
|---|---|
| `agent_session` | id, owner_id, tenant_id, title, active_skill, model, created_at, updated_at |
| `agent_run` | id, session_id, owner_id, status, model, budget, token_in, token_out, started_at, finished_at, error |
| `agent_run_event` | id, run_id, sequence, type, payload, created_at |
| `agent_step` | id, run_id, index, plan_snapshot, status, created_at |
| `agent_tool_call` | id, run_id, step_id, tool, args_hash, risk, status, result_ref, latency_ms, permission_decision |
| `agent_approval` | id, run_id, tool_call_id, proposal, diff, status, expires_at, decided_by, decided_at |
| `agent_artifact` | id, run_id, kind, uri, size, metadata |
| `agent_context_snapshot` | id, run_id, version, token_count, dropped_ids, memo, level |

索引：session owner、run owner/status、(`run_id`, `sequence`)、approval status/expiry、idempotency key 唯一索引。

敏感数据：音频、完整日志、Prompt 全文不入事件表；只存授权引用，日志脱敏。

## 11. API 与 SSE

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/agent/sessions` | 创建会话 |
| GET | `/api/v1/agent/sessions/{id}` | 会话与最近消息 |
| POST | `/api/v1/agent/sessions/{id}/runs` | 发起 run，支持 `Idempotency-Key` |
| GET | `/api/v1/agent/runs/{id}` | run 快照 |
| GET | `/api/v1/agent/runs/{id}/events?cursor=` | SSE，支持 `Last-Event-ID` 续传 |
| POST | `/api/v1/agent/runs/{id}/cancel` | 取消 |
| GET | `/api/v1/agent/runs/{id}/approvals` | 待审批提案 |
| POST | `/api/v1/agent/approvals/{id}/decision` | 批准/拒绝 |
| GET | `/api/v1/agent/skills` | 当前用户可见 Skill 列表 |
| GET | `/api/v1/agent/skill` | 外部 Skill zip 下载（保留） |
| POST | `/api/v1/mcp` | 外部 MCP（保留） |

SSE 事件载荷统一包含 `run_id`、`sequence`、`type`、`timestamp`；`message_delta` 带 `message_id`，避免重连重复拼接。

## 12. 代码落位

### 12.1 后端

```text
agent_service/
├─ interfaces/api/routes.py
├─ application/
│  ├─ run_orchestrator.py        # 唯一 Loop
│  ├─ skill_registry.py
│  ├─ context_assembler.py
│  ├─ tool_gateway.py
│  ├─ approval_service.py
│  └─ sandbox_runner.py
├─ domain/model/ + enums.py
└─ infrastructure/
   ├─ llm/openai_compatible.py
   ├─ skill/fs_skill_repository.py
   ├─ tools/registry_bridge.py
   ├─ persistence/
   ├─ sandbox/docker_runner.py
   └─ observability/
skills/                          # 顶层只读挂载
shared/agent_tools/              # 工具 Schema 单一事实源
```

- 端口注册到 `shared/config/service_ports.py`。
- `agent_service` 不直接 import 业务服务内部模块，只走 REST/gRPC 契约。
- 分层遵循 `interfaces → application → domain → infrastructure`，`domain` 零依赖。

### 12.2 前端（frontend-react）

| 位置 | 改造 | 落地卡 |
|---|---|---|
| `infrastructure/api/agentApi.ts` | 由占位桩改为真实契约（sessions / runs / events SSE / approvals 占位） | INT-2457 |
| `infrastructure/dto/` | 新增 Agent DTO 转换，snake_case 只在此层 | INT-2457 |
| `application/agent/use-agent-run.ts` | 发起 run、订阅 SSE、断线续传、取消 | INT-2457 |
| `features/ai-chat` | 接真实事件流；保留工具卡与来源卡 | INT-2457 |
| `features/ai-chat` 审批卡 + Run 时间线 | 审批提案/diff/风险/过期；事件时间线；重连恢复待审批 | INT-2472 |
| `features/ai-chat` Report Studio 文档面板 | 取数 → 起草 → 版本 → 导出（PDF/PPTX/HTML/MD） | INT-2473 |
| Auto 模式 | 目标输入、预算设置、进度汇报、中断/暂停/继续 | INT-2477 |
| `features/agent-workbench` | 保留页面能力映射，快捷指令仍只回填不自动发送 | INT-2457（保留） |

要求：加载/空/错误态齐全；审批按钮防重复；SSE 重连不重复渲染；Web 单通道验证（当前全仓无 Electron 依赖，桌面壳另行立项）。

## 13. 安全

1. 生产禁止 `AUTH_MODE=off`；Agent 总开关默认关闭，故障不影响人工流程。
2. 每工具逐调用校验，模型输出与前端按钮都不是授权。
3. 工具结果标记为不可信数据，其中的指令不执行；写操作必须审批。
4. 日志与事件脱敏：不落 Prompt 全文、不落密钥、不落原始音频。
5. 每个 run 可审计：谁发起、用了哪个 Skill、调了什么工具、谁批准、产生了什么副作用。
6. 外部 Skill zip 与 MCP 继续使用 `at_` Access Token，权限 = 用户权限 ∩ token scopes。

## 14. 评测

| 层级 | 内容 | 门槛 |
|---|---|---|
| 端到端 | 跨域任务集，中央小组维护 | 任务成功率、无编造数值、权限不越界 |
| 单 Skill | 每 Skill ≥10 条 golden tasks | 触发准确率 ≥90%，工具选择正确，成本达标 |
| 压缩 | 50+ 轮长任务 | 压缩前后成功率差 ≤5%，事实召回率 ≥95% |
| 沙箱 | 逃逸/联网/资源超限用例 | 100% 拦截，无宿主访问 |
| 恢复 | kill Worker 后继续 | 不重复写，状态一致 |

评测集入库，Skill 变更必须跑对应集合；失败阻断合并。

## 15. 里程碑与验收

| 阶段 | 交付 | 验收 |
|---|---|---|
| M0 底座 | 单 loop、SkillRegistry、意图工具 3 个、SSE 回放、Run 持久化；沙箱 T1；压缩 L1–L3；`platform-reference` | 沙箱逃逸测试全拦截；60 轮压缩任务不丢事实；kill Worker 可恢复；10 条 golden tasks 通过 |
| M1 只读全平台 | 11 域只读意图工具；12 个 Skill 的 L1/L2（§4.3 余下 12 个）；tool search | 每域 10 条任务；Skill 触发准确率 ≥90%；无编造数值 |
| M2 写操作与报告 | 写工具、审批、幂等；Report Studio 取数→起草→版本→导出；前端审批卡与时间线 | 提案→审批→执行可重放；重复执行无副作用；三类报告指标与 Report Service 逐字段一致 |
| M3 自动化与评测 | Auto 模式、预算/熔断、全量评测、外部 Skill zip/MCP 对齐、文档更新 | 端到端成功率与成本达标；Agent 关闭不影响原系统；外部 Agent 能力清单一致 |

## 16. 风险与开放问题

| 风险 | 应对 |
|---|---|
| 205 个工具注入导致选择退化 | 意图工具 ≤30 + tool search；Skill 限定工具集 |
| 模型能力不足导致计划漂移 | scratchpad + 确定性校验 + 审批 + 预算 |
| 压缩丢关键事实 | 永不压缩清单；事实带来源 ID，可重查 |
| 沙箱逃逸 | 三层隔离 + 逃逸用例纳入 CI |
| 写操作重复执行 | 幂等键 + 恢复前查副作用 |
| Skill 泛滥 | 一个 Skill 一件事；Owner + 版本 + eval；中央小组把关 |
| 外部与内部能力漂移 | 工具 Schema 单一事实源；清单一致性测试 |

开放问题（需负责人后续拍板）：

1. 默认模型与供应商（DeepSeek / OpenAI 兼容 / Claude）。
2. T2 沙箱是否首期启用，或只保留提案不执行。
3. Auto 模式的默认审批粒度与预算上限。
4. 长期记忆是否引入向量检索（首期不做）。

## 17. 参考

- https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop
- https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills
- https://agentskills.io/home
- https://openai.github.io/openai-agents-python/
- https://github.com/openai/skills
- https://code.claude.com/docs/en/agent-sdk/overview
