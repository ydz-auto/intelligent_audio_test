# Docker Compose 部署（INT-272）

全栈（3 infra + 12 后端微服务 + 前端）纳入 Docker Compose 编排。服务生命周期归
Docker daemon，与一切 agent run 树彻底解耦——run 退出收割不带走任何服务，
run_all 启动清场也不会击穿栈（清场模式已废除）。

> **落地状态**：2026-10-16（INT-472）容器化部署落地——本机实测 compose 全栈 up、
> 健康探测全绿、四步冒烟通过（登录→建用例→dry 执行→报告，自建自清零残留）。
> 落地缺陷修复见「已知边界」§1/§2。

## 快速开始

```bash
# 1. 环境变量（仓库根 .env 或 export；AUTH_MODE/VITE_AUTH_MODE 必填且一致）
#    完整清单见 docker/.env.compose.example
export AUTH_MODE=dev VITE_AUTH_MODE=dev

# 2. 拉起全栈（构建 + 分离模式启动；容器归 daemon 托管）
python docker/run_stack.py up --build

# 3. 健康探测（13+ 端点：10 个 HTTP /health + 前端 + 11 gRPC TCP + 3 infra）
python docker/run_stack.py health

# 4. 停止（保留数据卷）
python docker/run_stack.py down

# 危险：连数据卷一起删（清库），需 --yes
python docker/run_stack.py down -v --yes
```

首次 `up` 会先启动 postgres/redis/rustfs + `db_bootstrap` 一次性引导 job
（建表 69 张 → 幂等迁移 → RBAC 种子），引导完成（service_completed_successfully）
后业务服务才启动。已初始化的库重复 up 时引导幂等跳过，秒级完成。
`AUTH_MODE=prod` 时引导 job 不种子 dev 引导用户（缺省弱口令管理员禁止进入
生产形态，生产管理员由运维显式建号）；off/dev 形态行为不变。

## 端口映射（与宿主形态完全一致，下游用例不改）

端口唯一注册表：`shared/config/service_ports.py`。宿主缺省映射：

| 服务 | 宿主端口 | 容器端口 |
|---|---|---|
| api_gateway | 5000 | 5000 |
| task_service | 5001 / 51061 | 同左 |
| e2e_test_service | 5002 / 50051 | 同左 |
| api_test_service | **不发布**（UC-1001，容器网络内互访，多副本 DNS 轮询） | 5003 / 51071 |
| evaluation_service | 5004 / 51091 | 同左 |
| report_service | 5006 / 51068 | 同左 |
| algorithm_service | 5007 / 51067 | 同左 |
| api_adapter_service | 5008 / 51081 | 同左（INT-1176 已删除的独立适配服务） |
| auth_service | 5009 / 51069 | 同左 |
| transfer_agent | 5010 / 51101 | 同左 |
| audio_service (gRPC-only) | 50052 | 50052 |
| device_service (gRPC-only) | 50053 | 50053 |
| frontend (nginx) | **5173** | 80 |
| postgres | 5432 | 5432 |
| redis | 6379 | 6379 |
| rustfs | 9000 (S3) / 9001 (Console) | 同左 |

上表为快照口径，gRPC 端口以 `shared/config/service_ports.py` 为唯一注册表
（51061-51101 为 Hyper-V 排除段规避后的现役注册值）。宿主端口全部可用环境
变量覆盖（`*_PORT`，见 `.env.compose.example`）——切换窗口期与宿主旧栈并存
验证时，用端口覆盖拉第二套栈即可。

## 运行时纪律（成员裁定口径）

- agent 运行时只做 `docker compose up/down` 与健康探测（或等价的
  `python docker/run_stack.py ...`），**禁止宿主机直起进程**；
- **禁止启动期整树清场**：compose 启动遇宿主端口被占用一律报错退出，
  交执行者处置，绝不自动 kill；`run_all.py` 的 `cleanup_occupied_ports`
  已废除（改为 `_assert_ports_free` 只读检查，遇占用报错退出）；
- 验收与开发 run 一律**只连不拉**。

## 镜像

- `docker/Dockerfile.service`：12 个后端微服务统一镜像（单镜像多 CMD），
  含 ffmpeg + adb + portaudio 构建依赖；shared 以源码随镜像打包。
- `docker/Dockerfile.db_bootstrap`：一次性引导 job 镜像（同 requirements）。
- `docker/Dockerfile.frontend`：前端生产构建（VITE_AUTH_MODE 必须显式注入，
  INT-181 构建期守卫）+ nginx 反代（/api、/socket.io、/ws 契约与 vite dev 一致）。

镜像/网络加速：`PY_IMAGE` / `NODE_IMAGE` / `POSTGRES_IMAGE` / `REDIS_IMAGE` /
`RUSTFS_IMAGE` / `PIP_INDEX_URL` 环境变量按需覆盖。

## 数据持久化（volumes）

- `postgres_data`：业务库；`rustfs_data`：对象存储；`service_logs`：服务运行/
  业务日志（INT-81 统一卷）；`static_storage`：音频/静态资源；
  `data_transfer_tmp`：网关↔task_service 导入导出 ZIP 中转（INT-25，两容器同卷）。

## 已知边界

