# 单 Agent + Skills 落地方案

> 状态：已拍板，待实施。决策日期 2026-11-12；基线 `V10.11.2`。
> 上位变更：以本文替代 [00_DeepSeek_Harness统一迁移设计.md](00_DeepSeek_Harness统一迁移设计.md) 中的 Agent Runtime 选型。
> 保留不变：[01_功能介绍.md](01_功能介绍.md) 的业务能力与工具目录、[02_用户场景.md](02_用户场景.md) 的场景目标、[05_报告优先实施路线图.md](05_报告优先实施路线图.md) 的验收口径与安全原则。
> 作废范围：DSH Runtime、DSH Worker、DSH Plugin、DSH Session；[03_技术设计文档.md](03_技术设计文档.md) 的自研 Agent Loop 旧章节同样作废，以本文第 5 节为准。

## 1. 结论

1. **唯一 Runtime：一个模型、一个上下文窗口、一个开放式工具循环**。不引入编排器，不按域拆 subagent。
2. **能力扩展方式是 Skill，不是新 Agent**。Skill 承载流程、口径、判断与踩坑；工具承载动作与实时数据。
3. **全平台 61 个业务能力全部纳入**，但内部 Agent 不暴露 207 个 MCP 原子工具，收敛为 31 个工具（含 `tool_search`、2 个记忆工具、3 个探索工具，业务意图工具 25 个）延迟加载。
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
  报告取数、指标解释与起草口径：三类报告列表 / 详情、指标矩阵、用例明细、
  维度统计、生成进度、页签计数，以及报告文本的起草与版本口径。
  触发词：报告详情、报告指标、通过率、用例平均值、报告起草。
  不适用：多报告对比 / 趋势（report-compare）；生成 / 导出 / 发布等写操作（M2）。
version: 1.0.0
owner: report-team
allowed-tools:
  - report_query
  - tool_search
permissions:
  - report:read
budgets:
  maxToolCalls: 30
  maxTokens: 50000
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

> **M1 只读落点（2026-11-13）**：`spl-calibration` 的只读能力由 `device_query` 的
> SPL 动作承载（`spl_calibrate` 仍是 M2 写工具）；`tag-group` 的只读走 `tool_search`
> 命中的 `tag_list` / `group_list`（`tag_group_manage` 仍是 M2 写工具）；
> `driver-proposal` 在 M1 只做材料准备，`driver_propose` 未启用。
> 本表「主要意图工具」列写全生命周期工具，M1 只装配其中已启用的只读项。
>
> **跨域通用工具的实际装配口径（INT-2556 订正 §4.3，2026-11-13；取代 INT-2554 的
> 「三项目前只在通用会话可调用」说法）**：`memory_search` / `memory_write` 属于
> `ALWAYS_AVAILABLE_TOOLS`（`shared/agent_tools/intent_tools.py:1438`），
> `ContextAssembler.allowed_tools()` 返回的是
> `frozenset(skill.meta.allowed_tools) | ALWAYS_AVAILABLE_TOOLS`
> （`agent_service/application/context_assembler.py:241`），`run_orchestrator._scope_denial()`
> 命中即放行（`run_orchestrator.py:857` 先判 `ALWAYS_AVAILABLE_TOOLS` 再判 Skill 声明）。
> 因此**激活任意 Skill 后这两个记忆工具仍可调用，不存在 `memory_write` 被
> `SKILL_TOOL_DENIED` 拦下的问题**，Skill 正文也不是必须把它们写进 `allowed-tools`。
> 唯一「仅通用会话可用」的是 `dashboard_query`（INT-2461）：它不在
> `ALWAYS_AVAILABLE_TOOLS` 里，13 个 M1 Skill 也都没声明它。
> 保留的后续拍板只有两条：记忆两工具是否并入基础工具集并在文档中显式声明、
> `dashboard_query` 是否给 Skill 补声明；两者都不影响当前行为。
> §16 的 INT-2556 条目按本条收口，相关缺陷卡不再按「未授权工具」处理。

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
- `TENANT` 审核状态机（INT-2551 + INT-2594）：`DRAFT --SUBMIT--> PENDING_REVIEW --APPROVE--> ACTIVE`（`REJECT` / `WITHDRAW` 回 `DRAFT`）；创建人与提交人都不得审批同一版本。`ACTIVE` 版本再次保存走显式 `EDIT` 迁移回 `DRAFT` 并落审核审计，须重新提交 + 审批；`DISABLED` 为终态（无出边，不能编辑复活）。
- 租户管理员判定 = 管理员级授予：持有通配 `*`（内置 `admin` 角色），或显式授予自定义租户管理员角色的专属权限码 `agent:skill:admin`。网关按同一 permissions 集合算出 `X-User-Is-Admin` 并下发，服务端复核「该标记 + 管理员级权限码」——两半同源（同一凭据），用于拦截绕过网关的内部调用，不是两个独立来源。
- 停用/删除立即生效；已运行的 run 按版本快照继续，不中途换内容。
- 发布门槛：至少 3 条 golden tasks 且触发判定通过；未达标只能留在 `DRAFT`，不参与自动触发。

> **TENANT 级安全与隔离验收口径（INT-2551，M3 门追加项，2026-11-14）**：
>
> 1. **跨租户按 ID 直接访问一律 404**：`GET` / `PUT` / `publish` / `disable` /
>    `fork` / `versions` 等按 id 的入口，服务层先按登录身份的租户过滤，非本租户
>    一律 404（不返回「无权访问」，不泄漏对象是否存在）；跨租户只能从可见性列表
>    得到本租户可见的条目。网关恒覆盖 `X-Tenant-Id`（客户端伪造无效），因此跨租户
>    只能靠服务层判定，不能只依赖网关。
> 2. **创建人不得自审**：创建人与提交人都不能审批同一版本（含 TENANT 管理员本人）；
>    自审请求按无权处理，不落 `APPROVE`。
> 3. **审批链可还原**：每次状态迁移（`SUBMIT` / `APPROVE` / `REJECT` / `WITHDRAW` /
>    `EDIT` / `DISABLE`）落审核审计（操作人、时间、from → to、版本号），可从审计与
>    版本历史还原完整链路；`ACTIVE` 再保存必须显式 `EDIT` 回 `DRAFT`，不能静默覆盖。
> 4. **校验与门槛不可绕过**：发布路径必须经逐项校验 + 评测门槛；绕过网关直接调内部
>    接口同样被服务层复核拦下（网关不是唯一防线）。
> 5. 平台层（`PLATFORM`）Skill 只读：由 fs 扫描 `skills/` 得到，没有「自定义包 →
>    平台层」的写入口（N/A 依据见 09 §1）。

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
| `ArtifactKind` | `DEVICE_DRIVER` / `API_ADAPTER` / `TESTCASE_SET` / `REPORT_DRAFT` / `ALGORITHM_CONFIG` / `EVALUATION_CONFIG` / `SPL_PLAN` / `DIAGNOSIS_PLAN` / `CONTEXT_TOOL_RESULT` |
| `ExplorationStopReason` | `DONE` / `BUDGET` / `LOGIN_REQUIRED` / `CAPTCHA` / `DESTRUCTIVE_BLOCKED` / `USER_CANCEL` |
| `EventType` | `run_started` / `message_delta` / `tool_call` / `tool_result` / `approval_required` / `context_compacted` / `run_finished` / `error` |

run 级预算、阈值、超时、并发数写入配置（环境变量 + `config/`），不在代码中硬编码。
工具层的聚合护栏上限（`REPORT_COMPARE_MAX_REPORTS`、`MAX_GENERATE_AUDIOS`、
`MAX_LOG_ROWS` 等）当前是命名常量，配置化登记为残留（§16 R5）。

> **压缩枚举与快照口径（INT-2536 审计回写，2026-11-14）**：
>
> 1. `ArtifactKind` 增补 `CONTEXT_TOOL_RESULT`：L1 把超限工具结果落到对象存储时
>    用该类目（实现侧复用 `TOOL_RESULT` 产物语义，不新增第二套工具结果格式）；
> 2. `agent_context_snapshot.dropped_ids` 的语义是**被压缩移出模型上下文的消息
>    ID**，L1 截断 / L2 去重时被改写（摘要化、只留计数 + TopN）的消息也计入，
>    不等同于「被删掉的消息」；L3 / L4 快照写累计值，可单条回放（代码注释同步，
>    `agent_service/application/context_assembler.py` 的 `CompactionOutcome`）；
> 3. `keep_recent_turns` 按**轮次**（同一 `turn` 的消息整组）计数，不是按消息条数；
> 4. `ContextSection.SCRATCHPAD` / `RESERVE` 是 M1 计划块与安全余量预留，
>    当前不写入内容，只参与占比校验（`agent_service/domain/model/context_budget.py` 已注明）。

## 6. 工具层

### 6.1 意图级工具（内部 Agent）

原则：按用户意图分组，不按 API 1:1。本表合计 31 个（含 `tool_search`、2 个记忆工具、3 个探索工具；业务意图工具 25 个），仍在 30–50 安全区间下限。

| 工具 | 覆盖能力 | 风险 |
|---|---|---|
| `platform_contract` | 查询字段、枚举、权限码、接口说明 | READ |
| `tool_search` | 按关键词 + 轻量语义（bigram / 词表扩展，无向量）查找长尾工具并返回 Schema | READ |
| `ui_tree` | 读取设备 UI 树：裁剪节点、截图引用、与上次快照 diff；需设备租用 | READ |
| `ui_action` | 设备 UI 动作：点击/长按/滑动/输入/返回/Home/等待；需设备租用与审批 | WRITE |
| `api_spec` | 解析 OpenAPI/proto/WS 契约：端点、鉴权、请求响应样例 | READ |
| `memory_search` | `rg` 封装：按关键词检索用户/项目记忆与 Skill references | READ |
| `memory_write` | 写入用户偏好或项目规则；需审批 | WRITE |
| `audio_query` | 音频列表、详情、按 MD5 查重（`by_md5` + `md5_list`）、标签、目录树、特征/质量、已配算法（`algorithms`）、播放历史（`playback_history`） | READ |
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

> **音频 / 算法域实现口径（INT-2523 / INT-2525 审计回写，2026-11-14）**：
>
> 1. `audio_query` 的 `by_md5` 请求体字段是 **`md5_list`**（不是 `md5`），目标
>    `POST /api/v1/audios/by-md5`；`algorithms` / `playback_history` 需 `audio_id`
>    （播放历史另支持 `page` / `per_page`）。**`by_ids` 不对外暴露**：`audio_get_by_ids`
>    是无归属校验的宿主语境批量读通道，Agent 侧不可调用（INT-2530），覆盖能力里不写它。
>    `playback_history` 在无历史时返回 `{items: [], total: 0, ...}` 的**空成功**而非
>    404，这是既有接口行为（缺口说明已登记，不在 Agent 侧改写成错误）。
> 2. 算法域 `algorithm_query` 覆盖 **16 个只读动作**：`definitions` / `definition` /
>    `definition_draft` / `groups` / `group` / `params` / `param` / `reference_params` /
>    `reference_param` / `mappings` / `case_params` / `case_param` / `form_schema` /
>    `options` / `dimensions` / `dimension_params`。参数作用域按设备 / API 两类落库
>    （`param_type=device|api`，API 参数另带 `api_id` / `field_path`），读取路径按作用域
>    过滤、写路径用 `param_type_source` 判别，不能拿读侧过滤键收窄写侧；参数层级按
>    全局 / 分组 / 算法 / 用例四层引用（`case_params` 是第四层）。表单 Schema 契约是
>    **camelCase、`groups[].fields` 数组形态**（`GET /algorithm/form-schema/{type}`），
>    默认值口径要拿 `GET /algorithm/case-params` 对照，不能凭字段名推断。

