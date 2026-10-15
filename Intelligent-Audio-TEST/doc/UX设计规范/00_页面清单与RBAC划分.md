# 页面清单与 RBAC 划分总表（信息架构前置卡）

> 卡 INT-353 ｜ UX设计师A ｜ 2026-10-15 ｜ 性质：**全部页面卡的输入**——其余页面卡的导航结构、路由映射、RBAC 门槛以本总表为准；页面内部细节（版式/组件/文案全量）以各卡产出为准。
> 基准（全部实测，无杜撰）：newAPI 参照源码 `D:\00_code\new_api_xagents`（web/src/hooks/use-top-nav-links.ts + use-sidebar-data.ts + use-sidebar-view.ts、web/src/lib/nav-modules.ts + roles.ts、web/src/components/layout/components/{authenticated-layout,app-header,public-layout,public-header,public-navigation,top-nav,app-sidebar}.tsx、web/src/routes/_authenticated/*、web/src/routes/rankings/index.tsx）；本平台事实 `frontend/src/router/index.ts`（19 路由+守卫实测）、`frontend/src/store/authStore.ts`（hasPermission/'*' 通配实测）、`scripts/migrations/202608/seed_rbac.py`（RBAC 五角色+权限点全量实测）、`docs/RBAC权限划分.md`（角色定义文档）、`api_gateway/routes/benchmark_bp.py`（benchmark 权限码挂载实测）、`api_gateway/routes/{user_bp,role_bp}.py`（用户/角色管理端点实测，INT-30）。
> 信息架构拍板（负责人 2026-10-14）：**首页（门户）与工作台是两个页**；现有业务页全部是工作台功能挂工作台侧栏体系下；顶部导航含 benchmark 排行、报告直达；另有系统设置、个人中心、关于、文档；**全局算法切换器放导航栏右上角、切换一次全局生效，工作台各业务页不再各自做算法筛选**。（2026-10-15 负责人口径：原「控制台」统一更名「工作台」，全表同步。）

---

## 0. 文档地图（分工表 17 卡 ↔ 产出文件）

| 序号 | 文件 | 卡 | 负责人 | 状态 |
| --- | --- | --- | --- | --- |
| 00 | `00_页面清单与RBAC划分.md`（本文件） | INT-353 | A | ✅ 本卡 |
| 01 | `01_全局基座.md`（基准稿 v2.0） | INT-343 | A | ✅ done |
| 02 | `02_导航栏.md` | INT-344 | A | ✅ 产出 |
| 03 | `03_首页.md` | INT-345 | A | ✅ in_review |
| 04 | `04_控制台.md`（页面名已更名「工作台」，文件名沿用） | INT-346 | A | ✅ 产出 |
| 05 | `05_系统设置.md`（v1.1） | INT-347 | B | ✅ 产出 |
| 06 | `06_关于.md` | INT-348 | B | ⏳ 待产出 |
| 07 | `07_文档.md` | INT-349 | B | ✅ 产出 |
| 08 | `08_AI对话页.md` | INT-415 | A | ✅ 产出 |
| 09 | `09_任务域.md` | INT-354 | A | ✅ 产出 |
| 10 | `10_测试执行.md` | INT-355 | A | ✅ 产出 |
| 11 | `11_用例域.md` | INT-356 | A | ✅ 产出 |
| 12 | `12_登录与错误页.md` | INT-357 | A | ✅ 产出 |
| 13 | `13_个人中心.md` | INT-358 | B | ⏳ 待产出 |
| 14 | `14_benchmark排行.md` | INT-359 | B | ✅ 产出 |
| 15 | `15_报告域.md` | INT-360 | B | ⏳ 待产出 |
| 16 | `16_设备域.md` | INT-361 | B | 🔨 进行中 |
| 17 | `17_配置运维.md` | INT-362 | B | ⏳ 待产出 |

> 待产出卡的导航/RBAC 口径先按本总表执行；卡产出后若与本总表冲突，以产出卡为细节源并回写本表勘误（变更记录见 §8）。

---

## 1. 角色与权限事实基线（读实现，不杜撰）

### 1.1 系统内置角色（seed_rbac.py:175-179 `ROLES` 实测，全 is_system=true）

| 角色 name | 中文名 | 对应业务角色 | 权限范围概要 | 权限点数 |
| --- | --- | --- | --- | --- |
| `admin` | 超级管理员 | — | `*` 超级通配（seed_rbac.py:341），含用户/角色/权限管理 | 全部 |
| `tester` | 测试工程师（含测试主管） | 测试工程师+测试主管 | 任务全链（含 task:publish/export/import）、已发布任务全链、用例/音频/分组/标签全链、api_config 全链、报告（read/create/update/delete/compare/download_log，**无 publish**）、评估全链、algorithm:read+case_param_manage、日志全链、device:read、home 全 | ~68 |
| `algo_engineer` | 算法工程师（含质量负责人） | 算法工程师+质量负责人 | 报告（read/create/update/**publish**/compare/download_log）、评估（read/dim_manage/category_manage/import_export，**无 execute**）、算法全链（definition/group/param/case_param_manage）、task:read、testcase/audio/api_config/group/tag:read、log:read+websocket | ~45 |
| `device_admin` | 设备管理员 | 设备管理员 | 被测设备/播放设备/SPL 物理/SPL 数字四域全链（read/create/update/delete/control）、home:read、sse:read；**无任务/用例/音频/报告/算法/日志** | ~28 |
| `guest` | 游客 | — | report:read+report:compare、home:read、sse:read、认证五件；**不可看日志、无任何写操作** | ~9 |

