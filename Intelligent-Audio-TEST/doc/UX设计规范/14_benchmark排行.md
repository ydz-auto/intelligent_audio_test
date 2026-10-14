# Benchmark 排行页 UX 设计规范（对齐 newAPI rankings）

> 卡 INT-359 ｜ UX设计师B ｜ 2026-10-14 ｜ 基准：newAPI 参照源码 `D:\00_code\new_api_xagents`（web/src/features/rankings 全目录、web/src/routes/rankings、web/src/hooks/use-top-nav-links.ts、web/src/lib/nav-modules.ts、web/src/lib/use-chart-theme.ts、web/src/components/layout/components/public-layout.tsx｜public-navigation.tsx），本平台后端实测 `report_service/interfaces/api/benchmark_routes.py`、`api_gateway/routes/benchmark_bp.py`、`api_gateway/application/services/benchmark/benchmark_service.py`、`report_service/infrastructure/persistence/models/benchmark_models.py`、`report_service/application/services/benchmark_ranking_service.py`、`report_service/domain/entities/benchmark.py`、`scripts/migrations/202608/seed_rbac.py`，全部取材自实测源码，无杜撰。
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
| `POST /sources`、`POST /baselines(/version)`、`POST|PUT /metric-mappings` | `benchmark:baseline:write|publish`、`benchmark:mapping:manage` | 写侧（数据源/基线导入/映射管理——归配置运维卡 INT-362 设计，本页不设） |

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
| `published_task_id` / `published_task_version` / `report_id` | 实测轨溯源（已发布任务/版本/来源报告） | 「v{version}」徽章 + 「查看报告」链接（→ `/report/{report_id}`，report:read 门控） |
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

### 2.5 范围边界

- 本卡只做**排行展示页（读侧 + 重算按钮）**；数据源管理/基线导入/指标映射管理是写侧资源界面，归**配置运维卡 INT-362** 设计（接口契约已在 §2.1 记录）。
- 「Benchmark 徽章」联动：任务域已发布任务卡的 Benchmark 徽章（`PublishedTaskPanel.vue:19` 现状）在新前端可链入本页并预置 `publishedTaskId` 筛选（`/ranking` 实测支持该参数）——由任务域卡 INT-354 落地，本页只保证 URL 参数可还原。

---

## 3. 「newAPI 页面 → 本平台页面」映射表

### 3.1 映射总表

| newAPI rankings | 本平台现状（Vue，只读参考） | 映射进新前端 |
| --- | --- | --- |
| `/rankings` 公开排行页 | **无此页面**（benchmark 仅有后端接口与已发布任务上的徽章，站内无任何排行界面） | **新增「Benchmark 排行」页 `/rankings`**（公开路由，权限判定见 §6） |
| Hero 周期页签（today/week/month/year 下划线页签） | 无 | **类别维度下划线页签**：全部 / 语音识别 / 语音对话 / 语音合成 / 翻译（`category` 参数；周期切换待后端立项，见 §2.4） |
| Top Models 主卡（堆叠柱 + LLM Leaderboard 双栏榜） | 无 | **指标组卡 ×N**（每组=category×metric×scenario 一个组）：组头（指标名+方向徽章+参与主体数+计算时间）+ 指标值对比条形图（前端派生）+ 双栏主体榜单 |
| Market Share 厂商份额卡 | 无 | 不做（数据缺口，待后端立项） |
| Pulse 升降榜双卡 | 无 | 不做（数据缺口，待后端立项） |
| ModelLink → /pricing/$modelId | 无对应详情页 | **SubjectLink**（主体名→本页 `subjectName=` 筛选，同页联动）+ **ReportLink**（实测轨行→`/report/{report_id}`，`report:read` 门控；外部轨行无详情页，仅文字） |
| GrowthText（↑↓ 环比） | 无 | **DeltaText**（基线差 `delta_external`：±值+单位，双轨并存时显示；正负色沿用 emerald/rose 语义——按 direction 语义定正负色，见 §5.4） |
| `GET /api/rankings?period=` 单快照 | `/api/v1/benchmarks/ranking`（六参数筛选，单页全量） | `GET /api/v1/benchmarks/ranking` + `/ranking/subjects` + `/metric-mappings?activeOnly=true`（指标下拉）三请求 |
| 顶部导航 rankings 模块（本 fork 实测文案「Availability」→/platform；/rankings 不进导航，nav-modules 可控 enabled/requireAuth） | 无 | **顶部导航「Benchmark 排行」直达 `/rankings`**（负责人口径「顶部导航含 benchmark 排行、报告直达」；入口可见性按 `benchmark:ranking:read` 权限判定，导航树由导航栏卡 INT-344 统一落地。newAPI 的 enabled/requireAuth 站点级开关机制作参照，站点设置域纳入与否待后端立项） |
| PublicLayout 公共外壳 | 无（Vue 登录后单壳） | 复用 newAPI PublicLayout 骨架（站头+页脚），与首页/关于/文档页共用同一外壳——本卡只消费，外壳由导航栏卡 INT-344 / 关于页卡 INT-348 统一定义 |
| 图表 VChart + useChartTheme 深浅色 | 无 | 同款引入 `@visactor/react-vchart` + `use-chart-theme.ts` 机制（照搬，chart 主题跟随 next-themes） |

