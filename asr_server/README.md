# ASR Server

独立部署的 ASR（自动语音识别）HTTP 服务：**Silero VAD + SenseVoiceSmall**（段级时间戳）。

## 目录

| 文件 | 说明 |
|------|------|
| [asr_server.py](asr_server.py) | ASR HTTP 服务本体（Silero VAD 切段 + SenseVoice 出文本） |
| [asr_control.py](asr_control.py) | **启停 / 守护 / 状态 / 反向隧道 / 登录自启 统一入口**（推荐用这个） |
| [run_forever_asr.ps1](run_forever_asr.ps1) | 守护壳：子进程退出 5s 后重启（由 `asr_control.py` 拉起） |
| [ssh_tunnel_asr.ps1](ssh_tunnel_asr.ps1) | 反向隧道：本机 10095 → 服务器 `10.0.0.9:10095` |
| [autostart_asr.ps1](autostart_asr.ps1) | 登录自启入口（由 `IAT-ASR.vbs` 调用） |
| [asr_transcribe.py](asr_transcribe.py) | 阿里云百炼录音文件转写示例（云端方案，可选） |
| [qwen_omni_asr.py](qwen_omni_asr.py) | Qwen-Omni 云端 ASR 示例（可选） |
| [word_timestamps.py](word_timestamps.py) | 逐词时间戳工具 |

## 设计目标

- **独立部署**：运行在专用 ASR 主机上（纯 CPU 推理），避免 ASR 推理占用自动化测试主机的 CPU，从而保证时延测量的准确性
- **HTTP 调用**：测试主机通过 HTTP 上传 wav 文件获取识别结果，解耦推理与测试
- **结构化输出**：返回 `{text, chunks:[{text, timestamp:[start_s, end_s]}]}`，与 [asr_adapator.py](../eval_server/app/utils/asr_adapator.py) 的 `parse_result` 完全兼容
- **真实时间戳**：Silero VAD 出段级真实语音边界（不含标点造假时间戳），段级 chunks 也治了"标点单独成 chunk"的根因

## 架构

```
┌──────────────────────┐        HTTP (wav 上传)        ┌──────────────────────┐
│  自动化测试主机       │  POST /asr  (multipart)      │  ASR 主机             │
│  (eval_server)       │ ──────────────────────────▶  │  asr_server.py       │
│                      │                              │  Silero VAD 切段      │
│  asr_adapator.py     │ ◀──────────────────────────  │  + SenseVoice 出文本 │
│  call_modelscope_asr │  JSON {text, chunks}         │  (CPU 推理)           │
└──────────────────────┘                              └──────────────────────┘
```

## 部署

### 环境要求

- Python 3.10+（3.14 亦可，funasr/torch 需有对应 wheel）
- 纯 CPU 即可运行（无需 GPU）
- 首次启动需联网下载 SenseVoice（~900MB），之后读本地缓存

### 安装

```bash
pip install funasr torch fastapi uvicorn python-multipart soundfile librosa silero-vad
```

### 配置

复制 `.env.example` 为 `.env` 并按需修改：

```bash
cp .env.example .env
```

关键配置：
- `ASR_SENSEVOICE_MODEL=iic/SenseVoiceSmall`
- `ASR_SV_LANGUAGE=auto`（语言，可设 zh/en/ja/ko）
- `ASR_SILERO_MIN_SILENCE_MS=200`（静默阈值，打断检测建议 200；越小越细越碎）

### 启动

推荐用 `asr_control.py`（带守护、状态、隧道与日志）：

```bash
python asr_server/asr_control.py start --with-tunnel
```

前台调试时也可以直接跑：

```bash
python asr_server.py
```

启动时预加载模型（首次下载 SenseVoice ~900MB），随后监听 `0.0.0.0:10095`；
模型加载完成前 `/health` 的 `*_loaded` 仍为 `false`（分钟级，见「就绪判定」）。
启停 / 自启 / 排障见下文「启停、守护与自启」与「故障排查」。

