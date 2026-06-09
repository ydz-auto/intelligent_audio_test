# API 多轮用例端到端示例

> 本文档以一个完整的 API 多轮测试用例为例，从前端配置 → 任务创建 → 三服务执行流程 → 评估 → 结果存储 → 报告展示，完整走一遍数据流。
>
> 与 E2E 示例（`99_E2E用例端到端示例.md`）对比：API 测试不涉及物理设备，通过 api_adapter_service 中转调用被测云端 API。
>
> **参数驱动**：所有用例表单字段由 `case_algorithm_params` 表定义驱动，DynamicForm 动态渲染。音频走 `audios` 用例默认参数（与 E2E 一致），文本走 `algorithmParams` 中 `field_code=inputText` 的算法特定参数。

---

## 测试场景

- **被测目标**：某云端语音交互 API（voice_llm），提供对话能力
- **测试目标**：4 轮多轮对话（含追问、上下文依赖、多模态输入），评估 ASR 识别准确率、翻译质量和语义评分
- **会话模式**：`full`（完整上下文），超时 60s/轮
- **输入方式**：3 轮纯文本 + 1 轮**文本+音频共存**（多模态输入）
- **评估维度**：WER（词错误率）、BLEU（翻译质量）、LLM Judge（语义评分）
- **三服务协作**：主后端 → api_adapter_service (8000) → 被测厂商 API (9000)

---

## 一、前端配置

用户在 `CaseForm` 中填写，`test_type = 'api'`。

### 参数驱动表单

CaseForm 根据 `algorithmType = 'voice_llm'` 从后端加载参数定义（详见 `06_CaseForm_test_type驱动.md`、`24_AlgorithmConfigPage_voice_llm.md`）：

- **case_algorithm_params 表**（scope=api+common）→ DynamicForm 渲染算法参数表单（含 inputText）
- **音频列表** → AudioConfigList 渲染（与 E2E 一致，API 模式简化：仅选音频，无设备/SPL）

### 用户配置

```
CaseForm (test_type = 'api')
├── 基础信息
│   ├── 名称: "语音助手多轮对话-中文场景"
│   ├── 算法类型: voice_llm
│   └── 标签: ["多轮", "中文", "追问"]
│
├── 多轮配置 (RoundConfigEditor) — rounds[]
│   │
│   ├── 第 1 轮 (round_1)
│   │   ├── audios: [] (纯文本输入，无音频)
│   │   ├── algorithmParams:
│   │   │   └── inputText: "你好，我想了解一下天气"
│   │   ├── evaluation: WER + BLEU + LLM Judge
│   │   └── referenceParamsPath: /references/round1_ref.json
│   │
│   ├── 第 2 轮 (round_2)
│   │   ├── audios: []
│   │   ├── algorithmParams:
│   │   │   └── inputText: "那明天呢？"
│   │   ├── evaluation: WER + BLEU + LLM Judge
│   │   └── referenceParamsPath: /references/round2_ref.json
│   │
│   ├── 第 3 轮 (round_3)
│   │   ├── audios: [audio_303] (音频输入)
│   │   ├── algorithmParams:
│   │   │   ├── inputText: "请听这段录音"
│   │   │   └── inputAudio: "audio_303"
│   │   ├── evaluation: WER + BLEU + LLM Judge
│   │   └── referenceParamsPath: /references/round3_ref.json
│   │
│   └── 第 4 轮 (round_4)
│       ├── audios: []
│       ├── algorithmParams:
│       │   └── inputText: "帮我设个提醒，明天出门带伞"
│       ├── evaluation: WER + BLEU + LLM Judge
│       └── referenceParamsPath: /references/round4_ref.json
│
└── 整体评估维度
    └── WER (dim_1, weight=50), BLEU (dim_5, weight=30), LLM Judge (dim_8, weight=20)
```

> **每轮结构**：`audios`（音频列表）+ `algorithmParams`（算法参数，`[{field_code, field_value}]` 格式）+ `evaluation` + `referenceParamsPath`。
> API 模式下 `audios` 简化为仅选音频文件（无播放设备/SPL），`algorithmParams` 中 `inputText`/`inputAudio` 由 `case_algorithm_params` 表（scope=api+common）驱动渲染。

---

## 二、APITest 向导流程 & Config 存储

### APITest.vue 5 步向导

```
APITest.vue 向导:
Step 0 — 选算法: AlgorithmSelectionPanel → voice_llm
Step 1 — 选用例: TestCaseListContainer → test_type='api' 过滤（详见 16_APITest页面适配.md）
Step 2 — 选被测API: ResourceSelectionGrid → 按 algorithmType 过滤 API 列表
Step 3 — 执行测试: TestExecutionComponent
Step 4 — 查看结果: TaskReportPanel
```

