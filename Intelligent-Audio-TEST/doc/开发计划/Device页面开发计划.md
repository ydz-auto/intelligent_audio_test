# Device.vue 页面与模态窗开发计划

## 一、页面概述

| 项目 | 说明 |
|------|------|
| 页面文件 | frontend/src/views/Device.vue |
| 逻辑文件 | frontend/src/views/DeviceLogic/device.ts |
| 页面类型 | 设备管理主页面 |
| 技术栈 | Vue 3 + Composition API + TypeScript + Pinia |

---

## 二、功能架构

### 2.1 三大功能模块

| 模块 | 标签页 | 功能定位 | 后端 Blueprint |
|------|--------|----------|----------------|
| 测试设备管理 | 测试设备管理 | 管理 Android/iOS/HarmonyOS 真机设备 | device_bp.py |
| 播放设备管理 | 播放设备管理 | 管理音频播放设备（声卡、扬声器） | playback_bp.py |
| 测试API管理 | 测试API管理 | 管理第三方 API 服务配置 | api_bp.py |

---

## 三、现状分析

### 3.1 后端实现状态

#### 已完成 API

| API | 方法 | 路由 | 状态 |
|-----|------|------|------|
| 获取设备列表 | GET | /api/v1/test-devices | ✅ 已完成 |
| 获取设备详情 | GET | /api/v1/test-devices/:id | ✅ 已完成 |
| 创建设备 | POST | /api/v1/test-devices | ✅ 已完成 |
| 更新设备 | PUT | /api/v1/test-devices/:id | ✅ 已完成 |
| 删除设备 | DELETE | /api/v1/test-devices/:id | ✅ 已完成 |
| 扫描设备 | POST | /api/v1/test-devices/scan | ✅ 已完成 |
| 设备测试 | POST | /api/v1/test-devices/:id/test | ✅ 已完成 |
| 停止测试 | POST | /api/v1/test-devices/:id/stop-test | ✅ 已完成 |
| 健康检查 | POST | /api/v1/test-devices/health-check | ✅ 已完成 |
| 获取驱动关键字 | GET | /api/v1/test-devices/driver-keywords | ✅ 已完成 |
| 获取可用序列号 | GET | /api/v1/test-devices/serials | ✅ 已完成 |
| 播放设备 CRUD | - | /api/v1/playback-devices/* | ✅ 已完成 |
| 播放设备扫描 | POST | /api/v1/playback-devices/scan | ✅ 已完成 |
| 播放设备测试 | POST | /api/v1/playback-devices/:id/test | ✅ 已完成 |
| 播放设备SPL关联 | POST | /api/v1/playback-devices/:id/associate-spl | ✅ 已完成 |
| API设备 CRUD | - | /api/v1/apis/* | ✅ 已完成 |
| API设备健康检查 | POST | /api/v1/apis/:id/health | ✅ 已完成 |
| API设备连接测试 | POST | /api/v1/apis/:id/test | ✅ 已完成 |

#### 未完成 API（待开发）

| API | 方法 | 路由 | 说明 | 优先级 |
|-----|------|------|------|--------|
| 设备分组 CRUD | - | /api/v1/device-groups/* | 设备分组管理 | 高 |
| 设备标签 CRUD | - | /api/v1/device-tags/* | 设备标签管理 | 中 |
| 设备操作日志 | - | /api/v1/device-logs/* | 记录设备操作历史 | 中 |
| 设备批量操作 | POST | /api/v1/test-devices/batch-* | 批量更新/删除/状态变更 | 高 |
| 设备性能数据 | GET | /api/v1/test-devices/:id/performance | 设备性能指标采集 | 中 |

#### 设备驱动状态

| 驱动 | 文件 | 状态 | 说明 |
|------|------|------|------|
| Android Driver | device_driver/android_driver.py | ✅ 已完成 | ADB连接、扫描、唤醒 |
| HarmonyOS Driver | device_driver/harmony_driver.py | ✅ 已完成 | HDC连接、扫描 |
| iOS Driver | - | ⚠️ 需完善 | 仅基础框架，需集成libimobiledevice |
| Base Driver | device_driver/base_driver.py | ✅ 已完成 | 驱动基类 |
| Driver Factory | device_driver/driver_factory.py | ✅ 已完成 | 驱动工厂模式 |

---

### 3.2 前端实现状态

#### 已完成功能

| 功能点 | 说明 | 文件 | 状态 |
|--------|------|------|------|
| 设备类型切换 | 三个标签页切换 | Device.vue | ✅ 已完成 |
| 设备卡片列表 | 卡片式展示，支持选择/编辑/删除/测试 | Device.vue | ✅ 已完成 |
| 设备状态概览 | 统计总设备数、在线数、离线数、测试中数 | Device.vue | ✅ 已完成 |
| 设备搜索过滤 | 关键词搜索、状态过滤、类型过滤 | device.ts | ✅ 已完成 |
| 设备扫描 | 扫描物理设备（ADB/HDC命令） | ScanDevicesModal.vue | ✅ 已完成 |
| 批量删除 | 批量删除选中的设备 | device.ts | ✅ 已完成 |
| 设备导入导出 | 设备配置导入导出 | device.ts | ✅ 已完成 |
| 分页显示 | 三种设备类型各自独立分页 | device.ts | ✅ 已完成 |
| 设备测试 | 单设备测试连接/播放 | device.ts | ✅ 已完成 |
| 健康检查 | 单设备/批量健康检查 | device.ts | ✅ 已完成 |
| 添加设备 | 通过通用CRUDFormModal添加 | CRUDFormModal.vue | ✅ 已完成 |
| 编辑设备 | 通过通用CRUDFormModal编辑 | CRUDFormModal.vue | ✅ 已完成 |
| 播放设备选择 | GlobalPlaybackDeviceModal | GlobalPlaybackDeviceModal.vue | ✅ 已完成 |
| 批量播放设备设置 | BatchPlaybackDeviceModal | BatchPlaybackDeviceModal.vue | ✅ 已完成 |

#### 未完成功能（待开发）

| 功能点 | 说明 | 优先级 | 预计工作量 |
|--------|------|--------|-----------|
| 设备分组管理 UI | 分组创建、编辑、拖拽分配 | 高 | 2 人天 |
| 设备标签系统 UI | 标签创建、关联、过滤 | 高 | 1 人天 |
| 批量操作 UI | 批量选择、更新、删除 | 高 | 2 人天 |
| 设备性能监控 UI | CPU/内存/电池实时显示 | 中 | 4 人天 |
| 设备对比视图 | 多设备并排对比 | 低 | 5 人天 |
| 设备远程控制 | 远程重启/截图/桌面 | 低 | 5 人天 |

---

## 四、开发任务详情

### 4.1 前端待开发任务

| 序号 | 功能点 | 说明 | 文档参考 | 优先级 | 预计工作量 | 状态 |
|------|--------|------|----------|--------|-----------|------|
| F1 | 设备分组管理 UI | 分组创建/编辑/拖拽分配/批量操作 | 设备管理功能设计文档.md | 高 | 2 人天 | 待开发 |
| F2 | 设备标签系统 UI | 标签创建/关联/过滤搜索 | 设备管理功能设计文档.md | 高 | 1 人天 | 待开发 |
| F3 | 批量操作 UI | 批量选择、更新、删除设备 | 设备管理功能设计文档.md | 高 | 2 人天 | 待开发 |
| F4 | 设备性能监控 UI | CPU/内存/电池实时显示 | 设备管理功能设计文档.md | 中 | 4 人天 | 待开发 |
| F5 | 设备对比视图 | 多设备并排对比参数差异 | 设备管理功能设计文档.md | 低 | 5 人天 | 待开发 |
| F6 | 设备远程控制 | 远程重启/截图等功能 | 设备管理功能设计文档.md | 低 | 5 人天 | 待开发 |

**前端待开发总计：19 人天**

---

### 4.2 后端待开发任务

| 序号 | 功能点 | 说明 | 文档参考 | 优先级 | 预计工作量 | 状态 |
|------|--------|------|----------|--------|-----------|------|
| B1 | 设备分组 CRUD API | 分组的创建/查询/更新/删除 | 设备管理功能设计文档.md | 高 | 2 人天 | 待开发 |
| B2 | 设备标签管理 API | 标签的创建/关联/移除 | 设备管理功能设计文档.md | 高 | 1 人天 | 待开发 |
| B3 | 设备批量操作 API | 批量更新/删除/状态变更 | 04_测试设备管理-接口实现文档.md | 高 | 2 人天 | 待开发 |
| B4 | 设备性能数据采集 | 定期采集CPU/内存/电池指标 | 设备管理功能设计文档.md | 中 | 4 人天 | 待开发 |
| B5 | iOS 驱动完善 | 集成 libimobiledevice | 设备管理功能设计文档.md | 高 | 15 人天 | 待开发 |
| B6 | 设备对比 API | 获取多设备对比数据 | 设备管理功能设计文档.md | 低 | 1 人天 | 待开发 |
| B7 | 设备远程控制 | 远程重启/截图等功能 | 设备管理功能设计文档.md | 低 | 4 人天 | 待开发 |
| B8 | 设备状态缓存 | Redis缓存设备状态 | 后端设计文档.md | 高 | 1 人天 | 待开发 |
| B9 | 设备连接稳定性优化 | 断线重连机制增强 | 设备管理功能设计文档.md | 高 | 3 人天 | 待开发 |

**后端待开发总计：33 人天**

---

## 五、模态窗开发状态

### 5.1 已有模态窗

| 模态窗 | 文件位置 | 功能 | 状态 |
|--------|----------|------|------|
| ScanDevicesModal | components/common/modal/ScanDevicesModal.vue | 设备扫描 | ✅ 已完成 |
| CRUDFormModal | components/common/modal/CRUDFormModal.vue | 通用添加/编辑（设备/API/其他） | ✅ 已完成 |
| GlobalPlaybackDeviceModal | components/common/modal/GlobalPlaybackDeviceModal.vue | 播放设备选择 | ✅ 已完成 |
| BatchPlaybackDeviceModal | components/common/modal/BatchPlaybackDeviceModal.vue | 批量设置播放设备 | ✅ 已完成 |
| APIEditModal | components/common/modal/APIEditModal.vue | API设置 | ✅ 已完成 |

### 5.2 待开发模态窗

| 序号 | 模态窗名称 | 功能描述 | 优先级 | 预计工作量 |
|------|------------|----------|--------|-----------|
| M1 | DeviceGroupModal | 设备分组管理 | 高 | 2 人天 |
| M2 | DevicePerformanceModal | 性能监控面板 | 中 | 3 人天 |

**模态窗待开发总计：5 人天**

---

## 六、工作量汇总

### 6.1 按已完成/未完成汇总

| 分类 | 已完成 | 待开发 | 合计 |
|------|--------|--------|------|
| 前端功能 | 14项 ✅ | 10项 | 24项 |
| 后端 API | 28项 ✅ | 10项 | 38项 |
| 模态窗 | 5个 ✅ | 5个 | 10个 |
| 设备驱动 | 6个 ✅ | 1个 | 7个 |

### 6.2 待开发工作量汇总

| 分类 | 工作量 |
|------|--------|
| 前端待开发 | 19 人天 |
| 后端待开发 | 33 人天 |
| 模态窗待开发 | 5 人天 |
| **总计** | **57 人天** |

---

## 七、里程碑计划

| 里程碑 | 内容 | 交付时间 | 状态 |
|--------|------|----------|------|
| M1 | 核心功能补全（设备分组CRUD、批量操作、标签管理） | 第 2 周 | 待开发 |
| M2 | 配套UI完善（详情面板、批量导入、日志） | 第 3 周 | 待开发 |
| M3 | 高级功能（性能监控、iOS驱动、远程控制） | 第 5 周 | 待开发 |

---

## 八、代码文件索引

### 8.1 前端文件

| 文件 | 说明 | 状态 |
|------|------|------|
| frontend/src/views/Device.vue | 设备管理主页面 | ✅ 已完成 |
| frontend/src/views/DeviceLogic/device.ts | 设备管理逻辑 | ✅ 已完成 |
| frontend/src/composables/useDeviceManagement.ts | 设备管理组合式函数 | ✅ 已完成 |
| frontend/src/components/common/modal/ScanDevicesModal.vue | 设备扫描 | ✅ 已完成 |
| frontend/src/components/common/modal/CRUDFormModal.vue | 通用添加/编辑表单 | ✅ 已完成 |
| frontend/src/components/common/modal/GlobalPlaybackDeviceModal.vue | 播放设备选择 | ✅ 已完成 |
| frontend/src/components/common/modal/BatchPlaybackDeviceModal.vue | 批量播放设备 | ✅ 已完成 |
| frontend/src/components/common/modal/ | 待新增模态窗目录 | 待开发 | |

### 8.2 后端文件

| 文件 | 说明 | 状态 |
|------|------|------|
| backend/blueprints/device_bp.py | 测试设备路由 | ✅ 已完成 |
| backend/blueprints/playback_bp.py | 播放设备路由 | ✅ 已完成 |
| backend/blueprints/api_bp.py | API设备路由 | ✅ 已完成 |
| backend/controllers/device_controller.py | 测试设备控制器 | ✅ 已完成 |
| backend/controllers/playback_controller.py | 播放设备控制器 | ✅ 已完成 |
| backend/controllers/api_controller.py | API设备控制器 | ✅ 已完成 |
| backend/device_driver/android_driver.py | Android驱动 | ✅ 已完成 |
| backend/device_driver/harmony_driver.py | HarmonyOS驱动 | ✅ 已完成 |
| backend/device_driver/driver_factory.py | 驱动工厂 | ✅ 已完成 |
| backend/device_driver/base_driver.py | 驱动基类 | ✅ 已完成 |
| backend/schemas/device.py | 设备数据模型 | ✅ 已完成 |
| backend/models/models.py | 数据库模型 | ✅ 已完成 |

---

## 九、参考文档

| 文档名称 | 路径 |
|----------|------|
| 设备管理功能设计文档 | doc/功能设计文档/设备管理功能设计文档.md |
| 测试设备管理接口实现文档 | doc/接口实现文档/04_测试设备管理-接口实现文档.md |
| 播放设备管理接口实现文档 | doc/接口实现文档/05_播放设备管理-接口实现文档.md |
| WebSocket进度方案 | doc/功能设计文档/websocket_progress_solution.md |
| 后端设计文档 | doc/总架构/后端设计文档.md |

---

## 十、更新记录

| 日期 | 更新内容 |
|------|----------|
| 2026-04-02 | 首次创建 Device.vue 页面开发计划 |
| 2026-04-02 | 核实代码现状，区分已完成/未完成工作 |
