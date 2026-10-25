=== 01a16c65-1b86-7d69-ae6e-6c3cdbf3853a at 2026-10-24T05:32:07Z author 8fa7b5ec-b545-41f8-a772-997bea66ac0d parent None
## 结论：不通过（打回测试工程师）——case-detail 窗仍不满足已裁定的轮次口径；且 15173 现跑的并非修复版构建

四窗里 task-name / api-edit / api-health 沿用成立；**第 4 窗 `case-detail-dialog` 不能记 ✅**：本卡 04:29Z 交付依据的构建是 INT-1688 **返工前**的实现（`@round:{n}`/`@overall` 内部 key 直接当列头），而负责人 03:31Z 已裁定按 V9.7.10 轮次 Tab 口径、INT-1723 已回写规范。另外我本轮实测发现 **15173 在 05:03Z 被重建成了不含 INT-1688 修复的旧构建**，测试工程师交付里「15173 已重建到修复版」这句话在 05:03 之后已不成立。

### 一、审计清单逐项结论

| # | 项 | 结论 | 依据 |
|---|---|---|---|
| 1 | 交互与功能对齐（V9.7.10） | **不通过** | case-detail 的「执行结果与指标」呈现与 V9.7.10 `TestCaseReportDetail` 不一致（见 P2） |
| 2 | 实机验证（15173 + 15000 真实库） | **不通过** | 当前 15173 实测回到修复前形态（见 P1） |
| 3 | 构建与单测 | 通过 | `pnpm build` exit 0；`vitest run case-detail-dialog.test.tsx testCaseAdapter.test.ts --pool=threads` → 2 文件 23 测试全过（228s） |
| 4 | 视觉一致性 | 通过（本窗） | 表头/徽章/按钮走 shadcn 组件与 token 类名，无内联魔法样式；浅/深同源切换一致 |
| 5 | DDD 纪律 | 通过 | `devices: string[]` 修正在 `dto/testcase.dto.ts`，组合逻辑在 `adapters/testCaseAdapter.ts`（`caseDetailFromDto(dto, results)` 是唯一转换点），弹窗不造数据 |
| 6 | mock 残留裁定 | 通过（同前轮） | `MOCK_RESOURCE_LABS`→INT-487（代码标待接线）、设备连接测试动画→INT-361、`__tests__` 忽略；本域无新增 mock |
| 7 | 其余 3 窗 | 沿用成立 | task-name / api-edit 自 `7b321bdc` 起 `git log` 为空；api-health 仅有 `e7006f002`（INT-1632），即我 23:30Z 复核通过的版本 |

### 二、问题清单

**P2 ·（口径）case-detail「执行结果与指标」把内部 key 当列头，不是 V9.7.10 的轮次 Tab**

- 页面/文件：`frontend-react/src/features/test-execution/modals/case-detail-dialog.tsx:369-371`（渲染 `column.label`）、`infrastructure/adapters/testCaseAdapter.ts` `buildMetricColumns`（`label: \`${dimension}@round:${round}\``）。
- 实际：表头 14 列 = 设备 + **「逐轮话轮评估@round:1」「逐轮话轮评估@overall」…**（6 维度 × 2）+ 执行状态，无 `[role=tab]`，单轮用例也展开成 12 个轮次列。
- 期望（负责人 2026-10-24 03:31Z 裁定 + INT-1723 已回写 `doc/UX设计规范/10_测试执行.md §5.2`）：轮次用 Tab（多轮「第1轮…第N轮」+ 有值才出现「整体」，单轮单个「指标」），表体**行=指标、列=设备**；`@round:{n}`/`@overall` 只是内部 key，不得直接当 UI 文案。
- 证据：附件 `build_task402_light.png` / `build_task402_dark.png`（我自己 `pnpm build` 出的 dist + 旁路容器 15391，源码 = 本 worktree wiring/react 头 `312f698c6`）。
- 修复归属：**INT-1688 返工已交付未合入**——`agent/react-a/int-1688` @ `7dd09598c`（04:40Z，改为轮次 Tab），本卡不用另开修复卡；等它合入 + 重建后再验。

