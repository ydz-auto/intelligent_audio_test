# 联接你的 Agent：Access Token 与 skill / MCP 使用说明

> 版本：v1.1（使用说明版 · 2026-10-22 入口位置口径同步）
> 日期：2026-10-22
> 归属：V9.7.31 · INT-1140「Access Token + 智能音频测试 skill / MCP（联接你的 agent）」
> 类型：使用说明（面向外部 agent 接入本平台能力）

## 1. 文档说明

### 1.1 目标与定位

本说明面向希望让**外部 agent（Claude Code / Codex 等）直接调用智能语音测试平台能力**的用户与团队。平台提供三类素材，均围绕同一套「Access Token」鉴权：

| 素材 | 作用 | 使用方 |
| --- | --- | --- |
| **Access Token** | 外部 agent 调用平台接口时的鉴权凭据（`at_` 开头明文 token） | skill 与 MCP 通用 |
| **skill 包** | 可下载、可安装到外部 agent 的技能包（SKILL.md + MCP 配置模板），内含能力清单与 curl 调用示例 | Claude Code / Codex 等 CLI agent |
| **MCP 端点** | 平台网关提供的 MCP 协议端点（JSON-RPC 2.0，`initialize` / `tools/list` / `tools/call`），外部 MCP 客户端连入即可调用平台能力 | MCP 客户端（Claude Desktop 等） |

> **方向说明**：本能力是让**外部 agent 反向调用平台**（经 skill / MCP + access token），与前端「灵犀Agent」演示（前端直连用户自配外部 LLM provider 的对话式 AI）方向相反、互不替代、不共用实现。

### 1.2 能力覆盖与「除外」边界

- **覆盖（经 skill / MCP 暴露）**：task / case / audio / device / evaluation / report / algorithm / tag / group 业务接口；`:share` 数据可见性分享点；data-transfer（task 导出 / 导入）；favorites / trash（收藏 / 回收站，INT-141）；benchmarks；report-studio（对话式报告工作台）。
- **除外（不暴露）**：auth users / roles / permissions / oauth-providers（系统设置）、auth me / self / change-password / OAuth 绑定（个人信息）、option（系统设置）、system health / status。
- **待负责人验收核对**：logs 域只读（`log:read`）倾向覆盖、`log:manage` / `log:websocket` 倾向除外；SSE `/api/v1/sse` 倾向除外（长连接推送）。
- scopes 目录从 `scripts/migrations/202608/seed_rbac.py` 130 权限点中挑「业务可暴露子集」生成，前端个人配置页按目录勾选。

### 1.3 契约来源与实现状态

| 环节 | 实施卡 | 状态（2026-10-22） |
| --- | --- | --- |
| auth_service Access Token 领域（表 / CRUD / 校验 RPC） | INT-1148（BE1） | ✅ done（已合入开发基线） |
| api_gateway 鉴权扩展 + access-token CRUD 路由 | INT-1149（BE2） | ✅ done |
| skill 下载 + MCP 适配端点（网关内） | INT-1150（BE3） | ✅ done |
| 旧 Vue 前端（左侧栏「连接你的 agent」入口 / 入口页面 / 个人配置页 token 管理） | INT-1151 | ✅ done |
| 本文档 | INT-1152 | ✅ done |
| React 前端（灵犀Agent 页 /ai-chat 右上角 + Agent 工作台浮窗头行右上角入口 / 入口页面 / 个人配置页 token 管理） | INT-1153 | ✅ done |
| 新 Vue 前端（入口 + 入口页面） | INT-1154 | ✅ done（入口位置 2026-10-22 裁定返工中：顶栏 TopBarRight 移除，改放灵犀Agent 页 /ai-chat 右上角 + Agent 工作台浮窗头行右上角，经 INT-701 派发实施） |
| 新 Vue 前端（个人配置页 token 管理） | INT-1155 | ✅ done |
| 缺陷修复（access_tokens 列表过滤软删行） | INT-1182 | ✅ done |
| 本文档（入口位置口径同步） | INT-1188 | 本卡 |

本文档正文按 **INT-1140 规格 + INT-1142 可行性评审已裁定契约**编写；与实现出入处见 §5 实现演进裁定记录。

---

