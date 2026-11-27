# 宿主 audio_agent 脚本（INT-2086 防楔死）

audio 拆分后宿主侧固定跑**硬件面** `audio_agent`（`AUDIO_ROLE=agent`，gRPC 50052，
依赖真实声卡）；数据面（音频库 CRUD/元数据/历史）是 compose 里的 `audio_service`
容器（容器内 50052，开发栈宿主发布 50054）。容器内服务访问硬件面走
`host.docker.internal:50052`，访问数据面走 `audio_service:50052`。

**启停统一走仓库根 `stack.py`，本目录不再提供 `.cmd` 启动器**：

```bat
:: 启动（Docker 栈 + 宿主机 device/audio_agent）
python stack.py up

:: Windows 音频栈楔死时用影子 pyaudio（文件级功能可用，硬件放音不可用）
python stack.py up --no-docker --audio-mode shim

:: 只重启宿主服务
python stack.py restart host
python stack.py restart audio

:: 停止（优雅 Shutdown → 等端口释放 → 冷却）
python stack.py down

:: 看宿主服务日志（audio_agent.log / audio_agent_shim.log）
python stack.py logs audio -f
```

环境口径（e2e/device 的 DB/Redis；audio_agent 的数据面地址与下载网关）由
`scripts/host_services/control.py` 从 `docker compose config` 与
`logs/host_services/remote.env` 解析后注入。启动 audio 时会裁掉
`DATABASE_URL`/`POSTGRES_*`/`OSS_*`：agent 不连库也不直连对象存储，元数据与
播放历史走数据面 gRPC（`ResolveAudioByName` / `RecordPlaybackHistory`），音频
字节经 `STORAGE_SERVER_FETCH_URL` 网关下载并落本地缓存。

## 文件清单

| 文件 | 作用 |
|---|---|
| `check_pyaudio_health.py` | 单次 `Pa_Initialize` 自检，带超时，失败即退不重试 |
| `run_audio_service_noshim.py` | noshim 入口（必须在影子目录之外，否则 import 命中影子 pyaudio） |
| `stop_audio_service.py` | 优雅停止（gRPC Shutdown → 回退 taskkill → 端口释放等待 → 冷却） |
| `README.md` | 本文件 |

## 注意

- 环境铁律：不许起本地全栈；宿主只跑硬件面 `audio_agent`（gRPC 50052），
  数据面由 compose 的 `audio_service` 容器承担。
- agent 日志里不应出现数据库/OSS 连接：出现即说明 `AUDIO_ROLE` 或 env 裁剪失效。
- `taskkill /F` 只在优雅停止失败/旧代码不支持时使用，且会打印楔死风险警告；
  已楔死时需管理员重启 Audiosrv 或重启机器。
- 启动/停止由 `stack.py` 调用上述 Python 文件，不再需要 WMI 手工拉起。
