# API 参数策略化改造 — 验收清单（checklist）

> 对应 [spec.md](./spec.md) §5 验收标准与 [tasks.md](./tasks.md)。

- [x] 读路径作用域：`GetFullFieldMapping` 契约带 `api_id`，servicer / 客户端 / 报告 ACL / 任务详情 / 报告快照 / e2e ACL 全链路透传
- [x] 空声明显式告警：`get_api_params(api_id=None)` 与「已绑定但策略+覆盖为空」均写 WARN，不静默返回错值
- [x] 首帧模板：`apis.meta.first_frame` 可配置并按 `{{placeholder}}` 渲染，未配置回落 `session.update`
- [x] 首帧写侧校验：非法 JSON / 占位符超出已声明输入参数 → 400
- [x] 单测：`test_int1756_api_id_scope.py`、`test_int1757_api_id_call_sites.py`、`test_param_profile_resolve.py`、`test_param_profile_crud.py`、`test_param_profile_migration.py` 全部通过（`pytest` 54 passed）
- [x] 死代码：`api_gateway/application/services/algorithm/algorithm_common.py` 已删除且全仓无引用
- [x] 前端算法编辑弹窗无 API 参数页签 / 无「所有 API 共用」横幅
- [x] 前端 API 编辑弹窗可绑定策略、克隆/另存为策略、编辑输出字段与映射（写 `PUT /algorithm/api-scope/{api_id}/overrides`）；重开弹窗回显已绑定策略
- [x] 前端策略管理入口可用（列表 / 新建 / 编辑 / 克隆 / 删除）
- [x] 前端 DTO 分层：snake_case 仅存在于 `infrastructure/`；`npm run typecheck` 本轮改动文件 0 错误（仅剩工作区既有 18 条与本次无关的错误）
- [x] 用例参数提取（`ExtractCaseAllParams`）按 `case_config.api_id` 解析 API 声明与评估映射；无 api_id 时不触发「默认层已废弃」告警
- [x] 评估提交 / 重评估（`full_case_params`）携带 `api_id`（API 结果取 `test_results.api_id`）
- [x] `ExtractResultFields` / `GetTimelineFields` / `BuildApiRequestData` 支持 `optional api_id`