> **代理注意**：ModelScope 为国内站点，代码已自动清除 `HTTP_PROXY` / `HTTPS_PROXY` 等代理环境变量，避免 SSL 握手失败。如仍遇到下载问题，请检查系统代理设置。

## 启停、守护与自启

统一入口 [asr_control.py](asr_control.py)，不需要手工 `taskkill` 或注册计划任务。

| 命令 | 作用 |
|------|------|
| `python asr_server/asr_control.py start [--with-tunnel] [--timeout 180]` | 启动守护 + 服务（可一并拉起隧道），等到端口可连 |
| `python asr_server/asr_control.py stop` | 落 stop 标记 → 杀监听进程 → 收守护；三步都做才保证不复活 |
| `python asr_server/asr_control.py restart --with-tunnel` | 先 stop 再 start |
| `python asr_server/asr_control.py status` | 查看解释器 / 端口 / 守护 / 隧道 / health |
| `python asr_server/asr_control.py logs` | 打开独立窗口实时 tail 服务 + 守护日志 |
| `python asr_server/asr_control.py tunnel-start` / `tunnel-stop` | 只操作反向隧道 |
| `python asr_server/asr_control.py install-autostart` / `uninstall-autostart` | 写入 / 移除登录自启 |

进程模型（各占一个可见终端窗口，窗口标题 `IAT ASR` / `IAT ASR Tunnel`）：

```
asr_control.py start --with-tunnel
  ├─ WMI 拉起 → powershell run_forever_asr.ps1   while($true)：子进程退出 5s 重启
  │                └─ python asr_server.py        与控制台同窗，日志直接刷在窗口里
  └─ WMI 拉起 → ssh_tunnel_asr.ps1                while($true)：断线 5s 重连
                   └─ ssh -N -v -R 10.0.0.9:10095:127.0.0.1:10095 ubuntu@106.54.49.79
```

两个窗口都不隐藏输出：守护的启停/重启记录和 uvicorn 的访问日志实时滚动；
隧道窗口带 `ssh -v`，握手与断线原因可直接看到。关掉窗口等于结束该进程
（守护被关则服务停止），要长期常驻就别关窗，或用 `logs` 另开一个 tail 窗口。

`status` 输出示例：

```
解释器   : C:\...\Python310\python.exe
入口     : E:\...\asr_server\asr_server.py (exists=True)
服务端口 : :10095 listening=True pid=16040
守护进程 : alive=True pid=15320
守护日志 : E:\...\asr_server\logs\asr.supervisor.log
反向隧道 : 运行中 pid=[17244]
健康检查 : {'status': 'ok', 'vad_loaded': True, 'asr_loaded': True, 'paraformer_loaded': True}
```

**解释器**：ASR 依赖 funasr/torch，`asr_control.py` 按
`ASR_PYTHON` 环境变量 → 仓库根 `.env` 的 `ASR_PYTHON` → 当前 Python 的顺序解析，
守护子进程也用它（不是运行 control 的那个解释器）。指错环境会每 5 秒重启一次。

