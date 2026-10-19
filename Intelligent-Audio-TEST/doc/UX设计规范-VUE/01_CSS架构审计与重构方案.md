# 01_CSS架构审计与重构方案（UX设计-VUE · 样式管理）

> 卡 INT-757 ｜ UX设计师C ｜ 2026-10-18 ｜ 性质：**CSS 管理方式重构方案**——全面审计 `frontend/src` 样式现状（数据说话），照 newAPI `web/src/styles` 的管理方式给出可拆卡的重构方案；**视觉保持原 Vue**（负责人 2026-10-18：「VUE 项目的 CSS 管理非常混乱，全面审计一遍，然后重构，可以同样照 new api 的来」；「视觉保持原 Vue 风格（负责人更喜欢原来的样子）」）。
> 范围：只读代码、只产文档；本卡不改任何样式代码。
> 审计对象（只读）：`frontend/src` 全部样式来源（`.css` / `.vue <style>` / 内联 style / JS 拼样式）。
> 参照基准（只读）：newAPI `D:\00_code\new_api_xagents\web\src\styles\{index.css,theme.css,theme-presets.css}` + `web/src/lib/theme-customization.ts` + `web/src/components/ui/` 样式归属方式。
> 前置关联：INT-756（全站圆角统一，in_progress）——本方案圆角轴并入其产出；INT-735~745（在办页面实施卡）——先后关系见 §4。

---

## 0. 结论摘要（TL;DR）

- **现状是「半迁移态」**：Tailwind 4 + 语义令牌（tokens.css）基础设施已经就位（`index.css:6-11`、`tokens.css`），但 **38 个存量全局样式文件仍经 `main.css` 聚合器全局注入**（`main.css:5-60` 共 39 条 `@import`，含 1 条 fontawesome），组件内还有 30 个组件旁 `.css` + 约 1.6 万行 `<style scoped>` 内联样式；**Tailwind 原子类几乎未被采用**（全库语义色类出现仅 6 处）。
- **硬编码与冲突严重**：业务 CSS 散落 293 处 hex 色值、677 处 `border-radius`、4973 处 px 字面量；`!important` 169 处（重灾：`splMapping.css` 59、`HistoryReports.css` 18、`AlgorithmConfigModal.css` 14）；通用类名（`.btn-primary` 16 个文件、`.form-group` 12 个、`.modal-footer` 13 个等）跨文件重复定义，全靠全局加载顺序压胜——「谁靠后谁赢」。
- **token 层不完整**：tokens.css 只定义了颜色/布局/圆角，**间距（832 处引用）、字号（265）、阴影（136）、动效（155）、z-index（5）五大家族只存在于 variables.css**；另有 **18 个「用了没定义」的变量**（`--font-size-2xl/3xl/base`、`--spacing-2xl`、`--gray-lightest-color`、`--color-emerald-300`、`--danger-dark`、`--text` 等）。
- **深浅色零启用**：`.dark` 仅在 `tokens.css:251-289` 预留，全库**没有任何切换逻辑**（无 `classList.add('dark')`、无主题 store）。
- **重构方向（照 newAPI）**：单入口 `index.css` → 主题令牌（theme.css）→ base/reset（`@layer base`）→ 组件样式收敛到 `<style scoped>` + 共享组件样式（对应 newAPI `components/ui` 的样式归属）；`main.css` 聚合器逐域拆解后删除；完成 tokens.css 缺失家族；启用浅/深两套（**单品牌主题，非多预设**，遵循 00 总表 §1.2「不引入多主题预设体系」）；补 stylelint 守规则。
- **视觉不变是硬约束**：所有值取自原 Vue 现状（见 §2.2 映射表），每张迁移卡验收为「同页重构前后截图像素级对比」（§3）。

---

## 1. 审计（全量，数据 + 证据）

### 1.1 样式来源全量盘点

**总量**：`frontend/src` 共 **83 个 `.css` 文件、30,685 行**；**169 个 `.vue`**（157 个含 `<style>` 块、12 个无样式）、`<style>` 内容 **15,927 行**；352 处静态内联 `style="..."` + 48 处 `:style` 动态绑定。

**83 个 `.css` 按位置分**：

| 位置 | 数量 | 行数合计 | 说明 |
| --- | --- | --- | --- |
| `assets/styles/` | 42 | 12,912 | 全局存量库（聚合器 `main.css` 引入 38 个） |
| `components/**`（组件旁） | 30 | 12,186 | 组件私有样式，经 `<style scoped>@import` 或 script `import` 引入 |
| `views/**`（页面旁） | 11 | 5,587 | 页面私有样式，3 个经 `<style src>`（**非 scoped**）引入 |

**引入方式（实测 `main.ts:4` / `index.css` / `main.css` / `.vue`）**：

```
main.ts:4  import './assets/styles/index.css'          ← 全局唯一入口
index.css:6-11  @import 'tailwindcss'; @import './tokens.css'; @import './main.css'; @source '../../'
main.css:5-60   39 条 @import（38 个存量 css + fontawesome）→ 全部全局注入
.vue 内：38 处 @import 组件旁 .css（9 处与 <style scoped> 同行）；script import 实 4 处（main.ts:4 + report-filter-card ×3）
           3 处 <style src="...">（Home.vue:172 / ReportView.vue:430 / TagManagement.vue:320，非 scoped）
```

