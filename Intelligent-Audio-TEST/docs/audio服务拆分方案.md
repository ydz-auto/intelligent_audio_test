# audio 服务拆分方案（本地 audio_agent + 服务器 audio_service）

> 状态：方案评审稿，不改代码
> 日期：2026-11-25

## 0. 结论

按「**碰不碰声卡 / 是不是播放时序敏感**」切，而不是按音频业务模块切：

| 部署单元 | 位置 | 定位 | 包含 | 副本数 |
|---|---|---|---|---|
| `audio_service` | 服务器容器 | 数据面 | `AudioConfigService`（去除试听） | N（随页面 QPS + 转码队列） |
| `api_test_service` | 服务器容器 | API 执行 + API 混音 | 执行器 + 进程内混音模块（原 `RenderService`） | N（随用例并发） |
| `audio_agent` | 执行机宿主 | 硬件面 | `AudioService` + `PlaybackService` + `PreviewAudio/StopPreviewAudio`（E2E 试听） | 每台执行机 1 个 |

> `RenderService` **不单独部署，也不留在 `audio_service`**：它全仓只有一个消费方 `api_test_service`（`api_executor.py`、`realtime_session_executor.py`、`api_session_executor.py` 均经 `RoundRenderService` 调用），按「单一消费者的纯计算能力」降到进程内模块。混音代码抽成共享模块，`audio_agent` 的 E2E 混音复用同一套底层原语，避免两份实现。

两条硬约束：

1. **API 混音跟 API，E2E 混音跟 E2E**：`RenderService` 只被 `api_test_service` 调用，合并进 `api_test_service` 进程；E2E 的混音是播放编排里的实时多设备叠加（`audio_engine` 播放链路），不是 `RenderService`，跟着 E2E 留在本地 agent。
2. **音频流量全走服务器**：执行机不再拿 COS 预签名 URL，统一经网关 `/api/v1/audios/download` 取流，并落本地**预存储**缓存；执行机不持有 DB / COS 凭据。

---

## 1. 现状

一个宿主进程注册了 4 个 gRPC 服务（`audio_service/interfaces/grpc/server.py:139-144`）：

| 服务 | 实际职责 | 依赖 |
|---|---|---|
| `AudioService` | 播放/停止、播放状态、音频信息、物理设备、SPL、`PrepareAudios` | 声卡 + audio 表 + 对象存储 |
| `PlaybackService` | 轮次编排、重叠播放、背景噪声、声纹 | 声卡 + audio/设备表 + Redis 播放锁 + 对象存储 |
| `AudioConfigService` | 音频库 CRUD、上传、转码、分析、流地址，**以及 `PreviewAudio/StopPreviewAudio`（会占用声卡）** | audio 表 + 对象存储（试听还依赖声卡） |
| `RenderService` | `RenderAudioStream`（逐 chunk）/`RenderAudioFile`（整段） | audio 表 + 对象存储，无硬件 |

部署上只有执行机这一份（`docker/docker-compose.prod.yml:49-51`，所有容器 `AUDIO_SERVICE_HOST=EXECUTOR_HOST`），启动时同时 `init_db` + 软删清理 + 标签预热 + PyAudio 初始化（`server.py:101-125`）。

问题：

- 执行机离线，服务器上的音频库接口全部不可用；
- 执行机要连 DB（隧道/remote.env），schema 与服务器强耦合；
- 数据面（库管理、上传、转码、混音）和硬件面（声卡）混在一个进程里，无法独立扩缩/发版。

---

## 2. 拆分边界

### 2.1 服务器 `audio_service`（容器，N 副本）

- `AudioConfigService` 除 `PreviewAudio` / `StopPreviewAudio` 外的全部 RPC（见 §3.1）；
- 启动时保留：`init_db`、软删清理守护线程、标签 ACL 预热、DB 日志 handler；
- 不初始化 PyAudio、不注册 `RenderService`。

