# Device - 设备管理页面适配方案

> **落地状态说明**：本方案所述的设备算法兼容性能力（`Device.supportedAlgorithms` 字段、设备卡片算法标签、算法类型筛选、编辑弹窗算法选择）**已在前后端全面落地**。本文档已按当前代码库实际实现（`backend/models/models.py`、`backend/schemas/device.py`、`frontend/src/views/Device.vue`、`frontend/src/views/DeviceLogic/device.ts`、`frontend/src/components/algorithm/AlgorithmTag.vue` 等）对齐修订。

## 1. 页面概述

### 1.1 页面定位

Device 页面用于管理测试设备（测试设备、测试API、播放设备），承载智能语音算法配置化方案中的**设备算法兼容性管理**：声明每台设备支持的算法类型（`supportedAlgorithms`），供测试执行时按被测设备 `device_type` 路由三执行器（物理设备→E2EExecutor、HTTP API→APISessionExecutor、WebSocket API→RealtimeSessionExecutor）前的设备选择与筛选使用。

### 1.2 页面路由
- 路由路径：`/Device`
- 菜单位置：系统设置 > 设备管理

### 1.3 现有实现分析

**现有布局特点：**
- 采用 Tab 切换三种设备类型：测试设备、测试API、播放设备
- 使用卡片式网格布局展示设备列表
- 已有搜索框、状态筛选、类型筛选功能；测试设备 Tab 下已增加**算法类型筛选下拉**（`algorithmFilter`）
- 设备卡片包含：设备名称、型号、状态、规格参数、操作按钮；测试设备与 API 设备卡片均已展示**算法兼容性标签**（`AlgorithmTag`）

**适配结果（已落地）：**
- 保持现有卡片式布局不变
- 卡片中已增加算法兼容性标签显示（两处卡片模板均接入 `AlgorithmTag`，`:max-display="3"`）
- 筛选器区域已增加算法类型筛选下拉（选项："支持算法: 全部" + 各算法类型）
- 编辑/添加弹窗（动态表单）已增加算法选择字段（`FormField type='algorithmSelect'`）

### 1.4 核心改动

| 改动项 | 改动类型 | 状态 | 说明 |
|-------|---------|------|------|
| 设备卡片 | 改造 | ✅ 已落地 | 接入 `AlgorithmTag` 组件展示算法兼容性标签 |
| 筛选器 | 改造 | ✅ 已落地 | 测试设备 Tab 增加 `algorithmFilter` 算法类型筛选 |
| 编辑弹窗 | 改造 | ✅ 已落地 | `generateDeviceFields()` 注入 `algorithmSelect` 类型字段 |
| Device模型 | 扩展 | ✅ 已落地 | 后端新增 `supported_algorithms` JSON 字段，前端以 camelCase `supportedAlgorithms` 读写 |

---

## 2. 页面布局（基于现有实现）

### 2.1 设备列表页面（保持现有布局 + 已增强）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  设备管理                                                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [添加测试设备]  [扫描设备]  [批量操作▼]  [导入/导出▼]                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ [测试设备管理] [测试API管理] [播放设备管理]    ← Tab切换           │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  状态概览:                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│  │ 总设备数  │ │ 在线设备  │ │ 离线设备  │ │ 测试中   │                   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘                   │
│                                                                          │
│  筛选器:                                                                 │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────────────┐              │
│  │ 搜索设备名称  │  │ 状态 ▼   │  │ 支持算法: [全部 ▼]    │ ← 已落地     │
│  └──────────────┘  └──────────┘  └──────────────────────┘              │
│                                                                          │
│  设备卡片网格: (保持现有卡片布局，已增加算法标签)                          │
│  ┌────────────────────────┐  ┌────────────────────────┐                │
│  │ ☑ Android-01          │  │ ☑ iPhone-12           │                │
│  │ ──────────────────────│  │ ──────────────────────│                │
│  │ Pixel 6 Pro           │  │ iPhone 14             │                │
│  │                       │  │                       │                │
│  │ 支持算法: ← 已落地     │  │ 支持算法: ← 已落地     │                │
│  │ [翻译] [ASR] [声纹] +N │  │ [ASR] [TTS]          │                │
│  │                       │  │                       │                │
│  │ 固件版本: 13.0        │  │ 固件版本: 16.5        │                │
│  │ 最后在线: 2分钟前      │  │ 最后在线: 5分钟前      │                │
│  │                       │  │                       │                │
│  │ ● 在线                │  │ ● 在线                │                │
│  │ [编辑] [删除] [测试]   │  │ [编辑] [删除] [测试]   │                │
│  └────────────────────────┘  └────────────────────────┘                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 设备卡片增强（已落地：算法标签区域）

