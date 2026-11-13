# 单 Agent + Skills 落地方案

> 状态：已拍板，待实施。决策日期 2026-11-12；基线 `V10.11.2`。
> 上位变更：以本文替代 [00_DeepSeek_Harness统一迁移设计.md](00_DeepSeek_Harness统一迁移设计.md) 中的 Agent Runtime 选型。
> 保留不变：[01_功能介绍.md](01_功能介绍.md) 的业务能力与工具目录、[02_用户场景.md](02_用户场景.md) 的场景目标、[05_报告优先实施路线图.md](05_报告优先实施路线图.md) 的验收口径与安全原则。
> 作废范围：DSH Runtime、DSH Worker、DSH Plugin、DSH Session；[03_技术设计文档.md](03_技术设计文档.md) 的自研 Agent Loop 旧章节同样作废，以本文第 5 节为准。

## 1. 结论

1. **唯一 Runtime：一个模型、一个上下文窗口、一个开放式工具循环**。不引入编排器，不按域拆 subagent。
2. **能力扩展方式是 Skill，不是新 Agent**。Skill 承载流程、口径、判断与踩坑；工具承载动作与实时数据。
3. **全平台 61 个业务能力全部纳入**，但内部 Agent 不暴露 205 个 MCP 原子工具，收敛为 31 个工具（含 `tool_search`、2 个记忆工具、3 个探索工具，业务意图工具 25 个）延迟加载。
4. **一套 Skill，两种宿主**：平台内置 Agent 与外部 Claude Code / Codex 共用同一批 `skills/` 资产；对外 MCP 保持现有 1:1 契约不变。
5. **底座先行**：沙箱、上下文无感压缩、断点续跑、逐工具权限、写操作审批，先于业务 Skill 铺开。
6. **模型密钥归用户**：用户配置自己的供应商 Key，加密存库、按用户隔离；平台默认不提供 Key，也不做隐式兜底。
7. **记忆不用向量库**：沿用文件式记忆 + `rg/grep` + Skill references；Auto 模式审批粒度与预算见 §9.4；仅 Web 单通道，不保留 Electron。
8. **上下文窗口可配**：按模型目录给默认值，用户可在供应商配置里覆盖；预算与压缩阈值按有效窗口计算。
9. **主场景是 App/API 接入**：用户说“我要测这个 App/API”，Agent 交付驱动/适配器 + 配置 + 冒烟用例 + 验证证据，而不是只给一段代码。
10. **探索-生成是一等能力**：Agent 自己读 UI 树、API 契约、领域 schema，生成驱动/适配器/用例/配置/报告草案，再在 T1/T2/staging 验证；不依赖用户手工点选全部元素。
11. **Skill 可被用户扩展**：平台内置只读，用户可自建/导入/fork/导出个人 Skill（§4.4）；自定义 Skill 与内置走同一套校验、版本快照与触发评测，不允许绕过权限与审批。

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
| 用户模型供应商与 Key | 用户自行配置；加密存库，仅 `agent_service` 调用时内存解密 |
| 身份、租户、资源授权、审批决策、审计 | `api_gateway` + 各业务服务（强制校验） |
| 业务事实与指标计算 | 现有领域服务；模型不得编造数值 |
| 文档与版本 | Report Studio 文档/版本表 |
| 对话与工具历史 | Agent Session / Run / Event（独立于报告七表） |
| 外部 Agent 接入 | 现有 Skill zip + MCP |

### 3.2 业务领域地图

按“数据配置 → 执行观测 → 交付接入”三层划分，共 14 个领域。

#### 数据与配置层（把测试准备好）

| 领域 | 解决什么问题 | 核心对象 | Agent 典型任务 |
|---|---|---|---|
| 音频导入与标注 | 导入测试音频，建立目录、标签、元数据，写入参考文本/说话人/场景等标注 | 音频、目录、标签、标注、算法关联 | “把这批录音导进来，按目录打标，缺参考文本的标出来” |
| 用例生成与编辑 | 把音频+标注+维度+算法参数组装成可执行用例，支持多轮、参考参数、评估配置 | 用例、轮次、音频配置、算法参数、评估维度 | “按这批标注生成对话/命令/噪声三类用例，覆盖主要维度” |
| 标签管理 | 给用例/音频分类、筛选、批量打标 | 标签、分类、用例 | “把这两百条都打上‘远场’和‘噪声’标签” |
| 评估维度配置 | 定义评什么、怎么评：维度、分类、评分规则、API/算法映射、prompt | 维度树、分类、映射、评分规则 | “按现有维度生成一套口语评测配置，检查引用是否完整” |
| 算法配置 | 定义算法、参数、参考参数、表单 Schema、映射，热重载到运行时 | 算法定义、参数、参考参数、映射、版本 | “从标注里提取参数，生成配置草案，dry-run 后热重载” |
| SPL 与播放设备 | 保证声学播放的声压级和通道正确；扫描/测试播放设备，校准 SPL，管理映射和历史 | 播放设备、通道、SPL 映射、测试音、校准历史 | “这套音箱左通道偏小，帮我校准并回读验证” |

#### 执行与观测层（把测试跑起来）

| 领域 | 解决什么问题 | 核心对象 | Agent 典型任务 |
|---|---|---|---|
| 任务执行与控制 | 把用例编排成任务，调度设备/播放/API，执行多轮并收集结果；支持停止、重试、合并、重提取、重评估 | 任务、轮次、用例结果、设备、音频 | “跑这 50 条，失败的重试一次，给我失败归因” |
| 设备管理与运维 | 管理被测设备、分组、健康、告警；连接、重启、扫描、安装/卸载、测试；设备租用与占用 | 设备、分组、告警、实验室、租约 | “找三台空闲鸿蒙设备，装这个包，跑一轮冒烟” |
| API 测试 | 管理被测 API：协议、端点、鉴权、请求模板、响应解析、厂商适配器；执行 HTTP/WS/gRPC/Realtime 会话 | API 定义、端点、适配器、会话、流式报文 | “解析这份 OpenAPI，生成适配器和配置，先 mock 冒烟” |
| 日志诊断 | 搜索日志、按任务/级别/关键词过滤、失败归因、导出/归档 | 日志、任务、用例、设备、错误码 | “这个任务为什么失败？给我根因和重试建议” |

#### 交付与接入层（出结果、接新系统）

