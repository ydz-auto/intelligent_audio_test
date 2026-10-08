# Evaluation - 评估维度适配方案

## 1. 页面概述

### 1.1 页面定位
Evaluation 页面用于管理评估维度，需要适配算法配置化方案，支持评估维度与算法的多对多关联。

### 1.2 页面路由
- 路由路径：`/Evaluation`
- 菜单位置：系统设置 > 评估维度

### 1.3 核心改动
- 评估维度增加算法关联配置（**新增字段，不改变现有结构**）
- 支持一个评估维度关联多个算法
- 支持一个算法使用多个评估维度

---

## 2. 评估维度与算法关系

### 2.1 多对多关系模型

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    评估维度与算法关联模型                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  一个评估维度可以关联多个算法:                                            │
│                                                                          │
│  BLEU 评分 ──────────┬── 翻译                                           │
│                      ├── ASR (作为参考指标)                              │
│                      └── TTS                                             │
│                                                                          │
│  WER 错误率 ─────────┼── ASR                                            │
│                                                                          │
│  说话人准确率 ────────┼── 声纹识别                                        │
│                                                                          │
│  一个算法可以使用多个评估维度:                                            │
│                                                                          │
│  翻译 ────────────────┼── BLEU 评分                                      │
│                       ├── ROUGE 评分                                     │
│                       └── TER 错误率                                     │
│                                                                          │
│  ASR ────────────────┼── WER 错误率                                      │
│                       ├── CER 错误率                                     │
│                       └── BLEU 评分 (作为参考)                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 页面布局（基于现有实现最小化改动）

### 3.1 列表页改动

**现有布局：**
```
┌─────────────────────────────────────────────────────────────────────────┐
│  评估维度管理                                                            │
├─────────────────────────────────────────────────────────────────────────┤
│  [+ 新增维度]  [批量操作 ▼]  [导入/导出 ▼]                                │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ ☐ │ 维度名称 │ 描述 │ 分类 │ 权重 │ API状态 │ 状态 │ 操作          │ │
│  ├────────────────────────────────────────────────────────────────────┤ │
│  │ ☐ │ BLEU评分 │ ...  │ 性能 │  5   │ 在线    │ 启用 │ [编辑][删除] │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

**适配后布局（新增"关联算法"列）：**
```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  评估维度管理                                                                         │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  [+ 新增维度]  [批量操作 ▼]  [导入/导出 ▼]                                             │
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐ │
│  │ ☐ │ 维度名称 │ 描述 │ 分类 │ 关联算法      │ 权重 │ API状态 │ 状态 │ 操作       │ │
│  ├─────────────────────────────────────────────────────────────────────────────────┤ │
│  │ ☐ │ BLEU评分 │ ...  │ 性能 │ [翻译][ASR]   │  5   │ 在线    │ 启用 │ [编辑]... │ │
│  │ ☐ │ WER错误率│ ...  │ 性能 │ [ASR]         │  5   │ 在线    │ 启用 │ [编辑]... │ │
│  └─────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 编辑表单改动

**在现有表单字段基础上，新增"关联算法"选择器：**

```
┌─────────────────────────────────────────────────────────────────┐
│  编辑评估维度                                                    │
├─────────────────────────────────────────────────────────────────┤
│  维度名称: [____________]                                        │
│  关键词:   [____________]                                        │
│  描述:     [____________]                                        │
│  所属分类: [性能指标 ▼]                                          │
│  评估类型: [自动评估 ▼]  ← 保持现有字段                          │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 关联算法（新增）                                            ││
│  │ ┌───────┐ ┌───────┐ ┌───────────┐                         ││
│  │ │ 翻译  │ │  ASR  │ │ 说话人识别 │  [+ 添加算法]           ││
│  │ └───────┘ └───────┘ └───────────┘                         ││
│  │ (多选标签，点击可移除)                                      ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Master入口URL: [____________]                                   │
│  API端点配置: [...]                                              │
│  分数单位: [____________]                                        │
│  API设置: [JSON编辑器]                                           │
│  结果类型: [数值 ▼]                                              │
│  权重: [滑块 1-10]                                               │
│  评分规则: [JSON编辑器]                                          │
│  状态: [开关]                                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据结构（基于现有模型扩展）

### 4.1 现有 Dimension 模型字段

> **注**：以下为 `backend/models/models.py` 中 Dimension 模型的实际字段定义（已实施）。

```python
class Dimension(db.Model):
    __tablename__ = 'dimensions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    keywords = Column(String(255))
    dimension_type = Column(String(20), default='main')  # 'main' | 'sub'
    parent_dimension_id = Column(Integer, ForeignKey('dimensions.id'))  # 主维度ID
    task_type_code = Column(String(50))  # API调用的task_type值（如 wer）
    description = Column(Text)
    category_id = Column(Integer, ForeignKey('categories.id'))
    type = Column(String(50), nullable=False)  # 'auto' | 'manual'
    result_type = Column(Integer, nullable=False)  # 1:数值, 2:布尔, 3:文本
    result_min = Column(Float)
    result_max = Column(Float)
    decimal_places = Column(Integer)
    weight = Column(Integer, nullable=False, default=1)
    estimated_exec_time = Column(Integer, nullable=False, default=10)
    rule = Column(JSON, nullable=True, default=dict)
    api_settings = Column(JSON)
    api_endpoints = Column(JSON, nullable=True, default=list)
    api_url = Column(String(512))
    api_status = Column(String(20), nullable=False, default='online')
    score_unit = Column(String(50), nullable=True, default='')
    statistic_method = Column(String(30), nullable=False, default='average')
    # 统计方式: average(简单平均), weighted_wer(加权WER: Σ分子/Σ分母), pass_rate(达标率)
    status = Column(Boolean, nullable=False, default=True)
    deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

