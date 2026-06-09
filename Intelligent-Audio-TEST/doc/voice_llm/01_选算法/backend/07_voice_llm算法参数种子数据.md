# 07 - voice_llm 算法参数种子数据

## 涉及文件
- 数据库迁移脚本 / 种子数据 INSERT

## 现状分析

现有算法（translation/asr/tts/speaker_recognition）的 `CaseAlgorithmParam` 已在初始化时插入。voice_llm 作为新算法类型，需要在种子数据中注册其所有用例级参数。

### 设计原则：参数驱动

**所有**用例表单中需要出现的字段（包括公共能力和算法专有参数），都在 `case_algorithm_params` 表中注册。
RoundConfigEditor 通过 DynamicForm 根据这些定义动态渲染表单，不硬编码任何字段。

```
case_algorithm_params 表
  └─ 定义"表单有哪些字段"
       └─ DynamicForm 渲染
            └─ 用户填写值存入 algorithmParams: [{field_code, field_value}] 数组格式
                 例: [{field_code: 'railDistance', field_value: 50}, ...]
```

> **algorithmParams 数组格式**：用户填写的参数值以 `[{field_code: param_code, field_value: 用户填写值}]` 数组格式存储，而非扁平字典 `algorithmParams[param_code]`。每个元素包含 `field_code`（对应 `param_code`）和 `field_value`（用户填写的值）。

> **backgroundNoise 不在 algorithmParams 中**：`backgroundNoise` 属于 round 级别字段（带 `loop` 属性），直接存储在 round 配置中，由 `round_config.get('backgroundNoise')` 读取，不作为 `case_algorithm_param` 注册。

## 改造方案

### voice_llm 用例参数定义（case_algorithm_params）

voice_llm 需要在 `case_algorithm_params` 中注册以下参数：

#### 通用参数（scope=common）

| param_code | param_name | param_type | default_value | help_text |
|------------|------------|------------|---------------|-----------|
| `promptAudioId` | Prompt 音频 | audio_select | null | 在干声播放之前播放的引导音频 |

> **注意**：`backgroundNoise` 不在 `case_algorithm_params` 中注册，它属于 round 级别字段（带 `loop` 属性），在 RoundConfigEditor 中单独处理。

#### E2E 专用参数（scope=e2e）

| param_code | param_name | param_type | default_value | help_text |
|------------|------------|------------|---------------|-----------|
| `interferers` | 干扰人列表 | interferer_list | [] | 干扰人配置列表（多路独立干扰） |
| `railDistance` | 导轨距离(cm) | slider | null | 导轨距离，本轮结束后自动复位 |
| `volumeLevel` | 被测设备音量 | slider | null | 设备音量(0-100)，本轮结束后自动恢复 |
| `voiceprintEnabled` | 声纹注册 | switch | false | 是否在本轮播放声纹注册音频 |
| `voiceprintAudioId` | 声纹注册音频 | audio_select | null | 声纹注册音频文件 |
| `voiceprintPlaybackDeviceId` | 声纹播放设备 | device_select | null | 声纹注册音频播放设备 |
| `voiceprintSpl` | 声纹播放声压级 | number | 70.0 | 声纹注册音频播放声压级 |
| `voiceprintWaitTime` | 声纹等待时间(秒) | number | 5.0 | 声纹注册后等待时间 |
| `interruptionEnabled` | 打断检测 | switch | false | 是否启用全双工打断检测 |
| `interruptionSensitivity` | 打断灵敏度 | slider | 0.5 | 打断检测灵敏度(0~1) |

#### API 专用参数（scope=api）

| param_code | param_name | param_type | default_value | help_text |
|------------|------------|------------|---------------|-----------|
| `inputText` | 输入文本 | text | null | 发送给 API 的文本内容 |
| `inputAudio` | 输入音频 | audio_select | null | 发送给 API 的音频文件 |

> **说明**：`inputText` 和 `inputAudio` 是 API 测试的输入字段。两者独立存在，
> 用户可只填文本、只填音频、或两者都填（多种输入共存）。
> API 适配器通过 `algorithm_api_params` (direction=input) 中的 `input_text` 和 `input_audio`
> 映射到实际的 API 请求字段。

### INSERT SQL

