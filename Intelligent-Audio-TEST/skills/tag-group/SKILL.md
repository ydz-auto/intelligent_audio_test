---
name: tag-group
description: >-
  标签与用例分组口径速查：标签列表与分类归属、标签 / 分组可见性、用例分组列表
  与用例数，以及经提案 + 审批执行的标签 / 分组写操作（新增、修改、删除、批量
  打标与标签改名）。
  触发词：标签、标签列表、标签分类、标签归属、标签可见性、批量打标、打标策略、
  重命名标签、新建标签、删除标签、用例分组、分组、分组列表、分组下、分组里、
  分组可见性、分组用例数、新建分组、修改分组、删除分组。
  不适用：用例本身的编制与轮次配置（testcase-authoring）；音频标签的素材元数据
  （audio-import）。
version: 1.1.0
owner: testcase-team
allowed-tools:
  - tool_search
  - platform_contract
  - tag_group_manage
permissions:
  - tag:read
  - group:read
  - tag:create
  - tag:update
  - tag:delete
  - group:create
  - group:update
  - group:delete
  - testcase:update
  - testcase:delete
budgets:
  maxToolCalls: 30
  maxTokens: 30000
---

# tag-group

标签与用例分组的入口：查有哪些标签 / 分组、怎么归类、某分组下多少条用例，
以及经审批的写操作（标签 / 分组 CRUD、批量打标、标签改名）。**写操作一律先提案、
等审批**——提案阶段没有副作用，批准后才回源真实接口。

## 何时用

- 想知道平台有哪些标签、某个标签属于哪个分类、标签可见性；
- 想知道用例分组有哪些、每个分组下多少条用例；
- 用户要**新建 / 修改 / 删除标签或分组**、**给一批用例批量打标 / 去标 / 重命名
  标签**：用 `tag_group_manage` 发起写提案；
- 需要判断某个标签 / 分组是 `shared` 还是 `private`、归属人是谁。

## 何时不用

- 要查某个用例的轮次、维度、参数，或给**单条**用例加 / 去标签：转
  `testcase-authoring`（单条打标用 `testcase_write.tag`）；
- 要查**音频**上的标签元数据（音频标签不是用例标签）：转 `audio-import`；
- 要查标签分类的完整 CRUD 接口口径：分类列表接口不在 Agent 工具通道里，用
  `platform_contract` 查接口前缀后说明，不要臆造端点；
- 只是问「能不能改」而不要求执行：解释字段与影响即可，不要为了「看起来办成了」
  发起不必要的写提案。

## 只读工具用法

本域的只读能力没有专用意图工具：标签 / 分组列表是**长尾只读 MCP 工具**，先检索
再按返回的 Schema 调用（本 Skill 已声明 `tool_search`，因此允许调用检索到的长尾工具）。
本 Skill 声明 `tag:read` + `group:read` 等权限码：`tag_list` 需要 `tag:read`、
`group_list` 需要 `group:read`，缺哪一个都会显式返回「无权访问」：

| 工具 | 作用 | 参数 | 目标接口 |
|---|---|---|---|
| `tag_list` | 标签列表（分页） | `page`、`per_page`、`keyword` | `GET /api/v1/tags` |
| `group_list` | 用例分组列表（含 `test_case_count`） | Schema 只声明了列表语义，不声明过滤参数 | `GET /api/v1/groups` |

规则：

1. 先 `tool_search(query="标签列表")` / `tool_search(query="用例分组")`，再按返回
   的 `inputSchema` 调用；**不要**按记忆拼参数；
2. `tag_list` 的关键词参数是 `keyword`（不是 `search`）；按分类筛选不在 Schema 里，
   需要时读返回项上的 `category_id` / `category_name` 自行归属，别传不存在的参数；
3. `group_list` 的 MCP Schema **没有**声明 `page` / `per_page` / `keyword` 等
   过滤或分页参数，按 Schema 调用即可；分组数量一律以信封的 `total` 为准，
   不要数当前页，也不要臆造 Schema 里没有的过滤参数；
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

## 写操作（`tag_group_manage`，M2 提案 + 审批）

**批准前不产生任何副作用**：工具调用先落审批单（带方法、路径、参数预览），
审批通过后才回源真实接口执行一次。回答时说明「已提交提案、等待审批」，不能把
提案说成「已经建好 / 已删掉」。

标签 / 分组 CRUD（`action` + `target_kind`）：

| action | target_kind | 必填 | 目标接口 | 权限 | 风险 |
|---|---|---|---|---|---|
| `create` | `tag` | `body`（至少 `name`） | `POST /api/v1/tags` | `tag:create` | WRITE |
| `update` | `tag` | `tag_id`、`body` | `PUT /api/v1/tags/{tag_id}` | `tag:update` | WRITE |
| `delete` | `tag` | `tag_id`（`cascade` 可选） | `DELETE /api/v1/tags/{tag_id}` | `tag:delete` | **DESTRUCTIVE** |
| `create` | `group` | `body`（至少 `name`） | `POST /api/v1/groups` | `group:create` | WRITE |
| `update` | `group` | `group_id`、`body` | `PUT /api/v1/groups/{group_id}` | `group:update` | WRITE |
| `delete` | `group` | `group_id`（`cascade` 可选） | `DELETE /api/v1/groups/{group_id}` | `group:delete` | **DESTRUCTIVE** |