> **重要**：Dimension 表**不包含** `required_inputs`、`associated_algorithms` JSON 列，也不包含 `aggregation_mode`/`group_by` 字段。所需输入/输出字段由 `EvaluationDimensionParam` 表定义（见第 6 节），关联算法由 `AlgorithmDimensionRelation` 关联表管理（见 §4.3），统计方式由 `statistic_method` 字段驱动（见第 8 节）。

### 4.2 参数定义与关联算法的存储方式

```python
# 所需输入(required_inputs)与输出字段(output_fields)不再作为 Dimension 的 JSON 字段，
# 统一由 EvaluationDimensionParam 表定义，按 param_direction='input'/'output' 区分，
# 后端在查询维度详情时动态派生为 required_inputs / output_fields 视图
# 详见 algorithm_models.py 中的 EvaluationDimensionParam 模型（第 6 节）

# 评估维度与算法的关联通过 AlgorithmDimensionRelation 表管理，不再使用 JSON 字段
# 详见 algorithm_models.py 中的 AlgorithmDimensionRelation 模型（§4.3）
```

### 4.3 数据模型关系

```python
# algorithm_models.py 中的关键模型

class AlgorithmDimensionRelation(db.Model):
    """评估维度与算法关联表"""
    __tablename__ = 'algorithm_dimension_relations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False)
    dimension_id = Column(Integer, ForeignKey('dimensions.id', ondelete='CASCADE'), nullable=False)
    is_default = Column(Boolean, default=False)  # 是否默认评估维度
    weight = Column(Float, default=1.0)  # 权重
    deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 唯一索引：同一算法+维度（未删除记录）不允许重复关联
    __table_args__ = (
        Index('uq_algorithm_dimension', 'algorithm_type', 'dimension_id',
              unique=True, postgresql_where=text('deleted = false')),
    )
    
    # 关系
    algorithm = relationship('AlgorithmDefinition', back_populates='dimension_relations')
    dimension = relationship('Dimension')
```

> **已实施**：后端在维度创建/更新时（`evaluation_controller.py`）解析请求中的 `associatedAlgorithms`（camelCase），逐条写入/重建该关联表；查询维度详情时从关联表反向派生出 `associated_algorithms` 数组返回前端（`to_dict` 含 `dimension_name` 关联查询字段）。

### 4.4 数据结构示例

```typescript
// 通过 API 获取算法关联的评估维度
interface AlgorithmDimensionRelation {
  id: number;
  algorithm_type: string;   // 算法类型: 'asr' | 'translation' | 'tts' | 'speaker_recognition'
  dimension_id: number;    // 评估维度ID
  dimension_name: string;  // 评估维度名称（关联查询）
  is_default: boolean;    // 是否为该算法的默认评估维度
  weight: number;          // 在该算法下的权重 (0-1)
}

// 示例数据（API返回）
const relations = [
  {
    id: 1,
    algorithm_type: 'translation',
    dimension_id: 1,
    dimension_name: 'BLEU评分',
    is_default: true,
    weight: 1.0
  },
  {
    id: 2,
    algorithm_type: 'translation',
    dimension_id: 2,
    dimension_name: 'ROUGE评分',
    is_default: false,
    weight: 0.8
  },
  {
    id: 3,
    algorithm_type: 'asr',
    dimension_id: 3,
    dimension_name: 'WER错误率',
    is_default: true,
    weight: 1.0
  }
];
```

### 4.5 算法类型枚举

```typescript
const ALGORITHM_TYPES = [
  { value: 'asr', label: 'ASR语音识别' },
  { value: 'translation', label: '翻译' },
  { value: 'tts', label: 'TTS语音合成' },
  { value: 'speaker_recognition', label: '说话人识别' },
  { value: 'noise_reduction', label: '降噪' },
  { value: 'vad', label: '语音活动检测' }
];
```

---

## 5. 核心交互逻辑

### 5.1 算法关联选择器组件

```typescript
// 新增字段定义（已实施，见 frontend/src/views/EvaluationLogic/evaluation.ts）
const algorithmField = {
  key: 'associatedAlgorithms',
  label: '关联算法',
  type: 'multi-select-tags',
  required: false,
  options: ALGORITHM_TYPES.map(a => ({ value: a.value, label: a.label })),
  placeholder: '选择关联的算法类型'
};
```

### 5.2 算法关联选择

前端表单内 `associatedAlgorithms` 以**算法类型字符串数组**维护；编辑回填时若接口返回对象数组，则提取 `algorithmType` 转为字符串数组：

```typescript
// 编辑回填：对象数组 → 字符串数组（已实施）
const rawAssociatedAlgorithms = dimension.associatedAlgorithms || [];
let associatedAlgorithmsArray: string[] = [];
if (Array.isArray(rawAssociatedAlgorithms)) {
  if (rawAssociatedAlgorithms.length > 0 && typeof rawAssociatedAlgorithms[0] === 'object') {
    associatedAlgorithmsArray = rawAssociatedAlgorithms.map((item: any) => item.algorithmType);
  } else {
    associatedAlgorithmsArray = rawAssociatedAlgorithms;
  }
}
```

提交时后端（`evaluation_controller.py`）解析 `associatedAlgorithms`，逐条写入/重建 `AlgorithmDimensionRelation` 关联表（未选中项删除关联记录），而不是写入 JSON 字段。

### 5.3 列表显示关联算法

列表/详情接口从 `AlgorithmDimensionRelation` 表反向派生 `associatedAlgorithms`（对象数组，含 `algorithmType`/`isDefault`/`weight`，camelCase 由 schema 转换），前端据此渲染算法标签：

