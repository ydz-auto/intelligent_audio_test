# audio 服务拆分方案（本地 audio_agent + 服务器 audio_service）

> 状态：方案评审稿，不改代码
> 日期：2026-11-25

## 0. 结论

按「**碰不碰声卡 / 是不是播放时序敏感**」切，而不是按音频业务模块切：

| 部署单元 | 位置 | 定位 | 包含 | 副本数 |
|---|---|---|---|---|
| `audio_service` | 服务器容器 | 数据面 | `AudioConfigService`（去除试听） | N（随页面 QPS/转码队列） |
| `audio_render` | 服务器容器 | API 混音 | `RenderService` | N（随 API 实例同比例，CPU 密集） |
| `audio_agent` | 执行机宿主 | 硬件面 | `AudioService` + `PlaybackService` + `PreviewAudio/StopPreviewAudio`（E2E 试听） | 每台执行机 1 个 |

两条硬约束：

1. **API 混音跟 API，E2E 混音跟 E2E**：`RenderService` 只被 `api_test_service` 调用，属于 API 混音，搬服务器；E2E 的混音是播放编排里的实时多设备叠加（`audio_engine` 播放链路），不是 `RenderService`，跟着 E2E 留在本地。
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

- `AudioConfigService` 除 `PreviewAudio` / `StopPreviewAudio` 外的全部 RPC（见 §3）；
- 启动时保留：`init_db`、软删清理守护线程、标签 ACL 预热、DB 日志 handler；
- 不初始化 PyAudio。

### 2.2 服务器 `audio_render`（容器，N 副本）

- `RenderService.RenderAudioStream` / `RenderAudioFile`（API 混音，只服务 `api_test_service`）；
- 与 `audio_service` 同镜像不同 `AUDIO_ROLE=render`，单独 Deployment/Compose service，独立伸缩；
- 基本无状态：只读 audio 表 + 对象存储，返回字节流，不落本地盘（产物由 `api_test_service` 保存）；
- 不初始化 PyAudio，不启标签预热/软删清理。

### 2.3 本地 `audio_agent`（执行机宿主，端口 50052，每台 1 个）

- `AudioService`：`PlayAudio`、`StopAudio`、`GetPlayStatus`、`GetAudioInfo`、`GetPhysicalDevices`、`GetDeviceIndex`、`StopAudioByPattern`、`PrepareAudios`、`MeasureSPL`、`StartSPL`、`StopSPL`、`Shutdown`；
- `PlaybackService`：`StartPlayback`、`StopPlayback`（含 E2E 实时混音/重叠/背景噪声/声纹）；
- `AudioConfigService.PreviewAudio` / `StopPreviewAudio`（试听必须出声卡）；
- 启动时只保留 PyAudio 初始化；**不** `init_db`、**不**启软删清理、**不**做标签预热、**不**挂 DB 日志 handler；
- 不持有 DB 账号、不持有 COS 密钥。

> 边界判断口径：需要「本机声卡 / 本机音频文件 / 毫秒级播放时序」的留本地；只读写音频库和对象存储的进服务器。

---

## 3. RPC 归属总表

### 3.1 服务器 `audio_service`（库）

- `AudioConfigService`：
  - 元数据/标注/可见性/算法关联/删除：`UpdateAudioMetadata`、`UpdateAudioVisibility`、`BatchUpdateAnnotations`、`BatchActionAudios`、`DeleteAudio`、`UpdateAudioAlgorithms`、`BatchUpdateAudioAlgorithms`
  - 查询：`GetAllAudioTags`、`ListAudios`、`GetAudio`、`GetAudiosByIds`、`GetAudioByMD5`、`GetAllAudioIds`、`GetAudioAlgorithms`、`GetAudioFolderTree`、`GetAudioSpeakers`、`GetPlaybackHistory`
  - 取流：`StreamAudio`、`StreamAudioByPath`
  - 上传/导入/转换：`PresignUpload`、`PresignPart`、`CompleteDirectUpload`、`InitUploadTask`、`RegisterUploadFile`、`UploadChunk`、`MergeChunks`、`GetUploadProgress`、`UrlImport`、`RegisterAudioByBytes`、`ConvertAudio`
  - 分析/处理：`AnalyzeAudioFeatures`、`AssessAudioQuality`、`ProcessAudio`
  - **新增**：`RecordPlaybackHistory`（接收本地试听/播放历史回写，替代本地直接写表）

