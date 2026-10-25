# 09 API 协议面与执行道契约（A0 裁定 + B0 修订）

> 裁定日期：2026-10-24　卡片：INT-1788（A0）、INT-1798（B0，修订）　状态：**已裁定，未实施**
> 修订说明：负责人 2026-10-24 拍板把 A0 的「三条执行道」收敛为「流式 / 非流式」两条，并把 `protocol` / `streaming` 从 `apis.meta` 抬为 `apis` 表列。本文中被推翻的 A0 条款逐条标注 **【2026-10-24 负责人修订】**；未标注的 A0 条款继续有效。
> 适用域：被测 API 执行链路（`api_test_service`）——从 `apis` 配置到 `rounds[i].output` 产出。
> 不适用：离线搬运链路的协议面（INT-1782，见 §八）；前端推送链路（`api_gateway` WS/SSE，那是平台自己的通道，不是被测 API 的协议）。
> 前置裁决：C0（INT-1745）的 `rounds[i].output` 子字典契约本卡不重开，只规定各协议如何喂给它。

---

## 一、术语与边界

| 术语 | 含义 | 落点 |
|------|------|------|
| **protocol** | 被测 API 的传输协议，`apis` 上的一个属性 | **列** `apis.protocol VARCHAR(20) NOT NULL`，值域 4 值（§3.2） |
| **streaming** | 被测 API 的交互形态：`true` = 流式（= 实时），`false` = 非流式（= 非实时） | **列** `apis.streaming BOOLEAN NOT NULL` |
| **执行道（lane）** | 由 `streaming` 唯一决定的执行语义，**派生值，不落库** | `ExecutionLane`：`streaming` / `non_streaming` |
| **归一事件（NormalizedEvent）** | 传输层吐出的唯一原始产物，见 §五 | transport 的 `recv()` |
| **wire payload** | 一条被测 API 业务消息的可 JSON 化 dict | `NormalizedEvent.payload` |
| **field_path** | 在 wire payload 内取值的点号路径 | 已实施：C2（INT-1747），落 `algorithm_api_params(direction=output).field_path`（§4.2） |

一句话：**一个被测 API 实体，四个协议值 × 两个流式值，两条执行道；道只由 `streaming` 决定，协议不参与执行道判断。**

【2026-10-24 负责人修订】A0 原文「一个被测 API 实体，四个协议值，三条执行道」作废；「协议不拆实体、不拆菜单、不拆路由分支」继续有效。

---

## 二、现状核对（逐条给代码位置）

### 2.1 遗留问题的代码事实

| 事实 | 代码位置 | 说明 |
|------|---------|------|
| 协议与流式性被压进一个枚举 | `api_test_service/infrastructure/persistence/models/api_models.py:42`（`device_type`）、`shared/models/common_enums.py:100-111`（`DeviceType`） | `http_api` 同时表示「http」与「非流式」；`websocket_api` 同时表示「websocket」与「流式」 |
| 执行路由直接吃该枚举 | `api_test_service/core/api_executor.py:58-67`（`_executor_registry` + `route_executor(device_type)`） | 未知值静默回退 `APISessionExecutor` |
| 用轮次数二次推断流式 | `api_test_service/core/api_executor.py:202-229`（`rounds and len(rounds) > 1` → `APISessionExecutor`） | 就是负责人说的「遗留问题」 |
| API 实体仍带 `device_type` | `api_test_service/domain/entities/api.py:146`、`api_test_service/application/api_crud_service.py:294`（读侧 `to_dict`）、`:363/:405/:499`（写侧） | 写入/读出一整条链路都按三值枚举 |
| `meta.protocol` 仍在读 | `api_test_service/infrastructure/adapters/registry.py:515-536`（`infer_protocol`：用例 `protocol` > `meta.protocol` > 端点前缀 > 默认 HTTP） | 协议有两个来源（`device_type` 与 `meta.protocol`），口径不一致时无人裁决 |
| 执行器配置对象是白名单 | `api_test_service/core/api_executor.py:652-681`（`MockAPIConfig`） | 新列不进白名单即被静默丢成 `None` |

### 2.2 数据库实测（2026-10-24，主库 `intelligent_audio_test`，只读）

| 统计 | 结果 |
|------|------|
| `apis` 总行数 / `device_type` 分布 | 178 / 全部 `http_api`（含软删行；无 `websocket_api`、无 `NULL`、无非法值） |
| `meta` 含 `protocol` 键的行数 | 62 / 178，取值只有 `http`、`https` 两个 |
| 唯一未软删 API（id=1） | `device_type=http_api`、`meta.protocol=https`、首端点 `http://100.70.20.135:5000` |
| `test_cases` 顶层带 `protocol` 的用例 | 0 / 775 |
| `apis` 现有列 | 无 `protocol`、无 `streaming`（`information_schema.columns` 核验） |

结论：本库的回填是单值映射（`http_api → http + false`），且 `meta.protocol` 与 `device_type` 无冲突；迁移风险集中在「代码未同步时新列恒默认」而非数据本身。

---

## 三、六条裁定

### 3.1 裁定一：执行道收敛为两条（问题 1）

**结论：执行道只有两条，`ExecutionLane` 只有两个成员，值由 `streaming` 布尔唯一决定。**

```python
# shared/models/common_enums.py
class ExecutionLane(str, Enum):
    STREAMING = 'streaming'          # 流式 = 实时
    NON_STREAMING = 'non_streaming'  # 非流式 = 非实时
```

唯一推导入口（不接收 protocol / rounds / device_type）：

```python
def lane_of(streaming: bool) -> ExecutionLane
```

**组合矩阵（协议 × 流式性 → 道 → 执行器）**