```typescript
const renderAlgorithmTags = (associatedAlgorithms: AlgorithmAssociation[]) => {
  if (!associatedAlgorithms || associatedAlgorithms.length === 0) {
    return '-';
  }
  return associatedAlgorithms.map(a => {
    const algoType = ALGORITHM_TYPES.find(t => t.value === a.algorithmType);
    return `<span class="algo-tag ${a.isDefault ? 'default' : ''}">${algoType?.label || a.algorithmType}</span>`;
  }).join('');
};
```

---

## 6. 输入字段与API匹配配置

### 6.1 required_inputs 字段定义

> **注**：完整字段映射方案见 [15_完整字段映射方案.md](./15_完整字段映射方案.md)

`required_inputs` 用于定义评估维度计算所需的输入字段，解决"输入字段如何和设备/API输出匹配"的问题。

**已实施存储结构**：所需输入/输出字段统一由 `EvaluationDimensionParam` 表（`algorithm_models.py`）定义，按 `param_direction` 区分输入（`input`）与输出提取字段（`output`）；后端在查询维度详情时动态派生为 `required_inputs` / `output_fields` 数组返回前端。

```python
class EvaluationDimensionParam(db.Model):
    """评估维度参数定义表 - 多个算法共用"""
    __tablename__ = 'evaluation_dimension_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dimension_id = Column(Integer, ForeignKey('dimensions.id', ondelete='CASCADE'), nullable=False)
    param_code = Column(String(50), nullable=False)      # 参数代码（评估API需要的字段名，如 asr_result）
    param_name = Column(String(100))                     # 参数显示名称
    label = Column(String(100))                          # 字段显示名称
    field_type = Column(String(20), default='text')      # text, audio, number, boolean, json, timestamp
    param_direction = Column(String(10), nullable=False, default='input')  # input(输入参数) / output(结果提取字段)
    field_path = Column(String(200), nullable=True)      # 结果提取路径（output 专用，如 wer 或 data.result.wer）
    agg_role = Column(String(20), nullable=True)         # 聚合角色（output 专用）: numerator/denominator/value/pass_le/pass_ge/pass_eq
    output_role = Column(String(10), nullable=True)      # 输出字段角色（output 专用）: main(主结果) / aux(辅助字段)
    visible_in_report = Column(Boolean, default=True)    # 是否在报告中显示
    required = Column(Boolean, default=True)             # 是否必填
    default_value = Column(Text)                         # 默认值（JSON格式）
    pass_threshold = Column(Float, nullable=True)        # 达标阈值/目标值（pass_rate 策略专用）
    help_text = Column(Text)                             # 帮助提示文字
    ui_order = Column(Integer, default=0)                # 界面排序
    deleted = Column(Boolean, default=False)

    __table_args__ = (
        Index('uq_dimension_param_code_direction', 'dimension_id', 'param_code', 'param_direction',
              unique=True, postgresql_where=text('deleted = false')),
    )
```

> **映射说明**：原设计中的 `mapped_from`（映射源字段）概念已被 `ParamMapping` 参数映射表替代（见 §6.4）。保存维度时，后端会把 `required_inputs` 写入 `EvaluationDimensionParam` 表，并同步维护 `ParamMapping` 与 `api_settings.body_template` 占位符顺序（`evaluation_controller.py`）。

### 6.2 数据来源类型

数据来源由 `ParamMapping` 表的 `source` 字段定义（`algorithm_models.py`），实际共 **5 类**：

| 来源类型 | 说明 | 示例 |
|----------|------|------|
| `case` | 用例参数字段 | 用例中配置的算法参数（`algorithm_params` 列，按轮分组） |
| `case_config` | 用例配置字段 | 用例配置 `config.rounds` 中的结构性字段（如每轮播放的音频 audios） |
| `device` | 设备输出字段 | 设备采集的音频、文本等原始输出 |
| `api` | API输出字段 | ASR/翻译等算法的返回结果（`algorithm_result`） |
| `reference` | 参考参数字段 | 用例中存储的标准参考数据（文本/音频/RTTM/STM等），详见 [17_参考参数功能设计.md](./17_参考参数功能设计.md) |

> **重要**：`reference` 来源类型用于将用例中配置的参考参数映射到评估维度。参考参数按 `input`/`output` 分类（对应算法的输入/输出参考），每类包含 `api` 和 `e2e` 两种测试值。具体结构请参考 [15_完整字段映射方案.md](./15_完整字段映射方案.md) 第3.2节 `source` 字段含义。
>
> **注**：原设计中的 `context`（上下文计算字段）来源类型未实施，已拆分为 `case`（用例参数）与 `case_config`（用例配置字段）两类。

### 6.3 配置示例

以 WER 错误率为例，维度保存后的实际配置结构（`required_inputs` 对应 `EvaluationDimensionParam` 中 `param_direction='input'` 的记录）：

```json
{
  "name": "WER错误率",
  "statistic_method": "average",
  "required_inputs": [
    {
      "param_code": "asr_result",
      "label": "ASR识别结果",
      "field_type": "text",
      "required": true,
      "ui_order": 1
    },
    {
      "param_code": "asr_ref",
      "label": "参考文本",
      "field_type": "text",
      "required": true,
      "ui_order": 2
    }
  ],
  "api_settings": {
    "method": "POST",
    "timeout": 30000,
    "body_template": {
      "task_type": "wer",
      "rounds": [
        {
          "asr_result": "{{asr_result}}",
          "asr_ref": "{{asr_ref}}"
        }
      ]
    }
  }
}
```