- `body` 字段：标签 `name` / `description` / `color` / `category_id`；
  分组 `name` / `description` / `algorithm_type`（`name` 必填）；
- `group_id` 是 **UUID 字符串**，不是整数；
- 分组下仍有未删除用例时，`delete` 必须显式 `cascade=true`，否则接口直接拒绝；
  `cascade=true` 会**连带把分组下的用例软删进回收站**（实测文案「分组已删除，
  级联删除用例 N 条」，用例可在回收站恢复），执行前必须说清会连带多少条用例；
- 删除按 `DESTRUCTIVE` 提案，审批单能看到目标 ID；本工具不提供恢复。

### `batch_tag` 批量打标

走用例批量接口 `POST /api/v1/testcases/batch`，`batch_action` 子动作：

| batch_action | 作用 | 必填 | 权限 | 风险 |
|---|---|---|---|---|
| `add_tags` | 给一批用例加标签 | `ids`、`tags` | `testcase:update` | WRITE |
| `remove_tags` | 从一批用例移除标签 | `ids`、`tags` | `testcase:update` | WRITE |
| `rename_tag` | 重命名标签（作用于全部引用用例） | `old_tag_name`、`new_tag_name`（`ids` 传空数组） | `testcase:delete` | **DESTRUCTIVE** |

批量打标的前置条件：

1. `ids` 是**当前筛选条件下的用例 ID 集合**（可用用例列表的 `ids` 取数接口获得），
   不是页码；空集合不要提交；
2. `add_tags` 对不存在的标签名会由服务端**自动登记**标签字典（`get_or_create`，
   实测会新建标签记录，与产品页一致）；需要指定颜色 / 分类 / 可见性时先
   `create` + `target_kind=tag` 建好标签再打标；
3. `rename_tag` 是标签级动作，**不按用例筛选**：网关批量请求的 `ids` 是必填字段，
   传空数组 `[]`（工具层自动补）；它影响所有引用该标签的用例，按删除级权限与
   破坏性风险审批，执行前要说明影响范围；
4. 移动用例到另一个分组是独立能力（`POST /api/v1/groups/move-cases`），本工具
   **不承载**；用户要挪分组时说明该操作在产品页执行，不要假装已挪；
5. 同一个 tool call 的重复执行由审批幂等键领取一次；不要为了「多试一次」重复
   发起提案。

标签 / 分组可见性切换（`tag:share` / `group:share`）也不在本工具里（属分享点），
需要时说明在产品页操作。

## Gotchas

1. **只读没有专用意图工具**：必须用 `tool_search` 找到 `tag_list` / `group_list`
   再调用；未检索直接按名调用会因「未注册工具」失败。写操作有专用工具
   `tag_group_manage`，不要用长尾 MCP 写工具（`tag_create` 等）绕过审批。
2. **`tag_list` 没有分类过滤参数**：别传 `category_id`（会被静默忽略），按返回
   项的 `category_id` 归类比「伪过滤」诚实。
3. **分组名可重复**：同名分组是真实数据，回答分组数量以 `total` 为准。
4. **`group_id` 是字符串 UUID**，不是整数；用例列表按分组过滤时用的也是这个
   字符串。
5. **`public` 不是可见性取值**：只有 `shared` / `private`。
6. **标签 ≠ 音频标签**：`tag_list` 返回的是平台标签字典，音频上的标签只是名称
   引用；音频标签元数据走音频域。
7. **写提案不是写结果**：`tag_group_manage` 返回的是待审批提案；没批准就没有
   副作用，不要把「提案已提交」说成「标签已建 / 分组已删」。
8. **删除分组常被守卫拒绝**：分组下还有未删除用例且没带 `cascade=true` 时接口
   直接 400，这是业务守卫不是故障；带上 `cascade=true` 会连同分组下的用例
   一起软删（进回收站），先说明影响范围再重新提案。
9. **`rename_tag` 不按用例筛选**：网关批量请求要求 `ids` 字段（工具层补空数组），
   但它作用于全部引用用例；按用例改名不是它的能力。
10. **移动用例 / 可见性切换不在本工具里**：别拿删除 + 重建当「挪分组」，也不要
    去调长尾写工具绕过审批。

## 验收

- [ ] 标签 / 分组数量与字段来自 `tag_list` / `group_list` 的真实返回，没有编造
      ID、分类或计数；
- [ ] 先检索后调用，参数名与检索返回的 Schema 一致（`keyword` 而非 `search`）；
- [ ] 分页与总数引自接口信封的 `total` / `pages`；
- [ ] 同名分组用 `id` 区分；可见性只出现 `shared` / `private`；
- [ ] 写操作说明「提案 → 审批 → 执行」三态，没有把提案说成已经完成；
- [ ] 删除 / `rename_tag` 标注为破坏性审批并说明影响范围，没有承诺恢复；
- [ ] 批量打标说明 `add_tags` 会自动登记未知标签名，`rename_tag` 的 `ids` 为空数组；
- [ ] 移动用例 / 可见性切换明确说明不在工具能力内，没有假装已执行；
- [ ] 没有把音频标签与平台标签混为一谈。
