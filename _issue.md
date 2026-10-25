identifier = INT-1486
title = 【复走·React·开始测试域】用例选择/分组/执行模式 + 全模态窗
status = blocked
updated_at = 2026-10-24T09:57:52Z
last_activity_at = 2026-10-24T09:57:52.774313Z
parent_issue_id = 01a1677e-ed84-73db-998c-f0ed44526d8e
stage = None
---DESC---
# 复走·React·开始测试域

> 父总控 INT-1460（React 全量复走·总控）。本卡是**深走查**：每个模态窗逐条触发、提交、回读，禁止「打开正常 ✅」「真实数据正常 ✅」一笔带过。

## 目标
开始测试单入口（E2E/API 两模式）全流程：用例选择、分组、执行模式、API 编辑与健康检查、任务命名与提交逐窗深走。

## 覆盖范围
- 路由：`/start-test`（旧 `/E2ETest`、`/APITest` 重定向至此）
- 入口：`frontend-react/src/features/test-execution/index.tsx`（`components/step-cases.tsx` 等）
- 设计基准：`doc/功能设计文档/01_测试执行/`、`doc/UX设计规范/10_测试执行.md`
- 本域矩阵模态窗 **4 个**（2026-10-23 代码枚举，逐项勾选）：
  - [ ] `test-execution/modals/task-name-dialog.tsx` — 任务命名/提交：名称校验、提交后任务在任务页可见。
  - [ ] `test-execution/modals/case-detail-dialog.tsx` — 用例详情/试听（与报告域共用）：轮次、音频、维度。
  - [ ] `test-execution/modals/api-edit-dialog.tsx` — API 用例编辑：方法/URL/头/体，保存回读。
  - [ ] `test-execution/modals/api-health-dialog.tsx` — API 健康检查：发起、结果、失败态。

## 不做
- 不改业务代码（只有本卡测试脚本/证据可提交）；缺陷开修复卡，不在本卡顺手改。
- 不重复测本域以外的页面；跨域共用弹窗以组件使用点归口（谁页面上打开就归谁），回读以归属卡为准。
- 复用 INT-1245~1255 浅走查的结论一律不算数，必须按本卡清单重走。
- 不用空配置/简单数据绕过功能；不连 5000 段 test_test 栈。

## 环境与数据（2026-10-23 已核对）
- **前端**：docker `iat-react-frontend` → `http://localhost:15173`（已核实是 React 构建：`<div id="root">` + `/static/js/lib-react.*.js`；镜像构建 2026-10-23 14:24 本地，含 wiring/react 至 `d90085de`）。**不要用 16173（新 Vue）**，**不要起本地 dev server / pnpm dev**。
- **后端**：docker 真实库栈 `http://localhost:15000`（`/health` → `"database":"intelligent_audio_test"`）。**不要用 5000 段（intelligent_audio_test_test）**。
- **登录**：`接线测试_admin` / `JieXianTest@2026`（各角色账号见 `D:\00_env\multica_loop\real_db_accounts.md`）。
- **三次核对**（run 开始 / 每批截图前 / 交付前，记录写进交付评论）：
  `curl -s http://localhost:15000/health` 记 database；`curl -s http://localhost:15173/ | grep -o 'lib-react[^"]*'` 确认前端。任一不符 → 立即停，结论作废，开解阻卡（`--parent` 本卡）@yy dd。
- **镜像与源码**：报缺陷前先到本 run worktree 的 `frontend-react/` 源码核对缺陷是否仍存在（读源码 + `git log --since='24 hours'`）。源码已修则记「镜像滞后」并报需求规划师重构建，不计前端缺陷。
- **数据卫生**：写入只用「接线测试_」前缀自建记录，run 结束前删除；真实记录只读，不改不删。严禁 TRUNCATE / reset / 迁移。
- 不可逆外部影响（发邮件/短信、真实设备下发、清空真实日志、真实分享）只验取消路径，不执行。

