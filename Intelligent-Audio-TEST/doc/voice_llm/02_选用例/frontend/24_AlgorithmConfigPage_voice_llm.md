# 24_AlgorithmConfigPage voice_llm 注册

> 文件：`frontend/src/views/AlgorithmConfigPage.vue`

## 现状分析

AlgorithmConfigPage 是算法定义的管理页面，支持算法的增删改查、参数定义、映射关系配置。当前已注册 STT、TTS、enhance 等算法类型。

### 现有数据结构

```ts
// AlgorithmConfigPage.vue 本地接口
interface AlgorithmRecord {
  type: string           // 算法类型标识，如 'stt'、'tts'
  name: string           // 显示名称
  group_id?: number
  group_name?: string
  description?: string
  status: string         // 'online' | 'offline'
  icon?: string
  display_order: number
  params?: any[]
  mappings?: { device: any[]; api: any[]; evaluation: any[] }
}
```

### 现有 API 调用

| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/api/v1/algorithm/definitions` | 加载所有算法定义 |
| GET | `/api/v1/algorithm/definitions/{type}` | 加载单个算法详情 |
| POST | `/api/v1/algorithm/definitions` | 创建/克隆算法定义 |
| DELETE | `/api/v1/algorithm/definitions/{type}` | 删除算法定义 |
| GET | `/api/v1/algorithm/groups` | 加载算法分组 |

### 子组件

- `AlgorithmConfigModal` — 创建/编辑算法的模态窗（含 basic / params / mappings / dimensions 四个 Tab）
- `MappingEditor` — 映射关系编辑器
- `DynamicForm` — 动态参数表单
- `AlgorithmParamsConfig` — 参数定义配置器

## 改造方案

### 1. 注册 voice_llm 算法定义

通过 AlgorithmConfigPage 的 UI 或 API 注册：

```json
{
  "type": "voice_llm",
  "name": "语音交互大模型",
  "group_id": null,
  "description": "语音交互大模型测试，支持多轮会话、声纹注册、干扰人播放等",
  "status": "online",
  "icon": "chat",
  "display_order": 10
}
```

### 2. 参数定义管理

voice_llm 的 E2E 公共能力（导轨/音量/声纹/打断等）已迁出到 `algorithmParams`，由 `case_algorithm_params` 表驱动，不在此页面作为 config 结构化字段管理。

在 AlgorithmConfigModal 的 params Tab 中，仅注册 **voice_llm 算法专有参数**。当前 voice_llm 无专有参数，params Tab 可以为空。若后续需要 LLM 推理参数（如 `max_tokens`、`temperature`），按需添加。

> **注意**：以下参数已迁出，不在 params Tab 中作为 config 结构化字段管理，而是在 `case_algorithm_params` 表中定义，通过 DynamicForm 渲染到 `algorithmParams` 中：
> - rail_distance, volume → `algorithmParams[{field_code:'railDistance/volumeLevel', ...}]`（E2E 公共能力）
> - voiceprint_wait_time → `algorithmParams[{field_code:'voiceprintWaitTime', ...}]`
> - allow_interruption, interruption_sensitivity → `algorithmParams[{field_code:'interruptionEnabled/interruptionSensitivity', ...}]`
> - session_timeout, context_mode → 移除（不在原始需求中）
> - llm_judge_model → 评估微服务配置

**参考参数（Reference Params）**：
- `reference_text` — 参考文本（如需要）

### 3. 映射关系配置

在 AlgorithmConfigModal 的 mappings Tab 中，为 voice_llm 配置映射（仅非公共能力参数需要映射）：

| Tab | component_type | 映射示例 |
|-----|---------------|---------|
| evaluation | evaluation | reference_text → eval.reference_text |

### 4. scope 字段展示

voice_llm 的参数（CaseAlgorithmParam）新增了 `scope` 字段（common/api/e2e）。AlgorithmConfigPage 的参数定义列表中应展示 scope 列：

```vue
<el-table-column prop="scope" label="适用范围" width="100">
  <template #default="{ row }">
    <el-tag :type="scopeTagType(row.scope)">{{ row.scope }}</el-tag>
  </template>
</el-table-column>
```

其中 `scopeTagType` 返回不同的标签颜色：
- `common` → `info`
- `api` → `success`
- `e2e` → `warning`

### 5. 算法分组

可选：创建 voice_llm 专属分组

```json
{
  "name": "大模型测试",
  "description": "语音交互大模型相关算法",
  "icon": "brain",
  "display_order": 5
}
```

## 不变部分

- 页面整体布局（列表 + 详情）
- 克隆、删除功能
- 分页、搜索、筛选逻辑
- AlgorithmConfigModal 的 Tab 结构
- MappingEditor 和 DynamicForm 的交互方式

## 引用关系

- ← `01_选算法/backend/06_algorithm_Schema与Controller` — 后端算法 CRUD 接口
- ← `01_选算法/backend/07_voice_llm算法参数种子数据` — 参数种子数据
- → `01_选算法/frontend/03_api.ts算法API扩展` — algorithmApi 接口定义
- → `01_选算法/frontend/15_DynamicForm_scope过滤` — DynamicForm 的 scope 过滤