### Step 2：选择被测 API

用户在 `ResourceSelectionGrid` 中选择要测试的 API 端点：

```
ResourceSelectionGrid (Step 2)
├── API 列表按 algorithmType='voice_llm' 过滤
├── 仅允许选择在线的 API（status='online'）
├── 支持搜索和分页
└── 选中: voice_llm_api_001（某云端语音交互 API）
```

任务创建时，`apiTest.ts` 的 `handleStartTask` 将选中的 API ID 传入：

```ts
const payload = {
  name: taskName.value,
  type: 'api',
  algorithmType: 'voice_llm',
  caseIds: selectedTestCaseIds.value,
  apiIds: selectedAPIIds.value,     // 选中的被测 API
  tags: selectedTags.value
}
const task = await tasksApi.create(payload)
await tasksApi.start(task.id)
```

> 详见 `03_选设备API/frontend/16_APITest页面适配.md`、`03_选设备API/00_步骤总览.md`。

### Config JSON 存储

API 测试用例为**单条记录**（不同于 E2E 的双记录模式）：

```
TestCase (DB)
└── id=201, test_type='api', name='语音助手多轮对话-中文场景'
    config = { rounds: [...] }
```

config JSON（参数驱动版）：

```json
{
  "rounds": [
    {
      "roundNumber": 1,
      "audios": [],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "dimension_id": 1, "dimension_name": "WER", "params": { "case_sensitive": false } },
          { "dimension_id": 5, "dimension_name": "BLEU", "params": {} },
          { "dimension_id": 8, "dimension_name": "回答质量评估", "resultType": "llm_judge",
            "params": { "model": "gpt-4", "promptTemplate": "default" } }
        ]
      },
      "algorithmParams": [
        { "field_code": "inputText", "field_value": "你好，我想了解一下天气" }
      ],
      "referenceParamsPath": "/references/round1_ref.json"
    },
    {
      "roundNumber": 2,
      "audios": [],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "dimension_id": 1, "dimension_name": "WER", "params": { "case_sensitive": false } },
          { "dimension_id": 5, "dimension_name": "BLEU", "params": {} },
          { "dimension_id": 8, "dimension_name": "回答质量评估", "resultType": "llm_judge",
            "params": { "model": "gpt-4", "promptTemplate": "default" } }
        ]
      },
      "algorithmParams": [
        { "field_code": "inputText", "field_value": "那明天呢？" }
      ],
      "referenceParamsPath": "/references/round2_ref.json"
    },
    {
      "roundNumber": 3,
      "audios": [
        { "audio_id": "audio_303" }
      ],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "dimension_id": 1, "dimension_name": "WER", "params": { "case_sensitive": false } },
          { "dimension_id": 5, "dimension_name": "BLEU", "params": {} },
          { "dimension_id": 8, "dimension_name": "回答质量评估", "resultType": "llm_judge",
            "params": { "model": "gpt-4", "promptTemplate": "default" } }
        ]
      },
      "algorithmParams": [
        { "field_code": "inputText", "field_value": "请听这段录音" },
        { "field_code": "inputAudio", "field_value": "audio_303" }
      ],
      "referenceParamsPath": "/references/round3_ref.json"
    },
    {
      "roundNumber": 4,
      "audios": [],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "dimension_id": 1, "dimension_name": "WER", "params": { "case_sensitive": false } },
          { "dimension_id": 5, "dimension_name": "BLEU", "params": {} },
          { "dimension_id": 8, "dimension_name": "回答质量评估", "resultType": "llm_judge",
            "params": { "model": "gpt-4", "promptTemplate": "default" } }
        ]
      },
      "algorithmParams": [
        { "field_code": "inputText", "field_value": "帮我设个提醒，明天出门带伞" }
      ],
      "referenceParamsPath": "/references/round4_ref.json"
    }
  ],
  "dimensions": [
    { "dimension_id": 1, "dimension_name": "WER", "params": { "case_sensitive": false } },
    { "dimension_id": 5, "dimension_name": "BLEU", "params": {} },
    { "dimension_id": 8, "dimension_name": "回答质量评估", "resultType": "llm_judge",
      "params": { "model": "gpt-4", "promptTemplate": "default" } }
  ]
}
```

> **注意**：
> - 没有 `inputType` 字段（已废弃）
> - 音频走 `audios` 用例默认参数（与 E2E 的干声列表一致，API 模式简化：仅 `audio_id`，无设备/SPL）
> - 文本走 `algorithmParams` 中 `field_code=inputText` 的算法特定参数
> - 第3轮同时有 `audios` 和 `algorithmParams`（含 inputText + inputAudio），实现文本+音频输入
> - 所有算法参数统一在 `algorithmParams` 中，`[{field_code, field_value}]` 格式
> - 参考参数存文件，通过 `referenceParamsPath` 引用