> 精确权限串以 `scripts/migrations/202608/seed_rbac.py:187-253`（TESTER_PERMS / ALGO_ENGINEER_PERMS / DEVICE_ADMIN_PERMS / GUEST_PERMS）为唯一事实源；`docs/RBAC权限划分.md` §4.1 矩阵为设计文档（seed 为落地源，两者不一致处以 seed 为准——如 task:publish/export/import、published_task:*\、digital_spl:*\ 仅见于 seed）。

### 1.2 权限点结构（seed_rbac.py:46-168 实测，共 100 个，22 模块）

`资源:操作` 命名。本总表用到的页面门槛码全列：

| 模块 | 权限串 |
| --- | --- |
| task（11） | read/create/update/delete/execute/merge/batch/reextract/publish/export/import |
| published_task（4） | read/execute/version/archive |
| testcase（7） | read/create/update/delete/copy/preview/import_export |
| audio（6） | read/upload/update/delete/convert/folder |
| device（5）/ playback（5）/ spl（5）/ digital_spl（4） | read/create/update/delete + control（playback 同构）/ test_tone（spl 专属） |
| api_config（5） | read/create/update/delete/test |
| report（7） | read/create/update/delete/publish/compare/download_log |
| evaluation（5） | read/execute/dim_manage/category_manage/import_export |
| algorithm（5） | read/definition_manage/group_manage/param_manage/case_param_manage |
| group（4）/ tag（4） | read/create/update/delete |
| log（3） | read/manage/websocket |
| home（2） | read/refresh |
| sse（1） | read |
| 用户/角色/权限（11） | user:read/create/update/delete/assign_role/grant_permission、role:read/create/update/delete、permission:read、**auth:manage_provider** |
| auth（5） | login/callback/refresh/logout/me |
| 通配（1） | `*` |

### 1.3 校验机制（实测）

- 前端 `authStore.hasPermission(perm)`：`permissions.includes('*')` 直通，否则精确匹配；`hasAnyPermission(...)` 任一满足（`authStore.ts` 实测）。`/auth/me` 返回 permissions 数组（含 roleName），前端不写死角色清单——导航与按钮按权限码渲染，不按角色名硬编码。
- 后端 `User.has_permission`：角色权限 → 用户附加权限（`user_permissions` granted=true 授予 / false 撤销）双层叠加；`*` 仅 admin。
- AUTH_MODE 三态：`off`（后端注入 permissions=['*']，前端无 token 放行——开放模式）/ `dev`（可自助注册）/ `prod`。路由守卫、页面门槛、按钮显隐全部同一套权限函数（AUTH_MODE=off 时全显）。

### 1.4 benchmark 权限码现状缺口（本卡实测发现，待后端立项）

`api_gateway/routes/benchmark_bp.py` 全部端点已挂码：`benchmark:ranking:read`（排行/主体/指标映射查询）、`benchmark:ranking:compute`（立即计算）、`benchmark:baseline:read/write/publish`（数据源/基线）、`benchmark:mapping:manage`（映射写）。**但 `seed_rbac.py` 未定义任何 `benchmark:*` 权限点、未授任何角色**——现网仅 admin（`*` 通配）实际持有。影响与处置：

- 设计规范按「权限码存在」出（页面门槛 `benchmark:ranking:read`）；**seed 补授**（如 tester/algo_engineer/guest 是否授 ranking:read、谁授 compute）列**待后端立项**——补授前除 admin 外顶部导航「Benchmark 排行」项均隐藏（§4.1）。
- 基线/映射管理写侧（baseline:write/publish、mapping:manage）归配置运维卡 INT-362 设置工作区分区，同样待 seed 立项。

### 1.5 角色权限速查（域 × 五角色，seed 实测压缩）

| 域 | admin | tester | algo_engineer | device_admin | guest |
| --- | --- | --- | --- | --- | --- |
| 任务 task | ✓ | 全链（含 publish/export/import） | 仅 read | — | — |
| 已发布任务 published_task | ✓ | 全链 | 仅 read | — | — |
| 用例 testcase / 分组 group / 标签 tag | ✓ | 全链 | 仅 read | — | — |
| 音频 audio | ✓ | 全链 | 仅 read | — | — |
| 被测设备 device | ✓ | 仅 read | — | 全链 | — |
| 播放设备 playback / SPL 物理 spl / SPL 数字 digital_spl | ✓ | — | — | 全链 | — |
| API 配置 api_config | ✓ | 全链（含 test） | 仅 read | — | — |
| 报告 report | ✓ | 无 publish，其余全链 | **有 publish**，其余全链 | — | 仅 read+compare |
| 评估 evaluation | ✓ | 全链（含 execute） | 无 execute，其余全链 | — | — |
| 算法 algorithm | ✓ | read + case_param_manage | **全链** | — | — |
| 日志 log | ✓ | 全链（read/manage/websocket） | read + websocket | — | — |
| 首页 home | ✓ | read + refresh | 仅 read | 仅 read | 仅 read |
| SSE | ✓ | ✓ | ✓ | ✓ | ✓ |
| 用户/角色/权限管理 | ✓（`*`） | — | — | — | — |
| benchmark:* | ✓（`*`） | ⚠ 未 seed（§1.4） | ⚠ 未 seed | — | ⚠ 未 seed |

---

## 2. 完整页面清单（新前端路由总表）

### 2.1 新路由总表（信息架构拍板落地）

