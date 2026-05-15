# SPL 映射逻辑说明

本文描述后端在执行用例播放时，如何将「目标声压级（SPL, dB）」转换为「播放线性增益（gain）」并应用到音频输出的实际逻辑。

## 1. 核心结论

- 后端不会直接控制系统音量或"真实声压"。后端使用的是：对音频 PCM 采样幅值做乘法的线性增益（software gain）。
- SPL 仅用于在「SPL 映射（SPLMapping）」存在时计算 gain；如果没有映射或未提供 SPL，则会回退到默认值或默认增益。
- 新的增益计算方式采用 `gainOffset`（dB 偏移）而非直接的百分比增益。

## 2. 相关数据结构

### 2.1 PlaybackDevice（播放设备）

- `PlaybackDevice.current_spl_mapping_id`
  - 含义：该播放设备当前绑定使用的 SPL 映射（SPLMapping）的 ID。
  - 用途：用例执行/预览/设备测试播放时，会根据此字段决定是否启用 SPL→gain 的映射计算。
  - 代码：`backend/models/models.py` 的 `PlaybackDevice` 定义。

### 2.2 SPLMapping（SPL 映射）

字段说明（以代码实际使用为准）：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | Integer | 映射唯一ID |
| name | String | 映射配置名称 |
| description | Text | 映射配置详细描述 |
| device_id | Integer | 关联播放设备ID |
| device_type | String | 适用的设备类型（noise/dry） |
| distance | Float | 测试时的物理距离（米），默认 1.0 |
| target_spl | Float | 目标声压级（dB SPL） |
| digital_gain | Float | 对应的数字增益值（dB），当前版本主要从 gainOffset 计算 |
| calibration_status | String | 校准状态（calibrated/uncalibrated），默认 uncalibrated |
| test_frequency | Integer | 校准时使用的测试频率（Hz），默认 1000 |
| calibration_data | JSON | 详细校准测量点数据 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### 2.3 calibration_data 数据结构

当前实现约定的校准数据结构：

```json
{
  "points": [
    {
      "spl": 65.0,
      "gainOffset": 10.5,
      "baseLevel": -30,
      "finalLevel": -19.5,
      "digital_gain": 50
    }
  ]
}
```

字段说明：
- `spl`: 声压级测量值（dB）
- `gainOffset`: 增益偏移量（dB），相对于基准电平 -30 dBFS 的偏移
- `baseLevel`: 基准电平（dBFS），默认 -30
- `finalLevel`: 最终输出电平（dBFS）= baseLevel + gainOffset
- `digital_gain`: 兼容旧格式的数字增益百分比

**计算公式**：
- `gainOffset` 转线性增益：`linear_gain = 10 ^ (gainOffset / 20.0)`
- 最终电平限制：不能超过 -5 dBFS（即 gainOffset 不能超过 +25 dB）

## 3. 映射绑定（设备与映射的关联）

设备关联映射由播放设备接口完成：

- 接口逻辑：`backend/controllers/playback_controller.py` 的 `associate_spl`
- 主要规则：
  - 映射存在性校验：`spl_mapping_id` 必须对应一条 SPLMapping
  - 一致性校验：
    - 若映射指定了 `device_id`，则必须与当前设备一致
    - 若映射指定了 `device_type`，则必须与当前设备的 `device_type` 一致
  - 最终写入：`device.current_spl_mapping_id = spl_mapping_id`

## 4. SPL → gain 的计算逻辑

统一入口：

- `backend/utils/spl_service.py`：`SPLMappingService.spl_to_gain(mapping_id, target_spl)`

### 4.1 增益限制常量

```python
DB_MIN = -60.0      # 最小增益限制（dB）
DB_MAX = 0.0        # 最大增益限制（dB）
BASE_LEVEL_DB = -30.0  # 基准电平（dBFS）
MAX_OUTPUT_DB = -5.0   # 最大输出电平（dBFS）
MIN_GAIN_DB = MAX_OUTPUT_DB - BASE_LEVEL_DB  # -20 dB
MAX_GAIN_DB = MAX_OUTPUT_DB - BASE_LEVEL_DB   # +25 dB
```

### 4.2 计算优先级（按代码顺序）

1) **找不到映射**
   - 如果 `mapping_id` 对应的映射不存在：直接返回 `1.0`

2) **目标 SPL 命中映射的 target_spl（±0.1dB）**
   - 若 `abs(mapping.target_spl - target_spl) < 0.1` 且 `digital_gain` 非空：
     - `gain_db = digital_gain / 100.0`（当 `digital_gain > 1`）
     - 否则 `gain_db = digital_gain`
     - 返回 `SPLMappingService._apply_gain_limit(gain_db)`

3) **存在校准点（calibration_data.points）**
   - 取 `points` 的 `spl` 和增益信息，按 spl 排序后做线性插值：
     - 优先使用 `gainOffset`（dB 偏移）计算线性增益
     - 兼容旧格式：若 `gainOffset` 为空，则使用 `digital_gain` 或 `gain`（百分比）
     - 低于最小 spl：返回 `min(gains)` 并应用增益限制
     - 高于最大 spl：返回 `max(gains)` 并应用增益限制
     - 中间：`np.interp(target_spl, spls, gains)`
     - 应用增益限制：`MIN_GAIN_DB` 到 `MAX_GAIN_DB` 范围