### 2.2 `api_test_service` 进程内 API 混音（不再有 render 服务）

- 混音模块 = 原 `RenderService` 的六步混音（源加载 → 采样率对齐 → 时间轴 → 噪声/声纹 → 叠加 → SPL 增益），从 `audio_service/application/services/audio_stream_orchestrator.py` 抽到共享模块，由 `RoundRenderService` 直接调用；
- **契约变更（必须做）**：现在 `_load_source_pcm()` 在 audio_service 进程内用 `AudioRepository().get_audio()` 直连 `audios` 表（`audio_stream_orchestrator.py:242-257`）。搬走后 `api_test_service` 不直连 audio 表，改由 `RoundRenderService` 组装 `render_config` 时用已有的 `audio_acl.GetAudiosByIds` 批量补齐 `file_path / sample_rate / channels / duration`，混音模块只做 `storage.load_bytes()`；
- 读文件走 `shared.infrastructure.storage`，`api_test_service` 已有 storage 客户端（`infrastructure/oss/result_storage.py:33`），无需新增凭据；
- 实时链路收益：`realtime_session_executor` 原本「混音进程 → 跨进程 gRPC → WS 发送」变成同进程，少一次序列化和拷贝；
- 代价：PCM 缓存和混音线程进入 `api_test_service` 进程，**必须设上限**（缓存条数/TTL + 混音并发信号量），否则大文件缓存会顶爆进程内存。

### 2.3 本地 `audio_agent`（执行机宿主，端口 50052，每台 1 个）

- `AudioService`：`PlayAudio`、`StopAudio`、`GetPlayStatus`、`GetAudioInfo`、`GetPhysicalDevices`、`GetDeviceIndex`、`StopAudioByPattern`、`PrepareAudios`、`MeasureSPL`、`StartSPL`、`StopSPL`、`Shutdown`；
- `PlaybackService`：`StartPlayback`、`StopPlayback`（含 E2E 实时混音/重叠/背景噪声/声纹）；
- `AudioConfigService.PreviewAudio` / `StopPreviewAudio`（试听必须出声卡）；
- 启动时只保留 PyAudio 初始化；**不** `init_db`、**不**启软删清理、**不**做标签预热、**不**挂 DB 日志 handler；
- 不注册 `RenderService`；E2E 播放混音复用共享混音模块的底层原语（`audio_timeline`、`build_noise_info`、`audio_format_adapter`），与 API 混音保持同一套时间轴/噪声语义；
- 不持有 DB 账号、不持有 COS 密钥。

> 边界判断口径：需要「本机声卡 / 本机音频文件 / 毫秒级播放时序」的留本地；只读写音频库和对象存储的进服务器。

---

## 3. RPC 归属总表

### 3.1 服务器 `audio_service`

- `AudioConfigService`：
  - 元数据/标注/可见性/算法关联/删除：`UpdateAudioMetadata`、`UpdateAudioVisibility`、`BatchUpdateAnnotations`、`BatchActionAudios`、`DeleteAudio`、`UpdateAudioAlgorithms`、`BatchUpdateAudioAlgorithms`
  - 查询：`GetAllAudioTags`、`ListAudios`、`GetAudio`、`GetAudiosByIds`、`GetAudioByMD5`、`GetAllAudioIds`、`GetAudioAlgorithms`、`GetAudioFolderTree`、`GetAudioSpeakers`、`GetPlaybackHistory`
  - 取流：`StreamAudio`、`StreamAudioByPath`
  - 上传/导入/转换：`PresignUpload`、`PresignPart`、`CompleteDirectUpload`、`InitUploadTask`、`RegisterUploadFile`、`UploadChunk`、`MergeChunks`、`GetUploadProgress`、`UrlImport`、`RegisterAudioByBytes`、`ConvertAudio`
  - 分析/处理：`AnalyzeAudioFeatures`、`AssessAudioQuality`、`ProcessAudio`
  - **新增**：`RecordPlaybackHistory`（接收本地试听/播放历史回写，替代本地直接写表）
