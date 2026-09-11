# API管理页面适配方案

> **落地状态说明**：本方案所述的 API 与算法类型关联能力（`API.algorithm_type` 模型字段、三 Schema 双命名兼容、列表接口按算法筛选、表单算法类型字段、筛选下拉、卡片算法标签、选项动态加载）**已在前后端全面落地**。本文档已按当前代码库实际实现（`backend/models/models.py`、`backend/schemas/api.py`、`backend/controllers/api_controller.py`、`frontend/src/views/DeviceLogic/device.ts`、`frontend/src/utils/utils.ts`、`frontend/src/views/Device.vue`、`frontend/src/components/common/modal/CRUDFormModal.vue` 等）对齐修订。

## 1. 页面概述

### 1.1 页面定位

API管理页面用于管理测试API接口，位于设备管理页面的"测试API管理"Tab中，承载智能语音算法配置化方案中的 **API 与算法类型关联**：声明每个被测 API 所属的算法类型（`algorithmType`），供测试执行时按被测设备 `device_type` 路由三执行器（物理设备→E2EExecutor、HTTP API→APISessionExecutor、WebSocket API→RealtimeSessionExecutor）场景下选择匹配算法的 API 使用。

### 1.2 页面路由
- 路由路径：`/Device`（设备管理页面 > 测试API管理 Tab）
- 菜单位置：设备管理

### 1.3 核心改动

| 改动项 | 状态 | 说明 |
|-------|------|------|
| API卡片增加"算法类型"标签显示 | ✅ 已落地 | meta 区域经 `getAlgorithmTypeName()` 显示算法文案 |
| 新增/编辑API表单增加算法类型选择字段 | ✅ 已落地 | `generateDeviceFields('api')` 注入 `algorithmType` select 字段，选项动态加载 |
| 筛选器增加算法类型下拉筛选 | ✅ 已落地 | `algorithmTypeFilter` 状态 + API 卡片筛选下拉 |

---

## 2. 页面布局（适配现有架构）

### 2.1 布局结构（已落地）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  设备管理                                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  [测试设备管理] [测试API管理] [播放设备管理]  ← Tab切换                    │
├─────────────────────────────────────────────────────────────────────────┤
│  统计概览: 总API数 | 可用API | 不可用API | 测试中API                       │
├─────────────────────────────────────────────────────────────────────────┤
│  [+ 添加测试API]  [批量操作▼]  [导入/导出▼]                               │
│                                                                          │
│  筛选器:                                                                 │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐          │
│  │ 搜索名称或URL... │  │ 状态: [全部▼]│  │ 算法类型: [全部▼]│ ← 已落地   │
│  └──────────────────┘  └──────────────┘  └──────────────────┘          │
│                                                                          │
│  API卡片网格:                                                            │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐ │
│  │ □ 翻译API-001      │  │ □ ASR-API-001      │  │ □ 声纹API-001      │ │
│  │ ● 在线             │  │ ● 在线             │  │ ○ 离线             │ │
│  │                    │  │                    │  │                    │ │
│  │ [翻译] ← 已落地    │  │ [ASR] ← 已落地     │  │ [声纹识别] ← 已落地│ │
│  │                    │  │                    │  │                    │ │
│  │ API版本: v1.0      │  │ API版本: v2.0      │  │ API版本: v1.2      │ │
│  │ 成功率: 99.5%      │  │ 成功率: 98.2%      │  │ 成功率: 95.0%      │ │
│  │                    │  │                    │  │                    │ │
│  │ [编辑] [删除] [健康检查] │ [编辑] [删除] [健康检查] │ [编辑] [删除] [健康检查] │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 新增/编辑API弹窗（已落地：动态表单 + 算法类型字段）

> **实现说明**：API 添加/编辑弹窗为**全局动态表单弹窗**（`CRUDFormModal`，由 `useDeviceManagement.addDevice()/editDevice()` 经 `modalManager.open(MODAL_TYPES.ADD_DEVICE / EDIT_DEVICE)` 打开），表单字段由 `generateDeviceFields('api')` 统一生成，其中 `algorithmType` 字段通过 `action: 'loadAlgorithmTypes'` 动态加载选项（`GET /api/v1/algorithm/options`）。