- **frontend 构建需前端专用 dockerignore（2026-10-16 修复）**：根 `.dockerignore`
  为后端镜像瘦身排除 `frontend/`（后端 `COPY . .` 不需要），但 `Dockerfile.frontend`
  依赖 `frontend/` 进构建上下文。已新增 `docker/Dockerfile.frontend.dockerignore`
  （= 根忽略移除 `frontend/` 行，BuildKit 对命名 Dockerfile 取同目录
  `<名>.dockerignore` 替代根忽略）——前端构建恢复，后端镜像瘦身不受影响。
- **OSS presign 直传 URL 宿主侧需可达 `rustfs`**：容器内 `OSS_ENDPOINT=http://rustfs:9000`，
  presign 直传 URL 宿主为容器网络名 `rustfs`，宿主侧脚本/浏览器无法解析。冒烟脚本
  把 netloc 改写为 `127.0.0.1:9000` 并保留原 `Host: rustfs:9000` 头（S3 SigV4 签名
  覆盖 Host 头，改连接目标不改 Host 则签名仍有效）。部署建议：宿主 hosts 加
  `127.0.0.1 rustfs`（需管理员），或引入「公网 OSS 端点」配置分离两种 base URL。
- **测试栈 infra 复用容器栈后的隔离库预建**：compose postgres 占 5432 后宿主
  postgres 不再起（parallel_stack `_ensure_postgres` 探测到 5432 已监听即跳过）；
  并行隔离栈（服务仍宿主形态，端口 +1000）连接 127.0.0.1:5432 的隔离库
  `intelligent_audio_test_test`，需在容器 postgres 预建：
  `docker compose exec -T postgres psql -U intelligent_audio_test -d intelligent_audio_test -c "CREATE DATABASE intelligent_audio_test_test"`，
  再按 scripts/migrations/README.md 引导链对其建表/迁移。
- **device_service 物理设备链路**：容器内 adb/hdc 无法触达宿主 USB 实机
  （Linux 容器无宿主 USB 栈）。容器形态覆盖设备管理面全链路（CRUD/状态/
  告警）；E2E 物理链（真机放音/采集）验收时该服务可保留宿主形态例外
  （INT-272 卡面已论证，成员保留裁定权）。
  - **2026-10-23 实测（Windows + Docker Desktop/WSL2）**：usbipd-win
    5.3.0 经 `bind --force` + `attach --wsl` 已打通「宿主 USB → WSL2 VM →
    Docker 容器」链路，容器内可见 `/dev/bus/usb` 设备节点（一次性容器
    `--device /dev/bus/usb:/dev/bus/usb` 验证通过）。仍有两个缺口：
    ① 运行栈必须以 `devices: /dev/bus/usb:/dev/bus/usb` 启动（主 compose
    已带，run 隔离 override 栈缺此映射）；② 统一镜像仅装 adb、缺 hdc
    二进制（`Dockerfile.service` 运行阶段只装 adb），鸿蒙链路
    （harmony_driver 调 `hdc`）容器内不可用——需补 Linux 版 hdc 进
    device_service 镜像，或鸿蒙真机链路保留宿主形态。
- **mock_services**（INT-137/182）：仅联调/验收用、默认关闭，不进生产编排。
  需要时宿主形态直起（脚本自带 CLI，独立可运行）或按需补 profile。
- **audio_service 物理放音链路**（2026-10-23 补记，此前文档盲区）：
  PyAudio/PortAudio 驱动需真实声卡（RME Fireface 802/UCX II 等专业 USB
  声卡）+ Windows COM/WASAPI（`audio_driver.py` 调 `ctypes.windll.ole32.
  CoInitializeEx`）。WSL2 VM 无音频栈（`/dev/snd` 为空，usbipd 无法转发
  音频类设备），容器内 PyAudio 拿不到宿主声卡——仅能起降级形态（混音/
  渲染链可用，物理放音不可用，CI 由 `tests/fixtures/pyaudio_shim` 兜底）。
  与 device_service 同理，物理放音验收时该服务保留宿主形态例外；容器化
  需 Linux 宿主 + ALSA/PulseAudio 直通才成立。
- **混合部署形态（2026-10-23 全仓排查）**：物理世界依赖只有两个——
  device_service（adb/hdc/USB/串口/hypium）与 audio_service（声卡/
  WASAPI）必须宿主；其余业务服务（api_gateway/task/evaluation/report/
  algorithm/auth/api_test/frontend）与基础设施（postgres/redis/rustfs）
  全容器化已闭环。e2e_test_service 零硬件调用（设备操作 gRPC 委托
  device_service），纯容器可跑，真机 E2E 时经 `DEVICE_SERVICE_HOST`/
  `AUDIO_SERVICE_HOST` 指向宿主实例（host.docker.internal）；compose 里
  给 e2e 挂 `/dev/bus/usb` 属冗余防御。transfer_agent 未纳入 compose
  编排（B 区实例需跨区网络部署），属编排缺口而非技术不可行。mock
  四件套（mock_dut/mock_realtime/mock_eval/mock_third_party_eval）本就是
  真硬件替身，iso 栈已示范容器化。
- `run_all.py` 宿主形态仍可用（本地调试），但启动期不再清场；生产/验收形态
  一律 compose。
