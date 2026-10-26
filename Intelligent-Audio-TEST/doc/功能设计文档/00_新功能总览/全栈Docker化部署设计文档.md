# 全栈 Docker 化部署设计文档（INT-272 / INT-333 审计回写 / INT-472 落地）

> **状态**：容器化部署落地（2026-10-16，INT-472：compose 全栈 up + 健康验证 + 四步冒烟 + 双栈过渡验证通过；落地缺陷修复见 §7）。
> **裁定来源**：成员裁定 2026-10-13/14，根治方案 C——全栈服务 Docker 化（INT-220 需求入口）；负责人 2026-10-16 拍板「新的测试服务容器化部署」——宿主直起切换到 docker compose 容器形态。
> **回写说明**：本章节由 INT-333 后向一致性审计于 2026-10-14 回写，基线为 `docker/docker-compose.yml` 实态（实现演进裁定，文档跟代码库走）；2026-10-16 由 INT-472 补充落地实施结果；2026-10-26 由 INT-1236 一致性审计补 §8（演示前端托管与传输优化，实现演进裁定）。
> **部署手册**（操作指南）：代码库 `docs/docker-compose.md`；本文为设计契约与运行纪律基线。

## 0. 容器化落地拍板与实施结果（2026-10-16，INT-472）

- **拍板**：负责人 2026-10-16：「新的测试服务容器化部署」——从宿主直起（run_all.py / parallel_stack.py python 进程）切换到 docker compose 容器形态。
- **实施结果**（本机实测）：
  - `python docker/run_stack.py up --build` 拉起全栈（infra postgres/redis/rustfs + db_bootstrap 一次性引导 + 11 后端 + 前端）；`docker ps` 全部 healthy。
  - 健康探测全绿：`python docker/run_stack.py health`（13+ 端点：10 HTTP /health + 前端 + 11 gRPC TCP + 3 infra）。
  - 四步冒烟通过：登录（RSA-OAEP）→ 建用例（dry 样例上传 + voice_llm 用例 + turn_eval 绑定）→ dry 执行（mock 适配器，执行/评估双 completed）→ 报告（generate-task 完成 + summary）；自建自清零残留。
  - 双栈过渡：落地时宿主旧栈 infra（5432/6379/9000）被其它 run 常驻，容器栈后端/前端保持标准端口（5000-5010/5173，当时空闲），infra 宿主端口用 `*_PORT` 覆盖改 scratch 段（POSTGRES_PORT=15432/REDIS_PORT=16379/RUSTFS_PORT=19000/RUSTFS_CONSOLE_PORT=19001）与宿主 infra 并存互不击穿；`*_PORT` 覆盖切换口径见 §5。
- **落地缺陷修复**（§7）：`.dockerignore` 排除 `frontend/` 导致 `Dockerfile.frontend` 构建失败 → 新增前端专用 ignore 文件；`PIP_INDEX_URL` 构建参数未接线（pip 走默认源）→ Dockerfile 阶段内补 ARG + `--index-url`；OSS presign 直传 URL 宿主为容器网络名 `rustfs` 宿主侧不可解析 → 冒烟脚本改写连接目标保留 Host 头（部署建议见 §7）。
- **测试栈口径**（§5 增补）：parallel_stack.py（测试 agent UI 隔离栈，端口 +1000）服务进程仍宿主形态，infra（postgres/redis/rustfs）复用容器栈——隔离测试库 `intelligent_audio_test_test` 需在容器 postgres 预建。

## 1. 背景与裁定

- **故障家族**：2026-10-10 起 7 起事故——agent run 退出收割带走其拉起的服务 / `run_all` 启动期清场击穿树外常驻栈（证据链见 INT-220 评论史）。
- **根治裁定（方案 C）**：全栈微服务 + 前端 + infra 纳入 Docker Compose 编排，服务生命周期与一切 agent run 树彻底解耦。不上 K8s/swarm（单机 compose 即可）；不改业务逻辑与对外接口行为（纯部署形态改造）。

## 2. 服务生命周期归 Docker daemon（架构口径）

