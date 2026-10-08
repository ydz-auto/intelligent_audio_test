# 03 — LLM Judge 计算器

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：新增  
> **涉及文件**：`eval_server/app/services/calculators/xiaoyi_metrics/llm_judge/strategy.py`、`llm_judge_calculator.py`、`shared/llmClient.py`、`shared/constants.py`

---

## 背景

LLM Judge 使用大语言模型（默认 `gpt-4o-mini`，见 config）对设备回答进行语义级评分（1-5 分），适用于 voice_llm 场景中的对话质量评估。相比 WER 等确定性自动化指标，LLM Judge 能评估语义准确性、流畅度、相关性等主观维度。

在策略模式的 xiaoyi_metrics 家族中，`LlmJudgeCalculator` 是**独立的孤立策略节点**（不在 turn_taking 主维度的 `_SUB_DIMENSIONS` 内，注册 `llm_judge` 键，仅 1 键 1 类），但它复用了与 turn_taking 共享的两条基础设施：

1. **shared/llmClient 统一 LLM 客户端**：`callLlm() / parseJson()` 取代了此前分散在各文件里的 5 处重复实现（llmClient docstring 明确列出收敛对象）
2. **shared/constants 常量收敛**：`LLM_DEFAULT_MAX_TOKENS(4096)` / `LLM_DEFAULT_TEMPERATURE(0.1)` 等魔法数字不再散落

架构链路：`POST /api/create_task(llm_judge)` → `_validate_and_dispatch_task`（白名单校验）→ `calculate_in_process` → `TaskService.calculate()` 注册表路由 → `LlmJudgeCalculator.run()`（参考 `02_评估维度架构` 第 3 章）。

---

## 实际实现

### 1. 策略类注册与调度

`LlmJudgeCalculator(BaseCalculator)`（strategy.py）实现三阶段接口：

- `validate()`：单轮要求 `rounds[round_number]` 有 `answer`；多轮要求**至少一轮**有 `answer`
- `prepare_params()`：单轮取当前轮字段；多轮逐轮收集 `round_items`
- `calculate()`：调 `callLlm() + parseJson()`

```python
TaskService.register_calculator('llm_judge', LlmJudgeCalculator())  # calculators/__init__.py
```

单轮/多轮判定由 `round_number` 驱动：

- `round_number` 有值（0/1/2…）→ **单轮评估**：只取 `rounds[round_number]` 的 query/answer/correct_answer，算 1 次（`_iter_rounds` 只 yield 该轮）
- `round_number` 不存在 → **多轮整体评估**：逐轮评分，数值字段取平均（`round(x, 3)`），非数值取最后一轮，附加 `n_rounds` / `per_round`（`_aggregate_results`）

取参顺序（`_extract_round_fields`）：顶层 `query|question` → 当前轮 `query|question`；顶层 `answer` → 当前轮 `answer`；`correct_answer` 同理。`{'text': ..., 'json': [...]}` 格式值自动解包（`_unwrap_value`）为 text。

### 2. 参数定义（与 param_mappings target_param 一致）

| 字段 | 说明 |
|------|------|
| `answer` | 设备回答 |
| `correct_answer` | 参考答案 |
| `question` | 设备识别的问题 |
| `query` | 参考问题 |
| `record_file` | 音频文件路径（进入多模态） |
| `rounds` | 多轮数据 `[{answer, correct_answer, ...}, ...]` |
| `model` | LLM 模型名，默认 `config.LLM_JUDGE.default_model` |
| `prompt` | 自定义评分 prompt 模板 |
| `max_tokens` / `temperature` / `scoring_criteria` | LLM 调用参数（均有默认值） |

### 3. 默认参数口径（三处需区分，以代码为准）

| 位置 | model 默认 | max_tokens 默认 | temperature 默认 |
|------|-----------|----------------|-----------------|
| 策略类 `_extract_llm_config` (strategy.py) | `config.LLM_JUDGE.default_model`，无配置回退 `'gpt-4'` | `1024`（调用方或轮次未传时） | `0.1` |
| 底层 `evaluate_with_llm` 签名 (llm_judge_calculator.py) | `'deepseek-r1'` | `LLM_DEFAULT_MAX_TOKENS` → `4096` | `LLM_DEFAULT_TEMPERATURE` → `0.1` |
| `config.LLM_JUDGE` (config.py) | `gpt-4o-mini` | `4096` | `0.1` |

