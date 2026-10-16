# 排行榜页 UX 设计规范（对齐 newAPI rankings）

> 卡 INT-359 ｜ UX设计师B ｜ 2026-10-14（v1.1 修订 2026-10-15：算法切换口径改判 INT-442，见 §3.2；v1.2 修订 2026-10-16：INT-391 审核放行条件——文案全量改「排行榜」+ DTO→Domain 映射 + 未登录对齐 INT-344 + 基座节号勘误 + 权限码计数 5→6，见修订表；v1.3 修订 2026-10-16：INT-381 前置审核打回修订——Benchmark 报告域补全（§10）与 `infrastructure/adapters/*` 转换层，见修订表；v1.4 修订 2026-10-16：INT-429 RBAC 落地回写（§6.1 权限事实/§6.2 角色映射表改注）+ INT-391 复核收口对齐（§10 前端路由按 INT-344 v1.4 不新建 /benchmarks/*、写侧归属总控裁决、radius 校准）；v1.5 修订 2026-10-16：核心业务口径对齐——Hero 副标题显式落「多友商横向能力对比」、保留「按指标生成名次」（负责人 2026-10-16 口径），见修订表）｜ 基准：newAPI 参照源码 `D:\00_code\new_api_xagents`（web/src/features/rankings 全目录、web/src/routes/rankings、web/src/hooks/use-top-nav-links.ts、web/src/lib/nav-modules.ts、web/src/lib/use-chart-theme.ts、web/src/components/layout/components/public-layout.tsx｜public-navigation.tsx），本平台后端实测 `report_service/interfaces/api/benchmark_routes.py`、`api_gateway/routes/benchmark_bp.py`、`api_gateway/application/services/benchmark/benchmark_service.py`、`report_service/infrastructure/persistence/models/benchmark_models.py`、`report_service/application/services/benchmark_ranking_service.py`、`report_service/domain/entities/benchmark.py`、`scripts/migrations/202608/seed_rbac.py`，全部取材自实测源码，无杜撰。
> 背景裁定：benchmark 排行页**恢复设计**（原 2026-10-10 搁置裁定由负责人 2026-10-14 恢复，仅设计阶段）；版式照 newAPI 官方排行榜页（rankings）；**数据以 B 域 benchmark 钩子现状为准，后端没有的数据不虚构，缺口一律标注「待后端立项」**。
> 技术栈：React 19 + TS + Rsbuild + Tailwind 4 + shadcn 风格组件 + TanStack Router/Query + @visactor/react-vchart（newAPI 排行页图表同款依赖，`web/package.json:44-45` 实测 ^2.1.2）+ next-themes 深浅色（CSS/组件/交互件直接复用 newAPI 现成的，负责人 2026-10-14 裁定；多主题预设体系，lake-view 为默认参考预设——本文 token 均引基座卡 `01_全局基座.md` 的定义）。

---

## 1. newAPI 排行页布局结构（源码出处）

### 1.1 页面骨架

newAPI 排行页（/rankings）是「**公共数据页**」：不走登录后的侧栏壳，而是 PublicLayout（公共站头 + 正文 + 页脚），页面本体是「Hero（标题+周期下划线页签）+ 三块榜单卡」自上而下单列流，容器最宽 1280px。

| 部件 | 实现位置（newAPI 源码） |
| --- | --- |
| 路由（公开 + zod search 校验 + 模块守卫） | `web/src/routes/rankings/index.tsx`（`validateSearch` 校验 `period: today/week/month/year`；`beforeLoad` 经 `getModuleAccessForGuard('rankings')`：模块停用→重定向 `/`，要求登录未登录→`/sign-in?redirect=…`） |
| 页面骨架（背景光晕 + 容器 + Hero + 三块内容） | `web/src/features/rankings/index.tsx`（`Rankings`） |
| 公共外壳（站头/页脚，`showMainContainer={false}`） | `web/src/components/layout/components/public-layout.tsx`（`PublicLayout`） |
| Hero（标题 + 副标题 + 周期下划线页签） | `web/src/features/rankings/components/rankings-hero.tsx`（`RankingsHero`） |
| 「Top Models」主卡（堆叠柱图 + 双栏榜单） | `web/src/features/rankings/components/models-section.tsx`（`ModelsSection`） |
| 双栏模型榜单 | `web/src/features/rankings/components/model-leaderboard.tsx`（`ModelLeaderboard`，均分左右两列，`md:grid-cols-2 gap-x-8`） |
| 「Market Share」卡（100% 堆叠柱 + 厂商双栏列表） | `web/src/features/rankings/components/market-share-section.tsx`（`MarketShareSection`，厂商固定色板 `VENDOR_COLOURS` + 兜底 `FALLBACK_PALETTE`） |
| 「升降榜」双卡（上涨/下跌） | `web/src/features/rankings/components/pulse-section.tsx`（`PulseSection`，`lg:grid-cols-2`） |
| 实体链接（模型→/pricing/$modelId，厂商→/pricing?vendor=） | `web/src/features/rankings/components/entity-links.tsx`（`ModelLink`/`VendorLink`，细下划线常驻可点击提示） |
| 涨跌文案（↑303% / ↓12.4% / 0%） | `web/src/features/rankings/components/growth-text.tsx`（`GrowthText`，emerald/rose 双色 + `tabular-nums`） |
| 数字格式化（1.2B/42M/980K） | `web/src/features/rankings/lib/format.ts`（`formatTokens`/`formatShare`） |
| 数据获取（TanStack Query，staleTime 5min，可轮询） | `web/src/features/rankings/hooks/use-rankings.ts` + `api.ts`（`GET /api/rankings?period=…`，响应 `RankingsSnapshot`） |
| 类型（快照结构） | `web/src/features/rankings/types.ts`（models/vendors/top_movers/top_droppers/models_history/vendor_share_history） |
| 图表主题（VChart ThemeManager 懒加载，深浅色跟随） | `web/src/lib/use-chart-theme.ts`（`useChartTheme`） |
| 顶部导航入口 | `web/src/hooks/use-top-nav-links.ts:79-85`（`modules.rankings.enabled` → 导航项；本 fork 实测文案「Availability」指向 `/platform` 总览页，`/rankings` 为独立公开页——见 §2.2 入口映射） |
| 导航模块开关（enabled + requireAuth 双轴） | `web/src/lib/nav-modules.ts`（`HeaderNavModules.rankings: {enabled, requireAuth}`，来自后端 /api/status） |

### 1.2 视觉实测（摘自源码类名，token 名对齐 shadcn 变量）

- 背景光晕：`absolute inset-x-0 top-0 h-[600px] opacity-20 dark:opacity-[0.10]`，三层 `radial-gradient`（250°/200°/280° 色相椭圆）+ `maskImage: linear-gradient(to bottom, black 40%, transparent 100%)` 底部渐隐（index.tsx:95-108）。
- 容器：`PageTransition mx-auto w-full max-w-[1280px] space-y-8 px-3 pt-16 pb-10 sm:px-6 sm:pt-20 sm:pb-12 xl:px-8`（index.tsx:110）。
- Hero 标题：`text-[clamp(1.75rem,4vw,2.5rem)] leading-[1.15] font-bold tracking-tight`；副标题 `text-muted-foreground/80 max-w-2xl text-sm`（rankings-hero.tsx:47-54）。
- 周期页签（下划线式）：`role='tablist'`，容器 `border-border/60 flex items-center border-b`；页签 `relative -mb-px rounded-sm px-3 py-2 text-sm font-medium`；激活 `text-foreground` + 底部 `bg-foreground h-[2px]` 滑条，未激活 `text-muted-foreground hover:text-foreground`（rankings-hero.tsx:57-90）。
- 榜单卡：`bg-card overflow-hidden rounded-lg border`；卡头 `px-5 py-4`（图标+标题 `text-base font-semibold` 内联 `gap-2`，图标 `text-primary size-4`；说明 `text-muted-foreground mt-1 text-sm`；右侧统计 `font-mono text-2xl font-semibold tabular-nums` + 角标 `text-[10px] tracking-widest uppercase`）；图表区 `h-60 sm:h-72`（models-section.tsx:166-207）。
- 组内榜单块：`border-t` 分隔；小标题 `text-sm font-semibold` + Trophy 图标 `size-3.5 text-amber-500`；空态 `px-5 py-8 text-center text-sm text-muted-foreground/80`（models-section.tsx:210-229）。
- 榜单行：`flex items-center gap-3 py-2.5`；名次 `w-6 text-right font-mono text-xs tabular-nums text-muted-foreground/80`；主体名 `font-mono text-sm font-medium` 带 ModelLink 细下划线（`decoration-foreground/30 hover:decoration-foreground underline decoration-1 underline-offset-4`）；下行厂商 `text-xs italic text-muted-foreground/80`；右侧主值 `font-mono text-sm font-semibold tabular-nums` + 次行 GrowthText `text-[11px]`（model-leaderboard.tsx:72-136）。
- 升降榜行：`px-4 py-2`，右侧 `ArrowUpRight/ArrowDownRight size-3` + 位移数 `font-mono text-xs font-semibold`，上涨 `text-emerald-600 dark:text-emerald-400`、下跌 `text-rose-600 dark:text-rose-400`（pulse-section.tsx:111-146）。
- 图表轴文字/网格色：深色 `rgba(255,255,255,0.68)/0.12`、浅色 `rgba(15,23,42,0.58)/0.12`，虚线网格 `lineDash:[3,3]`（models-section.tsx:54-61）。
- 加载态：三段 Skeleton `h-[420px]/h-[360px]/h-[180px] rounded-xl`（index.tsx:120-128）。
- 错误态：`bg-card rounded-xl border border-dashed px-6 py-12 text-center`，标题 `text-base font-semibold` + 说明 `text-sm text-muted-foreground max-w-md`（index.tsx:130-142）。
- 站头（PublicHeader 实测，文档页卡 §1.2 同款）：未滚动 h-16 全宽，滚动 >20px 收胶囊 `max-w-[62rem] h-12 rounded-2xl bg-background/60 backdrop-blur-2xl`；右侧主题切换 + 登录按钮/头像下拉。

### 1.3 数据与交互机制（逐条实测）

1. 周期（today/week/month/year）写入 URL search（`navigate({search: prev => ({...prev, period: next})})`），刷新/分享可还原（index.tsx:51-56）。
2. `useRankings(period)` 单请求拉全量快照；`staleTime: 5*60*1000`；组件预留 `refetchInterval` 参数（当前页面未启用轮询）。
3. 三块内容全部由同一快照派生：模型榜（models+models_history）→ 厂商份额（vendors+vendor_share_history）→ 升降榜（top_movers/top_droppers）。
4. 图表渲染前等待 `themeReady`（VChart ThemeManager 切 light/dark），`key={…-${resolvedTheme}-${period}}` 主题/周期变化整图重建；`background: 'transparent'`。
5. 堆叠柱 tooltip：维度 tooltip 按值降序、最多 10 行，超出合并「+N more」，首行插「Total:」；份额图 tooltip 过滤 <0.1% 项、保留 1 位小数。
6. 模型名/厂商名是路由链接（/pricing 详情与 /pricing?vendor= 筛选），常驻细下划线做可点击暗示——榜单即导航。
7. 空态文案区分「无历史数据」「无匹配筛选」「无升降记录」三档。

---

## 2. 本平台 B 域 benchmark 能力现状（后端实测——本页数据契约）

> 本章是本页设计的唯一数据依据，全部取自后端实测源码。**后端没有的能力不进 UI，缺口汇总见 §2.4。**

### 2.1 接口现状（api_gateway BFF，前缀 `/api/v1/benchmarks`，`benchmark_bp.py` 实测）

| 接口 | 权限码 | 用途（本页） |
| --- | --- | --- |
| `GET /api/v1/benchmarks/ranking?suite=&category=&metricCode=&source=&publishedTaskId=&subjectName=` | `benchmark:ranking:read` | **排行主查询**。`source` 仅接受 `platform_test / external_import`；单页全量（INT-297 信封 `items/total/page/per_page/pages`，无分页语义） |
| `GET /api/v1/benchmarks/ranking/subjects?suite=` | `benchmark:ranking:read` | 参与排行的被测主体去重清单（用于主体搜索联想） |
| `POST /api/v1/benchmarks/ranking/compute` | `benchmark:ranking:compute` | 全量重算排行（可带 suite/category/source 过滤）——页内「立即计算」按钮 |
| `GET /api/v1/benchmarks/sources`（分页+sourceType） | `benchmark:baseline:read` | 数据源列表（管理界面用，见 §2.5） |
| `GET /api/v1/benchmarks/baselines`（category/metricCode/sourceId 分页） | `benchmark:baseline:read` | 外部基线条目列表（管理界面用） |
| `GET /api/v1/benchmarks/metric-mappings?activeOnly=` | `benchmark:ranking:read` | 指标映射清单（**指标筛选下拉的数据源**：metric_code ↔ 指标显示名/单位/方向） |
| `POST /sources`、`POST /baselines(/version)`、`POST|PUT /metric-mappings` | `benchmark:baseline:write|publish`、`benchmark:mapping:manage` | 写侧（数据源/基线导入/映射管理——归属总控 INT-391 收口裁决：另行立项「benchmark 配置写侧界面」，不归 INT-362；本页不设） |

权限校验语义（`api_gateway/application/services/auth/dependencies.py` 实测）：多权限 OR、`*` 通配直放、`AUTH_MODE=off` 时中间件注入 `['*']` 全放行。

### 2.2 ReadModel 行字段（`benchmark_models.py` BenchmarkRanking 实测——榜单行可用的全部事实）

| 字段 | 说明 | 页面用法 |
| --- | --- | --- |
| `source` | `platform_test`（平台实测）/ `external_import`（外部基线）——**双轨制** | 来源筛选 + 行内来源徽章 |
| `subject_name` | 被测对象名（模型/APP/API 名称） | 榜单行主体列 + 主体搜索筛选（`subjectName` 参数） |
| `subject_type` | `open_source / closed_source / app` | 主体类型徽章 |
| `device_type` | `physical / http_api / websocket_api`（可空） | 徽章（有值才显示） |
| `benchmark_suite` | 测试集标识（分组键，默认 `general`，`Config.BENCHMARK_DEFAULT_SUITE`） | 测试集筛选（`suite` 参数） |
| `category` | `asr / voice_llm / tts / translation`（`BenchmarkCategory` 枚举） | **类别维度页签**（`category` 参数） |
| `metric_code` / `metric_name` / `unit` / `direction` | 排行指标代码/显示名/单位/方向（`lower_is_better / higher_is_better`） | 组标题 + 方向徽章（「越低越好/越高越好」） |
| `metric_value` | 被测指标值 | 榜单主值 + 对比条形图 |
| `rank` / `total` | 名次（并列共享）/ 参与对比的模型数 | 名次列 +「N/M」计数 |
| `percentile` | 百分位（**越低越靠前**） | 次要指标 |
| `score100` | 归一化分 0-100（可空，单主体不归一化） | 次要指标（空显示「—」） |
| `gap_best` / `gap_median` | 与排行最佳/中位数差距 | 次要指标（tooltip 展开） |
| `delta_external` | 实测值与外部基线值的差异（**双轨并存时有值**） | 基线差徽章（对位 newAPI GrowthText 位置） |
| `published_task_id` / `published_task_version` / `report_id` | 实测轨溯源（已发布任务/版本/来源报告） | 「v{version}」徽章 + 「查看报告」链接（→ `/report/{reportId}`，report:read 门控） |
| `baseline_id` | 外部轨溯源基线 ID | 不显示（仅排障用） |
| `scenario_key` | 排行场景键（默认「通用」，`Config.BENCHMARK_DEFAULT_SCENARIO`） | 场景分组/场景筛选（**前端派生**，接口无 scenario 参数） |
| `computed_at` | 计算时间 | 组卡「计算于 {时间}」角标 |

### 2.3 排行计算语义（`benchmark_ranking_service.py` 实测——文案与空态措辞依据）

- 双轨合并：平台实测取同主体**最新版本**（旧版本留历史）参与排行；外部基线取当前版本首条；实测优先、无实测时导入值参与排序。
- 分组键：`(category, metric_code, scenario_key)`；组内 6 算法输出 rank/percentile/score100/gapBest/gapMedian/deltaExternal。
- 失败语义：采集/计算/刷新任一失败**整体失败，不触碰 ReadModel，上次排行结果保持可用**——「立即计算」失败 toast 需传达「上一次排行结果仍可查看」。
- 后端固定按 `suite, category, metric_code, rank` 排序返回；组内已按名次序，前端不再改排序（提供按名次/score100 的前端视图排序，见 §5.3）。

### 2.4 数据缺口清单（newAPI rankings 有、本平台后端无——全部「待后端立项」，本页不做假 UI）

| newAPI 能力 | 缺口事实（实测） | 本页处置 |
| --- | --- | --- |
| 周期切换（today/week/month/year） | ReadModel 无时间维度，`computed_at` 仅为计算时刻；`/ranking` 无 period 参数 | **不做周期页签**。下划线页签位改挂「类别维度」（asr/voice_llm/tts/translation/全部，`category` 参数真实存在）。时间维度列「待后端立项」 |
| 用量趋势堆叠图（models_history） | 无任何历史序列接口 | 不做时间趋势图。图表位改做**组内指标值横向对比条形图**（由现有 rows 前端派生，无新后端依赖） |
| 厂商市场份额（vendors + vendor_share_history） | 排行行无 vendor 字段（vendor 仅存在于基线表）；无厂商聚合接口 | 不做厂商份额卡。「待后端立项」（ReadModel 增厂商维度） |
| 升降榜（top_movers/top_droppers） | 无跨期名次对比数据 | 不做升降榜卡。「待后端立项」 |
| Token 体量角标（formatTokens 总量） | 无用量语义 | 角标位改放「参与主体 total + 计算于 computed_at」 |
| 榜单按算法过滤（INT-442 改判需求） | ReadModel 无算法维度字段；`/ranking` 无 `algorithm_type` 参数（§2.2 全字段实测） | **算法卡片网格先行落地**（每算法一张大卡：算法名+分组+参数摘要+描述，页内切换独立可用，§4.5）；榜单按算法过滤/重算**待后端立项**（ReadModel 增算法维度或查询附 algorithm_type） |

### 2.5 范围边界

- 本卡只做**排行展示页（读侧 + 重算按钮）**；数据源管理/基线导入/指标映射管理是写侧资源界面，归属总控 INT-391 收口裁决：另行立项「benchmark 配置写侧界面」（不归 INT-362），本页不设（接口契约已在 §2.1 记录）。
- 「Benchmark 徽章」联动：任务域已发布任务卡的 Benchmark 徽章（`PublishedTaskPanel.vue:19` 现状）在新前端可链入本页并预置 `publishedTaskId` 筛选（`/ranking` 实测支持该参数）——由任务域卡 INT-354 落地，本页只保证 URL 参数可还原。

---

## 3. 「newAPI 页面 → 本平台页面」映射表

### 3.1 映射总表

| newAPI rankings | 本平台现状（Vue，只读参考） | 映射进新前端 |
| --- | --- | --- |
| `/rankings` 公开排行页 | **无此页面**（benchmark 仅有后端接口与已发布任务上的徽章，站内无任何排行界面） | **新增「排行榜」页 `/rankings`**（公开路由，权限判定见 §6） |
| Hero 周期页签（today/week/month/year 下划线页签） | 无 | **类别维度下划线页签**：全部 / 语音识别 / 语音对话 / 语音合成 / 翻译（`category` 参数；周期切换待后端立项，见 §2.4） |
| Top Models 主卡（堆叠柱 + LLM Leaderboard 双栏榜） | 无 | **指标组卡 ×N**（每组=category×metric×scenario 一个组）：组头（指标名+方向徽章+参与主体数+计算时间）+ 指标值对比条形图（前端派生）+ 双栏主体榜单 |
| Market Share 厂商份额卡 | 无 | 不做（数据缺口，待后端立项） |
| Pulse 升降榜双卡 | 无 | 不做（数据缺口，待后端立项） |
| ModelLink → /pricing/$modelId | 无对应详情页 | **SubjectLink**（主体名→本页 `subjectName=` 筛选，同页联动）+ **ReportLink**（实测轨行→`/report/{reportId}`，`report:read` 门控；外部轨行无详情页，仅文字） |
| GrowthText（↑↓ 环比） | 无 | **DeltaText**（基线差 `deltaExternal`：±值+单位，双轨并存时显示；正负色沿用 emerald/rose 语义——按 direction 语义定正负色，见 §5.4） |
| `GET /api/rankings?period=` 单快照 | `/api/v1/benchmarks/ranking`（六参数筛选，单页全量） | `GET /api/v1/benchmarks/ranking` + `/ranking/subjects` + `/metric-mappings?activeOnly=true`（指标下拉）三请求 |
| 顶部导航 rankings 模块（本 fork 实测文案「Availability」→/platform；/rankings 不进导航，nav-modules 可控 enabled/requireAuth） | 无 | **顶部导航「排行榜」直达 `/rankings`**（负责人口径「顶部导航含 benchmark 排行、报告直达」；入口可见性按 `benchmark:ranking:read` 权限判定，导航树由导航栏卡 INT-344 统一落地。newAPI 的 enabled/requireAuth 站点级开关机制作参照，站点设置域纳入与否待后端立项） |
| PublicLayout 公共外壳 | 无（Vue 登录后单壳） | 复用 newAPI PublicLayout 骨架（站头+页脚），与首页/关于/文档页共用同一外壳——本卡只消费，外壳由导航栏卡 INT-344 / 关于页卡 INT-348 统一定义 |
| 图表 VChart + useChartTheme 深浅色 | 无 | 同款引入 `@visactor/react-vchart` + `use-chart-theme.ts` 机制（照搬，chart 主题跟随 next-themes） |
| （newAPI 无对位——算法切换为平台特有，INT-442 改判） | 无（原 §3.2 口径「不设算法筛选」） | **算法卡片网格**（§4.5，INT-436 契约口径修正 2026-10-16）：每算法一张大卡（算法名+分组+参数摘要+描述），页内算法切换、页内独立不写回全局；榜单按算法过滤待后端立项（§2.4）。详情见 §3.2 |

### 3.2 算法切换口径（负责人 2026-10-15 改判 + 2026-10-16 口径修正——INT-442 联动）

**改判**：本页**新增「算法卡片网格」**（工作台概览算法卡片网格形态——**每算法一张大卡**，不是单张当前算法卡），页面内切换算法——**不再用右上角全局切换器**。原「本页不设算法筛选、与全局切换器无联动」口径推翻（INT-442，2026-10-15）。

- **形态与契约**：复用 INT-436 工作台概览算法卡片网格组件契约（`04_控制台.md` §3.4）+ 数据源 `GET /algorithm/definitions`（含描述/参数摘要字段，不用仅 value/name/group 的 `/options`）——每卡=算法名+分组+参数摘要+描述，点击选中=切换页内算法、选中态高亮，首卡「全部算法」；网格微布局复用 INT-355 §3.4 卡片网格通道。算法选择组件 `algorithm-selector.tsx` 仍由导航栏切换器/测试执行步骤0 使用（导航栏切换器/测试执行步骤0/工作台概览/本页共用同一数据源与 store 契约，不发明第二套）。
- **页内独立（不写回全局）**：本页走公共壳（PublicLayout，URL 直达可打开——未登录导航隐藏、数据 403 空态，INT-344 口径，§6.2），算法切换**只过滤本页榜单、不写回全局算法 store**（INT-442 倾向：公开页不该污染全局；2026-10-16 口径修正仅改形态、不改 store 语义）。页内 Zustand store `useRankingAlgorithmStore { algorithmType: string|null; setAlgorithm(type); clear() }`，localStorage `iatp:rankings:v1:algorithm`；URL `algorithm=` 可还原。
- **数据缺口（待后端立项）**：排行 ReadModel 无算法维度字段，`/ranking` 无 `algorithm_type` 参数（§2.2 全字段实测）——**榜单按算法过滤/重算待后端立项**（ReadModel 增算法维度或查询附 algorithm_type）。就绪前：算法卡片网格完整呈现（显示/切换可用），所选算法写入页内 store 与 URL，榜单数据仍全量展示，网格区标注「按算法过滤待后端立项」。
- **公开页权限降级**：`GET /algorithm/definitions` 与 `/algorithm/options` 门槛 `algorithm:read`（`algorithm_bp.py` 实测）——持 `algorithm:read` 者（admin/tester/algo_engineer）完整网格（全量算法卡 + 选中高亮 + 点击切换）；无权限者（device_admin/guest）与未登录访客**只读降级条**（仅显示「全部算法」，无切换，可正常浏览榜单）——照 INT-436 只读降级态契约，公开页首屏不空。

---

## 4. 布局结构（本平台新前端）

### 4.1 页面总骨架

```
PublicLayout（站头 PublicHeader + main + 页脚 Footer，对位 newAPI public-layout.tsx）
└─ div.relative
   ├─ 背景光晕层（aria-hidden，h-[600px] 三椭圆径向渐变 + 底部渐隐遮罩；照 newAPI index.tsx:95-108，
   │   色相换本平台主色系：163° 主绿 / 200° 青蓝 / 280° 点缀，浅色 opacity-20 / 深色 opacity-[0.10]）
   └─ PageTransition（mx-auto max-w-[1280px] space-y-8 px-3 pt-16 pb-10 sm:px-6 sm:pt-20 sm:pb-12 xl:px-8）
      ├─ RankingsHero（标题 + 说明 + 类别维度下划线页签）
      ├─ AlgorithmCardGrid（算法卡片网格——INT-436 契约，每算法一张大卡 + 全部算法首卡，页内独立切换，§4.5）
      ├─ 筛选行（测试集 / 指标 / 数据来源 Select + 主体搜索 Input；本平台扩展，参数全部实测存在）
      ├─ MetricGroupCard ×N（按 category×metric×scenario 分组，组内 rank 升序）
      │  ├─ 卡头：图标+「{指标名} · {场景}」+ 方向徽章 ｜ 右侧：参与主体 N + 计算于 {computedAt}
      │  ├─ 指标值对比条形图（VChart 横向条形，h-60 sm:h-72，前端派生）
      │  └─ border-t 榜单块：SubjectLeaderboard（双栏榜单，对位 ModelLeaderboard）
      └─ （空态/加载/错误三态见 §5.5）
```

- 间距、断点、容器宽度全部照搬 newAPI 实测值（§1.2），不自研布局。
- 组卡数量 = 当前筛选下的 `(metricCode × scenarioKey)` 组数（category 由页签锁定）；组间 `space-y-8`。

### 4.2 RankingsHero（对位 rankings-hero.tsx）

- 标题「排行榜」（`clamp(1.75rem,4vw,2.5rem)` bold tracking-tight）；副标题一句（`text-muted-foreground/80 max-w-2xl text-sm`）。
- 下划线页签（`role='tablist' aria-label='指标类别'`）：全部 / 语音识别 ASR / 语音对话 / 语音合成 TTS / 翻译——样式照 newAPI（`border-b` + 激活 `bg-foreground h-[2px]` 滑条，激活/未激活色同 §1.2）；写入 URL `category=`。
- 页签切换不重置其他筛选（URL search 合并写入，照 newAPI `navigate({search: prev => ({...prev, …})})` 模式）。

### 4.3 筛选行（本平台扩展行）

- 布局：`flex flex-wrap items-center gap-2`，置于 Hero 之下、首张组卡之上；移动端换行堆叠。
- 控件（全部对基座卡 §5 组件选型，h-8）：
  - 「测试集」Select：选项=当前数据去重 `benchmarkSuite`（默认「全部测试集」）→ `suite=`。
  - 「指标」Select：选项=「全部指标」+ `metric-mappings?activeOnly=true` 清单（显示 `metricName`，值 `metricCode`）→ `metricCode=`。映射接口失败时退化为纯文本输入（容错，不打断页面）。
  - 「数据来源」Select：全部来源 / 平台实测 / 外部基线 → `source=`（platform_test/external_import，接口仅接受这两值，`benchmark_service.py:25` 实测）。
  - 「搜索主体」Input（lucide `Search` 前缀图标 + placeholder）：防抖 300ms → `subjectName=`；下拉联想用 `/ranking/subjects`（有输入时出现，键盘可选，Escape 关闭）。
  - 右端「重置」ghost 按钮（任一筛选非默认时出现）。
- 全部筛选状态写入 URL search（zod validateSearch：`category/suite/metricCode/source/subjectName` 全 optional + catch），刷新/分享可还原——照 newAPI 路由 validateSearch 模式。
- **算法切换不在筛选行**（Hero 下**算法卡片网格**承担，§3.2 改判口径）；无场景独立筛选器（场景是分组键，组卡标题已带场景，同指标跨场景自然分卡）。

### 4.4 指标组卡（对位 models-section.tsx）

- 卡容器：`bg-card overflow-hidden rounded-lg border`（照 newAPI 实测 `rounded-lg`；圆角值按基座卡 §5 组件表 Card 行 rounded-xl 实施时校准）。
- 卡头（`px-5 py-4`，两端对齐）：
  - 左：lucide 图标（按 category 固定：asr=`AudioLines`、voice_llm=`MessagesSquare`、tts=`Volume2`、translation=`Languages`，`text-primary size-4`）+ 标题 `{指标名} · {场景}`（`text-base font-semibold`）+ 方向徽章（「越低越好」=neutral 软底 /「越高越好」=primary 软底，基座卡 §5 组件表 Badge 行）+ 说明行（`text-muted-foreground mt-1 text-sm`：「平台实测与外部基线按 {direction} 排名，共 {total} 个主体参与。」）。
  - 右（`text-right shrink-0`）：参与主体数 `font-mono text-2xl font-semibold tabular-nums`（对位 newAPI tokens 大数字位）+ 角标「个主体 · 计算于 {MM-DD HH:mm}」（`text-[10px] tracking-widest uppercase text-muted-foreground/80`，uppercase 仅作用于西文，中文原样）。
- 图表区（`px-5 pb-5`，`h-60 sm:h-72`）：**指标值横向对比条形图**（VChart `bar`，横向，按 rank 升序自上而下）：
  - 单色 `--chart-1`（基座卡 §3.6）；实测轨与外部轨双色区分：实测 `--chart-1` / 外部 `--chart-2`，图例隐藏、行内徽章已区分，tooltip 标注来源。
  - 轴：类目轴（主体名，`autoHide/autoLimit`）；数值轴 `formatMethod` 按指标单位缩写（≥1000 显示 1.2K/3.4M，照 newAPI formatTokens 思路改数值通用版，保留两位内）；网格虚线 `lineDash:[3,3]` + 深浅色 rgba（§1.2 同值）。
  - tooltip：主体名 + 值 + 单位 + 来源；并列名次主体相邻排列。
  - `themeReady` 前与数据为空时显示占位文案「暂无图表数据」（照 newAPI `No history data available` 位置与样式）。
  - **本图为前端派生（数据已存在），不属 §2.4 缺口。**
- 榜单块（`border-t`）：
  - 块头（`px-5 pt-4 pb-2`）：lucide `Trophy`（`size-3.5 text-amber-500`，照 newAPI）+「榜单」（`text-sm font-semibold`）+ 说明「按名次排列，实测轨取最新版本」（`text-muted-foreground/80 mt-0.5 text-xs`）；右端视图切换 Tabs（`line` 变体，基座卡 §5 组件表 Tabs 行）：「列表」（默认，双栏）/「表格」（全字段，见 §5.3）。
  - 榜单双栏（对位 ModelLeaderboard）：`grid grid-cols-1 md:grid-cols-2 gap-x-8`，行数均分左右（`half = ceil(n/2)`，保持单榜视觉节奏）。
  - 榜单行（`flex items-center gap-3 py-2.5`）：
    - 名次：`w-6 text-right font-mono text-xs tabular-nums text-muted-foreground/80`（`{rank}.`，并列共享名次照实显示）。
    - 主体列：主体名 **SubjectLink**（`font-mono text-sm font-medium` + 常驻细下划线，点击=本页 `subjectName` 筛选，同 newAPI「榜单即导航」）；下行徽章组（`text-xs italic` 位对位 newAPI 厂商行）：主体类型（开源/闭源/App，neutral 软底）+ 设备类型（有值才显示：实体设备/HTTP API/WebSocket API）+ `v{publishedTaskVersion}`（实测轨）+ 来源徽章（「平台实测」info 软底 /「外部基线」secondary 软底）。
    - 右值列：主值 `{metricValue}{unit}`（`font-mono text-sm font-semibold tabular-nums`）；下行 DeltaText（`text-[11px]`）：实测轨双轨并存时显示「基线差 ±{deltaExternal}{unit}」（配色按 §5.4），否则显示 `score100`（有值：「{score100} 分」，空值「—」）。
    - 实测轨行尾「查看报告」link 变体小按钮（lucide `FileText size-3` + 文字，`→ /report/{reportId}`，仅 `report:read` 持有者渲染）。
  - 空组不渲染卡（全空时页面级空态，§5.5）。

### 4.5 算法卡片网格（INT-442 改判 + 2026-10-16 口径修正——页面内算法切换，复用 INT-436 契约）

**定位**：Hero 之下、筛选行之上的**算法选择区**（主视觉位、整宽），**每个算法一张大卡**的卡片网格（不是单张「当前算法」卡）：每卡含算法名/分组/参数摘要/描述，点击选中=切换页内算法、选中态高亮，选中卡即页内算法当前值；首卡「全部算法」。切换链路**复用 INT-436 工作台概览算法卡片网格组件契约**（`04_控制台.md` §3.4 实测：区壳 `bg-card overflow-hidden rounded-2xl border shadow-xs` + 径向光斑 + 区头 eyebrow「算法切换」+ 网格 `grid gap-3 sm:grid-cols-2 xl:grid-cols-3` + 每算法大卡 `rounded-xl border p-4` + 选中态 `border-primary ring-primary/20 ring-2`），不发明第二套算法切换。

- **版式（照 INT-436 §3.4 网格）**：
  - 区壳 + 区头：eyebrow「算法切换」（`text-muted-foreground text-xs font-medium tracking-wider uppercase`）+ 副文（`text-xs text-muted-foreground`）「仅影响本页榜单，不改变全局算法。」（**页内独立口径**）。
  - 网格 `grid gap-3 sm:grid-cols-2 xl:grid-cols-3`：**首卡「全部算法」**（Layers 图标，value=null，`rounded-xl border p-4` 图标位 + 名称「全部算法」+ 副文「不按算法筛选，展示全部算法数据。」——store 为 `null` 时选中态）；**每算法大卡** `rounded-xl border p-4 hover:border-primary/40 hover:shadow-sm`：图标位（`size-10 rounded-lg bg-primary/10 text-primary`）+ 名称 h3「{algorithm.name}」（`text-sm font-semibold tracking-tight`）+ 分组 Badge outline「{group_name}」（无分组不显）+ 状态 Badge outline「在线/离线」；**参数摘要行**（`text-xs text-muted-foreground`）「设备参数 {n} · API 参数 {m} · 用例参数 {k}」（由 `device_params/api_params/case_params` 长度派生，三项全 0/缺失隐藏）；描述（`text-sm text-muted-foreground line-clamp-2`）：`{algorithm.description}`。
  - **选中态**（页内 store 命中该算法）：`border-primary ring-primary/20 ring-2 bg-primary/5` + 右上 CheckIcon + 「当前」Badge；离线算法卡置灰不可选（`opacity-60 pointer-events-none`，对齐 options 仅在线可切语义）。
- **数据源与权限（实测）**：卡片网格数据源 `GET /algorithm/definitions`（门槛 `algorithm:read`，`algorithm_bp.py:14-16` 实测）→ `AlgorithmDefinitionDto.items`（含描述/参数摘要字段，`algorithmDto.ts:8-32` 实测；**不用仅 value/name/group 的 `/options`**）——与 INT-436 同源同 query（`['algorithm','definitions']`，staleTime 5min）。持 `algorithm:read`（admin/tester/algo_engineer）完整网格；无权限（device_admin/guest）与未登录访客**只读降级条**。
- **只读降级态**：网格不渲染（definitions 403），收敛为只读条 `bg-card rounded-2xl border shadow-xs` 单行 `flex items-center justify-between gap-2 px-4 py-3 sm:px-5`——左「当前算法」label（`text-muted-foreground text-xs font-medium`）+ 右「全部算法」（页内 store 默认 null，无描述/分组徽章/切换）+ Tooltip「切换算法需登录并具备算法查看权限」。**公开页首屏不空、榜单浏览不受影响**。
- **切换交互（点击卡片直选，写回页内 store）**：点击算法卡 → `setAlgorithm(algorithm.type)` → toast「已切换榜单算法为 {名}」→ 选中态即时高亮（store 订阅）；点击「全部算法」首卡 → `clear()` → toast「已恢复全部算法」→ 首卡选中态。Command 搜索通道仍由导航栏/测试执行的 `algorithm-selector` 承载（本网格即其「卡片网格」通道页内直显形态）。
- **与全局切换器关系**：本页**不出现**右上角全局切换器组件（INT-442：导航栏「报告」页与「排行榜」页不再用右上角全局切换器）；本页网格**不订阅 `useGlobalAlgorithmStore`、不写回全局**——页内独立，避免公开页污染全局。
- **榜单过滤生效条件（待后端立项）**：`/ranking` 支持 `algorithm_type` 参数（或 ReadModel 增算法维度）后，页内所选算法并入排行查询与 queryKey，榜单按算法过滤；就绪前榜单全量展示，网格区标注「按算法过滤待后端立项」。

### 4.6 页脚

复用公共外壳 Footer（导航栏卡/关于页卡统一定义），本页零特判。

---

## 5. 组件与交互细节

### 5.1 三态与加载

- 加载态（首次/切筛选 refetch 时 non-blocking 保留旧数据，TanStack Query `placeholderData: keepPreviousData`）：首访四段 Skeleton（对位 newAPI h-[420px]/h-[360px]/h-[180px] → 本页 Hero 骨架条 + 算法卡片网格骨架条（图标/标题/描述行三段，照 INT-436 骨架）+ 筛选行骨架 + 组卡骨架×2，`rounded-xl`）；`isFetching` 时筛选行右侧显示 `Loader2 size-4 animate-spin`。
- 算法卡降级：`/algorithm/definitions` 失败整卡值区「--」+「算法详情暂不可用」（不报错 toast，ErrorState 卡内降级——对齐 INT-436 工作台逐卡容错）；无权限/未登录只读降级条（§4.5）。
- 空态（查询成功但 0 行）：Empty 组件（基座卡 §5 组件表 Empty 行，border-dashed 圆角卡）：图标 `Trophy`、标题「暂无排行数据」、描述「尚未计算排行，或当前筛选条件下没有数据。」；持 `benchmark:ranking:compute` 者加主按钮「立即计算」（无权限者无按钮，描述后补一句「请联系管理员计算排行。」）。
- 权限空态（403：未登录或已登录无 `benchmark:ranking:read`）：**不跳登录**（INT-344 定稿「URL 直达可达、数据 403 空态」）。同 Empty 卡形态：图标 `Lock`、标题「无法查看排行数据」、描述「当前账号无排行查看权限，请登录或联系管理员。」，**无「重试」按钮**（非请求失败，重试无意义）；AUTH_MODE=off（现状部署）不出现此态。
- 错误态（请求失败）：`bg-card rounded-xl border border-dashed px-6 py-12 text-center`（照 newAPI RankingsError）+ 「重试」outline 按钮；`message` 取后端 detail（如「查询排行失败，请稍后重试」实测文案）。

### 5.2 「立即计算」（重算交互）

- 可见性：`hasPermission('benchmark:ranking:compute')` 才渲染（无权限整钮隐藏，对齐 newAPI「隐藏而非置灰」）；位置：筛选行右端（与「重置」同组）。
- 点击 → AlertDialog 确认（基座卡 §5 组件表 AlertDialog 行）：标题「重新计算排行？」描述「将合并平台实测与外部基线全量重算，期间现有排行保持可查看。」按钮「开始计算」（default）/「取消」。
- 进行中：按钮 loading（Spinner+「计算中…」），禁用重复点击；成功 `toast.success('排行计算完成')` + 失效 `rankings` 查询缓存自动刷新；失败 `toast.error('{message}')` + 附加说明「上一次排行结果仍可查看」（后端失败语义 §2.3）。
- 计算是同步接口、低频操作，**不做轮询**（TanStack Query staleTime 5 分钟，同 newAPI）。

### 5.3 列表 / 表格双视图

- 「列表」（默认）：§4.4 双栏榜单——快读名次与主值。
- 「表格」：TanStack Table（基座卡 §5 组件表 Table 行）：列=名次 / 主体 / 主体类型 / 来源 / 版本 / 指标值({unit}) / score100 / 百分位 / 与最佳差 / 与中位差 / 基线差 / 计算于；数值列右对齐 `tabular-nums`；方向提示在表头 tooltip（「该指标越低越好」）；空值统一「—」。
- 两视图共享同一组数据与筛选；视图选择存 localStorage（`iatp:rankings:v1:view`），不入 URL。

### 5.4 DeltaText 配色语义（对位 GrowthText，按 direction 定正负）

newAPI 的 growth 是"越大越好"隐含语义；本平台 delta 方向随指标 `direction` 翻转：

- `higher_is_better`：deltaExternal > 0（超基线）→ emerald `↑`；< 0 → rose `↓`。
- `lower_is_better`：deltaExternal < 0（低于基线=更优）→ emerald `↓`；> 0 → rose `↑`。
- 显示 `±{|delta| 保留 2 位}{unit}`，0 或空显示「—」（neutral）；色彩 token 用基座卡 §3.4 语义：涨=success 系文本色、跌=destructive 系文本色（emerald/rose 是 newAPI 实测用法，映射到本平台 `text-success / text-destructive`，多主题预设下自动联动）。

### 5.5 筛选联动与深浅色

- 任一筛选变化 → URL search 更新 → 查询键变化自动 refetch（`queryKey: ['benchmarks','ranking',filters]`）。
- 图表深浅色：`useChartTheme`（照搬 newAPI），`key={group-${resolvedTheme}}` 主题切换整图重建；图表底 `background:'transparent'` 融入卡片。
- 深浅两套全走语义 token（§8），页面零硬编码色值；多主题预设（lake-view/rose-garden/默认蓝等）由基座机制驱动，图表色 `--chart-1/2` 随预设自动换。

### 5.6 移动端

- 页签横向滚动（`overflow-x-auto`，不换行）；筛选行纵向堆叠；算法卡片网格单栏塌缩（`grid-cols-1`，首卡与各算法卡纵排）；组卡图表 `h-60`；榜单双栏塌单栏（`grid-cols-1`，照 newAPI）；表格视图横向滚动包裹（`role='region'` + aria-label，文档页卡同款可聚焦容器）。

---

## 6. RBAC 角色 → 页面 → 菜单/按钮映射表

### 6.1 权限事实（实测，非杜撰）

- 网关为 benchmark 路由定义 6 个权限码：`benchmark:ranking:read / benchmark:ranking:compute / benchmark:baseline:read / benchmark:baseline:write / benchmark:baseline:publish / benchmark:mapping:manage`（`benchmark_bp.py` 实测）。
- **现状（INT-429 已落地，commit 8e5ab2e6）**：`scripts/migrations/202608/seed_rbac.py` 已定义全部 6 个 `benchmark:*` 权限点（seed 全量 107 实码 + `*`，21 模块）并**授 tester 与 algo_engineer 全 6 码**（含 `ranking:read` 读榜与 `ranking:compute` 触发重算）；guest / device_admin **未授**；admin 经 `*` 通配持有。AUTH_MODE=on 时 tester/algo_engineer 正常读榜并可触发重算；device_admin/guest 一律 403；AUTH_MODE=off（现状部署）时中间件注入 `['*']` 全员放行。原「待后端立项（RBAC 补码）」已由 INT-429 闭合，本节不再立项。

### 6.2 角色映射表

| 角色（seed_rbac `ROLES`） | 现状权限判定 | 顶部导航「排行榜」 | 页面读取（榜单/筛选/搜索） | 算法卡片网格 | 「立即计算」 | 「查看报告」行内链接 | 立项结论（INT-429 已落地） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| admin 超级管理员（`*`） | `*` 通配 | 可见 | 可用 | 完整网格（algorithm:read∈`*`） | 可用（`benchmark:ranking:compute`） | 可用（report:read∈`*`） | 维持 |
| tester 测试工程师 | `benchmark:*` 全 6 码（INT-429 已授） | 可见 | 可用 | 完整网格（algorithm:read） | 可用（`benchmark:ranking:compute`） | 可用（report:read） | 已落地（INT-429），无需再立项 |
| algo_engineer 算法工程师 | `benchmark:*` 全 6 码（INT-429 已授） | 可见 | 可用 | 完整网格（algorithm:read） | 可用（`benchmark:ranking:compute`） | 可用（report:read） | 已落地（INT-429），无需再立项 |
| device_admin 设备管理员 | 无 benchmark:* → AUTH_MODE=on 403；off 放行 | 隐藏 | 数据 403 空态（URL 直达） | 只读降级条（无 algorithm:read，网格不渲染） | 隐藏 | 隐藏（无 report:read） | 维持不补（INT-429 未授） |
| guest 游客 | 无 benchmark:* → AUTH_MODE=on 403；off 放行 | 隐藏 | 数据 403 空态（URL 直达） | 只读降级条（无 algorithm:read，网格不渲染） | 隐藏 | 隐藏 | 维持不补（INT-429 未授） |
| 未登录访客（AUTH_MODE=on） | 无 | 隐藏（URL 直达可达——INT-344 定稿） | 数据 403 空态（不跳登录；榜单查询 403 → 权限空态，§5.1） | 只读降级条（未登录，definitions/options 均 403） | 隐藏 | 隐藏 | 无需立项（已按 INT-344 定稿：入口隐藏 + URL 直达 + 数据 403 空态） |

> 注：「算法卡片网格」页内独立（§3.2/§4.5），无 `algorithm:read` 时仅降级条不阻塞榜单浏览；AUTH_MODE=off（现状部署）时全员 `['*']`，网格全角色完整卡。

- 前端判定对齐本平台惯例（`authStore.hasPermission` 含 `*` 通配，系统设置卡 §2.0 实测）：**路由不设硬守卫**（公开可达，对齐 INT-344 §2.2「URL 直达可达、数据 403 空态」）——未登录与已登录无 `benchmark:ranking:read` 者，顶部导航入口隐藏，URL 直达时榜单数据 403 → 权限空态（§5.1，不跳登录）；已登录持码（admin/`*`、tester、algo_engineer——INT-429 已授）正常读；AUTH_MODE=off（现状部署）放行。
- 导航按角色渲染的原则由导航栏卡 INT-344 统一实现：本页入口无权限时**整项隐藏**（不是置灰）。
- 页面内无数据写操作按钮（除重算）；数据源/基线/映射管理写侧界面不在本页（总控 INT-391 收口裁决：另行立项「benchmark 配置写侧界面」，不归 INT-362）。

---

## 7. 页面文案（中文全量）

### 顶部导航（入口，随导航栏卡统一）

- 「排行榜」→ `/rankings`；移动端全屏菜单同项；当前页高亮。

### Hero

- 标题：「排行榜」
- 副标题：「多个厂商模型/APP/API 在同一标准化环境、同一测试集与指标下同时实测，按指标与场景生成名次，横向看清业界水平。」
- 页签（aria-label「指标类别」）：「全部」「语音识别」「语音对话」「语音合成」「翻译」
- 页签 sr-only 状态：「{名称}，当前已选中」/「{名称}」

### 筛选行

- 「测试集」「指标」「数据来源」「搜索主体」（Input placeholder：「搜索主体名称…」）
- 来源选项：「全部来源」「平台实测」「外部基线」
- 测试集/指标默认项：「全部测试集」「全部指标」
- 「重置」；「立即计算」；确认弹窗：标题「重新计算排行？」描述「将合并平台实测与外部基线全量重算，期间现有排行保持可查看。」按钮「开始计算」「取消」
- 主体联想空提示：「未找到匹配的主体」

### 算法卡片网格（INT-442 改判 + 2026-10-16 口径修正）

- 区头 eyebrow「算法切换」+ 副提示「仅影响本页榜单，不改变全局算法。」；首卡「全部算法」+ 副文「不按算法筛选，展示全部算法数据。」；每算法大卡：名称「{算法名}」+ 分组徽章「{分组名}」+ 状态徽章「在线/离线」+ 参数摘要「设备参数 {n} · API 参数 {m} · 用例参数 {k}」+ 描述「{算法描述}」；选中态「当前」Badge
- 降级条 Tooltip「切换算法需登录并具备算法查看权限」；失败态「算法详情暂不可用」；toast「已切换榜单算法为 {名}」「已恢复全部算法」
- 待后端立项标注：「按算法过滤待后端立项（排行数据暂无算法维度）」

### 组卡

- 方向徽章：「越低越好」「越高越好」
- 表头 tooltip：「该指标越低越好，名次靠前值更小。」/「该指标越高越好，名次靠前值更大。」
- 说明行：「平台实测与外部基线按{方向语义}排名，共 {N} 个主体参与。」（方向语义=「越低越好/越高越好」）
- 角标：「个主体 · 计算于 {YYYY-MM-DD HH:mm}」
- 榜单块头：「榜单」说明「按名次排列，实测轨取最新版本参与对比。」
- 视图切换：「列表」「表格」
- 徽章：主体类型「开源」「闭源」「App」；设备「实体设备」「HTTP API」「WebSocket API」；来源「平台实测」「外部基线」；版本「v{N}」
- 行尾链接：「查看报告」；DeltaText：「基线差 ±{X}{unit}」；score100：「{X} 分」；空值「—」
- 图表占位：「暂无图表数据」

### 空态 / 错误态 / toast

- 空态：标题「暂无排行数据」；描述「尚未计算排行，或当前筛选条件下没有数据。」（无计算权限追加：「请联系管理员计算排行。」）按钮「立即计算」（有权限时）
- 权限空态（403）：标题「无法查看排行数据」；描述「当前账号无排行查看权限，请登录或联系管理员。」（无重试按钮）
- 错误态：标题「排行加载失败」；描述=后端 message（默认「查询排行失败，请稍后重试」）；按钮「重试」
- toast：成功「排行计算完成」；失败「{message}」+「上一次排行结果仍可查看」；联想加载失败不打断输入（静默）
- 表格视图 aria（滚动容器）：「排行明细表：{列头拼接}」

---

## 8. 字体/色彩/组件 token 引用

- **字体**：标题 sans semibold（本页无衬线大标题——newAPI rankings 标题即 sans bold）；主体名/数值列 `font-mono` + `tabular-nums`（newAPI 实测同款：主体名 font-mono、数值 font-mono tabular-nums）；角标 10px 大写字距仅作用西文。
- **色彩**（全部引基座卡 `01_全局基座.md`）：表面 `--card/--border/--muted-foreground`；主色 `--primary`（图标/激活强调）；来源徽章 info/secondary 软底（基座卡 §5 组件表 Badge 行）；DeltaText `--success/--destructive`；图表 `--chart-1/--chart-2`（§3.6，深浅同值随预设联动）；骨架屏 `--skeleton-base/highlight`（§3.3）；算法卡片网格区壳/光斑照 INT-436 §3.4（`rounded-2xl` + `--overview-accent-1..3` color-mix 径向渐变，非 default 预设映射 chart-1..3）。多主题预设（lake-view 默认参考、rose-garden、默认蓝等）+ 深浅色由基座机制驱动，本页零特判。
- **组件选型**（全部 newAPI 现成件，基座卡 §5）：Button（default/outline/ghost/link）、Select、Input+Search 图标组、Tabs（line 变体做视图切换 + 页签自绘下划线照 newAPI hero）、Badge、Card 结构、Empty/Skeleton/Spinner、AlertDialog（重算确认）、Tooltip（方向提示）、sonner toast、Table（表格视图）、Collapsible（移动端不做——本页无侧栏，无此依赖）。
- **图表**：`@visactor/react-vchart ^2.1.2`（newAPI `web/package.json:44-45` 实测同版本）+ `use-chart-theme.ts` 照搬；轴/网格色 rgba 值照 §1.2。
- **待基座卡落 token**：色值、字号阶梯已定稿（基座卡为基准稿），本卡语义 token 名零改动替换。

---

## 9. React 组件树 + DDD 四层落位

```
interfaces/
├─ routes/rankings/index.tsx             # /rankings 公开路由：validateSearch(zod)（不设权限硬守卫）
│                                        #   （未登录/无权限入口隐藏；URL 直达时榜单数据 403 空态——INT-344 口径；
│                                        #    AUTH_MODE=off 放行）
├─ features/rankings/
│  ├─ index.tsx                          # Rankings 页骨架（光晕层 + PageTransition 容器 + 三态路由）
│  ├─ components/
│  │  ├─ rankings-hero.tsx               # 标题 + 说明 + 类别下划线页签
│  │  ├─ algorithm-card-grid.tsx        # 算法卡片网格（INT-436 契约：每算法一张大卡 + 全部算法首卡 + 选中态高亮 +
│  │  │                                  #   参数摘要 + 只读降级条；订阅 useRankingAlgorithmStore + ['algorithm','definitions']，页内独立）
│  │  ├─ ranking-filters.tsx             # 筛选行（Select×3 + 主体搜索联想 + 重置 + 立即计算）
│  │  ├─ metric-group-card.tsx           # 组卡（卡头统计 + 图表区 + 榜单块）
│  │  ├─ metric-bar-chart.tsx            # VChart 横向对比条形图（themeReady 门控 + 深浅重建）
│  │  ├─ subject-leaderboard.tsx         # 双栏榜单（对位 ModelLeaderboard，均分左右列）
│  │  ├─ subject-table.tsx               # 表格视图（TanStack Table，全字段 + 横向滚动包裹）
│  │  ├─ entity-links.tsx                # SubjectLink（本页筛选链）/ ReportLink（report:read 门控）
│  │  ├─ delta-text.tsx                  # 基线差文案（direction 感知正负色，对位 GrowthText）
│  │  └─ source-badge.tsx                # 来源/主体类型/设备类型/版本 徽章组
│  └─ lib/format.ts                      # formatMetricValue（单位缩写）/ formatGap / formatComputedAt
├─ features/benchmark-ranking-block/                 # 「Benchmark 排行」区块（报告详情页内嵌，15_报告域 §3.8 消费）
│  └─ components/benchmark-ranking-block.tsx         # 排行表 + 参考线图表(ECharts) + 来源筛选 + 版本标注 + 异步进度（报告Benchmark排行功能设计文档.md:436-444）
└─ （不新建 `/benchmarks/*` 前端路由——INT-344 v1.4 裁定 2026-10-16：Benchmark 报告列表并入报告中心类型页签
   `/reports`、详情复用报告详情页 `/report/{reportId}`，具体落位实施卡基线裁定，§10.2）
application/
├─ rankings/useRankings.ts               # TanStack Query（queryKey=[benchmarks,ranking,filters]，
│                                        #   staleTime 5min，keepPreviousData；对位 newAPI use-rankings.ts）
├─ rankings/useRankingAlgorithm.ts       # 页内算法 store 封装（useRankingAlgorithmStore Zustand +
│                                        #   ['algorithm','definitions'] 网格数据 + 参数摘要派生 + 选中态解析，algorithm:read 门控；不写回全局）
├─ rankings/useMetricMappings.ts         # 指标映射查询（指标下拉数据源，失败静默退化）
├─ rankings/useRankingSubjects.ts        # 主体联想查询（防抖 300ms，enabled=有输入）
├─ rankings/useComputeRanking.ts         # 重算 mutation（成功失效 rankings 缓存 + toast）
├─ rankings/groupRankings.ts             # 纯函数：rows → (metricCode×scenarioKey) 组，组内 rank 升序（单测）
└─ rankings/rankingFilters.ts            # URL search ↔ 筛选状态（zod schema + 默认值合并）
infrastructure/
├─ api/benchmarkApi.ts                   # GET/POST /api/v1/benchmarks/ranking…（http 客户端封装，纯取数不映射）
└─ adapters/benchmarkAdapter.ts          # DTO→Domain camelCase 转换唯一层（§9 映射表全量；对齐整站 infrastructure/adapters/* 约定——15_报告域 §8 同构，见下）
domain/
└─ model/benchmark.ts                    # RankingRow / RankingFilters / MetricMappingInfo / RankingGroup 类型
```

- 组件树（routes/features/lib）在 **interfaces 层**；查询/分组/筛选纯逻辑在 **application 层**；HTTP 客户端在 **infrastructure 层**；类型在 **domain 层**——与整站 DDD 四层约定一致（基座卡 §10 依赖规则：interfaces → application → infrastructure 单向，ui 组件零反向依赖）。路由组件属 interfaces，装配进基座卡 §10 组合根 `app/router.tsx`（beforeLoad 守卫统一在组合根挂），本页不另设 app/ 文件。
- **DTO→Domain camelCase 映射（唯一转换层 = `infrastructure/adapters/benchmarkAdapter.ts`）**：后端 `GET /api/v1/benchmarks/ranking` 返回 **snake_case** 字段（`report_service/infrastructure/persistence/benchmark_repository.py:_row_dict` 实测），**interfaces 层组件只见 camelCase Domain 字段**——`api/benchmarkApi.ts` 仅 HTTP 取回，`adapters/benchmarkAdapter.ts` 整体映射（整站 `infrastructure/adapters/*` 转换层约定，15_报告域 §8 同构），组件规格（§4.4/§5.3）一律写 camelCase。全量映射表：

| HTTP DTO 字段（snake_case，后端实测） | Domain 字段（camelCase，组件引用） |
| --- | --- |
| `id` / `source` / `category` / `metric_code` / `metric_name` / `unit` / `direction` / `rank` / `total` / `percentile` / `score100` | 同名（`id` / `source` / `category` / `metricCode` / `metricName` / `unit` / `direction` / `rank` / `total` / `percentile` / `score100`） |
| `subject_name` / `subject_type` / `device_type` | `subjectName` / `subjectType` / `deviceType` |
| `benchmark_suite` / `scenario_key` | `benchmarkSuite` / `scenarioKey` |
| `metric_value` / `gap_best` / `gap_median` / `delta_external` | `metricValue` / `gapBest` / `gapMedian` / `deltaExternal` |
| `published_task_id` / `published_task_version` / `report_id` / `baseline_id` | `publishedTaskId` / `publishedTaskVersion` / `reportId` / `baselineId`（`baselineId` 仅排障用不显示） |
| `computed_at`（ISO 字符串） | `computedAt` |

  - 查询参数：`GET /ranking` 的 `metricCode / publishedTaskId / subjectName` 后端 alias 兼容两拼写（`benchmark_routes.py:138-141` 实测），前端直接发 camelCase；`suite / category / source` 两拼写一致。
  - 指标映射响应（`GET /metric-mappings`）：`dimension_name→dimensionName / metric_code→metricCode / metric_name→metricName / scenario_tags→scenarioTags`，同层转换。
- 现有 Vue 前端无可平移逻辑（本页全新）；已发布任务 Benchmark 徽章→本页的入口链路由任务域卡 INT-354 落地。

### 实施改造清单（供实施卡）

1. 引入 `@visactor/react-vchart@^2.1.2`（对齐 newAPI 版本）+ 照搬 `web/src/lib/use-chart-theme.ts`。
2. 落 routes + features/rankings 全套组件（§4/§5 规格）；`groupRankings.ts`/`rankingFilters.ts` 配 vitest 单测（分组边界：并列名次/单主体不归一化 score100 为空/场景缺省「通用」）；`adapters/benchmarkAdapter.ts` DTO→Domain 映射配 vitest 单测（snake_case→camelCase 全字段，interfaces 层零 snake_case 断言）。
3. 抽平台件 `algorithm-selector.tsx`（Command 搜索 + 卡片网格双通道，INT-355 §3.4 基准）与 `useRankingAlgorithm`（页内 store，**不写回全局**），落 `algorithm-card-grid.tsx` 网格（每算法一张大卡 + 全部算法首卡 + 选中高亮 + 参数摘要 + 只读降级条，INT-436 §3.4 契约）。
4. 公开路由与站头/页脚接导航栏卡（INT-344）的 PublicLayout；导航入口「排行榜」由导航栏卡按 `benchmark:ranking:read` 渲染（未登录隐藏、URL 直达数据 403 空态）；主题切换/多预设接基座卡（INT-343）机制。
5. 「待后端立项」四项随本页实施不做、不占位：时间维度周期页签、厂商份额卡、升降榜卡、**榜单按算法过滤**（§2.4，算法卡片网格先行落地为显示/切换）；RBAC 补码已由 INT-429 落地（seed 补 6 码并授 tester+algo_engineer），不再单独立项（§6.1）。
6. 回归断言：URL 筛选刷新还原、并列名次显示、深浅色图表重建、无权限角色入口隐藏 + URL 直达数据 403 空态（不跳登录）、AUTH_MODE=off 全放行、**算法卡片网格完整/降级两态 + 页内切换不写全局**、组件字段全 camelCase（零 snake_case 泄漏到 interfaces）、移动端单栏塌缩。
7. **INT-381 返修 + INT-344 v1.4 路由对齐**：落 `benchmark-ranking-block` 排行区块组件（供 15_报告域 §3.8 装配）；**不新建 `/benchmarks/*` 前端路由**——报告列表并入报告中心类型页签、详情复用 `/report/{reportId}`（落位实施卡基线裁定）；发布接口 `POST /api/v1/benchmarks/reports` 接入；DTO 转换并入 `adapters/benchmarkAdapter.ts`；回归断言：排行区块异步进度/来源筛选/版本标注/导出 HTML 含排行区块。

---

## 10. Benchmark 报告域（发布 / 列表 / 详情 / 导出 HTML 含排行）

> **INT-381 前置审核打回补全**：本卡 v1.2 只覆盖排行展示页（读侧），Benchmark 报告域整块缺失。按 `报告Benchmark排行功能设计文档.md` 实测补全（:105/:107/:175-183/:388-394/:436-457），与 15_报告域.md §3.8 联动（报告详情页内嵌排行区块，15 消费本卡组件规格）。

### 10.1 Benchmark 报告发布（入口 / 流程 / report_type='benchmark'）

- **入口**：排行区块内「发布 Benchmark 报告」按钮——将当前排行结果生成独立 Benchmark 报告（报告Benchmark排行功能设计文档.md:107 实测）。
- **流程**（§4.5 :175-183 实测）：触发生成 → 收集排行结果 → 复用报告生成器 → 存储 → 可查看/导出。
- **类型**：`report_type='benchmark'`（独立 Benchmark 报告，不混入 task/comparison）。
- **接口**：`POST /api/v1/benchmarks/reports`（生成并发布，:388-394 实测）。

### 10.2 Benchmark 报告列表 / 详情（接口 + 路由）

- **接口**（:388-394 实测）：`GET /api/v1/benchmarks/reports`（列表）+ `GET /api/v1/benchmarks/reports/{reportId}`（详情）。
- **前端路由（INT-344 v1.4 对齐，2026-10-16 裁定）**：**不新建 `/benchmarks/*` 前端路由**——Benchmark 报告列表并入**报告中心类型页签**（`/reports`，DataTable 版式 + 类型徽标「Benchmark 报告」）；详情**复用报告详情页 `/report/{reportId}`**（报告头/导出/分享/AI 入口由 **15_报告域.md §3.8** 落位，本卡只定义排行区块组件）；具体落位在实施卡基线裁定。后端接口 `GET /api/v1/benchmarks/reports` + `/reports/{reportId}`（:388-394 实测）不变。

### 10.3 排行区块组件规格（14 定义，15 消费）

> 报告详情页内嵌「Benchmark 排行」区块（:105/:187 实测）：**异步计算 + 进度轮询**、**来源筛选**（仅实测/仅导入/全部/仅看有差异的）、**版本标注**（实测轨 `v{publishedTaskVersion}`）、**导出 HTML 时包含排行区块**。

| 部件 | 规格（报告Benchmark排行功能设计文档.md:436-444 实测） |
| --- | --- |
| 排行表 | 列=名次 / 被测主体 / 主体类型 / 数据来源标记 / 指标值 / 与头部差距 / 百分位条 / 实测导入差异列 delta——行字段徽章语义照本卡 §2.2 ReadModel（subject_type/device_type/source/gap_best/percentile/delta_external） |
| 参考线图表 | ECharts 横向柱状图 + 中位数与最佳参考线（排行区块专用 ECharts；视觉与本卡 §4.4 指标值横向条形图同构） |
| 异步计算 | 计算中进度条/轮询，完成后渲染；失败保留上次排行结果（§2.3 失败语义复用） |

- **15 联动**：15_报告域.md §3.8 报告详情页装配本区块组件（`interfaces/features/benchmark-ranking-block/benchmark-ranking-block.tsx`，§9 组件树），15 只装配不重设计。
- **DTO→Domain**：`/benchmarks/reports` 端点响应同样走 `infrastructure/adapters/benchmarkAdapter.ts` 转换（§9 同层）。

---

## 修订

| 日期 | 说明 |
| --- | --- |
| 2026-10-14 | 初稿：newAPI rankings 版式对齐 + B 域 benchmark 双轨排行全量实测映射 + 数据缺口标注待后端立项 + RBAC 映射 + 中文文案 + React 组件树/DDD 落位。 |
| 2026-10-15 | 负责人改判（INT-442 联动）：§3.2 算法口径推翻——原「本页不设算法筛选、与全局切换器无联动」改为**页面内「当前算法」大卡片**（复用 INT-436 工作台概览算法大卡片契约 + INT-355 §3.4 双通道选择器），**不再用右上角全局切换器**；页内独立不写回全局（公开页）；ReadModel 无算法维度 → 榜单按算法过滤标注待后端立项；新增 §4.5 大卡、§5.1/§5.6 交互、§6.2「当前算法」列、§7 文案、§9 组件树与清单同步。 |
| 2026-10-16 | INT-391 审核放行条件修订（v1.2）：①文案口径全量「排行榜」——页内 H1（§4.2/§7）、组件文案、导航引用（§3.1/§6.2/§9 清单）改纯中文，站内不出现 Benchmark 字样（红线④，INT-344 定稿）；②§9 补 DTO→Domain camelCase 全量字段映射（唯一转换层 `benchmarkApi.ts`），§4.4 组件规格字段改 camelCase；③未登录行为对齐 INT-344——入口隐藏 + URL 直达 + 数据 403 空态（不跳登录，新增 §5.1 权限空态/§7 权限空态文案，§6.2 各角色行同步）；④基座节号勘误（§5.9/5.8/5.10/5.11/5.6→§5 组件表对应行、§3.8→§3.3、§9 依赖规则→§10）；⑤权限码计数 5→6（§6.1）。 |
| 2026-10-16 | 前置审核 INT-381 打回修订：补 Benchmark 报告域（新增 §10）——报告发布（入口/流程/report_type='benchmark'）、报告列表/详情（`/benchmarks/reports` + `:reportId`，接口与路由引用报告Benchmark排行功能设计文档.md:388-394/:446-457）、报告详情内嵌排行区块组件规格（14 定义、15_报告域 §3.8 消费联动）、导出 HTML 含排行；§9 组件树补 benchmarks 路由 + `benchmark-ranking-block` 组件 + `infrastructure/adapters/benchmarkAdapter.ts` 转换层（对齐整站 `infrastructure/adapters/*` 约定）；实施清单补 §9-7。 |
| 2026-10-16 | INT-429 落地回写（总控放行条件 #1，回写归属 UX设计师A）：§6.1 权限事实改「6 码已定义并授 tester+algo_engineer（全 6 码）、guest/device_admin 未授」——原「缺口/待后端立项（RBAC 补码）」撤销；§6.2 角色映射表按当前 seed 重写（tester/algo 导航可见、可读榜、可触发重算；device_admin/guest 维持 403），「立项建议」列改「立项结论（已落地）」；§3.1 入口判定同步；实施清单 #5 RBAC 补码改注已落地。 |
| 2026-10-16 | INT-391 复核收口对齐（UX设计师B）：§10.2 前端路由按 INT-344 v1.4 对齐——**不新建 `/benchmarks/*` 前端路由**（列表并入报告中心类型页签、详情复用 `/report/{reportId}`，落位实施卡基线裁定）；§9 组件树移除 `routes/benchmarks/*`、保留 `benchmark-ranking-block`；§2.1/§2.5/§6.2 写侧界面归属按总控裁决改注（另行立项「benchmark 配置写侧界面」，不归 INT-362）；§4.4 radius-lg=12px 笔误按基座卡 §5 组件表 Card 行 rounded-xl 校准。 |
| 2026-10-16 | **INT-442 口径修正（负责人 2026-10-16）**：算法切换大卡片 = **每算法一张大卡**（算法卡片网格，不是单张当前算法卡）——§3.2/§4.5 由「「当前算法」大卡片」重做为「算法卡片网格」：数据源改 `GET /algorithm/definitions` 全量（含描述/参数摘要，不用仅 value/name/group 的 `/options`）、每卡=算法名+分组+参数摘要+描述、点击直选=切换页内算法、选中态高亮、首卡「全部算法」、离线卡置灰、只读降级条保留；**页内独立 store 语义不变**（公开页不污染全局，2026-10-16 修正仅改形态）；§2.1 映射表/§4.1/§5.1/§5.6/§6.2/§7 文案/§8 token/§9 组件树（algorithm-card-grid/useRankingAlgorithm）/实施清单同步；INT-486 可视稿按本口径修正（其卡单独落）。 |
| 2026-10-16 | 核心业务口径对齐（负责人 2026-10-16：多友商横向能力对比）：§7 Hero 副标题改「多个厂商模型/APP/API 在同一标准化环境、同一测试集与指标下同时实测，按指标与场景生成名次，横向看清业界水平。」——「按指标生成名次」口径保留，显式落「多友商同集同指标同时实测横向对比」业务模型；首页六卡「多 API 接入」改「多友商横向对比」表述归 INT-345（A 线），报告域/测试执行联动由对应卡承接。 |
