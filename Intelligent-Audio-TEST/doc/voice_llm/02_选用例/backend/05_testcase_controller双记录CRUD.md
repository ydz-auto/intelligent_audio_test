# 05 - testcase_controller 双记录 CRUD

## 涉及文件

- `Intelligent-Audio-TEST/backend/blueprints/testcase_bp.py` — testcase 蓝图（路由层）
- `Intelligent-Audio-TEST/backend/controllers/testcase_controller.py` — `TestCaseController`（业务逻辑）
- `Intelligent-Audio-TEST/backend/models/models.py` — `TestCase` 模型（含 `test_type` 列）
- `Intelligent-Audio-TEST/backend/schemas/testcase.py` — 请求/响应 Schema

## 现状分析（实际实现）

### 双记录架构含义

代码中的"双记录架构"指：`test_cases` 表新增 `test_type` 列（取值 `api`/`e2e`），**每条 TestCase 记录都是单类型**的独立记录（同一份 config 不再混合 API/E2E 两种类型）。需要 API 与 E2E 两类用例时，由前端**分别提交创建两条独立记录**，各自独立增删改查；纯单类型用例只创建一条记录。参见 `testcase_controller.py` L354、L671 注释，`models.py` L146，`reference_params_generator.py` L83。

实际 CRUD 方法（`TestCaseController` 静态方法，无文档设想的 `create_testcase()`/`update_testcase()` 等独立函数）：

| 方法 | 路由（蓝图） | 说明 |
|------|------|------|
| `get_all()` | GET `/api/v1/testcases` | 列表（分页 + 过滤） |
| `get_one(tc_id)` | GET `/api/v1/testcases/<tc_id>` | 详情 |
| `create()` | POST `/api/v1/testcases` | 创建单条记录 |
| `update(tc_id)` | PUT `/api/v1/testcases/<tc_id>` | 更新 |
| `delete(tc_id)` | DELETE `/api/v1/testcases/<tc_id>` | 逻辑删除（deleted=True） |
| `copy(tc_id)` | POST `/api/v1/testcases/<tc_id>/copy` | 复制单条记录 |

### 蓝图路由清单

蓝图注册：`backend/app.py` L278 `app.register_blueprint(testcase_bp, url_prefix='/api/v1/testcases')`

```python
# testcase_bp.py L4-L28（CRUD 相关路由）
testcase_bp = Blueprint('testcases', __name__)

@testcase_bp.route('', methods=['GET'])        # L6  → get_all()
@testcase_bp.route('/<tc_id>', methods=['GET'])        # L10 → get_one(tc_id)
@testcase_bp.route('', methods=['POST'])        # L14 → create()
@testcase_bp.route('/<tc_id>', methods=['PUT'])        # L18 → update(tc_id)
@testcase_bp.route('/<tc_id>', methods=['DELETE'])     # L22 → delete(tc_id)
@testcase_bp.route('/<tc_id>/copy', methods=['POST'])  # L26 → copy(tc_id)
```

| 方法 | 路径（url_prefix 下） | 蓝图函数（行号） | 控制器方法（行号） |
|------|------|------------------|--------------------|
| GET | `` | get_all（L6） | `get_all`（L310） |
| GET | `/<tc_id>` | get_one（L10） | `get_one`（L557） |
| POST | `` | create（L14） | `create`（L644） |
| PUT | `/<tc_id>` | update（L18） | `update`（L793） |
| DELETE | `/<tc_id>` | delete（L22） | `delete`（L986） |
| POST | `/<tc_id>/copy` | copy（L26） | `copy`（L1006） |

> 蓝图还包括 preview / stop_preview / batch / ids / stats / tags / export / import / template / refresh_task / ref-params 等非 CRUD 路由（testcase_bp.py L30-L88），不在本文档范围。

## 改造方案（已实现，以代码为准）

### 创建用例（POST /api/v1/testcases）

```python
# testcase_controller.py L671-L674（test_type 取值校验）
# 获取 test_type（新双记录架构）
test_type_val = data.test_type or 'api'
if test_type_val not in ['api', 'e2e']:
    return error_response(f"test_type 无效: {test_type_val}，必须为 api 或 e2e")

# testcase_controller.py L754-L765（构造单条记录）
tc_id = str(uuid.uuid4())
new_tc = TestCase(
    id=tc_id,
    name=data.name,
    description=data.description,
    group_id=group_id,
    config=merged_config,
    algorithm_params=algo_params_col,
    algorithm_type=algorithm_type,
    test_type=test_type_val,
)
```

- 入参 Schema：`TestCaseCreateSchema`（`schemas/testcase.py` L393-L457），字段：`name`（必填）、`description`、`group_id`/`group`、`test_type`（默认 `'api'`，L398）、`config`（rounds 结构）、`tags`、`audios`、`dimensions`、`background_noise_id`、`background_noise_spl`、`algorithm_type`、`algorithm_params`、`reference_params`。
- 校验：`test_type` 必须为 `api` 或 `e2e`（L673-674）；E2E 类型用例的每个音频必须指定 `playback_device_id`（L690-694、L720-721）。
- config 统一转换为 rounds 格式；`algorithm_params` 存入独立 JSON 列（按轮分组 `[{round_number, params:[{field_code, field_value}]}]`，兼容旧平面格式，L744-750）。
- 创建成功后调用 `refresh_reference_texts()` 刷新参考文本，并 `refresh_stats_cache()`（L779、L783-784）。
- 返回：`success_response(StringIdData(id=tc_id), "测试用例创建成功", 0, 201)`（L786）。
- **双记录**：一次创建只新增一条记录，**不存在"同时创建 API 与 E2E 两条记录"的逻辑**。原设计文档设想的"创建 voice_llm 用例时同时创建两条记录"实际未实现，实际为前端按用例类型分别提交 `test_type='api'` 或 `test_type='e2e'` 各建一条；查询、更新、删除也只针对单条记录处理（test_type 过滤见"查询用例"）。