布局壳四种：**PublicLayout**（公共站头+页脚，INT-344 出壳）/ **AuthLayout**（登录壳，INT-357）/ **AuthenticatedLayout**（工作台壳：AppHeader+AppSidebar+SidebarInset，INT-346 出壳）/ **无壳错误版式**（ErrorState 居中，INT-357）。

| 路由 | 页面 | 权限门槛 | 布局壳 | 归属卡 |
| --- | --- | --- | --- | --- |
| `/` | 首页（门户落地页） | 公开（全员含未登录） | PublicLayout | INT-345 ✅ |
| `/login` | 登录页 | 公开；已登录 redirect `/dashboard`（sanitize） | AuthLayout | INT-357 ✅ |
| `/register` | 注册页（自双 Tab 拆出） | 公开；同上；注册关闭→引导态 | AuthLayout | INT-357 ✅ |
| `/dashboard` | 工作台（侧栏壳根；页面名与侧栏首项并轨） | 登录即可（`home:read`） | AuthenticatedLayout | INT-346 ✅ |
| `/E2ETest` | 端到端测试（五步向导） | `task:execute` | AuthenticatedLayout | INT-355 ✅ |
| `/APITest` | API 测试（五步向导） | `task:execute` | AuthenticatedLayout | INT-355 ✅ |
| `/tasks` | 任务管理（四页签：全部/运行中/已发布/回收站） | `task:read` | AuthenticatedLayout | INT-354 ✅ |
| `/tasks/$taskId` | 任务详情 | `task:read` | AuthenticatedLayout（drill 同项高亮） | INT-354 ✅ |
| `/testcases` | 用例管理（双视图表格） | `testcase:read` | AuthenticatedLayout | INT-356 ✅ |
| `/audio-import` | 音频管理（上传/列表/试听） | `audio:read` | AuthenticatedLayout | INT-361 🔨 |
| `/devices` | 设备管理（被测/播放设备） | `device:read` | AuthenticatedLayout | INT-361 🔨 |
| `/reports` | 报告中心（测试报告+历史报告页签） | `report:read` | AuthenticatedLayout | INT-360 ⏳ |
| `/ai-chat` | AI 对话（Agent 工作台：报告生成/对比/分析；单栏对话+报告工作模式双栏变体） | `report:read` | AuthenticatedLayout | INT-415 ✅ |
| `/report/$reportId` | 报告查看（详情页） | `report:read` | AuthenticatedLayout | INT-360 ⏳ |
| `/logs` | 日志查看 | `log:read` | AuthenticatedLayout | INT-362 ⏳ |
| `/profile` | 个人中心（用户自己的管理） | 登录即可（无权限码） | AuthenticatedLayout | INT-358 ⏳ |
| `/system-settings/*` | 系统设置工作区（drill-in，§3.4 域树） | 入口：任一设置域权限（§3.4 集合）；域级再分域守卫 | AuthenticatedLayout（侧栏换树） | INT-347 ✅ / INT-362 ⏳ |
| `/rankings` | Benchmark 排行（公开数据页） | 页面公开；数据接口 `benchmark:ranking:read`；导航项按该码渲染 | PublicLayout | INT-359 ✅ |
| `/user-guide` | 文档 | 公开（全员） | PublicLayout | INT-349 ✅ |
| `/about` | 关于 | 公开（全员） | PublicLayout | INT-348 ⏳ |
| `/401` `/403` `/404` `/500` `/503` | 错误页五件 + 根路由 notFound/error 双兜底 | 公开 | 无壳 | INT-357 ✅ |

### 2.2 现有 19 路由 → 新路由映射（全保留重设计，事实源 `frontend/src/router/index.ts`）

现有 19 个业务路由页（home/e2eTest/apiTest/tasks/taskDetail/historyReports/testReports/reportView/reportViewQuery/testCaseManager/evaluation/device/audioImport/splMapping/logView/algorithmConfig/tagManagement/oauthProviders/accountSettings）**全部保留重设计**，无一删除。TanStack Router 配旧路径 redirect 兼容（收藏夹/外部链接不断链）：

| 现路由（Vue） | 权限串（现状实测） | 新路由 | 处置 |
| --- | --- | --- | --- |
| `/` | home:read | `/` | **重设计**为公开门户（门槛从 home:read 改为公开——数据接口仍持 home:read，未登录规模条降级文案，INT-345 §平台规模条） |
| `/E2ETest` | task:execute | `/E2ETest` | 保留路由名，版式重设计 |
| `/APITest` | task:execute | `/APITest` | 同上 |
| `/tasks` | task:read | `/tasks` | 保留，四页签 |
| `/tasks/:id` | task:read | `/tasks/$taskId` | 保留 |
| `/published-tasks` | （redirect） | `/tasks?tab=published` | 延续 redirect（INT-298 口径不变） |
| `/history-reports` | report:read | `/reports` | 并入报告中心「历史报告」页签，旧链 redirect |
| `/test-reports` | report:read | `/reports` | 并入「测试报告」页签，旧链 redirect |
| `/report/:id` | report:read | `/report/$reportId` | 保留（benchmark 行内「查看报告」同落此页） |
| `/report?id=` | report:read | `/report/$reportId` | query 入口 redirect 兼容 |
| `/TestCaseManager` | testcase:read | `/testcases` | 改名 redirect |
| `/Evaluation` | evaluation:read | `/system-settings/testing/evaluation`（URL 以 INT-347 落定为准） | 收编设置工作区「测试配置」域，旧链 redirect |
| `/Device` | device:read | `/devices` | 改名 redirect |
| `/AudioImport` | audio:read | `/audio-import` | 改名 redirect |
| `/SPLMapping` | spl:read | `/system-settings/testing/spl`（同上） | 收编设置工作区「测试配置」域 SPL 分区（含数字域 digital_spl），旧链 redirect |
| `/LogView` | log:read | `/logs` | 改名 redirect |
| `/AlgorithmConfig` | algorithm:read | `/system-settings/algorithm/…` | 收编设置工作区「算法配置」域，旧链 redirect |
| `/TagManagement` | tag:read | `/system-settings/testing/tags` | 收编「测试配置」域标签分区，旧链 redirect |
| `/OAuthProviders` | auth:manage_provider | `/system-settings/auth/oauth-providers` | 收编「认证设置」域，旧链 redirect |
| `/AccountSettings` | （无权限码） | `/profile` | 并入个人中心，旧链 redirect |
| `/:pathMatch(.*)*`（404） | 公开 | 根路由 `notFoundComponent` + `/404` | 五错误页全建（INT-357） |