> 当前环境实际生效：策略路由（API 调用）走 **config 默认 `gpt-4o-mini`**（`_extract_llm_config` 回退仅兜底）；`evaluate_with_llm` 作为非注册式复用函数，其 `deepseek-r1`/4096/0.1 是函数签名级默认值，调用方可覆盖。

### 4. 策略类计算流程（calculate）

统一走 **shared/llmClient.callLlm**（OpenAI 兼容、指数退避重试、json_object 解析，见 02 文档 shared 章节），结果经 `parseJson` 取 `score` / `reason`。

**单轮出参**：

```json
{
  "enabled": true,
  "llm_judge_score": 4,
  "criteria_scores": null,
  "reasoning": "打分理由",
  "model": "gpt-4o-mini"
}
```

**多轮出参**：外层为 `_aggregate_results` 聚合结果（数值字段平均 + 最后一轮字段 + `n_rounds` + `per_round`），并 `setdefault('enabled', True)` / `setdefault('model', model)`。

异常兜底：

- 全部轮次无有效 answer → `{"enabled": False, "message": "所有轮次均无有效 answer"}`
- `callLlm` 抛异常 → 该轮 `score=0, reason=str(e)`（错误不中断整批）
- LLM 输出无法解析 → `score=0, reason='LLM 输出解析失败'`

**prompt 填充**：`prompt_template.format(query=query, hypothesis=answer)`，`KeyError/IndexError` 时原样使用模板。

### 5. 底层函数 evaluate_with_llm（非注册式复用）

`llm_judge_calculator.py` 的 `evaluate_with_llm(...)` 供未走策略注册的调用方复用（含多模态），流程：

1. **音频收集**：`extractVideoPaths(kwargs)`（音频/视频扩展名 + 文件存在）附加 `record_file`，非空则构建多模态消息（base64 data URI / image_url 格式）
2. **prompt 构建**：有 `rounds` → `_build_rounds_prompt` 逐轮列出（不拼接），`custom_prompt.format(dialog=...)` 优先，否则内置中文模板；无 `rounds` → `_build_evaluation_prompt`，优先级 `custom_prompt → config.LLM_JUDGE.prompt_template → 内置模板`
3. **LLM 调用**：`callLlm(model, prompt, maxTokens, temperature, filePaths)`（重试/超时/解析全部在 shared/llmClient 内）
4. **结果构建** `_build_result`：`parseJson` 取 `score`/`reason`，失败时 `reason` 回退为原始 `content`

**底层返回结构**：

```json
{
  "llm_judge_score": 4,
  "reasoning": "打分理由",
  "tokens_used": 256,
  "input_token": 100,
  "output_token": 156,
  "model": "gpt-4o-mini"
}
```

### 6. 配置项（config.py）

```python
LLM_JUDGE = {
    'api_base_url': os.environ.get('LLM_JUDGE_API_BASE', 'https://az.gptplus5.com/v1'),
    'api_key': os.environ.get('LLM_JUDGE_API_KEY', ''),
    'default_model': os.environ.get('LLM_JUDGE_DEFAULT_MODEL', 'gpt-4o-mini'),
    'max_tokens': int(os.environ.get('LLM_JUDGE_MAX_TOKENS', '4096')),
    'temperature': float(os.environ.get('LLM_JUDGE_TEMPERATURE', '0.1')),
    'timeout': int(os.environ.get('LLM_JUDGE_TIMEOUT', '120')),
    'prompt_template': '...',   # 中文评分规则模板（format: {query} / {hypothesis}）
}
```

`prompt_template` 用 `format(query=..., hypothesis=...)` 填充，模板未包含对应占位符时原样使用。

---

## 不变部分

- `BaseCalculator` 策略框架不变（validate/prepare_params/calculate 三阶段）
- 其他计算器（wer/ser/der 等）不受影响
- 任务存储（TaskModel）不变
- 单轮/多轮判定与聚合语义不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `02_评估维度架构_策略模式与主从维度` | 策略模式骨架、shared/llmClient 与 shared/constants 基础设施、孤立策略节点定位 |
| `01_create_task新任务类型` | 任务入口与参数校验（llm_judge 白名单 15 项之一） |
| `04_ConcurrencyManager动态类型` | llm_judge 并发限制 |
| `25_evaluation_service单轮评估` (主后端) | 请求发送方与 round_number 驱动 |
| `26_evaluation_api_client适配` (主后端) | 主后端请求构建与文件上传 |