| protocol | streaming | lane | 执行器（道内策略） | B1 时是否可写 |
|----------|-----------|------|-------------------|--------------|
| `http` | `false` | `non_streaming` | `rounds≤1` → `APITaskRunner` / `_execute_linear`；`rounds>1` → `APISessionExecutor` | ✅ 已实现 |
| `http` | `true` | `streaming` | `StreamSessionExecutor`（A2，chunked 流式） | ❌ 400，A2 未上线 |
| `websocket` | `false` | `non_streaming` | 无执行器（当前适配器只有会话形态） | ❌ 400，实现未上线 |
| `websocket` | `true` | `streaming` | `RealtimeSessionExecutor`（存量） | ✅ 已实现 |
| `sse` | `false` | `non_streaming` | 无执行器 | ❌ 400，A2 未上线 |
| `sse` | `true` | `streaming` | `StreamSessionExecutor`（A2） | ❌ 400，A2 未上线 |
| `grpc` | `false` | `non_streaming` | unary 走 `APISessionExecutor` / 线性 | ❌ 400，A1 未上线 |
| `grpc` | `true` | `streaming` | server-stream → `StreamSessionExecutor`（A2 件）；bidi → `RealtimeSessionExecutor` | ❌ 400，A1 未上线 |

对 A0 三条道的处置 **【2026-10-24 负责人修订】**：

| A0 原道 | 归入 | 说明 |
|---------|------|------|
| `unary` | `non_streaming` | 单请求单回复属非流式 |
| `session` | 按 `streaming` 拆分 | HTTP 多轮（`streaming=false`）/ WS 会话、gRPC bidi（`streaming=true`）分属两道；「多轮」不再是道判据 |
| `stream` | `streaming` | SSE、gRPC server-stream 与 WS 同属流式道，靠道内策略区分 |
| `execution_lane` 名称 | 保留 | 枚举名与字段名仍叫 `execution_lane`，不复用 `execution_mode`（`ExecutionMode` 已被 INT-1115 的 `parallel/serial` 占用，`shared/models/common_enums.py:143-146`） |

**道内策略不丢语义（WS 的 pacing / 打断 / `RealtimeRoundMode`）**

- `RealtimeSessionExecutor` 原样保留为流式道的「按轮次」策略；`domain/services/realtime_pacing_service.py`、`resolve_round_mode → RealtimeRoundMode`（`core/realtime_session_executor.py:749-791` 一带）全部不动。
- `StreamSessionExecutor`（A2 新增）是流式道的「按事件」策略，按 §五 的句子边界切轮。
- 两者由**能力声明**选择，不按协议名写 if/else：

```
capabilities = {session_rounds, event_rounds, pacing, barge_in, client_push, session_affinity}
http+non-streaming        → {}
websocket+streaming       → {session_rounds, pacing, barge_in, client_push, session_affinity}
sse+streaming             → {event_rounds}
grpc unary (non-streaming)→ {}
grpc server-stream        → {event_rounds}
grpc bidi                 → {session_rounds, client_push, session_affinity}
```

- 道内「按轮次 / 按事件」是执行器内部策略；**不得**再以 `rounds>1` 推断流式（`api_executor.py:222-227` 的推断取消，「多轮走会话」降为 `non_streaming` 道内部的分支）。

### 3.2 裁定二：`protocol` × `streaming` 加列契约（问题 2）

#### 3.2.1 DDL 与默认值

```sql
-- 第一步：加列（先可空，避免存量行违反 NOT NULL）
ALTER TABLE apis ADD COLUMN IF NOT EXISTS protocol  VARCHAR(20);
ALTER TABLE apis ADD COLUMN IF NOT EXISTS streaming BOOLEAN;

-- 第二步：回填（严格映射，见 §3.6；不在 SQL 里静默兜底）

-- 第三步：收紧约束 + 补默认
ALTER TABLE apis ALTER COLUMN protocol  SET DEFAULT 'http';
ALTER TABLE apis ALTER COLUMN protocol  SET NOT NULL;
ALTER TABLE apis ALTER COLUMN streaming SET DEFAULT false;
ALTER TABLE apis ALTER COLUMN streaming SET NOT NULL;

-- 第四步：删除存量键
UPDATE apis SET meta = (meta::jsonb - 'protocol')::json WHERE meta::jsonb ? 'protocol';
```

| 项 | 结论 |
|----|------|
| 默认值 | `protocol='http'`、`streaming=false`（= 存量绝对多数形态，也是「新建表单预选值」） |
| 默认值语义 | **只在写侧缺省时生效**（新建不传 → http/false）；DB 默认是给迁移窗口内旧代码插入行的安全网，不是业务兜底 |
| 协议词表 | `http` / `websocket` / `sse` / `grpc`，**只存规范值**；`https`、`ws`、`wss`、大写等一律 400 |
| 列名 | 协议 `protocol`、流式性 `streaming`（负责人 2026-10-24 定名）；`realtime` 不再作为字段名或接口词 |
| `meta.protocol` | **迁移后删除**，不保留只读、不双读（负责人 2026-10-24 拍板） |

**关于卡面括注「http+true（SSE）」**：协议值域已由负责人定为 4 值，SSE 的落库形态是 `protocol='sse', streaming=true`；`http+streaming=true` 表示 chunked 流式（非 `text/event-stream`），仅当 A2 一并实现时开放。本条不改负责人已定的值域，只把括注示例归位。

#### 3.2.2 改动清单（B1）