> **要点**：
> - `body_template.rounds` 是**每轮字段模板数组**，占位符与 `required_inputs` 的 `param_code` 一一对应；前端保存时会按 `param_code` 顺序自动同步模板字段（`evaluation.ts`）
> - 多轮评估时后端按轮渲染 `rounds` 数组（`payload_builder.py` 的 `build_payload`），单轮无 rounds 数据时用顶层上下文字段构造单轮
> - 旧设计中手写在 `body_template` 里的 `dimensions` 数组已废弃，多子维度由后端自动注入 `sub_tasks`（见第 7 节）

### 6.4 字段映射机制

```
用例参数(case) / 用例配置(case_config) ──┐
设备输出(device) / 算法输出(api) ─────────┼──▶ ParamMapping 提取 ──▶ context/rounds ──▶ body_template 渲染 ──▶ sub_tasks 注入 ──▶ API请求
参考参数(reference) ──────────────────────┘
```

**实际执行流程（已实施，`evaluation_service.py`）：**
1. `EvaluationService.evaluate_case` 读取用例的 `algorithm_params` 独立列，调用 `_build_rounds_list` 按 `ParamMapping`（`get_param_mapping(algorithm_type, 'evaluation')`）从各来源提取每轮字段，构建 `rounds_list`
2. 多轮结构：`algorithm_result.rounds[]`（0-indexed）逐轮提取输出字段；`reference_params_col` 按 1-indexed 轮次取参考参数；`case_config.rounds` 按轮取结构性字段
3. `EndpointWorker._execute_evaluation` 组装 context：`algorithm_result` 输出字段（维度专属 key `{key}__dim_{dimension_id}` 优先）、参考参数、各轮字段；空值时用维度级 `default_value` 覆盖
4. `build_payload` 按 `body_template` 渲染占位符，`rounds` 模板按轮展开为 `rounds` 数组
5. 从同组子维度（group_items）提取各 `task_type_code` 注入 `payload.sub_tasks`，发送API请求到 eval_server

**ParamMapping 映射规则（已替代原 mapped_from 设计）：**

```python
class ParamMapping(db.Model):
    """参数映射表 - 设备/API/用例参数 → 评估维度参数"""
    algorithm_type = Column(String(50), nullable=False)   # 关联算法类型
    source = Column(String(20), nullable=False, default='api')
    # source: case=用例参数, reference=参考参数, device=设备输出, api=API输出, case_config=用例配置(config.rounds)字段
    source_param = Column(String(50), nullable=False)     # 源参数代码
    source_direction = Column(String(10), default='output')  # 源参数方向: input, output
    dimension_id = Column(Integer, nullable=True)         # 目标评估维度ID(可为空)
    target_param = Column(String(50), nullable=False)     # 目标评估维度参数代码（即 required_inputs 的 param_code）
    transform_type = Column(String(20), default='none')   # 转换类型: none, uppercase, lowercase, json_parse, base64
```

| source 类型 | source_param 示例 | 说明 |
|-------------|-------------------|------|
| `api` | `result` | 从算法输出（`algorithm_result`）中提取字段 |
| `device` | `audio_file` | 从设备输出中提取字段 |
| `case` | `source_lang` | 从用例 `algorithm_params`（按轮分组）中提取字段 |
| `case_config` | `audios` | 从用例配置 `config.rounds` 中提取结构性字段 |
| `reference` | `text`（direction=output） | 从参考参数的输出参考（标准文本）中提取 |
| `reference` | `audio`（direction=input） | 从参考参数的输入参考（待测音频）中提取 |

---

## 7. task_type 与 dimensions 多维度结果配置

### 7.1 核心问题

一次评估请求可返回多个同组维度的结果。请求中 `task_type` 传主维度关键字，同时需要告知微服务计算哪些子维度：

```json
{
  "task_type": "wer",     // 主维度关键字 (必需)
  "sub_tasks": ["wer", "wer_zh", "wer_en"],  // 由后端自动注入的子维度列表
  "rounds": [
    { "asr_result": "...", "asr_ref": "..." }
  ]
}
```

返回结果示例（eval_server 按 `sub_tasks` 计算各子维度）：
```json
{
  "result": {
    "wer": 85.5,
    "wer_zh": 88.2,
    "wer_en": 82.1
  }
}
```

### 7.2 配置方案（已实施：sub_tasks 自动注入）

**不再**在 `body_template` 中手写 `dimensions` 数组。实际机制：

1. 每个子维度是一条独立的 `Dimension` 记录（`dimension_type='sub'`，`parent_dimension_id` 指向主维度），各自配置 `task_type_code`（如 `wer_zh`、`wer_en`）
2. 评估服务 `_dispatch_evaluation_tasks` 按 `api_endpoints` 将同组主/子维度分为一组（group_items）
3. `EndpointWorker._execute_evaluation` 从 group_items 提取各维度的 `task_type_code`（去重），注入 `payload.sub_tasks`（`endpoint_worker.py`）
4. eval_server 侧按 `sub_tasks` 只计算选中的子维度（如 `TurnTakingCalculator`）

```json
{
  "name": "WER错误率",
  "keywords": "wer,word_error_rate",
  "api_settings": {
    "body_template": {
      "task_type": "wer",
      "rounds": [
        { "asr_result": "{{asr_result}}", "asr_ref": "{{asr_ref}}" }
      ]
    }
  }
}
```

> `sub_tasks` 无需配置，由后端运行时自动注入。

### 7.3 子维度继承配置

子维度（dimension_type='sub'）可以继承主维度的 API 配置，无需重复配置：

```json
{
  "name": "WER错误率(中文)",
  "dimension_type": "sub",
  "parent_dimension_id": 1,
  "keywords": "wer_zh,词错误率_中文",
  "type": "auto",
  "result_type": 1,
  "result_min": 0,
  "result_max": 100,
  "weight": 1,
  "rule": {"threshold": 85}
}
```