- **唯一编排入口**：`docker/docker-compose.yml`（project `intelligent-audio-test`）；薄封装 `docker/run_stack.py`（`up/down/ps/logs/health/wait` 子命令，agent 运行时等价入口）。
- 容器 `restart: unless-stopped`，生命周期归 Docker daemon；`up` 一律分离模式（`-d`），run 树收割不带走任何服务。
- **验收判据**：故意结束曾拉起过服务的 agent run → 全部端点不受影响。

## 3. 编排拓扑（服务清单与契约）

### 3.1 infra（3）

| 服务 | 镜像缺省 | 端口 | 说明 |
|---|---|---|---|
| postgres | postgres:16-alpine | 5432 | 业务库，卷 `postgres_data` |
| redis | redis:7-alpine | 6379 | 纯运行时状态（Pub/Sub/注册/锁），禁 RDB/AOF |
| rustfs | rustfs/rustfs:latest | 9000 (S3) / 9001 (Console) | 对象存储，卷 `rustfs_data`；OSS 桶由各服务 `OSSClient._ensure_buckets_exist` 自建，无需引导 |

### 3.2 db_bootstrap（一次性引导 job）

- 链路（全脚本幂等）：`create_all_tables`（69 表）→ 幂等结构迁移（202608/202609/202610 结构 + 种子）→ RBAC 种子（96 权限点 + 5 角色）；数据回填/清洗类脚本不入链。
- 以 `service_completed_successfully` 门控全部业务服务启动——未引导完成的库不会被业务服务连接；已初始化库重复 up 幂等跳过。
- `AUTH_MODE=prod` 不种子 dev 引导用户（缺省弱口令管理员不得进入生产形态，INT-156 门控在 `fix_users_schema_drift.py` ④）。
- 迁移脚本经卷只读挂载（`../scripts:/opt/scripts:ro`）遮蔽镜像内同源副本；镜像内含脚本副本，卷缺席亦可引导。

### 3.3 后端微服务（12）——端口契约

**端口唯一注册表：`shared/config/service_ports.py`**（下表为快照口径）：

| 服务 | 宿主端口 | 容器端口 | 备注 |
|---|---|---|---|
| api_gateway | 5000 | 5000 | /health 带 version 标记 |
| task_service | 5001 / 51061 | 同左 | |
| e2e_test_service | 5002 / 50051 | 同左 | |
| api_test_service | **不发布** | 5003 / 51071 | UC-1001：容器网络内互访，多副本（`API_TEST_REPLICAS`，缺省 2）Docker DNS 轮询 |
| evaluation_service | 5004 / 51091 | 同左 | |
| report_service | 5006 / 51068 | 同左 | |
| algorithm_service | 5007 / 51067 | 同左 | |
| api_adapter_service | 5008 / 51081 | 同左 | 已删除的独立适配服务（INT-1176，能力内嵌 api_test_service） |
| auth_service | 5009 / 51069 | 同左 | |
| transfer_agent | 5010 / 51101 | 同左 | B 区实例按需 `TRANSFER_ZONE=B` 扩展 |
| audio_service | 50052 | 50052 | gRPC-only，TCP 探测 |
| device_service | 50053 | 50053 | gRPC-only，TCP 探测 |

- 51061-51101 为 Hyper-V/WSL 排除端口段规避后的现役注册值（整体 +1000 平移）。
- 宿主端口全部可经 `*_PORT` 环境变量覆盖（见 `docker/.env.compose.example`），缺省映射与宿主形态完全一致——下游用例不改即可跑通。
- 健康检查：HTTP 服务容器内 `urllib` 探 `/health`；gRPC-only 服务探 gRPC 端口 TCP；`stop_grace_period: 30s`（uvicorn/gRPC 响应 SIGTERM 优雅退出）。

### 3.4 frontend（1）

- 生产构建 + nginx（`Dockerfile.frontend`：node:20-alpine 构建 → nginx:alpine 托管 `dist/`），宿主 **5173 → 容器 80**。
- `VITE_AUTH_MODE` 构建期必填守卫（INT-181：缺失时 compose 直接报错，禁止静默默认 off）；`AUTH_MODE` 亦为 compose 强制校验项（`:?`），`prod` 形态 `run_stack.py` 拦截缺省 `JWT_SECRET`。
- nginx 反代契约与 vite dev 代理一致（`/api/`、`/socket.io/`、`/ws`、SSE 禁缓冲）；`client_max_body_size 2048m` 对齐网关 `DATA_TRANSFER_MAX_UPLOAD_MB` 缺省 2048（`shared/infrastructure/config.py`），消除容器形态 >1MB 导入 413 回归（INT-272 审计 P2-1）。

