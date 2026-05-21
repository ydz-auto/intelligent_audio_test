# PostgreSQL INTEGER 到 BIGINT 迁移修复文档

## 问题描述

### 原始问题
系统数据库中所有自增 ID 字段使用 `INTEGER` 类型（对应 PostgreSQL 的 `SERIAL`），最大值限制为 **2,147,483,647**（约21亿）。

对于日志表、测试结果表等高频写入的表，长期运行后可能发生 ID 溢出问题。

### 数据类型范围对比

| 类型 | PostgreSQL 名称 | 最大值 | 说明 |
|------|-----------------|--------|------|
| `INTEGER` | SERIAL | 2,147,483,647 (~21亿) | 32位整数 |
| `BigInteger` | BIGSERIAL | 9,223,372,036,854,775,807 (~922万亿亿) | 64位整数 |

### 风险评估

| 表名 | 风险级别 | 说明 |
|------|----------|------|
| `logs` | 🔴 高 | 日志数据量极大，长期运行可能溢出 |
| `test_results` | 🔴 高 | 每个任务多条结果，累积增长 |
| `test_result_dimensions` | 🔴 高 | 每个结果多条维度记录 |
| `audios` | 🟡 中 | 音频文件数量累积 |
| `test_tasks` | 🟡 中 | 任务数量累积 |
| 其他配置表 | 🟢 低 | 数据量有限，不易溢出 |

---

## 修复方案

### 1. 修改 SQLAlchemy 模型

#### 修改的文件
- `backend/models/models.py`
- `backend/models/algorithm_models.py`

#### 修改内容
将所有 `Integer` 自增 ID 改为 `BigInteger`：

```python
# 修改前
from sqlalchemy import Column, Integer, String, ...
id = Column(Integer, primary_key=True, autoincrement=True, comment='...')

# 修改后
from sqlalchemy import Column, Integer, BigInteger, String, ...
id = Column(BigInteger, primary_key=True, autoincrement=True, comment='...')
```

#### 修改的模型列表（共42个表）

**models.py 中的表：**
- User, Permission, UserPermission
- TagCategory, Tag
- TestCaseTag
- Device, PlaybackDevice, DeviceTag
- TranslationDirection, Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation, PromptAudioRelation
- API
- Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation
- TestResult, TestResultDimension
- Report, ReportSummary, ReportDetailData
- Category, Dimension
- Log
- SPLMapping, CalibrationHistory
- UploadChunk
- StatsCache

**algorithm_models.py 中的表：**
- AlgorithmGroup, AlgorithmDefinition
- AlgorithmDeviceParam, AlgorithmApiParam, AlgorithmReferenceParam
- EvaluationDimensionParam
- ParamMapping
- AlgorithmDimensionRelation
- CaseAlgorithmParam
- Language

#### 同时修改的 ForeignKey 字段
所有引用上述表 ID 的 ForeignKey 字段也改为 `BigInteger`。

---

### 2. 数据库迁移

#### 迁移脚本位置
- SQL 脚本：`backend/migrations/migrate_integer_to_biginteger.sql`
- 执行脚本：`backend/migrations/run_migration.py`
- 数据完整性修复：`backend/migrations/fix_data_integrity.py`

#### 迁移步骤

**第一步：数据完整性检查**
```bash
cd backend/migrations
python fix_data_integrity.py
```

检查并清理无效的外键引用（本次清理了 145 条无效记录）。

**第二步：执行迁移**
```bash
python run_migration.py
```

迁移流程：
1. 删除所有外键约束
2. 修改所有主键字段类型为 BIGINT
3. 修改所有 ForeignKey 字段类型为 BIGINT
4. 重新创建所有外键约束
5. 验证迁移结果

---

## 前后端兼容性分析

### 后端 Python
✅ **无需修改** - Python `int` 类型为无限精度，可容纳任意大整数。

### 前端 JavaScript/TypeScript
⚠️ **部分兼容** - JavaScript `number` 类型最大安全整数为 `Number.MAX_SAFE_INTEGER` (9,007,199,254,740,991，约900万亿)。

#### 当前前端类型定义

大部分前端类型已使用 `number | string` 混合类型，已兼容：

```typescript
// businessTypes.ts - 已兼容的类型
interface Task { id: string | number; }
interface AudioInfo { id: string | number; }
interface TestCase { id: string | number; }
interface Device { id: string | number; }
interface Report { id: string | number; }
interface Dimension { id: number | string; }
interface PlaybackDevice { id: string | number; }
```

#### 需关注的类型（建议改为 number | string）

```typescript
// 建议修改
interface Tag { id: number; }              // → id: number | string
interface Log { id: number; }              // → id: number | string
interface EvaluationCategory { id: number; } // → id: number | string
```

#### 实际风险评估
实际业务场景中，ID 值很难超过 JavaScript 安全整数范围（900万亿），当前设计已足够安全。

---

## 迁移执行结果

### 执行日期
2026-05-21

### 执行日志摘要

```
============================================================
数据完整性检查与修复
============================================================
⚠ task_case_relations -> test_tasks: 发现 62 条无效引用
⚠ task_device_relations -> test_tasks: 发现 5 条无效引用
⚠ task_api_relations -> test_tasks: 发现 9 条无效引用
⚠ task_merge_relations -> test_tasks (source): 发现 2 条无效引用
⚠ test_results -> test_tasks: 发现 1 条无效引用
⚠ test_result_dimensions -> test_results: 发现 61 条无效引用
⚠ evaluation_dimension_params -> dimensions: 发现 4 条无效引用
⚠ algorithm_dimension_relations -> dimensions: 发现 1 条无效引用
============================================================
总计清理: 145 条无效记录
============================================================

============================================================
PostgreSQL INTEGER 到 BIGINT 迁移
============================================================
共需要执行 169 条SQL语句
成功: 169 条
跳过/失败: 0 条
============================================================

验证迁移结果...
✓ 所有 id 字段已成功转换为 BIGINT!
```

### 迁移后验证

所有 42 个表的 `id` 字段类型已确认转换为 `bigint`：

```sql
-- 验证 SQL
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'public' AND column_name = 'id'
ORDER BY table_name;
```

---

## 影响范围总结

| 层级 | 修改内容 | 影响 |
|------|----------|------|
| 数据库 | 42个表ID字段改为BIGINT | ✅ 完成 |
| SQLAlchemy模型 | 所有Integer ID改为BigInteger | ✅ 完成 |
| 后端Schema | 无需修改（Python int无限精度） | ✅ 已兼容 |
| 前端TypeScript | 大部分已使用number\|string | ✅ 已兼容 |

---

## 后续建议

1. **前端类型完善**（可选）
   - 将 `Tag.id`, `Log.id`, `EvaluationCategory.id` 改为 `number | string`

2. **监控建议**
   - 定期检查日志表数据量
   - 关注 ID 增长趋势

3. **备份建议**
   - 执行迁移前建议备份数据库
   - 本次迁移已成功，无需回滚

---

## 相关文件

| 文件路径 | 说明 |
|----------|------|
| `backend/models/models.py` | 主数据模型（已修改） |
| `backend/models/algorithm_models.py` | 算法配置模型（已修改） |
| `backend/migrations/migrate_integer_to_biginteger.sql` | SQL迁移脚本 |
| `backend/migrations/run_migration.py` | Python执行脚本 |
| `backend/migrations/fix_data_integrity.py` | 数据完整性修复脚本 |
| `frontend/src/shared/types/businessTypes.ts` | 前端类型定义（已兼容） |