```
┌────────────────────────────────────────┐
│ ☑ 设备名称                             │
│ ────────────────────────────────────   │
│ 设备型号                               │
│                                        │
│ 支持算法: ← 已落地（AlgorithmTag）      │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌─────┐    │
│ │ 翻译 │ │ ASR  │ │ 声纹 │ │ +N  │    │
│ └──────┘ └──────┘ └──────┘ └─────┘    │
│  （:max-display="3"，超出折叠为 +N）    │
│                                        │
│ 固件版本: xxx                          │
│ 最后在线: xxx                          │
│ ...                                    │
│                                        │
│ ● 状态                                 │
│ [编辑] [删除] [测试] [健康检查]         │
└────────────────────────────────────────┘
```

### 2.3 编辑设备弹窗（已落地：动态表单 + 算法选择字段）

> **实现说明**：设备添加/编辑弹窗为**全局动态表单弹窗**（`modalManager.open(MODAL_TYPES.ADD_DEVICE / EDIT_DEVICE, ...)`），表单字段由 `generateDeviceFields(targetType)` 统一生成，不存在独立的设备编辑弹窗组件。算法选择以 `FormField type='algorithmSelect'` 类型字段注入，渲染为**单选下拉**（设备与算法类型为多对一时，设备侧维护单值即可满足当前筛选与路由场景）。

```
┌─────────────────────────────────────────────────────────────────────────┐
│  编辑设备（动态表单弹窗）                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  设备名称:   [Pixel 6 Pro________]                                       │
│  设备型号:   [Pixel 6 Pro________]                                       │
│  操作系统:   [Android ▼]                                                │
│  系统版本:   [13.0______________]                                        │
│  应用名称:   [Default App________]                                       │
│  应用版本:   [1.0.0_____________]                                        │
│  序列号:     [MOCK-ADB-123456____]                                       │
│  IP地址:     [192.168.1.100______]                                       │
│                                                                          │
│  算法类型:   [翻译 ▼]   ← 已落地：FormField type='algorithmSelect'       │
│             （单选下拉，选项来自算法配置；可为空）                        │
│                                                                          │
│                                [取消] [保存]                              │
└─────────────────────────────────────────────────────────────────────────┘
```

> 若需要"勾选多个算法并为每个算法配置默认参数"，应复用 **AlgorithmParamsConfig** 组件（`components/algorithm/AlgorithmParamsConfig.vue`，见 07 号文档关联章节）：其 Props 为 `supportedAlgorithms?: string[]` 与 `algorithmConfigs?: Record<string, AlgorithmConfig>`，通过 `FormField type='algorithmConfigs'` 分支承载。当前设备编辑弹窗仅使用 `algorithmSelect` 单选。

---

## 3. 数据结构

### 3.1 后端 Device 模型（已落地）

**backend/models/models.py：**
```python
class Device(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)      # phone/tablet
    system = Column(String(50), nullable=False)    # Android/iOS/HarmonyOS
    system_version = Column(String(20))
    app_name = Column(String(100))
    app_version = Column(String(20))
    serial_number = Column(String(100))
    ip = Column(String(50))
    status = Column(String(20))
    # ... 其他字段

    # 算法兼容性字段（已落地）
    supported_algorithms = Column(JSON, default=list, comment='支持的算法类型列表')
```

**Pydantic Schema 双命名兼容（backend/schemas/device.py，已落地）：**

DeviceCreate / DeviceUpdate / DeviceItem 三个 Schema 均通过 `AliasChoices` 同时接受 camelCase 与 snake_case 写入，序列化输出为 snake_case，由 Infrastructure 的 dto/adapter 层转换为前端使用的 camelCase：

```python
supported_algorithms: Optional[List[str]] = Field(
    None,
    validation_alias=AliasChoices('supportedAlgorithms', 'supported_algorithms')
)
```

**按算法筛选接口（已落地，backend/controllers/device_controller.py）：**

```python
# GET /devices?algorithm_type=xxx
query = query.filter(Device.supported_algorithms.contains([algorithm_type]))
```

> 命名约定：后端唯一知道 snake_case（`supported_algorithms`），前端各层只见 camelCase（`supportedAlgorithms`）。严禁在 Presentation/Application 层出现 snake_case 字段。

### 3.2 前端数据结构（camelCase，已落地）