### 3.5 数据卷（5）

`service_logs`（INT-81 统一日志卷，读写侧同卷）/ `postgres_data` / `rustfs_data` / `static_storage`（audio_service 写、api_gateway 等读）/ `data_transfer_tmp`（INT-25 网关↔task_service 导入导出 ZIP 中转，双容器同卷）。

## 4. 运行纪律（成员裁定口径，2026-10-14）

1. **agent 运行时只做 `docker compose up/down` 与健康探测**（或等价 `python docker/run_stack.py ...`），**禁止宿主机直起进程**；
2. **禁止启动期整树清场**：`run_all.py` 的 `cleanup_occupied_ports` 已废除，改为 `_assert_ports_free` 只读检查（`run_all.py:524`）——任一目标端口被占用即列出占用方报错退出，处置权在执行者，绝不自动 kill；compose 启动遇端口占用同样报错退出交执行者处置（`run_stack.py` 不 kill 任何进程、不清理任何端口）；
3. **验收与开发 run 一律只连不拉**。

## 5. 双栈过渡与端口切换（过渡期口径）

- **并存形态**：宿主旧栈（标准端口 5000-5010 / 5173 / 50052-50053）与 compose 栈并存；第二套 compose 栈用 `*_PORT` 覆盖（scratch 段，如 15xxx）拉起，互不击穿。
- **切换窗口**：停宿主旧栈仅限负责人口令，切换时点待负责人裁定。
- **宿主形态边界**：`run_all.py` 宿主形态保留仅限本地调试（且不再清场）；生产/验收形态一律 compose。
- **测试栈口径（2026-10-16 INT-472 确认）**：测试 agent 的并行隔离栈（`tests/ui/utils/parallel_stack.py`，端口 +1000、隔离库 `intelligent_audio_test_test`）**服务进程仍宿主形态**——门禁（smoke_gate/run_gate/conftest）硬编码 +1000 网关与隔离库语义，转第二套 compose 栈需另做引导链与门禁常量改造；其 **infra 复用容器栈**（postgres 5432 / redis 6379 / rustfs 9000，隔离库与共享库同容器 postgres 分库共存）。隔离库在容器 postgres 需预建（`CREATE DATABASE intelligent_audio_test_test` + 建表/迁移链）。
- **容器形态例外**：device_service 物理设备链路——Linux 容器无宿主 USB 栈，容器内 adb/hdc 无法触达宿主实机；容器形态覆盖设备管理面全链路（CRUD/状态/告警），E2E 真机验收时该服务可保留宿主形态例外（成员保留裁定权）。
- **mock_services（INT-137/182）**：仅联调/验收用、默认关闭，不进生产编排与镜像。

### 5.1 多栈并行测试隔离（INT-597，docker 化；INT-993 按当前基线重交付）

