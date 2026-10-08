# 01 - TestCase 模型新增字段

## 涉及文件
- `Intelligent-Audio-TEST/backend/models/models.py:132-151`（TestCase 模型）
- 关联：`Intelligent-Audio-TEST/backend/controllers/testcase_controller.py`（创建/列表按 test_type 过滤）

## 现状分析

> 本文档原为改造设计稿；改造已完成并落地，以下内容与实际代码一致（models.py:132-151）。

实际 TestCase 模型（models.py:132-151）：

```python
class TestCase(db.Model):
    __tablename__ = 'test_cases'
    id = Column(String(50), primary_key=True, comment='用例唯一标识符')                                        # 138
    name = Column(String(150), nullable=False, comment='用例显示名称')                                          # 139
    description = Column(Text, comment='用例详细描述')                                                          # 140
    config = Column(JSON, nullable=False, comment='用例结构性配置 (JSON)，含 rounds/dimensions/background_noise 等，不含算法参数和参考参数')  # 141
    algorithm_params = Column(JSON, comment='算法参数（按轮分组 [{round_number, params:[{field_code, field_value}]}]）')  # 142
    reference_params = Column(JSON, comment='参考参数路径（按轮分组 [{round_number, reference_params_path}]，内容存文件）')  # 143
    group_id = Column(String(50), ForeignKey('test_case_groups.id'), comment='所属分组ID')                      # 144
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')  # 145
    test_type = Column(String(10), nullable=False, default='api', index=True, comment='测试类型 (api/e2e)')     # 146
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')                          # 147
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')        # 148
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')                            # 149

    tags = relationship('Tag', secondary='test_case_tags', backref='test_cases')                               # 151
```

与设计稿的差异：
- 字段名为 `algorithm_params` / `reference_params`（**无下划线前缀、无显式列名**，设计稿中的 `_algorithm_params = Column('algorithm_params', ...)` 写法未出现过）。
- 除 `test_type` 外，`algorithm_params`、`reference_params` 两个独立列也是本次改造一并新增（结构格式见 [04_testcase_Schema新类型.md](04_testcase_Schema新类型.md)）。
- 双记录架构已落地：创建/更新时按 `test_type`（api/e2e）分开记录，执行侧以记录的 `test_type` 为准（见 reference_params_generator.py:1080-1082「新双记录架构：使用记录的 test_type」）。
- `config` 已改为 `rounds-as-top-level` 结构：`config.rounds[]` 每轮含 `round_number`（轮号），不再使用 `config.dimensions = {api:[], e2e:[]}` 嵌套；维度为扁平列表，元素带 `test_type` 字段（见 schemas/testcase.py:58-63 TestCaseDimensionItem）。

## 改造方案

> 本节改造已全部落地，实际代码以 `models.py:146` 为准。

### 新增字段（已落地）

```python
# models.py:146
test_type = Column(
    String(10),
    nullable=False,
    default='api',
    index=True,
    comment='测试类型 (api/e2e)'
)
```

### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| test_type | VARCHAR(10) | 是 | 'api' | 测试类型，取值 `api` 或 `e2e` |

### 双记录架构示意

```
TestCase #A (test_type='api')
  ├── config = { rounds: [], dimensions: [], background_noise, source_audio, auto_generated }
  │             ← API 专用结构性配置（算法参数/参考参数不在 config 中，存独立列）
  ├── algorithm_params = [{ round_number, params: [{field_code, field_value}] }]
  ├── reference_params = [{ round_number, reference_params_path }]
  └── algorithm_type = 'voice_llm'

TestCase #B (test_type='e2e')
  ├── config = { rounds: [], dimensions: [], background_noise, source_audio, auto_generated }
  │             ← E2E 专用结构性配置
  ├── algorithm_params = [{ round_number, params: [{field_code, field_value}] }]
  ├── reference_params = [{ round_number, reference_params_path }]
  └── algorithm_type = 'voice_llm'
```

### 约束与索引
- `test_type` 建索引（`index=True`），用于列表页按类型筛选
- `test_type` 取值校验在应用层，不在数据库层：创建时 `testcase_controller.py:671-674` 校验 `test_type_val not in ['api', 'e2e']` 则报错 `test_type 无效: ...，必须为 api 或 e2e`；Schema 层 `TestCaseCreateSchema.test_type` 默认 `'api'`（schemas/testcase.py:398）

### 影响的查询
- 列表查询：增加 `WHERE test_type = ?` 过滤（实际代码 testcase_controller.py:354-356 列表视图、testcase_controller.py:475-476 标签视图，均按请求参数 `type` 过滤且仅接受 `api`/`e2e`）

## 相关文档
- [05_testcase_controller双记录CRUD.md](05_testcase_controller双记录CRUD.md) — Controller 层适配
- [35_数据迁移方案.md](../35_数据迁移方案.md) — DDL 变更和数据迁移
- [frontend/core/01_types.ts新接口定义.md](../../frontend/core/01_types.ts新接口定义.md) — 前端类型对应
