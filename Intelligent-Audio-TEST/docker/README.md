# docker/ 构建与栈操作手册（INT-1820）

本目录的 Dockerfile / compose / 脚本怎么构建、构建红了怎么判、引擎被构建打崩了怎么恢复。

> **全栈启停唯一入口：仓库根 `python stack.py up/down/status/health`**（compose 栈 + 宿主机
> audio/device 服务）。本目录的 `run_stack.py` 只做 docker-only 操作、`build_stack.py` 只构建镜像，
> 均被 `stack.py` 委托调用。

**构建入口：`python docker/build_stack.py`**（下文所有命令都在仓库根执行）。

## 1. 为什么有这份文档

2026-10-24 INT-1754 发版时，常规 `docker compose build` **连续两次失败**，最后只能拿既有镜像
叠加源码层手工重建才把版本推出去。两段独立故障：

| # | 故障 | 现象原文 | 影响面 |
|---|---|---|---|
| A | apt 源不可用 | `deb.debian.org` 返回 502 / `Temporary failure resolving 'deb.debian.org'` | 单次 build 失败 |
| B | 构建期引擎崩溃 | `error reading from server: EOF`，WSL VM 重启，**全部容器 `Exited (255)`** | **正在跑的 :15000 / :15173 / :16173 真实栈一起被打掉** |

故障 A 已由 Dockerfile 侧修掉（§3）；故障 B 无法从 Dockerfile 侧根治（属 Docker Desktop /
WSL2 稳定性），只能靠「构建前体检 + 串行单服务 + 崩溃后按清单恢复」把它的代价压到最低（§4/§5）。

## 2. 构建入口

```bash
# 只体检引擎，不构建（20s 内必回，不跑无限等）
python docker/build_stack.py --check

# 构建全部 9 个容器化后端服务（audio/device 跑宿主机，无镜像）
python docker/build_stack.py

# 常规发版：只构建这一批变动的服务（推荐）
python docker/build_stack.py api_gateway task_service evaluation_service

# BuildKit 把引擎打崩过 → 换旧 builder，单服务串行重跑
python docker/build_stack.py --buildkit 0 e2e_test_service

# 全量重建（不吃层缓存；重试代价高，见 --retries 提示）
python docker/build_stack.py --no-cache --retries 2 evaluation_service

# 只验构建链路、不碰现役镜像：换一个隔离项目名（镜像 tag 变 int1820-verify-<svc>:latest）
python docker/build_stack.py --project int1820-verify api_gateway
```

> **项目名决定镜像 tag**：compose 产出的镜像名是 `<项目名>-<服务名>:latest`。不指定
> `-p` 时 compose 按 compose 文件父目录名推导（= `docker`），会产出
> `docker-api_gateway:latest` 这种**现役栈根本不用的孤儿镜像**——构建「成功」但发版拿不到
> 新镜像（INT-1820 实测踩到过）。本脚本缺省钉在 `intelligent-audio-test`（现役栈项目名），
> 与 `docker images` 里 `intelligent-audio-test-*:latest` 对齐。`docker/run_stack.py` 同样
> 钉了项目名（`--project` / `COMPOSE_PROJECT_NAME` 可覆盖）——否则 `up` 会另起一套同名服务的
> 第二套栈。

| 退出码 | 含义 |
|---|---|
| 0 | 构建成功，且引擎全程健康、容器集合未被重启 |
| 2 | 参数/前置错误（未开始构建） |
| 3 | 引擎不健康（构建前体检失败，或构建期间被打掉）——**这是故障 B 的判据** |
| 4 | 构建失败（重试耗尽），目标镜像保持构建前身份，没有半成品 |

脚本不 `up`、不重启容器、不删镜像：它只调 `docker compose build`，构建完提示你自己跑
`python docker/run_stack.py health`。**它与「不要打断现役栈」的环境铁律不冲突**——真正会
打断现役栈的是故障 B 本身。

### 2.1 它做的三次对照

1. **构建前体检**：`docker version --format {{.Server.Version}}`，20s 有界。区分三种引擎状态：
   连不上（管道不存在）/ 连上了但 API 500（引擎半死，CLI 会挂 45s+）/ 正常。
2. **VM uptime 对照**：构建前后各读一次 `docker-desktop` VM 的 `/proc/uptime`。
   **这是判定「引擎真重启过」最硬的信号**——VM 重启会让 uptime 归零/变短，而容器状态会被
   同宿主上并行的其他 run 干扰。
