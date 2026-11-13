# 沙箱测试：T1 可信脚本（INT-2455）+ T2 不可信代码（INT-2489）

方案依据：`doc/agent化/07_单Agent_Skills落地方案.md` §7（T2 另见 §6.5 第 5 步）。
被测代码：

- `agent_service/application/sandbox_runner.py` — 编排与判定（层级选择、路径、
  代码来源 hash、产物、结果映射）
- `agent_service/infrastructure/sandbox/docker_runner.py` — T1 一次性容器（加固
  参数、超时/输出上限、OOM 判定；容器执行循环与 T2 共用）
- `agent_service/infrastructure/sandbox/runner_service.py` — 独立 runner/sidecar
- `agent_service/infrastructure/sandbox/policy.py` — T2 硬限配置（yaml + env）
- `agent_service/infrastructure/sandbox/t2_runner.py` — T2 gVisor `runsc` 执行器、
  运行时探测（不可用即 `T2_RUNTIME_UNAVAILABLE`，**绝不**降级 T1）
- `agent_service/config/sandbox.yaml` — T2 默认硬限（部署只读挂载，INT-2456）

## 用例分组

| 文件 | 内容 | 需要 Docker | 需要 runsc |
|---|---|---|---|
| `test_sandbox_contract.py` | T1 加固参数、挂载边界、凭证拒收、路径穿越、失败不静默、产物校验、配置默认值 | 否 | 否 |
| `test_sandbox_spec_validation.py` | runner 侧规格白名单（root 写法 / `--privileged` / `../../bin/sh` / 限额放大）→ 400；容量解析与非 root 数值判定 | 否 | 否 |
| `test_sandbox_execution.py` | T1 真实容器：非 root/只读根/无 capability、断网、宿主文件不可见、无凭证、超时、CPU、内存、PID、输出超限、两次执行隔离、产物只回收 `/work` | 是 | 否 |
| `test_sandbox_runner_transport.py` | T1 runner/sidecar HTTP 通道与宿主 CLI 通道行为一致；无令牌拒绝启动；鉴权失败明确失败 | 是 | 否 |
| `test_sandbox_lifecycle.py` | 异常路径必删容器、容器 `timeout -k` 自限、孤儿容器回收（超龄回收 / 未超龄不误杀） | 是 | 否 |
| `test_t2_contract.py` | T2 加固参数逐条、运行时不可用与**不降级 T1**、代码来源/hash、出口白名单、输入/产物上限、阶段失败映射、产物写 `agent_artifact`、yaml/env 配置 | 否 | 否 |
| `test_t2_escape.py` | T2 逃逸（mount/unshare/ptrace/setuid/chroot/宿主文件）、联网、凭证、资源（时长/CPU/内存/PID/产物体积）、失败语义、无遗留容器、默认四阶段链 + 多模块包（`.pyc` 不算产物） | 是 | **是** |

## 运行

```bash
# T1 门禁（CI / M3 复用；镜像缺失时先 docker pull）
python scripts/sandbox_gate.py --pull
python scripts/sandbox_gate.py --json

# T2 门禁（需 Linux 宿主 + Docker 且已注册 gVisor runsc；无 runsc 时门禁失败）
python scripts/sandbox_gate.py --tier t2 --pull
python scripts/sandbox_gate.py --tier all --json

# 直接跑 pytest（T1 需 Docker Desktop 的 Linux 容器 + python:3.11-slim 镜像）
python -m pytest tests/agent_sandbox -q

# T2 手工执行（Windows 开发机 Docker Desktop 通常没有 runsc，用例会 skip 并给出本命令）
python -m pytest tests/agent_sandbox/test_t2_escape.py -q -rs
```

无 Docker / 缺镜像 / 缺 `runsc` 时 docker 用例会 skip 并给出原因与手工命令；
**门禁脚本把 skip 判为失败**，因此 CI 必须先具备 Docker、镜像与（T2）runsc。
Windows 开发机的 Docker Desktop 属于「非生产等价」环境：本机 `docker info` 若
没有 `runsc`，只能证明加固参数与失败语义（契约单测），不能证明 gVisor 内核隔离。

