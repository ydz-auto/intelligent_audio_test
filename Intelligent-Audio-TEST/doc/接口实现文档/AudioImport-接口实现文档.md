# 音频资源管理接口实现文档

## 1. 模块概述
音频资源管理模块负责系统中测试音频（包括唤醒词、命令词、背景噪声等）的完整生命周期管理。支持多种导入方式（上传、URL 导入、在线录制）、格式转换、元数据编辑以及批量操作。

## 2. 接口详细实现思路

### 1.1 获取音频列表 (GET /api/v1/audios)
**实现思路：**
1. **参数过滤**：接收 `page`, `perPage/per_page`, `keyword`, `format`, `audioType/audio_type`, `folder`, `sampleRate/sample_rate`, `duration`。
2. **查询构建**：
   - 基础查询 `audios` 表，过滤 `deleted=False` 的记录。
   - `keyword`：在 `name`, `original_filename` 中模糊搜索。
   - `format`, `audioType` (dry/noise)：精确匹配。
   - `folder`：通过 `file_path` 字段模糊匹配。
   - `sampleRate/sample_rate`：精确匹配。
   - `duration`：根据枚举值（short/medium/long）过滤不同时长范围的音频。
3. **分页与排序**：使用 SQLAlchemy 的 `paginate` 方法实现物理分页，按 `created_at` 降序排列。
4. **统计信息**：返回总文件数、总大小、总时长、今日上传数等聚合数据。

### 1.2 音频上传 (POST /api/v1/audios/upload)
**实现思路：**
1. **文件接收与处理**：
   - 支持两种上传方式：通过 `request.files` 接收 FormData 上传的文件（浏览器环境），或通过 JSON 传递文件路径（Electron 环境）。
   - 处理 `relativePath` 参数，用于保持原文件结构。
2. **存储策略**：
   - 将文件保存至配置的静态资源目录（如 `/uploads/audios/`）。
   - 文件名处理：使用 `secure_filename` 清理文件名，防止重名，通过计数器机制确保文件名唯一。
3. **元数据提取**：使用 `pydub` 提取音频的 `duration`, `sample_rate`, `channels`, `bitrate`, `format` 等信息。
4. **MD5 校验**：支持通过 MD5 校验文件是否已存在，避免重复上传。
5. **入库记录**：在 `audios` 表中创建记录，保存 `file_path`, `file_size` 及元数据。
6. **标签生成**：根据 `relative_path` 自动生成标签，将目录结构作为标签关联到音频。
7. **测试用例创建**：支持上传后自动创建测试用例，可指定测试类型、播放设备、SPL 值等参数。

### 1.3 URL 远程导入 (POST /api/v1/audios/url-import)
**实现思路：**
1. **参数验证**：验证请求中是否包含 `url` 参数。
2. **文件下载**：使用 `requests` 库的 `get` 方法下载远程音频文件，支持流式下载。
3. **临时存储**：将下载的文件内容保存到 BytesIO 对象中。
4. **后续处理**：调用与“音频上传”一致的 `_save_audio` 方法处理文件：
   - 提取元数据
   - 保存文件到指定目录
   - 入库记录
   - 根据 `relative_path` 自动生成标签
5. **响应返回**：返回创建的音频 ID 和名称。


### 1.5 音频格式转换 (POST /api/v1/audios/:id/convert)
**实现思路：**
1. **参数验证**：校验目标格式、采样率、声道数、位深、比特率是否在支持范围内（INT-817 附加参数，2026-10-19 实现演进裁定）：
   - 目标采样率 `sample_rate`（可选）：8000-192000 Hz，超范围 400 且提示明确。
   - 目标声道数 `channels`（可选）：1-8，超范围 400。
   - 目标位深度 `bit_depth`（可选）：8 / 16 / 24 / 32 bit，仅 wav/flac 等无损失格式生效（WAV 走 PCM codec、FLAC 走 sample_fmt）。
   - 目标比特率 `bitrate`（可选）：正数 kbps，接受 `128` / `"128k"` / `"1m"`，仅 mp3/aac/ogg 等有损格式生效（`-b:a`）。
   - 全部附加参数可选，不传时保持原行为（仅转换格式）；旧前端透传任意数据向后兼容。
