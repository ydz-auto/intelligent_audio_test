# 宿主 audio_service 启动/停止脚本族（INT-2086 防楔死）

本目录是**仓库内规范版本**；宿主运行副本在 `D:\00_env\host_audio_service\`（部署/运维以宿主副本为准，改动须同步两处）。两者内容一致。

## 背景与三防（负责人 2026-10-27 拍板）

Windows 音频栈楔死触发机制（INT-2073 实测证据链）：强停（`taskkill /F`）带流的 noshim `audio_service` 后，旧进程 WASAPI 会话锁在声卡驱动里未释放；立刻跑下一个 `Pa_Initialize` 撞锁挂死；每次重试的挂死进程又排队在同一个全局音频锁上，越重启越死（实测遗留 5 个卡驱动 python 进程）。

三条防复发措施：

1. **冷却间隔**：kill 旧服务与下一次 `Pa_Initialize` 之间强制间隔——先等 TCP 50052 完全释放，再额外冷却 5~10s（默认 8s）。
2. **挂死禁连试**：`Pa_Initialize` 超时（默认 60s）**一次即失败退出**，不自动重试；失败日志含「重启 Audiosrv / 重启机器」指引。
3. **优雅停止通道**：服务端新增 gRPC `AudioService.Shutdown` RPC（停全部播放 → 等流关闭 → `pa.terminate()` → 停 server → 进程退出）；停止脚本优先调它，`taskkill /F` 只作最后手段并标注风险。

## 文件清单

| 文件 | 作用 |
|---|---|
| `start_audio_service_noshim.cmd` | 无影子 pyaudio 启动（真实放音）；先跑超时自检，失败即退不重试 |
| `start_audio_service.cmd` | 影子 pyaudio 启动（INT-95，文件级功能可用，硬件放音不可用） |
| `start_audio_service_shim_fallback.cmd` | 影子启动、日志换文件（旧日志被残留进程锁住时的绕行） |
| `stop_audio_service.cmd` | **新**：优雅停止 + 等端口释放 + 冷却 |
| `check_pyaudio_health.py` | **新**：单次 Pa_Initialize 自检，带超时，禁连试 |
| `stop_audio_service.py` | **新**：停止逻辑（gRPC Shutdown → 回退 taskkill → 端口释放等待 → 冷却） |
| `run_audio_service_noshim.py` | noshim 入口（必须在影子目录之外，否则 import 命中影子 pyaudio） |
| `README.md` | 本文件 |

## 日常用法

```bat
:: 启动（真实放音，需先确认 Audiosrv RUNNING）
start_audio_service_noshim.cmd

:: 停止（优雅停止 + 冷却，之后才能安全重启）
stop_audio_service.cmd

:: 失败路径验证（把超时调到 1s 触发，日志应含恢复指引且进程退出）
set AUDIO_CHECK_TIMEOUT=1
start_audio_service_noshim.cmd
```

## 服务端优雅停止（代码侧）

- proto：`shared/proto/audio_service.proto` 的 `AudioService` 新增 `Shutdown(ShutdownRequest) returns (ShutdownResponse)`。
- 实现：`audio_service/interfaces/grpc/servicers.py::AudioServiceServicer.Shutdown` → `server.py::initiate_graceful_shutdown()` → `audio_service.shutdown()`（`audio_engine.py`，停播放/等流/`pa.terminate()`）→ `server.stop(grace)` → `__main__` 的 `wait_for_termination()` 返回，进程自然退出。
  - 注意（INT-2086 审计 P1）：生产启动走 `runpy.run_module(..., run_name='__main__')`，`server.py` 只登记为 `__main__`，servicer 惰性按真实模块名 import 会拿到第二份拷贝（模块全局 `_server=None`）。因此 `start_grpc_server` 把 server 引用挂到 `AudioServiceServicer._grpc_server` 实例属性上，`Shutdown` 经实例引用停服，不依赖模块全局。
- Ctrl+C 同样走优雅停止（`server.py` `__main__`）。

## 注意

- 环境铁律：不许起本地栈；audio_service 固定宿主机（gRPC 50052），docker 经 `host.docker.internal:50052` 访问。
- `taskkill /F` 只在优雅停止失败/旧代码不支持时使用，且会打印楔死风险警告；已楔死时需管理员重启 Audiosrv 或重启机器。
- 部署通道：WMI `Win32_Process.Create` 让服务存活过 run；git 提交在 V9.7.31 主分支。
