---
name: tag-group
description: >-
  标签与用例分组口径速查：标签列表与分类归属、标签 / 分组可见性、用例分组列表
  与用例数、批量打标的动作与前置条件（只读解释，写操作在 M2）。
  触发词：标签、标签列表、标签分类、标签归属、标签可见性、批量打标、打标策略、
  重命名标签、用例分组、分组、分组列表、分组下、分组里、分组可见性、分组用例数。
  不适用：新增 / 修改 / 删除标签或分组、批量打标执行、分组移动用例（写操作，
  M2 走提案 + 审批）；用例本身的编制与轮次配置（testcase-authoring）；音频标签
  的素材元数据（audio-import）。
version: 1.0.0
owner: testcase-team
allowed-tools:
  - tool_search
  - platform_contract
permissions:
  - tag:read
  - group:read
budgets:
  maxToolCalls: 20
  maxTokens: 30000
---

# tag-group

标签与用例分组的只读口径入口。M1 只能查：有哪些标签 / 分组、它们怎么归类、
某分组下有多少用例、批量打标有哪些动作和前置条件。**任何写动作都不执行。**

## 何时用

- 想知道平台有哪些标签、某个标签属于哪个分类、标签可见性；
- 想知道用例分组有哪些、每个分组下多少条用例；
- 用户问「怎么批量给一批用例打标 / 改名 / 挪分组」——先解释动作与前置条件，
  再说明 M2 才执行；
- 需要判断某个标签 / 分组是 `shared` 还是 `private`、归属人是谁。

## 何时不用

- 要**新增 / 修改 / 删除标签或分组**、执行批量打标：M1 不执行（M2 提案 + 审批）；
- 要查某个用例的轮次、维度、参数：转 `testcase-authoring`；
- 要查**音频**上的标签元数据（音频标签不是用例标签）：转 `audio-import`；
- 要查标签分类的完整 CRUD 接口口径：分类列表接口不在 Agent 工具通道里，用
  `platform_contract` 查接口前缀后说明，不要臆造端点。

## 工具用法

本域没有专用意图工具：标签 / 分组列表是**长尾只读 MCP 工具**，先检索再按返回的
Schema 调用（本 Skill 已声明 `tool_search`，因此允许调用检索到的长尾工具）。
本 Skill 声明 `tag:read` + `group:read` 两个权限码：`tag_list` 需要 `tag:read`、
`group_list` 需要 `group:read`，缺哪一个都会显式返回「无权访问」：

| 工具 | 作用 | 参数 | 目标接口 |
|---|---|---|---|
| `tag_list` | 标签列表（分页） | `page`、`per_page`、`keyword` | `GET /api/v1/tags` |
| `group_list` | 用例分组列表（含 `test_case_count`） | `page`、`per_page`（Schema 未声明，网关支持） | `GET /api/v1/groups` |

规则：

1. 先 `tool_search(query="标签列表")` / `tool_search(query="用例分组")`，再按返回
   的 `inputSchema` 调用；**不要**按记忆拼参数；
2. `tag_list` 的关键词参数是 `keyword`（不是 `search`）；按分类筛选不在 Schema 里，
   需要时读返回项上的 `category_id` / `category_name` 自行归属，别传不存在的参数；
3. `group_list` 不接受过滤参数；分页可传 `page` / `per_page`，分组数量以信封的
   `total` 为准，不要数当前页；
4. 分页一律看返回信封：`{items, total, page, per_page, pages}`；
5. 需要其它只读能力（如按分类看标签）时用 `platform_contract` 查接口前缀，说明
   「当前工具通道未开放该动作」，不要编接口。

## 标签字段（TagItem）

`id`、`name`、`description`、`color`、`category_id`、`category_name`、
`created_at`、`updated_at`、`visibility`、`created_by_user_id`。