- 不注册 `RenderService`（挪到 `api_test_service` 进程内，见 §3.2）。

### 3.2 `api_test_service`（进程内，不再暴露 RPC）

- `RenderAudioStream` / `RenderAudioFile` 降级为方法调用：`RoundRenderService.stream_round_chunks()` / `render_round_file_to_storage()` 直接调用共享混音模块（`shared/audio_mix/`），不再走 `get_render_service_stub()`；
- 新增一次前置查询：`audio_acl.GetAudiosByIds` 补齐 `file_path / sample_rate / channels / duration`；
- 迁移完成后删除 `RenderService` proto、`RenderServiceServicer` 与 `shared/clients` 里的 render stub。

### 3.3 本地 `audio_agent`

- `AudioService` 全部 12 个 RPC；
- `PlaybackService` 2 个 RPC；
- `AudioConfigService.PreviewAudio`、`StopPreviewAudio`（只实现这两个方法，其余在服务器）。

### 3.4 调用方路由矩阵

| 调用方 | RPC | 目标 |
|---|---|---|
| `api_gateway` 音频库/上传/流地址 | `AudioConfigService` 数据面 | 服务器 `audio_service` |
| `api_gateway` 试听/停止试听、SPL | `PreviewAudio`/`StopPreviewAudio`、`StartSPL`/`StopSPL`/`MeasureSPL` | 对应 lab 的 `audio_agent` |
| `task_service` | `GetAudio*`/`ListAudios` | 服务器 `audio_service` |
| `task_service` 停播放 | `AudioService.StopAudio` | 对应 lab 的 `audio_agent` |
| `api_test_service` | `RenderAudioStream`/`RenderAudioFile` | **进程内调用**（无 RPC） |
| `api_test_service`/`algorithm_service`/`report_service` | `GetAudiosByIds` 等元数据 | 服务器 `audio_service` |
| `device_service` | 播放/播放状态、`GetAudio*` | 本机 `audio_agent`（127.0.0.1） |
| `e2e_test_service` | `PrepareAudios`、`StartPlayback`/`StopPlayback`、SPL | 本机 `audio_agent`（127.0.0.1） |

---

## 4. 服务之间的契约

### 4.1 音频文件：只走服务器 + 预存储

现有机制已具备，不需要新造：

- `shared/infrastructure/storage.py:330-345` `_fetch_bytes_via_server()`：按 `STORAGE_SERVER_FETCH_URL` 调网关 `/api/v1/audios/download?path=oss://...`；
- `storage.py:315-328` `STORAGE_LOCAL_CACHE_ENABLED` / `STORAGE_LOCAL_CACHE_WRITE`：回源成功后落本地缓存（预存储），下次直接命中；
- `storage.py:372-401` `load_file()` 顺序：预存储 → 服务器代理 → 本地降级 → OSS。

执行机配置：

```dotenv
STORAGE_BACKEND=local                  # 不初始化 S3 客户端
LOCAL_STORAGE_ROOT=<预存储目录>
STORAGE_LOCAL_CACHE_ENABLED=true
STORAGE_LOCAL_CACHE_WRITE=true
STORAGE_SERVER_FETCH_URL=http://<服务器网关>:15000
STORAGE_SERVER_FETCH_TOKEN=<媒体令牌密钥一致>
```

**禁止**在执行机下发 COS 预签名 URL；`PrepareAudios`/`load_file` 只允许走上述链路。

### 4.2 播放所需元数据：复用现有查询 RPC

本地 `PlaybackService` 现在直接查 audio/设备表，拆分后改为：

- 音频元数据：服务器 `GetAudiosByIds` / `GetAudioSpeakers` / `GetAudioAlgorithms`；
- 设备信息：本地 `device_service`（保留）；
- SPL/声纹增益：服务器 `GetAudioSpeakers` + 既有 `spl_to_gain` 逻辑随 agent 保留，入参由上面的查询补齐。