2. **转换引擎**：调用 `ffmpeg`（经 pydub）执行转换，采样率→`-ar`、声道数→`-ac`、位深→codec / sample_fmt、比特率→`-b:a`。
3. **文件管理**：转换产物统一另存为新文件（`conv_{uuid}.{format}`）并更新 `audios` 记录的 `file_path` / `format` / `size`，同时刷新 `sample_rate` / `channels` / `bitrate` 元数据（与 V9.7.10 行为一致；「替换原文件」选项未实现）。

### 1.6 元数据管理 (PUT /api/v1/audios/:id/metadata)
**实现思路：**
1. **字段更新**：支持修改 `filename`, `audio_type`, `asr_text`, `description`。
2. **标签管理**：更新 `audio_tags` 关联表。
3. **翻译管理**：
   - 翻译文本存储在 `audio_translations` 表中。
   - 需要指定 `direction_id`（关联 `translation_directions` 表）。
   - 若用户修改了 `asr_text`，可联动更新相关翻译。
4. **成功返回**：返回更新后的元数据。

### 1.7 批量操作 (POST /api/v1/audios/batch-action)
**实现思路：**
1. **批量删除**：
   - 物理删除文件。
   - 删除 `audio_tags`, `audio_translations`, `test_case_audios` (注意级联影响) 中的关联记录。
   - 从 `audios` 表中移除记录（逻辑删除）。
   - 被测试用例 / 设备提示词 / 任务引用的音频跳过并计入返回（与 V9.7.10 四重引用检查一致）。
2. **批量导出**：将选中的音频文件打包为 `zip` 提供下载（base64 返回）。
3. **批量修改标签**：批量更新 `audio_tags` 关联表。
4. **批量移动 / 复制 / 重命名 / 修改属性**（INT-818 扩展，2026-10-19 实现演进裁定）：
   - 请求扩展字段（React 弹窗 `targetFolder` / `renameRule` / `property` 一一对应；snake_case / camelCase 双口径接受，旧 Vue extraParams 透传向后兼容）：
     - `target_folder` / `targetFolder`：move / copy 目标文件夹（如 `test_data/dry`；兼容 folder-tree `direct/` 前缀，拒绝空目录 / `.` / `..` 穿越 / 绝对路径）。
     - `rename_rule` / `renameRule`：rename 统一命名规则前缀，自动追加序号（`{rule}{01..N}{原扩展名}`，如 `测试音频_01.wav`）。
     - `property`：modify-properties 属性名（`metadata` / `audio-type`）。
     - `property_value` / `propertyValue`：modify-properties 属性值（`metadata` 为字段字典，白名单列 `name` / `audio_type` / `asr_text` / `description` / `source_language`；`audio-type` 为 `dry` / `noise` / `prompt` / `mixed`）。
   - **move**：存储对象迁移（下载→重存→删源）+ 更新 `file_path`；目标 key 与源相同视为原地不动；目标已存在追加 `_N` 序号去重。
   - **copy**：存储对象复制 + 新建 `audios` 记录（元数据照搬，源记录与源文件保留）。
   - **rename**：仅更新 `name` 列（不碰物理文件）。
   - **modify-properties**：更新 `audios` 白名单列；`spl` 明确拒绝（`audios` 无 per-audio SPL 列，SPL 为设备/API 级 `spl_mappings` 映射，返回 400 说明原因，非静默跳过）。
   - 返回 `{action, success_count, failed_count}`（含失败 audio_id 明细）。

### 1.8 预览与播放 (GET /api/v1/audios/:id/stream)
**实现思路：**
1. **流式传输**：支持 `Range` 请求，满足前端播放器的拖动进度条需求。
2. **波形图生成**：提供接口返回音频的波形数据 JSON，供前端可视化渲染。

### 1.9 试听音频 (POST /api/v1/audios/:id/preview)
**实现思路：**
1. **参数解析**：接收 `audio_id` 及可选的 `playback_device_id`, `spl`。
2. **路由选择**：
   - 若未指定 `playback_device_id`：默认通过 HTTP Stream 返回，前端浏览器直接播放。
   - 若指定了 `playback_device_id`：后端控制指定的硬件播放器进行放音（用于现场环境验证）。
3. **音量映射**：若提供了 `spl` 值，后端需根据该设备的 `spl_mapping` 配置，将目标声压级转换为播放器所需的数字增益或音量百分比。
4. **即时性**：该接口应具备极低延迟，确保用户点击“试听”后能立即听到声音。