> **实现演进裁定（INT-2453，2026-11-13）**：31 个工具已在 `shared/agent_tools/intent_tools.py`
> 全量登记，名称与风险等级与本表逐项一致。M0 时只启用 `platform_contract` / `tool_search` /
> `task_query` / `report_query` 4 个（M1 已扩到 14 个，见下一条裁定）；其余 `enabled=false`
> （预留 Schema），调用返回 `TOOL_NOT_ENABLED`（不按写审批语义处理），启动不产生 `UNKNOWN_TOOL` 告警，`tool_search`
> 仍检索得到并标注 `enabled=false`。工具结果错误码固定为 `OK` / `PERMISSION_DENIED` /
> `INVALID_ARGUMENTS` / `TOOL_NOT_ENABLED` / `UNKNOWN_TOOL` / `NOT_FOUND` /
> `APPROVAL_REQUIRED` / `UPSTREAM_ERROR` / `UPSTREAM_UNAVAILABLE`。`tool_search` 的 M0 实现是
> 关键词检索 + 中英词表召回扩展，语义检索尚未实现。

> **实现演进裁定（INT-2459 / 2460 / 2461 / 2463，2026-11-13）**：M1 各域只读卡落地后，
> 口径按以下事实同步，工具总数与风险等级仍与本表逐项一致（31 项）。
>
> 1. **启用集合 14 个**（INT-2490 后为 16 个，见下一条裁定）：`platform_contract` / `tool_search` / `task_query` /
>    `report_query` / `audio_query` / `evaluation_query` / `algorithm_query` /
>    `device_query` / `testcase_query` / `testcase_generate` / `task_diagnose` /
>    `log_diagnose` / `dashboard_query` / `report_compare`；其余 17 个 `enabled=false`
>    （含 5 个预留名称 `memory_search` / `memory_write` / `ui_tree` / `ui_action` / `api_spec`）。
> 2. **`device_query` 覆盖 SPL 只读**（INT-2459）：物理域 `/api/v1/spl` 与数字域
>    `/api/v1/digital-spl` 的只读端点折进本工具的 `spl_*` / `digital_spl_*` 动作，
>    不新增 SPL 只读意图工具，也不进对外 MCP 1:1 清单；调用按 `action` 收窄到
>    `device:read` / `spl:read` / `digital_spl:read` 三域之一。`spl_calibrate` 仍是 M2 写工具。
> 3. **本地实现（不直接映射单一 REST）**：`testcase_generate`（标注 → 用例草案，只读推导、
>    不落库）、`task_diagnose` 与 `log_diagnose.diagnose`（多个只读接口聚合并带来源 ID）、
>    `report_compare`（按报告 ID 逐个 `GET /reports/{id}` 并排；平台 `POST /reports/compare`
>    会落库生成报告，属写操作，不作只读工具暴露）。
> 4. **标签 / 分组只读无专用意图工具**：走 `tool_search` 命中的 MCP 长尾
>    `tag_list` / `group_list`；`tag_group_manage` 仍是 M2 写工具。
> 5. **权限待规格**：`driver_propose` 的权限码在 RBAC 尚未建立（`memory_write` 已随
>    INT-2490 启用，见下一条裁定）。未启用期间，普通账号调用先返回 `PERMISSION_DENIED`，
>    只有 `*` 通配权限才走到 `TOOL_NOT_ENABLED`（fail-closed，两种结果都不执行）。

> **实现演进裁定（INT-2465 / INT-2490，INT-2554 收口审计，2026-11-13）**：
>
> 1. **启用集合 16 个**：上文 14 个只读工具 + `memory_search` / `memory_write`；其余
>    15 个 `enabled=false`，其中预留名称 3 个（`ui_tree` / `ui_action` / `api_spec`）。
>    工具总数与风险等级仍与本表 31 项逐项一致。
> 2. **记忆两工具不走 RBAC 码**：`memory_search`（READ）/ `memory_write`（WRITE）的
>    `permissions` 为空 = 只要求登录；隔离由服务端按登录身份构造
>    `memory/tenants/<tenant>/users/<owner>/` 路径保证（§8.6.1），模型入参里没有
>    tenant / owner / 任意路径。`memory_write` 只生成 `PENDING` 提案、本人审批后落盘
>    （M2 通用审批服务 INT-2466 未合入前的占位，见 §8.6.1 后「实现口径」注）。
> 3. **`tool_search` 三层检索**（INT-2465）：关键词（名称 / 描述子串）→ 轻量语义
>    （中文 bigram + 英文分词 + 中文意图词表 `_SYNONYMS` + 同族词 `_CONCEPTS` 的覆盖率
>    打分）→ 归属标注（每条结果带 `intent` / `external_only`，与覆盖矩阵同源）。
>    **不含 embedding 或向量库**：INT-2453 注里的「语义检索尚未实现」指向量语义检索，
>    至今仍未实现；INT-2465 交付的「轻量语义」是确定性词面扩展，不得对外称语义检索。
>    真实模型级检索质量评测归 M3（INT-2475）。
> 4. **索引视图 205 ≠ 对外 MCP 总量 207**：`TOOL_INDEX` = 205 条 MCP 条目（207 −
>    `audio_get_by_ids` 不索引 − `report_compare` 由已启用意图工具顶替）+ 30 条意图
>    工具条目 = **235** 条。代码注释里的「205 个 MCP 工具」指索引视图；对外
>    `tools/list` 以 §6.2 的 207 为准（同一口径也解释了 INT-2547 P3-1 的注释差异）。
> 5. **归属矩阵**：`shared/agent_tools/COVERAGE.md` 由 `shared/agent_tools/coverage.py`
>    生成（禁止手改），207 项逐行有结论：内部归属 198 / 仅外部 MCP 9 / 归属到 20 个
>    意图工具；11 个意图工具是本地能力、无 MCP 归属。校验命令：
>    `python -m shared.agent_tools.coverage --check`。
> 6. **P3 收口**（INT-2547 八条 + 本次新增）见 §16「已登记残留」；其中代码注释 / Skill
>    文案类不改本方案的对外口径。

> **实现演进裁定（INT-2467，2026-11-14）**：M2 第一批域写工具落地，工具总数与风险
> 等级仍与 §6.1 表 31 项逐项一致。
>
> 1. **启用集合 21 个**：M1 的 16 个 + `audio_import` / `audio_annotate` /
>    `device_control`（`DESTRUCTIVE`）/ `spl_calibrate` / `driver_propose`；其余
>    10 个 `enabled=false`（`testcase_write` / `tag_group_manage` /
>    `evaluation_manage` / `algorithm_manage` / `task_run` / `report_generate` /
>    `report_export` 与预留的 `ui_tree` / `ui_action` / `api_spec`）。
> 2. **写路径一律先提案后审批**：域写工具的动作 → 目标 REST 由
>    `shared/agent_tools/audio_tools.py` / `device_tools.py` 解析，执行走 INT-2466
>    的 `agent_approval`（提案 / 决策 / 幂等 / 审计），网关无审批凭据不执行。
> 3. **`device_control` 二次确认**：破坏性工具批准必须同时带 `confirm=true`
>    （决策接口 400 + `APPROVAL_CONFIRMATION_REQUIRED`），提案 `diff` 里带
>    `second_confirmation` 供审批端渲染；拒绝不需要确认。
> 4. **`driver_propose` 权限**：RBAC 仍无独立驱动码（INT-2501 待规格），INT-2467
>    改用 `device:update` 作为持有者判定（驱动属于设备接入能力；工具只产提案，
>    发布默认关闭）。若需求规划师后续定出专用码，只改工具声明的 `permissions`。
> 5. **`driver_propose` 实现**：本地工具（不映射 REST）。确定性模板生成
>    `AppDriver` / `ApiVendorAdapter` + `capabilities.json` + `manifest.json` +
>    `tests/`，宿主侧做 AST / JSON / 契约静态检查（不执行生成代码），再由
>    `SandboxRunner.run_untrusted_code` 在 T2 跑 导入/编译、单测、mock 厂商契约
>    （仅含 API 适配器时）、注册表 resolve。运行时不可用即
>    `T2_RUNTIME_UNAVAILABLE`（不降级）；静态检查或 T2 失败 → `publishable=false`。
>    发布是内部步骤：需 `AGENT_DRIVER_PUBLISH_ENABLED=true` + 已批准的独立审批单，
>    本期无注册表写入通道（只保留守卫）。
> 6. **SPL 写目标**：物理域 / 数字域没有对外 MCP 工具（§6.2 冻结 207 项），以
>    Agent 专用 REST 目标声明在 `device_tools.SPL_CALIBRATE_TARGETS`，只经
>    `spl_calibrate` 暴露；权限按动作收窄到 `spl:*` / `digital_spl:*`。

### 6.2 外部 MCP

- 保持 `POST /api/v1/mcp` 的 1:1 工具语义不变：工具名 / 路径 / 权限声明逐项一致。
  **实现演进裁定（INT-2461 / INT-2463，2026-11-13）**：工具数由 205 增至 **207**
  （新增 `home_stats_details` / `home_stats_summary` 两个首页只读工具）；
  `log_list` / `log_stats` / `report_list` / `report_statistics` /
  `report_statistics_trend` / `report_cases` 补声明网关真实支持的**可选**查询参数
  （不改既有参数语义、不移除参数）。外部 `tools/list` 以本节为准；
  `api_gateway/application/services/mcp/tools_registry.py` 已改为 re-export，不再保存第二份 Schema。
- 工具总数口径（INT-2554 审计）：对外 `tools/list` **207** 项；`tool_search` 的索引视图
  205 条 MCP 条目（207 − `audio_get_by_ids` − 由意图工具顶替的 `report_compare`）不是对外
  总量，两者不要混用。207 项的逐条归属（内部归属 / 仅外部）见
  `shared/agent_tools/COVERAGE.md`。
- 注册表抽到 `shared/agent_tools/`，Gateway MCP 与 `agent_service` 共用，禁止复制两份 Schema。
- 外部 Agent 的上下文管理由客户端负责，不做意图收敛。
- **参数口径（INT-2523 回写）**：按 MD5 查重的外部工具 `audio_get_by_md5` 请求体
  字段是 **`md5_list`**（数组），不是 `md5`；`playback_history` 目标
  `GET /api/v1/audios/{id}/playback-history` 在无历史时返回 `items=[]` 的空成功，
  按正常空结果消费，不当错误（既有接口行为，缺口已登记）。

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

#### 服务端通道（INT-2569 定稿，INT-2577 / INT-2578 实现）

