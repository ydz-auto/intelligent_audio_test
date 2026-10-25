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

---

## 十、A1（INT-1789）实施回写（2026-10-25）

gRPC 协议面按本文 A0 条款落地，实现位置与口径：

| 项 | 落地 | 说明 |
|----|------|------|
| 传输件 | `api_test_service/infrastructure/adapters/transport/grpc_client.py` | 动态 descriptor（上传 `.proto`，256 KB 上限 + `google/protobuf/*` import 白名单 + 只解析不执行）；unary / server-stream / bidi；`MessageToDict(preserving_proto_field_name=True)` 归一；`NormalizedEvent` 四值事件 |
| 协议级适配器 | `api_test_service/infrastructure/adapters/grpc_adapter.py` | 注册维度 `(AdapterProtocol.GRPC, AdapterVendor.ANY)`；配置只读 `meta.grpc`（`proto_object_key` / `proto_sha256` / `proto_size` / `service` / `method` / `method_kind` / `metadata` / `deadline_ms`），未新增配置键 |
| 流式道策略 | `api_test_service/core/grpc_stream_executor.py` | server-stream **按事件**切轮（一条消息 = 一轮）；bidi **按轮次**切轮，轮次字段与 WS realtime 同构；多轮聚合/落库/评估复用 `APISessionExecutor` |
| 非流式道 | `api_executor._NO_DUT_PROTOCOLS` | gRPC unary 没有 DUT 任务协议（health / create_task / 轮询），按 rounds 逐次调用会话执行器；单轮为该路径的特例 |
| 错误码 | `shared/utils/error_mapping.py` | gRPC 16 个状态码 → `biz_code` 表（§3.6 原表，补登记 11 OUT_OF_RANGE→400）；连接建立失败（连接拒绝 / DNS / TLS）以连接就绪探测判定，归 `network` / 503 |
| 可用矩阵 | `shared/models/common_enums.py` `AVAILABLE_PROTOCOL_STREAMING` | 扩 `(grpc, false)`、`(grpc, true)`；`sse` 两种仍 400（A2 未上线） |
| 枚举 | `AdapterProtocol` 新增 `GRPC` | SSE 值仍待 A2 落地时补 |

本轮明确不做（沿 A0 §四）：TLS / mTLS（insecure + metadata）、server reflection、多文件 proto bundle、
gRPC 音频帧（二进制不进 `payload`，音频仍走 `rounds[i].output_audio_path` 口径）。

**跨卡后续**：B2（INT-1800）前端「协议下拉 sse/grpc 置灰」是基于 B1 时点写的；A1 落地后
`grpc` 后端已可写可执行，前端应解除 grpc 置灰（`sse` 继续置灰到 A2），该改动归 A3 / B2 收口，
不在 A1 范围（A1 不改前端）。

## 十一、A2（INT-1790）实施回写（2026-10-25）

> 状态：**已实施**。本节是实施后的事实回写，与 §三 的裁定一致；§3.1 组合矩阵里
> 「A2 未上线 → 400」的一列自本节起失效，以本节为准。

### 11.1 交付件