子维度继承父维度的以下配置（保存主维度时自动同步，见 `evaluation_controller.py`）：
| 字段 | 说明 |
|------|------|
| `api_url` | Master入口URL |
| `api_endpoints` | API端点配置 |
| `api_settings` | API调用设置 |
| `task_type_code` | 评估任务关键字 |

> **注**：`required_inputs`/`output_fields` 仅在主维度上配置（前端表单字段 `conditional: dimensionType === 'main'`），评估时子维度与主维度共用同一组参数定义与 API 配置（同组分派到同一 EndpointWorker）；关联算法由 `AlgorithmDimensionRelation` 表独立维护，不随继承同步。

**继承规则：**
- 仅当子维度未配置对应字段时，才会继承父维度的配置
- 子维度可以覆盖父维度的任何配置
- **更新同步（已实施）**：保存主维度时，系统自动将 `api_url`、`api_endpoints`、`api_settings`、`task_type_code` 同步到所有未配置对应字段的子维度

### 7.4 多维度关联配置

同组主/子维度的层级关系由 `Dimension` 表的 `parent_dimension_id` 维护；与算法的关联由 `AlgorithmDimensionRelation` 表存储，**不包含**子维度列表字段：

```json
{
  "id": 1,
  "name": "WER错误率",
  "associatedAlgorithms": [
    { "algorithmType": "asr", "isDefault": true, "weight": 1.0 }
  ],
  "subDimensions": [
    { "id": 11, "name": "WER错误率(中文)", "taskTypeCode": "wer_zh" },
    { "id": 12, "name": "WER错误率(英文)", "taskTypeCode": "wer_en" }
  ]
}
```

> **注**：`subDimensions` 为前端展示用的关联查询视图（按 `parent_dimension_id` 查询派生），`AlgorithmDimensionRelation` 表中并无 `main_dimension`/`sub_dimensions` 字段。

### 7.5 实际配置示例

**场景：ASR 评估需要计算 WER、WER_ZH、WER_EN 三个维度**

主维度配置（关联算法由 AlgorithmDimensionRelation 表独立存储）：

```json
{
  "id": 1,
  "name": "WER错误率",
  "keywords": "wer,word_error_rate,词错误率",
  "dimension_type": "main",
  "type": "auto",
  "statistic_method": "average",
  "required_inputs": [
    {"param_code": "asr_result", "label": "ASR识别结果", "field_type": "text", "required": true},
    {"param_code": "asr_ref", "label": "参考文本", "field_type": "text", "required": true}
  ],
  "output_fields": [
    {"param_code": "wer", "field_path": "result.wer", "output_role": "main", "agg_role": "value"}
  ],
  "api_settings": {
    "method": "POST",
    "timeout": 30000,
    "body_template": {
      "task_type": "wer",
      "rounds": [
        { "asr_result": "{{asr_result}}", "asr_ref": "{{asr_ref}}" }
      ]
    }
  }
}
```

子维度配置（各自声明 `task_type_code`，API 配置未配置时自动继承主维度）：

```json
[
  {
    "id": 11, "name": "WER错误率(中文)", "dimension_type": "sub",
    "parent_dimension_id": 1, "task_type_code": "wer_zh"
  },
  {
    "id": 12, "name": "WER错误率(英文)", "dimension_type": "sub",
    "parent_dimension_id": 1, "task_type_code": "wer_en"
  }
]
```

**运行时注入的 payload（无需配置）：**

```json
{
  "task_type": "wer",
  "sub_tasks": ["wer", "wer_zh", "wer_en"],
  "rounds": [ { "asr_result": "...", "asr_ref": "..." } ]
}
```

**AlgorithmDimensionRelation 关联记录（实际字段）：**

```json
{
  "algorithm_type": "asr",
  "dimension_id": 1,
  "is_default": true,
  "weight": 1.0
}
```

### 7.6 结果分发机制

```
API返回 {result: {wer: 85.5, wer_zh: 88.2, wer_en: 82.1}}
            │
            ▼
┌──────────────────────────────────────────────────────────┐
│  按各维度的 output 参数（param_direction='output'）        │
│  的 field_path 从 API 响应提取值                          │
│  wer    ──field_path: result.wer───▶ 85.5                │
│  wer_zh ──field_path: result.wer_zh─▶ 88.2               │
│  wer_en ──field_path: result.wer_en─▶ 82.1               │
└──────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────┐
│  写入 TestResultDimension（按 dimension_id 分发）          │
│  - dimension_id / algorithm_type                         │
│  - round_number（多轮为 0-indexed，整体评估为 NULL）       │
│  - dimension_value / score / status(passed/failed)       │
│  - evaluation_status / api_raw_response / api_request_body│
└──────────────────────────────────────────────────────────┘
```

> **注**：结果模型为 `TestResult`（含 `algorithm_result` JSON）+ `TestResultDimension`（每维度×每轮一条记录），原始 API 响应保存在 `api_raw_response` 供追溯。多轮场景下输出字段在 `algorithm_result.rounds[].output` 中，维度专属 key 为 `{key}__dim_{dimension_id}`，缺失时回退通用 key。

---

## 8. 多维度聚合计算配置

### 8.1 聚合计算场景

**重要澄清**：您提到的"几何平均"是指微服务层面的批次聚合计算：

```
某任务/标签下的所有用例：
- 用例1: 10个错误字符 / 100个总字符 = 10% WER
- 用例2: 20个错误字符 / 200个总字符 = 10% WER  
- 用例3: 15个错误字符 / 150个总字符 = 10% WER

微服务返回：整体 WER = (10+20+15) / (100+200+150) = 10%
```