> **实现演进裁定（INT-2597 一致性审计，2026-11-14）**：本节此前只写工具层口径，没有服务端通道的
> 契约。设备侧 UI 能力已由 INT-2577（device_service 三 RPC）与 INT-2578（网关三端点）实现，以下
> 为实现后的契约事实，逐条与 V10.11.2 代码一致（`github/V10.11.2 = 92145961a`）：动作白名单与业务码
> 见 `shared/constants/ui_capture.py`，网关路由见 `api_gateway/routes/device_bp.py`，服务端语义见
> `device_service/interfaces/grpc/device_ui_servicers.py`。

拓扑固定为 agent 适配器 → 网关 REST（带 run 的 `Authorization`）→ `device_service` gRPC
`DeviceUiService`；权限与审计执行点在网关（`require_permission`），**不允许 agent 直连 gRPC 绕过
网关**（INT-2569 D1）。三个端点：

| 方法 | 路径 | 权限 | 请求体 |
|---|---|---|---|
| POST | `/api/v1/test-devices/{device_id}/ui/tree` | `device:read` | `{}` |
| POST | `/api/v1/test-devices/{device_id}/ui/screenshot` | `device:read` | `{"label": "a3"}`（可选，网关限长 64；不参与对象键，当前仅透传给 gRPC） |
| POST | `/api/v1/test-devices/{device_id}/ui/action` | `device:control` | `{"action_type": "TAP", "node": {...}, "params": {...}}` |

响应统一 `to_response(...)` 信封 `{success, message, code, data}`，成功 `code` 为空串；`data` 与
gRPC 同形（网关只做 JSON 解码，不二次包装、不做业务归一化）：

- tree：`{platform, format, payload, node_count, degraded, degrade_reason}`。`platform` ∈
  `ANDROID` / `HARMONYOS`，`format` ∈ `ANDROID_XML` / `HARMONY_COMPONENTS`；`payload` 是平台原始
  结构文本，**不裁剪也不截断**（`MAX_TREE_NODES=200` 的裁剪只在 agent 适配器 `crop_nodes` 生效），
  设备侧对 `payload` 设 8 MB 上限。
- action：`{action_type, performed, elapsed_ms}`；`BUSY` 时附 `{holder, waited_seconds, queue_ahead}`。
- screenshot：`{screenshot_ref, format, width, height}`；`screenshot_ref` 是 OSS 对象键，
  **不返回 base64、不落数据库**。

动作白名单与错误码是单一事实源 `shared/constants/ui_capture.py`：动作取 `UiActionType` 七枚举
（`UI_ACTION_TYPE_VALUES`，网关与 device_service 同一份），非枚举值 400 `ACTION_NOT_ALLOWED` 且
不下发，device_service 侧二次校验。业务码 → HTTP：

| code | HTTP | 说明 |
|---|---|---|
| `DEVICE_NOT_FOUND` | 404 | 设备不存在 |
| `ACTION_NOT_ALLOWED` | 400 | 非七枚举；网关侧请求体校验失败（动作 / 截图共用此码） |
| `ELEMENT_NOT_FOUND` / `TREE_TOO_LARGE` / `PLATFORM_UNSUPPORTED` | 400 | 元素定位失败 / 树超 8 MB / 平台不支持 |
| `BUSY` | 409 | 同 SN 锁等待超出预算 |
| `UI_CAPTURE_UNAVAILABLE` | 503 | 驱动不可用或上游不可达（附 `degrade_reason`） |
| 未登记码 | 500 | 网关与 device_service 契约不一致，不掩成 400 |

`code` 全程原样透传，**调用方按 `code` 判型，不靠 message 字符串**。每次动作调
`write_device_audit(AuditEvent.DEVICE_CONTROL_EXECUTED, 'device_ui', {...})`，成功 / 被白名单拦截 /
设备拒绝都记（`device_id` / `action_type` / `node` / `params` / `success` / `code`，operator 由审计
助手补）；旁路写入失败不影响业务结果。审批、预算、破坏性拦截仍在 agent 层（INT-2492），网关既不
复制也不绕过。残留口径见 §16。

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

> **沙箱失败原因码 → run 终态映射（INT-2532 D2 回写，2026-11-14）**：
> 失败原因码统一用 `SandboxFailureReason`（`agent_service/application/sandbox_runner.py`），
> 不另造魔法值；`RunOrchestrator._finish_sandbox_failure` 按 `SandboxOutcome` 收口：
>
> | 原因码 | SandboxOutcome | run 终态 |
> |---|---|---|
> | `TIMEOUT` / `OUTPUT_LIMIT_EXCEEDED` / `MEMORY_LIMIT_EXCEEDED` / `RESOURCE_LIMIT_EXCEEDED` | `BUDGET_EXCEEDED` | `BUDGET_EXCEEDED` |
> | `UNSUPPORTED_TIER` / `SCRIPT_NOT_FOUND` / `SCRIPT_OUTSIDE_SKILL` / `INVALID_INVOCATION` / `EXIT_CODE_NONZERO` / `CONTAINER_START_FAILED` / `RUNNER_ERROR` / `ARTIFACT_INVALID` / `ARTIFACT_TOO_LARGE` / `ARTIFACT_TOO_MANY` / `T2_RUNTIME_UNAVAILABLE` / `CODE_PROVENANCE_MISSING` / `CODE_PROVENANCE_MISMATCH` / `EGRESS_DENIED` / `INPUT_INVALID` | `FAILED` | `FAILED` |
>
> 落 `error` 与 `run_finished` 事件时同时带 `reason` 与 `reason_code`（同值），前端
> 按 `reason_code` 分支文案，不解析中文。**T1 / T2 产物超限差异**：T1 原始输出按
> 执行器 `output_limit_bytes`（默认 1 MB）截断，超过 1 MB 判
> `OUTPUT_LIMIT_EXCEEDED`；`/work` 产物按 `AGENT_SANDBOX_MAX_ARTIFACTS`（32）/ 单文件
> `AGENT_SANDBOX_MAX_ARTIFACT_BYTES`（8 MB）/ 总量 `AGENT_SANDBOX_MAX_TOTAL_ARTIFACT_BYTES`
> （32 MB）校验。T2 前三阶段（导入 / 编译、单测、mock 契约）除同样受 1 MB 输出上限
> 外，产物随阶段回收且**不跨阶段累积**；任一阶段超限按 `RESOURCE_LIMIT_EXCEEDED` /
> `ARTIFACT_TOO_LARGE` 失败，不降级到 T1、不判成功。
> **「T2 接 Loop」边界**：T2 目前只被驱动提案 / 接入验证等白名单动作调用，普通
> 对话与只读工具仍在 T0/T1；把 T2 接进通用 Loop 需要新卡（沙箱成本与延迟另评）。

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

1. 不引入向量库、embedding 或语义检索；沿用 DSH 的文件式记忆形态（用户偏好 / 项目记忆 / 话题记录 / 会话 JSONL），文件树按 §8.6.1 隔离落位：`memory/tenants/<tenant_id>/users/<owner_id>/user_profile.md`、`.../projects/<project>/project_memory.md`、`.../projects/<project>/<date>/topics.md`；会话正文归 `agent_context_snapshot`，不另存第二份。
2. 知识获取靠 `rg`/`grep` + 文件读取 + Skill `references/`；代码与文档不做索引同步。
3. 记忆分三层：用户偏好（跨项目）、项目规则（含本方案）、会话备忘（`run_scratchpad` + `context_snapshot`）。
4. 写入只允许：用户显式“记住”、审批通过的 `memory_write`、run 结束的结构化备忘；禁止模型把猜测写入长期记忆。`memory_write` 只生成 `PENDING` 提案，审批通过才落盘（M2 前由本人经 §11 的 memory 提案接口审批）。
5. 会话开始时只注入用户偏好与项目规则摘要（`AGENT_MEMORY_INJECT_MAX_TOKENS`，默认 600）；细节由 `memory_search` 按关键词取。
6. 记忆按 tenant/owner 目录隔离，路径不接收模型输入，写入前做敏感信息扫描（规则见 `agent_service/config/memory_sensitive_rules.json`：凭证类 `block`、PII `redact`）；检索、写入、审批与 break-glass 一律写 `memory/.audit/<tenant>.jsonl`，只记元数据、不落正文。

#### 8.6.1 隔离模型（默认严格按用户）

1. 目录：`memory/tenants/<tenant_id>/users/<owner_id>/...`；路径由服务端从登录身份构造，模型不能传入 `tenant_id`、`owner_id` 或任意路径。
2. 读取：`memory_search` 自动附加 tenant + owner 过滤；跨用户、跨租户一律返回空，不泄漏“是否存在”。
3. 写入：`memory_write` 只能写调用者自己的目录，且必须审批；拒绝 `..`、绝对路径、软链与符号链接穿越。
4. 平台规则与 `skills/references/` 是只读共享知识，不属于任何用户记忆，不能经 `memory_write` 修改。
5. 共享记忆默认关闭；确需团队共享时，只能由租户管理员显式开启独立的 tenant 级区域，并单独授权与审计。
6. 管理端默认只能看元数据（条数、更新时间），不能读内容；break-glass 读取必须留审计记录。
7. 会话与 Run 同样按 owner 隔离：`agent_session`、`agent_run`、`agent_run_event` 的查询强制带 `owner_id`。
8. 验收用例：A 读不到 B；跨租户读不到；路径穿越失败；提示注入无法改变身份；导出/删除只作用于本人。

> **实现口径（INT-2490，2026-11-13）**：`memory_search` / `memory_write` 已在
> `agent_service` 落地并启用（`shared/agent_tools/intent_tools.py` 两项 `enabled=true`，
> 权限只要求登录——记忆域无 RBAC 码，隔离由服务端按身份构造路径保证）。检索为
> `rg --fixed-strings --json`（镜像内安装 ripgrep，缺失即返回
> `MEMORY_BACKEND_UNAVAILABLE`，不静默当空结果）；路径组件只接受
> `[A-Za-z0-9._-]`，`..` / 绝对路径 / `~` / 软链或 junction 穿越全部拒绝并留审计。
> 写入走提案占位：M2 审批服务 INT-2466 未合入前，`memory_write` 只生成 `PENDING`
> 提案（`memory/.proposals/<tenant>/<owner>/<id>.json`，不在用户树内），由本人经
> `POST /api/v1/agent/memory/proposals/{id}/approve|reject` 审批；批准后文件内容与
> 预演 `preview` 逐字一致，文件已被改动则判冲突不覆盖。敏感信息规则配置化
> （`agent_service/config/memory_sensitive_rules.json`）：凭证类 `block`、PII `redact`。
> 审计写 `memory/.audit/<tenant>.jsonl`，只含 `ts / action / tool / run_id /
> tenant_id / owner_id / args_hash / decision / result_code / reason / rules`；
> `memory_write` 在 `agent_tool_call` 中的 `content` 以 sha256 + 长度代替。
> 会话开始只注入用户偏好 + 项目规则摘要（默认 600 tokens）；话题与细节由
> `memory_search` 取。每用户配额 `AGENT_MEMORY_USER_QUOTA_BYTES`（默认 20 MiB）只
> 回报用量、不阻断写入，自动清理策略留后续卡。管理端 break-glass 读取走
> `GET /api/v1/agent/memory/break-glass`，需 `memory:break_glass`（RBAC 尚未建码 =
> fail-closed，只有 `*` 通配可读），读取留审计。

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