| 层 | 位置 | 改动 |
|----|------|------|
| PO | `api_test_service/infrastructure/persistence/models/api_models.py:42` 附近 | 加 `protocol` / `streaming` 两列（`nullable=False`, `default`/`server_default` 与 DDL 一致）；`device_type` 列**保留不动**，注释标「废弃，P3 删列」 |
| 聚合根 | `api_test_service/domain/entities/api.py:146` | 加 `protocol: str = 'http'`、`streaming: bool = False`；`device_type` 标废弃 |
| PO↔实体 | `api_test_service/infrastructure/persistence/api_test_repository.py:45-130`（`_api_po_to_entity` / `_apply_aggregate_to_po`）、`:279`（`create_api`） | 双向映射两列；`create_api` 不再写 `device_type` |
| 应用层 | `api_test_service/application/api_crud_service.py:294`（`to_dict`）、`:363/:405`（create）、`:499`（update） | `to_dict` 输出 `protocol`/`streaming` 并**移除 `device_type`**；create 收 `protocol`/`streaming`（缺省 http/false）；update 按键覆盖 |
| 校验 | `api_test_service/application/api_crud_service.py:79-81` | 把 `device_type` 值域校验替换为：`protocol` ∈ 4 值、`streaming` 为 bool、组合在可用矩阵内（§3.2.3）；**显式收到 `device_type` 一律 400** |
| 枚举 | `shared/models/common_enums.py:125-129` | `APIProtocol` 加 `SSE='sse'`、`GRPC='grpc'`（值域承载体）；`AdapterProtocol` **本卡不加**（协议级 base 尚未落地，A1/A2 落地时再加；本条收口 A0 §3.4② 的「本卡补两值」） |
| gRPC | `shared/proto/api_test_service.proto` | **API CRUD 不改 proto**：`CreateAPIConfigRequest.data` / `UpdateAPIConfigRequest.data` 是 JSON 串，新字段随 JSON 透传。`StartAPITestRequest` 也不加字段（见 §3.4） |
| 网关 schema | `api_gateway/schemas/api.py:33-57`（`ApiItem`）、`:91-108`（`ApiCreateInput`）、`:110-127`（`ApiUpdateInput`）、`:25-31`（`ApiListQuery`） | 详情/列表：加 `protocol`/`streaming`，`device_type` 保字段但标废弃（服务端 400 拦截写侧）；创建/更新：加两字段 + 保留 `device_type` 用于「显式拒绝”；列表查询：加 `protocol`、`streaming` 两个过滤项 |
| 列表查询 | `api_test_service/infrastructure/persistence/api_test_repository.py:334-360`（`list_apis`）、`api_gateway/application/services/api/api_query_service.py:24-45` | 加 `protocol` / `streaming` 等值过滤；网关把查询参数透传给 gRPC |
| 导入导出 | `api_gateway/application/services/device/device_import_export_service.py:77-84`（`_API_FIELDS`） | `device_type` 换成 `protocol`、`streaming`；导入经 `ApiCreateInput` 走同一套校验 |
| 执行器白名单 | `api_test_service/core/api_executor.py:652-681`（`MockAPIConfig`） | **必须**复制 `protocol` / `streaming` 两个属性（漏复制即恒 `None`） |
| 协议推断 | `api_test_service/infrastructure/adapters/registry.py:515-536`（`infer_protocol`） | 改读 `api_config.protocol`（列）；删除 `case_config.protocol` 与 `api_config.meta.protocol` 两个来源、删除端点前缀兜底（单一来源，见 §3.4） |

#### 3.2.3 写侧规则（不静默兜底）

1. **新建**：缺省 → `protocol='http'`、`streaming=false`（前端预选，后端同一默认）。
2. **可用矩阵**（B1 上线时）：只放行 `http+false` 与 `websocket+true`；其余组合 400，文案固定：`协议 {protocol} 与流式性 streaming={true|false} 的组合实现未上线`。
3. **更新**：只校验提交的键；改 `protocol` 或 `streaming` 后必须重新过可用矩阵。
4. **旧前端**：写请求携带非空 `device_type` → 400，文案：`device_type 已废弃，请改用 protocol + streaming`。
5. **单执行单元单道**：一个任务内所有被测 API 的 `streaming` 必须一致（任务用一个执行器跑全部 `api_configs`，`api_executor.py:262`）。不一致 → 任务创建 400；执行侧再断言一次，违反即用例失败并写明原因（防历史脏数据）。
6. **读侧**：列表/详情/导出返回 `protocol`/`streaming`，不再返回 `device_type`。

### 3.3 裁定三：`device_type` 处置（问题 3）

**结论：`apis.device_type` 废弃；`task_case_relations.device_type` 保留为「执行亲和域令牌」，由 `streaming` 派生。**

| 载体 | 处置 | 理由 |
|------|------|------|
| `apis.device_type` | **废弃**（不再写、不再读、不再返回；列保留到 P3 删） | 它正是「协议+流式性」压在一起的病灶；API 的协议与流式性已由两新列表达 |
| `task_case_relations.device_type` | **保留**，语义收紧为「执行亲和域」：`physical` = 物理设备；`websocket_api` = 需要实例亲和的流式会话；`http_api` = 无状态请求 | 被 5 处消费且带 DB 唯一索引 `uq_task_case_route`：调度分发（`task_dispatch.py:266-295`）、亲和路由（`:289-295` → `RealtimeSessionRegistry.route_or_bind`）、统计派生（`_task_case_stats_mixin.py:260-330`）、发布任务快照/还原（`published_task_repository.py:1123-1182`）、前端任务类型筛选。改名/换维度收益为零，回归面极大 |
| 展示 | 前端不再显示 `device_type`；协议显示 `protocol`，实时性显示 `streaming` | 消除「websocket_api = 协议」的误读 |

**派生规则（唯一）**

| `streaming` | 派生 `task_case_relations.device_type` | 说明 |
|-------------|--------------------------------------|------|
| `false` | `http_api` | 无状态 |
| `true` | `websocket_api` | 亲和域（SSE 也亲和是保守超集，只损失一点负载均衡自由度） |
| 物理设备（E2E） | `physical` | 不进 `apis` 表，不参与本规则 |

派生点（B1 必改两处）：

| 位置 | 现状 | 改为 |
|------|------|------|
| `task_service/infrastructure/persistence/_task_crud_mixin.py:197-206`（建任务，请求未带 device_type 时的兜底） | 配置形态派生 → API 一律 `http_api` | 按任务 `api_ids` 对应 API 的 `streaming` 派生（任一为流式 → `websocket_api`）；取不到 API 配置或混道 → 400，不落猜测值 |
| `task_service/infrastructure/persistence/_task_crud_mixin.py:564-590`（运行中动态加用例） | 硬编码 `'physical' if derived == 'e2e' else 'http_api'` | 同上，按任务已关联 API 的 `streaming` 派生；取不到 → 400「无法确定执行亲和域」，**不得**静默落 `http_api` |
| 前端建任务（React / 新 Vue） | `deriveApiTargetDeviceType` 按 `deviceType` 或端点 `ws://` 前缀派生 | 按 `api.streaming` 派生（B2） |