如果一次播放要解析的音轨很多，再加一个批量 `ResolvePlaybackAssets`（`audio_ids + device_unique_id → [{audio_id, file_path, duration, sample_rate, spl_gain, speaker_info}]`）把多次往返收敛成一次。**优先复用现有 RPC，proto 能不改就不改。**

### 4.3 播放/试听历史回写

`audio_preview_service.py:125-170` 现在直接 `record_playback_history` 写表。拆分后：

- 试听仍在本地执行，历史通过新增 `RecordPlaybackHistory` 回写服务器；
- 失败时本地落盘队列重试，避免一次网络抖动丢历史。

### 4.4 播放锁

Redis 分布式锁可继续由本地 agent 使用（现有 6379 隧道）；如后续多执行机，则把锁的 key 维度改成「设备唯一 ID」并在服务器侧统一仲裁。

---

## 5. 启动与配置改造

### 5.1 进程角色

`audio_service/interfaces/grpc/server.py` 增加角色开关（默认 `server` 保证向后兼容）：

```python
AUDIO_ROLE = os.environ.get('AUDIO_ROLE', 'server')  # server | agent
```

- `server`：注册 `AudioConfigServiceServicer`；执行 `init_db` / 软删清理 / 标签预热 / DB 日志；
- `agent`：注册 `AudioServiceServicer`、`PlaybackServiceServicer` 和只含试听的 `AudioConfigServiceServicer`；只执行 PyAudio 初始化。

> 不再需要 `render` / `server_core` 角色——混音已不在这个进程里。

### 5.2 环境变量矩阵

| 变量 | `audio_service`（`server`） | `api_test_service`（进程内混音） | `audio_agent` |
|---|---|---|---|
| `AUDIO_ROLE` | `server` | — | `agent` |
| `DATABASE_URL` / `REDIS_URL` | 需要 | 已有（业务库） | **不需要**（锁除外，见 §4.4） |
| `S3_*` / COS 凭据 | 需要 | **已有**（result_storage 已用） | **不需要** |
| `STORAGE_SERVER_FETCH_URL` | 不需要 | 不需要 | 需要 |
| `STORAGE_LOCAL_CACHE_*` | 可选 | 可选 | 需要 |
| `AUDIO_SERVICE_HOST`（客户端用） | 容器名 `audio_service` | 容器名 `audio_service` | — |
| `AUDIO_AGENT_HOST/PORT`（客户端用） | `EXECUTOR_HOST:50052` | — | `127.0.0.1:50052` |
| 混音资源上限（新增） | — | `AUDIO_MIX_MAX_CONCURRENCY`、`AUDIO_PCM_CACHE_TTL` | `AUDIO_MIX_MAX_CONCURRENCY` |

### 5.3 客户端 stub 拆分

现在 4 个 stub 共用一个 channel（`shared/clients/_grpc_stubs.py:30-57`，`_grpc_channels.py:21`）。改为两个 channel，且不再保留 render channel：

- `_get_audio_channel()` → `AUDIO_SERVICE_HOST`（库）；
- 新增 `_get_audio_agent_channel()` → 目标执行机的 `audio_agent`（按 lab 解析，见 §7）；
- `get_audio_config_service_stub()` → 库 channel；
- `get_audio_service_stub()` / `get_playback_service_stub()` → agent channel；
- 新增 `get_audio_agent_config_stub()`（`AudioConfigServiceStub` over agent channel），只给网关试听/停止试听与本地 SPL 用；
- `get_render_service_stub()` **删除**，`api_test_service` 改为进程内调用共享混音模块。

---

## 6. 部署改造

