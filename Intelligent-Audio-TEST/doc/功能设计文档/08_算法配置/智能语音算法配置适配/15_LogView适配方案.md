# LogView - 日志查看适配方案

## 1. 页面概述

### 1.1 页面定位
LogView 页面用于查看系统日志，需要适配算法配置化方案，增加按算法类型筛选日志的功能。

### 1.2 页面路由
- 路由路径：`/LogView`
- 菜单位置：系统管理 > 日志查看

### 1.3 核心改动
- 日志筛选器增加算法类型选项
- 日志表格增加算法类型列
- 日志详情显示算法类型

---

## 2. 现有实现分析

### 2.1 现有后端 Log 模型

```python
# backend/models/models.py
class Log(db.Model):
    __tablename__ = 'logs'
    id = Column(Integer, primary_key=True)
    time = Column(DateTime, nullable=False)
    level = Column(String(20), nullable=False)        # DEBUG/INFO/WARN/ERROR
    category = Column(String(50), nullable=False)     # System/Task/Device
    module = Column(String(100), nullable=False)      # 代码模块
    source = Column(String(100), nullable=False)      # 日志来源 (case/reference/device/api)
    content = Column(Text, nullable=False)            # 日志内容
    mark = Column(String(20))                         # 标记
    device_id = Column(Integer, ForeignKey('devices.id'))
    task_id = Column(Integer, ForeignKey('test_tasks.id'))
    test_case_id = Column(String(50), ForeignKey('test_cases.id'))
    api_id = Column(Integer, ForeignKey('apis.id'))
    thread_id = Column(String(50))
    created_at = Column(DateTime, default=utc8now)
    algorithm_type = Column(String(50))               # 关联算法类型
```

### 2.2 现有前端筛选器

| 筛选器 | 位置 | 选项 | 状态 |
|--------|------|------|------|
| 分类筛选 | 第一行 | 所有分类/系统日志/测试日志/错误日志 | ✅ |
| 模块筛选 | 第一行 | 所有模块/API模块/E2E测试/设备管理 | ✅ |
| 时间范围 | 第二行 | 开始时间 - 结束时间 | ✅ |
| 标记筛选 | 第二行 | 所有标记/黄色/红色/绿色/蓝色 | ✅ |
| 算法类型 | 第二行 | 全部/翻译/ASR/声纹识别/TTS | ✅ |
| 日志级别 | 第三行 | debug/info/warning/error (多选标签) | ✅ |
| 高级过滤 | 展开面板 | 设备ID/任务ID/用户ID/线程ID/内容包含/内容不包含 | ✅ |
| 来源筛选 | 第一行 | case/reference/device/api/全部 | ❌ 待实现 |

### 2.3 现有表格列

| 列名 | 宽度 | 说明 |
|------|------|------|
| 复选框 | 40px | 批量选择 |
| 展开 | 30px | 展开详情 |
| 时间 | 150px | 日志时间 |
| 级别 | 100px | DEBUG/INFO/WARNING/ERROR |
| 模块 | 120px | 代码模块 |
| 来源 | 120px | 日志来源 (case/reference/device/api) |
| 算法 | 100px | 算法类型标签 |
| 内容 | 自适应 | 日志正文 |
| 操作 | 200px | 标记/复制按钮 |

---

## 3. 适配方案

### 3.1 后端改动

#### 3.1.1 Log 模型扩展

在现有 Log 模型中增加 `algorithm_type` 字段：

```python
# backend/models/models.py
class Log(db.Model):
    # ... 现有字段 ...
    
    # 新增：关联算法类型
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
```

> **注意**: Log 模型中已有 `source` 字段，用于标识日志来源，可选值：case(用例)、reference(参考参数)、device(设备)、api(算法服务)、backend(后端)

#### 3.1.2 日志记录接口扩展

修改 `log_handler.py` 中的 `log_and_emit` 函数，支持传入 `algorithm_type`：

```python
# backend/utils/log_handler.py
def log_and_emit(level, module, content, category='system', source='backend', 
                 task_id=None, device_id=None, api_id=None, test_case_id=None,
                 algorithm_type=None,  # 新增参数
                 push_to_websocket=True, enable_console_log=None, **kwargs):
    # ...
    record.algorithm_type = algorithm_type
    # ...
```

#### 3.1.3 日志查询接口扩展

修改 `log_controller.py` 中的 `get_logs` 和 `get_stats` 方法，支持按算法类型筛选：

```python
# backend/controllers/log_controller.py
@staticmethod
def get_logs():
    # ... 现有参数 ...
    algorithm_type = request.args.get('algorithm_type')  # 新增
    
    query = Log.query
    # ... 现有筛选逻辑 ...
    
    if algorithm_type and algorithm_type != 'all':
        query = query.filter(Log.algorithm_type == algorithm_type)
```

#### 3.1.4 日志 Schema 扩展

```python
# backend/schemas/log.py
class LogItem(APIModel):
    # ... 现有字段 ...
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
```

---

### 3.2 前端改动

#### 3.2.1 筛选器改动

在现有筛选器中：
- **算法类型筛选**：✅ 已实现
- **来源筛选**：❌ 待实现

```
第一行：分类筛选 | 模块筛选 | [搜索内容...]
第二行：时间范围 | 标记筛选 | 算法类型: [全部 ▼] | [高级过滤] [清除过滤器]
```

**已实现 - 算法类型筛选器配置**：
```typescript
const LOGAlgorithmOptions = [
  { value: 'all', label: '全部算法' },
  { value: 'translation', label: '翻译' },
  { value: 'asr', label: 'ASR' },
  { value: 'speaker_recognition', label: '声纹识别' },
  { value: 'tts', label: 'TTS' }
];
```

#### 3.2.2 表格增加算法类型列