数据来源：`task_service` 不直读 `apis` 表（跨域归属）。在 `task_service/infrastructure/acl/api_acl_repository.py` 增加一个只读方法（`get_api_streaming_flags(api_ids)`，经既有 `GetAPIConfig` 逐 id 取 JSON 的 `streaming`），供建任务兜底与动态加用例使用。这是唯一的跨服务读，且是既有 ACL 的扩展。

**迁移映射（存量数据逐值列出）**

| `apis.device_type` 存量值 | `protocol` | `streaming` | 备注 |
|---------------------------|-----------|-------------|------|
| `http_api` | `http` | `false` | 主库 178/178 |
| `websocket_api` | `websocket` | `true` | 主库 0 行；其他环境按此映射 |
| `physical` | — | — | **非法**：`apis` 表不承载物理设备。迁移遇此值 → 中止并列出 id |
| `NULL` / 空串 | — | — | **非法**（列本身 NOT NULL，理论不可达）→ 中止并列出 id |
| 其他未知值 | — | — | **非法** → 中止并列出 id |

`meta.protocol` 交叉校验（仅当键存在）：`http`/`https` → `http`；`ws`/`wss` → `websocket`；`sse` → `sse`；`grpc` → `grpc`；其余 → 中止并列出 id。归一后的值必须与 `device_type` 推出的协议一致，不一致 → 中止并列出 id（不猜、不覆盖）。主库 62 行全部一致。

### 3.4 裁定四：路由改造（问题 4）

1. **`route_executor(lane)`**：`api_test_service/core/api_executor.py:58-67` 的执行器注册表键由 `DeviceType` 三值改为 `ExecutionLane` 两值；未知/`None` lane **抛错**，删除「未知类型回退 APISessionExecutor」的静默兜底。

```python
self._executor_registry = {
    ExecutionLane.NON_STREAMING.value: self._non_streaming_executor,   # 道内再按 rounds 分线性/会话
    ExecutionLane.STREAMING.value:     self._streaming_executor,       # 道内再按能力选按轮次/按事件
}
def route_executor(self, lane): ...  # lane 非法 → ValueError
```

2. **道值来源**：`_validate_and_get_data`（`api_executor.py:535-625`）在组装 `data` 时，从已加载的 `api_configs` 读 `streaming`，做单道断言后写入 `data['streaming']`；`_execute_single_or_multi` 只读 `data['streaming']`，**不再读 `data['device_type']`**。`device_type` 仍保留在 `data` 里，只用于音频渲染出口与失败文案（`_get_audio_data`、`:727-728`）。
3. **取消 `rounds>1` 推断**：`api_executor.py:222-227` 的「多轮 → 会话执行器」不作为道判据；`rounds` 只决定非流式道内部走线性还是 `APISessionExecutor`，流式道内部走按轮次还是按事件。
4. **`StartAPITest` 入参不改**：`shared/proto/api_test_service.proto:66-71` 的 `device_type` / `device_id` 保留，语义收紧为「调度侧亲和域路由令牌」，**执行层不据此选道**。不需要新增 lane/streaming 字段——执行器以自己读到的 `apis.streaming` 为准，避免调度侧与执行侧双口径。
5. **`infer_protocol` 单一来源**：只读 `api_config.protocol`（列）。删除用例级 `case_config.protocol` 来源（主库 775 个用例中 0 个使用，删除是零数据影响）、删除 `meta.protocol` 来源与端点前缀兜底；值不在 4 值内 → 抛配置错误（`error_source=config`, 400）。
6. **调度层不改**：`task_dispatch.py:266-295` 仍按 `task_case_relations.device_type` 分发（physical → E2E；两 API 值 → api_test_service）与判亲和（`websocket_api`）。这条与道无关，不在本卡改。

### 3.5 裁定五：全量读点清单（问题 5）

处置列含义：**改** = 本批改；**不改** = 语义仍成立、无改动；**派生** = 由 `streaming` 派生新值；**废弃** = 停止读写。

#### api_test_service

| 位置 | 现状 | 处置 |
|------|------|------|
| `core/api_executor.py:58-67` | `route_executor(device_type)` | **改** → `route_executor(lane)` |
| `core/api_executor.py:202-229` | 按 `device_type` 选执行器 + `rounds>1` 推断 | **改**（道按 `streaming`；rounds 内部策略） |
| `core/api_executor.py:535-625` | `data['device_type']` | **改**：`data['streaming']` + 单道断言；`device_type` 仅供亲和/渲染/文案 |
| `core/api_executor.py:652-681` | `MockAPIConfig` 白名单 | **改**：补 `protocol` / `streaming` |
| `application/api_crud_service.py:79-81,294,363,405,499` | `device_type` 校验/序列化/写入 | **改**（§3.2.2）；`device_type` **废弃** |
| `domain/entities/api.py:146` | `device_type` 字段 | **废弃**，加两新字段 |
| `infrastructure/persistence/api_test_repository.py:82,279,334-360` | 读/建/列表 | **改**：两新列；列表加过滤 |
| `infrastructure/adapters/registry.py:515-536` | `infer_protocol` 三来源 | **改**：只读 `protocol` 列 |
| `domain/repositories/acl/audio_render_acl_repository.py:71-85` | `route_render_mode(device_type, stream)` | **改**：形参改 `streaming: bool`（`true→'stream'`，`false→'file'`，physical 拒绝不变）；现无业务调用方、仅单测 `tests/unit/test_int67_render_acl.py` 与 `tests/integration/test_int67_render_dual_end_smoke.py` 引用，同步改单测 |
| `core/realtime_session_executor.py:4`、`core/api_test_service.py:100-140`、`interfaces/grpc/servicers.py:120-129`、`application/commands/api_test_commands.py:24-30`、`application/handlers/command_handlers.py:82-92` | `device_type` 透传（亲和令牌） | **不改**（只改注释语义） |
| `security/`、`audio` 渲染调用 | 无 `device_type` 依赖 | **不改** |

