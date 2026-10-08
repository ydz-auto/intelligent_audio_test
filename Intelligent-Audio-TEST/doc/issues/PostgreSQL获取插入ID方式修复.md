# PostgreSQL 获取插入 ID 方式修复

## 问题描述

在 `backend/utils/api_executor.py` 中，测试结果保存功能使用了 SQLite 的 `last_insert_rowid()` 函数来获取最后插入记录的 ID。由于项目实际使用的是 PostgreSQL 数据库，该函数无法正常工作，会导致以下问题：

1. **兼容性问题**：PostgreSQL 不支持 `last_insert_rowid()` 函数
2. **运行时错误**：执行 SQL 查询时会报错，提示函数不存在
3. **数据完整性风险**：在高并发场景下，即使使用 PostgreSQL 的替代方案（如 `currval()`），也可能获取到错误的 ID

## 问题原因

原代码使用了 SQLite 特有的语法：

```python
# 原始实现（SQLite 方式）
insert_sql = text("""
    INSERT INTO test_results (...)
    VALUES (...)
""")

result = conn.execute(insert_sql, params)
conn.commit()

# SQLite 特有函数
last_id_sql = text("SELECT last_insert_rowid()")
result_id = conn.execute(last_id_sql).scalar()
```

**原因分析**：
- SQLite 使用 `last_insert_rowid()` 函数获取最后插入的自增 ID
- PostgreSQL 不支持此函数，需要使用 `RETURNING` 子句或其他方式

## 解决方案

使用 PostgreSQL 标准的 `RETURNING` 子句，在 INSERT 语句执行时直接返回插入的 ID。

### 方案优势

1. **单次查询完成** - 插入和获取 ID 在一次数据库交互中完成，减少网络往返
2. **原子性保证** - 返回的 ID 一定是刚插入记录的 ID，避免并发问题
3. **标准语法** - `RETURNING` 是 PostgreSQL/Oracle 等数据库的标准特性

## 修改内容

### 文件：`backend/utils/api_executor.py`

#### 修改点 1：INSERT 语句添加 RETURNING 子句

```python
# 修改前
insert_sql = text("""
    INSERT INTO test_results (task_id, test_case_id, device_id, api_id, algorithm_type, execution_status, response_time, algorithm_result, execution_steps, result_data, error_message, created_at)
    VALUES (:task_id, :test_case_id, :device_id, :api_id, :algorithm_type, :execution_status, :response_time, :algorithm_result, :execution_steps, :result_data, :error_message, :created_at)
""")

# 修改后
insert_sql = text("""
    INSERT INTO test_results (task_id, test_case_id, device_id, api_id, algorithm_type, execution_status, response_time, algorithm_result, execution_steps, result_data, error_message, created_at)
    VALUES (:task_id, :test_case_id, :device_id, :api_id, :algorithm_type, :execution_status, :response_time, :algorithm_result, :execution_steps, :result_data, :error_message, :created_at)
    RETURNING id
""")
```

#### 修改点 2：从 RETURNING 结果直接获取 ID

```python
# 修改前
with db.engine.connect() as conn:
    result = conn.execute(insert_sql, params)
    conn.commit()
    
    # SQLite 特有方式
    last_id_sql = text("SELECT last_insert_rowid()")
    result_id = conn.execute(last_id_sql).scalar()

# 修改后
with db.engine.connect() as conn:
    # RETURNING id 直接在结果中返回
    result = conn.execute(insert_sql, params)
    result_id = result.scalar()
    conn.commit()
```

## 代码对比

### 完整修改前后对比

| 项目 | 修改前 | 修改后 |
|------|--------|--------|
| SQL 语句 | 无 RETURNING 子句 | 添加 `RETURNING id` |
| 获取 ID 方式 | 执行两次查询 | 单次查询直接获取 |
| 数据库兼容性 | 仅 SQLite | PostgreSQL 标准 |
| 并发安全性 | 低（可能获取错误 ID） | 高（原子性保证） |
| 性能 | 两次数据库交互 | 一次数据库交互 |

## 影响范围

- **直接影响**：`api_executor.py` 中的 `_save_test_result` 方法
- **功能影响**：API 测试结果保存功能
- **数据库影响**：仅影响 ID 获取方式，不影响数据结构

## 测试建议

1. 执行 API 测试，验证结果能正常保存
2. 检查返回的 `result_id` 是否正确对应插入的记录
3. 并发场景测试，验证多个测试同时保存时 ID 不冲突

## 相关文件

- [backend/utils/api_executor.py](../../backend/utils/api_executor.py) - 主要修改文件
- [backend/models/database.py](../../backend/models/database.py) - 数据库配置

## 修复日期

2026-05-21