# 小艺慧记驱动 ASR/Fix 文件解析与拼接功能设计文档

## 1. 概述

本文档描述 `harmony_xiaoyihuiji_driver.py` 中 `extract_results_from_archive` 方法的 ASR/Fix 文件解析与拼接逻辑。

## 2. 背景

在会议录音场景中，设备可能生成多个 ASR 文件和 Fix 文件：
- **ASR 文件**：实时语音识别结果，可能有多个文件（不同时间段）
- **Fix 文件**：非实时处理后的修正结果，通常只有一个

原实现只使用 `select_best_file` 选择单个 ASR 文件，遗漏了其他文件的内容。

## 3. 解析与拼接规则

### 3.1 ASR 文件处理

**规则**：解析所有 ASR 文件，按首行时间戳排序后拼接

```
ASR1: [0.5-2.0]  首0.5, 末2.0
ASR3: [8.0-9.0]  首8.0, 末9.0
ASR2: [3.0-4.0]  首3.0, 末4.0

排序后: ASR1(0.5) → ASR2(3.0) → ASR3(8.0)

拼接结果: [0.5-2.0, 3.0-4.0, 8.0-9.0]
```

**间隙检测**：如果 ASR 文件间间隙 > 10s，记录警告日志：
```
ASR文件间隙>Xs: asr-file1 -> asr-file2
```

### 3.2 Fix 文件处理

**拼接条件**：遍历每个 ASR 文件，Fix 首行与该 ASR 文件的**首行和末行**差距均 > 10s

```
遍历每个 ASR 文件:
    gap_to_first = |Fix首行 - ASR首行|
    gap_to_last = |Fix首行 - ASR末行|

    if gap_to_first > 10 AND gap_to_last > 10:
        → Fix 插入位置: ASR之后
```

| 场景 | 条件 | 处理 |
|------|------|------|
| Fix 在 ASR 时间范围外 | `gap_to_first > 10s` 且 `gap_to_last > 10s` | Fix 插入到该 ASR **之后** |
| Fix 在 ASR 时间范围内 | `gap_to_first ≤ 10s` 或 `gap_to_last ≤ 10s` | 不拼接，继续遍历下一个 ASR |

### 3.3 Fix 插入位置算法

遍历所有 ASR 文件，找到第一个满足条件的 ASR，插入位置在该 ASR 之后：

```
ASR0: [0.5-2.0]  首0.5, 末2.0
ASR1: [3.0-4.0]  首3.0, 末4.0
ASR2: [8.0-9.0]  首8.0, 末9.0
Fix:  [15.0-16.0] 首15.0

遍历:
- Fix(15.0) vs ASR0: |15.0-0.5|=14.5>10, |15.0-2.0|=13>10 → 满足! insert_idx=1
- Fix(15.0) vs ASR1: |15.0-3.0|=12>10, |15.0-4.0|=11>10 → 也满足，但已在ASR0处插入

结果: [ASR0] + [Fix] + [ASR1] + [ASR2]
```

## 4. 关键函数

### 4.1 时间戳获取函数

```python
def get_first_timestamp(stm_lines):
    """获取 STM 首行 start_of_speech 时间戳"""
    if not stm_lines:
        return None
    parts = stm_lines[0].split()
    if len(parts) >= 4:
        return float(parts[3])  # start_sec
    return None

def get_last_timestamp(stm_lines):
    """获取 STM 末行 end_of_speech 时间戳"""
    if not stm_lines:
        return None
    parts = stm_lines[-1].split()
    if len(parts) >= 5:
        return float(parts[4])  # end_sec
    return None
```

### 4.2 文件选择函数

```python
def select_best_file(files):
    """从多个文件中选择最佳文件（按大小排序，选择非空且内容不为 [] 的）"""
    if not files:
        return None
    if len(files) == 1:
        return files[0]
    files_sorted = sorted(files, key=lambda f: f.stat().st_size, reverse=True)
    for f in files_sorted:
        if f.stat().st_size > 0:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    content = fp.read().strip()
                if content and content != "[]":
                    return f
            except:
                pass
    return files_sorted[0] if files_sorted else None
```

## 5. 数据结构

```python
asr_parsed = [
    {
        'stm_lines': [...],      # 该文件的 STM 行列表
        'rttm_lines': [...],     # 该文件的 RTTM 行列表
        'first_ts': 0.5,         # 首行时间戳
        'last_ts': 2.0,          # 末行时间戳
        'file': Path(...)         # 文件路径
    },
    ...
]
```

## 6. 日志输出

| 日志内容 | 场景 |
|----------|------|
| `ASR文件间隙>Xs: file1 -> file2` | ASR 文件间间隙 > 10s |
| `Fix时间戳(Xs)与ASRN(首Ys, 末Zs)差距>10s，插入位置: N` | Fix 与某 ASR 差距均 > 10s |
| `Fix时间戳(Xs)与所有ASR差距<=10s，不拼接` | 所有 ASR 都不满足拼接条件 |
| `最终ASR STM: N 条` | 拼接完成后的总数 |

## 7. 调用关系

```
get_results (设备在线)
    │
    ├── file_pull() - 仅负责从设备拉取文件
    │
    └── extract_results_from_archive (设备离线/存档)
            │
            ├── 解析所有 ASR 文件
            │       └── 按首行时间戳排序拼接
            │
            └── 处理 Fix 文件
                    ├── select_best_file() 选择最佳文件
                    ├── 遍历每个 ASR 文件
                    │       └── 对比 Fix 首行与 ASR 首行/末行
                    └── 插入到第一个满足条件的 ASR 之后
```

## 8. 注意事项

1. **Fix 文件使用 `select_best_file`**：仍选择单个最佳文件，而非全部拼接
2. **时间戳单位**：
   - ASR: `ms10_to_seconds` (ms / 100.0)
   - Fix: `ms_to_seconds` (ms / 1000.0)
3. **文件为空判断**：`fix_asr_content.strip() in ["", "[]"]`
4. **拼接条件**：必须同时满足 `gap_to_first > 10s` 且 `gap_to_last > 10s`
5. **插入位置**：在遍历中找到的第一个满足条件的 ASR 文件**之后**