3. **本项目容器身份快照**：只取 `com.docker.compose.project=<本项目>` 的容器，记 ID 集合
   **＋ `State.StartedAt`**。ID 集合一致不代表没崩过——引擎重启后 `restart: unless-stopped`
   会把同一批容器原地拉起，ID 一个不少、但 `StartedAt` 全变了。只取本项目的容器，是因为这台
   宿主上并行着其他 run 的栈，全量 `docker ps` 会把它们的启停误判成引擎崩溃。
4. **镜像身份对照**：命中的服务构建前后的 image ID。构建失败时若 ID 仍是旧值，说明没留下
   「看起来是新镜像」的半成品 tag。

## 3. 故障 A：apt 源 502 —— 已修

### 3.1 改了什么（`docker/Dockerfile.*`，9 个后端镜像统一）

覆盖 `build_stack.py` 的 `BACKEND_SERVICES` 全量：`api_gateway` / `task_service` /
`evaluation_service` / `e2e_test_service` / `report_service` / `algorithm_service` /
`auth_service` / `api_test_service` / `db_bootstrap`。每份 Dockerfile 都声明同两个 `ARG`：
`APT_MIRROR`（缺省 `mirrors.tuna.tsinghua.edu.cn`）、`PIP_INDEX_URL`（缺省
`https://pypi.org/simple`），并由 `docker-compose.yml` 的 `x-backend-build-args` 统一透传。
`mock_dut` / `mock_eval` 是纯标准库替身镜像，不跑 apt/pip，无需接；
`frontend` 是 node/nginx 多阶段构建，不走 Debian 源。

1. **apt 源换可达镜像**：`sed -i "s|deb.debian.org|${APT_MIRROR}|g"`，缺省
   `mirrors.tuna.tsinghua.edu.cn`。构建不再依赖 `deb.debian.org` 的可用性。
   **INT-2166**：`api_test_service` / `auth_service` / `report_service` 此前连这行都没有
   （`apt-get update` 直连 `deb.debian.org`），本机网络经代理返回 404 时 **apt 层 exit 100**，
   镜像必红；`task/evaluation/e2e/db_bootstrap` 此前把 tuna 写死在 `RUN` 里，`APT_MIRROR`
   覆盖不生效——一并改为读 `ARG`。
2. **`Acquire::Retries=5`**：镜像源本身也有瞬时 5xx / DNS 抖动，层内重试自愈，不把一次抖动
   放大成一次整 build 失败。9 份 Dockerfile 的每个 `apt-get` 都带。
3. **base image 钉 digest**：`python:3.11-slim` 这个浮 tag 已经漂过（bookworm → trixie，
   2026-10-24 实测部署镜像 `/etc/os-release` = Debian 13）。钉 digest 后同一份 Dockerfile
   产出的基座可复现，不会「昨天能构建、今天因为基座换了发行版而红」。
   **现状（INT-2166 核对）**：只有 `Dockerfile.db_bootstrap` 通过 `ARG PY_IMAGE` 接了这个
   digest（compose 的 `x-backend-build-args` 缺省值）；其余 8 个仍是 `FROM python:3.11-slim`
   浮 tag，compose 传下去的 `PY_IMAGE` 对它们不生效（未声明即被忽略）。基座是否统一钉
   digest 属另一项改动（会切换 8 个镜像的 Debian 发行版），不在本卡范围。

> **pip 源**（INT-2156/2166）：`pip install` 统一带 `--index-url "${PIP_INDEX_URL}"`。缺省
> `pypi.org` 在本机网络实测 ~150 kB/s，全量依赖 30 分钟起——**重建大镜像时建议显式指向镜像源**：
> `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。

### 3.2 覆盖方式

缺省值就是推荐值，不设也能构建（pip 缺省走 `pypi.org`，能通但慢）。要换源（内网 / tuna
不可达 / 想让 pip 走镜像）：

```bash
# 单次覆盖（compose 透传 --build-arg）
docker compose -f docker/docker-compose.yml build --build-arg APT_MIRROR=mirrors.aliyun.com api_gateway

# 或在 .env 里设同名变量（docker-compose.yml 的 x-backend-build-args 读同名变量做缺省）
echo 'APT_MIRROR=mirrors.aliyun.com' >> .env
echo 'PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple' >> .env
```

可用的 apt 镜像源（均实测可达）：`mirrors.tuna.tsinghua.edu.cn` / `mirrors.aliyun.com` /
`mirrors.ustc.edu.cn`。pip 镜像源（实测可达）：`https://pypi.tuna.tsinghua.edu.cn/simple`。

### 3.3 实测（2026-10-25，同一基座、同一台宿主）