- **背景与裁定**：INT-138 全流程实机走查被 INT-288 在跑 run 占用 6000 并行栈阻塞（共享隔离库 `intelligent_audio_test_test` 多 run 并发必踩踏），负责人 2026-10-17 拍板「咱们不是有docker嘛」→ 本小节落地 docker 化多栈并行测试隔离（服务域：docker/解阻）。
- **隔离形态**：`docker/run_stack_iso.py` 容器化隔离栈封装，每栈**独立 compose project** + **独立 postgres 数据卷**（docker volume 库隔离） + **独立端口段**（自动探测全空段） + 独立 redis / rustfs / 日志卷；`db_bootstrap` 自举（69 表 + 幂等迁移 + RBAC 种子 + dev 引导用户），base compose 以 `service_completed_successfully` 门控后端启动。
- **与 parallel_stack.py 的关系**：parallel_stack = 宿主进程 UI 栈（6000 段，SHIFT/隔离库写死，多 run 并发必踩踏），适用于单 run 独占 6000 段的浏览器实测；run_stack_iso = docker 容器化隔离栈，每栈一个独立库实例，适用于 API 级验收/冒烟与并发多栈。浏览器 UI 实测与真机 E2E 段仍走宿主栈（容器形态 device_service 无宿主 USB 栈）。
- **共享库隔离选择**：docker volume（独立库实例）——每栈 postgres 容器 + 项目级数据卷 = 完整独立库实例，比独立 schema 零侵入（schema 方案需改造全部 SQL/迁移）；`POSTGRES_DB=intelligent_audio_test_test` 覆盖后验收 gate 口径（`/health` database==隔离库名）原样满足，测试代码零改动；卷随 compose project 管理，`down` 保留卷复用、`down -v` 清库。
- **端口隔离落地**：base compose 全部宿主端口经 `*_PORT` 环境变量参数化（本小节补齐——此前 §5 并存形态的「第二套 compose 栈用 `*_PORT` 覆盖」仅有文档口径、compose 未接线），隔离栈自动探测 2000 起测跳过宿主 6000 段约定段，逐端口探测全空即起、被占即拒（INT-459 纪律：起栈前探测复用、测完必 stop）。
- **隔离栈专属增强**（`docker/docker-compose.iso.yml`）：rustfs 固定 `container_name` 跨栈冲突改名；`mock_eval_server_judge`（`docker/Dockerfile.mock_eval`）评估替身——外部算法服务 100.70.20.135:8888 不可达时，维度种子以 `EVAL_SERVER_URL` 指向本栈替身，报告链本栈内闭环。
- **用法**（仓库根 `Intelligent-Audio-TEST/`）：
  ```
  python docker/run_stack_iso.py up --name <project> [--auth-mode dev] [--offset N]
  python docker/run_stack_iso.py health --name <project>
  python docker/run_stack_iso.py smoke --name <project>      # 登录→用例→任务→报告 API 链
  python docker/run_stack_iso.py down --name <project>       # 测完必 stop（INT-459）
  ```
- **遗留风险**：docker 引擎宿主资源（Docker Desktop VM 内存 2GB 时多栈并发 OOM，2026-10-17 实测引擎自停）——已由环境侧调大 VM 内存缓解；多套栈并发前仍按需评估资源余量。

### 5.2 前端镜像构建修复（INT-597 顺手闭合）

- INT-597 原卡交付含 `docker/Dockerfile.frontend.dockerignore`（根 `.dockerignore` 排除 `frontend/` 导致 `Dockerfile.frontend` 从仓库根构建报 `"/frontend": not found`）。
- 当前基线该修复已随 INT-472 落地（见 §7.1），本小节仅归档 INT-597 归属，不重复实施。

## 6. 实现锚点

`docker/docker-compose.yml`（编排，`*_PORT`/`POSTGRES_DB` 参数化 + `db_bootstrap` 门控）· `docker/run_stack.py`（薄封装）· `docker/run_stack_iso.py` + `docker/docker-compose.iso.yml` + `docker/Dockerfile.mock_eval`（多栈并行测试隔离，§5.1）· `tools/iso_stack_smoke.py`（隔离栈验收冒烟）· `docker/Dockerfile.service`（12 后端统一镜像，单镜像多 CMD，含 ffmpeg/adb/portaudio）· `docker/Dockerfile.frontend` · `docker/Dockerfile.db_bootstrap` · `docker/db_bootstrap_entrypoint.py`（引导链）· `docker/nginx-frontend.conf`（反代契约 + gzip / 分级缓存，§8.2）· `docker/deploy_demo_frontends.ps1`（演示双址 15173 / 16173 幂等部署，§8.1）· `docker/.env.compose.example`（变量清单）· `run_all.py:524`（只读端口检查）· `shared/config/service_ports.py`（端口注册表）

## 7. 落地缺陷与修复（2026-10-16，INT-472 实测发现）