## T1 配置（环境变量）

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

## T2 配置（环境变量，覆盖 `agent_service/config/sandbox.yaml`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_SANDBOX_T2_RUNTIME` | `gvisor` | `gvisor` / `firecracker`（后者本期只报不可用） |
| `AGENT_SANDBOX_T2_RUNTIME_NAME` | `runsc` | docker `--runtime` 名；未注册即 `T2_RUNTIME_UNAVAILABLE` |
| `AGENT_SANDBOX_T2_RUNSC_BIN` | `runsc` | gVisor 二进制（部署侧安装，见 INT-2456） |
| `AGENT_SANDBOX_T2_IMAGE` | `python:3.11-slim` | T2 代码镜像（需带 Python；驱动测试需项目依赖时换自定义镜像） |
| `AGENT_SANDBOX_T2_MEMORY` / `_MEMORY_SWAP` | `512m` | 内存上限 |
| `AGENT_SANDBOX_T2_CPUS` | `1` | CPU 配额 |
| `AGENT_SANDBOX_T2_PIDS_LIMIT` | `128` | 进程数上限（fork 炸弹围栏） |
| `AGENT_SANDBOX_T2_TIMEOUT_SECONDS` | `120` | 单阶段超时（含编译/单测） |
| `AGENT_SANDBOX_T2_TOTAL_TIMEOUT_SECONDS` | `300` | 整份阶段计划总时长硬限 |
| `AGENT_SANDBOX_T2_OUTPUT_LIMIT_BYTES` | `1048576` | stdout+stderr 合计上限 |
| `AGENT_SANDBOX_T2_CONTAINER_USER` | `65534:65534` | 非 root（禁止 root，配置层拦截） |
| `AGENT_SANDBOX_T2_MAX_ARTIFACTS` | `32` | 产物数量上限 |
| `AGENT_SANDBOX_T2_MAX_ARTIFACT_BYTES` | `8388608` | 单产物大小上限 |
| `AGENT_SANDBOX_T2_MAX_TOTAL_ARTIFACT_BYTES` | `33554432` | 产物总量上限 |
| `AGENT_SANDBOX_T2_MAX_INPUT_FILES` / `_MAX_INPUT_FILE_BYTES` / `_MAX_INPUT_TOTAL_BYTES` | 200 / 1MB / 2MB | 输入代码包上限 |
| `AGENT_SANDBOX_T2_EGRESS_ENABLED` | `false` | 出口代理白名单总开关（默认完全禁网） |
| `AGENT_SANDBOX_T2_EGRESS_NETWORK` | `agent-sandbox-egress` | 必须是 internal 网络（只有代理可达） |
| `AGENT_SANDBOX_T2_EGRESS_PROXY_URL` | 空 | 出口代理地址（http/https） |
| `AGENT_SANDBOX_T2_EGRESS_ALLOWED_HOSTS` | 空 | 逗号分隔的主机白名单 |

## T2 结果口径

- `SUCCEEDED`：全部阶段退出码 0 且产物校验通过。
- 产物只收代码自己的输出：`.pyc` / `__pycache__` 是编译缓存（写在 `/tmp` 的
  tmpfs，不参与回收），不计入产物数量/体积；上限取上面的
  `AGENT_SANDBOX_T2_MAX_ARTIFACTS` / `_MAX_ARTIFACT_BYTES` /
  `_MAX_TOTAL_ARTIFACT_BYTES`（或 `sandbox.yaml` 的 `t2.artifact.*`），改配置即改判定。
- `BUDGET_EXCEEDED`：超时（`TIMEOUT`）、输出超限（`OUTPUT_LIMIT_EXCEEDED`）、
  内存超限（`MEMORY_LIMIT_EXCEEDED`）、被 SIGKILL（`RESOURCE_LIMIT_EXCEEDED`）、
  产物体积/数量超限（`ARTIFACT_TOO_LARGE` / `ARTIFACT_TOO_MANY`，T2 按「超资源」
  计；T1 仍按既有口径判 `FAILED`）。