- **聚合器现状**：`main.css:5-60` 把 `api-test/*`(5) `components/*`(14) `device/*`(2) `e2etest/*`(2) `layouts/main.css` `reports/*`(2) `tasks/*`(5) `test-case-manager/*`(4) `test-common.css` `reset.css` `variables.css` 共 38 个文件全部全局注入；**不管哪个页面，全部加载**。
- **例外**：`assets/styles/components/report-filter-card.css` 不在 `main.css`，由 3 个报告组件各自 import（`CaseCategoryComparisonComponent.vue:277` / `CaseTagComparisonComponent.vue:259` / `SpecificCaseComparisonComponent.vue:402`）——这是唯一「按组件加载」的正例。
- **重复加载风险**：除上述正例外，未发现同一文件经「全局 + 组件」双通道重复引入（`main.css` 之外的直接 assets 引用只有 report-filter-card）。
- **scoped 分布**：154 个 `<style scoped>`；**6 个非 scoped**：`<style src>` ×3（home.css 1119 行 / reportView.css 634 行 / tagManagement.css 427 行，**选择器全局泄漏**）+ 裸 `<style>` ×3（`AlgorithmSelectionPanel.vue:262` 空壳；`AddTestCaseModal.vue:138` 的 `.modal-backdrop`、`BatchSplModal.vue:110` 的 `.modal-overlay` 为全局泄漏的模态遮罩样式）。Vue 非 scoped `<style>` 编译后进全局 bundle——home.css 的 `.home-page*`（218 处行首选择器）、reportView、tagManagement 的规则全部全局可见。
- **双重置**：`index.css` 已引入 Tailwind 4 `preflight`（`@import 'tailwindcss'`），`main.css:5` 又引入自研 `reset.css`（357 行）——两套 reset 叠加，基色/边框被先后重置。

### 1.2 token 审计

**两个 token 文件并存**：

| 文件 | 行数 | 定位（文件内自述） |
| --- | --- | --- |
| `assets/styles/tokens.css` | 289 | 「语义化设计令牌（照 newAPI web/src/styles/theme.css 结构）」；`@theme inline` 映射 Tailwind 色板；`:root`/`.dark` 双主题；**只含颜色 + 布局 + 圆角** |
| `assets/styles/variables.css` | 147 | 「旧变量兼容别名层（迁移期专用）」；**颜色旧名→语义令牌别名 + 非颜色 token 原样保留**（间距/字号/阴影/动效/z-index 全在这） |

**数字**：
- 两文件合计定义 **294 个**自定义属性；全库 `var(--x)` 使用 **257 个唯一名**。
- **重复定义（同语义多名字 / 同值两处）**：
  - `--success-light: rgba(82,196,26,0.1)` 在 `tokens.css:113` 与 `variables.css:24` **各定义一次**；
  - `--secondary-light: #e3f2fd` 在 `tokens.css:112` 与 `variables.css:15` 各一次；
  - 布局四件套 `--sidebar-width/--header-height/--footer-height/--page-margin/--content-min-width` 在 `tokens.css:122-127` 与 `variables.css:72-76` **重复**；
  - 状态色三别名：`--warning`（tokens.css:75）/ `--warning-color`（variables.css:23）/ `--pending-color`（variables.css:129）；`--destructive`（tokens.css:77）/ `--error-color`（variables.css:27）/ `--danger-color`（variables.css:29）；`--info`（tokens.css:79）/ `--info-color`（variables.css:133）/ `--in-progress-color`（variables.css:132）——同一语义 3 个名字。
- **定义了没用的**：`--color-neutral-*`、`--color-yellow-400/800` **实际已被 `var()` 引用**（neutral-50/100、yellow-400/800 有业务消费）；真「定义未用」是另 **36 个** `@theme` 声明（如 `--color-accent`/`--color-chart-1~5`/`--color-amber-700` 等——Tailwind `@theme` 声明本身是供给层，但业务侧 0 消费）。
- **用了没定义的（18 个，均有文件:行号证据）**：

| 变量 | 使用处（代表） |
| --- | --- |
| `--font-size-2xl` | `components/common/audio/AudioListComponent.css:859` |
| `--font-size-3xl` | `AudioListComponent.css:887,970` |
| `--font-size-base` | `views/HistoryReports/HistoryReports.css:101` |
| `--font-weight-regular` | `views/LogView/LogArchivePanel.vue:282` |
| `--spacing-2xl` | `AudioListComponent.css:880,965` |
| `--gray-lightest-color` | `components/common/test-case/TestCaseListContainer.css:32` |
| `--danger-dark` | `AudioListComponent.css:675` |
| `--danger-hover` | `views/TagManagement/tagManagement.css:405` |
| `--active-bg` | `tagManagement.css:154` |
| `--badge-bg` | `tagManagement.css:180` |
| `--bg-color` | `components/task/TaskDataExportDialog.vue:99`、`TaskDataImportDialog.vue:222`、`tagManagement.css:10` |
| `--border-hover` | `tagManagement.css:275` |
| `--card-bg` | `views/ReportView/sections/BenchmarkReportPanel.vue:343`、`tagManagement.css:69,267` |
| `--hover-bg` | `tagManagement.css:150` |
| `--font-family-mono` | `components/benchmark/BenchmarkBadges.vue:68`、`MetricGroupCard.vue:185`、`SubjectLeaderboard.vue:105,123` |
| `--font-mono` | `components/layout/TestExecutionComponent.vue:396`（内联 style） |
| `--color-emerald-300` | `components/common/modal/BatchAnnotationModal.css:340`（tokens.css 只声明了 emerald-100/500/600/800） |
| `--text` | `views/ReportView/sections/BenchmarkReportPanel.vue:347,408,473`（带回退 #1f2937） |

  > 多数带 `var(--x, 兜底值)` 回退未致崩坏，但回退值本身就是硬编码（见 1.3）；`--danger-dark`、`--font-size-2xl/3xl`、`--spacing-2xl`、`--gray-lightest-color` 无回退，样式已失效（字体会落到继承值 / 背景透明）。
  > 注：审计后 INT-745 公共页新增 `--foreground-deep` 引用（`views/UserGuide/UserGuide.vue:331`，带回退 #1a1a1a），未计入上表基线，随 CSS-1 收编。