**frontend/src/views/DeviceLogic/device.ts：**
```typescript
interface TestDevice {
  id: string | number;
  name: string;
  model: string;
  type: string;
  system: string;
  systemVersion: string;
  appName: string;
  appVersion: string;
  serialNumber: string;
  ip: string;
  status: 'online' | 'offline';   // 设备在线状态枚举

  // 算法兼容性字段（已落地）
  supportedAlgorithms?: string[];  // 支持的算法类型列表，如: ['translation', 'asr', 'speaker_recognition']
}

// API 设备类型同样带有算法标记（已落地，双命名兼容由适配层收敛为 camelCase）
interface APIDevice {
  // ...
  algorithmType?: string;
}
```

> 状态枚举化：设备状态为有限枚举（online/offline 等），筛选判断使用 `'all'` 哨兵值，不引入魔法字符串拼接。

### 3.3 表单数据结构

设备添加/编辑弹窗不定义独立的 `DeviceFormData` 接口，而是复用动态表单 formData：`generateDeviceFields(targetType)` 生成的字段集合 + FormField 通用初始化/校验机制。算法选择字段的初始值由 `FormField.getInitialValue()` 归一（`algorithmSelect` 为数组单值，提交时取 `val[0]`）。提交时 `onConfirm` 将表单 data 直接传给 `devicesApi.update/create`，字段经 Infrastructure api 层与后端 `AliasChoices` 双向兼容。

---

## 4. 核心交互逻辑

### 4.1 算法选择（已落地：由 FormField/AlgorithmParamsConfig 承担，非页面内联函数）

算法勾选逻辑不再散落在页面中，统一收敛到表单组件层：

- `FormField type='algorithmSelect'`（设备编辑弹窗）：单选下拉，数据源为 `useAlgorithmConfig().algorithms`（Application 层 composable，缓存算法 ReadModel）；
- `FormField type='algorithmConfigs'`（如需多选+按算法配置参数）：承载 `AlgorithmParamsConfig`，通过 `v-model:supported-algorithms` 与 `v-model:algorithm-configs` 双向绑定，勾选/取消逻辑由组件内部维护（`AlgorithmConfig = { enabled, default_params, notes }`）。

### 4.2 设备筛选（已落地，frontend/src/views/DeviceLogic/device.ts）

```typescript
const algorithmFilter = ref('all');

const allFilteredTestDevices = computed(() => {
  return testDevices.value.filter(device => {
    if (!device) return false;

    // 现有筛选逻辑
    const matchesSearch = !searchQuery.value ||
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase()));

    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;

    // 已落地: 算法类型筛选
    const matchesAlgorithm = algorithmFilter.value === 'all' ||
      (device.supportedAlgorithms && device.supportedAlgorithms.includes(algorithmFilter.value));

    return matchesSearch && matchesStatus && matchesAlgorithm;
  });
});
```

> 除前端内存筛选外，后端 `GET /devices?algorithm_type=xxx`（`Device.supported_algorithms.contains`）也已落地，供列表接口服务端筛选使用。

---

## 5. 组件设计

### 5.1 组件结构（基于现有结构）

```
Device.vue                          # 主页面（保持现有结构，已接入 AlgorithmTag 与算法筛选）
├── DeviceLogic/
│   └── device.ts                   # 业务逻辑（已改造：supportedAlgorithms 字段 + algorithmFilter 筛选）
├── composables/
│   └── useDeviceManagement.ts      # 设备管理组合函数（Application 层：modalManager.open + generateDeviceFields 注入算法字段）
├── utils/
│   └── utils.ts                    # generateDeviceFields()：已注入 { key: 'supportedAlgorithms', type: 'algorithmSelect' } 字段
├── components/
│   ├── algorithm/
│   │   ├── AlgorithmTag.vue        # 算法标签组件（已落地，见 5.2）
│   │   └── AlgorithmParamsConfig.vue  # 多算法勾选+参数配置（FormField algorithmConfigs 分支承载，按需复用）
│   └── common/form/
│       └── FormField.vue           # 动态表单字段：algorithmSelect / algorithmConfigs 双分支
└── 全局模态窗（ModalManager 动态表单弹窗，无独立设备弹窗组件）
    └── MODAL_TYPES.ADD_DEVICE / EDIT_DEVICE
        fields: generateDeviceFields(targetType)   # 已含算法选择字段
```

**说明：** 现有模态窗采用全局模态窗管理器模式，通过 `useModalControl()` 获取全局单例实例，所有页面共享同一个模态窗管理器。`useDeviceManagement.addDevice()/editDevice()` 以 `modalManager.open(...)` 携带 `fields` 打开弹窗，算法字段随 `generateDeviceFields()` 自动注入，无需修改弹窗组件本身。

### 5.2 AlgorithmTag 组件（已落地，`components/algorithm/AlgorithmTag.vue`）