---

## 三、apis 表厂商配置

用户在 Device.vue「测试API管理」中配置被测 API，数据存入 `apis` 表：

```
API (DB, id=301)
├── name: "语音助手API-火山引擎"
├── vendor: "volc_llm"
├── api_url: "http://192.168.1.100:9000"
├── algorithm_type: "voice_llm"
├── status: "online"
├── max_process: 5
├── max_timeout: 60
├── max_audio_duration: 120
├── meta: {
│     "protocol": "http",
│     "method": "POST",
│     "headers": {
│       "Authorization": "Bearer {{api_key}}",
│       "Content-Type": "application/json"
│     },
│     "body_template": { ... },
│     "response_mappings": {
│       "asr_text_path": "result.asr_text",
│       "trans_text_path": "result.translated_text",
│       "session_id_path": "session_id"
│     },
│     "session": {
│       "context_mode": "full",
│       "max_history_rounds": 10,
│       "session_timeout": 120
│     }
│   }
└── api_endpoints: [
      {
        "endpoint": "http://192.168.1.100:9000",
        "name": "主节点",
        "max_process": 5,
        "max_timeout": 60,
        "status": "online",
        "priority": 0
      }
    ]
```

> **核心设计**：所有 API 配置由主服务从 `apis` 表加载，构建 `ExecutionConfig` 传给适配器。
> 适配器不持有配置状态，每次调用由主服务传入。新增厂商只需在数据库新增记录，无需重启服务。

---

## 四、执行流程

用户点击"创建任务" → 任务启动 → `APIExecutor.execute_api_case(task_id='task_002', case_id=201)`。

### Phase 1: 初始化

```python
data = self._validate_and_get_data(app, task_id, tc_rel_id)
case_config = data['case_config']

rounds = case_config.get('rounds', [])   # 非空 → 进入多轮会话

# 健康检查 api_adapter_service
health = requests.get("http://localhost:8000/health")
# → { status: 'healthy', dialog_sessions: 0, supported_modes: ['streaming', 'dialog'] }
```

### Phase 2: 创建会话

```python
session_id = str(uuid.uuid4())   # "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

session = SessionContext(session_id, {
    'session_timeout': 60,
    'context_mode': 'full',
    'max_history_rounds': 5,
})
# session.is_active = True
# session._context_history = []
# session._round_results = []
```

同时，`api_adapter_service` 端的 `SessionStore` 在收到第一轮请求时也会创建对应会话。

### Phase 3: 多轮循环

#### 第 1 轮 (round=1, 纯文本输入)

```
Step 1 — 构建请求体

  algo_params = CaseParameterExtractor.convert_params_to_dict(round.algorithmParams)
  # → { "inputText": "你好，我想了解一下天气" }
  context     = session.get_context() = []   (第 1 轮无历史)

  request_body = {
    "task_type": "voice_llm",
    "session_id": "a1b2c3d4-...",
    "round": 1,
    "input": { "text": "你好，我想了解一下天气" },
    "context": [],
    "vendor_config": {
      "api_url": "http://192.168.1.100:9000/chat",
      "headers": { "Authorization": "Bearer sk-voice-llm-api-key-xxx" },
      "timeout": 60
    }
  }

Step 2 — 发送到 api_adapter_service (端口 8000)

  POST http://localhost:8000/api/v1/tasks
  Body: request_body

  api_adapter_service 处理:
  ├── create_dialog_task(task_id="adapter_task_001", session_id="a1b2c3d4-...")
  ├── SessionStore.create_session(session_id, task_id, context_mode='full')
  ├── HttpAdapter.send_request(
  │     session_id="a1b2c3d4-...",
  │     input_text="你好，我想了解一下天气",
  │     input_audio=None,
  │     context=[]
  │   )
  │   → POST http://192.168.1.100:9000/chat
  │     Headers: Authorization=Bearer sk-..., X-Session-Id=a1b2c3d4-...
  │     Body: { session_id, input: {text:"..."}, context: [] }
  │
  │   被测 API 返回:
  │   {
  │     "session_id": "a1b2c3d4-...",
  │     "result": {
  │       "asr_text": "你好我想了解一下天气",
  │       "translated_text": "Hello, I'd like to know about the weather",
  │       "response": "今天北京天气晴朗，气温28°C，适合户外活动。"
  │     }
  │   }
  │
  ├── SessionStore.add_round(session_id, round=0, input="你好...", output="今天北京...")
  └── TaskManager.add_round_result → update_task_status('completed')

  api_adapter 返回主后端:
  {
    "output_content": "今天北京天气晴朗，气温28°C，适合户外活动。",
    "asr_text": "你好我想了解一下天气",
    "trans_text": "Hello, I'd like to know about the weather",
    "response_metrics": { "first_token_latency": 0.3, "tokens_per_second": 25 }
  }

Step 3 — 主后端提取结果

  round_result = {
    "roundNumber": 1,
    "input": { "text": "你好，我想了解一下天气" },
    "output": "今天北京天气晴朗，气温28°C，适合户外活动。",
    "latency": 1.23,
    "response_metrics": { "first_token_latency": 0.3, "tokens_per_second": 25 }
  }

Step 4 — 更新 SessionContext

  session.add_history(1, "你好，我想了解一下天气", "今天北京天气晴朗...")
  session.add_round_result(round_result)

Step 5 — 单轮评估 (evaluation.enabled=true)

  → evaluation_service.evaluate_case(round_number=0)
  → 提取 rounds[0] 数据:
    hypothesis = "今天北京天气晴朗，气温28°C，适合户外活动。"
    reference  = 从 round.referenceParamsPath 加载 → "今天北京天气晴朗，气温28度，适合户外活动"

  → 分发 3 个维度:
    WER  → eval_server: WER = 0.02 (1 处差异: "28°C" vs "28度")
    BLEU → eval_server: BLEU = 0.95
    LLM Judge → eval_server → GPT-4:
      {
        "scores": { "accuracy": 4.8, "fluency": 5.0, "relevance": 5.0 },
        "overall_score": 4.9,
        "reasoning": "输出准确完整，表达自然流畅"
      }

  → 写入 3 条 TestResultDimension (round_number=0)
```

