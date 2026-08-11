# API管理页面适配方案

## 1. 页面概述

### 1.1 页面定位
API管理页面用于管理测试API接口，位于设备管理页面的"测试API管理"Tab中，需要适配算法配置化方案，增加API与算法类型的关联。

### 1.2 页面路由
- 路由路径：`/Device`（设备管理页面 > 测试API管理 Tab）
- 菜单位置：设备管理

### 1.3 核心改动
- API卡片增加"算法类型"标签显示
- 新增/编辑API表单增加算法类型选择字段
- 筛选器增加算法类型下拉筛选

---

## 2. 页面布局（适配现有架构）

### 2.1 现有布局结构

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
│  │ 搜索名称或URL... │  │ 状态: [全部▼]│  │ 算法类型: [全部▼]│ ← 新增    │
│  └──────────────────┘  └──────────────┘  └──────────────────┘          │
│                                                                          │
│  API卡片网格:                                                            │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐ │
│  │ □ 翻译API-001      │  │ □ ASR-API-001      │  │ □ 声纹API-001      │ │
│  │ ● 在线             │  │ ● 在线             │  │ ○ 离线             │ │
│  │                    │  │                    │  │                    │ │
│  │ [翻译] ← 新增标签  │  │ [ASR] ← 新增标签   │  │ [声纹识别] ← 新增  │ │
│  │                    │  │                    │  │                    │ │
│  │ API版本: v1.0      │  │ API版本: v2.0      │  │ API版本: v1.2      │ │
│  │ 成功率: 99.5%      │  │ 成功率: 98.2%      │  │ 成功率: 95.0%      │ │
│  │                    │  │                    │  │                    │ │
│  │ [编辑] [删除] [健康检查] │ [编辑] [删除] [健康检查] │ [编辑] [删除] [健康检查] │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 新增/编辑API弹窗（适配现有表单）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  添加测试API / 编辑测试API                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  设备名称:   [__________________]                                         │
│  设备描述:   [__________________]                                         │
│  API名称:    [__________________]                                         │
│  供应商:     [__________________]  (如 volc_ast, ali, tencent)           │
│  Master入口URL: [__________________]                                      │
│                                                                          │
│  算法类型:   [请选择算法类型 ▼]        ← 新增字段                         │
│             选项: 翻译 / ASR / 声纹识别 / TTS / 全部                      │
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

### 3.1 后端模型扩展 (backend/models/models.py)

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
    
    # 新增字段
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    
    max_process = Column(Integer, nullable=False, default=5)
    max_timeout = Column(Integer, nullable=False, default=30)
    max_audio_duration = Column(Integer, nullable=False, default=60)
    health_score = Column(Float, nullable=False, default=100.0)
    api_endpoints = Column(JSON, nullable=False, default=list)
    # ... 其他现有字段
```

### 3.2 前端类型扩展 (frontend/src/shared/types.ts)

```typescript
interface APIConfig {
  id: string | number;
  name: string;
  vendor?: string;
  apiUrl?: string;
  description?: string;
  status: 'online' | 'offline' | 'testing';
  meta: Record<string, any>;
  
  // 新增字段
  algorithm_type?: string;  // 关联的算法类型
  
  defaultMaxProcess?: number;
  defaultMaxTimeout?: number;
  defaultMaxAudioDuration?: number;
  healthScore?: number;
  endpoints?: ApiEndpoint[];
}
```

### 3.3 Schema扩展 (backend/schemas/api.py)

```python
class ApiItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    vendor: Optional[str] = Field(None)
    api_url: str = Field(...)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # 新增字段
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    
    default_max_process: Optional[int] = Field(None)
    default_max_timeout: Optional[int] = Field(None)
    default_max_audio_duration: Optional[int] = Field(None)
    health_score: Optional[int] = Field(None)
    endpoints: List[ApiEndpointItem] = Field(default_factory=list)
