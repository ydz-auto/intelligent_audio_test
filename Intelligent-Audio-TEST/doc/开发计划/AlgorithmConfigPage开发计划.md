# 算法配置管理 - 开发计划

## 一、功能概述

### 1.1 现有实现状态

| 模块 | 状态 | 说明 |
|------|------|------|
| AlgorithmConfigPage.vue | ✅ 已实现 | 算法配置主页面，包含列表、筛选、详情展示 |
| AlgorithmConfigModal.vue | ✅ 已实现 | 算法配置模态窗，支持创建/编辑/列表模式 |
| AlgorithmParamsConfig.vue | ✅ 已实现 | 算法参数配置组件 |
| DynamicForm.vue | ✅ 已实现 | 动态表单渲染组件 |
| MappingEditor.vue | ✅ 已实现 | 参数映射编辑器 |
| 后端 API | ✅ 已实现 | 46+ API 端点 |
| 数据库模型 | ✅ 已实现 | 7 张相关表 |

---

## 二、文档索引

| 文档名称 | 路径 | 相关功能 |
|----------|------|----------|
| 智能语音算法配置化方案 | doc/功能设计文档/智能语音算法配置适配/智能语音算法配置化方案.md | 整体架构、数据库设计 |
| 智能语音算法配置适配方案 | doc/功能设计文档/智能语音算法配置适配/*.md | 各组件适配详情 |
| 算法配置页面设计 | doc/页面设计文档/AlgorithmConfigPage.md | 前端页面设计 |
| AlgorithmConfigPage.vue | frontend/src/views/AlgorithmConfigPage.vue | 前端页面实现 |
| AlgorithmConfigModal.vue | frontend/src/components/algorithm/AlgorithmConfigModal.vue | 模态窗实现 |
| DynamicForm.vue | frontend/src/components/algorithm/DynamicForm.vue | 动态表单实现 |
| algorithm_controller.py | backend/controllers/algorithm_controller.py | 后端控制器 |
| algorithm_models.py | backend/models/algorithm_models.py | 数据模型 |
| algorithm_bp.py | backend/blueprints/algorithm_bp.py | 路由定义 |

---

## 三、架构设计

```
┌─────────────────┐
│  AlgorithmConfigPage │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│     AlgorithmConfigModal        │
│  ┌─────────────────────────────┐│
│  │ AlgorithmParamsConfig       ││
│  │  └── DynamicForm            ││
│  └─────────────────────────────┘│
│  ┌─────────────────────────────┐│
│  │     MappingEditor          ││
│  └─────────────────────────────┘│
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│         后端 API                │
│  ┌─────────────────────────────┐│
│  │  algorithm_controller.py   ││
│  │  algorithm_service.py      ││
│  │  algorithm_config_loader.py││
│  └─────────────────────────────┘│
│  ┌─────────────────────────────┐│
│  │  algorithm_models.py       ││
│  │  (7 张数据表)              ││
│  └─────────────────────────────┘│
└─────────────────────────────────┘
```

---

## 四、待开发工作量评估

### 4.1 核心功能实现状态

| 功能模块 | 实现状态 | 代码位置 | 说明 |
|---------|---------|---------|------|
| **前端页面** | | | |
| AlgorithmConfigPage.vue | ✅ 已实现 | frontend/src/views/ | 列表、筛选、详情展示 |
| AlgorithmConfigModal.vue | ✅ 已实现 | frontend/src/components/algorithm/ | 创建/编辑/列表/选择模式 |
| - 基本信息配置 | ✅ | - | 包含分组选择、状态切换 |
| - 设备/API/用例参数配置 | ✅ | - | 三种参数类型独立配置 |
| - 参考参数配置 | ✅ | - | 支持文本/音频/RTTM/STM |
| - 参数映射配置 | ✅ | - | 设备/API/评估三种映射 |
| - 关联评估维度 | ✅ | - | 支持权重、默认值配置 |
| DynamicForm.vue | ✅ 已实现 | frontend/src/components/algorithm/ | 动态表单渲染 |
| - 字段渲染 | ✅ | - | input/select/textarea/slider/switch |
| - 分组折叠 | ✅ | - | 支持分组展开/收起 |
| - 字段验证 | ✅ | - | 必填、格式、范围验证 |
| - 字段联动 | ⚠️ 待确认 | - | 设计文档有提及，需验证实现 |
| - 动态选项 | ✅ | - | 支持 options_source 动态加载 |
| MappingEditor.vue | ✅ 已实现 | frontend/src/components/algorithm/ | 参数映射编辑器 |
| - 设备参数映射 | ✅ | - | 用例参数→设备参数 |
| - API参数映射 | ✅ | - | 用例参数→API参数 |
| - 评估参数映射 | ✅ | - | 支持case/device/api/reference四种来源 |
| - 转换类型 | ✅ | - | none/uppercase/lowercase/json_parse |
| **后端服务** | | | |
| algorithm_controller.py | ✅ 已实现 | backend/controllers/ | 46+ API端点 |
| algorithm_models.py | ✅ 已实现 | backend/models/ | 7张数据库表 |
| algorithm_config_loader.py | ✅ 已实现 | backend/algorithm/ | 单例模式、缓存机制 |
| case_parameter_extractor.py | ✅ 已实现 | backend/algorithm/ | 参数提取器 |
| - get_device_params | ✅ | - | 已被 e2e_executor 集成 |
| - get_api_params | ✅ | - | 已被 api_executor 集成 |
| - get_evaluation_params | ✅ | - | 已被 api_executor/base_executor 集成 |
| - get_form_schema | ⚠️ 待验证 | - | 需前端实际使用验证 |
| **执行器集成** | | | |
| api_executor.py | ✅ 已集成 | backend/utils/ | 使用 CaseParameterExtractor |
| e2e_executor.py | ✅ 已集成 | backend/utils/ | 使用 CaseParameterExtractor |
| base_executor.py | ✅ 已集成 | backend/utils/ | 使用 CaseParameterExtractor |

### 4.2 待确认/潜在工作量

| 功能点 | 状态 | 说明 | 优先级 |
|-------|------|------|--------|
| DynamicForm 字段联动 | ⚠️ 待验证 | 设计文档提及但需确认完整实现 | 中 |
| 配置热更新机制 | ⚠️ 待确认 | AlgorithmConfigLoader 有缓存失效接口，需确认触发时机 | 中 |
| 参考参数生成器 | ✅ 已集成 | reference_params_generator.py 已在 CaseParameterExtractor 中使用 | - |
| 完整字段类型 | ✅ 已实现 | text/audio/json/RTTM/STM 等类型均已支持 | - |
| 选项动态加载 | ✅ 已实现 | 所有参数为静态文本输入，不再从数据库表动态获取 | - |

### 4.3 验证建议

如需确认上述待确认功能点的实际实现状态，建议执行以下验证：

1. **字段联动验证**：在 DynamicForm 中配置联动规则，测试 show/hide/setValue 行为
2. **配置热更新验证**：在数据库中修改算法配置后，验证执行器是否使用新配置
3. **表单 Schema 验证**：使用 get_form_schema 接口，检查返回的 schema 是否满足前端渲染需求

---

## 五、更新记录

| 日期 | 更新内容 | 更新人 |
|------|----------|--------|
| 2026-04-02 | 首次创建算法配置开发计划 | - |
| 2026-04-02 | 移除所有待开发功能点，仅保留已实现功能 | - |
| 2026-04-02 | 重新审视工作量，添加待开发工作量评估章节 | - |
