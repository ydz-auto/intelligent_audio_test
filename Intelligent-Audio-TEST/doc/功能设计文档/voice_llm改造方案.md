# voice_llm 语音交互大模型测试改造方案

> 版本: v1.0 | 日期: 2026-06-05

---

## 目录

1. [概述](#1-概述)
2. [数据模型改造](#2-数据模型改造)
3. [前端改造](#3-前端改造)
4. [API 测试执行流程改造](#4-api-测试执行流程改造)
5. [E2E 测试执行流程改造](#5-e2e-测试执行流程改造)
6. [评估服务改造](#6-评估服务改造)
7. [数据迁移方案](#7-数据迁移方案)
8. [改动文件清单](#8-改动文件清单)

---

## 1. 概述

### 1.1 背景

在现有智能音频测试平台（Intelligent-Audio-TEST）基础上，新增 **voice_llm（语音交互大模型）** 算法类型的测试能力。

### 1.2 核心能力

| 能力 | 适用测试类型 | 说明 |
|------|-------------|------|
| 多轮交互 | API + E2E | N轮问答对话，每轮发送输入、获取响应 |
| 全双工交互 | E2E | 播放过程中可被中断（打断检测） |
| 评测维度 | API + E2E | WER/BLEU + LLM Judge（外部微服务） |
| 会话管理 | API | session_id + context_history 维护对话上下文 |
| 声纹注册 | E2E | 通过指定音箱播放注册音频完成声纹录入 |
| 干扰人播放 | E2E | 通过指定音箱播放干扰音频 |
| 导轨控制 | E2E | 控制被测设备与音箱的物理距离 |
| 单轮评估 | API + E2E | 可选，每轮交互结束后立即评估 |

### 1.3 架构原则

- **主后端是纯编排器**：只负责任务调度、状态管理、结果存储
- **评估计算外置**：所有评估（WER/BLEU/LLM Judge）由外部评估微服务完成，主后端通过异步任务协议（create_task → poll get_status → get_final_result）与之通信
- **双记录架构**：每个逻辑测试用例拆分为两条独立数据库记录（test_type='api' 和 test_type='e2e'），通过 related_case_id 关联

---

## 2. 数据模型改造

### 2.1 TestCase 模型扩展

**现有模型**（`backend/models/models.py:132`）：

```python
class TestCase(db.Model):
    id = Column(String(50), primary_key=True)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    config = Column(JSON)                    # 用例配置
    group_id = Column(String(50))
    algorithm_type = Column(String(50))      # 算法类型
    algorithm_params = Column(JSON)          # 算法参数
    reference_params = Column(JSON)          # 参考参数
```

**新增字段**：

```python
class TestCase(db.Model):
    # ... 现有字段不变 ...
    test_type = Column(String(10), nullable=False, default='api',
                       comment='测试类型: api / e2e')
    related_case_id = Column(String(50), nullable=True,
                             comment='关联的另一类型用例ID（API↔E2E互相关联）')
```

- `test_type`：区分此记录是 API 测试配置还是 E2E 测试配置
- `related_case_id`：指向对应的另一类型记录（API 记录指向其 E2E 记录，反之亦然）
- 旧数据全部迁移，不设 `test_type=null` 兼容逻辑

### 2.2 CaseAlgorithmParam 扩展

**现有模型**（`backend/models/algorithm_models.py`）：

```python
class CaseAlgorithmParam(db.Model):
    algorithm_type = Column(String(50))
    param_code = Column(String(100))
    param_name = Column(String(150))
    param_type = Column(String(30))    # input/textarea/input-number/select/slider/switch/code-editor
    default_value = Column(String(500))
    options_source = Column(String(200))
    ui_order = Column(Integer)
    # UniqueConstraint(algorithm_type, param_code)
```

**新增字段**：

```python
    scope = Column(String(10), nullable=False, default='common',
                   comment='参数适用范围: common / api / e2e')
```

- `common`：API 和 E2E 共用（如 overlap_rate）
- `api`：仅 API 测试显示（如 session_timeout）
- `e2e`：仅 E2E 测试显示（如 rail_distance）
- 前端 DynamicForm 根据当前 test_type 过滤：显示 `scope in (common, 当前test_type)` 的参数

### 2.3 Config 结构设计

双记录后，每条记录的 config 只存自己类型的数据，不再嵌套 api/e2e 子结构。

#### 2.3.1 API 测试用例 config

```jsonc
{
  // 音频配置 - API 只需 audioId 和播放顺序
  "audios": [
    { "audioId": "a001", "playOrder": 1 },
    { "audioId": "a002", "playOrder": 2 }
  ],

  // 评测维度
  "dimensions": [
    { "id": 1, "name": "WER", "weight": 0.6, "threshold": 0.1 },
    { "id": 2, "name": "LLM-Judge", "weight": 0.4, "threshold": 0.7 }
  ],

  // 多轮配置（voice_llm 专属）
  "rounds": [
    { "round": 1, "input_text": "今天天气怎么样", "input_audio_id": null },
    { "round": 2, "input_text": "明天呢", "input_audio_id": null }
  ],

  // 会话配置（voice_llm 专属）
  "session": {
    "session_timeout": 60,
    "context_mode": "full"   // full: 全量上下文, sliding_window: 滑动窗口
  }
}
```

#### 2.3.2 E2E 测试用例 config

```jsonc
{
  // 音频配置 - E2E 需要播放设备和声压级
  "audios": [
    {
      "audioId": "a001",
      "playbackDeviceId": "dev_01",
      "spl": 75,
      "playOrder": 1
    }
  ],

  // 背景噪音
  "backgroundNoise": {
    "audioId": "noise_001",
    "deviceIds": ["dev_03"],
    "spl": 60
  },

  // 声纹注册（voice_llm 专属）
  "voiceprintRegistration": {
    "enabled": true,
    "audioId": "vp_001",
    "playbackDeviceId": "dev_01",
    "spl": 75,
    "waitTime": 5            // 注册后等待时间（秒）
  },

  // 干扰人配置（voice_llm 专属）
  "interferers": [
    {
      "audioId": "interf_001",
      "playbackDeviceId": "dev_02",
      "spl": 65,
      "startDelay": 2,       // 开始延迟（秒），相对于被测音频播放开始
      "duration": 10         // 播放时长（秒），0=播完整个音频
    }
  ],

  // 多轮配置（voice_llm 专属）
  "rounds": [
    { "round": 1, "audioId": "a001", "waitTime": 10 },
    { "round": 2, "audioId": "a002", "waitTime": 10 }
  ],

  // 单轮评估开关
  "roundEvaluation": {
    "enabled": true,
    "dimensions": [
      { "id": 1, "name": "WER", "weight": 1.0, "threshold": 0.1 }
    ]
  },

  // 评测维度（整体）
  "dimensions": [
    { "id": 1, "name": "WER", "weight": 0.6, "threshold": 0.1 },
    { "id": 3, "name": "LLM-Judge", "weight": 0.4, "threshold": 0.7 }
  ]
}
```

### 2.4 algorithm_params 存储

`algorithm_params` 字段仍为 JSON，存储用户在用例编辑时填写的动态标量参数值：

```jsonc
{
  // 公共参数
  "overlap_rate": 0.5,

  // API 专属参数
  "session_timeout": 60,
  "max_rounds": 10,

  // E2E 专属参数
  "rail_distance": 50,
  "allow_interruption": true,
  "interruption_sensitivity": 0.7,
  "overlap_timeout": 3
}
```

前端根据 `CaseAlgorithmParam.scope` 和当前 `test_type` 过滤显示哪些参数。

### 2.5 reference_params 存储

`reference_params` 存储参考数据（参考文本、参考音频路径等），结构不变：

```json
{
  "reference_text": "今天天气晴朗",
  "reference_audio_path": "/data/ref/ref_001.wav"
}
```

### 2.6 新增 voice_llm 的 CaseAlgorithmParam 记录

为 `algorithm_type = 'voice_llm'` 新增以下参数定义：

| param_code | param_name | param_type | scope | default_value |
|------------|-----------|------------|-------|--------------|
| overlap_rate | 重叠率 | slider | common | 0.0 |
| session_timeout | 会话超时(秒) | input-number | api | 60 |
| max_rounds | 最大轮次数 | input-number | api | 10 |
| context_mode | 上下文模式 | select | api | full |
| rail_distance | 导轨距离(cm) | input-number | e2e | 50 |
| allow_interruption | 允许打断 | switch | e2e | false |
| interruption_sensitivity | 打断灵敏度 | slider | e2e | 0.5 |
| overlap_timeout | 重叠超时(秒) | input-number | e2e | 3 |
| voiceprint_wait_time | 声纹注册等待(秒) | input-number | e2e | 5 |

---

## 3. 前端改造

### 3.1 用例列表

**文件**: `frontend/src/components/common/test-case/`

- 列表显示 `test_type` 列（API / E2E 标签）
- 筛选条件增加 `test_type` 下拉（全部 / API / E2E）
- 新建用例时选择 `test_type`，创建一条记录
- 若 `related_case_id` 有值，列表行显示「关联用例」快捷跳转链接

### 3.2 用例编辑表单（CaseForm.vue）

**文件**: `frontend/src/components/common/test-case/TestCaseModal/CaseForm.vue` (1545行)

#### 3.2.1 现有逻辑变更

| 现有逻辑 | 改造为 |
|---------|--------|
| `hasAPIAudio` / `hasE2eAudio` 计算属性控制显隐 | 由 `test_type` 字段决定，不再按音频类型推断 |
| `config.dimensions.api` / `config.dimensions.e2e` 分两个子区域 | 单层 `config.dimensions` 数组，因为每条记录只有一种 test_type |
| `AudioConfig.testType` 字段区分音频用途 | 移除，因为记录本身已有 `test_type` |
| 背景噪音只在 `hasE2eAudio` 时显示 | 只在 `test_type === 'e2e'` 时显示 |

#### 3.2.2 新增表单区域（仅 voice_llm 算法类型 + 对应 test_type 时显示）

**API 测试表单新增**：

```
┌─────────────────────────────────────────┐
│ [基础信息] 名称/描述/分组/标签            │
│ [算法参数] DynamicForm 渲染 scope=common │
│            + scope=api 的参数            │
│ [音频配置] 音频卡片（仅 audioId+playOrder）│
│ [多轮配置] ← 新增                       │
│   轮次列表，可增删排序                     │
│   每轮: 文本输入 or 音频选择               │
│ [会话配置] ← 新增                       │
│   超时时间、上下文模式                     │
│ [评测维度] 维度卡片列表                   │
│ [参考参数] reference_params              │
└─────────────────────────────────────────┘
```

**E2E 测试表单新增**：

```
┌─────────────────────────────────────────┐
│ [基础信息] 名称/描述/分组/标签            │
│ [算法参数] DynamicForm 渲染 scope=common │
│            + scope=e2e 的参数            │
│ [声纹注册] ← 新增                       │
│   开关 + 音频选择 + 音箱选择 + SPL + 等待 │
│ [音频配置] 音频卡片(含播放设备+SPL)       │
│ [背景噪音] 噪音音频 + 设备 + SPL         │
│ [干扰人] ← 新增                         │
│   列表，可增删                           │
│   每人: 音频选择 + 音箱选择 + SPL + 延迟  │
│ [多轮配置] ← 新增                       │
│   轮次列表，可增删排序                     │
│   每轮: 音频选择 + 等待响应时间           │
│ [单轮评估] ← 新增                       │
│   开关 + 评估维度选择                     │
│ [评测维度] 维度卡片列表（整体评估）       │
│ [参考参数] reference_params              │
└─────────────────────────────────────────┘
```

### 3.3 类型定义改造

**文件**: `frontend/src/components/common/test-case/TestCaseModal/types.ts`

```typescript
// 新增
export interface RoundConfig {
  round: number;
  // API 轮次
  input_text?: string;
  input_audio_id?: string | null;
  // E2E 轮次
  audioId?: string;
  waitTime?: number;       // 等待响应时间（秒）
}

export interface VoiceprintConfig {
  enabled: boolean;
  audioId: string;
  playbackDeviceId: string;
  spl: number;
  waitTime: number;
}

export interface InterfererConfig {
  audioId: string;
  playbackDeviceId: string;
  spl: number;
  startDelay: number;
  duration: number;
}

export interface SessionConfig {
  session_timeout: number;
  context_mode: 'full' | 'sliding_window';
}

export interface RoundEvaluationConfig {
  enabled: boolean;
  dimensions: DimensionConfig[];
}

// 修改 TestCaseFormData
export interface TestCaseFormData {
  // ... 现有基础字段不变 ...
  test_type: 'api' | 'e2e';           // 新增
  related_case_id?: string;            // 新增
  config: {
    audios: AudioConfig[];
    dimensions: DimensionConfig[];     // 改为扁平数组（不再是 {api, e2e}）
    backgroundNoise?: BackgroundNoiseConfig;
    // voice_llm 新增
    rounds?: RoundConfig[];
    session?: SessionConfig;
    voiceprintRegistration?: VoiceprintConfig;
    interferers?: InterfererConfig[];
    roundEvaluation?: RoundEvaluationConfig;
  };
}

// 修改 AudioConfig（移除 testType）
export interface AudioConfig {
  audioId: string;
  playbackDeviceId?: string;   // E2E 才有
  spl?: number;                // E2E 才有
  playOrder: number;
}
```

### 3.4 五步流程（测试任务创建向导）

**不需要改动**。五步流程为：

1. 选择算法 → 自动发现 voice_llm
2. 选择 API → 按算法类型筛选
3. 选择测试用例 → 按 `test_type` 和 `algorithm_type` 筛选
4. 选择设备 → 不变
5. 确认执行 → 不变

---

## 4. API 测试执行流程改造

### 4.1 现有流程（线性单轮）

**文件**: `backend/utils/api_executor.py` (1770行)

```
execute_api_case()
  └── _validate_and_get_data()          # 验证+取数据（含 test_type 过滤音频）
      └── for api_config in api_configs: # 遍历每个 API
          ├── acquire_api_execution_right()
          ├── _setup_api_endpoints()
          ├── _health_check()
          ├── _create_task()             # 上传音频 → api_task_id
          ├── _wait_for_task_completion()# 轮询等待
          ├── _get_final_result()
          ├── _extract_final_result()    # field_mapper 提取
          ├── _create_test_result()      # 存 DB
          ├── _delete_task()             # 释放远程资源
          ├── _evaluate_result()         # 异步评估入队
          └── release_api_execution_right()
```

### 4.2 voice_llm API 新流程（多轮会话）

```
execute_api_case()
  └── _validate_and_get_data()          # 不再按 test_type 过滤音频（双记录后天然隔离）
      └── for api_config in api_configs:
          ├── acquire_api_execution_right()
          ├── _setup_api_endpoints()
          ├── _health_check()
          │
          ├── # ===== 多轮会话循环（voice_llm 新增） =====
          │   ├── _create_session()              # 创建会话 → session_id
          │   │
          │   └── for round in config.rounds:    # 遍历每个轮次
          │       ├── _send_round_request()       # 发送本轮输入（文本/音频 + session_id + context）
          │       ├── _wait_for_round_response()  # 等待本轮响应（独立超时）
          │       ├── _extract_round_result()     # 提取本轮结果
          │       ├── session.add_history()       # 更新上下文历史
          │       │
          │       └── if roundEvaluation.enabled:
          │           └── _evaluate_round()       # 单轮评估（可选）
          │
          │   ├── _aggregate_round_results()     # 汇总所有轮次结果
          │   └── _destroy_session()             # 销毁会话
          │
          ├── _create_test_result()       # 存 DB（包含 rounds 数组）
          ├── _evaluate_result()          # 整体评估入队
          └── release_api_execution_right()
```

### 4.3 关键新增模块

#### 4.3.1 会话管理器

```python
class SessionContext:
    """voice_llm 多轮会话上下文"""
    def __init__(self, session_id, config):
        self.session_id = session_id
        self.session_timeout = config.get('session_timeout', 60)
        self.context_mode = config.get('context_mode', 'full')
        self.context_history = []    # [(input, output), ...]
        self.round_results = []      # [RoundResult, ...]
    
    def add_history(self, input_data, output_data):
        self.context_history.append((input_data, output_data))
    
    def get_context(self):
        """根据 context_mode 返回上下文"""
        if self.context_mode == 'full':
            return self.context_history
        # sliding_window: 只返回最近N轮
        window_size = 5
        return self.context_history[-window_size:]
```

#### 4.3.2 轮次请求构建

现有 `_create_task()` 构建的是「上传音频文件」请求。voice_llm 需要构建「对话请求」：

```python
def _send_round_request(self, task_id, session, round_config, api_config, ...):
    """发送单轮对话请求"""
    request_data = {
        "session_id": session.session_id,
        "round": round_config['round'],
        "input": {
            "text": round_config.get('input_text'),
            "audio_path": round_config.get('input_audio_path'),  # 二选一
        },
        "context": session.get_context(),  # 历史上下文
    }
    # 通过 APIDriver 发送请求
    driver = APIDriver(api_config, api_specific_config, endpoint=chat_url)
    return driver.execute(request_data)
```

#### 4.3.3 轮次超时策略

现有超时基于 `audio_duration * 1.5`（[api_executor.py:727](../backend/utils/api_executor.py:727)），voice_llm 改为：

```python
# 单轮超时：配置的 session_timeout（默认60秒）
round_timeout = session_config.get('session_timeout', 60)

# 总会话超时：round_timeout * 轮次数 * 1.5
total_timeout = round_timeout * len(rounds) * 1.5
```

#### 4.3.4 结果存储结构

单条 TestResult 包含所有轮次：

```jsonc
// TestResult.algorithm_result
{
  "session_id": "sess_abc123",
  "rounds": [
    {
      "round": 1,
      "input": "今天天气怎么样",
      "output": "今天天气晴朗，气温25度",
      "latency": 1200,
      "round_evaluation": { "WER": 0.05 }   // 可选
    },
    {
      "round": 2,
      "input": "明天呢",
      "output": "明天多云转晴，气温22度",
      "latency": 800,
      "round_evaluation": { "WER": 0.08 }
    }
  ],
  "total_latency": 2000,
  "round_count": 2
}
```

### 4.4 现有模块复用度

| 模块 | 复用度 | 说明 |
|------|--------|------|
| 信号量并发控制 | 100% | `acquire_api_execution_right` / `release` 不变 |
| API 端点管理+负载均衡 | 100% | `_setup_api_endpoints` 不变 |
| 健康检查 | 90% | 音频文件检查需要条件化（voice_llm 可能纯文本输入） |
| APIDriver HTTP 执行 | 100% | 底层 HTTP客户端不变 |
| field_mapper 动态字段 | 80% | 扩展支持 voice_llm 字段映射 |
| 评估服务调度 | 90% | 评估维度不同，调度机制不变 |
| 测试结果存储 | 80% | `algorithm_result` 结构扩展 |

### 4.5 需要删除的代码

| 位置 | 说明 |
|------|------|
| `api_executor.py:325-332` | `test_type` 过滤音频逻辑 — 双记录后不需要，每条记录的 audios 天然是单一类型 |

---

## 5. E2E 测试执行流程改造

### 5.1 现有流程（线性单次）

**文件**: `backend/utils/e2e_executor.py`

```
execute_e2e_case()
  ├── _validate_and_get_data()          # 验证+取数据
  ├── prepare_audio_playback_info()     # 准备音频播放信息
  ├── _get_device_info()               # 获取测试设备
  ├── _initialize_devices()            # 初始化设备
  ├── _execute_audio_playback()        # 播放全部音频（一次性）
  ├── _post_process_devices()          # 设备后处理
  ├── sleep(3s)                        # 等待结果生成
  ├── _collect_results()               # 从所有设备收集结果
  └── _process_results()               # 处理结果 + 评估
```

### 5.2 voice_llm E2E 新流程（多轮循环 + 硬件控制）

```
execute_e2e_case()
  ├── _validate_and_get_data()           # 不再按 test_type 过滤（双记录天然隔离）
  ├── _get_device_info()                 # 获取测试设备
  ├── _initialize_devices()              # 初始化设备
  │
  ├── # ===== 硬件准备阶段（voice_llm 新增） =====
  │   ├── _control_rail()                # 导轨控制：调整设备到目标距离
  │   └── _register_voiceprint()         # 声纹注册：播放注册音频 + 等待
  │       ├── 选择播放设备
  │       ├── 播放声纹注册音频
  │       └── sleep(waitTime)            # 等待声纹注册完成
  │
  ├── # ===== 多轮交互循环（voice_llm 新增） =====
  │   └── for round in config.rounds:    # 遍历每个轮次
  │       │
  │       ├── _execute_round_playback()  # 播放本轮音频
  │       │   └── _play_interferers()    # 同时播放干扰人音频（如有）
  │       │       └── 考虑 startDelay 和 duration
  │       │
  │       ├── _wait_for_response()       # 等待被测设备响应
  │       │   └── timeout = round.waitTime
  │       │
  │       ├── _collect_round_results()   # 收集本轮结果
  │       │   └── 从所有采集设备收集
  │       │
  │       ├── if roundEvaluation.enabled:
  │       │   └── _evaluate_round()      # 单轮评估（可选）
  │       │
  │       └── # 全双工场景：检测打断事件
  │           └── _detect_interruption() # 如 allow_interruption=true
  │
  ├── _post_process_devices()            # 设备后处理
  │
  ├── # ===== 导轨复位（voice_llm 新增） =====
  │   └── _reset_rail()                  # 导轨回到初始位置
  │
  ├── _aggregate_round_results()         # 汇总所有轮次结果
  └── _process_results()                 # 整体处理 + 评估
```

### 5.3 与现有流程的详细对比

| 步骤 | 现有 E2E 流程 | voice_llm E2E 流程 | 差异 |
|------|-------------|-------------------|------|
| 数据验证 | `_validate_and_get_data()` 含 test_type 过滤 | 去掉 test_type 过滤 | 删除过滤代码 |
| 音频准备 | `prepare_audio_playback_info()` 一次性准备所有 | 按轮次分批准备 | 改造 |
| 设备初始化 | `_initialize_devices()` | 不变 | 无 |
| **导轨控制** | 无 | `_control_rail(distance)` | **新增** |
| **声纹注册** | 无 | 播放注册音频 + 等待 | **新增** |
| 音频播放 | `_execute_audio_playback()` 一次播完 | 按轮次分次播放 | **大改** |
| **干扰人** | 无 | 与本轮音频同时播放 | **新增** |
| **全双工打断检测** | 无 | 播放过程中监听打断事件 | **新增** |
| 结果收集 | `_collect_results()` 一次性收集 | 每轮单独收集 | **大改** |
| **单轮评估** | 无 | 可选每轮评估 | **新增** |
| 等待 | `sleep(3s)` 固定等待 | 每轮有独立 waitTime | 改造 |
| 结果处理 | `_process_results()` 一次处理 | 汇总多轮 + 整体处理 | 改造 |
| **导轨复位** | 无 | 测试结束后复位 | **新增** |

### 5.4 关键新增模块

#### 5.4.1 导轨控制模块

```python
class RailController:
    """自动化导轨控制"""
    
    def __init__(self, rail_config):
        self.rail_config = rail_config
    
    def move_to_distance(self, distance_cm, task_id):
        """移动导轨到指定距离"""
        # 通过设备驱动发送指令
        pass
    
    def reset(self, task_id):
        """导轨回到初始位置"""
        self.move_to_distance(0, task_id)
```

- 导轨距离来自 `algorithm_params.rail_distance`
- 导轨控制通过现有 `device_driver_factory` 框架扩展
- 需要新增导轨设备驱动类型

#### 5.4.2 声纹注册模块

```python
def _register_voiceprint(self, task_id, voiceprint_config, device_info_list):
    """执行声纹注册"""
    if not voiceprint_config.get('enabled'):
        return True
    
    audio_id = voiceprint_config['audioId']
    playback_device_id = voiceprint_config['playbackDeviceId']
    spl = voiceprint_config['spl']
    wait_time = voiceprint_config.get('waitTime', 5)
    
    # 1. 获取注册音频文件路径
    audio = db.session().query(Audio).get(audio_id)
    
    # 2. 获取播放设备
    playback_device = db.session().query(PlaybackDevice).get(playback_device_id)
    
    # 3. 通过 audio_service 播放注册音频
    audio_service.play_audio(
        file_path=audio.file_path,
        device_id=playback_device.device_unique_id,
        spl=spl
    )
    
    # 4. 等待声纹注册完成
    time.sleep(wait_time)
    
    self._log('INFO', f"声纹注册完成，等待了{wait_time}秒", task_id)
    return True
```

声纹注册复用现有组件：
- `Audio` 模型获取音频文件
- `PlaybackDevice` 模型获取播放设备
- `audio_service` 执行播放
- `spl_service` 校准声压级

#### 5.4.3 干扰人播放模块

```python
def _play_interferers(self, task_id, interferers, dry_devices):
    """播放干扰人音频"""
    threads = []
    for interferer in interferers:
        audio_id = interferer['audioId']
        device_id = interferer['playbackDeviceId']
        spl = interferer['spl']
        start_delay = interferer.get('startDelay', 0)
        duration = interferer.get('duration', 0)
        
        t = threading.Thread(
            target=self._play_single_interferer,
            args=(task_id, audio_id, device_id, spl, start_delay, duration)
        )
        threads.append(t)
        t.start()
    
    return threads

def _play_single_interferer(self, task_id, audio_id, device_id, spl, start_delay, duration):
    """播放单个干扰人"""
    time.sleep(start_delay)
    audio = db.session().query(Audio).get(audio_id)
    device = db.session().query(PlaybackDevice).get(device_id)
    audio_service.play_audio(
        file_path=audio.file_path,
        device_id=device.device_unique_id,
        spl=spl,
        duration=duration  # 0=播完
    )
```

#### 5.4.4 多轮播放与收集

```python
def _execute_multi_round(self, task_id, rounds, config, device_info_list, ...):
    """多轮交互执行主循环"""
    all_round_results = []
    
    for round_config in rounds:
        self._handle_control(task_id)
        round_num = round_config['round']
        
        # 1. 播放本轮音频（含干扰人）
        self._execute_round_playback(
            task_id, round_config, dry_devices, noise_devices, ...
        )
        
        # 2. 等待被测设备响应
        wait_time = round_config.get('waitTime', 10)
        self._log('INFO', f"第{round_num}轮：等待响应 {wait_time}秒", task_id)
        time.sleep(wait_time)
        
        # 3. 收集本轮结果
        round_results = self._collect_round_results(
            task_id, round_num, device_info_list, ...
        )
        
        # 4. 可选：单轮评估
        if config.get('roundEvaluation', {}).get('enabled'):
            self._evaluate_round(task_id, round_num, round_results, ...)
        
        all_round_results.append({
            'round': round_num,
            'results': round_results
        })
    
    return all_round_results
```

#### 5.4.5 全双工打断检测

```python
def _detect_interruption(self, task_id, device_info_list, allow_interruption, sensitivity):
    """检测全双工打断事件"""
    if not allow_interruption:
        return None
    
    # 在播放过程中持续监测
    # 通过设备驱动检测音频打断事件
    # 记录打断时间点、持续时长
    interruption_events = []
    for info in device_info_list:
        driver = info.get('driver')
        if driver and hasattr(driver, 'detect_interruption'):
            events = driver.detect_interruption(sensitivity=sensitivity)
            interruption_events.extend(events)
    
    return interruption_events
```

### 5.5 结果存储结构

```jsonc
// TestResult.algorithm_result（E2E 多轮）
{
  "rounds": [
    {
      "round": 1,
      "device_results": {
        "device_001": {
          "asr_text": "今天天气晴朗",
          "wer": 0.05,
          "latency": 2300
        }
      },
      "interruption_events": [],          // 全双工打断事件
      "round_evaluation": { "WER": 0.05 } // 可选单轮评估
    },
    {
      "round": 2,
      "device_results": { "device_001": { "asr_text": "明天多云", "latency": 1800 } },
      "round_evaluation": { "WER": 0.08 }
    }
  ],
  "rail_distance": 50,
  "voiceprint_registered": true,
  "interferer_count": 1,
  "total_rounds": 2
}
```

### 5.6 现有模块复用度

| 模块 | 复用度 | 说明 |
|------|--------|------|
| 设备初始化 | 100% | `_initialize_devices()` 不变 |
| 设备驱动框架 | 80% | 扩展导轨驱动 + 打断检测接口 |
| 音频播放引擎 | 70% | 从一次性播放改为按轮次分次播放 |
| SPL 校准服务 | 100% | `spl_service` 不变，干扰人和声纹注册也用 |
| 结果收集器 | 70% | 从一次收集改为每轮收集 |
| 结果处理器 | 60% | 增加轮次汇总逻辑 |
| 评估服务调度 | 90% | 增加单轮评估入口 |
| 设备后处理 | 100% | `_post_process_devices()` 不变 |

### 5.7 需要删除的代码

| 位置 | 说明 |
|------|------|
| `e2e_executor.py:105` | `test_type == 'e2e'` 过滤音频逻辑 — 双记录后不需要 |

---

## 6. 评估服务改造

### 6.1 评估架构（不变）

主后端仍为**纯编排器**，评估计算由外部微服务完成：

```
api_executor / e2e_executor
  → evaluation_service.evaluate_case()     # 入队
    → EndpointWorker                        # 按维度分组
      → evaluation_api_client               # HTTP 调用外部微服务
        → create_task → poll → get_result   # 异步任务协议
```

### 6.2 LLM Judge 评估维度

LLM Judge 作为一种新的评估维度，其计算**完全在外部评估微服务中完成**。主后端只需：

1. **维度配置**：在前端评测维度管理中，新增 `type='llm_judge'` 的维度类型
2. **任务分发**：`evaluation_service` 将 `llm_judge` 类型的维度分发到对应的评估微服务 endpoint
3. **结果收集**：从微服务返回的结果中提取分数，存入 `EvaluationResult`

**主后端不集成 GPT/Claude SDK**，不管理 prompt 模板，不调用 LLM API。

### 6.3 评估微服务需要实现的接口（外部团队）

外部评估微服务需要为 `voice_llm` 新增：

| 接口 | 说明 |
|------|------|
| `POST /api/create_task` | 接收评估任务，包含多轮对话历史、参考文本、评估维度 |
| `GET /api/get_status/{task_id}` | 查询评估进度 |
| `GET /api/get_final_result/{task_id}` | 获取评估结果（WER/BLEU/LLM Judge 分数） |

LLM Judge 评估请求示例：

```json
{
  "task_type": "evaluation",
  "algorithm_type": "voice_llm",
  "dimensions": ["WER", "BLEU", "LLM_Judge"],
  "rounds": [
    { "input": "今天天气怎么样", "output": "今天晴朗", "reference": "今天天气晴朗" },
    { "input": "明天呢", "output": "明天多云", "reference": "明天多云转晴" }
  ],
  "llm_judge_config": {
    "model": "gpt-4",
    "criteria": ["准确性", "流畅性", "上下文一致性"]
  }
}
```

### 6.4 单轮评估

单轮评估复用现有的 `evaluation_service.evaluate_case()` 机制，传入 `round_number` 参数：

```python
# 单轮评估入队
self._evaluate_result(
    task_id=task_id,
    result_id=round_result_id,
    test_case_id=test_case_id,
    algo_result=round_algo_result,
    case_config=round_eval_dimensions_config,  # 单轮评估维度
    algorithm_type=algorithm_type,
    test_type='e2e',
    round_number=1  # 新增参数，标识这是第几轮
)
```

---

## 7. 数据迁移方案

### 7.1 迁移策略

**全量迁移，不做向后兼容**。迁移完成后：
- 所有 `test_cases` 记录都有 `test_type` 值（'api' 或 'e2e'）
- 不存在 `test_type = null` 的记录
- 代码中不需要写 `test_type is null` 的兜底逻辑

### 7.2 迁移脚本

```sql
-- Step 1: 添加新字段
ALTER TABLE test_cases ADD COLUMN test_type VARCHAR(10) DEFAULT NULL;
ALTER TABLE test_cases ADD COLUMN related_case_id VARCHAR(50) DEFAULT NULL;
ALTER TABLE case_algorithm_params ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'common';

-- Step 2: 拆分现有记录
-- 对于每条现有记录，生成两条新记录（API + E2E）
-- 具体逻辑在 Python 迁移脚本中实现，因为需要处理 JSON config 拆分

-- Step 3: 更新关联
-- 将 related_case_id 互相指向

-- Step 4: 删除旧记录（或标记 deleted=true）

-- Step 5: 清理
-- 移除 config.dimensions.api / config.dimensions.e2e 嵌套结构
-- 改为扁平 config.dimensions 数组
```

### 7.3 Python 迁移脚本伪代码

```python
def migrate_test_cases():
    """将现有 TestCase 拆分为 API + E2E 双记录"""
    old_cases = TestCase.query.filter(TestCase.test_type.is_(None)).all()
    
    for old_case in old_cases:
        old_config = old_case.config or {}
        
        # 提取 API 音频和 E2E 音频
        api_audios = [a for a in old_config.get('audios', []) if a.get('test_type') == 'api']
        e2e_audios = [a for a in old_config.get('audios', []) if a.get('test_type') == 'e2e']
        
        # 提取 API 维度和 E2E 维度
        api_dims = old_config.get('dimensions', {}).get('api', [])
        e2e_dims = old_config.get('dimensions', {}).get('e2e', [])
        
        # 创建 API 记录
        api_case = TestCase(
            id=generate_id(),
            name=old_case.name + ' (API)',
            test_type='api',
            algorithm_type=old_case.algorithm_type,
            config={
                'audios': [{k: v for k, v in a.items() if k != 'test_type'} for a in api_audios],
                'dimensions': api_dims,
            },
            algorithm_params=old_case.algorithm_params,
            reference_params=old_case.reference_params,
            group_id=old_case.group_id,
        )
        
        # 创建 E2E 记录
        e2e_case = TestCase(
            id=generate_id(),
            name=old_case.name + ' (E2E)',
            test_type='e2e',
            algorithm_type=old_case.algorithm_type,
            config={
                'audios': [{k: v for k, v in a.items() if k != 'test_type'} for a in e2e_audios],
                'dimensions': e2e_dims,
                'backgroundNoise': old_config.get('backgroundNoise'),
            },
            algorithm_params=old_case.algorithm_params,
            reference_params=old_case.reference_params,
            group_id=old_case.group_id,
        )
        
        # 互相关联
        api_case.related_case_id = e2e_case.id
        e2e_case.related_case_id = api_case.id
        
        db.session.add(api_case)
        db.session.add(e2e_case)
        
        # 标记旧记录为已删除
        old_case.deleted = True
    
    db.session.commit()
```

### 7.4 迁移涉及的关联表

| 表 | 处理方式 |
|---|---------|
| `test_case_tags` | 复制关联到新记录 |
| `test_case_groups` | 新记录继承原 group_id |
| `task_case_relations` | 历史任务关联保持不变（指向旧记录ID） |
| `test_results` | 历史结果保持不变 |

---

## 8. 改动文件清单

### 8.1 后端

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/models/models.py` | 修改 | TestCase 新增 test_type, related_case_id 字段 |
| `backend/models/algorithm_models.py` | 修改 | CaseAlgorithmParam 新增 scope 字段 |
| `backend/schemas/testcase.py` | 修改 | 新增 voice_llm 相关 schema（RoundConfig 等） |
| `backend/utils/api_executor.py` | **大改** | 新增多轮会话循环、会话管理、轮次结果聚合；删除 test_type 过滤 |
| `backend/utils/e2e_executor.py` | **大改** | 新增多轮循环、声纹注册、干扰人、导轨控制、单轮评估；删除 test_type 过滤 |
| `backend/utils/base_executor.py` | 修改 | 评估入队方法支持 round_number 参数 |
| `backend/utils/evaluation_service.py` | 修改 | 支持 llm_judge 维度分发、单轮评估 |
| `backend/algorithm/field_mapper.py` | 修改 | 新增 voice_llm 字段映射 |
| `backend/algorithm/case_parameter_extractor.py` | 修改 | 支持 voice_llm 评估参数提取 |
| `backend/controllers/testcase_controller.py` | 修改 | 创建/更新用例时处理 test_type + related_case_id |
| `backend/device_driver/` | 新增 | 新增导轨控制器 rail_controller.py |
| `migrations/` | 新增 | 数据库迁移脚本 |

### 8.2 前端

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `frontend/src/components/common/test-case/TestCaseModal/types.ts` | 修改 | 新增 RoundConfig, VoiceprintConfig, InterfererConfig, SessionConfig 等类型；AudioConfig 移除 testType |
| `frontend/src/components/common/test-case/TestCaseModal/CaseForm.vue` | **大改** | 新增多轮配置、声纹注册、干扰人、会话配置等表单区域；test_type 驱动显隐 |
| `frontend/src/components/common/test-case/TestCaseList.vue` | 修改 | 列表显示 test_type 标签；筛选增加 test_type |
| `frontend/src/components/common/test-case/TestCaseCreateModal.vue` | 修改 | 新建时选择 test_type |

### 8.3 不变的部分

| 模块 | 说明 |
|------|------|
| 五步向导流程 | 算法自动发现 + test_type 筛选，无需改动 |
| APIDriver | 底层 HTTP 客户端不变 |
| 评估微服务协议 | create_task → poll → get_result 协议不变 |
| spl_service | 声压级校准不变 |
| audio_service | 音频播放引擎不变（E2E 多轮是在 executor 层分次调用） |
| 设备驱动框架 | device_driver_factory 框架不变，只扩展新的导轨驱动 |
| 日志系统 | 不变 |
| WebSocket 进度推送 | 不变 |
