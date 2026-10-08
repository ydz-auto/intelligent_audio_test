# 声压级映射管理（SPLMapping）开发计划

## 一、功能概述

### 1.1 现有实现状态

| 模块 | 状态 | 说明 |
|------|------|------|
| SPLMapping.vue | ✅ 已实现 | 声压级映射管理主页面，包含列表、筛选、详情展示 |
| SPLMapping.ts | ✅ 已实现 | 页面逻辑处理，包含模态窗调用 |
| useModal (模态窗系统) | ✅ 已实现 | 通用的 CRUD_FORM、DELETE_CONFIRM、DETAIL_VIEW、IMPORT_EXPORT 模态窗 |
| 后端 API | ✅ 已实现 | 11 个 API 端点（spl_bp.py） |
| 数据库模型 | ✅ 已实现 | SPLMapping、CalibrationHistory 表 |
| SPL 映射逻辑 | ✅ 已实现 | spl_service.py 中的 SPL→gain 计算 |
| 用例 SPL 配置 | ✅ 已实现 | 用例音频配置中的 spl 字段，后端自动计算增益 |
| 播放增益联动 | ✅ 已实现 | audio_engine.py 中干声/噪声播放时自动调用 SPL→gain |

### 1.2 重要说明

**校准方式**：当前系统仅支持**人工校准**，即用户手动输入校准点数据（数字增益 + 对应 SPL 值），不支持与声压计硬件通信的自动校准。

**用例声压播放**：用例音频配置中的 `spl` 字段（目标声压级）会在播放时自动通过 SPL 映射转换为对应增益，无需用户手动计算。

---

## 二、已完成工作量汇总

### 2.1 前端已完成功能

| 序号 | 功能模块 | 功能点 | 代码行数 | 工作量 | 完成时间 |
|------|----------|--------|---------|--------|----------|
| FE-1 | SPLMapping.vue | 页面主体结构（统计卡片、搜索筛选、分页） | ~150行 | 2 人天 | 已完成 |
| FE-2 | SPLMapping.vue | 映射卡片网格展示 | ~80行 | 1.5 人天 | 已完成 |
| FE-3 | SPLMapping.vue | Chart.js 折线图集成（卡片内） | ~50行 | 1 人天 | 已完成 |
| FE-4 | SPLMapping.ts | openAddMappingModal（添加映射模态窗） | ~75行 | 1 人天 | 已完成 |
| FE-5 | SPLMapping.ts | editMapping（编辑映射模态窗） | ~85行 | 1 人天 | 已完成 |
| FE-6 | SPLMapping.ts | viewMappingDetails（详情查看） | ~10行 | 0.5 人天 | 已完成 |
| FE-7 | SPLMapping.ts | handleDeleteMapping（删除确认） | ~15行 | 0.5 人天 | 已完成 |
| FE-8 | SPLMapping.ts | importMappingData（导入导出） | ~10行 | 0.5 人天 | 已完成 |
| FE-9 | SPLMapping.ts | 搜索、筛选、分页逻辑 | ~70行 | 1 人天 | 已完成 |
| FE-10 | SPLMapping.ts | initCharts（图表初始化） | ~145行 | 2 人天 | 已完成 |
| FE-11 | SPLMapping.ts | generateChartData（图表数据生成） | ~40行 | 0.5 人天 | 已完成 |
| FE-12 | SPLMapping.ts | fetchDevices（获取设备列表） | ~15行 | 0.5 人天 | 已完成 |

**前端已完成工作量合计：11.5 人天**

### 2.2 后端已完成功能

| 序号 | 功能模块 | 功能点 | 代码行数 | 工作量 | 完成时间 |
|------|----------|--------|---------|--------|----------|
| BE-1 | spl_bp.py | CRUD API（get_all/create/update/delete） | ~100行 | 1.5 人天 | 已完成 |
| BE-2 | spl_bp.py | 统计 API（get_stats） | ~20行 | 0.5 人天 | 已完成 |
| BE-3 | spl_bp.py | calibrate API（模拟校准） | ~50行 | 0.5 人天 | 已完成 |
| BE-4 | spl_bp.py | 历史 API（get_history） | ~15行 | 0.3 人天 | 已完成 |
| BE-5 | spl_bp.py | 校准数据 API（get_calibration_data） | ~10行 | 0.2 人天 | 已完成 |
| BE-6 | spl_bp.py | 按设备查询 API（get_by_device） | ~20行 | 0.3 人天 | 已完成 |
| BE-7 | spl_bp.py | 测试音 API（play/stop_test_tone） | ~100行 | 1.5 人天 | 已完成 |
| BE-8 | spl_controller.py | 映射创建/更新（含校准数据验证） | ~240行 | 3 人天 | 已完成 |
| BE-9 | spl_service.py | SPL→gain 计算（spl_to_gain） | ~90行 | 2 人天 | 已完成 |
| BE-10 | spl_service.py | 增益限制（_apply_gain_limit） | ~5行 | 0.2 人天 | 已完成 |
| BE-11 | audio_engine.py | 干声播放 SPL→gain 联动 | ~15行 | 0.5 人天 | 已完成 |
| BE-12 | audio_engine.py | 噪声播放 SPL→gain 联动 | ~10行 | 0.3 人天 | 已完成 |
| BE-13 | audio_controller.py | 预览 SPL→gain 联动 | ~5行 | 0.2 人天 | 已完成 |
| BE-14 | playback_controller.py | 设备关联映射（associate_spl） | ~30行 | 0.5 人天 | 已完成 |