- **家族缺口（关键）**：tokens.css 未定义间距/字号/阴影/动效/z-index，这五大家族的唯一正源在 variables.css：`--spacing-*`（variables.css:63-69，全库 832 处引用）、`--font-size-*`（:49-55，265 处）、`--shadow-*`（:88-91，136 处）、`--transition-*`（:94-96，155 处）、`--z-index-*`（:99-102，5 处）——**「一套语义变量」目前名不副实，语义层只做了一半**。
- **z-index 值域与变量体系脱节**：实际写死值含 `14000`(5 处)、`15000`、`10001`、`9999`(2)、`1050`(2)（见 1.3），而 variables.css 只定义了 1000/3000/10000/13000 四档——`--z-index-modal-top:13000` 之下已有 14000 在用，体系必须扩档。

### 1.3 硬编码（数值 + 按文件排行）

**颜色**：
- hex：**293 处**（其中 tokens.css 内 185 处为令牌定义本身；剔除后业务 CSS 仍有 **~86 处散落** + variables.css 22 处别名值）。
- `rgba()/rgb()`：21 处（如 `rgba(15,23,42,0.55)` `CherryPickDialog.css:6`、`rgba(15,23,42,0.3)` :20）。
- **半迁移回退模式**：`var(--x, #hex)` 带色值回退 **54 处**（`var(--primary, #ff6a00)` 13 处、`var(--color-slate-500, #64748b)` 6 处、`var(--border-color, #e2e8f0)` 6 处……）——说明存量文件已在「token 化 + 留硬编码尾巴」。

**按文件排行（业务 CSS，硬编码颜色数）**：

| 排行 | 文件 | 色值数 | 代表行 |
| --- | --- | --- | --- |
| 1 | `components/common/modal/CherryPickDialog.css` | 58 | :6,14,20,29,54-56,64 |
| 2 | `views/Evaluation/Evaluation.css` | 6 | — |
| 3 | `components/common/misc/TestCaseReportDetail.css` | 6 | — |
| 4 | `components/common/form/FormField.css` | 4 | — |
| 5 | `components/common/audio/AudioListComponent.css` | 4 | :675（`--danger-dark` 未定义） |
| 6 | `views/Home/home.css` / `TimelineComparison.css` 等 | 3 | — |

**圆角**：`border-radius:` 共 **677 处**；top 值：`6px`(98)、`8px`(93)、`var(--border-radius-md)`(87)、`4px`(72)、`12px`(59)、`var(--border-radius-lg)`(39)、`var(--border-radius-full)`(39)、`50%`(39)、`16px`(19)、`10px`(17)、`3px`(15)、`20px`(11)、`var(--border-radius-md, 8px)`(6)……——**6px/10px/3px/20px 不在任何 token 值域内**（INT-756 圆角轴需决策收编）。

**间距/字号**：全库 px 字面量 **4,973 处**；top 值 `12px`(625)、`8px`(582)、`1px`(491)、`16px`(420)、`4px`(338)、`6px`(287)、`2px`(265)、`14px`(252)、`24px`(224)、`20px`(238)……；`font-size` 写死 `14px`(216)、`12px`(159)、`13px`(134)、`16px`(63)、`11px`(40)、`18px`(34)、`24px`(29)。

**阴影**：`box-shadow:` 共 200+ 处；`var(--shadow-sm)`(57)/`var(--shadow-md)`(26)/`var(--shadow-lg)`(18) 之外仍有写死阴影（`0 0 0 3px var(--primary-light)` 9 处、`0 0 0 3px color-mix(...)` 7 处、`0 2px 8px color-mix(...)` 18 处等）。

**z-index**：写死 11 档值：`1000`(11)、`1`(10)、`10`(7)、`14000`(5)、`2`(4)、`100`(4)、`9999`(2)、`10000`(2)、`15000`(1)、`1050`(1)、`10001`(1) 等。

**内联样式**：静态 `style="..."` 352 处 + `:style` 48 处；代表如 `TestExecutionComponent.vue:396`（内联写 `font-family: var(--font-mono)`——未定义变量）、`DataTable.vue` 系列（:6,:14,:61 动态表格样式）。

### 1.4 冲突与覆盖

- **`!important` 共 169 处**；按文件：`views/splMapping/splMapping.css` **59**、`views/HistoryReports/HistoryReports.css` **18**、`components/algorithm/AlgorithmConfigModal.css` **14**、`views/Evaluation/Evaluation.css` **12**、`TestCaseListContainer.css` 10、`test-case-manager/category.css` 8、`components/common.css` 8……（`splMapping.css:21-30` 整块 10 连 `!important`）。
- **通用类名跨文件重复定义**（同一顶层选择器出现在 N 个文件，全局加载时后 import 覆盖前）：

