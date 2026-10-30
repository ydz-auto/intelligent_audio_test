# API 参数策略化改造 — 任务清单（tasks）

> 对应 [spec.md](./spec.md)。Phase 1 已完成，下列为剩余工作。
> 每项完成后须执行「验证」列的命令或断言。

## Phase 2 — R1 读路径作用域补齐（阻塞发布，最高优先）

| # | 任务 | 文件 | 变更 | 验证 |
|---|---|---|---|---|
| [x] T2.1 | 契约：`GetFullFieldMappingRequest` 加 `api_id` | `shared/proto/algorithm_service.proto` | `optional int32 api_id = 2;` | 临时目录重生成，pb2/grpc 与仓库现有文件哈希一致（旧契约部分） |
| [x] T2.2 | 重生成 pb2 / pb2_grpc | `shared/proto/algorithm_service_pb2.py`、`algorithm_service_pb2_grpc.py` | `grpcio-tools` 原地生成（grpc 文件哈希与仓库一致） | `HasField('api_id')` 为 True，未传时为 False |
| [x] T2.3 | 读 Handler 加 api_id | `algorithm_service/application/queries/result_field_mapping_queries.py` | `get_field_mapping(algorithm_type, api_id=None)`；api 声明/映射走配置缓存「策略 + 覆盖」，未传 api_id 保留算法级仓储口径 | import 冒烟 + 单测 |
| [x] T2.4 | Servicer 透传 | `algorithm_service/interfaces/grpc/algorithm_query_servicer.py:376` | 传 `_optional_api_id(request)` | import 冒烟 |
| [x] T2.5 | 客户端封装 | `shared/clients/_grpc_algo_audio.py:369` | `algo_get_full_field_mapping(algorithm_type, api_id=None)`，用 `_with_api_scope` | import 冒烟 |
| [x] T2.6 | 报告客户端 | `report_service/infrastructure/clients/grpc_clients.py:202`、`report_service/{domain,infrastructure}/acl/algorithm_acl_repository.py` | 三层签名加 `api_id` 透传 | import 冒烟 |
| [x] T2.7 | 任务详情 ACL | `task_service/infrastructure/acl/algorithm_acl_dimension_query_tx_mixin.py:127,136` | 两个方法加 `api_id` 透传 | `import task_service.application.task.task_query_service` |
| [x] T2.8 | 任务详情合并 | `task_service/application/task/task_query_service.py` | 聚合 `results` 的 `api_id`；逐个调用并按 `param_code` / `source_param` 并集去重；无 api_id 时单次 `None` | `_merge_field_mappings` / `_merge_output_fields` 冒烟 |
| [x] T2.9 | 报告快照合并 | `report_service/application/services/report_task_generator.py` | 快照键保持 `algorithm_type`，值取该类型下全部 api_id 并集 | import 冒烟 |
| [x] T2.10 | e2e ACL 透传 | `e2e_test_service/infrastructure/acl/algorithm_acl_repository_impl.py` | 三方法加 `api_id: Optional[int] = None` | import 冒烟 |
| [x] T2.11 | 空声明显式告警 | `algorithm_service/infrastructure/persistence/config_cache.py` | 「有 api_id 但策略空且无覆盖」/「未带 api_id」写 WARNING；新增 `get_source_mappings` 跨桶取输出映射 | import 冒烟 |

> 明确不改（见 spec §3）：`device_service` extra config、`shared/infrastructure/base_executor/*`、`case_parameter_queries`。理由为物理链路的 `query_fields`/`case_fields` 来源是 `param_type in (direction, language)`，现存 API 参数值为 `text/number/json`。

## Phase 3 — R2 首帧模板

| # | 任务 | 文件 | 变更 | 验证 |
|---|---|---|---|---|
| [x] T3.1 | 现状核对 | `realtime_ws_client.py:158-175`、`gateway/schemas/api.py:69,129,152` | `meta` 在网关闭环为自由 dict（可透传），运行时 `meta.session_config` 与用例级 session 合并 | 核对结论：`meta.first_frame` 无需新增 DTO 字段 |
| [x] T3.2 | 渲染器 | `realtime_session_executor.py`（`_build_first_frame` + `_render_placeholders`）、`realtime_ws_client.py#pre_process`、`realtime_adapter_base.py#pre_process` | 有 `meta.first_frame` 用之，否则回落 `session.update` | 冒烟：嵌套占位符渲染为 `{'a': '1', 'b': [{'c': 'z'}]}` |
| [x] T3.3 | 写侧校验 | `api_gateway/application/services/api/api_command_service.py` | 结构 + 合法 JSON + `{{x}}` ⊆ 已声明输入 `code`（未绑定策略时跳过子集校验） | 冒烟：非法 JSON 返回 400 文案 |
| [x] T3.4 | 网关 DTO | `api_gateway/schemas/api.py` | 已确认 `meta: Dict[str, Any]` 直通，无需改 schema | 保存/回读一致 |

## Phase 4 — R3 前端

