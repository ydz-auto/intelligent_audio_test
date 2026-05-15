# LogView 页面与模态窗开发计划

## 一、概述

| 项目   | 说明                                |
| ---- | --------------------------------- |
| 页面路由 | `/LogView`                        |
| 页面功能 | 日志查看、筛选、导出、实时监控                   |
| 技术栈  | Electron + Vue 3 + Flask + SQLite |

***

## 二、已完成工作

### 2.1 后端已完成

| 组件         | 文件                                      | 功能                       | 工作量   |
| ---------- | --------------------------------------- | ------------------------ | ----- |
| Blueprint  | `backend/blueprints/log_bp.py`          | 6个API端点                  | ✅ 已完成 |
| Controller | `backend/controllers/log_controller.py` | 日志CRUD、导出、标记、算法类型筛选      | ✅ 已完成 |
| Schema     | `backend/schemas/log.py`                | 数据模型定义（含algorithm\_type） | ✅ 已完成 |
| Model      | `backend/models/models.py`              | Log模型含algorithm\_type    | ✅ 已完成 |
| Handler    | `backend/utils/log_handler.py`          | 日志记录与推送                  | ✅ 已完成 |

**已完成 API 端点：**

- `GET /api/v1/logs` - 获取日志列表（支持分页、高级过滤）
- `GET /api/v1/logs/stats` - 获取日志统计
- `POST /api/v1/logs/refresh` - 刷新日志
- `PUT /api/v1/logs/mark` - 标记日志
- `POST /api/v1/logs/clear` - 清除日志
- `POST /api/v1/logs/export` - 导出日志

**后端已完成工作量：约 500+ 行代码**

### 2.2 前端已完成

| 组件 | 文件                                           | 功能           | 工作量   |
| -- | -------------------------------------------- | ------------ | ----- |
| 视图 | `frontend/src/views/LogView.vue`             | 主页面组件（约600行） | ✅ 已完成 |
| 逻辑 | `frontend/src/views/LogViewLogic/logView.ts` | 业务逻辑（约560行）  | ✅ 已完成 |
| 类型 | `frontend/src/shared/types/businessTypes.ts` | Log类型定义      | ✅ 已完成 |

**已完成功能：**

- 日志列表展示（分页、排序）
- 多维度筛选（分类、模块、时间、标记、算法类型、日志级别）
- 高级筛选（设备ID、任务ID、线程ID、内容包含/不包含）
- 实时日志监控（轮询方式）
- 批量标记、导出（Excel/JSON格式）
- 行内详情展开

**前端已完成工作量：约 1100+ 行代码**

***

## 三、未完成工作

### 3.1 待开发功能清单

| 功能     | 说明                                 | 优先级    |
| ------ | ---------------------------------- | ------ |
| <br /> | <br />                             | <br /> |
| <br /> | <br />                             | <br /> |
| 来源筛选支持 | 按日志来源筛选（case/reference/device/api） | 中      |
| 用户ID字段 | Log模型增加user\_id字段支持                | 低      |

***

### 3.2 日志详情模态窗

#### 功能描述

将日志行的展开详情从行内展开改为模态窗展示，提供更好的查看体验。

#### 前端改动

| 文件                                                        | 改动内容               | 工作量 |
| --------------------------------------------------------- | ------------------ | --- |
| `frontend/src/components/common/modal/LogDetailModal.vue` | 新建日志详情模态窗组件        | 3h  |
| `frontend/src/views/LogView.vue`                          | 点击日志行打开详情模态窗替代行内展开 | 2h  |
| `frontend/src/views/LogViewLogic/logView.ts`              | 模态窗状态管理            | 2h  |

**LogDetailModal 组件需求：**

- 显示完整日志信息（时间、级别、分类、模块、来源、算法类型、设备ID、任务ID、线程ID、内容）
- JSON格式的上下文信息展示
- 复制按钮（复制全部信息）
- 标记/取消标记功能
- 关闭按钮

#### 后端改动

无需后端改动，当前 API 已返回完整日志信息。

#### 文档参考

- `doc/功能设计文档/智能语音算法配置适配/15_LogView适配方案.md`

**预计工作量：前端 7 小时**

***

### 3.3 监控配置模态窗

#### 功能描述

提供实时监控参数配置界面，包括轮询间隔、连接参数等设置。

#### 前端改动

| 文件                                                            | 改动内容        | 工作量 |
| ------------------------------------------------------------- | ----------- | --- |
| `frontend/src/components/common/modal/MonitorConfigModal.vue` | 新建监控配置模态窗组件 | 3h  |
| `frontend/src/views/LogViewLogic/logView.ts`                  | 监控参数状态管理    | 2h  |
| `frontend/src/views/LogView.vue`                              | 配置按钮绑定      | 1h  |
| 本地存储                                                          | 监控配置持久化     | 1h  |

**MonitorConfigModal 组件需求：**

- 轮询间隔配置（默认5秒，可选3/5/10/30秒）
- 自动滚动开关
- 连接状态显示
- 监控速率限制配置
- 保存/取消按钮

#### 后端改动

无需后端改动，前端轮询间隔在前端控制。

**预计工作量：前端 7 小时**

***

### 3.4 来源筛选支持

#### 功能描述

在日志筛选器中增加"来源"下拉框，支持按日志来源筛选。

#### 前端改动

| 文件                                           | 改动内容                         | 工作量 |
| -------------------------------------------- | ---------------------------- | --- |
| `frontend/src/views/LogView.vue`             | 在筛选栏增加来源下拉框                  | 1h  |
| `frontend/src/views/LogViewLogic/logView.ts` | 增加 logSource 筛选逻辑            | 1h  |
| `frontend/src/shared/types/businessTypes.ts` | LogFilters 接口增加 logSource 字段 | 1h  |