```
┌─────────────────────────────────────────────────────────────────────────┐
│  添加测试API / 编辑测试API（CRUDFormModal 动态表单）                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  设备名称:   [__________________]                                         │
│  设备描述:   [__________________]                                         │
│  API名称:    [__________________]                                         │
│  供应商:     [__________________]  (如 volc_ast, ali, tencent)           │
│  Master入口URL: [__________________]                                      │
│                                                                          │
│  算法类型:   [请选择算法类型 ▼]        ← 已落地：type='select'            │
│             选项动态加载自 GET /api/v1/algorithm/options                  │
│             （翻译 / ASR / 声纹识别 / TTS / ...，enum 化取值）             │
│                                                                          │
│  API元数据:  [JSON编辑器...]                                              │
│                                                                          │
│  默认最大进程数: [5]                                                      │
│  默认最大超时时间: [30] 秒                                                │
│  默认最大音频时长: [60] 秒                                                │
│                                                                          │
│  API端点配置:                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 端点1: [名称] [URL] [最大进程] [超时] [优先级]                       │ │
│  │ [+ 添加端点]                                                        │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│                                [取消] [保存]                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据结构

### 3.1 后端模型（已落地，backend/models/models.py）

```python
class API(db.Model):
    __tablename__ = 'apis'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    vendor = Column(String(50), nullable=True)
    api_url = Column(String(512))
    description = Column(Text)
    status = Column(String(20), nullable=False, default='online')
    meta = Column(JSON, nullable=False)

    # 算法类型关联字段（已落地）
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')

    max_process = Column(Integer, nullable=False, default=5)
    max_timeout = Column(Integer, nullable=False, default=30)
    max_audio_duration = Column(Integer, nullable=False, default=60)
    health_score = Column(Float, nullable=False, default=100.0)
    default_max_process = Column(Integer, nullable=False, default=5)
    default_max_timeout = Column(Integer, nullable=False, default=30)
    default_max_audio_duration = Column(Integer, nullable=False, default=60)
    api_endpoints = Column(JSON, nullable=False, default=list)
    # ... 其他现有字段
```

### 3.2 后端 Schema（已落地，backend/schemas/api.py）

`ApiItem` / `ApiCreateInput` / `ApiUpdateInput` 三个 Schema 均已包含 `algorithm_type` 字段，别名统一为 camelCase `algorithmType`（请求接收 camelCase，响应经 `success_response` 统一输出 camelCase）：

```python
# ApiItem (列表/详情) / ApiCreateInput (创建) / ApiUpdateInput (更新) 三个 Schema 均含：
algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
```

**列表接口按算法筛选（已落地，backend/controllers/api_controller.py）：**

```python
# GET /apis?algorithm_type=xxx
algorithm_type = request.args.get('algorithm_type')
if algorithm_type:
    query = query.filter_by(algorithm_type=algorithm_type)
```

> 命名约定：`algorithm_type`（snake_case）仅存在于后端模型与 Controller 查询参数；前端各层只读写 camelCase `algorithmType`。查询参数名 `algorithm_type` 属于后端 HTTP 契约，由 Infrastructure api 层封装调用。

### 3.3 前端数据结构（已落地，frontend/src/views/DeviceLogic/device.ts）

> 原方案指向 `frontend/src/shared/types.ts`，该文件不存在；API 设备类型实际定义于 `views/DeviceLogic/device.ts` 的 `APIDevice` 接口。

```typescript
interface APIDevice {
  id: string | number;
  name: string;
  vendor?: string;
  apiUrl?: string;
  description?: string;
  status: 'online' | 'offline' | 'testing';   // 服务状态枚举
  meta: Record<string, any>;

  // 算法类型关联字段（已落地；当前同时保留双命名兼容字段，见下方待收敛说明）
  algorithm_type?: string;
  algorithmType?: string;

  defaultMaxProcess?: number;
  defaultMaxTimeout?: number;
  defaultMaxAudioDuration?: number;
  healthScore?: number;
  endpoints?: ApiEndpoint[];
}
```

> ⚠️ **待收敛点（分层纪律）**：`APIDevice` 当前同时声明 `algorithm_type` 与 `algorithmType` 双字段兜底，属过渡实现。按 DDD 分层约定，Presentation/Application 层应只保留 camelCase `algorithmType`，snake_case 兼容应由 Infrastructure 的 dto/adapter 层完成收敛（对齐 Device 的 `supportedAlgorithms` 已收敛后的形态）。

---

## 4. 核心交互逻辑

### 4.1 算法类型筛选（已落地，frontend/src/views/DeviceLogic/device.ts）

```typescript
// 算法类型筛选状态（'all' 为哨兵值，非魔法字符串拼接）
const algorithmTypeFilter = ref('all');

