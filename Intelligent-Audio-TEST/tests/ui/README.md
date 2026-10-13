# UI 自动化测试层（INT-260）

selenium Page Object 模式的 UI 用例层，补齐测试金字塔顶层：模态窗回填/提交、
表单校验、收藏交互、视图切换等"人手操作"路径的自动化覆盖。

## 运行前提

UI 用例直击运行中的实机栈，且有写操作（造数据），**必须以隔离库起栈**
（负责人数据零污染红线）。两种起栈方式：

**方式 A（推荐）—— 并行隔离栈**（共享栈被其它工作占用时也能跑）：

```
python tests/ui/run_gate.py          # 一键：WMI 起并行栈（端口+1000，隔离库）+ 跑 UI 用例
```

并行栈端口表：网关 6000 / HTTP 6001-6010 / gRPC 51051-51101 / 前端 6273，
Redis 用 db1，日志 `logs/ui_stack/`。栈常驻复用；Postgres 未监听 5432 时
启动器自动经 WMI 脱离进程树拉起（`_pg_start.cmd`，postgres.exe 从 run 内
直启会被平台整树收割，2026-10-13 实证）；显式清理：

```
python tests/ui/utils/parallel_stack.py stop
```

**方式 B —— 主栈切隔离库**（共享栈空闲时，INT-246 标准口径）：

```
python run_all.py --test-db          # 整栈切隔离库 intelligent_audio_test_test
RUN_LIVE_STACK=1 python -m pytest tests/ui -v
python scripts/reset_test_db.py      # 冒烟后清库
```

## 门禁三件套（conftest 会话级强制）

1. **默认 skip**：`RUN_LIVE_STACK=1` 显式纳入（与 tests/api 实机用例同口径，
   不参与日常回归）；
2. **隔离库守卫**：`/health` 上报的 database 必须等于
   `intelligent_audio_test_test`；指向共享业务库或字段缺失 → 整会话 FAIL；
3. **引导自举**：隔离库 RBAC 种子（`scripts/migrations/202608/seed_rbac.py`
   幂等重播）+ admin 账号（空库首注册即 admin 角色，与 .env `DEV_DEFAULT_*`
   同口径 admin/admin123）。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `RUN_LIVE_STACK` | （空=skip） | `1` 显式纳入 UI 实机用例 |
| `UI_FRONTEND_BASE` | `http://127.0.0.1:5173` | 前端地址 |
| `UI_API_BASE` | `http://127.0.0.1:5000` | 网关地址 |
| `UI_TEST_USERNAME` / `UI_TEST_PASSWORD` | `admin` / `admin123` | 引导账号（隔离库自建） |
| `UI_CHROME_BINARY` | `C:\Program Files\...\chrome.exe` | Chrome 二进制 |
| `UI_CHROMEDRIVER` | `e2e_tests/selenium/drivers/...` | chromedriver（沿用既有基建） |

## 结构

```
tests/ui/
├── conftest.py              # 门禁三件套 + Chrome 会话驱动 + 失败取证钩子
├── run_gate.py              # 集成门禁入口：WMI 起并行隔离栈 + 跑用例
├── pages/
│   ├── base_page.py         # Page Object 基类：等待策略 / 登录态注入 / 取证
│   ├── login_page.py        # 登录页 PO
│   └── test_case_page.py    # 用例管理页 PO（视图切换 / 类别读取）
├── utils/
│   ├── api_client.py        # RSA-OAEP 登录客户端 + 测试数据自建自清
│   ├── bootstrap.py         # 隔离库 RBAC 种子 + admin 自举
│   └── parallel_stack.py    # UI 专用并行隔离栈启动器（端口+1000，绝不 kill 占用者）
├── test_ui_01_login.py      # 登录域：表单登录跳转 / 错误提示 / 会话持久化 / 登出
├── test_ui_02_navigation.py # 导航域：侧栏点击 / 直达路由 / 未登录重定向 / 列表加载
├── test_ui_03_case_views.py # 视图域：分组↔标签切换数据一致性（防吞用例）
└── artifacts/               # 失败取证（截图 + console 日志 + page source）
```

## 失败取证

call 阶段失败的用例自动落盘 `tests/ui/artifacts/<用例nodeid>/`：
`screenshot.png` + `console.log`（浏览器 console 全量）+ `page.html`，
缺陷卡直接引用对应文件。

## 登录态复用

非登录用例经 `inject_login_state` 把 API 登录（RSA-OAEP 加密口径）得到的
token/用户写入 localStorage（`auth_token`/`auth_user`，与 authStore 持久化
键一致），免去逐用例重复登录；真实登录表单流由 test_ui_01 专属覆盖。

## 集成门禁接入（推送前冒烟含 UI）

集成工程师推送前冒烟口径（在隔离库跑，测试数据自建自清）：

```
python tests/ui/run_gate.py
```

一条命令完成：并行隔离栈确保就绪（未起则 WMI 脱离进程树自启）→ UI 全量
用例（隔离库自举 RBAC+admin → 造数 → 断言 → 自清）→ PASS/FAIL。
UI 用例不过 → 不推送。守卫会在栈未隔离/未就绪时直接 FAIL，不会静默跳过。