**来源选项：**

- all - 全部来源
- case - 测试用例
- reference - 参考参数
- device - 设备
- api - 算法服务
- backend - 后端

#### 后端改动

| 文件                                      | 改动内容                                    | 工作量 |
| --------------------------------------- | --------------------------------------- | --- |
| `backend/controllers/log_controller.py` | get\_logs 和 get\_stats 方法增加 source 参数筛选 | 2h  |

**预计工作量：前端 3 小时 + 后端 2 小时 = 5 小时**

***

### 3.5 用户ID字段支持

#### 功能描述

Log模型增加user\_id字段，支持按操作用户筛选日志。

#### 后端改动

| 文件                                      | 改动内容                | 工作量 |
| --------------------------------------- | ------------------- | --- |
| `backend/models/models.py`              | Log模型增加user\_id字段   | 2h  |
| `backend/controllers/log_controller.py` | 支持按user\_id筛选       | 1h  |
| `backend/schemas/log.py`                | LogItem增加user\_id字段 | 1h  |
| 数据库迁移                                   | 新增迁移脚本添加user\_id列   | 1h  |

#### 前端改动

| 文件                                           | 改动内容                      | 工作量 |
| -------------------------------------------- | ------------------------- | --- |
| `frontend/src/shared/types/businessTypes.ts` | LogFilters 接口增加 userId 字段 | 1h  |

**预计工作量：前端 1 小时 + 后端 5 小时 = 6 小时**

***

## 四、未完成工作量汇总

### 4.1 按迭代划分

| 迭代  | 功能       | 前端 | 后端 | 总计 | 优先级 |
| --- | -------- | -- | -- | -- | --- |
| 迭代一 | 来源筛选支持   | 3h | 2h | 5h | 中      |
| 迭代二 | 用户ID字段支持 | 1h | 5h | 6h | 低      |

### 4.2 总计

| 范围                | 前端  | 后端 | 总计      |
| ----------------- | --- | -- | ------- |
| **全部未完成功能**       | 4h | 7h | **11h** |
| **可选功能（迭代一、二）**   | 4h  | 7h | 11h      |

***

## 五、模态窗组件设计

### 5.1 LogDetailModal 组件设计

**位置：** `frontend/src/components/common/modal/LogDetailModal.vue`

**Props：**

```typescript
interface LogDetailModalProps {
  visible: boolean;
  log: Log | null;
  onClose: () => void;
  onMark: (logId: number, mark: string) => void;
  onCopy: (log: Log) => void;
}
```

**展示内容：**

- 时间（完整时间戳）
- 级别（带颜色标签）
- 分类
- 模块
- 来源
- 算法类型
- 设备ID
- 任务ID
- 线程ID
- 内容（完整文本）
- 上下文JSON

### 5.2 MonitorConfigModal 组件设计

**位置：** `frontend/src/components/common/modal/MonitorConfigModal.vue`

**Props：**

```typescript
interface MonitorConfigModalProps {
  visible: boolean;
  config: MonitorConfig;
  onClose: () => void;
  onSave: (config: MonitorConfig) => void;
}

interface MonitorConfig {
  pollInterval: number;  // 毫秒
  autoScroll: boolean;
  maxLogsPerBatch: number;
}
```

**配置项：**

- 轮询间隔：3s / 5s / 10s / 30s
- 自动滚动：开关
- 每批最大日志数：10 / 50 / 100

***

## 六、实施顺序建议

| 顺序 | 迭代  | 功能点     | 理由                 |
| -- | --- | ------- | ------------------ |
| 1  | 迭代一 | 日志详情模态窗 | 用户查看日志的核心功能，体验提升明显 |
| 2  | 迭代三 | 来源筛选支持  | 增强筛选能力，后端改动较小      |
| 3  | 迭代二 | 监控配置模态窗 | 高级功能，非核心需求         |
| 4  | 迭代四 | 用户ID字段  | 可选功能，根据实际需求决定      |

***

## 七、测试验证清单

### 7.1 前端测试

- [ ] 日志详情模态窗打开/关闭
- [ ] 模态窗内信息完整显示
- [ ] 标记功能在模态窗内正常工作
- [ ] 复制功能正常
- [ ] 监控配置保存后生效
- [ ] 来源筛选正确过滤结果

### 7.2 后端测试

- [ ] 来源参数正确筛选日志
- [ ] 分页参数正常工作
- [ ] 统计接口支持来源筛选

***

## 八、相关文档

| 文档          | 路径                                        |
| ----------- | ----------------------------------------- |
| LogView适配方案 | `doc/功能设计文档/智能语音算法配置适配/15_LogView适配方案.md` |
| 日志接口文档      | `doc/接口文档/日志接口文档.md`                      |
| 日志接口实现说明    | `doc/接口实现文档/日志接口实现说明.md`                  |
| 现有开发计划      | `doc/开发计划/开发计划.md`                        |
| 模态窗设计规范     | `doc/前端设计规范/UI设计规范.md`                    |

***

## 九、更新记录

| 日期         | 更新内容                           | 更新人 |
| ---------- | ------------------------------ | --- |
| 2026-04-07 | 更新未完成工作量汇总，移除已完成功能（日志详情模态窗、监控配置模态窗），剩余来源筛选支持和用户ID字段支持，总工作量更新为11h | -   |
| 2026-04-02 | 首次创建 LogView 开发计划，按完成/未完成分离工作量 | -   |

