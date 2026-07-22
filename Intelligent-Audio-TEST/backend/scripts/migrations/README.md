# 数据库迁移执行顺序

> **正式环境部署文档**
> 项目: Intelligent-Audio-TEST
> 更新日期: 2026-07-22

---

## 一、前置准备

### 1. 环境变量

```powershell
# 设置数据库连接串（如不是默认值）
$env:DATABASE_URI = "postgresql://user:password@host:5432/dbname"
```

### 2. 依赖安装

```powershell
pip install sqlalchemy psycopg2-binary
```

### 3. 备份数据库

```powershell
# 强烈建议在执行任何迁移前备份
pg_dump -U intelligent_audio_test -d intelligent_audio_test -F c -f backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump
```

### 4. 工作目录

所有命令在项目根目录下执行：

```powershell
cd "c:\S2TT\auto_test\ver8\202604231600\Intelligent-Audio-TEST"
```

---

## 二、迁移执行顺序

### 阶段 1: 结构迁移（旧 config → 新 rounds 结构）

| 序号 | 脚本 | 说明 |
|------|------|------|
| 1.1 | `python backend/scripts/migrations/202606/migrate_config_to_rounds.py --dry-run` | 预览：config 轮次化 + reference_params 存文件 + algorithm_params 移入独立列 |
| 1.2 | `python backend/scripts/migrations/202606/migrate_config_to_rounds.py` | 正式执行上述迁移 |
| 1.3 | `python backend/scripts/migrations/202606/extend_param_type.py` | 扩展 param_type 字段长度 + 推断新类型（rttm/stm/json） |

---

### 阶段 2: 用例拆分（混合用例 → API/E2E 分离）

| 序号 | 脚本 | 说明 |
|------|------|------|
| 2.1 | `python backend/scripts/migrations/202606/split_testcase_by_type.py --dry-run` | 预览：将同时含 API+E2E 的用例拆分为两条独立用例 |
| 2.2 | `python backend/scripts/migrations/202606/split_testcase_by_type.py` | 正式执行拆分 |

---

### 阶段 3: DDL 变更（新增字段/索引）

| 序号 | 脚本 | 说明 |
|------|------|------|
| 3.1 | `python backend/scripts/migrations/202606/add_result_data_path_to_test_results.py` | test_results 新增 result_data_path 列，result_data 改为可空 |
| 3.2 | `python backend/scripts/migrations/202606/add_round_number_to_result_dimensions.py` | test_result_dimensions 新增 round_number 列 + 复合索引 |

---

### 阶段 4: 综合修复（修复历史迁移脚本的错误）

> **核心步骤** — 修复前述脚本中的路径格式、字段归属、表结构等问题。

| 序号 | 脚本 | 说明 |
|------|------|------|
| 4.1 | `python backend/scripts/migrations/202607/fix_migration_errors.py --dry-run` | 预览所有修复项 |
| 4.2 | `python backend/scripts/migrations/202607/fix_migration_errors.py` | 正式执行（10 个步骤自动按序完成） |

**fix_migration_errors.py 内部 10 步流程：**

| Step | 修复内容 |
|------|----------|
| 1 | 恢复 `test_cases.algorithm_params` 和 `reference_params` 列（如被误删） |
| 2 | 从 `config.rounds[]` 剥离 `algorithmParams`/`referenceParamsPath` 回独立列 |
| 3 | 修正参考参数文件路径为 `static/case_result/{case_id}/round_{n}.json` |
| 4 | 清理 `config.rounds[]` 中残留的 `algorithmParams`/`referenceParamsPath` 字段 |
| 5 | 确保 `test_type` 列和索引存在 |
| 6 | 删除新模型中已不存在的旧表（`translation_directions` 等） |
| 7 | 修正 `case_algorithm_params` 表字段（新增 scope/min/max/step/unit 等，删除旧 options_* 列） |
| 8 | 修正 `evaluation_dimension_params` 表字段和唯一约束 |
| 9 | 修正 `algorithm_reference_params` 表字段（field_path/merge_mode） |
| 10 | 修正 `test_results`/`test_result_dimensions` 表字段 |

如需单独执行某步：`python fix_migration_errors.py --step 3`