1. 新增 `docker/Dockerfile.audio_service`：同一镜像两个角色（`AUDIO_ROLE=server|agent`）；gRPC 50052，无 HTTP；用 `grpc_health_probe` 或 TCP 探活。
2. `docker/docker-compose.prod.yml` / `docker-compose.yml` 只增加 `audio_service` 一个 service：
   - `depends_on`: postgres / redis / minio（或 RustFS）；
   - 挂载分片上传共享卷（`AUDIO_UPLOAD_BASE_DIR`，见 §7.1）与预存储目录；
   - 仅容器网络暴露 50052，不映射公网；
   - `deploy.replicas` 可调；业务容器统一 `AUDIO_SERVICE_HOST=audio_service`。
3. `api_test_service` 不需要新增凭据，只需给混音加 `AUDIO_MIX_MAX_CONCURRENCY` / `AUDIO_PCM_CACHE_TTL` 两个上限；镜像内新增 `shared/audio_mix/` 模块。
4. 宿主 `scripts/host_services/service_entry.py` 的 `audio` 分支带 `AUDIO_ROLE=agent` 启动；`stack.py` 日志名改为 `audio_agent.log`（同步脚本与排障文档）。
5. `scripts/host_services/control.py` 的 remote.env 只注入执行机需要的变量（去掉 DB/COS，保留 Redis + 服务器取流地址 + `LAB_NAME`）。
6. 文档同步：`docs/微服务.md`、`docs/系统架构.md`、`docs/部署指南.md`、`iat-deploy` 技能里的 50052 宿主服务说明。

---

## 7. 横向扩展（多 API 实例 / 多 E2E 实例）

### 7.1 服务器：两个服务各自伸缩

- `audio_service`：按页面 QPS + 上传/转码队列走，CPU 主要花在 ffmpeg 转码/分析，按 CPU 使用率 HPA。
- `api_test_service`：按用例并发走；混音进来后它是「执行器 + 混音」同进程，CPU 与内存都要盯：
  - 混音并发用 `AUDIO_MIX_MAX_CONCURRENCY` 信号量限制，超限排队或快速失败，避免把执行器线程饿死；
  - PCM 缓存必须有 TTL 和条数上限（原实现 `audio_stream_orchestrator.py:226-240` 只有 TTL），大文件并发缓存是主要内存风险；
  - **不需要**再讨论「混音 gRPC 多副本 round_robin / 长流占 worker」——混音已经是进程内方法调用，随 `api_test_service` 副本天然扩展。
- 多副本下 `audio_service` 有状态点：分片上传把分片写本地盘（`audio_upload/task_mixin.py:249-252`，`merge_mixin.py:235`），`UploadChunk` 和 `MergeChunks` 可能打到不同副本。二选一：
  - 共享卷（NFS/云盘）挂 `AUDIO_UPLOAD_BASE_DIR`；或
  - 上传走直传 COS（`PresignUpload`/`CompleteDirectUpload`），大文件避开分片。
- 长任务（转码/分析/转换）加超时 + 按 `audio_id` 的 Redis 幂等锁，避免多副本重复转码、重复写存储。

### 7.2 gRPC 负载均衡

- gRPC 是长连接，走 K8s ClusterIP 时一条 channel 会**固定在一个副本**，多副本里只有一个在干活。`audio_service` 必须：
  - 用 headless service + `dns:///audio_service:50052` + `round_robin`；或
  - 每请求新建 call 并配合服务网格/L7 代理。
- `audio_service` 的 RPC 都是短请求（含 `StreamAudio` 流式取流），round_robin 即可；分片上传若不做共享卷，则必须按 `file_id` 做一致性路由。
- 混音不再占用任何 gRPC channel，`api_test_service` 的扩缩与 `audio_service` 完全解耦。

### 7.3 E2E：每台执行机一个 agent，按 lab 路由