| 源 | `apt-get update` 结果 | 耗时 |
|---|---|---|
| `deb.debian.org`（原状） | rc=0，Fetched 10.0 MB | **66s**（155 kB/s） |
| `mirrors.tuna.tsinghua.edu.cn` | rc=0，Fetched 10.2 MB | **10s**（1307 kB/s） |

即当前 `deb.debian.org` 未处于 502 窗口，但只有 tuna 的 1/8 带宽且历史多次 502 / DNS 失败；
502 是间歇性故障，不能等它出现才修。

## 4. 故障 B：构建期引擎崩溃 —— 只能压制，不能根治

BuildKit 构建重层（apt 装 ffmpeg / adb / pulseaudio 这类大层）时会把 Docker Desktop 的
WSL2 VM 打崩，引擎整体重启。不是 OOM（INT-1653 实测 VM 内存峰值 ~3.2/7.9GB，宿主磁盘余量
充足），属 Docker Desktop 侧稳定性问题；本仓库能控制的是**让它少发生、发生时能立刻认出来、
发生后有确定的恢复路径**。

### 4.1 压制手段（按顺序用）

1. **单服务串行**：一次只 build 一个服务，别让 apt/pip 重层并发。`build_stack.py <单服务>` 天然如此。
2. **构建期间不跑其他重活**：不要同时跑 `db_bootstrap`、批量测试、前端打包。
3. **`DOCKER_BUILDKIT=0`（旧 builder）**：优先用于 `e2e_test_service` 这类最重镜像。
   代价是不并行、层缓存命中率低一些。
4. **构建前体检**：引擎已经不健康时不要开始——白等一次崩溃。

### 4.2 判据

`build_stack.py` 退出码 **3** = 引擎不健康 / 构建期间被打掉；输出里会明确写：

- `第 N/M 次构建失败，且引擎已不可用：...` → 构建期引擎崩溃，**不再重试**（重试只会白等）；
- `WARN: 构建期间有容器被重启（StartedAt 变化）——引擎崩过/被重启过。` → 即使构建返回 0，
  也按不稳定记（卡片验收口径要求「全过程引擎不重启」）；
- `容器：N → M；重启 X，新增 Y，消失 Z` → 全栈影响面。

### 4.3 一次 build 成功率（实测）

2026-10-25 本机（Docker 29.8.2 / WSL2 8GB，宿主同时跑着现役栈与其他 run 的容器）：

| 轮次 | 目标 | builder | 结果 | 耗时 | 引擎 / VM |
|---|---|---|---|---|---|
| b1 | `api_gateway`（apt 两层 + pip 全量重做） | BuildKit（默认） | 成功 | ≈15 min | 健康，VM uptime 连续 |
| b2 | `api_gateway task_service evaluation_service`（验收口径，一条命令） | BuildKit（默认） | 成功 | 951s | 健康，VM uptime 2.96h → 3.22h（连续） |
| b3 | `report_service` | **旧 builder**（`--buildkit 0`） | 成功 | 773s | 健康，VM uptime 3.23h → 3.44h（连续） |
| b4 | `e2e_test_service`（全场最重：ffmpeg+adb+alsa+pulseaudio） | BuildKit（默认） | 成功 | 912s | 健康，VM uptime 3.45h → 3.70h（连续） |

构建期间现役栈全程正常：`:15000/health` 200、`15173` 200、`16173` 200，`db_bootstrap` 退出码 0。

结论（本轮实测）：**4 次重层构建 0 次引擎重启**。

- **串行 + 单条命令构建三服务，BuildKit 未再打崩引擎**——历史上两次崩溃（INT-1653 / INT-1754）
  都发生在「apt/pip 重层 + 其他重活并发」的窗口；本轮全程串行、构建期间不跑批量测试，
  连最重的 e2e 镜像也没把 VM 打重启。
- `DOCKER_BUILDKIT=0` **可用**（b3 实测成功），是 BuildKit 再次打崩引擎时的确定绕行；代价是
  不并行、与 BuildKit 缓存不共享，同一服务全量重来时耗时与首次相当（773s vs 其它服务同量级）。
- 因此「一次 build 成功率」的口径不是「BuildKit 一定崩」，而是：**引擎健康 + 串行单服务 +
  构建前体检** 时可稳定成功；不满足这三条时崩溃概率显著上升（历史 2/2 崩溃都落在并发重活窗口）。
  这也是 `build_stack.py` 缺省一次只建你点名的服务、并且先体检再开工的原因。

## 5. 引擎崩溃后的恢复清单

按顺序做，**每步都先有界探测，别把 docker CLI 前台挂到 45s+**：

