# T1 沙箱测试（INT-2455）

方案依据：`doc/agent化/07_单Agent_Skills落地方案.md` §7。被测代码：

- `agent_service/application/sandbox_runner.py` — 编排与判定（层级、路径、产物、结果映射）
- `agent_service/infrastructure/sandbox/docker_runner.py` — 一次性 Docker 容器（加固参数、超时/输出上限、OOM 判定）
- `agent_service/infrastructure/sandbox/runner_service.py` — 独立 runner/sidecar（唯一持有 Docker 访问权）

## 用例分组

| 文件 | 内容 | 需要 Docker |
|---|---|---|
| `test_sandbox_contract.py` | 加固参数逐条断言、挂载边界、凭证拒收、路径穿越、失败不静默、产物校验、配置默认值 | 否 |
| `test_sandbox_spec_validation.py` | runner 侧规格白名单（root 写法 / `--privileged` / `../../bin/sh` / 限额放大）→ 400；容量解析与非 root 数值判定 | 否 |
| `test_sandbox_execution.py` | 真实容器：非 root/只读根/无 capability、断网、宿主文件不可见、无凭证、超时、CPU、内存、PID、输出超限、两次执行隔离、产物只回收 `/work` | 是 |
| `test_sandbox_runner_transport.py` | runner/sidecar HTTP 通道与宿主 CLI 通道行为一致；无令牌拒绝启动；鉴权失败明确失败 | 是 |
| `test_sandbox_lifecycle.py` | 异常路径必删容器、容器 `timeout -k` 自限、孤儿容器回收（超龄回收 / 未超龄不误杀） | 是 |

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
| `AGENT_SANDBOX_ALLOWED_IMAGES` | = `AGENT_SANDBOX_IMAGE` | runner 允许的镜像集合（逗号分隔）；payload 超出即 400 |
| `AGENT_SANDBOX_ALLOWED_INTERPRETERS` | = `AGENT_SANDBOX_INTERPRETER` | runner 允许的解释器集合 |
| `AGENT_SKILLS_ROOT` | `<项目根>/skills` | 允许只读挂进容器的 Skill 根目录；根外 `skill_root` 一律 400。缺省按 runner 自身位置本地计算（与 `Config.SKILLS_ROOT` 同源，不 import 业务配置）；给了相对路径等无法确定的值即配置错误，fail closed |
| `AGENT_SANDBOX_WORK_LIMIT_BYTES` | `33554432` | 运行中 `/work` 容量巡检上限，超限 terminate 并按资源超限收口 |
| `AGENT_SANDBOX_CONTAINER_KILL_GRACE_SECONDS` | `5` | 容器内 `timeout --kill-after` 宽限 |
| `AGENT_SANDBOX_ORPHAN_GRACE_SECONDS` | `30` | 孤儿容器回收阈值 = `timeout` + 本宽限 |
| `AGENT_SANDBOX_REAPER_INTERVAL_SECONDS` | `30` | 孤儿容器后台巡检间隔（runner 启动时另同步扫一次） |
| `AGENT_SANDBOX_RUNNER_RESPONSE_LIMIT_BYTES` | `8388608` | 客户端读取 runner 响应的上限 |

## 结果口径

- `SUCCEEDED`：容器退出码 0 且产物校验通过。
- `BUDGET_EXCEEDED`：超时（`TIMEOUT`，含容器内 `timeout` 自限退出码 124）、输出
  超限（`OUTPUT_LIMIT_EXCEEDED`）、内存超限（`MEMORY_LIMIT_EXCEEDED`）、被
  SIGKILL（`RESOURCE_LIMIT_EXCEEDED`）、运行中 `/work` 超容量。
- `FAILED`：非零退出、容器起不来（`CONTAINER_START_FAILED`）、runner 不可达、
  产物非法/超大小、请求非法（层级/路径/凭证/规格白名单）。失败一律带原因码，
  不静默成功。

## 容器生命周期（INT-2494）

三层防线，任何一层生效都不会留下在跑的容器：

1. 执行器 `Popen` 之后的整段包 `try/finally`，异常路径也 `docker rm -f`；`inspect`
   在 `rm` 之前取，超时 / 输出超限路径同样有 `container_id`。
2. 容器入口是 `timeout -k <grace> <timeout> <interpreter> ...`：runner 进程消失时
   容器到点自己退出（退出码 124，应用层判 `BUDGET_EXCEEDED/TIMEOUT`）。
3. runner 启动时同步扫一次 + 后台按 `agent-sandbox=t1` 标签定时回收创建时间超过
   `timeout + AGENT_SANDBOX_ORPHAN_GRACE_SECONDS` 的容器（日志带名 / id / 存活时长）。

> 未加 `--rm`：需要 `docker inspect` 取 `container_id` 与 `OOMKilled`。runner 崩溃
> 且不重启时容器会停在自己 `timeout` 到点（状态 `exited`），由下一次 runner 启动
> 的回收扫清。

## Docker 访问方式（红线）

`agent_service` 不得挂载 `/var/run/docker.sock`。两种合法通道：

1. `runner_http`（生产默认）：`agent_service` POST 容器规格到独立 runner/sidecar
   （compose 接线见 INT-2456），runner 才持有 Docker 访问权。
2. `host_cli`：宿主 runner / Windows 开发机直接调 docker CLI，仅在显式配置时启用。