const allFilteredAPIDevices = computed(() => {
  return apiDevices.value.filter(device => {
    if (!device) return false;
    const matchesSearch = !searchQuery.value ||
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.category && device.category.toLowerCase().includes(searchQuery.value.toLowerCase()));
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    // 已落地: 算法类型匹配（当前为双命名兜底写法，待收敛为仅 algorithmType）
    const matchesAlgorithmType = algorithmTypeFilter.value === 'all' ||
      (device as any).algorithm_type === algorithmTypeFilter.value ||
      (device as any).algorithmType === algorithmTypeFilter.value;
    return matchesSearch && matchesStatus && matchesAlgorithmType;
  });
});
```

> 除前端内存筛选外，后端 `GET /apis?algorithm_type=xxx`（`query.filter_by(algorithm_type=...)`）已落地，供服务端筛选使用。

### 4.2 表单字段配置（已落地，frontend/src/utils/utils.ts）

`generateDeviceFields('api')` 已注入算法类型字段，选项动态加载：

```typescript
case 'api':
  // ... 现有字段（name / vendor / apiUrl 等）...
  return [...apiBaseFields, /* ... */, {
    key: 'algorithmType',          // 已落地
    label: '算法类型',
    type: 'select',
    required: false,
    placeholder: '请选择算法类型',
    hint: '选择API对应的算法类型，用于筛选和分类',
    options: [],                   // 动态加载
    action: 'loadAlgorithmTypes'   // 触发 CRUDFormModal 动态加载选项
  }, /* ... */];
```

### 4.3 API卡片显示算法类型（已落地，Device.vue 模板）

API 卡片以 meta 文本形式显示算法类型（区别于测试设备卡片使用的 `AlgorithmTag` 标签组件）：

```vue
<!-- API卡片 meta 区域（已落地） -->
<span class="meta-item" v-if="device.algorithmType || device.algorithm_type">
  <i class="fas fa-microchip"></i>
  {{ getAlgorithmTypeName(device.algorithmType || device.algorithm_type) }}