```bash
# 1) 有界探测：健康 / 半死（API 500）/ 管道不存在
python docker/build_stack.py --check
```

| 探测结果 | 处置 |
|---|---|
| `引擎健康：server=...` | 直接重跑构建（层缓存会命中已完成层） |
| `引擎返回 500：...`（引擎半死） | **不要**反复 `docker desktop restart`——多 run 并发时会互相打架。等 2–3 分钟看是否自愈（INT-1820 2026-10-24 实测约 23 分钟自行恢复） |
| `Docker 引擎管道不存在` | `Docker Desktop.exe` 进程可能已不在：`Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'`，约 1–2 分钟引擎与整套 compose 恢复（比等 watchdog 快；watchdog 在「进程在、引擎不在」形态下帮不上忙） |

```powershell
# 2) 引擎回来后：容器由 restart 策略自行拉起，确认集合与状态
docker ps --format "table {{.Names}}\t{{.Status}}"
```

`db_bootstrap` 容器在引擎重启后会重跑整条引导链（幂等），看退出码判结果：
`docker inspect -f '{{.State.ExitCode}}' intelligent-audio-test-db_bootstrap-1`，**不要**用
`docker compose run` 手喂 stdin。

## 6. 为什么不给 e2e 挂 `/dev/bus/usb`

e2e_test_service 曾映射 `devices: /dev/bus/usb:/dev/bus/usb`。WSL VM 重启后该路径在 VM 内
不存在，容器直接起不来（`error gathering device information while adding custom device`），
建空目录也不行（`not a device node`），历史上只能手敲 `mknod c 189 0` 造假节点兜底，
**每次 VM/引擎重启都要重做一次**。

2026-10-29 核实后确认这条映射纯属冗余，已从 `docker-compose.yml` 删除：

- `e2e_test_service/` 源码零 `usb` / `adb` / `hdc` / `/dev/` 引用；
- 设备操作全部经 gRPC 委托 `device_service`（`device_acl_repository_impl.py`、
  `e2e_device_manager.py` → `DeviceService.CreateDriver`），容器内不需要设备节点；
- `device_service` 不在 compose 编排内（物理设备链路必须宿主形态，见
  `docs/docker-compose.md`），e2e 经 `DEVICE_SERVICE_HOST=host.docker.internal` 连宿主实例。

因此 VM/引擎重启后不再需要任何 USB 恢复动作，VM 里的占位节点也可以删掉。仅当未来有人把
device_service 容器化、并让 e2e 绕过 gRPC 直读 USB 时，才需要重新评估这条映射。

## 7. 可重复执行的验证清单

发版前按这个顺序跑，每步都有确定的预期输出。

### 步骤 0：引擎体检

```bash
python docker/build_stack.py --check
```
预期：`[BUILD] 引擎健康：server=29.8.2`（版本号随 Docker Desktop 升），`rc=0`。
若 `rc=3`，先按 §5 恢复引擎，不要继续。

### 步骤 1：apt 源可用性（Dockerfile 侧的最小验证）

```bash
docker run --rm python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce \
  sh -c 'for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources; do [ -f "$f" ] || continue; \
         sed -i "s|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g" "$f"; done; \
         apt-get -o Acquire::Retries=5 update'
```
预期：`Get:` 行全部指向 `mirrors.tuna.tsinghua.edu.cn`，`Fetched ~10 MB in ~10s`，
**不出现 `Err:` / `502`**，`rc=0`。

### 步骤 2：目标服务一次构建

```bash
# 只验构建链路（隔离项目名，不动现役 <intelligent-audio-test>-*:latest 标签）
python docker/build_stack.py --project int1820-verify api_gateway task_service evaluation_service
# 发布形态（把新镜像打出现役 tag）
python docker/build_stack.py api_gateway task_service evaluation_service
```
预期输出（末尾）：

```
[BUILD] 引擎：健康 server=...
[BUILD] VM uptime：X.XXh → X.XXh（连续，VM 未重启）
[BUILD] 项目 int1820-verify 容器：0 → 0；重启 0，新增 0，消失 0
[BUILD] api_gateway: 新镜像 sha256:...
[BUILD] task_service: 新镜像 sha256:...
[BUILD] evaluation_service: 新镜像 sha256:...
[BUILD] 构建成功（XXXs），引擎全程健康、VM 未重启、本项目容器集合未丢失。
```
`rc=0`。**判红的口径**：`VM uptime` 变短、或引擎不可用（rc=3）——即使构建返回 0 也按「引擎
被构建打崩过」记，改用 `--buildkit 0` 单服务串行复测。