- `FAILED`：阶段非零退出（`EXIT_CODE_NONZERO`，detail 带阶段名，编译/单测失败
  即此）、容器起不来（`CONTAINER_START_FAILED`）、产物非法（`ARTIFACT_INVALID`）、
  运行时缺失（`T2_RUNTIME_UNAVAILABLE`）、代码来源缺失/不一致
  （`CODE_PROVENANCE_MISSING` / `CODE_PROVENANCE_MISMATCH`）、请求非法
  （`INPUT_INVALID`）、非白名单联网（`EGRESS_DENIED`）。
- `SandboxResult.to_sandbox_event()` 输出 `sandbox_succeeded` / `sandbox_failed`
  事件载荷（含 reason、运行时、代码来源与 hash、逐阶段结果），由编排层落库
  （INT-2495 接线）。
- CPU 超额由 cgroup 节流（不会杀进程），最终由时长硬限终止 → `TIMEOUT`，与 T1
  口径一致。

## T2 API（供 INT-2467 driver_propose 消费）

```python
from agent_service.application.sandbox_runner import (
    T2Phase, T2SandboxRequest, default_validation_phases,
)
from agent_service.infrastructure.sandbox.policy import load_t2_policy
from agent_service.infrastructure.sandbox.t2_runner import build_t2_executor

policy = load_t2_policy()                 # yaml + AGENT_SANDBOX_T2_* 覆盖
# 生产默认 runner_http（agent_service 不碰 docker.sock，需 AGENT_SANDBOX_RUNNER_URL）；
# 宿主 runner / 开发机用 mode='host_cli'。
runner = SandboxRunner(untrusted_executor=build_t2_executor(policy),
                       t2_options=policy.to_runner_options())
result = runner.run_untrusted_code(T2SandboxRequest(
    code_source='driver_propose:DEVICE_DRIVER',   # 必填：来源标记
    files={'drivers/my_driver.py': source, ...},  # 代码内容副本（不挂宿主目录）
    phases=default_validation_phases(),           # 编译/单测/mock 契约/resolve
    code_sha256=expected_sha256,                  # 可选：与重算值不一致即拒绝
    run_id=run.id,                                # 可选：产物写 agent_artifact
))
result.outcome / result.reason / result.phases / result.artifacts
result.to_sandbox_event()
```

> 产物落 `agent_artifact` 需要同时注入 `artifact_repository`（`ArtifactRepository`）
> 与 `artifact_root`（产物内容落盘根目录，metadata 带 sha256 / 代码来源 / 代码
> hash / 阶段）；两者缺一时只回传 `result.artifacts`，不写库。

运行时不可用时 `result.reason == SandboxFailureReason.T2_RUNTIME_UNAVAILABLE`，
调用方不得把失败当成功，也不得自行回落 runc。

## T1 结果口径

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

T2 的 `T2DockerExecutor` 走同样的宿主/runner docker CLI 通道；生产要求宿主（或
runner 所在 Linux 容器）安装 gVisor 并把 `runsc` 注册为 docker runtime。
`agent_service` 侧默认用 `HttpRunnerT2Executor`（`build_t2_executor()` 按
`AGENT_SANDBOX_EXECUTOR_MODE=runner_http` 构造），只发 HTTP：

| 端点 | 用途 |
|---|---|
| `POST /v1/sandbox/t2/execute` | 执行一个 T2 阶段（一次性 gVisor 容器） |
| `GET /v1/sandbox/t2/runtime` | 运行时可用性；无 runsc 返回 `available=false` + `T2_RUNTIME_UNAVAILABLE` |
| `POST /v1/sandbox/execute` | T1（INT-2455 既有） |
| `GET /healthz` | 存活探针 |

T2 端点未装配时返回 503，客户端映射为 `T2_RUNTIME_UNAVAILABLE`——不存在回落到
runc/T1 的分支。

> HTTP 模式下 runner 与应用侧需共享输入/产物目录（同一卷，路径一致，与 T1 相同
> 约束）；部署挂载由 INT-2456 接线。代码来源 hash 由应用侧在写输入目录前重算，
> runner 只执行。