4) **无校准点但存在单点（target_spl + digital_gain）**
   - 计算 `diff_db = target_spl - mapping.target_spl`
   - `factor = 10 ** (diff_db / 20.0)`
   - 返回 `SPLMappingService._apply_gain_limit(factor)`

5) **其他情况**
   - 返回 `1.0`

### 4.3 增益限制函数

```python
@staticmethod
def _apply_gain_limit(gain_db):
    return max(MIN_GAIN_DB, min(MAX_GAIN_DB, gain_db))
```

- 最小增益：`MIN_GAIN_DB = -20.0` dB（对应线性增益约 0.1）
- 最大增益：`MAX_GAIN_DB = +25.0` dB（对应线性增益约 17.78）

### 4.4 单位约定（重要）

当前实现中的单位转换：

- `gainOffset`（dB 偏移）转线性增益：`10 ^ (gainOffset / 20.0)`
- `digital_gain`（dB 值）：
  - `digital_gain > 1`：按 dB 值处理（除以 100 后使用）
  - `digital_gain <= 1`：按线性增益处理（直接使用）

**注意**：系统使用 -30 dBFS 作为标准测试音基准电平，所有增益计算都相对于此基准。

## 5. 用例执行时如何使用 SPL 映射

### 5.1 干声（dry）音频播放

入口：`backend/utils/e2e_executor.py` 的 `_play_dry_audios`

逻辑要点：

- 默认增益：`gain = 1.0`
- 只有当播放设备绑定了 `current_spl_mapping_id` 才启用映射：
  - `spl_value = ca.get('spl', 65.0)`（用例未配置 spl 时默认 65.0）
  - `gain = spl_service.spl_to_gain(dev_current_spl_mapping_id, spl_value)`

### 5.2 背景噪声（noise）播放

入口：`backend/utils/e2e_executor.py` 的 `_play_background_noise`

逻辑要点：

- 默认增益：`gain = 1.0`
- 若噪声播放设备绑定了 `current_spl_mapping_id`，则：
  - `n_gain = spl_service.spl_to_gain(n_dev['current_spl_mapping_id'], noise_audio_data['spl'])`

### 5.3 预览（preview）与设备测试（test）

预览与设备测试同样使用 `spl_to_gain`：

- 预览：`backend/controllers/audio_controller.py`（干声默认 `spl=65.0`，噪声默认 `spl=0`）
- 设备测试：`backend/controllers/playback_controller.py`（请求里提供 `spl` 且设备已绑定映射时才计算）

## 6. gain 在播放链路中的实际应用

最终的增益在播放回调里以"幅值乘法"方式生效：

- 代码：`backend/utils/audio_engine.py`（PyAudioDriver）
- 关键行为：
  - `effective_gain = audio_gain * GLOBAL_SAFE_GAIN * gain_compensation`
  - `audio_data = audio_data * effective_gain`

其中：
- `audio_gain`：从 SPL 映射计算的线性增益（来自 `spl_service.spl_to_gain()`）
- `GLOBAL_SAFE_GAIN`：全局安全增益系数，当前为 `1`
- `gain_compensation`：根据音频实际 RMS 调整的补偿增益，确保达到预期的 SPL

**RMS 补偿计算**：
- `gain_db = 目标RMS - 当前RMS = -30 - current_rms_db`
- `gain_compensation = 10 ^ (gain_db / 20)`

### 6.1 调试日志示例

执行用例时，可通过以下日志排查增益计算问题：

```
[get_audio_configs_for_offset] device_id=3, device_obj=<PlaybackDevice 3>, current_spl_mapping_id=10
[get_audio_configs_for_offset] mapping_id=10, target_spl=60, SPL gain=0.1000 (-20.00 dB)
[calculate_gain_compensation] file=0077_1.wav, current_rms_db=-50.66 dBFS, target=-30 dBFS, gain_db=20.66 dB, gain_compensation=10.7939 (linear)
```

日志说明：
| 日志关键词 | 含义 |
|-----------|------|
| `device_id` | 播放设备 ID |
| `current_spl_mapping_id` | 设备绑定的 SPL 映射 ID（为空表示无映射） |
| `target_spl` | 目标声压级（来自用例配置） |
| `SPL gain` | 从映射计算的线性增益（dB 值） |
| `current_rms_db` | 测试音频的实际 RMS 电平 |
| `gain_compensation` | RMS 补偿增益（线性值） |

**最终增益计算示例**：
- SPL gain = 0.1000 (-20 dB)
- gain_compensation = 10.7939 (对应 20.66 dB)
- GLOBAL_SAFE_GAIN = 1
- effective_gain = 0.1000 × 1 × 10.7939 ≈ 1.08 (0.66 dB)

### 6.2 常见增益计算场景