### 步骤 3：构建后栈仍健康（不重启容器）

```bash
python docker/run_stack.py health
```
预期：各服务 health 绿；`docker ps` 的容器集合与步骤 2 前一致。

### 步骤 4：迁移幂等（只有动了 db_bootstrap / 迁移脚本时才跑）

```bash
docker inspect -f '{{.State.ExitCode}}' intelligent-audio-test-db_bootstrap-1
```
预期：`0`（引导链幂等，已初始化库重复 up 秒级跳过）。

## 8. 影响窗口与纪律

- 构建本身**不打断现役栈**：只构建镜像，不 `up`、不重启容器。但**故障 B 一旦发生是全栈影响**
  （全部容器 Exited 255，真实栈 :15000 / :15173 / :16173 一起不可用），所以重构建安排在低峰期。
- 一次发版只做一次部署（环境铁律）。本脚本只负责构建；部署仍走
  `python docker/run_stack.py up`。
- 不要在构建期间并发跑宿主机重活（批量测试 / 前端打包 / 全量迁移）。
- 不改业务代码：本卡只动 `docker/` 下的构建链路与脚本。

## 9. 演示前端部署（15173 / 16173）的三道护栏（INT-2012）

`docker/deploy_demo_frontends.ps1` 把 build 产物打进 nginx 镜像托管两个演示地址。2026-10-26 起
**15173 的产物来源唯一 = `wiring/react` 产品演示**（此前脚本默认指向 `design/ux-redesign` 的 dist，
按默认执行会把只有占位实现的设计稿刷上去，任务域导入导出等功能在演示上「消失」）。护栏：

1. **产物来源硬门禁**：React dist 必须命中产品标记 `连接你的 agent`，且不得命中占位串
   `导出流程见导出数据弹窗`；不满足直接拒绝（退出码非 0）。`-AllowAnyDist` 显式绕过，
   绕过时打醒目告警并记录 dist 路径与构建时间。
2. **部署锁** `docker/.deploy.lock`：已有部署在跑时第二个进程**立即失败**并打印持锁 PID / 开始时间，
   不排队不覆盖；持有进程已退出（如 run 被取消）的过期锁自动接管。
3. **部署后自检 + 自动回滚**：重建前给当前 `latest` 打 `rollback-<时间戳>` tag；起容器后自检
   `GET /` 200、容器 index.html 引用的 chunk 与 dist 一致、每个 chunk 文件在容器内存在、
   容器内 `static/js/async` 数量 == dist 内数量；任一失败自动回滚旧镜像（并把 `latest` 指回旧镜像）
   后退出非 0。

两侧产物**先都校验通过再一起部署**：任一边校验失败，两边都不动。演练自检失败路径用
`-FaultInject missing-chunk`（从构建上下文删一个 async chunk，预期自检失败 → 回滚 → 退出非 0）。

```powershell
# 常规发版（只刷 React 15173，用接线分支最新 dist）
pwsh -File deploy_demo_frontends.ps1 -SkipVue
# 故意传设计稿 dist：应被拒绝，容器与 latest tag 前后 ID 一致
pwsh -File deploy_demo_frontends.ps1 -SkipVue -ReactDist D:\00_code\V9.7.31-UX\Intelligent-Audio-TEST\frontend-react\dist
```

> 一次发版只做一次部署（环境铁律）：不要为了「再确认一下」重复执行；自检失败会自己回滚，
> 先查 dist 是不是缺文件，别手工连推。

### 9.1 上游网关 IP 漂移兜底（INT-2067）

`nginx-frontend.conf` 对 `api_gateway:5000` 的 `proxy_pass` 原本在 nginx **启动期解析一次并缓存
IP**。`api_gateway` 容器被 recreate（重刷 15000 栈 / 重建网关）后 IP 变化，演示双址仍连旧 IP →
15173/16173 全 `/api` 502（2026-10-27 日巡实证）。已改 Docker 内嵌 DNS 动态解析：

- `resolver 127.0.0.11 valid=30s ipv6=off;` + `set $api_gateway http://api_gateway:5000;`，
  四个反代 location（`/api/`、`/health`、`/socket.io/`、`/ws`）改用 `proxy_pass $api_gateway;`。
- 效果：网关重建后 nginx 每 30s 重解析一次，≤30s 自动恢复，不再依赖手工重启演示前端。
- 注意：该配置要随 `deploy_demo_frontends.ps1` 重新部署演示前端才生效（旧镜像仍是静态解析）；
  等不及自动恢复时，立即恢复手段仍是 `docker restart iat-react-frontend iat-uxvue-frontend`。