#### 第 2 轮 (round=2, 纯文本, 追问)

```
Step 1 — 构建请求体

  algo_params = CaseParameterExtractor.convert_params_to_dict(round.algorithmParams)
  # → { "inputText": "那明天呢？" }
  context = session.get_context() (1 轮历史, full 模式)

  request_body.input = { "text": "那明天呢？" }
  request_body.context = [{ round: 1, ... }]

Step 2 — api_adapter_service 处理

  HttpAdapter.send_request(
    input_text="那明天呢？",
    input_audio=None,
    context=[{role:"user",content:"你好..."}, {role:"assistant",content:"今天北京..."}]
  )
  → POST 被测 API (携带上下文 → API 理解"明天"是指天气)

  被测 API 返回:
  {
    "result": {
      "asr_text": "那明天呢",
      "translated_text": "What about tomorrow?",
      "response": "明天北京多云转晴，气温25°C，午后可能有短时阵雨。"
    }
  }

  SessionStore.add_round → context_history 增长到 4 条消息

Step 3 — 结果

  round_result = {
    "roundNumber": 2,
    "input": { "text": "那明天呢？" },
    "output": "明天北京多云转晴，气温25°C，午后可能有短时阵雨。",
    "latency": 1.87
  }

Step 4 — 更新 SessionContext

  session._context_history 增长到 2 轮

Step 5 — 单轮评估

  hypothesis = "明天北京多云转晴，气温25°C，午后可能有短时阵雨。"
  reference  = "明天北京多云转晴，气温25度，午后可能有短时阵雨"

  WER = 0.03, BLEU = 0.93
  LLM Judge: overall_score = 4.7, "准确回答了追问，上下文理解正确"
```

#### 第 3 轮 (round=3, 文本+音频输入)

```
Step 1 — 构建请求体

  algo_params = CaseParameterExtractor.convert_params_to_dict(round.algorithmParams)
  # → { "inputText": "请听这段录音", "inputAudio": "audio_303" }
  audio_id = round.audios[0].audio_id = "audio_303"   (用例默认参数)

  文本走 algorithmParams（算法特定参数），音频走 audios（用例默认参数）。
  执行器将两者组合发送给 API 适配器。

  context = session.get_context() (2 轮历史)

  request_body = {
    "input": {
      "text": "请听这段录音",
      "audio_path": "/uploads/task_002/query3.wav"
    },
    "context": [...]
  }

Step 2 — api_adapter_service 处理

  HttpAdapter.send_request(
    input_text="请听这段录音",
    input_audio="audio_303" (来自 round.audios[0]) → 上传文件获取 audio_path
  )
  → POST 被测 API (multipart/form-data)
    data:  { session_id, input_text: "请听这段录音", input_audio: "...", context: "[...]" }
    files: { "audio": ("query3.wav", <bytes>, "audio/wav") }

  被测 API 返回:
  {
    "result": {
      "asr_text": "后天天气怎么样",
      "translated_text": "How about the day after tomorrow?",
      "response": "后天北京晴间多云，气温26到30度，适合出行。"
    }
  }

Step 3 — 结果

  round_result = {
    "roundNumber": 3,
    "input": { "text": "请听这段录音", "audio_id": "audio_303" },
    "output": "后天北京晴间多云，气温26到30度，适合出行。",
    "latency": 2.45,
    "response_metrics": {}
  }
  (音频走 audios 用例默认参数 + 文本走 algorithmParams 算法参数，延迟较高: 2.45s)

Step 5 — 单轮评估

  WER = 0.04, BLEU = 0.90
  LLM Judge: 4.5, "ASR 识别准确，回答完整"
```

