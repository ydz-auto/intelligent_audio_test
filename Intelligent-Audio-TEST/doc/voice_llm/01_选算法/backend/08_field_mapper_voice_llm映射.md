# 08 - field_mapper voice_llm 映射（参数驱动版）

## 涉及文件
- `Intelligent-Audio-TEST/backend/algorithm/field_mapper.py`

## 现状分析

FieldMapper 是单例类，负责：
- 提供设备/API/评估的字段定义查询
- 字段类型转换和数据格式转换
- 构建 API 请求数据

核心方法：
- `get_device_params(algorithm_type)` — 获取设备参数定义
- `get_api_params(algorithm_type)` — 获取 API 参数定义
- `get_param_mappings(algorithm_type, source)` — 获取参数映射
- `build_create_task_data(algorithm_type, ...)` — 构建 create_task 请求体

## 改造方案（参数驱动，去除硬编码分支）

### 核心原则

FieldMapper **不应**为 voice_llm 添加硬编码分支（如 `if algorithm_type == 'voice_llm'`）。
所有字段定义和映射关系从数据库动态加载（`algorithm_api_params`、`algorithm_device_params`、`param_mappings` 表）。

### voice_llm 字段定义（数据库注册）

以下字段通过种子数据在数据库中注册，FieldMapper 从数据库动态加载：

#### 设备输出字段 (algorithm_device_params, direction='output')

| param_code | param_name | param_type | 说明 |
|------------|------------|------------|------|
| `asr_text` | 识别文本 | text | 设备端 ASR 识别结果 |
| `asr_rttm` | 说话人标注 | rttm | 说话人分离时间戳 |
| `asr_stm` | 分段标注 | stm | 分段文本标注 |
| `device_status` | 设备状态 | json | 设备运行状态信息 |

#### API 输入字段 (algorithm_api_params, direction='input')

| param_code | param_name | param_type | 说明 |
|------------|------------|------------|------|
| `input_text` | 输入文本 | text | 发送给 API 的文本 |
| `input_audio` | 输入音频 | audio_file | 发送给 API 的音频文件 |
| `session_id` | 会话 ID | text | voice_llm 会话标识 |
| `context_history` | 上下文历史 | json | 对话历史（用于多轮） |
| `round_number` | 轮次编号 | number | 当前是第几轮 |

#### API 输出字段 (algorithm_api_params, direction='output')

| param_code | param_name | param_type | 说明 |
|------------|------------|------------|------|
| `llm_response` | LLM 回复文本 | text | voice_llm 返回的文本内容 |
| `response_audio` | 回复音频 | audio_file | voice_llm 返回的音频 |
| `response_latency` | 响应延迟 | number | 本轮响应耗时(ms) |
| `session_status` | 会话状态 | json | 会话状态信息 |

### build_create_task_data（动态映射，无硬编码分支）

```python
def build_create_task_data(self, algorithm_type, device_results, api_config, 
                            case_params=None, reference_params=None):
    """
    构建 create_task 请求数据。
    
    通用逻辑：从 param_mappings 表加载映射规则，动态构建请求体。
    不为 voice_llm 添加特殊分支。
    """
    # 加载本算法的 API 输入字段定义
    api_input_params = self.get_api_params(algorithm_type, direction='input')
    
    # 加载参数映射（case → api, reference → api 等）
    mappings = self.get_param_mappings(algorithm_type, source='case')
    
    # 动态构建请求体
    task_data = {
        'algorithm_type': algorithm_type,
        'input': {},
        'config': api_config,
    }
    
    # 根据 param_mappings 将 case_params 中的值映射到 input 字段
    for mapping in mappings:
        source_value = self._resolve_source(
            mapping.source, mapping.source_param,
            case_params=case_params,
            reference_params=reference_params,
            device_results=device_results
        )
        if source_value is not None:
            task_data['input'][mapping.target_param] = source_value
    
    return task_data
```

### case_params 与 algorithmParams 的关系

执行器从 `test_cases.config.rounds[i].algorithmParams` 中读取用户填写的参数值，
`algorithmParams` 为 `[{field_code, field_value}]` 数组格式，需要通过辅助函数提取：

```python
def get_param_value(params_list, field_code):
    """从 [{field_code, field_value}] 数组中提取指定参数的值"""
    for item in params_list:
        if item.get('field_code') == field_code:
            return item.get('field_value')
    return None
```

执行器中构建 `case_params` 传给 FieldMapper：

```python
# 执行器中
round_config = config['rounds'][i]
algorithm_params = round_config.get('algorithmParams', [])

# 构建 case_params（从数组格式中提取值）
case_params = {
    'input_text': get_param_value(algorithm_params, 'inputText'),
    'input_audio': get_param_value(algorithm_params, 'inputAudio'),
    'round_number': round_config.get('roundNumber', i + 1),
    'session_id': session_context.session_id if session_context else None,
    'context_history': session_context.get_history() if session_context else [],
}

# backgroundNoise 从 round 级别读取（不在 algorithmParams 中）
background_noise = round_config.get('backgroundNoise')
```

> **backgroundNoise 在 round 级别**：`backgroundNoise` 不属于 `algorithmParams` 数组，而是直接存储在 round 配置中（带 `loop` 属性），通过 `round_config.get('backgroundNoise')` 读取。

### get_case_fields（废弃）

旧设计中的 `get_case_fields` 方法为 voice_llm 硬编码返回字段列表，**应废弃**。
改用动态加载 `case_algorithm_params` 表：

```python
# 旧设计（废弃）
def get_case_fields(self, algorithm_type):
    if algorithm_type == 'voice_llm':
        return { 'rounds': ..., 'voiceprintRegistration': ... }
    return {}

# 新设计（动态加载）
def get_case_param_definitions(self, algorithm_type):
    """获取用例参数定义（来自 case_algorithm_params 表）"""
    return CaseAlgorithmParam.query.filter_by(
        algorithm_type=algorithm_type, deleted=False
    ).order_by(CaseAlgorithmParam.ui_order).all()
```

## 相关文档
- [07_voice_llm算法参数种子数据.md](07_voice_llm算法参数种子数据.md) — 参数定义
- [09_case_parameter_extractor适配.md](09_case_parameter_extractor适配.md) — 参数提取
- [11_algorithm_result_field_mapper适配.md](../../05_查看结果/backend/11_algorithm_result_field_mapper适配.md) — 结果映射