#### task_service

| 位置 | 现状 | 处置 |
|------|------|------|
| `infrastructure/persistence/_task_crud_mixin.py:197-206` | 建任务兜底派生 | **改**：按 API `streaming` 派生 |
| `infrastructure/persistence/_task_crud_mixin.py:564-590` | 动态加用例硬编码 `http_api` | **改**：按 API `streaming` 派生；取不到 400 |
| `infrastructure/persistence/_task_crud_mixin.py:140-235`（`case_devices` 写入） | 信任前端带来的 `device_type` | **不改**（值域仍是三值；前端改派生源） |
| `core/execution_engine/mixins/task_dispatch.py:74-83,204-214,266-295` | 调度分发 + 亲和判定 | **不改**（令牌语义不变） |
| `core/execution_engine/mixins/case_execution.py:40-74` | `device_type` 随 `StartAPITest` 下发 | **不改** |
| `core/execution_engine/mixins/device_check.py:22-27`、`task_lifecycle.py:132-137,210` | physical / API 判定与 TaskAPI 初始化 | **不改** |
| `application/queries/task_queries.py:61-76`、`application/services/published_task_service.py:136-142`、`application/task/cherry_pick_service.py:1134-1183,1426-1449`、`application/task/task_lifecycle_service.py:563-567` | 任务筛选/类型派生/快照继承/评估口径 | **不改**（只用 `physical` vs `http_api|websocket_api` 的粗粒度） |
| `infrastructure/persistence/_task_case_stats_mixin.py:260-330`、`infrastructure/read_models/task_device_type_derivation.py:1-60` | 统计分布与任务级回退 | **不改**（`http_api` 仅表示 api 域） |
| `infrastructure/acl/api_acl_repository.py` | 只有 test/start | **改**：加 `get_api_streaming_flags(api_ids)` |

#### api_gateway

| 位置 | 现状 | 处置 |
|------|------|------|
| `schemas/api.py:25-57,91-127` | 读/写契约 | **改**（§3.2.2） |
| `application/services/api/api_query_service.py:24-45` | 列表过滤 | **改**：透传 `protocol`/`streaming` |
| `application/services/device/device_import_export_service.py:77-84` | 导入导出字段 | **改**：`device_type` → 两新字段 |
| `schemas/task.py:219-222,263-283` | 任务创建 `case_devices[].device_type` | **不改**（亲和令牌），但 B1 在任务创建处加「任务内 API 单道」校验 |
| `application/services/home_service.py:212`、`application/services/task/task_query_service.py:129,250` | 任务级 `device_types` | **不改** |

#### report_service

| 位置 | 现状 | 处置 |
|------|------|------|
| `application/services/report_utils/resource_mixin.py:225-255`（`serialize_api`） | 报告快照 `summary.apis[]` 不含协议/流式性 | **改**：输出 `protocol`、`streaming`（快照字段只增） |
| `application/services/benchmark_ranking_service.py:71-84`（`_resolve_subject`） | `api.type` 或 `api.protocol` 含 `websocket` → `websocket_api`，否则 `http_api` | **改**：按 `api.streaming` 派生；旧快照无该键时按 `device_type` 字段/任务关系回退，并记 WARNING（历史报告不重算） |
| `application/services/report_utils/resource_mixin.py:70-130`（`get_resource_name`）、`report_compare_helpers.py:150-210`、`report_data_builder_case_mixin.py` | 资源名 = `任务前缀-APIid-名称-版本[-result_type]` | **不改**（不读 `device_type`，核验确认） |
| `application/services/report_aggregation/statistics_service.py:185-282` | `device_type` 维度统计（物理设备维度） | **不改** |
| `domain/dto/report_acl_dto.py:79,184,193`、`domain/entities/benchmark.py:102`、`benchmark_models.py:43` | `device_type` 为结果/排行快照字段 | **不改** |

#### 前端（React / 新 Vue）

| 位置 | 处置 |
|------|------|
| API 表单（协议下拉 + 流式开关） | **改**：协议 4 选项，sse/grpc 禁用并提示「协议实现未上线」；流式开关按可用矩阵联动；默认 http/false |
| API 列表/筛选/列 | **改**：协议列读 `protocol` 列（不再读 `meta.protocol`），新增「流式 / 非流式」列与筛选 |
| 建任务的目标派生 | **改**：`device_type` 由 `api.streaming` 派生 |
| 导入导出对话框 | **改**：字段随 `_API_FIELDS` 同步 |
| 任务列表的类型筛选/徽章 | **不改**（任务级 api/e2e/mixed 口径不变） |

### 3.6 裁定六：迁移与发布/回滚（问题 6）

**迁移脚本（新增一份，幂等）**：`scripts/migrations/202610/add_api_protocol_streaming_int1798.py`，默认 dry-run，引导链须带 `--apply`。

执行顺序（同一脚本内固定，失败即回滚）：

1. **加列**（可空，`ADD COLUMN IF NOT EXISTS`）。
2. **校验 + 回填**（§3.3 映射表；`meta.protocol` 交叉校验；非法值/冲突 → 打印 id 清单并以非 0 退出，**不写任何行**；本库为单值映射）。
3. **收紧约束 + 补默认**（`SET DEFAULT` / `SET NOT NULL`）。
4. **删除 `meta.protocol` 键**（只删该键，保留 `meta` 其余键）。

约束与顺序细节：