```

---

## 4. 核心交互逻辑

### 4.1 算法类型筛选 (frontend/src/views/DeviceLogic/device.ts)

```typescript
// 新增算法类型筛选状态
const algorithmTypeFilter = ref('all');

// 修改 allFilteredAPIDevices 计算属性
const allFilteredAPIDevices = computed(() => {
  return apiDevices.value.filter(device => {
    if (!device) return false;
    
    // 搜索匹配
    const matchesSearch = !searchQuery.value || 
      (device.name && device.name.toLowerCase().includes(searchQuery.value.toLowerCase())) || 
      (device.vendor && device.vendor.toLowerCase().includes(searchQuery.value.toLowerCase()));
    
    // 状态匹配
    const matchesStatus = statusFilter.value === 'all' || device.status === statusFilter.value;
    
    // 算法类型匹配 (新增)
    const matchesAlgorithmType = algorithmTypeFilter.value === 'all' || 
      device.algorithm_type === algorithmTypeFilter.value;
    
    return matchesSearch && matchesStatus && matchesAlgorithmType;
  });
});
```

### 4.2 表单字段配置 (frontend/src/utils/utils.ts)

```typescript
case 'api':
  // ... 现有字段 ...
  
  return [...apiBaseFields, {
    key: 'name',
    label: 'API名称',
    type: 'text',
    required: true,
    placeholder: '请输入API名称'
  }, {
    key: 'algorithmType',  // 新增字段
    label: '算法类型',
    type: 'select',
    required: false,
    placeholder: '请选择算法类型',
    hint: '选择API对应的算法类型，用于筛选和分类',
    options: [],  // 动态加载
    action: 'loadAlgorithmTypes'  // 动态加载算法类型选项
  }, {
    // ... 其他现有字段 ...
  }];
```

### 4.3 API卡片显示算法类型标签

```vue
<!-- Device.vue API卡片区域增加算法类型标签 -->
<div class="device-meta">
  <span class="meta-item" v-if="device.algorithm_type">
    <i class="fas fa-microchip"></i>
    {{ getAlgorithmTypeName(device.algorithm_type) }}
  </span>
  <span class="meta-item">
    <i class="fas fa-tags"></i>
    {{ device.category }}
  </span>
  <!-- ... 其他现有meta项 ... -->
</div>
```

---

## 5. 实施清单

### 5.1 后端实施

- [ ] API 模型增加 `algorithm_type` 字段
- [ ] API Schema 增加 `algorithm_type` 字段
- [ ] API 列表接口支持 `algorithm_type` 筛选参数
- [ ] 数据库迁移脚本

### 5.2 前端实施

- [ ] `generateDeviceFields('api')` 增加算法类型选择字段
- [ ] Device.vue API筛选器增加算法类型下拉
- [ ] Device.vue API卡片显示算法类型标签
- [ ] device.ts 增加 `algorithmTypeFilter` 状态和筛选逻辑
- [ ] 加载算法类型选项列表

### 5.3 测试验证

- [ ] API 列表显示算法类型标签测试
- [ ] 算法类型筛选测试
- [ ] 新增 API 选择算法类型测试
- [ ] 编辑 API 修改算法类型测试

---

## 6. 改动文件清单

### 6.1 后端文件

| 文件路径 | 改动内容 |
|---------|---------|
| `backend/models/models.py` | API 模型增加 algorithm_type 字段 |
| `backend/schemas/api.py` | ApiItem 增加 algorithm_type 字段 |
| `backend/controllers/api_controller.py` | get_all 方法支持 algorithm_type 筛选 |

### 6.2 前端文件

| 文件路径 | 改动内容 |
|---------|---------|
| `frontend/src/utils/utils.ts` | generateDeviceFields 增加 algorithmType 字段 |
| `frontend/src/views/Device.vue` | 筛选器增加算法类型下拉，卡片显示算法类型标签 |
| `frontend/src/views/DeviceLogic/device.ts` | 增加 algorithmTypeFilter 状态和筛选逻辑 |