- `category_id` / `category_name` 可能为 `null`（未归类），不是「分类被删」；
- `color` 是展示色原值，空就是空，不补默认色；
- `visibility`：`shared`（所有有 `tag:read` 的用户可见）/ `private`（仅归属人与
  admin 可见）。

标签**分类**（TagCategoryItem：`id`、`name`、`description`、`color`、`sort_order`、
`tag_count`、`visibility`、`created_by_user_id`）在 `GET /api/v1/tags/categories`，
该路由**未**开放为 Agent 工具；`tag_list` 结果里的 `category_name` 已够回答
「这个标签属于哪个分类」。

## 分组字段（GroupItem）

`id`（字符串 UUID）、`name`、`description`、`algorithm_type`、
`test_case_count`、`created_at`、`updated_at`、`visibility`、
`created_by_user_id`。

- `test_case_count` 是接口给的计数，直接引用，不要用列表长度推算；
- 分组名允许重复（历史数据存在同名分组），要区分请带上 `id`；
- `algorithm_type` 为空字符串表示「不限定算法类型」，不是缺失。

## 批量打标策略（M2，只解释不执行）

批量打标走用例批量接口 `POST /api/v1/testcases/batch`（权限 `testcase:update`，
删除 / 改名类动作按 `testcase:delete` 校验），`action` 取值：

| action | 作用 | 必填 |
|---|---|---|
| `add_tag` | 给一批用例加标签 | `ids`、`tags` |
| `remove_tag` | 从一批用例移除标签 | `ids`、`tags` |
| `rename_tag` | 重命名标签（作用于全部引用） | `old_tag_name`、`new_tag_name` |

执行前必须说明的前置条件：

1. `ids` 是**当前筛选条件下的用例 ID 集合**（可用列表的 `ids` 取数接口获得），
   不是页码；空集合不要提交；
2. `tags` 里的标签名不存在时，创建标签属另一个写动作（`tag:create`），批量接口
   不会替你建标签——先确认标签已存在；
3. `rename_tag` 影响所有引用该标签的用例，属破坏性动作（删除级权限），执行前
   要确认影响范围；
4. 分组调整是独立动作（`POST /api/v1/groups/move-cases`，`group:update`），
   与打标不是同一件事；
5. 以上 M1 **一律不执行**，回答时明确「当前阶段只读，写操作在 M2 提案 + 审批」。

标签 / 分组的可见性切换是写操作（`tag:share` / `group:share`），同样留 M2。

## Gotchas

1. **本域没有专用意图工具**：必须用 `tool_search` 找到 `tag_list` / `group_list`
   再调用；未检索直接按名调用会因「未注册工具」失败。
2. **`tag_list` 没有分类过滤参数**：别传 `category_id`（会被静默忽略），按返回
   项的 `category_id` 归类比「伪过滤」诚实。
3. **分组名可重复**：同名分组是真实数据，回答分组数量以 `total` 为准。
4. **`group_id` 是字符串 UUID**，不是整数；用例列表按分组过滤时用的也是这个
   字符串。
5. **`public` 不是可见性取值**：只有 `shared` / `private`。
6. **标签 ≠ 音频标签**：`tag_list` 返回的是平台标签字典，音频上的标签只是名称
   引用；音频标签元数据走音频域。
7. **写动作返回的是权限 / 审批语义**：如果用户直接要求打标，说明 M1 不执行；
   不要说「平台不支持标签」，能力有、只是当前阶段不开放写。

## 验收

- [ ] 标签 / 分组数量与字段来自 `tag_list` / `group_list` 的真实返回，没有编造
      ID、分类或计数；
- [ ] 先检索后调用，参数名与检索返回的 Schema 一致（`keyword` 而非 `search`）；
- [ ] 分页与总数引自接口信封的 `total` / `pages`；
- [ ] 同名分组用 `id` 区分；可见性只出现 `shared` / `private`；
- [ ] 涉及批量打标 / 改名 / 分组调整时，说明动作、前置条件与 M2 审批边界；
- [ ] 没有把音频标签与平台标签混为一谈。