> **设计对齐**：音频走 `audios`（用例默认参数，与 E2E 干声列表一致），
> 文本走 `algorithmParams` 中 `field_code=inputText`（算法特定参数）。
> 两者独立，可同时存在实现文本+音频输入。

#### 第 4 轮 (round=4, 纯文本, 指令型)

```
Step 1 — 构建请求体

  algo_params = CaseParameterExtractor.convert_params_to_dict(round.algorithmParams)
  # → { "inputText": "帮我设个提醒，明天出门带伞" }
  context   = session.get_context() (3 轮历史, full 模式)

Step 2 — api_adapter_service 处理

  被测 API 返回:
  {
    "result": {
      "asr_text": "帮我设个提醒明天出门带伞",
      "translated_text": "Set a reminder for me to bring an umbrella tomorrow",
      "response": "好的，已为您设置提醒：明天出门请带伞。"
    }
  }

Step 3 — 结果

  round_result = {
    "roundNumber": 4,
    "input": { "text": "帮我设个提醒，明天出门带伞" },
    "output": "好的，已为您设置提醒：明天出门请带伞。",
    "latency": 1.05,
    "response_metrics": { "first_token_latency": 0.2 }
  }

Step 5 — 单轮评估

  WER = 0.0 (完全匹配), BLEU = 0.97
  LLM Judge: 5.0, "指令执行准确，回复简洁明了"
```

### Phase 4: 汇总 & 收尾

```python
# 汇总多轮结果
all_results = session.get_round_results()   # 4 条轮次结果
summary = session.get_summary()

# 保存到 DB
self._save_multi_round_results(task_id, tc_rel_id, aggregated, session.session_id)

# 整体评估入队
self._enqueue_evaluation(task_id, tc_rel_id, aggregated)

# 销毁会话 (主后端 + api_adapter)
session.destroy()
# api_adapter: SessionStore.destroy_session("a1b2c3d4-...")
```

---

## 五、三服务交互时序

```
主后端 (APIExecutor)            api_adapter_service (8000)      被测厂商 API (9000)
    │                              │                              │
    │  health_check                │                              │
    │──GET /health ───────────────→│                              │
    │←─{status:healthy} ──────────│                              │
    │                              │                              │
    │  创建 SessionContext          │                              │
    │  session_id="a1b2c3d4-..."   │                              │
    │                              │                              │
    │  ════ 第 1 轮 (文本) ═════   │                              │
    │                              │                              │
    │──POST /api/v1/tasks ────────→│                              │
    │  {session_id, round:1,       │  create_session              │
    │   input:{text:"你好..."},    │  HttpAdapter.send_request     │
    │   context:[]}                │                              │
    │                              │──POST /chat ────────────────→│
    │                              │  {session_id, input, context} │
    │                              │←─{asr_text, trans_text, ────│
    │                              │   response, session_id}       │
    │                              │  add_round → context 更新     │
    │←─{output_content, metrics}──│                              │
    │  session.add_history(1,...)  │                              │
    │  单轮评估 → eval_server      │                              │
    │                              │                              │
    │  ════ 第 2 轮 (文本) ═════   │                              │
    │                              │                              │
    │──POST /api/v1/tasks ────────→│  get_context → 2 条历史       │
    │  {input:{text:"那明天呢？"}, │──POST /chat ────────────────→│
    │   context:[{round:1,...}]}   │  (携带上下文 → 理解"明天")    │
    │                              │←─{response:"明天北京..."} ──│
    │←─{output_content} ──────────│  add_round → context 4 条     │
    │  session.add_history(2,...)  │                              │
    │  单轮评估                    │                              │
    │                              │                              │
    │  ════ 第 3 轮 (文本+音频) ═  │                              │
    │                              │                              │
    │──POST /api/v1/tasks ────────→│                              │
    │  {input:{text:"请听...",     │──POST /chat (multipart) ───→│
    │   audio_path:"..."},         │  (文本来自 algorithmParams,  │
    │   context:[2轮历史]}         │   音频来自 round.audios)      │
    │                              │←─{asr_text:"后天天气..."} ──│
    │←─{output_content} ──────────│                              │
    │  session.add_history(3,...)  │                              │
    │  单轮评估                    │                              │
    │                              │                              │
    │  ════ 第 4 轮 (文本) ═════   │                              │
    │                              │                              │
    │──POST /api/v1/tasks ────────→│──POST /chat ────────────────→│
    │  {input:{text:"帮我设个..."},│←─{response:"好的，已设置..."}│
    │   context:[3轮历史]}         │                              │
    │←─{output_content} ──────────│                              │
    │  session.add_history(4,...)  │                              │
    │  单轮评估                    │                              │
    │                              │                              │
    │  ════ 收尾 ═══════════════   │                              │
    │                              │                              │
    │  _save_multi_round_results   │                              │
    │  session.destroy()           │  cleanup_expired (定时)       │
```

