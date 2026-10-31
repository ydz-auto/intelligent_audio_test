# API 参数策略化改造 — 规格（spec）

> 状态：待评审
> 适用范围：`algorithm_service` / `api_gateway` / `api_test_service` / `evaluation_service` / `task_service` / `report_service` / `device_service` / `e2e_test_service` / `frontend-react`
> 前置文档：[18_设备参数和API参数绑定方案.md](../../功能设计文档/08_算法配置/智能语音算法配置适配/18_设备参数和API参数绑定方案.md) §10

## 1. 背景与目标

算法「API 参数」原先按 `algorithm_type` 全局声明（`api_id IS NULL` 的默认层），同一算法类型下所有 API 共用一份，导致不同协议 / 不同响应结构的 API 互相串味。本轮把 API 参数与 `source='api'` 的评估映射改为**实例作用域**：

- 新增可复用**参数策略**（`param_profiles` + `param_profile_params` + `param_profile_mappings`）；
- API 实例通过 `api_param_bindings` **引用**一份策略；
- 实例可对策略做**覆盖**（`algorithm_api_params` / `param_mappings` 中 `api_id = X` 的行）；
- 解析优先级恒定为：**实例覆盖 > 策略 > 空（显式告警）**；
- 彻底废弃 `api_id IS NULL` 的算法类型级默认层（迁移后软删）。

### 非目标

- 物理侧（`algorithm_device_params`、`DriverRegistry`、driver 语义声明）本轮不动；
- 不按 `DeviceType` / `protocol` / `streaming` 再派生参数作用域（已论证否决）。

## 2. 已落地（Phase 1，本规格的前置）

| 层 | 文件 | 内容 |
|---|---|---|
| 契约 | `shared/proto/algorithm_service.proto` | `AlgorithmDefinitionService` 新增 5 个写 RPC（Save/Clone/Delete ParamProfile、BindApiParamProfile、SaveApiScopeOverrides）；`AlgorithmQueryService` 新增 2 个读 RPC（List/GetParamProfile）；pb2/grpc 已按 Protobuf 7.35.1 重生成 |
| 模型 | `algorithm_service/infrastructure/persistence/models/algorithm_models.py` | `ParamProfile` / `ParamProfileParam` / `ParamProfileMapping` / `ApiParamBinding`（无 ORM relationship，按 id 显式查询） |
| 迁移 | `scripts/migrations/202610/add_param_profiles_scope.py` | 建表 → 按 `algorithm_type` 生成 `default` 策略 → 复制默认层参数与映射 → 回填绑定 → 软删默认行；`--apply` / `--rollback` / dry-run 默认 |
| 引导 | `docker/db_bootstrap_entrypoint.py` | ㊾ 之后、㊽ ANALYZE 之前执行迁移（`--apply`） |
| 解析 | `algorithm_service/infrastructure/persistence/config_cache.py` | `get_api_params` / `get_param_mapping` / `_scoped_mapping_buckets` / `_get_evaluation_mappings` 改为「策略 + 实例覆盖」；`api_id=None` 返回空 |
| 读 Handler | `algorithm_service/application/handlers/param_profile_handlers.py`、`algorithm_service/interfaces/grpc/algorithm_query_servicer.py` | 策略读 RPC |
| 写 Handler | `algorithm_service/interfaces/grpc/mixins/param_profile_mixin.py` | 策略写 RPC，成功后全量失效缓存 |
| 仓储 | `algorithm_service/infrastructure/persistence/_param_profile_repositories.py` | 策略 CRUD + 绑定 + 覆盖的原子落库 |
| 网关 | `api_gateway/routes/algorithm_bp.py`、`api_gateway/application/services/algorithm/algorithm_profile_service.py`、`api_gateway/infrastructure/grpc_proxies/algorithm_proxies.py` | 7 条路由：`/param-profiles`(GET/POST)、`/param-profiles/{id}`(GET/PUT/DELETE)、`/param-profiles/{id}/clone`、`/api-scope/{api_id}/binding`、`/api-scope/{api_id}/overrides` |

已删除：`api_gateway/application/services/algorithm/algorithm_api_scope_service.py`（网关侧非原子差集写）。

## 3. 现状核对结论（读路径）