> **终态事件口径（INT-2532 D3 回写，2026-11-14）**：`run_finished` 与 `error` 事件
> 都带 `reason` + `reason_code`（预算超限、沙箱失败、Auto 完成 / 熔断、连续失败等
> 机器码），前端与审计按 `reason_code` 分支，`reason` 只作人读摘要。run 进入
> `FAILED` / `BUDGET_EXCEEDED` 后不得再被恢复投递续跑；已产生的产物与事件保留。

### 9.4 Auto 模式：审批粒度与预算（已定）

审批粒度：

- `READ`：自动执行。
- `WRITE`：默认“计划级批量审批”，一次展示该步骤全部写操作 + diff/预览；以下必须单条审批：`DESTRUCTIVE`、单次影响 > 20 个对象、跨租户、导出含敏感数据、删除类。
- `DESTRUCTIVE`：永远单条审批，不允许批量或 Auto 预授权。
- Auto 只预授权 `WRITE`，启动前必须展示计划与预算；预算到 80% 或连续 2 次工具失败时暂停。

#### 9.4.1 「>20 对象强制单条」落地契约（INT-2571 定稿，2026-11-14）

上面「单次影响 > 20 个对象必须单条审批」在 M2 现行实现（一次 tool call 一张
`agent_approval`，`(run_id, tool_call_id)` 唯一）下的落地口径。**拆单 = 把一次 tool
call 拆成 N 张审批单，决策逐张、执行仍然只有一次。**

1. **对象计数**只统计参数里显式枚举的独立对象，按 `(kind, id)` 去重后计数；计数来源
   必须登记在「可拆参数注册表」（工具 + 动作 + 参数路径 + 对象 kind）。未登记的参数
   不参与计数；**写入工具新增的数组参数必须在注册表里显式分类**（拆 / 原子 /
   不适用），注册期测试枚举写工具的数组参数，漏登记判红（对齐 INT-2562 风险探针的
   fail-closed 做法）。非枚举范围（`mode=all` / `failed_only` 这类由服务端决定影响面）
   按 1 个对象计，审批单必须展示范围语义（`mode` / 上级对象），不伪造数量。
   一个参数可拆的前提：**只带其中一个对象时该调用仍然合法**（`merge` 这种少一个对象
   就非法的动作因此不可拆）。
2. **阈值**：严格 `> 20` 才拆，`= 20` 不拆。服务端配置
   `AGENT_APPROVAL_SPLIT_THRESHOLD` 默认 20，只允许收紧；请求不可放宽。拆单粒度
   `AGENT_APPROVAL_SPLIT_CHUNK_SIZE` 默认 1（每对象一张单）。重复对象只计一次，
   分块顺序按参数原顺序（去重后）。
3. **单次调用对象上限** `AGENT_APPROVAL_MAX_OBJECTS`（默认 100）：超过不建单，提案前
   直接拒绝 `APPROVAL_OBJECT_LIMIT_EXCEEDED`，提示模型改成多次调用（避免一次调用
   在库里堆出上千张单）。
4. **拆单产物**：一次 tool call → N 张审批单，共享 `batch_id`，各带 `batch_index`
   （1..N）/ `batch_total` / `object_ref = {kind, ids}`；`proposal.object_count` 是本批
   总对象数。**每张单的 `proposal.arguments` 与 `diff` 收窄到本单负责的对象**（用户
   逐张看到的就是这一份），完整参数保留在 `agent_tool_call.arguments` 供审计。唯一键
   改为 `(run_id, tool_call_id, batch_index)`；`list_for_run` 不再假设一次调用一张单。
5. **执行语义：全批准才执行（all-or-nothing），不逐单执行、不部分执行。**
   - 同批任一单 `PENDING` → run 停在 `WAITING_APPROVAL`，不执行；
   - 全部 `APPROVED` → 用**完整原始参数**执行一次（执行前按每张单的
     `decision_permissions` 快照逐一复核，任一不再授权即整批不执行）；
   - 任一单 `REJECTED` → 整批拒绝，其余 `PENDING` 自动转 `REJECTED`，回灌
     `APPROVAL_REJECTED`（带被拒对象）；
   - 任一单 `EXPIRED` 且整批未全批准 → 整批按 `APPROVAL_EXPIRED` 收口，其余
     `PENDING` 转 `EXPIRED`；若全批准发生在过期之前则照常执行。
   不做逐单执行：网关一次调用就是一个业务动作（`merge` 这类集合操作必须一次成型），
   拆成多次执行会造出非法中间态；也不做「部分对象执行」。
6. **决策接口不变**：仍按 approval id 逐张决策，本卡不提供批量决策端点
   （§9.4 的批量单条正是为了禁止一键放行）；`confirm=true` 仍只属于 DESTRUCTIVE。
7. **DESTRUCTIVE 恒一张单**（`batch_total=1`）：`device_control` 的 `device_ids`
   只计数、不拆单，不参与 Auto 预授权；前端对 DESTRUCTIVE 批量维持逐项核对展示。
8. **原子集合操作不拆单**：`task_run.merge`（`body.task_ids`）是一个原子动作，保持
   一张单，审批单展示对象数；后续同类工具在注册表标 `atomic`。
9. **恢复幂等**：拆单是 `(参数, 配置)` 的确定性函数；同一 tool call 已存在任一单时整批
   复用（不按新配置重建），`(run_id, tool_call_id, batch_index)` 唯一键兜底。
10. **SSE**：`approval_required` 每张单一条事件，载荷带 `batch_id` / `batch_index` /
    `batch_total` / `object_count`，同一批的 `tool_call_id` 相同。
11. **预算口径**：等人工审批的时长按批次取区间并集计一次，不能按 N 张单累加
    （否则同一段等待被重复扣除，§9.3 执行时长预算被放大）。
12. **前端**：审批面板按卡逐张渲染（已支持多卡同屏）；批次卡需显示「第 i/N 条 ·
    本批 N 条全部批准后才执行」。INT-2472 已实现的「>20 对象强制逐项核对」保留作
    纵深防御（DESTRUCTIVE 批量、以及拆单前的历史提案仍靠它兜底），批次卡本身
    不再触发逐项核对。
13. **§9.4 其余「必须单条」类别**：M2 工具面里没有跨租户参数（隔离由服务端按登录
    身份构造），删除类动作在动作级已是 `DESTRUCTIVE`，导出含敏感数据（`report_export`）
    仍是 reserved；这三类一律不进拆单注册表。未来新增同类能力必须按 `DESTRUCTIVE`
    处理（单张 + `confirm=true`），不得靠拆单绕开二次确认。

M2 现行可拆参数登记（定稿；注册期枚举全部写工具数组参数，未列入本表的必须给出
`atomic` / `not_applicable` 分类，否则测试判红）：

| 工具 | 动作 / 条件 | 参数路径 | 对象 kind | 分类 |
|---|---|---|---|---|
| `tag_group_manage` | `batch_tag` 且 `batch_action ∈ {add_tags, remove_tags}` | `ids` | `testcase` | 拆 |
| `audio_annotate` | `batch_annotate` | `items[].audio_id` | `audio` | 拆 |
| `task_run` | `retry` 且 `body.mode=selected` | `body.case_ids` | `testcase` | 拆 |
| `evaluation_manage` | `reevaluate` 且 `body.mode=selected` | `body.case_ids` | `testcase` | 拆 |
| `device_control` | `batch` | `device_ids` | `device` | 计数不拆（DESTRUCTIVE） |
| `task_run` | `merge` | `body.task_ids` | `task` | 原子（不拆） |
| 其余写工具数组参数（`audio_import.tags`、`audio_annotate.algorithms`、`testcase_write.tags`、`tag_group_manage.tags`、`evaluation_manage.body.dimension_ids` 等） | — | — | — | 属性 / 范围，不计入对象数 |

注：`evaluation_manage.reevaluate` 只有在 `mode=selected` 时 `case_ids` 才决定影响面；
`mode=all` / `failed_only` 按非枚举范围计 1 个对象（见第 1 条）。

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

> **实现口径（INT-2474，2026-11-14）**：Auto 与普通对话共用同一条 Loop，
> 入口是 `POST /agent/sessions/{id}/runs` 的 `mode: chat|auto`（默认 chat）；
> `budget` 可随请求下发但**只收紧**（`min(服务端, 请求值)`，`0`/负数视为不覆盖，
> 未知键 400 `INVALID_BUDGET`；`mode` 非法 400 `INVALID_RUN_MODE`）。
> `run_started` 载荷带 `mode` / `budget`（Auto 再带 `pause_policy = {budget_ratio,
> consecutive_failures}`），前端在开跑前即可展示预算与暂停规则（`budget.max_tokens`
> 为 0（默认）表示按有效窗口派生、Auto 取 4×W，实际生效上限见 `auto_step.limits`）；
> 计划自第 2 轮起随 `auto_step.plan` 下发：首条 `auto_step` 早于模型首轮、尚无计划，
> 模型首轮文本作为计划摘要写进下一 step 的 `scratchpad.plan`（INT-2601 审计订正）。
>
> 进度/控制事件（SSE，均带 `run_id` / `sequence` / `timestamp`）：
> - `auto_step`：每轮一条，含 `step` / `phase(step|continue|resume)` / `goal` /
>   `plan` / `usage`（rounds、tool_calls、tokens、elapsed_seconds、output_bytes）/
>   `limits` / `ratios` / `ratio` / `artifact_count` / `artifacts` /
>   `idle_nudges`（累计空转提示次数，重启恢复用）；`continue` /
>   `resume` 两种 phase 另带 `instruction`（该轮回灌模型的续跑提示，随本轮
>   请求立即送达，不是下一轮才补）；
> - `run_paused`：`reason ∈ {budget_threshold, consecutive_tool_failures}` +
>   当时的 `usage` / `ratio`，并按暂停类型附 `pause_budget_ratio`（预算阈值，如 0.8）
>   或 `pause_consecutive_failures`（连续失败阈值，如 2）；实现同时下发这两个字段，
>   前端不用从 `usage` 反推；run 转 `WAITING_APPROVAL`（等用户决策，不计入执行时长）；
> - `run_resumed`：用户点「继续」，记录 `pause_reason` / `consecutive_failures` /
>   `acked_budget_pause`（只有从 `budget_threshold` 暂停点继续才置 true，
>   因连续失败暂停的继续不确认预算暂停点）；用户继续后**同一预算暂停点不再
>   触发**，硬预算仍生效。控制状态在重启后按事件尾部重建，不受 `auto_step` /
>   `message_delta` 事件总数影响。
>
> 继续入口 `POST /agent/runs/{id}/resume`：仅暂停态 Auto run 可用；仍有待审批
> 提案时 409（先处理审批单，审批决策本身会唤醒 run）；已终态 / 非 Auto /
> 非本人 409/404。暂停态在进程重启后**不会**被恢复投递静默续跑。
>
> 停止条件：连续工具失败 2 次暂停、3 次熔断（`FAILED` +
> `CONSECUTIVE_TOOL_FAILURES`，不再自动重试）；模型在最终文本输出完成标记
> （默认 `[[AUTO_DONE]]`，`AGENT_AUTO_COMPLETE_MARKER`）→ `SUCCEEDED`
> （`run_finished.reason=auto_complete`）；无标记又不调工具的空转达
> `AGENT_AUTO_MAX_IDLE_TURNS` 次 → 按完成收口（`auto_idle_limit`）。
> 长任务恢复：非首轮进入 Loop 时按 L4_REBUILD 从 `agent_step`（计划 /
> scratchpad）+ `agent_tool_call`（已生效 / 待审批写操作）+ `agent_artifact`
> 重建状态块并落 `L4_REBUILD` 快照，已完成的写操作明确「禁止重复提交」。
> **边界**：Auto 下 WRITE 仍逐次走 M2 的提案 → 审批链（「计划级批量审批」尚无
> 实现卡），DESTRUCTIVE 恒单条且不参与任何预授权；若产品要求 Auto 免逐次审批
> WRITE，需新开卡改审批语义与审计。