> 差异注记：INT-361 卡描述写于设置卡收编拍板前（含「声压级映射管理 /SPLMapping」独立页）；SPL 映射落位以已产出的 INT-346 §3.2（不进侧栏根导航）+ INT-347 §3.2（设置工作区「测试配置」域 SPL 分区，`spl:read`+`digital_spl:read`）为准，**INT-361 产出时按此收敛**——设备域卡出 SPL 分区内容规范、落设置工作区路由。

### 2.3 新增页（负责人 2026-10-14 拍板）

`/dashboard`（工作台）、`/system-settings/*`（系统设置工作区）、`/profile`（个人中心）、`/about`（关于）、`/user-guide`（文档）、`/rankings`（Benchmark 排行）、`/register`（注册页，自登录双 Tab 拆出）、`/401 /403 /404 /500 /503`（错误页五件）。

---

## 3. 导航结构（逐项到页面）

### 3.1 顶部导航 TopNav（登录壳与公共站头同构，组件本体归 INT-344）

对位 newAPI `use-top-nav-links.ts`（home/console/pricing→报告/rankings/docs/about 六项）+ `nav-modules.ts` 模块开关机制。本平台六项：

| 导航项 | 落点 | 可见性 | 说明 |
| --- | --- | --- | --- |
| 主页 | `/` | 全员 | 公开门户；当前页高亮（activeProps `bg-accent text-foreground`） |
| 工作台 | `/dashboard` | 登录即可（home:read；未登录为受限项——点击弹「需要登录」Dialog，5 秒倒计时跳 `/login?redirect=`，`public-header.tsx:486-524` 机制照搬） | INT-345/346 同口径 |
| 报告 | `/reports` | `report:read`（admin/tester/algo_engineer/guest；device_admin 隐藏） | **报告直达**（负责人口径）；INT-345 文案「报告」 |
| Benchmark 排行 | `/rankings` | `benchmark:ranking:read`（现仅 admin，§1.4；未登录隐藏） | **benchmark 直达**；不进侧栏（公开数据页走 PublicLayout，对齐 newAPI rankings 不在侧栏） |
| 文档 | `/user-guide` | 全员 | 公开 |
| 关于 | `/about` | 全员 | 公开 |

> 文案统一注记：INT-359 产出稿用「Benchmark 排行」、INT-345 用「排行榜」——红线④页面文案一律中文，本总表建议统一「**排行榜**」（纯中文），最终以 INT-344 定稿为准（§7 待确认）。

### 3.2 右上角功能区

**登录壳（AuthenticatedLayout 的 AppHeader 右区，INT-344 出组件）**，从左到右（次序按 INT-344 §3.1 定稿——newAPI 实测 Search→Notification→Language→Config→Profile 相对次序保留，签到/充值摘除，算法切换器插首位）：

1. **全局算法切换器**（本平台特有，负责人口径；主案 INT-344）——总口径 §3.5。
2. 全局搜索（`bg-muted/25 h-8 rounded-md` + ⌘K CommandDialog，照 `search.tsx`；登录即可，命中范围按各域权限动态注册）。
3. 通知（NotificationPopover 照搬；登录即可，数据流 `sse:read` 五角色全持）。
4. 语言切换（LanguageSwitcher 照搬占位；默认中文，多语言包启用与否待负责人确认 §7）。
5. 主题切换（ConfigDrawer：深浅色 + 多主题预设 lake-view/rose-garden/默认蓝…，照 `config-drawer.tsx` + 基座卡机制；全员）。
6. 头像下拉（ProfileDropdown `w-56` 照搬：用户卡[头像+用户名+角色名] → 个人中心 `/profile` → 系统设置（入口判定同 §3.4，不满足隐藏）→ 登出 destructive）。

**公共站头（PublicHeader）**：语言切换 → 主题切换 → 通知 → 分隔线 → 「登录」按钮（未登录）/ 头像下拉（已登录）——`public-header.tsx` 实测顺序（INT-345 §站头实测点）。**全局算法切换器不在公共站头出现**（仅登录壳，INT-359 同口径）。

**newAPI 右上角不引入项**：CheckinRewardsButton / WalletRechargeButton / SystemUpdateAction（签到/充值/系统更新——LLM 业务与部署形态特有）。

### 3.3 工作台侧栏树（INT-346 §3.2 拍板，本卡汇总为总表口径；INT-415 产出后增「AI 工具」组→五组十一项，逐项权限过滤，空组整组隐藏）

