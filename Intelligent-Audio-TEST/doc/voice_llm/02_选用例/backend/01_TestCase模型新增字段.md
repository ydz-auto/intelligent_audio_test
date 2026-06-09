# 01 - TestCase 模型新增字段

## 涉及文件
- `Intelligent-Audio-TEST/backend/models/models.py:132-175`

## 现状分析

现有 TestCase 模型字段：

```python
class TestCase(db.Model):
    __tablename__ = 'test_cases'
    id = Column(String(50), primary_key=True)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    config = Column(JSON, nullable=False)          # 音频+维度配置
    group_id = Column(String(50), ForeignKey)
    algorithm_type = Column(String(50))            # translation/asr/tts/speaker_recognition
    _algorithm_params = Column('algorithm_params', JSON)
    _reference_params = Column('reference_params', JSON)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    deleted = Column(Boolean, default=False)
```

**问题**：当前一个 TestCase 记录的 `config.dimensions` 是 `{api:[], e2e:[]}` 嵌套结构，API 和 E2E 配置混在一条记录中。voice_llm 需要双记录架构，每条记录只属于一种测试类型。

## 改造方案

### 新增字段

```python
class TestCase(db.Model):
    # ... 现有字段 ...

    # === 新增字段 ===
    test_type = Column(
        String(10),
        nullable=False,
        default='api',
        index=True,
        comment='测试类型 (api/e2e)'
    )
    related_case_id = Column(
        String(50),
        nullable=True,
        comment='关联的对应类型用例ID (API用例关联E2E用例，反之亦然)'
    )
```

### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| test_type | VARCHAR(10) | 是 | 'api' | 测试类型，取值 `api` 或 `e2e` |
| related_case_id | VARCHAR(50) | 否 | NULL | 关联的对应用例 ID，API 记录指向 E2E 记录，反之亦然 |

### 双记录架构示意

```
TestCase #A (test_type='api')
  ├── related_case_id = '#B'  ──→  TestCase #B (test_type='e2e')
  │                                  └── related_case_id = '#A'
  ├── config = { rounds: [], dimensions: [] }   ← API 专用配置
  └── algorithm_type = 'voice_llm'

TestCase #B (test_type='e2e')
  ├── related_case_id = '#A'
  ├── config = { rounds: [], dimensions: [] }   ← E2E 专用配置
  └── algorithm_type = 'voice_llm'
```

### 约束与索引
- `test_type` 建索引（`index=True`），用于列表页按类型筛选
- `related_case_id` 不设外键约束（跨记录引用，避免循环依赖）
- `test_type` 取值校验在应用层（Schema/Controller），不在数据库层

### 影响的查询
- 列表查询：增加 `WHERE test_type = ?` 过滤
- 关联查询：通过 `related_case_id` 查找对应用例
- 删除操作：级联考虑——删除 API 记录时是否同时删除关联的 E2E 记录

## 相关文档
- [05_testcase_controller双记录CRUD.md](05_testcase_controller双记录CRUD.md) — Controller 层适配
- [35_数据迁移方案.md](../35_数据迁移方案.md) — DDL 变更和数据迁移
- [frontend/core/01_types.ts新接口定义.md](../../frontend/core/01_types.ts新接口定义.md) — 前端类型对应