---

## 六、结果存储

### 6.1 algorithm_result (写入 TestResult.algorithm_result)

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "round_count": 4,
  "total_latency": 6.60,
  "context_mode": "full",
  "history_count": 4,
  "error": null,
  "rounds": [
    {
      "roundNumber": 1,
      "input": { "text": "你好，我想了解一下天气" },
      "output": "今天北京天气晴朗，气温28°C，适合户外活动。",
      "latency": 1.23,
      "response_metrics": { "first_token_latency": 0.3, "tokens_per_second": 25 },
      "round_evaluation": { "wer": 0.02, "bleu": 0.95, "llm_judge": 4.9 }
    },
    {
      "roundNumber": 2,
      "input": { "text": "那明天呢？" },
      "output": "明天北京多云转晴，气温25°C，午后可能有短时阵雨。",
      "latency": 1.87,
      "response_metrics": {},
      "round_evaluation": { "wer": 0.03, "bleu": 0.93, "llm_judge": 4.7 }
    },
    {
      "roundNumber": 3,
      "input": { "text": "请听这段录音", "audio_id": "audio_303" },
      "output": "后天北京晴间多云，气温26到30度，适合出行。",
      "output_audio_path": null,
      "latency": 2.45,
      "response_metrics": {},
      "round_evaluation": { "wer": 0.04, "bleu": 0.90, "llm_judge": 4.5 }
    },
    {
      "roundNumber": 4,
      "input": { "text": "帮我设个提醒，明天出门带伞" },
      "output": "好的，已为您设置提醒：明天出门请带伞。",
      "latency": 1.05,
      "response_metrics": { "first_token_latency": 0.2 },
      "round_evaluation": { "wer": 0.00, "bleu": 0.97, "llm_judge": 5.0 }
    }
  ]
}
```

> **aggregated 字段来源**：`evaluation_result_processor.aggregate_round_results()` 在所有轮次评估完成后计算。

### 6.2 TestResultDimension 记录

每轮评估产生 3 条维度记录（WER/BLEU/LLM Judge），4 轮共 12 条 + 3 条整体评估：

```
TestResultDimension 表:
┌─────┬──────────────┬──────────────┬───────┬──────────────────────────────────┐
│ id  │ dimension_name│ round_number │ score │ 说明                             │
├─────┼──────────────┼──────────────┼───────┼──────────────────────────────────┤
│ 601 │ WER          │ 0            │ 98.0  │ 第1轮: WER=0.02                  │
│ 602 │ BLEU         │ 0            │ 0.95  │ 第1轮                            │
│ 603 │ 回答质量评估  │ 0            │ 4.9   │ 第1轮 LLM Judge                  │
│ 604 │ WER          │ 1            │ 97.0  │ 第2轮: WER=0.03                  │
│ 605 │ BLEU         │ 1            │ 0.93  │ 第2轮                            │
│ 606 │ 回答质量评估  │ 1            │ 4.7   │ 第2轮                            │
│ 607 │ WER          │ 2            │ 96.0  │ 第3轮(文本+音频): WER=0.04       │
│ 608 │ BLEU         │ 2            │ 0.90  │ 第3轮                            │
│ 609 │ 回答质量评估  │ 2            │ 4.5   │ 第3轮                            │
│ 610 │ WER          │ 3            │ 100.0 │ 第4轮: WER=0.00                  │
│ 611 │ BLEU         │ 3            │ 0.97  │ 第4轮                            │
│ 612 │ 回答质量评估  │ 3            │ 5.0   │ 第4轮                            │
│ 613 │ WER          │ NULL         │ 97.75 │ 整体评估: (98+97+96+100)/4        │
│ 614 │ BLEU         │ NULL         │ 0.938 │ 整体: (0.95+0.93+0.90+0.97)/4    │
│ 615 │ 回答质量评估  │ NULL         │ 4.78  │ 整体: (4.9+4.7+4.5+5.0)/4       │
└─────┴──────────────┴──────────────┴───────┴──────────────────────────────────┘
```

---

## 七、报告展示

### 7.1 单用例详情 (TestCaseReportDetail)

```
┌─ 用例详情：语音助手多轮对话-中文场景 ──────────────────────────────────┐
│                                                                      │
│  测试类型: API    算法: voice_llm    状态: 已完成                     │
│  会话 ID: a1b2c3d4-...    上下文模式: full    会话超时: 60s           │
│                                                                      │
│  ┌─ 聚合指标概览 ──────────────────────────────────────────────────┐ │
│  │  平均 WER: 0.0225   平均 BLEU: 0.938   平均 LLM 评分: 4.78     │ │
│  │  总延迟: 6.60s      总轮次: 4                                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌─ 多轮对话结果 (4 轮) ──────────────────────────────────────────┐ │
│  │                                                                  │ │
│  │  ▼ 第 1 轮 [文本]  延迟: 1.23s                                 │ │
│  │    输入: 你好，我想了解一下天气                                  │ │
│  │    输出: 今天北京天气晴朗，气温28°C，适合户外活动。              │ │
│  │    参考: 今天北京天气晴朗，气温28度，适合户外活动                │ │
│  │    WER: 0.02    BLEU: 0.95    LLM Judge: 4.9                    │ │
│  │    LLM 评语: 输出准确完整，表达自然流畅                          │ │
│  │    首 token: 0.3s   生成速度: 25 tok/s                           │ │
│  │                                                                  │ │
│  │  ▼ 第 2 轮 [文本·追问]  延迟: 1.87s                           │ │
│  │    输入: 那明天呢？                                              │ │
│  │    输出: 明天北京多云转晴，气温25°C，午后可能有短时阵雨。        │ │
│  │    WER: 0.03    BLEU: 0.93    LLM Judge: 4.7                    │ │
│  │    LLM 评语: 准确回答了追问，上下文理解正确                      │ │
│  │                                                                  │ │
│  │  ▼ 第 3 轮 [文本+音频]  延迟: 2.45s                            │ │
│  │    输入文本: 请听这段录音 (algorithmParams)                     │ │
│  │    输入音频: query3.wav (audios 用例默认参数)                   │ │
│  │    输出: 后天北京晴间多云，气温26到30度，适合出行。              │ │
│  │    WER: 0.04    BLEU: 0.90    LLM Judge: 4.5                    │ │
│  │    LLM 评语: ASR 识别准确，回答完整                              │ │
│  │                                                                  │ │
│  │  ▼ 第 4 轮 [文本·指令]  延迟: 1.05s                            │ │
│  │    输入: 帮我设个提醒，明天出门带伞                              │ │
│  │    输出: 好的，已为您设置提醒：明天出门请带伞。                  │ │
│  │    WER: 0.00    BLEU: 0.97    LLM Judge: 5.0                    │ │
│  │    LLM 评语: 指令执行准确，回复简洁明了                          │ │
│  │    首 token: 0.2s                                                │ │
│  │                                                                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌─ 整体维度评分 (TestResultDimension, round_number=NULL) ─────────┐ │
│  │  WER: 97.75 (weight=50)   BLEU: 0.938 (weight=30)              │ │
│  │  LLM Judge: 4.78 (weight=20)                                    │ │
│  │  加权总分: 97.75×0.5 + 93.8×0.3 + 47.8×0.2 = 86.58            │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  [对比视图]  [导出 Excel]  [重新评估]                                │
└──────────────────────────────────────────────────────────────────────┘
```

### 7.2 对比视图

```
┌─ 特定用例对比 ───────────────────────────────────────────────────────┐
│                                                                      │
│  用例名称                类型  WER     BLEU    LLM    总延迟  轮数   │
│  ─────────────────────  ────  ──────  ──────  ─────  ──────  ────  │
│  语音助手-中文场景       api   0.023   0.938   4.78   6.60s   4     │
│  语音助手-英文场景       api   0.035   0.910   4.50   7.20s   4     │
│  语音助手-中英混合       api   0.058   0.870   4.10   8.10s   3     │
│  智能音箱多轮-有噪       e2e   0.067   0.883   4.30   5.50s   3     │
│                                                                      │
│  * API 用例使用 total_latency，E2E 用例使用 avg_latency              │
│  * 多轮结果统一从 algorithm_result.aggregated 提取                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 八、API 与 E2E 关键差异对照