这种方式与"分别计算每个用例的WER再简单平均"是不同的概念。

### 8.2 评估模式分类

| 模式 | API返回 | 适用场景 |
|------|---------|----------|
| **用例级计算** | 多个用例的分数列表 | 需要查看单个用例表现 |
| **批次聚合计算** | 1个聚合后的分数 | 只需要整体评分，微服务内部聚合 |

```json
// 模式1: 用例级 - API返回数组
{
  "dimensions": ["wer"],
  "result": [10.5, 12.3, 8.7, 11.2]
}

// 模式2: 批次聚合 - API返回单个值
{
  "dimensions": ["wer"],
  "result": 10.5
}
```

### 8.3 维度统计方式（已实施）

**已实施**：维度通过 `statistic_method` 字段指定任务完成后的结果聚合方式（`Dimension.statistic_method`，前端表单字段 `statisticMethod`）：

```typescript
const statisticMethodOptions = [
  { value: 'average',      label: '简单平均' },
  { value: 'weighted_wer', label: '加权WER (Σ分子/Σ分母)' },
  { value: 'pass_rate',    label: '达标率 (达标用例数/总用例数)' }
];
```

后端由策略注册表实现（`backend/utils/report/aggregation_strategies.py`）：

| 策略类 | statistic_method | 聚合逻辑 | 依赖的 output 参数 |
|--------|------------------|----------|--------------------|
| `SimpleAverageStrategy` | `average` | 各用例分数简单平均 | `agg_role='value'` |
| `WeightedSumRatioStrategy` | `weighted_wer` | Σ分子 / Σ分母（如 Σ错误字符/Σ总字符） | `agg_role='numerator'` + `agg_role='denominator'` |
| `PassRateStrategy` | `pass_rate` | 达标用例数 / 总用例数 | `agg_role='pass_le'/'pass_ge'/'pass_eq'` + `pass_threshold` |

- 策略通过 `register_strategy(name, strategy)` 注册、`get_strategy(statistic_method)` 获取（注册表模式，可扩展自定义策略）
- 达标条件由 `_find_pass_condition` 按 output 参数的 `agg_role`（`pass_le`/`pass_ge`/`pass_eq`）与 `pass_threshold` 提取

> **未实施**：原设计的 `aggregation_mode`（per_case/batch_aggregate/grouped）与 `group_by`（分组字段）字段未落地到 Dimension 模型；当前所有维度均按"逐用例计算 + 任务完成后按 `statistic_method` 聚合"处理（见 §8.4）。

### 8.4 两种聚合模式对比

| 模式 | 聚合位置 | 说明 |
|------|----------|------|
| **单用例计算+聚合查询** | 微服务端 | 每个用例单独计算，同时保存中间数据，任务完成后可查询分组/整体聚合结果 |
| **微服务内聚合** | 微服务端 | 微服务直接返回聚合结果（不适合错误率这类需要字符数加权的指标） |

**推荐模式：单用例计算+聚合查询**

```
调用时：
- 用例1: tag=中文, 错误=10, 总=100
- 用例2: tag=中文, 错误=20, 总=200
- 用例3: tag=英文, 错误=15, 总=150
- 用例4: tag=英文, 错误=10, 总=100

微服务计算（每个用例单独算）：
- 用例1: 10%
- 用例2: 10%
- 用例3: 10%
- 用例4: 10%

任务完成后可查询聚合结果：
- 中文WER = (10+20)/(100+200) = 10%
- 英文WER = (15+10)/(150+100) = 10%
- 整体WER = (10+20+15+10)/(100+200+150+100) = 10%
```

### 8.5 微服务接口扩展（未实施，保留为规划）

> **现状说明**：当前 eval_server 提供的评估接口为 `POST /api/create_task`（JSON）与 `POST /api/create_task_upload`（multipart，`__MULTIPART__:field_name` 占位符传音频），均为**逐用例同步计算**，响应统一返回 `{code, msg, data: {eval_task_id, status_url, final_result_url}}`；不支持批量 cases、`group_by` 分组与聚合结果查询接口。以下为原规划设计，尚未实施。

#### 8.5.1 调用时传入分组字段（规划）

```json
// 后端调用微服务时传入分组字段
{
  "task_type": "wer",
  "dimensions": ["wer"],
  "group_by": "tag",
  "cases": [
    {"id": 1, "asr_ref": "...", "asr_result": "...", "tag": "中文"},
    {"id": 2, "asr_ref": "...", "asr_result": "...", "tag": "中文"},
    {"id": 3, "asr_ref": "...", "asr_result": "...", "tag": "英文"},
    {"id": 4, "asr_ref": "...", "asr_result": "...", "tag": "英文"}
  ]
}
```

#### 8.5.2 任务完成后查询聚合结果

```json
// GET /api/get_aggregate_result/<task_id>?group_by=tag

{
  "task_id": "xxx",
  "dimensions": ["wer"],
  "group_by": "tag",
  "results": {
    "中文": {
      "wer": 10.0,
      "total_errors": 30,
      "total_chars": 300,
      "case_count": 2
    },
    "英文": {
      "wer": 12.0,
      "total_errors": 25,
      "total_chars": 250,
      "case_count": 2
    }
  },
  "overall": {
    "wer": 11.0,
    "total_errors": 55,
    "total_chars": 550,
    "case_count": 4
  }
}
```

### 8.6 分组聚合结果存储（未实施，保留为规划）

