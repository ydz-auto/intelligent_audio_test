# frontend-react 前端开发规范

本文档定义智能语音测试平台 UX 重设计 React 应用（`frontend-react/`）的开发规范与最佳实践，供开发与 AI 助手共同遵循。基准为 newAPI `web/AGENTS.md`（228 行），按本平台技术栈**逐节适配**（pnpm / 全中文硬编码 / VChart + chart.js 双库），业务专属项（钱包/密钥/订阅等不适用章节）已移除。具体依赖与脚本以 `package.json` 为准。

> **平台红线（react_dev.md 口径，逐条照办）**
> ① 只动 `frontend-react/` 与 `doc/UX设计规范/`；**不改 `frontend/`（Vue）任何文件**——Vue 与 React 并存，逐页替换是后续集成的事。
> ② 数据一律 mock 常量，**不接真实后端、不起后端服务**；API client 留 `TODO(API 接线)` 桩。
> ③ CSS/token/组件/交互件一律照搬 newAPI 现成实现（`D:\00_code\new_api_xagents\web\src\styles\*.css` + `web/src/components/ui/*`），逐文件等价移植，**不发明样式值**。
> ④ 文案**全中文**；多主题预设（theme-presets.css 全部预设，lake-view 默认）。
> ⑤ 绝对禁止改动主库 checkout `D:\00_code\V9.7.31\Intelligent-Audio-TEST`（design/deepseek-harness-migration 分支）。

---

## 一、项目概览

### 技术栈