### 1.10 文件夹批量导入 (POST /api/v1/audios/folder-import)
**实现思路：**
1. **路径接收**：接收前端传递的本地文件夹绝对路径 `folder_path`（在 Electron 环境下可通过 `dialog.showOpenDialog` 获取）。
2. **递归扫描**：递归遍历该文件夹及其所有子文件夹，筛选出支持的音频格式文件。
3. **标签自动生成**：
   - 计算每个音频文件相对于 `folder_path` 的相对路径。
   - 将相对路径中的每一级文件夹名称作为音频的标签。
   - 示例：导入 `C:/MyAudios`，文件 `C:/MyAudios/Noise/Indoor/AC.wav` 的自动标签为 `["Noise", "Indoor"]`。
4. **元数据提取与入库**：
   - 将音频文件处理（如复制/移动）到系统指定的存储目录。
   - 提取音频元数据（时长、采样率等）。
   - 在 `audios` 表记录文件信息，在 `audio_tags` 表中建立文件夹层级与音频的关联。
5. **进度监控**：支持异步处理，通过 SocketIO (默认命名空间 `/`) 实时反馈进度（事件名：`audio_import_progress`）。

### 1.11 分片上传实现

#### 1.11.1 初始化上传任务 (POST /api/v1/audios/upload/init)
**实现思路：**
1. **目录初始化**：确保上传相关目录（基础目录、分片目录、临时目录）存在。
2. **任务创建**：生成唯一的 `taskId`，创建上传任务记录，设置过期时间（默认7天）。
3. **任务状态管理**：初始化任务状态为 `preparing`。
4. **响应返回**：返回 `taskId` 和成功消息。

#### 1.11.2 注册上传文件 (POST /api/v1/audios/upload/register)
**实现思路：**
1. **任务验证**：检查 `taskId` 是否存在且有效。
2. **文件信息注册**：
   - 接收 `files` 参数，包含多个文件的名称、大小、MD5 等信息。
   - 为每个文件生成唯一的 `fileId`，计算总分片数（默认 10MB/片）。
   - 检查 MD5 是否已存在，避免重复上传。
3. **数据库记录**：在 `upload_files` 表中创建记录，保存文件信息。
4. **响应生成**：返回文件上传信息，包括 `fileId`, `filename`, `totalChunks`, `chunkSize`。

#### 1.11.3 上传分片 (POST /api/v1/audios/upload/chunk)
**实现思路：**
1. **分片信息验证**：检查 `fileId`, `chunkIndex`, `totalChunks`, `taskId` 是否完整。
2. **分片存储**：将分片文件存储到对应文件的临时目录中，命名为 `chunk_{chunkIndex}`。
3. **数据库记录**：
   - 更新 `upload_chunks` 表中的分片状态。
   - 更新 `upload_files` 表中的已上传分片数和已上传大小。
   - 更新 `upload_tasks` 表中的总体进度。
4. **进度更新**：更新任务和文件的上传进度。
5. **响应返回**：返回当前分片的上传状态、已上传分片数、总分片数、已上传大小、文件大小以及任务整体进度。

#### 1.11.4 合并分片 (POST /api/v1/audios/upload/merge)
**实现思路：**
1. **参数验证**：检查 `taskId` 和 `fileId` 是否有效。
2. **分片完整性检查**：检查是否所有分片都已上传完成。
3. **分片合并**：
   - 按 `chunkIndex` 顺序读取所有分片文件。
   - 将分片内容合并为完整文件。
4. **元数据提取**：使用 `pydub` 提取合并后文件的时长、采样率、声道数、比特率、格式等元数据。
5. **文件处理**：
   - 将合并后的文件移动到最终存储目录。
   - 在 `audios` 表中创建记录，保存文件信息和元数据。
   - 根据 `relative_path` 自动生成标签，将目录结构作为标签关联到音频。
   - 可选：创建测试用例（根据 `createTestCase` 参数）。
6. **清理工作**：删除临时分片文件和目录。
7. **响应返回**：返回创建的音频 ID、名称和状态。

#### 1.11.5 获取上传进度 (GET /api/v1/audios/upload/progress)
**实现思路：**
1. **任务验证**：检查 `taskId` 是否存在且有效。
2. **进度查询**：
   - 查询 `upload_tasks` 表获取任务基本信息。
   - 查询 `upload_files` 表获取所有文件的上传进度。
3. **响应返回**：返回任务的当前状态、总文件数、已完成文件数、总大小、已上传大小，以及每个文件的详细进度信息。

