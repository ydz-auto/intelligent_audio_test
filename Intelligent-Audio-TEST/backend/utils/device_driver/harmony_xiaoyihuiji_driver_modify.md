# harmony_xiaoyihuiji_driver.py 日志提取逻辑修改文档

## 修改背景

原逻辑从 fix-*.txt 文件提取 fix 数据，修改为从 asr 文件中提取。

### 修改前后对比

| 项目 | 修改前 | 修改后 |
|------|--------|--------|
| Fix 来源 | fix-*.txt 文件 | asr 文件中的 vprFix 数据 |
| asr 来源 | asr-*.txt 文件中的 final | asr-*.txt 文件中的 final |
| Speaker ID | 固定不变 | 通过 idMap 映射转换 |

## 数据来源

### asr 文件

文件名格式：`asr-{timestamp}-{uuid}.txt`

### asr 文件中的 asrType 类型

| asrType | 数据来源字段 | 用途 |
|----------|---------------|------|
| `final` | `payload.speakerInfo` | Recording (asr) |
| `vprFix` | `payload.speakInfo` | Fix |
| `partial` | `payload.text` | 中间结果（忽略） |
| `prefinal` | `payload.text` | 中间结果（忽略） |
| `vprEmb` | `payload.content.clusterHistory` | 包含 idMap 映射 |

### idMap 映射

vprFix 数据中包含 idMap 映射表，格式如下：

```json
"idMap": [
    {"oldId": 1, "newId": 4},
    {"oldId": 2, "newId": 1},
    {"oldId": 3, "newId": 2},
    {"oldId": 5, "newId": 2},
    {"oldId": 6, "newId": 3},
    {"oldId": 8, "newId": 3}
]
```

- idMap 为空 `[]` 时：不替换 speaker id
- idMap 有值时：用映射替换 speaker id
- idMap 缺失的 oldId：分配递增的新 id

## 提取逻辑

### 1. Recording (asr)

```
for 每个 asr 文件:
    提取 asrType="final" 的数据
    按日志时间戳排序
    应用 offset 偏移
```

### 2. Fix

```
# Step 1: 收集所有 speaker id
收集所有 asr 文件中的 speaker oldId（从 final 和 vprFix 中）

# Step 2: 获取 idMap
扫描 asr 文件，获取任意一个 vprFix 的 idMap

# Step 3: 构建完整映射
构建完整 id 映射表：
  - 有 idMap：使用 idMap 中的映射
  - 无 idMap：id 保持不变
  - idMap 缺失的 oldId：分配递增的新 id

# Step 4: 提取 fix 数据
for 每个 asr 文件:
    尝试提取 vprFix 数据
    if 有 vprFix:
        使用 vprFix，file_id 改为 "fix-" 开头
    else:
        用 final 填充，file_id 保持原样

    应用 idMap 映射替换 speaker id
    按日志时间戳排序
    应用 offset 偏移
```

## 文件命名规则

### file_id 转换

- **有 vprFix 数据**：
  - 原始：`asr-202639153245-de0274f8-c356-436f-9d9b-793c0ab6caf0`
  - 转换：`fix-202639153245-de0274f8-c356-436f-9d9b-793c0ab6caf0`

- **无 vprFix（用 final 填充）**：
  - 原始：`asr-202639153245-de0274f8-c356-436f-9d9b-793c0ab6caf0`
  - 保持：`asr-202639153245-de0274f8-c356-436f-9d9b-793c0ab6caf0`

## STM/RTTM 格式

### STM 格式

```
{file_id} 1 speaker{speaker_id} {start_time} {end_time} {text}
```

示例：
```
asr-202639153245-xxx 1 speaker1 8.600 9.200 你好
fix-202639153245-xxx 1 speaker4 8.600 9.200 你好
```

### RTTM 格式

```
SPEAKER {file_id} 1 {start_time} {duration} <NA> <NA> speaker{speaker_id} <NA>
```

示例：
```
SPEAKER asr-202639153245-xxx 1 8.600 0.600 <NA> <NA> speaker1 <NA>
SPEAKER fix-202639153245-xxx 1 8.600 0.600 <NA> <NA> speaker4 <NA>
```

## 排序逻辑

### 文件级别排序

1. **按文件名时间戳排序**
2. **去重**：相同时间戳保留较大的文件
3. **按日志时间戳重新排序**
4. **计算 offset**：第一个文件为基准，计算后续文件的相对时间差

### offset 应用

在提取每个文件的数据后，给 STM/RTTM 行添加 offset：

```python
if offset > 0:
    stm_lines = add_offset_to_stm(stm_lines, offset)
    rttm_lines = add_offset_to_rttm(rttm_lines, offset)
```

## 新增函数

### 1. extract_stm_from_asr(filepath, file_id, asr_type="final")

提取 STM 数据。

**参数：**
- `filepath`: asr 文件路径
- `file_id`: 输出使用的文件 ID
- `asr_type`: 提取类型 `"final"` 或 `"vprFix"`

### 2. extract_rttm_from_asr(filepath, file_id, asr_type="final")

提取 RTTM 数据。

### 3. extract_idmap_from_asr(filepath)

从 asr 文件中提取 vprFix 的 idMap。

### 4. collect_all_speaker_ids(asr_files_list)

收集所有 asr 文件中的 speaker id。

### 5. build_complete_idmap(all_ids, idmap)

构建完整的 id 映射。

### 6. apply_idmap_to_stm(stm_lines, id_mapping)

应用 idMap 替换 STM 行中的 speaker id。

### 7. apply_idmap_to_rttm(rttm_lines, id_mapping)

应用 idMap 替换 RTTM 行中的 speaker id。

## 移除的代码

- `fix_files` 定义
- `extract_stm_from_fix` 函数
- `extract_rttm_from_fix` 函数

## 日志输出

- `收集到所有speaker id: [1, 2, 3]`
- `从asr-202639153245-xxx获取到idMap: [{'oldId': 1, 'newId': 4}, ...]`
- `完整speaker id映射: {1: 4, 2: 1, 3: 2}`
- `Fix ASR0 使用vprFix数据，file_id: fix-202639153245-xxx`
- `Fix ASR1 无vprFix数据，使用final填充，file_id: asr-202639153245-xxx`
- `Fix ASR0 已应用idMap替换speaker id`
- `最终ASR STM: 10 条`
- `最终Fix STM: 10 条`

## 边界情况

1. **没有 vprFix 数据**：所有 fix 都用 final 填充
2. **没有 idMap**：`build_complete_idmap` 返回 `{id: id}`，不替换
3. **idMap 缺失 oldId**：分配新的递增 id
4. **asr 文件为空**：跳过该文件