| 组（SidebarGroupLabel） | 菜单项 | 路由 | 图标（lucide） | 可见性权限 |
| --- | --- | --- | --- | --- |
| 总览 | 工作台 | `/dashboard` | Activity | 登录即可（home:read） |
| AI 工具 | AI 对话 | `/ai-chat` | MessagesSquare | `report:read` |
| 测试执行 | 端到端测试 | `/E2ETest` | Smartphone | `task:execute` |
| 测试执行 | API 测试 | `/APITest` | ArrowLeftRight | `task:execute` |
| 测试执行 | 任务管理 | `/tasks` | ClipboardList | `task:read` |
| 测试资产 | 用例管理 | `/testcases` | ListChecks | `testcase:read` |
| 测试资产 | 音频管理 | `/audio-import` | Music | `audio:read` |
| 测试资产 | 设备管理 | `/devices` | Headphones | `device:read` |
| 测试资产 | 报告中心 | `/reports` | FileBarChart | `report:read` |
| 管理 | 日志查看 | `/logs` | FileText | `log:read` |
| 管理 | 系统设置 | `/system-settings/site` | Settings | 任一设置域权限（§3.4 集合） |

对位 newAPI `use-sidebar-data.ts` 四组（AI 工具/常规/个人/管理员）→ 本平台重排为总览/测试执行/测试资产/管理；算法配置/OAuth 提供方/评估维度/SPL 映射/标签管理五项**不进侧栏**（收编设置工作区，INT-347 拍板）；个人中心不走侧栏（头像下拉直达，对位 newAPI Profile 在「个人」组——本平台收进头像下拉，侧栏保持纯业务）。

### 3.4 系统设置工作区 drill-in 树（INT-347 v1.1 拍板，URL `/system-settings/<域>/<分区>` 路径式；本卡汇总域级门槛）

命中 `/system-settings/*` 侧栏整树替换为设置树 + 头部「← 返回工作台」（→ `/dashboard`，`sidebar-view-registry.ts` 机制照搬）。

| 设置域 | 分区 | 域级门槛（可见性） | 写操作另需 |
| --- | --- | --- | --- |
| 站点设置 | 站点信息/站点公告/导航模块 | admin（`user:read` 同级口径） | — |
| 用户与权限 | 用户管理/角色权限管理 | `user:read`（或 role:read） | user:*/role:* 按钮级（user_bp/role_bp INT-30 端点实测） |
| 认证设置 | 认证方式/OAuth 提供方 | `auth:manage_provider` 或 `user:read` | 提供方 CRUD：`auth:manage_provider` |
| 算法配置 | 算法列表/分组管理 | `algorithm:read` | definition_manage / group_manage / param_manage（编辑模态窗全部数据 CRUD，INT-362） |
| 测试配置 | 评估维度/SPL 映射（物理+数字）/标签管理 | `evaluation:read` / `spl:read`+`digital_spl:read` / `tag:read`（域入口=三者任一） | dim_manage / spl:create / tag:create 等 |
| 配置运维 | 日志归档/API 健康等（INT-362 落定） | `log:manage`（或域内 read） | INT-362 |

工作区级守卫 = 入口可见性同一集合：`hasAnyPermission('user:read','role:read','auth:manage_provider','algorithm:definition_manage','evaluation:dim_manage','tag:create','log:manage','spl:create','digital_spl:create')`，不满足 redirect `/403`（对齐 newAPI `system-settings/route.tsx:29` 超管守卫模式）。

### 3.5 全局算法切换器总口径（负责人 2026-10-14 拍板；跨卡契约，本卡固化）

- **位置**：登录壳导航栏右上角（全局控制区首位，§3.2）；公共站头不出现。
- **行为**：切换一次全局生效——写 Zustand 全局算法 store（INT-344 主案）；工作台各业务页**不再各自做算法筛选**，页面内算法筛选与全局切换联动。
- **联动规则**（各卡已落地）：业务列表页（任务/用例/音频/设备/API/报告/日志）工具栏渲染**只读联动 chip**（Badge secondary + × 清空）；请求自动附 `algorithm_type`（store 非空时）。测试执行两页（INT-355）步骤0 算法选择**即写回全局**（「测试流程算法是业务步骤而非筛选器」）；页内不提供取消（清空唯一入口=导航栏切换器）；列表过滤空态给「更换算法」+「查看全部（临时解除，仅本页）」。
- **可见性**：`algorithm:read`（切换器数据源=算法定义清单 `GET /algorithm/definitions`）——admin/tester/algo_engineer 显，device_admin/guest 隐藏（隐藏而非置灰）。**本卡拍板**，INT-344 落组件时对齐。
- **不联动区**：工作台统计图表（`GET /tasks/stats` 无算法参数，全域视角，INT-346 口径注记）；设置工作区算法列表分区（展示全部算法并承担 CRUD 本体，切换器只读引用同一数据源）。

### 3.6 导航渲染规则（全站统一）

- **隐藏而非置灰**（对齐 newAPI requiredRole / admin 组做法，`use-sidebar-view.ts:61` 实测）：无权限菜单项/导航项/入口卡不渲染；空组整组隐藏。
- 当前页高亮：TopNav activeProps + 侧栏 `data-active bg-sidebar-accent font-medium`；子路由同项高亮（`/tasks/$taskId` 高亮「任务管理」，checkIsActive 机制照搬）。
- 移动端：TopNav 收进 DropdownMenu（`top-nav.tsx` 实测）+ 侧栏 Sheet `w-[17rem]`；Ctrl+B 折叠 + SidebarRail（INT-346）。
- URL 直达无权限 → `/403?from=<path>`（INT-357 拍板，替换现「跳首页」静默行为）；未登录 → `/login?redirect=<sanitize 后路径>`。