| 类名 | 出现文件数 | 代表文件 |
| --- | --- | --- |
| `.btn-secondary` | 17 | `components/button.css`、`AudioListComponent.css`、`api-test.css`、`common.css`、`reports/base.css`、8 个模态窗 css…… |
| `.btn-primary` | 16 | 同上 |
| `.modal-footer` | 13 | `components/modal.css`、`audioImport.css`、`splMapping.css`、4 个模态窗 css…… |
| `.form-input` | 15 | `components/form.css`、`main.css:120`、`test-case-manager.css`、`DynamicForm.css`…… |
| `.form-group` | 12 | `components/form.css`、`FormField.css`、`DynamicForm.css`、`ImportExportModal.css`…… |
| `.search-box` | 11 | `layouts/main.css`、`toolbar.css`、`Evaluation.css`、`AudioListComponent.css`…… |
| `.empty-state` | 8 | `test-common.css`、`CaseForm.css`、`e2etest.css`…… |
| `.checkbox-label` | 8 | `components/log.css`、`button.css`、`UploadFileModal.css`…… |
| `.card-header` | 7 | `card.css`、`device.css`、`reports/base.css`、`AudioListComponent.css`…… |

- **全局泄漏**：`<style src>` 非 scoped 注入的 `home.css`（`.home-page*` 族 218 处行首选择器）、`reportView.css`、`tagManagement.css`；`main.css:62-222` 自身就带一段全局覆写（`.filter-bar/.toolbar-filters/.device-toolbar/.form-input` 系列 + `!important`，如 :75）。
- **`:deep()` 滥用**：**0 处**（Vue 3 scoped 隔离正常，无穿透依赖）。
- **第三方覆盖**：Font Awesome 本地引入（`main.css:8`），无第三方 UI 库样式需覆盖；Tailwind preflight 已全局生效（见 1.1 双重置）。

### 1.5 深浅色

- `.dark` 仅在 `tokens.css:251-289` 定义，文件内注释明示「结构预留（照 newAPI 双主题设计），项目当前未启用 .dark」。
- **切换逻辑为零**：全库 grep `classList.*dark` / `'dark'` / `theme` store 均无命中（0 处）；无 `next-themes` 等价物、无 `prefers-color-scheme` 响应。
- **不跟主题的点**：所有硬编码色值（1.3）在深色下不会变；`variables.css:35 --text-disabled:#cccccc`、`--btn-secondary-bg` 渐变（variables.css:112）等固定浅色；大量 `box-shadow` 阴影写死黑透（深色下阴影不可见）。
- 现有 `.dark` 色板为灰色系（`#2a2a2a/#333`），与 00 总表 §1.1 保留的「dark 主色 `#ff8c3b` / 背景 `#2a2a2a`」一致——本次重设计启用。

### 1.6 死代码

- **Tailwind 原子类几乎零采用**：全库模板中语义色类（`bg-primary/text-foreground/bg-card/...`）仅 **6 处**命中；`@theme inline`（tokens.css:14-63）映射出的色板目前**无人消费**。
- **`main.css` 聚合器**：38 个存量文件全局注入后，多数页面只用到其中一小部分（如 `device.css` 只在设备页用、`api-test/*` 只在 API 测试用），却全量随首屏加载。
- **重复 reset**：`reset.css`（357 行）与 Tailwind preflight 重复（1.1 双重置）。
- **变量冗余**：`--text-disabled`、`--text-light`、`--text-tertiary`、`--text-muted` 四名近义（tokens.css:86-87 / variables.css:35,121）；`--card-bg`/`--bg-color`/`--active-bg` 等未定义名只在带回退处生效。
- 1 个空壳裸 `<style>`（`AlgorithmSelectionPanel.vue:262`）可删；另 2 个裸 `<style>`（`AddTestCaseModal.vue:138` / `BatchSplModal.vue:110`）为全局泄漏的模态遮罩样式，收敛进 scoped 或共享件（见 §2.4 规则 1）。

### 1.7 与 newAPI 对照（照它的管理方式，不照它的外观）

newAPI 实测（`web/src/styles/` + `web/src/lib/` + `components/ui/`）：

| 层 | newAPI 做法（实测出处） | 我们现状 | 差距 |
| --- | --- | --- | --- |
| 入口 | 单入口 `styles/index.css`：`@import 'tailwindcss'` + shadcn + 字体 + theme.css + theme-presets.css；`@layer base/components/utilities` 分层（`index.css:57,73,362`） | `index.css` 单入口已建（`index.css:6-11`），但无 `@layer` 分层（全库 `@layer` 0 处） | 入口有了，分层缺失 |
| 令牌 | `theme.css`：`:root` + `.dark` 全家族语义令牌（颜色/圆角/字体/骨架/表格 50+ 项）+ `@theme inline` 映射 Tailwind 色板（`theme.css:21-94`） | tokens.css 抄了结构，但**只有颜色/布局/圆角**，间距/字号/阴影/动效/z-index 仍在 variables.css（§1.2） | 令牌家族缺 5 项 |
| 主题预设 | `theme-presets.css`：`[data-theme-preset='xxx']` 10 套预设，每套含浅/深两色板 + 默认 `--radius`（`theme-presets.css:73` rose-garden 等）；`lib/theme-customization.ts` 预设注册表；`context/theme-customization-provider.tsx:132/149/156` 把 `data-theme-preset/radius/scale` 写到 body | 无预设文件；`.dark` 预留未启用；无 provider | **本平台单品牌双色，不做 10 预设**（00 总表 §1.2）；但要补「浅/深两套 + 切换入口」 |
| 深浅色 | `context/theme-provider.tsx` 切换 `.dark` 类 | 零切换逻辑（§1.5） | 需补切换机制（右上角入口见 INT-703 总表 §2.4） |
| 组件样式 | `components/ui/*.tsx` **0 个 .css 文件**，样式全在 `cva()` + Tailwind 原子类 + `cn()` 里（`button.tsx:26-65`）；全局只剩 base/工具类 | 30 个组件旁 .css + 1.6 万行 `<style scoped>`；组件样式散落且含硬编码 | 组件样式**归属组件**的方向一致（scoped 即归属），但要「值全部走令牌 + 消灭硬编码」；不强制改 Tailwind 原子类（视觉照原 Vue） |
| 工具类 | `@utility` 自定义工具类（`index.css:259-329`：container/no-scrollbar/hover-scrollbar/fade-*） | 0 处 `@utility`；业务 CSS 自造类名但无规则约束 | 可少量补充平台级工具类（如 `.scrollbar-thin`） |
| 规则 | 硬编码仅出现在高亮/渐变等故意场景，`!important` 仅用于覆盖第三方（`index.css:123-135` shiki、:151-153 json-editor） | 169 处 `!important` 业务覆盖链（§1.4） | 必须降噪 |
| lint | 未实测 stylelint 配置；但有 vitest 组件测试守护（`components/ui/__tests__`） | 无 stylelint（package.json 无相关依赖） | 补 stylelint + 截图回归 |