- 全部 DDL 走 db_bootstrap 的锁预算（`lock_timeout=5s` / `statement_timeout=300s`，`docker/db_bootstrap_entrypoint.py:34-75`）；178 行的回填在单事务内完成。
- **引导链位置**：加入 `BOOTSTRAP_STEPS` 时必须排在 INT-1741 的 `analyze_stale_statistics_int1741.py` **之前**（该步必须是最后一步，`tests/` 有守护用例）；建议紧接 `add_test_result_result_type_int1510.py` 之后。
- 幂等：列存在且已 NOT NULL → 列步骤 SKIP；回填按值比对（已是目标值不写）；`meta` 无键 → 跳过。
- 全新库：`create_all_tables.py` 按 ORM 建表已含两列，脚本全 SKIP。

**发布顺序（前后端同批，无灰度、无双写）**：

1. **DB 迁移**（先）。旧后端此时读不到 `meta.protocol`，`infer_protocol` 回落到端点前缀 —— 对已实现的两个协议（http/websocket）结论不变（http(s):// → HTTP，ws(s):// → WEBSOCKET），可安全过渡。
2. **后端（B1）**：新代码只读新列；写侧开始拒绝 `device_type` 与不可用组合。
3. **前端（B2）**：与 B1 同批上线；本批内旧前端写 API 会 400（已知且接受）。

**回滚**：按整批回退（后端 + 前端同版本回退），**新列保留不删**。回滚后旧后端只读 `device_type`/端点前缀，不回读 `meta.protocol`（已删）但结论等价；旧前端不再发送 `protocol`/`streaming`，新列保持默认/存量值不动。不写双写脚本。

---

## 四、不变契约（承接 A0，未被 B0 推翻）

### 4.1 归一事件与轮次切分

归一事件（`NormalizedEvent`，传输层 `recv()` 的唯一产物）：

```
{
  "event_type": "message" | "error" | "end_stream" | "heartbeat",
  "seq":        0,            // 连接内单调递增
  "payload":    {...},        // dict，必填；error 时为 {code, message, source}
  "ts":         1710000000.123
}
```

- `payload` 必须是 dict；二进制音频帧不进 `payload`，仍走 `rounds[i].output_audio_path` / `raw_response`。
- `event_type` 只有 4 值；厂商事件名 → 4 值的映射放适配器（同 `_EVENT_TYPE_MAP` 位置）。
- `RealtimeFrameType`（`common_enums.py:251-268`）与 `RealtimeFrame` 是**观测帧**，保留不动；归一事件是取值视图，两者同管线派生。

轮次切分（按道）：

| 道 / 策略 | 切分依据 | 结束标志 |
|-----------|---------|---------|
| `non_streaming`（线性） | 一次请求 = 一轮 | 响应返回 |
| `non_streaming`（多轮） | `rounds[]` 配置 | `rounds` 用尽 |
| `streaming`（按轮次：WS / gRPC bidi） | `rounds[]` 会话轮 | 会话 `end_stream` / `rounds` 用尽 |
| `streaming`（按事件：SSE / gRPC server-stream） | 句子边界（`meta.is_sentence_end_mapping`，缺省 `is_sentence_end`） | `meta.is_session_end_mapping`（缺省 `session_finished`）或 `end_stream` |

按事件策略沿用 `api_driver_adapter.py:523-528` 的 `asr_mapping` / `trans_mapping` / `sentence_end_mapping` / `session_end_mapping` / `append_mode` 五键，不新造键名。

### 4.2 `field_path` 作用对象

只作用于 `NormalizedEvent.payload`（wire payload），不作用于 HTTP 响应对象、WS 原始帧、gRPC message 对象。

| protocol | wire payload |
|----------|-------------|
| `http` | `response.json()` 顶层 dict |
| `websocket` | `json.loads(单条文本消息)` 顶层 dict |
| `sse` | `event.data` 解析后的 dict |
| `grpc` | `MessageToDict(msg, preserving_proto_field_name=True)`（snake_case） |

禁止协议特有语法进 `field_path`（`$.` / `[?()]` / `//` / `header:` / `event:`）；语法只有点号 + 数字下标，数字下标可写点号（`a.b.0.c`）或方括号（`a.b[0].c`），两种写法等价——`shared/utils/path_extractor.py:1-68`（C2 / INT-1747 已在原函数上扩展 `[n]`，未新增第二个提取器；非法写法如 `a[x]` / `a[-1]` 整体返回 `None`）。存储位置与优先级按 C2 已实施：`algorithm_api_params(direction=output).field_path`，为空则按 `param_code` 取顶层键；`meta.result_parser` / `asr_mapping` / `trans_mapping` 仅在该算法类型**零输出声明**时整体兜底（不做逐键合并），口径见 [18_设备参数和API参数绑定方案 §9.3](../08_算法配置/智能语音算法配置适配/18_设备参数和API参数绑定方案.md)。

### 4.3 错误码映射

所有协议归一到一个 `biz_code` 词表（`{0} ∪ 语义化 HTTP 状态码`）+ 两个诊断字段 `error_source`（`http/websocket/sse/grpc/network/config`）与 `raw_code`。A0 §3.6 的逐协议映射表（HTTP 4xx/5xx、WS close code、SSE 超时、gRPC 16 个状态码、配置/网络错误）**整体保留**，本卡不重开。现有判定 `biz_code in [400,404]`（`api_task_runner.py:297`）与 `str(biz_code) != '0'`（`api_driver_adapter.py:533`）语义不变。

### 4.4 配置载体（A0 §3.5 的保留与修订）

| 键 | 状态 |
|----|------|
| `meta.protocol` | **【2026-10-24 负责人修订】删除**（协议改为列） |
| `meta.grpc` / `meta.sse` | 保留 A0 设计（只有这两个新协议开子对象） |
| `meta.asr_mapping` / `trans_mapping` / `sentence_end_mapping` / `session_end_mapping` / `append_mode` / `error_code_mapping` / `error_msg_mapping` / `result_parser` | 存量通用，不搬家；只读「贴样例响应看提取结果」预览端点见 [20_API响应解析预览端点](../08_算法配置/智能语音算法配置适配/20_API响应解析预览端点.md)（INT-1772，提取走同一份 `path_extractor`） |
| `meta.session_config` / `pacing` / `vendor_adapter` / `ws_headers` / `adapter_class` / 端点级 `api_keys` | 存量，不动 |