## 2. Access Token 使用说明

### 2.1 什么是 Access Token

Access Token 是平台为外部 agent / skill / MCP 调用能力接口签发的长期访问凭据：

- **格式**：`at_` + 32 位十六进制（≈128 bit 随机熵），如 `at_9f2c…`。
- **明文仅一次**：明文只在**创建时显示一次**，关闭 / 刷新后不可再查看；库中**只存 SHA-256 哈希**，任何列表 / 详情接口都不回明文与哈希。
- **通用**：同一 token 同时用于 skill（curl 调用）与 MCP 连接，两边通用。
- **可配置**：权限 scopes 与有效时间均可配置；可随时启停 / 删除。

### 2.2 创建 Access Token（个人配置页）

入口：**个人配置页 → Access Token 管理区块 → 创建**（token 的创建 / 复制 / 管理在个人配置页，不在「连接你的 agent」入口页面内）。

创建表单：

| 字段 | 说明 |
| --- | --- |
| **名称** | 必填，≤ 100 字符，用于列表展示区分 |
| **权限 scopes** | 可选；按「业务可暴露子集」目录勾选 RBAC 权限码；**不勾选 = 继承用户当前全部权限** |
| **有效时间** | 三选一：缺省 = 平台默认有效期（30 天）；`0` = 永不过期；或填显式过期时间（ISO 格式） |

创建成功后在响应中**只显示一次明文 token**，请立即复制保存。列表页只显示掩码（末 4 位 `token_hint`）。

### 2.3 权限 scopes

- token 的**生效权限 = 用户当前权限 ∩ token scopes**：网关每次请求实时拉取用户当前权限再取交集，不使用 JWT 内嵌权限快照（用户权限被实时收回即从生效集消失）。
- 勾选 scopes 后，越权请求返回 403；不勾选（继承全部）时，权限与用户当前权限一致。
- scopes 必须使用现有 RBAC 权限码（seed_rbac.py 130 权限点中的业务可暴露子集）；非法权限码创建时报错。

### 2.4 有效时间

- 过期后 token 校验失败（401 语义）。
- 创建时缺省默认有效期 **30 天**（平台配置 `ACCESS_TOKEN_DEFAULT_EXPIRY_DAYS`，可调）。
- 支持配置为**永不过期**（`0`）。

### 2.5 启停 / 删除

- **启停**：可随时在 `enabled ⇄ disabled` 间切换；禁用后立即失效（401），重新启用即恢复。
- **删除**：**软删除**（置 `deleted_at`，行保留供审计）；删除后不可恢复，token 立即失效。
- **每用户上限**：默认 **20 个**（平台配置 `ACCESS_TOKEN_MAX_PER_USER`，0 = 不限制）；达到上限后需**删除旧 token 再创建**——上限按「未软删 token 数」计（含已停用），**停用不释放配额**。

### 2.6 安全口径

| 口径 | 说明 |
| --- | --- |
| 只存哈希 | 库中仅 SHA-256 哈希 + 末 4 位 `token_hint`，无明文落库 |
| 掩码展示 | 列表 / 详情仅返回 `token_hint` |
| 明文仅一次 | 创建响应返回 `data.token`，之后任何接口均不再出现 |
| 软删 + status | 删除置 `deleted_at` 保留审计（对齐本平台收藏 / 回收站语义，非 new-api 硬删） |
| 使用建议 | token 权限与个人账号等价或收窄，请妥善保管，勿写入公共仓库 / 日志 / 聊天记录 |

### 2.7 接口契约