### 创建说明

| 操作 | 说明 |
|------|------|
| 创建 API 记录 | 前端提交 `test_type='api'`，创建一条 `test_type='api'` 的记录 |
| 创建 E2E 记录 | 前端提交 `test_type='e2e'`，创建一条 `test_type='e2e'` 的记录（每个音频必须带 playback_device_id） |
| 单类型用例 | 只提交一次，只创建一条记录 |

### 更新用例（PUT /api/v1/testcases/<tc_id>）

```python
# testcase_controller.py L801-L810（关键校验）
if data.id and data.id != tc_id:
    return error_response("请求URL中的id与请求体中的id不一致")

tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
if not tc:
    return error_response("未找到测试用例", 404)

tc_test_type = tc.test_type or 'api'  # 使用记录的 test_type（L810）
```

- 入参 Schema：`TestCaseUpdateSchema`（`schemas/testcase.py` L520-L576），字段与 CreateSchema 基本一致（均可选）。
- **test_type 不可变**：`update()` 中没有任何对 `tc.test_type` 的赋值，请求体传入的 `test_type` 会被**静默忽略**（L810 仅读取用于 E2E 音频校验），记录类型保持创建时值。原设计设想的"传入 test_type 不一致时抛 `ValidationError`"实际未实现（不校验、不报错）。
- 更新字段：`group_id`/`group`、`name`、`description`、`config`（统一 rounds 格式，并剥离 `algorithmParams`/`referenceParamsPath`/`interferers`，L844-875）、`algorithm_params`（独立列）、`audios`（平面字段写入 rounds[0]，L899-921）、`dimensions`、`tags`、`background_noise`。
- 当音频变更、`algorithm_type` 变更或 `algorithm_params` 重叠参数变化时，触发 `refresh_reference_texts()`（L952-972），随后 `refresh_stats_cache()`（L976-977）。
- 返回：`success_response(None, "测试用例更新成功")`（L979）。

### 查询用例（GET /api/v1/testcases）

```python
# testcase_controller.py L316、L354-L356（test_type 过滤）
test_type = request.args.get('type')
...
# 按 test_type 列过滤（新双记录架构）
if test_type and test_type in ['api', 'e2e']:
    query = query.filter(TestCase.test_type == test_type)
```

- 列表 `get_all()`（L309-L427）：Query 参数 `page`/`per_page`/`keyword`/`tag`/`group_id`/**`type`**/`algorithm_type`/`dimension_id`/`view`/`include_deleted`。注意过滤 `test_type` 的**参数名是 `type`**（非 `test_type`），且仅接受 `'api'`/`'e2e'`。
- 默认过滤 `deleted=False`（除非 `include_deleted=true`，L320-321、L335-336），按 `created_at` 倒序分页返回 `TestCaseListData`；`view='tag'` 时走 `_get_tag_view()` 标签聚合视图（L323-329）。
- 详情 `get_one()`（L557-L640）：返回 `TestCaseDetailData`，含 audios / dimensions / total_duration 等派生字段。

### 删除用例（DELETE /api/v1/testcases/<tc_id>）

```python
# testcase_controller.py L986-L994（逻辑删除）
tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
if not tc:
    return error_response("未找到测试用例", 404)
tc.deleted = True
tc.updated_at = now_cst()
db.session.commit()
```

- 逻辑删除：置 `deleted=True` 并刷新 `updated_at`，随后 `refresh_stats_cache()`（L992-997）。
- 只作用于当前这条记录（不级联影响其他记录）；查询默认排除已删除记录。

### 复制用例（POST /api/v1/testcases/<tc_id>/copy）

```python
# testcase_controller.py L1013-L1025（复制单条记录）
new_id = str(uuid.uuid4())
new_tc = TestCase(
    id=new_id,
    name=f"{tc.name}_copy",
    description=tc.description,
    group_id=tc.group_id,
    config=tc.config.copy() if tc.config else {},
    algorithm_params=_copy.deepcopy(tc.algorithm_params) if tc.algorithm_params else None,
    reference_params=_copy.deepcopy(tc.reference_params) if tc.reference_params else None,
    algorithm_type=tc.algorithm_type,
    test_type=tc.test_type or 'api',   # 沿用原记录的 test_type（L1023）
)
```

- 复制逻辑内联于 `copy()`：新记录名称追加 `_copy` 后缀，深拷贝 `algorithm_params`/`reference_params`，沿用 `algorithm_type` 与 `test_type`，复制标签关联，并调用 `refresh_reference_texts()`（L1027-1032）。
- 返回：`success_response(StringIdData(id=new_id), "测试用例复制成功", 0, 201)`（L1035）。
- 原设计设想的 `_copy_single()` 辅助函数实际未实现（逻辑内联）；双记录架构下复制也只需复制当前这一条（test_type 随原记录）。

## 相关文档

- [01_TestCase模型新增字段.md](01_TestCase模型新增字段.md) — 数据模型
- [frontend/test-case/04_TestCaseListContainer_test_type.md](../../frontend/test-case/04_TestCaseListContainer_test_type.md) — 前端列表适配