其他协议配置一律仍放 `apis.meta`，**不新增表**；`protocol` / `streaming` 是唯一抬为列的两个属性（负责人 2026-10-24 拍板）。

---

## 五、B1（INT-1799）实现边界

### 5.1 改

| 文件 | 改动 |
|------|------|
| `api_test_service/infrastructure/persistence/models/api_models.py` | 加 `protocol` / `streaming` 列；`device_type` 标废弃 |
| `api_test_service/domain/entities/api.py` | 聚合根两字段；`device_type` 废弃 |
| `api_test_service/infrastructure/persistence/api_test_repository.py` | 映射 / 建 / 列表过滤 |
| `api_test_service/application/api_crud_service.py` | 校验、默认值、可用矩阵、`device_type` 400、`to_dict` |
| `api_test_service/core/api_executor.py` | `ExecutionLane` 路由、单道断言、`MockAPIConfig` 白名单、移除 rounds 推断 |
| `api_test_service/infrastructure/adapters/registry.py` | `infer_protocol` 只读列 |
| `api_test_service/domain/repositories/acl/audio_render_acl_repository.py` | `route_render_mode(streaming)` |
| `shared/models/common_enums.py` | `ExecutionLane`；`APIProtocol` 加两值 |
| `api_gateway/schemas/api.py`、`application/services/api/api_query_service.py` | 契约与筛选 |
| `api_gateway/application/services/device/device_import_export_service.py` | 导入导出字段 |
| `task_service/infrastructure/persistence/_task_crud_mixin.py` | 两处派生改按 `streaming` |
| `task_service/infrastructure/acl/api_acl_repository.py` | 新增 `get_api_streaming_flags` |
| `report_service/application/services/report_utils/resource_mixin.py` | `serialize_api` 两字段 |
| `report_service/application/services/benchmark_ranking_service.py` | 按 `streaming` 派生被测主体类型 |
| `scripts/migrations/202610/add_api_protocol_streaming_int1798.py` | 新增迁移 |
| `docker/db_bootstrap_entrypoint.py` | `BOOTSTRAP_STEPS` 在 INT-1741 之前插入本迁移 |
| 单测 | 新增道映射、可用矩阵、迁移映射、单道断言；改 `tests/unit/test_int67_render_acl.py`、`tests/integration/test_int67_render_dual_end_smoke.py` |

### 5.2 明确不动

- `shared/proto/api_test_service.proto`（`StartAPITestRequest` 不加字段；API CRUD 走 JSON `data`）。
- `task_service` 的调度分发、亲和路由、任务类型统计、发布任务快照（`device_type` 令牌语义不变）。
- `e2e_test_service`、`device_service`、`audio_service`、`evaluation_service`。
- `AdapterProtocol` 枚举、适配器注册表既有键。
- `RealtimeSessionExecutor` / pacing / 打断 / `RealtimeRoundMode`。

### 5.3 验收用例（B1 必跑，B2 对应用例见 §6.3）

1. **迁移**：主库 dry-run 报 178 行映射、0 冲突；`--apply` 后 `protocol='http'` 且 `streaming=false` 为 178/178；`meta::jsonb ? 'protocol'` = 0；两列 `is_nullable=NO` 且默认值正确；重复执行全 SKIP。
2. **新建缺省**：不传两字段 → 201，回读 `protocol='http'`、`streaming=false`。
3. **不可用组合**：`grpc+false`、`sse+true`、`http+true`、`websocket+false` 各 → 400，文案含组合与「实现未上线」。
4. **旧前端**：创建/更新带 `device_type` → 400，文案指明改 `protocol + streaming`。
5. **更新**：`http+false` 改 `websocket+true` → 200 且回读一致；改 `websocket+false` → 400。
6. **读契约**：列表/详情无 `device_type` 键；筛选 `protocol=websocket&streaming=true` 只返回命中行。
7. **执行道**：`streaming=true` 且 `rounds=1` 的用例进入 `RealtimeSessionExecutor`（不得落 HTTP 线性）；`streaming=false` 且 `rounds>1` 仍进 `APISessionExecutor`（零回归）。
8. **单道**：任务内混选流式与非流式 API → 任务创建 400；绕过校验直接构造数据 → 执行用例失败且原因写明「同一任务内 API 流式性不一致」。
9. **动态加用例**：向流式 API 任务动态加用例 → `task_case_relations.device_type='websocket_api'`；ACL 失败 → 400 且不落行。
10. **报告**：新生成报告 `summary.apis[].protocol/streaming` 存在；benchmark 排行被测主体类型按 `streaming` 得 `websocket_api`/`http_api`。
11. **回归**：A0 §3.7 第 6 条清单（`tests/unit/test_int511_api_http_ws.py`、`tests/unit/test_int123_round_output_normalization.py` + 各 1 张存量 HTTP/WS 用例结果逐字段 diff 为空）。

---

## 六、B2（INT-1800）实现边界

### 6.1 React（`V9.7.31-WIRING-REACT` / `wiring/react/frontend-react`）