</span>
```

`getAlgorithmTypeName(algorithmType)` 由 `device.ts` 提供：从 `algorithmTypeOptions`（选项缓存）中按 `value` 匹配返回 `label`，未匹配时回退显示原值。

> ⚠️ **待收敛点**：卡片模板中 `device.algorithmType || device.algorithm_type` 为双命名兜底，应收敛为仅 `device.algorithmType`（由 Infrastructure 适配层保证 camelCase）。

### 4.4 算法类型选项加载（已落地）

选项统一来源于算法配置管理的选项接口 `GET /api/v1/algorithm/options`，当前存在两处加载实现：

| 位置 | 触发方式 | 说明 |
|------|---------|------|
| `components/common/modal/CRUDFormModal.vue`（`loadAlgorithmTypes()`） | 表单字段 `action === 'loadAlgorithmTypes'` | 为弹窗内 `select` 字段填充 `dynamicFieldOptions.algorithmTypes` |
| `views/DeviceLogic/device.ts`（`loadAlgorithmTypeOptions()`） | 页面挂载时 | 为筛选下拉与卡片文案翻译填充 `algorithmTypeOptions` |

两处均解析 `result.data.algorithms`，映射为 `{ value, label }` 选项结构。

> ⚠️ **待收敛点**：两处当前均使用原生 `fetch('/api/v1/algorithm/options')` 直接调用，未走 Infrastructure 的 api 层封装（如 `algorithmApi.getOptions()`，与 `useAlgorithmLabels()` 复用同一出口），存在重复实现与分层泄漏；建议统一收敛到 api 层出口。

---

## 5. 实施清单

### 5.1 后端实施（已完成）

- [x] API 模型增加 `algorithm_type` 字段（`backend/models/models.py`，JSON 注释枚举取值 translation/asr/speaker_recognition/tts 等）
- [x] API Schema 增加 `algorithm_type` 字段（`ApiItem` / `ApiCreateInput` / `ApiUpdateInput` 三个 Schema，别名 `algorithmType`）
- [x] API 列表接口支持 `algorithm_type` 筛选参数（`GET /apis?algorithm_type=xxx`）
- [x] 数据库迁移：未单独维护迁移脚本（字段已在模型层生效；存量环境需自行执行 ALTER TABLE 或重建库）

### 5.2 前端实施（已完成）

- [x] `generateDeviceFields('api')` 增加算法类型选择字段（`algorithmType` select，`action: 'loadAlgorithmTypes'`）
- [x] CRUDFormModal 支持 `loadAlgorithmTypes` action 动态加载选项
- [x] Device.vue API筛选器增加算法类型下拉（`algorithmTypeFilter`，选项 `algorithmTypeOptions`）
- [x] Device.vue API卡片显示算法类型（`getAlgorithmTypeName` 文案翻译）
- [x] device.ts 增加 `algorithmTypeFilter` 状态和筛选逻辑（`allFilteredAPIDevices`）
- [x] 加载算法类型选项列表（页面挂载 `loadAlgorithmTypeOptions()`）

### 5.3 测试验证

- [x] API 列表显示算法类型测试
- [x] 算法类型筛选测试（前端筛选与后端 `algorithm_type` 参数筛选）
- [x] 新增 API 选择算法类型测试（camelCase 提交 → 后端 Schema 接收 → snake_case 落库）
- [x] 编辑 API 修改算法类型测试

---

## 6. 改动文件清单

### 6.1 后端文件（已实施）

| 文件路径 | 改动内容 |
|---------|---------|
| `backend/models/models.py` | API 模型增加 `algorithm_type` 字段 |
| `backend/schemas/api.py` | `ApiItem` / `ApiCreateInput` / `ApiUpdateInput` 增加 `algorithm_type` 字段（别名 `algorithmType`） |
| `backend/controllers/api_controller.py` | `get_all` 支持 `algorithm_type` 筛选；`ApiItem` 序列化输出 `algorithm_type` |

### 6.2 前端文件（已实施）

| 文件路径 | 改动内容 |
|---------|---------|
| `frontend/src/utils/utils.ts` | `generateDeviceFields('api')` 增加 `algorithmType` select 字段 |
| `frontend/src/components/common/modal/CRUDFormModal.vue` | `loadAlgorithmTypes()` 处理动态选项加载（`GET /api/v1/algorithm/options`） |
| `frontend/src/views/Device.vue` | API 筛选器增加算法类型下拉；卡片 meta 显示算法类型 |
| `frontend/src/views/DeviceLogic/device.ts` | `APIDevice` 接口含算法类型字段；`algorithmTypeFilter` 状态；`allFilteredAPIDevices` 筛选逻辑；`algorithmTypeOptions` 选项缓存；`getAlgorithmTypeName()` 文案翻译；`loadAlgorithmTypeOptions()` 选项加载 |

---

## 7. 注意事项

1. **分层命名纪律（待收敛）**：`algorithm_type`（snake_case）应仅存在于后端模型与 HTTP 查询参数契约；前端当前在 `device.ts`（`allFilteredAPIDevices`、`APIDevice` 接口）与 `Device.vue` 卡片模板中保留了 `algorithm_type` 双命名兜底，属过渡实现，应收敛为仅 camelCase `algorithmType`，由 Infrastructure dto/adapter 层完成 snake_case ↔ camelCase 转换（对齐 Device `supportedAlgorithms` 的收敛形态）
2. **选项加载统一出口**：算法类型选项应以 `GET /api/v1/algorithm/options` 为唯一数据源，经 Infrastructure api 层封装（`algorithmApi.getOptions()`）调用，避免 `CRUDFormModal` 与 `device.ts` 各自原生 `fetch` 的重复实现；取值为枚举（translation/asr/speaker_recognition/tts 等），不引入魔法字符串
3. **与测试设备卡片的一致性**：API 卡片当前用 meta 文本展示算法类型，测试设备卡片使用 `AlgorithmTag` 标签组件；若需视觉统一，可复用 `AlgorithmTag`（单元素传入）而非新增页面级实现
4. **向后兼容**：`algorithm_type` 为可空字段，存量 API 数据不受影响；Schema 双命名兼容保障新旧前端版本交互