### 1.12 播放历史 (GET /api/v1/audios/:id/playback-history)
（INT-819 新增，2026-10-19 实现演进裁定）
**实现思路：**
1. **数据表**：新增 `audio_playback_history` 表（见数据库设计文档 §2.5.4），记录播放时间 / 测试用例 / 播放设备 / 结果 / 时长。
2. **写侧**：
   - 试听 preview 落点：`audio_preview_service.preview_audio` 播放成功时每设备落一条 `success`；解析到设备但不可用 / 硬件播放失败落一条 `failed`（不阻塞试听主流程）。
   - 用例预览落点：`playback_orchestrator` 对每个尝试播放的干声音频落一条（已安排播放 → `success`，未安排 → `failed`），携带 `testcase_id`（UUID，String 列）与 `testcase_name` 快照。
   - `source` 字段标识记录来源，本期写侧为 `preview`（`execution` 为测试执行回放预留）。
3. **读侧**：按 `audio_id` 过滤，`created_at` 倒序分页（`page` / `per_page`，默认 1 / 10，INT-297 信封 `items/total/page/per_page/pages`）。
4. **响应条目字段**：`id` / `audio_id` / `testcase_id` / `testcase_name` / `device_id` / `device_name` / `result`（`success` | `failed`）/ `duration`（秒）/ `source` / `played_at`（= 播放时间 `created_at`），与 React 播放历史弹窗期望一致。
5. **权限**：`audio:read`。
6. **迁移**：`scripts/migrations/202610/add_audio_playback_history_table.py`（幂等；新建库经 `create_all_tables` 带出）。

### 1.13 音频特征分析 / 质量评估 / 处理
（INT-820 新增，2026-10-19 实现演进裁定）
**实现思路：**

1. **特征分析** (GET /api/v1/audios/:id/features，权限 `audio:read`)：
   - 频谱特征：基频范围（帧级自相关估计 min/max）、主频能量峰（Welch PSD 峰值频率）、谐波失真（THD%）。
   - 能量分布：平均能量（整体 RMS dBFS）、峰值能量（峰值 dBFS）、能量集中度（1 - 谱平坦度）。
   - 时域特征：过零率、活跃时长占比（帧 RMS 相对峰值 -50dB 门限）、起始时间（首个活跃帧）。
   - 响应：`{spectral: {fundamental_range_low, fundamental_range_high, dominant_frequency, harmonic_distortion}, energy: {average_energy_db, peak_energy_db, energy_concentration}, time_domain: {zero_crossing_rate, active_duration_ratio, onset_time}, audio_id, duration}`。

2. **质量评估** (GET /api/v1/audios/:id/quality，权限 `audio:read`)：
   - 信噪比（谱域 SNR：信号平均功率密度 vs PSD 中位数宽带噪声底）。
   - 动态范围（峰值幅度 vs 噪声底幅度）。
   - 频率响应评分（-40dB 带宽覆盖可闻频带比例）。
   - 整体质量评分（SNR / 动态范围 / 频率响应加权，0-100）。
   - 响应：`{snr_db, dynamic_range_db, frequency_response_score, quality_score, audio_id, duration}`。

3. **处理** (POST /api/v1/audios/:id/process，权限 `audio:update`)：
   - 请求：`operation`（`denoise` | `gain` | `trim`，必填）、`mode`（`new` 默认：生成新文件并创建新音频记录；`overwrite`：更新原记录 `file_path` / `format` / `size` / `duration` / `sample_rate` / `channels`）、`gain_db`（增益调整，有限值且 clamp 到 ±60dB）、`start_ms` / `end_ms`（剪辑区间，ms；省略默认取全长，非法区间 400）。
   - 处理产物统一导出为 wav 落存储（`processed/{uuid}.wav`）；`mode=new` 时新记录命名「原名 + 操作后缀」。
   - 响应：`{audio_id, operation, mode, format: 'wav', file_path, duration, size[, new_audio_id]}`。
   - DSP：降噪 = STFT 谱门降噪（软增益掩码 + 响度保持）；增益 = 线性增益 + 削波保护；剪辑 = pydub 切片。

### 1.14 按字节登记音频（RegisterAudioByBytes，gRPC 内部命令，INT-2216）
（INT-2215 用例 ZIP 导入回导音频的第二张卡；契约来自 INT-2205 审计「导入侧裁定」，2026-10-31）

**用途**：用例包只带音频二进制 + manifest（name/format/size/md5，见 INT-2214 导出），目标库没有对应音频时按字节登记一条 `audios` 记录；**同 md5 幂等复用**，保证跨库导入重复执行不产生重复音频、不按 `audio_id` 错绑。本命令不对外暴露 HTTP，只经 audio_service gRPC 供 api_gateway 用例导入服务调用。