| 领域 | 解决什么问题 | 核心对象 | Agent 典型任务 |
|---|---|---|---|
| 结果分析与报告 | 汇总任务结果和评估分数，生成报告，发布/导出，看趋势和用例均值 | 报告、指标、用例结果、基线、模板 | “和上周基线比，写份报告，导出 PPT” |
| 报告对比 | 多报告/已发布报告对比，趋势、异常下钻 | 报告、指标、版本、基线 | “哪些指标退化，原因是什么” |
| 设备驱动/API 适配器接入 | 新 App/新 API 接入：探索 UI 树/API 契约，生成驱动/适配器+配置+冒烟，验证后审批发布 | `AppDriver`、`ApiVendorAdapter`、能力画像、接入包 | “我要测这个 App/API，帮我把驱动和适配器接好” |
| 系统概览 | 首页统计：用例、任务、设备、音频；缓存刷新 | 聚合统计 | “今天整体情况怎么样，哪里异常” |

#### 领域如何串联

```text
音频/标注 → 用例 → 任务 → 设备/播放/API 执行 → 结果/报告 → 日志诊断
                     ↑                              ↓
              评估维度/算法/SPL 配置          反馈到用例/算法/驱动
```

- 前置配置：评估维度、算法、SPL/播放设备，决定“怎么评、怎么放”。
- 执行层：设备、播放、API 三选一或组合，决定“在哪跑”。
- 交付层：报告、对比、导出，决定“怎么交付”。
- 接入层：驱动/适配器，决定“能不能跑”。

Agent 在每个领域只做三档动作：**查询解释 → 生成草案 → 审批后执行**。写操作、设备动作、发布/导出一律审批。

探索-生成型领域：设备驱动/API 适配器接入、用例生成、算法配置、评估维度、SPL 校准、报告草稿、日志诊断、任务编排；其余偏自然语言查询与批量操作。共性约束见 §6.7。

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

合计 14 个：M0 交付 `platform-reference`，其余 12 个在 M1 出 L1/L2，`app-api-onboarding` 在 M2（依赖 `driver_propose` 与 staging 冒烟）。

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
| `driver-proposal` | UiAutoDev 元素 → 设备驱动（`AppDriver`）+ 厂商 API 适配器（`ApiVendorAdapter`）提案 | `driver_propose`（对外唯一工具名；`target_kind` = `DEVICE_DRIVER` / `API_ADAPTER` / `PAIR`；`generate_driver_from_elements` / `publish_driver_proposal` 是内部步骤，不新增对外工具，落地卡 INT-2467） | P2 |
| `app-api-onboarding` | App/API 接入全流程（含 ASR/TTS 测量路径）：受理、发现、计划、生成、验证、迭代、交付 | `ui_tree`、`ui_action`、`api_spec`、`driver_propose`、`device_query`、`testcase_generate`、`task_run`、`tool_search` | P1 |

### 4.4 用户自定义 Skill