网关对外路径（转发 auth_service；鉴权 = 当前登录用户本人，对齐 `/auth/self` 语义，不需额外权限码）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/auth/access-tokens` | 创建；响应 `data.token` 为明文，仅此一次 |
| GET | `/api/v1/auth/access-tokens` | 列表（掩码，`data.total` + `data.items`） |
| GET | `/api/v1/auth/access-tokens/{id}` | 详情（掩码） |
| PATCH | `/api/v1/auth/access-tokens/{id}` | 更新 name / scopes / status / expires_at；字段缺省 = 不修改；scopes 空列表 = 清空继承全部 |
| DELETE | `/api/v1/auth/access-tokens/{id}` | 软删除 |

调用平台能力接口时，外部请求使用 `Authorization: Bearer <明文 token>`。网关 AuthMiddleware **Bearer 单分支**：JWT 优先，非 JWT → access token 查证（auth_service gRPC `ValidateAccessToken`），两者均无效 → 401。前端仍只认 Bearer，不留双口径。

---

## 3. skill 使用说明

### 3.1 下载 skill

1. 浏览器登录平台，按所属前端点击「**连接你的 agent**」**炫彩入口按钮**，打开入口页面。三端入口位置（2026-10-22 最终裁定）：**旧 Vue = 左侧栏**；**React / 新 Vue = 灵犀Agent 页 /ai-chat 右上角 + Agent 工作台浮窗头行右上角**；导航栏 / 顶栏均无入口。
2. 入口页面内展示使用说明与 skill 服务地址配置（见 §3.3）。
3. 点击**炫彩「下载 skill」按钮**，下载 skill 包（zip：SKILL.md + MCP 配置模板）。

### 3.2 安装到外部 agent

- **Claude Code**：将 skill 包解压后的目录放入 Claude Code 的 skills 目录（项目 `.claude/skills/` 或用户级 `~/.claude/skills/`），重启会话即可按 SKILL.md 中的说明调用平台能力。
- **Codex**：将 skill 包放入 Codex 的 skills 目录（如 `~/.codex/skills/`），后续按 SKILL.md 调用。
- **其他 CLI agent**：按各 agent 自身的 skill 目录约定放置 SKILL.md。

skill 包内 **SKILL.md** 包含：能力清单、服务地址配置说明、Access Token 使用方式，以及至少一个能力接口的 curl 调用示例（见 §3.4）；**MCP 配置模板**（`mcp.json`）见 §4.1。

### 3.3 服务地址 URL 配置

- skill 内所有 URL 路径**均可配置**，适配多网络环境（IP / http(s) 域名均支持）。
- 入口页面默认取**当前浏览器地址栏**（`window.location.origin`，如 `http://192.168.x.x:5000`）作为服务地址，**可编辑修改**后再下载。
- 下载时服务地址作为 `base_url` 参数传给 `GET /api/v1/agent/skill?base_url=<服务地址>`，注入 skill 包模板（SKILL.md 与 mcp.json 内 URL 预填该值）；后端另从 Host / Origin 头兜底。下载本身需登录（JWT）。

### 3.4 用 token 调通能力接口示例

SKILL.md 内示例（以任务列表为例）：

```bash
# 替换 <服务地址> 为入口页面配置的服务地址，<明文token> 为个人配置页创建的 access token
curl -s \
  -H "Authorization: Bearer at_<明文token>" \
  "http://<服务地址>/api/v1/tasks?page=1&per_page=10"
```

返回 `data.items` 即任务列表。其他能力接口同理：URL 前缀替换为配置的服务地址，Authorization 头统一使用同一个 access token；token 权限不含目标接口所需权限时返回 403。

---

## 4. MCP 使用说明

### 4.1 端点与配置模板

- 平台在**网关内**提供 MCP 协议端点：`{服务地址}/api/v1/mcp`（JSON-RPC 2.0；`initialize` / `tools/list` / `tools/call`）。
- skill 包内附 `mcp.json` 配置模板：模板中服务地址预填入口页面配置的 `base_url`（可改），指向网关 MCP 端点；Authorization 头填同一 access token。

示例（Claude Desktop MCP 配置）：

```json
{
  "mcpServers": {
    "intelligent-audio-test": {
      "url": "http://<服务地址>/api/v1/mcp",
      "headers": {
        "Authorization": "Bearer at_<明文token>"
      }
    }
  }
}
```

### 4.2 同一 token 与 skill 通用

MCP 连接使用与 skill **完全相同的 Access Token**（同一 `Bearer at_xxx`，走网关同一条 AuthMiddleware 分支）：在个人配置页创建 / 启停 / 删除一次，skill 与 MCP 同时生效 / 失效。

### 4.3 tools 清单（覆盖能力与除外边界）

tools 注册表 = INT-1140 覆盖能力清单：