| 文件 | 内容 |
|------|------|
| `api_test_service/infrastructure/adapters/transport/sse_client.py` | 新增 `HttpStreamClient`：`text/event-stream` 逐帧解析（`event` / `data` 多行拼接 / `id` / `retry` / 注释心跳）、chunked「一行一个 JSON」兜底、空闲超时、时长上限、按 `Last-Event-ID` 重连；产出归一事件（§4.1 四值 `event_type`） |
| `api_test_service/domain/services/stream_round_splitter.py` | 新增 `StreamRoundSplitter`：句子边界切轮 / 零声明一条 message 一轮 / `append_mode` 聚合 / 会话结束收尾 |
| `api_test_service/core/stream_session_executor.py` | 新增 `StreamSessionExecutor`：流式道「按事件」策略，读流 → 切轮 → 轮次 `output` → 多轮结果落库 → 评估入队 |
| `api_test_service/core/eval_output_collector.py`、`core/evaluation_submitter.py` | `RealtimeSessionExecutor` 的评估字段收集 / 评估入队提库，两条流式策略共用（行为不变） |
| `api_test_service/core/api_executor.py` | `_STREAMING_STRATEGIES` 补 `sse` / `http` → `_stream_executor`；`STREAMING_CAPABILITIES` 补 `sse` / `http → {event_rounds}` |
| `shared/models/common_enums.py` | 可用矩阵在 A1 的 gRPC 两种基础上再扩 `sse+true`、`http+true`，合计 6 组：`http+false`、`websocket+true`、`grpc+false`、`grpc+true`、`sse+true`、`http+true` |
| `api_test_service/application/api_crud_service.py` | `meta.sse` 校验（未知键 / 非法超时 400） |
| `api_test_service/domain/value_objects/sse_policy.py` | SSE 配置边界常量（`SSE_MAX_MS` / `SSE_MAX_RETRY_MS` / `SSE_MAX_RECONNECT_ATTEMPTS`），写侧校验与执行侧线缆限幅共用 |

### 11.2 `meta.sse` 键（写侧校验口径）

| 键 | 类型 / 范围 | 缺省 | 说明 |
|----|------------|------|------|
| `event_name_field` | 非空字符串 | `event` | payload 内事件名键（不进 `field_path`）；执行侧按该键写入事件名，缺省键 `event` 不被额外占用（A2 返工 P3-1） |
| `idle_timeout_ms` | 整数 1-3600000 | `apis.default_max_timeout × 1000` | 无字节多久算空闲超时 |
| `retry_ms` | 整数 0-60000 | `1000` | 重连退避**上限**；服务端帧内 `retry:` 只可缩短、不可放大，并再限幅到 60000 与剩余 `max_duration_ms`（A2 返工 P3-2） |
| `reconnect_enabled` | 布尔 | `false` | 缺省不重连（A0 §3.5 ④：断流即失败，重连会让轮次数不可复现） |
| `max_reconnect_attempts` | 整数 0-10 | `2` | 重连次数上限，用尽转 504 |
| `max_duration_ms` | 整数 1-3600000 | 空（不设上限） | 单条流的整体时长护栏，防挂死 |
| `params` | JSON 对象 | 空 | GET 请求的查询参数，支持 `{{placeholder}}` |

未知键一律 400（防止把 WS 的 `pacing` / `barge_in` 等会话语义写进 SSE 而被静默忽略）。
显式 `null` 与「键未提交」同义：写侧不拒绝，执行侧一律回落上表缺省值（A2 终审 F1，
禁止出现「配置能存、执行不可用」）；`0` 是 `retry_ms` / `max_reconnect_attempts` 的
合法值，不会被缺省值吞掉。

### 11.3 分帧与终止条件

| 情形 | 归一事件 | 业务码 |
|------|---------|--------|
| 服务端正常关闭连接（EOF） | `end_stream` | —（正常收尾） |
| 空闲超时（`idle_timeout_ms` 内无字节） | 可重连则先重连（心跳事件）；否则 `error` | `504` `idle timeout` |
| 传输层异常断开且未到 EOF | 同上 | `504` `connection closed without end_stream` |
| 整体时长超 `max_duration_ms` | `error` | `504` `stream duration exceeded` |
| HTTP 非 2xx | 连接即失败 | `biz_code` = HTTP status，`error_source=sse` |
| 网络层（DNS / 拒绝 / TLS） | 连接即失败 | `503`，`error_source=network` |
| 帧不是合法 JSON 对象 | `error` | `502` |
| 重连退避期间命中停止 / 用例移除 | 立即 `error`（`504` `reconnect aborted by control signal`），不等满退避 | `504` |

重连退避口径（A2 返工 P3-2）：生效退避 = `min(线缆 retry:, 配置 retry_ms, 60000,
剩余 max_duration_ms)`；等待按 0.2s 片长回询执行器控制口（暂停 / 停止 / 用例移除），
服务端给出超大 `retry:` 也不会把任务挂起。

