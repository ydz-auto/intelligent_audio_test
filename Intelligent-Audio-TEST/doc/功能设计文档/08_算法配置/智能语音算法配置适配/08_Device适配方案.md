# Device - 设备管理页面适配方案

## 1. 页面概述

### 1.1 页面定位
Device 页面用于管理测试设备（测试设备、测试API、播放设备），需要适配算法配置化方案，增加设备算法兼容性管理功能。

### 1.2 页面路由
- 路由路径：`/Device`
- 菜单位置：系统设置 > 设备管理

### 1.3 现有实现分析

**现有布局特点：**
- 采用 Tab 切换三种设备类型：测试设备、测试API、播放设备
- 使用卡片式网格布局展示设备列表
- 已有搜索框、状态筛选、类型筛选功能
- 设备卡片包含：设备名称、型号、状态、规格参数、操作按钮

**适配原则：**
- 保持现有卡片式布局不变
- 在卡片中增加算法兼容性标签显示
- 在现有筛选器旁边增加算法类型筛选
- 在现有编辑弹窗中增加算法选择区域

### 1.4 核心改动

| 改动项 | 改动类型 | 说明 |
|-------|---------|------|
| 设备卡片 | 改造 | 增加算法兼容性标签显示 |
| 筛选器 | 改造 | 增加算法类型筛选下拉 |
| 编辑弹窗 | 改造 | 增加算法选择 |
| Device模型 | 扩展 | 增加 supported_algorithms 字段 |

---

## 2. 页面布局（基于现有实现调整）

### 2.1 设备列表页面（保持现有布局 + 增强）

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
│  │    12    │ │    8     │ │    3     │ │    1    │                   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘                   │
│                                                                          │
│  筛选器:                                                                 │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────────────┐              │
│  │ 搜索设备名称  │  │ 状态 ▼   │  │ 支持算法: [全部 ▼]    │ ← 新增      │
│  └──────────────┘  └──────────┘  └──────────────────────┘              │
│                                                                          │
│  设备卡片网格: (保持现有卡片布局，增加算法标签)                            │
│  ┌────────────────────────┐  ┌────────────────────────┐                │
│  │ ☑ Android-01          │  │ ☑ iPhone-12           │                │
│  │ ──────────────────────│  │ ──────────────────────│                │
│  │ Pixel 6 Pro           │  │ iPhone 14             │                │
│  │                       │  │                       │                │
│  │ 支持算法: ← 新增       │  │ 支持算法: ← 新增       │                │
│  │ [翻译] [ASR] [声纹]    │  │ [ASR] [TTS]           │                │
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

### 2.2 设备卡片增强（新增算法标签区域）

```
┌────────────────────────────────────────┐
│ ☑ 设备名称                             │
│ ────────────────────────────────────   │
│ 设备型号                               │
│                                        │
│ 支持算法: ← 新增区域                    │
│ ┌──────┐ ┌──────┐ ┌──────┐            │
│ │ 翻译 │ │ ASR  │ │ 声纹 │            │
│ └──────┘ └──────┘ └──────┘            │
│                                        │
│ 固件版本: xxx                          │
│ 最后在线: xxx                          │
│ 测试延迟: xxx                          │
│ ...                                    │
│                                        │
│ ● 状态                                 │
│ [编辑] [删除] [测试] [健康检查]         │
└────────────────────────────────────────┘
```

### 2.3 编辑设备弹窗（在现有弹窗基础上扩展）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  编辑设备                                                                │
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
│  ────────────────────────────────────────────────────────────────────   │
│  支持算法: (新增区域)                                                    │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  [✓ 翻译]  [✓ ASR]  [✓ 声纹识别]  [☐ TTS]                         │ │
│  │                                                                    │ │
│  │  注: 勾选表示该设备支持此算法类型                                    │ │
│  └─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│                                [取消] [保存]                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据结构

### 3.1 Device 模型扩展（基于现有模型）

**现有模型字段（backend/models/models.py）：**
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
```

**新增字段：**
```python
class Device(db.Model):
    # ... 现有字段保持不变 ...
    
    # 新增字段
    supported_algorithms = Column(JSON, default=list, comment='支持的算法类型列表')
```

### 3.2 前端数据结构

```typescript
interface Device {
  id: string | number;
  name: string;
  model: string;
  type: string;
  system: string;
  system_version: string;
  app_name: string;
  app_version: string;
  serial_number: string;
  ip: string;
  status: 'online' | 'offline' | 'testing' | 'busy' | 'error';
  
  // 新增字段
  supported_algorithms?: string[];  // 支持的算法类型列表，如: ['translation', 'asr', 'speaker_recognition']
}
```

### 3.3 表单数据结构

```typescript
interface DeviceFormData {
  id?: string | number;
  name: string;
  model: string;
  type: string;
  system: string;
  system_version: string;
  app_name: string;
  app_version: string;
  serial_number: string;
  ip: string;
  
