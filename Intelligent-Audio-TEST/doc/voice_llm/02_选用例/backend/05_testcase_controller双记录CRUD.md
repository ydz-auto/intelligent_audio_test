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

**问题**：双记录架构下，创建 voice_llm 用例时需要同时创建 API 和 E2E 两条记录，并通过 related_case_id 互指。查询、更新、删除也需要考虑关联记录。

## 改造方案

### 创建用例

```python
def create_testcase(data):
    """
    创建测试用例
    - 接收 test_type 参数
    - 创建单条记录（前端根据用例类型分别提交）
    - related_case_id 由前端在创建关联记录后回写
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

    if data.get('related_case_id'):
        testcase.related_case_id = data['related_case_id']
        related = TestCase.query.get(data['related_case_id'])
        if related:
            related.related_case_id = testcase.id
        db.session.commit()

    return testcase
```

### 关联管理

| 操作 | 说明 |
|------|------|
| 创建 API 记录 | 前端先创建 API 记录，再创建 E2E 记录，E2E 记录的 related_case_id 指向 API 记录 ID |
| 回写关联 | E2E 创建成功后，回写 API 记录的 related_case_id 指向 E2E 记录 ID |
| 无关联 | 如果只创建单类型用例（如纯 API 用例），related_case_id 留空 |

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
def delete_testcase(testcase_id, cascade=True):
    """
    删除用例
    - cascade=True 时，同时逻辑删除关联记录
    - cascade=False 时，只删除当前记录，清空关联记录的 related_case_id
    """
    testcase = TestCase.query.get(testcase_id)
    testcase.deleted = True

    if cascade and testcase.related_case_id:
        related = TestCase.query.get(testcase.related_case_id)
        if related:
            related.deleted = True
    elif not cascade and testcase.related_case_id:
        related = TestCase.query.get(testcase.related_case_id)
        if related:
            related.related_case_id = None

    db.session.commit()
```

### 复制用例

```python
def copy_testcase(testcase_id):
    """
    复制用例
    - 复制当前记录
    - 如果原记录有关联记录，同时复制关联记录
    - 新记录之间建立 related_case_id 关联
    """
    original = TestCase.query.get(testcase_id)
    new_api = _copy_single(original)

    if original.related_case_id:
        related = TestCase.query.get(original.related_case_id)
        new_e2e = _copy_single(related)
        new_api.related_case_id = new_e2e.id
        new_e2e.related_case_id = new_api.id
        db.session.commit()

    return new_api
```

## 相关文档
- [01_TestCase模型新增字段.md](01_TestCase模型新增字段.md) — 数据模型
- [frontend/test-case/04_TestCaseListContainer_test_type.md](../../frontend/test-case/04_TestCaseListContainer_test_type.md) — 前端列表适配