用例移除（A2 终审 F3）：执行中用例被删除（Redis 用例级中断标志）时，执行器按
INT-305 与 Realtime 会话同口径**静默收敛**——只记 INFO 日志，返回失败但不落结果行、
不发 `CASE_FAILED`、不提交评估；退避期间命中同一标志时，传输层仍以
`504 reconnect aborted by control signal` 结束本次读流，执行器收尾前再确认一次标志，
同样静默收敛。用例移除不是流式失败，不计入任务失败轮次。

失败文案（A2 终审 F2）：流式层失败（连接失败 / 空闲超时 / 时长上限 / 非 2xx /
非 JSON 帧）没有失败轮次，落库 `error_message` 与 TaskCase 终态文案取执行器聚合出的
具体原因（如 `流式错误[504]: idle timeout`），不再退化成「0 轮失败」；只有轮内业务
失败（有失败轮次、无传输级错误）才用「N 轮失败」。

`http+streaming=true`（chunked）走同一客户端：响应 `Content-Type` 不含
`text/event-stream` 时按「一行一个 JSON」分帧。

### 11.4 切轮口径

- 声明 `sentence_end_mapping`：该字段（在 `payload` 的 `data` 根上取值，同存量
  `api_driver_adapter` 口径）为 `true` 的事件结束一轮；
- 零声明（缺键 / 空串）：**一条 `message` 事件 = 一轮**；
- `session_end_mapping`（缺省 `session_finished`）为 `true` → 会话结束，未闭合的
  残轮作为最后一轮交出；
- `append_mode`：`true` 轮内文本拼接，`false` 取最后一条非空；
- 轮次输出 `rounds[i].output` 仍是 `{target_param: value}`（C0/C1），字段提取走
  `field_path`（C2），文本型字段按 `text` 兜底。

### 11.5 未做（边界）

- gRPC 接入见 §十（A1 / INT-1789，与本卡同批合入）；
- `AdapterProtocol` 未加 `sse` 成员：A2 没有协议级 vendor adapter base（传输与执行
  都在本卡新增件里），加成员会得到一个无人注册的死值；
- 音频输入推流与平台 frame/summary 实时流推送（SSE 是「一问多回、客户端只读」）；
- 前端协议页签（A3 / INT-1791）。

---

## 十二、proto 上传与符号解析端点（INT-1952 实施回写，2026-10-26）

A3（INT-1791，前端 gRPC 协议区块）的硬前置：gRPC 配置面此前只有**读取侧**
（执行期按 `meta.grpc.proto_object_key` 取 `.proto`），没有任何上传 / 符号解析端点，
前端拿不到 `proto_object_key` / `sha256` / `size`，也拿不到 service / method / 消息字段
供下拉。本端点补齐上传与符号解析。**执行期适配器（`grpc_adapter.py`）一行未改**，
`meta.grpc` 的读取侧键名不变。

| 项 | 位置 | 说明 |
|----|------|------|
| HTTP 端点 | `api_gateway/routes/api_bp.py` `POST /api/v1/apis/proto` | multipart 字段 `file`；静态段先于 `/{api_id}` 注册；权限 `api_config:create` |
| 网关应用层 | `api_gateway/application/services/api/api_command_service.py` `parse_proto()` + `.../proto_upload.py` | 只做预检与错误码映射；上传预检在调 RPC **之前** |
| 网关代理 / ACL | `grpc_proxies/api_config_proxies.py` `parse_proto`（`_attach_code` 透传业务码） | 不反向 import `api_test_service` |
| gRPC RPC | `shared/proto/api_test_service.proto` `APITestService.ParseProto` | pb2 / pb2_grpc 同批重生成 |
| 应用服务 | `api_test_service/application/api_proto_service.py` | 编译预算 + 并发限流 + 内容寻址落存储 + 符号表 |
| 符号枚举 | `api_test_service/.../transport/grpc_client.py` `CompiledProto.enumerate_services()` | 只读能力，复用 `load_compiled_proto` 的 sha 缓存 |
| 常量 | `shared/models/proto_limits.py` | `PROTO_MAX_BYTES` 等单一来源，网关与执行期同口径 |