---

### 阶段 5: 文件路径规范化

| 序号 | 脚本 | 说明 |
|------|------|------|
| 5.1 | `python backend/scripts/migrations/202607/normalize_file_paths.py` | 预览：将 audios.file_path 中的 `\` 替换为 `/` |
| 5.2 | `python backend/scripts/migrations/202607/normalize_file_paths.py --apply` | 正式执行 |

---

### 阶段 6: 种子数据（按需执行）

> 根据业务需要选择执行，无强依赖关系。

| 序号 | 脚本 | 说明 |
|------|------|------|
| 7.1 | `python backend/scripts/migrations/202606/seed_voice_llm.py` | voice_llm 算法定义 + 参数 + 映射 |
| 7.2 | `python backend/scripts/migrations/202606/seed_llm_judge_dimension.py` | llm_judge 评估维度 + 参数 |
| 7.3 | `python backend/scripts/migrations/202606/seed_xiaoyi_dimensions.py` | 小艺评估维度（tor/false_takeover/takeover_latency） |

---

## 三、完整执行脚本（一键迁移）

```powershell
cd "c:\S2TT\auto_test\ver8\202604231600\Intelligent-Audio-TEST"

# 阶段 1: 结构迁移
python backend/scripts/migrations/202606/migrate_config_to_rounds.py
python backend/scripts/migrations/202606/extend_param_type.py

# 阶段 2: 用例拆分
python backend/scripts/migrations/202606/split_testcase_by_type.py

# 阶段 3: DDL 变更
python backend/scripts/migrations/202606/add_result_data_path_to_test_results.py
python backend/scripts/migrations/202606/add_round_number_to_result_dimensions.py

# 阶段 4: 综合修复
python backend/scripts/migrations/202607/fix_migration_errors.py

# 阶段 5: 路径规范化
python backend/scripts/migrations/202607/normalize_file_paths.py --apply

# 阶段 6: 种子数据（按需）
python backend/scripts/migrations/202606/seed_voice_llm.py
python backend/scripts/migrations/202606/seed_llm_judge_dimension.py
python backend/scripts/migrations/202606/seed_xiaoyi_dimensions.py
```

---

## 四、回滚方案

如果迁移出现问题，按逆序回滚：

```powershell
# 回滚阶段 4: 重新运行 fix_migration_errors.py 不会造成额外损害（幂等设计）
#   如列被误删，Step 1 会自动恢复

# 回滚阶段 3: 删除新增列
python -c "
from sqlalchemy import create_engine, text
eng = create_engine('postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')
with eng.begin() as c:
    c.execute(text('ALTER TABLE test_results DROP COLUMN IF EXISTS result_data_path'))
    c.execute(text('ALTER TABLE test_results ALTER COLUMN result_data SET NOT NULL'))
    c.execute(text('DROP INDEX IF EXISTS idx_trd_round'))
    c.execute(text('ALTER TABLE test_result_dimensions DROP COLUMN IF EXISTS round_number'))
    print('Rollback DDL done')
"

# 回滚阶段 1: 从备份恢复 config / algorithm_params / reference_params 列
#   需要从 pg_dump 备份恢复

# 最终手段: 从备份恢复整个数据库
# pg_restore -U intelligent_audio_test -d intelligent_audio_test -c backup_xxxxx.dump
```

---

## 五、注意事项

1. **幂等性**: 所有脚本设计为可重复执行，不会造成数据丢失
2. **dry-run**: 每个脚本执行前建议先用 `--dry-run` 预览
3. **备份**: 阶段 1 和阶段 2 执行前必须备份
4. **顺序**: 阶段 1 → 2 → 3 → 4 必须按序执行，不可跳过
5. **种子数据**: 阶段 6 可按需执行，与其他阶段无强依赖
6. **路径格式**: 参考参数文件路径统一为 `static/case_result/{case_id}/round_{n}.json`
7. **数据结构**:
   - `algorithm_params` 独立列格式: `[{round_number, params:[{field_code, field_value}]}]`
   - `reference_params` 独立列格式: `[{round_number, reference_params_path}]`
   - `config.rounds[]` 不含 `algorithmParams`/`referenceParamsPath`
