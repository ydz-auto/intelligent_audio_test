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
│  │ │ 翻译  │ │  ASR  │ │ 声纹识别   │  [+ 添加算法]           ││
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

```python
class Dimension(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    keywords = Column(String(255))
    dimension_type = Column(String(20), default='main')  # 'main' | 'sub'
    parent_dimension_id = Column(Integer, ForeignKey('dimensions.id'))  # 主维度ID
    task_type_code = Column(String(50))  # API调用的task_type值
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
    required_inputs = Column(JSON, nullable=False, default=list)
    score_unit = Column(String(50), nullable=True, default='')
    associated_algorithms = Column(JSON, nullable=True, default=list)  # 关联算法列表
    status = Column(Boolean, nullable=False, default=True)
    deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

### 4.2 新增字段（扩展）

```python
# 评估维度与算法的关联现在通过 AlgorithmDimensionRelation 表管理，不再使用 JSON 字段
# 详见 algorithm_models.py 中的 AlgorithmDimensionRelation 模型
```

### 4.3 数据模型关系

```python
# algorithm_models.py 中的关键模型

class AlgorithmDimensionRelation(db.Model):
    """评估维度与算法关联表"""
    __tablename__ = 'algorithm_dimension_relations'
    
    id = Column(Integer, primary_key=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False)
    dimension_id = Column(Integer, ForeignKey('dimensions.id', ondelete='CASCADE'), nullable=False)
    is_default = Column(Boolean, default=False)  # 是否默认评估维度
    weight = Column(Float, default=1.0)  # 权重
    deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关系
    algorithm = relationship('AlgorithmDefinition', back_populates='dimension_relations')
```

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

### 4.4 算法类型枚举

```typescript
const ALGORITHM_TYPES = [
  { value: 'asr', label: 'ASR语音识别' },
  { value: 'translation', label: '翻译' },
  { value: 'tts', label: 'TTS语音合成' },
  { value: 'speaker_recognition', label: '声纹识别' },
  { value: 'noise_reduction', label: '降噪' },
  { value: 'vad', label: '语音活动检测' }
];
```

---

## 5. 核心交互逻辑

### 5.1 算法关联选择器组件

```typescript
// 新增字段定义
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

```typescript
const handleAlgorithmSelect = (algorithms: string[]) => {
  const existingAlgoTypes = formData.value.associatedAlgorithms
    .map((a: AlgorithmAssociation) => a.algorithm_type);
  
  // 添加新选择的算法
  algorithms.forEach(algoType => {
    if (!existingAlgoTypes.includes(algoType)) {
      formData.value.associatedAlgorithms.push({
        algorithm_type: algoType,
        is_default: false,
        weight: 1.0
      });
    }
  });
  
  // 移除取消选择的算法
  formData.value.associatedAlgorithms = formData.value.associatedAlgorithms
    .filter((a: AlgorithmAssociation) => algorithms.includes(a.algorithm_type));
};
```

### 5.3 列表显示关联算法

```typescript
// 在表格中显示关联算法标签
const renderAlgorithmTags = (associatedAlgorithms: AlgorithmAssociation[]) => {
  if (!associatedAlgorithms || associatedAlgorithms.length === 0) {
    return '-';
  }
  return associatedAlgorithms.map(a => {
    const algoType = ALGORITHM_TYPES.find(t => t.value === a.algorithm_type);
    return `<span class="algo-tag ${a.is_default ? 'default' : ''}">${algoType?.label || a.algorithm_type}</span>`;
  }).join('');
};
```

---

## 6. 输入字段与API匹配配置

### 6.1 required_inputs 字段定义

