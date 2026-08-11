# 08 - field_mapper voice_llm 映射（参数驱动版）

## 涉及文件
- `Intelligent-Audio-TEST/backend/algorithm/field_mapper.py`

## 现状分析

FieldMapper 是单例类，负责：
- 提供设备/API/评估的字段定义查询
- 字段类型转换和数据格式转换
- 构建 API 请求数据（单轮流程）

核心方法：
- `get_device_params(algorithm_type)` — 获取设备参数定义
- `get_api_params(algorithm_type)` — 获取 API 参数定义
- `get_param_mappings(algorithm_type, source)` — 获取参数映射
- `build_create_task_data(algorithm_type, ...)` — 构建 create_task 请求体（**仅用于单轮流程**）

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

### build_create_task_data（单轮流程使用）

`build_create_task_data` **仅用于单轮流程**的 `_create_task` 阶段。多轮流程不使用此方法。

```python
def build_create_task_data(
    self,
    algorithm_type: str,
    audio_path: str = None,
    vendor: str = None,
    max_process: int = None,
    max_timeout: int = None,
    endpoints: List[Dict] = None,
    case_config: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """构建API创建任务的请求数据（单轮流程）"""
    api_input_fields = self.get_api_input_fields(algorithm_type)

    task_data = {}
    case_params = case_config.get('algorithm_params', {}) if case_config else {}
    param_sources = {**case_params, **kwargs}

    explicit_params = {
        'audio_path': audio_path,
        'audio_url': audio_path,
        'vendor': vendor,
        'max_process': max_process,
        'max_timeout': max_timeout,
        'endpoints': endpoints
    }
    for k, v in explicit_params.items():
        if v is not None:
            param_sources[k] = v

    for field_code, field_def in api_input_fields.items():
        transform = field_def.get('transform', 'none')
        value = param_sources.get(field_code)
        if value is not None:
            transform_func = self._transforms.get(transform, lambda x: x)
            task_data[field_code] = transform_func(value)

    return task_data
```

### 多轮流程不使用 field_mapper 的原因

多轮流程（`_send_round_request`）采用**模板驱动**方式，不使用 `build_create_task_data`：

| 对比项 | 单轮流程 | 多轮流程 |
|--------|----------|----------|
| 请求构建 | `field_mapper.build_create_task_data()` | `_build_round_context()` + `APIDriver.render_request_parts()` |
| 数据来源 | `case_config.algorithm_params` 字典 | `SessionContext` + `algorithmParams` 数组 |
| session_id | 不涉及 | `SessionContext` 动态生成 |
| context_history | 不涉及 | `SessionContext.get_context()` 动态生成 |
| round_number | 不涉及 | 循环变量 |
| 请求格式 | 由 `api_input_fields` 决定 | 由 API 表 `body_template` + `headers` 决定 |

详细设计见 [14_轮次请求构建.md](../../04_执行测试/backend/14_轮次请求构建.md)。

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

> **backgroundNoise 在 round 级别**：`backgroundNoise` 不属于 `algorithmParams` 数组，而是直接存储在 round 配置中（带 `loop` 属性），通过 `round_config.get('backgroundNoise')` 读取。

### get_case_fields（保留，不废弃）

`get_case_fields` 方法保留用于单轮流程的字段查询。多轮流程通过 `_build_round_context` 独立处理上下文构建。

```python
def get_case_fields(self, algorithm_type: str) -> Dict[str, str]:
    """获取算法需要的case表字段（单轮流程使用）"""
    case_fields = {}
    device_params = self._get_device_params(algorithm_type)
    api_params = self._get_api_params(algorithm_type)
    params = device_params + api_params

    for param in params:
        param_code = param.get('code', '')
        param_type = param.get('param_type', '')
        source = param.get('source', '')
        if source == 'case_table' or param_type in ['direction', 'language']:
            case_fields[param_code] = param_code

    mappings = self._get_param_mappings(algorithm_type)
    for comp_type, comp_mappings in mappings.items():
        for mapping in comp_mappings:
            source_param = mapping.get('source_param', '')
            target_key = mapping.get('target_key', source_param)
            source = mapping.get('source', '')
            if source == 'case_table':
                case_fields[target_key] = source_param

    return case_fields
```

## 相关文档
- [07_voice_llm算法参数种子数据.md](07_voice_llm算法参数种子数据.md) — 参数定义
- [09_case_parameter_extractor适配.md](../../02_选用例/backend/09_case_parameter_extractor适配.md) — 参数提取
- [14_轮次请求构建.md](../../04_执行测试/backend/14_轮次请求构建.md) — 多轮请求构建（模板驱动）
- [11_algorithm_result_field_mapper适配.md](../../05_查看结果/backend/11_algorithm_result_field_mapper适配.md) — 结果映射