在"模块"列后面增加"算法"列：

| 列名 | 宽度 | 说明 |
|------|------|------|
| ... | ... | ... |
| 模块 | 120px | 代码模块 |
| **算法** | **100px** | **算法类型标签 (新增)** |
| 来源 | 120px | 日志来源 (case/reference/device/api) |
| ... | ... | ... |

**算法类型标签样式**：
```css
.log-algorithm {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.log-algorithm.translation { background: #e6f7ff; color: #1890ff; }
.log-algorithm.asr { background: #f6ffed; color: #52c41a; }
.log-algorithm.speaker_recognition { background: #fff7e6; color: #fa8c16; }
.log-algorithm.tts { background: #fff1f0; color: #f5222d; }
```

#### 3.2.3 日志详情扩展

在日志详情展开区域增加算法类型显示：

```html
<p><strong>算法类型:</strong> {{ log.algorithmType || '-' }}</p>
```

#### 3.2.4 类型定义扩展

```typescript
// frontend/src/shared/types/businessTypes.ts
export interface Log {
  id: number;
  level: string;
  module?: string;
  category?: string;
  source?: string;       // 日志来源: case/reference/device/api
  content: string;
  time?: string | number;
  timestamp?: string | number;
  createdAt: string;
  taskId?: number | string;
  deviceId?: number;
  threadId?: string | number;
  mark?: string;
  testCaseId?: string | number;
  algorithmType?: string;  // 新增
}

export interface LogFilters {
  startDateTime: string;
  endDateTime: string;
  logCategory: string;
  logModule: string;
  logSource: string;     // 新增：来源筛选
  markFilter: string;
  algorithmType: string;  // 新增
}
```

---

## 4. 页面布局（适配后）

### 4.1 日志列表 (当前实现)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  日志查看                                                                │
├─────────────────────────────────────────────────────────────────────────┤
│  筛选器:                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐          │
│  │ 分类:全部▼│  │ 模块:全部▼│  [搜索内容...] │          │
│  └──────────┘  └──────────┘  └──────────────┘          │
│                                                                          │
│  ┌────────────────────┐  ┌──────────┐  ┌──────────────┐                │
│  │ 时间范围: [至]     │  │ 标记:全部▼│  │ 算法:全部 ▼  │ ← 已实现      │
│  └────────────────────┘  └──────────┘  └──────────────┘                │
│                                                                          │
│  日志级别: [DEBUG] [INFO] [WARNING] [ERROR]                              │
│                                                                          │
│  日志列表:                                                               │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 时间        │ 级别  │ 模块   │ 算法    │ 来源  │ 内容              │ │
│  ├────────────────────────────────────────────────────────────────────┤ │
│  │ 10:30:01   │ INFO  │ TASK   │ [翻译]  │ api   │ 设备连接成功       │ │
│  │ 10:30:02   │ INFO  │ TASK   │ [翻译]  │ api   │ 开始执行翻译测试   │ │
│  │ 10:30:05   │ DEBUG │ ASR    │ [ASR]   │ api   │ ASR模型加载完成    │ │
│  │ 10:30:08   │ INFO  │ TASK   │ [翻译]  │ api   │ 翻译结果完成       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 日志详情（展开）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  详细信息                                                                │
├─────────────────────────────────────────────────────────────────────────┤
│  时间: 2024-01-15 10:30:01                                              │
│  级别: INFO                                                              │
│  分类: task                                                              │
│  模块: TASK                                                              │
│  来源: api                                                               │
│  算法类型: translation          ← 新增                                   │
│  设备ID: -                                                               │
│  任务ID: 123                                                             │
│  线程ID: -                                                               │
│  内容: 设备连接成功                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 实施清单

### 5.1 后端实施

- [x] Log 模型增加 `algorithm_type` 字段
- [x] 数据库迁移脚本
- [x] `log_handler.py` 支持 `algorithm_type` 参数
- [x] `log_controller.py` 支持按算法类型筛选
- [x] `log.py` Schema 增加 `algorithm_type` 字段
- [ ] 后端支持按来源筛选 (case/reference/device/api) - **待实现**

### 5.2 前端实施

- [x] `businessTypes.ts` 类型定义扩展 (新增 algorithmType)
- [x] `logView.ts` 增加算法类型筛选逻辑
- [x] `LogView.vue` 增加算法类型筛选器
- [x] `LogView.vue` 表格增加算法类型列
- [x] `LogView.vue` 详情区域增加算法类型显示
- [ ] `businessTypes.ts` 增加 `logSource` 字段 - **待实现**
- [ ] `logView.ts` 增加来源筛选逻辑 - **待实现**
- [ ] `LogView.vue` 增加来源筛选器 - **待实现**

### 5.3 测试验证

- [ ] 日志列表显示测试
- [ ] 算法类型筛选测试
- [ ] 日志详情显示测试
- [ ] 日志记录时算法类型关联测试
- [ ] 来源筛选测试 (case/reference/device/api) - **待实现**

---

## 6. 改动量评估

| 改动项 | 文件 | 改动量 | 状态 |
|--------|------|--------|------|
| 后端模型 | models.py | 新增1个字段 | ✅ |
| 后端处理器 | log_handler.py | 新增1个参数 | ✅ |
| 后端控制器 | log_controller.py | 新增约10行 | ✅ |
| 后端Schema | log.py | 新增1个字段 | ✅ |
| 前端类型 | businessTypes.ts | 新增2个字段 | ✅ |
| 前端逻辑 | logView.ts | 新增约20行 | ✅ |
| 前端视图 | LogView.vue | 新增约30行 | ✅ |
| 来源筛选 | 待定 | 待定 | ❌ |

**已实现改动量**：约70行代码

**待实现改动量**：约30行代码