```sql
-- voice_llm 用例参数定义（case_algorithm_params）

-- === 通用参数（scope=common，API 和 E2E 都显示） ===

INSERT INTO case_algorithm_params
  (algorithm_type, param_code, param_name, label, param_type, scope,
   required, default_value, help_text, ui_order, hidden, deleted)
VALUES
  ('voice_llm', 'promptAudioId', 'Prompt 音频', 'Prompt 音频', 'audio_select', 'common',
   FALSE, NULL, '在干声播放之前播放的引导音频', 30, FALSE, FALSE);


-- === E2E 专用参数（scope=e2e，仅 E2E 测试显示） ===

INSERT INTO case_algorithm_params
  (algorithm_type, param_code, param_name, label, param_type, scope,
   required, default_value, help_text, ui_order, hidden, deleted)
VALUES
  ('voice_llm', 'interferers', '干扰人列表', '干扰人', 'interferer_list', 'e2e',
   FALSE, '[]', '干扰人配置列表，支持多路独立干扰', 20, FALSE, FALSE),

  ('voice_llm', 'railDistance', '导轨距离(cm)', '导轨距离', 'slider', 'e2e',
   FALSE, NULL, '导轨距离，本轮结束后自动复位。不填则不控制导轨', 40, FALSE, FALSE),

  ('voice_llm', 'volumeLevel', '被测设备音量', '设备音量', 'slider', 'e2e',
   FALSE, NULL, '被测设备音量(0-100)，本轮结束后自动恢复。不填则不控制音量', 41, FALSE, FALSE),

  ('voice_llm', 'voiceprintEnabled', '声纹注册', '声纹注册', 'switch', 'e2e',
   FALSE, 'false', '是否在本轮播放声纹注册音频', 50, FALSE, FALSE),

  ('voice_llm', 'voiceprintAudioId', '声纹注册音频', '声纹音频', 'audio_select', 'e2e',
   FALSE, NULL, '声纹注册音频文件', 51, FALSE, FALSE),

  ('voice_llm', 'voiceprintPlaybackDeviceId', '声纹播放设备', '播放设备', 'device_select', 'e2e',
   FALSE, NULL, '声纹注册音频播放设备', 52, FALSE, FALSE),

  ('voice_llm', 'voiceprintSpl', '声纹播放声压级', '声压级', 'number', 'e2e',
   FALSE, '70.0', '声纹注册音频播放声压级', 53, FALSE, FALSE),

  ('voice_llm', 'voiceprintWaitTime', '声纹等待时间(秒)', '等待时间', 'number', 'e2e',
   FALSE, '5.0', '声纹注册后等待时间', 54, FALSE, FALSE),

  ('voice_llm', 'interruptionEnabled', '打断检测', '打断检测', 'switch', 'e2e',
   FALSE, 'false', '是否启用全双工打断检测', 60, FALSE, FALSE),

  ('voice_llm', 'interruptionSensitivity', '打断灵敏度', '灵敏度', 'slider', 'e2e',
   FALSE, '0.5', '打断检测灵敏度(0~1)', 61, FALSE, FALSE);


-- === API 专用参数（scope=api，仅 API 测试显示） ===

INSERT INTO case_algorithm_params
  (algorithm_type, param_code, param_name, label, param_type, scope,
   required, default_value, help_text, ui_order, hidden, deleted)
VALUES
  ('voice_llm', 'inputText', '输入文本', '输入文本', 'text', 'api',
   FALSE, NULL, '发送给 API 的文本内容（可与输入音频共存）', 70, FALSE, FALSE),

  ('voice_llm', 'inputAudio', '输入音频', '输入音频', 'audio_select', 'api',
   FALSE, NULL, '发送给 API 的音频文件（可与输入文本共存）', 71, FALSE, FALSE);
```

> **注意**：`backgroundNoise` 不在 `case_algorithm_params` 中注册。它属于 round 级别字段，直接存储在 round 配置的 `backgroundNoise` 属性中（带 `loop` 属性），由 `round_config.get('backgroundNoise')` 读取。

### voice_llm 算法专有参数（扩展预留）

如果后续 voice_llm 需要算法专有参数（如 `max_tokens`、`temperature` 等 LLM 推理参数），
在 `case_algorithm_params` 中按需 INSERT，scope 设为 `common`。

### scope 过滤机制

`CaseAlgorithmParam.scope` 字段（common/api/e2e）控制 DynamicForm 中参数的可见性：

| param.scope | test_type='api' | test_type='e2e' |
|-------------|:---------------:|:---------------:|
| common | 显示 | 显示 |
| api | 显示 | 隐藏 |
| e2e | 隐藏 | 显示 |

RoundConfigEditor 传入 `scope=testType`，DynamicForm 自动过滤：

```ts
// DynamicForm 内部过滤
const filteredParams = params.filter(p =>
  p.scope === 'common' || p.scope === props.scope
)
```

### DynamicForm param_type 映射

| param_type | 前端渲染组件 | 说明 |
|-----------|------------|------|
| `slider` | el-slider | 滑块（导轨距离、音量、灵敏度） |
| `switch` | el-switch | 开关（声纹注册、打断检测） |
| `number` | el-input-number | 数字输入（声压级、等待时间） |
| `audio_select` | AudioSelectButton | 音频选择器 |
| `device_select` | DeviceSelect | 设备选择器 |
| `interferer_list` | InterfererConfigEditor | 干扰人列表子编辑器 |
| `text` | el-input | 文本输入 |

> 标准 param_type（slider/switch/number/text）由 DynamicForm 内置。
> 复杂 param_type（interferer_list/audio_select/device_select）需要注册子编辑器组件。
> `noise_config` 类型已移除，`backgroundNoise` 不再作为 case_algorithm_param，改为 round 级别字段在 RoundConfigEditor 中单独渲染。

### algorithm_api_params（API 接口定义）

voice_llm 的 API 输入/输出字段在 `algorithm_api_params` 表中注册（见 `08_field_mapper_voice_llm映射.md`）。
这些定义用于 API 适配器构建请求体，与 `case_algorithm_params` 中的 `inputText`/`inputAudio` 通过 param_mappings 关联。

## 相关文档
- [02_CaseAlgorithmParam_scope字段.md](02_CaseAlgorithmParam_scope字段.md) — scope 字段定义
- [06_algorithm_Schema与Controller.md](06_algorithm_Schema与Controller.md) — 接口适配
- [08_field_mapper_voice_llm映射.md](08_field_mapper_voice_llm映射.md) — algorithm_api_params 定义
- [02_选用例/frontend/10_RoundConfigEditor.md](../../02_选用例/frontend/10_RoundConfigEditor.md) — DynamicForm 驱动
- [01_选算法/frontend/15_DynamicForm_scope过滤.md](../../01_选算法/frontend/15_DynamicForm_scope过滤.md) — scope 过滤
- [35_数据迁移方案.md](../../35_数据迁移方案.md) — 迁移脚本