**核心差距一句话**：newAPI 是「token 全家族 → 组件内原子类消费，全局只剩 base」；我们是「token 半家族 + 全局 38 文件聚合器 + 组件内硬编码」。重构 = 补齐 token 家族 + 把全局聚合器逐域拆回组件/共享层 + 全库硬编码收敛到令牌，**值不动、视觉不动**。

---

## 2. 重构方案（照 newAPI 管理方式，视觉保持原 Vue）

### 2.1 目标结构（样式目录与分层）

```
frontend/src/assets/styles/
  index.css            ← 唯一全局入口（已有，微调）：
                          @import 'tailwindcss'; @import './theme.css'; @import './theme-presets.css';
                          @import './base/index.css'; @import './main.css';   // main.css 迁移期聚合器，逐域拆解后删除
  theme.css            ← 【基座卡】语义令牌全家族（= 现 tokens.css 补齐间距/字号/阴影/动效/z-index，
                          圆角轴并入 INT-756）+ @theme inline + :root/.dark 双色板；值全部取自原 Vue 现状
  theme-presets.css    ← 【基座卡】浅/深两套组织（本平台单品牌，不引入多预设）：
                          .dark { ... } 按 newAPI theme-presets.css 的「预设块 + .dark 子块」结构组织，
                          但只保留本平台一套品牌色板（主色 #ff6a00 / 次色 #1976d2 / dark #ff8c3b）
  base/
    reset.css          ← 并入 @layer base（与 Tailwind preflight 合并，删重复规则）
    base.css           ← body/滚动条/字体基线等平台基础（对应 newAPI index.css @layer base）
  main.css             ← 【迁移期】存量聚合器：每拆一个域就删一批 @import，全部拆完删除
  components/          ← 【迁移期】共享组件样式（button/form/modal/table/log/...）
                          迁移目标：被具体组件按需 import（如 report-filter-card.css 的正例），不进全局
  pages/               ← 【迁移期】页面样式（迁移目标：进各视图 <style scoped> 或就近组件样式）
```

**分层职责与谁能改（对应 newAPI 文件）**：

| 层 | 放什么 | 谁能改 | 对应 newAPI |
| --- | --- | --- | --- |
| token | 全部设计决策值（颜色/圆角/阴影/间距/字号/动效/z-index） | 基座/UX 规划师 | `styles/theme.css` |
| 主题预设（浅/深） | 双色板切换、品牌色变体 | 基座/UX 规划师 | `styles/theme-presets.css` |
| base / reset | 元素默认样式、reset、平台基础 | 基座工程师 | `index.css @layer base` |
| 组件 | 每个组件的私有样式（`<style scoped>`）+ 少量共享件（被组件 import） | 页面工程师 | `components/ui/*`（样式归属组件） |
| 页面 | 每个视图的私有样式（`<style scoped>`） | 页面工程师 | `features/*`（样式就近） |

### 2.2 token 体系（一套语义变量，值全部取自原 Vue 现状）

**目标**：tokens.css 升级为 theme.css，补齐全家族；variables.css 降级为纯兼容别名层（迁移完成后删除）。**所有新值 = 现 variables.css/tokens.css 的现值，零漂移**。

**旧变量 → 新语义变量映射表（颜色类已由 variables.css 部分建立，此为全量清单）**：