#### 9.4.2 前端实现口径（INT-2621 审计回写，2026-11-14）

1. **Auto 下 `WAITING_APPROVAL` 有两种语义**：①预算阈值 / 连续失败**暂停**（可点
   「继续」，有 `run_paused` 事件与 `pause_reason`）；②**待审批提案**（有
   `approval_required` 事件与待决策审批单，继续入口 409，必须先处理审批）。
   前端区分依据是事件类型与 `run.resume` 可用性：有 `run_paused` 且无待审批提案
   → 展示「继续」；有待审批提案 → 展示审批卡，不给「继续」按钮。
2. **刷新恢复**：刷新后**不重接事件流**（事件游标未持久化），按
   `GET /agent/runs/{id}` 取快照收口该轮；点「继续」后同样只用快照轮询跟随终态
   （首查 1.5s，之后 5s 间隔，30 分钟上限，连续 4 次失败即停止轮询并提示中断）。
3. **终态口径**：`BUDGET_EXCEEDED` / 熔断（`FAILED` + `CONSECUTIVE_TOOL_FAILURES`）
   **不显示成功**；已生成的正文保留在气泡里，只落一个终态徽标，不把文本清空。
4. **预算录入单位**：UI 以「分钟 / MB」录入时长与输出字节，请求层换算成秒 / 字节
   再发给服务端（`budget` 仍只能收紧，见本节实现口径）。

## 10. 数据模型

| 表 | 关键字段 |
|---|---|
| `agent_session` | id, owner_id, tenant_id, title, active_skill, model, created_at, updated_at |
| `agent_llm_provider` | id, owner_id, tenant_id, name, protocol, base_url, model, api_key_ciphertext, **api_key_mask**（列表直接读掩码，不解密）, key_version, context_window, context_window_source, is_default, status, last_verified_at, created_at, updated_at |
| `agent_run` | id, session_id, owner_id, status, model, budget, token_in, token_out, started_at, finished_at, error |
| `agent_run_event` | id, run_id, sequence, type, payload, created_at |
| `agent_step` | id, run_id, index, plan_snapshot, status, created_at |
| `agent_tool_call` | id, run_id, step_id, tool, args_hash, risk, status, result_ref, latency_ms, permission_decision, result_code |
| `agent_approval` | id, run_id, tool_call_id, proposal, diff, status, expires_at, decided_by, decided_at；拆单批次（INT-2571）：batch_id, batch_index, batch_total, object_ref |
| `agent_artifact` | id, run_id, kind, uri, size, metadata |
| `agent_context_snapshot` | id, run_id, version, token_count, dropped_ids, memo, level |
| `agent_skill` / `agent_skill_version` | 自定义 Skill 与版本快照，字段见 §4.4；M2/M3 交付，当前未建表 |

索引：session owner、run owner/status、(`run_id`, `sequence`)、approval status/expiry、(`run_id`, `tool_call_id`, `batch_index`) 唯一（拆单后一次调用多张单，INT-2571）、idempotency key 唯一索引。

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
| POST | `/api/v1/agent/runs/{id}/resume` | Auto 暂停后继续（INT-2474）|
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
| GET | `/api/v1/agent/memory/metadata` | 本人记忆条数 / 更新时间 / 用量（不含正文；INT-2490） |
| GET | `/api/v1/agent/memory/proposals` | 待审批记忆写入提案（含预演 `preview`） |
| POST | `/api/v1/agent/memory/proposals/{id}/approve` | 按预演落盘（文件被改动则判冲突） |
| POST | `/api/v1/agent/memory/proposals/{id}/reject` | 拒绝提案，无副作用 |
| GET | `/api/v1/agent/memory/break-glass` | 管理端读取正文，需 `memory:break_glass`，留审计 |
| GET | `/api/v1/agent/skill` | 外部 Skill zip 下载（保留） |
| POST | `/api/v1/mcp` | 外部 MCP（保留） |
| POST | `/api/v1/test-devices/{device_id}/ui/tree` | 设备 UI 树（`device:read`；平台原始结构，不裁剪）——INT-2569 / INT-2578 |
| POST | `/api/v1/test-devices/{device_id}/ui/screenshot` | 设备截图（`device:read`；只回 `screenshot_ref` 对象键）——INT-2569 / INT-2578 |
| POST | `/api/v1/test-devices/{device_id}/ui/action` | 设备 UI 动作（`device:control`；`UiActionType` 七枚举白名单）——INT-2569 / INT-2578 |

SSE 事件载荷统一包含 `run_id`、`sequence`、`type`、`timestamp`；`message_delta` 带 `message_id`，避免重连重复拼接。

> **SSE 与信封口径（INT-2517 D1–D7 回写，2026-11-14）**：
>
> 1. **三种 JSON 信封**由网关透明转发、前端按路径区分：
>    - run 发起：`{run, created}`（`created=false` 表示幂等命中已有 run）；
>    - 会话详情：`{session, messages, runs}`；
>    - 列表类：`{"items": [...]}`。
> 2. **游标语义**：严格 `sequence > cursor`；`Last-Event-ID` 与 `?cursor=` 同时出现时
>    取**较大值**；SSE 的 `id:` 字段就是游标值（同一条事件重放幂等）。
> 3. **网关合成的 error 帧**：上游转发失败时网关生成 `type=error` 的帧，`code` 为
>    `UPSTREAM_ERROR`（上游返回错误）/ `UPSTREAM_UNAVAILABLE`（连不上 agent_service），
>    与 run 级终态错误（`reason_code`）分开：可恢复中断只在本次连接内重连，不改变
>    run 状态；run 级错误是终态。
> 4. **敏感数据例外（§10 口径）**：续跑必需的回合消息与工具结果可入库；system prompt、
>    完整模型请求与密钥不入库、不落日志。
> 5. **仅 Web 单通道**：不保留 Electron / 桌面壳双通道口径，前端只按浏览器 SSE 实现。
> 6. **Agent 通道错误码**：503（`AGENT_DISABLED` 未启用；网关转发失败时目前是
>    `detail='agent service unavailable'` **无机器码**，`AGENT_SERVICE_UNAVAILABLE`
>    为约定目标码，落地状态见 §16 C3）、401（未登录 / 凭据无效）、凭据库不可用
>    （目标码 `CREDENTIAL_STORE_UNAVAILABLE`）、404（对象不存在或非本人）、400
>    （参数 / 预算非法）、409（状态冲突，如待审批提案未处理时续跑）。前端按 `code`
>    映射文案，不解析中文；暂无机器码的 503 按文案兜底展示。
> 7. **`GET /agent/skills` 前端落点** = INT-2550（已交付），本轮不新增第二个技能列表入口。

审批单响应字段（§9.4.1 拆单）：`id` / `run_id` / `tool_call_id` / `status` / `proposal`（含 `object_count`）/ `diff` / `expires_at` / `decided_by` / `decided_at` / `batch_id` / `batch_index` / `batch_total` / `object_ref`；不新增端点。

## 12. 代码落位

### 12.1 后端

```text
agent_service/
├─ interfaces/api/routes.py
├─ interfaces/api/memory_routes.py   # 记忆元数据 / 提案审批 / break-glass（INT-2490）
├─ application/
│  ├─ run_orchestrator.py        # 唯一 Loop
│  ├─ skill_registry.py
│  ├─ context_assembler.py
│  ├─ tool_gateway.py
│  ├─ memory_service.py          # 检索 / 提案 / 落盘 / 审计（INT-2490）
│  ├─ approval_service.py
│  ├─ sandbox_runner.py
│  └─ sandbox_dispatch.py        # T1 工具调用 → 沙箱执行器接线 + 失败信号（INT-2495/INT-2532）
├─ domain/model/ + enums.py
├─ domain/services/context_window_resolver.py
├─ config/model_catalog.json        # 模型默认窗口/最大输出（配置化）
├─ config/memory_sensitive_rules.json   # 记忆敏感信息规则（block / redact）
└─ infrastructure/
   ├─ llm/openai_compatible.py
   ├─ llm/anthropic.py
   ├─ llm/provider_registry.py      # 用户供应商解析/默认选择
   ├─ llm/credential_store.py       # AES-GCM 加解密，禁止明文落盘
   ├─ skill/fs_skill_repository.py
   ├─ memory/file_memory_store.py   # 文件式记忆读写（INT-2490）
   ├─ memory/paths.py               # tenant/owner 路径构造与穿越拦截
   ├─ memory/rg_search.py           # rg --fixed-strings --json 检索
   ├─ memory/sensitive.py           # 敏感信息扫描
   ├─ tools/registry_bridge.py
   ├─ persistence/
   ├─ sandbox/docker_runner.py
   └─ observability/
skills/                          # 顶层只读挂载
shared/agent_tools/              # 工具 Schema 单一事实源（含 coverage.py → COVERAGE.md 归属矩阵）
tests/agent_eval/coverage/       # M1 汇总评测：清单一致性 / 长尾 / 触发 / 无编造（INT-2465）
```

- 端口注册到 `shared/config/service_ports.py`。
- `agent_service` 不直接 import 业务服务内部模块，只走 REST/gRPC 契约。
- 分层遵循 `interfaces → application → domain → infrastructure`，`domain` 零依赖。
- **部署与编排**：见 `docker/README.md` §8.1。agent_service 不发布宿主端口，只经网关
  入站（compose 网络 `agent_internal` / `agent_egress`）；总开关与灰度配置口径见 §13.1，
  运维步骤见 08 手册。

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
| `features/ai-chat` 审批批次展示 | 拆单后按「第 i/N 条 · 本批 N 条全部批准后才执行」展示批次与对象标识；DTO 补 `batch_id` / `batch_index` / `batch_total` / `object_ref`（§9.4.1） | INT-2571 后端落地的跟进卡（不阻塞后端） |
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
10. 网关 `POST /api/v1/reports/{report_id}/cases/search` 当前只有登录校验、无
    `require_permission`（INT-2547 P3-8 登记，非 M1 四卡引入）；Agent / MCP 侧仍有工具级
    权限门禁，但网关补 `report:read` 之前不得把该端点当作权限边界。

### 13.1 总开关与灰度（INT-2456 总闸 / INT-2478 灰度扩展）

1. **唯一总闸**：`AGENT_ENABLED`（默认 `false`）。启动期与运行期都取该名，不新增第二个
   开关名。关闭时 `/api/v1/agent/**` 的运行底座（sessions / runs / events / approvals /
   skills）、用户模型供应商接口与 Skill 管理接口一律 503 + `code=AGENT_DISABLED`，
   **不转发** agent_service，不产生后台 run；任务 / 用例 / 报告 / 设备等人工流程不走这些
   路由，完全不受影响。