已落地实现比原设计稿增强，关键点：

- **Props**：`algorithms?: string[]`、`maxDisplay?: number`（默认 4，设备卡片传 3）、`showMore?: boolean`（默认 true）；
- **标签文案后端优先**：优先经 `useAlgorithmLabels()`（Application 层 composable，模块级单例 + `loadingPromise` 防重入）调用 `algorithmApi.getOptions()`（`GET /api/v1/algorithm/options`）获取算法 label，避免魔法字符串硬编码；仅在接口未就绪时 fallback 到内置 `DEFAULT_ALGORITHMS` 映射（translation/asr/speaker_recognition/tts/asr_eval 等）；
- **分类着色**：`getAlgorithmClass` 按算法类型归类着色（翻译/识别/声纹/合成等类别）；
- **超出折叠**：超过 `maxDisplay` 的算法折叠为 `+N` 提示（受 `showMore` 控制）；
- **空态占位**：`algorithms` 为空时显示"未配置"占位标签。

### 5.3 设备卡片接入（已落地，Device.vue 模板）

```vue
<!-- 设备卡片中已接入算法标签（测试设备与 API 设备两处卡片模板均接入） -->
<AlgorithmTag :algorithms="device.supportedAlgorithms" :max-display="3" />
```

筛选下拉（Device.vue）：

```vue
<!-- 算法类型筛选下拉，选项为"支持算法: 全部" + 各算法类型，v-model="algorithmFilter" -->
```

---

## 6. 实施清单

### 6.1 后端实施（已全部完成）

| 序号 | 任务 | 状态 | 说明 |
|-----|------|------|------|
| 1 | Device 模型增加 supported_algorithms 字段 | ✅ | JSON 类型，`models.py` 已落地，默认空列表 |
| 2 | 修改设备创建/更新接口 | ✅ | Create/Update/Item 三个 Schema 经 `AliasChoices` 支持双命名读写 |
| 3 | 新增设备按算法筛选接口参数 | ✅ | `GET /devices?algorithm_type=xxx`，`Device.supported_algorithms.contains([algorithm_type])` |

### 6.2 前端实施（已全部完成）

| 序号 | 任务 | 状态 | 说明 |
|-----|------|------|------|
| 1 | 创建 AlgorithmTag.vue 组件 | ✅ | `components/algorithm/AlgorithmTag.vue`，含 useAlgorithmLabels 后端优先文案 + 分类着色 + +N 折叠 |
| 2 | 改造 Device.vue 卡片模板 | ✅ | 两处设备卡片均接入 `<AlgorithmTag :algorithms="device.supportedAlgorithms" :max-display="3" />` |
| 3 | 改造 device.ts 筛选逻辑 | ✅ | `allFilteredTestDevices` 三条件筛选（搜索 + 状态 + 算法） |
| 4 | 增加算法筛选下拉框 | ✅ | 测试设备 Tab 筛选器区域 `algorithmFilter` 下拉 |
| 5 | 编辑弹窗算法选择字段 | ✅ | `generateDeviceFields()` 注入 `algorithmSelect` 字段，FormField 单选下拉分支 |

### 6.3 测试验证

| 序号 | 测试项 | 说明 |
|-----|-------|------|
| 1 | 设备卡片算法标签显示 | 验证标签正确显示（含 +N 折叠、未配置占位） |
| 2 | 算法筛选功能 | 验证前端筛选与后端 `algorithm_type` 参数筛选结果一致 |
| 3 | 新增设备算法配置 | 验证 camelCase 提交与后端 AliasChoices 接收、snake_case 落库 |
| 4 | 编辑设备算法配置 | 验证回显（后端 snake_case → 前端 camelCase）与保存 |

---

## 7. 注意事项

1. **向后兼容（已保障）**：`supported_algorithms` 默认空列表；后端 Schema 双命名兼容（`AliasChoices`），存量请求不受影响
2. **分层命名纪律**：`supported_algorithms`（snake_case）仅存在于 Infrastructure 层（后端模型/Schema/dto）；前端 views/components/composables 一律使用 `supportedAlgorithms`（camelCase），不得在 Presentation/Application 层出现 snake_case 兜底读取
3. **组件复用**：算法标签复用 `AlgorithmTag`，算法文案统一经 `useAlgorithmLabels()`（后端 options 接口优先），禁止新增页面级硬编码算法映射；多算法+参数配置场景复用 `AlgorithmParamsConfig`（经 `FormField type='algorithmConfigs'` 承载）
4. **数据迁移**：无需数据迁移，新字段使用默认值；算法类型取值以算法配置管理的枚举为准（enum 化，不引入魔法字符串）
