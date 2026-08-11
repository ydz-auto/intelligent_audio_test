# 05 - testcase_controller 双记录 CRUD

## 涉及文件
- `Intelligent-Audio-TEST/backend/controllers/testcase_controller.py`

## 现状分析

现有 CRUD 逻辑：
- `create_testcase()`：创建一条 TestCase 记录
- `update_testcase()`：更新记录
- `get_testcases()`：查询列表，按 algorithmType/groupId 过滤
- `delete_testcase()`：逻辑删除（deleted=True）
- `copy_testcase()`：复制一条记录

**问题**：双记录架构下，创建 voice_llm 用例时需要同时创建 API 和 E2E 两条记录。查询、更新、删除也需要考虑双记录。

## 改造方案

### 创建用例

```python
def create_testcase(data):
    """
    创建测试用例
    - 接收 test_type 参数
    - 创建单条记录（前端根据用例类型分别提交）
    """
    testcase = TestCase(
        id=generate_id(),
        name=data['name'],
        test_type=data.get('test_type', 'api'),
        config=data['config'],  # {rounds: [], dimensions: []}
        algorithm_type=data.get('algorithm_type'),
    )
    db.session.add(testcase)
    db.session.commit()

    return testcase
```

### 创建说明

| 操作 | 说明 |
|------|------|
| 创建 API 记录 | 前端提交 test_type='api'，创建一条 API 记录 |
| 创建 E2E 记录 | 前端提交 test_type='e2e'，创建一条 E2E 记录 |
| 单类型用例 | 如果只创建单类型用例（如纯 API 用例），只创建一条记录 |

### 更新用例

```python
def update_testcase(testcase_id, data):
    """
    - test_type 不可变（不允许修改）
    - 只更新当前记录的 config
    - 不级联更新关联记录
    """
    testcase = TestCase.query.get(testcase_id)
    if 'test_type' in data and data['test_type'] != testcase.test_type:
        raise ValidationError("test_type 不允许修改")
    # ... 更新其他字段
```

### 查询用例

```python
def get_testcases(filters):
    """
    支持 test_type 过滤参数
    """
    query = TestCase.query.filter_by(deleted=False)
    if filters.get('test_type'):
        query = query.filter_by(test_type=filters['test_type'])
    if filters.get('algorithm_type'):
        query = query.filter_by(algorithm_type=filters['algorithm_type'])
    # ...
    return query.all()
```

### 删除用例

```python
def delete_testcase(testcase_id):
    """
    删除用例
    - 逻辑删除当前记录
    """
    testcase = TestCase.query.get(testcase_id)
    testcase.deleted = True

    db.session.commit()
```

### 复制用例

```python
def copy_testcase(testcase_id):
    """
    复制用例
    - 复制当前记录
    """
    original = TestCase.query.get(testcase_id)
    new_case = _copy_single(original)

    return new_case
```

## 相关文档
- [01_TestCase模型新增字段.md](01_TestCase模型新增字段.md) — 数据模型
- [frontend/test-case/04_TestCaseListContainer_test_type.md](../../frontend/test-case/04_TestCaseListContainer_test_type.md) — 前端列表适配