**后端已完成工作量合计：11.5 人天**

### 2.3 已完成工作量总汇总

| 分类 | 工作量 |
|------|--------|
| 前端已完成 | 11.5 人天 |
| 后端已完成 | 11.5 人天 |
| **已完成总计** | **23 人天** |

---

## 三、待开发工作量汇总

### 3.1 待开发功能

| 序号 | 功能点 | 说明 | 工作量 | 优先级 |
|------|--------|------|--------|--------|
| M1 | 模态窗 Bug 修复 | 详情/编辑/删除模态窗交互问题修复 | 3 人天 | 高 |

**待开发工作量合计：3 人天**

---

## 四、工作量总览

| 分类 | 已完成 | 待开发 | 合计 |
|------|--------|--------|------|
| 前端 | 11.5 人天 | 3 人天 | 14.5 人天 |
| 后端 | 11.5 人天 | 0 人天 | 11.5 人天 |
| **总计** | **23 人天** | **3 人天** | **26 人天** |

---

## 五、待开发功能详细说明

### M1: 模态窗 Bug 修复

| 属性 | 说明 |
|------|------|
| **功能描述** | 修复 SPLMapping 页面中模态窗的交互问题 |
| **当前状态** | 模态窗基础功能已实现，但存在交互 bug |
| **文档参考** | SPLMapping.vue, SPLMapping.ts |
| **优先级** | 高 |
| **预计工作量** | 前端 3 人天 |

**待修复问题**：
- 详情模态窗数据展示不完整
- 编辑模态窗表单数据回填异常
- 删除确认模态窗关闭后状态未重置
- 多步操作（编辑→保存）后列表未刷新

**修复方案**：
- 检查 modalRegistration.ts 中的模态窗注册逻辑
- 验证 SPLMapping.ts 中 showModal 调用参数
- 确保 initModalWatchers 正确监听状态变化
- 添加操作完成后的数据刷新逻辑

---

## 六、文档索引

| 文档名称 | 路径 | 相关功能 |
|----------|------|----------|
| 声压级映射功能设计文档 | doc/功能设计文档/声压级映射功能设计文档.md | 整体架构、功能设计 |
| SPL映射逻辑说明 | doc/功能设计文档/SPL映射逻辑说明.md | SPL→gain 计算逻辑、用例联动 |
| SPLMapping 页面设计 | doc/页面设计文档/声压级映射管理页面设计.md | 前端页面设计 |
| SPLMapping 接口文档 | doc/接口文档/SPLMapping-接口文档.md | API 接口定义 |
| SPLMapping 接口实现 | doc/接口实现文档/SPLMapping-接口实现文档.md | API 实现说明 |
| SPLMapping.vue | frontend/src/views/SPLMapping.vue | 前端页面实现 |
| SPLMapping.ts | frontend/src/views/SPLMapping_logic/SPLMapping.ts | 页面逻辑实现 |
| spl_bp.py | backend/blueprints/spl_bp.py | 路由定义 |
| spl_controller.py | backend/controllers/spl_controller.py | 控制器实现 |
| spl_service.py | backend/utils/spl_service.py | SPL 计算服务 |
| audio_engine.py | backend/utils/audio_engine.py | 播放时 SPL→gain 调用 |
| playback_controller.py | backend/controllers/playback_controller.py | 设备关联映射 |
| 模态窗系统 | frontend/src/composables/useModal.ts | 通用模态窗 |
| modalRegistration.ts | frontend/src/composables/modalRegistration.ts | 模态窗注册 |
| BatchSPLModal.vue | frontend/src/components/common/modal/BatchSPLModal.vue | 批量 SPL 设置 |

---

## 七、核心流程说明

### 7.1 人工校准流程

```
用户操作流程：
1. 选择设备 → 播放测试音
2. 用声压计手动测量不同增益下的 SPL 值
3. 在增益点配置中人工输入（数字增益, 实测SPL）
4. 系统自动计算 gainOffset 并保存
```

### 7.2 用例声压播放流程

```
用例执行流程：
1. 用例配置 audio.spl = 65 (目标声压级)
2. 获取播放设备 → 查找 current_spl_mapping_id
3. 调用 spl_service.spl_to_gain(mapping_id, target_spl=65)
4. 根据校准数据线性插值计算增益
5. 将增益应用到音频播放
```

---

## 八、风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 模态窗状态同步问题 | 中 | 中 | 完善 modalStore 状态管理 |
| 后端验证遗漏 | 低 | 中 | 保持 API 验证逻辑与前端一致 |

---

## 九、更新记录

| 日期 | 更新内容 | 更新人 |
|------|----------|--------|
| 2026-04-02 | 首次创建，分离已完成/待开发工作量，修正待开发为模态窗Bug修复 | - |