| 调用点 | 位置 | 是否带 api_id | 结论 |
|---|---|---|---|
| API 执行道 | `api_test_service/core/api_task_runner.py:429,454` | 是 | 无需改 |
| 评估轮数据 | `evaluation_service/domain/services/evaluation_service/round_data_builder.py:58` | 是 | 无需改 |
| 任务详情输出字段 | `task_service/application/task/task_query_service.py:394,397` | 否 | **需改**（`GetOutputFields` 已支持 api_id，只是未传） |
| 任务详情字段映射 | `task_service/application/task/task_query_service.py:391` | 否 | **需改**（`GetFullFieldMapping` 契约缺 api_id） |
| 报告快照 | `report_service/application/services/report_task_generator.py:564` | 否 | **需改**（同 `GetFullFieldMapping`） |
| e2e ACL | `e2e_test_service/infrastructure/acl/algorithm_acl_repository_impl.py:47,53,59` | 否 | 需加 api_id 透传（e2e 调用方仍可不传，行为不变） |
| 物理 extra config | `device_service/infrastructure/acl/algorithm_query_acl_repository.py:229,275` | 否 | **不改**：消费方 `device_result_collector.py:359` 只用 `query_fields`，其来源是 `param_type in (direction, language)`；现存 API 参数 `param_type` 为 `text/number/json`，接入策略后无实际影响 |
| 通用 base_executor | `shared/infrastructure/base_executor/_db_mixin.py:297,305`、`_results_mixin.py:203` | 否 | **不改**：物理执行链路，只丢 `source='api'` 行；物理无 API 输出声明 |
| 用例参数提取 | `algorithm_service/application/queries/case_parameter_queries.py:76,110` | 否 | **不改**：物理/旧链路，接入策略后 API 输入参数为空，语义上等价于「无 API 输入」 |

## 4. 需求与决策

### R1 读路径作用域补齐（最高优先，防回归）

**R1.1 `GetFullFieldMapping` 支持 api_id（契约变更）**

- `shared/proto/algorithm_service.proto`：`GetFullFieldMappingRequest` 增加 `int32 api_id = 2;`（0 表示未指定，与既有 `_optional_api_id` 口径一致）。
- 重生成 `shared/proto/algorithm_service_pb2.py`、`algorithm_service_pb2_grpc.py`（必须与仓库既有 7.35.1 生成结果哈希自检一致后再覆盖）。
- `algorithm_service/interfaces/grpc/algorithm_query_servicer.py:376` `GetFullFieldMapping` → 透传 `_optional_api_id(request)`。
- `algorithm_service/application/queries/result_field_mapping_queries.py` `get_field_mapping(algorithm_type, api_id=None)`：新增参数并透传到 `config_cache` 的 `get_api_params` / `get_param_mapping`。
- `shared/clients/_grpc_algo_audio.py:369` `algo_get_full_field_mapping(algorithm_type, api_id=None)`：用 `_with_api_scope` 组装请求。
- `report_service/infrastructure/clients/grpc_clients.py:202` `_grpc_algo_get_field_mapping(algorithm_type=None, api_id=None)` 透传。

**R1.2 任务详情按 api_id 解析**

- `task_service/infrastructure/acl/algorithm_acl_dimension_query_tx_mixin.py:127,136`：`algo_get_full_field_mapping(algorithm_type, api_id=None)`、`algo_get_output_fields(algorithm_type, device_type=None, api_id=None)`。
- `task_service/application/task/task_query_service.py:381-398`：
  1. 先聚合本次任务所有结果行的 `api_id`（`{r.get('api_id') for r in results if r.get('api_id')}`）；
  2. 无 api_id → 单次 `api_id=None` 调用（保持物理任务行为）；
  3. 有 api_id → 对每个 api_id 调一次，按 `code`（输出字段）与 `target_param`（映射）取**并集去重**后合并；
  4. `device_output_fields` 保持 `algorithm_type` 级（设备声明不受本轮影响）。

**R1.3 报告快照按 api_id 解析**

- `report_service/application/services/report_task_generator.py:545` `_collect_field_mappings_snapshot`：签名增加对 `results` 中 `api_id` 的聚合；快照键仍为 `{algorithm_type: {result, reference}}`（不破渲染契约），值改为「该算法类型下涉及的全部 api_id 的并集」；无 api_id 时退回 `api_id=None`。

**R1.4 e2e ACL 透传**

- `e2e_test_service/infrastructure/acl/algorithm_acl_repository_impl.py`：`get_api_params` / `get_param_mapping` / `get_field_mappings` 增加 `api_id: Optional[int] = None` 并透传；现有调用点不传，行为不变。

**R1.5 空声明显式告警**

- `config_cache.get_api_params` 在 `api_id` 有值时若「策略为空且无覆盖」→ 写 `WARNING`（含 `algorithm_type` / `api_id`），不再静默返回 `[]`。

### R2 WS/gRPC 首帧模板可配置

- 配置位：`apis.meta.first_frame`（JSON：`{"enabled": bool, "template": "<raw json with {{placeholders}}>"}`），随 `apis` 一起保存。
- 渲染：`api_test_service/infrastructure/adapters/transport/realtime_ws_client.py:158-175` 由固定 `{"type":"session.update","session":<session_config>}` 改为「有 `meta.first_frame` 用之，否则回落现状」。
- 校验（写侧）：`first_frame.template` 中 `{{x}}` 必须 ⊆ 该 API 所绑定策略/覆盖已声明的 `direction='input'` 参数 `code` 集合，否则 400。
- 透传：`ExecutionLane` 仍只由 `apis.streaming` 推导（INT-1799），`meta.first_frame` 不参与。

