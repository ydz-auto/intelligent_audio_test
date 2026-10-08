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
1. **参数验证**：校验目标格式、采样率、声道数、位深是否在支持范围内。
2. **转换引擎**：调用 `ffmpeg` 执行异步转换任务，ffmpeg 路径写在配置里。
3. **文件管理**：转换完成后，可选择替换原文件或另存为新文件。更新数据库中的元数据信息。

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
   - 从 `audios` 表中移除记录。
2. **批量导出**：将选中的音频文件打包为 `zip` 提供下载。
3. **批量修改标签**：批量更新 `audio_tags` 关联表。

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