| 旧名（variables.css / 散落） | 新语义名（theme.css） | 现值（原 Vue 实测） | 出处 |
| --- | --- | --- | --- |
| `--primary-color` | `--primary` | `#ff6a00` | tokens.css:67 |
| `--primary-dark` | `--primary-hover` | `#e65c00` | tokens.css:68 |
| `--primary-light` | `--accent` | `rgba(255,106,0,.1)` | tokens.css:88 |
| `--secondary-color` | `--secondary` | `#1976d2` | tokens.css:70 |
| `--secondary-dark` | `--secondary-deep` | `#0958d9` | tokens.css:71 |
| `--secondary-light` | `--secondary-light` | `#e3f2fd` | tokens.css:112 |
| `--success-color` / `--success-border` | `--success` | `#52c41a` | tokens.css:73 |
| `--success-light` | `--success-light` | `rgba(82,196,26,.1)` | tokens.css:113 |
| `--warning-color` / `--pending-color` / `--pending-border` | `--warning` | `#ffa940` | tokens.css:75 |
| `--warning-light` / `--pending-light` | `--warning-light` | `rgba(255,169,64,.1)` | tokens.css:115 |
| `--error-color` / `--danger-color` | `--destructive` | `#f5222d` | tokens.css:77 |
| `--error-light` / `--danger-light` | `--destructive-light` | `rgba(245,34,45,.1)` | tokens.css:117 |
| `--info-color` / `--in-progress-color` | `--info` | `#1976d2` | tokens.css:79 |
| `--info-light` | `--info-light` | `rgba(25,118,210,.1)` | variables.css:134（提级） |
| `--text-primary` | `--foreground` | `#333333` | tokens.css:83 |
| `--text-secondary` / `--text-muted` | `--muted-foreground` | `#777777` | tokens.css:85 |
| `--text-light` / `--text-tertiary` | `--text-light` | `#999999` | tokens.css:86-87 |
| `--text-disabled` | `--text-disabled` | `#cccccc` | variables.css:35（提级） |
| `--gray-color` | `--gray` | `#737373` | tokens.css:98 |
| `--gray-light-color` / `--background-tertiary` / `--disabled-bg` / `--background-hover` | `--gray-light` | `#f0f0f0` | tokens.css:99 |
| `--border-color` / `--border-color-light` | `--border` | `#e5e7eb` | tokens.css:90 |
| `--background-primary` / `--input-bg` | `--background` | `#ffffff` | tokens.css:93 |
| `--background-secondary` | `--muted` | `#f5f5f5` | tokens.css:84 |
| `--white-color` | `--color-white` | `#ffffff` | tokens.css:246 |
| `--dark-color` | `--foreground` | `#333333` | tokens.css:83 |
| 状态遗留：`--btn-secondary-hover` | `--secondary-light` | `#e3f2fd` | variables.css:125 |
| `--font-size-xs…xxxl` | `--font-size-xs…xxxl` | `12/14/16/18/20/24/32px` | variables.css:49-55（**提级入 theme.css**） |
| `--font-weight-normal/medium/semibold/bold` | 同左 | `400/500/600/700` | variables.css:57-60 |
| `--spacing-xs…xxxl` | 同左 | `4/8/16/24/32/48/64px` | variables.css:63-69（**提级入 theme.css**） |
| `--shadow-sm/md/lg/xl` | 同左 | `0 1px 3px…` / `0 4px 12px…` / `0 8px 24px…` / `0 16px 48px…` | variables.css:88-91（**提级入 theme.css**） |
| `--transition-fast/normal/slow` | 同左 | `0.2s/0.3s/0.5s ease` | variables.css:94-96（**提级入 theme.css**） |
| `--z-index-dropdown/modal/modal-top/tooltip` | 同左（**扩档**） | `1000/10000/13000/3000` + 实测补 `14000/15000/10001` 档 | variables.css:99-102（**提级入 theme.css**，值域对齐 §1.3） |
| `--border-radius-sm/md/lg/xl/xxl/full` | `--radius-sm/md/lg/xl/xxl/full`（`--radius` 派生，**并入 INT-756 圆角轴**） | `4/8/12/16/24/9999px` | variables.css:80-85 + INT-756 |
| `--card-border/--card-radius/--card-shadow/--card-shadow-hover` | 合成层保留（引用 `--border/--gray-light`、`--radius-xl`、`--shadow-md/lg`） | — | variables.css:105-108 |
| `--btn-*`（bg/height/padding/border-radius） | 合成层保留 | — | variables.css:111-117 |

> 补充决策：§1.3 实测的 `6px/10px/3px/20px` 圆角、`#94a3b8/#64748b/#dc2626` 等高频散色——由 **INT-756 圆角轴 + 基座卡**按「值保真」收进色阶/圆角档（如 `--radius-md:8px` 与 6px 并存则新增 `--radius-6` 或并入 xxl 档，以 INT-756 定案为准）。**每收编一个值，就删一处硬编码**。

### 2.3 工具类层（Tailwind 4 评估）

**现状**：Tailwind 4 已安装并接入（`package.json` `tailwindcss ^4.3.3` + `@tailwindcss/vite`，`vite.config.ts:35`），`index.css` 已 `@import 'tailwindcss'` 且 `@source '../../'` 已配（`index.css:11`）。

**建议：保留 Tailwind 4，但定位为「令牌桥 + 可选糖」而非强制范式**：
- ✅ 继续用作 **preflight reset**（替代自研 reset.css，见基座卡）。
- ✅ 继续用作 **`@theme inline` 令牌桥**（tokens.css 已做，把语义变量映射成 `bg-primary` 等原子类）——**这是照 newAPI 的关键**：newAPI 正是靠 `theme.css` 的 `@theme inline` 让组件用原子类消费 token。
- ⚠️ **不强制存量组件改用 Tailwind 原子类**：视觉保持原 Vue、`<style scoped>` 是 Vue 惯用形态（对照 00 总表 §1.2「不引入 React/newAPI 样式」）。**新页面/新组件可选用**原子类（与令牌桥打通），存量只做「硬编码→令牌」收敛。
- 与 Vite 兼容：`@tailwindcss/vite` 已在跑，构建影响为既有状态（`main.css` 39 条 `@import` 的打包压力在迁移期消除，Tailwind 本身开销可忽略）。迁移成本≈0（无需装新依赖）。
- 不引入则退化为「少量手工工具类约定」：如 `.scrollbar-thin`、`.text-ellipsis`、`.flex-center` 等 3~5 个平台级 `@utility`（照 newAPI `index.css:259-329`）。**推荐先做这批 @utility**，无论 Tailwind 采用与否都有用。