| 类别       | 技术                                                                                       |
| ---------- | ------------------------------------------------------------------------------------------ |
| 包管理     | pnpm（`pnpm-lock.yaml` 入库）                                                              |
| 框架       | React 19、TypeScript                                                                       |
| 构建       | Rsbuild（`rsbuild.config.ts`；dev server 钉死 **5273** strictPort）                        |
| 数据与请求 | @tanstack/react-query、Zustand；axios 预留（真实后端未接，见 [3.6 API 请求](#36-api-请求)） |
| 路由       | @tanstack/react-router（文件路由 + autoCodeSplitting）                                     |
| 表格与列表 | @tanstack/react-table、@tanstack/react-virtual（基座规范 §1 选型，页面卡落地时补装）       |
| 文案       | **全中文硬编码**（无 i18n 框架、无 t()/i18n 键，见 [3.1 文案与格式化](#31-文案与格式化全中文硬编码)） |
| 日期       | 原生 `Intl` / `Date`（不装 dayjs；格式化用默认 locale）                                     |
| UI 与样式  | @base-ui/react（shadcn 风格封装）、Tailwind CSS 4、clsx / class-variance-authority          |
| 图标       | **双库照搬**：@hugeicons/react + @hugeicons/core-free-icons（ui 基元实际使用）+ lucide-react |
| 表单       | React Hook Form、Zod                                                                       |
| 图表       | @visactor/vchart + @visactor/react-vchart（通用图表）+ **chart.js v4 + chartjs-plugin-zoom**（报告域正态分布/缩放，见 [3.1](#31-文案与格式化全中文硬编码) 图表分工） |
| 深浅色/主题 | next-themes（三态）+ `theme-presets.css` 全部 10 套预设（lake-view 默认）                   |
| 弹层       | sonner（toast）；vaul（抽屉）/ cmdk（命令面板）基座规范 §1 选型，页面卡落地时补装           |
| 字体       | @fontsource-variable/public-sans（正文）+ @fontsource-variable/lora（衬线标题）             |
| 测试       | vitest + @testing-library/react + jsdom + @vitest/coverage-v8（INT-477 已落地）             |

优先复用项目已有组件与能力（见 [3.3 组件](#33-组件)）；项目内无合适实现时，再评估已安装依赖及成熟、维护良好的开源库。仅在复用、组合或合理扩展仍无法满足需求时自行实现，并说明具体能力缺口。

### DDD 四层（基座规范 §10，开发/审查必读）

```
src/
├─ app/                    # 应用装配（组合根）：providers.tsx（ThemeProvider + ThemeCustomizationProvider + QueryClientProvider + RouterProvider）、router.ts（beforeLoad 权限守卫）
├─ components/             # 展示层（interfaces 层职责）：ui/（照 newAPI 逐文件移植的基元）、layout/、common/（report-chart 等页级通用件）
├─ features/               # 按页组织（页面卡逐张产出，内含 components/ lib/ hooks/ 及入口组件）
├─ application/            # 应用层（用例 hooks，TanStack Query，如 use-task-detail / use-report-charts）
├─ domain/                 # 领域层（零依赖；models/ camelCase 域模型 + enums）
├─ infrastructure/         # 基础设施层：api/（请求桩）+ adapters/（chartConfig、deviceAdapter 等）+ dto/（snake_case↔camelCase）+ http/ + auth/（hasPermission）+ stores/（zustand）+ mock/（桩数据）+ storage/ + content/
└─ styles/                 # index.css、theme.css（:root + .dark 语义 token）、theme-presets.css（10 预设 + 五轴）
```

依赖规则：`components/features` → `application` → `domain/infrastructure` 单向（**domain 零依赖**、不 import 上层）；`ui/` 纯 props 组件不 import 上层。字段命名契约（前端只见 camelCase Domain、infrastructure 唯一知 snake_case）见基座规范 §10.1（INT-385 拍板结果为准，拍板前实施不强制返工）。

---

## 二、目录

- [一、项目概览](#一项目概览)
- [二、目录](#二目录)
- [三、开发规范](#三开发规范)
  - [3.1 文案与格式化（全中文硬编码）](#31-文案与格式化全中文硬编码)
  - [3.2 代码风格与类型](#32-代码风格与类型)
  - [3.3 组件](#33-组件)
  - [3.4 性能](#34-性能)
  - [3.5 状态管理](#35-状态管理)
  - [3.6 API 请求](#36-api-请求)
  - [3.7 表单](#37-表单)
  - [3.8 路由](#38-路由)
  - [3.9 错误处理](#39-错误处理)
  - [3.10 样式](#310-样式)
  - [3.11 文件组织](#311-文件组织)
  - [3.12 可访问性](#312-可访问性)
  - [3.13 安全](#313-安全)
  - [3.14 测试](#314-测试)
  - [3.15 依赖管理](#315-依赖管理)
  - [3.16 构建与部署](#316-构建与部署)
- [四、协作与提交](#四协作与提交)
- [更新日志](#更新日志)

---

## 三、开发规范

### 3.1 文案与格式化（全中文硬编码）

- **页面文本**：所有面向用户的文案一律**中文硬编码**，直接写入组件或常量；**不引入 i18n 框架、无 `t()`/i18n 键、无 `useTranslation()`**（负责人 2026-10-16 拍板暂不启用多语言；若未来启用，本节另立契约）。
- **专有名词**：品牌、产品、技术术语等可保留英文（如 API、React、TypeScript、Benchmark、ASR）；中文语境下约定俗成的术语使用中文。
- **常量中的文案**：各 feature 的 `constants.ts` 中「枚举/状态 + 展示文案」或「成功/错误消息」直接存中文文案字符串；展示时直接使用该常量，**无 i18n 键登记环节**（无 `static-keys.ts`、无翻译扫描）。
  - 成功/错误/提示类消息（如 `SUCCESS_MESSAGES`、`ERROR_MESSAGES`）：常量值为最终中文文案，例如 `toast.success('保存成功')`、`toast.error('删除失败：请先停止运行中的任务')`。
  - 状态/选项的 label：常量中直接存中文 label（如「运行中」「已通过」），组件直接渲染。
- **数字/日期格式化（强制）**：
  - 普通数字、紧凑数字展示优先复用 `@/lib/format` 的 `formatNumber` / `formatCompactNumber`；本平台暂无金额/余额/额度类业务（newAPI 钱包类封装不适用），不得从 newAPI 引入 `@/lib/currency`。
  - 格式函数**直接使用默认 locale**（即 `Intl.NumberFormat()` / `toLocaleString()` 不传 `locales` 参数，或调用 `formatNumber(value)` 省略 `locales`），不传语言码——本平台单语言，**无 `zhCN`/`zhTW` 语言码映射层、无 `toIntlLocale()` 转换**（与 newAPI 3.1 的强制转换链不同，勿照抄）。
  - 明确使用固定协议格式的场景（如日志时间戳）可显式传 `undefined` 或固定选项。
- **图表库分工（INT-439 裁定，勿混用）**：
  - **通用图表（仪表盘/首页统计等）**：`@visactor/vchart` + `@visactor/react-vchart`（`<VChart />`，配置封装在 feature 的 `lib/vchart.ts`）。
  - **报告域图表**：**chart.js v4 + chartjs-plugin-zoom**（`src/components/common/report-chart/` 的 ChartComponent/ChartStatsCard/ChartActions；`infrastructure/adapters/chartConfig.ts` 色值映射 `--chart-1..5`）。正态分布图依赖前端自算均值/标准差/正态曲线 + zoom/pan 重分箱 + 统计卡，**VChart 无法等价**，一律用 chart.js。
  - 新增图表前先判断所属域：报告域 → chart.js 生态；其他页 → VChart。禁止在同一域内混用两库。
- **多主题联动**：图表颜色走语义 token（`--chart-1..5` 随预设联动）；chart.js 用 `chartConfig.colors` 等价 hex 常量与 `theme.css` 保持映射。

### 3.2 代码风格与类型

- **表达式**：禁止 2 层及以上嵌套三元表达式；改用 `if-else`、提前返回或抽取函数。单层三元可保留，但需简洁。
- **可读性**：控制函数圈复杂度，复杂逻辑拆成小函数；变量与函数命名需有意义，遵循驼峰等常规约定。
- **TypeScript**：避免 `any`，优先具体类型或 `unknown`；为参数与返回值显式标注类型；仅类型用途的导入使用 `import type { X } from '...'`。
- **类型检查**：每次改动 TypeScript 或 TSX 代码后都要执行 `pnpm typecheck`；若出现类型错误，须修复至无错误为止，不得遗留。
- **Lint 检查**：本仓库暂未接入 newAPI 的 oxlint/oxfmt（lint/format 脚本落地前），以 `pnpm typecheck` + `pnpm build` 零错误为门禁；照搬代码时注意修复新产生的警告，不得遗留 error。
- **解构**：对象非必要不要进行解构，特别是组件的 props；直接使用 `props.xxx` 更清晰，避免不必要的解构增加代码复杂度。

### 3.3 组件

**先检索，再复用，最后才新增（强制）**

- **开发前检索**：新增或修改 UI 前，必须检索 `src/components/ui/`（照 newAPI 逐文件移植的基元，基座规范 §5：首批 27 基元 + ConfigDrawer，总清单 53 项按页面卡分批补齐）和相关 `src/features/`；涉及通用交互时同时检查 `src/components/common/`、`src/components/layout/` 与 `src/hooks/`。按用途和行为查找，不能只查准备新增的组件名。阅读候选组件的实现、props 和实际调用示例后再确定方案。
- **复用顺序**：优先使用满足场景的项目业务封装（feature 内已有组件/`src/components/common/`）；能力不足时，先评估现有 props、插槽、组合方式或兼容扩展。业务封装确实不适用时，再用 `src/components/ui/` 中已有基础组件组合。项目内仍有能力缺口时，才评估引入组件或新增实现。
- **复用到行为层**：仅使用 `Button`、`Dialog`、`AlertDialog` 等基础组件，不代表已经复用了对应的复制、确认、弹窗布局等通用能力。已有业务封装能覆盖时，必须使用该封装，禁止在 feature 内重新拼装同一套交互、状态和样式。
- **新增条件**：新增替代实现前，必须明确候选组件缺少的具体能力，并在变更说明或 PR 中记录候选路径及不能复用、组合或兼容扩展的原因。文案、图标、尺寸、颜色或所在页面不同，不构成重复实现的理由；优先通过已有 API 和主题约定处理这些差异。
- **合理组合**：允许新增承载业务数据、权限、事件和内容的 feature 组件，但其中的通用 UI 与交互必须继续复用。扩展公共组件需保持已有调用行为，不能为单个页面塞入无关业务逻辑，也不能为消除少量相似代码建立过度通用的抽象。
- **基础元素边界**：业务代码中，已有基础组件覆盖的按钮、输入框、选择器、弹层等控件，必须使用项目组件，不能手写同等控件或直接绕过封装调用底层库。普通语义化布局、隐藏字段及现有组件无法表达的特殊控件可使用原生元素；特殊控件仍须说明能力缺口并满足可访问性要求。
- **等价移植红线**：`src/components/ui/` 与 `src/styles/` 一律照 newAPI 现成实现**逐文件等价移植**，不发明样式值、不自行改 token；平台化差异仅限中文文案。

以下为常用检索入口，不能把本表当作完整组件清单：

| 场景                         | 优先检查的项目入口                                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------------- |
| 通用弹窗布局                 | `src/components/ui/dialog`、`sheet`                                                      |
| 删除、危险操作及普通确认     | `src/components/ui/alert-dialog`、`dialog`                                               |
| 复制按钮与剪贴板交互         | `src/components/ui/`（button/tooltip）+ `@/hooks/use-copy-to-clipboard`（页面卡落地时对齐） |
| 空状态、加载状态、错误状态   | `src/components/ui/empty`、`skeleton`、`spinner`、`src/components/common/`               |
| 表格、分页、工具栏及列表布局 | `src/components/ui/table` + @tanstack/react-table（页面卡落地时补装）                     |
| 图表                         | 通用 → feature 的 `lib/vchart.ts`（VChart）；报告域 → `src/components/common/report-chart`（chart.js） |
| 按钮、输入、选择、提示等基元 | `src/components/ui/`（以本地实现为准，与基座规范 §5 表格对位）                           |
| 主题设置抽屉                 | `src/components/config-drawer.tsx`（预设色卡 + 五轴）                                    |

- 使用函数式组件与 Hooks，单一职责；组件 props 须有明确类型（接口或类型别名）。
- **Props 使用**：组件 props 非必要不要解构，直接使用 `props.xxx` 访问属性，保持代码清晰（详见 [3.2 代码风格与类型](#32-代码风格与类型)）。
- 单文件超过约 200 行时考虑拆分子组件或将逻辑抽到自定义 Hooks；类型定义可与组件同文件或放在同模块的 `types` 中。

### 3.4 性能

- **React**：合理使用 `useMemo`、`useCallback` 减少无效重渲染；避免在渲染路径中创建新对象/数组；必要时使用 `React.memo`。
- **代码分割**：TanStack Router 已开启 `autoCodeSplitting`（rsbuild.config.ts 生产环境）；页面按路由自动按需加载，控制首屏与路由体积。
- **资源**：图片选用合适格式与尺寸，大列表考虑虚拟滚动（@tanstack/react-virtual），大量图片考虑懒加载。

### 3.5 状态管理

- 使用 Zustand 的 `create` 定义 store，并为 state 与 actions 定义清晰类型；store 文件统一放 `src/infrastructure/stores/`（照基座规范 §10 DDD 落位），单文件职责清晰，命名表意明确。
- 组件内优先用选择器订阅，避免整 store 订阅导致多余渲染，例如：`const user = useAuthStore((s) => s.auth.user)`。
- 需持久化的状态在 store 内读写 localStorage（如 `src/lib/theme-storage.ts`，iatp 前缀），并在初始化时恢复。

### 3.6 API 请求

- **红线④（当前阶段）**：数据一律 mock 常量，**不接真实后端、不起后端服务**。mock 数据放 `src/infrastructure/mock/`（dashboard-mock、tasks-mock、reports-mock、ai-chat-mock、test-execution-mock 等），形态对照真实接口 schema（`api_gateway/schemas/`，接线时字段不返工）；`src/infrastructure/api/client.ts` 为统一请求桩，标注 `TODO(API 接线)`。
- **React Query（mock 阶段即可用）**：数据获取用 `useQuery`，变更用 `useMutation`；用例 hooks 归 `src/application/`；为每个查询配置唯一 `queryKey`（建议数组形式、层级一致）；在 `onSuccess` 中对相关 query 做 `invalidateQueries`，可配合乐观更新。
- **接线时**：统一请求出口走 `src/infrastructure/http`（拦截器、`withCredentials`、错误码映射、SSE 订阅）；`src/infrastructure/api` 是唯一知道后端 snake_case 的层，DTO 转换在 `src/infrastructure/dto/`（见基座规范 §10.1 字段命名契约）；服务端错误统一通过错误处理函数处理（详见 [3.9 错误处理](#39-错误处理)）。
- 数据获取逻辑不得写在组件内联 fetch；一律走 application 层 hooks + infrastructure 层客户端/桩。

### 3.7 表单

- 使用 React Hook Form + Zod：在功能模块的 `lib/` 下定义 schema，并用 `z.infer` 导出表单类型；`useForm` 配合 `@hookform/resolvers/zod` 做校验。
- 提交逻辑放在 `onSubmit`，展示加载与错误状态；成功后视场景重置表单或关闭弹窗。服务端校验错误映射到对应字段并展示（字段级错误展示方式见 [3.9 错误处理](#39-错误处理)）。
- 表单控件一律用 `src/components/ui/` 基元（Field/Label/Input/Select/Checkbox/Switch 等），禁止手写同等控件。

### 3.8 路由

- 使用 TanStack Router，路由文件位于 `src/routes/`，通过 `createFileRoute` 定义；搜索参数用 Zod schema + `validateSearch` 校验。
- 在 `beforeLoad` 中做认证与 RBAC 重定向（`meta.permission` → 无权限跳 403 错误页），避免不必要的请求；嵌套结构用布局路由与 `_authenticated` 等前缀，子路由通过 `<Outlet />` 渲染（登录页/首页/关于/文档公开，其余重定向登录页）。
- 导航使用 `useNavigate` 或 `Link`，保持类型安全，避免直接操作 `window.location`。
- 路由树与页面归属见基座规范 §9 与 `doc/UX设计规范/00_页面清单与RBAC划分.md`。

### 3.9 错误处理

- **服务端错误（接线后）**：统一错误处理函数（`handleServerError` 等价物），优先保留服务端具体原因；禁止把完整 Axios 错误对象（可能包含凭据）直接写入控制台。共享 QueryClient 在 Query/Mutation 最终失败时提示；Mutation 自定义 `onError` 负责自己的提示或表单错误。
- **提示归属**：普通请求拦截器不弹 Toast；自动重试期间和主动取消时不报错；`meta.errorToast: false` 关闭自动提示，页面仍可主动调用错误处理函数。
- **业务失败**：保留原始 API 响应契约；Query 使用 `requireServerSuccess` 检查 `success: false`，或在业务层用 `createServerError` 抛错并保留来源。需要展示失败状态的 Mutation 不得把失败结果当作保存成功。
- **展示**：使用 `toast`（sonner）等统一方式；路由级错误由 `errorComponent` 承接，提供友好错误页（403/404/500，归 `src/features/errors/`）并记录便于排查的信息。
- **表单**：校验与服务端错误映射到字段后，在字段下方展示；使用 `form.setError` 等与表单库一致的方式。

### 3.10 样式

- 以 Tailwind 工具类为主，动态类名用 `cn()` 合并；非动态场景避免内联样式。
- 响应式采用移动优先与 Tailwind 断点（`sm:`、`md:`、`lg:` 等）；主题与暗色用 CSS 变量与 `dark:`，自定义样式集中在 `src/styles/`（index.css / theme.css / theme-presets.css），组件内尽量少写自定义 CSS。
- **不发明样式值**：色值、间距、圆角、阴影、层级、动效一律照 newAPI 等价移植，多主题语义 token 随 `--chart-1..5` 等预设联动（基座规范 §3/§4/§6）。
- **深浅色三态 + 多主题**：深浅色走 `next-themes` 三态（light/dark/system）；主题预设走 ConfigDrawer（10 套预设 + radius/scale/font/contentLayout 五轴，lake-view 默认），主题状态由 `src/lib/theme-customization.ts` + `theme-storage.ts` 持久化。

### 3.11 文件组织

- **功能模块**：置于 `src/features/<feature>/`，内含 `components/`、`lib/`、`hooks/`，以及按需的 `api.ts`、`types.ts`、`constants.ts`、入口组件等（mock 阶段无真实 `api.ts` 时以 `src/infrastructure/mock/` 对应数据为准）。
- **DDD 四层归属**：展示层（interfaces）= `src/components/` + `src/features/`；应用层 = `src/application/`（用例 hooks、TanStack Query）；领域层 = `src/domain/`（零依赖 camelCase models + enums）；基础设施层 = `src/infrastructure/`（api/adapters/dto/http/auth/stores/mock/storage/content）。依赖单向：`components/features → application → domain/infrastructure`（见基座规范 §10）。
- **通用**：通用组件放 `src/components/`，通用工具与类型放 `src/lib/`；组件文件 PascalCase，工具/类型文件 kebab-case 或 `types.ts`，类型使用 PascalCase 命名并 `export type`。

### 3.12 可访问性

- 使用语义化 HTML（如 `header`、`nav`、`main`、`footer`），表单用 `label` 关联输入。
- 保证键盘可操作与焦点顺序合理；必要时使用 ARIA（如 `aria-label`、`aria-expanded`、`aria-hidden`）；装饰性图标加 `aria-hidden="true"`，重要信息提供文本等价。
- 对比度满足 WCAG 2.1 AA（正文至少 4.5:1）。
- 涉及可访问性的组件（dialog、tooltip、dropdown、switch 等）必须覆盖可访问名称、键盘可操作性与视觉状态一致的 ARIA 属性（见 [3.14 测试](#314-测试)）。

### 3.13 安全

- 认证与权限在路由（`beforeLoad` meta.permission）与接口层校验；RBAC 判定用 `hasPermission` / `hasAnyPermission`（照 authStore 逻辑移植，支持 `*` 通配，归 `src/infrastructure/auth/`）；敏感操作增加二次确认（AlertDialog）等。
- 前后端均做数据校验（如 Zod），不信任仅前端校验；敏感信息不落前端存储，配置用环境变量，禁止硬编码密钥。
- 依赖 React 默认转义，慎用 `dangerouslySetInnerHTML`；markdown 渲染走 `marked` + `dompurify` 清洗（`src/components/ui/markdown`）。跨域与 Cookie 使用 `withCredentials` 并按后端要求处理 CSRF（接线时）。
- 禁止把完整 Axios 错误对象（可能包含凭据）写入控制台或日志。

### 3.14 测试

> 落地依据：INT-477 测试体系搭建（vitest + @testing-library/react，`vitest.config.ts` include `src/**/__tests__/*.{test,spec}.{ts,tsx}`，覆盖率 v8 含 `src/features`/`src/components`/`src/application`/`src/lib`）。

- 工具函数与纯逻辑优先单元测试（Vitest），测试文件 `*.test.ts`；组件用 React Testing Library 测交互与行为，避免测实现细节。
- 新增功能、修复缺陷或修改现有行为时，必须同步新增或更新测试；Bug 修复必须先编写能够稳定复现问题的失败用例，再实现修复并确认用例转为通过。
- 修改前端组件的布局、尺寸、滚动定位、焦点管理、键盘操作、选中状态、禁用状态、加载状态、空状态、错误状态或响应式行为时，必须补充对应的回归测试，覆盖本次变更保护的用户可见行为，防止后续调整重新引入问题。
- 功能模块或组件模块的测试必须放在该模块专属的 `__tests__/` 目录中，例如 `src/features/reports/components/__tests__/report-card.test.tsx`；禁止将新增测试文件与正式代码文件平铺在同一目录。
- 测试文件按被测职责命名，例如 `layout.test.ts`、`selection.test.ts`、`validation.test.ts`；一个测试文件只覆盖一个明确模块或职责，避免形成跨模块的超大测试文件。
- 每个测试用例应只保护一个可描述的行为，名称必须包含触发条件和预期结果；优先使用 Arrange、Act、Assert 的清晰结构，避免在单个用例中混合多个无关断言。
- 测试必须覆盖主要成功路径以及本次变更涉及的关键边界和失败路径，包括空数据、单项和多项数据、超长文本、无效输入、禁用状态、异步失败与降级逻辑；不得为了数量机械枚举不相关输入。
- 布局测试应断言明确且稳定的行为契约，例如固定尺寸、排列方向、溢出策略、滚动目标和降级路径；不要仅断言组件能够渲染，也不要依赖浏览器像素误差、浏览器私有实现或脆弱的完整 class 字符串快照。
- 组件交互测试应从用户视角查询元素并执行点击、输入、键盘和焦点操作，断言可见结果、可访问状态或对外回调；禁止直接断言组件内部 state、私有函数调用次数或无用户意义的 DOM 层级。
- 涉及可访问性的组件必须覆盖可访问名称、键盘可操作性，以及 `aria-expanded`、`aria-selected`、`aria-disabled`、`aria-invalid` 等与视觉状态一致的属性。
- **文案断言**：本平台文案全中文硬编码，测试可用稳定中文文案或角色/label 定位元素；**禁止**将「某语言完整展示文案」视为脆弱断言（无多语言切换场景，此条为中文文案的稳定化要求）。
- 异步测试必须等待明确的界面状态或 Promise 结果，不得使用固定 `sleep`、依赖执行耗时或制造竞态；定时器、网络请求和浏览器 API 仅在必要边界进行可控 mock，并在每个用例后恢复。
- 优先测试真实代码路径；只有外部网络、时间、随机数、存储或浏览器 API 等不可控边界可以 mock。禁止 mock 被测模块自身，也不要通过复制生产逻辑到测试中计算期望结果。
- 测试数据应使用最小且具有业务含义的显式 fixture，测试内部必须独立初始化并清理全局状态、缓存、localStorage、mock 和定时器，确保用例可单独运行且不依赖执行顺序。
- 快照测试仅适用于稳定且人工可审查的结构输出；交互组件、复杂 DOM 和 Tailwind class 列表不得使用大范围快照代替行为断言。
- 关键流程补充集成与 E2E（如 MSW 模拟 API、Playwright/Cypress）；核心功能目标覆盖率 80% 以上，关注业务路径与关键分支。
- 测试必须保护真实用户行为、稳定 API 契约或明确回归路径；禁止为了覆盖率添加 smoke、sleep/timing、随机输入、日志输出或只证明代码运行的测试。
- 新增或大幅重写测试时优先使用 Vitest 与 React Testing Library 的标准断言和查询方式，避免手写通用断言辅助函数；只有表达项目特定业务不变量时才抽取测试 helper。
- 清理测试时先合并重复场景、删除不明不白的实现细节断言；若旧测试间接覆盖了真实契约，需替换为更小、更直接的行为测试。
- 提交前必须至少运行受影响测试文件（`pnpm test` 或 `pnpm test -- <file>`），并根据影响范围执行相关测试集、`pnpm typecheck` 和构建；不得在未看到最新通过结果的情况下声明测试完成。

### 3.15 依赖管理

- 使用 **pnpm**：`pnpm install`、`pnpm add <pkg>`、`pnpm add -D <pkg>`、`pnpm remove <pkg>`、`pnpm update` 等；`pnpm-lock.yaml` 必须入库（与 `package.json` 同步变更）。
- 新增依赖前评估维护情况、体积与许可；生产与开发依赖区分清楚，版本用 `^`/`~` 控制，定期更新以获取安全修复。
- 版本基准：照 newAPI `web/package.json` 实测值（见基座规范 §1）；补装 TanStack Table/virtual、vaul、cmdk 等时以 newAPI 对应版本为准。

### 3.16 构建与部署

- 使用 Rsbuild，配置见 `rsbuild.config.ts`；脚本以 `package.json` 为准（`pnpm dev`、`pnpm build`、`pnpm typecheck`、`pnpm test`、`pnpm preview`），包管理见 [3.15 依赖管理](#315-依赖管理)。
- **Dev server**：钉死端口 **5273**（strictPort，失败即报错，禁止静默漂移）；3000 被 newAPI 参照实例占用、5173 属 Vue 主前端家族，不得占用。
- 代码分割与懒加载策略见 [3.4 性能](#34-性能)（TanStack Router autoCodeSplitting）；资源使用合适格式与压缩，环境变量用 `.env` 且以 `VITE_` 前缀（接线时），不在代码中硬编码。
- **发布前（交付自检）**：执行 `pnpm typecheck` 零错误 + `pnpm build` 零错误，mock 阶段还需核对浏览器逐页可视稿与对应设计规范（`doc/UX设计规范/`）；不接后端、不起服务，交付物为可视稿。

---

## 四、协作与提交

- **提交范围**：只 commit 不 push，commit 落在 `design/ux-redesign` 分支；交付评论列出 commit 范围与改动文件。绝对禁止改动主库 checkout（`D:\00_code\V9.7.31\Intelligent-Audio-TEST`）与 `frontend/`（Vue）文件。
- 提交信息清晰、符合项目约定，描述变更内容与原因，中英文统一即可；结束提交信息需附署名行 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 变更需经过代码审查，符合本文档规范，并关注质量、性能与安全。
- **复用审查**：UI 变更完成前必须检查新增组件、基础组件导入及手写交互是否绕过已有业务封装；发现重复实现应在本次变更范围内改为复用。保留的新实现需在变更说明中说明能力缺口，typecheck、build 和测试通过不能替代此项检查。
- **页面交付标准**：`pnpm i && pnpm dev` 可起，浏览器逐页可看（出图先，可视稿即交付物）；每页对照对应设计规范逐项落地（布局分区/组件/中文文案/主题切换/深浅色）；组件树与 DDD 四层落位符合基座规范 §10；mock 数据形态对照真实接口 schema（`api_gateway/schemas/`），接线时字段不返工。
- 重大功能或规范变更时更新相关文档与 `AGENTS.md`。

---

## 更新日志

- **2026-10-16**：初始版本——移植 newAPI `web/AGENTS.md` 适配本平台（INT-480）：包管理 Bun→**pnpm**；国际化 i18next→**全中文硬编码**（§3.1，含图表库 VChart + chart.js 分工）；引用本平台红线（只动 frontend-react/、mock 不接后端、照 newAPI 等价移植、中文文案）与 DDD 四层落位；§3.14 测试规范与 INT-477 vitest 落地联动；移除 newAPI 钱包/密钥/订阅等业务专属章节。