> **实际结果模型（已实施）**：系统中并不存在 `EvaluationResult` 模型，实际为：
> - `TestResult`：用例级结果，含 `algorithm_result`（JSON，含 rounds[] 结构）与 `result_data_path`
> - `TestResultDimension`：维度级结果（每维度×每轮一条），含 `dimension_id`、`algorithm_type`、`round_number`（NULL=整体评估，0-indexed）、`dimension_value`、`score`、`status`（passed/failed）、`evaluation_status`、`api_raw_response`、`api_request_body`
>
> 任务级统计聚合由 `statistic_method` 策略（§8.3）在任务完成后计算，不落独立分组记录。

#### 8.6.1 数据模型扩展（规划）

在结果模型中增加分组字段的原始设计（未实施）：

```python
class EvaluationResult(db.Model):
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('test_tasks.id'))
    test_case_id = Column(Integer, ForeignKey('test_cases.id'))
    dimension_id = Column(Integer, ForeignKey('dimensions.id'))
    
    # 分组聚合字段（新增）
    group_key = Column(String(255))  # 分组标识，如 "中文"、"音频A"
    group_by = Column(String(50))    # 分组类型：tag/device/task
    
    score = Column(Float)            # 分数值
    raw_result = Column(JSON)       # 原始API返回
    is_aggregate = Column(Boolean, default=False)  # 是否聚合结果
```

#### 8.6.2 存储策略

| 场景 | 存储方式 | 说明 |
|------|----------|------|
| 用例级结果 | `is_aggregate=False` | 每个用例的独立分数 |
| 分组聚合结果 | `is_aggregate=True, group_key='标签名'` | 按标签聚合的分数 |
| 整体聚合结果 | `is_aggregate=True, group_key='_overall'` | 整体聚合分数 |

#### 8.6.3 存储示例

```json
// 微服务返回
{
  "dimensions": ["wer"],
  "result": {
    "中文": 10.5,
    "英文": 8.2,
    "_overall": 10.27
  }
}

// 后端存储为多条记录
[
  {
    "dimension_id": 1,
    "group_key": "中文",
    "group_by": "tag",
    "score": 10.5,
    "is_aggregate": true
  },
  {
    "dimension_id": 1,
    "group_key": "英文", 
    "group_by": "tag",
    "score": 8.2,
    "is_aggregate": true
  },
  {
    "dimension_id": 1,
    "group_key": "_overall",
    "group_by": "task",
    "score": 10.27,
    "is_aggregate": true
  }
]
```

### 8.7 完整配置示例（已实施口径：加权WER）

评估维度配置（维度本身）：
```json
{
  "id": 1,
  "name": "WER错误率",
  "keywords": "wer,word_error_rate",
  "type": "auto",
  "statistic_method": "weighted_wer",

  "required_inputs": [
    {"param_code": "asr_result", "label": "ASR识别结果", "field_type": "text", "required": true},
    {"param_code": "asr_ref", "label": "参考文本", "field_type": "text", "required": true}
  ],
  "output_fields": [
    {"param_code": "total_errors", "field_path": "result.total_errors", "agg_role": "numerator", "output_role": "aux", "visible_in_report": true},
    {"param_code": "total_chars", "field_path": "result.total_chars", "agg_role": "denominator", "output_role": "aux", "visible_in_report": true},
    {"param_code": "wer", "field_path": "result.wer", "agg_role": "value", "output_role": "main", "visible_in_report": true}
  ],
  "api_settings": {
    "method": "POST",
    "body_template": {
      "task_type": "wer",
      "rounds": [
        { "asr_result": "{{asr_result}}", "asr_ref": "{{asr_ref}}" }
      ]
    }
  }
}
```

**AlgorithmDimensionRelation 表中的关联配置：**

```json
{
  "algorithm_type": "asr",
  "dimension_id": 1,
  "is_default": true,
  "weight": 1.0
}
```

> 任务完成后按 `WeightedSumRatioStrategy` 聚合：整体 WER = Σtotal_errors / Σtotal_chars。