2. **灰度扩展（不是第二套开关）**：总闸开启后可配两级白名单——
   `AGENT_GRAY_TENANTS`（租户 ID 列表）与 `AGENT_GRAY_USERS`（用户 ID 列表），逗号 /
   分号 / 空白分隔。判定在 `shared/agent_access.py`（枚举 `AgentAccessDecision`：
   `ENABLED` / `DISABLED` / `NOT_IN_GRAY`）：
   - 总闸关闭 → 拒绝（`DISABLED`）；
   - 总闸开启、两个白名单都为空 → **放行所有人**（默认值向后兼容，现役
     `AGENT_ENABLED=true` 的部署不会因缺灰度配置整体关闭）；
   - 配置了任白名单 → 租户命中 **或** 用户命中才放行，否则 `NOT_IN_GRAY`。
3. **未命中与关闭同一表现**：两者都返回 503 + `AGENT_DISABLED`（不新增第二个机器码，
   不在响应里区分灰度与总闸，避免探测灰度名单），不转发上游、不产生后台 run、不落
   用户身份的敏感日志（只记不带身份的 debug 级路径）。
4. **执行点只在网关**：agent_service 不发布宿主端口，网关是唯一外部入口；不在
   agent_service 再判一次（避免两处配置漂移）。agent_service 的启动恢复投递仍只看
   `AGENT_ENABLED`：把某用户移出灰名单不会追溯取消已存在的 run，需要停止就让用户或
   管理员显式取消。
5. **配置生效方式**：网关按调用时读环境变量（改配置不冻结在进程初始化），但容器 env
   是启动时快照，真实切换需按 `.env` 重启**目标容器**（`api_gateway`），不做全栈重复部署。
   `AGENT_ENABLED` / 灰名单的运维步骤见 08_Agent运维手册 §1。

## 14. 评测

| 层级 | 内容 | 门槛 |
|---|---|---|
| 端到端 | 跨域任务集，中央小组维护 | 任务成功率、无编造数值、权限不越界 |
| 单 Skill | 每 Skill ≥10 条 golden tasks | 触发准确率 ≥90%，工具选择正确，成本达标 |
| 压缩 | 50+ 轮长任务 | 压缩前后成功率差 ≤5%，事实召回率 ≥95% |
| 沙箱 | 逃逸/联网/资源超限用例 | 100% 拦截，无宿主访问 |
| 恢复 | 进程内重启模拟后继续 | 不重复写，状态一致 |

评测集入库，Skill 变更必须跑对应集合；失败阻断合并。

> **评测判定口径（INT-2609 P2-4 / P3-1 / P3-2 / P3-5 回写，2026-11-14）**：
>
> 1. **工具选择判定归 e2e 层**：门禁里「工具选择正确」按 **100% 派发口径**在端到端层
>    判定（实际调用工具 == 任务声明工具），单 Skill 层不单独设工具选择门槛；成本
>    只做**相对观测**（同数据集前后对比），**不设绝对成本门槛**。
> 2. **压缩轮次口径差**：实现侧压缩下限是 **50 轮**（长任务数据集），本页与 §15 的
>    「60 轮」是 M0 初版目标值（历史文案）。以 50 轮为实现门槛；若产品要求 60 轮，
>    属待补数据集项，**本卡不改代码**，在 §16 登记为待补。
> 3. **恢复层「kill Worker」是进程内重启模拟**：实现是同一进程内 `container.shutdown()`
>    后新建 container 重建状态，**不杀宿主进程**；对外表述统一写「进程内重启模拟」，
>    不写「kill Worker 进程」。
> 4. **事实召回率口径**：压缩后模型经工具**重查后答对也算召回**（事实没丢，只是需要
>    重查）；重查率单独统计（`requery_rate`），不与召回率合并成一个数。
> 5. 确定性复现要求：评测报告含 `started_at` / 耗时等非确定字段，**不可字节比对**；
>    CI / 回归按 `metrics` 逐项比对（见 §14.1 P3-9）。

> **实现口径（INT-2465 / INT-2554，2026-11-13）**：M1 汇总评测在
> `tests/agent_eval/coverage/`（离线、不连外部服务）：
>
> - 清单一致性：31 个意图工具在注册表 / Skill `allowed-tools` / `tool_search` 索引三处
>   一致，`tools/list` 快照 207 项，`COVERAGE.md` 与 `coverage.py` 同源
>   （`python -m shared.agent_tools.coverage --check`）；
> - 长尾检索：20 个关键词全命中（18 条排第 1、19 条进前 3）；
> - Skill 触发：12 个 M1 Skill 120/120，`platform-reference` 10/10 回归；
> - 无编造数值：30/30（确定性模型 + 确定性工具替身，答案必须与工具返回逐字段相等）；
> - 真实网关契约用例需 `AGENT_LIVE_GATEWAY=http://localhost:15000`，默认跳过。
>
> **触发评测是确定性词面代理**：只读 Skill L1 `description` 的「触发词：」段 + 本域词汇表
> 做词面打分，**不调用真实模型**。真实模型级触发准确率需要用户供应商 Key / 计费通道，
> 归 M3 全量评测卡 INT-2475；代理结论不等同于模型实测。

### 14.1 评测门禁落地（INT-2475，2026-11-14）

五层评测集入库 + 一条命令 + 非 0 退出码即门禁（仓库当前无 CI 配置，先落「脚本 +
文档 + 退出码」，接外部 CI 另行立项）。实现：`tests/agent_eval/gate.py`（层与阈值）、
`scripts/run_agent_eval.py`（入口）、`tests/agent_eval/README.md`（用法与口径）。

| 层 | 评测集 | 门槛 | 失败集合名 |
|---|---|---|---|
| 端到端 | `datasets/e2e_cross_domain.json`（清单）→ `golden_tasks.json`（10）+ `no_fabrication_tasks.json`（30） | 成功率 ≥95%、编造 0、越权 0 | `e2e:<dataset>` / `e2e:success_rate` / `e2e:permission_boundary` |
| 单 Skill | `coverage/datasets/skill_trigger_tasks.json`（14 Skill × ≥10） | 每条 ≥10、触发准确率 ≥90%、L1 描述可追溯 | `skill:<name>` |
| 压缩 | `datasets/long_task.json`（68 轮，关/开各跑一遍） | 成功率差 ≤5 点、事实召回 ≥95%、观察到压缩 | `compaction:long_task` |
| 沙箱 | `tests/agent_sandbox/`（T1 默认，T2 按宿主 runsc 可选） | 100% 拦截、无跳过、无遗留容器 | `sandbox:<tier>` |
| 恢复 | `tests/agent_eval/auto/`（kill Worker / 暂停继续） | 用例全过且「不重复写」用例在场 | `recovery:kill_worker` |

- **入口**：`python scripts/run_agent_eval.py`。产物 `<out>/report.json`（层结果 /
  失败集合 / 数据集版本 / 成本 / exit_code）与 `<out>/report.md`。
- **退出码**：0 全通过；1 有层未通过；2 基础设施不可用（Docker / 镜像 / runsc /
  评测集缺失），与「用例失败」区分。
- **Skill 变更门禁**：`--changed-skills auto --base-ref <ref>` 按 `git diff`（含工作区
  未提交改动）判定变更 Skill，只跑对应集合；失败项精确到 `skill:<name>`，即「故意改坏
  一个 Skill，门禁失败并指出具体集合」。门禁同时校验代理词汇表能在 L1 描述里找到依据，
  改坏正文不会被词表兜底掩盖。
- **版本化**：评测集全部入库并带整数 `version`，缺失即按基础设施错误退出；端到端任务集
  由 `datasets/e2e_cross_domain.json` 清单登记，新增域只加成员 + version，不改评测代码。
- **成本可观测**：每层墙钟耗时 + 模型轮次 / 工具调用 / 输入字符（近似 token = chars/4）。
  确定性替身不产生真实计费，用于**相对**成本回归。
- **口径边界**：Skill 触发仍是确定性词面代理（`trigger_proxy: true`），**不是模型实测**；
  模型级触发 / 工具选择准确率需要用户供应商 Key，本门禁未覆盖，报告与文档均按代理口径
  表述，不冒充模型结论。`runner.py` 的「工具选择正确率」是 Loop 派发口径（实际调用工具
  == 任务声明工具）。
- **沙箱层级**：默认 T1；T2 需宿主 Docker 已注册 gVisor `runsc`，缺失时门禁按
  `unavailable`（exit 2）上报，不静默降级。`--sandbox-tier none` 仅在无 Docker 的
  本地排障时使用，不作为合并门禁证据。

> **门禁落地补充（INT-2609 P3-8 / P3-9 回写，2026-11-14）**：
>
> - **一次性容器产物路径是 `/out`**（不是 `/app/eval-out`）：`docker-compose.eval.yml`
>   的容器入口把报告落到 `/out/report.json` / `/out/report.md`，宿主持久化时挂载该目录；
>   文档与排障命令按 `/out` 写。层子集入口显式放行（`AGENT_EVAL_ALLOW_SKIP=1`）时
>   缺层写 `layers_missing`、选中不跑写 `layers_skipped`，两者都不是通过。
> - **`--changed-skills auto` 仅宿主 worktree 可用**：它按 `git diff` 判定变更 Skill，
>   容器内没有 git 工作区/基线，容器内跑必须显式给 Skill 名子集，否则按基础设施错误退出。
> - **报告不可字节比对**：`report.json` 含 `started_at`、各层耗时等非确定字段；CI 与
>   跨版本回归按 `metrics`（成功率、召回率、成本相对值、失败集合）比对，不比整文件字节。

## 15. 里程碑与验收

| 阶段 | 交付 | 验收 |
|---|---|---|
| M0 底座 | 单 loop、SkillRegistry、意图工具 **4 个（3 业务 + `tool_search`）**、SSE 回放、Run 持久化；用户供应商密钥库（加密/掩码/无 Key 失败）；沙箱 T1 + T2（首期启用）；压缩 L1–L3；`platform-reference` | T1/T2 逃逸测试全拦截；50 轮压缩任务不丢事实（原写「60 轮」，实现下限 50 轮，见 §14 口径）；进程内重启模拟可恢复；无 Key 时明确失败且不回退平台 Key；10 条 golden tasks 通过 |
| M1 只读全平台 | 11 域只读意图工具；**§4.3 除 `app-api-onboarding` 外的 12 个** Skill 的 L1/L2；`tool_search` 轻量语义扩展（中文 bigram / 词表扩展，无向量，INT-2465；关键词检索 M0 已交付）；文件式长期记忆（`rg` 检索，无向量库） | 每域 10 条任务；Skill 触发准确率 ≥90%（当前为确定性词面代理，模型实测归 INT-2475）；无编造数值；记忆写入需审批 |
| M2 写操作与报告 | 探索-生成层（`ui_tree`/`ui_action`/`api_spec`）；写工具、审批、幂等；App/API 接入全流程（受理→发现→计划→生成→验证→迭代→交付）；驱动提案（设备驱动 + API 适配器，提案 + T2 验证，不自动发布）；Report Studio 取数→起草→版本→导出；**用户自定义 Skill（USER 级 CRUD + zip 导入导出 + 逐项校验 + 版本快照 + 触发门槛）+ Skill 管理页**；前端审批卡与时间线 | 提案→审批→执行可重放；重复执行无副作用；两类提案均可复现且未审批不写注册表；接入包在 staging 冒烟通过；三类报告指标与 Report Service 逐字段一致；自定义 Skill 不得提权、不得越权引用工具、同名不得覆盖内置、历史 run 按版本回放 |
| M3 自动化与评测 | Auto 模式、预算/熔断、全量评测；**TENANT 级共享 Skill 与发布审核流**；外部 Skill zip/MCP 对齐、文档更新；**总开关灰度（租户 / 用户白名单，INT-2478）** | 端到端成功率与成本达标；Agent 关闭不影响原系统；外部 Agent 能力清单一致；**总闸关闭 / 灰度未命中与总闸关闭同一表现（`AGENT_DISABLED`，无后台 run）**；灰名单用户可用、非灰名单不可用；M0–M3 文档与实现对齐（07 / 08 / 09 回写完成） |

