# 算法配置模块 - 测试计划

> 基于 [algorithm-api-e2e.md](algorithm-api-e2e.md) 接口文档生成，目标：100% 分支覆盖率
> 测试策略：后端单元测试 → 前端单元测试 → 前后端链调（E2E）

---

## 目录

1. [测试策略总览](#1-测试策略总览)
2. [后端单元测试](#2-后端单元测试)
3. [前端单元测试](#3-前端单元测试)
4. [前后端链调测试](#4-前后端链调测试)
5. [测试环境与执行](#5-测试环境与执行)

---

## 1. 测试策略总览

### 1.1 测试分层

```
Phase 1: 后端单元测试 (pytest)
  │  覆盖 algorithm_controller.py 所有函数的所有分支
  │  使用 Flask test_client + 内存数据库
  │
  ▼ 全部通过
Phase 2: 前端单元测试 (Vitest)
  │  覆盖 AlgorithmConfigModal.vue 所有交互逻辑
  │  使用 @vue/test-utils + jsdom + mock API
  │
  ▼ 全部通过
Phase 3: 前后端链调 (E2E)
  │  真实前后端服务联调
  │  覆盖完整业务流程
  │
  ▼ 全部通过
  完成
```

### 1.2 测试框架

| 层 | 框架 | 配置文件 | 测试目录 |
|----|------|----------|----------|
| 后端 | pytest | `backend/pytest.ini`（待创建） | `backend/tests/algorithm/` |
| 前端 | Vitest + @vue/test-utils | `frontend/vite.config.ts`（追加 test 配置） | `frontend/src/components/algorithm/__tests__/` |
| E2E | curl 脚本 + 手动 UI | - | `docs/e2e-test-scripts/` |

### 1.3 分支覆盖率目标

| 模块 | 目标覆盖率 | 关键分支数 |
|------|------------|------------|
| `algorithm_controller.py` | 100% | ~180 个分支 |
| `AlgorithmConfigModal.vue` | 100% | ~45 个分支 |
| `_update_params()` | 100% | 22 个分支 |
| `_update_case_params()` | 100% | 28 个分支 |
| `_update_mappings()` | 100% | 18 个分支 |
| `_update_associated_dimensions()` | 100% | 10 个分支 |

---

## 2. 后端单元测试

### 2.1 测试文件结构

```
backend/tests/algorithm/
  ├── conftest.py                    # 公共 fixtures
  ├── test_algorithm_crud.py         # 3.1-3.5: 算法定义 CRUD
  ├── test_device_api_params.py      # 3.6-3.8: 设备/API参数 CRUD
  ├── test_case_params.py            # 3.9-3.11: 用例参数 CRUD
  ├── test_reference_params.py       # 3.12-3.14: 参考参数 CRUD
  ├── test_mappings.py               # 3.15-3.17: 参数映射 CRUD
  ├── test_dimension_relations.py    # 3.18-3.20: 维度关联
  ├── test_groups_and_options.py     # 3.21-3.22: 分组和选项来源
  └── test_internal_helpers.py       # 内部辅助函数
```

### 2.2 公共 Fixtures (conftest.py)

```python
# backend/tests/algorithm/conftest.py
import pytest
from flask import Flask
from backend.models.database import db
from backend.blueprints.algorithm_bp import algorithm_bp

@pytest.fixture(scope='function')
def app():
    """创建测试用 Flask 应用，使用内存 SQLite"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(algorithm_bp, url_prefix='/api/v1/algorithm')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """测试客户端"""
    return app.test_client()

@pytest.fixture
def sample_algorithm(client):
    """创建一个基础算法供其他测试复用"""
    resp = client.post('/api/v1/algorithm/definitions', json={
        'type': 'test_algo',
        'name': '测试算法',
        'groupId': None,
        'status': 'online'
    })
    return resp.get_json()['data']
```

### 2.3 算法定义 CRUD 测试 (test_algorithm_crud.py)

#### 2.3.1 POST /definitions — create_algorithm()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-CREATE-001 | 正常创建（仅必填字段） | `{type:"t1", name:"算法1"}` | validation通过 + type不存在 + device_params=None + api_params=None + case_params=None + mappings=None + associated_dimensions=None | 201, success=true |
| TC-CREATE-002 | 创建时name为空 | `{type:"t2", name:""}` | `req.name or req.type` → 回退用type | name="t2" |
| TC-CREATE-003 | 创建时status为空 | `{type:"t3", name:"算法3", status:null}` | `req.status or 'online'` → 回退"online" | status="online" |
| TC-CREATE-004 | 创建时display_order为空 | `{type:"t4", name:"算法4", displayOrder:null}` | `req.display_order or 0` → 回退0 | displayOrder=0 |
| TC-CREATE-005 | 创建时带device_params | `{type:"t5", ..., deviceParams:[{paramCode:"a",paramType:"text"}]}` | `req.device_params is not None` → True | deviceParams有1条 |
| TC-CREATE-006 | 创建时不带device_params | `{type:"t6", ...}` (无deviceParams字段) | `req.device_params is not None` → False | deviceParams=[] |
| TC-CREATE-007 | 创建时带api_params | `{type:"t7", ..., apiParams:[...]}` | `req.api_params is not None` → True | apiParams有数据 |
| TC-CREATE-008 | 创建时带case_params | `{type:"t8", ..., caseParams:[...]}` | `req.case_params is not None` → True | caseParams有数据 |
| TC-CREATE-009 | 创建时带mappings | `{type:"t9", ..., mappings:{device:[...]}}` | `req.mappings is not None` → True | mappings有数据 |
| TC-CREATE-010 | 创建时带associated_dimensions | `{type:"t10", ..., associatedDimensions:[...]}` | `req.associated_dimensions is not None` → True | associatedDimensions有数据 |
| TC-CREATE-011 | 重复创建type | 已存在type="t1"，再次创建 | `if AlgorithmDefinition.query.filter_by(...)` → True | 400, "already exists" |
| TC-CREATE-012 | 缺少type字段 | `{name:"无类型"}` | `model_validate` 抛异常 → except分支 | 400, "验证失败" |
| TC-CREATE-013 | 缺少name字段 | `{type:"t13"}` | `model_validate` 抛异常 → except分支 | 400, "验证失败" |
| TC-CREATE-014 | type超长（>50字符） | `{type:"a"*51, name:"超长"}` | `model_validate` 抛异常（min_length=1, max_length=50） | 400 |
| TC-CREATE-015 | name超长（>100字符） | `{type:"t15", name:"a"*101}` | `model_validate` 抛异常 | 400 |
| TC-CREATE-016 | display_order为负数 | `{type:"t16", name:"负序", displayOrder:-1}` | `model_validate` 抛异常（ge=0） | 400 |
| TC-CREATE-017 | 带所有子配置的完整创建 | 完整JSON（device+api+case+mappings+dimensions） | 所有5个if分支均为True | 所有子配置创建成功 |
| TC-CREATE-018 | reference_params字段传入 | `{type:"t18", ..., referenceParams:[...]}` | Schema接受但控制器不处理 | referenceParams=[]（需单独创建） |

#### 2.3.2 GET /definitions/{type} — get_algorithm()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-GET-001 | 获取存在的算法 | type="test_algo" | `if not algo_data` → False | 200, 返回完整数据 |
| TC-GET-002 | 获取不存在的算法 | type="nonexistent" | `if not algo_data` → True | 404, "not found" |
| TC-GET-003 | 获取已删除的算法 | 先创建再删除，再GET | `filter_by(deleted=False)` 过滤掉 | 404 |
| TC-GET-004 | 验证group_name回填 | 算法有group_id | `algo_def.group` → True → `group.name` | groupName有值 |
| TC-GET-005 | 验证group_name为null | 算法无group_id | `algo_def.group` → None → groupName=null | groupName=null |

#### 2.3.3 PUT /definitions/{type} — update_algorithm()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-UPDATE-001 | 更新name | `{name:"新名称"}` | `req_data.name is not None` → True | name更新 |
| TC-UPDATE-002 | 不传name | `{description:"描述"}` | `req_data.name is not None` → False | name不变 |
| TC-UPDATE-003 | 更新group_id | `{groupId:2}` | `req_data.group_id is not None` → True | group_id更新 |
| TC-UPDATE-004 | 更新description | `{description:"新描述"}` | `req_data.description is not None` → True | description更新 |
| TC-UPDATE-005 | 更新status | `{status:"offline"}` | `req_data.status is not None` → True | status更新 |
| TC-UPDATE-006 | 更新icon | `{icon:"icon.png"}` | `req_data.icon is not None` → True | icon更新 |
| TC-UPDATE-007 | 更新display_order | `{displayOrder:5}` | `req_data.display_order is not None` → True | display_order更新 |
| TC-UPDATE-008 | 更新device_params（全量覆盖） | `{deviceParams:[...]}` | `req_data.device_params is not None` → True | 旧参数软删除，新参数创建 |
| TC-UPDATE-009 | 更新api_params | `{apiParams:[...]}` | `req_data.api_params is not None` → True | api参数更新 |
| TC-UPDATE-010 | 更新case_params | `{caseParams:[...]}` | `req_data.case_params is not None` → True | 用例参数更新 |
| TC-UPDATE-011 | 更新mappings | `{mappings:{...}}` | `req_data.mappings is not None` → True | 映射更新 |
| TC-UPDATE-012 | 更新associated_dimensions | `{associatedDimensions:[...]}` | `req_data.associated_dimensions is not None` → True | 维度关联更新 |
| TC-UPDATE-013 | 算法不存在 | type="nonexistent" | `if not algo_def` → True | 404 |
| TC-UPDATE-014 | 空body更新 | `{}` | 所有if分支 → False | 200，数据不变 |
| TC-UPDATE-015 | device_params全量覆盖-删除旧参数 | 原有2个参数，提交1个 | `existing_ids - submitted_ids` 非空 → 软删除 | 旧参数deleted=true |

#### 2.3.4 DELETE /definitions/{type} — delete_algorithm()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-DEL-001 | 删除存在的算法 | type="test_algo" | `if not algo_def` → False | 200, deleted=true |
| TC-DEL-002 | 删除不存在的算法 | type="nonexistent" | `if not algo_def` → True | 404 |
| TC-DEL-003 | 删除已删除的算法 | 二次删除 | `filter_by(deleted=False)` → None → `if not algo_def` → True | 404 |

#### 2.3.5 GET /definitions — list_algorithms()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-LIST-001 | 无过滤参数 | 无query | `if query_params.status` → False + `if query_params.group_id` → False | 返回全部 |
| TC-LIST-002 | 按status过滤 | `?status=online` | `if query_params.status` → True | 仅返回online |
| TC-LIST-003 | 按group_id过滤 | `?groupId=1` | `if query_params.group_id` → True | 仅返回该分组 |
| TC-LIST-004 | 同时过滤 | `?status=online&groupId=1` | 两个if均为True | 交集 |
| TC-LIST-005 | 空数据库列表 | 无数据 | 查询返回空列表 | data=[], total=0 |

### 2.4 设备/API参数 CRUD 测试 (test_device_api_params.py)

#### 2.4.1 POST /params — create_param()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-PARAM-CREATE-001 | 创建device参数（默认） | `{algorithmType:"t1", paramCode:"a", paramType:"text"}` | `param_type_source != 'api'` → device分支 | 200, device参数 |
| TC-PARAM-CREATE-002 | 创建api参数 | `{paramTypeSource:"api", algorithmType:"t1", paramCode:"a", paramType:"text"}` | `param_type_source == 'api'` → True | 200, api参数 |
| TC-PARAM-CREATE-003 | param_type_source默认值 | 不传paramTypeSource | `json_data.get('param_type_source', 'device')` → 'device' | device参数 |
| TC-PARAM-CREATE-004 | 缺少algorithm_type | `{paramCode:"a", paramType:"text"}` | `if not req.algorithm_type` → True | 400 |
| TC-PARAM-CREATE-005 | 缺少param_code | `{algorithmType:"t1", paramType:"text"}` | `if not req.param_code` → True | 400 |
| TC-PARAM-CREATE-006 | device参数重复 | 同一(type,code,direction) | `if existing:` → True (device) | 400, "already exists" |
| TC-PARAM-CREATE-007 | api参数重复 | 同一(type,code,direction) | `if existing:` → True (api) | 400, "already exists" |
| TC-PARAM-CREATE-008 | 同code不同direction | code="a" direction="input" + code="a" direction="output" | 唯一约束不冲突 | 两条都创建成功 |
| TC-PARAM-CREATE-009 | device验证失败 | 缺少paramType | `model_validate` 抛异常 → except (device) | 400 |
| TC-PARAM-CREATE-010 | api验证失败 | 缺少paramType | `model_validate` 抛异常 → except (api) | 400 |
| TC-PARAM-CREATE-011 | direction默认值 | 不传direction | `req.direction or 'input'` → 'input' | direction="input" |
| TC-PARAM-CREATE-012 | param_type默认值 | 不传paramType | `req.param_type or 'text'` → 'text' | paramType="text" |
| TC-PARAM-CREATE-013 | required默认值 | 不传required | `req.required or False` → False | required=false |
| TC-PARAM-CREATE-014 | ui_order默认值 | 不传uiOrder | `req.ui_order or 0` → 0 | uiOrder=0 |
| TC-PARAM-CREATE-015 | hidden默认值 | 不传hidden | `req.hidden or False` → False | hidden=false |

#### 2.4.2 PUT /params/{id} — update_param()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-PARAM-UPD-001 | 更新device参数 | PUT /params/{device_id} | `AlgorithmDeviceParam.query` → found → `param_type='device'` | 200 |
| TC-PARAM-UPD-002 | 更新api参数 | PUT /params/{api_id} | device未找到 → `AlgorithmApiParam.query` → found → `param_type='api'` | 200 |
| TC-PARAM-UPD-003 | 参数不存在 | PUT /params/99999 | device未找到 → api未找到 → `if not param` → True | 404 |
| TC-PARAM-UPD-004 | device验证失败 | 无效JSON | `model_validate` → except (device) | 400 |
| TC-PARAM-UPD-005 | api验证失败 | 无效JSON | `model_validate` → except (api) | 400 |
| TC-PARAM-UPD-006 | 更新单个字段 | `{paramName:"新名"}` | `if value is not None` → True for param_name, False for others | 仅param_name更新 |
| TC-PARAM-UPD-007 | 更新所有可更新字段 | 全字段JSON | 所有11个`if value is not None` → True | 全字段更新 |
| TC-PARAM-UPD-008 | 空body更新 | `{}` | 所有`if value is not None` → False | 数据不变 |
| TC-PARAM-UPD-009 | 更新direction | `{direction:"output"}` | direction字段 → True | direction更新 |
| TC-PARAM-UPD-010 | 更新hidden | `{hidden:true}` | hidden字段 → True | hidden更新 |

#### 2.4.3 DELETE /params/{id} — delete_param()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-PARAM-DEL-001 | 删除device参数 | DELETE /params/{device_id} | `AlgorithmDeviceParam.query` → found → `if param:` → True | 200 |
| TC-PARAM-DEL-002 | 删除api参数 | DELETE /params/{api_id} | device未找到 → api找到 → `if param:` → True | 200 |
| TC-PARAM-DEL-003 | 参数不存在 | DELETE /params/99999 | device未找到 → api未找到 → 两个`if param:` → False | 404 |
| TC-PARAM-DEL-004 | 删除已删除的参数 | 二次删除 | `filter_by(deleted=False)` → None | 404 |

#### 2.4.4 _update_params() 内部函数分支

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-UPD-PARAMS-001 | 参数有id且存在 | `if param_id:` → True + `if param:` → True | 更新现有参数 |
| TC-UPD-PARAMS-002 | 参数有id但不存在 | `if param_id:` → True + `if param:` → False | 跳过（不创建） |
| TC-UPD-PARAMS-003 | 参数无id，code已存在 | `else:` + `if existing_param:` → True | 更新现有参数 |
| TC-UPD-PARAMS-004 | 参数无id，code不存在 | `else:` + `if existing_param:` → False | 创建新参数 |
| TC-UPD-PARAMS-005 | 全量覆盖删除旧参数 | `existing_ids - submitted_ids` 非空 + `if param:` → True | 旧参数软删除 |
| TC-UPD-PARAMS-006 | param_type='api' | `ParamModel = AlgorithmApiParam` | 操作API参数表 |
| TC-UPD-PARAMS-007 | param_type='device' | `ParamModel = AlgorithmDeviceParam` | 操作设备参数表 |
| TC-UPD-PARAMS-008 | 字段在param_data中 | `if field in param_data` → True | 更新该字段 |
| TC-UPD-PARAMS-009 | 字段不在param_data中 | `if field in param_data` → False | 跳过该字段 |

### 2.5 用例参数 CRUD 测试 (test_case_params.py)

#### 2.5.1 POST /case-params — create_case_param()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-CASE-CREATE-001 | 正常创建 | `{algorithmType, paramCode, paramType:"select"}` | validation通过 + existing=None | 200 |
| TC-CASE-CREATE-002 | 重复创建 | 同一(type, code) | `if existing:` → True | 400, "already exists" |
| TC-CASE-CREATE-003 | 缺少algorithm_type | `{paramCode:"a"}` | validation失败 → except | 400 |
| TC-CASE-CREATE-004 | 缺少param_code | `{algorithmType:"t1"}` | validation失败 → except | 400 |
| TC-CASE-CREATE-005 | param_type默认值 | 不传paramType | `req.param_type or 'text'` → 'text' | paramType="text" |
| TC-CASE-CREATE-006 | scope默认值 | 不传scope | `req.scope or 'common'` → 'common' | scope="common" |
| TC-CASE-CREATE-007 | scope=api | `{scope:"api"}` | scope有效 | scope="api" |
| TC-CASE-CREATE-008 | scope=e2e | `{scope:"e2e"}` | scope有效 | scope="e2e" |
| TC-CASE-CREATE-009 | scope非法值 | `{scope:"invalid"}` | Schema pattern验证失败 → except | 400 |
| TC-CASE-CREATE-010 | 带min/max/step/unit | `{paramType:"slider", minValue:0, maxValue:100, step:1, unit:"dB"}` | 可选字段写入 | 字段有值 |
| TC-CASE-CREATE-011 | 带options_source | `{paramType:"select", optionsSource:"languages"}` | options字段写入 | optionsSource有值 |

#### 2.5.2 PUT /case-params/{id} — update_case_param()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-CASE-UPD-001 | 正常更新 | `{paramName:"新名"}` | `if not param` → False + field in raw_data → True | 200 |
| TC-CASE-UPD-002 | 参数不存在 | PUT /case-params/99999 | `if not param` → True | 404 |
| TC-CASE-UPD-003 | 验证失败 | 无效JSON | validation → except | 400 |
| TC-CASE-UPD-004 | snake_case键名 | `{param_name:"新名"}` | `field in raw_data` → True | 更新成功 |
| TC-CASE-UPD-005 | camelCase键名 | `{paramName:"新名"}` | `field.replace('_','') in raw_data` → True | 更新成功 |
| TC-CASE-UPD-006 | 更新scope | `{scope:"api"}` | scope字段在raw_data中 | scope更新 |
| TC-CASE-UPD-007 | 更新min_value | `{minValue:50}` | min_value字段在raw_data中 | minValue更新 |
| TC-CASE-UPD-008 | 空body更新 | `{}` | 所有字段 `field in raw_data` → False | 数据不变 |
| TC-CASE-UPD-009 | 更新所有16个字段 | 全字段JSON | 16个字段分支全为True | 全字段更新 |

#### 2.5.3 DELETE /case-params/{id}

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-CASE-DEL-001 | 删除存在参数 | `if not param` → False | 200 |
| TC-CASE-DEL-002 | 删除不存在参数 | `if not param` → True | 404 |
| TC-CASE-DEL-003 | 二次删除 | `filter_by(deleted=False)` → None | 404 |

#### 2.5.4 GET /case-params — list_case_params()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-CASE-LIST-001 | 无参数 | 无query | `if scope` → False + `if algorithm_type` → False | 返回全部 |
| TC-CASE-LIST-002 | 按algorithm_type过滤 | `?algorithmType=t1` | `if algorithm_type` → True | 仅返回该算法的 |
| TC-CASE-LIST-003 | 按scope=api过滤 | `?scope=api` | `if scope` → True + scope有效 | 返回common+api |
| TC-CASE-LIST-004 | 按scope=e2e过滤 | `?scope=e2e` | `if scope` → True + scope有效 | 返回common+e2e |
| TC-CASE-LIST-005 | scope非法值 | `?scope=invalid` | `if scope and scope not in valid_scopes` → True | 400 |
| TC-CASE-LIST-006 | scope=common | `?scope=common` | scope有效 → filter条件 | 返回common |

#### 2.5.5 _update_case_params() 内部函数分支

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-UPD-CASE-001 | 参数有id且存在 | `if param_id:` → True + `if param:` → True | 更新现有 |
| TC-UPD-CASE-002 | 参数有id但不存在 | `if param_id:` → True + `if param:` → False | 跳过 |
| TC-UPD-CASE-003 | 参数无id，code已存在 | `else:` + `if dup:` → True | 更新现有 |
| TC-UPD-CASE-004 | 参数无id，code不存在 | `else:` + `if dup:` → False | 创建新参数 |
| TC-UPD-CASE-005 | 参数无id且无param_code | `else:` + `if not pc: continue` → True | 跳过该参数 |
| TC-UPD-CASE-006 | scope非法值（更新时） | `if field == 'scope' and param_data[field] not in valid_scopes` → True | `continue` 跳过scope更新 |
| TC-UPD-CASE-007 | scope合法值（更新时） | `if field == 'scope' and ...` → False | scope更新 |
| TC-UPD-CASE-008 | 字段值为None | `if field in param_data and param_data[field] is not None` → False | 跳过该字段 |
| TC-UPD-CASE-009 | 全量覆盖删除旧参数 | `existing_ids - submitted_ids` 非空 | 旧参数软删除 |
| TC-UPD-CASE-010 | scope非法值（创建时） | `raw_scope if raw_scope in valid_scopes else 'common'` → 'common' | scope回退为common |

### 2.6 参考参数 CRUD 测试 (test_reference_params.py)

#### 2.6.1 POST /reference-params — create_reference_param()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-REF-CREATE-001 | 正常创建 | `{algorithmType, code:"ref1", name:"参考1"}` | validation通过 + existing=None | 200 |
| TC-REF-CREATE-002 | 重复创建 | 同一(type, code) | `if existing:` → True | 400, "already exists" |
| TC-REF-CREATE-003 | name为空 | `{algorithmType, code:"ref2"}` | `req.name or ''` → '' | name="" |
| TC-REF-CREATE-004 | type为空 | `{algorithmType, code:"ref3"}` (无type) | `req.type or 'text'` → 'text' | paramType="text" |
| TC-REF-CREATE-005 | merge_mode为空 | 不传mergeMode | `req.merge_mode or 'join'` → 'join' | mergeMode="join" |
| TC-REF-CREATE-006 | help_text为空 | 不传helpText | `req.help_text or ''` → '' | helpText="" |
| TC-REF-CREATE-007 | 缺少algorithm_type | `{code:"ref4"}` | validation失败 → except | 400 |
| TC-REF-CREATE-008 | 缺少code | `{algorithmType:"t1"}` | validation失败 → except | 400 |
| TC-REF-CREATE-009 | 带所有字段 | 完整JSON | 所有字段写入 | 字段有值 |

#### 2.6.2 PUT /reference-params/{id} — update_reference_param()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-REF-UPD-001 | 更新code（非空） | `{code:"new_code"}` | `if req.code:` → True (truthy) | code更新 |
| TC-REF-UPD-002 | 更新code（空字符串） | `{code:""}` | `if req.code:` → False (falsy) | code不变 |
| TC-REF-UPD-003 | 更新name | `{name:"新名"}` | `if req.name is not None` → True | name更新 |
| TC-REF-UPD-004 | 更新name为null | `{name:null}` | `if req.name is not None` → False | name不变 |
| TC-REF-UPD-005 | 更新type（非空） | `{type:"audio"}` | `if req.type:` → True (truthy) | paramType更新 |
| TC-REF-UPD-006 | 更新type（空字符串） | `{type:""}` | `if req.type:` → False (falsy) | paramType不变 |
| TC-REF-UPD-007 | 更新annotation_code | `{annotationCode:"new"}` | `if req.annotation_code is not None` → True | annotationCode更新 |
| TC-REF-UPD-008 | 更新annotation_format | `{annotationFormat:"json"}` | `if req.annotation_format is not None` → True | annotationFormat更新 |
| TC-REF-UPD-009 | 更新field_path | `{fieldPath:"segments[]"}` | `if req.field_path is not None` → True | fieldPath更新 |
| TC-REF-UPD-010 | 更新merge_mode | `{mergeMode:"collect"}` | `if req.merge_mode is not None` → True | mergeMode更新 |
| TC-REF-UPD-011 | 更新help_text | `{helpText:"帮助"}` | `if req.help_text is not None` → True | helpText更新 |
| TC-REF-UPD-012 | 参数不存在 | PUT /reference-params/99999 | `if not relation` → True | 404 |
| TC-REF-UPD-013 | 验证失败 | 无效JSON | validation → except | 400 |
| TC-REF-UPD-014 | 空body更新 | `{}` | 所有if → False | 数据不变 |

#### 2.6.3 DELETE /reference-params/{id}

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-REF-DEL-001 | 删除存在参数 | `?algorithm_type=t1` | `if not param` → False | 200 |
| TC-REF-DEL-002 | 删除不存在参数 | `?algorithm_type=t1` | `if not param` → True | 404 |
| TC-REF-DEL-003 | 二次删除 | - | `filter_by(deleted=False)` → None | 404 |

### 2.7 参数映射 CRUD 测试 (test_mappings.py)

#### 2.7.1 POST /mappings — create_mapping()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-MAP-CREATE-001 | 正常创建 | `{algorithmType, sourceType:"case", sourceParam:"a", targetParam:"b"}` | validation通过 | 200 |
| TC-MAP-CREATE-002 | 缺少algorithm_type | `{sourceType:"case", ...}` | validation失败 → except | 400 |
| TC-MAP-CREATE-003 | 缺少source_type | `{algorithmType, ...}` | validation失败 → except | 400 |
| TC-MAP-CREATE-004 | 缺少source_param | `{algorithmType, sourceType, ...}` | validation失败 → except | 400 |
| TC-MAP-CREATE-005 | 缺少target_param | `{algorithmType, sourceType, sourceParam}` | validation失败 → except | 400 |
| TC-MAP-CREATE-006 | source_direction默认值 | 不传sourceDirection | `req.source_direction or 'output'` → 'output' | sourceDirection="output" |
| TC-MAP-CREATE-007 | transform_type默认值 | 不传transformType | `req.transform_type or 'none'` → 'none' | transformType="none" |
| TC-MAP-CREATE-008 | dimension_id为null | 不传dimensionId | dimensionId=None | dimensionId=null |
| TC-MAP-CREATE-009 | 带dimension_id | `{dimensionId:1}` | dimensionId有值 | dimensionId=1 |
| TC-MAP-CREATE-010 | 验证source→source字段映射 | sourceType="case" | `source=req.source_type` → source="case" | 响应中source="case" |

#### 2.7.2 PUT /mappings/{id} — update_mapping()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-MAP-UPD-001 | 更新source_type | `{sourceType:"api"}` | `if req.source_type is not None` → True | source更新 |
| TC-MAP-UPD-002 | 更新source_param | `{sourceParam:"new"}` | `if req.source_param is not None` → True | sourceParam更新 |
| TC-MAP-UPD-003 | 更新source_direction | `{sourceDirection:"input"}` | `if req.source_direction is not None` → True | sourceDirection更新 |
| TC-MAP-UPD-004 | 更新dimension_id | `{dimensionId:2}` | `if req.dimension_id is not None` → True | dimensionId更新 |
| TC-MAP-UPD-005 | 更新target_param | `{targetParam:"new"}` | `if req.target_param is not None` → True | targetParam更新 |
| TC-MAP-UPD-006 | 更新transform_type | `{transformType:"uppercase"}` | `if req.transform_type is not None` → True | transformType更新 |
| TC-MAP-UPD-007 | 映射不存在 | PUT /mappings/99999 | `if not mapping` → True | 404 |
| TC-MAP-UPD-008 | 验证失败 | 无效JSON | validation → except | 400 |
| TC-MAP-UPD-009 | 空body更新 | `{}` | 所有if → False | 数据不变 |

#### 2.7.3 DELETE /mappings/{id}

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-MAP-DEL-001 | 删除存在映射 | `if not mapping` → False | 200 |
| TC-MAP-DEL-002 | 删除不存在映射 | `if not mapping` → True | 404 |
| TC-MAP-DEL-003 | 二次删除 | `filter_by(deleted=False)` → None | 404 |

#### 2.7.4 _update_mappings() 内部函数分支

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-UPD-MAP-001 | source_type非法值 | `if source_type not in ('device','api','evaluation')` → True | 跳过该source_type |
| TC-UPD-MAP-002 | source_type=device | 在合法集合中 | 处理device映射 |
| TC-UPD-MAP-003 | source_type=api | 在合法集合中 | 处理api映射 |
| TC-UPD-MAP-004 | source_type=evaluation | 在合法集合中 | 处理evaluation映射 |
| TC-UPD-MAP-005 | 映射有id且存在 | `if mapping_id:` → True + `if mapping:` → True | 更新现有 |
| TC-UPD-MAP-006 | 映射有id但不存在 | `if mapping_id:` → True + `if mapping:` → False | 跳过 |
| TC-UPD-MAP-007 | 映射无id（evaluation） | `else:` + `source_type == 'evaluation'` → True | source从mapping_data获取 |
| TC-UPD-MAP-008 | 映射无id（device） | `else:` + `source_type == 'evaluation'` → False | source='device' |
| TC-UPD-MAP-009 | source_value合法 | `source_value in ('device','api','case','reference')` → True | source_type=source_value |
| TC-UPD-MAP-010 | source_value非法 | `source_value in (...)` → False | source_type='api'（回退） |
| TC-UPD-MAP-011 | evaluation更新时source字段 | `if source_type == 'evaluation'` → True | `mapping.source = mapping_data.get('source','case')` |
| TC-UPD-MAP-012 | 全量覆盖删除旧映射 | `existing_ids - submitted_ids` 非空 + `if mapping:` → True | 旧映射软删除 |

### 2.8 维度关联测试 (test_dimension_relations.py)

#### 2.8.1 POST /dimension-relations — create_dimension_relation()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-DIM-CREATE-001 | 正常创建 | `{algorithmType, dimensionId:1}` | validation通过 + existing=None | 200 |
| TC-DIM-CREATE-002 | 重复创建 | 同一(type, dimension_id) | `if existing:` → True | 400, "already exists" |
| TC-DIM-CREATE-003 | 缺少algorithm_type | `{dimensionId:1}` | `if not req.algorithm_type` → True | 400 |
| TC-DIM-CREATE-004 | 缺少dimension_id | `{algorithmType:"t1"}` | `if not req.dimension_id` → True | 400 |
| TC-DIM-CREATE-005 | 验证失败 | 无效JSON | validation → except | 400 |
| TC-DIM-CREATE-006 | weight默认值 | 不传weight | `weight=1.0` (Schema默认) | weight=1.0 |
| TC-DIM-CREATE-007 | is_default默认值 | 不传isDefault | `is_default=False` (Schema默认) | isDefault=false |

#### 2.8.2 PUT /dimension-relations/{id} — update_dimension_relation()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-DIM-UPD-001 | 更新weight | `{weight:0.5}` | `if req.weight is not None` → True | weight更新 |
| TC-DIM-UPD-002 | 更新is_default | `{isDefault:true}` | `if req.is_default is not None` → True | isDefault更新 |
| TC-DIM-UPD-003 | 更新dimension_id | `{dimensionId:2}` | `if req.dimension_id is not None` → True | dimensionId更新 |
| TC-DIM-UPD-004 | 关联不存在 | PUT /dimension-relations/99999 | `if not relation` → True | 404 |
| TC-DIM-UPD-005 | 验证失败 | 无效JSON | validation → except | 400 |
| TC-DIM-UPD-006 | 空body更新 | `{}` | 所有if → False | 数据不变 |
| TC-DIM-UPD-007 | weight为负数 | `{weight:-1}` | Schema验证 `ge=0` 失败 → except | 400 |

#### 2.8.3 DELETE /dimension-relations/{id}

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-DIM-DEL-001 | 删除存在关联 | `if not relation` → False | 200 |
| TC-DIM-DEL-002 | 删除不存在关联 | `if not relation` → True | 404 |

#### 2.8.4 GET /dimensions/{type} — get_algorithm_dimensions()

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-DIM-GET-001 | 有关联维度 | relations非空 | 返回维度详情列表 |
| TC-DIM-GET-002 | 无关联维度 | relations为空 | dimensions=[], default_dimension_id=null |
| TC-DIM-GET-003 | 有默认维度 | `next((r for r in relations if r.is_default), None)` → found | default_dimension_id有值 |
| TC-DIM-GET-004 | 无默认维度 | `next(...)` → None | default_dimension_id=null |
| TC-DIM-GET-005 | 维度已删除 | `Dimension.deleted == False` 过滤 | 不返回已删除维度 |

#### 2.8.5 POST /dimensions/{type} — associate_dimensions()

| 测试用例 ID | 场景 | 输入 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-DIM-ASSOC-001 | 正常批量关联 | `{dimensions:[{dimensionId:1,...}]}` | validation通过 + `if req.dimensions:` → True | 200 |
| TC-DIM-ASSOC-002 | 空dimensions | `{dimensions:[]}` | `if req.dimensions:` → False | 200, 清空所有关联 |
| TC-DIM-ASSOC-003 | dimensions为null | `{}` | `if req.dimensions:` → False (default=[]) | 200, 清空 |
| TC-DIM-ASSOC-004 | dim_data有id | `{dimensionId:1}` | `if dim_id:` → True | 创建关联 |
| TC-DIM-ASSOC-005 | dim_data无id | `{weight:1.0}` | `if dim_id:` → False | 跳过 |
| TC-DIM-ASSOC-006 | 验证失败 | 无效JSON | validation → except | 400 |
| TC-DIM-ASSOC-007 | 先清空再创建 | 已有关联+新关联 | `.update({'deleted': True})` 先执行 | 旧关联软删除，新关联创建 |

#### 2.8.6 _update_associated_dimensions() 内部函数分支

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-UPD-DIM-001 | dim_id在existing中 | `if dim_id in existing_dim_ids` → True + `if relation:` → True | 更新现有 |
| TC-UPD-DIM-002 | dim_id不在existing中 | `if dim_id in existing_dim_ids` → False | 创建新关联 |
| TC-UPD-DIM-003 | dim_id为空 | `if dim_id:` → False | 跳过 |
| TC-UPD-DIM-004 | 全量覆盖删除旧关联 | `relation.dimension_id not in submitted_dim_ids` → True | 旧关联软删除 |
| TC-UPD-DIM-005 | dim_data用id字段 | `{id:1}` | `dim_data.get('dimension_id') or dim_data.get('id')` → 1 | 使用id值 |

### 2.9 分组和选项来源测试 (test_groups_and_options.py)

#### 2.9.1 GET /groups

| 测试用例 ID | 场景 | 预期结果 |
|------------|------|----------|
| TC-GROUP-001 | 有分组数据 | 返回分组列表 |
| TC-GROUP-002 | 无分组数据 | data=[], total=0 |

#### 2.9.2 GET /options-sources

| 测试用例 ID | 场景 | 预期结果 |
|------------|------|----------|
| TC-OPTS-001 | 有配置文件 | 返回选项来源列表 |
| TC-OPTS-002 | 配置文件不存在 | `_load_options_sources_config()` → except → 返回{} → 空列表 |

### 2.10 内部辅助函数测试 (test_internal_helpers.py)

#### 2.10.1 _serialize_mappings()

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-SER-MAP-001 | dimension_id不为null | `if m.dimension_id is not None` → True | 放入evaluation |
| TC-SER-MAP-002 | dimension_id为null, source=device | `elif m.source in result` → True | 放入device |
| TC-SER-MAP-003 | dimension_id为null, source=api | `elif m.source in result` → True | 放入api |
| TC-SER-MAP-004 | dimension_id为null, source=case | `elif m.source in result` → False | 丢弃（不在result中） |

#### 2.10.2 _get_options_from_source()

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-OPTS-SRC-001 | options_source为空 | `if not options_source` → True | 返回[] |
| TC-OPTS-SRC-002 | source_type非table | `if source_type == 'table'` → False | 返回[] |
| TC-OPTS-SRC-003 | model_class为None | `if model_class:` → False | 返回[] |
| TC-OPTS-SRC-004 | 有deleted字段 | `if deleted_field:` → True | `filter_by(deleted=False)` |
| TC-OPTS-SRC-005 | 无deleted字段 | `if deleted_field:` → False | `.query.all()` |
| TC-OPTS-SRC-006 | val为None | `if val is None: continue` → True | 跳过 |
| TC-OPTS-SRC-007 | lbl为None且有fallback | `if lbl is None and fallback_label_field` → True | 使用fallback |
| TC-OPTS-SRC-008 | lbl为None且无fallback | `if lbl is None and fallback_label_field` → False + `if lbl is None` → True | lbl=str(val) |

#### 2.10.3 _serialize_algorithm()

| 测试用例 ID | 场景 | 预期分支 | 预期结果 |
|------------|------|----------|----------|
| TC-SER-ALGO-001 | 算法存在 | `if not algo_def` → False | 返回完整序列化数据 |
| TC-SER-ALGO-002 | 算法不存在 | `if not algo_def` → True | 返回None |
| TC-SER-ALGO-003 | 有group关联 | `algo_def.group` → True | group_name有值 |
| TC-SER-ALGO-004 | 无group关联 | `algo_def.group` → None | group_name=null |

---

## 3. 前端单元测试

### 3.1 测试文件结构

```
frontend/src/components/algorithm/__tests__/
  ├── AlgorithmConfigModal.test.ts     # 模态窗组件测试
  ├── AlgorithmConfigPage.test.ts      # 列表页组件测试
  └── useAlgorithmConfig.test.ts       # 组合式函数测试
```

### 3.2 AlgorithmConfigModal.vue 测试

#### 3.2.1 模态窗打开/关闭

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-MODAL-001 | create模式打开 | props: mode='create', visible=true | `if props.mode === 'create'` → True | 表单为空 |
| TC-FE-MODAL-002 | edit模式打开 | props: mode='edit', visible=true, algorithm=数据 | `if props.mode === 'create'` → False | 表单回填 |
| TC-FE-MODAL-003 | 关闭模态窗 | 点击取消/遮罩 | emit('update:visible', false) | 模态窗关闭 |
| TC-FE-MODAL-004 | 打开时加载分组 | visible变为true | `loadGroups()` 调用 | groups下拉有数据 |
| TC-FE-MODAL-005 | 打开时加载选项来源 | visible变为true | `loadOptionsSources()` 调用 | optionsSources有数据 |
| TC-FE-MODAL-006 | 打开时加载维度 | visible变为true | `loadDimensions()` 调用 | dimensions有数据 |

#### 3.2.2 表单校验

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-VALID-001 | type为空时提交 | 清空type → 点击确定 | `if (!formState.value.type)` → True | 校验失败，不发送请求 |
| TC-FE-VALID-002 | name为空时提交 | 清空name → 点击确定 | `if (!formState.value.name)` → True | 校验失败 |
| TC-FE-VALID-003 | group_id为空时提交 | 不选分组 → 点击确定 | `if (!formState.value.group_id)` → True | 校验失败 |
| TC-FE-VALID-004 | 所有必填项已填 | 填写type+name+group → 点击确定 | 所有校验通过 | 调用saveAlgorithm() |

#### 3.2.3 saveAlgorithm() 分支

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-SAVE-001 | create模式保存成功 | mode='create' → 确定 | `if props.mode === 'create'` → True → POST | emit('success') |
| TC-FE-SAVE-002 | edit模式保存成功 | mode='edit' → 确定 | `if props.mode === 'create'` → False → PUT | emit('success') |
| TC-FE-SAVE-003 | 保存失败 | API返回错误 | `catch` 分支 | console.error |
| TC-FE-SAVE-004 | statusSwitch=true | 开关打开 | `status: 'online'` | status="online" |
| TC-FE-SAVE-005 | statusSwitch=false | 开关关闭 | `status: 'offline'` | status="offline" |
| TC-FE-SAVE-006 | icon为空 | 不填icon | `icon: formState.value.icon || ''` → '' | icon="" |
| TC-FE-SAVE-007 | display_order为空 | 不填display_order | `display_order: formState.value.display_order || 0` → 0 | displayOrder=0 |
| TC-FE-SAVE-008 | bodyData组装完整性 | 提交 | 验证bodyData包含所有字段 | bodyData有13个字段 |

#### 3.2.4 参数自动保存

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-AUTOSAVE-001 | device参数失焦（有id） | 编辑已有参数 → blur | `if (param.id)` → True → PUT | 调用updateParam |
| TC-FE-AUTOSAVE-002 | device参数失焦（无id） | 新增参数 → blur | `if (param.id)` → False → POST | 调用createParam, param.id赋值 |
| TC-FE-AUTOSAVE-003 | case参数失焦（有id） | 编辑 → blur | `if (param.id)` → True → PUT | 调用updateCaseParam |
| TC-FE-AUTOSAVE-004 | case参数失焦（无id） | 新增 → blur | `if (param.id)` → False → POST | 调用createCaseParam |
| TC-FE-AUTOSAVE-005 | reference参数失焦（有id） | 编辑 → blur | `if (param.id)` → True → PUT | 调用updateReferenceParam |
| TC-FE-AUTOSAVE-006 | reference参数失焦（无id） | 新增 → blur | `if (param.id)` → False → POST | 调用createReferenceParam |
| TC-FE-AUTOSAVE-007 | type为空时不自动保存 | type="" → blur | `if (!formState.value.type)` → True → return | 不发送请求 |
| TC-FE-AUTOSAVE-008 | 自动保存失败 | API返回错误 | `catch` 分支 | console.error |
| TC-FE-AUTOSAVE-009 | debounce延迟 | 快速编辑 → blur | debounce 1000-1500ms后才发请求 | 请求延迟发送 |
| TC-FE-AUTOSAVE-010 | annotation_code自动同步 | code填写后annotation_code为空 | `annotation_code: param.annotation_code || param.code` | annotation_code=code值 |

#### 3.2.5 维度关联交互

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-DIM-001 | create模式不触发维度自动保存 | mode='create' → 编辑维度 → blur | `if (props.mode !== 'edit')` → True → return | 不发请求 |
| TC-FE-DIM-002 | edit模式触发维度自动保存 | mode='edit' → 编辑维度 → blur | `if (props.mode !== 'edit')` → False | 发请求 |
| TC-FE-DIM-003 | 维度有id时更新 | 编辑已有维度 | `if (dim.id)` → True → PUT | 调用updateDimensionRelation |
| TC-FE-DIM-004 | 维度无id时创建 | 新增维度 | `if (dim.id)` → False → POST | 调用createDimensionRelation |
| TC-FE-DIM-005 | 设置默认维度 | is_default=true | 自动将其他维度is_default设为false | 互斥逻辑 |

#### 3.2.6 Tab切换

| 测试用例 ID | 场景 | 操作 | 预期结果 |
|------------|------|------|----------|
| TC-FE-TAB-001 | 切换到参数配置 | 点击Tab | 显示设备/API参数表格 |
| TC-FE-TAB-002 | 切换到用例参数 | 点击Tab | 显示用例参数表格 |
| TC-FE-TAB-003 | 切换到参考参数 | 点击Tab | 显示参考参数表格 |
| TC-FE-TAB-004 | 切换到参数映射 | 点击Tab | 显示MappingEditor |
| TC-FE-TAB-005 | 切换到关联维度 | 点击Tab | 显示维度表格 |

#### 3.2.7 参数行操作

| 测试用例 ID | 场景 | 操作 | 预期结果 |
|------------|------|------|----------|
| TC-FE-ROW-001 | 添加设备参数行 | 点击添加按钮 | 新行出现 |
| TC-FE-ROW-002 | 删除设备参数行 | 点击删除按钮 | 行消失，乐观更新 |
| TC-FE-ROW-003 | 删除失败恢复 | API返回错误 | 行恢复 |
| TC-FE-ROW-004 | 添加用例参数行 | 点击添加 | 新行出现，预设代码可选 |
| TC-FE-ROW-005 | 添加参考参数行 | 点击添加 | 新行出现，annotation_code 预填为 formState.type |
| TC-FE-ROW-006 | 删除参考参数行（有id） | 点击删除 | 乐观删除 + API调用 deleteReferenceParam，失败恢复 |
| TC-FE-ROW-007 | 删除参考参数行（无id） | 点击删除 | 仅从本地数组移除，不发请求 |
| TC-FE-ROW-008 | 删除设备/API参数行（有id） | 点击删除 | 乐观删除 + API调用 deleteParam，失败恢复 |
| TC-FE-ROW-009 | 删除设备/API参数行（无id） | 点击删除 | 仅从本地数组移除 |
| TC-FE-ROW-010 | 删除用例参数行（有id） | 点击删除 | 乐观删除 + API调用 deleteCaseParam，失败恢复 |
| TC-FE-ROW-011 | 删除用例参数行（无id） | 点击删除 | 仅从本地数组移除 |
| TC-FE-ROW-012 | 添加关联维度行 | 点击添加 | 新行出现，dimension_id=null, weight=1.0, is_default=false |
| TC-FE-ROW-013 | 删除关联维度（edit模式有id） | 点击删除 | 本地移除 + API调用 deleteDimensionRelation |
| TC-FE-ROW-014 | 删除关联维度（create模式） | 点击删除 | 仅本地移除 |
| TC-FE-ROW-015 | 删除关联维度（edit模式无id有tempId） | 点击删除 | 仅本地移除，不调API |

#### 3.2.8 功能特性快捷开关（Feature Bundles）

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-BND-001 | Bundle已激活时取消 | toggleBundle → hasAll=true | `if (hasAll)` → True | 删除该 bundle 所有参数 |
| TC-FE-BND-002 | Bundle未激活时添加 | toggleBundle → hasAll=false | `if (hasAll)` → False → else | 添加缺失参数，使用 PARAM_CODE_PRESETS |
| TC-FE-BND-003 | Bundle部分参数已存在 | toggleBundle → 部分codes已有 | `if (!codes.has(code))` → False 跳过 | 只添加缺失的参数 |
| TC-FE-BND-004 | isBundleActive 全部存在 | 检查bundle状态 | `bundle.params.every()` → True | 返回 true |
| TC-FE-BND-005 | isBundleActive 部分缺失 | 检查bundle状态 | `bundle.params.every()` → False | 返回 false |
| TC-FE-BND-006 | isBundleActive bundle不存在 | 传入无效key | `if (!bundle)` → True | 返回 false |
| TC-FE-BND-007 | toggleBundle 后自动保存 | 添加新参数后 | `saveCaseParams()` → `if (!p.id && p.param_code)` → True | 调用 autoSaveCaseParams |
| TC-FE-BND-008 | saveCaseParams 无新参数 | 所有参数已有id | `if (!p.id && p.param_code)` → False | 跳过保存 |

#### 3.2.9 参数类型变更与预设填充

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-PTY-001 | 切换参数类型为非select | handleCaseParamTypeChange | `if (param.param_type !== 'select')` → True | 设置 component + 清空 options 字段 |
| TC-FE-PTY-002 | 切换参数类型为select | handleCaseParamTypeChange | `if (param.param_type !== 'select')` → False → else | component='select' |
| TC-FE-PTY-003 | 预设代码匹配且有param_name | handleParamCodeSelect | `if (preset && !param.param_name)` → True | 填充所有预设字段 |
| TC-FE-PTY-004 | 预设代码匹配但已有param_name | handleParamCodeSelect | `!param.param_name` → False | 不覆盖 param_name |
| TC-FE-PTY-005 | 预设代码不匹配 | handleParamCodeSelect | `if (preset && ...)` → preset为undefined | 不填充任何字段 |
| TC-FE-PTY-006 | getDefaultComponent 已知类型 | 传入 'slider' | `typeComponentMap[paramType]` → 'slider' | 返回 'slider' |
| TC-FE-PTY-007 | getDefaultComponent 未知类型 | 传入 'unknown' | `typeComponentMap[paramType]` → undefined → `\|\| 'input'` | 返回 'input' |

#### 3.2.10 参考参数自动同步

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-REF-001 | annotation_code为空且code有值 | handleReferenceParamBlur | `if (!param.annotation_code && param.code)` → True | annotation_code = code |
| TC-FE-REF-002 | annotation_code已有值 | handleReferenceParamBlur | `!param.annotation_code` → False | 不覆盖 |
| TC-FE-REF-003 | code为空时不保存 | handleReferenceParamBlur | `if (!formState.type \|\| !param.code)` → True | return，不保存 |
| TC-FE-REF-004 | 参考参数有id时更新 | autoSaveReferenceParams | `if (param.id)` → True | 调用 updateReferenceParam |
| TC-FE-REF-005 | 参考参数无id时创建 | autoSaveReferenceParams | `if (param.id)` → False → else | 调用 createReferenceParam，回写id |

#### 3.2.11 模式切换与取消

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-MOD-001 | list模式内部切换到create | handleCreate | `internalMode.value = 'create'` | 重置表单 + 切换模式 |
| TC-FE-MOD-002 | edit模式从列表进入 | handleEdit | API成功 → `if (result)` → True | 填充formState + internalMode='edit' |
| TC-FE-MOD-003 | edit模式API失败 | handleEdit | catch块 | console.error，不切换模式 |
| TC-FE-MOD-004 | handleCancel 内部模式不匹配 | internalMode !== props.mode 且 props.mode='list' | `if (internalMode.value !== props.mode && props.mode === 'list')` → True | 回退到 list 模式 |
| TC-FE-MOD-005 | handleCancel 正常关闭 | 模式匹配或非list | else 分支 | emit('update:visible', false) |
| TC-FE-MOD-006 | handleOk select模式 | effectiveMode='select' | `if (effectiveMode.value === 'select')` → True | emit select + 关闭 |
| TC-FE-MOD-007 | handleOk select无editData | effectiveMode='select', editData=null | `if (props.editData)` → False | return，不emit |
| TC-FE-MOD-008 | handleOk 必填校验失败 | type/name/group_id 缺失 | `if (!formState.type \|\| !formState.name \|\| !formState.group_id)` → True | alert 提示 |
| TC-FE-MOD-009 | handleOk edit模式保存 | 校验通过 + edit模式 | `if (effectiveMode.value === 'edit')` → True | 调用 updateDefinition |
| TC-FE-MOD-010 | handleOk create模式保存 | 校验通过 + create模式 | else 分支 | 调用 createDefinition |

#### 3.2.12 状态切换与删除

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-ACT-001 | 切换online→offline | handleToggleStatus | `record.status === 'online'` → True | newStatus='offline' |
| TC-FE-ACT-002 | 切换offline→online | handleToggleStatus | `record.status === 'online'` → False | newStatus='online' |
| TC-FE-ACT-003 | 确认删除-确认 | confirmDelete → confirmed=true | `if (confirmed)` → True | 调用 executeDelete |
| TC-FE-ACT-004 | 确认删除-取消 | confirmDelete → confirmed=false | `if (confirmed)` → False | 不执行删除 |
| TC-FE-ACT-005 | executeDelete record为空 | executeDelete(null) | `if (!record)` → True | return |
| TC-FE-ACT-006 | 删除成功 | executeDelete → API成功 | `result.success` → True | loadAlgorithms + 切回list |
| TC-FE-ACT-007 | 删除失败 | executeDelete → API失败 | `result.success` → False | console.error |

#### 3.2.13 映射折叠与更新

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-MAP-001 | 折叠设备映射 | toggleMapping('device') | `mappingExpanded.value[key] = !...` | device 折叠 |
| TC-FE-MAP-002 | 折叠API映射 | toggleMapping('api') | 同上 | api 折叠 |
| TC-FE-MAP-003 | 折叠评估映射 | toggleMapping('evaluation') | 同上 | evaluation 折叠 |
| TC-FE-MAP-004 | 更新设备映射 | updateMappings('device', [...]) | `formState.mappings[componentType] = mappings` | 设备映射更新 |
| TC-FE-MAP-005 | 更新API映射 | updateMappings('api', [...]) | 同上 | API映射更新 |
| TC-FE-MAP-006 | 更新评估映射 | updateMappings('evaluation', [...]) | 同上 | 评估映射更新 |

#### 3.2.14 computed 属性分支

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CMP-001 | currentParams device类型 | paramConfigType='device' | `if (paramConfigType.value === 'device')` → True | 返回 device_params |
| TC-FE-CMP-002 | currentParams api类型 | paramConfigType='api' | `else if (paramConfigType.value === 'api')` → True | 返回 api_params |
| TC-FE-CMP-003 | currentParams case类型 | paramConfigType='case' | 两个条件都False | 返回 [] |
| TC-FE-CMP-004 | filteredAlgorithms 有搜索词 | searchKeyword非空 | `if (!searchKeyword.value)` → False | 过滤结果 |
| TC-FE-CMP-005 | filteredAlgorithms 无搜索词 | searchKeyword空 | `if (!searchKeyword.value)` → True | 返回全部 |
| TC-FE-CMP-006 | getGroupTagClass 已知分组 | groupName='翻译' | `classes[groupName]` → 'pending' | 返回 'pending' |
| TC-FE-CMP-007 | getGroupTagClass 未知分组 | groupName='未知' | `classes[groupName]` → undefined → `\|\| ''` | 返回 '' |
| TC-FE-CMP-008 | getGroupTagClass 空分组 | groupName=undefined | `if (!groupName)` → True | 返回 '' |
| TC-FE-CMP-009 | modalWidth list模式 | effectiveMode='list' | `if (effectiveMode.value === 'list')` → True | '700px' |
| TC-FE-CMP-010 | modalWidth 非list模式 | effectiveMode='edit' | False | '1200px' |
| TC-FE-CMP-011 | okText select模式 | effectiveMode='select' | `if (effectiveMode.value === 'select')` → True | '选择' |
| TC-FE-CMP-012 | okText 非select模式 | effectiveMode='edit' | False | '确定' |
| TC-FE-CMP-013 | mainDimensions 有dimensionType | d.dimensionType='main' | `d.dimensionType === 'main' \|\| !d.dimensionType` → True | 包含 |
| TC-FE-CMP-014 | mainDimensions 无dimensionType | d.dimensionType=undefined | `!d.dimensionType` → True | 包含 |
| TC-FE-CMP-015 | mainDimensions 子维度 | d.dimensionType='sub' | 两个条件都False | 排除 |

#### 3.2.15 watch 与生命周期

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-WCH-001 | visible变为true且list模式 | watch visible | `if (effectiveMode.value === 'list')` → True | loadAlgorithms |
| TC-FE-WCH-002 | visible变为true且create模式 | watch visible | `else if (effectiveMode.value === 'create')` → True | resetForm |
| TC-FE-WCH-003 | visible变为true且edit模式 | watch visible | 两个条件都False | 不加载/重置 |
| TC-FE-WCH-004 | visible变为false | watch visible | `if (visible)` → False | 不执行任何操作 |
| TC-FE-WCH-005 | watch mode=edit有editData | watch [mode, editData] | `if (mode === 'edit' && editData)` → True | 填充formState |
| TC-FE-WCH-006 | watch mode=edit无editData | watch [mode, editData] | `mode === 'edit' && editData` → False | 不填充 |
| TC-FE-WCH-007 | watch mode=create | watch [mode, editData] | `else if (mode === 'create')` → True | resetForm |
| TC-FE-WCH-008 | watch mode=list | watch [mode, editData] | 两个条件都False | 不操作 |

---

### 3.3 AlgorithmConfigPage.vue 测试

#### 3.3.1 列表加载与渲染

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-PG-001 | onMounted 加载 | 组件挂载 | `onMounted` → loadAlgorithms + loadGroups | 两个API调用 |
| TC-FE-PG-002 | loadAlgorithms 成功 | API返回 success=true | `if (result.success)` → True | algorithms赋值 + normalizeAlgorithmFields |
| TC-FE-PG-003 | loadAlgorithms 失败 | API返回 success=false | `if (result.success)` → False | 不赋值 |
| TC-FE-PG-004 | loadAlgorithms 网络错误 | fetch抛异常 | catch块 | console.error |
| TC-FE-PG-005 | loadGroups 成功 | API返回 success=true | `if (result.success)` → True | groups赋值 |
| TC-FE-PG-006 | loadGroups 失败 | API异常 | catch块 | console.error |
| TC-FE-PG-007 | loading状态 | 加载中 | `v-if="loading"` → True | 显示加载中 |
| TC-FE-PG-008 | 空数据 | loading=false, 列表空 | `v-else-if="filteredAlgorithms.length === 0"` → True | 显示"暂无数据" |
| TC-FE-PG-009 | 有数据 | loading=false, 列表非空 | `v-else` → True | 渲染表格行 |

#### 3.3.2 搜索与过滤

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-PG-010 | 按类型搜索 | 输入关键词 | `if (searchKeyword.value)` → True → filter type | 过滤结果 |
| TC-FE-PG-011 | 按名称搜索 | 输入关键词 | `a.name.toLowerCase().includes(keyword)` → True | 过滤结果 |
| TC-FE-PG-012 | 无搜索词 | searchKeyword空 | `if (searchKeyword.value)` → False | 返回全部 |
| TC-FE-PG-013 | 按分组过滤 | groupFilter非空 | `if (groupFilter.value !== '')` → True | 过滤 group_id |
| TC-FE-PG-014 | 不按分组过滤 | groupFilter空 | `if (groupFilter.value !== '')` → False | 不过滤 |
| TC-FE-PG-015 | 按状态过滤 | statusFilter='online' | `if (statusFilter.value !== '')` → True | 过滤 status |
| TC-FE-PG-016 | 不按状态过滤 | statusFilter空 | `if (statusFilter.value !== '')` → False | 不过滤 |
| TC-FE-PG-017 | 搜索重置页码 | handleSearch | `currentPage.value = 1` | 页码重置 |
| TC-FE-PG-018 | 过滤重置页码 | handleFilter | `currentPage.value = 1` | 页码重置 |

#### 3.3.3 分页

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-PG-019 | 上一页（非第一页） | handlePrevPage | `if (currentPage.value > 1)` → True | currentPage-- |
| TC-FE-PG-020 | 上一页（第一页） | handlePrevPage | `if (currentPage.value > 1)` → False | 不变 |
| TC-FE-PG-021 | 下一页（非最后页） | handleNextPage | `if (currentPage.value < totalPages)` → True | currentPage++ |
| TC-FE-PG-022 | 下一页（最后页） | handleNextPage | `if (currentPage.value < totalPages)` → False | 不变 |
| TC-FE-PG-023 | 跳转指定页 | handleGoToPage(3) | 直接赋值 | currentPage=3 |
| TC-FE-PG-024 | 修改每页条数 | handlePageSizeChange(20) | `pageSize.value = newSize; currentPage.value = 1` | 更新+重置 |
| TC-FE-PG-025 | 显示分页器 | 数据>pageSize | `v-if="filteredAlgorithms.length > pageSize"` → True | 显示PaginationComponent |
| TC-FE-PG-026 | 隐藏分页器 | 数据<=pageSize | `v-if="filteredAlgorithms.length > pageSize"` → False | 不显示 |

#### 3.3.4 CRUD操作

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-PG-027 | 新建算法 | handleCreate | modalMode='create', currentAlgorithm=null, visible=true | 打开模态窗 |
| TC-FE-PG-028 | 编辑算法 | handleEdit(record) | modalMode='edit', 深拷贝record, loadAlgorithmDetail | 加载详情后打开 |
| TC-FE-PG-029 | loadAlgorithmDetail 成功 | API返回 success=true | `if (result.success && result.data)` → True | currentAlgorithm赋值 |
| TC-FE-PG-030 | loadAlgorithmDetail 失败 | API返回 success=false | `if (result.success && result.data)` → False | 不赋值 |
| TC-FE-PG-031 | 复制算法-确认 | handleClone → confirmed=true | `if (!confirmed)` → False → 继续 | 执行复制 |
| TC-FE-PG-032 | 复制算法-取消 | handleClone → confirmed=false | `if (!confirmed)` → True | return |
| TC-FE-PG-033 | 复制算法-详情成功 | detailResult.success=true | `if (detailResult.success && detailResult.data)` → True | 使用详情数据 |
| TC-FE-PG-034 | 复制算法-详情失败 | detailResult.success=false | False | 使用record数据 |
| TC-FE-PG-035 | 复制算法-创建成功 | result.success=true | `if (result.success)` → True | loadAlgorithms |
| TC-FE-PG-036 | 复制算法-创建失败 | result.success=false | False | console.error |
| TC-FE-PG-037 | 删除-确认 | confirmDelete → confirmed=true | `if (confirmed)` → True | executeDelete |
| TC-FE-PG-038 | 删除-取消 | confirmDelete → confirmed=false | `if (confirmed)` → False | 不删除 |
| TC-FE-PG-039 | executeDelete record为空 | executeDelete(null) | `if (!record)` → True | return |
| TC-FE-PG-040 | 删除成功且在详情页 | result.success + activeTab='detail' | `if (result.success)` → True + `if (activeTab.value === 'detail')` → True | loadAlgorithms + 切回list |
| TC-FE-PG-041 | 删除成功且在列表页 | result.success + activeTab='list' | `if (activeTab.value === 'detail')` → False | loadAlgorithms |
| TC-FE-PG-042 | 删除失败 | result.success=false | False | console.error |

#### 3.3.5 Tab切换与详情视图

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-PG-043 | 切换到list | handleTabChange('list') | `if (tabKey === 'list')` → True | currentAlgorithm=null |
| TC-FE-PG-044 | 切换到detail | handleTabChange('detail') | `if (tabKey === 'list')` → False | 保留currentAlgorithm |
| TC-FE-PG-045 | 详情页有算法 | activeTab='detail', currentAlgorithm有值 | `v-if="currentAlgorithm"` → True | 显示详情 |
| TC-FE-PG-046 | 详情页无算法 | activeTab='detail', currentAlgorithm=null | `v-if="currentAlgorithm"` → False → v-else | 显示空状态 |
| TC-FE-PG-047 | group_name有值 | record.group_name='翻译' | `v-if="record.group_name"` → True | 显示标签 |
| TC-FE-PG-048 | group_name为空 | record.group_name=undefined | `v-if="record.group_name"` → False → v-else | 显示'-' |
| TC-FE-PG-049 | status=online | record.status='online' | `record.status === 'online'` → True | 显示'上线'+active样式 |
| TC-FE-PG-050 | status=offline | record.status='offline' | `record.status === 'online'` → False | 显示'下线'+inactive样式 |
| TC-FE-PG-051 | 参数为空 | currentAlgorithm.params=[] | `v-if="!currentAlgorithm.params?.length"` → True | 显示'暂无参数' |
| TC-FE-PG-052 | 参数非空 | currentAlgorithm.params有值 | `v-if="!currentAlgorithm.params?.length"` → False → v-else | 渲染参数行 |
| TC-FE-PG-053 | 映射为空 | mappings[tab]=[] | `v-if="!currentAlgorithm.mappings?.[activeMappingTab]?.length"` → True | 显示'暂无映射' |
| TC-FE-PG-054 | 映射非空 | mappings[tab]有值 | False → v-else | 渲染映射行 |
| TC-FE-PG-055 | getGroupName 已知 | group='basic' | `names[group]` → '基本配置' | 返回'基本配置' |
| TC-FE-PG-056 | getGroupName 未知 | group='unknown' | `names[group]` → undefined → `\|\| group` | 返回'unknown' |
| TC-FE-PG-057 | getGroupName 空 | group=undefined | `names[group || '']` → undefined → `\|\| group` → undefined → `\|\| '-'` | 返回'-' |

#### 3.3.6 normalizeAlgorithmFields 字段兼容

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-PG-058 | camelCase字段 | algo.groupId有值 | `algo.groupId ?? algo.group_id` → groupId | 使用camelCase值 |
| TC-FE-PG-059 | snake_case字段 | algo.group_id有值, groupId无 | `algo.groupId ?? algo.group_id` → group_id | 使用snake_case值 |
| TC-FE-PG-060 | mappings缺失 | algo.mappings=undefined | `algo.mappings ?? { device: [], api: [], evaluation: [] }` | 使用默认空对象 |

---

### 3.4 useAlgorithmConfig.ts 测试

#### 3.4.1 loadAlgorithms

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-001 | 加载成功 | API返回 success=true | `if (result.success)` → True | algorithms赋值, 返回数组 |
| TC-FE-CFG-002 | 加载失败-success=false | API返回 success=false | `if (result.success)` → False | message.error, 返回[] |
| TC-FE-CFG-003 | 加载失败-网络错误 | fetch抛异常 | catch块 | message.error, 返回[] |
| TC-FE-CFG-004 | loading状态正确 | 加载前后 | finally块 | loading: true→false |

#### 3.4.2 getAlgorithm

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-005 | 获取成功 | API返回 success=true | `if (result.success)` → True | 返回 result.data |
| TC-FE-CFG-006 | 获取失败 | API返回 success=false | `if (result.success)` → False | 返回 null |
| TC-FE-CFG-007 | 获取异常 | fetch抛异常 | catch块 | message.error, 返回 null |

#### 3.4.3 getFormSchema（缓存）

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-008 | 缓存命中 | formSchemas.has(type) → True | `if (formSchemas.value.has(algorithmType))` → True | 返回缓存 |
| TC-FE-CFG-009 | 缓存未命中-成功 | formSchemas.has(type) → False, API成功 | `if (result.success && result.data)` → True | 缓存+返回schema |
| TC-FE-CFG-010 | 缓存未命中-失败 | API success=false | `if (result.success && result.data)` → False | 返回 null |
| TC-FE-CFG-011 | 缓存未命中-异常 | fetch抛异常 | catch块 | message.error, 返回 null |
| TC-FE-CFG-012 | 清除缓存 | clearFormSchemaCache() | `formSchemas.value.clear()` | Map清空 |

#### 3.4.4 getAlgorithmOptions

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-013 | 成功 | API返回 success=true | `if (result.success)` → True | 返回 algorithms数组 |
| TC-FE-CFG-014 | 失败 | API返回 success=false | `if (result.success)` → False | 返回 [] |
| TC-FE-CFG-015 | 异常 | fetch抛异常 | catch块 | message.error, 返回 [] |

#### 3.4.5 getParamOptions

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-016 | 成功 | API返回 success=true | `if (result.success)` → True | 返回 options对象 |
| TC-FE-CFG-017 | 失败 | API返回 success=false | `if (result.success)` → False | 返回 {} |
| TC-FE-CFG-018 | 异常 | fetch抛异常 | catch块 | 返回 {} (无message) |

#### 3.4.6 getAssociatedDimensions

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-019 | 成功 | API返回 success=true | `if (result.success)` → True | 返回 dimensions数据 |
| TC-FE-CFG-020 | 失败 | API返回 success=false | `if (result.success)` → False | 返回 null |
| TC-FE-CFG-021 | 异常 | fetch抛异常 | catch块 | 返回 null (无message) |

#### 3.4.7 createAlgorithm / updateAlgorithm / deleteAlgorithm

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-022 | create成功 | API返回 success=true | `if (result.success)` → True | message.success + loadAlgorithms + true |
| TC-FE-CFG-023 | create失败 | API返回 success=false | `if (result.success)` → False | message.error + false |
| TC-FE-CFG-024 | create异常 | fetch抛异常 | catch块 | message.error + false |
| TC-FE-CFG-025 | update成功 | API返回 success=true | `if (result.success)` → True | message.success + loadAlgorithms + true |
| TC-FE-CFG-026 | update失败 | API返回 success=false | `if (result.success)` → False | message.error + false |
| TC-FE-CFG-027 | update异常 | fetch抛异常 | catch块 | message.error + false |
| TC-FE-CFG-028 | delete成功 | API返回 success=true | `if (result.success)` → True | message.success + loadAlgorithms + true |
| TC-FE-CFG-029 | delete失败 | API返回 success=false | `if (result.success)` → False | message.error + false |
| TC-FE-CFG-030 | delete异常 | fetch抛异常 | catch块 | message.error + false |

#### 3.4.8 getCaseAlgorithmParams

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-031 | algorithmType为空 | getCaseAlgorithmParams('') | `if (!algorithmType)` → True | 返回 [] |
| TC-FE-CFG-032 | 成功且有参数 | API返回 parameters非空 | `result?.parameters \|\| []` → 有值 | 返回转换后的数组 |
| TC-FE-CFG-033 | 成功但无参数 | API返回 parameters=[] | `result?.parameters \|\| []` → [] | 返回 [] |
| TC-FE-CFG-034 | 异常 | API抛异常 | catch块 | console.error, 返回 [] |

#### 3.4.9 getAlgorithmIcon

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-035 | 已知分组 | groupName='翻译' | `iconMap[groupName]` → 'fa-globe' | 返回 'fa-globe' |
| TC-FE-CFG-036 | 未知分组 | groupName='未知' | `iconMap[groupName]` → undefined → `iconMap['general']` | 返回 'fa-cog' |
| TC-FE-CFG-037 | 空分组 | groupName=undefined | `iconMap[groupName \|\| '']` → `iconMap['']` → undefined → `iconMap['general']` | 返回 'fa-cog' |

#### 3.4.10 useAlgorithmForm

| 测试用例 ID | 场景 | 操作 | 预期分支 | 预期结果 |
|------------|------|------|----------|----------|
| TC-FE-CFG-038 | loadSchema无algorithmType | algorithmType=null | `if (!algorithmType)` → True | schema=null, return |
| TC-FE-CFG-039 | loadSchema有algorithmType | algorithmType='asr' | `if (!algorithmType)` → False | Promise.all加载 |
| TC-FE-CFG-040 | resetForm有defaultValue | field.defaultValue有值且!hidden | `if (field.defaultValue !== undefined && !field.hidden)` → True | 填充默认值 |
| TC-FE-CFG-041 | resetForm无defaultValue | field.defaultValue=undefined | `if (field.defaultValue !== undefined && !field.hidden)` → False | 不填充 |
| TC-FE-CFG-042 | resetForm hidden字段 | field.hidden=true | `!field.hidden` → False | 不填充 |

---

## 4. 前后端链调测试（E2E Integration）

> **前置条件**：后端单元测试 100% 通过 + 前端单元测试 100% 通过

### 4.1 完整创建算法流程

| 测试用例 ID | 场景 | 前端操作 | 后端验证 | 预期结果 |
|------------|------|----------|----------|----------|
| TC-E2E-001 | 新建算法-基本信息 | 填写type/name/group_id/status → 点击确定 | POST /definitions → 校验schema → 写DB | 返回201 + algorithm_id |
| TC-E2E-002 | 新建算法-重复type | 填写已存在的type | POST /definitions → 查询已存在 → 返回409 | 前端显示错误消息 |
| TC-E2E-003 | 新建算法-type边界 | type长度=1（最小） | POST /definitions → min_length=1 通过 | 创建成功 |
| TC-E2E-004 | 新建算法-type超长 | type长度=51（超限） | POST /definitions → max_length=50 失败 | 返回422验证错误 |
| TC-E2E-005 | 新建算法-name边界 | name长度=100（最大） | POST /definitions → max_length=100 通过 | 创建成功 |
| TC-E2E-006 | 新建算法-name超长 | name长度=101 | POST /definitions → max_length=100 失败 | 返回422 |
| TC-E2E-007 | 新建算法-display_order=0 | display_order=0 | POST /definitions → ge=0 通过 | 创建成功 |
| TC-E2E-008 | 新建算法-display_order负数 | display_order=-1 | POST /definitions → ge=0 失败 | 返回422 |
| TC-E2E-009 | 新建算法-含设备参数 | 填写device_params → 确定 | POST /definitions → _update_params → 写DB | 算法+参数同时创建 |
| TC-E2E-010 | 新建算法-含用例参数 | 填写case_params → 确定 | POST /definitions → _update_case_params → 写DB | 算法+用例参数同时创建 |
| TC-E2E-011 | 新建算法-含映射 | 填写mappings → 确定 | POST /definitions → _update_mappings → 写DB | 算法+映射同时创建 |
| TC-E2E-012 | 新建算法-含关联维度 | 填写associated_dimensions → 确定 | POST /definitions → _update_associated_dimensions → 写DB | 算法+维度关联同时创建 |
| TC-E2E-013 | 新建算法-含参考参数 | 填写reference_params → 确定 | POST /definitions → _update_reference_params → 写DB | 算法+参考参数同时创建 |
| TC-E2E-014 | 新建算法-全子配置 | 同时填写所有子配置 | POST /definitions → 5个子配置全部更新 | 全部创建成功 |

### 4.2 编辑算法流程

| 测试用例 ID | 场景 | 前端操作 | 后端验证 | 预期结果 |
|------------|------|----------|----------|----------|
| TC-E2E-015 | 编辑-加载详情 | 点击编辑 → GET /definitions/{type} | 查询DB → 序列化返回 | 前端填充表单 |
| TC-E2E-016 | 编辑-修改名称 | 修改name → 确定 | PUT /definitions/{type} → 更新DB | 返回200 + 更新后数据 |
| TC-E2E-017 | 编辑-不存在的type | 编辑已被删除的算法 | PUT /definitions/{type} → 查询不存在 → 404 | 前端显示错误 |
| TC-E2E-018 | 编辑-添加新设备参数 | 在已有参数基础上添加新行 → blur | PUT /definitions/{type} → _update_params → 新参数无id → POST | 新参数创建成功 |
| TC-E2E-019 | 编辑-更新已有设备参数 | 修改已有参数的name → blur | PUT /definitions/{type} → _update_params → 参数有id → PUT | 参数更新成功 |
| TC-E2E-020 | 编辑-删除设备参数 | 删除已有参数行 | PUT /definitions/{type} → _update_params → 参数在data中缺失 → soft delete | 参数软删除 |
| TC-E2E-021 | 编辑-添加用例参数 | 新增用例参数 → blur | PUT /definitions/{type} → _update_case_params → 无id → POST | 用例参数创建 |
| TC-E2E-022 | 编辑-用例参数scope变更 | 修改scope common→api | PUT /definitions/{type} → _update_case_params → 有id → PUT | scope更新 |
| TC-E2E-023 | 编辑-用例参数重复code | 添加重复param_code | PUT /definitions/{type} → _update_case_params → 重复检查 → 400 | 返回错误 |
| TC-E2E-024 | 编辑-添加映射 | 新增mapping → 保存 | PUT /definitions/{type} → _update_mappings → 无id → POST | 映射创建 |
| TC-E2E-025 | 编辑-映射source_type无效 | source_type='unknown' | PUT /definitions/{type} → _update_mappings → 验证失败 → 400 | 返回错误 |
| TC-E2E-026 | 编辑-添加关联维度 | 新增维度 → blur | PUT /definitions/{type} → _update_associated_dimensions → 无id → POST | 维度关联创建 |
| TC-E2E-027 | 编辑-删除关联维度 | 删除维度行 | PUT /definitions/{type} → _update_associated_dimensions → 缺失 → soft delete | 维度关联软删除 |
| TC-E2E-028 | 编辑-添加参考参数 | 新增参考参数 → blur | PUT /definitions/{type} → _update_reference_params → 无id → POST | 参考参数创建 |
| TC-E2E-029 | 编辑-更新参考参数 | 修改已有参考参数 | PUT /definitions/{type} → _update_reference_params → 有id → PUT | 参考参数更新 |

### 4.3 自动保存流程

| 测试用例 ID | 场景 | 前端操作 | 后端验证 | 预期结果 |
|------------|------|----------|----------|----------|
| TC-E2E-030 | 设备参数自动保存-新建 | 编辑参数 → 1500ms后 | POST /params → 创建 | 返回id，前端回写 |
| TC-E2E-031 | 设备参数自动保存-更新 | 编辑已有参数 → 1500ms后 | PUT /params/{id} → 更新 | 返回200 |
| TC-E2E-032 | 用例参数自动保存-新建 | 编辑用例参数 → 1000ms后 | POST /case-params → 创建 | 返回id |
| TC-E2E-033 | 用例参数自动保存-重复code | 两个相同param_code | 后端重复检查 → 400 | 前端跳过保存+warn |
| TC-E2E-034 | 参考参数自动保存-新建 | 编辑参考参数 → 1000ms后 | POST /reference-params → 创建 | 返回id |
| TC-E2E-035 | 参考参数自动保存-annotation同步 | code填写后annotation_code空 | 后端 annotation_code = code | 同步成功 |
| TC-E2E-036 | 维度自动保存-新建 | 添加维度 → blur | POST /dimension-relations → 创建 | 返回id |
| TC-E2E-037 | 维度自动保存-更新 | 修改weight → blur | PUT /dimension-relations/{id} → 更新 | 返回200 |
| TC-E2E-038 | 维度自动保存-默认互斥 | 设置is_default=true | PUT /dimension-relations → 其他维度is_default=false | 互斥生效 |

### 4.4 删除流程

| 测试用例 ID | 场景 | 前端操作 | 后端验证 | 预期结果 |
|------------|------|----------|----------|----------|
| TC-E2E-039 | 删除算法 | 确认删除 → DELETE /definitions/{type} | soft delete → 返回200 | 列表刷新 |
| TC-E2E-040 | 删除不存在的算法 | 删除已删除的算法 | DELETE /definitions/{type} → 404 | 前端显示错误 |
| TC-E2E-041 | 删除设备参数 | 删除参数行 → DELETE /params/{id} | soft delete → 200 | 乐观删除成功 |
| TC-E2E-042 | 删除设备参数失败 | DELETE /params/{id} → 500 | 后端异常 | 前端恢复行+alert |
| TC-E2E-043 | 删除用例参数 | 删除用例参数行 | DELETE /case-params/{id} → 200 | 乐观删除成功 |
| TC-E2E-044 | 删除参考参数 | 删除参考参数行 | DELETE /reference-params/{id}/{type} → 200 | 乐观删除成功 |
| TC-E2E-045 | 删除维度关联 | 删除维度行 | DELETE /dimension-relations/{id} → 200 | 删除成功 |

### 4.5 查询流程

| 测试用例 ID | 场景 | 前端操作 | 后端验证 | 预期结果 |
|------------|------|----------|----------|----------|
| TC-E2E-046 | 获取算法列表 | 页面加载 → GET /definitions | 查询DB → 分页 → 序列化 | 返回列表 |
| TC-E2E-047 | 获取算法详情 | 点击编辑 → GET /definitions/{type} | 查询DB → 序列化(含子配置) | 返回完整算法 |
| TC-E2E-048 | 获取算法选项 | 下拉选择 → GET /options | 查询DB → 精简序列化 | 返回options数组 |
| TC-E2E-049 | 获取表单Schema | 加载表单 → GET /form-schema/{type} | 查询DB → 构建schema | 返回FormSchema |
| TC-E2E-050 | 获取参数选项 | 加载选项 → GET /params/{type}/options | 查询DB → _get_options_from_source | 返回options对象 |
| TC-E2E-051 | 获取关联维度 | 加载维度 → GET /dimensions/{type} | 查询DB → 构建维度数据 | 返回维度+权重 |
| TC-E2E-052 | 获取分组列表 | 加载分组 → GET /groups | 查询DB → 序列化 | 返回分组数组 |
| TC-E2E-053 | 获取选项来源 | 加载来源 → GET /options-sources | 查询DB → 构建来源列表 | 返回来源数组 |

### 4.6 状态切换流程

| 测试用例 ID | 场景 | 前端操作 | 后端验证 | 预期结果 |
|------------|------|----------|----------|----------|
| TC-E2E-054 | 上线→下线 | 点击禁用 → PUT /definitions/{type} {status:'offline'} | 更新DB → 200 | 列表刷新，状态变更 |
| TC-E2E-055 | 下线→上线 | 点击启用 → PUT /definitions/{type} {status:'online'} | 更新DB → 200 | 列表刷新，状态变更 |

### 4.7 复制算法流程

| 测试用例 ID | 场景 | 前端操作 | 后端验证 | 预期结果 |
|------------|------|----------|----------|----------|
| TC-E2E-056 | 复制算法 | 确认复制 → GET详情 → POST新算法 | 查询详情 → 创建新算法(type=_copy) | 列表刷新 |
| TC-E2E-057 | 复制-目标type已存在 | type_copy已存在 | POST → 409冲突 | 前端显示错误 |

### 4.8 完整端到端回归场景

| 测试用例 ID | 场景 | 完整流程 | 预期结果 |
|------------|------|----------|----------|
| TC-E2E-058 | 全流程CRUD | 新建算法 → 添加参数 → 添加映射 → 添加维度 → 保存 → 编辑 → 修改参数 → 删除参数 → 删除算法 | 每步都正确，最终算法被软删除 |
| TC-E2E-059 | 自动保存全流程 | 新建算法 → 添加设备参数(自动保存) → 添加用例参数(自动保存) → 添加参考参数(自动保存) → 添加维度(自动保存) → 关闭模态窗 → 重新打开编辑 → 验证所有数据持久化 | 所有自动保存的数据都在重新打开后可见 |
| TC-E2E-060 | 并发编辑场景 | 用户A编辑算法 → 用户B同时编辑同一算法 → A先保存 → B后保存 | B的更新覆盖A的更新（最后写入胜出），无数据损坏 |
| TC-E2E-061 | 网络中断恢复 | 编辑参数 → 网络中断 → 自动保存失败 → 网络恢复 → 再次编辑触发保存 | 失败时前端保留数据，恢复后可重新保存 |

---

## 5. 测试环境与执行

### 5.1 测试环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11 |
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 14+ (端口 5432) |
| 后端框架 | Flask 3 + pytest + pytest-cov |
| 前端框架 | Vue 3 + Vitest 4 + @vue/test-utils 2 + jsdom |
| 测试数据库 | 使用独立测试数据库（非生产库） |

### 5.2 后端测试执行

#### 5.2.1 测试配置

在 `backend/tests/conftest.py` 中配置测试夹具：

```python
import pytest
from app import create_app
from models import db

@pytest.fixture
def app():
    """测试用 Flask 应用"""
    app = create_app(testing=True)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """测试用 HTTP 客户端"""
    return app.test_client()

@pytest.fixture
def algorithm_factory(db):
    """算法工厂夹具"""
    from models import AlgorithmDefinition
    def create(**kwargs):
        algo = AlgorithmDefinition(
            type=kwargs.get('type', 'test_algo'),
            name=kwargs.get('name', '测试算法'),
            status=kwargs.get('status', 'online'),
            display_order=kwargs.get('display_order', 0),
            **{k: v for k, v in kwargs.items() if k not in ['type', 'name', 'status', 'display_order']}
        )
        db.session.add(algo)
        db.session.commit()
        return algo
    return create
```

#### 5.2.2 执行命令

```bash
# 运行全部后端测试
cd backend
pytest tests/ -v

# 运行算法模块测试
pytest tests/test_algorithm_controller.py -v

# 生成覆盖率报告（要求分支覆盖率 100%）
pytest tests/test_algorithm_controller.py --cov=controllers/algorithm_controller --cov-branch --cov-report=term-missing --cov-report=html

# 运行特定测试用例
pytest tests/test_algorithm_controller.py::TestCreateAlgorithm::test_create_success -v
```

#### 5.2.3 覆盖率目标

| 模块 | 行覆盖率 | 分支覆盖率 |
|------|---------|-----------|
| algorithm_controller.py | 100% | 100% |
| schemas/algorithm.py | 100% | 100% |
| services/algorithm_service.py | 100% | 100% |

### 5.3 前端测试执行

#### 5.3.1 测试配置

在 `frontend/vitest.config.ts` 中配置：

```typescript
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      branches: 100,
      lines: 100,
      functions: 100,
      statements: 100
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  }
})
```

在 `frontend/package.json` 中添加测试脚本：

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage"
  }
}
```

#### 5.3.2 执行命令

```bash
# 运行全部前端测试
cd frontend
npm test

# 运行算法模块测试
npm test -- --reporter=verbose src/components/algorithm/__tests__/

# 生成覆盖率报告
npm run test:coverage

# 运行特定测试文件
npm test -- src/components/algorithm/__tests__/AlgorithmConfigModal.spec.ts
```

#### 5.3.3 覆盖率目标

| 组件 | 行覆盖率 | 分支覆盖率 |
|------|---------|-----------|
| AlgorithmConfigModal.vue | 100% | 100% |
| AlgorithmConfigPage.vue | 100% | 100% |
| useAlgorithmConfig.ts | 100% | 100% |

### 5.4 链调测试执行

#### 5.4.1 前置条件检查

```bash
# 1. 确认后端单元测试全部通过
cd backend
pytest tests/test_algorithm_controller.py -v --tb=short
# 预期：所有测试 PASSED，分支覆盖率 100%

# 2. 确认前端单元测试全部通过
cd frontend
npm test -- --reporter=verbose
# 预期：所有测试 PASSED，分支覆盖率 100%

# 3. 确认服务已启动
# PostgreSQL (端口 5432)
# Flask 后端 (端口 5000)
# Vite 前端 (端口 5173/5174)
```

#### 5.4.2 链调执行方式

**方式一：API 自动化链调（推荐）**

使用 pytest 的 requests 库对真实后端发请求，验证完整流程：

```bash
cd backend
pytest tests/test_algorithm_e2e.py -v --tb=short
```

**方式二：前端 E2E 框架**

使用 Playwright/Cypress 对真实前端页面操作：

```bash
cd frontend
npx playwright test e2e/algorithm-config.spec.ts
```

#### 5.4.3 链调通过标准

| 检查项 | 标准 |
|--------|------|
| TC-E2E-001 ~ TC-E2E-061 | 全部 PASSED |
| 数据一致性 | 前端创建的数据在后端 DB 中可查 |
| 响应格式 | snake_case → camelCase 转换正确 |
| 错误处理 | 后端错误能正确传递到前端显示 |
| 软删除 | 删除后 GET 请求不再返回该记录 |

### 5.5 CI/CD 集成建议

```yaml
# .github/workflows/test.yml
name: Test Pipeline

on: [push, pull_request]

jobs:
  backend-test:
    runs-on: windows-latest
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r backend/requirements.txt
      - run: pip install pytest pytest-cov
      - run: |
          cd backend
          pytest tests/ --cov=controllers --cov-branch --cov-report=xml --cov-fail-under=100
      - uses: codecov/codecov-action@v3

  frontend-test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: |
          cd frontend
          npm ci
          npm run test:coverage
      - uses: codecov/codecov-action@v3

  e2e-test:
    needs: [backend-test, frontend-test]
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start services
        run: |
          # 启动 PostgreSQL, 后端, 前端
      - name: Run E2E tests
        run: |
          cd backend
          pytest tests/test_algorithm_e2e.py -v
```

### 5.6 测试用例统计

| 阶段 | 模块 | 用例数 | 覆盖分支 |
|------|------|--------|----------|
| 后端单元 | 算法定义 CRUD | ~30 | create/update/delete + 子配置更新 |
| 后端单元 | 参数管理 | ~25 | create/update/delete param + options |
| 后端单元 | 用例参数 | ~25 | create/update/delete case-param + scope/dup |
| 后端单元 | 参考参数 | ~15 | create/update/delete reference-param |
| 后端单元 | 映射管理 | ~15 | create/update/delete mapping + source_type |
| 后端单元 | 维度关联 | ~12 | create/update/delete dimension-relation |
| 后端单元 | 分组管理 | ~8 | create/update/delete group |
| 后端单元 | 选项来源 | ~6 | get options-sources |
| 后端单元 | 内部辅助函数 | ~20 | _serialize/_get_options/_update_* |
| 后端单元 | Schema验证 | ~15 | 边界条件验证 |
| **后端小计** | | **~171** | **~180 分支** |
| 前端单元 | AlgorithmConfigModal | ~80 | 模态窗/表单/自动保存/维度/Tab/行操作/Bundle/computed/watch |
| 前端单元 | AlgorithmConfigPage | ~60 | 列表/搜索/分页/CRUD/Tab/详情/normalize |
| 前端单元 | useAlgorithmConfig | ~42 | 加载/获取/缓存/CRUD/图标/useAlgorithmForm |
| **前端小计** | | **~182** | **~45 分支** |
| 链调测试 | E2E 集成 | 61 | 完整流程覆盖 |
| **总计** | | **~414** | **分支覆盖率 100%** |