| 文件 | 改动 |
|------|------|
| `src/domain/models/apiConfig.ts:47,62-73` | 去 `deviceType`，加 `protocol`/`streaming`；`deriveApiTargetDeviceType` 改按 `streaming` 派生亲和令牌 |
| `src/infrastructure/dto/apis.dto.ts:40`、`src/infrastructure/adapters/apiConfigAdapter.ts:62` | `device_type` → `protocol`/`streaming` |
| `src/infrastructure/adapters/apiDeviceAdapter.ts:27,50`、`src/domain/models/apiDevice.ts` | 协议列改读 `dto.protocol`（不再读 `meta.protocol`），新增 `streaming` |
| `src/features/devices/components/modals/device-mutate-drawer.tsx:85,110,264,514-523,926-940`、`src/features/devices/lib/api-device-meta.ts` | 协议下拉改 4 值（sse/grpc 禁用提示）+ 流式开关；`meta` 只管理 `environment` 等，不再管 `protocol` |
| `src/features/devices/components/devices-filter-toolbar.tsx:51-53,245-260`、`src/features/devices/types.ts`、`src/features/devices/components/api-device-table.tsx` | 筛选与列：协议（新列）+ 流式性 |
| `src/features/test-execution/modals/api-edit-dialog.tsx:47,110-112,166-167,251-266`、`components/api-card.tsx:80`、`components/api-table.tsx` | `deviceType` 三选改协议 + 流式；徽章按 `streaming` |
| `src/application/test-execution/useTestLaunch.ts:91-113` | 目标亲和令牌按 `api.streaming` 派生 |
| 导入导出对话框 | 字段随 `_API_FIELDS` 同步（协议 + 流式性） |

### 6.2 新 Vue（`V9.7.31-WIRING-UXVUE` / `wiring/ux-vue/frontend/src`）

| 文件 | 改动 |
|------|------|
| `domain/model/apiConfig.ts`、`infrastructure/dto/apiConfigDto.ts`、`infrastructure/adapters/apiConfigAdapter.ts` | 两维字段替换 `deviceType`/`meta.protocol` |
| `components/common/modal/CRUDFormModal.ts:227-277,372,699-712`、`components/common/form/formFieldTypes.ts:58` | 删除「按端点自动派生 deviceType」，改为协议下拉 + 流式开关 |
| API 列表/筛选/列组件 | 协议 + 流式性两维 |
| `components/common/form/FormField.vue:182-190` | `apiMeta` 协议子表单移除（协议升为顶层字段） |
| 建任务目标派生 | 按 `api.streaming` 派生 |

> 新 Vue 的文件为核验基线，实际落位以 B2 开工时该 worktree 为准；功能口径以本节与 React 一致。

### 6.3 验收用例

1. **表单可用性**：协议下拉 4 项，`sse`/`grpc` 置灰且提示「协议实现未上线」；选 `http` 时流式开关关且禁用、选 `websocket` 时开且禁用；新建默认 http/false。
2. **保存回显**：新建 `websocket+流式` 保存后重开，协议与流式开关回显一致；列表与详情一致。
3. **筛选**：协议 + 流式性筛选与接口返回逐条对照（主库真实数据为 178 条 / 全部 http / 非流式）。
4. **旧值不可见**：页面不再出现「device_type / 被测设备类型」输入项与列；后端返回无 `device_type`。
5. **建任务**：选流式 API 建任务，Network 中 `case_devices[].device_type='websocket_api'`；选非流式 → `http_api`。
6. **提示与拒绝**：构造不可用组合（如直接改请求体 grpc+false）→ 前端提示后端 400 文案。
7. **导入导出**：导出表头含 `protocol`/`streaming`、无 `device_type`；导入同结构文件成功。
8. **真实数据**：用 docker 前端（15173/16173）+ 后端 15000 走查，不出现「列表按协议筛选不到」。

---

## 七、与既有裁决的一致性

| 既有裁决 | 本卡关系 |
|---------|---------|
| A0（INT-1788）：三道、协议在 `meta`、`device_type` 派生不废弃、数据零迁移 | **2026-10-24 负责人修订**：三道 → 两道；`protocol`/`streaming` 抬为列；`apis.device_type` 废弃；破坏性迁移 |
| C0（INT-1745）：`rounds[i].output = {target_param: value}` | 不重开 |
| C1（INT-1746）：三条链轮次结构统一 | 依赖；本文不另定 `output` 结构 |
| C2（INT-1747）：`field_path` 存储与优先级 | 依赖；已实施；本文只钉作用对象 |
| INT-1770：`meta.protocol` 词表归一、`AdapterProtocol` 不改本体 | 承接归一词表；本卡把来源改为列并删除该键；`AdapterProtocol` 仍不改 |
| INT-1115 / INT-604：`ExecutionMode = parallel/serial` | 避让；执行道用 `ExecutionLane` |
| 负责人 2026-10-24：不新增 `DeviceType` 成员 | 遵守；不加枚举值 |

---

## 八、与 INT-1782（离线搬运协议面）的互引

- 分工：INT-1782 写搬运链路协议面（客户端 ↔ 网关 REST、网关 ↔ 服务 gRPC、WS/SSE 推送、OSS、MCP）；本文写被测 API 执行链路（`api_test_service` 作为客户端调被测方）。
- 命名一致：`protocol` 值域 `http / websocket / sse / grpc` 两处一致；错误码词表两处一致。
- 不合并：平台在搬运链路是服务端、在被测链路是客户端，合写会污染语义。

---

## 九、遗留与风险

| 项 | 说明 | 归属 |
|----|------|------|
| 破坏性契约变更 | 前后端必须同批；不存在「先上后端、老前端继续跑」的灰度期（负责人已定） | B1/B2 发布顺序 |
| 旧前端写 API | 本批窗口内 400；这是预期行为，不是缺陷 | B2 同批上线 |
| 亲和令牌名不副实 | `task_case_relations.device_type='websocket_api'` 也用于 SSE 流式（保守超集）；展示层一律显示 `protocol`/`streaming` | 设计约束 |
| 历史报告快照 | 旧报告的 `summary.apis[]` 无 `streaming`，排行回退派生并记 WARNING；不重算历史报告 | report_service |
| 协议实现未上线 | sse/grpc/http 流式/websocket 非流式在 B1 时 400；A1/A2 落地后同步扩可用矩阵与 `AdapterProtocol` | A1/A2 |
| 动态加用例跨服务读 | 新增 `get_api_streaming_flags` 让 task_service 依赖 api_test_service 可用性；取不到即 400（不静默） | B1 |
| 文档超前于代码 | `HttpStreamAdapter` / `factory.py` / `base.py` 仍散见 6 份文档，A0 已在 `05_路由与废弃.md §2.4` 补注，其余图文档未重写 | 后续文档卡 |