| # | 任务 | 文件（`D:\00_code\V9.7.31-WIRING-REACT\...\frontend-react\src`） | 变更 | 验证 |
|---|---|---|---|---|
| [x] T4.1 | 算法弹窗移除 API 参数 | `features/algorithm-config/mutate/algorithm-mutate-sheet.tsx`、`params-table.tsx`、`param-scope-chips.tsx` | 去掉「API」chip 与 API 参数区；设备/用例保持 | 页面无 API 参数页签 |
| [x] T4.2 | API 弹窗参数页签 | `features/test-execution/modals/api-edit-dialog.tsx` | 新增「参数配置」：绑定策略、克隆/另存为；输出字段与映射改为可编辑 | 绑定后保存，回读一致 |
| [x] T4.3 | 策略管理入口 | 新增 `features/algorithm-config/param-profiles/*` | 列表/新建/编辑/克隆/删除，表单对齐 `features/evaluation/mutate/api-section.tsx` | 走查 5 个操作 |
| [x] T4.4 | DTO / Domain | `infrastructure/dto/algorithm-config.dto.ts`、`domain/models/algorithmConfig.ts` | 新增策略 DTO；`paramProfileId` / `apiScopeOverrides`；snake_case 仅留在 Infrastructure | `tsc --noEmit` 通过 |

## Phase 5 — R4 测试与清理

| # | 任务 | 文件 | 变更 | 验证 |
|---|---|---|---|---|
| [x] T5.1 | 解析优先级单测 | `tests/unit/test_param_profile_resolve.py`（新建） | 覆盖 / 策略 / 空三档 + `api_id=None` + WARNING | `pytest tests/unit/test_param_profile_resolve.py -q` |
| [x] T5.2 | 策略 CRUD 单测 | `tests/unit/test_param_profile_crud.py`（新建） | save/clone/delete/bind/overrides 原子性与唯一键 | 同上 |
| [x] T5.3 | 迁移单测 | `tests/unit/test_param_profile_migration.py`（新建） | dry-run / 幂等 / 跨库跳过 / rollback | 同上 |
| [x] T5.4 | 回归 | `tests/unit/test_int1756_api_id_scope.py`、`test_int1757_api_id_call_sites.py` | 保持通过 | `pytest tests/unit -q -k "int1756 or int1757"` |
| [x] T5.5 | 死代码清理 | `api_gateway/application/services/algorithm/algorithm_common.py:61-70` | 删除无引用的 `_serialize_algorithm` 分类逻辑 | 全仓 grep 无引用 |

## Phase 6 — 验收补齐（读路径复核后新增）

| # | 任务 | 文件 | 变更 | 验证 |
|---|---|---|---|---|
| [x] T6.1 | 用例参数提取带 api_id | `algorithm_service/application/queries/case_parameter_queries.py` | `case_config['api_id']` → `get_api_params(api_id)` / `get_param_mapping(..., 'evaluation', api_id)`；无 api_id 时返回空且不触发 WARN | `tests/unit/test_case_params_api_scope.py` |
| [x] T6.2 | 评估提交/重评补传 api_id | `api_test_service/core/{api_session_executor,stream_session_executor,api_executor,api_result_processor,evaluation_submitter}.py`、`evaluation_service/.../reevaluation_executor.py`、`reevaluation_service._build_case_info` | `full_case_params` 携带 `api_id`（API 结果取 test_results.api_id） | 同上 + 回归 |
| [x] T6.3 | 物理链热路径去噪 | `shared/infrastructure/base_executor/_results_mixin.py`、`_db_mixin.py`、`config_cache.get_algorithm_params` | 不再把 api params 并入 device（每用例一次 `GetApiParamsList(None)` + WARN） | `test_int1666` 调用数 8 → 10（策略 +2，与算法数无关） |
| [x] T6.4 | 潜伏 RPC 补 api_id | `ExtractResultFields` / `GetTimelineFields` / `BuildApiRequestData`（proto + pb2 + servicer + 客户端） | `optional int32 api_id` 透传到输出声明解析；顺带修正三处 servicer 参数错位（`algorithm_type` 未传） | import 冒烟 + `HasField('api_id')` |

## 执行顺序

1. T2.1 → T2.2（契约先行，避免后续改动夹带重新生成）
2. T2.3 → T2.6（服务端与客户端链路）
3. T2.7 → T2.10（消费方）
4. T2.11 → T5.1 → T5.4（告警与回归）
5. T3（需先 T3.1 核对）
6. T4（与后端可并行，依赖 T2 的接口定稿）
7. T5.2 / T5.3 / T5.5

## 验收（合并自 spec §5）

- `import` 冒烟：servicer、`api_gateway.routes.algorithm_bp`（52 路由）、`task_query_service`、`report_task_generator`、e2e ACL 全部可导入；
- 迁移 dry-run 与 `--apply` 行数一致，默认层全部软删；
- 两个 API 绑定不同策略时输出字段互不包含；
- 任务详情 / 报告快照在 `results.api_id` 存在时非空且仅含对应声明；
- 前端算法弹窗无 API 参数；API 弹窗可绑定策略并编辑输出字段。
