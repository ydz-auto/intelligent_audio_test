# 任务结果 Cherry-Pick 挑选合并功能设计文档

## 1. 文档说明

### 1.1 目标

从已执行的任务中按条件挑选执行结果（如：某台设备上某模型相关用例的执行结果），多个挑选结果可再合并，生成一个新的任务与报告。新任务与新报告作为一等公民，支持现有任务与报告的全部功能。

### 1.2 需求来源

负责人口头需求（2026-10-14）原话：

> cherry pick 可以从已经执行中的任务挑选出 某个设备的模型用例的执行结果 与另外一个任务的cherry pick 合并 啥的 生成一个新的任务 报告 这个新的任务 报告 等 支持 现有 的所有任务 和报告功能

同日追加（交互模型）：「cherry pick 出的 数据放在一个类似于购物车里，cherry pick 完 下单合并？」

即：挑选结果进入**购物车**（可跨任务连续加购），最后对购物车**下单合并**生成新任务与报告。按「口头需求落文档」纪律回写本文档，标注裁定日期。

追加口径（2026-10-14）：

- 下单出口扩展：「pick 出异常用例 然后 放购物车 然后 再 重新执行 或者评估」——购物车下单除合并生成新任务外，还可直接发起**重新执行**/**重新评估**（§3 出口 b/c）。
- 页面文案：**cherry pick 一律用中文**（「挑选」等），页面不出现 Cherry-Pick 字样（接口路径除外；任务分类标识见 §5.4，`task.type` 字段已删除，不使用 type=cherry_pick）。
- 边界澄清（负责人 2026-10-14「这俩cherry pick 不是一个功能 别混了」）：本功能与「测试结果人工复核」（01_测试执行/测试结果人工复核功能设计文档.md，可人工设置用例执行/评估状态）是**两个独立功能，不得混合**。

### 1.3 文档关系

| 文档 | 职责 |
| --- | --- |
| [任务管理功能设计文档](任务管理功能设计文档.md) | 任务列表、执行、详情总设计 |
| [任务合并功能设计文档](任务合并功能设计文档.md) | 整任务级合并（现有能力，与本功能的区分见 §2） |
| [任务发布功能设计文档](任务发布功能设计文档.md) | 发布三冻结口径；cherry-pick 任务可发布 |
| [报告管理功能设计文档](../05_报告管理/报告管理功能设计文档.md) | 报告生成/查看/对比/导出；cherry-pick 任务报告走现有链路 |
| [status_fields_relationship](status_fields_relationship.md) | 执行状态/评估状态双状态口径 |

## 2. 与「任务合并」的关系（重要区分）

| 维度 | 任务合并（现有，V9.7.31 实现） | Cherry-Pick 挑选合并（本功能） |
| --- | --- | --- |
| 挑选粒度 | 整任务（全部结果） | 执行结果级（按设备/用例/标签/状态等条件挑选） |
| 源任务处置 | 容器任务持有 `TaskMergeRelation` 关系展开引用源结果；源任务标记 `merged` | **源任务保持原样不动**（未挑中的结果仍留在源任务），容器任务以专有关系表存在性判定（§5.4） |
| 结果持有 | **不搬家**——`test_results` 原地不动，报告/详情按关系展开引用取数（report_data_builder 按 TaskMergeRelation 展开源任务取结果） | 挑中的结果**禁止搬家改挂**（源任务还要用）——引用（方案 A，评审倾向）或复制，见 §5.1 |
| 组合使用 | 合并后的任务可独立执行与统计 | cherry-pick 生成的任务可再被合并/挑选/发布 |

> 口径修正（2026-10-14 前向可行性评审）：本表此前沿用 V9.7.10 旧实现描述「test_results 改挂 task_id（搬家语义）」；V9.7.31 任务合并实际为**容器任务+关系展开引用+源任务标记 merged**，不搬结果。修正后 §5.1 引用方案在主库有直接实现先例。另注：任务合并功能设计文档.md 本身仍是 V9.7.10 旧内容（含已失效的 backend/blueprints 代码段），滞后回写另行开卡处理（见 §13）。

## 3. 核心流程

```text
1. 挑选=加购：在任务（一个或多个）的结果列表按条件筛选（§4），勾选「加入购物车」
   -> 跨任务连续挑选，统一进入购物车（负责人 2026-10-14 口径：挑选数据放购物车）
2. 购物车管理：查看/移除条目、按来源任务分组展示；可另存为挑选集复用
3. 下单（三出口，按需选择）：
   a. 合并生成新任务：合并预览（结果清单/设备分布/用例分布/重复与冲突提示）
      -> 填写新任务名/说明/任务级配置 -> 生成新任务（cherry-pick 容器任务，§5.4）
      -> 关联所选执行结果（引用或复制，见 §5.1）-> 手动生成报告（§6）
   b. 发起重新执行：按所选结果的用例×设备集合创建重执行任务
      （走 任务重新执行功能设计文档.md 流程；负责人点名场景：挑出异常用例放购物车重跑）
   c. 发起重新评估：对所选结果发起重新评估（评估域动作，不重跑执行，走重新评估链路）
4. 下单后按出口跳转；生成的新任务全功能可用（§7）
```

购物车口径：

- 购物车按用户持久化，跨会话保留；下单成功后已下单条目出清，未下单条目保留。
- 购物车是工作区（一次性下单用），挑选集是可复用的命名快照（另存/恢复两向）。

## 4. 挑选条件设计

挑选器为多条件组合筛选（AND），维度：

| 条件 | 说明 |
| --- | --- |
| 来源任务 | 可多选（支持跨任务挑选，负责人原话「与另外一个任务的 cherry pick 合并」） |
| 设备 | **负责人点名维度**：某台设备的执行结果 |
| 用例/模型 | **负责人点名维度**：某（模型）用例的执行结果；可按用例标签/分组/算法参数（模型）过滤 |
| 执行状态 | completed / failed / stopped 等结果执行状态 |
| 评估状态 | 已评估 / 未评估（双状态口径） |
| 时间范围 | 结果执行时间 |

> 口径注记：原话「某个设备的模型用例的执行结果」= 设备 + 用例（模型）两个点名维度为**必支持项**；其余维度为规格阶段可扩展项。

### 4.1 选择交互（负责人 2026-10-14 追加口径）

- **正选/反选**：全选当前筛选结果后可反选剔除。
- **粒度三档**：一个一个选（单条勾选）/ 一组一组选（按用例分组整组勾选）/ 按维度选（按标签、评价维度等维度筛选后批量勾选）。
- **交互基线**：参考现有端到端测试的用例选择标签页（端到端测试功能设计文档 §5.2.1——列表/卡片双模式、筛选条件、搜索、多选批量、详情预览），在其上加正选/反选与分组/维度批量勾选。

## 5. 新任务口径

### 5.1 结果持有方式（关键设计点，两方案）

| 方案 | 机制 | 优点 | 代价 |
| --- | --- | --- | --- |
| A 引用（评审起点） | 关联表（cherry-pick 任务 ↔ result_id + 溯源字段）引用源执行结果，详情/报告/统计按引用聚合 | 无数据冗余；源结果重评估后视图随之更新 | 源任务删除时需保护被引用结果或标注缺失；导出需内联 |
| B 复制 | 挑中的结果行（含轮次/维度/音频引用）复制到新任务下 | 新任务完全自治，源删除无影响 | 数据冗余；与源结果脱钩（不随后续重评估更新） |

- **已定稿（负责人 2026-10-15，INT-400 #14-①）：方案 A 引用**（2026-10-14 评审倾向转正）。
- **红线：禁止采用「搬家」语义（修改 `test_results.task_id`）**——源任务必须保持原样（与现有任务合并的本质区别）。

### 5.2 任务级配置

多来源任务合并时，任务级字段（算法参数/评价维度/标签）可能不一致：

- 默认口径：结果级展示各自原配置（结果自带溯源标注）；任务级配置取「首个来源任务」，创建弹窗中允许编辑。
- **已拍板（负责人 2026-10-15，INT-400 #14-③）：跨任务配置不一致时强制确认**——比默认口径严：创建弹窗弹确认提示，而非仅默认取首源。

### 5.3 状态

- 执行状态：新任务无执行过程，创建即落 `completed`（口径对齐现有合并容器任务：创建即 completed + TaskCase 状态继承，双状态派生表达式自动生效）。
- 评估状态：按所选结果的评估情况聚合（全部已评估=已评估；否则部分/未评估，具体枚举规格阶段对齐 status_fields_relationship.md）。

### 5.4 任务分类标识（评审修正：不新增 task.type）

`task.type` 字段已在 V9.7.31 物理删除（迁移 `202610/drop_task_type_and_testcase_test_type.py`，任务分类由用例级 device_type 派生，INT-263 裁定）。本功能**不新增 type 字段、不使用 `type=cherry_pick`**，对齐现有 merged 容器任务的存在性判定口径：

- cherry-pick 容器任务以**专有关系表存在性判定**（与 TaskMergeRelation 对 merged 容器的判定方式同构），表结构规格阶段定（评审建议：容器任务 ↔ result_id + 溯源字段关联表）。
- 列表筛选对齐 merged=true 模式新增 `cherry_pick=true` 查询参数（服务端过滤，复用 useMergedTasks 同构实现）。
- 后端枚举/常量按「enum 化+配置化」红线进 shared 枚举定义，拒绝魔法字符串。

## 6. 报告口径

- cherry-pick 任务的报告走现有报告链路：**手动生成**（对齐报告管理功能设计文档 §3.1 手动生成/多任务合并生成入口）；「任务完成自动触发报告」不适用（无执行过程），创建成功后引导手动生成。
- 报告内容 = 所选结果的聚合报告；模板/字段/导出/对比与普通任务报告一致。
- cherry-pick 任务可作为普通任务被「多任务合并生成报告」选入。

## 7. 全功能支持清单（原话「支持现有的所有任务和报告功能」的验收基线）

| 功能 | 对 cherry-pick 任务的支持 |
| --- | --- |
| 列表/详情/筛选/统计 | 一等公民；任务列表页新增「挑选合并」页签展示（见 §9），`cherry_pick=true` 参数可筛（§5.4） |
| 重执行/重评估 | 任务级重执行/重评估走原有口径；**购物车下单可直接发起**：对所选结果的用例×设备集合发起重执行/重评估（§3 出口 b/c） |
| 发布 | 走三冻结口径（任务发布功能设计文档 §4.1），无差异 |
| 收藏/回收站 | 无差异 |
| 任务对比 | 作为普通任务参与对比 |
| 再合并/再挑选 | 可作为挑选源与合并源 |
| 导入导出 | 与普通任务一致（引用方案下导出需内联所选结果，规格阶段定） |
| 报告生成/查看/对比/导出/收藏 | 无差异（§6） |

## 8. 接口草案

前缀 `/tasks/cherry-picks`。

| 接口 | 说明 |
| --- | --- |
| `GET /tasks/cherry-picks/cart` | 当前用户购物车内容（按来源任务分组） |
| `POST /tasks/cherry-picks/cart/items` | 加入购物车（来源任务 + 结果勾选集） |
| `DELETE /tasks/cherry-picks/cart/items/{itemId}` | 从购物车移除 |
| `POST /tasks/cherry-picks/cart/checkout` | **下单**：`action=merge`（合并生成新任务，默认）/ `reexecute`（发起重执行）/ `reevaluate`（发起重评估） |
| `POST /tasks/cherry-picks/cart/save-as-set` | 购物车另存为挑选集 |
| `POST /tasks/cherry-picks/sets/{setId}/to-cart` | 挑选集恢复进购物车 |
| `GET /tasks/cherry-picks/sets` | 挑选集列表 |
| `POST /tasks/cherry-picks/preview` | 合并预览（下单前统计/失效校验） |
| `GET /tasks/cherry-picks/pickable-tasks` | 可挑选终态任务清单（挑选向导阶段 1 数据源，INT-1496；契约见 §8.1） |
| `GET /tasks/cherry-picks/candidates/tree` | 阶段 2 候选树聚合（任务→用例→设备/API→result_type，节点计数 + result_id 集，服务端一次聚合；INT-1510，契约见 §8.2） |
| `GET /tasks/cherry-picks/{taskId}/source` | 新任务溯源（各结果来源任务 + 结果级字段 + 源任务状态，非容器 200+空 groups，契约见 §8.3；INT-1714 起追加结果级字段。旧文写的 `GET /tasks/{taskId}/cherry-pick-source` 是历史占位名，只出现在注释/docstring，实际路由一直是本行这个） |

命名边界：前端/Domain 用 camelCase；snake_case 只允许出现在后端数据库与 DTO 转换层（总览 §1.3 口径）。

`GET /tasks/cherry-picks/cart` 响应行字段（INT-1693，2026-10-24）：`data.groups[].items[]` 行级含 `tags: string[]` / `group_id: string|null` / `group_name: string|null`，缺省 `[]` / `null` / `null`，与候选行同源（来源、软删口径与实现位置见 §13 2026-10-24 条）；`groups[].source_task_id`、`source_task_name`、`total`、`invalid_item_ids` 结构与语义不变。HTTP 响应保持后端 snake_case（DTO 层输出），前端 camelCase 转换按 §13 2026-10-21 条由 infrastructure adapter 完成。

### 8.1 可挑选任务清单接口（INT-1496 契约裁定，2026-10-23）

> 结论：采用**方向 A（轻）**。交互规范 18 §3.8.2 阶段 1 的「数据源=候选行聚合」改为本端点；方向 B（18 §11-3 候选树聚合端点）仍为可选增强，不在本卡实施。

缺陷背景（2026-10-23 真实库实测）：原实现取 `GET /tasks/cherry-picks/candidates` 首页 200 行（`per_page` 封顶 200、不翻页）在客户端按 `task_id` 聚合出任务清单。真实库候选结果行 3614 条，集中在大任务（task 419 138 条、418 62 条），首页 200 行只覆盖 2 个任务，而真实库含可挑结果的终态任务有 117 个——阶段 1 清单严重残缺。同接口 `per_page=200` 实测 60s 未返回，阶段 1 也不应再背这条慢查询。

**接口**：`GET /tasks/cherry-picks/pickable-tasks`，权限 `task:read`，前缀沿用 `/api/v1/tasks/cherry-picks`。

| 参数 | 类型 / 取值 | 缺省 | 说明 |
| --- | --- | --- | --- |
| `keyword` | string | 空 | 任务名模糊匹配（`ILIKE %kw%`；只匹配任务名，不匹配任务 ID） |
| `status` | `completed` / `failed` / `stopped` | 全部 | 任务状态过滤（`PickableTaskStatus` 枚举值） |
| `sort_by` | `status` / `name` / `created_at` | `status` | `status` 排序 = 权重 completed→failed→stopped，同权重按任务名 |
| `sort_order` | `asc` / `desc` | `asc` | 时间倒序由前端显式传 `sort_by=created_at&sort_order=desc` |
| `page` | int ≥ 1 | 1 | |
| `per_page` | int 1–200 | 50 | 与 candidates 同口径（上行越界 → 400） |

入选口径（服务端一次 GROUP BY，不下发候选结果行）：

```
test_tasks t JOIN test_results r ON r.task_id = t.id
WHERE t.deleted = false
  AND t.status IN PickableTaskStatus                 -- 显式枚举，不写字面量
  AND r.excluded = 0                                 -- INT-305：剔除被删用例结果行
  AND visible_condition(t.created_by_user_id, t.visibility, uid, admin)   -- INT-423 可见性
GROUP BY t.id HAVING count(r.id) > 0
ORDER BY <排序键>, t.id ASC                          -- id 兜底稳定次序
```

**性能要求（硬性，负责人 2026-10-23 实测口径，验收必查）**

1. **聚合在 task_service 一次完成**：`test_tasks ⋈ test_results` 的计数聚合在仓储层单条 SQL 内 `GROUP BY t.id` 出结果；网关只做参数校验、透传与 `success_response` 信封，**禁止**把候选/结果行下发到网关再聚合，响应体也不得携带候选行数组。
2. **分页在服务端聚合结果上做**（窗口函数 `count(*) over()` 或子查询 + `LIMIT/OFFSET`），不得把全量任务行拉进进程内存再切片。
3. **返回体只含任务级字段**：`id / name / execution_status / pickable_count / created_at`；不含结果行、用例/设备/评估等结果级装饰，不携带候选树结构。
4. **基线对照**：现行 `GET /tasks/cherry-picks/candidates?page=1&per_page=200` 真实库实测 **7169 ms**（total=3614 行，INT-1280 登记）；本端点单次请求目标 **< 2s**（见验收第 2 条）。
5. **阶段解耦**：阶段 2 候选查询的性能优化（candidates 慢查询、候选树重建）**另行开卡，与本端点解耦**——本端点不等待、不复用其优化结果，验收不以阶段 2 性能为条件；反之本端点的性能也不得靠裁剪阶段 2 能力来换。

响应 `data`：`{ items: [{ id, name, execution_status, pickable_count, created_at }], total, page, per_page }`（网关 `success_response` 信封）。

- `id` / `name` = 任务 ID / 任务名（任务级，不是结果行）；
- `execution_status` = **任务**执行状态（三终态之一），不是结果级执行状态（原实现误用候选行的 `execution_status`）；
- `pickable_count` = 该任务可挑结果行数（`excluded=0`），供阶段 1 行尾「{n} 条」；
- `created_at` = 任务创建时间（ISO 8601），**不是**首条结果时间（原实现取候选行时间）；
- `total` = 满足条件的任务总数（不受分页影响）。

边界（本卡不做）：

- 容器任务（cherry-pick 合并容器）自身无 `test_results` 行，不入本清单——与现状一致；再挑容器结果仍走 INT-657 的显式 `task_ids` 口径，是否纳入清单另立卡评估。
- 不含设备 / 用例 / 评估状态等结果级条件：阶段 1 只做任务维度过滤与排序。
- `candidates` 契约与分页语义保持不变，不做兼容层、不留双口径。

落位（DDD 四层，上层不绕过 Application 直触 Infrastructure）：

- 网关：`routes/cherry_pick_bp.py` 新增路由 → `schemas/cherry_pick.py` 新增 `CherryPickPickableTasksQuery` → `application/services/task/cherry_pick_service.py` → ACL `infrastructure/acl/cherry_pick_acl_repository.py` + `infrastructure/grpc_proxies/cherry_pick_proxies.py`。
- 契约：`shared/proto/task_service.proto` 新增 `rpc ListCherryPickPickableTasks(CherryPickPickableTasksRequest) returns (TaskConfigResponse)` 与消息（`data` JSON，同 candidates 风格），重新生成 `shared/proto/task_service_pb2*.py`（两服务共用同一份生成物）。
- task_service：`interfaces/grpc/cherry_pick.py` 新增 servicer 方法 → `application/task/cherry_pick_service.py` → `infrastructure/persistence/cherry_pick_repository.py` 承载上述 GROUP BY（application 不直连 session）。

验收：

1. 真实库栈（`/health` → `database=intelligent_audio_test`）下 `total` 与同口径 SQL `count(DISTINCT t.id)` 一致；2026-10-23 基线与分布（只读取证）：非删除任务 125（全部是 completed 79 / failed 39 / stopped 7），其中含可挑结果的 117 个、结果行 3614 条；首屏 200 行候选只覆盖 task 419（138）与 418（62）。
2. 单次请求 < 2s（基线：candidates 首页 `per_page=200` 实测 7169 ms / 曾超 60s）：聚合须在 task_service 单条 `GROUP BY` 内完成，网关侧不得接收候选行再聚合；性能要求见上文「性能要求（硬性）」5 条，逐条验收。
3. 既有回归不破坏：`tests/unit/test_int339_cherry_pick.py`、`test_int577_cherry_pick_upgrade.py`、`test_int1130_cherry_pick_case_meta.py`、`test_int339_acceptance.py`；5000 段隔离库冒烟。
4. 可见性：非 owner 非 admin 用户看不到他人私有任务（INT-423 同口径）。

前端接线（另卡，React 接线项目）：

- 阶段 1 `PickTaskRow` 改由本端点取数（`pickable_count→count`、`execution_status→executionStatus`、`created_at` 直接映射），删除候选首页聚合与客户端状态权重排序；
- 「来源任务」筛选选项 `fetchPickableTasks` 同源切换（顺带去掉候选 30s 缓存兜底）；
- 「全选当前筛选」须覆盖 `total` 全部任务（按 `per_page` 拉齐或显式提示已加载 N/total），不允许再出现只选到首页。

已知边界（**阶段 2 性能另行开卡，与本端点解耦**）：阶段 2 候选树仍由 candidates 首页 200 行重建（18 §11-3 降级），其慢查询优化由规划师另立卡，不并入本卡、不阻塞本端点验收。本卡上线后用户可选到结果数 > 200 的任务，阶段 2 展示仍是「已加载 200 条」，跨页全选由 `POST /candidates/select-all` 保证。

> 后续（2026-10-24，INT-1510 契约审查）：阶段 2 已裁定走服务端候选树聚合端点，契约见 §8.2；本节的「200 行降级」边界在 §8.2 落地后失效，`candidates` 保留为叶明细分页与 `select-all` 口径来源。

### 8.2 阶段 2 候选树聚合接口（INT-1510 契约裁定，2026-10-24）

> **结论：采用方向 B（服务端候选树聚合端点）**，并在同一张卡内把方向 C 的必备性能收口作为硬性前提（禁止逐行回源 OSS、装饰次数与结果行数解耦）。理由：阶段 2 的缺陷首先是**完整性**——树由 `candidates` 首页 200 行重建（UX 规范 18 §11-3 降级），而真实库命中 3614 行且集中在少数大任务；只要树的数据源仍是「一页平铺行」，任何单页耗时优化都拿不到正确节点计数。方向 C 的行接口优化仍然必要，但只承担**叶明细分页**与平铺辅助视图，不承担树骨架。端点形态按 UX 规范 18 §11-3（任务→用例→设备/API→result_type，含每节点 `result_id` 集与计数），三视图（用例/设备/结果类型）由同一棵树重排。

#### 8.2.1 缺陷根因（2026-10-24 真实库只读取证 + 代码核对）

| # | 事实（实测 / 代码位置） | 对方案的含义 |
| --- | --- | --- |
| 1 | 可挑结果行 **3614 条 / 117 个终态任务**（`test_tasks ⋈ test_results`，`t.deleted=false`、`t.status∈三终态`、`r.excluded=0`） | 与 §8.1 登记一致；200 行首页只覆盖 5.5% |
| 2 | 全表 5537 行，`count(distinct task_id, test_case_id, device_id, api_id)` = **5537**，即每行唯一 | 按 (任务,用例,设备/API) 聚合**不减少**条目数；聚合的收益只能来自「去掉逐行装饰」，不能指望节点数远小于行数 |
| 3 | `result_type` **不是列**（`task_service/infrastructure/persistence/models/result_models.py` 的 `TestResult` 无该字段）；取值走 `shared/utils/result_data_store.py:extract_result_type → load_full_result_data`，而后者在 `result_data_path` 非空时**先读 OSS 文件**：`storage.exists` + `storage.load_bytes`（`shared/infrastructure/storage.py:265/302`），每行 **2 次 OSS 往返**；`shared/clients/oss_client.py:94-95` connect_timeout=5 / **read_timeout=60** | 候选查询当前的成本主体是「按行数线性放大的对象存储往返」，其长尾可把单请求拖到 60s 级（见 #5） |
| 4 | 有 `result_data_path` 的行：全表 3562/5537，可挑范围 2805/3614；可挑行中 **2598/3614 的 DB 轻量 JSON 已含 `result_type`**，1016 行缺键 | 大多数行根本不需要 OSS：改为 DB-first 取值即可消除大部分往返；缺键存量行需一次性收口（见 §8.2.3 第 1 条）。**〔INT-1669 落地复核修正：2598 是含嵌套 `raw_results_list` 的行数，顶层键命中 0 行，回填后 3614/3614 落缺值桶，见 §8.2.7 第 4/5 条〕** |
| 5 | 每请求另有 **4 条跨服务 gRPC** 装饰：evaluation（`evaluated`）、audio（用例时长）、device（设备名）、api_test（API 名），均在 `task_service/application/task/cherry_pick_service.py:_query_candidate_results` | 装饰链与行数/节点数耦合，需按「去重后的集合」批量化并限定条数 |
| 6 | 本 run 在 :15000 实测：`candidates?per_page=200` **60.4s** 返回 `gRPC DEADLINE_EXCEEDED`；另一次 `per_page=1` 亦在 60s 级失败（当日引擎重启与并发压测期间，属尾部风险佐证；良态基线取 §8.1 登记的 **7169 ms**） | 性能红线必须按「最坏情况」定，而不是按良态平均值定 |

#### 8.2.2 接口契约

**接口**：`GET /tasks/cherry-picks/candidates/tree`，权限 `task:read`，前缀沿用 `/api/v1/tasks/cherry-picks`；可见性 INT-423（非 owner 非 admin 不可见私有任务）。

| 参数 | 类型 / 取值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_ids` | 逗号分隔 int，**1–200 个** | 是 | 阶段 1 已选任务集（阶段 2 的作用域）；空数组或越界 → 400 |
| `device_ids` | 逗号分隔 int | 否 | 设备维度过滤（结果级） |
| `api_ids` | 逗号分隔 int | 否 | API 维度过滤（结果级） |
| `case_ids` | 逗号分隔 string | 否 | 用例精确过滤 |
| `case_keyword` | string | 否 | 用例名/用例 ID 模糊（与 `case_ids` 语义同 candidates） |
| `execution_status` | `completed` / `failed` / `stopped` | 否 | **结果**执行状态 |
| `evaluation_status` | `evaluated` / `pending` | 否 | 评估状态（口径同 candidates） |
| `start_date` / `end_date` | ISO 8601 | 否 | 结果执行时间范围 |

响应 `data`（网关 `success_response` 信封）：

```json
{
  "total": 3614,
  "task_count": 117,
  "meta": {
    "tasks":   [{"task_id": 419, "task_name": "...", "task_status": "completed"}],
    "cases":   [{"case_id": "...", "case_name": "...", "algorithm_type": "...",
                 "tags": [], "group_id": null, "group_name": null,
                 "duration": 12.5, "rounds": 2}],
    "devices": [{"device_id": 1, "device_name": "..."}],
    "apis":    [{"api_id": 7, "api_name": "..."}]
  },
  "tree": [
    {"task_id": 419, "count": 138, "cases": [
      {"case_id": "...", "count": 6, "devices": [
        {"device_id": 1, "api_id": null, "count": 2, "result_types": [
          {"result_type": "real-time", "count": 2, "result_ids": [1, 2]}
        ]},
        {"device_id": null, "api_id": 7, "count": 4, "result_types": [
          {"result_type": "final", "count": 4, "result_ids": [3, 4, 5, 6]}
        ]}
      ]}
    ]}
  ]
}
```

字段口径：

- `total` = 命中**结果行**总数，必须与同口径 SQL 一致；等于全部 `tree[*].cases[*].devices[*].result_types[*].count` 之和；`task_count` = 命中任务数。
- `meta` 为**去重表**：`cases` 按 `case_id`、`devices` 按 `device_id`、`apis` 按 `api_id`、`tasks` 按 `task_id` 各一条，供三视图节点命名与用例卡元信息使用；`duration` / `rounds` / `tags` / `group_*` 口径同 §8.1 的用例元信息（`total_duration` 同源）。
- `tree` 为三视图共用的最细分组：任务 → 用例 → 设备/API（`device_id`、`api_id` 二选一，与 `TestResult` 归属一致）→ `result_type`；每个 `result_type` 节点带 `result_ids`（该节点下的全部结果 ID，用于 R1-R10 三态勾选与节点级全选）。
- `result_type` 缺值按 UX 规范 18 §3.7.1 归「结果类型待补充」桶（不得回源 OSS 判定，见 §8.2.3）；**对外取值统一为 `default`**（单一常量 `RESULT_TYPE_PENDING`，`shared/utils/status_constants.py:85`），过滤参数传 `default` 命中缺值桶，不得另立第二个缺值取值。
- 容器任务（INT-657）语义保持不变：容器任务自身无结果行，`task_ids` 含容器时经 `task_cherry_pick_relations` 展开引用结果，命中行归属标注为**容器任务**（直查命中的源任务优先），与 `candidates` 现行口径一致。

#### 8.2.3 性能硬性要求（验收必查，逐条核对）

1. **tree 端点零 OSS 往返**：`result_type` 必须取自数据库（新增落库列或直接读 `test_results.result_data` 轻量 JSON），禁止逐行/逐节点调用 `storage.exists/load_bytes`。存量缺键行（可挑范围 1016 行）由随卡交付的一次性迁移/回填收口（可离线回源 OSS 一次），**请求路径不得回源**；不回填的行按「结果类型待补充」桶呈现。`candidates` 的 `result_type` 取值同步改为 DB-first（同一收口）。〔已由 INT-1669 落地：迁移 ㊷ + 写时物化，见 §8.2.7〕
2. **聚合在 task_service 仓储完成**：`test_tasks ⋈ test_results` 的分组计数在仓储层单条 SQL（至多 2 条：主聚合 + 去重元信息）内完成，`total` 与节点计数不依赖把结果行拉进进程内存；网关只做参数校验、透传与信封，**不得接收结果行再聚合**。
3. **跨服务调用 ≤ 4 次/请求且与行数无关**：用例元信息（tags/group）与 `duration`（audio gRPC）按**去重后的用例集合**各 1 次批量；设备名、API 名各 1 次；`evaluation_status` 过滤时允许再 1 次 evaluation 批量。禁止按行/按节点循环调用。〔INT-1500/INT-1625/INT-1669 演进后现行口径：`duration`、`evaluated`、API 名均已改共享库窄字段只读投影，不再有 audio / evaluation / api_test gRPC；**真实跨服务调用只剩设备名 1 次**，见 §8.2.7〕
4. **叶明细走服务端分页**：tree 只给节点计数与 `result_id` 集，不给结果行明细；叶明细由 `candidates` 按「当前展开节点」的过滤组合（`task_ids + case_ids + device_id 或 api_id + result_type`）分页取，`per_page` 1–200，`total` = 该节点命中数（翻页语义正确，不因客户端过滤而错页）。
5. **首屏 < 2 s**：以「`task_ids` = 全部 117 个可挑任务、3614 行、无其它筛选」为最坏情况实测；`evaluation_status` 过滤路径、叶明细分页（≤200 行）各自单独实测，均 < 2 s。并行/高负载下的绝对时延不可判定时，按 devloop 性能口径用同栈多轮 A/B 给逐轮数据，不取中位冒充。
6. **不得回退或双口径**：不得恢复「拉全量候选行再客户端聚合」；阶段 2 的树骨架与节点计数**唯一来源**为 tree 端点，`candidates` 仅作叶明细分页与 `select-all` 口径来源，二者不是两套树口径。

#### 8.2.4 落位（DDD 四层，与 §8.1 同构）

- 网关：`routes/cherry_pick_bp.py` 新增路由 → `schemas/cherry_pick.py` 新增 `CherryPickCandidateTreeQuery`（`task_ids` 必填校验、`per_page` 不适用）→ `application/services/task/cherry_pick_service.py` → ACL `infrastructure/acl/cherry_pick_acl_repository.py` + `infrastructure/grpc_proxies/cherry_pick_proxies.py`。
- 契约：`shared/proto/task_service.proto` 新增 `rpc ListCherryPickCandidateTree(CherryPickCandidateTreeRequest) returns (TaskConfigResponse)` 与消息（`data` JSON，同 candidates 风格），重新生成 `shared/proto/task_service_pb2*.py`（两服务共用同一份生成物）。
- task_service：`interfaces/grpc/cherry_pick.py` 新增 servicer 方法 → `application/task/cherry_pick_service.py` → `infrastructure/persistence/cherry_pick_repository.py` 承载聚合 SQL 与去重元信息查询（application 不直连 session）。
- `candidates` 增量参数：`api_ids`、`result_type` 服务端过滤（新增可选参数，既有参数与分页语义不变）；`api_ids` / `result_type` 的客户端过滤随前端接线卡删除。

#### 8.2.5 验收

1. **完整性**：真实库栈（`/health` → `database=intelligent_audio_test`）下 `total=3614`、`task_count=117`，与同口径 SQL 一致；`tree` 各级计数求和 = `total`；任一视图分组（task / case / device / result_type）抽样计数与 SQL 一致。
2. **性能**：§8.2.3 第 5 条的三条路径分别实测，逐轮数据入交付评论；同时核对第 1/3 条（tree 请求期间无 OSS 往返、跨服务调用次数达标）。
3. **分页/选择**：「全选当前筛选」仍走 `POST /candidates/select-all`，其返回集合与 tree 各 `result_type` 节点 `result_ids` 并集一致；叶明细分页逐页 `result_id` 不重不漏。
4. **权限/可见性**：非 owner 非 admin 看不到他人私有任务及其结果（INT-423 同口径）。
5. **回归**：`tests/unit/test_int339_cherry_pick.py`、`test_int577_cherry_pick_upgrade.py`、`test_int1130_cherry_pick_case_meta.py`、`test_int339_acceptance.py` 全绿；阶段 1 `pickable-tasks` 契约与响应不变。

#### 8.2.6 边界（本卡不做）

- 不改阶段 1 `pickable-tasks` 的契约与响应（§8.1），不接受它承担阶段 2 的树数据。
- React 阶段 2 接线（树数据源切换、三视图重排、删除客户端 `api_ids`/`result_type` 过滤、全选提示改为服务端全量）另立接线卡，依赖本卡 done。
- `task_ids` 上限 200：当前真实库 117 个可挑任务，留有余量；接近上限时另立卡收窄范围或分批挑选，不偷偷放大上限。
- 不在本卡做 tree 响应的 ETag/缓存层；如后续需要另立卡。

#### 8.2.7 实现演进裁定（2026-10-24，INT-1669 落地复核）

> 本节记录 §8.2 定稿后、行接口收口（INT-1669）落地时发生的口径变化。**冲突以本节为准**；§8.2.1 / §8.2.3 的原始表述保留为裁定当日的取证记录。

| # | §8.2 原表述 | 落地现状（INT-1669，2026-10-24） | 证据 |
| --- | --- | --- | --- |
| 1 | §8.2.3 第 3 条「`duration`（audio gRPC）」 | 候选行 `duration` 已改共享库窄字段只读投影，**不再有 audio gRPC 调用**（INT-1625 起） | `task_service/infrastructure/acl/audio_acl_repository.py:44` |
| 2 | §8.2.3 第 3 条「`evaluation_status` 过滤时允许再 1 次 evaluation 批量」 | `evaluated` 标记与 `evaluation_status` 过滤已改共享库存在性投影，**不再有 evaluation gRPC 调用** | `task_service/infrastructure/acl/evaluation_config_acl_repository.py:83` |
| 3 | §8.2.3 第 3 条「API 名各 1 次」 | API 名称已改共享库窄字段批量投影（`apis` 表，`deleted = FALSE`），**不再有 api_test gRPC 调用** | `task_service/infrastructure/acl/report_acl_repository.py:174`（INT-1500 `e4d4e3030`，已进 V9.7.31） |
| 4 | §8.2.1 第 4 条「可挑行 2598/3614 的 DB 轻量 JSON 已含 `result_type`」 | 2598 是**含嵌套 `raw_results_list`** 的行数，其 `result_type` 取值全为 `default`；**顶层 `result_data.result_type` 命中 0 行**（全表 5546 行、可挑 3614 行均为 0）。`extract_result_type` 只读顶层键，故按原口径取不到任何值 | 2026-10-24 主库只读实测；`shared/utils/result_data_store.py:196` |
| 5 | §8.2.3 第 1 条「存量缺键行（可挑范围 1016 行）由随卡迁移回填」 | 回填**命中 0 行**：缺键的是全部 3614 行（2598 行只有嵌套键、1016 行无该键），因此迁移后 3614/3614 全部落「结果类型待补充」桶 | `scripts/migrations/202610/add_test_result_result_type_int1510.py` 模块注释（只读 DB 轻量 JSON、不回源 OSS） |

因此 §8.2.3 第 3 条的现行口径是：**真实跨服务调用只剩设备名 1 次**（`task_service/application/task/cherry_pick_service.py:1172` → `device_acl_repository.get_device_statuses`，device_service `GetDeviceStatuses` RPC），与结果行数、节点数无关；其余装饰全部走共享库只读投影。

`result_type` 的单一取值定义（不得双口径）：

- 落库列 `test_results.result_type VARCHAR(50) NULL`（`task_service/infrastructure/persistence/models/result_models.py:40`）；写时由 `submit()` 物化（显式值优先，否则只读 DB 轻量 JSON、不回源 OSS，`task_service/infrastructure/persistence/test_result_repository.py:131/154`），缺值落 NULL。
- 对外取值 `default` = 缺值桶（`RESULT_TYPE_PENDING`，`shared/utils/status_constants.py:85`）：读侧统一输出该值，过滤参数传 `default` 命中 `NULL / 空串`。`candidates`、`select-all`、购物车/挑选集快照（`source_result_type`）同用这一口径。
- 迁移 ㊷ `scripts/migrations/202610/add_test_result_result_type_int1510.py`（幂等、默认 dry-run、不建索引），已登记 `scripts/migrations/README.md` 与 `docker/db_bootstrap_entrypoint.py` 的 `BOOTSTRAP_STEPS` ㊷。**主库尚未执行**（2026-10-24 实测 `information_schema` 无该列）：部署顺序必须是「重建 db_bootstrap 镜像（迁移脚本是 COPY 进镜像的）→ 启动执行 ㊷ `--apply` → 再上 task_service 新镜像」，未执行前按落库列读会 `UndefinedColumn`。
- 数据事实（2026-10-24 主库只读实测）：可挑范围 3614 行经 ㊷ 回填后**全部落 `default` 桶**，即阶段 2 树的 `result_type` 层在真实库上只有一个节点（UX 18 §3.7.1「结果类型待补充」）。这是数据现状而非契约问题；若后续要求多桶，需另立卡补真实 `result_type` 来源。

#### 8.2.8 meta 缺省口径与数据侧处置（2026-10-25，INT-1824）

> 阶段 2 真库终验（INT-1818）发现候选树 `meta` 存在用例/设备元信息缺口，本节定其**数据侧处置与缺省口径**。**不改端点契约与计数口径**（§8.2.2 的字段与结构不变）。

**实测**（2026-10-25，docker 真实库栈 `:15000`，`/health` → `database=intelligent_audio_test`，`task_ids` = 全部 117 个可挑任务）

| 项 | 结果 |
| --- | --- |
| `total` / `task_count` | 3614 / 117（与 §8.2.5 一致） |
| `meta.cases` | 1057 条，其中 **483 条 `case_name == case_id`**（UUID 形态），其余 574 条元信息正常 |
| `meta.devices` | 5 条（设备 1/6/7/9/10），其中 **1/6/7 三条 `device_name = null`**，承载 1204/3614 行结果 |
| `meta.apis` | 0 条（可挑范围无 API 维度结果），无缺口 |

483 的构成：**463** 个 `case_id` 在 `test_cases` 无行（硬缺失），**20** 个已软删（`deleted = true`）。

**结论一：用例目录不回填**（可复原性不足 + 回填会污染共享用例目录）

- `test_results.result_data` 与 `task_case_relations` 都**不存用例名、也不存用例配置**（前者只有 `multi_round` / `raw_results_list` / `evaluation_data` 等结果键，后者只有任务-用例关系与执行状态），无法据此补建用例目录。
- 名字快照只剩报告侧：`report_cases.name` 能捞到 214/483 的用例名，其中仅 45 个 case_id 能按名字指回现存 `test_cases`——即 438/483 连「指回现有用例」都做不到。
- 补建要伪造 `test_cases.config`（`NOT NULL`）与 `algorithm_params` / `reference_params`，会把 463 条无音频、0 轮次的空壳用例灌进**共享用例目录**（用例管理页可见、可被选进新任务）。代价远大于「名字可读」的收益，属数据污染，不做。
- 20 个软删用例按 INT-1693 与 §8.3.1 的既有口径「软删 = 查不到」不进映射，**不为树单独放宽**。现状三处口径并不齐（2026-10-25 审计实测）：候选行显示真实名（`_case_name_map` 不过滤软删，`36f5696f-24a3-4537-9064-e3c84820aadf` 在 `GET /candidates` 返「测试用例_DD075…」）、树 meta 返 UUID、溯源返 null；放宽树只会让树与候选行一致（仍是两套口径，不构成第三套），口径统一属另一套裁定，本卡不动，留作遗留观察。
- 来源可追溯性到此为止：`logs` 表最早记录是 2026-10-17（导入之后），本地无法判定是导入未随迁还是源端已删；报告快照的 `created_at`（2026-08-29 等）是**源端时间**，不能当作平台内删除的证据。故「补建/恢复用例目录」在本库无源可依。

**结论二：设备名不是数据缺口，是既有跨域口径**

- 设备 1/6/7 的行仍在 `devices`（`deleted = true`）、名字可得；拿不到是因为 device_service `GetDeviceStatuses` 对显式 ID 也过滤 `deleted = FALSE`（`device_service/infrastructure/persistence/_device_repository_impl.py:152`）。
- 报告侧同源：`_grpc_get_devices_by_ids` → 报告服务 ACL 的 `get_devices_by_ids`（逐 ID 调 `get_device`）→ gRPC `GetDevice` → device_service `get_device`（同文件 `:80`，同样过滤 `deleted = FALSE`）；device_service 自身的批量 `get_devices_by_ids`（同文件 `:172`）也带同样过滤，其调用方是进程内的 `device_result_reextractor_service.py:231`。即**软删设备名在全域都解析不到**，tree 不是特例。本卡不改 device_service（跨域，且动的就是全域口径）；如需显示软删设备的真实名，另立 FEAT（显式 ID 查询加 `include_deleted` 开关——device_service 目前无此开关，或设备名快照——`test_results` 无设备名列，均属新增）。

**结论三：缺省口径 = 接口不拼展示文案，前端兜底**

阶段 2 树沿用「查不到 = 缺省」，**接口不返回中文文案**（与 §8.3.1 第 2 条同一原则）：

| 场景 | 接口返回（现状） | 前端兜底（阶段 2 接线卡落实） |
| --- | --- | --- |
| 用例目录查不到 / 已软删 | `case_name = case_id` | `case_name === case_id` → 「未知用例」，**不裸显 UUID** |
| 设备已软删 | `device_name = null` | `device_name === null` → 「未知设备」 |

兜底文案与容器溯源端点（§8.3.1）统一，同一功能不留两套说法。前端落点：React 阶段 2 接线卡（§8.2.6 已登记「另立接线卡」，**尚未建**；建卡时必须带上本条兜底，否则 483 条用例将以 UUID 形态直接展示给用户）。

**复现（主库只读）**

```sql
-- 483 = 463 无行 + 20 软删
with ids as (
  select distinct r.test_case_id from test_results r
  join test_tasks t on t.id = r.task_id
  where r.excluded = 0 and t.deleted = false
    and t.status in ('completed','failed','stopped'))
select count(*) filter (where c.id is null)                       as hard_missing,
       count(*) filter (where c.deleted)                          as soft_deleted,
       count(*) filter (where c.id is not null and not c.deleted)  as healthy
from ids left join test_cases c on c.id = ids.test_case_id;
-- hard_missing | soft_deleted | healthy
--           463 |           20 |     574
```

### 8.3 溯源接口契约（INT-1706 裁定，2026-10-24）

> **编号说明（INT-1755 裁定，2026-10-24）**：本节即 INT-1706 的溯源契约，原占 §8.2，因与阶段 2 候选树契约（§8.2，INT-1510）撞号，顺延为 §8.3；INT-1706 / INT-1714 代码注释中写作「§8.2」的溯源口径均指本节。裁定记录见 §13。

**接口**：`GET /tasks/cherry-picks/{taskId}/source`，权限 `task:read`（设计 §8 表）。

| 场景 | HTTP | 响应 data |
| --- | --- | --- |
| 挑选合并容器（有关系行） | 200 | `{task_id, is_cherry_pick: true, total, groups: [{source_task_id, source_task_name, results: [...]}]}`（results 逐条含 `missing` 标注，§10） |
| 普通任务 / 无关系行（存活的 Task） | **200** | `{task_id, is_cherry_pick: false, total: 0, groups: []}` |
| 任务不存在 / 容器 Task 已软删（INT-1715 存活判定） | 404 | `{code: 404}`（不返回容器数据，避免软删容器仍被渲染成容器） |

裁定理由：「不是容器」是查询的正常结果，不是错误。任务详情页的复核范围解析（`useReviewRecordScope`）对每个任务都会探一次本接口，普通任务恒 400 会在 Network 里制造每页一次的 4xx 噪音（INT-1701 日巡命中）。前端据此约定保持零改动：`groups` 为空且请求成功即回落「归属=页面任务」。

只读探针口径：与同域 `review_count` / `review_history` 一致——无数据即空结果，避免读探针用 4xx 表达正常空结果；存在性判定只保留「任务不存在 / 容器已软删」一处（INT-1715 ①，防止软删容器仍返 200 被当成容器）。


#### 8.3.1 容器溯源字段表（交互规范 18 §11-8 落地，INT-1714，2026-10-24）

**接口与场景判定**：见 §8.3（含 §8.3 的场景表与编号说明）；本节只登记该端点的响应结果级字段与取值语义。端点本体 `GET /api/v1/tasks/cherry-picks/{task_id}/source`，权限 `task:read`。网关路由 `api_gateway/routes/cherry_pick_bp.py:103`（前缀 `/api/v1/tasks/cherry-picks` 见 `app.py:165`）；服务侧 `CherryPickService.source_trace`（`task_service/application/task/cherry_pick_service.py:951`）。gRPC `GetCherryPickSource` 以 JSON 字符串透传（`shared/utils/grpc_json`），网关无响应模型、直返 `data`——**扩字段不改网关、不新增端点、不改路由与返回层级、不动 proto**。

响应 `data`：`{ task_id, is_cherry_pick, total, groups[] }`；`groups[] = { source_task_id, source_task_name, source_task_status, results[] }`。

`results[]` 字段表（前 9 项为老字段，一个不删、不改名、不改语义）：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `id` | int | 关系行 ID |
| `result_id` | int | 源结果 ID |
| `source_task_id` | int | 来源任务 ID |
| `source_task_name` | string | 来源任务名快照（关系行缺名回落 `任务 {id}`） |
| `source_case_id` | string | 源用例 ID（UUID，展示配 `case_name`） |
| `source_device_id` | int \| null | 源设备 ID |
| `source_api_id` | int \| null | 源 API ID |
| `created_at` | string | **关系行**创建时间（老字段，语义不变） |
| `missing` | bool | 源结果行已不存在（物理删除）为 `true` |
| `result_type` | string \| null | 源结果类型；取落库列 `test_results.result_type`，NULL / 空串输出 `default`（「结果类型待补充」桶）；`missing=true` 为 null |
| `execution_status` | string \| null | 源结果执行状态（completed / failed / stopped / pending / running）；`missing=true` 为 null |
| `evaluated` | bool | 源结果是否已评估（`test_result_dimensions` 有该结果行，与候选行同口径）；`missing=true` 为 false |
| `case_name` | string \| null | 源用例名；用例目录查不到（含已软删）为 null，前端渲染「未知用例」，**不裸显 UUID** |
| `device_name` | string \| null | 设备名（device_service ACL 批量）；无设备 / 查不到为 null |
| `api_name` | string \| null | API 名（api_test ACL 批量）；无 API / 查不到为 null |
| `result_created_at` | string \| null | **源结果自身**创建时间（ISO 8601），区别于关系行 `created_at`；`missing=true` 为 null |

`groups[]`：`source_task_id`（int）、`source_task_name`（string）、`source_task_status`（string \| null，`Task.status`；来源任务行查不到为 null；软删来源任务仍返其状态、不带删除标记）、`results[]`（上表）。

**取值与语义（实现演进裁定，2026-10-24）**

1. `result_type` **取落库列，不再从 `result_data` / `result_data_path` 解析**：INT-1510 把结果类型落成列、INT-1669 起读侧 DB-first，与候选行同源（`result.result_type or RESULT_TYPE_PENDING`），请求路径零对象存储往返。交互规范 18 §11-8 表格里的旧解析口径以本条为准。
2. 缺名 / 缺失态不在接口侧拼文案：`case_name=null` 由前端出「未知用例」；`missing=true` 行结果级字段全部 null、`evaluated=false`，关系行快照字段（`source_task_id` / `source_case_id` / `source_device_id` / `source_api_id` / `created_at`）照常返回。
3. 非容器判定以 §8.3 场景表为准（INT-1715 存活判定已合入 V9.7.31）：存活普通任务 / 无关系行 → **200** + `{is_cherry_pick: false, total: 0, groups: []}`；任务不存在 / 容器已软删 → **404**（服务层 `{'code': 404}`；旧版本经网关 `_CODE_HTTP_MAP.get(None, 400)` 兜底成 400+`code:203` 的口径已由 INT-1715 取代）。前端按「非 200 即非容器、静默 + 空 groups 即回落页面任务」判定，不改语义、不加别名端点。
4. 软删**容器**不再返 200：INT-1715（已合入 V9.7.31）在 `source_trace` 加存活校验——容器 Task 已软删即按「不存在」返回 404，不给软删容器渲染机会；存活普通任务仍 200 + 空 groups（见 §8.3 场景表）。软删来源任务仍返其 `Task.status`、不带删除标记（现状不变）。
5. 性能：一次 `TestResult` 多列投影（`_source_result_snapshots`）+ `_evaluated_result_ids` 一次 IN + `_case_name_map` 一次 IN + device / api 名各一次批量 gRPC（id 非空才调，失败降级 null）+ `Task.id IN` 一次（`cherry_pick_repository.source_task_status_map`）；语句数与关系行数无关，无逐行查询、无对象存储往返。
6. 部署前置：主库 `test_results.result_type` 列**已存在**（2026-10-24 INT-1742 审计实测，5546 行、值全 NULL → 对外统一 `default` 桶）；新环境仍必须先执行迁移 ㊷（`scripts/migrations/202610/add_test_result_result_type_int1510.py`，幂等、默认 dry-run，已在 `docker/db_bootstrap_entrypoint.py:182` 引导链；entrypoint 以 COPY 进镜像，需重建 `db_bootstrap`），否则容器溯源与候选接口均 `UndefinedColumn` → 500。
7. 前端同步点：`CherryPickSourceTraceDto` 的结果时间改读 `result_created_at`（原可选 `created_at` 会静默读到关系行时间），由前端 §5.5 卡处理。

## 9. 前端设计

> **INT-577 交互升级（2026-10-17 裁定，本卡实施）**：本节的「四页签 + 三步向导」口径已被专项交互规范《18_挑选合并功能交互重设计.md》（INT-576）整体升级取代——任务列表终态**三页签**（日常/已发布/挑选合并，「合并」页签收编），挑选合并页承载统一容器列表（merged ∪ cherry_pick，`merge_type` facet + 统计徽章）+ **页内四步向导**（挑选→购物车→复核→下单）+ **多级挑选树**（任务→用例→设备/API→result_type，联动 R1-R10）+ 购物车树形分组/移除矩阵 + 全局购物车角标。本节保留旧文作为演进记录，冲突处以后者为准（替代关系见 18 号规范 §0.2）。

- **任务列表「挑选合并」页签**（INT-577 §2.2 裁定①终态三页签）：日常/已发布/挑选合并（合并容器计数 = 双容器并集）；旧 `/tasks/merged`、`?tab=merged`、`?tab=cherry-picks` redirect 到 `/tasks?tab=cherry-picks`（合并方式筛选随 URL `merge_type=whole|picked`）。cherry-pick 容器与整任务合并容器统一在此页签展示，按「合并方式」facet 区分。
- 入口：任务列表/详情的结果列表「加入购物车」（打开挑选弹窗，预筛来源任务）；批量浮条「加入挑选」（任务级整任务加购，替代旧「合并任务」钮）；全局购物车角标/抽屉（导航栏，任意页面可达）。
- 挑选交互：**多级挑选树**四级分组（任务→用例→设备/API→result_type）+ 结果行叶，联动规则 R1-R10（勾父级全选子孙/取消父级清空子孙/子级部分选中/device 容器语义/result_type 仅清叶/跨任务独立/已加购标记等，详见 18 号规范 §3.2）；三档粒度升格到树；树形/平铺视图共享勾选状态；筛选与会话级记忆（刷新保留、不持久化）。
- 购物车：树形分组（任务→用例→设备→result_type）+ 移除矩阵（单条/节点/整组/批量/失效/清空）+ 另存挑选集。
- 复核合并：**四步向导**（挑选→购物车→复核→下单）；复核为独立步骤（preview 摘要 3 StatBadge + 失效/重复/配置不一致 Alert + 可编辑）；下单三出口沿用（合并生成新任务[默认]/重新执行/重新评估）+ configInconsistent 强制确认。
- **页面文案一律中文**（负责人 2026-10-14：站内不出现 "Cherry-Pick" 字样，如「挑选」「加入购物车」「下单」；接口路径除外）。
- 下单成功 → 购物车出清 → 按出口跳转（新任务详情 / 重执行任务 / 重新评估进度）→ 合并出口引导手动生成报告。
- RBAC（18 号规范 §8）：admin/tester 全链可用；algo_engineer 页签列表只读可见、挑选合并写链整链隐藏、购物车角标可看只读；device_admin/guest 整页隐藏。

## 10. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| 挑选结果为空 | 拒绝创建，提示条件无命中 |
| 源任务仍在执行中 | 默认仅允许对已有终态（completed/failed/stopped）的任务挑选（**显式终态集合**，宽于合并容器实际限制 completed/merged——挑选是结果级，宽集合合理，评审 2026-10-14 确认）；执行中任务能否边跑边挑：**不做（§11-② 已拍板，负责人 2026-10-15）** |
| 源任务/源结果被删除 | 引用方案：详情标注缺失、其余正常；复制方案：无此问题 |
| 购物车内条目在下单前失效（源结果被删/源任务被删） | 下单预览时校验，失效条目标注并允许一键移除后再下单 |
| 重复提交 | 任务创建幂等；同名挑选集允许重复保存 |

## 11. 拍板结果（负责人 2026-10-15，INT-400 #14 全部落定）

1. **结果持有方式**：**引用（方案 A）定稿**（§5.1；2026-10-14 评审倾向经负责人拍板转正）。
2. **执行中任务能否边跑边挑**：**不做**——仅终态（completed/failed/stopped）可挑，§10 默认口径转正。
3. **跨任务配置不一致的合并策略**：**强制确认提示**（弹窗确认，比「默认取首源」严）。

## 12. 验收标准

1. 从任务 A 加购「设备 X + 用例集 Y」的结果、从任务 B 加购另一批，购物车下单合并生成新任务；源任务 A/B 的结果与状态不变。
2. 新任务详情正确展示所选结果，且每条结果可溯源到来源任务。
3. 新任务手动生成报告，报告的查看/对比/导出能力与普通任务报告一致。
4. 新任务可发布（三冻结）、可收藏、可参与任务对比、可再次被挑选/合并。
5. 重执行生成的新执行任务覆盖「所选结果的用例×设备」集合。
6. 任务列表筛选/统计对 cherry-pick 容器任务（`cherry_pick=true` 参数）正常。
7. 购物车下单出口 b/c：对所选结果发起的重新执行覆盖「所选结果的用例×设备」集合；重新评估对所选结果生效（人工复核功能与本功能独立，见 §1.2 边界澄清）。
8. 页面无 "Cherry-Pick" 英文字样（接口路径除外）。

## 13. 实现演进裁定记录

- **2026-10-25（INT-1824 数据缺陷处置，开发工程师A）**：候选树 `meta` 用例/设备元信息缺口（483/1057 用例 `case_name` 回落 UUID、1204/3614 行结果的设备名 null）定处置：**数据侧不回填、缺省口径照旧、前端兜底**，完整口径与取证见新增的 §8.2.8。三条要点：①463 个硬缺失用例在库内无源（`result_data`/`task_case_relations` 不含用例名与配置；`report_cases.name` 只覆盖 214 个、其中 45 个能指回现存用例），补建需伪造 `config`（`NOT NULL`）并污染共享用例目录，故不做；20 个软删用例按 INT-1693「软删=查不到」不进映射，不为树单独放宽；②设备 1/6/7 的 `device_name = null` 不是数据缺口，而是 device_service 显式 ID 查询也过滤 `deleted = FALSE` 的全域口径（报告侧同源），本卡不动 device_service，要真实设备名需另立 FEAT；③接口不拼展示文案，前端阶段 2 接线卡对 `case_name === case_id` / `device_name === null` 出「未知用例」/「未知设备」（与 §8.3.1 溯源端点文案统一）。**待办**：React 阶段 2 接线卡建卡时带上兜底（该卡尚未建）。本卡无代码改动。**2026-10-25 方案一致性审计回写**：卡面与 §8.2.8 的全部数字已逐条对主库/端点复核一致（3614/117、1057 − 483 = 574 且 483 = 463 + 20、软删设备承载 1204/3614、`report_cases.name` 覆盖 214/483 且 45 可按名指回、`logs` 最早 2026-10-17、`test_cases.config NOT NULL`、`meta.apis` 0），代码引用 `cherry_pick_service.py:596/1560/1610` 与 `_device_repository_impl.py:152/:80` 亦核对无误；另按代码事实更正两处表述——报告侧设备名链路（是逐 ID `GetDevice` 走 `:80`，非 `:172`）与软删用例名「候选行真名 / 树 UUID / 溯源 null」的现状描述（放宽树只是与候选行一致，不构成第三套）。

- **2026-10-24（INT-1755 章节编号裁定，方案一致性审计员）**：INT-1733（阶段 2 候选树聚合 · INT-1510 契约）与 INT-1706（溯源接口契约）在同一篇文档抢同一节号 §8.2，导致 INT-1733 的两个 doc 提交无法直接合入 V9.7.31。**裁定方案 A：候选树契约保持 §8.2（含 §8.2.1~§8.2.7 原样不动），溯源契约顺延为 §8.3。** 依据是已合入 V9.7.31 代码的引用面：`INT-1510 §8.2.x` 在代码里已落地 26 处（`api_gateway/schemas/cherry_pick.py:37`、`task_service/application/task/cherry_pick_service.py` 多处、`shared/utils/result_data_store.py:219/226`、`shared/utils/status_constants.py:82`、`task_service/infrastructure/persistence/models/result_models.py:38`、`test_result_repository.py:131/134`、`scripts/migrations/202610/add_test_result_result_type_int1510.py`、`scripts/migrations/README.md`、`docker/db_bootstrap_entrypoint.py:178` 及单测），而 `INT-1706 §8.2` 只有 4 处注释级引用（`task_service/application/task/cherry_pick_service.py:1062`、`tests/unit/test_int1714_cherry_pick_source_fields.py:13/241`、`tests/unit/test_int339_cherry_pick.py:411`）；让引用面大的一侧保持原号，改动面最小，也不会产生代码与文档的第二套编号。同步项：§8 接口表「新任务溯源」行改指 §8.3；INT-1670 卡面、INT-1669 回写（§8.2.7）、UX 18 号规范对「§8.2 = 候选树」的引用全部继续成立，无需改动。遗留：上述 4 处 `INT-1706 §8.2` 的代码注释仍写作 §8.2，按本节说明其指向已变为 §8.3（注释级、不影响行为，下轮改到这些文件时顺带同步，不为它单开代码卡）。

- **2026-10-24（INT-1714 实施 + 方案一致性审计 INT-1739 回写，实现演进裁定）**：容器溯源端点 `GET /api/v1/tasks/cherry-picks/{task_id}/source` 按交互规范 18 §11-8 在既有返回结构上**追加** 7 个结果级字段（`result_type` / `execution_status` / `evaluated` / `case_name` / `device_name` / `api_name` / `result_created_at`）与 `groups[].source_task_status`，老字段与返回层级不变；完整字段表与语义见新增的 §8.3.1。§8 接口草案里的历史占位路由 `GET /tasks/{taskId}/cherry-pick-source` 同步更正为真实路由。三条裁定：①`result_type` 取落库列（INT-1510 落列 / INT-1669 读侧 DB-first），**不按** §11-8 旧文字解析 `result_data` / `result_data_path`，与候选行同口径、零 OSS 往返；②缺名与缺失态不在接口侧拼文案——`case_name` 缺名返回 null（前端出「未知用例」，不裸显 UUID），`missing=true` 行结果级字段 null、`evaluated=false`；③软删来源任务仍返其 `Task.status`（无删除标记）；软删容器「仍返 200」的旧现状已由 INT-1715 修复为 404（存活判定，见 §8.3 场景表）。本卡只扩 `source_trace` 返回内容：网关零改动、不动 proto、不改 `relations_by_container` 的共用返回结构；六类数据均批量取（一次结果多列投影 + 各自一次 `IN` + 两次名查询 gRPC），无 N+1、无对象存储往返。发版前置：迁移 ㊷（`result_type` 列，幂等）已在 `db_bootstrap` 引导链；主库该列已存在（2026-10-24 复核），新环境部署仍须重建 `db_bootstrap` 并跑 ㊷，否则容器溯源/候选接口 `UndefinedColumn` → 500。前端同步点：`CherryPickSourceTraceDto` 的结果时间改读 `result_created_at`。<br>落地分支 `agent/a/int-1714` @ `1f05b0e29`（本审计只回写文档，不改代码；`agent/agent/int-1739` 提交见卡 INT-1739 评论）。

- **2026-10-24（INT-1510 FEAT 契约审查裁定，方案一致性审计员）**：阶段 2「候选树由 candidates 首页 200 行重建」的性能与完整性收口。**裁定方向 B（服务端候选树聚合端点 `GET /tasks/cherry-picks/candidates/tree`）**，完整契约见 §8.2；方向 C 的行接口优化降级为叶明细分页与平铺辅助视图，不再承担树骨架。核心理由是完整性（命中 3614 行 / 117 任务，200 行只覆盖 5.5%，且每行唯一、(任务,用例,设备/API) 聚合不减少条目数）。同日真实库只读取证定位到成本主体：`result_type` 无列、取值经 `load_full_result_data` 在 `result_data_path` 非空时**先读 OSS**（每行 exists + download 2 次往返，`read_timeout=60`），因此把「tree 端点零 OSS 往返 + 装饰次数与行数解耦 + 首屏最坏情况 < 2 s」列为硬性验收，并要求 result_type 落库/回填一次收口。`candidates` 新增 `api_ids`/`result_type` 服务端过滤（既有契约与分页语义不变）。阶段 1 `pickable-tasks` 契约不动；前端 React 接线另卡。（裁定当日的「可挑行 2598/3614 的 DB JSON 已含该键」统计后被 INT-1669 复核修正为「顶层键命中 0 行、3614/3614 落 `default` 桶」，见 §8.2.7 第 4/5 条。）

- **2026-10-24（INT-1669 实施 + 方案一致性审计回写，实现演进裁定）**：§8.2 的行接口收口落地（`338b5cd19` 主体 + `1a5836897` 返工，均已进 V9.7.31）。`test_results.result_type` 落库列 + 写时物化，`candidates` 读侧改 DB-first、请求路径零 OSS 往返（INT-1625 的 OSS 并发预取已删除、不留开关），`api_ids` / `result_type` 为服务端过滤且 `select-all` 同口径，缺值桶对外统一 `default`。**§8.2.3 第 3 条的「duration（audio gRPC）」「evaluation 再 1 次批量」在 INT-1625 后已改共享库窄字段只读投影**（`task_service/infrastructure/acl/audio_acl_repository.py:44`、`evaluation_config_acl_repository.py:83`），真实跨服务调用只剩设备名 1 次（API 名亦已于 INT-1500 改共享库窄字段投影）。迁移编号为 **㊷**（`add_test_result_result_type_int1510.py`，㊶ 已被 INT-1679 的 device_kind 占用），已登记 README 与 db_bootstrap 引导链，**主库尚未执行**——部署须重建 db_bootstrap 镜像后先跑 ㊷ 再上 task_service 新镜像。详见 §8.2.7。

- **2026-10-24（负责人口径 + INT-1693 实施，购物车行补用例分组/标签）**：负责人 2026-10-24 于 INT-1499 定购物车三视图口径「用例视图 = 任务 → 分组/标签组织（照用例管理页）」。INT-1130 只把 `tags / group_id / group_name / duration / rounds` 装饰到挑选候选行，购物车快照行没有这组字段，用例视图只能全落「未分组 / 未设置标签」兜底桶。本卡把**候选行的用例级元信息口径原样延伸到购物车行**：
  - 落点 `GET /tasks/cherry-picks/cart` 的 `data.groups[].items[]` 行级，三字段 `tags: string[]` / `group_id: string|null` / `group_name: string|null`，来源与候选行完全一致（`test_cases → test_case_tags → tags.name` 去重保序；`test_cases.group_id → test_case_groups.name`），缺省 `[]` / `null` / `null`；用例已软删或查不到同落缺省（与 `_case_meta_map` 吞异常返回空映射的既有行为一致）。**2026-10-24 返工（测试反馈 P2）**：软删口径由 `_case_meta_map` 的用例批量查询补 `test_cases.deleted = false` 实现——用例管理页已看不到的用例一律不进映射，调用方落缺省。
  - **实现演进裁定（2026-10-24 方案一致性审计回写，INT-1737）**：本节原写「候选侧结果本就由 `TestResult.excluded` 挡掉，补过滤不改变候选可见行为」，**与实现不符，以本条为准更正**。全局软删用例（`soft_delete_testcase` / `soft_delete_testcases_by_ids`）只改 `test_cases.deleted`，不回写 `test_results.excluded`（`excluded=1` 仅由「从任务移除用例」置位），故候选查询的 `TestResult.excluded == 0` 挡不住「用例已软删但结果仍在可挑选终态任务里」的行；共享 helper 补 `deleted = false` 后，这些**候选行**的 `tags / group_id / group_name` 由真实值变为 `[]/null/null`（口径与用例管理页一致：用例已删除即归「未分组 / 未设置标签」）。主库只读实测（2026-10-24）：`excluded=0` 且引用软删用例的结果行 35 条，其中落在未删除终态任务（可挑选）上的 21 行 / 20 个用例。属预期口径统一，无功能破坏，候选端点字段与结构不变；若后续要求候选侧严格保持原值，另给 helper 加「仅存活」开关，不属本卡范围。
  - 实现位置在应用层 `cherry_pick_service.cart_get`（与 `_case_name_map` / `_fetch_device_names` 同层），按响应内全部 `source_case_id` **一次**批量回填，不改仓储 `cart_list` / `_cart_item_to_dict`（后者是公共出口，save-as-set / preview / checkout / reexecute / reevaluate 五条下游链路不应连带拿到字段）。SQL 语句数与行数无关（1 条与 N 条用例购物车语句数相同），无 N+1。
  - 购物车**不取 `duration`**：`_case_meta_map(case_ids, with_duration=False)` 跳过音频收集与 audio_service gRPC（INT-1625 实测该路径为候选慢路径），同时也不再逐用例跑 `collect_audios` 只为算一个恒为 None 的 duration；候选行 `duration` 行为不变。
  - 不动表 / 不动 proto / 不动网关（网关直返 `data` 透传，无响应模型过滤），`candidates` / `preview` 端点零改动；`groups[].source_task_id`、`source_task_name`、`total`、`invalid_item_ids` 结构与语义不变。前端消费方为 INT-1694（React 挑选合并三视图）：字段落地后用例视图分组/标签组织层自动出真名。

- **2026-10-23（续·负责人性能口径并入契约，方案一致性审计员回写）**：负责人要求契约设计必须带性能要求，已并入 §8.1「性能要求（硬性）」：①聚合在 task_service 仓储层单条 `GROUP BY` 完成，网关禁止接收候选行再聚合、响应不得下发候选行数组；②分页在服务端聚合结果上做，不得全量入内存切片；③返回体只含任务级字段 `id / name / execution_status / pickable_count / created_at`（本次按负责人口径统一字段名，替代初稿的 `task_id/task_name/task_status/result_count`），不含结果级装饰与候选树；④基线 7169 ms（candidates `per_page=200`、total=3614），本端点目标 < 2s；⑤**阶段 2 候选查询性能优化另行开卡、与本端点解耦**，互不阻塞、验收互不挂钩。前端接线字段映射同步改为 `pickable_count→count`、`execution_status→executionStatus`。

- **2026-10-23（INT-1496 FEAT 契约审查裁定，方案一致性审计员）**：挑选向导阶段 1「选择任务」清单数据源缺陷收口。原 `fetchPickableTasks` 与阶段 1 行聚合都取 `GET /tasks/cherry-picks/candidates` 首页 200 行客户端聚合，真实库候选结果行 3614 条集中在大任务（task 419 138 条、418 62 条），200 行只覆盖 2 个任务；真实库含可挑结果的终态任务 117 个（非删除任务 125，均为终态）。裁定：新增轻量端点 `GET /tasks/cherry-picks/pickable-tasks`（完整契约见 §8.1，含入选 SQL、排序、字段、分层落位与验收）；**方向 B（18 §11-3 候选树聚合端点）不实施**，留作可选增强；`candidates` 契约与分页语义不变，不做兼容层、不留双口径。前端阶段 1 消费切换与「全选当前筛选」覆盖 `total` 另立 React 接线卡；阶段 2 200 行降级边界保持，交规划师按 §11-3 或阶段 2 分页排卡。

- **2026-10-21（INT-1130 实施 + 方案一致性审计回写，实现演进裁定）**：挑选合并候选接口 `POST /tasks/cherry-picks/candidates`（`task_service/application/task/cherry_pick_service.py` `list_candidates → _query_candidate_results`）候选行在既有 `case_id/case_name/algorithm_type` 基础上补用例级元信息（交互规范 18_挑选合并 §11-7 落地）：
  - `tags: string[]` — `test_cases → test_case_tags → tags.name`（去重保序；同源用例管理列表 `TestCaseListItem.tags`）
  - `group_id` / `group_name`（`string|null`）— `test_cases.group_id → test_case_groups`（缺分组 null）
  - `duration`（`number|null`）— `collect_audios(config)` 逐音频时长累加，同用例管理列表 `total_duration` 口径（`testcase_query_service.py` 同路径，经 audio_service gRPC 一次性批量查询）；无音频/无时长 null
  - `rounds`（`number`）— `len(config.get('rounds') or [])`（轮次数，非 rounds 数组本身；空配置 0）
  数据源全部既有表，无新表、无新服务；每页一次 TestCase 批量查询（joinedload group/tags）+ 一次音频 gRPC 批量，无多余请求；容器任务（INT-657）命中行按 `result.test_case_id` 取元信息天然覆盖；网关 `list_candidates` 直返 `data` 透传（无响应模型过滤），分页 per_page≤200 语义不变。
  实现演进裁定：设计 §11-7 的 `category` 不属候选行字段——标签分类/色值由前端标签注册表（`TagItem.categoryName`）解析，与用例管理列表一致；`duration` 不读 `config.duration`（共享库 579 用例实测 config 无顶层 duration 键），按 `total_duration` 同源口径累加；字段命名保持 `duration`（设计口径），前端 adapter 桥接 `duration→totalDuration` 供 `SubViewCaseItem`/`CaseCard` 消费。旧 Vue `frontend/src/infrastructure/api/cherryPickApi.ts` `PickCandidate` 接口补 5 字段（toCamel 自动转换，契约对齐）；React 三视图/购物车分组·标签组织消费随 UX 项目接线卡（INT-1127/1128/1129）适配。
- **2026-10-17（INT-577 实施）**：专项交互规范《18_挑选合并功能交互重设计.md》（INT-576）为唯一交互口径，本卡在 V9.7.31（Vue3 + 后端微服务）落地——页签三页签终态（「合并」收编，推翻 INT-400 #13 四页签）；批量「合并任务」钮撤销为「加入挑选」（任务级整任务加购）；四步向导（复核独立步骤）+ 多级挑选树（R1-R10）+ 购物车树形分组/移除矩阵；后端统一容器列表（`merge_type` + merged ∪ cherry_pick 并集 + stats 计数）、候选行补 case/device/api/result_type、`select-all`、购物车快照补 `source_result_type`；任务级挑选不标记源任务 merged（存量历史容器除外）；algo_engineer 只读可见、写链隐藏；筛选会话级记忆不持久化。
- **2026-10-14 前向可行性评审修正**（方案一致性审计员评审，规划师落文档）：①任务分类标识弃用 `type=cherry_pick`（task.type 已物理删除），改为专有关系表存在性判定 + `cherry_pick=true` 列表参数（§5.4）；②§2 对现有合并的描述修正为 V9.7.31 实际实现（容器任务+关系展开引用，不搬结果）；③页签计数修正为现有四页签基础上新增（五页签）；④§10 状态限制措辞改显式终态集合。
- **滞后回写待办**：任务合并功能设计文档.md 仍为 V9.7.10 旧内容（含已失效的 backend/blueprints 代码段），需按 V9.7.31 实现整体回写——不阻塞本功能，另行开卡。
- **2026-10-15 负责人三拍板定稿（INT-400 #14）**：①引用方案（方案 A）；②仅终态可挑（执行中边跑边挑不做）；③跨任务配置不一致强制确认提示——§5.1/§5.2/§10/§11 已同步修正。同日 INT-400 #13 收藏收编裁定：任务列表取消独立收藏页签（收编为工具条筛选），本功能页签定稿四页签（§9 已修正）。