**结论：引入（已引入，维持），优先级 P1 的只有令牌桥与 base 层；原子类采用度作为 P3 软目标。**

### 2.4 组件样式规则 + lint

**强制规则（写进 stylelint + 卡验收）**：
1. **`<style scoped>` 是唯一组件样式通道**：禁止裸 `<style>`、禁止 `<style src>` 非 scoped（存量 3 处 Home/ReportView/TagManagement 转 scoped 或把类名收敛到组件前缀）。
2. **禁止硬编码设计值**：颜色（hex/rgb/hsl）、圆角、阴影、间距、字号、z-index 一律 `var(--…)`；渐变、透明度组合可用 `color-mix(in srgb, var(--x) n%, transparent)`（newAPI 同款手法）。
3. **禁止业务 `!important`**：只允许覆盖第三方/内联样式的白名单场景（如全局提示条），逐一注释原因。
4. **禁止全局选择器泄漏**：组件内选择器必须以组件根类为前缀（`.task-card .title` 而非裸 `.title`）。
5. **内联 `style`/`:style`**：只允许动态布局值（宽/高/位置/百分比），颜色与静态样式不得内联。
6. **`:deep()` 仍禁用**（现状 0，保持）。
7. **合成层**（如 `--card-*`、`--btn-*`）只放 components 共享样式，页面样式不得再造合成变量。

**stylelint 配置建议（`frontend/stylelint.config.mjs`）**：

```js
export default {
  extends: ['stylelint-config-standard', 'stylelint-config-recess-order'],
  overrides: [
    {
      files: ['src/assets/styles/theme*.css'], // token/预设文件豁免
      rules: { 'color-no-hex': null, 'declaration-no-important': null },
    },
  ],
  rules: {
    'color-no-hex': [true, { severity: 'warning' }],        // 业务 CSS 禁 hex（token 文件豁免）
    'declaration-no-important': [true, { severity: 'warning' }], // 禁 !important
    'custom-property-pattern': '^--[a-z][a-zA-Z0-9-]*$',     // 变量命名
    'no-duplicate-selectors': true,                          // 禁跨文件重复类
    'no-descending-specificity': null,                        // 存量太深，先关
    'selector-max-compound-selectors': [5, { severity: 'warning' }],
    'custom-property-no-missing-var': true,                  // 用未定义变量即报（§1.2 的 18 个现形）
  },
}
```
> 建议依赖：`stylelint` + `stylelint-config-standard` + `stylelint-config-recess-order`（devDependencies 现无 stylelint）。CI/`npm run lint:css` 接入；存量告警先 warning 后逐步降 0。

### 2.5 迁移计划（可并行拆卡）

**原则**：基座卡先行（token 全家族 + 双色板 + base + 公共件壳 + lint），之后按域并行；每张卡「**只搬值、不改值**」，验收 = 同页截图像素级对比（§3）。

**卡清单**：

| 卡 | 名称 | 文件范围（现状） | 依赖 | 执行人 | 验收 |
| --- | --- | --- | --- | --- | --- |
| CSS-0 | **基座卡**：theme.css 全家族（含 INT-756 圆角轴并入）、theme-presets.css 浅/深、base/reset 合并、index.css 收敛、`@utility` 首批、stylelint 接入、`.dark` 启用开关（配合右上角主题切换入口） | `assets/styles/{index.css,tokens.css→theme.css,variables.css,reset.css,main.css 的 reset 段}`；**不动页面/组件业务 css** | INT-756（圆角）先落 | Vue基座工程师 | 全站抽查 5 页截图无变化 + stylelint 0 新错 |
| CSS-1 | 工作台/测试执行/公共页域样式收敛 | `views/{Home,APITest,E2ETest,TestFlow,TestReports,BenchmarkRanking,Login,NotFound}` 旁 css + `components/{layout,benchmark,benchmark-report}/*.css` + 相关 `tasks/` | CSS-0；INT-736/737/745 合并后 | Vue页面工程师（对应页） | 每页重构前后截图对比 |
| CSS-2 | 任务域/用例域/设备域样式收敛 | `views/{Tasks,TestCaseManager,Evaluation,Device,AudioImport,SPLMapping,TagManagement}` 旁 css + `components/{task,test-case,published-task,algorithm?}/*.css` + `assets/styles/{tasks/*,test-case-manager/*,device/*,e2etest/*,components/{test-case-card,tag,dropdown-multi-select}}` | CSS-0；INT-738/739/740 合并后 | Vue页面工程师 | 同上 |
| CSS-3 | 报告域/AI工作台/配置运维/个人中心样式收敛 | `views/{ReportView,HistoryReports,OAuthProviders,Account,LogView,AlgorithmConfig}` 旁 css + `components/report/*.css` + `assets/styles/{reports/*,api-test/*,layouts/main.css,components/{comparison-common,report-filter-card,log,progress,navigation}}` | CSS-0；INT-741/742/743/744 合并后 | Vue页面工程师 | 同上 |
| CSS-4 | **收尾**：variables.css 别名层删除、`main.css` 聚合器清零删除、死代码清理（3 空壳 style、双 reset、未用变量） | `variables.css`、`main.css`、全部存量遗留 | CSS-1~3 全落 | Vue基座工程师 | 全站截图回归 + `grep` 无残留旧变量 |