### 3.2 全局算法切换器口径（负责人 2026-10-14）

本页**不设算法筛选**，与全局切换器无联动：

- 排行 ReadModel 无算法维度字段（§2.2 全字段实测）；排行按被测主体聚合，与「当前测试算法」无关。
- 本页是公开页，走 PublicLayout 公共站头（对位 newAPI PublicHeader——右侧仅主题切换与登录/头像），全局算法切换器挂登录壳导航栏右上角（导航栏卡 INT-344），不在公共站头出现。
- 若未来 ReadModel 增加算法维度，再立项补筛选并与全局切换器联动（待后端立项，不在本卡）。

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
      ├─ 筛选行（测试集 / 指标 / 数据来源 Select + 主体搜索 Input；本平台扩展，参数全部实测存在）
      ├─ MetricGroupCard ×N（按 category×metric×scenario 分组，组内 rank 升序）
      │  ├─ 卡头：图标+「{指标名} · {场景}」+ 方向徽章 ｜ 右侧：参与主体 N + 计算于 {computed_at}
      │  ├─ 指标值对比条形图（VChart 横向条形，h-60 sm:h-72，前端派生）
      │  └─ border-t 榜单块：SubjectLeaderboard（双栏榜单，对位 ModelLeaderboard）
      └─ （空态/加载/错误三态见 §5.5）