**自启**：`install-autostart` 写
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\IAT-ASR.vbs`，登录时无窗口调起
`autostart_asr.ps1` → `asr_control.py start --with-tunnel`。只由登录触发、不注册计划任务，
所以 `stop` 之后不会被顶回来。

**反向隧道**：固定为 `-R 10.0.0.9:10095:127.0.0.1:10095 ubuntu@106.54.49.79`，依赖服务器
sshd 的 `GatewayPorts clientspecified` 与本机公钥免密。服务器侧自检：

```bash
curl -s http://10.0.0.9:10095/health
```

**日志**：

| 文件 | 内容 |
|------|------|
| `logs/asr_server.log` | 服务业务日志（含模型加载、请求），同时打到 `IAT ASR` 窗口 |
| `logs/asr.supervisor.log` | 守护启停与重启记录，同时打到 `IAT ASR` 窗口 |
| `logs/asr.supervisor.pid` / `logs/asr.supervisor.stop` | 守护 PID / 停止标记 |
| `logs/autostart_asr.log` | 登录自启执行记录 |

## 配置项

### ASR Server (asr_server.py)

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ASR_HOST` | `0.0.0.0` | 监听地址 |
| `ASR_PORT` | `10095` | 监听端口 |
| `ASR_CACHE_DIR` | `../static/asr_models` | 模型缓存目录（ModelScope 下载的模型存放在此） |
| `ASR_MODELSCOPE_MODEL` | `iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch` | 主 ASR 模型 |
| `ASR_VAD_MODEL` | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | VAD（语音活动检测）模型 |
| `ASR_PUNC_MODEL` | `iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch` | 标点恢复模型 |
| `ASR_THREAD_LIMIT` | `0` | 并发上限（同时在跑的 ASR 请求数）。`0` = 用 anyio 默认 40；>0 时改写线程池上限。见下「并发」 |

### 并发

服务**可以同时处理多个 ASR 请求**（同一进程、共享一份模型）。实现要点只有一条：
**阻塞式推理端点必须是同步 `def`，不能是 `async def`。**

`async def` 里直接调阻塞的同步函数（funasr 推理）会占死 uvicorn 的单事件循环，整个服务
一次只能处理一个请求——后续请求全部排队，客户端先撞读超时（`ASR_TIMEOUT`）或平台先撞
评估预算。FastAPI 对**同步 `def`** 端点会自动丢进 anyio 线程池并发执行；torch/funasr 在
C++ 计算期间释放 GIL，所以多路推理能真重叠。

**实测（本机 12 物理核 / 20 逻辑核，40.7s 的 wav，服务空闲）**

| N 并发 | 改前 墙钟 | 改前 各请求耗时 | 改后 墙钟 | 改后 各请求耗时 |
|--------|-----------|-----------------|-----------|-----------------|
| 1 | 0.90s | [1.12] | 0.98s | [1.08] |
| 2 | 1.83s | [1.83, 1.83] | 1.52s | [1.52, 1.53] |
| 4 | 3.84s | [1.02, 2.83, 2.84, 3.81] | 2.99s | [2.55, 2.70, 2.75, 2.99] |
| 8 | 7.95s | [1.0, 1.89, 3.8, 3.8, 4.76, 7.82, 7.84, 7.86] | 9.20s | [11.66 … 14.52] |

看**各请求耗时的形状**最直观：改前 N=4 是**阶梯状**（第 k 个请求 ≈ k × 单发才完成）——
这就是队头阻塞，长文件排在前面时后面全部饿死；改后 N=4 **齐平**（全部同时在跑，一起在
~3s 收尾）。

**整批规模实测**（138 个 wav / 8201s 音频，全量跑一遍 `/asr_word`）：

| 客户端并发 | 墙钟 | 吞吐 | `Σ单请求耗时 / 墙钟` | 单请求 P95 / 最大 |
|------------|------|------|----------------------|-------------------|
| 1（= 改前行为） | 155.4s | 52.8×RT | 1.00 | 5.04s / 12.6s |
| 2 | **106.1s** | **77.3×RT** | **2.00** | 6.75s / 16.3s |
| 4 | 113.0s | 72.6×RT | 4.00 | 15.2s / 30.5s |
| 8 | 139.8s | 58.7×RT | 7.67 | 37.5s / 103.6s |

`Σ单请求耗时 / 墙钟` = 2.00 意味着**真的有两个请求在同时跑**（1.00 才是串行）。