- 部署单元 = 一台执行机上的三件套：`e2e_test_service + audio_agent + device_service`。N 台 E2E = N 个 `audio_agent`，各自监听 50052，**不是全局单例**。
- 同一台机器上跑多个 E2E 进程时，共享同一个 agent（不要每个进程起一个，声卡会互相抢）；并发由 `PlaybackService` 的设备维度锁串行化。
- 路由规则：
  - 同机调用（`e2e_test_service`、`device_service`）→ `127.0.0.1:50052`，不出网；
  - 跨机调用（网关试听、`task_service` 停播）→ 必须带执行机/lab 标识。任务用例本身已有 `lab_id` / `device_id`（执行域 P0），按 lab 找 agent；
  - 试听：前端需按实验室选择（或由用例/设备所属 lab 推断），网关把 `PreviewAudio/StopPreviewAudio` 路由到该 lab 的 agent；无 lab 的通用用例配置默认 lab。
- 服务发现：复用 `shared/utils/service_registry.py`，`audio_agent` 以 `capabilities={'lab_id': ..., 'devices': [...]}` 注册；客户端 `discover('audio_agent', lab_id=...)` 选实例，`AUDIO_AGENT_HOST` 仅保留为单机/开发兜底。

### 7.4 容量与端口

| 服务 | 副本数 | 伸缩依据 | 端口 |
|---|---|---|---|
| `audio_service` | ≥2 | CPU 使用率（转码/分析/CRUD） | 容器内 50052 |
| `api_test_service` | N | 用例并发 + 混音并发 | 容器内 50050 |
| `audio_agent` | 每执行机 1 | 固定 | 宿主 50052 |

### 7.5 客户端注意

- `api_test_service` 自己混音，多副本之间无需协调，但要限制单副本的混音并发和 PCM 缓存，避免 CPU/内存打满后拖垮同一进程里的执行器。
- agent 的地址解析结果要短缓存（例如 10s），避免每次播放都查注册中心；实例下线靠心跳过期。

---

## 8. 分阶段迁移与回滚

| 阶段 | 动作 | 可回滚点 |
|---|---|---|
| P0（本方案） | 定边界、RPC 归属、配置矩阵 | — |
| P1 | 服务器起 `audio_service`（只含库，1~2 副本）；`api_test_service` 混音加开关（默认仍走 gRPC，灰度切进程内）；本地进程仍全量（双跑）；网关读接口灰度切服务器 | 网关 `AUDIO_SERVICE_HOST` 切回执行机；混音开关切回 gRPC |
| P2 | 混音全量切进程内后删除 `RenderService` RPC/servicer/stub；本地只起硬件三服务；去掉本地 DB/COS；播放元数据改 RPC；取流改服务器代理 + 预存储；历史回写走新 RPC | 恢复本地全量进程 + 原 env；保留 `RenderService` 代码一个版本 |
| P3 | 清理本地数据面代码/配置、隧道和旧文档；按 §7 配多副本与按 lab 路由 | 保留 P2 的回滚包 |

灰度建议：P1 先切「列表/详情/上传/转码/分析」这类纯数据接口，试听与播放保持本地；确认服务器音频库稳定后再进 P2。

---

## 9. 风险与待确认

**风险**

1. 试听路由拆错会导致前端点击无声：网关的 `preview`/`stop-preview` 必须走目标 lab 的 agent channel，建议加开关灰度。
2. 本地去 DB 后，播放配置里的设备/SPL/说话人信息若缺字段会导致播放降级：P2 前先确认 `playback_config` 已带齐 `device_unique_id`、目标采样率、SPL 增益。
3. 预存储缓存一致性：音频被替换/转码后，key 若不变会命中旧文件；需确认 key 含内容 hash 或版本号（现有 `conv/`、`processed/` 路径已按产物分目录，需要核对覆盖场景）。
4. 服务器 audio 的取流鉴权：`/api/v1/audios/download` 已有 media token（`api_gateway/middleware.py:160-163`），执行机复用同一套 token 密钥，不要新开匿名通道。
5. 历史回写丢数据：本地队列 + 重试；服务器侧按幂等键去重。
6. 混音搬进 `api_test_service` 后与执行器同进程争 CPU/内存：必须用 `AUDIO_MIX_MAX_CONCURRENCY` + PCM 缓存上限兜住；实时用例的时序抖动要在压测里单独看。
7. `render_config` 契约变更容易漏：混音模块不再直连 `audios` 表，若 `RoundRenderService` 没把 `file_path` 等字段补齐，运行期才报 `FileNotFoundError`；建议加一条「配置字段齐全」的单测。
8. 多副本下的分片上传与 gRPC 连接固定（见 §7.1/§7.2）。