### 12.1 HTTP 契约

```
POST /api/v1/apis/proto        multipart/form-data: file
权限：api_config:create（缺失 → 403）

200 data: {
  object_key: "oss://api-protos/<sha256>.proto" | "local://api-protos/<sha256>.proto",
  sha256:     "<64 位小写 hex>",          // 服务端对字节计算，客户端声明不参与
  size:       12345,                      // 同上
  services: [{ name, methods: [{
      name, method_kind,                  // unary / server_stream / bidi
      input_type, output_type,            // descriptor 全限定名，如 demo.Req
      input_fields, output_fields         // [{path, type, repeated}]
  }]}]
}
```

`object_key` 是 `storage.save_bytes(...)` 的**原样返回值**（带 scheme）。执行期
`_proto_bytes` → `load_bytes` → `_parse_path` 按 scheme 选介质，因此前端只需把它
原样写进 `meta.grpc.proto_object_key`。

### 12.2 gRPC 契约

```proto
rpc ParseProto(ParseProtoRequest) returns (ParseProtoResponse);

message ParseProtoRequest {
  string filename = 1;   // 只用于校验 / 报错文案，不进编译与存储
  bytes  content  = 2;
}

message ParseProtoResponse {
  bool   success = 1;
  string message = 2;
  string data    = 3;    // JSON 序列化上述 data 结构
  int32  code    = 4;    // 0=成功，400=内容类错误，503=存储不可用，500=意外内部错误
}
```

`code` 是**必须存在**的：网关代理异常默认回 `code=400`，没有该字段时「存储不可用」
会被压成 400，与「503 不被压成 400」的验收冲突。网关用 `_common._attach_code` 口径
透传（同 `ApiRmsSplConfigService` 各 Response 的先例）。

### 12.3 错误码（HTTP 状态由业务码决定，不是一律 400）

| 场景 | code / HTTP | message 示例 |
|---|---|---|
| 缺 `file` 字段 / 空文件 | 400 | `未收到 proto 文件` |
| 超过 `PROTO_MAX_BYTES` | 400 | `proto 文件超过 262144 字节上限（实际 N）` |
| 非 UTF-8 | 400 | `proto 文件不是 UTF-8 文本: ...` |
| 非法 import | 400 | `proto import 不在白名单内: [...]` |
| protoc 编译失败 / 超时 | 400 | `proto 编译失败（protoc 返回 N）` / `proto 编译超时` |
| 无 service / 无可用 method | 400 | `proto 中没有可调用的 service` |
| 权限缺失 | 403 | 网关 `require_permission` 直出 |
| 存储不可用 | **503** | `存储不可用: ...` |
| 其他意外异常 | 500 | `proto 解析失败: ...` |

`PROTO_MAX_BYTES` 超限的「实际 N」：网关 Content-Length 预检时是整个 multipart 包体的
长度上界，分块读取时是读到的字节数（`上限 + 1` 即拒）。

### 12.4 符号表枚举规则（前端直接消费，不另解析一套）

- **client-streaming-only 方法剔除**：执行期只支持 unary / server_stream / bidi
  （`METHOD_KINDS` 三值不变），吐出去前端下拉必然报错。只有 client-streaming 方法的
  service 也一并从结果里去掉；全部方法都被剔除时按「没有可调用的 service」报 400。
- **字段展开**到第 2 层（顶层 + 一层嵌套），`path` 用点号（`user.id`）。
- `map<k, v>` 把完整类型写进 `type`（如 `map<string, int32>`），`repeated=false`。
- enum 写枚举全名（`demo.Color`）且不展开。
- repeated message 记 `repeated=true` 后继续展开一层。
- `google.protobuf.*`（well-known types）只给类型名不展开。
- 自引用 / 递归在重复出现处截断（挡在 `ancestors` 集合上，防死循环）。
- `input_type` / `output_type` 写 descriptor 全限定名，与 `meta.grpc.service` 全名口径一致。

### 12.5 存储、限流与安全

