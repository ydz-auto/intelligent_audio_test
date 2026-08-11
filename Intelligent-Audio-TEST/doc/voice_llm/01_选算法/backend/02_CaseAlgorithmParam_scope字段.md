# 02 - CaseAlgorithmParam scope 字段

## 涉及文件
- `Intelligent-Audio-TEST/backend/models/algorithm_models.py:356-413`

## 现状分析

现有 CaseAlgorithmParam 模型字段：

```python
class CaseAlgorithmParam(db.Model):
    __tablename__ = 'case_algorithm_params'
    id = Column(Integer, primary_key=True)
    algorithm_type = Column(String(50), ForeignKey, nullable=False)
    param_code = Column(String(50), nullable=False)
    param_name = Column(String(100))
    label = Column(String(100))
    param_type = Column(String(20), nullable=False)   # select/text/number/textarea/slider/switch
    required = Column(Boolean, default=False)
    default_value = Column(Text)
    options_source = Column(String(50))
    options_field = Column(String(50))
    options_label_field = Column(String(50))
    help_text = Column(Text)
    ui_order = Column(Integer, default=0)
    hidden = Column(Boolean, default=False)
    deleted = Column(Boolean, default=False)
    created_at / updated_at = Column(DateTime)
```

**问题**：voice_llm 的某些参数只适用于 API 测试（如 session_timeout），某些只适用于 E2E 测试（如 rail_distance、voiceprint_audio）。当前模型无法区分参数的适用范围，前端 DynamicForm 无法按 test_type 过滤。

## 改造方案

### 新增字段

```python
class CaseAlgorithmParam(db.Model):
    # ... 现有字段 ...
    
    # === 新增字段 ===
    scope = Column(
        String(10), 
        nullable=False, 
        default='common', 
        comment='参数适用范围 (common/api/e2e)'
    )
```

### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| scope | VARCHAR(10) | 是 | 'common' | 参数适用范围 |

### scope 取值

| 值 | 说明 | 前端显示规则 |
|----|------|-------------|
| common | 通用参数，API 和 E2E 都显示 | 始终显示 |
| api | 仅 API 测试显示 | test_type='api' 时显示 |
| e2e | 仅 E2E 测试显示 | test_type='e2e' 时显示 |

### 前端过滤规则

```
显示条件: scope == 'common' OR scope == 当前用例的 test_type
```

### algorithmParams 存储格式

用户填写的参数值以 `[{field_code, field_value}]` 数组格式存储在 `round.algorithmParams` 中，而非扁平字典：

```json
[
  {"field_code": "railDistance", "field_value": 50},
  {"field_code": "volumeLevel", "field_value": 80}
]
```

- `field_code` 对应 `CaseAlgorithmParam.param_code`
- `field_value` 为用户填写的值

### API 单记录 / E2E 双记录差异

- **API 测试用例**：单记录结构，每个用例只有一条记录
- **E2E 测试用例**：双记录结构，每个用例包含主记录和参考记录，两者在提交和返回的数据结构上有差异

### UniqueConstraint 不变

现有唯一约束 `UniqueConstraint('algorithm_type', 'param_code')` 保持不变。同一个算法类型下，param_code 唯一。scope 不参与唯一性约束（同一个 param_code 不能同时是 api 和 e2e）。

### to_dict 扩展

```python
def to_dict(self):
    return {
        # ... 现有字段 ...
        'scope': self.scope  # 新增
    }
```

## 相关文档
- [06_algorithm_Schema与Controller.md](06_algorithm_Schema与Controller.md) — Schema 和 Controller 适配
- [07_voice_llm算法参数种子数据.md](07_voice_llm算法参数种子数据.md) — 种子数据中 scope 值设定
- [frontend/dynamic-form/15_DynamicForm_scope过滤.md](../../frontend/dynamic-form/15_DynamicForm_scope过滤.md) — 前端过滤实现