### R3 前端

前端仓库 `D:\00_code\V9.7.31-WIRING-REACT\Intelligent-Audio-TEST\frontend-react\src`：

- 算法编辑弹窗（`features/algorithm-config/mutate/algorithm-mutate-sheet.tsx` + `params-table.tsx`）：移除「API 参数」页签与 `source=api` 映射项；设备参数保持不动。
- API 编辑弹窗（`features/test-execution/modals/api-edit-dialog.tsx`）：
  - 新增「参数配置」页签：绑定策略（下拉：本算法类型的策略列表 + 克隆 / 另存为）；
  - 「输出字段」「映射」从只读改为可编辑（写实例覆盖，`PUT /api-scope/{api_id}/overrides`）；
  - 移除「算法类型级声明，本类型下所有 API 共用」横幅。
- 新增策略管理入口（列表 / 新建 / 编辑 / 克隆 / 删除），表单形态对齐 `features/evaluation/mutate/api-section.tsx` 的「所需输入配置 / 输出字段配置」`useFieldArray`。
- DTO 层：`infrastructure/dto/algorithm-config.dto.ts` 新增策略相关 DTO；`domain/models/algorithmConfig.ts` 去掉 `apiParams` 语义、新增 `paramProfileId` / `apiScopeOverrides`；保持「只有 Infrastructure 层知道 snake_case」。

### R4 测试与清理

- 单测：
  - `tests/unit/test_param_profile_resolve.py`：覆盖「实例覆盖 > 策略 > 空」三档 + `api_id=None` 返回空 + WARNING；
  - `tests/unit/test_param_profile_crud.py`：策略 save/clone/delete/bind/overrides 的原子性与唯一键冲突；
  - `tests/unit/test_param_profile_migration.py`：迁移幂等、dry-run、`apis` 跨库跳过回填、回滚；
  - 回归：`tests/unit/test_int1756_api_id_scope.py`、`tests/unit/test_int1757_api_id_call_sites.py`。
- 清理死代码：`api_gateway/application/services/algorithm/algorithm_common.py:61-70`（按 `param_type == 'device'/'api'` 分类，实际 `param_type` 是值类型，全仓无引用）。

### R5 策略整份保存的字段语义（INT-2268 写死）

`POST /param-profiles`（新建）与 `PUT /param-profiles/{id}`（更新）共用 `ParamProfileSaveRequest`，
字段级语义如下，网关 `model_dump(exclude_none=True)` → 仓储 `save()` 同口径：

| 字段 | 缺失 / 显式 `null` | 传值 | 说明 |
|---|---|---|---|
| `name` / `description` / `status` | 更新时保持原值 | 覆盖 | 新建时缺省取 schema 默认（`status=online`） |
| `config` | **保持原 `config_snapshot`**（不清空） | 对象整体覆盖；`{}` = 清成空快照（存 `'{}'`） | 编辑名称/描述/状态不会再把快照写成 NULL |
| `params` / `mappings` | 等同 `[]` → **整份替换**，未提交的既有行按自然键软删 | 整份替换 | 缺省即清空，前端必须提交完整行集 |

快照的 `config_snapshot` 当前只做详情回显与「新建 API 时套用」，运行期解析不消费（见走查 P3）。

## 5. 验收标准

1. `python -c "import algorithm_service.interfaces.grpc.algorithm_query_servicer"`、`import api_gateway.routes.algorithm_bp`（52 路由）通过；
2. 迁移脚本 dry-run 输出与 `--apply` 后行数一致；`api_id IS NULL` 的 `algorithm_api_params` / `param_mappings(source='api')` 全部 `deleted=true`；
3. 同一算法类型下两个 API 绑定不同策略时，`GetOutputFields(api_id=A)` 与 `GetOutputFields(api_id=B)` 结果互不包含；
4. 任务详情 / 报告快照在 `results.api_id` 存在时输出字段非空，且只含对应 API 的声明；
5. 前端算法编辑弹窗无 API 参数页签；API 弹窗可绑定策略并编辑输出字段。

## 6. 风险与回滚

| 风险 | 处置 |
|---|---|
| proto 重新生成版本漂移 | 先在临时目录重生成并与仓库文件比对哈希，一致才覆盖 |
| 报告快照契约被破坏 | 快照键保持 `algorithm_type`，只改取值来源（并集） |
| 存量环境未跑迁移 | `get_api_params(api_id=None)` 返回空 + WARNING，不静默错值 |
| 迁移误删默认层 | `--rollback` 反向恢复 `deleted=false` 并删除策略表数据 |