  // 新增字段
  supported_algorithms: string[];
}
```

---

## 4. 核心交互逻辑

### 4.1 算法兼容性选择

```typescript
const handleAlgorithmToggle = (algorithmType: string) => {
  const index = formData.value.supported_algorithms.indexOf(algorithmType);
  
  if (index > -1) {
    // 取消选择
    formData.value.supported_algorithms.splice(index, 1);
  } else {
    // 添加选择
    formData.value.supported_algorithms.push(algorithmType);
  }
};
```


### 4.2 设备筛选（增强现有筛选逻辑）

```typescript
const allFilteredTestDevices = computed(() => {
  return testDevices.value.filter(device => {
    if (!device) return false;
    
    // 现有筛选逻辑
    const matchesSearch = !searchQuery.value || 
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) || 
      (device.model && device.model.toLowerCase().includes(searchQuery.value.toLowerCase()));
    
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    
    // 新增: 算法类型筛选
    const matchesAlgorithm = algorithmFilter.value === 'all' || 
      (device.supported_algorithms && device.supported_algorithms.includes(algorithmFilter.value));
    
    return matchesSearch && matchesStatus && matchesAlgorithm;
  });
});
```

---

## 5. 组件设计

### 5.1 组件结构（基于现有结构调整）

```
Device.vue                          # 主页面（保持现有结构）
├── DeviceLogic/
│   └── device.ts                   # 业务逻辑（改造：增加算法筛选和配置逻辑）
├── composables/
│   └── useDeviceManagement.ts      # 设备管理组合函数（改造：增加算法配置字段）
└── 全局模态窗组件（由 ModalManager 统一管理）
    ├── AddDeviceModal              # 添加设备弹窗（改造：增加算法选择区域）
    ├── EditDeviceModal             # 编辑设备弹窗（改造：增加算法选择区域）
    └── ScanDevicesModal.vue        # 扫描设备弹窗（保持现有）
```

**说明：** 现有模态窗采用全局模态窗管理器模式，通过 `useModalControl()` 获取全局单例实例，所有页面共享同一个模态窗管理器。改造时需要修改对应的模态窗组件和 `generateDeviceFields()` 函数。

### 5.2 AlgorithmTag 组件（新增）

```vue
<template>
  <div class="algorithm-tags">
    <span 
      v-for="algo in algorithms" 
      :key="algo" 
      class="algorithm-tag"
      :class="`algorithm-tag--${algo}`"
    >
      {{ algorithmLabels[algo] || algo }}
    </span>
    <span v-if="!algorithms || algorithms.length === 0" class="algorithm-tag algorithm-tag--none">
      未配置
    </span>
  </div>
</template>

<script setup>
const algorithmLabels = {
  'translation': '翻译',
  'asr': 'ASR',
  'speaker_recognition': '声纹',
  'tts': 'TTS'
};

defineProps({
  algorithms: {
    type: Array,
    default: () => []
  }
});
</script>
```

### 5.3 设备卡片改造（Device.vue 模板部分）

```vue
<!-- 在现有设备卡片中增加算法标签区域 -->
<div class="device-card-content">
  <div class="device-info">
    <h3 class="device-name">{{ device.name }}</h3>
    <p class="device-model">{{ device.model }}</p>
    
    <!-- 新增: 支持算法标签 -->
    <div class="device-algorithms" v-if="device.supported_algorithms?.length">
      <span class="algo-label">支持算法:</span>
      <AlgorithmTag :algorithms="device.supported_algorithms" />
    </div>
    
    <!-- 现有元数据 -->
    <div class="device-meta">
      <!-- ... -->
    </div>
  </div>
  <!-- ... -->
</div>
```

---

## 6. 实施清单

### 6.1 后端实施

| 序号 | 任务 | 优先级 | 说明 |
|-----|------|-------|------|
| 1 | Device 模型增加 supported_algorithms 字段 | 高 | JSON 类型，存储算法类型列表 |
| 2 | 修改设备创建/更新接口 | 高 | 支持新增字段的读写 |
| 3 | 新增设备按算法筛选接口参数 | 中 | GET /devices?algorithm_type=xxx |

### 6.2 前端实施

| 序号 | 任务 | 优先级 | 说明 |
|-----|------|-------|------|
| 1 | 创建 AlgorithmTag.vue 组件 | 高 | 算法标签显示组件 |
| 2 | 改造 Device.vue 卡片模板 | 高 | 增加算法标签显示区域 |
| 3 | 改造 device.ts 筛选逻辑 | 高 | 增加算法类型筛选 |
| 4 | 增加算法筛选下拉框 | 中 | 在筛选器区域增加算法筛选 |

### 6.3 测试验证

| 序号 | 测试项 | 说明 |
|-----|-------|------|
| 1 | 设备卡片算法标签显示 | 验证标签正确显示 |
| 2 | 算法筛选功能 | 验证筛选结果正确 |
| 3 | 新增设备算法配置 | 验证保存和读取正确 |
| 4 | 编辑设备算法配置 | 验证修改和保存正确 |


---

## 7. 注意事项

1. **向后兼容**：现有设备数据 `supported_algorithms` 默认为空数组，不影响现有功能
2. **渐进式改造**：先完成显示和筛选，再完成编辑配置
3. **组件复用**：算法选择组件应复用其他页面已实现的组件
4. **数据迁移**：无需数据迁移，新字段使用默认值