**接口签名**：`rpc RegisterAudioByBytes(RegisterAudioByBytesRequest) returns (AudioConfigResponse);`

- 请求：`RegisterAudioByBytesRequest { string data = 1; }`，`data` 为 JSON 字符串（与 `UploadChunk` 同法，二进制走 base64）。
- 响应：既有 `AudioConfigResponse { success, message, data }`；`data` 为 JSON 字符串。proto 无 `code` 字段，成功/失败的 200/400 语义随 `data.code` 回传。

**请求字段（data JSON）**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 音频显示名（`audios.name`）；同 md5 复用时**不会**改名 |
| `md5` | string | 是 | 源字节 md5（32 位十六进制，大小写不敏感）；必须与实际字节一致 |
| `content_b64` | string | 是 | 源字节 base64；空串表示 0 字节内容（会被拒） |
| `format` | string | 否 | 源格式，缺省 `wav`（落库 `audios.format`） |
| `size` | int | 否 | 源字节数，仅作调用方自检参照；落库 `audios.size` 取存储对象真实大小 |
| `audio_type` | string | 否 | 音频类型，缺省 `dry` |
| `source_filename` | string | 否 | 原始文件名（存储 key 用的 stem），缺省用 `name` |

**响应字段（成功时 `data`）**

`{id, name, original_filename, format, size, md5, duration, sample_rate, channels, bitrate, audio_type, file_path, visibility, created_by_user_id, reused, code}`

- `reused`：`true` = 命中既有同 md5 记录（未新建、未改名）；`false` = 本次新建。
- `code`：成功恒 `200`。
- `duration` 为**真实探测值**（pydub 解码，秒）；`size` 为存储对象字节数；`visibility` 默认 `shared`；`created_by_user_id` 取调用方 gRPC metadata `x-user-id`（未透传时为空）。

**失败分类（四类分开，`success=false` + `data.code` / `data.reason` + `message`，均不落库）**

| 场景 | `data.code` | `data.reason` | 说明 |
|---|---|---|---|
| 缺 `name` / `md5` / `content_b64` | 400 | `missing_name` / `missing_md5` / `missing_content` | 参数缺失 |
| `content_b64` 非法 | 400 | `invalid_base64` | 不是合法 base64 |
| 内容为空（0 字节） | 400 | `empty_content` | INT-2202 口径 |
| 非音频（无法解码 / 时长 ≤ 0，含纯文本伪装 `.wav`） | 400 | `invalid_audio_content` | INT-2202 口径 |
| `md5` 与实际字节不一致 | 400 | `md5_mismatch` | **防错绑**：直接拒绝，不以实算 md5 静默改写 |
| 入库失败（DB 异常） | 500 | `persist_failed` | 已回滚 |

**幂等与落库语义**

1. **去重维度只认 md5**：先 `repo.get_audio_by_md5(md5)`（未软删记录）；命中直接返回既有 `id`（`reused=true`），不新建、不改名、不写标注/标签。
2. 同名不同 md5：允许新建（名称不是去重键）。
3. 落库复用既有上传链 `AudioTranscodingService.transcode_and_extract_metadata`：写临时文件 → 落存储 → 真实探测 `duration/sample_rate/channels/bitrate` → `repo.create_audio` + commit。`audios.duration` 为 NOT NULL，不在此处重算。
4. **合法 wav 不重编码**：存储对象字节与入参字节一致（`size`、`md5` 与入参一致，存储对象 md5 = `audios.md5`），保证「导入 → 导出（INT-2214）→ 再导入」往复中 md5 幂等键稳定。非 wav 输入按既有链转码为 wav 落存储。
5. 不迁移标注 / 标签 / 播放历史（用例包只带音频二进制）。
6. 登记成功后按既有口径刷新首页统计缓存（与 URL 导入一致，失败不影响登记结果）。

**调用方顺序（api_gateway 用例导入服务）**：先用 `GetAudioByMD5`（`{md5_list: [...]}` → `{md5: {id, name}}`）查目标库 → 命中直接复用 `id`；未命中再对包内文件调用本命令，取 `data.id` 做 config 的 audio_id 重映射。**传入的 `md5` 必须按包内文件实际字节计算**（不能取源库 `audios.md5` 回填），否则命中 `md5_mismatch` 被拒。