| 场景 | audio_gain | gain_compensation | 实际效果 |
|------|-------------|-------------------|----------|
| 设备有 SPL 映射 + 测试音频 RMS 正常 | 按映射计算 | ~1.0 | 接近目标 SPL |
| 设备有 SPL 映射 + 测试音频 RMS 偏低 | 按映射计算 | >1.0 (补偿) | 目标 SPL + RMS 补偿 |
| 设备无 SPL 映射 (current_spl_mapping_id=null) | 1.0 | >1.0 (补偿) | 仅 RMS 补偿，无 SPL 映射 |
| 设备有 SPL 映射但未生效 | 1.0 | >1.0 | 误以为 SPL 映射未生效 |

## 7. 常见行为与排查要点

| 场景 | 行为 | 排查要点 |
|------|------|----------|
| 用例未配置 SPL | 干声默认 `spl=65.0`，噪声默认 `spl=0` | 检查用例配置中的 `spl` 字段 |
| 设备未绑定映射 | 不计算映射，直接 `gain=1.0` | 检查 `current_spl_mapping_id` 是否为空 |
| **SPL 映射未生效** | `audio_gains[i]=1.0`，SPL gain 日志缺失 | 检查 `current_spl_mapping_id` 是否为 `None`，日志搜索 `[get_audio_configs_for_offset]` |
| 增益值异常 | 检查 `gainOffset` 是否在有效范围内（+25 dB 内） | 验证 calibration_data.points 中的 gainOffset |
| 校准点格式错误 | 优先使用 `gainOffset`，兼容 `digital_gain`/`gain` | 确保 points 数据结构正确 |
| 输出偏小 | 检查 MIN_GAIN_DB 限制（-20 dB） | 确认 target_spl 不低于校准点最小值 |
| 输出失真 | 检查是否超过 MAX_OUTPUT_DB（-5 dBFS） | 确认 gainOffset 不超过 +25 dB |

### 7.1 排查步骤：SPL 映射未生效

如果日志中出现 `audio_gains[i]=1.0000`（即 SPL gain 为 1.0），请按以下步骤排查：

1. **检查设备是否绑定 SPL 映射**
   - 日志中搜索 `current_spl_mapping_id`
   - 如果显示 `current_spl_mapping_id=None` 或为空，说明设备未绑定映射

2. **检查映射计算是否成功**
   - 正常日志应包含：`[get_audio_configs_for_offset] mapping_id=10, target_spl=60, SPL gain=0.1000 (-20.00 dB)`
   - 如果没有此日志，说明 `spl_to_gain()` 返回了默认值 1.0

3. **检查数据库**
   - 确认 `PlaybackDevice.current_spl_mapping_id` 字段有值
   - 确认对应的 `SPLMapping` 记录存在

### 7.2 排查步骤：实际 SPL 与预期不符

如果实际播放音量与目标 SPL 差距较大：

1. **检查 gain_compensation 是否过大**
   - 如果测试音频 RMS 远低于 -30 dBFS（如 -50 dBFS），gain_compensation 会很大（>10）
   - 这可能导致实际 SPL 超出预期

2. **检查 SPL 映射的校准数据**
   - 确认 calibration_data.points 包含目标 SPL 对应的校准点
   - 确认 gainOffset 值合理（-20 dB 到 +25 dB 范围内）

## 8. 示例

### 8.1 SPLMapping.calibration_data 示例（新格式）

```json
{
  "points": [
    {
      "spl": 55.0,
      "gainOffset": -15.0,
      "baseLevel": -30,
      "finalLevel": -45.0
    },
    {
      "spl": 60.0,
      "gainOffset": -5.0,
      "baseLevel": -30,
      "finalLevel": -35.0
    },
    {
      "spl": 65.0,
      "gainOffset": 5.0,
      "baseLevel": -30,
      "finalLevel": -25.0
    },
    {
      "spl": 70.0,
      "gainOffset": 15.0,
      "baseLevel": -30,
      "finalLevel": -15.0
    }
  ]
}
```

计算说明：
- 对于 target_spl=62.5，插值计算 gainOffset ≈ 0 dB
- 线性增益 = 10^(0/20) = 1.0
- 最终输出电平 = -30 + 0 = -30 dBFS

### 8.2 用例音频配置示例（干声）

```json
{
  "audios": [
    {
      "audio_id": "xxx",
      "playback_device_id": "dry_device_id",
      "spl": 65.0,
      "play_order": 1,
      "test_type": "e2e"
    }
  ]
}
```

### 8.3 设备关联映射 API 请求

```json
POST /api/v1/playback/devices/{device_id}/associate-spl
{
  "splMappingId": 1
}
```

## 9. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0 | 2025-01-01 | 初始版本，基于百分比增益计算 |
| 1.1 | 2025-12-01 | 升级为 dB 偏移计算方式，支持 gainOffset |
| 1.2 | 2026-01-01 | 添加增益限制，优化 RMS 补偿计算 |
| 1.3 | 2026-03-20 | 完善调试日志说明，添加排查步骤文档 |