### 3.2 服务器 `audio_render`（API 混音）

- `RenderService`：`RenderAudioStream`、`RenderAudioFile`（仅 `api_test_service` 调用）。

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
| `api_test_service` | `RenderAudioStream`/`RenderAudioFile` | 服务器 `audio_render` |
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
AUDIO_ROLE = os.environ.get('AUDIO_ROLE', 'server')  # server | render | agent
```

- `server`：只注册 `AudioConfigServiceServicer`；执行 `init_db` / 软删清理 / 标签预热 / DB 日志；
- `render`：只注册 `RenderServiceServicer`；执行 `init_db`（只读 audio 表）；不启标签预热/软删清理；
- `agent`：注册 `AudioServiceServicer`、`PlaybackServiceServicer` 和只含试听的 `AudioConfigServiceServicer`；只执行 PyAudio 初始化。

### 5.2 环境变量矩阵

| 变量 | `audio_service`（server） | `audio_render`（render） | `audio_agent` |
|---|---|---|---|
| `AUDIO_ROLE` | `server` | `render` | `agent` |
| `DATABASE_URL` / `REDIS_URL` | 需要 | 需要（只读 audio 表；Redis 可不配） | **不需要**（锁除外，见 §4.4） |
| `S3_*` / COS 凭据 | 需要 | 需要（读源文件） | **不需要** |
| `STORAGE_SERVER_FETCH_URL` | 不需要 | 不需要 | 需要 |
| `STORAGE_LOCAL_CACHE_*` | 可选 | 可选（PCM 缓存走进程内存，可不落盘） | 需要 |
| `AUDIO_SERVICE_HOST`（客户端用） | 容器名 `audio_service` | — | — |
| `AUDIO_RENDER_HOST`（客户端用） | — | 容器名 `audio_render` | — |
| `AUDIO_AGENT_HOST/PORT`（客户端用） | `EXECUTOR_HOST:50052` | — | `127.0.0.1:50052` |

### 5.3 客户端 stub 拆分

现在 4 个 stub 共用一个 channel（`shared/clients/_grpc_stubs.py:30-57`，`_grpc_channels.py:21`）。改为三个 channel：

- `_get_audio_channel()` → `audio_service`（库）；
- 新增 `_get_audio_render_channel()` → `audio_render`（API 混音，需 `dns:///` + round_robin，见 §7）；
- 新增 `_get_audio_agent_channel()` → 目标执行机的 `audio_agent`（按 lab 解析，见 §7）；
- `get_audio_config_service_stub()` → 库 channel；
- `get_render_service_stub()` → render channel；
- `get_audio_service_stub()` / `get_playback_service_stub()` → agent channel；
- 新增 `get_audio_agent_config_stub()`（`AudioConfigServiceStub` over agent channel），只给网关试听/停止试听与本地 SPL 用。

---

## 6. 部署改造

1. 新增 `docker/Dockerfile.audio_service`：同一镜像三个角色（`AUDIO_ROLE=server|render|agent`）；gRPC 50052，无 HTTP；用 `grpc_health_probe` 或 TCP 探活。
2. `docker/docker-compose.prod.yml` / `docker-compose.yml` 增加 `audio_service`、`audio_render` 两个 service：
   - `depends_on`: postgres / redis / minio（或 RustFS）；
   - `audio_service` 挂载分片上传共享卷（`AUDIO_UPLOAD_BASE_DIR`，见 §7.1）与预存储目录；
   - 仅容器网络暴露 50052，不映射公网；
   - 两个服务都设 `deploy.replicas` 可调；业务容器分别配置 `AUDIO_SERVICE_HOST=audio_service`、`AUDIO_RENDER_HOST=audio_render`。
3. 宿主 `scripts/host_services/service_entry.py` 的 `audio` 分支带 `AUDIO_ROLE=agent` 启动；`stack.py` 日志名改为 `audio_agent.log`（同步脚本与排障文档）。
4. `scripts/host_services/control.py` 的 remote.env 只注入执行机需要的变量（去掉 DB/COS，保留 Redis + 服务器取流地址 + `LAB_NAME`）。
5. 文档同步：`docs/微服务.md`、`docs/系统架构.md`、`docs/部署指南.md`、`iat-deploy` 技能里的 50052 宿主服务说明。

---