> **注**：完整字段映射方案见 [15_完整字段映射方案.md](file:///c:/S2TT/auto_test/ver8/202601292330/doc/功能设计文档/智能语音算法配置适配/15_完整字段映射方案.md)

`required_inputs` 用于定义评估维度计算所需的输入字段，解决"输入字段如何和设备/API输出匹配"的问题。

```typescript
interface RequiredInput {
  key: string;               // 字段键名 (如: asr_result, translation_result)
  label: string;            // 字段显示名称
  type: 'text' | 'audio' | 'number';  // 字段类型
  source: 'device' | 'api' | 'context' | 'reference';  // 数据来源
  required: boolean;         // 是否必需
  mapped_from?: string;     // 映射源字段（如 api_output.result, reference.input.text）
  description?: string;     // 字段说明
}
```

### 6.2 数据来源类型

| 来源类型 | 说明 | 示例 |
|----------|------|------|
| `device` | 设备输出字段 | 设备采集的音频、文本等原始输出 |
| `api` | API返回字段 | ASR/翻译等算法的返回结果 |
| `context` | 上下文计算字段 | 从测试上下文计算得出的衍生数据 |
| `reference` | 参考参数字段 | 用例中存储的标准参考数据（文本/音频/RTTM/STM等），详见 [17_参考参数功能设计.md](file:///c:/S2TT/auto_test/ver8/202601292330/doc/功能设计文档/智能语音算法配置适配/17_参考参数功能设计.md) |

> **重要**：`reference` 来源类型用于将用例中配置的参考参数映射到评估维度。参考参数按 `input`/`output` 分类（对应算法的输入/输出参考），每类包含 `api` 和 `e2e` 两种测试值。具体结构请参考 [15_完整字段映射方案.md](file:///c:/S2TT/auto_test/ver8/202601292330/doc/功能设计文档/智能语音算法配置适配/15_完整字段映射方案.md) 第3.2节 `source` 字段含义。

### 6.3 配置示例

```json
{
  "name": "WER错误率",
  "required_inputs": [
    {
      "key": "asr_result",
      "label": "ASR识别结果",
      "source": "api",
      "required": true,
      "mapped_from": "api_output.result",
      "description": "ASR算法识别出的文本"
    },
    {
      "key": "asr_ref",
      "label": "参考文本",
      "source": "reference",
      "required": true,
      "mapped_from": "reference.output.text",
      "description": "标准参考文本"
    },
    {
      "key": "task_type",
      "label": "任务类型",
      "source": "context",
      "required": true,
      "description": "用于指定计算引擎"
    }
  ],
  "api_settings": {
    "body_template": {
      "task_type": "wer",
      "dimensions": ["wer", "wer_zh", "wer_en"],
      "asr_result": "{{asr_result}}",
      "asr_ref": "{{asr_ref}}"
    }
  }
}
```

### 6.4 字段映射机制

```
设备输出/API返回 ─────────────────┐
                                    ├──▶ required_inputs 校验 ──▶ body_template 渲染 ──▶ API请求
测试上下文 ────────────────────────┘
参考参数 ──────────────────────────┘
```

**执行流程：**
1. 从设备输出和API返回中提取 `required_inputs` 定义的字段
2. 从参考参数（`reference.input` 或 `reference.output`）中提取对应字段
3. 校验必填字段是否存在
4. 将字段值渲染到 `body_template` 占位符
5. 发送API请求

**mapped_from 映射规则：**

| source 类型 | mapped_from 示例 | 说明 |
|-------------|------------------|------|
| `api` | `api_output.result` | 从API返回中提取字段 |
| `device` | `device_output.audio_file` | 从设备输出中提取字段 |
| `context` | `context.task_id` | 从测试上下文中提取字段 |
| `reference` | `reference.output.text` | 从参考参数中提取（output表示输出参考，text表示文本类型） |
| `reference` | `reference.input.audio` | 从参考参数中提取（input表示输入参考） |

---

## 7. task_type 与 dimensions 多维度结果配置

### 7.1 核心问题

一次评估请求可返回多个同组维度的结果，但 `task_type` 只传主维度关键字：

```json
{
  "task_type": "wer",           // 主维度关键字 (必需)
  "dimensions": ["wer", "wer_zh", "wer_en"],  // 返回的多个维度
  "asr_result": "...",
  "asr_ref": "..."
}
```

返回结果示例：
```json
{
  "dimensions": ["wer", "wer_zh", "wer_en"],
  "result": {
    "wer": 85.5,
    "wer_zh": 88.2,
    "wer_en": 82.1
  }
}
```

### 7.2 配置方案

在维度配置中使用 `task_type` 作为主维度标识，`dimensions` 数组声明返回的所有子维度：

```json
{
  "name": "WER错误率",
  "keywords": "wer,word_error_rate",
  "api_settings": {
    "body_template": {
      "task_type": "wer",
      "dimensions": ["wer", "wer_zh", "wer_en"],
      "asr_result": "{{asr_result}}",
      "asr_ref": "{{asr_ref}}"
    }
  }
}
```

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

子维度继承父维度的以下配置：
| 字段 | 说明 |
|------|------|
| `api_url` | Master入口URL |
| `api_endpoints` | API端点配置 |
| `api_settings` | API调用设置 |
| `task_type_code` | 评估任务关键字 |
| `associated_algorithms` | 关联算法列表 |
| `required_inputs` | 所需输入配置 |

**继承规则：**
- 仅当子维度未配置对应字段时，才会继承父维度的配置
- 子维度可以覆盖父维度的任何配置
- **更新同步**：当主维度的 `api_url`、`api_endpoints`、`api_settings`、`task_type_code` 等配置变更时，系统会自动将新配置同步到所有未配置对应字段的子维度

### 7.4 多维度关联配置

使用 `AlgorithmDimensionRelation` 表关联同组维度：

```json
{
  "id": 1,
  "name": "WER错误率",
  "associated_algorithms": [
    {
      "algorithm_type": "asr",
      "is_default": true,
      "weight": 1.0,
      "sub_dimensions": ["wer", "wer_zh", "wer_en"]
    }
  ]
}
```

### 7.5 实际配置示例

**场景：ASR 评估需要计算 WER、WER_ZH、WER_EN 三个维度**

评估维度本身配置（AlgorithmDimensionRelation 表独立存储关联）：

```json
{
  "id": 1,
  "name": "WER错误率",
  "keywords": "wer,word_error_rate,词错误率",
  "type": "auto",
  "required_inputs": [
    {"key": "asr_result", "label": "ASR识别结果", "source": "api", "required": true, "mapped_from": "api_output.result"},
    {"key": "asr_ref", "label": "参考文本", "source": "reference", "required": true, "mapped_from": "reference.output.text"},
    {"key": "task_type", "label": "任务类型", "source": "context", "required": true},
    {"key": "source_lang", "label": "源语言", "source": "context", "required": false}
  ],
  "api_settings": {
    "method": "POST",
    "timeout": 60,
    "body_template": {
      "task_type": "wer",
      "dimensions": ["wer", "wer_zh", "wer_en"],
      "asr_result": "{{asr_result}}",
      "asr_ref": "{{asr_ref}}",
      "source_lang": "{{source_lang}}"
    }
  }
}
```

**AlgorithmDimensionRelation 关联记录：**

```json
{
  "algorithm_type": "asr",
  "dimension_id": 1,
  "is_default": true,
  "weight": 1.0,
  "main_dimension": "wer",
  "sub_dimensions": ["wer", "wer_zh", "wer_en"]
}
```

### 7.6 结果分发机制

```
API返回 {wer: 85.5, wer_zh: 88.2, wer_en: 82.1}
            │
            ▼
┌─────────────────────────────────────────────┐
│  评估引擎解析 dimensions 数组                │
│  [wer, wer_zh, wer_en]                      │
└─────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────┐
│  分发到对应的评估维度记录                    │
│  wer ────────▶ 85.5                         │
│  wer_zh ─────▶ 88.2                         │
│  wer_en ─────▶ 82.1                         │
└─────────────────────────────────────────────┘
```

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

### 8.3 维度配置中的模式指定

在维度配置中增加 `aggregation_mode` 字段来指定评估模式：

```typescript
interface DimensionConfig {
  // 评估模式
  aggregation_mode: 'per_case' | 'batch_aggregate' | 'grouped';
  
  // 分组字段（用于 grouped 模式）
  group_by?: string[];  // 如 ["tag", "device_id"]
}
```

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

### 8.5 微服务接口扩展

#### 8.5.1 调用时传入分组字段

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

### 8.6 分组聚合结果存储

#### 8.6.1 数据模型扩展

在 `EvaluationResult` 模型中增加分组字段：

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

### 8.6 完整配置示例

评估维度配置（维度本身）：
```json
{
  "id": 1,
  "name": "WER错误率",
  "keywords": "wer,word_error_rate",
  "type": "auto",
  
  "aggregation_mode": "grouped",
  "group_by": ["tag"],
  
  "required_inputs": [
    {"key": "asr_result", "label": "ASR识别结果", "source": "api", "required": true, "mapped_from": "api_output.result"},
    {"key": "asr_ref", "label": "参考文本", "source": "reference", "required": true, "mapped_from": "reference.output.text"},
    {"key": "task_type", "label": "任务类型", "source": "context", "required": true},
    {"key": "tag", "label": "标签分组", "source": "context", "required": true}
  ],
  "api_settings": {
    "method": "POST",
    "body_template": {
      "task_type": "wer",
      "dimensions": ["wer"],
      "group_by": "tag",
      "asr_result": "{{asr_result}}",
      "asr_ref": "{{asr_ref}}"
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

### 8.7 执行流程（单用例计算+聚合查询模式）

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

### 9.1 微服务改动 (WER微服务)

- [ ] 创建批量用例计算接口 `/api/create_batch_task`
- [ ] 批量模式下保存每个用例的中间数据（错误字符数、总字符数）
- [ ] 创建聚合结果查询接口 `/api/get_aggregate_result/<task_id>`
- [ ] 支持 `group_by` 参数（tag/device/task）
- [ ] 返回分组聚合和整体聚合结果

### 9.2 后端改动

- [ ] Dimension 模型新增 `aggregation_mode` 字段
- [ ] Dimension 模型新增 `group_by` 字段
- [ ] 评估执行器支持批量用例模式
- [ ] 评估执行器调用聚合结果查询接口
- [ ] EvaluationResult 模型新增分组字段
- [ ] 分组聚合结果存储逻辑

### 9.3 前端改动

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

- **向后兼容**：现有数据 `associated_algorithms` 为空数组，不影响现有功能
- **无破坏性改动**：不修改现有字段含义和结构
- **渐进式增强**：新功能可选，不影响现有评估维度使用