**P1 ·（环境/部署）15173 当前镜像是 INT-1688 修复前的构建，弹窗回到「设备 / 结果」两列、设备名空白、恒「失败」**

- 实测（2026-10-24T05:03Z 后）：`iat-react-frontend:latest` = `sha256:807d65a5f17a`（created `05:03:34Z`），容器 `05:03:35Z` 启动；容器内 `static/js/async` **0 个 chunk 含 `result_audios`**；首页 bundle 由 `lib-react.5c68ee069a.js` 变为 `lib-react.0da624625f.js`。
- 页面表现（附件 `15173deploy_ux_task402_light.png` / `_dark.png`）：任务 402 → 同一条用例，弹窗只有「设备 / 结果」两列，设备名空白、结果恒「失败」，无维度/轮次/结果音频——与 INT-1688 修复前完全一致。
- 时间线：03:45:08Z 镜像（含 `fddeca1d2`，我 04:45Z 实测表头 14 列）→ 04:47:48Z 重建 → 04:51Z 容器重启（期间我遇到 `/detail` Fetch 失败）→ 05:03:34Z 再重建为不含修复的旧构建。期间还有他卡 run 的旁路容器 `iat-int1688-verify`（`nginx:alpine`）在跑，共享 15173 被并发改动。
- 影响：本卡「15173 已重建到修复版」的结论不成立；任何以 15173 为准的复测都会被这个构建误导。
- 建议：部署/集成侧核实 `iat-react-frontend:latest` 为何被重建为旧代码；重建到含 INT-1688 返工（`7dd09598c`）的 wiring/react 后再复走。

### 三、我本轮独立复现到的「已修」部分（在自建构建上，供下轮对照）

任务 402 / 用例 `7bac162b-…`，旁路容器 15391（wiring/react 头源码 `pnpm build`）：
- 设备名「pura90小艺」出现在头部徽章与表格行 ✅；执行状态「已完成」✅；弹窗内「失败」0 次 ✅；
- 结果音频区：`user_wav (第1轮)`、`ai_wav (第1轮)` 两条 + 试听入口 ✅（参考音频「…silence.wav」1 条 ✅）；
- 浅/深两主题表头与行完全一致（`document.documentElement.className="dark"`）。
- 说明：本轮 CDP 点击首个「试听」未取到 `<audio>` src（自动化限制，非失败结论）；试听链路的 200 + 预签名证据沿用 04:29Z 交付与本卡历史轮次。

### 四、环境三次核对

| 时点 | `/health` database | 15173 |
|---|---|---|
| 开工 04:32Z | `intelligent_audio_test` | 200，`lib-react.5c68ee069a.js` + `id="root"` |
| 每批截图前 05:07Z | `intelligent_audio_test` | 200，`lib-react.0da624625f.js`（已被外部重建） |
| 交付前 05:47Z | `intelligent_audio_test` | 200，同上；镜像 `807d65a5`（05:03:34Z） |

期间 15173 被本卡以外的 run 重启/重建两次（04:51Z、05:03Z），非本 run 操作。

### 五、打回交接

- 本卡最新交付分支与 sha：`agent/agent/int-1486` @ **`e01fb169a`**（仅测试脚本）。
- 请测试工程师：① 先核 INT-1688 返工 `7dd09598c` 已合入 `wiring/react` 且 15173 已重建（判据：容器 bundle 含 `result_audios`，且弹窗是轮次 Tab、无 `@round:` 列头）；② 按 Tab 口径只重走 `case-detail`（任务 402 有结果用例 + 无结果空态各一次，浅/深 + `/detail`+`/results` 原文）；③ 交回前端UX审计员。其余 3 窗沿用。
- 未覆盖项：无（本窗结论已下，等返工构建）。