---

## 4. RBAC 总表（角色 × 页面 × 菜单/按钮）

### 4.1 页面可见性总表（行=页面组，列=角色/状态；✓ 可见 ✗ 隐藏 ↗ redirect）

| 页面 | admin | tester | algo_engineer | device_admin | guest | 未登录访客 |
| --- | --- | --- | --- | --- | --- | --- |
| `/` 首页门户 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓（公开；规模条降级文案） |
| `/login` `/register` | ↗ /dashboard | ↗ | ↗ | ↗ | ↗ | ✓ |
| `/dashboard` 工作台 | ✓ | ✓ | ✓ | ✓ | ✓ | ↗ /login |
| `/E2ETest` `/APITest` | ✓ | ✓ | ✗ | ✗ | ✗ | ↗ /login |
| `/tasks`（+详情） | ✓ | ✓ | ✓（只读） | ✗ | ✗ | ↗ /login |
| `/testcases` | ✓ | ✓ | ✓（只读） | ✗ | ✗ | ↗ /login |
| `/audio-import` | ✓ | ✓ | ✓（只读） | ✗ | ✗ | ↗ /login |
| `/devices` | ✓ | ✓ | ✗ | ✓ | ✗ | ↗ /login |
| `/reports` `/report/$id` | ✓ | ✓ | ✓ | ✗ | ✓（只读+对比） | ↗ /login |
| `/ai-chat` AI 对话 | ✓ | ✓ | ✓ | ✗（无 report:read） | ✓（只读对话+对比，生成卡隐藏） | ↗ /login |
| `/logs` | ✓ | ✓ | ✓ | ✗ | ✗ | ↗ /login |
| `/profile` 个人中心 | ✓ | ✓ | ✓ | ✓ | ✓ | ↗ /login |
| `/system-settings/*` | ✓ 全域 | ✓（测试配置+算法只读/参数管理） | ✓（算法/测试配置域） | ✓（仅 SPL 分区） | ✗（入口集合不满足，整树隐藏） | ↗ /login |
| `/rankings` 页面本体 | ✓ | ✓（数据待 seed，§1.4） | ✓（同左） | ✗（无码，导航隐藏；URL 直达同样 403 数据） | ✗（同左） | ✓ 页面可达（数据 403→登录引导空态；导航项隐藏） |
| `/user-guide` `/about` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓（公开） |
| 错误页五件 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓（公开） |
| 顶部导航项结果 | 六项全显 | 五项（无 Benchmark） | 五项（无 Benchmark） | 四项（主页/工作台/文档/关于——无报告、无 Benchmark） | 五项（主页/工作台/报告/文档/关于，无 Benchmark） | 主页/文档/关于 + 受限项弹登录 Dialog |
| 侧栏树结果 | 全部 11 项 | 10 项（AI 对话+总览+执行 3+资产 4+日志；设置入口✓） | 8 项（AI 对话+总览+任务管理（只读）+用例+音频+报告+日志；设置入口✓；无执行 2 项、无设备） | 2 项（工作台+设备管理；日志/其余隐藏） | 3 项（工作台+AI 对话+报告中心；「管理」组空→整组隐藏） | —（未登录不进壳） |

> AUTH_MODE=off：一切页面全放行全显（permissions=['*']，`authStore.ts` + `router/index.ts` 守卫实测）；`/login` 渲染开放模式 Alert（INT-357 §3.1）。

### 4.2 各页按钮级权限（指针表——细节全量在各卡矩阵节）

| 页面 | 关键操作 → 权限码 | 按钮级矩阵出处 |
| --- | --- | --- |
| 端到端/API 测试 | 整页 `task:execute`；扫描设备 `device:control`；新增设备 `device:create`；API 连接测试 `api_config:test`；发布入口 `report:publish` | INT-355 §RBAC ✅ |
| 任务管理 | 新建/批量/重试 `task:create/batch/execute`；导出 `task:export`；发布 `task:publish` | INT-354 §RBAC ✅ |
| 用例管理 | 新建/编辑/复制/删除 `testcase:*`；导入导出 `testcase:import_export`；预览 `testcase:preview`；分组/标签写 `group:*/tag:*` | INT-356 §RBAC ✅ |
| 设备管理 | device/playback 全链码（INT-361 落定） | INT-361 🔨（进行中） |
| 报告中心 | 生成 `report:create`；发布 `report:publish`（tester ✗ / algo ✓）；删除 `report:delete`；对比 `report:compare` | INT-360 ⏳（沿用 §1.5 域矩阵） |
| 日志查看 | 标记/清空/归档 `log:manage`（tester ✓ / algo ✗） | INT-362 ⏳（沿用 §1.5） |
| 设置工作区 | 各域写码见 §3.4 表 | INT-347 §RBAC ✅（全量矩阵已出） |
| Benchmark 排行 | 查询 `benchmark:ranking:read`；立即计算 `benchmark:ranking:compute`（现仅 admin） | INT-359 §RBAC ✅ |
| 音频管理 | audio 全链码 | INT-361 🔨（进行中） |

### 4.3 守卫行为统一口径（INT-357 拍板 + INT-346/347 落地）