1. **`frontend/` 被根 `.dockerignore` 排除 → `Dockerfile.frontend` 构建失败**
   - 现象：`compose up --build` 在 frontend `COPY frontend/ ./` 报 `"/frontend": not found`。
   - 根因：2026-10-15 后端镜像瘦身把 `frontend/`、`tests/` 加进根 `.dockerignore`（后端 `COPY . .` 不需要），但 `Dockerfile.frontend` 依赖 `frontend/` 进构建上下文——同一忽略文件无法同时满足两种构建。
   - 修复：新增 `docker/Dockerfile.frontend.dockerignore`（前端专用忽略文件 = 根 .dockerignore 移除 `frontend/` 行，BuildKit 对命名 Dockerfile 取同目录 `<名>.dockerignore` 替代根忽略）；后端镜像瘦身不受影响。
2. **OSS presign 直传 URL 宿主侧不可解析**
   - 现象：容器内 `OSS_ENDPOINT=http://rustfs:9000`（容器网络名），presign 返回的直传 URL 宿主为 `rustfs`——宿主侧脚本/浏览器无法解析，前端直传链路在容器形态下断裂。
   - 处置（本次冒烟）：脚本把 presign URL 的 netloc 改写为发布端口
     `127.0.0.1:9000`，并保留原 `Host: rustfs:9000` 头（S3 SigV4 签名覆盖
     Host 头，改连接目标不改 Host 则签名仍有效）。
   - 部署建议（后续）：宿主 hosts 加 `127.0.0.1 rustfs`（浏览器/宿主直传可达发布端口），或引入「公网 OSS 端点」配置分离 service-to-service 与 client 直传两种 base URL。
   - 已实施（INT-1719，2026-10-24）：采用后者。新增 `OSS_PUBLIC_ENDPOINT`（对浏览器/第三方暴露的地址，空串回落 `OSS_ENDPOINT`），`OSSClient` 另建签名客户端，`get_presigned_url` / `get_upload_presigned_url` / `get_part_upload_presigned_url` 三个方法改用它签名；内部读写仍走 `OSS_ENDPOINT`。compose 给 api_gateway / task_service / report_service / api_test_service 加 `${OSS_PUBLIC_ENDPOINT:-http://127.0.0.1:9000}`。不采用「生成后替换 URL 前缀」：SigV4 下 Host 参与签名，换 host 会 403。`scripts/compose_stack_smoke.py` 的 netloc 改写仅在新旧容器混跑期仍需（presign 已是宿主地址时命中不到 `rustfs`，逻辑自然跳过）。
3. **测试栈 infra 复用容器栈后的隔离库预建**
   - compose postgres 占 5432 后，宿主 postgres 不再起（parallel_stack `_ensure_postgres` 探测 5432 已监听即跳过）；parallel_stack 服务连接 127.0.0.1:5432 的隔离库 `intelligent_audio_test_test` 需在容器 postgres 预建（CREATE DATABASE + 建表/迁移），见 §5。