```

- 间距、断点、容器宽度全部照搬 newAPI 实测值（§1.2），不自研布局。
- 组卡数量 = 当前筛选下的 `(metric_code × scenario_key)` 组数（category 由页签锁定）；组间 `space-y-8`。

### 4.2 RankingsHero（对位 rankings-hero.tsx）

- 标题「Benchmark 排行」（`clamp(1.75rem,4vw,2.5rem)` bold tracking-tight）；副标题一句（`text-muted-foreground/80 max-w-2xl text-sm`）。
- 下划线页签（`role='tablist' aria-label='指标类别'`）：全部 / 语音识别 ASR / 语音对话 / 语音合成 TTS / 翻译——样式照 newAPI（`border-b` + 激活 `bg-foreground h-[2px]` 滑条，激活/未激活色同 §1.2）；写入 URL `category=`。
- 页签切换不重置其他筛选（URL search 合并写入，照 newAPI `navigate({search: prev => ({...prev, …})})` 模式）。

### 4.3 筛选行（本平台扩展行）

- 布局：`flex flex-wrap items-center gap-2`，置于 Hero 之下、首张组卡之上；移动端换行堆叠。
- 控件（全部对基座卡 §5 组件选型，h-8）：
  - 「测试集」Select：选项=当前数据去重 `benchmark_suite`（默认「全部测试集」）→ `suite=`。
  - 「指标」Select：选项=「全部指标」+ `metric-mappings?activeOnly=true` 清单（显示 `metric_name`，值 `metric_code`）→ `metricCode=`。映射接口失败时退化为纯文本输入（容错，不打断页面）。
  - 「数据来源」Select：全部来源 / 平台实测 / 外部基线 → `source=`（platform_test/external_import，接口仅接受这两值，`benchmark_service.py:25` 实测）。
  - 「搜索主体」Input（lucide `Search` 前缀图标 + placeholder）：防抖 300ms → `subjectName=`；下拉联想用 `/ranking/subjects`（有输入时出现，键盘可选，Escape 关闭）。
  - 右端「重置」ghost 按钮（任一筛选非默认时出现）。
- 全部筛选状态写入 URL search（zod validateSearch：`category/suite/metricCode/source/subjectName` 全 optional + catch），刷新/分享可还原——照 newAPI 路由 validateSearch 模式。
- **无算法筛选**（§3.2 口径）；无场景独立筛选器（场景是分组键，组卡标题已带场景，同指标跨场景自然分卡）。

### 4.4 指标组卡（对位 models-section.tsx）

- 卡容器：`bg-card overflow-hidden rounded-lg border`（radius-lg=12px 系，基座卡 §4.2）。
- 卡头（`px-5 py-4`，两端对齐）：
  - 左：lucide 图标（按 category 固定：asr=`AudioLines`、voice_llm=`MessagesSquare`、tts=`Volume2`、translation=`Languages`，`text-primary size-4`）+ 标题 `{指标名} · {场景}`（`text-base font-semibold`）+ 方向徽章（「越低越好」=neutral 软底 /「越高越好」=primary 软底，基座卡 §5.9 徽章）+ 说明行（`text-muted-foreground mt-1 text-sm`：「平台实测与外部基线按 {direction} 排名，共 {total} 个主体参与。」）。
  - 右（`text-right shrink-0`）：参与主体数 `font-mono text-2xl font-semibold tabular-nums`（对位 newAPI tokens 大数字位）+ 角标「个主体 · 计算于 {MM-DD HH:mm}」（`text-[10px] tracking-widest uppercase text-muted-foreground/80`，uppercase 仅作用于西文，中文原样）。
- 图表区（`px-5 pb-5`，`h-60 sm:h-72`）：**指标值横向对比条形图**（VChart `bar`，横向，按 rank 升序自上而下）：
  - 单色 `--chart-1`（基座卡 §3.6）；实测轨与外部轨双色区分：实测 `--chart-1` / 外部 `--chart-2`，图例隐藏、行内徽章已区分，tooltip 标注来源。
  - 轴：类目轴（主体名，`autoHide/autoLimit`）；数值轴 `formatMethod` 按指标单位缩写（≥1000 显示 1.2K/3.4M，照 newAPI formatTokens 思路改数值通用版，保留两位内）；网格虚线 `lineDash:[3,3]` + 深浅色 rgba（§1.2 同值）。
  - tooltip：主体名 + 值 + 单位 + 来源；并列名次主体相邻排列。
  - `themeReady` 前与数据为空时显示占位文案「暂无图表数据」（照 newAPI `No history data available` 位置与样式）。
  - **本图为前端派生（数据已存在），不属 §2.4 缺口。**
- 榜单块（`border-t`）：
  - 块头（`px-5 pt-4 pb-2`）：lucide `Trophy`（`size-3.5 text-amber-500`，照 newAPI）+「榜单」（`text-sm font-semibold`）+ 说明「按名次排列，实测轨取最新版本」（`text-muted-foreground/80 mt-0.5 text-xs`）；右端视图切换 Tabs（`line` 变体，基座卡 §5.10）：「列表」（默认，双栏）/「表格」（全字段，见 §5.3）。
  - 榜单双栏（对位 ModelLeaderboard）：`grid grid-cols-1 md:grid-cols-2 gap-x-8`，行数均分左右（`half = ceil(n/2)`，保持单榜视觉节奏）。
  - 榜单行（`flex items-center gap-3 py-2.5`）：
    - 名次：`w-6 text-right font-mono text-xs tabular-nums text-muted-foreground/80`（`{rank}.`，并列共享名次照实显示）。
    - 主体列：主体名 **SubjectLink**（`font-mono text-sm font-medium` + 常驻细下划线，点击=本页 `subjectName` 筛选，同 newAPI「榜单即导航」）；下行徽章组（`text-xs italic` 位对位 newAPI 厂商行）：主体类型（开源/闭源/App，neutral 软底）+ 设备类型（有值才显示：实体设备/HTTP API/WebSocket API）+ `v{published_task_version}`（实测轨）+ 来源徽章（「平台实测」info 软底 /「外部基线」secondary 软底）。
    - 右值列：主值 `{metric_value}{unit}`（`font-mono text-sm font-semibold tabular-nums`）；下行 DeltaText（`text-[11px]`）：实测轨双轨并存时显示「基线差 ±{delta_external}{unit}」（配色按 §5.4），否则显示 `score100`（有值：「{score100} 分」，空值「—」）。
    - 实测轨行尾「查看报告」link 变体小按钮（lucide `FileText size-3` + 文字，`→ /report/{report_id}`，仅 `report:read` 持有者渲染）。
  - 空组不渲染卡（全空时页面级空态，§5.5）。

### 4.5 页脚

复用公共外壳 Footer（导航栏卡/关于页卡统一定义），本页零特判。

---

## 5. 组件与交互细节

### 5.1 三态与加载

- 加载态（首次/切筛选 refetch 时 non-blocking 保留旧数据，TanStack Query `placeholderData: keepPreviousData`）：首访三段 Skeleton（对位 newAPI h-[420px]/h-[360px]/h-[180px] → 本页 Hero 骨架条 + 筛选行骨架 + 组卡骨架×2，`rounded-xl`）；`isFetching` 时筛选行右侧显示 `Loader2 size-4 animate-spin`。
- 空态（查询成功但 0 行）：Empty 组件（基座卡 §5.11，border-dashed 圆角卡）：图标 `Trophy`、标题「暂无排行数据」、描述「尚未计算排行，或当前筛选条件下没有数据。」；持 `benchmark:ranking:compute` 者加主按钮「立即计算」（无权限者无按钮，描述后补一句「请联系管理员计算排行。」）。
- 错误态（请求失败）：`bg-card rounded-xl border border-dashed px-6 py-12 text-center`（照 newAPI RankingsError）+ 「重试」outline 按钮；`message` 取后端 detail（如「查询排行失败，请稍后重试」实测文案）。

### 5.2 「立即计算」（重算交互）

- 可见性：`hasPermission('benchmark:ranking:compute')` 才渲染（无权限整钮隐藏，对齐 newAPI「隐藏而非置灰」）；位置：筛选行右端（与「重置」同组）。
- 点击 → AlertDialog 确认（基座卡 §5.8）：标题「重新计算排行？」描述「将合并平台实测与外部基线全量重算，期间现有排行保持可查看。」按钮「开始计算」（default）/「取消」。
- 进行中：按钮 loading（Spinner+「计算中…」），禁用重复点击；成功 `toast.success('排行计算完成')` + 失效 `rankings` 查询缓存自动刷新；失败 `toast.error('{message}')` + 附加说明「上一次排行结果仍可查看」（后端失败语义 §2.3）。
- 计算是同步接口、低频操作，**不做轮询**（TanStack Query staleTime 5 分钟，同 newAPI）。

### 5.3 列表 / 表格双视图

- 「列表」（默认）：§4.4 双栏榜单——快读名次与主值。
- 「表格」：TanStack Table（基座卡 §5.6）：列=名次 / 主体 / 主体类型 / 来源 / 版本 / 指标值({unit}) / score100 / 百分位 / 与最佳差 / 与中位差 / 基线差 / 计算于；数值列右对齐 `tabular-nums`；方向提示在表头 tooltip（「该指标越低越好」）；空值统一「—」。
- 两视图共享同一组数据与筛选；视图选择存 localStorage（`iatp:rankings:v1:view`），不入 URL。

### 5.4 DeltaText 配色语义（对位 GrowthText，按 direction 定正负）

newAPI 的 growth 是"越大越好"隐含语义；本平台 delta 方向随指标 `direction` 翻转：

- `higher_is_better`：delta_external > 0（超基线）→ emerald `↑`；< 0 → rose `↓`。
- `lower_is_better`：delta_external < 0（低于基线=更优）→ emerald `↓`；> 0 → rose `↑`。
- 显示 `±{|delta| 保留 2 位}{unit}`，0 或空显示「—」（neutral）；色彩 token 用基座卡 §3.4 语义：涨=success 系文本色、跌=destructive 系文本色（emerald/rose 是 newAPI 实测用法，映射到本平台 `text-success / text-destructive`，多主题预设下自动联动）。

### 5.5 筛选联动与深浅色

- 任一筛选变化 → URL search 更新 → 查询键变化自动 refetch（`queryKey: ['benchmarks','ranking',filters]`）。
- 图表深浅色：`useChartTheme`（照搬 newAPI），`key={group-${resolvedTheme}}` 主题切换整图重建；图表底 `background:'transparent'` 融入卡片。
- 深浅两套全走语义 token（§8），页面零硬编码色值；多主题预设（lake-view/rose-garden/默认蓝等）由基座机制驱动，图表色 `--chart-1/2` 随预设自动换。

### 5.6 移动端

- 页签横向滚动（`overflow-x-auto`，不换行）；筛选行纵向堆叠；组卡图表 `h-60`；榜单双栏塌单栏（`grid-cols-1`，照 newAPI）；表格视图横向滚动包裹（`role='region'` + aria-label，文档页卡同款可聚焦容器）。

---

## 6. RBAC 角色 → 页面 → 菜单/按钮映射表

### 6.1 权限事实（实测，非杜撰）

- 网关为 benchmark 路由定义 5 个权限码：`benchmark:ranking:read / benchmark:ranking:compute / benchmark:baseline:read / benchmark:baseline:write / benchmark:baseline:publish / benchmark:mapping:manage`（`benchmark_bp.py` 实测）。
- **缺口**：`scripts/migrations/202608/seed_rbac.py` 的 100 个权限码中**不含任何 `benchmark:*`**（全文 grep 实测）——即 AUTH_MODE=on 时，五个系统角色中**仅 admin（通配 `*`）可访问**，tester/algo_engineer/device_admin/guest 一律 403；AUTH_MODE=off（现状部署）时中间件注入 `['*']` 全员放行。**「待后端立项（RBAC 补码）」**：将 `benchmark:ranking:read` 补入种子并分发角色（建议见 §6.2 建议列，供后端立项参考，非现状）。

### 6.2 角色映射表

| 角色（seed_rbac `ROLES`） | 现状权限判定 | 顶部导航「Benchmark 排行」 | 页面读取（榜单/筛选/搜索） | 「立即计算」 | 「查看报告」行内链接 | 立项建议（待后端立项，非现状） |
| --- | --- | --- | --- | --- | --- | --- |
| admin 超级管理员（`*`） | `*` 通配 | 可见 | 可用 | 可用（`benchmark:ranking:compute`） | 可用（report:read∈`*`） | 维持 |
| tester 测试工程师 | 无 benchmark:* → AUTH_MODE=on 403；off 放行 | off 可见 / on 隐藏 | off 可用 / on 不可用 | 隐藏 | 可用（report:read） | 建议：补 `benchmark:ranking:read`（可读榜） |
| algo_engineer 算法工程师 | 同上 | 同上 | 同上 | 隐藏 | 可用（report:read） | 建议：补 `benchmark:ranking:read` + `benchmark:ranking:compute`（算法侧负责重算） |
| device_admin 设备管理员 | 同上 | 同上 | 同上 | 隐藏 | 隐藏（无 report:read） | 建议：不补（职能无关，导航整项隐藏） |
| guest 游客 | 同上 | 同上 | 同上 | 隐藏 | 隐藏 | 建议：补 `benchmark:ranking:read`（公开榜可读，无溯源报告链接） |
| 未登录访客（AUTH_MODE=on） | 无 | 可见（入口公开展示） | 跳 `/sign-in?redirect=/rankings`（守卫） | 隐藏 | 隐藏 | 建议：路由按 requireAuth 轴处理（对齐 newAPI rankings requireAuth 机制） |

- 前端判定对齐本平台惯例（`authStore.hasPermission` 含 `*` 通配，系统设置卡 §2.0 实测）：页面路由守卫 `hasPermission('benchmark:ranking:read')`，不满足且已登录 → 403 页；未登录 → `/sign-in?redirect=/rankings`；AUTH_MODE=off 放行（与现 Vue 守卫口径一致）。
- 导航按角色渲染的原则由导航栏卡 INT-344 统一实现：本页入口无权限时**整项隐藏**（不是置灰）。
- 页面内无数据写操作按钮（除重算）；数据源/基线/映射管理入口不在本页（归配置运维卡 INT-362）。

---

## 7. 页面文案（中文全量）

### 顶部导航（入口，随导航栏卡统一）

- 「Benchmark 排行」→ `/rankings`；移动端全屏菜单同项；当前页高亮。

### Hero

- 标题：「Benchmark 排行」
- 副标题：「汇聚平台实测与业界公开基线的语音能力横向对比，按指标与场景生成名次。」
- 页签（aria-label「指标类别」）：「全部」「语音识别」「语音对话」「语音合成」「翻译」
- 页签 sr-only 状态：「{名称}，当前已选中」/「{名称}」

### 筛选行

- 「测试集」「指标」「数据来源」「搜索主体」（Input placeholder：「搜索主体名称…」）
- 来源选项：「全部来源」「平台实测」「外部基线」
- 测试集/指标默认项：「全部测试集」「全部指标」
- 「重置」；「立即计算」；确认弹窗：标题「重新计算排行？」描述「将合并平台实测与外部基线全量重算，期间现有排行保持可查看。」按钮「开始计算」「取消」
- 主体联想空提示：「未找到匹配的主体」

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
- 错误态：标题「排行加载失败」；描述=后端 message（默认「查询排行失败，请稍后重试」）；按钮「重试」
- toast：成功「排行计算完成」；失败「{message}」+「上一次排行结果仍可查看」；联想加载失败不打断输入（静默）
- 表格视图 aria（滚动容器）：「排行明细表：{列头拼接}」

---

## 8. 字体/色彩/组件 token 引用

- **字体**：标题 sans semibold（本页无衬线大标题——newAPI rankings 标题即 sans bold）；主体名/数值列 `font-mono` + `tabular-nums`（newAPI 实测同款：主体名 font-mono、数值 font-mono tabular-nums）；角标 10px 大写字距仅作用西文。
- **色彩**（全部引基座卡 `01_全局基座.md`）：表面 `--card/--border/--muted-foreground`；主色 `--primary`（图标/激活强调）；来源徽章 info/secondary 软底（基座卡 §5.9）；DeltaText `--success/--destructive`；图表 `--chart-1/--chart-2`（§3.6，深浅同值随预设联动）；骨架屏 `--skeleton-base/highlight`（§3.8）。多主题预设（lake-view 默认参考、rose-garden、默认蓝等）+ 深浅色由基座机制驱动，本页零特判。
- **组件选型**（全部 newAPI 现成件，基座卡 §5）：Button（default/outline/ghost/link）、Select、Input+Search 图标组、Tabs（line 变体做视图切换 + 页签自绘下划线照 newAPI hero）、Badge、Card 结构、Empty/Skeleton/Spinner、AlertDialog（重算确认）、Tooltip（方向提示）、sonner toast、Table（表格视图）、Collapsible（移动端不做——本页无侧栏，无此依赖）。
- **图表**：`@visactor/react-vchart ^2.1.2`（newAPI `web/package.json:44-45` 实测同版本）+ `use-chart-theme.ts` 照搬；轴/网格色 rgba 值照 §1.2。
- **待基座卡落 token**：色值、字号阶梯已定稿（基座卡为基准稿），本卡语义 token 名零改动替换。

---

## 9. React 组件树 + DDD 四层落位

```
interfaces/
├─ routes/rankings/index.tsx             # /rankings 公开路由：validateSearch(zod) + 守卫
│                                        #   （benchmark:ranking:read / AUTH_MODE=off 放行 / 未登录跳登录）
├─ features/rankings/
│  ├─ index.tsx                          # Rankings 页骨架（光晕层 + PageTransition 容器 + 三态路由）
│  ├─ components/
│  │  ├─ rankings-hero.tsx               # 标题 + 说明 + 类别下划线页签
│  │  ├─ ranking-filters.tsx             # 筛选行（Select×3 + 主体搜索联想 + 重置 + 立即计算）
│  │  ├─ metric-group-card.tsx           # 组卡（卡头统计 + 图表区 + 榜单块）
│  │  ├─ metric-bar-chart.tsx            # VChart 横向对比条形图（themeReady 门控 + 深浅重建）
│  │  ├─ subject-leaderboard.tsx         # 双栏榜单（对位 ModelLeaderboard，均分左右列）
│  │  ├─ subject-table.tsx               # 表格视图（TanStack Table，全字段 + 横向滚动包裹）
│  │  ├─ entity-links.tsx                # SubjectLink（本页筛选链）/ ReportLink（report:read 门控）
│  │  ├─ delta-text.tsx                  # 基线差文案（direction 感知正负色，对位 GrowthText）
│  │  └─ source-badge.tsx                # 来源/主体类型/设备类型/版本 徽章组
│  └─ lib/format.ts                      # formatMetricValue（单位缩写）/ formatGap / formatComputedAt
application/
├─ rankings/useRankings.ts               # TanStack Query（queryKey=[benchmarks,ranking,filters]，
│                                        #   staleTime 5min，keepPreviousData；对位 newAPI use-rankings.ts）
├─ rankings/useMetricMappings.ts         # 指标映射查询（指标下拉数据源，失败静默退化）
├─ rankings/useRankingSubjects.ts        # 主体联想查询（防抖 300ms，enabled=有输入）
├─ rankings/useComputeRanking.ts         # 重算 mutation（成功失效 rankings 缓存 + toast）
├─ rankings/groupRankings.ts             # 纯函数：rows → (metric_code×scenario) 组，组内 rank 升序（单测）
└─ rankings/rankingFilters.ts            # URL search ↔ 筛选状态（zod schema + 默认值合并）
infrastructure/
└─ api/benchmarkApi.ts                   # GET/POST /api/v1/benchmarks/ranking…（http 客户端封装）
domain/
└─ model/benchmark.ts                    # RankingRow / RankingFilters / MetricMappingInfo / RankingGroup 类型
```

- 组件树（routes/features/lib）在 **interfaces 层**；查询/分组/筛选纯逻辑在 **application 层**；HTTP 客户端在 **infrastructure 层**；类型在 **domain 层**——与整站 DDD 四层约定一致（基座卡 §9 依赖规则：interfaces → application → infrastructure 单向，ui 组件零反向依赖）。
- 现有 Vue 前端无可平移逻辑（本页全新）；已发布任务 Benchmark 徽章→本页的入口链路由任务域卡 INT-354 落地。

### 实施改造清单（供实施卡）

1. 引入 `@visactor/react-vchart@^2.1.2`（对齐 newAPI 版本）+ 照搬 `web/src/lib/use-chart-theme.ts`。
2. 落 routes + features/rankings 全套组件（§4/§5 规格）；`groupRankings.ts`/`rankingFilters.ts` 配 vitest 单测（分组边界：并列名次/单主体不归一化 score100 为空/场景缺省「通用」）。
3. 公开路由与站头/页脚接导航栏卡（INT-344）的 PublicLayout；导航入口「Benchmark 排行」由导航栏卡按 `benchmark:ranking:read` 渲染；主题切换/多预设接基座卡（INT-343）机制。
4. 「待后端立项」三项随本页实施不做、不占位：时间维度周期页签、厂商份额卡、升降榜卡（§2.4）；RBAC 补码（§6.1）单独立项。
5. 回归断言：URL 筛选刷新还原、并列名次显示、深浅色图表重建、无权限角色入口隐藏与 403、AUTH_MODE=off 全放行、移动端单栏塌缩。