现状：只有只读的平台 `skills/` 目录（[fs_skill_repository.py](file:///d:/00_code/V10.11.2/Intelligent-Audio-TEST/agent_service/infrastructure/skill/fs_skill_repository.py)），用户无法自建、修改、导入导出。补齐三层来源。

#### 来源与优先级

| 层 | 存储 | 可写 | 优先级 | 说明 |
|---|---|---|---|---|
| `PLATFORM` | `skills/<name>/`，容器只读挂载 | 否 | 0 | 平台内置，不允许被覆盖 |
| `TENANT` | `agent_skill` 表 + 对象存储 | 租户管理员 | 1 | 同租户共享 |
| `USER` | 同上，`owner_id` 非空 | 本人 | 2 | 个人私有 |

命名冲突规则：

1. 自定义 Skill 不得与 `PLATFORM` 同名，冲突返回 `SKILL_NAME_CONFLICT`，引导改名或 fork。
2. `TENANT` 与 `USER` 同名时 `USER` 优先，并在列表中标注被遮蔽的项。
3. 同一作用域内同名直接拒绝，不做静默覆盖。

#### 数据模型

`agent_skill`

| 字段 | 说明 |
|---|---|
| `id` | uuid |
| `scope` | `PLATFORM` / `TENANT` / `USER` |
| `tenant_id` / `owner_id` | 作用域键，由服务端按登录身份填，模型不可传入 |
| `name` / `description` | frontmatter 关键字段冗余，便于列表与检索 |
| `version` | 每次保存递增 |
| `status` | `DRAFT` / `ACTIVE` / `DISABLED` |
| `content_hash` | 正文 + 资源 sha256，run 记录引用 |
| `frontmatter_json` / `body` | 原始 frontmatter 与 SKILL.md 正文 |
| `resources` | `references/` / `scripts/` / `assets/` 的对象存储 key |
| `created_by` / `updated_at` | 审计 |

`agent_skill_version` 保存历史版本；`agent_run` 记录 `(skill_id, version, content_hash)`，历史 run 按当时版本回放，不随 Skill 修改而漂移。

仓储：新增 `CompositeSkillRepository`，平台层保持只读扫描，自定义层读写数据库；`SkillRegistry` 的校验逻辑复用，不另写一套。

#### 入口

1. **对话沉淀**：onboarding、报告、诊断等任务完成后，Agent 提议“把这套流程沉淀为 Skill”，生成草案供确认。
2. **上传导入**：zip 包，兼容 agentskills.io 目录格式，与外部 Claude Code / Codex 使用的 `skill zip` 同一格式。
3. **从内置 fork**：复制平台 Skill 作为模板，在副本上改。
4. **在线编辑**：直接编辑 `SKILL.md`，保存后即时校验。

#### 落库前校验

| 项 | 规则 |
|---|---|
| 名称 | `^[a-z0-9][a-z0-9-]{1,63}$` |
| 必填 | `name`、`description`（含触发词与不适用边界） |
| 正文 | 必须含 `## Gotchas`、`## 验收`；≤ 500 行 |
| 工具 | `allowed-tools` ⊆ 已注册意图工具（31 个）+ `tool_search` 可发现的长尾工具 |
| 权限 | `permissions` ⊆ 当前用户权限，不得提权 |
| 体积 | `SKILL.md` ≤ 64 KB；单资源 ≤ 512 KB；整包 ≤ 5 MB |
| 路径 | 禁止绝对路径、`..`、软链、外链资源 |
| 内容 | 禁止凭证、内网地址、可执行二进制；`scripts/` 只登记不自动执行 |

校验失败返回逐项原因，不落库、不进入触发候选。

#### 安全与生命周期

- 自定义 Skill 正文视为**不可信内容**：其中的指令不得覆盖系统不变量；注入检测命中时拒绝发布。
- `USER` 级：本人 `DRAFT → ACTIVE` 需显式确认；`TENANT` 级发布需租户管理员审批。
- 停用/删除立即生效；已运行的 run 按版本快照继续，不中途换内容。
- 发布门槛：至少 3 条 golden tasks 且触发判定通过；未达标只能留在 `DRAFT`，不参与自动触发。

#### 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/agent/skills?scope=` | 列表（含来源、状态、版本、校验结果） |
| POST | `/api/v1/agent/skills` | 新建草稿 |
| PUT | `/api/v1/agent/skills/{id}` | 保存，version +1 |
| POST | `/api/v1/agent/skills/{id}/publish` | 发布（校验 + 评测门槛 + 审批） |
| POST | `/api/v1/agent/skills/{id}/disable` | 停用 |
| POST | `/api/v1/agent/skills/{id}/fork` | 从内置或他人可见 Skill 复制 |
| POST | `/api/v1/agent/skills/import` | zip 导入 |
| GET | `/api/v1/agent/skills/{id}/export` | zip 导出（与外部 Skill 格式一致） |
| GET | `/api/v1/agent/skills/{id}/versions` | 版本历史与回放 |

前端新增 Skill 管理页：列表、来源标签、状态、编辑器、逐项校验反馈、评测门槛、导入导出。

里程碑：M2 末交付 `USER` 级 + 导入导出 + 校验 + 版本；`TENANT` 级共享与审核流放 M3。

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
| `ContextWindowSource` | `MODEL_DEFAULT` / `USER_OVERRIDE` / `FALLBACK` |
| `UiActionType` | `TAP` / `LONG_PRESS` / `SWIPE` / `INPUT_TEXT` / `BACK` / `HOME` / `WAIT` |
| `ArtifactKind` | `DEVICE_DRIVER` / `API_ADAPTER` / `TESTCASE_SET` / `REPORT_DRAFT` / `ALGORITHM_CONFIG` / `EVALUATION_CONFIG` / `SPL_PLAN` / `DIAGNOSIS_PLAN` |
| `ExplorationStopReason` | `DONE` / `BUDGET` / `LOGIN_REQUIRED` / `CAPTCHA` / `DESTRUCTIVE_BLOCKED` / `USER_CANCEL` |
| `EventType` | `run_started` / `message_delta` / `tool_call` / `tool_result` / `approval_required` / `context_compacted` / `run_finished` / `error` |

所有预算、阈值、超时、并发数写入配置（环境变量 + `config/`），不在代码中硬编码。

## 6. 工具层

### 6.1 意图级工具（内部 Agent）

原则：按用户意图分组，不按 API 1:1。本表合计 31 个（含 `tool_search`、2 个记忆工具、3 个探索工具；业务意图工具 25 个），仍在 30–50 安全区间下限。

| 工具 | 覆盖能力 | 风险 |
|---|---|---|
| `platform_contract` | 查询字段、枚举、权限码、接口说明 | READ |
| `tool_search` | 按关键词/语义查找长尾工具并返回 Schema | READ |
| `ui_tree` | 读取设备 UI 树：裁剪节点、截图引用、与上次快照 diff；需设备租用 | READ |
| `ui_action` | 设备 UI 动作：点击/长按/滑动/输入/返回/Home/等待；需设备租用与审批 | WRITE |
| `api_spec` | 解析 OpenAPI/proto/WS 契约：端点、鉴权、请求响应样例 | READ |
| `memory_search` | `rg` 封装：按关键词检索用户/项目记忆与 Skill references | READ |
| `memory_write` | 写入用户偏好或项目规则；需审批 | WRITE |
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
| `driver_propose` | 生成设备驱动（`AppDriver`）+ 厂商 API 适配器（`ApiVendorAdapter`）代码提案（不执行、不注册、不发布）；`target_kind` = `DEVICE_DRIVER` / `API_ADAPTER` / `PAIR`；落地卡 INT-2467。对外意图工具名唯一为 `driver_propose`，`generate_driver_from_elements` / `publish_driver_proposal` 是内部步骤，不新增对外工具 | WRITE |
| `dashboard_query` | 首页统计（只读；缓存刷新留 M2，与 INT-2461 一致） | READ |

> **实现演进裁定（INT-2453，2026-11-13）**：31 个工具已在 `shared/agent_tools/intent_tools.py`
> 全量登记，名称与风险等级与本表逐项一致。M0 只启用 `platform_contract` / `tool_search` /
> `task_query` / `report_query` 4 个；其余 27 个 `enabled=false`（预留 Schema），调用返回
> `TOOL_NOT_ENABLED`（不按写审批语义处理），启动不产生 `UNKNOWN_TOOL` 告警，`tool_search`
> 仍检索得到并标注 `enabled=false`。工具结果错误码固定为 `OK` / `PERMISSION_DENIED` /
> `INVALID_ARGUMENTS` / `TOOL_NOT_ENABLED` / `UNKNOWN_TOOL` / `NOT_FOUND` /
> `APPROVAL_REQUIRED` / `UPSTREAM_ERROR` / `UPSTREAM_UNAVAILABLE`。`tool_search` 的 M0 实现是
> 关键词检索 + 中英词表召回扩展，语义检索尚未实现。

### 6.2 外部 MCP

- 保持 `POST /api/v1/mcp` 现有 1:1 工具不变（205 个，迁移前后 `tools/list` 逐项一致）；
  `api_gateway/application/services/mcp/tools_registry.py` 已改为 re-export，不再保存第二份 Schema。
- 注册表抽到 `shared/agent_tools/`，Gateway MCP 与 `agent_service` 共用，禁止复制两份 Schema。
- 外部 Agent 的上下文管理由客户端负责，不做意图收敛。

### 6.3 权限

1. 工具声明 `permissions`（OR 语义）；Skill 的 `allowed-tools` 与用户权限取交集。
2. 每次调用由 ToolGateway 重新校验：用户、租户、对象归属、实时状态、参数 Schema。
3. 越权返回模型可读的普通拒绝文本，不抛内部异常，不泄漏资源是否存在。
4. 所有工具调用写审计：`run_id`、`tool`、`args_hash`、`decision`、`latency`、`result_code`。

### 6.4 模型供应商与密钥（P0-1 已定）

1. 用户在平台内配置自己的模型供应商（名称、协议、Base URL、模型名、API Key），保存到 `agent_llm_provider`；平台默认不提供任何 Key，`AGENT_ALLOW_PLATFORM_KEY=false`。
2. API Key 使用 AES-256-GCM 加密落库：主密钥来自 KMS / 环境变量 `AGENT_CREDENTIAL_MASTER_KEY`，每条记录独立 nonce，AAD 绑定 `owner_id + provider_id`；禁止明文、禁止可逆日志、禁止向前端返回明文，列表只返回 `sk-****abcd` 掩码。
3. 每次模型调用按 run 的 `owner_id` 取默认供应商，仅在内存中解密；用后即弃，不进入上下文、事件、沙箱、审计日志。
4. 无可用 Key 时 run 以 `LLM_PROVIDER_NOT_CONFIGURED` 失败，前端引导配置；不回退到平台 Key。
5. 协议支持：OpenAI 兼容（DeepSeek / Qwen / 自建网关）与 Anthropic；协议适配放 `infrastructure/llm/`，与 Key 存储解耦。
6. 密钥管理 API 需 `agent:provider:manage` 权限；审计只记 `provider_id` 与操作类型，不记 Key。
7. 主密钥支持版本号轮换，旧版本仍可解密；删除供应商为逻辑删除并清空密文。
8. 前端 `llmProviderApi` 的 localStorage 方案降级为“直连 Demo”，平台 Agent 一律走服务端供应商配置。
9. 上下文窗口：`config/model_catalog.json` 按协议 + 模型名给默认 `context_window` 与 `max_output_tokens`；用户可在供应商配置里覆盖（8k–2M，1024 对齐）。有效值优先级：用户覆盖 → 目录默认 → 128k 兜底，并记录 `context_window_source`。覆盖值高于目录最大值时允许保存但 UI 告警，预算按覆盖值计算。

### 6.5 驱动提案（driver-propose）

这里的“驱动”是两条并行的 Port，不是泛指的硬件驱动：

| 类型 | 契约 | 注册键 | 作用 |
|---|---|---|---|
| 设备驱动 | `AppDriver`（[app_driver.py](file:///d:/00_code/V10.11.2/Intelligent-Audio-TEST/device_service/infrastructure/drivers/contracts/app_driver.py)） | `(app_type, version, platform)` | 在真机上操作 App：`initialize` / `pre_process` / `get_results` / `teardown`，采集结果 |
| API 适配器 | `ApiVendorAdapter`（[api_vendor_adapter.py](file:///d:/00_code/V10.11.2/Intelligent-Audio-TEST/api_test_service/domain/ports/api_vendor_adapter.py)） | `(AdapterProtocol, AdapterVendor)` | 适配厂商协议：`render_request_parts` / `execute` / 流式钩子，覆盖 HTTP/WS/gRPC/Realtime |

#### 6.5.1 ASR/TTS 测量路径

接入前必须先定“怎么喂、怎么收、怎么算”，否则生成的驱动不可测。现有驱动已形成五类可复用模板：

| 模板 | 参考驱动 | 输入 | 采集 | 适用 |
|---|---|---|---|---|
| UI 文本 | `DouBaoAndroidAsrDriver`、`HarmonyXiaoyiInputMethodDriver` | 声学播放 / 手动说话 | 消息列表或编辑器文本 | ASR 文本、对话回复 |
| 录屏音频 | `HarmonyDriver` + `HarmonyCollectionMixin` | 声学播放 | 每轮 mp4 → wav → OSS，首帧时间 | TTS 播放、对话回复音频 |
| PCM 抓取 | `HarmonyDoubaoChat` / `XiaoyiLiveChat` | 声学播放 | `cap_client_out.pcm`（用户）/ `client_in..pcm`（AI），RMS 判结束 | 低延迟、打断、TTS 音频 |
| App 导出 | `PlaudDriver` | 声学播放 | App 内转写/导出/分享 | 长录音转写、离线结果 |
| API 响应 | `OpenAIRealtimeAdapter` / `WebSocketAdapter` | 文件上传 / 流式音频 / 文本 | JSON 文本 + 音频流/文件 | API ASR/TTS |

生成驱动/适配器时必须声明能力画像 `capabilities.json`：

- `stimulus_modes`：`ACOUSTIC_PLAYBACK` / `VIRTUAL_MIC` / `FILE_UPLOAD` / `TEXT_INPUT`
- `capture_modes`：`UI_TEXT` / `SCREEN_RECORD` / `PCM_CAPTURE` / `APP_EXPORT` / `API_RESPONSE`
- `timing_points`：`PLAYBACK_START` / `PLAYBACK_END` / `FIRST_FRAME` / `FIRST_PARTIAL` / `FINAL_TEXT` / `FIRST_AUDIO_PACKET` / `REPLY_END`
- `result_fields`：必须对齐现有结果契约
- `supported_metrics`：`WER` / `CER` / `SENTENCE_ACC` / `FIRST_TOKEN_LATENCY` / `REPLY_LATENCY` / `TTS_QUALITY` / `BARGE_IN`
- `limitations`：如“无 PCM，仅能录屏”“只能取文本，无法评 TTS 音质”

结果字段沿用现有驱动契约，不另造 schema：

`success`、`message`、`asr`、`text`、`question`、`answer`、`wav_path`、`user_wav`、`ai_wav`、`record_path`、`start_ms`、`end_ms`、`first_frame_ms`、`latency_ms`。

指标由 algorithm_service / evaluation_service 计算，驱动只负责采集文本、音频与时序，不在驱动里算 WER/MOS。

`driver_propose` 的 `target_kind` 支持 `DEVICE_DRIVER` / `API_ADAPTER` / `PAIR`；新 App/新厂商接入通常一次生成一对。

流程：

1. 输入：`target_kind`、app_type/vendor、platform/protocol、UiAutoDev 元素/页面树、API 契约（OpenAPI / WS 帧 / gRPC proto）、样例请求响应、音频格式。
2. `device_query` 取设备型号、现有驱动版本；`tool_search` 找同类驱动/适配器样例。
3. 激活 `driver-proposal`，按需读 `references/device-driver-contract.md`、`references/api-adapter-contract.md`、`references/examples.md`、`references/gotchas.md`。
4. 生成提案：
   - 设备驱动：`AppDriver` 子类（元数据 + 生命周期桩 + 结果解析），按平台复用 `BaseDeviceDriver` / `AndroidDriver` / `HarmonyDriver`。
   - API 适配器：`ApiVendorAdapter` 子类（`protocol` / `vendor` 声明 + `render_request_parts` + `execute` + 流式钩子），按协议复用 `WebSocketAdapter` / `GrpcAdapter` / `RealtimeAdapterBase`。
   - 注册与配置：`@register_driver` / `@register_vendor_adapter`、`AdapterProtocol`/`AdapterVendor` 枚举、`vendor_adapter` 配置示例；只生成提案，不写入生产注册表。
5. T2 沙箱：导入/编译、单测、mock 厂商契约测试、注册表 resolve 测试；禁网、无凭证。
6. 审批：保存草稿/分支/PR；合并与注册到生产需要单独的 `DESTRUCTIVE` 审批。
7. 记录模型、输入元素、代码 hash、测试结果、审批人。

边界：

- 不自动注册、不自动发布、不重启设备、不覆盖线上驱动/适配器。
- 生成代码不得含凭证、不得联网；API Key 只通过现有 key resolver 注入。
- 设备驱动与 API 适配器职责不能混：驱动不写厂商报文，适配器不操作 UI。
- 与 `device_control` 分开：一个是写代码提案，一个是设备动作。

验收：

- 同一输入重复生成，提案可复现（同 hash 或可解释 diff）。
- 设备驱动提案通过 `(app_type, version, platform)` resolve；API 适配器提案通过 `(protocol, vendor)` resolve 与 mock 契约测试。
- 静态检查/单测失败时，不产生可发布产物。
- 未审批不能写入驱动/适配器注册表。

### 6.6 App/API 接入（onboarding）

这是最主要的落地场景：用户说“我要测这个 App/API”，Agent 交付一套可运行的接入包，而不是一段代码。**Agent 自己探索 UI 树/API 契约；UiAutoDev 只作为可选的可视化辅助。**

#### 入口

| 入口 | 用户提供 | Agent 产出 |
|---|---|---|
| App（设备驱动） | 设备 + App 包名/版本；Agent 用 `ui_tree` / `ui_action` 自主探索，也可由 UiAutoDev 推送元素卡片 | `AppDriver` + 配置 + 冒烟用例 + 验证报告 |
| API（厂商适配器） | OpenAPI / gRPC proto / WS 帧文档、样例请求响应、鉴权方式；Agent 用 `api_spec` 解析 | `ApiVendorAdapter` + `vendor_adapter` 配置 + mock 契约测试 + 冒烟用例 |
| App + API | 两者都给 | 成对交付：驱动负责设备侧 UI，适配器负责服务端协议 |

UiAutoDev 元素卡片通过受认证的桥接事件进入会话，不作为新的对外工具；`driver_propose` 消费这些结构化输入。元素选择仍可用 UiAutoDev，但不是唯一入口。

#### 流程

1. **受理**：确认 app_type/vendor、platform、protocol、版本；明确测试目标（ASR/TTS/对话/翻译/降噪/打断）；按 §6.5.1 确认输入方式、采集方式、完成判定、时序点、指标与测试资产；确认是否已有同类驱动。
2. **发现**：App 侧用 `ui_tree` 逐页读取裁剪后的 UI 树，用 `ui_action` 导航并记录 `ui_trace.json`；API 侧用 `api_spec` 解析端点/鉴权/样例；`tool_search` 找同类实现与既有约定；校验测量路径可测——只能取 UI 文本就不能评 TTS 音质，只能录屏则 ASR 文本需要额外识别步骤。
3. **计划**：输出接入计划与缺口清单（缺元素、缺鉴权、缺样例、缺设备），用户确认后再生成。
4. **生成**：调用 `driver_propose`，`target_kind` = `DEVICE_DRIVER` / `API_ADAPTER` / `PAIR`；产出代码、配置、测试、manifest。
5. **验证**：T2 编译/单测/mock 契约/注册表 resolve；App 侧在租用设备上跑冒烟用例。
6. **迭代**：失败必须带新证据（日志/截图/元素变化/报文差异），最多 3 轮；不收敛就交回诊断，不无限重试。
7. **交付**：提案包 + 验证报告 + 已知限制 + 回滚方案；合并/注册生产需单独的 `DESTRUCTIVE` 审批。

#### UI 探索会话

- `ui_tree` 返回裁剪树（最多 200 节点）：`id`、`text`、`resource_id`/`key`、`class`、`bounds`、`clickable`、`enabled`，附截图引用与上次快照 diff；不返回整页 XML/base64。
- `ui_action` 支持 `TAP` / `LONG_PRESS` / `SWIPE` / `INPUT_TEXT` / `BACK` / `HOME` / `WAIT`；每次动作返回新的树 diff，并写入 `ui_trace.json`。
- 预算：单次探索最多 30 个动作 / 5 分钟；超限以 `BUDGET` 停止并交回。
- 安全：必须先租用/锁定设备；首个动作需审批，后续在同一探索计划内自动放行；卸载、重启、支付、删账号等 `DESTRUCTIVE` 动作一律拒绝。
- 遇到登录、验证码、实名/支付页，立即以 `LOGIN_REQUIRED` / `CAPTCHA` 停止，交给用户接管，不尝试绕过。
- 探索轨迹是 `driver_propose` 的输入之一：动作序列 + 页面树 + 截图，用来生成稳定的元素定位和生命周期步骤。

#### 交付包

```text
onboarding/<app_type|vendor>/
├─ driver.py / adapter.py
├─ config.yaml
├─ capabilities.json
├─ test_plan.md
├─ ui_trace.json
├─ tests/
├─ smoke_case.json
├─ manifest.json
└─ onboarding_report.md
```

#### 边界

- 不直接写生产目录、不自动注册、不下发设备。
- 设备侧必须租用/锁定设备，操作前有用户授权；API 侧默认 mock，真实调用需审批。
- 生成代码不含凭证；Key 走现有 resolver。
- 不替代 UiAutoDev：元素选择仍在 UiAutoDev 完成。

#### 验收

- 驱动按 `(app_type, version, platform)` resolve；适配器按 `(protocol, vendor)` resolve。
- 冒烟用例在租用设备/mock 上通过，至少产出一个可计算指标（ASR 文本或 TTS 音频 + 时序）。
- 驱动返回字段对齐现有契约；指标由平台计算，不在驱动里算 WER/MOS。
- 交付包可复现；报告含证据、限制、回滚。
- 未审批不写生产注册表。

### 6.7 探索-生成类任务（跨领域）

共性：用户给一个不熟悉的系统，Agent 先探索、建模，再生成可验证产物。不是每个领域写一套新 Agent，而是复用同一套“探索 → 建模 → 生成 → 验证 → 迭代 → 审批”。

| 领域 | 探索对象 | 生成产物 | 验证方式 |
|---|---|---|---|
| App 驱动 | UI 树、页面流、控件状态 | `AppDriver` + `capabilities.json` | T2 + 真机冒烟 |
| API 适配器 | OpenAPI/proto/WS、鉴权、样例 | `ApiVendorAdapter` + `vendor_adapter` 配置 | mock 契约 + 网关冒烟 |
| 用例生成 | 标注、音频、维度、标签 | 用例草案 + 覆盖矩阵 | schema + 覆盖 + 试跑 |
| 算法配置 | 定义、参数、映射 | 配置草案 | schema + dry-run + 热重载 |
| 评估维度 | 维度树、分类、映射 | 维度配置草案 | schema + 引用检查 |
| SPL 校准 | 设备、通道、测试音、历史 | 校准计划 | 试播 + 回读 |
| 报告草稿 | 指标、模板、基线 | 报告草案 | Report Service 逐字段复算 |
| 日志诊断 | 日志、错误、任务、设备状态 | 诊断 + 重试计划 | 证据链 + dry-run |
| 任务编排 | 用例、设备、音频、时间窗 | 任务计划 | 容量/冲突检查 |

统一约束：

1. 探索只读优先；生成物与写动作必须提案 + 审批。
2. 每个生成物带 `artifact_kind`、`source_trace`、`validation_report`。
3. 写工具标配 `dry_run` / `validate=true`，先校验再落库。
4. 迭代必须带新证据；最多 3 轮；不收敛交回诊断。
5. 领域规则写 Skill/references，校验写工具；不在 Agent 里硬编码业务规则。

现有 CRUD 工具的缺口与补法：

- 缺 UI 树/动作 → `ui_tree` / `ui_action`
- 缺 API 契约解析 → `api_spec`
- 缺 schema 自省 → `platform_contract` 扩展字段/枚举/别名
- 缺产物校验 → 写工具统一支持 `dry_run` / `validate`
- 缺 staging 冒烟 → `task_run(mode=SMOKE)`，需设备租用与审批

## 7. 沙箱

| 层级 | 场景 | 方案 |
|---|---|---|
| `T0_NONE` | 所有业务工具调用 | 不执行代码；短时令牌（user + tenant + run + scopes），无 DB/设备凭证 |
| `T1_TRUSTED_SCRIPT` | Skill 自带 `scripts/` | 一次性 Docker：非 root、`--network=none`、`--read-only`、`--cap-drop=ALL`、`--security-opt=no-new-privileges`、`--pids-limit=128`、`--memory=512m`、`--cpus=1`、`/tmp` tmpfs 64m；Skill 只读挂载，仅 `/work` 可写；超时 60s；输出限 1MB |
| `T2_UNTRUSTED_CODE` | 模型生成代码、驱动代码、任意分析脚本 | **首期启用**。gVisor（`runsc`）或 Firecracker microVM：禁网、无宿主挂载、无凭证、非 root、只读根 + `/work` 输出卷、pids/CPU/内存/时长硬限、用完即毁；Windows 开发机用 Linux 容器并标注“非生产等价” |

硬规则：

1. 凭证永不进入沙箱；工具调用在沙箱外由 ToolGateway 执行。
2. 静态检查不能替代沙箱。
3. 沙箱产物只通过 `/work` 输出卷回收，校验类型与大小。
4. 生产环境 Linux 容器；Windows 开发机使用 Docker Desktop 的 Linux 容器，不使用 Windows 容器。
5. 沙箱失败不得让 run 静默成功；按 `FAILED` 或 `BUDGET_EXCEEDED` 明确记录。
6. T2 默认禁网；确需联网只能走出口代理白名单，并记录代码来源与 hash。

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

W = 有效上下文窗口 = 用户覆盖值 → 模型目录默认值 → 128k 兜底；输出预留在 W 内，单轮输出不超过 `min(8k, 10% × W)`。

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

### 8.6 长期记忆（不用向量 RAG）

1. 不引入向量库、embedding 或语义检索；沿用 DSH 的文件式记忆：`memory/user_profile.md`、`memory/projects/<project>/project_memory.md`、`memory/projects/<project>/<date>/topics.md` 与会话 JSONL。
2. 知识获取靠 `rg`/`grep` + 文件读取 + Skill `references/`；代码与文档不做索引同步。
3. 记忆分三层：用户偏好（跨项目）、项目规则（含本方案）、会话备忘（`run_scratchpad` + `context_snapshot`）。
4. 写入只允许：用户显式“记住”、审批通过的 `memory_write`、run 结束的结构化备忘；禁止模型把猜测写入长期记忆。
5. 会话开始时只注入用户偏好与项目规则摘要；细节由 `memory_search` 按关键词取。
6. 记忆按 tenant/owner 目录隔离，路径不接收模型输入，写入前做敏感信息扫描。

#### 8.6.1 隔离模型（默认严格按用户）

1. 目录：`memory/tenants/<tenant_id>/users/<owner_id>/...`；路径由服务端从登录身份构造，模型不能传入 `tenant_id`、`owner_id` 或任意路径。
2. 读取：`memory_search` 自动附加 tenant + owner 过滤；跨用户、跨租户一律返回空，不泄漏“是否存在”。
3. 写入：`memory_write` 只能写调用者自己的目录，且必须审批；拒绝 `..`、绝对路径、软链与符号链接穿越。
4. 平台规则与 `skills/references/` 是只读共享知识，不属于任何用户记忆，不能经 `memory_write` 修改。
5. 共享记忆默认关闭；确需团队共享时，只能由租户管理员显式开启独立的 tenant 级区域，并单独授权与审计。
6. 管理端默认只能看元数据（条数、更新时间），不能读内容；break-glass 读取必须留审计记录。
7. 会话与 Run 同样按 owner 隔离：`agent_session`、`agent_run`、`agent_run_event` 的查询强制带 `owner_id`。
8. 验收用例：A 读不到 B；跨租户读不到；路径穿越失败；提示注入无法改变身份；导出/删除只作用于本人。

## 9. 运行可靠性与状态

### 9.1 状态机

```text
QUEUED → RUNNING → WAITING_APPROVAL → RUNNING → SUCCEEDED
                 ↘ FAILED / CANCELLED / BUDGET_EXCEEDED
```

### 9.2 断点续跑

1. 每个 step、tool call、approval、event 持久化，事件带严格递增 `sequence`。
2. 写工具必须带 `Idempotency-Key`（run_id + step_id + tool + args_hash）。
   **实现演进裁定（INT-2487）**：落地实现为 `run:step:tool_call_id:tool:args_hash`，
   在方案口径上并入 `tool_call_id`。原因：同一批并行、参数相同的两次调用按
   原口径会撞键，后一次的结果被错误复用（实测只执行一次）；`tool_call_id`
   由模型给出、重启后按同一轮次原样重建，并入后既不丢幂等也不会误合并。
   模型列注释与实现同步。
3. Worker 重启后先查业务真实副作用，再决定是否重放，禁止重复执行可能已成功的写操作。
4. 取消：设置取消标记，当前模型调用中止，已完成的写操作不回滚，后续步骤不再执行。

### 9.3 预算与熔断

- 每 run：最大轮次、最大工具调用数、最大 token、最大时长、最大输出字节。
- 超限 → `BUDGET_EXCEEDED`，保留已完成产物与事件。
- 连续工具失败 ≥ 阈值 → 停止自动重试，转 `WAITING_APPROVAL` 或 `FAILED`，交用户决策。

### 9.4 Auto 模式：审批粒度与预算（已定）

审批粒度：

- `READ`：自动执行。
- `WRITE`：默认“计划级批量审批”，一次展示该步骤全部写操作 + diff/预览；以下必须单条审批：`DESTRUCTIVE`、单次影响 > 20 个对象、跨租户、导出含敏感数据、删除类。
- `DESTRUCTIVE`：永远单条审批，不允许批量或 Auto 预授权。
- Auto 只预授权 `WRITE`，启动前必须展示计划与预算；预算到 80% 或连续 2 次工具失败时暂停。

预算（单 run，W = 有效上下文窗口：用户覆盖 → 模型目录默认 → 128k 兜底）：

| 项 | 默认 | Auto |
|---|---|---|
| 最大轮次 | 40 | 60 |
| 最大工具调用 | 80 | 120 |
| 总 token（输入+输出） | 2 × W | 4 × W |
| 单轮输出 | 8k | 8k |
| 时长 | 15 min | 30 min |
| 输出字节 | 10 MB | 20 MB |
| 压缩触发 | 60% / 80% | 60% / 80% |

预算只能由服务端配置收紧，请求不可放宽；超限统一 `BUDGET_EXCEEDED`。

## 10. 数据模型

| 表 | 关键字段 |
|---|---|
| `agent_session` | id, owner_id, tenant_id, title, active_skill, model, created_at, updated_at |
| `agent_llm_provider` | id, owner_id, tenant_id, name, protocol, base_url, model, api_key_ciphertext, key_version, context_window, context_window_source, is_default, status, last_verified_at, created_at, updated_at |
| `agent_run` | id, session_id, owner_id, status, model, budget, token_in, token_out, started_at, finished_at, error |
| `agent_run_event` | id, run_id, sequence, type, payload, created_at |
| `agent_step` | id, run_id, index, plan_snapshot, status, created_at |
| `agent_tool_call` | id, run_id, step_id, tool, args_hash, risk, status, result_ref, latency_ms, permission_decision, result_code |
| `agent_approval` | id, run_id, tool_call_id, proposal, diff, status, expires_at, decided_by, decided_at |
| `agent_artifact` | id, run_id, kind, uri, size, metadata |
| `agent_context_snapshot` | id, run_id, version, token_count, dropped_ids, memo, level |

索引：session owner、run owner/status、(`run_id`, `sequence`)、approval status/expiry、idempotency key 唯一索引。

长期记忆不建表：使用 `memory/` 文件树（按 tenant/owner 隔离），检索走 `rg`；`agent_context_snapshot` 只存会话内压缩快照。

敏感数据：音频、完整日志、Prompt 全文、模型 API Key 明文均不入事件表与日志；Key 只存密文与掩码，日志脱敏。

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
| GET | `/api/v1/agent/providers` | 我的模型供应商（Key 掩码；含有效窗口与来源） |
| POST | `/api/v1/agent/providers` | 新建供应商（Key 加密入库；可带 `context_window`） |
| PUT | `/api/v1/agent/providers/{id}` | 修改供应商；Key 留空表示不变；可改 `context_window` |
| GET | `/api/v1/agent/model-catalog` | 按协议/模型返回默认上下文窗口与最大输出，供表单预填 |
| DELETE | `/api/v1/agent/providers/{id}` | 逻辑删除并清空密文 |
| POST | `/api/v1/agent/providers/{id}/verify` | 轻量连通性验证 |
| POST | `/api/v1/agent/providers/{id}/set-default` | 设为默认 |
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
├─ domain/services/context_window_resolver.py
├─ config/model_catalog.json        # 模型默认窗口/最大输出（配置化）
└─ infrastructure/
   ├─ llm/openai_compatible.py
   ├─ llm/anthropic.py
   ├─ llm/provider_registry.py      # 用户供应商解析/默认选择
   ├─ llm/credential_store.py       # AES-GCM 加解密，禁止明文落盘
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
| `application/agent/agent-run-store.ts` | run 生命周期收敛为模块级单一实例：会话 id（含 run id）随 `aiChatSessionStore` 持久化，整页 / 浮窗共用同一 phase、消息补丁与取消闸；宿主挂载时用 `GET /agent/sessions/{id}` 校验会话、回填历史、收口刷新打断的气泡 | INT-2507 |
| `application/agent/agent-run-store.ts` 宿主离场 | 宿主（整页 / 浮窗）登记存活；**只有最后一个宿主按取消语义离场**（浮窗「关闭」、离开 `/ai-chat` 路由）才给 `phase ∈ {preparing,running,reconnecting}` 的 run 发一次 `cancel` 并提示「已中断当前回答」——浮窗「最小化」「展开整页」与整页 ↔ 浮窗切换不取消（INT-2507 单实例下另一宿主仍在展示该 run）；建 run 请求在途时等响应返回后补发取消，不留孤儿 run；离场判定有宽限窗口，StrictMode 双挂载不会误取消 | INT-2521（按 INT-2507 A5–A7 收窄） |
| `features/ai-chat` | 接真实事件流；保留工具卡与来源卡 | INT-2457 |
| `features/ai-chat` 审批卡 + Run 时间线 | 审批提案/diff/风险/过期；事件时间线；重连恢复待审批 | INT-2472 |
| `features/ai-chat` Report Studio 文档面板 | 取数 → 起草 → 版本 → 导出（PDF/PPTX/HTML/MD） | INT-2473 |
| Auto 模式 | 目标输入、预算设置、进度汇报、中断/暂停/继续 | INT-2477 |
| `features/agent-workbench` | 保留页面能力映射，快捷指令仍只回填不自动发送 | INT-2457（保留） |

要求：加载/空/错误态齐全；审批按钮防重复；SSE 重连不重复渲染；仅 Web 单通道，不保留 Electron/桌面壳方案。

前端会话口径（INT-2507）：整页（`/ai-chat`）与全局浮窗是同一服务端会话的两个宿主，会话 id 落在共享 store 并随消息一起持久化——展开整页、切换宿主、刷新页面后续问都延续服务端上下文。边界：刷新时若 run 仍在服务端执行，前端不重接事件流（事件游标未持久化），该轮气泡按「事件流中断」收口；会话上下文不受影响，下一轮追问仍续用同一会话（事件流游标持久化与断点续跑留给后续卡）。

## 13. 安全

1. 生产禁止 `AUTH_MODE=off`；Agent 总开关默认关闭，故障不影响人工流程。
2. 每工具逐调用校验，模型输出与前端按钮都不是授权。
3. 工具结果标记为不可信数据，其中的指令不执行；写操作必须审批。
4. 日志与事件脱敏：不落 Prompt 全文、不落密钥、不落原始音频。
5. 每个 run 可审计：谁发起、用了哪个 Skill、调了什么工具、谁批准、产生了什么副作用。
6. 外部 Skill zip 与 MCP 继续使用 `at_` Access Token，权限 = 用户权限 ∩ token scopes。
7. 用户模型 Key 加密存储、掩码返回，只在模型调用时内存解密；平台默认无 Key，禁止隐式回退。
8. 生产缺少 `AGENT_CREDENTIAL_MASTER_KEY` 时拒绝启动；主密钥轮换期间新旧版本并存。
9. 记忆文件按 tenant/owner 隔离，路径不接收模型输入；写入需审批，读取前做敏感信息扫描。

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
| M0 底座 | 单 loop、SkillRegistry、意图工具 3 个 + `tool_search`（关键词检索，INT-2453）、SSE 回放、Run 持久化；用户供应商密钥库（加密/掩码/无 Key 失败）；沙箱 T1 + T2（首期启用）；压缩 L1–L3；`platform-reference` | T1/T2 逃逸测试全拦截；60 轮压缩任务不丢事实；kill Worker 可恢复；无 Key 时明确失败且不回退平台 Key；10 条 golden tasks 通过 |
| M1 只读全平台 | 11 域只读意图工具；12 个 Skill 的 L1/L2（§4.3 余下 12 个）；`tool_search` 语义检索（关键词检索已随 M0 交付）；文件式长期记忆（`rg` 检索，无向量库） | 每域 10 条任务；Skill 触发准确率 ≥90%；无编造数值；记忆写入需审批 |
| M2 写操作与报告 | 探索-生成层（`ui_tree`/`ui_action`/`api_spec`）；写工具、审批、幂等；App/API 接入全流程（受理→发现→计划→生成→验证→迭代→交付）；驱动提案（设备驱动 + API 适配器，提案 + T2 验证，不自动发布）；Report Studio 取数→起草→版本→导出；**用户自定义 Skill（USER 级 CRUD + zip 导入导出 + 逐项校验 + 版本快照 + 触发门槛）+ Skill 管理页**；前端审批卡与时间线 | 提案→审批→执行可重放；重复执行无副作用；两类提案均可复现且未审批不写注册表；接入包在 staging 冒烟通过；三类报告指标与 Report Service 逐字段一致；自定义 Skill 不得提权、不得越权引用工具、同名不得覆盖内置、历史 run 按版本回放 |
| M3 自动化与评测 | Auto 模式、预算/熔断、全量评测；**TENANT 级共享 Skill 与发布审核流**；外部 Skill zip/MCP 对齐、文档更新 | 端到端成功率与成本达标；Agent 关闭不影响原系统；外部 Agent 能力清单一致 |

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

1. ~~默认模型与供应商~~ **已定（2026-11-12）**：用户自带 Key，AES-256-GCM 加密存 `agent_llm_provider`，按用户隔离；平台默认不提供 Key（`AGENT_ALLOW_PLATFORM_KEY=false`）；协议支持 OpenAI 兼容与 Anthropic。
2. ~~T2 沙箱~~ **已定（2026-11-12）**：首期启用，gVisor/Firecracker，禁网、无宿主挂载、无凭证。
3. ~~Auto 模式审批粒度与预算~~ **已定（2026-11-12）**：见 §9.4；WRITE 计划级批量审批，DESTRUCTIVE 单条；预算按模型上下文窗口 W 计算。
4. ~~长期记忆~~ **已定（2026-11-12）**：文件式记忆 + `rg/grep` + Skill references，不引入向量 RAG。
5. ~~上下文窗口~~ **已定（2026-11-12）**：模型目录给默认值，用户可覆盖（8k–2M，1024 对齐）；有效窗口 = 覆盖 → 默认 → 128k，预算与压缩阈值按有效窗口计算。
6. 无其他开放问题。

## 17. 参考

- https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop
- https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills
- https://agentskills.io/home
- https://openai.github.io/openai-agents-python/
- https://github.com/openai/skills
- https://code.claude.com/docs/en/agent-sdk/overview