| 维度 | API 多轮用例 | E2E 多轮用例 |
|------|-------------|-------------|
| **物理设备** | 无，纯软件调用 | 有，需要播放设备+被测设备+导轨 |
| **音频播放** | 无 (文本/音频直接传给 API) | 有 (play_overlap + play_multi 混音) |
| **噪声/干扰人** | 无 | 有 (backgroundNoise 在 round 顶层，interferers 在 algorithmParams 中) |
| **导轨/音量** | 无 | 有 (algorithmParams 中 railDistance / volumeLevel) |
| **会话管理** | SessionContext (上下文历史) | 无 (每轮独立) |
| **中转服务** | api_adapter_service (8000) | 无 (直接控制设备) |
| **被测目标** | 云端 API (HTTP REST) | 物理设备 (ADB/HDC) |
| **超时策略** | session_timeout (固定 60s/轮) | 无 (play + 等待设备响应) |
| **输入方式** | algorithmParams 中 inputText/inputAudio (scope=api) + audios (音频) | audios (干声，设备播放) + algorithmParams (scope=e2e) |
| **结果来源** | API 响应 JSON | DeviceResultCollector 采集 |
| **参数驱动** | case_algorithm_params (scope=api+common) | case_algorithm_params (scope=e2e+common) |

---

## 九、完整数据流总结