- **内容寻址**：`category='api-protos'`、`key='<sha256>.proto'`。幂等 = 同 key 覆盖写，
  **不做 `exists()` 预检**（`storage.exists` 会吞异常回退本地副本，OSS 不可达时每次探活
  约 13s 且给出「看着成功」的假象，INT-1806 教训）。
- **写入一律 `allow_fallback=False`**（D1 / INT-1805）：OSS 不可用即抛
  `StorageUnavailableError` → `code=503`，不写本地降级目录、不吞错。
- **编译**：复用 `compile_proto`（大小 / UTF-8 / import 白名单 / protoc 全链路），端点只加
  ≤10s 编译预算与进程内并发上限（默认 2），同 sha 命中 `load_compiled_proto` 缓存不重编。
- **filename 安全**：端点不把客户端 filename 交给编译（`compile_proto` 会把 filename 拼进
  临时目录）。编译用 sha 派生文件名 `api_<sha256>.proto`（与执行期同口径），存储 key 用
  sha256；客户端 filename 只做 basename 归一 + ≤200 字符后进报错文案。
- **网关预检**：网关没有全局 body 上限，有 `Content-Length` 时按「上限 + 64 KiB multipart
  包体余量」先拒；无该头（chunked）时按块读到 `PROTO_MAX_BYTES + 1` 即拒。两条路都在调
  RPC 之前，超大文件不进内存、不进 gRPC。
- 上传内容不写日志明文（只记 `file` / `sha256` / `size` / service 名）。

### 12.6 明确不做 / 限制

- 不做 server reflection（A1 §十既定，`meta.grpc.reflection` 为真执行期直接抛错），
  端点不放行、不返回该字段。
- 不做多文件 / 跨包 import 包管理（只接受单文件 + `google/protobuf/*`），多文件 proto 会被
  白名单拒绝，UI 需在错误文案里提示。
- 不做 proto 版本历史 / 删除清理 / 灰度。
- **只保证单桶模式**：`api-protos` 未注册进多桶 `_buckets` 白名单
  （`shared/clients/oss_client.py`），多桶模式会 `ValueError`；docker compose 是单桶
  （`OSS_BUCKET_NAME=intelligent-audio-test`），线上不受影响。多桶需求另开卡。
- 前端接线归 A3（INT-1791），本端点只提供契约。

---

## 十三、A3（INT-1791）前端协议区块：控件 ↔ `meta` 键映射与校验口径

> 状态：**文档基线已补（INT-1954，2026-10-26），A3 实施后回写**。本节只钉「前端控件 ↔ `apis.meta` 键」的归属与校验口径，不重开 §三 的裁定；A3 只改 `wiring/react` 前端树，不动本节引用的后端契约。
> 修正（INT-1955，2026-10-26）：§13.3 归属裁定三 回收「SSE 复用 `body_template`」的错误口径（按 A2 实现改为 SSE 下不生效）；§13.1 补「A2 合入取并集」的可用矩阵集成口径。其余条款未变。
> 编号说明：本节成稿时取的是当时末节（§十）之后，故原写作 §十一 / §11.1–§11.5。集成时按实际末节顺延：A1 = §十、A2（INT-1790）= §十一 / §11.x、proto 上传端点（INT-1952）= §十二 / §12.x，**本节 = §十三 / §13.x**；§13.3 / §13.4 中对 A2 `meta.sse` 键表的引用已同步改为 §11.2。引用请优先用标题锚点「A3 前端协议区块」。

### 13.1 归属与边界（不新增实体 / 页签）

