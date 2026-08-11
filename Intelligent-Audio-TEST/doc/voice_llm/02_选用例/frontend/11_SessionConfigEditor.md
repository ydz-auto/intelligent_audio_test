# 11_SessionConfigEditor 会话配置编辑器

> **已移除** — 此编辑器不再创建。

## 移除原因

1. session_timeout、context_mode 不在原始需求中
2. 会话级参数若将来需要，通过算法参数通道（DynamicForm + `CaseAlgorithmParam.scope`）管理，无需独立结构化编辑器
3. 从 5 个编辑器精简为 4 个通用编辑器

## 替代方案

若算法将来需要配置会话超时等参数，在算法种子数据中定义对应的 FormSchema 字段，通过 DynamicForm 渲染即可。无需在 Step 2 新增编辑器组件。

## 保留的 4 个通用编辑器

| # | 编辑器 | 说明 |
|---|--------|------|
| 1 | RoundConfigEditor | 多轮对话配置 |
| 2 | VoiceprintConfigEditor | 声纹注册配置 |
| 3 | InterfererConfigEditor | 干扰人配置 |
| 4 | RoundEvaluationEditor | 单轮评估配置 |
