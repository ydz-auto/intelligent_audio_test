# 06 - algorithm Schema 与 Controller

## 涉及文件
- `Intelligent-Audio-TEST/backend/schemas/algorithm.py`
- `Intelligent-Audio-TEST/backend/controllers/algorithm_controller.py`

## 现状分析

### Schema 层
`CaseAlgorithmParamSchema` 序列化 CaseAlgorithmParam 模型，当前不包含 scope 字段。

### Controller 层
`algorithm_controller.py` 提供 CaseAlgorithmParam 的 CRUD：
- `GET /algorithm/case-params?algorithm_type=xxx` — 按算法类型查询参数列表
- `POST /algorithm/case-params` — 创建参数
- `PUT /algorithm/case-params/<id>` — 更新参数
- `DELETE /algorithm/case-params/<id>` — 删除参数

查询时不支持 scope 过滤。

## 改造方案

### Schema 修改

```python
class CaseAlgorithmParamSchema(Schema):
    # ... 现有字段 ...
    scope = fields.String(dump_default='common')  # 新增
```

### Controller 修改

```python
# GET /algorithm/case-params
def get_case_params():
    algorithm_type = request.args.get('algorithm_type')
    scope = request.args.get('scope')  # 新增：可选过滤参数
    
    query = CaseAlgorithmParam.query.filter_by(
        algorithm_type=algorithm_type, deleted=False
    )
    
    if scope:
        # 过滤规则：scope='common' 的参数 + scope 匹配的参数
        query = query.filter(
            (CaseAlgorithmParam.scope == 'common') | 
            (CaseAlgorithmParam.scope == scope)
        )
    
    params = query.order_by(CaseAlgorithmParam.ui_order).all()
    return CaseAlgorithmParamSchema(many=True).dump(params)
```

### 接口参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| algorithm_type | string | 是 | 算法类型 |
| scope | string | 否 | 过滤范围：api/e2e，不传返回全部 |

### 过滤逻辑

```
请求 scope=api  → 返回 scope='common' + scope='api' 的参数
请求 scope=e2e  → 返回 scope='common' + scope='e2e' 的参数
不传 scope      → 返回全部参数（向后兼容）
```

### algorithmParams 存储格式

前端提交用例时，`algorithmParams` 以 `[{field_code, field_value}]` 数组格式存储，而非扁平字典：

```json
[
  {"field_code": "inputText", "field_value": "你好"},
  {"field_code": "inputAudio", "field_value": "audio_001"}
]
```

- `field_code` 对应 `CaseAlgorithmParam.param_code`
- `field_value` 为用户填写的值

### API 单记录 / E2E 双记录差异

- **API 测试用例**：单记录结构，提交时 `algorithmParams` 只包含一条记录的参数
- **E2E 测试用例**：双记录结构，提交时包含主记录和参考记录，每条记录各有独立的 `algorithmParams` 数组

## 相关文档
- [02_CaseAlgorithmParam_scope字段.md](02_CaseAlgorithmParam_scope字段.md) — 数据模型
- [07_voice_llm算法参数种子数据.md](07_voice_llm算法参数种子数据.md) — 种子数据
- [frontend/dynamic-form/15_DynamicForm_scope过滤.md](../../frontend/dynamic-form/15_DynamicForm_scope过滤.md) — 前端过滤