1. 未登录访问受保护路由 → `redirect /login?redirect=<sanitized>`（redirect 消毒：拒 `//`、反斜杠、外站；默认 `/dashboard`）。
2. 已登录无权限 → `redirect /403?from=<path>`（403 页渲染来源页 muted 小字）；**不再跳首页**（修正现状 `router/index.ts:83-85`）。
3. 设置工作区两级守卫：工作区级（§3.4 集合）+ 域/分区级（域码），均 redirect /403。
4. 未匹配路径 → 根路由 `notFoundComponent`（/404 版式）；渲染异常 → `errorComponent`（/500 版式，429/ChunkLoad 特判）。
5. 已登录访问 `/login` `/register` → sanitize redirect `/dashboard`（防死表单）。

---

## 5. newAPI 页面 → 本平台页面映射表

### 5.1 页面映射（含版式对位）

| newAPI 页面 | newAPI 源码落点 | 本平台对位 | 处置/版式对位 |
| --- | --- | --- | --- |
| Home `/` | `features/home` + `routes/index.tsx` | 首页门户 `/` | 整版式照搬，内容换测试平台（INT-345） |
| Console `/dashboard` | `features/dashboard` + `_authenticated/dashboard` | 工作台 `/dashboard` | 工作台四分区照搬（INT-346） |
| Playground `/playground` | `features/playground` | 端到端测试 `/E2ETest` + API 测试 `/APITest` | 三段式全高布局 + 五步向导（INT-355） |
| Usage Logs `/usage-logs/*` | `features/usage-logs` | 任务管理 `/tasks`（四页签+详情） | 双视图表格版式（INT-354） |
| Users `/users` | `features/users` | 用例管理 `/testcases`（用户管理本体→设置工作区） | 表格版式基准（INT-356 / INT-347） |
| Models `/models/*` | `features/models` | 算法配置域（设置工作区） | 分区注册器机制照搬（INT-347/362） |
| Model Pricing `/pricing` | `features/model-pricing` | 报告中心/报告查看 | **版式对位**（模型价格页版式，负责人拍板；LLM 定价内容不引入）（INT-360） |
| Rankings `/rankings` | `features/rankings` | Benchmark 排行 `/rankings` | 版式对位（官方排行榜页，负责人拍板）（INT-359） |
| System Settings `/system-settings/*` | `features/system-settings` | 系统设置工作区 `/system-settings/*` | drill-in 机制+表单脏状态/离开守卫全套照搬；域树重排为本平台六域（INT-347） |
| Profile `/profile` | `features/profile` | 个人中心 `/profile` | 版式对位；并入现 `/AccountSettings`（INT-358） |
| Security `/security` | `features/security` | 个人中心「账号安全」分区 | 并入 INT-358（待该卡确认） |
| Auth（sign-in/sign-up/register/oauth） | `features/auth` | `/login` + `/register`（双页拆分） | auth-layout 版式；OAuth 回调契约保留（INT-357） |
| Errors（401/403/404/500/503） | `features/errors` | 同名五页 + 根路由双兜底 | 同构版式（INT-357） |
| User Guide `/user-guide(-api)` | `features/user-guide` | 文档 `/user-guide` | 栅格+侧栏+代码块照搬；API 手册并入内容分区（INT-349） |
| About `/about` | `features/about` | 关于 `/about` | 版式对位（INT-348） |
| 公共壳 PublicLayout/PublicHeader | `layout/components/public-*` | PublicLayout/PublicHeader | 导航栏卡 INT-344 统一出壳 |

### 5.2 不引入清单（LLM 业务页，负责人 2026-10-14 拍板）

Channels（渠道）/ Keys（密钥）/ Redemption Codes（兑换码）/ Wallet（钱包+充值）/ Subscriptions（订阅）/ Model Pricing 定价内容 / Chat（对话）/ Task Plugins / Setup 引导 / System Info（运维观测语义如需并入设置工作区，待后端立项）/ 签到奖励 / 系统更新角标。对应支付/计费机制不进本平台设计。

### 5.3 机制对位（导航/RBAC 实现机制）

| newAPI 机制 | 源码 | 本平台对应 |
| --- | --- | --- |
| 角色化导航（requiredRole + admin 组过滤） | `use-sidebar-view.ts:55-68` + `lib/roles.ts`（GUEST=0/USER=1/ADMIN=10/SUPER_ADMIN=100 数值梯度） | **权限码过滤**（不引数值梯度）：逐项 `hasPermission(码)` / 入口 `hasAnyPermission(集合)`——本平台 RBAC 是权限点制而非角色数值制，语义等价（隐藏而非置灰） |
| 顶部导航模块开关（home/console/pricing/rankings/docs/about enabled/requireAuth） | `lib/nav-modules.ts` + `/api/status` 驱动 | 前端常量驱动（六项固定）+ 权限码渲染；站点级开关（enabled/requireAuth）待后端立项 |
| drill-in 侧栏视图注册 | `lib/sidebar-view-registry.ts` + `config/system-settings.config.ts` | 机制照搬；注册设置树（INT-346 出骨架、INT-347 出树内容） |
| 侧栏折叠持久化（cookie `sidebar_state`）+ Ctrl+B | `ui/sidebar.tsx:116-130` | 照搬（cookie key 按基座命名规范） |
| 全局搜索 CommandDialog | `components/search.tsx` + `command-menu.tsx` | 照搬；命中范围按权限注册 |
| 主题多预设（preset/font/radius/scale 轴） | `styles/theme-presets.css` + `lib/theme-customization.ts` | 基座卡 INT-343 全套落定（lake-view 默认参考预设） |
| 登录回跳消毒 | `features/auth/lib/auth-redirect.ts` | 照搬（INT-357，安全修复随卡落） |

