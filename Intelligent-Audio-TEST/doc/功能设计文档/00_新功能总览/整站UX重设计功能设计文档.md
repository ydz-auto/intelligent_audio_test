# 整站 UX 重设计功能设计文档

> 版本：V9.7.31 v1.1（2026-10-14）｜负责人口头需求落文档初始稿

## 1. 需求来源

负责人口头需求（2026-10-14）原话：

> 整个站的 ux 需要让UX设计agent 重新设计 照着 new api

同日追加（基准细化）：

> UX 直接抄 new api 的 字体 导航栏 色彩 系统设置页面 控制台 首页 关于 文档 色彩参考我的网站 https://api.xagents.uk/

**基准（负责人 2026-10-14）**：

1. **布局与页面结构**：直接照 newAPI 的——字体、导航栏、**系统设置页面**、**控制台**、**首页**、**关于**、**文档**页（这七项逐一对齐 newAPI 的实现）。
2. **色彩体系（负责人 2026-10-14 纠偏：该站有多种主题，不得做成单一主题）**：参考负责人站点 https://api.xagents.uk/ （该站为 new-api 部署，**多主题预设**）。照 newAPI 预设机制做**可切换多主题**（`theme-presets.css` + `theme-customization.ts`），lake-view 为默认参考预设。实测取色（2026-10-14 抓取其样式表，供 UX 设计 agent 起步；以站点实际呈现为准）：
   - lake-view 预设：主色翡翠绿 `--primary #00d294`（emerald 系 50~500：`#a4f4cf / #5ee9b5 / #00d294`），secondary `#138187`，ring/chart 同主色
   - 浅色：背景 `#fff / #fafafa / #f5f5f5`，文字 `#172033`
   - 备选主题预设：rose-garden `#e30054`、默认蓝 `#2563eb`
   - 深色近黑（该站暗色底）：`#0a0a0a / #0b0b0b / #191715 / #13110f`
3. 设计规范落 doc/ 时附「newAPI 页面 → 本平台页面」映射表（首页/控制台/系统设置/关于/文档 → 本平台对应页）。
4. **参照源码（负责人 2026-10-14 提供并克隆）**：`D:\00_code\new_api_xagents`（github ydz-auto/new-api fork）——主题预设 CSS 在 `web/src/styles/theme-presets.css`（lake-view 等预设，§1.2 实测色值即出自此）、主题定制逻辑在 `web/src/lib/theme-customization.ts`，页面布局/导航/控制台/系统设置/首页/关于/文档在 `web/src/routes|features|components`。**UX 设计 agent 直接读该仓库取材**，不依赖线上站点猜测。
5. **技术栈（负责人 2026-10-14 追加裁定）**：直接在 V9.7.31 仓库开设计分支（独立 checkout `D:\00_code\V9.7.31-UX`，分支 `design/ux-redesign`）；**新前端用 React 重写、仍按 DDD 四层分层**；其余技术栈与 newAPI 前端一致——实测 `web/package.json`：React 19 + TypeScript + Rsbuild + Tailwind CSS 4 + shadcn 风格组件（@base-ui/react）+ TanStack Router/Query/Table + Zustand + react-hook-form/zod + next-themes + 字体 Public Sans/Lora + lucide 图标 + sonner/vaul + vitest。
6. **样式与组件直接复用 newAPI（负责人 2026-10-14 追加裁定：「css 啥的 直接用new api的 只要照 new api 重新设计页面就行 包括模态窗 啥的」）**：CSS/token/组件样式/**模态窗等交互件直接用 newAPI 现成的**，不自己发明设计体系；页面照 newAPI 重新设计，业务内容换本平台+中文文案。

## 2. 目标与基准

- **全站 UX 重新设计**，以 **newAPI** 的界面风格为基准（负责人点名参照产品；设计时须对照 newAPI 实际界面取材，不得凭空杜撰其风格）。
- **主导**：UX 设计 agent（流水线「前端UX审计员」角色承接设计职责）产出设计规范与方案，开发分批实施。

## 3. 范围

- 全站页面：登录/注册、任务列表与详情、用例管理、设备管理、报告、正式任务、算法配置、系统设置等（**所有页面含模态窗都重新设计**；页面体系按 **RBAC 角色划分**——角色→页面→菜单/按钮可见性映射，清单以本平台 RBAC 实现为准，导航按角色渲染，参照 newAPI root/admin/user 角色化导航）。
- 视觉风格、布局、导航信息架构、组件样式、交互细节。
- **实施形态（2026-10-14 裁定）**：设计分支上以 React 重写新前端（分支 design/ux-redesign，独立 checkout）；现 Vue 前端在主分支保留，切换时机负责人拍板。
- 页面文案中文（负责人同日口径：站内不出现 "Cherry-Pick" 等英文字样，见 任务结果CherryPick挑选合并功能设计文档.md §9）。

## 4. 约束

- 只改交互与视觉，**不改功能口径**：功能行为一律以各域设计文档为准。
- **新前端仍按 DDD 四层分层**（domain/application/infrastructure/interfaces，组件树在 interfaces 层），与后端接口契约不变。
- **工作区隔离**：重设计在独立 checkout（分支 design/ux-redesign）进行，主库 checkout（design/deepseek-harness-migration）不动；分批交付不阻塞功能开发主线。

## 5. 流程

```text
UX 设计 agent 产出设计规范（配色/布局/组件/导航信息架构，对照 newAPI 基准）
  -> 负责人确认基准稿
  -> 分批改造（每批过前端 UX 审计轮）
  -> 负责人签收
```

## 6. 验收标准

1. 设计规范文档落 `doc/`（对照 newAPI 基准，负责人确认基准稿）。
2. 分批改造每批通过前端 UX 审计轮。
3. 整站风格统一，功能无回归（现有 UI 测试通过）。
4. 负责人签收。

## 修订说明

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0 | 2026-10-14 | 初始稿：负责人口头需求落文档 |
| v1.1 | 2026-10-14 | 负责人裁定：直接在 V9.7.31 仓库开设计分支（独立 checkout，分支 design/ux-redesign）；新前端 React 重写、保留 DDD 四层；其余技术栈对齐 newAPI 前端（web/package.json 实测：React 19/TS/Rsbuild/Tailwind 4/shadcn 风格/TanStack/Zustand/Public Sans+Lora） |
| v1.2 | 2026-10-14 | 负责人追加裁定：CSS/组件/模态窗等交互件直接复用 newAPI 现成的，页面照 newAPI 重新设计+内容换中文；色彩改为**多主题预设体系**（站点有多种主题，不得做成单一主题，lake-view 为默认参考预设） |
| v1.3 | 2026-10-14 | 负责人追加裁定：**所有页面（含模态窗）都重新设计；页面体系按 RBAC 角色划分**（角色→页面→菜单/按钮可见性映射表，清单以本平台 RBAC 实现为准，导航按角色渲染，参照 newAPI root/admin/user 角色化导航） |