> **M3 门判定（2026-11-15）**：M3 五卡（INT-2474 / 2475 / 2476 / 2477 / INT-2551 经
> INT-2587）全部合入 `V10.11.2`，一致性审计无未处置 P0/P1，部署面就绪；本卡（INT-2478）
> 完成文档回写 + 灰度开关后，M3 里程碑收口。M0–M2 的验收结论见各阶段审计卡与 §16
> 「已登记残留」。

## 16. 风险与开放问题

| 风险 | 应对 |
|---|---|
| 207 个工具注入导致选择退化 | 意图工具 ≤30 + tool search；Skill 限定工具集 |
| 模型能力不足导致计划漂移 | scratchpad + 确定性校验 + 审批 + 预算 |
| 压缩丢关键事实 | 永不压缩清单；事实带来源 ID，可重查 |
| 沙箱逃逸 | 三层隔离 + 逃逸用例纳入 CI |
| 写操作重复执行 | 幂等键 + 恢复前查副作用 |
| Skill 泛滥 | 一个 Skill 一件事；Owner + 版本 + eval；中央小组把关 |
| 外部与内部能力漂移 | 工具 Schema 单一事实源；清单一致性测试 |

### 已登记残留（INT-2554 收口审计，2026-11-13）

**P2（已开卡）**

| 项 | 位置 | 状态 |
|---|---|---|
| 记忆工具未接入 Skill allowlist：`platform-reference` 正文指示 `memory_search` / `memory_write`，`allowed-tools` 却没声明（激活 Skill 时返回 `SKILL_TOOL_DENIED`）；两卡合入后清单一致性用例的白名单也要同步 `memory_search` | `skills/platform-reference/SKILL.md:11-13`、`:163-165`；`tests/agent_eval/coverage/test_registry_consistency.py:113` | 缺陷卡 **INT-2556** → 开发工程师A |

**P3（INT-2547 八条，随本页登记、不阻塞 M1 门）**

| # | 残留 | 位置 | 处置 |
|---|---|---|---|
| R1 | 代码注释仍写「205 个 MCP 工具」 | `shared/agent_tools/__init__.py:4`、`device_tools.py:9`、`intent_tools.py:20/:1074`、`search.py:4`、`testcase_tools.py:11` | 属索引视图口径（§6.1 裁定 4），对外仍以 §6.2 的 207 为准；注释随 M2 统一改 |
| R2 | ~~`driver-proposal` Skill 称调用 `driver_propose` 返回 `TOOL_NOT_ENABLED`~~ | `skills/driver-proposal/SKILL.md` | **已修（INT-2467）**：Skill 改为「审批前返回 `APPROVAL_REQUIRED`」，工具已启用 |
| R3 | `tag-group` Skill 称 `group_list` 可分页 | `skills/tag-group/SKILL.md:55,63` | `group_list` 的 MCP Schema 无 `page` / `per_page`，按 Schema 调用；文案随 M2 修 |
| R4 | `testcase_generate` 只声明 `testcase:read`，实际还依赖 audio / algorithm / evaluation / playback / group 只读权限 | `shared/agent_tools/intent_tools.py:756` | 工具描述补依赖权限（M2） |
| R5 | 工具层聚合上限是代码常量 | `intent_tools.py:273`、`testcase_tools.py:119`、`diagnostics.py:27-30` | 见 §5.3；配置化（M2） |
| R6 | `testcase_generate` 与创建服务是第二份推导实现 | `testcase_tools.py:204-234` vs `audio_service/application/services/_creation_annotation_mixin.py:174-204` | 补一致性回归或抽共享纯函数（后续卡） |
| R7 | `testcase_query.export_status` 声明 `testcase:read`，端点要 `testcase:import_export` | `shared/agent_tools/intent_tools.py` | 权限码对齐（M2） |
| R8 | 网关 `POST /reports/{id}/cases/search` 无 `require_permission` | `api_gateway/routes/report_bp.py:181` | 补 `report:read`（见 §13 第 10 条） |

### 已登记残留（INT-2597 一致性审计，2026-11-14）

审计对象：设备 UI 网关三端点（INT-2578 交付提交 `f328f2bf2`，已合入 `V10.11.2`）。§6.6「服务端
通道」为本次回写的契约事实；以下为不阻塞的 P3 残留，均由 INT-2579（agent 适配器）或后续卡收口。

| # | 残留 | 位置 | 处置 |
|---|---|---|---|
| S1 | 请求体校验失败（缺 `action_type` / 类型错 / 截图 `label` 超长）复用 `ACTION_NOT_ALLOWED`，`UiCaptureErrorCode` 无独立「参数非法」码；截图参数错也报动作类码，消费方按 `code` 分支时语义偏斜 | `api_gateway/application/services/device/device_ui_service.py:117-137` | 如需精确分支，回评审新增 `INVALID_ARGUMENT` 或改用框架 422；当前 400 满足卡面 |
| S2 | 动作请求体校验失败不写设备审计（七枚举拦截与设备侧失败都写），与卡面「每次动作写一条审计」的字面口径有差；该路径未下发设备动作 | `api_gateway/application/services/device/device_ui_service.py:131-137` | 统一审计口径时一并收口 |
| S3 | `CaptureUiScreenshot.label` 只透传到 gRPC：device_service 未消费（不进对象键、也未写日志 / 回放定位），与 proto 字段注释不一致 | `device_service/interfaces/grpc/device_ui_servicers.py:192-195` | 卡 1（INT-2577）遗留，按需补日志或改注释 |
| S4 | `CommandResultDTO.code` 由 `int` 放宽为 `int \| str`，同一 DTO 承载 HTTP 数字码与设备 UI 字符串业务码 | `api_gateway/domain/dto/api_gateway_acl_dto.py:293-295` | 类型折中，注释已写明；新码只有设备 UI 三条路径产生 |
| S5 | `doc/接口文档/04_测试设备管理.md` / `doc/接口实现文档/04_测试设备管理-接口实现文档.md` 未收录 `ui/*` 三端点 | `doc/接口文档/04_测试设备管理.md`、`doc/接口实现文档/04_测试设备管理-接口实现文档.md` | 契约以 §6.6 / §11 为准；接口参考文档随文档批次补齐 |

### 已登记残留（INT-2477 审计，2026-11-14）

审计对象：Auto 模式前端（预算 / 进度 / 中断 / 审批，`8bd4a32fd`）。以下 P3 均不阻塞
M3 门，登记在此、由后续前端卡收口：

| # | 残留 | 位置 | 处置 |
|---|---|---|---|
| A1 | 快照轮询到 `WAITING_APPROVAL` 时未触发 `refreshApprovals`，暂停恢复后审批卡可能不刷新 | `frontend-react/src/application/agent/agent-run-store.ts:648-649` | 轮询进入 `WAITING_APPROVAL` 时补一次审批刷新（后续前端卡） |
| A2 | `runInput.mode` 用字面量 `'auto'` / `'chat'`，未走枚举常量 | `agent-run-store.ts:1178` | 收敛到域枚举（类型层面修正） |
| A3 | `AGENT_AUTO_COPY.pausePolicy` / `restoreHint` 无引用，开跑前不展示暂停规则 | `frontend-react/src/**/agent-auto-copy.ts` | 开跑前展示暂停规则，或删掉未用文案 |
| A4 | `auto-progress.ts` 暂停文案写「阈值」，未用实际 `pause.consecutive_failures` | `frontend-react/src/**/auto-progress.ts` | 文案改用事件下发的实际阈值 |

### 已登记残留（INT-2609 / INT-2610 / INT-2621 文档批，2026-11-15）

| # | 残留 | 位置 | 处置 |
|---|---|---|---|
| B1 | 压缩数据集 50 轮与初版 60 轮目标差 | `tests/agent_eval/datasets/long_task.json`（68 轮数据集，实现门槛 50） | 若要 60 轮验收需补轮次阶段的数据集与用例，**本卡不改代码**，待测试/评测卡评估 |
| B2 | `mcp.json（同目录）` 旧文案 | `api_gateway/skill_templates/SKILL.md` | **已修**（本卡）：改为 `assets/mcp.json` |
| B3 | 使用说明按旧包结构写 | `doc/功能设计文档/00_新功能总览/联接你的Agent（Access Token 与 skill·MCP）使用说明.md` §3.1 / §4.1 | **已修**（本卡）：`assets/mcp.json`、正文按 `skills/platform-reference/` 生成、base_url 默认值口径 |
| B4 | `agent_bp.py` 下载 docstring 仍写 `SKILL.md + mcp.json` | `api_gateway/routes/agent_bp.py:44` | **已修**（本卡）：`assets/mcp.json` |
| B5 | 09 权限码表述 | `doc/agent化/09_外部Agent能力清单.md` §2 | **已修**（本卡）：`资源:操作`，可多级 |
| B6 | 09 缺 USER Skill 文档型说明 | 09 §1 | **已修**（本卡）：USER Skill 是文档型 Skill，`allowed-tools` / `permissions` 为空，不参与内部工具收敛 |
| B7 | 「自定义包 → 平台层」方向 N/A 依据 | 09 §1 / §4.4 | **已写进文档**：PLATFORM 层只读 fs 扫描 `skills/`，无写入口 |
| B8 | 算法域文本 | `docs/RBAC权限划分.md` §3.10、`shared/agent_tools/contract.py` | **已修**（本卡）：`algorithm:read` 补全只读端点；状态 source 标注 `online/offline/draft → ACTIVE/DEPRECATED/DRAFT` |
| B9 | 评估子维度描述与实现相反 | `skills/evaluation-config/SKILL.md` §硬规则 6 | **已修**（本卡）：子维度不单独发请求，但与主维度同批计算、各有输出字段与评分记录 |
| B10 | 上下文快照 / 预算枚举口径 | 07 §5.3 + `context_assembler.py` / `context_budget.py` 注释 | **已修**（本卡）：见 §5.3 回写 |
| B11 | `resolve_rest_call` docstring 缺音频 / 算法 | `shared/agent_tools/intent_tools.py:2181` | **已落地**（核实已含 `audio_query` / `algorithm_query`，无需改） |
| B12 | 设备 UI 三端点未收录接口文档 | `doc/接口文档/04_测试设备管理.md`、`doc/接口实现文档/04_测试设备管理-接口实现文档.md` | **已修**（本卡）：补 `ui/tree` / `ui/screenshot` / `ui/action` |