**调优建议：客户端并发取 2。** N=2 是墙钟最优（106s）且尾延迟最好；再往上收益被 CPU
吃满抵消，N=8 甚至比串行还慢——本机 20 逻辑核在 N=1 时 torch 就已用到 ~3.8 核，N=4 时
并行度到 12.2 核，单请求算力成本从 3.0 核·秒涨到 7.9 核·秒（线程超订）。**若还要继续
提速，下一根杠杆是限制 torch 的 intra-op 线程数**（`torch.set_num_threads`，让 N × 线程
≈ 物理核），本次未做——它会改变浮点归约顺序，属于「改计算」，需单独评审。

**内存代价**：并发**不额外加载模型**，只是每路多一份音频缓冲与中间张量。实测空闲 RSS
4.9GB，增量 N=1 +172MB / N=2 +310MB / N=4 +760MB / N=8 +1387MB（≈172MB/路）。
对比方案 `uvicorn.run(workers=N)`：每个 worker 各加载一份模型（单份 ≈4.9GB RSS），
N=2 就要 ~9.8GB——本机可用内存只剩 ~3.7GB，**该方案在本机不可行**，故选用线程池方案。

### 就绪判定与启动时间

启动时预加载全部模型（SenseVoice / Paraformer / Silero），**这是分钟级**，并发改造
**不影响启动时间**（实测 58s / 63.9s / 70.9s / 77.8s，波动来自机器负载而非改动）。

改后**如何验证就绪**——轮询 `/health`，三个 `*_loaded` 全为 `true` 才算就绪：

```bash
curl -s http://127.0.0.1:10095/health
# {"status":"ok", "vad_loaded":true, "asr_loaded":true, "paraformer_loaded":true,
#  "thread_limit":"anyio_default"}
```

`thread_limit` 回显实际生效的并发上限（未设 `ASR_THREAD_LIMIT` 时为 `"anyio_default"`）。