**待确认**

- 除 `api_gateway / task / api_test / algorithm / report / device / e2e` 外，是否还有其它入口直接调 audio？（当前扫描到的都在这 7 个内）
- 执行机是否允许保留 Redis 连接做播放锁；若不允许，锁要迁到服务器按设备维度仲裁。
- 多 E2E 实例的 lab 选择：试听由用户选 lab，还是按用例的 `lab_id` 强绑定？
- `GetAudioInfo` 是否需要本地解析新上传文件（若是，仍留 agent，但文件通过服务器代理取）。
- 服务器 `audio_service` 的预存储卷容量与清理策略（与现有 `LOCAL_STORAGE_ROOT` 清理任务是否共用）。
- 混音模块的物理落点：抽到顶层 `shared/audio_mix/`（`api_test_service` 与 `audio_agent` 都 import），还是留在 `audio_service` 包内被跨包引用？倾向前者，但会带来一次 `audio_service` 内部 import 路径调整。

---

## 10. 本次不做

- 不改 proto、不改代码、不动部署；
- 不引入新的音频存储后端，沿用现有对象存储 + 本地缓存。

---

## 11. 目标拓扑速查

```
服务器（N 副本）                              执行机（每 lab 一台）
┌────────────────────────────────────┐      ┌────────────────────────────────┐
│ api_gateway ×N                    │      │ e2e_test_service               │
│   │ 库/上传/转码/试听路由            │      │ device_service                 │
│   ▼                               │      │   │ 127.0.0.1                  │
│ audio_service ×N                  │ RPC  │   ▼                            │
│   AudioConfigService · 音频库      │◄────►│ audio_agent :50052             │
│   │                               │取流回源│   AudioService + Playback      │
│   ▼                               │      │   PreviewAudio / SPL           │
│ PostgreSQL · Redis · 对象存储      │      │   E2E 播放混音                  │
│                                   │      │   │                            │
│ api_test_service ×N（执行器）      │      │   ▼                            │
│   混音模块（原 RenderService）      │      │ 本机声卡 · 预存储缓存            │
└────────────────────────────────────┘      └────────────────────────────────┘
```

四条关键链路：

1. **浏览器 → 网关 → `audio_service`**：音频库 CRUD、上传、转码、分析、`StreamAudio`。
2. **浏览器 → 网关 → `audio_agent`**：试听/停止试听、SPL。按 lab 路由，不经过服务器。
3. **`audio_agent` → 网关 `/api/v1/audios/download` → 回源对象存储**：执行机取音频文件，落预存储，不持有 COS 密钥。
4. **`api_test_service` 进程内混音**：`RoundRenderService` 先 `GetAudiosByIds` 拿 `file_path` 等元数据，再调用共享混音模块产出 chunk/整段；E2E 的实时混音在 `audio_agent` 的播放编排里用同一套底层原语完成。

与改造前相比的结构变化：

- 服务器多一个 `audio_service`（原来只有执行机那一份）；
- 执行机那份进程改叫 `audio_agent`，只保留硬件面，去掉 DB/COS 依赖；
- `RenderService` 从 gRPC 服务降级为 `api_test_service` 进程内模块，服务端不再有混音服务；
- 网关的试听类接口从「调唯一 audio 服务」变成「按 lab 调对应 agent」。