### 8.8 执行流程（已实施：逐用例计算 + statistic_method 聚合）

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 逐用例评估（evaluation_service.py）                  │
│ - 每个用例独立调用 eval_server（POST /api/create_task 或     │
│   /api/create_task_upload multipart）                        │
│ - 单次请求仅含该用例的 rounds 数据，不含批量 cases/group_by  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 结果落库（逐用例、逐维度、逐轮）                     │
│ - TestResult.algorithm_result 保存原始返回（含 rounds[]）    │
│ - TestResultDimension 按维度×轮次写入 dimension_value/score │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 任务完成后聚合                                       │
│ - 按 Dimension.statistic_method 选择策略（注册表模式）       │
│   average      → SimpleAverageStrategy                      │
│   weighted_wer → WeightedSumRatioStrategy（Σ分子/Σ分母）    │
│   pass_rate    → PassRateStrategy（agg_role + threshold）   │
│ - 聚合为任务级统计分数，不落独立分组记录                     │
└─────────────────────────────────────────────────────────────┘
```

> **未实施（规划）**：批量用例聚合模式（Step 1 改为批量请求 + 分组字段、Step 3 前增加 `get_aggregate_result` 分组查询、分组聚合记录落库）仍为原设计规划，见 §8.5/§8.6。

### 8.9 原规划流程：批量用例 + 分组聚合查询（未实施）

> 以下为原设计的"单用例计算+聚合查询"批量流程图示，依赖 §8.5 的微服务扩展接口，尚未实施；已实施的执行流程见 §8.8。

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 后端调用微服务（批量用例）                           │
│ POST /api/create_task (批量模式)                            │
│ {                                                           │
│   task_type: "wer",                                         │
│   dimensions: ["wer"],                                      │
│   group_by: "tag",                                          │
│   cases: [                                                  │
│     {"id": 1, "asr_ref": "...", "asr_result": "...", "tag": "中文"},
│     {"id": 2, "asr_ref": "...", "asr_result": "...", "tag": "中文"},
│     {"id": 3, "asr_ref": "...", "asr_result": "...", "tag": "英文"},
│     {"id": 4, "asr_ref": "...", "asr_result": "...", "tag": "英文"}
│   ]                                                         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 微服务计算（单用例级别）                            │
│ - 用例1: 10% (错误10/总100, tag=中文)                      │
│ - 用例2: 10% (错误20/总200, tag=中文)                      │
│ - 用例3: 10% (错误15/总150, tag=英文)                      │
│ - 用例4: 10% (错误10/总100, tag=英文)                      │
│ - 保存中间数据用于聚合计算                                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 任务状态变为 completed/failed 时获取聚合结果        │
│                                                            │
│ 后端轮询检测任务状态：                                      │
│ - 当 status=completed 或 status=failed 时                  │
│ - 调用 GET /api/get_aggregate_result/<task_id>?group_by=tag│
│                                                            │
│ 返回:                                                      │
│ {                                                          │
│   "results": {                                             │
│     "中文": {"wer": 10.0, "total_errors": 30, "total_chars": 300},
│     "英文": {"wer": 10.0, "total_errors": 25, "total_chars": 250}
│   },                                                        │
│   "overall": {"wer": 10.0, "total_errors": 55, "total_chars": 550}
│ }                                                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 后端存储结果                                        │
│ - 用例级结果: is_aggregate=false (4条记录)                │
│ - 分组聚合: is_aggregate=true, group_key="中文/英文"      │
│ - 整体聚合: is_aggregate=true, group_key="_overall"        │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 实施清单

### 9.1 已实施（✅，经代码核实）

**数据模型与配置（后端）**
- [x] `Dimension.statistic_method` 统计方式字段（average/weighted_wer/pass_rate）
- [x] `EvaluationDimensionParam` 参数定义表（required_inputs/output_fields，param_direction 区分输入/输出，含 agg_role/pass_threshold/output_role/default_value 等）
- [x] `AlgorithmDimensionRelation` 维度-算法关联表（唯一索引 `uq_algorithm_dimension`），替代 JSON 字段
- [x] `ParamMapping` 参数映射表（source: case/reference/device/api/case_config），替代 mapped_from
- [x] 保存维度时同步 `ParamMapping` 与 `body_template` 占位符（`evaluation_controller.py`）
- [x] 保存主维度时同步 API 配置到未配置的子维度（api_url/api_endpoints/api_settings/task_type_code）

**评估执行链路（后端）**
- [x] `EvaluationService.evaluate_case` 逐用例评估，`_build_rounds_list` 多轮字段构建（case/case_config/reference/api 四来源按轮提取）
- [x] `_dispatch_evaluation_tasks` 按 api_endpoints 分组，`EndpointWorker` 构建上下文并渲染 `body_template`（rounds 按轮展开）
- [x] `sub_tasks` 运行时自动注入（从 group_items 提取各子维度 `task_type_code`，eval_server 按此只算选中子维度）
- [x] 结果按维度×轮次写入 `TestResult`/`TestResultDimension`（含 api_raw_response/api_request_body 追溯）

**聚合策略（后端）**
- [x] `aggregation_strategies.py` 策略注册表：`SimpleAverageStrategy`/`WeightedSumRatioStrategy`/`PassRateStrategy`，`register_strategy`/`get_strategy(statistic_method)`
- [x] 达标条件提取 `_find_pass_condition`（agg_role: pass_le/pass_ge/pass_eq + pass_threshold）

**前端**
- [x] 维度表单"统计方式"选择（简单平均/加权WER/达标率）
- [x] 所需输入配置（requiredInputs）/输出字段配置（outputFields）编辑组件
- [x] 关联算法多选（multi-select-tags，提交字符串数组，后端写关联表）

### 9.2 未实施（保留为规划）

**微服务改动 (eval_server)**
- [ ] 创建批量用例计算接口 `/api/create_batch_task`
- [ ] 批量模式下保存每个用例的中间数据（错误字符数、总字符数）
- [ ] 创建聚合结果查询接口 `/api/get_aggregate_result/<task_id>`
- [ ] 支持 `group_by` 参数（tag/device/task）
- [ ] 返回分组聚合和整体聚合结果

**后端改动**
- [ ] Dimension 模型新增 `aggregation_mode` 字段
- [ ] Dimension 模型新增 `group_by` 字段
- [ ] 评估执行器支持批量用例模式
- [ ] 评估执行器调用聚合结果查询接口
- [ ] 结果模型新增分组聚合字段
- [ ] 分组聚合结果存储逻辑

**前端改动**
- [ ] 维度配置新增"聚合模式"选择（单用例/批量用例）
- [ ] 维度配置新增"分组字段"选择（tag/device/task）
- [ ] 评估结果展示支持分组聚合视图

---

## 10. 改动影响评估

### 10.1 最小化改动原则

| 改动项 | 影响范围 | 改动量 |
|--------|----------|--------|
| 数据库 | 新增1个字段 | 小 |
| 后端模型 | 新增1个字段定义 | 小 |
| 后端Schema | 新增1个字段 | 小 |
| 前端表格 | 新增1列 | 小 |
| 前端表单 | 新增1个字段 | 小 |

### 10.2 兼容性

- **向后兼容**：维度未配置关联算法时 `AlgorithmDimensionRelation` 无记录，接口返回空数组，不影响现有功能
- **无破坏性改动**：不修改现有字段含义和结构（关联算法与参数定义均独立建表）
- **渐进式增强**：新功能可选，不影响现有评估维度使用
