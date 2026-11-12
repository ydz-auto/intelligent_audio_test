# T1 沙箱测试（INT-2455）

方案依据：`doc/agent化/07_单Agent_Skills落地方案.md` §7。被测代码：

- `agent_service/application/sandbox_runner.py` — 编排与判定（层级、路径、产物、结果映射）
- `agent_service/infrastructure/sandbox/docker_runner.py` — 一次性 Docker 容器（加固参数、超时/输出上限、OOM 判定）
- `agent_service/infrastructure/sandbox/runner_service.py` — 独立 runner/sidecar（唯一持有 Docker 访问权）

## 用例分组

| 文件 | 内容 | 需要 Docker |
|---|---|---|
| `test_sandbox_contract.py` | 加固参数逐条断言、挂载边界、凭证拒收、路径穿越、失败不静默、产物校验、配置默认值 | 否 |
| `test_sandbox_execution.py` | 真实容器：非 root/只读根/无 capability、断网、宿主文件不可见、无凭证、超时、CPU、内存、PID、输出超限、两次执行隔离、产物只回收 `/work` | 是 |
| `test_sandbox_runner_transport.py` | runner/sidecar HTTP 通道与宿主 CLI 通道行为一致；无令牌拒绝启动；鉴权失败明确失败 | 是 |

## 运行

```bash
# 门禁（CI / M3 复用；镜像缺失时先 docker pull）
python scripts/sandbox_gate.py --pull
python scripts/sandbox_gate.py --json

# 直接跑 pytest（需 Docker Desktop 的 Linux 容器 + python:3.11-slim 镜像）
python -m pytest tests/agent_sandbox -q
```

无 Docker / 缺镜像时 docker 用例会 skip 并给出原因；**门禁脚本把 skip 判为失败**，
因此 CI 必须先具备 Docker 与镜像（预拉取或 `--pull`）。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_SANDBOX_IMAGE` | `python:3.11-slim` | T1 脚本镜像（Linux 容器） |
| `AGENT_SANDBOX_EXECUTOR_MODE` | `runner_http` | `runner_http`（生产，无 Docker socket）/ `host_cli`（开发机 / runner 内部） |
| `AGENT_SANDBOX_RUNNER_URL` | 空 | runner/sidecar 地址；未配置时 `runner_http` 直接失败（fail closed） |
| `AGENT_SANDBOX_RUNNER_TOKEN` | 空 | runner 共享令牌；runner 未配置令牌时拒绝启动 |
| `AGENT_SANDBOX_MEMORY` / `_MEMORY_SWAP` | `512m` | 内存上限 |
| `AGENT_SANDBOX_CPUS` | `1` | CPU 配额 |
| `AGENT_SANDBOX_PIDS_LIMIT` | `128` | 进程数上限（fork 炸弹围栏） |
| `AGENT_SANDBOX_TMPFS_SIZE` | `64m` | `/tmp` tmpfs 大小 |
| `AGENT_SANDBOX_TIMEOUT_SECONDS` | `60` | 单次执行超时 |
| `AGENT_SANDBOX_OUTPUT_LIMIT_BYTES` | `1048576` | stdout+stderr 合计上限，超限即杀容器 |
| `AGENT_SANDBOX_CONTAINER_USER` | `65534:65534` | 容器内非 root 用户（禁止 root，配置层拦截） |
| `AGENT_SANDBOX_MAX_ARTIFACTS` | `32` | 产物数量上限 |
| `AGENT_SANDBOX_MAX_ARTIFACT_BYTES` | `8388608` | 单产物大小上限 |
| `AGENT_SANDBOX_MAX_TOTAL_ARTIFACT_BYTES` | `33554432` | 产物总量上限 |

## 结果口径

- `SUCCEEDED`：容器退出码 0 且产物校验通过。
- `BUDGET_EXCEEDED`：超时（`TIMEOUT`）、输出超限（`OUTPUT_LIMIT_EXCEEDED`）、
  内存超限（`MEMORY_LIMIT_EXCEEDED`）、被 SIGKILL（`RESOURCE_LIMIT_EXCEEDED`）。
- `FAILED`：非零退出、容器起不来（`CONTAINER_START_FAILED`）、runner 不可达、
  产物非法/超大小、请求非法（层级/路径/凭证）。失败一律带原因码，不静默成功。

## Docker 访问方式（红线）

`agent_service` 不得挂载 `/var/run/docker.sock`。两种合法通道：

1. `runner_http`（生产默认）：`agent_service` POST 容器规格到独立 runner/sidecar
   （compose 接线见 INT-2456），runner 才持有 Docker 访问权。
2. `host_cli`：宿主 runner / Windows 开发机直接调 docker CLI，仅在显式配置时启用。