## 7. 横向扩展（多 API 实例 / 多 E2E 实例）

### 7.1 服务器：`audio_service` 与 `audio_render` 分开伸缩

- 副本数不同源：`audio_service` 跟页面 QPS、上传/转码队列走；`audio_render` 跟 API 用例并发走，是 CPU 密集型，必须独立 HPA。
- `audio_render` 基本无状态：只读 audio 表 + 对象存储，返回字节流，PCM 缓存只在进程内（`audio_stream_orchestrator.py:226-257`），多副本无需共享状态。
- `audio_service` 有状态点：分片上传把分片写本地盘（`audio_upload/task_mixin.py:249-252`，`merge_mixin.py:235`），`UploadChunk` 和 `MergeChunks` 可能打到不同副本。二选一：
  - 共享卷（NFS/云盘）挂 `AUDIO_UPLOAD_BASE_DIR`；或
  - 上传走直传 COS（`PresignUpload`/`CompleteDirectUpload`），大文件避开分片。
- 长任务（转码/分析/转换）加超时 + 按 `audio_id` 的 Redis 幂等锁，避免多副本重复转码、重复写存储。

### 7.2 gRPC 负载均衡（关键）

- gRPC 是长连接，走 K8s ClusterIP 时一条 channel 会**固定在一个副本**，多副本里只有一个在干活。必须：
  - 用 headless service + `dns:///audio_render:50052` + `round_robin`；或
  - 每请求新建 call 并配合服务网格/L7 代理。
- `RenderAudioStream` 是长时间 server-streaming：单个 stream 固定在某个副本是正常的，但要限制每副本并发 stream 数（`grpc.max_concurrent_streams`），并给 render 调用设置合理 deadline；扩容以「并发 stream 数 / CPU 核数」估算副本。
- `audio_service` 的 CRUD 是短请求，round_robin 即可；分片上传若不做共享卷，则必须按 `file_id` 做一致性路由。

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
| `audio_service` | ≥2 | 页面 QPS / 上传转码队列 | 容器内 50052 |
| `audio_render` | 与 API 实例同比例 | 并发 render stream / CPU | 容器内 50052 |
| `audio_agent` | 每执行机 1 | 固定 | 宿主 50052 |

### 7.5 客户端注意

- `api_test_service` 多实例时，render channel 必须开 round_robin，否则所有 render 流量压到同一个 `audio_render` 副本。
- 长流调用不要无限重试；render 失败应让该用例失败并带上下文，避免重试放大 CPU。
- agent 的地址解析结果要短缓存（例如 10s），避免每次播放都查注册中心；实例下线靠心跳过期。

---

## 8. 分阶段迁移与回滚

| 阶段 | 动作 | 可回滚点 |
|---|---|---|
| P0（本方案） | 定边界、RPC 归属、配置矩阵 | — |
| P1 | 服务器起 `audio_service` + `audio_render`（各 1 副本即可）；本地进程仍全量（双跑）；网关读接口灰度切服务器 | 网关 `AUDIO_SERVICE_HOST` 切回执行机 |
| P2 | 本地只起硬件三服务；去掉本地 DB/COS；播放元数据改 RPC；取流改服务器代理 + 预存储；历史回写走新 RPC | 恢复本地全量进程 + 原 env |
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
6. 多副本下的分片上传与 gRPC 连接固定（见 §7.1/§7.2），是上线前必须先压测的两项。

**待确认**

- 除 `api_gateway / task / api_test / algorithm / report / device / e2e` 外，是否还有其它入口直接调 audio？（当前扫描到的都在这 7 个内）
- 执行机是否允许保留 Redis 连接做播放锁；若不允许，锁要迁到服务器按设备维度仲裁。
- 多 E2E 实例的 lab 选择：试听由用户选 lab，还是按用例的 `lab_id` 强绑定？
- `GetAudioInfo` 是否需要本地解析新上传文件（若是，仍留 agent，但文件通过服务器代理取）。
- 服务器 `audio_service` 的预存储卷容量与清理策略（与现有 `LOCAL_STORAGE_ROOT` 清理任务是否共用）。

---

## 10. 本次不做

- 不改 proto、不改代码、不动部署；
- 不调整 `api_test_service` 的混音调用方式（仅换目标地址与 LB 策略）；
- 不引入新的音频存储后端，沿用现有对象存储 + 本地缓存。
