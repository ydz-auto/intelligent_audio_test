## INT-1106 返工交回（P1 已修复 + P3 顺带）

### P1 修复：DimensionSelect 面板浮于模态遮罩之上
`.ds-panel` z-index 由 `var(--z-index-popover)`(1200) 提到 **21000**（照 ColumnFilter popover 约定，注释「模态窗遮罩 z-index 为 13000，弹层需在其之上」），算法配置模态窗内「关联维度 / 参数映射」下拉不再被 50% 黑遮罩压暗、选项可正常点击选择。用例/开始测试页 facet 不受影响（面板仍正常，21000 与 ColumnFilter 同口径全场景可用）。

### 实测证据（dev server :5511，连常驻后端 :5000，admin/admin123 真实数据）
- **elementsFromPoint 命中探测**（面板中心）：4 处（关联维度/参数映射 × 浅/深）首元素均为 `.ds-option`（面板选项），**非 modal-overlay**；面板计算 z-index = 21000 > 遮罩 13000。
- **真实鼠标点击**：每处点击一个与当前值不同的维度选项，面板关闭 + 触发器值改变（4/4 `changed:true`，例：`话轮接管` → `└ 逐字转写评测`）。写接口（`/algorithm/dimension-relations`、`/algorithm/mappings`）在测试中以 200 成功响应截断，**不改库**；console 零报错。
- 截图：关联维度/参数映射 面板打开态 浅色+深色 各一张（本评论附件）。

### P3 顺带
- `.ds-badge` `border-radius: 3px` 硬编码 → `var(--radius-tag)`（审计建议口径）。
- `TestCaseListContainer.ts:123` 缺换行格式瑕疵已修。
- `.ds-badge/.ds-chevron/.ds-section-count/.ds-count-badge/.ds-option-branch` 的 9/10/11px 字号与 React `text-[9px]` 等 arbitrary 值对应、现 tokens 无此档位：**保留现状，留 CSS 架构卡统一补 token**（审计 P3 原话口径）。

### 提交
- 分支 `agent/vue-c/int-1106`，提交 `e6bc0e3e`「INT-1106 返工: DimensionSelect 面板 z-index 提至 21000 浮于模态遮罩之上 + 徽章圆角走 --radius-tag + TestCaseListContainer 格式修正」（上一轮 `4a9ce74a` 之上）。

### 自测
- `npm run build`（VITE_AUTH_MODE=dev）零错误。
- vitest：1003 passed / 6 failed（`home.loadErrorState`、`logView.loadErrorState` 为 V9.7.31 带入的 INT-288/INT-743 既有不适配，与本卡无关；本卡相关 AlgorithmConfig/Evaluation/test-case 套件全过）。