---

## 6. 信息架构落位（DDD 四层 + 实施改造清单）

### 6.1 分层归属

- **interfaces 层**：路由树（TanStack Router `routes/` 全目录——_public/_authenticated/_errors 组壳 + 页面路由）、四种布局壳组件、TopNav/AppSidebar/AppHeader、设置树注册器、导航项权限渲染组件。
- **application 层**：`usePermissions`（hasPermission/hasAnyPermission 封装 + `/auth/me` 查询）、全局算法 store（Zustand，INT-344 契约：algorithm 全局态 + setAlgorithm/清除）、主题定制 hooks（基座卡）、侧栏视图解析 hook（use-sidebar-view 对位）、auth guards（useAuthGuards：登录/权限/反向守卫三分支）。
- **infrastructure 层**：auth API client（login/register/oauth/me/refresh/encryption-key）、status/options API client、侧栏折叠 cookie 存取、主题 localStorage 存取、redirect 消毒纯函数（domain/lib）。
- **domain 层**：权限码常量表（100 权限点枚举单一来源，对齐 seed）、角色枚举与中文名映射、路由 meta 权限契约（permission 码 ↔ 路由映射常量）。

### 6.2 实施改造清单（供实施卡）

1. TanStack Router 路由树全量新建（§2.1 表 + §2.2 旧路径 redirect 兼容表一次配齐）。
2. `_authenticated` 组壳 beforeLoad（未登录→login / 权限不足→/403?from）+ 各路由 meta 权限码 + `/system-settings` 两级守卫。
3. `usePermissions` + 权限码常量表（domain）落地，替换 Vue authStore.hasPermission（语义不变）。
4. 全局算法 Zustand store + 导航栏切换器（INT-344）+ 各业务页联动 chip（各卡已注明消费点）。
5. 侧栏树四组十项 + 设置树注册器 + drill-in 返回工作台。
6. TopNav 六项 + 右上角功能区 + PublicHeader（INT-344 一卡落全）。

---

## 7. 待负责人确认 / 待后端立项汇总

| # | 事项 | 类型 | 出处 |
| --- | --- | --- | --- |
| 1 | benchmark 权限 seed 补授：tester/algo_engineer/guest 是否授 `benchmark:ranking:read`、谁授 `ranking:compute`、baseline/mapping 写码授谁 | 待后端立项 | §1.4 |
| 2 | 顶部导航「Benchmark 排行」文案统一（本表建议「排行榜」纯中文，红线④）vs INT-359 稿「Benchmark 排行」 | 待负责人/INT-344 定稿 | §3.1 |
| 3 | 语言切换器保留交互位（默认中文），多语言包是否启用 | 待负责人确认 | §3.2 |
| 4 | 顶部导航站点级模块开关（newAPI nav-modules enabled/requireAuth）是否纳入设置工作区 | 待后端立项 | §5.3 |
| 5 | INT-361 卡描述含 `/SPLMapping` 独立页 vs INT-347/346 收编设置工作区拍板——产出时按后者收敛 | 流程对齐 | §2.2 注记 |
| 6 | 首页门槛从 `home:read` 改公开路由（数据接口仍持码），规模条未登录降级文案——负责人拍板过的口径复核 | 已拍板（INT-345），本表登记 | §2.2 |

---

## 8. 变更记录

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-10-15 | v1.0 | 初稿（INT-353）：§0 文档地图、§1 RBAC 事实基线（seed_rbac 100 权限点/五角色实测 + benchmark 权限缺口发现）、§2 新路由总表与 19 旧路由全量映射、§3 导航结构（顶部六项/右上角/侧栏四组十项/设置树/全局算法切换器总口径/渲染规则）、§4 RBAC 总表（页面可见性矩阵+按钮级指针+守卫口径）、§5 newAPI→本平台映射（页面/不引入/机制）、§6 DDD 落位+实施清单、§7 待确认六项 |
| 2026-10-15 | v1.1 | 负责人口径：**控制台更名工作台**——全表「控制台」字样逐处替换为「工作台」（§2.1 /dashboard 行、§3.2 顶部导航项、§3.3 侧栏树标题、§3.4 返回文案、§3.5 联动口径、§4 导航项结果行、§5 映射表、§6 实施清单）；路由 `/dashboard` 与侧栏结构不变，侧栏首项「工作台」与页面名并轨；02/03/04/05/08/09/10/11/12 各卡文档同步核改 |
| 2026-10-15 | v1.1 | INT-344 产出后勘误回写：§0 文档地图 02 卡置「✅ 产出」；§3.2 右上角功能区次序定稿（切换器→搜索→通知→语言→主题→头像——对齐 newAPI app-header 实测相对次序）；§4.1 顶部导航项结果行修正（device_admin 4 项、guest 5 项含报告——guest 持 report:read 实测） |
| 2026-10-15 | v1.2 | INT-415 产出后回写：§0 文档地图 08 行置「✅ 产出」；§2.1 新增 `/ai-chat` 路由行（`report:read`）；§3.3 侧栏树增「AI 工具」组「AI 对话」项→五组十一项；§4.1 新增 `/ai-chat` 可见性行（device_admin ✗、guest 只读）+ 侧栏树结果行更新（admin/tester/algo/device/guest = 11/10/8/2/3 项） |
