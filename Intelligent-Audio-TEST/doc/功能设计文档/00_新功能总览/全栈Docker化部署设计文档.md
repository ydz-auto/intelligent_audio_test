# 全栈 Docker 化部署设计文档（INT-272 / INT-333 审计回写）

> **状态**：已实施并验收（INT-272 done 2026-10-14；24/24 端点实测全绿）。
> **裁定来源**：成员裁定 2026-10-13/14，根治方案 C——全栈服务 Docker 化（INT-220 需求入口）。
> **回写说明**：本章节由 INT-333 后向一致性审计于 2026-10-14 回写，基线为 `docker/docker-compose.yml` 实态（实现演进裁定，文档跟代码库走）。
> **部署手册**（操作指南）：代码库 `docs/docker-compose.md`；本文为设计契约与运行纪律基线。

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
| api_adapter_service | 5008 / 51081 | 同左 | |
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
- **容器形态例外**：device_service 物理设备链路——Linux 容器无宿主 USB 栈，容器内 adb/hdc 无法触达宿主实机；容器形态覆盖设备管理面全链路（CRUD/状态/告警），E2E 真机验收时该服务可保留宿主形态例外（成员保留裁定权）。
- **mock_services（INT-137/182）**：仅联调/验收用、默认关闭，不进生产编排与镜像。

## 6. 实现锚点

`docker/docker-compose.yml`（编排）· `docker/run_stack.py`（薄封装）· `docker/Dockerfile.service`（12 后端统一镜像，单镜像多 CMD，含 ffmpeg/adb/portaudio）· `docker/Dockerfile.frontend` · `docker/Dockerfile.db_bootstrap` · `docker/db_bootstrap_entrypoint.py`（引导链）· `docker/nginx-frontend.conf`（反代契约）· `docker/.env.compose.example`（变量清单）· `run_all.py:524`（只读端口检查）· `shared/config/service_ports.py`（端口注册表）