- 协议区块在**请求模板页签（`request`）内**按 `apis.protocol` 显示；五页签骨架（basic / request / response / output / mapping）不变，不新增页签、菜单、列表分类或独立页面。协议是被测 API 的属性（§一），四协议复用同一编辑弹窗。
- 切协议时各协议组各自持有草稿，切回不丢；保存时**只写当前协议组声明的键**。
- `meta` 的写侧是**整块 replace**（`api_test_service/application/api_crud_service.py:531-543`，仅对 `meta.api_keys` 做保留特判），没有子对象级合并。因此前端必须以 GET 回来的 `meta.grpc` / `meta.sse` 为 base，逐子键覆盖，清空即删该子键，**不得整块重建**——否则切协议或换页签会静默冲掉别的键（A3 最大技术风险）。
- 可用矩阵：前端置灰表必须与后端 `AVAILABLE_PROTOCOL_STREAMING`（`shared/models/common_enums.py:188-194`）**同一张表**，禁止前端自行放宽或收紧。A1 落地后 `grpc+false` / `grpc+true` 已放行；A2 本批合入后 `sse+true` / `http+true` 一并放行，即六组合全部可写可执行。
- **可用矩阵合入口径（INT-1955 补，2026-10-26）**：A2（`63bc84b95`）该表只有 `{http+false, websocket+true, sse+true, http+true}`，**不含 A1 的 `grpc+false` / `grpc+true`**——A1 的合并提交（`26c1f7beb`）不是 A2 的祖先，A2 侧同一文件是「A1 之前」的版本（`AdapterProtocol.GRPC` 也在该侧被删回）。因此 **A2 合入 V9.7.31 时目标表是六组合并集**（`http+false` / `http+true` / `websocket+true` / `sse+true` / `grpc+false` / `grpc+true`），集成必须**取并集**，不得用 A2 侧整块覆盖：覆盖会静默删掉 gRPC 两种，`is_protocol_streaming_available()` 随即对 grpc 返回 False、写侧 400。前端 `WRITABLE_COMBINATIONS` 同样取该六组合。
- 读侧脱敏保持现状：`_api_to_dict` 只剥 `meta.api_keys`（`api_crud_service.py:306-312`），`meta.grpc.metadata` 的鉴权值仍**明文回显**；前端只能提示「尚未脱敏」，不得假定已脱敏（后端补丁归 INT-1953）。

### 13.2 `meta.grpc` 键表与校验

| 键 | 类型 / 约束 | 前端控件 | 校验落点（代码） |
|---|---|---|---|
| `proto_object_key` | 必填；storage key，内容寻址 `api-protos/<sha256>.proto` | 上传成功后自动填入，只读 | 执行期必填：`grpc_adapter.py:91-93`；上传端点归 INT-1952 |
| `proto_sha256` | 64 位小写十六进制 | 上传后自动填入，只读 | 声明与内容不符即报错：`grpc_adapter.py:119-126` |
| `proto_size` | 整数，≤ 256 KiB | 上传后自动填入，只读 | 声明与实际不符即报错：`grpc_adapter.py:115-118` |
| `service` | 必填；proto 内 service 全名 | 下拉（来自上传端点返回的符号表） | `_REQUIRED_CONFIG_KEYS`：`grpc_adapter.py:48,84` |
| `method` | 必填；方法名 | 下拉，随 `service` 联动 | 同上 |
| `method_kind` | `unary` / `server_stream` / `bidi`，须与 descriptor 一致 | 下拉；默认取符号表推断值，用户改动需二次确认 | 非法值即报错：`grpc_adapter.py:94-97` |
| `metadata` | 对象；键**必须小写**，值不含 CR/LF，支持 `{{placeholder}}` | 键值表；鉴权键（`authorization` / `x-api-key` / `api-key`）用密码控件 | `validate_metadata`：`adapters/transport/grpc_client.py:305-320` |
| `deadline_ms` | 正整数；缺省 = `apis.max_timeout × 1000`（列缺省 30 → 30000） | 数字输入，placeholder 显示缺省 | `grpc_adapter.py:143-151` |

- **不做**：server reflection（A1 明确不做）、多文件 / 跨包 proto bundle（沿用 `google/protobuf/` import 白名单）。
- proto 上传端点（`POST /api/v1/apis/proto`）归子卡 **INT-1952**；端点未上线前控件标 `// 待接线` 并在 UI 明示「协议文件上传接口尚未上线」，**不得用假 `object_key` 冒充成功**。
- 后端 **`meta.grpc` 写侧校验目前缺失**（`api_crud_service` 无该分支），补丁归子卡 **INT-1953**；A3 的前端校验镜像执行期规则，不因后端未校验而放宽。