- **覆盖（经 MCP 暴露）**：
  - task：任务 CRUD / 执行控制 / 合并 / 批量 / 导出导入 / 发布 / 结果复核 / 挑选合并 / 分享
  - case：用例 CRUD / 复制 / 预览 / 导入导出 / 分享
  - audio：音频查看 / 上传 / 修改 / 删除 / 转码 / 文件夹 / 分享
  - device：被测设备 CRUD / 控制；播放设备 CRUD / 控制
  - evaluation：评估维度查看 / 触发评估 / 维度分类管理 / 导入导出 / 分享
  - report：报告 CRUD / 发布 / 对比 / 日志下载 / 分享
  - algorithm：算法配置查看 / 定义分组参数管理 / 用例算法参数
  - tag / group：标签与分组的 CRUD / 分享
  - 跨域：数据可见性 `:share` 分享点、data-transfer（task 导出 / 导入）、favorites / trash（收藏 / 回收站，INT-141）、benchmarks、report-studio
- **除外（不暴露）**：
  - 系统设置：auth users / roles / permissions / oauth-providers、option（系统选项）、system health / status
  - 个人信息：auth me / self / change-password / OAuth 绑定
  - 待负责人验收核对：`log:read` 倾向覆盖、`log:manage` / `log:websocket` 倾向除外；SSE `/api/v1/sse` 倾向除外（长连接推送）
- **越权**：token scopes 不含某工具所需权限时，`tools/call` 拒绝（403 语义）。

---

## 5. 实现演进裁定记录

- **2026-10-21（INT-1148 实施，实现演进裁定）**：Access Token 领域落地——明文 `at_` + 32 hex（≈128 bit）；**只存 SHA-256 哈希** + 末 4 位 `token_hint`；scopes 空列表 = 继承用户全部权限；`expires_at` `0` = 永不过期；**软删（`deleted_at`）+ status（enabled|disabled）**（对齐本平台收藏 / 回收站语义，new-api 为硬删，本平台取软删）；每用户上限默认 20、默认有效期 30 天（`ACCESS_TOKEN_MAX_PER_USER` / `ACCESS_TOKEN_DEFAULT_EXPIRY_DAYS` 配置项可调）。
- **2026-10-21（INT-1152 一致性审计回写，实现演进裁定）**：每用户上限按「未软删 token 数」计（`count_active_by_user`，含已停用），**停用不释放配额，仅删除（软删）可释放**——§2.5 据此回写；实现侧该限额报错文案（「删除或停用」）略过宽，不改变行为语义。
- **2026-10-21（INT-1149 实施，实现演进裁定）**：网关 AuthMiddleware **Bearer 单分支**（JWT 优先 → 非 JWT 走 access token 查证）；AUTH_MODE=off 下先尝试 access token 查证、均失败才回落 dev_user；**生效权限 = 用户当前权限 ∩ token scopes**（`GetUserPermissions` 实时拉取，不用 JWT 快照）；网关 `/api/v1/auth/access-tokens[/{id}]` 转发 auth_service 同前缀端点。
- **2026-10-21（INT-1152 使用说明文档）**：本文档按 INT-1140 规格 + INT-1142 已裁定契约编写；**skill 包与 MCP 端点（INT-1150 / BE3）尚未落地**，落地后须回写：skill zip 内 SKILL.md / mcp.json 模板的具体字段、MCP 端点 `/api/v1/mcp` 的请求 / 响应格式、tools 注册表具体工具名与参数映射；若实现与本文档契约有出入，以本节实现演进裁定方式回写。
- **2026-10-22（INT-1188 文档同步，实现演进裁定）**：新 Vue「连接你的 agent」入口位置按 React 二轮裁定同步（INT-1140 线程负责人回复「1 同步」）——**顶栏 TopBarRight 与左侧栏导航均不放**，入口改放**灵犀Agent 页 /ai-chat 右上角 + Agent 工作台浮窗头行右上角**；文案统一「连接你的 agent」，炫彩样式不变。三端入口位置最终口径：**旧 Vue = 左侧栏**；**React / 新 Vue = 灵犀Agent 页 /ai-chat 右上角 + Agent 工作台浮窗头行右上角**（导航栏 / 顶栏均无入口）。新 Vue 返工经 INT-701 派发实施中，落地后本节与 §3.1 无需再改。