## 每个模态窗的强制动作（逐窗执行，缺一不算 ✅）
1. **触发**：从真实入口打开，记录首次请求/初值来自哪个接口（Network）。
2. **字段**：逐个字段/开关/下拉编辑；每个下拉的选项条数与对应接口返回条数逐一对照；必填留空、非法值各提交一次看校验。
3. **提交**：真实提交一次（「接线测试_」数据），抓请求体 + 响应（方法 / URL / 状态码 / 关键字段）。
4. **回读**：关闭重开 / 刷新列表 / 直接 GET 接口，逐字段核对；不得只看 toast。
5. **取消与重开**：Esc、遮罩、关闭按钮各试一次；重开是否残留上次输入。
6. **空态 / 加载 / 错误态**：至少观察一次（无数据筛选、慢网或接口失败）。
7. **联动**：列表总数、页签计数、导航角标、其它引用处是否同步刷新。
每窗浅色 + 深色截图各一张（主题 key `iatp:theme:v1:mode`），关键交互帧另截。

## 三门禁（缺一不得交 in_review）
1. **逐窗证据**：上方清单 100% 勾选，每项 = 浅/深截图 + 真实请求/响应 + GET 回读。
2. **假数据残留**：对本域整页组件树执行
   `grep -rniE "mock|MOCK|dummy|hardcode|写死|假数据" frontend-react/src/features/test-execution`
   逐条列出并裁定「合理占位（代码标待接线 + FEAT 卡号）/ 缺陷（开卡）/ 测试文件忽略」；未裁定不得交。
   本域已知需重点裁定的残留：
   - 本域组件头无 MOCK；用例选择步骤与用例域共用弹窗，整页 grep 仍要跑。
3. **V9.7.10 对照**：对照 `D:\00_code\V9.7.10` 旧 Vue 的对应页面与模态窗，字段 / 选项来源 / 按钮 / 流程逐项比对；V9.7.10 有而 React 缺失或走样的单列缺口（开缺陷卡或写明裁定），不得静默通过。

## 可测验收标准
- 4 个模态窗全部勾选；用例选择步骤的分组数与 `GET /groups`、用例数与筛选结果逐一对照（历史漏项：2/8 组）。
- E2E 与 API 两模式各走一次到提交（「接线测试_」任务），记录请求体与后端响应。
- 执行模式/目标形态切换后请求体字段与选择一致。
- 清单外新增发现（不可达模态窗、矩阵未列出的窗）单列一节，注明是否可达、V9.7.10 是否有、裁定结论。
- 交付评论包含：三次 `/health` 记录、前端 `lib-react` 识别记录、逐窗证据、grep 裁定、V9.7.10 差异、缺陷卡号、未覆盖项。

## 已知风险与既有卡（复现先查，避免重复开卡）
- 分组卡只渲染已加载分组：首屏 100 条内无成员的分组 `return null`（INT-1248 同源）→ 先「加载更多」再核对。
- 常驻栈后端 `target_modes` 未落地时只接受不使用 → 只验前端请求体，不以此判前端缺陷。
- 真实库音频全 dry；试听/噪声相关空态裁定同上。

## 出口（按 devloop 出口表，测试工程师不自己置 done）
- 三门禁全过 → 交付评论（逐窗证据清单 / grep 裁定 / V9.7.10 差异 / 缺陷卡号 / 三次环境记录）→ `in_review` + **前端UX审计员**（交接三步：评论 → `multica issue update <本卡> --status in_review --assignee 前端UX审计员 --no-start` → `multica issue rerun <本卡>`）。
- 发现缺陷 → 先开修复卡挂 INT-1460（`--project 两前端接线·React`），本卡等修复验收后把相关窗重走一遍再交；其余窗不得因此漏走。
- 90 分钟软上限：走不完就列明未覆盖项并拆子卡（`--parent` 本卡），**不得带未覆盖项交 in_review**。