4. **`PIP_INDEX_URL` 构建参数未接线**
   - compose 声明了 `PIP_INDEX_URL` build-arg（`.env.compose.example` 有模板注释），但 `Dockerfile.service` / `Dockerfile.db_bootstrap` 的 `pip install` 未消费它，且 FROM 前声明的 `ARG` 在构建阶段内不生效 → 镜像内 pip 固定走默认源（内网/镜像源加速失效）。
   - 修复：两 Dockerfile 在阶段内补 `ARG PIP_INDEX_URL` + `pip install --index-url "${PIP_INDEX_URL}"`；仓库根 .env 配 `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。
5. **requirements.txt 残留 `hypium` 阻断容器 pip 解析**
   - 2026-10-15 已拍板把 `hypium` 拆出主 requirements（`requirements-device.txt`，device_service 鸿蒙链路专属），但主 requirements.txt 未实际移除（line 63 仍在）——容器内全新 pip 解析触发 hypium→xdevice 依赖与主 requirements 的 `ResolutionImpossible` 冲突（宿主 env 无 hypium，代码懒加载兜底不受影响）。
   - 修复：主 requirements.txt 移除 `hypium>=6.0.0`（注释标明已拆至 requirements-device.txt），容器构建恢复。

## 8. 演示/走查前端托管与传输优化（INT-1236 一致性审计回写 / INT-1276 实施，2026-10-26）

> **实现演进裁定**：本节按 INT-1276 落地后的实态回写（此前文档只登记 `docker/nginx-frontend.conf` 为「反代契约」，未记演示双址的托管形态、压缩与缓存口径）。INT-1236（前端包体积与首屏测量卡）拆出的 E1~E4 里，E1 交付的就是本节内容。

### 8.1 托管形态（取代 dev server）

- **两个演示/走查地址**：React `:15173`、新 Vue `:16173`（容器 `iat-react-frontend` / `iat-uxvue-frontend`，`nginx:alpine`），**托管 build 产物**，不再是 `rsbuild dev` / `vite dev`（旧的 5273 / 5601 已停用）。
- 旧形态的病灶（INT-1236 实测）：React dev 首屏 3 个 JS 共 ≈32.6 MB 未压缩未 minify、无 `Content-Encoding`；新 Vue dev 在 400 ms RTT 下首屏 544 个请求（Vite dev 每模块一请求）。切 build 产物后同一口径下首屏请求数降到 30 / 26。
- **部署脚本**：`docker/deploy_demo_frontends.ps1`（幂等：重建镜像 + 重建容器，固定容器名 / 端口 / 网络）。默认产物目录为设计分支的 dist（React `D:\00_code\V9.7.31-UX\Intelligent-Audio-TEST\frontend-react\dist`、新 Vue `D:\00_code\V9.7.31-WIRING-UXVUE\Intelligent-Audio-TEST\frontend\dist`），可用 `-ReactDist` / `-VueDist` 指向别的产物目录，`-SkipReact` / `-SkipVue` 只刷一边。
- **纪律**：从 `docker/` 目录操作，一次只部署一次，不重复重启（同 §4.1 运行纪律）。

### 8.2 压缩与缓存分级（`docker/nginx-frontend.conf`）

- **压缩**：`gzip on` + `gzip_vary on` + `gzip_comp_level 6` + `gzip_min_length 1024`，类型含 `text/html text/css application/javascript application/json image/svg+xml font/ttf font/otf` 等。镜像内 nginx 无 brotli 模块，**只用 gzip**，不为 brotli 另装模块（没有就退回 gzip，不引额外依赖）。小于 1 KB 的响应不压（如新 Vue 的 641 字节 `index.html`）。
- **缓存分级**：
  - 带 hash 的构建产物 `/static/`（React）、`/assets/`（新 Vue）→ `Cache-Control: public, max-age=31536000, immutable`；
  - 入口 `index.html` → `no-cache, must-revalidate`（发版即生效，避免长缓存锁死旧壳）；
  - SPA 兜底 `location /` → `no-cache`。
- **接口 JSON 压缩只在网关侧做一次**：`api_gateway/app.py` 的 Starlette `GZipMiddleware(minimum_size=1024, compresslevel=6)`，最后添加（包在最外层），401 短接与异常响应同样带 `Content-Encoding`；`text/event-stream`（SSE）、`audio/*`、图片 / 字体在库的排除表里，不会被缓冲或二次压缩。前端 nginx 的 `/api/` 代理显式 `gzip_proxied off`，**不重复压**——`15000` 直连端口 nginx 覆盖不到，压缩归网关才能两条路径一致。
- **验收判据**（`curl -sI -H 'Accept-Encoding: gzip, br'`）：`/static/js/*`、`/static/css/*`、`/assets/*`、`/index.html`、`/api/v1/*` 均有 `Content-Encoding: gzip`；静态产物有 `immutable`，`index.html` 为 `no-cache`。
- **不属于本节的**：主 compose 的前端 `frontend` 服务（`Dockerfile.frontend`，宿主 5173）仍是旧 Vue 生产形态，与演示双址无关（旧 Vue 已废弃，§1.1）。

### 8.3 重发演示时的注意

- **产物必须来自当前 build**：用 `-ReactDist` / `-VueDist` 指向「线上容器里冻结的旧产物」重发，只换托管方式、不更新内容，结果是**演示仍展示旧包**（首屏请求数 / 压缩上去了，但包体优化、图表与字体改造看不到）。发版要指向设计 / 接线分支**最新 dist**。
- 演示地址与仓库分支是两条线：`design/ux-redesign`、`design/ux-vue` 的优化要经集成进 `wiring/react`、`wiring/ux-vue`（§4.6）后，重发演示才有意义。