### 13.3 `meta.sse` 键表：沿用 A2，不重复抄写

键表以 A2（INT-1790）**§11.2** 为唯一权威，本节不复制。A2 已于本批合入 V9.7.31（§十一），键表以 §11.2 为准；键名或范围若有变化，本节的控件映射同批返工，不得出现双口径。

- 键集合（以 §11.2 为准）：`event_name_field` / `params` / `reconnect_enabled` / `max_reconnect_attempts` / `retry_ms` / `idle_timeout_ms` / `max_duration_ms`；未知键一律 400；显式 `null` 与「键未提交」同义（执行侧回落缺省，禁止「配置能存、执行不可用」）。
- 前端控件形态：输入框（`event_name_field`）、JSON 键值表（`params`，支持 `{{placeholder}}`）、开关（`reconnect_enabled`）、数字（其余四项，范围与缺省按 §11.2；`reconnect_enabled=false` 时重连相关控件禁用）。
- **归属裁定一**：句子 / 会话结束标记**不进 SSE 区块**——`sentence_end_mapping` / `session_end_mapping` 的所有权在**响应解析页签**（轮次切分见 §4.1，INT-1778 已声明）；SSE 区块只做只读提示。
- **归属裁定二**：data 取值路径属 `algorithm_api_params(direction=output).field_path`（C2，见 §4.2），不写进 `meta.sse`（写成键即触发未知键 400）。
- **归属裁定三**：SSE 复用 HTTP 组的 `method` / `headers`，所有权在 **HTTP 组**；SSE 区块可见但不重复声明同名键。**`body_template` 在 SSE 下不生效、前端不显示**，请求载荷统一走 `meta.sse.params`（用例 `params` 优先；GET → query，非 GET → JSON body）。
  - 代码依据（A2 `63bc84b95`，`api_test_service/core/stream_session_executor.py`）：`_render_request_body`（`:446-466`）在 `protocol == 'sse'` 时直接返回 `meta.sse.params`（用例 `params` 优先），**永远不读 `meta.body_template`**；真正复用的只有 `meta.method`（`:111-112`，缺省 GET）与 `meta.headers`（`_resolve_headers` `:417-444`）。查询 / 载荷的分流在传输层：`GET` → `params`（query），非 GET → `json`（`adapters/transport/sse_client.py:179-183`）。

### 13.4 校验口径（前后端同源，前端不得放宽）

前端逐字段拦截并在控件上报错，拦截项与后端同口径：

1. 必填缺失（`proto_object_key` / `service` / `method` / `method_kind`）；
2. `method_kind` 不在三值内；
3. `deadline_ms ≤ 0`；
4. `metadata` 键含大写、值含 CR/LF；
5. SSE 的 `retry_ms` / `max_reconnect_attempts` / `idle_timeout_ms` / `max_duration_ms` 越界（范围见 §11.2）；
6. 写表外键（未知键一律提交前拦截；后端侧为 400）。

### 13.5 声明文件（A3 实施落位）

| 层 | 文件 | 职责 |
|---|---|---|
| 前端 Domain | `frontend-react/src/domain/models/apiProtocol.ts` | `WRITABLE_COMBINATIONS` 与后端 `AVAILABLE_PROTOCOL_STREAMING` 同表 |
| 前端 Application | `frontend-react/src/features/test-execution/modals/api-edit-dialog-model.ts` | 协议组草稿、`meta.grpc` / `meta.sse` 子对象级 merge、字段级校验 |
| 后端（只读参考，A3 不改） | `api_test_service/infrastructure/adapters/grpc_adapter.py` | `meta.grpc` 唯一读取方与执行期校验（本节键表来源） |

> 前端两文件位于 **`wiring/react` 树**（V9.7.31 本仓库无 `frontend-react/`），A3 交付以该树 HEAD 为准；本节只声明契约归属，不表示实施已完成。
