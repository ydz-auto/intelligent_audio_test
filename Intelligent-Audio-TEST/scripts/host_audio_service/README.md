# 宿主 audio_service 脚本（INT-2086 防楔死）

宿主侧 `audio_service` 固定跑在本机（依赖真实声卡），容器经
`host.docker.internal:50052` 访问它。

**启停统一走仓库根 `stack.py`，本目录不再提供 `.cmd` 启动器**：

```bat
:: 启动（Docker 栈 + 宿主机 device/audio）
python stack.py up

:: Windows 音频栈楔死时用影子 pyaudio（文件级功能可用，硬件放音不可用）
python stack.py up --no-docker --audio-mode shim

:: 只重启宿主服务
python stack.py restart host
python stack.py restart audio

:: 停止（优雅 Shutdown → 等端口释放 → 冷却）
python stack.py down

:: 看宿主服务日志
python stack.py logs audio -f
```

环境口径（DB/Redis/OSS/跨服务 gRPC 端口）由
`scripts/host_services/control.py` 从 `docker compose config` 解析后注入，
不再在本目录的各脚本里手抄——历史上 15432/15435/5432 三份口径漂移，导致
audio_service 连到测试库、音频列表“消失”。

## 文件清单

| 文件 | 作用 |
|---|---|
| `check_pyaudio_health.py` | 单次 `Pa_Initialize` 自检，带超时，失败即退不重试 |
| `run_audio_service_noshim.py` | noshim 入口（必须在影子目录之外，否则 import 命中影子 pyaudio） |
| `stop_audio_service.py` | 优雅停止（gRPC Shutdown → 回退 taskkill → 端口释放等待 → 冷却） |
| `README.md` | 本文件 |

## 注意

- 环境铁律：不许起本地全栈；audio_service 固定宿主机（gRPC 50052）。
- `taskkill /F` 只在优雅停止失败/旧代码不支持时使用，且会打印楔死风险警告；
  已楔死时需管理员重启 Audiosrv 或重启机器。
- 启动/停止由 `stack.py` 调用上述 Python 文件，不再需要 WMI 手工拉起。