> 与在办页卡（INT-735~745）关系：**CSS-0 与页面实施卡并行安全**（纯增量 token/主题/base，旧别名继续可用，实施卡可直接消费新 token）；**CSS-1~3 排在对应 INT-73x 之后**——那些卡正在重写同一批页面文件，避免互踩（§4 详述）。

**每张域卡的内部步骤**：
1. `git status` 确认工作区干净、目标文件未被在办卡占用；
2. 迁值：硬编码→语义 token（查 §2.2 映射表；表中没有的值先补进 theme.css 再引用，**值原样**）；
3. 拆搬：全局聚合器里的该域样式 → 组件 `<style scoped>` 或「被组件 import 的共享 css」（照 report-filter-card 正例），从 `main.css` 删除对应 `@import`；
4. `!important` 逐个降噪（查来源、能去则去，留则注释）；
5. 跑 stylelint + 构建 + 截图对比。

---

## 3. 视觉不变验证方法（明确写出）

1. **截图对比（主法）**：用 Playwright 脚本固定视口 `1920×1080`，对**同一路由、同一测试数据**分别拍摄重构前/后整页截图；用 `pixelmatch` 做像素级 diff，容差 `≤0.1%` 差异像素视为通过；关键交互件（模态窗/下拉/空态/loading）单独补拍。截图基线由 CSS-0 卡建立（重构前快照），每张域卡取自己域内页面对比。
2. **计算样式抽查**：对代表性组件断言 `getComputedStyle` 关键值不变（如主按钮 `color/background/border-radius/height`），防止「看着像但值漂了」。
3. **构建守护**：`npm run build`（vue-tsc + vite）零错误；stylelint 该域文件 0 新告警。
4. **令牌漂移守护**：`grep -rE '#[0-9a-fA-F]{3,8}'` 业务 css 该域清零（除 theme 文件）；`grep -r '!important'` 该域归零或全注释。
5. **CSS 变量完整性守护**：`custom-property-no-missing-var`（stylelint）保证无「用了没定义」。

---

## 4. 与在办卡（INT-735~745 / INT-756）的先后关系

| 在办卡 | 与本卡关系 |
| --- | --- |
| **INT-756（圆角统一，in_progress）** | 圆角轴的**上游**：CSS-0 的 `--radius-*` 值域以 INT-756 定案为准（§2.2 圆角行「并入 INT-756」）；CSS-0 排在 INT-756 之后启动，或两卡按「INT-756 先出 token、CSS-0 再并入」接力。 |
| **INT-735（基座壳，in_progress）** | 与 CSS-0 共享 `App.vue`/壳样式边界：CSS-0 **不碰**壳文件（token/base/公共件），壳的样式收敛留给 CSS-1 且排在 INT-735 合并后；实施卡可直接用 CSS-0 的 token。 |
| **INT-736~745（页面实施卡）** | 同域文件重叠：CSS-1~3 **必须排在对应 INT-73x 合并之后**（先落地的实施卡会重写页面，重建时直接按新 token 规范写，天然完成大半收敛）；CSS-0 先行提供 token 供实施卡消费，避免实施卡继续写硬编码。 |
| **00 总表（INT-703）** | 本方案与总表 §1.1 保留清单（tokens/variables/Fa/Inter/组件库）一致；§1.2「不引入多预设/Public Sans」本方案遵守（仅浅/深两套）。 |

> **拆卡建议给 UX 规划师**：按 §2.5 的 CSS-0~4 建 5 张实施卡（或并入 INT-756 后只建 CSS-1~4）；卡面引用本文件 §2.2 映射表 + §2.4 规则 + §3 验收。

---

## 5. 附：审计证据索引（文件:行号速查）

| 证据 | 位置 |
| --- | --- |
| 单入口链 | `frontend/src/main.ts:4`、`assets/styles/index.css:6-11` |
| 全局聚合器 39 条 @import | `assets/styles/main.css:5-60` |
| 全局覆写块 + !important | `assets/styles/main.css:62-222`（:75） |
| .dark 预留未启用 | `assets/styles/tokens.css:250-289` |
| 旧变量别名层 | `assets/styles/variables.css:1-6` |
| 非 scoped 页面 css 泄漏 | `views/Home/Home.vue:172`、`views/ReportView/ReportView.vue:430`、`views/TagManagement/TagManagement.vue:320` |
| 未定义变量使用 | `AudioListComponent.css:675,859,880,887,965,970`、`HistoryReports.css:101`、`LogArchivePanel.vue:282`、`TestCaseListContainer.css:32`、`tagManagement.css:10,150,154,180,275,405`、`BatchAnnotationModal.css:340`、`TestExecutionComponent.vue:396` |
| 硬编码重灾 | `CherryPickDialog.css:6,14,20,29,54-56,64` |
| !important 重灾 | `views/splMapping/splMapping.css:21-30`（59 处全文件）、`views/HistoryReports/HistoryReports.css`（18） |
| 通用类跨文件重复 | `.btn-primary/.btn-secondary` 16/17 文件、`.modal-footer` 13、`.form-input` 15、`.form-group` 12、`.card-header` 7、`.search-box` 11（§1.4 表） |
| z-index 值域脱节 | 写死 14000/15000/10001（`grep -rh 'z-index'`）vs `variables.css:99-102` |
| Tailwind 原子类零采用 | 语义色类全库仅 6 处（`grep -rhoE 'class="[^"]*"'`） |
| 无 stylelint | `frontend/package.json`（devDependencies 无 stylelint） |