```
前端 APITest.vue 5 步向导
  │
  ├─ Step 0: 选算法 → voice_llm
  ├─ Step 1: 选用例 → test_type='api' 过滤
  │    └─ CaseForm 编辑用例:
  │         加载 case_algorithm_params (scope=api+common) → DynamicForm (含 inputText)
  │         音频列表 → AudioConfigList (与 E2E 一致，API 模式简化)
  │         用户填写: rounds (4轮), algorithmParams (inputText), audios (音频)
  ├─ Step 2: 选被测API → ResourceSelectionGrid (algorithmType='voice_llm')
  │
  ▼
testcase_controller (CRUD)
  │  保存 API 用例记录 (id=201, test_type='api')
  │
  ▼
tasksApi.create → 创建任务 (含 apiIds: 选中的被测 API)
  │
  ▼
ExecutionEngine 调度 → APIExecutor.execute_api_case()
  │
  ├─ Phase 1: 初始化
  │    health_check → api_adapter_service
  │    case_config.rounds 非空 → 进入多轮会话
  │
  ├─ Phase 2: 创建会话
  │    SessionContext(session_id, context_mode='full', timeout=60s)
  │
  ├─ Phase 3: 多轮循环 (for round in rounds)
  │    │
  │    ├─ 读取输入参数
  │    │    algo_params = CaseParameterExtractor.convert_params_to_dict(round.algorithmParams)
  │    │    input_text = algo_params.get('inputText')  (算法特定参数)
  │    │    input_audio = round.audios[0].audio_id if audios else None  (用例默认参数)
  │    │
  │    ├─ 构建请求体
  │    │    context = session.get_context() (全量历史)
  │    │    vendor_config = { api_url, headers, timeout }
  │    │
  │    ├─ POST api_adapter_service /api/v1/tasks
  │    │    ├── SessionStore.get_context → 适配器侧上下文
  │    │    ├── HttpAdapter.send_request → POST 被测厂商 API
  │    │    ├── 被测 API 返回 { asr_text, trans_text, response }
  │    │    ├── SessionStore.add_round → 更新上下文
  │    │    └── 返回 { output_content, metrics }
  │    │
  │    ├─ session.add_history → 更新主后端上下文
  │    │
  │    └─ 单轮评估 (evaluation.enabled=true)
  │         → evaluation_service.evaluate_case(round_number=N)
  │           ├─ WER  → eval_server (wer_calculator)
  │           ├─ BLEU → eval_server (bleu_calculator)
  │           └─ LLM Judge → eval_server (llm_judge_calculator → GPT-4)
  │         → 回调写入 TestResultDimension (round_number=N)
  │
  ├─ Phase 4: 收尾
  │    _save_multi_round_results → algorithm_result = { rounds, session_id, total_latency }
  │    整体评估入队
  │    session.destroy()
  │
  └─ 评估聚合
       evaluation_result_processor.aggregate_round_results()
       → 按维度分组取平均 → algorithm_result.aggregated
       → 写入整体 TestResultDimension (round_number=NULL)
       → 标记任务完成
           │
           ▼
  报告展示 (TestCaseReportDetail)
    │  isMultiRound 检测 → 多轮视图
    │  聚合指标 + 每轮展开 (输入/输出/延迟/首token/LLM评语)
    │
    └─ 对比视图 (API vs API / API vs E2E 混合对比)
```