### M0–M2 历史审计回写核对（INT-2478，2026-11-15）

逐条核对各审计卡原文（结论均为「有条件通过」），落地位置如下：

| 来源 | 条目 | 落地 / 处置 |
|---|---|---|
| INT-2505 | P2-a 01/02 旧驱动工具名（`receive_picked_elements` / `generate_driver_from_elements` / `publish_driver_proposal`） | 01 / 02 已加「实现演进裁定」注记：对外唯一名 `driver_propose`，两个名字只是内部步骤；04 已标作废 |
| INT-2505 | P2-b 04 的 Electron 双通道 | 04 已标作废；07 §11-5 定仅 Web 单通道 |
| INT-2505 | P2-c §15 Skill 数措辞 | **已修**：§15 M1 改为「§4.3 除 `app-api-onboarding` 外的 12 个」 |
| INT-2505 | P2-d `dashboard_query` 权限码 `dashboard:read`（网关实为 `home:read`） | 登记 §16 D1（工具当前 `enabled=false`，启用时改码，属工具实现不在本卡范围） |
| INT-2505 | P2-e §11 审批决策端点 | **已落地**：M2 INT-2466 已实现 `POST /agent/approvals/{id}/decision`（`agent_service/interfaces/api/routes.py`） |
| INT-2505 | P2-f §15 M0 工具数 3 → 4 | **已修**：M0 行改为「4 个（3 业务 + `tool_search`）」 |
| INT-2504 | P2-1 生产 fail-fast 依赖 `LOG_ENVIRONMENT=prod`，compose 默认仍是 `dev` | 登记 §16 D2：`docker/.env.compose.example` 已注明生产必须设 `prod`；现网部署清单随下次部署卡显式设置 |
| INT-2504 | P2-3 §10 缺 `api_key_mask` 字段 | **已修**：§10 `agent_llm_provider` 补 `api_key_mask` |
| INT-2502 | P2-4 `/api/v1/trash` 前缀不存在 | **已修（INT-2501）**：`shared/agent_tools/contract.py` 已无该前缀；`mcp_registry` 的 `favorites / trash` 只是域描述 |
| INT-2476 | 09 工具 31 / 207 / 14 口径 | **已核对一致**，本次未改数字（09 §9.1 复述） |
| INT-2517 | D1–D7 | 已回写 §11 的「SSE 与信封口径」段（三种信封 / 游标 / error 帧 / 单通道 / 错误码 / skills 落点） |
| INT-2522 | D1–D6 / P2-1~P2-3 | 已回写 §13.1、§12.1、§16 C1–C5、08 手册 §2/§4 |
| INT-2523 / 2525 | 音频 / 算法域口径 | 已回写 §6.1 注、§6.2 参数口径、`docs/RBAC权限划分.md` §3.10、`contract.py` 状态标注 |
| INT-2524 | 评估子维度「不独立算分」表述 | **已修**：`skills/evaluation-config/SKILL.md` 硬规则 6 |
| INT-2532 | 沙箱接线 / 原因码映射 / 终态事件 | 已回写 §7 映射表、§9.3、§12.1 |
| INT-2536 | ArtifactKind / dropped_ids / keep_recent_turns / SCRATCHPAD / 召回率 | 已回写 §5.3 注、§14-4、`context_assembler.py` / `context_budget.py` 注释 |
| INT-2544 | 配置路径 `agent_service/config/config.py` | 已核对一致（见本节 C 段末） |
| INT-2556 | D-ALWAYS（记忆工具实际可调用） | 已订正 §4.3 |
| INT-2551 | TENANT 隔离 / 不得自审 / 审批链 / 门槛不可绕过 | 已回写 §4.4 注 |
| INT-2597 | S5 设备 UI 三端点接口文档 | **已修**：两份设备接口文档补 `ui/tree` / `ui/screenshot` / `ui/action` |

### 已登记残留（INT-2522 部署 / 可观测批，2026-11-15 核对）

| # | 残留 | 位置 | 处置 |
|---|---|---|---|
| C1 | T2 可见性两套口径（`AGENT_T2_RUNTIME` vs `AGENT_SANDBOX_T2_RUNTIME_NAME`） | `agent_service/config/config.py`、`docker/README.md` §8.1 | 08 手册 §2.4 写明两者必须一致；不一致按 `T2_RUNTIME_UNAVAILABLE` 失败，不降级 |
| C2 | healthcheck 只看 HTTP 200（agent_service `/health` 已校验 DB/Redis，但 compose 只判 200） | `docker/docker-compose.yml` agent_service 段 | 非门禁阻断项；判活以 `/health` 语义 + Agent 接口实际可用性为准 |
| C3 | 网关转发失败 503 无机器码 | `api_gateway/routes/agent_runtime_bp.py:110` | 目标码 `AGENT_SERVICE_UNAVAILABLE`；补码属 api_gateway 行为变更，登记待后续卡，不阻塞 M3 |
| C4 | Redis 降级时健康检查 200 | 部署面 | 明确为非门禁项：Redis 降级不影响已建会话读取与业务接口，只影响事件推送时序；不以 200 反推 Agent 可用 |
| C5 | 生产部署清单需显式列 `AGENT_CREDENTIAL_MASTER_KEY` 为必填 | `docker/README.md` §8.1、08 手册 §2.1 | 08 手册 §2.1 已写明「生产必填，缺失拒绝启动」；compose 部署清单随下次部署卡同步 |
| D1 | `dashboard_query` 权限码 `dashboard:read` 不存在（网关实际 `home:read`） | `shared/agent_tools/intent_tools.py` | 工具当前 `enabled=false` 不触发；启用前改为 `home:read`（属工具实现，登记不本卡改） |
| D2 | 生产 fail-fast 依赖 `LOG_ENVIRONMENT=prod`，compose 默认 `dev` | `docker/docker-compose.yml` agent_service 段 | 现网缺该值时主密钥缺失不会在启动期暴露（运行期仍 fail-closed）；下次部署卡显式设置并补启动校验用例 |

**关于 INT-2522 D4 / D5**：`AGENT_TOOL_GATEWAY_BASE_URL` 已在
`docker/.env.compose.example` 列入（注释示例）；部署 / 配置口径见本方案 §12.1 的
「部署与编排」条与 `docker/README.md` §8.1。**INT-2544**：配置真身是
`agent_service/config/config.py`（不是 `agent_service/config.py`），本方案与代码一致。

### 开放问题落地位置（5 条，均已于 2026-11-12 拍板）

| # | 结论 | 正文落点 |
|---|---|---|
| 1 | 默认模型与供应商：用户自带 Key，AES-256-GCM 加密存库，平台默认无 Key（`AGENT_ALLOW_PLATFORM_KEY=false`），协议支持 OpenAI 兼容 + Anthropic | §6.4、§13-7/8；08 手册 §2 |
| 2 | T2 沙箱首期启用（gVisor / Firecracker，禁网、无宿主挂载、无凭证） | §7、§14；08 手册 §2 / §4 |
| 3 | Auto 审批粒度与预算：WRITE 计划级批量、DESTRUCTIVE 单条，预算按有效窗口 W | §9.4、§9.4.1；08 手册 §3 |
| 4 | 长期记忆：文件式 + `rg/grep` + Skill references，不引入向量 RAG | §8.6 / §8.6.1；08 手册 §2 |
| 5 | 上下文窗口：模型目录默认 + 用户可覆盖（8k–2M，1024 对齐），有效窗口 = 覆盖 → 默认 → 128k | §8.3、§9.4 预算表；08 手册 §2 / §3 |

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

## 18. 方案与实现差异台账（M3 收口，2026-11-15）

本方案从 M0 到 M3 与早期文档（00 / 04 的 DeepSeek Harness 路线、05 的 DSH 报告路线）
存在实现演进差异。下表是**最终口径**，后续按「以本表 + 各节「实现口径」注为准」执行，
不再回到早期文档的实现方式：

| # | 早期方案口径 | 最终实现口径 | 依据 / 落点 |
|---|---|---|---|
| 1 | 集成 DeepSeek Harness（DSH Plugins + Bridge） | **自研单 Agent Loop + Skills**（无 DSH 依赖） | 01 / 02 / 03 / 04 的 DSH 章节作废，见各文档头部标记；本方案 §5 |
| 2 | 浏览器 + Electron 双通道 | **仅 Web 单通道**（浏览器 SSE） | §11-5、§12.2 |
| 3 | 跨域工具没有归属 Skill、激活 Skill 后被拒 | `memory_search` / `memory_write` 属 `ALWAYS_AVAILABLE_TOOLS`，激活任意 Skill 均可调用；只有 `dashboard_query` 仅通用会话可用 | §4.3 INT-2556 订正 |
| 4 | 工具索引 205 与对外 207 混用 | 对外 `tools/list` **207**；`tool_search` 索引视图 **205 条 MCP + 30 条意图 = 235** | §6.1 裁定 4、§6.2 |
| 5 | 压缩验收「60 轮」 | 实现下限 **50 轮**（数据集 68 轮，门禁按 50 判定）；60 轮为待补目标 | §14、§15、§16 B1 |
| 6 | 恢复层「kill Worker」 | **进程内重启模拟**：同进程 `container.shutdown()` + 新建 container | §14-3 |
| 7 | T2 首期不执行 / 或可回落 T1 | T2 首期启用，运行时缺失 → `T2_RUNTIME_UNAVAILABLE`，**绝不回落 T1**；通用 Loop 仍未接 T2 | §7、§14.1 |
| 8 | Auto 计划级批量审批 WRITE | Auto 下 WRITE 仍逐次提案 + 审批；DESTRUCTIVE 恒单条不预授权 | §9.4 边界 |
| 9 | 一次 tool call 一张审批单 | **>20 对象拆单**（`batch_id` / `batch_index` / `batch_total`），全批准才执行 | §9.4.1 |
| 10 | 评测一次性容器产物落 `/app/eval-out` | 落 **`/out`**（compose 挂载该目录） | §14.1 |
| 11 | 触发准确率用真实模型评测 | M1–M3 门禁为**确定性词面代理**；模型级评测需用户供应商 Key，未覆盖 | §14、§14.1 |
| 12 | 评测报告可字节回归 | `report.json` 含 `started_at` / 耗时，**按 metrics 比对** | §14.1 P3-9 |
| 13 | 总开关只有 `AGENT_ENABLED` | 唯一总闸仍是 `AGENT_ENABLED`，**在其上加租户 / 用户灰度白名单**（`AGENT_GRAY_TENANTS` / `AGENT_GRAY_USERS`）；未配白名单 = 全员放行 | §13-1、§13 灰度段、08 手册 §1 |
| 14 | 外部 Skill 包含根目录 `mcp.json` | **`assets/mcp.json`**；正文按 `skills/platform-reference/` 生成 | 09 §1、使用说明 §3.1 / §4.1 |

> 「最终口径」= 上述 14 条 + 各节标注「实现口径 / 审计回写」的注。任何与早期文档冲突的
> 表述，以本方案正文与本表为准；早期文档只作演进记录，不得据此实施。