### 阿里云百炼云端转写 (asr_transcribe.py)

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DASHSCOPE_API_KEY` | （无） | 阿里云百炼 API Key（必填） |
| `DASHSCOPE_MODEL` | `fun-asr` | 转写模型 |
| `DASHSCOPE_LANGUAGES` | `zh,en` | 语言提示（逗号分隔） |
| `DASHSCOPE_BASE_URL` | （空） | 自定义 API 地址（可选，用于华北2等地域） |

## API 接口

### `GET /`

服务信息，列出所有可用端点。

**响应示例：**

```json
{
  "service": "ModelScope ASR Service",
  "model": "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
  "endpoints": {
    "health": "GET /health",
    "asr": "POST /asr (上传 wav 文件)",
    "asr_file": "POST /asr_file?wav_path=<本地路径>"
  }
}
```

---

### `GET /health`

健康检查。

**响应：**

```json
{
  "status": "ok",
  "engine": "sensevoice+silero + paraformer",
  "vad_loaded": true,
  "asr_loaded": true,
  "paraformer_loaded": true,
  "thread_limit": "anyio_default"
}
```

三个 `*_loaded` 为 `false` 表示对应模型尚未加载完成（启动预加载是分钟级，见下「就绪判定」）。
`thread_limit` 是实际生效的并发上限。

---

### `POST /asr`

上传 wav 文件，执行 ASR 推理并返回结构化结果。**远程调用的主接口。**

**请求：**

- Content-Type: `multipart/form-data`
- 表单字段 `file`：wav 文件

**响应示例：**

```json
{
  "text": "你好世界",
  "chunks": [
    {"text": "你", "timestamp": [0.10, 0.25]},
    {"text": "好", "timestamp": [0.25, 0.40]},
    {"text": "世", "timestamp": [0.40, 0.55]},
    {"text": "界", "timestamp": [0.55, 0.70]}
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 识别全文 |
| `chunks` | array | 逐字分片，含时间戳（单位：秒） |
| `chunks[].text` | string | 单字 |
| `chunks[].timestamp` | `[float, float]` | `[开始秒, 结束秒]` |

**错误码：**

| HTTP | 说明 |
|------|------|
| 400 | 非 wav 文件 |
| 500 | ASR 推理失败 |

---

### `POST /asr_file`

本机调用：传 wav 文件绝对路径返回 ASR 结果。仅限 ASR 主机本地测试使用。

**请求：**

```
POST /asr_file?wav_path=C:/xxx/audio.wav
```

**响应**：同 `POST /asr`。

## 调用方集成

测试主机（eval_server）通过 [asr_adapator.py](../eval_server/app/utils/asr_adapator.py) 调用本服务：

```python
from app.utils.asr_adapator import call_modelscope_asr, parse_result

raw = call_modelscope_asr("/path/to/audio.wav")
result = parse_result(raw)
# result = {"text": "...", "chunks": [{"text": "字", "timestamp": [start_s, end_s]}, ...]}
```

### 测试主机配置

在 `eval_server/.env` 中配置 ASR 服务地址：

```env
ASR_SERVER_URL=http://<ASR主机IP>:10095
ASR_TIMEOUT=120
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ASR_SERVER_URL` | `http://127.0.0.1:10095` | ASR 服务地址（改为实际 ASR 主机 IP） |
| `ASR_TIMEOUT` | `120` | 请求超时秒数 |

## 备选方案：阿里云百炼云端转写

[asr_transcribe.py](asr_transcribe.py) 提供基于阿里云百炼（DashScope）的录音文件转写方案，适用于不需要本地部署、希望使用云端算力的场景。

### 使用前提

- 在 `.env` 中配置 `DASHSCOPE_API_KEY`
- 音频文件需上传至可公网访问的 URL（如 OSS）

### 调用示例

```python
from asr_transcribe import transcribe

# 模型和语言从 .env 读取（DASHSCOPE_MODEL / DASHSCOPE_LANGUAGES），也可显式传入
transcribe(
    file_urls=['https://example.com/audio.wav'],
)
```

> 云端方案为异步转写，适合批量离线处理；本地 `asr_server.py` 为同步推理，适合实时性要求高的自动化测试场景。

## 故障排查

### 守护日志反复出现 `child exited rc= uptime=24s`

说明子进程启动即退出、守护在无限重启。traceback 直接看 `IAT ASR` 窗口，或 `logs/asr_server.log` 尾部。

**已修复的坑（2026-11-24）**：
- 用 `pythonw.exe` 启动时 `sys.stdout` / `sys.stderr` 为 `None`，uvicorn 在启动阶段抛
  `AttributeError` 并以 `rc=1` 静默退出；同一份代码用 `python.exe` 完全正常。现在
  `run_forever_asr.ps1` 检测到 `pythonw.exe` 会自动替换为同目录的 `python.exe`。
- funasr 的 Paraformer 初始化会 `GET https://pypi.org` 查版本且**不设超时**，网络不通时模型
  加载会永久挂住（CPU 不再增长、日志停在「加载 Paraformer 模型」）。现在 `asr_server.py`
  给 SenseVoice / Paraformer 都传了 `disable_update=True`。

### `start` 等到超时，但进程还活着

模型加载是分钟级（实测 58–78s，机器有负载时更久）。用
`curl -s http://127.0.0.1:10095/health` 轮询，三个 `*_loaded` 全为 `true` 才算就绪；
必要时加大 `--timeout 300`。若日志卡在「加载 Paraformer 模型」且 CPU 不动，见上一条的
`disable_update` 问题。

### 隧道起不来 / 起来就退出

`ssh -R` 开启 `ExitOnForwardFailure=yes`，远端绑定失败会立即退出（避免出现假隧道）。
常见原因：远端 `10.0.0.9:10095` 已被别的连接占用（上一次隧道没退干净）、sshd 未开启
`GatewayPorts clientspecified`、公钥免密失效。先手工 `ssh ubuntu@106.54.49.79` 验证连通性。

### 端口被占用

```powershell
netstat -ano | findstr :10095
```

不要直接 `taskkill`：先执行 `python asr_server/asr_control.py stop`，否则守护进程会立刻把它拉起来。
